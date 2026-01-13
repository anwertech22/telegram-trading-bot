import os
import time
import csv
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
# Files & State
# =========================
TRADES_FILE = "trades.csv"
SUBSCRIBERS = set()
OPEN_TRADE = None  # {direction, entry, tp, sl, time}

# =========================
# Ensure CSV Exists
# =========================
if not os.path.exists(TRADES_FILE):
    with open(TRADES_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "pair", "direction", "entry", "tp", "sl", "result"])

# =========================
# Utils
# =========================
def save_trade(direction, entry, tp, sl, result):
    with open(TRADES_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
            "XAUUSD",
            direction,
            entry,
            tp,
            sl,
            result
        ])

def get_stats():
    total = wins = losses = 0
    with open(TRADES_FILE, "r") as f:
        reader = csv.DictReader(f)
        for r in reader:
            total += 1
            if r["result"] == "WIN":
                wins += 1
            if r["result"] == "LOSS":
                losses += 1
    winrate = round((wins / total) * 100, 2) if total else 0
    return total, wins, losses, winrate

# =========================
# Market Data
# =========================
def get_xauusd_price():
    r = requests.get(
        "https://metals-api.com/api/latest",
        params={"access_key": METALS_API_KEY, "base": "USD", "symbols": "XAU"},
        timeout=10
    )
    return round(1 / r.json()["rates"]["XAU"], 2)

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
# Strategy (RSI + EMA + ATR)
# =========================
def analyze_market():
    highs, lows, closes = get_ohlc()
    price = get_xauusd_price()

    rsi = calculate_rsi(closes)
    ema20 = calculate_ema(closes, 20)
    ema50 = calculate_ema(closes, 50)
    atr = calculate_atr(highs, lows, closes)

    if rsi >= 70 and price < ema20 and price < ema50:
        sl = round(price + atr * 1.5, 2)
        tp = round(price - atr * 2.5, 2)
        return ("SELL", price, tp, sl, rsi, ema20, ema50, atr)

    if rsi <= 30 and price > ema20 and price > ema50:
        sl = round(price - atr * 1.5, 2)
        tp = round(price + atr * 2.5, 2)
        return ("BUY", price, tp, sl, rsi, ema20, ema50, atr)

    return None

# =========================
# Open Trade
# =========================
def open_trade(signal):
    global OPEN_TRADE
    direction, entry, tp, sl, rsi, ema20, ema50, atr = signal
    OPEN_TRADE = {
        "direction": direction,
        "entry": entry,
        "tp": tp,
        "sl": sl,
        "time": datetime.utcnow()
    }
    for cid in SUBSCRIBERS:
        bot.send_message(
            cid,
            f"""
📊 XAUUSD – M5
{'🔴 SELL' if direction=='SELL' else '🟢 BUY'} @ {entry}

RSI: {rsi}
EMA20: {ema20}
EMA50: {ema50}
ATR: {atr}

🎯 TP: {tp}
❌ SL: {sl}
"""
        )

# =========================
# Monitor Open Trade (TP/SL)
# =========================
def trade_monitor_loop():
    global OPEN_TRADE
    while True:
        try:
            if OPEN_TRADE:
                price = get_xauusd_price()
                d = OPEN_TRADE["direction"]
                tp = OPEN_TRADE["tp"]
                sl = OPEN_TRADE["sl"]
                entry = OPEN_TRADE["entry"]

                if d == "BUY" and price >= tp:
                    save_trade("BUY", entry, tp, sl, "WIN")
                    for cid in SUBSCRIBERS:
                        bot.send_message(cid, f"✅ TP HIT @ {price} — WIN")
                    OPEN_TRADE = None

                elif d == "BUY" and price <= sl:
                    save_trade("BUY", entry, tp, sl, "LOSS")
                    for cid in SUBSCRIBERS:
                        bot.send_message(cid, f"❌ SL HIT @ {price} — LOSS")
                    OPEN_TRADE = None

                elif d == "SELL" and price <= tp:
                    save_trade("SELL", entry, tp, sl, "WIN")
                    for cid in SUBSCRIBERS:
                        bot.send_message(cid, f"✅ TP HIT @ {price} — WIN")
                    OPEN_TRADE = None

                elif d == "SELL" and price >= sl:
                    save_trade("SELL", entry, tp, sl, "LOSS")
                    for cid in SUBSCRIBERS:
                        bot.send_message(cid, f"❌ SL HIT @ {price} — LOSS")
                    OPEN_TRADE = None

        except Exception:
            pass

        time.sleep(60)  # فحص كل دقيقة

# =========================
# Auto Signal Loop (كل 5 دقائق)
# =========================
def auto_signal_loop():
    while True:
        try:
            if OPEN_TRADE is None:
                signal = analyze_market()
                if signal:
                    open_trade(signal)
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
        "🤖 البوت يعمل\n"
        "📈 إشارات تلقائية\n"
        "🎯 إغلاق تلقائي عند TP/SL\n"
        "/stats ➜ إحصائيات الأداء"
    )

@bot.message_handler(commands=["stats"])
def stats(message):
    total, wins, losses, winrate = get_stats()
    bot.send_message(
        message.chat.id,
        f"""
📊 إحصائيات XAUUSD

Total Trades: {total}
Wins: {wins}
Losses: {losses}
Win Rate: {winrate}%
"""
    )

# =========================
# Run
# =========================
Thread(target=trade_monitor_loop).start()
Thread(target=auto_signal_loop).start()
print("🤖 Bot running with AUTO TP/SL closing")
bot.polling(none_stop=True)
