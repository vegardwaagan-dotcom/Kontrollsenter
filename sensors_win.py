"""Maskinvaredata på Windows – samme grensesnitt som sensors.py på Linux.

- CPU-last, minne, disk og nett: psutil
- Temperaturer, vifter, CPU-watt og klokkefart: LibreHardwareMonitor (LHM), som Kontrollsenter-installasjonen
  setter opp til å starte ved innlogging (med administratorrettigheter) og dele målingene på
  http://127.0.0.1:8085/data.json – bare lokalt på maskinen.
"""
import json
import re
import subprocess
import threading
import time
import urllib.request

import psutil

LHM_URL = "http://127.0.0.1:8085/data.json"


# --------------------------------------------------------------------------
# LibreHardwareMonitor
# --------------------------------------------------------------------------
class Lhm:
    """Leser LHM-treet i en bakgrunnstråd (hvert sekund) – vinduet venter aldri på LHM.
    Svarer ikke LHM, spørres det hvert 5. sekund, og etter 20 sek prøves det å starte LHM-oppgaven."""
    _cache, ok = [], False
    _thread = None
    _down_since = None
    _tried_start = False
    TASK = "Kontrollsenter - LibreHardwareMonitor"

    @classmethod
    def sensors(cls):
        if cls._thread is None:
            cls._thread = threading.Thread(target=cls._loop, daemon=True)
            cls._thread.start()
        return cls._cache

    @classmethod
    def _loop(cls):
        while True:
            try:
                with urllib.request.urlopen(LHM_URL, timeout=3) as r:
                    tree = json.load(r)
                out = []
                cls._walk(tree, [], out)
                cls._cache, cls.ok, cls._down_since = out, True, None
                time.sleep(1)
            except (OSError, ValueError):
                cls._cache, cls.ok = [], False
                now = time.monotonic()
                cls._down_since = cls._down_since or now
                if now - cls._down_since > 20 and not cls._tried_start:
                    cls._tried_start = True
                    try:                                   # oppgaven er laget av installasjonen
                        subprocess.run(["schtasks", "/run", "/tn", cls.TASK], capture_output=True, timeout=15,
                                       creationflags=0x08000000)
                    except (OSError, subprocess.SubprocessError, ValueError):
                        pass
                time.sleep(5)

    @classmethod
    def _walk(cls, node, path, out):
        sid = node.get("SensorId")
        if sid:
            v = _num(node.get("RawValue", node.get("Value")))
            out.append({"id": sid, "name": node.get("Text", ""), "type": node.get("Type", ""), "value": v,
                        "hw": path[-2] if len(path) >= 2 else (path[-1] if path else "")})
        for ch in node.get("Children", []) or []:
            cls._walk(ch, path + [node.get("Text", "")], out)

    @classmethod
    def find(cls, type_, id_re=".*", name_re=".*"):
        return [s for s in cls.sensors() if s["type"] == type_ and re.search(id_re, s["id"])
                and re.search(name_re, s["name"], re.I) and s["value"] is not None]


def _num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(v))
    return float(m.group(0).replace(",", ".")) if m else None


# --------------------------------------------------------------------------
# Samme funksjoner/klasser som sensors.py
# --------------------------------------------------------------------------
class CpuReader:
    def __init__(self):
        psutil.cpu_percent(percpu=True)
        n = psutil.cpu_count() or 1
        self.prev = {"cpu": 0, **{f"cpu{i}": 0 for i in range(n)}}

    def usage(self):
        per = psutil.cpu_percent(percpu=True)
        res = {f"cpu{i}": float(v) for i, v in enumerate(per)}
        res["cpu"] = sum(per) / len(per) if per else 0.0
        return res

    @staticmethod
    def freq_ghz():
        clocks = [s["value"] for s in Lhm.find("Clock", r"/(intel|amd)cpu/", r"core")]
        if clocks:
            return max(clocks) / 1000
        f = psutil.cpu_freq()
        return f.current / 1000 if f else None


def cpu_freqs_ghz():
    f = psutil.cpu_freq()
    return ((f.max / 1000) if f and f.max else None, None)


def cpu_model():
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
        return winreg.QueryValueEx(k, "ProcessorNameString")[0].strip()
    except OSError:
        return "CPU"


def meminfo():
    vm, sw = psutil.virtual_memory(), psutil.swap_memory()
    return {"MemTotal": vm.total, "MemAvailable": vm.available, "MemFree": vm.free,
            "Cached": getattr(vm, "cached", 0) or 0, "Buffers": 0,
            "SwapTotal": sw.total, "SwapFree": sw.free}


def hwmon_temps():
    """(enhet, etikett, °C) – fra LibreHardwareMonitor."""
    out = []
    from sensors import plausible
    for s in Lhm.find("Temperature"):
        if not plausible(s["name"], s["value"]):          # RAM-grenser, «Distance to TjMax» o.l.
            continue
        dev = s["id"].split("/")[1] if "/" in s["id"] else s["hw"]
        out.append((dev, s["name"], s["value"]))
    return out


def cpu_temp(temps):
    pick = None
    for dev, label, t in temps:
        if dev in ("amdcpu", "intelcpu"):
            if re.search(r"tctl|tdie|package", label, re.I):
                return t
            pick = pick if pick is not None else t
    return pick


NICE_DEVICE = {"amdcpu": "CPU", "intelcpu": "CPU", "gpu-nvidia": "Skjermkort", "gpu-amd": "AMD GPU",
               "nvme": "NVMe", "hdd": "Disk", "lpc": "Hovedkort", "memory": "RAM"}


class DiskReader:
    def __init__(self):
        self.prev = self._snap()
        self.prev_t = time.monotonic()

    @staticmethod
    def _snap():
        c = psutil.disk_io_counters()
        return (c.read_bytes, c.write_bytes) if c else (0, 0)

    def rates(self):
        now, t = self._snap(), time.monotonic()
        dt = max(t - self.prev_t, 1e-3)
        rr, wr = (now[0] - self.prev[0]) / dt, (now[1] - self.prev[1]) / dt
        self.prev, self.prev_t = now, t
        return max(rr, 0), max(wr, 0)


class NetReader:
    def __init__(self):
        self.prev = self._snap()
        self.prev_t = time.monotonic()

    @staticmethod
    def _snap():
        rx = tx = 0
        for name, c in psutil.net_io_counters(pernic=True).items():
            if re.search(r"loopback|vethernet|vmware|virtualbox|hyper-v|bluetooth", name, re.I):
                continue
            rx += c.bytes_recv
            tx += c.bytes_sent
        return rx, tx

    def rates(self):
        now, t = self._snap(), time.monotonic()
        dt = max(t - self.prev_t, 1e-3)
        rx, tx = (now[0] - self.prev[0]) / dt, (now[1] - self.prev[1]) / dt
        self.prev, self.prev_t = now, t
        return max(rx, 0), max(tx, 0)


def amd_gpus():
    return []


def laptop_batteries(root=None):
    try:
        return ["windows"] if psutil.sensors_battery() else []
    except Exception:  # noqa: BLE001
        return []


def battery_info(paths):
    b = psutil.sensors_battery()
    if not b:
        return None
    state = "Charging" if b.power_plugged and b.percent < 99 else ("Full" if b.power_plugged else "Discharging")
    secs = b.secsleft if isinstance(b.secsleft, int) and b.secsleft > 0 else None
    return {"pct": round(b.percent), "state": state, "secs": secs, "watts": 0.0, "health": None, "count": 1}


def uptime_seconds():
    return time.time() - psutil.boot_time()


def fans():
    """[(id, navn, RPM)] fra LHM."""
    return [(s["id"], s["name"], s["value"]) for s in Lhm.find("Fan")]


def cpu_package_watts():
    p = Lhm.find("Power", r"/(intel|amd)cpu/", r"package|cpu cores|total")
    return p[0]["value"] if p else None
