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
            self.body.append(_lab(obj["sub"], "dim-label"))
            self.body.append(_grid(obj["rows"]))
            for title, rows in ((i18n.tr("Drept mest"), obj["kills_by"]), (i18n.tr("Drept av"), obj["killers"]),
                                (i18n.tr("Siste økt"), obj["session"] or [])):
                if rows:
                    self.body.append(_lab(title, "heading"))
                    self.body.append(_grid(rows))
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
        else:
            self.body.append(_lab(i18n.tr("Spill litt, så dukker statistikken opp her. WoW: logg ut eller skriv "
                                          "/reload etter at addonen «Kontrollsenter Stats» er lastet."), "dim-label",
                                  wrap=True))

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
