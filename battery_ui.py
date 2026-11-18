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
        d = Gtk.Label(label=i18n.tr("Batteriet i trådløs mus, tastatur og hodesett. Du får varsel når det blir lavt."),
                      xalign=0, wrap=True)
        d.add_css_class("ks-sub")
        i.append(d)
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
        GLib.timeout_add_seconds(5, lambda: (self.refresh() if self.get_mapped() else None) or True)
        B.listen(self.refresh)                     # med en gang en lader settes inn eller tas ut

    def refresh(self):
        ds = [d for d in B.cached() if d.get("logitech") or not self.logitech_only or d["kind"] == "headset"]
        self.hint.set_visible(not B.headsetcontrol_bin() and not any(d["kind"] == "headset" for d in ds))
        sig = [(d["name"], d.get("pct"), d.get("charging"), d.get("full")) for d in ds]
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
            bar.set_value(d["pct"] if d.get("pct") is not None else (100 if d.get("full") else 0))
            bar.set_sensitive(d.get("pct") is not None or d.get("charging") or d.get("full"))
            r.append(bar)
            ic = Gtk.Image(icon_name=B.charge_icon(d) or "ks-charging-symbolic", valign=Gtk.Align.CENTER,
                           pixel_size=16)
            ic.set_opacity(1 if B.charge_icon(d) else 0)                 # holder av plassen så stolpene står likt
            ic.set_tooltip_text(i18n.tr("Lader" if d.get("charging") else "Fulladet"))
            r.append(ic)
            txt = B.label(d).replace("⚡ ", "").replace("🔌 ", "")      # ikonet viser lyn/støpsel
            v = Gtk.Label(label=i18n.tr(txt), width_chars=16, xalign=1)
            v.add_css_class("numeric")
            if d.get("charging") or d.get("full"):
                for w in (bar, ic, v):
                    w.add_css_class("ks-charging")
            elif d.get("pct") is not None and d["pct"] <= 20:
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
