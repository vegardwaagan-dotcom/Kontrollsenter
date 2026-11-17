"""Scener: én knapp som setter hele rommet og PC-en på én gang.

En scene kan styre strømmodus, vifter, RGB, Hue-lysene, Samsung-TV-en, lyden, fargetemaet og varslene –
og kan slå seg på av seg selv: når et spill starter, når det slutter, eller på et klokkeslett.

Lagres i ~/.config/systemmonitor/scener.json. Brukes av PC-siden «Scener» og av mobilappen (/api/x/scenes,
handling {"a": "scene", "id": ...}).
"""
import copy
import json
import os
import threading
import time

CFG = os.path.expanduser("~/.config/systemmonitor/scener.json")

POWER = [(None, "Ikke endre"), ("power-saver", "Strømsparing"), ("balanced", "Balansert"), ("performance", "Max Ytelse")]
FANS = [(None, "Ikke endre"), ("auto", "Auto"), ("curve", "Kurve"), (30, "Stille (30 %)"), (70, "Kraftig (70 %)"),
        (100, "Max (100 %)")]
TV = [(None, "Ikke endre"), ("on", "Slå på"), ("off", "Slå av")]
QUIET = [(None, "Ikke endre"), (True, "Stille – ingen varsler"), (False, "Vanlige varsler")]
TRIGGERS = [("manual", "Bare når jeg trykker"), ("game_start", "Når et spill starter"),
            ("game_end", "Når et spill avsluttes"), ("time", "Hver dag klokka …")]

DEFAULTS = [
    {"id": "spillkveld", "name": "Spillkveld", "icon": "🎮", "color": "#ff2bd6",
     "power": "performance", "fans": 70, "rgb": "#8a5cff", "hue": {"on": True, "bri": 35, "color": "#7c5cff"},
     "tv": None, "volume": None, "mute": None, "theme": "synthwave", "quiet": True,
     "trigger": {"type": "game_start", "auto": False, "at": "20:00"}},
    {"id": "etter", "name": "Etter spillet", "icon": "🛋️", "color": "#ffb46b",
     "power": "balanced", "fans": "auto", "rgb": None, "hue": {"on": True, "bri": 70, "color": "#ffc58a"},
     "tv": None, "volume": None, "mute": None, "theme": None, "quiet": False,
     "trigger": {"type": "game_end", "auto": False, "at": "20:00"}},
    {"id": "film", "name": "Filmkveld", "icon": "🍿", "color": "#ff8a3d",
     "power": "power-saver", "fans": 30, "rgb": "off", "hue": {"on": True, "bri": 12, "color": "#ff8a3d"},
     "tv": "on", "volume": None, "mute": None, "theme": "solnedgang", "quiet": True,
     "trigger": {"type": "manual", "auto": False, "at": "20:00"}},
    {"id": "fokus", "name": "Fokus", "icon": "💼", "color": "#2f9bff",
     "power": "balanced", "fans": "auto", "rgb": "#ffffff", "hue": {"on": True, "bri": 100, "color": "#f2f6ff"},
     "tv": "off", "volume": None, "mute": None, "theme": "arktis", "quiet": True,
     "trigger": {"type": "manual", "auto": False, "at": "08:00"}},
    {"id": "natt", "name": "God natt", "icon": "🌙", "color": "#7c5cff",
     "power": "power-saver", "fans": "auto", "rgb": "off", "hue": {"on": False},
     "tv": "off", "volume": None, "mute": True, "theme": "nordlys", "quiet": False,
     "trigger": {"type": "time", "auto": False, "at": "23:30"}},
]

_LOCK = threading.Lock()


def load():
    try:
        with open(CFG) as f:
            d = json.load(f)
        if isinstance(d.get("scenes"), list):
            return d
    except (OSError, ValueError):
        pass
    return {"scenes": copy.deepcopy(DEFAULTS), "active": None}


def save(d):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    with open(CFG + ".tmp", "w") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
    os.replace(CFG + ".tmp", CFG)


def get(sid):
    return next((s for s in load()["scenes"] if s["id"] == sid), None)


def put(scene):
    d = load()
    for i, s in enumerate(d["scenes"]):
        if s["id"] == scene["id"]:
            d["scenes"][i] = scene
            break
    else:
        d["scenes"].append(scene)
    save(d)


def delete(sid):
    d = load()
    d["scenes"] = [s for s in d["scenes"] if s["id"] != sid]
    save(d)


def new_id(name):
    base = "".join(c for c in name.lower() if c.isalnum())[:16] or "scene"
    ids = {s["id"] for s in load()["scenes"]}
    i, sid = 2, base
    while sid in ids:
        sid, i = f"{base}{i}", i + 1
    return sid


def summary(s):
    """Kort tekst om hva scenen gjør (til kortene og appen)."""
    parts = []
    lab = lambda lst, v: next((t for k, t in lst if k == v), None)  # noqa: E731
    if s.get("power"):
        parts.append(lab(POWER, s["power"]))
    if s.get("fans") is not None:
        parts.append("vifter " + (lab(FANS, s["fans"]) or str(s["fans"])).lower())
    if s.get("rgb"):
        parts.append("RGB av" if s["rgb"] == "off" else "RGB-farge")
    h = s.get("hue")
    if h:
        parts.append("lys av" if not h.get("on") else f"lys {h.get('bri', 100)} %")
    if s.get("tv"):
        parts.append("TV på" if s["tv"] == "on" else "TV av")
    if s.get("mute"):
        parts.append("demp")
    elif s.get("volume") is not None:
        parts.append(f"volum {s['volume']} %")
    if s.get("theme"):
        import theme
        parts.append("tema " + theme.THEMES.get(s["theme"], {}).get("name", s["theme"]))
    if s.get("quiet"):
        parts.append("ingen varsler")
    return " · ".join(p for p in parts if p) or "Gjør ingenting ennå – trykk Rediger"


def trigger_text(s):
    t = s.get("trigger") or {}
    if not t.get("auto") or t.get("type") == "manual":
        return "Bare når du trykker"
    if t["type"] == "time":
        return f"Automatisk hver dag kl. {t.get('at', '')}"
    return dict(TRIGGERS).get(t["type"], "")


# --------------------------------------------------------------------------
# Kjør en scene
# --------------------------------------------------------------------------
def _steps(s):
    steps = []
    if s.get("power"):
        steps.append(("Strømmodus", {"a": "power", "mode": s["power"]}))
    if s.get("fans") is not None:
        steps.append(("Vifter", {"a": "fans", "value": s["fans"]}))
    if s.get("rgb"):
        steps.append(("RGB", {"a": "rgb", "mode": "off"} if s["rgb"] == "off" else
                      {"a": "rgb", "mode": "color", "color": s["rgb"]}))
    h = s.get("hue")
    if h:
        body = {"a": "smart", "do": "hue", "on": bool(h.get("on"))}
        if h.get("on"):
            body["bri"] = max(1, round(254 * int(h.get("bri", 100)) / 100))
            if h.get("color"):
                body["color"] = h["color"]
        steps.append(("Hue-lys", body))
    if s.get("mute") is not None or s.get("volume") is not None:
        v = {"a": "volume"}
        if s.get("volume") is not None:
            v["volume"] = int(s["volume"])
        if s.get("mute") is not None:
            v["mute"] = bool(s["mute"])
        steps.append(("Lyd", v))
    return steps


def _tv(want):
    import smarthome
    tvs = list((smarthome.cfg().get("tvs") or {}).keys())
    if not tvs:
        raise RuntimeError("ingen Samsung-TV funnet")
    for ip in tvs:
        st = smarthome.tv_state(ip).get("power")
        if want == "on" and st != "on":
            smarthome.tv_key(ip, "on")
        elif want == "off" and st == "on":
            smarthome.tv_key(ip, "power")
    return True


def run(win, sid, why="trykket", done=None):
    """Kjør scenen i bakgrunnen. done(navn, ok_antall, totalt, feil) kalles i GTK-tråden etterpå."""
    s = get(sid)
    if not s:
        raise ValueError("fant ikke scenen")

    def work():
        import remote
        from gi.repository import GLib
        steps = _steps(s)
        ok, errs = 0, []
        for name, a in steps:
            try:
                remote.do_action(win, a)
                ok += 1
            except Exception as e:  # noqa: BLE001
                errs.append(f"{name}: {e}")
        n = len(steps)
        if s.get("tv"):
            n += 1
            try:
                _tv(s["tv"])
                ok += 1
            except Exception as e:  # noqa: BLE001
                errs.append(f"TV: {e}")

        def ui():
            if s.get("theme"):
                try:
                    import theme
                    theme.set_theme(s["theme"])
                except Exception as e:  # noqa: BLE001
                    errs.append(f"Tema: {e}")
            if s.get("quiet") is not None:
                bg = getattr(win, "bg", None)
                if bg:
                    bg.set("dnd", bool(s["quiet"]))
            d = load()
            d["active"] = sid
            d["active_t"] = time.time()
            save(d)
            try:
                import remote_extra
                remote_extra.event("scene", f"Scene: {s['icon']} {s['name']}",
                                   ("automatisk – " + why if why != "trykket" else "") +
                                   (f" ({len(errs)} feil)" if errs else ""), "info")
            except Exception:  # noqa: BLE001
                pass
            for cb in list(_LISTENERS):
                try:
                    cb(sid)
                except Exception:  # noqa: BLE001
                    pass
            if done:
                done(s["name"], ok + (1 if s.get("theme") else 0) + (1 if s.get("quiet") is not None else 0),
                     n + (1 if s.get("theme") else 0) + (1 if s.get("quiet") is not None else 0), errs)
            return False
        GLib.idle_add(ui)
    threading.Thread(target=work, daemon=True).start()
    return s["name"]


_LISTENERS = []


def listen(fn):
    if fn not in _LISTENERS:
        _LISTENERS.append(fn)


# --------------------------------------------------------------------------
# Automatikk: spill starter/slutter og klokkeslett
# --------------------------------------------------------------------------
_FIRED = {}


def on_event(win, kind, game=None):
    """kind = «game_start» eller «game_end» (fra spillprofilene)."""
    for s in load()["scenes"]:
        t = s.get("trigger") or {}
        if t.get("auto") and t.get("type") == kind:
            run(win, s["id"], why=("spillet startet" if kind == "game_start" else "spillet ble avsluttet")
                + (f": {game}" if game else ""), done=_toast(win))


def tick(win):
    """Kalles jevnlig (ca. hvert 5. sekund) – kjører scener med klokkeslett."""
    now = time.localtime()
    hhmm = f"{now.tm_hour:02d}:{now.tm_min:02d}"
    day = time.strftime("%Y-%m-%d")
    for s in load()["scenes"]:
        t = s.get("trigger") or {}
        if t.get("auto") and t.get("type") == "time" and t.get("at") == hhmm and _FIRED.get(s["id"]) != day:
            _FIRED[s["id"]] = day
            run(win, s["id"], why=f"kl. {hhmm}", done=_toast(win))


def _toast(win):
    def done(name, ok, n, errs):
        try:
            win.toast(f"Scene «{name}» er satt" + (f" ({ok} av {n})" if errs else " ✓"))
        except Exception:  # noqa: BLE001
            pass
    return done
