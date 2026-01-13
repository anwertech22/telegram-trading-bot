import os
import time
import csv
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
CHECK_EVERY = 900  # 15 minutes

RSI_BUY = 40
RSI_SELL = 60
MIN_CONFIDENCE = 60
NEAR_CONFIDENCE = 45

BREAKOUT_LOOKBACK = 20
BREAKOUT_BUFFER = 0.2
BREAKOUT_WEIGHT = 30

MIN_ATR = 1.5

# Counters
CANDLES_WITHOUT_TRADE = 0
NEAR_TRADES_COUNT = 0
ANALYZED_CANDLES = 0

LAST_DAILY_REPORT_DATE = None

# =========================
# ENV VARIABLES
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
TD_API_KEY = os.getenv("TD_API_KEY")

if not BOT_TOKEN or not TD_API_KEY:
    raise Exception("❌ Missing Environment Variables")

bot = telebot.TeleBot(BOT_TOKEN)
SUBSCRIBERS = set()
OPEN_TRADE = None

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
# ANALYSIS
# =========================
def analyze_market():
    global CANDLES_WITHOUT_TRADE, NEAR_TRADES_COUNT, ANALYZED_CANDLES

    ANALYZED_CANDLES += 1
    candles = get_candles()

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

    # RSI
    if r <= RSI_BUY:
        confidence += 25
        direction = "BUY"
    elif r >= RSI_SELL:
        confidence += 25
        direction = "SELL"

    # EMA
    if price > e20 and price > e50:
        confidence += 20
        direction = "BUY"
    elif price < e20 and price < e50:
        confidence += 20
        direction = "SELL"

    # ATR
    if a >= MIN_ATR:
        confidence += 15

    # Breakout
    recent_high = max(highs[-BREAKOUT_LOOKBACK:])
    recent_low = min(lows[-BREAKOUT_LOOKBACK:])

    if price > recent_high + BREAKOUT_BUFFER:
        confidence += BREAKOUT_WEIGHT
        direction = "BUY"
    elif price < recent_low - BREAKOUT_BUFFER:
        confidence += BREAKOUT_WEIGHT
        direction = "SELL"

    # Momentum Alert
    if abs(r - rsi(closes[:-1])) >= 5:
        for uid in SUBSCRIBERS:
            bot.send_message(
                uid,
                f"⚡ بداية زخم – XAUUSD M15\nRSI يتحرّك بقوة ({r:.2f})"
            )

    # Near Trade
    if NEAR_CONFIDENCE <= confidence < MIN_CONFIDENCE:
        NEAR_TRADES_COUNT += 1
        return "NEAR"

    # No Trade
    if confidence < MIN_CONFIDENCE or not direction:
        CANDLES_WITHOUT_TRADE += 1
        return None

    # Trade
    CANDLES_WITHOUT_TRADE = 0
    return {
        "direction": direction,
        "price": price,
        "atr": a,
        "confidence": confidence
    }

# =========================
# DAILY REPORT
# =========================
def send_daily_report():
    global LAST_DAILY_REPORT_DATE, ANALYZED_CANDLES, NEAR_TRADES_COUNT, CANDLES_WITHOUT_TRADE

    today = dz_now().date()
    if LAST_DAILY_REPORT_DATE == today:
        return

    if dz_now().hour == 23:
        for uid in SUBSCRIBERS:
            bot.send_message(
                uid,
                f"""
📊 التقرير اليومي – XAUUSD (M15)

🔍 الشموع المحللة: {ANALYZED_CANDLES}
⚠️ Near Trades: {NEAR_TRADES_COUNT}
⏳ شمعات بدون صفقة: {CANDLES_WITHOUT_TRADE}

🕒 التوقيت: الجزائر 🇩🇿
"""
            )

        LAST_DAILY_REPORT_DATE = today
        ANALYZED_CANDLES = 0
        NEAR_TRADES_COUNT = 0

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
📊 XAUUSD – M15
{'🟢 BUY' if result['direction']=='BUY' else '🔴 SELL'}
Price: {result['price']:.2f}
Confidence: {result['confidence']}%
"""
                    )

            if CANDLES_WITHOUT_TRADE % 8 == 0 and CANDLES_WITHOUT_TRADE != 0:
                for uid in SUBSCRIBERS:
                    bot.send_message(
                        uid,
                        f"⏳ لا توجد صفقات منذ {CANDLES_WITHOUT_TRADE} شمعات M15"
                    )

            send_daily_report()

        except Exception as e:
            print("ERROR:", e)

        for _ in range(CHECK_EVERY):
            time.sleep(1)

# =========================
# COMMANDS
# =========================
@bot.message_handler(commands=["start"])
def start(message):
    SUBSCRIBERS.add(message.chat.id)
    bot.send_message(
        message.chat.id,
        "🤖 البوت يعمل\n📍 توقيت الجزائر\n🧠 شفافية كاملة مفعّلة"
    )

# =========================
# START
# =========================
Thread(target=auto_loop, daemon=True).start()
bot.infinity_polling()
