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
DEBUG = True
PAIR = "XAUUSD"
INTERVAL = "15min"
CHECK_EVERY = 900  # seconds

# ====== STRATEGY CORE ======
RSI_BUY = 40
RSI_SELL = 60

MIN_CONFIDENCE = 60   # ⬅️ تم التخفيض من 70 إلى 60 (اختبار ذكي)

MIN_ATR = 1.5

# Breakout
BREAKOUT_LOOKBACK = 20
BREAKOUT_BUFFER = 0.2
BREAKOUT_WEIGHT = 25

# ICT
ICT_LOOKBACK = 20
FVG_BUFFER = 0.1

# Risk
R_TP = 2.5
R_SL = 1.5
BE_R = 1.0
TRAIL_R = 2.0
TRAIL_STEP = 0.5

# Sessions (Algeria Time)
LONDON = (9, 12)
NEWYORK = (15, 18)

# =========================
# ENV
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
TD_API_KEY = os.getenv("TD_API_KEY")

if not BOT_TOKEN or not TD_API_KEY:
    raise Exception("Missing ENV")

bot = telebot.TeleBot(BOT_TOKEN)
SUBSCRIBERS = set()

# =========================
# STATE
# =========================
OPEN_TRADE = None
ANALYZED = 0
NO_TRADE_CANDLES = 0
NEAR_COUNT = 0
LAST_REPORT_DATE = None

# =========================
# DATA
# =========================
def get_candles(limit=200):
    r = requests.get(
        "https://api.twelvedata.com/time_series",
        params={
            "symbol": "XAU/USD",
            "interval": INTERVAL,
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
# ICT LOGIC
# =========================
def liquidity_sweep(h,l,c):
    ph = max(h[-ICT_LOOKBACK:-1])
    pl = min(l[-ICT_LOOKBACK:-1])
    if h[-1] > ph and c[-1] < ph:
        return "SELL"
    if l[-1] < pl and c[-1] > pl:
        return "BUY"
    return None

def fvg(h,l,dir):
    if dir=="BUY" and l[-1] > h[-3]:
        return True
    if dir=="SELL" and h[-1] < l[-3]:
        return True
    return False

# =========================
# TIME FILTER
# =========================
def in_session():
    hr = dz_now().hour
    return (LONDON[0] <= hr < LONDON[1]) or (NEWYORK[0] <= hr < NEWYORK[1])

# =========================
# PREMIUM / DISCOUNT
# =========================
def premium_discount(h,l,price,dir):
    hi, lo = max(h[-ICT_LOOKBACK:]), min(l[-ICT_LOOKBACK:])
    mid = (hi+lo)/2
    return (price < mid if dir=="BUY" else price > mid)

# =========================
# ANALYSIS
# =========================
def analyze():
    global ANALYZED, NO_TRADE_CANDLES, NEAR_COUNT
    ANALYZED += 1

    if not in_session():
        return ["خارج جلسات التداول"]

    cs = get_candles()
    if len(cs) < 100:
        return ["بيانات غير كافية"]

    c = [float(x["close"]) for x in cs]
    h = [float(x["high"]) for x in cs]
    l = [float(x["low"]) for x in cs]

    price = c[-1]
    r = rsi(c)
    e20, e50 = ema(c[-40:],20), ema(c[-80:],50)
    a = atr(h,l,c)

    conf = 0
    direction = None
    reasons = []

    if r <= RSI_BUY:
        conf += 20
        direction = "BUY"
    elif r >= RSI_SELL:
        conf += 20
        direction = "SELL"
    else:
        reasons.append("RSI حيادي")

    if price > e20 and price > e50:
        conf += 20
        direction = "BUY"
    elif price < e20 and price < e50:
        conf += 20
        direction = "SELL"
    else:
        reasons.append("بين EMA")

    if a >= MIN_ATR:
        conf += 10
    else:
        reasons.append("ATR ضعيف")

    sweep = liquidity_sweep(h,l,c)
    if not sweep or sweep != direction:
        return ["لا يوجد Liquidity Sweep صالح"]

    if not fvg(h,l,direction):
        return ["لا يوجد FVG"]

    if not premium_discount(h,l,price,direction):
        return ["ليس في Premium/Discount"]

    conf += 30

    if conf < MIN_CONFIDENCE:
        NEAR_COUNT += 1
        return [f"Confidence منخفض ({conf}%)"]

    NO_TRADE_CANDLES = 0
    return {
        "dir": direction,
        "price": price,
        "atr": a,
        "conf": conf
    }

# =========================
# LOOP
# =========================
def loop():
    global OPEN_TRADE, NO_TRADE_CANDLES
    while True:
        try:
            res = analyze()
            if isinstance(res, dict):
                entry = res["price"]
                a = res["atr"]
                tp = entry + a*R_TP if res["dir"]=="BUY" else entry - a*R_TP
                sl = entry - a*R_SL if res["dir"]=="BUY" else entry + a*R_SL

                for u in SUBSCRIBERS:
                    bot.send_message(
                        u,
                        f"""📊 XAUUSD – M15 (TEST MODE)
{'🟢 BUY' if res['dir']=='BUY' else '🔴 SELL'} @ {entry:.2f}
🎯 TP: {tp:.2f}
❌ SL: {sl:.2f}
🧠 Confidence: {res['conf']}%"""
                    )
            else:
                NO_TRADE_CANDLES += 1
                if DEBUG:
                    for u in SUBSCRIBERS:
                        bot.send_message(u, "🧪 DEBUG\n" + "\n".join("❌ "+x for x in res))

        except Exception as e:
            print("ERROR:", e)

        for _ in range(CHECK_EVERY):
            time.sleep(1)

# =========================
# COMMAND
# =========================
@bot.message_handler(commands=["start"])
def start(m):
    SUBSCRIBERS.add(m.chat.id)
    bot.send_message(
        m.chat.id,
        "🤖 البوت يعمل\n🧪 Test Mode: Confidence = 60\n⏱️ M15"
    )

# =========================
# START
# =========================
Thread(target=loop, daemon=True).start()
bot.infinity_polling()
