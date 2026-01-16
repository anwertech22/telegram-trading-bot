# ======================================
# BOT WITH STAT ENGINE + TELEGRAM (FIXED)
# ======================================

import os
import time
import random
import threading
from datetime import datetime
from collections import defaultdict
import telebot

# ===============================
# TELEGRAM
# ===============================
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise Exception("BOT_TOKEN missing")

bot = telebot.TeleBot(BOT_TOKEN)
SUBSCRIBERS = set()

# ===============================
# SETTINGS
# ===============================
SYMBOL = "XAUUSD"
RSI_BUY = 35
RSI_SELL = 65
EMA_PERIOD = 20
CHECK_INTERVAL = 60

BASE_CONFIDENCE = 60
POST_DUMP_CONF_BOOST = 15
ICT_PRIORITY_BOOST = 10

ATR_MULTIPLIER = 1.8
BODY_MULTIPLIER = 1.5

# ===============================
# GLOBAL STATE
# ===============================
open_trades = []
LIQUIDITY_DUMP_ACTIVE = False
POST_DUMP_MODE = False

stats = {
    "total": 0,
    "wins": 0,
    "losses": 0,
    "by_strategy": defaultdict(lambda: {"wins": 0, "losses": 0})
}

# ===============================
# INDICATORS
# ===============================
def ema(values, period):
    k = 2 / (period + 1)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e

def atr(candles):
    tr = []
    for i in range(1, len(candles)):
        tr.append(max(
            candles[i]['high'] - candles[i]['low'],
            abs(candles[i]['high'] - candles[i-1]['close']),
            abs(candles[i]['low'] - candles[i-1]['close'])
        ))
    return sum(tr[-14:]) / 14

# ===============================
# CANDLES
# ===============================
def is_hammer(c):
    body = abs(c['close'] - c['open'])
    wick = min(c['open'], c['close']) - c['low']
    return wick > body * 2

def is_pinbar(c):
    body = abs(c['close'] - c['open'])
    full = c['high'] - c['low']
    return body < full * 0.3

# ===============================
# LIQUIDITY DUMP
# ===============================
def detect_liquidity_dump(candles):
    global LIQUIDITY_DUMP_ACTIVE, POST_DUMP_MODE

    bodies = [abs(c['close'] - c['open']) for c in candles[-10:-1]]
    avg_body = sum(bodies) / len(bodies)
    last = candles[-1]

    body = abs(last['close'] - last['open'])
    current_atr = atr(candles)
    avg_atr = sum([atr(candles[:i]) for i in range(len(candles)-5, len(candles)-1)]) / 4

    if body > avg_body * BODY_MULTIPLIER and current_atr > avg_atr * ATR_MULTIPLIER:
        LIQUIDITY_DUMP_ACTIVE = True
        POST_DUMP_MODE = True

# ===============================
# CONFIDENCE
# ===============================
def calc_conf(strategy):
    conf = BASE_CONFIDENCE
    if POST_DUMP_MODE:
        conf += POST_DUMP_CONF_BOOST
    if strategy == "ICT" and POST_DUMP_MODE:
        conf += ICT_PRIORITY_BOOST
    return min(conf, 90)

# ===============================
# TRADE HANDLING
# ===============================
def open_trade(strategy, direction, price):
    conf = calc_conf(strategy)

    trade = {
        "strategy": strategy,
        "direction": direction,
        "entry": price,
        "tp": price + 10 if direction == "BUY" else price - 10,
        "sl": price - 6 if direction == "BUY" else price + 6,
        "time": datetime.now()
    }

    open_trades.append(trade)

    msg = (
        f"📊 {strategy} SIGNAL\n"
        f"{SYMBOL}\n"
        f"Direction: {direction}\n"
        f"Entry: {price:.2f}\n"
        f"Confidence: {conf}%"
    )

    for u in SUBSCRIBERS:
        bot.send_message(u, msg)

def check_trades(price):
    for trade in open_trades[:]:
        hit_tp = trade["direction"] == "BUY" and price >= trade["tp"] or \
                 trade["direction"] == "SELL" and price <= trade["tp"]
        hit_sl = trade["direction"] == "BUY" and price <= trade["sl"] or \
                 trade["direction"] == "SELL" and price >= trade["sl"]

        if hit_tp or hit_sl:
            stats["total"] += 1
            if hit_tp:
                stats["wins"] += 1
                stats["by_strategy"][trade["strategy"]]["wins"] += 1
                result = "✅ WIN"
            else:
                stats["losses"] += 1
                stats["by_strategy"][trade["strategy"]]["losses"] += 1
                result = "❌ LOSS"

            for u in SUBSCRIBERS:
                bot.send_message(u, f"{result} | {trade['strategy']}")

            open_trades.remove(trade)

# ===============================
# MOCK DATA (كما كان سابقًا)
# ===============================
def mock_candles():
    base = 4600 + random.uniform(-5, 5)
    candles = []
    for _ in range(30):
        o = base + random.uniform(-3, 3)
        c = o + random.uniform(-5, 5)
        h = max(o, c) + random.uniform(0, 3)
        l = min(o, c) - random.uniform(0, 3)
        candles.append({"open": o, "high": h, "low": l, "close": c})
        base = c
    return candles

def mock_rsi():
    return random.randint(20, 80)

# ===============================
# MAIN ENGINE
# ===============================
def engine_loop():
    global LIQUIDITY_DUMP_ACTIVE, POST_DUMP_MODE

    while True:
        candles = mock_candles()
        rsi = mock_rsi()
        prices = [c['close'] for c in candles]

        detect_liquidity_dump(candles)

        if POST_DUMP_MODE and prices[-1] > ema(prices, EMA_PERIOD):
            LIQUIDITY_DUMP_ACTIVE = False
            POST_DUMP_MODE = False

        if not LIQUIDITY_DUMP_ACTIVE:
            if rsi <= RSI_BUY:
                open_trade("Scalping", "BUY", prices[-1])
            elif rsi >= RSI_SELL:
                open_trade("Scalping", "SELL", prices[-1])

        check_trades(prices[-1])
        time.sleep(CHECK_INTERVAL)

# ===============================
# TELEGRAM COMMAND
# ===============================
@bot.message_handler(commands=["start"])
def start(msg):
    SUBSCRIBERS.add(msg.chat.id)
    bot.send_message(msg.chat.id, "🤖 Bot reconnected and running ✅")

# ===============================
# START
# ===============================
if __name__ == "__main__":
    threading.Thread(target=engine_loop, daemon=True).start()
    bot.infinity_polling()
