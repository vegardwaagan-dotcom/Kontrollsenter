"""Chat-funksjoner (runde 2): talemeldinger med lydbølge, lenkeforhåndsvisning med bilde, /-kommandoer, GIF-søk,
sikkerhetskopi av chatten til NAS-en og «spiller nå» med tid. Samme på Linux og Windows (GStreamer i prosessen).
"""
import hashlib
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request

CACHE = os.path.expanduser("~/.cache/systemmonitor/lenker")

# --------------------------------------------------------------------------
# Talemeldinger med lydbølge (GStreamer: virker likt på Linux og Windows, ingen FFmpeg)
# --------------------------------------------------------------------------
_REC = {"pipe": None, "path": None, "t": 0, "levels": []}
SRC = "autoaudiosrc"                                      # testene bruker en testtone i stedet for mikrofonen


def rec_available():
    try:
        import gi
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst
        Gst.init(None)
        return all(Gst.ElementFactory.find(n) for n in ("autoaudiosrc", "level", "opusenc", "oggmux"))
    except (ValueError, ImportError):
        return False


def rec_start():
    import gi
    gi.require_version("Gst", "1.0")
    from gi.repository import Gst
    Gst.init(None)
    import chatplus
    os.makedirs(chatplus.FILES, exist_ok=True)
    path = os.path.join(chatplus.FILES, f"tale-{int(time.time())}.ogg")
    pipe = Gst.parse_launch(
        f"{SRC} ! audioconvert ! audioresample ! audio/x-raw,channels=1,rate=48000 ! "
        "level interval=50000000 post-messages=true ! audioconvert ! opusenc bitrate=32000 ! oggmux ! "
        f"filesink location=\"{path}\"")
    _REC.update(pipe=pipe, path=path, t=time.time(), levels=[])
    bus = pipe.get_bus()
    bus.add_signal_watch()

    def on_msg(_b, msg):
        if msg.type == Gst.MessageType.ELEMENT and msg.get_structure().get_name() == "level":
            try:
                rms = msg.get_structure().get_value("rms")
                _REC["levels"].append(max(rms) if rms else -60.0)
            except (TypeError, ValueError):
                pass
    bus.connect("message", on_msg)
    if pipe.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
        _REC["pipe"] = None
        raise RuntimeError("fant ingen mikrofon")
    return True


def rec_level():
    """Siste nivå 0–1 (for å vise at mikrofonen hører deg mens du tar opp)."""
    lv = _REC["levels"][-1] if _REC["levels"] else -60
    return max(0.0, min(1.0, (lv + 50) / 45))


def recording():
    return _REC["pipe"] is not None


def wave(levels, n=40):
    """dB-nivåer -> n søyler 0–9."""
    if not levels:
        return [0] * n
    step = max(1, len(levels) / n)
    out = []
    for i in range(n):
        chunk = levels[int(i * step):int((i + 1) * step)] or [levels[-1]]
        db = max(chunk)
        out.append(int(max(0, min(9, round((db + 50) / 45 * 9)))))
    return out


def rec_stop():
    """Stopp opptaket. Returnerer (sti, bølge, sekunder) eller None hvis for kort."""
    from gi.repository import Gst
    pipe, path = _REC["pipe"], _REC["path"]
    _REC["pipe"] = None
    if pipe is None:
        return None
    secs = time.time() - _REC["t"]
    pipe.send_event(Gst.Event.new_eos())
    pipe.get_bus().timed_pop_filtered(2 * Gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
    pipe.set_state(Gst.State.NULL)
    if secs < 0.7 or not os.path.exists(path) or os.path.getsize(path) < 500:
        return None
    return path, wave(_REC["levels"]), round(secs, 1)


def rec_cancel():
    from gi.repository import Gst
    pipe, path = _REC["pipe"], _REC["path"]
    _REC["pipe"] = None
    if pipe is not None:
        pipe.set_state(Gst.State.NULL)
        try:
            os.remove(path)
        except OSError:
            pass


def send_voice(room, path, wv, secs, notify=None):
    import base64
    import chat
    import chatplus
    data = open(path, "rb").read()
    _p, sha = chatplus.store_file(os.path.basename(path), data)
    att = {"name": os.path.basename(path), "size": len(data), "sha": sha, "kind": "audio", "wave": wv,
           "secs": secs, "data": base64.b64encode(data).decode()}
    return chat.send(room, f"🎙️ Talemelding ({int(secs)} s)", None, notify, extra={"attach": att})


# --------------------------------------------------------------------------
# Lenkeforhåndsvisning med bilde
# --------------------------------------------------------------------------
_PREV = {}


def _local(url):
    host = urllib.parse.urlparse(url).hostname or ""
    return bool(re.match(r"^(127\.|192\.168\.|10\.|100\.|172\.(1[6-9]|2\d|3[01])\.|localhost)", host)) or \
        not host or "." not in host


def link_preview(url):
    """{title, desc, site, image (filsti eller None)} – mellomlagret. Aldri for adresser på hjemmenettet."""
    if url in _PREV:
        return _PREV[url]
    if _local(url) or not url.startswith(("http://", "https://")):
        _PREV[url] = None
        return None
    out = None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Kontrollsenter"})
        with urllib.request.urlopen(req, timeout=6) as r:
            if "html" not in (r.headers.get("Content-Type") or ""):
                raise ValueError("ikke en nettside")
            html = r.read(200000).decode("utf-8", "replace")
        import html as H

        def meta(*names):
            for n in names:
                m = re.search(r'<meta[^>]+(?:property|name)=["\']' + re.escape(n) +
                              r'["\'][^>]+content=["\']([^"\']+)', html, re.I) or \
                    re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']' +
                              re.escape(n) + r'["\']', html, re.I)
                if m:
                    return H.unescape(m.group(1)).strip()
            return None
        title = meta("og:title", "twitter:title")
        if not title:
            m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
            title = H.unescape(m.group(1)).strip() if m else None
        out = {"title": (title or "")[:120], "desc": (meta("og:description", "description") or "")[:200],
               "site": (meta("og:site_name") or urllib.parse.urlparse(url).hostname or "")[:60], "image": None}
        img = meta("og:image", "twitter:image")
        if img:
            out["image"] = _fetch_image(urllib.parse.urljoin(url, img))
    except Exception:  # noqa: BLE001
        out = None
    _PREV[url] = out
    return out


def _fetch_image(url):
    if _local(url):
        return None
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, hashlib.sha1(url.encode()).hexdigest()[:16])
    if os.path.exists(path):
        return path
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Kontrollsenter"})
        with urllib.request.urlopen(req, timeout=6) as r:
            if not (r.headers.get("Content-Type") or "").startswith("image/"):
                return None
            data = r.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            return None
        with open(path, "wb") as f:
            f.write(data)
        return path
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------
# GIF-søk (Tenor – gratis nøkkel fra Google, legges inn én gang)
# --------------------------------------------------------------------------
def gif_key():
    import chatplus
    return chatplus.cfg().get("tenor_key") or ""


def gif_search(q, limit=16):
    """[(forhåndsvisning-fil, gif-adresse)] – tom liste hvis ingen nøkkel."""
    key = gif_key()
    if not key:
        return []
    url = ("https://tenor.googleapis.com/v2/search?" +
           urllib.parse.urlencode({"q": q, "key": key, "limit": limit, "media_filter": "tinygif,gif",
                                   "contentfilter": "medium", "client_key": "kontrollsenter"}))
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Kontrollsenter"}),
                                timeout=8) as r:
        j = json.load(r)
    out = []
    for it in j.get("results", []):
        f = it.get("media_formats", {})
        tiny, big = (f.get("tinygif") or {}).get("url"), (f.get("gif") or {}).get("url")
        if tiny and big:
            out.append((tiny, big))
    return out


def gif_file(url):
    """Last ned en GIF (for å vise den / sende den som bilde)."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, hashlib.sha1(url.encode()).hexdigest()[:16] + ".gif")
    if not os.path.exists(path):
        req = urllib.request.Request(url, headers={"User-Agent": "Kontrollsenter"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = r.read(8 * 1024 * 1024 + 1)
        if len(data) > 8 * 1024 * 1024:
            raise ValueError("GIF-en er for stor")
        with open(path, "wb") as f:
            f.write(data)
    return path


# --------------------------------------------------------------------------
# /-kommandoer
# --------------------------------------------------------------------------
COMMANDS = [
    ("/poll", "Spørsmål | valg 1 | valg 2", "Avstemning med knapper"),
    ("/påminn", "20:00 raid", "Påminnelse til deg (og varsel i kanalen)"),
    ("/terning", "[sider]", "Kast terning (6 sider om ikke annet)"),
    ("/spill", "[spill]", "«Bli med i …»-kort for spillet du spiller"),
    ("/gif", "søkeord", "Søk etter en GIF"),
    ("/skjerm", "", "Del skjermen din"),
    ("/status", "tekst", "Sett statusmeldingen din (tom = fjern)"),
    ("/stille", "[timer]", "Ikke forstyrr (0 = av)"),
    ("@ai", "spørsmål", "AI-en din svarer i chatten (Claude, Codex, Gemini eller lokal)"),
    ("/hjelp", "", "Vis alle kommandoene"),
]


def command(room, text, win=None, notify=None):
    """Kjør en /-kommando. Returnerer (ferdig_tekst, spesial) – spesial = ("gif", søk) når UI-en må hjelpe til.
    (None, None) hvis teksten ikke er en kommando."""
    if not text.startswith("/"):
        return None, None
    cmd, _sp, arg = text.partition(" ")
    cmd, arg = cmd.lower(), arg.strip()
    import chatplus
    if cmd in ("/hjelp", "/help", "/?"):
        return "\n".join(f"{c} {a}".strip() + f" – {d}" for c, a, d in COMMANDS), None
    if cmd == "/poll":
        parts = [p.strip() for p in arg.split("|") if p.strip()]
        if len(parts) < 3:
            return "Skriv: /poll Spørsmål | valg 1 | valg 2", None
        return chatplus.send_poll(room, parts[0], parts[1:6], notify), None
    if cmd in ("/påminn", "/paminn", "/remind"):
        m = re.match(r"(\S+)\s+(.+)", arg)
        if not m:
            return "Skriv: /påminn 20:00 raid", None
        return chatplus.remind(room, m.group(2), m.group(1)), None
    if cmd in ("/terning", "/dice", "/roll"):
        sides = int(arg) if arg.isdigit() and 2 <= int(arg) <= 1000 else 6
        return chatplus.dice(room, sides, notify), None
    if cmd in ("/spill", "/play"):
        game = arg or (getattr(getattr(win, "bg", None), "game_name", None) if win else None)
        if not game:
            return "Skriv: /spill Navn på spillet", None
        import chatlink
        return chatlink.send_play(room, game, notify), None
    if cmd == "/gif":
        return None, ("gif", arg)
    if cmd in ("/skjerm", "/screen"):
        import chatlink
        return chatlink.share_screen(room, notify), None
    if cmd == "/status":
        chatplus.set_(status=arg[:80])
        try:
            import chatlink
            chatlink.broadcast_presence(win)
        except Exception:  # noqa: BLE001
            pass
        return ("Status: " + arg) if arg else "Statusen er fjernet", None
    if cmd in ("/stille", "/dnd"):
        import chatlook
        h = float(arg.replace(",", ".")) if re.match(r"^\d+([.,]\d+)?$", arg) else 1
        chatlook.set_dnd(h)
        return (chatlook.dnd_text() or "Ikke forstyrr er av"), None
    return f"Ukjent kommando {cmd} – skriv /hjelp", None


# --------------------------------------------------------------------------
# Sikkerhetskopi av chatten til NAS-en (én om dagen, de siste 14 beholdes)
# --------------------------------------------------------------------------
STATE = os.path.expanduser("~/.local/share/systemmonitor/chat-backup.json")


def backup_due():
    try:
        with open(STATE) as f:
            return time.time() - json.load(f).get("t", 0) > 20 * 3600
    except (OSError, ValueError):
        return True


def backup_to_nas():
    """Legg samtaler, servere og chat-valg i Kontrollsenter/Chat-backup/<PC>/<dato>/ på NAS-en."""
    import chat
    import chatplus
    import chatsrv
    import lanupdate as L
    import savegames
    if not L.on_lan():
        return False, "NAS-en svarer ikke"
    day = time.strftime("%Y-%m-%d")
    pc = re.sub(r"[^\w.-]", "_", savegames.pc_name())
    _h, _s, folder = L._split()
    base = f"{folder}/Chat-backup"
    L.smb_mkdir(base)
    L.smb_mkdir(f"{base}/{pc}")
    L.smb_mkdir(f"{base}/{pc}/{day}")
    files = {n: p for n, p in (("rom.json", chat.FILE), ("servere.json", chatsrv.FILE),
                                ("pluss.json", chatplus.CFG)) if os.path.exists(p)}
    cmds = "; ".join(f'put "{p}" "{n}"' for n, p in files.items())    # _smb virker også på Windows
    L._smb(f'cd "Chat-backup/{pc}/{day}"; {cmds}', 120)
    _prune(pc)
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w") as f:
        json.dump({"t": time.time(), "day": day}, f)
    return True, f"Chatten er tatt vare på (Chat-backup/{pc}/{day})"


def _prune(pc, keep=14):
    import lanupdate as L
    try:
        if os.name == "nt":
            import ntpath
            import shutil
            _h, _s, folder = L._split()
            root = ntpath.join(L._unc_root(), *folder.split("/"), "Chat-backup", pc)
            days = sorted(d for d in os.listdir(root) if re.match(r"\d{4}-\d\d-\d\d$", d))
            for d in days[:-keep]:
                shutil.rmtree(ntpath.join(root, d), ignore_errors=True)
            return
        out = L._smb(f'cd "Chat-backup/{pc}"; ls', 60)
        days = sorted(set(re.findall(r"(\d{4}-\d\d-\d\d)\s+D", out or "")))
        for d in days[:-keep]:
            L._smb(f'cd "Chat-backup/{pc}"; deltree "{d}"', 60)
    except Exception:  # noqa: BLE001
        pass


def backup_tick():
    """Kalles fra bakgrunnen: ta kopi én gang i døgnet (i egen tråd)."""
    if backup_due():
        threading.Thread(target=lambda: _safe(backup_to_nas), daemon=True).start()


def _safe(fn):
    try:
        fn()
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------
# Knappene i chatvarselet
# --------------------------------------------------------------------------
def from_notification(name, target):
    """«👍» eller «✓ Lest» trykket i varselet. target = «rom|melding-id»."""
    room, _sp, mid = str(target).partition("|")
    if not room:
        return

    def work():
        import chat
        if name == "chat-read":
            chat.mark_read(room)
            if room.startswith("p:"):
                chat.send_event(room, {"type": "read", "t": time.time()})
            return
        if room.startswith("s:"):
            import chatsrv
            _s, sid, ch = room.split(":", 2)
            srv = chatsrv.get(sid)
            me = chatsrv.me()
            ev = {"type": "react", "mid": mid, "ch": ch, "emoji": "👍", "from": me["name"], "from_id": me["id"]}
            chat.apply_event(room, ev, (srv or {}).get("members", {}).get(me["id"]))
            chatsrv.broadcast(srv, ev)
        else:
            chat.send_event(room, {"type": "react", "mid": mid, "emoji": "👍"})
        chat.mark_read(room)
    threading.Thread(target=lambda: _safe(work), daemon=True).start()


# --------------------------------------------------------------------------
# «Spiller nå» – hvor lenge
# --------------------------------------------------------------------------
_GAME = {"name": None, "since": 0}


def game_since(game):
    """Når spillet startet (for «spiller WoW · 1 t 20 min»)."""
    if game != _GAME["name"]:
        _GAME.update(name=game, since=time.time() if game else 0)
    return _GAME["since"]


def fmt_dur(secs):
    m = int(secs // 60)
    return f"{m // 60} t {m % 60} min" if m >= 60 else f"{m} min"
