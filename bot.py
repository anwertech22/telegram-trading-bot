import os
import time
import requests
import telebot
from datetime import datetime, timedelta
from threading import Thread

# =========================
# TIMEZONE (ALGERIA UTC+1)
# =========================
def dz_now():
    return datetime.utcnow() + timedelta(hours=1)

# =========================
# CONFIG
# =========================
DEBUG = True

PAIR = "XAUUSD"
INTERVAL = "15min"
CHECK_EVERY = 900

RSI_BUY = 40
RSI_SELL = 60
MIN_CONFIDENCE = 60

BREAKOUT_LOOKBACK = 20
BREAKOUT_BUFFER = 0.2
BREAKOUT_WEIGHT = 25

MIN_ATR = 1.5

# ICT SETTINGS
ICT_LOOKBACK = 20
FVG_BUFFER = 0.1

# =========================
# ENV
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
TD_API_KEY = os.getenv("TD_API_KEY")

if not BOT_TOKEN or not TD_API_KEY:
    raise Exception("Missing ENV")

bot = telebot.TeleBot(BOT_TOKEN)
SUBSCRIBERS = set()

# =========================
# HELPERS
# =========================
def get_candles(limit=200):
    r = requests.get(
        "https://api.twelvedata.com/time_series",
        params={
            "symbol": "XAU/USD",
            "interval": INTERVAL,
            "outputsize": limit,
            "apikey": TD_API_KEY
        },
        timeout=10
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
# ICT LOGIC
# =========================
def liquidity_sweep(highs, lows, closes):
    prev_high = max(highs[-ICT_LOOKBACK:-1])
    prev_low = min(lows[-ICT_LOOKBACK:-1])

    # Sweep High -> Sell
    if highs[-1] > prev_high and closes[-1] < prev_high:
        return "SELL"

    # Sweep Low -> Buy
    if lows[-1] < prev_low and closes[-1] > prev_low:
        return "BUY"

    return None

def fair_value_gap(highs, lows, direction):
    # ICT classic 3-candle FVG
    if direction == "BUY":
        if lows[-1] > highs[-3]:
            return True
    if direction == "SELL":
        if highs[-1] < lows[-3]:
            return True
    return False

# =========================
# ANALYSIS
# =========================
def analyze_market():
    candles = get_candles()
    if len(candles) < 100:
        return None

    closes = [float(c["close"]) for c in candles]
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]

    price = closes[-1]
    r = rsi(closes)
    e20 = ema(closes[-40:], 20)
    e50 = ema(closes[-80:], 50)
    a = atr(highs, lows, closes)

    confidence = 0
    direction = None
    reasons = []

    # RSI
    if r <= RSI_BUY:
        confidence += 20
        direction = "BUY"
    elif r >= RSI_SELL:
        confidence += 20
        direction = "SELL"
    else:
        reasons.append("RSI حيادي")

    # EMA
    if price > e20 and price > e50:
        confidence += 20
        direction = "BUY"
    elif price < e20 and price < e50:
        confidence += 20
        direction = "SELL"
    else:
        reasons.append("بين EMA")

    # ATR
    if a >= MIN_ATR:
        confidence += 10
    else:
        reasons.append("ATR ضعيف")

    # ICT FILTER 🔥
    sweep = liquidity_sweep(highs, lows, closes)
    if not sweep:
        reasons.append("لا يوجد Liquidity Sweep")
        return reasons

    if sweep != direction:
        reasons.append("Sweep ضد الاتجاه")
        return reasons

    fvg = fair_value_gap(highs, lows, direction)
    if not fvg:
        reasons.append("لا يوجد FVG")
        return reasons

    confidence += 30

    if confidence < MIN_CONFIDENCE:
        reasons.append(f"Confidence منخفض ({confidence}%)")
        return reasons

    return {
        "direction": direction,
        "price": price,
        "atr": a,
        "confidence": confidence
    }

# =========================
# AUTO LOOP
# =========================
def auto_loop():
    while True:
        try:
            result = analyze_market()

            if isinstance(result, dict):
                for uid in SUBSCRIBERS:
                    bot.send_message(
                        uid,
                        f"""
📊 XAUUSD – M15 (ICT FILTER)

{'🟢 BUY' if result['direction']=='BUY' else '🔴 SELL'}
Price: {result['price']:.2f}
Confidence: {result['confidence']}%
📌 Liquidity Sweep + FVG
"""
                    )

            elif DEBUG and isinstance(result, list):
                for uid in SUBSCRIBERS:
                    bot.send_message(
                        uid,
                        "🧪 DEBUG ICT\n" +
                        "\n".join(f"❌ {r}" for r in result)
                    )

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
        "🤖 البوت يعمل\n🧠 ICT Filter مفعل (Liquidity Sweep + FVG)"
    )

# =========================
# START
# =========================
Thread(target=auto_loop, daemon=True).start()
bot.infinity_polling()
