"""Detaljvinduet som åpnes når du trykker på en flis eller et kort i Oversikt."""
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

import details  # noqa: E402
import i18n  # noqa: E402

ICONS = {"cpu": "ks-overview-symbolic", "gpu": "ks-gpu-symbolic", "mem": "ks-programs-symbolic",
         "disk": "ks-disk-symbolic", "net": "ks-network-symbolic", "temps": "ks-power-symbolic",
         "watt": "ks-power-symbolic", "mode": "ks-auto-symbolic", "bat": "ks-power-symbolic",
         "fans": "ks-auto-symbolic", "health": "ks-tools-symbolic", "info": "ks-laptop-symbolic"}


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _fmt(v, unit):
    if unit == "B/s":
        from sensors import fmt_rate
        return fmt_rate(v)
    return f"{v:.0f} {unit}"


class Chart(Gtk.DrawingArea):
    """Myk linjegraf med fargetoning under – siste 10 minutter."""

    def __init__(self):
        super().__init__(content_height=170, hexpand=True)
        self.series = []
        self.set_draw_func(self._draw)

    def set_series(self, series):
        self.series = series
        self.queue_draw()

    def _draw(self, _a, cr, w, h):
        ser = [s for s in self.series if s.get("pts")]
        if not ser:
            return
        top = max([s.get("max") or 0 for s in ser] + [max(max(s["pts"]), 0.0001) * 1.15 for s in ser])
        pad_b, pad_t = 18, 8
        fg = self.get_color()
        cr.set_source_rgba(fg.red, fg.green, fg.blue, .08)
        cr.set_line_width(1)
        for i in range(1, 4):
            y = pad_t + (h - pad_t - pad_b) * i / 4
            cr.move_to(0, y)
            cr.line_to(w, y)
        cr.stroke()
        for s in ser:
            pts = s["pts"]
            n = max(len(pts) - 1, 1)
            xy = [(w * i / n, pad_t + (h - pad_t - pad_b) * (1 - v / top)) for i, v in enumerate(pts)]
            r, g, b = _hex(s.get("color", "#5b8cff"))
            cr.move_to(*xy[0])
            for (x0, y0), (x1, y1) in zip(xy, xy[1:]):
                mx = (x0 + x1) / 2
                cr.curve_to(mx, y0, mx, y1, x1, y1)
            path = cr.copy_path()
            cr.line_to(xy[-1][0], h - pad_b)
            cr.line_to(xy[0][0], h - pad_b)
            cr.close_path()
            import cairo
            grad = cairo.LinearGradient(0, pad_t, 0, h - pad_b)
            grad.add_color_stop_rgba(0, r, g, b, .35)
            grad.add_color_stop_rgba(1, r, g, b, 0)
            cr.set_source(grad)
            cr.fill()
            cr.new_path()
            cr.append_path(path)
            cr.set_source_rgb(r, g, b)
            cr.set_line_width(2.2)
            cr.stroke()
        cr.set_source_rgba(fg.red, fg.green, fg.blue, .55)
        cr.select_font_face("Sans")
        cr.set_font_size(11)
        cr.move_to(2, h - 4)
        cr.show_text(i18n.tr("10 min siden"))
        txt = i18n.tr("nå")
        ext = cr.text_extents(txt)
        cr.move_to(w - ext.width - 4, h - 4)
        cr.show_text(txt)
        lbl = _fmt(top, ser[0].get("unit", ""))
        cr.move_to(2, pad_t + 10)
        cr.show_text(lbl)


class DetailsDialog(Adw.Dialog):
    def __init__(self, win, kind):
        super().__init__(content_width=620, content_height=760)
        self.win, self.kind = win, kind
        self.set_title(i18n.tr(details.TITLES.get(kind, "")))
        tv = Adw.ToolbarView()
        tv.add_top_bar(Adw.HeaderBar())
        sc = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(18)
        sc.set_child(Adw.Clamp(maximum_size=640, child=box))
        tv.set_content(sc)
        self.set_child(tv)

        hero = Gtk.Box(spacing=14)
        ic = Gtk.Image(icon_name=ICONS.get(kind, "ks-overview-symbolic"), pixel_size=28, valign=Gtk.Align.CENTER)
        ic.add_css_class("tile-icon")
        hero.append(ic)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
        self.h_title = Gtk.Label(xalign=0, wrap=True)
        self.h_title.add_css_class("title-4")
        col.append(self.h_title)
        self.h_sub = Gtk.Label(xalign=0)
        self.h_sub.add_css_class("dim-label")
        col.append(self.h_sub)
        hero.append(col)
        self.h_val = Gtk.Label(valign=Gtk.Align.CENTER)
        self.h_val.add_css_class("title-1")
        self.h_val.add_css_class("numeric")
        hero.append(self.h_val)
        box.append(hero)

        chart_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        chart_card.add_css_class("card")
        self.chart = Chart()
        for side in ("top", "bottom", "start", "end"):
            getattr(self.chart, f"set_margin_{side}")(12)
        chart_card.append(self.chart)
        self.legend = Gtk.Box(spacing=14, margin_start=14, margin_bottom=10)
        chart_card.append(self.legend)
        self.chart_card = chart_card
        box.append(chart_card)

        if kind == "watt":
            b = Gtk.Button(label=i18n.tr("Strømpris og målinger …"), halign=Gtk.Align.START)
            b.connect("clicked", lambda *_: __import__("power").dialog(win))
            box.append(b)
        self.sec_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.append(self.sec_box)
        self._groups = {}
        self._legend_sig = None
        self.refresh()
        self._tid = GLib.timeout_add(2000, self._tick)
        self.connect("closed", lambda *_: GLib.source_remove(self._tid))

    def _tick(self):
        self.refresh()
        return True

    def refresh(self):
        try:
            d = details.collect(self.win, self.kind)
        except Exception:  # noqa: BLE001
            return
        self.h_title.set_label(i18n.tr(d.get("title") or ""))
        self.h_sub.set_label(i18n.tr(d.get("sub") or ""))
        self.h_sub.set_visible(bool(d.get("sub")))
        self.h_val.set_label(d.get("value") or "")
        ser = d.get("series") or []
        self.chart_card.set_visible(any(s.get("pts") for s in ser))
        self.chart.set_series(ser)
        sig = tuple(s["name"] for s in ser)
        if sig != self._legend_sig:
            self._legend_sig = sig
            while self.legend.get_first_child():
                self.legend.remove(self.legend.get_first_child())
            if len(ser) > 1:
                for s in ser:
                    lb = Gtk.Label()
                    lb.set_markup(f'<span foreground="{s["color"]}">●</span> {GLib.markup_escape_text(i18n.tr(s["name"]))}')
                    lb.add_css_class("caption")
                    self.legend.append(lb)
        seen = set()
        for sec in d.get("sections") or []:
            key = sec["title"]
            seen.add(key)
            g = self._groups.get(key)
            if g is None:
                g = self._new_group(sec)
            self._fill(g, sec)
        for key, g in self._groups.items():
            g["w"].set_visible(key in seen)

    def _new_group(self, sec):
        grp = Adw.PreferencesGroup(title=i18n.tr(sec["title"]))
        lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        lb.add_css_class("boxed-list")
        grp.add(lb)
        g = {"w": grp, "lb": lb, "rows": {}}
        self._groups[sec["title"]] = g
        self.sec_box.append(grp)
        return g

    def _fill(self, g, sec):
        names = set()
        if "bars" in sec:
            for i, (name, pct, txt) in enumerate(sec["bars"]):
                key = i
                names.add(key)
                r = g["rows"].get(key)
                if r is None:
                    row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
                    for side, v in (("top", 10), ("bottom", 10), ("start", 14), ("end", 14)):
                        getattr(row, f"set_margin_{side}")(v)
                    top = Gtk.Box(spacing=8)
                    a = Gtk.Label(label=i18n.tr(name), xalign=0, hexpand=True, ellipsize=3)
                    b = Gtk.Label(xalign=1)
                    b.add_css_class("dim-label")
                    b.add_css_class("numeric")
                    top.append(a)
                    top.append(b)
                    row.append(top)
                    bar = Gtk.LevelBar(min_value=0, max_value=100)
                    bar.set_size_request(-1, 8)
                    bar.add_offset_value("low", 70)
                    bar.add_offset_value("high", 85)
                    bar.add_offset_value("full", 100)
                    row.append(bar)
                    lr = Gtk.ListBoxRow(activatable=False, child=row)
                    g["lb"].append(lr)
                    r = g["rows"][key] = (lr, b, bar, a)
                r[3].set_label(i18n.tr(name))
                r[1].set_label(txt)
                r[2].set_value(max(0, min(100, pct or 0)))
        else:
            for i, (name, val) in enumerate(sec.get("rows") or []):
                key = i
                names.add(key)
                r = g["rows"].get(key)
                if r is None:
                    row = Adw.ActionRow(title=GLib.markup_escape_text(i18n.tr(name)))
                    row.set_title_lines(1)
                    v = Gtk.Label(xalign=1, wrap=True, max_width_chars=34, justify=Gtk.Justification.RIGHT)
                    v.add_css_class("numeric")
                    v.set_selectable(True)
                    row.add_suffix(v)
                    g["lb"].append(row)
                    r = g["rows"][key] = (row, v)
                if r[0].get_title() != GLib.markup_escape_text(i18n.tr(name)):
                    r[0].set_title(GLib.markup_escape_text(i18n.tr(name)))
                val = str(val)
                long = len(val) > 42                       # lange forklaringer under tittelen, ikke ved siden av
                r[0].set_subtitle(GLib.markup_escape_text(val) if long else "")
                r[0].set_subtitle_lines(0)
                r[0].set_title_lines(0 if long else 1)
                r[1].set_visible(not long)
                r[1].set_label("" if long else val)
                r[1].set_width_chars(min(len(val), 30))
        for key, r in g["rows"].items():
            r[0].set_visible(key in names)

