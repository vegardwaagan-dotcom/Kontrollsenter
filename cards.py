"""Kontrollsenter – kortene i Oversikt-fanen (grafer, strømmodus, vifter, diskplass)."""
import glob
import json
import os
import shutil
import subprocess
import threading
import time
from collections import deque

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402,F401

from sensors import *  # noqa: E402,F401,F403


# --------------------------------------------------------------------------
# GUI-komponenter
# --------------------------------------------------------------------------
UI_SCALE = [1.0]       # gjeldende skaleringsfaktor for tekst og grafer
GRAPHS = []


def _monitor_geometry(widget=None):
    disp = Gdk.Display.get_default()
    mons = disp.get_monitors() if disp else None
    if not mons or mons.get_n_items() == 0:
        return None
    return mons.get_item(0).get_geometry()


class Graph(Gtk.DrawingArea):
    """Enkel linjegraf med én eller flere serier."""

    def __init__(self, colors, fixed_max=100.0):
        super().__init__()
        self.colors = colors
        self.fixed_max = fixed_max
        self.series = [deque([0.0] * HISTORY, maxlen=HISTORY) for _ in colors]
        self._first = True
        self.set_content_height(round(80 * UI_SCALE[0]))
        GRAPHS.append(self)
        self.set_hexpand(True)
        self.set_draw_func(self._draw)

    def push(self, *values):
        for s, v in zip(self.series, values):
            if self._first:
                s.extend([float(v or 0)] * HISTORY)
            s.append(float(v or 0))
        self._first = False
        self.queue_draw()

    def _draw(self, _area, cr, w, h):
        top = self.fixed_max or max(1.0, *(max(s) for s in self.series)) * 1.15
        # bakgrunn + rutenett
        fg = self.get_color()
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.06)
        cr.rectangle(0, 0, w, h)
        cr.fill()
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.10)
        cr.set_line_width(1)
        for i in range(1, 4):
            y = round(h * i / 4) + 0.5
            cr.move_to(0, y)
            cr.line_to(w, y)
        cr.stroke()

        step = w / (HISTORY - 1)
        for s, (r, g, b) in zip(self.series, self.colors):
            pts = [(i * step, h - min(v / top, 1.0) * (h - 2) - 1) for i, v in enumerate(s)]
            cr.move_to(*pts[0])
            for p in pts[1:]:
                cr.line_to(*p)
            cr.set_source_rgba(r, g, b, 1)
            cr.set_line_width(2)
            cr.stroke_preserve()
            cr.line_to(w, h)
            cr.line_to(0, h)
            cr.close_path()
            cr.set_source_rgba(r, g, b, 0.18)
            cr.fill()


BLUE = (0.21, 0.52, 0.89)
GREEN = (0.20, 0.72, 0.42)
ORANGE = (0.96, 0.55, 0.15)
PURPLE = (0.57, 0.38, 0.85)
RED = (0.88, 0.27, 0.29)
TEAL = (0.13, 0.66, 0.70)


class Card(Gtk.Box):
    def __init__(self, title, colors=None, fixed_max=100.0, legend=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add_css_class("card")
        for side in ("top", "bottom", "start", "end"):
            getattr(self, f"set_margin_{side}")(0)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        inner.set_margin_top(14)
        inner.set_margin_bottom(14)
        inner.set_margin_start(16)
        inner.set_margin_end(16)
        self.append(inner)

        head = Gtk.Box(spacing=8)
        t = Gtk.Label(label=title, xalign=0, hexpand=True)
        t.add_css_class("heading")
        head.append(t)
        self.value = Gtk.Label(xalign=1)
        self.value.add_css_class("title-2")
        self.value.add_css_class("numeric")
        head.append(self.value)
        inner.append(head)

        self.subtitle = Gtk.Label(xalign=0, wrap=True)
        self.subtitle.add_css_class("dim-label")
        self.subtitle.add_css_class("caption")
        inner.append(self.subtitle)

        self.graph = None
        if colors:
            self.graph = Graph(colors, fixed_max)
            inner.append(self.graph)
        if legend:
            row = Gtk.Box(spacing=12)
            for (r, g, b), text in zip(colors, legend):
                lbl = Gtk.Label(xalign=0)
                lbl.set_markup(
                    f'<span foreground="#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}">●</span> {text}'
                )
                lbl.add_css_class("caption")
                row.append(lbl)
            inner.append(row)

        self.details = Gtk.Label(xalign=0)
        self.details.add_css_class("caption")
        self.details.add_css_class("numeric")
        inner.append(self.details)
        self.inner = inner


# --------------------------------------------------------------------------
# Strømmodus (tuned via power-profiles D-Bus + NVIDIA-strømgrense)
# --------------------------------------------------------------------------
PP_BUS = "org.freedesktop.UPower.PowerProfiles"
PP_PATH = "/org/freedesktop/UPower/PowerProfiles"
GPU_HELPER = "/usr/local/bin/systemmonitor-gpu-power"
APP_DIR = os.path.dirname(os.path.abspath(__file__))

MODES = [
    ("power-saver", "Strømsparing", "power-profile-power-saver-symbolic",
     "Lavt strømforbruk og lite varme: CPU-en sparer strøm, og skjermkortet får laveste strømgrense."),
    ("balanced", "Balansert", "power-profile-balanced-symbolic",
     "Midt på treet: full fart når du trenger det, sparer strøm når PC-en har lite å gjøre."),
    ("performance", "Max Ytelse", "power-profile-performance-symbolic",
     "Alt på max: CPU-en kjører for full ytelse, og skjermkortet får høyeste strømgrense."),
]
MODE_NAMES = {m[0]: m[1] for m in MODES}


class PowerCard(Gtk.Box):
    def __init__(self, has_nvidia):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("card")
        self.has_nvidia = has_nvidia
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side, v in (("top", 14), ("bottom", 14), ("start", 16), ("end", 16)):
            getattr(inner, f"set_margin_{side}")(v)
        self.append(inner)

        head = Gtk.Box(spacing=8)
        t = Gtk.Label(label="Strømmodus", xalign=0, hexpand=True)
        t.add_css_class("heading")
        head.append(t)
        self.status = Gtk.Label(xalign=1)
        self.status.add_css_class("dim-label")
        head.append(self.status)
        inner.append(head)

        row = Gtk.Box(homogeneous=True)
        row.add_css_class("linked")
        self.buttons = {}
        first = None
        for key, name, icon, _desc in MODES:
            b = Gtk.ToggleButton(label=name)
            b.set_size_request(-1, 44)
            if first is None:
                first = b
            else:
                b.set_group(first)
            b.connect("toggled", self._on_toggled, key)
            row.append(b)
            self.buttons[key] = b
        inner.append(row)

        # Fart per modus, under hver knapp
        specs = Gtk.Box(homogeneous=True, spacing=6)
        self.spec_lbls, self.peak_lbls = {}, {}
        for key, *_ in MODES:
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            a = Gtk.Label(xalign=0.5, justify=Gtk.Justification.CENTER, wrap=True)
            a.add_css_class("caption")
            a.add_css_class("numeric")
            b = Gtk.Label(xalign=0.5, justify=Gtk.Justification.CENTER, wrap=True)
            b.add_css_class("caption")
            b.add_css_class("dim-label")
            b.add_css_class("numeric")
            col.append(a)
            col.append(b)
            specs.append(col)
            self.spec_lbls[key], self.peak_lbls[key] = a, b
        inner.append(specs)
        self.peaks = self._load_peaks()
        self._peaks_dirty = False
        self._peaks_saved = time.monotonic()
        self.gpu_clock_max = None
        self.gpu_limits = None

        self.live = Gtk.Label(xalign=0)
        self.live.add_css_class("numeric")
        inner.append(self.live)

        self.desc = Gtk.Label(xalign=0, wrap=True)
        self.desc.add_css_class("caption")
        inner.append(self.desc)

        gpu_row = Gtk.Box(spacing=8)
        self.gpu_lbl = Gtk.Label(xalign=0, wrap=True, hexpand=True)
        self.gpu_lbl.add_css_class("caption")
        self.gpu_lbl.add_css_class("dim-label")
        gpu_row.append(self.gpu_lbl)
        self.setup_btn = Gtk.Button(label="Aktiver GPU-styring", valign=Gtk.Align.CENTER)
        self.setup_btn.set_tooltip_text(
            "Engangsoppsett: lar Kontrollsenter endre strømgrensen på skjermkortet.\n"
            "Du blir spurt om passordet ditt én gang."
        )
        self.setup_btn.connect("clicked", self._on_setup)
        gpu_row.append(self.setup_btn)
        gpu_row.set_visible(has_nvidia)
        inner.append(gpu_row)

        self._updating = False
        self._gpu_mode_applied = None
        try:
            self.proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, None, PP_BUS, PP_PATH, PP_BUS, None)
            self.proxy.connect("g-properties-changed", lambda *_: self._sync())
        except GLib.Error:
            self.proxy = None
        self._sync()

    # --- fart per modus ----------------------------------------------------
    PEAKS_FILE = os.path.expanduser("~/.config/systemmonitor/peaks.json")

    def _load_peaks(self):
        import json
        try:
            with open(self.PEAKS_FILE) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _save_peaks(self):
        import json
        try:
            os.makedirs(os.path.dirname(self.PEAKS_FILE), exist_ok=True)
            with open(self.PEAKS_FILE, "w") as f:
                json.dump(self.peaks, f)
        except OSError:
            pass

    def flush_peaks(self):
        if self._peaks_dirty:
            self._save_peaks()
        self._peaks_dirty = False
        self._peaks_saved = time.monotonic()

    def update_specs(self):
        base, turbo = cpu_freqs_ghz()
        gmax = f"{self.gpu_clock_max / 1000:.2f} GHz" if self.gpu_clock_max else None
        lim = self.gpu_limits or (None, None, None)
        cpu_txt = {
            "power-saver": f"CPU opptil {base:.2f} GHz (turbo av)" if base else "CPU: turbo av",
            "balanced": f"CPU opptil {turbo:.2f} GHz (turbo ved behov)" if turbo else "CPU: turbo på",
            "performance": f"CPU opptil {turbo:.2f} GHz (alltid klar)" if turbo else "CPU: full fart",
        }
        for i, (key, *_r) in enumerate(MODES):
            lines = [cpu_txt[key]]
            if self.has_nvidia and gmax:
                w = f" · maks {lim[i]:.0f} W" if lim[i] else ""
                lines.append(f"GPU opptil {gmax}{w}")
            self.spec_lbls[key].set_label("\n".join(lines))
            pk = self.peaks.get(key, {})
            if pk:
                parts = []
                if pk.get("cpu"):
                    parts.append(f"CPU {pk['cpu']:.2f}")
                if pk.get("gpu"):
                    parts.append(f"GPU {pk['gpu'] / 1000:.2f}")
                self.peak_lbls[key].set_label("Målt topp: " + " · ".join(parts) + " GHz")
            else:
                self.peak_lbls[key].set_label("Målt topp: ikke målt ennå")

    def tick(self, cpu_ghz, nv):
        """Kalles hvert sekund med nåværende fart."""
        nv = nv or {}
        if nv.get("clock_max") and not self.gpu_clock_max:
            self.gpu_clock_max = nv["clock_max"]
        if nv.get("limits") and all(nv["limits"]) and not self.gpu_limits:
            self.gpu_limits = nv["limits"]
        mode = self.active_profile()
        gpu_mhz = nv.get("clock")
        parts = []
        if cpu_ghz:
            parts.append(f"CPU {cpu_ghz:.2f} GHz")
        if gpu_mhz is not None:
            parts.append(f"GPU {gpu_mhz / 1000:.2f} GHz")
        if nv.get("limit"):
            parts.append(f"GPU-grense {nv['limit']:.0f} W")
        self.live.set_label(("Akkurat nå: " + " · ".join(parts)) if parts else "")
        if mode in MODE_NAMES:
            pk = self.peaks.setdefault(mode, {})
            changed = False
            if cpu_ghz and cpu_ghz > pk.get("cpu", 0) + 0.005:
                pk["cpu"] = round(cpu_ghz, 3)
                changed = True
            if gpu_mhz and gpu_mhz > pk.get("gpu", 0):
                pk["gpu"] = gpu_mhz
                changed = True
            if changed:
                self._peaks_dirty = True
            if self._peaks_dirty and time.monotonic() - self._peaks_saved >= 30:
                self.flush_peaks()
        self.update_specs()

    # --- systemprofil -------------------------------------------------------
    def active_profile(self):
        if not self.proxy:
            return None
        v = self.proxy.get_cached_property("ActiveProfile")
        return v.unpack() if v else None

    def _sync(self):
        mode = self.active_profile()
        if mode is None:
            self.status.set_label("Strømprofiler er ikke tilgjengelig")
            for b in self.buttons.values():
                b.set_sensitive(False)
            return
        self._updating = True
        for key, b in self.buttons.items():
            b.set_active(key == mode)
            (b.add_css_class if key == mode else b.remove_css_class)("suggested-action")
        self._updating = False
        self.status.set_label(f"Aktiv: {MODE_NAMES.get(mode, mode)}")
        self.desc.set_label(next((m[3] for m in MODES if m[0] == mode), ""))
        self._apply_gpu(mode)

    def _on_toggled(self, btn, key):
        if self._updating or not btn.get_active() or not self.proxy:
            return
        self.status.set_label("Bytter …")
        self.proxy.call(
            "org.freedesktop.DBus.Properties.Set",
            GLib.Variant("(ssv)", (PP_BUS, "ActiveProfile", GLib.Variant("s", key))),
            Gio.DBusCallFlags.NONE, -1, None, self._on_set_done, key,
        )

    def _on_set_done(self, proxy, res, key):
        try:
            proxy.call_finish(res)
        except GLib.Error as e:
            self._sync()
            self.status.set_label("Kunne ikke bytte modus")
            self.desc.set_label(f"Feil: {e.message}")
            return
        # Oppdater hurtigbufferen med en gang (signalet kommer også, men kan komme sent)
        proxy.set_cached_property("ActiveProfile", GLib.Variant("s", key))
        self._sync()

    # --- skjermkort ---------------------------------------------------------
    def _apply_gpu(self, mode):
        if not self.has_nvidia:
            return
        if not os.path.exists(GPU_HELPER):
            self.setup_btn.set_visible(True)
            self.gpu_lbl.set_label("Skjermkortets strømgrense styres ikke ennå. Trykk knappen for å slå det på.")
            return
        self.setup_btn.set_visible(False)
        if mode == self._gpu_mode_applied:
            return
        self._gpu_mode_applied = mode
        self.gpu_lbl.set_label("Setter strømgrense på skjermkortet …")

        def work():
            try:
                r = subprocess.run(["sudo", "-n", GPU_HELPER, mode],
                                   capture_output=True, text=True, timeout=20)
                ok, msg = r.returncode == 0, (r.stdout or r.stderr).strip()
            except (OSError, subprocess.SubprocessError) as e:
                ok, msg = False, str(e)
            GLib.idle_add(self._gpu_done, mode, ok, msg)

        threading.Thread(target=work, daemon=True).start()

    def _gpu_done(self, mode, ok, msg):
        if ok:
            self.gpu_lbl.set_label(msg.replace("GPU 0: s", "Skjermkort: s") or "Strømgrense satt.")
        else:
            self._gpu_mode_applied = None
            self.gpu_lbl.set_label(f"Kunne ikke endre skjermkortet: {msg or 'ukjent feil'}")
            self.setup_btn.set_visible(True)
        return False

    def _on_setup(self, _btn):
        self.setup_btn.set_sensitive(False)
        self.gpu_lbl.set_label("Venter på passord …")
        user = os.environ.get("USER") or os.getlogin()

        def work():
            try:
                r = subprocess.run(
                    ["pkexec", "/bin/bash", os.path.join(APP_DIR, "install-gpu-power.sh"), user],
                    capture_output=True, text=True)
                ok, msg = r.returncode == 0, (r.stderr or r.stdout).strip()
            except OSError as e:
                ok, msg = False, str(e)
            GLib.idle_add(self._setup_done, ok, msg)

        threading.Thread(target=work, daemon=True).start()

    def _setup_done(self, ok, msg):
        self.setup_btn.set_sensitive(True)
        if ok:
            self._gpu_mode_applied = None
            self._apply_gpu(self.active_profile())
        else:
            self.gpu_lbl.set_label("Oppsettet ble avbrutt." if not msg or "dismissed" in msg.lower()
                                   or "126" in msg else f"Oppsett feilet: {msg}")
        return False


# --------------------------------------------------------------------------
# Viftestyring (hovedkort via nct6775 + NVIDIA via NVML, gjennom root-hjelper)
# --------------------------------------------------------------------------
FAN_HELPER = "/usr/local/bin/systemmonitor-fan"
FAN_PREFS = os.path.expanduser("~/.config/systemmonitor/fans.json")
CPU_PANIC, GPU_PANIC = 90, 85      # °C – over dette går alle vifter til auto
PRESETS = [("Alle auto", "auto"), ("Stille", 35), ("Kraftig", 70), ("Max", 100)]


def board_fan_chip():
    """Finn nct67xx-brikken. Returnerer (navn, sti) eller (None, None)."""
    import re
    for h in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
        name = read(os.path.join(h, "name"), "")
        if re.fullmatch(r"nct6\d{3}[a-z]?", name):
            return name, h
    return None, None


class FanRow:
    def __init__(self, card, key, title, grid, row, min_pct):
        self.card, self.key, self.min_pct = card, key, min_pct
        name = Gtk.Label(label=title, xalign=0)
        self.rpm = Gtk.Label(xalign=1, width_chars=10)
        self.rpm.add_css_class("numeric")
        self.rpm.add_css_class("dim-label")
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, min_pct, 100, 1)
        self.scale.set_hexpand(True)
        self.scale.set_draw_value(False)
        self.pct = Gtk.Label(xalign=1, width_chars=5)
        self.pct.add_css_class("numeric")
        self.auto = Gtk.CheckButton(label="Auto")
        for col, w in enumerate((name, self.rpm, self.scale, self.pct, self.auto)):
            grid.attach(w, col, row, 1, 1)
        self._quiet = False
        self._timer = 0
        self.scale.connect("value-changed", self._on_scale)
        self.auto.connect("toggled", self._on_auto)

    def set_value(self, v, send=True):
        """v = 'auto' eller prosent. Sender maks én kommando."""
        self._quiet = True
        if v == "auto":
            self.auto.set_active(True)
        else:
            self.auto.set_active(False)
            self.scale.set_value(max(int(v), self.min_pct))
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0
        self._sync_ui()
        self._quiet = False
        if send:
            self.card.send(self.key, self.value())

    def _sync_ui(self):
        on = self.auto.get_active()
        self.scale.set_sensitive(not on)
        self.pct.set_label("auto" if on else f"{int(self.scale.get_value())} %")

    def value(self):
        return "auto" if self.auto.get_active() else int(self.scale.get_value())

    def _on_auto(self, btn):
        on = btn.get_active()
        self._sync_ui()
        if not self._quiet:
            self.card.send(self.key, "auto" if on else int(self.scale.get_value()))

    def _on_scale(self, scale):
        self.pct.set_label(f"{int(scale.get_value())} %")
        if self._quiet or self.auto.get_active():
            return
        if self._timer:
            GLib.source_remove(self._timer)
        self._timer = GLib.timeout_add(350, self._fire)   # vent til du slipper glidebryteren

    def _fire(self):
        self._timer = 0
        self.card.send(self.key, int(self.scale.get_value()))
        return False


class FanCard(Gtk.Box):
    def __init__(self, has_nvidia):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("card")
        self.has_nvidia = has_nvidia
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side, v in (("top", 14), ("bottom", 14), ("start", 16), ("end", 16)):
            getattr(inner, f"set_margin_{side}")(v)
        self.append(inner)
        self.inner = inner

        head = Gtk.Box(spacing=8)
        t = Gtk.Label(label="Vifter", xalign=0, hexpand=True)
        t.add_css_class("heading")
        head.append(t)
        self.status = Gtk.Label(xalign=1, wrap=True)
        self.status.add_css_class("dim-label")
        head.append(self.status)
        inner.append(head)

        presets = Gtk.Box(spacing=6)
        for label, val in PRESETS:
            b = Gtk.Button(label=label)
            b.connect("clicked", lambda _b, v=val: self.apply_all(v))
            presets.append(b)
        self.presets = presets
        inner.append(presets)

        self.grid = Gtk.Grid(column_spacing=12, row_spacing=6)
        inner.append(self.grid)

        self.note = Gtk.Label(xalign=0, wrap=True)
        self.note.add_css_class("caption")
        self.note.add_css_class("dim-label")
        self.note.set_label(
            f"Hovedkortvifter går aldri under 20 %. Alle vifter settes tilbake til auto "
            f"hvis CPU når {CPU_PANIC} °C eller GPU {GPU_PANIC} °C, og når programmet lukkes."
        )
        inner.append(self.note)

        setup_row = Gtk.Box(spacing=8)
        self.setup_lbl = Gtk.Label(xalign=0, wrap=True, hexpand=True)
        self.setup_lbl.add_css_class("caption")
        setup_row.append(self.setup_lbl)
        self.setup_btn = Gtk.Button(label="Aktiver viftestyring", valign=Gtk.Align.CENTER)
        self.setup_btn.add_css_class("suggested-action")
        self.setup_btn.connect("clicked", self._on_setup)
        setup_row.append(self.setup_btn)
        self.setup_row = setup_row
        inner.append(setup_row)

        import queue
        self.q = queue.Queue()
        threading.Thread(target=self._worker, daemon=True).start()
        self.rows = {}
        self.panic = False
        self.build()

    # --- oppbygging ---------------------------------------------------------
    def ready(self):
        return os.path.exists(FAN_HELPER)

    def build(self):
        while (c := self.grid.get_first_child()):
            self.grid.remove(c)
        self.rows = {}
        self.chip, self.chip_path = board_fan_chip()
        r = 0
        if self.chip:
            for pwm in sorted(glob.glob(os.path.join(self.chip_path, "pwm[1-7]")),
                              key=lambda x: int(x[-1])):
                ch = pwm[-1]
                key = f"board:{self.chip}:{ch}"
                self.rows[key] = FanRow(self, key, f"Hovedkortvifte {ch}", self.grid, r, 20)
                r += 1
        if self.has_nvidia:
            self.rows["gpu"] = FanRow(self, "gpu", "Skjermkort (begge)", self.grid, r, 30)
            r += 1

        ok = self.ready()
        missing_board = self.chip is None
        self.setup_row.set_visible(not ok or missing_board)
        if not ok:
            self.setup_lbl.set_label(
                "Viftestyring er ikke slått på ennå. Trykk knappen og skriv passordet ditt én gang.")
        elif missing_board:
            self.setup_lbl.set_label(
                "Fant ikke hovedkortets viftebrikke. Prøv knappen igjen, eller start PC-en på nytt.")
        for w in (self.grid, self.presets, self.note):
            w.set_sensitive(ok)

        prefs = self._load()
        for key, row in self.rows.items():
            row.set_value(prefs.get(key, "auto"), send=False)
        if ok and any(v != "auto" for k, v in prefs.items() if k in self.rows):
            for key, row in self.rows.items():   # legg inn lagrede innstillinger igjen
                self.send(key, row.value())

    # --- lagring ------------------------------------------------------------
    def _load(self):
        import json
        try:
            with open(FAN_PREFS) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _save(self):
        import json
        try:
            os.makedirs(os.path.dirname(FAN_PREFS), exist_ok=True)
            with open(FAN_PREFS, "w") as f:
                json.dump({k: r.value() for k, r in self.rows.items()}, f)
        except OSError:
            pass

    # --- kommandoer ---------------------------------------------------------
    def send(self, key, val):
        if not self.ready():
            return
        self.panic = False
        v = "auto" if val == "auto" else str(int(val))
        if key == "gpu":
            self.q.put(["gpu", v])
        else:
            _b, chip, ch = key.split(":")
            self.q.put(["pwm", chip, ch, v])
        self._save()

    def apply_all(self, val):
        for row in self.rows.values():
            row.set_value(val, send=True)

    def all_auto_now(self, save=True):
        """Brukes ved lukking og ved overoppheting."""
        if not self.ready():
            return
        try:
            subprocess.run(["sudo", "-n", FAN_HELPER, "all-auto"], timeout=15,
                           capture_output=True)
        except (OSError, subprocess.SubprocessError):
            pass

    def _worker(self):
        while True:
            args = self.q.get()
            try:
                r = subprocess.run(["sudo", "-n", FAN_HELPER, *args],
                                   capture_output=True, text=True, timeout=15)
                err = None if r.returncode == 0 else (r.stderr.strip() or "ukjent feil")
            except (OSError, subprocess.SubprocessError) as e:
                err = str(e)
            if err:
                GLib.idle_add(self.status.set_label, f"Feil: {err}")

    # --- oppdatering hvert sekund ------------------------------------------
    def refresh(self, cpu_t, gpu_t, gpu_fan):
        for key, row in self.rows.items():
            if key == "gpu":
                row.rpm.set_label(f"{gpu_fan:.0f} %" if gpu_fan is not None else "–")
            else:
                ch = key.rsplit(":", 1)[1]
                rpm = read(os.path.join(self.chip_path, f"fan{ch}_input"))
                row.rpm.set_label(f"{rpm} RPM" if rpm is not None else "–")
        manual = any(r.value() != "auto" for r in self.rows.values())
        hot = (cpu_t or 0) >= CPU_PANIC or (gpu_t or 0) >= GPU_PANIC
        if manual and hot and self.ready():
            self.panic = True
            for row in self.rows.values():
                row.set_value("auto", send=False)
            self._save()
            threading.Thread(target=self.all_auto_now, daemon=True).start()
            self.status.set_label("⚠ For varmt – alle vifter satt til auto")
        elif not self.panic:
            self.status.set_label("Manuell styring aktiv" if manual else "Alle vifter på auto")

    # --- engangsoppsett ----------------------------------------------------
    def _on_setup(self, _btn):
        self.setup_btn.set_sensitive(False)
        self.setup_lbl.set_label("Venter på passord …")
        user = os.environ.get("USER") or os.getlogin()

        def work():
            try:
                r = subprocess.run(
                    ["pkexec", "/bin/bash", os.path.join(APP_DIR, "install-fan-control.sh"), user],
                    capture_output=True, text=True)
                ok, msg = r.returncode == 0, (r.stderr or r.stdout).strip()
            except OSError as e:
                ok, msg = False, str(e)
            GLib.idle_add(self._setup_done, ok, msg)

        threading.Thread(target=work, daemon=True).start()

    def _setup_done(self, ok, msg):
        self.setup_btn.set_sensitive(True)
        if ok:
            GLib.timeout_add(1500, lambda: self.build() or False)  # gi driveren tid
            self.setup_lbl.set_label("Ferdig! Leter etter vifter …")
        else:
            self.setup_lbl.set_label(f"Oppsettet ble avbrutt eller feilet. {msg}".strip())
        return False


# --------------------------------------------------------------------------
# Diskplass
# --------------------------------------------------------------------------
DISK_FS = {"btrfs", "ext4", "ext3", "xfs", "vfat", "exfat", "ntfs", "ntfs3", "fuseblk", "f2fs"}
CSS = b"""
levelbar.disk-ok block.filled { background-color: @accent_bg_color; }
levelbar.disk-warn block.filled { background-color: @warning_bg_color; }
levelbar.disk-crit block.filled { background-color: @error_bg_color; }
"""


def disk_model(dev):
    """Modellnavn for disken en partisjon ligger på."""
    name = os.path.basename(dev)
    path = os.path.realpath(f"/sys/class/block/{name}")
    for p in (path, os.path.dirname(path)):
        m = read(os.path.join(p, "device", "model"))
        if m:
            return m.strip()
    return None


def list_filesystems():
    """Én oppføring per ekte partisjon (btrfs-delvolumer slås sammen)."""
    best = {}
    try:
        with open("/proc/self/mounts") as f:
            mounts = [line.split()[:3] for line in f]
    except OSError:
        return []
    pref = ["/var/home", "/home", "/"]
    for dev, mnt, fs in mounts:
        mnt = mnt.replace("\\040", " ")
        if fs not in DISK_FS or not dev.startswith("/dev/"):
            continue
        cur = best.get(dev)
        rank = pref.index(mnt) if mnt in pref else (len(pref) + len(mnt))
        if cur is None or rank < cur[0]:
            best[dev] = (rank, mnt, fs)
    out = []
    for dev, (_r, mnt, fs) in best.items():
        try:
            sv = os.statvfs(mnt)
        except OSError:
            continue
        total = sv.f_blocks * sv.f_frsize
        if total == 0:
            continue
        free = sv.f_bavail * sv.f_frsize
        out.append({"dev": dev, "mnt": mnt, "fs": fs, "total": total, "free": free,
                    "used": total - sv.f_bfree * sv.f_frsize})
    out.sort(key=lambda d: -d["total"])
    return out


def nice_mount(mnt):
    return {
        "/var/home": "Hovedlagring (hjemmemappe, programmer og spill)",
        "/home": "Hovedlagring (hjemmemappe)",
        "/": "System",
        "/boot": "Oppstart (/boot)",
        "/boot/efi": "EFI-partisjon",
    }.get(mnt, mnt.replace("/run/media/", "").split("/")[-1] or mnt)


class DiskSpaceCard(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("card")
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side, v in (("top", 14), ("bottom", 14), ("start", 16), ("end", 16)):
            getattr(inner, f"set_margin_{side}")(v)
        self.append(inner)
        head = Gtk.Box(spacing=8)
        t = Gtk.Label(label="Diskplass", xalign=0, hexpand=True)
        t.add_css_class("heading")
        head.append(t)
        self.value = Gtk.Label(xalign=1)
        self.value.add_css_class("title-2")
        self.value.add_css_class("numeric")
        head.append(self.value)
        inner.append(head)
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        inner.append(self.box)

        # Andre partisjoner skjules bak «Mer»
        self.more_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.revealer = Gtk.Revealer(child=self.more_box, reveal_child=False,
                                     transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN)
        inner.append(self.revealer)
        self.more_btn = Gtk.Button(halign=Gtk.Align.START)
        self.more_btn.add_css_class("flat")
        self.more_btn.connect("clicked", self._toggle_more)
        inner.append(self.more_btn)
        self._sig = None
        self.rows = {}

    def _toggle_more(self, _btn=None):
        self.revealer.set_reveal_child(not self.revealer.get_reveal_child())
        self._update_more_btn()

    def _update_more_btn(self):
        n = len(self._sig or ()) - 1
        self.more_btn.set_visible(n > 0)
        open_ = self.revealer.get_reveal_child()
        self.more_btn.set_child(Adw.ButtonContent(
            label="Mindre" if open_ else f"Mer ({n} til)",
            icon_name="pan-up-symbolic" if open_ else "pan-down-symbolic"))

    def refresh(self):
        fss = list_filesystems()
        # Hovedlagringen først
        main_i = next((i for i, d in enumerate(fss) if d["mnt"] in ("/var/home", "/home")), 0)
        if fss:
            fss.insert(0, fss.pop(main_i))
        sig = tuple(d["dev"] for d in fss)
        if sig != self._sig:
            self._sig = sig
            for b in (self.box, self.more_box):
                while (c := b.get_first_child()):
                    b.remove(c)
            self.rows = {}
            for i, d in enumerate(fss):
                row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                top = Gtk.Box(spacing=8)
                name = Gtk.Label(label=nice_mount(d["mnt"]), xalign=0, hexpand=True)
                name.set_ellipsize(3)
                top.append(name)
                free = Gtk.Label(xalign=1)
                free.add_css_class("numeric")
                free.add_css_class("heading")
                top.append(free)
                row.append(top)
                bar = Gtk.LevelBar(min_value=0, max_value=1)
                for off in ("low", "high", "full"):
                    bar.remove_offset_value(off)
                bar.set_size_request(-1, 10)
                row.append(bar)
                info = Gtk.Label(xalign=0, wrap=True)
                info.add_css_class("caption")
                info.add_css_class("dim-label")
                info.add_css_class("numeric")
                row.append(info)
                (self.box if i == 0 else self.more_box).append(row)
                model = disk_model(d["dev"])
                self.rows[d["dev"]] = (free, bar, info, model)
            self._update_more_btn()
        total_free = 0
        for d in fss:
            free, bar, info, model = self.rows[d["dev"]]
            frac = d["used"] / d["total"]
            total_free += d["free"]
            free.set_label(f"{fmt_bytes(d['free'])} ledig")
            bar.set_value(frac)
            for c in ("disk-ok", "disk-warn", "disk-crit"):
                bar.remove_css_class(c)
            bar.add_css_class("disk-crit" if frac >= 0.9 else "disk-warn" if frac >= 0.8 else "disk-ok")
            extra = f" · {model}" if model else ""
            info.set_label(
                f"{fmt_bytes(d['used'])} brukt av {fmt_bytes(d['total'])} ({frac * 100:.0f} %) · "
                f"{d['fs']} · {d['dev']}{extra}"
            )
        main = next((d for d in fss if d["mnt"] in ("/var/home", "/home")), fss[0] if fss else None)
        self.value.set_label(f"{fmt_bytes(main['free'])} ledig" if main else "–")
