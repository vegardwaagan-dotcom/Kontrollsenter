"""Utseendet i chatten: profilbilder (initialer i egen farge), datoskiller, store emojier, chatbakgrunner,
Ikke forstyrr og spillstatus. Brukes av chat_ui.py (PC) – samme regler i mobilappen (remote_web/chat.js).
"""
import hashlib
import re
import time

PALETTE = ["#ff6b6b", "#ff9f43", "#feca57", "#1dd1a1", "#48dbfb", "#54a0ff", "#5f27cd", "#c56cf0",
           "#ff6bcb", "#10ac84", "#2e86de", "#ee5253"]

# chatbakgrunner (nøkkel -> (navn, CSS-bakgrunn)); «bilde» bruker et eget bilde
BACKGROUNDS = {
    "": ("Ingen", "none"),
    "nordlys": ("Nordlys", "radial-gradient(ellipse at 10% 0%, alpha(#2ef2b3,0.30), transparent 60%), "
                           "radial-gradient(ellipse at 100% 30%, alpha(#7c5cff,0.28), transparent 60%)"),
    "solnedgang": ("Solnedgang", "linear-gradient(180deg, alpha(#ff8a3d,0.22), alpha(#ff3d7f,0.18) 60%, "
                                 "alpha(#3a1c71,0.20))"),
    "hav": ("Dyphav", "linear-gradient(200deg, alpha(#00c2ff,0.22), alpha(#3a5bff,0.16) 70%)"),
    "galakse": ("Galakse", "radial-gradient(ellipse at 80% 10%, alpha(#c86bff,0.30), transparent 55%), "
                           "radial-gradient(ellipse at 10% 90%, alpha(#ff5fa2,0.22), transparent 55%)"),
    "skog": ("Skog", "linear-gradient(160deg, alpha(#5bd68a,0.20), alpha(#0a130d,0.10) 70%)"),
    "lava": ("Lava", "radial-gradient(ellipse at 50% 120%, alpha(#ff4d1a,0.35), transparent 65%)"),
}

_EMOJI_RE = re.compile(
    "^(?:[\U0001F000-\U0001FAFF☀-➿⬀-⯿⌀-⏿️‍\U0001F3FB-\U0001F3FF]|"
    "[\U0001F1E6-\U0001F1FF]{2})+$")


def color_for(name):
    """Fast farge per person (samme på alle PC-ene og mobilen)."""
    h = int(hashlib.md5(str(name or "?").lower().encode()).hexdigest()[:6], 16)
    return PALETTE[h % len(PALETTE)]


def initials(name):
    parts = [p for p in re.split(r"[\s\-_.]+", str(name or "?").strip()) if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


def emoji_count(text):
    """Antall emojier hvis meldingen BARE er emojier (1–3 vises stort), ellers 0."""
    t = str(text or "").replace(" ", "")
    if not t or len(t) > 24 or not _EMOJI_RE.match(t):
        return 0
    n = len([c for c in t if ord(c) > 0x2300 and c not in "️‍" and not 0x1F3FB <= ord(c) <= 0x1F3FF])
    return n if 1 <= n <= 3 else 0


def day_label(t, now=None):
    now = now or time.time()
    d = time.localtime(t)
    today = time.localtime(now)
    days = (time.mktime(today[:3] + (0, 0, 0, 0, 0, -1)) - time.mktime(d[:3] + (0, 0, 0, 0, 0, -1))) / 86400
    if days < 0.5:
        return "I dag"
    if days < 1.5:
        return "I går"
    names = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"]
    months = ["jan.", "feb.", "mars", "april", "mai", "juni", "juli", "aug.", "sep.", "okt.", "nov.", "des."]
    s = f"{names[d.tm_wday]} {d.tm_mday}. {months[d.tm_mon - 1]}"
    return s if d.tm_year == today.tm_year else f"{s} {d.tm_year}"


# --------------------------------------------------------------------------
# Ikke forstyrr
# --------------------------------------------------------------------------
def dnd_active(win=None):
    """Er Ikke forstyrr på nå? (manuelt med tid, eller automatisk mens du spiller)"""
    import chatplus
    c = chatplus.cfg()
    if c.get("dnd_until", 0) > time.time():
        return True
    if c.get("dnd_game") and win is not None and getattr(getattr(win, "bg", None), "game_name", None):
        return True
    return False


def set_dnd(hours):
    """hours: 0 = av, -1 = til i morgen kl. 07, ellers antall timer."""
    import chatplus
    if hours == 0:
        until = 0
    elif hours == -1:
        lt = time.localtime()
        until = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday + (1 if lt.tm_hour >= 7 else 0), 7, 0, 0, 0, 0, -1))
    else:
        until = time.time() + hours * 3600
    chatplus.set_(dnd_until=until)
    return until


def dnd_text():
    import chatplus
    u = chatplus.cfg().get("dnd_until", 0)
    if u <= time.time():
        return ""
    return "Ikke forstyrr til " + time.strftime("%H:%M" if u - time.time() < 20 * 3600 else "%d.%m %H:%M",
                                               time.localtime(u))
