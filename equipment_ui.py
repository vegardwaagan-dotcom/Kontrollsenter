"""Utstyr+ i vinduet: batteri og ladegrense, Wi-Fi, kontrollere, forrige systemversjon, skjermkalibrering og
brytere (hodesett-bytte, vent på spillere, ukens beste øyeblikk)."""
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

import equipment as EQ  # noqa: E402
import i18n  # noqa: E402


def _dim(t):
    lab = Gtk.Label(label=i18n.tr(t), xalign=0, wrap=True)
    lab.add_css_class("dim-label")
    lab.add_css_class("caption")
    return lab


def _h(t):
    lab = Gtk.Label(label=i18n.tr(t), xalign=0, margin_top=8)
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


def _btn(label, cb, primary=False):
    b = Gtk.Button(label=i18n.tr(label), valign=Gtk.Align.CENTER)
    b.add_css_class("pill")
    if primary:
        b.add_css_class("suggested-action")
    b.connect("clicked", cb)
    return b


class EquipmentBox(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.msg = _dim("")
        self.append(_h("🔋 Batteri"))
        self.bat = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.append(self.bat)
        # Wi-Fi ligger under Nettverk, kontrollere under Spill › Kontrollere og forrige systemversjon under
        # Vedlikehold › Gjenoppretting – ikke dobbelt her
        self.append(_h("🖥️ Skjerm"))
        self.append(_btn("Kalibrer skjermen", lambda _b: CalibrateWindow(self.get_root()).present()))
        self.append(_h("⚙️ Innstillinger"))
        c = EQ.cfg()
        for key, title, sub in (("headset_switch", "Lyden følger hodesettet", "Når hodesettet slås på, går lyden dit – "
                                 "og tilbake når det slås av (Linux)."),
                                ("wait_for_gamers", "Vent mens noen spiller", "Oppdateringskvelden, NAS-sikkerhetskopien "
                                 "og fartstesten venter til ingen i huset spiller."),
                                ("weekly_video", "Ukens beste øyeblikk", "Søndag kveld lages en video av ukas beste "
                                 "klipp, og familien får beskjed.")):
            r = Gtk.Box(spacing=12)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            col.append(Gtk.Label(label=i18n.tr(title), xalign=0))
            col.append(_dim(sub))
            r.append(col)
            sw = Gtk.Switch(active=bool(c[key]), valign=Gtk.Align.CENTER)
            sw.connect("notify::active", lambda w, _p, k=key: EQ.set_(**{k: w.get_active()}))
            r.append(sw)
            self.append(r)
        self.append(self.msg)
        self.refresh()

    def refresh(self):
        _bg(lambda: EQ.battery_health(), self._show)

    def _show(self, r):
        if isinstance(r, Exception):
            self.msg.set_label(f"Feil: {r}")
            return
        bats = r
        while (c := self.bat.get_first_child()) is not None:
            self.bat.remove(c)
        if not bats:
            self.bat.append(_dim("Ingen innebygd batteri (stasjonær PC)."))
        for b in bats:
            h = b["health"]
            word = "god" if h >= 85 else "brukt" if h >= 70 else "slitt – vurder nytt batteri"
            self.bat.append(Gtk.Label(label=f"{b['name']}: {h} % av ny kapasitet ({word})" +
                                      (f" · {b['cycles']} ladesykluser" if b.get("cycles") else ""), xalign=0,
                                      wrap=True))
            if b.get("can_limit"):
                row = Gtk.Box(spacing=8)
                row.append(_dim(f"Ladegrense: {b['limit']} %" if b.get("limit") else "Ladegrense: av"))
                row.append(_btn("Lad til 80 % (står mest i strøm)", lambda _b: _bg(lambda: EQ.set_charge_limit(80),
                                                                                    self._done)))
                row.append(_btn("Lad til 100 %", lambda _b: _bg(lambda: EQ.set_charge_limit(100), self._done)))
                self.bat.append(row)

    def _done(self, r):
        self.msg.set_label(("✗ " if isinstance(r, Exception) else "✓ ") + str(r))
        self.refresh()

    def _rollback(self, b):
        dlg = Adw.AlertDialog(heading=i18n.tr("Gå tilbake til forrige systemversjon?"),
                              body=i18n.tr("Forrige versjon av systemet (med de gamle driverne) brukes fra neste "
                                           "omstart. Du kan gå fremover igjen med «Oppdater alt»."))
        dlg.add_response("nei", i18n.tr("Avbryt"))
        dlg.add_response("ja", i18n.tr("Gå tilbake"))
        dlg.set_response_appearance("ja", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.connect("response", lambda _d, r: r == "ja" and _bg(EQ.system_rollback, self._done))
        dlg.present(self.get_root())


class CalibrateWindow(Gtk.Window):
    """66: testmønstre i fullskjerm – svartnivå, hvitnivå og gamma – med lysstyrke."""
    STEPS = [("svart", "Svartnivå: du skal så vidt se alle rutene 1–8. Ser du ikke de mørkeste, skru opp lysstyrken "
              "(eller «svartnivå» i skjermmenyen)."),
             ("hvit", "Hvitnivå: du skal så vidt se alle rutene 1–8 mot hvitt. Forsvinner de lyseste, skru ned "
              "kontrasten i skjermmenyen."),
             ("gamma", "Gamma: myss på feltene – midten skal se like lys ut som de stripete kantene.")]

    def __init__(self, parent):
        super().__init__(title=i18n.tr("Kalibrer skjermen"), transient_for=parent, modal=True)
        self.step = 0
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.da = Gtk.DrawingArea(vexpand=True, hexpand=True)
        self.da.set_draw_func(self._draw)
        box.append(self.da)
        bar = Gtk.Box(spacing=10, margin_top=10, margin_bottom=10, margin_start=16, margin_end=16)
        self.text = Gtk.Label(xalign=0, wrap=True, hexpand=True)
        bar.append(self.text)
        try:
            import avprofiles
            cur = avprofiles.brightness()
            cur = cur if isinstance(cur, (int, float)) else (cur or {}).get("pct", 70)
        except Exception:  # noqa: BLE001
            cur = None
        if cur is not None:
            bar.append(Gtk.Label(label=i18n.tr("Lysstyrke")))
            sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 5, 100, 1)
            sc.set_value(cur)
            sc.set_size_request(180, -1)
            sc.connect("value-changed", lambda s: threading.Thread(
                target=lambda v=int(s.get_value()): __import__("avprofiles").set_brightness(v), daemon=True).start())
            bar.append(sc)
        self.next = _btn("Neste", self._next, True)
        bar.append(self.next)
        bar.append(_btn("Lukk", lambda _b: self.close()))
        box.append(bar)
        self.set_child(box)
        self._show()
        self.fullscreen()

    def _show(self):
        self.text.set_label(f"{self.step + 1}/3 · " + i18n.tr(self.STEPS[self.step][1]))
        self.next.set_label(i18n.tr("Ferdig") if self.step == 2 else i18n.tr("Neste"))
        self.da.queue_draw()

    def _next(self, _b):
        if self.step == 2:
            self.close()
            return
        self.step += 1
        self._show()

    def _draw(self, _a, cr, w, h):
        kind = self.STEPS[self.step][0]
        if kind == "gamma":
            cr.set_source_rgb(0.7297, 0.7297, 0.7297)         # 50 % lys ved gamma 2.2 (hele midtfeltet)
            cr.paint()
            for i in range(0, w, 2):                          # stripete kanter: 50 % svart/hvitt
                cr.set_source_rgb(1, 1, 1) if (i // 2) % 2 else cr.set_source_rgb(0, 0, 0)
                if i < w * 0.3 or i > w * 0.7:
                    cr.rectangle(i, 0, 2, h)
                    cr.fill()
            return
        base = 0.0 if kind == "svart" else 1.0
        cr.set_source_rgb(base, base, base)
        cr.paint()
        n = 8
        bw = w / (n + 2)
        for i in range(1, n + 1):
            v = (i * 2.0 / 255) if kind == "svart" else 1 - (i * 2.0 / 255)
            cr.set_source_rgb(v, v, v)
            cr.rectangle(bw * i, h * 0.35, bw * 0.9, h * 0.3)
            cr.fill()
            cr.set_source_rgb(0.5, 0.5, 0.5)
            cr.move_to(bw * i + bw * 0.4, h * 0.72)
            cr.set_font_size(20)
            cr.show_text(str(i))
