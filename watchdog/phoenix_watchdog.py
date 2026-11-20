#!/usr/bin/env python3
"""Phoenix Watchdog (المراقب).

Keeps an eye on everything around the Phoenix HT bot and tells the owner on Telegram:

* the bot (GitHub Actions): is a run going? When nothing runs it is started again (GitHub's own schedule often
  starts the next run hours late). Crashes, crash loops and a disabled workflow are reported;
* the channel: can the bot still post there?
* the prices: does Capital.com still let the bot in, and does gold move while the market is open?
* the app and the link page (optional, from the APP_URL / LINK_URL secrets): do they open?
* every finished bot run: its log is read and its warnings and errors are counted;
* every morning a short report: "كل شي تمام", or what is still wrong.

The messages come from the watchdog's own Telegram bot (WATCHDOG_BOT_TOKEN), in its own chat, so they never mix
with the trades; it can also tell when the signal bot itself stops working. Without that secret they come from the
signal bot.

It never changes the bot's code, settings or state: it only reads, and starts the bot workflow the same way its own
schedule does. A problem is sent once, repeated every few hours while it lasts, and followed by a ✅ message when it
is solved.

The repository is public, so its Actions logs are public too: chat ids, links and passwords are never written to the
log here.
"""
import argparse
import html
import json
import logging
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests

log = logging.getLogger("watchdog")
ENV = os.environ.get
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = ENV("WATCHDOG_STATE") or os.path.join(ROOT, "watchdog_state.json")
BOT_STATE_FILE = ENV("BOT_STATE") or os.path.join(ROOT, "phoenix_state.json")   # the bot's saved state (read only)

REPO = ENV("GITHUB_REPOSITORY") or "abbasmjallal521-hub/Phoenix-ht-bot"
GH_API = ENV("GITHUB_API_URL") or "https://api.github.com"
BOT_WF = ENV("BOT_WORKFLOW") or "phoenix.yml"
SELF_WF = ENV("WATCHDOG_WORKFLOW") or "watchdog.yml"
TZ = ZoneInfo(ENV("WATCHDOG_TZ") or "Asia/Beirut")
MORNING_AT = ENV("WATCHDOG_MORNING") or "08:50"       # daily report time (WATCHDOG_TZ)
AUTO_RESTART = (ENV("AUTO_RESTART") or "1") == "1"    # start the bot again when nothing runs
NOTIFY_RESTARTS = (ENV("NOTIFY_RESTARTS") or "0") == "1"   # 1 = a message for every restart (else: in the report)
UA = {"User-Agent": "PhoenixWatchdog/1.0"}

TICK = 300                      # one round every 5 minutes: the bot's runs are read every round
EVERY = {"workflow": 1800, "tg": 3600, "capital": 3600, "app": 3600, "link": 3600, "keepalive": 7 * 86400}
RECHECK = 300                   # a check that failed once runs again after 5 minutes, before any message
OPEN_RECHECK = 900              # while a problem lasts, its check runs every 15 minutes (to see it solved)
REMIND = 4 * 3600               # a problem that lasts is sent again every 4 hours
RESTART_GRACE = 90              # seconds the bot may stay off before it is started again
MAX_RESTARTS, RESTART_WINDOW = 3, 1800          # at most 3 restarts in 30 minutes, then a message
CRASH_LOOP, CRASH_WINDOW = 3, 7200              # 3 failed runs in 2 hours = crash loop: restarts pause
CRASH_PAUSE = 3 * 3600                          # ... until a new commit, or for 3 hours
STALE_PRICE = 15 * 60           # market open and no new gold minute for this long = prices stopped
QUEUED_TOO_LONG = 15 * 60       # a bot run waiting this long for a GitHub machine
CHAIN_AFTER = 20 * 60           # a watch that lasted this long starts the next one (never a fast crash loop)

DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
esc = html.escape


# ───────────────────────────── small helpers ─────────────────────────────
def count_ar(n, one, two, few, many):
    """Arabic number + word: 1 مرة, 2 مرتين, 3 مرات, 11 مرة."""
    if n == 1:
        return one
    if n == 2:
        return two
    return f"{n} {few}" if 3 <= n <= 10 else f"{n} {many}"


def times(n):
    return count_ar(n, "مرة", "مرتين", "مرات", "مرة")


def dur(sec):
    """A length of time in words: 5 دقايق, ساعة و20 دقيقة, يومين."""
    sec = max(0, int(sec or 0))
    if sec < 60:
        return "أقل من دقيقة"
    mins = round(sec / 60)
    if mins < 60:
        return count_ar(mins, "دقيقة", "دقيقتين", "دقايق", "دقيقة")
    hours, mins = divmod(mins, 60)
    if hours < 24:
        out = count_ar(hours, "ساعة", "ساعتين", "ساعات", "ساعة")
        return out + (" و" + count_ar(mins, "دقيقة", "دقيقتين", "دقايق", "دقيقة") if mins >= 5 else "")
    return count_ar(round(hours / 24), "يوم", "يومين", "أيام", "يوم")


def ts(iso):
    """GitHub / ISO time -> epoch seconds (None when empty)."""
    if not iso:
        return None
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def local_now():
    return datetime.fromtimestamp(time.time(), TZ)


def clock(t):
    return datetime.fromtimestamp(t, TZ).strftime("%H:%M")


def clean_token(t):
    """Same as the bot: accept a token pasted with spaces, quotes or a 'bot' prefix."""
    t = "".join((t or "").split()).strip("'\"")
    return t[3:] if t.lower().startswith("bot") and ":" in t else t


def clean_chat(c):
    """Same as the bot: @name, name, t.me/name links or a numeric id."""
    c = "".join((c or "").split()).strip("'\"")
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


def owner_chat():
    """Who gets the messages: WATCHDOG_CHAT_ID, else ADMIN_ID, else the bot's owner from its saved state."""
    for key in ("WATCHDOG_CHAT_ID", "ADMIN_ID"):
        v = (ENV(key) or "").strip()
        if v:
            return v, key
    try:
        with open(BOT_STATE_FILE, encoding="utf-8") as fh:
            d = json.load(fh)
        v = str((d.get("meta") or {}).get("owner") or next(iter(d.get("subs") or {}), "") or "")
        if v:
            return v, "the bot's owner (saved state)"
    except (OSError, ValueError):
        pass
    return "", ""


def write_output(key, value):
    path = ENV("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{key}={value}\n")


# ───────────────────────────── GitHub ─────────────────────────────
class GitHub:
    def __init__(self, token, repo=REPO, api=GH_API):
        self.repo, self.api, self.branch = repo, api.rstrip("/"), None
        self.s = requests.Session()
        self.s.headers.update({"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", **UA})
        if token:
            self.s.headers["Authorization"] = f"Bearer {token}"

    def _url(self, path):
        return f"{self.api}/repos/{self.repo}/{path}".rstrip("/")

    def get(self, path, **params):
        r = self.s.get(self._url(path), params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def runs(self, wf, n=20):
        return self.get(f"actions/workflows/{wf}/runs", per_page=n).get("workflow_runs", [])

    def jobs(self, run_id):
        return self.get(f"actions/runs/{run_id}/jobs", per_page=10).get("jobs", [])

    def job_log(self, job_id):
        r = self.s.get(self._url(f"actions/jobs/{job_id}/logs"), timeout=120)   # redirect: the token is not sent on
        r.raise_for_status()
        return r.text

    def workflow(self, wf):
        return self.get(f"actions/workflows/{wf}")

    def default_branch(self):
        if not self.branch:
            self.branch = self.get("").get("default_branch") or "main"
        return self.branch

    def head_sha(self):
        return self.get(f"commits/{self.default_branch()}").get("sha")

    def dispatch(self, wf):
        r = self.s.post(self._url(f"actions/workflows/{wf}/dispatches"), json={"ref": self.default_branch()}, timeout=30)
        if r.status_code != 204:
            log.warning("starting %s was refused: %s %s", wf, r.status_code, r.text[:200])
        return r.status_code == 204

    def enable(self, wf):
        r = self.s.put(self._url(f"actions/workflows/{wf}/enable"), timeout=30)
        return r.status_code == 204


# ───────────────────────────── Telegram ─────────────────────────────
class Telegram:
    def __init__(self, token, chat, channel="", dry=False):
        self.token, self.chat, self.channel, self.dry = token, chat, channel, dry
        self.last_error, self._me = None, None          # (http status, Telegram's text) of the last failed send

    def me(self):
        """The bot's own account (getMe), kept after the first answer."""
        if self._me is None:
            ok, res, _ = self.call("getMe", {})
            if ok:
                self._me = res
        return self._me or {}

    def call(self, method, payload):
        """(ok, result or error text, http status). The URL holds the token: it is never logged."""
        if not self.token:
            return False, "no bot token", 0
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        last = (False, "no answer", 0)
        for _ in range(3):
            try:
                r = requests.post(url, json=payload, timeout=25)
            except requests.RequestException as e:
                last = (False, type(e).__name__, 0)
                time.sleep(3)
                continue
            try:
                d = r.json()
            except ValueError:
                d = {}
            if r.status_code == 429:
                last = (False, "too many requests", 429)
                time.sleep(min(60, (d.get("parameters") or {}).get("retry_after", 5) + 1))
                continue
            if r.ok and d.get("ok"):
                return True, d.get("result"), r.status_code
            return False, d.get("description") or r.text[:200], r.status_code
        return last

    def send(self, text):
        if self.dry:
            print(f"\n──── Telegram ────\n{text}\n", flush=True)
            return True
        if not self.chat:
            log.error("no chat to message: add the secret WATCHDOG_CHAT_ID (your Telegram id)")
            return False
        ok, res, code = self.call("sendMessage", {"chat_id": self.chat, "text": text, "parse_mode": "HTML",
                                                  "disable_web_page_preview": True})
        self.last_error = None if ok else (code, str(res)[:200])
        if not ok:
            log.error("Telegram sendMessage failed (%s): %s", code, str(res)[:200])
        return ok


# ───────────────────────────── outside checks ─────────────────────────────
CAPITAL_HOSTS = {"demo": "https://demo-api-capital.backend-capital.com", "live": "https://api-capital.backend-capital.com"}


def market_open_guess(t):
    """Gold CFD hours when Capital.com gives no market status: closed on the weekend and in the daily break."""
    d = datetime.fromtimestamp(t, timezone.utc)
    if d.weekday() == 5 or (d.weekday() == 4 and d.hour >= 21) or (d.weekday() == 6 and d.hour < 23):
        return False
    return d.hour not in (21, 22)


def capital_probe(epic="GOLD"):
    """Log in to Capital.com like the bot does and read gold. kind: ok, closed, stale, login, down or off."""
    key = (ENV("CAPITAL_API_KEY") or "").strip()
    if not key:
        return {"kind": "off"}
    body = {"identifier": (ENV("CAPITAL_IDENTIFIER") or "").strip(),
            "password": (ENV("CAPITAL_PASSWORD") or "").strip(), "encryptedPassword": False}
    first = (ENV("CAPITAL_ENV") or "demo").strip().lower()
    order = [first] + [e for e in CAPITAL_HOSTS if e != first] if first in CAPITAL_HOSTS else list(CAPITAL_HOSTS)
    hdr = base = None
    refused, errors = [], []
    for env in order:                                   # a key made on the other account type still works (as the bot)
        time.sleep(1.1)                                 # Capital.com: one new session a second per key (the bot too)
        try:
            r = requests.post(CAPITAL_HOSTS[env] + "/api/v1/session", json=body, timeout=20,
                              headers={"X-CAP-API-KEY": key, "Content-Type": "application/json", **UA})
        except requests.RequestException as e:
            errors.append(type(e).__name__)
            continue
        if r.ok and r.headers.get("CST"):
            hdr = {"CST": r.headers["CST"], "X-SECURITY-TOKEN": r.headers.get("X-SECURITY-TOKEN", ""), **UA}
            base = CAPITAL_HOSTS[env]
            break
        try:
            code = (r.json() or {}).get("errorCode", "")
        except ValueError:
            code = ""
        (refused if r.status_code in (400, 401, 403) else errors).append(f"{env} {r.status_code} {code}".strip())
    if not hdr:
        if refused and not errors:
            return {"kind": "login", "why": ", ".join(refused)}
        return {"kind": "down", "why": ", ".join(refused + errors) or "no answer"}
    try:
        mk = requests.get(f"{base}/api/v1/markets/{epic}", headers=hdr, timeout=20)
        mk.raise_for_status()
        snap = (mk.json() or {}).get("snapshot") or {}
        pr = requests.get(f"{base}/api/v1/prices/{epic}", params={"resolution": "MINUTE", "max": 3}, headers=hdr, timeout=20)
        pr.raise_for_status()
        prices = (pr.json() or {}).get("prices") or []
    except (requests.RequestException, ValueError) as e:
        return {"kind": "down", "why": type(e).__name__}
    last = None
    if prices:
        t = prices[-1].get("snapshotTimeUTC") or prices[-1].get("snapshotTime")
        if t:
            last = datetime.fromisoformat(t[:19] + "+00:00").timestamp()
    status = (snap.get("marketStatus") or "").upper()
    is_open = status == "TRADEABLE" if status else market_open_guess(time.time())
    age = time.time() - last if last else None
    out = {"bid": snap.get("bid"), "age": age, "status": status}
    if is_open and (age is None or age > STALE_PRICE):
        return {"kind": "stale", **out}
    return {"kind": "ok" if is_open else "closed", **out}


def web_probe(url):
    """Open a page like a visitor. A sleeping free Render service needs about a minute to wake up."""
    t0 = time.time()
    try:
        r = requests.get(url, headers=UA, timeout=(20, 110), allow_redirects=True)
    except requests.Timeout:
        return {"ok": False, "why": "timeout"}
    except requests.RequestException as e:
        return {"ok": False, "why": type(e).__name__}
    sec = round(time.time() - t0, 1)
    if r.status_code < 400:
        return {"ok": True, "sec": sec, "code": r.status_code}
    routing = (r.headers.get("x-render-routing") or "").lower()
    return {"ok": False, "sec": sec, "code": r.status_code,
            "suspended": "suspend" in routing or "suspended" in r.text[:4000].lower()}


# ───────────────────────────── bot logs ─────────────────────────────
CRITICAL = (                                            # (text in the log, the live check that covers it, label)
    ("TELEGRAM CHECK FAILED", "tg_channel", "البوت ما قدر ينشر بالقناة"),
    ("Capital.com login failed", "capital", "Capital.com رفض الدخول (يعني ما في أسعار)"),
    ("Traceback (most recent call last)", None, "البوت ضرب خطأ بالكود (Traceback)"),
)
LEVEL = re.compile(r"\s(WARNING|ERROR|CRITICAL)\s+(.*)$")


def kind_of(msg):
    """One warning kind: Telegram's own explanation instead of its raw JSON, numbers as #."""
    m = re.search(r'"description":\s*"([^"]*)', msg)
    if m and "{" in msg:
        msg = msg[:msg.index("{")].strip() + " " + m.group(1)
    return re.sub(r"\d[\d.,:/-]*", "#", msg).strip()[:80]


def scan_log(text):
    """Count the bot's warnings and errors, the most frequent kinds, and the serious ones."""
    warn = err = 0
    kinds, crit = Counter(), Counter()
    for line in text.splitlines():
        for pat, _, label in CRITICAL:
            if pat in line:
                crit[label] += 1
        m = LEVEL.search(line)
        if not m:
            continue
        if m.group(1) == "WARNING":
            warn += 1
        else:
            err += 1
        kinds[kind_of(m.group(2))] += 1
    keys = {label: key for _, key, label in CRITICAL}
    return {"warn": warn, "err": err, "top": kinds.most_common(3),
            "crit": [[label, n, keys[label]] for label, n in crit.items()]}


# ───────────────────────────── the watchdog ─────────────────────────────
class Watchdog:
    def __init__(self, gh, tg, quiet=False, dry=False, sig=None):
        self.gh, self.tg = gh, tg                   # tg: the bot the messages come from
        self.sig = sig or tg                        # the signal bot: its channel is checked (and setup notes go there)
        self.own_bot = self.sig is not tg           # the watchdog has its own bot (WATCHDOG_BOT_TOKEN): no mixing
        self.quiet = quiet                          # report run: checks and the report only, no alerts, no restarts
        self.dry = dry                              # print the messages, start nothing
        self.st = self.load()
        self.outbox = self.st["outbox"]
        self.job_cache = {}
        self.probe_capital, self.probe_web = capital_probe, web_probe
        self.app_url = (ENV("APP_URL") or "").strip()
        self.link_url = (ENV("LINK_URL") or "").strip()

    # ── memory (kept between runs in the Actions cache)
    @staticmethod
    def load():
        st = {}
        try:
            with open(STATE_FILE, encoding="utf-8") as fh:
                st = json.load(fh)
        except (OSError, ValueError):
            pass
        for k, v in (("issues", {}), ("fails", {}), ("due", {}), ("restarts", []), ("crashes", []), ("seen", []),
                     ("stats", {}), ("outbox", [])):
            st.setdefault(k, v)
        return st

    def save(self):
        now = time.time()
        self.st["restarts"] = [t for t in self.st["restarts"] if now - t < 2 * 86400]
        self.st["crashes"] = [t for t in self.st["crashes"] if now - t < 2 * 86400]
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.st, fh, ensure_ascii=False)
        os.replace(tmp, STATE_FILE)

    # ── messages
    def say(self, text):
        """Send now. What Telegram does not take is kept and sent later (the 20 newest)."""
        if self.quiet:
            log.info("(report run: not sent) %s", re.sub(r"<[^>]+>", "", text.splitlines()[0]))
            return
        if self.flush() and self.tg.send(text):
            return
        self.outbox.append(text)
        del self.outbox[:-20]
        self.sender_trouble()

    def sender_trouble(self):
        """The watchdog's own bot could not deliver: say why through the signal bot, at most once a day."""
        if not self.own_bot or not self.tg.last_error:
            return
        code = self.tg.last_error[0]
        if code == 403:                                     # Start never pressed on the new bot (or it was blocked)
            name = self.tg.me().get("username")
            key, text = "start", ("🛡️ <b>المراقب صار إله بوت لحاله</b>\n"
                                  + (f"فوت عـ @{name} واكبس Start" if name else "فوت عالبوت الجديد تبع المراقب واكبس Start")
                                  + "، كرمال توصلك التحذيرات هونيك ومش مع الصفقات.")
        elif code in (401, 404):                            # its token is wrong
            key, text = "token", ("🛡️ <b>توكن بوت المراقب ما عاد شغال</b>\n"
                                  "حط توكن جديد من @BotFather بالـsecret اسمه WATCHDOG_BOT_TOKEN.")
        else:
            return                                          # network trouble: it is simply sent again later
        today = local_now().date().isoformat()
        if self.st.get("hint_" + key) != today:
            self.st["hint_" + key] = today
            self.sig.send(text)

    def flush(self):
        while self.outbox:
            if not self.tg.send(self.outbox[0]):
                return False
            self.outbox.pop(0)
        return True

    def problem(self, key, title, detail="", ok="", confirm=1, level="🔴", remind=REMIND, check=None):
        """A check found `key` wrong. Sent after `confirm` failures in a row, again every `remind` seconds."""
        now = time.time()
        n, first = self.st["fails"].get(key, [0, now])
        self.st["fails"][key] = [n + 1, first]
        check = check or key
        if n + 1 < confirm:
            self.st["due"][check] = now + RECHECK
            log.info("%s: failed %d/%d, checking again in 5 minutes", key, n + 1, confirm)
            return
        if check in EVERY:                                  # while it lasts, look again every 15 minutes
            self.st["due"][check] = min(self.st["due"].get(check, now + OPEN_RECHECK), now + OPEN_RECHECK)
        body = f"{level} <b>{title}</b>" + (f"\n{detail}" if detail else "")
        iss = self.st["issues"].get(key)
        if iss is None:
            self.st["issues"][key] = {"title": title, "ok": ok or "رجع كل شي طبيعي", "since": first, "said": now}
            log.info("problem: %s", key)
            self.say(body)
        else:
            iss["title"] = title
            if now - iss["said"] >= remind:
                iss["said"] = now
                self.say(f"⏳ <b>لسا في مشكلة من {dur(now - iss['since'])}</b>\n{body}")

    def fine(self, key, extra=""):
        self.st["fails"].pop(key, None)
        iss = self.st["issues"].pop(key, None)
        if iss:
            log.info("solved: %s", key)
            self.say(f"✅ <b>{iss['ok']}</b>\nالمشكلة دامت {dur(time.time() - iss['since'])}." + (f"\n{extra}" if extra else ""))

    def due(self, key):
        return time.time() >= self.st["due"].get(key, 0)

    def later(self, key, sec):
        self.st["due"][key] = time.time() + sec

    def hello(self):
        who = "own" if self.own_bot else "signal"           # said again when the messages move to the own bot
        if self.st.get("hello") is True:                    # v1 said hello from the signal bot
            self.st["hello"] = "signal"
        if self.quiet or self.st.get("hello") == who:
            return
        self.st["hello"] = who
        where = ("📌 هيدا البوت لحاله للتحذيرات بس، فما بتختلط مع الصفقات.\n\n" if self.own_bot else
                 "💡 هلق عم ببعتلك من بوت الإشارات. إذا بدك التحذيرات بشات لحالها: اعمل بوت جديد من @BotFather، "
                 "حط التوكن تبعه بـ secret اسمه WATCHDOG_BOT_TOKEN، واكبس Start عالبوت الجديد.\n\n")
        self.say("🛡️ <b>أهلا، أنا المراقب تبع Phoenix</b>\n"
                 "من هلق عيني عالبوت والقناة والأسعار والتطبيق، 24 ساعة.\n\n"
                 "🔴 إذا صار شي بدقلك هون فوراً، وبس ينحل ببعتلك ✅\n"
                 "🔄 إذا البوت وقف برجّعه يشتغل لحالي\n"
                 f"🌅 كل يوم الساعة {MORNING_AT} الصبح ببعتلك تقرير\n\n"
                 + where +
                 "<i>إذا يوم ما وصلك التقرير الصبحي، يعني أنا كمان واقف: شوف GitHub › Actions › Phoenix Watchdog.</i>")

    # ── the bot's runs
    def main_job(self, run_id, done=False):
        """The run's job (start, end, steps). `done`: the run has ended, so a copy kept while it ran is read again."""
        job = self.job_cache.get(run_id)
        if job is None or (done and job.get("status") != "completed"):
            jobs = self.gh.jobs(run_id)
            job = jobs[0] if jobs else {}
            if job.get("started_at"):
                self.job_cache[run_id] = job
        return job

    def check_bot(self):
        now = time.time()
        runs = self.gh.runs(BOT_WF, 20)
        self.scan_finished(runs)
        running = [r for r in runs if r.get("status") == "in_progress"]
        waiting = [r for r in runs if r.get("status") in ("queued", "pending", "waiting", "requested")]
        bot = self.st["stats"].setdefault("bot", {})
        if running:
            since = ts(self.main_job(running[0]["id"]).get("started_at"))
            bot.update(ok=True, since=since, at=now)
            self.st["off_since"] = self.st["wait_since"] = None
            self.fine("bot_down")
            self.fine("bot_queued")
            if "bot_loop" in self.st["issues"] and since and now - since >= 1800:     # it runs again for real
                self.st["crash_loop"], self.st["crashes"] = None, []
                self.fine("bot_loop")
            return
        bot.update(ok=False, since=None, at=now)
        if waiting:                                         # a run is waiting for a GitHub machine
            self.st["wait_since"] = self.st.get("wait_since") or now
            if now - self.st["wait_since"] > QUEUED_TOO_LONG:
                self.problem("bot_queued", "بوت الإشارات عالق بالدور على GitHub",
                             f"عم يستنى يبلّش من {dur(now - self.st['wait_since'])}. هيدا من عند GitHub (ضغط أو عطل)، "
                             "وأنا عم ضل شيّك.", ok="بوت الإشارات بلّش يشتغل", level="⚠️")
            return
        self.st["wait_since"] = None
        if self.st["stats"].get("wf_state", "active") != "active":
            return                                          # disabled: check_workflow() tells, nothing is started
        if not self.st.get("off_since"):
            ends = [ts(r["updated_at"]) for r in runs if r.get("status") == "completed"]
            self.st["off_since"] = min(max(ends, default=now), now)
        off = now - self.st["off_since"]
        if off < RESTART_GRACE or self.quiet:
            return
        if self.st.get("crash_loop"):
            sha = self.gh.head_sha()
            if sha == self.st.get("loop_sha") and now - self.st["crash_loop"] < CRASH_PAUSE:
                return                                      # bot_loop already told; wait for a fix
            log.info("crash loop: %s, trying again", "new commit" if sha != self.st.get("loop_sha") else "pause over")
            self.st["crash_loop"], self.st["crashes"], self.st["restart_reset"] = None, [], now
        recent = [t for t in self.st["restarts"] if now - t < RESTART_WINDOW and t >= self.st.get("restart_reset", 0)]
        if not AUTO_RESTART:
            detail = "الإرجاع التلقائي مطفّى (AUTO_RESTART=0)."
        elif len(recent) < MAX_RESTARTS:
            if self.dry:
                log.info("dry run: the bot is off since %s, it would be started now", dur(off))
                return
            if self.gh.dispatch(BOT_WF):
                self.st["restarts"].append(now)
                log.info("the bot was off for %s: started again", dur(off))
                if NOTIFY_RESTARTS:
                    self.say(f"🔄 بوت الإشارات كان واقف {dur(off)}، رجّعته يشتغل.")
                return
            self.check_workflow()                           # refused: maybe it was just disabled
            if self.st["stats"].get("wf_state", "active") != "active":
                return
            detail = "حاولت رجّعه يشتغل وGitHub رفض الطلب."
        else:
            detail = f"حاولت رجّعه {times(len(recent))} بآخر نص ساعة وما اشتغل."
        self.problem("bot_down", "بوت الإشارات واقف",
                     f"واقف من {dur(off)}. {detail}\nشوف GitHub › Actions › Phoenix HT Bot.",
                     ok="بوت الإشارات رجع يشتغل")

    def scan_finished(self, runs):
        """Every bot run that ended since the last round: crash? errors in its log?"""
        seen = self.st["seen"]
        first = not self.st.get("init")
        done = sorted((r for r in runs if r.get("status") == "completed" and r["id"] not in seen),
                      key=lambda r: r.get("created_at") or "")
        self.st["init"] = True
        for r in done:
            seen.append(r["id"])
            if not first:
                try:
                    self.finished_run(r)
                except requests.RequestException as e:
                    log.warning("run %s: %s", r["id"], e)
        if first and done:                                  # first watch ever: old runs are not news, the newest log
            try:                                            # only fills the report
                self.read_log(done[-1], alert=False)
            except requests.RequestException as e:
                log.warning("first log: %s", e)
        del seen[:-80]

    def finished_run(self, r):
        now = time.time()
        job = self.main_job(r["id"], done=True)
        if not job or not job.get("started_at"):
            return                                          # cancelled while waiting: it never ran
        start, end = ts(job["started_at"]), ts(job.get("completed_at")) or now
        ran = end - start
        if r.get("conclusion") == "failure":
            step = next((s.get("name") for s in job.get("steps") or [] if s.get("conclusion") == "failure"), "?")
            self.st["crashes"].append(end)
            recent = [t for t in self.st["crashes"] if now - t < CRASH_WINDOW]
            if len(recent) >= CRASH_LOOP:
                self.st["crash_loop"], self.st["loop_sha"] = now, r.get("head_sha")
                self.problem("bot_loop", "بوت الإشارات عم يوقع كل ما يشتغل",
                             f"وقع {times(len(recent))} بآخر ساعتين، آخر مرة بخطوة «{esc(step)}» بعد {dur(ran)}.\n"
                             "وقّفت رجّعه لحتى تنصلح المشكلة (بجرّب من جديد بس ينزل تعديل، أو بعد 3 ساعات).",
                             ok="بوت الإشارات رجع يشتغل طبيعي")
            else:
                self.say(f"⚠️ <b>بوت الإشارات وقع</b> ({clock(end)})\n"
                         f"اشتغل {dur(ran)} ووقف بخطوة «{esc(step)}»."
                         + ("\nعم رجّعه يشتغل هلق." if AUTO_RESTART else ""))
        if ran >= 120:
            self.read_log(r, job=job)

    def read_log(self, r, job=None, alert=True):
        job = job or self.main_job(r["id"], done=True)
        if not job:
            return
        res = scan_log(self.gh.job_log(job["id"]))
        start, end = ts(job.get("started_at")), ts(job.get("completed_at"))
        res.update(id=r["id"], end=end, ran=(end - start) if start and end else None)
        self.st["last_run"] = res
        if not alert:
            return
        rows = [f"• {label}: {times(n)}" for label, n, key in res["crit"]
                if not (key and key in self.st["issues"])
                and not (key == "tg_channel" and not self.sig.channel)]     # no channel wanted: not news
        if rows:
            when = f" ({clock(end)})" if end else ""
            self.say(f"⚠️ <b>ملاحظة من آخر تشغيلة للبوت</b>{when}\n" + "\n".join(rows))

    def check_workflow(self):
        self.later("workflow", EVERY["workflow"])
        state = self.gh.workflow(BOT_WF).get("state", "active")
        self.st["stats"]["wf_state"] = state
        if state == "active":
            self.fine("bot_off")
            return
        if state == "disabled_inactivity" and not (self.quiet or self.dry) and self.gh.enable(BOT_WF):
            self.st["stats"]["wf_state"] = "active"
            self.say("⚠️ <b>GitHub كان موقّف بوت الإشارات</b>\n"
                     "لأنه صرلك 60 يوم ما عدّلت شي بالريبو. رجّعت فتحته ✅")
            return
        if state == "disabled_manually":
            self.problem("bot_off", "بوت الإشارات موقّف يدوياً",
                         "حدا كبس «Disable workflow» عـ GitHub، فما رح رجّعه لحالي.\n"
                         "إذا مش قصدك: GitHub › Actions › Phoenix HT Bot › Enable workflow.",
                         ok="بوت الإشارات انفتح من جديد", level="⏸️", remind=86400, check="workflow")
        else:
            self.problem("bot_off", "GitHub موقّف بوت الإشارات",
                         f"حالته هلق: {esc(state)}.\nفوت عـ GitHub › Actions › Phoenix HT Bot › Enable workflow.",
                         ok="بوت الإشارات انفتح من جديد", check="workflow")

    def keepalive(self):
        """GitHub stops scheduled workflows after 60 days without a commit: an "enable" every week keeps them on."""
        self.later("keepalive", EVERY["keepalive"])
        if self.quiet or self.dry:
            return
        for wf in (BOT_WF, SELF_WF):
            try:
                if self.gh.workflow(wf).get("state") == "active":
                    self.gh.enable(wf)
            except requests.RequestException as e:
                log.warning("keepalive %s: %s", wf, e)

    # ── outside services
    def check_telegram(self):
        self.later("tg", EVERY["tg"])
        tgs = self.st["stats"].setdefault("tg", {})
        if self.own_bot:                                    # can the watchdog's own bot still talk?
            ok, res, code = self.tg.call("getMe", {})
            if ok:
                self.st["tg_dead"] = False
                self.flush()
            elif code in (401, 404):
                self.st["tg_dead"] = True
                self.tg.last_error = (code, str(res))
                log.error("TELEGRAM: the watchdog bot token (WATCHDOG_BOT_TOKEN) is refused (%s)", code)
                self.sender_trouble()
        ok, me, code = self.sig.call("getMe", {})           # the signal bot
        if not ok:
            if code in (401, 404):
                tgs.update(ok=False, text="توكن بوت الإشارات ما عاد شغال")
                if self.own_bot:                            # its own bot can still tell
                    self.problem("tg_token", "توكن بوت الإشارات ما عاد شغال",
                                 "تلغرام رافض التوكن، يعني ولا إشارة عم تطلع (لا عالقناة ولا عالخاص).\n"
                                 "اعمل توكن جديد من @BotFather (/token) وحطه بالـsecret اسمه TELEGRAM_BOT_TOKEN.",
                                 ok="بوت الإشارات رجع يشتغل عالتلغرام", confirm=2, check="tg")
                else:
                    self.st["tg_dead"] = True
                log.error("TELEGRAM: the signal bot token is refused (%s)", code)
            else:
                log.warning("TELEGRAM: getMe failed (%s %s)", code, me)
            return
        self.fine("tg_token")
        if not self.own_bot:
            self.st["tg_dead"] = False
            self.flush()
        if not self.sig.channel:                            # no channel: the bot sends to its subscribers only
            tgs.update(ok=True, text="بوت الإشارات شغّال وبيبعت عالخاص (بلا قناة)")
            self.st["issues"].pop("tg_channel", None)       # an old channel warning no longer applies: dropped quietly
            self.st["fails"].pop("tg_channel", None)
            return
        ok, m, code = self.sig.call("getChatMember", {"chat_id": self.sig.channel, "user_id": me["id"]})
        if not ok:
            why = ("البوت مش لاقي القناة. تأكد من شغلتين:\n"
                   "1. الـsecret اسمه TELEGRAM_CHAT_ID لازم يكون @اسم_القناة (أو رقمها اللي بيبلّش بـ -100 إذا القناة خاصة).\n"
                   "2. البوت مضاف عالقناة كأدمن مع صلاحية «نشر الرسائل».\n"
                   f"<code>{esc(str(m))}</code>")
        elif m.get("status") not in ("administrator", "creator"):
            why = "البوت مش أدمن بالقناة. رجّعه أدمن مع صلاحية «نشر الرسائل»."
        elif m.get("status") == "administrator" and m.get("can_post_messages") is False:
            why = "البوت أدمن بس ما عنده صلاحية «نشر الرسائل». فعّلها من إعدادات القناة."
        else:
            tgs.update(ok=True, text="البوت بينشر عادي")
            self.fine("tg_channel", "إذا البوت كان شغال وقت المشكلة، الإشارات بترجع عالقناة من تشغيلته الجاية.")
            return
        tgs.update(ok=False, text=why)
        self.problem("tg_channel", "الإشارات ما عم تنزل بالقناة", why, ok="البوت رجع يقدر ينشر بالقناة",
                     confirm=2, check="tg")

    def check_capital(self):
        self.later("capital", EVERY["capital"])
        res = self.probe_capital()
        self.st["stats"]["capital"] = {"kind": res["kind"], "bid": res.get("bid"), "at": time.time()}
        kind, why = res["kind"], esc(res.get("why", ""))
        if kind == "login":
            self.problem("capital", "الأسعار وقفت: Capital.com رافض الدخول",
                         "يمكن انتهت صلاحية مفتاح الـAPI أو تغيّرت كلمة السر. البوت ما عم توصله أسعار، "
                         f"يعني ما في إشارات لحتى ينصلح.\n<code>{why}</code>",
                         ok="الأسعار رجعت توصل من Capital.com", confirm=2)
        elif kind == "down":
            self.problem("capital", "Capital.com مش عم يرد",
                         f"ما قدرت وصل لسيرفر الأسعار. إذا طوّلت، البوت ما رح يطلّع إشارات.\n<code>{why}</code>",
                         ok="Capital.com رجع يرد", confirm=2, level="⚠️")
        elif kind == "stale":
            age = res.get("age")
            self.problem("capital", "أسعار الدهب واقفة",
                         f"السوق مفتوح بس آخر سعر وصل من {dur(age)}." if age else "السوق مفتوح بس ما عم يوصل ولا سعر.",
                         ok="أسعار الدهب رجعت تتحرك", confirm=2, level="⚠️")
        else:
            self.fine("capital")

    def check_web(self, key, url, name, ok):
        self.later(key, EVERY[key])
        res = self.probe_web(url)
        self.st["stats"][key] = {**res, "at": time.time()}
        if res["ok"]:
            self.fine(key)
            return
        if res.get("why") == "timeout":
            why = "ما فتح خلال دقيقتين."
        elif res.get("code"):
            why = f"فتح بخطأ {res['code']}."
        else:
            why = f"ما قدرت وصله ({esc(str(res.get('why')))})."
        if res.get("suspended"):
            why += "\nRender موقّف الخدمة: يمكن خلصت الساعات المجانية لهالشهر، أو انوقفت من الحساب."
        self.problem(key, f"{name} مش عم يفتح", why, ok=ok, confirm=2)

    # ── one round, the report
    def tick(self, report=False):
        if self.outbox and not self.quiet:                  # messages Telegram did not take before
            self.flush()
        self.hello()
        try:
            self.check_bot()
            self.st["gh_fails"] = 0
            self.fine("github")
        except requests.RequestException as e:             # GitHub's API did not answer: the rest still runs
            self.st["gh_fails"] = self.st.get("gh_fails", 0) + 1
            log.warning("GitHub API: %s", e)
            if self.st["gh_fails"] >= 3:
                self.problem("github", "ما عم قدر شوف البوت عـ GitHub",
                             "الـAPI تبع GitHub مش عم يرد من ربع ساعة. يمكن عطل عندهن (githubstatus.com).",
                             ok="رجعت شوف البوت عـ GitHub", level="⚠️")
        except Exception:
            log.exception("bot check failed")
        checks = [("workflow", self.check_workflow), ("tg", self.check_telegram), ("capital", self.check_capital),
                  ("keepalive", self.keepalive)]
        if self.app_url:
            checks.append(("app", lambda: self.check_web("app", self.app_url, "تطبيق Phoenix HT Trading",
                                                         "التطبيق رجع يفتح")))
        if self.link_url:
            checks.append(("link", lambda: self.check_web("link", self.link_url, "صفحة الروابط",
                                                          "صفحة الروابط رجعت تفتح")))
        for key, fn in checks:
            if report or self.due(key):
                try:
                    fn()
                except Exception as e:
                    log.warning("%s check failed: %s", key, e)
        if not report:
            try:
                self.morning()
            except Exception as e:
                log.warning("morning report failed: %s", e)

    def morning(self):
        now = local_now()
        hh, mm = (int(x) for x in MORNING_AT.split(":"))
        if self.st.get("morning") == now.date().isoformat() or (now.hour, now.minute) < (hh, mm):
            return
        self.st["morning"] = now.date().isoformat()
        self.say(self.report())

    def uptime(self, hours=24):
        """Share of the last `hours` with a bot run going (from the runs' own start and end times)."""
        now = time.time()
        start = now - hours * 3600
        spans = []
        for r in self.gh.runs(BOT_WF, 30):
            if r.get("status") == "completed" and (ts(r.get("updated_at")) or 0) < start:
                continue
            job = self.main_job(r["id"], done=r.get("status") == "completed")
            if not job or not job.get("started_at"):
                continue
            s, e = ts(job["started_at"]), ts(job.get("completed_at")) or now
            if e > start:
                spans.append((max(s, start), min(e, now)))
        total, cur = 0.0, None
        for s, e in sorted(spans):
            if cur and s <= cur[1]:
                cur[1] = max(cur[1], e)
                continue
            if cur:
                total += cur[1] - cur[0]
            cur = [s, e]
        if cur:
            total += cur[1] - cur[0]
        return total / (hours * 3600)

    def report(self):
        now, d, S = time.time(), local_now(), self.st["stats"]
        out = [f"🛡️ <b>تقرير المراقب · {DAYS[d.weekday()]} {d.day}/{d.month}</b>", ""]
        b = S.get("bot", {})
        if S.get("wf_state", "active") != "active":
            out.append("🤖 بوت الإشارات: ⏸️ موقّف من GitHub")
        elif not b:
            out.append("🤖 بوت الإشارات: ⚪ ما قدرت شيّك عليه (GitHub ما ردّ)")
        elif b.get("ok"):
            out.append("🤖 بوت الإشارات: ✅ شغال" + (f" (من {dur(now - b['since'])})" if b.get("since") else ""))
        else:
            out.append("🤖 بوت الإشارات: 🔴 واقف هلق")
        try:
            up = self.uptime()
            out.append(f"   ⏱️ آخر 24 ساعة: كان شغال {round(up * 100)}% من الوقت")
        except Exception as e:
            log.warning("uptime: %s", e)
        r24 = sum(1 for t in self.st["restarts"] if now - t < 86400)
        if r24:
            out.append(f"   🔄 رجّعته يشتغل {times(r24)} لما وقف")
        c24 = sum(1 for t in self.st["crashes"] if now - t < 86400)
        if c24:
            out.append(f"   💥 وقع {times(c24)}")
        t = S.get("tg")
        if t:
            out.append("📣 تلغرام: " + {True: "✅ ", False: "🔴 ", None: "⚪ "}[t.get("ok")] + t.get("text", ""))
        c = S.get("capital")
        if c:
            bid = c.get("bid")
            gold = f" · الدهب {bid:,.2f}" if isinstance(bid, (int, float)) else ""
            out.append("💹 الأسعار (Capital.com): " + {
                "ok": "✅ واصلة" + gold,
                "closed": "😴 السوق مسكّر هلق" + gold,
                "stale": "⚠️ واقفة والسوق مفتوح",
                "login": "🔴 Capital.com رافض الدخول",
                "down": "⚠️ Capital.com مش عم يرد",
                "off": "⚪ ما في مفتاح Capital.com"}.get(c.get("kind"), "⚪ ما انفحصت"))
        for key, label, url in (("app", "📱 التطبيق", self.app_url), ("link", "🔗 صفحة الروابط", self.link_url)):
            w = S.get(key)
            if not url:
                if key == "app":
                    out.append(f"{label}: ⚪ ما بعرف رابطه (زيد secret اسمه APP_URL)")
                continue
            if not w:
                continue
            sec = round(w.get("sec") or 0)
            took = count_ar(sec, "ثانية", "ثانيتين", "ثواني", "ثانية") if sec >= 1 else "أقل من ثانية"
            out.append(f"{label}: " + (f"✅ شغال (فتح بـ{took})" if w.get("ok") else "🔴 مش عم يفتح"))
        lr = self.st.get("last_run")
        if lr:
            line = f"🧾 آخر تشغيلة للبوت: {lr.get('err', 0)} خطأ · {lr.get('warn', 0)} تحذير"
            for label, n, _ in lr.get("crit") or []:          # the serious ones first
                line += f"\n   ❗ {label} ({times(n)})"
            if lr.get("top") and not lr.get("crit"):
                text, n = lr["top"][0]
                line += f"\n   أكتر شي تكرر: <code>{esc(text)}</code> ×{n}"
            out.append(line)
        out.append("")
        problems = [f"• {iss['title']} (من {dur(now - iss['since'])})" for iss in self.st["issues"].values()]
        if (b and not b.get("ok") and S.get("wf_state", "active") == "active"
                and not any(k in self.st["issues"] for k in ("bot_down", "bot_loop", "bot_queued"))):
            problems.insert(0, "• بوت الإشارات واقف هلق، وعم رجّعه يشتغل")
        if problems:
            out += ["⚠️ <b>لسا في مشاكل مفتوحة:</b>"] + problems
        elif any(("🔴" in x or "⚠️" in x) for x in out):
            out.append("⚠️ <b>في شي مش طبيعي فوق، وعم شيّك عليه مرة تانية</b>")
        else:
            out.append("✅ <b>كل شي تمام</b>")
        if not self.own_bot:
            out.append("\n💡 <i>هالرسائل عم توصل من بوت الإشارات. لتكون بشات لحالها: بوت جديد من @BotFather "
                       "وتوكنه بـ secret اسمه WATCHDOG_BOT_TOKEN.</i>")
        return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="Phoenix Watchdog: watches the bot and its services, tells the owner")
    ap.add_argument("--minutes", type=float, default=0, help="keep watching this many minutes (GitHub Actions: 340)")
    ap.add_argument("--report", action="store_true", help="one round of checks, send the status report now, stop")
    ap.add_argument("--dry-run", action="store_true", help="print the messages instead of sending, start nothing")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    chat, source = owner_chat()
    channel = clean_chat(ENV("TELEGRAM_CHAT_ID"))
    sig = Telegram(clean_token(ENV("TELEGRAM_BOT_TOKEN")), chat, channel, dry=a.dry_run)     # the signal bot
    own = clean_token(ENV("WATCHDOG_BOT_TOKEN"))                                             # the watchdog's own bot
    tg = Telegram(own, chat, channel, dry=a.dry_run) if own else sig
    log.info("messages go to: %s, from %s", source or "nobody yet (add the secret WATCHDOG_CHAT_ID)",
             "the watchdog's own bot" if own else "the signal bot (no WATCHDOG_BOT_TOKEN yet)")
    wd = Watchdog(GitHub(ENV("GITHUB_TOKEN") or ""), tg, quiet=a.report, dry=a.dry_run, sig=sig)

    if a.report:
        wd.tick(report=True)
        sent = tg.send(wd.report())
        if not sent:
            wd.sender_trouble()
        return 0 if sent else 1

    t0 = time.time()
    end = t0 + a.minutes * 60
    while True:
        t = time.time()
        try:
            wd.tick()
        except Exception:
            log.exception("round failed")
        wd.save()
        left = end - time.time()
        if not a.minutes or left <= 0:
            break
        time.sleep(max(5.0, min(TICK - (time.time() - t), left)))
    if a.minutes and time.time() - t0 >= CHAIN_AFTER:
        write_output("chain", "1")
    if not chat or wd.st.get("tg_dead") or wd.outbox:
        log.error("messages could not reach you (%d waiting): check WATCHDOG_BOT_TOKEN (and Start on that bot), "
                  "TELEGRAM_BOT_TOKEN or WATCHDOG_CHAT_ID", len(wd.outbox))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
