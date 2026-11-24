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
            st = pr.get("State")                  # 1 = lader, 4 = fulladet, 5 = venter på lading
            out.append({"id": p, "name": name, "pct": round(float(pr.get("Percentage", 0))), "kind": kind,
                        "charging": st == 1, "full": st == 4, "plugged": st in (1, 4, 5), "source": "upower",
                        "native": os.path.basename(str(pr.get("NativePath") or "")),
                        "logitech": "logitech" in (name + vendor).lower()})
    except Exception:  # noqa: BLE001
        pass
    return out


_HCB = {"t": 0, "v": None}


def headsetcontrol_bin():
    """Stien til HeadsetControl (husket et minutt – søket i WinGet-mappen er tregt på Windows)."""
    if time.time() - _HCB["t"] < 60:
        return _HCB["v"]
    _HCB.update(t=time.time(), v=_headsetcontrol_bin())
    return _HCB["v"]


def _headsetcontrol_bin():
    for c in (shutil.which("headsetcontrol"), "/home/linuxbrew/.linuxbrew/bin/headsetcontrol",
              os.path.expanduser("~/.local/bin/headsetcontrol"), "/usr/local/bin/headsetcontrol",
              os.path.expandvars(r"%LOCALAPPDATA%\Kontrollsenter\headsetcontrol.exe"),
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
                if lvl < 0:                                    # noen hodesett sier ikke nivået mens de lader
                    lvl = None
            name = d.get("device") or d.get("product") or "Hodesett"
            vendor = d.get("vendor") or ""
            out.append({"id": f"hc{i}", "name": name, "pct": lvl, "kind": "headset", "available": avail,
                        "charging": "CHARGING" in st, "full": "FULL" in st, "plugged": "CHARGING" in st or "FULL" in st,
                        "source": "headsetcontrol",
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


# --- Logitech-mus/-tastatur i ladekabelen ------------------------------------------------------------
# Med kabel snakker musa direkte over USB i stedet for via mottakeren. Da forsvinner den fra UPower, mens kjernen
# beholder siste kjente nivå (status «Unknown»). Solaar kan lese den over kabelen (nivå + «recharging»).
SOLAAR_CMD = ["flatpak", "run", "--command=python3", "io.github.pwr_solaar.solaar", "-"]
_SOL = {"t": 0, "list": []}


def _uevent(path):
    out = {}
    try:
        with open(os.path.join(path, "uevent")) as f:
            for ln in f:
                k, _, v = ln.strip().partition("=")
                out[k] = v
    except OSError:
        pass
    return out


def _usb_products():
    names = set()
    for d in glob.glob("/sys/bus/usb/devices/*"):
        try:
            with open(os.path.join(d, "idVendor")) as f:
                if f.read().strip() != "046d":
                    continue
            with open(os.path.join(d, "product")) as f:
                names.add(f.read().strip())
        except OSError:
            continue
    return names


def _solaar_installed():
    return any(os.path.isdir(os.path.join(b, "app", "io.github.pwr_solaar.solaar"))
               for b in ("/var/lib/flatpak", os.path.expanduser("~/.local/share/flatpak")))


def _solaar_battery(max_age=6):
    if time.time() - _SOL["t"] < max_age or not _solaar_installed():
        return _SOL["list"]
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "logi_solaar.py")) as f:
            script = f.read()
        r = subprocess.run(SOLAAR_CMD + ["battery"], input=script, capture_output=True, text=True, timeout=30)
        lines = [ln for ln in r.stdout.splitlines() if ln.startswith("[")]
        _SOL["list"] = json.loads(lines[-1]) if lines else []
    except (OSError, subprocess.SubprocessError, ValueError):
        _SOL["list"] = []
    _SOL["t"] = time.time()
    return _SOL["list"]


def _sysfs_devices():
    """Trådløse enheter rett fra kjernen (/sys/class/power_supply, scope=Device). UPower mister av og til en mus
    når laderen settes inn eller tas ut, men kjernen har den fortsatt – med «Charging»/«Full»."""
    if IS_WIN:
        return []
    prods = _usb_products()
    out = []
    sol = None
    for p in sorted(glob.glob("/sys/class/power_supply/*")):
        ue = _uevent(p)
        if ue.get("POWER_SUPPLY_TYPE") != "Battery" or ue.get("POWER_SUPPLY_SCOPE") != "Device":
            continue
        model = ue.get("POWER_SUPPLY_MODEL_NAME") or os.path.basename(p)
        try:
            pct = int(ue.get("POWER_SUPPLY_CAPACITY"))
        except (TypeError, ValueError):
            pct = None
        st = (ue.get("POWER_SUPPLY_STATUS") or "").lower()
        wired = model in prods                      # i ladekabelen: koblet direkte med USB
        if wired:
            if sol is None:
                sol = _solaar_battery()
            x = next((x for x in sol if x.get("name") == model), None) or {}
            if x.get("pct") is not None:
                pct = x["pct"]
            st = (x.get("status") or st).lower()
        full = "full" in st
        charging = "charg" in st and "discharg" not in st or (wired and not full)
        low = model.lower()
        kind = "keyboard" if "keyboard" in low or low.startswith(("g9", "g7", "g8", "k")) else \
            "headset" if "headset" in low else "mouse"
        out.append({"id": "sys:" + os.path.basename(p), "native": os.path.basename(p), "name": model, "pct": pct,
                    "kind": kind,
                    "charging": bool(charging), "full": full, "plugged": bool(charging or full),
                    "source": "sysfs", "logitech": "logitech" in (ue.get("POWER_SUPPLY_MANUFACTURER") or "").lower()
                    or os.path.basename(p).startswith("hidpp")})
    return out


def _merge(up, sysfs):
    """UPower først; kjernens oppføring fyller inn det UPower mangler. Lading fra kjernen vinner (den er raskest)."""
    by = {d["native"]: d for d in sysfs}
    out = []
    for d in up:
        k = by.pop(d.get("native"), None)
        if k and (k["charging"] or k["full"]) and not (d.get("charging") or d.get("full")):
            d = {**d, "charging": k["charging"], "full": k["full"], "plugged": True,
                 "pct": k["pct"] if k["pct"] is not None else d["pct"]}
        out.append(d)
    return out + list(by.values())


def devices():
    out = ([] if IS_WIN else _merge(_upower(), _sysfs_devices())) + _headsets()
    with _LOCK:
        _CACHE.update(t=time.time(), list=out)
    return out


_LISTENERS = []
_WATCH = {"on": False}


def _sig(lst):
    return [(d.get("id"), d.get("pct"), d.get("charging"), d.get("full")) for d in lst]


def _changed():
    from gi.repository import GLib
    for fn in list(_LISTENERS):
        GLib.idle_add(lambda f=fn: f() and False)


_REF = {"busy": False, "again": False}


def _refresh_now():
    """Les UPower-enhetene på nytt i bakgrunnen (maks én om gangen) og si fra hvis noe endret seg."""
    if _REF["busy"]:
        _REF["again"] = True
        return

    def work():
        try:
            while True:
                _REF["again"] = False
                up = [] if IS_WIN else _merge(_upower(), _sysfs_devices())
                with _LOCK:
                    old = _CACHE["list"]
                    new = up + [d for d in old if d.get("source") == "headsetcontrol"]
                    changed = _sig(old) != _sig(new)
                    _CACHE["list"] = new
                    _CACHE["t"] = max(_CACHE["t"], time.time() - 15)
                if changed:
                    _changed()
                if not _REF["again"]:
                    break
                time.sleep(0.3)
        finally:
            _REF["busy"] = False
    _REF["busy"] = True
    threading.Thread(target=work, daemon=True).start()


def listen(fn):
    """fn() kalles (i GTK-tråden) med en gang batteriene endrer seg. Starter overvåkingen første gang."""
    if fn not in _LISTENERS:
        _LISTENERS.append(fn)
    start_watch()


def start_watch():
    """UPower sier fra med en gang en enhet begynner/slutter å lade (D-Bus-signal). Hodesett via HeadsetControl
    har ingen signaler, så de sjekkes hvert 4. sekund. Må kalles fra GTK-tråden."""
    if _WATCH["on"]:
        return
    _WATCH["on"] = True
    if not IS_WIN:
        try:
            from gi.repository import Gio
            bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            cb = lambda *_a: _refresh_now()  # noqa: E731
            bus.signal_subscribe("org.freedesktop.UPower", "org.freedesktop.DBus.Properties", "PropertiesChanged",
                                 None, "org.freedesktop.UPower.Device", Gio.DBusSignalFlags.NONE, cb)
            for sig in ("DeviceAdded", "DeviceRemoved"):
                bus.signal_subscribe("org.freedesktop.UPower", "org.freedesktop.UPower", sig, None, None,
                                     Gio.DBusSignalFlags.NONE, cb)
            _WATCH["bus"] = bus
        except Exception:  # noqa: BLE001
            pass

    def headset_loop():
        n = 0
        while True:
            time.sleep(4)
            n += 1
            if not IS_WIN:
                _refresh_now()                       # kjernen/UPower: lader satt inn eller tatt ut
            if not headsetcontrol_bin():
                continue
            try:
                hs = _headsets()
            except Exception:  # noqa: BLE001
                continue
            with _LOCK:
                old = _CACHE["list"]
                new = [d for d in old if d.get("source") != "headsetcontrol"] + hs
                changed = _sig([d for d in old if d.get("source") == "headsetcontrol"]) != _sig(hs)
                _CACHE["list"] = new
            if changed:
                _changed()
    threading.Thread(target=headset_loop, daemon=True).start()
    _refresh_now()


def cached(max_age=20):
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
    """«⚡ Lader · 64 %», «🔌 Fulladet · 100 %», «64 %» eller «av / ikke tilkoblet»."""
    p = d.get("pct")
    if d.get("charging"):
        return "⚡ Lader" + (f" · {p} %" if p is not None else "")
    if d.get("full"):
        return "🔌 Fulladet" + (f" · {p} %" if p is not None else "")
    if p is None:
        return "av / ikke tilkoblet"
    return f"{p} %"


def charge_icon(d):
    """Eget ikon (finnes på både Linux og Windows): lyn når enheten lader, støpsel når den er fulladet."""
    if d.get("charging"):
        return "ks-charging-symbolic"
    if d.get("full"):
        return "ks-plugged-symbolic"
    return None


RELEASES = "https://api.github.com/repos/Sapd/HeadsetControl/releases/latest"


def _download_headsetcontrol():
    """Hent ferdigbygd HeadsetControl fra prosjektets GitHub-side: ~/.local/bin/headsetcontrol (Linux) eller
    %LOCALAPPDATA%\\Kontrollsenter\\headsetcontrol.exe (Windows). Returnerer stien."""
    import io
    import urllib.request
    import zipfile
    req = urllib.request.Request(RELEASES, headers={"User-Agent": "Kontrollsenter",
                                                    "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        rel = json.load(r)
    want = "headsetcontrol-windows-x86_64.exe" if IS_WIN else "headsetcontrol-linux-x86_64.zip"
    url = next((a["browser_download_url"] for a in rel.get("assets", []) if a.get("name") == want), None)
    if not url:
        raise RuntimeError(f"fant ikke {want} i siste versjon ({rel.get('tag_name')})")
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Kontrollsenter"}),
                                timeout=120) as r:
        data = r.read()
    if IS_WIN:
        dest = os.path.expandvars(r"%LOCALAPPDATA%\Kontrollsenter\headsetcontrol.exe")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(data)
        return dest
    dest = os.path.expanduser("~/.local/bin/headsetcontrol")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        name = next((n for n in z.namelist() if os.path.basename(n) == "headsetcontrol"), None)
        if not name:
            raise RuntimeError("zip-fila mangler headsetcontrol")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest + ".ny", "wb") as f:
            f.write(z.read(name))
    os.chmod(dest + ".ny", 0o755)
    os.replace(dest + ".ny", dest)
    return dest


def install_headsetcontrol():
    """Installer HeadsetControl (ferdigbygd fra GitHub, ellers Homebrew) og regelen som gir tilgang til hodesettet uten root. Returnerer (ok, tekst)."""
    hc = headsetcontrol_bin()
    if not hc:
        err = ""
        try:
            hc = _download_headsetcontrol()
        except Exception as e:  # noqa: BLE001
            err = str(e)
        if not hc and not IS_WIN:                     # reserve: Homebrew (har ikke alltid pakken)
            brew = shutil.which("brew") or "/home/linuxbrew/.linuxbrew/bin/brew"
            if os.path.exists(brew):
                r = subprocess.run([brew, "install", "headsetcontrol"], capture_output=True, text=True, timeout=900)
                hc = headsetcontrol_bin()
                err = err or (r.stderr or r.stdout).strip()[-200:]
        if not hc:
            return False, "Installasjonen feilet: " + (err or "ukjent feil")
    if IS_WIN:
        devices()
        return True, "HeadsetControl er installert ✓ – slå hodesettet av og på hvis batteriet ikke vises"
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
