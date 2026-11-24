"""Kortet «Test hodesett og høyttalere» på Lyd-siden (Linux og Windows)."""
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
        st = Gtk.Button(label=i18n.tr("■ Stopp"))
        st.add_css_class("destructive-action")
        st.connect("clicked", lambda *_: (L.stop(), self._mark(None)))
        bb.append(st)
        self.append(bb)
        self.status = Gtk.Label(xalign=0, wrap=True)
        self.status.add_css_class("dim-label")
        self.append(self.status)
        self._sink_changed(first=True)

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
