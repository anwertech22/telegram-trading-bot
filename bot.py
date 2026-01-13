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

bot = telebot.TeleBot(BOT_TOKEN)

TRADES_FILE = "trades.csv"

# =========================
# Ensure CSV Exists
# =========================
if not os.path.exists(TRADES_FILE):
    with open(TRADES_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "pair", "direction", "entry", "tp", "sl", "result"])

# =========================
# Save Trade
# =========================
def save_trade(direction, entry, tp, sl, result="OPEN"):
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

# =========================
# Get Stats
# =========================
def get_stats():
    trades = []
    with open(TRADES_FILE, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            trades.append(row)

    total = len(trades)
    wins = sum(1 for t in trades if t["result"] == "WIN")
    losses = sum(1 for t in trades if t["result"] == "LOSS")

    winrate = round((wins / total) * 100, 2) if total > 0 else 0

    return total, wins, losses, winrate

# =========================
# Example Trade Execution
# =========================
def execute_trade(direction, price, atr):
    sl = round(price + atr * 1.5, 2) if direction == "SELL" else round(price - atr * 1.5, 2)
    tp = round(price - atr * 2.5, 2) if direction == "SELL" else round(price + atr * 2.5, 2)

    # 🔴 مؤقتًا: نحاكي النتيجة (لاحقًا نراقب السعر الحقيقي)
    result = "WIN" if atr % 2 == 0 else "LOSS"

    save_trade(direction, price, tp, sl, result)
    return tp, sl, result

# =========================
# Commands
# =========================
@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        "🤖 البوت يعمل\n"
        "/stats ➜ عرض إحصائيات الأداء"
    )

@bot.message_handler(commands=["stats"])
def stats(message):
    total, wins, losses, winrate = get_stats()
    bot.send_message(
        message.chat.id,
        f"""
📊 إحصائيات الأداء – XAUUSD

عدد الصفقات: {total}
الصفقات الرابحة: {wins}
الصفقات الخاسرة: {losses}
Win Rate: {winrate}%
"""
    )

# =========================
# Run
# =========================
print("🤖 Bot running with TRADE STATS")
bot.polling(none_stop=True)
