import os
import requests
import telebot

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
# Get OHLC (Closes) - TwelveData
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
    closes.reverse()  # الأقدم → الأحدث
    return closes

# =========================
# Indicators
# =========================
def calculate_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
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
    if len(closes) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for price in closes[period:]:
        ema = price * k + ema * (1 - k)
    return round(ema, 2)

# =========================
# Commands
# =========================
@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        "🤖 بوت XAUUSD يعمل 24/7\n\n"
        "الأوامر:\n"
        "/signal ➜ إشارة RSI + EMA20/50 على M5"
    )

@bot.message_handler(commands=["signal"])
def signal(message):
    try:
        price = get_xauusd_price()
        closes = get_closes()

        rsi = calculate_rsi(closes, 14)
        ema20 = calculate_ema(closes, 20)
        ema50 = calculate_ema(closes, 50)

        if None in (rsi, ema20, ema50):
            bot.send_message(message.chat.id, "⚠️ بيانات غير كافية")
            return

        # منطق القرار
        if rsi >= 70 and price < ema20 and price < ema50:
            direction = "🔴 SELL"
            tp = round(price - 10, 2)
            sl = round(price + 12, 2)
            conf = 78
        elif rsi <= 30 and price > ema20 and price > ema50:
            direction = "🟢 BUY"
            tp = round(price + 10, 2)
            sl = round(price - 12, 2)
            conf = 78
        else:
            bot.send_message(
                message.chat.id,
                f"""
📊 XAUUSD – M5
⏸️ NO TRADE

RSI(14): {rsi}
EMA20: {ema20}
EMA50: {ema50}

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
EMA20: {ema20}
EMA50: {ema50}

🎯 TP: {tp}
❌ SL: {sl}
Confidence: {conf}%
"""
        )

    except Exception:
        bot.send_message(message.chat.id, "⚠️ حدث خطأ، حاول لاحقًا")

# =========================
# Run
# =========================
print("🤖 Bot running with RSI + EMA20/50")
bot.polling(none_stop=True)
