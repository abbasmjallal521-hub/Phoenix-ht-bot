"""Offline tests of the mail check (مدير الإيميلات): Gmail is a fake.  python watchdog/test_mail.py -v"""
import imaplib
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import phoenix_mail as pm   # noqa: E402
import test_watchdog as T   # noqa: E402  the watchdog's fakes and test base

pw = T.pw
GMAIL_OK = "mx.google.com; dkim=pass header.i=@{d}; spf=pass smtp.mailfrom={d}; dmarc=pass (p=REJECT) header.from={d}"
GMAIL_FAIL = "mx.google.com; dkim=fail; spf=softfail; dmarc=fail (p=NONE) header.from={d}"


def mail(frm, subject, ok=True, date="Sat, 21 Nov 2026 05:12:00 +0200"):
    d = pm.domain_of(pm.parseaddr(frm)[1])
    auth = (GMAIL_OK if ok else GMAIL_FAIL).format(d=d)
    return f"From: {frm}\r\nSubject: {subject}\r\nDate: {date}\r\nAuthentication-Results: {auth}\r\n\r\n".encode()


class FakeIMAP:
    """A Gmail inbox: {uid: header bytes}. Checks it is opened read-only and read with BODY.PEEK."""

    def __init__(self, box):
        self.box = box

    def login(self, user, password):
        if password != self.box["password"]:
            raise imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Invalid credentials (Failure)")

    def status(self, mailbox, what):
        nxt = max(self.box["msgs"], default=0) + 1
        return "OK", [f'"INBOX" (UIDNEXT {nxt} UIDVALIDITY {self.box["uidv"]})'.encode()]

    def select(self, mailbox, readonly=False):
        assert readonly, "the inbox must be opened read-only"
        return "OK", [b"1"]

    def uid(self, cmd, *args):
        if cmd == "SEARCH":
            lo = int(args[1].split()[1].split(":")[0])
            hits = [u for u in sorted(self.box["msgs"]) if u >= lo] or [max(self.box["msgs"])]   # IMAP's "n:*"
            return "OK", [" ".join(map(str, hits)).encode()]
        assert cmd == "FETCH" and "BODY.PEEK" in args[1], "headers only, never marked as read"
        out = []
        for u in args[0].split(","):
            out += [(f"{u} (UID {u} BODY[HEADER.FIELDS] {{99}}".encode(), self.box["msgs"][int(u)]), b")"]
        return "OK", out

    def logout(self):
        self.box["logouts"] = self.box.get("logouts", 0) + 1


def watcher(box, mem=None):
    return pm.MailWatch("me@gmail.com", "abcd efgh ijkl mnop", {} if mem is None else mem,
                        repo="abbasmjallal521-hub/Phoenix-ht-bot", connect=lambda: FakeIMAP(box))


class Sorting(unittest.TestCase):
    def c(self, frm, subject, ok=True):
        name, addr = pm.parseaddr(frm)
        auth = (GMAIL_OK if ok else GMAIL_FAIL).format(d=pm.domain_of(addr))
        return pm.classify(name, addr, subject, auth, "abbasmjallal521-hub/Phoenix-ht-bot", ["paypal.com"])

    def test_serious_from_known_senders(self):
        self.assertEqual(self.c("GitHub <noreply@github.com>", "[GitHub] Please verify your device")["label"], "GitHub")
        self.assertTrue(self.c("Google <no-reply@accounts.google.com>", "Hello")["real"])          # every one
        self.assertEqual(self.c("Render <no-reply@render.com>", "Deploy failed for phoenix-ht-trading")["label"], "Render")
        self.assertEqual(self.c("Firebase <firebase-noreply@google.com>", "Your Cloud Firestore database has insecure rules")["label"], "Firebase")
        self.assertEqual(self.c("Capital.com <support@capital.com>", "Margin call warning")["label"], "Capital.com")
        self.assertEqual(self.c("PayPal <service@paypal.com>", "Receipt")["label"], "paypal.com")   # MAIL_WATCH

    def test_ordinary_mail_is_only_counted(self):
        self.assertIsNone(self.c("GitHub <notifications@github.com>", "Re: [abbasmjallal521-hub/Phoenix-ht-bot] Analyst (PR #7)"))
        self.assertIsNone(self.c("Capital.com <news@capital.com>", "Weekly market outlook"))
        self.assertIsNone(self.c("LinkedIn <jobs@linkedin.com>", "New jobs for you"))

    def test_the_bots_own_failed_runs_are_left_to_the_watchdog(self):
        self.assertIsNone(self.c("GitHub <notifications@github.com>",
                                 "[abbasmjallal521-hub/Phoenix-ht-bot] Run failed: Phoenix HT Bot - main (abc123)"))
        self.assertIsNotNone(self.c("GitHub <notifications@github.com>",
                                    "[abbasmjallal521-hub/phoenix-ht-trading] Run failed: Deploy - main (abc123)"))

    def test_fakes_are_marked(self):
        spoof = self.c("GitHub <noreply@github.com>", "[GitHub] Security alert", ok=False)
        self.assertEqual((spoof["label"], spoof["real"]), ("GitHub", False))
        look = self.c("GitHub Security <alert@github.com.secure-login.io>", "Security alert: new sign-in")
        self.assertEqual((look["real"], look["unknown"]), (False, True))
        self.assertFalse(pm.is_from("x@evilgithub.com", ("github.com",)))
        self.assertTrue(self.c("بنك <info@bank.example>", "تنبيه أمان: تسجيل دخول جديد")["unknown"])


class Inbox(unittest.TestCase):
    def setUp(self):
        self.box = {"password": "abcdefghijklmnop", "uidv": 7,
                    "msgs": {10: mail("Old <old@example.com>", "Security alert from last year")}}
        self.mem = {}

    def test_first_look_only_marks_the_place(self):
        found, came, first = watcher(self.box, self.mem).check()
        self.assertEqual((found, came, first, self.mem["next"]), ([], 0, True, 11))   # nothing old is sent

    def test_new_mail_is_sorted_and_counted(self):
        w = watcher(self.box, self.mem)
        w.check()
        self.box["msgs"].update({11: mail("GitHub <noreply@github.com>", "[GitHub] A new SSH key was added"),
                                 12: mail("LinkedIn <jobs@linkedin.com>", "New jobs"),
                                 13: mail("GitHub <notifications@github.com>", "Re: [x/y] Fix (PR #3)")})
        found, came, first = w.check()
        self.assertEqual((len(found), came, first), (1, 3, False))
        self.assertEqual(found[0]["subject"], "[GitHub] A new SSH key was added")
        self.assertEqual(self.mem["digest"], {"n": 3, "serious": 1, "by": {"GitHub": 2, "LinkedIn": 1}})
        self.assertEqual(w.check(), ([], 0, False))                        # read once only
        self.assertEqual(self.box["logouts"], 3)

    def test_a_new_inbox_id_starts_again(self):
        w = watcher(self.box, self.mem)
        w.check()
        self.box["uidv"] = 8
        self.box["msgs"][11] = mail("GitHub <noreply@github.com>", "[GitHub] Security alert")
        self.assertEqual(w.check()[2], True)

    def test_wrong_password(self):
        self.box["password"] = "other"
        with self.assertRaises(pm.LoginError):
            watcher(self.box).check()


class WithTheWatchdog(T.Case):
    def setUp(self):
        super().setUp()
        self.box = {"password": "abcdefghijklmnop", "uidv": 1, "msgs": {5: mail("A <a@example.com>", "hi")}}
        self.wd.mail = watcher(self.box, self.wd.st["mail"])

    def test_hello_then_serious_mail_at_once(self):
        self.tick()
        self.assertIn("مدير الإيميلات صار شغّال", self.texts())
        self.box["msgs"][6] = mail("Render <no-reply@render.com>", "Your service phoenix-ht-trading was suspended")
        self.tick()                                                     # 5 minutes: not yet due
        self.tick()
        sent = self.texts()
        self.assertIn("📧 <b>إيميل مهم</b>", sent)
        self.assertIn("Your service phoenix-ht-trading was suspended", sent)
        self.assertNotIn("ما تأكّدت", sent)
        self.tick()
        self.tick()
        self.assertNotIn("مدير الإيميلات صار شغّال", self.texts())       # said once

    def test_unverified_senders_carry_a_warning(self):
        self.tick()
        self.box["msgs"][6] = mail("GitHub <noreply@github.com>", "[GitHub] Security alert", ok=False)
        self.box["msgs"][7] = mail("Google <no-reply@accounts.google.com>", "Critical security alert")
        self.clock += 600
        self.tick()
        sent = self.texts()
        self.assertIn("إيميلين مهمّين", sent)
        self.assertIn("1. ⚠️ <b>GitHub</b>", sent)
        self.assertIn("ما تأكّدت إنه المرسل حقيقي", sent)

    def test_wrong_password_is_told_after_a_second_try(self):
        self.box["password"] = "changed"
        self.tick()
        self.assertNotIn("ما قدرت فوت عالـGmail", self.texts())
        self.tick()
        self.assertIn("ما قدرت فوت عالـGmail", self.texts())
        self.box["password"] = "abcdefghijklmnop"
        self.clock += 900
        self.tick()
        self.assertIn("رجعت فوت عالـGmail", self.texts())

    def test_the_report_counts_the_rest(self):
        self.tick()
        self.texts()
        self.box["msgs"].update({6: mail("LinkedIn <jobs@linkedin.com>", "Jobs"), 7: mail("LinkedIn <jobs@linkedin.com>", "More")})
        self.clock += 600
        self.tick()
        self.assertIn("📬 الإيميلات من آخر تقرير: 2", self.wd.report())
        self.assertIn("LinkedIn 2", self.wd.report())

    def test_no_secrets_no_mail_check(self):
        self.wd.mail = pm.MailWatch("", "", self.wd.st["mail"])
        self.tick()
        self.assertNotIn("مدير الإيميلات", self.texts().replace("📬 الإيميلات: ⚪ مش مربوطة", ""))
        self.assertIn("مش مربوطة", self.wd.report())


if __name__ == "__main__":
    unittest.main()
