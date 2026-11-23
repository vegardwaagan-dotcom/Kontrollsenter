"""Flisene og kortene i Oversikt: dra for å flytte, velg størrelse, trykk for detaljer.

Et rutenett som pakker flisene i rekkefølgen du har valgt. Hver flis kan være 1, 2 eller alle kolonner bred.
Antall kolonner følger bredden på vinduet. Rekkefølge og størrelser lagres i ~/.config/systemmonitor/oversikt.json.
Effekter: flisen du drar blir halvgjennomsiktig, målet lyser lilla, og når du slipper «spretter» flisen på plass
med en lilla glød mens de andre glir inn på sine nye plasser.
"""
import json
import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gdk, GLib, GObject, Gtk  # noqa: E402

import i18n  # noqa: E402

CFG = os.path.expanduser("~/.config/systemmonitor/oversikt.json")
SIZE_NAMES = {1: "Liten", 2: "Bred", 9: "Hele bredden"}

CSS = """
.ks-dash-item { transition: opacity 180ms ease; }
.ks-dash-item.ks-drag-src { opacity: .3; }
.ks-dash-item.ks-drop-target > .card, .ks-dash-item.ks-drop-target > .tile {
  box-shadow: 0 0 0 3px alpha(#8a5cff,.85), 0 10px 30px alpha(#8a5cff,.35); }
.ks-dash-item.ks-dropped > * { animation: ks-pop 520ms cubic-bezier(.2,1.4,.4,1); }
.ks-dash-item.ks-moved > * { animation: ks-slide 380ms cubic-bezier(.2,.8,.2,1); }
@keyframes ks-pop {
  0%   { transform: scale(.9);  box-shadow: 0 0 0 4px alpha(#8a5cff,.9), 0 0 40px alpha(#5b8cff,.6); }
  55%  { transform: scale(1.04); box-shadow: 0 0 0 3px alpha(#8a5cff,.7), 0 0 34px alpha(#5b8cff,.45); }
  100% { transform: scale(1);   box-shadow: 0 0 0 0 alpha(#8a5cff,0); }
}
@keyframes ks-slide {
  0%   { opacity: .35; transform: scale(.96); }
  100% { opacity: 1;   transform: scale(1); }
}
.ks-dash-edit > .card, .ks-dash-edit > .tile { box-shadow: 0 0 0 2px alpha(#8a5cff,.55); }
.ks-dash-tools { margin: 8px; padding: 2px; border-radius: 999px; background: alpha(@window_bg_color,.92);
  box-shadow: 0 2px 10px alpha(black,.25); }
.ks-dash-tools button { min-height: 26px; min-width: 26px; padding: 0 9px; font-size: 12px; font-weight: 700; }
"""


def _load():
    try:
        with open(CFG) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_group(name, data):
    d = _load()
    d[name] = data
    try:
        os.makedirs(os.path.dirname(CFG), exist_ok=True)
        with open(CFG, "w") as f:
            json.dump(d, f, indent=1)
    except OSError:
        pass


_css_done = [False]


def _css():
    if _css_done[0]:
        return
    _css_done[0] = True
    import theme
    theme.add_css(CSS, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 2)


class _Item(Gtk.Overlay):
    def __init__(self, dash, key, widget, size, sizes, on_click):
        super().__init__(hexpand=True)
        self.dash, self.key, self.size, self.sizes = dash, key, size, sizes
        self.add_css_class("ks-dash-item")
        self.set_overflow(Gtk.Overflow.VISIBLE)          # gløden rundt flisen skal ikke klippes
        widget.set_hexpand(True)
        widget.set_valign(Gtk.Align.FILL)
        self.set_child(widget)
        self.widget = widget
        # verktøylinje (vises når du tilpasser): størrelser
        self.tools = Gtk.Box(halign=Gtk.Align.END, valign=Gtk.Align.START, visible=False)
        self.tools.add_css_class("ks-dash-tools")
        self.tools.add_css_class("linked")
        self.size_btns = {}
        first = None
        for s in sizes:
            b = Gtk.ToggleButton(label={1: "S", 2: "M", 9: "L"}[s], active=(s == size))
            b.set_tooltip_text(i18n.tr(SIZE_NAMES[s]))
            b.add_css_class("flat")
            if first:
                b.set_group(first)
            first = first or b
            b.connect("toggled", lambda w, s=s: w.get_active() and self.dash.set_size(self, s))
            self.tools.append(b)
            self.size_btns[s] = b
        hb = Gtk.Button(label="✕")
        hb.set_tooltip_text(i18n.tr("Skjul flisen"))
        hb.add_css_class("flat")
        hb.connect("clicked", lambda *_: self.dash.hide(self.key))
        self.tools.append(hb)
        self.add_overlay(self.tools)
        # dra for å flytte
        src = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
        src.connect("prepare", self._prepare)
        src.connect("drag-begin", self._begin)
        src.connect("drag-end", self._end)
        self.add_controller(src)
        tgt = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
        tgt.connect("enter", lambda *_: (self.add_css_class("ks-drop-target"), Gdk.DragAction.MOVE)[1])
        tgt.connect("leave", lambda *_: self.remove_css_class("ks-drop-target"))
        tgt.connect("drop", self._drop)
        self.add_controller(tgt)
        # trykk = detaljer, høyreklikk = størrelse
        if on_click:
            click = Gtk.GestureClick(button=1)
            click.connect("released", lambda g, n, x, y: self._clicked(g, on_click, x, y))
            self.add_controller(click)
            self.set_cursor_from_name("pointer")
            self.set_tooltip_text(i18n.tr("Trykk for detaljer · dra for å flytte · høyreklikk for størrelse"))
        rc = Gtk.GestureClick(button=3)
        rc.connect("pressed", lambda g, n, x, y: self._menu(x, y))
        self.add_controller(rc)

    def _clicked(self, g, fn, x, y):
        if self.dash.editing or self.dash.dragging:
            return
        w = self.pick(x, y, Gtk.PickFlags.DEFAULT)
        while w is not None and w is not self:          # knapper og brytere inne i kortet får klikket selv
            if isinstance(w, (Gtk.Button, Gtk.Switch, Gtk.DropDown, Gtk.Scale, Gtk.SpinButton, Gtk.Entry)):
                return
            w = w.get_parent()
        fn()

    def _menu(self, x, y):
        pop = Gtk.Popover(has_arrow=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for s in self.sizes:
            b = Gtk.Button(label=("✓  " if s == self.size else "     ") + i18n.tr(SIZE_NAMES[s]))
            b.add_css_class("flat")
            b.connect("clicked", lambda _b, s=s: (pop.popdown(), self.dash.set_size(self, s)))
            box.append(b)
        box.append(Gtk.Separator())
        hb = Gtk.Button(label="     " + i18n.tr("Skjul flisen"))
        hb.add_css_class("flat")
        hb.connect("clicked", lambda *_: (pop.popdown(), self.dash.hide(self.key)))
        box.append(hb)
        b = Gtk.Button(label=i18n.tr("Skjul S / M / L" if self.dash.editing else "Vis S / M / L i hjørnet"))
        b.add_css_class("flat")
        b.connect("clicked", lambda *_: (pop.popdown(), self.dash.on_edit_request and self.dash.on_edit_request()))
        box.append(b)
        pop.set_child(box)
        pop.set_parent(self)
        r = Gdk.Rectangle()
        r.x, r.y, r.width, r.height = int(x), int(y), 1, 1
        pop.set_pointing_to(r)
        pop.connect("closed", lambda p: GLib.idle_add(p.unparent))
        pop.popup()

    def _prepare(self, src, x, y):
        w = self.pick(x, y, Gtk.PickFlags.DEFAULT)
        while w is not None and w is not self:          # ikke dra kortet når du drar i en glidebryter e.l.
            if isinstance(w, (Gtk.Scale, Gtk.Button, Gtk.Switch, Gtk.Entry, Gtk.SpinButton, Gtk.DropDown,
                              Gtk.CheckButton, Gtk.TextView)):
                return None
            w = w.get_parent()
        self._hot = (x, y)
        return Gdk.ContentProvider.new_for_value(self.dash.name + ":" + self.key)

    def _begin(self, src, drag):
        self.dash.dragging = True
        try:
            src.set_icon(Gtk.WidgetPaintable(widget=self.widget), int(self._hot[0]), int(self._hot[1]))
        except Exception:  # noqa: BLE001
            pass
        self.add_css_class("ks-drag-src")

    def _end(self, *_):
        self.remove_css_class("ks-drag-src")
        GLib.timeout_add(150, lambda: setattr(self.dash, "dragging", False) or False)

    def _drop(self, tgt, value, x, y):
        self.remove_css_class("ks-drop-target")
        name, _, key = str(value).partition(":")
        if name != self.dash.name or key == self.key:
            return False
        after = x > self.get_width() / 2
        self.dash.move(key, self.key, after)
        return True


class Dash(Gtk.Widget):
    """Rutenett med flyttbare fliser. add(key, widget, size) – deretter finish()."""

    def __init__(self, name, max_cols=4, min_col=220, sizes=(1, 2, 9)):
        super().__init__()
        _css()
        self.name, self.max_cols, self.min_col, self.sizes = name, max_cols, min_col, sizes
        self.grid = Gtk.Grid(column_spacing=12, row_spacing=12, column_homogeneous=True)
        self.grid.set_parent(self)
        self.items = {}
        self.order = []
        self.cols = 0
        self.editing = False
        self.dragging = False
        self.on_edit_request = None
        self._defaults = []
        self._def_hidden = set()
        self.preset = _load().get("_preset:" + name, "standard")
        self.hidden = set(_load().get(self.ckey(), {}).get("hidden") or [])
        self.on_change = None
        self.set_hexpand(True)

    def ckey(self, preset=None):
        p = preset or self.preset
        return self.name if p == "standard" else f"{self.name}@{p}"

    def add(self, key, widget, size=1, on_click=None, hidden=False):
        saved = _load().get(self.ckey(), {})
        if hidden:
            self._def_hidden.add(key)
            if "hidden" not in saved:
                self.hidden.add(key)
        sz = int((saved.get("size") or {}).get(key, size))
        if sz not in self.sizes:
            sz = size
        it = _Item(self, key, widget, sz, self.sizes, on_click)
        if self.editing:
            it.tools.set_visible(True)
            it.add_css_class("ks-dash-edit")
        widget.connect("notify::visible", lambda *_: GLib.idle_add(self._layout))
        self.items[key] = it
        self._defaults.append((key, size))
        return it

    def finish(self):
        saved = _load().get(self.ckey(), {}).get("order") or []
        keys = list(dict.fromkeys(k for k, _s in self._defaults))
        self.order = [k for k in saved if k in self.items] + [k for k in keys if k not in saved]
        self._layout()

    # --- plassering ----------------------------------------------------------
    def do_dispose(self):
        if self.grid is not None and self.grid.get_parent() is self:
            self.grid.unparent()
        Gtk.Widget.do_dispose(self)

    def do_measure(self, orientation, for_size):
        gmin, gnat, _a, _b = self.grid.measure(Gtk.Orientation.HORIZONTAL, -1)
        if orientation == Gtk.Orientation.HORIZONTAL:
            return min(gmin, self.min_col), gnat, -1, -1     # vinduet kan bli smalere – da blir det færre kolonner
        mn, nat, _a, _b = self.grid.measure(orientation, max(for_size, gmin) if for_size >= 0 else -1)
        return mn, nat, -1, -1

    def do_size_allocate(self, w, h, b):
        gmin = self.grid.measure(Gtk.Orientation.HORIZONTAL, -1)[0]
        self.grid.allocate(max(w, gmin), h, b, None)
        cols = self._fit(w)
        if cols != self.cols:
            self.cols = cols
            GLib.idle_add(self._layout)

    def _layout(self, animate=None, dropped=None):
        cols = self.cols or self.max_cols
        old = {k: (self.grid.query_child(it) if it.get_parent() is self.grid else None) for k, it in self.items.items()}
        for it in self.items.values():
            if it.get_parent() is self.grid:
                self.grid.remove(it)
        r = c = 0
        for k in self.order:
            it = self.items[k]
            if not it.widget.get_visible() or k in self.hidden:
                continue
            span = min(cols, it.size if it.size != 9 else cols)
            if c + span > cols:
                r, c = r + 1, 0
            self.grid.attach(it, c, r, span, 1)
            pos = (c, r, span, 1)
            if animate and old.get(k) and tuple(old[k]) != pos and k != dropped:
                self._flash(it, "ks-moved", 420)
            c += span
            if c >= cols:
                r, c = r + 1, 0
        if dropped:
            self._flash(self.items[dropped], "ks-dropped", 560)
        return False

    def _fit(self, w):
        """Flest mulig kolonner (opptil max_cols) der alle flisene får plass med sin minste bredde."""
        mins = []
        for it in self.items.values():
            if it.widget.get_visible():
                mins.append((it.measure(Gtk.Orientation.HORIZONTAL, -1)[0], it.size))
        gap = self.grid.get_column_spacing()
        for cols in range(min(self.max_cols, max(1, w // self.min_col)), 0, -1):
            colmin = 0
            for mn, size in mins:
                span = cols if size == 9 else min(size, cols)
                colmin = max(colmin, (mn - (span - 1) * gap) / span)
            if cols * colmin + (cols - 1) * gap <= w:
                return cols
        return 1

    @staticmethod
    def _flash(w, cls, ms):
        w.remove_css_class(cls)
        w.add_css_class(cls)
        GLib.timeout_add(ms, lambda: w.remove_css_class(cls) or False)

    def _save(self):
        _save_group(self.ckey(), {"order": self.order, "size": {k: it.size for k, it in self.items.items()},
                                  "hidden": sorted(self.hidden)})
        if self.on_change:
            self.on_change()

    def hide(self, key):
        self.hidden.add(key)
        self._save()
        self._layout(animate=True)

    def unhide(self, key):
        self.hidden.discard(key)
        self._save()
        self._layout(animate=True, dropped=key)

    def set_preset(self, preset):
        """Bytt oppsett (Standard / Spill / Jobb / Natt). Et nytt oppsett starter som en kopi av det du har nå."""
        if preset == self.preset:
            return
        self._save()
        d = _load().get(self.ckey(preset))
        self.preset = preset
        _save_group("_preset:" + self.name, None)
        dd = _load()
        dd["_preset:" + self.name] = preset
        try:
            with open(CFG, "w") as f:
                json.dump(dd, f, indent=1)
        except OSError:
            pass
        if d:
            self.order = [k for k in d.get("order", []) if k in self.items] + \
                [k for k in self.items if k not in d.get("order", [])]
            for k, it in self.items.items():
                sz = int((d.get("size") or {}).get(k, it.size))
                it.size = sz if sz in self.sizes else it.size
                b = it.size_btns.get(it.size)
                if b and not b.get_active():
                    b.set_active(True)
            self.hidden = set(d.get("hidden") or [])
        self._save()
        self._layout(animate=True)

    def move(self, key, target, after):
        if key not in self.order or target not in self.order:
            return
        self.order.remove(key)
        i = self.order.index(target) + (1 if after else 0)
        self.order.insert(i, key)
        self._save()
        self._layout(animate=True, dropped=key)

    def set_size(self, it, size):
        if it.size == size:
            return
        it.size = size
        b = it.size_btns.get(size)
        if b and not b.get_active():
            b.set_active(True)
        self._save()
        self._layout(animate=True, dropped=it.key)

    def set_editing(self, on):
        self.editing = on
        for it in self.items.values():
            it.tools.set_visible(on)
            (it.add_css_class if on else it.remove_css_class)("ks-dash-edit")

    def reset(self):
        self.order = [k for k, _s in self._defaults]
        for k, s in self._defaults:
            self.items[k].size = s
            b = self.items[k].size_btns.get(s)
            if b:
                b.set_active(True)
        self.hidden = set(self._def_hidden)
        _save_group(self.ckey(), {})
        self._layout(animate=True)
