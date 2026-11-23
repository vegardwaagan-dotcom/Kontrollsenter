"""Webkamera-overlay i spill – Windows-utgaven (GTK4 + Win32).

Alltid øverst (HWND_TOPMOST), ingen fokus (WS_EX_NOACTIVATE), og når den er låst går museklikk rett gjennom
(WS_EX_LAYERED | WS_EX_TRANSPARENT). Virker over spill i «uten ramme»/vindu-modus – eksklusiv fullskjerm (DirectX)
kan ligge over alt annet. Samme innstillinger og bilder som Linux-utgaven (webcam_overlay.py).
"""
import ctypes
import json
import os
import struct
import sys
import tempfile
import time

os.environ.setdefault("GSK_RENDERER", "cairo")           # gjennomsiktige GL-vinduer blir ofte svarte på Windows

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

DIR = os.path.join(tempfile.gettempdir(), "ks-vc-overlay")
CFG = os.environ.get("KS_OV_CFG") or os.path.expanduser("~/.config/systemmonitor/chat-overlay.json")
HDR = struct.Struct("<4sIIIQ")
SIZES = {"liten": 200, "middels": 300, "stor": 440}
PARENT = int(sys.argv[sys.argv.index("--forelder") + 1]) if "--forelder" in sys.argv else 0
TITLE = "Kontrollsenter – webkamera-overlay"

U = ctypes.windll.user32 if sys.platform == "win32" else None
GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT = -20, 0x80000, 0x20
WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE, WS_EX_TOPMOST = 0x80, 0x08000000, 0x8
HWND_TOPMOST, SWP_NOSIZE, SWP_NOACTIVATE, SWP_SHOWWINDOW = -1, 0x1, 0x10, 0x40
LWA_ALPHA = 0x2

CSS = """
window { background: transparent; }
.tile { border-radius: 12px; background: rgba(0,0,0,0.55); padding: 3px; }
.tile.talking { border: 3px solid #3ad16b; }
.name { color: white; font-weight: 700; font-size: 11px; background: rgba(0,0,0,0.55); border-radius: 6px;
        padding: 1px 6px; margin: 4px; }
.edit { border: 2px dashed #ff6aa8; border-radius: 14px; padding: 4px; background: rgba(20,10,20,0.35); }
.bar { background: rgba(0,0,0,0.75); border-radius: 10px; padding: 4px 8px; color: white; }
"""


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def cfg():
    try:
        with open(CFG, encoding="utf-8") as f:
            c = json.load(f)
    except (OSError, ValueError):
        c = {}
    width = int(c.get("width") or SIZES.get(c.get("size"), 300))
    return {"show": c.get("show", "both"), "corner": c.get("corner", "top-right"),
            "width": max(120, min(1200, width)), "x": int(c.get("x", 28)), "y": int(c.get("y", 28)),
            "opacity": max(0, min(100, int(c.get("opacity", 100)))), "locked": c.get("locked", True) is not False}


def save(**kw):
    try:
        with open(CFG, encoding="utf-8") as f:
            c = json.load(f)
    except (OSError, ValueError):
        c = {}
    c.update(kw)
    tmp = CFG + ".ov.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(c, f, indent=1)
    os.replace(tmp, CFG)


def sources(show):
    try:
        with open(os.path.join(DIR, "kilder.json"), encoding="utf-8") as f:
            src = json.load(f)
    except (OSError, ValueError):
        return []
    if show == "me":
        return [s for s in src if s["me"]]
    if show == "peer":
        return [s for s in src if not s["me"]]
    return sorted(src, key=lambda s: s["me"])


def read_frame(path):
    with open(path, "rb") as f:
        raw = f.read()
    if path.endswith(".jpg"):
        ld = GdkPixbuf.PixbufLoader.new_with_type("jpeg")
        ld.write(raw)
        ld.close()
        return ld.get_pixbuf(), hash(raw[-64:])
    magic, w, h, stride, seq = HDR.unpack_from(raw, 0)
    if magic != b"KSVC":
        return None
    data = GLib.Bytes.new(raw[HDR.size:HDR.size + stride * h])
    return GdkPixbuf.Pixbuf.new_from_bytes(data, GdkPixbuf.Colorspace.RGB, True, 8, w, h, stride), seq


ROT = {90: GdkPixbuf.PixbufRotation.CLOCKWISE, 180: GdkPixbuf.PixbufRotation.UPSIDEDOWN,
       270: GdkPixbuf.PixbufRotation.COUNTERCLOCKWISE}


class WinOverlay(Gtk.Window):
    def __init__(self, app):
        super().__init__(application=app, title=TITLE, decorated=False, resizable=False)
        prov = Gtk.CssProvider()
        prov.load_from_string(CSS) if hasattr(prov, "load_from_string") else prov.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), prov,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_child(self.vbox)
        self.bar = Gtk.Box(spacing=6)
        self.bar.add_css_class("bar")
        self.bar.append(Gtk.Label(label="✋ Dra for å flytte · hjul eller −/+ for størrelse", hexpand=True))
        for lab, fn in (("−", lambda *_: self._resize(-30)), ("+", lambda *_: self._resize(30)),
                        ("🔒 Lås", lambda *_: save(locked=True))):
            b = Gtk.Button(label=lab)
            b.connect("clicked", fn)
            self.bar.append(b)
        self.vbox.append(self.bar)
        self.box = Gtk.Box(spacing=8)
        self.vbox.append(self.box)
        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._drag_begin)
        drag.connect("drag-update", self._drag_update)
        drag.connect("drag-end", self._drag_end)
        self.vbox.add_controller(drag)
        sc = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL)
        sc.connect("scroll", lambda _c, _dx, dy: (not self.c["locked"]) and (self._resize(int(-dy * 30)), True)[1])
        self.vbox.add_controller(sc)
        self.tiles = {}
        self.c = cfg()
        self.locked = None
        self.hwnd = None
        self.drag = None
        self.placed = None
        GLib.timeout_add(66, self.tick)

    # ---------------- Win32
    def _hwnd(self):
        if self.hwnd:
            return self.hwnd
        try:
            gi.require_version("GdkWin32", "4.0")
            from gi.repository import GdkWin32
            self.hwnd = GdkWin32.Win32Surface.get_handle(self.get_surface())
        except Exception:  # noqa: BLE001
            self.hwnd = U.FindWindowW(None, TITLE) if U else None
        return self.hwnd

    def _style(self):
        h = self._hwnd()
        if not h or not U:
            return
        ex = U.GetWindowLongW(h, GWL_EXSTYLE) | WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST
        ex = ex | WS_EX_TRANSPARENT if self.c["locked"] else ex & ~WS_EX_TRANSPARENT
        U.SetWindowLongW(h, GWL_EXSTYLE, ex)
        op = self.c["opacity"] / 100 if self.c["locked"] else max(self.c["opacity"] / 100, 0.6)
        U.SetLayeredWindowAttributes(h, 0, int(255 * op), LWA_ALPHA)

    def _screen_pos(self):
        """Øverste venstre hjørne på skjermen ut fra hjørnet og avstanden (x, y)."""
        sw, sh = U.GetSystemMetrics(0), U.GetSystemMetrics(1)
        w, h = max(1, self.get_width()), max(1, self.get_height())
        c = self.c
        x = c["x"] if "left" in c["corner"] else sw - w - c["x"]
        y = c["y"] if "top" in c["corner"] else sh - h - c["y"]
        return int(x), int(y)

    def _place(self, force=False):
        h = self._hwnd()
        if not h or not U:
            return
        key = (self.c["corner"], self.c["x"], self.c["y"], self.get_width(), self.get_height())
        if key == self.placed and not force:
            return
        self.placed = key
        x, y = self._screen_pos()
        U.SetWindowPos(h, HWND_TOPMOST, x, y, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)

    # ---------------- flytt og størrelse
    def _drag_begin(self, _g, _x, _y):
        if self.c["locked"] or not U:
            return
        p = POINT()
        U.GetCursorPos(ctypes.byref(p))
        self.drag = (p.x, p.y, self.c["x"], self.c["y"])

    def _drag_update(self, _g, _dx, _dy):
        if not self.drag:
            return
        p = POINT()
        U.GetCursorPos(ctypes.byref(p))
        x0, y0, cx, cy = self.drag
        dx, dy = p.x - x0, p.y - y0
        self.c["x"] = max(0, cx + (dx if "left" in self.c["corner"] else -dx))
        self.c["y"] = max(0, cy + (dy if "top" in self.c["corner"] else -dy))
        self._place()

    def _drag_end(self, *_a):
        if self.drag:
            self.drag = None
            save(x=int(self.c["x"]), y=int(self.c["y"]))

    def _resize(self, d):
        self.c["width"] = max(120, min(1200, self.c["width"] + d))
        save(width=self.c["width"])

    # ---------------- hovedløkka
    def tick(self):
        if PARENT:
            try:
                h = ctypes.windll.kernel32.OpenProcess(0x1000, False, PARENT)
                code = ctypes.c_ulong()
                alive = bool(h) and ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code)) and code.value == 259
                if h:
                    ctypes.windll.kernel32.CloseHandle(h)
                if not alive:
                    self.get_application().quit()
                    return False
            except Exception:  # noqa: BLE001
                pass
        old = self.c
        self.c = c = cfg()
        if self.drag:
            c["x"], c["y"] = old["x"], old["y"]
        if c["locked"] != self.locked:
            self.locked = c["locked"]
            self.bar.set_visible(not c["locked"])
            (self.vbox.remove_css_class if c["locked"] else self.vbox.add_css_class)("edit")
        width = c["width"]
        want = []
        now = time.time()
        for s in sources(c["show"]):
            for ext in (".rgba", ".jpg"):
                path = os.path.join(DIR, s["key"] + ext)
                try:
                    if now - os.path.getmtime(path) <= 3:
                        want.append((s, path))
                        break
                except OSError:
                    continue
        if not want and not c["locked"]:
            want = [({"key": "_ph", "name": "Webkamera", "me": True}, None)]
        keys = [s["key"] for s, _p in want]
        for k in [k for k in self.tiles if k not in keys]:
            self.box.remove(self.tiles.pop(k)[0])
        for s, path in want:
            if s["key"] not in self.tiles:
                ov = Gtk.Overlay()
                pic = Gtk.Picture(can_shrink=True)
                ov.set_child(pic)
                lab = Gtk.Label(label=s["name"], halign=Gtk.Align.START, valign=Gtk.Align.END)
                lab.add_css_class("name")
                ov.add_overlay(lab)
                ov.add_css_class("tile")
                self.box.append(ov)
                self.tiles[s["key"]] = [ov, pic, lab, None, 0]
            t = self.tiles[s["key"]]
            (t[0].add_css_class if s.get("talking") else t[0].remove_css_class)("talking")
            if path is None:
                t[1].set_size_request(width, width * 9 // 16)
                t[4] = width
                continue
            try:
                r = read_frame(path)
                if not r or (r[1] == t[3] and t[4] == width):
                    continue
                pb, t[3] = r
                if s.get("rot") in ROT:
                    pb = pb.rotate_simple(ROT[s["rot"]])
                t[4] = width
                hh = max(1, int(pb.get_height() * width / pb.get_width()))
                t[1].set_size_request(width, hh)
                t[1].set_paintable(Gdk.Texture.new_for_pixbuf(pb.scale_simple(width, hh,
                                                                                GdkPixbuf.InterpType.BILINEAR)))
            except (OSError, struct.error, GLib.Error, ValueError, TypeError):
                continue
        if self.tiles:
            if not self.get_visible():
                self.set_visible(True)
                self.placed = None
            self._style()
            self._place()
        elif self.get_visible():
            self.set_visible(False)
        return True


def main():
    if "--sjekk" in sys.argv:
        print("vindu")
        return
    app = Gtk.Application(application_id="no.waagan.KontrollsenterOverlay")
    app.connect("activate", lambda a: setattr(a, "_w", WinOverlay(a)))
    app.run([])
