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
    raise Exception("❌ تأكد من جميع Environment Variables")

bot = telebot.TeleBot(BOT_TOKEN)

# =========================
# Global State
# =========================
LAST_SIGNAL = None
SUBSCRIBERS = set()
NEWS_ALERT_SENT = False

# =========================
# News Time Filter (UTC)
# =========================
def is_news_time():
    now = datetime.utcnow().time()

    # أخبار قوية + افتتاح نيويورك
    blocked_times = [
        ("12:15", "13:45"),
        ("13:20", "14:00"),
    ]

    for start, end in blocked_times:
        start_t = datetime.strptime(start, "%H:%M").time()
        end_t = datetime.strptime(end, "%H:%M").time()
        if start_t <= now <= end_t:
            return True

    return False

# =========================
# Price - Metals API
# =========================
def get_xauusd_price():
    url = "https://metals-api.com/api/latest"
    params = {
        "access_key": METALS_API_KEY,
        "base": "USD",
        "symbols": "XAU"
    }
    r = requests.get(url, params=params, timeout=10)
    return round(1 / r.json()["rates"]["XAU"], 2)

# =========================
# Closes - TwelveData
# =========================
def get_closes(limit=120):
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": "XAU/USD",
        "interval": "5min",
        "outputsize": limit,
        "apikey": TD_API_KEY
    }
    r = requests.get(url, params=params, timeout=10)
    data = r.json()
    closes = [float(v["close"]) for v in data["values"]]
    closes.reverse()
    return closes

# =========================
# Indicators
# =========================
def calculate_rsi(closes, period=14):
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = closes[-i] - closes[-i - 1]
        if diff >= 0:
            gains.append(diff)
        else:
            losses.append(abs(diff))
    avg_gain = sum(gains) / period
    avg_loss = (sum(losses) / period) if losses else 0.0001
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def calculate_ema(closes, period):
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for price in closes[period:]:
        ema = price * k + ema * (1 - k)
    return round(ema, 2)

# =========================
# Signal Logic
# =========================
def analyze_market():
    price = get_xauusd_price()
    closes = get_closes()

    rsi = calculate_rsi(closes)
    ema20 = calculate_ema(closes, 20)
    ema50 = calculate_ema(closes, 50)

    if rsi >= 70 and price < ema20 and price < ema50:
        return ("SELL", f"""
📊 XAUUSD – M5
🔴 SELL @ {price}

RSI: {rsi}
EMA20: {ema20}
EMA50: {ema50}

🎯 TP: {price - 10}
❌ SL: {price + 12}
Confidence: 78%
""")

    if rsi <= 30 and price > ema20 and price > ema50:
        return ("BUY", f"""
📊 XAUUSD – M5
🟢 BUY @ {price}

RSI: {rsi}
EMA20: {ema20}
EMA50: {ema50}

🎯 TP: {price + 10}
❌ SL: {price - 12}
Confidence: 78%
""")

    return ("NO_TRADE", None)

# =========================
# Auto Loop
# =========================
def auto_signal_loop():
    global LAST_SIGNAL, NEWS_ALERT_SENT

    while True:
        try:
            if is_news_time():
                if not NEWS_ALERT_SENT:
                    for chat_id in SUBSCRIBERS:
                        bot.send_message(
                            chat_id,
                            "⛔ التداول متوقف مؤقتًا بسبب أخبار قوية\n⏳ ننتظر هدوء السوق"
                        )
                    NEWS_ALERT_SENT = True
                time.sleep(300)
                continue
            else:
                NEWS_ALERT_SENT = False

            signal, text = analyze_market()
            if signal not in ("NO_TRADE", LAST_SIGNAL):
                for chat_id in SUBSCRIBERS:
                    bot.send_message(chat_id, text)
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
        "🤖 تم تفعيل الإشارات التلقائية\n"
        "📰 فلترة الأخبار مفعّلة\n"
        "⏱️ فحص كل 5 دقائق"
    )

# =========================
# Run
# =========================
Thread(target=auto_signal_loop).start()
print("🤖 Bot running with NEWS FILTER")
bot.polling(none_stop=True)
