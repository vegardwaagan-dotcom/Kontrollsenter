"""Lyd-fanen i Kontrollsenter – enkel styring av all lyd (PipeWire/PulseAudio via pactl).

* Utgang: velg høyttaler/hodetelefon/HDMI, volum, demp, testlyd
* Inngang: velg mikrofon, volum, demp
* Programmer: volum og utgang per program som spiller lyd
* Lydkort: profil per kort (stereo, surround, HDMI, av …)
Endringer gjort andre steder (f.eks. i KDE) vises automatisk (pactl subscribe).
"""
import json
import os
import subprocess
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

TEST_SOUNDS = ["/usr/share/sounds/freedesktop/stereo/audio-volume-change.oga",
               "/usr/share/sounds/freedesktop/stereo/bell.oga",
               "/usr/share/sounds/freedesktop/stereo/complete.oga"]


_CHILDREN = []


def _die_with_parent():
    """Barneprosessen (pactl subscribe) avsluttes når Kontrollsenter avsluttes."""
    try:
        import ctypes
        import signal
        ctypes.CDLL("libc.so.6").prctl(1, signal.SIGTERM)       # PR_SET_PDEATHSIG
    except Exception:  # noqa: BLE001
        pass


def _cleanup():
    for p in _CHILDREN:
        try:
            p.terminate()
        except Exception:  # noqa: BLE001
            pass


import atexit  # noqa: E402

atexit.register(_cleanup)


def pactl(*args, timeout=10):
    try:
        r = subprocess.run(["pactl", *args], capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def pjson(kind):
    code, out = pactl("-f", "json", "list", kind)
    try:
        return json.loads(out) if code == 0 else []
    except ValueError:
        return []


def vol_pct(obj):
    try:
        ch = list(obj.get("volume", {}).values())
        return int(round(sum(int(c["value_percent"].rstrip("%")) for c in ch) / len(ch)))
    except (ValueError, KeyError, ZeroDivisionError):
        return 0


def card(title, subtitle=None):
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    outer.add_css_class("card")
    inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    for side, v in (("top", 14), ("bottom", 14), ("start", 16), ("end", 16)):
        getattr(inner, f"set_margin_{side}")(v)
    outer.append(inner)
    t = Gtk.Label(label=title, xalign=0)
    t.add_css_class("heading")
    inner.append(t)
    if subtitle:
        s = Gtk.Label(label=subtitle, xalign=0, wrap=True)
        s.add_css_class("caption")
        s.add_css_class("dim-label")
        inner.append(s)
    return outer, inner


class VolumeRow(Gtk.Box):
    """Ikon-knapp for demp + glidebryter + prosent. on_vol(pct), on_mute(bool)."""

    def __init__(self, on_vol, on_mute, maxv=150, kind="output"):
        super().__init__(spacing=10)
        self.kind = kind
        self.on_vol, self.on_mute = on_vol, on_mute
        self.mute = Gtk.ToggleButton(valign=Gtk.Align.CENTER, tooltip_text="Demp")
        self.mute.add_css_class("flat")
        self.mute.add_css_class("circular")
        self.mute.connect("toggled", self._muted)
        self.append(self.mute)
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, maxv, 1)
        self.scale.set_hexpand(True)
        self.scale.set_draw_value(False)
        self.scale.add_mark(100, Gtk.PositionType.BOTTOM, None)
        self.scale.connect("value-changed", self._changed)
        self.append(self.scale)
        self.pct = Gtk.Label(width_chars=5, xalign=1)
        self.pct.add_css_class("numeric")
        self.append(self.pct)
        self._quiet = False
        self._touched = 0.0
        self._timer = 0

    def _icon(self, v, muted):
        if self.kind == "input":
            return "microphone-sensitivity-muted-symbolic" if muted else "microphone-sensitivity-high-symbolic"
        if muted or v == 0:
            return "audio-volume-muted-symbolic"
        return "audio-volume-low-symbolic" if v < 34 else "audio-volume-medium-symbolic" if v < 67 \
            else "audio-volume-high-symbolic"

    def set_state(self, v, muted):
        if time.monotonic() - self._touched < 1.5:          # ikke hopp mens du drar
            return
        self._quiet = True
        if abs(self.scale.get_value() - v) >= 1:
            self.scale.set_value(v)
        self.mute.set_active(muted)
        self._quiet = False
        self.pct.set_label(f"{v} %")
        self.mute.set_icon_name(self._icon(v, muted))

    def _changed(self, s):
        v = int(s.get_value())
        self.pct.set_label(f"{v} %")
        self.mute.set_icon_name(self._icon(v, self.mute.get_active()))
        if self._quiet:
            return
        self._touched = time.monotonic()
        if self._timer:
            GLib.source_remove(self._timer)

        def fire():
            self._timer = 0
            self.on_vol(v)
            return False
        self._timer = GLib.timeout_add(80, fire)

    def _muted(self, b):
        self.mute.set_icon_name(self._icon(int(self.scale.get_value()), b.get_active()))
        if not self._quiet:
            self._touched = time.monotonic()
            self.on_mute(b.get_active())


class AudioPage(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(12)
        self.set_child(Adw.Clamp(maximum_size=__import__("theme").PAGE_WIDTH, child=box))
        self.box = box
        self._sig = None
        self._pending = False
        try:                                                  # lydprofiler øverst
            import avprofiles_ui
            box.append(avprofiles_ui.ProfileCard("audio", card))
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("lydprofiler")

        # Utgang
        c, i = card("Utgang", "Hvor lyden spilles: høyttalere, hodetelefoner eller skjerm (HDMI).")
        try:
            import audiofollow
            fr = Gtk.Box(spacing=10)
            fcol = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            fcol.append(Gtk.Label(label="Volumtastene følger lyden", xalign=0))
            fs = Gtk.Label(label="Volumrullen på headsettet og volumtastene styrer utgangen som faktisk spiller – "
                                 "også når et spill eller Discord bruker en annen utgang enn standard.",
                           xalign=0, wrap=True)
            fs.add_css_class("caption")
            fs.add_css_class("dim-label")
            fcol.append(fs)
            fr.append(fcol)
            fsw = Gtk.Switch(active=audiofollow.enabled(), valign=Gtk.Align.CENTER)
            fsw.connect("notify::active", lambda s, _p: audiofollow.set_enabled(s.get_active()))
            fr.append(fsw)
            i.append(fr)
        except Exception:  # noqa: BLE001
            pass
        row = Gtk.Box(spacing=8)
        self.out_dd = Gtk.DropDown.new_from_strings(["…"])
        self.out_dd.set_hexpand(True)
        self.out_dd.connect("notify::selected", self._on_out_sel)
        row.append(self.out_dd)
        test = Gtk.Button(label="Test lyd")
        test.connect("clicked", self._test)
        row.append(test)
        i.append(row)
        self.out_vol = VolumeRow(lambda v: self._set("set-sink-volume", self._out(), f"{v}%"),
                                 lambda m: self._set("set-sink-mute", self._out(), "1" if m else "0"))
        i.append(self.out_vol)
        box.append(c)

        try:                                                  # 🎧 7.1 i hodesettet – én knapp, øverst
            import lydfilter_ui
            c, i = card("🎧 7.1 i hodesettet", "Virtuell surround: spill og filmer får en 7.1-utgang, og du hører "
                                                "lyden rundt deg – i et vanlig hodesett.")
            i.append(lydfilter_ui.Headset71())
            box.append(c)
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("7.1 hodesett")
        try:                                                  # test av hodesett og høyttalere, mono → 9.1
            import lydtest_ui
            c, i = card("Test hodesett og høyttalere", "Fra mono og stereo til 7.1, 9.1 og Atmos med takhøyttalere. "
                                                       "Trykk på en høyttaler – den sier navnet sitt der den står.")
            i.append(lydtest_ui.SpeakerTest())
            box.append(c)
            c, i = card("Mikrofontest", "Ta opp 5 sekunder og hør hvordan du høres ut – med nivå, bakgrunnsstøy og "
                                        "råd om hva du bør justere.")
            i.append(lydtest_ui.MicTestBox())
            box.append(c)
            import lydfilter_ui
            c, i = card("Lydfiltre", "Equalizer og støyfilter på mikrofonen.")
            i.append(lydfilter_ui.FilterBox())
            box.append(c)
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("lydtest")

        # Inngang
        c, i = card("Inngang", "Mikrofonen som brukes i samtaler, opptak og spill.")
        self.in_dd = Gtk.DropDown.new_from_strings(["…"])
        self.in_dd.connect("notify::selected", self._on_in_sel)
        i.append(self.in_dd)
        self.in_vol = VolumeRow(lambda v: self._set("set-source-volume", self._in(), f"{v}%"),
                                lambda m: self._set("set-source-mute", self._in(), "1" if m else "0"),
                                kind="input")
        i.append(self.in_vol)
        box.append(c)

        # Programmer
        c, self.apps_box = card("Programmer", "Volum for hvert program som spiller lyd akkurat nå.")
        self.apps_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.apps_box.append(self.apps_list)
        box.append(c)

        # Lydkort
        c, self.cards_box = card("Lydkort", "Velg hvordan hvert lydkort brukes (f.eks. stereo, surround eller av).")
        self.cards_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.cards_box.append(self.cards_list)
        box.append(c)

        self.status = Gtk.Label(xalign=0, wrap=True)
        self.status.add_css_class("dim-label")
        box.append(self.status)

        self.sinks = self.sources = self.inputs = self.cards = []
        self._q_refresh()
        threading.Thread(target=self._subscribe, daemon=True).start()

    # --- data ---------------------------------------------------------------
    def _out(self):
        return self.default_sink or "@DEFAULT_SINK@"

    def _in(self):
        return self.default_source or "@DEFAULT_SOURCE@"

    def _set(self, *args):
        threading.Thread(target=lambda: pactl(*args), daemon=True).start()

    def _subscribe(self):
        while True:
            try:
                p = subprocess.Popen(["pactl", "subscribe"], stdout=subprocess.PIPE, text=True,
                                     stderr=subprocess.DEVNULL, preexec_fn=_die_with_parent)
                _CHILDREN.append(p)
                for _line in p.stdout:
                    GLib.idle_add(self._q_refresh)
            except OSError:
                pass
            time.sleep(3)

    def _q_refresh(self):
        if not self._pending:
            self._pending = True
            GLib.timeout_add(250, self._refresh_start)
        return False

    def _refresh_start(self):
        def work():
            data = {
                "sinks": pjson("sinks"),
                "sources": [s for s in pjson("sources") if not s.get("name", "").endswith(".monitor")],
                "inputs": pjson("sink-inputs"),
                "cards": pjson("cards"),
                "dsink": pactl("get-default-sink")[1].strip(),
                "dsource": pactl("get-default-source")[1].strip(),
            }
            GLib.idle_add(self._apply, data)
        threading.Thread(target=work, daemon=True).start()
        return False

    def _apply(self, d):
        self._pending = False
        self.sinks, self.sources, self.inputs, self.cards = d["sinks"], d["sources"], d["inputs"], d["cards"]
        self.default_sink, self.default_source = d["dsink"], d["dsource"]
        sig = (tuple(s["name"] for s in self.sinks), tuple(s["name"] for s in self.sources),
               tuple(i["index"] for i in self.inputs), tuple((c["name"], c["active_profile"]) for c in self.cards))
        if sig != self._sig:
            self._sig = sig
            self._build()
        self._update_values()
        if not self.sinks:
            self.status.set_label("Fant ingen lydenheter (er PipeWire/PulseAudio i gang?)")
        return False

    # --- bygg lister ----------------------------------------------------------
    def _build(self):
        self._quiet = True
        self.out_dd.set_model(Gtk.StringList.new([s["description"] for s in self.sinks] or ["(ingen)"]))
        self.in_dd.set_model(Gtk.StringList.new([s["description"] for s in self.sources] or ["(ingen)"]))
        self._quiet = False
        while (c := self.apps_list.get_first_child()):
            self.apps_list.remove(c)
        self.app_rows = {}
        for inp in self.inputs:
            pr = inp.get("properties", {})
            name = pr.get("application.name") or pr.get("media.name") or "Program"
            row = Gtk.Box(spacing=10)
            icon = Gtk.Image.new_from_icon_name(pr.get("application.icon_name") or "audio-x-generic-symbolic")
            icon.set_pixel_size(28)
            row.append(icon)
            mid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            lab = Gtk.Label(label=name, xalign=0, ellipsize=3)
            lab.add_css_class("heading")
            mid.append(lab)
            idx = inp["index"]
            vr = VolumeRow(lambda v, i=idx: self._set("set-sink-input-volume", str(i), f"{v}%"),
                           lambda m, i=idx: self._set("set-sink-input-mute", str(i), "1" if m else "0"))
            mid.append(vr)
            row.append(mid)
            dd = Gtk.DropDown.new_from_strings([s["description"] for s in self.sinks] or ["—"])
            dd.set_valign(Gtk.Align.CENTER)
            dd.set_tooltip_text("Utgang for dette programmet")
            dd.set_size_request(220, -1)
            pos = next((n for n, s in enumerate(self.sinks) if s["index"] == inp.get("sink")), 0)
            dd.set_selected(pos)
            dd.connect("notify::selected", lambda d_, _p, i=idx: self._set(
                "move-sink-input", str(i), self.sinks[d_.get_selected()]["name"]) if self.sinks else None)
            row.append(dd)
            self.apps_list.append(row)
            self.app_rows[idx] = vr
        if not self.inputs:
            lab = Gtk.Label(label="Ingen programmer spiller lyd akkurat nå.", xalign=0)
            lab.add_css_class("dim-label")
            self.apps_list.append(lab)

        while (c := self.cards_list.get_first_child()):
            self.cards_list.remove(c)
        for cd in self.cards:
            pr = cd.get("properties", {})
            name = pr.get("device.description") or cd["name"]
            profs = [(k, v) for k, v in cd.get("profiles", {}).items() if v.get("available", True)]
            if not profs:
                continue
            row = Gtk.Box(spacing=10)
            lab = Gtk.Label(label=name, xalign=0, hexpand=True, ellipsize=3)
            row.append(lab)
            names = [("Av" if k == "off" else v.get("description", k)) for k, v in profs]
            dd = Gtk.DropDown.new_from_strings(names)
            dd.set_size_request(320, -1)
            keys = [k for k, _v in profs]
            if cd.get("active_profile") in keys:
                dd.set_selected(keys.index(cd["active_profile"]))
            dd.connect("notify::selected", lambda d_, _p, c=cd["name"], k=keys:
                       self._set("set-card-profile", c, k[d_.get_selected()]))
            row.append(dd)
            self.cards_list.append(row)

    def _update_values(self):
        self._quiet = True
        si = next((n for n, s in enumerate(self.sinks) if s["name"] == self.default_sink), None)
        if si is not None and self.out_dd.get_selected() != si:
            self.out_dd.set_selected(si)
        so = next((n for n, s in enumerate(self.sources) if s["name"] == self.default_source), None)
        if so is not None and self.in_dd.get_selected() != so:
            self.in_dd.set_selected(so)
        self._quiet = False
        if si is not None:
            s = self.sinks[si]
            self.out_vol.set_state(vol_pct(s), s.get("mute", False))
        if so is not None:
            s = self.sources[so]
            self.in_vol.set_state(vol_pct(s), s.get("mute", False))
        for inp in self.inputs:
            vr = getattr(self, "app_rows", {}).get(inp["index"])
            if vr:
                vr.set_state(vol_pct(inp), inp.get("mute", False))

    # --- handlinger ------------------------------------------------------------
    def _on_out_sel(self, dd, _p):
        if getattr(self, "_quiet", False) or not self.sinks:
            return
        name = self.sinks[dd.get_selected()]["name"]
        self.default_sink = name
        self._set("set-default-sink", name)
        self.status.set_label(f"Lyd spilles nå på: {self.sinks[dd.get_selected()]['description']}")

    def _on_in_sel(self, dd, _p):
        if getattr(self, "_quiet", False) or not self.sources:
            return
        name = self.sources[dd.get_selected()]["name"]
        self.default_source = name
        self._set("set-default-source", name)
        self.status.set_label(f"Mikrofon: {self.sources[dd.get_selected()]['description']}")

    def _test(self, btn=None):
        p = getattr(self, "_test_proc", None)
        if p is not None and p.poll() is None:              # trykk igjen = stopp
            p.terminate()
            self._test_proc = None
            if btn:
                btn.set_label("Test lyd")
            self.status.set_label("Stoppet")
            return
        snd = next((p for p in TEST_SOUNDS if os.path.exists(p)), None)
        player = "pw-play" if subprocess.run(["which", "pw-play"], capture_output=True).returncode == 0 else "paplay"
        if snd:
            self._test_proc = subprocess.Popen([player, snd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.status.set_label("Spiller testlyd …")
            if btn:
                btn.set_label("■ Stopp")

                def back():
                    if self._test_proc is None or self._test_proc.poll() is not None:
                        btn.set_label("Test lyd")
                        return False
                    return True
                GLib.timeout_add(300, back)
        else:
            self.status.set_label("Fant ingen testlyd på systemet")
