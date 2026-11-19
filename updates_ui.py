"""Knappene for «Oppdater alt» og bryteren for automatikk – i Innstillinger, på Oversikt, på PC-er-siden og i
hver funksjon som bruker et program som kan oppdateres."""
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk  # noqa: E402

import i18n  # noqa: E402
import updates as U  # noqa: E402

_CSS = """
.ks-upd-bar { padding: 8px 14px; border-radius: 14px; background: alpha(@accent_bg_color, 0.10); }
.ks-upd-bar.ks-upd-ok { background: alpha(@window_fg_color, 0.04); }
.ks-upd-strip { padding: 6px 12px; border-radius: 12px; background: alpha(@accent_bg_color, 0.10); }
.ks-upd-count { font-weight: 800; }
"""
_DONE = []


def _css():
    if _DONE:
        return
    _DONE.append(True)
    try:
        import theme
        theme.add_css(_CSS)
    except Exception:  # noqa: BLE001
        pass


def _bg(fn, done):
    def work():
        try:
            r = fn()
        except Exception as e:  # noqa: BLE001
            r = e
        GLib.idle_add(lambda: (done(r), False)[1])
    threading.Thread(target=work, daemon=True).start()


def _icon(count):
    return "✅" if count == 0 else "🔄" if count > 0 else "❔"


def auto_row(on_toggle=None):
    """Bryteren «Automatisk oppdatering og opprydding» (samme overalt)."""
    row = Gtk.Box(spacing=10)
    col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
    t = Gtk.Label(label=i18n.tr("Automatisk oppdatering og opprydding"), xalign=0)
    col.append(t)
    sub = Gtk.Label(xalign=0, wrap=True, label=i18n.tr(
        "Av: ingen automatiske sjekker, oppdateringer eller diskopprydding – du gjør det selv med «Oppdater alt»."))
    sub.add_css_class("dim-label")
    sub.add_css_class("caption")
    col.append(sub)
    row.append(col)
    sw = Gtk.Switch(active=U.auto_on(), valign=Gtk.Align.CENTER)

    def toggled(w, _p):
        if w.get_active() != U.auto_on():
            U.set_auto(w.get_active())
            if on_toggle:
                on_toggle(w.get_active())
    sw.connect("notify::active", toggled)
    U.on_change(lambda: sw.get_active() != U.auto_on() and sw.set_active(U.auto_on()))
    row.append(sw)
    return row


class UpdatesCard(Gtk.Box):
    """Fullt oppdateringskort (Innstillinger → Oppdateringer)."""

    def __init__(self, win_getter):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        _css()
        self.win_getter = win_getter
        top = Gtk.Box(spacing=10)
        self.head = Gtk.Label(xalign=0, hexpand=True, wrap=True, label=i18n.tr("Ser etter oppdateringer …"))
        self.head.add_css_class("heading")
        top.append(self.head)
        self.check_b = Gtk.Button(label=i18n.tr("Se etter"), valign=Gtk.Align.CENTER)
        self.check_b.add_css_class("pill")
        self.check_b.connect("clicked", lambda *_: self.refresh(True))
        top.append(self.check_b)
        self.all_b = Gtk.Button(label=i18n.tr("Oppdater alt"), valign=Gtk.Align.CENTER)
        self.all_b.add_css_class("pill")
        self.all_b.add_css_class("suggested-action")
        self.all_b.connect("clicked", self._all)
        top.append(self.all_b)
        self.append(top)
        self.rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.append(self.rows)
        self.msg = Gtk.Label(xalign=0, wrap=True, visible=False)
        self.msg.add_css_class("caption")
        self.append(self.msg)
        self.append(Gtk.Separator())
        self.append(auto_row())
        U.on_change(lambda: self.get_mapped() and self._show(U.cached()))
        self._show(U.cached())
        self.refresh(False)

    def refresh(self, force):
        self.check_b.set_sensitive(False)
        if force or not U.cached():
            self.head.set_label(i18n.tr("Ser etter oppdateringer …"))
        _bg(lambda: U.status(refresh=force), self._show)

    def _show(self, st):
        self.check_b.set_sensitive(True)
        if isinstance(st, Exception):
            self.head.set_label(i18n.tr("Kunne ikke sjekke: ") + str(st)[:80])
            return False
        if not st:
            return False
        n = U.total(st)
        self.head.set_label(i18n.tr("Alt er oppdatert ✓") if n == 0 else
                            i18n.tr("{n} oppdateringer er klare").replace("{n}", str(n)))
        self.all_b.set_sensitive(n > 0 and not U.running())
        if U.running():
            self.all_b.set_label(i18n.tr("Oppdaterer …"))
        else:
            self.all_b.set_label(i18n.tr("Oppdater alt"))
        while (c := self.rows.get_first_child()) is not None:
            self.rows.remove(c)
        for s in st:
            r = Gtk.Box(spacing=10)
            ic = Gtk.Label(label=_icon(s["count"]), valign=Gtk.Align.START)
            r.append(ic)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            col.append(Gtk.Label(label=i18n.tr(s["name"]), xalign=0))
            d = Gtk.Label(label=i18n.tr(s["detail"]), xalign=0, wrap=True)
            d.add_css_class("dim-label")
            d.add_css_class("caption")
            col.append(d)
            r.append(col)
            self.rows.append(r)
        return False

    def _all(self, *_):
        win = self.win_getter()
        self.all_b.set_sensitive(False)
        self.all_b.set_label(i18n.tr("Oppdaterer …"))

        def done(results):
            bad = [r for r in results if not r[1]]
            self.msg.set_label("\n".join(f"{'✓' if ok else '✗'} {i18n.tr(n)}: {m}" for n, ok, m in results))
            self.msg.set_visible(True)
            if bad:
                self.msg.add_css_class("error")
            self.refresh(False)
        if not U.update_all(win, on_done=done):
            self.msg.set_label(i18n.tr("En oppdatering pågår allerede"))
            self.msg.set_visible(True)


class OverviewBar(Gtk.Box):
    """Linjen på Oversikt: «🔄 3 oppdateringer · [Oppdater alt]» og automatikk av/på."""

    def __init__(self, win):
        super().__init__(spacing=10)
        _css()
        self.win = win
        self.add_css_class("ks-upd-bar")
        self.set_margin_bottom(4)
        self.lab = Gtk.Label(xalign=0, hexpand=True, ellipsize=3, label="")
        self.append(self.lab)
        self.auto = Gtk.Switch(valign=Gtk.Align.CENTER, active=U.auto_on())
        self.auto.set_tooltip_text(i18n.tr("Automatisk oppdatering og opprydding. Av = du gjør det selv med "
                                           "«Oppdater alt»."))
        self.auto.connect("notify::active", lambda w, _p: w.get_active() != U.auto_on() and U.set_auto(w.get_active()))
        alab = Gtk.Label(label=i18n.tr("Automatisk"), valign=Gtk.Align.CENTER)
        alab.add_css_class("dim-label")
        self.append(alab)
        self.append(self.auto)
        self.check = Gtk.Button(icon_name="view-refresh-symbolic", valign=Gtk.Align.CENTER,
                                tooltip_text=i18n.tr("Se etter oppdateringer nå"))
        self.check.add_css_class("flat")
        self.check.connect("clicked", lambda *_: self.refresh(True))
        self.append(self.check)
        self.btn = Gtk.Button(label=i18n.tr("Oppdater alt"), valign=Gtk.Align.CENTER)
        self.btn.add_css_class("pill")
        self.btn.add_css_class("suggested-action")
        self.btn.connect("clicked", self._all)
        self.append(self.btn)
        U.on_change(self._sync)
        self._show(U.cached())
        GLib.timeout_add_seconds(8, lambda: (self.refresh(False), False)[1])
        GLib.timeout_add_seconds(1800, lambda: (self.get_mapped() and U.auto_on() and self.refresh(False), True)[1])

    def _sync(self):
        if self.auto.get_active() != U.auto_on():
            self.auto.set_active(U.auto_on())
        self._show(U.cached())

    def refresh(self, force):
        if not force and not U.auto_on() and U.cached():
            return
        if not force and not U.auto_on():                  # manuelt: ingen automatisk sjekk
            self._show([])
            return
        self.check.set_sensitive(False)
        if force:
            self.lab.set_label(i18n.tr("Ser etter oppdateringer …"))
        _bg(lambda: U.status(refresh=force), self._show)

    def _show(self, st):
        self.check.set_sensitive(True)
        if isinstance(st, Exception):
            st = []
        if U.running():
            self.lab.set_label("🔄 " + i18n.tr("Oppdaterer …"))
            self.btn.set_sensitive(False)
            return False
        n = U.total(st) if st else 0
        if not st:
            self.lab.set_label(i18n.tr("Oppdateringer: trykk ⟳ for å se etter") if not U.auto_on() else
                               i18n.tr("Ser etter oppdateringer …"))
        elif n == 0:
            self.lab.set_label("✅ " + i18n.tr("Alt er oppdatert"))
        else:
            names = ", ".join(i18n.tr(s["name"]) for s in st if s["count"] > 0)
            self.lab.set_label("🔄 " + i18n.tr("{n} oppdateringer").replace("{n}", str(n)) + " · " + names)
        self.btn.set_visible(n > 0 or not st)
        self.btn.set_sensitive(True)
        (self.remove_css_class if n > 0 else self.add_css_class)("ks-upd-ok")
        return False

    def _all(self, *_):
        self.btn.set_sensitive(False)
        self.lab.set_label("🔄 " + i18n.tr("Oppdaterer …"))
        U.update_all(self.win, on_done=lambda _r: self._show(U.cached()))


class AppStrip(Gtk.Box):
    """I en funksjon: «Oppdatering klar for Discord · [Oppdater]» – bare når et program den bruker har en."""

    def __init__(self, feature):
        super().__init__(spacing=10, visible=False)
        _css()
        self.feature = feature
        self.add_css_class("ks-upd-strip")
        self.lab = Gtk.Label(xalign=0, hexpand=True, wrap=True)
        self.append(self.lab)
        self.btn = Gtk.Button(label=i18n.tr("Oppdater"), valign=Gtk.Align.CENTER)
        self.btn.add_css_class("pill")
        self.btn.add_css_class("suggested-action")
        self.btn.connect("clicked", self._go)
        self.append(self.btn)
        self.ids = []
        U.on_change(self.check)
        self.check()

    def _ids_for(self, upd):
        import apps
        keys = set(apps.top5(self.feature)) | set(apps.choices(self.feature))
        out = []
        for k in keys:
            a = apps.APPS.get(k) or {}
            pid = a.get("winget") if U.IS_WIN else a.get("flatpak")
            if pid and pid in upd:
                out.append((pid, a.get("name", upd[pid])))
        return out

    def check(self):
        def work():
            if not U.auto_on() and not U.cached():
                return []
            return self._ids_for(U.app_updates())
        _bg(work, self._show)
        return False

    def _show(self, items):
        if isinstance(items, Exception) or not items:
            self.set_visible(False)
            return False
        self.ids = [i for i, _n in items]
        self.lab.set_label("🔄 " + i18n.tr("Oppdatering klar for {n}").replace("{n}", ", ".join(n for _i, n in items)))
        self.btn.set_sensitive(True)
        self.btn.set_label(i18n.tr("Oppdater"))
        self.set_visible(True)
        return False

    def _go(self, *_):
        import progress as P
        self.btn.set_sensitive(False)
        self.btn.set_label(i18n.tr("Oppdaterer …"))
        ids = list(self.ids)

        def work():
            t = P.begin("Oppdaterer " + self.lab.get_label().split(" for ", 1)[-1], "")
            ok, msg = U.update_ids(ids, t)
            t.done(msg, ok)
            return ok, msg

        def done(r):
            ok, msg = r if isinstance(r, tuple) else (False, str(r))
            if ok:
                self.lab.set_label("✅ " + i18n.tr("Oppdatert"))
                self.btn.set_visible(False)
                GLib.timeout_add_seconds(4, lambda: (self.set_visible(False), self.btn.set_visible(True), False)[2])
            else:
                self.lab.set_label("✗ " + msg)
                self.btn.set_sensitive(True)
                self.btn.set_label(i18n.tr("Prøv igjen"))
        _bg(work, done)
