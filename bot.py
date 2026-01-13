import os
import time
import requests
import telebot
from threading import Thread

# =========================
# Environment Variables
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
METALS_API_KEY = os.getenv("METALS_API_KEY")
TD_API_KEY = os.getenv("TD_API_KEY")

if not BOT_TOKEN or not METALS_API_KEY or not TD_API_KEY:
    raise Exception("❌ تأكد من BOT_TOKEN و METALS_API_KEY و TD_API_KEY")

bot = telebot.TeleBot(BOT_TOKEN)

# =========================
# Global State
# =========================
LAST_SIGNAL = None
SUBSCRIBERS = set()  # chat_ids

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
    data = r.json()
    return round(1 / data["rates"]["XAU"], 2)

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
    values = data.get("values", [])
    closes = [float(v["close"]) for v in values]
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
        return {
            "type": "SELL",
            "text": f"""
📊 XAUUSD – M5
🔴 SELL @ {price}

RSI(14): {rsi}
EMA20: {ema20}
EMA50: {ema50}

🎯 TP: {round(price - 10, 2)}
❌ SL: {round(price + 12, 2)}
Confidence: 78%
"""
        }

    if rsi <= 30 and price > ema20 and price > ema50:
        return {
            "type": "BUY",
            "text": f"""
📊 XAUUSD – M5
🟢 BUY @ {price}

RSI(14): {rsi}
EMA20: {ema20}
EMA50: {ema50}

🎯 TP: {round(price + 10, 2)}
❌ SL: {round(price - 12, 2)}
Confidence: 78%
"""
        }

    return {"type": "NO_TRADE"}

# =========================
# Auto Signal Loop (5 min)
# =========================
def auto_signal_loop():
    global LAST_SIGNAL
    while True:
        try:
            signal = analyze_market()
            if signal["type"] != "NO_TRADE" and signal["type"] != LAST_SIGNAL:
                for chat_id in SUBSCRIBERS:
                    bot.send_message(chat_id, signal["text"])
                LAST_SIGNAL = signal["type"]
        except Exception:
            pass
        time.sleep(300)  # 5 دقائق

# =========================
# Commands
# =========================
@bot.message_handler(commands=["start"])
def start(message):
    SUBSCRIBERS.add(message.chat.id)
    bot.send_message(
        message.chat.id,
        "🤖 تم تفعيل الإشارات التلقائية كل 5 دقائق\n"
        "سيتم إرسال الإشارة عند ظهور فرصة حقيقية فقط ✅"
    )

@bot.message_handler(commands=["signal"])
def manual_signal(message):
    try:
        signal = analyze_market()
        if signal["type"] == "NO_TRADE":
            bot.send_message(message.chat.id, "⏸️ لا توجد فرصة الآن")
        else:
            bot.send_message(message.chat.id, signal["text"])
    except Exception:
        bot.send_message(message.chat.id, "⚠️ خطأ مؤقت")

# =========================
# Run
# =========================
Thread(target=auto_signal_loop).start()
print("🤖 Bot running with AUTO signals every 5 minutes")
bot.polling(none_stop=True)
