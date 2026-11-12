"""Strømforbruk: måler CPU-pakken (RAPL/zenergy) og skjermkortene, og regner ut pris.

Hovedkort, RAM, disker og vifter kan ikke måles fra Linux – de legges til som et fast tillegg
(standard 50 W, kan endres). Prisen er kroner per kWh, som du selv setter.
"""
import glob
import json
import os
import time

CFG = os.path.expanduser("~/.config/systemmonitor/strom.json")
DEFAULTS = {"price": 1.50, "extra_w": 50}


def load():
    try:
        with open(CFG) as f:
            return {**DEFAULTS, **json.load(f)}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save(cfg):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    with open(CFG, "w") as f:
        json.dump(cfg, f)


def _read_int(path):
    try:
        with open(path) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


class EnergyCounter:
    """Watt ut fra en teller i mikrojoule (håndterer at telleren går rundt)."""

    def __init__(self, path, wrap_path=None):
        self.path = path
        self.wrap = _read_int(wrap_path) if wrap_path else None
        self.last = None

    def watts(self):
        v, t = _read_int(self.path), time.monotonic()
        if v is None:
            return None
        w = None
        if self.last:
            dv, dt = v - self.last[0], t - self.last[1]
            if dv < 0 and self.wrap:
                dv += self.wrap
            if dt > 0.2 and dv >= 0:
                w = dv / 1e6 / dt
        self.last = (v, t)
        return w


def _cpu_counter():
    # 1) powercap (RAPL) – «package-0»
    for d in sorted(glob.glob("/sys/class/powercap/intel-rapl:[0-9]")):
        if _read_int(f"{d}/energy_uj") is not None:
            return EnergyCounter(f"{d}/energy_uj", f"{d}/max_energy_range_uj")
    # 2) hwmon zenergy / amd_energy – «Esocket0»
    for lab in glob.glob("/sys/class/hwmon/hwmon*/energy*_label"):
        try:
            if open(lab).read().strip().lower().startswith("esocket"):
                path = lab.replace("_label", "_input")
                if _read_int(path) is not None:
                    return EnergyCounter(path)
        except OSError:
            pass
    return None


class PowerMeter:
    def __init__(self):
        self.cpu = _cpu_counter()
        self.igpu = [p for p in glob.glob("/sys/class/hwmon/hwmon*/power1_input")
                     if open(os.path.join(os.path.dirname(p), "name")).read().strip() == "amdgpu"]
        self.last = {}

    def read(self, nvidia_w=None):
        """Ordbok: cpu, gpu, measured, total (med tillegg). Verdier i watt (eller None)."""
        cfg = load()
        cpu = self.cpu.watts() if self.cpu else None
        gpu = nvidia_w or 0.0
        for p in self.igpu:
            v = _read_int(p)
            if v:
                gpu += v / 1e6
        measured = (cpu or 0.0) + gpu
        self.last = {"cpu": cpu, "gpu": gpu if (nvidia_w is not None or self.igpu) else None,
                     "measured": measured if (cpu is not None or gpu) else None,
                     "total": measured + cfg["extra_w"] if (cpu is not None or gpu) else None}
        return self.last


def cost(watts, hours, price=None):
    price = load()["price"] if price is None else price
    return watts / 1000 * hours * price
