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


def _flag(key):
    try:
        return bool(json.load(open(CFG)).get(key, False))
    except (OSError, ValueError):
        return False


_FLAGS = {}


def flag(key):
    """«mem» (mindre minnebruk) eller «ssd» (mindre skriving til disk)."""
    if key not in _FLAGS:
        _FLAGS[key] = _flag(key)
    return _FLAGS[key]


def set_flag(key, on):
    _FLAGS[key] = bool(on)
    try:
        d = json.load(open(CFG))
    except (OSError, ValueError):
        d = {}
    d[key] = bool(on)
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    json.dump(d, open(CFG, "w"))
    if key == "ssd":
        try:
            import applog
            applog.set_quiet(bool(on))
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------
# Mindre minnebruk
# --------------------------------------------------------------------------
# GTK holder på sidene du har åpnet så lenge programmet kjører (de kan ikke tas ut av minnet trygt). Med
# «Mindre minnebruk» startes Kontrollsenter derfor stille på nytt i statusfeltet når vinduet har vært lukket en
# stund og det bruker mye minne – en fersk start bruker bare en tredjedel. Aldri mens du spiller eller noe pågår.
HIDDEN_FOR = 180          # sekunder vinduet må ha vært lukket
MEM_LIMIT = 200 * 2 ** 20  # bare når Kontrollsenter bruker mer enn dette
MIN_GAP = 1800            # høyst hver halvtime


def trim():
    """Gi ubrukt minne tilbake til systemet (Windows: tøm arbeidsminnet)."""
    import gc
    gc.collect()
    try:
        import ctypes
        if IS_WIN:
            ctypes.windll.psapi.EmptyWorkingSet(ctypes.windll.kernel32.GetCurrentProcess())
        else:
            ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:  # noqa: BLE001
        pass


_MEM = {"hidden": None, "trim": 0, "started": time.monotonic()}


def mem_tick(win):
    """Kalles hvert 30. sekund fra bakgrunnen."""
    if not flag("mem"):
        return
    try:
        now = time.monotonic()
        if win.get_mapped():
            _MEM["hidden"] = None
            return
        _MEM["hidden"] = _MEM["hidden"] or now
        if now - _MEM["trim"] > 300:
            _MEM["trim"] = now
            trim()
        if now - _MEM["hidden"] < HIDDEN_FOR or now - _MEM["started"] < MIN_GAP:
            return
        import psutil
        if psutil.Process().memory_info().rss < MEM_LIMIT:
            return
        bg = getattr(win, "bg", None)
        if getattr(bg, "game_name", None):
            return
        try:
            import progress
            if progress.active():
                return
        except Exception:  # noqa: BLE001
            pass
        import applog
        applog.log.info("Mindre minnebruk: starter stille på nytt (%s brukt)",
                        human(psutil.Process().memory_info().rss))
        win.restart_app(hidden=True)
    except Exception:  # noqa: BLE001
        import applog
        applog.log.exception("mindre minnebruk")


# --------------------------------------------------------------------------
# Lagring på disk – én bryter per ting (av = verken skrives eller leses; holdes bare i minnet mens programmet kjører)
# --------------------------------------------------------------------------
DISK_ITEMS = [
    ("historikk", "Historikk", "Temperatur, last og strøm hvert 10. sekund (Historikk-siden)."),
    ("strom", "Strømforbruk per dag", "kWh og kroner per dag og uke."),
    ("spilltid", "Spilletid", "Spilletid per dag. Av: telles bare mens Kontrollsenter kjører – grensene "
                              "nullstilles ved omstart."),
    ("hendelser", "Hendelser", "Tidslinjen og varslene i mobilappen."),
    ("logg", "Logg", "Feilloggen – brukes når noe skal feilsøkes."),
    ("topp", "Toppverdier", "Høyeste klokkefrekvens målt i hver strømmodus."),
    ("tidsmaskin", "Tidsmaskin", "Kopi av innstillingene når de endres, så du kan gå tilbake (bare små filer)."),
] + ([("pssvar", "Windows-svar", "Husker svar fra Windows mellom omstarter, så vinduet åpner raskere.")]
     if IS_WIN else [])


def _cfg():
    try:
        return json.load(open(CFG))
    except (OSError, ValueError):
        return {}


def _save_cfg(d):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    json.dump(d, open(CFG, "w"))


_DISK = {}


def disk_ok(key):
    """Skal denne tingen skrives til og leses fra disk?"""
    if not _DISK:
        d = _cfg()
        _DISK.update(nodisk=bool(d.get("nodisk")), off=set(d.get("disk_off") or []))
    return not _DISK["nodisk"] and key not in _DISK["off"]


def set_disk(key, on):
    d = _cfg()
    off = set(d.get("disk_off") or [])
    (off.discard if on else off.add)(key)
    d["disk_off"] = sorted(off)
    _save_cfg(d)
    _DISK.clear()
    _disk_changed()


def no_disk():
    disk_ok("x")
    return _DISK["nodisk"]


def set_no_disk(on):
    """Hovedbryteren: ingen lesing og skriving til disk, og oppdateringer bare manuelt."""
    import updates
    d = _cfg()
    if on and not d.get("nodisk"):
        d["auto_before"] = updates.auto_on()
        updates.set_auto(False)
    elif not on and d.get("nodisk"):
        updates.set_auto(d.get("auto_before", True))
    d["nodisk"] = bool(on)
    _save_cfg(d)
    _DISK.clear()
    _disk_changed()


def _disk_changed():
    try:
        import applog
        applog.apply_level()
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------
# Spar alt: minst mulig prosessor og minne (slår på alle sparemodusene og stopper ekstra ting i bakgrunnen)
# Varsler, vifter, mobilappen, spilletidsgrenser og familiekontroll virker som før.
# --------------------------------------------------------------------------
def save_all():
    return bool(flag("saveall"))


def set_save_all(on, window=None):
    d = _cfg()
    if on and not d.get("saveall"):
        d["before"] = {"eco": eco(), "mem": flag("mem")}
        _save_cfg(d)
        set_eco(True, window)
        set_flag("mem", True)
    elif not on and d.get("saveall"):
        b = d.get("before") or {}
        set_eco(bool(b.get("eco")), window)
        set_flag("mem", bool(b.get("mem")))
    set_flag("saveall", bool(on))


# --------------------------------------------------------------------------
# Mindre skriving til disk (skåner SSD/M.2)
# --------------------------------------------------------------------------
def save_every(seconds):
    """Hvor ofte noe lagres: vanlig, eller sjeldnere (maks 15 min) med «Mindre skriving til disk»."""
    return max(seconds, 900) if flag("ssd") else seconds


def lowend():
    """«Eldre PC»: alt det grafiske som tar ytelse er av."""
    return bool(flag("lowend"))


def light():
    """Skal effekter, animasjoner og lys som følger musa være av?"""
    return eco() or lowend()


def set_lowend(on, window=None):
    d = _cfg()
    if on and not d.get("lowend"):
        d["lowend_before"] = {"mem": flag("mem")}
        _save_cfg(d)
        set_flag("mem", True)                              # mindre minne når vinduet har vært lukket en stund
    elif not on and d.get("lowend"):
        set_flag("mem", bool((d.get("lowend_before") or {}).get("mem")))
    set_flag("lowend", bool(on))
    apply_graphics(window)


_ANIM = {}


def apply_graphics(window=None):
    """Animasjoner, effekter og minigrafer av/på etter bryterne (kan kalles når som helst)."""
    try:
        from gi.repository import Gtk
        st = Gtk.Settings.get_default()
        if st is not None:
            if "orig" not in _ANIM:
                _ANIM["orig"] = st.get_property("gtk-enable-animations")
            st.set_property("gtk-enable-animations", False if lowend() else _ANIM["orig"])
        import effects
        for w in ([window] if window else Gtk.Window.list_toplevels()):
            if w is not None:
                effects.apply(w)
                (w.add_css_class if lowend() else w.remove_css_class)("ks-lowend")
    except Exception:  # noqa: BLE001
        pass


def old_reason():
    """Hvorfor «Eldre PC» anbefales – tom tekst hvis den ikke gjør det.

    Antall kjerner alene sier lite (en moderne 8-kjerner er rask), så vi ser på kjerner, minne, klokkefrekvens og –
    hvis du har kjørt den – ytelsestesten."""
    try:
        import psutil
        cores = psutil.cpu_count() or 8
        mem = psutil.virtual_memory().total / 2 ** 30
        try:
            mhz = (psutil.cpu_freq() or None).max or 0
        except (AttributeError, NotImplementedError, OSError):
            mhz = 0
    except Exception:  # noqa: BLE001
        return ""
    why = []
    if cores <= 4:
        why.append(f"{cores} kjerner")
    if mem < 7.5:
        why.append(f"{mem:.0f} GB minne")
    if mhz and mhz < 2500 and cores <= 8:
        why.append(f"{mhz / 1000:.1f} GHz")
    try:
        import pctools
        b = (pctools.cfg().get("bench") or [None])[-1]
        if b and b.get("cpuN") and b["cpuN"] < 600:              # ytelsestesten: tregt totalt
            why.append("lav score i ytelsestesten")
    except Exception:  # noqa: BLE001
        pass
    return ", ".join(why)


def looks_old():
    """Grovt anslag: få kjerner, lite minne, lav klokkefrekvens eller lav ytelsestest → «Eldre PC» anbefales."""
    return bool(old_reason())


def interval_factor():
    """Hvor mange sekunder mellom hver oppdatering av vinduet."""
    return 3 if eco() else 2 if lowend() else 1


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
            if now - _USE.get("_uss_t", 0) > 10:              # eget minne (uten delte biblioteker/driver) – dyrere å lese
                try:
                    _USE["uss"] = p.memory_full_info().uss
                except (psutil.Error, AttributeError):
                    _USE["uss"] = mem
                _USE["_uss_t"] = now
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
