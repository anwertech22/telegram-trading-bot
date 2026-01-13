import os, time, requests, telebot
from datetime import datetime, timedelta
from threading import Thread

# =========================
# TIMEZONE (ALGERIA UTC+1)
# =========================
def dz_now():
    return datetime.utcnow() + timedelta(hours=1)

# =========================
# CONFIG
# =========================
PAIR = "XAU/USD"
LOT_SIZE = 0.02

ICT_INTERVAL = "15min"
FAST_INTERVAL = "5min"

CHECK_EVERY = 300  # 5 minutes

# === Risk & Confidence ===
MIN_CONF_ICT = 80
MIN_CONF_EMA = 80
MIN_CONF_SCALP = 80

NEAR_TRADE_MIN = 60
NEAR_TRADE_MAX = 79

TP_FAST_ATR = 0.6
SL_FAST_ATR = 0.8
TP_ICT_ATR = 1.8
SL_ICT_ATR = 1.2

DIRECTION_COOLDOWN = 60  # minutes

# =========================
# ENV
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
TD_API_KEY = os.getenv("TD_API_KEY")
if not BOT_TOKEN or not TD_API_KEY:
    raise Exception("Missing ENV variables")

bot = telebot.TeleBot(BOT_TOKEN)
SUBSCRIBERS = set()

# =========================
# STATE
# =========================
LAST_TRADE_DIR = None
LAST_TRADE_TIME = None
LAST_NEAR_ALERT = None

# =========================
# DATA
# =========================
def get_candles(interval, limit=200):
    r = requests.get(
        "https://api.twelvedata.com/time_series",
        params={
            "symbol": PAIR,
            "interval": interval,
            "outputsize": limit,
            "apikey": TD_API_KEY
        },
        timeout=10
    )
    data = r.json().get("values", [])
    data.reverse()
    return data

def ema(vals, p):
    k = 2/(p+1)
    e = sum(vals[:p])/p
    for v in vals[p:]:
        e = v*k + e*(1-k)
    return e

def rsi(vals, p=14):
    g,l = [],[]
    for i in range(1,p+1):
        d = vals[-i]-vals[-i-1]
        (g if d>=0 else l).append(abs(d))
    ag, al = sum(g)/p, (sum(l)/p if l else 0.0001)
    rs = ag/al
    return 100 - (100/(1+rs))

def atr(h,l,c,p=14):
    t=[]
    for i in range(1,p+1):
        t.append(max(h[-i]-l[-i], abs(h[-i]-c[-i-1]), abs(l[-i]-c[-i-1])))
    return sum(t)/p

# =========================
# HELPERS
# =========================
def direction_allowed(direction):
    global LAST_TRADE_DIR, LAST_TRADE_TIME
    if LAST_TRADE_DIR is None:
        return True
    if direction != LAST_TRADE_DIR:
        return True
    elapsed = (dz_now() - LAST_TRADE_TIME).total_seconds()/60
    return elapsed >= DIRECTION_COOLDOWN

def in_killzone():
    h = dz_now().hour
    return (9 <= h <= 11) or (15 <= h <= 18)

def send_near_trade(price, score, direction, tf):
    global LAST_NEAR_ALERT
    if LAST_NEAR_ALERT == score:
        return
    LAST_NEAR_ALERT = score

    zone = f"{round(price-2,2)} – {round(price+2,2)}"
    msg = f"""
🚨 Near Trade Alert – XAUUSD ({tf})

📍 المنطقة: {zone}
📊 الاتجاه: {direction}
⏳ قربنا من صفقة: {score}%
🕯️ متوقّع خلال: 1–2 شمعة

⚠️ تنبيه فقط – لا دخول بعد
"""
    for u in SUBSCRIBERS:
        bot.send_message(u, msg)

# =========================
# STRATEGIES
# =========================
def analyze(interval, mode):
    cs = get_candles(interval)
    if len(cs) < 60:
        return None

    c = [float(x["close"]) for x in cs]
    h = [float(x["high"]) for x in cs]
    l = [float(x["low"]) for x in cs]

    price = c[-1]
    e20 = ema(c[-40:],20)
    e50 = ema(c[-80:],50)
    r = rsi(c)
    a = atr(h,l,c)

    score = 0
    direction = None

    if in_killzone():
        score += 20
    if price > e20 and price > e50:
        direction = "BUY"
        score += 20
    elif price < e20 and price < e50:
        direction = "SELL"
        score += 20
    else:
        return None

    if 40 <= r <= 60:
        score += 15
    if abs(price - max(h[-20:])) < 2 or abs(price - min(l[-20:])) < 2:
        score += 15
    if abs(c[-1]-c[-2]) > a*0.3:
        score += 10

    # Near Trade
    if NEAR_TRADE_MIN <= score <= NEAR_TRADE_MAX:
        send_near_trade(price, score, direction, interval)
        return None

    # Real trade
    if score >= 80 and direction_allowed(direction):
        tp = price + a*(TP_ICT_ATR if interval==ICT_INTERVAL else TP_FAST_ATR) if direction=="BUY" else price - a*(TP_ICT_ATR if interval==ICT_INTERVAL else TP_FAST_ATR)
        sl = price - a*(SL_ICT_ATR if interval==ICT_INTERVAL else SL_FAST_ATR) if direction=="BUY" else price + a*(SL_ICT_ATR if interval==ICT_INTERVAL else SL_FAST_ATR)

        return mode, direction, price, tp, sl, score

    return None

# =========================
# MAIN LOOP
# =========================
def loop():
    global LAST_TRADE_DIR, LAST_TRADE_TIME
    while True:
        try:
            checks = [
                (ICT_INTERVAL, "🟢 صفقة قوية (ICT – M15)"),
                (FAST_INTERVAL, "🟡 صفقة متوسطة (EMA – M5)"),
                (FAST_INTERVAL, "🔴 صفقة مخاطرة عالية (Scalping – M5)")
            ]

            for tf, label in checks:
                res = analyze(tf, label)
                if res:
                    title, direction, price, tp, sl, conf = res
                    for u in SUBSCRIBERS:
                        bot.send_message(
                            u,
                            f"""{title}
📊 XAUUSD
{'🟢 BUY' if direction=='BUY' else '🔴 SELL'}
Lot: {LOT_SIZE}
Entry: {price:.2f}
TP: {tp:.2f}
SL: {sl:.2f}
🧠 Confidence: {conf}%"""
                        )
                    LAST_TRADE_DIR = direction
                    LAST_TRADE_TIME = dz_now()
                    time.sleep(60)
        except Exception as e:
            print("ERROR:", e)

        time.sleep(CHECK_EVERY)

# =========================
# COMMAND
# =========================
@bot.message_handler(commands=["start"])
def start(m):
    SUBSCRIBERS.add(m.chat.id)
    bot.send_message(
        m.chat.id,
        "🤖 النظام شبه الاحترافي يعمل\n"
        "🚨 Near Trade مفعّل\n"
        "🟢 قوية / 🟡 متوسطة / 🔴 مخاطرة\n"
        "⏱️ منع الاتجاه: 60 دقيقة"
    )

# =========================
# START
# =========================
Thread(target=loop, daemon=True).start()
bot.infinity_polling()
