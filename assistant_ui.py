"""PC-assistenten i vinduet: «Hvorfor er PC-en treg?», diskvakt, SSD-levetid, varmere enn vanlig og ukens rapport."""
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

import i18n  # noqa: E402

ICON = {"ok": "✅", "info": "ℹ️", "warn": "⚠️", "error": "❌"}


def _bg(fn, done):
    def work():
        try:
            r = fn()
        except Exception as e:  # noqa: BLE001
            r = e
        GLib.idle_add(lambda: (done(r), False)[1])
    threading.Thread(target=work, daemon=True).start()


def findings_box(findings):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    for f in findings:
        r = Gtk.Box(spacing=10)
        r.append(Gtk.Label(label=ICON.get(f.level, "•"), valign=Gtk.Align.START))
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        t = Gtk.Label(label=i18n.tr(f.title), xalign=0, wrap=True)
        t.add_css_class("heading" if f.level in ("warn", "error") else "body")
        col.append(t)
        d = Gtk.Label(label=i18n.tr(f.detail), xalign=0, wrap=True)
        d.add_css_class("dim-label")
        d.add_css_class("caption")
        col.append(d)
        r.append(col)
        if f.fix:
            b = Gtk.Button(label=i18n.tr(f.fix[0]), valign=Gtk.Align.CENTER)
            b.add_css_class("pill")
            if f.level in ("warn", "error"):
                b.add_css_class("suggested-action")

            def go(btn, fn=f.fix[1], det=d):
                btn.set_sensitive(False)
                btn.set_label(i18n.tr("Jobber …"))
                _bg(fn, lambda res: (btn.set_label("✓"), det.set_label(str(res)[:200])))
            b.connect("clicked", go)
            r.append(b)
        box.append(r)
    return box


class AssistantDialog(Adw.Dialog):
    def __init__(self, win):
        super().__init__(title=i18n.tr("PC-assistent"), content_width=640, content_height=720)
        self.win = win
        tv = Adw.ToolbarView()
        tv.add_top_bar(Adw.HeaderBar())
        sc = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        for side in ("top", "bottom", "start", "end"):
            getattr(self.box, f"set_margin_{side}")(18)
        sc.set_child(self.box)
        tv.set_content(sc)
        self.set_child(tv)
        self.sections = {}
        for key, title in (("slow", "Hvorfor er PC-en treg akkurat nå?"), ("disk", "Diskvakt"),
                           ("ssd", "Levetid for diskene"), ("week", "Ukens helserapport"),
                           ("crash", "Krasj og strømbrudd"), ("tm", "Tidsmaskin for innstillingene")):
            h = Gtk.Box(spacing=8)
            lab = Gtk.Label(label=i18n.tr(title), xalign=0, hexpand=True)
            lab.add_css_class("title-4")
            h.append(lab)
            again = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text=i18n.tr("Sjekk på nytt"))
            again.add_css_class("flat")
            again.connect("clicked", lambda _b, k=key: self.run(k))
            h.append(again)
            self.box.append(h)
            holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            self.box.append(holder)
            self.sections[key] = holder
        for k in self.sections:
            self.run(k)

    def run(self, key):
        import assistant as A
        holder = self.sections[key]
        while (c := holder.get_first_child()) is not None:
            holder.remove(c)
        sp = Gtk.Spinner(spinning=True, halign=Gtk.Align.START)
        holder.append(sp)
        fn = {"slow": lambda: A.why_slow(self.win), "disk": A.disk_watch, "ssd": A.ssd_life,
              "week": lambda: A.weekly_report(self.win), "crash": _crashes,
              "tm": lambda: __import__("timemachine").snapshots()}[key]

        def done(res):
            holder.remove(sp)
            if isinstance(res, Exception):
                holder.append(Gtk.Label(label=f"Feil: {res}", xalign=0, wrap=True))
            elif key == "tm":
                holder.append(_tm_box(self.win, res))
            elif isinstance(res, str):
                lab = Gtk.Label(label=res, xalign=0, wrap=True)
                holder.append(lab)
            elif not res:
                ok = Gtk.Label(label="✅ " + i18n.tr({"disk": "Alle diskene har god plass",
                                                     "ssd": "Fant ingen SSD-er med levetidsmåling",
                                                     "crash": "Ingen krasj eller strømbrudd registrert"}.get(key,
                                                                                                          "Alt i orden")),
                               xalign=0)
                holder.append(ok)
            else:
                holder.append(findings_box(res))
        _bg(fn, done)


def _crashes():
    import crashlog
    evs = crashlog.history()[-10:][::-1]
    return "\n".join("• " + crashlog.text(e) for e in evs) if evs else []


def _tm_box(win, snaps):
    import time as _t
    import timemachine as TM
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    if not snaps:
        box.append(Gtk.Label(label=i18n.tr("Ingen kopier ennå – det tas en når innstillingene endres."), xalign=0,
                             wrap=True))
        return box
    for t, name, changed, why in snaps[:12]:
        r = Gtk.Box(spacing=10)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        col.append(Gtk.Label(label=_t.strftime("%d.%m kl. %H:%M", _t.localtime(t)), xalign=0))
        d = Gtk.Label(label=(i18n.tr("Endret: ") + TM.nice(changed)) if changed else (why or i18n.tr("Første kopi")),
                      xalign=0, wrap=True)
        d.add_css_class("dim-label")
        d.add_css_class("caption")
        col.append(d)
        r.append(col)
        b = Gtk.Button(label=i18n.tr("Gå tilbake hit"), valign=Gtk.Align.CENTER)
        b.add_css_class("pill")

        def go(btn, n=name):
            def ok():
                try:
                    k = TM.restore(n)
                    btn.set_label(f"✓ {k} filer – starter på nytt")
                    GLib.timeout_add(1500, lambda: (win.restart_app(), False)[1])
                except Exception as e:  # noqa: BLE001
                    btn.set_label(f"✗ {e}")
            dlg = Adw.AlertDialog(heading=i18n.tr("Gå tilbake til denne innstillingen?"),
                                  body=i18n.tr("Innstillingene settes slik de var da, og Kontrollsenter starter på "
                                               "nytt. Det tas en kopi av slik det er nå først, så du kan angre."))
            dlg.add_response("nei", i18n.tr("Avbryt"))
            dlg.add_response("ja", i18n.tr("Gå tilbake"))
            dlg.set_response_appearance("ja", Adw.ResponseAppearance.SUGGESTED)
            dlg.connect("response", lambda _d, r: r == "ja" and ok())
            dlg.present(btn.get_root())
        b.connect("clicked", go)
        r.append(b)
        box.append(r)
    return box


def open_dialog(win):
    AssistantDialog(win).present(win)


def quick_button(win):
    """Knapp til Oversikt: «🩺 Hvorfor treg?»"""
    b = Gtk.Button(label="🩺 " + i18n.tr("Hvorfor treg?"), valign=Gtk.Align.CENTER)
    b.set_tooltip_text(i18n.tr("PC-assistenten ser etter hva som gjør PC-en treg akkurat nå – og fikser det"))
    b.add_css_class("pill")
    b.connect("clicked", lambda *_: open_dialog(win))
    return b
