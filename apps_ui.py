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
        for group in miss:
            best = group[0]
            a = apps.APPS[best]
            t = Gtk.Label(xalign=0, wrap=True,
                          label="🧩 " + i18n.tr("Denne funksjonen trenger {name}").format(name=a["name"]))
            t.add_css_class("ks-needapp-title")
            self.append(t)
            sub = Gtk.Label(xalign=0, wrap=True, label=i18n.tr(self.text or a["why"]))
            sub.add_css_class("dim-label")
            self.append(sub)
            row = Gtk.Box(spacing=8)
            msg = Gtk.Label(xalign=0, wrap=True, hexpand=True)
            msg.add_css_class("caption")
            for k in group:
                if not apps.can_install(k):
                    continue
                b = Gtk.Button(label=i18n.tr("Installer {name}").format(name=apps.APPS[k]["name"]))
                if k == best:
                    b.add_css_class("suggested-action")
                b.add_css_class("pill")
                b.connect("clicked", self._install, k, msg)
                row.append(b)
            if not any(apps.can_install(k) for k in group):
                msg.set_label(i18n.tr(apps.manual_hint(best)))
            row.append(msg)
            self.append(row)
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


def all_card():
    """Kort med alle programmene Kontrollsenter kan bruke (Innstillinger → Generelt)."""
    _css()
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    lst = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    box.append(lst)

    def fill(rows):
        while (ch := lst.get_first_child()) is not None:
            lst.remove(ch)
        for r in rows:
            row = Gtk.Box(spacing=10)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            col.append(Gtk.Label(label=("✅ " if r["installed"] else "⬜ ") + r["name"], xalign=0))
            s = Gtk.Label(label=i18n.tr(r["why"]), xalign=0, wrap=True)
            s.add_css_class("dim-label")
            s.add_css_class("caption")
            col.append(s)
            row.append(col)
            if not r["installed"] and r["can_install"]:
                b = Gtk.Button(label=i18n.tr("Installer"), valign=Gtk.Align.CENTER)
                b.add_css_class("pill")

                def go(btn, k=r["key"]):
                    btn.set_sensitive(False)
                    btn.set_label(i18n.tr("Installerer …"))

                    def work():
                        try:
                            apps.install(k)
                        except Exception as e:  # noqa: BLE001
                            GLib.idle_add(btn.set_label, str(e)[:60])
                            return
                        GLib.idle_add(load)
                    threading.Thread(target=work, daemon=True).start()
                b.connect("clicked", go)
                row.append(b)
            lst.append(row)
        return False

    def load():
        threading.Thread(target=lambda: GLib.idle_add(fill, apps.status()), daemon=True).start()
        return False
    load()
    return box
