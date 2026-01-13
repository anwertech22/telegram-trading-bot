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

# === INTERVALS ===
ICT_INTERVAL = "15min"
FAST_INTERVAL = "5min"

CHECK_EVERY = 300  # 5 minutes

# === ICT SETTINGS ===
ICT_LOOKBACK = 20
TP_ICT_ATR = 1.8
SL_ICT_ATR = 1.2
MIN_CONF_ICT = 70

# === EMA / SCALP SETTINGS ===
TP_FAST_ATR = 0.6
SL_FAST_ATR = 0.8
MIN_CONF_EMA = 60
MIN_CONF_SCALP = 55

# === DIRECTION COOLDOWN ===
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

# =========================
# DATA FUNCTIONS
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
# DIRECTION FILTER
# =========================
def direction_allowed(direction):
    global LAST_TRADE_DIR, LAST_TRADE_TIME

    if LAST_TRADE_DIR is None:
        return True

    if direction != LAST_TRADE_DIR:
        return True

    elapsed = (dz_now() - LAST_TRADE_TIME).total_seconds() / 60
    return elapsed >= DIRECTION_COOLDOWN

# =========================
# ICT STRATEGY (STRONG)
# =========================
def ict_strategy():
    cs = get_candles(ICT_INTERVAL)
    if len(cs) < 100:
        return None

    c = [float(x["close"]) for x in cs]
    h = [float(x["high"]) for x in cs]
    l = [float(x["low"]) for x in cs]

    price = c[-1]
    e20 = ema(c[-40:],20)
    e50 = ema(c[-80:],50)

    direction = None
    conf = 40

    if price > e20 and price > e50:
        direction = "BUY"
    elif price < e20 and price < e50:
        direction = "SELL"
    else:
        return None

    ph = max(h[-ICT_LOOKBACK:-1])
    pl = min(l[-ICT_LOOKBACK:-1])

    if direction == "SELL" and h[-1] > ph and c[-1] < ph:
        conf += 30
    elif direction == "BUY" and l[-1] < pl and c[-1] > pl:
        conf += 30
    else:
        return None

    if conf < MIN_CONF_ICT:
        return None

    a = atr(h,l,c)
    tp = price + a*TP_ICT_ATR if direction=="BUY" else price - a*TP_ICT_ATR
    sl = price - a*SL_ICT_ATR if direction=="BUY" else price + a*SL_ICT_ATR

    return ("🟢 صفقة قوية (ICT – M15)", direction, price, tp, sl, conf)

# =========================
# EMA STRATEGY (MEDIUM)
# =========================
def ema_strategy():
    cs = get_candles(FAST_INTERVAL)
    if len(cs) < 60:
        return None

    c = [float(x["close"]) for x in cs]
    h = [float(x["high"]) for x in cs]
    l = [float(x["low"]) for x in cs]

    price = c[-1]
    e20 = ema(c[-30:],20)
    e50 = ema(c[-50:],50)
    r = rsi(c)

    direction = None
    conf = 40

    if price > e50 and price <= e20 and r < 55:
        direction = "BUY"
        conf += 20
    elif price < e50 and price >= e20 and r > 45:
        direction = "SELL"
        conf += 20
    else:
        return None

    if conf < MIN_CONF_EMA:
        return None

    a = atr(h,l,c)
    tp = price + a*TP_FAST_ATR if direction=="BUY" else price - a*TP_FAST_ATR
    sl = price - a*SL_FAST_ATR if direction=="BUY" else price + a*SL_FAST_ATR

    return ("🟡 صفقة متوسطة (EMA – M5)", direction, price, tp, sl, conf)

# =========================
# SCALPING STRATEGY (HIGH RISK)
# =========================
def scalp_strategy():
    cs = get_candles(FAST_INTERVAL)
    if len(cs) < 40:
        return None

    c = [float(x["close"]) for x in cs]
    h = [float(x["high"]) for x in cs]
    l = [float(x["low"]) for x in cs]

    price = c[-1]
    r = rsi(c)

    if r < 30:
        direction = "BUY"
    elif r > 70:
        direction = "SELL"
    else:
        return None

    conf = 55
    a = atr(h,l,c)
    tp = price + a*0.4 if direction=="BUY" else price - a*0.4
    sl = price - a*0.6 if direction=="BUY" else price + a*0.6

    return ("🔴 صفقة مخاطرة عالية (Scalping – M5)", direction, price, tp, sl, conf)

# =========================
# MAIN LOOP
# =========================
def loop():
    global LAST_TRADE_DIR, LAST_TRADE_TIME

    while True:
        try:
            for strat in [ict_strategy, ema_strategy, scalp_strategy]:
                res = strat()
                if res:
                    title, direction, price, tp, sl, conf = res

                    if not direction_allowed(direction):
                        continue

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
                    time.sleep(60)  # anti-spam
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
        "🤖 البوت يعمل\n"
        "🟢 ICT (قوية)\n"
        "🟡 EMA (متوسطة)\n"
        "🔴 Scalping (مخاطرة)\n"
        "⏱️ منع الاتجاه: 60 دقيقة"
    )

# =========================
# START
# =========================
Thread(target=loop, daemon=True).start()
bot.infinity_polling()
