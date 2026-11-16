"""Side med faner øverst (som Hjem/Styr/Spill i mobilappen).

Hver fane er en egen rullbar kolonne med kort. Kortbyggerne skriver til ``self.box``,
så ``tab()`` setter ``self.box`` til fanen som bygges nå. Siste valgte fane huskes.
"""
import json
import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

import i18n  # noqa: E402

_CFG = os.path.expanduser("~/.config/systemmonitor/faner.json")


def _load():
    try:
        with open(_CFG) as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def _save(key, name):
    d = _load()
    if d.get(key) == name:
        return
    d[key] = name
    try:
        os.makedirs(os.path.dirname(_CFG), exist_ok=True)
        with open(_CFG, "w") as f:
            json.dump(d, f)
    except OSError:
        pass


class TabbedPage(Gtk.Box):
    def __init__(self, key):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._key = key
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, vexpand=True,
                               hhomogeneous=False, vhomogeneous=False)
        bar = Gtk.StackSwitcher(stack=self.stack, halign=Gtk.Align.CENTER)
        bar.add_css_class("ks-tabs")
        for side, v in (("top", 8), ("bottom", 2), ("start", 12), ("end", 12)):
            getattr(bar, f"set_margin_{side}")(v)
        self.tabbar = bar
        self.append(bar)
        self.append(self.stack)
        self.box = None

    def tab(self, name, title):
        """Ny fane; kortene som bygges etterpå havner i den."""
        import theme
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(12)
        sc = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        sc.set_child(Adw.Clamp(maximum_size=theme.PAGE_WIDTH, tightening_threshold=900, child=box))
        self.stack.add_titled(sc, name, i18n.tr(title))
        self.box = box
        return box

    def finish(self):
        """Fjern tomme faner, skjul fanelinjen hvis bare én er igjen, og åpne fanen fra sist."""
        pages = self.stack.get_pages()
        for pg in [pages.get_item(i) for i in range(pages.get_n_items())]:
            sc = pg.get_child()
            box = sc.get_child()
            box = box.get_child() if isinstance(box, Gtk.Viewport) else box
            inner = box.get_child() if isinstance(box, Adw.Clamp) else box
            if inner is not None and inner.get_first_child() is None:
                self.stack.remove(sc)
        self.tabbar.set_visible(self.stack.get_pages().get_n_items() > 1)
        last = _load().get(self._key)
        if last and self.stack.get_child_by_name(last):
            self.stack.set_visible_child_name(last)
        self.stack.connect("notify::visible-child-name",
                           lambda s, _p: _save(self._key, s.get_visible_child_name()))

    def show_tab(self, name):
        if self.stack.get_child_by_name(name):
            self.stack.set_visible_child_name(name)
