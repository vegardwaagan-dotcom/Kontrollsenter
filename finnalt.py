"""«Finn alt»: én fane som viser hvor alle innstillinger og funksjoner ligger – og et søkefelt.

Uten søk: alle sidene i samme rekkefølge som sidemenyen, med kategoriene/fanene og kortene i hver.
Med søk: treffene (også hurtigkommandoer). Trykk på noe for å hoppe rett dit – kortet blinker.
Lista lages fra det som faktisk finnes i appen (search.build_index), så den er alltid oppdatert.
"""
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk  # noqa: E402

import i18n  # noqa: E402
import search as S  # noqa: E402

_t = i18n.tr


def _win(w):
    r = w.get_root()
    return r if r is not None and hasattr(r, "stack") else None


class FindAllPage(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.idx, self.idx_t, self.busy = [], 0, False
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(outer, f"set_margin_{side}")(16)
        clamp = __import__("gi.repository.Adw", fromlist=["Clamp"]).Clamp(maximum_size=1000, child=outer)
        self.set_child(clamp)
        self.entry = Gtk.SearchEntry(placeholder_text=_t("Søk etter en innstilling eller funksjon – f.eks. «vifte», "
                                                         "«DLSS», «oppløsning», «tema»"))
        self.entry.add_css_class("ks-find-entry")
        outer.append(self.entry)
        self.status = Gtk.Label(xalign=0, label=_t("Gjør klar oversikten …"))
        self.status.add_css_class("dim-label")
        self.status.add_css_class("caption")
        outer.append(self.status)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        outer.append(self.body)
        self.entry.connect("search-changed", lambda *_: self._render())
        self.entry.connect("activate", lambda *_: self._first())
        self.connect("map", lambda *_: self._ensure())
        self._first_hit = None

    # ------------------------------------------------------------------
    def _ensure(self):
        if self.busy or (self.idx and time.time() - self.idx_t < 120):
            return
        win = _win(self)
        if win is None:
            return
        self.busy = True
        if not self.idx:
            self.status.set_label(_t("Gjør klar oversikten … (første gang tar det noen sekunder)"))

        def done(idx):
            self.idx, self.idx_t, self.busy = idx, time.time(), False
            self._render()
        S.prepare(win, done)

    def _clear(self):
        while (c := self.body.get_first_child()) is not None:
            self.body.remove(c)

    def _go(self, row):
        win = _win(self)
        if win is not None:
            S.go_to(win, row)

    def _first(self):
        if self._first_hit:
            self._first_hit()

    # ------------------------------------------------------------------
    def _render(self):
        self._clear()
        self._first_hit = None
        q = self.entry.get_text().strip()
        if q:
            self._results(q)
        else:
            self._directory()

    def _results(self, q):
        win = _win(self)
        acts = S.search_actions(S.actions(win), q) if win is not None else []
        hits = S.search(self.idx, q, limit=80) if self.idx else []
        lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        lb.add_css_class("boxed-list")
        rows = []
        for a in acts:
            rows.append((a[2], a[0], _t("Hurtigkommando – gjør det med en gang")))
        for row in hits:
            name, title, _tab, ttitle, text, w = row
            cat = S.category_of(w)
            lines = text.splitlines()
            where = " → ".join(x for x in (title, ttitle, cat[1] if cat else None) if x)
            rows.append((lambda r=row: self._go(r), lines[0][:100],
                         where + (" · " + lines[1][:90] if len(lines) > 1 else "")))
        for fn, head, sub in rows:
            r = Gtk.ListBoxRow(activatable=True)
            b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            b.add_css_class("ks-search-hit")
            t = Gtk.Label(label=head, xalign=0, ellipsize=3)
            t.add_css_class("heading")
            b.append(t)
            s = Gtk.Label(label=sub, xalign=0, ellipsize=3)
            s.add_css_class("dim-label")
            s.add_css_class("caption")
            b.append(s)
            r.set_child(b)
            r._fn = fn
            lb.append(r)
        lb.connect("row-activated", lambda _l, r: r._fn())
        if rows:
            self._first_hit = rows[0][0]
            self.body.append(lb)
            self.status.set_label(_t("{n} treff – trykk på et for å gå dit (Enter = det første)").format(n=len(rows)))
        else:
            self.status.set_label(_t("Fant ingenting – prøv et annet ord") if self.idx else
                                  _t("Gjør klar oversikten …"))

    def _directory(self):
        """Alle sidene → kategorier/faner → kortene."""
        import theme
        win = _win(self)
        if win is None or not self.idx:
            return
        titles = {}
        pages = win.stack.get_pages()
        for i in range(pages.get_n_items()):
            pg = pages.get_item(i)
            titles[pg.get_name()] = pg.get_title() or pg.get_name()
        groups = {}                                   # side → {gruppe: [(tekst, rad)]}
        for row in self.idx:
            name, _title, _tab, ttitle, text, w = row
            if not S.is_title(w):
                continue
            first = text.splitlines()[0].strip()
            if len(first) < 2 or first.isupper():
                continue
            cat = S.category_of(w)
            g = " · ".join(x for x in (ttitle, cat[1] if cat else None) if x) or ""
            lst = groups.setdefault(name, {}).setdefault(g, [])
            if first not in [x[0] for x in lst]:
                lst.append((first, row))
        n_items = 0
        for sec, names in theme.SECTIONS:
            present = [n for n in names if n in groups]
            if not present:
                continue
            h = Gtk.Label(label=_t(sec).upper(), xalign=0, margin_top=6)
            h.add_css_class("caption-heading")
            h.add_css_class("dim-label")
            self.body.append(h)
            for name in present:
                self.body.append(self._page_card(name, titles.get(name, name), theme.PAGE_HELP.get(name, ""),
                                                 groups[name]))
                n_items += sum(len(v) for v in groups[name].values())
        self.status.set_label(_t("{p} sider og {n} innstillinger og funksjoner. Trykk på en for å gå dit, eller "
                                 "søk øverst.").format(p=len(groups), n=n_items))

    def _page_card(self, name, title, help_, groups):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.add_css_class("card")
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for side, v in (("top", 12), ("bottom", 12), ("start", 14), ("end", 14)):
            getattr(inner, f"set_margin_{side}")(v)
        card.append(inner)
        exp = Gtk.Expander()
        head = Gtk.Box(spacing=10)
        hl = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        t = Gtk.Label(label=_t(title), xalign=0)
        t.add_css_class("heading")
        hl.append(t)
        if help_:
            s = Gtk.Label(label=_t(help_), xalign=0, wrap=True)
            s.add_css_class("dim-label")
            s.add_css_class("caption")
            hl.append(s)
        head.append(hl)
        n = sum(len(v) for v in groups.values())
        cnt = Gtk.Label(label=str(n), valign=Gtk.Align.CENTER)
        cnt.add_css_class("dim-label")
        head.append(cnt)
        go = Gtk.Button(label=_t("Åpne"), valign=Gtk.Align.CENTER)
        go.add_css_class("flat")
        go.connect("clicked", lambda *_: self._open_page(name))
        head.append(go)
        exp.set_label_widget(head)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=8)
        for g, items in groups.items():
            if g:
                gl = Gtk.Label(label=g, xalign=0, margin_top=4)
                gl.add_css_class("caption-heading")
                body.append(gl)
            fb = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=4, min_children_per_line=1,
                             column_spacing=6, row_spacing=6, homogeneous=False)
            for text, row in items:
                b = Gtk.Button(label=text[:60])
                b.add_css_class("ks-find-item")
                b.connect("clicked", lambda *_a, r=row: self._go(r))
                fb.append(b)
            body.append(fb)
        exp.set_child(body)
        inner.append(exp)
        return card

    def _open_page(self, name):
        win = _win(self)
        if win is None:
            return
        win.stack.set_visible_child_name(name)
        rows = getattr(win, "_rows", {})
        lead = getattr(win, "_leader", {}).get(name, name)
        if rows.get(lead) is not None:
            try:
                win.sidebar.select_row(rows[lead])
            except Exception:  # noqa: BLE001
                pass
        return False
