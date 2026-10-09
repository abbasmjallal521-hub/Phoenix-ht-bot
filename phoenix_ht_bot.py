#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PHOENIX HT SMC — Telegram Signal Bot
Developed by: The Phoenix HT Syndicate

Reads the market (Gold, Silver, Dow, Nasdaq, Oil), builds the same pending-order
plan as the Phoenix HT SMC indicator (range + ATR + 4-timeframe trend) and posts
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
"""
import os, sys, json, time, html, random, argparse, logging
from collections import namedtuple
from datetime import datetime, timezone, timedelta
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
    "XAUUSD": {"name": "Gold",       "yahoo": "GC=F", "oanda": "XAU_USD",    "digits": 2, "tick": 0.01},
    "XAGUSD": {"name": "Silver",     "yahoo": "SI=F", "oanda": "XAG_USD",    "digits": 3, "tick": 0.001},
    "US30":   {"name": "Dow Jones",  "yahoo": "YM=F", "oanda": "US30_USD",   "digits": 1, "tick": 0.1},
    "NAS100": {"name": "Nasdaq 100", "yahoo": "NQ=F", "oanda": "NAS100_USD", "digits": 1, "tick": 0.1},
    "USOIL":  {"name": "WTI Oil",    "yahoo": "CL=F", "oanda": "WTICO_USD",  "digits": 2, "tick": 0.01},
}
TF_SEC = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600}

# same defaults as the indicator
RANGE_BARS = int(ENV("RANGE_BARS", "24"))
SPREAD_PCT, EARLY_PCT, TP_SAFE_PCT = 15.0, 10.0, 10.0
SL_MULT = float(ENV("SL_MULT", "1.0"))
T1_MULT = float(ENV("T1_MULT", "2.5"))        # indicator default is 1.5; set the same value there
REV_MULT = 0.3
REFRESH_MIN = int(ENV("REFRESH_MIN", "120"))   # how often a plan may be refreshed (minutes)
MAX_DIST_ATR = float(ENV("MAX_DIST_ATR", "3"))  # only post orders within this many ATR of price
DEDUP_ATR = float(ENV("DEDUP_ATR", "0.5"))      # keep the old order if the new one is this close

TZ = ZoneInfo(ENV("TIMEZONE", "America/New_York"))
def hm(s):
    h, m = s.split(":"); return int(h) * 60 + int(m)
PLAN_START = hm(ENV("PLAN_START", "01:30"))
PLAN_END = hm(ENV("PLAN_END", "21:30"))

SHOW_COUNTER = ENV("SHOW_COUNTER", "0") == "1"
MIN_RR = float(ENV("MIN_RR", "1.0"))   # never post an order whose stop is bigger than its target
SEND_UPDATES = ENV("SEND_UPDATES", "1") == "1"
MAX_PER_PAIR_DAY = int(ENV("MAX_PER_PAIR_DAY", "2"))        # new signals per symbol+timeframe per day
MAX_SIGNALS_PER_DAY = int(ENV("MAX_SIGNALS_PER_DAY", "40"))  # new signals per day, all symbols together

PENDING, OPEN, TP_HIT, SL_HIT, DAY_END, CANCELLED = 0, 1, 2, 3, 4, 9
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

def arrow(b): return "▲" if b == 1 else "▼" if b == -1 else "•"

def ny_parts(ts):
    dt = datetime.fromtimestamp(ts, TZ)
    return dt.hour * 60 + dt.minute, dt.strftime("%Y-%m-%d")

# ───────────────────────────── plan logic (mirrors the indicator) ─────────────────────────────
def build_orders(atr, hi, lo, close, bias, tick):
    sp = max(atr * SPREAD_PCT / 100.0, tick)
    early = min(atr * EARLY_PCT / 100.0, sp)
    safe = atr * TP_SAFE_PCT / 100.0
    slD, t1D, rev = atr * SL_MULT, atr * T1_MULT, atr * REV_MULT
    mid = (hi + lo) / 2.0
    out = []

    def mk(direction, kind, is_stop, with_trend, lvl, sl, tp):
        o_lo = lvl if direction == 1 else lvl - sp
        o_hi = lvl + sp if direction == 1 else lvl
        entry = o_hi if direction == 1 else o_lo                 # worst side, used for R
        trig = o_lo if (direction == 1 and is_stop) or (direction == -1 and not is_stop) else o_hi
        out.append(dict(dir=direction, kind=kind, is_stop=is_stop, with_trend=with_trend,
                        lo=o_lo, hi=o_hi, entry=entry, trig=trig, sl=sl, tp=tp))

    lvl = hi + sp - early; tp = hi + t1D - sp - safe; wt = bias >= 0
    if tp > lvl + sp and (wt or SHOW_COUNTER):
        mk(1, "BUY STOP", True, wt, lvl, hi - slD, tp)
    lvl = lo - sp + early; tp = lo - t1D + sp + safe; wt = bias <= 0
    if tp < lvl - sp and (wt or SHOW_COUNTER):
        mk(-1, "SELL STOP", True, wt, lvl, lo + slD, tp)
    lvl = hi - sp - early; raw = min(mid, lvl - sp - rev); tp = raw + sp + safe; wt = bias <= 0
    if close < lvl - sp and tp < lvl - sp and (wt or SHOW_COUNTER):
        mk(-1, "SELL LIMIT", False, wt, lvl, hi + slD, tp)
    lvl = lo + sp + early; raw = max(mid, lvl + sp + rev); tp = raw - sp - safe; wt = bias >= 0
    if close > lvl + sp and tp > lvl + sp and (wt or SHOW_COUNTER):
        mk(1, "BUY LIMIT", False, wt, lvl, lo - slD, tp)
    return out

def risk_reward(o):
    risk = max(abs(o["entry"] - o["sl"]), 1e-9)
    return abs(o["tp"] - o["entry"]) / risk

# ───────────────────────────── messages ─────────────────────────────
LINE = "━━━━━━━━━━━━━━━━━━"
SIGN = "— The Phoenix HT Syndicate"


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
QN = 0   # rotating counter, saved in the state file so phrases never repeat back to back

def footer():
    global QN
    en, ar = QUOTES[QN % len(QUOTES)]
    QN += 1
    return (f"\n<i>“{html.escape(en)}”</i>\n<i>{html.escape(ar)}</i>\n\n"
            f"<i>Disclaimer: educational only, not financial advice. Trading is high risk; prices may differ from your broker.</i>\n"
            f"<i>إخلاء مسؤولية: للتعليم فقط وليس نصيحة مالية. التداول عالي المخاطر وقد تختلف الأسعار عن وسيطك.</i>\n{SIGN}")

def fmt(sym, x):
    return f"{x:,.{INSTRUMENTS[sym]['digits']}f}"

def title(o):
    return f"<b>{o['sym']}</b> · {INSTRUMENTS[o['sym']]['name']} · <b>{o['tf'].upper()}</b>"

def msg_signal(o, bias_info):
    d = "🟢" if o["dir"] == 1 else "🔴"
    trend = "with trend" if o["with_trend"] else "AGAINST trend"
    until = f"{PLAN_END // 60:02d}:{PLAN_END % 60:02d}"
    return (
        f"<b>PHOENIX HT SMC</b>  |  PENDING ORDER\n{LINE}\n"
        f"{title(o)}\n{d} <b>{o['kind']}</b> · {trend}\n\n"
        f"<code>Entry   {fmt(o['sym'], o['trig'])}</code>\n"
        f"<code>Stop    {fmt(o['sym'], o['sl'])}</code>\n"
        f"<code>Target  {fmt(o['sym'], o['tp'])}</code>\n"
        f"<code>R : R   1 : {risk_reward(o):.1f}</code>\n\n"
        f"Trend  <b>{bias_info['txt']}</b> · {bias_info['arrows']}\n"
        f"Valid until {until} NY, or until filled / cancelled\n{LINE}\n"
        f"Tip: enter a touch early, close a touch before the target.\n" + footer())

def short(o):
    return f"{o['sym']} {o['tf'].upper()} {o['kind']}  entry {fmt(o['sym'], o['trig'])}"

def msg_expired(o, reason):
    return f"⚪ <b>EXPIRED</b> — {html.escape(reason)}\n<s>{html.escape(short(o))}</s>"

def msg_filled(o):
    return (f"<b>FILLED</b> — {html.escape(short(o))}\nTrade is active. Stop {fmt(o['sym'], o['sl'])} · "
            f"Target {fmt(o['sym'], o['tp'])}\nOther pending orders of this plan are cancelled.\n{LINE}" + footer())

def msg_tp(o, r):
    return f"✅ <b>TARGET HIT</b> · +{r:.1f}R\n{html.escape(short(o))}\nWell done. Secure it, stay disciplined.\n{LINE}" + footer()

def msg_sl(o):
    return f"❌ <b>STOP HIT</b> · −1R\n{html.escape(short(o))}\nLoss is part of the plan. Next setup.\n{LINE}" + footer()

def msg_dayend(o, r):
    s = "+" if r >= 0 else "−"
    return f"⏹ <b>SESSION END</b> · ≈ {s}{abs(r):.1f}R\n{html.escape(short(o))}\nClose the trade at market.\n{LINE}" + footer()

# ───────────────────────────── telegram ─────────────────────────────
class Telegram:
    def __init__(self, token, chat_id, dry=False):
        self.token, self.chat, self.dry = token, chat_id, dry
        self.last = 0.0
        self.fake_id = 1000

    def _call(self, method, payload):
        wait = 2.5 - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        for _ in range(4):
            try:
                r = requests.post(url, json=payload, timeout=20)
            except requests.RequestException as e:      # never print the URL: it contains the bot token
                log.error("Telegram %s network error (%s)", method, type(e).__name__)
                time.sleep(3); continue
            self.last = time.time()
            if r.status_code == 429:
                time.sleep(r.json().get("parameters", {}).get("retry_after", 5) + 1); continue
            if not r.ok:
                log.error("Telegram %s failed: %s", method, r.text[:200]); return None
            return r.json()["result"]
        return None

    def send(self, text, reply_to=None):
        if self.dry:
            self.fake_id += 1
            print(f"\n[DRY-RUN] send #{self.fake_id}" + (f" (reply to #{reply_to})" if reply_to else "") + f"\n{text}\n")
            return self.fake_id
        p = {"chat_id": self.chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
        if reply_to:
            p["reply_to_message_id"] = reply_to
        res = self._call("sendMessage", p)
        return res["message_id"] if res else None

    def edit(self, msg_id, text):
        if self.dry:
            print(f"\n[DRY-RUN] edit #{msg_id}\n{text}\n"); return
        self._call("editMessageText", {"chat_id": self.chat, "message_id": msg_id, "text": text,
                                       "parse_mode": "HTML", "disable_web_page_preview": True})

# ───────────────────────────── data providers ─────────────────────────────
UA = {"User-Agent": "Mozilla/5.0 (PhoenixHT bot)"}

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

def get_candles(sym, tf, now):
    return (fetch_oanda if ENV("DATA_PROVIDER", "yahoo").lower() == "oanda" else fetch_yahoo)(sym, tf, now)

# ───────────────────────────── engine ─────────────────────────────
class Engine:
    def __init__(self, tg):
        self.tg = tg
        self.orders, self.pairs = [], {}
        self.stats = {"built": 0, "rr_skip": 0, "dist_skip": 0, "capped": 0}
        self.sent = {}
        self.load()

    # state
    def load(self):
        if os.path.exists(STATE_FILE):
            try:
                d = json.load(open(STATE_FILE, encoding="utf-8"))
                self.orders, self.pairs = d.get("orders", []), d.get("pairs", {})
                global QN
                QN = d.get("q", 0)
                self.sent = d.get("sent", {})
            except Exception as e:
                log.warning("state not loaded: %s", e)

    def save(self):
        if getattr(self.tg, "dry", False):          # a dry run must never write state (fake message ids)
            return
        tmp = STATE_FILE + ".tmp"
        json.dump({"orders": self.orders[-400:], "pairs": self.pairs, "q": QN, "sent": dict(sorted(self.sent.items())[-3:])}, open(tmp, "w", encoding="utf-8"))
        os.replace(tmp, STATE_FILE)

    def pair(self, sym, tf):
        return self.pairs.setdefault(f"{sym}|{tf}", {"last_t": 0, "day": "", "last_slot": -1, "day_ended": False, "seq": 0})

    # helpers
    def say(self, o, text):
        if SEND_UPDATES and o.get("msg_id"):
            self.tg.send(text, reply_to=o["msg_id"])

    def expire(self, o, reason):
        o["state"] = CANCELLED
        if o.get("msg_id"):
            self.tg.edit(o["msg_id"], msg_expired(o, reason))

    # one completed bar
    def process_bar(self, sym, tf, bars, bias_info, is_latest):
        bar, ps = bars[-1], self.pair(sym, tf)
        mins, day = ny_parts(bar.t)
        tick = INSTRUMENTS[sym]["tick"]
        mine = [o for o in self.orders if o["sym"] == sym and o["tf"] == tf and o["state"] in (PENDING, OPEN)]

        if ps["day"] != day:                                         # new New-York day
            ps.update(day=day, last_slot=-1, day_ended=False, sent=0)

        # 1) manage orders
        for o in mine:
            if o["state"] == PENDING:
                d = o["dir"]
                filled = (bar.h >= o["lo"] if o["is_stop"] else bar.l <= o["hi"]) if d == 1 else \
                         (bar.l <= o["hi"] if o["is_stop"] else bar.h >= o["lo"])
                if filled:
                    o["state"], o["fill_t"] = OPEN, bar.t
                    for q in mine:
                        if q is not o and q["plan"] == o["plan"] and q["state"] == PENDING:
                            self.expire(q, "another order of this plan was filled")
                    self.say(o, msg_filled(o))
                else:
                    missed = (not o["is_stop"]) and ((d == 1 and bar.h >= o["tp"]) or (d == -1 and bar.l <= o["tp"]))
                    if missed:
                        self.expire(o, "price reached the target before entry")
            elif o["state"] == OPEN and bar.t > o.get("fill_t", 0):
                d = o["dir"]
                if (d == 1 and bar.l <= o["sl"]) or (d == -1 and bar.h >= o["sl"]):
                    o["state"] = SL_HIT; self.say(o, msg_sl(o))
                elif (d == 1 and bar.h >= o["tp"]) or (d == -1 and bar.l <= o["tp"]):
                    o["state"] = TP_HIT; self.say(o, msg_tp(o, risk_reward(o)))

        # 2) end of session
        if mins >= PLAN_END and not ps["day_ended"]:
            ps["day_ended"] = True
            for o in self.orders:
                if o["sym"] == sym and o["tf"] == tf:
                    if o["state"] == PENDING:
                        self.expire(o, "session ended")
                    elif o["state"] == OPEN:
                        r = (bar.c - o["entry"]) * o["dir"] / max(abs(o["entry"] - o["sl"]), 1e-9)
                        o["state"] = DAY_END; self.say(o, msg_dayend(o, r))

        # 3) plan / refresh
        atr = calc_atr(bars)
        in_win = PLAN_START <= mins < PLAN_END
        eff = max(REFRESH_MIN, TF_SEC[tf] / 60.0)
        slot = int((mins - PLAN_START) // eff) if in_win else -1
        if is_latest and in_win and slot != ps["last_slot"] and atr and len(bars) > RANGE_BARS:
            ps["last_slot"] = slot
            live = [o for o in self.orders if o["sym"] == sym and o["tf"] == tf and o["state"] in (PENDING, OPEN)]
            win = bars[-RANGE_BARS:]
            hi, lo = max(b.h for b in win), min(b.l for b in win)
            if not any(o["state"] == OPEN for o in live) and hi - lo >= atr:
                new = build_orders(atr, hi, lo, bar.c, bias_info["now"], tick)
                ok_rr = [n for n in new if risk_reward(n) >= MIN_RR]
                ok = [n for n in ok_rr if abs(n["trig"] - bar.c) <= MAX_DIST_ATR * atr]
                self.stats["built"] += len(new); self.stats["rr_skip"] += len(new) - len(ok_rr)
                self.stats["dist_skip"] += len(ok_rr) - len(ok)
                new = ok
                pend = [o for o in live if o["state"] == PENDING]
                keep, add = [], []
                for n in new:                                         # keep an existing order if it is nearly identical
                    same = next((p for p in pend if p["kind"] == n["kind"] and all(
                        abs(p[k] - n[k]) <= DEDUP_ATR * atr for k in ("trig", "sl", "tp"))), None)
                    (keep if same else add).append(same or n)
                for p in pend:
                    if p not in keep:
                        self.expire(p, "replaced by an updated plan")
                if add:
                    ps["seq"] += 1
                    for n in add:
                        if ps.get("sent", 0) >= MAX_PER_PAIR_DAY or self.sent.get(day, 0) >= MAX_SIGNALS_PER_DAY:
                            self.stats["capped"] += 1
                            continue
                        n.update(sym=sym, tf=tf, plan=f"{sym}{tf}{ps['seq']}", state=PENDING, born_t=bar.t, fill_t=0)
                        n["msg_id"] = self.tg.send(msg_signal(n, bias_info))
                        ps["sent"] = ps.get("sent", 0) + 1
                        self.sent[day] = self.sent.get(day, 0) + 1
                        self.orders.append(n)

        ps["last_t"] = bar.t
        self.orders = [o for o in self.orders if o["state"] in (PENDING, OPEN) or o["born_t"] > bar.t - 3 * 86400]

# ───────────────────────────── live loop ─────────────────────────────
def bias_info_for(sym, now, cache):
    c = cache.get(sym)
    if c and now - c["ts"] < 600:
        return c
    bs = {}
    for tf in ("1d", "4h", "1h", "15m"):
        try:
            bs[tf] = bias_from_bars(get_candles(sym, tf, now))
        except Exception as e:
            log.warning("bias %s %s: %s", sym, tf, e); bs[tf] = 0
    bull = sum(1 for v in bs.values() if v == 1); bear = sum(1 for v in bs.values() if v == -1)
    now_b = 1 if bull > bear else -1 if bear > bull else 0
    txt = ("BULL" if now_b == 1 else "BEAR" if now_b == -1 else "MIXED") + f" {max(bull, bear)}/4"
    info = dict(ts=now, now=now_b, txt=txt,
                arrows=f"D{arrow(bs['1d'])} 4H{arrow(bs['4h'])} 1H{arrow(bs['1h'])} 15{arrow(bs['15m'])}")
    cache[sym] = info
    return info

def run(symbols, tfs, tg, once=False):
    eng, cache, nxt = Engine(tg), {}, {}
    log.info("Phoenix HT bot running: %s | %s | provider=%s", ",".join(symbols), ",".join(tfs), ENV("DATA_PROVIDER", "yahoo"))
    while True:
        now = int(time.time())
        for sym in symbols:
            for tf in tfs:
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
        if once:
            return
        time.sleep(5)

# ───────────────────────────── offline self-test ─────────────────────────────
def selftest():
    sent = []
    class Fake:
        n = 0
        def send(self, text, reply_to=None):
            Fake.n += 1; sent.append(("reply" if reply_to else "new", text)); return Fake.n
        def edit(self, mid, text): sent.append(("edit", text))
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
    eng = Engine(Fake())
    for i in range(60, len(bars)):
        day_idx = (bars[i].t - start) // 86400
        b = [-1, 1, 0, -1][day_idx]
        info = dict(now=b, txt={1: "BULL 3/4", -1: "BEAR 3/4", 0: "MIXED 2/4"}[b], arrows="D▼ 4H▼ 1H▼ 15•")
        eng.process_bar("XAUUSD", "5m", bars[max(0, i - 300):i + 1], info, is_latest=True)
    kinds = {}
    for k, t in sent:
        key = k + ":" + ("PENDING" if "PENDING ORDER" in t else "FILLED" if "FILLED" in t else "TARGET" if "TARGET" in t
                         else "STOP" if "STOP HIT" in t else "SESSION" if "SESSION END" in t else "EXPIRED" if "EXPIRED" in t else "?")
        kinds[key] = kinds.get(key, 0) + 1
    print("messages by type:", json.dumps(kinds, indent=1))
    first = next(t for k, t in sent if k == "new")
    print("\n--- sample signal ---\n" + first.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", "").replace("<i>", "").replace("</i>", ""))
    left = [o for o in eng.orders if o["state"] in (PENDING, OPEN)]
    print("\nopen/pending left at end:", len(left))
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
    samples, rows = {}, []
    class Fake:
        def __init__(self): self.n, self.log = 0, []
        def send(self, text, reply_to=None):
            self.n += 1; self.log.append(("reply" if reply_to else "new", text)); return self.n
        def edit(self, mid, text): self.log.append(("edit", text))
    for si, (sym, (p0, vol)) in enumerate(base.items()):
        price, one = p0, []
        for i in range(1440 * days):
            reg = (i // 1440 + si) % 3
            drift = vol * 0.04 * (1 if reg == 0 else -1 if reg == 1 else 0)
            o = price; c = o + drift + rnd.gauss(0, vol)
            one.append(Bar(start + i * 60, o, max(o, c) + abs(rnd.gauss(0, vol * .5)), min(o, c) - abs(rnd.gauss(0, vol * .5)), c)); price = c
        for tf, sec in TF_SEC.items():
            bars = one if tf == "1m" else resample(one, sec)
            if os.path.exists(STATE_FILE): os.remove(STATE_FILE)
            fk = Fake(); eng = Engine(fk)
            for i in range(60, len(bars)):
                b = [-1, 1, 0][((bars[i].t - start) // 86400 + si) % 3]
                info = dict(now=b, txt={1: "BULL 3/4", -1: "BEAR 3/4", 0: "MIXED 2/4"}[b], arrows="D" + arrow(b) + " 4H" + arrow(b) + " 1H" + arrow(b) + " 15•")
                eng.process_bar(sym, tf, bars[max(0, i - 300):i + 1], info, is_latest=True)
            cnt = {"new": 0, "FILLED": 0, "TARGET": 0, "STOP": 0, "SESSION": 0, "edit": 0}
            for k, t in fk.log:
                if k == "new": cnt["new"] += 1
                elif k == "edit": cnt["edit"] += 1
                else:
                    for w, key2 in (("FILLED", "FILLED"), ("TARGET HIT", "TARGET"), ("STOP HIT", "STOP"), ("SESSION END", "SESSION")):
                        if w in t: cnt[key2] += 1
                key = k + ("|" + next((w for w in ("PENDING ORDER", "FILLED", "TARGET HIT", "STOP HIT", "SESSION END", "EXPIRED") if w in t), "?"))
                samples.setdefault(key, strip_tags(t))
            rows.append((sym, tf, cnt, dict(eng.stats)))
    print(f"{'symbol':8}{'tf':5}{'signals':>8}{'filled':>8}{'target':>8}{'stop':>6}{'session':>8}   skipped(R<{MIN_RR:g} | far | cap)")
    tot = 0
    for sym, tf, c, st in rows:
        tot += c["new"]
        print(f"{sym:8}{tf:5}{c['new']:>8}{c['FILLED']:>8}{c['TARGET']:>8}{c['STOP']:>6}{c['SESSION']:>8}   {st['rr_skip']} | {st['dist_skip']} | {st['capped']}   (built {st['built']})")
    print(f"\nTOTAL signals over {days} simulated days: {tot}  (~{tot / days:.0f} per day for 5 symbols x 5 timeframes)")
    out = os.path.join(HERE, "sample_messages.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write("SIMULATED DATA - samples of every message type\n\n")
        for k, t in samples.items():
            f.write(f"##### {k}\n{t}\n\n")
    if os.path.exists(STATE_FILE): os.remove(STATE_FILE)
    print("samples written to", out)

# ───────────────────────────── entry ─────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print messages instead of sending")
    ap.add_argument("--once", action="store_true", help="one pass then exit")
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
    syms = [s.strip().upper() for s in ENV("SYMBOLS", ",".join(INSTRUMENTS)).split(",") if s.strip() in INSTRUMENTS or s.strip().upper() in INSTRUMENTS]
    tfs = [t.strip().lower() for t in ENV("TIMEFRAMES", "1m,5m,15m,30m,1h").split(",") if t.strip().lower() in TF_SEC]
    token, chat = ENV("TELEGRAM_BOT_TOKEN", ""), ENV("TELEGRAM_CHAT_ID", "")
    if not a.dry_run and (not token or not chat):
        sys.exit("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env (or use --dry-run).")
    run(syms, tfs, Telegram(token, chat, dry=a.dry_run), once=a.once)

if __name__ == "__main__":
    main()
