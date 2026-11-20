"""Offline tests for the analyst: python watchdog/test_analyst.py -v (no internet, nothing sent)."""
import os
import sys
import unittest
from datetime import date, datetime, timedelta

sys.path[:0] = [os.path.dirname(os.path.abspath(__file__))]
import phoenix_analyst as A   # noqa: E402

MON = date(2026, 11, 16)                       # a Monday


def entry(day, sym, tf, oc, hour=12, dur=1800, dist=None):
    """A ledger line as the bot books it: closed at `hour` Beirut (+ dur), on trading day `day`."""
    opened = datetime(day.year, day.month, day.day, hour, 0, tzinfo=A.wd.TZ).timestamp()
    cost = A.bot.cost_price(sym)
    if dist is None:
        dist = {1: 3.0, -1: -2.0, 2: cost}[oc] * (1 if sym == "XAUUSD" else 10)
    return {"t": opened + dur, "td": day.isoformat(), "sym": sym, "tf": tf, "dist": dist, "cost": cost, "oc": oc,
            "dur": dur}


def week(rows):
    """rows: (weekday 0-4, sym, tf, oc, hour) -> ledger of the test week."""
    return [entry(MON + timedelta(days=d), s, tf, oc, h) for d, s, tf, oc, h in rows]


class Numbers(unittest.TestCase):
    def test_tally_and_rate(self):
        ts = A.trades_of(week([(0, "XAUUSD", "5m", 1, 10), (0, "XAUUSD", "5m", -1, 11), (1, "XAUUSD", "5m", 2, 12),
                               (2, "XAUUSD", "5m", 1, 16)]))
        t = A.tally(ts)
        self.assertEqual((t["n"], t["win"], t["loss"], t["be"]), (4, 2, 1, 1))
        self.assertEqual(A.rate(t), 67)                              # 2 of 3: the one at entry is left out
        gold = A.bot.money("XAUUSD", 3.0 - A.bot.cost_price("XAUUSD"), A.LOT)
        self.assertAlmostEqual(ts[0]["usd"], gold)

    def test_old_ledger_lines_without_result(self):
        e = entry(MON, "XAUUSD", "5m", 1)
        del e["oc"], e["dur"]
        ts = A.trades_of([e, {"sym": "BTC", "tf": "5m", "td": MON.isoformat()}])   # unknown instrument: skipped
        self.assertEqual([x["oc"] for x in ts], [1])

    def test_sessions_and_streak(self):
        self.assertEqual([A.session_of(h) for h in (0, 1, 8, 9, 14, 15, 22, 23)],
                         ["الليل", "آسيا", "آسيا", "لندن", "لندن", "نيويورك", "نيويورك", "الليل"])
        ts = A.trades_of(week([(0, "XAUUSD", "5m", -1, 9), (0, "XAUUSD", "5m", 2, 10), (0, "XAUUSD", "5m", -1, 11),
                               (0, "XAUUSD", "5m", 1, 12), (0, "XAUUSD", "5m", -1, 13)]))
        self.assertEqual(A.loss_streak(ts), 2)


class Report(unittest.TestCase):
    def test_week_numbers_and_sections(self):
        rows = [(d, "XAUUSD", "5m", 1, 10) for d in range(5)] + [(1, "NAS100", "15m", -1, 16), (2, "NAS100", "15m", 1, 16)]
        prev = [entry(MON - timedelta(days=3), "XAUUSD", "15m", -1)]
        msg = A.build({"ledger": week(rows) + prev}, MON + timedelta(days=5))
        self.assertIn("16 – 20 تشرين الثاني 2026", msg)
        self.assertIn("<b>7 صفقة</b> · ✅6 ❌1 ⚪0", msg)
        self.assertIn("<b>86%</b>", msg)
        self.assertIn("الأسبوع الماضي: 1 صفقة", msg)
        self.assertIn("• الدهب 5M: 5 · ✅5 ❌0 ⚪0", msg)
        self.assertIn("• لندن 9–15: 5", msg)
        self.assertIn("• الجمعة: 1", msg)
        self.assertIn("⏸ بلا صفقات:", msg)
        self.assertIn("(الداو والناسداك 0.1)", msg)
        self.assertLess(len(msg), 4096)                               # one Telegram message

    def test_ideas_follow_the_numbers(self):
        rows = ([(d, "NAS100", "5m", -1, 16) for d in range(4)] + [(0, "NAS100", "5m", 1, 16)] +
                [(d, "XAUUSD", "15m", 1, 10) for d in range(5)] + [(1, "US30", "30m", -1, 16)] * 2)
        msg = A.build({"ledger": week(rows)}, MON + timedelta(days=5))
        self.assertIn("📉 <b>الناسداك 5M</b> خسّر", msg)
        self.assertIn("🔥 <b>الدهب 15M</b> كان الأحسن", msg)
        self.assertIn("🎯 نسبة الربح 50% والهدف 80%. أضعف وقت كان نيويورك", msg)
        self.assertIn("بلا ما نوقف التداول فيه", msg)                  # the owner wants trades at every hour
        self.assertIn("📊 12 صفقة والهدف حوالي 40", msg)
        self.assertIn("نختبر الفضة والنفط", msg)                       # instruments with no tested settings yet
        self.assertNotIn("ستوب", msg)                                  # the stop rules are the owner's call

    def test_quiet_good_week(self):
        rows = [(i % 5, s, tf, 1, 10) for s, tfs in A.bot.V20.items() for tf in tfs for i in range(3)]
        msg = A.build({"ledger": week(rows)}, MON + timedelta(days=5))
        self.assertIn("👌", msg)                                      # no chart stands out, goals met
        self.assertNotIn("⏸", msg)

    def test_no_trades_and_no_state(self):
        self.assertIn("ما سكّرت ولا صفقة", A.build({"ledger": []}, MON))
        self.assertIn("ما قدرت اقرا ذاكرة بوت الإشارات", A.build(None, MON))


class FakeGH:
    def __init__(self, runs):
        self._runs = runs

    def runs(self, wf, n=20):
        return [{"id": i, "status": "completed" if e else "in_progress", "updated_at": e or s}
                for i, (s, e) in enumerate(self._runs)]

    def jobs(self, run_id):
        s, e = self._runs[run_id]
        return [{"started_at": s, "completed_at": e}] if s else []


class Uptime(unittest.TestCase):
    def test_share_and_stops(self):
        iso = lambda h: datetime.fromtimestamp(NOW - h * 3600, A.wd.TZ).astimezone().isoformat()
        global NOW
        NOW = 1_800_000_000
        runs = [(iso(10), None), (iso(20), iso(10.5)), (iso(30), iso(21)), ("", "")]   # stops: 0.5h and 1h
        share, gaps = A.bot_uptime(FakeGH(runs), hours=30, now=NOW)
        self.assertAlmostEqual(share, 28.5 / 30, places=3)
        self.assertEqual(sorted(round(g / 3600, 1) for g in gaps), [0.5, 1.0])


class Main(unittest.TestCase):
    def test_dry_run_prints_the_report(self):
        import io
        import contextlib
        os.environ.pop("GITHUB_TOKEN", None)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = A.main(["--dry-run", "--week", "2026-11-18"])
        self.assertEqual(code, 0)
        self.assertIn("المحلل · تقرير الأسبوع", buf.getvalue())


NOW = 0

if __name__ == "__main__":
    unittest.main()
