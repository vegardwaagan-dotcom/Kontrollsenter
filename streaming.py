"""Strømming og fjernhjelp: Sunshine (strøm spill og skjerm fra PC-en), Moonlight (se strømmen på telefon,
nettbrett eller en annen PC) og RustDesk (fjernstyring/fjernhjelp).

Sunshine kjører som systemd-tjeneste på Linux (starter av seg selv igjen hvis den krasjer) og som
Windows-tjeneste. Paring med telefonen: Moonlight viser en PIN – den skrives inn i Kontrollsenter
(på PC-en eller i appen), som sender den til Sunshine.
"""
import base64
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.request

IS_WIN = sys.platform == "win32"
CFG = os.path.expanduser("~/.config/systemmonitor/strømming.json")
SUN_FLATPAK = "dev.lizardbyte.app.Sunshine"
SUN_UNIT = "app-dev.lizardbyte.app.Sunshine.service"
SUN_CONF = os.path.expanduser(f"~/.var/app/{SUN_FLATPAK}/config/sunshine/sunshine.conf")
SUN_CONF_NATIVE = os.path.expanduser("~/.config/sunshine/sunshine.conf")
SUN_CONF_WIN = r"C:\Program Files\Sunshine\config\sunshine.conf"
SUN_API = "https://localhost:47990"
MOON_FLATPAK = "com.moonlight_stream.Moonlight"
RUST_FLATPAK = "com.rustdesk.RustDesk"
FLAGS = {"creationflags": 0x08000000} if IS_WIN else {}

# Innstillinger som vises i Kontrollsenter: nøkkel -> (navn, forklaring, valg eller None for tekst/tall)
SETTINGS = [
    ("sunshine_name", "Navn i Moonlight", "Navnet PC-en får i Moonlight-appen.", None),
    ("encoder", "Videokoder", "Hvem som pakker bildet. NVENC bruker skjermkortet (best på NVIDIA), VA-API passer "
     "AMD/Intel, programvare bruker prosessoren.", [("", "Automatisk"), ("nvenc", "NVIDIA NVENC"),
                                                    ("vaapi", "VA-API (AMD/Intel)"), ("software", "Prosessoren")]),
    ("nvenc_preset", "Kvalitet eller fart (NVENC)", "Lavere tall = raskere og litt mindre forsinkelse, høyere = "
     "skarpere bilde.", [("", "Standard"), ("1", "1 – raskest"), ("3", "3"), ("5", "5"), ("7", "7 – best bilde")]),
    ("capture", "Skjermopptak", "Portal virker på alle Wayland-skrivebord (spør én gang). KMS er raskest, men "
     "krever ekstra rettigheter.", [("", "Automatisk"), ("portal", "Portal (anbefalt)"), ("kms", "KMS"),
                                    ("wlr", "wlroots")]),
    ("gamepad", "Håndkontroll", "Hvilken kontroll PC-en ser når du spiller fra telefonen med en kontroll.",
     [("", "Automatisk"), ("xseries", "Xbox Series"), ("x360", "Xbox 360"), ("ds5", "PlayStation 5"),
      ("ds4", "PlayStation 4")]),
    ("max_bitrate", "Høyeste bitrate (kbit/s, 0 = ingen grense)", "Tak for datamengden. 20000–40000 passer godt "
     "på telefon via Wi-Fi; Moonlight velger selv innenfor taket.", None),
    ("upnp", "Åpne porter automatisk (UPnP)", "Trengs bare for strømming utenfor hjemmet uten Tailscale. "
     "Tailscale er tryggere.", [("", "Av"), ("enabled", "På")]),
    ("origin_web_ui_allowed", "Hvem kan åpne Sunshine-nettsiden", "Bare denne PC-en er tryggest.",
     [("", "Hjemmenettet (standard)"), ("pc", "Bare denne PC-en")]),
]


def cfg():
    try:
        with open(CFG, encoding="utf-8") as f:
            c = json.load(f)
    except (OSError, ValueError):
        c = {}
    return {"keep_running": True, "user": "", "password": "", **c}


def save_cfg(c):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    tmp = CFG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=1)
    if not IS_WIN:
        os.chmod(tmp, 0o600)                       # Sunshine-passordet ligger her
    os.replace(tmp, CFG)


def _run(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **FLAGS)
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


def _flatpak_installed(app):
    if IS_WIN or not shutil.which("flatpak"):
        return False
    return _run(["flatpak", "info", app], 15)[0] == 0


def _win_exe(*cands):
    for c in cands:
        p = os.path.expandvars(c)
        if os.path.exists(p):
            return p
    return None


# --------------------------------------------------------------------------
# Sunshine
# --------------------------------------------------------------------------
def sunshine_installed():
    if IS_WIN:
        return bool(_win_exe(r"%ProgramFiles%\Sunshine\sunshine.exe"))
    return _flatpak_installed(SUN_FLATPAK) or bool(shutil.which("sunshine"))


def sunshine_running():
    try:
        with socket.create_connection(("127.0.0.1", 47990), timeout=1):
            return True
    except OSError:
        return False


def sunshine_state():
    st = {"installed": sunshine_installed(), "running": sunshine_running(), "autostart": False,
          "keep_running": cfg()["keep_running"], "has_login": bool(cfg()["user"])}
    if IS_WIN:
        code, out = _run(["sc", "qc", "SunshineService"], 10)
        st["autostart"] = "AUTO_START" in out
    else:
        st["autostart"] = _run(["systemctl", "--user", "is-enabled", SUN_UNIT], 10)[1].strip() == "enabled"
        st["unit"] = _run(["systemctl", "--user", "is-active", SUN_UNIT], 10)[1].strip()
    st["addresses"] = addresses()
    return st


def allow_portal():
    """KDE spør «Tillat fjernstyring?» på PC-skjermen hver gang Sunshine starter uten gyldig portal-token (f.eks.
    når den startes fra telefonen etter et krasj) – og ingen sitter der for å trykke. KDE sin egen tillatelsestabell
    «kde-authorized» lar Sunshine slippe dialogen for godt. Gjøres bare for Sunshine-flatpaken, og bare én gang."""
    if IS_WIN or not shutil.which("flatpak") or not _flatpak_installed(SUN_FLATPAK):
        return False
    if "KDE" not in os.environ.get("XDG_CURRENT_DESKTOP", "").upper() and not shutil.which("plasmashell"):
        return False
    code, out = _run(["flatpak", "permissions", "kde-authorized", "remote-desktop"], 10)
    if code == 0 and any(SUN_FLATPAK in ln and "yes" in ln.split() for ln in out.splitlines()):
        return True
    return _run(["flatpak", "permission-set", "kde-authorized", "remote-desktop", SUN_FLATPAK, "yes"], 10)[0] == 0


def disallow_portal():
    """Når Strømming slås av: ta tilbake tillatelsen Kontrollsenter ga."""
    if not IS_WIN and shutil.which("flatpak"):
        _run(["flatpak", "permission-remove", "kde-authorized", "remote-desktop", SUN_FLATPAK], 10)


def sunshine_start():
    if IS_WIN:
        return _run(["sc", "start", "SunshineService"], 30)[0] == 0
    try:
        allow_portal()
    except Exception:  # noqa: BLE001
        pass
    # stopp en løs utgave (startet fra menyen) først – tjenesten starter den av seg selv igjen ved krasj
    with _START_LOCK:
        return _start_linux()


_START_LOCK = threading.Lock()


def _start_linux():
    _run(["systemctl", "--user", "reset-failed"], 10)
    for _attempt in range(2):
        # tjenesten kan være «aktiv» mens Sunshine henger på skjermportalen (lytter ikke) – da hjelper bare omstart
        active = _run(["systemctl", "--user", "is-active", SUN_UNIT], 10)[1].strip() == "active"
        verb = "restart" if active and not sunshine_running() else "start"
        if _run(["systemctl", "--user", verb, SUN_UNIT], 60)[0] != 0:
            return False
        if _wait_running(40):
            return True
    return False


def _wait_running(secs):
    end = time.time() + secs
    while time.time() < end:
        if sunshine_running():
            return True
        time.sleep(2)
    return False


def sunshine_stop():
    if IS_WIN:
        return _run(["sc", "stop", "SunshineService"], 30)[0] == 0
    _run(["systemctl", "--user", "stop", SUN_UNIT], 60)
    if shutil.which("flatpak"):
        _run(["flatpak", "kill", SUN_FLATPAK], 20)
    return True


def sunshine_restart():
    if IS_WIN:
        sunshine_stop()
        time.sleep(1.5)
        return sunshine_start()
    try:
        allow_portal()
    except Exception:  # noqa: BLE001
        pass
    with _START_LOCK:                                         # to raske trykk skal ikke slå hverandre i hjel
        sunshine_stop()
        time.sleep(1.5)
        return _start_linux()


def sunshine_autostart(on):
    if IS_WIN:
        return _run(["sc", "config", "SunshineService", "start=", "auto" if on else "demand"], 20)[0] == 0
    return _run(["systemctl", "--user", "enable" if on else "disable", SUN_UNIT], 30)[0] == 0


def watchdog():
    """Kalles hvert minutt: hold Sunshine i gang hvis du har valgt det (den kan krasje når en strøm avsluttes)."""
    c = cfg()
    if not __import__("funksjoner").on("stromming"):           # Strømming er slått av under Funksjoner
        return False
    if not c["keep_running"] or not sunshine_installed() or sunshine_running():
        return False
    if _START_LOCK.locked():                                    # en start/omstart pågår allerede
        return False
    if time.time() - watchdog.__dict__.get("last", 0) < 120:
        return False
    watchdog.last = time.time()
    ok = sunshine_start()
    try:
        import remote_extra
        remote_extra.event("stream", "Sunshine ble startet igjen", "Den hadde stoppet", "info")
    except Exception:  # noqa: BLE001
        pass
    return ok


# --- innstillinger (sunshine.conf) -----------------------------------------
def conf_path():
    if IS_WIN:
        return SUN_CONF_WIN
    return SUN_CONF if os.path.exists(os.path.dirname(SUN_CONF)) else SUN_CONF_NATIVE


def read_conf():
    out = {}
    try:
        with open(conf_path(), encoding="utf-8") as f:
            for ln in f:
                m = re.match(r"\s*([A-Za-z0-9_]+)\s*=\s*(.*?)\s*$", ln)
                if m:
                    out[m.group(1)] = m.group(2)
    except OSError:
        pass
    return out


def write_conf(changes):
    """Endre noen nøkler og behold resten. Tom verdi = fjern (Sunshine bruker standard)."""
    allowed = {k for k, *_ in SETTINGS}
    for k, v in changes.items():
        if k not in allowed:
            raise ValueError(f"ukjent innstilling: {k}")
        if not re.fullmatch(r"[\w .:-]{0,60}", str(v)):
            raise ValueError("ugyldig verdi")
    if "max_bitrate" in changes and changes["max_bitrate"] not in ("", None):
        if not str(changes["max_bitrate"]).isdigit():
            raise ValueError("bitrate må være et tall")
    if IS_WIN:
        return _api_config(changes)
    p = conf_path()
    try:
        lines = open(p, encoding="utf-8").read().splitlines()
    except OSError:
        lines = []
    seen = set()
    out = []
    for ln in lines:
        m = re.match(r"\s*([A-Za-z0-9_]+)\s*=", ln)
        if m and m.group(1) in changes:
            k = m.group(1)
            seen.add(k)
            if str(changes[k]).strip() not in ("", "0" if k == "max_bitrate" else "\0"):
                out.append(f"{k} = {changes[k]}")
            continue
        out.append(ln)
    for k, v in changes.items():
        if k not in seen and str(v).strip() not in ("", "0" if k == "max_bitrate" else "\0"):
            out.append(f"{k} = {v}")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    if sunshine_running():
        threading.Thread(target=sunshine_restart, daemon=True).start()
    return True


# --- Sunshine-API (paring og enheter) – krever innloggingen til Sunshine-nettsiden ----------
def _api(path, body=None, method=None):
    c = cfg()
    if not c["user"]:
        raise RuntimeError("Legg inn brukernavn og passord for Sunshine i Kontrollsenter først")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE                       # Sunshine bruker et selvsignert sertifikat (bare localhost)
    tok = base64.b64encode(f"{c['user']}:{c['password']}".encode()).decode()
    req = urllib.request.Request(SUN_API + path, data=json.dumps(body).encode() if body is not None else None,
                                 method=method or ("POST" if body is not None else "GET"),
                                 headers={"Authorization": "Basic " + tok, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
            txt = r.read().decode() or "{}"
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise RuntimeError("Feil brukernavn eller passord for Sunshine") from e
        raise RuntimeError(f"Sunshine svarte {e.code}") from e
    except OSError as e:
        raise RuntimeError("Sunshine kjører ikke") from e
    try:
        return json.loads(txt)
    except ValueError:
        return {}


def _api_config(changes):
    cur = _api("/api/config")
    cur.update({k: v for k, v in changes.items()})
    _api("/api/config", cur)
    return True


def set_login(user, password):
    c = cfg()
    c["user"], c["password"] = str(user)[:64], str(password)[:128]
    save_cfg(c)
    _api("/api/clients/list")                             # sjekk at innloggingen virker


def pair(pin, name="Telefon"):
    pin = re.sub(r"\D", "", str(pin))
    if len(pin) != 4:
        raise ValueError("PIN-koden fra Moonlight har 4 sifre")
    r = _api("/api/pin", {"pin": pin, "name": re.sub(r"[^\w .-]", "", str(name))[:40] or "Telefon"})
    ok = r.get("status") in (True, "true", "True")
    if not ok:
        raise RuntimeError("Sunshine godtok ikke PIN-koden – trykk på PC-en i Moonlight og prøv igjen innen 1 minutt")
    return True


def clients():
    try:
        r = _api("/api/clients/list")
        return [{"name": x.get("name") or "?", "id": x.get("uuid")} for x in r.get("named_certs", [])]
    except Exception:  # noqa: BLE001
        return []


def unpair(uuid):
    _api("/api/clients/unpair", {"uuid": str(uuid)})


def addresses():
    """Adressene Moonlight kan bruke: hjemmenettet og Tailscale."""
    out = []
    try:
        import remote
        out += [{"kind": "Hjemmenett", "ip": ip} for ip in remote.local_ips()
                if ip.startswith(("192.168.", "10.", "172."))][:2]
    except Exception:  # noqa: BLE001
        pass
    if not out:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("192.168.1.1", 9))
            out.append({"kind": "Hjemmenett", "ip": s.getsockname()[0]})
            s.close()
        except OSError:
            pass
    try:
        import psutil
        for name, addrs in psutil.net_if_addrs().items():
            for a in addrs:
                if a.family == socket.AF_INET and a.address.startswith("100.") and \
                        64 <= int(a.address.split(".")[1]) <= 127:
                    out.append({"kind": "Tailscale (utenfor hjemmet)", "ip": a.address})
    except Exception:  # noqa: BLE001
        pass
    return out


# --------------------------------------------------------------------------
# Moonlight på PC-en (se strømmen fra en annen PC)
# --------------------------------------------------------------------------
def moonlight_installed():
    if IS_WIN:
        return bool(_win_exe(r"%ProgramFiles%\Moonlight Game Streaming\Moonlight.exe"))
    return _flatpak_installed(MOON_FLATPAK)


def moonlight_open():
    if IS_WIN:
        exe = _win_exe(r"%ProgramFiles%\Moonlight Game Streaming\Moonlight.exe")
        if not exe:
            raise RuntimeError("Moonlight er ikke installert")
        subprocess.Popen([exe], **FLAGS)
    else:
        subprocess.Popen(["flatpak", "run", MOON_FLATPAK], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)


# --------------------------------------------------------------------------
# RustDesk (fjernstyring og fjernhjelp)
# --------------------------------------------------------------------------
def _rust_cmd():
    if IS_WIN:
        exe = _win_exe(r"%ProgramFiles%\RustDesk\rustdesk.exe")
        return [exe] if exe else None
    if _flatpak_installed(RUST_FLATPAK):
        return ["flatpak", "run", RUST_FLATPAK]
    if shutil.which("rustdesk"):
        return ["rustdesk"]
    return None


def rustdesk_state():
    cmd = _rust_cmd()
    st = {"installed": bool(cmd), "running": False, "id": None}
    if not cmd:
        return st
    code, out = _run(cmd + ["--get-id"], 25)
    m = re.search(r"\b(\d{8,11})\b", out or "")
    st["id"] = m.group(1) if m else None
    try:
        import psutil
        st["running"] = any("rustdesk" in (p.info.get("name") or "").lower()
                            for p in psutil.process_iter(["name"]))
    except Exception:  # noqa: BLE001
        pass
    return st


_RD = {"t": 0, "v": None}


def rustdesk_cached(max_age=600):
    """rustdesk_state() mellomlagret (henting av ID kan ta mange sekunder)."""
    if _RD["v"] is None or time.time() - _RD["t"] > max_age:
        _RD.update(v=rustdesk_state(), t=time.time())
    return _RD["v"]


def rustdesk_connect(rid):
    """Koble til en annen PC med RustDesk-ID."""
    rid = re.sub(r"\s+", "", str(rid))
    if not re.fullmatch(r"\d{6,12}", rid):
        raise ValueError("RustDesk-ID er 9–10 siffer")
    cmd = _rust_cmd()
    if not cmd:
        raise RuntimeError("RustDesk er ikke installert")
    subprocess.Popen(cmd + ["--connect", rid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     **(FLAGS if IS_WIN else {"start_new_session": True}))
    return f"Kobler til {rid} – godta på den andre PC-en"


def rustdesk_open():
    cmd = _rust_cmd()
    if not cmd:
        raise RuntimeError("RustDesk er ikke installert")
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **(FLAGS if IS_WIN else
                                                                                    {"start_new_session": True}))


# --------------------------------------------------------------------------
# Installasjon (bare når du trykker på knappen)
# --------------------------------------------------------------------------
INSTALL = {"sunshine": (SUN_FLATPAK, "LizardByte.Sunshine"),
           "moonlight": (MOON_FLATPAK, "MoonlightGameStreamingProject.Moonlight"),
           "rustdesk": (RUST_FLATPAK, "RustDesk.RustDesk")}


def install(what):
    if what not in INSTALL:
        raise ValueError("ukjent program")
    import apps
    apps.install(what)
    return True
