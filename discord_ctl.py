"""Discord: lyd, mikrofon og de viktigste innstillingene – fra PC-en og mobilappen.

To nivåer:
1. Uten oppsett (Linux): Discords egne lydstrømmer styres via lydsystemet (PipeWire/PulseAudio): volum på
   samtalen, mikrofon av/på og «lyd av» for Discord. Windows: volum og demping av Discord-lyden.
2. Full tilkobling via Discords lokale RPC (discord-ipc): inn-/utvolum, inn-/utenhet, mikrofonmodus
   (stemmeaktivering / trykk for å snakke), støydemping, ekkodemping, automatisk forsterkning, mute og deafen,
   hvem som er i samtalen, og forlat kanalen. Krever at du lager en (gratis) app på discord.com/developers én gang
   og limer inn Client ID og Client Secret – Discord spør så om du godkjenner tilkoblingen.

Discord har ingen API for overlayet – det åpnes i Discord (Innstillinger → Spilloverlay). På Linux har Discord
ikke eget overlay; MangoHud-overlayet i Kontrollsenter kan brukes i stedet.
"""
import glob
import json
import os
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid

IS_WIN = sys.platform == "win32"
CFG = os.path.expanduser("~/.config/systemmonitor/discord.json")
SCOPES = ["rpc", "rpc.voice.read", "rpc.voice.write", "identify", "messages.read"]
_LOCK = threading.Lock()


def cfg():
    try:
        with open(CFG) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_cfg(**kw):
    d = cfg()
    d.update(kw)
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    with open(CFG + ".tmp", "w") as f:
        json.dump(d, f, indent=1)
    try:
        os.chmod(CFG + ".tmp", 0o600)                  # nøkkelen til Discord – bare for deg
    except OSError:
        pass
    os.replace(CFG + ".tmp", CFG)


def running():
    try:
        import psutil
        for p in psutil.process_iter(["name"]):
            n = (p.info["name"] or "").lower()
            if n in ("discord", "discord.exe", "discordcanary", "discordptb", "vesktop", "webcord"):
                return True
    except Exception:  # noqa: BLE001
        pass
    return bool(_ipc_paths())


# --------------------------------------------------------------------------
# 1. Uten oppsett: Discords lydstrømmer
# --------------------------------------------------------------------------
def _is_discord(props):
    s = " ".join(str(props.get(k, "")) for k in ("application.name", "application.process.binary",
                                                 "application.id", "pipewire.access.portal.app_id",
                                                 "application.flatpak.id")).lower()
    return "discord" in s or "webrtc voiceengine" in s or "vesktop" in s


def _pjson(kind):
    out = subprocess.run(["pactl", "-f", "json", "list", kind], capture_output=True, text=True, timeout=5).stdout
    return json.loads(out or "[]")


def audio_state():
    """Discord sin lyd i lydsystemet: {"out": [volum, demp] eller None, "mic": [volum, demp] eller None}."""
    st = {"out": None, "mic": None}
    if IS_WIN:
        try:
            import winaudio
            for name, _vol, v, m in winaudio.sessions():
                if "discord" in name.lower():
                    st["out"] = [v, m]
        except Exception:  # noqa: BLE001
            pass
        return st
    try:
        for kind, key in (("sink-inputs", "out"), ("source-outputs", "mic")):
            for x in _pjson(kind):
                if _is_discord(x.get("properties") or {}):
                    vols = [int(str(c.get("value_percent", "0")).rstrip("%")) for c in (x.get("volume") or {}).values()]
                    st[key] = [round(sum(vols) / len(vols)) if vols else 100, bool(x.get("mute"))]
                    break
    except Exception:  # noqa: BLE001
        pass
    return st


def audio_set(what, volume=None, mute=None):
    """what = "out" (det du hører fra Discord) eller "mic" (mikrofonen inn i Discord)."""
    if IS_WIN:
        import winaudio
        for name, vol, _v, _m in winaudio.sessions():
            if "discord" in name.lower() and what == "out":
                winaudio.session_set(vol, volume, mute)
                return True
        raise RuntimeError("Discord spiller ingen lyd akkurat nå")
    kind, cmd = ("sink-inputs", "sink-input") if what == "out" else ("source-outputs", "source-output")
    hit = False
    for x in _pjson(kind):
        if _is_discord(x.get("properties") or {}):
            hit = True
            if volume is not None:
                subprocess.run(["pactl", f"set-{cmd}-volume", str(x["index"]), f"{int(volume)}%"], timeout=5)
            if mute is not None:
                subprocess.run(["pactl", f"set-{cmd}-mute", str(x["index"]), "1" if mute else "0"], timeout=5)
    if not hit:
        raise RuntimeError("Discord bruker ikke " + ("lyden" if what == "out" else "mikrofonen") + " akkurat nå")
    return True


# --------------------------------------------------------------------------
# 2. Discord RPC (lokal tilkobling til Discord-appen)
# --------------------------------------------------------------------------
def _ipc_paths():
    if IS_WIN:
        out = []
        for i in range(10):
            p = rf"\\.\pipe\discord-ipc-{i}"
            try:
                with open(p, "r+b"):
                    pass
                out.append(p)
            except OSError:
                continue
        return out
    base = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    pats = [base + "/discord-ipc-*", base + "/app/com.discordapp.Discord/discord-ipc-*",
            base + "/app/dev.vencord.Vesktop/discord-ipc-*", base + "/snap.discord/discord-ipc-*", "/tmp/discord-ipc-*"]
    return sorted(p for pat in pats for p in glob.glob(pat))


class RPC:
    def __init__(self, client_id):
        self.client_id = str(client_id)
        self.sock = self.pipe = None
        for path in _ipc_paths():
            try:
                if IS_WIN:
                    self.pipe = open(path, "r+b", buffering=0)
                else:
                    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    s.settimeout(8)
                    s.connect(path)
                    self.sock = s
                break
            except OSError:
                continue
        if not (self.sock or self.pipe):
            raise RuntimeError("Discord kjører ikke (fant ingen tilkobling)")
        self._send(0, {"v": 1, "client_id": self.client_id})
        op, data = self._recv()
        if data.get("evt") != "READY":
            raise RuntimeError(data.get("message") or "Discord godtok ikke tilkoblingen – sjekk Client ID")
        self.user = (data.get("data") or {}).get("user") or {}

    def _write(self, b):
        if self.pipe:
            self.pipe.write(b)
        else:
            self.sock.sendall(b)

    def _read(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.pipe.read(n - len(buf)) if self.pipe else self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("Discord lukket tilkoblingen")
            buf += chunk
        return buf

    def _send(self, op, obj):
        b = json.dumps(obj).encode()
        self._write(struct.pack("<II", op, len(b)) + b)

    def _recv(self):
        op, n = struct.unpack("<II", self._read(8))
        return op, json.loads(self._read(n).decode("utf-8", "replace"))

    def cmd(self, name, args=None, timeout=60):
        nonce = str(uuid.uuid4())
        self._send(1, {"cmd": name, "args": args or {}, "nonce": nonce})
        t = time.time()
        while time.time() - t < timeout:
            _op, d = self._recv()
            if d.get("nonce") == nonce:
                if d.get("evt") == "ERROR":
                    raise RuntimeError((d.get("data") or {}).get("message") or "Discord sa nei")
                return d.get("data")
        raise TimeoutError("Discord svarte ikke")

    def close(self):
        try:
            (self.pipe or self.sock).close()
        except Exception:  # noqa: BLE001
            pass


def _token_request(form):
    data = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request("https://discord.com/api/oauth2/token", data=data,
                                 headers={"Content-Type": "application/x-www-form-urlencoded",
                                          "User-Agent": "Kontrollsenter (hjemme-PC)"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def connect_app(client_id, client_secret):
    """Første gang: Discord spør om du godkjenner. Lagrer nøkkelen. Returnerer brukernavnet."""
    rpc = RPC(client_id)
    try:
        code = rpc.cmd("AUTHORIZE", {"client_id": str(client_id), "scopes": SCOPES}, timeout=120)["code"]
        tok = _token_request({"client_id": client_id, "client_secret": client_secret, "grant_type": "authorization_code",
                              "code": code, "redirect_uri": "http://localhost"})
        save_cfg(client_id=str(client_id), client_secret=client_secret, access_token=tok["access_token"],
                 scopes=SCOPES,
                 refresh_token=tok.get("refresh_token"), expires=time.time() + int(tok.get("expires_in", 604800)) - 60)
        rpc.cmd("AUTHENTICATE", {"access_token": tok["access_token"]})
        save_cfg(me_id=rpc.user.get("id"))
        return rpc.user.get("global_name") or rpc.user.get("username") or "Discord"
    finally:
        rpc.close()


def disconnect_app():
    save_cfg(access_token=None, refresh_token=None, expires=0)


def linked():
    return bool(cfg().get("access_token"))


def _authed():
    c = cfg()
    if not c.get("access_token"):
        raise RuntimeError("ikke koblet til Discord ennå")
    if time.time() > c.get("expires", 0) and c.get("refresh_token"):
        tok = _token_request({"client_id": c["client_id"], "client_secret": c.get("client_secret", ""),
                              "grant_type": "refresh_token", "refresh_token": c["refresh_token"]})
        save_cfg(access_token=tok["access_token"], refresh_token=tok.get("refresh_token", c["refresh_token"]),
                 expires=time.time() + int(tok.get("expires_in", 604800)) - 60)
        c = cfg()
    rpc = RPC(c["client_id"])
    try:
        rpc.cmd("AUTHENTICATE", {"access_token": c["access_token"]})
    except Exception:
        rpc.close()
        raise
    return rpc


def state():
    """Alt om Discord til siden og appen."""
    out = {"running": running(), "linked": linked(), "audio": audio_state(), "voice": None, "channel": None,
           "error": None, "overlay_note": ("Discord har ikke eget overlay på Linux – bruk MangoHud-overlayet i "
                                           "Kontrollsenter." if not IS_WIN else
                                           "Overlayet slås av og på i Discord: Innstillinger → Spilloverlay.")}
    if not out["linked"] or not out["running"]:
        return out
    with _LOCK:
        try:
            rpc = _authed()
            try:
                v = rpc.cmd("GET_VOICE_SETTINGS")
                out["voice"] = {
                    "mute": v.get("mute"), "deaf": v.get("deaf"),
                    "in_vol": round((v.get("input") or {}).get("volume", 0)),
                    "out_vol": round((v.get("output") or {}).get("volume", 0)),
                    "in_dev": (v.get("input") or {}).get("device_id"),
                    "out_dev": (v.get("output") or {}).get("device_id"),
                    "in_devs": [[d["id"], d["name"]] for d in (v.get("input") or {}).get("available_devices", [])],
                    "out_devs": [[d["id"], d["name"]] for d in (v.get("output") or {}).get("available_devices", [])],
                    "mode": ((v.get("mode") or {}).get("type") or "VOICE_ACTIVITY"),
                    "noise": v.get("noise_suppression"), "echo": v.get("echo_cancellation"),
                    "agc": v.get("automatic_gain_control")}
                ch = rpc.cmd("GET_SELECTED_VOICE_CHANNEL")
                if ch:
                    out["channel"] = {"id": ch.get("id"), "name": ch.get("name"), "guild": ch.get("guild_id"),
                                      "members": [{"name": (m.get("nick") or (m.get("user") or {}).get("global_name")
                                                            or (m.get("user") or {}).get("username")),
                                                   "mute": (m.get("voice_state") or {}).get("self_mute") or
                                                   (m.get("voice_state") or {}).get("mute"),
                                                   "deaf": (m.get("voice_state") or {}).get("self_deaf")}
                                                  for m in ch.get("voice_states", [])]}
            finally:
                rpc.close()
        except Exception as e:  # noqa: BLE001
            out["error"] = str(e)
    return out


def action(a):
    """a = {"do": ...} fra PC-siden eller appen."""
    do = a.get("do")
    if do in ("out_vol_sys", "mic_mute_sys", "out_mute_sys"):           # uten oppsett: lydsystemet
        if do == "out_vol_sys":
            audio_set("out", volume=max(0, min(150, int(a.get("value", 100)))))
        elif do == "mic_mute_sys":
            audio_set("mic", mute=bool(a.get("on")))
        else:
            audio_set("out", mute=bool(a.get("on")))
        return "OK"
    if do == "leave":
        with _LOCK:
            rpc = _authed()
            try:
                rpc.cmd("SELECT_VOICE_CHANNEL", {"channel_id": None, "force": True})
            finally:
                rpc.close()
        return "Du forlot samtalen"
    args = {}
    if do == "mute":
        args["mute"] = bool(a.get("on"))
    elif do == "deaf":
        args["deaf"] = bool(a.get("on"))
    elif do == "in_vol":
        args["input"] = {"volume": max(0, min(100, float(a.get("value", 100))))}
    elif do == "out_vol":
        args["output"] = {"volume": max(0, min(200, float(a.get("value", 100))))}
    elif do == "in_dev":
        args["input"] = {"device_id": str(a.get("value"))}
    elif do == "out_dev":
        args["output"] = {"device_id": str(a.get("value"))}
    elif do == "mode":
        args["mode"] = {"type": "PUSH_TO_TALK" if a.get("value") == "PUSH_TO_TALK" else "VOICE_ACTIVITY"}
    elif do in ("noise", "echo", "agc"):
        key = {"noise": "noise_suppression", "echo": "echo_cancellation", "agc": "automatic_gain_control"}[do]
        args[key] = bool(a.get("on"))
    else:
        raise ValueError("ukjent Discord-kommando")
    with _LOCK:
        rpc = _authed()
        try:
            rpc.cmd("SET_VOICE_SETTINGS", args)
        finally:
            rpc.close()
    return "OK"


# --------------------------------------------------------------------------
# Servere, kanaler og chat (lesing). Discord har ingen godkjent måte å sende meldinger som deg selv eller å lese
# vennelisten for vanlige apper – da måtte vi brukt innloggingsnøkkelen din, som bryter vilkårene. Svar skjer i
# Discord: open_url() gir en lenke rett til kanalen.
# --------------------------------------------------------------------------
_GUILDS = {"t": 0, "v": None}


def can_read_chat():
    return "messages.read" in (cfg().get("scopes") or [])


def _call(name, args=None):
    with _LOCK:
        rpc = _authed()
        try:
            return rpc.cmd(name, args or {})
        finally:
            rpc.close()


def guilds():
    """[{id, name, icon_url}] – serverne du er med i (mellomlagret 5 min)."""
    if _GUILDS["v"] is not None and time.time() - _GUILDS["t"] < 300:
        return _GUILDS["v"]
    g = (_call("GET_GUILDS") or {}).get("guilds", [])
    _GUILDS["v"] = [{"id": x["id"], "name": x.get("name"), "icon": x.get("icon_url")} for x in g]
    _GUILDS["t"] = time.time()
    return _GUILDS["v"]


def channels(guild_id):
    """Tekst- og talekanalene på en server, sortert slik Discord viser dem."""
    ch = (_call("GET_CHANNELS", {"guild_id": str(guild_id)}) or {}).get("channels", [])
    out = []
    for c in ch:
        kind = {0: "text", 2: "voice", 5: "news", 13: "stage", 15: "forum"}.get(c.get("type"))
        if kind:
            out.append({"id": c["id"], "name": c.get("name"), "kind": kind})
    order = {"text": 0, "news": 0, "forum": 1, "voice": 2, "stage": 2}
    return sorted(out, key=lambda c: (order[c["kind"]], (c["name"] or "").lower()))


def _author(m):
    a = m.get("author") or {}
    return m.get("nick") or a.get("global_name") or a.get("username") or "?"


def messages(channel_id, limit=50):
    """Siste meldinger i en tekstkanal: [{id, author, content, t, color, mine}]."""
    c = _call("GET_CHANNEL", {"channel_id": str(channel_id)}) or {}
    me = cfg().get("me_id")
    out = []
    for m in (c.get("messages") or [])[-limit:]:
        txt = m.get("content") or ""
        if not txt and m.get("attachments"):
            txt = "📎 " + ", ".join(x.get("filename", "vedlegg") for x in m["attachments"])
        if not txt and m.get("embeds"):
            e = m["embeds"][0]
            txt = "🔗 " + (e.get("title") or e.get("description") or e.get("url") or "innebygd innhold")
        ts = m.get("timestamp") or ""
        try:
            from datetime import datetime
            t = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
        except ValueError:
            t = time.time()
        out.append({"id": m.get("id"), "author": _author(m), "content": txt, "t": t,
                    "color": m.get("author_color"), "mine": (m.get("author") or {}).get("id") == me})
    return {"name": c.get("name"), "guild": c.get("guild_id"), "messages": out}


def open_url(guild_id, channel_id, app=True):
    """Lenke som åpner kanalen i Discord (for å svare der)."""
    g = guild_id or "@me"
    return f"discord://-/channels/{g}/{channel_id}" if app else f"https://discord.com/channels/{g}/{channel_id}"
