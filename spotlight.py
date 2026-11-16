"""Lys som følger musa på knappene – sterkest der pekeren er, som knappene i Windows 11.

Én bevegelsesmåler per vindu finner knappen under pekeren. Bare den knappen får et eget lite stilark med et
radialt lys på pekerens plass, så det er bare den som tegnes på nytt (billig – ingen omtegning av hele vinduet).
"""
import warnings

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Graphene, Gtk  # noqa: E402

PRIORITY = Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 3          # over glass- og glød-stilen
_LIGHT = "radial-gradient(circle {r}px at {x}px {y}px, alpha(white, {a}), alpha(#8a9bff, {b}) 45%, transparent 75%)"


def _target(w):
    """Knappen (eller raden i sidemenyen) under pekeren."""
    while w is not None:
        if isinstance(w, (Gtk.Button, Gtk.ListBoxRow)) and w.get_sensitive():
            return w
        if isinstance(w, Gtk.Window):
            return None
        w = w.get_parent()
    return None


def _base(w):
    """Bakgrunnen knappen har fra før (lyset legges oppå)."""
    if isinstance(w, Gtk.ListBoxRow):
        return "none" if not w.is_selected() else "linear-gradient(90deg, alpha(#5b8cff, 0.22), alpha(#8a5cff, 0.12))"
    if w.has_css_class("suggested-action") or (isinstance(w, Gtk.ToggleButton) and w.get_active()):
        return "linear-gradient(135deg, #5b8cff, #8a5cff)"
    if w.has_css_class("destructive-action"):
        return "none"
    if w.has_css_class("flat"):
        return "none"
    return "linear-gradient(180deg, alpha(white, 0.13), alpha(white, 0) 62%)"


class Spotlight:
    def __init__(self, window):
        self.win = window
        self.cur = None
        self.prov = Gtk.CssProvider()
        self.last = None
        mc = Gtk.EventControllerMotion()
        mc.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        mc.connect("motion", self._motion)
        mc.connect("leave", lambda *_: self._set(None))
        window.add_controller(mc)

    def _set(self, w):
        if w is self.cur:
            return
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            if self.cur is not None:
                try:
                    self.cur.get_style_context().remove_provider(self.prov)
                except Exception:  # noqa: BLE001
                    pass
            self.cur = w
            self.last = None
            if w is not None:
                w.get_style_context().add_provider(self.prov, PRIORITY)

    def _motion(self, _c, x, y):
        try:
            picked = self.win.pick(x, y, Gtk.PickFlags.DEFAULT)
        except Exception:  # noqa: BLE001
            return
        w = _target(picked)
        self._set(w)
        if w is None:
            return
        ok, pt = self.win.compute_point(w, Graphene.Point().init(x, y))
        if not ok:
            return
        lx, ly = int(pt.x), int(pt.y)
        if self.last and abs(self.last[0] - lx) < 2 and abs(self.last[1] - ly) < 2:
            return
        self.last = (lx, ly)
        big = max(w.get_width(), w.get_height())
        r = max(40, min(140, int(big * 0.9)))
        strong = w.has_css_class("suggested-action") or (isinstance(w, Gtk.ToggleButton) and w.get_active())
        light = _LIGHT.format(r=r, x=lx, y=ly, a=0.42 if strong else 0.30, b=0.30 if strong else 0.22)
        base = _base(w)
        css = (f"* {{ background-image: {light}{', ' + base if base != 'none' else ''}; "
               f"background-size: 100% 100%; background-repeat: no-repeat; }}")
        if hasattr(self.prov, "load_from_string"):
            self.prov.load_from_string(css)
        else:
            self.prov.load_from_data(css.encode(), -1)


def attach(window):
    """Slå på lyset i et vindu (gjør ingenting om det allerede er på)."""
    if getattr(window, "_ks_spot", None) is None:
        window._ks_spot = Spotlight(window)
    return window._ks_spot
