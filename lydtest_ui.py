"""Kortet «Test hodesett og høyttalere» på Lyd-siden (Linux og Windows)."""
import math
import threading

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

import i18n  # noqa: E402
import lydtest as L  # noqa: E402

_CSS = b"""
.spk { min-width: 74px; min-height: 52px; padding: 4px 6px; border-radius: 14px; }
.spk label { font-size: 0.86em; }
button.spk.playing { background: alpha(@accent_bg_color, 0.85); background-image: none; color: @accent_fg_color;
  box-shadow: 0 0 0 3px alpha(@accent_bg_color, 0.35); }
.spk-me { font-size: 30px; }
"""
_css_done = False


def _css():
    global _css_done
    if _css_done:
        return
    _css_done = True
    from gi.repository import Gdk
    p = Gtk.CssProvider()
    p.load_from_data(_CSS)
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), p,
                                              Gtk.STYLE_PROVIDER_PRIORITY_USER + 20)   # over temaet


class SpeakerTest(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        _css()
        self.btns = {}
        self.sinks = L.sinks()
        d = L.default_sink()

        # utgang (Linux) – oppsett – lyd
        row = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, column_spacing=8, row_spacing=6, max_children_per_line=3)
        self.sink_dd = None
        if len(self.sinks) > 1:
            self.sink_dd = Gtk.DropDown.new_from_strings([s[1] for s in self.sinks])
            self.sink_dd.set_tooltip_text(i18n.tr("Utgangen testlyden spilles på"))
            idx = next((i for i, s in enumerate(self.sinks) if s[0] == d), 0)
            self.sink_dd.set_selected(idx)
            self.sink_dd.connect("notify::selected", lambda *_: self._sink_changed())
            row.append(self.sink_dd)
        self.lay_dd = Gtk.DropDown.new_from_strings([n for _k, n, _c in L.LAYOUTS])
        self.lay_dd.set_tooltip_text(i18n.tr("Høyttaleroppsett"))
        self.lay_dd.connect("notify::selected", lambda *_: self._draw())
        row.append(self.lay_dd)
        self.snd_dd = Gtk.DropDown.new_from_strings([n for _k, n in L.SOUNDS])
        self.snd_dd.set_tooltip_text(i18n.tr("Hva hver høyttaler spiller"))
        row.append(self.snd_dd)
        self.append(row)

        self.hint = Gtk.Label(xalign=0, wrap=True)
        self.hint.add_css_class("caption")
        self.hint.add_css_class("dim-label")
        self.append(self.hint)

        # rommet: høyttalerne rundt deg – trykk på en for å høre den
        self.grid = Gtk.Grid(column_spacing=6, row_spacing=6, column_homogeneous=True, valign=Gtk.Align.START, halign=Gtk.Align.CENTER)
        self.append(self.grid)

        bb = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, column_spacing=6, row_spacing=6, max_children_per_line=6)
        for lab, ch, tip in (("▶ Én og én", "seq", "Hver høyttaler sier navnet sitt etter tur"),
                             ("🔊 Alle samtidig", "all", "Støy fra alle høyttalerne på en gang"),
                             ("〰 Bass-sveip", "bass", "Lav tone fra 20 til 120 Hz i subwooferen – hør etter skrangling"),
                             ("🎧 Motfase", "hp-phase", "Venstre og høyre i motfase: høres lyden «inne i hodet» og "
                                                       "diffus ut, er alt koblet riktig. Høres den tydelig midt foran, "
                                                       "er en høyttaler koblet med feil pol.")):
            b = Gtk.Button(label=i18n.tr(lab), tooltip_text=i18n.tr(tip))
            b.connect("clicked", lambda _b, c=ch: self._play(c))
            bb.append(b)
        cal = Gtk.Button(label=i18n.tr("🎯 Kalibrer nivåer"),
                         tooltip_text=i18n.tr("Mikrofonen måler hver høyttaler der du sitter, og volumet justeres per "
                                              "kanal så alle blir like høye. Sett mikrofonen der hodet ditt er."))
        cal.connect("clicked", lambda *_: self._calibrate())
        bb.append(cal)
        rs = Gtk.Button(label=i18n.tr("↺ Like nivåer"), tooltip_text=i18n.tr("Nullstill kalibreringen"))
        rs.connect("clicked", lambda *_: self._apply_levels({}))
        bb.append(rs)
        st = Gtk.Button(label=i18n.tr("■ Stopp"))
        st.add_css_class("destructive-action")
        st.connect("clicked", lambda *_: (L.stop(), self._mark(None), self.status.set_label(i18n.tr("Stoppet"))))
        bb.append(st)
        self.append(bb)
        self.status = Gtk.Label(xalign=0, wrap=True)
        self.status.add_css_class("dim-label")
        self.append(self.status)
        self._sink_changed(first=True)
        self.append(Gtk.Separator())
        self.pan = PanCircle(self)
        self.append(self.pan)

    # ------------------------------------------------------------------
    def _sink(self):
        if not self.sink_dd:
            return self.sinks[0] if self.sinks else ("", "", [])
        return self.sinks[self.sink_dd.get_selected()]

    def _sink_changed(self, first=False):
        s = self._sink()
        keys = [k for k, _n, _c in L.LAYOUTS]
        self.lay_dd.set_selected(keys.index(L.suggest(s[2])))
        self._draw()

    def _layout(self):
        return L.LAYOUTS[self.lay_dd.get_selected()][0]

    def _draw(self):
        while (c := self.grid.get_first_child()) is not None:
            self.grid.remove(c)
        self.btns = {}
        key = self._layout()
        chans = L.LAYOUT[key][1]
        for c in chans:
            name, _m, (x, y) = L.CH[c]
            b = Gtk.Button(tooltip_text=i18n.tr(f"Spill av: {name}"))
            b.add_css_class("spk")
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            col.append(Gtk.Label(label="🔉" if c == "LFE" else "🔊"))
            nm = i18n.tr(name)
            lb = Gtk.Label(label=nm.replace(" ", "\n", 1) if " " in nm else nm + "\n",   # alltid to linjer = like høye
                           justify=Gtk.Justification.CENTER)
            col.append(lb)
            b.set_child(col)
            b.connect("clicked", lambda _b, ch=c: self._play(ch))
            self.grid.attach(b, x, y, 1, 1)
            self.btns[c] = b
        me = Gtk.Label(label="🧑", tooltip_text=i18n.tr("Du"))
        me.add_css_class("spk-me")
        self.grid.attach(me, 3, 2, 1, 1)
        for x in range(7):                                  # hold rommet like bredt uansett oppsett
            if self.grid.get_child_at(x, 2) is None and x not in (0, 6):
                self.grid.attach(Gtk.Box(width_request=74), x, 2, 1, 1)
        if getattr(self, "pan", None):                       # lydsirkelen viser høyttalerne i oppsettet
            self.pan.area.queue_draw()
        have = len(self._sink()[2])
        if L.IS_WIN:
            self.hint.set_label(i18n.tr("Spilles på standard lydutgang. Har Windows færre høyttalere satt opp enn "
                                        "oppsettet, blandes lyden ned (Lyd › Konfigurer høyttalere)."))
        elif have and have < len(chans):
            self.hint.set_label(i18n.tr(f"Utgangen har bare {have} kanaler – lyden blandes ned. Velg en utgang med "
                                        "flere kanaler, eller sett lydkortet til surround under «Lydkort» lenger ned."))
        else:
            self.hint.set_label(i18n.tr("Trykk på en høyttaler for å høre den. Den skal komme fra der den står i "
                                        "rommet."))

    def _mark(self, ch):
        for c, b in self.btns.items():
            (b.add_css_class if c == ch else b.remove_css_class)("playing")
        if ch is None:
            self.status.set_label("")
        elif ch in L.CH:
            self.status.set_label(i18n.tr(f"Spiller: {L.CH[ch][0]}"))

    def _calibrate(self):
        lay = self._layout()
        sink = self._sink()[0]
        self.status.set_label(i18n.tr("Kalibrerer – vær stille, sett mikrofonen der du sitter …"))

        def work():
            r = L.calibrate(lay, sink, on_step=lambda s: GLib.idle_add(lambda: (self.status.set_label(i18n.tr(s)),
                                                                              False)[1]))
            msg = L.apply_levels(r["adjust"], sink, lay) if not len(r["weak"]) == len(r["levels"]) else ""
            return r, msg

        def done(res):
            if isinstance(res, Exception):
                self.status.set_label(f"✗ {res}")
                return
            r, msg = res
            parts = [f"{L.CH[c][0]}: {r['adjust'][c]:+.1f} dB" for c in r["levels"] if c not in r["weak"]]
            txt = (msg + "\n" + " · ".join(parts)) if msg else ""
            if r["weak"]:
                txt += ("\n" if txt else "") + i18n.tr("⚠ Mikrofonen hørte ikke: ") + ", ".join(
                    L.CH[c][0] for c in r["weak"]) + i18n.tr(" – er de koblet til, eller er rommet for bråkete?")
            self.status.set_label(txt)

        def run():
            try:
                r = work()
            except Exception as e:  # noqa: BLE001
                r = e
            GLib.idle_add(lambda: (done(r), False)[1])
        threading.Thread(target=run, daemon=True).start()

    def _apply_levels(self, adj):
        sink = self._sink()[0]
        lay = self._layout()

        def run():
            try:
                m = L.apply_levels(adj, sink, lay)
            except Exception as e:  # noqa: BLE001
                m = f"✗ {e}"
            GLib.idle_add(lambda: (self.status.set_label(i18n.tr(m)), False)[1])
        threading.Thread(target=run, daemon=True).start()

    def _play(self, ch):
        snd = L.SOUNDS[self.snd_dd.get_selected()][0]
        sink = self._sink()[0]
        self.status.set_label(i18n.tr("Lager testlyden …"))

        def work():
            try:
                msg = L.play(self._layout(), ch, snd, sink,
                             on_change=lambda c: GLib.idle_add(lambda: (self._mark(c), False)[1]))
            except Exception as e:  # noqa: BLE001
                msg = f"Kunne ikke spille: {e}"
            GLib.idle_add(lambda: (self.status.get_label().startswith("Spiller:") or self.status.set_label(msg),
                                   False)[1])
        threading.Thread(target=work, daemon=True).start()


class MicTestBox(Gtk.Box):
    """Mikrofontest: ta opp 5 sekunder, se nivået mens du snakker, spill av og få råd."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.mt = L.MicTest()
        row = Gtk.Box(spacing=8)
        self.rec = Gtk.Button(label=i18n.tr("🎙️ Ta opp 5 sekunder"))
        self.rec.add_css_class("suggested-action")
        self.rec.connect("clicked", self._start)
        row.append(self.rec)
        self.pl = Gtk.Button(label=i18n.tr("▶ Spill av"), sensitive=False)
        self.pl.connect("clicked", lambda *_: self._play())
        row.append(self.pl)
        st = Gtk.Button(label=i18n.tr("■ Stopp"))
        st.connect("clicked", lambda *_: (self.mt.stop(), self.mt.stop_play(), self.rec.set_sensitive(True),
                                          self.bar.set_value(0)))
        self._stop_btn = st
        row.append(self._stop_btn)
        self.append(row)
        self.bar = Gtk.LevelBar(min_value=0, max_value=1)
        self.bar.add_offset_value("low", 0.55)
        self.bar.add_offset_value("high", 0.85)
        self.bar.add_offset_value("full", 1.0)
        self.append(self.bar)
        self.out = Gtk.Label(xalign=0, wrap=True)
        self.append(self.out)

    def _start(self, *_):
        self.rec.set_sensitive(False)
        self.out.set_label(i18n.tr("Snakk som vanlig i 5 sekunder – f.eks. tell til ti …"))

        def lvl(db):
            GLib.idle_add(lambda: (self.bar.set_value(max(0.0, min(1.0, (db + 60) / 60))), False)[1])
        try:
            self.mt.start(5, on_level=lvl, on_done=self._done)
        except Exception as e:  # noqa: BLE001
            self.rec.set_sensitive(True)
            self.out.set_label(f"✗ {e}")

    def _done(self, r):
        self.rec.set_sensitive(True)
        self.rec.set_label(i18n.tr("🎙️ Ta opp på nytt"))
        self.pl.set_sensitive(r.get("ok", False))
        self.bar.set_value(0)
        txt = ""
        if r.get("ok"):
            txt = i18n.tr(f"Stemme {r['speech']:.0f} dB · bakgrunn {r['noise']:.0f} dB · topp {r['peak']:.0f} dB "
                          f"· {r['snr']:.0f} dB over støyen\n")
        self.out.set_label(txt + "\n".join("• " + i18n.tr(a) for a in r["advice"]))

    def _play(self):
        try:
            self.mt.play()
        except Exception as e:  # noqa: BLE001
            self.out.set_label(f"✗ {e}")


class PanCircle(Gtk.Box):
    """Lydsirkelen: dra den runde knappen rundt, så flytter lyden seg til den vinkelen i rommet."""

    def __init__(self, test):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.test = test                                     # SpeakerTest (oppsett og utgang)
        h = Gtk.Label(label=i18n.tr("🎯 Lydsirkel"), xalign=0)
        h.add_css_class("heading")
        self.append(h)
        sub = Gtk.Label(label=i18n.tr("Dra den runde knappen rundt sirkelen – lyden flytter seg dit i rommet. Fint for "
                                      "å høre om alle vinklene henger sammen (og om virtuell 7.1 i hodesettet virker)."),
                        xalign=0, wrap=True)
        sub.add_css_class("caption")
        sub.add_css_class("dim-label")
        self.append(sub)
        self.area = Gtk.DrawingArea(content_width=340, content_height=290, halign=Gtk.Align.CENTER)
        self.area.set_draw_func(self._draw)
        self.append(self.area)
        dr = Gtk.GestureDrag()
        dr.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)   # sirkelen tar dra-bevegelsen før vinduet gjør det

        def begin(g, x, y):
            g.set_state(Gtk.EventSequenceState.CLAIMED)          # ellers flytter KDE hele vinduet
            self._at(x, y, start=True)
        dr.connect("drag-begin", begin)
        dr.connect("drag-update", lambda g, dx, dy: self._at(*self._origin(g, dx, dy)))
        self.area.add_controller(dr)
        self._redraw = False
        row = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
        self.play = Gtk.Button(label=i18n.tr("▶ Start"))
        self.play.add_css_class("suggested-action")
        self.play.connect("clicked", lambda *_: self._toggle())
        row.append(self.play)
        self.spin = Gtk.ToggleButton(label=i18n.tr("🔄 Snurr rundt"))
        self.spin.connect("toggled", lambda b: self._spin(b.get_active()))
        row.append(self.spin)
        st = Gtk.Button(label=i18n.tr("■ Stopp"))
        st.add_css_class("destructive-action")
        st.connect("clicked", lambda *_: self._stop())
        row.append(st)
        self.append(row)
        self.lab = Gtk.Label(label="", halign=Gtk.Align.CENTER)
        self.append(self.lab)
        self._tid = GLib.timeout_add(100, self._tick)
        self.connect("unmap", lambda *_: self._stop())        # går du fra siden, stopper lyden

    def _origin(self, g, dx, dy):
        ok, x0, y0 = g.get_start_point()
        return x0 + dx, y0 + dy

    def _at(self, x, y, start=False):
        w, h = self.area.get_width(), self.area.get_height()
        dx, dy = x - w / 2, y - h / 2
        if dx * dx + dy * dy < 100:
            return
        deg = math.degrees(math.atan2(dx, -dy))                # 0 = opp (rett fram), med klokka = høyre
        L.PAN.set_angle(deg)
        if self.spin.get_active():
            self.spin.set_active(False)
        if start and not L.PAN.running():
            self._start()
        if not self._redraw:                                    # tegn maks én gang per skjermbilde
            self._redraw = True
            self.area.add_tick_callback(lambda *_: (setattr(self, "_redraw", False), self.area.queue_draw(),
                                                   False)[2])

    def _start(self):
        try:
            L.PAN.start(self.test._layout(), self.test._sink()[0])
            self.play.set_label(i18n.tr("⏸ Pause"))
        except Exception as e:  # noqa: BLE001
            self.lab.set_label(f"✗ {e}")

    def _toggle(self):
        if L.PAN.running():
            self._stop()
        else:
            self._start()

    def _spin(self, on):
        L.PAN.spin = 72.0 if on else 0.0                     # én runde på 5 sekunder
        if on and not L.PAN.running():
            self._start()

    def _stop(self):
        L.PAN.spin = 0.0
        if self.spin.get_active():
            self.spin.set_active(False)
        L.PAN.stop()
        self.play.set_label(i18n.tr("▶ Start"))
        self.area.queue_draw()

    def _tick(self):
        if not self.get_mapped():
            return True
        if L.PAN.running():
            chans = L.LAYOUT[self.test._layout()][1]
            self.lab.set_label(f"{round(L.PAN.angle)}° · {i18n.tr(L.nearest(chans, L.PAN.angle))}")
            self.area.queue_draw()
        elif self.lab.get_label():
            self.lab.set_label("")
        return True

    def _draw(self, _a, cr, w, h):
        cx, cy = w / 2, h / 2
        r = min(h / 2 - 28, w / 2 - 50)                       # plass til navnene på sidene
        cr.set_source_rgba(0.5, 0.5, 0.6, 0.12)
        cr.arc(cx, cy, r + 18, 0, 2 * math.pi)
        cr.fill()
        cr.set_source_rgba(0.6, 0.6, 0.7, 0.45)
        cr.set_line_width(2)
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.stroke()
        chans = L.LAYOUT[self.test._layout()][1]
        cr.set_font_size(11)
        for c in chans:                                       # høyttalerne rundt sirkelen
            if c not in L.ANGLE or c == "LFE" or c.startswith("T"):
                continue
            a = math.radians(L.ANGLE[c])
            x, y = cx + math.sin(a) * r, cy - math.cos(a) * r
            cr.set_source_rgba(0.75, 0.78, 0.9, 0.9)
            cr.new_path()
            cr.arc(x, y, 5, 0, 2 * math.pi)
            cr.fill()
            lab = L.SHORT.get(c, c)
            ext = cr.text_extents(lab)
            lx = cx + math.sin(a) * (r + 16) - ext.width / 2
            ly = cy - math.cos(a) * (r + 16) + ext.height / 2
            cr.move_to(lx, ly)
            cr.show_text(lab)
        cr.set_source_rgba(0.75, 0.78, 0.9, 0.85)            # deg i midten: hode med nese (ser framover)
        cr.new_path()
        cr.arc(cx, cy, 13, 0, 2 * math.pi)
        cr.fill()
        cr.new_path()
        cr.move_to(cx - 5, cy - 11)
        cr.line_to(cx, cy - 20)
        cr.line_to(cx + 5, cy - 11)
        cr.fill()
        a = math.radians(L.PAN.angle)
        kx, ky = cx + math.sin(a) * r, cy - math.cos(a) * r
        on = L.PAN.running()
        cr.set_source_rgba(0.36, 0.55, 1, 0.25 if on else 0.12)  # glød rundt knappen
        cr.new_path()
        cr.arc(kx, ky, 22, 0, 2 * math.pi)
        cr.fill()
        cr.set_source_rgb(0.36, 0.55, 1) if on else cr.set_source_rgb(0.55, 0.58, 0.68)
        cr.new_path()
        cr.arc(kx, ky, 14, 0, 2 * math.pi)
        cr.fill()
        cr.set_source_rgb(1, 1, 1)
        cr.new_path()
        cr.arc(kx, ky, 5, 0, 2 * math.pi)
        cr.fill()
