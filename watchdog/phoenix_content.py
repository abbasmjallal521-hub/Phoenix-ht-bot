#!/usr/bin/env python3
"""صانع المحتوى · Phoenix Content

Every morning it takes yesterday's closed trades of the signal bot and makes ready-to-post pictures for Instagram and
TikTok (1080x1350): a card of the whole day (every trade, the losses too) and a card for each of the best winning
trades (entry, stop, targets, result). It sends them to the owner on Telegram (the watchdog's bot) with a caption in
Arabic and one in English, ready to copy. Nothing is posted anywhere: the owner shares what he wants.

It reads the bot's saved state (phoenix_state.json, restored read-only from the Actions cache) and draws the cards in
HTML, photographed by the Chrome that GitHub's runner already has. Every card carries a risk line; no profit promises.
The log holds counts only: the repo is public.

  python watchdog/phoenix_content.py                     # yesterday (Beirut), sent on Telegram
  python watchdog/phoenix_content.py --day 2026-11-20    # that day
  python watchdog/phoenix_content.py --dry-run --out x/  # draw the cards into x/ and print the captions
"""
import argparse
import html
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE)]
import requests                   # noqa: E402
import phoenix_watchdog as wd     # noqa: E402  Telegram, owner_chat, time helpers
import phoenix_ht_bot as bot      # noqa: E402  the bot's instruments, money and day maths
import phoenix_analyst as analyst  # noqa: E402  the bot's ledger, read the same way as the analyst

log = logging.getLogger("content")
ENV = os.environ.get
FONT = os.path.join(HERE, "assets", "ReadexPro.ttf")
W, H = 1080, 1350
LOT = bot.LOT_DEFAULT
HANDLE = ENV("CONTENT_HANDLE") or "@phoenix.haz.syndi"
TOP_TRADES = 3                                 # winning trades that get a card of their own
LIST_MAX = 7                                   # trades listed on the day card
AR = {"XAUUSD": "الدهب", "XAGUSD": "الفضة", "US30": "الداو", "NAS100": "الناسداك", "USOIL": "النفط"}
MONTHS = ["كانون الثاني", "شباط", "آذار", "نيسان", "أيار", "حزيران", "تموز", "آب", "أيلول", "تشرين الأول",
          "تشرين الثاني", "كانون الأول"]
DONE = {bot.TP_HIT, bot.SL_HIT, bot.DAY_END, bot.BE_HIT, bot.LOCK_HIT}
RISK = "التداول فيه مخاطرة، والنتايج الماضية ما بتضمن الجاي."
FLAME = ('<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 30c-6.5-2.4-8.7-8.6-4.4-15.5.3 3.2 1.8 4.6 3.2 5.2'
         'C13.7 13 16.8 7.6 21.5 3c-.9 4.6.4 7.8 2.6 10.8 3.2 4.4 2.1 13.4-8.1 16.2Z" fill="#e4682a"/><path d="M16.3 '
         '27.4c-3.1-1.3-3.6-4.6-1.4-7.8.6 1.8 1.6 2.4 2.7 2.6.1-2.2 1.2-4 2.9-5.4.1 4.5 2.6 8.9-4.2 10.6Z" '
         'fill="#ffc58a"/></svg>')
TICK = ('<svg class="tick" viewBox="0 0 24 24"><path d="M5 12.5l4.2 4.2L19 7" fill="none" stroke="currentColor" '
        'stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/></svg>')
UP = '<svg class="arr" viewBox="0 0 20 20"><path d="M10 3l7 11H3z" fill="currentColor"/></svg>'
DOWN = '<svg class="arr" viewBox="0 0 20 20"><path d="M10 17L3 6h14z" fill="currentColor"/></svg>'
e = html.escape


# ───────────────────────────── the day's trades ─────────────────────────────
def load_state(path=None):
    try:
        with open(path or wd.BOT_STATE_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def closed_trades(state, day):
    """The orders that closed on trading day `day`, with their result, oldest first."""
    out = []
    for o in (state or {}).get("orders") or []:
        sym = o.get("sym")
        if sym not in bot.INSTRUMENTS or o.get("state") not in DONE or not o.get("exit_t") or not o.get("tps"):
            continue
        if bot.trading_day(o["exit_t"]) != day:
            continue
        exit_px = o.get("exit_px")
        if o.get("v20") and exit_px is not None:
            dist = (exit_px - o["trig"]) * o["dir"]                  # the bot books v20 trades at their exit
        else:
            dist = bot.realized(o, exit_px)
        net = dist - bot.cost_price(sym)
        oc = -1 if o["state"] == bot.SL_HIT else 1 if net > bot.INSTRUMENTS[sym]["tick"] else 2      # the bot's rule
        opened = o.get("fill_at") or o.get("fill_t") or o.get("born_t") or o["exit_t"]
        out.append({"o": o, "sym": sym, "tf": o.get("tf", ""), "dir": o.get("dir", 1), "dist": dist, "net": net,
                    "usd": bot.money(sym, net, LOT), "oc": oc, "opened": opened, "closed": o.get("exit_at") or o["exit_t"]})
    return sorted(out, key=lambda x: x["closed"])


def day_tally(state, day, trades):
    """W / L / back-at-entry and $ of the day from the bot's own ledger (the same numbers as its reports)."""
    rows = [x for x in analyst.trades_of(state.get("ledger")) if x["td"] == day] if state else []
    if not rows:                                                     # no ledger: count the orders themselves
        rows = [{"oc": x["oc"], "usd": x["usd"]} for x in trades]
    t = {"n": len(rows), "win": 0, "loss": 0, "be": 0, "usd": 0.0}
    for r in rows:
        t["usd"] += r["usd"]
        t["win" if r["oc"] == 1 else "loss" if r["oc"] == -1 else "be"] += 1
    return t


# ───────────────────────────── words ─────────────────────────────
def day_ar(d):
    return f"{wd.DAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}"


def money_txt(v):
    return f"{'+' if v >= 0 else '−'}${abs(v):,.2f}"


def price(sym, p):
    return f"{p:,.{bot.INSTRUMENTS[sym]['digits']}f}"


def tf_txt(tf):
    return tf.upper()


def clock_of(ts):
    return datetime.fromtimestamp(ts, wd.TZ).strftime("%H:%M")


def lot_note():
    big = sorted({AR[s] for s in bot.INSTRUMENTS if s in AR and bot.lot_for(s, LOT) > LOT})
    return f"على لوت {LOT:g}" + (f" ({' و'.join(big)} 0.1)" if big else "")


def captions(day, t, trades):
    best = max((x for x in trades if x["oc"] == 1), key=lambda x: x["usd"], default=None)
    r = round(100 * t["win"] / (t["win"] + t["loss"])) if t["win"] + t["loss"] else None
    ar = [f"🔥 نتايج مؤشر Phoenix HAZ SMC · {day_ar(day)}",
          f"✅ {t['win']} ربح · ❌ {t['loss']} خسارة · ⚪ {t['be']} رجعت عالدخول" + (f" · نسبة الربح {r}%" if r is not None else "")]
    en = [f"🔥 Phoenix HAZ SMC results · {day.strftime('%a %d %b %Y')}",
          f"✅ {t['win']} wins · ❌ {t['loss']} losses · ⚪ {t['be']} breakeven" + (f" · {r}% win rate" if r is not None else "")]
    if best:
        ar.append(f"أحسن صفقة: {best['sym']} {tf_txt(best['tf'])} · +{bot.pts(best['sym'], best['dist'])} نقطة")
        en.append(f"Best trade: {best['sym']} {tf_txt(best['tf'])} · +{bot.pts(best['sym'], best['dist'])} points")
    ar += ["الإشارات بتوصل للمشتركين عالتلغرام لحظة بلحظة: الدخول والستوب والأهداف.", "", f"⚠️ {RISK}", "",
           "#PhoenixHAZ #تداول #فوركس #الذهب #ناسداك #XAUUSD #NAS100 #US30 #SMC #ICT"]
    en += ["Signals go out live to subscribers on Telegram: entry, stop and targets.", "",
           "⚠️ Trading involves risk. Past results don't guarantee future ones.", "",
           "#PhoenixHAZ #forex #gold #XAUUSD #NAS100 #US30 #SMC #ICT #trading #daytrading"]
    return "\n".join(ar), "\n".join(en)


# ───────────────────────────── the cards (HTML, photographed by Chrome) ─────────────────────────────
CSS = """
@font-face { font-family: "Readex"; src: url("__FONT__") format("truetype"); font-weight: 160 700; }
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { width: 1080px; height: 1350px; }
body { font-family: "Readex", "DejaVu Sans", sans-serif; color: #f7efe5; overflow: hidden; position: relative;
  background: radial-gradient(105% 70% at 88% -8%, rgba(228,104,42,.5) 0%, rgba(228,104,42,0) 58%),
              radial-gradient(80% 55% at -5% 108%, rgba(255,197,138,.14) 0%, rgba(255,197,138,0) 62%),
              linear-gradient(165deg, #1c120c 0%, #0e0b0a 55%, #07080a 100%); }
.frame { position: absolute; inset: 34px; border-radius: 46px; border: 1.5px solid rgba(255,197,138,.22);
  padding: 52px 58px 44px; display: flex; flex-direction: column; }
.brand { display: flex; align-items: center; gap: 18px; direction: ltr; }
.brand svg { width: 64px; height: 64px; filter: drop-shadow(0 0 20px rgba(228,104,42,.6)); }
.brand b { display: block; font-size: 25px; font-weight: 600; letter-spacing: .16em; }
.brand small { display: block; font-size: 16px; font-weight: 500; letter-spacing: .34em; color: #ffc58a; margin-top: 5px; }
.n { direction: ltr; unicode-bidi: isolate; display: inline-block; }
.win { color: #3ddc84; } .loss { color: #ff6b5e; } .be { color: #cfc7bc; }
.kicker { margin-top: 54px; font-size: 30px; font-weight: 500; color: #ffc58a; }
h1 { font-size: 70px; line-height: 1.15; font-weight: 700; margin-top: 6px; }
.total { margin-top: 30px; font-size: 150px; line-height: 1; font-weight: 700; letter-spacing: -.02em; }
.sub { margin-top: 14px; font-size: 24px; color: rgba(247,239,229,.64); }
.tiles { margin-top: 40px; display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
.tiles div { border-radius: 26px; background: rgba(255,255,255,.055); border: 1px solid rgba(255,255,255,.07);
  padding: 22px 10px 18px; text-align: center; }
.tiles .n { font-size: 64px; font-weight: 700; line-height: 1.05; }
.tiles i { display: block; font-style: normal; font-size: 23px; color: rgba(247,239,229,.7); margin-top: 6px; }
.rate { margin-top: 30px; display: flex; align-items: center; gap: 22px; font-size: 26px; }
.rate .bar { flex: 1; height: 16px; border-radius: 99px; background: rgba(255,107,94,.35); overflow: hidden; }
.rate .bar span { display: block; height: 100%; border-radius: 99px; background: linear-gradient(90deg, #2bb673, #3ddc84); }
.rate b { font-weight: 700; color: #3ddc84; }
.list { list-style: none; margin-top: 32px; display: grid; gap: 12px; }
.list li { display: grid; grid-template-columns: 150px 1fr auto 210px; align-items: center; gap: 18px; font-size: 27px;
  padding: 13px 22px; border-radius: 20px; background: rgba(255,255,255,.04); }
.list .t { color: rgba(247,239,229,.55); font-size: 23px; }
.list .r { text-align: left; font-weight: 700; }
.list .more { display: block; text-align: center; color: rgba(247,239,229,.6); background: none; padding: 4px; font-size: 24px; }
.dir { display: inline-flex; align-items: center; gap: 8px; direction: ltr; font-weight: 700; font-size: 24px; letter-spacing: .06em; }
.dir.buy { color: #3ddc84; } .dir.sell { color: #ff6b5e; }
.arr { width: 22px; height: 22px; }
.sym { direction: ltr; font-weight: 600; } .sym em { font-style: normal; color: #ffc58a; margin-left: 8px; }
.foot { margin-top: auto; display: flex; justify-content: space-between; align-items: center; gap: 24px; padding-top: 24px;
  border-top: 1px solid rgba(255,197,138,.14); font-size: 21px; color: rgba(247,239,229,.6); }
.foot .handle { direction: ltr; color: #ffc58a; font-weight: 600; letter-spacing: .04em; white-space: nowrap; }
.badge { margin-top: 46px; align-self: flex-start; display: inline-flex; align-items: center; gap: 12px; font-size: 28px; font-weight: 600;
  padding: 10px 24px; border-radius: 99px; background: rgba(61,220,132,.14); color: #3ddc84; border: 1px solid rgba(61,220,132,.35); }
.badge .tick { width: 30px; height: 30px; }
.symrow { margin-top: 26px; display: flex; align-items: baseline; gap: 22px; flex-wrap: wrap; }
.symrow h1 { margin: 0; font-size: 96px; direction: ltr; letter-spacing: .01em; }
.symrow .ar { font-size: 40px; color: rgba(247,239,229,.75); }
.chip { font-size: 30px; font-weight: 600; padding: 4px 18px; border-radius: 14px; background: rgba(255,197,138,.14); color: #ffc58a; }
.symrow .dir { font-size: 32px; padding: 6px 18px; border-radius: 14px; background: rgba(255,255,255,.06); align-self: center; }
.ladder { position: relative; margin-top: 34px; height: 520px; border-radius: 32px; background: rgba(255,255,255,.035);
  border: 1px solid rgba(255,255,255,.06); }
.ladder .move { position: absolute; left: 214px; width: 12px; border-radius: 99px; background: linear-gradient(180deg, #3ddc84, rgba(61,220,132,.25)); }
.ladder .move.down { background: linear-gradient(0deg, #3ddc84, rgba(61,220,132,.25)); }
.ladder .row { position: absolute; left: 0; right: 0; display: flex; align-items: center; gap: 18px; padding: 0 34px; transform: translateY(-50%); }
.ladder .row .lab { font-size: 27px; font-weight: 600; display: inline-flex; align-items: center; gap: 10px; min-width: 210px; }
.ladder .row .line { flex: 1; height: 0; border-top: 2px dashed currentColor; opacity: .5; }
.ladder .row .px { direction: ltr; font-size: 27px; font-weight: 600; min-width: 170px; text-align: left; }
.ladder .tp { color: #3ddc84; } .ladder .tp.miss { color: rgba(247,239,229,.45); }
.ladder .en { color: #ffc58a; } .ladder .sl { color: #ff6b5e; }
.ladder .tick { width: 28px; height: 28px; }
.result { margin-top: 34px; display: flex; align-items: baseline; gap: 18px; }
.result .big { font-size: 128px; line-height: 1; font-weight: 700; letter-spacing: -.02em; }
.result .unit { font-size: 40px; font-weight: 600; color: rgba(247,239,229,.8); }
"""


def page(body):
    css = CSS.replace("__FONT__", Path(FONT).as_uri())
    return f'<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><style>{css}</style></head><body>{body}</body></html>'


def brand():
    return f'<div class="brand">{FLAME}<div><b>THE PHOENIX HAZ SYNDICATE</b><small>PHOENIX HAZ SMC</small></div></div>'


def foot():
    return f'<div class="foot"><span>{e(RISK)}</span><span class="handle">{e(HANDLE)}</span></div>'


def dir_html(d):
    return f'<span class="dir {"buy" if d == 1 else "sell"}">{UP if d == 1 else DOWN}{"BUY" if d == 1 else "SELL"}</span>'


def day_card(day, t, trades):
    cls = "win" if t["usd"] > 0 else "loss" if t["usd"] < 0 else "be"
    r = round(100 * t["win"] / (t["win"] + t["loss"])) if t["win"] + t["loss"] else None
    rate = (f'<div class="rate"><div class="bar"><span style="width:{r}%"></span></div>'
            f'<p>نسبة الربح <b class="n">{r}%</b></p></div>') if r is not None else ""
    rows = []
    for x in trades[-LIST_MAX:]:
        c = "win" if x["oc"] == 1 else "loss" if x["oc"] == -1 else "be"
        rows.append(f'<li>{dir_html(x["dir"])}<span class="sym">{e(x["sym"])}<em>{e(tf_txt(x["tf"]))}</em></span>'
                    f'<span class="t n">{clock_of(x["closed"])}</span><span class="r n {c}">{money_txt(x["usd"])}</span></li>')
    if len(trades) > LIST_MAX:
        rows.append(f'<li class="more">و{len(trades) - LIST_MAX} صفقات قبلهن</li>')
    body = (f'<div class="frame">{brand()}<p class="kicker">نتايج المؤشر</p><h1>{e(day_ar(day))}</h1>'
            f'<div class="total {cls}"><span class="n">{money_txt(t["usd"])}</span></div>'
            f'<p class="sub">مجموع اليوم {e(lot_note())}، بعد السبريد والعمولة</p>'
            f'<div class="tiles"><div><span class="n">{t["n"]}</span><i>صفقة</i></div>'
            f'<div class="win"><span class="n">{t["win"]}</span><i>ربح</i></div>'
            f'<div class="loss"><span class="n">{t["loss"]}</span><i>خسارة</i></div>'
            f'<div class="be"><span class="n">{t["be"]}</span><i>عالدخول</i></div></div>'
            f'{rate}<ul class="list">{"".join(rows)}</ul>{foot()}</div>')
    return page(body)


def ladder(x):
    """Stop, entry and targets on a price scale; the move from the entry to the last target reached."""
    o, sym = x["o"], x["sym"]
    tps, hits, entry, stop = o["tps"], o.get("hits", 0), o["trig"], o.get("sl", o.get("stop", o["trig"] - o["risk"] * o["dir"]))
    items = [("sl", "الستوب", stop, False), ("en", "الدخول", entry, False)]
    items += [("tp" + ("" if i < hits else " miss"), f"TP{i + 1}", p, i < hits) for i, p in enumerate(tps)]
    hi, lo = max(p for *_, p, _ in items), min(p for *_, p, _ in items)
    span, top, room = (hi - lo) or 1.0, 50.0, 420.0
    order = sorted(range(len(items)), key=lambda k: (hi - items[k][2]) / span)
    y = [top + (hi - items[k][2]) / span * room for k in order]
    gap = 58.0
    for i in range(1, len(y)):                                       # keep the labels apart ...
        y[i] = max(y[i], y[i - 1] + gap)
    if y[-1] > top + room:                                           # ... and inside the box
        y[-1] = top + room
        for i in range(len(y) - 2, -1, -1):
            y[i] = min(y[i], y[i + 1] - gap)
    fixed = {k: y[i] for i, k in enumerate(order)}
    rows = []
    for k, (cls, label, p, hit) in enumerate(items):
        mark = TICK if hit else ""
        rows.append(f'<div class="row {cls}" style="top:{fixed[k]:.0f}px"><span class="lab">{mark}{e(label)}</span>'
                    f'<span class="line"></span><span class="px">{price(sym, p)}</span></div>')
    reach = [fixed[2 + i] for i in range(hits)] if hits else []
    move = ""
    if reach:
        a, b = sorted((fixed[1], reach[-1]))
        move = f'<div class="move{" down" if x["dir"] == -1 else ""}" style="top:{a:.0f}px;height:{b - a:.0f}px"></div>'
    return f'<div class="ladder">{move}{"".join(rows)}</div>'


def trade_card(x):
    o, sym = x["o"], x["sym"]
    hits, n = o.get("hits", 0), len(o["tps"])
    reached = "وصلت كل الأهداف" if hits == n else f"وصلت TP{hits}" if hits else "ربح"
    mins = max(1, round((x["closed"] - x["opened"]) / 60))
    took = wd.dur(mins * 60)
    body = (f'<div class="frame">{brand()}<div class="badge">{TICK}صفقة رابحة · {e(reached)}</div>'
            f'<div class="symrow"><h1>{e(sym)}</h1><span class="ar">{e(AR.get(sym, ""))}</span>'
            f'<span class="chip n">{e(tf_txt(x["tf"]))}</span>{dir_html(x["dir"])}</div>'
            f'{ladder(x)}'
            f'<div class="result"><span class="big win n">+{bot.pts(sym, x["dist"])}</span><span class="unit">نقطة</span></div>'
            f'<p class="sub"><span class="n">{money_txt(x["usd"])}</span> على لوت <span class="n">{bot.lot_for(sym, LOT):g}</span>'
            f'، بعد السبريد والعمولة<br>مدّتها {e(took)} · <span class="n">{clock_of(x["opened"])} → {clock_of(x["closed"])}</span> بتوقيت بيروت</p>'
            f'{foot()}</div>')
    return page(body)


def find_chrome():
    for name in (ENV("CHROME"), "google-chrome", "google-chrome-stable", "chromium-browser", "chromium"):
        if name and (shutil.which(name) or os.path.isfile(name)):
            return shutil.which(name) or name
    return None


def shoot(chrome, html_text, png):
    src = png[:-4] + ".html"
    with open(src, "w", encoding="utf-8") as fh:
        fh.write(html_text)
    subprocess.run([chrome, "--headless", "--disable-gpu", "--no-sandbox", "--hide-scrollbars", "--mute-audio",
                    "--force-device-scale-factor=1", f"--window-size={W},{H}", "--virtual-time-budget=5000",
                    f"--screenshot={png}", Path(src).as_uri()], check=True, timeout=120, capture_output=True)
    if not os.path.isfile(png) or os.path.getsize(png) < 10_000:
        raise RuntimeError("no picture")
    return png


# ───────────────────────────── sending ─────────────────────────────
def send_album(tg, pngs, caption):
    """The pictures as one album (photos: easy to save on the phone), the caption on the first."""
    files, media = {}, []
    for i, p in enumerate(pngs[:10]):
        files[f"p{i}"] = open(p, "rb")
        media.append({"type": "photo", "media": f"attach://p{i}"})
    media[0].update(caption=caption, parse_mode="HTML")
    try:
        r = requests.post(f"https://api.telegram.org/bot{tg.token}/sendMediaGroup",
                          data={"chat_id": tg.chat, "media": json.dumps(media)}, files=files, timeout=120)
        ok = r.status_code == 200 and r.json().get("ok")
        if not ok:
            log.warning("album refused: HTTP %s", r.status_code)
        return bool(ok)
    except requests.RequestException as ex:
        log.warning("album not sent: %s", type(ex).__name__)
        return False
    finally:
        for f in files.values():
            f.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Phoenix Content: yesterday's trades as ready-to-post pictures")
    ap.add_argument("--day", default=ENV("CONTENT_DAY") or "", help="YYYY-MM-DD (default: yesterday in Beirut)")
    ap.add_argument("--dry-run", action="store_true", help="draw the cards and print the captions, send nothing")
    ap.add_argument("--out", default="", help="where to keep the pictures (default: a temporary folder)")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    day = date.fromisoformat(a.day) if a.day.strip() else wd.local_now().date() - timedelta(days=1)
    state = load_state()
    if state is None:
        log.warning("the bot's state was not found: nothing to make")
        return 0
    trades = closed_trades(state, day)
    t = day_tally(state, day, trades)
    log.info("day %s: %d trades closed", day.isoformat(), t["n"])
    if not t["n"]:
        return 0                                                    # a day without trades: nothing to post
    wins = sorted((x for x in trades if x["oc"] == 1), key=lambda x: -x["usd"])[:TOP_TRADES]
    out = a.out or tempfile.mkdtemp(prefix="phoenix-content-")
    os.makedirs(out, exist_ok=True)
    chrome = find_chrome()
    pngs = []
    if chrome:
        try:
            pngs.append(shoot(chrome, day_card(day, t, trades), os.path.join(out, f"{day}-day.png")))
            for i, x in enumerate(wins, 1):
                pngs.append(shoot(chrome, trade_card(x), os.path.join(out, f"{day}-trade{i}.png")))
        except (subprocess.SubprocessError, OSError, RuntimeError) as ex:
            log.warning("cards not drawn: %s", type(ex).__name__)
    else:
        log.warning("no Chrome found: captions only")
    ar, en = captions(day, t, trades)
    log.info("made %d pictures", len(pngs))
    if a.dry_run:
        print("\n".join(pngs), "\n", ar, "\n\n", en, sep="")
        return 0
    chat, source = wd.owner_chat()
    own = wd.clean_token(ENV("WATCHDOG_BOT_TOKEN"))
    tg = wd.Telegram(own or wd.clean_token(ENV("TELEGRAM_BOT_TOKEN")), chat)
    log.info("content goes to: %s, from %s", source or "nobody yet", "the watchdog's own bot" if own else "the signal bot")
    head = (f"🎬 <b>صانع المحتوى · {e(day_ar(day))}</b>\n"
            + ("جاهزين للإنستغرام والتيك توك. احفظ الصور، والكابشن تحت 👇" if pngs else "ما قدرت اعمل الصور هالمرة، بس هيدا الكابشن 👇")
            + ("\n📉 يوم خسارة: انشره بس إذا بدك تبيّن الشفافية." if t["usd"] < 0 else ""))
    ok = send_album(tg, pngs, head) if pngs else tg.send(head)
    ok = tg.send(e(ar)) and ok
    ok = tg.send(e(en)) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
