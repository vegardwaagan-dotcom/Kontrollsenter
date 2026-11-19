"""Huset-kortet: oppdateringskveld, strømsparing etter pris, glemte PC-er, sovemodus, testmodus og strøm per PC."""
import threading

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

import house as H  # noqa: E402
import i18n  # noqa: E402

DAYS = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"]


def _dim(t):
    lab = Gtk.Label(label=i18n.tr(t), xalign=0, wrap=True)
    lab.add_css_class("dim-label")
    lab.add_css_class("caption")
    return lab


def _switch(box, title, sub, active, cb):
    r = Gtk.Box(spacing=12)
    col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
    col.append(Gtk.Label(label=i18n.tr(title), xalign=0, wrap=True))
    if sub:
        col.append(_dim(sub))
    r.append(col)
    sw = Gtk.Switch(active=active, valign=Gtk.Align.CENTER)
    sw.connect("notify::active", lambda w, _p: cb(w.get_active()))
    r.append(sw)
    box.append(r)
    return r


def _time_entry(value, cb, placeholder="23:30"):
    e = Gtk.Entry(text=value or "", placeholder_text=placeholder, width_chars=6, max_width_chars=6,
                  valign=Gtk.Align.CENTER)

    def done(*_):
        t = e.get_text().strip()
        if t == "" or (len(t) == 5 and t[2] == ":" and t[:2].isdigit() and t[3:].isdigit()):
            e.remove_css_class("error")
            cb(t)
        else:
            e.add_css_class("error")
    e.connect("activate", done)
    fc = Gtk.EventControllerFocus()
    fc.connect("leave", done)
    e.add_controller(fc)
    return e


def _row(box, label, widget):
    r = Gtk.Box(spacing=10, margin_start=16)
    r.append(Gtk.Label(label=i18n.tr(label), xalign=0, hexpand=True))
    r.append(widget)
    box.append(r)
    return r


def house_card(win_getter):
    c = H.cfg()
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box.append(_dim("Slå på her på én PC – den vekker, oppdaterer og legger de andre i dvale via hjemmenettet."))

    # 3 – oppdateringskveld
    nu = c["night_update"]
    _switch(box, "Oppdateringskveld", "Én natt i uka: PC-ene som er av vekkes (Wake-on-LAN), «Oppdater alt» kjøres "
                                      "på alle, de vekte går i dvale igjen, og du får rapport på mobilen.",
            nu["on"], lambda on: H.set_part("night_update", on=on))
    dd = Gtk.DropDown.new_from_strings([i18n.tr(d) for d in DAYS])
    dd.set_selected(nu["weekday"])
    dd.connect("notify::selected", lambda d, _p: H.set_part("night_update", weekday=d.get_selected()))
    _row(box, "Dag", dd)
    at = Gtk.DropDown.new_from_strings([i18n.tr("Billigste strømtime"), "01:00", "03:00", "05:00"])
    opts = ["cheap", "01:00", "03:00", "05:00"]
    at.set_selected(opts.index(nu["at"]) if nu["at"] in opts else 0)
    at.connect("notify::selected", lambda d, _p: H.set_part("night_update", at=opts[d.get_selected()]))
    _row(box, "Når", at)
    run = Gtk.Button(label=i18n.tr("Kjør nå"))
    run.add_css_class("pill")
    msg = _dim("")

    def go(_b):
        run.set_sensitive(False)
        msg.set_label(i18n.tr("Vekker og oppdaterer … (kan ta en stund)"))

        def work():
            txt = H.run_night_update(win_getter(), report=False)
            GLib.idle_add(lambda: (msg.set_label(txt), run.set_sensitive(True), False)[2])
        threading.Thread(target=work, daemon=True).start()
    run.connect("clicked", go)
    _row(box, "Prøv oppdateringskvelden nå", run)
    box.append(msg)
    box.append(Gtk.Separator())

    # 27 – strømsparing etter pris
    _switch(box, "Strømsparing når strømmen er dyr", "Er prisen 25 % over dagens snitt og PC-en står ubrukt, går den "
                                                     "i Strømsparing – tilbake når prisen faller eller du bruker den.",
            c["price_saver"]["on"], lambda on: H.set_part("price_saver", on=on))
    # 29 – glemte PC-er
    fg = c["forgotten"]
    _switch(box, "Glemte PC-er om natten", f"Står en PC på uten å brukes i {fg['idle_min']} min mellom {fg['from']} og "
                                           f"{fg['to']}, får du beskjed – eller den legges i dvale.",
            fg["on"], lambda on: H.set_part("forgotten", on=on))
    md = Gtk.DropDown.new_from_strings([i18n.tr("Spør meg"), i18n.tr("Legg i dvale automatisk")])
    md.set_selected(1 if fg["mode"] == "auto" else 0)
    md.connect("notify::selected", lambda d, _p: H.set_part("forgotten", mode="auto" if d.get_selected() else "ask"))
    _row(box, "Hva skal skje", md)
    # 39 – sovemodus
    hs = c["house_sleep"]
    _switch(box, "Sovemodus for huset", "Ved leggetid får alle 10 minutters varsel, og så går alle PC-ene i dvale.",
            hs["on"], lambda on: H.set_part("house_sleep", on=on))
    _row(box, "Leggetid", _time_entry(hs["at"], lambda t: H.set_part("house_sleep", at=t or "23:30")))
    _row(box, "Vekk PC-ene igjen kl. (tom = nei)", _time_entry(hs.get("wake_at"), lambda t: H.set_part(
        "house_sleep", wake_at=t), "07:00"))
    box.append(Gtk.Separator())

    # 72 – testmodus
    pl = c["pilot"]
    _switch(box, "Testmodus for nye versjoner", "Nye versjoner av Kontrollsenter prøves først på én PC i 24 timer. "
                                                "Rulles den tilbake der, får de andre den aldri.",
            pl["on"], lambda on: H.set_part("pilot", on=on))
    names = [""]
    try:
        import homepcs
        names += [p["name"] for p in homepcs.fetch() or []]
    except Exception:  # noqa: BLE001
        pass
    if pl["pc"] and pl["pc"] not in names:
        names.append(pl["pc"])
    pd = Gtk.DropDown.new_from_strings([n or i18n.tr("(velg PC)") for n in names])
    pd.set_selected(names.index(pl["pc"]) if pl["pc"] in names else 0)
    pd.connect("notify::selected", lambda d, _p: H.set_part("pilot", pc=names[d.get_selected()]))
    _row(box, "Test-PC", pd)
    box.append(Gtk.Separator())

    # 28 – strøm per PC
    h = Gtk.Label(label=i18n.tr("Strøm denne måneden"), xalign=0)
    h.add_css_class("heading")
    box.append(h)
    grid = Gtk.Grid(column_spacing=24, row_spacing=4)
    box.append(grid)

    def fill(rows):
        for i, (n, kwh, kr) in enumerate(rows):
            for j, t in enumerate((n, f"{kwh:.1f} kWh", f"{kr:.0f} kr")):
                lab = Gtk.Label(label=t, xalign=0 if j == 0 else 1)
                if j:
                    lab.add_css_class("numeric")
                grid.attach(lab, j, i, 1, 1)
        if not rows:
            grid.attach(_dim("Ingen data ennå"), 0, 0, 1, 1)
        return False
    threading.Thread(target=lambda: GLib.idle_add(fill, H.power_by_pc()), daemon=True).start()
    return box
