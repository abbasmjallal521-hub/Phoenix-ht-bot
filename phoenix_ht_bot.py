#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PHOENIX HAZ SMC — Telegram Signal Bot  (v29.2)
Developed by: The Phoenix HAZ Syndicate

Reads the market (Gold, Silver, Dow, Nasdaq, Oil), builds the same pending-order
plan as the Phoenix HAZ SMC indicator (range + ATR + 4-timeframe trend) and posts
each order to a Telegram channel: entry, stop, target, timeframe. It then follows
each order and posts when it is filled, hits the target, hits the stop, or expires.

v29.2 — SHORT messages: a new order is 7 lines (side and entry, stop, targets with $, trend, price now, lot), a
  fill 2 lines, a target 3 lines and one short sentence, a closing 2 lines (the last target with a congratulations).
  Each reader gets one language only (Arabic, or English with /lang en): no line twice any more.

v29.1 — the target messages: at every target the bot says the profit there for whoever closes, and how to secure
  the trade (move the stop) and carry on; the last target is a congratulations with every detail of the trade (the
  profit of each target, entry -> exit, the time it took); a trade that comes back to the entry after target 1 is
  told as "done after target 1" with the profit whoever closed at target 1 made. The stop rules did not change.

v29 (same rules and settings as the indicator v20.4; backtest "Phoenix HAZ v20.4 — backtest at all hours" in Google
  Drive) — THE PHOENIX HAZ SYNDICATE, development @Abbas Mjallal:
  INSTANT. The minute that is still forming is read every LIVE_SEC seconds (default 1) for every instrument with a
  waiting or open trade: a fill, a target, the stop or the closing is sent the moment the price touches it, not when
  the minute or the candle closes. Only the NEW high / low since the last read counts, so nothing is sent twice; the
  finished minute is checked again for what happened between two reads. A new order is sent about one second after
  its candle closes (it is read again every 2 seconds until the closed candle is there). Messages to the channel go
  out at once (one a second at most, 19 a minute, under Telegram's limits). Needs the Capital.com prices; with
  another price source the trades are followed on the finished minutes as before.
  ALL HOURS. No trading hours: every chart gives orders at any hour, with the setting tested at all hours (the
  MetaTrader 5 EA keeps its own hours). The trade size grows with the timeframe: the smallest AND the biggest move
  (in ATR) per chart, so 1 minute has small stops and targets and every higher timeframe a little bigger ones. Gold 1
  minute is on (ALLOW_1M=0 turns it off).
  MESSAGES. New, clearer messages in Arabic (English with /lang en): why the order is there (the liquidity above the
  swing high / below the swing low, the Fibonacci of the move and its order block), entry / stop / targets with $ at
  the lot shown after spread and commission, how long the order waited, how long the trade has been running and how
  long it took, the time of the fill and of the close, what to do at every target, and a short meaningful line under
  every result. Cancelled orders say why, in Arabic.

v28 (same rules as the indicator v20 and the MetaTrader 5 EA v4; backtests and the guide in Google Drive, folder
  "Phoenix HAZ SMC v20 — Fibonacci"):
  FIBONACCI ORDERS. At every chart candle close, for each side: the last swing high that is not broken yet gets a
  BUY STOP (a swing = a high above the L candles before it and not below the R candles after it). Its Fibonacci goes
  from the lowest point since the swing low before it (1.0, the base of the move with its order block) to the swing
  high (0.0): entry = 0.0, stop = beyond the tested Fibonacci level (0.786 / 1.0 ...) by a little ATR, targets = the
  Fibonacci extensions (0.382 / 0.618 / 1.0 / 1.618 of the move beyond the 0.0). A SELL STOP the same way down.
  One trade per swing, never a buy and a sell together, tested trading hours and trend rule per chart, the last target
  always at least as far as the stop. TP1 -> "move the stop to the entry + costs", TP2 -> "move the stop to TP1", the
  last target closes the trade (the bot says it within the minute). A waiting order whose base moved is updated in
  its message; one that is no longer valid is cancelled with the reason. Tested on real 1-minute prices Mar 2023 -
  Nov 2026, every calendar year alone, with the OneRoyal ECN costs (spreads seen on the account: gold 0.07-0.14,
  Nasdaq 0.8, Dow 1.1, silver 0.024, oil 0.020; used a little wider). Charts with no tested setting get no orders.
  New, clearer messages: every order shows entry / stop / targets with their Fibonacci level and $ at the lot shown,
  the trend rule, and the tested result of that chart in every year.

v27 (same rules as the indicator v19; made for trading by hand on the OneRoyal ECN account; backtests in Google Drive):
  buy / sell zones and order blocks at every market open: at the Tokyo (09:00), London (08:00) and New York (09:30)
  open, each in its own local time, the zones of the last day that no candle has closed through are taken again (swing
  lows = buy zones, swing highs = sell zones, order blocks = the last opposite candle before price broke the last swing).
  Where the tested setting says so, a BUY LIMIT waits at the top of the nearest buy zone under the price and a SELL
  LIMIT at the bottom of the nearest sell zone above it, the stop beyond the zone, each zone used once; the signal says
  which zone and which market open · all five instruments on 5m and 15m (gold, Nasdaq, Dow, silver, oil) plus gold and
  Nasdaq 30m / 1h; a chart where one of the three test years lost money says so in every signal (trade it smaller) ·
  the full tested table is the default (ACCOUNT=big: no stop cap, no daily target); ACCOUNT=small keeps the $200 table
  (gold 5m and Nasdaq 1h, stop cap, daily target and loss limit; DAY_TARGET_USD / DAY_MAX_LOSS_USD / MAX_RISK_USD) ·
  stricter trend where it tested better (gold 5m: 4H, 1H and 15M the same way; gold 15m: all four) and trading hours
  per chart · trades followed minute by minute: every minute the bot reads the 1-minute candles of the instruments
  that have waiting or open trades, so fills, targets, stops and the stop moves are sent within the minute (move the
  stop as soon as the message comes, or when the live profit in MT5 reaches the step); the backtest does the same
  inside each candle, so the bot, the indicator and the backtest count the same trades · at most two stop moves per
  trade, as shares of the way to the target, shown in every signal as prices and $ at the lot shown (gold / silver /
  oil 0.01, Dow / Nasdaq 0.1) · targets 1:1 or more (never smaller than the stop) · quiet market: no order when spread
  + commission are more than 6% of the stop · tested on three years of real 1-minute prices with the ECN costs ·
  candles missed between two runs are planned like the indicator does; the orders from them that are still waiting are
  sent, and the ones already open are followed after a restart too · messages in MT5 points and $ at the lot shown ·
  MINUTES=0 = follow the trades on the chart candles only (as before).

v26: the report counts wins / losses / at entry (W / L / BE) the same way as the indicator v18 dashboard:
  a trade that came back to its stop at entry (moved there before it covered the costs: "PROTECTED EXIT · 0R") is BE,
  not a loss (its money still shows the small cost) · a profit-locked exit is a win only when it is above the costs,
  else BE · a trade closed by the time limit is a win when it closed above its entry, else a loss · the trades booked
  before v26 are read the same way. Signals, settings and the money are the same as v25.

v25 (same as indicator v18 and the MetaTrader 5 EA v2; made for the OneRoyal ECN account; backtests in Google Drive):
  new tested settings (PROFILES) for every instrument and timeframe, tested on one year of real 1-minute prices WITH the
  ECN costs of the account (commission, spread and swaps); targets from 1:1 up to 1:3, never smaller than the stop ·
  protection 10/20/50 with break-even after costs (the protected stop also covers spread + commission) · OneRoyal ECN
  costs by default (COSTS=none for none) · Dow / Nasdaq: smallest lot 0.1, 1 pip = 1 index point = 10 MT5 points ·
  tested per instrument and timeframe: the range window, and stacking (one more trade the same way once the open
  ones are protected) where it made more in both halves of the year · wins / losses / at entry counted after costs ·
  no daily lock and no limit on the number of signals · 1m off.

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
import os, bisect, re, sys, json, time, html, random, argparse, logging
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
    "XAUUSD": {"name": "Gold",       "yahoo": "GC=F", "oanda": "XAU_USD",    "capital": "GOLD",    "digits": 2, "tick": 0.01, "pip": 0.1, "contract": 100},
    "XAGUSD": {"name": "Silver",     "yahoo": "SI=F", "oanda": "XAG_USD",    "capital": "SILVER",    "digits": 3, "tick": 0.001, "pip": 0.01, "contract": 5000},
    "US30":   {"name": "Dow Jones",  "yahoo": "YM=F", "ref": "^DJI", "oanda": "US30_USD",   "capital": "US30",   "digits": 1, "tick": 0.1, "pip": 1.0, "contract": 1},
    "NAS100": {"name": "Nasdaq 100", "yahoo": "NQ=F", "ref": "^NDX", "oanda": "NAS100_USD", "capital": "US100", "digits": 1, "tick": 0.1, "pip": 1.0, "contract": 1},
    "USOIL":  {"name": "WTI Oil",    "yahoo": "CL=F", "oanda": "WTICO_USD",  "capital": "OIL_CRUDE",  "digits": 2, "tick": 0.01, "pip": 0.01, "contract": 1000},
}
# OneRoyal ECN account (from the account's MT5 specification): commission per lot for the whole trade (charged on the
# opening deal), a typical raw spread (price), and the smallest lot. 1 pip: gold 0.1, silver 0.01, Dow / Nasdaq 1 index
# point (= 10 MT5 points, the price has 1 decimal), oil 0.01. Dow / Nasdaq: contract 1 = $1 per point per lot,
# smallest lot 0.1 = $0.10 per pip.
ECN_COSTS = {"XAUUSD": (7.0, 0.12, 0.01), "XAGUSD": (7.0, 0.03, 0.01), "US30": (0.7, 1.5, 0.1),
             "NAS100": (0.7, 1.0, 0.1), "USOIL": (7.0, 0.025, 0.01)}
# trading costs taken off every closed trade in the reports, and covered by the protected stop (break-even after costs).
# Default: the OneRoyal ECN costs above (COSTS=none for no costs). Override for everybody with COMMISSION_PER_LOT /
# SPREAD, or per instrument: COMMISSION_XAUUSD=7, SPREAD_US30=2, MINLOT_US30=0.1
COSTS = (ENV("COSTS", "oneroyal_ecn") or "").strip().lower()
COMMISSION_PER_LOT = ENV("COMMISSION_PER_LOT", "")
SPREAD_ALL = ENV("SPREAD", "")
for _s, _i in INSTRUMENTS.items():              # override a pip size with PIP_XAUUSD=0.1 etc.
    if ENV("PIP_" + _s):
        _i["pip"] = float(ENV("PIP_" + _s))
    _c, _sp, _ml = ECN_COSTS[_s] if COSTS == "oneroyal_ecn" else (0.0, 0.0, 0.01)
    _i["commission"] = float(ENV("COMMISSION_" + _s, COMMISSION_PER_LOT or str(_c)))
    _i["spread"] = float(ENV("SPREAD_" + _s, SPREAD_ALL or str(_sp)))
    _i["min_lot"] = float(ENV("MINLOT_" + _s, str(_ml)))
    if ENV("EPIC_" + _s):                           # Capital.com market name, e.g. EPIC_USOIL=OIL_CRUDE
        _i["capital"] = ENV("EPIC_" + _s).strip()
    if ENV("CONTRACT_" + _s):                       # units per 1 lot at your broker (money maths)
        _i["contract"] = float(ENV("CONTRACT_" + _s))
TF_SEC = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600}

# plan settings (same defaults as the indicator)
RANGE_BARS = int(ENV("RANGE_BARS", "24"))
SPREAD_PCT, EARLY_PCT = 15.0, 10.0
SL_MULT = float(ENV("SL_MULT", "1.0"))
ALLOW_1M = ENV("ALLOW_1M", "1") == "1"           # 1m on: gold 1m tested at all hours (small trades); ALLOW_1M=0 = off
LIVE = ENV("LIVE", "1") == "1"                   # follow the trades on the minute that is still forming (instant messages)
LIVE_SEC = max(0.5, float(ENV("LIVE_SEC", "1")))  # how often that minute is read (seconds) per instrument with a trade
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

# tested settings for every instrument and timeframe (USE_PROFILES=0 = use the plain settings above instead)
#   on = signals on this timeframe · sl = stop distance in ATR (+ the sweep buffer) · rr = target (reward:risk)
#   limits = reversal limit orders · mixed = breakouts when the higher timeframes are mixed
#   start / end = trading hours, New York time (no new orders outside them)
#   protect = "pct": the stop goes to entry (+ costs) at be_at_r of the way to the target, locks lock1_to of the target
#   at lock1_at, and lock2_to at lock2_at (shares of the way) · protect = "usd": at be_usd $ the stop goes to entry,
#   at lock_at_usd $ it locks lock_usd $ ($ at the lot shown: gold / silver / oil 0.01, Dow / Nasdaq 0.1)
#   cost_max = quiet market: no order when spread + commission are more than this share of the stop
#   day_green = once the pair's day is in profit no more orders that day · day_losses = the same after this many
#   losses (0 = off) - off in every tested setting: signals all day. Tested on three years (Mar 2023 - Oct 2026) of
#   real 1-minute prices, trades followed minute by minute, OneRoyal ECN costs, at most two stop moves per trade;
#   weak = one of the three years lost money (the signal says so) · zones / zsl / zrr / ztrend / zkeep / rng: see ZONES.
#   day_target / day_max_loss / max_risk (small accounts, $ at the lot shown): see DAY_TARGET_USD below.
# Two tested tables (ACCOUNT=small or big):
#   PROFILES_SMALL = accounts of about $200 at the smallest lot (gold 0.01, Nasdaq 0.1), profits withdrawn every
#     day: smaller stops, no order with a stop above the cap, daily target and loss limit; on = only the charts that
#     never took such an account below about $50 in three years, together on one account (gold 5m + Nasdaq 1h)
#   PROFILES = the full table (default): the most money per lot, all five instruments on 5m / 15m, gold and Nasdaq to 1h
USE_PROFILES = ENV("USE_PROFILES", "1") == "1"
ACCOUNT = (ENV("ACCOUNT", "big") or "big").strip().lower()     # big (default) = the full tested table
PROFILES = {
    "XAUUSD": {
        "5m": dict(on=True, sl=3.0, rr=[2.0], limits=False, mixed=False, start="00:00", end="24:00", stack=4, align=1, zones=3, zsl=0.25, zrr=[1.5], ztrend=1, zkeep=0, protect="pct", be_at_r=0.3, lock1_at=0.6, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # p8
        "15m": dict(on=True, sl=3.0, rr=[1.5], limits=True, mixed=True, start="01:30", end="24:00", stack=4, align=2, zones=3, zsl=0.25, zrr=[1.0], ztrend=1, zkeep=0, protect="pct", be_at_r=0.4, lock1_at=0.7, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # q1
        "30m": dict(on=True, sl=2.0, rr=[1.5], limits=False, mixed=True, start="01:30", end="21:30", range=12, stack=3, protect="pct", be_at_r=0.3, lock1_at=0.6, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # p8
        "1h": dict(on=True, sl=2.0, rr=[1.5], limits=False, mixed=False, start="00:00", end="24:00", stack=2, protect="pct", be_at_r=0.4, lock1_at=0.7, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # q1
    },
    "XAGUSD": {
        "5m": dict(on=True, sl=2.0, rr=[2.0], limits=False, mixed=False, start="02:00", end="12:00", range=48, zones=2, zsl=0.25, zrr=[1.0], ztrend=1, zkeep=0, protect="pct", be_at_r=0.4, lock1_at=0.7, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # q1
        "15m": dict(on=True, sl=4.0, rr=[1.5], limits=False, mixed=True, start="08:00", end="12:00", zones=2, zsl=0.25, zrr=[1.5], ztrend=1, zkeep=0, weak=True, protect="pct", be_at_r=0.5, lock1_at=0.0, lock1_to=0.0, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # h50
        "30m": dict(on=False, sl=3.0, rr=[1.5], limits=False, mixed=True, start="01:30", end="24:00", range=36, protect="pct", be_at_r=0.4, lock1_at=0.7, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # q1
        "1h": dict(on=False, sl=3.0, rr=[1.5], limits=False, mixed=False, start="00:00", end="21:30", protect="pct", be_at_r=0.4, lock1_at=0.7, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # q1
    },
    "US30": {
        "5m": dict(on=True, sl=2.0, rr=[2.0], limits=False, mixed=False, start="03:00", end="07:00", range=48, stack=2, zones=2, zsl=0.75, zrr=[1.0], ztrend=1, zkeep=0, protect="pct", be_at_r=0.3, lock1_at=0.6, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # p8
        "15m": dict(on=True, sl=3.0, rr=[2.0], limits=False, mixed=True, start="02:00", end="12:00", align=1, zones=2, zsl=0.75, zrr=[1.5], ztrend=1, zkeep=0, protect="pct", be_at_r=0.3, lock1_at=0.6, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # p8
        "30m": dict(on=False, sl=3.0, rr=[1.5], limits=True, mixed=True, start="00:00", end="24:00", stack=2, protect="pct", be_at_r=0.4, lock1_at=0.7, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # q1
        "1h": dict(on=False, sl=3.0, rr=[1.5], limits=True, mixed=False, start="00:00", end="24:00", protect="pct", be_at_r=0.4, lock1_at=0.7, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # q1
    },
    "NAS100": {
        "5m": dict(on=True, sl=2.0, rr=[1.5], limits=False, mixed=True, start="08:00", end="24:00", protect="pct", be_at_r=0.3, lock1_at=0.6, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # p8
        "15m": dict(on=True, sl=4.0, rr=[1.5], limits=False, mixed=True, start="03:00", end="11:00", protect="pct", be_at_r=0.3, lock1_at=0.6, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # p8
        "30m": dict(on=True, sl=3.0, rr=[1.5], limits=False, mixed=False, start="01:30", end="24:00", stack=4, protect="pct", be_at_r=0.3, lock1_at=0.6, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # p8
        "1h": dict(on=True, sl=2.0, rr=[1.5], limits=False, mixed=True, start="00:00", end="24:00", stack=2, protect="pct", be_at_r=0.3, lock1_at=0.6, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # p8
    },
    "USOIL": {
        "5m": dict(on=True, sl=3.0, rr=[2.0], limits=False, mixed=False, start="03:00", end="11:00", protect="pct", be_at_r=0.5, lock1_at=0.0, lock1_to=0.0, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # h50
        "15m": dict(on=True, sl=2.0, rr=[1.5], limits=False, mixed=True, start="03:00", end="11:00", align=2, zones=3, zsl=0.75, zrr=[1.0], ztrend=2, zkeep=0, protect="pct", be_at_r=0.4, lock1_at=0.7, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # q1
        "30m": dict(on=False, sl=3.0, rr=[1.5], limits=False, mixed=True, start="00:00", end="24:00", stack=3, protect="pct", be_at_r=0.4, lock1_at=0.7, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # q1
        "1h": dict(on=False, sl=3.0, rr=[1.5], limits=True, mixed=True, start="00:00", end="17:00", protect="pct", be_at_r=0.4, lock1_at=0.7, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # q1
    },
}
PROFILES_SMALL = {
    "XAUUSD": {
        "5m": dict(on=True, sl=1.5, rr=[2.0], limits=False, mixed=False, start="00:00", end="24:00", stack=4, protect="pct", be_at_r=0.4, lock1_at=0.7, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0, day_target=5.0, day_max_loss=15.0, max_risk=8.0),  # q1
        "15m": dict(on=False, sl=3.0, rr=[1.5], limits=True, mixed=True, start="01:30", end="24:00", stack=4, protect="pct", be_at_r=0.4, lock1_at=0.7, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # q1
        "30m": dict(on=False, sl=2.0, rr=[1.5], limits=False, mixed=True, start="01:30", end="21:30", range=12, stack=3, protect="pct", be_at_r=0.3, lock1_at=0.6, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # p8
        "1h": dict(on=False, sl=2.0, rr=[1.5], limits=False, mixed=False, start="00:00", end="24:00", stack=2, protect="pct", be_at_r=0.4, lock1_at=0.7, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # q1
    },
    "XAGUSD": {
        "5m": dict(on=False, sl=3.0, rr=[1.5], limits=False, mixed=False, start="00:00", end="24:00", range=48, protect="pct", be_at_r=0.4, lock1_at=0.7, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # q1
        "15m": dict(on=False, sl=3.0, rr=[1.5], limits=False, mixed=True, start="08:00", end="24:00", protect="pct", be_at_r=0.4, lock1_at=0.7, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # q1
        "30m": dict(on=False, sl=3.0, rr=[1.5], limits=False, mixed=True, start="01:30", end="24:00", range=36, protect="pct", be_at_r=0.4, lock1_at=0.7, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # q1
        "1h": dict(on=False, sl=3.0, rr=[1.5], limits=False, mixed=False, start="00:00", end="21:30", protect="pct", be_at_r=0.4, lock1_at=0.7, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # q1
    },
    "US30": {
        "5m": dict(on=False, sl=3.0, rr=[1.5], limits=False, mixed=True, start="01:30", end="17:00", range=48, stack=2, protect="pct", be_at_r=0.4, lock1_at=0.7, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # q1
        "15m": dict(on=False, sl=3.0, rr=[1.5], limits=False, mixed=True, start="00:00", end="24:00", protect="pct", be_at_r=0.4, lock1_at=0.7, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # q1
        "30m": dict(on=False, sl=3.0, rr=[1.5], limits=True, mixed=True, start="00:00", end="24:00", stack=2, protect="pct", be_at_r=0.4, lock1_at=0.7, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # q1
        "1h": dict(on=False, sl=3.0, rr=[1.5], limits=True, mixed=False, start="00:00", end="24:00", protect="pct", be_at_r=0.4, lock1_at=0.7, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # q1
    },
    "NAS100": {
        "5m": dict(on=False, sl=2.0, rr=[1.5], limits=False, mixed=True, start="08:00", end="24:00", protect="pct", be_at_r=0.3, lock1_at=0.6, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # p8
        "15m": dict(on=False, sl=4.0, rr=[1.5], limits=False, mixed=True, start="01:30", end="24:00", protect="pct", be_at_r=0.3, lock1_at=0.6, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # p8
        "30m": dict(on=False, sl=3.0, rr=[1.5], limits=False, mixed=False, start="01:30", end="24:00", stack=4, protect="pct", be_at_r=0.3, lock1_at=0.6, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # p8
        "1h": dict(on=True, sl=2.0, rr=[2.0], limits=False, mixed=True, start="00:00", end="24:00", stack=2, protect="usd", be_usd=5.0, lock_at_usd=10.0, lock_usd=5.0, cost_max=0.06, day_green=False, day_losses=0, day_target=5.0, max_risk=16.0),  # U5L
    },
    "USOIL": {
        "5m": dict(on=False, sl=3.0, rr=[1.5], limits=False, mixed=False, start="00:00", end="24:00", protect="pct", be_at_r=0.4, lock1_at=0.7, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # q1
        "15m": dict(on=False, sl=3.0, rr=[1.5], limits=False, mixed=True, start="00:00", end="24:00", protect="pct", be_at_r=0.4, lock1_at=0.7, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # q1
        "30m": dict(on=False, sl=3.0, rr=[1.5], limits=False, mixed=True, start="00:00", end="24:00", stack=3, protect="pct", be_at_r=0.4, lock1_at=0.7, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # q1
        "1h": dict(on=False, sl=3.0, rr=[1.5], limits=True, mixed=True, start="00:00", end="17:00", protect="pct", be_at_r=0.4, lock1_at=0.7, lock1_to=0.3, lock2_at=0.0, lock2_to=0.0, cost_max=0.06, day_green=False, day_losses=0),  # q1
    },
}

# filters that remove orders that look unrealistic
MIN_RISK_ATR = float(ENV("MIN_RISK_ATR", "0.5"))     # stop must be at least this many ATR
MAX_TP_ATR = float(ENV("MAX_TP_ATR", "8"))           # farthest target within this many ATR
MAX_TP_DAILY = float(ENV("MAX_TP_DAILY", "1.0"))     # farthest target within this share of a normal daily range
MOVE_PER_BAR = float(ENV("MOVE_PER_BAR", "0.5"))     # net ATR price travels per bar (time check)
MAX_HOLD_HOURS = float(ENV("MAX_HOLD_HOURS", "24"))   # the last target must be reachable within this many hours

# quality rules (fewer stop-outs)
# plain settings with PROTECT=pct only (the v25 / v26 protection, indicator v18 and EA v2): 3 steps, shares of the way:
BE_AT_R = float(ENV("BE_AT_R", "0.1"))               # step 1: at 10% the stop moves to entry (0 = off)
LOCK1_AT = float(ENV("LOCK1_AT", "0.2"))             # step 2: at 20% ...
LOCK1_TO = float(ENV("LOCK1_TO", "0.05"))            # ... the stop moves to 5% of the target (profit locked)
LOCK2_AT = float(ENV("LOCK2_AT", "0.5"))             # step 3: at 50% ...
LOCK2_TO = float(ENV("LOCK2_TO", "0.3"))             # ... the stop moves to 30% of the target
LOCK_LOT = float(ENV("LOCK_LOT", ENV("LOT_DEFAULT", "0.01")))   # lot used for the $ shown in the lock message
STACK_SAFE = ENV("STACK_SAFE", "0") == "1"           # plain settings: one more trade the same way once the open one is protected
STACK_MAX = int(ENV("STACK_MAX", "3"))              # ... up to this many open trades the same way (the tested settings set their own)
BE_PLUS_COST = ENV("BE_PLUS_COST", "1") == "1"   # with trading costs set: the protected stop also covers spread + commission
# Plain settings only (USE_PROFILES=0; the tested settings set their own steps): protection in money: +$2 -> the stop
# goes to entry (+ costs), +$5 -> the stop locks $5, then on to the target. The $ are at the lot shown (gold / silver /
# oil 0.01, Dow / Nasdaq 0.1). PROTECT=pct = steps of the way to the target instead (BE_AT_R, LOCK1_*, LOCK2_*).
PROTECT = (ENV("PROTECT", "usd") or "usd").strip().lower()
BE_USD = float(ENV("BE_USD", "2"))                   # step 1: at this profit the stop moves to entry (+ costs)
LOCK_AT_USD = float(ENV("LOCK_AT_USD", "5"))         # step 2: at this profit ...
LOCK_USD = float(ENV("LOCK_USD", "5"))               # ... the stop locks this much
REAL_STOP = ENV("REAL_STOP", "1") == "1"             # a moved stop goes only where it can really be put: behind the price
COST_MAX = float(ENV("COST_MAX", "0"))               # plain settings: no order when costs are more than this share of the stop
REPLAY_MISSED = ENV("REPLAY_MISSED", "1") == "1"     # candles missed between runs are planned too; still-waiting orders are sent
MINUTES = ENV("MINUTES", "1") == "1"                 # follow trades on 1-minute candles: stop moves sent within the minute
DAY_GREEN = ENV("DAY_GREEN", "0") == "1"             # daily rule: once the day is in profit, no more orders on that pair today
DAY_LOSSES = int(ENV("DAY_LOSSES", "0"))             # daily rule: after this many losses, no more orders on that pair today
DAY_RULE = (ENV("DAY_RULE", "auto") or "auto").strip().lower()   # auto = as the tested setting says (all off) · on · off
# Small accounts (the tested setting can set its own; a value here wins, 0 = off). $ at the lot shown:
#   DAY_TARGET_USD   your daily target: once a pair's closed profit today reaches it, its waiting orders go, no new ones
#                    today, and a message says so (close the open trades too if that is your way)
#   DAY_MAX_LOSS_USD daily loss limit: once a pair's closed loss today reaches it, no new orders today
#   MAX_RISK_USD     no order when its stop is more than this many $ (the account can not take it)
def user_or_tested(name, pp, key):
    v = (ENV(name, "") or "").strip()
    return float(v) if v else float(pp.get(key, 0.0) or 0.0)
COOLDOWN_MIN = int(ENV("COOLDOWN_MIN", "30"))        # after a stop-out, no new order in the same direction for this long
SPIKE_ATR = float(ENV("SPIKE_ATR", "3.0"))           # skip planning right after a news-size candle (range above this many ATR)
NEUTRAL_FADE = ENV("NEUTRAL_FADE", "0") == "1"       # mixed trend: also reversal (limit) orders (off: they lost the most)
SWEEP_BUFFER = float(ENV("SWEEP_BUFFER_ATR", "0.25"))   # extra stop room (ATR) so a quick stop-hunt wick does not take the trade out
FAKE_BREAK_BARS = int(ENV("FAKE_BREAK_BARS", "6"))      # a wick beyond the range that closes back inside within this many bars = fake breakout
DAY_START_HOUR = int(ENV("DAY_START_HOUR", "0"))        # totals reset at this hour of DAY_TIMEZONE (0 = midnight)
DAY_TZ = ZoneInfo(ENV("DAY_TIMEZONE", "Asia/Beirut"))     # time zone of the daily reset (Beirut, like the indicator)
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
MIN_RR = float(ENV("MIN_RR", "1.0"))   # never post an order whose target is smaller than its stop
SEND_UPDATES = ENV("SEND_UPDATES", "1") == "1"
MAX_PER_PAIR_DAY = int(ENV("MAX_PER_PAIR_DAY", "0"))        # new signals per symbol+timeframe per day (0 = no limit, like the indicator)
MAX_SIGNALS_PER_DAY = int(ENV("MAX_SIGNALS_PER_DAY", "0"))    # limit per day, all symbols together (0 = no limit)

PENDING, OPEN, TP_HIT, SL_HIT, DAY_END, BE_HIT, LOCK_HIT, CANCELLED = 0, 1, 2, 3, 4, 5, 6, 9
STICKY_MAX_ATR = float(ENV("STICKY_MAX_ATR", "8"))      # an unfilled order stays while price is within this many ATR of it
CONFLICT_ATR = float(ENV("CONFLICT_ATR", "1.5"))        # a buy and a sell closer than this (ATR) are never waiting together
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

def sweep_flags(bars, n=None):
    """Fake breakout: price poked beyond the older range recently but closed back inside."""
    k, n = FAKE_BREAK_BARS, (n or RANGE_BARS)
    if len(bars) < n + k + 1:
        return False, False
    older, recent = bars[-(n + k):-k], bars[-k:]
    ph, pl = max(b.h for b in older), min(b.l for b in older)
    return (max(b.h for b in recent) > ph and bars[-1].c < ph), (min(b.l for b in recent) < pl and bars[-1].c > pl)

# ───────────────────────────── buy / sell zones and order blocks (v27, same as the indicator) ─────────────────────────────
# At every market open (Tokyo, London, New York) the zones of the last day that no candle has CLOSED through are taken:
# swing lows = buy zones, swing highs = sell zones, and order blocks (the last opposite candle before price broke the
# last swing). During that session a BUY LIMIT waits at the top of the nearest buy zone under the price and a SELL LIMIT
# at the bottom of the nearest sell zone above it (as the tested setting of the chart says), the stop beyond the zone.
ZONE_LEN = int(ENV("ZONE_LEN", "8"))            # swing size of a zone: bars each side
OB_LEN = int(ENV("OB_LEN", "5"))                # swing size of the break that makes an order block
ZONE_AGE_H = float(ENV("ZONE_AGE_H", "24"))     # zones formed in the last day (and not broken since)
ZONE_W = 0.15                                    # a swing zone = the swing price +- this share of the ATR
OB_BACK = 100                                    # an order block: the break comes within this many bars of the swing
SESSIONS = (("TOKYO", "Asia/Tokyo", 9, 0), ("LONDON", "Europe/London", 8, 0), ("NEW YORK", "America/New_York", 9, 30))
# plain settings (the tested setting of each chart says its own): 0 = no zone orders, 1 = swing zones, 2 = order blocks,
# 3 = both; stop room beyond the zone (ATR, + the stop-hunt room); target (R); trend rule (see zone_allowed); keep = a
# zone order is not cancelled when the chart runs against it or the trend turns (only when its zone breaks)
ZONES = int(ENV("ZONES", "0"))
ZONE_SL = float(ENV("ZONE_SL", "0.5"))
ZONE_RR = parse_rr(ENV("ZONE_RR", "1.5"), [1.5])
ZONE_TREND = int(ENV("ZONE_TREND", "1"))
ZONE_KEEP = int(ENV("ZONE_KEEP", "0"))
_OPENS = {}

def opens_on(d):
    """The market opens on the UTC date d: [(UTC seconds, name)] (Tokyo 09:00, London 08:00, New York 09:30 local)."""
    if d not in _OPENS:
        _OPENS[d] = sorted((int(datetime(d.year, d.month, d.day, h, m, tzinfo=ZoneInfo(tz)).timestamp()), name)
                           for name, tz, h, m in SESSIONS)
    return _OPENS[d]

def last_open(t):
    """The latest market open at or before t: (UTC seconds, name)."""
    d = datetime.fromtimestamp(t, timezone.utc).date()
    best = None
    for dd in (d - timedelta(days=1), d):
        for T, name in opens_on(dd):
            if T <= t and (best is None or T > best[0]):
                best = (T, name)
    return best

def swing_hi(hs, j, n):
    """A swing high: above the n candles before it and not below the n after it (the indicator uses the same rule)."""
    h = hs[j]
    return all(h > hs[j - i] and h >= hs[j + i] for i in range(1, n + 1))

def swing_lo(ls, j, n):
    v = ls[j]
    return all(v < ls[j - i] and v <= ls[j + i] for i in range(1, n + 1))

def find_zones(bars, atr, use=3, n=None, ob_n=None, age_h=None):
    """The zones not broken at the close of bars[-1], formed in the last age_h hours. use: 1 = swing zones, 2 = order
    blocks, 3 = both. A swing zone is the swing price +- ZONE_W x ATR; an order block is its candle (low to high). A zone
    is broken once a candle closes beyond its far side. Each zone: dict(d=+1 buy / -1 sell, lo, hi, t, src)."""
    n, ob_n, age = n or ZONE_LEN, ob_n or OB_LEN, (age_h or ZONE_AGE_H) * 3600
    N = len(bars)
    if N < 2 * max(n, ob_n) + 2 or not atr:
        return []
    t_min = bars[-1].t - age
    hs, ls, cs = [b.h for b in bars], [b.l for b in bars], [b.c for b in bars]
    mn, mx = [0.0] * (N + 1), [0.0] * (N + 1)               # lowest / highest close from index i to the end
    mn[N], mx[N] = float("inf"), float("-inf")
    for i in range(N - 1, -1, -1):
        mn[i], mx[i] = min(mn[i + 1], cs[i]), max(mx[i + 1], cs[i])
    out = []
    if use & 1:
        zw = ZONE_W * atr
        for j in range(n, N - n):
            if bars[j].t < t_min:
                continue
            if swing_hi(hs, j, n) and mx[j + 1] <= hs[j] + zw:
                out.append(dict(d=-1, lo=hs[j] - zw, hi=hs[j] + zw, t=bars[j].t, src="ZONE"))
            if swing_lo(ls, j, n) and mn[j + 1] >= ls[j] - zw:
                out.append(dict(d=1, lo=ls[j] - zw, hi=ls[j] + zw, t=bars[j].t, src="ZONE"))
    if use & 2:
        sh = sl = None                                       # last swing high / low: (price, index), and broken yet?
        sh_b = sl_b = True
        for k in range(2 * ob_n, N):
            j = k - ob_n
            if swing_hi(hs, j, ob_n):
                sh, sh_b = (hs[j], j), False
            if swing_lo(ls, j, ob_n):
                sl, sl_b = (ls[j], j), False
            for side in (1, -1):
                sw, broken = (sh, sh_b) if side == 1 else (sl, sl_b)
                if sw is None or broken or not ((cs[k] > sw[0]) if side == 1 else (cs[k] < sw[0])):
                    continue
                if side == 1:
                    sh_b = True
                else:
                    sl_b = True
                if k - sw[1] > OB_BACK or bars[k].t < t_min:
                    continue
                back = max(1, min(k - sw[1] + ob_n * 2, OB_BACK))
                ke = 1                                      # the candle the move started from (lowest low / highest high)
                for jj in range(1, back + 1):
                    if (ls[k - jj] < ls[k - ke]) if side == 1 else (hs[k - jj] > hs[k - ke]):
                        ke = jj
                kk = -1                                     # ... and the last opposite candle at or before it
                for jj in range(ke, min(ke + 5, back) + 1):
                    b = bars[k - jj]
                    if (b.c < b.o) if side == 1 else (b.c > b.o):
                        kk = jj
                        break
                if kk < 0:
                    continue
                b = bars[k - kk]
                if (side == 1 and mn[k] >= b.l) or (side == -1 and mx[k] <= b.h):
                    out.append(dict(d=side, lo=b.l, hi=b.h, t=b.t, src="OB"))
    return out

def zone_order(d, z, sp, slD, rrs, bias):
    """A BUY LIMIT at the top of a buy zone / a SELL LIMIT at the bottom of a sell zone; the stop beyond the far side."""
    trig = z["hi"] if d == 1 else z["lo"]
    sl = z["lo"] - slD if d == 1 else z["hi"] + slD
    risk = abs(trig - sl)
    return dict(dir=d, kind="BUY LIMIT" if d == 1 else "SELL LIMIT", is_stop=False, with_trend=(bias == d),
                lo=trig - sp if d == 1 else trig, hi=trig if d == 1 else trig + sp, entry=trig, trig=trig, sl=sl,
                inval=sl, risk=risk, sp=sp, rrs=list(rrs), tps=[trig + d * r * risk for r in rrs])

def zone_allowed(d, bias, ema_dir, mom_dir, mode):
    """Zone orders: mode 1 = with the higher-timeframe trend only, 2 = with the trend or a mixed trend, 0 = any; never
    while the chart runs hard against the order (falling for a buy, rising for a sell)."""
    if ema_dir == -d and mom_dir == -d:
        return False
    return bias == d if mode == 1 else bias != -d if mode == 2 else True

def arrow(b): return "▲" if b == 1 else "▼" if b == -1 else "•"

def ny_parts(ts):
    dt = datetime.fromtimestamp(ts, TZ)
    return dt.hour * 60 + dt.minute, dt.strftime("%Y-%m-%d")

# ───────────────────────────── plan logic (mirrors the indicator) ─────────────────────────────
def cost_price(sym):
    """Cost of one trade in price units: spread + commission per lot / contract size (e.g. gold 7 / 100 = 0.07)."""
    i = INSTRUMENTS[sym]
    return i.get("spread", 0.0) + i.get("commission", 0.0) / max(i["contract"], 1e-9)

def active_profiles():
    return PROFILES_SMALL if ACCOUNT == "small" else PROFILES

def plan_params(sym, tf):
    """Settings for this instrument and timeframe: the tested profile, or the plain settings."""
    p = dict(on=True, sl=SL_MULT, rr=list(RR[tf]), limits=True, mixed=True, start=PLAN_START, end=PLAN_END, range=RANGE_BARS,
             stack=STACK_MAX if STACK_SAFE else 0, rng=True, zones=ZONES, zsl=ZONE_SL, zrr=ZONE_RR, ztrend=ZONE_TREND,
             zkeep=ZONE_KEEP)
    if USE_PROFILES:
        p.update(active_profiles().get(sym, {}).get(tf, {}))
    if not isinstance(p["rr"], (list, tuple)):
        p["rr"] = [float(p["rr"])]
    if not isinstance(p["zrr"], (list, tuple)):
        p["zrr"] = [float(p["zrr"])]
    for k in ("start", "end"):                      # "03:00" -> minutes after midnight (New York)
        if isinstance(p[k], str):
            p[k] = hm(p[k])
    return p

def build_orders(atr, hi, lo, close, bias, tick, rrs, ema_dir=0, mom_dir=0, fake_up=False, fake_dn=False,
                 sl_mult=None, limits=True, mixed=True):
    """Entry / stop come from the range and ATR. The target = R x stop distance (R set by timeframe).
    Direction must agree with the higher timeframes AND with what the chart timeframe is doing now."""
    sp = max(atr * SPREAD_PCT / 100.0, tick)
    early = min(atr * EARLY_PCT / 100.0, sp)
    slD = atr * ((SL_MULT if sl_mult is None else sl_mult) + SWEEP_BUFFER)
    out = []

    def allowed(d, is_stop):
        if ema_dir == -d or mom_dir == -d:          # the chart is moving against this direction right now
            return False
        if bias == d:
            return True
        if bias == 0:                               # mixed higher timeframes
            strong = ema_dir == d and mom_dir == d  # ...but the chart itself is clearly running this way: take the breakout
            return (strong and mixed) or ((not is_stop) and NEUTRAL_FADE)
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
    if limits and close < lvl - sp and allowed(-1, False):
        mk(-1, "SELL LIMIT", False, lvl, hi + slD, hi + slD)
    lvl = lo + sp + early
    if limits and close > lvl + sp and allowed(1, False):
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
    """The day of the totals: starts at DAY_START_HOUR in DAY_TZ (default midnight Beirut)."""
    return (datetime.fromtimestamp(ts, DAY_TZ) + timedelta(hours=(24 - DAY_START_HOUR) % 24)).date()

def realized(o, exit_px=None):
    """Signed price distance banked by an order (when there are several targets the position is split equally)."""
    n = max(len(o["tps"]), 1); w = 1.0 / n
    banked = sum(w * (o["tps"][i] - o["trig"]) * o["dir"] for i in range(o.get("hits", 0)))
    rest = 1.0 - w * o.get("hits", 0)
    if o["state"] == SL_HIT:
        return banked - rest * o["risk"]
    if o["state"] == LOCK_HIT:
        return banked + rest * o.get("lock_d", 0.0)
    if o["state"] == DAY_END and exit_px is not None:
        return banked + rest * (exit_px - o["trig"]) * o["dir"]
    return banked

def outcome(o, dist, cost):
    """W (1), L (-1) or BE (2) of a closed trade, counted the same way as the indicator dashboard."""
    st = o["state"]
    if st == TP_HIT:
        return 1
    if st == SL_HIT:
        return -1
    if st == BE_HIT:                                  # back to the stop at entry: BE (its money still shows the cost)
        return 1 if o.get("hits", 0) > 0 else 2       # (with two targets the first one was already banked)
    if st == LOCK_HIT:                                # locked stop: a win only when it is above the costs
        return 1 if dist - cost > INSTRUMENTS[o["sym"]]["tick"] else 2
    return 1 if dist > 0 else -1                      # time limit: closed above or below its entry

def lot_for(sym, lot):
    """The lot actually traded on this instrument: never below its smallest lot (Dow / Nasdaq 0.1 at OneRoyal)."""
    return max(lot, INSTRUMENTS[sym].get("min_lot", 0.0))

def usd_px(sym, usd):
    """A money amount at the lot shown (LOT_DEFAULT, never below the smallest lot) as a price distance."""
    i = INSTRUMENTS[sym]
    return usd / max(i["contract"] * lot_for(sym, LOT_DEFAULT), 1e-12)

def money(sym, dist, lot):
    return dist * INSTRUMENTS[sym]["contract"] * lot_for(sym, lot)

def summarize(ledger, syms, tfs, lot, ref_ts):
    td = trading_day(ref_ts); wk = td.isocalendar()[:2]; mo = (td.year, td.month)
    out = {k: dict(pts=0.0, usd=0.0, win=0, loss=0, be=0) for k in ("day", "week", "month")}
    for e in ledger:
        if e["sym"] not in syms or e["tf"] not in tfs:
            continue
        d = date.fromisoformat(e["td"])
        net = e["dist"] - e.get("cost", e.get("sp", 0.0))       # after the trading cost (commission + spread)
        pp, uu = net / point(e["sym"]), money(e["sym"], net, lot)        # MT5 points and $
        oc = e.get("oc")
        if oc is None:                                # booked before v26: read the same way (a stop at entry booked 0)
            dist = e["dist"]
            oc = 2 if abs(dist) < 1e-12 else -1 if dist < 0 else 1 if net > INSTRUMENTS[e["sym"]]["tick"] else 2
        for key, same in (("day", d == td), ("week", d.isocalendar()[:2] == wk), ("month", (d.year, d.month) == mo)):
            if same:
                o = out[key]; o["pts"] += pp; o["usd"] += uu
                if oc == 1: o["win"] += 1
                elif oc == -1: o["loss"] += 1
                else: o["be"] += 1                    # at entry (protected exit; the money still shows its small cost)
    return out

# ───────────────────────────── v28: FIBONACCI ORDERS (the same rules as the indicator v20 and the EA v4) ─────────────────────────────
# At every chart candle close, for each side:
#   the last swing high that is not broken yet (a high above the L candles before it and not below the R candles after
#   it, seen R candles later) gets a BUY STOP. Its Fibonacci: 1.0 = the lowest point since the swing low before it (the
#   base of the move, with its order block), 0.0 = the swing high. Entry = 0.0, stop = beyond the tested Fibonacci level
#   by a little ATR, targets = the Fibonacci extensions beyond the 0.0. A SELL STOP the same way down. One trade per swing.
#   On the charts where it tested better (gold 5m, Nasdaq 15m and 30m) the move that made the swing must also have left
#   a fair value gap (FVG).
#   Rules: any hour (v29: the settings are tested at all hours), the move between the smallest and the biggest size of
#   the chart (in ATR: small trades on 1 minute, bigger on the higher timeframes), tested trend rule (EMA 20/50 of the
#   last FINISHED higher candles), never a buy and a sell together, at most the tested number of trades the same way,
#   the last target at least as far as the stop. Management: target 1 -> stop to entry + costs, target 2 -> stop to target 1, the last target closes.
# The tested setting of every chart (backtest 2023 - 2026, every year alone) is V20 below; a chart that is not there
# gets no orders.
# == V20 START ==
V20 = {
    "XAUUSD": {
        "1m": {"L": 30, "R": 2, "minleg": 6.0, "maxleg": 12.0, "sfib": 0.618, "slb": 0.0, "tps": [0.618, 1.0, 1.618], "trend": 2, "bias": "mid", "stack": 3, "start": 0, "end": 1440, "fvg": False, "years": [-282.95, 649.59, 582.23, 2265.04]},
        "5m": {"L": 30, "R": 1, "minleg": 4.5, "maxleg": 0.0, "sfib": 0.618, "slb": 0.0, "tps": [0.618, 1.0, 1.618], "trend": 2, "bias": "mid", "stack": 3, "start": 0, "end": 1440, "fvg": True, "years": [596.5, 289.0, 1939.5, 4251.61]},
        "15m": {"L": 30, "R": 1, "minleg": 4.5, "maxleg": 8.0, "sfib": 0.618, "slb": 1.0, "tps": [0.382, 0.618, 1.0], "trend": 1, "bias": "fast", "stack": 3, "start": 0, "end": 1440, "fvg": False, "years": [279.49, 222.73, 1379.99, 1381.03]},
        "30m": {"L": 8, "R": 1, "minleg": 3.0, "maxleg": 8.0, "sfib": 1.0, "slb": 0.0, "tps": [0.618, 1.0, 1.618], "trend": 1, "bias": "1d", "stack": 3, "start": 0, "end": 1440, "fvg": False, "years": [400.27, 835.11, 1225.37, 2599.81]},
        "1h": {"L": 8, "R": 1, "minleg": 0.5, "maxleg": 0.0, "sfib": 0.786, "slb": 0.25, "tps": [0.618, 1.0, 1.618], "trend": 0, "bias": "fast", "stack": 3, "start": 0, "end": 1440, "fvg": False, "years": [1036.15, 857.06, 1992.85, 4507.1]},
    },
    "NAS100": {
        "5m": {"L": 30, "R": 1, "minleg": 6.0, "maxleg": 0.0, "sfib": 0.5, "slb": 0.0, "tps": [0.618, 1.0, 1.618], "trend": 2, "bias": "mid", "stack": 3, "start": 0, "end": 1440, "fvg": False, "years": [114.77, 580.93, 99.44, 297.27]},
        "15m": {"L": 20, "R": 3, "minleg": 0.5, "maxleg": 8.0, "sfib": 0.618, "slb": 1.0, "tps": [0.382, 0.618, 1.0], "trend": 2, "bias": "slow", "stack": 3, "start": 0, "end": 1440, "fvg": True, "years": [208.04, 344.89, 252.34, 162.55]},
        "30m": {"L": 20, "R": 1, "minleg": 3.0, "maxleg": 0.0, "sfib": 0.786, "slb": 0.5, "tps": [0.272, 0.618, 1.0], "trend": 0, "bias": "slow", "stack": 3, "start": 0, "end": 1440, "fvg": True, "years": [245.93, 1337.54, 476.3, 648.68]},
        "1h": {"L": 30, "R": 2, "minleg": 6.0, "maxleg": 0.0, "sfib": 0.786, "slb": 0.5, "tps": [0.382, 0.618, 1.0], "trend": 2, "bias": "mid", "stack": 3, "start": 0, "end": 1440, "fvg": False, "years": [695.99, 1117.7, 1246.28, 980.13]},
    },
    "US30": {
        "5m": {"L": 12, "R": 2, "minleg": 0.5, "maxleg": 8.0, "sfib": 0.786, "slb": 0.5, "tps": [0.382, 0.618, 1.0], "trend": 2, "bias": "slow", "stack": 3, "start": 0, "end": 1440, "fvg": True, "years": [-158.21, 319.82, 238.1, -269.53]},
        "15m": {"L": 30, "R": 1, "minleg": 4.5, "maxleg": 0.0, "sfib": 0.618, "slb": 0.1, "tps": [0.382, 0.618, 1.0], "trend": 2, "bias": "slow", "stack": 3, "start": 0, "end": 1440, "fvg": True, "years": [-32.08, 662.5, -272.56, -259.02]},
        "30m": {"L": 3, "R": 1, "minleg": 0.5, "maxleg": 8.0, "sfib": 0.786, "slb": 0.5, "tps": [0.618, 1.0, 1.618], "trend": 1, "bias": "mid", "stack": 2, "start": 0, "end": 1440, "fvg": True, "years": [129.87, 991.34, 169.12, -11.78]},
        "1h": {"L": 8, "R": 1, "minleg": 1.5, "maxleg": 8.0, "sfib": 0.786, "slb": 0.0, "tps": [0.382, 1.0], "trend": 1, "bias": "slow", "stack": 1, "start": 0, "end": 1440, "fvg": False, "years": [94.4, 537.49, 193.29, 272.85]},
    },
}

V20_BIAS_NAME = {"tf": "", "quick": "15M+5M", "fast": "1H+15M", "mid": "4H·1H·15M", "slow": "D·4H·1H", "4h": "4H", "1d": "D"}
V20_TF_DEFAULT = {"1m": "quick", "5m": "fast", "15m": "mid", "30m": "mid", "1h": "slow"}
V20_HTF = {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}


def v20_params(sym, tf):
    return V20.get(sym, {}).get(tf)


def v20_swh(hs, j, L, R):
    h = hs[j]
    return all(h > hs[j - q] for q in range(1, L + 1)) and all(h >= hs[j + q] for q in range(1, R + 1))


def v20_swl(ls, j, L, R):
    v = ls[j]
    return all(v < ls[j - q] for q in range(1, L + 1)) and all(v <= ls[j + q] for q in range(1, R + 1))


def v20_bias_one(bars, tc, sec):
    """Trend of one higher timeframe: its last candle FINISHED BEFORE tc (the close of the chart candle), like the
    indicator (no repaint): close against EMA 20 / 50."""
    closed = [b for b in bars if b.t + sec < tc]
    return bias_from_bars(closed)


def v20_bias(htf, tc, code, tf):
    """The trend the chart reads (code: tf / quick / fast / mid / slow / 4h / 1d) at the close tc of its candle."""
    code = code if code and code != "tf" else V20_TF_DEFAULT.get(tf, "fast")
    b = {k: v20_bias_one(htf.get(k) or [], tc, s) for k, s in V20_HTF.items()}

    def maj(a, c, d):
        t = a + c + d
        return 1 if t >= 2 else -1 if t <= -2 else 0
    if code == "quick":
        return b["15m"] if b["15m"] == b["5m"] else 0
    if code == "fast":
        return b["1h"] if b["1h"] == b["15m"] else 0
    if code == "mid":
        return maj(b["4h"], b["1h"], b["15m"])
    if code == "slow":
        return maj(b["1d"], b["4h"], b["1h"])
    if code == "4h":
        return b["4h"]
    return b["1d"]


def v20_plan(bars, d, pp, atr, bias, mins, used_t, open_same, open_opp):
    """The STOP order of side d at the close of bars[-1]: (plan dict, '') or (None, why). bars: closed candles."""
    L, R = int(pp["L"]), int(pp["R"])
    n = len(bars)
    hs, ls, cs = [b.h for b in bars], [b.l for b in bars], [b.c for b in bars]
    j = -1
    for q in range(n - 1 - R, L - 1, -1):
        if (v20_swh(hs, q, L, R) if d == 1 else v20_swl(ls, q, L, R)):
            j = q
            break
    if j < 0:
        return None, "no swing yet"
    lvl = hs[j] if d == 1 else ls[j]
    if any((cs[q] > lvl) if d == 1 else (cs[q] < lvl) for q in range(j + R, n)):
        return None, "the swing broke: waiting for a new one"
    if used_t == bars[j].t:
        return None, "this swing was traded already"
    j0 = -1
    for q in range(j - 1, L - 1, -1):
        if (v20_swl(ls, q, L, R) if d == 1 else v20_swh(hs, q, L, R)):
            j0 = q
            break
    if j0 < 0:
        return None, "no base swing yet"
    if pp.get("fvg"):                      # the move that made the swing must have left a gap (FVG)
        seg = range(j0, j + 1)
        kb0 = min(seg, key=lambda q: (ls[q], q)) if d == 1 else min(seg, key=lambda q: (-hs[q], q))
        if not any((ls[q + 1] > hs[q - 1]) if d == 1 else (hs[q + 1] < ls[q - 1]) for q in range(kb0 + 1, j)):
            return None, "the move left no FVG"
    kb = j0
    for q in range(j0, n):
        if (ls[q] < ls[kb]) if d == 1 else (hs[q] > hs[kb]):
            kb = q
    lo, hi = (ls[kb], lvl) if d == 1 else (lvl, hs[kb])
    leg = hi - lo
    if leg <= 0 or not atr or leg < pp["minleg"] * atr:
        return None, "the move is too small"
    if pp.get("maxleg") and leg > pp["maxleg"] * atr:
        return None, "the move is too big for this timeframe"
    tps = [float(x) for x in pp["tps"]]
    if d == 1:
        E, S, G = hi, hi - pp["sfib"] * leg - pp["slb"] * atr, [hi + x * leg for x in tps]
    else:
        E, S, G = lo, lo + pp["sfib"] * leg + pp["slb"] * atr, [lo - x * leg for x in tps]
    risk = abs(E - S)
    if not (risk > 0 and abs(G[-1] - E) >= risk and ((d == 1 and G[0] > E > S) or (d == -1 and G[0] < E < S))):
        return None, "the target would be smaller than the stop"
    if not (pp["start"] <= mins < pp["end"]):
        return None, f"outside the hours {pp['start'] // 60:02d}:{pp['start'] % 60:02d}-{pp['end'] // 60:02d}:{pp['end'] % 60:02d} NY"
    tr = int(pp["trend"])
    if not (tr == 0 or (tr == 1 and bias != -d) or (tr == 2 and bias == d)):
        return None, "against the trend rule"
    if open_opp:
        return None, "a trade the other way is open"
    if open_same >= int(pp["stack"]):
        return None, "enough trades this way"
    if (d == 1 and not cs[-1] < E) or (d == -1 and not cs[-1] > E):
        return None, "price is already beyond the entry"
    ob = kb
    for q in range(kb, max(kb - 5, 0) - 1, -1):
        if (bars[q].c < bars[q].o) if d == 1 else (bars[q].c > bars[q].o):
            ob = q
            break
    return dict(dir=d, E=E, S=S, tps=G, lo=lo, hi=hi, swing_t=bars[j].t, base_t=bars[kb].t, ob_hi=bars[ob].h,
                ob_lo=bars[ob].l, ob_t=bars[ob].t, risk=risk, fib=[float(pp["sfib"])] + tps), ""

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

# a light joke under the result messages (JOKES=0 turns them off)
JOKES = ENV("JOKES", "1") == "1"
JOKES_TP = [
    "الهدف انضرب، وهلّق فيك تقول لمرتك «شغّال، مش عم إلعب عالتلفون» 😎",
    "السوق اليوم مشي معنا متل ما بتمشي المي بالساقية 🌊",
    "ضرب التارغت وما لحق يشرب قهوتو ☕️",
    "هيك بيتحرّك السعر لما يعرف إنو العنقاء ناطرتو 🔥",
    "الشمعة طلعت أسرع من سيرفيس الحمرا بيوم أحد 🚐",
    "خلّي الأرباح تشتغل، ونحنا منشتغل عالانضباط 💪",
    "تارغت مضروب… حدا يبلّغ البنك إنو جايين 🏦",
    "السوق قال: خود يا معلّم 🎁",
    "مبروك! بس ما تصير تشتري يخت من أول صفقة ⛵️",
    "كبسة هدف نضيفة، متل منقوشة الصبح الطازة 🫓",
    "اليوم السعر سمع الكلمة من أول مرة 👂",
    "ربح وبهدوء… هيدا اسمو احتراف 🎯",
    "التارغت انضرب أسرع من ما ترجع الكهربا بعد التقنين ⚡️",
    "اليوم السوق عزمنا عالغدا وما دفّعنا الحساب 🍽",
    "صفقة نضيفة متل صحن تبولة عند ستّي 🥗",
    "السعر مشي عالخط متل تاكسي بيعرف الطريق 🚕",
    "ربحنا، بس خلّي الإيد عالأرض… الانضباط أول 🙌",
    "هيدا التارغت بيستاهل كاسة شاي وكعكة 🫖",
    "السوق قلّنا: تفضّلوا، البيت بيتكم 🏡",
    "ضربة معلّم… حتى الشارت انبسط 📈",
    "مبروك! هلّق فيك تقول عن حالك تريدر بثقة 😏",
    "الأرباح وصلت قبل الديليفري 🛵",
    "شمعة خضرا ورا شمعة خضرا… متل عرس بالضيعة 🎉",
    "التارغت ضرب، والمولّد بعدو شغّال كمان 🔌",
    "ربحنا اليوم… العشا عليك يا معلّم 🍢",
    "السعر طلع عالتارغت متل ما بيطلع الدولار بالسوق السودا 💵",
    "هيك صفقات بتخلّي الحماة تحبّك 😅",
    "التارغت انضرب، وحتى الجيران سمعوا الصريخ 📣",
    "من اليوم ورايح، اسمك عالشارت: أبو التارغت 👑",
    "صفقة بتستاهل أرگيلة عالبحر 🌊",
    "السوق اليوم كان كريم متل عرس لبناني 💃",
    "هيدا الربح بيكفّي بنزين للأسبوع… تقريباً ⛽️",
]
JOKES_SL = [
    "الستوب عمل شغلو، متل الحزام بالسيارة 🚗",
    "السوق أخد أجرة الدرس، والدرس محفوظ 📚",
    "خسارة صغيرة ومحسوبة… الكبار بيخسروا صغير 😌",
    "حتى العنقاء بتوقع قبل ما تطير من جديد 🔥",
    "اليوم السعر كان معصّب شوي، بكرا بيروق ☁️",
    "هيدي مش خسارة، هيدي ضريبة دخول السوق 🧾",
    "ولا يهمك، الشمس بتطلع بكرا وكمان التارغت 🌅",
    "السوق قال: مش هلّق يا حبيبي ⏳",
    "ستوب صغير أحسن من حساب فاضي 🙏",
    "خدنا نفس، شربنا مي، ومنرجع أقوى 💧",
    "حتى أحسن طبّاخ بتنحرق معو الطبخة مرّة 🍳",
    "السوق أخد الستوب ورجّع لنا الخبرة ببلاش 🎓",
    "مش كل يوم عيد… بكرا منعيّد 🎈",
    "الستوب متل المظلّة: بيحميك من الشتي الكبير ☔️",
    "صغيرة وبتمرق… متل زحمة الدورة الصبح 🚗",
    "السوق اليوم كان مزاجو متل الطقس بلبنان: ما بينعرف 🌦",
    "خسرنا صفقة، ما خسرنا الخطة 📋",
    "روق، القهوة بعدها سخنة والسوق بعدو فاتح ☕️",
    "السوق خدلنا الستوب متل ما الصرّاف بياخد العمولة 🏧",
    "ولا يهمك، حتى ميسي بيضيّع بنالتي ⚽️",
    "الستوب ضرب… منقول «يللا» ومنكمّل متل كل لبناني 🇱🇧",
    "اليوم السوق عملنا متل شرطي السير: وقّفنا بلا سبب 🚦",
    "خسارة صغيرة، بتنتسى قبل ما يبرد الشاي 🫖",
    "السوق بيمزح معنا… بكرا منردّلو المزحة 😏",
]
JOKES_SAFE = [
    "طلعنا سالمين، والسلامة أهم من الغنيمة 🛡",
    "لا ربحنا ولا خسرنا… بس السوق عرف إنو نحنا مش لقمة سهلة 😏",
    "الحماية عملت شغلها، متل الإمّ لما تقلّك خود جاكيت 🧥",
    "ربح مقفول بالجيبة، والباقي عالله 🔒",
    "شو ما صار، رجعنا عالبيت ومعنا شي 🏠",
    "السوق حاول يقرصنا، بس الحماية كانت أسرع 🦟",
    "طلعنا متل الشعرة من العجينة 🍞",
    "مش ربح كبير، بس أحسن من نومة عالخسارة 😴",
    "الستوب المحمي عمل شغلو متل الناطور عالبناية 🏢",
    "حبة حبة بيمتلي الكيس 💰",
    "خرجنا بكرامتنا والجيبة سليمة 👌",
    "متل لما تطلع من عزومة شبعان وما دفعت 😌",
    "الحماية أحسن من التأمين الصحي عنّا 🩺",
    "السوق فتّش جيابنا وما لقى شي 🕵️",
    "مش كل الصفقات أبطال، في منها دبلوماسيين 🤝",
    "صفر خسارة… هيدا بحد ذاتو انتصار 🏳️",
]
JOKES_TP_EN = [
    "Target hit. Your banker just started returning your calls 📞",
    "The market said yes faster than your crush ever did 😏",
    "Profit secured. Tonight dinner is on you, legend 🍽",
    "That candle ran like it saw its ex at the mall 🏃",
    "Target hit. Screenshot it, frame it, show your mother-in-law 🖼",
    "Green day. Even your coffee tastes richer ☕️",
    "The chart did exactly what we told it. Good chart 🐕",
    "Money printer goes brrr… responsibly 🖨",
    "Another one. DJ Khaled would be proud 🎧",
    "Target hit before the pizza arrived 🍕",
    "Smooth like your best pickup line, but it actually worked 😎",
    "Profit in the pocket, ego in check 💼",
    "The market blinked first 👀",
    "Plan, patience, payday 💸",
    "That trade had more confidence than a gym selfie 💪",
]
JOKES_SL_EN = [
    "Stop hit. Even Batman needs a backup plan 🦇",
    "The market took a small fee for today's lesson 🎓",
    "Small loss, big discipline. That's how the pros roll 😌",
    "We lost the battle, not the war ⚔️",
    "The market said 'not today'… we heard 'tomorrow' 🌅",
    "Stop loss: the seatbelt nobody likes but everyone needs 🚗",
    "Even Messi misses penalties sometimes ⚽️",
    "The chart ghosted us. Its loss 👻",
    "Deep breath, sip of water, back to the plan 💧",
    "Losses are tuition fees. At least this class was cheap 📚",
    "Mr. Market woke up grumpy. Happens 😤",
    "It's not a loss, it's a plot twist 🎬",
]
JOKES_SAFE_EN = [
    "Walked out safe. Ninja exit 🥷",
    "No loss, no drama, no therapy needed 🛋",
    "The market tried to pickpocket us. Nice try 🧤",
    "Locked profit. Smart money moves only 🔒",
    "Break even: the trading version of a polite handshake 🤝",
    "We left the party before the cops came 🚓",
    "Protected and happy, like a cat in a box 📦",
    "A little profit is still profit. Stack it 🧱",
    "Safe exit. Mom would be proud 👩",
    "The stop moved up, the stress moved out 😮‍💨",
]
JN = 0
EN_MARK = "\u2063"                                     # invisible mark: this line is for English-only readers

def joke(pool, pool_en=None):
    """Next joke (rotates, saved with the state): the Arabic one, plus an English one that only
    English-only readers see. Empty when JOKES is off."""
    global JN
    if not JOKES or not pool:
        return ""
    j = pool[JN % len(pool)]
    out = f"\n\n😄 <i>{html.escape(j)}</i>"
    if pool_en:
        out += f"\n{EN_MARK}😄 <i>{html.escape(pool_en[JN % len(pool_en)])}</i>"
    JN += 1
    return out

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

def point(sym):
    """1 MT5 point = the price step of the OneRoyal symbol = pip / 10 (gold 0.01, silver 0.001, Dow / Nasdaq 0.1, oil 0.001)."""
    return INSTRUMENTS[sym]["pip"] / 10.0

def pts(sym, dist):
    return f"{abs(dist) / point(sym):,.0f}"

def usd_txt(sym, dist):
    """A price distance as $ at the lot shown (LOT_DEFAULT, never below the smallest lot)."""
    return f"${abs(money(sym, dist, LOT_DEFAULT)):,.2f}"

def prot_steps(o):
    """The protection of this order as distances from the entry: [(reached at, stop goes to), ...]; stop goes to 0 =
    entry. Money ($ at the lot shown) or shares of the way to the target, as the tested setting says."""
    sym = o["sym"]
    pp = plan_params(sym, o["tf"])
    if pp.get("protect", PROTECT) == "usd":
        be, at, lk = pp.get("be_usd", BE_USD), pp.get("lock_at_usd", LOCK_AT_USD), pp.get("lock_usd", LOCK_USD)
        steps = [(usd_px(sym, be), 0.0)] if be > 0 else []
        if at > 0 and lk > 0:
            steps.append((usd_px(sym, at), usd_px(sym, lk)))
        return steps
    tg = abs(o["tps"][0] - o["trig"])
    be = pp.get("be_at_r", BE_AT_R)
    steps = [(be * tg, 0.0)] if be > 0 else []
    for at, to in ((pp.get("lock1_at", LOCK1_AT), pp.get("lock1_to", LOCK1_TO)),
                   (pp.get("lock2_at", LOCK2_AT), pp.get("lock2_to", LOCK2_TO))):
        if at > 0 and to > 0:
            steps.append((at * tg, to * tg))
    return steps

def prot_rows(o):
    """The protection of this order as prices: where the stop goes to entry, and where it locks profit."""
    sym, d, trig = o["sym"], o["dir"], o["trig"]
    rows = []
    for at, to in prot_steps(o):
        if to <= 0:
            rows.append(f"🛡 At <code>{fmt(sym, trig + d * at)}</code> (+{usd_txt(sym, at)}) → stop to entry")
        else:
            rows.append(f"🔒 At <code>{fmt(sym, trig + d * at)}</code> (+{usd_txt(sym, at)}) → stop to "
                        f"<code>{fmt(sym, trig + d * to)}</code> (+{usd_txt(sym, to)} locked)")
    return rows

def title(o):
    return f"{ICON.get(o['sym'], '•')} <b>{o['sym']}</b> {INSTRUMENTS[o['sym']]['name']}  ·  ⏱ <b>{o['tf'].upper()}</b>"

def short(o):
    return f"{ICON.get(o['sym'], '•')} {o['sym']} · {o['tf'].upper()} · {o['kind']} @ {fmt(o['sym'], o['trig'])}"

def rr_txt(o):
    return " / ".join(f"1:{r:g}" for r in o["rrs"])

def msg_signal(o, bias_info, price=None, late=False):
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
        rows.append(f"🎯 Entry          <code>{fmt(sym, o['trig'])}</code>  · {pts(sym, away)} points {where}")
    else:
        rows.append(f"🎯 Entry          <code>{fmt(sym, o['trig'])}</code>")
    risk = o["sl"] - o["trig"]
    rows.append(f"🛑 Stop loss     <code>{fmt(sym, o['sl'])}</code>  · −{pts(sym, risk)} points · −{usd_txt(sym, risk)}")
    for i, (tp, r) in enumerate(zip(o["tps"], o["rrs"]), 1):
        name = "Take profit" if len(o["tps"]) == 1 else f"Target {i}"
        rows.append(f"🏆 {name}  <code>{fmt(sym, tp)}</code>  · +{pts(sym, tp - o['trig'])} points · "
                    f"+{usd_txt(sym, tp - o['trig'])} · 1:{r:g}")
    prot = prot_rows(o)
    if o.get("src"):                                 # a zone order: which zone, and the market open it was drawn at
        what = ("📦 Order block (buy)" if o["dir"] == 1 else "📦 Order block (sell)") if o["src"] == "OB" else \
               ("📍 Buy zone" if o["dir"] == 1 else "📍 Sell zone")
        ar = ("أوردر بلوك شراء" if o["dir"] == 1 else "أوردر بلوك بيع") if o["src"] == "OB" else \
             ("منطقة شراء ما انكسرت" if o["dir"] == 1 else "منطقة بيع ما انكسرت")
        trend += (f"\n{what} <code>{fmt(sym, o['zlo'])}</code> – <code>{fmt(sym, o['zhi'])}</code> · "
                  f"{o.get('sess', '').title()} open · {ar}")
    if plan_params(sym, o["tf"]).get("weak"):        # a year of the three lost money in the tests
        trend += "\n⚠️ Weak in the 3-year test (a losing year): trade it smaller · ضعيف بالتجربة، خفّف اللوت"
    when = ""
    if late:                                         # planned on a candle the bot caught up later
        t_close = datetime.fromtimestamp(o["born_t"] + TF_SEC[o["tf"]], MSG_TZ).strftime("%H:%M")
        when = f"🕒 <i>From the {o['tf'].upper()} candle of {t_close}, still waiting for its entry</i>\n"
    return (f"🔥 <b>PHOENIX HAZ SMC</b>  ·  <i>New signal · إشارة جديدة</i>\n{LINE}\n"
            f"{title(o)}\n{d} <b>{o['kind']}</b> — {KIND_AR.get(o['kind'], '')}\n{trend}\n\n"
            + "\n".join(rows) + ("\n\n" + "\n".join(prot) if prot else "") +
            f"\n\n📊 Trend <b>{bias_info['txt']}</b>\n      {bias_info['arrows']}\n" + when +
            f"⏳ Pending: waits for price to reach the entry\n" + day_rules_txt(sym, o["tf"]) +
            f"💵 1 point = {point(sym):g} · ${money(sym, point(sym), LOT_DEFAULT):,.2f} at lot {lot_for(sym, LOT_DEFAULT):g}"
            + (" · move the stop when the bot says so (within the minute)" if MINUTES else
               " · the stop is moved at a candle close" if REAL_STOP else "") + "\n"
            f"💡 <i>Enter a touch early, close a touch before the target.</i>" + footer())

def day_rules_txt(sym, tf):
    """The small-account day rules of this chart, one line (empty when there are none)."""
    pp = plan_params(sym, tf)
    tgt, ml = user_or_tested("DAY_TARGET_USD", pp, "day_target"), user_or_tested("DAY_MAX_LOSS_USD", pp, "day_max_loss")
    if not tgt and not ml:
        return ""
    parts = ([f"target +${tgt:g}"] if tgt else []) + ([f"loss limit −${ml:g}"] if ml else [])
    return f"🎯 Today on this chart: {' · '.join(parts)} (closed $), then done for the day\n"

def msg_day_done(sym, tf, net, target, lot):
    i = INSTRUMENTS[sym]
    head = ("🎯 <b>Daily target reached</b> · وصلنا هدف النهار" if target else
            "🛑 <b>Daily loss limit reached</b> · وصلنا حد الخسارة بالنهار")
    sign = "+" if net >= 0 else "−"
    return (f"{head}\n{LINE}\n{i['name']} {sym} · ⏱ {tf.upper()}\n"
            f"💵 Today (closed): <b>{sign}${abs(net):,.2f}</b> at lot {lot:g}\n"
            + ("✅ Close the open trades if that is your way, take the profit. No more orders on this pair today.\n"
               "✅ سكّر الصفقات المفتوحة إذا هيك طريقتك، واسحب الربح. ما في أوامر جديدة عهالزوج اليوم."
               if target else
               "⏸ No more orders on this pair today; the open trades keep their stops.\n"
               "⏸ ما في أوامر جديدة اليوم، والصفقات المفتوحة بتضل عستوباتها.") + footer())

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
    dist = o["tps"][i] - o["trig"]
    near = pct(o["adv"], o["risk"])
    extra = "" if final else f"\nMove your stop to entry. Next target <code>{fmt(sym, o['tps'][i + 1])}</code>."
    return (f"✅ <b>TARGET HIT</b> · +{r:g}R · +{pts(sym, dist)} points · +{usd_txt(sym, dist)} 🎉\nمبروك، ضرب الهدف\n"
            f"{html.escape(short(o))}{extra}\n\n"
            f"Closest it came to the stop: <b>{near}%</b> of the way." + joke(JOKES_TP, JOKES_TP_EN) + footer())

def msg_sl(o):
    sym = o["sym"]
    best = pct(o["fav"], abs(o["tps"][0] - o["trig"]))
    return (f"❌ <b>STOP LOSS HIT</b> · −1R · −{pts(sym, o['sl'] - o['trig'])} points · −{usd_txt(sym, o['sl'] - o['trig'])}\n"
            f"ضرب وقف الخسارة. خسارة صغيرة ومحسوبة، ومنكمّل بانضباط.\n{html.escape(short(o))}\n\n"
            f"Best it reached toward the target: <b>{best}%</b> of the way." + joke(JOKES_SL, JOKES_SL_EN) + footer())

def msg_be(o):
    if o.get("hits", 0) > 0:
        best = pct(o["fav"], abs(o["tps"][-1] - o["trig"]))
        return (f"⚖️ <b>STOPPED AT ENTRY</b> · target 1 was already reached ✅\n{html.escape(short(o))}\n\n"
                f"The rest closed at entry. Best toward the last target: <b>{best}%</b>." + joke(JOKES_SAFE, JOKES_SAFE_EN) + footer())
    best = pct(o["fav"], abs(o["tps"][0] - o["trig"]))
    return (f"🛡 <b>PROTECTED EXIT</b> · 0R · طلعت على الدخول بدون خسارة\n{html.escape(short(o))}\n\n"
            f"Price had reached <b>{best}%</b> of the way to the target, so the stop was at entry." + joke(JOKES_SAFE, JOKES_SAFE_EN) + footer())

def where_txt(o, share):
    """How far the trade has come: in $ at the lot shown and as a share of the way to the target."""
    return f"price reached <b>+{usd_txt(o['sym'], o['fav'])}</b> ({share}% of the way to the target)"

def msg_protect(o, share):
    sym = o["sym"]
    if o.get("locked") and o.get("lock_d", 0) > 0:          # break-even after costs: entry + spread + commission
        px = fmt(sym, o["lock_px"])
        return (f"🛡 <b>PROTECT YOUR TRADE</b> · {where_txt(o, share)}\n"
                f"انقل الستوب لـ <code>{px}</code> (الدخول + الكوميشن والسبريد)\n{html.escape(short(o))}\n\n"
                f"Move your stop to <code>{px}</code> (entry + costs): from here the trade can not turn into a loss." + footer())
    return (f"🛡 <b>PROTECT YOUR TRADE</b> · {where_txt(o, share)}\n"
            f"انقل الستوب على سعر الدخول\n{html.escape(short(o))}\n\n"
            f"Move your stop to entry: from here the trade can not turn into a loss." + footer())

def msg_lock(o, share):
    sym = o["sym"]; d = o["lock_d"]
    usd = money(sym, d, LOCK_LOT)
    return (f"🔒 <b>LOCK PROFIT</b> · {where_txt(o, share)}\n"
            f"انقل الستوب لـ <code>{fmt(sym, o['lock_px'])}</code> وقفّل ربح\n{html.escape(short(o))}\n\n"
            f"Move your stop to <code>{fmt(sym, o['lock_px'])}</code>: +{pts(sym, d)} points locked "
            f"(≈ ${usd:,.2f} at lot {lot_for(sym, LOCK_LOT):g})." + footer())

def msg_locked(o):
    sym = o["sym"]; d = o.get("lock_d", 0.0)
    best = pct(o["fav"], abs(o["tps"][0] - o["trig"]))
    return (f"🔒 <b>PROFIT LOCKED EXIT</b> · +{pts(sym, d)} points · +{usd_txt(sym, d)} ✅\nطلعت بربح مقفول\n"
            f"{html.escape(short(o))}\n\n"
            f"Price reached <b>{best}%</b> of the way to the target, then came back to the locked stop." + joke(JOKES_SAFE, JOKES_SAFE_EN) + footer())

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

def menu_markup(sub, owner=False):
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
    rows.append([{"text": "🌐 English" if sub.get("lang") != "en" else "🌐 عربي", "callback_data": "lang"}])
    if owner:
        rows.append([{"text": "🎯 Calibrate prices · ظبّط الأسعار", "callback_data": "cal"}])
    return {"inline_keyboard": rows}

def calib_markup():
    syms = [x for x in AVAILABLE_SYMS if x in INSTRUMENTS]
    rows = [[{"text": ICON.get(x, "") + " " + INSTRUMENTS[x]["name"], "callback_data": "c:" + x} for x in syms[i:i + 2]]
            for i in range(0, len(syms), 2)]
    rows.append([{"text": "✖ Cancel", "callback_data": "cx"}])
    return {"inline_keyboard": rows}

def msg_welcome(name):
    who = html.escape(name) if name else "trader"
    return (f"🔥 <b>Welcome to PHOENIX HAZ SMC</b>\nأهلاً وسهلاً فيك يا {who} 🤝\n{LINE}\n"
            "Fibonacci breakout orders on Gold, Nasdaq and Dow (Silver and Oil when they pass the test): entry, stop and "
            "three targets from the Fibonacci of the move, followed live until the end.\n"
            "أوامر فيبوناتشي عند كسر القمم والقيعان على الذهب والناسداك والداو: دخول ووقف وتلات أهداف من فيبوناتشي الحركة، ومتابعة كل صفقة لآخرها.\n\n"
            "<b>What you get · شو بيوصلك</b>\n"
            "🎯 Every order with the price now, entry, stop and 3 targets (with their Fibonacci level)\n"
            "⚡ Live updates: filled, TP1 → stop to entry, TP2 → stop to TP1, closed\n"
            "☀️ A morning brief and 🌙 a market-close summary\n"
            "📊 /report: today, week and month in points and $\n\n"
            "<b>How to start · كيف تبلّش</b>\n"
            "1️⃣ Choose instruments and timeframes below · اختار الأدوات والفريمات تحت\n"
            "2️⃣ Set your lot: /lot 0.1 · حدّد اللوت\n"
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
            f"🛡 Risk 1–2% per trade. Put the STOP order as it comes; at TP1 move the stop to the entry, at TP2 to TP1 "
            f"(the bot tells you within the minute). Every order shows how its chart did in every test year.\n\n"
            f"✨ <i>{html.escape(en)}</i>\n<i>{html.escape(ar)}</i>" + footer())

def stats_text(sub, ledger, ref_ts):
    """Every instrument with every timeframe (Gold 5M, Gold 15M ...), then each timeframe for all
    instruments together, then the total. Money in $ (points of different instruments can not be added)."""
    syms = [x for x in (sub["syms"] or list(INSTRUMENTS)) if x in INSTRUMENTS]
    tfs = [t for t in TF_SEC if t in sub["tfs"] and t in AVAILABLE_TFS]
    has = lambda sm: any(sm[k]["win"] or sm[k]["loss"] or sm[k]["be"] for k in ("day", "week", "month"))

    def usd_rows(sm):                         # narrow rows: fit a phone screen without wrapping
        return [f"<code>{name:<6}{sm[k]['win']:>3}W{sm[k]['loss']:>3}L{sm[k]['be']:>3}BE {sm[k]['usd']:>+9,.2f}$</code>"
                for name, k in (("Today", "day"), ("Week", "week"), ("Month", "month"))]

    blocks = []
    for sym in syms:
        allm = summarize(ledger, [sym], tfs, sub["lot"], ref_ts)
        head = f"{ICON.get(sym, '•')} <b>{INSTRUMENTS[sym]['name']}</b>"
        if not has(allm):
            blocks.append(f"{head}  <i>· no closed trades this month</i>")
            continue
        mo = allm["month"]
        parts = [f"{head}  <i>· month {mo['usd']:+,.2f}$ · {mo['pts']:+,.0f} points</i>"]
        for tf in tfs:
            sm = summarize(ledger, [sym], [tf], sub["lot"], ref_ts)
            if has(sm):
                parts.append(f"⏱ <b>{INSTRUMENTS[sym]['name']} · {tf.upper()}</b>\n" + "\n".join(usd_rows(sm)))
        blocks.append("\n".join(parts[:1]) + "\n" + "\n\n".join(parts[1:]))

    tf_blocks = []                            # each timeframe, all chosen instruments together
    for tf in tfs:
        sm = summarize(ledger, syms, [tf], sub["lot"], ref_ts)
        if has(sm):
            tf_blocks.append(f"⏱ <b>{tf.upper()}</b>\n" + "\n".join(usd_rows(sm)))
    tf_txt = ("\n\n📐 <b>By timeframe · حسب الفريم</b> (all instruments)\n" + "\n\n".join(tf_blocks)) if tf_blocks else ""
    tot = summarize(ledger, syms, tfs, sub["lot"], ref_ts)
    return ("\n\n".join(blocks) + tf_txt + f"\n\n💼 <b>Total · المجموع</b>\n" + "\n".join(usd_rows(tot)) +
            "\n<i>W ربح · L خسارة · BE طلعت على الدخول</i>")

def today_line(sub, ledger, ref_ts):
    """One line: what we did today, all chosen instruments and timeframes together."""
    syms = [x for x in (sub["syms"] or list(INSTRUMENTS)) if x in INSTRUMENTS]
    d = summarize(ledger, syms, [t for t in sub["tfs"] if t in AVAILABLE_TFS], sub["lot"], ref_ts)["day"]
    icon = "🟢" if d["usd"] > 0 else "🔴" if d["usd"] < 0 else "⚪️"
    return (f"{icon} <b>Today · اليوم</b>  {d['win']}W · {d['loss']}L · {d['be']}BE  ·  <b>{d['usd']:+,.2f}$</b>")

def msg_close(sub, stats, n_signals, weekly, lines_i, today=""):
    en, ar = CLOSE_LINES[lines_i % len(CLOSE_LINES)]
    head = "🌙 <b>WEEK CLOSED</b> · سكّر السوق للأسبوع" if weekly else "🌙 <b>MARKET CLOSED</b> · سكّر السوق"
    return (f"{head}\n{LINE}\n📨 Signals today: <b>{n_signals}</b>\n" + (today + "\n" if today else "") + "\n" + stats +
            f"\n\n<i>Lot {sub['lot']:g} · estimates from each plan's target and stop.</i>\n\n"
            f"✨ <i>{html.escape(en)}</i>\n<i>{html.escape(ar)}</i>" + footer())

def msg_report(sub, stats, title="REPORT"):
    s, t = sel_text(sub)
    return (f"📊 <b>PHOENIX HAZ SMC</b>  ·  {title}\n{LINE}\n⏱ <b>{t}</b>\n\n" + stats +
            f"\n\n<i>Lot {sub['lot']:g}. Estimates from each plan's target and stop, not your broker statement.</i>\n"
            f"<i>التقديرات مبنية على هدف ووقف كل خطة وليست كشف حسابك لدى الوسيط.</i>" + footer())

HELP = (f"🔥 <b>PHOENIX HAZ SMC</b>\n{LINE}\n/start · choose instruments and timeframes\n/price · prices now\n"
        "/status · what you receive\n/lot 0.1 · lot size for the money numbers\n/report · today, week, month\n"
        "/lang en · English only (/lang ar · Arabic + English)\n/stop · pause all signals\n\n" + SIGN)

def msg_dayend(o, r, gain_pts):
    s = "+" if r >= 0 else "−"
    return (f"⏹ <b>TIME LIMIT</b> · ≈ {s}{abs(r):.1f}R ({s}{gain_pts} points)\nالصفقة طوّلت كتير، سكّرها على السوق\n"
            f"{html.escape(short(o))}" + footer())

BOT_COMMANDS = [("start", "Choose instruments and timeframes"), ("price", "Prices now"), ("report", "Today, week, month"),
                ("status", "What you receive"), ("lot", "Lot size, e.g. /lot 0.1"), ("lang", "English only / Arabic + English"),
                ("stop", "Pause all signals"), ("help", "Help")]
BOT_DESCRIPTION = ("🔥 PHOENIX HAZ SMC v20\nFibonacci breakout orders for Gold, Nasdaq and Dow: price now, entry, stop, "
                   "3 targets and live follow-up (when to move the stop). Morning brief and market-close summary.\n"
                   "إشارات أوامر معلّقة على الذهب والفضة والداو والناسداك والنفط مع متابعة مباشرة.\n"
                   "Press START · اضغط START\n⚠️ Educational only, not financial advice.")
BOT_SHORT = "Gold · Silver · Dow · Nasdaq · Oil signals with live follow-up · The Phoenix HAZ Syndicate"

# ── English-only messages (/lang en): the Arabic half of every message is removed
AR = re.compile(r"[\u0600-\u06FF]")
AR_PART = re.compile(r"\s*[·—]\s*[^·—<\n]*[\u0600-\u06FF][^·—<\n]*")

def to_en(text):
    out = []
    for line in text.split("\n"):
        if AR.search(line):
            line = AR_PART.sub("", line)                 # "English · عربي" -> "English"
            if AR.search(line):
                continue                                 # a line that is Arabic only
        out.append(line)
    t = "\n".join(out)
    while "\n\n\n" in t:
        t = t.replace("\n\n\n", "\n\n")
    return t.strip()

def msg_lang(sub):
    if sub.get("lang") == "en":
        return "🌐 Messages are now in <b>English</b> only. Send /lang ar for Arabic."
    return "🌐 الرسائل صارت <b>بالعربي</b>. للإنكليزي ابعت /lang en"

# ───────────────────────────── v29 messages (Fibonacci orders) ─────────────────────────────
# Every message is written twice: in Arabic for the channel and the Arabic readers, and in English on lines marked
# EN_MARK that only the English-only readers (/lang en) get. Prices, $ (at the lot shown, after spread + commission)
# and the time of every step: how long the order waited, how long the trade has been running, how long it took.
TF_AR = {"1m": "دقيقة", "5m": "5 دقايق", "15m": "ربع ساعة", "30m": "نص ساعة", "1h": "ساعة"}


AR_MARK = "\u2064"                                     # invisible mark: this line is for Arabic readers only


def bi(ar, en):
    """One line in Arabic (Arabic readers) and the same line in English (English-only readers): never both."""
    return f"{AR_MARK}{ar}\n{EN_MARK}{en}"


def v20_fib(x):
    t = f"{x:.3f}".rstrip("0")
    return t + "0" if t.endswith(".") else t


def v20_kind(o):
    return "BUY STOP" if o["dir"] == 1 else "SELL STOP"


def v20_head(o, en=False):
    tf = o["tf"].upper() if en else TF_AR.get(o["tf"], o["tf"])
    return f"{ICON.get(o['sym'], '•')} <b>{o['sym']}</b> · {tf}"


def v29_usd(sym, dist):
    """A price distance as signed $ at the lot shown (never below the smallest lot)."""
    v = money(sym, dist, LOT_DEFAULT)
    return f"{'+' if v >= 0 else '−'}${abs(v):,.2f}"


def v29_lot(sym):
    return f"{lot_for(sym, LOT_DEFAULT):g}"


def v29_dur(sec, en=False):
    """1h 25m / 1 س 25 د (minutes under an hour, days over a day)."""
    m = max(0, int(round(sec / 60.0)))
    if m < 60:
        if en:
            return f"{m} min"
        return "دقيقة" if m <= 1 else "دقيقتين" if m == 2 else f"{m} دقايق" if m <= 10 else f"{m} دقيقة"
    h, mm = divmod(m, 60)
    if h < 24:
        return (f"{h}h {mm:02d}m" if en else f"{h} س {mm} د")
    d, hh = divmod(h, 24)
    return f"{d}d {hh}h" if en else f"{d} يوم و{hh} س"


def v29_clock(t):
    return datetime.fromtimestamp(t, MSG_TZ).strftime("%H:%M")


def v20_years_txt(sym, tf, en=False):
    pp = v20_params(sym, tf) or {}
    y = pp.get("years") or []
    if len(y) < 4:
        return ""
    s = "  ".join(f"{yr} {'+' if v >= 0 else '−'}${abs(v):,.0f}" for yr, v in zip((2023, 2024, 2025, 2026), y))
    return f"🧾 {'Tested' if en else 'التيست'}: {s}"


def v20_level_rows(o, en=False):
    """Stop and targets, one short line each: price and $ at the lot shown (after spread + commission)."""
    sym, d, E = o["sym"], o["dir"], o["trig"]
    cost = cost_price(sym)
    n = len(o["tps"])
    stop_now = o.get("stop", o["sl"])
    rows = [f"🛑 {'SL' if en else 'ستوب'} <code>{fmt(sym, stop_now)}</code> ({v29_usd(sym, (stop_now - E) * d - cost)})"]
    for i, tp in enumerate(o["tps"]):
        mark = "✅" if o.get("hits", 0) > i else ("🏁" if i == n - 1 else "🎯")
        rows.append(f"{mark} {f'TP{i + 1}' if en else f'هدف {i + 1}'} <code>{fmt(sym, tp)}</code> ({v29_usd(sym, (tp - E) * d - cost)})")
    return rows


def short_note():
    return "\n" + bi("⚠️ <i>للتعليم فقط · مش نصيحة مالية</i>", "⚠️ <i>Education only · not financial advice</i>")


def msg_v20_new(o, bias, price=None, updated=False, late=False):
    """A new (or updated) order, short: side and entry, stop, targets with $, trend and price now, lot."""
    sym, d = o["sym"], o["dir"]
    tr_ar = {1: "▲ صاعد", -1: "▼ هابط"}.get(bias, "• مخلوط")
    tr_en = {1: "▲ BULL", -1: "▼ BEAR"}.get(bias, "• MIXED")
    tag_ar = "🔄 <b>تحديث</b>" if updated else "🔔 <b>أمر جديد</b>"
    tag_en = "🔄 <b>Updated</b>" if updated else "🔔 <b>New order</b>"
    out = [bi(f"{tag_ar} · {v20_head(o)}" + (" · 🕒" if late else ""), f"{tag_en} · {v20_head(o, True)}" + (" · 🕒" if late else "")),
           f"{'🟢' if d == 1 else '🔴'} <b>{v20_kind(o)}</b> <code>{fmt(sym, o['trig'])}</code>"]
    for a, e in zip(v20_level_rows(o), v20_level_rows(o, True)):
        out.append(bi(a, e))
    now_ar = f" · هلّق <code>{fmt(sym, price)}</code>" if price is not None else ""
    now_en = f" · now <code>{fmt(sym, price)}</code>" if price is not None else ""
    out.append(bi(f"📊 {tr_ar}{now_ar} · لوت {v29_lot(sym)}", f"📊 {tr_en}{now_en} · lot {v29_lot(sym)}"))
    return "\n".join(out) + short_note()


LINES_FILL = [
    ("💪 الخطة واضحة، والباقي عالانضباط.", "💪 The plan is clear; the rest is discipline."),
    ("🧠 دخلنا بخطة: ستوب محسوب وأهداف واضحة.", "🧠 In with a plan: a known stop and clear targets."),
    ("🎯 ما في شي عشوائي: الدخول عالسيولة والأهداف عالفيبوناتشي.", "🎯 Nothing random: entry at the liquidity, targets on the Fibonacci."),
]
LINES_TP = [
    ("💰 أوّل ربح وصل! أمّن وكفّي بقلب مرتاح.", "💰 The first profit is in! Secure it and carry on with peace of mind."),
    ("🎯 الخطة عم تمشي متل ما انرسمت.", "🎯 The plan is working exactly as drawn."),
    ("🦅 الفينيق طار، والستوب بيلحقو.", "🦅 The Phoenix is flying; the stop follows it."),
    ("🔥 كل هدف بيضرب، الربح بيكبر والصفقة بتصير أأمن.", "🔥 Every target hit: more profit, a safer trade."),
]
LINES_LAST = [
    ("🔥 هيك بتكون الصفقات! اللي صبر وكفّى للآخر قطف الربح كلّو 👑", "🔥 That's how it's done! Whoever held to the end took the whole profit 👑"),
    ("🚀 من الدخول للهدف الأخير متل ما انرسمت، مبروك لكل الفريق 🦅", "🚀 From the entry to the last target exactly as drawn — congrats to the whole team 🦅"),
    ("💎 صفقة كاملة وكل الأهداف انضربت! الانضباط بيدفع، مبروك 🎉", "💎 A full trade, every target hit! Discipline pays — congrats 🎉"),
]
LINES_SL = [
    ("🛡 الستوب جزء من الشغل: خسارة صغيرة ومحسوبة من الأول.", "🛡 The stop is part of the job: small and planned from the start."),
    ("💪 منحمي الحساب أول شي، والربح بيجي ورا.", "💪 Protect the account first; profits follow."),
    ("🧘 ولا صفقة بتعمل الشهر، الانضباط هو اللي بيعمل.", "🧘 No single trade makes the month; discipline does."),
]
LINES_BE = [
    ("💰 هدف 1 انضرب والربح كان بين إيديك، والباقي ما خسر ولا قرش 👌", "💰 TP1 was hit and the profit was there to take; the rest lost nothing 👌"),
    ("🛡 أمّنّا عهدف 1، فالسوق رجع وما أخد منّا شي.", "🛡 We secured at TP1, so when the market came back it took nothing from us."),
]
LINES_LOCK = [
    ("🔐 طلعنا بربح محفوظ: هيك بتنحمى الأرباح.", "🔐 Out with the profit kept: this is how gains are protected."),
    ("💰 الربح بالجيبة، والسوق بيرجع بيعطي فرص.", "💰 The profit is in the pocket; the market will give more chances."),
]


def v29_line(pool):
    global JN
    if not JOKES or not pool:
        return ""
    a, e = pool[JN % len(pool)]
    JN += 1
    return "\n" + bi(f"<i>{html.escape(a)}</i>", f"<i>{html.escape(e)}</i>")


def msg_v20_filled(o):
    sym, d, tf = o["sym"], o["dir"], o["tf"]
    at = o.get("fill_at", o.get("fill_t", time.time()))
    waited = max(0, at - (o["born_t"] + TF_SEC[tf]))
    out = [bi(f"⚡ <b>تفعّلت</b> {'🟢 شراء' if d == 1 else '🔴 بيع'} · {v20_head(o)}",
              f"⚡ <b>FILLED</b> {'🟢 BUY' if d == 1 else '🔴 SELL'} · {v20_head(o, True)}"),
           bi(f"🎯 <code>{fmt(sym, o['trig'])}</code> · 🛑 <code>{fmt(sym, o['sl'])}</code> · ⏱ استنّى {v29_dur(waited)}",
              f"🎯 <code>{fmt(sym, o['trig'])}</code> · 🛑 <code>{fmt(sym, o['sl'])}</code> · ⏱ waited {v29_dur(waited, True)}")]
    return "\n".join(out)


ORD_AR = ["الأول", "التاني", "التالت", "الرابع"]


def msg_v20_tp(o, k):
    """A target hit (not the last one): the profit there, and how to secure and carry on. Short."""
    sym, d = o["sym"], o["dir"]
    cost = cost_price(sym)
    gain = (o["tps"][k] - o["trig"]) * d - cost
    mv = o["mv"]
    nxt = o["tps"][k + 1]
    ran = max(0, o.get("hit_at", time.time()) - o.get("fill_at", o.get("fill_t", time.time())))
    where_ar = "الدخول" if k == 0 else f"هدف {k}"
    where_en = "the entry" if k == 0 else f"TP{k}"
    out = [bi(f"{'✅' * (k + 1)} <b>هدف {k + 1} انضرب!</b> {v29_usd(sym, gain)} 🎉 · {v20_head(o)}",
              f"{'✅' * (k + 1)} <b>TP{k + 1} HIT</b> {v29_usd(sym, gain)} 🎉 · {v20_head(o, True)}"),
           bi(f"💵 سكّر وخود ربحك، أو كفّي: الستوب عـ <code>{fmt(sym, mv)}</code> ({where_ar})",
              f"💵 Take the profit, or carry on: stop to <code>{fmt(sym, mv)}</code> ({where_en})"),
           bi(f"🎯 الجاي <code>{fmt(sym, nxt)}</code> ({v29_usd(sym, (nxt - o['trig']) * d - cost)}) · ⏱ {v29_dur(ran)}",
              f"🎯 Next <code>{fmt(sym, nxt)}</code> ({v29_usd(sym, (nxt - o['trig']) * d - cost)}) · ⏱ {v29_dur(ran, True)}")]
    return "\n".join(out) + v29_line(LINES_TP)


def msg_v20_exit(o):
    """The end of a trade, short: the result with $, entry -> exit, targets hit, the time it took."""
    sym, d, st = o["sym"], o["dir"], o["state"]
    cost = cost_price(sym)
    px = o.get("exit_px", o["sl"])
    net = (px - o["trig"]) * d - cost
    took = max(0, o.get("exit_at", o.get("exit_t", time.time())) - o.get("fill_at", o.get("fill_t", time.time())))
    n = len(o["tps"])
    h = int(o.get("hits", 0))
    gains = [(t - o["trig"]) * d - cost for t in o["tps"]]
    path = f"<code>{fmt(sym, o['trig'])}</code> ← <code>{fmt(sym, px)}</code>"
    path_en = f"<code>{fmt(sym, o['trig'])}</code> → <code>{fmt(sym, px)}</code>"
    if st == TP_HIT:
        out = [bi(f"🏆🎉 <b>مبروك! الهدف الأخير</b> · {v20_head(o)}", f"🏆🎉 <b>CONGRATS! LAST TARGET</b> · {v20_head(o, True)}"),
               bi(f"💰 <b>{v29_usd(sym, net)}</b> · {path} · {'✅' * h} · ⏱ {v29_dur(took)}",
                  f"💰 <b>{v29_usd(sym, net)}</b> · {path_en} · {'✅' * h} · ⏱ {v29_dur(took, True)}")]
        pool = LINES_LAST
    elif st == SL_HIT:
        out = [bi(f"❌ <b>ستوب</b> {v29_usd(sym, net)} · {v20_head(o)}", f"❌ <b>STOP LOSS</b> {v29_usd(sym, net)} · {v20_head(o, True)}"),
               bi(f"📍 {path} · ⏱ {v29_dur(took)}", f"📍 {path_en} · ⏱ {v29_dur(took, True)}")]
        pool = LINES_SL
    elif st == LOCK_HIT:
        out = [bi(f"🔒 <b>ربح محفوظ {v29_usd(sym, net)}</b> · {v20_head(o)}", f"🔒 <b>PROFIT KEPT {v29_usd(sym, net)}</b> · {v20_head(o, True)}"),
               bi(f"💵 اللي سكّر عهدف {h}: {v29_usd(sym, gains[h - 1])} · ⏱ {v29_dur(took)}",
                  f"💵 Closed at TP{h}: {v29_usd(sym, gains[h - 1])} · ⏱ {v29_dur(took, True)}")]
        pool = LINES_LOCK
    else:
        out = [bi(f"✅ <b>خلصت بعد هدف 1</b> · {v20_head(o)}", f"✅ <b>DONE AFTER TP1</b> · {v20_head(o, True)}"),
               bi(f"💵 اللي سكّر عهدف 1: {v29_usd(sym, gains[0])} · الباقي عالدخول · ⏱ {v29_dur(took)}",
                  f"💵 Closed at TP1: {v29_usd(sym, gains[0])} · the rest CLOSED AT ENTRY · ⏱ {v29_dur(took, True)}")]
        pool = LINES_BE
    return "\n".join(out) + v29_line(pool)


WHY_AR = {
    "no swing yet": "ما في قمة أو قاع جديد بعد",
    "the swing broke: waiting for a new one": "انكسرت القمة/القاع بإغلاق شمعة بلا ما يتفعّل: منستنّى وحدة جديدة",
    "this swing was traded already": "هالقمة/القاع انفاتت فيها قبل",
    "no base swing yet": "ما في بداية حركة واضحة",
    "the move left no FVG": "الحركة ما تركت فير فاليو غاب (FVG)",
    "the move is too small": "الحركة صغيرة عهالفريم",
    "the move is too big for this timeframe": "الحركة كبيرة عهالفريم (الصفقة كانت رح تطلع كبيرة)",
    "the target would be smaller than the stop": "الهدف كان رح يطلع أصغر من الستوب",
    "against the trend rule": "صار عكس الاتجاه",
    "a trade the other way is open": "في صفقة شغّالة بالعكس",
    "enough trades this way": "في صفقات كفاية بهالاتجاه",
    "price is already beyond the entry": "السعر صار بعد الدخول",
    "a newer swing replaced it": "إجت قمة/قاع أجدد وأخدت محلّو",
    "a trade the other way is open (never a buy and a sell together)": "انفتحت صفقة بالعكس (ما منفتح شراء وبيع سوا)",
    "the other order was filled (never a buy and a sell together)": "تفعّل الأمر التاني (ما منفتح شراء وبيع سوا)",
    "this chart has no tested setting": "هالشارت ما إلو إعدادات مجرّبة",
    "the order was never filled": "الأمر ما تفعّل بالوقت",
}


def msg_v20_cancel(o, reason):
    ar = WHY_AR.get(reason, reason)
    return (bi(f"🟣 <b>انلغى الأمر</b> · <i>{html.escape(ar)}</i>", f"🟣 <b>CANCELLED</b> · <i>{html.escape(reason)}</i>")
            + f"\n<s>{html.escape(short(o))}</s>")

# ───────────────────────────── telegram ─────────────────────────────
class Telegram:
    def __init__(self, token, channel, dry=False):
        self.token, self.channel, self.dry = token, channel, dry
        self.last_chat, self.last_any, self.fake_id, self.win = {}, 0.0, 1000, {}
        self.lang_of = None                      # set by the engine: chat id -> "en" or "ar"

    def _lang(self, chat, text):
        try:
            if self.lang_of and self.lang_of(chat) == "en":
                return to_en("\n".join(x for x in text.split("\n") if AR_MARK not in x)).replace(EN_MARK, "")
            return "\n".join(x for x in text.split("\n") if EN_MARK not in x).replace(AR_MARK, "")
        except Exception:
            return text

    @staticmethod
    def _is_group(chat):
        c = str(chat)
        return c.startswith("@") or c.startswith("-")

    def _call(self, method, payload, chat=None):
        now = time.time()
        wait = self.last_any + 0.04 - now
        if chat is not None:
            key = str(chat)
            wait = max(wait, self.last_chat.get(key, 0) + 1.05 - now)       # at most one message a second per chat
            if self._is_group(chat):                                      # and 19 a minute in a group / channel
                win = [x for x in self.win.get(key, []) if x > now - 60]
                self.win[key] = win
                if len(win) >= 19:
                    wait = max(wait, win[0] + 60.5 - now)
        if wait > 0:
            time.sleep(wait)
        if chat is not None and self._is_group(chat):
            self.win.setdefault(str(chat), []).append(time.time())
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
        text = self._lang(chat, text)
        if len(text) > 4000:                          # Telegram refuses messages over 4096 characters: send in parts
            parts, cur = [], ""
            for para in text.split("\n\n"):
                if cur and len(cur) + len(para) + 2 > 4000:
                    parts.append(cur); cur = para
                else:
                    cur = cur + "\n\n" + para if cur else para
            parts.append(cur)
            first = None
            for i, part in enumerate(parts):
                mid = self.send(part[:4096], chat=chat, reply_to=reply_to if i == 0 else None,
                                markup=markup if i == len(parts) - 1 else None)
                first = first or mid
            return first
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
        text = self._lang(chat, text)
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
    r = requests.get(url, headers={"Authorization": f"Bearer {(ENV('OANDA_TOKEN', '') or '').strip()}"}, timeout=20)
    r.raise_for_status()
    out = []
    for c in r.json()["candles"]:
        if not c.get("complete"):
            continue
        t = int(datetime.fromisoformat(c["time"][:19] + "+00:00").timestamp())
        m = c["mid"]
        out.append(Bar(t, float(m["o"]), float(m["h"]), float(m["l"]), float(m["c"])))
    return out

class CapitalFeed:
    """Capital.com REST prices (real time, CFD/spot candles like the CAPITALCOM charts on TradingView).
    Needs CAPITAL_API_KEY, CAPITAL_IDENTIFIER (login e-mail) and CAPITAL_PASSWORD (the API key's custom password)."""
    HOSTS = {"demo": "https://demo-api-capital.backend-capital.com", "live": "https://api-capital.backend-capital.com"}
    RES = {"1m": "MINUTE", "5m": "MINUTE_5", "15m": "MINUTE_15", "30m": "MINUTE_30", "1h": "HOUR", "4h": "HOUR_4", "1d": "DAY"}

    def __init__(self):
        self.hdr, self.base, self.used, self.last_call = None, None, 0.0, 0.0
        self.side = (ENV("CAPITAL_PRICE", "bid") or "bid").strip().lower()   # bid = what MetaTrader and TradingView draw

    def _wait(self):                                         # Capital.com allows 10 requests a second: stay well below
        gap = self.last_call + 0.12 - time.time()
        if gap > 0:
            time.sleep(gap)
        self.last_call = time.time()

    def login(self):
        key = (ENV("CAPITAL_API_KEY", "") or "").strip()
        body = {"identifier": (ENV("CAPITAL_IDENTIFIER", "") or "").strip(),
                "password": (ENV("CAPITAL_PASSWORD", "") or "").strip(), "encryptedPassword": False}
        first = (ENV("CAPITAL_ENV", "demo") or "demo").strip().lower()
        for env in [first] + [e for e in self.HOSTS if e != first]:   # a key made on the other account type still works
            self._wait()
            time.sleep(1.0)                                  # session creation: max 1 per second
            r = requests.post(self.HOSTS[env] + "/api/v1/session", json=body,
                              headers={"X-CAP-API-KEY": key, "Content-Type": "application/json"}, timeout=20)
            if r.ok and r.headers.get("CST"):
                self.base, self.used = self.HOSTS[env], time.time()
                self.hdr = {"CST": r.headers["CST"], "X-SECURITY-TOKEN": r.headers.get("X-SECURITY-TOKEN", "")}
                log.info("Capital.com session OK (%s)", env)
                return
            log.warning("Capital.com login on %s refused (%s)", env, r.status_code)   # never log the key or password
        raise RuntimeError("Capital.com login failed: check CAPITAL_API_KEY, CAPITAL_IDENTIFIER, CAPITAL_PASSWORD")

    def get(self, path, params):
        for attempt in range(2):
            if self.hdr is None or time.time() - self.used > 540:      # sessions expire after 10 idle minutes
                self.login()
            self._wait()
            r = requests.get(self.base + path, params=params, headers=self.hdr, timeout=20)
            self.used = time.time()
            if r.status_code in (401, 403) and attempt == 0:
                self.hdr = None
                continue
            r.raise_for_status()
            return r.json()

    def candles(self, sym, tf, now):
        epic = INSTRUMENTS[sym]["capital"]
        out = self._parse(self.get(f"/api/v1/prices/{epic}", {"resolution": self.RES[tf], "max": 1000}))
        sec = 86400 if tf == "1d" else 14400 if tf == "4h" else TF_SEC[tf]
        return completed(out, sec, now)                       # drop the candle that is still forming

    def forming(self, sym, now=None):
        """The 1-minute candle that is still forming: its high / low so far and the price now (close), with the price
        offset of the symbol. Read every LIVE_SEC seconds for the instant follow-up of the trades. When the candles do
        not show the forming minute, the price now of the market snapshot builds it (high / low of the prices read)."""
        now = time.time() if now is None else now
        cur = int(now) // 60 * 60
        epic = INSTRUMENTS[sym]["capital"]
        if not hasattr(self, "live_mode"):
            self.live_mode, self.miss, self.own = {}, {}, {}
        b = None
        if self.live_mode.get(sym, "candle") == "candle" or now - self.live_mode.get(sym + "_t", 0) > 600:
            out = self._parse(self.get(f"/api/v1/prices/{epic}", {"resolution": "MINUTE", "max": 2}))
            if out and out[-1].t == cur:
                b, self.miss[sym], self.live_mode[sym] = out[-1], 0, "candle"
            elif now - cur > 5:                               # a few seconds into the minute and still not there
                self.miss[sym] = self.miss.get(sym, 0) + 1
                if self.miss[sym] >= 3:
                    self.live_mode[sym], self.live_mode[sym + "_t"] = "snap", now
                    log.info("%s: the candles do not show the forming minute: the market snapshot is read instead", sym)
        if b is None:
            snap = (self.get(f"/api/v1/markets/{epic}", {}) or {}).get("snapshot") or {}
            bid, ask = snap.get("bid"), snap.get("offer")
            if bid is None and ask is None:
                return None
            px = float(ask if (self.side == "ask" and ask is not None) or bid is None else bid)
            if self.side == "mid" and bid is not None and ask is not None:
                px = (float(bid) + float(ask)) / 2
            t0, o_, h_, l_ = self.own.get(sym, (None, px, px, px))
            if t0 != cur:
                o_, h_, l_ = px, px, px
            self.own[sym] = (cur, o_, max(h_, px), min(l_, px))
            b = Bar(cur, o_, max(h_, px), min(l_, px), px)
        off = OFFSETS.get(sym, 0.0) if use_offsets() else 0.0
        return Bar(b.t, b.o + off, b.h + off, b.l + off, b.c + off) if off else b

    def _parse(self, data):
        side = self.side
        def px(p):
            if not p:
                return None
            b, a = p.get("bid"), p.get("ask")
            if side == "mid" and b is not None and a is not None:
                return (float(b) + float(a)) / 2
            v = b if side == "bid" else a
            v = v if v is not None else (a if b is None else b)
            return None if v is None else float(v)
        out = []
        for c in data.get("prices", []):
            ts = c.get("snapshotTimeUTC") or c.get("snapshotTime")
            vals = [px(c.get(k)) for k in ("openPrice", "highPrice", "lowPrice", "closePrice")]
            if not ts or None in vals:
                continue
            t = int(datetime.fromisoformat(ts[:19] + "+00:00").timestamp())
            out.append(Bar(t, *vals))
        out.sort(key=lambda b: b.t)
        return out

CAPITAL = CapitalFeed()

def fetch_capital(sym, tf, now):
    return CAPITAL.candles(sym, tf, now)

# ── price alignment ──
# Yahoo gives FUTURES prices (YM=F, NQ=F, GC=F...). Brokers and TradingView "cash" charts trade a little
# below or above them (the futures basis, e.g. about 250 points on the Dow). Every price the bot uses is
# shifted by OFFSETS[sym] so entries, stops and targets match the chart. Indices calibrate themselves
# against the cash index (^DJI, ^NDX) during US hours; any symbol can be calibrated by hand from Telegram
# with /calibrate XAUUSD 4105.2 (the price your chart shows now), or with OFFSET_XAUUSD=-25 in the settings.
OFFSETS = {s: float(ENV("OFFSET_" + s, "0") or 0) for s in INSTRUMENTS}

def provider():
    """Capital.com when its key is set, else OANDA when its token is set (both real time), else Yahoo (delayed futures)."""
    p = (ENV("DATA_PROVIDER", "") or "").strip().lower()
    if p in ("capital", "oanda", "yahoo"):
        return p
    if (ENV("CAPITAL_API_KEY", "") or "").strip():
        return "capital"
    return "oanda" if (ENV("OANDA_TOKEN", "") or "").strip() else "yahoo"

def use_offsets():
    """Manual calibration (a few points to match your own broker) works on Yahoo and Capital.com."""
    return provider() != "oanda"

def get_candles(sym, tf, now, raw=False):
    bars = {"capital": fetch_capital, "oanda": fetch_oanda, "yahoo": fetch_yahoo}[provider()](sym, tf, now)
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
        self.seen, self.seen_hist, self.poll_id, self.dirty = {}, {}, 0, False   # live reads of the forming minute
        self.load()
        self.meta.setdefault("feed", provider())
        if tg is not None:
            tg.lang_of = lambda chat: self.subs.get(str(chat), {}).get("lang", "ar")

    # ── state
    def load(self):
        global QN, JN
        if os.path.exists(STATE_FILE):
            try:
                d = json.load(open(STATE_FILE, encoding="utf-8"))
                self.pairs, self.sent, QN = d.get("pairs", {}), d.get("sent", {}), d.get("q", 0)
                JN = d.get("j", 0)
                self.subs, self.ledger, self.meta = d.get("subs", {}), d.get("ledger", []), d.get("meta", {})
                if self.meta.get("feed", "yahoo") != provider():   # new data source: old offsets do not apply
                    log.info("data source changed %s -> %s: price offsets reset", self.meta.get("feed", "yahoo"), provider())
                    self.meta["offsets"] = {}
                self.meta["feed"] = provider()
                for sym, x in self.meta.get("offsets", {}).items():
                    if sym in OFFSETS and "v" in x:
                        OFFSETS[sym] = x["v"]
                for o in d.get("orders", []):
                    o.setdefault("inval", o.get("sl"))
                # orders planned on missed candles (late) stay too: one already open counts in the results like
                # the indicator's, even after a restart
                self.orders = [o for o in d.get("orders", []) if "tps" in o and
                               (o.get("msgs") or o.get("late") or o["state"] not in (PENDING, OPEN))]
            except Exception as e:
                log.warning("state not loaded: %s", e)

    def save(self):
        if getattr(self.bc, "dry", False):          # a dry run must never write state (fake message ids)
            return
        tmp = STATE_FILE + ".tmp"
        json.dump({"orders": self.orders[-400:], "pairs": self.pairs, "q": QN, "j": JN, "subs": self.subs, "ledger": self.ledger,
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
                    for k in ("lo", "hi", "trig", "entry", "sl", "inval", "lock_px"):
                        if k in o:
                            o[k] += delta
                    o["tps"] = [x + delta for x in o["tps"]]
        log.info("offset %s = %+.3f (%s)", sym, value, src)

    def auto_offsets(self, syms, now):
        """Indices: offset = cash index - futures, measured on the same closed minute during US hours (Yahoo only)."""
        if provider() != "yahoo":
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
            self.bc.edit(o, msg_v20_cancel(o, reason) if o.get("v20") else msg_expired(o, reason, not_triggered))

    def why(self, text):
        self.stats["unreal"] += 1
        self.stats["why"][text] = self.stats["why"].get(text, 0) + 1

    def book(self, o, bar, exit_px=None):
        dist, cost, td = realized(o, exit_px), cost_price(o["sym"]), trading_day(bar.t).isoformat()
        oc = outcome(o, dist, cost)
        self.ledger.append({"t": bar.t, "td": td, "sym": o["sym"], "tf": o["tf"], "dist": dist, "cost": cost, "oc": oc})
        ps = self.pair(o["sym"], o["tf"])                 # the pair's day so far (for the daily rule)
        if ps.get("dday") != td:
            ps.update(dday=td, dnet=0.0, dloss=0)
        ps["dnet"] += money(o["sym"], dist - cost, LOT_DEFAULT)
        ps["dloss"] += 1 if oc == -1 else 0
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

    def day_locked(self, sym, tf, t):
        return self.pair(sym, tf).get("lock_day") == trading_day(t).isoformat()

    def _day_check(self, sym, tf, t):
        """Daily rules, checked after each candle (minute): the daily target / loss limit of a small account (closed
        $ today), and the old rule (stop once the day is in profit, or after N losses). When one is reached the pair's
        waiting orders are removed and no new ones come until the next day."""
        pp = plan_params(sym, tf)
        green, max_l = pp.get("day_green", DAY_GREEN), pp.get("day_losses", DAY_LOSSES)
        if DAY_RULE == "off":
            green, max_l = False, 0
        elif DAY_RULE == "on":
            green = True
        tgt, mloss = user_or_tested("DAY_TARGET_USD", pp, "day_target"), user_or_tested("DAY_MAX_LOSS_USD", pp, "day_max_loss")
        ps, td = self.pair(sym, tf), trading_day(t).isoformat()
        if (not green and not max_l and not tgt and not mloss) or ps.get("dday") != td or ps.get("lock_day") == td:
            return
        lot = lot_for(sym, LOT_DEFAULT)
        why = (f"daily target reached (+${ps['dnet']:,.2f} at lot {lot:g}): no more orders on this pair today"
               if tgt and ps["dnet"] >= tgt else
               f"daily loss limit reached (-${-ps['dnet']:,.2f} at lot {lot:g}): no more orders on this pair today"
               if mloss and ps["dnet"] <= -mloss else
               "the day is in profit: no more orders on this pair today" if green and ps["dnet"] > 1e-9 else
               f"{ps['dloss']} losses today: no more orders on this pair today" if max_l and ps["dloss"] >= max_l else None)
        if why:
            ps["lock_day"] = td
            for q in self.orders:
                if q["sym"] == sym and q["tf"] == tf and q["state"] == PENDING:
                    self.expire(q, why)
            if (tgt or mloss) and abs(time.time() - t) < 900 and self.bc.targets(sym, tf):     # live only
                self.bc.send_new(sym, tf, msg_day_done(sym, tf, ps["dnet"], tgt and ps["dnet"] >= tgt, lot))

    def _manage_v19(self, sym, tf, mine, sb, ps):
        """One candle (a minute, or the whole chart candle) for the waiting and open orders `mine` of a pair: first
        the entries (and a breakout's target in the minute it was filled), then the open trades, then the daily rule."""
        for o in mine:
            d = o["dir"]
            if o["state"] == PENDING:
                filled = (sb.h >= o["lo"] if o["is_stop"] else sb.l <= o["hi"]) if d == 1 else \
                         (sb.l <= o["hi"] if o["is_stop"] else sb.h >= o["lo"])
                if filled:
                    o.update(state=OPEN, fill_t=sb.t, fav=0.0, adv=0.0, hits=0, be=False)
                    for q in mine:
                        if q is not o and q["plan"] == o["plan"] and q["state"] == PENDING:
                            self.expire(q, "another order of this plan was filled")
                    self.say(o, msg_filled(o))
                    # a breakout order must have crossed its entry to reach the target, so count a same-bar target
                    # (unless the stop was touched in that bar too: the order of events is unknown, so stay careful)
                    sl_touch = (d == 1 and sb.l <= o["sl"]) or (d == -1 and sb.h >= o["sl"])
                    if o["is_stop"] and not sl_touch:
                        self._hits(o, sb, d)
        for o in mine:
            d = o["dir"]
            if o["state"] == OPEN and sb.t > o.get("fill_t", 0):
                trig = o["trig"]
                fav = (sb.h - trig) if d == 1 else (trig - sb.l)
                adv = (trig - sb.l) if d == 1 else (sb.h - trig)
                stop = o["lock_px"] if o.get("locked") else trig if o["be"] else o["sl"]
                if (d == 1 and sb.l <= stop) or (d == -1 and sb.h >= stop):
                    o["state"] = LOCK_HIT if o.get("locked") else BE_HIT if o["be"] else SL_HIT
                    if o["state"] == SL_HIT:
                        ps.setdefault("cool", {})[str(d)] = sb.t + COOLDOWN_MIN * 60
                    self.book(o, sb)
                    self.say(o, msg_locked(o) if o["state"] == LOCK_HIT else msg_be(o) if o["be"] else msg_sl(o))
                else:
                    o["fav"], o["adv"] = max(o["fav"], fav), max(o["adv"], adv)
                    self._hits(o, sb, d)
                    if o["state"] == OPEN:
                        # protection: the stop only moves forward, and only to where it can really be put at this close
                        tg = abs(o["tps"][0] - trig)
                        floor = cost_price(sym) if BE_PLUS_COST else 0.0   # spread + commission: a protected exit is no loss
                        if floor > 0 and o["fav"] < 2 * floor:
                            floor = 0.0                               # price not far enough yet: plain entry first
                        # a buy's stop must be under the bid (the close); a sell's stop over the ask (close + spread)
                        room = ((sb.c - trig) * d - (INSTRUMENTS[sym].get("spread", 0.0) if d == -1 else 0.0)
                                if REAL_STOP else float("inf"))
                        want_be, want_d = False, None
                        pp = plan_params(sym, o["tf"])
                        if pp.get("protect", PROTECT) == "usd":
                            be_d = usd_px(sym, pp.get("be_usd", BE_USD))
                            at_d, lk_d = usd_px(sym, pp.get("lock_at_usd", LOCK_AT_USD)), usd_px(sym, pp.get("lock_usd", LOCK_USD))
                            want_be = be_d > 0 and o["fav"] >= be_d                 # step 1: +$2 -> entry (+ costs)
                            if at_d > 0 and lk_d > 0 and o["fav"] >= at_d:
                                want_d = lk_d                                      # step 2: +$5 -> lock $5
                        else:
                            be_r = pp.get("be_at_r", BE_AT_R)
                            want_be = be_r > 0 and o["fav"] >= be_r * tg
                            for at, to in ((pp.get("lock1_at", LOCK1_AT), pp.get("lock1_to", LOCK1_TO)),
                                           (pp.get("lock2_at", LOCK2_AT), pp.get("lock2_to", LOCK2_TO))):
                                if at > 0 and to > 0 and o["fav"] >= at * tg:
                                    want_d = to * tg                               # steps 2 and 3 of the way to the target
                        goal = None                                   # how far into profit the stop should be (0 = entry)
                        if want_be or o["be"]:
                            goal = floor                              # entry, or entry + costs once price is far enough
                        if want_d is not None:
                            goal = max(goal or 0.0, want_d, floor)    # a locked stop is never below the costs
                        if goal is not None:
                            now_d = min(goal, room)                   # never beyond the price (less now, more later)
                            cur = o.get("lock_d", 0.0) if o.get("locked") else (0.0 if o["be"] else None)
                            if now_d >= 0 and (cur is None or now_d > cur + 1e-12):
                                if now_d > 1e-12:
                                    o.update(be=True, locked=True, lock_d=now_d, lock_px=trig + d * now_d)
                                    self.say(o, msg_lock(o, pct(o["fav"], tg)) if now_d > floor + 1e-12
                                             else msg_protect(o, pct(o["fav"], tg)))
                                else:
                                    o["be"] = True                    # stop to entry
                                    self.say(o, msg_protect(o, pct(o["fav"], tg)))
        self._day_check(sym, tf, sb.t)

    def manage_minutes(self, sym, m1bars, until=None):
        """Follow the waiting and open orders of `sym` on the 1-minute candles as they close. Each order starts at the
        first minute after the candle it was planned in and sees each minute once (the backtest does the same inside
        each chart candle). A minute the live reads already followed counts only for what they did not see (a new high
        or low after the last read). until = only minutes that closed by then (the chart candle about to be planned)."""
        act = [o for o in self.orders if o["sym"] == sym and o["state"] in (PENDING, OPEN)]
        if not act:
            return
        first = min(o.get("m1_next", self.pair(sym, o["tf"])["last_t"] + TF_SEC[o["tf"]]) for o in act)
        for b in m1bars[bisect.bisect_left([x.t for x in m1bars], first):]:
            if until is not None and b.t + 60 > until:
                break
            for tf in sorted({o["tf"] for o in self.orders if o["sym"] == sym and o["state"] in (PENDING, OPEN)}):
                ps = self.pair(sym, tf)
                mine = [o for o in self.orders if o["sym"] == sym and o["tf"] == tf and o["state"] in (PENDING, OPEN)
                        and o.get("m1_next", ps["last_t"] + TF_SEC[tf]) <= b.t]
                if mine:
                    sh = self.seen_hist.get(f"{sym}|{tf}", {}).get(b.t)
                    sb = b if not sh else Bar(b.t, b.o, b.h if b.h > sh[0] else -1e18, b.l if b.l < sh[1] else 1e18, b.c)
                    self._manage(sym, tf, mine, sb, ps)
                    for o in mine:
                        o["m1_next"] = b.t + 60

    def live_check(self, sym, bar, now):
        """The 1-minute candle still forming (bar: its high / low so far, close = the price now), read every LIVE_SEC:
        the fills, targets and stops of `sym` are sent the moment they happen. Per chart only the NEW high / low since
        its last read count, so nothing is sent twice. A chart whose candle just closed waits until that candle is
        planned, and an order waits until the minutes before this one were followed (same order as the backtest)."""
        self.poll_id += 1
        for tf in sorted({o["tf"] for o in self.orders if o["sym"] == sym and o["state"] in (PENDING, OPEN)}):
            ps = self.pair(sym, tf)
            if not ps["last_t"] or now >= ps["last_t"] + 2 * TF_SEC[tf]:
                continue
            key = f"{sym}|{tf}"
            hist = self.seen_hist.setdefault(key, {})
            mine = [o for o in self.orders if o["sym"] == sym and o["tf"] == tf and o["state"] in (PENDING, OPEN)
                    and (o.get("m1_next", 0) == bar.t or (o.get("m1_next", 0) == bar.t - 60 and (bar.t - 60) in hist))]
            if not mine:
                continue
            seen = self.seen.get(key)
            if seen and seen[0] > bar.t:
                continue
            if seen and seen[0] == bar.t:
                up = bar.h if bar.h > seen[1] else None
                dn = bar.l if bar.l < seen[2] else None
                h, l = max(bar.h, seen[1]), min(bar.l, seen[2])
            else:
                up, dn, h, l = bar.h, bar.l, bar.h, bar.l
            self.seen[key] = (bar.t, h, l)
            hist[bar.t] = (h, l)
            for t_ in [t_ for t_ in hist if t_ < bar.t - 900]:
                del hist[t_]
            if up is None and dn is None:
                continue
            sb = Bar(bar.t, bar.o, up if up is not None else -1e18, dn if dn is not None else 1e18, bar.c)
            self._manage(sym, tf, mine, sb, ps, live=True, now=now)

    # ── buy / sell zones of the market session
    @staticmethod
    def _zone_break(z, c):
        if not z["broken"] and ((z["d"] == 1 and c < z["lo"]) or (z["d"] == -1 and c > z["hi"])):
            z["broken"] = True

    @staticmethod
    def _zone_use(zs, z):
        for y in zs:                                         # this zone and every zone the same way that overlaps it
            if y["d"] == z["d"] and y["lo"] <= z["hi"] and y["hi"] >= z["lo"]:
                y["used"] = True

    def _zones_update(self, sym, tf, bars, ps, use):
        """At each market open (Tokyo, London, New York) the zones of the last day that are still not broken are taken,
        from the candle the market opened in (also after a restart); every later close beyond a zone breaks it."""
        bar, sec = bars[-1], TF_SEC[tf]
        lo = last_open(bar.t + sec)
        if lo is None:
            return
        T, name = lo
        if ps.get("zs_T") == T:
            for z in ps.get("zs") or []:
                self._zone_break(z, bar.c)
            return
        zs, idx = [], None
        for i in range(len(bars) - 1, -1, -1):              # the candle the market opened in
            if bars[i].t < T <= bars[i].t + sec:
                idx = i
                break
            if bars[i].t + sec < T:
                break
        if idx is not None:
            sub = bars if idx == len(bars) - 1 else bars[:idx + 1]
            zs = find_zones(sub, calc_atr(sub), use)
            for z in zs:
                z.update(used=False, broken=False)
            for b in bars[idx + 1:]:
                for z in zs:
                    self._zone_break(z, b.c)
        live = {(z["d"], z["src"], z["t"]) for z in zs if not z["broken"]}
        for o in self.orders:                                # waiting zone orders: kept while their zone is still there
            if o["sym"] == sym and o["tf"] == tf and o["state"] == PENDING and o.get("src"):
                k = (o["dir"], o["src"], o.get("zt"))
                if k in live:
                    for z in zs:
                        if (z["d"], z["src"], z["t"]) == k:
                            self._zone_use(zs, z)
                else:
                    self.expire(o, f"new market open ({name.title()}): its zone is no longer there")
        ps.update(zs_T=T, zs_name=name, zs=zs)

    def _plan_zones(self, sym, tf, bars, atr, pp, bias_info, ema_dir, mom_dir, ps, is_latest, replay, day):
        """Zone orders of this market session: a BUY LIMIT at the top of the nearest buy zone under the price and a SELL
        LIMIT at the bottom of the nearest sell zone above it, one waiting each way; each zone is used once."""
        bar, zs = bars[-1], ps["zs"]
        live = [o for o in self.orders if o["sym"] == sym and o["tf"] == tf and o["state"] in (PENDING, OPEN)]
        pend = [o for o in live if o["state"] == PENDING]
        open_now = [o for o in live if o["state"] == OPEN]
        open_dirs = {o["dir"] for o in open_now}
        safe_dirs = {dd for dd in open_dirs if pp["stack"] > 0 and sum(1 for o in open_now if o["dir"] == dd) < pp["stack"]
                     and all(o["be"] for o in open_now if o["dir"] == dd)}
        bias = bias_info["now"]
        sp = max(atr * SPREAD_PCT / 100.0, INSTRUMENTS[sym]["tick"])
        slD = atr * (float(pp.get("zsl", ZONE_SL)) + SWEEP_BUFFER)
        for d in (1, -1):
            if any(o["dir"] == d and o.get("src") for o in pend):
                continue                                     # one zone order waiting each way
            if -d in open_dirs or (d in open_dirs and d not in safe_dirs):
                continue                                     # never both directions; the same way only when stacking allows
            if not zone_allowed(d, bias, ema_dir, mom_dir, int(pp.get("ztrend", ZONE_TREND))):
                continue
            if ps.get("cool", {}).get(str(d), 0) > bar.t:
                continue
            cands = [z for z in zs if z["d"] == d and not z["broken"] and not z["used"]
                     and (z["hi"] < bar.c if d == 1 else z["lo"] > bar.c)]
            if not cands:
                continue
            z = min(cands, key=lambda y: (abs((y["hi"] if d == 1 else y["lo"]) - bar.c), -y["t"]))
            n = zone_order(d, z, sp, slD, pp["zrr"], bias)
            if abs(n["trig"] - bar.c) > MAX_DIST_ATR * atr:
                continue                                     # still far away: it may be taken later
            if any(q["dir"] == -d and abs(q["trig"] - n["trig"]) <= CONFLICT_ATR * atr for q in pend):
                continue                                     # an order waits the other way in this area
            self.stats["built"] += 1
            why = "target smaller than the stop" if n["rrs"][0] < MIN_RR else unrealistic(n, atr, bias_info.get("datr"), 0, tf)
            cmax = pp.get("cost_max", COST_MAX)
            if not why and cmax > 0 and cost_price(sym) > cmax * n["risk"]:
                why = "quiet market: spread + commission too big a share of the stop"
            rmax = user_or_tested("MAX_RISK_USD", pp, "max_risk")
            if not why and rmax > 0 and money(sym, n["risk"], LOT_DEFAULT) > rmax:
                why = "stop too big for the account"
            self._zone_use(zs, z)
            if why:
                self.why(why)
                continue
            if (MAX_PER_PAIR_DAY and ps.get("sent", 0) >= MAX_PER_PAIR_DAY) or \
                    (MAX_SIGNALS_PER_DAY and self.sent.get(day, 0) >= MAX_SIGNALS_PER_DAY):
                self.stats["capped"] += 1
                continue
            ps["seq"] += 1
            n.update(sym=sym, tf=tf, plan=f"{sym}{tf}{ps['seq']}", state=PENDING, born_t=bar.t, fill_t=0, fav=0.0, adv=0.0,
                     hits=0, be=False, m1_next=bar.t + TF_SEC[tf], src=z["src"], sess=ps.get("zs_name", ""), zt=z["t"],
                     zlo=z["lo"], zhi=z["hi"])
            if is_latest and not replay:
                msgs = self.bc.send_new(sym, tf, msg_signal(n, bias_info, bar.c))
                if not msgs:                                 # Telegram refused: try this zone again on the next bar
                    z["used"] = False
                    continue
                n["msgs"] = msgs
                ps["sent"] = ps.get("sent", 0) + 1
                self.sent[day] = self.sent.get(day, 0) + 1
            else:
                n["late"] = True
            self.orders.append(n)
            pend.append(n)

    # ── one completed bar
    def process_bar_v19(self, sym, tf, bars, bias_info, is_latest, replay=False, subbars=None):
        """is_latest = the newest closed candle: new orders are planned and sent. replay = a candle missed between two
        runs, caught up now: it is planned the same way (like the indicator, which plans on every candle), but its new
        orders are only kept; the ones still waiting are sent at the newest candle."""
        bar, ps = bars[-1], self.pair(sym, tf)
        plan_ok = is_latest or (replay and REPLAY_MISSED and len(bars) > 60)
        by_tf = bias_info.get("by_tf", {})
        bias_info = dict(bias_info, now=by_tf.get(tf, bias_info["now"]), txt=bias_info.get("txt_by_tf", {}).get(tf, bias_info["txt"]))
        al = int(plan_params(sym, tf).get("align", 0) or 0)
        if al in ALIGN_KEYS and bias_info.get("bs"):          # stricter trend: the higher timeframes must all agree
            bias_info = dict(bias_info, now=aligned_trend(bias_info["bs"], tf, al))
        mins, day = ny_parts(bar.t)
        tick = INSTRUMENTS[sym]["tick"]
        mine = [o for o in self.orders if o["sym"] == sym and o["tf"] == tf and o["state"] in (PENDING, OPEN)]

        if ps["day"] != day:                                         # new New-York day
            ps.update(day=day, last_slot=-1, sent=0)

        # 1) manage orders (wicks count: a touch of the target or the stop is enough). With the minute candles of
        #    this candle (subbars), orders are followed minute by minute: fills, targets and stops in the order
        #    they happened, and a stop is moved at the close of the minute the price reached the step in - the
        #    way it is done by hand from the live profit in MT5 (without them: at the close of this candle)
        for sb in (subbars if subbars is not None else [bar]):
            self._manage(sym, tf, mine, sb, ps)

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
                    self.say(o, msg_dayend(o, r, pts(sym, bar.c - o["trig"])))
        self._day_check(sym, tf, bar.t)

        # 2b) buy / sell zones: taken at each market open (Tokyo, London, New York), broken by a close beyond them
        atr = calc_atr(bars)
        pp = plan_params(sym, tf)
        if pp["on"] and pp.get("zones"):
            self._zones_update(sym, tf, bars, ps, int(pp["zones"]))

        # 3) re-check ONLY the unfilled orders. A pending order stays while its zone is still valid,
        #    so when the market comes back to test the same zone the order is still there.
        in_win = pp["on"] and pp["start"] <= mins < pp["end"]          # trading hours of this instrument + timeframe
        eff = max(REFRESH_MIN, TF_SEC[tf] / 60.0)
        slot = int((mins - pp["start"]) // eff) if in_win else -1
        spike = bool(atr) and (bar.h - bar.l) > SPIKE_ATR * atr
        if spike and plan_ok and in_win:
            self.stats["spike"] += 1                                # news-size candle: wait for the next bar
        elif plan_ok and in_win and atr and len(bars) > pp["range"] and not self.day_locked(sym, tf, bar.t):
            prune_now = slot != ps["last_slot"]
            if prune_now:
                ps["last_slot"] = slot
            live = [o for o in self.orders if o["sym"] == sym and o["tf"] == tf and o["state"] in (PENDING, OPEN)]
            ema_dir, mom_dir = local_dirs(bars, atr)
            keep_z = bool(pp.get("zkeep"))                          # zone orders wait for their zone (tested setting)
            for p in [o for o in live if o["state"] == PENDING]:    # every bar: the chart now runs hard against it
                if ema_dir == -p["dir"] and mom_dir == -p["dir"] and not (keep_z and p.get("src")):
                    self.expire(p, "the market turned against it (falling for a buy, rising for a sell)")
            if prune_now:                                           # re-check unfilled orders only
                for p in [o for o in live if o["state"] == PENDING]:
                    d = p["dir"]
                    if (d == 1 and bar.c < p["inval"]) or (d == -1 and bar.c > p["inval"]):
                        self.expire(p, "price closed beyond its invalidation level")
                    elif bias_info["now"] == -d and not (keep_z and p.get("src")):
                        self.expire(p, "the trend turned against it")
                    elif abs(p["trig"] - bar.c) > STICKY_MAX_ATR * atr:
                        self.expire(p, "price moved far away")
            pend = [o for o in live if o["state"] == PENDING]
            have = {p["kind"] for p in pend if not p.get("src")}
            zpend = [p for p in pend if p.get("src")]
            open_now = [o for o in live if o["state"] == OPEN]
            open_dirs = {o["dir"] for o in open_now}
            # stacking (tested per instrument and timeframe): one more trade the SAME way when every open trade
            # that way is already protected (its stop at entry or better), up to "stack" trades
            safe_dirs = {dd for dd in open_dirs if pp["stack"] > 0 and sum(1 for o in open_now if o["dir"] == dd) < pp["stack"]
                         and all(o["be"] for o in open_now if o["dir"] == dd)}
            win = bars[-pp["range"]:]
            hi, lo = max(b.h for b in win), min(b.l for b in win)
            if pp.get("rng", True) and hi - lo >= atr and self.bc.targets(sym, tf):     # rng off = zone orders only
                fake_up, fake_dn = sweep_flags(bars, pp["range"])
                built = build_orders(atr, hi, lo, bar.c, bias_info["now"], tick, pp["rr"], ema_dir, mom_dir, fake_up, fake_dn,
                                     sl_mult=pp["sl"], limits=pp["limits"], mixed=pp["mixed"])
                lean = mom_dir or ema_dir or bias_info["now"]
                keep = []
                for n in built:                                     # a buy and a sell in the SAME area: keep only one
                    rival = [m for m in built if m["dir"] == -n["dir"] and abs(m["trig"] - n["trig"]) <= CONFLICT_ATR * atr]
                    if rival and not (n["dir"] == lean or (lean == 0 and not n["is_stop"])):
                        continue
                    keep.append(n)
                built = keep
                self.stats["built"] += len(built)
                add = []
                for n in built:
                    if n["kind"] in have or -n["dir"] in open_dirs or (n["dir"] in open_dirs and n["dir"] not in safe_dirs):
                        continue                                    # already waiting, or a trade is open (never both directions)
                    if any(q["dir"] == -n["dir"] and abs(q["trig"] - n["trig"]) <= CONFLICT_ATR * atr for q in zpend):
                        continue                                    # a zone order waits the other way in this area
                    if n["rrs"][0] < MIN_RR:
                        self.stats["rr_skip"] += 1
                    elif ps.get("cool", {}).get(str(n["dir"]), 0) > bar.t:
                        self.stats["cool"] += 1
                    elif abs(n["trig"] - bar.c) > MAX_DIST_ATR * atr:
                        self.stats["dist_skip"] += 1
                    else:
                        why = unrealistic(n, atr, bias_info.get("datr"), mins, tf)
                        cmax = pp.get("cost_max", COST_MAX)
                        if not why and cmax > 0 and cost_price(sym) > cmax * n["risk"]:
                            why = "quiet market: spread + commission too big a share of the stop"
                        rmax = user_or_tested("MAX_RISK_USD", pp, "max_risk")
                        if not why and rmax > 0 and money(sym, n["risk"], LOT_DEFAULT) > rmax:
                            why = "stop too big for the account"
                        if why:
                            self.why(why)
                        else:
                            add.append(n)
                if add:
                    ps["seq"] += 1
                    for n in add:
                        if (MAX_PER_PAIR_DAY and ps.get("sent", 0) >= MAX_PER_PAIR_DAY) or \
                                (MAX_SIGNALS_PER_DAY and self.sent.get(day, 0) >= MAX_SIGNALS_PER_DAY):
                            self.stats["capped"] += 1
                            continue
                        n.update(sym=sym, tf=tf, plan=f"{sym}{tf}{ps['seq']}", state=PENDING, born_t=bar.t, fill_t=0,
                                 fav=0.0, adv=0.0, hits=0, be=False, m1_next=bar.t + TF_SEC[tf])
                        if is_latest and not replay:
                            msgs = self.bc.send_new(sym, tf, msg_signal(n, bias_info, bar.c))
                            if not msgs:                              # Telegram refused: forget it and retry on the next bar
                                continue
                            n["msgs"] = msgs
                            ps["sent"] = ps.get("sent", 0) + 1
                            self.sent[day] = self.sent.get(day, 0) + 1
                        else:
                            n["late"] = True                          # a missed candle: sent later, if still waiting
                        for q in self.orders:                       # the new order replaces an opposite one waiting in the same area
                            if (q["sym"] == sym and q["tf"] == tf and q["state"] == PENDING and q["dir"] == -n["dir"]
                                    and not q.get("src") and abs(q["trig"] - n["trig"]) <= CONFLICT_ATR * atr):
                                self.expire(q, f"replaced by a {n['kind']}: the market changed direction")
                        self.orders.append(n)
            if pp.get("zones") and ps.get("zs") and self.bc.targets(sym, tf):
                self._plan_zones(sym, tf, bars, atr, pp, bias_info, ema_dir, mom_dir, ps, is_latest, replay, day)

        # 4) orders planned on missed candles: the ones still waiting for their entry are sent now (the others were
        #    filled, closed or removed while the bot was catching up; they count in the results like the indicator's)
        if is_latest and not replay:
            for o in self.orders:
                if o["sym"] == sym and o["tf"] == tf and o["state"] == PENDING and o.get("late") and not o.get("msgs"):
                    msgs = self.bc.send_new(sym, tf, msg_signal(o, bias_info, bar.c, late=True))
                    if msgs:
                        o["msgs"] = msgs
                        ps["sent"] = ps.get("sent", 0) + 1
                        self.sent[day] = self.sent.get(day, 0) + 1

        ps["last_t"] = bar.t
        self.orders = [o for o in self.orders if o["state"] in (PENDING, OPEN) or o["born_t"] > bar.t - 3 * 86400]

    # ── v28: Fibonacci orders (the same rules as the indicator v20, the EA v4 and the backtest)
    def _v20_open(self, sym, tf, d):
        return [o for o in self.orders if o["sym"] == sym and o["tf"] == tf and o["state"] == OPEN and o["dir"] == d]

    def _v20_book(self, o, t, px, state, at=None):
        """A finished trade: its state, its exit, the ledger (W / L / BE after the costs, like the indicator).
        t = the minute it happened in, at = the moment the bot saw it (the live reads) or the close of that minute."""
        o["state"], o["exit_px"], o["exit_t"] = state, px, t
        o["exit_at"] = at if at is not None else t + 60
        dist = (px - o["trig"]) * o["dir"]
        cost = cost_price(o["sym"])
        oc = -1 if state == SL_HIT else 1 if dist - cost > INSTRUMENTS[o["sym"]]["tick"] else 2
        self.ledger.append({"t": t, "td": trading_day(t).isoformat(), "sym": o["sym"], "tf": o["tf"], "dist": dist,
                            "cost": cost, "oc": oc,
                            "dur": max(0, int(o["exit_at"] - o.get("fill_at", o.get("fill_t", t))))})
        cutoff = t - 100 * 86400
        self.ledger = [e for e in self.ledger if e["t"] > cutoff]
        self.dirty = True

    def _manage(self, sym, tf, mine, sb, ps, live=False, now=None):
        """One minute (or the whole chart candle) for the waiting and open orders `mine` of a chart: first the fills
        (a STOP order fills when the price touches it; a stop touched in the same minute counts first), then the open
        trades: the stop first, then the targets (TP1 -> the stop goes to the entry + costs, TP2 -> to TP1, the last
        target closes). On a finished minute the stop is moved at its close, only where it can really be put.
        live = the minute that is still forming, read every LIVE_SEC: sb holds only the NEW high / low since the last
        read (the other side is out of reach), so every event is sent the moment it happens and the stop is moved at
        once (the price is already beyond it)."""
        at = now if live else None
        for o in mine:
            if o["state"] != PENDING:
                continue
            d = o["dir"]
            if (d == 1 and sb.h >= o["trig"]) or (d == -1 and sb.l <= o["trig"]):
                ps.setdefault("used", {})[str(d)] = o.get("swing_t")      # one trade per swing
                if self._v20_open(sym, tf, -d):
                    self.expire(o, "a trade the other way is open (never a buy and a sell together)")
                    continue
                o.update(state=OPEN, fill_t=sb.t, fill_at=at if live else sb.t, fill_poll=self.poll_id if live else -1,
                         hits=0, stop=o["sl"], mv=None)
                self.dirty = True
                self.say(o, msg_v20_filled(o))
                for q in self.orders:                 # the other side's waiting order goes (never both ways)
                    if q is not o and q["sym"] == sym and q["tf"] == tf and q["state"] == PENDING and q["dir"] == -d:
                        self.expire(q, "the other order was filled (never a buy and a sell together)")
                if (d == 1 and sb.l <= o["sl"]) or (d == -1 and sb.h >= o["sl"]):
                    self._v20_book(o, sb.t, o["sl"], SL_HIT, at=at)
                    self.say(o, msg_v20_exit(o))
        for o in mine:
            if o["state"] != OPEN:
                continue
            if live:
                if o.get("fill_poll") == self.poll_id:          # filled on this very read: its stop was checked above
                    continue
            elif sb.t < o.get("fill_t", 0) or (sb.t == o.get("fill_t", 0) and o.get("fill_poll", -1) < 0):
                continue                                        # filled in this finished minute: from the next one
                                                                # (filled by a live read: what came after the read counts)
            d = o["dir"]
            if (d == 1 and sb.l <= o["stop"]) or (d == -1 and sb.h >= o["stop"]):
                locked = (o["stop"] - o["trig"]) * d > 1.5 * cost_price(sym)
                st = SL_HIT if o.get("hits", 0) == 0 else LOCK_HIT if locked else BE_HIT
                self._v20_book(o, sb.t, o["stop"], st, at=at)
                self.say(o, msg_v20_exit(o))
                continue
            n = len(o["tps"])
            while o["state"] == OPEN and o["hits"] < n and (
                    (d == 1 and sb.h >= o["tps"][o["hits"]]) or (d == -1 and sb.l <= o["tps"][o["hits"]])):
                k = o["hits"]
                o["hits"] += 1
                o["hit_at"] = at if live else sb.t + 60
                self.dirty = True
                if k == n - 1:
                    self._v20_book(o, sb.t, o["tps"][k], TP_HIT, at=at)
                    self.say(o, msg_v20_exit(o))
                    break
                o["mv"] = o["trig"] + d * cost_price(sym) if k == 0 else o["tps"][k - 1]
                self.say(o, msg_v20_tp(o, k))
            if o["state"] == OPEN and o.get("mv") is not None:
                mv = o["mv"]
                can = (sb.c > mv) if d == 1 else (sb.c + INSTRUMENTS[sym].get("spread", 0.0) < mv)
                if can or not REAL_STOP:
                    if (d == 1 and mv > o["stop"]) or (d == -1 and mv < o["stop"]):
                        o["stop"] = mv
                    o["mv"] = None
                    self.dirty = True

    def process_bar(self, sym, tf, bars, bias_info, is_latest, replay=False, subbars=None):
        """At a chart candle close: its minutes (fills, stops, targets), then the BUY STOP / SELL STOP of the chart made
        again from its structure. A waiting order of the same swing is kept (its message is updated when its stop or
        targets moved); an order that is no longer valid is cancelled with the reason."""
        bar, ps = bars[-1], self.pair(sym, tf)
        sec = TF_SEC[tf]
        tc = bar.t + sec
        mins, day = ny_parts(tc)
        mine = [o for o in self.orders if o["sym"] == sym and o["tf"] == tf and o["state"] in (PENDING, OPEN)]
        if ps["day"] != day:
            ps.update(day=day, last_slot=-1, sent=0)
        for sb in (subbars if subbars is not None else [bar]):
            self._manage(sym, tf, mine, sb, ps)
        pp = v20_params(sym, tf)
        plan_ok = is_latest or (replay and REPLAY_MISSED and len(bars) > 60)
        if not pp:
            for o in self.orders:
                if o["sym"] == sym and o["tf"] == tf and o["state"] == PENDING:
                    self.expire(o, "this chart has no tested setting")
            ps["last_t"] = bar.t
            return
        if plan_ok:
            atr = calc_atr(bars)
            htf = bias_info.get("htf") or {}
            bias = v20_bias(htf, tc, pp.get("bias", "tf"), tf) if htf else bias_info.get("now", 0)
            for d in (1, -1):
                cur = [o for o in self.orders if o["sym"] == sym and o["tf"] == tf and o["state"] == PENDING and o["dir"] == d]
                plan, why = v20_plan(bars, d, pp, atr, bias, mins, ps.get("used", {}).get(str(d)),
                                     len(self._v20_open(sym, tf, d)), len(self._v20_open(sym, tf, -d)))
                keep = None
                for o in cur:
                    if plan and o.get("swing_t") == plan["swing_t"] and keep is None:
                        keep = o
                    else:
                        self.expire(o, why or "a newer swing replaced it")
                if not plan:
                    continue
                if keep is not None:
                    moved = any(abs(a - b) > INSTRUMENTS[sym]["tick"] / 2
                                for a, b in zip([keep["sl"]] + keep["tps"], [plan["S"]] + plan["tps"]))
                    if moved:
                        keep.update(sl=plan["S"], inval=plan["S"], stop=plan["S"], tps=plan["tps"], risk=plan["risk"],
                                    rrs=[abs(t - keep["trig"]) / max(plan["risk"], 1e-12) for t in plan["tps"]],
                                    upd_t=bar.t, base_t=plan["base_t"])
                        if keep.get("msgs") and is_latest and not replay:
                            self.bc.edit(keep, msg_v20_new(keep, bias, bar.c, updated=True))
                    continue
                if not self.bc.targets(sym, tf):
                    continue
                ps["seq"] += 1
                o = dict(v20=True, sym=sym, tf=tf, dir=d, kind="BUY STOP" if d == 1 else "SELL STOP", is_stop=True,
                         trig=plan["E"], entry=plan["E"], lo=plan["E"], hi=plan["E"], sl=plan["S"], inval=plan["S"],
                         stop=plan["S"], tps=plan["tps"], risk=plan["risk"],
                         rrs=[abs(t - plan["E"]) / max(plan["risk"], 1e-12) for t in plan["tps"]],
                         swing_t=plan["swing_t"], base_t=plan["base_t"], fib=plan["fib"], plan=f"{sym}{tf}{ps['seq']}",
                         state=PENDING, born_t=bar.t, fill_t=0, hits=0, mv=None, m1_next=bar.t + sec, sp=0.0,
                         with_trend=(bias == d), fav=0.0, adv=0.0, be=False)
                if is_latest and not replay:
                    msgs = self.bc.send_new(sym, tf, msg_v20_new(o, bias, bar.c))
                    if not msgs:
                        continue                                 # Telegram refused: tried again at the next candle
                    o["msgs"] = msgs
                    ps["sent"] = ps.get("sent", 0) + 1
                    self.sent[day] = self.sent.get(day, 0) + 1
                else:
                    o["late"] = True
                self.orders.append(o)
            if is_latest and not replay:                          # orders of missed candles still waiting: sent now
                for o in self.orders:
                    if o["sym"] == sym and o["tf"] == tf and o["state"] == PENDING and o.get("late") and not o.get("msgs"):
                        msgs = self.bc.send_new(sym, tf, msg_v20_new(o, bias, bar.c, late=True))
                        if msgs:
                            o["msgs"] = msgs
        ps["last_t"] = bar.t
        self.orders = [o for o in self.orders if o["state"] in (PENDING, OPEN) or o["born_t"] > bar.t - 3 * 86400]

    # ── subscribers: every user chooses what he receives
    def sub_of(self, chat, name=""):
        return self.subs.setdefault(str(chat), {"syms": [], "tfs": [], "lot": LOT_DEFAULT, "name": name})

    def send_report(self, chat, sub, title="REPORT"):
        self.tg.send(msg_report(sub, stats_text(sub, self.ledger, time.time()), title), chat=chat)

    def is_owner(self, cid):
        owner = str(ENV("ADMIN_ID", "") or self.meta.get("owner") or next(iter(self.subs), ""))
        return str(cid) == owner

    def do_calibrate(self, cid, sym, chart):
        """Shift every price of `sym` so the feed matches the price the owner sees on his chart now."""
        try:
            feed = get_candles(sym, "1m", int(time.time()), raw=True)[-1].c
        except Exception as e:
            self.tg.send(f"Could not read the feed price now ({type(e).__name__}). Try again in a minute.", chat=cid)
            return
        if not use_offsets():
            self.tg.send(f"ℹ️ The bot reads OANDA now, so <b>{sym}</b> needs no calibration (feed <code>{fmt(sym, feed)}</code>).", chat=cid)
            return
        self.set_offset(sym, round(chart - feed, 4), "manual")
        self.tg.send(f"✅ <b>{sym}</b> calibrated · تم الضبط\nFeed <code>{fmt(sym, feed)}</code> → your chart <code>{fmt(sym, chart)}</code>"
                     f" (offset {chart - feed:+.2f}).\nAll {sym} prices, waiting orders and open trades now match your chart.", chat=cid)

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
        waiting = sub.pop("await_cal", None)
        if waiting and self.is_owner(cid):
            try:
                self.do_calibrate(cid, waiting, float(m["text"].strip().replace(",", "")))
            except ValueError:
                self.tg.send("That is not a price. Tap 🎯 Calibrate again and send a number like <code>4105.2</code>.", chat=cid)
            return
        cmd, _, arg = m["text"].strip().partition(" ")
        cmd = cmd.split("@")[0].lower()
        if not self.meta.get("owner") and not ENV("ADMIN_ID", ""):
            self.meta["owner"] = next(iter(self.subs), str(cid))
        if cmd in ("/start", "/menu", "/settings"):
            if is_new or not sub.get("welcomed"):
                self.tg.send(msg_welcome(sub.get("name", "")), chat=cid)
                sub["welcomed"] = True
            self.tg.send(msg_menu(sub), chat=cid, markup=menu_markup(sub, self.is_owner(cid)))
        elif cmd == "/calibrate":
            if not self.is_owner(cid):
                self.tg.send("Only the bot owner can calibrate prices.", chat=cid)
                return
            parts = arg.replace(",", "").split()
            alias = {"GOLD": "XAUUSD", "SILVER": "XAGUSD", "DOW": "US30", "WALLSTREET": "US30", "DJ30": "US30",
                     "NASDAQ": "NAS100", "NAS": "NAS100", "USTEC": "NAS100", "NDX": "NAS100", "OIL": "USOIL", "WTI": "USOIL"}
            sym = alias.get(parts[0].upper(), parts[0].upper()) if parts else ""
            try:
                if sym not in INSTRUMENTS:
                    raise ValueError
                self.do_calibrate(cid, sym, float(parts[1]))
            except (ValueError, IndexError):
                self.tg.send("🎯 Choose the instrument, then send the price your chart shows now.\n"
                             "اختار الأداة، وبعدين ابعت السعر يلي على شارتك هلق.", chat=cid, markup=calib_markup())
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
                self.tg.send(f"Lot size set to <b>{v:g}</b>. This changes the money numbers in your reports. "
                             f"Dow and Nasdaq use at least their smallest lot (0.1).", chat=cid)
            except ValueError:
                self.tg.send("Write it like this: <code>/lot 0.1</code>", chat=cid)
        elif cmd == "/report":
            self.send_report(cid, sub)
        elif cmd == "/lang":
            a = arg.strip().lower()
            sub["lang"] = "en" if a.startswith("en") else "ar" if a.startswith("ar") else ("ar" if sub.get("lang") == "en" else "en")
            self.tg.send(msg_lang(sub), chat=cid)
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
        elif data == "lang":
            sub["lang"] = "ar" if sub.get("lang") == "en" else "en"
            self.tg.send(msg_lang(sub), chat=cid)
        elif data in ("cal", "cx") or data.startswith("c:"):
            self.tg.answer(cq["id"])
            if not self.is_owner(cid):
                return
            if data == "cal":
                self.tg.send("🎯 <b>Calibrate prices</b> · ظبّط الأسعار\nChoose the instrument · اختار الأداة", chat=cid, markup=calib_markup())
            elif data == "cx":
                sub.pop("await_cal", None)
                self.tg.edit(cid, mid, "✖ Calibration cancelled.")
            elif data[2:] in INSTRUMENTS:
                sub["await_cal"] = data[2:]
                self.tg.edit(cid, mid, f"{ICON.get(data[2:], '')} <b>{INSTRUMENTS[data[2:]]['name']}</b>\n"
                                       f"Send the price your chart shows now (just the number).\n"
                                       f"ابعت السعر يلي على شارتك هلق، رقم بس.")
            return
        self.tg.answer(cq["id"])
        self.tg.edit(cid, mid, msg_menu(sub), markup=menu_markup(sub, self.is_owner(cid)))

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
            ref = ny.replace(hour=12, minute=0, second=0).timestamp()   # midday NY = the Beirut day that is closing
            self._broadcast_daily(lambda sub: msg_close(sub, stats_text(sub, self.ledger, ref),
                                                        n_sig, weekly, i, today_line(sub, self.ledger, ref)))
            self.save()

# ───────────────────────────── live loop ─────────────────────────────
HTF_SEC = {"1d": 86400, "4h": 14400, "1h": 3600, "15m": 900}

def bias_info_for(sym, now, cache, fresh_after=0):
    """The higher-timeframe candles and trends of a symbol (read again when older than 10 minutes, or when a chart
    candle closed after they were read: the trend must see every higher candle finished before that close)."""
    c = cache.get(sym)
    if c and now - c["ts"] < 600 and c["ts"] >= fresh_after:
        return c
    bs, datr, htf = {}, None, {}
    for tf in ("1d", "4h", "1h", "15m", "5m"):
        try:
            bars_tf = get_candles(sym, tf, now)
            htf[tf] = bars_tf
            bs[tf] = bias_from_bars(bars_tf)
            if tf == "1d":
                datr = calc_atr(bars_tf)
        except Exception as e:
            log.warning("bias %s %s: %s", sym, tf, e); bs[tf] = 0
    info = make_info(bs, datr, now)
    info["htf"] = htf                                 # kept to rebuild the trend of a missed candle (bias_info_at)
    cache[sym] = info
    return info

def bias_info_at(sym, t, cache, fallback):
    """The trend as it was at time t (the close of a missed candle), from the higher-timeframe candles already read:
    only the candles that had closed by then count, the way the indicator saw it on that candle."""
    c = cache.get(sym) or {}
    htf = c.get("htf") or {}
    if len(htf) < len(HTF_SEC) or t >= c.get("ts", 0):     # nothing read, or read before that candle closed
        return fallback
    bs, datr = {}, fallback.get("datr")
    for tf, sec in HTF_SEC.items():
        closed = [b for b in htf[tf] if b.t + sec <= t]
        bs[tf] = bias_from_bars(closed)
        if tf == "1d" and closed:
            datr = calc_atr(closed) or datr
    return make_info(bs, datr, t)

def make_info(bs, datr, ts):
    """Trend per chart timeframe from the four higher-timeframe trends (same rules as the indicator)."""
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
    return dict(ts=ts, now=now_b, txt=txt, datr=datr, by_tf=by_tf, txt_by_tf=txt_by_tf, bs=dict(bs),
                arrows=f"D{arrow(bs['1d'])} 4H{arrow(bs['4h'])} 1H{arrow(bs['1h'])} 15{arrow(bs['15m'])}")

ALIGN_KEYS = {1: {"1m": ("4h", "1h", "15m"), "5m": ("4h", "1h", "15m"), "15m": ("4h", "1h", "15m"),
                  "30m": ("4h", "1h", "15m"), "1h": ("1d", "4h", "1h")},
              2: {tf: ("1d", "4h", "1h", "15m") for tf in ("1m", "5m", "15m", "30m", "1h")}}

def aligned_trend(bs, tf, align):
    """Stricter trend (tested per setting): align 1 = the 4H, 1H and 15M all the same way (1H chart: D, 4H, 1H),
    align 2 = all four (D, 4H, 1H, 15M). Otherwise mixed (0)."""
    vals = [bs.get(k, 0) for k in ALIGN_KEYS[align][tf]]
    return vals[0] if vals[0] != 0 and all(v == vals[0] for v in vals) else 0

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
    log.info("Phoenix HAZ bot running: %s | %s | provider=%s", ",".join(symbols), ",".join(tfs), provider())
    eng.snap_fn = lambda syms: snapshot(syms, int(time.time()), cache)
    if not tg.dry:
        tg.setup()
    if not tg.dry and not tg.check() and tg.channel:
        log.warning("Channel disabled for this run: signals go to private subscribers only (fix TELEGRAM_CHAT_ID or remove it)")
        tg.channel = ""
    end = time.time() + minutes * 60 if minutes else None
    m1c, nxt_m1 = {}, {}                                    # 1-minute candles read this round, next minute per symbol
    nxt_live, last_poll = {}, 0.0
    live_ok = LIVE and MINUTES and provider() == "capital"
    log.info("Instant follow-up: %s", f"on (the forming minute every {LIVE_SEC:g}s)" if live_ok else "off (finished minutes)")

    def minute_bars(sym, now):
        if sym not in m1c or m1c[sym][0] != now:
            m1c[sym] = (now, get_candles(sym, "1m", now))
        return m1c[sym][1]

    def minute_limit(sym, pairs):
        # minutes are followed only up to the close of the next chart candle each timeframe still has to plan, so
        # a stop or an exit never happens before a candle that closed earlier was planned (same order as the backtest)
        lim = [eng.pair(x, t)["last_t"] + 2 * TF_SEC[t] for x, t in pairs if x == sym and eng.pair(x, t)["last_t"]]
        return min(lim) if lim else None

    while True:
        tnow = time.time()
        now = int(tnow)
        if tnow - last_poll >= 2.0:
            eng.poll()                                      # users choosing their signals
            last_poll = tnow
        eng.daily_messages(now)
        pairs = watch_pairs(eng, symbols, tfs)
        eng.auto_offsets(sorted({x for x, _ in pairs}), now)
        act_syms = sorted({o["sym"] for o in eng.orders if o["state"] in (PENDING, OPEN)})
        # 0) instant: the minute that is still forming, every LIVE_SEC, for the instruments with a waiting / open trade
        if live_ok:
            for sym in act_syms:
                if tnow < nxt_live.get(sym, 0):
                    continue
                nxt_live[sym] = tnow + LIVE_SEC
                try:
                    bar = CAPITAL.forming(sym, time.time())
                    if bar is not None:
                        eng.live_check(sym, bar, time.time())
                except Exception as e:
                    log.warning("%s live: %s", sym, e)
                    nxt_live[sym] = tnow + 10
            if eng.dirty:
                eng.save()
                eng.dirty = False
        # a) every minute: the waiting and open trades on the minute that just closed (stop moves, exits)
        if MINUTES:
            for sym in sorted({o["sym"] for o in eng.orders if o["state"] in (PENDING, OPEN)}):
                if now < nxt_m1.get(sym, 0):
                    continue
                try:
                    m1 = minute_bars(sym, now)
                    eng.manage_minutes(sym, m1, until=minute_limit(sym, pairs))
                    eng.save()
                    nxt_m1[sym] = (m1[-1].t + 120 + 3) if m1 else now + 20
                except Exception as e:
                    log.warning("%s 1m: %s", sym, e)
                    nxt_m1[sym] = now + 20
        # b) every chart candle: the minutes up to its close, then the plan (missed candles are caught up in order)
        for sym, tf in pairs:
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
                    m1 = minute_bars(sym, now) if MINUTES else []
                    t_end = bars[new[-1]].t + TF_SEC[tf]
                    if MINUTES and (not m1 or m1[-1].t + 60 < t_end) and now < t_end + 180:
                        nxt[key] = now + 2                           # the minutes of that candle are not all in yet
                        continue
                    info = bias_info_for(sym, now, cache, fresh_after=t_end)
                    for i in new:
                        sub = None
                        if MINUTES:
                            eng.manage_minutes(sym, m1, until=bars[i].t + TF_SEC[tf])
                            sub = []                                  # already followed minute by minute
                        if i == len(bars) - 1:
                            eng.process_bar(sym, tf, bars[:i + 1], info, is_latest=True, subbars=sub)
                        else:                                       # missed between runs: planned too, sent later if still waiting
                            eng.process_bar(sym, tf, bars[:i + 1], info, is_latest=False, replay=True, subbars=sub)
                    eng.save()
                last = bars[-1].t if bars else now
                nxt[key] = max(last + 2 * TF_SEC[tf] + 1, now + 2)          # about a second after the next close
            except Exception as e:
                log.warning("%s: %s", key, e)
                nxt[key] = now + 30
        if once or (end and time.time() >= end):
            eng.save()
            log.info("Run finished, state saved")
            return
        time.sleep(0.25 if (live_ok and act_syms) else 1.0)

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
        key = k + ":" + next((w for w in ("New order", "Updated", "FILLED", "TP1 HIT", "TP2 HIT", "LAST TARGET", "STOP LOSS", "CLOSED AT ENTRY", "PROFIT KEPT", "CANCELLED") if w in t), "?")
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
                key = k + "|" + next((w for w in ("New signal", "FILLED", "TARGET HIT", "STOP LOSS HIT", "STOPPED AT ENTRY", "PROTECTED EXIT", "PROFIT LOCKED EXIT", "LOCK PROFIT", "PROTECT", "TIME LIMIT", "NOT TRIGGERED", "UPDATED") if w in t), "?")
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
    tfs = [t.strip().lower() for t in ENV("TIMEFRAMES", "5m,15m,30m,1h").split(",") if t.strip().lower() in TF_SEC]
    if not ALLOW_1M:
        tfs = [t for t in tfs if t != "1m"] or ["5m", "15m", "30m", "1h"]
    AVAILABLE_SYMS, AVAILABLE_TFS = syms, tfs
    token, chat = clean_token(ENV("TELEGRAM_BOT_TOKEN", "")), clean_chat(ENV("TELEGRAM_CHAT_ID", ""))
    if not a.dry_run and not token:
        sys.exit("Set TELEGRAM_BOT_TOKEN in .env (or use --dry-run). TELEGRAM_CHAT_ID is optional: it is the channel that gets every signal.")
    run(syms, tfs, Telegram(token, chat, dry=a.dry_run), once=a.once, minutes=a.minutes)

if __name__ == "__main__":
    main()
