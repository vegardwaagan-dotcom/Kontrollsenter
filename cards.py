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


GRAPH_WINDOW = [60]     # sekunder som vises i grafene (1 min / 10 min / 1 t) – velges i Oversikt
GRAPH_KEEP = 3600       # så mye historikk hver graf husker (1 time)


def fmt_pct(v):
    return f"{v:.0f} %"


class Graph(Gtk.DrawingArea):
    """Linjegraf med én eller flere serier. Hold musa over for verdi og tidspunkt."""

    def __init__(self, colors, fixed_max=100.0, fmt=fmt_pct, names=None):
        super().__init__()
        self.colors = colors
        self.fixed_max = fixed_max
        self.fmt = fmt
        self.names = names
        self.series = [deque(maxlen=GRAPH_KEEP) for _ in colors]
        self.times = deque(maxlen=GRAPH_KEEP)
        self.hover = None
        self.set_content_height(round(80 * UI_SCALE[0]))
        GRAPHS.append(self)
        self.set_hexpand(True)
        self.set_draw_func(self._draw)
        mc = Gtk.EventControllerMotion()
        mc.connect("motion", lambda _c, x, _y: self._set_hover(x))
        mc.connect("leave", lambda *_: self._set_hover(None))
        self.add_controller(mc)

    def _set_hover(self, x):
        self.hover = x
        self.queue_draw()

    def push(self, *values):
        for s, v in zip(self.series, values):
            s.append(float(v or 0))
        self.times.append(time.time())
        if self.get_mapped():
            self.queue_draw()

    def _visible(self, w):
        """Siste GRAPH_WINDOW sekunder, slått sammen til høyst én verdi per piksel (maks i hver bit)."""
        n = min(len(self.times), GRAPH_WINDOW[0])
        if n == 0:
            return [], []
        start = len(self.times) - n
        out = []
        buckets = max(1, min(n, int(w)))
        per = n / buckets
        for s in self.series:
            vals = list(s)[start:]
            out.append([max(vals[int(i * per):max(int((i + 1) * per), int(i * per) + 1)]) for i in range(buckets)])
        ts = list(self.times)[start:]
        t_out = [ts[min(int((i + 1) * per) - 1, n - 1)] for i in range(buckets)]
        return out, t_out

    def _draw(self, _area, cr, w, h):
        data, ts = self._visible(w)
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
        if not data or not data[0]:
            return
        top = self.fixed_max or max(1.0, *(max(s) for s in data)) * 1.15
        n = len(data[0])
        # Grafen fylles fra høyre: før historikken er full, er venstre del tom
        span = max(GRAPH_WINDOW[0], 2)
        filled = min(len(self.times), GRAPH_WINDOW[0])
        x0 = w * (1 - (filled - 1) / (span - 1)) if filled > 1 else w
        step = (w - x0) / max(n - 1, 1)
        ys = lambda v: h - min(v / top, 1.0) * (h - 2) - 1  # noqa: E731
        for s, (r, g, b) in zip(data, self.colors):
            cr.move_to(x0, ys(s[0]))
            for i, v in enumerate(s[1:], 1):
                cr.line_to(x0 + i * step, ys(v))
            cr.set_source_rgba(r, g, b, 1)
            cr.set_line_width(2)
            cr.stroke_preserve()
            cr.line_to(w, h)
            cr.line_to(x0, h)
            cr.close_path()
            cr.set_source_rgba(r, g, b, 0.18)
            cr.fill()
        # Hold musa over: loddrett strek + verdi og tid
        if self.hover is not None and self.hover >= x0 - 1:
            i = max(0, min(n - 1, round((self.hover - x0) / step))) if step else n - 1
            x = x0 + i * step
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.45)
            cr.set_line_width(1)
            cr.move_to(round(x) + 0.5, 0)
            cr.line_to(round(x) + 0.5, h)
            cr.stroke()
            ago = int(time.time() - ts[i])
            when = "nå" if ago < 2 else (f"{ago} s siden" if ago < 60 else f"{ago // 60} min siden")
            parts = []
            for k, s in enumerate(data):
                nm = f"{self.names[k]} " if self.names and k < len(self.names) else ""
                parts.append(nm + self.fmt(s[i]))
            import i18n
            text = " · ".join(parts) + "  –  " + i18n.tr(when)
            layout = self.create_pango_layout(text)
            tw, th = layout.get_pixel_size()
            bx = min(max(x - tw / 2 - 6, 2), w - tw - 14)
            cr.set_source_rgba(0, 0, 0, 0.72)
            cr.rectangle(bx, 3, tw + 12, th + 6)
            cr.fill()
            cr.set_source_rgba(1, 1, 1, 1)
            cr.move_to(bx + 6, 6)
            from gi.repository import PangoCairo
            PangoCairo.show_layout(cr, layout)


class Gauge(Gtk.DrawingArea):
    """Rundt mål (f.eks. temperatur) – grønn, gul eller rød etter verdien."""

    def __init__(self, maximum=100.0, warn=70, crit=85, unit="°"):
        super().__init__()
        self.maximum, self.warn, self.crit, self.unit = maximum, warn, crit, unit
        self.value = None
        self.set_content_width(round(92 * UI_SCALE[0]))
        self.set_content_height(round(92 * UI_SCALE[0]))
        GRAPHS.append(self)            # skaleres sammen med grafene
        self.set_draw_func(self._draw)

    def set_value(self, v):
        if v != self.value:
            self.value = v
            self.queue_draw()

    def _draw(self, _a, cr, w, h):
        import math
        size = min(w, h)
        cx, cy, r = w / 2, h / 2, size / 2 - 7
        lw = max(6, size * 0.09)
        a0, a1 = math.radians(135), math.radians(405)
        fg = self.get_color()
        cr.set_line_cap(1)     # rund
        cr.set_line_width(lw)
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.12)
        cr.arc(cx, cy, r, a0, a1)
        cr.stroke()
        v = self.value
        if v is not None:
            frac = max(0.0, min(1.0, v / self.maximum))
            col = (0.20, 0.72, 0.42) if v < self.warn else (0.96, 0.66, 0.15) if v < self.crit else (0.88, 0.27, 0.29)
            cr.set_source_rgba(*col, 1)
            if frac > 0.005:
                cr.arc(cx, cy, r, a0, a0 + (a1 - a0) * frac)
                cr.stroke()
        layout = self.create_pango_layout(f"{v:.0f}{self.unit}" if v is not None else "–")
        from gi.repository import Pango, PangoCairo
        fd = Pango.FontDescription.from_string(f"Sans Bold {max(9, size * 0.2):.0f}px")
        fd.set_absolute_size(max(11, size * 0.22) * Pango.SCALE)
        fd.set_weight(Pango.Weight.BOLD)
        layout.set_font_description(fd)
        tw, th = layout.get_pixel_size()
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 1)
        cr.move_to(cx - tw / 2, cy - th / 2)
        PangoCairo.show_layout(cr, layout)


class Tile(Gtk.Box):
    """Nøkkeltall øverst i Oversikt: lite ikon/mål, stor verdi og en kort undertekst."""

    def __init__(self, title, gauge=None, icon=None):
        super().__init__(spacing=14)
        self.add_css_class("card")
        self.add_css_class("tile")
        for side in ("top", "bottom"):
            getattr(self, f"set_margin_{side}")(0)
        inner = Gtk.Box(spacing=14)
        for side, v in (("top", 12), ("bottom", 12), ("start", 14), ("end", 14)):
            getattr(inner, f"set_margin_{side}")(v)
        self.append(inner)
        self.gauge = gauge
        if gauge:
            inner.append(gauge)
        elif icon:
            img = Gtk.Image(icon_name=icon, pixel_size=24, valign=Gtk.Align.CENTER)
            img.add_css_class("tile-icon")
            inner.append(img)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, spacing=2, hexpand=True)
        t = Gtk.Label(label=title, xalign=0)
        t.add_css_class("caption-heading")
        t.add_css_class("dim-label")
        col.append(t)
        self.value = Gtk.Label(xalign=0, ellipsize=3)
        self.value.add_css_class("title-3")
        self.value.add_css_class("numeric")
        col.append(self.value)
        self.sub = Gtk.Label(xalign=0, ellipsize=3)
        self.sub.add_css_class("caption")
        self.sub.add_css_class("dim-label")
        col.append(self.sub)
        inner.append(col)
        self.spark = None

    def add_spark(self, series, color=None, top=100.0):
        """Liten graf for siste minutt rett i flisen (series = deque med verdier, nyeste sist)."""
        da = Gtk.DrawingArea(content_height=22, hexpand=True)
        da.add_css_class("tile-spark")
        self._spark_src, self._spark_top = series, top
        self._spark_col = color

        def draw(_a, cr, w, h):
            try:
                import perf
                if perf.lowend():
                    return
            except Exception:  # noqa: BLE001
                pass
            vals = list(self._spark_src)[-60:]
            if len(vals) < 2:
                return
            mx = self._spark_top or max(max(vals), 1e-6) * 1.2
            if callable(mx):
                mx = mx(vals)
            fg = self.get_color()
            col = self._spark_col or (fg.red, fg.green, fg.blue)
            n = len(vals) - 1
            pts = [(w * i / n, h - 2 - (h - 4) * min(1, (v or 0) / mx)) for i, v in enumerate(vals)]
            cr.move_to(*pts[0])
            for x, y in pts[1:]:
                cr.line_to(x, y)
            cr.set_source_rgba(*col, 0.95)
            cr.set_line_width(1.6)
            cr.stroke_preserve()
            cr.line_to(w, h)
            cr.line_to(0, h)
            cr.close_path()
            cr.set_source_rgba(*col, 0.18)
            cr.fill()
        da.set_draw_func(draw)
        self.get_first_child().get_last_child().append(da)
        self.spark = da
        return da


BLUE = (0.36, 0.55, 1.00)     # merkevarens blå
GREEN = (0.20, 0.72, 0.42)
ORANGE = (0.96, 0.55, 0.15)
PURPLE = (0.54, 0.36, 1.00)   # merkevarens lilla
RED = (0.88, 0.27, 0.29)
TEAL = (0.13, 0.66, 0.70)


class Card(Gtk.Box):
    def __init__(self, title, colors=None, fixed_max=100.0, legend=None, fmt=fmt_pct):
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
            self.graph = Graph(colors, fixed_max, fmt=fmt, names=legend)
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
        _d = Gtk.Label(label='Hvor mye kraft prosessoren og skjermkortet får. Max Ytelse til spill, Balansert til det meste, Strømsparing når PC-en bare står på.', xalign=0, wrap=True)
        _d.add_css_class("ks-sub")
        inner.append(_d)

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
        gpu_row.set_visible(has_nvidia and not IS_WIN)      # Windows: strømgrensen styres av driveren
        inner.append(gpu_row)

        self._updating = False
        self._gpu_mode_applied = None
        if IS_WIN:
            self.proxy = None
            self._sync()
            GLib.timeout_add_seconds(10, lambda: (self._sync(), True)[1])   # fang opp bytte gjort i Windows
            return
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
            if not __import__("perf").disk_ok("topp"):
                return {}
            with open(self.PEAKS_FILE) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _save_peaks(self):
        import json
        try:
            if not __import__("perf").disk_ok("topp"):
                return
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
        if IS_WIN:
            import winsupport
            now = time.monotonic()
            if not hasattr(self, "_plan"):                     # første gang: les med en gang
                self._plan_t, self._plan = now, winsupport.active_plan()
            elif now - self._plan_t > 5 and not getattr(self, "_plan_busy", False):
                self._plan_busy, self._plan_t = True, now      # powercfg er tregt – les i bakgrunnen

                def work():
                    self._plan = winsupport.active_plan()
                    self._plan_busy = False
                threading.Thread(target=work, daemon=True).start()
            return self._plan
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
        if IS_WIN and not self._updating and btn.get_active():
            import winsupport
            self.status.set_label("Bytter …")

            def work():
                ok, msg = winsupport.set_plan(key)
                self._plan_t = 0

                def done():
                    self._sync()
                    if not ok:
                        self.desc.set_label(f"Feil: {msg or 'kunne ikke bytte strømplan'}")
                    return False
                GLib.idle_add(done)
            threading.Thread(target=work, daemon=True).start()
            return
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
        if not self.has_nvidia or IS_WIN:
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
        self.widgets = (name, self.rpm, self.scale, self.pct, self.auto)
        self.stopped = False
        for col, w in enumerate(self.widgets):
            grid.attach(w, col, row, 1, 1)

        self._quiet = False
        self._timer = 0
        self.scale.connect("value-changed", self._on_scale)
        self.auto.connect("toggled", self._on_auto)

    def set_shown(self, on):
        for w in self.widgets:
            w.set_visible(on)

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
        _d = Gtk.Label(label='Velg en ferdig innstilling for alle viftene, lag en kurve etter temperatur, eller styr hver vifte for seg. «Auto» lar hovedkortet bestemme.', xalign=0, wrap=True)
        _d.add_css_class("ks-sub")
        inner.append(_d)

        presets = Gtk.Box(spacing=6)
        for label, val in PRESETS:
            b = Gtk.Button(label=label)
            b.connect("clicked", lambda _b, v=val: self.apply_all(v))
            presets.append(b)
        # Viftekurve: farten følger temperaturen
        self.curve_btn = Gtk.ToggleButton(label="Kurve", tooltip_text="Viftene følger temperaturen etter kurven din")
        self.curve_btn.connect("toggled", lambda b: self.set_curve(b.get_active()) if not self._quiet_curve else None)
        presets.append(self.curve_btn)
        edit = Gtk.Button(icon_name="document-edit-symbolic", tooltip_text="Rediger viftekurvene")
        edit.add_css_class("flat")
        edit.connect("clicked", self._edit_curve)
        presets.append(edit)
        self.presets = presets
        self.curve_on = False
        self._quiet_curve = False
        self._curve_sending = False
        self._curve_tick = 0
        self.last_temps = (None, None)
        inner.append(presets)

        self.grid = Gtk.Grid(column_spacing=12, row_spacing=6)
        inner.append(self.grid)
        # Vifter som står stille (0 RPM) skjules – de er som regel ikke koblet til
        self.show_all = False
        self.more_btn = Gtk.Button(halign=Gtk.Align.START, visible=False)
        self.more_btn.add_css_class("flat")
        self.more_btn.connect("clicked", self._toggle_all)
        inner.append(self.more_btn)

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
        if IS_WIN:
            return bool(getattr(self, "_win_controls", None))
        return os.path.exists(FAN_HELPER)

    def build(self):
        while (c := self.grid.get_first_child()):
            self.grid.remove(c)
        self.rows = {}
        self.chip, self.chip_path = (None, None) if IS_WIN else board_fan_chip()
        r = 0
        if IS_WIN:
            # Windows: styrbare vifter fra LibreHardwareMonitor (hovedkort og skjermkort)
            from sensors_win import Lhm
            self._win_controls = {s["id"]: s for s in Lhm.find("Control")}
            for sid, s in sorted(self._win_controls.items()):
                gpu = "/gpu" in sid
                title = f"{'Skjermkort' if gpu else 'Hovedkort'} – {s['name'].replace('Fan Control', 'Vifte')}"
                self.rows["lhm:" + sid] = FanRow(self, "lhm:" + sid, title, self.grid, r, 30 if gpu else 20)
                r += 1
        if self.chip:
            for pwm in sorted(glob.glob(os.path.join(self.chip_path, "pwm[1-7]")),
                              key=lambda x: int(x[-1])):
                ch = pwm[-1]
                key = f"board:{self.chip}:{ch}"
                self.rows[key] = FanRow(self, key, f"Hovedkortvifte {ch}", self.grid, r, 20)
                r += 1
        if self.has_nvidia and not IS_WIN:
            self.rows["gpu"] = FanRow(self, "gpu", "Skjermkort (begge)", self.grid, r, 30)
            r += 1

        ok = self.ready()
        if IS_WIN:
            self.setup_row.set_visible(not ok)
            self.setup_btn.set_visible(False)
            from sensors_win import Lhm
            self.setup_lbl.set_label(
                "Venter på LibreHardwareMonitor …" if not Lhm.ok else
                "Fant ingen vifter som kan styres. På mange bærbare (f.eks. MSI) styres viftene bare av "
                "produsentens program (MSI Center).")
            for w in (self.grid, self.presets, self.note):
                w.set_sensitive(ok)
            if not ok and not getattr(self, "_win_retry", False):
                self._win_retry = True                         # LHM kan bruke litt tid etter innlogging
                GLib.timeout_add_seconds(10, lambda: (setattr(self, "_win_retry", False), self.build(), False)[2])
            prefs = self._load()
            for key, row in self.rows.items():
                row.set_value(prefs.get(key, "auto"), send=False)
            return
        missing_board = self.chip is None
        self.setup_row.set_visible(not ok or missing_board)
        if not ok:
            self.setup_lbl.set_label(
                "Viftestyring er ikke slått på ennå. Trykk knappen og skriv passordet ditt én gang.")
        elif missing_board:
            if "acpi_enforce_resources=lax" in read("/proc/cmdline", ""):
                self.setup_lbl.set_label("Fant ikke hovedkortets viftebrikke. Hovedkortet kan ha en brikke Linux "
                                         "ikke kan styre ennå – send feilsøkingsrapporten (Verktøy).")
            else:
                self.setup_lbl.set_label(
                    "Hovedkortets viftebrikke er sperret av BIOS (vanlig på ASUS-kort med Intel, f.eks. Z270). "
                    "Trykk «Rett viftebrikken» – det legger inn et oppstartsvalg, og PC-en må startes på nytt.")
                self.setup_btn.set_label("Rett viftebrikken")
        for w in (self.grid, self.presets, self.note):
            w.set_sensitive(ok)

        prefs = self._load()
        for key, row in self.rows.items():
            row.set_value(prefs.get(key, "auto"), send=False)
        import fancurve
        if ok and fancurve.load().get("active"):
            GLib.idle_add(lambda: self.set_curve(True) or False)
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
        if self.curve_on and not self._curve_sending:      # du tok over manuelt → kurven slås av
            self.set_curve(False, apply_auto=False)
        self.panic = False
        v = "auto" if val == "auto" else str(int(val))
        if key.startswith("lhm:"):
            self.q.put(["lhm", key[4:], v])
        elif key == "gpu":
            self.q.put(["gpu", v])
        else:
            _b, chip, ch = key.split(":")
            self.q.put(["pwm", chip, ch, v])
        if not self._curve_sending:
            self._save()

    def apply_all(self, val):
        if self.curve_on:
            self.set_curve(False, apply_auto=False)
        for row in self.rows.values():
            row.set_value(val, send=True)

    # --- viftekurve ------------------------------------------------------------
    def set_curve(self, on, apply_auto=True):
        import fancurve
        cfg = fancurve.load()
        cfg["active"] = bool(on)
        fancurve.save(cfg)
        self.curve_on = bool(on)
        self._quiet_curve = True
        self.curve_btn.set_active(self.curve_on)
        self._quiet_curve = False
        if on:
            self._curve_tick = 0
            self._apply_curve(*self.last_temps)
        elif apply_auto:
            for row in self.rows.values():
                row.set_value("auto", send=True)

    def _apply_curve(self, cpu_t, gpu_t):
        import fancurve
        cfg = fancurve.load()
        self._curve_sending = True
        try:
            parts = []
            for key, row in self.rows.items():
                kind = "gpu" if key == "gpu" or "/gpu" in key else "board"
                temp = gpu_t if kind == "gpu" else cpu_t
                pct = fancurve.interp(cfg[kind], temp, fancurve.MIN[kind])
                if pct is None:
                    continue
                cur = row.value()
                if cur == "auto" or abs(int(cur) - pct) >= 2:
                    row.set_value(pct, send=True)
                if kind == "board" and not parts:
                    parts.append(f"CPU {cpu_t:.0f} °C → {pct} %")
                if kind == "gpu":
                    parts.append(f"GPU {gpu_t:.0f} °C → {pct} %")
            self.status.set_label("Kurve: " + " · ".join(parts) if parts else "Kurve aktiv")
        finally:
            self._curve_sending = False

    def _edit_curve(self, *_):
        import fancurve
        fancurve.CurveDialog(self, *self.last_temps).present(self.get_root())

    def all_auto_now(self, save=True):
        """Brukes ved lukking og ved overoppheting."""
        if not self.ready():
            return
        if IS_WIN:
            for key in self.rows:
                if key.startswith("lhm:"):
                    self._lhm_set(key[4:], "auto")
            return
        try:
            subprocess.run(["sudo", "-n", FAN_HELPER, "all-auto"], timeout=15,
                           capture_output=True)
        except (OSError, subprocess.SubprocessError):
            pass

    @staticmethod
    def _lhm_set(sid, v):
        """Sett en vifte via LibreHardwareMonitor (bare lokalt). «auto» gir styringen tilbake til maskinen."""
        import urllib.parse
        import urllib.request
        q = urllib.parse.urlencode({"action": "Set", "id": sid, "value": "null" if v == "auto" else v})
        with urllib.request.urlopen(f"http://127.0.0.1:8085/Sensor?{q}", timeout=5) as r:
            body = r.read().decode("utf-8", "replace")
        if '"error"' in body.lower() or "fail" in body.lower():
            raise RuntimeError(body[:200])

    def _worker(self):
        while True:
            args = self.q.get()
            if args[0] == "lhm":
                try:
                    self._lhm_set(args[1], args[2])
                except Exception as e:  # noqa: BLE001
                    GLib.idle_add(self.status.set_label, f"Feil: {str(e) or type(e).__name__}")
                continue
            try:
                r = subprocess.run(["sudo", "-n", FAN_HELPER, *args],
                                   capture_output=True, text=True, timeout=15)
                err = None if r.returncode == 0 else (r.stderr.strip() or "ukjent feil")
            except (OSError, subprocess.SubprocessError) as e:
                err = str(e)
            if err:
                GLib.idle_add(self.status.set_label, f"Feil: {err}")

    def _toggle_all(self, *_):
        self.show_all = not self.show_all
        self._update_hidden()

    def _update_hidden(self):
        n = 0
        for row in self.rows.values():
            hide = row.stopped and not self.show_all
            n += row.stopped
            if row.widgets[0].get_visible() == hide:
                row.set_shown(not hide)
        self.more_btn.set_visible(n > 0)
        lbl = (f"Skjul {n} vifter som står stille" if self.show_all else f"Vis {n} vifter som står stille")
        if self.more_btn.get_label() != lbl:
            self.more_btn.set_label(lbl)

    # --- oppdatering hvert sekund ------------------------------------------
    def refresh(self, cpu_t, gpu_t, gpu_fan):
        # Omdreiningstallene vises bare – les dem kun når kortet er synlig, og hvert 3. sekund. (Hovedkortbrikken
        # henter alle registrene på nytt ved lesing, ~50 ms kjernetid.) Viftekurven styres av temperaturene.
        self._rpm_tick = getattr(self, "_rpm_tick", 0) + 1
        if self.get_mapped() and self._rpm_tick % 3 == 1:
            self._read_rpm(gpu_fan)
        self._control(cpu_t, gpu_t)

    def _read_rpm(self, gpu_fan):
        if IS_WIN:
            from sensors_win import Lhm
            fans = {s["id"]: s["value"] for s in Lhm.find("Fan")}
            ctl = {s["id"]: s["value"] for s in Lhm.find("Control")}
            for key, row in self.rows.items():
                sid = key[4:]
                rpm = fans.get(sid.replace("/control/", "/fan/"))
                row.rpm.set_label(f"{rpm:.0f} RPM" if rpm is not None else
                                  (f"{ctl[sid]:.0f} %" if ctl.get(sid) is not None else "–"))
                row.stopped = rpm is not None and rpm < 1
            if not self.rows and Lhm.ok and not getattr(self, "_win_built_after_lhm", False):
                self._win_built_after_lhm = True
                GLib.idle_add(lambda: self.build() or False)
        for key, row in self.rows.items():
            if key.startswith("lhm:"):
                continue
            if key == "gpu":
                row.rpm.set_label(f"{gpu_fan:.0f} %" if gpu_fan is not None else "–")
            else:
                ch = key.rsplit(":", 1)[1]
                rpm = read(os.path.join(self.chip_path, f"fan{ch}_input"))
                row.rpm.set_label(f"{rpm} RPM" if rpm is not None else "–")
                row.stopped = str(rpm).strip() == "0"
        self._update_hidden()

    def _control(self, cpu_t, gpu_t):
        self.last_temps = (cpu_t, gpu_t)
        manual = any(r.value() != "auto" for r in self.rows.values())
        hot = (cpu_t or 0) >= CPU_PANIC or (gpu_t or 0) >= GPU_PANIC
        if self.curve_on and not hot and self.ready():
            self._curve_tick += 1
            if self._curve_tick % 3 == 1:                  # hvert 3. sekund
                self._apply_curve(cpu_t, gpu_t)
            return
        if manual and hot and self.ready():
            if self.curve_on:
                self.set_curve(False, apply_auto=False)
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
        if not ok and "OMSTART" in msg:
            self.setup_btn.set_visible(False)
            self.setup_lbl.set_label("✓ Oppstartsvalget er lagt inn. Start PC-en på nytt, så dukker "
                                     "hovedkortviftene opp her.")
            return False
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
.tile-icon { color: @accent_color; }
.sidebar-badge { font-size: 0.85em; }
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
    if IS_WIN:
        import psutil
        out = []
        for p in psutil.disk_partitions(all=False):
            if "cdrom" in p.opts or not p.fstype:
                continue
            try:
                u = psutil.disk_usage(p.mountpoint)
            except OSError:
                continue
            out.append({"dev": p.device, "mnt": p.mountpoint, "fs": p.fstype, "total": u.total, "free": u.free,
                        "used": u.used})
        return sorted(out, key=lambda d: (d["mnt"] != "C:\\", -d["total"]))
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
