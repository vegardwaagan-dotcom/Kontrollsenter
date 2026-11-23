"""Fjernhjelp (egen side i sidemenyen): RustDesk – din ID, koble til andre, PC-ene hjemme med ett trykk, og
«Be om hjelp»."""
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

import i18n  # noqa: E402
import streaming as S  # noqa: E402


def _dim(t):
    lab = Gtk.Label(label=i18n.tr(t), xalign=0, wrap=True)
    lab.add_css_class("dim-label")
    return lab


def _card(title, desc=None):
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    outer.add_css_class("card")
    inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=16, margin_bottom=16,
                    margin_start=18, margin_end=18)
    outer.append(inner)
    t = Gtk.Label(label=i18n.tr(title), xalign=0)
    t.add_css_class("title-4")
    inner.append(t)
    if desc:
        inner.append(_dim(desc))
    return outer, inner


def _btn(label, cb, primary=False):
    b = Gtk.Button(label=i18n.tr(label), valign=Gtk.Align.CENTER)
    b.add_css_class("pill")
    if primary:
        b.add_css_class("suggested-action")
    b.connect("clicked", cb)
    return b


def _bg(fn, done):
    def work():
        try:
            r = fn()
        except Exception as e:  # noqa: BLE001
            r = e
        GLib.idle_add(lambda: (done(r), False)[1])
    threading.Thread(target=work, daemon=True).start()


class RemoteHelpPage(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(18)
        import theme
        self.set_child(Adw.Clamp(maximum_size=theme.PAGE_WIDTH, child=box))

        # ---- denne PC-en ----
        c, i = _card("Denne PC-en", "Gi ID-en til den som skal hjelpe deg. Passordet vises i RustDesk-vinduet, og du "
                                    "godtar tilkoblingen på skjermen.")
        box.append(c)
        row = Gtk.Box(spacing=12)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        col.append(_dim("RustDesk-ID"))
        self.rid = Gtk.Label(label="…", xalign=0, selectable=True)
        self.rid.add_css_class("title-1")
        self.rid.add_css_class("numeric")
        col.append(self.rid)
        row.append(col)
        cp = Gtk.Button(icon_name="edit-copy-symbolic", tooltip_text=i18n.tr("Kopier ID"), valign=Gtk.Align.CENTER)
        cp.add_css_class("circular")
        cp.connect("clicked", lambda *_: (Gdk.Display.get_default().get_clipboard().set(self.rid.get_label()),
                                          self.msg.set_label(i18n.tr("ID-en er kopiert"))))
        row.append(cp)
        self.open_b = _btn("Åpne RustDesk", lambda *_: self._do(S.rustdesk_open, "RustDesk er åpnet"))
        row.append(self.open_b)
        self.inst_b = _btn("Installer RustDesk", lambda *_: self._do(lambda: S.install("rustdesk"),
                                                                       "RustDesk er installert ✓"), True)
        row.append(self.inst_b)
        i.append(row)
        hr = Gtk.Box(spacing=8)
        self.help_t = Gtk.Entry(placeholder_text=i18n.tr("Hva trenger du hjelp med? (valgfritt)"), hexpand=True)
        hr.append(self.help_t)
        hr.append(_btn("🆘 Be om hjelp", self._help, True))
        i.append(hr)
        i.append(_dim("«Be om hjelp» sender beskjed med ID-en til de voksne hjemme (chat og mobilen) og åpner "
                      "RustDesk."))

        # ---- koble til ----
        c, i = _card("Koble til en annen PC", "Skriv ID-en den andre ser i RustDesk – eller trykk på en PC hjemme.")
        box.append(c)
        cr = Gtk.Box(spacing=8)
        self.to = Gtk.Entry(placeholder_text=i18n.tr("RustDesk-ID, f.eks. 123 456 789"), hexpand=True,
                            input_purpose=Gtk.InputPurpose.DIGITS)
        self.to.connect("activate", self._connect)
        cr.append(self.to)
        cr.append(_btn("Koble til", self._connect, True))
        i.append(cr)
        i.append(Gtk.Label(label=i18n.tr("PC-ene hjemme"), xalign=0, css_classes=["heading"], margin_top=6))
        self.pcs = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        i.append(self.pcs)

        # ---- andre programmer ----
        c, i = _card("Andre programmer for fjernstyring", "RustDesk er gratis og virker fra mobilen også. Vil du "
                                                           "heller bruke noe annet, velg det her.")
        box.append(c)
        try:
            import apps_ui
            i.append(apps_ui.need("remote", on_done=self.refresh))
            i.append(apps_ui.ranked_list("remote", on_installed=self.refresh))
        except Exception:  # noqa: BLE001
            pass

        self.msg = _dim("")
        box.append(self.msg)
        self.refresh()
        GLib.timeout_add_seconds(30, lambda: (self.get_mapped() and self.refresh(), True)[1])

    def refresh(self):
        def load():
            import homepcs
            import savegames
            me = savegames.pc_name()
            return S.rustdesk_cached(60), [p for p in homepcs.fetch() or [] if p.get("name") != me]
        _bg(load, self._show)
        return False

    def _show(self, r):
        if isinstance(r, Exception):
            self.msg.set_label(f"Feil: {r}")
            return
        rd, pcs = r
        self.rid.set_label(" ".join((rd["id"] or "")[i:i + 3] for i in range(0, len(rd["id"] or ""), 3)) if rd["id"]
                           else ("–" if rd["installed"] else i18n.tr("ikke installert")))
        self.open_b.set_visible(rd["installed"])
        self.inst_b.set_visible(not rd["installed"])
        while (c := self.pcs.get_first_child()) is not None:
            self.pcs.remove(c)
        import time
        for p in pcs:
            on = time.time() - (p.get("time") or 0) < 900
            row = Gtk.Box(spacing=8)
            row.append(Gtk.Label(label=("🟢 " if on else "⚫ ") + p.get("name", "?"), xalign=0, hexpand=True))
            rid = p.get("rustdesk_id")
            row.append(_dim(rid or ("RustDesk-ID ikke delt ennå" if on else "av")))
            if rid:
                row.append(_btn("Koble til", lambda _b, x=rid: self._do(lambda: S.rustdesk_connect(x)), on))
            self.pcs.append(row)
        if not pcs:
            self.pcs.append(_dim("Ingen andre PC-er hjemme ennå."))

    def _connect(self, *_):
        rid = self.to.get_text()
        self._do(lambda: S.rustdesk_connect(rid))

    def _help(self, *_):
        import homeplus
        t = self.help_t.get_text().strip()
        self._do(lambda: homeplus.ask_help(t))

    def _do(self, fn, ok=None):
        self.msg.set_label(i18n.tr("Arbeider …"))
        _bg(fn, lambda r: (self.msg.set_label(("✗ " + str(r)) if isinstance(r, Exception) else (ok or str(r or "OK"))),
                           GLib.timeout_add_seconds(2, self.refresh)))
