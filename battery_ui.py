"""Kortet «Batterier»: prosent for mus, tastatur, hodesett og andre trådløse enheter (Oversikt og Logitech)."""
import threading

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

import batteries as B  # noqa: E402
import i18n  # noqa: E402


class BatteryCard(Gtk.Box):
    def __init__(self, logitech_only=False, title="Batterier"):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("card")
        self.logitech_only = logitech_only
        i = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for side, v in (("top", 12), ("bottom", 12), ("start", 16), ("end", 16)):
            getattr(i, f"set_margin_{side}")(v)
        self.append(i)
        t = Gtk.Label(label=i18n.tr(title), xalign=0)
        t.add_css_class("heading")
        i.append(t)
        self.rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        i.append(self.rows)
        self.hint = Gtk.Box(spacing=8)
        lab = Gtk.Label(label=i18n.tr("Hodesett vises når HeadsetControl er installert."), xalign=0, hexpand=True,
                        wrap=True)
        lab.add_css_class("dim-label")
        self.hint.append(lab)
        self.inst = Gtk.Button(label=i18n.tr("Installer"), valign=Gtk.Align.CENTER)
        self.inst.connect("clicked", self._install)
        self.hint.append(self.inst)
        i.append(self.hint)
        self.msg = Gtk.Label(xalign=0, wrap=True, visible=False)
        self.msg.add_css_class("dim-label")
        i.append(self.msg)
        self._sig = None
        threading.Thread(target=lambda: (B.devices(), GLib.idle_add(self.refresh)), daemon=True).start()
        GLib.timeout_add_seconds(30, lambda: self.refresh() or True)

    def refresh(self):
        ds = [d for d in B.cached() if d.get("logitech") or not self.logitech_only or d["kind"] == "headset"]
        self.hint.set_visible(not B.headsetcontrol_bin() and not any(d["kind"] == "headset" for d in ds))
        sig = [(d["name"], d.get("pct"), d.get("charging")) for d in ds]
        if sig == self._sig:
            return False
        self._sig = sig
        while (c := self.rows.get_first_child()) is not None:
            self.rows.remove(c)
        if not ds:
            lab = Gtk.Label(label=i18n.tr("Ingen trådløse enheter med batteri funnet (av eller i dvale?)"), xalign=0,
                            wrap=True)
            lab.add_css_class("dim-label")
            self.rows.append(lab)
        for d in ds:
            r = Gtk.Box(spacing=10)
            r.append(Gtk.Label(label=B.ICON.get(d["kind"], "🔋")))
            r.append(Gtk.Label(label=d["name"], xalign=0, hexpand=True, ellipsize=3))
            bar = Gtk.LevelBar(min_value=0, max_value=100, valign=Gtk.Align.CENTER)
            bar.set_size_request(110, 8)
            bar.add_offset_value("low", 20)
            bar.add_offset_value("high", 50)
            bar.set_value(d["pct"] or 0)
            bar.set_sensitive(d.get("pct") is not None)
            r.append(bar)
            v = Gtk.Label(label=i18n.tr(B.label(d)), width_chars=8, xalign=1)
            if d.get("pct") is not None and d["pct"] <= 20 and not d.get("charging"):
                v.add_css_class("error")
            r.append(v)
            self.rows.append(r)
        return False

    def _install(self, _b):
        self.inst.set_sensitive(False)
        self.msg.set_visible(True)
        self.msg.set_label(i18n.tr("Installerer HeadsetControl (kan ta noen minutter, spør om passord) …"))

        def work():
            ok, txt = B.install_headsetcontrol()
            GLib.idle_add(lambda: (self.msg.set_label(i18n.tr(txt)), self.inst.set_sensitive(not ok),
                                   self.refresh(), False)[3])
        threading.Thread(target=work, daemon=True).start()
