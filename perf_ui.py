"""Bryterne for lagring på disk og «Spar alt» – brukes i Innstillinger → Generelt og på hver ting som lagres."""
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

import i18n  # noqa: E402
import perf  # noqa: E402

_SWITCHES = {}               # nøkkel -> [brytere] (samme ting kan vises flere steder)


def _sync():
    for key, sws in _SWITCHES.items():
        for sw in list(sws):
            want = perf.disk_ok(key) if key != "_nodisk" else perf.no_disk()
            if sw.get_active() != want:
                sw._ks_sync = True
                sw.set_active(want)
                sw._ks_sync = False
            if key != "_nodisk":
                sw.set_sensitive(not perf.no_disk())


def _row(title, sub, sw):
    r = Gtk.Box(spacing=12)
    tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
    tb.append(Gtk.Label(label=i18n.tr(title), xalign=0, wrap=True))
    if sub:
        d = Gtk.Label(label=i18n.tr(sub), xalign=0, wrap=True)
        d.add_css_class("dim-label")
        d.add_css_class("caption")
        tb.append(d)
    r.append(tb)
    r.append(sw)
    return r


def disk_switch(key, compact=False):
    """«Lagre på disk» for én ting (av = verken skrives eller leses)."""
    name, desc = next(((n, d) for k, n, d in perf.DISK_ITEMS if k == key), (key, ""))
    sw = Gtk.Switch(active=perf.disk_ok(key), valign=Gtk.Align.CENTER, sensitive=not perf.no_disk())
    sw.set_tooltip_text(i18n.tr("Av: verken skrives til eller leses fra disk – bare i minnet mens Kontrollsenter kjører"))

    def toggled(w, _p):
        if getattr(w, "_ks_sync", False):
            return
        perf.set_disk(key, w.get_active())
        _sync()
    sw.connect("notify::active", toggled)
    _SWITCHES.setdefault(key, []).append(sw)
    if compact:
        return _row("Lagre på disk", None, sw)
    return _row(name, desc, sw)


def no_disk_switch():
    """Hovedbryteren: ingen lesing og skriving til disk, og oppdateringer bare manuelt."""
    sw = Gtk.Switch(active=perf.no_disk(), valign=Gtk.Align.CENTER)

    def toggled(w, _p):
        if getattr(w, "_ks_sync", False):
            return
        perf.set_no_disk(w.get_active())
        _sync()
    sw.connect("notify::active", toggled)
    _SWITCHES.setdefault("_nodisk", []).append(sw)
    return _row("Ingen lesing og skriving til disk",
                "Alt holdes bare i minnet mens Kontrollsenter kjører (historikk, strøm, spilletid, hendelser, logg …), "
                "og oppdateringer og diskopprydding gjøres bare manuelt med «Oppdater alt». Innstillingene du endrer "
                "lagres fortsatt.", sw)


def disk_card_body():
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box.append(no_disk_switch())
    box.append(Gtk.Separator())
    h = Gtk.Label(label=i18n.tr("Eller velg for hver ting:"), xalign=0)
    h.add_css_class("caption-heading")
    box.append(h)
    for key, _n, _d in perf.DISK_ITEMS:
        box.append(disk_switch(key))
    return box
