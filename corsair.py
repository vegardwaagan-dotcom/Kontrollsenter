"""Corsair-utstyr som OpenRGB ikke kan styre (f.eks. iCUE COMMANDER DUO) – styres med OpenLinkHub.

OpenLinkHub (github.com/jurkovic-nikola/OpenLinkHub) er et åpent Linux-program for Corsair-hubber,
AIO-er og vifter. Det kjører som tjeneste med nettside på http://127.0.0.1:27003.
Installasjon (bare når du trykker): siste utgivelse lastes ned til ~/OpenLinkHub, og installeringsskriptet
for brukerområdet kjøres i et terminalvindu (spør om passord for udev-reglene). Deretter omstart.
"""
import glob
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import threading
import urllib.request
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

import i18n  # noqa: E402

API = "http://127.0.0.1:27003"
RELEASES = "https://api.github.com/repos/jurkovic-nikola/OpenLinkHub/releases/latest"
DEST = Path.home() / "OpenLinkHub"
# Corsair-enheter OpenLinkHub støtter, men OpenRGB 1.x ikke (PID → navn)
OLH_ONLY = {"0c56": "iCUE COMMANDER DUO", "0c3f": "iCUE LINK System Hub", "0c32": "iCUE COMMANDER Core",
            "0c1c": "iCUE COMMANDER Core XT", "0c2a": "iCUE COMMANDER Core XT", "0c1d": "iCUE COMMANDER Core"}


def unsupported_devices(openrgb_names=()):
    """Corsair-enheter på USB som OpenRGB ikke fant: [(pid, navn)]."""
    seen = " ".join(openrgb_names).lower()
    out = []
    for d in glob.glob("/sys/bus/usb/devices/*"):
        try:
            if open(f"{d}/idVendor").read().strip().lower() != "1b1c":
                continue
            pid = open(f"{d}/idProduct").read().strip().lower()
            prod = open(f"{d}/product").read().strip() if os.path.exists(f"{d}/product") else ""
        except OSError:
            continue
        name = OLH_ONLY.get(pid) or prod or f"Corsair {pid}"
        key = name.lower().replace("icue", "").replace("usb", "").strip()
        if pid in OLH_ONLY and key not in seen and (pid, name) not in out:
            out.append((pid, name))
    return out


def running():
    try:
        with urllib.request.urlopen(API + "/api/devices/", timeout=2) as r:
            return r.status == 200
    except OSError:
        return False


def installed():
    """Tjenesten er satt opp (ikke bare lastet ned)."""
    return any(Path(p).exists() for p in (Path.home() / ".config/systemd/user/OpenLinkHub.service",
                                          "/etc/systemd/system/OpenLinkHub.service",
                                          "/usr/lib/systemd/system/OpenLinkHub.service",
                                          "/etc/systemd/user/OpenLinkHub.service"))


def _terminal(cmd):
    """Kjør en kommando i et synlig terminalvindu (så du ser hva som skjer og kan skrive passord)."""
    for t, args in (("ptyxis", ["--", "bash", "-c"]), ("konsole", ["-e", "bash", "-c"]),
                    ("gnome-terminal", ["--", "bash", "-c"]), ("kgx", ["--", "bash", "-c"]),
                    ("xterm", ["-e", "bash", "-c"])):
        if shutil.which(t):
            subprocess.Popen([t, *args, cmd], start_new_session=True)
            return True
    return False


def download(progress=None):
    """Last ned siste OpenLinkHub til ~/OpenLinkHub. Returnerer mappen med installeringsskriptet."""
    req = urllib.request.Request(RELEASES, headers={"Accept": "application/vnd.github+json",
                                                     "User-Agent": "Kontrollsenter"})
    with urllib.request.urlopen(req, timeout=30) as r:
        rel = json.load(r)
    assets = [a for a in rel.get("assets", []) if a["name"].endswith((".tar.gz", ".tgz"))
              and not any(x in a["name"].lower() for x in ("arm", "aarch64", "src", "source"))]
    if not assets:
        raise RuntimeError(i18n.tr("fant ingen nedlasting for Linux i siste utgivelse"))
    a = assets[0]
    tmp = Path(tempfile.mkdtemp())
    try:
        f = tmp / a["name"]
        if progress:
            progress(i18n.tr("Laster ned ") + f"{a['name']} ({a['size'] / 1e6:.0f} MB) …")
        req = urllib.request.Request(a["browser_download_url"], headers={"User-Agent": "Kontrollsenter"})
        with urllib.request.urlopen(req, timeout=120) as r, open(f, "wb") as out:
            shutil.copyfileobj(r, out)
        DEST.mkdir(exist_ok=True)
        with tarfile.open(f) as t:
            t.extractall(tmp / "x", filter="data")
        script = next(iter(sorted((tmp / "x").rglob("install-user-space.sh"))), None)
        if not script:
            raise RuntimeError(i18n.tr("pakken mangler install-user-space.sh"))
        root = script.parent
        for p in root.iterdir():                       # flytt innholdet til ~/OpenLinkHub
            target = DEST / p.name
            if target.exists():
                shutil.rmtree(target) if target.is_dir() else target.unlink()
            shutil.move(str(p), str(target))
        return DEST, rel.get("tag_name", "")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_card(page, card_box, devices):
    """Kort i RGB-fanen for Corsair-enheter som OpenRGB ikke kan styre."""
    names = ", ".join(n for _p, n in devices)
    outer, inner, _h = card_box(names, "ks-rgb-symbolic",
                                i18n.tr("Denne Corsair-enheten (vifter og ARGB-lys) støttes ikke av OpenRGB, men av "
                                        "OpenLinkHub – et åpent Linux-program for Corsair-hubber."))
    status = Gtk.Label(xalign=0, wrap=True)
    status.add_css_class("dim-label")
    row = Gtk.Box(spacing=8)
    btn = Gtk.Button()
    btn.add_css_class("suggested-action")
    row.append(btn)
    inner.append(row)
    inner.append(status)

    def refresh():
        if running():
            btn.set_label(i18n.tr("Åpne OpenLinkHub"))
            status.set_label(i18n.tr("OpenLinkHub kjører. Farger, effekter og viftefart for Corsair-enheten "
                                     "stilles inn der."))
        elif installed():
            btn.set_label(i18n.tr("Start OpenLinkHub"))
            status.set_label(i18n.tr("OpenLinkHub er installert, men kjører ikke. Har du startet PC-en på nytt "
                                     "etter installasjonen?"))
        else:
            btn.set_label(i18n.tr("Installer OpenLinkHub"))
            status.set_label(i18n.tr("Laster ned siste utgave fra GitHub til ~/OpenLinkHub og kjører "
                                     "installeringen i et terminalvindu (spør om passordet ditt). Start PC-en på "
                                     "nytt etterpå."))
        return False

    def clicked(_b):
        if running():
            subprocess.Popen(["xdg-open", API], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        if installed():
            for scope in (["--user"], []):
                if subprocess.run(["systemctl", *scope, "start", "OpenLinkHub.service"], capture_output=True,
                                  timeout=20).returncode == 0:
                    break
            GLib.timeout_add_seconds(3, refresh)
            return
        btn.set_sensitive(False)

        def work():
            try:
                d, tag = download(lambda t: GLib.idle_add(status.set_label, t))
                cmd = (f"cd {str(d)!r} && echo 'Installerer OpenLinkHub {tag} …' && ./install-user-space.sh; "
                       "echo; read -p 'Ferdig. Start PC-en på nytt etterpå. Trykk Enter for å lukke.' _")
                ok = _terminal(cmd)
                msg = (i18n.tr("Installeringen kjører i terminalvinduet. Start PC-en på nytt når den er ferdig.")
                       if ok else i18n.tr("Fant ikke noe terminalprogram. Kjør ./install-user-space.sh i ") + str(d))
            except Exception as e:  # noqa: BLE001
                msg = i18n.tr("Kunne ikke installere OpenLinkHub: ") + (str(e) or type(e).__name__)
            GLib.idle_add(lambda: (status.set_label(msg), btn.set_sensitive(True), False)[2])
        threading.Thread(target=work, daemon=True).start()
    btn.connect("clicked", clicked)
    refresh()
    return outer
