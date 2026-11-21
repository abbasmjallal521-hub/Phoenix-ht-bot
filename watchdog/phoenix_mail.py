"""مدير الإيميلات · Phoenix Mail: the owner's Gmail, read for the watchdog (headers only, nothing changed).

Every 10 minutes the watchdog asks for the emails that came since its last look. The serious ones go to the owner at
once on Telegram; the rest are counted for the morning report. Serious: Google security alerts, GitHub alerts and
sign-ins (and failed runs of the other repos: the bot's own runs are already watched), Render deploys that fail or
services that stop, Firebase and Google Cloud warnings, Capital.com and OneRoyal account emails (margin, withdrawals,
security), and security words from anyone. A sender counts as real only when Gmail checked it (DMARC, or DKIM for the
sender's own domain); the others are marked, because they may be phishing.

Only the headers are read (from, subject, date, Gmail's sender check), with BODY.PEEK on a mailbox opened read-only:
nothing is marked as read, moved or deleted. The log never holds a sender or a subject: the repo is public.

Two secrets turn it on: GMAIL_ADDRESS and GMAIL_APP_PASSWORD (a Google app password, made at
myaccount.google.com/apppasswords with 2-Step Verification on). MAIL_WATCH (optional): more domains whose every
email is serious, comma separated.
"""
import email
import imaplib
import os
import re
from email.policy import default as POLICY
from email.utils import parseaddr, parsedate_to_datetime

HOST = os.environ.get("GMAIL_IMAP") or "imap.gmail.com"
BATCH = 40                      # headers fetched in one request
MAX_NEW = 200                   # a flood: only the newest 200 are read, the others are only counted
FIELDS = "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE AUTHENTICATION-RESULTS)])"

ACCOUNT = (r"margin|stop.?out|liquidat|withdraw|deposit|verif|security|password|log.?in|sign.?in|suspend|restrict|"
           r"block|kyc|document|funds|closed|api key")
SENDERS = (   # label, the sender's domains (or full addresses), what in the subject makes it serious (None: all)
    ("Google · أمان الحساب", ("accounts.google.com",), None),
    ("GitHub", ("github.com",), r"security|alert|dependabot|vulnerab|token|sign.?in|verif|password|two.?factor|2fa|"
                               r"ssh key|deploy key|oauth|suspend|disabled|run failed|all jobs have failed|billing|payment"),
    ("Render", ("render.com",), r"fail|suspend|down|usage|limit|exceed|billing|payment|invoice|error|crash|unhealthy|hours"),
    ("Firebase", ("firebase.google.com", "firebase-noreply@google.com"),
     r"insecure|rules|security|billing|quota|limit|exceed|expir|suspend|delet|test mode|disabled|alert"),
    ("Google Cloud", ("cloud.google.com", "cloudplatform-noreply@google.com", "google-cloud-noreply@google.com"),
     r"billing|quota|security|suspend|alert|expir|budget|payment|disabled|exceed"),
    ("Capital.com", ("capital.com",), ACCOUNT),
    ("OneRoyal", ("oneroyal.com",), ACCOUNT + r"|account|credential"),
    ("TradingView", ("tradingview.com",), r"security|password|sign.?in|log.?in|suspend|payment|billing|subscription|expir"),
    ("Telegram", ("telegram.org",), None),
)
ANYONE = re.compile(r"security alert|unusual (?:activity|sign)|suspicious|suspended|compromis|unauthori[sz]ed|"
                    r"password (?:was |has been )?changed|new sign.?in|account (?:has been |was )?(?:locked|disabled|closed)|"
                    r"تنبيه أمان|نشاط مريب|تعليق حسابك|كلمة المرور|تسجيل دخول جديد", re.I)
RUN_MAIL = re.compile(r"run failed|run cancelled|all jobs have failed", re.I)


class LoginError(Exception):
    """Gmail refused the address or the app password."""


def domain_of(addr):
    return (addr or "").rpartition("@")[2].lower().strip("> ")


def is_from(addr, entries):
    addr, dom = (addr or "").lower(), domain_of(addr)
    return any(addr == e if "@" in e else (dom == e or dom.endswith("." + e)) for e in entries)


def verified(auth, addr):
    """Gmail's own check of the sender: DMARC passed, or DKIM passed for the sender's own domain."""
    a = (auth or "").lower()
    if "dmarc=pass" in a:
        return True
    dom = domain_of(addr)
    return any(dom == d or dom.endswith("." + d) for d in re.findall(r"dkim=pass[^;]*?header\.[di]=@?([a-z0-9.-]+)", a))


def label_of(name, addr):
    for label, entries, _ in SENDERS:
        if is_from(addr, entries):
            return label.split(" · ")[0]
    return ((name or "").strip() or domain_of(addr) or "؟")[:30]


def classify(name, addr, subject, auth, watched_repo="", extra=()):
    """None (not serious) or {"label", "real", "unknown"}: real = Gmail checked the sender is who it says."""
    subj, real = subject or "", verified(auth, addr)
    for d in extra:
        if is_from(addr, (d,)):
            return {"label": d, "real": real, "unknown": False}
    for label, entries, words in SENDERS:
        if is_from(addr, entries):
            if label == "GitHub" and RUN_MAIL.search(subj) and watched_repo and watched_repo.lower() in subj.lower():
                return None                                   # the watchdog already watches this repo's runs
            if words is None or re.search(words, subj, re.I) or ANYONE.search(subj):
                return {"label": label, "real": real, "unknown": False}
            return None
    if ANYONE.search(subj):
        return {"label": label_of(name, addr), "real": False, "unknown": True}
    return None


def read_header(raw):
    """Header bytes -> {name, addr, subject, auth, when}, or None when they cannot be read."""
    try:
        msg = email.message_from_bytes(raw, policy=POLICY)
        subject = " ".join(str(msg.get("Subject") or "").split())
        name, addr = parseaddr(str(msg.get("From") or ""))
        auths = [str(a) for a in (msg.get_all("Authentication-Results") or [])]
    except Exception:
        return None
    try:
        when = parsedate_to_datetime(str(msg.get("Date"))).timestamp()
    except Exception:
        when = None
    auth = next((a for a in auths if a.strip().lower().startswith("mx.google.com")), "")   # Gmail's own, on top
    return {"name": name.strip(), "addr": addr.strip().lower(), "subject": subject[:200], "auth": auth, "when": when}


class MailWatch:
    """The mail check the watchdog runs. `memory`: the "mail" part of the watchdog's saved memory."""

    def __init__(self, address, password, memory, repo="", extra=None, connect=None):
        self.address = (address or "").strip()
        self.password = re.sub(r"\s+", "", password or "")    # Google shows it in groups of 4: spaces don't matter
        self.mem = memory
        self.repo = repo
        self.extra = [d.strip().lower() for d in (extra or "").split(",") if d.strip()]
        self.connect = connect or (lambda: imaplib.IMAP4_SSL(HOST, 993, timeout=40))

    @property
    def on(self):
        return bool(self.address and self.password)

    def count(self, label, serious=False, n=1):
        d = self.mem.setdefault("digest", {"n": 0, "serious": 0, "by": {}})
        d["n"] += n
        d["serious"] += n if serious else 0
        d["by"][label] = d["by"].get(label, 0) + n

    def check(self):
        """-> (serious emails, how many came, first look). The first look only marks where the inbox is."""
        box = self.connect()
        try:
            try:
                box.login(self.address, self.password)
            except imaplib.IMAP4.error:
                raise LoginError() from None
            _, data = box.status("INBOX", "(UIDNEXT UIDVALIDITY)")
            text = (data[0] or b"").decode("ascii", "replace") if data else ""
            nxt = int(re.search(r"UIDNEXT (\d+)", text).group(1))
            uidv = int(re.search(r"UIDVALIDITY (\d+)", text).group(1))
            if self.mem.get("uidv") != uidv or "next" not in self.mem:
                self.mem.update(uidv=uidv, next=nxt)
                return [], 0, True
            start = self.mem["next"]
            if nxt <= start:
                return [], 0, False
            box.select("INBOX", readonly=True)
            _, data = box.uid("SEARCH", None, f"UID {start}:*")
            uids = sorted(u for u in (int(x) for x in ((data[0] if data else b"") or b"").split()) if u >= start)
            came, found = len(uids), []
            if came > MAX_NEW:
                self.count("غيرهن", n=came - MAX_NEW)
                uids = uids[-MAX_NEW:]
            for i in range(0, len(uids), BATCH):
                _, data = box.uid("FETCH", ",".join(map(str, uids[i:i + BATCH])), FIELDS)
                for item in data or []:
                    if not isinstance(item, tuple):
                        continue
                    one = read_header(item[1])
                    if one is None:
                        self.count("؟")
                        continue
                    hit = classify(one["name"], one["addr"], one["subject"], one["auth"], self.repo, self.extra)
                    self.count(hit["label"].split(" · ")[0] if hit else label_of(one["name"], one["addr"]), bool(hit))
                    if hit:
                        found.append({**one, **hit})
            self.mem["next"] = max(nxt, uids[-1] + 1 if uids else start)
            return found, came, False
        finally:
            try:
                box.logout()
            except Exception:
                pass
