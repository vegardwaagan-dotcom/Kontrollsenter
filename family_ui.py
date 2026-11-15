"""Kortet «Familie og drift» i Hjemme-fanen: chat og «Middag!» til de andre PC-ene, belønning, leggetid,
sikkerhetskopi av innstillingene, selvtest, feilrapport og automatisk oppdatering."""
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

import features as F  # noqa: E402
import i18n  # noqa: E402


def _dim(text):
    lab = Gtk.Label(label=i18n.tr(text), xalign=0, wrap=True)
    lab.add_css_class("dim-label")
    return lab


def _row(label, widget):
    r = Gtk.Box(spacing=10)
    r.append(Gtk.Label(label=i18n.tr(label), xalign=0, hexpand=True, wrap=True))
    widget.set_valign(Gtk.Align.CENTER)
    r.append(widget)
    return r


class FamilyCard(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("card")
        i = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side, v in (("top", 14), ("bottom", 14), ("start", 16), ("end", 16)):
            getattr(i, f"set_margin_{side}")(v)
        self.append(i)
        t = Gtk.Label(label=i18n.tr("Familie"), xalign=0)
        t.add_css_class("heading")
        i.append(t)
        i.append(_dim("Meldinger vises som varsel på PC-en de sendes til – også mens et spill kjører."))
        self.chat = Gtk.Label(xalign=0, wrap=True, selectable=True)
        i.append(self.chat)
        row = Gtk.Box(spacing=8)
        self.to = Gtk.DropDown.new_from_strings([i18n.tr("Alle PC-ene")])
        self.targets = ["*"]
        row.append(self.to)
        self.entry = Gtk.Entry(hexpand=True, placeholder_text=i18n.tr("Skriv en melding …"), max_length=500)
        self.entry.connect("activate", lambda *_: self._send(self.entry.get_text()))
        row.append(self.entry)
        b = Gtk.Button(label=i18n.tr("Send"))
        b.add_css_class("suggested-action")
        b.connect("clicked", lambda *_: self._send(self.entry.get_text()))
        row.append(b)
        i.append(row)
        r2 = Gtk.Box(spacing=8)
        d = Gtk.Button(label="🍽️ " + i18n.tr("Middag!"))
        d.connect("clicked", lambda *_: self._send(i18n.tr("🍽️ Middag! Kom og spis."), urgent=True))
        r2.append(d)
        for m in (15, 30, 60):
            bb = Gtk.Button(label=f"+{m} min")
            bb.set_tooltip_text(i18n.tr("Ekstra spilletid i dag på denne PC-en"))
            bb.connect("clicked", lambda _b, mm=m: self._do(lambda: F.give_bonus(mm), f"+{mm} min ✓"))
            r2.append(bb)
        i.append(r2)

        exp = Gtk.Expander(label=i18n.tr("Leggetid, sikkerhetskopi og drift"))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(8)
        exp.set_child(box)
        i.append(exp)
        c = F.cfg()
        bt = Gtk.Switch(active=bool(c["bedtime"].get("enabled")))
        bt.connect("notify::active", lambda s, _p: self._bed(enabled=s.get_active()))
        box.append(_row("Leggetid – PC-en varsler 10 min før og slås av", bt))
        for key, label in (("weekday", "Søndag–torsdag"), ("weekend", "Fredag og lørdag")):
            e = Gtk.Entry(text=c["bedtime"][key], width_chars=6, max_length=5)
            e.connect("activate", lambda en, k=key: self._bed(**{k: en.get_text().strip()}))
            box.append(_row(label + " " + i18n.tr("(tt:mm, Enter for å lagre)"), e))
        for key, label in (("auto_update", "Oppdater av seg selv kl. 04 (rulles tilbake hvis den ikke starter)"),
                           ("wishlist", "Varsle om tilbud på Steam-ønskelisten")):
            s = Gtk.Switch(active=bool(c.get(key)))
            s.connect("notify::active", lambda w, _p, k=key: self._set(k, w.get_active()))
            box.append(_row(label, s))
        btns = Gtk.Box(spacing=8)
        for label, fn in (("Sikkerhetskopi av innstillingene", lambda: "Lagret: " + F.backup_settings()),
                          ("Selvtest", lambda: ", ".join(("✅ " if x["ok"] else "❌ ") + x["name"]
                                                         for x in F.selftest(self.get_root()))),
                          ("Send feilrapport", lambda: "Lagt på NAS-en ✓" if F.send_report("Fra PC-en")
                           else "Kunne ikke sende")):
            bb = Gtk.Button(label=i18n.tr(label))
            bb.connect("clicked", lambda _b, f=fn: self._do(f))
            btns.append(bb)
        box.append(btns)
        self.msg = _dim("")
        i.append(self.msg)
        self.refresh()
        GLib.timeout_add_seconds(20, lambda: self.refresh() or True)

    def refresh(self):
        def work():
            msgs = F.chat_list(8)
            try:
                import homepcs
                me = F._pc()
                pcs = [p["name"] for p in (homepcs.fetch() or []) if p.get("name") and p["name"] != me]
            except Exception:  # noqa: BLE001
                pcs = []
            GLib.idle_add(self._show, msgs, pcs)
        threading.Thread(target=work, daemon=True).start()

    def _show(self, msgs, pcs):
        self.chat.set_label("\n".join(f"{time.strftime('%H:%M', time.localtime(m['t']))}  {m['from']}: {m['text']}"
                                      for m in msgs) or i18n.tr("Ingen meldinger ennå."))
        if ["*", *pcs] != self.targets:
            self.targets = ["*", *pcs]
            self.to.set_model(Gtk.StringList.new([i18n.tr("Alle PC-ene"), *pcs]))
        return False

    def _send(self, text, urgent=False):
        text = text.strip()
        if not text:
            return
        target = self.targets[self.to.get_selected()] if self.to.get_selected() < len(self.targets) else "*"
        self.entry.set_text("")
        self._do(lambda: F.send_to(target, F._pc(), text, urgent=urgent), i18n.tr("Sendt ✓"))

    def _bed(self, **kw):
        c = F.cfg()
        for k, v in kw.items():
            if k != "enabled" and not (len(v) == 5 and v[2] == ":" and v.replace(":", "").isdigit()):
                self.msg.set_label(i18n.tr("Skriv klokkeslettet som tt:mm"))
                return
            c["bedtime"][k] = v
        F.save_cfg(c)
        self.msg.set_label(i18n.tr("Leggetiden er lagret ✓"))

    def _set(self, key, on):
        c = F.cfg()
        c[key] = on
        F.save_cfg(c)

    def _do(self, fn, ok=None):
        self.msg.set_label(i18n.tr("Arbeider …"))

        def work():
            try:
                r = fn()
                txt = ok or (r if isinstance(r, str) else i18n.tr("Ferdig ✓"))
            except Exception as e:  # noqa: BLE001
                txt = str(e)
            GLib.idle_add(lambda: (self.msg.set_label(txt), self.refresh(), False)[2])
        threading.Thread(target=work, daemon=True).start()
