"""Viftekurver: viftefarten følger temperaturen (CPU for hovedkortviftene, GPU for skjermkortet).

Kurven har fire punkter du drar i. Kontrollsenter justerer viftene hvert 3. sekund.
Sikkerhet: hovedkortvifter går aldri under 20 %, skjermkortet aldri under 30 %, og
overopphetingsvernet (alt til auto ved 90/85 °C) gjelder fortsatt.
"""
import json
import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

import i18n  # noqa: E402

CFG = os.path.expanduser("~/.config/systemmonitor/viftekurver.json")
DEFAULT = {"active": False,
           "board": [[30, 25], [50, 35], [70, 60], [85, 100]],
           "gpu": [[40, 30], [60, 40], [75, 70], [85, 100]]}
MIN = {"board": 20, "gpu": 30}


def load():
    try:
        with open(CFG) as f:
            d = json.load(f)
        return {**DEFAULT, **d}
    except (OSError, ValueError):
        return json.loads(json.dumps(DEFAULT))


def save(cfg):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    with open(CFG, "w") as f:
        json.dump(cfg, f)


def interp(points, temp, minimum=0):
    """Viftefart (%) for en temperatur, lineært mellom punktene."""
    if temp is None:
        return None
    pts = sorted(points)
    if temp <= pts[0][0]:
        v = pts[0][1]
    elif temp >= pts[-1][0]:
        v = pts[-1][1]
    else:
        v = pts[-1][1]
        for (t0, p0), (t1, p1) in zip(pts, pts[1:]):
            if t0 <= temp <= t1:
                v = p0 + (p1 - p0) * (temp - t0) / max(t1 - t0, 1e-6)
                break
    return int(round(max(minimum, min(100, v))))


class CurveEditor(Gtk.DrawingArea):
    """Graf med fire punkter du kan dra: x = temperatur (20–100 °C), y = viftefart (0–100 %)."""
    T0, T1 = 20, 100

    def __init__(self, points, minimum, color=(0.21, 0.52, 0.89)):
        super().__init__()
        self.points = [list(p) for p in points]
        self.minimum, self.color = minimum, color
        self.now = None
        self.drag = None
        self.set_content_height(220)
        self.set_hexpand(True)
        self.set_draw_func(self._draw)
        g = Gtk.GestureDrag()
        g.connect("drag-begin", self._begin)
        g.connect("drag-update", self._update)
        g.connect("drag-end", lambda *_: setattr(self, "drag", None))
        self.add_controller(g)
        self._start = (0, 0)

    # koordinater
    def _box(self):
        w, h = self.get_width(), self.get_height()
        return 50, 10, w - 74, h - 34          # x, y, bredde, høyde for selve grafen

    def _to_px(self, t, p):
        x, y, w, h = self._box()
        return x + (t - self.T0) / (self.T1 - self.T0) * w, y + h - p / 100 * h

    def _from_px(self, px, py):
        x, y, w, h = self._box()
        return self.T0 + (px - x) / w * (self.T1 - self.T0), (y + h - py) / h * 100

    def _begin(self, _g, x, y):
        best, bd = None, 1e9
        for i, (t, p) in enumerate(self.points):
            px, py = self._to_px(t, p)
            d = (px - x) ** 2 + (py - y) ** 2
            if d < bd:
                best, bd = i, d
        self.drag = best if bd < 30 ** 2 else None
        self._start = (x, y)

    def _update(self, _g, dx, dy):
        if self.drag is None:
            return
        t, p = self._from_px(self._start[0] + dx, self._start[1] + dy)
        i = self.drag
        lo = self.points[i - 1][0] + 2 if i > 0 else self.T0
        hi = self.points[i + 1][0] - 2 if i < len(self.points) - 1 else self.T1
        self.points[i] = [int(round(max(lo, min(hi, t)))), int(round(max(self.minimum, min(100, p))))]
        # farten skal ikke synke når temperaturen stiger
        for k in range(1, len(self.points)):
            self.points[k][1] = max(self.points[k][1], self.points[k - 1][1])
        self.queue_draw()

    def set_now(self, temp):
        if temp != self.now:
            self.now = temp
            self.queue_draw()

    def _draw(self, _a, cr, _w, _h):
        x, y, w, h = self._box()
        fg = self.get_color()
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.06)
        cr.rectangle(x, y, w, h)
        cr.fill()
        cr.set_line_width(1)
        from gi.repository import PangoCairo
        for t in range(20, 101, 20):
            px, _ = self._to_px(t, 0)
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.10)
            cr.move_to(round(px) + 0.5, y)
            cr.line_to(round(px) + 0.5, y + h)
            cr.stroke()
            lay = self.create_pango_layout(f"{t}°")
            tw, _th = lay.get_pixel_size()
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.6)
            cr.move_to(px - tw / 2, y + h + 6)
            PangoCairo.show_layout(cr, lay)
        for p in (0, 50, 100):
            _, py = self._to_px(self.T0, p)
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.10)
            cr.move_to(x, round(py) + 0.5)
            cr.line_to(x + w, round(py) + 0.5)
            cr.stroke()
            lay = self.create_pango_layout(f"{p}%")
            tw, th = lay.get_pixel_size()
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.6)
            cr.move_to(x - tw - 6, py - th / 2)
            PangoCairo.show_layout(cr, lay)
        # kurven (flat før første og etter siste punkt)
        r, g, b = self.color
        pts = [(self.T0, self.points[0][1])] + [tuple(p) for p in self.points] + [(self.T1, self.points[-1][1])]
        cr.set_source_rgba(r, g, b, 1)
        cr.set_line_width(2.5)
        for i, (t, p) in enumerate(pts):
            (cr.move_to if i == 0 else cr.line_to)(*self._to_px(t, p))
        cr.stroke_preserve()
        cr.line_to(*self._to_px(self.T1, 0))
        cr.line_to(*self._to_px(self.T0, 0))
        cr.close_path()
        cr.set_source_rgba(r, g, b, 0.15)
        cr.fill()
        for t, p in self.points:
            px, py = self._to_px(t, p)
            cr.arc(px, py, 7, 0, 6.3)
            cr.set_source_rgba(r, g, b, 1)
            cr.fill()
            cr.arc(px, py, 3, 0, 6.3)
            cr.set_source_rgba(1, 1, 1, 1)
            cr.fill()
        if self.now is not None:                         # nåværende temperatur
            px, py = self._to_px(max(self.T0, min(self.T1, self.now)), interp(self.points, self.now, self.minimum))
            cr.set_source_rgba(0.88, 0.27, 0.29, 0.9)
            cr.set_line_width(1.5)
            cr.move_to(round(px) + 0.5, y)
            cr.line_to(round(px) + 0.5, y + h)
            cr.stroke()
            cr.arc(px, py, 5, 0, 6.3)
            cr.fill()


class CurveDialog(Adw.Dialog):
    def __init__(self, fancard, cpu_t=None, gpu_t=None):
        super().__init__(title=i18n.tr("Viftekurver"), content_width=760, content_height=720)
        self.card = fancard
        cfg = load()
        tv = Adw.ToolbarView()
        hb = Adw.HeaderBar()
        tv.add_top_bar(hb)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(18)
        intro = Gtk.Label(label=i18n.tr("Dra i punktene. Den røde streken viser temperaturen nå. Farten øker aldri "
                                        "mindre når det blir varmere."), wrap=True, xalign=0)
        intro.add_css_class("dim-label")
        box.append(intro)
        self.eds = {}
        for key, title, now, col in (("board", "Hovedkortvifter – følger CPU-temperaturen", cpu_t, (0.21, 0.52, 0.89)),
                                     ("gpu", "Skjermkort – følger GPU-temperaturen", gpu_t, (0.96, 0.55, 0.15))):
            if key == "gpu" and "gpu" not in fancard.rows:
                continue
            lab = Gtk.Label(label=i18n.tr(title), xalign=0)
            lab.add_css_class("heading")
            box.append(lab)
            ed = CurveEditor(cfg[key], MIN[key], col)
            ed.set_now(now)
            box.append(ed)
            self.eds[key] = ed
        btns = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        std = Gtk.Button(label=i18n.tr("Standardkurve"))
        std.connect("clicked", self._default)
        btns.append(std)
        use = Gtk.Button(label=i18n.tr("Bruk kurvene"))
        use.add_css_class("suggested-action")
        use.connect("clicked", self._use)
        btns.append(use)
        box.append(btns)
        sc = Gtk.ScrolledWindow(child=box, hscrollbar_policy=Gtk.PolicyType.NEVER)
        tv.set_content(sc)
        self.set_child(tv)
        self._t = GLib.timeout_add(1000, self._tick)
        self.connect("closed", lambda *_: GLib.source_remove(self._t))

    def _tick(self):
        temps = self.card.last_temps
        if "board" in self.eds:
            self.eds["board"].set_now(temps[0])
        if "gpu" in self.eds:
            self.eds["gpu"].set_now(temps[1])
        return True

    def _default(self, *_):
        for key, ed in self.eds.items():
            ed.points = [list(p) for p in DEFAULT[key]]
            ed.queue_draw()

    def _use(self, *_):
        cfg = load()
        for key, ed in self.eds.items():
            cfg[key] = ed.points
        cfg["active"] = True
        save(cfg)
        self.card.set_curve(True)
        self.close()
