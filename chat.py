"""Chat for alle som har Kontrollsenter: hjemme, vennene (Tailscale) og privat.

Rom:
  hjemme        familie-chatten (de andre PC-ene hjemme, via NAS-en – som før)
  alle          alle PC-ene hjemme + alle vennene dine
  p:<navn>      privat med én PC hjemme eller én venn

Vennene får meldingene direkte (POST /api/friend/chat). Mottakeren godtar bare meldinger fra en adresse som står i
sin egen venneliste – fremmede kan ikke skrive. Er noen av (eller borte), ligger meldingen i en kø og sendes når de
svarer igjen (i opptil 3 døgn).
"""
import json
import os
import threading
import time
import urllib.parse
import urllib.request

DATA = os.path.expanduser("~/.local/share/systemmonitor")
FILE = os.path.join(DATA, "chat-rom.json")
OUTBOX = os.path.join(DATA, "chat-ut.json")
_LOCK = threading.Lock()
_LISTENERS = []
KEEP = 300


def _me():
    import savegames
    return savegames.pc_name()


def _load(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _save(path, data):
    os.makedirs(DATA, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def on_message(fn):
    _LISTENERS.append(fn)


def _fire(room, msg):
    for fn in list(_LISTENERS):
        try:
            from gi.repository import GLib
            GLib.idle_add(lambda f=fn: (f(room, msg), False)[1])
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------
# Rom og meldinger
# --------------------------------------------------------------------------
def rooms():
    """[(rom-id, visningsnavn, ikon, uleste)]"""
    out = [("hjemme", "Hjemme", "🏠"), ("alle", "Alle (hjemme + venner)", "🌍")]
    seen = set()
    try:
        import homepcs
        for p in homepcs.fetch() or []:
            n = p.get("name")
            if n and n != _me() and n not in seen:
                seen.add(n)
                out.append((f"p:{n}", n, "💻"))
    except Exception:  # noqa: BLE001
        pass
    try:
        import friends
        for f in friends.cfg()["friends"]:
            n = f.get("name")
            if n and n not in seen:
                seen.add(n)
                out.append((f"p:{n}", n, "👋"))
    except Exception:  # noqa: BLE001
        pass
    d = _load(FILE, {})
    read = d.get("_read", {})
    res = []
    for rid, name, icon in out:
        msgs = messages(rid, 200)
        unread = sum(1 for m in msgs if m.get("t", 0) > read.get(rid, 0) and m.get("from") != _me())
        res.append((rid, name, icon, unread))
    return res


def messages(room, limit=100):
    if room == "hjemme":
        import features
        return [{**m, "room": "hjemme"} for m in features.chat_list(limit)]
    d = _load(FILE, {})
    return (d.get(room) or [])[-limit:]


def mark_read(room):
    with _LOCK:
        d = _load(FILE, {})
        d.setdefault("_read", {})[room] = time.time()
        _save(FILE, d)


def _store(room, msg):
    if room == "hjemme":
        return
    with _LOCK:
        d = _load(FILE, {})
        lst = d.setdefault(room, [])
        if any(m.get("id") == msg.get("id") for m in lst[-50:]):   # samme melding to ganger (ny sending fra kø)
            return False
        lst.append(msg)
        d[room] = lst[-KEEP:]
        _save(FILE, d)
    return True


# --------------------------------------------------------------------------
# Sende
# --------------------------------------------------------------------------
def _friend(name):
    try:
        import friends
        return next((f for f in friends.cfg()["friends"] if f.get("name") == name), None)
    except Exception:  # noqa: BLE001
        return None


def _home_pc(name):
    try:
        import homepcs
        return next((p for p in homepcs.fetch() or [] if p.get("name") == name), None)
    except Exception:  # noqa: BLE001
        return None


def _post_friend(f, payload, timeout=6):
    url = (f"http://{f['addr']}:{f.get('port', 27100)}/api/friend/chat?k=" + urllib.parse.quote(f["key"]))
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "Kontrollsenter"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def send(room, text, frm=None, notify=None):
    """Send en melding i et rom. Returnerer tekst om hvordan det gikk."""
    text = str(text or "").strip()[:500]
    if not text:
        raise ValueError("tom melding")
    me = _me()
    frm = frm or me
    if room == "hjemme":
        import features
        features.send_to("*", frm, text, notify)
        return "Sendt til PC-ene hjemme"
    msg = {"id": f"{me}-{time.time_ns()}", "t": time.time(), "from": frm, "pc": me, "text": text, "room": room}
    _store(room, msg)
    _fire(room, msg)
    targets = []                                            # (type, mål)
    if room == "alle":
        try:
            import friends
            targets += [("venn", f) for f in friends.cfg()["friends"]]
        except Exception:  # noqa: BLE001
            pass
        try:
            import homepcs
            targets += [("hjem", p["name"]) for p in homepcs.fetch() or [] if p.get("name") and p["name"] != me]
        except Exception:  # noqa: BLE001
            pass
    elif room.startswith("p:"):
        name = room[2:]
        f = _friend(name)
        if f:
            targets.append(("venn", f))
        elif _home_pc(name):
            targets.append(("hjem", name))
        else:
            raise ValueError("fant ikke mottakeren")
    ok = queued = 0
    for kind, t in targets:
        payload = {**msg, "room": "alle" if room == "alle" else f"p:{me}"}   # hos mottakeren heter privatrommet meg
        if _deliver(kind, t, payload):
            ok += 1
        else:
            _queue(kind, t, payload)
            queued += 1
    if not targets:
        return "Ingen å sende til ennå – legg til venner under PC-er utenfor hjemmet"
    return f"Sendt til {ok}" + (f" · {queued} får den når de er på igjen" if queued else "")


def _deliver(kind, target, payload):
    try:
        if kind == "venn":
            return bool(_post_friend(target, payload).get("ok"))
        import features
        features.nas_send(target, payload["from"], json.dumps({"_chat2": payload}, ensure_ascii=False))
        return True
    except Exception:  # noqa: BLE001
        return False


def _queue(kind, target, payload):
    with _LOCK:
        q = _load(OUTBOX, [])
        key = target.get("addr") if kind == "venn" else target
        q.append({"kind": kind, "to": key, "name": target.get("name") if kind == "venn" else target,
                  "payload": payload, "t": time.time()})
        _save(OUTBOX, q[-500:])


def retry_outbox():
    """Fra bakgrunnen: prøv køen på nytt (meldinger eldre enn 3 døgn droppes)."""
    with _LOCK:
        q = _load(OUTBOX, [])
    if not q:
        return 0
    left, sent = [], 0
    for e in q:
        if time.time() - e["t"] > 3 * 86400:
            continue
        if e["kind"] == "venn":
            f = _friend(e.get("name")) or next((x for x in __import__("friends").cfg()["friends"]
                                                if x.get("addr") == e["to"]), None)
            if f and _deliver("venn", f, e["payload"]):
                sent += 1
                continue
        elif _deliver("hjem", e["to"], e["payload"]):
            sent += 1
            continue
        left.append(e)
    with _LOCK:
        _save(OUTBOX, left)
    return sent


def queued_count():
    return len(_load(OUTBOX, []))


# --------------------------------------------------------------------------
# Motta
# --------------------------------------------------------------------------
def receive_friend(payload, src_ip, notify=None):
    """POST /api/friend/chat: bare fra adresser i vennelista."""
    import friends
    import socket

    def ip_of(a):
        try:
            return socket.gethostbyname(a)
        except OSError:
            return None
    f = next((x for x in friends.cfg()["friends"] if x.get("addr") == src_ip), None) or \
        next((x for x in friends.cfg()["friends"] if ip_of(x.get("addr", "")) == src_ip), None)
    if not f:
        raise PermissionError("du står ikke i vennelista til denne PC-en")
    room = payload.get("room") or "alle"
    if room.startswith("p:"):
        room = f"p:{f['name']}"                           # privat: rommet heter det JEG kaller vennen
    elif room != "alle":
        room = "alle"
    msg = {"id": str(payload.get("id") or time.time_ns())[:80], "t": time.time(),
           "from": str(payload.get("from") or f["name"])[:40], "pc": f["name"], "text": str(payload.get("text"))[:500],
           "room": room}
    if _store(room, msg):
        _alert(room, msg, notify)
    return True


def receive_home(payload, notify=None):
    """En melding fra en PC hjemme (via NAS-postkassen)."""
    room = payload.get("room") or "alle"
    if room not in ("alle",) and not room.startswith("p:"):
        room = "alle"
    msg = {"id": str(payload.get("id"))[:80], "t": time.time(), "from": str(payload.get("from"))[:40],
           "pc": str(payload.get("pc"))[:40], "text": str(payload.get("text"))[:500], "room": room}
    if _store(room, msg):
        _alert(room, msg, notify)


def _alert(room, msg, notify):
    _fire(room, msg)
    try:
        import remote_extra
        remote_extra.event("chat", f"💬 {msg['from']}", msg["text"], "info")
    except Exception:  # noqa: BLE001
        pass
    if notify:
        try:
            from gi.repository import GLib
            where = "" if room.startswith("p:") else " (alle)"
            GLib.idle_add(lambda: (notify("chat", f"💬 {msg['from']}{where}", msg["text"], force=True,
                                          action="app.chat"), False)[1])
        except Exception:  # noqa: BLE001
            pass
