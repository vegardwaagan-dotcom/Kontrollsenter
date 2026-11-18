"""Effekter i hele programmet: levende bakgrunn, kort som glir inn, myke overganger og trykk-effekter.

Nivå (Innstillinger → Utseende):
  full  – alt, også bakgrunnen som sakte driver (står stille når vinduet ikke er i fokus, f.eks. mens du spiller)
  rolig – animasjoner, men stillestående bakgrunn
  av    – ingen effekter
"""
import json
import os

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

LOOK = os.path.expanduser("~/.config/systemmonitor/utseende.json")
LEVELS = [("full", "Full – levende bakgrunn og animasjoner"), ("rolig", "Rolig – animasjoner, rolig bakgrunn"),
          ("av", "Av – ingen effekter")]

FX_CSS = """
@keyframes ks-rise { from { opacity: 0; transform: translateY(18px) scale(0.985); } to { opacity: 1; transform: none; } }
@keyframes ks-fade { from { opacity: 0; } to { opacity: 1; } }
@keyframes ks-drift {
  0%   { background-position: 0% 0%, 100% 0%, 50% 100%; }
  50%  { background-position: 35% 25%, 65% 35%, 40% 75%; }
  100% { background-position: 10% 45%, 90% 15%, 65% 90%; }
}
@keyframes ks-breathe { from { opacity: .82; } to { opacity: 1; } }

/* levende bakgrunn – står stille når vinduet ikke er i fokus */
window.ks-fx-bg .ks-content { background-size: 170% 170%, 170% 170%, 170% 170%;
  animation: ks-drift 30s ease-in-out infinite alternate; }
window.ks-fx-bg:backdrop .ks-content { animation-play-state: paused; }
window.ks-fx-bg .ks-brand-logo { animation: ks-breathe 3.2s ease-in-out infinite alternate; }
window.ks-fx-bg:backdrop .ks-brand-logo { animation-play-state: paused; }

/* kortene glir inn når du bytter side */
window.ks-fx .ks-enter > * { animation: ks-rise 480ms cubic-bezier(.2, .8, .2, 1) both; }
window.ks-fx .ks-enter > :nth-child(2) { animation-delay: 45ms; }
window.ks-fx .ks-enter > :nth-child(3) { animation-delay: 90ms; }
window.ks-fx .ks-enter > :nth-child(4) { animation-delay: 135ms; }
window.ks-fx .ks-enter > :nth-child(5) { animation-delay: 180ms; }
window.ks-fx .ks-enter > :nth-child(6) { animation-delay: 220ms; }
window.ks-fx .ks-enter > :nth-child(n+7) { animation-delay: 260ms; }

/* knapper: lett trykk */
window.ks-fx button { transition: transform 130ms ease, box-shadow 220ms ease, background-color 220ms ease; }
window.ks-fx button:active { transform: scale(0.955); }
window.ks-fx button.pill:hover, window.ks-fx button.suggested-action:hover { transform: translateY(-1px); }

/* fliser og kort løfter seg */
window.ks-fx .ks-dash-item > .card, window.ks-fx .ks-dash-item > .tile, window.ks-fx .card.ks-scene {
  transition: transform 240ms cubic-bezier(.2, .8, .2, 1), box-shadow 260ms ease; }
window.ks-fx .ks-dash-item:hover > .card, window.ks-fx .ks-dash-item:hover > .tile,
window.ks-fx .card.ks-scene:hover { transform: translateY(-3px); }

/* sidemenyen glir litt når du peker */
window.ks-fx .navigation-sidebar > row { transition: background-color 220ms ease, transform 180ms ease; }
window.ks-fx .navigation-sidebar > row:hover { transform: translateX(3px); }

/* brytere og glidere med sprett */
window.ks-fx switch slider { transition: all 260ms cubic-bezier(.3, 1.5, .6, 1); }
window.ks-fx progressbar progress { transition: all 320ms ease; }
window.ks-fx popover.menu contents, window.ks-fx popover contents { animation: ks-fade 160ms ease-out; }
"""

_DONE = []


def level():
    try:
        v = json.load(open(LOOK)).get("effects", "full")
    except (OSError, ValueError):
        v = "full"
    return v if v in ("full", "rolig", "av") else "full"


def set_level(v, window=None):
    try:
        d = json.load(open(LOOK))
    except (OSError, ValueError):
        d = {}
    d["effects"] = v
    os.makedirs(os.path.dirname(LOOK), exist_ok=True)
    json.dump(d, open(LOOK, "w"))
    for w in ([window] if window else Gtk.Window.list_toplevels()):
        if w is not None:
            apply(w)


def apply(window):
    """Sett effekt-klassene på et vindu (og last stilarket første gang)."""
    if not _DONE:
        _DONE.append(1)
        import theme
        theme.add_css(FX_CSS, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 3)
    lv = level()
    for c, on in (("ks-fx", lv in ("full", "rolig")), ("ks-fx-bg", lv == "full")):
        (window.add_css_class if on else window.remove_css_class)(c)


def _content_box(w):
    """Første boks med flere barn under siden (der kortene ligger)."""
    queue = [w]
    for _ in range(60):
        if not queue:
            return None
        x = queue.pop(0)
        if isinstance(x, Gtk.Box) and x.get_orientation() == Gtk.Orientation.VERTICAL:
            n, c = 0, x.get_first_child()
            while c is not None and n < 3:
                n += 1
                c = c.get_next_sibling()
            if n >= 3:
                return x
        c = x.get_first_child()
        while c is not None:
            queue.append(c)
            c = c.get_next_sibling()
    return None


def page_enter(page):
    """La kortene på siden gli inn (kalles når du bytter side eller fane)."""
    if level() == "av" or page is None:
        return
    box = _content_box(page)
    if box is None:
        return
    box.remove_css_class("ks-enter")

    def on():
        box.add_css_class("ks-enter")
        GLib.timeout_add(900, lambda: (box.remove_css_class("ks-enter"), False)[1])
        return False
    GLib.idle_add(on)
