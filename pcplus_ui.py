"""Kortene for PC-runde 4 (Vedlikehold › System): PC-ens helse, strømbudsjett, stresstest og sammenligning – og
«Stille nå» (Innstillinger › Automatikk)."""
import threading

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

import i18n  # noqa: E402
import pcplus as P  # noqa: E402

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


def _clear(b):
    while (c := b.get_first_child()) is not None:
        b.remove(c)


def _open(w, page):
    win = w.get_root()
    if hasattr(win, "ensure_lazy"):
        win.ensure_lazy(page)
    win.stack.set_visible_child_name(page)


# ------------------------------------------------------------------ helse
def health_card(card):
    c, i = card(_t("❤️ PC-ens helse"), _t("Ett tall for hvordan PC-en har det: temperaturer, diskene, ledig plass, "
                                         "krasj, oppdateringer, støv og sikkerhetskopi."))
    top = Gtk.Box(spacing=16)
    score = Gtk.Label(label="…")
    score.add_css_class("title-1")
    top.append(score)
    word = Gtk.Label(xalign=0, hexpand=True)
    word.add_css_class("title-3")
    top.append(word)
    i.append(top)
    lst = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    i.append(lst)
    bios = _dim()
    i.append(bios)

    def show(r):
        if isinstance(r, Exception):
            word.set_label(f"✗ {r}")
            return
        h, b = r
        score.set_label(f"{h['score']}")
        word.set_label(_t(h["word"]) + " / 100")
        _clear(lst)
        if not h["items"]:
            lst.append(Gtk.Label(label=_t("✅ Ingenting å utsette – alt ser bra ut."), xalign=0))
        icon = {"bad": "❌", "warn": "⚠️", "info": "ℹ️"}
        for x in h["items"]:
            row = Gtk.Box(spacing=8)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            col.append(Gtk.Label(label=f"{icon.get(x['level'], '•')}  {_t(x['title'])}  (−{x['minus']})", xalign=0,
                                 wrap=True))
            if x.get("detail"):
                col.append(_dim(_t(x["detail"])))
            row.append(col)
            if x.get("page"):
                bt = Gtk.Button(label=_t("Fiks →"), valign=Gtk.Align.CENTER)
                bt.connect("clicked", lambda _b, p=x["page"]: _open(c, p))
                row.append(bt)
            lst.append(row)
        if b:
            bios.set_label(_t(b["text"]))
            if not getattr(bios, "_lnk", None):
                bios._lnk = Gtk.LinkButton(uri=b["url"], label=_t("Se etter ny BIOS hos produsenten"),
                                           halign=Gtk.Align.START)
                i.append(bios._lnk)
    _bg(lambda: (P.health(), P.bios()), show)
    return c


# ------------------------------------------------------------------ strømbudsjett
def budget_card(card):
    c, i = card(_t("💡 Strømbudsjett"), _t("Sett hvor mye PC-en får bruke på strøm i måneden. Du får varsel ved 80 % "
                                          "og når det ser ut til å gå over."))
    row = Gtk.Box(spacing=8)
    row.append(Gtk.Label(label=_t("Kr per måned (0 = av)"), xalign=0, hexpand=True))
    sp = Gtk.SpinButton.new_with_range(0, 5000, 25)
    sp.set_value(P.cfg()["budget_kr"])
    row.append(sp)
    i.append(row)
    bar = Gtk.LevelBar(min_value=0, max_value=1)
    bar.add_offset_value("low", 0.8)
    bar.add_offset_value("high", 0.95)
    bar.add_offset_value("full", 1.0)
    i.append(bar)
    txt = _dim("…")
    i.append(txt)

    def show(r):
        if isinstance(r, Exception):
            txt.set_label(f"✗ {r}")
            return
        txt.set_label(_t(r["text"]))
        bar.set_visible(bool(r["budget"]))
        if r["budget"]:
            bar.set_value(min(1.0, r["month_kr"] / r["budget"]))
    tid = {"t": None}

    def changed(*_):
        if tid["t"]:
            GLib.source_remove(tid["t"])

        def go():
            tid["t"] = None
            P.set_(budget_kr=int(sp.get_value()), budget_warned="")
            _bg(lambda: P.budget(c.get_root()), show)
            return False
        tid["t"] = GLib.timeout_add(600, go)
    sp.connect("value-changed", changed)
    _bg(lambda: P.budget(c.get_root()), show)
    return c


# ------------------------------------------------------------------ stresstest
class StressCard(Gtk.Box):
    def __init__(self, card):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        c, i = card(_t("🔥 Stresstest"), _t("Prosessoren og minnet på full guffe i noen minutter, mens temperaturen og "
                                           "klokkefrekvensen logges. Regnestykkene sjekkes – feil betyr at PC-en er "
                                           "ustabil. Fint etter overklokking, ny kjølepasta eller ny kjøler."))
        self.append(c)
        row = Gtk.Box(spacing=8)
        self.dd = Gtk.DropDown.new_from_strings([_t("2 minutter"), _t("5 minutter"), _t("15 minutter")])
        self.dd.set_selected(1)
        row.append(self.dd)
        self.go = Gtk.Button(label=_t("Start stresstest"))
        self.go.add_css_class("suggested-action")
        self.go.connect("clicked", self._start)
        row.append(self.go)
        self.stop = Gtk.Button(label=_t("Stopp"), sensitive=False)
        self.stop.connect("clicked", lambda *_: P.STRESS.update(stop=True))
        row.append(self.stop)
        i.append(row)
        self.area = Gtk.DrawingArea(content_height=110, hexpand=True)
        self.area.set_draw_func(self._draw)
        i.append(self.area)
        self.msg = Gtk.Label(xalign=0, wrap=True)
        i.append(self.msg)

    def _start(self, *_):
        mins = (2, 5, 15)[self.dd.get_selected()]
        self.go.set_sensitive(False)
        self.stop.set_sensitive(True)
        self.msg.set_label(_t("Kjører – PC-en blir varm og viftene går opp. Det er meningen."))

        def prog(t, tot, ct):
            GLib.idle_add(lambda: (self.msg.set_label(_t(f"{int(t // 60)}:{int(t % 60):02d} av {tot // 60:.0f}:00 · "
                                                         f"CPU {ct or '?'} °C")), self.area.queue_draw(), False)[2])

        def done(r):
            self.go.set_sensitive(True)
            self.stop.set_sensitive(False)
            if isinstance(r, Exception):
                self.msg.set_label(f"✗ {r}")
                return
            self.msg.set_label(_t(f"{r['verdict']}\nMaks {r['max_temp'] or '?'} °C · snitt {r['avg_temp'] or '?'} °C · "
                                  f"{r['errors']} regnefeil · {r['minutes']} min"))
            self.area.queue_draw()
        _bg(lambda: P.stress(mins, prog), done)

    def _draw(self, _a, cr, w, h):
        log = P.STRESS["log"]
        cr.set_source_rgba(0.5, 0.5, 0.6, 0.1)
        cr.rectangle(0, 0, w, h)
        cr.fill()
        pts = [(x[0], x[1]) for x in log if x[1]]
        if len(pts) < 2:
            return
        t1 = max(p[0] for p in pts) or 1
        for lim, col in ((95, (0.9, 0.2, 0.2, 0.5)), (85, (0.95, 0.65, 0.1, 0.4))):
            y = h - (lim - 30) / 70 * h
            cr.set_source_rgba(*col)
            cr.move_to(0, y)
            cr.line_to(w, y)
            cr.stroke()
        cr.set_source_rgb(0.36, 0.55, 1)
        cr.set_line_width(2)
        for n, (t, v) in enumerate(pts):
            x, y = t / t1 * w, h - (max(30, min(100, v)) - 30) / 70 * h
            (cr.line_to if n else cr.move_to)(x, y)
        cr.stroke()


# ------------------------------------------------------------------ sammenligning
def compare_card(card):
    c, i = card(_t("📊 Sammenlign med de andre PC-ene"), _t("Ytelsestesten her mot de andre PC-ene i huset. Kjør "
                                                           "«Ytelsestest» på hver PC først."))
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    i.append(box)

    def show(r):
        _clear(box)
        if isinstance(r, Exception) or not r.get("mine"):
            box.append(_dim(_t("Kjør «Ytelsestest» over først.")))
            return
        rows = [{"name": _t("Denne PC-en"), **r["mine"]}] + r["others"]
        best = {k: max((x.get(k) or 0) for x in rows) or 1 for k in ("cpu1", "cpuN", "mem_gbs", "disk_w")}
        g = Gtk.Grid(column_spacing=18, row_spacing=4)
        for col, head in enumerate((_t("PC"), _t("Én kjerne"), _t("Alle kjerner"), _t("Minne"), _t("Disk"))):
            lb = Gtk.Label(label=head, xalign=0)
            lb.add_css_class("dim-label")
            g.attach(lb, col, 0, 1, 1)
        for n, x in enumerate(rows, 1):
            g.attach(Gtk.Label(label=x["name"], xalign=0), 0, n, 1, 1)
            for col, k, unit in ((1, "cpu1", ""), (2, "cpuN", ""), (3, "mem_gbs", " GB/s"), (4, "disk_w", " MB/s")):
                v = x.get(k)
                pct = round((v or 0) / best[k] * 100)
                lb = Gtk.Label(label=f"{v}{unit} ({pct} %)" if v else "–", xalign=0)
                if pct == 100:
                    lb.add_css_class("accent")
                g.attach(lb, col, n, 1, 1)
        box.append(g)
        if not r["others"]:
            box.append(_dim(_t("Ingen andre PC-er har kjørt ytelsestesten ennå (krever Kontrollsenter 0.99.34 der).")))
    _bg(P.compare_pcs, show)
    return c


# ------------------------------------------------------------------ stille nå
def quiet_row():
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    h = Gtk.Label(label=_t("Stille nå"), xalign=0)
    h.add_css_class("heading")
    box.append(h)
    box.append(_dim(_t("Rolige vifter og lavere effekt i noen timer – f.eks. når noen sover i rommet ved siden av. "
                       "Bruker de samme innstillingene som «Stille om natten».")))
    row = Gtk.Box(spacing=6)
    st = _dim()

    def upd():
        m = P.quiet_left()
        st.set_label(_t(f"På – {m // 60} t {m % 60} min igjen") if m else _t("Av"))
        return True
    for lab, hrs in (("1 time", 1), ("2 timer", 2), ("4 timer", 4), ("Av", 0)):
        b = Gtk.Button(label=_t(lab))
        b.connect("clicked", lambda _b, x=hrs: (P.quiet_for(x), upd()))
        row.append(b)
    row.append(st)
    box.append(row)
    upd()
    GLib.timeout_add_seconds(60, upd)
    return box
