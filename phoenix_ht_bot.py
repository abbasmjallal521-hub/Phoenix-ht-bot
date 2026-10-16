#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PHOENIX HAZ SMC — Telegram Signal Bot
Developed by: The Phoenix HAZ Syndicate

Reads the market (Gold, Silver, Dow, Nasdaq, Oil), builds the same pending-order
plan as the Phoenix HAZ SMC indicator (range + ATR + 4-timeframe trend) and posts
each order to a Telegram channel: entry, stop, target, timeframe. It then follows
each order and posts when it is filled, hits the target, hits the stop, or expires.

DISCLAIMER: educational use only, not financial advice. Trading on margin or CFDs
is high risk. Prices come from a data feed and can differ from your broker.
This bot posts plans; it does not place trades.

Usage:
  python phoenix_ht_bot.py --dry-run --once   # test: prints messages, sends nothing
  python phoenix_ht_bot.py --selftest         # offline logic test with fake data
  python phoenix_ht_bot.py --simulate         # every symbol x every timeframe, fake prices
  python phoenix_ht_bot.py                    # run for real (needs .env)
  python phoenix_ht_bot.py --minutes 340      # run 340 minutes, then save and exit (GitHub Actions)
"""
import os, sys, json, time, html, random, argparse, logging
from collections import namedtuple
from datetime import datetime, timezone, timedelta, date
from zoneinfo import ZoneInfo

try:
    import requests
except ImportError:  # selftest does not need it
    requests = None

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, "phoenix_state.json")

# ───────────────────────────── settings ─────────────────────────────
def load_env(path=os.path.join(HERE, ".env")):
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

load_env()
ENV = os.environ.get

INSTRUMENTS = {
    "XAUUSD": {"name": "Gold",       "yahoo": "GC=F", "oanda": "XAU_USD",    "digits": 2, "tick": 0.01, "pip": 0.1, "contract": 100},
    "XAGUSD": {"name": "Silver",     "yahoo": "SI=F", "oanda": "XAG_USD",    "digits": 3, "tick": 0.001, "pip": 0.01, "contract": 5000},
    "US30":   {"name": "Dow Jones",  "yahoo": "YM=F", "ref": "^DJI", "oanda": "US30_USD",   "digits": 1, "tick": 0.1, "pip": 1.0, "contract": 1},
    "NAS100": {"name": "Nasdaq 100", "yahoo": "NQ=F", "ref": "^NDX", "oanda": "NAS100_USD", "digits": 1, "tick": 0.1, "pip": 1.0, "contract": 1},
    "USOIL":  {"name": "WTI Oil",    "yahoo": "CL=F", "oanda": "WTICO_USD",  "digits": 2, "tick": 0.01, "pip": 0.01, "contract": 1000},
}
for _s, _i in INSTRUMENTS.items():              # override a pip size with PIP_XAUUSD=0.1 etc.
    if ENV("PIP_" + _s):
        _i["pip"] = float(ENV("PIP_" + _s))
    if ENV("CONTRACT_" + _s):                       # units per 1 lot at your broker (money maths)
        _i["contract"] = float(ENV("CONTRACT_" + _s))
TF_SEC = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600}

# plan settings (same defaults as the indicator)
RANGE_BARS = int(ENV("RANGE_BARS", "24"))
SPREAD_PCT, EARLY_PCT = 15.0, 10.0
SL_MULT = float(ENV("SL_MULT", "1.0"))
REFRESH_MIN = int(ENV("REFRESH_MIN", "20"))      # how often a plan is refreshed and unfilled orders re-checked (minutes)
MAX_DIST_ATR = float(ENV("MAX_DIST_ATR", "3"))   # only post orders within this many ATR of price
DEDUP_ATR = float(ENV("DEDUP_ATR", "0.5"))       # keep the old order if the new one is this close

def parse_rr(txt, default):
    try:
        v = [float(x) for x in txt.replace(" ", "").split(",") if x]
        return v or default
    except ValueError:
        return default

# reward:risk of each target, per timeframe (target = entry +/- R x stop distance)
RR = {"1m": parse_rr(ENV("RR_1M", "1"), [1.0]),
      "5m": parse_rr(ENV("RR_5M", "1"), [1.0]),
      "15m": parse_rr(ENV("RR_15M", "2"), [2.0]),
      "30m": parse_rr(ENV("RR_30M", "2"), [2.0]),
      "1h": parse_rr(ENV("RR_1H", "3"), [3.0])}      # ONE target per trade, set by timeframe (write "1,2" for two)

# filters that remove orders that look unrealistic
MIN_RISK_ATR = float(ENV("MIN_RISK_ATR", "0.5"))     # stop must be at least this many ATR
MAX_TP_ATR = float(ENV("MAX_TP_ATR", "8"))           # farthest target within this many ATR
MAX_TP_DAILY = float(ENV("MAX_TP_DAILY", "1.0"))     # farthest target within this share of a normal daily range
MOVE_PER_BAR = float(ENV("MOVE_PER_BAR", "0.5"))     # net ATR price travels per bar (time check)
MAX_HOLD_HOURS = float(ENV("MAX_HOLD_HOURS", "24"))   # the last target must be reachable within this many hours

# quality rules (fewer stop-outs)
BE_AT_R = float(ENV("BE_AT_R", "0.7"))               # move the stop to entry after this share of the way to target 1 (0 = off)
COOLDOWN_MIN = int(ENV("COOLDOWN_MIN", "30"))        # after a stop-out, no new order in the same direction for this long
SPIKE_ATR = float(ENV("SPIKE_ATR", "3.0"))           # skip planning right after a news-size candle (range above this many ATR)
NEUTRAL_FADE = ENV("NEUTRAL_FADE", "1") == "1"       # mixed trend: only reversal (limit) orders, no breakouts
SWEEP_BUFFER = float(ENV("SWEEP_BUFFER_ATR", "0.25"))   # extra stop room (ATR) so a quick stop-hunt wick does not take the trade out
FAKE_BREAK_BARS = int(ENV("FAKE_BREAK_BARS", "6"))      # a wick beyond the range that closes back inside within this many bars = fake breakout
DAY_START_HOUR = int(ENV("DAY_START_HOUR", "18"))       # trading day starts (NY hour): totals reset at market open
REPORT_HOUR = int(ENV("REPORT_HOUR", "17"))             # market-close message time (NY hour, sent at :05). Friday = weekly
MSG_TZ = ZoneInfo(ENV("MSG_TIMEZONE", "Asia/Beirut"))    # time zone of the morning message
MORNING_HOUR = int(ENV("MORNING_HOUR", "9"))            # morning message hour (MSG_TIMEZONE), Monday to Friday
DAILY_MSGS = ENV("DAILY_MSGS", "1") == "1"              # morning and market-close messages on/off
LOT_DEFAULT = float(ENV("LOT_DEFAULT", "0.01"))         # lot size for the money numbers until a user sets /lot
CHANNEL_FEED = ENV("CHANNEL_FEED", "1") == "1"          # also post every signal to the channel (TELEGRAM_CHAT_ID)
PENDING_MAX_HOURS = float(ENV("PENDING_MAX_HOURS", "24"))  # an order never taken is dropped after this long
OPEN_MAX_HOURS = float(ENV("OPEN_MAX_HOURS", "48"))        # an open trade is closed after this long

TZ = ZoneInfo(ENV("TIMEZONE", "America/New_York"))
def hm(s):
    h, m = s.split(":"); return int(h) * 60 + int(m)
PLAN_START = hm(ENV("PLAN_START", "01:30"))
PLAN_END = hm(ENV("PLAN_END", "21:30"))

SHOW_COUNTER = ENV("SHOW_COUNTER", "0") == "1"
MIN_RR = float(ENV("MIN_RR", "1.0"))   # never post an order whose stop is bigger than its target
SEND_UPDATES = ENV("SEND_UPDATES", "1") == "1"
MAX_PER_PAIR_DAY = int(ENV("MAX_PER_PAIR_DAY", "6"))        # new signals per symbol+timeframe per day
MAX_SIGNALS_PER_DAY = int(ENV("MAX_SIGNALS_PER_DAY", "100"))  # new signals per day, all symbols together

PENDING, OPEN, TP_HIT, SL_HIT, DAY_END, BE_HIT, CANCELLED = 0, 1, 2, 3, 4, 5, 9
STICKY_MAX_ATR = float(ENV("STICKY_MAX_ATR", "8"))      # an unfilled order stays while price is within this many ATR of it
AVAILABLE_SYMS, AVAILABLE_TFS = list(INSTRUMENTS), list(TF_SEC)
Bar = namedtuple("Bar", "t o h l c")
log = logging.getLogger("phoenix")

# ───────────────────────────── maths ─────────────────────────────
def calc_atr(bars, n=14):
    if len(bars) < n + 1:
        return None
    trs, prev = [], None
    for b in bars:
        trs.append(b.h - b.l if prev is None else max(b.h - b.l, abs(b.h - prev), abs(b.l - prev)))
        prev = b.c
    atr = sum(trs[:n]) / n
    for tr in trs[n:]:
        atr = (atr * (n - 1) + tr) / n
    return atr

def ema_last(values, n):
    a, e = 2.0 / (n + 1), None
    for v in values:
        e = v if e is None else a * v + (1 - a) * e
    return e

def bias_from_bars(bars):
    """+1 bull, -1 bear, 0 mixed, from the last completed bar (like the indicator)."""
    if len(bars) < 55:
        return 0
    closes = [b.c for b in bars]
    c, e20, e50 = closes[-1], ema_last(closes, 20), ema_last(closes, 50)
    return 1 if (c > e20 and e20 >= e50) else -1 if (c < e20 and e20 <= e50) else 0

def local_dirs(bars, atr):
    """Direction of the chart timeframe itself: (EMA structure, 8-bar momentum), each +1 / -1 / 0."""
    closes = [b.c for b in bars]
    if len(closes) < 55 or not atr:
        return 0, 0
    c, e20, e50 = closes[-1], ema_last(closes, 20), ema_last(closes, 50)
    ema_dir = 1 if (c > e20 and e20 >= e50) else -1 if (c < e20 and e20 <= e50) else 0
    mom = (c - closes[-9]) / atr
    return ema_dir, (1 if mom > 0.6 else -1 if mom < -0.6 else 0)

def sweep_flags(bars):
    """Fake breakout: price poked beyond the older range recently but closed back inside."""
    k, n = FAKE_BREAK_BARS, RANGE_BARS
    if len(bars) < n + k + 1:
        return False, False
    older, recent = bars[-(n + k):-k], bars[-k:]
    ph, pl = max(b.h for b in older), min(b.l for b in older)
    return (max(b.h for b in recent) > ph and bars[-1].c < ph), (min(b.l for b in recent) < pl and bars[-1].c > pl)

def arrow(b): return "▲" if b == 1 else "▼" if b == -1 else "•"

def ny_parts(ts):
    dt = datetime.fromtimestamp(ts, TZ)
    return dt.hour * 60 + dt.minute, dt.strftime("%Y-%m-%d")

# ───────────────────────────── plan logic (mirrors the indicator) ─────────────────────────────
def build_orders(atr, hi, lo, close, bias, tick, rrs, ema_dir=0, mom_dir=0, fake_up=False, fake_dn=False):
    """Entry / stop come from the range and ATR. The target = R x stop distance (R set by timeframe).
    Direction must agree with the higher timeframes AND with what the chart timeframe is doing now."""
    sp = max(atr * SPREAD_PCT / 100.0, tick)
    early = min(atr * EARLY_PCT / 100.0, sp)
    slD = atr * (SL_MULT + SWEEP_BUFFER)
    out = []

    def allowed(d, is_stop):
        if ema_dir == -d or mom_dir == -d:          # the chart is moving against this direction right now
            return False
        if bias == d:
            return True
        if bias == 0:                               # mixed higher timeframes
            strong = ema_dir == d and mom_dir == d  # ...but the chart itself is clearly running this way: take the breakout
            return strong or ((not is_stop) and NEUTRAL_FADE)
        return SHOW_COUNTER

    def mk(direction, kind, is_stop, lvl, sl, inval):
        o_lo = lvl if direction == 1 else lvl - sp
        o_hi = lvl + sp if direction == 1 else lvl
        trig = o_lo if (direction == 1 and is_stop) or (direction == -1 and not is_stop) else o_hi
        risk = abs(trig - sl)
        out.append(dict(dir=direction, kind=kind, is_stop=is_stop, with_trend=(bias == direction), lo=o_lo, hi=o_hi,
                        entry=trig, trig=trig, sl=sl, inval=inval, risk=risk, sp=sp, rrs=list(rrs),
                        tps=[trig + direction * r * risk for r in rrs]))

    if allowed(1, True) and not fake_up:               # no breakout buy right after a fake break above
        mk(1, "BUY STOP", True, hi + sp - early, hi - slD, lo)               # a close below the range low kills a breakout buy
    if allowed(-1, True) and not fake_dn:
        mk(-1, "SELL STOP", True, lo - sp + early, lo + slD, hi)
    lvl = hi - sp - early
    if close < lvl - sp and allowed(-1, False):
        mk(-1, "SELL LIMIT", False, lvl, hi + slD, hi + slD)
    lvl = lo + sp + early
    if close > lvl + sp and allowed(1, False):
        mk(1, "BUY LIMIT", False, lvl, lo - slD, lo - slD)
    return out

def unrealistic(o, atr, datr, mins, tf):
    """Return the reason an order looks impossible to work out, or None."""
    far = abs(o["tps"][-1] - o["trig"])
    if o["risk"] < MIN_RISK_ATR * atr or o["risk"] < 4 * o["sp"]:
        return "stop too tight for the noise and spread"
    if far > MAX_TP_ATR * atr:
        return "last target too far for this timeframe"
    if datr and far > MAX_TP_DAILY * datr:
        return "last target bigger than a normal daily range"
    bars_left = MAX_HOLD_HOURS * 60 / (TF_SEC[tf] / 60.0)
    if far / atr / MOVE_PER_BAR > bars_left:
        return "last target would take too long to reach"
    return None

def pct(x, base):
    return int(max(0, min(99, x / base * 100))) if base > 0 else 0

def trading_day(ts):
    """The trading day starts at market open (DAY_START_HOUR New York), not at midnight."""
    return (datetime.fromtimestamp(ts, TZ) + timedelta(hours=24 - DAY_START_HOUR)).date()

def realized(o, exit_px=None):
    """Signed price distance banked by an order (when there are several targets the position is split equally)."""
    n = max(len(o["tps"]), 1); w = 1.0 / n
    banked = sum(w * (o["tps"][i] - o["trig"]) * o["dir"] for i in range(o.get("hits", 0)))
    rest = 1.0 - w * o.get("hits", 0)
    if o["state"] == SL_HIT:
        return banked - rest * o["risk"]
    if o["state"] == DAY_END and exit_px is not None:
        return banked + rest * (exit_px - o["trig"]) * o["dir"]
    return banked

def money(sym, dist, lot):
    return dist * INSTRUMENTS[sym]["contract"] * lot

def summarize(ledger, syms, tfs, lot, ref_ts):
    td = trading_day(ref_ts); wk = td.isocalendar()[:2]; mo = (td.year, td.month)
    out = {k: dict(pips=0.0, usd=0.0, win=0, loss=0) for k in ("day", "week", "month")}
    for e in ledger:
        if e["sym"] not in syms or e["tf"] not in tfs:
            continue
        d = date.fromisoformat(e["td"])
        pp, uu = e["dist"] / INSTRUMENTS[e["sym"]]["pip"], money(e["sym"], e["dist"], lot)
        for key, same in (("day", d == td), ("week", d.isocalendar()[:2] == wk), ("month", (d.year, d.month) == mo)):
            if same:
                o = out[key]; o["pips"] += pp; o["usd"] += uu
                if e["dist"] > 0: o["win"] += 1
                elif e["dist"] < 0: o["loss"] += 1
    return out

# ───────────────────────────── messages ─────────────────────────────
LINE = "━━━━━━━━━━━━━━━━━━"
SIGN = "🔥 <b>The Phoenix HAZ Syndicate</b>"
ICON = {"XAUUSD": "🥇", "XAGUSD": "🥈", "US30": "🏛", "NAS100": "💻", "USOIL": "🛢"}
KIND_AR = {"BUY STOP": "شراء عند الاختراق", "SELL STOP": "بيع عند الكسر",
           "BUY LIMIT": "شراء عند الارتداد", "SELL LIMIT": "بيع عند الارتداد"}

QUOTES = [
    ("Discipline is the real edge.", "الانضباط هو الميزة الحقيقية."),
    ("Plan the trade, trade the plan.", "خطّط للصفقة ثم التزم بخطتك."),
    ("Protect your capital first. Profits follow.", "احمِ رأس مالك أولاً، والأرباح تأتي لاحقاً."),
    ("Fall seven times, rise like a Phoenix.", "اسقط سبع مرات وانهض كالعنقاء."),
    ("Patience is also a position.", "الصبر أيضاً مركز في السوق."),
    ("Small risk. Big discipline.", "مخاطرة صغيرة، وانضباط كبير."),
    ("Be early to protect, never late to cut.", "كن مبكراً في الحماية، ولا تتأخر في القطع."),
    ("Calm minds read the market best.", "العقول الهادئة تقرأ السوق أفضل."),
    ("One good trade beats ten rushed ones.", "صفقة جيدة واحدة أفضل من عشر متسرّعة."),
    ("The market rewards patience, not impulse.", "السوق يكافئ الصبر لا الاندفاع."),
    ("Cut losses small, let discipline grow.", "اقطع الخسارة صغيرة ودع الانضباط ينمو."),
    ("Consistency beats intensity.", "الاستمرارية تتفوق على الحماس."),
    ("Your stop loss is your best friend.", "وقف الخسارة أفضل أصدقائك."),
    ("Trade what you see, not what you hope.", "تداول ما تراه لا ما تتمنّاه."),
    ("Every setup is a lesson, win or lose.", "كل فرصة درس، سواء ربحت أو خسرت."),
    ("Risk is a price. Pay it wisely.", "المخاطرة ثمن، فادفعه بحكمة."),
    ("Rise from every loss.", "انهض بعد كل خسارة."),
    ("Slow is smooth, smooth is fast.", "البطء سلاسة، والسلاسة سرعة."),
    ("Greed chases, discipline waits.", "الطمع يلاحق، والانضباط ينتظر."),
    ("Respect the stop, respect yourself.", "احترم وقفك، تحترم نفسك."),
    ("No trade is also a trade.", "عدم الدخول أيضاً قرار."),
    ("Let the market come to you.", "دع السوق يأتي إليك."),
    ("Focus on the process, not the outcome.", "ركّز على العملية لا على النتيجة."),
    ("Good risk management keeps you in the game.", "إدارة المخاطر الجيدة تُبقيك في اللعبة."),
    ("Trade with a plan, rest with peace.", "تداول بخطة، وارتح بسلام."),
    ("Precision over prediction.", "الدقة قبل التوقّع."),
    ("Don't chase. Wait for your price.", "لا تلاحق السعر، انتظر سعرك."),
    ("Review, learn, improve.", "راجع، تعلّم، تطوّر."),
    ("Stay humble, the market is bigger than all of us.", "تواضع، فالسوق أكبر منا جميعاً."),
    ("Emotion is noise. The plan is the signal.", "العاطفة ضجيج، والخطة هي الإشارة."),
    ("Your edge is your routine.", "ميزتك في روتينك."),
    ("Today's discipline is tomorrow's confidence.", "انضباط اليوم هو ثقة الغد."),
]
MORNING_LINES = [
    ("A new day, a new chance. Trade it with a clear head.", "يوم جديد وفرصة جديدة، تداوله بعقل صافي."),
    ("Coffee first, plan second, trades third.", "القهوة أولاً، الخطة ثانياً، والصفقات ثالثاً."),
    ("Today we wait for our price, not for luck.", "اليوم ننتظر سعرنا، مش الحظ."),
    ("Rise like the Phoenix: calm, focused, ready.", "انهض كالعنقاء: هادئ، مركّز، وجاهز."),
    ("Small risk, steady hands, strong week.", "مخاطرة صغيرة، إيد ثابتة، وأسبوع قوي."),
]
CLOSE_LINES = [
    ("The market is closed. Rest well, you earned it.", "السوق سكّر. ارتاح منيح، بتستاهل."),
    ("Green or red, discipline was the win today.", "ربح أو خسارة، الانضباط هو المكسب اليوم."),
    ("Review today, sleep well, come back sharper.", "راجع يومك، نام منيح، وارجع أقوى."),
]
QN = 0   # rotating counter, saved in the state file so phrases never repeat back to back

def quote():
    global QN
    q = QUOTES[QN % len(QUOTES)]
    QN += 1
    return q

def footer():
    en, ar = quote()
    return (f"\n{LINE}\n🕊 <i>“{html.escape(en)}”</i>\n<i>{html.escape(ar)}</i>\n\n"
            "⚠️ <i>Educational only · not financial advice · high risk · prices may differ from your broker.</i>\n"
            "<i>للتعليم فقط · ليست نصيحة مالية · مخاطر عالية · قد تختلف الأسعار عن وسيطك.</i>\n" + SIGN)

def fmt(sym, x):
    return f"{x:,.{INSTRUMENTS[sym]['digits']}f}"

def pips(sym, dist):
    return f"{abs(dist) / INSTRUMENTS[sym]['pip']:,.0f}"

def title(o):
    return f"{ICON.get(o['sym'], '•')} <b>{o['sym']}</b> {INSTRUMENTS[o['sym']]['name']}  ·  ⏱ <b>{o['tf'].upper()}</b>"

def short(o):
    return f"{ICON.get(o['sym'], '•')} {o['sym']} · {o['tf'].upper()} · {o['kind']} @ {fmt(o['sym'], o['trig'])}"

def rr_txt(o):
    return " / ".join(f"1:{r:g}" for r in o["rrs"])

def msg_signal(o, bias_info, price=None):
    sym = o["sym"]
    d = "🟢" if o["dir"] == 1 else "🔴"
    if bias_info["now"] == 0:
        trend = "⚡ Momentum breakout · mixed trend" if o["is_stop"] else "↩️ Reversal zone · mixed trend"
    else:
        trend = "✨ With the trend" if o["with_trend"] else "⚠️ Against the trend"
    rows = []
    if price is not None:
        away = o["trig"] - price
        where = "above" if away > 0 else "below"
        rows.append(f"💰 Price now     <code>{fmt(sym, price)}</code>")
        rows.append(f"🎯 Entry          <code>{fmt(sym, o['trig'])}</code>  · {pips(sym, away)} pips {where}")
    else:
        rows.append(f"🎯 Entry          <code>{fmt(sym, o['trig'])}</code>")
    rows.append(f"🛑 Stop loss     <code>{fmt(sym, o['sl'])}</code>  · −{pips(sym, o['sl'] - o['trig'])} pips")
    for i, (tp, r) in enumerate(zip(o["tps"], o["rrs"]), 1):
        name = "Take profit" if len(o["tps"]) == 1 else f"Target {i}"
        rows.append(f"🏆 {name}  <code>{fmt(sym, tp)}</code>  · +{pips(sym, tp - o['trig'])} pips · 1:{r:g}")
    return (f"🔥 <b>PHOENIX HAZ SMC</b>  ·  <i>New signal · إشارة جديدة</i>\n{LINE}\n"
            f"{title(o)}\n{d} <b>{o['kind']}</b> — {KIND_AR.get(o['kind'], '')}\n{trend}\n\n"
            + "\n".join(rows) +
            f"\n\n📊 Trend <b>{bias_info['txt']}</b>\n      {bias_info['arrows']}\n"
            f"⏳ Pending: waits for price to reach the entry · 1 pip = {INSTRUMENTS[sym]['pip']:g}\n"
            f"💡 <i>Enter a touch early, close a touch before the target.</i>" + footer())

def msg_expired(o, reason, not_triggered):
    head = "🟣 <b>NOT TRIGGERED</b> ✖ · لم يتفعّل" if not_triggered else "⚪ <b>UPDATED</b>"
    return f"{head}\n<i>{html.escape(reason)}</i>\n<s>{html.escape(short(o))}</s>"

def msg_filled(o):
    sym = o["sym"]
    return (f"⚡ <b>ORDER FILLED</b> · تم تفعيل الأمر\n{html.escape(short(o))}\n\n"
            f"🛑 Stop  <code>{fmt(sym, o['sl'])}</code>\n🏆 Target  <code>{fmt(sym, o['tps'][0])}</code>\n\n"
            f"The trade is live. Stick to the plan, no moving the stop back.\n"
            f"الصفقة شغّالة. التزم بالخطة ولا ترجّع الستوب لورا." + footer())

def msg_tp(o, i, final):
    sym, r = o["sym"], o["rrs"][i]
    gain = pips(sym, o["tps"][i] - o["trig"])
    near = pct(o["adv"], o["risk"])
    extra = "" if final else f"\nMove your stop to entry. Next target <code>{fmt(sym, o['tps'][i + 1])}</code>."
    return (f"✅ <b>TARGET HIT</b> · +{r:g}R · +{gain} pips 🎉\nمبروك، ضرب الهدف\n{html.escape(short(o))}{extra}\n\n"
            f"Closest it came to the stop: <b>{near}%</b> of the way." + footer())

def msg_sl(o):
    sym = o["sym"]
    best = pct(o["fav"], abs(o["tps"][0] - o["trig"]))
    return (f"❌ <b>STOP LOSS HIT</b> · −1R · −{pips(sym, o['sl'] - o['trig'])} pips\n"
            f"ضرب وقف الخسارة. خسارة صغيرة ومحسوبة، ومنكمّل بانضباط.\n{html.escape(short(o))}\n\n"
            f"Best it reached toward the target: <b>{best}%</b> of the way." + footer())

def msg_be(o):
    if o.get("hits", 0) > 0:
        best = pct(o["fav"], abs(o["tps"][-1] - o["trig"]))
        return (f"⚖️ <b>STOPPED AT ENTRY</b> · target 1 was already reached ✅\n{html.escape(short(o))}\n\n"
                f"The rest closed at entry. Best toward the last target: <b>{best}%</b>." + footer())
    best = pct(o["fav"], abs(o["tps"][0] - o["trig"]))
    return (f"🛡 <b>PROTECTED EXIT</b> · 0R · طلعت على الدخول بدون خسارة\n{html.escape(short(o))}\n\n"
            f"Price had reached <b>{best}%</b> of the way to the target, so the stop was at entry." + footer())

def msg_protect(o, share):
    return (f"🛡 <b>PROTECT YOUR TRADE</b> · price is <b>{share}%</b> of the way to the target\n"
            f"انقل الستوب على سعر الدخول\n{html.escape(short(o))}\n\n"
            f"Move your stop to entry: from here the trade can not turn into a loss." + footer())

def sel_text(sub):
    s = ", ".join(INSTRUMENTS[x]["name"] for x in sub["syms"]) or "—"
    t = ", ".join(x.upper() for x in sub["tfs"]) or "—"
    return s, t

def msg_menu(sub):
    s, t = sel_text(sub)
    return (f"⚙️ <b>PHOENIX HAZ SMC</b>  ·  <i>Signal settings · الإعدادات</i>\n{LINE}\n"
            "Tap to turn an instrument or timeframe on or off.\n"
            "اضغط على الزر لتفعيل أو إيقاف أي أداة أو فريم.\n\n"
            f"📈 Instruments  <b>{s}</b>\n⏱ Timeframes  <b>{t}</b>\n💼 Lot  <b>{sub['lot']:g}</b>  ·  change it: /lot 0.1\n\n"
            f"💰 /price  ·  📊 /report  ·  🔎 /status  ·  ⏸ /stop\n{SIGN}")

def menu_markup(sub):
    rows = []
    syms = [x for x in AVAILABLE_SYMS if x in INSTRUMENTS]
    for i in range(0, len(syms), 2):
        rows.append([{"text": ("✅ " if x in sub["syms"] else "▫️ ") + ICON.get(x, "") + " " + INSTRUMENTS[x]["name"],
                      "callback_data": "s:" + x} for x in syms[i:i + 2]])
    tfs = AVAILABLE_TFS
    for i in range(0, len(tfs), 3):
        rows.append([{"text": ("✅ " if x in sub["tfs"] else "▫️ ") + x.upper(), "callback_data": "t:" + x} for x in tfs[i:i + 3]])
    rows.append([{"text": "✨ All instruments", "callback_data": "sa"}, {"text": "✨ All timeframes", "callback_data": "ta"}])
    rows.append([{"text": "🧹 Clear", "callback_data": "clr"}, {"text": "📊 Report", "callback_data": "rep"}])
    return {"inline_keyboard": rows}

def msg_welcome(name):
    who = html.escape(name) if name else "trader"
    return (f"🔥 <b>Welcome to PHOENIX HAZ SMC</b>\nأهلاً وسهلاً فيك يا {who} 🤝\n{LINE}\n"
            "Smart-money pending orders on Gold, Silver, Dow, Nasdaq and Oil: entry, stop and target, followed live until the end.\n"
            "إشارات أوامر معلّقة بأسلوب SMC على الذهب والفضة والداو والناسداك والنفط: دخول ووقف وهدف، ومتابعة كل صفقة لآخرها.\n\n"
            "<b>What you get · شو بيوصلك</b>\n"
            "🎯 Every order with the price now, entry, stop and target\n"
            "⚡ Live updates: filled, protect, target, stop\n"
            "☀️ A morning brief and 🌙 a market-close summary\n"
            "📊 /report: today, week and month in pips and $\n\n"
            "<b>How to start · كيف تبلّش</b>\n"
            "1️⃣ Choose instruments and timeframes below · اختار الأدوات والفريمات تحت\n"
            "2️⃣ Set your lot · حدّد اللوت: /lot 0.1\n"
            "3️⃣ Wait for your price, risk 1–2% per trade · انتظر سعرك وخاطر 1–2% بالصفقة\n" + footer())

def msg_price(sub, snap):
    syms = sub["syms"] or list(INSTRUMENTS)
    return (f"💰 <b>PHOENIX HAZ SMC</b>  ·  <i>Prices now · الأسعار هلق</i>\n{LINE}\n" + snapshot_rows(syms, snap) +
            "\n\n<i>Prices from the data feed, they can differ a little from your broker.</i>\n" + SIGN)

def snapshot_rows(syms, snap):
    rows = []
    for sym in syms:
        x = snap.get(sym)
        if not x:
            continue
        ch = f"{x['chg']:+.2f}%" if x.get("chg") is not None else ""
        tr = {1: "▲ BULL", -1: "▼ BEAR"}.get(x.get("trend", 0), "• MIXED")
        rows.append(f"{ICON.get(sym, '•')} <b>{INSTRUMENTS[sym]['name']}</b>  <code>{fmt(sym, x['price'])}</code>  {ch}  ·  {tr}")
    return "\n".join(rows) or "—"

def day_name(dt):
    ar = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"][dt.weekday()]
    return f"{dt.strftime('%A %d %B')} · {ar}"

def msg_morning(sub, snap, dt, lines_i):
    who = html.escape(sub.get("name") or "")
    en, ar = MORNING_LINES[lines_i % len(MORNING_LINES)]
    s, t = sel_text(sub)
    syms = sub["syms"] or list(INSTRUMENTS)
    return (f"☀️ <b>Good morning{', ' + who if who else ''}</b> · صباح الخير\n{LINE}\n"
            f"🗓 {day_name(dt)}\n\n<b>Market now · السوق هلق</b>\n{snapshot_rows(syms, snap)}\n\n"
            f"🎯 Today we follow: <b>{s}</b> · <b>{t}</b>\n"
            f"🛡 Risk 1–2% per trade, wait for your price, protect at 70%.\n\n"
            f"✨ <i>{html.escape(en)}</i>\n<i>{html.escape(ar)}</i>" + footer())

def msg_close(sub, summ, n_signals, weekly, lines_i):
    en, ar = CLOSE_LINES[lines_i % len(CLOSE_LINES)]
    head = "🌙 <b>WEEK CLOSED</b> · سكّر السوق للأسبوع" if weekly else "🌙 <b>MARKET CLOSED</b> · سكّر السوق"
    rows = []
    for name, k in (("Today", "day"), ("Week", "week"), ("Month", "month")):
        o = summ[k]
        rows.append(f"<code>{name:<6} {o['win']}W {o['loss']}L  {o['pips']:+,.0f} pips  {o['usd']:+,.2f}$</code>")
    return (f"{head}\n{LINE}\n📨 Signals today: <b>{n_signals}</b>\n\n" + "\n".join(rows) +
            f"\n\n<i>Lot {sub['lot']:g} · estimates from each plan's target and stop.</i>\n\n"
            f"✨ <i>{html.escape(en)}</i>\n<i>{html.escape(ar)}</i>" + footer())

def msg_report(sub, summ, title="REPORT"):
    s, t = sel_text(sub)
    rows = []
    for name, k in (("Today", "day"), ("Week", "week"), ("Month", "month")):
        o = summ[k]
        rows.append(f"<code>{name:<6} {o['win']}W {o['loss']}L  {o['pips']:+,.0f} pips  {o['usd']:+,.2f}$</code>")
    return (f"📊 <b>PHOENIX HAZ SMC</b>  ·  {title}\n{LINE}\n📈 <b>{s}</b> · ⏱ <b>{t}</b>\n\n" + "\n".join(rows) +
            f"\n\n<i>Lot {sub['lot']:g}. Estimates from each plan's target and stop, not your broker statement.</i>\n"
            f"<i>التقديرات مبنية على هدف ووقف كل خطة وليست كشف حسابك لدى الوسيط.</i>" + footer())

HELP = (f"🔥 <b>PHOENIX HAZ SMC</b>\n{LINE}\n/start · choose instruments and timeframes\n/price · prices now\n"
        "/status · what you receive\n/lot 0.1 · lot size for the money numbers\n/report · today, week, month\n/stop · pause all signals\n\n" + SIGN)

def msg_dayend(o, r, gain_pips):
    s = "+" if r >= 0 else "−"
    return (f"⏹ <b>TIME LIMIT</b> · ≈ {s}{abs(r):.1f}R ({s}{gain_pips} pips)\nالصفقة طوّلت كتير، سكّرها على السوق\n"
            f"{html.escape(short(o))}" + footer())

BOT_COMMANDS = [("start", "Choose instruments and timeframes"), ("price", "Prices now"), ("report", "Today, week, month"),
                ("status", "What you receive"), ("lot", "Lot size, e.g. /lot 0.1"), ("stop", "Pause all signals"), ("help", "Help")]
BOT_DESCRIPTION = ("🔥 PHOENIX HAZ SMC\nSmart-money pending orders for Gold, Silver, Dow, Nasdaq and Oil: price now, entry, stop, "
                   "target and live follow-up. Morning brief and market-close summary.\n"
                   "إشارات أوامر معلّقة على الذهب والفضة والداو والناسداك والنفط مع متابعة مباشرة.\n"
                   "Press START · اضغط START\n⚠️ Educational only, not financial advice.")
BOT_SHORT = "Gold · Silver · Dow · Nasdaq · Oil signals with live follow-up · The Phoenix HAZ Syndicate"

# ───────────────────────────── telegram ─────────────────────────────
class Telegram:
    def __init__(self, token, channel, dry=False):
        self.token, self.channel, self.dry = token, channel, dry
        self.last_chat, self.last_any, self.fake_id = {}, 0.0, 1000

    @staticmethod
    def _is_group(chat):
        c = str(chat)
        return c.startswith("@") or c.startswith("-")

    def _call(self, method, payload, chat=None):
        gap = 3.2 if (chat is not None and self._is_group(chat)) else 1.1
        now = time.time()
        wait = max(self.last_chat.get(str(chat), 0) + (gap if chat is not None else 0) - now, self.last_any + 0.05 - now)
        if wait > 0:
            time.sleep(wait)
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        for _ in range(4):
            try:
                r = requests.post(url, json=payload, timeout=25)
            except requests.RequestException as e:      # never print the URL: it contains the bot token
                log.error("Telegram %s network error (%s)", method, type(e).__name__)
                time.sleep(3); continue
            self.last_any = time.time()
            if chat is not None:
                self.last_chat[str(chat)] = self.last_any
            if r.status_code == 429:
                time.sleep(r.json().get("parameters", {}).get("retry_after", 5) + 1); continue
            if not r.ok:
                if "not modified" not in r.text:
                    log.error("Telegram %s failed: %s", method, r.text[:200])
                return None
            return r.json()["result"]
        return None

    def check(self):
        """Log one clear line about the Telegram setup (token, channel, admin rights)."""
        me = self._call("getMe", {})
        if not me:
            log.error("TELEGRAM CHECK FAILED: the bot token is wrong, or Telegram is unreachable"); return False
        if not self.channel:
            log.info("TELEGRAM CHECK OK: @%s (no channel set: private subscribers only)", me.get("username")); return True
        m = self._call("getChatMember", {"chat_id": self.channel, "user_id": me["id"]})
        if not m:
            log.error("TELEGRAM CHECK FAILED: cannot read channel %s. Use @channelname for TELEGRAM_CHAT_ID and add the bot to the channel", self.channel); return False
        if m.get("status") not in ("administrator", "creator"):
            log.error("TELEGRAM CHECK FAILED: the bot is not an admin of the channel. Add it as admin with permission to post messages"); return False
        if m.get("status") == "administrator" and m.get("can_post_messages") is False:
            log.error("TELEGRAM CHECK FAILED: the bot is admin but cannot post messages. Enable Post messages for it"); return False
        log.info("TELEGRAM CHECK OK: @%s can post to %s", me.get("username"), self.channel)
        return True

    def setup(self):
        """Command menu and the text people see before they press START."""
        self._call("setMyCommands", {"commands": [{"command": c, "description": d} for c, d in BOT_COMMANDS]})
        self._call("setMyDescription", {"description": BOT_DESCRIPTION})
        self._call("setMyShortDescription", {"short_description": BOT_SHORT})

    def send(self, text, chat=None, reply_to=None, markup=None):
        chat = chat if chat is not None else self.channel
        if self.dry:
            self.fake_id += 1
            print(f"\n[DRY-RUN] send #{self.fake_id} to {chat}" + (f" (reply to #{reply_to})" if reply_to else "") + f"\n{text}\n")
            return self.fake_id
        p = {"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
        if reply_to:
            p["reply_to_message_id"] = reply_to
        if markup:
            p["reply_markup"] = markup
        res = self._call("sendMessage", p, chat)
        return res["message_id"] if res else None

    def edit(self, chat, msg_id, text, markup=None):
        if self.dry:
            print(f"\n[DRY-RUN] edit #{msg_id} in {chat}\n{text}\n"); return
        p = {"chat_id": chat, "message_id": msg_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
        if markup:
            p["reply_markup"] = markup
        self._call("editMessageText", p, chat)

    def updates(self, offset):
        return self._call("getUpdates", {"offset": offset, "timeout": 0, "allowed_updates": ["message", "callback_query"]}) or []

    def answer(self, cb_id, text=""):
        self._call("answerCallbackQuery", {"callback_query_id": cb_id, "text": text})

class Broadcaster:
    """Sends each order to the channel (optional) and to every subscriber who chose that symbol and timeframe."""
    def __init__(self, tg, store):
        self.tg, self.store = tg, store

    @property
    def dry(self):
        return getattr(self.tg, "dry", False)

    def targets(self, sym, tf):
        t = [self.tg.channel] if (self.tg.channel and CHANNEL_FEED) else []
        t += [cid for cid, s in self.store.subs.items() if sym in s["syms"] and tf in s["tfs"]]
        return t

    def send_new(self, sym, tf, text):
        msgs = {}
        for cid in self.targets(sym, tf):
            mid = self.tg.send(text, chat=cid)
            if mid:
                msgs[str(cid)] = mid
        return msgs

    def reply(self, o, text):
        for cid, mid in o["msgs"].items():
            self.tg.send(text, chat=cid, reply_to=mid)

    def edit(self, o, text):
        for cid, mid in o["msgs"].items():
            self.tg.edit(cid, mid, text)

# ───────────────────────────── data providers ─────────────────────────────
UA = {"User-Agent": "Mozilla/5.0 (PhoenixHAZ bot)"}

def completed(bars, tf_sec, now):
    return [b for b in bars if b.t + tf_sec <= now]

def fetch_yahoo(sym, tf, now):
    tick = INSTRUMENTS[sym]["yahoo"]
    cfg = {"1m": ("1m", "5d"), "5m": ("5m", "5d"), "15m": ("15m", "10d"), "30m": ("30m", "1mo"),
           "1h": ("60m", "3mo"), "4h": ("60m", "6mo"), "1d": ("1d", "1y")}[tf]
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{tick}?interval={cfg[0]}&range={cfg[1]}&includePrePost=true"
    r = requests.get(url, headers=UA, timeout=20); r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    raw = [Bar(t, o, h, l, c) for t, o, h, l, c in zip(res["timestamp"], q["open"], q["high"], q["low"], q["close"])
           if None not in (o, h, l, c)]
    if tf == "4h":  # resample 1h -> 4h
        buckets = {}
        for b in raw:
            k = b.t // 14400 * 14400
            buckets.setdefault(k, []).append(b)
        raw = [Bar(k, v[0].o, max(x.h for x in v), min(x.l for x in v), v[-1].c) for k, v in sorted(buckets.items())]
        return completed(raw, 14400, now)
    sec = 86400 if tf == "1d" else TF_SEC.get(tf, 3600)
    return completed(raw, sec, now)

def fetch_oanda(sym, tf, now):
    base = "https://api-fxtrade.oanda.com" if ENV("OANDA_ENV", "practice") == "live" else "https://api-fxpractice.oanda.com"
    gran = {"1m": "M1", "5m": "M5", "15m": "M15", "30m": "M30", "1h": "H1", "4h": "H4", "1d": "D"}[tf]
    url = (f"{base}/v3/instruments/{INSTRUMENTS[sym]['oanda']}/candles?granularity={gran}&count=500&price=M"
           f"&dailyAlignment=17&alignmentTimezone=America%2FNew_York")
    r = requests.get(url, headers={"Authorization": f"Bearer {ENV('OANDA_TOKEN', '')}"}, timeout=20)
    r.raise_for_status()
    out = []
    for c in r.json()["candles"]:
        if not c.get("complete"):
            continue
        t = int(datetime.fromisoformat(c["time"][:19] + "+00:00").timestamp())
        m = c["mid"]
        out.append(Bar(t, float(m["o"]), float(m["h"]), float(m["l"]), float(m["c"])))
    return out

# ── price alignment ──
# Yahoo gives FUTURES prices (YM=F, NQ=F, GC=F...). Brokers and TradingView "cash" charts trade a little
# below or above them (the futures basis, e.g. about 250 points on the Dow). Every price the bot uses is
# shifted by OFFSETS[sym] so entries, stops and targets match the chart. Indices calibrate themselves
# against the cash index (^DJI, ^NDX) during US hours; any symbol can be calibrated by hand from Telegram
# with /calibrate XAUUSD 4105.2 (the price your chart shows now), or with OFFSET_XAUUSD=-25 in the settings.
OFFSETS = {s: float(ENV("OFFSET_" + s, "0") or 0) for s in INSTRUMENTS}

def use_offsets():
    return ENV("DATA_PROVIDER", "yahoo").lower() != "oanda"

def get_candles(sym, tf, now, raw=False):
    bars = (fetch_oanda if not use_offsets() else fetch_yahoo)(sym, tf, now)
    off = 0.0 if raw or not use_offsets() else OFFSETS.get(sym, 0.0)
    return [Bar(b.t, b.o + off, b.h + off, b.l + off, b.c + off) for b in bars] if off else bars

def fetch_ref(sym, now):
    """1-minute bars of the cash index the CFD follows (None when the symbol has no reference)."""
    tick = INSTRUMENTS[sym].get("ref")
    if not tick:
        return None
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{tick}?interval=1m&range=1d"
    r = requests.get(url, headers=UA, timeout=20); r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    return [Bar(t, o, h, l, c) for t, o, h, l, c in zip(res.get("timestamp", []), q["open"], q["high"], q["low"], q["close"])
            if None not in (o, h, l, c) and t + 60 <= now]

# ───────────────────────────── engine ─────────────────────────────
class Engine:
    def __init__(self, tg=None, bc=None):
        self.tg = tg
        self.bc = bc or Broadcaster(tg, self)
        self.orders, self.pairs, self.sent = [], {}, {}
        self.subs, self.ledger, self.meta = {}, [], {}
        self.snap_fn = None                      # set by run(): returns current prices for a list of symbols
        self.stats = {"built": 0, "rr_skip": 0, "dist_skip": 0, "unreal": 0, "capped": 0, "cool": 0, "spike": 0, "why": {}}
        self.load()

    # ── state
    def load(self):
        global QN
        if os.path.exists(STATE_FILE):
            try:
                d = json.load(open(STATE_FILE, encoding="utf-8"))
                self.pairs, self.sent, QN = d.get("pairs", {}), d.get("sent", {}), d.get("q", 0)
                self.subs, self.ledger, self.meta = d.get("subs", {}), d.get("ledger", []), d.get("meta", {})
                for sym, x in self.meta.get("offsets", {}).items():
                    if sym in OFFSETS and "v" in x:
                        OFFSETS[sym] = x["v"]
                for o in d.get("orders", []):
                    o.setdefault("inval", o.get("sl"))
                self.orders = [o for o in d.get("orders", []) if "tps" in o and
                               (o.get("msgs") or o["state"] not in (PENDING, OPEN))]
            except Exception as e:
                log.warning("state not loaded: %s", e)

    def save(self):
        if getattr(self.bc, "dry", False):          # a dry run must never write state (fake message ids)
            return
        tmp = STATE_FILE + ".tmp"
        json.dump({"orders": self.orders[-400:], "pairs": self.pairs, "q": QN, "subs": self.subs, "ledger": self.ledger,
                   "meta": self.meta, "sent": dict(sorted(self.sent.items())[-3:])}, open(tmp, "w", encoding="utf-8"))
        os.replace(tmp, STATE_FILE)

    def set_offset(self, sym, value, src):
        """Store a new price offset and move the open and waiting orders of that symbol with it."""
        old = OFFSETS.get(sym, 0.0)
        delta = value - old
        OFFSETS[sym] = value
        self.meta.setdefault("offsets", {})[sym] = {"v": value, "src": src, "t": int(time.time())}
        if abs(delta) > 0:
            for o in self.orders:
                if o["sym"] == sym and o["state"] in (PENDING, OPEN):
                    for k in ("lo", "hi", "trig", "entry", "sl", "inval"):
                        if k in o:
                            o[k] += delta
                    o["tps"] = [x + delta for x in o["tps"]]
        log.info("offset %s = %+.3f (%s)", sym, value, src)

    def auto_offsets(self, syms, now):
        """Indices: offset = cash index - futures, measured on the same closed minute during US hours."""
        if not use_offsets():
            return
        for sym in syms:
            if not INSTRUMENTS[sym].get("ref"):
                continue
            last = self.meta.get("offsets", {}).get(sym, {})
            if now - last.get("checked", 0) < 1800:
                continue
            self.meta.setdefault("offsets", {}).setdefault(sym, {})["checked"] = now
            try:
                ref = {b.t: b.c for b in (fetch_ref(sym, now) or [])}
                fut = get_candles(sym, "1m", now, raw=True)
                common = [b for b in fut[-60:] if b.t in ref]
                if common:
                    b = common[-1]
                    self.set_offset(sym, round(ref[b.t] - b.c, 2), "auto")
                    self.meta["offsets"][sym]["checked"] = now
            except Exception as e:
                log.warning("auto offset %s: %s", sym, e)

    def pair(self, sym, tf):
        return self.pairs.setdefault(f"{sym}|{tf}", {"last_t": 0, "day": "", "last_slot": -1, "seq": 0, "sent": 0})

    # ── helpers
    def say(self, o, text):
        if SEND_UPDATES and o.get("msgs"):
            self.bc.reply(o, text)

    def expire(self, o, reason, not_triggered=True):
        o["state"] = CANCELLED
        if o.get("msgs"):
            self.bc.edit(o, msg_expired(o, reason, not_triggered))

    def why(self, text):
        self.stats["unreal"] += 1
        self.stats["why"][text] = self.stats["why"].get(text, 0) + 1

    def book(self, o, bar, exit_px=None):
        self.ledger.append({"t": bar.t, "td": trading_day(bar.t).isoformat(), "sym": o["sym"], "tf": o["tf"],
                            "dist": realized(o, exit_px)})
        cutoff = bar.t - 100 * 86400
        self.ledger = [e for e in self.ledger if e["t"] > cutoff]

    def _hits(self, o, bar, d):
        while o["state"] == OPEN and o["hits"] < len(o["tps"]) and (
                (d == 1 and bar.h >= o["tps"][o["hits"]]) or (d == -1 and bar.l <= o["tps"][o["hits"]])):
            i = o["hits"]; o["hits"] += 1
            final = o["hits"] == len(o["tps"])
            if final:
                o["state"] = TP_HIT
                self.book(o, bar)
            else:
                o["be"] = True
            self.say(o, msg_tp(o, i, final))

    # ── one completed bar
    def process_bar(self, sym, tf, bars, bias_info, is_latest):
        bar, ps = bars[-1], self.pair(sym, tf)
        by_tf = bias_info.get("by_tf", {})
        bias_info = dict(bias_info, now=by_tf.get(tf, bias_info["now"]), txt=bias_info.get("txt_by_tf", {}).get(tf, bias_info["txt"]))
        mins, day = ny_parts(bar.t)
        tick = INSTRUMENTS[sym]["tick"]
        mine = [o for o in self.orders if o["sym"] == sym and o["tf"] == tf and o["state"] in (PENDING, OPEN)]

        if ps["day"] != day:                                         # new New-York day
            ps.update(day=day, last_slot=-1, sent=0)

        # 1) manage orders (wicks count: a touch of the target or the stop is enough)
        for o in mine:
            d = o["dir"]
            if o["state"] == PENDING:
                filled = (bar.h >= o["lo"] if o["is_stop"] else bar.l <= o["hi"]) if d == 1 else \
                         (bar.l <= o["hi"] if o["is_stop"] else bar.h >= o["lo"])
                if filled:
                    o.update(state=OPEN, fill_t=bar.t, fav=0.0, adv=0.0, hits=0, be=False)
                    for q in mine:
                        if q is not o and q["plan"] == o["plan"] and q["state"] == PENDING:
                            self.expire(q, "another order of this plan was filled")
                    self.say(o, msg_filled(o))
                    # a breakout order must have crossed its entry to reach the target, so count a same-bar target
                    # (unless the stop was touched in that bar too: the order of events is unknown, so stay careful)
                    sl_touch = (d == 1 and bar.l <= o["sl"]) or (d == -1 and bar.h >= o["sl"])
                    if o["is_stop"] and not sl_touch:
                        self._hits(o, bar, d)
            elif o["state"] == OPEN and bar.t > o.get("fill_t", 0):
                trig = o["trig"]
                fav = (bar.h - trig) if d == 1 else (trig - bar.l)
                adv = (trig - bar.l) if d == 1 else (bar.h - trig)
                stop = trig if o["be"] else o["sl"]
                if (d == 1 and bar.l <= stop) or (d == -1 and bar.h >= stop):
                    o["state"] = BE_HIT if o["be"] else SL_HIT
                    if not o["be"]:
                        ps.setdefault("cool", {})[str(d)] = bar.t + COOLDOWN_MIN * 60
                    self.book(o, bar)
                    self.say(o, msg_be(o) if o["be"] else msg_sl(o))
                else:
                    o["fav"], o["adv"] = max(o["fav"], fav), max(o["adv"], adv)
                    self._hits(o, bar, d)
                    if o["state"] == OPEN and not o["be"] and BE_AT_R > 0 and o["fav"] >= BE_AT_R * o["risk"]:
                        o["be"] = True                                # protect: stop moves to entry
                        self.say(o, msg_protect(o, pct(o["fav"], abs(o["tps"][0] - trig))))

        # 2) housekeeping: nothing is closed at the end of the session; only very old orders are dropped
        for o in self.orders:
            if o["sym"] == sym and o["tf"] == tf:
                age_h = (bar.t - o["born_t"]) / 3600.0
                if o["state"] == PENDING and age_h > PENDING_MAX_HOURS:
                    self.expire(o, "never triggered, too old")
                elif o["state"] == OPEN and age_h > OPEN_MAX_HOURS:
                    o["state"] = DAY_END
                    self.book(o, bar, bar.c)
                    r = (bar.c - o["trig"]) * o["dir"] / max(o["risk"], 1e-9)
                    self.say(o, msg_dayend(o, r, pips(sym, bar.c - o["trig"])))

        # 3) re-check ONLY the unfilled orders. A pending order stays while its zone is still valid,
        #    so when the market comes back to test the same zone the order is still there.
        atr = calc_atr(bars)
        in_win = PLAN_START <= mins < PLAN_END
        eff = max(REFRESH_MIN, TF_SEC[tf] / 60.0)
        slot = int((mins - PLAN_START) // eff) if in_win else -1
        spike = bool(atr) and (bar.h - bar.l) > SPIKE_ATR * atr
        if spike and is_latest and in_win:
            self.stats["spike"] += 1                                # news-size candle: wait for the next bar
        elif is_latest and in_win and atr and len(bars) > RANGE_BARS:
            prune_now = slot != ps["last_slot"]
            if prune_now:
                ps["last_slot"] = slot
            live = [o for o in self.orders if o["sym"] == sym and o["tf"] == tf and o["state"] in (PENDING, OPEN)]
            if prune_now:                                           # re-check unfilled orders only
                for p in [o for o in live if o["state"] == PENDING]:
                    d = p["dir"]
                    if (d == 1 and bar.c < p["inval"]) or (d == -1 and bar.c > p["inval"]):
                        self.expire(p, "price closed beyond its invalidation level")
                    elif bias_info["now"] == -d:
                        self.expire(p, "the trend turned against it")
                    elif abs(p["trig"] - bar.c) > STICKY_MAX_ATR * atr:
                        self.expire(p, "price moved far away")
            pend = [o for o in live if o["state"] == PENDING]
            have = {p["kind"] for p in pend}
            open_dirs = {o["dir"] for o in live if o["state"] == OPEN}
            win = bars[-RANGE_BARS:]
            hi, lo = max(b.h for b in win), min(b.l for b in win)
            if hi - lo >= atr and self.bc.targets(sym, tf):
                ema_dir, mom_dir = local_dirs(bars, atr)
                fake_up, fake_dn = sweep_flags(bars)
                built = build_orders(atr, hi, lo, bar.c, bias_info["now"], tick, RR[tf], ema_dir, mom_dir, fake_up, fake_dn)
                self.stats["built"] += len(built)
                add = []
                for n in built:
                    if n["kind"] in have or n["dir"] in open_dirs:
                        continue                                    # already waiting, or a trade this way is open
                    if n["rrs"][0] < MIN_RR:
                        self.stats["rr_skip"] += 1
                    elif ps.get("cool", {}).get(str(n["dir"]), 0) > bar.t:
                        self.stats["cool"] += 1
                    elif abs(n["trig"] - bar.c) > MAX_DIST_ATR * atr:
                        self.stats["dist_skip"] += 1
                    else:
                        why = unrealistic(n, atr, bias_info.get("datr"), mins, tf)
                        if why:
                            self.why(why)
                        else:
                            add.append(n)
                if add:
                    ps["seq"] += 1
                    for n in add:
                        if ps.get("sent", 0) >= MAX_PER_PAIR_DAY or self.sent.get(day, 0) >= MAX_SIGNALS_PER_DAY:
                            self.stats["capped"] += 1
                            continue
                        n.update(sym=sym, tf=tf, plan=f"{sym}{tf}{ps['seq']}", state=PENDING, born_t=bar.t, fill_t=0,
                                 fav=0.0, adv=0.0, hits=0, be=False)
                        msgs = self.bc.send_new(sym, tf, msg_signal(n, bias_info, bar.c))
                        if not msgs:                                  # Telegram refused: forget it and retry on the next bar
                            continue
                        n["msgs"] = msgs
                        ps["sent"] = ps.get("sent", 0) + 1
                        self.sent[day] = self.sent.get(day, 0) + 1
                        self.orders.append(n)

        ps["last_t"] = bar.t
        self.orders = [o for o in self.orders if o["state"] in (PENDING, OPEN) or o["born_t"] > bar.t - 3 * 86400]

    # ── subscribers: every user chooses what he receives
    def sub_of(self, chat, name=""):
        return self.subs.setdefault(str(chat), {"syms": [], "tfs": [], "lot": LOT_DEFAULT, "name": name})

    def send_report(self, chat, sub, title="REPORT"):
        summ = summarize(self.ledger, sub["syms"], sub["tfs"], sub["lot"], time.time())
        self.tg.send(msg_report(sub, summ, title), chat=chat)

    def handle_update(self, u):
        if "callback_query" in u:
            return self._callback(u["callback_query"])
        m = u.get("message") or {}
        chat = m.get("chat", {})
        if chat.get("type") != "private" or "text" not in m:
            return
        cid = chat["id"]
        is_new = str(cid) not in self.subs
        sub = self.sub_of(cid, m.get("from", {}).get("first_name", ""))
        cmd, _, arg = m["text"].strip().partition(" ")
        cmd = cmd.split("@")[0].lower()
        if not self.meta.get("owner") and not ENV("ADMIN_ID", ""):
            self.meta["owner"] = next(iter(self.subs), str(cid))
        if cmd in ("/start", "/menu", "/settings"):
            if is_new or not sub.get("welcomed"):
                self.tg.send(msg_welcome(sub.get("name", "")), chat=cid)
                sub["welcomed"] = True
            self.tg.send(msg_menu(sub), chat=cid, markup=menu_markup(sub))
        elif cmd == "/calibrate":
            owner = str(ENV("ADMIN_ID", "") or self.meta.get("owner") or next(iter(self.subs), ""))
            if str(cid) != owner:
                self.tg.send("Only the bot owner can calibrate prices.", chat=cid)
                return
            self.meta["owner"] = owner
            parts = arg.replace(",", "").split()
            sym = parts[0].upper() if parts else ""
            if sym in ("GOLD",): sym = "XAUUSD"
            if sym in ("SILVER",): sym = "XAGUSD"
            if sym in ("DOW", "WALLSTREET", "DJ30"): sym = "US30"
            if sym in ("NASDAQ", "NAS", "USTEC", "NDX"): sym = "NAS100"
            if sym in ("OIL", "WTI", "USOUSD"): sym = "USOIL"
            try:
                chart = float(parts[1])
                if sym not in INSTRUMENTS:
                    raise ValueError
                feed = get_candles(sym, "1m", int(time.time()), raw=True)[-1].c
                self.set_offset(sym, round(chart - feed, 4), "manual")
                self.tg.send(f"✅ <b>{sym}</b> calibrated. Feed <code>{fmt(sym, feed)}</code> → your chart <code>{fmt(sym, chart)}</code>"
                             f" (offset {chart - feed:+.2f}). All {sym} prices now match your chart.", chat=cid)
            except (ValueError, IndexError):
                self.tg.send("Write the price your chart shows now, like this:\n<code>/calibrate XAUUSD 4105.2</code>\n"
                             "<code>/calibrate US30 52350</code>", chat=cid)
            except Exception as e:
                self.tg.send(f"Could not read the feed price now ({type(e).__name__}). Try again in a minute.", chat=cid)
        elif cmd == "/price":
            snap = self.snap_fn(sub["syms"] or list(INSTRUMENTS)) if self.snap_fn else {}
            self.tg.send(msg_price(sub, snap), chat=cid)
        elif cmd == "/status":
            self.tg.send(msg_menu(sub), chat=cid)
        elif cmd == "/lot":
            try:
                v = float(arg.replace(",", "."))
                if not 0.001 <= v <= 1000:
                    raise ValueError
                sub["lot"] = v
                self.tg.send(f"Lot size set to <b>{v:g}</b>. This changes the money numbers in your reports.", chat=cid)
            except ValueError:
                self.tg.send("Write it like this: <code>/lot 0.1</code>", chat=cid)
        elif cmd == "/report":
            self.send_report(cid, sub)
        elif cmd == "/stop":
            sub["syms"], sub["tfs"] = [], []
            self.tg.send("Signals stopped. Send /start any time to choose again.\nتم إيقاف الإشارات. أرسل /start لتختار من جديد.", chat=cid)
        else:
            self.tg.send(HELP, chat=cid)

    def _callback(self, cq):
        msg = cq.get("message") or {}
        cid, mid = msg.get("chat", {}).get("id"), msg.get("message_id")
        if cid is None:
            return
        sub, data = self.sub_of(cid), cq.get("data", "")
        if data.startswith("s:") and data[2:] in INSTRUMENTS:
            (sub["syms"].remove if data[2:] in sub["syms"] else sub["syms"].append)(data[2:])
        elif data.startswith("t:") and data[2:] in TF_SEC:
            (sub["tfs"].remove if data[2:] in sub["tfs"] else sub["tfs"].append)(data[2:])
        elif data == "sa":
            sub["syms"] = [x for x in AVAILABLE_SYMS if x in INSTRUMENTS]
        elif data == "ta":
            sub["tfs"] = list(AVAILABLE_TFS)
        elif data == "clr":
            sub["syms"], sub["tfs"] = [], []
        elif data == "rep":
            self.send_report(cid, sub)
        self.tg.answer(cq["id"])
        self.tg.edit(cid, mid, msg_menu(sub), markup=menu_markup(sub))

    def poll(self):
        if getattr(self.bc, "dry", False) or self.tg is None:
            return
        ups = self.tg.updates(self.meta.get("offset", 0))
        for u in ups:
            self.meta["offset"] = u["update_id"] + 1
            try:
                self.handle_update(u)
            except Exception as e:
                log.warning("update failed: %s", e)
        if ups:
            self.save()

    def _broadcast_daily(self, build):
        """Send a message to the channel (if any) and to every active subscriber."""
        if self.tg is not None and self.tg.channel and CHANNEL_FEED:
            chan = {"syms": list(AVAILABLE_SYMS), "tfs": list(AVAILABLE_TFS), "lot": LOT_DEFAULT, "name": ""}
            self.tg.send(build(chan), chat=self.tg.channel)
        for cid, sub in list(self.subs.items()):
            if sub["syms"] and sub["tfs"]:
                self.tg.send(build(sub), chat=cid)

    def daily_messages(self, now):
        """Morning brief (Mon-Fri, MORNING_HOUR local) and market-close summary (Mon-Fri, REPORT_HOUR:05 New York)."""
        if not DAILY_MSGS or self.tg is None or getattr(self.bc, "dry", False):
            return
        loc = datetime.fromtimestamp(now, MSG_TZ)
        m = loc.hour * 60 + loc.minute
        key = loc.strftime("%Y-%m-%d")
        if loc.weekday() < 5 and MORNING_HOUR * 60 <= m < MORNING_HOUR * 60 + 180 and self.meta.get("morning") != key:
            self.meta["morning"] = key
            syms = sorted({x for s in self.subs.values() for x in s["syms"]} | (set(AVAILABLE_SYMS) if self.tg.channel else set()))
            snap = self.snap_fn(syms) if (self.snap_fn and syms) else {}
            i = loc.toordinal()
            self._broadcast_daily(lambda sub: msg_morning(sub, snap, loc, i))
            self.save()
        ny = datetime.fromtimestamp(now, TZ)
        m = ny.hour * 60 + ny.minute
        key = ny.strftime("%Y-%m-%d")
        if ny.weekday() < 5 and REPORT_HOUR * 60 + 5 <= m < REPORT_HOUR * 60 + 180 and self.meta.get("close") != key:
            self.meta["close"] = key
            weekly, i = ny.weekday() == 4, ny.toordinal()
            n_sig = self.sent.get(key, 0)
            self._broadcast_daily(lambda sub: msg_close(sub, summarize(self.ledger, sub["syms"], sub["tfs"], sub["lot"], now),
                                                        n_sig, weekly, i))
            self.save()

# ───────────────────────────── live loop ─────────────────────────────
def bias_info_for(sym, now, cache):
    c = cache.get(sym)
    if c and now - c["ts"] < 600:
        return c
    bs, datr = {}, None
    for tf in ("1d", "4h", "1h", "15m"):
        try:
            bars_tf = get_candles(sym, tf, now)
            bs[tf] = bias_from_bars(bars_tf)
            if tf == "1d":
                datr = calc_atr(bars_tf)
        except Exception as e:
            log.warning("bias %s %s: %s", sym, tf, e); bs[tf] = 0
    def maj(*v):
        t = sum(v)
        return 1 if t >= 2 else -1 if t <= -2 else 0
    fast = bs["1h"] if bs["1h"] == bs["15m"] else 0
    by_tf = {"1m": fast, "5m": fast, "15m": maj(bs["4h"], bs["1h"], bs["15m"]), "30m": maj(bs["4h"], bs["1h"], bs["15m"]),
             "1h": maj(bs["1d"], bs["4h"], bs["1h"])}
    word = lambda v: "BULL" if v == 1 else "BEAR" if v == -1 else "MIXED"
    txt_by_tf = {"1m": word(fast) + " (1H+15M)", "5m": word(fast) + " (1H+15M)", "15m": word(by_tf["15m"]) + " (4H+1H+15M)",
                 "30m": word(by_tf["30m"]) + " (4H+1H+15M)", "1h": word(by_tf["1h"]) + " (D+4H+1H)"}
    bull = sum(1 for v in bs.values() if v == 1); bear = sum(1 for v in bs.values() if v == -1)
    now_b = 1 if bull > bear else -1 if bear > bull else 0
    txt = ("BULL" if now_b == 1 else "BEAR" if now_b == -1 else "MIXED") + f" {max(bull, bear)}/4"
    info = dict(ts=now, now=now_b, txt=txt, datr=datr, by_tf=by_tf, txt_by_tf=txt_by_tf,
                arrows=f"D{arrow(bs['1d'])} 4H{arrow(bs['4h'])} 1H{arrow(bs['1h'])} 15{arrow(bs['15m'])}")
    cache[sym] = info
    return info

def snapshot(syms, now, cache):
    """Current price, change since the last daily close, and the 1H-level trend for each symbol."""
    out = {}
    for sym in syms:
        try:
            b1 = get_candles(sym, "1m", now)                 # last closed 1-minute bar = price now
            d1 = get_candles(sym, "1d", now)
            price = b1[-1].c
            prev = d1[-1].c if d1 else None
            info = bias_info_for(sym, now, cache)
            out[sym] = {"price": price, "chg": (price / prev - 1) * 100 if prev else None,
                        "trend": info.get("by_tf", {}).get("1h", info.get("now", 0))}
        except Exception as e:
            log.warning("snapshot %s: %s", sym, e)
    return out

def watch_pairs(eng, symbols, tfs):
    pairs = set()
    if eng.tg is not None and eng.tg.channel and CHANNEL_FEED:
        pairs |= {(x, t) for x in symbols for t in tfs}
    for sub in eng.subs.values():
        pairs |= {(x, t) for x in sub["syms"] for t in sub["tfs"] if x in symbols and t in tfs}
    return sorted(pairs)

def run(symbols, tfs, tg, once=False, minutes=0):
    eng, cache, nxt = Engine(tg), {}, {}
    log.info("Phoenix HAZ bot running: %s | %s | provider=%s", ",".join(symbols), ",".join(tfs), ENV("DATA_PROVIDER", "yahoo"))
    eng.snap_fn = lambda syms: snapshot(syms, int(time.time()), cache)
    if not tg.dry:
        tg.setup()
    if not tg.dry and not tg.check() and tg.channel:
        log.warning("Channel disabled for this run: signals go to private subscribers only (fix TELEGRAM_CHAT_ID or remove it)")
        tg.channel = ""
    end = time.time() + minutes * 60 if minutes else None
    while True:
        now = int(time.time())
        eng.poll()                                          # users choosing their signals
        eng.daily_messages(now)
        eng.auto_offsets(sorted({x for x, _ in watch_pairs(eng, symbols, tfs)}), now)
        for sym, tf in watch_pairs(eng, symbols, tfs):
            key = f"{sym}|{tf}"
            if now < nxt.get(key, 0):
                continue
            try:
                bars = get_candles(sym, tf, now)
                ps = eng.pair(sym, tf)
                new = [i for i, b in enumerate(bars) if b.t > ps["last_t"]]
                if ps["last_t"] == 0 and new:
                    new = new[-1:]                                  # first run: only the latest bar
                if new:
                    info = bias_info_for(sym, now, cache)
                    for i in new:
                        eng.process_bar(sym, tf, bars[:i + 1], info, is_latest=(i == len(bars) - 1))
                    eng.save()
                last = bars[-1].t if bars else now
                nxt[key] = max(last + 2 * TF_SEC[tf] + 3, now + 20)
            except Exception as e:
                log.warning("%s: %s", key, e)
                nxt[key] = now + 30
        if once or (end and time.time() >= end):
            eng.save()
            log.info("Run finished, state saved")
            return
        time.sleep(5)

class FakeBC:
    dry = False
    def __init__(self): self.n, self.log = 0, []
    def targets(self, sym, tf): return [1]
    def send_new(self, sym, tf, text):
        self.n += 1; self.log.append(("new", text)); return {"1": self.n}
    def reply(self, o, text): self.log.append(("reply", text))
    def edit(self, o, text): self.log.append(("edit", text))

# ───────────────────────────── offline self-test ─────────────────────────────
def selftest():
    fb = FakeBC()
    rnd = random.Random(11)
    start = int(datetime(2026, 10, 5, 0, 0, tzinfo=TZ).timestamp())
    price, bars = 4100.0, []
    for i in range(288 * 4):                                           # 4 days of 5m bars
        t = start + i * 300
        drift = rnd.uniform(-0.6, 0.6) + (1.2 if (i // 288) == 1 else -0.4 if (i // 288) == 0 else 0)
        o = price; c = o + drift + rnd.gauss(0, 1.6)
        bars.append(Bar(t, o, max(o, c) + abs(rnd.gauss(0, 1.1)), min(o, c) - abs(rnd.gauss(0, 1.1)), c)); price = c
    global STATE_FILE
    STATE_FILE = os.path.join(HERE, "selftest_state.json")
    if os.path.exists(STATE_FILE): os.remove(STATE_FILE)
    eng = Engine(bc=fb)
    for i in range(60, len(bars)):
        day_idx = (bars[i].t - start) // 86400
        b = [-1, 1, 0, -1][day_idx]
        info = dict(now=b, txt={1: "BULL 3/4", -1: "BEAR 3/4", 0: "MIXED 2/4"}[b], arrows="D▼ 4H▼ 1H▼ 15•")
        eng.process_bar("XAUUSD", "5m", bars[max(0, i - 300):i + 1], info, is_latest=True)
    kinds = {}
    for k, t in fb.log:
        key = k + ":" + next((w for w in ("New signal", "FILLED", "TARGET", "STOP LOSS HIT", "PROTECT", "NOT TRIGGERED", "UPDATED") if w in t), "?")
        kinds[key] = kinds.get(key, 0) + 1
    print("messages by type:", json.dumps(kinds, indent=1))
    print("ledger entries:", len(eng.ledger))
    first = next(t for k, t in fb.log if k == "new")
    print("\n--- sample signal ---\n" + strip_tags(first))
    if os.path.exists(STATE_FILE): os.remove(STATE_FILE)


def strip_tags(t):
    import re
    return re.sub(r"<[^>]+>", "", t)

def resample(bars, sec):
    out, cur, k = [], [], None
    for b in bars:
        kk = b.t // sec * sec
        if kk != k and cur:
            out.append(Bar(k, cur[0].o, max(x.h for x in cur), min(x.l for x in cur), cur[-1].c)); cur = []
        k = kk; cur.append(b)
    if cur:
        out.append(Bar(k, cur[0].o, max(x.h for x in cur), min(x.l for x in cur), cur[-1].c))
    return out

def simulate():
    """Offline run of every symbol on every timeframe with simulated prices (tests the mechanics only)."""
    global STATE_FILE
    STATE_FILE = os.path.join(HERE, "sim_state.json")
    rnd = random.Random(21)
    base = {"XAUUSD": (4100.0, 0.55), "XAGUSD": (55.0, 0.016), "US30": (45000.0, 6.0),
            "NAS100": (21000.0, 3.5), "USOIL": (70.0, 0.03)}
    start, days = int(datetime(2026, 10, 5, 0, 0, tzinfo=TZ).timestamp()), 4
    samples, rows, why_all = {}, [], {}
    for si, (sym, (p0, vol)) in enumerate(base.items()):
        price, one = p0, []
        for i in range(1440 * days):
            reg = (i // 1440 + si) % 3
            drift = vol * 0.04 * (1 if reg == 0 else -1 if reg == 1 else 0)
            o = price; c = o + drift + rnd.gauss(0, vol)
            one.append(Bar(start + i * 60, o, max(o, c) + abs(rnd.gauss(0, vol * .5)), min(o, c) - abs(rnd.gauss(0, vol * .5)), c)); price = c
        daily = resample(one, 86400)
        datr = sum(b.h - b.l for b in daily) / len(daily)
        for tf, sec in TF_SEC.items():
            bars = one if tf == "1m" else resample(one, sec)
            if os.path.exists(STATE_FILE): os.remove(STATE_FILE)
            fk = FakeBC(); eng = Engine(bc=fk)
            for i in range(60, len(bars)):
                b = [-1, 1, 0][((bars[i].t - start) // 86400 + si) % 3]
                info = dict(now=b, txt={1: "BULL 3/4", -1: "BEAR 3/4", 0: "MIXED 2/4"}[b], datr=datr,
                            arrows="D" + arrow(b) + " 4H" + arrow(b) + " 1H" + arrow(b) + " 15•")
                eng.process_bar(sym, tf, bars[max(0, i - 300):i + 1], info, is_latest=True)
            cnt = dict(new=0, fill=0, tp=0, sl=0, be=0, nt=0)
            for k, t in fk.log:
                if k == "new": cnt["new"] += 1
                elif k == "edit":
                    if "NOT TRIGGERED" in t: cnt["nt"] += 1
                else:
                    if "FILLED" in t: cnt["fill"] += 1
                    if "TARGET" in t and "HIT" in t: cnt["tp"] += 1
                    if "STOP LOSS HIT" in t: cnt["sl"] += 1
                    if "STOPPED AT ENTRY" in t: cnt["be"] += 1
                key = k + "|" + next((w for w in ("New signal", "FILLED", "TARGET HIT", "STOP LOSS HIT", "STOPPED AT ENTRY", "PROTECTED EXIT", "PROTECT", "TIME LIMIT", "NOT TRIGGERED", "UPDATED") if w in t), "?")
                samples.setdefault(key, strip_tags(t))
            for w, n in eng.stats["why"].items():
                why_all[w] = why_all.get(w, 0) + n
            rows.append((sym, tf, cnt, dict(eng.stats)))
    print(f"{'symbol':8}{'tf':5}{'signals':>8}{'filled':>7}{'target':>7}{'stop':>6}{'be':>4}{'notTrig':>8}   filtered: R | far | unrealistic | cap   (built)")
    tot = 0
    for sym, tf, c, st in rows:
        tot += c["new"]
        print(f"{sym:8}{tf:5}{c['new']:>8}{c['fill']:>7}{c['tp']:>7}{c['sl']:>6}{c['be']:>4}{c['nt']:>8}   {st['rr_skip']} | {st['dist_skip']} | {st['unreal']} | {st['capped']}   ({st['built']})")
    print(f"\nTOTAL signals over {days} simulated days: {tot}  (~{tot / days:.0f} per day for 5 symbols x 5 timeframes)")
    print("why orders were filtered as unrealistic:")
    for w, n in sorted(why_all.items(), key=lambda x: -x[1]):
        print(f"  {n:5}  {w}")
    out = os.path.join(HERE, "sample_messages.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write("SIMULATED DATA - samples of every message type\n\n")
        for k, t in samples.items():
            f.write(f"##### {k}\n{t}\n\n")
    if os.path.exists(STATE_FILE): os.remove(STATE_FILE)
    print("samples written to", out)

# ───────────────────────────── entry ─────────────────────────────
def clean_token(t):
    """Accept a token pasted with spaces, quotes, new lines or a 'bot' prefix."""
    t = "".join(t.split()).strip("'\"")
    if t.lower().startswith("bot") and ":" in t:
        t = t[3:]
    return t

def clean_chat(c):
    """Accept @name, name, t.me/name links or a numeric id (-100...)."""
    c = "".join(c.split()).strip("'\"")
    if not c:
        return ""
    for pre in ("https://t.me/", "http://t.me/", "t.me/", "https://telegram.me/", "telegram.me/"):
        if c.lower().startswith(pre):
            c = c[len(pre):]
            break
    c = c.split("?")[0].strip("/")
    if c.lstrip("-").isdigit():
        return c
    return c if c.startswith("@") else "@" + c

def main():
    global AVAILABLE_SYMS, AVAILABLE_TFS
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print messages instead of sending")
    ap.add_argument("--once", action="store_true", help="one pass then exit")
    ap.add_argument("--minutes", type=float, default=0, help="keep running this many minutes, then save and exit (GitHub Actions)")
    ap.add_argument("--selftest", action="store_true", help="offline logic test")
    ap.add_argument("--simulate", action="store_true", help="offline run: all symbols x all timeframes, simulated prices")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if a.selftest:
        return selftest()
    if a.simulate:
        return simulate()
    if requests is None:
        sys.exit("Please run: pip install -r requirements.txt")
    syms = [x.strip().upper() for x in ENV("SYMBOLS", ",".join(INSTRUMENTS)).split(",") if x.strip().upper() in INSTRUMENTS]
    tfs = [t.strip().lower() for t in ENV("TIMEFRAMES", "1m,5m,15m,30m,1h").split(",") if t.strip().lower() in TF_SEC]
    AVAILABLE_SYMS, AVAILABLE_TFS = syms, tfs
    token, chat = clean_token(ENV("TELEGRAM_BOT_TOKEN", "")), clean_chat(ENV("TELEGRAM_CHAT_ID", ""))
    if not a.dry_run and not token:
        sys.exit("Set TELEGRAM_BOT_TOKEN in .env (or use --dry-run). TELEGRAM_CHAT_ID is optional: it is the channel that gets every signal.")
    run(syms, tfs, Telegram(token, chat, dry=a.dry_run), once=a.once, minutes=a.minutes)

if __name__ == "__main__":
    main()
