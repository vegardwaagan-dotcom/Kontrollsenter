"""Kortene for spill-runde 3 på Spill-siden: Ditt spillår, Før og etter, Nettet i spillet, Plass per spill og
LAN-turnering."""
import threading

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

import i18n  # noqa: E402
import spill3 as S  # noqa: E402

_t = i18n.tr


def _bg(work, done):
    def run():
        try:
            r = work()
        except Exception as e:  # noqa: BLE001
            r = e
        GLib.idle_add(lambda: (done(r), False)[1])
    threading.Thread(target=run, daemon=True).start()


def _dim(t=""):
    lb = Gtk.Label(label=t, xalign=0, wrap=True)
    lb.add_css_class("dim-label")
    return lb


def _clear(box):
    while (c := box.get_first_child()) is not None:
        box.remove(c)


def _toast(w, text):
    r = w.get_root()
    if hasattr(r, "toast"):
        r.toast(text)


# ------------------------------------------------------------------ Ditt spillår
def wrapped_card(card):
    c, i = card(_t("🎁 Ditt spillår"), _t("Timer, favorittspill, lengste økt, klipp og prestasjoner i år – "
                                         "del det i chatten."))
    lab = Gtk.Label(xalign=0, wrap=True, selectable=True)
    i.append(lab)
    row = Gtk.Box(spacing=8)
    share = Gtk.Button(label=_t("💬 Del i chatten"), sensitive=False)
    row.append(share)
    i.append(row)
    st = {}

    def show(r):
        if isinstance(r, Exception):
            lab.set_label(f"✗ {r}")
            return
        st["r"] = r
        lab.set_label(r["text"])
        share.set_sensitive(bool(r["total_h"]))
    _bg(S.wrapped, show)

    def do_share(*_):
        import chat
        try:
            chat.send("alle", st["r"]["text"])
            _toast(c, _t("Delt i chatten ✓"))
        except Exception as e:  # noqa: BLE001
            _toast(c, f"✗ {e}")
    share.connect("clicked", do_share)
    return c


# ------------------------------------------------------------------ Før og etter
def compare_card(card):
    c, i = card(_t("⚖️ Før og etter"), _t("Skal du bytte driver, Proton eller innstillinger? Merk det her, spill som "
                                         "vanlig – så ser du om FPS ble bedre eller dårligere i hvert spill."))
    row = Gtk.Box(spacing=8)
    e = Gtk.Entry(placeholder_text=_t("Hva endrer du? f.eks. Ny NVIDIA-driver"), hexpand=True)
    row.append(e)
    b = Gtk.Button(label=_t("Merk endring"))
    row.append(b)
    i.append(row)
    res = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    i.append(res)

    def show(r):
        _clear(res)
        if isinstance(r, Exception) or not r["mark"]:
            res.append(_dim(_t("Ingen endring merket ennå.")))
            return
        import time
        m = r["mark"]
        res.append(_dim(_t(f"Siden «{m['label']}» ({time.strftime('%d.%m', time.localtime(m['t']))}):")))
        if not r["games"]:
            res.append(_dim(_t("Spill noen økter, så kommer sammenligningen her.")))
        for g in r["games"]:
            arrow = "🟢 +" if g["pct"] > 2 else "🔴 " if g["pct"] < -2 else "⚪ "
            low = f" · 1 % low {g['low_before']} → {g['low_after']}" if g["low_before"] and g["low_after"] else ""
            res.append(Gtk.Label(label=f"{arrow}{g['pct']:.1f} %  {g['game']}: {g['before']} → {g['after']} FPS{low}",
                                 xalign=0, wrap=True))
    b.connect("clicked", lambda *_: (S.mark(e.get_text()), e.set_text(""), _bg(S.compare, show),
                                     _toast(c, _t("Merket ✓"))))
    _bg(S.compare, show)
    return c


# ------------------------------------------------------------------ Nettet i spillet
class NetCard(Gtk.Box):
    def __init__(self, card):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        c, i = card(_t("📶 Nettet i spillet"), _t("Ping og pakketap til ruteren, internett og selve spillserveren mens "
                                                  "du spiller – så du ser om laggen kommer fra deg eller serveren."))
        self.append(c)
        self.verdict = Gtk.Label(xalign=0, wrap=True)
        self.verdict.add_css_class("heading")
        i.append(self.verdict)
        self.vals = _dim()
        i.append(self.vals)
        self.area = Gtk.DrawingArea(content_height=90, hexpand=True)
        self.area.set_draw_func(self._draw)
        i.append(self.area)
        i.append(_dim(_t("Grønn = spillserveren · blå = internett · grå = ruteren. Måles hvert 30. sekund.")))
        self._tick()
        GLib.timeout_add_seconds(15, self._tick)

    def _tick(self):
        if not self.get_mapped() and self.vals.get_label():
            return True
        h = S.NET["hist"]
        if not h:
            self.verdict.set_label(_t("Starter når du spiller"))
            self.vals.set_label(_t("Ingen måling ennå."))
        else:
            x = h[-1]

            def f(v, loss):
                return "–" if v is None else f"{v:.0f} ms" + (f" ({loss} % tap)" if loss else "")
            self.verdict.set_label(_t(S.net_verdict()))
            self.vals.set_label(_t(f"{S.NET['game'] or ''} · Spillserver {x.get('server') or '?'}: "
                                   f"{f(x['srv'], x['srv_loss'])} · Internett {f(x['net'], x['net_loss'])} · "
                                   f"Ruter {f(x['gw'], x['gw_loss'])}"))
        self.area.queue_draw()
        return True

    def _draw(self, _a, cr, w, h):
        hist = S.NET["hist"][-60:]
        cr.set_source_rgba(0.5, 0.5, 0.6, 0.1)
        cr.rectangle(0, 0, w, h)
        cr.fill()
        if len(hist) < 2:
            return
        top = max([x[k] or 0 for x in hist for k in ("srv", "net", "gw")] + [50])
        for k, col in (("gw", (0.6, 0.6, 0.65)), ("net", (0.36, 0.55, 1)), ("srv", (0.2, 0.82, 0.48))):
            cr.set_source_rgb(*col)
            cr.set_line_width(2)
            started = False
            for n, x in enumerate(hist):
                v = x.get(k)
                if v is None:
                    started = False
                    continue
                px, py = n / (len(hist) - 1) * w, h - v / top * (h - 6) - 3
                (cr.line_to if started else cr.move_to)(px, py)
                started = True
            cr.stroke()


# ------------------------------------------------------------------ Plass per spill + spilloppdatering om natten
def storage_card(card):
    c, i = card(_t("💾 Plass per spill"), _t("De største spillene du ikke har spilt på et halvt år. «Avinstaller» "
                                            "spør Steam – lagrede spill i skyen blir liggende."))
    head = _dim("…")
    i.append(head)
    lst = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    i.append(lst)

    def show(r):
        _clear(lst)
        if isinstance(r, Exception):
            head.set_label(f"✗ {r}")
            return
        head.set_label(_t(f"Spillene bruker {r['total_gb']:.0f} GB. Ikke spilt på 6 måneder: {len(r['old'])} spill, "
                          f"{r['old_gb']:.0f} GB."))
        for g in r["old"][:12]:
            row = Gtk.Box(spacing=8)
            when = _t("aldri spilt") if g["days"] is None else _t(f"sist spilt for {g['days']} dager siden")
            row.append(Gtk.Label(label=f"{g['name']} · {g['gb']:.1f} GB · {when}", xalign=0, hexpand=True, wrap=True))
            b = Gtk.Button(label=_t("Avinstaller"))
            b.connect("clicked", lambda _b, a=g["appid"]: _toast(c, _t(S.uninstall(a))))
            row.append(b)
            lst.append(row)
    _bg(S.storage, show)
    if not S.IS_WIN:
        r = Gtk.Box(spacing=12)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        col.append(Gtk.Label(label=_t("Spilloppdateringer om natten"), xalign=0))
        col.append(_dim(_t("Steam laster ned spilloppdateringer bare i de 4 billigste strømtimene i natt, så de er klare når du vil "
                           "spille. Steam må være lukket når du slår det på.")))
        r.append(col)
        sw = Gtk.Switch(active=S.cfg()["night_updates"], valign=Gtk.Align.CENTER)
        busy = {"v": False}

        def tog(s, _p):
            if busy["v"]:
                return
            try:
                _toast(c, _t(S.night_updates(s.get_active())))
            except Exception as e:  # noqa: BLE001
                busy["v"] = True
                s.set_active(not s.get_active())
                busy["v"] = False
                _toast(c, f"✗ {e}")
        sw.connect("notify::active", tog)
        r.append(sw)
        i.append(r)
    return c


# ------------------------------------------------------------------ LAN-turnering
class TourneyCard(Gtk.Box):
    def __init__(self, card):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        c, self.i = card(_t("🏆 LAN-turnering"), _t("Lag og poengtavle for spillkvelden – deles med alle PC-ene og "
                                                    "mobilene hjemme (NAS-en). «Spillmodus på alle» gjør alle PC-ene "
                                                    "klare samtidig."))
        self.append(c)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.i.append(self.body)
        self.refresh()
        GLib.timeout_add_seconds(20, lambda: (self.get_mapped() and self.refresh(), True)[1])

    def refresh(self):
        _bg(S.t_load, self._show)

    def _show(self, d):
        _clear(self.body)
        if isinstance(d, Exception):
            d = {}
        if not d.get("teams"):
            if d.get("last"):
                self.body.append(_dim(_t(f"Sist: {d['last']['winner']} vant {d['last']['name']} "
                                         f"({d['last']['score']} poeng)")))
            g = Gtk.Grid(column_spacing=8, row_spacing=6)
            self.e_name = Gtk.Entry(placeholder_text=_t("Navn, f.eks. Fredagsturnering"), hexpand=True)
            self.e_game = Gtk.Entry(placeholder_text=_t("Spill, f.eks. CS2"))
            self.e_teams = Gtk.Entry(placeholder_text=_t("Lag eller spillere, med komma: Rød, Blå, Grønn"),
                                     hexpand=True)
            g.attach(self.e_name, 0, 0, 1, 1)
            g.attach(self.e_game, 1, 0, 1, 1)
            g.attach(self.e_teams, 0, 1, 2, 1)
            self.body.append(g)
            b = Gtk.Button(label=_t("Start turneringen"), halign=Gtk.Align.START)
            b.add_css_class("suggested-action")
            b.connect("clicked", self._new)
            self.body.append(b)
            return
        h = Gtk.Label(label=f"{d['name']}" + (f" · {d['game']}" if d.get("game") else ""), xalign=0)
        h.add_css_class("title-4")
        self.body.append(h)
        best = max(t["score"] for t in d["teams"])
        for n, t in enumerate(sorted(enumerate(d["teams"]), key=lambda x: -x[1]["score"])):
            idx, tm = t
            row = Gtk.Box(spacing=8)
            medal = "🥇" if tm["score"] == best and best else "  "
            row.append(Gtk.Label(label=f"{medal} {tm['name']}", xalign=0, hexpand=True))
            sc = Gtk.Label(label=str(tm["score"]))
            sc.add_css_class("title-3")
            row.append(sc)
            for lab, dl in (("−", -1), ("+1", 1)):
                b = Gtk.Button(label=lab)
                b.connect("clicked", lambda _b, x=idx, dd=dl: _bg(lambda: S.t_score(x, dd), self._show))
                row.append(b)
            self.body.append(row)
        bb = Gtk.Box(spacing=8)
        gm = Gtk.Button(label=_t("🎮 Spillmodus på alle"))
        gm.connect("clicked", lambda *_: _bg(S.t_gamemode_all, lambda r: _toast(self, str(r))))
        bb.append(gm)
        end = Gtk.Button(label=_t("Avslutt og kår vinner"))
        end.add_css_class("destructive-action")

        def finish(*_):
            def done(r):
                _toast(self, str(r))
                try:
                    import chat
                    chat.send("hjemme", str(r))
                except Exception:  # noqa: BLE001
                    pass
                self.refresh()
            _bg(S.t_end, done)
        end.connect("clicked", finish)
        bb.append(end)
        self.body.append(bb)

    def _new(self, *_):
        teams = [{"name": x.strip(), "players": []} for x in self.e_teams.get_text().split(",") if x.strip()]
        name, game = self.e_name.get_text(), self.e_game.get_text()
        _bg(lambda: S.t_new(name, game, teams), lambda r: _toast(self, f"✗ {r}") if isinstance(r, Exception)
            else self._show(r))
