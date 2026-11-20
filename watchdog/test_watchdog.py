"""Offline tests of the watchdog: GitHub, Telegram, Capital.com and the app are all fakes.
Run:  python watchdog/test_watchdog.py -v
"""
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import phoenix_watchdog as pw  # noqa: E402

T0 = datetime(2026, 11, 20, 7, 0, tzinfo=timezone.utc).timestamp()      # 09:00 in Beirut: after the morning time


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class FakeGH:
    def __init__(self):
        self.runs_list, self.job, self.logs = [], {}, {}
        self.state, self.sha = "active", "aaa"
        self.dispatched, self.enabled = [], []
        self.dispatch_ok = True

    def add_run(self, rid, status, start=None, end=None, conclusion=None, failed_step=None, created=None):
        run = {"id": rid, "status": status, "conclusion": conclusion, "head_sha": self.sha,
               "created_at": iso(created or start or time.time()), "updated_at": iso(end or start or time.time())}
        self.runs_list.insert(0, run)
        steps = [{"name": "Run bot", "conclusion": "failure" if failed_step else "success"}]
        self.job[rid] = {"id": rid * 10, "status": "completed" if status == "completed" else status,
                         "started_at": iso(start) if start else None, "completed_at": iso(end) if end else None,
                         "steps": steps}
        return run

    def finish(self, rid, end, conclusion="success", failed_step=None):
        for r in self.runs_list:
            if r["id"] == rid:
                r.update(status="completed", conclusion=conclusion, updated_at=iso(end))
        self.job[rid].update(status="completed", completed_at=iso(end))
        if failed_step:
            self.job[rid]["steps"] = [{"name": failed_step, "conclusion": "failure"}]

    def runs(self, wf, n=20):
        return [dict(r) for r in self.runs_list[:n]]

    def jobs(self, run_id):
        return [dict(self.job[run_id])] if run_id in self.job else []

    def job_log(self, job_id):
        return self.logs.get(job_id // 10, "")

    def workflow(self, wf):
        return {"state": self.state}

    def head_sha(self):
        return self.sha

    def dispatch(self, wf):
        self.dispatched.append(time.time())
        return self.dispatch_ok

    def enable(self, wf):
        self.enabled.append(wf)
        if self.state == "disabled_inactivity":
            self.state = "active"
        return True


class FakeTG:
    def __init__(self, username="Phoenix_ht_smc"):
        self.sent, self.channel, self.username = [], "@phoenixhttrading", username
        self.member = {"status": "administrator", "can_post_messages": True}
        self.token_ok, self.deliver, self.refuse = True, True, None     # refuse: 403 = Start never pressed
        self.last_error = None

    def call(self, method, payload):
        if not self.token_ok:
            return False, "Unauthorized", 401
        if method == "getMe":
            return True, self.me(), 200
        if method == "getChatMember":
            return (True, self.member, 200) if self.member else (False, "chat not found", 400)
        return True, {}, 200

    def me(self):
        return {"id": 42, "username": self.username}

    def send(self, text):
        if self.refuse or not self.deliver or not self.token_ok:
            self.last_error = (self.refuse or (401 if not self.token_ok else 0), "refused")
            return False
        self.last_error = None
        self.sent.append(text)
        return True


class Case(unittest.TestCase):
    def setUp(self):
        self.clock = T0
        self.tmp = tempfile.TemporaryDirectory()
        patches = [mock.patch.object(pw.time, "time", lambda: self.clock),
                   mock.patch.object(pw.time, "sleep", lambda s: None),
                   mock.patch.object(pw, "STATE_FILE", os.path.join(self.tmp.name, "state.json"))]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)
        self.gh, self.tg = FakeGH(), FakeTG()
        self.cap = {"kind": "ok", "bid": 4105.2}
        self.web = {"ok": True, "sec": 1.4, "code": 200}
        self.wd = self.make()

    def make(self, **kw):
        wd = pw.Watchdog(self.gh, self.tg, **kw)
        wd.probe_capital = lambda: dict(self.cap)
        wd.probe_web = lambda url: dict(self.web)
        wd.app_url = "https://app.example"
        return wd

    def tick(self, minutes=5):
        self.wd.tick()
        self.wd.save()
        self.clock += minutes * 60

    def texts(self):
        out = "\n=====\n".join(self.tg.sent)
        self.tg.sent.clear()
        return out


class Words(unittest.TestCase):
    def test_durations(self):
        self.assertEqual(pw.dur(30), "أقل من دقيقة")
        self.assertEqual(pw.dur(60), "دقيقة")
        self.assertEqual(pw.dur(120), "دقيقتين")
        self.assertEqual(pw.dur(5 * 60), "5 دقايق")
        self.assertEqual(pw.dur(25 * 60), "25 دقيقة")
        self.assertEqual(pw.dur(80 * 60), "ساعة و20 دقيقة")
        self.assertEqual(pw.dur(2 * 3600), "ساعتين")
        self.assertEqual(pw.dur(5 * 3600 + 120), "5 ساعات")
        self.assertEqual(pw.dur(2 * 86400), "يومين")
        self.assertEqual(pw.times(1), "مرة")
        self.assertEqual(pw.times(3), "3 مرات")

    def test_clean(self):
        self.assertEqual(pw.clean_chat("t.me/phoenixhttrading"), "@phoenixhttrading")
        self.assertEqual(pw.clean_chat("-1001234"), "-1001234")
        self.assertEqual(pw.clean_token(" bot123:ABC "), "123:ABC")

    def test_scan_log(self):
        text = ("2026-11-20T10:00:00Z 2026-11-20 10:00:00,1 INFO Phoenix HAZ bot running\n"
                "2026-11-20T10:01:00Z 2026-11-20 10:01:00,1 WARNING XAUUSD|5m: Capital.com login failed: check\n"
                "2026-11-20T10:02:00Z 2026-11-20 10:02:00,1 WARNING XAUUSD|5m: Capital.com login failed: check\n"
                "2026-11-20T10:03:00Z 2026-11-20 10:03:00,1 ERROR Telegram sendMessage failed: 400\n"
                "2026-11-20T10:03:00Z WARNING: Running pip as the 'root' user\n")
        res = pw.scan_log(text)
        self.assertEqual((res["warn"], res["err"]), (2, 1))
        self.assertEqual(res["top"][0][1], 2)
        self.assertEqual(res["crit"], [["Capital.com رفض الدخول (يعني ما في أسعار)", 2, "capital"]])

    def test_kind_of_reads_telegram_json(self):
        msg = ('Telegram answerCallbackQuery failed: {"ok":false,"error_code":400,'
               '"description":"Bad Request: query is too old"}')
        self.assertEqual(pw.kind_of(msg), "Telegram answerCallbackQuery failed: Bad Request: query is too old")

    def test_market_guess(self):
        sat = datetime(2026, 11, 21, 12, tzinfo=timezone.utc).timestamp()
        tue = datetime(2026, 11, 24, 12, tzinfo=timezone.utc).timestamp()
        self.assertFalse(pw.market_open_guess(sat))
        self.assertTrue(pw.market_open_guess(tue))


class FirstWatch(Case):
    def test_hello_and_report(self):
        self.gh.add_run(1, "completed", start=T0 - 8 * 3600, end=T0 - 2.5 * 3600, conclusion="success")
        self.gh.add_run(2, "in_progress", start=T0 - 2 * 3600)
        self.gh.logs[1] = "x 2026 WARNING NEWS CHECK: the calendar could not be read (Timeout)\n"
        self.tick()
        out = self.texts()
        self.assertIn("أهلا، أنا المراقب", out)
        self.assertIn("تقرير المراقب", out)
        self.assertIn("✅ شغال (من ساعتين)", out)
        self.assertIn("الدهب 4,105.20", out)
        self.assertIn("كل شي تمام", out)
        self.assertIn("0 خطأ · 1 تحذير", out)
        self.assertEqual(self.gh.dispatched, [])
        self.tick()                                          # nothing new: silence
        self.assertEqual(self.texts(), "")

    def test_morning_once_a_day(self):
        self.gh.add_run(2, "in_progress", start=T0 - 3600)
        self.tick()
        self.texts()
        for _ in range(12):
            self.tick(60)                                    # the next 12 hours
        self.assertNotIn("تقرير المراقب", self.texts())
        self.clock = T0 + 86400                              # next day, 09:00 Beirut
        self.tick()
        self.assertIn("تقرير المراقب", self.texts())


class Restarts(Case):
    def setUp(self):
        super().setUp()
        self.gh.add_run(1, "in_progress", start=T0 - 3600)
        self.tick()
        self.texts()

    def test_bot_off_is_started_silently(self):
        self.gh.finish(1, self.clock)
        self.tick(1)                                         # just ended: not yet
        self.tick(4)                                         # 1 minute off: still in the grace time
        self.assertEqual(self.gh.dispatched, [])
        self.tick()                                          # 5 minutes off: started again
        self.assertEqual(len(self.gh.dispatched), 1)
        self.assertEqual(self.texts(), "")                   # silent, counted in the report
        self.gh.add_run(2, "in_progress", start=self.clock)
        self.tick()
        self.assertEqual(self.texts(), "")
        self.assertIn("رجّعته يشتغل مرة لما وقف", self.wd.report())

    def test_restart_fails_three_times_then_alert_then_solved(self):
        self.gh.finish(1, self.clock)
        self.clock += 120
        for _ in range(3):
            self.tick()
        self.assertEqual(len(self.gh.dispatched), 3)
        self.assertEqual(self.texts(), "")
        self.tick()
        out = self.texts()
        self.assertIn("بوت الإشارات واقف", out)
        self.assertIn("حاولت رجّعه 3 مرات", out)
        self.gh.add_run(2, "in_progress", start=self.clock)
        self.tick()
        self.assertIn("✅ <b>بوت الإشارات رجع يشتغل</b>", self.texts())

    def test_crash_alert_and_crash_loop(self):
        self.gh.finish(1, self.clock, conclusion="failure", failed_step="Run bot")
        self.gh.logs[1] = "x WARNING a\nTraceback (most recent call last):\n"
        self.tick()
        out = self.texts()
        self.assertIn("بوت الإشارات وقع", out)
        self.assertIn("Run bot", out)
        self.assertIn("البوت ضرب خطأ بالكود", out)
        for rid in (2, 3):                                   # two more quick crashes
            self.gh.add_run(rid, "completed", start=self.clock - 60, end=self.clock - 30, conclusion="failure",
                            failed_step="pip install")
            self.gh.finish(rid, self.clock - 30, conclusion="failure", failed_step="pip install")
            self.tick()
        out = self.texts()
        self.assertIn("عم يوقع كل ما يشتغل", out)
        n = len(self.gh.dispatched)
        self.tick()
        self.tick()
        self.assertEqual(len(self.gh.dispatched), n)          # paused
        self.gh.sha = "bbb"                                   # a fix was pushed
        self.tick()
        self.assertEqual(len(self.gh.dispatched), n + 1)
        self.gh.add_run(4, "in_progress", start=self.clock)
        self.tick(35)
        self.tick()
        self.assertIn("رجع يشتغل طبيعي", self.texts())

    def test_queued_too_long(self):
        self.gh.finish(1, self.clock)
        self.gh.add_run(2, "queued", created=self.clock - 5 * 3600)   # waited behind run 1 for hours: not news
        self.tick()
        self.assertEqual(self.texts(), "")
        self.tick(15)
        self.tick()
        self.assertIn("عالق بالدور", self.texts())
        self.gh.runs_list[0]["status"] = "in_progress"
        self.gh.job[2]["started_at"] = iso(self.clock)
        self.tick()
        self.assertIn("بلّش يشتغل", self.texts())
        self.assertEqual(self.gh.dispatched, [])

    def test_disabled_by_hand_is_left_alone(self):
        self.gh.state = "disabled_manually"
        self.gh.finish(1, self.clock)
        self.wd.st["due"]["workflow"] = 0
        self.tick()
        self.tick()
        self.assertIn("موقّف يدوياً", self.texts())
        self.assertEqual(self.gh.dispatched, [])

    def test_disabled_by_github_is_enabled_again(self):
        self.gh.state = "disabled_inactivity"
        self.wd.st["due"]["workflow"] = 0
        self.tick()
        self.assertIn("رجّعت فتحته", self.texts())
        self.assertIn("phoenix.yml", self.gh.enabled)


class Services(Case):
    def setUp(self):
        super().setUp()
        self.gh.add_run(1, "in_progress", start=T0 - 3600)
        self.tick()
        self.texts()

    def due_now(self, key):
        self.wd.st["due"][key] = 0

    def test_channel_lost_then_fixed(self):
        self.tg.member = {"status": "member"}
        self.due_now("tg")
        self.tick()
        self.assertEqual(self.texts(), "")                   # one failure: look again first
        self.tick()
        out = self.texts()
        self.assertIn("الإشارات ما عم تنزل بالقناة", out)
        self.assertIn("مش أدمن", out)
        self.tg.member = {"status": "administrator", "can_post_messages": True}
        self.tick(15)
        self.tick()
        out = self.texts()
        self.assertIn("رجع يقدر ينشر", out)
        self.assertIn("تشغيلته الجاية", out)

    def test_channel_not_found_explains_the_fix(self):
        self.tg.member = None                                # getChatMember: chat not found (the bot's logs today)
        self.due_now("tg")
        self.tick()
        self.assertIn("🔴", self.wd.report())                 # first failure: in the report, not yet an alert
        self.assertIn("في شي مش طبيعي فوق", self.wd.report())
        self.tick()
        out = self.texts()
        self.assertIn("البوت مش لاقي القناة", out)
        self.assertIn("TELEGRAM_CHAT_ID", out)
        self.assertIn("chat not found", out)

    def test_capital_refused(self):
        self.cap = {"kind": "login", "why": "demo 401 error.invalid.details"}
        self.due_now("capital")
        self.tick()
        self.tick()
        out = self.texts()
        self.assertIn("رافض الدخول", out)
        self.assertIn("error.invalid.details", out)
        self.cap = {"kind": "ok", "bid": 4100.0}
        self.tick(15)
        self.tick()
        self.assertIn("الأسعار رجعت توصل", self.texts())

    def test_capital_closed_is_fine(self):
        self.cap = {"kind": "closed", "bid": 4090.5}
        self.due_now("capital")
        self.tick()
        self.assertEqual(self.texts(), "")
        self.assertIn("السوق مسكّر", self.wd.report())

    def test_app_down_with_reminder(self):
        self.web = {"ok": False, "code": 503, "suspended": True}
        self.due_now("app")
        self.tick()
        self.tick()
        out = self.texts()
        self.assertIn("تطبيق Phoenix HT Trading مش عم يفتح", out)
        self.assertIn("الساعات المجانية", out)
        for _ in range(17):                                  # 4 hours later: one reminder
            self.tick(15)
        out = self.texts()
        self.assertEqual(out.count("لسا في مشكلة"), 1)
        self.web = {"ok": True, "sec": 52.0, "code": 200}
        self.tick(15)
        self.tick()
        self.assertIn("التطبيق رجع يفتح", self.texts())

    def test_telegram_down_keeps_messages(self):
        self.tg.deliver = False
        self.web = {"ok": False, "why": "timeout"}
        self.due_now("app")
        self.tick()
        self.tick()
        self.assertEqual(len(self.wd.outbox), 1)
        self.tg.deliver = True
        self.tick()
        self.assertIn("ما فتح خلال دقيقتين", self.texts())
        self.assertEqual(self.wd.outbox, [])

    def test_report_with_problems_and_no_app_link(self):
        self.wd.app_url = ""
        self.wd.st["issues"]["capital"] = {"title": "أسعار الدهب واقفة", "ok": "x", "since": self.clock - 1200,
                                           "said": self.clock}
        rep = self.wd.report()
        self.assertIn("زيد secret اسمه APP_URL", rep)
        self.assertIn("لسا في مشاكل مفتوحة", rep)
        self.assertIn("أسعار الدهب واقفة (من 20 دقيقة)", rep)


class ReportRun(Case):
    def test_report_run_is_quiet(self):
        self.gh.add_run(1, "completed", start=T0 - 7 * 3600, end=T0 - 3600, conclusion="success")
        wd = self.make(quiet=True)
        wd.tick(report=True)
        self.assertEqual(self.tg.sent, [])                   # no hello, no alert
        self.assertEqual(self.gh.dispatched, [])             # never starts anything
        self.assertIn("🔴 واقف هلق", wd.report())


class OwnBot(Case):
    """WATCHDOG_BOT_TOKEN set: the alerts come from the watchdog's own bot, never mixed with the trades."""

    def setUp(self):
        super().setUp()
        self.sig = FakeTG()                                  # the signal bot
        self.own = FakeTG(username="Phoenix_Watchdog_bot")   # the watchdog's own bot
        self.wd = self.make_own()
        self.gh.add_run(1, "in_progress", start=T0 - 3600)

    def make_own(self):
        wd = pw.Watchdog(self.gh, self.own, sig=self.sig)
        wd.probe_capital = lambda: dict(self.cap)
        wd.probe_web = lambda url: dict(self.web)
        wd.app_url = "https://app.example"
        return wd

    def test_everything_goes_to_its_own_chat(self):
        self.tick()
        out = "\n".join(self.own.sent)
        self.assertIn("لحاله للتحذيرات", out)
        self.assertIn("تقرير المراقب", out)
        self.assertNotIn("WATCHDOG_BOT_TOKEN", out)
        self.assertEqual(self.sig.sent, [])                  # nothing in the signal bot's chat

    def test_start_not_pressed_one_note_through_the_signal_bot(self):
        self.own.refuse = 403
        self.tick()
        self.tick()
        self.assertEqual(len(self.sig.sent), 1)              # once a day only
        self.assertIn("@Phoenix_Watchdog_bot", self.sig.sent[0])
        self.assertIn("Start", self.sig.sent[0])
        self.own.refuse = None                               # Start pressed
        self.tick()
        out = "\n".join(self.own.sent)
        self.assertIn("أهلا، أنا المراقب", out)              # what waited is delivered
        self.assertIn("تقرير المراقب", out)
        self.assertEqual(self.wd.outbox, [])

    def test_signal_bot_token_broken_is_told_by_the_own_bot(self):
        self.tick()
        self.own.sent.clear()
        self.sig.token_ok = False
        self.wd.st["due"]["tg"] = 0
        self.tick()
        self.tick()
        out = "\n".join(self.own.sent)
        self.assertIn("توكن بوت الإشارات ما عاد شغال", out)
        self.assertIn("TELEGRAM_BOT_TOKEN", out)
        self.sig.token_ok = True
        self.tick(15)
        self.tick()
        self.assertIn("بوت الإشارات رجع يشتغل عالتلغرام", "\n".join(self.own.sent))

    def test_moving_to_the_own_bot_says_hello_there(self):
        old = self.make()                                    # first without WATCHDOG_BOT_TOKEN
        old.tick()
        old.save()
        self.assertIn("WATCHDOG_BOT_TOKEN", "\n".join(self.tg.sent))
        self.wd = self.make_own()                            # then the secret is added
        self.tick()
        self.assertIn("لحاله للتحذيرات", "\n".join(self.own.sent))


if __name__ == "__main__":
    unittest.main()
