"""Finner eksterne verktøy uansett hvordan de er installert (systempakke, pipx eller egen venv).

Kontrollsenter bruker TRCC (trcc-linux) for CPU-skjermen. På Bazzite følger den med i
/usr/bin, på andre distroer installeres den med pipx av installer.sh.
"""
import functools
import os
import subprocess

HOME = os.path.expanduser("~")
TRCC_CANDIDATES = [
    "/usr/bin/trcc",
    "/usr/local/bin/trcc",
    os.path.join(HOME, ".local/bin/trcc"),
    os.path.join(HOME, ".local/share/systemmonitor/trcc-venv/bin/trcc"),
]


def _works(path):
    if not (os.path.isfile(path) and os.access(path, os.X_OK)):
        return False
    try:
        return subprocess.run([path, "--version"], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


_CACHE_FILE = os.path.join(HOME, ".cache", "systemmonitor", "trcc-sjekk.json")


@functools.lru_cache(maxsize=1)
def find_trcc():
    """Første trcc-kommando som faktisk virker (en ødelagt gammel installasjon hoppes over).
    Svaret huskes på disk sammen med filens endringstid – «trcc --version» kjøres bare når noe er endret."""
    import json
    try:
        c = json.load(open(_CACHE_FILE))
        p = c.get("path")
        if p is None and all(not os.path.exists(x) for x in TRCC_CANDIDATES) == c.get("none_missing"):
            if c.get("none") and c.get("stamp") == _stamp():
                return None
        elif p and os.path.exists(p) and os.path.getmtime(p) == c.get("mtime"):
            return p
    except (OSError, ValueError):
        pass
    found = next((p for p in TRCC_CANDIDATES if _works(p)), None)
    try:
        os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
        json.dump({"path": found, "mtime": os.path.getmtime(found) if found else None, "none": found is None,
                   "stamp": _stamp(), "none_missing": all(not os.path.exists(x) for x in TRCC_CANDIDATES)},
                  open(_CACHE_FILE, "w"))
    except OSError:
        pass
    return found


def _stamp():
    return [os.path.getmtime(p) if os.path.exists(p) else 0 for p in TRCC_CANDIDATES]


