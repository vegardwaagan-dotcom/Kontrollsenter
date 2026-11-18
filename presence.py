"""Hjemme/borte: telefonene i huset på hjemmenettet styrer scener («Når noen kommer hjem» / «Når alle har dratt»).

En telefon regnes som hjemme hvis den svarer på ping, står som aktiv i nettverkstabellen (ARP), eller
Kontrollsenter-appen på den har vært i kontakt med PC-en nylig. Telefoner sover på wifi, så «borte» settes først
etter et visst antall minutter uten livstegn (standard 20). Alt skjer lokalt – ingenting sendes ut av huset.
"""
import json
import os
import re
import subprocess
import sys
import threading
import time

CFG = os.path.expanduser("~/.config/systemmonitor/tilstede.json")
IS_WIN = sys.platform == "win32"
SEEN_API = {}                    # ip -> sist appen på telefonen snakket med PC-en (fylles av remote.py)
_STATE = {"home": None, "who": {}, "changed": 0}
_LOCK = threading.Lock()


def cfg():
    try:
        with open(CFG) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"phones": [], "away_min": 20}


def save_cfg(d):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    with open(CFG, "w") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)


def seen_api(ip):
    SEEN_API[ip.replace("::ffff:", "")] = time.time()


def _ping(ip):
    cmd = ["ping", "-n", "1", "-w", "800", ip] if IS_WIN else ["ping", "-c", "1", "-W", "1", ip]
    try:
        return subprocess.run(cmd, capture_output=True, timeout=3).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _neigh():
    """mac -> (ip, aktiv?) fra nettverkstabellen."""
    out = {}
    if IS_WIN:
        return out
    try:
        txt = subprocess.run(["ip", "neigh"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return out
    for m in re.finditer(r"^(\d+\.\d+\.\d+\.\d+) .*lladdr ([0-9a-f:]{17}) (\w+)", txt, re.M):
        out[m.group(2).lower()] = (m.group(1), m.group(3) in ("REACHABLE", "DELAY", "PROBE"))
    return out


def check():
    """Oppdater hvem som er hjemme. Returnerer («home»/«away»/None ved ingen endring, navn)."""
    c = cfg()
    phones = c.get("phones") or []
    if not phones:
        return None, None
    now = time.time()
    neigh = _neigh()
    who = _STATE["who"]
    for p in phones:
        mac = (p.get("mac") or "").lower()
        ip = neigh.get(mac, (p.get("ip"), False))[0] if mac else p.get("ip")
        alive = bool(ip) and (now - SEEN_API.get(ip, 0) < 600 or _ping(ip))
        if not alive and mac:
            alive = _neigh().get(mac, (None, False))[1]
        if ip and ip != p.get("ip"):
            p["ip"] = ip
        if alive:
            who[p["name"]] = now
    away_s = max(5, int(c.get("away_min", 20))) * 60
    home_now = [n for n, t in who.items() if now - t < away_s and any(p["name"] == n for p in phones)]
    is_home = bool(home_now)
    with _LOCK:
        prev = _STATE["home"]
        _STATE["home"] = is_home
        if prev is None or prev == is_home:
            return None, None
        _STATE["changed"] = now
    save_cfg(c)
    return ("home" if is_home else "away"), (", ".join(home_now) if is_home else None)


def state():
    c = cfg()
    now = time.time()
    away_s = max(5, int(c.get("away_min", 20))) * 60
    return {"home": _STATE["home"], "changed": _STATE["changed"], "away_min": c.get("away_min", 20),
            "phones": [{**p, "home": now - _STATE["who"].get(p["name"], 0) < away_s} for p in c.get("phones") or []]}


_LAST = [0.0]


def tick(win):
    """Kalles jevnlig fra bakgrunnen; sjekker hvert minutt i en egen tråd."""
    if time.time() - _LAST[0] < 60 or not cfg().get("phones"):
        return
    _LAST[0] = time.time()

    def work():
        try:
            ev, who = check()
        except Exception:  # noqa: BLE001
            return
        if ev:
            from gi.repository import GLib
            import scenes
            GLib.idle_add(lambda: (scenes.on_event(win, ev, who), False)[1])
    threading.Thread(target=work, daemon=True).start()
