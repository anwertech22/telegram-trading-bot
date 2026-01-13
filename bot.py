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
CHECK_EVERY = 900

# ===== ACCOUNT MODE =====
SMALL_ACCOUNT_MODE = True   # 🔥 مفعل
LOT_SIZE = 0.02

# ===== STRATEGY =====
RSI_BUY = 40
RSI_SELL = 60
MIN_CONFIDENCE = 60
MIN_ATR = 1.0

# ICT
ICT_LOOKBACK = 20

# ===== QUICK PROFIT (لوت 0.02) =====
TP_ATR_MULTIPLIER = 0.6     # خروج سريع
SL_ATR_MULTIPLIER = 0.8

# ===== Killzones (الجزائر) =====
LONDON_KZ = (9, 10, 30)     # 09:00 → 10:30
NY_KZ = (15, 30, 17, 0)     # 15:30 → 17:00

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
# ICT
# =========================
def liquidity_sweep(h,l,c):
    ph = max(h[-ICT_LOOKBACK:-1])
    pl = min(l[-ICT_LOOKBACK:-1])
    if h[-1] > ph and c[-1] < ph:
        return "SELL", ph
    if l[-1] < pl and c[-1] > pl:
        return "BUY", pl
    return None, None

def fvg(h,l,dir):
    if dir=="BUY" and l[-1] > h[-3]:
        return True
    if dir=="SELL" and h[-1] < l[-3]:
        return True
    return False

# =========================
# KILLZONE
# =========================
def in_killzone():
    now = dz_now()
    h, m = now.hour, now.minute

    if h == LONDON_KZ[0] or (h == LONDON_KZ[1] and m <= LONDON_KZ[2]):
        return "London"

    if (h > NY_KZ[0] or (h == NY_KZ[0] and m >= NY_KZ[1])) and \
       (h < NY_KZ[2] or (h == NY_KZ[2] and m <= NY_KZ[3])):
        return "NewYork"

    return None

# =========================
# ANALYSIS
# =========================
def analyze():
    session = in_killzone()
    if not session:
        return None

    cs = get_candles()
    if len(cs) < 100:
        return None

    c = [float(x["close"]) for x in cs]
    h = [float(x["high"]) for x in cs]
    l = [float(x["low"]) for x in cs]

    price = c[-1]
    r = rsi(c)
    e20 = ema(c[-40:],20)
    e50 = ema(c[-80:],50)
    a = atr(h,l,c)

    conf = 0
    direction = None

    if r <= RSI_BUY:
        conf += 20; direction="BUY"
    elif r >= RSI_SELL:
        conf += 20; direction="SELL"
    else:
        return None

    if price > e20 and price > e50:
        conf += 20; direction="BUY"
    elif price < e20 and price < e50:
        conf += 20; direction="SELL"
    else:
        return None

    if a < MIN_ATR:
        return None
    conf += 10

    sweep_dir, sweep_level = liquidity_sweep(h,l,c)
    if sweep_dir != direction:
        return None

    if not fvg(h,l,direction):
        return None

    conf += 30
    if conf < MIN_CONFIDENCE:
        return None

    return {
        "dir": direction,
        "price": price,
        "atr": a,
        "conf": conf,
        "session": session
    }

# =========================
# LOOP
# =========================
def loop():
    while True:
        try:
            res = analyze()
            if isinstance(res, dict):
                entry = res["price"]
                a = res["atr"]

                tp = entry + a*TP_ATR_MULTIPLIER if res["dir"]=="BUY" else entry - a*TP_ATR_MULTIPLIER
                sl = entry - a*SL_ATR_MULTIPLIER if res["dir"]=="BUY" else entry + a*SL_ATR_MULTIPLIER

                for u in SUBSCRIBERS:
                    bot.send_message(
                        u,
                        f"""📊 XAUUSD – M15 (Small Account Mode)
{'🟢 BUY' if res['dir']=='BUY' else '🔴 SELL'}
Session: {res['session']}
Lot: {LOT_SIZE}
Entry: {entry:.2f}
TP: {tp:.2f}
SL: {sl:.2f}
🧠 Confidence: {res['conf']}%

🎯 هدف ربح صغير وسريع"""
                    )
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
        "🔥 Small Account Mode مفعل\n"
        "💰 مناسب لحساب 100$–300$\n"
        "📈 أهداف ربح صغيرة وسريعة"
    )

# =========================
# START
# =========================
Thread(target=loop, daemon=True).start()
bot.infinity_polling()
