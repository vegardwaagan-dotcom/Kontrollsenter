"""Talekanaler med webkamera i chat-serverne (Linux, GStreamer i selve programmet).

Alle i samme talekanal sender lyd (Opus) og eventuelt bilde (VP8) direkte til hverandre over Tailscale/hjemmenettet
(UDP). Hver deltaker har én mottaksport for lyd og én for bilde; strømmene skilles på SSRC (rtpssrcdemux), og hver
deltaker får sin egen kjede med eget volum og lydnivå (hvem som snakker).

Signalisering: «vc»-hendelser gjennom serveren (chatsrv) – join/state/leave til alle medlemmer, så også de som ikke
er inne ser hvem som sitter i kanalen. Deltakerne sender «state» hvert 15. sekund; den som ikke er hørt fra på 45 s
regnes som ute.

Innstillinger (chat-av.json): mikrofon, høyttaler, kamera, kvalitet, volum, støyreduksjon, automatisk forsterkning
og stemmeaktivering.
"""
import json
import os
import random
import socket
import subprocess
import sys
import threading
import time

IS_WIN = sys.platform == "win32"
CFG = os.path.expanduser("~/.config/systemmonitor/chat-av.json")
DEFAULT = {"mic": "", "speaker": "", "camera": "", "quality": "middels", "fps": 15, "mic_vol": 100, "out_vol": 100,
           "noise": True, "agc": True, "vad": False, "vad_level": -50}
QUALITY = {"lav": (320, 180, 250), "middels": (640, 360, 600), "høy": (1280, 720, 1500)}   # bredde, høyde, kbit/s
APORTS, VPORTS = range(27160, 27170), range(27170, 27180)
TEST = os.environ.get("KS_VC_TEST") == "1"                # tester: tone og testbilde i stedet for mikrofon/kamera

_ROSTER = {}             # (sid, ch) -> {mid: {name, ip, aport, vport, assrc, vssrc, cam, mute, deaf, t}}
_S = {"sid": None, "ch": None, "mute": False, "deaf": False, "cam": False, "pipes": {}, "assrc": 0, "vssrc": 0,
      "aport": 0, "vport": 0, "peers": set()}
_FRAMES = {}             # mid («me» for meg selv) -> (bytes, w, h, stride, t)
_SPEAK = {}              # mid -> sist hørt over terskelen
_LISTENERS = []
_LOCK = threading.RLock()
_GST = {"ok": None}


# --------------------------------------------------------------------------
# Innstillinger og enheter
# --------------------------------------------------------------------------
def cfg():
    try:
        with open(CFG) as f:
            return {**DEFAULT, **json.load(f)}
    except (OSError, ValueError):
        return dict(DEFAULT)


def set_(**kw):
    old = cfg()
    c = {**old, **{k: v for k, v in kw.items() if k in DEFAULT}}
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    with open(CFG, "w") as f:
        json.dump(c, f, indent=1, ensure_ascii=False)
    changed = {k for k in c if c[k] != old.get(k)}
    if _S["sid"]:                                          # i en kanal: bytt enhet med en gang
        try:
            if changed & {"mic", "noise", "agc"}:
                _restart_send_audio()
            if changed & {"speaker"}:
                _restart_recv_audio()
            if changed & {"camera", "quality", "fps"} and _S["cam"]:
                _stop("send-v")
                _start_camera()
        except Exception as e:  # noqa: BLE001
            _S["error"] = str(e)
            _fire("error")
    _apply_live(c)
    return c


def _pactl(kind):
    try:
        out = subprocess.run(["pactl", "-f", "json", "list", kind], capture_output=True, text=True, timeout=5).stdout
        return [(d["name"], d.get("description") or d["name"]) for d in json.loads(out)
                if not d["name"].endswith(".monitor")]
    except (OSError, ValueError, subprocess.SubprocessError, KeyError):
        return []


def devices():
    """{"mic": [(id, navn)], "speaker": [...], "camera": [...]} – første valg er alltid «Standard»."""
    cams = []
    base = "/sys/class/video4linux"
    try:
        for n in sorted(os.listdir(base)):
            try:
                with open(f"{base}/{n}/name") as f:
                    name = f.read().strip()
                with open(f"{base}/{n}/index") as f:
                    if f.read().strip() != "0":                # bare én node per kamera
                        continue
            except OSError:
                continue
            cams.append((f"/dev/{n}", name))
    except OSError:
        pass
    std = [("", "Standard")]
    return {"mic": std + _pactl("sources"), "speaker": std + _pactl("sinks"),
            "camera": [("", "Første kamera")] + cams}


def gst_ok():
    if _GST["ok"] is None:
        try:
            import gi
            gi.require_version("Gst", "1.0")
            from gi.repository import Gst
            Gst.init(None)
            need = ("opusenc", "opusdec", "rtpopuspay", "rtpopusdepay", "rtpssrcdemux", "multiudpsink", "level",
                    "vp8enc", "vp8dec", "rtpvp8pay", "rtpvp8depay", "appsink")
            _GST["ok"] = not IS_WIN and all(Gst.ElementFactory.find(e) for e in need)
            _GST["Gst"] = Gst
        except (ImportError, ValueError):
            _GST["ok"] = False
    return _GST["ok"]


def why_not():
    if IS_WIN:
        return "Talekanaler virker foreløpig bare på Linux – på Windows kan du bruke walkie-talkie eller Discord"
    return "GStreamer-tilleggene for lyd/bilde mangler (gst-plugins-good/-bad)"


def _free(ports):
    for p in ports:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.bind(("0.0.0.0", p))
            return p
        except OSError:
            continue
        finally:
            s.close()
    raise RuntimeError("fant ingen ledig port for lyd/bilde")


# --------------------------------------------------------------------------
# Lytting (brukergrensesnittet)
# --------------------------------------------------------------------------
def on_change(fn):
    _LISTENERS.append(fn)


def _fire(what="roster"):
    for fn in list(_LISTENERS):
        try:
            from gi.repository import GLib
            GLib.idle_add(lambda f=fn: (f(what), False)[1])
        except Exception:  # noqa: BLE001
            pass


def roster(sid, ch):
    """[{id, name, mute, deaf, cam, speaking, me}] for kanalen (gamle oppføringer ryddes bort)."""
    import chatsrv
    now = time.time()
    with _LOCK:
        r = _ROSTER.get((sid, ch)) or {}
        for mid in [m for m, v in r.items() if now - v["t"] > 45]:
            r.pop(mid, None)
        out = [{"id": mid, "name": v["name"], "mute": v.get("mute"), "deaf": v.get("deaf"), "cam": v.get("cam"),
                "speaking": now - _SPEAK.get(mid, 0) < 0.6, "me": False} for mid, v in r.items()]
    if _S["sid"] == sid and _S["ch"] == ch:
        out.insert(0, {"id": "me", "name": chatsrv.me()["name"], "mute": _S["mute"], "deaf": _S["deaf"],
                       "cam": _S["cam"], "speaking": now - _SPEAK.get("me", 0) < 0.6, "me": True})
    return out


def current():
    return (_S["sid"], _S["ch"]) if _S["sid"] else None


def state():
    return {"in": bool(_S["sid"]), "sid": _S["sid"], "ch": _S["ch"], "mute": _S["mute"], "deaf": _S["deaf"],
            "cam": _S["cam"]}


def frames():
    return dict(_FRAMES)


# --------------------------------------------------------------------------
# GStreamer
# --------------------------------------------------------------------------
def _send_audio_desc(c):
    src = ("audiotestsrc is-live=true wave=sine freq=440 volume=0.3" if TEST else
           "pulsesrc" + (f' device="{c["mic"]}"' if c["mic"] else ""))
    dsp = ""
    if (c["noise"] or c["agc"]) and _GST["Gst"].ElementFactory.find("webrtcdsp") and not TEST:
        dsp = (f"webrtcdsp echo-cancel=false noise-suppression={str(bool(c['noise'])).lower()} "
               f"gain-control={str(bool(c['agc'])).lower()} ! ")
    return (f"{src} ! audioconvert ! audioresample ! audio/x-raw,rate=48000,channels=1,format=S16LE ! {dsp}"
            f"level name=lv interval=100000000 post-messages=true ! volume name=mv ! "
            f"opusenc bitrate=32000 frame-size=20 ! rtpopuspay pt=96 ssrc={_S['assrc']} ! "
            f"multiudpsink name=out sync=false async=false")


def _send_video_desc(c):
    w, h, kb = QUALITY.get(c["quality"], QUALITY["middels"])
    fps = max(5, min(30, int(c.get("fps") or 15)))
    src = ("videotestsrc is-live=true pattern=ball" if TEST else
           "v4l2src" + (f' device="{c["camera"]}"' if c["camera"] else "") + " ! decodebin")
    return (f"{src} ! videoconvert ! videoscale ! videorate ! video/x-raw,width={w},height={h},framerate={fps}/1 ! "
            f"tee name=t t. ! queue leaky=downstream max-size-buffers=2 ! videoconvert ! "
            f"video/x-raw,format=RGBA ! appsink name=self emit-signals=true max-buffers=1 drop=true sync=false "
            f"t. ! queue leaky=downstream max-size-buffers=2 ! videoconvert ! "
            f"vp8enc deadline=1 cpu-used=8 end-usage=cbr target-bitrate={kb * 1000} error-resilient=1 "
            f"keyframe-max-dist={fps * 2} ! rtpvp8pay pt=97 mtu=1200 ssrc={_S['vssrc']} ! "
            f"multiudpsink name=out sync=false async=false")


def _bus(pipe, name):
    Gst = _GST["Gst"]
    bus = pipe.get_bus()
    bus.add_signal_watch()

    def msg(_b, m):
        if m.type == Gst.MessageType.ELEMENT and m.get_structure() and m.get_structure().get_name() == "level":
            st = m.get_structure()
            try:
                rms = max(st.get_value("rms"))
            except (TypeError, ValueError):
                return
            who = "me" if name == "send-a" else m.src.get_name().split("_", 1)[-1]
            who = _ssrc_owner(who) if who != "me" else "me"
            if who == "me":
                c = cfg()
                gate = c["vad"] and rms < c["vad_level"]
                vol = pipe.get_by_name("mv")
                if vol:
                    vol.set_property("mute", _S["mute"] or _S["deaf"] or gate)
                if _S["mute"] or _S["deaf"] or gate:
                    return
            if rms > -45 and who:
                was = time.time() - _SPEAK.get(who, 0) < 0.6
                _SPEAK[who] = time.time()
                if not was:
                    _fire("speak")
        elif m.type == Gst.MessageType.ERROR:
            err, _dbg = m.parse_error()
            _S["error"] = f"{name}: {err.message}"
            _fire("error")
    bus.connect("message", msg)


def _ssrc_owner(ssrc):
    with _LOCK:
        for mid, v in (_ROSTER.get((_S["sid"], _S["ch"])) or {}).items():
            if str(v.get("assrc")) == str(ssrc) or str(v.get("vssrc")) == str(ssrc):
                return mid
    return None


def _on_sample(sink, who):
    s = sink.emit("pull-sample")
    if s is None:
        return 1
    if who != "me":
        who = _ssrc_owner(who) or who
    last = _FRAMES.get(who)
    if last and time.time() - last[4] < 1 / 20:
        return 0
    caps = s.get_caps().get_structure(0)
    buf = s.get_buffer()
    ok, info = buf.map(_GST["Gst"].MapFlags.READ)
    if ok:
        w, h = caps.get_value("width"), caps.get_value("height")
        _FRAMES[who] = (bytes(info.data), w, h, len(info.data) // max(1, h), time.time())
        buf.unmap(info)
        _fire("video")
    return 0


def _recv_audio_pipe(port):
    Gst = _GST["Gst"]
    pipe = Gst.parse_launch(f"udpsrc port={port} caps=application/x-rtp,media=audio,encoding-name=OPUS,"
                            f"clock-rate=48000,payload=96 ! rtpssrcdemux name=dmx")
    c = cfg()

    def new_pad(_d, ssrc, pad):
        sink = "fakesink sync=false" if TEST else ("pulsesink" + (f' device="{c["speaker"]}"' if c["speaker"] else ""))
        b = Gst.parse_bin_from_description(
            f"rtpjitterbuffer latency=80 ! rtpopusdepay ! opusdec plc=true ! audioconvert ! audioresample ! "
            f"level name=lv_{ssrc} interval=100000000 post-messages=true ! volume name=pv_{ssrc} ! {sink}", True)
        pipe.add(b)
        b.sync_state_with_parent()
        pad.link(b.get_static_pad("sink"))
        _apply_live(c)
    pipe.get_by_name("dmx").connect("new-ssrc-pad", new_pad)
    _bus(pipe, "recv-a")
    return pipe


def _recv_video_pipe(port):
    Gst = _GST["Gst"]
    pipe = Gst.parse_launch(f"udpsrc port={port} caps=application/x-rtp,media=video,encoding-name=VP8,"
                            f"clock-rate=90000,payload=97 ! rtpssrcdemux name=dmx")

    def new_pad(_d, ssrc, pad):
        b = Gst.parse_bin_from_description(
            "rtpjitterbuffer latency=100 ! rtpvp8depay ! vp8dec ! videoconvert ! video/x-raw,format=RGBA ! "
            f"appsink name=vs_{ssrc} emit-signals=true max-buffers=1 drop=true sync=false", True)
        pipe.add(b)
        b.get_by_name(f"vs_{ssrc}").connect("new-sample", _on_sample, str(ssrc))
        b.sync_state_with_parent()
        pad.link(b.get_static_pad("sink"))
    pipe.get_by_name("dmx").connect("new-ssrc-pad", new_pad)
    _bus(pipe, "recv-v")
    return pipe


def _apply_live(c=None):
    """Nye innstillinger mens man er i kanalen: volum, demping."""
    c = c or cfg()
    p = _S["pipes"]
    if p.get("send-a") and p["send-a"].get_by_name("mv"):
        p["send-a"].get_by_name("mv").set_property("volume", c["mic_vol"] / 100)
        p["send-a"].get_by_name("mv").set_property("mute", _S["mute"] or _S["deaf"])
    ra = p.get("recv-a")
    if ra:
        it = ra.iterate_recurse()
        while True:
            ok, el = it.next()
            if ok != _GST["Gst"].IteratorResult.OK:
                break
            if el.get_name().startswith("pv_"):
                el.set_property("volume", 0 if _S["deaf"] else c["out_vol"] / 100)


def _start_camera():
    Gst = _GST["Gst"]
    p = Gst.parse_launch(_send_video_desc(cfg()))
    p.get_by_name("self").connect("new-sample", _on_sample, "me")
    _bus(p, "send-v")
    out = p.get_by_name("out")
    for ip, _a, vport in _S["peers"]:
        out.emit("add", ip, vport)
    p.set_state(Gst.State.PLAYING)
    _S["pipes"]["send-v"] = p


def _restart_send_audio():
    Gst = _GST["Gst"]
    _stop("send-a")
    p = Gst.parse_launch(_send_audio_desc(cfg()))
    _bus(p, "send-a")
    for ip, aport, _v in _S["peers"]:
        p.get_by_name("out").emit("add", ip, aport)
    p.set_state(Gst.State.PLAYING)
    _S["pipes"]["send-a"] = p


def _restart_recv_audio():
    _stop("recv-a")
    p = _recv_audio_pipe(_S["aport"])
    p.set_state(_GST["Gst"].State.PLAYING)
    _S["pipes"]["recv-a"] = p


def play_test():
    """Kort testtone i valgt høyttaler."""
    if not gst_ok():
        return
    Gst = _GST["Gst"]
    c = cfg()
    sink = "fakesink" if TEST else "pulsesink" + (f' device="{c["speaker"]}"' if c["speaker"] else "")
    p = Gst.parse_launch(f"audiotestsrc num-buffers=60 freq=660 volume={0.25 * c['out_vol'] / 100} ! audioconvert ! "
                         f"audioresample ! {sink}")
    p.set_state(Gst.State.PLAYING)
    threading.Timer(2.0, lambda: p.set_state(Gst.State.NULL)).start()


def _stop(name):
    p = _S["pipes"].pop(name, None)
    if p is not None:
        p.set_state(_GST["Gst"].State.NULL)


# --------------------------------------------------------------------------
# Inn og ut av kanalen
# --------------------------------------------------------------------------
def _payload(op):
    return {"type": "vc", "op": op, "ch": _S["ch"], "aport": _S["aport"], "vport": _S["vport"],
            "assrc": _S["assrc"], "vssrc": _S["vssrc"], "cam": _S["cam"], "mute": _S["mute"], "deaf": _S["deaf"]}


def _fanout(srv, payload, only=None):
    """Til medlemmene direkte (ingen kø – gamle talekanal-meldinger er verdiløse)."""
    import chatsrv
    me = chatsrv.me()["id"]
    payload = {**payload, "srv": srv["id"], "from_id": me}
    for mid, m in srv.get("members", {}).items():
        if mid == me or (only and mid != only):
            continue
        threading.Thread(target=lambda mm=m: _quiet_post(mm, payload), daemon=True).start()


def _quiet_post(m, payload):
    import chatsrv
    try:
        chatsrv._post(m, payload, timeout=4)
    except Exception:  # noqa: BLE001 – medlemmet er av
        pass


def join(sid, ch):
    """Gå inn i talekanalen (forlater en annen kanal først)."""
    import chatsrv
    if not gst_ok():
        raise RuntimeError(why_not())
    srv = chatsrv.get(sid)
    chan = chatsrv.channel(srv or {}, ch) if srv else None
    if not chan or chan.get("kind") != "voice":
        raise ValueError("fant ikke talekanalen")
    if _S["sid"] == sid and _S["ch"] == ch:
        return "Du er allerede i kanalen"
    leave()
    Gst = _GST["Gst"]
    with _LOCK:
        _S.update(sid=sid, ch=ch, mute=False, deaf=False, cam=False, peers=set(), error=None,
                  assrc=random.randint(1, 2 ** 31 - 1), vssrc=random.randint(1, 2 ** 31 - 1),
                  aport=_free(APORTS), vport=_free(VPORTS))
        _S["pipes"]["recv-a"] = _recv_audio_pipe(_S["aport"])
        _S["pipes"]["recv-v"] = _recv_video_pipe(_S["vport"])
        sa = Gst.parse_launch(_send_audio_desc(cfg()))
        _bus(sa, "send-a")
        _S["pipes"]["send-a"] = sa
        for p in _S["pipes"].values():
            p.set_state(Gst.State.PLAYING)
        _apply_live()
        # de som allerede er inne
        for mid, v in (_ROSTER.get((sid, ch)) or {}).items():
            if time.time() - v["t"] < 45:
                _add_peer(v)
    _fanout(srv, _payload("join"))
    _heartbeat()
    _fire()
    return f"Du er i 🔊 {chan['name']}"


def leave():
    import chatsrv
    if not _S["sid"]:
        return "Du er ikke i en talekanal"
    srv = chatsrv.get(_S["sid"])
    if srv:
        _fanout(srv, _payload("leave"))
    with _LOCK:
        for name in list(_S["pipes"]):
            _stop(name)
        _S.update(sid=None, ch=None, cam=False, peers=set())
        _FRAMES.clear()
    _fire()
    return "Du forlot talekanalen"


def _add_peer(v):
    key = (v["ip"], int(v["aport"]), int(v["vport"]))
    if key in _S["peers"]:
        return
    _S["peers"].add(key)
    for name, port in (("send-a", key[1]), ("send-v", key[2])):
        p = _S["pipes"].get(name)
        if p is not None:
            p.get_by_name("out").emit("add", key[0], port)


def _drop_peer(v):
    key = (v["ip"], int(v["aport"]), int(v["vport"]))
    if key not in _S["peers"]:
        return
    _S["peers"].discard(key)
    for name, port in (("send-a", key[1]), ("send-v", key[2])):
        p = _S["pipes"].get(name)
        if p is not None:
            p.get_by_name("out").emit("remove", key[0], port)


def _heartbeat():
    def loop(token):
        import chatsrv
        while _S["sid"] and _S.get("hb") == token:
            time.sleep(15)
            if not _S["sid"] or _S.get("hb") != token:
                return
            srv = chatsrv.get(_S["sid"])
            if srv:
                _fanout(srv, _payload("state"))
            _fire()
    tok = random.random()
    _S["hb"] = tok
    threading.Thread(target=loop, args=(tok,), daemon=True).start()


def _broadcast_state():
    import chatsrv
    srv = chatsrv.get(_S["sid"]) if _S["sid"] else None
    if srv:
        _fanout(srv, _payload("state"))
    _fire()


def toggle_mute():
    _S["mute"] = not _S["mute"]
    _apply_live()
    _broadcast_state()
    return _S["mute"]


def toggle_deaf():
    _S["deaf"] = not _S["deaf"]
    _apply_live()
    _broadcast_state()
    return _S["deaf"]


def toggle_camera():
    if not _S["sid"]:
        raise RuntimeError("gå inn i en talekanal først")
    if _S["cam"]:
        _stop("send-v")
        _S["cam"] = False
        _FRAMES.pop("me", None)
    else:
        if not TEST and not any(d for d, _n in devices()["camera"] if d):
            raise RuntimeError("fant ikke noe webkamera")
        _start_camera()
        _S["cam"] = True
    _broadcast_state()
    return _S["cam"]


def on_event(srv, sender, ev, src_ip):
    """«vc»-hendelse fra et medlem (chatsrv.receive)."""
    sid, ch, op = srv["id"], str(ev.get("ch") or ""), ev.get("op")
    mid = sender["id"]
    with _LOCK:
        for (s, c), r in _ROSTER.items():                # bare i én kanal om gangen
            if s == sid and c != ch and mid in r:
                old = r.pop(mid)
                if (_S["sid"], _S["ch"]) == (s, c):
                    _drop_peer(old)
        r = _ROSTER.setdefault((sid, ch), {})
        mine = (_S["sid"], _S["ch"]) == (sid, ch)
        if op == "leave":
            old = r.pop(mid, None)
            if old and mine:
                _drop_peer(old)
            _FRAMES.pop(mid, None)
        elif op in ("join", "state"):
            new = mid not in r
            v = {"name": sender.get("name", "?"), "ip": src_ip, "aport": int(ev.get("aport") or 0),
                 "vport": int(ev.get("vport") or 0), "assrc": ev.get("assrc"), "vssrc": ev.get("vssrc"),
                 "cam": bool(ev.get("cam")), "mute": bool(ev.get("mute")), "deaf": bool(ev.get("deaf")),
                 "t": time.time()}
            r[mid] = v
            if not v["cam"]:
                _FRAMES.pop(mid, None)
            if mine:
                _add_peer(v)
                if op == "join" or new:                  # fortell den nye at jeg er her
                    _fanout(srv, _payload("state"), only=mid)
    _fire()


# --------------------------------------------------------------------------
# Test av mikrofon og kamera (innstillingene)
# --------------------------------------------------------------------------
_TEST = {}


def mic_test(on, hear=False, cb=None):
    """Lydnivå fra mikrofonen (cb(dB)); hear=True spiller deg selv av i høyttaleren."""
    Gst = _GST["Gst"] if gst_ok() else None
    if _TEST.get("mic") is not None:
        _TEST.pop("mic").set_state(Gst.State.NULL)
    if not on or Gst is None:
        return
    c = cfg()
    src = ("audiotestsrc is-live=true wave=sine volume=0.3" if TEST else
           "pulsesrc" + (f' device="{c["mic"]}"' if c["mic"] else ""))
    sink = ("pulsesink" + (f' device="{c["speaker"]}"' if c["speaker"] else "")) if hear and not TEST else \
        "fakesink sync=false"
    p = Gst.parse_launch(f"{src} ! audioconvert ! volume volume={c['mic_vol'] / 100} ! "
                         f"level interval=100000000 post-messages=true ! {sink}")
    bus = p.get_bus()
    bus.add_signal_watch()

    def msg(_b, m):
        if m.type == Gst.MessageType.ELEMENT and m.get_structure().get_name() == "level" and cb:
            try:
                cb(max(m.get_structure().get_value("rms")))
            except (TypeError, ValueError):
                pass
    bus.connect("message", msg)
    p.set_state(Gst.State.PLAYING)
    _TEST["mic"] = p


def cam_test(on, cb=None):
    """Forhåndsvisning av kameraet: cb(bytes, w, h, stride) for hvert bilde."""
    Gst = _GST["Gst"] if gst_ok() else None
    if _TEST.get("cam") is not None:
        _TEST.pop("cam").set_state(Gst.State.NULL)
    if not on or Gst is None:
        return
    c = cfg()
    w, h, _kb = QUALITY.get(c["quality"], QUALITY["middels"])
    src = ("videotestsrc is-live=true pattern=ball" if TEST else
           "v4l2src" + (f' device="{c["camera"]}"' if c["camera"] else "") + " ! decodebin")
    p = Gst.parse_launch(f"{src} ! videoconvert ! videoscale ! video/x-raw,width={w},height={h} ! videoconvert ! "
                         "video/x-raw,format=RGBA ! appsink name=a emit-signals=true max-buffers=1 drop=true "
                         "sync=false")

    def sample(sink):
        s = sink.emit("pull-sample")
        if s is None:
            return 1
        st = s.get_caps().get_structure(0)
        buf = s.get_buffer()
        ok, info = buf.map(Gst.MapFlags.READ)
        if ok and cb:
            hh = st.get_value("height")
            cb(bytes(info.data), st.get_value("width"), hh, len(info.data) // max(1, hh))
            buf.unmap(info)
        return 0
    p.get_by_name("a").connect("new-sample", sample)
    p.set_state(Gst.State.PLAYING)
    _TEST["cam"] = p

