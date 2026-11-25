"""Kort for lyd- og skjermprofiler, nattlys og lysstyrke (Lyd-siden og GPU-siden)."""
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

import avprofiles as P  # noqa: E402
import i18n  # noqa: E402

_t = i18n.tr


def _bg(work, done):
    def run():
        try:
            r = work()
        except Exception as e:  # noqa: BLE001
            r = e
        GLib.idle_add(lambda: (done(r), False)[1])
    threading.Thread(target=run, daemon=True).start()


def _msg_text(r):
    return str(r) if isinstance(r, Exception) else (r or "")


class ProfileCard(Gtk.Box):
    """kind = «audio» eller «display»."""

    def __init__(self, kind, card_fn):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.kind = kind
        title = "Lydprofiler" if kind == "audio" else "Skjermprofiler"
        desc = ("Lagre hvor lyden går (høyttalere, hodesett, TV), mikrofonen og volumet – og bytt med ett trykk, "
                "fra mobilen eller automatisk i en scene." if kind == "audio" else
                "Lagre oppløsning, Hz, HDR og VRR – f.eks. «Spill» (høy Hz, HDR) og «Film» (60 Hz) – og bytt med "
                "ett trykk, fra mobilen eller i en scene.")
        c, self.i = card_fn(_t(title), _t(desc))
        self.append(c)
        self.flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=4,
                                min_children_per_line=1, column_spacing=8, row_spacing=8, homogeneous=True)
        self.i.append(self.flow)
        self.now = Gtk.Label(xalign=0, wrap=True)
        self.now.add_css_class("dim-label")
        self.now.add_css_class("caption")
        self.i.append(self.now)
        row = Gtk.Box(spacing=8)
        self.entry = Gtk.Entry(placeholder_text=_t("Navn, f.eks. Hodesett" if kind == "audio" else "Navn, f.eks. Spill"),
                               hexpand=True)
        row.append(self.entry)
        b = Gtk.Button(label=_t("Lagre slik det er nå"))
        b.connect("clicked", self._save)
        self.entry.connect("activate", self._save)
        row.append(b)
        self.i.append(row)
        self.msg = Gtk.Label(xalign=0, wrap=True)
        self.msg.add_css_class("ks-sub")
        self.i.append(self.msg)
        self.refresh()

    def refresh(self):
        def work():
            return P.cfg(), (P.devices() if self.kind == "audio" else P.displays())
        _bg(work, self._show)

    def _show(self, r):
        if isinstance(r, Exception):
            self.msg.set_label(str(r))
            return
        c, cur = r
        while (ch := self.flow.get_first_child()) is not None:
            self.flow.remove(ch)
        active = c.get(self.kind + "_active")
        for p in c[self.kind]:
            box = Gtk.Box(spacing=0)
            box.add_css_class("linked")
            sub = (p.get("out_name") or "") if self.kind == "audio" else \
                ", ".join(f"{o['w']}×{o['h']} @ {o['hz']} Hz" + (" HDR" if o.get("hdr") else "")
                          for o in p.get("outputs", []))
            b = Gtk.Button(hexpand=True)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            t = Gtk.Label(label=f"{p.get('icon', '')} {p['name']}", xalign=0)
            t.add_css_class("heading")
            col.append(t)
            s = Gtk.Label(label=sub, xalign=0, ellipsize=3)
            s.add_css_class("caption")
            col.append(s)
            b.set_child(col)
            if p["id"] == active:
                b.add_css_class("suggested-action")
            b.connect("clicked", lambda _b, pid=p["id"]: self._apply(pid))
            box.append(b)
            rm = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text=_t("Slett"))
            rm.connect("clicked", lambda _b, pid=p["id"]: (P.delete(self.kind, pid), self.refresh()))
            box.append(rm)
            self.flow.append(box)
        if not c[self.kind]:
            e = Gtk.Label(label=_t("Ingen profiler ennå – sett det opp slik du vil ha det, og trykk «Lagre slik det er "
                                   "nå»."), xalign=0, wrap=True)
            e.add_css_class("dim-label")
            self.flow.append(e)
        if self.kind == "audio":
            on = next((x["name"] for x in cur["out"] if x["id"] == cur["cur_out"]), "?")
            mic = next((x["name"] for x in cur["in"] if x["id"] == cur["cur_in"]), "?")
            self.now.set_label(_t("Nå: {o} ({v} %) · mikrofon: {m}").format(o=on, v=cur.get("out_vol") or "?", m=mic))
        else:
            self.now.set_label(_t("Nå: ") + "; ".join(f"{o['name']} {o['w']}×{o['h']} @ {o['hz']} Hz" +
                                                      (" · HDR" if o.get("hdr") else "") for o in cur))

    def _save(self, *_):
        name = self.entry.get_text().strip()
        if not name:
            self.msg.set_label(_t("Skriv et navn først"))
            return
        fn = P.save_audio if self.kind == "audio" else P.save_display
        _bg(lambda: fn(name), lambda r: (self.msg.set_label(_msg_text(r) if isinstance(r, Exception) else
                                                            _t("Lagret «{n}» ✓").format(n=r["name"])),
                                         self.entry.set_text(""), self.refresh()))

    def _apply(self, pid):
        fn = P.apply_audio if self.kind == "audio" else P.apply_display
        self.msg.set_label(_t("Bytter …"))
        _bg(lambda: fn(pid), lambda r: (self.msg.set_label(_msg_text(r)), self.refresh()))


class NightCard(Gtk.Box):
    def __init__(self, card_fn):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        c, i = card_fn(_t("Nattlys og lysstyrke"),
                       _t("Varmere farger om kvelden og skjermens lysstyrke – også fra mobilen og i scener "
                          "(f.eks. «Film» eller «Leggetid»)."))
        self.append(c)
        self._busy = True
        r1 = Gtk.Box(spacing=10)
        r1.append(Gtk.Label(label=_t("Nattlys"), xalign=0, hexpand=True))
        self.temp = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 2000, 6000, 100)
        self.temp.set_size_request(220, -1)
        self.temp.set_value(3500)
        self.temp.set_tooltip_text(_t("Lavere = varmere (mer gult)"))
        r1.append(self.temp)
        self.sw = Gtk.Switch(valign=Gtk.Align.CENTER)
        r1.append(self.sw)
        i.append(r1)
        r2 = Gtk.Box(spacing=10)
        r2.append(Gtk.Label(label=_t("Lysstyrke"), xalign=0, hexpand=True))
        self.bri = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 100, 1)
        self.bri.set_size_request(320, -1)
        self.bri.set_draw_value(True)
        self.bri.set_value_pos(Gtk.PositionType.RIGHT)
        r2.append(self.bri)
        i.append(r2)
        self.msg = Gtk.Label(xalign=0, wrap=True)
        self.msg.add_css_class("ks-sub")
        i.append(self.msg)
        self.sw.connect("notify::active", self._night)
        self._tid = None
        self.temp.connect("value-changed", self._temp_moved)
        self.bri.connect("value-changed", lambda *_: self._debounce(self._bright))
        _bg(lambda: (P.night_state(), P.brightness()), self._show)

    def _show(self, r):
        if not isinstance(r, Exception):
            night, bri = r
            if night:
                self.sw.set_active(night["on"])
                if night["on"]:
                    self.temp.set_value(night["temp"])
            if bri is not None:
                self.bri.set_value(bri)
            else:
                self.bri.set_sensitive(False)
                self.msg.set_label(_t("Lysstyrken kan ikke styres for denne skjermen (slå på DDC/CI i skjermens "
                                      "meny)."))
        self._busy = False

    def _debounce(self, fn):
        if self._busy:
            return
        if self._tid:
            GLib.source_remove(self._tid)
        self._tid = GLib.timeout_add(350, lambda: (setattr(self, "_tid", None), fn(), False)[2])

    def _temp_moved(self, *_):
        """Dra i glideren: still temperaturen – og slå på nattlys hvis det var av."""
        if self._busy:
            return
        if not self.sw.get_active():
            self.sw.set_active(True)                  # notify::active slår det på med denne temperaturen
            return
        self._debounce(self._night)

    def _night(self, *_):
        if self._busy:
            return
        on, t = self.sw.get_active(), int(self.temp.get_value())
        _bg(lambda: P.set_night(on, t), lambda r: self.msg.set_label(_msg_text(r)))

    def _bright(self, *_):
        v = int(self.bri.get_value())
        _bg(lambda: P.set_brightness(v), lambda r: self.msg.set_label(_msg_text(r)))


def _confirm(parent, heading, body, ok):
    d = Adw.AlertDialog(heading=heading, body=body)
    d.add_response("no", _t("Avbryt"))
    d.add_response("yes", _t("OK"))
    d.connect("response", lambda _d, r: r == "yes" and ok())
    d.present(parent)
