"""Ryddig PC-app: sider som hører sammen er gruppert, og lange sider er delt i kategorier.

* GROUPS: flere sider bak én linje i sidemenyen (f.eks. Spill + VR + Strømming). Når du står på en av dem, vises en
  kategorilinje øverst – ‹ rullehjul › – for å bytte mellom dem (som i mobilappen).
* PAGE_CATS: lange sider (Familie, GPU, Discord) deles i kategorier med samme linje øverst; bare kortene i valgt
  kategori vises.
"""
import json
import os

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

import i18n  # noqa: E402

PREF = os.path.expanduser("~/.config/systemmonitor/kategorier.json")

# gruppe: (nøkkel, tittel i sidemenyen, ikon, [sider – den første er «lederen»])
GROUPS = [
    ("spill", "Spill", "ks-games-symbolic", ["spill", "vr", "stromming"]),
    ("utstyr", "Utstyr", "ks-rgb-symbolic", ["rgb", "logitech", "cpuskjerm", "msi"]),
    ("nett", "Nett og tilkobling", "ks-network-symbolic", ["nettverk", "wifi", "bluetooth"]),
    ("hjem", "Scener og Smart Hjem", "ks-smarthome-symbolic", ["scener", "smarthjem"]),
    ("pcer", "PC-er", "ks-home-symbolic", ["hjemme", "venner"]),
]
ICONS = {"spill": "🎮", "vr": "🥽", "stromming": "📡", "rgb": "🌈", "logitech": "🖱️", "cpuskjerm": "🖥️", "msi": "💻",
         "nettverk": "🌐", "wifi": "📶", "bluetooth": "🔵", "scener": "✨", "smarthjem": "🏠", "hjemme": "🏠",
         "venner": "👥", "chat": "💬", "fjernhjelp": "🛟", "ai": "🤖", "kalender": "📅"}

# side: [(nøkkel, navn, [titler – «=X» er nøyaktig, ellers starten av tittelen; «G:» = gruppe-overskrift])]
PAGE_CATS = {
    "familie": [("kontroll", "🛡️ Kontroll og trygghet", ["Familiekontroll", "Trygg på nettet"]),
                ("sammen", "💬 Sammen", ["=Familie", "Se på", "Ukeplan"]),
                ("mal", "⭐ Mål og belønning", ["Mål og belønning", "Belønningsbutikk", "Ukesrapport"])],
    "gpu": [("kort", "🎛️ Skjermkortene", ["NVIDIA", "AMD", "Intel", "Spillinnstillinger", "Ved oppstart",
                                          "Gi Kontrollsenter", "Fant ingen"]),
            ("skjerm", "🖥️ Skjerm og lys", ["Hovedskjermkort", "Skjermprofiler", "Nattlys"])],
    "discord": [("samtale", "📞 Samtalen", ["=G:", "G:Samtalen"]),
                ("lyd", "🎙️ Lyd, mikrofon og overlay", ["G:Lyd", "G:Mikrofon", "G:Overlay"]),
                ("chat", "💬 Servere og chat", ["G:Servere"]),
                ("oppsett", "🔗 Tilkobling", ["G:Full tilkobling"])],
}


def _prefs():
    try:
        return json.load(open(PREF))
    except (OSError, ValueError):
        return {}


def _save(**kw):
    d = _prefs()
    d.update(kw)
    os.makedirs(os.path.dirname(PREF), exist_ok=True)
    json.dump(d, open(PREF, "w"))


def group_of(name):
    return next((g for g in GROUPS if name in g[3]), None)


# --------------------------------------------------------------------------
# Kategorilinjen: ‹ [rullehjul] ›
# --------------------------------------------------------------------------
CSS = """
.ks-catbar { padding: 6px; border-radius: 16px; margin: 4px 0 6px 0; background: alpha(currentColor, .05);
  border: 1px solid alpha(currentColor, .10); }
.ks-catbar dropdown > button { min-height: 38px; font-weight: 700; }
.ks-catbar > button.ks-catstep { min-width: 38px; min-height: 38px; padding: 0; font-size: 20px; font-weight: 700; }
"""
_css = []


class CatBar(Gtk.Box):
    def __init__(self, items, current, on_change):
        super().__init__(spacing=8)
        if not _css:
            _css.append(1)
            import theme
            theme.add_css(CSS, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 4)
        self.add_css_class("ks-catbar")
        self.items, self.on_change = items, on_change
        prev = Gtk.Button(label="‹", tooltip_text=i18n.tr("Forrige"))
        nxt = Gtk.Button(label="›", tooltip_text=i18n.tr("Neste"))
        for b in (prev, nxt):
            b.add_css_class("ks-catstep")
            b.add_css_class("flat")
        self.dd = Gtk.DropDown.new_from_strings([i18n.tr(n) for _k, n in items])
        self.dd.set_hexpand(True)
        keys = [k for k, _n in items]
        self.dd.set_selected(keys.index(current) if current in keys else 0)
        self._quiet = False
        self.dd.connect("notify::selected", lambda d, _p: self._quiet or on_change(keys[d.get_selected()]))
        prev.connect("clicked", lambda *_: self.step(-1))
        nxt.connect("clicked", lambda *_: self.step(1))
        self.append(prev)
        self.append(self.dd)
        self.append(nxt)

    def step(self, d):
        n = len(self.items)
        self.dd.set_selected((self.dd.get_selected() + d) % n)

    def select(self, key):
        keys = [k for k, _n in self.items]
        if key in keys and keys.index(key) != self.dd.get_selected():
            self._quiet = True
            self.dd.set_selected(keys.index(key))
            self._quiet = False


# --------------------------------------------------------------------------
# Kategorier inne på en lang side
# --------------------------------------------------------------------------
def _title(w, d=0):
    from gi.repository import Adw
    if getattr(w, "_ks_title", None):
        return w._ks_title
    if isinstance(w, Adw.PreferencesGroup):
        return "G:" + (w.get_title() or "")
    if isinstance(w, Gtk.Label) and (w.has_css_class("heading") or w.has_css_class("title-4") or
                                     w.has_css_class("title-3")):
        return w.get_label()
    if d > 6:
        return None
    c = w.get_first_child()
    while c is not None:
        t = _title(c, d + 1)
        if t:
            return t
        c = c.get_next_sibling()
    return None


def _match(t, keys):
    for k in keys:
        if k.startswith("="):
            if t == k[1:]:
                return True
        elif t.startswith(k):
            return True
    return False


def attach(name, page):
    """Del en lang side i kategorier (kalles når siden er bygd)."""
    cats = PAGE_CATS.get(name)
    if not cats or page is None or getattr(page, "_ks_cats", False):
        return
    import effects
    box = effects._content_box(page)
    if box is None:
        return
    page._ks_cats = True
    kids = []
    c = box.get_first_child()
    while c is not None:
        kids.append(c)
        c = c.get_next_sibling()
    owner = {}
    for w in kids:
        t = _title(w)
        if t is None:
            continue
        for key, _n, keys in cats:
            if _match(t, keys):
                owner[w] = key
                break
    present = [(k, n) for k, n, _keys in cats if k in owner.values()]
    if len(present) < 2:
        return
    cur = _prefs().get("page:" + name, present[0][0])
    if cur not in [k for k, _n in present]:
        cur = present[0][0]

    def show(key):
        _save(**{"page:" + name: key})
        for w, k in owner.items():
            if k == key:
                if getattr(w, "_ks_cat_hidden", False):
                    w._ks_cat_hidden = False
                    w.set_visible(True)
            elif w.get_visible():
                w._ks_cat_hidden = True
                w.set_visible(False)
        # kortene kan ha blitt flyttbare (sortbox → Dash): be rutenettet tegne seg på nytt
        try:
            import dashboard
            from gi.repository import GLib
            seen = set()
            for w in owner:
                d = w.get_ancestor(dashboard.Dash)
                if d is not None and id(d) not in seen:
                    seen.add(id(d))
                    GLib.idle_add(lambda d=d: (d._layout(), False)[1])
        except Exception:  # noqa: BLE001
            pass
        try:
            effects.page_enter(page)
        except Exception:  # noqa: BLE001
            pass
    bar = CatBar(present, cur, show)
    box.prepend(bar)
    show(cur)
