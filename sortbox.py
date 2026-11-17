"""Flytt kortene på alle sidene i PC-appen: dra et kort med musa og slipp det der du vil ha det.

scan(side, navn) finner alle loddrette bokser med minst to kort (css-klassen «card») og gjør kortene flyttbare.
Rekkefølgen lagres per side og boks i ~/.config/systemmonitor/rekkefolge.json (kortene kjennes igjen på tittelen).
Effekter som i Oversikt: målet lyser lilla, kortet «spretter» på plass med glød, de andre glir inn.
"""
import json
import os

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, GObject, Gtk  # noqa: E402


CFG = os.path.expanduser("~/.config/systemmonitor/rekkefolge.json")
INTERACTIVE = (Gtk.Scale, Gtk.Button, Gtk.Switch, Gtk.Entry, Gtk.SpinButton, Gtk.DropDown, Gtk.CheckButton,
               Gtk.TextView, Gtk.ListBox, Gtk.FlowBox, Gtk.ScrolledWindow, Gtk.ColorDialogButton)

CSS = """
.ks-sort-src { opacity: .3; }
.card.ks-sort-target, .ks-sort-target > .card { box-shadow: 0 0 0 3px alpha(#8a5cff,.85), 0 10px 30px alpha(#8a5cff,.35); }
.card.ks-sort-dropped, .ks-sort-dropped > .card { animation: ks-pop 520ms cubic-bezier(.2,1.4,.4,1); }
.card.ks-sort-moved, .ks-sort-moved > .card { animation: ks-slide 380ms cubic-bezier(.2,.8,.2,1); }
"""
_css_done = [False]


def _css():
    if _css_done[0]:
        return
    _css_done[0] = True
    import dashboard
    dashboard._css()                         # keyframes ks-pop og ks-slide
    p = Gtk.CssProvider()
    if hasattr(p, "load_from_string"):
        p.load_from_string(CSS)
    else:
        p.load_from_data(CSS.encode(), -1)
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 3)


def _load():
    try:
        with open(CFG) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(key, titles):
    d = _load()
    d[key] = titles
    try:
        os.makedirs(os.path.dirname(CFG), exist_ok=True)
        with open(CFG, "w") as f:
            json.dump(d, f, indent=1, ensure_ascii=False)
    except OSError:
        pass


def _children(w):
    c = w.get_first_child()
    while c is not None:
        yield c
        c = c.get_next_sibling()


def _title(card):
    """Første overskrift i kortet – kortets navn."""
    stack = [card]
    while stack:
        w = stack.pop(0)
        if isinstance(w, Gtk.Label) and (w.has_css_class("heading") or w.has_css_class("title-4")) and w.get_label():
            return w.get_label()
        stack.extend(_children(w))
    return None


def _is_card(w):
    """Et kort – eller en boks som bare inneholder ett kort (f.eks. Statistikk og Klipp)."""
    if w.has_css_class("card"):
        return True
    f = w.get_first_child()
    return isinstance(w, Gtk.Box) and f is not None and f.get_next_sibling() is None and f.has_css_class("card")


def _cards(box):
    if isinstance(box, Gtk.FlowBox):
        out = []
        for fc in _children(box):
            c = fc.get_child() if isinstance(fc, Gtk.FlowBoxChild) else None
            if c is not None and _is_card(c):
                out.append(c)
        return out
    return [c for c in _children(box) if _is_card(c)]


def _move(box, moving, target, after):
    """Flytt kortet moving rett før/etter target (Gtk.Box eller Gtk.FlowBox)."""
    if isinstance(box, Gtk.FlowBox):
        mf, tf = moving.get_parent(), target.get_parent()
        mi, ti = mf.get_index(), tf.get_index()
        idx = ti + (1 if after else 0)
        if mi < idx:
            idx -= 1
        mf.set_child(None)
        box.remove(mf)
        box.insert(moving, idx)
        nf = moving.get_parent()
        if nf is not None:
            nf.set_focusable(False)
        return
    if after:
        box.reorder_child_after(moving, target)
    else:
        prev = target.get_prev_sibling()
        box.reorder_child_after(moving, prev if prev is not moving else moving.get_prev_sibling())


def scan(root, name):
    """Gjør alle kortbokser under root flyttbare. Trygt å kalle flere ganger."""
    if root is None:
        return False
    _css()
    n = [0]

    def walk(w):
        if ((isinstance(w, Gtk.Box) and w.get_orientation() == Gtk.Orientation.VERTICAL) or isinstance(w, Gtk.FlowBox)) \
                and len(_cards(w)) >= 2:
            _enable(w, f"{name}:{n[0]}")
            n[0] += 1
        for c in _children(w):
            walk(c)
    walk(root)
    return False


def _enable(box, key):
    if getattr(box, "_ks_sort_key", None):
        for c in _cards(box):                # nye kort siden sist
            if not getattr(c, "_ks_sort", False):
                _wire(box, c)
        _apply(box)
        return
    box._ks_sort_key = key
    for c in _cards(box):
        _wire(box, c)
    _apply(box)


def _apply(box):
    order = _load().get(box._ks_sort_key) or []
    cards = _cards(box)
    if not order or len(cards) < 2:
        return
    idx = {c: i for i, c in enumerate(cards)}
    rank = lambda c: order.index(_title(c)) if _title(c) in order else 1000 + idx[c]  # noqa: E731
    want = sorted(cards, key=rank)
    if want == cards:
        return
    if isinstance(box, Gtk.FlowBox):
        for i, c in enumerate(want):
            cur = _cards(box)
            if cur[i] is not c:
                _move(box, c, cur[i], False)
        return
    anchor = cards[0].get_prev_sibling()
    for c in want:
        box.reorder_child_after(c, anchor)
        anchor = c


def _wire(box, card):
    card._ks_sort = True
    src = Gtk.DragSource(actions=Gdk.DragAction.MOVE)

    def prepare(s, x, y):
        w = card.pick(x, y, Gtk.PickFlags.DEFAULT)
        while w is not None and w is not card:
            if isinstance(w, INTERACTIVE):
                return None
            w = w.get_parent()
        card._hot = (x, y)
        return Gdk.ContentProvider.new_for_value("ks-sort:" + str(id(card)))

    def begin(s, drag):
        try:
            s.set_icon(Gtk.WidgetPaintable(widget=card), int(card._hot[0]), int(card._hot[1]))
        except Exception:  # noqa: BLE001
            pass
        card.add_css_class("ks-sort-src")
        box._ks_dragging = card

    def end(*_):
        card.remove_css_class("ks-sort-src")
        box._ks_dragging = None
    src.connect("prepare", prepare)
    src.connect("drag-begin", begin)
    src.connect("drag-end", end)
    card.add_controller(src)

    tgt = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)

    def enter(*_):
        if getattr(box, "_ks_dragging", None) not in (None, card):
            card.add_css_class("ks-sort-target")
        return Gdk.DragAction.MOVE

    def drop(t, value, x, y):
        card.remove_css_class("ks-sort-target")
        moving = getattr(box, "_ks_dragging", None)
        if moving is None or moving is card or not str(value).startswith("ks-sort:"):
            return False
        before = [c for c in _cards(box)]
        if isinstance(box, Gtk.FlowBox):
            _move(box, moving, card, x > card.get_width() / 2)
        else:
            _move(box, moving, card, y > card.get_height() / 2)
        after = _cards(box)
        _save(box._ks_sort_key, [_title(c) or "" for c in after])
        for c in after:
            if c is moving:
                _flash(c, "ks-sort-dropped", 560)
            elif before.index(c) != after.index(c):
                _flash(c, "ks-sort-moved", 420)
        return True
    tgt.connect("enter", enter)
    tgt.connect("leave", lambda *_: card.remove_css_class("ks-sort-target"))
    tgt.connect("drop", drop)
    card.add_controller(tgt)


def _flash(w, cls, ms):
    w.remove_css_class(cls)
    w.add_css_class(cls)
    GLib.timeout_add(ms, lambda: w.remove_css_class(cls) or False)


def reset(name):
    d = _load()
    for k in [k for k in d if k.startswith(name + ":")]:
        del d[k]
    try:
        with open(CFG, "w") as f:
            json.dump(d, f, indent=1, ensure_ascii=False)
    except OSError:
        pass
