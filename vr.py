"""VR med Meta Quest 3 gjennom Steam og SteamVR – trådløst og med kabel, på Linux og Windows.

Beste oppsett per system:
  Linux   trådløst: ALVR → SteamVR            kabel: ALVR over USB (adb) → SteamVR
  Windows trådløst: Steam Link (på Questen)    kabel: Meta Quest Link (Meta Horizon Link) → SteamVR
          (ALVR virker også på Windows, som reserve)

checks() går gjennom alt som trengs og sier hva som mangler; fix(key) retter det som kan rettes automatisk
(installerer, registrerer driveren, åpner brannmuren, installerer ALVR på Questen, setter OpenXR …).
Det som må gjøres med hendene (kabel, utviklermodus, «Tillat USB-feilsøking» i brillene) forklares.
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile

IS_WIN = sys.platform == "win32"
DATA = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Kontrollsenter") if IS_WIN else \
    os.path.expanduser("~/.local/share/systemmonitor")
ALVR_DIR = os.path.join(DATA, "alvr")
PT_DIR = os.path.join(DATA, "platform-tools")
CFG = os.path.expanduser("~/.config/systemmonitor/vr.json")
STEAMVR_APPID = "250820"
UA = {"User-Agent": "Kontrollsenter"}
META_LINK_URL = "https://www.oculus.com/download_app/?id=1582076955407037"   # Meta Horizon Link (offisiell)
QUEST_VID = "2833"


def _run(cmd, t=30):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=t,
                           **({"creationflags": 0x08000000} if IS_WIN else {}))
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


def cfg():
    try:
        with open(CFG) as f:
            c = json.load(f)
    except (OSError, ValueError):
        c = {}
    return {"mode": "wireless", "keepalive": True, **c}


def save_cfg(**kw):
    c = cfg()
    c.update(kw)
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    with open(CFG, "w") as f:
        json.dump(c, f, indent=1)


# --------------------------------------------------------------------------
# Steam og SteamVR
# --------------------------------------------------------------------------
def steam_ok():
    import apps
    return apps.installed("steam", 5)


def steamvr_dir():
    try:
        import games
        g = next((x for x in games.installed_games() if x["appid"] == STEAMVR_APPID), None)
        if g and g.get("dir") and os.path.isdir(g["dir"]):
            return g["dir"]
        if games.STEAM and (games.STEAM / "steamapps/common/SteamVR/bin").is_dir():
            return str(games.STEAM / "steamapps/common/SteamVR")
    except Exception:  # noqa: BLE001
        pass
    return None


def _steam_uri(uri):
    if IS_WIN:
        os.startfile(uri)  # noqa: S606
    else:
        from gi.repository import Gio
        Gio.AppInfo.launch_default_for_uri(uri, None)


def running(name):
    try:
        import psutil
        n = name.lower()
        return any((p.info.get("name") or "").lower().startswith(n) for p in psutil.process_iter(["name"]))
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------
# adb (Android-verktøyene – for å snakke med Questen over USB)
# --------------------------------------------------------------------------
def adb():
    p = os.path.join(PT_DIR, "adb.exe" if IS_WIN else "adb")
    if os.path.exists(p):
        return p
    return shutil.which("adb")


def install_adb():
    url = ("https://dl.google.com/android/repository/platform-tools-latest-" +
           ("windows" if IS_WIN else "linux") + ".zip")
    tmp = tempfile.mkdtemp()
    import progress as P
    try:
        with P.task("Installerer Android-verktøy (adb)", "", "adb er installert") as pt:
            z = os.path.join(tmp, "pt.zip")
            P.download(url, z, pt.sub(0, 0.9), UA)
            pt.set(0.95, "Pakker ut …")
        with zipfile.ZipFile(z) as zf:
            zf.extractall(DATA)                  # → DATA/platform-tools/
        if not IS_WIN:
            for f in ("adb", "fastboot"):
                p = os.path.join(PT_DIR, f)
                if os.path.exists(p):
                    os.chmod(p, 0o755)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return "Android-verktøyene (adb) er installert ✓"


def quest():
    """{"state": "none"|"unauthorized"|"device"|"offline", "serial", "usb": bool} for Questen."""
    usb = _quest_usb()
    a = adb()
    if not a:
        return {"state": "none" if not usb else "noadb", "usb": usb}
    _c, out = _run([a, "devices", "-l"], 15)
    for ln in out.splitlines()[1:]:
        p = ln.split()
        if len(p) >= 2 and ("quest" in ln.lower() or "eureka" in ln.lower() or "hollywood" in ln.lower()
                            or "seacliff" in ln.lower() or p[1] in ("unauthorized", "device", "offline")):
            return {"state": p[1], "serial": p[0], "usb": True, "model": next((x.split(":", 1)[1] for x in p
                                                                               if x.startswith("model:")), "")}
    return {"state": "none", "usb": usb}


def _quest_usb():
    if IS_WIN:
        _c, out = _run(["powershell", "-NoProfile", "-Command",
                        f"(Get-PnpDevice -PresentOnly | Where-Object InstanceId -like '*VID_{QUEST_VID}*').Count"], 20)
        try:
            return int(out.strip() or 0) > 0
        except ValueError:
            return False
    for d in glob.glob("/sys/bus/usb/devices/*/idVendor"):
        try:
            if open(d).read().strip() == QUEST_VID:
                return True
        except OSError:
            continue
    return False


def _adb_q(*args, t=60):
    q = quest()
    if q["state"] != "device":
        raise RuntimeError("Questen er ikke koblet til med USB-feilsøking godkjent")
    return _run([adb(), "-s", q["serial"], *args], t)


def quest_packages():
    code, out = _adb_q("shell", "pm", "list", "packages", t=20)
    return [ln.split(":", 1)[1].strip() for ln in out.splitlines() if ln.startswith("package:")]


def alvr_client_pkg():
    try:
        return next((p for p in quest_packages() if "alvr" in p.lower()), None)
    except RuntimeError:
        return None


def quest_wifi_mhz():
    try:
        _c, out = _adb_q("shell", "dumpsys", "wifi", t=20)
    except RuntimeError:
        return None
    m = re.search(r"mWifiInfo.*?Frequency: (\d+)MHz", out) or re.search(r"Frequency: (\d+)MHz", out)
    return int(m.group(1)) if m else None


# --------------------------------------------------------------------------
# ALVR
# --------------------------------------------------------------------------
def _latest_alvr():
    with urllib.request.urlopen(urllib.request.Request("https://api.github.com/repos/alvr-org/ALVR/releases/latest",
                                                       headers=UA), timeout=20) as r:
        d = json.load(r)
    return d["tag_name"], {a["name"]: a["browser_download_url"] for a in d.get("assets", [])}


def alvr_root():
    """Mappen med ALVR-streameren (dashboard + SteamVR-driver), eller None."""
    pat = "alvr_streamer_windows" if IS_WIN else "alvr_streamer_linux"
    p = os.path.join(ALVR_DIR, pat)
    return p if os.path.isdir(p) else None


def alvr_dashboard():
    r = alvr_root()
    if not r:
        return None
    p = os.path.join(r, "ALVR Dashboard.exe") if IS_WIN else os.path.join(r, "bin", "alvr_dashboard")
    return p if os.path.exists(p) else None


def alvr_driver_dir():
    r = alvr_root()
    if not r:
        return None
    for d in ([r] if IS_WIN else [os.path.join(r, "lib64", "alvr")]):
        if os.path.exists(os.path.join(d, "driver.vrdrivermanifest")):
            return d
    hits = glob.glob(os.path.join(r, "**", "driver.vrdrivermanifest"), recursive=True)
    return os.path.dirname(hits[0]) if hits else None


def install_alvr():
    tag, assets = _latest_alvr()
    name = "alvr_streamer_windows.zip" if IS_WIN else "alvr_streamer_linux.tar.gz"
    url = assets.get(name)
    if not url:
        raise RuntimeError("fant ikke ALVR for dette systemet")
    os.makedirs(ALVR_DIR, exist_ok=True)
    tmp = tempfile.mkdtemp()
    import progress as P
    pt = P.begin(f"Installerer ALVR {tag}", "")
    try:
        f = os.path.join(tmp, name)
        P.download(url, f, pt.sub(0, 0.85), UA)
        pt.set(0.9, "Pakker ut …")
        old = alvr_root()
        if old:
            shutil.rmtree(old, ignore_errors=True)
        if name.endswith(".zip"):
            with zipfile.ZipFile(f) as z:
                z.extractall(ALVR_DIR)
        else:
            with tarfile.open(f) as t:
                t.extractall(ALVR_DIR, filter="data")
        with open(os.path.join(ALVR_DIR, "VERSION"), "w") as fh:
            fh.write(tag)
        pt.done(f"ALVR {tag} er installert")
    except Exception as e:  # noqa: BLE001
        pt.done(str(e)[:100], False)
        raise
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return f"ALVR {tag} er installert ✓"


def alvr_version():
    try:
        return open(os.path.join(ALVR_DIR, "VERSION")).read().strip()
    except OSError:
        return None


def install_alvr_client():
    tag, assets = _latest_alvr()
    url = assets.get("alvr_client_android.apk")
    if not url:
        raise RuntimeError("fant ikke ALVR-appen til Questen")
    tmp = tempfile.mkdtemp()
    import progress as P
    try:
        with P.task("Installerer ALVR i brillene", "", "ALVR er installert i Questen") as pt:
            f = os.path.join(tmp, "alvr.apk")
            P.download(url, f, pt.sub(0, 0.7), UA)
            pt.set(0.75, "Legger appen inn i Questen …")
            code, out = _adb_q("install", "-r", f, t=300)
        if code != 0 or "Success" not in out:
            raise RuntimeError("installasjonen på Questen feilet: " + out.strip()[-160:])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return f"ALVR {tag} er installert på Questen ✓ (finnes under «Ukjente kilder» i app-biblioteket)"


def _vrpaths_file():
    if IS_WIN:
        return os.path.join(os.environ.get("LOCALAPPDATA", ""), "openvr", "openvrpaths.vrpath")
    return os.path.expanduser("~/.config/openvr/openvrpaths.vrpath")


def alvr_driver_registered():
    d = alvr_driver_dir()
    try:
        j = json.load(open(_vrpaths_file()))
    except (OSError, ValueError):
        return False
    return bool(d) and any(os.path.normpath(x) == os.path.normpath(d) for x in j.get("external_drivers") or [])


def register_alvr_driver():
    d = alvr_driver_dir()
    if not d:
        raise RuntimeError("ALVR er ikke installert")
    p = _vrpaths_file()
    if not os.path.exists(p):
        raise RuntimeError("Start SteamVR én gang først (Kontrollsenter gjør det for deg med «Fiks»)")
    j = json.load(open(p))
    ext = [x for x in (j.get("external_drivers") or []) if "alvr" not in x.lower() or os.path.exists(x)]
    if d not in ext:
        ext.append(d)
    j["external_drivers"] = ext
    shutil.copy2(p, p + ".bak-kontrollsenter")
    with open(p, "w") as f:
        json.dump(j, f, indent="\t")
    return "ALVR er koblet til SteamVR ✓"


# --------------------------------------------------------------------------
# Linux: brannmur, SteamVR-rettigheter, OpenXR og videokoding
# --------------------------------------------------------------------------
PORTS = ["9943-9944/tcp", "9943-9944/udp"]


def _zones():
    """Aktive soner – bare navnet («FedoraWorkstation (default)» → «FedoraWorkstation»)."""
    _c, out = _run(["firewall-cmd", "--get-active-zones"], 10)
    return [ln.split()[0] for ln in out.splitlines() if ln.strip() and not ln.startswith((" ", "\t"))]


def _covers(spec, port, proto):
    """«1025-65535/tcp» eller «9943/udp» dekker port/proto?"""
    m = re.fullmatch(r"(\d+)(?:-(\d+))?/(\w+)", spec.strip())
    if not m or m.group(3) != proto:
        return False
    lo, hi = int(m.group(1)), int(m.group(2) or m.group(1))
    return lo <= port <= hi


def _zone_open(z):
    _c, ports = _run(["firewall-cmd", "--zone", z, "--list-ports"], 10)
    _c, svcs = _run(["firewall-cmd", "--zone", z, "--list-services"], 10)
    _c, target = _run(["firewall-cmd", "--zone", z, "--get-target"], 10)
    if "alvr" in svcs.split() or target.strip().upper() == "ACCEPT":
        return True
    specs = ports.split()
    return all(any(_covers(sp, p, proto) for sp in specs) for p in (9943, 9944) for proto in ("tcp", "udp"))


def firewall_ok():
    if IS_WIN:
        _c, out = _run(["powershell", "-NoProfile", "-Command",
                        "(Get-NetFirewallRule -DisplayName 'Kontrollsenter ALVR*' -ErrorAction SilentlyContinue).Count"], 20)
        return out.strip() not in ("", "0")
    if not shutil.which("firewall-cmd") or _run(["firewall-cmd", "--state"], 10)[0] != 0:
        return True                                   # ingen aktiv brannmur
    return all(_zone_open(z) for z in _zones())


def fix_firewall():
    if IS_WIN:
        ps = ("New-NetFirewallRule -DisplayName 'Kontrollsenter ALVR TCP' -Direction Inbound -Action Allow -Protocol TCP "
              "-LocalPort 9943-9944 -Profile Private,Domain | Out-Null; New-NetFirewallRule -DisplayName "
              "'Kontrollsenter ALVR UDP' -Direction Inbound -Action Allow -Protocol UDP -LocalPort 9943-9944 "
              "-Profile Private,Domain | Out-Null")
        code, _o = _run(["powershell", "-NoProfile", "-Command",
                         f"Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList "
                         f"'-NoProfile','-Command',\"{ps}\""], 120)
        if code != 0:
            raise RuntimeError("Windows ga ikke administratortilgang")
        return "Brannmuren slipper gjennom VR-strømmen ✓"
    if firewall_ok():
        return "Brannmuren slipper allerede gjennom VR-strømmen ✓"
    zones = [z for z in _zones() if not _zone_open(z)]
    if not zones:
        return "Brannmuren slipper gjennom VR-strømmen ✓"
    if not all(re.fullmatch(r"[\w.-]+", z) for z in zones):
        raise RuntimeError("uventet navn på brannmursone")
    cmds = []
    for z in zones:
        for p in PORTS:
            cmds.append(f"firewall-cmd --zone={z} --add-port={p} --permanent")
    cmds.append("firewall-cmd --reload")
    code, out = _run(["pkexec", "sh", "-c", " && ".join(cmds)], 180)
    if code in (126, 127):
        raise RuntimeError("Passordet ble ikke gitt (avbrutt) – prøv igjen")
    if code != 0:
        raise RuntimeError("firewall-cmd feilet: " + (out.strip().splitlines() or ["ukjent feil"])[-1][:160])
    if not firewall_ok():
        raise RuntimeError("Portene ble lagt til, men brannmuren melder fortsatt at de er stengt")
    return "Brannmuren slipper gjennom VR-strømmen ✓"


def _launcher_bin():
    d = steamvr_dir()
    return os.path.join(d, "bin", "linux64", "vrcompositor-launcher") if d else None


def steamvr_cap_ok():
    if IS_WIN:
        return True
    p = _launcher_bin()
    if not p or not os.path.exists(p):
        return True
    _c, out = _run(["getcap", p], 10)
    return "cap_sys_nice" in out.lower()


def fix_steamvr_cap():
    p = _launcher_bin()
    if not p:
        raise RuntimeError("SteamVR er ikke installert")
    code, out = _run(["pkexec", "setcap", "CAP_SYS_NICE=eip", p], 120)
    if code != 0:
        raise RuntimeError("Tilgangen ble ikke gitt (avbrutt?)")
    return "SteamVR får høy prioritet (jevnere bilde) ✓"


def _openxr_target():
    d = steamvr_dir()
    if not d:
        return None
    return os.path.join(d, "steamxr_win64.json" if IS_WIN else "steamxr_linux64.json")


def openxr_ok():
    t = _openxr_target()
    if not t or not os.path.exists(t):
        return True
    if IS_WIN:
        _c, out = _run(["reg", "query", r"HKLM\SOFTWARE\Khronos\OpenXR\1", "/v", "ActiveRuntime"], 10)
        return "steamxr" in out.lower() or "oculus" in out.lower()   # Meta Link-kjøretiden virker også
    try:
        cur = os.path.realpath(os.path.expanduser("~/.config/openxr/1/active_runtime.json"))
        return os.path.exists(cur) and ("steamxr" in cur.lower() or "alvr" in cur.lower() or "wivrn" in cur.lower())
    except OSError:
        return False


def fix_openxr():
    t = _openxr_target()
    if not t:
        raise RuntimeError("SteamVR er ikke installert")
    if IS_WIN:
        code, _o = _run(["powershell", "-NoProfile", "-Command",
                         f"Start-Process reg -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList 'add',"
                         f"'HKLM\\SOFTWARE\\Khronos\\OpenXR\\1','/v','ActiveRuntime','/t','REG_SZ','/d','{t}','/f'"], 60)
        if code != 0:
            raise RuntimeError("Windows ga ikke administratortilgang")
    else:
        d = os.path.expanduser("~/.config/openxr/1")
        os.makedirs(d, exist_ok=True)
        link = os.path.join(d, "active_runtime.json")
        if os.path.lexists(link):
            os.replace(link, link + ".bak-kontrollsenter")
        os.symlink(t, link)
    return "SteamVR er valgt som OpenXR (VR-spill som bruker OpenXR virker) ✓"


def encoder_ok():
    """Skjermkortet kan kode video i maskinvare (NVENC / VA-API / AMF)."""
    if IS_WIN:
        return True
    if shutil.which("nvidia-smi") and _run(["nvidia-smi", "-L"], 10)[0] == 0:
        return True
    _c, out = _run(["vainfo"], 15)
    return "VAEntrypointEncSlice" in out


def pc_wired():
    if IS_WIN:
        _c, out = _run(["powershell", "-NoProfile", "-Command",
                        "(Get-NetAdapter -Physical | Where-Object {$_.Status -eq 'Up' -and $_.MediaType -eq '802.3'}).Count"], 20)
        return out.strip() not in ("", "0")
    _c, out = _run(["nmcli", "-t", "-f", "TYPE,STATE", "dev"], 10)
    return any(ln.startswith("ethernet:connected") for ln in out.splitlines())


# --------------------------------------------------------------------------
# Windows: Meta Horizon Link (kabel)
# --------------------------------------------------------------------------
def meta_link_dir():
    for p in (r"%ProgramFiles%\Oculus", r"%ProgramFiles%\Meta Horizon", r"C:\Oculus"):
        d = os.path.expandvars(p)
        if os.path.exists(os.path.join(d, "Support", "oculus-runtime")):
            return d
    return None


def meta_service_ok():
    _c, out = _run(["sc", "query", "OVRService"], 10)
    return "RUNNING" in out


def fix_meta_service():
    code, _o = _run(["powershell", "-NoProfile", "-Command",
                     "Start-Process sc -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList 'start','OVRService'"], 60)
    if code != 0:
        raise RuntimeError("Windows ga ikke administratortilgang")
    return "Meta-tjenesten kjører ✓"


def install_meta_link():
    tmp = os.path.join(tempfile.gettempdir(), "MetaHorizonLinkSetup.exe")
    with urllib.request.urlopen(urllib.request.Request(META_LINK_URL, headers=UA), timeout=300) as r, \
            open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    os.startfile(tmp)  # noqa: S606 – Metas eget installasjonsprogram (du godkjenner i vinduet)
    return "Meta Horizon Link-installasjonen er startet – følg vinduet"


# --------------------------------------------------------------------------
# Sjekkliste og retting
# --------------------------------------------------------------------------
def checks(mode=None):
    """[{key, title, ok, info, fix (True hvis automatisk), manual (tekst)}] for valgt tilkobling."""
    mode = mode or cfg()["mode"]
    out = []

    def add(key, title, ok, info="", fix=True, manual=None, warn=False):
        out.append({"key": key, "title": title, "ok": bool(ok), "info": info, "fix": fix, "manual": manual,
                    "warn": warn})
    st = steam_ok()
    add("steam", "Steam", st, "", True)
    svr = steamvr_dir()
    add("steamvr", "SteamVR", bool(svr), "Installeres gjennom Steam (gratis)" if not svr else "", st)
    vp = os.path.exists(_vrpaths_file())
    if svr and not vp:
        add("steamvr_first", "SteamVR startet én gang", False, "SteamVR må startes én gang for å bli klar", True)
    use_alvr = not IS_WIN or cfg().get("win_alvr")
    if not IS_WIN and svr:
        add("steamvr_cap", "SteamVR-rettigheter", steamvr_cap_ok(), "Gir SteamVR høy prioritet – ellers hakker bildet",
            bool(svr))
    if use_alvr:
        add("alvr", "ALVR på PC-en", bool(alvr_dashboard()), alvr_version() or "Strømmer SteamVR til Questen", True)
        add("alvr_driver", "ALVR koblet til SteamVR", alvr_driver_registered(), "", True)
        add("firewall", "Brannmur åpen for VR", firewall_ok(), "Port 9943–9944 på hjemmenettet", True)
    if IS_WIN and not use_alvr and mode == "wired":
        md = meta_link_dir()
        add("metalink", "Meta Horizon Link", bool(md), "Metas program for kabel (Quest Link)", True)
        if md:
            add("metasvc", "Meta-tjenesten kjører", meta_service_ok(), "", True)
    if IS_WIN and not use_alvr and mode == "wireless":
        add("steamlink", "Steam Link på Questen", None, "", False,
            "Installer «Steam Link» fra butikken i Questen (gratis). Start SteamVR-spill derfra – PC-en trenger "
            "bare Steam og SteamVR.", warn=True)
    if svr:
        add("openxr", "OpenXR satt til SteamVR", openxr_ok(), "Trengs for nyere VR-spill", True)
    add("encoder", "Videokoding i skjermkortet", encoder_ok(), "NVENC / VA-API", False,
        None if encoder_ok() else "Installer skjermkortdriveren (NVIDIA) eller Mesa VA-API (AMD/Intel).")
    q = quest() if (use_alvr or mode == "wired") else {"state": "skip"}
    if use_alvr:
        a = adb()
        add("adb", "Android-verktøy (adb)", bool(a), "Til å installere ALVR på Questen og kabel-tilkobling", True)
        if q["state"] == "device":
            pkg = alvr_client_pkg()
            add("alvr_client", "ALVR-appen på Questen", bool(pkg), pkg or "", True)
        elif q["state"] == "unauthorized":
            add("quest_auth", "Godkjenn PC-en i brillene", False, "", False,
                "Ta på brillene og trykk «Tillat» (kryss av for «Tillat alltid fra denne datamaskinen»).")
        elif mode == "wired" or not alvr_client_installed_flag():
            add("quest_usb", "Questen koblet til med USB", False, "", False,
                "Koble Questen til PC-en med USB-C-kabel (USB 3). Første gang: slå på utviklermodus i Meta "
                "Horizon-appen på mobilen (Meny → Enheter → Utviklermodus), og godkjenn PC-en i brillene.")
    elif mode == "wired":
        add("quest_usb", "Questen koblet til med USB", bool(q.get("usb")), "", False,
            None if q.get("usb") else "Koble til med en USB 3-kabel (USB-C), og velg «Link» i Questen.")
    if mode == "wireless":
        w = pc_wired()
        add("pc_lan", "PC-en på kabel til ruteren", w, "Gir jevnest trådløs VR", False,
            None if w else "Koble PC-en til ruteren med nettverkskabel – da får Questen hele Wi-Fi-en.", warn=not w)
        mhz = quest_wifi_mhz() if q.get("state") == "device" else None
        if mhz:
            add("quest_wifi", "Questen på 5/6 GHz Wi-Fi", mhz >= 5000, f"{mhz} MHz", False,
                None if mhz >= 5000 else "Questen er på 2,4 GHz – koble den til 5 GHz- eller 6 GHz-nettet.",
                warn=mhz < 5000)
    return out


def alvr_client_installed_flag():
    return bool(cfg().get("client_ok"))


def fix(key):
    """Rett én ting. Returnerer melding (kaster ved feil)."""
    import apps
    if key == "steam":
        return apps.install("steam")
    if key == "steamvr":
        _steam_uri(f"steam://install/{STEAMVR_APPID}")
        return "Steam installerer SteamVR – trykk «Installer» i Steam-vinduet"
    if key == "steamvr_first":
        _steam_uri(f"steam://run/{STEAMVR_APPID}")
        return "SteamVR startes én gang – lukk det igjen når det er oppe, og trykk «Sjekk på nytt»"
    if key == "steamvr_cap":
        return fix_steamvr_cap()
    if key == "alvr":
        return install_alvr()
    if key == "alvr_driver":
        return register_alvr_driver()
    if key == "firewall":
        return fix_firewall()
    if key == "openxr":
        return fix_openxr()
    if key == "adb":
        return install_adb()
    if key == "alvr_client":
        m = install_alvr_client()
        save_cfg(client_ok=True)
        return m
    if key == "metalink":
        return install_meta_link()
    if key == "metasvc":
        return fix_meta_service()
    raise ValueError("kan ikke rettes automatisk")


ORDER = ["steam", "steamvr", "steamvr_first", "alvr", "steamvr_cap", "alvr_driver", "firewall", "openxr", "adb",
         "alvr_client", "metalink", "metasvc"]


def fix_all(progress=None, mode=None):
    """Rett alt som kan rettes, i riktig rekkefølge. Returnerer [(tittel, melding)]."""
    done = []
    import progress as P
    todo = [x for x in checks(mode) if not x["ok"] and x["fix"]]
    pt = P.begin("Setter opp VR", f"{len(todo)} ting å rette")
    for k in ORDER:
        c = next((x for x in checks(mode) if x["key"] == k), None)
        if not c or c["ok"] or not c["fix"]:
            continue
        pt.step(len(done), max(1, len(todo)), f"Retter: {c['title']}")
        if progress:
            progress(f"Retter: {c['title']} …")
        try:
            done.append((c["title"], fix(k)))
        except Exception as e:  # noqa: BLE001
            done.append((c["title"], f"feilet: {e}"))
        if k in ("steamvr", "steamvr_first"):
            break                                  # Steam må gjøre jobben først – sjekk igjen etterpå
    bad = [t for t, m in done if m.startswith("feilet")]
    pt.done("Alt som kan rettes automatisk er rettet" if not bad else f"{len(bad)} ting feilet", not bad)
    return done


# --------------------------------------------------------------------------
# Start VR og hold det i gang
# --------------------------------------------------------------------------
def start(mode=None):
    mode = mode or cfg()["mode"]
    save_cfg(mode=mode)
    use_alvr = not IS_WIN or cfg().get("win_alvr")
    msgs = []
    if use_alvr:
        dash = alvr_dashboard()
        if not dash:
            raise RuntimeError("ALVR er ikke installert – trykk «Fiks alt»")
        if not running("alvr_dashboard") and not running("ALVR Dashboard"):
            kw = {"creationflags": 0x08000000} if IS_WIN else {"start_new_session": True}
            subprocess.Popen([dash], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
            msgs.append("ALVR startet")
        if mode == "wired":
            msgs.append(wired_link())
        if not running("vrserver"):
            _steam_uri(f"steam://run/{STEAMVR_APPID}")
            msgs.append("SteamVR startes")
        pkg = alvr_client_pkg() if quest()["state"] == "device" else None
        if pkg:
            _adb_q("shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1", t=20)
            msgs.append("ALVR åpnet i brillene")
        else:
            msgs.append("Åpne ALVR i brillene (App-bibliotek → Ukjente kilder)")
    else:
        if mode == "wired":
            d = meta_link_dir()
            if not d:
                raise RuntimeError("Meta Horizon Link er ikke installert – trykk «Fiks alt»")
            if not meta_service_ok():
                fix_meta_service()
            exe = glob.glob(os.path.join(d, "Support", "oculus-client", "OculusClient.exe"))
            if exe:
                os.startfile(exe[0])  # noqa: S606
            msgs.append("Meta Horizon Link startet – velg «Quest Link» i brillene")
        if not running("vrserver"):
            _steam_uri(f"steam://run/{STEAMVR_APPID}")
            msgs.append("SteamVR startes")
        if mode == "wireless":
            msgs.append("Åpne «Steam Link» i brillene og velg PC-en")
    save_cfg(active=True, started=time.time())
    return " · ".join(msgs)


def wired_link():
    """ALVR over USB: send trafikken gjennom kabelen (adb forward)."""
    q = quest()
    if q["state"] != "device":
        raise RuntimeError("Questen er ikke koblet til med USB (eller PC-en er ikke godkjent i brillene)")
    for p in ("9943", "9944"):
        _adb_q("forward", f"tcp:{p}", f"tcp:{p}", t=15)
    return "Kabel-tilkobling klar (USB)"


def stop():
    save_cfg(active=False)
    return "VR-vakten er stoppet"


_WATCH = {"t": 0, "fixes": 0}


def watch_tick(notify=None):
    """Kalles jevnlig: mens VR er startet, hold det i gang og rett feil av seg selv."""
    c = cfg()
    if not c.get("active") or not c.get("keepalive"):
        return None
    if time.time() - c.get("started", 0) > 6 * 3600:
        save_cfg(active=False)
        return None
    if time.time() - _WATCH["t"] < 20 or time.time() - c.get("started", 0) < 40:
        return None
    _WATCH["t"] = time.time()
    use_alvr = not IS_WIN or c.get("win_alvr")
    fixed = []
    try:
        if use_alvr and alvr_dashboard() and not running("alvr_dashboard") and not running("ALVR Dashboard"):
            kw = {"creationflags": 0x08000000} if IS_WIN else {"start_new_session": True}
            subprocess.Popen([alvr_dashboard()], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
            fixed.append("ALVR ble startet igjen")
        if use_alvr and c.get("mode") == "wired" and quest()["state"] == "device":
            _c, out = _run([adb(), "forward", "--list"], 10)
            if "9944" not in out:
                wired_link()
                fixed.append("kabel-tilkoblingen ble satt opp igjen")
        if not running("vrserver") and running("steam"):
            _steam_uri(f"steam://run/{STEAMVR_APPID}")
            fixed.append("SteamVR ble startet igjen")
    except Exception:  # noqa: BLE001
        pass
    if fixed:
        _WATCH["fixes"] += 1
        msg = "VR: " + ", ".join(fixed)
        if notify:
            notify("vr", "VR rettet automatisk", msg)
        return msg
    return None


def state():
    c = cfg()
    q = quest()
    return {"mode": c["mode"], "active": bool(c.get("active")), "quest": q, "os": "windows" if IS_WIN else "linux",
            "headset": headset(),
            "alvr": alvr_version(), "steamvr": bool(steamvr_dir()), "win_alvr": bool(c.get("win_alvr")),
            "vr_running": running("vrserver"), "checks": checks(c["mode"])}


# --------------------------------------------------------------------------
# Hodesettet: koblet til med kabel eller Wi-Fi?
# --------------------------------------------------------------------------
def _alvr_session():
    for p in ([os.path.join(alvr_root() or "", "session.json")] if IS_WIN else []) + \
            [os.path.expanduser("~/.config/alvr/session.json")]:
        try:
            with open(p) as f:
                return json.load(f)
        except (OSError, ValueError):
            continue
    return {}


def _alvr_client_ips():
    """IP-ene ALVR kjenner for brillene (fra «klienter» i ALVR)."""
    ips = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("current_ip", "ip") and isinstance(v, str) and re.fullmatch(r"\d+\.\d+\.\d+\.\d+", v):
                    ips.append(v)
                elif k == "manual_ips" and isinstance(v, list):
                    ips.extend(x for x in v if isinstance(x, str) and re.fullmatch(r"\d+\.\d+\.\d+\.\d+", x))
                else:
                    walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)
    walk(_alvr_session().get("client_connections", {}))
    return [ip for ip in dict.fromkeys(ips) if not ip.startswith("127.")]


def _ping(ip):
    cmd = ["ping", "-n", "1", "-w", "700", ip] if IS_WIN else ["ping", "-c", "1", "-W", "1", ip]
    return _run(cmd, 4)[0] == 0


def _talking_to(ip):
    """Har PC-en en aktiv forbindelse til brillene akkurat nå (strømmer)?"""
    if IS_WIN:
        _c, out = _run(["netstat", "-an"], 15)
    else:
        _c, out = _run(["ss", "-tunH"], 10)
    return any(f"{ip}:" in ln for ln in out.splitlines())


def headset():
    """{"usb", "adb", "model", "battery", "wifi_ip", "wifi_online", "streaming", "via"}"""
    out = {"usb": _quest_usb(), "adb": None, "model": None, "battery": None, "wifi_ip": None,
           "wifi_online": False, "streaming": False, "via": None}
    q = quest() if out["usb"] else {"state": "none"}
    out["adb"] = q.get("state")
    if q.get("state") == "device":
        try:
            _c, m = _adb_q("shell", "getprop", "ro.product.model", t=8)
            out["model"] = m.strip() or None
            _c, b = _adb_q("shell", "dumpsys", "battery", t=8)
            mm = re.search(r"level: (\d+)", b)
            out["battery"] = int(mm.group(1)) if mm else None
            _c, ipo = _adb_q("shell", "ip", "-f", "inet", "addr", "show", "wlan0", t=8)
            mi = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", ipo)
            if mi:
                out["wifi_ip"] = mi.group(1)
                if cfg().get("quest_ip") != mi.group(1):
                    save_cfg(quest_ip=mi.group(1))
        except Exception:  # noqa: BLE001
            pass
    ips = list(dict.fromkeys([x for x in ([out["wifi_ip"], cfg().get("quest_ip")] + _alvr_client_ips()) if x]))
    for ip in ips:
        if _talking_to(ip):
            out.update(wifi_ip=ip, wifi_online=True, streaming=True)
            break
    if not out["streaming"]:
        for ip in ips[:3]:
            if _ping(ip):
                out.update(wifi_ip=ip, wifi_online=True)
                break
    if out["streaming"]:
        out["via"] = "ALVR" if (not IS_WIN or cfg().get("win_alvr")) else "Steam Link"
    if out["usb"] and (running("OVRServer") or running("OVRServer_x64")):
        out["via"] = out["via"] or "Quest Link"
    return out
