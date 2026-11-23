"""Hjemmet › Kalender: måned, uke, år og dagbok. Røde dager, egne hendelser (delt med huset), bursdager og ukeplan
fra Familie, skoleferier, flaggdager, månefaser, sol, ferieplanlegger, søk og utskrift. Se kalender.py / dagbok.py."""
import calendar
import datetime as dt
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

import helligdager as H  # noqa: E402
import i18n  # noqa: E402
import kalender as K  # noqa: E402

MONTHS = ["januar", "februar", "mars", "april", "mai", "juni", "juli", "august", "september", "oktober", "november",
          "desember"]
WD = ["man", "tir", "ons", "tor", "fre", "lør", "søn"]
WD_LONG = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"]
SEASON = {12: "#5b8cff", 1: "#5b8cff", 2: "#5b8cff", 3: "#2ecc71", 4: "#2ecc71", 5: "#2ecc71", 6: "#feca57",
          7: "#feca57", 8: "#feca57", 9: "#ff9f43", 10: "#ff9f43", 11: "#ff9f43"}
REPEATS = [("", "Ikke gjenta"), ("weekly", "Hver uke"), ("days:14", "Hver 2. uke"), ("monthly", "Hver måned"),
           ("months:3", "Hver 3. måned"), ("months:6", "Hvert halvår"), ("yearly", "Hvert år"),
           ("months:24", "Hvert 2. år")]
REMINDS = [(-1, "Ingen påminnelse"), (0, "Når det starter"), (15, "15 min før"), (30, "30 min før"),
           (60, "1 time før"), (1440, "Dagen før")]
CSS = """
.ks-cal-day { min-width: 50px; min-height: 54px; border-radius: 12px; padding: 2px; font-weight: 600; }
.ks-cal-day.out { opacity: .35; }
.ks-cal-day.red { color: #ff4d4d; }
.ks-cal-day.holiday { background: alpha(#ff4d4d, 0.16); }
.ks-cal-day.school { box-shadow: inset 0 -3px alpha(#1dd1a1, 0.8); }
.ks-cal-day.today { box-shadow: inset 0 0 0 2px @accent_bg_color; }
.ks-cal-day.sel { background: @accent_bg_color; color: @accent_fg_color; }
.ks-cal-dots { font-size: 8px; letter-spacing: 1px; }
.ks-cal-wd { font-size: .8em; font-weight: 800; opacity: .6; }
.ks-cal-wk { font-size: .85em; font-weight: 800; border-radius: 8px; padding: 2px 5px; min-width: 22px; }
.ks-cal-wk.even { background: alpha(@accent_bg_color, 0.20); color: @accent_color; }
.ks-cal-wk.odd { background: alpha(@window_fg_color, 0.08); opacity: .8; }
.ks-cal-weekbig { font-size: 1.05em; margin-bottom: 2px; }
.ks-cal-title { font-size: 1.5em; font-weight: 800; }
.ks-cal-red { color: #ff4d4d; font-weight: 700; }
.ks-cal-item { border-radius: 10px; padding: 6px 10px; background: alpha(@window_fg_color, 0.06); }
.ks-cal-item.done label { text-decoration: line-through; opacity: .6; }
.ks-cal-chip { border-radius: 6px; padding: 1px 5px; font-size: .78em; }
.ks-year-month { border-radius: 12px; padding: 6px; background: alpha(@window_fg_color, 0.04); }
.ks-year-day { font-size: .78em; min-width: 22px; min-height: 20px; padding: 0; border-radius: 6px; }
.ks-diary-lock { font-size: 3em; }
.ks-diary-text { border-radius: 12px; padding: 8px; background: alpha(@window_fg_color, 0.05); }
"""


def _bg(fn, done):
    def work():
        try:
            r = fn()
        except Exception as e:  # noqa: BLE001
            r = e
        GLib.idle_add(lambda: (done(r), False)[1])
    threading.Thread(target=work, daemon=True).start()


def _card(title, sub=None):
    c = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    c.add_css_class("card")
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
    c._title = t
    return c, inner


def _clear(box, keep=0):
    ch = box.get_first_child()
    for _ in range(keep):
        ch = ch.get_next_sibling() if ch else None
    while ch is not None:
        nx = ch.get_next_sibling()
        box.remove(ch)
        ch = nx


def _dim(t):
    lab = Gtk.Label(label=t, xalign=0, wrap=True)
    lab.add_css_class("dim-label")
    lab.add_css_class("caption")
    return lab


class CalendarPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        try:
            import theme
            theme.add_css(CSS)
        except Exception:  # noqa: BLE001
            pass
        today = dt.date.today()
        self.year, self.month, self.sel = today.year, today.month, today
        self._items = {}
        # ---- verktøylinje: visning, søk, ⚙️, skriv ut
        bar = Gtk.Box(spacing=8, margin_top=10, margin_start=12, margin_end=12)
        self.views = Adw.ViewStack()
        sw = Adw.ViewSwitcher(stack=self.views, policy=Adw.ViewSwitcherPolicy.WIDE, hexpand=True)
        bar.append(sw)
        self.search = Gtk.SearchEntry(placeholder_text=i18n.tr("Søk i kalenderen …"), width_chars=18)
        self.search.connect("activate", lambda e: self._do_search(e.get_text()))
        bar.append(self.search)
        pr = Gtk.Button(icon_name="document-print-symbolic", tooltip_text=i18n.tr("Skriv ut / lagre som PDF"))
        pr.connect("clicked", lambda *_: self._print())
        bar.append(pr)
        st = Gtk.Button(icon_name="emblem-system-symbolic", tooltip_text=i18n.tr("Innstillinger for kalenderen"))
        st.connect("clicked", lambda *_: self._settings())
        bar.append(st)
        self.append(bar)
        self.append(self.views)

        self.views.add_titled_with_icon(self._month_view(), "maned", i18n.tr("Måned"), "x-office-calendar-symbolic")
        self.views.add_titled_with_icon(self._week_view(), "uke", i18n.tr("Uke"), "view-list-symbolic")
        self.views.add_titled_with_icon(self._year_view(), "ar", i18n.tr("År"), "view-grid-symbolic")
        import dagbok_ui
        self.diary = dagbok_ui.DiaryView()
        self.views.add_titled_with_icon(self.diary, "dagbok", i18n.tr("Dagbok"), "changes-prevent-symbolic")
        self.views.connect("notify::visible-child-name", lambda *_: self._render())
        self.connect("unmap", lambda *_: self.diary.lock())
        self._load()

    # ================= månedsvisning
    def _month_view(self):
        sc = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=2, min_children_per_line=1,
                           column_spacing=12, row_spacing=12, margin_top=12, margin_bottom=12, margin_start=12,
                           margin_end=12, homogeneous=False)
        sc.set_child(flow)
        mc, mi = _card("Kalender")
        self.mcard = mc
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
        self.week_lab = Gtk.Label(halign=Gtk.Align.CENTER)
        self.week_lab.add_css_class("ks-cal-weekbig")
        mi.append(self.week_lab)
        jump = Gtk.Box(spacing=6)
        tb = Gtk.Button(label=i18n.tr("I dag"))
        tb.connect("clicked", lambda *_: self._goto(dt.date.today()))
        jump.append(tb)
        self.year_spin = Gtk.SpinButton.new_with_range(1900, 2300, 1)
        self.year_spin.set_value(self.year)
        self.year_spin.connect("value-changed", lambda s: self._set_ym(int(s.get_value()), self.month))
        jump.append(self.year_spin)
        self.month_dd = Gtk.DropDown.new_from_strings([m.capitalize() for m in MONTHS])
        self.month_dd.set_selected(self.month - 1)
        self.month_dd.connect("notify::selected", lambda d, _p: self._set_ym(self.year, d.get_selected() + 1))
        jump.append(self.month_dd)
        add = Gtk.Button(label="＋ " + i18n.tr("Ny hendelse"))
        add.add_css_class("suggested-action")
        add.connect("clicked", lambda *_: self._edit_event(None, self.sel))
        jump.append(add)
        mi.append(jump)
        self.grid = Gtk.Grid(column_spacing=4, row_spacing=4, halign=Gtk.Align.CENTER, margin_top=6)
        mi.append(self.grid)
        self.mstats = _dim("")
        mi.append(self.mstats)
        flow.append(mc)
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        dc, self.day_box = _card("Dagen")
        self.day_card = dc
        side.append(dc)
        uc, self.up_box = _card("Kommer snart")
        side.append(uc)
        fc, self.fr_box = _card("Når vennene pleier å spille", "Fra når vennene dine har vært på de siste ukene.")
        side.append(fc)
        vc, self.vac_box = _card("Ferieplanlegger", "Få mest mulig fri med færrest feriedager rundt de røde dagene.")
        self.vac_card = vc
        side.append(vc)
        flow.append(side)
        return sc

    # ================= ukevisning
    def _week_view(self):
        sc = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12,
                      margin_start=12, margin_end=12)
        nav = Gtk.Box(spacing=6)
        p = Gtk.Button(icon_name="go-previous-symbolic")
        p.connect("clicked", lambda *_: self._goto(self.sel - dt.timedelta(days=7)))
        nav.append(p)
        self.wtitle = Gtk.Label(hexpand=True)
        self.wtitle.add_css_class("ks-cal-title")
        nav.append(self.wtitle)
        n = Gtk.Button(icon_name="go-next-symbolic")
        n.connect("clicked", lambda *_: self._goto(self.sel + dt.timedelta(days=7)))
        nav.append(n)
        box.append(nav)
        self.week_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.append(self.week_box)
        sc.set_child(box)
        return sc

    # ================= årsvisning
    def _year_view(self):
        sc = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12,
                      margin_start=12, margin_end=12)
        nav = Gtk.Box(spacing=6)
        p = Gtk.Button(icon_name="go-previous-symbolic")
        p.connect("clicked", lambda *_: self._set_ym(self.year - 1, self.month))
        nav.append(p)
        self.ytitle = Gtk.Label(hexpand=True)
        self.ytitle.add_css_class("ks-cal-title")
        nav.append(self.ytitle)
        n = Gtk.Button(icon_name="go-next-symbolic")
        n.connect("clicked", lambda *_: self._set_ym(self.year + 1, self.month))
        nav.append(n)
        box.append(nav)
        self.ystats = _dim("")
        box.append(self.ystats)
        self.year_flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=4,
                                     min_children_per_line=2, column_spacing=10, row_spacing=10, homogeneous=True)
        box.append(self.year_flow)
        sc.set_child(box)
        return sc

    # ================= data og navigasjon
    def _load(self):
        y, m = self.year, self.month
        a = dt.date(y, m, 1) - dt.timedelta(days=7)
        b = dt.date(y, m, calendar.monthrange(y, m)[1]) + dt.timedelta(days=14)
        if self.views.get_visible_child_name() == "ar":
            a, b = dt.date(y, 1, 1), dt.date(y, 12, 31)
        sel = self.sel
        a, b = min(a, sel - dt.timedelta(days=7)), max(b, sel + dt.timedelta(days=7))
        _bg(lambda: K.items(a, b), self._loaded)

    def _loaded(self, it):
        if not isinstance(it, Exception):
            self._items = it
        self._render()

    def _step(self, n):
        m = self.month - 1 + n
        self._set_ym(self.year + m // 12, m % 12 + 1)

    def _goto(self, d):
        self.sel = d
        self._set_ym(d.year, d.month, force=True)

    def _set_ym(self, y, m, force=False):
        y = max(1900, min(2300, y))
        if (y, m) == (self.year, self.month) and not force:
            return
        self.year, self.month = y, m
        self.year_spin.set_value(y)
        self.month_dd.set_selected(m - 1)
        self._load()

    # ================= tegning
    def _render(self):
        v = self.views.get_visible_child_name()
        if v == "maned":
            self._render_month()
        elif v == "uke":
            self._render_week()
        elif v == "ar":
            if not any(d.year == self.year and d.month in (1, 12) for d in self._items):
                self._load()
                return
            self._render_year()

    def _dots(self, d):
        cols = []
        for x in self._items.get(d, []):
            if x.get("kind") in ("red", "moon", "school"):
                continue
            cols.append(x.get("color") or "#888")
        return "".join(f'<span foreground="{c}">●</span>' for c in cols[:4])

    def _render_month(self):
        y, m = self.year, self.month
        self.title.set_label(f"{MONTHS[m - 1].capitalize()} {y}")
        wk_sel = self.sel.isocalendar()[1]
        self.week_lab.set_markup(f"<b>Uke {wk_sel}</b> · " + ("partallsuke" if wk_sel % 2 == 0 else "oddetallsuke")
                                 + f"  <span alpha='60%'>(valgt dag)</span>")
        self.mcard._title.set_markup(f'<span foreground="{SEASON[m]}">●</span> {i18n.tr("Kalender")}')
        _clear(self.grid)
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
        for r, week in enumerate(calendar.Calendar(0).monthdatescalendar(y, m), start=1):
            wnum = week[0].isocalendar()[1]
            wn = Gtk.Label(label=str(wnum), tooltip_text=f"Uke {wnum} – " + ("partallsuke" if wnum % 2 == 0
                                                                             else "oddetallsuke"))
            wn.add_css_class("ks-cal-wk")
            wn.add_css_class("even" if wnum % 2 == 0 else "odd")
            self.grid.attach(wn, 0, r, 1, 1)
            for c, d in enumerate(week, start=1):
                its = self._items.get(d, [])
                b = Gtk.Button()
                v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
                v.append(Gtk.Label(label=str(d.day)))
                moon = next((x["icon"] for x in its if x.get("kind") == "moon"), "")
                dots = Gtk.Label()
                dots.set_markup(self._dots(d) + (" " + moon if moon else "") or " ")
                dots.add_css_class("ks-cal-dots")
                v.append(dots)
                b.set_child(v)
                b.add_css_class("flat")
                b.add_css_class("ks-cal-day")
                for cond, cls in ((d.month != m, "out"), (H.is_red(d), "red"), (d in H.red_days(d.year), "holiday"),
                                  (any(x.get("kind") == "school" for x in its), "school"), (d == today, "today"),
                                  (d == self.sel, "sel")):
                    if cond:
                        b.add_css_class(cls)
                tip = "\n".join(f"{x['icon']} {x['title']}" + (f" {x['time']}" if x.get("time") else "") for x in its)
                if tip:
                    b.set_tooltip_text(tip)
                b.connect("clicked", lambda _b, dd=d: self._pick(dd))
                g = Gtk.GestureClick()
                g.connect("pressed", lambda _g, n, _x, _y, dd=d: n == 2 and self._edit_event(None, dd))
                b.add_controller(g)
                self.grid.attach(b, c, r, 1, 1)
        self.mstats.set_label(f"{K.workdays(y, m)} arbeidsdager i {MONTHS[m - 1]} · {K.workdays(y)} i {y}"
                              " · dobbeltklikk på en dag for å legge til")
        self._render_day()
        self._render_upcoming()
        self._render_friends()
        self._render_vacation()

    def _pick(self, d):
        self.sel = d
        if (d.year, d.month) != (self.year, self.month):
            self._set_ym(d.year, d.month)
        else:
            self._render()

    def _render_day(self):
        d = self.sel
        info = K.day_info(d)
        n = (d - dt.date.today()).days
        when = ("i dag" if n == 0 else "i morgen" if n == 1 else "i går" if n == -1 else
                (f"om {n} dager" if n > 0 else f"for {-n} dager siden"))
        self.day_card._title.set_label(f"{WD_LONG[d.weekday()].capitalize()} {d.day}. {MONTHS[d.month - 1]} {d.year}")
        _clear(self.day_box, 1)
        sun = info["sun"]
        self.day_box.append(_dim(f"Uke {info['week']} ({'partall' if info['week'] % 2 == 0 else 'oddetall'}) · "
                                 f"{when} · {info['moon']}"
                                 + (f" · 🌅 {sun[0]} 🌇 {sun[1]}" if sun else " · ☀️ midnattssol / mørketid")))
        its = self._items.get(d, [])
        for x in its:
            if x.get("kind") == "moon" and not x.get("title"):
                continue
            row = Gtk.Box(spacing=8)
            row.add_css_class("ks-cal-item")
            if x.get("done"):
                row.add_css_class("done")
            lab = Gtk.Label(xalign=0, hexpand=True, wrap=True)
            col = x.get("color") or "#888"
            lab.set_markup(f'<span foreground="{col}">●</span> {GLib.markup_escape_text(x["icon"] + " " + x["title"])}'
                           + (f'  <span alpha="60%">{x["time"]}</span>' if x.get("time") else ""))
            row.append(lab)
            if x.get("src") == "egen":
                if x.get("kind") == "dinner" and x.get("note"):
                    sb = Gtk.Button(label="🛒", tooltip_text=i18n.tr("Legg notatet (ingrediensene) i handlelista"))
                    sb.add_css_class("flat")
                    sb.connect("clicked", lambda _b, xx=x: self._to_shop(xx))
                    row.append(sb)
                if x.get("kind") in ("gamenight", "stream", "event"):
                    ib = Gtk.Button(label="💬", tooltip_text=i18n.tr("Inviter i chatten (svar: Kommer / Kanskje / Nei)"))
                    ib.add_css_class("flat")
                    ib.connect("clicked", lambda _b, xx=x: self._invite(xx, d))
                    row.append(ib)
                if x.get("kind") in ("todo", "routine"):
                    cb = Gtk.CheckButton(active=bool(x.get("done")), tooltip_text=i18n.tr("Gjort"))
                    cb.connect("toggled", lambda w, eid=x["id"]: _bg(lambda: K.mark_done(eid, d, w.get_active()),
                                                                     lambda _r: self._load()))
                    row.append(cb)
                e = Gtk.Button(icon_name="document-edit-symbolic", tooltip_text=i18n.tr("Endre"))
                e.add_css_class("flat")
                e.connect("clicked", lambda _b, eid=x["id"]: self._edit_event(eid, d))
                row.append(e)
            self.day_box.append(row)
        if not its:
            self.day_box.append(_dim(i18n.tr("Ingenting denne dagen.")))
        a = Gtk.Button(label="＋ " + i18n.tr("Legg til denne dagen"), halign=Gtk.Align.START)
        a.add_css_class("flat")
        a.connect("clicked", lambda *_: self._edit_event(None, d))
        self.day_box.append(a)

    def _render_upcoming(self):
        _clear(self.up_box, 1)
        cd = K.countdown() if K.cfg().get("countdown", True) else None
        if cd:
            lab = Gtk.Label(label="⏳ " + cd[1], xalign=0)
            lab.add_css_class("heading")
            self.up_box.append(lab)
        today = dt.date.today()
        shown = 0
        for d in sorted(x for x in self._items if x >= today):
            for x in self._items[d]:
                if x.get("kind") in ("moon", "school", "special") or shown >= 8:
                    continue
                b = Gtk.Button()
                b.add_css_class("flat")
                h = Gtk.Box(spacing=10)
                dl = Gtk.Label(label=f"{d.day}. {MONTHS[d.month - 1][:3]}", xalign=0, width_chars=8)
                if x.get("red"):
                    dl.add_css_class("ks-cal-red")
                h.append(dl)
                h.append(Gtk.Label(label=f"{x['icon']} {x['title']}" + (f" {x['time']}" if x.get("time") else ""),
                                   xalign=0, hexpand=True, ellipsize=3))
                b.set_child(h)
                b.connect("clicked", lambda _b, dd=d: self._goto(dd))
                self.up_box.append(b)
                shown += 1
        if not shown:
            self.up_box.append(_dim(i18n.tr("Ingenting de neste ukene.")))

    def _render_friends(self):
        _clear(self.fr_box, 2)
        try:
            import kalender_extra
            fu = kalender_extra.friends_usual()
        except Exception:  # noqa: BLE001
            fu = {}
        if not fu:
            self.fr_box.append(_dim(i18n.tr("Ingen data ennå – Kontrollsenter noterer når vennene er på (hvert 15. "
                                            "minutt).")))
        for name, slots in list(fu.items())[:6]:
            self.fr_box.append(Gtk.Label(label=f"👤 {name}: " + ", ".join(slots), xalign=0, wrap=True))

    def _to_shop(self, x):
        import re
        import chatlink
        items = [i.strip() for i in re.split(r"[,\n;]", x.get("note") or "") if i.strip()]
        for i in items:
            chatlink.shop_add(i)
        self._toast(f"🛒 {len(items)} ting lagt i handlelista")

    def _invite(self, x, day):
        import chat
        rooms = [(r, n, i) for r, n, i, _u in chat.rooms() if r not in ("hjemme", "meg")]
        dlg = Adw.AlertDialog(heading=i18n.tr("Inviter i chatten"), body=f"{x['title']} – {day.day}.{day.month}"
                              + (f" kl. {x['time']}" if x.get("time") else ""))
        dd = Gtk.DropDown.new_from_strings([f"{i} {n}" for _r, n, i in rooms] or [i18n.tr("Ingen samtaler")])
        dlg.set_extra_child(dd)
        dlg.add_response("cancel", i18n.tr("Avbryt"))
        dlg.add_response("ok", i18n.tr("Send invitasjon"))
        dlg.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)

        def go(_d, rr):
            if rr != "ok" or not rooms:
                return
            room = rooms[dd.get_selected()][0]
            hh, mm = (int(v) for v in (x.get("time") or "20:00").split(":"))
            when = dt.datetime(day.year, day.month, day.day, hh, mm).timestamp()

            def send():
                bg = getattr(self.get_root(), "bg", None)
                return chat.send(room, f"📅 {x['title']} – {WD_LONG[day.weekday()]} {day.day}.{day.month}"
                                 + (f" kl. {x['time']}" if x.get("time") else ""), None, bg.notify if bg else None,
                                 extra={"kind": "event", "event": {"title": x["title"], "when": when,
                                                                    "options": ["Kommer", "Kanskje", "Nei"]}})
            _bg(send, lambda r_: self._toast(("✗ " if isinstance(r_, Exception) else "💬 ") + str(r_)))
        dlg.connect("response", go)
        dlg.present(self.get_root())

    def _toast(self, t):
        root = self.get_root()
        if hasattr(root, "toast"):
            root.toast(t)

    def _render_vacation(self):
        _clear(self.vac_box, 2)
        self.vac_card._title.set_label(i18n.tr("Ferieplanlegger") + f" {self.year}")
        for name, took, a, b, length in K.vacation_tips(self.year):
            row = Gtk.Button()
            row.add_css_class("flat")
            h = Gtk.Box(spacing=8)
            h.append(Gtk.Label(label=f"{name}", xalign=0, width_chars=14, ellipsize=3))
            h.append(Gtk.Label(label=f"{took} {'dag' if took == 1 else 'dager'} fri → {length} dager", xalign=0,
                               hexpand=True))
            dl = Gtk.Label(label=f"{a.day}.{a.month}–{b.day}.{b.month}")
            dl.add_css_class("dim-label")
            h.append(dl)
            row.set_child(h)
            row.connect("clicked", lambda _b, aa=a: self._goto(aa))
            self.vac_box.append(row)

    def _render_week(self):
        mon = self.sel - dt.timedelta(days=self.sel.weekday())
        wkn = mon.isocalendar()[1]
        self.wtitle.set_label(f"Uke {wkn} ({'partall' if wkn % 2 == 0 else 'oddetall'}) · {mon.day}. "
                              f"{MONTHS[mon.month - 1][:3]} – "
                              f"{(mon + dt.timedelta(days=6)).day}. {MONTHS[(mon + dt.timedelta(days=6)).month - 1][:3]}"
                              f" {mon.year}")
        if not all((mon + dt.timedelta(days=i)) in self._items or True for i in range(7)):
            pass
        _clear(self.week_box)
        for i in range(7):
            d = mon + dt.timedelta(days=i)
            c, inner = _card(f"{WD_LONG[i].capitalize()} {d.day}. {MONTHS[d.month - 1]}")
            if H.is_red(d):
                c._title.add_css_class("ks-cal-red")
            for x in self._items.get(d, []):
                if x.get("kind") == "moon" and not x.get("title"):
                    continue
                lab = Gtk.Label(xalign=0, wrap=True)
                lab.set_markup(f'<span foreground="{x.get("color") or "#888"}">●</span> '
                               f'{GLib.markup_escape_text(x["icon"] + " " + x["title"])}'
                               + (f'  <span alpha="60%">{x["time"]}</span>' if x.get("time") else ""))
                inner.append(lab)
            if not self._items.get(d):
                inner.append(_dim("–"))
            add = Gtk.Button(label="＋", halign=Gtk.Align.START, tooltip_text=i18n.tr("Legg til"))
            add.add_css_class("flat")
            add.connect("clicked", lambda _b, dd=d: self._edit_event(None, dd))
            inner.append(add)
            self.week_box.append(c)
        if any((mon + dt.timedelta(days=i)) not in self._items for i in range(7)) and \
                not getattr(self, "_wk_loading", False):
            self._wk_loading = True
            _bg(lambda: K.items(mon, mon + dt.timedelta(days=6)),
                lambda it: (setattr(self, "_wk_loading", False), not isinstance(it, Exception) and
                            (self._items.update(it), self._render_week())))

    def _render_year(self):
        y = self.year
        self.ytitle.set_label(str(y))
        self.ystats.set_label(f"{K.workdays(y)} arbeidsdager · {len(H.red_days(y))} røde dager (utenom søndager) · "
                              f"{sum(1 for d, _n in H.long_weekends(y))} langhelger")
        _clear(self.year_flow)
        today = dt.date.today()
        for m in range(1, 13):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            box.add_css_class("ks-year-month")
            t = Gtk.Button(label=MONTHS[m - 1].capitalize())
            t.add_css_class("flat")
            t.add_css_class("heading")
            t.connect("clicked", lambda _b, mm=m: (self._set_ym(y, mm), self.views.set_visible_child_name("maned")))
            box.append(t)
            g = Gtk.Grid(column_spacing=1, row_spacing=1, halign=Gtk.Align.CENTER)
            for r, week in enumerate(calendar.Calendar(0).monthdatescalendar(y, m)):
                for c, d in enumerate(week):
                    if d.month != m:
                        g.attach(Gtk.Label(label=""), c, r, 1, 1)
                        continue
                    b = Gtk.Button(label=str(d.day))
                    b.add_css_class("flat")
                    b.add_css_class("ks-year-day")
                    if H.is_red(d):
                        b.add_css_class("ks-cal-red")
                    if d in H.red_days(y):
                        b.add_css_class("holiday")
                        b.set_tooltip_text(H.red_days(y)[d])
                    if d == today:
                        b.add_css_class("today")
                    if any(x.get("src") == "egen" for x in self._items.get(d, [])):
                        b.set_label(f"{d.day}•")
                    b.connect("clicked", lambda _b, dd=d: (self._goto(dd), self.views.set_visible_child_name("maned")))
                    g.attach(b, c, r, 1, 1)
            box.append(g)
            self.year_flow.append(box)

    # ================= hendelser
    def _edit_event(self, eid, day):
        ev = next((e for e in K.load()["events"] if e.get("id") == eid), None) if eid else None
        dlg = Adw.AlertDialog(heading=i18n.tr("Endre hendelse") if ev else i18n.tr("Ny hendelse"))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        title = Gtk.Entry(text=(ev or {}).get("title", ""), placeholder_text=i18n.tr("Hva skjer? f.eks. Tannlege"))
        box.append(title)
        kinds = list(K.KINDS)
        kd = Gtk.DropDown.new_from_strings([f"{v[0]} {i18n.tr(v[1])}" for v in K.KINDS.values()])
        kd.set_selected(kinds.index((ev or {}).get("kind", "event")) if (ev or {}).get("kind", "event") in kinds else 0)
        box.append(kd)
        # dato: kalender i en sprettboks (ingen skriving av datoformat)
        try:
            d0 = dt.date.fromisoformat((ev or {}).get("date") or day.isoformat())
        except ValueError:
            d0 = day
        sel_date = {"v": d0}
        date_btn = Gtk.MenuButton(label=f"📅 {d0.day}. {MONTHS[d0.month - 1]} {d0.year}")
        calw = Gtk.Calendar()
        calw.select_day(GLib.DateTime.new_local(d0.year, d0.month, d0.day, 0, 0, 0))
        pop = Gtk.Popover(child=calw)
        date_btn.set_popover(pop)

        def picked(c):
            g = c.get_date()
            sel_date["v"] = dt.date(g.get_year(), g.get_month(), g.get_day_of_month())
            v = sel_date["v"]
            date_btn.set_label(f"📅 {v.day}. {MONTHS[v.month - 1]} {v.year}")
            pop.popdown()
        calw.connect("day-selected", picked)
        r1 = Gtk.Box(spacing=8)
        r1.append(date_btn)
        # klokkeslett: hele dagen eller timer/minutter
        t0 = (ev or {}).get("time") or ""
        allday = Gtk.CheckButton(label=i18n.tr("Hele dagen"), active=not t0)
        r1.append(allday)
        hh = Gtk.SpinButton.new_with_range(0, 23, 1)
        mm = Gtk.SpinButton.new_with_range(0, 55, 5)
        hh.set_value(int(t0.split(":")[0]) if t0 else 18)
        mm.set_value(int(t0.split(":")[1]) if t0 else 0)
        for w in (hh, mm):
            w.set_wrap(True)
            w.set_orientation(Gtk.Orientation.VERTICAL)
            w.connect("output", lambda s_: (s_.set_text(f"{int(s_.get_value()):02d}"), True)[1])
        tbox = Gtk.Box(spacing=2)
        tbox.append(Gtk.Label(label=i18n.tr("kl.")))
        tbox.append(hh)
        tbox.append(Gtk.Label(label=":"))
        tbox.append(mm)
        tbox.set_sensitive(not allday.get_active())
        allday.connect("toggled", lambda w: tbox.set_sensitive(not w.get_active()))
        r1.append(tbox)
        box.append(r1)
        end_v = {"v": (ev or {}).get("end", "")}
        rd = Gtk.DropDown.new_from_strings([i18n.tr(n) for _k, n in REPEATS])
        rk = [k for k, _n in REPEATS]
        rd.set_selected(rk.index((ev or {}).get("repeat", "")) if (ev or {}).get("repeat", "") in rk else 0)
        box.append(rd)
        md = Gtk.DropDown.new_from_strings([i18n.tr(n) for _k, n in REMINDS])
        mk = [k for k, _n in REMINDS]
        cur_r = (ev or {}).get("remind", 30)
        md.set_selected(mk.index(cur_r) if cur_r in mk else 3)
        box.append(md)
        cr = Gtk.Box(spacing=4)
        color = {"v": (ev or {}).get("color") or K.COLORS[0]}
        cbtns = []
        for c in K.COLORS:
            b = Gtk.ToggleButton(active=c == color["v"])
            b.set_size_request(26, 26)
            prov = Gtk.CssProvider()
            prov.load_from_data(f"button {{ background: {c}; border-radius: 99px; min-width: 22px; "
                                f"min-height: 22px; }} button:checked {{ box-shadow: 0 0 0 3px white; }}".encode())
            b.get_style_context().add_provider(prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 9)
            if cbtns:
                b.set_group(cbtns[0])
            cbtns.append(b)
            b.connect("toggled", lambda w, cc=c: w.get_active() and color.update(v=cc))
            cr.append(b)
        box.append(cr)
        scene_dd = None
        try:
            import scenes
            sc = scenes.load() if hasattr(scenes, "load") else []
            names = [(s.get("id"), s.get("name")) for s in (sc if isinstance(sc, list) else sc.get("scenes", []))]
        except Exception:  # noqa: BLE001
            names = []
        if names:
            scene_dd = Gtk.DropDown.new_from_strings([i18n.tr("Ingen scene")] + [n for _i, n in names])
            cur = (ev or {}).get("scene", "")
            ids = [i for i, _n in names]
            scene_dd.set_selected(ids.index(cur) + 1 if cur in ids else 0)
            scene_dd.set_tooltip_text(i18n.tr("Kjør en Smart Hjem-scene på dette tidspunktet"))
            box.append(scene_dd)
        note = Gtk.Entry(text=(ev or {}).get("note", ""), placeholder_text=i18n.tr("Notat (valgfritt)"))
        box.append(note)
        st = _dim(i18n.tr("Lagres på NAS-en – alle i huset ser det."))
        box.append(st)
        dlg.set_extra_child(box)
        dlg.add_response("cancel", i18n.tr("Avbryt"))
        if ev:
            dlg.add_response("del", i18n.tr("Slett"))
            dlg.set_response_appearance("del", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.add_response("ok", i18n.tr("Lagre"))
        dlg.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)

        def resp(_d, r):
            if r == "del":
                _bg(lambda: K.remove(eid), lambda _r: self._load())
            elif r == "ok":
                kind = kinds[kd.get_selected()]
                sid = names[scene_dd.get_selected() - 1][0] if scene_dd and scene_dd.get_selected() > 0 else ""
                data = {"id": eid, "title": title.get_text(), "date": sel_date["v"].isoformat(),
                        "time": "" if allday.get_active() else f"{int(hh.get_value()):02d}:{int(mm.get_value()):02d}",
                        "end": end_v["v"], "repeat": rk[rd.get_selected()],
                        "remind": mk[md.get_selected()], "color": color["v"], "kind": "scene" if sid else kind,
                        "scene": sid, "note": note.get_text(), "done": (ev or {}).get("done")}

                def save():
                    return K.add(data)

                def done(res):
                    if isinstance(res, Exception):
                        self._toast(f"✗ {res}")
                        return
                    self._load()
                _bg(save, done)
        dlg.connect("response", resp)
        dlg.present(self.get_root())

    # ================= søk, innstillinger, utskrift
    def _do_search(self, q):
        hits = K.search(q)
        dlg = Adw.AlertDialog(heading=f"«{q}»", body=i18n.tr("Ingen treff") if not hits else "")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for d, tm, t in hits[:40]:
            b = Gtk.Button(label=f"{d.day}. {MONTHS[d.month - 1]} {d.year}  ·  {t}" + (f"  {tm}" if tm else ""))
            b.add_css_class("flat")
            b.get_child().set_xalign(0)
            b.connect("clicked", lambda _b, dd=d: (dlg.close(), self._goto(dd),
                                                   self.views.set_visible_child_name("maned")))
            box.append(b)
        sc = Gtk.ScrolledWindow(child=box, propagate_natural_height=True, max_content_height=420)
        dlg.set_extra_child(sc)
        dlg.add_response("close", i18n.tr("Lukk"))
        dlg.present(self.get_root())

    def _settings(self):
        c = K.cfg()
        dlg = Adw.AlertDialog(heading=i18n.tr("Kalender"),
                              body=i18n.tr("Vinter- og høstferie varierer fra kommune til kommune – sett ukene "
                                           "som gjelder hos dere."))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        r = Gtk.Box(spacing=8)
        r.append(Gtk.Label(label=i18n.tr("Vinterferie uke"), hexpand=True, xalign=0))
        vw = Gtk.SpinButton.new_with_range(5, 12, 1)
        vw.set_value(int(c["vinter_uke"]))
        r.append(vw)
        box.append(r)
        r2 = Gtk.Box(spacing=8)
        r2.append(Gtk.Label(label=i18n.tr("Høstferie uke"), hexpand=True, xalign=0))
        hw = Gtk.SpinButton.new_with_range(36, 45, 1)
        hw.set_value(int(c["host_uke"]))
        r2.append(hw)
        box.append(r2)
        shows = {}
        for key, label in (("flagg", "🇳🇴 Flaggdager"), ("ferie", "🎒 Skoleferier"), ("mane", "🌕 Fullmåne og nymåne"),
                           ("familie", "🎂 Bursdager fra Familie"), ("ukeplan", "🗓️ Ukeplanen fra Familie"),
                           ("spill", "🎮 Spill (WoW-reset, gratis spill, salg, spilletid)"),
                           ("pc", "🖥️ PC-en (dagbok, oppgaver, strøm og temperatur)"),
                           ("ics", "📆 Google/Outlook-kalender (fra Oversikt-flisen)")):
            cb = Gtk.CheckButton(label=i18n.tr(label), active=bool(c["show"].get(key, True)))
            shows[key] = cb
            box.append(cb)
        cd = Gtk.CheckButton(label=i18n.tr("⏳ Nedtelling til neste store dag på Oversikt"),
                             active=bool(c.get("countdown", True)))
        box.append(cd)
        dlg.set_extra_child(box)
        dlg.add_response("cancel", i18n.tr("Avbryt"))
        dlg.add_response("ok", i18n.tr("Lagre"))
        dlg.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
        dlg.connect("response", lambda _d, rr: rr == "ok" and (
            K.set_cfg(vinter_uke=int(vw.get_value()), host_uke=int(hw.get_value()), countdown=cd.get_active(),
                      show={k: w.get_active() for k, w in shows.items()}), self._load()))
        dlg.present(self.get_root())

    def _print(self):
        """Årskalender (eller måneden) som PDF – til kjøleskapet."""
        fd = Gtk.FileDialog(title=i18n.tr("Lagre kalenderen som PDF"), initial_name=f"Kalender {self.year}.pdf")

        def done(d, res):
            try:
                f = d.save_finish(res)
            except GLib.Error:
                return
            if f and f.get_path():
                _bg(lambda: write_pdf(f.get_path(), self.year), lambda r: (
                    isinstance(r, Exception) or Gtk.FileLauncher.new(Gio.File.new_for_path(f.get_path())).launch(
                        self.get_root(), None, None)))
        fd.save(self.get_root(), None, done)


def write_pdf(path, year):
    """A4 liggende: hele året med røde dager, ukenummer og egne hendelser (prikk)."""
    import cairo
    w, h = 842, 595
    surf = cairo.PDFSurface(path, w, h)
    cr = cairo.Context(surf)
    cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    cr.set_font_size(22)
    cr.move_to(30, 40)
    cr.show_text(f"Kalender {year}")
    own = K.items(dt.date(year, 1, 1), dt.date(year, 12, 31), extra=False)
    cw, ch = (w - 60) / 4, (h - 70) / 3
    for m in range(1, 13):
        x0 = 30 + ((m - 1) % 4) * cw
        y0 = 60 + ((m - 1) // 4) * ch
        cr.set_source_rgb(0.1, 0.1, 0.15)
        cr.set_font_size(12)
        cr.move_to(x0, y0 + 14)
        cr.show_text(MONTHS[m - 1].capitalize())
        cr.set_font_size(7)
        for i, wd in enumerate(["uke"] + WD):
            cr.set_source_rgb(0.85, 0.2, 0.2) if wd == "søn" else cr.set_source_rgb(0.4, 0.4, 0.45)
            cr.move_to(x0 + i * (cw - 10) / 8, y0 + 28)
            cr.show_text(wd)
        for r, week in enumerate(calendar.Calendar(0).monthdatescalendar(year, m)):
            yy = y0 + 42 + r * 13
            cr.set_source_rgb(0.6, 0.6, 0.65)
            cr.move_to(x0, yy)
            cr.show_text(str(week[0].isocalendar()[1]))
            for c, d in enumerate(week, start=1):
                if d.month != m:
                    continue
                xx = x0 + c * (cw - 10) / 8
                if d in H.red_days(year):
                    cr.set_source_rgba(1, 0.3, 0.3, 0.18)
                    cr.rectangle(xx - 2, yy - 8, 15, 11)
                    cr.fill()
                cr.set_source_rgb(0.85, 0.15, 0.15) if H.is_red(d) else cr.set_source_rgb(0.1, 0.1, 0.15)
                cr.move_to(xx, yy)
                cr.show_text(str(d.day))
                if any(x.get("src") in ("egen", "familie") for x in own.get(d, [])):
                    cr.set_source_rgb(0.36, 0.55, 1)
                    cr.arc(xx + 13, yy - 6, 1.6, 0, 6.3)
                    cr.fill()
    cr.set_font_size(8)
    cr.set_source_rgb(0.4, 0.4, 0.45)
    reds = " · ".join(f"{d.day}.{d.month} {n}" for d, n in H.red_days(year).items())
    cr.move_to(30, h - 12)
    cr.show_text("Røde dager: " + reds[:230])
    surf.finish()
    return path
