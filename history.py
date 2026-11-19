"""Historikk: temperaturer, last og strøm lagres hvert 10. sekund i 8 dager (SQLite).

Siden «Historikk» viser siste time, døgn eller uke – hold musa over grafene for verdier.
"""
import os
import sqlite3
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk  # noqa: E402

import i18n  # noqa: E402

DB = os.path.expanduser("~/.local/share/systemmonitor/historikk.db")
KEEP_DAYS = 8
COLS = ("cpu_t", "gpu_t", "cpu_l", "gpu_l", "watts")


class Recorder:
    def __init__(self, path=DB):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # timeout + WAL: flere Kontrollsenter-prosesser (vindu, bakgrunn, test) kan skrive uten «database is locked»
        self.db = sqlite3.connect(path, check_same_thread=False, timeout=0.5)
        try:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=NORMAL")    # trygt med WAL, og ingen fsync for hver måling
        except sqlite3.Error:
            pass
        self.pending = []
        self.db.execute("CREATE TABLE IF NOT EXISTS s (ts INTEGER PRIMARY KEY, cpu_t REAL, gpu_t REAL, "
                        "cpu_l REAL, gpu_l REAL, watts REAL)")
        self.db.commit()
        self.last = 0
        self.last_commit = time.time()
        self.last_prune = 0

    def add(self, cpu_t, gpu_t, cpu_l, gpu_l, watts, every=10):
        now = time.time()
        if now - self.last < every:
            return
        self.last = now
        self.pending.append((int(now), cpu_t, gpu_t, cpu_l, gpu_l, watts))
        try:
            import perf
            if perf.flag("ssd") and now - self.last_commit < 300 and len(self.pending) < 60:
                return                                # mindre skriving: lagre samlet hvert 5. minutt
        except Exception:  # noqa: BLE001
            pass
        rows, self.pending = self.pending, []
        try:
            self.db.executemany("INSERT OR REPLACE INTO s VALUES (?,?,?,?,?,?)", rows)
            if now - self.last_prune > 3600:
                self.last_prune = now
                self.db.execute("DELETE FROM s WHERE ts < ?", (int(now - KEEP_DAYS * 86400),))
        except sqlite3.OperationalError:          # låst av en annen prosess akkurat nå – hopp over én måling
            pass
        self.flush()                              # kort transaksjon: holder ikke låsen i et helt minutt

    def flush(self):
        self.last_commit = time.time()
        try:
            if self.pending:                          # avslutter/lagrer: skriv det som er samlet opp
                rows, self.pending = self.pending, []
                self.db.executemany("INSERT OR REPLACE INTO s VALUES (?,?,?,?,?,?)", rows)
            self.db.commit()
        except sqlite3.Error:
            pass


def query(seconds, buckets=360, path=DB):
    """[(ts, cpu_t, gpu_t, cpu_l, gpu_l, watts)] slått sammen i like lange biter (maks for temperatur, snitt ellers)."""
    if not os.path.exists(path):
        return []
    db = sqlite3.connect(path)
    now = time.time()
    start = now - seconds
    size = max(10, seconds / buckets)
    rows = db.execute(
        "SELECT CAST((ts - ?) / ? AS INTEGER) AS b, MAX(ts), MAX(cpu_t), MAX(gpu_t), AVG(cpu_l), AVG(gpu_l), AVG(watts) "
        "FROM s WHERE ts >= ? GROUP BY b ORDER BY b", (start, size, start)).fetchall()
    db.close()
    return [r[1:] for r in rows]


def stats(seconds, path=DB):
    if not os.path.exists(path):
        return None
    db = sqlite3.connect(path)
    r = db.execute("SELECT MAX(cpu_t), MAX(gpu_t), AVG(cpu_l), AVG(watts), COUNT(*), MIN(ts) FROM s WHERE ts >= ?",
                   (time.time() - seconds,)).fetchone()
    db.close()
    return r


class Chart(Gtk.DrawingArea):
    """Tidsgraf for historikk. series: [(navn, farge, verdier)], verdier kan være None (hull)."""

    def __init__(self, unit, fixed_max=None, height=170):
        super().__init__()
        self.unit, self.fixed_max = unit, fixed_max
        self.ts, self.series, self.span = [], [], 3600
        self.hover = None
        self.set_content_height(height)
        self.set_hexpand(True)
        self.set_draw_func(self._draw)
        mc = Gtk.EventControllerMotion()
        mc.connect("motion", lambda _c, x, _y: (setattr(self, "hover", x), self.queue_draw()))
        mc.connect("leave", lambda *_: (setattr(self, "hover", None), self.queue_draw()))
        self.add_controller(mc)

    def set_data(self, ts, series, span):
        self.ts, self.series, self.span = ts, series, span
        self.queue_draw()

    def _draw(self, _a, cr, w, h):
        from gi.repository import PangoCairo
        fg = self.get_color()
        left, bottom, T = 58, 22, 12
        gw, gh = w - left - 6, h - bottom - T
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.05)
        cr.rectangle(left, T, gw, gh)
        cr.fill()
        vals = [v for _n, _c, vs in self.series for v in vs if v is not None]
        top = self.fixed_max or (max(vals) * 1.15 if vals else 1)
        top = max(top, 1)
        now = time.time()
        t0 = now - self.span

        def X(t):
            return left + (t - t0) / self.span * gw

        def Y(v):
            return T + gh - min(v / top, 1) * gh
        cr.set_line_width(1)
        for k in range(0, 5):                                   # vannrette linjer + tall
            v = top * k / 4
            y = Y(v)
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.10)
            cr.move_to(left, round(y) + 0.5)
            cr.line_to(left + gw, round(y) + 0.5)
            cr.stroke()
            lay = self.create_pango_layout(f"{v:.0f}{self.unit}")
            tw, th = lay.get_pixel_size()
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.55)
            cr.move_to(left - tw - 6, y - th / 2)
            PangoCairo.show_layout(cr, lay)
        fmt = "%H:%M" if self.span <= 86400 else "%a %d."
        for k in range(0, 5):                                   # tid langs bunnen
            t = t0 + self.span * k / 4
            lay = self.create_pango_layout(time.strftime(fmt, time.localtime(t)))
            tw, _th = lay.get_pixel_size()
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.55)
            cr.move_to(min(max(X(t) - tw / 2, left), w - tw - 2), h - bottom + 4)
            PangoCairo.show_layout(cr, lay)
        if not self.ts:
            lay = self.create_pango_layout(i18n.tr("Ingen data ennå – historikken fylles mens Kontrollsenter kjører."))
            tw, th = lay.get_pixel_size()
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.55)
            cr.move_to(left + gw / 2 - tw / 2, T + gh / 2 - th / 2)
            PangoCairo.show_layout(cr, lay)
            return
        gap = max(self.span / 360 * 3, 40)                       # hull i grafen når PC-en var av
        for _name, (r, g, b), vs in self.series:
            cr.set_source_rgba(r, g, b, 1)
            cr.set_line_width(2)
            prev = None
            for t, v in zip(self.ts, vs):
                if v is None:
                    prev = None
                    continue
                if prev is None or t - prev > gap:
                    cr.move_to(X(t), Y(v))
                else:
                    cr.line_to(X(t), Y(v))
                prev = t
            cr.stroke()
        if self.hover is not None and self.hover >= left:
            t = t0 + (self.hover - left) / gw * self.span
            i = min(range(len(self.ts)), key=lambda k: abs(self.ts[k] - t))
            if abs(self.ts[i] - t) < self.span / 50:
                x = X(self.ts[i])
                cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.45)
                cr.set_line_width(1)
                cr.move_to(round(x) + 0.5, T)
                cr.line_to(round(x) + 0.5, T + gh)
                cr.stroke()
                parts = [f"{i18n.tr(n)} {vs[i]:.0f}{self.unit}" for n, _c, vs in self.series if vs[i] is not None]
                text = time.strftime("%H:%M  ", time.localtime(self.ts[i])) + " · ".join(parts)
                lay = self.create_pango_layout(text)
                tw, th = lay.get_pixel_size()
                bx = min(max(x - tw / 2 - 6, left), w - tw - 14)
                cr.set_source_rgba(0, 0, 0, 0.75)
                cr.rectangle(bx, 6, tw + 12, th + 6)
                cr.fill()
                cr.set_source_rgba(1, 1, 1, 1)
                cr.move_to(bx + 6, 9)
                PangoCairo.show_layout(cr, lay)


class HistoryPage(Gtk.ScrolledWindow):
    RANGES = ((3600, "Siste time"), (86400, "Siste døgn"), (7 * 86400, "Siste uke"))

    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(12)
        self.set_child(box)
        top = Gtk.Box(spacing=8)
        self.summary = Gtk.Label(xalign=0, hexpand=True, wrap=True)
        self.summary.add_css_class("dim-label")
        top.append(self.summary)
        seg = Gtk.Box()
        seg.add_css_class("linked")
        first = None
        self.span = 86400
        for secs, text in self.RANGES:
            b = Gtk.ToggleButton(label=i18n.tr(text), active=(secs == self.span))
            if first:
                b.set_group(first)
            first = first or b
            b.connect("toggled", lambda btn, s=secs: btn.get_active() and self._set_span(s))
            seg.append(b)
        top.append(seg)
        box.append(top)
        self.charts = {}
        for key, title, unit, mx in (("temp", "Temperaturer", "°", None), ("load", "Last", "%", 100),
                                     ("watts", "Strømforbruk", " W", None)):
            c = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            c.add_css_class("card")
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            for side, v in (("top", 14), ("bottom", 12), ("start", 14), ("end", 14)):
                getattr(inner, f"set_margin_{side}")(v)
            c.append(inner)
            hrow = Gtk.Box(spacing=14)
            lab = Gtk.Label(label=i18n.tr(title), xalign=0, hexpand=True)
            lab.add_css_class("heading")
            hrow.append(lab)
            for name, colr in (([("CPU", "#3584e4"), ("GPU", "#f68c26")] if key != "watts" else
                                [(i18n.tr("Hele PC-en"), "#33b86b")])):
                leg = Gtk.Label()
                leg.set_markup(f'<span foreground="{colr}">●</span> {name}')
                leg.add_css_class("caption")
                hrow.append(leg)
            inner.append(hrow)
            ch = Chart(unit, mx)
            inner.append(ch)
            self.charts[key] = ch
            box.append(c)
        self.refresh()
        self._t = GLib.timeout_add_seconds(30, self.refresh)

    def _set_span(self, s):
        self.span = s
        self.refresh()

    def refresh(self):
        rows = query(self.span)
        ts = [r[0] for r in rows]
        col = lambda i: [r[i] for r in rows]  # noqa: E731
        BLUE, ORANGE, GREEN = (0.21, 0.52, 0.89), (0.96, 0.55, 0.15), (0.20, 0.72, 0.42)
        self.charts["temp"].set_data(ts, [("CPU", BLUE, col(1)), ("GPU", ORANGE, col(2))], self.span)
        self.charts["load"].set_data(ts, [("CPU", BLUE, col(3)), ("GPU", ORANGE, col(4))], self.span)
        self.charts["watts"].set_data(ts, [("Strøm", GREEN, col(5))], self.span)
        st = stats(self.span)
        if st and st[4]:
            import power
            hours = st[4] * 10 / 3600
            kwh = (st[3] or 0) * hours / 1000
            parts = []
            if st[0] is not None:
                parts.append(f"CPU maks {st[0]:.0f} °C")
            if st[1] is not None:
                parts.append(f"GPU maks {st[1]:.0f} °C")
            if st[3]:
                parts.append(f"snitt {st[3]:.0f} W · {kwh:.2f} kWh ≈ {kwh * power.load()['price']:.2f} kr")
            parts.append(f"PC-en var på {hours:.1f} t")
            self.summary.set_label(" · ".join(i18n.tr(p) for p in parts))
        else:
            self.summary.set_label(i18n.tr("Historikken fylles mens Kontrollsenter kjører (også i bakgrunnen)."))
        return True
