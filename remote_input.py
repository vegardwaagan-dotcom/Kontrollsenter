"""Telefonen eller TV-fjernkontrollen som mus og tastatur for PC-en.

Linux: en virtuell mus/tastatur via uinput (python3-evdev følger med systemet) – virker i både Wayland og X11.
Windows: SendInput. Brukes bare når du selv åpner styreflaten i appen; ingenting kjører ellers.
"""
import sys
import threading
import time

IS_WIN = sys.platform == "win32"
_DEV = {"ui": None, "t": 0}
_LOCK = threading.Lock()

# tastene appen kan sende (navn → Linux-kode, Windows-virtuell tast)
KEYS = {"enter": (28, 0x0D), "esc": (1, 0x1B), "tab": (15, 0x09), "backspace": (14, 0x08), "space": (57, 0x20),
        "up": (103, 0x26), "down": (108, 0x28), "left": (105, 0x25), "right": (106, 0x27), "home": (102, 0x24),
        "end": (107, 0x23), "pageup": (104, 0x21), "pagedown": (109, 0x22), "delete": (111, 0x2E),
        "f11": (87, 0x7A), "super": (125, 0x5B), "alt-tab": None, "playpause": (164, 0xB3),
        "volup": (115, 0xAF), "voldown": (114, 0xAE), "mute": (113, 0xAD)}


def _ui():
    """Den virtuelle enheten (lages første gang, lukkes etter 10 min uten bruk)."""
    from evdev import UInput, ecodes as e
    with _LOCK:
        if _DEV["ui"] is None:
            keys = list(range(1, 249)) + [e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE]
            _DEV["ui"] = UInput({e.EV_KEY: keys, e.EV_REL: [e.REL_X, e.REL_Y, e.REL_WHEEL, e.REL_HWHEEL]},
                                name="Kontrollsenter fjernkontroll")
            time.sleep(0.15)                                  # gi systemet tid til å se den nye enheten
            threading.Thread(target=_reaper, daemon=True).start()
        _DEV["t"] = time.time()
        return _DEV["ui"]


def _reaper():
    while True:
        time.sleep(60)
        with _LOCK:
            if _DEV["ui"] is not None and time.time() - _DEV["t"] > 600:
                _DEV["ui"].close()
                _DEV["ui"] = None
                return


def move(dx, dy):
    dx, dy = int(max(-400, min(400, dx))), int(max(-400, min(400, dy)))
    if IS_WIN:
        _win_mouse(0x0001, dx, dy)
        return
    from evdev import ecodes as e
    u = _ui()
    if dx:
        u.write(e.EV_REL, e.REL_X, dx)
    if dy:
        u.write(e.EV_REL, e.REL_Y, dy)
    u.syn()


def click(button="left", double=False):
    if IS_WIN:
        down, up = {"left": (0x2, 0x4), "right": (0x8, 0x10), "middle": (0x20, 0x40)}[button]
        for _ in range(2 if double else 1):
            _win_mouse(down)
            _win_mouse(up)
        return
    from evdev import ecodes as e
    u = _ui()
    b = {"left": e.BTN_LEFT, "right": e.BTN_RIGHT, "middle": e.BTN_MIDDLE}[button]
    for _ in range(2 if double else 1):
        u.write(e.EV_KEY, b, 1)
        u.syn()
        u.write(e.EV_KEY, b, 0)
        u.syn()
        time.sleep(0.04)


def scroll(dy):
    dy = int(max(-15, min(15, dy)))
    if IS_WIN:
        _win_mouse(0x0800, 0, 0, data=dy * 120)
        return
    from evdev import ecodes as e
    u = _ui()
    u.write(e.EV_REL, e.REL_WHEEL, dy)
    u.syn()


def key(name):
    name = str(name).lower()
    if name == "alt-tab":
        if IS_WIN:
            _win_key(0x12, True)
            _win_key(0x09, True)
            _win_key(0x09, False)
            _win_key(0x12, False)
            return
        from evdev import ecodes as e
        u = _ui()
        for c, v in ((e.KEY_LEFTALT, 1), (e.KEY_TAB, 1), (e.KEY_TAB, 0), (e.KEY_LEFTALT, 0)):
            u.write(e.EV_KEY, c, v)
            u.syn()
        return
    if name not in KEYS:
        raise ValueError("ukjent tast")
    lin, vk = KEYS[name]
    if IS_WIN:
        _win_key(vk, True)
        _win_key(vk, False)
        return
    from evdev import ecodes as e
    u = _ui()
    u.write(e.EV_KEY, lin, 1)
    u.syn()
    u.write(e.EV_KEY, lin, 0)
    u.syn()


def text(s):
    """Skriver tekst. Linux: via utklippstavlen + Ctrl+V (støtter æøå og alt annet). Windows: Unicode-taster."""
    s = str(s)[:500]
    if not s:
        return
    if IS_WIN:
        for ch in s:
            _win_unicode(ch)
        return
    import subprocess
    try:
        subprocess.run(["wl-copy"], input=s.encode(), timeout=3)
    except (OSError, subprocess.SubprocessError):
        subprocess.run(["xclip", "-selection", "clipboard"], input=s.encode(), timeout=3)
    from evdev import ecodes as e
    u = _ui()
    for c, v in ((e.KEY_LEFTCTRL, 1), (e.KEY_V, 1), (e.KEY_V, 0), (e.KEY_LEFTCTRL, 0)):
        u.write(e.EV_KEY, c, v)
        u.syn()


# ------------------------------------------------------------------ Windows
def _win_input():
    import ctypes
    from ctypes import wintypes as W

    class MI(ctypes.Structure):
        _fields_ = [("dx", W.LONG), ("dy", W.LONG), ("mouseData", W.DWORD), ("dwFlags", W.DWORD),
                    ("time", W.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class KI(ctypes.Structure):
        _fields_ = [("wVk", W.WORD), ("wScan", W.WORD), ("dwFlags", W.DWORD), ("time", W.DWORD),
                    ("dwExtraInfo", ctypes.c_size_t)]

    class U(ctypes.Union):
        _fields_ = [("mi", MI), ("ki", KI), ("pad", ctypes.c_byte * 32)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", W.DWORD), ("u", U)]
    return ctypes, MI, KI, INPUT


def _win_mouse(flags, dx=0, dy=0, data=0):
    ctypes, MI, _KI, INPUT = _win_input()
    i = INPUT(type=0)
    i.u.mi = MI(dx, dy, data & 0xFFFFFFFF, flags, 0, 0)
    ctypes.windll.user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INPUT))


def _win_key(vk, down):
    ctypes, _MI, KI, INPUT = _win_input()
    i = INPUT(type=1)
    i.u.ki = KI(vk, 0, 0 if down else 0x2, 0, 0)
    ctypes.windll.user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INPUT))


def _win_unicode(ch):
    ctypes, _MI, KI, INPUT = _win_input()
    for up in (0, 0x2):
        i = INPUT(type=1)
        i.u.ki = KI(0, ord(ch), 0x4 | up, 0, 0)               # KEYEVENTF_UNICODE
        ctypes.windll.user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INPUT))


def action(a):
    """Fra appen: {do: move|click|scroll|key|text, …}."""
    do = a.get("do")
    if do == "move":
        move(float(a.get("dx", 0)), float(a.get("dy", 0)))
    elif do == "click":
        click(a.get("button", "left") if a.get("button") in ("left", "right", "middle") else "left",
              bool(a.get("double")))
    elif do == "scroll":
        scroll(float(a.get("dy", 0)))
    elif do == "key":
        key(a.get("key", ""))
    elif do == "text":
        text(a.get("text", ""))
    else:
        raise ValueError("ukjent")
    return "OK"
