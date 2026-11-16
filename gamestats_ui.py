"""Kortet «Spillstatistikk» i Spill-fanen: CS2 live, WoW-karakterer og Steam-statistikk."""
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk  # noqa: E402

import gamestats  # noqa: E402
import i18n  # noqa: E402


def _lab(text, cls=None, xalign=0, wrap=False):
    lab = Gtk.Label(label=str(text), xalign=xalign, wrap=wrap, selectable=True)
    for c in (cls or "").split():
        lab.add_css_class(c)
    return lab


def _grid(rows, cols=2):
    g = Gtk.Grid(column_spacing=24, row_spacing=4, column_homogeneous=True)
    per = (len(rows) + cols - 1) // cols
    for n, (k, v) in enumerate(rows):
        col, row = divmod(n, per)
        b = Gtk.Box(spacing=8)
        b.append(_lab(i18n.tr(k), "dim-label"))
        b.append(Gtk.Box(hexpand=True))
        b.append(_lab(f"{v:,}".replace(",", " ") if isinstance(v, int) else v, "numeric", xalign=1))
        g.attach(b, col, row, 1, 1)
    return g


def _hours(h):
    h = max(0, h or 0)
    return f"{int(h // 24)} d {int(h % 24)} t" if h >= 24 else f"{int(h)} t {int(h * 60 % 60)} min"


def _gold(c):
    c = int(c or 0)
    return f"{c // 10000} g {c % 10000 // 100} s"


class WowPlusCard(Gtk.Box):
    """World of Warcraft: av/på (alt og hver funksjon), oversikt over karakterene og søk i bagger og bank."""

    def __init__(self, card_fn):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        import wowplus
        self.W = wowplus
        c, i = card_fn("World of Warcraft",
                       i18n.tr("Varsel ved hvisking, oversikt over karakterene, bagsøk, questlogg, gull, raid-låser, "
                               "yrker, reparasjonsvarsel og WoW-skjermbilder. Bare lesing av det WoW og addonen lagrer – "
                               "ingen automatisering. Endringer gjelder etter /reload i spillet."))
        self.append(c)
        top = Gtk.Box(spacing=10)
        top.append(_lab(i18n.tr("Alle WoW-funksjonene"), "heading"))
        top.append(Gtk.Box(hexpand=True))
        self.master = Gtk.Switch(active=wowplus.cfg()["on"], valign=Gtk.Align.CENTER)
        self.master.connect("notify::active", self._on_master)
        top.append(self.master)
        i.append(top)
        self.alts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        i.append(self.alts)
        self.search = Gtk.SearchEntry(placeholder_text=i18n.tr("Søk i bagger og bank …"))
        self.search.connect("search-changed", lambda *_: self._search())
        i.append(self.search)
        self.res = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        i.append(self.res)
        exp = Gtk.Expander(label=i18n.tr("Velg WoW-funksjoner"))
        fb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=6)
        self.sw = {}
        for key, name, desc in wowplus.FEATURES:
            row = Gtk.Box(spacing=10)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            col.append(_lab(i18n.tr(name)))
            col.append(_lab(i18n.tr(desc), "dim-label caption", wrap=True))
            row.append(col)
            s = Gtk.Switch(active=wowplus.cfg()["f"][key], valign=Gtk.Align.CENTER)
            s.connect("notify::active", self._on_feature, key)
            row.append(s)
            self.sw[key] = s
            fb.append(row)
        exp.set_child(fb)
        i.append(exp)
        self.items = []
        self._sync()
        self.load()

    def _on_master(self, sw, _p):
        self.W.set_option(None, sw.get_active())
        self._sync()
        self.load()

    def _on_feature(self, sw, _p, key):
        self.W.set_option(key, sw.get_active())
        self._sync()
        self.load()

    def _sync(self):
        c = self.W.cfg()
        for k, s in self.sw.items():
            s.set_sensitive(c["on"])
        self.alts.set_visible(c["on"] and c["f"]["alts"])
        self.search.set_visible(c["on"] and c["f"]["bags"])
        self.res.set_visible(c["on"] and c["f"]["bags"])

    def load(self):
        def work():
            try:
                d = self.W.overview(gamestats.wow_stats())
            except Exception:  # noqa: BLE001
                d = None
            GLib.idle_add(self._loaded, d)
        threading.Thread(target=work, daemon=True).start()

    def _loaded(self, d):
        while (ch := self.alts.get_first_child()):
            self.alts.remove(ch)
        if not d:
            return False
        for a in d.get("alts", []):
            row = Gtk.Box(spacing=10)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            col.append(_lab(f"{a['name']}  ·  {a.get('level') or ''} {a.get('cls') or ''}", "heading"))
            sub = [a.get("zone") or "", _gold(a.get("gold"))]
            if a.get("durability") is not None and a["durability"] <= 30:
                sub.append(f"🔧 {a['durability']} %")
            col.append(_lab(" · ".join(x for x in sub if x), "dim-label caption"))
            row.append(col)
            if a.get("rested") is not None:
                full = (i18n.tr("fullt om") + " " + _hours(a["full_h"])) if a.get("full_h") else i18n.tr("fullt uthvilt")
                row.append(_lab(f"{a['rested']} % {i18n.tr('uthvilt')}\n{full}", "numeric", xalign=1))
            self.alts.append(row)
        self.items = d.get("items", [])
        self._search()
        return False

    def _search(self):
        while (ch := self.res.get_first_child()):
            self.res.remove(ch)
        q = self.search.get_text().strip().lower()
        if not q:
            self.res.append(_lab((f"{len(self.items)} " + i18n.tr("ting registrert. Banken leses når du åpner den i spillet."))
                                 if self.items else i18n.tr("Ingenting registrert ennå – logg ut eller skriv /reload i WoW."),
                                 "dim-label caption", wrap=True))
            return
        hits = [x for x in self.items if q in x[2].lower()][:60]
        if not hits:
            self.res.append(_lab(i18n.tr("Fant ingenting."), "dim-label"))
            return
        self.res.append(_grid([(x[2], f"{x[3]} · {x[0]} ({x[1].lower()})") for x in hits], cols=1))


class StatsCard(Gtk.Box):
    def __init__(self, card_fn):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        c, i = card_fn(i18n.tr("Spillstatistikk"),
                       i18n.tr("CS2 (live under kampen og totalt), World of Warcraft per karakter og statistikk fra "
                               "Steam. WoW-tallene lagres når du logger ut eller skriver /reload – /ks viser dem i spillet."))
        self.append(c)
        self.live = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        i.append(self.live)
        top = Gtk.Box(spacing=8)
        self.dd = Gtk.DropDown.new_from_strings([i18n.tr("Henter …")])
        self.dd.set_hexpand(True)
        self.dd.connect("notify::selected", lambda *_: self._show())
        top.append(self.dd)
        ref = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text=i18n.tr("Oppdater"))
        ref.add_css_class("flat")
        ref.connect("clicked", lambda *_: self.load())
        top.append(ref)
        i.append(top)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        i.append(self.body)
        self.items = []
        self.load()
        GLib.timeout_add_seconds(2, self._tick_live)

    def load(self):
        def work():
            d = gamestats.snapshot()
            GLib.idle_add(self._loaded, d)
        threading.Thread(target=work, daemon=True).start()

    def _loaded(self, d):
        items = []
        for c in d.get("wow", []):
            items.append((f"WoW · {c['title']}", ("wow", c)))
        if d.get("wow_hints"):
            items.append(("World of Warcraft – " + i18n.tr("venter på tall"), ("hint", d["wow_hints"])))
        multi = len(d.get("accounts", [])) > 1
        rank = lambda g: 0 if g["highlights"] else 1 if g["stats"] else 2   # noqa: E731 – mest statistikk først
        for acc in d.get("accounts", []):
            for g in sorted(acc["games"], key=rank):
                if g["stats"] or g["highlights"] or g["playtime_min"]:
                    items.append((g["name"] + (f"  ({acc['name']})" if multi else ""), ("steam", g)))
        if not items:
            items = [(i18n.tr("Ingen statistikk ennå"), ("none", None))]
        keep = self.items[self.dd.get_selected()][0] if self.items and self.dd.get_selected() < len(self.items) else None
        self.items = items
        self.dd.set_model(Gtk.StringList.new([n for n, _ in items]))
        names = [n for n, _ in items]
        if keep in names:
            self.dd.set_selected(names.index(keep))
        self._show()
        return False

    def _show(self):
        while (ch := self.body.get_first_child()):
            self.body.remove(ch)
        n = self.dd.get_selected()
        if not self.items or n >= len(self.items):
            return
        kind, obj = self.items[n][1]
        if kind == "wow":
            outer, P = self.body, obj.get("plus") or {}
            stack = None
            if "sheet" in P:                         # to faner: statistikk og egenskaper/talenter
                stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, vhomogeneous=False)
                outer.append(Gtk.StackSwitcher(stack=stack, halign=Gtk.Align.START))
                outer.append(stack)
                page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
                stack.add_titled(page, "s", i18n.tr("Statistikk"))
                self.body = page
            try:
                self.body.append(_lab(obj["sub"], "dim-label"))
                self.body.append(_grid(obj["rows"]))
                for title, rows in ((i18n.tr("Drept mest"), obj["kills_by"]), (i18n.tr("Drept av"), obj["killers"]),
                                    (i18n.tr("Siste økt"), obj["session"] or [])):
                    if rows:
                        self.body.append(_lab(title, "heading"))
                        self.body.append(_grid(rows))
                self._wow_plus(P)
            finally:
                self.body = outer
            if stack is not None:
                kp = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
                self._wow_sheet(kp, P.get("sheet"))
                stack.add_titled(kp, "k", i18n.tr("Egenskaper og talenter"))
                if getattr(self, "_wow_tab", "s") == "k":
                    stack.set_visible_child_name("k")
                stack.connect("notify::visible-child-name",
                              lambda st, _p: setattr(self, "_wow_tab", st.get_visible_child_name()))
        elif kind == "steam":
            sub = [f"{obj['playtime_min'] / 60:.1f} " + i18n.tr("timer spilt")]
            have, tot = obj["achievements"]
            if tot:
                sub.append(f"{have} / {tot} " + i18n.tr("prestasjoner"))
            if obj.get("last_played"):
                sub.append(i18n.tr("sist spilt") + " " + time.strftime("%d.%m.%Y", time.localtime(obj["last_played"])))
            self.body.append(_lab(" · ".join(sub), "dim-label"))
            if obj["highlights"]:
                self.body.append(_grid(obj["highlights"]))
            if obj["stats"]:
                exp = Gtk.Expander(label=i18n.tr("All statistikk fra spillet") + f" ({len(obj['stats'])})")
                exp.set_child(_grid(obj["stats"][:300]))
                self.body.append(exp)
        elif kind == "hint":
            for h in obj:
                self.body.append(_lab("• " + h, wrap=True))
        else:
            self.body.append(_lab(i18n.tr("Spill litt, så dukker statistikken opp her. WoW: logg ut eller skriv "
                                          "/reload etter at addonen «Kontrollsenter Stats» er lastet."), "dim-label",
                                  wrap=True))

    @staticmethod
    def _wow_sheet(box, S):
        """Karakterarket: spec, råd, prioritet, egenskaper, motstand og talenter."""
        if not S:
            box.append(_lab(i18n.tr("Egenskapene leses av addonen når du logger inn, logger ut eller skriver /reload i WoW."),
                            "dim-label", wrap=True))
            return
        if S.get("spec"):
            box.append(_lab(S["spec"] + (f"  ·  {' / '.join(str(t['points']) for t in S['talents'])}" if S["talents"] else ""),
                            "title-4"))
            if S.get("why"):
                box.append(_lab(S["why"], "dim-label", wrap=True))
        box.append(_lab(i18n.tr("Råd"), "heading"))
        for t in S["tips"]:
            box.append(_lab("💡 " + t, wrap=True))
        if S["prio"]:
            box.append(_lab(i18n.tr("Prioriter i denne rekkefølgen"), "heading"))
            box.append(_lab("  ›  ".join(S["prio"]), wrap=True))
        box.append(_lab(i18n.tr("Egenskaper"), "heading"))
        box.append(_grid(S["rows"]))
        if S["res"]:
            box.append(_lab(i18n.tr("Motstand"), "heading"))
            box.append(_grid(S["res"]))
        if S["talents"]:
            box.append(_lab(i18n.tr("Talenter"), "heading"))
            box.append(_grid([(t["name"] or "?", f"{t['points']} " + i18n.tr("poeng")) for t in S["talents"]]
                             + ([(i18n.tr("Ubrukte poeng"), S["unspent"])] if S["unspent"] else [])))

    def _wow_plus(self, P):
        """Uthvilt, utstyr, yrker, questlogg, låser og gull for én WoW-karakter (det som er slått på)."""
        if not P:
            return
        rows = []
        if P.get("rested"):
            r = P["rested"]
            rows += [(i18n.tr("Uthvilt XP nå"), f"{r['pct']} %"),
                     (i18n.tr("Fullt uthvilt"), (i18n.tr("om") + " " + _hours(r["full_h"])) if r["full_h"] else i18n.tr("nå"))]
        if P.get("zone"):
            rows.append((i18n.tr("Sist sett"), P["zone"]))
        if P.get("durability") is not None:
            rows.append((i18n.tr("Utstyr (dårligste del)"), f"{P['durability']} %" + (" – " + i18n.tr("reparer!")
                                                                                     if P["durability"] <= 20 else "")))
        if rows:
            self.body.append(_lab(i18n.tr("Uthvilt og utstyr"), "heading"))
            self.body.append(_grid(rows))
        if P.get("profs"):
            self.body.append(_lab(i18n.tr("Yrker"), "heading"))
            for p in P["profs"]:
                row = Gtk.Box(spacing=10)
                row.append(_lab(p["name"]))
                lb = Gtk.LevelBar(min_value=0, max_value=max(1, p["max"]), value=min(p["rank"], p["max"]),
                                  hexpand=True, valign=Gtk.Align.CENTER)
                row.append(lb)
                extra = (" – " + i18n.tr("lær neste nivå")) if p["capped"] and p["max"] < 300 else ""
                row.append(_lab(f"{p['rank']} / {p['max']}{extra}", "numeric"))
                self.body.append(row)
        if P.get("quests"):
            exp = Gtk.Expander(label=i18n.tr("Questloggen") + f" ({len(P['quests'])})")
            qb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            for q in P["quests"]:
                qb.append(_lab(("✅ " if q["done"] else "📜 ") + f"[{q.get('level') or '?'}] {q['title']}"
                               + (f"  · {q['zone']}" if q.get("zone") else ""), "heading"))
                for o in q["obj"]:
                    qb.append(_lab(("   ✓ " if o.startswith("+") else "   • ") + o[2:], "dim-label" if o.startswith("+") else None,
                                   wrap=True))
            exp.set_child(qb)
            self.body.append(exp)
        if P.get("locks") is not None:
            self.body.append(_lab(i18n.tr("Raid- og dungeon-låser"), "heading"))
            if P["locks"]:
                self.body.append(_grid([(lk["name"], i18n.tr("nullstilles om") + " " + _hours((lk["reset_at"] - time.time()) / 3600))
                                        for lk in P["locks"]], cols=1))
            else:
                self.body.append(_lab(i18n.tr("Ingen låser nå."), "dim-label"))
        if P.get("gold") and len(P["gold"]) > 1:
            self.body.append(_lab(i18n.tr("Gull over tid"), "heading"))
            self.body.append(_grid([(time.strftime("%d.%m %H:%M", time.localtime(t)), _gold(g))
                                    for t, g in P["gold"][-8:]], cols=2))

    def _tick_live(self):
        if not self.get_mapped():
            return True
        s = gamestats.LIVE.state()
        while (ch := self.live.get_first_child()):
            self.live.remove(ch)
        if s:
            self.live.append(_lab(f"🔴 CS2 live · {s['map']} · {s['mode']} · runde {s['round']} · "
                                  f"CT {s['ct']} – {s['t']} T", "heading"))
            if s["mine"]:
                self.live.append(_grid([("Kills", s["kills"]), ("Dødsfall", s["deaths"]), ("Assists", s["assists"]),
                                        ("Headshots", f"{s['hs']} ({s['hs_pct'] or '–'})"), ("Skade", s["dmg"]),
                                        ("ADR", s["adr"]), ("MVP", s["mvps"]), ("Penger", f"${s['money']}")], 4))
        return True
