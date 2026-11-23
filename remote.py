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
    """Kjør fn i GTK-tråden og vent på svaret (vinduet og kortene er ikke trådsikre).
    Kalles den fra GTK-tråden selv (f.eks. en knapp i vinduet eller en hurtigkommando), kjøres fn direkte –
    ellers ville den vente på seg selv til tidsavbruddet («vinduet svarte ikke»)."""
    if threading.current_thread() is threading.main_thread():
        return fn()
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
        "gpu": gpu, "power": power, "fans": fans, "info": _info(), "fps": _live_fps(win), "tasks": _tasks(),
        "overlay": ov.get_active() if ov and ov.get_visible() else None,
        "msi": _is_msi(),
        "cs2": _cs2_live(),
        "gamemode": bool(INSTANCE and INSTANCE.gamemode.on),
        "batteries": _batteries(),
        "timer": INSTANCE.timer.state() if INSTANCE else None,
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
        if nas is None:
            try:                                          # borte: via en venn-PC hjemme
                import lanupdate
                if not lanupdate.on_lan():
                    import relayupdate
                    r = relayupdate.remote(force)
                    a = (r or {}).get("apk") or {}
                    if a.get("code"):
                        nas = {"version": str(a["version"]), "code": int(a["code"]), "sha256": a.get("sha256", ""),
                               "source": "venn"}
            except Exception:  # noqa: BLE001
                pass
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
            if info["source"] == "venn":
                import relayupdate
                relayupdate.download("apk", part)
            else:
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
    import remote_extra as X
    if kind == "gamemode":
        col = a.get("color")
        if col and not re.fullmatch(r"#?[0-9a-fA-F]{6}", str(col)):
            raise ValueError("ugyldig farge")
        _call_main(lambda: INSTANCE.gamemode.set(bool(a.get("on")), col and __import__("automation").hex_rgb(col)))
        return True, "Spillmodus " + ("på" if a.get("on") else "av")
    if kind == "timer":
        mins = a.get("minutes")
        if mins is not None and not (isinstance(mins, int) and 1 <= mins <= 24 * 60):
            raise ValueError("ugyldig tid")
        _call_main(lambda: INSTANCE.timer.set(mins, a.get("when_idle")))
        return True, "Planlagt avslåing er satt" if mins or a.get("when_idle") else "Avbrutt"
    if kind == "kill":
        n = X.kill(str(a.get("name", "")))
        return True, f"Avsluttet ({n})"
    if kind == "media":
        X.media_cmd(a.get("cmd"), a.get("player"))
        return True, "OK"
    if kind == "appvolume":
        X.set_app_volume(a.get("id"), a.get("volume"), a.get("mute"))
        return True, "OK"
    if kind == "open_url":
        X.open_url(a.get("url"))
        return True, "Lenken er åpnet på PC-en"
    if kind == "clipboard":
        txt = str(a.get("text", ""))
        _call_main(lambda: X.set_clipboard(txt))
        return True, "Kopiert til PC-ens utklippstavle"
    if kind == "backup":
        X.backup_now()
        return True, "Sikkerhetskopien er startet"
    if kind == "syscheck":
        _call_main(lambda: (win.get_application().activate(), win._open_syscheck(None)))
        return True, "Systemsjekk er åpnet på PC-en"
    if kind == "clip":
        import clips
        if not clips.INSTANCE:
            raise RuntimeError("klipp er ikke klart")
        ok, msg = clips.INSTANCE.save()
        return ok, msg
    if kind == "clipcfg":
        import clips
        clips.set_cfg(a.get("enabled"), a.get("length"), a.get("only_games"))
        return True, "Lagret"
    if kind == "clipkey":
        import clips
        spec = str(a.get("key", ""))
        _call_main(lambda: clips.set_hotkey(spec))
        return True, f"Hurtigtasten er {spec}"
    if kind == "cliptest":
        import clips
        _call_main(lambda: clips.test_hotkey(15))
        return True, "Trykk hurtigtasten på PC-en nå"
    if kind == "clipdel":
        import clipx
        clipx.delete(str(a.get("name", "")))
        return True, "Slettet"
    if kind == "clipfav":
        import clipx
        clipx.set_fav(str(a.get("name", "")), bool(a.get("on")))
        return True, "Favoritt" if a.get("on") else "Ikke favoritt"
    if kind == "clipexport":
        import clipx
        opts = {k: a[k] for k in ("start", "end", "seconds", "text", "area") if k in a}
        jid = clipx.export(str(a.get("name", "")), str(a.get("kind", "")), **opts)
        return True, f"Jobb startet ({jid})"
    if kind == "clipmontage":
        import clipx
        names = [str(x) for x in (a.get("names") or [])][:20]
        jid = clipx.montage(names, a.get("music") or None, str(a.get("title") or "Montasje")[:40])
        return True, f"Montasjen lages ({jid})"
    if kind == "clipweekly":
        import clipx
        clipx.weekly()
        return True, "«Beste fra uka» lages – den dukker opp blant klippene"
    if kind == "clipshare":
        import clipx
        import urllib.parse as up
        name, pc = str(a.get("name", "")), str(a.get("pc", ""))
        if not (clipx.any_path(name) or pc):
            raise ValueError("fant ikke klippet")
        tok = clipx.share_token(f"{pc}/{name}" if pc else name)
        q = f"name={up.quote(name)}&s={tok}" + (f"&pc={up.quote(pc)}" if pc else "")
        return True, f"/api/clipfile?{q}"
    if kind == "clipopts":
        import clips
        opts = {k: v for k, v in a.items() if k != "a"}
        clips.set_options(**opts)
        return True, "Lagret"
    if kind == "clipextrakey":
        import clips
        which, spec = str(a.get("which", "")), str(a.get("key", ""))
        _call_main(lambda: clips.set_extra_key(which, spec))
        return True, "Hurtigtasten er lagret"
    if kind == "cliprecord":
        import clips
        return clips.INSTANCE.toggle_record() if clips.INSTANCE else (False, "ikke klart")
    if kind == "clipshot":
        import clipx
        import clips
        return clipx.screenshot(clips.INSTANCE.game if clips.INSTANCE else None)
    if kind == "wol":
        X.send_wol(a.get("mac"))
        return True, "Wake-on-LAN er sendt"
    if kind == "wowgoal":
        lvl = a.get("level")
        if lvl is not None and not (isinstance(lvl, int) and 1 <= lvl <= 200):
            raise ValueError("ugyldig level")
        X.set_wow_goal(str(a.get("key", ""))[:100], lvl, a.get("by"))
        return True, "Målet er lagret"
    if kind == "playlimits":
        c = X.limit_cfg()
        for k in ("weekday", "weekend"):
            if k in a:
                v = float(a[k])
                if not 0 < v <= 24:
                    raise ValueError("ugyldig grense")
                c[k] = v
        if "enabled" in a:
            c["enabled"] = bool(a["enabled"])
        X._jsave(X.LIMITS, c)
        return True, "Grensene er lagret"
    return _feature_action(win, kind, a)


def _feature_action(win, kind, a):
    import features as F
    if kind == "chat":
        F.send_to(a.get("to"), a.get("_dev") or "Mobil", a.get("text"), _notify(win), urgent=bool(a.get("urgent")))
        return True, "Sendt"
    if kind == "chat2":                                  # chat for alle: hjemme, alle, privat
        import chat
        return True, chat.send(str(a.get("room") or "alle"), a.get("text"), a.get("_dev") or None, _notify(win))
    if kind == "chatvote":                               # stemme i en avstemning fra mobilen
        import chat
        import chatplus
        room = str(a.get("room") or "")
        m = next((x for x in chat.messages(room, 300) if x.get("id") == a.get("mid")), None)
        if not m:
            raise ValueError("fant ikke avstemningen")
        chatplus.vote(room, m, int(a.get("idx", 0)))
        return True, "Stemt ✓"
    if kind == "dinner":
        F.send_to(a.get("to") or "*", a.get("_dev") or "Mobil", a.get("text") or "🍽️ Middag! Kom og spis.",
                  _notify(win), urgent=True)
        try:                                              # trapper opp etter 5 min (lyd ned + RGB blinker)
            import familyfun
            familyfun.dinner_sent()
        except Exception:  # noqa: BLE001
            pass
        return True, "«Middag!» er sendt"
    if kind == "bedtime":
        c = F.cfg()
        for k in ("weekday", "weekend"):
            if k in a:
                if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(a[k])):
                    raise ValueError("ugyldig klokkeslett")
                c["bedtime"][k] = a[k]
        if "enabled" in a:
            c["bedtime"]["enabled"] = bool(a["enabled"])
        F.save_cfg(c)
        return True, "Leggetiden er lagret"
    if kind == "bonus":
        F.give_bonus(int(a.get("minutes", 0)))
        return True, f"{int(a['minutes'])} min ekstra i dag"
    if kind == "feature":                                   # brytere: auto_update, wishlist
        c = F.cfg()
        k = a.get("key")
        if k not in ("auto_update", "wishlist"):
            raise ValueError("ukjent innstilling")
        c[k] = bool(a.get("on"))
        F.save_cfg(c)
        return True, "Lagret"
    if kind == "setbackup":
        return True, "Sikkerhetskopiert: " + F.backup_settings()
    if kind == "restore":
        F.restore_settings(str(a.get("name", "")))
        return True, "Gjenopprettet – start Kontrollsenter på nytt"
    if kind == "report":
        return (True, "Feilrapporten er lagt på NAS-en") if F.send_report(str(a.get("note", ""))[:2000]) \
            else (False, "Kunne ikke sende (er PC-en på hjemmenettet?)")
    if kind == "startup":
        F.startup_set(str(a.get("id", "")), bool(a.get("on")))
        return True, "Lagret – gjelder fra neste oppstart"
    if kind == "lanname":
        F.name_device(str(a.get("mac", "")).lower(), a.get("name", ""))
        return True, "Navnet er lagret"
    if kind == "stream":
        import streaming as ST
        do = a.get("do")
        fn = {"start": ST.sunshine_start, "stop": ST.sunshine_stop, "restart": ST.sunshine_restart}.get(do)
        if not fn:
            raise ValueError("ukjent kommando")
        threading.Thread(target=fn, daemon=True).start()
        return True, {"start": "Sunshine starter (tar ca. 20 sekunder)", "stop": "Sunshine stoppes",
                      "restart": "Sunshine starter på nytt"}[do]
    if kind == "streampin":
        import streaming as ST
        ST.pair(a.get("pin", ""), a.get("_dev") or "Telefon")
        return True, "Paret ✓ – Moonlight er klar"
    if kind == "rustdesk":
        import streaming as ST
        ST.rustdesk_open()
        return True, "RustDesk er startet på PC-en"
    if kind == "wowplus":                        # slå WoW-ekstra av/på (alt, eller én funksjon)
        import wowplus
        feat = a.get("feature") or None
        wowplus.set_option(feat, bool(a.get("on")))
        return True, "Lagret – skriv /reload i WoW (eller logg inn på nytt) for at addonen skal bruke det"
    if kind == "wowhide":                        # fjern en slettet WoW-karakter fra statistikken
        import gamestats
        key = str(a.get("key") or "")
        c = next((c for c in gamestats.wow_stats() if c.get("key") == key), None)
        if not c:
            return False, "Fant ikke karakteren"
        gamestats.wow_hide(key, c.get("last_seen"))
        return True, f"{c.get('name')} er fjernet fra listen – den kommer tilbake hvis du spiller med den igjen"
    if kind == "uilog":                          # appen melder at noe er bredere enn skjermen (for feilsøking)
        import applog
        items = [str(x)[:160] for x in (a.get("items") or [])][:8]
        applog.log.warning("Appen: for bredt på fanen %s (%s px): %s", str(a.get("tab"))[:20],
                           str(a.get("width"))[:6], " | ".join(items))
        return True, "OK"
    if kind == "pcupdate":                       # oppdater Kontrollsenter på denne PC-en fra NAS-en
        import lanupdate as L
        import tools
        st, new = L.check()
        if not new:
            return True, st
        ok, msg = L.apply_update(tools.PACKAGE_FILES)
        if ok:
            GLib.timeout_add_seconds(3, lambda: (win.restart_app(), False)[1])
            return True, f"Oppdatert til {new} – Kontrollsenter starter på nytt på PC-en"
        return False, msg
    if kind == "familylock":
        import familylock
        if a.get("on"):
            familylock.set_pin(str(a.get("pin", "")))
            return True, "Familiekontroll er på – koden trengs for å lukke Kontrollsenter"
        familylock.turn_off()
        return True, "Familiekontroll er slått av (koden er fjernet)"
    if kind == "watchallow":
        import watch as W
        c = W.cfg()
        c["allow"] = bool(a.get("on"))
        W.save_cfg(c)
        return True, "Lagret"
    if kind == "headsetinstall":
        import batteries
        return batteries.install_headsetcontrol()
    if kind == "notify":                         # varselvalg på PC-en fra mobilappen
        import background as B
        kid, on = str(a.get("kind") or ""), bool(a.get("on"))
        if kid != "all" and kid not in {k[0] for k in B.KINDS}:
            raise ValueError("ukjent varseltype")

        def go():
            bg = getattr(win, "bg", None)
            cfg = bg.cfg if bg else B.load()
            if kid == "all":
                val, key = on, "notify"
            else:
                val, key = {**(cfg.get("kinds") or {}), kid: on}, "kinds"
            if bg:
                bg.set(key, val)
            else:
                cfg[key] = val
                B.save(cfg)
        _call_main(go)
        return True, "Varsler på PC-en: " + ("på" if on else "av")
    if kind == "discord":                        # Discord: mikrofon, lyd av, volum, enheter, demping …
        import funksjoner
        if not funksjoner.on("discord"):
            return False, "Discord er slått av i Kontrollsenter (Innstillinger → Funksjoner)"
        import discord_ctl
        return True, discord_ctl.action(a)
    if kind == "goal_req":                       # «ferdig med lekser» – barna kan be om ekstra spilletid
        import features as F
        return True, F.goal_request(str(a.get("goal", "")), a.get("_dev") or "Mobil")
    if kind == "panel":                          # PC-funksjoner fra appen (apppanels)
        import apppanels
        return True, apppanels.run(win, a)
    if kind == "friend":                         # legg til / fjern venn, del av/på (bare full tilgang)
        import friends
        do = str(a.get("do", ""))
        if do == "add":
            f = friends.add_friend(str(a.get("invite", "")), a.get("name"))
            return True, f"{f['name']} er lagt til ✓"
        if do == "remove":
            friends.remove_friend(str(a.get("addr", "")))
            return True, "Fjernet"
        if do == "share":
            friends.set_share(on=bool(a.get("on")))
            return True, "Deling " + ("på ✓" if a.get("on") else "av")
        raise ValueError("ukjent")
    if kind == "vr":                             # VR fra mobilen: start / fiks alt / stopp
        import vr
        do = str(a.get("do", ""))
        if do == "start":
            return True, vr.start(a.get("mode") or None)
        if do == "fixall":
            return True, "; ".join(f"{t}: {m}" for t, m in vr.fix_all(mode=a.get("mode") or None)) or "Alt er klart ✓"
        if do == "stop":
            return True, vr.stop()
        if do == "noop":
            return True, ""
        if do == "engine" and a.get("engine") in ("alvr", "wivrn"):
            vr.save_cfg(engine=a["engine"])
            return True, ("WiVRn" if a["engine"] == "wivrn" else "ALVR") + " er valgt"
        raise ValueError("ukjent VR-handling")
    if kind == "push":                           # slå ntfy-push av/på (bare full tilgang)
        import push
        if a.get("new_topic"):
            push.new_topic()
        if "on" in a:
            push.set_enabled(bool(a["on"]))
        return True, "Pushvarsler " + ("på ✓" if push.enabled() else "av")
    if kind == "dnsfilter":                      # nettfilter (familie-DNS) – bare full tilgang
        import familysafe
        return True, familysafe.set_dns(a.get("provider") or None)
    if kind == "school":                         # leksetid
        import familysafe
        kw = {k: a[k] for k in ("enabled", "days", "from", "to") if k in a}
        familysafe.set_school(**kw)
        return True, "Leksetid lagret ✓"
    if kind == "avprofile":                      # lyd-/skjermprofil (mobilen og scener)
        import avprofiles as P
        k, pid = str(a.get("kind", "")), str(a.get("id", ""))
        if k == "audio":
            return True, P.apply_audio(pid)
        if k == "display":
            return True, P.apply_display(pid)
        raise ValueError("ukjent profiltype")
    if kind == "nightlight":
        import avprofiles as P
        return True, P.set_night(bool(a.get("on")), a.get("temp"))
    if kind == "brightness":
        import avprofiles as P
        return True, P.set_brightness(int(a.get("value", 50)))
    if kind == "plan_add":                       # ny avtale i familiens ukeplan
        import familyplus
        return True, familyplus.plan_add(a.get("day", 0), str(a.get("at", "")), str(a.get("text", "")),
                                         str(a.get("who", "*")), int(a.get("remind", 10)))
    if kind == "plan_del":
        import familyplus
        return True, familyplus.plan_del(str(a.get("id", "")))
    if kind == "shop_req":                       # løs inn stjerner (må godkjennes)
        import familyplus
        return True, familyplus.shop_request(str(a.get("item", "")), a.get("_dev") or "Mobil")
    if kind == "shop_ok":
        import familyplus
        return True, familyplus.shop_answer(str(a.get("id", "")), bool(a.get("ok")))
    if kind == "goal_ok":                        # foreldrene godkjenner eller avslår
        import features as F
        return True, F.goal_answer(str(a.get("id", "")), bool(a.get("ok")))
    if kind == "scene":                          # kjør en scene fra mobilappen
        import scenes
        name = scenes.run(win, str(a.get("id", "")))
        return True, f"«{name}» settes …"
    if kind == "smart":
        import smarthome
        return True, smarthome.action(a)
    if kind == "huepair":
        F.hue_pair()
        return True, "Hue er koblet til"
    if kind == "hue":
        col = a.get("color")
        if col and not re.fullmatch(r"#?[0-9a-fA-F]{6}", col):
            raise ValueError("ugyldig farge")
        F.hue_set(a.get("on"), col, a.get("ids"))
        return True, "OK"
    raise ValueError("ukjent kommando")


def _live_fps(win):
    """Siste FPS fra spillet som kjører (MangoHud), eller None."""
    try:
        ses = win.bg.auto.session
        return round(ses.fps_hist[-1]) if ses and ses.fps_hist else None
    except Exception:  # noqa: BLE001
        return None


def house_update(win):
    """Oppdater denne PC-en fra NAS-en og start Kontrollsenter på nytt (bedt om av en annen PC hjemme)."""
    import applog
    import lanupdate as L
    import tools
    if L.is_source_pc():
        return {"ok": True, "msg": "utviklings-PC-en – oppdateres ikke herfra", "version": applog.RUNNING}
    try:
        st, new = L.check()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "msg": f"fikk ikke sjekket NAS-en: {e}", "version": applog.RUNNING}
    if new:
        ok, msg = L.apply_update(tools.PACKAGE_FILES)
        if not ok:
            return {"ok": False, "msg": msg, "version": applog.RUNNING}
        GLib.timeout_add_seconds(2, lambda: (win.restart_app(), False)[1])
        return {"ok": True, "msg": f"oppdatert til {new} – starter på nytt", "version": new, "restart": True}
    if applog.needs_restart():                        # ny versjon er installert, men den gamle kjører fortsatt
        GLib.timeout_add_seconds(2, lambda: (win.restart_app(), False)[1])
        return {"ok": True, "msg": f"starter på nytt med {applog.needs_restart()}", "version": applog.needs_restart(),
                "restart": True}
    return {"ok": True, "msg": "har allerede nyeste versjon", "version": applog.RUNNING}


def _tasks():
    """Det PC-en holder på med akkurat nå (fremdriftslinjen) – vises også i appen."""
    try:
        import progress
        return [{"title": t.title, "detail": t.detail, "pct": None if t.frac is None else round(t.frac * 100),
                 "eta": t.eta_text(), "done": bool(t.finished), "ok": t.ok, "result": t.result}
                for t in progress.active()]
    except Exception:  # noqa: BLE001
        return []


def _info():
    try:
        import infotiles
        return infotiles.snapshot()
    except Exception:  # noqa: BLE001
        return None


def _batteries():
    try:
        import batteries
        return {"devices": batteries.cached(), "headsetcontrol": bool(batteries.headsetcontrol_bin())}
    except Exception:  # noqa: BLE001
        return {"devices": [], "headsetcontrol": False}


def _notify(win):
    bg = getattr(win, "bg", None)
    return bg.notify if bg else None


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
WEB_TYPES = {".html": "text/html", ".htm": "text/html", ".css": "text/css", ".js": "application/javascript",
             ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
             ".jpeg": "image/jpeg", ".webp": "image/webp", ".ico": "image/x-icon", ".woff2": "font/woff2",
             ".apk": "application/vnd.android.package-archive"}


LIMITED_OK = {"game", "volume", "media", "appvolume", "open_url", "clipboard", "show", "clip", "chat", "chat2", "chatvote", "uilog",
              "goal_req", "shop_req"}   # «begrenset» tilgang


class Remote:
    def __init__(self, win):
        self.win = win
        self.pair_role = "full"
        import remote_extra as X
        self.timer = X.ShutdownTimer(win)
        self.gamemode = X.GameMode(win)
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

    def new_code(self, role="full"):
        self.pair_role = role if role in ("full", "begrenset") else "full"
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
            c["devices"].append({"name": name, "hash": _hash(token), "added": int(time.time()), "last": 0,
                                 "role": self.pair_role})
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

        def _body(self, limit=MAX_BODY):
            n = int(self.headers.get("Content-Length") or 0)
            if n > limit:
                raise ValueError("for stor forespørsel")
            raw = self.rfile.read(n) if n else b"{}"
            v = json.loads(raw or b"{}")
            if not isinstance(v, dict):
                raise ValueError("forventet et JSON-objekt")
            return v

        def _local(self):
            """Bare programmer på denne PC-en (ikke nettsider i nettleseren – de sender Origin og kan ikke
            sende hodet X-KS-Local uten at nettleseren spør først, noe vi ikke svarer ja til)."""
            ip = self.client_address[0]
            return (ip in ("127.0.0.1", "::1", "::ffff:127.0.0.1") and self.headers.get("X-KS-Local") == "1"
                    and not self.headers.get("Origin"))

        def _remote_on(self):
            """Fjernstyring fra mobilen er slått av: tjenesten kjører bare for chatten (egne nøkler)."""
            if load_cfg()["enabled"]:
                return True
            self._send(403, {"error": "Fjernstyring er slått av på denne PC-en (Hjemme-fanen)"})
            return False

        def _auth(self):
            if not self._remote_on():
                return False
            h = self.headers.get("Authorization", "")
            tok = h[7:].strip() if h.startswith("Bearer ") else ""
            d = remote.check(tok)
            if d:
                try:
                    import presence
                    presence.seen_api(self.client_address[0])
                except Exception:  # noqa: BLE001
                    pass
            if d:
                self.device = d
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
                m_ntfy = re.fullmatch(r"/(ks[A-Za-z0-9]{20,60})/(json|raw)", p)
                if m_ntfy:                                # ntfy-appen på telefonen (pushvarsler)
                    import push
                    if not push.enabled() or m_ntfy.group(1) != push.topic():
                        return self._send(404, {"error": "finnes ikke"})
                    q = parse_qs(u.query)
                    sp = (q.get("since") or [""])[0]
                    if (q.get("poll") or ["0"])[0] in ("1", "true", "yes"):
                        body = "".join(json.dumps(push._clean(m), ensure_ascii=False) + "\n"
                                       for m in push.since(sp or "all")).encode()
                        return self._send(200, body, "application/x-ndjson; charset=utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    try:
                        push.stream(self.wfile, m_ntfy.group(1), sp or None)
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        pass
                    return
                if p == "/api/cover":                    # spill-cover til appen (nøkkel i adressen)
                    q = parse_qs(u.query)
                    if not remote.check((q.get("k") or [""])[0]):
                        return self._send(401, {"error": "ikke paret"})
                    import apppanels
                    cp = apppanels.cover_path((q.get("id") or [""])[0])
                    if not cp or not os.path.exists(cp):
                        return self._send(404, {"error": "finnes ikke"})
                    with open(cp, "rb") as f:
                        return self._send(200, f.read(), "image/jpeg", {"Cache-Control": "max-age=86400"})
                if p in ("/api/house/status", "/api/house/update", "/api/house/updates", "/api/house/updateall",
                         "/api/house/auto", "/api/house/system", "/api/house/family"):            # PC-ene hjemme (felles husnøkkel)
                    import watch as W
                    q = parse_qs(u.query)
                    if not W.check_house_key((q.get("fk") or [""])[0]):
                        return self._send(403, {"error": "feil husnøkkel"})
                    if p == "/api/house/status":
                        import friends
                        return self._send(200, friends.snapshot(remote.win, full=True))
                    if p == "/api/house/family":           # gi tid / pause / middag trinn 2 (fra mobilen via huset)
                        import familyfun
                        try:
                            msg = familyfun.house_action(remote.win, (q.get("do") or [""])[0],
                                                         **{k: v[0] for k, v in q.items() if k not in ("fk", "do")})
                            return self._send(200, {"ok": True, "msg": msg})
                        except ValueError as e:
                            return self._send(400, {"error": str(e)})
                    if p == "/api/house/system":           # dvale / slå av / omstart (sovemodus, glemte PC-er)
                        what = (q.get("do") or [""])[0]
                        if what not in ("sleep", "shutdown", "restart", "lock"):
                            return self._send(400, {"error": "ukjent"})
                        ok, msg = _system(what)
                        return self._send(200, {"ok": ok, "msg": msg})
                    import updates as UPD
                    if p == "/api/house/updates":       # oppdateringer på denne PC-en (r=1: sjekk på nytt)
                        if (q.get("r") or [""])[0] == "1":
                            UPD.status(refresh=True)
                        return self._send(200, UPD.summary_json())
                    if p == "/api/house/updateall":     # «Oppdater alt» her, startet fra en annen PC
                        started = UPD.update_all(remote.win)
                        return self._send(200, {"ok": started, "msg": "startet" if started else "pågår allerede"})
                    if p == "/api/house/auto":          # automatikk av/på herfra
                        UPD.set_auto((q.get("on") or ["1"])[0] == "1")
                        return self._send(200, {"ok": True, "auto": UPD.auto_on()})
                    return self._send(200, house_update(remote.win))
                if p in ("/api/friend/update", "/api/friend/update/file"):   # videresend NAS-ens versjon til venner
                    import friends
                    import relayupdate
                    q = parse_qs(u.query)
                    if not friends.check_key((q.get("k") or [""])[0]):
                        return self._send(403, {"error": "feil vennekode eller deling er av"})
                    if p == "/api/friend/update":
                        return self._send(200, relayupdate.serve_info() or {})
                    try:
                        fp = relayupdate.serve_file((q.get("f") or [""])[0])
                    except ValueError as e:
                        return self._send(400, {"error": str(e)})
                    except Exception as e:  # noqa: BLE001
                        return self._send(503, {"error": str(e)})
                    with open(fp, "rb") as f:
                        return self._send(200, f.read(), "application/octet-stream")
                if p == "/api/friend":                   # venner utenfor huset (Tailscale): bare lesing, egen kode
                    import friends
                    if not friends.check_key((parse_qs(u.query).get("k") or [""])[0]):
                        return self._send(403, {"error": "feil vennekode eller deling er av"})
                    return self._send(200, friends.snapshot(remote.win))
                if p == "/api/watch":                    # «Se på»: MJPEG-strøm av skjermen (bare visning)
                    return self._watch(parse_qs(u.query))
                if p == "/api/chatfile":                   # vedlegg i chatten til mobilappen (<img> kan ikke sende nøkkel)
                    q = parse_qs(u.query)
                    if not remote.check((q.get("k") or [""])[0]):
                        return self._send(401, {"error": "ikke paret"})
                    import chatplus
                    fp = chatplus.file_path({"sha": (q.get("sha") or [""])[0], "name": (q.get("name") or [""])[0]})
                    if not fp:
                        return self._send(404, {"error": "fant ikke fila"})
                    import mimetypes
                    return self._send(200, open(fp, "rb").read(), mimetypes.guess_type(fp)[0] or
                                      "application/octet-stream")
                if p in ("/api/clipfile", "/api/clipthumb"):   # nøkkel i adressen – <video>/<img> kan ikke sende den
                    q = parse_qs(u.query)
                    import clipx
                    name = (q.get("name") or [""])[0]
                    pc = (q.get("pc") or [""])[0]
                    ok = remote.check((q.get("k") or [""])[0]) or (q.get("s") and clipx.check_share(
                        f"{pc}/{name}" if pc else name, q["s"][0]))
                    if not ok:
                        return self._send(401, {"error": "ikke paret eller utløpt lenke"})
                    if p == "/api/clipthumb":
                        t = clipx.thumb(clipx.any_path(name) or "") if clipx.any_path(name) else None
                        if not t:
                            return self._send(404, {"error": "finnes ikke"})
                        with open(t, "rb") as f:
                            return self._send(200, f.read(), "image/jpeg")
                    path = clipx.nas_fetch(pc, name) if pc else clipx.any_path(name)
                    if not path:
                        return self._send(404, {"error": "finnes ikke"})
                    if path.lower().endswith((".png", ".jpg", ".gif")):
                        ctype = {".png": "image/png", ".gif": "image/gif"}.get(os.path.splitext(path)[1].lower(), "image/jpeg")
                        with open(path, "rb") as f:
                            return self._send(200, f.read(), ctype)
                    return self._video(path)
                if p == "/api/hello":
                    import applog
                    import savegames
                    ts = tailscale_info()
                    return self._send(200, {"app": "Kontrollsenter", "name": savegames.pc_name(),
                                            "version": applog.RUNNING, "os": "windows" if IS_WIN else "linux",
                                            "lan": local_ips(),
                                            "mac": __import__("remote_extra").lan_mac()[0],
                                            "ts": {"ip": ts["ip"], "name": ts["name"]} if ts["running"] else None})
                if p == "/api/local/widgets":                # KDE-widgetene på denne PC-en
                    if not self._local():
                        return self._send(403, {"error": "bare fra denne PC-en"})
                    import widgets
                    return self._send(200, _call_main(lambda: widgets.data(remote.win)))
                if not self._auth():
                    return
                if p == "/api/status":
                    return self._send(200, _call_main(lambda: build_status(remote.win)))
                if p == "/api/widgets":                      # widgetene i Android-appen
                    import widgets
                    d = _call_main(lambda: widgets.data(remote.win))
                    try:                                     # «Demp» i hurtigknappene blir lilla når lyden er dempet
                        d["mute"] = bool((audio_state(remote.win) or {}).get("mute"))
                    except Exception:  # noqa: BLE001
                        pass
                    return self._send(200, d)
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
                if p.startswith("/api/x/"):
                    return self._extra_get(p[7:], parse_qs(u.query))
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
            if p == "/api/phonecam":                       # mobilen som webkamera: ett JPEG-bilde per kall
                if not self._remote_on():
                    return
                q = parse_qs(urlparse(self.path).query)
                if not remote.check((q.get("k") or [""])[0]):
                    return self._send(401, {"error": "ikke paret"})
                n = int(self.headers.get("Content-Length") or 0)
                if not 0 < n <= 3 * 1024 * 1024:
                    return self._send(413, {"error": "for stort bilde"})
                try:
                    import phonecam
                    phonecam.push(self.rfile.read(n), int((q.get("rot") or ["0"])[0] or 0),
                                  (q.get("dev") or [""])[0][:40])
                except ValueError as e:
                    return self._send(400, {"error": str(e)})
                return self._send(200, {"ok": True})
            try:
                body = self._body(12 * 1024 * 1024 if p == "/api/chat/inbox" else 1024 * 1024
                                  if p in ("/api/house/setup", "/api/chat/join") else MAX_BODY)
                if p == "/api/local/ai":                     # «ks» – AI-assistentene styrer Kontrollsenter (bare herfra)
                    if not self._local():
                        return self._send(403, {"error": "bare fra denne PC-en"})
                    import ai_bridge
                    try:
                        res = ai_bridge.run(remote.win, body.get("cmd"), [str(x) for x in body.get("args") or []])
                        return self._send(200, {"result": res})
                    except Exception as e:  # noqa: BLE001
                        return self._send(400, {"error": str(e)})
                if p == "/api/local/action":                 # knapper i KDE-widgetene
                    if not self._local():
                        return self._send(403, {"error": "bare fra denne PC-en"})
                    import widgets
                    ok, msg = widgets.local_action(remote.win, body)
                    return self._send(200, {"ok": bool(ok), "msg": str(msg)})
                if p == "/api/pair":
                    if not self._remote_on():
                        return
                    token, msg = remote.pair(body.get("code", ""), body.get("device", ""))
                    if not token:
                        time.sleep(1)                       # bremser gjetting
                        return self._send(403, {"error": msg})
                    import savegames
                    return self._send(200, {"token": token, "name": savegames.pc_name()})
                if p in ("/api/chat/inbox", "/api/chat/join"):   # servere i chatten
                    import chatsrv
                    ip = self.client_address[0]
                    if ip.startswith("::ffff:"):
                        ip = ip[7:]
                    try:
                        if p == "/api/chat/join":
                            return self._send(200, {"ok": True, "server": chatsrv.handle_join(body)})
                        if (parse_qs(urlparse(self.path).query).get("k") or [""])[0] != chatsrv.me()["key"]:
                            return self._send(403, {"error": "feil kode"})
                        chatsrv.receive(body, ip, _notify(remote.win))
                        return self._send(200, {"ok": True})
                    except PermissionError as e:
                        return self._send(403, {"error": str(e)})
                    except ValueError as e:
                        return self._send(400, {"error": str(e)})
                if p == "/api/friend/chat":                 # chat fra en venn (vennekoden + må stå i vennelista)
                    import friends
                    import chat
                    if not friends.check_key((parse_qs(urlparse(self.path).query).get("k") or [""])[0]):
                        return self._send(403, {"error": "feil vennekode eller deling er av"})
                    ip = self.client_address[0]
                    if ip.startswith("::ffff:"):
                        ip = ip[7:]
                    try:
                        chat.receive_friend(body, ip, _notify(remote.win))
                        return self._send(200, {"ok": True})
                    except PermissionError as e:
                        return self._send(403, {"error": str(e)})
                if p == "/api/house/chat":                  # chat fra en PC i huset – direkte (raskere enn NAS-en)
                    import watch as W
                    if not W.check_house_key((parse_qs(urlparse(self.path).query).get("fk") or [""])[0]):
                        return self._send(403, {"error": "feil husnøkkel"})
                    import chat
                    chat.receive_home(body.get("_chat2") or body, _notify(remote.win))
                    return self._send(200, {"ok": True})
                if p == "/api/house/setup":                 # 14: oppsett fra en annen PC i huset (husnøkkel)
                    import watch as W
                    if not W.check_house_key((parse_qs(urlparse(self.path).query).get("fk") or [""])[0]):
                        return self._send(403, {"error": "feil husnøkkel"})
                    import homeplus
                    try:
                        return self._send(200, {"ok": True, "msg": homeplus.receive(body.get("files") or {},
                                                                                   remote.win)})
                    except ValueError as e:
                        return self._send(400, {"error": str(e)})
                if not self._auth():
                    return
                if p == "/api/action":
                    role = (getattr(self, "device", None) or {}).get("role", "full")
                    if role == "begrenset" and body.get("a") not in LIMITED_OK:
                        return self._send(403, {"ok": False, "error": "denne enheten har begrenset tilgang"})
                    body["_dev"] = (getattr(self, "device", None) or {}).get("name", "Mobil")
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
                    "oppdater Kontrollsenter i Innstillinger → Oppdatering.</p></body>")
            return self._send(503, html.encode(), "text/html; charset=utf-8")

        def _extra_get(self, what, q):
            import remote_extra as X
            arg = lambda k, d=None: (q.get(k) or [d])[0]  # noqa: E731
            if what == "me":
                d = getattr(self, "device", {}) or {}
                return self._send(200, {"name": d.get("name"), "role": d.get("role", "full")})
            if what == "discord":
                import discord_ctl
                return self._send(200, discord_ctl.state())
            if what == "dc_guilds":
                import discord_ctl as DC
                if not DC.can_read_chat():
                    return self._send(200, {"guilds": [], "need_relink": DC.linked()})
                return self._send(200, {"guilds": DC.guilds()})
            if what == "dc_channels":
                import discord_ctl as DC
                if not arg("g", ""):
                    return self._send(400, {"error": "mangler server (g)"})
                return self._send(200, {"channels": DC.channels(arg("g", ""))})
            if what == "dc_chat":
                import discord_ctl as DC
                if not arg("c", ""):
                    return self._send(400, {"error": "mangler kanal (c)"})
                d = DC.messages(arg("c", ""))
                d["url"] = DC.open_url(arg("g", ""), arg("c", ""), app=False)
                return self._send(200, d)
            if what == "slow":
                import upkeep
                return self._send(200, upkeep.analyze(remote.win))
            if what == "goals":
                import features as F
                return self._send(200, F.goals())
            if what == "panels":
                import apppanels
                q = parse_qs(urlparse(self.path).query)
                only = [x for x in (q.get("only") or [""])[0].split(",") if x] or None
                return self._send(200, {"panels": apppanels.all_panels(remote.win, only)})
            if what == "pclive":
                import apppanels
                q = parse_qs(urlparse(self.path).query)
                return self._send(200, apppanels.pc_live((q.get("name") or [""])[0]))
            if what == "friends":
                import friends
                return self._send(200, friends.state())
            if what == "today":
                import today
                s = today.summary()
                return self._send(200, {**s, "text": today.text(s), "achievements": today.achievements()})
            if what == "vr":
                import vr
                return self._send(200, vr.state())
            if what == "push":
                import push
                return self._send(200, {"enabled": push.enabled(), "topic": push.topic(), "port": PORT})
            if what == "familysafe":
                import familysafe
                return self._send(200, familysafe.state())
            if what == "avprofiles":
                import avprofiles as P
                return self._send(200, P.state())
            if what == "plan":
                import familyplus
                import savegames
                return self._send(200, {**familyplus.load_plan(), "days": familyplus.DAYS, "me": savegames.pc_name()})
            if what == "shop":
                import familyplus
                return self._send(200, familyplus.shop())
            if what == "weekly":
                import features as F
                r = F.weekly_report()
                r["text"] = F.weekly_text(r)
                return self._send(200, r)
            if what == "scenes":
                import scenes
                d = scenes.load()
                return self._send(200, {"active": d.get("active"), "scenes": [
                    {"id": x["id"], "name": x["name"], "icon": x.get("icon"), "color": x.get("color"),
                     "summary": scenes.summary(x), "trigger": scenes.trigger_text(x),
                     "auto": bool((x.get("trigger") or {}).get("auto")) and (x.get("trigger") or {}).get("type") != "manual"}
                    for x in d["scenes"]]})
            if what == "notify":
                import background as B
                bg = getattr(remote.win, "bg", None)
                cfg = bg.cfg if bg else B.load()
                k = cfg.get("kinds") or {}
                return self._send(200, {"all": bool(cfg.get("notify", True)), "kinds": [
                    {"id": i, "name": n, "desc": d, "on": bool(k.get(i, True))} for i, n, d, _ in B.KINDS]})
            if what == "detail":
                import details
                k = arg("k", "cpu")
                return self._send(200, _call_main(lambda: details.collect(remote.win, k)))
            if what == "events":
                return self._send(200, {"events": X.events(float(arg("since", 0) or 0)), "now": time.time()})
            if what == "playtime":
                return self._send(200, X.playtime_summary(int(arg("days", 14))))
            if what == "cs2":
                return self._send(200, X.cs2_history())
            if what == "wowgoals":
                import gamestats
                return self._send(200, {"goals": [g for g in (X.wow_goal_progress(c) for c in gamestats.wow_stats())
                                                  if g]})
            if what == "energy":
                return self._send(200, _call_main(lambda: X.energy(remote.win)))
            if what == "network":
                return self._send(200, X.network())
            if what == "processes":
                return self._send(200, {"processes": X.processes()})
            if what == "media":
                return self._send(200, {**X.media_state(), "apps": X.app_volumes()})
            if what == "clipboard":
                return self._send(200, {"text": X.get_clipboard(_call_main)})
            if what == "screenshot":
                return self._send(200, X.screenshot(), "image/jpeg")
            if what == "nas":
                return self._send(200, X.nas_state())
            if what == "health":
                return self._send(200, X.health(arg("force") == "1"))
            if what == "clips":
                import clips
                import clipx
                st = clips.INSTANCE.state() if clips.INSTANCE else clips.load_cfg()
                st = {k: v for k, v in st.items() if k != "share_secret"}
                fs = clipx.files()
                return self._send(200, {**st, "clips": [x for x in fs if x["kind"] != "image"][:120],
                                        "images": [x for x in fs if x["kind"] == "image"][:60],
                                        "jobs": dict(list(clipx.JOBS.items())[-10:]), "ffmpeg": bool(clipx.ffmpeg())})
            if what == "clipstats":
                import clipx
                return self._send(200, clipx.stats())
            if what == "nasclips":
                import clipx
                return self._send(200, {"clips": clipx.nas_list()})
            if what == "music":
                import clipx
                return self._send(200, {"music": clipx.music_files()[0]})
            if what == "smart":                          # Smart Hjem: enheter på hjemmenettet
                import smarthome
                return self._send(200, smarthome.state(rescan=arg("scan") == "1"))
            if what == "homepcs":
                import homepcs
                return self._send(200, {"pcs": homepcs.fetch() or []})
            import features as F
            if what == "phonecam":                         # mobilkameraet: støtter PC-en det, og sender det nå?
                import phonecam
                return self._send(200, {"ok": True, "live": phonecam.live(), "status": phonecam.status()})
            if what == "chatrooms":
                import chat
                return self._send(200, {"rooms": [{"id": r, "name": n, "icon": i, "unread": u}
                                                  for r, n, i, u in chat.rooms()], "tailscale": chat.tailscale()})
            if what == "chatroom":
                import chat
                room = arg("room", "alle")
                chat.mark_read(room)
                import chatsrv
                return self._send(200, {"room": room, "messages": chat.messages(room, 80), "me_id": chatsrv.me()["id"],
                                        "me": chatsrv.me()["name"]})
            simple = {"chat": lambda: {"messages": F.chat_list()}, "family": F.family,
                      "perf": lambda: {"games": F.perf_per_game(), "driver": F.driver_info()},
                      "startup": lambda: {"items": F.startup_list()}, "lan": lambda: {"devices": F.lan_devices()},
                      "security": lambda: {"items": F.security()}, "wishlist": lambda: {"sales": F.wishlist_check()},
                      "hue": lambda: {"paired": bool(F.cfg()["hue"].get("user")), "lights": F.hue_lights()},
                      "achievements": lambda: {"items": F.achievements()},
                      "wrapped": lambda: F.wrapped(arg("month")), "backups": lambda: {"backups": F.list_backups()},
                      "selftest": lambda: {"items": F.selftest(remote.win)},
                      "features": lambda: {k: v for k, v in F.cfg().items() if not k.startswith("_") and k != "hue"}}
            if what == "familylock":
                import familylock
                return self._send(200, {"on": familylock.locked()})
            if what == "stream":
                import streaming as ST
                st = ST.sunshine_state()
                st["clients"] = ST.clients() if st["running"] and st["has_login"] else []
                st["rustdesk"] = ST.rustdesk_state()
                try:
                    import apps
                    st["remote_app"] = apps.get_use("remote")
                except Exception:  # noqa: BLE001
                    st["remote_app"] = "rustdesk"
                return self._send(200, st)
            if what in simple:
                return self._send(200, simple[what]())
            return self._send(404, {"error": "finnes ikke"})

        def _watch(self, q):
            import watch as W
            arg = lambda k: (q.get(k) or [""])[0]  # noqa: E731
            dev = remote.check(arg("k"))
            if dev:
                if dev.get("role", "full") != "full":
                    return self._send(403, {"error": "denne enheten har begrenset tilgang"})
                who = dev.get("name") or "Mobil"
            elif W.check_house_key(arg("fk")):
                who = re.sub(r"[^\w .-]", "", arg("by"))[:40] or "En annen PC"
            else:
                return self._send(401, {"error": "ikke paret"})
            target = arg("pc")
            import savegames
            if target and target != savegames.pc_name():          # en annen PC: hent og send videre
                ip = W.pc_address(target)
                if not ip:
                    return self._send(404, {"error": f"{target} er ikke på"})
                url = (f"http://{ip}:{PORT}/api/watch?fk={W.house_key()}&by="
                       + __import__("urllib.parse").parse.quote(who))
                self._mjpeg_head()
                try:
                    W.relay(url, self.wfile)
                except Exception:  # noqa: BLE001
                    pass
                return None
            if not W.cfg()["allow"]:
                return self._send(403, {"error": "Skjermdeling er slått av på denne PC-en"})

            def notify(name):
                bg = getattr(remote.win, "bg", None)
                if bg:
                    GLib.idle_add(lambda: (bg.notify("watch", "📺 " + name + " ser på skjermen din",
                                                     "Bare visning – ingen kan styre PC-en. Slå av under "
                                                     "Familie → «La andre i huset se skjermen min».", force=True), False)[1])
                try:
                    import remote_extra
                    remote_extra.event("watch", f"{name} så på skjermen", "", "info")
                except Exception:  # noqa: BLE001
                    pass
            self._mjpeg_head()
            try:
                W.stream_to(self.wfile, who, notify)
            except Exception:  # noqa: BLE001
                pass
            return None

        def _mjpeg_head(self):
            import watch as W
            self.send_response(200)
            self.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={W.BOUNDARY}")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True

        def _video(self, path):
            size = os.path.getsize(path)
            rng = self.headers.get("Range", "")
            m = re.match(r"bytes=(\d*)-(\d*)", rng)
            start, end = 0, size - 1
            if m and (m.group(1) or m.group(2)):
                if m.group(1):
                    start = int(m.group(1))
                    end = int(m.group(2)) if m.group(2) else size - 1
                else:
                    start = max(0, size - int(m.group(2)))
                end = min(end, size - 1, start + 8 * 1024 * 1024 - 1)       # høyst 8 MB per bit
            length = end - start + 1
            self.send_response(206 if m else 200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            if m:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            if self.command == "HEAD":
                return
            with open(path, "rb") as f:
                f.seek(start)
                left = length
                while left > 0:
                    chunk = f.read(min(262144, left))
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        return
                    left -= len(chunk)

        def _static(self, rel):
            rel = os.path.normpath(rel).replace("\\", "/")
            if rel.startswith("..") or os.path.isabs(rel):
                return self._send(404, {"error": "finnes ikke"})
            path = os.path.join(WEB, rel)
            if not os.path.isfile(path):
                return self._send(404, {"error": "finnes ikke"})
            # Faste filtyper: på Windows leser mimetypes Windows-registeret, der .css/.js kan stå feil
            # (f.eks. text/plain). Med «nosniff» nekter nettleseren da å bruke stilark/skript – panelet
            # mister oppsettet og skalerer ikke.
            ctype = WEB_TYPES.get(os.path.splitext(path)[1].lower()) or mimetypes.guess_type(path)[0] \
                or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
                ctype += "; charset=utf-8"
            with open(path, "rb") as f:
                return self._send(200, f.read(), ctype)
    return H
