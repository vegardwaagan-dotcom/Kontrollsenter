"""Ikon i systemstatusfeltet (StatusNotifierItem + dbusmenu over D-Bus) – virker i KDE Plasma,
og i GNOME med AppIndicator-utvidelsen.

Venstreklikk: vis/skjul vinduet. Høyreklikk: meny (strømmodus, overlay, avslutt).
"""
import os

from gi.repository import Gio, GLib

SNI_XML = """<node><interface name="org.kde.StatusNotifierItem">
<property name="Category" type="s" access="read"/><property name="Id" type="s" access="read"/>
<property name="Title" type="s" access="read"/><property name="Status" type="s" access="read"/>
<property name="WindowId" type="i" access="read"/><property name="IconName" type="s" access="read"/>
<property name="IconThemePath" type="s" access="read"/><property name="Menu" type="o" access="read"/>
<property name="ItemIsMenu" type="b" access="read"/><property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
<method name="Activate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="SecondaryActivate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="ContextMenu"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="Scroll"><arg type="i" direction="in"/><arg type="s" direction="in"/></method>
<signal name="NewToolTip"/><signal name="NewIcon"/><signal name="NewTitle"/><signal name="NewStatus"><arg type="s"/></signal>
</interface></node>"""

MENU_XML = """<node><interface name="com.canonical.dbusmenu">
<property name="Version" type="u" access="read"/><property name="TextDirection" type="s" access="read"/>
<property name="Status" type="s" access="read"/><property name="IconThemePath" type="as" access="read"/>
<method name="GetLayout"><arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="as" direction="in"/>
<arg type="u" direction="out"/><arg type="(ia{sv}av)" direction="out"/></method>
<method name="GetGroupProperties"><arg type="ai" direction="in"/><arg type="as" direction="in"/>
<arg type="a(ia{sv})" direction="out"/></method>
<method name="GetProperty"><arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="out"/></method>
<method name="Event"><arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="in"/>
<arg type="u" direction="in"/></method>
<method name="EventGroup"><arg type="a(isvu)" direction="in"/><arg type="ai" direction="out"/></method>
<method name="AboutToShow"><arg type="i" direction="in"/><arg type="b" direction="out"/></method>
<method name="AboutToShowGroup"><arg type="ai" direction="in"/><arg type="ai" direction="out"/><arg type="ai" direction="out"/></method>
<signal name="LayoutUpdated"><arg type="u"/><arg type="i"/></signal>
<signal name="ItemsPropertiesUpdated"><arg type="a(ia{sv})"/><arg type="a(ias)"/></signal>
</interface></node>"""


class Tray:
    """items: liste med (id, tekst, handling) – tekst «-» gir skillelinje. Kan bygges om med set_items()."""

    def __init__(self, title, icon, on_activate, items, tr=lambda s: s):
        self.title, self.icon, self.on_activate, self.tr = title, icon, on_activate, tr
        self.items = items
        self.tooltip = ""
        self.revision = 1
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
        sni = Gio.DBusNodeInfo.new_for_xml(SNI_XML).interfaces[0]
        menu = Gio.DBusNodeInfo.new_for_xml(MENU_XML).interfaces[0]
        self._regs = [
            self.bus.register_object("/StatusNotifierItem", sni, self._sni_call, self._sni_prop, None),
            self.bus.register_object("/MenuBar", menu, self._menu_call, self._menu_prop, None)]
        self._own = Gio.bus_own_name_on_connection(self.bus, self.name, Gio.BusNameOwnerFlags.NONE, None, None)
        self._register()
        # registrer på nytt hvis panelet (vert) starter på nytt
        self._watch = Gio.bus_watch_name_on_connection(
            self.bus, "org.kde.StatusNotifierWatcher", Gio.BusNameWatcherFlags.NONE,
            lambda *a: self._register(), None)

    def close(self):
        """Fjern ikonet fra statusfeltet."""
        Gio.bus_unwatch_name(self._watch)
        for r in self._regs:
            self.bus.unregister_object(r)
        Gio.bus_unown_name(self._own)

    def _register(self):
        try:
            self.bus.call_sync("org.kde.StatusNotifierWatcher", "/StatusNotifierWatcher",
                               "org.kde.StatusNotifierWatcher", "RegisterStatusNotifierItem",
                               GLib.Variant("(s)", (self.name,)), None, Gio.DBusCallFlags.NONE, 3000, None)
        except GLib.Error:
            pass

    # --- StatusNotifierItem ------------------------------------------------------
    def _sni_prop(self, conn, sender, path, iface, prop):
        tt = GLib.Variant("(sa(iiay)ss)", (self.icon, [], self.title, self.tooltip))
        return {"Category": GLib.Variant("s", "SystemServices"), "Id": GLib.Variant("s", "systemmonitor"),
                "Title": GLib.Variant("s", self.title), "Status": GLib.Variant("s", "Active"),
                "WindowId": GLib.Variant("i", 0), "IconName": GLib.Variant("s", self.icon),
                "IconThemePath": GLib.Variant("s", ""), "Menu": GLib.Variant("o", "/MenuBar"),
                "ItemIsMenu": GLib.Variant("b", False), "ToolTip": tt}.get(prop)

    def _sni_call(self, conn, sender, path, iface, method, params, inv):
        if method in ("Activate", "SecondaryActivate"):
            GLib.idle_add(self.on_activate)
        inv.return_value(None)

    def set_tooltip(self, text):
        if text != self.tooltip:
            self.tooltip = text
            self.bus.emit_signal(None, "/StatusNotifierItem", "org.kde.StatusNotifierItem", "NewToolTip", None)

    # --- meny --------------------------------------------------------------------
    def set_items(self, items):
        self.items = items
        self.revision += 1
        self.bus.emit_signal(None, "/MenuBar", "com.canonical.dbusmenu", "LayoutUpdated",
                             GLib.Variant("(ui)", (self.revision, 0)))

    def _props(self, item):
        _id, text, _fn = item[:3]
        if text == "-":
            return {"type": GLib.Variant("s", "separator")}
        p = {"label": GLib.Variant("s", self.tr(text)), "enabled": GLib.Variant("b", True),
             "visible": GLib.Variant("b", True)}
        if len(item) > 3 and item[3] is not None:              # avkrysningsboks/radio
            p["toggle-type"] = GLib.Variant("s", item[4] if len(item) > 4 else "radio")
            p["toggle-state"] = GLib.Variant("i", 1 if item[3] else 0)
        return p

    def _layout(self):
        kids = [GLib.Variant("(ia{sv}av)", (it[0], self._props(it), [])) for it in self.items]
        return (0, {"children-display": GLib.Variant("s", "submenu")}, kids)

    def _menu_prop(self, conn, sender, path, iface, prop):
        return {"Version": GLib.Variant("u", 3), "TextDirection": GLib.Variant("s", "ltr"),
                "Status": GLib.Variant("s", "normal"), "IconThemePath": GLib.Variant("as", [])}.get(prop)

    def _menu_call(self, conn, sender, path, iface, method, params, inv):
        if method == "GetLayout":
            inv.return_value(GLib.Variant("(u(ia{sv}av))", (self.revision, self._layout())))
        elif method == "GetGroupProperties":
            ids = params.unpack()[0]
            res = [(it[0], self._props(it)) for it in self.items if not ids or it[0] in ids]
            inv.return_value(GLib.Variant("(a(ia{sv}))", (res,)))
        elif method == "GetProperty":
            iid, name = params.unpack()
            it = next((x for x in self.items if x[0] == iid), None)
            v = self._props(it).get(name) if it else None
            inv.return_value(GLib.Variant("(v)", (v or GLib.Variant("s", ""),)))
        elif method == "Event":
            iid, ev = params.unpack()[:2]
            if ev == "clicked":
                it = next((x for x in self.items if x[0] == iid), None)
                if it and it[2]:
                    GLib.idle_add(it[2])
            inv.return_value(None)
        elif method == "EventGroup":
            for iid, ev, _d, _t in params.unpack()[0]:
                if ev == "clicked":
                    it = next((x for x in self.items if x[0] == iid), None)
                    if it and it[2]:
                        GLib.idle_add(it[2])
            inv.return_value(GLib.Variant("(ai)", ([],)))
        elif method == "AboutToShow":
            inv.return_value(GLib.Variant("(b)", (False,)))
        elif method == "AboutToShowGroup":
            inv.return_value(GLib.Variant("(aiai)", ([], [])))
        else:
            inv.return_value(None)
