"""Rullehjul for alle valgmenyer – som på den gamle iPhone, men med «liquid glass».

install(window) gjør at alle Gtk.DropDown og Adw.ComboRow i vinduet (også i dialoger som åpnes senere) viser et
rullehjul i stedet for en vanlig liste: elementene ligger på en sylinder som snurrer, det valgte står i et
glassbånd i midten, og hjulet snapper mykt på plass. Rull med musehjulet, dra, trykk på et valg, eller bruk
piltastene og Enter. Esc avbryter. Lister med mer enn 80 valg beholder den vanlige listen med søk.
"""
import math
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Adw, Gdk, GLib, Gtk, Pango, PangoCairo  # noqa: E402

ROW = 42                # høyden på en rad i midten
VISIBLE = 3.4           # rader over og under midten som vises
MAX_ITEMS = 80

CSS = """
popover.ks-wheel > contents {
  padding: 10px;
  border-radius: 26px;
  background-color: color-mix(in srgb, var(--popover-bg-color, @popover_bg_color) 72%, transparent);
  background-image: linear-gradient(160deg, alpha(white, 0.16), alpha(white, 0.03) 40%, transparent 65%, alpha(white, 0.06)),
                    radial-gradient(ellipse 80% 60% at 0% 0%, alpha(#5b8cff, 0.18), transparent),
                    radial-gradient(ellipse 70% 60% at 100% 100%, alpha(#8a5cff, 0.16), transparent);
  box-shadow: inset 0 1px alpha(white, 0.45), inset 0 -1px alpha(black, 0.12), inset 1px 0 alpha(white, 0.10),
              0 0 0 1px alpha(currentColor, 0.10), 0 28px 60px -20px alpha(black, 0.55);
}
popover.ks-wheel > arrow { background: none; border: none; }
.ks-wheel-head { font-weight: 800; font-size: 0.85em; letter-spacing: .08em; opacity: .65; margin: 2px 6px 6px; }
"""
_css = [False]


def _ensure_css():
    if _css[0]:
        return
    _css[0] = True
    try:
        import theme
        theme.add_css(CSS, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 7)
    except Exception:  # noqa: BLE001
        p = Gtk.CssProvider()
        p.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 7)


def _accent(widget):
    try:
        import theme
        t = theme._t(theme._SHOWN[0] or theme.current_theme())
        a, b = t.get("a", "#5b8cff"), t.get("b", "#8a5cff")
    except Exception:  # noqa: BLE001
        a, b = "#5b8cff", "#8a5cff"
    h = lambda c: tuple(int(c.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4))  # noqa: E731
    return h(a), h(b)


class Wheel(Gtk.DrawingArea):
    def __init__(self, items, selected, on_pick):
        super().__init__(focusable=True, can_focus=True)
        self.items, self.on_pick = items, on_pick
        self.pos = float(max(0, selected))
        self.target = self.pos
        self._tick = 0
        self._snap_t = 0
        lay = self.create_pango_layout("")
        w = 0
        for t in items:
            lay.set_text(t, -1)
            w = max(w, lay.get_pixel_size()[0])
        self.set_content_width(int(min(520, max(240, w + 90))))
        self.set_content_height(int(2 * ROW / math.sin((math.pi / 2) / (VISIBLE + 0.6)) * 0.95 + 8))
        self.set_draw_func(self._draw)
        sc = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL | Gtk.EventControllerScrollFlags.KINETIC)
        sc.connect("scroll", self._on_scroll)
        sc.connect("decelerate", lambda *_: self._snap_later())
        self.add_controller(sc)
        dr = Gtk.GestureDrag()
        dr.connect("drag-begin", self._drag_begin)
        dr.connect("drag-update", self._drag_update)
        dr.connect("drag-end", self._drag_end)
        self.add_controller(dr)
        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._on_key)
        self.add_controller(key)
        self._drag_from = None
        self._moved = 0

    # --- bevegelse ---------------------------------------------------------------------------
    def _clamp(self, v):
        return max(-0.35, min(len(self.items) - 0.65, v))

    def _animate_to(self, target):
        self.target = max(0, min(len(self.items) - 1, round(target)))
        if not self._tick:
            self._tick = self.add_tick_callback(self._step)

    def _step(self, _w, _clock):
        d = self.target - self.pos
        if abs(d) < 0.004:
            self.pos = self.target
            self.queue_draw()
            self._tick = 0
            return GLib.SOURCE_REMOVE
        self.pos += d * 0.22                         # myk «fjær» mot nærmeste valg
        self.queue_draw()
        return GLib.SOURCE_CONTINUE

    def _snap_later(self):
        self._snap_t = time.monotonic()

        def snap():
            if time.monotonic() - self._snap_t >= 0.11 and self._drag_from is None:
                self._animate_to(self.pos)
            return False
        GLib.timeout_add(120, snap)

    def _on_scroll(self, c, _dx, dy):
        # Musehjul: ett hakk = ett valg (høyoppløselige hjul summeres til et helt hakk).
        # Styreplate: myk rulling som før, og snapper til nærmeste valg når fingrene slipper.
        if c.get_unit() == Gdk.ScrollUnit.WHEEL:
            self._acc = getattr(self, "_acc", 0.0) + dy
            steps = int(self._acc) if abs(self._acc) >= 1 else 0
            if steps:
                self._acc -= steps
                base = self.target if self._tick else round(self.pos)
                self._animate_to(base + (1 if steps > 0 else -1) * min(abs(steps), 3))
            return True
        self.pos = self._clamp(self.pos + dy * (0.45 if abs(dy) < 3 else 1.0))
        self.target = self.pos
        self.queue_draw()
        self._snap_later()
        return True

    def _drag_begin(self, _g, _x, y):
        self._drag_from = self.pos
        self._moved = 0
        self._y0 = y

    def _drag_update(self, _g, _dx, dy):
        self._moved = max(self._moved, abs(dy))
        self.pos = self._clamp(self._drag_from - dy / (ROW * 0.92))
        self.target = self.pos
        self.queue_draw()

    def _drag_end(self, _g, _dx, dy):
        self._drag_from = None
        if self._moved < 6:                          # et trykk: velg raden som ble trykket på
            h = self.get_height()
            off = (self._y0 - h / 2) / (ROW * 0.92)
            i = round(self.pos + off)
            if 0 <= i < len(self.items):
                if i == round(self.pos):
                    self.on_pick(i)
                else:
                    self._animate_to(i)
                    GLib.timeout_add(260, lambda: (self.on_pick(i), False)[1])
            return
        self._animate_to(self.pos)

    def _on_key(self, _c, keyval, _code, _state):
        if keyval in (Gdk.KEY_Down, Gdk.KEY_KP_Down):
            self._animate_to(self.target + 1)
        elif keyval in (Gdk.KEY_Up, Gdk.KEY_KP_Up):
            self._animate_to(self.target - 1)
        elif keyval in (Gdk.KEY_Page_Down,):
            self._animate_to(self.target + 5)
        elif keyval in (Gdk.KEY_Page_Up,):
            self._animate_to(self.target - 5)
        elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            self.on_pick(int(round(self.target)))
        else:
            return False
        return True

    # --- tegning ---------------------------------------------------------------------------------
    def _draw(self, _a, cr, w, h):
        fg = self.get_color()
        (ar, ag, ab), (br, bg, bb) = _accent(self)
        cy = h / 2
        step = (math.pi / 2) / (VISIBLE + 0.6)
        R = ROW / math.sin(step) * 0.95               # radius på sylinderen: nabovalgene står nesten en rad unna
        # glassbåndet for det valgte
        bh = ROW * 0.98
        x0, y0, bw = 6, cy - bh / 2, w - 12
        rad = 14
        cr.new_sub_path()
        cr.arc(x0 + bw - rad, y0 + rad, rad, -math.pi / 2, 0)
        cr.arc(x0 + bw - rad, y0 + bh - rad, rad, 0, math.pi / 2)
        cr.arc(x0 + rad, y0 + bh - rad, rad, math.pi / 2, math.pi)
        cr.arc(x0 + rad, y0 + rad, rad, math.pi, 3 * math.pi / 2)
        cr.close_path()
        import cairo
        g = cairo.LinearGradient(x0, y0, x0 + bw, y0 + bh)
        g.add_color_stop_rgba(0, ar, ag, ab, 0.26)
        g.add_color_stop_rgba(1, br, bg, bb, 0.22)
        cr.set_source(g)
        cr.fill_preserve()
        g2 = cairo.LinearGradient(0, y0, 0, y0 + bh)
        g2.add_color_stop_rgba(0, 1, 1, 1, 0.22)
        g2.add_color_stop_rgba(0.5, 1, 1, 1, 0.02)
        g2.add_color_stop_rgba(1, 1, 1, 1, 0.08)
        cr.set_source(g2)
        cr.fill_preserve()
        cr.set_line_width(1.2)
        g3 = cairo.LinearGradient(x0, 0, x0 + bw, 0)
        g3.add_color_stop_rgba(0, ar, ag, ab, 0.85)
        g3.add_color_stop_rgba(1, br, bg, bb, 0.85)
        cr.set_source(g3)
        cr.stroke()
        # elementene på sylinderen
        lay = self.create_pango_layout("")
        lay.set_ellipsize(Pango.EllipsizeMode.END)
        lay.set_width(int((w - 44) * Pango.SCALE))
        first, last = int(math.floor(self.pos - VISIBLE - 1)), int(math.ceil(self.pos + VISIBLE + 1))
        for i in range(max(0, first), min(len(self.items), last + 1)):
            d = i - self.pos
            ang = d * (math.pi / 2) / (VISIBLE + 0.6)
            if abs(ang) >= math.pi / 2:
                continue
            c = math.cos(ang)
            y = cy + R * math.sin(ang)
            near = max(0.0, 1 - abs(d) * 1.6)        # 1 i midten, 0 et stykke unna
            lay.set_text(self.items[i], -1)
            fd = Pango.FontDescription.from_string("Sans")
            fd.set_weight(Pango.Weight.BOLD if near > 0.5 else Pango.Weight.MEDIUM)
            fd.set_absolute_size(int((15 + 3 * near) * Pango.SCALE))
            lay.set_font_description(fd)
            lay.set_alignment(Pango.Alignment.CENTER)
            tw, th = lay.get_pixel_size()
            cr.save()
            cr.translate(22, y)
            cr.scale(1, max(0.05, c))                 # sammenpresset mot kantene – som en sylinder
            cr.translate(0, -th / 2)
            alpha = (0.18 + 0.82 * c ** 3)
            if near > 0.5:
                cr.set_source_rgba(fg.red, fg.green, fg.blue, 1)
            else:
                cr.set_source_rgba(fg.red, fg.green, fg.blue, alpha * 0.85)
            cr.move_to(0, 0)
            PangoCairo.show_layout(cr, lay)
            cr.restore()


def _strings(dd):
    m = dd.get_model()
    if m is None:
        return None
    n = m.get_n_items()
    if n == 0 or n > MAX_ITEMS:
        return None
    out = []
    for i in range(n):
        it = m.get_item(i)
        s = None
        if isinstance(it, Gtk.StringObject):
            s = it.get_string()
        else:
            ex = dd.get_expression() if hasattr(dd, "get_expression") else None
            if ex is not None:
                try:
                    s = ex.evaluate(it)
                except Exception:  # noqa: BLE001
                    s = None
            if s is None:
                s = getattr(it, "props", None) and getattr(it.props, "string", None)
        if s is None:
            return None
        out.append(str(s))
    return out


def open_wheel(widget, anchor=None):
    """Vis rullehjulet for en Gtk.DropDown eller Adw.ComboRow."""
    items = _strings(widget)
    if not items:
        return False
    _ensure_css()
    pop = Gtk.Popover(has_arrow=False, autohide=True)
    pop.add_css_class("ks-wheel")
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    title = widget.get_title() if isinstance(widget, Adw.ComboRow) else None
    if title:
        lab = Gtk.Label(label=title.upper(), xalign=0)
        lab.add_css_class("ks-wheel-head")
        box.append(lab)

    def pick(i):
        if 0 <= i < len(items) and widget.get_selected() != i:
            widget.set_selected(i)
        pop.popdown()
    whl = Wheel(items, widget.get_selected(), pick)
    box.append(whl)
    pop.set_child(box)
    pop.set_parent(anchor or widget)
    pop.connect("closed", lambda p: GLib.idle_add(p.unparent))
    pop.popup()
    whl.grab_focus()
    return True


def _wire(w):
    if getattr(w, "_ks_wheel", False):
        return
    w._ks_wheel = True
    g = Gtk.GestureClick(button=1)
    g.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)

    def pressed(gest, _n, _x, _y):
        if not w.get_sensitive() or _strings(w) is None:
            return
        gest.set_state(Gtk.EventSequenceState.CLAIMED)
        open_wheel(w)
    g.connect("pressed", pressed)
    w.add_controller(g)


def scan(root):
    """Finn alle valgmenyer under root og gi dem rullehjul (trygt å kalle ofte)."""
    stack = [root]
    while stack:
        w = stack.pop()
        if isinstance(w, (Gtk.DropDown, Adw.ComboRow)):
            _wire(w)
        c = w.get_first_child()
        while c is not None:
            stack.append(c)
            c = c.get_next_sibling()


def install(window):
    """Skann vinduet jevnlig mens det er i bruk – nye sider og dialoger får rullehjul av seg selv."""
    def tick():
        if window.get_mapped() and window.is_active():
            try:
                scan(window)
            except Exception:  # noqa: BLE001
                pass
        return True
    GLib.timeout_add(1200, tick)
    tick()
