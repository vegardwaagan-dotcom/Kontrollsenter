"""Kontrollertest: alle knapper, stikker (dødsone og drift), avtrekkere og vibrasjon.

Linux: evdev (python3-evdev følger med systemet) – Xbox, PlayStation, Switch Pro, 8BitDo, Steam Deck m.fl.
Windows: XInput (Xbox-kontrollere og alt som later som det er en). Ingenting installeres.
"""
import sys
import threading
import time

IS_WIN = sys.platform == "win32"

# knappene, i visningsrekkefølge: (nøkkel, etikett)
BUTTONS = [("A", "A ✕"), ("B", "B ○"), ("X", "X □"), ("Y", "Y △"), ("LB", "LB / L1"), ("RB", "RB / R1"),
           ("BACK", "View / Share"), ("START", "Menu / Options"), ("GUIDE", "Xbox / PS"), ("LS", "L3 (venstre stikke)"),
           ("RS", "R3 (høyre stikke)"), ("UP", "▲"), ("DOWN", "▼"), ("LEFT", "◀"), ("RIGHT", "▶")]


def _state():
    return {"buttons": {k: False for k, _l in BUTTONS}, "lx": 0.0, "ly": 0.0, "rx": 0.0, "ry": 0.0,
            "lt": 0.0, "rt": 0.0, "seen": set(), "t": time.time()}


# ------------------------------------------------------------------ Linux (evdev)
def _evdev_pads():
    import evdev
    from evdev import ecodes as e
    out = []
    for p in evdev.list_devices():
        try:
            d = evdev.InputDevice(p)
            caps = d.capabilities()
            keys = set(caps.get(e.EV_KEY, []))
            if e.BTN_SOUTH in keys or e.BTN_GAMEPAD in keys:
                if e.EV_ABS in caps:
                    out.append(d)
                    continue
            d.close()
        except OSError:
            continue
    return out


class _LinuxPad:
    def __init__(self, path):
        import evdev
        self.dev = evdev.InputDevice(path)
        self.s = _state()
        self.info = {}
        from evdev import ecodes as e
        for code, ai in self.dev.capabilities(absinfo=True).get(e.EV_ABS, []):
            self.info[code] = ai
        self.stop = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()

    def _norm(self, code, v, center=True):
        ai = self.info.get(code)
        if not ai or ai.max == ai.min:
            return 0.0
        x = (v - ai.min) / (ai.max - ai.min)
        return round(x * 2 - 1, 3) if center else round(x, 3)

    def _run(self):
        from evdev import ecodes as e
        km = {e.BTN_SOUTH: "A", e.BTN_EAST: "B", e.BTN_WEST: "X", e.BTN_NORTH: "Y", e.BTN_TL: "LB", e.BTN_TR: "RB",
              e.BTN_SELECT: "BACK", e.BTN_START: "START", e.BTN_MODE: "GUIDE", e.BTN_THUMBL: "LS",
              e.BTN_THUMBR: "RS", e.BTN_DPAD_UP: "UP", e.BTN_DPAD_DOWN: "DOWN", e.BTN_DPAD_LEFT: "LEFT",
              e.BTN_DPAD_RIGHT: "RIGHT", e.BTN_TL2: "LT_BTN", e.BTN_TR2: "RT_BTN"}
        s = self.s
        try:
            for ev in self.dev.read_loop():
                if self.stop.is_set():
                    break
                if ev.type == e.EV_KEY and ev.code in km:
                    k = km[ev.code]
                    if k in s["buttons"]:
                        s["buttons"][k] = bool(ev.value)
                        if ev.value:
                            s["seen"].add(k)
                    elif k == "LT_BTN" and "LT" not in self._has_trig():
                        s["lt"] = float(ev.value)
                    elif k == "RT_BTN" and "RT" not in self._has_trig():
                        s["rt"] = float(ev.value)
                elif ev.type == e.EV_ABS:
                    c = ev.code
                    if c == e.ABS_X:
                        s["lx"] = self._norm(c, ev.value)
                    elif c == e.ABS_Y:
                        s["ly"] = self._norm(c, ev.value)
                    elif c == e.ABS_RX:
                        s["rx"] = self._norm(c, ev.value)
                    elif c == e.ABS_RY:
                        s["ry"] = self._norm(c, ev.value)
                    elif c in (e.ABS_Z, e.ABS_BRAKE):
                        s["lt"] = self._norm(c, ev.value, False)
                    elif c in (e.ABS_RZ, e.ABS_GAS):
                        s["rt"] = self._norm(c, ev.value, False)
                    elif c == e.ABS_HAT0X:
                        s["buttons"]["LEFT"], s["buttons"]["RIGHT"] = ev.value < 0, ev.value > 0
                        ev.value and s["seen"].add("LEFT" if ev.value < 0 else "RIGHT")
                    elif c == e.ABS_HAT0Y:
                        s["buttons"]["UP"], s["buttons"]["DOWN"] = ev.value < 0, ev.value > 0
                        ev.value and s["seen"].add("UP" if ev.value < 0 else "DOWN")
                    if s["lt"] > 0.5:
                        s["seen"].add("LT")
                    if s["rt"] > 0.5:
                        s["seen"].add("RT")
                s["t"] = time.time()
        except OSError:
            s["gone"] = True

    def _has_trig(self):
        from evdev import ecodes as e
        return {"LT" for c in (e.ABS_Z, e.ABS_BRAKE) if c in self.info} | \
            {"RT" for c in (e.ABS_RZ, e.ABS_GAS) if c in self.info}

    def rumble(self, strong=1.0, weak=1.0, ms=600):
        from evdev import ecodes as e, ff
        if e.EV_FF not in self.dev.capabilities():
            raise RuntimeError("kontrolleren har ikke vibrasjon (eller driveren støtter det ikke)")
        eff = ff.Effect(e.FF_RUMBLE, -1, 0, ff.Trigger(0, 0), ff.Replay(ms, 0),
                        ff.EffectType(ff_rumble_effect=ff.Rumble(strong_magnitude=int(strong * 0xFFFF),
                                                                 weak_magnitude=int(weak * 0xFFFF))))
        try:
            eid = self.dev.upload_effect(eff)
            self.dev.write(e.EV_FF, eid, 1)
            threading.Timer(ms / 1000 + 0.3, lambda: self._erase(eid)).start()
        except OSError as x:
            raise RuntimeError(f"fikk ikke lov til å vibrere ({x.strerror})") from x

    def _erase(self, eid):
        try:
            self.dev.erase_effect(eid)
        except OSError:
            pass

    def close(self):
        self.stop.set()
        try:
            self.dev.close()
        except OSError:
            pass


# ------------------------------------------------------------------ Windows (XInput)
def _xinput():
    import ctypes
    for n in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
        try:
            return getattr(ctypes.windll, n)
        except OSError:
            continue
    raise RuntimeError("fant ikke XInput")


class _WinPad:
    BITS = {"UP": 0x1, "DOWN": 0x2, "LEFT": 0x4, "RIGHT": 0x8, "START": 0x10, "BACK": 0x20, "LS": 0x40, "RS": 0x80,
            "LB": 0x100, "RB": 0x200, "GUIDE": 0x400, "A": 0x1000, "B": 0x2000, "X": 0x4000, "Y": 0x8000}

    def __init__(self, idx):
        self.idx = int(idx)
        self.s = _state()
        self.stop = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        import ctypes
        from ctypes import wintypes as W

        class GP(ctypes.Structure):
            _fields_ = [("wButtons", W.WORD), ("bLeftTrigger", ctypes.c_ubyte), ("bRightTrigger", ctypes.c_ubyte),
                        ("sThumbLX", ctypes.c_short), ("sThumbLY", ctypes.c_short), ("sThumbRX", ctypes.c_short),
                        ("sThumbRY", ctypes.c_short)]

        class ST(ctypes.Structure):
            _fields_ = [("dwPacketNumber", W.DWORD), ("Gamepad", GP)]
        x = _xinput()
        st = ST()
        s = self.s
        while not self.stop.is_set():
            if x.XInputGetState(self.idx, ctypes.byref(st)) != 0:
                s["gone"] = True
                time.sleep(0.5)
                continue
            g = st.Gamepad
            for k, b in self.BITS.items():
                on = bool(g.wButtons & b)
                s["buttons"][k] = on
                on and s["seen"].add(k)
            s["lx"], s["ly"] = round(g.sThumbLX / 32767, 3), round(-g.sThumbLY / 32767, 3)
            s["rx"], s["ry"] = round(g.sThumbRX / 32767, 3), round(-g.sThumbRY / 32767, 3)
            s["lt"], s["rt"] = round(g.bLeftTrigger / 255, 3), round(g.bRightTrigger / 255, 3)
            s["lt"] > 0.5 and s["seen"].add("LT")
            s["rt"] > 0.5 and s["seen"].add("RT")
            s["t"] = time.time()
            time.sleep(1 / 120)

    def rumble(self, strong=1.0, weak=1.0, ms=600):
        import ctypes
        from ctypes import wintypes as W

        class VIB(ctypes.Structure):
            _fields_ = [("l", W.WORD), ("r", W.WORD)]
        x = _xinput()
        x.XInputSetState(self.idx, ctypes.byref(VIB(int(strong * 65535), int(weak * 65535))))
        threading.Timer(ms / 1000, lambda: x.XInputSetState(self.idx, ctypes.byref(VIB(0, 0)))).start()

    def close(self):
        self.stop.set()


# ------------------------------------------------------------------ felles
def pads():
    """[(id, navn)] for kontrollerne som er koblet til nå."""
    if IS_WIN:
        import ctypes
        try:
            x = _xinput()
        except RuntimeError:
            return []
        buf = ctypes.create_string_buffer(16)
        return [(str(i), f"Xbox-kontroller {i + 1}") for i in range(4) if x.XInputGetState(i, buf) == 0]
    try:
        ds = _evdev_pads()
    except Exception:  # noqa: BLE001
        return []
    out = [(d.path, d.name) for d in ds]
    for d in ds:
        d.close()
    return out


def open_pad(pid):
    return _WinPad(pid) if IS_WIN else _LinuxPad(pid)


def drift(samples):
    """samples = [(lx, ly, rx, ry)] tatt mens stikkene hviler. → (venstre, høyre, anbefalt dødsone 0–1)."""
    if not samples:
        return 0.0, 0.0, 0.0
    lm = max((lx * lx + ly * ly) ** 0.5 for lx, ly, _rx, _ry in samples)
    rm = max((rx * rx + ry * ry) ** 0.5 for _lx, _ly, rx, ry in samples)
    return round(lm, 3), round(rm, 3), round(min(0.3, max(lm, rm) + 0.03), 2)
