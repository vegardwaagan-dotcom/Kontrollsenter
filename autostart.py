"""Automatisk start ved innlogging – minimert – for faste programmer.

Hvert program får én oppstartsfil laget av Kontrollsenter. Andre oppstartsfiler for samme
program (laget av programmet selv eller tidligere) skrus av med Hidden=true (en kopi tas
vare på som .bak), slik at ingenting starter to ganger eller med vindu.
"""
import glob
import os
import re
import shutil
import subprocess

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

AUTOSTART = os.path.expanduser("~/.config/autostart")


def _flatpak(app):
    try:
        return subprocess.run(["flatpak", "info", app], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _trcc():
    try:
        import deps
        return deps.find_trcc()
    except Exception:  # noqa: BLE001
        return shutil.which("trcc")


def _battlenet_exec():
    """Finn Lutris-snarveien til Battle.net (meny, skrivebord)."""
    dirs = [os.path.expanduser("~/.local/share/applications"), os.path.expanduser("~/Desktop"),
            os.path.expanduser("~/Skrivebord")]
    try:
        out = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True, text=True, timeout=5).stdout.strip()
        if out:
            dirs.append(out)
    except (OSError, subprocess.SubprocessError):
        pass
    for d in dirs:
        for f in glob.glob(os.path.join(d, "*.desktop")):
            try:
                txt = open(f, errors="replace").read()
            except OSError:
                continue
            if re.search(r"^Name=Battle\.net", txt, re.M):
                m = re.search(r"^Exec=(.+)$", txt, re.M)
                if m:
                    return m.group(1).strip()
    return None


def apps():
    """Liste over programmene: nøkkel, navn, ikon, kommando (minimert) eller None, merknad, matcher."""
    trcc = _trcc()
    steam = ("/usr/bin/bazzite-steam -silent" if os.path.exists("/usr/bin/bazzite-steam") else
             "steam -silent" if shutil.which("steam") else
             "flatpak run com.valvesoftware.Steam -silent" if _flatpak("com.valvesoftware.Steam") else None)
    discord = ("flatpak run com.discordapp.Discord --start-minimized" if _flatpak("com.discordapp.Discord") else
               "discord --start-minimized" if shutil.which("discord") else None)
    solaar = ("flatpak run io.github.pwr_solaar.solaar --window=hide" if _flatpak("io.github.pwr_solaar.solaar") else
              "solaar --window=hide" if shutil.which("solaar") else None)
    openrgb = ("flatpak run org.openrgb.OpenRGB --startminimized --server --noautoconnect --profile Systemmonitor"
               if _flatpak("org.openrgb.OpenRGB") else
               "openrgb --startminimized --server --noautoconnect --profile Systemmonitor" if shutil.which("openrgb")
               else None)
    bnet = _battlenet_exec()
    me = f"python3 {os.path.join(os.path.dirname(os.path.abspath(__file__)), 'systemmonitor.py')} --hidden"
    return [
        ("systemmonitor", "Kontrollsenter", "no.waagan.Systemmonitor", me,
         "Starter skjult med ikon i systemstatusfeltet, så overlay, vifter og varsler virker fra start.",
         r"systemmonitor\.py", r"^Kontrollsenter$"),
        ("steam", "Steam", "steam", steam, "Starter i systemstatusfeltet (-silent).", r"steam", r"steam"),
        ("discord", "Discord", "com.discordapp.Discord", discord, "Starter minimert i systemstatusfeltet.",
         r"discord", r"discord"),
        ("battlenet", "Battle.net", "applications-games", f"sh -c 'sleep 15; {bnet}'" if bnet else None,
         "Starter via Lutris 15 sek etter innlogging. For å starte den minimert: Battle.net → Innstillinger → "
         "Program → «Start Battle.net minimert».", r"battle\.net|rungameid", r"battle"),
        ("solaar", "Solaar", "io.github.pwr_solaar.solaar", solaar, "Starter uten vindu (--window=hide).",
         r"solaar", r"solaar"),
        ("openrgb", "OpenRGB", "org.openrgb.OpenRGB", openrgb,
         "Starter minimert og legger inn RGB-profilen fra RGB-fanen.", r"openrgb", r"openrgb"),
        ("trcc", "TRCC (CPU-skjerm)", "trcc",
         f"sh -c '{trcc} daemon & sleep 4; {trcc} display resume'" if trcc else None,
         "Starter tjenesten uten vindu, så kjølerskjermen viser temaet ditt.", r"trcc", r"trcc"),
    ]


# Filnavn: TRCC og OpenRGB deler fil med CPU-skjerm- og RGB-fanen
OWN = {"trcc": "systemmonitor-trcc.desktop", "openrgb": "systemmonitor-openrgb.desktop"}


def own_file(key):
    return os.path.join(AUTOSTART, OWN.get(key, f"systemmonitor-autostart-{key}.desktop"))


def _entries(exec_rx, name_rx):
    """Alle oppstartsfiler i ~/.config/autostart som gjelder programmet."""
    out = []
    for f in glob.glob(os.path.join(AUTOSTART, "*.desktop")):
        try:
            txt = open(f, errors="replace").read()
        except OSError:
            continue
        head = txt.split("\n[", 1)[0]                     # bare [Desktop Entry]-delen
        ex = re.search(r"^Exec=(.*)$", head, re.M)
        nm = re.search(r"^Name=(.*)$", head, re.M)
        if (ex and re.search(exec_rx, ex.group(1), re.I)) or (nm and re.search(name_rx, nm.group(1), re.I)
                                                            and re.search(name_rx, os.path.basename(f), re.I)):
            hidden = bool(re.search(r"^Hidden=true", head, re.M | re.I)) or \
                bool(re.search(r"^X-GNOME-Autostart-enabled=false", head, re.M | re.I))
            out.append({"file": f, "exec": ex.group(1) if ex else "", "hidden": hidden})
    return out


def status(app):
    key, _n, _i, cmd, _note, exec_rx, name_rx = app
    ents = [e for e in _entries(exec_rx, name_rx)]
    active = [e for e in ents if not e["hidden"]]
    own = own_file(key)
    minimized = all(e["file"] == own or re.search(r"-silent|--start-?minimized|--window=hide|daemon|--server|--hidden",
                                                  e["exec"]) for e in active)
    return {"on": bool(active), "count": len(active), "minimized": minimized, "others": [
        e for e in active if e["file"] != own]}


def _hide(path):
    txt = open(path, errors="replace").read()
    if re.search(r"^Hidden=true", txt, re.M):
        return
    bak = path + ".bak"
    if not os.path.exists(bak):
        with open(bak, "w") as f:
            f.write(txt)
    head, sep, rest = txt.partition("\n[")
    head = head.rstrip("\n") + "\nHidden=true\n"
    with open(path, "w") as f:
        f.write(head + (("[" + rest) if sep else ""))


def enable(app):
    key, name, icon, cmd, _note, exec_rx, name_rx = app
    if not cmd:
        raise RuntimeError(f"{name} er ikke installert")
    os.makedirs(AUTOSTART, exist_ok=True)
    own = own_file(key)
    for e in _entries(exec_rx, name_rx):
        if e["file"] != own and not e["hidden"]:
            _hide(e["file"])
    with open(own, "w") as f:
        f.write("[Desktop Entry]\nType=Application\n"
                f"Name={name} (automatisk start fra Kontrollsenter)\n"
                f"Exec={cmd}\nIcon={icon}\nTerminal=false\nX-GNOME-Autostart-enabled=true\n"
                "X-KDE-autostart-after=panel\n")


def disable(app):
    key, _name, _icon, _cmd, _note, exec_rx, name_rx = app
    own = own_file(key)
    if os.path.exists(own):
        os.remove(own)
    for e in _entries(exec_rx, name_rx):
        if not e["hidden"]:
            _hide(e["file"])


# --------------------------------------------------------------------------
class AutostartPage(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(4)
        self.set_child(Adw.Clamp(maximum_size=900, child=box))
        intro = Gtk.Label(label="Velg hvilke programmer som skal starte av seg selv – minimert – når du "
                                "logger inn.", xalign=0, wrap=True)
        intro.add_css_class("dim-label")
        box.append(intro)
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.list.add_css_class("boxed-list")
        box.append(self.list)
        self.status = Gtk.Label(xalign=0, wrap=True)
        box.append(self.status)
        self.build()

    def build(self):
        while (c := self.list.get_first_child()):
            self.list.remove(c)
        self._quiet = True
        import hardware
        hw = hardware.present()
        needs = {"openrgb": "rgb", "solaar": "logitech", "trcc": "lcd"}   # bare når utstyret finnes
        for app in apps():
            key, name, icon, cmd, note, _e, _n = app
            if key in needs and not hw[needs[key]]:
                continue
            st = status(app)
            row = Gtk.Box(spacing=12)
            for side, v in (("top", 10), ("bottom", 10), ("start", 12), ("end", 12)):
                getattr(row, f"set_margin_{side}")(v)
            img = Gtk.Image.new_from_icon_name(icon)
            img.set_pixel_size(32)
            row.append(img)
            mid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            t = Gtk.Label(label=name, xalign=0)
            t.add_css_class("heading")
            mid.append(t)
            if not cmd:
                sub = "Ikke installert"
            elif st["on"] and not st["minimized"]:
                sub = "Starter med vindu nå – slå av og på igjen for å starte minimert"
            elif st["on"] and st["count"] > 1:
                sub = f"Starter {st['count']} ganger nå – slå av og på igjen for å rydde opp"
            else:
                sub = note
            d = Gtk.Label(label=sub, xalign=0, wrap=True)
            d.add_css_class("caption")
            d.add_css_class("dim-label")
            if cmd and st["on"] and (not st["minimized"] or st["count"] > 1):
                d.remove_css_class("dim-label")
                d.add_css_class("warning")
            mid.append(d)
            row.append(mid)
            sw = Gtk.Switch(active=st["on"], valign=Gtk.Align.CENTER, sensitive=bool(cmd))
            sw.connect("notify::active", self._toggled, app)
            row.append(sw)
            self.list.append(row)
        self._quiet = False

    def _toggled(self, sw, _p, app):
        if self._quiet:
            return
        try:
            (enable if sw.get_active() else disable)(app)
            self.status.set_label(f"{app[1]}: " + ("starter automatisk (minimert) ✓" if sw.get_active()
                                                    else "starter ikke automatisk lenger ✓"))
        except Exception as e:  # noqa: BLE001
            self.status.set_label(f"Feil: {e}")
        self.build()
