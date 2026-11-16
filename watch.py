"""«Se på» – se skjermen til en annen PC i huset live (som casting fra Meta Quest): bare visning, ingen styring.

* Bildet tas bare opp mens noen ser på, og stopper 8 sekunder etter at siste seer har gått.
* Den som blir sett på får et varsel (og KDE viser skjermdelingsikonet). Kan slås av: «La andre se skjermen min».
* Linux: skjermdelingsportalen (spør én gang, husker svaret) + GStreamer/PipeWire → JPEG.
  Windows: GDI-skjermkopi → JPEG via GdkPixbuf.
* Strømmen sendes som MJPEG (multipart/x-mixed-replace) – virker rett i <img> på telefonen og i Kontrollsenter.
* PC-ene stoler på hverandre med en felles husnøkkel på NAS-en; telefonen bruker sin vanlige paring, og
  PC-en den er koblet til henter bildet fra den andre PC-en og sender det videre.
"""
import json
import os
import secrets
import sys
import threading
import time

IS_WIN = sys.platform == "win32"
CFG = os.path.expanduser("~/.config/systemmonitor/se-pa.json")
FPS = 12
WIDTH = 1280
BOUNDARY = "ksframe"


def cfg():
    try:
        with open(CFG, encoding="utf-8") as f:
            c = json.load(f)
    except (OSError, ValueError):
        c = {}
    return {"allow": True, "key": "", "fps": FPS, "width": WIDTH, **c}


def save_cfg(c):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    tmp = CFG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(c, f, indent=1)
    if not IS_WIN:
        os.chmod(tmp, 0o600)
    os.replace(tmp, CFG)


# --------------------------------------------------------------------------
# Husnøkkel: felles for PC-ene i huset (ligger på NAS-en, kopi lokalt)
# --------------------------------------------------------------------------
def house_key():
    c = cfg()
    if c["key"]:
        return c["key"]
    try:
        import lanupdate as L
        import tempfile
        if L.on_lan():
            d = tempfile.mkdtemp()
            f = os.path.join(d, "k")
            key = ""
            try:
                L._smb(f'cd "PC-er"; get ".husnokkel" "{f}"', 30)
                key = open(f).read().strip()
            except Exception:  # noqa: BLE001
                key = ""
            if len(key) < 32:                                  # første PC lager nøkkelen
                key = secrets.token_urlsafe(32)
                with open(f, "w") as fh:
                    fh.write(key)
                _h, _s, folder = L._split()
                L.smb_mkdir(f"{folder}/PC-er")
                L._smb(f'cd "PC-er"; put "{f}" ".husnokkel"', 30)
            c["key"] = key
            save_cfg(c)
            return key
    except Exception:  # noqa: BLE001
        pass
    return ""


def check_house_key(k):
    import hmac
    mine = house_key()
    return bool(mine and k and hmac.compare_digest(str(k), mine))


# --------------------------------------------------------------------------
# Opptak (deles av alle seere)
# --------------------------------------------------------------------------
class Capture:
    def __init__(self):
        self.frame = None
        self.seq = 0
        self.cond = threading.Condition()
        self.viewers = {}
        self.running = False
        self.error = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

    # --- seere ---
    def join(self, who, notify=None):
        with self._lock:
            first_time = who not in self.viewers
            self.viewers[who] = self.viewers.get(who, 0) + 1
            if not self.running:
                self.error = None
                self._stop.clear()
                self.running = True
                threading.Thread(target=self._run, daemon=True, name="se-pa").start()
        if first_time and notify:
            try:
                notify(who)
            except Exception:  # noqa: BLE001
                pass

    def leave(self, who):
        with self._lock:
            n = self.viewers.get(who, 1) - 1
            if n <= 0:
                self.viewers.pop(who, None)
            else:
                self.viewers[who] = n
            if not self.viewers:
                threading.Timer(8, self._maybe_stop).start()

    def _maybe_stop(self):
        with self._lock:
            if not self.viewers:
                self._stop.set()

    def _push(self, jpeg):
        with self.cond:
            self.frame = jpeg
            self.seq += 1
            self.cond.notify_all()

    def wait_frame(self, last_seq, timeout=5):
        with self.cond:
            if self.seq == last_seq:
                self.cond.wait(timeout)
            return self.seq, self.frame

    def _run(self):
        try:
            if IS_WIN:
                self._run_windows()
            else:
                self._run_linux()
        except Exception as e:  # noqa: BLE001
            self.error = str(e) or type(e).__name__
            import applog
            applog.log.warning("Se på: %s", self.error)
            with self.cond:
                self.cond.notify_all()
        finally:
            self.running = False

    # --- Windows: GDI ---
    def _run_windows(self):
        import wincapture
        c = cfg()
        while not self._stop.is_set():
            t0 = time.time()
            self._push(wincapture.jpeg(c["width"], 70))
            time.sleep(max(0.0, 1 / c["fps"] - (time.time() - t0)))

    # --- Linux: skjermdelingsportalen + GStreamer ---
    def _run_linux(self):
        fd, node = _portal_screencast()
        import gi
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst
        Gst.init(None)
        c = cfg()
        tail = (f"videoscale ! video/x-raw,width={c['width']},pixel-aspect-ratio=1/1 ! videorate ! "
                f"video/x-raw,framerate={c['fps']}/1 ! jpegenc quality=70 ! "
                "appsink name=out emit-signals=false max-buffers=1 drop=true sync=false")
        # Flere oppsett, prøves etter tur til ett gir bilder. Det første kopierer bildet fra GPU-minnet
        # (DMA-BUF) til vanlig minne – det løser «forhandlingsproblem» (not-negotiated) på de fleste maskiner.
        variants = [
            f"pipewiresrc fd={{fd}} path={node} do-timestamp=true always-copy=true ! video/x-raw ! videoconvert ! {tail}",
            f"pipewiresrc fd={{fd}} path={node} do-timestamp=true always-copy=true ! videoconvert ! {tail}",
            f"pipewiresrc fd={{fd}} target-object={node} do-timestamp=true always-copy=true ! video/x-raw ! "
            f"videoconvert ! {tail}",
            f"pipewiresrc fd={{fd}} path={node} do-timestamp=true keepalive-time=1000 ! videoconvert ! {tail}",
        ]
        last_err = None
        try:
            for v in variants:
                if self._stop.is_set():
                    return
                pipe = Gst.parse_launch(v.format(fd=os.dup(fd)))
                sink = pipe.get_by_name("out")
                pipe.set_state(Gst.State.PLAYING)
                got = False
                t0 = time.monotonic()
                try:
                    while not self._stop.is_set():
                        smp = sink.emit("try-pull-sample", 500 * Gst.MSECOND)
                        if smp is None:
                            msg = pipe.get_bus().pop_filtered(Gst.MessageType.ERROR)
                            if msg:
                                raise RuntimeError(msg.parse_error()[0].message)
                            if not got and time.monotonic() - t0 > 6:
                                raise RuntimeError("fikk ikke bilde fra skjermen")
                            continue
                        b = smp.get_buffer()
                        ok, info = b.map(Gst.MapFlags.READ)
                        if ok:
                            got = True
                            self._push(bytes(info.data))
                            b.unmap(info)
                    return
                except RuntimeError as e:
                    last_err = e
                    if got:                                    # virket en stund, så feil – ikke prøv videre
                        raise
                    import applog
                    applog.log.info("Se på: prøver neste oppsett (%s)", e)
                finally:
                    pipe.set_state(Gst.State.NULL)
            raise last_err or RuntimeError("fikk ikke bilde fra skjermen")
        finally:
            try:
                os.close(fd)
            except OSError:
                pass
            _portal_close()


CAP = Capture()

# --------------------------------------------------------------------------
# Skjermdelingsportalen (org.freedesktop.portal.ScreenCast)
# --------------------------------------------------------------------------
_SESSION = {"handle": None}
TOKEN_FILE = os.path.expanduser("~/.config/systemmonitor/se-pa-portal")


def _portal_screencast():
    from gi.repository import Gio, GLib
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    try:                                         # samme app-ID hver gang → «husk valget» gjelder Kontrollsenter
        bus.call_sync("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
                      "org.freedesktop.host.portal.Registry", "Register",
                      GLib.Variant("(sa{sv})", ("no.waagan.Systemmonitor", {})), None, 0, 3000, None)
    except GLib.Error:
        pass                                     # allerede registrert (f.eks. av hurtigtasten for klipp)
    sender = bus.get_unique_name()[1:].replace(".", "_")
    n = [0]

    def request(method, args_fmt, args, opts):
        n[0] += 1
        tok = f"kssp{os.getpid()}x{n[0]}x{int(time.time())}"
        path = f"/org/freedesktop/portal/desktop/request/{sender}/{tok}"
        ev, res = threading.Event(), {}

        def on_resp(_c, _s, _p, _i, _sig, params):
            code, results = params.unpack()
            res["code"], res["r"] = code, results
            ev.set()
        sid = bus.signal_subscribe("org.freedesktop.portal.Desktop", "org.freedesktop.portal.Request", "Response",
                                   path, None, Gio.DBusSignalFlags.NO_MATCH_RULE, on_resp)
        opts = dict(opts)
        opts["handle_token"] = GLib.Variant("s", tok)
        bus.call_sync("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
                      "org.freedesktop.portal.ScreenCast", method,
                      GLib.Variant(args_fmt, (*args, opts)), None, 0, 10000, None)
        if not ev.wait(120):                                   # brukeren kan trenge litt tid første gang
            bus.signal_unsubscribe(sid)
            raise RuntimeError("skjermdelingen ble ikke godkjent på PC-en")
        bus.signal_unsubscribe(sid)
        if res["code"] != 0:
            raise RuntimeError("skjermdelingen ble avvist på PC-en")
        return res["r"]

    r = request("CreateSession", "(a{sv})", (), {"session_handle_token": GLib.Variant("s", f"kss{os.getpid()}")})
    session = r["session_handle"]
    _SESSION["handle"] = session
    sel = {"types": GLib.Variant("u", 1), "multiple": GLib.Variant("b", False),
           "cursor_mode": GLib.Variant("u", 2), "persist_mode": GLib.Variant("u", 2)}
    try:
        old = open(TOKEN_FILE).read().strip()
        if old:
            sel["restore_token"] = GLib.Variant("s", old)
    except OSError:
        pass
    request("SelectSources", "(oa{sv})", (session,), sel)
    r = request("Start", "(osa{sv})", (session, ""), {})
    if r.get("restore_token"):
        os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
        with open(TOKEN_FILE, "w") as f:
            f.write(r["restore_token"])
    streams = r.get("streams") or []
    if not streams:
        raise RuntimeError("ingen skjerm ble valgt")
    node = streams[0][0]
    res, fdl = bus.call_with_unix_fd_list_sync(
        "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop", "org.freedesktop.portal.ScreenCast",
        "OpenPipeWireRemote", GLib.Variant("(oa{sv})", (session, {})), None, 0, 10000, None, None)
    fd = fdl.get(res.unpack()[0])
    return fd, node


def _portal_close():
    from gi.repository import Gio
    h = _SESSION.get("handle")
    _SESSION["handle"] = None
    if not h:
        return
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        bus.call_sync("org.freedesktop.portal.Desktop", h, "org.freedesktop.portal.Session", "Close",
                      None, None, 0, 3000, None)
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------
# Strømmen (brukes av nettjenesten i remote.py)
# --------------------------------------------------------------------------
def stream_to(wfile, who, notify=None, stop=None):
    """Skriv MJPEG til en HTTP-forbindelse til den lukkes. who = hvem som ser på (vises i varselet)."""
    if not cfg()["allow"]:
        raise PermissionError("Skjermdeling er slått av på denne PC-en")
    CAP.join(who, notify)
    seq = -1
    sent = 0
    try:
        t0 = time.time()
        while not (stop and stop.is_set()):
            seq, frame = CAP.wait_frame(seq, 5)
            if CAP.error:
                raise RuntimeError(CAP.error)
            if frame is None:
                if time.time() - t0 > 130:
                    raise RuntimeError("fikk ikke bilde fra skjermen")
                continue
            wfile.write(f"--{BOUNDARY}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(frame)}\r\n\r\n".encode())
            wfile.write(frame)
            wfile.write(b"\r\n")
            sent += 1
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
        pass
    finally:
        CAP.leave(who)
    return sent


def relay(url, wfile, stop=None):
    """Hent MJPEG fra en annen PC og send den videre (telefonen er bare paret med én PC)."""
    import urllib.request
    with urllib.request.urlopen(url, timeout=150) as r:
        while not (stop and stop.is_set()):
            chunk = r.read(65536)
            if not chunk:
                break
            wfile.write(chunk)


def pc_address(name):
    """IP-adressen til en annen PC fra statusen den deler på NAS-en."""
    import homepcs
    for p in homepcs.fetch() or []:
        if p.get("name") == name and not p.get("off"):
            ips = p.get("ips") or []
            if ips:
                return ips[0]
    return None
