"""Felles, mellomlagret oversikt over prosessene (Linux): én rask skanning av /proc/*/comm deles av
spill-, klipp- og shadersjekken i stedet for at hver av dem går gjennom alle prosessene selv."""
import os
import time

_CACHE = {"t": 0.0, "comm": {}}


def comm_map(max_age=2.0):
    """{pid: kort navn (comm, maks 15 tegn)} – oppdateres høyst hvert max_age sekund."""
    now = time.monotonic()
    if now - _CACHE["t"] < max_age:
        return _CACHE["comm"]
    out = {}
    try:
        names = os.listdir("/proc")
    except OSError:
        names = []
    for d in names:
        if not d.isdigit():
            continue
        try:
            with open(f"/proc/{d}/comm", "rb") as f:
                out[int(d)] = f.read().strip().decode(errors="replace")
        except OSError:
            continue
    _CACHE.update(t=now, comm=out)
    return out


def cmdline(pid):
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return f.read()
    except OSError:
        return b""


def pids_named(*names, max_age=2.0):
    want = set(names)
    return [p for p, c in comm_map(max_age).items() if c in want]
