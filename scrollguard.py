"""Musehjulet over en glider (volum, lysstyrke …) eller et tallfelt skal rulle siden – ikke endre verdien ved et uhell.

Én kontroller på hele vinduet (fanger hjulet før glideren gjør det): står pekeren over en glider eller et tallfelt,
ruller vi siden i stedet. Gliderne justeres ved å dra, klikke eller med piltastene.
"""
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

GUARDED = (Gtk.Scale, Gtk.SpinButton)


def _guarded_under(w):
    """Glideren/tallfeltet pekeren står over (eller None)."""
    while w is not None:
        if isinstance(w, GUARDED):
            return w
        if isinstance(w, Gtk.ScrolledWindow):          # innenfor en rulleliste: ikke let lenger ut
            return None
        w = w.get_parent()
    return None


def _scroller(w):
    while w is not None:
        if isinstance(w, Gtk.ScrolledWindow):
            return w
        w = w.get_parent()
    return None


def handle(win, x, y, dx, dy):
    """→ True hvis vi tok hjulet (rullet siden i stedet for å endre glideren)."""
    target = win.pick(x, y, Gtk.PickFlags.DEFAULT)
    g = _guarded_under(target)
    if g is None:
        return False
    sw = _scroller(g)
    if sw is None:
        return True                                      # ingen side å rulle – bare ikke endre glideren
    for adj, d in ((sw.get_vadjustment(), dy), (sw.get_hadjustment(), dx)):
        if adj is None or not d:
            continue
        step = max(30.0, adj.get_page_size() ** (2 / 3))
        lo, hi = adj.get_lower(), adj.get_upper() - adj.get_page_size()
        adj.set_value(max(lo, min(hi, adj.get_value() + d * step)))
    return True


def install(win):
    pos = {"x": 0.0, "y": 0.0}
    mo = Gtk.EventControllerMotion()
    mo.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    mo.connect("motion", lambda _c, x, y: pos.update(x=x, y=y))
    win.add_controller(mo)
    sc = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.BOTH_AXES)
    sc.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    sc.connect("scroll", lambda _c, dx, dy: handle(win, pos["x"], pos["y"], dx, dy))
    win.add_controller(sc)
