"""Volumtastene følger lyden (Linux).

Volumrullen på et headset og volumtastene på tastaturet justerer STANDARDUTGANGEN. Spiller lyden et annet sted
(f.eks. et spill og Discord som husker headsettet, mens standarden er høyttalerne), skjer ingenting – selv om
volumvinduet vises. Kontrollsenter flytter derfor standardutgangen dit lyden faktisk spilles:

  * utgangen der flest programmer spiller blir standard – men bare når den har flere enn standardutgangen
    (f.eks. spill + Discord på headsettet, ingenting på høyttalerne).

Når et headset kobles til og begynner å spille, blir det altså standard av seg selv. Kan slås av på Lyd-siden.
"""
import json
import os
import subprocess
import sys
import time

CFG = os.path.expanduser("~/.config/systemmonitor/lyd.json")
_LAST = {"t": 0}


def enabled():
    try:
        return bool(json.load(open(CFG)).get("follow", True))
    except (OSError, ValueError):
        return True


def set_enabled(on):
    try:
        d = json.load(open(CFG))
    except (OSError, ValueError):
        d = {}
    d["follow"] = bool(on)
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    json.dump(d, open(CFG, "w"))


def _pactl(*a, t=5):
    try:
        return subprocess.run(["pactl", *a], capture_output=True, text=True, timeout=t).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def check():
    """Flytt standardutgangen hvis lyden spilles et annet sted. Returnerer navnet på ny utgang, eller None."""
    if sys.platform == "win32" or not enabled():
        return None
    default = _pactl("get-default-sink").strip()
    if not default:
        return None
    try:
        sinks = json.loads(_pactl("-f", "json", "list", "sinks") or "[]")
        inputs = json.loads(_pactl("-f", "json", "list", "sink-inputs") or "[]")
    except ValueError:
        return None
    def _n(v):                                           # pactl gir nummeret som tall for utganger, tekst for avspilling
        try:
            return int(v)
        except (TypeError, ValueError):
            return None
    by_index = {_n(s.get("index")): s for s in sinks}
    playing, count = {}, {}
    for i in inputs:
        if i.get("corked"):
            continue
        s = by_index.get(_n(i.get("sink")))
        if s is not None:
            playing[s["name"]] = s
            count[s["name"]] = count.get(s["name"], 0) + 1
    if not count:
        return None
    name = max(count, key=lambda k: count[k])
    if name == default or count[name] <= count.get(default, 0):
        return None                                         # standarden spiller like mye (eller mer) – la den være
    s = playing[name]
    if s.get("state") not in ("RUNNING", "IDLE"):
        return None
    _pactl("set-default-sink", name)
    try:
        import applog
        applog.log.info("Lyd: standardutgang → %s (der lyden spilles)", s.get("description") or name)
    except Exception:  # noqa: BLE001
        pass
    return s.get("description") or name


def tick():
    """Kalles jevnlig fra bakgrunnen (billig: to pactl-kall hvert 4. sekund)."""
    if time.time() - _LAST["t"] < 4:
        return None
    _LAST["t"] = time.time()
    return check()
