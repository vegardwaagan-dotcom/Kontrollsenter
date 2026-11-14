"""Feilsøkingsrapport: alt som trengs for å finne ut hvorfor RGB, vifter eller Logitech ikke virker på en PC.

Rapporten legges på NAS-en (Kontrollsenter\\Diagnose\\<PC>.txt) når PC-en er på hjemmenettet, og kan
kopieres fra Verktøy. Den inneholder maskinvare, drivere og programmer – ingen personlige filer eller passord.
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

APP_DIR = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.expanduser("~/.config/systemmonitor/diagnose.json")
REMOTE = "Diagnose"


def _run(cmd, timeout=20):
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        if sys.platform == "win32":                       # konsollens tegnkode, ikke UTF-8
            import winsupport
            return (winsupport.decode(r.stdout) + winsupport.decode(r.stderr)).strip()
        return (r.stdout + r.stderr).decode("utf-8", "replace").strip()
    except (OSError, subprocess.SubprocessError) as e:
        return f"({e})"


def _read(p):
    try:
        return Path(p).read_text(errors="replace").strip()
    except OSError:
        return ""


def _section(title, body):
    return f"\n===== {title} =====\n{body.strip() if body else '(tomt)'}\n"


def usb_devices():
    out = []
    for d in sorted(glob.glob("/sys/bus/usb/devices/*")):
        v, p = _read(f"{d}/idVendor"), _read(f"{d}/idProduct")
        if v and v != "1d6b":
            out.append(f"{v}:{p}  {_read(f'{d}/manufacturer')} | {_read(f'{d}/product')}")
    return "\n".join(sorted(set(out)))


def hid_devices():
    out = []
    for d in sorted(glob.glob("/sys/bus/hid/devices/*")):
        name = _read(f"{d}/uevent")
        m = re.search(r"HID_NAME=(.*)", name)
        drv = os.path.basename(os.path.realpath(f"{d}/driver")) if os.path.exists(f"{d}/driver") else "-"
        out.append(f"{os.path.basename(d)}  driver={drv}  {m.group(1) if m else ''}")
    return "\n".join(out)


def hwmon():
    out = []
    for h in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
        pwms = len(glob.glob(f"{h}/pwm[0-9]"))
        fans = [f"{os.path.basename(f)}={_read(f)}" for f in sorted(glob.glob(f"{h}/fan*_input"))]
        out.append(f"{os.path.basename(h)}: {_read(h + '/name')}  pwm={pwms}  {' '.join(fans)}")
    return "\n".join(out)


def openrgb_devices():
    """Enheter OpenRGB ser – via kjørende tjeneste, ellers kommandolinja."""
    import sys
    sys.path.insert(0, os.path.join(APP_DIR, "vendor"))
    try:
        from openrgb import OpenRGBClient
        c = OpenRGBClient("127.0.0.1", 6742, "Kontrollsenter-diagnose")
        lines = [f"{d.type.name:10} {d.name}  ({len(d.leds)} LED, {len(d.zones)} soner, moduser: "
                 f"{', '.join(m.name for m in d.modes[:8])})" for d in c.devices]
        c.disconnect()
        return "Fra OpenRGB-tjenesten:\n" + ("\n".join(lines) or "(ingen enheter)")
    except Exception as e:  # noqa: BLE001
        first = f"Tjenesten svarer ikke ({e}).\n"
    if shutil.which("flatpak") and "org.openrgb.OpenRGB" in _run(["flatpak", "list", "--app", "--columns=application"]):
        return first + "Fra kommandolinja:\n" + _run(["flatpak", "run", "org.openrgb.OpenRGB", "--noautoconnect",
                                                      "--list-devices"], 90)[-6000:]
    if shutil.which("openrgb"):
        return first + _run(["openrgb", "--noautoconnect", "--list-devices"], 90)[-6000:]
    return first + "OpenRGB er ikke installert."


def windows_report():
    import platform
    import sys
    import applog
    parts = [f"Kontrollsenter {applog.RUNNING} (Windows) – feilsøkingsrapport {time.strftime('%Y-%m-%d %H:%M')}",
             f"PC: {platform.node()}"]
    bios = []
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\BIOS") as k:
            for name in ("SystemManufacturer", "SystemProductName", "BaseBoardManufacturer", "BaseBoardProduct",
                         "BIOSVersion", "BIOSReleaseDate"):
                try:
                    bios.append(f"{name}: {winreg.QueryValueEx(k, name)[0]}")
                except OSError:
                    pass
    except OSError as e:
        bios.append(str(e))
    parts.append(_section("Maskin", "\n".join(bios)))
    parts.append(_section("System", f"{platform.platform()}\nPython {sys.version.split()[0]} ({sys.executable})"))
    try:
        import gi
        from gi.repository import Adw, Gtk
        parts.append(_section("GTK", f"GTK {Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}"
                                     f" · libadwaita {Adw.get_major_version()}.{Adw.get_minor_version()}"
                                     f" · PyGObject {gi.__version__}"))
    except Exception as e:  # noqa: BLE001
        parts.append(_section("GTK", str(e)))
    try:
        import psutil
        vm = psutil.virtual_memory()
        parts.append(_section("CPU og minne", f"{psutil.cpu_count()} tråder · {vm.total / 2**30:.1f} GB RAM · "
                                              f"last {psutil.cpu_percent(0.5)} %"))
    except Exception as e:  # noqa: BLE001
        parts.append(_section("CPU og minne", f"psutil mangler: {e}"))
    try:
        from sensors_win import Lhm
        ss = Lhm.sensors()
        parts.append(_section("LibreHardwareMonitor", ("svarer ✓" if Lhm.ok else "svarer IKKE på 127.0.0.1:8085") +
                              "\n" + "\n".join(f"{x['type']:12} {x['id']:45} {x['name']}: {x['value']}"
                                                for x in ss)[:20000]))
    except Exception as e:  # noqa: BLE001
        parts.append(_section("LibreHardwareMonitor", str(e)))
    try:
        import winsupport
        lines = []
        for title, cmd in (("Prosess", ["tasklist", "/fi", "imagename eq LibreHardwareMonitor.exe"]),
                           ("Oppgave", ["schtasks", "/query", "/tn", "Kontrollsenter - LibreHardwareMonitor", "/v",
                                        "/fo", "list"]),
                           ("Port 8085", ["netstat", "-ano", "-p", "tcp"]),
                           ("PawnIO", ["sc", "query", "PawnIO"])):
            code, out = winsupport.run(cmd, 20)
            if title == "Port 8085":
                out = "\n".join(ln for ln in out.splitlines() if ":8085" in ln) or "ingen lytter på 8085"
            lines.append(f"--- {title} ---\n{out.strip()[:2500]}")
        import glob as _g
        cfg = _g.glob(r"C:\Program Files\LibreHardwareMonitor\LibreHardwareMonitor.config")
        lines.append("--- config ---\n" + (open(cfg[0], encoding="utf-8", errors="replace").read()[:1500]
                                            if cfg else "mangler"))
        parts.append(_section("LibreHardwareMonitor-status", "\n".join(lines)))
    except Exception as e:  # noqa: BLE001
        parts.append(_section("LibreHardwareMonitor-status", str(e)))
    try:
        import msi as _msi
        if _msi.is_msi():
            import winmsi
            parts.append(_section("MSI-styring", winmsi.diagnose()))
    except Exception as e:  # noqa: BLE001
        parts.append(_section("MSI-styring", str(e)))
    try:
        from sensors import NvidiaReader
        n = NvidiaReader()
        n.poll()
        time.sleep(1.2)
        n.poll()
        parts.append(_section("NVIDIA", f"tilgjengelig: {n.available} · {json.dumps(n.data, default=str)[:600]}"))
    except Exception as e:  # noqa: BLE001
        parts.append(_section("NVIDIA", str(e)))
    try:
        import winsupport
        parts.append(_section("Strømplan og oppstart", f"aktiv: {winsupport.active_plan()}\n"
                                                       f"autostart: {winsupport.autostart_get('Kontrollsenter')}"))
    except Exception as e:  # noqa: BLE001
        parts.append(_section("Strømplan og oppstart", str(e)))
    parts.append(_section("Kontrollsenter-logg (siste linjer)", applog.tail(150)))
    return "\n".join(parts)


def report():
    import sys
    if sys.platform == "win32":
        return windows_report()
    import applog
    parts = [f"Kontrollsenter {applog.RUNNING} – feilsøkingsrapport {time.strftime('%Y-%m-%d %H:%M')}",
             f"PC: {os.uname().nodename}"]
    dmi = "\n".join(f"{k}: {_read('/sys/class/dmi/id/' + k)}" for k in
                    ("sys_vendor", "product_name", "board_vendor", "board_name", "bios_version", "bios_date",
                     "chassis_type"))
    parts.append(_section("Maskin", dmi))
    parts.append(_section("System", f"{_read('/etc/os-release').splitlines()[0] if _read('/etc/os-release') else ''}\n"
                                    f"kjerne {os.uname().release}\ncmdline: {_read('/proc/cmdline')}"))
    try:
        import hardware
        parts.append(_section("Funnet utstyr (hardware.py)", json.dumps(hardware.present())))
    except Exception as e:  # noqa: BLE001
        parts.append(_section("Funnet utstyr", str(e)))
    parts.append(_section("USB-enheter", usb_devices()))
    parts.append(_section("HID-enheter (tastatur, mus, RGB)", hid_devices()))
    parts.append(_section("Sensorer og vifter (hwmon)", hwmon()))
    mods = _run(["lsmod"])
    parts.append(_section("Drivere", "\n".join(l for l in mods.splitlines() if re.match(
        r"(nct67|it87|asus|i2c|razer|hid_logitech|hid_razer|corsair|openrazer|ee1004|spd5118|nvidia\b)", l))))
    klog = _run(["journalctl", "-k", "-b", "--no-pager", "-o", "cat"], 30).splitlines()
    pick = [ln for ln in klog if re.search(r"nct67|it87|conflict|i2c|smbus|razer|corsair|logitech|hidpp|"
                                            r"asus.*(wmi|ec)|ACPI Warning", ln, re.I)]
    parts.append(_section("Kjernemeldinger (utvalg)", "\n".join(pick[-120:])))
    parts.append(_section("i2c (RAM-RGB)", _run(["ls", "-l", *glob.glob("/dev/i2c-*")]) if glob.glob("/dev/i2c-*")
                          else "ingen /dev/i2c-* (i2c-dev ikke lastet?)"))
    rules = [f for d in ("/etc/udev/rules.d", "/usr/lib/udev/rules.d") for f in glob.glob(f"{d}/*")
             if re.search(r"openrgb|logitech|razer|corsair|trcc|ratbag", f, re.I)]
    parts.append(_section("udev-regler", "\n".join(rules)))
    parts.append(_section("Grupper for brukeren", _run(["id"])))
    fl = _run(["flatpak", "list", "--app", "--columns=application,version"]) if shutil.which("flatpak") else ""
    parts.append(_section("Flatpak (relevante)", "\n".join(l for l in fl.splitlines()
                                                           if re.search(r"openrgb|solaar|piper", l, re.I))))
    parts.append(_section("OpenRGB", openrgb_devices()))
    parts.append(_section("ratbagd (Logitech/gaming-mus)",
                          _run(["systemctl", "is-active", "ratbagd"]) + "\n" +
                          (_run(["ratbagctl", "list"]) if shutil.which("ratbagctl") else "ratbagctl mangler")))
    if shutil.which("flatpak") and "solaar" in fl:
        parts.append(_section("Solaar (Logitech)", _run(["flatpak", "run", "--command=solaar",
                                                         "io.github.pwr_solaar.solaar", "show"], 40)[-5000:]))
    fan_ok = os.path.exists("/usr/local/bin/systemmonitor-fan")
    parts.append(_section("Kontrollsenter-oppsett",
                          f"viftehjelper: {'ja' if fan_ok else 'nei'}\n"
                          f"gpu-hjelper: {'ja' if os.path.exists('/usr/local/bin/systemmonitor-gpu-power') else 'nei'}\n"
                          f"modules-load: {', '.join(glob.glob('/etc/modules-load.d/*systemmonitor*'))}"))
    parts.append(_section("Kontrollsenter-logg (siste linjer)", applog.tail(120)
                          if hasattr(applog, "tail") else ""))
    return "\n".join(parts)


def upload(text):
    import lanupdate as L
    if os.environ.get("SYSTEMMONITOR_APP_ID") or not L.on_lan():
        return False
    import savegames
    tmp = Path(tempfile.mkdtemp())
    try:
        f = tmp / f"{savegames.pc_name()}.txt"
        f.write_text(text, encoding="utf-8")
        _host, share, folder = L._split()
        L.smb_mkdir(f"{folder}/{REMOTE}")
        L._smb(f'cd "{REMOTE}"; put "{f}" "{f.name}"', 60)
        return True
    except Exception:  # noqa: BLE001
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def auto_upload():
    """Én gang per versjon og døgn, i bakgrunnen (kalles fra programmet ved oppstart)."""
    import applog
    try:
        st = json.loads(Path(STATE).read_text())
    except (OSError, ValueError):
        st = {}
    key = f"{applog.RUNNING}-{time.strftime('%Y-%m-%d')}"
    if st.get("sent") == key or not st.get("enabled", True):
        return

    def work():
        if upload(report()):
            st["sent"] = key
            os.makedirs(os.path.dirname(STATE), exist_ok=True)
            Path(STATE).write_text(json.dumps(st))
    threading.Thread(target=work, daemon=True).start()
