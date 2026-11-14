"""Kortet «Mobil og nettbrett» i Hjemme-fanen: slå fjernstyring av/på, par nye enheter og fjern gamle."""
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk  # noqa: E402

import i18n  # noqa: E402
import remote  # noqa: E402


def _dim(text, wrap=True):
    lab = Gtk.Label(label=i18n.tr(text), xalign=0, wrap=wrap)
    lab.add_css_class("dim-label")
    return lab


class RemoteCard(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("card")
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side, v in (("top", 14), ("bottom", 14), ("start", 16), ("end", 16)):
            getattr(inner, f"set_margin_{side}")(v)
        self.append(inner)
        head = Gtk.Box(spacing=10)
        t = Gtk.Label(label=i18n.tr("Mobil og nettbrett"), xalign=0, hexpand=True)
        t.add_css_class("heading")
        head.append(t)
        head.append(Gtk.Label(label=i18n.tr("Tillat fjernstyring")))
        self.sw = Gtk.Switch(active=remote.load_cfg()["enabled"], valign=Gtk.Align.CENTER)
        self.sw.connect("notify::active", self._on_switch)
        head.append(self.sw)
        inner.append(head)
        inner.append(_dim("Styr PC-en og se alt fra Android-appen «Kontrollsenter» (mobil og nettbrett). Bare "
                          "enheter på hjemmenettet som er paret med en kode fra denne PC-en, får tilgang."))
        self.addr = Gtk.Label(xalign=0, selectable=True, wrap=True)
        self.addr.add_css_class("title-4")
        inner.append(self.addr)
        self.apk = _dim("")
        self.apk.set_selectable(True)
        inner.append(self.apk)
        row = Gtk.Box(spacing=8)
        self.pair_btn = Gtk.Button(label=i18n.tr("Par ny enhet"))
        self.pair_btn.add_css_class("suggested-action")
        self.pair_btn.connect("clicked", self._pair)
        row.append(self.pair_btn)
        inner.append(row)
        self.code = Gtk.Label(xalign=0, selectable=True)
        self.code.add_css_class("title-1")
        self.code.add_css_class("numeric")
        self.code.set_visible(False)
        inner.append(self.code)
        self.code_info = _dim("")
        self.code_info.set_visible(False)
        inner.append(self.code_info)
        self.msg = _dim("")
        inner.append(self.msg)
        self.lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.lb.add_css_class("boxed-list")
        inner.append(self.lb)
        self._timer = 0
        r = remote.INSTANCE
        if r:
            r.on_paired = self._paired
        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self):
        r = remote.INSTANCE
        on = bool(r and r.running)
        ips = remote.local_ips()
        if on and ips:
            self.addr.set_label("  ·  ".join(f"http://{ip}:{remote.PORT}" for ip in ips[:2]))
            self.apk.set_label(i18n.tr("Appen: åpne {} i nettleseren på mobilen/nettbrettet for å laste ned "
                                       "Kontrollsenter.apk – eller hent den fra NAS-en (Kontrollsenter → Android).")
                               .replace("{}", f"http://{ips[0]}:{remote.PORT}/app/kontrollsenter.apk"))
        else:
            self.addr.set_label(i18n.tr("Av") if not on else i18n.tr("Fant ingen adresse på hjemmenettet"))
            self.apk.set_label("")
        self.pair_btn.set_sensitive(on)
        while (ch := self.lb.get_first_child()):
            self.lb.remove(ch)
        devs = remote.load_cfg()["devices"]
        for d in devs:
            b = Gtk.Box(spacing=10)
            for side, v in (("top", 8), ("bottom", 8), ("start", 12), ("end", 8)):
                getattr(b, f"set_margin_{side}")(v)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            col.append(Gtk.Label(label="📱  " + d.get("name", "?"), xalign=0))
            last = d.get("last") or 0
            when = time.strftime("%d.%m %H:%M", time.localtime(last)) if last else i18n.tr("aldri")
            s = Gtk.Label(label=i18n.tr("Sist brukt") + f": {when}", xalign=0)
            s.add_css_class("caption")
            s.add_css_class("dim-label")
            col.append(s)
            b.append(col)
            rm = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text=i18n.tr("Fjern tilgangen"),
                            valign=Gtk.Align.CENTER)
            rm.add_css_class("flat")
            rm.connect("clicked", lambda _b, h=d.get("hash"): self._remove(h))
            b.append(rm)
            self.lb.append(b)
        self.lb.set_visible(bool(devs))

    def _on_switch(self, sw, _p):
        c = remote.load_cfg()
        c["enabled"] = sw.get_active()
        remote.save_cfg(c)
        r = remote.INSTANCE
        if r:
            if sw.get_active():
                ok, err = r.start()
                self.msg.set_label("" if ok else err)
            else:
                r.stop()
                self.msg.set_label("")
        self.refresh()

    def _pair(self, *_):
        r = remote.INSTANCE
        if not r:
            return
        code = r.new_code()
        self.code.set_label(f"{code[:3]} {code[3:]}")
        self.code.set_visible(True)
        self.code_info.set_visible(True)
        if self._timer:
            GLib.source_remove(self._timer)
        self._timer = GLib.timeout_add_seconds(1, self._tick)
        self._tick()

    def _tick(self):
        r = remote.INSTANCE
        left = int(r.code_until - time.time()) if r and r.code else 0
        if left <= 0:
            self.code.set_visible(False)
            self.code_info.set_visible(False)
            self._timer = 0
            return False
        self.code_info.set_label(i18n.tr("Skriv koden i appen. Gyldig i {} til.").replace(
            "{}", f"{left // 60}:{left % 60:02d}"))
        return True

    def _paired(self, name):
        self.code.set_visible(False)
        self.code_info.set_visible(False)
        self.msg.set_label(i18n.tr("«{}» er paret ✓").replace("{}", name))
        self.refresh()

    def _remove(self, h):
        c = remote.load_cfg()
        c["devices"] = [d for d in c["devices"] if d.get("hash") != h]
        remote.save_cfg(c)
        self.refresh()
