"""NVIDIA sin offisielle liste over spill med DLSS – hentes jevnlig, og varsler når et nytt spill får DLSS 5.

Kilde: tabellen på nvidia.com/geforce/news/nvidia-rtx-games-engines-apps (JSON-filen siden selv bruker).
DLSS 5 står der som «3D-Guided Neural Rendering» i AI-kolonnen.
"""
import json
import os
import re
import time
import urllib.request

URL = ("https://www.nvidia.com/content/dam/en-zz/Solutions/geforce/news/nvidia-rtx-games-engines-apps/"
       "dlss-rt-games-apps-overrides.json")
PAGE = "https://www.nvidia.com/en-eu/geforce/news/nvidia-rtx-games-engines-apps/"
CACHE = os.path.expanduser("~/.cache/systemmonitor/nvidia-dlss-spill.json")
SEEN = os.path.expanduser("~/.config/systemmonitor/dlss5-sett.json")
MAX_AGE = 12 * 3600
DLSS5 = "neural rendering"


def _load():
    try:
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def refresh(force=False):
    """Hent lista på nytt hvis den er eldre enn 12 timer. Returnerer {"t", "rows"}."""
    c = _load()
    if c and not force and time.time() - c.get("t", 0) < MAX_AGE:
        return c
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 Kontrollsenter"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
        rows = [x for x in data.get("data", []) if x.get("name")]
        if not rows:
            raise ValueError("tom liste")
        c = {"t": time.time(), "rows": rows}
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        with open(CACHE + ".tmp", "w", encoding="utf-8") as f:
            json.dump(c, f)
        os.replace(CACHE + ".tmp", CACHE)
    except Exception:  # noqa: BLE001
        if c is None:
            return {"t": 0, "rows": []}
    return c


def _norm(name):
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower().replace("™", "").replace("®", "").replace("&", "and"))


def _installed():
    try:
        import games
        return {_norm(g["name"]): g["name"] for g in games.installed_games()}
    except Exception:  # noqa: BLE001
        return {}


def dlss5_games(refresh_if_old=False):
    """[{"name", "installed", "mfg", "rt"}] – spillene med DLSS 5, installerte først."""
    c = refresh() if refresh_if_old else (_load() or {"rows": []})
    inst = _installed()
    out = [{"name": str(r["name"]), "installed": _norm(r["name"]) in inst,
            "mfg": r.get("dlss multi frame generation", ""), "rt": r.get("ray tracing", "")}
           for r in c.get("rows", []) if DLSS5 in str(r.get("ai", "")).lower()]
    return sorted(out, key=lambda g: (not g["installed"], g["name"].lower()))


def updated():
    c = _load()
    return time.strftime("%d.%m.%Y %H:%M", time.localtime(c["t"])) if c and c.get("t") else None


def features(name):
    """Hva NVIDIA oppgir for ett spill, kort på norsk – f.eks. «DLSS 5 · 6× bildegenerering · strålesporing»."""
    c = _load() or {"rows": []}
    n = _norm(name)
    r = next((x for x in c.get("rows", []) if _norm(x["name"]) == n), None)
    if not r:
        return ""
    bits = []
    if DLSS5 in str(r.get("ai", "")).lower():
        bits.append("DLSS 5")
    mfg = r.get("dlss multi frame generation", "")
    if mfg:
        bits.append(mfg.split(",")[-1].strip().replace("X", "×") + " bildegenerering")
    elif r.get("dlss frame generation"):
        bits.append("bildegenerering")
    if r.get("dlss super resolution"):
        bits.append("DLSS")
    if r.get("dlss ray reconstruction"):
        bits.append("Ray Reconstruction")
    if r.get("ray tracing"):
        bits.append("path tracing" if r["ray tracing"] == "Path Tracing" else "strålesporing")
    return " · ".join(bits)


def check_new(notify):
    """Kalles jevnlig: varsle om spill som har fått DLSS 5 siden sist."""
    c = refresh()
    if not c.get("rows"):
        return
    now = [g["name"] for g in dlss5_games()]
    try:
        seen = set(json.load(open(SEEN, encoding="utf-8")))
    except (OSError, ValueError):
        seen = None
    os.makedirs(os.path.dirname(SEEN), exist_ok=True)
    with open(SEEN, "w", encoding="utf-8") as f:
        json.dump(now, f)
    if seen is None:                                 # første gang: bare husk lista
        return
    new = [n for n in now if n not in seen]
    if new:
        inst = [g["name"] for g in dlss5_games() if g["installed"] and g["name"] in new]
        notify("dlss5", "Nytt med DLSS 5: " + ", ".join(new[:3]) + (" …" if len(new) > 3 else ""),
               ("Du har " + ", ".join(inst) + " installert – slå på DLSS 5 i spillets grafikkmeny."
                if inst else "Se lista under GPU-innstillinger → DLSS, Reflex og G-SYNC."))
