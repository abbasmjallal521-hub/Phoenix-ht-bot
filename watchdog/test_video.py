"""Offline tests of the video maker (no Chrome, nothing sent): python watchdog/test_video.py -v"""
import os
import sys
import tempfile
import unittest
import wave
from datetime import timedelta
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import phoenix_video as V   # noqa: E402
import test_content as TC   # noqa: E402  the same made-up trades as the pictures' tests

C, b = V.content, V.bot
T0 = TC.ts(10, 15)


def walk(entry, target, opened, before=24, after=8, sec=300):
    """Candles: quiet around the entry before it opens, then a straight walk to (and past) the target."""
    out, t = [], (int(opened) // sec - before) * sec
    for _ in range(before):
        out.append((t, entry, entry + 0.05 * abs(target - entry), entry - 0.05 * abs(target - entry), entry))
        t += sec
    prev = entry
    for i in range(1, after + 1):
        c = entry + (target - entry) * 1.1 * i / after
        out.append((t, prev, max(prev, c), min(prev, c), c))
        prev, t = c, t + sec
    return out


def trade(o):
    return C.closed_trades(TC.state([o]), TC.DAY)[0]


class Chart(unittest.TestCase):
    def test_a_trade_on_its_own_timeframe(self):
        x = {"tf": "5m", "opened": T0, "closed": T0 + 40 * 60}
        tf, sec, start, end = V.trade_window(x)
        self.assertEqual((tf, sec), ("5m", 300))
        self.assertEqual(start, (int(T0) // 300 - V.BEFORE) * 300)            # the stretch before the entry
        self.assertGreaterEqual(end, x["closed"])

    def test_a_long_trade_on_a_bigger_timeframe(self):
        tf, sec, start, end = V.trade_window({"tf": "5m", "opened": T0, "closed": T0 + 10 * 3600})
        self.assertEqual(tf, "15m")
        self.assertLessEqual((end - start) / sec, V.MAX_BARS)

    def test_the_entry_and_the_targets_in_order(self):
        for o in (TC.GOLD_WIN, TC.NAS_WIN):                                  # a buy and a sell
            x = trade(o)
            bars = walk(o["trig"], o["tps"][-1], x["opened"])
            info = V.trade_info(x, bars, "5m")
            self.assertEqual(info["fill"], V.BEFORE)
            self.assertEqual(len(info["hit_at"]), o["hits"])
            self.assertEqual(info["hit_at"], sorted(info["hit_at"]))
            for k, i in enumerate(info["hit_at"]):                            # each target really is in that candle
                self.assertTrue(bars[i][2] >= o["tps"][k] if o["dir"] == 1 else bars[i][3] <= o["tps"][k])
            hits = V.reveal(info)["hit"]
            self.assertEqual(hits, sorted(hits))

    def test_without_candles_the_ladder(self):
        info = V.trade_info(trade(TC.GOLD_WIN))
        self.assertIsNone(info["bars"])
        s = V.reveal(info)
        self.assertEqual(len(s["hit"]), 3)
        self.assertAlmostEqual(s["hit"][-1], s["b1"])

    def test_candles_from_capital_with_the_bots_offset(self):
        x = trade(TC.GOLD_WIN)
        raw = [b.Bar(t, o, h, l, c) for t, o, h, l, c in walk(2650.0, 2655.0, x["opened"], after=12)]
        feed = mock.Mock(get=mock.Mock(return_value={"prices": []}), _parse=mock.Mock(return_value=raw))
        bars, tf = V.trade_bars(feed, x, {"XAUUSD": 0.5})
        self.assertEqual(tf, "5m")
        self.assertEqual(bars[0][1], raw[0].o + 0.5)                         # the bot's levels carry the offset
        params = feed.get.call_args[0][1]
        self.assertEqual(params["resolution"], "MINUTE_5")
        self.assertIn("from", params)
        feed._parse.return_value = raw[:5]                                    # not the whole trade: no chart
        self.assertIsNone(V.trade_bars(feed, x)[0])
        feed.get.side_effect = RuntimeError("down")                           # no prices: no chart, no crash
        self.assertIsNone(V.trade_bars(feed, x)[0])


class Stories(unittest.TestCase):
    def infos(self):
        out = []
        for o in (TC.GOLD_WIN, TC.NAS_WIN):
            x = trade(o)
            out.append(V.trade_info(x, walk(o["trig"], o["tps"][-1], x["opened"]), "5m"))
        return out

    def check(self, story):
        at = 0.0
        for sc in story["scenes"]:
            self.assertAlmostEqual(sc["start"], at, places=2)                 # one scene after the other
            at += sc["dur"]
        self.assertAlmostEqual(story["dur"], at, places=2)
        for t, _ in story["sfx"]:
            self.assertTrue(0 <= t <= story["dur"])

    def test_the_days_video(self):
        st = TC.state(TC.ALL)
        t = C.day_tally(st, TC.DAY, C.closed_trades(st, TC.DAY))
        story = V.day_story(TC.DAY, t, self.infos())
        self.check(story)
        self.assertEqual([s["kind"] for s in story["scenes"]], ["intro", "summary", "trade", "trade", "outro"])
        self.assertEqual(sum(k.startswith("ding") for _, k in story["sfx"]), 6)   # a bell for every target reached
        self.assertEqual(story["scenes"][1]["tiles"][1][0], t["win"])
        self.assertIn(C.RISK, story["risk"])

    def test_the_weeks_numbers(self):
        st = TC.state(TC.ALL)
        mon, t, by, best = V.week_numbers(st, TC.DAY)
        self.assertEqual(mon.weekday(), 0)
        self.assertEqual((t["n"], t["win"], t["loss"], t["be"]), (5, 3, 1, 1))  # the 19th and the 20th
        wins = [x for d in range(7) for x in C.closed_trades(st, mon + timedelta(days=d)) if x["oc"] == 1]
        self.assertEqual(best["usd"], max(x["usd"] for x in wins))
        self.assertEqual(set(by), {"XAUUSD", "NAS100", "US30"})

    def test_the_weeks_video(self):
        st = TC.state(TC.ALL)
        mon, t, by, best = V.week_numbers(st, TC.DAY)
        story = V.week_story(mon, t, by, self.infos()[1])
        self.check(story)
        self.assertEqual([s["kind"] for s in story["scenes"]], ["intro", "how", "week", "trade", "outro"])
        how = story["scenes"][1]
        self.assertEqual(len(how["hits"]), 3)
        self.assertEqual(how["hits"][-1][0], "وصلت كل الأهداف")
        bare = V.week_story(mon, t, by, None)                                 # no winning trade: the numbers only
        self.assertEqual([s["kind"] for s in bare["scenes"]], ["intro", "week", "outro"])
        ar, en = V.week_captions(mon, t)
        self.assertIn("نسبة الربح 75%", ar)
        self.assertIn("Trading involves risk", en)

    def test_the_page_cannot_be_broken_by_a_word(self):
        story = V.day_story(TC.DAY, {"n": 1, "win": 1, "loss": 0, "be": 0, "usd": 1.0}, [])
        story["scenes"][0]["sub"] = "</script><b>"
        page = V.page_html(story)
        self.assertEqual(page.count("</script>"), 1)
        self.assertIn("data:font/ttf;base64,", page)


class Sound(unittest.TestCase):
    def test_the_soundtrack(self):
        try:
            import numpy  # noqa: F401
        except ImportError:
            self.skipTest("numpy not installed")
        story = {"dur": 3.0, "drop": 1.0, "sfx": [(0.1, "boom"), (0.6, "whoosh"), (1.2, "ding0"), (1.6, "sparkle"),
                                                    (2.0, "pop"), (2.2, "hit")]}
        path = os.path.join(tempfile.mkdtemp(), "s.wav")
        V.soundtrack(story, path)
        with wave.open(path) as w:
            self.assertEqual((w.getnchannels(), w.getframerate()), (2, V.SR))
            self.assertEqual(w.getnframes(), int(3.6 * V.SR))


class Sending(unittest.TestCase):
    def test_the_video_goes_as_a_telegram_video(self):
        path = os.path.join(tempfile.mkdtemp(), "v.mp4")
        with open(path, "wb") as fh:
            fh.write(b"x" * 100)
        ok_reply = mock.Mock(status_code=200, json=lambda: {"ok": True})
        with mock.patch.object(V.requests, "post", return_value=ok_reply) as post:
            self.assertTrue(V.send_video(mock.Mock(token="TOKEN", chat="42"), path, "<b>hi</b>", 31.6))
        url, kw = post.call_args[0][0], post.call_args[1]
        self.assertTrue(url.endswith("/sendVideo"))
        self.assertEqual((kw["data"]["chat_id"], kw["data"]["duration"], kw["data"]["supports_streaming"]), ("42", 32, "true"))
        self.assertIn("video", kw["files"])

    def test_the_morning_sends_pictures_videos_and_captions_in_order(self):
        sent = []
        tg = mock.Mock(token="t", chat="1", send=lambda text: sent.append(("text", text[:12])) or True)
        vids = [("/x/day.mp4", 30.0, "day", None), ("/x/week.mp4", 25.0, "week", ("week ar", "week en"))]
        with mock.patch.object(C, "load_state", return_value=TC.state(TC.ALL)), \
                mock.patch.object(C, "find_chrome", return_value=None), \
                mock.patch.object(C, "make_videos", return_value=vids) as make, \
                mock.patch.object(C, "send_video", side_effect=lambda tg_, p, cap, s: sent.append(("video", cap)) or True), \
                mock.patch.object(C.wd, "Telegram", return_value=tg), mock.patch.object(C.wd, "owner_chat", return_value=("1", "test")):
            self.assertEqual(C.main(["--day", TC.DAY.isoformat()]), 0)
        self.assertTrue(make.call_args[0][4])                                 # a Friday: the week's video too
        kinds = [k if k == "video" else v for k, v in sent]
        self.assertEqual(sent[1], ("video", "day"))                           # the head, the day's video, the captions
        self.assertEqual(sent[4], ("video", "week"))                          # then the week's video and its captions
        self.assertEqual(sent[5:], [("text", "week ar"), ("text", "week en")])
        self.assertEqual(len(kinds), 7)


if __name__ == "__main__":
    unittest.main()
