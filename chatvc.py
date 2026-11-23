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
DEFAULT = {"mic": "", "speaker": "", "camera": "", "quality": "hd", "fps": 30, "codec": "auto", "mic_vol": 100, "out_vol": 100,
           "noise": True, "agc": True, "vad": False, "vad_level": -50, "auto_leave_min": 30}
# oppløsninger for webkameraet: nøkkel -> (bredde, høyde, navn)
QUALITY = {"lav": (320, 180, "180p – svak nettlinje"), "middels": (640, 360, "360p"),
           "hd": (1280, 720, "HD 720p"), "fullhd": (1920, 1080, "Full HD 1080p"), "qhd": (2560, 1440, "1440p"),
           "4k": (3840, 2160, "4K 2160p")}
_OLD_Q = {"høy": "hd"}                                    # eldre innstillinger
FPS_CHOICES = [15, 24, 30, 60, 90, 120]
APORTS, VPORTS, HPORTS = range(27160, 27170), range(27170, 27180), range(27180, 27190)
TEST = os.environ.get("KS_VC_TEST") == "1"                # tester: tone og testbilde i stedet for mikrofon/kamera

_ROSTER = {}             # (sid, ch) -> {mid: {name, ip, aport, vport, assrc, vssrc, cam, mute, deaf, t}}
_S = {"sid": None, "ch": None, "mute": False, "deaf": False, "cam": False, "pipes": {}, "assrc": 0, "vssrc": 0,
      "aport": 0, "vport": 0, "hport": 0, "peers": set(), "vcodec": "vp8", "vmode": ""}
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
            if changed & {"camera", "quality", "fps", "codec"} and _S["cam"]:
                _stop("send-v")
                _start_camera()
                _broadcast_state()
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
            "camera": [("", "Første kamera")] + cams + [("phone", "📱 Mobilkamera (Android-appen)")]}


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
                "vmode": v.get("vmode") or "",
                "speaking": now - _SPEAK.get(mid, 0) < 0.6, "me": False} for mid, v in r.items()]
    if _S["sid"] == sid and _S["ch"] == ch:
        out.insert(0, {"id": "me", "name": chatsrv.me()["name"], "mute": _S["mute"], "deaf": _S["deaf"],
                       "cam": _S["cam"], "vmode": _S["vmode"] if _S["cam"] else "", "speaking": now - _SPEAK.get("me", 0) < 0.6, "me": True})
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


def encoder():
    """Beste H.264-koder på skjermkortet: «nv» (NVIDIA NVENC), «va» (AMD/Intel VA-API) – eller None (VP8 i CPU-en)."""
    if not gst_ok():
        return None
    if "enc" not in _GST:
        F = _GST["Gst"].ElementFactory
        _GST["enc"] = "nv" if F.find("nvh264enc") else "va" if F.find("vah264enc") else None
    return _GST["enc"]


def encoder_name():
    return {"nv": "NVIDIA NVENC (H.264)", "va": "VA-API (H.264, AMD/Intel)"}.get(encoder(),
                                                                                 "ingen – VP8 i prosessoren")


def quality(c=None):
    """(bredde, høyde, bilder/s, kodek) som faktisk brukes. Uten maskinvarekoding: høyst 1080p30."""
    c = c or cfg()
    q = _OLD_Q.get(c.get("quality"), c.get("quality"))
    w, h, _n = QUALITY.get(q, QUALITY["hd"])
    fps = max(5, min(120, int(c.get("fps") or 30)))
    codec = "h264" if encoder() and c.get("codec", "auto") != "vp8" else "vp8"
    if codec == "vp8":
        if w * h > 1920 * 1080:
            w, h = 1920, 1080
        fps = min(fps, 30 if w * h > 1280 * 720 else 60)
    cam = camera_choice(c)
    if cam == "phone":                                      # Android-appen sender høyst 1080p, ca. 15–25 bilder/s
        w, h, fps = min(w, 1920), min(h, 1080), min(fps, 30)
    if cam and cam != "phone" and not TEST:                 # ikke mer enn kameraet klarer (ikke skaler opp)
        m = best_mode(cam, w, h, fps)
        if m:
            w, h, fps = min(w, m[1]), min(h, m[2]), min(fps, m[3])
    return w, h, fps, codec


def bitrate_kbps(w, h, fps, codec):
    k = (0.07 if codec == "h264" else 0.1) * w * h * fps / 1000
    return int(max(250, min(40000, k)))


def _send_video_desc(c):
    w, h, fps, codec = quality(c)
    kb = bitrate_kbps(w, h, fps, codec)
    _S["vcodec"], _S["vmode"] = codec, f"{h}p{fps}"
    if codec == "h264":
        enc = (f"nvh264enc preset=p1 tune=ultra-low-latency rc-mode=cbr bitrate={kb} gop-size={fps * 2} "
               f"zerolatency=true bframes=0" if encoder() == "nv" else
               f"vah264enc rate-control=cbr bitrate={kb} key-int-max={min(1024, fps * 2)} b-frames=0 target-usage=7")
        tail = (f"videoconvert n-threads=0 ! video/x-raw,format=NV12 ! {enc} ! h264parse config-interval=-1 ! "
                f"rtph264pay pt=98 mtu=1200 config-interval=-1 aggregate-mode=zero-latency ssrc={_S['vssrc']}")
    else:
        tail = (f"videoconvert n-threads=0 ! vp8enc deadline=1 cpu-used=8 end-usage=cbr target-bitrate={kb * 1000} "
                f"error-resilient=1 threads=4 keyframe-max-dist={fps * 2} ! "
                f"rtpvp8pay pt=97 mtu=1200 ssrc={_S['vssrc']}")
    return (f"{_cam_src(c, w, h, fps)} ! videoconvert n-threads=0 ! videoscale n-threads=0 ! videorate ! "
            f"video/x-raw,width={w},height={h},framerate={fps}/1 ! tee name=t "
            # egen forhåndsvisning: liten og høyst 30 bilder/s (sparer minne og CPU også ved 4K120)
            f"t. ! queue leaky=downstream max-size-buffers=2 ! videorate max-rate=30 drop-only=true ! videoscale ! "
            f"videoconvert ! video/x-raw,format=RGBA,width=640,pixel-aspect-ratio=1/1 ! "
            f"appsink name=self emit-signals=true max-buffers=1 drop=true sync=false "
            f"t. ! queue leaky=downstream max-size-buffers=3 ! {tail} ! "
            f"multiudpsink name=out sync=false async=false")


# --------------------------------------------------------------------------
# Hva webkameraet klarer
# --------------------------------------------------------------------------
_MODES = {}


def camera_modes(dev):
    """[(mediatype, bredde, høyde, bilder/s)] som kameraet kan levere (GStreamer DeviceMonitor)."""
    if dev in _MODES:
        return _MODES[dev]
    out = []
    if gst_ok() and dev and dev != "phone":
        import re as _re
        Gst = _GST["Gst"]
        mon = Gst.DeviceMonitor()
        mon.add_filter("Video/Source", None)
        mon.start()
        try:
            for d in mon.get_devices():
                props = d.get_properties()
                path = (props.get_string("api.v4l2.path") or props.get_string("device.path") or "") if props else ""
                if path != dev:
                    continue
                caps = d.get_caps()
                for i in range(caps.get_size() if caps else 0):
                    st = caps.get_structure(i)
                    name = st.get_name()
                    if name not in ("video/x-raw", "image/jpeg"):
                        continue
                    ok1, w = st.get_int("width")
                    ok2, h = st.get_int("height")
                    if not (ok1 and ok2):
                        continue
                    txt = st.to_string()
                    rates = [int(a) / max(1, int(b)) for a, b in _re.findall(r"(\d+)/(\d+)", txt.split("framerate", 1)[-1])]
                    for fr in rates or [30]:
                        if fr >= 1:
                            out.append((name, w, h, int(round(fr))))
        finally:
            mon.stop()
    _MODES[dev] = sorted(set(out), key=lambda m: (m[1] * m[2], m[3]), reverse=True)
    return _MODES[dev]


def best_mode(dev, w, h, fps):
    """Kameramodus nærmest ønsket: samme eller mindre oppløsning, så høyest mulig bilder/s (MJPEG ved høy fart)."""
    modes = camera_modes(dev)
    if not modes:
        return None
    fits = [m for m in modes if m[1] <= w and m[2] <= h] or [min(modes, key=lambda m: m[1] * m[2])]
    top = max(m[1] * m[2] for m in fits)
    same = [m for m in fits if m[1] * m[2] == top]
    enough = [m for m in same if m[3] >= fps]
    pick = min(enough, key=lambda m: (m[3], m[0] != "image/jpeg")) if enough else max(same, key=lambda m: m[3])
    return pick


def mode_summary(dev):
    """«4K 30 · 1080p 60 · 720p 120» – det beste kameraet klarer per oppløsning."""
    best = {}
    for _t, w, h, fr in camera_modes(dev):
        best[h] = max(best.get(h, 0), fr)
    lab = {2160: "4K", 1440: "1440p", 1080: "1080p", 720: "720p", 480: "480p", 360: "360p"}
    return " · ".join(f"{lab.get(h, str(h) + 'p')} {fr}" for h, fr in sorted(best.items(), reverse=True)[:5])


def camera_choice(c=None):
    """Kameraet som faktisk brukes: «Første kamera» hopper over virtuelle kameraer (OBS) og tar mobilkameraet
    når det sender og det ikke finnes noe ekte webkamera."""
    c = c or cfg()
    if c.get("camera"):
        return c["camera"]
    import phonecam
    virt = {d for d, _n in phonecam.loopback_devices()}
    real = [d for d, _n in devices()["camera"] if d and d != "phone" and d not in virt]
    if real:
        return real[0]
    return "phone" if phonecam.live() else ""


def _cam_src(c, w=None, h=None, fps=None):
    """Kamerakilden: testbilde, mobilkameraet (Android-appen) eller et vanlig webkamera i riktig modus."""
    cam = camera_choice(c)
    if TEST and cam != "phone":
        return "videotestsrc is-live=true pattern=ball"
    if cam == "phone":
        import phonecam
        return phonecam.SRC_DESC
    src = "v4l2src" + (f' device="{cam}"' if cam else "")
    m = best_mode(cam, w, h, fps) if cam and w else None
    if m:                                                   # be kameraet om akkurat denne modusen
        t, mw, mh, mf = m
        return f"{src} ! {t},width={mw},height={mh},framerate={mf}/1 ! " + ("jpegdec idct-method=ifast" if t == "image/jpeg"
                                                                               else "videoconvert")
    return src + " ! decodebin"


def _attach_phone(p, key):
    """Mobilkameraet: koble kjeden til bildene som kommer fra Android-appen."""
    if p.get_by_name("phsrc") is not None:
        import phonecam
        _S.setdefault("detach", {})[key] = phonecam.attach(p)


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


# --------------------------------------------------------------------------
# Webkamera-overlay i spill (webcam_overlay.py: eget lite program i overlay-laget over spillet)
# --------------------------------------------------------------------------
OV_CFG = os.path.expanduser("~/.config/systemmonitor/chat-overlay.json")
import tempfile as _tf
OV_DIR = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or _tf.gettempdir(), "ks-vc-overlay")
OV_DEFAULT = {"on": False, "show": "both", "corner": "top-right", "size": "middels", "width": 300, "x": 28, "y": 28,
              "opacity": 100, "locked": True, "key": "Ctrl+Shift+O"}
_OV = {"proc": None, "last": {}, "seq": 0, "t": 0}


def ov_cfg():
    try:
        with open(OV_CFG) as f:
            return {**OV_DEFAULT, **json.load(f)}
    except (OSError, ValueError):
        return dict(OV_DEFAULT)


def ov_set(**kw):
    c = {**ov_cfg(), **{k: v for k, v in kw.items() if k in OV_DEFAULT}}
    os.makedirs(os.path.dirname(OV_CFG), exist_ok=True)
    with open(OV_CFG, "w") as f:
        json.dump(c, f, indent=1)
    ov_sync()
    return c


def ov_supported():
    """«layer-shell» (over fullskjermspill), «vindu» (alltid øverst – X11 og Windows) eller None."""
    if IS_WIN:
        return "vindu"
    if "sup" not in _OV:                                   # rask sjekk – ikke start et eget program i hovedtråden
        import glob as _g
        has_ls = any(_g.glob(d + "/GtkLayerShell-0.1.typelib") for d in
                     ("/usr/lib64/girepository-1.0", "/usr/lib/girepository-1.0",
                      "/usr/lib/x86_64-linux-gnu/girepository-1.0"))
        _OV["sup"] = "layer-shell" if has_ls and os.environ.get("WAYLAND_DISPLAY") else "vindu"
    return _OV["sup"]


def ov_running():
    p = _OV["proc"]
    return p is not None and p.poll() is None


def ov_toggle_lock():
    """Hurtigtasten (Ctrl+Shift+O): lås opp for å flytte/endre størrelse – eller lås igjen (klikk går gjennom)."""
    c = ov_cfg()
    if not c["on"]:
        return ov_set(on=True, locked=False)
    return ov_set(locked=not c["locked"])


def _ov_hotkey(on):
    """Global hurtigtast mens spillet har fokus (KDE: KGlobalAccel, Windows: RegisterHotKey)."""
    h = _OV.get("hotkey")
    if on and h is None:
        try:
            import clips
            _OV["hotkey"] = clips.Hotkey(lambda: ov_toggle_lock(), ov_cfg()["key"],
                                         ("webkamera-overlay", "Webkamera-overlay: lås / flytt"), 0x4B59)
        except Exception as e:  # noqa: BLE001
            _OV["hotkey_err"] = str(e)
    elif h is not None and on and h.spec != ov_cfg()["key"]:
        try:
            h.set_key(ov_cfg()["key"])
        except (ValueError, Exception):  # noqa: BLE001
            pass


def _ov_phone():
    """Mobilkameraet (Android-appen) i overlayet også når du ikke er i en talekanal – og på Windows."""
    if _S["sid"] and cfg().get("camera") == "phone" and _S["cam"]:
        return                                              # i kanalen: bildet kommer fra kamerakjeden
    import phonecam
    jpeg, rot = phonecam.latest()
    if not jpeg or not phonecam.live():
        return
    now = time.time()
    if now - _OV["last"].get("phone", 0) < 1 / 15:
        return
    _OV["last"]["phone"] = now
    try:
        with open(os.path.join(OV_DIR, "me.jpg.tmp"), "wb") as f:
            f.write(jpeg)
        os.replace(os.path.join(OV_DIR, "me.jpg.tmp"), os.path.join(OV_DIR, "me.jpg"))
        if not _S["sid"] and now - _OV["t"] > 0.5:
            _OV["t"] = now
            with open(os.path.join(OV_DIR, "kilder.json.tmp"), "w") as f:
                json.dump([{"key": "me", "me": True, "name": "Deg", "talking": False, "rot": rot}], f)
            os.replace(os.path.join(OV_DIR, "kilder.json.tmp"), os.path.join(OV_DIR, "kilder.json"))
    except OSError:
        pass


def ov_sync():
    """Start overlay-programmet når det er slått på – det viser seg selv bare når det har bilder (talekanal eller
    mobilkamera), eller når det er låst opp for flytting. Ellers stopp det."""
    want = ov_cfg()["on"] and bool(ov_supported()) and __import__("funksjoner").on("chat")
    _ov_hotkey(want)
    if want and not ov_running():
        import shutil as _sh
        _sh.rmtree(OV_DIR, ignore_errors=True)
        os.makedirs(OV_DIR, exist_ok=True)
        try:
            import phonecam
            if not _OV.get("phone_hook"):
                phonecam.on_frame(lambda: _OV["proc"] is not None and _ov_phone())
                _OV["phone_hook"] = True
        except Exception:  # noqa: BLE001
            pass
        kw = {"creationflags": 0x08000000} if IS_WIN else {}
        exe = sys.executable
        if IS_WIN and exe.lower().endswith("python.exe"):    # ikke noe svart konsollvindu
            exe = exe[:-10] + "pythonw.exe"
        try:
            _OV["proc"] = subprocess.Popen([exe, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                              "webcam_overlay.py"),
                                            "--forelder", str(os.getpid())],
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
        except OSError:
            _OV["proc"] = None
    elif not want and ov_running():
        _OV["proc"].terminate()
        _OV["proc"] = None
        import shutil as _sh
        _sh.rmtree(OV_DIR, ignore_errors=True)


def _ov_write(who, data, w, h, stride):
    """Siste bilde til overlayet (minne, høyst 15 per sekund per kilde)."""
    now = time.time()
    if now - _OV["last"].get(who, 0) < 1 / 15:
        return
    _OV["last"][who] = now
    _OV["seq"] += 1
    import struct as _st
    path = os.path.join(OV_DIR, f"{who}.rgba")
    try:
        with open(path + ".tmp", "wb") as f:
            f.write(_st.pack("<4sIIIQ", b"KSVC", w, h, stride, _OV["seq"]))
            f.write(data)
        os.replace(path + ".tmp", path)
        if now - _OV["t"] > 0.5:                           # navn og hvem som snakker
            _OV["t"] = now
            cur = current()
            people = {p["id"]: p for p in roster(*cur)} if cur else {}
            src = [{"key": k, "me": k == "me", "name": "Deg" if k == "me" else people.get(k, {}).get("name", "?"),
                    "talking": bool(people.get(k, {}).get("speaking"))} for k in _FRAMES
                   if k == "me" or k in people]
            with open(os.path.join(OV_DIR, "kilder.json.tmp"), "w") as f:
                json.dump(src, f)
            os.replace(os.path.join(OV_DIR, "kilder.json.tmp"), os.path.join(OV_DIR, "kilder.json"))
    except OSError:
        pass


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
        if _OV["proc"] is not None:
            fr = _FRAMES[who]
            _ov_write(who, fr[0], fr[1], fr[2], fr[3])
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


_SHOW = "videorate max-rate=30 drop-only=true ! videoscale n-threads=0 ! videoconvert n-threads=0 ! " \
        "video/x-raw,format=RGBA,width=[16,1280],height=[16,720],pixel-aspect-ratio=1/1"


def _h264dec():
    """Fast H.264-dekoder (ikke decodebin – den gir dynamiske pads som ikke kan kobles i en bin)."""
    F = _GST["Gst"].ElementFactory
    for e in ("nvh264dec", "vah264dec", "avdec_h264", "openh264dec"):
        if F.find(e):
            return e
    return "avdec_h264"


def _recv_video_pipe(port, codec="vp8"):
    """Mottak av bilde fra de andre: VP8 (port vport) eller H.264 (port hport). Vises høyst 720p/30."""
    Gst = _GST["Gst"]
    enc, pt = ("H264", 98) if codec == "h264" else ("VP8", 97)
    pipe = Gst.parse_launch(f"udpsrc port={port} caps=application/x-rtp,media=video,encoding-name={enc},"
                            f"clock-rate=90000,payload={pt} ! rtpssrcdemux name=dmx")
    dec = (f"rtph264depay ! h264parse ! {_h264dec()}" if codec == "h264" else "rtpvp8depay ! vp8dec")

    def new_pad(_d, ssrc, pad):
        b = Gst.parse_bin_from_description(
            f"rtpjitterbuffer latency=100 ! {dec} ! {_SHOW} ! "
            f"appsink name=vs_{ssrc} emit-signals=true max-buffers=1 drop=true sync=false", True)
        pipe.add(b)
        b.get_by_name(f"vs_{ssrc}").connect("new-sample", _on_sample, str(ssrc))
        b.sync_state_with_parent()
        pad.link(b.get_static_pad("sink"))
    pipe.get_by_name("dmx").connect("new-ssrc-pad", new_pad)
    _bus(pipe, "recv-h" if codec == "h264" else "recv-v")
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


def _vport_for(peer):
    """Porten hos en deltaker for kodeken vi sender med (None = deltakeren kan ikke ta imot den)."""
    ip, _a, vport, hport = peer
    return (hport or None) if _S["vcodec"] == "h264" else vport


def _start_camera():
    Gst = _GST["Gst"]
    _S["vssrc"] = random.randint(1, 2 ** 31 - 1)
    p = Gst.parse_launch(_send_video_desc(cfg()))
    _attach_phone(p, "send-v")
    p.get_by_name("self").connect("new-sample", _on_sample, "me")
    _bus(p, "send-v")
    out = p.get_by_name("out")
    for peer in _S["peers"]:
        port = _vport_for(peer)
        if port:
            out.emit("add", peer[0], port)
    p.set_state(Gst.State.PLAYING)
    _S["pipes"]["send-v"] = p


def _restart_send_audio():
    Gst = _GST["Gst"]
    _stop("send-a")
    p = Gst.parse_launch(_send_audio_desc(cfg()))
    _bus(p, "send-a")
    for ip, aport, _v, _h in _S["peers"]:
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
    det = (_S.get("detach") or {}).pop(name, None)
    if det:
        det()
    p = _S["pipes"].pop(name, None)
    if p is not None:
        p.set_state(_GST["Gst"].State.NULL)


# --------------------------------------------------------------------------
# Inn og ut av kanalen
# --------------------------------------------------------------------------
def _payload(op):
    return {"type": "vc", "op": op, "ch": _S["ch"], "aport": _S["aport"], "vport": _S["vport"],
            "hport": _S["hport"], "vcodec": _S["vcodec"], "vmode": _S["vmode"] if _S["cam"] else "",
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
        _S.update(sid=sid, ch=ch, mute=False, deaf=False, cam=False, peers=set(), error=None, joined=time.time(),
                  assrc=random.randint(1, 2 ** 31 - 1), vssrc=random.randint(1, 2 ** 31 - 1),
                  aport=_free(APORTS), vport=_free(VPORTS), hport=_free(HPORTS))
        _S["pipes"]["recv-a"] = _recv_audio_pipe(_S["aport"])
        _S["pipes"]["recv-v"] = _recv_video_pipe(_S["vport"])
        _S["pipes"]["recv-h"] = _recv_video_pipe(_S["hport"], "h264")
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
    ov_sync()
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
    ov_sync()
    _fire()
    return "Du forlot talekanalen"


def _peer_key(v):
    return (v["ip"], int(v["aport"]), int(v["vport"]), int(v.get("hport") or 0))


def _add_peer(v):
    key = _peer_key(v)
    if key in _S["peers"]:
        return
    for old in [k for k in _S["peers"] if k[0] == key[0] and k[1] == key[1]]:   # samme deltaker, nye porter
        _drop_peer({"ip": old[0], "aport": old[1], "vport": old[2], "hport": old[3]})
    _S["peers"].add(key)
    for name, port in (("send-a", key[1]), ("send-v", _vport_for(key))):
        p = _S["pipes"].get(name)
        if p is not None and port:
            p.get_by_name("out").emit("add", key[0], port)


def _drop_peer(v):
    key = _peer_key(v)
    if key not in _S["peers"]:
        return
    _S["peers"].discard(key)
    for name, port in (("send-a", key[1]), ("send-v", _vport_for(key))):
        p = _S["pipes"].get(name)
        if p is not None and port:
            p.get_by_name("out").emit("remove", key[0], port)


def idle_check(now=None):
    """Har du vært borte (verken mus/tastatur eller snakket) i «auto_leave_min» minutter? → forlat talen.
    Ukjent om du er borte (None fra skrivebordet): aldri – da kan du sitte og lytte."""
    mins = int(cfg().get("auto_leave_min") or 0)
    if not mins or not _S["sid"]:
        return False
    now = now or time.time()
    try:
        import house
        idle = house.idle_seconds()
    except Exception:  # noqa: BLE001
        idle = None
    if idle is None:
        return False
    last = max(_S.get("joined", now), _SPEAK.get("me", 0), now - idle)
    if now - last < mins * 60:
        return False
    import chatsrv
    srv = chatsrv.get(_S["sid"]) or {}
    ch = chatsrv.channel(srv, _S["ch"]) or {}
    leave()
    try:
        import remote
        from gi.repository import GLib
        bg = getattr(getattr(remote, "win", None), "bg", None)
        if bg:
            GLib.idle_add(lambda: (bg.notify("chat", "Du forlot talen", f"Du var borte i {mins} minutter – "
                                             f"{ch.get('name', 'talekanalen')} ({srv.get('name', '')})",
                                             force=True, action="app.chat"), False)[1])
    except Exception:  # noqa: BLE001
        pass
    return True


def _heartbeat():
    def loop(token):
        import chatsrv
        while _S["sid"] and _S.get("hb") == token:
            time.sleep(15)
            if not _S["sid"] or _S.get("hb") != token:
                return
            if idle_check():
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
        cam = camera_choice()
        if cam == "phone":
            import phonecam
            if not phonecam.live():
                raise RuntimeError("mobilkameraet sender ikke – åpne Chat i Android-appen og trykk «📷 Kamera»")
        elif not TEST and not cam:
            raise RuntimeError("fant ikke noe webkamera – bruk mobilen: Chat i Android-appen → «📷 Kamera»")
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
                 "vport": int(ev.get("vport") or 0), "hport": int(ev.get("hport") or 0),
                 "vmode": str(ev.get("vmode") or "")[:12], "assrc": ev.get("assrc"), "vssrc": ev.get("vssrc"),
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
    if _TEST.get("cam_detach"):
        _TEST.pop("cam_detach")()
    if not on or Gst is None:
        return
    c = cfg()
    w, h, fps, _codec = quality(c)
    p = Gst.parse_launch(f"{_cam_src(c, w, h, fps)} ! videoconvert n-threads=0 ! videoscale n-threads=0 ! videorate ! "
                         f"video/x-raw,width={w},height={h},framerate={fps}/1 ! videorate max-rate=30 drop-only=true ! "
                         "videoscale ! videoconvert ! video/x-raw,format=RGBA,width=640,pixel-aspect-ratio=1/1 ! "
                         "appsink name=a emit-signals=true max-buffers=1 drop=true sync=false")

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
    if p.get_by_name("phsrc") is not None:
        import phonecam
        _TEST["cam_detach"] = phonecam.attach(p)
    p.set_state(Gst.State.PLAYING)
    _TEST["cam"] = p

