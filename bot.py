# ==================================================
# FINAL TELEGRAM TRADING BOT (RENDER + TELEBOT)
# ==================================================

import os
import time
import math
import threading
from datetime import datetime
import telebot

# ==================================================
# ENV
# ==================================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise Exception("❌ BOT_TOKEN not found in ENV")

bot = telebot.TeleBot(BOT_TOKEN)

# ==================================================
# CONFIG
# ==================================================
SYMBOL = "XAUUSD"
TIMEZONE = "UTC+1 (Algeria)"

CHECK_INTERVAL = 60  # seconds

EMA_PERIOD = 20
RSI_BUY = 35
RSI_SELL = 65

CONFIDENCE_MIN = 60

ATR_MULTIPLIER = 1.8
BODY_MULTIPLIER = 1.5

# ==================================================
# STATE
# ==================================================
SUBSCRIBERS = set()
LIQUIDITY_DUMP_ACTIVE = False
POST_DUMP_MODE = False
last_signal_time = None

# ==================================================
# UTILITIES
# ==================================================
def log(msg):
    print(f"[{datetime.utcnow()}] {msg}")

# ==================================================
# MOCK MARKET DATA (SAFE FOR RENDER)
# ==================================================
def get_market_data():
    base = 4600
    closes = [base + math.sin(i / 3) * 12 for i in range(50)]
    highs = [c + 6 for c in closes]
    lows = [c - 6 for c in closes]
    return closes, highs, lows

# ==================================================
# INDICATORS
# ==================================================
def ema(values, period):
    k = 2 / (period + 1)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e

def rsi(values, period=14):
    gains, losses = [], []
    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        if diff >= 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))
    if len(gains) < period:
        return None
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def atr(highs, lows, closes, period=14):
    trs = []
    for i in range(1, len(closes)):
        trs.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1])
        ))
    return sum(trs[-period:]) / period if len(trs) >= period else None

# ==================================================
# LIQUIDITY DUMP DETECTOR
# ==================================================
def detect_liquidity_dump(highs, lows, closes):
    global LIQUIDITY_DUMP_ACTIVE, POST_DUMP_MODE

    current_atr = atr(highs, lows, closes)
    avg_atr = atr(highs[:-1], lows[:-1], closes[:-1])

    if not current_atr or not avg_atr:
        return

    if current_atr > avg_atr * ATR_MULTIPLIER:
        LIQUIDITY_DUMP_ACTIVE = True
        POST_DUMP_MODE = True
        log("🔥 Liquidity Dump Detected")

# ==================================================
# SIGNAL ENGINE
# ==================================================
def analyze_market():
    global last_signal_time, LIQUIDITY_DUMP_ACTIVE, POST_DUMP_MODE

    closes, highs, lows = get_market_data()

    detect_liquidity_dump(highs, lows, closes)

    ema20 = ema(closes, EMA_PERIOD)
    rsi_val = rsi(closes)
    price = closes[-1]

    # Block during dump
    if LIQUIDITY_DUMP_ACTIVE:
        if price > ema20:
            LIQUIDITY_DUMP_ACTIVE = False
            POST_DUMP_MODE = False
            log("✅ Post-Dump recovery confirmed")
        else:
            return

    direction = None
    confidence = CONFIDENCE_MIN

    if price > ema20 and rsi_val and rsi_val <= RSI_BUY:
        direction = "BUY"
    elif price < ema20 and rsi_val and rsi_val >= RSI_SELL:
        direction = "SELL"

    if not direction:
        return

    # Prevent spam
    now = datetime.utcnow().minute
    if last_signal_time == now:
        return
    last_signal_time = now

    msg = (
        f"📊 إشارة تداول\n"
        f"{SYMBOL}\n"
        f"الاتجاه: {direction}\n"
        f"السعر: {price:.2f}\n"
        f"🧠 Confidence: {confidence}%\n\n"
        f"⏱ Timezone: {TIMEZONE}"
    )

    for uid in SUBSCRIBERS:
        bot.send_message(uid, msg)

# ==================================================
# BACKGROUND LOOP (RENDER SAFE)
# ==================================================
def market_loop():
    log("🤖 Market engine started")
    while True:
        try:
            analyze_market()
        except Exception as e:
            log(f"ERROR: {e}")
        time.sleep(CHECK_INTERVAL)

# ==================================================
# TELEGRAM COMMANDS
# ==================================================
@bot.message_handler(commands=["start"])
def start(message):
    SUBSCRIBERS.add(message.chat.id)
    bot.send_message(
        message.chat.id,
        "🤖 البوت يعمل الآن بنجاح ✅\n\n"
        "📊 XAUUSD\n"
        "🧠 EMA20 + RSI\n"
        "🔥 Liquidity Dump Protection\n"
        "⏱ يعمل 24/7 على Render\n\n"
        "سيتم إرسال الإشارات تلقائيًا عند توفر فرصة."
    )

# ==================================================
# START BOT (IMPORTANT)
# ==================================================
if __name__ == "__main__":
    threading.Thread(target=market_loop, daemon=True).start()
    log("📡 Telegram polling started")
    bot.infinity_polling()
