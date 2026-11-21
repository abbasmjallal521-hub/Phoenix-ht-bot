"""Offline tests of the content maker (no Chrome, nothing sent): python watchdog/test_content.py -v"""
import os
import re
import sys
import unittest
from datetime import date, datetime
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import phoenix_content as C   # noqa: E402

b, wd = C.bot, C.wd
DAY = date(2026, 11, 20)


def ts(h, m, day=DAY):
    return datetime(day.year, day.month, day.day, h, m, tzinfo=wd.TZ).timestamp()


def order(sym, tf, d, trig, sl, tps, hits, state, exit_px, t0, t1):
    return {"v20": True, "sym": sym, "tf": tf, "dir": d, "trig": trig, "sl": sl, "tps": tps, "risk": abs(trig - sl),
            "hits": hits, "state": state, "exit_px": exit_px, "fill_t": t0, "exit_t": t1, "exit_at": t1, "born_t": t0}


def state(orders):
    ledger = []
    for o in orders:
        if o["state"] in C.DONE:
            dist, cost = (o["exit_px"] - o["trig"]) * o["dir"], b.cost_price(o["sym"])
            oc = -1 if o["state"] == b.SL_HIT else 1 if dist - cost > b.INSTRUMENTS[o["sym"]]["tick"] else 2
            ledger.append({"t": o["exit_t"], "td": b.trading_day(o["exit_t"]).isoformat(), "sym": o["sym"],
                           "tf": o["tf"], "dist": dist, "cost": cost, "oc": oc})
    return {"orders": orders, "ledger": ledger}


GOLD_WIN = order("XAUUSD", "5m", 1, 2650.2, 2647.1, [2652.12, 2653.3, 2655.22], 3, b.TP_HIT, 2655.22, ts(10, 15), ts(10, 57))
NAS_WIN = order("NAS100", "15m", -1, 20810.5, 20845.0, [20789.4, 20776.0, 20756.0], 3, b.TP_HIT, 20756.0, ts(16, 35), ts(17, 50))
DOW_LOSS = order("US30", "5m", 1, 43950.0, 43912.0, [43973.0, 43988.0, 44011.0], 0, b.SL_HIT, 43912.0, ts(15, 40), ts(16, 5))
GOLD_BE = order("XAUUSD", "15m", -1, 2661.4, 2664.9, [2659.3, 2657.9, 2655.7], 1, b.BE_HIT, 2661.21, ts(12, 5), ts(13, 20))
OPEN = order("XAUUSD", "1h", 1, 2640.1, 2635.6, [2645.7, 2649.4], 0, b.OPEN, None, ts(18, 0), 0)
OTHER_DAY = order("XAUUSD", "5m", 1, 2600.0, 2597.0, [2602.0], 1, b.TP_HIT, 2602.0, ts(10, 0, date(2026, 11, 19)),
                  ts(10, 30, date(2026, 11, 19)))
ALL = [GOLD_WIN, NAS_WIN, DOW_LOSS, GOLD_BE, OPEN, OTHER_DAY]


class TheDay(unittest.TestCase):
    def test_only_that_days_closed_trades(self):
        got = C.closed_trades(state(ALL), DAY)
        self.assertEqual([(x["sym"], x["oc"]) for x in got],
                         [("XAUUSD", 1), ("XAUUSD", 2), ("US30", -1), ("NAS100", 1)])    # by closing time
        self.assertAlmostEqual(got[0]["usd"], b.money("XAUUSD", 5.02 - b.cost_price("XAUUSD"), C.LOT))

    def test_the_numbers_are_the_bots_own(self):
        st = state(ALL)
        t = C.day_tally(st, DAY, C.closed_trades(st, DAY))
        self.assertEqual((t["n"], t["win"], t["loss"], t["be"]), (4, 2, 1, 1))

    def test_captions_tell_the_truth(self):
        st = state(ALL)
        trades = C.closed_trades(st, DAY)
        ar, en = C.captions(DAY, C.day_tally(st, DAY, trades), trades)
        self.assertIn("✅ 2 ربح · ❌ 1 خسارة · ⚪ 1 رجعت عالدخول · نسبة الربح 67%", ar)
        self.assertIn("التداول فيه مخاطرة", ar)
        self.assertIn("Trading involves risk", en)
        for words in (ar, en):
            self.assertIsNone(re.search(r"مضمون|guarantee[ds]? profit|100%", words))   # no promises


class Cards(unittest.TestCase):
    def setUp(self):
        self.st = state(ALL)
        self.trades = C.closed_trades(self.st, DAY)

    def test_day_card_shows_every_trade_and_the_risk(self):
        page = C.day_card(DAY, C.day_tally(self.st, DAY, self.trades), self.trades)
        self.assertIn("الجمعة 20 تشرين الثاني", page)
        self.assertIn("US30", page)                                    # the loss is on the card too
        self.assertIn("−$", page)
        self.assertIn(C.RISK, page)
        self.assertIn("@phoenix.haz.syndi", page)
        self.assertIn(".ttf", page)                                    # the brand font, from the repo

    def test_trade_card_ladder(self):
        win = [x for x in self.trades if x["sym"] == "NAS100"][0]
        page = C.trade_card(win)
        self.assertIn("وصلت كل الأهداف", page)
        self.assertIn("SELL", page)
        rows = re.findall(r'class="row (\w+)[^"]*" style="top:(\d+)px"><span class="lab">(?:<svg.*?</svg>)?([^<]+)<', page)
        order_ = [label for _, _, label in sorted(rows, key=lambda r: int(r[1]))]
        self.assertEqual(order_, ["الستوب", "الدخول", "TP1", "TP2", "TP3"])     # a sell: the stop on top
        tops = sorted(int(t) for _, t, _ in rows)
        self.assertTrue(all(b2 - a2 >= 57 for a2, b2 in zip(tops, tops[1:])))     # labels never overlap
        self.assertTrue(all(40 <= t <= 480 for t in tops))                        # all inside the box

    def test_lot_of_the_instrument(self):
        nas = [x for x in self.trades if x["sym"] == "NAS100"][0]
        self.assertIn('على لوت <span class="n">0.1</span>', C.trade_card(nas))


class Running(unittest.TestCase):
    def run_main(self, st, *args):
        sent = []
        tg = mock.Mock(token="t", chat="1", send=lambda text: sent.append(text) or True)
        with mock.patch.object(C, "load_state", return_value=st), mock.patch.object(C, "find_chrome", return_value=None), \
                mock.patch.object(C.wd, "Telegram", return_value=tg), mock.patch.object(C.wd, "owner_chat", return_value=("1", "test")):
            code = C.main(["--day", DAY.isoformat(), "--no-video", *args])
        return code, sent

    def test_no_chrome_still_sends_the_captions(self):
        code, sent = self.run_main(state(ALL))
        self.assertEqual(code, 0)
        self.assertEqual(len(sent), 3)
        self.assertIn("ما قدرت اعمل الصور", sent[0])
        self.assertIn("نتايج مؤشر Phoenix HAZ SMC", sent[1])

    def test_a_day_without_trades_sends_nothing(self):
        code, sent = self.run_main(state([OPEN, OTHER_DAY]))
        self.assertEqual((code, sent), (0, []))

    def test_album_is_one_request_with_the_pictures(self):
        import tempfile
        d = tempfile.mkdtemp()
        pngs = []
        for i in range(2):
            pngs.append(os.path.join(d, f"{i}.png"))
            with open(pngs[-1], "wb") as fh:
                fh.write(b"x")
        tg = mock.Mock(token="TOKEN", chat="42")
        ok_reply = mock.Mock(status_code=200, json=lambda: {"ok": True})
        with mock.patch.object(C.requests, "post", return_value=ok_reply) as post:
            self.assertTrue(C.send_album(tg, pngs, "<b>hi</b>"))
        url, kw = post.call_args[0][0], post.call_args[1]
        self.assertTrue(url.endswith("/sendMediaGroup"))
        self.assertEqual(sorted(kw["files"]), ["p0", "p1"])
        self.assertIn('"caption": "<b>hi</b>"', kw["data"]["media"])


if __name__ == "__main__":
    unittest.main()
