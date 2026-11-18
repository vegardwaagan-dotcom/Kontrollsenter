"""Pushvarsler til mobilen med ntfy – uten at Kontrollsenter-appen må være åpen, og uten skytjenester.

Kontrollsenter snakker ntfy sin protokoll selv: ntfy-appen på telefonen abonnerer direkte på PC-en
(http://<PC>:27100/<hemmelig emne>) over hjemmenettet eller Tailscale, og holder en åpen forbindelse som bruker
svært lite batteri. Varslene kommer med en gang, i stedet for hvert 15. minutt.

Emnenavnet er en lang tilfeldig nøkkel – den som ikke kjenner den, får ikke varslene.
"""
import collections
import json
import os
import secrets
import threading
import time

CFG = os.path.expanduser("~/.config/systemmonitor/push.json")
_LOCK = threading.Condition()
_Q = collections.deque(maxlen=60)
_SEQ = [0]


def cfg():
    try:
        with open(CFG) as f:
            c = json.load(f)
    except (OSError, ValueError):
        c = {}
    if not c.get("topic"):
        c["topic"] = "ks" + secrets.token_urlsafe(24).replace("-", "x").replace("_", "y")
        c.setdefault("enabled", False)
        save_cfg(c)
    return c


def save_cfg(c):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    tmp = CFG + ".tmp"
    with open(tmp, "w") as f:
        json.dump(c, f)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, CFG)


def topic():
    return cfg()["topic"]


def enabled():
    return bool(cfg().get("enabled"))


def set_enabled(on):
    c = cfg()
    c["enabled"] = bool(on)
    save_cfg(c)


def new_topic():
    c = cfg()
    c["topic"] = "ks" + secrets.token_urlsafe(24).replace("-", "x").replace("_", "y")
    save_cfg(c)
    return c["topic"]


PRIO = {"temp": 4, "playlimit": 4, "bedtime": 4, "invite": 4, "chat": 4, "disk": 4, "syscheck": 3}
TAGS = {"temp": "fire", "battery": "battery", "playlimit": "hourglass", "bedtime": "zzz", "chat": "speech_balloon",
        "invite": "video_game", "session": "video_game", "clip": "movie_camera", "updates": "arrow_up",
        "goal": "star", "plan": "calendar", "weekly": "bar_chart"}


def publish(key, title, body):
    if not enabled():
        return
    import socket
    with _LOCK:
        _SEQ[0] += 1
        kind = key.rstrip("0123456789:")
        _Q.append({"id": f"{int(time.time())}{_SEQ[0]:04d}", "time": int(time.time()), "event": "message",
                   "topic": topic(), "title": f"{title}", "message": body or title,
                   "priority": PRIO.get(kind, 3), "tags": [TAGS.get(kind, "computer")],
                   "click": "", "_seq": _SEQ[0], "_pc": socket.gethostname()})
        _LOCK.notify_all()


def _clean(m):
    return {k: v for k, v in m.items() if not k.startswith("_") and v != ""}


def since(spec):
    """Meldinger etter «since» (all, unix-tid eller meldings-id)."""
    with _LOCK:
        msgs = list(_Q)
    if not spec or spec == "all":
        return msgs
    if spec.isdigit() and len(spec) <= 11:
        return [m for m in msgs if m["time"] > int(spec)]
    ids = [m["id"] for m in msgs]
    return msgs[ids.index(spec) + 1:] if spec in ids else msgs


def stream(wfile, top, since_spec=None, stop=None):
    """ntfy JSON-strøm: open, så meldinger og keepalive hvert 45. sekund."""
    def send(obj):
        wfile.write((json.dumps(obj, ensure_ascii=False) + "\n").encode())
        wfile.flush()
    send({"id": secrets.token_hex(6), "time": int(time.time()), "event": "open", "topic": top})
    last = _SEQ[0]
    for m in since(since_spec) if since_spec else []:
        send(_clean(m))
    while not (stop and stop.is_set()):
        with _LOCK:
            _LOCK.wait(45)
            new = [m for m in _Q if m["_seq"] > last]
        if new:
            for m in new:
                send(_clean(m))
            last = new[-1]["_seq"]
        else:
            send({"id": secrets.token_hex(6), "time": int(time.time()), "event": "keepalive", "topic": top})
