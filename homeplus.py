"""Hjem+ (runde 5): VR med ett trykk, rommet følger PC-en, ny PC / kopier oppsett, nettverksvakt, fjernhjelp,
passordsjekk, svindel-skjold, kamera og mikrofon, gjeste-Wi-Fi og nattlig fartstest.

  9  Klar for VR: Max Ytelse, sjekk og fiks (brannmur, Wi-Fi …) og start SteamVR + ALVR/WiVRn
  11 Rommet følger PC-en: lysene (Hue) slukkes når PC-en går i dvale og tennes når den våkner (Linux)
  13 Ny PC: hent innstillinger fra en annen PC (NAS) og installer de samme programmene
  14 Kopier oppsett til en annen PC: vifter, RGB, overlay, lyd, utseende … via hjemmenettet
  19 Nettverksvakt: varsel når en ukjent enhet kobler seg til hjemmenettet
  46 Fjernhjelp: «Hjelp»-knapp sender beskjed og RustDesk-ID til de voksne
  56 Passordsjekk: har passordet vært med i en datalekkasje? (bare 5 tegn av en hash sendes – passordet forlater
     aldri PC-en)
  57 Svindel-skjold: DNS som blokkerer svindel og skadevare (Quad9) for voksne
  58 Kamera og mikrofon: hvilke programmer bruker dem nå – demp mikrofonen med ett trykk
  62 Gjeste-Wi-Fi: QR-kode gjestene skanner med mobilen
  63 Nattlig fartstest: nedlasting, opplasting og ping hver natt – månedsrapport
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request

IS_WIN = sys.platform == "win32"
DATA = os.path.expanduser("~/.local/share/systemmonitor")
CFG = os.path.expanduser("~/.config/systemmonitor/hjem-pluss.json")
DEF = {"room_follow": False, "guest_ssid": "", "guest_pass": "", "speedtest": False, "lan_notify": True}
SPEED = os.path.join(DATA, "fartstest.json")
COPY_FILES = {"vifter": ["fans.json", "viftekurver.json"], "rgb": ["rgb.json"], "overlay": ["overlay"],
              "lyd": ["lyd.json", "profiler.json"], "utseende": ["utseende.json"],
              "oversikt": ["oversikt.json", "rekkefolge.json", "infofliser.json"], "scener": ["scener.json"],
              "varsler": ["bakgrunn.json"]}
CONF = os.path.expanduser("~/.config/systemmonitor")


def cfg():
    try:
        d = json.load(open(CFG))
    except (OSError, ValueError):
        d = {}
    return {**DEF, **d}


def set_(**kw):
    d = cfg()
    d.update(kw)
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    json.dump(d, open(CFG, "w"), ensure_ascii=False, indent=1)
    return d


def _notify(win, key, title, body, action=None):
    bg = getattr(win, "bg", None)
    if bg:
        from gi.repository import GLib
        GLib.idle_add(lambda: (bg.notify(key, title, body, force=True, action=action or "app.show"), False)[1])


# --------------------------------------------------------------------------
# 9 – Klar for VR
# --------------------------------------------------------------------------
def vr_ready(win, progress=None):
    import remote
    import vr
    steps = []
    try:
        remote.do_action(win, {"a": "power", "mode": "performance"})
        steps.append("Max Ytelse")
    except Exception:  # noqa: BLE001
        pass
    bad = [c for c in vr.checks() if not c.get("ok") and c.get("fix")]
    if bad:
        try:
            vr.fix_all(progress)
            steps.append(f"fikset {len(bad)} ting")
        except Exception as e:  # noqa: BLE001
            steps.append(f"kunne ikke fikse alt: {e}")
    try:
        r = vr.start()
        steps.append(r if isinstance(r, str) else "SteamVR og strømmingen startet")
    except Exception as e:  # noqa: BLE001
        steps.append(f"start feilet: {e}")
    return "🥽 " + " · ".join(steps)


# --------------------------------------------------------------------------
# 11 – rommet følger PC-en (dvale/våkne → Hue)
# --------------------------------------------------------------------------
_SLEEP = {"sub": None, "was_on": None}


def watch_sleep(win):
    """Linux: lytt på logind «PrepareForSleep» (dvale og våkne)."""
    if IS_WIN or _SLEEP["sub"]:
        return
    try:
        from gi.repository import Gio
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)

        def on_signal(_c, _s, _p, _i, _sig, params):
            going = params.unpack()[0]
            if cfg()["room_follow"]:
                threading.Thread(target=_room, args=(going,), daemon=True).start()
        _SLEEP["sub"] = bus.signal_subscribe("org.freedesktop.login1", "org.freedesktop.login1.Manager",
                                             "PrepareForSleep", "/org/freedesktop/login1", None,
                                             Gio.DBusSignalFlags.NONE, on_signal)
    except Exception:  # noqa: BLE001
        pass


def _room(going_to_sleep):
    try:
        import features
        if going_to_sleep:
            features.hue_set(on=False)
        else:
            features.hue_set(on=True)
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------
# 13 – ny PC: innstillinger og programmer fra en annen PC
# --------------------------------------------------------------------------
def setup_from(backup_name):
    """Hent innstillinger fra en sikkerhetskopi på NAS-en og installer de samme programmene. Returnerer tekst."""
    import features
    features.restore_settings(backup_name)
    msg = f"Innstillingene fra {backup_name} er hentet"
    installed = []
    try:
        import apps
        for feat in apps.TOP5:
            use = apps.get_use(feat)
            if use and not apps.installed(use) and apps.can_install(use):
                try:
                    apps.install(use)
                    installed.append(apps.APPS[use]["name"])
                except Exception:  # noqa: BLE001
                    pass
    except Exception:  # noqa: BLE001
        pass
    return str(msg) + (f" · Installerte: {', '.join(installed)}" if installed else "")


# --------------------------------------------------------------------------
# 14 – kopier oppsett til en annen PC
# --------------------------------------------------------------------------
def pack(parts):
    """{filnavn: innhold} for de valgte delene (bare kjente innstillingsfiler)."""
    out = {}
    for p in parts:
        for f in COPY_FILES.get(p, []):
            path = os.path.join(CONF, f)
            if os.path.isfile(path) and os.path.getsize(path) < 512 * 1024:
                out[f] = open(path, encoding="utf-8", errors="replace").read()
    return out


def receive(files, win=None):
    """Fra en annen PC: lagre innstillingene (tidsmaskinen tar kopi først) og start på nytt."""
    allowed = {f for fs in COPY_FILES.values() for f in fs}
    bad = [f for f in files if f not in allowed or "/" in f or "\\" in f]
    if bad:
        raise ValueError("ukjente filer: " + ", ".join(bad))
    try:
        import timemachine
        timemachine.snapshot(why="før oppsett fra en annen PC", force=True)
    except Exception:  # noqa: BLE001
        pass
    for f, text in files.items():
        with open(os.path.join(CONF, f), "w", encoding="utf-8") as fh:
            fh.write(text)
    if win is not None:
        from gi.repository import GLib
        GLib.timeout_add(1500, lambda: (win.restart_app(hidden=not win.get_visible()), False)[1])
    return f"{len(files)} innstillingsfiler mottatt – Kontrollsenter starter på nytt"


def send_setup(p, parts):
    """Send oppsettet til PC-en p (husnøkkel, POST)."""
    import watch
    files = pack(parts)
    if not files:
        raise RuntimeError("fant ingen innstillinger å sende for det du valgte")
    body = json.dumps({"files": files}).encode()
    last = "svarer ikke"
    for ip in (p.get("ips") or [])[:2]:
        try:
            req = urllib.request.Request(f"http://{ip}:27100/api/house/setup?fk={watch.house_key()}", data=body,
                                         headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r).get("msg", "OK")
        except Exception as e:  # noqa: BLE001
            last = str(e)[:80]
            if "404" in last or "405" in last:
                return f"{p.get('name')} har en eldre versjon – oppdater den først"
    raise RuntimeError(last)


# --------------------------------------------------------------------------
# 19 – nettverksvakt (varsel om ny enhet)
# --------------------------------------------------------------------------
def lan_tick(win):
    if not cfg()["lan_notify"]:
        return
    import features
    before = set(features._known())
    features.lan_tick()
    new = [d for d in features.lan_devices() if d["mac"] not in before]
    if before and new:
        names = ", ".join(f"{d['ip']}" for d in new[:3])
        _notify(win, "lan", "Ny enhet på hjemmenettet", f"{names} – gi den navn i Smart Hjem hvis du kjenner den, "
                                                         "ellers bør du sjekke ruteren.")


# --------------------------------------------------------------------------
# 46 – fjernhjelp
# --------------------------------------------------------------------------
def rustdesk_id():
    try:
        import apps
        if not apps.installed("rustdesk"):
            return None
        cmd = ["flatpak", "run", "com.rustdesk.RustDesk", "--get-id"] if not IS_WIN and not os.path.exists(
            "/usr/bin/rustdesk") else (["rustdesk", "--get-id"] if not IS_WIN else
                                       [os.path.expandvars(r"%ProgramFiles%\RustDesk\rustdesk.exe"), "--get-id"])
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15).stdout.strip()
        m = re.search(r"\b\d{9,10}\b", out)
        return m.group(0) if m else None
    except Exception:  # noqa: BLE001
        return None


def ask_help(text=""):
    """«Hjelp!»: beskjed til de voksne (familie-chat + push) med RustDesk-ID og «Se på»."""
    import features
    import savegames
    rid = rustdesk_id()
    me = savegames.pc_name()
    msg = f"🆘 {me} trenger hjelp" + (f": {text}" if text else "") + \
        (f". RustDesk-ID: {rid} (åpne RustDesk og koble til)" if rid else ". Bruk «Se på» i Kontrollsenter.")
    features.send_to("*", me, msg, urgent=True)
    try:
        import push
        push.publish("help", f"🆘 {me} trenger hjelp", msg)
    except Exception:  # noqa: BLE001
        pass
    try:
        import apps
        if rid:
            apps.launch("rustdesk")
    except Exception:  # noqa: BLE001
        pass
    return "Hjelp er bedt om ✓" + (f" – RustDesk er åpnet (ID {rid})" if rid else "")


# --------------------------------------------------------------------------
# 56 – passordsjekk (k-anonymitet)
# --------------------------------------------------------------------------
def pwned(password):
    """Antall ganger passordet finnes i kjente lekkasjer. Bare de 5 første tegnene av SHA-1 sendes."""
    if not password:
        raise ValueError("skriv et passord")
    h = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    req = urllib.request.Request(f"https://api.pwnedpasswords.com/range/{h[:5]}",
                                 headers={"User-Agent": "Kontrollsenter", "Add-Padding": "true"})
    with urllib.request.urlopen(req, timeout=15) as r:
        for ln in r.read().decode().splitlines():
            suf, _, n = ln.partition(":")
            if suf.strip() == h[5:]:
                return int(n.strip() or 0)
    return 0


# --------------------------------------------------------------------------
# 58 – kamera og mikrofon i bruk
# --------------------------------------------------------------------------
def cam_mic():
    """{"mic": [programmer], "cam": [programmer]}"""
    out = {"mic": [], "cam": []}
    if IS_WIN:
        try:
            import winreg
            for kind, key in (("mic", "microphone"), ("cam", "webcam")):
                base = rf"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\{key}"
                for root in (base, base + r"\NonPackaged"):
                    try:
                        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, root)
                    except OSError:
                        continue
                    i = 0
                    while True:
                        try:
                            sub = winreg.EnumKey(k, i)
                        except OSError:
                            break
                        i += 1
                        try:
                            sk = winreg.OpenKey(k, sub)
                            stop = winreg.QueryValueEx(sk, "LastUsedTimeStop")[0]
                            start = winreg.QueryValueEx(sk, "LastUsedTimeStart")[0]
                            if stop == 0 and start:
                                out[kind].append(sub.split("#")[-1].replace(".exe", ""))
                        except OSError:
                            pass
        except Exception:  # noqa: BLE001
            pass
        return out
    try:                                                  # mikrofon: PipeWire/Pulse-opptak som kjører
        r = subprocess.run(["pactl", "-f", "json", "list", "source-outputs"], capture_output=True, text=True,
                           timeout=5)
        for so in json.loads(r.stdout or "[]"):
            props = so.get("properties", {})
            name = props.get("application.name") or props.get("application.process.binary") or "?"
            if "peak detect" in str(props.get("media.name", "")).lower() or name in ("pavucontrol", "plasmashell"):
                continue
            if not so.get("corked"):
                out["mic"].append(name)
    except Exception:  # noqa: BLE001
        pass
    try:                                                  # kamera: hvem har /dev/video* åpen
        vids = {os.path.realpath(v) for v in __import__("glob").glob("/dev/video*")}
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                for fd in os.listdir(f"/proc/{pid}/fd"):
                    if os.path.realpath(f"/proc/{pid}/fd/{fd}") in vids:
                        out["cam"].append(open(f"/proc/{pid}/comm").read().strip())
                        break
            except OSError:
                continue
    except Exception:  # noqa: BLE001
        pass
    out["mic"] = sorted(set(out["mic"]))
    out["cam"] = sorted(set(out["cam"]))
    return out


def mic_mute(on=True):
    if IS_WIN:
        return False, "Demp mikrofonen i Windows (lydikonet) – ikke støttet herfra ennå"
    subprocess.run(["pactl", "set-source-mute", "@DEFAULT_SOURCE@", "1" if on else "0"], timeout=5)
    return True, "Mikrofonen er dempet" if on else "Mikrofonen er på"


# --------------------------------------------------------------------------
# 63 – nattlig fartstest
# --------------------------------------------------------------------------
def speedtest():
    """{"down": Mbit/s, "up": Mbit/s, "ping": ms} mot Cloudflare."""
    ua = {"User-Agent": "Kontrollsenter/1.0"}

    def get(url, timeout=60):
        return urllib.request.urlopen(urllib.request.Request(url, headers=ua), timeout=timeout)
    t = time.monotonic()
    pings = []
    for _ in range(3):
        t0 = time.monotonic()
        try:
            get("https://speed.cloudflare.com/__down?bytes=0", 8).read()
            pings.append((time.monotonic() - t0) * 1000)
        except Exception:  # noqa: BLE001
            pass
    size = 25_000_000
    t0 = time.monotonic()
    got = 0
    with get(f"https://speed.cloudflare.com/__down?bytes={size}") as r:
        while True:
            b = r.read(1 << 16)
            if not b:
                break
            got += len(b)
    down = got * 8 / (time.monotonic() - t0) / 1e6
    up_size = 10_000_000
    t0 = time.monotonic()
    req = urllib.request.Request("https://speed.cloudflare.com/__up", data=b"0" * up_size, method="POST",
                                 headers={**ua, "Content-Type": "application/octet-stream"})
    urllib.request.urlopen(req, timeout=60).read()
    up = up_size * 8 / (time.monotonic() - t0) / 1e6
    return {"t": time.time(), "down": round(down, 1), "up": round(up, 1),
            "ping": round(min(pings), 1) if pings else None, "secs": round(time.monotonic() - t)}


def speed_history():
    try:
        return json.load(open(SPEED))
    except (OSError, ValueError):
        return []


def speed_tick(win):
    if not cfg()["speedtest"]:
        return
    try:
        import equipment
        if equipment.someone_gaming():                  # 61: ikke ta båndbredden mens noen spiller
            return
    except Exception:  # noqa: BLE001
        pass
    lt = time.localtime()
    try:
        import pricejobs
        hour = pricejobs.night_hour()
    except Exception:  # noqa: BLE001
        hour = 3
    if lt.tm_hour != hour or lt.tm_min > 30:
        return
    hist = speed_history()
    if hist and time.strftime("%Y-%m-%d", time.localtime(hist[-1]["t"])) == time.strftime("%Y-%m-%d"):
        return
    try:
        r = speedtest()
    except Exception:  # noqa: BLE001
        return
    hist = (hist + [r])[-120:]
    try:
        os.makedirs(DATA, exist_ok=True)
        json.dump(hist, open(SPEED, "w"))
    except OSError:
        pass


def speed_report():
    h = [x for x in speed_history() if time.time() - x["t"] < 31 * 86400]
    if not h:
        return "Ingen målinger ennå"
    d = sorted(x["down"] for x in h)
    u = sorted(x["up"] for x in h)
    return (f"Siste 30 dager ({len(h)} målinger): nedlasting {d[len(d) // 2]:.0f} Mbit/s (lavest {d[0]:.0f}), "
            f"opplasting {u[len(u) // 2]:.0f} Mbit/s")


_T = {"lan": 0}


def tick(win):
    fns = [speed_tick]
    if time.time() - _T["lan"] > 300:                    # nettverksvakten hvert 5. minutt
        _T["lan"] = time.time()
        fns.append(lan_tick)
    for fn in fns:
        try:
            fn(win)
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("hjem+: %s", fn.__name__)
