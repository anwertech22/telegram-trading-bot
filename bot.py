import os
import telebot

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id,
        "🤖 البوت يعمل 24/7!\nاكتب /signal للحصول على إشارة."
    )

@bot.message_handler(commands=['signal'])
def signal(message):
    price = 4583
    bot.send_message(
        message.chat.id,
        f"""
📊 XAUUSD – M5
🔴 SELL @ {price}
🎯 TP: {price - 10}
❌ SL: {price + 12}
Confidence: 68%
"""
    )

bot.polling()
