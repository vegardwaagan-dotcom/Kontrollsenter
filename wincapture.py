"""Windows: skjermbilde av hele skjermen med Windows' egen skjermkopi (GDI), og mappen «Opptak» (Captures).

Brukes av skjermbilde i appen, «Lagre skjermbilde» og «Se på» – uten PowerShell og uten Xbox Game Bar,
så det virker også på skrivebordet og når Game Bar er slått av.
"""
import ctypes
import os
import sys

IS_WIN = sys.platform == "win32"


def _dpi_aware():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)        # riktig størrelse på skjermer med skalering
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


_API = None


def _api():
    """user32/gdi32 med riktige typer – uten dette blir 64-bits håndtak (HDC, HBITMAP) kuttet til 32 bit."""
    global _API
    if _API:
        return _API
    from ctypes import c_int, c_uint, c_ulong, c_void_p
    u, g = ctypes.WinDLL("user32"), ctypes.WinDLL("gdi32")
    u.GetDC.restype, u.GetDC.argtypes = c_void_p, [c_void_p]
    u.ReleaseDC.restype, u.ReleaseDC.argtypes = c_int, [c_void_p, c_void_p]
    u.GetSystemMetrics.restype, u.GetSystemMetrics.argtypes = c_int, [c_int]
    g.CreateCompatibleDC.restype, g.CreateCompatibleDC.argtypes = c_void_p, [c_void_p]
    g.CreateCompatibleBitmap.restype, g.CreateCompatibleBitmap.argtypes = c_void_p, [c_void_p, c_int, c_int]
    g.SelectObject.restype, g.SelectObject.argtypes = c_void_p, [c_void_p, c_void_p]
    g.SetStretchBltMode.restype, g.SetStretchBltMode.argtypes = c_int, [c_void_p, c_int]
    g.SetBrushOrgEx.restype, g.SetBrushOrgEx.argtypes = c_int, [c_void_p, c_int, c_int, c_void_p]
    g.StretchBlt.restype = c_int
    g.StretchBlt.argtypes = [c_void_p, c_int, c_int, c_int, c_int, c_void_p, c_int, c_int, c_int, c_int, c_ulong]
    g.GetDIBits.restype = c_int
    g.GetDIBits.argtypes = [c_void_p, c_void_p, c_uint, c_uint, c_void_p, c_void_p, c_uint]
    g.DeleteObject.restype, g.DeleteObject.argtypes = c_int, [c_void_p]
    g.DeleteDC.restype, g.DeleteDC.argtypes = c_int, [c_void_p]
    _API = (u, g)
    return _API


def grab(width=None):
    """GdkPixbuf (RGB, uten gjennomsiktighet) av hele skrivebordet – alle skjermer. width = skaler ned til bredden."""
    from ctypes import wintypes
    import gi
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf, GLib
    _dpi_aware()
    u, g = _api()
    x0, y0 = u.GetSystemMetrics(76), u.GetSystemMetrics(77)            # SM_X/YVIRTUALSCREEN
    sw, sh = u.GetSystemMetrics(78), u.GetSystemMetrics(79)            # SM_CX/CYVIRTUALSCREEN
    if sw <= 0 or sh <= 0:
        x0, y0, sw, sh = 0, 0, u.GetSystemMetrics(0), u.GetSystemMetrics(1)
    w = min(int(width), sw) if width else sw
    h = max(2, int(sh * w / sw)) // 2 * 2

    class BMI(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                    ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]
    src = u.GetDC(None)
    if not src:
        raise RuntimeError("fikk ikke tilgang til skjermen")
    mem = g.CreateCompatibleDC(src)
    bmp = g.CreateCompatibleBitmap(src, w, h)
    try:
        old = g.SelectObject(mem, bmp)
        g.SetStretchBltMode(mem, 4)                                    # HALFTONE – pen nedskalering
        g.SetBrushOrgEx(mem, 0, 0, None)
        ok = g.StretchBlt(mem, 0, 0, w, h, src, x0, y0, sw, sh, 0x00CC0020 | 0x40000000)   # SRCCOPY | CAPTUREBLT
        g.SelectObject(mem, old)                     # bildet må være frakoblet før GetDIBits
        if not ok:
            raise RuntimeError("Windows ga ikke skjermbildet (StretchBlt)")
        bmi = BMI(ctypes.sizeof(BMI), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        if not g.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bmi), 0):
            raise RuntimeError("Windows ga ikke skjermbildet (GetDIBits)")
        px = buf.raw
    finally:
        g.DeleteObject(bmp)
        g.DeleteDC(mem)
        u.ReleaseDC(None, src)
    rgb = bytearray(w * h * 3)                                         # BGRA → RGB
    rgb[0::3], rgb[1::3], rgb[2::3] = px[2::4], px[1::4], px[0::4]
    return GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(bytes(rgb)), GdkPixbuf.Colorspace.RGB, False, 8, w, h, w * 3)


def jpeg(width=None, quality=75):
    ok, data = grab(width).save_to_bufferv("jpeg", ["quality"], [str(quality)])
    if not ok:
        raise RuntimeError("kunne ikke lage JPEG")
    return bytes(data)


def captures_dir():
    """Mappen Windows og Xbox Game Bar lagrer klipp og skjermbilder i («Opptak»/Captures) – også når den er flyttet,
    f.eks. til OneDrive."""
    for guid in ("{EDC0FE71-98D8-4F4A-B920-C8DC133CB165}",            # FOLDERID_Captures
                 "{18989B1D-99B5-455B-841C-AB7C74E4DDFC}"):           # FOLDERID_Videos (+ \Captures)
        try:
            class GUID(ctypes.Structure):
                _fields_ = [("a", ctypes.c_ulong), ("b", ctypes.c_ushort), ("c", ctypes.c_ushort),
                            ("d", ctypes.c_ubyte * 8)]
            gu = GUID()
            ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p(guid), ctypes.byref(gu))
            p = ctypes.c_void_p()
            sh = ctypes.WinDLL("shell32")
            sh.SHGetKnownFolderPath.restype = ctypes.c_long
            sh.SHGetKnownFolderPath.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p]
            if sh.SHGetKnownFolderPath(ctypes.byref(gu), 0, None, ctypes.byref(p)) == 0 and p.value:
                path = ctypes.wstring_at(p.value)
                ole = ctypes.WinDLL("ole32")
                ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
                ole.CoTaskMemFree(p)
                if path:
                    return path if guid.startswith("{EDC0") else os.path.join(path, "Captures")
        except (AttributeError, OSError):
            continue
    return os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), "Videos", "Captures")
