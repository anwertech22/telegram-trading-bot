import os, time, requests, telebot
from datetime import datetime, timedelta
from threading import Thread

# ==================================================
# TIMEZONE (ALGERIA UTC+1)
# ==================================================
def dz_now():
    return datetime.utcnow() + timedelta(hours=1)

# ==================================================
# BASIC CONFIG
# ==================================================
PAIR = "XAU/USD"
LOT_SIZE = 0.02

TF_ICT = "15min"
TF_FAST = "5min"

CHECK_EVERY = 300  # 5 minutes

# ==================================================
# INDICATORS SETTINGS
# ==================================================
EMA_PERIOD = 20

RSI_BUY = 40
RSI_SELL = 60

CONF_TRADE = 60
CONF_NEAR_MIN = 50
CONF_NEAR_MAX = 59

# ATR TP/SL
TP_ICT_ATR = 1.5
SL_ICT_ATR = 1.0

TP_EMA_ATR = 0.7
SL_EMA_ATR = 0.9

TP_SCALP_ATR = 0.4
SL_SCALP_ATR = 0.6

# ==================================================
# PROTECTION
# ==================================================
DIRECTION_COOLDOWN = 60  # minutes
MAX_SCALP_TRADES = 1

# ==================================================
# NEWS (ALGERIA TIME)
# ==================================================
NEWS_EVENTS = {
    "CPI": ["14:30"],
    "NFP": ["14:30"],
    "FOMC": ["20:00"]
}

NEWS_BLOCK_BEFORE = 45  # minutes
NEWS_BLOCK_AFTER = 15   # minutes
POST_NEWS_WINDOW = 90   # minutes
POST_NEWS_LIMIT = 2

# ==================================================
# ENV
# ==================================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
TD_API_KEY = os.getenv("TD_API_KEY")
if not BOT_TOKEN or not TD_API_KEY:
    raise Exception("Missing ENV variables")

bot = telebot.TeleBot(BOT_TOKEN)
SUBSCRIBERS = set()

# ==================================================
# STATE
# ==================================================
LAST_TRADE_DIR = None
LAST_TRADE_TIME = None

LAST_NEAR_ALERT = None

LAST_NEWS_TIME = None
POST_NEWS_ACTIVE = False
POST_NEWS_COUNT = 0

SCALP_COUNT = 0

# ==================================================
# DATA
# ==================================================
def get_candles(interval, limit=200):
    r = requests.get(
        "https://api.twelvedata.com/time_series",
        params={
            "symbol": PAIR,
            "interval": interval,
            "outputsize": limit,
            "apikey": TD_API_KEY
        }, timeout=10)
    data = r.json().get("values", [])
    data.reverse()
    return data

def ema(vals, p=EMA_PERIOD):
    k = 2/(p+1)
    e = sum(vals[:p])/p
    for v in vals[p:]:
        e = v*k + e*(1-k)
    return e

def rsi(vals, p=14):
    g,l=[],[]
    for i in range(1,p+1):
        d = vals[-i]-vals[-i-1]
        (g if d>=0 else l).append(abs(d))
    ag, al = sum(g)/p, (sum(l)/p if l else 0.0001)
    rs = ag/al
    return 100-(100/(1+rs))

def atr(h,l,c,p=14):
    tr=[]
    for i in range(1,p+1):
        tr.append(max(h[-i]-l[-i],abs(h[-i]-c[-i-1]),abs(l[-i]-c[-i-1])))
    return sum(tr)/p

# ==================================================
# HELPERS
# ==================================================
def in_killzone():
    h = dz_now().hour
    return (9 <= h <= 11) or (15 <= h <= 18)

def direction_allowed(direction):
    global LAST_TRADE_DIR, LAST_TRADE_TIME
    if LAST_TRADE_DIR is None:
        return True
    if direction != LAST_TRADE_DIR:
        return True
    mins = (dz_now()-LAST_TRADE_TIME).total_seconds()/60
    return mins >= DIRECTION_COOLDOWN

def send_near(price, score, direction, tf, label):
    global LAST_NEAR_ALERT
    if LAST_NEAR_ALERT == score:
        return
    LAST_NEAR_ALERT = score

    zone = f"{round(price-2,2)} – {round(price+2,2)}"
    msg = f"""
🚨 Near Trade Alert – {label}
📊 XAUUSD ({tf})
📍 المنطقة: {zone}
📈 الاتجاه: {direction}
⏳ قربنا من صفقة: {score}%
⚠️ تنبيه فقط – لا دخول بعد
"""
    for u in SUBSCRIBERS:
        bot.send_message(u, msg)

# ==================================================
# NEWS ENGINE
# ==================================================
def news_blocked():
    now = dz_now()
    for times in NEWS_EVENTS.values():
        for t in times:
            h,m = map(int,t.split(":"))
            nt = now.replace(hour=h,minute=m,second=0)
            diff = abs((nt-now).total_seconds()/60)
            if diff <= NEWS_BLOCK_BEFORE:
                return True
    return False

def check_news():
    global LAST_NEWS_TIME, POST_NEWS_ACTIVE, POST_NEWS_COUNT

    now = dz_now()
    now_str = now.strftime("%H:%M")

    for name,times in NEWS_EVENTS.items():
        if now_str in times:
            LAST_NEWS_TIME = now
            POST_NEWS_ACTIVE = False
            POST_NEWS_COUNT = 0
            for u in SUBSCRIBERS:
                bot.send_message(u,f"📰 {name} صدر الآن\n⏸️ ننتظر هدوء السوق")

    if LAST_NEWS_TIME:
        mins = (now-LAST_NEWS_TIME).total_seconds()/60
        if mins >= NEWS_BLOCK_AFTER:
            POST_NEWS_ACTIVE = True
        if mins >= POST_NEWS_WINDOW:
            POST_NEWS_ACTIVE = False

# ==================================================
# STRATEGIES
# ==================================================
def analyze(tf, mode):
    cs = get_candles(tf)
    if len(cs) < 60:
        return None

    c=[float(x["close"]) for x in cs]
    h=[float(x["high"]) for x in cs]
    l=[float(x["low"]) for x in cs]

    price=c[-1]
    e20=ema(c)
    r=rsi(c)
    a=atr(h,l,c)

    score=0
    direction=None

    if price>e20:
        direction="BUY"; score+=30
    elif price<e20:
        direction="SELL"; score+=30
    else:
        return None

    if r<=RSI_BUY or r>=RSI_SELL:
        score+=20

    if abs(c[-1]-c[-2]) > a*0.3:
        score+=20

    # Near Trade
    if CONF_NEAR_MIN <= score <= CONF_NEAR_MAX:
        send_near(price, score, direction, tf, mode)
        return None

    if score < CONF_TRADE:
        return None

    tp_mult, sl_mult = (
        (TP_ICT_ATR, SL_ICT_ATR) if mode=="🟢 صفقة قوية (ICT)" else
        (TP_EMA_ATR, SL_EMA_ATR) if mode=="🟡 صفقة متوسطة (EMA)" else
        (TP_SCALP_ATR, SL_SCALP_ATR)
    )

    tp = price + a*tp_mult if direction=="BUY" else price - a*tp_mult
    sl = price - a*sl_mult if direction=="BUY" else price + a*sl_mult

    return mode, direction, price, tp, sl, score

# ==================================================
# MAIN LOOP
# ==================================================
def loop():
    global LAST_TRADE_DIR, LAST_TRADE_TIME, POST_NEWS_COUNT, SCALP_COUNT

    while True:
        try:
            check_news()

            if news_blocked():
                time.sleep(CHECK_EVERY)
                continue

            strategies = [
                (TF_ICT, "🟢 صفقة قوية (ICT)"),
                (TF_FAST, "🟡 صفقة متوسطة (EMA)")
            ]

            if in_killzone() and SCALP_COUNT < MAX_SCALP_TRADES:
                strategies.append((TF_FAST, "🔴 مخاطرة عالية (Scalp)"))

            for tf,label in strategies:
                res = analyze(tf,label)
                if res:
                    mode, direction, price, tp, sl, conf = res

                    if not direction_allowed(direction):
                        continue

                    if POST_NEWS_ACTIVE:
                        if POST_NEWS_COUNT >= POST_NEWS_LIMIT:
                            continue
                        POST_NEWS_COUNT += 1

                    if "Scalp" in label:
                        SCALP_COUNT += 1

                    for u in SUBSCRIBERS:
                        bot.send_message(
                            u,
f"""{mode}
📊 XAUUSD ({tf})
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
            print("ERROR:",e)

        time.sleep(CHECK_EVERY)

# ==================================================
# COMMAND
# ==================================================
@bot.message_handler(commands=["start"])
def start(m):
    SUBSCRIBERS.add(m.chat.id)
    bot.send_message(
        m.chat.id,
        "🤖 FINAL Multi-Strategy System\n"
        "🟢 ICT | 🟡 EMA | 🔴 Scalping\n"
        "🚨 Near Trade مفعّل\n"
        "📰 CPI / NFP / FOMC 🇩🇿\n"
        "⛔ منع التداول وقت الخبر\n"
        "🔥 Post-News Mode\n"
        "🛡️ حماية كاملة"
    )

# ==================================================
# START
# ==================================================
Thread(target=loop,daemon=True).start()
bot.infinity_polling()
