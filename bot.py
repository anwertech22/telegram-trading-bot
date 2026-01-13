import os
import requests
import telebot
import math

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
# Get XAUUSD Price (LIVE) - Metals API
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
    xau_rate = data["rates"]["XAU"]
    return round(1 / xau_rate, 2)

# =========================
# Get OHLC for RSI - TwelveData
# =========================
def get_closes_for_rsi(limit=50):
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
    closes.reverse()  # الأقدم → الأحدث
    return closes

# =========================
# RSI Calculation
# =========================
def calculate_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None

    gains, losses = [], []
    for i in range(1, period + 1):
        change = closes[-i] - closes[-i - 1]
        if change >= 0:
            gains.append(change)
        else:
            losses.append(abs(change))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period if losses else 0.0001

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 2)

# =========================
# Commands
# =========================
@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        "🤖 بوت XAUUSD يعمل 24/7\n\n"
        "الأوامر:\n"
        "/signal ➜ إشارة RSI على M5"
    )

@bot.message_handler(commands=["signal"])
def signal(message):
    try:
        price = get_xauusd_price()
        closes = get_closes_for_rsi()
        rsi = calculate_rsi(closes)

        if rsi is None:
            bot.send_message(message.chat.id, "⚠️ بيانات غير كافية لحساب RSI")
            return

        # قرار التداول
        if rsi >= 70:
            direction = "🔴 SELL"
            tp = round(price - 10, 2)
            sl = round(price + 12, 2)
            conf = 72
        elif rsi <= 30:
            direction = "🟢 BUY"
            tp = round(price + 10, 2)
            sl = round(price - 12, 2)
            conf = 72
        else:
            bot.send_message(
                message.chat.id,
                f"""
📊 XAUUSD – M5
⏸️ NO TRADE

RSI(14): {rsi}
السوق محايد — ننتظر
"""
            )
            return

        bot.send_message(
            message.chat.id,
            f"""
📊 XAUUSD – M5
{direction} @ {price}

RSI(14): {rsi}

🎯 TP: {tp}
❌ SL: {sl}
Confidence: {conf}%
"""
        )

    except Exception:
        bot.send_message(message.chat.id, "⚠️ حدث خطأ، حاول لاحقًا")

# =========================
# Run Bot
# =========================
print("🤖 Bot is running with RSI...")
bot.polling(none_stop=True)
