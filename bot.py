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
# Signal Logic
# =========================
def analyze_market():
    price = get_xauusd_price()
    highs, lows, closes = get_ohlc()

    rsi = calculate_rsi(closes)
    ema20 = calculate_ema(closes, 20)
    ema50 = calculate_ema(closes, 50)
    atr = calculate_atr(highs, lows, closes)

    sl_dist = round(atr * 1.5, 2)
    tp_dist = round(atr * 2.5, 2)

    if rsi >= 70 and price < ema20 and price < ema50:
        return ("SELL", f"""
📊 XAUUSD – M5
🔴 SELL @ {price}

RSI: {rsi}
EMA20: {ema20}
EMA50: {ema50}
ATR(14): {atr}

🎯 TP: {round(price - tp_dist, 2)}
❌ SL: {round(price + sl_dist, 2)}
RR ≈ 1 : 1.6
""")

    if rsi <= 30 and price > ema20 and price > ema50:
        return ("BUY", f"""
📊 XAUUSD – M5
🟢 BUY @ {price}

RSI: {rsi}
EMA20: {ema20}
EMA50: {ema50}
ATR(14): {atr}

🎯 TP: {round(price + tp_dist, 2)}
❌ SL: {round(price - sl_dist, 2)}
RR ≈ 1 : 1.6
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
        "📉 RSI + EMA + ATR\n"
        "📰 فلترة أخبار\n"
        "⏱️ كل 5 دقائق"
    )

# =========================
# Run
# =========================
Thread(target=auto_loop).start()
print("🤖 Bot running with ATR-based TP/SL")
bot.polling(none_stop=True)
