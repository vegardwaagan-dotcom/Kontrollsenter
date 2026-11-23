"""Mobilen som webkamera: Android-appen sender JPEG-bilder (POST /api/phonecam) til PC-en den er koblet til.

Bildene kan brukes
  • som kamera i talekanalene i chatten («📱 Mobilkamera» under Lyd og video),
  • i et eget vindu (virker også på Windows – kan fanges av OBS/Discord som vindu),
  • som vanlig webkamera i andre programmer på Linux via v4l2loopback (f.eks. «OBS Virtual Camera»).
"""
import os
import sys
import threading
import time

IS_WIN = sys.platform == "win32"
ROT = {0: "none", 90: "clockwise", 180: "rotate-180", 270: "counterclockwise"}
_S = {"jpeg": None, "rot": 0, "t": 0, "n": 0, "fps": 0.0, "fps_t": 0, "from": ""}
_SINKS = []              # [(appsrc, videoflip)] – GStreamer-kjeder som skal ha bildene
_LISTENERS = []
_VIRT = {"pipe": None, "dev": None}
_LOCK = threading.Lock()


def push(jpeg, rot=0, who=""):
    """Ett bilde fra mobilen."""
    if not jpeg or jpeg[:2] != b"\xff\xd8":
        raise ValueError("ikke et JPEG-bilde")
    rot = int(rot) % 360 // 90 * 90
    now = time.time()
    with _LOCK:
        _S.update(jpeg=jpeg, rot=rot, t=now, n=_S["n"] + 1, **({"from": who} if who else {}))
        if now - _S["fps_t"] >= 2:
            _S["fps"] = round(_S.pop("_cnt", 0) / max(0.001, now - _S["fps_t"]), 1) if _S["fps_t"] else 0.0
            _S["fps_t"] = now
        _S["_cnt"] = _S.get("_cnt", 0) + 1
        sinks = list(_SINKS)
    for src, flip in sinks:
        _feed(src, flip, jpeg, rot)
    if _VIRT["pipe"] is not None:
        _feed(*_VIRT["pipe"][1:], jpeg, rot)
    for fn in list(_LISTENERS):
        try:
            fn()
        except Exception:  # noqa: BLE001
            pass


def _feed(src, flip, jpeg, rot):
    try:
        from gi.repository import Gst
        if flip is not None and flip.get_property("method").value_nick != ROT[rot]:
            flip.set_property("method", ROT[rot])
        src.emit("push-buffer", Gst.Buffer.new_wrapped(jpeg))
    except Exception:  # noqa: BLE001 – kjeden er stoppet
        pass


def live():
    return time.time() - _S["t"] < 3


def status():
    if not live():
        return "Ikke tilkoblet – åpne Chat i Android-appen og trykk «📷 Kamera»"
    return f"📱 Tilkoblet{(' (' + _S['from'] + ')') if _S['from'] else ''} · {_S['fps']} bilder/s"


def latest():
    return _S["jpeg"], _S["rot"]


def on_frame(fn):
    _LISTENERS.append(fn)


def off_frame(fn):
    if fn in _LISTENERS:
        _LISTENERS.remove(fn)


# --------------------------------------------------------------------------
# GStreamer: «appsrc» som kamerakilde
# --------------------------------------------------------------------------
SRC_DESC = ("appsrc name=phsrc is-live=true do-timestamp=true format=time caps=image/jpeg,framerate=0/1 "
            "max-bytes=4000000 block=false ! jpegdec ! videoflip name=phflip method=none")


def attach(pipe):
    """Koble en kjede som bruker SRC_DESC til mobilbildene. Returnerer en funksjon som kobler fra."""
    pair = (pipe.get_by_name("phsrc"), pipe.get_by_name("phflip"))
    with _LOCK:
        _SINKS.append(pair)
    if _S["jpeg"] is not None:
        _feed(*pair, _S["jpeg"], _S["rot"])

    def detach():
        with _LOCK:
            if pair in _SINKS:
                _SINKS.remove(pair)
    return detach


# --------------------------------------------------------------------------
# Linux: webkamera for alle programmer (v4l2loopback)
# --------------------------------------------------------------------------
def loopback_devices():
    """[(/dev/videoN, navn)] for virtuelle kameraer vi kan skrive til."""
    out = []
    base = "/sys/class/video4linux"
    if IS_WIN or not os.path.isdir(base):
        return out
    for n in sorted(os.listdir(base)):
        try:
            real = os.path.realpath(f"{base}/{n}")
            with open(f"{base}/{n}/name") as f:
                name = f.read().strip()
        except OSError:
            continue
        if "/virtual/" in real and os.access(f"/dev/{n}", os.W_OK):
            out.append((f"/dev/{n}", name))
    return out


def virtual_on():
    return _VIRT["pipe"] is not None


def set_virtual(on, dev=None):
    """Send mobilbildet videre til et v4l2loopback-kamera (Discord, nettleseren, OBS … ser det som et webkamera)."""
    if _VIRT["pipe"] is not None:
        from gi.repository import Gst
        _VIRT["pipe"][0].set_state(Gst.State.NULL)
        _VIRT.update(pipe=None, dev=None)
    if not on:
        return "Virtuelt kamera er av"
    devs = loopback_devices()
    dev = dev or (devs[0][0] if devs else None)
    if not dev:
        raise RuntimeError("fant ikke noe virtuelt kamera (v4l2loopback) – installer v4l2loopback eller start "
                           "OBS sitt virtuelle kamera én gang")
    import gi
    gi.require_version("Gst", "1.0")
    from gi.repository import Gst
    Gst.init(None)
    p = Gst.parse_launch(f"{SRC_DESC} ! videoconvert ! videoscale ! "
                         f"video/x-raw,format=YUY2,width=1280,height=720 ! v4l2sink device={dev} sync=false")
    p.set_state(Gst.State.PLAYING)
    _VIRT.update(pipe=(p, p.get_by_name("phsrc"), p.get_by_name("phflip")), dev=dev)
    if _S["jpeg"] is not None:
        _feed(_VIRT["pipe"][1], _VIRT["pipe"][2], _S["jpeg"], _S["rot"])
    name = next((n for d, n in devs if d == dev), dev)
    return f"Mobilkameraet vises nå som «{name}» i andre programmer"


# --------------------------------------------------------------------------
# Eget vindu (Linux og Windows – trenger ikke GStreamer)
# --------------------------------------------------------------------------
def open_window(parent=None):
    import gi
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gdk, GdkPixbuf, GLib, Gtk
    import i18n
    win = Gtk.Window(title=i18n.tr("Mobilkamera – Kontrollsenter"), default_width=960, default_height=600)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    pic = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN, can_shrink=True, vexpand=True)
    box.append(pic)
    lab = Gtk.Label(label=i18n.tr(status()), margin_top=4, margin_bottom=6)
    lab.add_css_class("dim-label")
    box.append(lab)
    win.set_child(box)
    st = {"busy": False, "last": 0}

    def show():
        st["busy"] = False
        jpeg, rot = latest()
        if jpeg is None:
            return False
        try:
            ld = GdkPixbuf.PixbufLoader.new_with_type("jpeg")
            ld.write(jpeg)
            ld.close()
            pb = ld.get_pixbuf()
            if rot:
                pb = pb.rotate_simple({90: GdkPixbuf.PixbufRotation.CLOCKWISE,
                                       180: GdkPixbuf.PixbufRotation.UPSIDEDOWN,
                                       270: GdkPixbuf.PixbufRotation.COUNTERCLOCKWISE}[rot])
            pic.set_paintable(Gdk.Texture.new_for_pixbuf(pb))
        except GLib.Error:
            pass
        if time.time() - st["last"] > 1:
            st["last"] = time.time()
            lab.set_label(i18n.tr(status()))
        return False

    def frame():
        if not st["busy"]:
            st["busy"] = True
            GLib.idle_add(show)

    on_frame(frame)
    tick = GLib.timeout_add_seconds(2, lambda: (lab.set_label(i18n.tr(status())), True)[1])
    win.connect("close-request", lambda *_: (off_frame(frame), GLib.source_remove(tick), False)[2])
    show()
    win.present()
    return win
