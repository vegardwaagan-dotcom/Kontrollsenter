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
.ks-useapp { border-radius: 16px; padding: 10px 14px; margin-bottom: 10px; background: alpha(currentColor, .05);
  border: 1px solid alpha(currentColor, .10); }
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
    """Programfeltet øverst i en funksjon.

    * Mangler programmet: «Denne funksjonen trenger …» + topp 5 med Installer/Nettside.
    * Ellers: «Program: [velger] Åpne» med de installerte programmene, og «Flere programmer» (topp 5).
    on_change(nøkkel) kalles når du bytter program; on_done når et program er installert.
    """

    def __init__(self, feature, on_done=None, text=None, on_change=None, picker=True):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        _css()
        self.feature, self.on_done, self.text, self.on_change, self.picker = feature, on_done, text, on_change, picker
        self.set_visible(False)
        self.check()

    def check(self):
        def work():
            try:
                miss = apps.missing(self.feature)
                ch = apps.choices(self.feature)
                use = apps.get_use(self.feature)
            except Exception:  # noqa: BLE001
                miss, ch, use = [], [], None
            GLib.idle_add(self._show, miss, ch, use)
        threading.Thread(target=work, daemon=True).start()
        return False

    def _clear(self):
        while (ch := self.get_first_child()) is not None:
            self.remove(ch)
        for c in ("ks-needapp", "ks-useapp"):
            self.remove_css_class(c)

    def _show(self, miss, ch, use):
        self._clear()
        multi = self.feature in apps.MULTI
        if miss:
            self._show_missing(miss)
        elif self.picker and (len(ch) >= 2 or (ch and not apps.APPS[ch[0]].get("ks"))):
            self._show_picker(ch, use, multi)
        else:
            self.set_visible(False)
            return False
        self.set_visible(True)
        return False

    def _show_missing(self, miss):
        self.add_css_class("ks-needapp")
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
        if title:
            h = Gtk.Label(xalign=0, label=i18n.tr("Topp 5 – {t}").format(t=i18n.tr(title).lower()), margin_top=4)
            h.add_css_class("caption-heading")
            self.append(h)
        self.append(ranked_list(self.feature, msg, best=best, on_installed=self._installed))
        self.append(msg)

    def _installed(self):
        self.check()
        if self.on_done:
            GLib.timeout_add(800, lambda: (self.on_done(), False)[1])

    def _show_picker(self, ch, use, multi):
        self.add_css_class("ks-useapp")
        row = Gtk.Box(spacing=10)
        lab = Gtk.Label(label=i18n.tr("Vis spill fra") if multi else i18n.tr("Program"), xalign=0)
        lab.add_css_class("heading")
        row.append(lab)
        keys = ([None] if multi else []) + ch
        names = [(i18n.tr("Alle") if k is None else apps.APPS[k]["name"]) for k in keys]
        dd = Gtk.DropDown.new_from_strings(names)
        dd.set_selected(keys.index(use) if use in keys else 0)
        dd.set_hexpand(not multi)
        row.append(dd)
        if multi:
            row.append(Gtk.Box(hexpand=True))
        open_b = Gtk.Button(label=i18n.tr("Åpne"), valign=Gtk.Align.CENTER)
        open_b.add_css_class("pill")
        row.append(open_b)
        self.append(row)
        note = Gtk.Label(xalign=0, wrap=True)
        note.add_css_class("dim-label")
        note.add_css_class("caption")
        self.append(note)

        def refresh_note(k):
            open_b.set_visible(k is not None)
            note.set_visible(k is not None)
            if k is None:
                return
            a = apps.APPS[k]
            note.set_label(i18n.tr("Styres her i Kontrollsenter.") if a.get("ks") else
                           i18n.tr("Kontrollsenter kan ikke styre {n} – innstillingene gjøres i {n} (trykk «Åpne»).")
                           .format(n=a["name"]))

        def changed(d, _p):
            k = keys[d.get_selected()]
            apps.set_use(self.feature, k)
            refresh_note(k)
            if self.on_change:
                self.on_change(k)
        dd.connect("notify::selected", changed)
        open_b.connect("clicked", lambda *_: keys[dd.get_selected()] and apps.launch(keys[dd.get_selected()]))
        refresh_note(keys[dd.get_selected()])
        more = Gtk.Expander(label=i18n.tr("Flere programmer – topp 5"))
        more.add_css_class("caption")
        msg = Gtk.Label(xalign=0, wrap=True)
        msg.add_css_class("caption")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=6)
        box.append(ranked_list(self.feature, msg, on_installed=self.check))
        box.append(msg)
        more.set_child(box)
        self.append(more)


def need(feature, on_done=None, text=None, on_change=None, picker=True):
    return Need(feature, on_done, text, on_change, picker)


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
