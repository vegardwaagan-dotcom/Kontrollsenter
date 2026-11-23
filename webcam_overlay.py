#!/usr/bin/env python3
"""Webkamera-overlay i spill: viser deg selv og/eller de andre i talekanalen over spillet.

Eget lite program, startet og stoppet av Kontrollsenter (chatvc.ov_sync).
  Linux: GTK3 + gtk-layer-shell («overlay»-laget i KDE/Wayland – ligger over fullskjermspill).
  Windows: webcam_overlay_win.py (GTK4, «alltid øverst» og klikk-gjennom med Win32).

Låst: museklikk går rett gjennom til spillet. Låst opp (Ctrl+Shift+O, eller i Kontrollsenter): dra for å flytte,
musehjulet eller −/+ for størrelse, 🔒 for å låse igjen. Plassering og størrelse lagres.

Bildene leses fra overlay-mappa (minne): <nøkkel>.rgba (rått) eller <nøkkel>.jpg (mobilkameraet), og kilder.json.
Innstillingene fra ~/.config/systemmonitor/chat-overlay.json.
"""
import json
import os
import struct
import sys
import tempfile
import time

if sys.platform == "win32":                                  # Windows: egen GTK4-utgave
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import webcam_overlay_win
    webcam_overlay_win.main()
    sys.exit(0)

import gi  # noqa: E402

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell  # noqa: E402
except (ValueError, ImportError):
    GtkLayerShell = None

DIR = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir(), "ks-vc-overlay")
CFG = os.environ.get("KS_OV_CFG") or os.path.expanduser("~/.config/systemmonitor/chat-overlay.json")
HDR = struct.Struct("<4sIIIQ")                            # «KSVC», bredde, høyde, stride, nummer
SIZES = {"liten": 200, "middels": 300, "stor": 440}
PARENT = int(sys.argv[sys.argv.index("--forelder") + 1]) if "--forelder" in sys.argv else 0

CSS = b"""
window { background: transparent; }
.tile { border-radius: 12px; background: rgba(0,0,0,0.55); padding: 3px; }
.tile.talking { border: 3px solid #3ad16b; }
.name { color: white; font-weight: 700; font-size: 11px; background: rgba(0,0,0,0.55); border-radius: 6px;
        padding: 1px 6px; margin: 4px; }
.edit { border: 2px dashed #ff6aa8; border-radius: 14px; padding: 4px; background: rgba(20,10,20,0.35); }
.bar { background: rgba(0,0,0,0.75); border-radius: 10px; padding: 4px 8px; color: white; }
.bar button { padding: 2px 8px; min-height: 0; }
"""


def cfg():
    try:
        with open(CFG) as f:
            c = json.load(f)
    except (OSError, ValueError):
        c = {}
    width = int(c.get("width") or SIZES.get(c.get("size"), 300))
    return {"show": c.get("show", "both"), "corner": c.get("corner", "top-right"),
            "width": max(120, min(1200, width)), "x": int(c.get("x", 28)), "y": int(c.get("y", 28)),
            "opacity": max(0, min(100, int(c.get("opacity", 100)))), "locked": c.get("locked", True) is not False}


def save(**kw):
    """Lagre endringer gjort i selve overlayet (plassering, størrelse, lås)."""
    try:
        with open(CFG) as f:
            c = json.load(f)
    except (OSError, ValueError):
        c = {}
    c.update(kw)
    tmp = CFG + ".ov.tmp"
    with open(tmp, "w") as f:
        json.dump(c, f, indent=1)
    os.replace(tmp, CFG)


def sources(show):
    try:
        with open(os.path.join(DIR, "kilder.json")) as f:
            src = json.load(f)
    except (OSError, ValueError):
        return []
    if show == "me":
        return [s for s in src if s["me"]]
    if show == "peer":
        return [s for s in src if not s["me"]]
    return sorted(src, key=lambda s: s["me"])               # motparten først, meg sist


def read_frame(path):
    """(pixbuf, nummer) fra .rgba eller .jpg, eller None."""
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


class Overlay(Gtk.Window):
    def __init__(self, test_png=None):
        super().__init__(title="Kontrollsenter – webkamera-overlay")
        self.set_decorated(False)
        self.set_app_paintable(True)
        scr = self.get_screen()
        vis = scr.get_rgba_visual()
        if vis:
            self.set_visual(vis)
        prov = Gtk.CssProvider()
        prov.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(scr, prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.test_png = test_png
        self.layer = False
        if not test_png and GtkLayerShell and GtkLayerShell.is_supported():
            GtkLayerShell.init_for_window(self)
            GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
            GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.NONE)
            GtkLayerShell.set_namespace(self, "kontrollsenter-webcam")
            GtkLayerShell.set_exclusive_zone(self, -1)
            self.layer = True
        elif not test_png:                                  # X11 / uten layer-shell: «alltid øverst»
            self.set_keep_above(True)
            self.set_skip_taskbar_hint(True)
            self.set_accept_focus(False)
        # innhold: [verktøylinje når låst opp] + rutene
        self.outer = Gtk.EventBox()
        self.outer.set_visible_window(False)
        self.outer.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK |
                              Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.SCROLL_MASK |
                              Gdk.EventMask.SMOOTH_SCROLL_MASK)
        self.outer.connect("button-press-event", self._press)
        self.outer.connect("button-release-event", self._release)
        self.outer.connect("motion-notify-event", self._motion)
        self.outer.connect("scroll-event", self._scroll)
        self.vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.outer.add(self.vbox)
        self.bar = Gtk.Box(spacing=6)
        self.bar.get_style_context().add_class("bar")
        hint = Gtk.Label(label="✋ Dra for å flytte · hjul eller −/+ for størrelse")
        self.bar.pack_start(hint, True, True, 0)
        for lab, fn in (("−", lambda *_: self._resize(-30)), ("+", lambda *_: self._resize(30)),
                        ("🔒 Lås", lambda *_: save(locked=True))):
            b = Gtk.Button(label=lab)
            b.connect("clicked", fn)
            self.bar.pack_start(b, False, False, 0)
        self.vbox.pack_start(self.bar, False, False, 0)
        self.box = Gtk.Box(spacing=8)
        self.vbox.pack_start(self.box, False, False, 0)
        self.tiles = {}                                     # nøkkel -> [overlay, image, label, sist nummer, bredde]
        self.placed = None
        self.locked = None
        self.drag = None
        self.c = cfg()
        if test_png:
            self.off = Gtk.OffscreenWindow()
            self.off.add(self.outer)
            self.off.show_all()
            GLib.timeout_add(2500, self._save_png)
        else:
            self.add(self.outer)
            self.connect("realize", lambda *_: self._input())
        GLib.timeout_add(66, self.tick)

    # ---------------- test
    def _save_png(self):
        pb = self.off.get_pixbuf()
        if pb:
            pb.savev(self.test_png, "png", [], [])
        print("kilder vist:", list(self.tiles), "låst:", self.c["locked"], flush=True)
        Gtk.main_quit()
        return False

    # ---------------- klikk-gjennom og plassering
    def _input(self):
        if self.test_png:
            return
        try:
            import cairo
            self.input_shape_combine_region(cairo.Region() if self.c["locked"] else None)
        except Exception:  # noqa: BLE001
            pass

    def _apply_place(self):
        c = self.c
        key = (c["corner"], c["x"], c["y"])
        if key == self.placed:
            return
        self.placed = key
        if not self.layer:
            return
        top, left = "top" in c["corner"], "left" in c["corner"]
        E = GtkLayerShell.Edge
        for edge, on, m in ((E.TOP, top, c["y"]), (E.BOTTOM, not top, c["y"]), (E.LEFT, left, c["x"]),
                            (E.RIGHT, not left, c["x"])):
            GtkLayerShell.set_anchor(self, edge, on)
            GtkLayerShell.set_margin(self, edge, int(max(0, m)) if on else 0)

    # ---------------- flytt og størrelse (bare når låst opp)
    def _press(self, _w, ev):
        if self.c["locked"] or ev.button != 1:
            return False
        self.drag = [ev.x, ev.y]
        return True

    def _motion(self, _w, ev):
        if not self.drag:
            return False
        dx, dy = ev.x - self.drag[0], ev.y - self.drag[1]
        if abs(dx) < 1 and abs(dy) < 1:
            return True
        c = self.c
        c["x"] = max(0, c["x"] + (dx if "left" in c["corner"] else -dx))
        c["y"] = max(0, c["y"] + (dy if "top" in c["corner"] else -dy))
        self._apply_place()
        if not self.layer:
            self.move(int(c["x"]), int(c["y"]))
        return True

    def _release(self, _w, _ev):
        if self.drag:
            self.drag = None
            save(x=int(self.c["x"]), y=int(self.c["y"]))
        return False

    def _scroll(self, _w, ev):
        if self.c["locked"]:
            return False
        ok, _dx, dy = ev.get_scroll_deltas()
        if ok:
            self._resize(int(-dy * 30))
        else:
            self._resize(30 if ev.direction == Gdk.ScrollDirection.UP else -30)
        return True

    def _resize(self, d):
        w = max(120, min(1200, self.c["width"] + d))
        self.c["width"] = w
        save(width=w)

    # ---------------- hovedløkka
    def tick(self):
        if PARENT:                                          # Kontrollsenter er avsluttet: lukk overlayet også
            try:
                os.kill(PARENT, 0)
            except OSError:
                Gtk.main_quit()
                return False
        old = self.c
        self.c = c = cfg()
        if self.drag:                                       # ikke hopp tilbake midt i en flytting
            c["x"], c["y"] = old["x"], old["y"]
        self._apply_place()
        if c["locked"] != self.locked:
            self.locked = c["locked"]
            self._input()
            ctx = self.vbox.get_style_context()
            (ctx.remove_class if c["locked"] else ctx.add_class)("edit")
            self.bar.set_no_show_all(c["locked"])
            self.bar.set_visible(not c["locked"])
        # synlighet 0–100 %; låst opp vises den alltid litt, så du ser hva du flytter
        op = c["opacity"] / 100
        self.outer.set_opacity(op if c["locked"] else max(op, 0.6))
        width = c["width"]
        want = []
        now = time.time()
        for s in sources(c["show"]):
            for ext in (".rgba", ".jpg"):
                path = os.path.join(DIR, s["key"] + ext)
                try:
                    if now - os.path.getmtime(path) <= 3:  # ingen bilder på 3 s: kameraet er av
                        want.append((s, path))
                        break
                except OSError:
                    continue
        if not want and not c["locked"]:                    # låst opp uten kamera: en plassholder å flytte
            want = [({"key": "_ph", "name": "Webkamera", "me": True}, None)]
        keys = [s["key"] for s, _p in want]
        for k in [k for k in self.tiles if k not in keys]:
            self.box.remove(self.tiles.pop(k)[0])
        for s, path in want:
            if s["key"] not in self.tiles:
                ov = Gtk.Overlay()
                img = Gtk.Image()
                ov.add(img)
                lab = Gtk.Label(label=s["name"], halign=Gtk.Align.START, valign=Gtk.Align.END)
                lab.get_style_context().add_class("name")
                ov.add_overlay(lab)
                ov.get_style_context().add_class("tile")
                ov.show_all()
                self.box.pack_start(ov, False, False, 0)
                self.tiles[s["key"]] = [ov, img, lab, None, 0]
            t = self.tiles[s["key"]]
            (t[0].get_style_context().add_class if s.get("talking") else
             t[0].get_style_context().remove_class)("talking")
            if path is None:                                # plassholder
                if t[4] != width:
                    t[4] = width
                    pb = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, width, width * 9 // 16)
                    pb.fill(0x303030ff)
                    t[1].set_from_pixbuf(pb)
                continue
            try:
                r = read_frame(path)
                if not r or (r[1] == t[3] and t[4] == width):
                    continue
                pb, t[3] = r
                rot = {90: GdkPixbuf.PixbufRotation.CLOCKWISE, 180: GdkPixbuf.PixbufRotation.UPSIDEDOWN,
                       270: GdkPixbuf.PixbufRotation.COUNTERCLOCKWISE}.get(s.get("rot"))
                if rot is not None:                         # mobilkameraet sender bildet slik sensoren ser det
                    pb = pb.rotate_simple(rot)
                t[4] = width
                t[1].set_from_pixbuf(pb.scale_simple(width, max(1, int(pb.get_height() * width / pb.get_width())),
                                                     GdkPixbuf.InterpType.BILINEAR))
            except (OSError, struct.error, GLib.Error, ValueError, TypeError):
                continue
        if self.test_png:
            return True
        if self.tiles:
            if not self.get_visible():
                self.show_all()
                self.bar.set_visible(not c["locked"])
                self._input()
        elif self.get_visible():
            self.hide()
        return True


def main():
    if "--sjekk" in sys.argv:                               # brukes av Kontrollsenter: virker overlay her?
        print("layer-shell" if GtkLayerShell and GtkLayerShell.is_supported() else "vindu")
        return
    Overlay(sys.argv[sys.argv.index("--test-png") + 1] if "--test-png" in sys.argv else None)
    Gtk.main()


if __name__ == "__main__":
    main()
