# =====================================================
# FINAL WORKING TELEGRAM TRADING BOT (RENDER SAFE)
# =====================================================

import os
import time
import random
import threading
from datetime import datetime
from collections import defaultdict
import telebot

# -----------------------
# TELEGRAM
# -----------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set")

bot = telebot.TeleBot(BOT_TOKEN)
SUBSCRIBERS = set()

# -----------------------
# SETTINGS
# -----------------------
SYMBOL = "XAUUSD"
TIMEFRAME = "M5"

RSI_BUY = 35
RSI_SELL = 65

EMA_PERIOD = 20
ATR_PERIOD = 14

SL_ATR_MULT = 0.8
TP_ATR_MULT = 1.6

BASE_CONFIDENCE = 60
POST_DUMP_BOOST = 15

BODY_MULT = 1.5
ATR_DUMP_MULT = 1.8

CHECK_INTERVAL = 60  # seconds

# -----------------------
# STATE
# -----------------------
open_trades = []
LIQUIDITY_DUMP = False
POST_DUMP = False

stats = {
    "total": 0,
    "wins": 0,
    "losses": 0,
    "by_strategy": defaultdict(lambda: {"wins": 0, "losses": 0})
}

# -----------------------
# INDICATORS
# -----------------------
def ema(values, period):
    k = 2 / (period + 1)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e

def atr(candles, period=ATR_PERIOD):
    trs = []
    for i in range(1, len(candles)):
        h = candles[i]["high"]
        l = candles[i]["low"]
        pc = candles[i-1]["close"]
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period

def rsi_from_closes(closes, period=14):
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]
        gains.append(max(d, 0))
        losses.append(abs(min(d, 0)))
    if len(gains) < period:
        return None
    ag = sum(gains[-period:]) / period
    al = sum(losses[-period:]) / period
    if al == 0:
        return 100
    rs = ag / al
    return 100 - (100 / (1 + rs))

# -----------------------
# CANDLES
# -----------------------
def is_hammer(c):
    body = abs(c["close"] - c["open"])
    lower = min(c["open"], c["close"]) - c["low"]
    return lower > body * 2

def is_pinbar(c):
    body = abs(c["close"] - c["open"])
    full = c["high"] - c["low"]
    return body < full * 0.3

# -----------------------
# LIQUIDITY DUMP
# -----------------------
def detect_dump(candles):
    global LIQUIDITY_DUMP, POST_DUMP
    if len(candles) < 20:
        return
    bodies = [abs(c["close"]-c["open"]) for c in candles[-6:-1]]
    avg_body = sum(bodies)/len(bodies)
    last = candles[-1]
    body = abs(last["close"]-last["open"])
    a_now = atr(candles)
    a_prev = atr(candles[:-1])
    if a_now and a_prev and body > avg_body*BODY_MULT and a_now > a_prev*ATR_DUMP_MULT:
        LIQUIDITY_DUMP = True
        POST_DUMP = True

# -----------------------
# TRADE MGMT
# -----------------------
def open_trade(strategy, direction, entry, atr_val):
    sl = entry - atr_val*SL_ATR_MULT if direction=="BUY" else entry + atr_val*SL_ATR_MULT
    tp = entry + atr_val*TP_ATR_MULT if direction=="BUY" else entry - atr_val*TP_ATR_MULT
    trade = {
        "strategy": strategy,
        "direction": direction,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "open": True,
        "time": datetime.utcnow()
    }
    open_trades.append(trade)

    conf = BASE_CONFIDENCE + (POST_DUMP_BOOST if strategy=="ICT" else 0)
    msg = (
        f"📊 {strategy} SIGNAL\n{SYMBOL} ({TIMEFRAME})\n"
        f"Dir: {direction}\nEntry: {entry:.2f}\n"
        f"TP: {tp:.2f}\nSL: {sl:.2f}\n"
        f"Confidence: {conf}%"
    )
    for u in SUBSCRIBERS:
        bot.send_message(u, msg)

def update_trades(candle):
    hi, lo = candle["high"], candle["low"]
    for t in open_trades[:]:
        if not t["open"]:
            continue
        hit_tp = (t["direction"]=="BUY" and hi>=t["tp"]) or (t["direction"]=="SELL" and lo<=t["tp"])
        hit_sl = (t["direction"]=="BUY" and lo<=t["sl"]) or (t["direction"]=="SELL" and hi>=t["sl"])
        if hit_tp or hit_sl:
            t["open"] = False
            stats["total"] += 1
            if hit_tp:
                stats["wins"] += 1
                stats["by_strategy"][t["strategy"]]["wins"] += 1
                res = "✅ WIN"
            else:
                stats["losses"] += 1
                stats["by_strategy"][t["strategy"]]["losses"] += 1
                res = "❌ LOSS"
            for u in SUBSCRIBERS:
                bot.send_message(u, f"{res} | {t['strategy']}")
            open_trades.remove(t)

# -----------------------
# MOCK MARKET (حتى تربطه ببياناتك)
# -----------------------
def mock_candles():
    base = 4600 + random.uniform(-5,5)
    cs=[]
    for _ in range(30):
        o = base + random.uniform(-3,3)
        c = o + random.uniform(-5,5)
        h = max(o,c)+random.uniform(0,3)
        l = min(o,c)-random.uniform(0,3)
        cs.append({"open":o,"high":h,"low":l,"close":c})
        base=c
    return cs

# -----------------------
# ENGINE LOOP (BLOCKING)
# -----------------------
def engine_loop():
    global LIQUIDITY_DUMP, POST_DUMP
    while True:
        candles = mock_candles()
        closes = [c["close"] for c in candles]
        rsi = rsi_from_closes(closes)
        e20 = ema(closes, EMA_PERIOD)
        a = atr(candles)
        if not a or rsi is None:
            time.sleep(CHECK_INTERVAL); continue

        detect_dump(candles)
        last = candles[-1]

        # Post-dump re-entry (ICT)
        if POST_DUMP and (is_hammer(last) or is_pinbar(last)) and last["close"]>e20:
            open_trade("ICT","BUY",last["close"],a)
            POST_DUMP=False; LIQUIDITY_DUMP=False
        # Normal scalping only if safe
        if not LIQUIDITY_DUMP:
            if rsi<=RSI_BUY and last["close"]>e20:
                open_trade("Scalping","BUY",last["close"],a)
            elif rsi>=RSI_SELL and last["close"]<e20:
                open_trade("Scalping","SELL",last["close"],a)

        update_trades(last)
        time.sleep(CHECK_INTERVAL)

# -----------------------
# TELEGRAM COMMANDS
# -----------------------
@bot.message_handler(commands=["start"])
def start_cmd(m):
    SUBSCRIBERS.add(m.chat.id)
    bot.send_message(m.chat.id,"🤖 Bot running ✅")

@bot.message_handler(commands=["stats"])
def stats_cmd(m):
    if stats["total"]==0:
        bot.send_message(m.chat.id,"📊 No trades yet")
        return
    wr = stats["wins"]/stats["total"]*100
    bot.send_message(
        m.chat.id,
        f"📊 STATS\nTotal: {stats['total']}\nWins: {stats['wins']}\nLosses: {stats['losses']}\nWinrate: {wr:.2f}%"
    )

# -----------------------
# START (IMPORTANT)
# -----------------------
if __name__ == "__main__":
    threading.Thread(target=engine_loop, daemon=True).start()
    bot.infinity_polling()
