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

TRANSITIONS = [("glid", "Glid – kortene glir inn"), ("fade", "Fade – myk inntoning"), ("av", "Av – ingen overganger")]

FX_CSS = """
/* Eldre PC: ingen animasjoner, overganger, skygger eller glød – det tyngste å tegne */
window.ks-lowend, window.ks-lowend * { transition: none; animation: none; box-shadow: none; text-shadow: none;
  -gtk-icon-shadow: none; filter: none; }
window.ks-lowend .tile-spark { opacity: 0; min-height: 0; }
/* minimal prosessbruk: ingen store skygger/glød (tunge å tegne) */
window.ks-eco .ks-dash-item:hover > .card, window.ks-eco .ks-dash-item:hover > .tile, window.ks-eco .card.ks-scene:hover,
window.ks-eco .navigation-sidebar > row:hover, window.ks-eco button:hover { box-shadow: none; }
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
  animation: ks-drift 30s steps(45) infinite alternate; }   /* i små trinn: ~1,5 tegninger/s i stedet for full fps */
window.ks-fx-bg:backdrop .ks-content { animation-play-state: paused; }
window.ks-fx-bg .ks-brand-logo { animation: ks-breathe 3.2s steps(6) infinite alternate; }
window.ks-fx-bg:backdrop .ks-brand-logo { animation-play-state: paused; }

/* overganger når du bytter side: glid (kortene glir opp etter tur) eller fade (myk inntoning) */
window .ks-enter > * { animation: ks-rise 380ms cubic-bezier(.2, .8, .2, 1) both; }
window .ks-enter > :nth-child(2) { animation-delay: 35ms; }
window .ks-enter > :nth-child(3) { animation-delay: 70ms; }
window .ks-enter > :nth-child(4) { animation-delay: 105ms; }
window .ks-enter > :nth-child(5) { animation-delay: 140ms; }
window .ks-enter > :nth-child(n+6) { animation-delay: 170ms; }
window .ks-enter-fade > * { animation: ks-fade 260ms ease-out both; }
window.ks-lowend .ks-enter > *, window.ks-lowend .ks-enter-fade > * { animation: none; }

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
        import perf
        if perf.light():
            return "av"
    except Exception:  # noqa: BLE001
        pass
    dflt = "rolig" if os.name == "nt" else "full"
    try:
        v = json.load(open(LOOK)).get("effects", dflt)
    except (OSError, ValueError):
        v = dflt
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


def transition():
    """«glid», «fade» eller «av» (Innstillinger › Utseende › Overganger)."""
    try:
        v = json.load(open(LOOK)).get("transition", "glid")
    except (OSError, ValueError):
        v = "glid"
    return v if v in ("glid", "fade", "av") else "glid"


def set_transition(v, window=None):
    try:
        d = json.load(open(LOOK))
    except (OSError, ValueError):
        d = {}
    d["transition"] = v
    os.makedirs(os.path.dirname(LOOK), exist_ok=True)
    with open(LOOK + ".tmp", "w") as f:
        json.dump(d, f)
    os.replace(LOOK + ".tmp", LOOK)
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
    try:
        import perf
        (window.add_css_class if perf.light() else window.remove_css_class)("ks-eco")
        (window.add_css_class if perf.lowend() else window.remove_css_class)("ks-lowend")
    except Exception:  # noqa: BLE001
        pass
    for c, on in (("ks-fx", lv in ("full", "rolig")), ("ks-fx-bg", lv == "full")):
        (window.add_css_class if on else window.remove_css_class)(c)
    st = getattr(window, "stack", None)                  # sidebytte: kort krysstoning (eller ingenting)
    if st is not None:
        tr = transition()
        try:
            if hasattr(st, "set_enable_transitions"):         # Adw.ViewStack: innebygd krysstoning
                st.set_enable_transitions(tr != "av")
            else:
                st.set_transition_type(Gtk.StackTransitionType.NONE if tr == "av" else
                                       Gtk.StackTransitionType.CROSSFADE)
            st.set_transition_duration(140)
        except (AttributeError, TypeError):
            pass


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
    """La kortene på siden gli eller tone inn (kalles når du bytter side eller fane)."""
    tr = transition()
    if tr == "av" or page is None:
        return
    box = _content_box(page)
    if box is None:
        return
    cls = "ks-enter" if tr == "glid" else "ks-enter-fade"
    box.remove_css_class("ks-enter")
    box.remove_css_class("ks-enter-fade")

    def on():
        box.add_css_class(cls)
        GLib.timeout_add(700, lambda: (box.remove_css_class(cls), False)[1])
        return False
    GLib.idle_add(on)
