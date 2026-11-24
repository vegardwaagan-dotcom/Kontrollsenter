"""Kortet «Lydfiltre» på Lyd-siden: virtuell 7.1 i hodesettet, equalizer og støyfilter på mikrofonen."""
import threading

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

import i18n  # noqa: E402
import lydfilter as F  # noqa: E402

_t = i18n.tr


def _bg(work, done):
    def run():
        try:
            r = work()
        except Exception as e:  # noqa: BLE001
            r = e
        GLib.idle_add(lambda: (done(r), False)[1])
    threading.Thread(target=run, daemon=True).start()


def _row(title, sub, widget):
    r = Gtk.Box(spacing=12)
    col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
    col.append(Gtk.Label(label=_t(title), xalign=0))
    s = Gtk.Label(label=_t(sub), xalign=0, wrap=True)
    s.add_css_class("caption")
    s.add_css_class("dim-label")
    col.append(s)
    r.append(col)
    widget.set_valign(Gtk.Align.CENTER)
    r.append(widget)
    return r


class FilterBox(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.msg = Gtk.Label(xalign=0, wrap=True)
        self.msg.add_css_class("dim-label")
        if F.IS_WIN:
            self.append(Gtk.Label(label=_t("Windows har dette innebygd: «Romlyd» (Windows Sonic for hodetelefoner), "
                                           "«Lydforbedringer» og «Stemmefokus» for mikrofonen."), xalign=0, wrap=True))
            b = Gtk.Button(label=_t("Åpne lydinnstillingene i Windows"), halign=Gtk.Align.START)
            b.connect("clicked", lambda *_: __import__("winsupport").open_uri("ms-settings:sound"))
            self.append(b)
            return
        if not F.available():
            self.append(Gtk.Label(label=_t("Krever PipeWire."), xalign=0))
            return
        st = F.state()
        self._busy = True
        self.sw = {}
        for kind, title, sub in (                       # (7.1 i hodesettet har eget kort øverst på Lyd-siden)
                ("noise", "Støyfilter på mikrofonen", "Fjerner vifter, tastatur og sus (WebRTC). Lager «Mikrofon med "
                                                      "støyfilter» og gjør den til standard.")):
            sw = Gtk.Switch(active=st[kind])
            sw.connect("notify::active", lambda s, _p, k=kind: self._toggle(k, s.get_active()))
            self.sw[kind] = sw
            self.append(_row(title, sub, sw))
        eqsw = Gtk.Switch(active=st["eq"])
        eqsw.connect("notify::active", lambda s, _p: self._toggle("eq", s.get_active()))
        self.sw["eq"] = eqsw
        self.append(_row("Equalizer", "Juster bass, mellomtone og diskant på utgangen.", eqsw))
        keys = [p["key"] for p in st["presets"]]
        self.pre = Gtk.DropDown.new_from_strings([p["name"] for p in st["presets"]] + [_t("Egen")])
        self.pre.set_selected(keys.index(st["eq_preset"]) if st["eq_preset"] in keys else len(keys))
        self.pre.set_halign(Gtk.Align.START)
        self.pre.connect("notify::selected", self._preset)
        self.append(self.pre)
        grid = Gtk.Box(spacing=4, homogeneous=True)
        self.sliders = []
        for f, g in zip(st["freq"], st["eq_gains"]):
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            sc = Gtk.Scale.new_with_range(Gtk.Orientation.VERTICAL, -12, 12, 1)
            sc.set_inverted(True)
            sc.set_size_request(-1, 140)
            sc.set_value(g)
            sc.add_mark(0, Gtk.PositionType.RIGHT, None)
            sc.connect("value-changed", self._slider)
            col.append(sc)
            col.append(Gtk.Label(label=(f"{f // 1000}k" if f >= 1000 else str(f)), css_classes=["caption"]))
            grid.append(col)
            self.sliders.append(sc)
        self.append(grid)
        self.append(self.msg)
        self._tid = None
        self._busy = False

    def _toggle(self, kind, on):
        if self._busy:
            return
        self.msg.set_label(_t("Et øyeblikk …"))

        def done(r):
            if isinstance(r, Exception):
                self._busy = True
                self.sw[kind].set_active(False)
                self._busy = False
                self.msg.set_label(f"✗ {r}")
            else:
                self.msg.set_label(_t(r))
        _bg(lambda: F.enable(kind, on), done)

    def _preset(self, dd, _p):
        if self._busy:
            return
        keys = list(F.PRESETS)
        i = dd.get_selected()
        if i >= len(keys):
            return
        c = F.set_eq(preset=keys[i])
        self._busy = True
        for sc, g in zip(self.sliders, c["eq_gains"]):
            sc.set_value(g)
        self._busy = False
        self.msg.set_label(_t(f"Equalizer: {F.PRESETS[keys[i]][0]}"))

    def _slider(self, *_):
        if self._busy:
            return
        if self._tid:
            GLib.source_remove(self._tid)

        def go():
            self._tid = None
            F.set_eq(gains=[s.get_value() for s in self.sliders])
            self._busy = True
            self.pre.set_selected(len(F.PRESETS))
            self._busy = False
            return False
        self._tid = GLib.timeout_add(500, go)


class Headset71(Gtk.Box):
    """«🎧 7.1 i hodesettet»: én knapp – spill og filmer får en 7.1-utgang, og du hører lyden rundt deg."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        if F.IS_WIN:
            self.append(Gtk.Label(label=_t("På Windows heter dette «Romlyd» (Windows Sonic for hodetelefoner). Velg "
                                           "hodesettet ditt og slå på Romlyd."), xalign=0, wrap=True))
            b = Gtk.Button(label=_t("🎧 Åpne Romlyd for hodesettet"), halign=Gtk.Align.START)
            b.add_css_class("suggested-action")
            b.connect("clicked", lambda *_: __import__("winsupport").open_uri("ms-settings:sound"))
            self.append(b)
            return
        if not F.available():
            self.append(Gtk.Label(label=_t("Krever PipeWire."), xalign=0))
            return
        self.hs = F.headsets()
        row = Gtk.Box(spacing=10)
        self.dd = Gtk.DropDown.new_from_strings([d for _n, d in self.hs] or [_t("Fant ingen hodesett")])
        self.dd.set_hexpand(True)
        tgt = F.cfg().get("surround_target")
        idx = next((i for i, (n, _d) in enumerate(self.hs) if n == tgt), 0)
        self.dd.set_selected(idx)
        row.append(self.dd)
        self.btn = Gtk.Button()
        self.btn.set_size_request(200, -1)
        self.btn.connect("clicked", self._toggle)
        row.append(self.btn)
        self.append(row)
        self.msg = Gtk.Label(xalign=0, wrap=True)
        self.msg.add_css_class("dim-label")
        self.append(self.msg)
        self._show(bool(F.running(F.SURROUND_NAME)))

    def _show(self, on):
        self.btn.set_label(_t("■ Slå av 7.1") if on else _t("🎧 Slå på 7.1"))
        for c in ("suggested-action", "destructive-action"):
            self.btn.remove_css_class(c)
        self.btn.add_css_class("destructive-action" if on else "suggested-action")
        self.dd.set_sensitive(not on)
        self.msg.set_label(_t("På – spill og filmer sender 7.1, og du hører lyden rundt deg. Test med lydsirkelen "
                              "under (velg oppsett 7.1).") if on else
                           _t("Av. Trykk for å få 7.1-lyd i et vanlig stereohodesett (virtuell surround)."))

    def _toggle(self, *_):
        on = not F.running(F.SURROUND_NAME)
        if on and not self.hs:
            self.msg.set_label(_t("Koble til hodesettet først."))
            return
        sink = self.hs[self.dd.get_selected()][0] if self.hs else ""
        self.btn.set_sensitive(False)
        self.msg.set_label(_t("Et øyeblikk …"))

        def done(r):
            self.btn.set_sensitive(True)
            if isinstance(r, Exception):
                self.msg.set_label(f"✗ {r}")
                self._show(bool(F.running(F.SURROUND_NAME)))
                return
            self._show(on)
        _bg(lambda: F.headset_on(sink) if on else F.enable("surround", False), done)
