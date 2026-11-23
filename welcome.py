"""Velkomstveiviser: språk, oppstart, viftestyring og spill-overlay i noen få steg.

Vises automatisk første gang Kontrollsenter startes på en PC, og kan åpnes fra menyen.
"""
import json
import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

import i18n  # noqa: E402

DONE = os.path.expanduser("~/.config/systemmonitor/velkommen.json")
CFG_DIR = os.path.expanduser("~/.config/systemmonitor")
FIRST_RUN = not os.path.isdir(CFG_DIR)          # sjekkes før noe annet lager mappen


def should_show():
    return FIRST_RUN and not os.path.exists(DONE)


def mark_done():
    try:
        os.makedirs(CFG_DIR, exist_ok=True)
        with open(DONE, "w") as f:
            json.dump({"done": True}, f)
    except OSError:
        pass


def _page(icon, title, text, extra=None, pixel=72):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, valign=Gtk.Align.CENTER,
                  halign=Gtk.Align.CENTER, hexpand=True)
    for side in ("start", "end"):
        getattr(box, f"set_margin_{side}")(36)
    if pixel:
        img = Gtk.Image(icon_name=icon, pixel_size=pixel)
        if icon.endswith("-symbolic"):
            img.add_css_class("tile-icon")
        box.append(img)
    t = Gtk.Label(label=i18n.tr(title), wrap=True, justify=Gtk.Justification.CENTER)
    t.add_css_class("title-1")
    box.append(t)
    d = Gtk.Label(label=i18n.tr(text), wrap=True, justify=Gtk.Justification.CENTER, max_width_chars=48)
    d.add_css_class("dim-label")
    box.append(d)
    if extra:
        extra.set_halign(Gtk.Align.CENTER)
        extra.set_margin_top(8)
        box.append(extra)
    return box


class WelcomeDialog(Adw.Dialog):
    def __init__(self, win):
        super().__init__(title=i18n.tr("Velkommen"), content_width=640, content_height=600)
        self.win = win
        self.lang = i18n.CHOICE
        tv = Adw.ToolbarView()
        hb = Adw.HeaderBar(show_title=False)
        tv.add_top_bar(hb)
        self.car = Adw.Carousel(allow_scroll_wheel=False, hexpand=True, vexpand=True)

        # 1. Velkommen
        self.car.append(_page("no.waagan.Systemmonitor", "Velkommen til Kontrollsenter",
                              "Her ser og styrer du PC-en: ytelse, temperaturer, vifter, strømmodus, RGB, spill og "
                              "mer. Noen få valg, så er du i gang.", pixel=112))
        # 2. Språk
        seg = Gtk.Box()
        seg.add_css_class("linked")
        first = None
        for code, label in (("auto", "Automatisk (som Linux)"), ("no", "Norsk"), ("en", "English")):
            b = Gtk.ToggleButton(label=i18n.tr(label), active=(code == self.lang))
            if first:
                b.set_group(first)
            first = first or b
            b.connect("toggled", lambda btn, c=code: btn.get_active() and setattr(self, "lang", c))
            seg.append(b)
        self.car.append(_page("ks-network-symbolic", "Språk",
                              "Automatisk følger språket i Linux: norsk gir norsk, alt annet gir engelsk.", seg))
        # 3. Funksjoner: hva skal Kontrollsenter ha med?
        import funksjoner_ui
        self.features = funksjoner_ui.FeaturePicker()
        self.features.set_size_request(480, -1)
        self.car.append(_page("ks-overview-symbolic", "Hvilke funksjoner vil du ha?",
                              "Det du ikke tar med, slås helt av: det vises ikke i menyen og bruker verken minne "
                              "eller prosessor. Du kan endre det senere under Innstillinger → Funksjoner.",
                              self.features, pixel=0))
        # 4. Oppstart
        import sys
        self.win32 = sys.platform == "win32"
        if self.win32:
            import winsupport
            self.app_entry = None
            self.start_sw = Gtk.Switch(active=bool(winsupport.autostart_get("Kontrollsenter")))
        else:
            import autostart
            self.app_entry = next((a for a in autostart.apps() if a[0] == "systemmonitor"), None)
            self.start_sw = Gtk.Switch(active=bool(self.app_entry and autostart.status(self.app_entry)["on"]))
        row = Gtk.Box(spacing=12)
        row.append(Gtk.Label(label=i18n.tr("Start skjult ved innlogging")))
        row.append(self.start_sw)
        self.car.append(_page("ks-overview-symbolic", "Start ved innlogging",
                              "Kontrollsenter kan starte skjult med et ikon i systemstatusfeltet, så overlay, "
                              "vifter, spillprofiler og varsler virker med en gang.", row))
        # 4. Viftestyring (Linux – på Windows kommer den i neste runde)
        fans = getattr(win, "fans", None) if not self.win32 else None
        if fans and fans.ready():
            extra = Gtk.Label(label="✓ " + i18n.tr("Viftestyring er slått på"))
            extra.add_css_class("success")
        else:
            extra = Gtk.Button(label=i18n.tr("Aktiver viftestyring"))
            extra.add_css_class("suggested-action")
            extra.add_css_class("pill")
            extra.connect("clicked", lambda b: (fans._on_setup(b) if fans else None, b.set_sensitive(False)))
        if not self.win32:
            self.car.append(_page("ks-overview-symbolic", "Viftestyring",
                              "Lar Kontrollsenter styre viftene (stille, kraftig eller etter temperatur). "
                              "Du blir spurt om passordet ditt én gang.", extra))
        # 5. Spill-overlay
        self.ov_sw = Gtk.Switch(active=win.ov_button.get_active())
        row = Gtk.Box(spacing=12)
        row.append(Gtk.Label(label=i18n.tr("Overlay i spill")))
        row.append(self.ov_sw)
        if not self.win32:
            self.car.append(_page("ks-overlay-symbolic", "Spill-overlay",
                              "Viser FPS, temperaturer og last oppe i hjørnet mens du spiller. Høyre Shift + F12 "
                              "slår det av og på inne i spillet.", row))
        # 6. Ferdig
        go = Gtk.Button(label=i18n.tr("Kom i gang"))
        go.add_css_class("suggested-action")
        go.add_css_class("pill")
        go.connect("clicked", self._finish)
        self.car.append(_page("no.waagan.Systemmonitor", "Alt klart!",
                              "Du finner alt i sidemenyen til venstre, og flere valg i menyen (☰). Veiviseren kan "
                              "åpnes igjen derfra.", go, pixel=96))

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        body.append(self.car)
        nav = Gtk.Box(spacing=12)
        for side in ("start", "end", "bottom"):
            getattr(nav, f"set_margin_{side}")(18)
        self.back = Gtk.Button(label=i18n.tr("Tilbake"))
        self.back.connect("clicked", lambda *_: self._go(-1))
        nav.append(self.back)
        dots = Adw.CarouselIndicatorDots(carousel=self.car, hexpand=True)
        nav.append(dots)
        self.next = Gtk.Button(label=i18n.tr("Neste"))
        self.next.add_css_class("suggested-action")
        self.next.connect("clicked", lambda *_: self._go(1))
        nav.append(self.next)
        body.append(nav)
        tv.set_content(body)
        self.set_child(tv)
        self.car.connect("page-changed", lambda *_: self._sync())
        self.connect("closed", lambda *_: mark_done())
        self._sync()

    def _go(self, d):
        i = round(self.car.get_position()) + d
        if 0 <= i < self.car.get_n_pages():
            self.car.scroll_to(self.car.get_nth_page(i), True)

    def _sync(self):
        i = round(self.car.get_position())
        self.back.set_sensitive(i > 0)
        self.next.set_visible(i < self.car.get_n_pages() - 1)

    def _finish(self, *_):
        if self.win32:
            import winsupport
            winsupport.autostart_set("Kontrollsenter", winsupport.self_command() if self.start_sw.get_active()
                                     else None)
        import autostart
        if self.app_entry:
            try:
                (autostart.enable if self.start_sw.get_active() else autostart.disable)(self.app_entry)
            except Exception:  # noqa: BLE001
                pass
        if not self.win32 and self.ov_sw.get_active() != self.win.ov_button.get_active():
            self.win.ov_button.set_active(self.ov_sw.get_active())
        try:
            import funksjoner_ui
            funksjoner_ui.apply(self.win, *self.features.get())
        except Exception:  # noqa: BLE001
            pass
        mark_done()
        self.close()
        if self.lang != i18n.CHOICE:
            self.win._set_lang(self.lang)
