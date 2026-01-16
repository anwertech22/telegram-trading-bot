# ======================================
# WORKING TELEGRAM TRADING BOT (STABLE)
# ======================================

import time
import telebot
from datetime import datetime
from collections import defaultdict

# ===============================
# TELEGRAM
# ===============================

TELEGRAM_TOKEN = "PUT_YOUR_TOKEN_HERE"
bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML")

# ===============================
# SETTINGS
# ===============================

SYMBOL = "XAUUSD"
TIMEFRAME = "M5"

RSI_BUY = 35
RSI_SELL = 65

EMA_PERIOD = 20
ATR_PERIOD = 14

SL_ATR_MULT = 1.0
TP_ATR_MULT = 1.5

BASE_CONFIDENCE = 60

# ===============================
# GLOBAL STATE
# ===============================

open_trades = []
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
    ema_vals = []
    for i, v in enumerate(values):
        ema_vals.append(v if i == 0 else v * k + ema_vals[-1] * (1 - k))
    return ema_vals

def atr(candles, period=ATR_PERIOD):
    trs = []
    for i in range(1, len(candles)):
        high = candles[i]["high"]
        low = candles[i]["low"]
        prev_close = candles[i-1]["close"]
        trs.append(max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        ))
    if len(trs) < period:
        return sum(trs) / max(1, len(trs))
    return sum(trs[-period:]) / period

# ===============================
# TELEGRAM MESSAGES
# ===============================

def send_signal(strategy, direction, entry, sl, tp, confidence):
    msg = (
        f"📊 <b>{strategy} SIGNAL</b>\n"
        f"<b>{SYMBOL}</b> ({TIMEFRAME})\n"
        f"Direction: <b>{direction}</b>\n"
        f"Entry: <b>{entry:.2f}</b>\n"
        f"TP: <b>{tp:.2f}</b>\n"
        f"SL: <b>{sl:.2f}</b>\n"
        f"Confidence: <b>{confidence}%</b>"
    )
    bot.send_message(CHAT_ID, msg)

def send_result(win, strategy):
    if win:
        bot.send_message(CHAT_ID, f"✅ <b>WIN</b> | {strategy}")
    else:
        bot.send_message(CHAT_ID, f"❌ <b>LOSS</b> | {strategy}")

# ===============================
# TRADE ENGINE
# ===============================

def open_trade(strategy, direction, price, atr_value):
    sl = price - SL_ATR_MULT * atr_value if direction == "BUY" else price + SL_ATR_MULT * atr_value
    tp = price + TP_ATR_MULT * atr_value if direction == "BUY" else price - TP_ATR_MULT * atr_value

    trade = {
        "strategy": strategy,
        "direction": direction,
        "entry": price,
        "sl": sl,
        "tp": tp,
        "time": datetime.now()
    }
    open_trades.append(trade)

    send_signal(strategy, direction, price, sl, tp, BASE_CONFIDENCE)

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
                send_result(True, trade["strategy"])
            else:
                stats["losses"] += 1
                stats["by_strategy"][trade["strategy"]]["losses"] += 1
                send_result(False, trade["strategy"])

            open_trades.remove(trade)

# ===============================
# SIMPLE STRATEGY (WORKING)
# ===============================

def on_new_candle(candles, rsi_value):
    prices = [c["close"] for c in candles]
    ema20 = ema(prices, EMA_PERIOD)
    atr_value = atr(candles)

    price = prices[-1]

    # BUY
    if rsi_value <= RSI_BUY and price > ema20[-1]:
        open_trade("Scalping", "BUY", price, atr_value)

    # SELL
    if rsi_value >= RSI_SELL and price < ema20[-1]:
        open_trade("Scalping", "SELL", price, atr_value)

    check_trades(price)

# ===============================
# COMMANDS
# ===============================

@bot.message_handler(commands=["start"])
def start_cmd(message):
    global CHAT_ID
    CHAT_ID = message.chat.id
    bot.send_message(
        CHAT_ID,
        "🤖 <b>Bot connected and running ✅</b>\n"
        "Scalping active | ATR SL/TP | Stats enabled"
    )

@bot.message_handler(commands=["stats"])
def stats_cmd(message):
    if stats["total"] == 0:
        bot.send_message(message.chat.id, "📊 No trades yet")
        return

    winrate = (stats["wins"] / stats["total"]) * 100
    msg = (
        f"📊 <b>STATS</b>\n"
        f"Total: {stats['total']}\n"
        f"Wins: {stats['wins']}\n"
        f"Losses: {stats['losses']}\n"
        f"Winrate: {winrate:.2f}%"
    )
    bot.send_message(message.chat.id, msg)

# ===============================
# RUN
# ===============================

print("Bot running...")
bot.polling(none_stop=True)
