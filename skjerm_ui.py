"""Skjerm: velg oppløsning og Hz (med 15 s angring) og skjermtest i fullskjerm.

Skjermtesten: ensfargede flater (døde/fastlåste piksler), fargeovergang (bånd), svartnivå og hvitnivå, skarphet,
bevegelse (UFO-test) og måling av hvor mange bilder i sekundet skjermen faktisk viser – så du ser om den kjører på
144/165/180 Hz og ikke 60. Piltaster / mellomrom / klikk = neste, Esc = avslutt.
"""
import math
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

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


def _res_name(w, h):
    names = {(3840, 2160): "4K", (2560, 1440): "1440p", (1920, 1080): "1080p", (1280, 720): "720p",
             (3440, 1440): "Ultrabred 1440p", (2560, 1080): "Ultrabred 1080p", (5120, 1440): "Superultrabred",
             (7680, 4320): "8K", (5120, 2880): "5K"}
    n = names.get((w, h))
    g = math.gcd(w, h)
    ar = f"{w // g}:{h // g}"
    ar = {"64:27": "21:9", "43:18": "21:9", "12:5": "21:9", "32:9": "32:9", "8:5": "16:10"}.get(ar, ar)
    return f"{w} × {h}  ({n + ', ' if n else ''}{ar})"


class ModeCard(Gtk.Box):
    """Oppløsning, Hz, HDR og VRR for hver skjerm – endres med en gang, og settes tilbake etter 15 s uten «Behold»."""

    def __init__(self, card_fn):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        c, self.i = card_fn(_t("Oppløsning og Hz"),
                            _t("Velg oppløsning og oppdateringsfrekvens for hver skjerm. Blir skjermen svart, går "
                               "den tilbake av seg selv etter 15 sekunder."))
        self.append(c)
        self.rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.i.append(self.rows)
        bb = Gtk.Box(spacing=8)
        test = Gtk.Button(label=_t("🧪 Skjermtest"), tooltip_text=_t("Døde piksler, fargebånd, svartnivå, "
                                                                    "bevegelse og faktisk Hz"))
        test.connect("clicked", lambda *_: ScreenTest(self.get_root()).present())
        bb.append(test)
        self.i.append(bb)
        self.msg = Gtk.Label(xalign=0, wrap=True)
        self.msg.add_css_class("dim-label")
        self.i.append(self.msg)
        self.refresh()

    def refresh(self):
        _bg(P.displays, self._show)

    def _show(self, ds):
        while (ch := self.rows.get_first_child()) is not None:
            self.rows.remove(ch)
        if isinstance(ds, Exception) or not ds:
            import shutil
            import sys
            if sys.platform != "win32" and P._display_tool() is None:     # f.eks. GNOME på Wayland
                self.rows.append(Gtk.Label(label=_t("På dette skrivebordet endres oppløsning og Hz i systemets egne "
                                                    "skjerminnstillinger."), xalign=0, wrap=True))
                app = next((c for c in (["gnome-control-center", "display"], ["cinnamon-settings", "display"],
                                        ["xfce4-display-settings"], ["systemsettings", "kcm_kscreen"])
                            if shutil.which(c[0])), None)
                if app:
                    b = Gtk.Button(label=_t("Åpne skjerminnstillingene"), halign=Gtk.Align.START)
                    b.connect("clicked", lambda *_: __import__("subprocess").Popen(app))
                    self.rows.append(b)
                return
            self.rows.append(Gtk.Label(label=_t("Fant ingen skjermer å endre her."), xalign=0))
            return
        for d in ds:
            self.rows.append(self._row(d, len(ds) > 1))

    def _row(self, d, many):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        if many:
            h = Gtk.Label(label=d["name"], xalign=0)
            h.add_css_class("heading")
            box.append(h)
        res = []
        for w, h, _hz in d["modes"]:
            if (w, h) not in res:
                res.append((w, h))
        res.sort(key=lambda x: (-x[0] * x[1], -x[0]))
        line = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, column_spacing=8, row_spacing=6,
                           max_children_per_line=4)
        rdd = Gtk.DropDown.new_from_strings([_res_name(w, h) + (" ★" if i == 0 else "") for i, (w, h) in
                                             enumerate(res)])
        rdd.set_tooltip_text(_t("Oppløsning (★ = skjermens beste)"))
        cur_r = (d["w"], d["h"])
        rdd.set_selected(res.index(cur_r) if cur_r in res else 0)
        line.append(rdd)
        hdd = Gtk.DropDown.new_from_strings(["…"])
        hdd.set_tooltip_text(_t("Oppdateringsfrekvens"))
        line.append(hdd)
        state = {"hz": []}

        def fill_hz(*_):
            w, h = res[rdd.get_selected()]
            hz = sorted({m[2] for m in d["modes"] if (m[0], m[1]) == (w, h)}, reverse=True)
            state["hz"] = hz
            hdd.set_model(Gtk.StringList.new([f"{x} Hz" + (" ★" if i == 0 else "") for i, x in enumerate(hz)]))
            want = d["hz"] if (w, h) == cur_r else hz[0]
            hdd.set_selected(hz.index(want) if want in hz else 0)
        rdd.connect("notify::selected", fill_hz)
        fill_hz()
        ap = Gtk.Button(label=_t("Bruk"))
        ap.add_css_class("suggested-action")
        line.append(ap)
        box.append(line)
        now = Gtk.Label(xalign=0, label=_t(f"Nå: {d['w']} × {d['h']} @ {d['hz']} Hz"))
        now.add_css_class("caption")
        now.add_css_class("dim-label")
        box.append(now)
        if d.get("hdr") is not None or d.get("vrr") is not None:
            ex = Gtk.Box(spacing=16)
            if d.get("hdr") is not None:
                hb = Gtk.Box(spacing=8)
                hb.append(Gtk.Label(label="HDR"))
                hsw = Gtk.Switch(active=bool(d["hdr"]), valign=Gtk.Align.CENTER)
                hsw.connect("notify::active", lambda s, _p: self._apply(d["id"], hdr=s.get_active()))
                hb.append(hsw)
                ex.append(hb)
            if d.get("vrr") is not None:
                vb = Gtk.Box(spacing=8)
                vb.append(Gtk.Label(label=_t("VRR / FreeSync")))
                vdd = Gtk.DropDown.new_from_strings([_t("Aldri"), _t("Alltid"), _t("Automatisk (i spill)")])
                vdd.set_selected(int(d["vrr"]) if d["vrr"] in (0, 1, 2) else 2)
                vdd.connect("notify::selected", lambda dd, _p: self._apply(d["id"], vrr=dd.get_selected(),
                                                                           revert=0))
                vb.append(vdd)
                ex.append(vb)
            box.append(ex)

        def go(*_):
            w, h = res[rdd.get_selected()]
            hz = state["hz"][hdd.get_selected()]
            if (w, h, hz) == (d["w"], d["h"], d["hz"]):
                self.msg.set_label(_t("Skjermen bruker allerede dette."))
                return
            self._apply(d["id"], w=w, h=h, hz=hz)
        ap.connect("clicked", go)
        return box

    def _apply(self, out_id, revert=15, **kw):
        self.msg.set_label(_t("Endrer skjermen …"))

        def done(r):
            if isinstance(r, Exception):
                self.msg.set_label(f"✗ {r}")
                return
            self.msg.set_label(r)
            if revert:
                self._ask_keep()
            else:
                self.refresh()
        _bg(lambda: P.set_mode(out_id, revert=revert, **kw), done)

    def _ask_keep(self):
        dlg = Adw.AlertDialog(heading=_t("Beholde denne skjerminnstillingen?"),
                              body=_t("Går tilbake om 15 sekunder."))
        dlg.add_response("undo", _t("Angre"))
        dlg.add_response("keep", _t("Behold"))
        dlg.set_response_appearance("keep", Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response("keep")
        dlg.set_close_response("undo")

        def tick():
            left = P.pending()
            if not left:
                dlg.close()
                self.refresh()
                return False
            dlg.set_body(_t(f"Går tilbake om {left} sekunder."))
            return True
        tid = GLib.timeout_add(500, tick)

        def resp(_d, r):
            GLib.source_remove(tid) if GLib.MainContext.default().find_source_by_id(tid) else None
            if r == "keep" and P.pending():
                self.msg.set_label(P.keep_mode())
            elif P.pending():
                self.msg.set_label(P.undo_mode())
            GLib.timeout_add(800, lambda: (self.refresh(), False)[1])
        dlg.connect("response", resp)
        dlg.present(self.get_root())


# ===================================================================== skjermtest
TESTS = [
    ("solid", "Døde piksler: helt rødt – se etter prikker som ikke er røde", (1, 0, 0)),
    ("solid", "Grønt", (0, 1, 0)),
    ("solid", "Blått", (0, 0, 1)),
    ("solid", "Hvitt – svarte prikker er døde piksler", (1, 1, 1)),
    ("solid", "Svart – lysende prikker er fastlåste piksler, lys i hjørnene er lyslekkasje", (0, 0, 0)),
    ("gradient", "Fargebånd: overgangene skal være jevne, uten striper", None),
    ("black", "Svartnivå: du skal så vidt se rute 2–3. Ser du ikke 4, er skjermen for mørk", None),
    ("white", "Hvitnivå: du skal se forskjell på rutene helt opp til 252", None),
    ("sharp", "Skarphet: linjene skal være skarpe, uten skygge eller glorie", None),
    ("ufo", "Bevegelse: følg romskipet med øynene – skarpt = rask skjerm, utsmurt = treg", None),
    ("hz", "Faktisk Hz: hvor mange bilder skjermen viser hvert sekund", None),
]


class ScreenTest(Gtk.Window):
    def __init__(self, parent=None):
        super().__init__(title=_t("Skjermtest"), decorated=False)
        if parent:
            self.set_transient_for(parent)
        self.i = 0
        self.area = Gtk.DrawingArea(hexpand=True, vexpand=True)
        self.area.set_draw_func(self._draw)
        self.set_child(self.area)
        self.frames = []
        self.t0 = time.monotonic()
        self.hint = True
        k = Gtk.EventControllerKey()
        k.connect("key-pressed", self._key)
        self.add_controller(k)
        cl = Gtk.GestureClick(button=0)
        cl.connect("pressed", lambda g, *_: self._step(-1 if g.get_current_button() == 3 else 1))
        self.area.add_controller(cl)
        self.area.add_tick_callback(self._tick)
        self.want = None                                    # Hz som er valgt i innstillingene (hentes én gang)
        _bg(lambda: max((d["hz"] or 0) for d in P.displays()), lambda r: setattr(self, "want", None if
                                                                                 isinstance(r, Exception) else r))
        self.fullscreen()

    def _key(self, _c, kv, _code, _st):
        if kv == Gdk.KEY_Escape:
            self.close()
        elif kv in (Gdk.KEY_Left, Gdk.KEY_Up, Gdk.KEY_BackSpace):
            self._step(-1)
        elif kv in (Gdk.KEY_h, Gdk.KEY_H):
            self.hint = not self.hint
        else:
            self._step(1)
        return True

    def _step(self, d):
        self.i = (self.i + d) % len(TESTS)
        self.frames = []
        self.t0 = time.monotonic()
        self.area.queue_draw()

    def _tick(self, _w, clock):
        kind = TESTS[self.i][0]
        if kind in ("ufo", "hz"):
            self.frames.append(clock.get_frame_time() / 1e6)
            self.frames = self.frames[-400:]
            self.area.queue_draw()
        return True

    def measured_hz(self):
        f = self.frames
        if len(f) < 30:
            return None
        d = [b - a for a, b in zip(f[-120:], f[-119:]) if b > a]
        d.sort()
        med = d[len(d) // 2] if d else 0
        return 1 / med if med else None

    def _draw(self, _a, cr, w, h):
        kind, text, col = TESTS[self.i]
        if kind == "solid":
            cr.set_source_rgb(*col)
            cr.paint()
        elif kind == "gradient":
            bands = [(1, 1, 1), (1, 0, 0), (0, 1, 0), (0, 0, 1)]
            bh = h / len(bands)
            for n, (r, g, b) in enumerate(bands):
                steps = 256
                sw = w / steps
                for s in range(steps):
                    v = s / (steps - 1)
                    cr.set_source_rgb(r * v, g * v, b * v)
                    cr.rectangle(s * sw, n * bh, sw + 1, bh + 1)
                    cr.fill()
        elif kind in ("black", "white"):
            cr.set_source_rgb(0, 0, 0) if kind == "black" else cr.set_source_rgb(1, 1, 1)
            cr.paint()
            n = 10
            cw = w / (n + 2)
            for s in range(1, n + 1):
                lvl = s * 3 if kind == "black" else 225 + s * 3          # 3–30 og 228–255
                v = lvl / 255
                cr.set_source_rgb(v, v, v)
                cr.rectangle(cw * s, h * 0.35, cw * 0.9, h * 0.3)
                cr.fill()
                cr.set_source_rgb(0.5, 0.5, 0.5)
                cr.move_to(cw * s + cw * 0.3, h * 0.72)
                cr.set_font_size(max(14, h / 50))
                cr.show_text(str(s) if kind == "black" else str(lvl))
        elif kind == "sharp":
            cr.set_source_rgb(0, 0, 0)
            cr.paint()
            cr.set_source_rgb(1, 1, 1)
            for x in range(0, int(w), 2):
                if (x // 2) % 2 == 0 and x < w / 2:
                    cr.rectangle(x, 0, 1, h)
            for y in range(0, int(h), 2):
                if (y // 2) % 2 == 0:
                    cr.rectangle(w / 2, y, w / 2, 1)
            cr.fill()
            cr.set_font_size(max(18, h / 30))
            cr.move_to(w * 0.55, h * 0.5)
            cr.set_source_rgb(1, 0.2, 0.2)
            cr.show_text("Aa Bb 123 – skarp tekst?")
        elif kind == "ufo":
            cr.set_source_rgb(0.08, 0.1, 0.16)
            cr.paint()
            speed = 960.0                                     # piksler per sekund (som testufo.com)
            t = time.monotonic() - self.t0
            for lane, (sp, lab) in enumerate(((speed, "960 px/s"), (speed / 2, "480 px/s"), (speed / 4, "240 px/s"))):
                y = h * (0.25 + lane * 0.22)
                x = (t * sp) % (w + 120) - 60
                cr.new_path()
                cr.set_source_rgb(0.3, 0.9, 0.5)
                cr.arc(x, y, 28, math.pi, 2 * math.pi)
                cr.fill()
                cr.set_source_rgb(0.75, 0.75, 0.85)
                cr.rectangle(x - 50, y, 100, 16)
                cr.fill()
                cr.set_source_rgb(1, 0.85, 0.2)
                for k in (-30, 0, 30):
                    cr.new_path()
                    cr.arc(x + k, y + 8, 5, 0, 2 * math.pi)
                    cr.fill()
                cr.set_source_rgb(0.6, 0.6, 0.7)
                cr.set_font_size(16)
                cr.move_to(20, y + 50)
                cr.show_text(lab)
        elif kind == "hz":
            cr.set_source_rgb(0.05, 0.06, 0.1)
            cr.paint()
            hz = self.measured_hz()
            n = len(self.frames)
            cr.set_source_rgb(1, 1, 1)
            cr.set_font_size(max(40, h / 8))
            txt = f"{hz:.0f} Hz" if hz else "måler …"
            ext = cr.text_extents(txt)
            cr.move_to((w - ext.width) / 2, h * 0.45)
            cr.show_text(txt)
            # stripe som hopper ett felt per bilde – jevn rad = ingen tapte bilder
            cols = 60
            cwid = w / cols
            for c in range(cols):
                cr.set_source_rgb(0.25, 0.8, 1) if c == n % cols else cr.set_source_rgb(0.15, 0.17, 0.25)
                cr.rectangle(c * cwid + 1, h * 0.6, cwid - 2, h * 0.06)
                cr.fill()
            want = self.want
            if hz and want:
                cr.set_font_size(max(18, h / 36))
                ok = abs(hz - want) < max(3, want * 0.05)
                msg = (f"OK – stemmer med innstillingen ({want} Hz)" if ok else
                       f"OBS: Innstillingen er {want} Hz, men bare ca. {hz:.0f} vises – sjekk kabel (DP/HDMI 2.1) "
                       "eller at vinduet står på riktig skjerm")
                cr.set_source_rgb(0.4, 1, 0.5) if ok else cr.set_source_rgb(1, 0.75, 0.3)
                ext = cr.text_extents(msg)
                cr.move_to(max(10, (w - ext.width) / 2), h * 0.8)
                cr.show_text(msg)
        if self.hint:
            cr.set_font_size(max(15, h / 60))
            bar = f"{self.i + 1}/{len(TESTS)}  ·  {_t(text)}  ·  {_t('Pil/klikk = neste · H = skjul tekst · Esc = avslutt')}"
            ext = cr.text_extents(bar)
            cr.set_source_rgba(0, 0, 0, 0.65)
            cr.rectangle(0, h - ext.height - 26, w, ext.height + 26)
            cr.fill()
            cr.set_source_rgb(1, 1, 1)
            cr.move_to(16, h - 13)
            cr.show_text(bar)
