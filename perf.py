"""Kontrollsenters eget forbruk (prosessor, minne, disk) og «Minimal prosessbruk».

Minimal prosessbruk:
  * ingen effekter (levende bakgrunn, animasjoner, glød og lys som følger musa er av)
  * vinduet oppdateres hvert 3. sekund i stedet for hvert sekund (dataene samles fortsatt)
  * fargeskiftende «levende tema» står stille
  * valgfrie ting i bakgrunnen (prestasjoner, «Dagen i dag», sparkline-grafer) går sjeldnere
Varsler, vifter, mobilappen og alt som er viktig virker som før.

Windows: effektene står på «Rolig» som standard (full levende bakgrunn er tung for GTK på Windows).
"""
import json
import os
import sys
import threading
import time

IS_WIN = sys.platform == "win32"
CFG = os.path.expanduser("~/.config/systemmonitor/ytelse.json")
_STATE = {"eco": None}


def eco():
    if _STATE["eco"] is None:
        try:
            _STATE["eco"] = bool(json.load(open(CFG)).get("eco", False))
        except (OSError, ValueError):
            _STATE["eco"] = False
    return _STATE["eco"]


def set_eco(on, window=None):
    _STATE["eco"] = bool(on)
    try:
        d = json.load(open(CFG))
    except (OSError, ValueError):
        d = {}
    d["eco"] = bool(on)
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    json.dump(d, open(CFG, "w"))
    try:                                                   # effekter av/på med en gang
        import effects
        from gi.repository import Gtk
        for w in ([window] if window else Gtk.Window.list_toplevels()):
            if w is not None:
                effects.apply(w)
                (w.add_css_class if on else w.remove_css_class)("ks-eco")
    except Exception:  # noqa: BLE001
        pass


def interval_factor():
    """Hvor mange sekunder mellom hver oppdatering av vinduet."""
    return 3 if eco() else 1


# --------------------------------------------------------------------------
# Eget forbruk – målt i en bakgrunnstråd (vinduet venter aldri)
# --------------------------------------------------------------------------
_USE = {"cpu": 0.0, "rss": 0, "read": 0.0, "write": 0.0, "threads": 0, "t": 0}
_RUN = []


def _loop():
    import psutil
    p = psutil.Process()
    p.cpu_percent(None)
    last_io, last_t = None, time.monotonic()
    ncpu = psutil.cpu_count() or 1
    while True:
        time.sleep(2)
        try:
            now = time.monotonic()
            cpu = p.cpu_percent(None) / ncpu                 # i prosent av hele maskinen
            mem = p.memory_info().rss
            try:
                io = p.io_counters()
                rb, wb = io.read_bytes, io.write_bytes
            except (AttributeError, psutil.Error):
                rb = wb = 0
            if last_io:
                dt = max(0.1, now - last_t)
                _USE["read"] = max(0.0, (rb - last_io[0]) / dt)
                _USE["write"] = max(0.0, (wb - last_io[1]) / dt)
            last_io, last_t = (rb, wb), now
            _USE.update(cpu=round(cpu, 1), rss=mem, threads=p.num_threads(), t=time.time())
        except Exception:  # noqa: BLE001
            pass


def usage():
    """{"cpu": % av maskinen, "rss": byte, "read"/"write": byte/s, "threads"}"""
    if not _RUN:
        _RUN.append(threading.Thread(target=_loop, daemon=True, name="eget-forbruk"))
        _RUN[0].start()
    return dict(_USE)


def human(n):
    for u in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:.0f} {u}" if u in ("B", "KB") else f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} TB"
