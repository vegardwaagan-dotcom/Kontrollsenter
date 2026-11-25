"""Mini-vindu: lite vindu med temperaturer, last og strøm som ligger øverst over andre vinduer.

Wayland lar ikke programmer legge seg øverst selv. På KDE Plasma ber vi KWin om det med et lite
skript over D-Bus, og på Hyprland festes det med hyprctl (pin). På GNOME: Alt+Mellomrom → «Alltid øverst».
"""
import os
import tempfile

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

import i18n  # noqa: E402

TITLE = "Kontrollsenter mini"
KWIN_JS = """
const list = workspace.windowList ? workspace.windowList() : workspace.clientList();
for (const w of list) {
    if (w.caption === "%s") { w.keepAbove = true; w.skipTaskbar = true; }
}
"""


def keep_above(caption):
    """Be KWin (KDE) holde vinduet øverst. Stille hvis det ikke går."""
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        fd, path = tempfile.mkstemp(suffix=".js", prefix="kontrollsenter-mini-")
        with os.fdopen(fd, "w") as f:
            f.write(KWIN_JS % caption.replace('"', ""))
        name = "kontrollsenter-mini"
        call = lambda obj, iface, method, args, rtype=None: bus.call_sync(  # noqa: E731
            "org.kde.KWin", obj, iface, method, args, rtype, Gio.DBusCallFlags.NONE, 3000, None)
        try:
            call("/Scripting", "org.kde.kwin.Scripting", "unloadScript", GLib.Variant("(s)", (name,)))
        except GLib.Error:
            pass
        sid = call("/Scripting", "org.kde.kwin.Scripting", "loadScript",
                   GLib.Variant("(ss)", (path, name)), GLib.VariantType.new("(i)")).unpack()[0]
        for obj in (f"/Scripting/Script{sid}", f"/{sid}"):
            try:
                call(obj, "org.kde.kwin.Script", "run", None)
                break
            except GLib.Error:
                continue
        GLib.timeout_add_seconds(3, lambda: (os.path.exists(path) and os.remove(path), False)[1])
        return True
    except (GLib.Error, OSError):
        return False


class MiniWindow(Adw.Window):
    def __init__(self, main):
        super().__init__(title=TITLE, default_width=330, default_height=150, resizable=False)
        self.main = main
        tv = Adw.ToolbarView()
        hb = Adw.HeaderBar(show_title=False)
        hb.add_css_class("flat")
        open_btn = Gtk.Button(icon_name="ks-overview-symbolic", tooltip_text=i18n.tr("Åpne Kontrollsenter"))
        open_btn.connect("clicked", lambda *_: (main.set_visible(True), main.present()))
        hb.pack_start(open_btn)
        tv.add_top_bar(hb)
        grid = Gtk.Grid(column_spacing=18, row_spacing=4, halign=Gtk.Align.CENTER)
        for side in ("start", "end", "bottom"):
            getattr(grid, f"set_margin_{side}")(14)
        self.vals = {}
        for col, (key, name) in enumerate((("cpu", "CPU"), ("gpu", "GPU"), ("pow", "Strøm"))):
            n = Gtk.Label(label=i18n.tr(name))
            n.add_css_class("caption-heading")
            n.add_css_class("dim-label")
            grid.attach(n, col, 0, 1, 1)
            v = Gtk.Label()
            v.add_css_class("title-2")
            v.add_css_class("numeric")
            grid.attach(v, col, 1, 1, 1)
            sub = Gtk.Label()
            sub.add_css_class("caption")
            sub.add_css_class("dim-label")
            sub.add_css_class("numeric")
            grid.attach(sub, col, 2, 1, 1)
            self.vals[key] = (v, sub)
        tv.set_content(grid)
        self.set_content(tv)
        self.connect("map", lambda *_: GLib.timeout_add(400, lambda: keep_above(TITLE) and False))
        self._ks_hypr_own = True                     # Hyprland: flytende og festet øverst (desktop.py)
        import desktop
        desktop.hypr_follow(self, TITLE, floating=True, pin=True, size=(330, 150))
        self.refresh(main._cpu_t if hasattr(main, "_cpu_t") else None,
                     main.nvidia.data if main.nvidia.available else None, getattr(main, "_power", {}))

    def refresh(self, cpu_t, nv, pw):
        v, sub = self.vals["cpu"]
        v.set_label(f"{cpu_t:.0f}°" if cpu_t is not None else "–")
        sub.set_label(f"{getattr(self.main, '_cpu_load', 0):.0f} %")
        v, sub = self.vals["gpu"]
        v.set_label(f"{nv['temp']:.0f}°" if nv and nv.get("temp") is not None else "–")
        sub.set_label(f"{nv.get('util') or 0:.0f} %" if nv else "")
        v, sub = self.vals["pow"]
        tot = (pw or {}).get("total")
        v.set_label(f"{tot:.0f} W" if tot else "–")
        mode = self.main.power.active_profile() if hasattr(self.main, "power") else None
        import cards
        sub.set_label(i18n.tr(cards.MODE_NAMES.get(mode, "")))
