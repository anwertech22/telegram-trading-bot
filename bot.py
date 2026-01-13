import os
import time
import requests
import telebot
from threading import Thread
from datetime import datetime

# =========================
# Environment Variables
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
METALS_API_KEY = os.getenv("METALS_API_KEY")
TD_API_KEY = os.getenv("TD_API_KEY")

if not BOT_TOKEN or not METALS_API_KEY or not TD_API_KEY:
    raise Exception("❌ Missing Environment Variables")

bot = telebot.TeleBot(BOT_TOKEN)

# =========================
# Global State
# =========================
LAST_SIGNAL = None
SUBSCRIBERS = set()
NEWS_ALERT_SENT = False

# =========================
# News Filter (UTC)
# =========================
def is_news_time():
    now = datetime.utcnow().time()
    blocked = [("12:15", "13:45"), ("13:20", "14:00")]
    for s, e in blocked:
        if datetime.strptime(s, "%H:%M").time() <= now <= datetime.strptime(e, "%H:%M").time():
            return True
    return False

# =========================
# Price (Metals API)
# =========================
def get_xauusd_price():
    r = requests.get(
        "https://metals-api.com/api/latest",
        params={"access_key": METALS_API_KEY, "base": "USD", "symbols": "XAU"},
        timeout=10
    )
    return round(1 / r.json()["rates"]["XAU"], 2)

# =========================
# OHLC (TwelveData)
# =========================
def get_ohlc(limit=120):
    r = requests.get(
        "https://api.twelvedata.com/time_series",
        params={
            "symbol": "XAU/USD",
            "interval": "5min",
            "outputsize": limit,
            "apikey": TD_API_KEY
        },
        timeout=10
    )
    values = r.json()["values"]
    values.reverse()
    highs = [float(v["high"]) for v in values]
    lows = [float(v["low"]) for v in values]
    closes = [float(v["close"]) for v in values]
    return highs, lows, closes

# =========================
# Indicators
# =========================
def calculate_rsi(closes, period=14):
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = closes[-i] - closes[-i - 1]
        (gains if diff >= 0 else losses).append(abs(diff))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period if losses else 0.0001
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def calculate_ema(closes, period):
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for price in closes[period:]:
        ema = price * k + ema * (1 - k)
    return round(ema, 2)

def calculate_atr(highs, lows, closes, period=14):
    trs = []
    for i in range(1, period + 1):
        tr = max(
            highs[-i] - lows[-i],
            abs(highs[-i] - closes[-i - 1]),
            abs(lows[-i] - closes[-i - 1])
        )
        trs.append(tr)
    return round(sum(trs) / period, 2)

# =========================
# Confidence Engine
# =========================
def calculate_confidence(rsi, price, ema20, ema50, atr, news_ok, direction):
    score = 0
    reasons = []

    # RSI
    if (direction == "SELL" and rsi >= 70) or (direction == "BUY" and rsi <= 30):
        score += 30
        reasons.append("RSI متطرف")

    # Trend
    if direction == "SELL" and price < ema20 and price < ema50:
        score += 25
        reasons.append("اتجاه هابط")
    if direction == "BUY" and price > ema20 and price > ema50:
        score += 25
        reasons.append("اتجاه صاعد")

    # Momentum (distance from EMA20)
    if abs(price - ema20) >= atr * 0.3:
        score += 15
        reasons.append("زخم كافٍ")

    # ATR sanity
    if atr >= 3:
        score += 15
        reasons.append("تذبذب مناسب")

    # News
    if news_ok:
        score += 15
        reasons.append("لا أخبار")

    return score, reasons

# =========================
# Signal Logic
# =========================
def analyze_market():
    price = get_xauusd_price()
    highs, lows, closes = get_ohlc()

    rsi = calculate_rsi(closes)
    ema20 = calculate_ema(closes, 20)
    ema50 = calculate_ema(closes, 50)
    atr = calculate_atr(highs, lows, closes)

    # Decide direction candidate
    candidates = []
    if rsi >= 70:
        candidates.append("SELL")
    if rsi <= 30:
        candidates.append("BUY")

    if not candidates:
        return ("NO_TRADE", None)

    for direction in candidates:
        conf, reasons = calculate_confidence(
            rsi, price, ema20, ema50, atr, not is_news_time(), direction
        )
        if conf >= 70:
            sl = round(price + (atr * 1.5), 2) if direction == "SELL" else round(price - (atr * 1.5), 2)
            tp = round(price - (atr * 2.5), 2) if direction == "SELL" else round(price + (atr * 2.5), 2)
            return (direction, f"""
📊 XAUUSD – M5
{"🔴 SELL" if direction=="SELL" else "🟢 BUY"} @ {price}

RSI: {rsi}
EMA20: {ema20}
EMA50: {ema50}
ATR: {atr}

🎯 TP: {tp}
❌ SL: {sl}

Confidence: {conf}%
Reasons:
- {" | ".join(reasons)}
""")

    return ("NO_TRADE", None)

# =========================
# Auto Loop
# =========================
def auto_loop():
    global LAST_SIGNAL, NEWS_ALERT_SENT
    while True:
        try:
            if is_news_time():
                if not NEWS_ALERT_SENT:
                    for cid in SUBSCRIBERS:
                        bot.send_message(cid, "⛔ التداول متوقف بسبب أخبار قوية")
                    NEWS_ALERT_SENT = True
            else:
                NEWS_ALERT_SENT = False
                signal, text = analyze_market()
                if signal not in ("NO_TRADE", LAST_SIGNAL):
                    for cid in SUBSCRIBERS:
                        bot.send_message(cid, text)
                    LAST_SIGNAL = signal
        except Exception:
            pass
        time.sleep(300)

# =========================
# Commands
# =========================
@bot.message_handler(commands=["start"])
def start(message):
    SUBSCRIBERS.add(message.chat.id)
    bot.send_message(
        message.chat.id,
        "🤖 إشارات تلقائية مفعّلة\n"
        "🧠 نظام Confidence بالنقاط\n"
        "⏱️ فحص كل 5 دقائق"
    )

# =========================
# Run
# =========================
Thread(target=auto_loop).start()
print("🤖 Bot running with CONFIDENCE ENGINE")
bot.polling(none_stop=True)
