"""Wi-Fi-fanen i Kontrollsenter – koble til trådløse nettverk (NetworkManager).

Passord sendes rett til NetworkManager over D-Bus – aldri på kommandolinjen (som andre
prosesser kan lese) eller i en fil. NetworkManager lagrer det i en fil som bare root kan lese.
"""
import os
import re
import subprocess
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402


def nmcli(*args, timeout=40):
    try:
        r = subprocess.run(["nmcli", *args], capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, "LC_ALL": "C"})
        return r.returncode, r.stdout, r.stderr.strip()
    except (OSError, subprocess.SubprocessError) as e:
        return 1, "", str(e)


def split_t(line):
    """Del en «nmcli -t»-linje på kolon (\\: er et kolon inni en verdi)."""
    out, cur, esc = [], "", False
    for ch in line:
        if esc:
            cur += ch
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == ":":
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return out


def wifi_devices():
    code, out, _e = nmcli("-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device")
    return [dict(zip(("dev", "type", "state", "con"), split_t(ln)))
            for ln in out.splitlines() if split_t(ln)[1:2] == ["wifi"]]


def saved_wifi():
    code, out, _e = nmcli("-t", "-f", "NAME,TYPE", "connection", "show")
    return {split_t(ln)[0] for ln in out.splitlines() if "wireless" in ln}


def scan(rescan="auto"):
    code, out, err = nmcli("-t", "-f", "IN-USE,SSID,SECURITY,SIGNAL,CHAN,RATE", "device", "wifi",
                           "list", "--rescan", rescan, timeout=60)
    nets = {}
    for ln in out.splitlines():
        f = split_t(ln)
        if len(f) < 6 or not f[1]:
            continue
        n = {"inuse": f[0] == "*", "ssid": f[1], "sec": f[2] if f[2] not in ("", "--") else "",
             "signal": int(f[3] or 0), "chan": f[4], "rate": f[5]}
        old = nets.get(n["ssid"])
        if not old or n["inuse"] or (n["signal"] > old["signal"] and not old["inuse"]):
            nets[n["ssid"]] = n
    return sorted(nets.values(), key=lambda n: (not n["inuse"], -n["signal"]))


def signal_icon(s):
    lvl = "excellent" if s >= 75 else "good" if s >= 50 else "ok" if s >= 25 else "weak"
    return f"network-wireless-signal-{lvl}-symbolic"


NM = "org.freedesktop.NetworkManager"


def _nm_proxy(path, iface):
    from gi.repository import Gio
    return Gio.DBusProxy.new_for_bus_sync(Gio.BusType.SYSTEM, Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES,
                                          None, NM, path, iface, None)


def _nm_add_and_activate(ssid, key_mgmt, password, hidden):
    """Ny tilkobling via NetworkManagers D-Bus-API – passordet går rett til NetworkManager
    (aldri på kommandolinjen eller i en fil)."""
    import time
    from gi.repository import Gio
    dev_name = next((d["dev"] for d in wifi_devices()), None)
    if not dev_name:
        return False, "Fant ikke Wi-Fi-kortet"
    nm = _nm_proxy("/org/freedesktop/NetworkManager", NM)
    dev = nm.call_sync("GetDeviceByIpIface", GLib.Variant("(s)", (dev_name,)),
                       Gio.DBusCallFlags.NONE, 10000, None).unpack()[0]
    settings = {
        "connection": {"id": GLib.Variant("s", ssid), "type": GLib.Variant("s", "802-11-wireless")},
        "802-11-wireless": {"ssid": GLib.Variant("ay", ssid.encode()), "hidden": GLib.Variant("b", hidden)},
    }
    if key_mgmt:
        settings["802-11-wireless-security"] = {"key-mgmt": GLib.Variant("s", key_mgmt),
                                                "psk": GLib.Variant("s", password or "")}
    con_path, act_path = nm.call_sync(
        "AddAndActivateConnection", GLib.Variant("(a{sa{sv}}oo)", (settings, dev, "/")),
        Gio.DBusCallFlags.NONE, 30000, None).unpack()
    act = _nm_proxy(act_path, NM + ".Connection.Active")
    state = 0
    for _ in range(90):                       # vent på at tilkoblingen er ferdig (maks ~45 s)
        try:
            state = act.call_sync("org.freedesktop.DBus.Properties.Get",
                                  GLib.Variant("(ss)", (NM + ".Connection.Active", "State")),
                                  Gio.DBusCallFlags.NONE, 5000, None).unpack()[0]
        except Exception:  # noqa: BLE001 – den aktive tilkoblingen forsvant = feilet
            state = 4
        if state in (2, 4):                    # 2 = tilkoblet, 4 = frakoblet (feilet)
            break
        time.sleep(0.5)
    if state == 2:
        return True, ""
    try:                                      # rydd bort den mislykkede tilkoblingen
        _nm_proxy(con_path, NM + ".Settings.Connection").call_sync(
            "Delete", None, Gio.DBusCallFlags.NONE, 10000, None)
    except Exception:  # noqa: BLE001
        pass
    return False, "Feil passord, eller nettverket avviste tilkoblingen."


def connect(ssid, sec, password=None, hidden=False):
    """Koble til. Returnerer (ok, melding)."""
    if ssid in saved_wifi() and password is None:
        code, out, err = nmcli("connection", "up", "id", ssid, timeout=60)
        return code == 0, err or out
    if "802.1X" in (sec or ""):
        return False, "Bedriftsnettverk (802.1X) må settes opp i systeminnstillingene."
    key_mgmt = None
    if sec:
        key_mgmt = "sae" if ("WPA3" in sec and "WPA2" not in sec and "WPA1" not in sec) else "wpa-psk"
    try:
        return _nm_add_and_activate(ssid, key_mgmt, password, hidden)
    except Exception as e:  # noqa: BLE001
        return False, str(e)


class WifiPage(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(12)
        self.set_child(Adw.Clamp(maximum_size=900, child=box))

        top = Gtk.Box(spacing=8)
        t = Gtk.Label(label="Trådløst nettverk (Wi-Fi)", xalign=0, hexpand=True)
        t.add_css_class("title-3")
        top.append(t)
        self.radio = Gtk.Switch(valign=Gtk.Align.CENTER, tooltip_text="Wi-Fi på/av")
        self.radio.connect("notify::active", self._on_radio)
        top.append(self.radio)
        self.scan_btn = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Søk etter nettverk")
        self.scan_btn.connect("clicked", lambda *_: self.refresh(True))
        top.append(self.scan_btn)
        box.append(top)

        self.current = Gtk.Label(xalign=0, wrap=True)
        self.current.add_css_class("dim-label")
        box.append(self.current)
        self.status = Gtk.Label(xalign=0, wrap=True)
        box.append(self.status)
        self.spinner = Gtk.Spinner(halign=Gtk.Align.START)
        box.append(self.spinner)

        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.list.add_css_class("boxed-list")
        box.append(self.list)

        hidden = Gtk.Button(label="Koble til skjult nettverk …", halign=Gtk.Align.START)
        hidden.add_css_class("flat")
        hidden.connect("clicked", self._hidden)
        box.append(hidden)
        self.hidden_btn = hidden

        self._quiet = False
        self.refresh()
        GLib.timeout_add_seconds(20, lambda: (self.refresh(), True)[1])

    def _busy(self, on, text=None):
        self.spinner.set_spinning(on)
        if text is not None:
            self.status.set_label(text)
        return False

    def refresh(self, rescan=False):
        self._busy(True, "Søker etter nettverk …" if rescan else None)

        def work():
            devs = wifi_devices()
            code, out, _e = nmcli("-t", "-f", "WIFI", "radio")
            radio = out.strip() == "enabled"
            nets = scan("yes" if rescan else "auto") if devs and radio else []
            saved = saved_wifi()
            ip = ""
            con = next((d for d in devs if d["state"] == "connected"), None)
            if con:
                c2, o2, _ = nmcli("-t", "-f", "IP4.ADDRESS", "device", "show", con["dev"])
                ip = o2.split(":", 1)[1].strip() if ":" in o2 else ""
            GLib.idle_add(self._show, devs, radio, nets, saved, con, ip)
        threading.Thread(target=work, daemon=True).start()

    def _show(self, devs, radio, nets, saved, con, ip):
        self._busy(False)
        self._quiet = True
        self.radio.set_active(radio)
        self._quiet = False
        while (c := self.list.get_first_child()):
            self.list.remove(c)
        if not devs:
            self.radio.set_sensitive(False)
            self.scan_btn.set_sensitive(False)
            self.hidden_btn.set_visible(False)
            board = ""
            try:
                board = open("/sys/class/dmi/id/board_name").read().strip()
            except OSError:
                pass
            hint = ("Hovedkortet har innebygd Wi-Fi, men det er slått av i BIOS: Advanced → Onboard Devices "
                    "Configuration → Wi-Fi Controller → Enabled." if "WIFI" in board.upper() else
                    "Sett inn et Wi-Fi-kort eller en USB-pinne. Kjør «Systemsjekk» hvis kortet mangler driver.")
            self.current.set_label("Fant ikke noe Wi-Fi-kort i maskinen.\n" + hint)
            return False
        self.radio.set_sensitive(True)
        self.scan_btn.set_sensitive(radio)
        self.hidden_btn.set_visible(radio)
        if not radio:
            self.current.set_label("Wi-Fi er slått av. Slå det på med bryteren øverst til høyre.")
            return False
        self.current.set_label(f"Tilkoblet: {con['con']}" + (f" · IP {ip}" if ip else "") if con
                               else "Ikke tilkoblet et trådløst nettverk")
        for n in nets:
            self.list.append(self._row(n, n["ssid"] in saved))
        if not nets:
            self.list.append(Gtk.Label(label="Ingen nettverk funnet. Trykk ⟳ for å søke på nytt.",
                                       margin_top=16, margin_bottom=16))
        return False

    def _row(self, n, known):
        row = Gtk.Box(spacing=12)
        for side, v in (("top", 8), ("bottom", 8), ("start", 12), ("end", 12)):
            getattr(row, f"set_margin_{side}")(v)
        img = Gtk.Image.new_from_icon_name(signal_icon(n["signal"]))
        img.set_pixel_size(24)
        row.append(img)
        mid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        t = Gtk.Label(label=n["ssid"], xalign=0, ellipsize=3)
        t.add_css_class("heading")
        mid.append(t)
        info = [f"{n['signal']} %", ("🔒 " + n["sec"]) if n["sec"] else "Åpent nettverk"]
        if n["inuse"]:
            info.insert(0, "✓ Tilkoblet")
        elif known:
            info.insert(0, "Lagret")
        d = Gtk.Label(label=" · ".join(info), xalign=0)
        d.add_css_class("caption")
        d.add_css_class("dim-label")
        mid.append(d)
        row.append(mid)
        if known and not n["inuse"]:
            f = Gtk.Button(label="Glem", valign=Gtk.Align.CENTER)
            f.add_css_class("flat")
            f.connect("clicked", lambda *_: self._forget(n["ssid"]))
            row.append(f)
        b = Gtk.Button(label="Koble fra" if n["inuse"] else "Koble til", valign=Gtk.Align.CENTER)
        b.add_css_class("destructive-action" if n["inuse"] else "suggested-action")
        b.connect("clicked", lambda *_: self._disconnect(n) if n["inuse"] else self._connect(n, known))
        row.append(b)
        return row

    # --- handlinger --------------------------------------------------------------
    def _on_radio(self, sw, _p):
        if self._quiet:
            return
        self._busy(True, "Slår Wi-Fi " + ("på …" if sw.get_active() else "av …"))

        def work():
            nmcli("radio", "wifi", "on" if sw.get_active() else "off")
            GLib.idle_add(self.refresh, False)
        threading.Thread(target=work, daemon=True).start()

    def _connect(self, n, known):
        if n["sec"] and not known:
            self._ask_password(n["ssid"], n["sec"])
        else:
            self._do_connect(n["ssid"], n["sec"], None)

    def _ask_password(self, ssid, sec, hidden=False):
        d = Adw.AlertDialog(heading=f"Koble til «{ssid}»" if ssid else "Skjult nettverk",
                            body="Skriv inn passordet for nettverket.")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        ssid_entry = None
        if hidden:
            ssid_entry = Gtk.Entry(placeholder_text="Nettverksnavn (SSID)")
            box.append(ssid_entry)
        pw = Gtk.PasswordEntry(show_peek_icon=True, placeholder_text="Passord")
        box.append(pw)
        d.set_extra_child(box)
        d.add_response("cancel", "Avbryt")
        d.add_response("ok", "Koble til")
        d.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
        d.set_default_response("ok")
        pw.connect("activate", lambda *_: (d.close(), self._do_connect(
            ssid_entry.get_text() if hidden else ssid, sec, pw.get_text(), hidden)))

        def resp(_d, r):
            if r == "ok":
                name = ssid_entry.get_text().strip() if hidden else ssid
                if name:
                    self._do_connect(name, sec, pw.get_text() or None, hidden)
        d.connect("response", resp)
        d.present(self)

    def _do_connect(self, ssid, sec, password, hidden=False):
        self._busy(True, f"Kobler til «{ssid}» …")

        def work():
            ok, msg = connect(ssid, sec, password, hidden)
            if not ok and re.search(r"secrets|password|psk|802-11-wireless-security", msg, re.I):
                msg = "Feil passord, eller nettverket avviste tilkoblingen."
            GLib.idle_add(self._busy, False, f"Tilkoblet «{ssid}» ✓" if ok else f"Kunne ikke koble til: {msg}")
            GLib.idle_add(self.refresh, False)
        threading.Thread(target=work, daemon=True).start()

    def _disconnect(self, n):
        self._busy(True, f"Kobler fra «{n['ssid']}» …")

        def work():
            for d in wifi_devices():
                if d["state"] == "connected":
                    nmcli("device", "disconnect", d["dev"])
            GLib.idle_add(self._busy, False, "Frakoblet")
            GLib.idle_add(self.refresh, False)
        threading.Thread(target=work, daemon=True).start()

    def _forget(self, ssid):
        def work():
            code, out, err = nmcli("connection", "delete", "id", ssid)
            GLib.idle_add(self._busy, False, f"«{ssid}» er glemt" if code == 0 else f"Feil: {err or 'nmcli svarte uten feilmelding'}")
            GLib.idle_add(self.refresh, False)
        threading.Thread(target=work, daemon=True).start()

    def _hidden(self, *_):
        self._ask_password("", "WPA2", hidden=True)
