#!/usr/bin/env python3
"""Webkamera-overlay i spill: viser deg selv og/eller de andre i talekanalen i et hjørne over spillet.

Eget lite program (GTK3 + gtk-layer-shell, «overlay»-laget i KDE/Wayland – ligger over fullskjermspill, og museklikk
går rett gjennom til spillet). Startes og stoppes av Kontrollsenter (chatvc.ov_sync). Bildene leses fra
$XDG_RUNTIME_DIR/ks-vc-overlay/ (minne, ikke disk), innstillingene fra ~/.config/systemmonitor/chat-overlay.json.
"""
import json
import os
import struct
import sys
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, GLib, Gtk  # noqa: E402

try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell  # noqa: E402
except (ValueError, ImportError):
    GtkLayerShell = None

DIR = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "ks-vc-overlay")
CFG = os.environ.get("KS_OV_CFG") or os.path.expanduser("~/.config/systemmonitor/chat-overlay.json")
HDR = struct.Struct("<4sIIIQ")                            # «KSVC», bredde, høyde, stride, nummer
SIZES = {"liten": 200, "middels": 300, "stor": 440}
PARENT = int(sys.argv[sys.argv.index("--forelder") + 1]) if "--forelder" in sys.argv else 0

CSS = b"""
window { background: transparent; }
.tile { border-radius: 12px; background: rgba(0,0,0,0.55); padding: 3px; }
.tile.talking { box-shadow: 0 0 0 3px #3ad16b; }
.name { color: white; font-weight: 700; font-size: 11px; background: rgba(0,0,0,0.55); border-radius: 6px;
        padding: 1px 6px; margin: 4px; }
"""


def cfg():
    try:
        with open(CFG) as f:
            c = json.load(f)
    except (OSError, ValueError):
        c = {}
    return {"show": c.get("show", "both"), "corner": c.get("corner", "top-right"),
            "size": c.get("size", "middels"), "opacity": int(c.get("opacity", 100))}


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
        if test_png:                                        # tester: tegn usynlig og lagre som bilde
            pass
        elif GtkLayerShell and GtkLayerShell.is_supported():
            GtkLayerShell.init_for_window(self)
            GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
            GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.NONE)
            GtkLayerShell.set_namespace(self, "kontrollsenter-webcam")
            GtkLayerShell.set_exclusive_zone(self, -1)
        else:                                               # X11 / uten layer-shell: «alltid øverst»
            self.set_keep_above(True)
            self.set_skip_taskbar_hint(True)
            self.set_accept_focus(False)
        self.box = Gtk.Box(spacing=8)
        if test_png:
            self.off = Gtk.OffscreenWindow()
            self.off.add(self.box)
            self.off.show_all()
            GLib.timeout_add(2500, self._save)
        else:
            self.add(self.box)
        self.tiles = {}                                     # nøkkel -> (eventbox, image, label, sist nummer)
        self.corner = None
        self.connect("realize", lambda *_: self._click_through())
        GLib.timeout_add(66, self.tick)

    def _save(self):
        pb = self.off.get_pixbuf()
        if pb:
            pb.savev(self.test_png, "png", [], [])
        print("kilder vist:", list(self.tiles), flush=True)
        Gtk.main_quit()
        return False

    def _click_through(self):
        try:
            import cairo
            self.input_shape_combine_region(cairo.Region())    # museklikk går til spillet
        except Exception:  # noqa: BLE001
            pass

    def _place(self, c):
        if not (GtkLayerShell and GtkLayerShell.is_layer_window(self)) or c["corner"] == self.corner:
            return
        self.corner = c["corner"]
        top = "top" in c["corner"]
        left = "left" in c["corner"]
        E = GtkLayerShell.Edge
        for edge, on in ((E.TOP, top), (E.BOTTOM, not top), (E.LEFT, left), (E.RIGHT, not left)):
            GtkLayerShell.set_anchor(self, edge, on)
            GtkLayerShell.set_margin(self, edge, 28 if on else 0)

    def _sources(self, c):
        try:
            with open(os.path.join(DIR, "kilder.json")) as f:
                src = json.load(f)
        except (OSError, ValueError):
            return []
        if c["show"] == "me":
            return [s for s in src if s["me"]]
        if c["show"] == "peer":
            return [s for s in src if not s["me"]]
        return sorted(src, key=lambda s: s["me"])           # motparten først, meg sist (nærmest hjørnet)

    def tick(self):
        if PARENT:                                          # Kontrollsenter er avsluttet: lukk overlayet også
            try:
                os.kill(PARENT, 0)
            except OSError:
                Gtk.main_quit()
                return False
        c = cfg()
        self._place(c)
        self.set_opacity(max(0.2, min(1.0, c["opacity"] / 100)))
        width = SIZES.get(c["size"], 300)
        want = []
        now = time.time()
        for s in self._sources(c):
            path = os.path.join(DIR, s["key"] + ".rgba")
            try:
                if now - os.path.getmtime(path) > 3:        # ingen bilder på 3 s: kameraet er av
                    continue
            except OSError:
                continue
            want.append((s, path))
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
                self.tiles[s["key"]] = [ov, img, lab, -1]
            t = self.tiles[s["key"]]
            (t[0].get_style_context().add_class if s.get("talking") else
             t[0].get_style_context().remove_class)("talking")
            try:
                with open(path, "rb") as f:
                    raw = f.read()
                magic, w, h, stride, seq = HDR.unpack_from(raw, 0)
                if magic != b"KSVC" or seq == t[3]:
                    continue
                t[3] = seq
                data = GLib.Bytes.new(raw[HDR.size:HDR.size + stride * h])
                pb = GdkPixbuf.Pixbuf.new_from_bytes(data, GdkPixbuf.Colorspace.RGB, True, 8, w, h, stride)
                t[1].set_from_pixbuf(pb.scale_simple(width, max(1, int(h * width / w)),
                                                     GdkPixbuf.InterpType.BILINEAR))
            except (OSError, struct.error, GLib.Error, ValueError):
                continue
        if self.test_png:
            return True
        if self.tiles:
            if not self.get_visible():
                self.show_all()
                self._click_through()
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
