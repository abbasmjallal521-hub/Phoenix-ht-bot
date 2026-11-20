#!/usr/bin/env python3
"""المحلل · Phoenix Analyst

Once a week (Saturday morning, Beirut) it reads the signal bot's closed trades and sends the owner on Telegram:
what won and what lost by instrument and timeframe, by time of day and by day, against the owner's goals
(80% winning trades, about 40 trades a week), how long the bot was up, and a few ideas to improve.

It reads the bot's saved state (phoenix_state.json, restored read-only from the Actions cache) and the bot's runs on
GitHub. It never changes the bot, its settings or its state. It sends from the watchdog's own bot
(WATCHDOG_BOT_TOKEN), else from the signal bot, to the same chat as the watchdog. The repo is public: the log never
holds trades, ids or links.

  python watchdog/phoenix_analyst.py                    # this week, sent on Telegram
  python watchdog/phoenix_analyst.py --dry-run          # print the message instead
  python watchdog/phoenix_analyst.py --week 2026-11-16  # the week that holds this day
"""
import argparse
import json
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE)]
import phoenix_watchdog as wd     # noqa: E402  Telegram, GitHub, owner_chat, time helpers
import phoenix_ht_bot as bot      # noqa: E402  the bot's own instruments, charts and money maths

log = logging.getLogger("analyst")
ENV = os.environ.get
GOAL_WR = float(ENV("GOAL_WINRATE") or 80)      # the owner's goals: 80% winning trades ...
GOAL_TRADES = int(ENV("GOAL_TRADES") or 40)     # ... and about 40 trades a week
MIN_N = 4                                       # trades a chart or a time needs before it is called best or worst
LOT = bot.LOT_DEFAULT
AR = {"XAUUSD": "الدهب", "XAGUSD": "الفضة", "US30": "الداو", "NAS100": "الناسداك", "USOIL": "النفط"}
MONTHS = ["كانون الثاني", "شباط", "آذار", "نيسان", "أيار", "حزيران", "تموز", "آب", "أيلول", "تشرين الأول",
          "تشرين الثاني", "كانون الأول"]
SESSIONS = (("آسيا", 1, 9), ("لندن", 9, 15), ("نيويورك", 15, 23), ("الليل", 23, 25))   # Beirut hours [from, to)
LINE = "━━━━━━━━━━━━━━"
esc = wd.esc


# ───────────────────────────── the trades ─────────────────────────────
def load_state(path=None):
    try:
        with open(path or wd.BOT_STATE_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def trades_of(ledger):
    """The bot's ledger -> closed trades with their day, result (1 win, -1 loss, 2 at entry), $ and opening hour."""
    out = []
    for e in ledger or []:
        sym, tf = e.get("sym"), e.get("tf")
        if sym not in bot.INSTRUMENTS or not tf or not e.get("td"):
            continue
        dist = e.get("dist", 0.0)
        net = dist - e.get("cost", e.get("sp", 0.0))              # after the trading costs, like the bot's reports
        oc = e.get("oc")
        if oc is None:                                            # booked before v26: the bot's own reading
            oc = 2 if abs(dist) < 1e-12 else -1 if dist < 0 else 1 if net > bot.INSTRUMENTS[sym]["tick"] else 2
        opened = e.get("t", 0) - (e.get("dur") or 0)
        out.append({"sym": sym, "tf": tf, "td": date.fromisoformat(e["td"]), "oc": oc, "t": e.get("t", 0),
                    "usd": bot.money(sym, net, LOT), "hour": datetime.fromtimestamp(opened, wd.TZ).hour,
                    "dur": e.get("dur")})
    return sorted(out, key=lambda x: x["t"])


def tally(trades):
    o = {"n": 0, "win": 0, "loss": 0, "be": 0, "usd": 0.0}
    for x in trades:
        o["n"] += 1
        o["usd"] += x["usd"]
        o["win" if x["oc"] == 1 else "loss" if x["oc"] == -1 else "be"] += 1
    return o


def rate(t):
    """Winning share of the trades that ended in a win or a loss (the ones back at entry are left out)."""
    d = t["win"] + t["loss"]
    return round(100 * t["win"] / d) if d else None


def group(trades, key):
    out = {}
    for x in trades:
        out.setdefault(key(x), []).append(x)
    return {k: tally(v) for k, v in out.items()}


def session_of(hour):
    for name, a, b in SESSIONS:
        if a <= hour < b or a <= hour + 24 < b:
            return name
    return SESSIONS[-1][0]


def loss_streak(trades):
    """The most losses in a row (a trade back at entry neither adds nor breaks it)."""
    best = cur = 0
    for x in trades:
        if x["oc"] == -1:
            cur += 1
            best = max(best, cur)
        elif x["oc"] == 1:
            cur = 0
    return best


def week_of(day):
    mon = day - timedelta(days=day.weekday())
    return mon, mon + timedelta(days=6)


# ───────────────────────────── the bot's time up (from its runs on GitHub) ─────────────────────────────
def bot_uptime(gh, hours=168, now=None):
    """(share of the last `hours` with a bot run going, the stops longer than 10 minutes in seconds)."""
    now = now or time.time()
    start = now - hours * 3600
    spans = []
    for r in gh.runs(wd.BOT_WF, 80):
        if r.get("status") == "completed" and (wd.ts(r.get("updated_at")) or 0) < start:
            continue
        jobs = gh.jobs(r["id"])
        job = jobs[0] if jobs else {}
        s = wd.ts(job.get("started_at"))
        if not s:
            continue                                              # cancelled while waiting: it never ran
        e = wd.ts(job.get("completed_at")) or now
        if e > start:
            spans.append((max(s, start), min(e, now)))
    merged = []
    for s, e in sorted(spans):
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    edges = [start] + [x for s, e in merged for x in (s, e)] + [now]
    gaps = [edges[i + 1] - edges[i] for i in range(0, len(edges) - 1, 2)]
    return sum(e - s for s, e in merged) / (now - start), [g for g in gaps if g > 600]


# ───────────────────────────── the message ─────────────────────────────
def usd(v):
    return f"{v:+,.2f}$"


def wlb(t):
    return f"✅{t['win']} ❌{t['loss']} ⚪{t['be']}"


def chart(key):
    sym, tf = key
    return f"{AR.get(sym, sym)} {tf.upper()}"


def span_label(mon):
    fri = mon + timedelta(days=4)
    if mon.month == fri.month:
        return f"{mon.day} – {fri.day} {MONTHS[fri.month - 1]} {fri.year}"
    return f"{mon.day} {MONTHS[mon.month - 1]} – {fri.day} {MONTHS[fri.month - 1]} {fri.year}"


def lot_note():
    bigger = {}
    for s in bot.INSTRUMENTS:
        if s in AR and bot.lot_for(s, LOT) > LOT:
            bigger.setdefault(bot.lot_for(s, LOT), []).append(AR[s])
    extra = "، ".join(f"{' و'.join(v)} {k:g}" for k, v in bigger.items())
    return f"بالدولار على لوت {LOT:g}" + (f" ({extra})" if extra else "")


def ideas(week, by_chart, by_session):
    """A few ideas from the numbers. They never cut the trading hours, never touch the stop rules (the stop is
    never bigger than the target, after target 1 it stays at the entry) and are always tested before use."""
    out = []
    charts = [(k, t) for k, t in by_chart.items() if t["n"] >= MIN_N]
    worst = min(charts, key=lambda kt: kt[1]["usd"], default=None)
    best = max(charts, key=lambda kt: (rate(kt[1]) or 0, kt[1]["usd"]), default=None)
    total = rate(week)
    if worst and worst[1]["usd"] < 0:
        out.append(f"📉 <b>{chart(worst[0])}</b> خسّر هالأسبوع ({wlb(worst[1])}، {usd(worst[1]['usd'])}). "
                   "فكرة: نعيد اختبار إعداداته على آخر شهرين، ونشوف إذا بدّه شرط دخول أقوى.")
    if total is not None and total < GOAL_WR and week["n"] >= 8:
        times_ = [(s, t) for s, t in by_session.items() if t["n"] >= MIN_N]
        weak = min(times_, key=lambda st: st[1]["usd"], default=None)
        where = f" أضعف وقت كان {weak[0]} ({usd(weak[1]['usd'])})." if weak and weak[1]["usd"] < 0 else ""
        out.append(f"🎯 نسبة الربح {total}% والهدف {GOAL_WR:g}%.{where} "
                   "فكرة: نشدّد شرط الدخول بهالوقت (بلا ما نوقف التداول فيه)، ونجرّبه عالاختبار قبل ما نعتمده.")
    if week["n"] < GOAL_TRADES * 0.8:
        untested = [AR[s] for s in bot.INSTRUMENTS if s in AR and s not in bot.V20]
        what = f"نختبر {' و'.join(untested)}، أو فريمات جديدة" if untested else "نختبر فريمات جديدة"
        out.append(f"📊 {week['n']} صفقة والهدف حوالي {GOAL_TRADES} بالأسبوع. فكرة: {what}، ونزيد بس يلي بينجح بالاختبار.")
    if best and (rate(best[1]) or 0) >= GOAL_WR and best[1]["usd"] > 0:
        out.append(f"🔥 <b>{chart(best[0])}</b> كان الأحسن ({wlb(best[1])}، {usd(best[1]['usd'])}). "
                   "فكرة: صانع المحتوى يعمل عنه فيديو بالنتيجة الحقيقية.")
    if not out:
        out.append("👌 أسبوع متوازن، ما في شي لافت. منكمّل متل ما نحنا ومنرجع منقيّم الأسبوع الجاي.")
    return out[:4]


def build(state, today, up=None):
    """The weekly message (Telegram HTML). `up` = bot_uptime(...) or None when it could not be read."""
    head = "🧠 <b>المحلل · تقرير الأسبوع</b>"
    mon, _ = week_of(today)
    if state is None:
        return (f"{head}\n{LINE}\nما قدرت اقرا ذاكرة بوت الإشارات هالمرة، فما في أرقام.\n"
                "بجرّب من جديد الأسبوع الجاي، أو شغّلني بإيدك: GitHub › Actions › Phoenix Analyst › Run workflow.")
    all_ = trades_of(state.get("ledger"))
    wk = [x for x in all_ if mon <= x["td"] <= mon + timedelta(days=6)]
    prev = [x for x in all_ if mon - timedelta(days=7) <= x["td"] < mon]
    month = [x for x in all_ if (x["td"].year, x["td"].month) == (today.year, today.month) and x["td"] <= today]
    t, p, m = tally(wk), tally(prev), tally(month)
    out = [head, span_label(mon), LINE]
    if t["n"]:
        r = rate(t)
        out += [f"📊 <b>{t['n']} صفقة</b> · {wlb(t)}",
                f"🎯 نسبة الربح: <b>{r}%</b> (بلا يلي رجعت عالدخول) · الهدف {GOAL_WR:g}%" if r is not None else
                "🎯 نسبة الربح: ما في صفقات سكّرت بربح أو خسارة",
                f"💵 <b>{usd(t['usd'])}</b> · {lot_note()}"]
    else:
        out.append("📊 ما سكّرت ولا صفقة هالأسبوع.")
    if p["n"]:
        pr = rate(p)
        out.append(f"↩️ الأسبوع الماضي: {p['n']} صفقة · " + (f"{pr}% · " if pr is not None else "") + usd(p["usd"]))
    if m["n"]:
        out.append(f"📅 {MONTHS[today.month - 1]} لهلق: {m['n']} صفقة · {wlb(m)} · {usd(m['usd'])}")
    by_chart = group(wk, lambda x: (x["sym"], x["tf"]))
    by_session = group(wk, lambda x: session_of(x["hour"]))
    if t["n"]:
        out += ["", "<b>حسب الأداة والفريم</b>"]
        out += [f"• {chart(k)}: {v['n']} · {wlb(v)} · {usd(v['usd'])}"
                for k, v in sorted(by_chart.items(), key=lambda kv: -kv[1]["usd"])]
        quiet = [chart((s, tf)) for s, tfs in bot.V20.items() for tf in tfs if (s, tf) not in by_chart]
        if quiet:
            out.append(f"⏸ بلا صفقات: {'، '.join(quiet)}")
        out += ["", "<b>حسب الوقت (بيروت، ساعة الدخول)</b>"]
        out += [f"• {name} {a}–{b % 24}: {by_session[name]['n']} · {wlb(by_session[name])} · {usd(by_session[name]['usd'])}"
                for name, a, b in SESSIONS if name in by_session]
        by_day = group(wk, lambda x: x["td"].weekday())
        out += ["", "<b>حسب اليوم</b>"]
        out += [f"• {wd.DAYS[d]}: {v['n']} · {wlb(v)} · {usd(v['usd'])}" for d, v in sorted(by_day.items())]
        extra = []
        streak = loss_streak(wk)
        if streak >= 2:
            extra.append(f"🔁 أكتر خسارات ورا بعض: {streak}")
        wins = [x["dur"] for x in wk if x["oc"] == 1 and x.get("dur")]
        losses = [x["dur"] for x in wk if x["oc"] == -1 and x.get("dur")]
        if wins or losses:
            extra.append("⏱ مدة الصفقة: " + " · ".join(
                f"{label} {wd.dur(sum(v) / len(v))}" for label, v in (("الربح", wins), ("الخسارة", losses)) if v))
        if extra:
            out += [""] + extra
    if up is not None:
        share, gaps = up
        line = f"🛡️ <b>بوت الإشارات</b> كان شغّال {round(share * 100)}% من آخر 7 أيام"
        if gaps:
            line += f"، ووقف {wd.times(len(gaps))} (أطولها {wd.dur(max(gaps))})"
        out += ["", line + "."]
    out += ["", "💡 <b>أفكار</b>"] + [f"{i}. {x}" for i, x in enumerate(ideas(t, by_chart, by_session), 1)]
    out += ["", "<i>تقديرات من هدف ووقف كل صفقة، مش كشف حسابك. أي تعديل بيصير بس بموافقتك.</i>",
            "<i>THE PHOENIX HAZ SYNDICATE · المحلل</i>"]
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Phoenix Analyst: the weekly results report, to the owner on Telegram")
    ap.add_argument("--dry-run", action="store_true", help="print the message instead of sending it")
    ap.add_argument("--week", help="a day (YYYY-MM-DD) of the week to report; default: this week in Beirut")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    today = date.fromisoformat(a.week) if a.week else wd.local_now().date()
    state = load_state()
    log.info("bot state: %s", "read" if state is not None else "not found")
    up = None
    if ENV("GITHUB_TOKEN") and not a.week:
        try:
            up = bot_uptime(wd.GitHub(ENV("GITHUB_TOKEN")))
        except Exception as e:                                    # the report goes out without it
            log.warning("the bot's runs could not be read: %s", type(e).__name__)
    chat, source = wd.owner_chat()
    own = wd.clean_token(ENV("WATCHDOG_BOT_TOKEN"))
    tg = wd.Telegram(own or wd.clean_token(ENV("TELEGRAM_BOT_TOKEN")), chat, dry=a.dry_run)
    log.info("report goes to: %s, from %s", source or "nobody yet (add the secret WATCHDOG_CHAT_ID)",
             "the watchdog's own bot" if own else "the signal bot")
    return 0 if tg.send(build(state, today, up)) else 1


if __name__ == "__main__":
    sys.exit(main())
