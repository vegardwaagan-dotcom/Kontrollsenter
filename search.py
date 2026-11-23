"""Søk i hele Kontrollsenter (Ctrl+K): finn en innstilling, et kort eller en bryter, og hopp rett dit.

Indeksen lages fra det som faktisk vises i appen: alle sider og faner gjennomgås (sider som ikke er åpnet ennå
bygges i bakgrunnen første gang du søker), og kortenes titler, beskrivelser og radene i dem tas med.
"""
import threading
import unicodedata

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

import i18n  # noqa: E402

SKIP_PAGES = {"rgb"}                    # RGB starter OpenRGB når siden bygges – tas med når den er åpnet
CSS = """
.ks-found { outline: 3px solid @accent_color; outline-offset: 2px; border-radius: 14px;
  transition: outline-color 900ms ease-out; }
.ks-search-hit { padding: 8px 10px; }
"""
_css_done = []


def _norm(s):
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c)).replace("ø", "o").replace("æ", "ae")


def _text_of(w):
    if isinstance(w, Gtk.Label):
        return w.get_label() or ""
    if isinstance(w, Adw.PreferencesRow):
        t = w.get_title() or ""
        sub = w.get_subtitle() if hasattr(w, "get_subtitle") else ""
        return t + ("\n" + sub if sub else "")
    if isinstance(w, Gtk.CheckButton) or isinstance(w, Gtk.Button):
        return w.get_label() or ""
    return ""


def _card_of(w):
    """Kortet (eller raden) treffet ligger i – det som skal blinke."""
    p, last = w, w
    while p is not None:
        if p.has_css_class("card") or isinstance(p, (Adw.PreferencesGroup, Adw.PreferencesRow)):
            return p
        last = p
        p = p.get_parent()
    return last


def _walk(w, out, depth=0):
    if depth > 40 or not w.get_visible():
        return
    t = _text_of(w)
    if t and len(t.strip()) > 1:
        out.append((t.strip(), w))
    c = w.get_first_child()
    while c is not None:
        _walk(c, out, depth + 1)
        c = c.get_next_sibling()


def build_index(win):
    """[(side, sidetittel, fane, fanetittel, tekst, widget)] for alt som er bygd."""
    import tabbed
    idx = []
    pages = win.stack.get_pages()
    for i in range(pages.get_n_items()):
        pg = pages.get_item(i)
        name, title, child = pg.get_name(), pg.get_title() or pg.get_name(), pg.get_child()
        if not __import__("funksjoner").page_on(name):     # slått av under Funksjoner
            continue
        tps = []

        def find(w, d=0):
            if isinstance(w, tabbed.TabbedPage):
                tps.append(w)
                return
            if d > 14:
                return
            c = w.get_first_child()
            while c is not None:
                find(c, d + 1)
                c = c.get_next_sibling()
        find(child)
        if tps:
            for tp in tps:
                ps = tp.stack.get_pages()
                for j in range(ps.get_n_items()):
                    tpage = ps.get_item(j)
                    hits = []
                    _walk(tpage.get_child(), hits)
                    for t, w in hits:
                        idx.append((name, title, tpage.get_name(), tpage.get_title(), t, w))
        else:
            hits = []
            _walk(child, hits)
            for t, w in hits:
                idx.append((name, title, None, None, t, w))
    return idx


def search(idx, q, limit=40):
    nq = _norm(q).split()
    if not nq:
        return []
    scored, seen = [], set()
    for row in idx:
        name, title, tab, ttitle, text, w = row
        hay = _norm(f"{text} {title} {ttitle or ''}")
        if not all(x in hay for x in nq):
            continue
        first = text.splitlines()[0]
        key = (name, tab, first[:60])
        if key in seen:
            continue
        seen.add(key)
        important = isinstance(w, Adw.PreferencesRow) or (isinstance(w, Gtk.Label) and (
            w.has_css_class("heading") or w.has_css_class("title-4") or w.has_css_class("ks-card-title")))
        caps = first.isupper()                                   # «VIFTE» o.l. er måleverdier, ikke innstillinger
        score = (0 if important else 1, 1 if caps else 0, 0 if _norm(first).startswith(nq[0]) else 1,
                 0 if nq[0] in _norm(first) else 1, len(first))
        scored.append((score, row))
    scored.sort(key=lambda x: x[0])
    return [r for _s, r in scored[:limit]]


def go_to(win, row):
    name, _title, tab, _tt, _text, w = row
    win.stack.set_visible_child_name(name)
    lead = getattr(win, "_leader", {}).get(name, name)
    if hasattr(win, "_on_sidebar") and getattr(win, "_rows", {}).get(lead) is not None:
        try:
            win.sidebar.select_row(win._rows[lead])
        except Exception:  # noqa: BLE001
            pass

    def after():
        if tab:
            import tabbed
            p = w
            while p is not None and not isinstance(p, tabbed.TabbedPage):
                p = p.get_parent()
            if p is not None:
                p.show_tab(tab)
        GLib.timeout_add(250, lambda: (_reveal(w), False)[1])
        return False
    GLib.timeout_add(120, after)


def _reveal(w):
    target = _card_of(w)
    sc = target.get_ancestor(Gtk.ScrolledWindow)
    if sc is not None and sc.get_child() is not None:
        ok, pt = target.compute_point(sc.get_child(), __import__("gi.repository.Graphene",
                                                                  fromlist=["Point"]).Point())
        if ok:
            adj = sc.get_vadjustment()
            adj.set_value(max(0, pt.y - 40))
    target.add_css_class("ks-found")
    GLib.timeout_add(1800, lambda: (target.remove_css_class("ks-found"), False)[1])


def _act(win, body, label):
    """Kjør en handling (samme som fra mobilen) og vis svaret som toast."""
    import threading

    def work():
        try:
            import remote
            b = body
            if b is None:                                    # spillmodus: bytt fra det den er nå
                b = {"a": "gamemode", "on": not bool(remote.build_status(win).get("gamemode"))}
            ok, msg = remote.do_action(win, b)
            txt = msg if isinstance(msg, str) and msg else (label + " ✓")
        except Exception as e:  # noqa: BLE001
            txt = f"{label}: {e}"
        GLib.idle_add(lambda: (win.toast(txt) if hasattr(win, "toast") else None, False)[1])
    threading.Thread(target=work, daemon=True).start()


def actions(win):
    """Hurtigkommandoer: (tekst, søkeord, funksjon)."""
    out = []

    def a(text, words, fn):
        out.append((text, words, fn))
    st = getattr(win, "bg", None)
    a("🥽 Klar for VR", "vr quest steamvr alvr wivrn klar",
      lambda: threading.Thread(target=lambda: __import__("homeplus").vr_ready(win), daemon=True).start())
    a("🆘 Be om hjelp", "hjelp help fjernhjelp rustdesk",
      lambda: threading.Thread(target=lambda: __import__("homeplus").ask_help(), daemon=True).start())
    a("🩺 Hvorfor er PC-en treg?", "treg hakker sakte assistent hjelp lag",
      lambda: __import__("assistant_ui").open_dialog(win))
    a("🎮 Spillmodus på/av", "spillmodus gamemode ytelse", lambda: _act(win, None, "Spillmodus"))
    a("🎬 Lagre klipp nå", "klipp clip lagre opptak", lambda: _act(win, {"a": "clip"}, "Klipp"))
    a("📸 Ta skjermbilde", "skjermbilde screenshot", lambda: _act(win, {"a": "clipshot"}, "Skjermbilde"))
    a("🔇 Demp lyden", "demp mute lyd stille", lambda: _act(win, {"a": "volume", "mute": True}, "Demp"))
    a("🔈 Slå på lyden", "lyd på unmute", lambda: _act(win, {"a": "volume", "mute": False}, "Lyd"))
    a("🍽️ Middag! til alle", "middag mat familie", lambda: _act(win, {"a": "dinner"}, "Middag"))
    a("🔒 Lås PC-en", "lås lock", lambda: _act(win, {"a": "system", "do": "lock"}, "Lås"))
    a("🥽 Start VR", "vr quest steamvr alvr", lambda: _act(win, {"a": "vr", "do": "start"}, "VR"))
    a("🌙 Nattlys på", "nattlys night", lambda: _act(win, {"a": "nightlight", "on": True, "temp": 3400}, "Nattlys"))
    a("☀️ Nattlys av", "nattlys av night", lambda: _act(win, {"a": "nightlight", "on": False}, "Nattlys"))
    a("📺 Stue-modus", "stue tv ambient andreskjerm klokke", lambda: win.open_ambient())
    try:
        import scenes
        for sc in scenes.load()["scenes"]:
            a(f"✨ Kjør scene «{sc['name']}»", "scene " + sc["name"], lambda sid=sc["id"], n=sc["name"]:
              _act(win, {"a": "scene", "id": sid}, n))
    except Exception:  # noqa: BLE001
        pass
    try:
        import theme
        for k, t in theme.THEMES.items():
            a(f"🎨 Tema: {t['name']}", "tema theme farge " + t["name"], lambda k=k: theme.set_theme(k))
    except Exception:  # noqa: BLE001
        pass
    try:
        import avprofiles as AP
        c = AP.cfg()
        for p in c["audio"]:
            a(f"🎧 Lydprofil «{p['name']}»", "lyd profil " + p["name"],
              lambda pid=p["id"], n=p["name"]: _act(win, {"a": "avprofile", "kind": "audio", "id": pid}, n))
        for p in c["display"]:
            a(f"🖥️ Skjermprofil «{p['name']}»", "skjerm profil " + p["name"],
              lambda pid=p["id"], n=p["name"]: _act(win, {"a": "avprofile", "kind": "display", "id": pid}, n))
    except Exception:  # noqa: BLE001
        pass
    _ = st
    return out


def search_actions(acts, q):
    nq = _norm(q).split()
    if not nq:
        return []
    return [x for x in acts if all(w in _norm(x[0] + " " + x[1]) for w in nq)][:8]


class SearchDialog(Adw.Dialog):
    def __init__(self, win):
        super().__init__(title=i18n.tr("Søk"), content_width=620, content_height=560)
        if not _css_done:
            _css_done.append(1)
            import theme
            theme.add_css(CSS, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 6)
        self.win = win
        self.idx = []
        tv = Adw.ToolbarView()
        tv.add_top_bar(Adw.HeaderBar())
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(14)
        self.entry = Gtk.SearchEntry(placeholder_text=i18n.tr("Søk eller gi en kommando – «vifte», «spillmodus», «klipp», «tema»"))
        box.append(self.entry)
        self.status = Gtk.Label(xalign=0)
        self.status.add_css_class("dim-label")
        self.status.add_css_class("caption")
        box.append(self.status)
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.list.add_css_class("boxed-list")
        sc = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER, child=self.list)
        box.append(sc)
        tv.set_content(box)
        self.set_child(tv)
        self.rows = []
        self.acts = actions(win)
        self.entry.connect("search-changed", lambda *_: self._update())
        self.entry.connect("activate", lambda *_: self._open(0))
        self.list.connect("row-activated", lambda _l, r: self._open(r.get_index()))
        self.status.set_label(i18n.tr("Gjør klar søket …"))
        GLib.idle_add(self._prepare)

    def _prepare(self):
        """Bygg sidene som ikke er åpnet ennå (én om gangen, så vinduet ikke fryser), så indeksen."""
        lazy = [n for n, lz in getattr(self.win, "_lazy", {}).items() if lz[3] is None and n not in SKIP_PAGES
                and __import__("funksjoner").page_on(n)]

        def step():
            if lazy:
                n = lazy.pop(0)
                try:
                    self.win.ensure_lazy(n)
                except Exception:  # noqa: BLE001
                    pass
                return True
            try:
                if getattr(self.win, "audio_page", None) is None:
                    self.win.ensure_audio_page()
            except Exception:  # noqa: BLE001
                pass
            GLib.timeout_add(300, self._index)
            return False
        GLib.idle_add(step)
        return False

    def _index(self):
        self.idx = build_index(self.win)
        self.status.set_label(i18n.tr("{n} ting å søke i").format(n=len(self.idx)))
        self._update()
        return False

    def _update(self):
        while (r := self.list.get_first_child()) is not None:
            self.list.remove(r)
        q = self.entry.get_text()
        acts = search_actions(self.acts, q)
        self.rows = [("act", a) for a in acts] + (search(self.idx, q) if self.idx else [])
        for row in self.rows:
            if row[0] == "act":
                r = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                r.add_css_class("ks-search-hit")
                t = Gtk.Label(label=row[1][0], xalign=0)
                t.add_css_class("heading")
                r.append(t)
                s2 = Gtk.Label(label=i18n.tr("Hurtigkommando – trykk Enter"), xalign=0)
                s2.add_css_class("dim-label")
                s2.add_css_class("caption")
                r.append(s2)
                self.list.append(r)
                continue
            name, title, _tab, ttitle, text, _w = row
            lines = text.splitlines()
            r = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            r.add_css_class("ks-search-hit")
            t = Gtk.Label(label=lines[0][:90], xalign=0, ellipsize=3)
            t.add_css_class("heading")
            r.append(t)
            where = title + (f" → {ttitle}" if ttitle else "")
            s = Gtk.Label(label=where + (" · " + lines[1][:80] if len(lines) > 1 else ""), xalign=0, ellipsize=3)
            s.add_css_class("dim-label")
            s.add_css_class("caption")
            r.append(s)
            self.list.append(r)
        if self.entry.get_text().strip() and not self.rows and self.idx:
            self.status.set_label(i18n.tr("Fant ingenting – prøv et annet ord"))
        elif self.idx:
            self.status.set_label(i18n.tr("{n} treff").format(n=len(self.rows)) if self.entry.get_text().strip()
                                  else i18n.tr("{n} ting å søke i").format(n=len(self.idx)))

    def _open(self, i):
        if 0 <= i < len(self.rows):
            row = self.rows[i]
            self.close()
            if row[0] == "act":
                row[1][2]()
            else:
                go_to(self.win, row)
