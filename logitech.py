"""Logitech-fanen i Kontrollsenter – innstillinger for Logitech-mus og -tastatur (som G HUB).

* Enheter som libratbag støtter (G502, G815 …) styres via ratbagd på D-Bus.
  Endringer lagres i enhetens innebygde minne med «Lagre til …».
* Andre (f.eks. trådløse PRO X2 SUPERSTRIKE) styres via Solaar-biblioteket
  (logi_solaar.py kjøres inne i Solaar-Flatpaken).
"""
import json
import os
import queue
import subprocess
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

APP_DIR = os.path.dirname(os.path.abspath(__file__))
BUS = "org.freedesktop.ratbag1"
ROOT = "/org/freedesktop/ratbag1"
SOLAAR = ["flatpak", "run", "--command=python3", "io.github.pwr_solaar.solaar", "-"]

# --- knapper og handlinger -------------------------------------------------
NONE, BUTTON, SPECIAL, KEY, MACRO = 0, 1, 2, 3, 4
SP = 1 << 30
SPECIALS = [
    (SP + 1, "Dobbeltklikk"),
    (SP + 9, "DPI opp"), (SP + 10, "DPI ned"),
    (SP + 7, "DPI-syklus opp"), (SP + 8, "DPI-syklus ned"),
    (SP + 11, "DPI-bytte (sniper, hold inne)"), (SP + 12, "Standard-DPI"),
    (SP + 4, "Rull opp"), (SP + 5, "Rull ned"), (SP + 2, "Rull venstre"), (SP + 3, "Rull høyre"),
    (SP + 6, "Hjulmodus (klikk/fri)"),
    (SP + 13, "Neste profil"), (SP + 14, "Forrige profil"),
    (SP + 17, "G-shift (andre funksjon)"), (SP + 18, "Vis batterinivå"),
]
SPECIAL_NAME = dict(SPECIALS)
MOUSE_BUTTONS = [(1, "Venstreklikk"), (2, "Høyreklikk"), (3, "Midtklikk"),
                 (4, "Tilbake"), (5, "Frem")]
MOD_CODES = {29: "Ctrl", 97: "Ctrl", 42: "Shift", 54: "Shift", 56: "Alt", 100: "AltGr",
             125: "Super", 126: "Super"}

G502_NAMES = ["G1 · venstreklikk", "G2 · høyreklikk", "G3 · hjulklikk", "G4 · tilbake (tommel)",
              "G5 · frem (tommel)", "G6 · sniper (tommel)", "G7 · ved venstreklikk (bak)",
              "G8 · ved venstreklikk (foran)", "G9 · bak hjulet", "G10 · hjul vipp venstre",
              "G11 · hjul vipp høyre"]


# Fabrikkstandard
G502_DPI = (400, 800, 1600, 2400, 3200)          # trinn 1–5, trinn 2 (800) er standard
G502_BTNS = [(BUTTON, 1), (BUTTON, 2), (BUTTON, 3), (BUTTON, 4), (BUTTON, 5),
             (SPECIAL, SP + 11), (SPECIAL, SP + 10), (SPECIAL, SP + 9),
             (SPECIAL, SP + 13), (SPECIAL, SP + 2), (SPECIAL, SP + 3)]
G815_KEYS = [(59, 60, 61, 62, 63), (2, 3, 4, 5, 6), (7, 8, 9, 10, 11)]   # F1–F5, 1–5, 6–0
PROX2_ANALOG = {"actuation": 10, "rapid-trigger": 3, "haptics": 5}


def key_name(code):
    if code in MOD_CODES:
        return MOD_CODES[code]
    try:
        disp = Gdk.Display.get_default()
        ok, _keys, vals = disp.map_keycode(code + 8)
        if ok and vals:
            n = Gdk.keyval_name(vals[0]) or ""
            return n.upper() if len(n) == 1 else n.replace("_", " ")
    except Exception:  # noqa: BLE001
        pass
    return f"Tast {code}"


def describe(mapping):
    t, v = mapping
    if t == NONE:
        return "Deaktivert"
    if t == BUTTON:
        return dict(MOUSE_BUTTONS).get(v, f"Museknapp {v}")
    if t == SPECIAL:
        return SPECIAL_NAME.get(v, "Ukjent / ikke støttet")
    if t == KEY:
        return key_name(v)
    if t == MACRO:
        seen = []
        for typ, val in v:
            if typ == 1 and val not in seen:
                seen.append(val)
        return "Tast: " + " + ".join(key_name(c) for c in seen) if seen else "Makro"
    return "?"


# --- ratbagd D-Bus ---------------------------------------------------------
def proxy(path, iface):
    return Gio.DBusProxy.new_for_bus_sync(
        Gio.BusType.SYSTEM, Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES, None,
        BUS, path, f"{BUS}.{iface}", None)


def getp(p, prop):
    r = p.call_sync("org.freedesktop.DBus.Properties.Get",
                    GLib.Variant("(ss)", (p.get_interface_name(), prop)),
                    Gio.DBusCallFlags.NONE, 5000, None)
    return r.unpack()[0]


def setp(p, prop, variant):
    p.call_sync("org.freedesktop.DBus.Properties.Set",
                GLib.Variant("(ssv)", (p.get_interface_name(), prop, variant)),
                Gio.DBusCallFlags.NONE, 5000, None)


def call(p, method):
    return p.call_sync(method, None, Gio.DBusCallFlags.NONE, 5000, None)


def ratbag_devices():
    try:
        m = proxy(ROOT, "Manager")
        return [proxy(d, "Device") for d in getp(m, "Devices")]
    except GLib.Error:
        return []


# --- små GUI-hjelpere --------------------------------------------------------
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


def row(label, widget, sub=None):
    r = Gtk.Box(spacing=12)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
    lab = Gtk.Label(label=label, xalign=0)
    box.append(lab)
    if sub:
        s = Gtk.Label(label=sub, xalign=0, wrap=True)
        s.add_css_class("caption")
        s.add_css_class("dim-label")
        box.append(s)
    r.append(box)
    widget.set_valign(Gtk.Align.CENTER)
    r.append(widget)
    return r


def page_box():
    sc = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    for side in ("top", "bottom", "start", "end"):
        getattr(box, f"set_margin_{side}")(12)
    clamp = Adw.Clamp(maximum_size=__import__("theme").PAGE_WIDTH, child=box)
    sc.set_child(clamp)
    return sc, box


# --------------------------------------------------------------------------
# Tastefangst-dialog («trykk tasten du vil bruke»)
# --------------------------------------------------------------------------
class KeyCapture(Gtk.Window):
    def __init__(self, parent, on_done):
        super().__init__(title="Velg tast", modal=True, transient_for=parent,
                         default_width=420, default_height=180)
        self.on_done = on_done
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(20)
        t = Gtk.Label(label="Trykk tasten eller tastekombinasjonen\n(f.eks. Ctrl + C eller F5)",
                      justify=Gtk.Justification.CENTER)
        t.add_css_class("title-4")
        box.append(t)
        self.preview = Gtk.Label(label="…")
        self.preview.add_css_class("title-2")
        box.append(self.preview)
        cancel = Gtk.Button(label="Avbryt", halign=Gtk.Align.CENTER)
        cancel.connect("clicked", lambda *_: self.close())
        box.append(cancel)
        self.set_child(box)
        kc = Gtk.EventControllerKey()
        kc.connect("key-pressed", self._pressed)
        self.add_controller(kc)

    def _pressed(self, _c, _keyval, keycode, state):
        code = keycode - 8
        mods = []
        if state & Gdk.ModifierType.CONTROL_MASK:
            mods.append(29)
        if state & Gdk.ModifierType.SHIFT_MASK:
            mods.append(42)
        if state & Gdk.ModifierType.ALT_MASK:
            mods.append(56)
        if state & Gdk.ModifierType.SUPER_MASK:
            mods.append(125)
        if code in MOD_CODES:                       # bare modifikator så langt
            self.preview.set_label(" + ".join(key_name(m) for m in mods + [code]) + " + …")
            return True
        mods = [m for m in mods if m != code]
        macro = [(1, m) for m in mods] + [(1, code), (2, code)] + [(2, m) for m in reversed(mods)]
        self.on_done(macro)
        self.close()
        return True


# --------------------------------------------------------------------------
# ratbagd-enhet (G502, G815 …)
# --------------------------------------------------------------------------
class RatbagPage:
    def __init__(self, dev, status):
        self.dev, self.status = dev, status
        self.name = getp(dev, "Name")
        model = getp(dev, "Model")
        self.pid = model.split(":")[2] if model.count(":") >= 2 else ""
        self.is_kb = getp(dev, "DeviceType") != 2 and "keyboard" in self.name.lower() or \
            self.pid == "c33f"
        self.kind = "tastaturet" if self.is_kb else "musen"
        self.profiles = [proxy(p, "Profile") for p in getp(dev, "Profiles")]
        self.widget, box = page_box()
        self.box = box

        head, hi = card(self.name.replace("Logitech ", ""),
                        "Innstillingene lagres i enhetens eget minne og virker også uten at "
                        "programmet kjører. Belysning styres i RGB-fanen.")
        bar = Gtk.Box(spacing=8)
        self.dirty_lbl = Gtk.Label(xalign=0, hexpand=True, wrap=True)
        self.dirty_lbl.add_css_class("caption")
        bar.append(self.dirty_lbl)
        self.save_btn = Gtk.Button(child=Adw.ButtonContent(
            label=f"Lagre til {self.kind}", icon_name="document-save-symbolic"))
        self.save_btn.add_css_class("suggested-action")
        self.save_btn.add_css_class("pill")
        self.save_btn.connect("clicked", self._commit)
        bar.append(self.save_btn)
        hi.append(bar)
        box.append(head)

        # profiler
        pc, pi = card("Profil", "Enheten har flere profiler i innebygd minne. "
                                "Velg hvilken du vil endre, og hvilken som skal være i bruk.")
        prow = Gtk.Box(homogeneous=True)
        prow.add_css_class("linked")
        self.pbtns = []
        first = None
        for i, _p in enumerate(self.profiles):
            b = Gtk.ToggleButton(label=f"Profil {i + 1}")
            if first:
                b.set_group(first)
            first = first or b
            b.connect("toggled", self._on_profile_btn, i)
            prow.append(b)
            self.pbtns.append(b)
        pi.append(prow)
        self.p_enabled = Gtk.Switch()
        self.p_enabled.connect("notify::active", self._on_p_enabled)
        pi.append(row("Profilen er slått på", self.p_enabled,
                      "Avslåtte profiler hoppes over når du bytter profil på enheten."))
        self.p_active_btn = Gtk.Button(label="Bruk denne profilen nå")
        self.p_active_btn.connect("clicked", self._on_p_activate)
        self.p_active_lbl = Gtk.Label(xalign=0)
        self.p_active_lbl.add_css_class("caption")
        ar = Gtk.Box(spacing=12)
        ar.append(self.p_active_lbl)
        self.p_active_lbl.set_hexpand(True)
        ar.append(self.p_active_btn)
        pi.append(ar)
        box.append(pc)

        self.pbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.append(self.pbox)

        self._quiet = False
        self._timers = {}
        cur = next((i for i, p in enumerate(self.profiles) if getp(p, "IsActive")), 0)
        self.pbtns[cur].set_active(True)
        self._update_dirty()

    # --- profil -------------------------------------------------------------
    def _on_profile_btn(self, btn, i):
        if btn.get_active():
            self.sel = i
            self._build_profile()

    def _build_profile(self):
        p = self.profiles[self.sel]
        self._quiet = True
        self.p_enabled.set_active(not getp(p, "Disabled"))
        self._quiet = False
        active = getp(p, "IsActive")
        self.p_active_lbl.set_label("✓ Denne profilen er i bruk nå" if active
                                    else "Denne profilen er ikke i bruk")
        self.p_active_btn.set_sensitive(not active)
        while (c := self.pbox.get_first_child()):
            self.pbox.remove(c)

        # ytelse
        yc, yi = card("Ytelse")
        rates = list(getp(p, "ReportRates"))
        if rates:
            dd = Gtk.DropDown.new_from_strings([f"{r} Hz ({1000 / r:g} ms)" for r in rates])
            cur = getp(p, "ReportRate")
            if cur in rates:
                dd.set_selected(rates.index(cur))
            dd.connect("notify::selected",
                       lambda d, _p: self._write(p, "ReportRate", GLib.Variant("u", rates[d.get_selected()])))
            yi.append(row("Rapporteringsfrekvens", dd,
                          "Hvor ofte enheten sender data til PC-en. 1000 Hz er best for spill."))
        snap = getp(p, "AngleSnapping")
        if snap != -1:
            sw = Gtk.Switch(active=bool(snap))
            sw.connect("notify::active",
                       lambda s, _p: self._write(p, "AngleSnapping", GLib.Variant("i", int(s.get_active()))))
            yi.append(row("Vinkelfeste (angle snapping)", sw, "Retter opp små skjevheter i rette linjer."))
        self.pbox.append(yc)

        # DPI
        res = [proxy(r, "Resolution") for r in getp(p, "Resolutions")]
        if res:
            self.pbox.append(self._dpi_card(res))

        # knapper
        btns = [proxy(b, "Button") for b in getp(p, "Buttons")]
        if btns:
            self.pbox.append(self._buttons_card(btns))

    def _on_p_enabled(self, sw, _p):
        if not self._quiet:
            self._write(self.profiles[self.sel], "Disabled", GLib.Variant("b", not sw.get_active()))

    def _on_p_activate(self, _b):
        try:
            call(self.profiles[self.sel], "SetActive")
            self._changed("Profil valgt")
            self._build_profile()
        except GLib.Error as e:
            self.status(f"Feil: {e.message or 'ukjent feil fra ratbagd'}")

    # --- DPI ----------------------------------------------------------------
    def _dpi_card(self, res):
        c, i = card("DPI-følsomhet",
                    "Opptil fem trinn som du bytter mellom med DPI-knappene på musen. "
                    "«Standard» brukes når musen starter.")
        grid = Gtk.Grid(column_spacing=12, row_spacing=10)
        group = None
        for n, r in enumerate(res):
            allowed = list(getp(r, "Resolutions"))
            val = getp(r, "Resolution")
            dpi = val[0] if isinstance(val, tuple) else val
            on = Gtk.Switch(active=not getp(r, "IsDisabled"), valign=Gtk.Align.CENTER)
            on.set_tooltip_text("Slå trinnet av/på")
            name = Gtk.Label(label=f"Trinn {n + 1}", xalign=0)
            idx = min(range(len(allowed)), key=lambda k: abs(allowed[k] - dpi)) if allowed else 0
            sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, max(len(allowed) - 1, 1), 1)
            sc.set_value(idx)
            sc.set_hexpand(True)
            sc.set_draw_value(False)
            vl = Gtk.Label(label=f"{dpi} DPI", width_chars=10, xalign=1)
            vl.add_css_class("numeric")
            std = Gtk.CheckButton(label="Standard", active=getp(r, "IsDefault"))
            if group:
                std.set_group(group)
            group = group or std
            act = Gtk.Label(label="● aktiv" if getp(r, "IsActive") else "")
            act.add_css_class("accent")
            act.add_css_class("caption")
            tuple_type = isinstance(val, tuple)

            def on_scale(s, r=r, allowed=allowed, vl=vl, tuple_type=tuple_type):
                v = allowed[int(s.get_value())]
                vl.set_label(f"{v} DPI")
                inner = GLib.Variant("(uu)", (v, v)) if tuple_type else GLib.Variant("u", v)
                self._debounce(("dpi", id(r)), lambda: self._write(r, "Resolution", GLib.Variant("v", inner)))
            sc.connect("value-changed", on_scale)
            on.connect("notify::active",
                       lambda s, _p, r=r: self._write(r, "IsDisabled", GLib.Variant("b", not s.get_active())))
            std.connect("toggled", lambda b, r=r: b.get_active() and self._call(r, "SetDefault", "Standard-DPI satt"))
            for col, w in enumerate((on, name, sc, vl, std, act)):
                grid.attach(w, col, n, 1, 1)
        i.append(grid)
        presets = Gtk.Box(spacing=6)
        lab = Gtk.Label(label="Hurtigvalg for trinn 1–5:")
        lab.add_css_class("caption")
        presets.append(lab)
        for name, vals in (("Spill", (400, 800, 1600, 3200, 6400)),
                           ("Kontor", (800, 1200, 1600, 2400, 3200)),
                           ("Presisjon", (200, 400, 800, 1200, 1600))):
            b = Gtk.Button(label=name)
            b.connect("clicked", lambda _b, vals=vals: self._dpi_preset(res, vals))
            presets.append(b)
        i.append(presets)
        return c

    def _dpi_preset(self, res, vals):
        for r, v in zip(res, vals):
            val = getp(r, "Resolution")
            inner = GLib.Variant("(uu)", (v, v)) if isinstance(val, tuple) else GLib.Variant("u", v)
            self._write(r, "Resolution", GLib.Variant("v", inner), rebuild=False)
            if getp(r, "IsDisabled"):
                self._write(r, "IsDisabled", GLib.Variant("b", False), rebuild=False)
        self._build_profile()

    # --- knapper ------------------------------------------------------------
    def _buttons_card(self, btns):
        c, i = card("Knapper" if not self.is_kb else "G-taster",
                    "Velg hva hver knapp skal gjøre. Trykk «Endre» og velg en funksjon, "
                    "eller «Tastetrykk …» for å trykke inn en tast eller kombinasjon.")
        grid = Gtk.Grid(column_spacing=12, row_spacing=8)
        r = 0
        for n, b in enumerate(btns):
            mapping = getp(b, "Mapping")
            if self.is_kb and mapping[0] == SPECIAL and mapping[1] == SP:
                continue                              # ukjente ekstra-taster
            if self.is_kb:
                name = f"G{n + 1}"
            elif self.pid == "c332" and n < len(G502_NAMES):
                name = G502_NAMES[n]
            else:
                name = f"Knapp {n + 1}"
            nl = Gtk.Label(label=name, xalign=0)
            dl = Gtk.Label(label=describe(mapping), xalign=0, hexpand=True, ellipsize=3)
            dl.add_css_class("dim-label")
            mb = Gtk.MenuButton(label="Endre")
            mb.set_popover(self._action_popover(b, dl, mb, list(getp(b, "ActionTypes"))))
            grid.attach(nl, 0, r, 1, 1)
            grid.attach(dl, 1, r, 1, 1)
            grid.attach(mb, 2, r, 1, 1)
            r += 1
        i.append(grid)
        return c

    def _action_popover(self, b, dl, mb, types):
        pop = Gtk.Popover()
        sc = Gtk.ScrolledWindow(propagate_natural_height=True, max_content_height=420,
                                hscrollbar_policy=Gtk.PolicyType.NEVER)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(6)
        sc.set_child(box)
        pop.set_child(sc)

        def head(text):
            h = Gtk.Label(label=text, xalign=0)
            h.add_css_class("caption-heading")
            h.set_margin_top(6)
            box.append(h)

        def item(text, fn):
            it = Gtk.Button(label=text)
            it.add_css_class("flat")
            it.get_child().set_xalign(0)
            it.connect("clicked", lambda *_: (pop.popdown(), fn()))
            box.append(it)

        def setmap(t, v):
            sig = {BUTTON: "u", SPECIAL: "u", KEY: "u", NONE: "u", MACRO: "a(uu)"}[t]
            try:
                setp(b, "Mapping", GLib.Variant("(uv)", (t, GLib.Variant(sig, v))))
                dl.set_label(describe((t, v)))
                self._changed("Knapp endret")
            except GLib.Error as e:
                self.status(f"Feil: {e.message or 'ukjent feil fra ratbagd'}")

        if MACRO in types or KEY in types:
            item("⌨ Tastetrykk … (trykk tasten)", lambda: KeyCapture(
                mb.get_root(), lambda m: setmap(MACRO, m) if MACRO in types else
                setmap(KEY, [c for t, c in m if t == 1][-1])).present())
        if BUTTON in types:
            head("Museknapper")
            for v, t in MOUSE_BUTTONS:
                item(t, lambda v=v: setmap(BUTTON, v))
        if SPECIAL in types:
            head("Spesialfunksjoner")
            for v, t in SPECIALS:
                item(t, lambda v=v: setmap(SPECIAL, v))
        if NONE in types:
            head("Annet")
            item("Deaktiver knappen", lambda: setmap(NONE, 0))
        return pop

    # --- skriving -----------------------------------------------------------
    def _debounce(self, key, fn, ms=300):
        if key in self._timers:
            GLib.source_remove(self._timers[key])

        def fire():
            self._timers.pop(key, None)
            fn()
            return False
        self._timers[key] = GLib.timeout_add(ms, fire)

    def _write(self, p, prop, variant, rebuild=False):
        try:
            setp(p, prop, variant)
            self._changed()
        except GLib.Error as e:
            self.status(f"Kunne ikke endre: {e.message}")
        if rebuild:
            self._build_profile()

    def _call(self, p, method, msg):
        try:
            call(p, method)
            self._changed(msg)
        except GLib.Error as e:
            self.status(f"Feil: {e.message or 'ukjent feil fra ratbagd'}")

    def _changed(self, msg="Endret"):
        self.status(f"{msg} – husk «Lagre til {self.kind}»")
        self._update_dirty()

    def _update_dirty(self):
        dirty = any(getp(p, "IsDirty") for p in self.profiles)
        self.dirty_lbl.set_label("● Ulagrede endringer" if dirty else "Alt er lagret i enheten")
        (self.dirty_lbl.add_css_class if dirty else self.dirty_lbl.remove_css_class)("warning")
        self.save_btn.set_sensitive(dirty)

    def factory_reset(self):
        errors = []

        def s(p, prop, v):
            try:
                setp(p, prop, v)
            except GLib.Error as e:
                errors.append(e.message)

        def c(p, method):
            try:
                call(p, method)
            except GLib.Error as e:
                errors.append(e.message)

        for i, p in enumerate(self.profiles):
            s(p, "Disabled", GLib.Variant("b", False))
            if 1000 in list(getp(p, "ReportRates")):
                s(p, "ReportRate", GLib.Variant("u", 1000))
            if getp(p, "AngleSnapping") != -1:
                s(p, "AngleSnapping", GLib.Variant("i", 0))
            res = [proxy(r, "Resolution") for r in getp(p, "Resolutions")]
            for n, r in enumerate(res):
                allowed = list(getp(r, "Resolutions")) or [800]
                target = G502_DPI[min(n, len(G502_DPI) - 1)]
                v = min(allowed, key=lambda a: abs(a - target))
                cur = getp(r, "Resolution")
                inner = GLib.Variant("(uu)", (v, v)) if isinstance(cur, tuple) else GLib.Variant("u", v)
                s(r, "Resolution", GLib.Variant("v", inner))
                s(r, "IsDisabled", GLib.Variant("b", False))
            if res:
                std = res[min(1, len(res) - 1)]
                c(std, "SetDefault")
                c(std, "SetActive")
            btns = [proxy(b, "Button") for b in getp(p, "Buttons")]
            if self.is_kb:
                keys = G815_KEYS[i] if i < len(G815_KEYS) else G815_KEYS[0]
                for b, k in zip(btns, keys):
                    s(b, "Mapping", GLib.Variant("(uv)", (MACRO, GLib.Variant("a(uu)", [(1, k), (2, k)]))))
            else:
                defaults = G502_BTNS if self.pid == "c332" else G502_BTNS[:5]
                for b, (t, v) in zip(btns, defaults):
                    s(b, "Mapping", GLib.Variant("(uv)", (t, GLib.Variant("u", v))))
        c(self.profiles[0], "SetActive")
        if errors:
            self.status(f"Noen innstillinger kunne ikke tilbakestilles: {errors[0]}")
        self.pbtns[0].set_active(True)
        self._commit(None)
        return errors

    def _commit(self, _b):
        self.save_btn.set_sensitive(False)
        self.status(f"Lagrer til {self.kind} …")

        def done(dev, res):
            try:
                r = dev.call_finish(res).unpack()[0]
                self.status(f"Lagret til {self.kind} ✓" if r == 0 else f"Lagring feilet (kode {r})")
            except GLib.Error as e:
                self.status(f"Lagring feilet: {e.message}")
            self._update_dirty()
            self._build_profile()
        self.dev.call("Commit", None, Gio.DBusCallFlags.NONE, 30000, None, done)


# --------------------------------------------------------------------------
# Solaar-enhet (f.eks. PRO X2 SUPERSTRIKE)
# --------------------------------------------------------------------------
RATE_HZ = {"8ms": "125 Hz", "4ms": "250 Hz", "2ms": "500 Hz", "1ms": "1000 Hz",
           "500us": "2000 Hz", "250us": "4000 Hz", "125us": "8000 Hz"}


def solaar(*args):
    with open(os.path.join(APP_DIR, "logi_solaar.py")) as f:
        script = f.read()
    r = subprocess.run(SOLAAR + list(args), input=script, capture_output=True, text=True, timeout=90)
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith(("{", "["))]
    if not lines:
        raise RuntimeError((r.stderr.strip().splitlines() or ["ukjent feil"])[-1])
    out = json.loads(lines[-1])
    if isinstance(out, dict) and out.get("error"):
        raise RuntimeError(out["error"])
    return out


class SolaarPage:
    def __init__(self, info, status):
        self.info, self.status = info, status
        self.name = info["name"]
        self.widget, self.box = page_box()
        sp = Gtk.Spinner(spinning=True, halign=Gtk.Align.CENTER)
        self.box.append(sp)
        self.box.append(Gtk.Label(label="Leser innstillinger fra musen …"))
        self.q = queue.Queue()
        threading.Thread(target=self._worker, daemon=True).start()
        self.q.put(("get",))

    def _worker(self):
        while True:
            job = self.q.get()
            # slå sammen gjentatte skrivinger til samme innstilling
            if job[0] == "set":
                rest = []
                while not self.q.empty():
                    n = self.q.get()
                    if n[:2] == job[:2]:
                        job = n
                    else:
                        rest.append(n)
                for n in rest:
                    self.q.put(n)
            try:
                if job[0] == "get":
                    data = solaar("get", self.info["codename"])
                    GLib.idle_add(self._build, data)
                else:
                    _s, key, val, label = job
                    GLib.idle_add(self.status, f"Lagrer {label} …")
                    solaar("set", self.info["codename"], key, str(val))
                    GLib.idle_add(self.status, f"{label}: lagret ✓")
            except Exception as e:  # noqa: BLE001
                GLib.idle_add(self.status, f"Feil: {e}")

    def put(self, key, val, label):
        self.q.put(("set", key, val, label))

    def _build(self, data):
        while (c := self.box.get_first_child()):
            self.box.remove(c)
        s = data.get("settings", {})
        bat = data.get("battery")
        head, hi = card(self.name, (f"Batteri: {bat} % · " if bat is not None else "") +
                        "Trådløs mus via Lightspeed. Innstillingene sendes rett til musen.")
        self.box.append(head)

        # profilmodus
        onboard = s.get("onboard_profiles", {})
        host = onboard.get("value") == "Disabled"
        pc, pi = card("Profilmodus")
        if onboard.get("choices"):
            dd = Gtk.DropDown.new_from_strings(["Styres herfra (kan endres)", "Innebygd profil fra G HUB (låst)"])
            dd.set_selected(0 if host else 1)
            choices = onboard["choices"]
            locked = next((c for c in choices if c != "Disabled"), choices[-1])

            def on_mode(d, _p):
                val = "Disabled" if d.get_selected() == 0 else locked
                self.put("onboard_profiles", val, "Profilmodus")
                self.perf.set_sensitive(d.get_selected() == 0)
            dd.connect("notify::selected", on_mode)
            pi.append(row("Hvem styrer DPI og rapporteringsfrekvens", dd,
                          "Musen bruker nå en låst profil fra G HUB. Velg «Styres herfra» for å endre "
                          "DPI og frekvens. Analogknappene kan alltid endres."))
        self.box.append(pc)

        # ytelse
        yc, yi = card("DPI og rapporteringsfrekvens")
        self.perf = yi
        dpi = s.get("dpi_extended", {}).get("value") or {}
        cur_dpi = int(dpi.get("0", 800)) if isinstance(dpi, dict) else 800
        spin = Gtk.SpinButton.new_with_range(100, 44000, 50)
        spin.set_value(cur_dpi)
        spin.connect("value-changed", lambda sp_: self._deb("dpi", lambda: self.put(
            "dpi_extended", int(sp_.get_value()), "DPI")))
        yi.append(row("DPI-følsomhet", spin, "Høyere DPI = raskere peker."))
        pr = Gtk.Box(spacing=6, halign=Gtk.Align.END)
        for v in (400, 800, 1600, 3200):
            b = Gtk.Button(label=str(v))
            b.connect("clicked", lambda _b, v=v: spin.set_value(v))
            pr.append(b)
        yi.append(pr)
        rr = s.get("report_rate_extended") or s.get("report_rate") or {}
        if rr.get("choices"):
            key = "report_rate_extended" if "report_rate_extended" in s else "report_rate"
            ch = rr["choices"]
            dd = Gtk.DropDown.new_from_strings([RATE_HZ.get(c, c) for c in ch])
            if rr.get("value") in ch:
                dd.set_selected(ch.index(rr["value"]))
            dd.connect("notify::selected", lambda d, _p: self.put(key, ch[d.get_selected()],
                                                                  "Rapporteringsfrekvens"))
            yi.append(row("Rapporteringsfrekvens", dd, "8000 Hz gir lavest forsinkelse, men bruker mer CPU og batteri."))
        yi.set_sensitive(host)
        self.box.append(yc)

        # analogknapper
        if any(k.startswith("analog-button-tuning_") for k in s):
            ac, ai = card("Analoge knapper",
                          "Juster hvor dypt knappen må trykkes, Rapid Trigger og klikkfølelse.")
            for idx, side in ((0, "Venstreknapp"), (1, "Høyreknapp")):
                hl = Gtk.Label(label=side, xalign=0)
                hl.add_css_class("heading")
                ai.append(hl)
                for kind, label, sub in (
                        ("actuation", "Aktiveringspunkt", "1 = grunt (lett), 10 = dypt"),
                        ("rapid-trigger", "Rapid Trigger", "1–5, høyere = mer følsom"),
                        ("haptics", "Klikk-haptikk", "0 = av, 5 = kraftigst")):
                    k = f"analog-button-tuning_{kind}-{idx}"
                    st = s.get(k)
                    if not st:
                        continue
                    sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, st.get("min") or 0,
                                                  st.get("max") or 10, 1)
                    sc.set_value(st.get("value") or 0)
                    sc.set_size_request(220, -1)
                    sc.set_draw_value(True)
                    sc.set_value_pos(Gtk.PositionType.RIGHT)
                    for m in range(int(st.get("min") or 0), int(st.get("max") or 10) + 1):
                        sc.add_mark(m, Gtk.PositionType.BOTTOM, None)
                    sc.connect("value-changed", lambda s_, k=k, lab=f"{side} {label.lower()}":
                               self._deb(k, lambda: self.put(k, int(s_.get_value()), lab)))
                    ai.append(row(label, sc, sub))
            self.box.append(ac)
        self.settings = s
        self.locked = next((c for c in onboard.get("choices") or [] if c != "Disabled"), None)
        self.status(f"{self.name}: innstillinger lest")
        GLib.idle_add(lambda: _rescan(self) or False)
        return False

    def factory_reset(self):
        s = getattr(self, "settings", None)
        if s is None:
            self.status(f"{self.name}: vent til innstillingene er lest, og prøv igjen")
            return
        if self.locked:
            self.put("onboard_profiles", self.locked, "Fabrikkprofil")
        for k in s:
            if k.startswith("analog-button-tuning_"):
                kind = k[len("analog-button-tuning_"):].rsplit("-", 1)[0]
                if kind in PROX2_ANALOG:
                    self.put(k, PROX2_ANALOG[kind], "Analogknapper")
        self.q.put(("get",))                    # les inn på nytt og vis

    _timers = {}

    def _deb(self, key, fn, ms=500):
        if key in self._timers:
            GLib.source_remove(self._timers[key])

        def fire():
            self._timers.pop(key, None)
            fn()
            return False
        self._timers[key] = GLib.timeout_add(ms, fire)


# --------------------------------------------------------------------------
# Fanen
# --------------------------------------------------------------------------
class LogitechPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        bar = Gtk.Box(spacing=8)
        for side in ("top", "start", "end"):
            getattr(bar, f"set_margin_{side}")(12)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, vexpand=True)
        sw = Gtk.StackSwitcher(stack=self.stack)
        bar.append(sw)
        import confirm
        self._reset_btn = confirm.reset_button(
            "Logitech-enhetene",
            "• Alle Logitech-enhetene som vises her, settes tilbake til fabrikkinnstillingene: profiler, "
            "DPI, rapporthyppighet og knappefunksjoner\n"
            "Endringene lagres i enhetenes minne.",
            self.factory_reset)
        self.status_lbl = Gtk.Label(xalign=1, hexpand=True, wrap=True)
        self.status_lbl.add_css_class("dim-label")
        bar.append(self.status_lbl)
        bar.append(self._reset_btn)
        self.append(bar)
        try:
            import apps_ui
            nd = apps_ui.need("logitech", text="Solaar viser batteri og styrer DPI, knapper og lys på trådløse "
                                               "Logitech-mus og -tastatur.")
            for side in ("top", "start", "end"):
                getattr(nd, f"set_margin_{side}")(12)
            self.append(nd)
        except Exception:  # noqa: BLE001
            pass
        try:
            import battery_ui
            bc = battery_ui.BatteryCard(logitech_only=True, title="Batteri")
            bc.set_margin_top(12)
            for side in ("start", "end"):
                getattr(bc, f"set_margin_{side}")(4)
            self.append(Adw.Clamp(maximum_size=__import__("theme").PAGE_WIDTH, child=bc))
        except Exception:  # noqa: BLE001
            pass
        self.append(self.stack)
        self.pages = []

        # ratbagd-enheter (raskt)
        pids = set()
        for dev in ratbag_devices():
            try:
                pg = RatbagPage(dev, self.status)
            except GLib.Error as e:
                self.status(f"Feil: {e.message or 'ukjent feil fra ratbagd'}")
                continue
            pids.add(pg.pid)
            short = pg.name.replace("Logitech ", "").replace("Gaming Mouse ", "") \
                .replace(" RGB MECHANICAL GAMING KEYBOARD", "")
            self.stack.add_titled(pg.widget, pg.pid or short, short)
            self.pages.append(pg)
        # Solaar-enheter som ratbagd ikke dekker (tregt – i bakgrunnen)
        self.status("Ser etter Logitech-enheter (trådløse kan ta noen sekunder) …")
        self._reset_btn.set_sensitive(bool(self.pages))

        def scan():
            try:
                devs = solaar("list")
            except Exception as e:  # noqa: BLE001
                GLib.idle_add(self.status, f"Solaar: {str(e) or type(e).__name__}")
                GLib.idle_add(self._add_solaar, [])
                return
            extra = [d for d in devs if d.get("pid") not in pids and d.get("online")]
            GLib.idle_add(self._add_solaar, extra)
        threading.Thread(target=scan, daemon=True).start()

    def _add_solaar(self, devs):
        for d in devs:
            pg = SolaarPage(d, self.status)
            short = d["name"].replace("Logitech ", "")
            self.stack.add_titled(pg.widget, "solaar-" + d["codename"], short)
            self.pages.append(pg)
        self._reset_btn.set_sensitive(bool(self.pages))
        if not self.pages:
            import ui
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, vexpand=True)
            box.append(ui.empty("ks-mouse-symbolic", "Ingen Logitech-enheter med innstillinger",
                                "Mus og tastatur som er slått av eller i dvale vises ikke – beveg musa eller trykk "
                                "en tast, og åpne fanen igjen. Hodesett styres ikke herfra.", compact=False))
            self.stack.add_named(box, "tom")
            self.status("")
        else:
            n = len(self.pages)
            self.status(f"{n} Logitech-enhet funnet" if n == 1 else f"{n} Logitech-enheter funnet")
        return False

    def status(self, text):
        self.status_lbl.set_label(text)
        return False

    def factory_reset(self):
        self.status("Tilbakestiller til fabrikkstandard …")
        for pg in self.pages:
            pg.factory_reset()


def _rescan(obj):
    """Si fra til vinduet at kortene er bygd på nytt (så de kan flyttes og få ny størrelse)."""
    w = obj if hasattr(obj, "get_root") else getattr(obj, "box", None)
    root = w.get_root() if w is not None else None
    fn = getattr(root, "rescan_cards", None)
    if fn:
        fn()
