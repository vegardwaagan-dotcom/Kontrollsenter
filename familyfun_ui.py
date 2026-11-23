"""Familie+ på Familie-siden: gjøremål i dag, spillkø, konkurranse, husprestasjoner, bursdager og innstillinger."""
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

import familyfun as F  # noqa: E402
import i18n  # noqa: E402


def _dim(t):
    lab = Gtk.Label(label=i18n.tr(t), xalign=0, wrap=True)
    lab.add_css_class("dim-label")
    lab.add_css_class("caption")
    return lab


def _h(t):
    lab = Gtk.Label(label=i18n.tr(t), xalign=0, margin_top=6)
    lab.add_css_class("heading")
    return lab


def _bg(fn, done):
    def work():
        try:
            r = fn()
        except Exception as e:  # noqa: BLE001
            r = e
        GLib.idle_add(lambda: (done(r), False)[1])
    threading.Thread(target=work, daemon=True).start()


class FamilyPlus(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.msg = _dim("")
        # 4 – gjøremål
        self.append(_h("✅ Gjøremål i dag"))
        self.append(_dim("Fra ukeplanen. Kryss av når det er gjort – en voksen godkjenner i appen, og du får "
                         "stjerner og ekstra spilletid."))
        self.chores = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.append(self.chores)
        # 43 – spillkø
        self.append(_h("⏳ Spillkø på denne PC-en"))
        self.queue_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.append(self.queue_box)
        qr = Gtk.Box(spacing=6)
        self.q_name = Gtk.Entry(placeholder_text=i18n.tr("Navn"), hexpand=True)
        qr.append(self.q_name)
        self.q_min = Gtk.SpinButton.new_with_range(5, 240, 5)
        self.q_min.set_value(30)
        qr.append(self.q_min)
        add = Gtk.Button(label=i18n.tr("Still i kø"))
        add.add_css_class("pill")
        add.connect("clicked", self._q_add)
        qr.append(add)
        self.append(qr)
        # 37 – konkurranse
        self.append(_h("🏆 Familiekonkurransen denne uka"))
        self.append(_dim("Poeng: stjerner + 3 for hver dag under spilletiden."))
        self.board = Gtk.Grid(column_spacing=18, row_spacing=4)
        self.append(self.board)
        pr = Gtk.Box(spacing=6)
        pr.append(Gtk.Label(label=i18n.tr("Premie"), xalign=0))
        self.prize = Gtk.Entry(text=F.cfg()["prize"], placeholder_text=i18n.tr("f.eks. velge fredagsfilm"),
                               hexpand=True)
        self.prize.connect("activate", lambda e: F.set_(prize=e.get_text().strip()))
        pr.append(self.prize)
        self.append(pr)
        # 48 – husprestasjoner
        self.append(_h("🏠 Husprestasjoner"))
        self.ach = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.append(self.ach)
        # 35 / 55 / 5 – innstillinger
        self.append(_h("⚙️ Innstillinger"))
        self._switch("Fri fra leksetid i dag", "Spill er lov i leksetiden resten av dagen.", F.is_free_today(),
                     lambda on: F.school_free_today(on))
        self._switch("Pausevarsel etter 3 timer", "Melding inni spillet om å ta en pause (på som standard der "
                                                  "familiekontroll er på).", F.break_on(),
                     lambda on: F.set_(break_on=on))
        self._switch("Leggetid som trapper ned", "30 min før: nattlys, varmt lys og beskjed · 15 min før: lavere "
                                                 "lyd · 5 min før: «lagre nå».", F.cfg()["winddown"],
                     lambda on: F.set_(winddown=on))
        # 70 – bursdager
        self.append(_h("🎂 Bursdager"))
        self.append(_dim("På bursdagen: konfetti, bursdagsfarger på RGB og ekstra spilletid i gave."))
        self.bdays = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.append(self.bdays)
        br = Gtk.Box(spacing=6)
        self.b_name = Gtk.Entry(placeholder_text=i18n.tr("Navn"), hexpand=True)
        br.append(self.b_name)
        self.b_date = Gtk.Entry(placeholder_text="DD.MM", width_chars=6)
        br.append(self.b_date)
        ba = Gtk.Button(label=i18n.tr("Legg til"))
        ba.add_css_class("pill")
        ba.connect("clicked", self._b_add)
        br.append(ba)
        self.append(br)
        self.append(self.msg)
        self.refresh()
        GLib.timeout_add_seconds(30, lambda: (self.get_mapped() and self.refresh(), True)[1])

    def _switch(self, title, sub, active, cb):
        r = Gtk.Box(spacing=12)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        col.append(Gtk.Label(label=i18n.tr(title), xalign=0))
        col.append(_dim(sub))
        r.append(col)
        sw = Gtk.Switch(active=active, valign=Gtk.Align.CENTER)
        sw.connect("notify::active", lambda w, _p: cb(w.get_active()))
        r.append(sw)
        self.append(r)

    @staticmethod
    def _clear(b):
        while (c := b.get_first_child()) is not None:
            b.remove(c)

    def refresh(self):
        _bg(lambda: (F.chores_today(), F.leaderboard(), F.house_achievements()), self._show)
        return False

    def _show(self, res):
        if isinstance(res, Exception):
            self.msg.set_label(f"Feil: {res}")
            return
        chores, board, ach = res
        self._clear(self.chores)
        if not chores:
            self.chores.append(_dim("Ingen gjøremål for deg i dag i ukeplanen."))
        for x in chores:
            r = Gtk.Box(spacing=8)
            r.append(Gtk.Label(label=f"{x['at']}  {x['text']}", xalign=0, hexpand=True, wrap=True))
            if x["done"]:
                r.append(Gtk.Label(label="✓ " + i18n.tr("sendt")))
            else:
                b = Gtk.Button(label=i18n.tr("Ferdig ✓"))
                b.add_css_class("pill")
                b.add_css_class("suggested-action")
                b.connect("clicked", lambda btn, iid=x["id"]: self._chore(btn, iid))
                r.append(b)
            self.chores.append(r)
        self._show_queue()
        self._clear(self.board)
        if not board:
            self.board.attach(_dim("Ingen poeng ennå"), 0, 0, 1, 1)
        for i, (n, pts, st, und) in enumerate(board):
            for j, t in enumerate((("🥇", "🥈", "🥉")[i] if i < 3 else f"{i + 1}.", n, f"{pts} p",
                                   f"{st} ⭐" + (f" · {und}/7 dager under grensen" if und is not None else ""))):
                lab = Gtk.Label(label=t, xalign=0)
                if j == 2:
                    lab.add_css_class("heading")
                self.board.attach(lab, j, i, 1, 1)
        self._clear(self.ach)
        for icon, title, done, prog in ach:
            r = Gtk.Box(spacing=8)
            r.append(Gtk.Label(label=icon if done else "▫️"))
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            t = Gtk.Label(label=i18n.tr(title), xalign=0)
            if not done:
                t.add_css_class("dim-label")
            col.append(t)
            col.append(_dim(prog))
            r.append(col)
            self.ach.append(r)
        self._clear(self.bdays)
        for b in F.cfg()["birthdays"]:
            r = Gtk.Box(spacing=8)
            d = str(b.get("date", ""))
            r.append(Gtk.Label(label=f"🎂 {b.get('name')}  ·  {d[-2:]}.{d[-5:-3]}", xalign=0, hexpand=True))
            rm = Gtk.Button(icon_name="user-trash-symbolic")
            rm.add_css_class("flat")
            rm.connect("clicked", lambda _b, bb=b: (F.set_(birthdays=[x for x in F.cfg()["birthdays"] if x != bb]),
                                                    self.refresh()))
            r.append(rm)
            self.bdays.append(r)

    def _show_queue(self):
        self._clear(self.queue_box)
        q = F.queue()
        if not q:
            self.queue_box.append(_dim("Ingen i kø."))
            return
        for i, x in enumerate(q):
            r = Gtk.Box(spacing=8)
            if i == 0 and x.get("start"):
                left = max(0, int((x["start"] + x["minutes"] * 60 - time.time()) // 60))
                txt = f"▶ {x['name']} – {left} min igjen"
            else:
                txt = f"{i + 1}. {x['name']} ({x['minutes']} min)"
            r.append(Gtk.Label(label=txt, xalign=0, hexpand=True))
            if i == 0:
                nx = Gtk.Button(label=i18n.tr("Neste"))
                nx.add_css_class("flat")
                nx.connect("clicked", lambda *_: (F.queue_next(), self._show_queue()))
                r.append(nx)
            self.queue_box.append(r)
        cl = Gtk.Button(label=i18n.tr("Tøm køen"), halign=Gtk.Align.START)
        cl.add_css_class("flat")
        cl.connect("clicked", lambda *_: (F.queue_clear(), self._show_queue()))
        self.queue_box.append(cl)

    def _q_add(self, *_):
        n = self.q_name.get_text().strip()
        if not n:
            return
        F.queue_add(n, int(self.q_min.get_value()))
        self.q_name.set_text("")
        self._show_queue()

    def _chore(self, btn, iid):
        btn.set_sensitive(False)
        _bg(lambda: F.chore_done(iid), lambda r: (self.msg.set_label(str(r)), self.refresh()))

    def _b_add(self, *_):
        n, d = self.b_name.get_text().strip(), self.b_date.get_text().strip()
        try:
            dd, mm = (int(x) for x in d.replace("/", ".").split(".")[:2])
            assert 1 <= dd <= 31 and 1 <= mm <= 12 and n
        except (ValueError, AssertionError):
            self.msg.set_label(i18n.tr("Skriv navn og dato som DD.MM"))
            return
        F.set_(birthdays=F.cfg()["birthdays"] + [{"name": n, "date": f"{mm:02d}-{dd:02d}", "pc": "*"}])
        self.b_name.set_text("")
        self.b_date.set_text("")
        self.refresh()


_CONF_CSS = """
.ks-confetti { font-size: 34px; }
@keyframes ks-conf-fall { from { margin-top: -200px; opacity: 1; } to { margin-top: 520px; opacity: 0; } }
.ks-confetti label { animation: ks-conf-fall 3.2s ease-in 1; }
"""


def confetti(win, name, minutes):
    try:
        import theme
        theme.add_css(_CONF_CSS)
    except Exception:  # noqa: BLE001
        pass
    import random
    dlg = Adw.Dialog(title=i18n.tr("Gratulerer med dagen!"), content_width=520, content_height=440)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, valign=Gtk.Align.CENTER)
    rain = Gtk.Box(spacing=10, halign=Gtk.Align.CENTER)
    rain.add_css_class("ks-confetti")
    for _ in range(9):
        rain.append(Gtk.Label(label=random.choice("🎉🎊🎈✨🥳🎂🍰")))
    box.append(rain)
    t = Gtk.Label(label=f"🎂 {i18n.tr('Gratulerer med dagen')}, {name}!")
    t.add_css_class("title-1")
    box.append(t)
    box.append(Gtk.Label(label=i18n.tr("Du har fått {m} min ekstra spilletid i gave 🎁").replace("{m}", str(minutes))))
    dlg.set_child(box)
    if win is not None and win.get_mapped():
        dlg.present(win)
