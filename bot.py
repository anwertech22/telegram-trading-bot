import time, os, requests
from datetime import datetime, timedelta
from threading import Thread
import telebot

# =========================
# BASIC CONFIG
# =========================
PAIR = "XAU/USD"
TF_ICT = "15min"
TF_EMA = "5min"

CHECK_EVERY = 60  # seconds
CONF_MIN = 60
CANDLE_CONFIRM_CONF = 70

RSI_BUY = 35
RSI_SELL = 65

EMA_FAST = 20
EMA_TREND = 50

# TP / SL ATR Multipliers
TP_ICT = 1.5
SL_ICT = 1.0
TP_EMA = 0.7
SL_EMA = 0.9
TP_SCALP = 0.4
SL_SCALP = 0.6

# =========================
# NEWS (ALGERIA TIME UTC+1)
# =========================
NEWS_EVENTS = {
    "CPI": "14:30",
    "NFP": "14:30",
    "FOMC": "20:00"
}
NEWS_BLOCK_MIN = 45

# =========================
# ENV
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
TD_API_KEY = os.getenv("TD_API_KEY")
bot = telebot.TeleBot(BOT_TOKEN)
SUBSCRIBERS = set()

# =========================
# STATE
# =========================
open_trades = []  # list of dicts
last_bias = None

# =========================
# TIME HELPERS
# =========================
def dz_now():
    return datetime.utcnow() + timedelta(hours=1)

def in_killzone():
    h = dz_now().hour
    return (9 <= h <= 12) or (14 <= h <= 17)

def news_blocked():
    now = dz_now()
    for t in NEWS_EVENTS.values():
        hh, mm = map(int, t.split(":"))
        news_time = now.replace(hour=hh, minute=mm, second=0)
        if abs((news_time - now).total_seconds()) <= NEWS_BLOCK_MIN * 60:
            return True
    return False

# =========================
# MARKET DATA
# =========================
def get_candles(tf, limit=200):
    r = requests.get("https://api.twelvedata.com/time_series", params={
        "symbol": PAIR,
        "interval": tf,
        "outputsize": limit,
        "apikey": TD_API_KEY
    })
    data = r.json().get("values", [])
    data.reverse()
    return data

def ema(values, period):
    k = 2 / (period + 1)
    e = sum(values[:period]) / period
    for v in values[period:]:
        e = v * k + e * (1 - k)
    return e

def rsi(values, period=14):
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = values[-i] - values[-i - 1]
        if diff >= 0:
            gains.append(diff)
        else:
            losses.append(abs(diff))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period if losses else 0.0001
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def atr(h, l, c, p=14):
    tr = []
    for i in range(1, p + 1):
        tr.append(max(
            h[-i] - l[-i],
            abs(h[-i] - c[-i - 1]),
            abs(l[-i] - c[-i - 1])
        ))
    return sum(tr) / p

# =========================
# CANDLE FILTER
# =========================
def bullish_candle(c):
    body = abs(c[-1] - c[-2])
    wick = (c[-2] - min(c[-1], c[-2]))
    return wick > body * 1.5

def bearish_candle(c):
    body = abs(c[-1] - c[-2])
    wick = (max(c[-1], c[-2]) - c[-1])
    return wick > body * 1.5

# =========================
# TREND FILTER (M15 EMA50)
# =========================
def trend_bias():
    cs = get_candles(TF_ICT)
    closes = [float(x["close"]) for x in cs]
    price = closes[-1]
    e50 = ema(closes, EMA_TREND)
    if price > e50:
        return "BUY"
    if price < e50:
        return "SELL"
    return None

# =========================
# STRATEGY ENGINE
# =========================
def try_strategy(tf, label, tp_mult, sl_mult, need_rsi=False):
    global last_bias

    cs = get_candles(tf)
    c = [float(x["close"]) for x in cs]
    h = [float(x["high"]) for x in cs]
    l = [float(x["low"]) for x in cs]

    price = c[-1]
    a = atr(h, l, c)
    e20 = ema(c, EMA_FAST)
    r = rsi(c)

    bias = trend_bias()
    if not bias:
        return

    if last_bias and bias != last_bias:
        return

    conf = 60
    direction = None

    if bias == "BUY" and price > e20:
        direction = "BUY"
    if bias == "SELL" and price < e20:
        direction = "SELL"

    if not direction:
        return

    if need_rsi:
        if direction == "BUY" and r > RSI_BUY:
            return
        if direction == "SELL" and r < RSI_SELL:
            return

    if conf < CANDLE_CONFIRM_CONF:
        if direction == "BUY" and not bullish_candle(c):
            return
        if direction == "SELL" and not bearish_candle(c):
            return

    tp = price + a * tp_mult if direction == "BUY" else price - a * tp_mult
    sl = price - a * sl_mult if direction == "BUY" else price + a * sl_mult

    open_trades.append({
        "label": label,
        "direction": direction,
        "entry": price,
        "tp": tp,
        "sl": sl,
        "time": dz_now()
    })

    last_bias = direction

    for u in SUBSCRIBERS:
        bot.send_message(u,
f"""{label}
XAUUSD {direction}
Entry: {price:.2f}
TP: {tp:.2f}
SL: {sl:.2f}
🧠 Confidence: {conf}%""")

# =========================
# TRADE TRACKER
# =========================
def monitor_trades():
    while True:
        price = float(get_candles(TF_EMA, 1)[-1]["close"])
        for trade in open_trades[:]:
            if trade["direction"] == "BUY":
                if price >= trade["tp"]:
                    result = "✅ الصفقة أغلقت ربح"
                elif price <= trade["sl"]:
                    result = "❌ الصفقة أغلقت خسارة"
                else:
                    continue
            else:
                if price <= trade["tp"]:
                    result = "✅ الصفقة أغلقت ربح"
                elif price >= trade["sl"]:
                    result = "❌ الصفقة أغلقت خسارة"
                else:
                    continue

            duration = int((dz_now() - trade["time"]).total_seconds() / 60)
            for u in SUBSCRIBERS:
                bot.send_message(u,
f"""{result}
{trade['label']}
⏱️ مدة الصفقة: {duration} دقيقة""")

            open_trades.remove(trade)

        time.sleep(30)

# =========================
# MAIN LOOP
# =========================
def loop():
    while True:
        if news_blocked() or not in_killzone():
            time.sleep(CHECK_EVERY)
            continue

        try_strategy(TF_ICT, "🟢 صفقة قوية (ICT)", TP_ICT, SL_ICT)
        try_strategy(TF_EMA, "🟡 صفقة متوسطة (EMA)", TP_EMA, SL_EMA)
        try_strategy(TF_EMA, "🔴 مخاطرة عالية (Scalp)", TP_SCALP, SL_SCALP, True)

        time.sleep(CHECK_EVERY)

@bot.message_handler(commands=["start"])
def start(m):
    SUBSCRIBERS.add(m.chat.id)
    bot.send_message(m.chat.id, "🤖 البوت النهائي يعمل الآن\nصفقات ذكية + تتبع كامل")

Thread(target=loop, daemon=True).start()
Thread(target=monitor_trades, daemon=True).start()
bot.infinity_polling()
