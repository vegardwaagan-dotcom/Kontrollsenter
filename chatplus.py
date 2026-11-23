"""Chat+ (runde 2): vedlegg og bilder, talemeldinger, avstemninger, avtaler, påminnelser, planlagte meldinger,
lest/levert, «skriver …», søk, autosvar, oppsummering, meldinger som forsvinner, eksport, opprydding, status og
farge, klistremerker, feiring, minispill, statistikk og minner.

Alt dette virker i serverkanaler (meldingene går direkte til medlemmene). Filer opptil 8 MB sendes med meldingen;
klipp deles som lenke (strømmes fra PC-en som har klippet).
"""
import base64
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time

IS_WIN = sys.platform == "win32"
DATA = os.path.expanduser("~/.local/share/systemmonitor")
FILES = os.path.join(DATA, "chat-filer")
CFG = os.path.expanduser("~/.config/systemmonitor/chat-pluss.json")
MAX_FILE = 8 * 1024 * 1024
DEF = {"status": "", "color": "", "avatar": "", "autoreply": True, "autoreply_text": "",
       "sounds": {}, "pinned_rooms": [], "vanish": {}, "scheduled": [], "reminders": [], "notes": {},
       "clean_days": 30, "celebrate": True, "stickers": []}
_TYPING = {}                 # rom -> {navn: tid}
_READ = {}                   # rom -> {medlem-id: tid}
_DELIV = {}                  # melding-id -> antall levert


def cfg():
    try:
        d = json.load(open(CFG))
    except (OSError, ValueError):
        d = {}
    return {**DEF, **d}


def set_(**kw):
    d = cfg()
    d.update(kw)
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    json.dump(d, open(CFG, "w"), ensure_ascii=False)
    return d


def _srv_ch(room):
    _s, sid, ch = room.split(":", 2)
    import chatsrv
    return chatsrv.get(sid), ch


def _send_event(room, ev):
    """Til alle i serveren (hendelser som ikke er meldinger)."""
    import chatsrv
    srv, ch = _srv_ch(room)
    if srv:
        threading.Thread(target=chatsrv.broadcast, args=(srv, {**ev, "ch": ch}), daemon=True).start()


# --------------------------------------------------------------------------
# 1 / 2 – lest, levert og «skriver …»
# --------------------------------------------------------------------------
def mark_read(room):
    if room.startswith("s:"):
        import chatsrv
        _send_event(room, {"type": "read", "t": time.time(), "from_id": chatsrv.me()["id"]})


def typing(room):
    if room.startswith("s:") and time.time() - _TYPING.get(("me", room), 0) > 3:
        _TYPING[("me", room)] = time.time()
        import chatsrv
        _send_event(room, {"type": "typing", "from": chatsrv.me()["name"]})


def on_event(room, ev, sender):
    """Fra chatsrv.receive for read/typing (vises bare, lagres ikke)."""
    if ev.get("type") == "typing":
        _TYPING.setdefault(room, {})[sender["name"]] = time.time()
    elif ev.get("type") == "read":
        _READ.setdefault(room, {})[sender["id"]] = float(ev.get("t") or time.time())


def who_typing(room):
    now = time.time()
    return [n for n, t in (_TYPING.get(room) or {}).items() if now - t < 5]


def receipt(room, msg):
    """«✓ sendt», «✓✓ levert til N» eller «👁 lest av …» for min siste melding."""
    import chatsrv
    srv, _ch = _srv_ch(room)
    if not srv:
        return ""
    others = {mid: m for mid, m in srv.get("members", {}).items() if mid != chatsrv.me()["id"]}
    readers = [others[mid]["name"] for mid, t in (_READ.get(room) or {}).items() if mid in others and t >= msg["t"]]
    if readers:
        return "👁 " + ("lest av alle" if len(readers) == len(others) else "lest av " + ", ".join(readers[:3]))
    n = _DELIV.get(msg.get("id"))
    return f"✓✓ levert til {n}" if n else "✓ sendt"


def delivered(mid, n):
    _DELIV[mid] = n


# --------------------------------------------------------------------------
# 7 / 8 / 9 – vedlegg (bilder, filer) og klipp
# --------------------------------------------------------------------------
def _kind(name):
    ext = os.path.splitext(name.lower())[1]
    if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        return "image"
    if ext in (".ogg", ".opus", ".wav", ".mp3", ".m4a"):
        return "audio"
    if ext in (".mp4", ".mkv", ".webm", ".mov"):
        return "video"
    return "file"


def store_file(name, data):
    os.makedirs(FILES, exist_ok=True)
    sha = hashlib.sha256(data).hexdigest()[:24]
    ext = os.path.splitext(name)[1][:8] or ".bin"
    path = os.path.join(FILES, sha + ext)
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(data)
    return path, sha


def file_path(att):
    if not att:
        return None
    p = os.path.join(FILES, att.get("sha", "") + (os.path.splitext(att.get("name", ""))[1][:8] or ".bin"))
    return p if os.path.exists(p) else None


def send_file(room, path, text="", notify=None):
    """Bilde/fil opptil 8 MB sendes med meldingen. Klipp (video) deles som lenke."""
    import chat
    size = os.path.getsize(path)
    name = os.path.basename(path)
    kind = _kind(name)
    if kind == "video" or size > MAX_FILE:
        link = clip_link(path)
        if not link:
            raise ValueError(f"filen er for stor (maks {MAX_FILE // 1048576} MB) – klipp deles fra Klipp-mappen")
        return chat.send(room, (text + "\n" if text else "") + f"🎬 {name}: {link}", None, notify,
                         extra={"kind": "clip"})
    data = open(path, "rb").read()
    _p, sha = store_file(name, data)
    att = {"name": name, "size": size, "sha": sha, "kind": kind, "data": base64.b64encode(data).decode()}
    return chat.send(room, text or ("🖼️ Bilde" if kind == "image" else "🎙️ Talemelding" if kind == "audio" else
                                    f"📎 {name}"), None, notify, extra={"attach": att})


def receive_attach(att):
    """Lagre vedlegget fra en melding og fjern selve dataene fra meldingen (lagres som fil)."""
    if not att or "data" not in att:
        return att
    try:
        data = base64.b64decode(att["data"])
        if len(data) <= MAX_FILE:
            store_file(att.get("name", "fil"), data)
    except (ValueError, OSError):
        pass
    return {k: v for k, v in att.items() if k != "data"}


def clip_link(path):
    """Lenke til et klipp (strømmes fra denne PC-en; gjelder i 3 døgn)."""
    try:
        import clipx
        import chatsrv
        import urllib.parse
        name = os.path.basename(path)
        if not clipx.any_path(name):
            return None
        tok = clipx.share_token(name, 72)
        addr = (chatsrv.my_addrs() or ["?"])[0]
        return f"http://{addr}:27100/api/clipfile?name={urllib.parse.quote(name)}&s={tok}"
    except Exception:  # noqa: BLE001
        return None


def recent_media(n=12):
    """Siste klipp og skjermbilder (til «📎 Legg ved»)."""
    try:
        import clipx
        return [x for x in clipx.files()][:n]
    except Exception:  # noqa: BLE001
        return []


# --------------------------------------------------------------------------
# 10 / 37 – talemeldinger og walkie-talkie
# --------------------------------------------------------------------------
_REC = {"p": None, "path": None}


def _win_mic():
    import clipx
    ff = clipx.ffmpeg()
    if not ff:
        return None, None
    out = subprocess.run([ff, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                         capture_output=True, text=True, timeout=15, creationflags=0x08000000).stderr
    m = re.search(r'"([^"]+)"\s*\(audio\)', out)
    return ff, (m.group(1) if m else None)


def record_start():
    """Start opptak fra mikrofonen. Returnerer True."""
    os.makedirs(FILES, exist_ok=True)
    path = os.path.join(FILES, f"opptak-{int(time.time())}.ogg")
    if IS_WIN:
        ff, dev = _win_mic()
        if not ff or not dev:
            raise RuntimeError("talemeldinger på Windows trenger FFmpeg (Programmer → Redigere klipp)")
        cmd = [ff, "-hide_banner", "-loglevel", "error", "-f", "dshow", "-i", f"audio={dev}", "-ac", "1",
               "-c:a", "libopus", "-b:a", "32k", "-y", path]
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE, creationflags=0x08000000)
    else:
        ff = shutil.which("ffmpeg")
        if ff:
            cmd = [ff, "-hide_banner", "-loglevel", "error", "-f", "pulse", "-i", "default", "-ac", "1",
                   "-c:a", "libopus", "-b:a", "32k", "-y", path]
            p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        else:
            path = path[:-4] + ".wav"
            p = subprocess.Popen(["pw-record", "--channels", "1", "--rate", "24000", path])
    _REC.update(p=p, path=path, t=time.time())
    return True


def record_stop():
    """Stopp opptaket. Returnerer filstien (eller None hvis for kort)."""
    p, path = _REC["p"], _REC["path"]
    _REC.update(p=None, path=None)
    if not p:
        return None
    try:
        if p.stdin:
            p.stdin.write(b"q")
            p.stdin.flush()
        else:
            p.terminate()
        p.wait(5)
    except Exception:  # noqa: BLE001
        p.kill()
    if time.time() - _REC.get("t", 0) < 0.7 or not os.path.exists(path) or os.path.getsize(path) < 1000:
        return None
    return path


def play(path):
    if not path or not os.path.exists(path):
        return False
    if IS_WIN:
        if path.endswith(".wav"):
            import winsound
            threading.Thread(target=lambda: winsound.PlaySound(path, winsound.SND_FILENAME), daemon=True).start()
        else:
            os.startfile(path)  # noqa: S606
        return True
    for cmd in (["pw-play", path], ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path], ["paplay", path]):
        if shutil.which(cmd[0]):
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
    return False


# --------------------------------------------------------------------------
# 15 / 60 – avstemninger, 74 – avtaler med svar
# --------------------------------------------------------------------------
def send_poll(room, question, options, notify=None):
    import chat
    opts = [o.strip()[:60] for o in options if o.strip()][:8]
    if len(opts) < 2:
        raise ValueError("minst to valg")
    return chat.send(room, f"📊 {question}", None, notify, extra={"kind": "poll", "poll": {"options": opts}})


def vote(room, msg, idx):
    import chatsrv
    ev = {"type": "vote", "mid": msg["id"], "idx": int(idx), "from": chatsrv.me()["name"],
          "from_id": chatsrv.me()["id"]}
    _apply_vote(room, ev, chatsrv.me()["name"])
    _send_event(room, ev)


def _apply_vote(room, ev, who):
    import chat
    with chat._LOCK:
        d = chat._load(chat.FILE, {})
        for m in d.get(room) or []:
            if m.get("id") == ev.get("mid") and (m.get("poll") or m.get("event")):
                key = "votes" if m.get("poll") else "rsvp"
                votes = m.setdefault(key, {})
                for v in votes.values():             # ett valg per person
                    if who in v:
                        v.remove(who)
                votes.setdefault(str(ev.get("idx")), []).append(who)
                break
        chat._save(chat.FILE, d)
    chat._fire(room, {"event": "vote"})
    try:
        import chatlink
        m = next((x for x in chat.messages(room, 300) if x.get("id") == ev.get("mid")), None)
        if m:
            threading.Thread(target=chatlink.lobby_check, args=(room, m), daemon=True).start()
    except Exception:  # noqa: BLE001
        pass


def send_event_invite(room, title, when_text, notify=None):
    """«LAN lørdag kl. 18» – svar: kommer / kanskje / nei. Legges også i ukeplanen."""
    import chat
    when = parse_when(when_text)
    if not when:
        raise ValueError("skriv tid som f.eks. «lørdag 18:00» eller «i morgen 20:00»")
    try:
        import familyplus
        lt = time.localtime(when)
        familyplus.plan_add(lt.tm_wday, time.strftime("%H:%M", lt), title[:80])
    except Exception:  # noqa: BLE001
        pass
    return chat.send(room, f"📅 {title} – {time.strftime('%A %d.%m kl. %H:%M', time.localtime(when))}", None, notify,
                     extra={"kind": "event", "event": {"title": title, "when": when,
                                                       "options": ["Kommer", "Kanskje", "Nei"]}})


# --------------------------------------------------------------------------
# 25 / 42 – påminnelser og planlagte meldinger
# --------------------------------------------------------------------------
DAYS = {"mandag": 0, "tirsdag": 1, "onsdag": 2, "torsdag": 3, "fredag": 4, "lørdag": 5, "søndag": 6}


def parse_when(text, now=None):
    """«i dag 17:00», «i morgen 07:30», «lørdag 18», «om 10 min», «om 2 timer», «18:30» → tidspunkt."""
    now = now or time.time()
    t = (text or "").lower().strip()
    m = re.search(r"om\s+(\d+)\s*(min|minutt|minutter|t|time|timer)", t)
    if m:
        n = int(m.group(1))
        return now + n * (60 if m.group(2).startswith("min") else 3600)
    tm = re.search(r"(\d{1,2})(?:[:.](\d{2}))?\s*$", t) or re.search(r"kl\.?\s*(\d{1,2})(?:[:.](\d{2}))?", t)
    if not tm:
        return None
    hh, mm = int(tm.group(1)), int(tm.group(2) or 0)
    if hh > 23 or mm > 59:
        return None
    lt = time.localtime(now)
    base = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, hh, mm, 0, 0, 0, -1))
    if "i morgen" in t:
        return base + 86400
    for name, wd in DAYS.items():
        if name in t:
            ahead = (wd - lt.tm_wday) % 7
            if ahead == 0 and base <= now:
                ahead = 7
            return base + ahead * 86400
    return base if base > now else base + 86400


def remind(room, text, when_text):
    when = parse_when(when_text)
    if not when:
        raise ValueError("skriv tid som «i morgen 17:00», «om 10 min» eller «fredag 18»")
    c = cfg()
    c["reminders"].append({"room": room, "text": text[:200], "when": when})
    set_(reminders=c["reminders"])
    return f"⏰ Påminnelse {time.strftime('%a %d.%m %H:%M', time.localtime(when))}: {text}"


def schedule(room, text, when_text):
    when = parse_when(when_text)
    if not when:
        raise ValueError("skriv tid som «i morgen 07:00»")
    c = cfg()
    c["scheduled"].append({"room": room, "text": text[:2000], "when": when})
    set_(scheduled=c["scheduled"])
    return f"🕒 Sendes {time.strftime('%a %d.%m %H:%M', time.localtime(when))}"


def tick(win):
    """Hvert minutt: påminnelser, planlagte meldinger, meldinger som forsvinner og opprydding."""
    c = cfg()
    now = time.time()
    due_r = [r for r in c["reminders"] if r["when"] <= now]
    due_s = [s for s in c["scheduled"] if s["when"] <= now]
    if due_r or due_s:
        set_(reminders=[r for r in c["reminders"] if r["when"] > now],
             scheduled=[s for s in c["scheduled"] if s["when"] > now])
    bg = getattr(win, "bg", None)
    for r in due_r:
        if bg:
            from gi.repository import GLib
            GLib.idle_add(lambda rr=r: (bg.notify("chat", "⏰ Påminnelse", rr["text"], force=True,
                                                  action="app.chat"), False)[1])
    for s in due_s:
        try:
            import chat
            chat.send(s["room"], s["text"])
        except Exception:  # noqa: BLE001
            pass
    if int(now) % 3600 < 70:
        vanish_tick()
        cleanup()


# --------------------------------------------------------------------------
# 43 – autosvar, 40 – oppsummering
# --------------------------------------------------------------------------
_AUTO = {}


def autoreply(room, msg, win):
    """Svar automatisk på private meldinger/omtaler når du spiller (høyst én gang per 30 min per rom)."""
    c = cfg()
    if not c["autoreply"]:
        return
    game = getattr(getattr(win, "bg", None), "game_name", None)
    if not game:
        return
    import chatsrv
    mine = chatsrv.me()
    if not (room.startswith("p:") or f"@{mine['name'].lower()}" in str(msg.get("text", "")).lower()):
        return
    if time.time() - _AUTO.get(room, 0) < 1800:
        return
    _AUTO[room] = time.time()
    import chat
    txt = c["autoreply_text"] or f"🎮 Spiller {game} nå – svarer etter kampen"
    threading.Thread(target=lambda: chat.send(room, f"🤖 {txt}"), daemon=True).start()


def summary(since=None):
    """«Mens du var borte»: hvem som skrev og hva, per rom (siste 12 timer eller siden sist lest)."""
    import chat
    since = since or time.time() - 12 * 3600
    out = []
    read = chat._load(chat.FILE, {}).get("_read", {})
    for rid, name, icon, unread in chat.rooms():
        if not unread:
            continue
        msgs = [m for m in chat.messages(rid, 100) if m.get("t", 0) > max(since, read.get(rid, 0))
                and not str(m.get("from", "")).startswith("🤖")]
        if not msgs:
            continue
        who = sorted({m.get("from") for m in msgs})
        last = msgs[-1]
        out.append(f"{icon} {name}: {len(msgs)} nye fra {', '.join(who[:3])} – siste: «{str(last.get('text'))[:60]}»")
    return out


def translate_url(text):
    import urllib.parse
    return "https://translate.google.com/?sl=auto&tl=no&text=" + urllib.parse.quote(text[:1500])


# --------------------------------------------------------------------------
# 26 – søk, 52 – forsvinner, 53 – eksport, 54 – opprydding
# --------------------------------------------------------------------------
def search(q, limit=60):
    import chat
    q = q.lower().strip()
    if not q:
        return []
    d = chat._load(chat.FILE, {})
    hits = []
    for room, msgs in d.items():
        if room.startswith("_") or not isinstance(msgs, list):
            continue
        for m in msgs:
            if q in str(m.get("text", "")).lower() or q in str(m.get("from", "")).lower():
                hits.append((room, m))
    for m in chat.messages("hjemme", 300):
        if q in str(m.get("text", "")).lower():
            hits.append(("hjemme", m))
    hits.sort(key=lambda x: -x[1].get("t", 0))
    return hits[:limit]


def set_vanish(room, seconds):
    c = cfg()
    v = c["vanish"]
    if seconds:
        v[room] = int(seconds)
    else:
        v.pop(room, None)
    set_(vanish=v)


def vanish_tick():
    import chat
    v = cfg()["vanish"]
    if not v:
        return
    now = time.time()
    with chat._LOCK:
        d = chat._load(chat.FILE, {})
        for room, secs in v.items():
            if isinstance(d.get(room), list):
                d[room] = [m for m in d[room] if now - m.get("t", now) < secs or m.get("pinned")]
        chat._save(chat.FILE, d)


def export(room, path):
    import chat
    msgs = chat.messages(room, 100000)
    with open(path, "w", encoding="utf-8") as f:
        for m in msgs:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M', time.localtime(m.get('t', 0)))}] {m.get('from')}: "
                    f"{m.get('text', '')}\n")
    return len(msgs)


def cleanup():
    days = cfg()["clean_days"]
    if not days or not os.path.isdir(FILES):
        return 0
    n = 0
    for f in os.listdir(FILES):
        p = os.path.join(FILES, f)
        try:
            if time.time() - os.path.getmtime(p) > days * 86400:
                os.remove(p)
                n += 1
        except OSError:
            pass
    return n


# --------------------------------------------------------------------------
# 47 – feiring, 48 – minispill, 79 – statistikk, 80 – minner
# --------------------------------------------------------------------------
CELEBRATE = re.compile(r"\b(gratulerer|gratu|gg|grattis|hurra|wp|well played)\b|🎉|🥳|🎂", re.I)


def is_celebration(text):
    return cfg()["celebrate"] and bool(CELEBRATE.search(text or ""))


RPS = {"stein": "🪨", "saks": "✂️", "papir": "📄"}


def rps(room, choice, notify=None):
    """Stein–saks–papir mot PC-en (alle ser resultatet)."""
    import chat
    choice = choice.lower().strip()
    if choice not in RPS:
        raise ValueError("velg stein, saks eller papir")
    pc = random.choice(list(RPS))
    win = {("stein", "saks"), ("saks", "papir"), ("papir", "stein")}
    res = "Uavgjort!" if pc == choice else ("Du vant! 🎉" if (choice, pc) in win else "PC-en vant 🤖")
    return chat.send(room, f"✊ Stein–saks–papir: {RPS[choice]} mot {RPS[pc]} – {res}", None, notify)


def dice(room, sides=6, notify=None):
    import chat
    return chat.send(room, f"🎲 Kastet terning (1–{sides}): {random.randint(1, sides)}", None, notify)


def stats():
    import chat
    d = chat._load(chat.FILE, {})
    per, emoji, total = {}, {}, 0
    for room, msgs in d.items():
        if room.startswith("_") or not isinstance(msgs, list):
            continue
        for m in msgs:
            total += 1
            per[m.get("from")] = per.get(m.get("from"), 0) + 1
            for ch in str(m.get("text", "")):
                if ord(ch) > 0x2600:
                    emoji[ch] = emoji.get(ch, 0) + 1
    top = sorted(per.items(), key=lambda kv: -kv[1])[:5]
    em = sorted(emoji.items(), key=lambda kv: -kv[1])[:5]
    return {"total": total, "top": top, "emoji": em}


def memories():
    """Meldinger fra i dag for ett år siden (eller en måned siden)."""
    import chat
    d = chat._load(chat.FILE, {})
    out = []
    for back, label in ((365, "for ett år siden"), (30, "for en måned siden")):
        day = time.strftime("%Y-%m-%d", time.localtime(time.time() - back * 86400))
        for room, msgs in d.items():
            if room.startswith("_") or not isinstance(msgs, list):
                continue
            for m in msgs:
                if time.strftime("%Y-%m-%d", time.localtime(m.get("t", 0))) == day:
                    out.append((label, room, m))
    return out[:10]


# --------------------------------------------------------------------------
# 75 / 76 / 78 – status, farge og lyd per person
# --------------------------------------------------------------------------
def my_profile():
    c = cfg()
    return {"status": c["status"], "color": c["color"], "avatar": c["avatar"]}


def notes(room):
    return cfg()["notes"].get(room, "")


def set_notes(room, text):
    n = cfg()["notes"]
    n[room] = text[:5000]
    set_(notes=n)


def sound_for(name):
    return cfg()["sounds"].get(name)


def play_notify_sound(name):
    snd = sound_for(name)
    if snd and os.path.exists(snd):
        play(snd)
        return True
    return False
