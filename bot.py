# ======================================
# FINAL BOT WITH AUTO STATISTICS ENGINE
# ======================================

import time
from datetime import datetime
from collections import defaultdict

# ===============================
# SETTINGS
# ===============================

SYMBOL = "XAUUSD"

RSI_BUY = 35
RSI_SELL = 65

EMA_PERIOD = 20

BASE_CONFIDENCE = 60
POST_DUMP_CONF_BOOST = 15
ICT_PRIORITY_BOOST = 10

ATR_MULTIPLIER = 1.8
BODY_MULTIPLIER = 1.5

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

LIQUIDITY_DUMP_ACTIVE = False
POST_DUMP_MODE = False

# ===============================
# INDICATORS (SIMPLIFIED)
# ===============================

def ema(values, period):
    k = 2 / (period + 1)
    ema_vals = []
    for i, v in enumerate(values):
        ema_vals.append(v if i == 0 else v * k + ema_vals[-1] * (1 - k))
    return ema_vals

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
# CANDLE PATTERNS
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
        print("🧨 Liquidity Dump detected")

# ===============================
# POST DUMP REENTRY
# ===============================

def post_dump_reentry(candles, ema20):
    global LIQUIDITY_DUMP_ACTIVE, POST_DUMP_MODE

    last = candles[-1]
    reject = (is_hammer(last) or is_pinbar(last))
    above_ema = last['close'] > ema20[-1]

    if POST_DUMP_MODE and reject and above_ema:
        LIQUIDITY_DUMP_ACTIVE = False
        POST_DUMP_MODE = False
        return True

    return False

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
    trade = {
        "strategy": strategy,
        "direction": direction,
        "entry": price,
        "tp": price + 10 if direction == "BUY" else price - 10,
        "sl": price - 6 if direction == "BUY" else price + 6,
        "time": datetime.now()
    }
    open_trades.append(trade)
    print(f"📥 OPEN {strategy} {direction} @ {price}")

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
                print(f"✅ WIN {trade['strategy']}")
            else:
                stats["losses"] += 1
                stats["by_strategy"][trade["strategy"]]["losses"] += 1
                print(f"❌ LOSS {trade['strategy']}")

            open_trades.remove(trade)

# ===============================
# STATS REPORT
# ===============================

def print_stats():
    if stats["total"] == 0:
        print("📊 No trades yet")
        return

    winrate = (stats["wins"] / stats["total"]) * 100
    print("\n📊 PERFORMANCE REPORT")
    print(f"Total Trades: {stats['total']}")
    print(f"Wins: {stats['wins']}")
    print(f"Losses: {stats['losses']}")
    print(f"Win Rate: {winrate:.2f}%")

    for strat, s in stats["by_strategy"].items():
        total = s["wins"] + s["losses"]
        if total > 0:
            wr = (s["wins"] / total) * 100
            print(f"- {strat}: {wr:.1f}%")

# ===============================
# MAIN LOOP (SIMULATION)
# ===============================

def on_new_candle(candles, rsi):
    prices = [c['close'] for c in candles]
    ema20 = ema(prices, EMA_PERIOD)

    detect_liquidity_dump(candles)

    if post_dump_reentry(candles, ema20):
        open_trade("ICT", "BUY", prices[-1])

    if not LIQUIDITY_DUMP_ACTIVE:
        if rsi <= RSI_BUY:
            open_trade("Scalping", "BUY", prices[-1])
        elif rsi >= RSI_SELL:
            open_trade("Scalping", "SELL", prices[-1])

    check_trades(prices[-1])

# ======================================
# END
# ======================================
# ===============================
# SIMPLE RUN LOOP (FIX)
# ===============================

import random

def mock_candles():
    base = 4600 + random.uniform(-5, 5)
    candles = []
    for _ in range(30):
        o = base + random.uniform(-3, 3)
        c = o + random.uniform(-5, 5)
        h = max(o, c) + random.uniform(0, 3)
        l = min(o, c) - random.uniform(0, 3)
        candles.append({
            "open": o,
            "high": h,
            "low": l,
            "close": c
        })
        base = c
    return candles

def mock_rsi():
    return random.randint(20, 80)

print("🤖 Bot started (simulation mode)")

while True:
    candles = mock_candles()
    rsi_val = mock_rsi()
    on_new_candle(candles, rsi_val)
    time.sleep(5)
