"""Krasj- og strømbruddlogg (17).

Kontrollsenter skriver et lite «livstegn» hvert minutt (tid, spill, temperaturer, strøm). Avsluttes PC-en på
vanlig måte, merkes det. Starter PC-en igjen uten at forrige økt ble avsluttet, var det et krasj, en frys eller
strømbrudd – og da vises når det skjedde og hva som foregikk rett før.
"""
import json
import os
import sys
import time

DATA = os.path.expanduser("~/.local/share/systemmonitor")
PULSE = os.path.join(DATA, "livstegn.json")
LOG = os.path.join(DATA, "krasjlogg.json")


def _boot_id():
    try:
        if sys.platform == "win32":
            import psutil
            return str(int(psutil.boot_time()))
        return open("/proc/sys/kernel/random/boot_id").read().strip()
    except Exception:  # noqa: BLE001
        return "?"


def _ok():
    try:
        import perf
        return perf.disk_ok("logg")
    except Exception:  # noqa: BLE001
        return True


def _write(path, d):
    os.makedirs(DATA, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f)
    os.replace(tmp, path)


def pulse(win, clean=False):
    """Hvert minutt (og ved vanlig avslutning med clean=True)."""
    if not _ok():
        return
    try:
        import perf
        if not clean and perf.flag("ssd") and time.time() - _LAST[0] < 300:
            return
    except Exception:  # noqa: BLE001
        pass
    _LAST[0] = time.time()
    nv = win.nvidia.data if getattr(win, "nvidia", None) and win.nvidia.available else {}
    d = {"t": time.time(), "boot": _boot_id(), "clean": clean,
         "game": getattr(getattr(win, "bg", None), "game_name", None),
         "cpu_t": getattr(win, "_cpu_t", None), "gpu_t": (nv or {}).get("temp"),
         "watts": (getattr(win, "_power", None) or {}).get("total")}
    try:
        _write(PULSE, d)
    except OSError:
        pass


_LAST = [0.0]


def check_at_start():
    """Ved oppstart: ble forrige økt avsluttet uten «vanlig avslutning» før en ny oppstart av PC-en?
    Returnerer hendelsen (ordbok) eller None."""
    if not _ok():
        return None
    try:
        last = json.load(open(PULSE))
    except (OSError, ValueError):
        return None
    if last.get("clean") or last.get("boot") == _boot_id():
        return None                                    # avsluttet pent, eller samme oppstart (bare programmet)
    if sys.platform == "win32" and not _win_unexpected(last.get("t") or 0):
        return None                                    # Windows lukker programmer brått ved vanlig avslutning
    ev = {"t": last.get("t"), "game": last.get("game"), "cpu_t": last.get("cpu_t"), "gpu_t": last.get("gpu_t"),
          "watts": last.get("watts")}
    log = history()
    if not any(abs((x.get("t") or 0) - (ev["t"] or 0)) < 1 for x in log):
        log.append(ev)
        try:
            _write(LOG, log[-50:])
        except OSError:
            pass
    try:                                               # ikke meld samme hendelse to ganger
        last["clean"] = True
        _write(PULSE, last)
    except OSError:
        pass
    return ev


def _win_unexpected(since):
    """Windows: logget systemet en uventet avslutning (Kernel-Power 41 / EventLog 6008) etter siste livstegn?"""
    try:
        import winsupport
        start = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(max(0, since - 120)))
        ps = ("(Get-WinEvent -FilterHashtable @{LogName='System'; Id=41,6008; StartTime=[datetime]'" + start +
              "'} -MaxEvents 1 -ErrorAction SilentlyContinue | Measure-Object).Count")
        _c, out = winsupport.run(["powershell", "-NoProfile", "-Command", ps], 60)
        return out.strip().splitlines()[-1].strip() not in ("", "0")
    except Exception:  # noqa: BLE001
        return False


def history():
    try:
        return json.load(open(LOG))
    except (OSError, ValueError):
        return []


def text(ev):
    when = time.strftime("%d.%m kl. %H:%M", time.localtime(ev.get("t") or 0))
    bits = []
    if ev.get("game"):
        bits.append(f"under {ev['game']}")
    if ev.get("cpu_t") is not None:
        bits.append(f"CPU {ev['cpu_t']:.0f} °C")
    if ev.get("gpu_t") is not None:
        bits.append(f"GPU {ev['gpu_t']:.0f} °C")
    if ev.get("watts"):
        bits.append(f"{ev['watts']:.0f} W")
    hot = (ev.get("cpu_t") or 0) >= 95 or (ev.get("gpu_t") or 0) >= 90
    why = " Den var svært varm – sjekk vifter og støv." if hot else \
        " Kan være strømbrudd, frys eller at den ble holdt inne på av-knappen."
    return f"PC-en stoppet uten å avslutte {when}" + (f" ({', '.join(bits)})" if bits else "") + "." + why
