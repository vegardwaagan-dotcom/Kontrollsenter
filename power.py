"""Strømforbruk: måler CPU-pakken (RAPL/zenergy) og skjermkortene, og regner ut pris.

Hovedkort, RAM, disker og vifter kan ikke måles fra Linux – de legges til som et fast tillegg
(standard 50 W, kan endres). Prisen er kroner per kWh, som du selv setter.
"""
import glob
import json
import os
import sys
import threading
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
        if sys.platform == "win32":
            from sensors_win import cpu_package_watts
            cpu = cpu_package_watts()
        else:
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
        if cfg.get("shelly"):                              # ekte måling fra smartplugg: hele PC-en (og skjermen)
            try:
                import shelly
                w = shelly.watts()
                if w is not None:
                    self.last["total"], self.last["plug"] = w, True
            except Exception:  # noqa: BLE001
                pass
        return self.last


def cost(watts, hours, price=None):
    price = load()["price"] if price is None else price
    return watts / 1000 * hours * price


# --------------------------------------------------------------------------
# Forbruk per dag (Wh) – lagres for de siste 62 dagene
# --------------------------------------------------------------------------
DAYS = os.path.expanduser("~/.config/systemmonitor/strom-dager.json")


_CURRENT = []


def current():
    """Den som teller nå (i vinduet) – ellers les fra fila."""
    return _CURRENT[0] if _CURRENT else EnergyLog()


class EnergyLog:
    def __init__(self):
        try:
            import perf
            if not perf.disk_ok("strom"):
                raise OSError("lagring av")
            with open(DAYS) as f:
                self.days = json.load(f)
        except (OSError, ValueError):
            self.days = {}
        self.last = None
        self.saved = time.monotonic()

    def add(self, watts):
        """Legg til målt forbruk. Hver dag lagres som [Wh, sekunder målt]."""
        now = time.monotonic()
        if watts is not None and self.last is not None:
            dt = min(now - self.last, 10)
            day = time.strftime("%Y-%m-%d")
            wh, secs = self._get(day)
            self.days[day] = [wh + watts * dt / 3600, secs + dt]
        self.last = now
        import perf
        if now - self.saved > perf.save_every(60):
            self.save()

    def _get(self, day):
        v = self.days.get(day, [0.0, 0.0])
        return (v, 0.0) if isinstance(v, (int, float)) else (v[0], v[1])

    def save(self):
        self.saved = time.monotonic()
        if not __import__("perf").disk_ok("strom"):
            return
        keep = sorted(self.days)[-62:]
        self.days = {k: self.days[k] for k in keep}
        try:
            os.makedirs(os.path.dirname(DAYS), exist_ok=True)
            with open(DAYS, "w") as f:
                json.dump({k: [round(self._get(k)[0], 1), round(self._get(k)[1])] for k in self.days}, f)
        except OSError:
            pass

    def today_wh(self):
        return self._get(time.strftime("%Y-%m-%d"))[0]

    def avg_watts(self):
        """Snittforbruk over alt som er målt (siste 62 dager), mens PC-en var på."""
        wh = sum(self._get(k)[0] for k in self.days)
        secs = sum(self._get(k)[1] for k in self.days)
        return wh * 3600 / secs if secs > 60 else None

    def on_hours_per_day(self):
        """Hvor mange timer PC-en typisk er på per døgn (fra dagene som er logget, høyst 24)."""
        today = time.strftime("%Y-%m-%d")
        full = [self._get(k)[1] / 3600 for k in self.days if k != today]
        return min(24.0, sum(full) / len(full)) if full else None

    def month_estimate_kwh(self, hours_per_day=None):
        w = self.avg_watts()
        if w is None:
            return None
        h = hours_per_day or self.on_hours_per_day() or 8.0
        return w * h * 30 / 1000


# --------------------------------------------------------------------------
# Vinduet «Strømforbruk» (klikk på strøm-flisen i Oversikt)
# --------------------------------------------------------------------------
def dialog(win):
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, GLib, Gtk
    import i18n

    d = Adw.Dialog(title=i18n.tr("Strømforbruk"), content_width=520)
    tv = Adw.ToolbarView()
    tv.add_top_bar(Adw.HeaderBar())
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
    for side in ("top", "bottom", "start", "end"):
        getattr(box, f"set_margin_{side}")(20)
    big = Gtk.Label()
    big.add_css_class("title-1")
    big.add_css_class("numeric")
    box.append(big)
    grid = Gtk.Grid(column_spacing=24, row_spacing=6)
    labels = {}
    rows = [("cpu", "Prosessor (målt)"), ("gpu", "Skjermkort (målt)"), ("extra", "Resten av PC-en (anslått)"),
            ("sep", ""), ("today", "I dag"), ("avg", "Snitt når PC-en er på"), ("month", "Anslag per måned")]
    for r, (key, text) in enumerate(rows):
        if key == "sep":
            grid.attach(Gtk.Separator(), 0, r, 2, 1)
            continue
        a = Gtk.Label(label=i18n.tr(text), xalign=0, hexpand=True)
        a.add_css_class("dim-label")
        b = Gtk.Label(xalign=1)
        b.add_css_class("numeric")
        grid.attach(a, 0, r, 1, 1)
        grid.attach(b, 1, r, 1, 1)
        labels[key] = b
    box.append(grid)

    cfg = load()
    sets = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    sets.set_margin_top(6)
    for key, text, lo, hi, step, digits in (("price", "Strømpris (kr per kWh, med nettleie)", 0, 10, 0.05, 2),
                                            ("extra_w", "Tillegg for resten av PC-en (W)", 0, 300, 5, 0)):
        r = Gtk.Box(spacing=12)
        r.append(Gtk.Label(label=i18n.tr(text), xalign=0, hexpand=True))
        sp = Gtk.SpinButton.new_with_range(lo, hi, step)
        sp.set_digits(digits)
        sp.set_value(cfg[key])

        def changed(w, k=key):
            c = load()
            c[k] = round(w.get_value(), 2)
            save(c)
        sp.connect("value-changed", changed)
        r.append(sp)
        sets.append(r)
    note = Gtk.Label(label=i18n.tr("Prosessor og skjermkort måles direkte. Hovedkort, RAM, disker, vifter og "
                                   "strømforsyningens tap kan ikke måles fra Linux, så de legges til som et fast "
                                   "tillegg. Skjermen er ikke med."), wrap=True, xalign=0)
    note.add_css_class("caption")
    note.add_css_class("dim-label")
    sets.append(note)
    sh = Gtk.Box(spacing=12)                             # 73: ekte måling fra en Shelly-plugg
    sh.append(Gtk.Label(label=i18n.tr("Shelly-smartplugg (IP-adresse)"), xalign=0, hexpand=True))
    she = Gtk.Entry(text=cfg.get("shelly", ""), placeholder_text="192.168.1.50", width_chars=16)
    sh.append(she)
    shl = Gtk.Label(xalign=0, wrap=True)
    shl.add_css_class("caption")
    shl.add_css_class("dim-label")

    def sh_save(*_):
        c = load()
        c["shelly"] = she.get_text().strip()
        save(c)

        def test():
            import shelly
            try:
                msg = f"✓ Måler {shelly.read_once(c['shelly']):.0f} W – brukes i stedet for beregnet strøm" if \
                    c["shelly"] else "Av – strømmen beregnes"
            except Exception as e:  # noqa: BLE001
                msg = f"✗ {e}"
            GLib.idle_add(shl.set_label, msg)
        threading.Thread(target=test, daemon=True).start()
    she.connect("activate", sh_save)
    shb = Gtk.Button(label=i18n.tr("Lagre"))
    shb.connect("clicked", sh_save)
    sh.append(shb)
    sets.append(sh)
    shl.set_label(i18n.tr("Måler hele PC-en (og det som står i samme plugg) i stedet for å beregne. Shelly Plug S / "
                          "Plus Plug S – lokalt, uten sky."))
    sets.append(shl)
    try:                                                  # lagre strømforbruket per dag på disk av/på
        import perf_ui
        sets.append(perf_ui.disk_switch("strom"))
    except Exception:  # noqa: BLE001
        pass
    box.append(sets)
    tv.set_content(box)
    d.set_child(tv)

    def tick():
        pw = getattr(win, "_power", {}) or {}
        c = load()
        log = win.energy
        big.set_label(f"{pw.get('total') or 0:.0f} W")
        labels["cpu"].set_label(f"{pw.get('cpu') or 0:.0f} W")
        labels["gpu"].set_label(f"{pw.get('gpu') or 0:.0f} W")
        labels["extra"].set_label(f"{c['extra_w']:.0f} W")
        wh = log.today_wh()
        labels["today"].set_label(f"{wh / 1000:.2f} kWh · {wh / 1000 * c['price']:.2f} kr")
        avg = log.avg_watts()
        labels["avg"].set_label(f"{avg:.0f} W" if avg else "–")
        m = log.month_estimate_kwh()
        hrs = log.on_hours_per_day()
        labels["month"].set_label(
            f"{m:.0f} kWh · {m * c['price']:.0f} kr  " + i18n.tr(f"({hrs or 8:.0f} t/døgn)")
            if m else "–")
        return True
    tick()
    tid = GLib.timeout_add(1000, tick)
    d.connect("closed", lambda *_: GLib.source_remove(tid))
    d.present(win)
