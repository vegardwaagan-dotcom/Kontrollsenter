"""Kortene for hjem-runde 5 på Familie-siden: Middagsplan, Pakker, Beskjed til alle, Søvnrapport og Minnevegg."""
import datetime as dt
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

import hjem5 as H  # noqa: E402
import i18n  # noqa: E402

_t = i18n.tr


def _bg(work, done):
    def run():
        try:
            r = work()
        except Exception as e:  # noqa: BLE001
            r = e
        GLib.idle_add(lambda: (done(r), False)[1])
    threading.Thread(target=run, daemon=True).start()


def _dim(t=""):
    lb = Gtk.Label(label=t, xalign=0, wrap=True)
    lb.add_css_class("dim-label")
    return lb


def _clear(b):
    while (c := b.get_first_child()) is not None:
        b.remove(c)


def _toast(w, text):
    r = w.get_root()
    if hasattr(r, "toast"):
        r.toast(str(text))


# ------------------------------------------------------------------ middagsplan
def meals_card(card):
    c, i = card(_t("Middagsplan"), _t("Hva blir det til middag denne uka? Vises i kalenderen hos alle. Skriv "
                                     "ingrediensene én gang – de huskes til neste gang du lager retten."))
    grid = Gtk.Grid(column_spacing=8, row_spacing=6)
    i.append(grid)
    msg = _dim()

    def show(week):
        _clear(grid)
        if isinstance(week, Exception):
            msg.set_label(f"✗ {week}")
            return
        for n, m in enumerate(week):
            d = dt.date.fromisoformat(m["day"])
            lab = Gtk.Label(label=f"{_t(m['wd'])} {d.day}.{d.month}", xalign=0)
            if n == 0:
                lab.add_css_class("heading")
            grid.attach(lab, 0, n, 1, 1)
            e = Gtk.Entry(text=m["dish"], placeholder_text=_t("Rett"), hexpand=True)
            ing = Gtk.Entry(text=m["ing"], placeholder_text=_t("Ingredienser, med komma"), hexpand=True)

            last = {"v": (m["dish"], m["ing"])}

            def save(*_a, day=m["day"], e=e, ing=ing, last=last):
                dish, ii = e.get_text(), ing.get_text()
                if (dish, ii) == last["v"]:                  # ingenting endret – ikke skriv til NAS-en
                    return
                last["v"] = (dish, ii)
                _bg(lambda: H.set_meal(day, dish, ii), lambda r: msg.set_label(f"✗ {r}") if isinstance(r, Exception)
                    else msg.set_label(_t("Lagret ✓")))
            for w in (e, ing):
                w.connect("activate", save)
                fc = Gtk.EventControllerFocus()
                fc.connect("leave", save)
                w.add_controller(fc)
            grid.attach(e, 1, n, 1, 1)
            grid.attach(ing, 2, n, 1, 1)
    row = Gtk.Box(spacing=8)
    sug = Gtk.Button(label=_t("🎲 Forslag"))

    def suggest(*_):
        f = H.suggest()
        if f:
            msg.set_label(_t(f"Hva med {f['dish']}? Skriv det inn på en dag."))
    sug.connect("clicked", suggest)
    row.append(sug)
    shop = Gtk.Button(label=_t("🛒 Ukas ingredienser til handlelista"))
    shop.connect("clicked", lambda *_: _bg(H.menu_to_shop, lambda r: msg.set_label(str(r))))
    row.append(shop)
    i.append(row)
    i.append(msg)
    _bg(H.week_menu, show)
    return c


# ------------------------------------------------------------------ pakker
def packages_card(card):
    c, i = card(_t("Pakker"), _t("Lim inn sporingsnummeret – Kontrollsenter kjenner igjen Posten/Bring, PostNord, "
                                "UPS og DHL og åpner riktig sporingsside. Forventet levering havner i kalenderen."))
    form = Gtk.Box(spacing=6)
    nr = Gtk.Entry(placeholder_text=_t("Sporingsnummer"), hexpand=True)
    name = Gtk.Entry(placeholder_text=_t("Hva er det? (valgfritt)"))
    eta = Gtk.Entry(placeholder_text=_t("Kommer (2026-11-30)"), width_chars=12)
    add = Gtk.Button(label=_t("Legg til"))
    for w in (nr, name, eta, add):
        form.append(w)
    i.append(form)
    lst = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    i.append(lst)

    def show(items):
        _clear(lst)
        if isinstance(items, Exception):
            lst.append(_dim(str(items)))
            return
        if not items:
            lst.append(_dim(_t("Ingen pakker på vei.")))
        for p in sorted(items, key=lambda x: (x.get("done"), x.get("eta") or "9")):
            row = Gtk.Box(spacing=8)
            row.append(Gtk.Label(label=("✅ " if p.get("done") else "📦 ") + f"{p['name']} · {p['carrier']}" +
                                 (f" · {p['eta'][8:]}.{p['eta'][5:7]}" if p.get("eta") else ""),
                                 xalign=0, hexpand=True, wrap=True))
            row.append(Gtk.LinkButton(uri=p["url"], label=_t("Spor →")))
            b = Gtk.Button(label=_t("Fjern") if p.get("done") else _t("Hentet"))
            b.connect("clicked", lambda _b, n=p["nr"], d=p.get("done"): _bg(lambda: H.done_package(n, remove=d),
                                                                             lambda r: refresh()))
            row.append(b)
            lst.append(row)

    def refresh():
        _bg(H.packages, show)

    def do_add(*_):
        a, b, e = nr.get_text(), name.get_text(), eta.get_text().strip()

        def done(r):
            _toast(c, r if not isinstance(r, Exception) else f"✗ {r}")
            if not isinstance(r, Exception):
                for w in (nr, name, eta):
                    w.set_text("")
            refresh()
        _bg(lambda: H.add_package(a, b, e), done)
    add.connect("clicked", do_add)
    nr.connect("activate", do_add)
    refresh()
    return c


# ------------------------------------------------------------------ beskjed til alle
def broadcast_card(card):
    c, i = card(_t("Beskjed til alle"), _t("Vises på alle PC-ene i huset (over spillet, med lyd), på telefonene og "
                                          "på TV-en."))
    row = Gtk.Box(spacing=8)
    e = Gtk.Entry(placeholder_text=_t("Skriv en beskjed …"), hexpand=True)
    send = Gtk.Button(label=_t("📢 Send"))
    send.add_css_class("suggested-action")
    row.append(e)
    row.append(send)
    i.append(row)
    quick = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=4, column_spacing=6)
    for q in ("Kom ned nå", "Middag om 5 min", "Legg dere nå 😴", "Vi drar om 10 min"):
        b = Gtk.Button(label=_t(q))
        b.connect("clicked", lambda _b, t=q: go(t))
        quick.append(b)
    i.append(quick)

    def go(text):
        _bg(lambda: H.broadcast(text, _t("PC-en")), lambda r: _toast(c, r if not isinstance(r, Exception)
                                                                     else f"✗ {r}"))
        e.set_text("")
    send.connect("clicked", lambda *_: go(e.get_text()))
    e.connect("activate", lambda *_: go(e.get_text()))
    return c


# ------------------------------------------------------------------ søvnrapport + TV av ved leggetid
def sleep_card(card):
    c, i = card(_t("Søvnrapport"), _t("Når PC-ene i huset sist var på hver kveld, sammenlignet med leggetiden. "
                                     "Rødt = etter leggetid."))
    grid = Gtk.Grid(column_spacing=14, row_spacing=4)
    i.append(grid)

    def show(r):
        _clear(grid)
        if isinstance(r, Exception) or not r["rows"]:
            grid.attach(_dim(_t("Ingen kvelder logget ennå – kommer etter første kveld.")), 0, 0, 1, 1)
            return
        for col, d in enumerate(r["days"], 1):
            wd = ["Man", "Tir", "Ons", "Tor", "Fre", "Lør", "Søn"][dt.date.fromisoformat(d).weekday()]
            lb = Gtk.Label(label=_t(wd))
            lb.add_css_class("dim-label")
            grid.attach(lb, col, 0, 1, 1)
        for n, row in enumerate(r["rows"], 1):
            grid.attach(Gtk.Label(label=row["pc"], xalign=0), 0, n, 1, 1)
            for col, x in enumerate(row["nights"], 1):
                lb = Gtk.Label(label=x["off"] or "–")
                if x["over"] and x["over"] > 0:
                    lb.add_css_class("error")
                    lb.set_tooltip_text(_t(f"{x['over']} min etter leggetid"))
                grid.attach(lb, col, n, 1, 1)
            grid.attach(_dim(_t(f"{row['late_n']} sene kvelder") if row["late_n"] else "✓"), len(r["days"]) + 1, n,
                        1, 1)
    _bg(H.sleep_report, show)
    tv = Gtk.Box(spacing=12)
    col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
    col.append(Gtk.Label(label=_t("Slå av TV-en ved leggetid"), xalign=0))
    col.append(_dim(_t("Samsung-TV-en (Smart Hjem) slås av ved leggetiden, med 10 min varsel på PC-ene først.")))
    tv.append(col)
    sw = Gtk.Switch(active=H.cfg()["tv_bedtime"], valign=Gtk.Align.CENTER)
    sw.connect("notify::active", lambda s, _p: H.set_(tv_bedtime=s.get_active()))
    tv.append(sw)
    i.append(tv)
    return c


# ------------------------------------------------------------------ minnevegg
def memories_card(card):
    c, i = card(_t("Minnevegg"), _t("Bildene fra chatten som lysbildeshow i fullskjerm – fint på TV-en eller en ekstra "
                                   "skjerm."))
    n = _dim()
    i.append(n)
    b = Gtk.Button(label=_t("🖼️ Start lysbildeshow"), halign=Gtk.Align.START)
    i.append(b)

    def show(m):
        cnt = 0 if isinstance(m, Exception) else len(m)
        n.set_label(_t(f"{cnt} bilder") if cnt else _t("Ingen bilder i chatten ennå."))
        b.set_sensitive(bool(cnt))
        b._m = m
    b.connect("clicked", lambda *_: Slideshow(getattr(b, "_m", []), c.get_root()).present())
    _bg(H.memories, show)
    return c


class Slideshow(Gtk.Window):
    def __init__(self, items, parent=None, secs=7):
        super().__init__(title=_t("Minnevegg"), decorated=False)
        if parent:
            self.set_transient_for(parent)
        self.items, self.i = items, 0
        self.pic = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN, hexpand=True, vexpand=True)
        bg = Gtk.Box()
        bg.add_css_class("ks-slideshow")
        bg.append(self.pic)
        self.set_child(bg)
        p = Gtk.CssProvider()
        p.load_from_data(b".ks-slideshow { background: black; }")
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), p, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        k = Gtk.EventControllerKey()
        k.connect("key-pressed", self._key)
        self.add_controller(k)
        cl = Gtk.GestureClick()
        cl.connect("pressed", lambda *_: self._next(1))
        self.add_controller(cl)
        self._show()
        self._tid = GLib.timeout_add_seconds(secs, lambda: (self._next(1), True)[1])
        self.connect("close-request", lambda *_: GLib.source_remove(self._tid) and False)
        self.fullscreen()

    def _key(self, _c, kv, _code, _st):
        if kv == Gdk.KEY_Escape:
            self.close()
        else:
            self._next(-1 if kv == Gdk.KEY_Left else 1)
        return True

    def _next(self, d):
        if self.items:
            self.i = (self.i + d) % len(self.items)
            self._show()

    def _show(self):
        if self.items:
            self.pic.set_filename(self.items[self.i]["path"])
