"""«Installer app»-feltet som vises i en funksjon når programmet den trenger mangler.

    box.prepend(apps_ui.need("discord", on_done=self.refresh))

Feltet er usynlig når alt er på plass. Etter installasjonen forsvinner det, og on_done kalles (f.eks. for å
laste siden på nytt).
"""
import threading

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

import apps  # noqa: E402
import i18n  # noqa: E402

CSS = """
.ks-needapp { border-radius: 16px; padding: 12px 14px; margin-bottom: 10px;
  background: alpha(@accent_bg_color, .14); border: 1px solid alpha(@accent_bg_color, .45); }
.ks-needapp .ks-needapp-title { font-weight: 700; }
.ks-rank { font-weight: 800; font-size: 15px; min-width: 26px; min-height: 26px; border-radius: 99px;
  background: alpha(currentColor, .10); }
.ks-rank-1 { background: @accent_bg_color; color: @accent_fg_color; }
"""
_css_done = []


def _css():
    if not _css_done:
        _css_done.append(1)
        try:
            import theme
            theme.add_css(CSS, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 4)
        except Exception:  # noqa: BLE001
            pass


class Need(Gtk.Box):
    def __init__(self, feature, on_done=None, text=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        _css()
        self.feature, self.on_done, self.text = feature, on_done, text
        self.add_css_class("ks-needapp")
        self.set_visible(False)
        self.check()

    def check(self):
        def work():
            try:
                miss = apps.missing(self.feature)
            except Exception:  # noqa: BLE001
                miss = []
            GLib.idle_add(self._show, miss)
        threading.Thread(target=work, daemon=True).start()
        return False

    def _show(self, miss):
        while (ch := self.get_first_child()) is not None:
            self.remove(ch)
        self.set_visible(bool(miss))
        if not miss:
            return False
        best = miss[0][0]
        title = apps.TOP5.get(self.feature, {}).get("title", "")
        t = Gtk.Label(xalign=0, wrap=True, label="🧩 " + i18n.tr("Denne funksjonen trenger {name}").format(
            name=apps.APPS[best]["name"]))
        t.add_css_class("ks-needapp-title")
        self.append(t)
        if self.text:
            sub = Gtk.Label(xalign=0, wrap=True, label=i18n.tr(self.text))
            sub.add_css_class("dim-label")
            self.append(sub)
        msg = Gtk.Label(xalign=0, wrap=True)
        msg.add_css_class("caption")
        lst = ranked_list(self.feature, msg, best=best, on_installed=self.check)
        if title:
            h = Gtk.Label(xalign=0, label=i18n.tr("Topp 5 – {t}").format(t=i18n.tr(title).lower()), margin_top=4)
            h.add_css_class("caption-heading")
            self.append(h)
        self.append(lst)
        self.append(msg)
        return False

    def _install(self, btn, key, msg):
        for b in self._buttons():
            b.set_sensitive(False)
        spin = Gtk.Spinner(spinning=True)
        btn.get_parent().insert_child_after(spin, btn)

        def work():
            try:
                res, ok = apps.install(key, lambda t: GLib.idle_add(msg.set_label, i18n.tr(t))), True
            except Exception as e:  # noqa: BLE001
                res, ok = str(e), False
            GLib.idle_add(done, res, ok)

        def done(res, ok):
            spin.get_parent() and spin.get_parent().remove(spin)
            msg.set_label(res)
            for b in self._buttons():
                b.set_sensitive(True)
            if ok:
                self.check()
                if self.on_done:
                    GLib.timeout_add(800, lambda: (self.on_done(), False)[1])
            return False
        threading.Thread(target=work, daemon=True).start()

    def _buttons(self):
        out = []

        def walk(w):
            c = w.get_first_child()
            while c is not None:
                if isinstance(c, Gtk.Button):
                    out.append(c)
                walk(c)
                c = c.get_next_sibling()
        walk(self)
        return out


def need(feature, on_done=None, text=None):
    return Need(feature, on_done, text)


def ranked_list(feature, msg=None, best=None, on_installed=None):
    """De fem beste programmene for en funksjon, rangert, med Installer / Nettside / ✅."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    for rank, k in enumerate(apps.top5(feature), 1):
        a = apps.APPS[k]
        row = Gtk.Box(spacing=10)
        num = Gtk.Label(label=str(rank), valign=Gtk.Align.CENTER, width_chars=2)
        num.add_css_class("ks-rank")
        if rank == 1:
            num.add_css_class("ks-rank-1")
        row.append(num)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        tags = []
        if a.get("ks"):
            tags.append(i18n.tr("styres fra Kontrollsenter"))
        if a.get("builtin") == "windows":
            tags.append(i18n.tr("følger med Windows"))
        name = Gtk.Label(xalign=0, label=a["name"] + ("   ·  " + " · ".join(tags) if tags else ""))
        name.add_css_class("heading" if rank == 1 else "body")
        col.append(name)
        why = Gtk.Label(xalign=0, wrap=True, label=i18n.tr(a["why"]))
        why.add_css_class("dim-label")
        why.add_css_class("caption")
        col.append(why)
        row.append(col)
        right = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
        row.append(right)
        box.append(row)

        def fill(right=right, k=k, rank=rank):
            while (ch := right.get_first_child()) is not None:
                right.remove(ch)
            if apps.installed(k):
                ok = Gtk.Label(label="✅ " + i18n.tr("Installert"))
                ok.add_css_class("dim-label")
                right.append(ok)
            elif apps.can_install(k):
                b = Gtk.Button(label=i18n.tr("Installer"))
                b.add_css_class("pill")
                if (best and k == best) or (not best and rank == 1):
                    b.add_css_class("suggested-action")
                b.connect("clicked", _install_btn, k, msg, lambda: (fill(), on_installed and on_installed()))
                right.append(b)
            elif apps.APPS[k].get("url"):
                b = Gtk.Button(label=i18n.tr("Nettside"))
                b.add_css_class("pill")
                b.connect("clicked", lambda *_x, k=k: apps.open_url(k))
                right.append(b)
            else:
                hint = Gtk.Label(label=i18n.tr(apps.manual_hint(k)), wrap=True, max_width_chars=28)
                hint.add_css_class("caption")
                right.append(hint)
        fill()
    return box


def _install_btn(btn, key, msg, after):
    btn.set_sensitive(False)
    btn.set_label(i18n.tr("Installerer …"))

    def work():
        try:
            res, ok = apps.install(key), True
        except Exception as e:  # noqa: BLE001
            res, ok = str(e), False

        def done():
            if msg is not None:
                msg.set_label(res)
            if ok:
                after()
            else:
                btn.set_sensitive(True)
                btn.set_label(i18n.tr("Prøv igjen"))
            return False
        GLib.idle_add(done)
    threading.Thread(target=work, daemon=True).start()


def all_card():
    """Topp 5 for hver funksjon (Innstillinger → Generelt)."""
    _css()
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
    msg = Gtk.Label(xalign=0, wrap=True)
    msg.add_css_class("caption")
    box.append(msg)
    box.append(Gtk.Label(label=i18n.tr("Laster …"), xalign=0))

    def show(_rows):
        while (ch := box.get_last_child()) is not None and ch is not msg:
            box.remove(ch)
        for f, t in apps.TOP5.items():
            if f in ("medal", "moonlight") or not apps.top5(f):
                continue
            exp = Gtk.Expander(label=i18n.tr(t["title"]))
            exp.add_css_class("heading")
            exp.set_child(ranked_list(f, msg))
            miss = apps.missing(f)
            if miss:
                exp.set_label(i18n.tr(t["title"]) + "  ·  " + i18n.tr("mangler program"))
                exp.set_expanded(True)
            box.append(exp)
        return False
    threading.Thread(target=lambda: (apps.status(), GLib.idle_add(show, None)), daemon=True).start()
    return box
