"""Lag velkomstbildet til installasjonen (164x314, 24-bit BMP): mørk flate med logoen og navnet."""
import os
import struct
import sys
import tempfile

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Gio, Graphene, Gtk  # noqa: E402

svg, out = sys.argv[1], sys.argv[2]
W, H, LOGO = 164, 314, 112

# logoen som PNG (via GTK, samme gjengivelse som i programmet)
Gtk.init()
win = Gtk.Window()
win.present()
snap = Gtk.Snapshot()
Gtk.IconPaintable.new_for_file(Gio.File.new_for_path(svg), LOGO, 1).snapshot(snap, LOGO, LOGO)
tex = win.get_native().get_renderer().render_texture(snap.to_node(), Graphene.Rect().init(0, 0, LOGO, LOGO))
png = os.path.join(tempfile.mkdtemp(), "logo.png")
tex.save_to_png(png)

surf = cairo.ImageSurface(cairo.FORMAT_RGB24, W, H)
cr = cairo.Context(surf)
g = cairo.LinearGradient(0, 0, W * 0.35, H)
g.add_color_stop_rgb(0, 0x23 / 255, 0x2a / 255, 0x4d / 255)
g.add_color_stop_rgb(0.55, 0x13 / 255, 0x17 / 255, 0x33 / 255)
g.add_color_stop_rgb(1, 0x08 / 255, 0x0a / 255, 0x17 / 255)
cr.set_source(g)
cr.paint()
# svak lysring bak logoen
rg = cairo.RadialGradient(W / 2, 112, 10, W / 2, 112, 95)
rg.add_color_stop_rgba(0, 0.24, 0.48, 1.0, 0.35)
rg.add_color_stop_rgba(1, 0.24, 0.48, 1.0, 0.0)
cr.set_source(rg)
cr.paint()
logo = cairo.ImageSurface.create_from_png(png)
cr.set_source_surface(logo, (W - LOGO) / 2, 112 - LOGO / 2)
cr.paint()
for text, size, y, alpha in (("Kontrollsenter", 17, 214, 1.0), ("for Windows", 11.5, 236, 0.65)):
    cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD if size > 12 else
                        cairo.FONT_WEIGHT_NORMAL)
    cr.set_font_size(size)
    ext = cr.text_extents(text)
    cr.move_to((W - ext.width) / 2 - ext.x_bearing, y)
    cr.set_source_rgba(1, 1, 1, alpha)
    cr.show_text(text)
surf.flush()

# 24-bit BMP (nederste rad først, rader polstret til 4 byte)
data, stride = surf.get_data(), surf.get_stride()
row = (W * 3 + 3) & ~3
pix = bytearray()
for y in range(H - 1, -1, -1):
    line = data[y * stride:y * stride + W * 4]
    for x in range(W):
        b, gr, r = line[x * 4], line[x * 4 + 1], line[x * 4 + 2]
        pix += bytes((b, gr, r))
    pix += b"\0" * (row - W * 3)
hdr = struct.pack("<2sIHHI", b"BM", 54 + len(pix), 0, 0, 54)
info = struct.pack("<IiiHHIIiiII", 40, W, H, 1, 24, 0, len(pix), 2835, 2835, 0, 0)
open(out, "wb").write(hdr + info + pix)
png_preview = out.replace(".bmp", "-forhand.png")
surf.write_to_png(png_preview)
print(out, len(hdr + info + pix), "byte")
