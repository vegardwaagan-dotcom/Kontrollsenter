"""Siden «Tester» (under Utstyr): skjermtest, mus og tastatur, og kontroller.

Høyttaler-, hodesett- og mikrofontesten ligger på Lyd-siden; oppløsning og Hz under GPU-innstillinger › Skjerm.
"""
import math
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

import i18n  # noqa: E402
import theme  # noqa: E402

_t = i18n.tr


def card(title, sub=None):
    import automation
    c, i, _h = automation.card(_t(title), _t(sub) if sub else None)
    return c, i


class TesterPage(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(12)
        self.set_child(Adw_clamp(box))
        self.box = box
        for fn in (self._screen, self._mouse, self._pad, self._more):
            try:
                fn()
            except Exception:  # noqa: BLE001
                import applog
                applog.log.exception("tester")

    # ------------------------------------------------------------------ skjerm
    def _screen(self):
        c, i = card("🖥️ Skjermtest", "Døde og fastlåste piksler, fargebånd, svart- og hvitnivå, skarphet, bevegelse "
                                     "(UFO-test) og hvor mange Hz skjermen faktisk viser. Åpnes i fullskjerm.")
        row = Gtk.Box(spacing=8)
        b = Gtk.Button(label=_t("Start skjermtest"))
        b.add_css_class("suggested-action")
        b.connect("clicked", lambda *_: __import__("skjerm_ui").ScreenTest(self.get_root()).present())
        row.append(b)
        go = Gtk.Button(label=_t("Oppløsning og Hz →"))
        go.connect("clicked", lambda *_: _open_page(self, "gpu"))
        row.append(go)
        i.append(row)
        self.box.append(c)

    # ------------------------------------------------------------------ mus og tastatur
    def _mouse(self):
        c, i = card("🖱️ Mus og tastatur", "Klikk, rull og beveg musa i feltet. Trykk mange taster samtidig. Du ser om musa dobbeltklikker av seg selv, og hvor raskt den svarer.")
        area = Gtk.DrawingArea(content_height=230, hexpand=True, focusable=True, can_focus=True)
        area.set_cursor(Gdk.Cursor.new_from_name("crosshair"))
        st = {"clicks": {}, "chatter": {}, "last": {}, "scroll": 0, "rates": [], "rate": 0, "win_t": time.monotonic(),
              "win_n": 0, "keys": set(), "maxkeys": 0, "seen": set(), "pos": None, "trail": []}
        self._mst = st

        def draw(_a, cr, w, h):
            acc = theme.accent_rgb() if hasattr(theme, "accent_rgb") else (0.36, 0.55, 1)
            cr.set_source_rgba(0.5, 0.5, 0.6, 0.12)
            cr.rectangle(0, 0, w, h)
            cr.fill()
            for k, (x, y) in enumerate(st["trail"][-60:]):
                cr.set_source_rgba(*acc, k / 60)
                cr.arc(x, y, 3, 0, 2 * math.pi)
                cr.fill()
            cr.set_source_rgba(0.6, 0.6, 0.7, 0.9)
            cr.set_font_size(14)
            cr.move_to(12, 22)
            cr.show_text(_t("Klikk her først, så virker tastaturtesten også"))
        area.set_draw_func(draw)
        i.append(area)
        out = Gtk.Label(xalign=0, wrap=True, selectable=True)
        i.append(out)
        names = {1: _t("Venstre"), 2: _t("Midtre"), 3: _t("Høyre"), 8: _t("Tilbake (4)"), 9: _t("Frem (5)")}

        def show():
            cl = "  ".join(f"{names.get(b, f'Knapp {b}')}: {n}" for b, n in sorted(st["clicks"].items())) or "–"
            ch = sum(st["chatter"].values())
            keys = " + ".join(sorted(st["keys"])) or "–"
            txt = (f"<b>{_t('Klikk')}</b>  {cl}\n"
                   f"<b>{_t('Rullehjul')}</b>  {st['scroll']} {_t('hakk')}    "
                   f"<b>Polling rate</b>  {('ca. ' + str(st['rate']) + ' Hz') if st['rate'] else _t('beveg musa raskt')}\n"
                   f"<b>{_t('Dobbeltklikk-feil')}</b>  " +
                   (f"⚠ {ch} – " + _t("musa sender to klikk på under 60 ms. Typisk slitt bryter.") if ch else
                    "✓ " + _t("ingen")) + "\n"
                   f"<b>{_t('Taster nå')}</b>  {GLib.markup_escape_text(keys)}    "
                   f"<b>{_t('Flest samtidig')}</b>  {st['maxkeys']}    <b>{_t('Ulike taster testet')}</b>  "
                   f"{len(st['seen'])}")
            out.set_markup(txt)
        show()

        def pressed(g, n, x, y):
            area.grab_focus()
            b = g.get_current_button()
            now = time.monotonic()
            st["clicks"][b] = st["clicks"].get(b, 0) + 1
            if now - st["last"].get(b, 0) < 0.06:
                st["chatter"][b] = st["chatter"].get(b, 0) + 1
            st["last"][b] = now
            show()
        cg = Gtk.GestureClick(button=0)
        cg.connect("pressed", pressed)
        area.add_controller(cg)

        def motion(ctl, x, y):
            ev = ctl.get_current_event()
            n = 1
            try:
                n += len(ev.get_history() or [])
            except Exception:  # noqa: BLE001
                pass
            st["win_n"] += n
            now = time.monotonic()
            if now - st["win_t"] >= 0.5:
                r = st["win_n"] / (now - st["win_t"])
                st["rates"].append(r)
                st["rates"] = st["rates"][-6:]
                best = max(st["rates"])
                st["rate"] = next((v for v in (125, 250, 500, 1000, 2000, 4000, 8000) if best < v * 1.25), int(best)) \
                    if best > 90 else 0
                st["win_t"], st["win_n"] = now, 0
                show()
            st["trail"].append((x, y))
            st["trail"] = st["trail"][-60:]
            area.queue_draw()
        mc = Gtk.EventControllerMotion()
        mc.connect("motion", motion)
        mc.connect("enter", lambda *_: st.update(win_t=time.monotonic(), win_n=0))
        area.add_controller(mc)
        sc = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.BOTH_AXES)
        sc.connect("scroll", lambda _c, dx, dy: (st.__setitem__("scroll", st["scroll"] + int(abs(dy) or abs(dx))),
                                                 show(), True)[2])
        area.add_controller(sc)
        kc = Gtk.EventControllerKey()

        def kp(_c, kv, _code, _s):
            n = Gdk.keyval_name(kv) or str(kv)
            st["keys"].add(n)
            st["seen"].add(n)
            st["maxkeys"] = max(st["maxkeys"], len(st["keys"]))
            show()
            return True

        def kr(_c, kv, _code, _s):
            st["keys"].discard(Gdk.keyval_name(kv) or str(kv))
            show()
        kc.connect("key-pressed", kp)
        kc.connect("key-released", kr)
        area.add_controller(kc)
        fc = Gtk.EventControllerFocus()
        fc.connect("leave", lambda *_: (st["keys"].clear(), show()))
        area.add_controller(fc)
        rs = Gtk.Button(label=_t("Nullstill"), halign=Gtk.Align.START)

        def reset(*_):
            st.update(clicks={}, chatter={}, scroll=0, rates=[], rate=0, keys=set(), maxkeys=0, seen=set(), trail=[])
            show()
            area.queue_draw()
        rs.connect("clicked", reset)
        i.append(rs)
        self.box.append(c)

    # ------------------------------------------------------------------ kontroller
    def _pad(self):
        import kontroller as K
        c, i = card("🎮 Kontroller", "Trykk på alle knappene – de lyser når de virker og blir grønne når de er testet. "
                                     "«Mål drift» finner stikker som beveger seg av seg selv.")
        top = Gtk.Box(spacing=8)
        self.pad_dd = Gtk.DropDown.new_from_strings([_t("Leter …")])
        self.pad_dd.set_hexpand(True)
        top.append(self.pad_dd)
        rf = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text=_t("Let på nytt"))
        top.append(rf)
        vib = Gtk.Button(label=_t("📳 Vibrer"))
        top.append(vib)
        dr = Gtk.Button(label=_t("Mål drift"))
        top.append(dr)
        i.append(top)
        self.pad_area = Gtk.DrawingArea(content_height=200, hexpand=True)
        self.pad_area.set_draw_func(self._draw_pad)
        i.append(self.pad_area)
        self.btn_box = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=8, column_spacing=4,
                                   row_spacing=4)
        self.btn_lbl = {}
        for k, lab in K.BUTTONS + [("LT", "LT / L2"), ("RT", "RT / R2")]:
            lb = Gtk.Label(label=lab)
            lb.add_css_class("pad-chip")
            self.btn_box.append(lb)
            self.btn_lbl[k] = lb
        i.append(self.btn_box)
        self.pad_msg = Gtk.Label(xalign=0, wrap=True)
        self.pad_msg.add_css_class("dim-label")
        i.append(self.pad_msg)
        self.box.append(c)
        self.pad = None
        self.pads = []
        _css()

        def scan(*_):
            def work():
                return K.pads()

            def done(ps):
                self.pads = ps if isinstance(ps, list) else []
                names = [n for _p, n in self.pads] or [_t("Ingen kontroller funnet – koble til og trykk ↻")]
                self.pad_dd.set_model(Gtk.StringList.new(names))
                self._open(0)
            threading.Thread(target=lambda: GLib.idle_add(lambda r=work(): (done(r), False)[1]), daemon=True).start()
        rf.connect("clicked", scan)
        self.pad_dd.connect("notify::selected", lambda dd, _p: self._open(dd.get_selected()))
        vib.connect("clicked", lambda *_: self._vibrate())
        dr.connect("clicked", lambda *_: self._drift())
        self._scan = scan
        self.connect("map", lambda *_: scan())
        self.connect("unmap", lambda *_: self._close())
        GLib.timeout_add(33, self._pad_tick)

    def _open(self, idx):
        import kontroller as K
        self._close()
        if not self.pads or idx >= len(self.pads):
            return
        try:
            self.pad = K.open_pad(self.pads[idx][0])
            self.pad_msg.set_label("")
        except Exception as e:  # noqa: BLE001
            self.pad_msg.set_label(_t("Fikk ikke åpnet kontrolleren: ") + str(e))

    def _close(self):
        if self.pad:
            self.pad.close()
            self.pad = None

    def _pad_tick(self):
        if not self.get_mapped():
            return True
        s = self.pad.s if self.pad else None
        sig = (s["t"], len(s["seen"])) if s else None            # tegn bare på nytt når noe har endret seg
        if sig == getattr(self, "_pad_sig", 0):
            return True
        self._pad_sig = sig
        for k, lb in self.btn_lbl.items():
            on = bool(s and (s["buttons"].get(k) or (k == "LT" and s["lt"] > 0.5) or (k == "RT" and s["rt"] > 0.5)))
            (lb.add_css_class if on else lb.remove_css_class)("pad-on")
            (lb.add_css_class if s and k in s["seen"] else lb.remove_css_class)("pad-seen")
        self.pad_area.queue_draw()
        return True

    def _draw_pad(self, _a, cr, w, h):
        s = self.pad.s if self.pad else {"lx": 0, "ly": 0, "rx": 0, "ry": 0, "lt": 0, "rt": 0}
        r = min(h * 0.38, w * 0.16)
        for cx, x, y, lab in ((w * 0.3, s["lx"], s["ly"], "L"), (w * 0.7, s["rx"], s["ry"], "R")):
            cy = h * 0.5
            cr.set_source_rgba(0.5, 0.5, 0.6, 0.18)
            cr.arc(cx, cy, r, 0, 2 * math.pi)
            cr.fill()
            cr.set_source_rgba(0.5, 0.5, 0.6, 0.35)
            cr.arc(cx, cy, r * 0.1, 0, 2 * math.pi)                # 10 % dødsone
            cr.stroke()
            dist = (x * x + y * y) ** 0.5
            cr.set_source_rgb(0.3, 0.85, 0.5) if dist < 0.1 else cr.set_source_rgb(0.36, 0.55, 1)
            cr.arc(cx + x * r, cy + y * r, 9, 0, 2 * math.pi)
            cr.fill()
            cr.set_source_rgba(0.7, 0.7, 0.8, 0.9)
            cr.set_font_size(12)
            cr.move_to(cx - r, cy + r + 14)
            cr.show_text(f"{lab}: x {x:+.2f}  y {y:+.2f}")
        for bx, v, lab in ((w * 0.06, s["lt"], "LT"), (w * 0.92, s["rt"], "RT")):
            bh = h * 0.7
            cr.set_source_rgba(0.5, 0.5, 0.6, 0.2)
            cr.rectangle(bx, h * 0.15, 18, bh)
            cr.fill()
            cr.set_source_rgb(0.36, 0.55, 1)
            cr.rectangle(bx, h * 0.15 + bh * (1 - v), 18, bh * v)
            cr.fill()
            cr.set_source_rgba(0.7, 0.7, 0.8, 0.9)
            cr.move_to(bx - 2, h * 0.95)
            cr.show_text(f"{lab} {int(v * 100)} %")

    def _vibrate(self):
        if not self.pad:
            self.pad_msg.set_label(_t("Ingen kontroller valgt."))
            return
        try:
            self.pad.rumble(1.0, 1.0, 700)
            self.pad_msg.set_label(_t("Vibrerer … (begge motorene)"))
        except Exception as e:  # noqa: BLE001
            self.pad_msg.set_label(str(e))

    def _drift(self):
        import kontroller as K
        if not self.pad:
            self.pad_msg.set_label(_t("Ingen kontroller valgt."))
            return
        self.pad_msg.set_label(_t("Slipp begge stikkene og ikke rør kontrolleren … (3 sekunder)"))
        samples = []

        def take():
            s = self.pad.s if self.pad else None
            if s:
                samples.append((s["lx"], s["ly"], s["rx"], s["ry"]))
            if len(samples) < 90:
                return True
            lm, rm, dz = K.drift(samples)

            def v(m):
                return ("✓ " + _t("ingen drift") if m < 0.06 else "⚠ " + _t("litt drift") if m < 0.12 else
                        "❌ " + _t("tydelig drift"))
            self.pad_msg.set_label(_t(f"Venstre stikke: {v(lm)} ({lm:.2f}) · Høyre stikke: {v(rm)} ({rm:.2f}). "
                                      f"Anbefalt dødsone i spill: {int(dz * 100)} %."))
            return False
        GLib.timeout_add(33, take)

    def _more(self):
        c, i = card("🔊 Lyd", "Høyttaler-, hodesett- og mikrofontesten ligger på Lyd-siden.")
        b = Gtk.Button(label=_t("Til Lyd-siden →"), halign=Gtk.Align.START)
        b.connect("clicked", lambda *_: _open_page(self, "lyd"))
        i.append(b)
        self.box.append(c)


def Adw_clamp(child):
    from gi.repository import Adw
    return Adw.Clamp(maximum_size=getattr(theme, "PAGE_WIDTH", 1000), child=child)


def _open_page(w, name):
    win = w.get_root()
    try:
        if hasattr(win, "ensure_lazy"):
            win.ensure_lazy(name)
        win.stack.set_visible_child_name(name)
    except Exception:  # noqa: BLE001
        pass


_css_done = False


def _css():
    global _css_done
    if _css_done:
        return
    _css_done = True
    p = Gtk.CssProvider()
    p.load_from_data(b"""
label.pad-chip { padding: 4px 10px; border-radius: 999px; background: alpha(currentColor, 0.10); color: @window_fg_color; font-size: 0.9em; }
label.pad-chip.pad-seen { background: alpha(#33d17a, 0.35); }
label.pad-chip.pad-on { background: @accent_bg_color; color: @accent_fg_color; }
""")
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), p, Gtk.STYLE_PROVIDER_PRIORITY_USER + 20)
