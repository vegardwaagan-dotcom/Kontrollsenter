"""Fanen «Familie»: familiekontroll (kode), «Se på» skjermen til de andre PC-ene, og familiekortet (chat,
«Middag!», ekstra spilletid, leggetid)."""
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

import familylock  # noqa: E402
import i18n  # noqa: E402
import theme  # noqa: E402

STALE = 15 * 60


def _card(title, desc):
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    outer.add_css_class("card")
    inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    for side, v in (("top", 18), ("bottom", 18), ("start", 20), ("end", 20)):
        getattr(inner, f"set_margin_{side}")(v)
    outer.append(inner)
    h = Gtk.Label(label=i18n.tr(title), xalign=0)
    h.add_css_class("title-4")
    inner.append(h)
    d = Gtk.Label(label=i18n.tr(desc), xalign=0, wrap=True)
    d.add_css_class("ks-desc")
    inner.append(d)
    return outer, inner


class FamilyPage(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(18)
        self.set_child(Adw.Clamp(maximum_size=theme.PAGE_WIDTH, child=box))

        # ---- familiekontroll ----
        c, i = _card("Familiekontroll",
                     "Velg en kode som trengs for å lukke Kontrollsenter på denne PC-en. Lukkes vinduet, fortsetter "
                     "programmet i bakgrunnen. Koden beskytter også familieinnstillingene, ekstra spilletid og "
                     "bakgrunn/oppstart. Glemt koden? Slå den av fra telefonen (Spill → Familie).")
        box.append(c)
        r = Gtk.Box(spacing=16)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
        self.lock_title = Gtk.Label(xalign=0)
        self.lock_title.add_css_class("heading")
        col.append(self.lock_title)
        self.lock_sub = Gtk.Label(xalign=0, wrap=True)
        self.lock_sub.add_css_class("ks-sub")
        col.append(self.lock_sub)
        r.append(col)
        self.lock_sw = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.lock_sw.connect("notify::active", self._lock_toggle)
        r.append(self.lock_sw)
        i.append(r)
        self.chg = Gtk.Button(label=i18n.tr("Bytt kode"), halign=Gtk.Align.START)
        self.chg.connect("clicked", self._change)
        i.append(self.chg)
        self.msg = Gtk.Label(xalign=0, wrap=True)
        self.msg.add_css_class("ks-sub")
        i.append(self.msg)

        # ---- se på ----
        c, i = _card("Se på skjermen til de andre PC-ene",
                     "Som å caste fra Meta Quest: se live hva som skjer på en annen PC i huset. Bare visning – ingen "
                     "kan styre PC-en, og den som blir sett på får beskjed. Fra telefonen: «📺 Se på» på Hjem.")
        box.append(c)
        self.watch_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        i.append(self.watch_list)

        # ---- chat, middag, belønning, leggetid ----
        try:
            import family_ui
            box.append(family_ui.FamilyCard())
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("familie-kort")

        self._busy = False
        self._show_lock()
        self.refresh()
        GLib.timeout_add_seconds(30, lambda: (self.get_mapped() and self.refresh(), True)[1])

    # ---- familiekontroll ----
    def _show_lock(self):
        self._busy = True
        on = familylock.locked()
        self.lock_sw.set_active(on)
        self.lock_title.set_label(i18n.tr("Kode for å lukke Kontrollsenter") + (" – " + i18n.tr("på") if on else ""))
        self.lock_sub.set_label(i18n.tr("Kontrollsenter kan bare lukkes med koden." if on else
                                        "Av – alle kan lukke Kontrollsenter."))
        self.chg.set_visible(on)
        self._busy = False

    def _lock_toggle(self, sw, _p):
        if self._busy:
            return
        if sw.get_active() and not familylock.locked():
            familylock.ask_new_pin(self.get_root(), lambda ok: (self.msg.set_label(
                i18n.tr("Familiekontroll er på ✓") if ok else ""), self._show_lock()))
        elif not sw.get_active() and familylock.locked():
            familylock.ask(self.get_root(), "Skriv koden for å slå av familiekontroll.",
                           lambda: (familylock.turn_off(), self.msg.set_label(i18n.tr("Familiekontroll er av")),
                                    self._show_lock()), self._show_lock)

    def _change(self, *_):
        familylock.ask(self.get_root(), "Skriv den nåværende koden.",
                       lambda: familylock.ask_new_pin(self.get_root(), lambda ok: self.msg.set_label(
                           i18n.tr("Ny kode er lagret ✓") if ok else "")))

    # ---- se på ----
    def refresh(self):
        def work():
            try:
                import homepcs
                import savegames
                pcs, me = homepcs.fetch() or [], savegames.pc_name()
            except Exception:  # noqa: BLE001
                pcs, me = [], ""
            GLib.idle_add(self._show_pcs, pcs, me)
        threading.Thread(target=work, daemon=True).start()
        return False

    def _show_pcs(self, pcs, me):
        while (ch := self.watch_list.get_first_child()) is not None:
            self.watch_list.remove(ch)
        others = [p for p in pcs if p.get("name") and p["name"] != me]
        if not others:
            lab = Gtk.Label(label=i18n.tr("Fant ingen andre PC-er på hjemmenettet ennå."), xalign=0)
            lab.add_css_class("ks-sub")
            self.watch_list.append(lab)
        for p in others:
            on = time.time() - (p.get("time") or 0) < STALE and not p.get("off")
            row = Gtk.Box(spacing=14)
            img = Gtk.Image(icon_name="ks-lcd-symbolic", pixel_size=22, valign=Gtk.Align.CENTER)
            img.add_css_class("tile-icon" if on else "dim-label")
            row.append(img)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True, valign=Gtk.Align.CENTER)
            t = Gtk.Label(label=p["name"], xalign=0)
            t.add_css_class("heading")
            col.append(t)
            if not on:
                why = i18n.tr("Av")
            elif p.get("watch"):
                why = ("🎮 " + p["game"]) if p.get("game") else i18n.tr("Ingen spill nå")
            elif "watch" not in p:
                why = i18n.tr("Trenger Kontrollsenter 0.16 eller nyere – oppdater og start den på nytt")
            else:
                why = i18n.tr("Deling er slått av på den PC-en (eller fjernstyring er av)")
            s = Gtk.Label(label=why, xalign=0, wrap=True)
            s.add_css_class("ks-sub")
            col.append(s)
            row.append(col)
            b = Gtk.Button(label="📺 " + i18n.tr("Se på"), valign=Gtk.Align.CENTER,
                           sensitive=bool(on and p.get("watch") and p.get("ips")))
            if p.get("game"):
                b.add_css_class("suggested-action")
            b.connect("clicked", lambda _b, pp=p: __import__("watch_ui").WatchWindow(
                self.get_root(), pp["name"], pp["ips"][0], pp.get("game")).present())
            row.append(b)
            self.watch_list.append(row)
        return False
