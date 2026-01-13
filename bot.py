import os
import time
import requests
import telebot

# =========================
# Environment Variables
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
METALS_API_KEY = os.getenv("METALS_API_KEY")

if not BOT_TOKEN or not METALS_API_KEY:
    raise Exception("❌ BOT_TOKEN أو METALS_API_KEY غير موجود")

bot = telebot.TeleBot(BOT_TOKEN)

# =========================
# Get XAUUSD Price (LIVE)
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

    if "rates" not in data or "XAU" not in data["rates"]:
        raise Exception("❌ خطأ في جلب سعر الذهب")

    # السعر المعطى هو XAU مقابل USD (معكوس)
    xau_rate = data["rates"]["XAU"]
    price = 1 / xau_rate  # تحويله إلى XAUUSD
    return round(price, 2)

# =========================
# Commands
# =========================
@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        "🤖 بوت XAUUSD يعمل 24/7\n\n"
        "الأوامر المتاحة:\n"
        "/signal ➜ إشارة تداول على الذهب"
    )

@bot.message_handler(commands=["signal"])
def signal(message):
    try:
        price = get_xauusd_price()

        # منطق بسيط مؤقت (سيُطوّر لاحقًا)
        sell = True  # مؤقتًا SELL فقط

        if sell:
            entry = price
            tp = round(price - 10, 2)
            sl = round(price + 12, 2)
            direction = "🔴 SELL"
        else:
            entry = price
            tp = round(price + 10, 2)
            sl = round(price - 12, 2)
            direction = "🟢 BUY"

        bot.send_message(
            message.chat.id,
            f"""
📊 XAUUSD – M5
{direction} @ {entry}

🎯 TP: {tp}
❌ SL: {sl}

Confidence: 70%
"""
        )

    except Exception as e:
        bot.send_message(
            message.chat.id,
            "⚠️ تعذّر جلب السعر الآن، حاول بعد قليل"
        )

# =========================
# Run Bot
# =========================
print("🤖 Bot is running...")
bot.polling(none_stop=True)
