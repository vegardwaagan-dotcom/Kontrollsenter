"""Fjernstyring – styr og følg med på PC-en fra mobil og nettbrett (Android-appen «Kontrollsenter»).

En liten nettjeneste på port 27100 som bare svarer maskiner på hjemmenettet (private IP-adresser):
  /app/…            selve kontrollpanelet (remote_web/) – appen viser det, og det oppdateres med Kontrollsenter
  /api/hello        navn og versjon (uten pålogging – brukes når appen leter etter PC-er)
  /api/pair         par en ny enhet med 6-sifret kode som vises på PC-en (gyldig i 5 minutter, 5 forsøk)
  /api/status …     alt annet krever nøkkelen fra paringen (Authorization: Bearer …)

Tjenesten er AV til du slår den på (Hjemme-fanen). Nøklene lagres bare som SHA-256 på PC-en, og
/api/action tar bare imot en fast liste med kommandoer.
"""
import hashlib
import hmac
import ipaddress
import json
import mimetypes
import os
import re
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from gi.repository import GLib

APP_DIR = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(APP_DIR, "remote_web")
PORT = 27100
CFG = os.path.expanduser("~/.config/systemmonitor/fjernstyring.json")
IS_WIN = sys.platform == "win32"
MAX_BODY = 16 * 1024
mimetypes.add_type("application/vnd.android.package-archive", ".apk")
mimetypes.add_type("text/javascript", ".js")


def load_cfg():
    try:
        with open(CFG, encoding="utf-8") as f:
            c = json.load(f)
    except (OSError, ValueError):
        c = {}
    c.setdefault("enabled", False)
    c.setdefault("devices", [])
    return c


def save_cfg(c):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    tmp = CFG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=1)
    os.replace(tmp, CFG)
    try:
        os.chmod(CFG, 0o600)
    except OSError:
        pass


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def local_ips():
    """IPv4-adressene PC-en har på hjemmenettet."""
    out = []
    try:
        import psutil
        import socket
        for name, addrs in psutil.net_if_addrs().items():
            for a in addrs:
                if a.family == socket.AF_INET:
                    ip = ipaddress.ip_address(a.address)
                    if ip.is_private and not ip.is_loopback and not ip.is_link_local:
                        out.append(a.address)
    except Exception:  # noqa: BLE001
        pass
    return sorted(set(out), key=lambda x: (not x.startswith("192.168."), x))


# --------------------------------------------------------------------------
# Tailscale – privat, kryptert nett mellom dine egne enheter (tilgang utenfor hjemmenettet)
# --------------------------------------------------------------------------
TS_NETS = [ipaddress.ip_network("100.64.0.0/10"), ipaddress.ip_network("fd7a:115c:a1e0::/48")]
_TS = {"t": 0, "v": None}


def tailscale_bin():
    import shutil
    if IS_WIN:
        for p in (r"C:\Program Files\Tailscale\tailscale.exe", r"C:\Program Files (x86)\Tailscale\tailscale.exe"):
            if os.path.exists(p):
                return p
        return shutil.which("tailscale")
    return shutil.which("tailscale")


def tailscale_info(force=False):
    """{"installed", "running", "ip", "name", "state", "login"} (hurtigbuffer 30 s)."""
    if not force and time.time() - _TS["t"] < 30 and _TS["v"] is not None:
        return _TS["v"]
    b = tailscale_bin()
    info = {"installed": bool(b), "running": False, "ip": None, "name": None, "state": None}
    if b:
        import winsupport as WS
        code, out = WS.run([b, "status", "--json"], 8)
        try:
            j = json.loads(out[out.find("{"):])
            me = j.get("Self") or {}
            info["state"] = j.get("BackendState")
            info["running"] = j.get("BackendState") == "Running"
            ips = [x for x in me.get("TailscaleIPs") or [] if ":" not in x]
            info["ip"] = ips[0] if ips else None
            info["name"] = (me.get("DNSName") or "").rstrip(".") or None
            info["login"] = (j.get("User") or {}).get(str(me.get("UserID")), {}).get("LoginName")
        except (ValueError, AttributeError):
            pass
    _TS["t"], _TS["v"] = time.time(), info
    return info


def _call_main(fn, timeout=4):
    """Kjør fn i GTK-tråden og vent på svaret (vinduet og kortene er ikke trådsikre)."""
    box, ev = {}, threading.Event()

    def run():
        try:
            box["v"] = fn()
        except Exception as e:  # noqa: BLE001
            box["e"] = e
        ev.set()
        return False
    GLib.idle_add(run)
    if not ev.wait(timeout):
        raise TimeoutError("vinduet svarte ikke")
    if "e" in box:
        raise box["e"]
    return box.get("v")


# --------------------------------------------------------------------------
# Status
# --------------------------------------------------------------------------
def build_status(win):
    import homepcs
    st = homepcs.status(win)
    r = getattr(win, "_remote", {}) or {}
    nv = win.nvidia.data if getattr(win, "nvidia", None) and win.nvidia.available else None
    gpu = None
    if nv:
        gpu = {k: nv.get(k) for k in ("name", "util", "temp", "power", "limit", "fan", "mem_used", "mem_total")}
    power = None
    if getattr(win, "power", None):
        from cards import MODES
        power = {"modes": [[k, n] for k, n, _i, _d in MODES if k in win.power.buttons],
                 "active": win.power.active_profile()}
    fans = None
    fc = getattr(win, "fans", None)
    if fc and fc.rows:
        fans = {"curve": bool(fc.curve_on), "ready": bool(fc.ready()),
                "rows": [{"key": k, "name": row.widgets[0].get_label(), "value": row.value(),
                          "rpm": row.rpm.get_label(), "min": row.min_pct} for k, row in fc.rows.items()]}
    du = None
    try:
        import shutil
        d = shutil.disk_usage(os.path.expanduser("~"))
        du = [d.total - d.free, d.total]
    except OSError:
        pass
    ov = getattr(win, "ov_button", None)
    st.update({
        "os": "windows" if IS_WIN else "linux",
        "cpu": {"load": st.get("cpu_l"), "temp": st.get("cpu_t"), "freq": r.get("freq"),
                "model": getattr(win, "cpu_name", None)},
        "mem": r.get("mem"), "disk": r.get("disk"), "home": du, "net": r.get("net"),
        "temps": [[a, b, round(c, 1)] for a, b, c in r.get("temps", [])],
        "gpu": gpu, "power": power, "fans": fans,
        "overlay": ov.get_active() if ov and ov.get_visible() else None,
        "msi": _is_msi(),
        "cs2": _cs2_live(),
    })
    return st


def _cs2_live():
    try:
        import gamestats
        return gamestats.LIVE.state()
    except Exception:  # noqa: BLE001
        return None


_MSI = {}


def _is_msi():
    if "v" not in _MSI:
        try:
            import msi
            _MSI["v"] = bool(msi.is_msi())
        except Exception:  # noqa: BLE001
            _MSI["v"] = False
    return _MSI["v"]


def audio_state(win):
    if IS_WIN:
        def get():
            import winaudio
            ep = winaudio.Endpoint(0)
            try:
                v, m = ep.get()
                return {"volume": v, "mute": m, "device": ep.name}
            finally:
                ep.close()
        return _call_main(get)
    import audio
    sinks = audio.pjson("sinks")
    code, default = audio.pactl("get-default-sink")
    s = next((x for x in sinks if x.get("name") == default.strip()), sinks[0] if sinks else None)
    if not s:
        return None
    return {"volume": audio.vol_pct(s), "mute": bool(s.get("mute")), "device": s.get("description", "")}


def msi_state():
    if not _is_msi():
        return None
    import msi
    if IS_WIN:
        import winmsi
        r = winmsi.state()
        if not r.get("ok") or not r.get("known"):
            return {"ok": False, "error": r.get("error") or f"ukjent EC-fastvare {r.get('fw', '')}"}
        sc = next((s[0] for s in msi.SCENARIOS if s[3] == r.get("shift") and s[4] == r.get("fan")
                   and (s[5] == "on") == r.get("sb")), None)
        return {"ok": True, "scenario": sc, "boost": r.get("boost"), "charge": r.get("charge"),
                "scenarios": [[s[0], s[1]] for s in msi.SCENARIOS], "charges": [c[0] for c in msi.CHARGE]}
    if not msi.ec_ok():
        return {"ok": False, "error": "msi-ec-driveren mangler"}
    sm, fm, sb = msi.ec("shift_mode"), msi.ec("fan_mode"), msi.ec("super_battery")
    sc = next((s[0] for s in msi.SCENARIOS if s[3] == sm and s[4] == fm and s[5] == (sb or "off")), None)
    ch = None
    for p in msi.batteries():
        ch = msi.read(p)
    return {"ok": True, "scenario": sc, "boost": msi.ec("cooler_boost") == "on",
            "charge": int(ch) if ch and ch.isdigit() else None,
            "scenarios": [[s[0], s[1]] for s in msi.SCENARIOS], "charges": [c[0] for c in msi.CHARGE]}


_GAMES = {"t": 0, "v": []}


def games():
    if time.time() - _GAMES["t"] > 120:
        try:
            import diskusage
            _GAMES["v"] = [{"appid": a, "name": n, "size": s} for a, n, s, _d in diskusage.steam_games()]
        except Exception:  # noqa: BLE001
            _GAMES["v"] = []
        _GAMES["t"] = time.time()
    return _GAMES["v"]


# --------------------------------------------------------------------------
# Oppdatering av Android-appen: NAS-en (Kontrollsenter/Android) er fasit, ellers APK-en PC-en har selv
# --------------------------------------------------------------------------
APK_CACHE = os.path.expanduser("~/.cache/systemmonitor/android/Kontrollsenter.apk")
_APK = {"t": 0, "info": None}
_APK_LOCK = threading.Lock()


def version_code(v):
    try:
        p = (list(map(int, str(v).split("."))) + [0, 0])[:3]
        return p[0] * 10000 + p[1] * 100 + p[2]
    except ValueError:
        return 0


def _local_apk():
    path = os.path.join(WEB, "kontrollsenter.apk")
    if not os.path.isfile(path):
        return None
    try:
        with open(os.path.join(APP_DIR, "VERSION"), encoding="utf-8") as f:
            ver = f.read().strip()
    except OSError:
        return None
    return {"version": ver, "code": version_code(ver), "source": "pc", "path": path}


def apk_info(force=False):
    """Nyeste Android-app: {version, code, source: nas|pc} – eller None."""
    with _APK_LOCK:
        if not force and time.time() - _APK["t"] < 300 and _APK["t"]:
            return _APK["info"]
        nas = None
        try:
            import tempfile
            import lanupdate
            if lanupdate.on_lan():
                tmp = tempfile.mkdtemp()
                try:
                    lanupdate._smb(f'cd "Android"; get versjon.json "{tmp}/v.json"', 30)
                    with open(os.path.join(tmp, "v.json"), encoding="utf-8") as f:
                        nas = json.load(f)
                    nas = {"version": str(nas["version"]), "code": int(nas["code"]), "sha256": nas.get("sha256", ""),
                           "source": "nas"}
                finally:
                    import shutil
                    shutil.rmtree(tmp, ignore_errors=True)
        except Exception:  # noqa: BLE001
            nas = None
        loc = _local_apk()
        best = max((x for x in (nas, loc) if x), key=lambda x: (x["code"], x["source"] == "nas"), default=None)
        _APK["t"], _APK["info"] = time.time(), best
        return best


def apk_path():
    """Filen som skal sendes til telefonen (henter fra NAS-en ved behov, med sjekksum)."""
    info = apk_info()
    if not info:
        return None
    if info["source"] == "pc":
        return info["path"]
    want = info.get("sha256", "")

    def ok(p):
        if not os.path.isfile(p):
            return False
        with open(p, "rb") as f:
            return not want or hashlib.sha256(f.read()).hexdigest() == want
    with _APK_LOCK:
        if not ok(APK_CACHE):
            import lanupdate
            os.makedirs(os.path.dirname(APK_CACHE), exist_ok=True)
            part = APK_CACHE + ".part"
            lanupdate._smb(f'cd "Android"; get Kontrollsenter.apk "{part}"', 120)
            if not ok(part):
                raise RuntimeError("APK-en på NAS-en har feil sjekksum")
            os.replace(part, APK_CACHE)
    return APK_CACHE


# --------------------------------------------------------------------------
# Kommandoer (fast liste)
# --------------------------------------------------------------------------
def _open(uri):
    if IS_WIN:
        os.startfile(uri)
    else:
        subprocess.Popen(["xdg-open", uri], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)


def _system(what):
    if IS_WIN:
        cmds = {"lock": ["rundll32.exe", "user32.dll,LockWorkStation"],
                "sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
                "restart": ["shutdown", "/r", "/t", "5"], "shutdown": ["shutdown", "/s", "/t", "5"]}
    else:
        cmds = {"lock": ["loginctl", "lock-session"], "sleep": ["systemctl", "suspend"],
                "restart": ["systemctl", "reboot"], "shutdown": ["systemctl", "poweroff"]}
    import winsupport as WS  # run() virker på begge systemer
    if what in ("restart", "shutdown", "sleep"):
        threading.Timer(1.5, lambda: WS.run(cmds[what], 30)).start()   # svar appen før PC-en går ned
        return True, "OK"
    code, out = WS.run(cmds[what], 20)
    return code == 0, out.strip()[:200] or "OK"


def do_action(win, a):
    kind = a.get("a")
    if kind == "power":
        key = a.get("mode")

        def go():
            b = win.power.buttons.get(key)
            if not b:
                raise ValueError("ukjent strømmodus")
            b.set_active(True)
        _call_main(go)
        return True, "Strømmodus endret"
    if kind == "fans":
        v = a.get("value")
        if v not in ("auto", "curve") and not (isinstance(v, int) and 0 <= v <= 100):
            raise ValueError("ugyldig viftefart")
        key = a.get("key")

        def go():
            fc = win.fans
            if not fc.ready():
                raise RuntimeError("viftestyringen er ikke klar")
            if key:
                if key not in fc.rows or v == "curve":
                    raise ValueError("ukjent vifte")
                if fc.curve_on:
                    fc.set_curve(False, apply_auto=False)
                fc.rows[key].set_value(v)
            else:
                import automation
                if fc.curve_on and v != "curve":
                    fc.set_curve(False, apply_auto=False)
                automation.apply(win, fans=v)
        _call_main(go)
        return True, "Viftene er endret"
    if kind == "rgb":
        import automation
        mode = a.get("mode")
        if mode == "off":
            automation.rgb_set(None)
        elif mode == "color" and re.fullmatch(r"#?[0-9a-fA-F]{6}", str(a.get("color", ""))):
            automation.rgb_set(automation.hex_rgb(a["color"]))
        elif mode == "restore":
            automation.rgb_restore()
        else:
            raise ValueError("ugyldig RGB-kommando")
        return True, "RGB endret"
    if kind == "overlay":
        on = bool(a.get("on"))
        _call_main(lambda: win.ov_button.set_active(on))
        return True, "Overlay " + ("på" if on else "av")
    if kind == "volume":
        vol, mute = a.get("volume"), a.get("mute")
        if vol is not None and not (isinstance(vol, int) and 0 <= vol <= 100):
            raise ValueError("ugyldig volum")
        if IS_WIN:
            def go():
                import winaudio
                ep = winaudio.Endpoint(0)
                try:
                    if vol is not None:
                        ep.set_volume(vol)
                    if mute is not None:
                        ep.set_mute(bool(mute))
                finally:
                    ep.close()
            _call_main(go)
        else:
            import audio
            if vol is not None:
                audio.pactl("set-sink-volume", "@DEFAULT_SINK@", f"{vol}%")
            if mute is not None:
                audio.pactl("set-sink-mute", "@DEFAULT_SINK@", "1" if mute else "0")
        return True, "Lyd endret"
    if kind == "msi":
        return _msi_action(a)
    if kind == "game":
        appid = str(a.get("appid", ""))
        if not appid.isdigit():
            raise ValueError("ugyldig spill")
        _open(f"steam://rungameid/{appid}")
        return True, "Starter spillet"
    if kind == "system":
        what = a.get("do")
        if what not in ("lock", "sleep", "restart", "shutdown"):
            raise ValueError("ukjent systemkommando")
        return _system(what)
    if kind == "show":
        _call_main(lambda: win.get_application().activate())
        return True, "Vinduet vises"
    raise ValueError("ukjent kommando")


def _msi_action(a):
    import msi
    if not _is_msi():
        raise ValueError("ikke en MSI-maskin")
    if "scenario" in a:
        s = next((x for x in msi.SCENARIOS if x[0] == a["scenario"]), None)
        if not s:
            raise ValueError("ukjent brukerscenario")
        _k, _n, _d, sm, fm, sb = s
        if IS_WIN:
            import winmsi
            r = winmsi.scenario(sm, fm, sb)
            return bool(r.get("ok")), r.get("error") or f"{_n} ✓"
        errs = [e for ok, e in (msi.helper("set", "shift_mode", sm), msi.helper("set", "fan_mode", fm),
                                msi.helper("set", "super_battery", sb)) if not ok]
        return not errs, (errs[0] if errs else f"{_n} ✓")
    if "boost" in a:
        on = bool(a["boost"])
        if IS_WIN:
            import winmsi
            r = winmsi.set_bit(winmsi.A_BOOST, on)
            return bool(r.get("ok")), r.get("error") or "OK"
        ok, err = msi.helper("set", "cooler_boost", "on" if on else "off")
        return ok, err or "OK"
    if "charge" in a:
        v = a["charge"]
        if v not in [c[0] for c in msi.CHARGE]:
            raise ValueError("ugyldig ladegrense")
        if IS_WIN:
            import winmsi
            r = winmsi.set_charge(v)
            return bool(r.get("ok")), r.get("error") or "OK"
        ok, err = msi.helper("charge", str(v))
        return ok, err or "OK"
    raise ValueError("ukjent MSI-kommando")


# --------------------------------------------------------------------------
# Nettjenesten
# --------------------------------------------------------------------------
INSTANCE = None          # settes av bakgrunnsdelen (background.py)


class Remote:
    def __init__(self, win):
        self.win = win
        self.httpd = None
        self.code = None
        self.code_until = 0
        self.code_tries = 0
        self.lock = threading.Lock()
        self.on_paired = None          # kalles i GTK-tråden når en enhet er paret

    @property
    def running(self):
        return self.httpd is not None

    def start(self):
        if self.httpd:
            return True, ""
        try:
            self.httpd = ThreadingHTTPServer(("0.0.0.0", PORT), _handler(self))
        except OSError as e:
            self.httpd = None
            return False, f"Port {PORT} er opptatt ({e})"
        self.httpd.daemon_threads = True
        threading.Thread(target=self.httpd.serve_forever, daemon=True, name="fjernstyring").start()
        return True, ""

    def stop(self):
        if self.httpd:
            h, self.httpd = self.httpd, None
            threading.Thread(target=lambda: (h.shutdown(), h.server_close()), daemon=True).start()

    def new_code(self):
        with self.lock:
            self.code = f"{secrets.randbelow(1_000_000):06d}"
            self.code_until = time.time() + 300
            self.code_tries = 0
            return self.code

    def pair(self, code, device):
        with self.lock:
            if not self.code or time.time() > self.code_until:
                return None, "Ingen gyldig kode – trykk «Par ny enhet» på PC-en"
            self.code_tries += 1
            if self.code_tries > 5:
                self.code = None
                return None, "For mange forsøk – lag en ny kode på PC-en"
            if not hmac.compare_digest(str(code).strip(), self.code):
                return None, "Feil kode"
            self.code = None
            token = secrets.token_urlsafe(32)
            c = load_cfg()
            name = re.sub(r"[^\w .,'()-]", "", str(device or "Enhet"))[:40] or "Enhet"
            c["devices"].append({"name": name, "hash": _hash(token), "added": int(time.time()), "last": 0})
            save_cfg(c)
        if self.on_paired:
            GLib.idle_add(lambda: (self.on_paired(name), False)[1])
        return token, "OK"

    def check(self, token):
        if not token:
            return None
        h = _hash(token)
        c = load_cfg()
        for d in c["devices"]:
            if hmac.compare_digest(d.get("hash", ""), h):
                if time.time() - d.get("last", 0) > 60:
                    d["last"] = int(time.time())
                    save_cfg(c)
                return d
        return None


def _handler(remote):
    class H(BaseHTTPRequestHandler):
        server_version = "Kontrollsenter"
        sys_version = ""

        def log_message(self, *a):           # ingen utskrift per forespørsel
            pass

        # ---- hjelpere ----
        def _allowed(self):
            try:
                ip = ipaddress.ip_address(self.client_address[0])
                if ip.version == 6 and ip.ipv4_mapped:
                    ip = ip.ipv4_mapped
                return ip.is_private or ip.is_loopback or any(ip in n for n in TS_NETS)
            except ValueError:
                return False

        def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Private-Network", "true")   # Chrome/WebView: lokalt nett
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                raise ValueError("for stor forespørsel")
            raw = self.rfile.read(n) if n else b"{}"
            v = json.loads(raw or b"{}")
            if not isinstance(v, dict):
                raise ValueError("forventet et JSON-objekt")
            return v

        def _auth(self):
            h = self.headers.get("Authorization", "")
            tok = h[7:].strip() if h.startswith("Bearer ") else ""
            if remote.check(tok):
                return True
            self._send(401, {"error": "ikke paret"})
            return False

        # ---- metoder ----
        def do_OPTIONS(self):
            self._send(204, b"", "text/plain")

        def do_GET(self):
            if not self._allowed():
                return self._send(403, {"error": "bare hjemmenettet"})
            u = urlparse(self.path)
            p = u.path
            try:
                if p in ("/", "/app"):
                    return self._send(302, b"", "text/plain", {"Location": "/app/"})
                if p.startswith("/app/"):
                    if not os.path.isdir(WEB):
                        return self._missing_web()
                    return self._static(p[5:] or "index.html")
                if p == "/api/appupdate":                 # åpen: bare versjonsnummeret til appen
                    force = (parse_qs(u.query).get("force") or ["0"])[0] == "1"
                    info = apk_info(force)
                    return self._send(200, {k: v for k, v in (info or {}).items() if k in ("version", "code",
                                                                                         "source")})
                if p == "/api/apk":
                    path = apk_path()
                    if not path:
                        return self._send(404, {"error": "fant ingen app"})
                    with open(path, "rb") as f:
                        return self._send(200, f.read(), "application/vnd.android.package-archive",
                                          {"Content-Disposition": 'attachment; filename="Kontrollsenter.apk"'})
                if p == "/api/hello":
                    import applog
                    import savegames
                    ts = tailscale_info()
                    return self._send(200, {"app": "Kontrollsenter", "name": savegames.pc_name(),
                                            "version": applog.RUNNING, "os": "windows" if IS_WIN else "linux",
                                            "lan": local_ips(),
                                            "ts": {"ip": ts["ip"], "name": ts["name"]} if ts["running"] else None})
                if not self._auth():
                    return
                if p == "/api/status":
                    return self._send(200, _call_main(lambda: build_status(remote.win)))
                if p == "/api/extra":
                    out = {}
                    for k, fn in (("audio", lambda: audio_state(remote.win)), ("msi", msi_state)):
                        try:
                            out[k] = fn()
                        except Exception as e:  # noqa: BLE001
                            out[k] = {"ok": False, "error": str(e)}
                    return self._send(200, out)
                if p == "/api/history":
                    import history
                    s = int((parse_qs(u.query).get("s") or ["3600"])[0])
                    s = max(600, min(s, 8 * 86400))
                    return self._send(200, {"cols": ["ts", "cpu_t", "gpu_t", "cpu_l", "gpu_l", "watts"],
                                            "rows": history.query(s, buckets=240)})
                if p == "/api/games":
                    return self._send(200, {"games": games()})
                if p == "/api/gamestats":
                    import gamestats
                    return self._send(200, gamestats.snapshot())
                return self._send(404, {"error": "finnes ikke"})
            except Exception as e:  # noqa: BLE001
                return self._send(500, {"error": str(e)})

        do_HEAD = do_GET

        def do_POST(self):
            if not self._allowed():
                return self._send(403, {"error": "bare hjemmenettet"})
            p = urlparse(self.path).path
            try:
                body = self._body()
                if p == "/api/pair":
                    token, msg = remote.pair(body.get("code", ""), body.get("device", ""))
                    if not token:
                        time.sleep(1)                       # bremser gjetting
                        return self._send(403, {"error": msg})
                    import savegames
                    return self._send(200, {"token": token, "name": savegames.pc_name()})
                if not self._auth():
                    return
                if p == "/api/action":
                    ok, msg = do_action(remote.win, body)
                    return self._send(200, {"ok": bool(ok), "msg": str(msg)})
                return self._send(404, {"error": "finnes ikke"})
            except (ValueError, KeyError) as e:
                return self._send(400, {"ok": False, "error": str(e)})
            except Exception as e:  # noqa: BLE001
                return self._send(500, {"ok": False, "error": str(e)})

        def _missing_web(self):
            html = ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
                    "<body style='font:17px system-ui;padding:24px;background:#1e1e24;color:#eee'>"
                    "<h2>Kontrollpanelet mangler på PC-en</h2><p>Kontrollsenter på denne PC-en mangler mappen "
                    "<b>remote_web</b> (oppdateringen fra en eldre versjon tok den ikke med). Start Kontrollsenter "
                    "på nytt på PC-en mens den er på hjemmenettet – da hentes den fra NAS-en automatisk – eller "
                    "oppdater Kontrollsenter i Verktøy.</p></body>")
            return self._send(503, html.encode(), "text/html; charset=utf-8")

        def _static(self, rel):
            rel = os.path.normpath(rel).replace("\\", "/")
            if rel.startswith("..") or os.path.isabs(rel):
                return self._send(404, {"error": "finnes ikke"})
            path = os.path.join(WEB, rel)
            if not os.path.isfile(path):
                return self._send(404, {"error": "finnes ikke"})
            ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
                ctype += "; charset=utf-8"
            with open(path, "rb") as f:
                return self._send(200, f.read(), ctype)
    return H
