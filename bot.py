# ======================================
# FINAL REALISTIC TRADING BOT ENGINE
# WITH TRUE STATS + ATR SL/TP
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
ATR_PERIOD = 14

SL_ATR_MULT = 0.8
TP_ATR_MULT = 1.6

BASE_CONFIDENCE = 60
POST_DUMP_BOOST = 15

BODY_MULTIPLIER = 1.5
ATR_DUMP_MULT = 1.8

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

LIQUIDITY_DUMP = False
POST_DUMP_MODE = False

# ===============================
# INDICATORS
# ===============================

def ema(values, period):
    k = 2 / (period + 1)
    out = []
    for i, v in enumerate(values):
        out.append(v if i == 0 else v * k + out[-1] * (1 - k))
    return out

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
        return None
    return sum(trs[-period:]) / period

# ===============================
# CANDLE PATTERNS
# ===============================

def is_hammer(c):
    body = abs(c["close"] - c["open"])
    lower_wick = min(c["open"], c["close"]) - c["low"]
    return lower_wick > body * 2

def is_pinbar(c):
    body = abs(c["close"] - c["open"])
    full = c["high"] - c["low"]
    return body < full * 0.3

# ===============================
# LIQUIDITY DUMP
# ===============================

def detect_liquidity_dump(candles):
    global LIQUIDITY_DUMP, POST_DUMP_MODE

    if len(candles) < 20:
        return

    bodies = [abs(c["close"] - c["open"]) for c in candles[-6:-1]]
    avg_body = sum(bodies) / len(bodies)

    last = candles[-1]
    body = abs(last["close"] - last["open"])

    atr_now = atr(candles)
    atr_prev = atr(candles[:-1])

    if atr_now and atr_prev:
        if body > avg_body * BODY_MULTIPLIER and atr_now > atr_prev * ATR_DUMP_MULT:
            LIQUIDITY_DUMP = True
            POST_DUMP_MODE = True
            print("🧨 LIQUIDITY DUMP DETECTED")

# ===============================
# TRADE ENGINE
# ===============================

def open_trade(strategy, direction, price, atr_value):
    sl = price - atr_value * SL_ATR_MULT if direction == "BUY" else price + atr_value * SL_ATR_MULT
    tp = price + atr_value * TP_ATR_MULT if direction == "BUY" else price - atr_value * TP_ATR_MULT

    trade = {
        "strategy": strategy,
        "direction": direction,
        "entry": price,
        "sl": sl,
        "tp": tp,
        "time": datetime.now(),
        "open": True
    }

    open_trades.append(trade)

    print(f"📥 OPEN {strategy} {direction}")
    print(f"Entry: {price} | SL: {sl:.2f} | TP: {tp:.2f}")

def update_trades(candle):
    price_high = candle["high"]
    price_low = candle["low"]

    for trade in open_trades[:]:
        if not trade["open"]:
            continue

        hit_tp = (
            trade["direction"] == "BUY" and price_high >= trade["tp"] or
            trade["direction"] == "SELL" and price_low <= trade["tp"]
        )

        hit_sl = (
            trade["direction"] == "BUY" and price_low <= trade["sl"] or
            trade["direction"] == "SELL" and price_high >= trade["sl"]
        )

        if hit_tp or hit_sl:
            trade["open"] = False
            stats["total"] += 1

            if hit_tp:
                stats["wins"] += 1
                stats["by_strategy"][trade["strategy"]]["wins"] += 1
                print(f"✅ WIN | {trade['strategy']}")
            else:
                stats["losses"] += 1
                stats["by_strategy"][trade["strategy"]]["losses"] += 1
                print(f"❌ LOSS | {trade['strategy']}")

            open_trades.remove(trade)

# ===============================
# MAIN LOGIC
# ===============================

def on_new_candle(candles, rsi_value):
    global LIQUIDITY_DUMP, POST_DUMP_MODE

    prices = [c["close"] for c in candles]
    ema20 = ema(prices, EMA_PERIOD)
    atr_value = atr(candles)

    if not atr_value:
        return

    detect_liquidity_dump(candles)

    last = candles[-1]

    # POST DUMP RE-ENTRY
    if POST_DUMP_MODE:
        if (is_hammer(last) or is_pinbar(last)) and last["close"] > ema20[-1]:
            open_trade("ICT", "BUY", last["close"], atr_value)
            POST_DUMP_MODE = False
            LIQUIDITY_DUMP = False
            return

    # NORMAL SCALPING (ONLY IF SAFE)
    if not LIQUIDITY_DUMP:
        if rsi_value <= RSI_BUY:
            open_trade("Scalping", "BUY", last["close"], atr_value)
        elif rsi_value >= RSI_SELL:
            open_trade("Scalping", "SELL", last["close"], atr_value)

    update_trades(last)

# ===============================
# STATS
# ===============================

def print_stats():
    if stats["total"] == 0:
        print("📊 No trades yet")
        return

    winrate = stats["wins"] / stats["total"] * 100

    print("\n📊 PERFORMANCE")
    print(f"Total Trades: {stats['total']}")
    print(f"Wins: {stats['wins']}")
    print(f"Losses: {stats['losses']}")
    print(f"Winrate: {winrate:.2f}%")

    for s, v in stats["by_strategy"].items():
        t = v["wins"] + v["losses"]
        if t > 0:
            print(f"- {s}: {v['wins']/t*100:.1f}%")

# ======================================
# END OF FILE
# ======================================
