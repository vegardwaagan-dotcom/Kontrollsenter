"""Lyd på Windows: hovedvolum og demping (høyttalere og mikrofon) og volum per program.

Bruker Windows' Core Audio-API (COM) direkte via ctypes – ingen ekstra programmer.
"""
import ctypes
import threading
from ctypes import POINTER, byref, c_float, c_int, c_uint, c_void_p, wintypes as W

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk  # noqa: E402

import i18n  # noqa: E402

HRESULT = ctypes.c_long


class GUID(ctypes.Structure):
    _fields_ = [("d1", c_uint), ("d2", ctypes.c_ushort), ("d3", ctypes.c_ushort), ("d4", ctypes.c_ubyte * 8)]

    def __init__(self, s):
        import uuid
        u = uuid.UUID(s)
        super().__init__(u.fields[0], u.fields[1], u.fields[2],
                         (ctypes.c_ubyte * 8)(*u.bytes[8:]))


CLSID_MMDeviceEnumerator = GUID("BCDE0395-E52F-467C-8E3D-C4579291692E")
IID_IMMDeviceEnumerator = GUID("A95664D2-9614-4F35-A746-DE8DB63617E6")
IID_IAudioEndpointVolume = GUID("5CDF2C82-841E-4546-9722-0CF74078229A")
IID_IAudioSessionManager2 = GUID("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F")
IID_IAudioSessionControl2 = GUID("BFB7FF88-7239-4FC9-8FA2-07C950BE9C6D")
IID_ISimpleAudioVolume = GUID("87CE5498-68D6-44E5-9215-6DA47EF883D8")
CLSCTX_ALL = 23
E_RENDER, E_CAPTURE, E_MULTIMEDIA = 0, 1, 1


class PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", W.DWORD)]


class PROPVARIANT(ctypes.Structure):
    _fields_ = [("vt", ctypes.c_ushort), ("r1", ctypes.c_ushort), ("r2", ctypes.c_ushort), ("r3", ctypes.c_ushort),
                ("val", c_void_p), ("pad", c_void_p)]


def _call(obj, index, *args, argtypes=()):
    """Kall metode nr. «index» i COM-objektets vtabell."""
    vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p)))[0]
    fn = ctypes.WINFUNCTYPE(HRESULT, c_void_p, *argtypes)(vtbl[index])
    hr = fn(obj, *args)
    if hr < 0:
        raise OSError(f"COM-feil 0x{hr & 0xffffffff:08x}")
    return hr


def _release(obj):
    if obj:
        vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p)))[0]
        ctypes.WINFUNCTYPE(c_uint, c_void_p)(vtbl[2])(obj)


def _qi(obj, iid):
    out = c_void_p()
    _call(obj, 0, byref(iid), byref(out), argtypes=(POINTER(GUID), POINTER(c_void_p)))
    return out


_init = threading.local()


def _com():
    if not getattr(_init, "done", False):
        ctypes.windll.ole32.CoInitializeEx(None, 2)       # STA (ok om GTK allerede har gjort det)
        _init.done = True


def _enumerator():
    _com()
    en = c_void_p()
    hr = ctypes.windll.ole32.CoCreateInstance(byref(CLSID_MMDeviceEnumerator), None, CLSCTX_ALL,
                                              byref(IID_IMMDeviceEnumerator), byref(en))
    if hr < 0:
        raise OSError(f"Core Audio utilgjengelig (0x{hr & 0xffffffff:08x})")
    return en


def _default_device(flow):
    en = _enumerator()
    dev = c_void_p()
    try:
        _call(en, 4, flow, E_MULTIMEDIA, byref(dev), argtypes=(c_int, c_int, POINTER(c_void_p)))
    finally:
        _release(en)
    return dev


def _device_name(dev):
    store = c_void_p()
    _call(dev, 4, 0, byref(store), argtypes=(W.DWORD, POINTER(c_void_p)))     # OpenPropertyStore(STGM_READ)
    try:
        key = PROPERTYKEY(GUID("A45C254E-DF1C-4EFD-8020-67D146A850E0"), 14)    # PKEY_Device_FriendlyName
        pv = PROPVARIANT()
        _call(store, 5, byref(key), byref(pv), argtypes=(POINTER(PROPERTYKEY), POINTER(PROPVARIANT)))
        return ctypes.wstring_at(pv.val) if pv.vt == 31 and pv.val else ""
    finally:
        _release(store)


def _activate(dev, iid):
    out = c_void_p()
    _call(dev, 3, byref(iid), CLSCTX_ALL, None, byref(out),
          argtypes=(POINTER(GUID), W.DWORD, c_void_p, POINTER(c_void_p)))
    return out


class Endpoint:
    """Hovedvolum for standard høyttaler (render) eller mikrofon (capture)."""

    def __init__(self, flow):
        self.dev = _default_device(flow)
        self.name = _device_name(self.dev)
        self.vol = _activate(self.dev, IID_IAudioEndpointVolume)

    def get(self):
        v, m = c_float(), W.BOOL()
        _call(self.vol, 9, byref(v), argtypes=(POINTER(c_float),))
        _call(self.vol, 15, byref(m), argtypes=(POINTER(W.BOOL),))
        return round(v.value * 100), bool(m.value)

    def set_volume(self, pct):
        _call(self.vol, 7, c_float(max(0, min(100, pct)) / 100), None, argtypes=(c_float, c_void_p))

    def set_mute(self, on):
        _call(self.vol, 14, W.BOOL(on), None, argtypes=(W.BOOL, c_void_p))

    def channels(self):
        n = c_uint()
        _call(self.vol, 5, byref(n), argtypes=(POINTER(c_uint),))
        return n.value

    def get_channel(self, i):
        v = c_float()
        _call(self.vol, 13, c_uint(i), byref(v), argtypes=(c_uint, POINTER(c_float)))
        return v.value

    def set_channel(self, i, scalar):
        _call(self.vol, 11, c_uint(i), c_float(max(0.0, min(1.0, scalar))), None,
              argtypes=(c_uint, c_float, c_void_p))

    def close(self):
        _release(self.vol)
        _release(self.dev)


def sessions():
    """[(navn, ISimpleAudioVolume, volum %, demp)] for programmer som spiller lyd."""
    dev = _default_device(E_RENDER)
    out = []
    try:
        mgr = _activate(dev, IID_IAudioSessionManager2)
        en = c_void_p()
        _call(mgr, 5, byref(en), argtypes=(POINTER(c_void_p),))
        n = c_int()
        _call(en, 3, byref(n), argtypes=(POINTER(c_int),))
        import psutil
        for i in range(n.value):
            ctl = c_void_p()
            _call(en, 4, i, byref(ctl), argtypes=(c_int, POINTER(c_void_p)))
            try:
                ctl2 = _qi(ctl, IID_IAudioSessionControl2)
                pid = W.DWORD()
                _call(ctl2, 14, byref(pid), argtypes=(POINTER(W.DWORD),))
                if pid.value == 0:                       # systemlyder
                    _release(ctl2)
                    continue
                try:
                    name = psutil.Process(pid.value).name().replace(".exe", "")
                except Exception:  # noqa: BLE001
                    name = f"PID {pid.value}"
                vol = _qi(ctl, IID_ISimpleAudioVolume)
                v, m = c_float(), W.BOOL()
                _call(vol, 4, byref(v), argtypes=(POINTER(c_float),))
                _call(vol, 6, byref(m), argtypes=(POINTER(W.BOOL),))
                out.append((name, vol, round(v.value * 100), bool(m.value)))
                _release(ctl2)
            finally:
                _release(ctl)
        _release(en)
        _release(mgr)
    finally:
        _release(dev)
    return out


def session_set(vol, pct=None, mute=None):
    if pct is not None:
        _call(vol, 3, c_float(max(0, min(100, pct)) / 100), None, argtypes=(c_float, c_void_p))
    if mute is not None:
        _call(vol, 5, W.BOOL(mute), None, argtypes=(W.BOOL, c_void_p))


# --------------------------------------------------------------------------
# Siden «Lyd» på Windows
# --------------------------------------------------------------------------
class AudioWinPage(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        import automation
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(12)
        self.set_child(box)
        self.box = box
        self.ends = {}
        try:
            import avprofiles_ui
            box.append(avprofiles_ui.ProfileCard("audio", lambda t, d=None: automation.card(t, d)[:2]))
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("lydprofiler")
        for flow, title, icon in ((E_RENDER, "Høyttalere", "ks-sound-symbolic"),
                                  (E_CAPTURE, "Mikrofon", "audio-input-microphone-symbolic")):
            c, i, head = automation.card(title, None, icon)
            try:
                ep = Endpoint(flow)
                self.ends[flow] = ep
                name = Gtk.Label(label=ep.name, xalign=0)
                name.add_css_class("dim-label")
                i.append(name)
                row = Gtk.Box(spacing=10)
                sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
                sc.set_hexpand(True)
                sc.set_draw_value(True)
                sc.set_value_pos(Gtk.PositionType.RIGHT)
                v, m = ep.get()
                sc.set_value(v)
                sc.connect("value-changed", lambda s, e=ep: e.set_volume(int(s.get_value())))
                mute = Gtk.ToggleButton(icon_name="audio-volume-muted-symbolic", active=m,
                                        tooltip_text=i18n.tr("Demp"))
                mute.connect("toggled", lambda b, e=ep: e.set_mute(b.get_active()))
                row.append(sc)
                row.append(mute)
                i.append(row)
            except Exception as e:  # noqa: BLE001
                i.append(Gtk.Label(label=i18n.tr("Fant ingen enhet: ") + (str(e) or type(e).__name__), xalign=0))
            box.append(c)

        try:                                              # 🎧 7.1 i hodesettet (Windows: Romlyd)
            import lydfilter_ui
            c, i, _h = automation.card("🎧 7.1 i hodesettet", "Virtuell surround i et vanlig hodesett.",
                                       "ks-sound-symbolic")
            i.append(lydfilter_ui.Headset71())
            box.append(c)
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("7.1 hodesett")
        try:                                              # test av hodesett og høyttalere, mono → 9.1
            import lydtest_ui
            c, i, _h = automation.card("Test hodesett og høyttalere", "Fra mono og stereo til 7.1, 9.1 og Atmos med "
                                       "takhøyttalere. Trykk på en høyttaler – den sier navnet sitt der den står.",
                                       "ks-sound-symbolic")
            i.append(lydtest_ui.SpeakerTest())
            box.append(c)
            c, i, _h = automation.card("Mikrofontest", "Ta opp 5 sekunder og hør hvordan du høres ut – med nivå, "
                                       "bakgrunnsstøy og råd om hva du bør justere.", "audio-input-microphone-symbolic")
            i.append(lydtest_ui.MicTestBox())
            box.append(c)
            import lydfilter_ui
            c, i, _h = automation.card("Lydfiltre", "Romlyd i hodesettet, lydforbedringer og støyfilter på "
                                       "mikrofonen.", "ks-sound-symbolic")
            i.append(lydfilter_ui.FilterBox())
            box.append(c)
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("lydtest")
        c, i, head = automation.card("Programmer", "Volum for hvert program som spiller lyd nå.", "ks-programs-symbolic")
        self.sess_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        i.append(self.sess_box)
        btns = Gtk.Box(spacing=8)
        for label, uri in (("Lydinnstillinger", "ms-settings:sound"), ("Volummikser", "ms-settings:apps-volume")):
            b = Gtk.Button(label=i18n.tr(label))
            b.connect("clicked", lambda _b, u=uri: __import__("winsupport").open_uri(u))
            btns.append(b)
        i.append(btns)
        box.append(c)
        self._sig = None
        self.refresh()
        GLib.timeout_add_seconds(3, self.refresh)

    def refresh(self):
        if self._sig is not None and not self.get_mapped():    # siden vises ikke: ikke spør Windows
            return True
        try:
            ss = sessions()
        except Exception:  # noqa: BLE001
            ss = []
        sig = tuple(s[0] for s in ss)
        if sig == self._sig:
            for s in ss:
                _release(s[1])
            return True
        self._sig = sig
        while (ch := self.sess_box.get_first_child()):
            self.sess_box.remove(ch)
        if not ss:
            import ui
            self.sess_box.append(ui.empty("ks-sound-symbolic", "Ingen programmer spiller lyd nå"))
        for name, vol, pct, muted in ss:
            row = Gtk.Box(spacing=10)
            lab = Gtk.Label(label=name, xalign=0, width_chars=16, ellipsize=3)
            row.append(lab)
            sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
            sc.set_hexpand(True)
            sc.set_value(pct)
            sc.connect("value-changed", lambda s, v=vol: session_set(v, pct=int(s.get_value())))
            row.append(sc)
            mb = Gtk.ToggleButton(icon_name="audio-volume-muted-symbolic", active=muted)
            mb.connect("toggled", lambda b, v=vol: session_set(v, mute=b.get_active()))
            row.append(mb)
            self.sess_box.append(row)
        return True
