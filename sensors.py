"""Kontrollsenter – lesing av maskinvaredata (CPU, minne, disk, nett, GPU, temperatur, batteri)."""
import glob
import json
import os
import re
import shutil
import subprocess
import threading
import time
from collections import deque

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402,F401


import sys

IS_WIN = sys.platform == "win32"     # Windows-versjonen bruker sensors_win.py for maskinvaredata
HISTORY = 60          # antall punkter i grafene (sekunder)
INTERVAL_MS = 1000    # oppdateringsintervall


# --------------------------------------------------------------------------
# Hjelpefunksjoner for å lese data
# --------------------------------------------------------------------------
def read(path, default=None):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def fmt_bytes(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n:.0f} B"
        n /= 1024


def fmt_rate(n):
    return fmt_bytes(n) + "/s"


class CpuReader:
    def __init__(self):
        self.prev = self._snap()

    @staticmethod
    def _snap():
        out = {}
        with open("/proc/stat") as f:
            for line in f:
                if not line.startswith("cpu"):
                    break
                parts = line.split()
                vals = list(map(int, parts[1:]))
                idle = vals[3] + vals[4]
                out[parts[0]] = (sum(vals), idle)
        return out

    def usage(self):
        now = self._snap()
        res = {}
        for k, (tot, idle) in now.items():
            ptot, pidle = self.prev.get(k, (tot, idle))
            dt = tot - ptot
            res[k] = 0.0 if dt <= 0 else 100.0 * (1 - (idle - pidle) / dt)
        self.prev = now
        return res

    @staticmethod
    def freq_ghz():
        vals = []
        for p in glob.glob("/sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_cur_freq"):
            v = read(p)
            if v and v.isdigit():
                vals.append(int(v))
        return (max(vals) / 1e6) if vals else None


def cpu_freqs_ghz():
    """(grunnfrekvens, maks turbo) i GHz, eller None der det ikke finnes."""
    base = read("/sys/devices/system/cpu/cpu0/acpi_cppc/nominal_freq")
    mx = read("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq")
    return (int(base) / 1000 if base and base.isdigit() else None,
            int(mx) / 1e6 if mx and mx.isdigit() else None)


def cpu_model():
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return "CPU"


def meminfo():
    info = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, v = line.split(":", 1)
            info[k] = int(v.split()[0]) * 1024
    return info


_HW = {"t": 0.0, "list": []}


def _hwmon_inputs():
    """[(enhet, etikett, sti)] – sensorene endrer seg sjelden, så lista lages på nytt bare hvert minutt."""
    import time as _time
    now = _time.monotonic()
    if now - _HW["t"] < 60 and _HW["list"]:
        return _HW["list"]
    lst = []
    for h in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
        name = read(os.path.join(h, "name"), "?")
        for inp in sorted(glob.glob(os.path.join(h, "temp*_input"))):
            label = read(inp.replace("_input", "_label"), os.path.basename(inp).split("_")[0])
            if _NOT_TEMP.search(label or ""):
                continue
            lst.append((name, label, inp))
    _HW.update(t=now, list=lst)
    return lst


_SLOW = {}          # sensorbrikke -> {"t": sist lest, "vals": {sti: verdi}, "slow": bool}


def hwmon_temps():
    """Returnerer liste med (enhet, etikett, °C).

    Noen sensorbrikker er trege å lese (f.eks. nct67xx på hovedkortet henter alle registrene på nytt, RAM- og
    NVMe-sensorer går over en treg buss). De leses bare hvert 5. sekund; raske (CPU, GPU) hvert sekund."""
    import time as _time
    now = _time.monotonic()
    by_dev = {}
    for name, label, inp in _hwmon_inputs():
        by_dev.setdefault(os.path.dirname(inp), []).append((name, label, inp))
    out = []
    for dev, items in by_dev.items():
        st = _SLOW.setdefault(dev, {"t": 0.0, "vals": {}, "slow": False})
        if not (st["slow"] and now - st["t"] < 5):
            t0 = _time.perf_counter()
            st["vals"] = {inp: read(inp) for _n, _l, inp in items}
            st["slow"] = st["slow"] or (_time.perf_counter() - t0) > 0.001     # treg én gang = treg
            st["t"] = now
        for name, label, inp in items:
            v = st["vals"].get(inp)
            if not v or not v.lstrip("-").isdigit():
                continue
            t = int(v) / 1000
            if plausible(label, t):
                out.append((name, label, t))
    return out


# Navn på «temperaturer» som egentlig er grenseverdier/innstillinger (f.eks. RAM: «Thermal Sensor Critical High
# Limit: 85») – de er ikke målinger og skal ikke vises eller gi rødt varsel. «Core Max» er en ekte måling.
_NOT_TEMP = re.compile(r"limit|threshold|resolution|distance|tj\s*max|warning|critical|alarm|trip|hyst|"
                       r"calibration|offset", re.I)


def plausible(label, t):
    """Ekte måling? Hopper over grenseverdier og frakoblede sensorer (0 °C, −62 °C, 127 °C o.l.)."""
    if t is None or _NOT_TEMP.search(label or ""):
        return False
    return 0 < t < 125


def cpu_temp(temps):
    for dev, label, t in temps:
        if dev == "k10temp" and label == "Tctl":
            return t
    for dev, label, t in temps:
        if dev in ("coretemp", "k10temp", "zenpower"):
            return t
    return None


NICE_DEVICE = {
    "k10temp": "CPU",
    "coretemp": "CPU",
    "amdgpu": "AMD GPU",
    "nvme": "NVMe",
    "asusec": "Hovedkort",
    "spd5118": "RAM",
}


class DiskReader:
    def __init__(self):
        self.prev = self._snap()
        self.prev_t = time.monotonic()

    @staticmethod
    def _snap():
        r = w = 0
        try:
            with open("/proc/diskstats") as f:
                for line in f:
                    p = line.split()
                    name = p[2]
                    # bare hele disker (ikke partisjoner/loop/zram)
                    if name.startswith(("loop", "ram", "zram", "dm-")):
                        continue
                    if not os.path.exists(f"/sys/block/{name}"):
                        continue
                    r += int(p[5]) * 512
                    w += int(p[9]) * 512
        except OSError:
            pass
        return r, w

    def rates(self):
        now, t = self._snap(), time.monotonic()
        dt = max(t - self.prev_t, 1e-3)
        rr = (now[0] - self.prev[0]) / dt
        wr = (now[1] - self.prev[1]) / dt
        self.prev, self.prev_t = now, t
        return max(rr, 0), max(wr, 0)


class NetReader:
    def __init__(self):
        self.prev = self._snap()
        self.prev_t = time.monotonic()

    @staticmethod
    def _snap():
        rx = tx = 0
        try:
            with open("/proc/net/dev") as f:
                for line in f.readlines()[2:]:
                    iface, data = line.split(":", 1)
                    iface = iface.strip()
                    if iface == "lo" or iface.startswith(("veth", "docker", "br-", "virbr")):
                        continue
                    d = data.split()
                    rx += int(d[0])
                    tx += int(d[8])
        except OSError:
            pass
        return rx, tx

    def rates(self):
        now, t = self._snap(), time.monotonic()
        dt = max(t - self.prev_t, 1e-3)
        rx = (now[0] - self.prev[0]) / dt
        tx = (now[1] - self.prev[1]) / dt
        self.prev, self.prev_t = now, t
        return max(rx, 0), max(tx, 0)


class _Nvml:
    """Direkte kall til NVIDIAs bibliotek (libnvidia-ml) – ingen nytt program hvert sekund."""

    def __init__(self):
        import ctypes
        self.C = ctypes
        self.lib = ctypes.CDLL("nvml.dll" if IS_WIN else "libnvidia-ml.so.1")
        if self.lib.nvmlInit_v2() != 0:
            raise OSError("nvmlInit feilet")
        self.h = ctypes.c_void_p()
        if self.lib.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(self.h)) != 0:
            raise OSError("fant ingen NVIDIA-GPU")

    def _u(self, fn, *extra):
        v = self.C.c_uint()
        return v.value if getattr(self.lib, fn)(self.h, *extra, self.C.byref(v)) == 0 else None

    def _static(self):
        import time as _time
        st = getattr(self, "_st", None)
        if st and _time.monotonic() - st["t"] < 30:
            return st
        C, lib, h = self.C, self.lib, self.h
        name = C.create_string_buffer(96)
        lib.nvmlDeviceGetName(h, name, 96)
        lo, hi = C.c_uint(), C.c_uint()
        ok_c = lib.nvmlDeviceGetPowerManagementLimitConstraints(h, C.byref(lo), C.byref(hi)) == 0
        default = self._u("nvmlDeviceGetPowerManagementDefaultLimit")
        self._st = {"t": _time.monotonic(), "name": name.value.decode(errors="replace"),
                    "clock_max": self._u("nvmlDeviceGetMaxClockInfo", 0),
                    "limits": (lo.value / 1000, default / 1000, hi.value / 1000) if ok_c and default else None}
        return self._st

    def read(self):
        C, lib, h = self.C, self.lib, self.h
        st = self._static()

        class Util(C.Structure):
            _fields_ = [("gpu", C.c_uint), ("memory", C.c_uint)]

        class Mem(C.Structure):
            _fields_ = [("total", C.c_ulonglong), ("free", C.c_ulonglong), ("used", C.c_ulonglong)]
        class Mem2(C.Structure):                       # v2 regner ikke med reservert minne (som nvidia-smi)
            _fields_ = [("version", C.c_uint), ("total", C.c_ulonglong), ("reserved", C.c_ulonglong),
                        ("free", C.c_ulonglong), ("used", C.c_ulonglong)]
        util, mem = Util(), Mem2()
        mem.version = C.sizeof(Mem2) | (2 << 24)
        ok_u = lib.nvmlDeviceGetUtilizationRates(h, C.byref(util)) == 0
        ok_m = hasattr(lib, "nvmlDeviceGetMemoryInfo_v2") and lib.nvmlDeviceGetMemoryInfo_v2(h, C.byref(mem)) == 0
        if not ok_m:
            mem = Mem()
            ok_m = lib.nvmlDeviceGetMemoryInfo(h, C.byref(mem)) == 0
        mw = lambda v: v / 1000 if v is not None else None          # noqa: E731
        return {
            "name": st["name"],
            "util": util.gpu if ok_u else None,
            "mem_used": mem.used / 1048576 if ok_m else None, "mem_total": mem.total / 1048576 if ok_m else None,
            "temp": self._u("nvmlDeviceGetTemperature", 0),
            "power": mw(self._u("nvmlDeviceGetPowerUsage")),
            "fan": self._u("nvmlDeviceGetFanSpeed"),
            "limit": mw(self._u("nvmlDeviceGetEnforcedPowerLimit")),
            "clock": self._u("nvmlDeviceGetClockInfo", 0), "clock_max": st["clock_max"],
            "limits": st["limits"],
        }


class NvidiaReader:
    """NVIDIA-data: via NVML (raskt, ingen nye prosesser), ellers nvidia-smi i en bakgrunnstråd."""

    FIELDS = "name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw,fan.speed,power.limit,clocks.gr,clocks.max.gr,power.min_limit,power.default_limit,power.max_limit"

    def __init__(self):
        self.data = None
        self._busy = False
        try:
            self.nvml = _Nvml()
            self.available = True
        except (OSError, AttributeError):
            self.nvml = None
            self.available = shutil.which("nvidia-smi") is not None

    def poll(self):
        if self.nvml:
            try:
                self.data = self.nvml.read()
                return
            except Exception:  # noqa: BLE001 – faller tilbake til nvidia-smi
                self.nvml = None
        if not self.available or self._busy:
            return
        self._busy = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            out = subprocess.run(
                ["nvidia-smi", f"--query-gpu={self.FIELDS}", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            ).stdout.strip().splitlines()
            if out:
                p = [x.strip() for x in out[0].split(",")]

                def num(x):
                    try:
                        return float(x)
                    except ValueError:
                        return None

                self.data = {
                    "name": p[0], "util": num(p[1]), "mem_used": num(p[2]),
                    "mem_total": num(p[3]), "temp": num(p[4]),
                    "power": num(p[5]), "fan": num(p[6]),
                    "limit": num(p[7]) if len(p) > 7 else None,
                    "clock": num(p[8]) if len(p) > 8 else None,
                    "clock_max": num(p[9]) if len(p) > 9 else None,
                    "limits": tuple(num(x) for x in p[10:13]) if len(p) > 12 else None,
                }
        except (OSError, subprocess.SubprocessError, IndexError):
            pass
        finally:
            self._busy = False


def amd_gpus():
    """Finn AMD-GPUer som eksponerer belastning via sysfs."""
    res = []
    for card in sorted(glob.glob("/sys/class/drm/card[0-9]")):
        dev = os.path.join(card, "device")
        if read(os.path.join(dev, "vendor")) == "0x1002" and os.path.exists(
            os.path.join(dev, "gpu_busy_percent")
        ):
            res.append(dev)
    return res


# --------------------------------------------------------------------------
# Batteri (bare bærbare PC-er – batterier i mus/tastatur teller ikke)
# --------------------------------------------------------------------------
POWER_SUPPLY = "/sys/class/power_supply"


def laptop_batteries(root=None):
    out = []
    for p in sorted(glob.glob(os.path.join(root or POWER_SUPPLY, "*"))):
        if read(os.path.join(p, "type")) == "Battery" and \
                (read(os.path.join(p, "scope"), "System") or "System").lower() != "device":
            out.append(p)
    return out


def _num(p, name):
    v = read(os.path.join(p, name))
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def battery_info(paths):
    """Samlet status for alle interne batterier."""
    now = full = design = power = 0
    caps, states = [], []
    for p in paths:
        volt = _num(p, "voltage_now") or _num(p, "voltage_min_design") or 0
        e_now, e_full, e_des = _num(p, "energy_now"), _num(p, "energy_full"), _num(p, "energy_full_design")
        if e_now is None and _num(p, "charge_now") is not None and volt:          # µAh -> µWh
            e_now = _num(p, "charge_now") * volt // 1_000_000
            e_full = (_num(p, "charge_full") or 0) * volt // 1_000_000
            e_des = (_num(p, "charge_full_design") or 0) * volt // 1_000_000
        now += e_now or 0
        full += e_full or 0
        design += e_des or 0
        pw = _num(p, "power_now")
        if pw is None and _num(p, "current_now") is not None and volt:
            pw = _num(p, "current_now") * volt // 1_000_000
        power += abs(pw or 0)
        c = _num(p, "capacity")
        if c is not None:
            caps.append(c)
        states.append((read(os.path.join(p, "status")) or "Unknown"))
    pct = round(now * 100 / full) if full else (round(sum(caps) / len(caps)) if caps else 0)
    state = "Charging" if "Charging" in states else "Discharging" if "Discharging" in states else \
        "Full" if all(s in ("Full", "Not charging") for s in states) else states[0] if states else "Unknown"
    secs = None
    try:                                                   # samme anslag som systemet viser
        from gi.repository import Gio
        up = Gio.DBusProxy.new_for_bus_sync(Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, None,
                                            "org.freedesktop.UPower",
                                            "/org/freedesktop/UPower/devices/DisplayDevice",
                                            "org.freedesktop.UPower.Device", None)
        key = "TimeToFull" if state == "Charging" else "TimeToEmpty"
        v = up.get_cached_property(key)
        secs = v.unpack() if v and v.unpack() > 0 else None
    except Exception:  # noqa: BLE001
        pass
    if secs is None and power > 0:                          # reserve: regn ut selv
        if state == "Discharging":
            secs = now * 3600 // power
        elif state == "Charging" and full > now:
            secs = (full - now) * 3600 // power
    return {"pct": max(0, min(100, pct)), "state": state, "secs": secs, "watts": power / 1e6,
            "health": round(full * 100 / design) if design else None, "count": len(paths)}


def fmt_duration(secs):
    h, m = divmod(int(secs) // 60, 60)
    return f"{h} t {m} min" if h else f"{m} min"


def uptime_seconds():
    try:
        return float(read("/proc/uptime", "0").split()[0])
    except (ValueError, IndexError):
        return 0.0


# Windows: bytt ut alt som leser /proc og /sys med psutil og LibreHardwareMonitor
if IS_WIN:
    from sensors_win import (CpuReader, DiskReader, NetReader, NICE_DEVICE, amd_gpus, battery_info,  # noqa: F811
                             cpu_freqs_ghz, cpu_model, cpu_temp, hwmon_temps, laptop_batteries, meminfo,
                             uptime_seconds)
