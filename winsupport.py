"""Windows-støtte: strømplaner, oppstart ved innlogging og ikon i systemstatusfeltet (Win32 via ctypes).

Brukes bare når sys.platform == "win32". Linux-versjonen rører ikke denne fila.
"""
import ctypes
import os
import re
import subprocess
import sys
import threading

IS_WIN = sys.platform == "win32"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
NO_WINDOW = 0x08000000                      # CREATE_NO_WINDOW – ingen svart konsoll som blinker

# Windows' innebygde strømplaner (samme GUID på alle Windows-maskiner)
PLANS = {"power-saver": "a1841308-3541-4fab-bc81-f71556f20b4a",
         "balanced": "381b4222-f694-41f0-9685-ff5bb260df2e",
         "performance": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"}


def decode(data):
    """Tekst fra et Windows-verktøy. powercfg, netsh, ping og PowerShell skriver i konsollens tegnkode (OEM,
    f.eks. cp850), ikke UTF-8 – med text=True krasjet lesetråden på æøå og utskriften ble borte."""
    if not data:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    for enc in ("oem", "mbcs", "cp850"):
        try:
            return data.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", "replace")


def run(cmd, timeout=20):
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=NO_WINDOW if IS_WIN else 0)
        return r.returncode, decode(r.stdout) + decode(r.stderr)
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


# --------------------------------------------------------------------------
# Strømmodus = strømplan
# --------------------------------------------------------------------------
def active_plan():
    code, out = run(["powercfg", "/getactivescheme"])
    m = re.search(r"([0-9a-f]{8}-[0-9a-f-]{27})", out, re.I)
    guid = m.group(1).lower() if m else ""
    for key, g in PLANS.items():
        if g == guid:
            return key
    return "balanced" if guid else None


def set_plan(key):
    guid = PLANS[key]
    code, out = run(["powercfg", "/setactive", guid])
    if code != 0 and key == "performance":
        # «Høy ytelse» er skjult på noen maskiner – lag den fra malen og prøv igjen
        run(["powercfg", "-duplicatescheme", guid, guid])
        code, out = run(["powercfg", "/setactive", guid])
    return code == 0, out.strip()


# --------------------------------------------------------------------------
# Oppstart ved innlogging (HKCU\Software\Microsoft\Windows\CurrentVersion\Run)
# --------------------------------------------------------------------------
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_get(name):
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def autostart_set(name, command):
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
        if command:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(k, name)
            except OSError:
                pass


def self_command(hidden=True):
    """Kommandoen som starter Kontrollsenter (uten konsollvindu)."""
    py = sys.executable.replace("python.exe", "pythonw.exe")
    return f'"{py}" -X utf8 "{os.path.join(APP_DIR, "systemmonitor.py")}"' + (" --hidden" if hidden else "")


# --------------------------------------------------------------------------
# Ikon i systemstatusfeltet (Shell_NotifyIconW + egen meldingsløkke i en tråd)
# --------------------------------------------------------------------------
class WinTray:
    """Samme grensesnitt som tray.Tray på Linux: (tittel, ikon, on_activate, items, tr)."""
    WM_USER = 0x0400
    CALLBACK = WM_USER + 20
    NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
    NIF_MESSAGE, NIF_ICON, NIF_TIP = 1, 2, 4

    def __init__(self, title, icon, on_activate, items, tr=lambda s: s):
        self.title, self.on_activate, self.items, self.tr = title, on_activate, items, tr
        self.tooltip = title
        self.hwnd = None
        self._ready = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()
        self._ready.wait(5)

    def _loop(self):
        from ctypes import wintypes as W
        u32, sh, k32 = ctypes.windll.user32, ctypes.windll.shell32, ctypes.windll.kernel32
        WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
        u32.DefWindowProcW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
        u32.DefWindowProcW.restype = ctypes.c_ssize_t

        class WNDCLASS(ctypes.Structure):
            _fields_ = [("style", W.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                        ("cbWndExtra", ctypes.c_int), ("hInstance", W.HINSTANCE), ("hIcon", W.HICON),
                        ("hCursor", W.HANDLE), ("hbrBackground", W.HBRUSH), ("lpszMenuName", W.LPCWSTR),
                        ("lpszClassName", W.LPCWSTR)]

        class NOTIFYICONDATA(ctypes.Structure):
            _fields_ = [("cbSize", W.DWORD), ("hWnd", W.HWND), ("uID", W.UINT), ("uFlags", W.UINT),
                        ("uCallbackMessage", W.UINT), ("hIcon", W.HICON), ("szTip", W.WCHAR * 128),
                        ("dwState", W.DWORD), ("dwStateMask", W.DWORD), ("szInfo", W.WCHAR * 256),
                        ("uVersion", W.UINT), ("szInfoTitle", W.WCHAR * 64), ("dwInfoFlags", W.DWORD),
                        ("guidItem", ctypes.c_byte * 16), ("hBalloonIcon", W.HICON)]
        self._NID = NOTIFYICONDATA

        def wndproc(hwnd, msg, wp, lp):
            if msg == self.CALLBACK:
                if lp in (0x0202, 0x0203):          # venstreklikk / dobbeltklikk
                    self._idle(self.on_activate)
                elif lp == 0x0205:                  # høyreklikk → meny
                    self._menu(hwnd)
                return 0
            if msg == 0x0002:                       # WM_DESTROY
                u32.PostQuitMessage(0)
                return 0
            return u32.DefWindowProcW(hwnd, msg, wp, lp)
        self._wndproc = WNDPROC(wndproc)            # hold referansen
        hinst = k32.GetModuleHandleW(None)
        wc = WNDCLASS(0, self._wndproc, 0, 0, hinst, None, None, None, None, "KontrollsenterTray")
        u32.RegisterClassW(ctypes.byref(wc))
        self.hwnd = u32.CreateWindowExW(0, "KontrollsenterTray", "Kontrollsenter", 0, 0, 0, 0, 0, None, None,
                                        hinst, None)
        ico = os.path.join(APP_DIR, "icons", "kontrollsenter.ico")
        self.hicon = u32.LoadImageW(None, ico, 1, 0, 0, 0x10 | 0x40) if os.path.exists(ico) else \
            u32.LoadIconW(None, 32512)
        nid = self._nid()
        sh.Shell_NotifyIconW(self.NIM_ADD, ctypes.byref(nid))
        self._ready.set()
        msg = W.MSG()
        while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))

    def _nid(self):
        nid = self._NID()
        nid.cbSize = ctypes.sizeof(self._NID)
        nid.hWnd, nid.uID = self.hwnd, 1
        nid.uFlags = self.NIF_MESSAGE | self.NIF_ICON | self.NIF_TIP
        nid.uCallbackMessage = self.CALLBACK
        nid.hIcon = self.hicon
        nid.szTip = (self.tooltip or self.title)[:127]
        return nid

    @staticmethod
    def _idle(fn):
        from gi.repository import GLib
        GLib.idle_add(lambda: (fn(), False)[1])

    def _menu(self, hwnd):
        u32 = ctypes.windll.user32
        from ctypes import wintypes as W
        m = u32.CreatePopupMenu()
        ids = {}
        for n, it in enumerate(self.items, 1):
            text = it[1]
            if text == "-":
                u32.AppendMenuW(m, 0x800, 0, None)              # skillelinje
                continue
            flags = 0x8 if (len(it) > 3 and it[3]) else 0       # MF_CHECKED
            u32.AppendMenuW(m, flags, n, self.tr(text))
            ids[n] = it[2]
        pt = W.POINT()
        u32.GetCursorPos(ctypes.byref(pt))
        u32.SetForegroundWindow(hwnd)
        cmd = u32.TrackPopupMenu(m, 0x100 | 0x2, pt.x, pt.y, 0, hwnd, None)   # TPM_RETURNCMD | RIGHTBUTTON
        u32.DestroyMenu(m)
        if cmd and ids.get(cmd):
            self._idle(ids[cmd])

    def set_tooltip(self, text):
        if text and text != self.tooltip and self.hwnd:
            self.tooltip = f"Kontrollsenter · {text}"
            nid = self._nid()
            ctypes.windll.shell32.Shell_NotifyIconW(self.NIM_MODIFY, ctypes.byref(nid))

    def set_items(self, items):
        self.items = items

    def notify(self, title, body):
        """Windows-varsel (boble/varslingssenter) fra ikonet i statusfeltet."""
        if not self.hwnd:
            return
        nid = self._nid()
        nid.uFlags |= 0x10                      # NIF_INFO
        nid.szInfoTitle = title[:63]
        nid.szInfo = body[:255]
        nid.dwInfoFlags = 0x4 | 0x20            # NIIF_USER | NIIF_LARGE_ICON
        nid.hBalloonIcon = self.hicon
        ctypes.windll.shell32.Shell_NotifyIconW(self.NIM_MODIFY, ctypes.byref(nid))


# --------------------------------------------------------------------------
# Bare én Kontrollsenter om gangen (D-Bus gjør dette på Linux)
# --------------------------------------------------------------------------
SINGLE_PORT = 27011


def already_running():
    """True hvis Kontrollsenter allerede kjører – da bes det om å vise vinduet sitt."""
    import socket
    try:
        with socket.create_connection(("127.0.0.1", SINGLE_PORT), timeout=1) as s:
            s.sendall(b"show\n")
        return True
    except OSError:
        return False


def listen_for_show(on_show):
    """Lytt etter «vis vinduet» fra nye oppstarter (kalles i programmet som allerede kjører)."""
    import socket

    def loop():
        srv = socket.socket()
        try:
            srv.bind(("127.0.0.1", SINGLE_PORT))
        except OSError:
            return
        srv.listen(2)
        while True:
            c, _a = srv.accept()
            try:
                if c.recv(16).startswith(b"show"):
                    WinTray._idle(on_show)
            finally:
                c.close()
    threading.Thread(target=loop, daemon=True).start()

    def close(self):
        if self.hwnd:
            nid = self._nid()
            ctypes.windll.shell32.Shell_NotifyIconW(self.NIM_DELETE, ctypes.byref(nid))
            ctypes.windll.user32.PostMessageW(self.hwnd, 0x0010, 0, 0)   # WM_CLOSE
            self.hwnd = None


# --------------------------------------------------------------------------
# Enheter (PnP) – hvilke USB-/HID-/Bluetooth-/nettverksenheter som finnes
# --------------------------------------------------------------------------
PNP_CACHE = os.path.expanduser("~/.cache/systemmonitor/pnp.json")


def _pnp_query():
    import json
    ps = ("Get-PnpDevice -PresentOnly | Select-Object InstanceId, Class, FriendlyName, Status | "
          "ConvertTo-Json -Compress")
    code, out = run(["powershell", "-NoProfile", "-Command", ps], 40)
    try:
        data = json.loads(out[out.find("["):]) if "[" in out else []
    except ValueError:
        data = []
    return [{"id": d.get("InstanceId") or "", "cls": d.get("Class") or "", "name": d.get("FriendlyName") or "",
             "ok": d.get("Status") == "OK"} for d in data if isinstance(d, dict)]


def pnp_devices():
    """Enhetene fra forrige oppstart (raskt), og frisk liste i bakgrunnen til neste gang.
    Første gang (ingen hurtigbuffer) hentes lista med en gang."""
    import json
    try:
        with open(PNP_CACHE, encoding="utf-8") as f:
            cached = json.load(f)
    except (OSError, ValueError):
        cached = None

    def refresh():
        devs = _pnp_query()
        if devs:
            os.makedirs(os.path.dirname(PNP_CACHE), exist_ok=True)
            with open(PNP_CACHE, "w", encoding="utf-8") as f:
                json.dump(devs, f)
        return devs
    if cached is None:
        return refresh()
    threading.Thread(target=refresh, daemon=True).start()
    return cached


def bios_info():
    import winreg
    out = {}
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\BIOS") as k:
            for name in ("SystemManufacturer", "SystemProductName", "BaseBoardManufacturer", "BaseBoardProduct",
                         "BIOSVersion"):
                try:
                    out[name] = str(winreg.QueryValueEx(k, name)[0]).strip()
                except OSError:
                    pass
    except OSError:
        pass
    return out


def open_uri(uri):
    """Åpne en nettadresse, en fil eller en Windows-innstilling (f.eks. ms-settings:bluetooth)."""
    try:
        os.startfile(uri)
        return True
    except (OSError, AttributeError):
        return False
