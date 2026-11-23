"""Kalender med norske røde dager – bla så langt fram (eller tilbake) i tid du vil. Hjemmet › Kalender."""
import calendar
import datetime as dt

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk  # noqa: E402

import helligdager as H  # noqa: E402
import i18n  # noqa: E402

MONTHS = ["januar", "februar", "mars", "april", "mai", "juni", "juli", "august", "september", "oktober", "november",
          "desember"]
WD = ["man", "tir", "ons", "tor", "fre", "lør", "søn"]
WD_LONG = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"]
CSS = """
.ks-cal-day { min-width: 46px; min-height: 46px; border-radius: 12px; padding: 2px; font-weight: 600; }
.ks-cal-day.out { opacity: .35; }
.ks-cal-day.red { color: #ff4d4d; }
.ks-cal-day.holiday { background: alpha(#ff4d4d, 0.16); }
.ks-cal-day.today { box-shadow: inset 0 0 0 2px @accent_bg_color; }
.ks-cal-day.sel { background: @accent_bg_color; color: @accent_fg_color; }
.ks-cal-dot { font-size: 9px; color: @accent_color; }
.ks-cal-wd { font-size: .8em; font-weight: 800; opacity: .6; }
.ks-cal-wk { font-size: .75em; opacity: .45; }
.ks-cal-title { font-size: 1.5em; font-weight: 800; }
.ks-cal-red { color: #ff4d4d; font-weight: 700; }
"""


def _card(title, sub=None):
    c = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    c.add_css_class("card")
    for s, v in (("top", 14), ("bottom", 14), ("start", 16), ("end", 16)):
        getattr(c, f"set_margin_{s}")(0)
    inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=14, margin_bottom=14, margin_start=16,
                    margin_end=16)
    t = Gtk.Label(label=i18n.tr(title), xalign=0)
    t.add_css_class("heading")
    inner.append(t)
    if sub:
        d = Gtk.Label(label=i18n.tr(sub), xalign=0, wrap=True)
        d.add_css_class("dim-label")
        d.add_css_class("caption")
        inner.append(d)
    c.append(inner)
    return c, inner


class CalendarPage(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        try:
            import theme
            theme.add_css(CSS)
        except Exception:  # noqa: BLE001
            pass
        today = dt.date.today()
        self.year, self.month, self.sel = today.year, today.month, today
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=12, margin_bottom=12,
                      margin_start=12, margin_end=12)
        self.set_child(box)
        top = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=2, min_children_per_line=1,
                          column_spacing=12, row_spacing=12, homogeneous=False)
        box.append(top)

        # ---- måneden
        mc, mi = _card("Kalender", "Norske røde dager er markert med rødt. Bla så langt fram i tid du vil.")
        nav = Gtk.Box(spacing=6)
        prev = Gtk.Button(icon_name="go-previous-symbolic", tooltip_text=i18n.tr("Forrige måned"))
        prev.connect("clicked", lambda *_: self._step(-1))
        nav.append(prev)
        self.title = Gtk.Label(hexpand=True)
        self.title.add_css_class("ks-cal-title")
        nav.append(self.title)
        nxt = Gtk.Button(icon_name="go-next-symbolic", tooltip_text=i18n.tr("Neste måned"))
        nxt.connect("clicked", lambda *_: self._step(1))
        nav.append(nxt)
        mi.append(nav)
        jump = Gtk.Box(spacing=6)
        tb = Gtk.Button(label=i18n.tr("I dag"))
        tb.connect("clicked", lambda *_: self._goto(dt.date.today()))
        jump.append(tb)
        jump.append(Gtk.Label(label=i18n.tr("År:"), margin_start=8))
        self.year_spin = Gtk.SpinButton.new_with_range(1900, 2300, 1)
        self.year_spin.set_value(self.year)
        self.year_spin.connect("value-changed", lambda s: self._set_year(int(s.get_value())))
        jump.append(self.year_spin)
        self.month_dd = Gtk.DropDown.new_from_strings([m.capitalize() for m in MONTHS])
        self.month_dd.set_selected(self.month - 1)
        self.month_dd.connect("notify::selected", lambda d, _p: self._set_month(d.get_selected() + 1))
        jump.append(self.month_dd)
        mi.append(jump)
        self.grid = Gtk.Grid(column_spacing=4, row_spacing=4, halign=Gtk.Align.CENTER, margin_top=6)
        mi.append(self.grid)
        self.info = Gtk.Label(xalign=0, wrap=True, margin_top=6)
        mi.append(self.info)
        top.append(mc)

        # ---- neste røde dager og hele året
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        uc, self.up_box = _card("Neste røde dager")
        side.append(uc)
        yc, self.year_box = _card("Røde dager i året", "🏖️ = langhelg (fredag eller mandag).")
        self.year_title = yc.get_first_child().get_first_child()
        side.append(yc)
        top.append(side)
        self._render()

    # ---- navigasjon
    def _step(self, n):
        m = self.month - 1 + n
        self._goto_month(self.year + m // 12, m % 12 + 1)

    def _goto(self, d):
        self.sel = d
        self._goto_month(d.year, d.month)

    def _goto_month(self, y, m):
        self.year, self.month = max(1900, min(2300, y)), m
        self.year_spin.set_value(self.year)
        self.month_dd.set_selected(self.month - 1)
        self._render()

    def _set_year(self, y):
        if y != self.year:
            self.year = y
            self._render()

    def _set_month(self, m):
        if m != self.month:
            self.month = m
            self._render()

    # ---- tegning
    def _render(self):
        y, m = self.year, self.month
        self.title.set_label(f"{MONTHS[m - 1].capitalize()} {y}")
        while (c := self.grid.get_first_child()) is not None:
            self.grid.remove(c)
        wk = Gtk.Label(label=i18n.tr("uke"))
        wk.add_css_class("ks-cal-wd")
        self.grid.attach(wk, 0, 0, 1, 1)
        for i, w in enumerate(WD):
            lab = Gtk.Label(label=w)
            lab.add_css_class("ks-cal-wd")
            if i == 6:
                lab.add_css_class("ks-cal-red")
            self.grid.attach(lab, i + 1, 0, 1, 1)
        today = dt.date.today()
        weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(y, m)
        for r, week in enumerate(weeks, start=1):
            wn = Gtk.Label(label=str(week[0].isocalendar()[1]))
            wn.add_css_class("ks-cal-wk")
            self.grid.attach(wn, 0, r, 1, 1)
            for c, d in enumerate(week, start=1):
                nm = H.name(d)
                b = Gtk.Button()
                v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
                v.append(Gtk.Label(label=str(d.day)))
                dot = Gtk.Label(label="●" if nm and not H.red_days(d.year).get(d) else " ")
                dot.add_css_class("ks-cal-dot")
                v.append(dot)
                b.set_child(v)
                b.add_css_class("flat")
                b.add_css_class("ks-cal-day")
                if d.month != m:
                    b.add_css_class("out")
                if H.is_red(d):
                    b.add_css_class("red")
                if d in H.red_days(d.year):
                    b.add_css_class("holiday")
                if d == today:
                    b.add_css_class("today")
                if d == self.sel:
                    b.add_css_class("sel")
                if nm:
                    b.set_tooltip_text(nm)
                b.connect("clicked", lambda _b, dd=d: self._pick(dd))
                self.grid.attach(b, c, r, 1, 1)
        self._show_info()
        self._lists()

    def _pick(self, d):
        self.sel = d
        if d.month != self.month or d.year != self.year:
            self._goto_month(d.year, d.month)
        else:
            self._render()

    def _show_info(self):
        d = self.sel
        n = (d - dt.date.today()).days
        when = (i18n.tr("i dag") if n == 0 else i18n.tr("i morgen") if n == 1 else i18n.tr("i går") if n == -1 else
                (f"om {n} dager" if n > 0 else f"for {-n} dager siden"))
        nm = H.name(d)
        red = d in H.red_days(d.year)
        txt = f"<b>{WD_LONG[d.weekday()].capitalize()} {d.day}. {MONTHS[d.month - 1]} {d.year}</b> · uke " \
              f"{d.isocalendar()[1]} · {when}"
        if nm:
            txt += f"\n<span foreground=\"#ff4d4d\" weight=\"bold\">{GLib.markup_escape_text(nm)}</span>" if red else \
                f"\n{GLib.markup_escape_text(nm)}"
        elif d.weekday() == 6:
            txt += "\n" + i18n.tr("Søndag (rød dag)")
        self.info.set_markup(txt)

    def _lists(self):
        for b in (self.up_box, self.year_box):
            ch = b.get_first_child().get_next_sibling()           # behold overskriften (og forklaringen)
            if b is self.year_box:
                ch = ch.get_next_sibling() if ch else None
            while ch is not None:
                nx = ch.get_next_sibling()
                b.remove(ch)
                ch = nx
        for d, nm, n in H.upcoming(8):
            self.up_box.append(self._row(d, nm, "i dag" if n == 0 else "i morgen" if n == 1 else f"om {n} dager"))
        self.year_title.set_label(i18n.tr("Røde dager i") + f" {self.year}")
        lw = {d for d, _n in H.long_weekends(self.year)}
        for d, nm in H.red_days(self.year).items():
            self.year_box.append(self._row(d, nm + ("  🏖️" if d in lw else ""), WD_LONG[d.weekday()]))

    def _row(self, d, nm, right):
        r = Gtk.Button()
        r.add_css_class("flat")
        h = Gtk.Box(spacing=10)
        dl = Gtk.Label(label=f"{d.day}. {MONTHS[d.month - 1][:3]}" + (f" {d.year}" if d.year != self.year else ""),
                       xalign=0, width_chars=11)
        dl.add_css_class("ks-cal-red")
        h.append(dl)
        h.append(Gtk.Label(label=nm, xalign=0, hexpand=True))
        rl = Gtk.Label(label=right, xalign=1)
        rl.add_css_class("dim-label")
        h.append(rl)
        r.set_child(h)
        r.connect("clicked", lambda *_: self._goto(d))
        return r
