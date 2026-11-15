"""Bluetooth-fanen i Kontrollsenter – pare og koble til hodetelefoner, kontrollere, høyttalere m.m.

Bruker BlueZ direkte over D-Bus. Hvis en enhet krever PIN-kode, viser KDE/GNOME sin egen
Bluetooth-agent spørsmålet (bluedevil / gnome-bluetooth).
"""
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

BZ = "org.bluez"
ICONS = {"audio-headset": "audio-headset-symbolic", "audio-headphones": "audio-headphones-symbolic",
         "audio-card": "audio-speakers-symbolic", "input-gaming": "input-gaming-symbolic",
         "input-mouse": "input-mouse-symbolic", "input-keyboard": "input-keyboard-symbolic",
         "phone": "phone-symbolic", "computer": "computer-symbolic", "input-tablet": "input-tablet-symbolic"}


def bus():
    return Gio.bus_get_sync(Gio.BusType.SYSTEM, None)


def objects():
    try:
        r = bus().call_sync(BZ, "/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects", None, None,
                            Gio.DBusCallFlags.NONE, 10000, None)
        return r.unpack()[0]
    except GLib.Error:
        return {}


def call(path, iface, method, args=None, timeout=30000):
    return bus().call_sync(BZ, path, iface, method, args, None, Gio.DBusCallFlags.NONE, timeout, None)


def set_prop(path, iface, prop, variant):
    bus().call_sync(BZ, path, "org.freedesktop.DBus.Properties", "Set",
                    GLib.Variant("(ssv)", (iface, prop, variant)), None, Gio.DBusCallFlags.NONE, 10000, None)


def adapter(objs):
    return next(((p, i["org.bluez.Adapter1"]) for p, i in objs.items() if "org.bluez.Adapter1" in i), (None, None))


class BluetoothPage(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(12)
        self.set_child(Adw.Clamp(maximum_size=__import__("theme").PAGE_WIDTH, child=box))

        top = Gtk.Box(spacing=8)
        t = Gtk.Label(label="Bluetooth", xalign=0, hexpand=True)
        t.add_css_class("title-3")
        top.append(t)
        self.power = Gtk.Switch(valign=Gtk.Align.CENTER, tooltip_text="Bluetooth på/av")
        self.power.connect("notify::active", self._on_power)
        top.append(self.power)
        self.scan_btn = Gtk.ToggleButton(label="Søk etter enheter")
        self.scan_btn.connect("toggled", self._on_scan)
        top.append(self.scan_btn)
        box.append(top)
        self.status = Gtk.Label(xalign=0, wrap=True)
        self.status.add_css_class("dim-label")
        box.append(self.status)

        h1 = Gtk.Label(label="Mine enheter", xalign=0)
        h1.add_css_class("heading")
        box.append(h1)
        self.paired = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.paired.add_css_class("boxed-list")
        box.append(self.paired)
        h2 = Gtk.Label(label="Enheter i nærheten", xalign=0)
        h2.add_css_class("heading")
        box.append(h2)
        tip = Gtk.Label(label="Sett enheten i paringsmodus (ofte: hold inne av/på- eller Bluetooth-knappen til lyset "
                              "blinker), og trykk «Søk etter enheter».", xalign=0, wrap=True)
        tip.add_css_class("caption")
        tip.add_css_class("dim-label")
        box.append(tip)
        self.nearby = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.nearby.add_css_class("boxed-list")
        box.append(self.nearby)

        self._quiet = False
        self._sig = None
        self.busy = set()
        try:
            self._sub = bus().signal_subscribe(BZ, None, None, None, None, Gio.DBusSignalFlags.NONE,
                                               lambda *a: GLib.idle_add(self._q), None)
        except GLib.Error:
            pass
        self._pending = False
        self.refresh()
        GLib.timeout_add_seconds(5, lambda: (self.refresh(), True)[1])

    def _q(self):
        if not self._pending:
            self._pending = True
            GLib.timeout_add(400, lambda: (setattr(self, "_pending", False), self.refresh(), False)[2])
        return False

    def refresh(self):
        objs = objects()
        ap, ad = adapter(objs)
        self.adapter = ap
        self._quiet = True
        if not ap:
            self.power.set_sensitive(False)
            self.scan_btn.set_sensitive(False)
            self.status.set_label("Fant ingen Bluetooth-adapter. Sjekk at Bluetooth er slått på i BIOS, "
                                  "eller sett inn en Bluetooth-USB-pinne.")
            self._quiet = False
            return False
        self.power.set_active(ad.get("Powered", False))
        self.scan_btn.set_active(ad.get("Discovering", False))
        self.scan_btn.set_sensitive(ad.get("Powered", False))
        self._quiet = False
        devs = []
        for p, i in objs.items():
            d = i.get("org.bluez.Device1")
            if not d or not p.startswith(ap):
                continue
            bat = i.get("org.bluez.Battery1", {}).get("Percentage")
            devs.append({"path": p, "name": d.get("Alias") or d.get("Name") or d.get("Address"),
                         "paired": d.get("Paired") or d.get("Bonded"), "connected": d.get("Connected"),
                         "icon": ICONS.get(d.get("Icon", ""), "bluetooth-symbolic"), "battery": bat,
                         "rssi": d.get("RSSI"), "named": bool(d.get("Name"))})
        sig = tuple(sorted((d["path"], d["paired"], d["connected"], d["battery"], d["path"] in self.busy)
                           for d in devs))
        if sig != self._sig:
            self._sig = sig
            self._fill(devs)
        n_con = sum(1 for d in devs if d["connected"])
        if not ad.get("Powered"):
            self.status.set_label("Bluetooth er slått av.")
        elif ad.get("Discovering"):
            self.status.set_label("Søker etter enheter i nærheten …")
        else:
            self.status.set_label(f"{n_con} tilkoblet" if n_con else "Ingen enheter tilkoblet")
        return False

    def _fill(self, devs):
        for lb in (self.paired, self.nearby):
            while (c := lb.get_first_child()):
                lb.remove(c)
        paired = sorted((d for d in devs if d["paired"]), key=lambda d: (not d["connected"], d["name"].lower()))
        near = sorted((d for d in devs if not d["paired"] and d["named"]),
                      key=lambda d: -(d["rssi"] or -999))
        for d in paired:
            self.paired.append(self._row(d))
        for d in near[:30]:
            self.nearby.append(self._row(d))
        if not paired:
            self.paired.append(self._empty("Ingen parede enheter ennå."))
        if not near:
            self.nearby.append(self._empty("Ingen enheter funnet – trykk «Søk etter enheter»."))

    @staticmethod
    def _empty(text):
        import ui
        return Gtk.ListBoxRow(child=ui.empty("ks-bluetooth-symbolic", text), activatable=False, selectable=False)

    def _row(self, d):
        row = Gtk.Box(spacing=12)
        for side, v in (("top", 8), ("bottom", 8), ("start", 12), ("end", 12)):
            getattr(row, f"set_margin_{side}")(v)
        img = Gtk.Image.new_from_icon_name(d["icon"])
        img.set_pixel_size(28)
        row.append(img)
        mid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        t = Gtk.Label(label=d["name"], xalign=0, ellipsize=3)
        t.add_css_class("heading")
        mid.append(t)
        info = []
        if d["connected"]:
            info.append("✓ Tilkoblet")
        elif d["paired"]:
            info.append("Paret")
        if d["battery"] is not None:
            info.append(f"🔋 {d['battery']} %")
        if info:
            s = Gtk.Label(label=" · ".join(info), xalign=0)
            s.add_css_class("caption")
            s.add_css_class("dim-label")
            mid.append(s)
        row.append(mid)
        if d["path"] in self.busy:
            sp = Gtk.Spinner(spinning=True)
            row.append(sp)
            return row
        if d["paired"]:
            rm = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text="Glem enheten", valign=Gtk.Align.CENTER)
            rm.add_css_class("flat")
            rm.connect("clicked", lambda *_: self._remove(d))
            row.append(rm)
            b = Gtk.Button(label="Koble fra" if d["connected"] else "Koble til", valign=Gtk.Align.CENTER)
            b.add_css_class("destructive-action" if d["connected"] else "suggested-action")
            b.connect("clicked", lambda *_: self._act(d, "Disconnect" if d["connected"] else "Connect"))
        else:
            b = Gtk.Button(label="Par og koble til", valign=Gtk.Align.CENTER)
            b.add_css_class("suggested-action")
            b.connect("clicked", lambda *_: self._act(d, "Pair"))
        row.append(b)
        return row

    # --- handlinger -------------------------------------------------------------
    def _on_power(self, sw, _p):
        if self._quiet or not self.adapter:
            return
        try:
            set_prop(self.adapter, "org.bluez.Adapter1", "Powered", GLib.Variant("b", sw.get_active()))
        except GLib.Error as e:
            self.status.set_label(f"Feil: {e.message or 'ukjent feil fra BlueZ'}")
        GLib.timeout_add(600, lambda: (self.refresh(), False)[1])

    def _on_scan(self, btn, _p=None):
        if self._quiet or not self.adapter:
            return
        try:
            call(self.adapter, "org.bluez.Adapter1", "StartDiscovery" if btn.get_active() else "StopDiscovery")
            if btn.get_active():             # stopp av seg selv etter 30 sek (sparer strøm)
                GLib.timeout_add_seconds(30, lambda: (btn.get_active() and btn.set_active(False), False)[1])
        except GLib.Error as e:
            self.status.set_label(f"Feil: {e.message or 'ukjent feil fra BlueZ'}")

    def _act(self, d, method):
        self.busy.add(d["path"])
        self._sig = None
        self.refresh()
        self.status.set_label({"Pair": f"Parer med {d['name']} …", "Connect": f"Kobler til {d['name']} …",
                               "Disconnect": f"Kobler fra {d['name']} …"}[method])

        def work():
            err = None
            try:
                if method == "Pair":
                    call(d["path"], "org.bluez.Device1", "Pair", timeout=60000)
                    set_prop(d["path"], "org.bluez.Device1", "Trusted", GLib.Variant("b", True))
                    call(d["path"], "org.bluez.Device1", "Connect", timeout=30000)
                else:
                    call(d["path"], "org.bluez.Device1", method)
            except GLib.Error as e:
                err = e.message.split(":")[-1].strip()
            self.busy.discard(d["path"])
            ok = {"Pair": f"{d['name']} er paret og tilkoblet ✓", "Connect": f"{d['name']} er tilkoblet ✓",
                  "Disconnect": f"{d['name']} er frakoblet"}[method]
            GLib.idle_add(self.status.set_label, ok if not err else f"Kunne ikke {('pare med' if method == 'Pair' else 'koble til')} "
                          f"{d['name']}: {err}")
            self._sig = None
            GLib.idle_add(self.refresh)
        threading.Thread(target=work, daemon=True).start()

    def _remove(self, d):
        try:
            call(self.adapter, "org.bluez.Adapter1", "RemoveDevice", GLib.Variant("(o)", (d["path"],)))
            self.status.set_label(f"{d['name']} er glemt")
        except GLib.Error as e:
            self.status.set_label(f"Feil: {e.message or 'ukjent feil fra BlueZ'}")
        self._sig = None
        self.refresh()
