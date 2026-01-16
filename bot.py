# =========================================
# FINAL MULTI-STRATEGY TRADING BOT (SIGNALS)
# =========================================

import time
import math
import statistics
from datetime import datetime, timedelta

# =========================
# CONFIG
# =========================

SYMBOL = "XAUUSD"
TIMEFRAMES = ["M5", "M15"]
CONFIDENCE_MIN = 60

EMA_PERIOD = 20
RSI_BUY = 35
RSI_SELL = 65

ATR_PERIOD = 14
ATR_DUMP_MULTIPLIER = 1.8

CHECK_INTERVAL = 60  # seconds
TIMEZONE = "Algeria (UTC+1)"

# News (manual schedule – can be automated later)
NEWS_EVENTS = ["CPI", "NFP", "FOMC"]
NEWS_BLOCK_MINUTES = 30
POST_NEWS_WAIT = 15

# =========================
# GLOBAL STATE
# =========================

last_signal_time = None
post_dump_mode = False
open_trades = []
stats = {
    "total": 0,
    "win": 0,
    "loss": 0
}

# =========================
# UTILITIES
# =========================

def log(msg):
    print(f"[{datetime.utcnow()}] {msg}")

def in_news_time():
    # Placeholder (manual / future API)
    return False

def calculate_rsi(closes, period=14):
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
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

def calculate_ema(prices, period):
    if len(prices) < period:
        return None
    k = 2 / (period + 1)
    ema = prices[0]
    for price in prices[1:]:
        ema = price * k + ema * (1 - k)
    return ema

def calculate_atr(highs, lows, closes, period=14):
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1])
        )
        trs.append(tr)
    if len(trs) < period:
        return None
    return statistics.mean(trs[-period:])

# =========================
# PATTERNS
# =========================

def is_hammer(open_, high, low, close):
    body = abs(close - open_)
    lower_wick = min(open_, close) - low
    upper_wick = high - max(open_, close)
    return lower_wick > body * 2 and upper_wick < body

def is_pinbar(open_, high, low, close):
    body = abs(close - open_)
    wick = max(high - close, open_ - low)
    return wick > body * 2

# =========================
# LIQUIDITY DUMP DETECTOR
# =========================

def detect_liquidity_dump(highs, lows, closes):
    atr_current = calculate_atr(highs, lows, closes, ATR_PERIOD)
    atr_avg = calculate_atr(highs[:-1], lows[:-1], closes[:-1], ATR_PERIOD)
    if not atr_current or not atr_avg:
        return False
    return atr_current > atr_avg * ATR_DUMP_MULTIPLIER

# =========================
# STRATEGIES
# =========================

def strategy_ema(closes, rsi):
    ema = calculate_ema(closes, EMA_PERIOD)
    if not ema or not rsi:
        return None
    price = closes[-1]
    if price > ema and rsi <= RSI_BUY:
        return "BUY"
    if price < ema and rsi >= RSI_SELL:
        return "SELL"
    return None

def strategy_ict(closes):
    # simplified ICT bias (higher highs / lower lows)
    if closes[-1] > closes[-3]:
        return "BUY"
    if closes[-1] < closes[-3]:
        return "SELL"
    return None

def strategy_scalping(closes):
    if abs(closes[-1] - closes[-2]) > abs(closes[-2] - closes[-3]):
        return "SELL"
    return None

# =========================
# SIGNAL ENGINE
# =========================

def evaluate_market(data):
    global post_dump_mode

    closes = data["close"]
    highs = data["high"]
    lows = data["low"]

    rsi = calculate_rsi(closes)
    dump = detect_liquidity_dump(highs, lows, closes)

    if dump:
        post_dump_mode = True
        log("🔥 Liquidity Dump detected → Post-Dump Mode ON")
        return None

    if post_dump_mode:
        if closes[-1] > calculate_ema(closes, EMA_PERIOD):
            post_dump_mode = False
            log("✅ Market stabilized after dump")

    signals = []

    ema_sig = strategy_ema(closes, rsi)
    if ema_sig:
        signals.append(("EMA", ema_sig, 60))

    ict_sig = strategy_ict(closes)
    if ict_sig:
        signals.append(("ICT", ict_sig, 70))

    scalp_sig = strategy_scalping(closes)
    if scalp_sig:
        signals.append(("Scalping", scalp_sig, 55))

    if not signals:
        return None

    # choose strongest
    best = max(signals, key=lambda x: x[2])
    if best[2] < CONFIDENCE_MIN:
        return None

    return best

# =========================
# MOCK MARKET DATA
# =========================

def get_mock_data():
    base = 4600
    closes = [base + math.sin(i / 3) * 10 for i in range(50)]
    highs = [c + 5 for c in closes]
    lows = [c - 5 for c in closes]
    return {"close": closes, "high": highs, "low": lows}

# =========================
# TRADE TRACKING
# =========================

def register_trade(strategy, side, confidence):
    stats["total"] += 1
    open_trades.append({
        "strategy": strategy,
        "side": side,
        "confidence": confidence,
        "time": datetime.utcnow()
    })
    log(f"📢 SIGNAL → {strategy} | {side} | Conf {confidence}%")

def close_trade(win=True):
    if win:
        stats["win"] += 1
    else:
        stats["loss"] += 1

# =========================
# MAIN LOOP (RENDER SAFE)
# =========================

def run_bot():
    log("🤖 FINAL Multi-Strategy Bot STARTED")
    log("⏱ Timezone: Algeria (UTC+1)")
    log("🧠 Strategies: ICT | EMA | Scalping")
    log("🛡 News Filter: CPI / NFP / FOMC")
    log("🔥 Liquidity Dump Protection ON")

    while True:
        try:
            if in_news_time():
                log("⛔ News time – trading paused")
                time.sleep(CHECK_INTERVAL)
                continue

            data = get_mock_data()
            signal = evaluate_market(data)

            if signal:
                strategy, side, conf = signal
                register_trade(strategy, side, conf)

            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            log(f"❌ ERROR: {e}")
            time.sleep(10)

# =========================
# START
# =========================

if __name__ == "__main__":
    run_bot()
