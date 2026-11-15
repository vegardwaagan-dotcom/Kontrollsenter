"""Batteri i trådløse enheter: mus og tastatur (UPower/Solaar), Bluetooth-enheter og hodesett (HeadsetControl).

devices() leser alt (tregt – kalles i bakgrunnen), cached() gir siste resultat med en gang.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import threading
import time

IS_WIN = sys.platform == "win32"
_CACHE = {"t": 0, "list": []}
_LOCK = threading.Lock()


def _upower():
    out = []
    try:
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        devs = bus.call_sync("org.freedesktop.UPower", "/org/freedesktop/UPower", "org.freedesktop.UPower",
                             "EnumerateDevices", None, None, Gio.DBusCallFlags.NONE, 3000, None).unpack()[0]
        for p in devs:
            pr = bus.call_sync("org.freedesktop.UPower", p, "org.freedesktop.DBus.Properties", "GetAll",
                               GLib.Variant("(s)", ("org.freedesktop.UPower.Device",)), None,
                               Gio.DBusCallFlags.NONE, 3000, None).unpack()[0]
            # 1 = strømadapter, 2 = laptopbatteri, 3 = UPS – resten er tilkoblede enheter
            if pr.get("Type") in (0, 1, 2, 3) or not pr.get("IsPresent", True):
                continue
            name = pr.get("Model") or pr.get("NativePath") or "Enhet"
            vendor = pr.get("Vendor") or ""
            kind = {5: "mouse", 6: "keyboard", 12: "gamepad", 17: "headset", 18: "speaker", 19: "headset"}.get(
                pr.get("Type"), "device")
            out.append({"id": p, "name": name, "pct": round(float(pr.get("Percentage", 0))), "kind": kind,
                        "charging": pr.get("State") == 1, "source": "upower",
                        "logitech": "logitech" in (name + vendor).lower()})
    except Exception:  # noqa: BLE001
        pass
    return out


def headsetcontrol_bin():
    for c in (shutil.which("headsetcontrol"), "/home/linuxbrew/.linuxbrew/bin/headsetcontrol",
              os.path.expanduser("~/.local/bin/headsetcontrol"), "/usr/local/bin/headsetcontrol",
              *glob.glob(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\*HeadsetControl*\headsetcontrol.exe"))):
        if c and os.path.isfile(c):
            return c
    return None


def _headsets():
    """Hodesett fra HeadsetControl (Logitech G PRO X 2, G733, G535, G435, G933/G935, SteelSeries, Corsair …)."""
    hc = headsetcontrol_bin()
    if not hc:
        return []
    flags = {"creationflags": 0x08000000} if IS_WIN else {}
    try:
        r = subprocess.run([hc, "-o", "json"], capture_output=True, text=True, timeout=10, **flags)
        data = json.loads(r.stdout or "{}")
    except (OSError, subprocess.SubprocessError, ValueError):
        data = None
    out = []
    if isinstance(data, dict) and "devices" in data:
        for i, d in enumerate(data.get("devices") or []):
            b = d.get("battery") or {}
            st = str(b.get("status", ""))
            if "UNAVAILABLE" in st or b.get("level") is None:
                lvl, avail = None, False                       # hodesettet er av / ikke koblet til mottakeren
            else:
                lvl, avail = int(b.get("level")), True
            name = d.get("device") or d.get("product") or "Hodesett"
            vendor = d.get("vendor") or ""
            out.append({"id": f"hc{i}", "name": name, "pct": lvl, "kind": "headset", "available": avail,
                        "charging": "CHARGING" in st, "source": "headsetcontrol",
                        "logitech": "logitech" in (name + vendor).lower()})
        return out
    try:                                                       # eldre HeadsetControl: -b -c gir bare et tall
        r = subprocess.run([hc, "-b", "-c"], capture_output=True, text=True, timeout=10, **flags)
        v = int(r.stdout.strip())
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    if v == -2:
        return [{"id": "hc0", "name": "Hodesett", "pct": None, "kind": "headset", "available": False,
                 "charging": False, "source": "headsetcontrol", "logitech": True}]
    return [{"id": "hc0", "name": "Hodesett", "pct": None if v < 0 else v, "kind": "headset", "available": True,
             "charging": v == -1, "source": "headsetcontrol", "logitech": True}]


def devices():
    out = ([] if IS_WIN else _upower()) + _headsets()
    with _LOCK:
        _CACHE.update(t=time.time(), list=out)
    return out


def cached(max_age=90):
    """Siste kjente liste; starter en ny lesing i bakgrunnen når den er gammel."""
    if time.time() - _CACHE["t"] > max_age and not getattr(cached, "busy", False):
        cached.busy = True

        def work():
            try:
                devices()
            finally:
                cached.busy = False
        threading.Thread(target=work, daemon=True).start()
    return list(_CACHE["list"])


ICON = {"mouse": "🖱️", "keyboard": "⌨️", "headset": "🎧", "gamepad": "🎮", "speaker": "🔊"}


def label(d):
    if d.get("pct") is None:
        return "av / ikke tilkoblet" if not d.get("charging") else "lader"
    return f"{d['pct']} %" + (" ⚡" if d.get("charging") else "")


def install_headsetcontrol():
    """Installer HeadsetControl (Homebrew) og regelen som gir tilgang til hodesettet uten root. Returnerer (ok, tekst)."""
    if IS_WIN:
        return False, "Last ned HeadsetControl for Windows fra github.com/Sapd/HeadsetControl/releases"
    hc = headsetcontrol_bin()
    if not hc:
        brew = shutil.which("brew") or "/home/linuxbrew/.linuxbrew/bin/brew"
        if not os.path.exists(brew):
            return False, "Fant ikke Homebrew – kjør «ujust install-brew» eller installer HeadsetControl selv"
        r = subprocess.run([brew, "install", "headsetcontrol"], capture_output=True, text=True, timeout=900)
        hc = headsetcontrol_bin()
        if not hc:
            return False, "Installasjonen feilet: " + (r.stderr or r.stdout).strip()[-300:]
    rules = subprocess.run([hc, "-u"], capture_output=True, text=True, timeout=20).stdout
    if "SUBSYSTEM" not in rules:
        return True, "HeadsetControl er installert"
    import tempfile
    d = tempfile.mkdtemp()
    f = os.path.join(d, "70-headsets.rules")
    with open(f, "w") as fh:
        fh.write(rules)
    os.chmod(d, 0o755)
    os.chmod(f, 0o644)
    r = subprocess.run(["pkexec", "sh", "-c", 'install -m 644 "$1" /etc/udev/rules.d/70-headsets.rules && '
                        "udevadm control --reload-rules && udevadm trigger", "sh", f],
                       capture_output=True, text=True, timeout=300)
    shutil.rmtree(d, ignore_errors=True)
    if r.returncode != 0:
        return False, "HeadsetControl er installert, men tilgangsregelen ble ikke lagt inn (avbrutt?)"
    devices()
    return True, "HeadsetControl er installert ✓ – slå hodesettet av og på hvis batteriet ikke vises"
