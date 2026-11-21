#!/usr/bin/env python3
"""صانع المحتوى · الفيديوهات · Phoenix Video

Vertical videos (1080x1920, 30 fps, MP4 with sound) for TikTok, Instagram Reels and YouTube Shorts, made from the
signal bot's real trades:

  * the day's video: the day's result, then its best winning trades on their real chart (Capital.com candles, the
    prices the bot itself reads), the price climbing target after target;
  * the week's video for the signal bot: how a signal reaches the subscribers (on a phone), the week's numbers, the
    week's best trade on its chart, and the call to subscribe.

Every video ends on the risk line; no promises. The music and the sounds are made here, note by note (nobody else's
music): free to post. Each frame is an HTML page drawn in Chrome (Playwright) and ffmpeg puts them together.
phoenix_content.py calls it every morning; the week's video comes on Saturdays (after Friday's close).

  python watchdog/phoenix_video.py --sample day --out x/    # a sample video with made-up numbers (marked as a sample)
  python watchdog/phoenix_video.py --sample week --out x/
"""
import argparse
import base64
import json
import logging
import math
import os
import shutil
import subprocess
import sys
import tempfile
import wave
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE)]
import requests                   # noqa: E402
import phoenix_watchdog as wd     # noqa: E402
import phoenix_ht_bot as bot      # noqa: E402
import phoenix_analyst as analyst  # noqa: E402
import phoenix_content as content  # noqa: E402  the day's trades, the words and the money, the same as the pictures

log = logging.getLogger("video")
ENV = os.environ.get
VW, VH, FPS = 1080, 1920, 30
LOGO = os.path.join(HERE, "assets", "phoenix_logo.jpg")
SR = 44100                                       # the sound: 44.1 kHz stereo
INTRO, SUMMARY, TRADE, HOW, WEEK, OUTRO = 2.6, 4.8, 6.8, 7.0, 5.6, 3.8
TOP_VIDEO = 3                                    # winning trades shown in the day's video
MAX_BARS, BEFORE = 72, 24                        # candles on a trade's chart, and how many come before its entry
STEPS = (("1m", 60), ("5m", 300), ("15m", 900), ("30m", 1800), ("1h", 3600), ("4h", 14400))
WHOOSH = 0.42                                    # a whoosh ends on the scene it brings in


# ───────────────────────────── the trades on their chart ─────────────────────────────
def trade_window(x):
    """The chart of a trade: its own timeframe, or a bigger one when the trade lasted too long to fit; with a stretch
    before the entry (to see where it came from) and a little after the close. (tf, seconds, from, to)"""
    base = bot.TF_SEC.get(x["tf"], 300)
    span = max(1, x["closed"] - x["opened"])
    tf, sec = STEPS[-1]
    for name, s in STEPS:
        if s >= base and span / s + BEFORE + 4 <= MAX_BARS:
            tf, sec = name, s
            break
    return tf, sec, (int(x["opened"]) // sec - BEFORE) * sec, (int(x["closed"]) // sec + 3) * sec


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def offsets_of(state):
    """The price offsets the bot calibrated (its levels carry them, so its candles must too)."""
    out = {}
    for sym, v in ((state or {}).get("meta") or {}).get("offsets", {}).items():
        if isinstance(v, dict) and "v" in v:
            out[sym] = float(v["v"])
    return out


def trade_bars(feed, x, offsets=None):
    """The real candles of a trade from Capital.com (the bot's own prices): [(t, o, h, l, c)], or None."""
    tf, sec, start, end = trade_window(x)
    try:
        data = feed.get(f"/api/v1/prices/{bot.INSTRUMENTS[x['sym']]['capital']}",
                        {"resolution": bot.CapitalFeed.RES[tf], "from": iso(start), "to": iso(end), "max": 1000})
        bars = feed._parse(data or {})
    except Exception as ex:                                   # no prices: the trade is shown on its ladder instead
        log.info("%s %s: no candles (%s)", x["sym"], x["tf"], type(ex).__name__)
        return None, tf
    off = (offsets or {}).get(x["sym"], 0.0)
    bars = [(b.t, b.o + off, b.h + off, b.l + off, b.c + off) for b in bars if start <= b.t <= end]
    if len(bars) < 8 or bars[0][0] > x["opened"] or bars[-1][0] + sec < x["closed"]:
        return None, tf
    return bars, tf


def trade_info(x, bars=None, chart_tf=None):
    """Everything the video shows about one trade. With candles: which candle holds the entry, each target reached
    and the close (so the chart climbs to them in order)."""
    o, sym, d = x["o"], x["sym"], x["dir"]
    tps, hits = list(o["tps"]), o.get("hits", 0)
    entry = o["trig"]
    stop = o.get("sl", o.get("stop", entry - o.get("risk", 0) * d))
    dg = bot.INSTRUMENTS[sym]["digits"]
    n = len(tps)
    mins = max(1, round((x["closed"] - x["opened"]) / 60))
    info = {"sym": sym, "ar": content.AR.get(sym, ""), "tf": content.tf_txt(x["tf"]), "dir": d, "dg": dg,
            "entry": entry, "sl": stop, "tps": tps, "hits": hits,
            "reached": "وصلت كل الأهداف" if hits == n else f"وصلت TP{hits}" if hits else "ربح",
            "pts": bot.pts(sym, x["dist"]), "usd": content.money_txt(x["usd"]), "lot": f"{bot.lot_for(sym, content.LOT):g}",
            "took": wd.dur(mins * 60), "bars": None}
    if bars:
        fill = max([i for i, b in enumerate(bars) if b[0] <= x["opened"]] or [0])
        last = max([i for i, b in enumerate(bars) if b[0] <= x["closed"]] or [len(bars) - 1])
        last = max(last, fill)
        hit_at = []
        for k in range(hits):
            tp, start = tps[k], hit_at[-1] if hit_at else fill
            i = next((i for i in range(start, last + 1) if (bars[i][2] >= tp if d == 1 else bars[i][3] <= tp)), last)
            hit_at.append(i)
        info.update(bars=[[b[0]] + [round(v, dg + 1) for v in b[1:]] for b in bars], fill=fill, last=last,
                    hit_at=hit_at, chart_tf=content.tf_txt(chart_tf or x["tf"]))
    return info


def reveal(info):
    """When the candles appear and each target is hit, in seconds from the start of the trade's scene. The page and
    the sound both use these numbers, so the bell rings on the frame the target is reached."""
    s = {"a0": 0.3, "a1": 1.4, "l0": 1.45, "b0": 2.0, "b1": 4.8, "r0": 4.95}
    if info.get("bars"):
        span = max(1, info["last"] - info["fill"])
        s["hit"] = [s["b0"] + (s["b1"] - s["b0"]) * max(0.04, (h - info["fill"]) / span) for h in info["hit_at"]]
    else:
        n = max(1, info["hits"])
        s["hit"] = [s["b0"] + (s["b1"] - s["b0"]) * (k + 1) / n for k in range(info["hits"])]
    return s


# ───────────────────────────── the stories (scenes, times, sounds) ─────────────────────────────
def _scene(story, kind, dur, **kw):
    sc = dict(kind=kind, start=round(story["dur"], 3), dur=dur, **kw)
    story["scenes"].append(sc)
    if story["scenes"][:-1]:
        story["sfx"].append((max(0.0, sc["start"] - WHOOSH), "whoosh"))
    story["dur"] = round(story["dur"] + dur, 3)
    return sc


def _trade_scene(story, info):
    sc = _scene(story, "trade", TRADE, trade=info, sched=reveal(info))
    story["sfx"] += [(sc["start"] + h, f"ding{k}") for k, h in enumerate(sc["sched"]["hit"])]
    story["sfx"].append((sc["start"] + sc["sched"]["r0"] + 0.1, "sparkle"))


def week_range(mon):
    fri = mon + timedelta(days=4)
    if mon.month == fri.month:
        return f"{mon.day}–{fri.day} {content.MONTHS[mon.month - 1]}"
    return f"{mon.day} {content.MONTHS[mon.month - 1]} – {fri.day} {content.MONTHS[fri.month - 1]}"


def day_story(day, t, infos, sample=False):
    r = analyst.rate(t)
    story = {"kind": "day", "dur": 0.0, "scenes": [], "sfx": [(0.12, "boom")], "sample": sample,
             "handle": content.HANDLE, "risk": content.RISK}
    _scene(story, "intro", INTRO, sub=f"نتايج {content.day_ar(day)}")
    sc = _scene(story, "summary", SUMMARY, kicker="نتايج اليوم", title=content.day_ar(day), usd=round(t["usd"], 2),
                note=f"مجموع اليوم {content.lot_note()}، بعد السبريد والعمولة",
                tiles=[[t["n"], "صفقة", ""], [t["win"], "ربح", "win"], [t["loss"], "خسارة", "loss"], [t["be"], "عالدخول", "be"]],
                rate=r)
    story["sfx"].append((sc["start"] + 1.5, "sparkle"))
    story["drop"] = sc["start"]
    for info in infos:
        _trade_scene(story, info)
    sc = _scene(story, "outro", OUTRO, cta="الإشارات بتوصل للمشتركين عالتلغرام لحظة بلحظة",
                pills=["الدخول", "الستوب", "الأهداف"])
    story["sfx"].append((sc["start"] + 0.4, "hit"))
    return story


def week_story(mon, t, by_sym, best, sample=False):
    r = analyst.rate(t)
    story = {"kind": "week", "dur": 0.0, "scenes": [], "sfx": [(0.12, "boom")], "sample": sample,
             "handle": content.HANDLE, "risk": content.RISK}
    _scene(story, "intro", INTRO, sub=f"بوت الإشارات · أسبوع {week_range(mon)}")
    if best:
        o = best
        lines = [["الدخول", f"{o['entry']:,.{o['dg']}f}", "en"], ["الستوب", f"{o['sl']:,.{o['dg']}f}", "sl"]]
        lines += [[f"TP{k + 1}", f"{p:,.{o['dg']}f}", "tp"] for k, p in enumerate(o["tps"])]
        hits = [[f"وصل TP{k + 1}", ""] for k in range(o["hits"])]
        if o["hits"] and o["hits"] == len(o["tps"]):
            hits[-1] = ["وصلت كل الأهداف", o["pts"]]
        bub = [0.9, 1.5] + [2.9 + 0.75 * k for k in range(len(hits))]
        sc = _scene(story, "how", HOW, kicker="كيف بيشتغل؟", sym=o["sym"], tf=o["tf"], dir=o["dir"], lines=lines,
                    hits=hits, bub=bub, steps=["المؤشر بيقرا السوق", "الصفقة بتوصلك عالتلغرام", "خبر عند كل هدف"])
        story["sfx"] += [(sc["start"] + b, "pop") for b in bub[1:]]
        story["drop"] = sc["start"]
    syms = sorted(by_sym.items(), key=lambda kv: -kv[1]["n"])
    sc = _scene(story, "week", WEEK, kicker="نتايج الأسبوع", title=f"أسبوع {week_range(mon)}", usd=round(t["usd"], 2),
                note=f"مجموع الأسبوع {content.lot_note()}، بعد السبريد والعمولة",
                tiles=[[t["n"], "صفقة", ""], [t["win"], "ربح", "win"], [t["loss"], "خسارة", "loss"]] + ([[r, "نسبة الربح", "win", "%"]] if r is not None else []),
                rate=r,
                syms=[[s, content.AR.get(s, s), v["win"], v["loss"], v["be"]] for s, v in syms[:5]])
    story.setdefault("drop", sc["start"])
    story["sfx"].append((sc["start"] + 1.5, "sparkle"))
    if best:
        _trade_scene(story, best)
    sc = _scene(story, "outro", OUTRO, cta="اشترك وخلّي الصفقات توصلك عالتلغرام", pills=["الدخول", "الستوب", "الأهداف"])
    story["sfx"].append((sc["start"] + 0.4, "hit"))
    return story


# ───────────────────────────── the page that draws every frame ─────────────────────────────
PAGE = r"""<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><style>
@font-face { font-family: "Readex"; src: url("__FONT__") format("truetype"); font-weight: 160 700; }
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { width: 1080px; height: 1920px; overflow: hidden; background: #07080a; }
body { font-family: "Readex", sans-serif; color: #f7efe5; position: relative; }
#bg { position: absolute; inset: 0; }
.scene { position: absolute; inset: 0; opacity: 0; will-change: opacity, transform; }
.n { direction: ltr; unicode-bidi: isolate; display: inline-block; }
.win { color: #3ddc84; } .loss { color: #ff6b5e; } .be { color: #cfc7bc; }
#brand { position: absolute; top: 118px; left: 0; right: 0; display: flex; justify-content: center; align-items: center; gap: 22px;
  direction: ltr; opacity: 0; }
#brand img { width: 92px; height: 92px; border-radius: 50%; border: 3px solid #d4af37; box-shadow: 0 0 34px rgba(228,104,42,.55); }
#brand b { display: block; font-size: 30px; font-weight: 700; letter-spacing: .2em; }
#brand small { display: block; font-size: 19px; font-weight: 500; letter-spacing: .32em; color: #ffc58a; margin-top: 6px; }
#sample { position: absolute; top: 46px; left: 0; right: 0; text-align: center; font-size: 26px; font-weight: 600; color: #1a120c;
  display: none; } #sample span { background: #ffc58a; border-radius: 99px; padding: 6px 26px; }
#fade { position: absolute; inset: 0; background: #000; opacity: 0; pointer-events: none; }
/* intro */
.intro .logo-wrap { position: absolute; left: 50%; top: 520px; width: 470px; height: 470px; margin-left: -235px; }
.intro .halo { position: absolute; inset: -46px; border-radius: 50%;
  background: conic-gradient(from 0deg, rgba(212,175,55,0), rgba(255,197,138,.85), rgba(228,104,42,.2), rgba(212,175,55,0) 60%, rgba(255,197,138,.7), rgba(212,175,55,0));
  -webkit-mask: radial-gradient(closest-side, transparent 93%, #000 94.5%, #000 100%); mask: radial-gradient(closest-side, transparent 93%, #000 94.5%, #000 100%); }
.intro .glow { position: absolute; inset: -160px; border-radius: 50%; background: radial-gradient(closest-side, rgba(228,104,42,.55), rgba(228,104,42,0)); }
.intro img { position: absolute; inset: 0; width: 100%; height: 100%; border-radius: 50%; border: 6px solid #d4af37; }
.intro h1 { position: absolute; top: 1120px; left: 0; right: 0; text-align: center; direction: ltr; font-size: 74px; font-weight: 700; letter-spacing: .2em; }
.intro .syn { position: absolute; top: 1232px; left: 0; right: 0; text-align: center; direction: ltr; font-size: 26px; letter-spacing: .42em; color: #ffc58a; }
.intro .sub { position: absolute; top: 1330px; left: 0; right: 0; text-align: center; font-size: 46px; font-weight: 600; }
/* numbers */
.kicker { position: absolute; top: 290px; left: 80px; right: 140px; font-size: 40px; font-weight: 500; color: #ffc58a; }
.title { position: absolute; top: 352px; left: 80px; right: 140px; font-size: 64px; font-weight: 700; line-height: 1.12; white-space: nowrap; }
.total { position: absolute; top: 520px; left: 110px; right: 110px; text-align: center; font-size: 176px; font-weight: 700; letter-spacing: -.02em; line-height: 1; }
.note { position: absolute; top: 730px; left: 130px; right: 130px; text-align: center; font-size: 30px; color: rgba(247,239,229,.66); line-height: 1.4; }
.tiles { position: absolute; top: 860px; left: 70px; right: 130px; display: grid; gap: 20px; }
.tiles div { border-radius: 34px; background: rgba(255,255,255,.06); border: 1.5px solid rgba(255,255,255,.08); padding: 30px 10px 24px; text-align: center; }
.tiles b { display: block; font-size: 92px; font-weight: 700; line-height: 1.02; }
.tiles i { display: block; font-style: normal; font-size: 32px; color: rgba(247,239,229,.72); margin-top: 6px; }
.ring { position: absolute; top: 1150px; left: 50%; width: 340px; height: 340px; margin-left: -170px; }
.ring svg { width: 100%; height: 100%; transform: rotate(-90deg); }
.ring .lab { position: absolute; inset: 0; display: grid; place-content: center; text-align: center; }
.ring .lab b { font-size: 96px; font-weight: 700; color: #3ddc84; direction: ltr; line-height: 1; }
.ring .lab i { font-style: normal; font-size: 30px; color: rgba(247,239,229,.72); margin-top: 10px; }
.syms { position: absolute; top: 1140px; left: 80px; right: 140px; display: grid; gap: 22px; }
.syms .row { display: grid; grid-template-columns: 210px 1fr 130px; align-items: center; gap: 22px; font-size: 34px; }
.syms .bar { height: 26px; border-radius: 99px; background: rgba(255,255,255,.07); overflow: hidden; display: flex; direction: ltr; }
.syms .bar .w { background: linear-gradient(90deg, #2bb673, #3ddc84); } .syms .bar .l { background: #ff6b5e; } .syms .bar .b { background: #9d958b; }
.syms .wl { direction: ltr; text-align: left; font-weight: 600; font-size: 30px; }
/* a trade */
.badge { position: absolute; top: 250px; left: 70px; display: inline-flex; align-items: center; gap: 14px; font-size: 36px; font-weight: 600;
  padding: 12px 30px; border-radius: 99px; background: rgba(61,220,132,.14); color: #3ddc84; border: 1.5px solid rgba(61,220,132,.4); }
.badge svg { width: 38px; height: 38px; }
.symrow { position: absolute; top: 346px; left: 70px; right: 130px; display: flex; align-items: center; gap: 18px; }
.symrow h1 { font-size: 96px; font-weight: 700; direction: ltr; letter-spacing: .01em; line-height: 1; }
.symrow .ar { font-size: 42px; color: rgba(247,239,229,.78); }
.chip { font-size: 32px; font-weight: 600; padding: 6px 22px; border-radius: 16px; background: rgba(255,197,138,.15); color: #ffc58a; direction: ltr; }
.dir { display: inline-flex; align-items: center; gap: 10px; direction: ltr; font-weight: 700; font-size: 32px; letter-spacing: .06em;
  padding: 6px 20px; border-radius: 16px; background: rgba(255,255,255,.07); }
.dir.buy { color: #3ddc84; } .dir.sell { color: #ff6b5e; } .dir svg { width: 28px; height: 28px; }
.chart { position: absolute; top: 486px; left: 60px; width: 900px; height: 840px; }
.result { position: absolute; top: 1356px; left: 110px; right: 110px; display: flex; align-items: baseline; justify-content: center; gap: 22px; }
.result .big { font-size: 150px; font-weight: 700; line-height: 1; color: #3ddc84; direction: ltr; }
.result .unit { font-size: 52px; font-weight: 600; color: rgba(247,239,229,.85); }
.sub2 { position: absolute; top: 1530px; left: 120px; right: 120px; text-align: center; font-size: 32px; color: rgba(247,239,229,.7); line-height: 1.45; }
/* the phone */
.how .kicker { top: 286px; text-align: center; font-size: 54px; font-weight: 700; color: #f7efe5; }
.phone { position: absolute; top: 372px; left: 50%; width: 600px; height: 940px; margin-left: -300px; border-radius: 74px;
  background: #0b0d11; border: 10px solid #1d1f25; box-shadow: 0 0 0 2px rgba(212,175,55,.5), 0 40px 120px rgba(0,0,0,.6), 0 0 90px rgba(228,104,42,.18); overflow: hidden; }
.phone .notch { position: absolute; top: 16px; left: 50%; width: 170px; height: 34px; margin-left: -85px; border-radius: 99px; background: #000; }
.ph-head { position: absolute; top: 70px; left: 0; right: 0; height: 110px; display: flex; align-items: center; gap: 20px; padding: 0 32px;
  background: rgba(255,255,255,.04); border-bottom: 1px solid rgba(255,255,255,.06); }
.ph-head img { width: 72px; height: 72px; border-radius: 50%; border: 2px solid #d4af37; }
.ph-head b { display: block; font-size: 30px; direction: ltr; text-align: right; } .ph-head small { display: block; font-size: 22px; color: #8fa0b5; }
.chat { position: absolute; top: 200px; left: 26px; right: 26px; bottom: 30px; display: flex; flex-direction: column; gap: 16px; }
.bub { align-self: flex-start; max-width: 92%; border-radius: 30px 30px 10px 30px; background: #1a2330; padding: 22px 28px; font-size: 28px; line-height: 1.5;
  transform-origin: 0% 100%; opacity: 0; box-shadow: 0 8px 24px rgba(0,0,0,.3); }
.bub .hd { display: flex; align-items: center; gap: 14px; font-weight: 700; font-size: 32px; direction: ltr; justify-content: flex-end; margin-bottom: 8px; }
.bub .ln { display: flex; justify-content: space-between; gap: 30px; }
.bub .ln b { direction: ltr; font-weight: 600; }
.bub .en b { color: #ffc58a; } .bub .sl b { color: #ff6b5e; } .bub .tp b { color: #3ddc84; }
.bub.ok { background: rgba(61,220,132,.16); color: #3ddc84; font-weight: 600; display: flex; align-items: center; gap: 12px; }
.bub.ok svg { width: 32px; height: 32px; }
.typing { align-self: flex-start; border-radius: 30px; background: #1a2330; padding: 22px 28px; display: flex; gap: 10px; opacity: 0; }
.typing i { width: 14px; height: 14px; border-radius: 50%; background: #8fa0b5; display: block; }
.steps { position: absolute; top: 1350px; left: 120px; right: 140px; display: grid; gap: 12px; }
.step { display: flex; align-items: center; gap: 18px; font-size: 32px; font-weight: 500; opacity: 0; }
.step i { font-style: normal; width: 56px; height: 56px; border-radius: 50%; display: grid; place-items: center; font-weight: 700; font-size: 30px;
  background: linear-gradient(135deg, #ffc58a, #e4682a); color: #1a110b; flex: none; }
/* outro */
.outro img { position: absolute; top: 430px; left: 50%; width: 250px; height: 250px; margin-left: -125px; border-radius: 50%; border: 5px solid #d4af37;
  box-shadow: 0 0 60px rgba(228,104,42,.5); }
.outro .cta { position: absolute; top: 760px; left: 90px; right: 90px; text-align: center; font-size: 64px; font-weight: 700; line-height: 1.3; }
.outro .pills { position: absolute; top: 1010px; left: 0; right: 0; display: flex; justify-content: center; gap: 18px; }
.outro .pills span { font-size: 34px; font-weight: 600; padding: 12px 30px; border-radius: 99px; background: rgba(255,197,138,.14); color: #ffc58a;
  border: 1.5px solid rgba(255,197,138,.35); }
.outro .follow { position: absolute; top: 1160px; left: 0; right: 0; text-align: center; font-size: 40px; color: rgba(247,239,229,.75); }
.outro .handle { position: absolute; top: 1222px; left: 0; right: 0; text-align: center; font-size: 66px; font-weight: 700; color: #ffc58a; direction: ltr; letter-spacing: .02em; }
.outro .risk { position: absolute; top: 1420px; left: 110px; right: 110px; text-align: center; font-size: 28px; color: rgba(247,239,229,.55); line-height: 1.5; }
</style></head><body>
<canvas id="bg" width="1080" height="1920"></canvas>
<div id="stage"></div>
<div id="brand"><img src="__LOGO__" alt=""><div><b>PHOENIX HAZ SMC</b><small>THE PHOENIX HAZ SYNDICATE</small></div></div>
<div id="sample"><span>نموذج للتجربة · أرقام وهمية</span></div>
<div id="fade"></div>
<script>
const D = __DATA__, LOGO = "__LOGO__";
const $ = (s, r) => (r || document).querySelector(s);
const clamp = (x, a, b) => Math.min(b === undefined ? 1 : b, Math.max(a || 0, x));
const E = { out: p => 1 - Math.pow(1 - p, 3), inOut: p => p < .5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2, lin: p => p,
  back: p => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(p - 1, 3) + c1 * Math.pow(p - 1, 2); } };
const P = (t, a, d, e) => (e || E.out)(clamp((t - a) / d));
const fmt = (v, dp) => Number(v).toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp });
const money = v => (v >= 0 ? "+" : "−") + "$" + fmt(Math.abs(v), 2);
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fract = x => x - Math.floor(x);
const TICK = '<svg viewBox="0 0 24 24"><path d="M5 12.5l4.2 4.2L19 7" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const ARROW = d => d === 1 ? '<svg viewBox="0 0 20 20"><path d="M10 3l7 11H3z" fill="currentColor"/></svg>' : '<svg viewBox="0 0 20 20"><path d="M10 17L3 6h14z" fill="currentColor"/></svg>';
function look(el, o, x, y, s) { el.style.opacity = o; el.style.transform = `translate(${x || 0}px,${y || 0}px) scale(${s === undefined ? 1 : s})`; }
function make(cls, html) { const d = document.createElement("div"); d.className = "scene " + cls; d.innerHTML = html; $("#stage").appendChild(d); return d; }
const withEl = (el, f) => { f.el = el; return f; };

// the background: warm dark, a slow glow, embers rising
const bg = $("#bg").getContext("2d");
const EMB = Array.from({ length: 64 }, (_, i) => ({ x: fract(Math.sin(i * 12.9898) * 43758.5453) * 1080, sp: 45 + fract(Math.sin(i * 78.233) * 9631.7) * 95,
  sz: 1.6 + fract(Math.sin(i * 39.425) * 3758.1) * 3.6, ph: fract(Math.sin(i * 4.13) * 917.3) * 10, sw: 12 + fract(Math.sin(i * 7.7) * 311.1) * 26 }));
function drawBg(t) {
  const g = bg, gr = g.createLinearGradient(0, 0, 0, 1920);
  gr.addColorStop(0, "#1b120c"); gr.addColorStop(.55, "#0e0b0a"); gr.addColorStop(1, "#06070a");
  g.fillStyle = gr; g.fillRect(0, 0, 1080, 1920);
  const gx = 880 + Math.sin(t * .35) * 140, gy = -60 + Math.cos(t * .28) * 70, rg = g.createRadialGradient(gx, gy, 0, gx, gy, 1150);
  rg.addColorStop(0, "rgba(228,104,42,.46)"); rg.addColorStop(1, "rgba(228,104,42,0)"); g.fillStyle = rg; g.fillRect(0, 0, 1080, 1920);
  const r2 = g.createRadialGradient(60, 1960, 0, 60, 1960, 950); r2.addColorStop(0, "rgba(255,197,138,.14)"); r2.addColorStop(1, "rgba(255,197,138,0)");
  g.fillStyle = r2; g.fillRect(0, 0, 1080, 1920);
  for (const e of EMB) {
    const y = 1990 - ((t * e.sp + e.ph * 210) % 2120), x = e.x + Math.sin(t * .8 + e.ph) * e.sw, a = .22 + .34 * (.5 + .5 * Math.sin(t * 3 + e.ph * 5));
    g.fillStyle = `rgba(255,${150 + Math.round(55 * Math.sin(e.ph))},70,${a.toFixed(3)})`; g.beginPath(); g.arc(x, y, e.sz, 0, 6.2832); g.fill();
  }
}
function leave(el, lt, dur) { const q = P(lt, dur - .42, .42, E.inOut); el.style.opacity = 1 - q; el.style.transform = `scale(${1 + .05 * q})`; }

// ── the scenes
const B = {};
B.intro = sc => {
  const el = make("intro", `<div class="logo-wrap"><div class="glow"></div><div class="halo"></div><img src="${LOGO}"></div>
    <h1>PHOENIX HAZ SMC</h1><p class="syn">THE PHOENIX HAZ SYNDICATE</p><p class="sub">${esc(sc.sub)}</p>`);
  const w = $(".logo-wrap", el), halo = $(".halo", el), glow = $(".glow", el), h1 = $("h1", el), syn = $(".syn", el), sub = $(".sub", el);
  return withEl(el, lt => {
    el.style.opacity = 1; el.style.transform = "";
    const p = P(lt, .12, .9, E.back);
    look(w, P(lt, .05, .35), 0, 0, .55 + .45 * p);
    halo.style.transform = `rotate(${lt * 70}deg)`; glow.style.opacity = .6 + .4 * Math.sin(lt * 3);
    const q = P(lt, .7, .7); look(h1, q, 0, 50 * (1 - q)); h1.style.letterSpacing = (.5 - .3 * q).toFixed(3) + "em";
    const s = P(lt, .95, .6); look(syn, s, 0, 30 * (1 - s));
    const u = P(lt, 1.15, .6); look(sub, u, 0, 30 * (1 - u));
    leave(el, lt, sc.dur);
  });
};
function numbers(sc, cls) {
  const tiles = sc.tiles.map(([v, l, c, u]) => `<div class="${c}"><b class="n">0${u || ""}</b><i>${esc(l)}</i></div>`).join("");
  const rows = (sc.syms || []).map(([s, ar, w, l, b]) => `<div class="row"><span>${esc(ar)}</span><div class="bar"><span class="w"></span><span class="l"></span><span class="b"></span></div><span class="wl n">${w} / ${l}</span></div>`).join("");
  const C = 2 * Math.PI * 150;
  const ring = sc.rate === null ? "" : `<div class="ring"><svg viewBox="0 0 340 340"><circle cx="170" cy="170" r="150" fill="none" stroke="rgba(255,107,94,.28)" stroke-width="22"/>
    <circle class="arc" cx="170" cy="170" r="150" fill="none" stroke="#3ddc84" stroke-width="22" stroke-linecap="round" stroke-dasharray="${C}" stroke-dashoffset="${C}"/></svg>
    <div class="lab"><b class="n">0%</b><i>نسبة الربح</i></div></div>`;
  const usdCls = sc.usd > 0 ? "win" : sc.usd < 0 ? "loss" : "be";
  const el = make(cls, `<p class="kicker">${esc(sc.kicker)}</p><h2 class="title">${esc(sc.title)}</h2>
    <div class="total ${usdCls}"><span class="n">${money(0)}</span></div><p class="note">${esc(sc.note)}</p>
    <div class="tiles" style="grid-template-columns:repeat(${sc.tiles.length},1fr)">${tiles}</div>${rows ? `<div class="syms">${rows}</div>` : ring}`);
  const kick = $(".kicker", el), title = $(".title", el), total = $(".total", el), tv = $(".total .n", el), note = $(".note", el);
  const tl = [...el.querySelectorAll(".tiles div")], arc = $(".arc", el), pct = $(".ring .lab b", el), ringEl = $(".ring", el);
  const rowEls = [...el.querySelectorAll(".syms .row")];
  return withEl(el, lt => {
    el.style.opacity = 1; el.style.transform = "";
    let p = P(lt, .05, .5); look(kick, p, 60 * (1 - p), 0);
    p = P(lt, .15, .55); look(title, p, 80 * (1 - p), 0);
    p = P(lt, .5, .5, E.back); look(total, P(lt, .45, .3), 0, 0, .7 + .3 * p);
    tv.textContent = money(sc.usd * P(lt, .55, 1.25));
    p = P(lt, .9, .5); look(note, p, 0, 20 * (1 - p));
    tl.forEach((d, i) => { const a = 1.0 + .13 * i, q = P(lt, a, .5, E.back); look(d, P(lt, a, .25), 0, 60 * (1 - P(lt, a, .5)), .85 + .15 * q);
      d.querySelector("b").textContent = Math.round(sc.tiles[i][0] * P(lt, a, .8)) + (sc.tiles[i][3] || ""); });
    if (ringEl) { const r = P(lt, 1.6, 1.3); look(ringEl, P(lt, 1.5, .4), 0, 0, .9 + .1 * P(lt, 1.5, .5, E.back));
      arc.style.strokeDashoffset = C * (1 - sc.rate / 100 * r); pct.textContent = Math.round(sc.rate * r) + "%"; }
    rowEls.forEach((row, i) => { const a = 1.55 + .14 * i, q = P(lt, a, .5); look(row, q, -50 * (1 - q), 0);
      const [, , w, l, b] = sc.syms[i], n = Math.max(1, w + l + b), g = P(lt, a + .2, .9), sp = row.querySelectorAll(".bar span");
      sp[0].style.width = (100 * w / n * g) + "%"; sp[1].style.width = (100 * l / n * g) + "%"; sp[2].style.width = (100 * b / n * g) + "%"; });
    leave(el, lt, sc.dur);
  });
}
B.summary = sc => numbers(sc, "summary");
B.week = sc => numbers(sc, "week");

B.trade = sc => {
  const T = sc.trade, S = sc.sched, buy = T.dir === 1;
  const el = make("trade", `<div class="badge">${TICK}صفقة رابحة · ${esc(T.reached)}</div>
    <div class="symrow"><h1>${esc(T.sym)}</h1><span class="ar">${esc(T.ar)}</span><span class="chip">${esc(T.tf)}</span>
    <span class="dir ${buy ? "buy" : "sell"}">${ARROW(T.dir)}${buy ? "BUY" : "SELL"}</span></div>
    <canvas class="chart" width="900" height="840"></canvas>
    <div class="result"><span class="big">+0</span><span class="unit">نقطة</span></div>
    <p class="sub2"><span class="n">${esc(T.usd)}</span> على لوت <span class="n">${esc(T.lot)}</span>، بعد السبريد والعمولة<br>مدّتها ${esc(T.took)}</p>`);
  const badge = $(".badge", el), symrow = $(".symrow", el), cv = $(".chart", el), g = cv.getContext("2d");
  const res = $(".result", el), big = $(".result .big", el), sub2 = $(".sub2", el);
  const bars = T.bars, n = bars ? bars.length : 0;
  const levels = [{ p: T.sl, c: "#ff6b5e", tag: "الستوب", dash: [14, 10] }, { p: T.entry, c: "#ffc58a", tag: "الدخول", dash: [] }]
    .concat(T.tps.map((p, k) => ({ p, c: "#3ddc84", tag: "TP" + (k + 1), dash: [14, 10], k })));
  let hi = Math.max(...levels.map(l => l.p)), lo = Math.min(...levels.map(l => l.p));
  if (bars) for (const b of bars) { hi = Math.max(hi, b[2]); lo = Math.min(lo, b[3]); }
  const pad = (hi - lo) * .07; hi += pad; lo -= pad;
  const CW = 900, CH = 840, X0 = 26, X1 = CW - 250, Y0 = 34, Y1 = CH - 34, step = (X1 - X0) / Math.max(1, n);
  const xs = i => X0 + (i + .5) * step, ys = p => Y0 + (hi - p) / (hi - lo) * (Y1 - Y0);
  const shown = lt => {
    if (!bars) return 0;
    if (lt < S.a0) return 0;
    if (lt < S.a1) return (T.fill + 1) * (lt - S.a0) / (S.a1 - S.a0);
    if (lt < S.b0) return T.fill + 1;
    if (lt < S.b1) return T.fill + 1 + (T.last - T.fill) * (lt - S.b0) / (S.b1 - S.b0);
    return T.last + 1;
  };
  function pill(y, l, hit, s) {
    const w = 236, h = 56, x = CW - w - 4;
    g.save(); g.translate(x + w / 2, y); g.scale(s, s); g.translate(-(x + w / 2), -y);
    g.fillStyle = hit ? l.c : "rgba(12,12,14,.92)"; g.strokeStyle = l.c; g.lineWidth = 2.5;
    g.beginPath(); g.roundRect(x, y - h / 2, w, h, 16); g.fill(); g.stroke();
    g.fillStyle = hit ? "#07140c" : l.c; g.font = "600 25px Readex"; g.textBaseline = "middle";
    g.textAlign = "right"; g.fillText((hit ? "✓ " : "") + l.tag, x + w - 16, y + 1);
    g.textAlign = "left"; g.fillText(fmt(l.p, T.dg), x + 14, y + 1);
    g.restore();
  }
  function draw(lt) {
    g.clearRect(0, 0, CW, CH);
    g.fillStyle = "rgba(255,255,255,.035)"; g.strokeStyle = "rgba(255,255,255,.08)"; g.lineWidth = 2;
    g.beginPath(); g.roundRect(1, 1, CW - 2, CH - 2, 34); g.fill(); g.stroke();
    g.strokeStyle = "rgba(255,255,255,.05)"; g.lineWidth = 1.5;
    for (let k = 1; k < 6; k++) { const y = Y0 + (Y1 - Y0) * k / 6; g.beginPath(); g.moveTo(X0, y); g.lineTo(X1, y); g.stroke(); }
    const sh = shown(lt), full = Math.floor(sh), frac = sh - full;
    // the move in profit: from the entry to the best price reached so far
    if (bars && sh > T.fill + 1) {
      let best = T.entry; for (let i = T.fill; i < Math.min(full + 1, T.last + 1, n); i++) best = buy ? Math.max(best, bars[i][2]) : Math.min(best, bars[i][3]);
      best = buy ? Math.min(best, T.tps[Math.max(0, T.hits - 1)] + (hi - lo)) : best;
      const ya = ys(T.entry), yb = ys(best), xa = xs(T.fill) - step / 2, xb = xs(Math.min(full, T.last)) + step / 2;
      const gr = g.createLinearGradient(0, Math.min(ya, yb), 0, Math.max(ya, yb));
      gr.addColorStop(buy ? 0 : 1, "rgba(61,220,132,.26)"); gr.addColorStop(buy ? 1 : 0, "rgba(61,220,132,.03)");
      g.fillStyle = gr; g.fillRect(xa, Math.min(ya, yb), xb - xa, Math.abs(yb - ya));
    }
    // the candles
    if (bars) for (let i = 0; i < Math.min(n, full + 1); i++) {
      const b = bars[i], a = i < full ? 1 : frac; if (a <= 0) continue;
      const up = b[4] >= b[1], ctx = i < T.fill;
      g.globalAlpha = a * (ctx ? .5 : 1); g.strokeStyle = g.fillStyle = up ? "#3ddc84" : "#ff6b5e";
      const x = xs(i), w = Math.max(3, step * .62); g.lineWidth = Math.max(1.5, step * .1);
      g.beginPath(); g.moveTo(x, ys(b[2])); g.lineTo(x, ys(b[3])); g.stroke();
      const y1 = ys(Math.max(b[1], b[4])), y2 = ys(Math.min(b[1], b[4])); g.fillRect(x - w / 2, y1, w, Math.max(2, y2 - y1));
    }
    g.globalAlpha = 1;
    // the levels: drawn across, then the targets light up when they are reached
    const lp = P(lt, S.l0, .55, E.inOut);
    if (lp > 0) levels.forEach(l => {
      const y = ys(l.p), x0 = bars ? xs(T.fill) - step / 2 : X0, hit = l.k !== undefined && l.k < T.hits && lt >= S.hit[l.k];
      g.save(); g.strokeStyle = l.c; g.globalAlpha = hit ? 1 : .85; g.lineWidth = l.tag === "الدخول" ? 3.5 : 2.5; g.setLineDash(l.dash);
      g.beginPath(); g.moveTo(x0, y); g.lineTo(x0 + (X1 - x0) * lp, y); g.stroke(); g.restore();
      const s = hit ? 1 + .22 * (1 - P(lt, S.hit[l.k], .35)) : 1;
      g.globalAlpha = lp; pill(y, l, hit, s); g.globalAlpha = 1;
    });
    // without candles: a light runs up the ladder from the entry to the targets
    if (!bars && lt > S.b0) {
      const k = T.hits ? T.tps[T.hits - 1] : T.entry, p = P(lt, S.b0, S.b1 - S.b0, E.inOut), y = ys(T.entry + (k - T.entry) * p), x = X0 + 110;
      g.strokeStyle = "rgba(61,220,132,.9)"; g.lineWidth = 12; g.lineCap = "round"; g.beginPath(); g.moveTo(x, ys(T.entry)); g.lineTo(x, y); g.stroke();
      const rg = g.createRadialGradient(x, y, 0, x, y, 46); rg.addColorStop(0, "rgba(61,220,132,.95)"); rg.addColorStop(1, "rgba(61,220,132,0)");
      g.fillStyle = rg; g.beginPath(); g.arc(x, y, 46, 0, 6.2832); g.fill();
    }
  }
  return withEl(el, lt => {
    el.style.opacity = 1; el.style.transform = "";
    let p = P(lt, 0, .45, E.back); look(badge, P(lt, 0, .3), 0, 0, .8 + .2 * p);
    p = P(lt, .1, .5); look(symrow, p, 70 * (1 - p), 0);
    look(cv, P(lt, .2, .4), 0, 30 * (1 - P(lt, .2, .5)));
    draw(lt);
    p = P(lt, S.r0, .5, E.back); look(res, P(lt, S.r0, .25), 0, 0, .7 + .3 * p);
    big.textContent = "+" + Math.round(parseFloat(String(T.pts).replace(/,/g, "")) * P(lt, S.r0, .9)).toLocaleString("en-US");
    p = P(lt, S.r0 + .35, .5); look(sub2, p, 0, 20 * (1 - p));
    leave(el, lt, sc.dur);
  });
};

B.how = sc => {
  const buy = sc.dir === 1;
  const lines = sc.lines.map(([k, v, c]) => `<div class="ln ${c}"><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join("");
  const oks = sc.hits.map(([h, pts]) => `<div class="bub ok">${TICK}<span>${esc(h)}${pts ? ` · <span class="n">+${esc(pts)}</span> نقطة` : ""}</span></div>`).join("");
  const el = make("how", `<p class="kicker">${esc(sc.kicker)}</p>
    <div class="phone"><div class="notch"></div><div class="ph-head"><img src="${LOGO}"><div><b>Phoenix HT SMC</b><small>بوت الإشارات</small></div></div>
    <div class="chat"><div class="typing"><i></i><i></i><i></i></div>
    <div class="bub sig"><div class="hd"><span class="${buy ? "win" : "loss"}">${buy ? "BUY" : "SELL"}</span><span>${esc(sc.sym)}</span><span style="color:#ffc58a">${esc(sc.tf)}</span></div>${lines}</div>${oks}</div></div>
    <div class="steps">${sc.steps.map((s, i) => `<div class="step"><i>${i + 1}</i>${esc(s)}</div>`).join("")}</div>`);
  const kick = $(".kicker", el), phone = $(".phone", el), typing = $(".typing", el), sig = $(".bub.sig", el);
  const ok = [...el.querySelectorAll(".bub.ok")], steps = [...el.querySelectorAll(".step")], dots = [...el.querySelectorAll(".typing i")];
  return withEl(el, lt => {
    el.style.opacity = 1; el.style.transform = "";
    let p = P(lt, 0, .5); look(kick, p, 0, -30 * (1 - p));
    p = P(lt, .1, .7, E.back); look(phone, P(lt, .1, .35), 0, 160 * (1 - P(lt, .1, .7)), .92 + .08 * p);
    const ty = lt >= sc.bub[0] && lt < sc.bub[1]; typing.style.display = lt < sc.bub[1] ? "flex" : "none";
    typing.style.opacity = ty ? 1 : 0; dots.forEach((d, i) => d.style.opacity = .35 + .65 * (.5 + .5 * Math.sin(lt * 9 - i * .9)));
    p = P(lt, sc.bub[1], .4, E.back); look(sig, P(lt, sc.bub[1], .2), 0, 0, .85 + .15 * p); sig.style.display = lt < sc.bub[1] ? "none" : "block";
    ok.forEach((b, i) => { const a = sc.bub[2 + i]; b.style.display = lt < a ? "none" : "flex"; const q = P(lt, a, .35, E.back); look(b, P(lt, a, .2), 0, 0, .85 + .15 * q); });
    steps.forEach((s, i) => { const a = [sc.bub[1], sc.bub[1] + .5, sc.bub[2] || sc.bub[1] + 1][i] + .1, q = P(lt, a, .5); look(s, q, 60 * (1 - q), 0); });
    leave(el, lt, sc.dur);
  });
};

B.outro = sc => {
  const el = make("outro", `<img src="${LOGO}"><p class="cta">${esc(sc.cta)}</p><div class="pills">${sc.pills.map(p => `<span>${esc(p)}</span>`).join("")}</div>
    <p class="follow">تابعنا</p><p class="handle">${esc(D.handle)}</p><p class="risk">${esc(D.risk)}</p>`);
  const img = $("img", el), cta = $(".cta", el), pills = [...el.querySelectorAll(".pills span")], fol = $(".follow", el), hnd = $(".handle", el), risk = $(".risk", el);
  return withEl(el, lt => {
    el.style.opacity = 1; el.style.transform = "";
    let p = P(lt, 0, .6, E.back); look(img, P(lt, 0, .3), 0, 0, .6 + .4 * p);
    p = P(lt, .25, .55); look(cta, p, 0, 40 * (1 - p));
    pills.forEach((s, i) => { const q = P(lt, .6 + .12 * i, .45, E.back); look(s, P(lt, .6 + .12 * i, .2), 0, 0, .7 + .3 * q); });
    p = P(lt, 1.1, .5); look(fol, p, 0, 20 * (1 - p));
    p = P(lt, 1.25, .55, E.back); look(hnd, P(lt, 1.25, .3), 0, 0, .8 + .2 * p);
    p = P(lt, 1.6, .6); look(risk, p, 0, 0);
  });
};

const SC = D.scenes.map(sc => ({ sc, draw: B[sc.kind](sc) }));
const brand = $("#brand"), fade = $("#fade");
if (D.sample) $("#sample").style.display = "block";
window.seek = t => {
  drawBg(t);
  for (const { sc, draw } of SC) {
    const lt = t - sc.start;
    if (lt < 0 || lt > sc.dur) { draw.el.style.opacity = 0; continue; }
    draw(lt);
  }
  const intro = D.scenes[0], out = D.scenes[D.scenes.length - 1], bt = t - (intro.start + intro.dur - .25);
  const ob = t - out.start;
  brand.style.opacity = clamp(bt / .4) * (1 - clamp(ob / .3));
  fade.style.opacity = clamp((t - (D.dur - .5)) / .5);
};
document.fonts.ready.then(() => { const im = [...document.images].map(i => i.complete ? 1 : new Promise(r => { i.onload = i.onerror = r; }));
  Promise.all(im).then(() => { window.seek(0); window.ready = true; }); });
</script></body></html>"""


def _data_uri(path, mime):
    with open(path, "rb") as fh:
        return f"data:{mime};base64," + base64.b64encode(fh.read()).decode()


def page_html(story):
    data = json.dumps({k: v for k, v in story.items() if k != "sfx"}, ensure_ascii=False).replace("</", "<\\/")
    return (PAGE.replace("__FONT__", _data_uri(content.FONT, "font/ttf")).replace("__LOGO__", _data_uri(LOGO, "image/jpeg"))
            .replace("__DATA__", data))


# ───────────────────────────── the sound: our own music and effects ─────────────────────────────
def _hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def soundtrack(story, path, bpm=96):
    """Original music (a warm minor pad, a soft bass and a half-time beat that drops after the intro) and the effects
    on the story's times: a boom under the logo, a whoosh into every scene, a bell on every target, a sparkle on the
    totals. Written note by note here, so the video can be posted anywhere."""
    import numpy as np
    rng = np.random.default_rng(7)
    dur = story["dur"] + 0.6
    n = int(dur * SR)
    out = np.zeros((n, 2))
    beat, bar = 60.0 / bpm, 240.0 / bpm

    def add(start, sig, gain=1.0, pan=0.0):
        i = int(start * SR)
        if i >= n or i < 0:
            return
        sig = sig[: n - i]
        a = (pan + 1) * math.pi / 4
        out[i:i + len(sig), 0] += sig * gain * math.cos(a)
        out[i:i + len(sig), 1] += sig * gain * math.sin(a)

    def tt(sec):
        return np.arange(int(sec * SR)) / SR

    def band(x, lo, hi):
        X = np.fft.rfft(x)
        f = np.fft.rfftfreq(len(x), 1 / SR)
        X[(f < lo) | (f > hi)] = 0
        return np.fft.irfft(X, len(x))

    # the pad: Am – F – C – G, two bars each, soft and wide
    prog = [(57, 60, 64, 69), (53, 57, 60, 65), (48, 52, 55, 60), (55, 59, 62, 67)]
    seg = 2 * bar
    k = 0
    while k * seg < dur:
        length = seg + 0.8
        x = tt(length)
        env = np.minimum(1, x / 0.7) * np.where(x > seg, np.exp(-(x - seg) * 5), 1.0)
        for side, det in ((-0.7, -0.08), (0.7, 0.08)):
            sig = np.zeros_like(x)
            for m in prog[k % 4]:
                f = _hz(m) * 2 ** (det / 12)
                for h, amp in ((1, 1.0), (2, 0.32), (3, 0.12), (4, 0.05)):
                    sig += amp * np.sin(2 * np.pi * f * h * x + h * m)
            add(k * seg, sig * env * 0.010, pan=side)
        k += 1
    drop = story.get("drop", INTRO)
    # the bass and the beat, from the drop to the last second
    t0 = drop
    i = 0
    while t0 + i * beat < story["dur"] - 0.6:
        at = t0 + i * beat
        pos = i % 8                                   # 8 beats = 2 bars
        root = prog[int((at // seg) % 4)][0] - 24
        if pos % 4 == 0:                              # the kick: beat 1, and a ghost before beat 3
            x = tt(0.42)
            ph = 2 * np.pi * np.cumsum(46 + 80 * np.exp(-x * 32)) / SR
            add(at, np.sin(ph) * np.exp(-x * 7) * 0.55)
            x = tt(0.38)
            add(at + 1.75 * beat, np.sin(2 * np.pi * np.cumsum(46 + 70 * np.exp(-x * 32)) / SR) * np.exp(-x * 8) * 0.32)
        if pos % 4 == 2:                              # the clap on beat 3
            x = tt(0.3)
            nz = band(rng.standard_normal(len(x)), 900, 7000)
            env = np.exp(-x * 16) + 0.6 * np.exp(-np.maximum(0, x - 0.012) * 40) * (x > 0.012)
            add(at, nz * env * 0.09, pan=0.1)
        for h in (0, 0.5):                            # hats on the eighths
            x = tt(0.07)
            nz = band(rng.standard_normal(len(x)), 7000, 16000)
            add(at + h * beat, nz * np.exp(-x * 70) * (0.05 if h else 0.07), pan=-0.25)
        if pos in (0, 3, 4):                          # the bass, under the chord's root
            x = tt(0.5)
            f = _hz(root + 12)
            sig = (np.sin(2 * np.pi * f * x) + 0.25 * np.sin(4 * np.pi * f * x)) * np.minimum(1, x / 0.006) * np.exp(-x * 4.5)
            add(at, sig * 0.16)
        i += 1
    # the effects
    for at, kind in story["sfx"]:
        if kind == "boom":
            x = tt(2.0)
            ph = 2 * np.pi * np.cumsum(40 + 50 * np.exp(-x * 4)) / SR
            add(at, np.sin(ph) * np.exp(-x * 2.2) * 0.55)
            nz = band(rng.standard_normal(len(x)), 60, 900)
            add(at, nz * np.exp(-x * 5) * 0.08)
        elif kind == "whoosh":
            x = tt(0.62)
            nz = band(rng.standard_normal(len(x)), 300, 5000)
            env = np.where(x < 0.42, (x / 0.42) ** 2, np.exp(-(x - 0.42) * 18))
            add(at, nz * env * 0.06, pan=-0.3)
            add(at + 0.01, nz * env * 0.06, pan=0.3)
        elif kind.startswith("ding"):
            k = int(kind[4:] or 0)
            f = (1318.5, 1568.0, 2093.0, 2349.3)[min(k, 3)]
            x = tt(1.4)
            sig = sum(a * np.sin(2 * np.pi * f * m * x) * np.exp(-x * d) for m, a, d in ((1, 1, 3.2), (2.0, .3, 5), (3.01, .16, 8)))
            add(at, sig * np.minimum(1, x / 0.003) * 0.2)
        elif kind == "sparkle":
            for j, m in enumerate((84, 88, 91, 96)):
                x = tt(0.6)
                add(at + 0.045 * j, np.sin(2 * np.pi * _hz(m) * x) * np.exp(-x * 7) * 0.07, pan=-0.4 + 0.27 * j)
        elif kind == "pop":
            x = tt(0.12)
            f = 700 + 600 * np.minimum(1, x / 0.05)
            add(at, np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-x * 30) * 0.14)
        elif kind == "hit":
            x = tt(1.6)
            add(at, np.sin(2 * np.pi * np.cumsum(45 + 90 * np.exp(-x * 30)) / SR) * np.exp(-x * 6) * 0.5)
            nz = band(rng.standard_normal(len(x)), 3000, 15000)
            add(at, nz * np.exp(-x * 2.6) * 0.035)
    fade_in = np.minimum(1, np.arange(n) / (0.05 * SR))
    fade_out = np.clip((story["dur"] - np.arange(n) / SR) / 1.2, 0, 1)
    out *= (fade_in * fade_out)[:, None]
    out = np.tanh(out * 1.6) / np.tanh(1.6)
    peak = float(np.max(np.abs(out))) or 1.0
    pcm = (out / peak * 0.89 * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return path


# ───────────────────────────── making the film ─────────────────────────────
def ffmpeg_exe():
    exe = shutil.which(ENV("FFMPEG") or "ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _browser(p):
    """Playwright's own Chromium, else the Chrome the runner already has."""
    args = ["--no-sandbox", "--hide-scrollbars", "--mute-audio", "--force-color-profile=srgb", "--disable-gpu"]
    try:
        return p.chromium.launch(args=args)
    except Exception:
        chrome = content.find_chrome()
        if not chrome:
            raise
        return p.chromium.launch(executable_path=chrome, args=args)


def render(story, out_mp4, workdir):
    """Every frame drawn in Chrome, put together by ffmpeg with the soundtrack. Returns the MP4's path."""
    from playwright.sync_api import sync_playwright
    ff = ffmpeg_exe()
    if not ff:
        raise RuntimeError("no ffmpeg")
    src = os.path.join(workdir, "video.html")
    with open(src, "w", encoding="utf-8") as fh:
        fh.write(page_html(story))
    wav = None
    try:
        wav = soundtrack(story, os.path.join(workdir, "sound.wav"))
    except Exception as ex:                                   # no numpy: a film without sound is still a film
        log.warning("no soundtrack: %s", type(ex).__name__)
    frames = int(math.ceil(story["dur"] * FPS))
    cmd = [ff, "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "mjpeg", "-i", "-"]
    cmd += ["-i", wav] if wav else []
    cmd += ["-map", "0:v"] + (["-map", "1:a", "-c:a", "aac", "-b:a", "160k"] if wav else [])
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-movflags", "+faststart", "-shortest", out_mp4]
    with sync_playwright() as p:
        browser = _browser(p)
        try:
            page = browser.new_page(viewport={"width": VW, "height": VH}, device_scale_factor=1)
            page.goto(Path(src).as_uri(), wait_until="load")
            page.wait_for_function("window.ready === true", timeout=30000)
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
            try:
                for f in range(frames):
                    page.evaluate(f"window.seek({f / FPS:.5f})")
                    proc.stdin.write(page.screenshot(type="jpeg", quality=90))
            finally:
                proc.stdin.close()
                code = proc.wait(timeout=600)
        finally:
            browser.close()
    if code or not os.path.isfile(out_mp4) or os.path.getsize(out_mp4) < 50_000:
        raise RuntimeError("no video")
    return out_mp4


# ───────────────────────────── the day's video and the week's ─────────────────────────────
def _feed(state):
    """Capital.com, when its key is here (the same account as the bot): the trades' real candles."""
    if not (ENV("CAPITAL_API_KEY") or "").strip():
        return None, {}
    return bot.CapitalFeed(), offsets_of(state)


def _infos(state, xs):
    feed, offs = _feed(state)
    out = []
    for x in xs:
        bars, tf = trade_bars(feed, x, offs) if feed else (None, None)
        out.append(trade_info(x, bars, tf))
    return out


def day_video(state, day, t, trades, out_dir):
    """(path, seconds) of the day's video, or None."""
    wins = sorted((x for x in trades if x["oc"] == 1), key=lambda x: -x["usd"])[:TOP_VIDEO]
    story = day_story(day, t, _infos(state, wins))
    path = os.path.join(out_dir, f"{day}-video.mp4")
    work = tempfile.mkdtemp(prefix="phoenix-video-")
    render(story, path, work)
    log.info("day video: %.1f s, %d trades shown", story["dur"], len(wins))
    return path, story["dur"]


def week_numbers(state, day):
    """The week of `day` (Monday to Sunday): the bot's ledger tally, by instrument, and its best winning trade."""
    mon, sun = analyst.week_of(day)
    rows = [x for x in analyst.trades_of((state or {}).get("ledger")) if mon <= x["td"] <= sun]
    best = None
    for k in range(7):
        for x in content.closed_trades(state, mon + timedelta(days=k)):
            if x["oc"] == 1 and (best is None or x["usd"] > best["usd"]):
                best = x
    return mon, analyst.tally(rows), analyst.group(rows, lambda x: x["sym"]), best


def week_captions(mon, t):
    r = analyst.rate(t)
    rng = week_range(mon)
    ar = [f"🔥 بوت Phoenix للإشارات · أسبوع {rng}",
          f"✅ {t['win']} ربح · ❌ {t['loss']} خسارة · ⚪ {t['be']} رجعت عالدخول" + (f" · نسبة الربح {r}%" if r is not None else ""),
          "الصفقات بتوصل للمشتركين عالتلغرام لحظة بلحظة: الدخول والستوب والأهداف، وخبر عند كل هدف.", "",
          f"⚠️ {content.RISK}", "", "#PhoenixHAZ #تداول #فوركس #الذهب #ناسداك #بوت_تداول #XAUUSD #NAS100 #SMC"]
    en = [f"🔥 Phoenix signal bot · week of {mon.strftime('%d %b %Y')}",
          f"✅ {t['win']} wins · ❌ {t['loss']} losses · ⚪ {t['be']} breakeven" + (f" · {r}% win rate" if r is not None else ""),
          "Signals reach subscribers live on Telegram: entry, stop and targets, with an alert at every target.", "",
          "⚠️ Trading involves risk. Past results don't guarantee future ones.", "",
          "#PhoenixHAZ #tradingbot #forex #gold #XAUUSD #NAS100 #SMC #daytrading"]
    return "\n".join(ar), "\n".join(en)


def week_video(state, day, out_dir):
    """(path, seconds, tally, monday) of the week's video for the signal bot, or None when the week had no trades."""
    mon, t, by, best = week_numbers(state, day)
    if not t["n"]:
        return None
    info = _infos(state, [best])[0] if best else None
    story = week_story(mon, t, by, info)
    path = os.path.join(out_dir, f"{mon}-week-video.mp4")
    render(story, path, tempfile.mkdtemp(prefix="phoenix-video-"))
    log.info("week video: %.1f s, %d trades in the week", story["dur"], t["n"])
    return path, story["dur"], t, mon


def send_video(tg, path, caption, seconds):
    """The video as a Telegram video (plays in the chat, saves in full quality)."""
    try:
        with open(path, "rb") as fh:
            r = requests.post(f"https://api.telegram.org/bot{tg.token}/sendVideo",
                              data={"chat_id": tg.chat, "caption": caption, "parse_mode": "HTML", "supports_streaming": "true",
                                    "width": VW, "height": VH, "duration": int(round(seconds))},
                              files={"video": (os.path.basename(path), fh, "video/mp4")}, timeout=300)
        ok = r.status_code == 200 and r.json().get("ok")
        if not ok:
            log.warning("video refused: HTTP %s", r.status_code)
        return bool(ok)
    except (requests.RequestException, OSError, ValueError) as ex:
        log.warning("video not sent: %s", type(ex).__name__)
        return False


# ───────────────────────────── a sample, to see the style ─────────────────────────────
def _sample_bars(entry, d, tps, sl, sec, seed=3):
    """Made-up candles for the sample: a drift, a dip near the entry, then the climb through the targets."""
    import random
    rnd = random.Random(seed)
    risk = abs(entry - sl)
    bars, t, p = [], 1_700_000_000 // sec * sec, entry + d * risk * 1.2
    path = [entry + d * risk * (1.1 - 1.0 * i / (BEFORE - 1)) + rnd.uniform(-.25, .25) * risk for i in range(BEFORE)]
    path += [entry + (tps[-1] - entry) * (i / 16) + rnd.uniform(-.22, .22) * risk for i in range(1, 19)]
    for c in path:
        o = p
        h, l = max(o, c) + rnd.uniform(.05, .3) * risk, min(o, c) - rnd.uniform(.05, .3) * risk
        bars.append((t, o, h, l, c))
        t, p = t + sec, c
    return bars


def sample_story(kind):
    """A story with made-up trades (the video says so on every frame)."""
    sec = 300
    trades = []
    for k, (sym, d, entry, risk, tf, mult) in enumerate((("XAUUSD", 1, 4128.40, 3.1, "5m", 1),
                                                         ("NAS100", -1, 24810.5, 34.5, "15m", 1),
                                                         ("US30", 1, 46950.0, 38.0, "5m", 1))):
        tps = [round(entry + d * risk * r, 2) for r in (0.62, 1.0, 1.62)]
        sl = round(entry - d * risk, 2)
        bars = _sample_bars(entry, d, tps, sl, sec, seed=k + 3)
        dist = (tps[-1] - entry) * d
        x = {"o": {"trig": entry, "sl": sl, "tps": tps, "hits": 3, "risk": risk}, "sym": sym, "tf": tf, "dir": d,
             "dist": dist, "usd": bot.money(sym, dist - bot.cost_price(sym), content.LOT), "oc": 1,
             "opened": bars[BEFORE][0], "closed": bars[BEFORE + 17][0]}
        trades.append(trade_info(x, bars, tf))
    day = date.today() - timedelta(days=1)
    if kind == "week":
        mon = day - timedelta(days=day.weekday())
        t = {"n": 41, "win": 33, "loss": 6, "be": 2, "usd": 186.4}
        by = {"XAUUSD": {"n": 19, "win": 16, "loss": 2, "be": 1}, "NAS100": {"n": 12, "win": 9, "loss": 2, "be": 1},
              "US30": {"n": 10, "win": 8, "loss": 2, "be": 0}}
        return week_story(mon, t, by, trades[0], sample=True)
    t = {"n": 7, "win": 5, "loss": 1, "be": 1, "usd": 48.27}
    return day_story(day, t, trades, sample=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Phoenix Video: a sample video, to see the style")
    ap.add_argument("--sample", choices=("day", "week"), default="day")
    ap.add_argument("--out", default=".")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    os.makedirs(a.out, exist_ok=True)
    story = sample_story(a.sample)
    path = render(story, os.path.join(a.out, f"sample-{a.sample}.mp4"), tempfile.mkdtemp(prefix="phoenix-video-"))
    print(path, f"{story['dur']:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
