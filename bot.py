import os
import time
import csv
import requests
import telebot
from datetime import datetime
from threading import Thread

# =========================
# CONFIG
# =========================
DEBUG = True

PAIR = "XAUUSD"
INTERVAL = "15min"
CHECK_EVERY = 900  # 15 minutes

# تخفيف ذكي
MIN_CONFIDENCE = 60
RSI_BUY = 35
RSI_SELL = 65
MIN_ATR = 1.5

# =========================
# ENV VARIABLES
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
METALS_API_KEY = os.getenv("METALS_API_KEY")
TD_API_KEY = os.getenv("TD_API_KEY")

if not BOT_TOKEN or not METALS_API_KEY or not TD_API_KEY:
    raise Exception("❌ Missing Environment Variables")

bot = telebot.TeleBot(BOT_TOKEN)

SUBSCRIBERS = set()
OPEN_TRADE = None
TRADES_FILE = "trades.csv"

# =========================
# INIT CSV
# =========================
if not os.path.exists(TRADES_FILE):
    with open(TRADES_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "pair", "direction", "entry", "tp", "sl", "result"])

# =========================
# HELPERS
# =========================
def save_trade(direction, entry, tp, sl, result="OPEN"):
    with open(TRADES_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
            PAIR,
            direction,
            entry,
            tp,
            sl,
            result
        ])

def get_price():
    r = requests.get(
        "https://api.metals.dev/v1/latest",
        params={"api_key": METALS_API_KEY, "symbols": "XAU"}
    )
    return float(r.json()["rates"]["XAU"])

def get_candles(limit=150):
    r = requests.get(
        "https://api.twelvedata.com/time_series",
        params={
            "symbol": "XAU/USD",
            "interval": INTERVAL,
            "outputsize": limit,
            "apikey": TD_API_KEY
        }
    )
    data = r.json().get("values", [])
    data.reverse()
    return data

def ema(values, period):
    k = 2 / (period + 1)
    ema_val = sum(values[:period]) / period
    for v in values[period:]:
        ema_val = v * k + ema_val * (1 - k)
    return ema_val

def rsi(values, period=14):
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = values[-i] - values[-i - 1]
        if diff >= 0:
            gains.append(diff)
        else:
            losses.append(abs(diff))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period if losses else 0.0001
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def atr(highs, lows, closes, period=14):
    trs = []
    for i in range(1, period + 1):
        trs.append(max(
            highs[-i] - lows[-i],
            abs(highs[-i] - closes[-i - 1]),
            abs(lows[-i] - closes[-i - 1])
        ))
    return sum(trs) / period

# =========================
# ANALYSIS
# =========================
def analyze_market():
    reasons = []
    candles = get_candles()

    if len(candles) < 80:
        return ["بيانات غير كافية"]

    closes = [float(c["close"]) for c in candles]
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]

    price = closes[-1]
    r = rsi(closes)
    e20 = ema(closes[-40:], 20)
    e50 = ema(closes[-80:], 50)
    a = atr(highs, lows, closes)

    confidence = 0
    trend = None

    # RSI
    if r <= RSI_BUY or r >= RSI_SELL:
        confidence += 30
    else:
        reasons.append(f"RSI غير مناسب ({r:.2f})")

    # EMA Trend
    if price > e20 and price > e50:
        trend = "BUY"
        confidence += 25
    elif price < e20 and price < e50:
        trend = "SELL"
        confidence += 25
    else:
        reasons.append("السعر بين EMA20 و EMA50")

    # ATR
    if a >= MIN_ATR:
        confidence += 20
    else:
        reasons.append(f"ATR ضعيف ({a:.2f})")

    if confidence < MIN_CONFIDENCE:
        reasons.append(f"Confidence منخفض ({confidence}%)")

    if reasons:
        return reasons

    return {
        "direction": trend,
        "price": price,
        "atr": a,
        "confidence": confidence
    }

# =========================
# AUTO LOOP
# =========================
def auto_loop():
    global OPEN_TRADE
    while True:
        try:
            print("🔍 Checking market", datetime.utcnow())

            if OPEN_TRADE is None:
                result = analyze_market()

                if isinstance(result, list):
                    if DEBUG:
                        for uid in SUBSCRIBERS:
                            bot.send_message(
                                uid,
                                "🧪 DEBUG MODE\n" +
                                "\n".join(f"❌ {r}" for r in result)
                            )
                else:
                    direction = result["direction"]
                    price = result["price"]
                    a = result["atr"]

                    tp = price + a * 2.5 if direction == "BUY" else price - a * 2.5
                    sl = price - a * 1.5 if direction == "BUY" else price + a * 1.5

                    save_trade(direction, price, tp, sl)

                    for uid in SUBSCRIBERS:
                        bot.send_message(
                            uid,
                            f"""
📊 XAUUSD – M15
{'🟢 BUY' if direction=='BUY' else '🔴 SELL'} @ {price:.2f}
🎯 TP: {tp:.2f}
❌ SL: {sl:.2f}
🧠 Confidence: {result['confidence']}%
"""
                        )

                    OPEN_TRADE = True

        except Exception as e:
            print("ERROR:", e)

        time.sleep(CHECK_EVERY)

# =========================
# COMMANDS
# =========================
@bot.message_handler(commands=["start"])
def start(message):
    SUBSCRIBERS.add(message.chat.id)
    bot.send_message(
        message.chat.id,
        "🤖 البوت يعمل\n⏱️ فريم M15\n🧪 DEBUG MODE مفعل"
    )

@bot.message_handler(commands=["stats"])
def stats(message):
    with open(TRADES_FILE, "r") as f:
        rows = list(csv.DictReader(f))

    total = len(rows)
    wins = sum(1 for r in rows if r["result"] == "WIN")
    losses = sum(1 for r in rows if r["result"] == "LOSS")
    winrate = round((wins / total) * 100, 2) if total else 0

    bot.send_message(
        message.chat.id,
        f"""
📊 XAUUSD – إحصائيات الأداء

Total Trades: {total}
Wins: {wins}
Losses: {losses}
Win Rate: {winrate}%
"""
    )

@bot.message_handler(commands=["force"])
def force_trade(message):
    price = get_price()
    atr_val = 5.0

    tp = price - atr_val * 2.5
    sl = price + atr_val * 1.5

    save_trade("SELL", price, tp, sl)

    bot.send_message(
        message.chat.id,
        f"""
🧪 FORCED TRADE (TEST)

XAUUSD – M15
🔴 SELL @ {price:.2f}
🎯 TP: {tp:.2f}
❌ SL: {sl:.2f}
🧠 Confidence: 100%
"""
    )

# =========================
# START
# =========================
Thread(target=auto_loop, daemon=True).start()
print("🤖 BOT STARTED – M15 MODE")
bot.infinity_polling()
