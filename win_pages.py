"""Windows-utgavene av sidene som på Linux bruker Linux-tjenester (Logitech, MSI, Bluetooth, Wi-Fi, Programmer,
CPU-skjerm). Samme utseende – men styrt med Windows' egne verktøy (PnP, netsh, winget, ms-settings)."""
import glob
import json
import os
import re
import subprocess
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk  # noqa: E402

import i18n  # noqa: E402
import winsupport as WS  # noqa: E402


def _card(title, subtitle=None, icon=None):
    import automation
    return automation.card(title, subtitle, icon)


def _dim(text):
    lab = Gtk.Label(label=i18n.tr(text), xalign=0, wrap=True)
    lab.add_css_class("dim-label")
    return lab


def _button(label, fn, suggested=False):
    b = Gtk.Button(label=i18n.tr(label))
    if suggested:
        b.add_css_class("suggested-action")
    b.connect("clicked", lambda *_: fn())
    return b


def _bg(work, done):
    threading.Thread(target=lambda: GLib.idle_add(lambda: (done(work()), False)[1]), daemon=True).start()


def _list():
    lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
    lb.add_css_class("boxed-list")
    return lb


def _row(title, sub="", widgets=()):
    r = Gtk.Box(spacing=10)
    for side, v in (("top", 8), ("bottom", 8), ("start", 12), ("end", 10)):
        getattr(r, f"set_margin_{side}")(v)
    col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
    col.append(Gtk.Label(label=title, xalign=0, ellipsize=3))
    if sub:
        s = Gtk.Label(label=sub, xalign=0, ellipsize=3)
        s.add_css_class("caption")
        s.add_css_class("dim-label")
        col.append(s)
    r.append(col)
    for w in widgets:
        w.set_valign(Gtk.Align.CENTER)
        r.append(w)
    return r


class _Page(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(self.box, f"set_margin_{side}")(12)
        self.set_child(self.box)


def _winget(*args, timeout=900):
    return WS.run(["winget", *args, "--accept-source-agreements", "--disable-interactivity"], timeout)


# --------------------------------------------------------------------------
# Logitech
# --------------------------------------------------------------------------
GHUB_EXE = r"C:\Program Files\LGHUB\lghub.exe"


class LogitechWinPage(_Page):
    def __init__(self):
        super().__init__()
        c, i, _h = _card("Logitech-enheter", "På Windows styres DPI, knapper, lys og profiler i Logitech G HUB. "
                                             "Innstillingene lagres i musa og tastaturet, så de virker også på Linux.",
                         "ks-mouse-symbolic")
        lb = _list()
        devs = {}
        for d in WS.pnp_devices():
            if re.search(r"VID_046D|VID&0002046D|VID&01046D", d["id"], re.I) and d["name"] and \
                    not re.search(r"USB Input Device|HID-compliant|Composite|USB Composite", d["name"], re.I):
                devs.setdefault(d["name"], d)
        for name, d in sorted(devs.items()):
            lb.append(_row(name, d["cls"] + (" · " + i18n.tr("tilkoblet") if d["ok"] else "")))
        if not devs:
            import ui
            lb.append(ui.empty("ks-mouse-symbolic", "Ingen Logitech-enheter funnet"))
        i.append(lb)
        btns = Gtk.Box(spacing=8)
        if os.path.exists(GHUB_EXE):
            btns.append(_button("Åpne G HUB", lambda: WS.open_uri(GHUB_EXE), True))
        else:
            st = _dim("")

            def install():
                st.set_label(i18n.tr("Installerer G HUB …"))
                _bg(lambda: _winget("install", "-e", "--id", "Logitech.GHUB", "--silent")[0],
                    lambda code: st.set_label(i18n.tr("G HUB er installert ✓") if code == 0 else
                                              i18n.tr("Kunne ikke installere G HUB")))
            btns.append(_button("Installer G HUB", install, True))
            i.append(btns)
            i.append(st)
            self.box.append(c)
            return
        i.append(btns)
        self.box.append(c)


# --------------------------------------------------------------------------
# MSI (bærbare)
# --------------------------------------------------------------------------
class MsiWinPage(_Page):
    def __init__(self):
        super().__init__()
        bi = WS.bios_info()
        c, i, _h = _card(bi.get("SystemProductName", "MSI"),
                         f"{bi.get('BaseBoardProduct', '')} · BIOS {bi.get('BIOSVersion', '')}", "ks-laptop-symbolic")
        i.append(_dim("Ytelsesmodus (strømplan) byttes i Oversikt. Viftemodus (Cooler Boost), brukerscenario og "
                      "batterigrense styres av MSI Center på Windows – MSI har ingen åpen måte å styre dem på."))
        try:
            import psutil
            b = psutil.sensors_battery()
            if b:
                i.append(Gtk.Label(label=f"🔋 {b.percent:.0f} % · " + (i18n.tr("lader") if b.power_plugged else
                                                                     i18n.tr("på batteri")), xalign=0))
        except Exception:  # noqa: BLE001
            pass
        btns = Gtk.Box(spacing=8)
        btns.append(_button("Åpne MSI Center", lambda: WS.run(["explorer.exe", "shell:AppsFolder\\"
                                                                "9426MICRO-STARINTERNATION.MSICenter_kzh8wxbdkxb8p!App"]),
                            True))
        btns.append(_button("Strøm og batteri", lambda: WS.open_uri("ms-settings:powersleep")))
        i.append(btns)
        self.box.append(c)


# --------------------------------------------------------------------------
# Bluetooth
# --------------------------------------------------------------------------
class BluetoothWinPage(_Page):
    def __init__(self):
        super().__init__()
        c, i, head = _card("Bluetooth-enheter", "Parede enheter. Nye enheter pares i Windows-innstillingene.",
                           "ks-bluetooth-symbolic")
        self.lb = _list()
        i.append(self.lb)
        btns = Gtk.Box(spacing=8)
        btns.append(_button("Legg til enhet", lambda: WS.open_uri("ms-settings:bluetooth"), True))
        btns.append(_button("Oppdater", self.refresh))
        i.append(btns)
        self.box.append(c)
        self.refresh()

    def refresh(self):
        def work():
            import winsupport
            devs = winsupport._pnp_query()
            return [d for d in devs if d["cls"] == "Bluetooth" and d["name"] and
                    not re.search(r"enumerator|radio|adapter|transport|service|LE Generic|Microsoft",
                                  d["name"], re.I)]

        def done(devs):
            while (ch := self.lb.get_first_child()):
                self.lb.remove(ch)
            if not devs:
                import ui
                self.lb.append(ui.empty("ks-bluetooth-symbolic", "Ingen parede enheter"))
            seen = set()
            for d in devs:
                if d["name"] in seen:
                    continue
                seen.add(d["name"])
                self.lb.append(_row(d["name"], i18n.tr("tilkoblet") if d["ok"] else i18n.tr("ikke tilkoblet")))
        _bg(work, done)


# --------------------------------------------------------------------------
# Wi-Fi
# --------------------------------------------------------------------------
def _netsh(*args):
    return WS.run(["netsh", "wlan", *args], 20)[1]


class WifiWinPage(_Page):
    def __init__(self):
        super().__init__()
        c, i, head = _card("Tilkoblet", None, "ks-wifi-symbolic")
        self.now = _dim("…")
        i.append(self.now)
        self.box.append(c)
        c, i, head = _card("Nettverk i nærheten", "Kjente nettverk kobles til med ett klikk. Nye nettverk (med "
                                                  "passord) legges til i Windows-innstillingene.")
        self.lb = _list()
        i.append(self.lb)
        btns = Gtk.Box(spacing=8)
        btns.append(_button("Oppdater", self.refresh))
        btns.append(_button("Wi-Fi-innstillinger", lambda: WS.open_uri("ms-settings:network-wifi")))
        i.append(btns)
        self.box.append(c)
        self.refresh()

    def refresh(self):
        def work():
            iface = _netsh("show", "interfaces")
            nets = _netsh("show", "networks", "mode=bssid")
            profs = _netsh("show", "profiles")
            return iface, nets, profs

        def done(res):
            iface, nets, profs = res
            ssid = re.search(r"^\s*SSID\s*:\s*(.+)$", iface, re.M)
            sig = re.search(r"^\s*(?:Signal|Signalstyrke)\s*:\s*(\d+)\s*%", iface, re.M)
            self.now.set_label(f"{ssid.group(1).strip()} · {sig.group(1)} %" if ssid and sig else
                               (ssid.group(1).strip() if ssid else i18n.tr("Ikke tilkoblet")))
            known = set(m.strip() for m in re.findall(r":\s*(.+)$", profs, re.M))
            while (ch := self.lb.get_first_child()):
                self.lb.remove(ch)
            found = []
            for block in re.split(r"\n(?=SSID \d+)", nets):
                m = re.search(r"^SSID \d+\s*:\s*(.*)$", block, re.M)
                s = re.search(r"(\d+)\s*%", block)
                if m and m.group(1).strip():
                    found.append((m.group(1).strip(), int(s.group(1)) if s else 0))
            for name, strength in sorted(found, key=lambda x: -x[1])[:20]:
                w = []
                if name in known:
                    b = Gtk.Button(label=i18n.tr("Koble til"))
                    b.connect("clicked", lambda _b, n=name: _bg(lambda: _netsh("connect", f"name={n}"),
                                                                 lambda _r: GLib.timeout_add_seconds(
                                                                     3, lambda: (self.refresh(), False)[1])))
                    w.append(b)
                self.lb.append(_row(name, f"{strength} %" + (" · " + i18n.tr("kjent") if name in known else ""), w))
            if not found:
                import ui
                self.lb.append(ui.empty("ks-wifi-symbolic", "Ingen nettverk funnet"))
        _bg(work, done)


# --------------------------------------------------------------------------
# Programmer (winget) og oppstart
# --------------------------------------------------------------------------
CATALOG = [
    ("Valve.Steam", "Steam", "Spill"), ("EpicGames.EpicGamesLauncher", "Epic Games", "Spill"),
    ("Blizzard.BattleNet", "Battle.net", "Spill"), ("GOG.Galaxy", "GOG Galaxy", "Spill"),
    ("Discord.Discord", "Discord", "Spill"), ("Guru3D.Afterburner", "MSI Afterburner", "Spill"),
    ("Guru3D.RTSS", "RivaTuner (FPS-overlay)", "Spill"),
    ("Mozilla.Firefox", "Firefox", "Internett"), ("Google.Chrome", "Google Chrome", "Internett"),
    ("Brave.Brave", "Brave", "Internett"), ("Spotify.Spotify", "Spotify", "Media"),
    ("VideoLAN.VLC", "VLC", "Media"), ("OBSProject.OBSStudio", "OBS Studio", "Media"),
    ("GIMP.GIMP", "GIMP", "Media"), ("TheDocumentFoundation.LibreOffice", "LibreOffice", "Kontor"),
    ("Bitwarden.Bitwarden", "Bitwarden", "Kontor"), ("Microsoft.VisualStudioCode", "Visual Studio Code", "Kontor"),
    ("7zip.7zip", "7-Zip", "Verktøy"), ("OpenRGB.OpenRGB", "OpenRGB", "Verktøy"),
    ("LibreHardwareMonitor.LibreHardwareMonitor", "LibreHardwareMonitor", "Verktøy"),
    ("REALiX.HWiNFO", "HWiNFO", "Verktøy"), ("Logitech.GHUB", "Logitech G HUB", "Verktøy"),
    ("Microsoft.PowerToys", "PowerToys", "Verktøy"),
]


class ProgramsWinPage(_Page):
    def __init__(self):
        super().__init__()
        c, i, head = _card("Programmer", "Installer, oppdater og fjern programmer med winget (Windows' egen "
                                         "pakkebehandler).", "ks-programs-symbolic")
        top = Gtk.Box(spacing=8)
        self.upd = _button("Oppdater alle programmer", self.update_all, True)
        top.append(self.upd)
        i.append(top)
        self.st = _dim(i18n.tr("Leser installerte programmer …"))
        i.append(self.st)
        self.lb = _list()
        i.append(self.lb)
        self.box.append(c)
        self._autostart_card()
        self.refresh()

    def refresh(self):
        def work():
            code, out = _winget("list", timeout=120)
            return out

        def done(out):
            installed = {pid for pid, _n, _c in CATALOG if re.search(rf"\b{re.escape(pid)}\b", out, re.I)}
            ups = len(re.findall(r"^\S.*\s\d[\w.\-]*\s+\d[\w.\-]*\s+winget\s*$", out, re.M))
            self.st.set_label(i18n.tr("Kunne ikke lese winget") if not out.strip() else "")
            while (ch := self.lb.get_first_child()):
                self.lb.remove(ch)
            for pid, name, cat in CATALOG:
                on = pid in installed
                b = Gtk.Button(label=i18n.tr("Avinstaller" if on else "Installer"))
                if not on:
                    b.add_css_class("suggested-action")
                b.connect("clicked", lambda btn, p=pid, o=on: self.act(btn, p, o))
                self.lb.append(_row(name, i18n.tr(cat) + (" · ✓ " + i18n.tr("installert") if on else ""), [b]))
            _ = ups
        _bg(work, done)

    def act(self, btn, pid, installed):
        btn.set_sensitive(False)
        btn.set_label(i18n.tr("Arbeider …"))
        args = ["uninstall", "-e", "--id", pid, "--silent"] if installed else \
            ["install", "-e", "--id", pid, "--silent", "--accept-package-agreements"]
        _bg(lambda: _winget(*args)[0], lambda code: self.refresh())

    def update_all(self):
        self.upd.set_sensitive(False)
        self.st.set_label(i18n.tr("Oppdaterer alle programmer … (kan ta noen minutter)"))

        def done(res):
            self.upd.set_sensitive(True)
            import ui
            ui.status(self.st, "Programmene er oppdatert ✓" if res[0] == 0 else "Noen oppdateringer feilet")
            self.refresh()
        _bg(lambda: _winget("upgrade", "--all", "--silent", "--accept-package-agreements"), done)

    def _autostart_card(self):
        c, i, head = _card("Oppstart", "Programmer som starter når du logger inn.", "ks-overview-symbolic")
        lb = _list()
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WS.RUN_KEY) as k:
                n = 0
                while True:
                    try:
                        name, val, _t = winreg.EnumValue(k, n)
                    except OSError:
                        break
                    n += 1
                    sw = Gtk.Switch(active=True)

                    def toggle(w, _p, nm=name, v=val):
                        WS.autostart_set(nm, v if w.get_active() else None)
                    sw.connect("notify::active", toggle)
                    lb.append(_row(name, str(val)[:90], [sw]))
        except OSError:
            pass
        i.append(lb)
        i.append(_button("Flere oppstartsprogrammer (Windows)", lambda: WS.open_uri("ms-settings:startupapps")))
        self.box.append(c)


# --------------------------------------------------------------------------
# CPU-skjerm (Thermalright)
# --------------------------------------------------------------------------
class LcdWinPage(_Page):
    def __init__(self):
        super().__init__()
        c, i, _h = _card("Thermalright-skjerm", "På Windows styres kjølerskjermen av Thermalrights eget program "
                                                "(TRCC).", "ks-lcd-symbolic")
        exe = next(iter(glob.glob(r"C:\Program Files*\**\TRCC*.exe", recursive=False) +
                        glob.glob(os.path.expandvars(r"%LOCALAPPDATA%\Programs\**\TRCC*.exe"), recursive=True)), None)
        if exe:
            i.append(_button("Åpne TRCC", lambda: WS.open_uri(exe), True))
        else:
            i.append(_dim("TRCC er ikke installert. Last det ned fra Thermalright sin nettside."))
            i.append(_button("Åpne Thermalright.com", lambda: WS.open_uri("https://www.thermalright.com/support/download/"),
                             True))
        self.box.append(c)
