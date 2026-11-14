"""MSI-fanen i Kontrollsenter – innstillinger som i MSI Center, for MSI-laptoper
(laget for Vector GP68HX 13VH) via kjernedriveren msi-ec.

Vises bare på MSI-maskiner. Endringer skrives av hjelpeprogrammet systemmonitor-msi
(root, fast liste over lovlige verdier), som settes opp én gang med passord.
"""
import glob
import os
import shutil
import subprocess
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

APP_DIR = os.path.dirname(os.path.abspath(__file__))
HELPER = "/usr/local/bin/systemmonitor-msi"
EC = os.environ.get("SYSTEMMONITOR_MSI_ROOT", "/sys/devices/platform/msi-ec")
DMI = "/sys/class/dmi/id"
DEMO = os.environ.get("SYSTEMMONITOR_MSI_DEMO") == "1"
DEMO_BAT = None


def _make_demo():
    """Demomodus: simulert Vector GP68HX 13VH (for å se fanen på en maskin som ikke er MSI)."""
    global EC, DMI, HELPER, DEMO_BAT
    root = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "systemmonitor-msi-demo")
    files = {"ec/shift_mode": "comfort", "ec/available_shift_modes": "eco\ncomfort\nturbo",
             "ec/fan_mode": "auto", "ec/available_fan_modes": "auto\nsilent\nadvanced",
             "ec/cooler_boost": "off", "ec/super_battery": "off", "ec/webcam": "on", "ec/webcam_block": "off",
             "ec/win_key": "right", "ec/fn_key": "left", "ec/fw_version": "15M1IMS1.110",
             "ec/cpu/realtime_temperature": "62", "ec/cpu/realtime_fan_speed": "41",
             "ec/gpu/realtime_temperature": "55", "ec/gpu/realtime_fan_speed": "38",
             "dmi/sys_vendor": "Micro-Star International Co., Ltd.", "dmi/product_name": "Vector GP68HX 13VH",
             "dmi/bios_version": "E15M1IMS.311", "bat/charge_control_end_threshold": "100"}
    for rel, val in files.items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if not os.path.exists(p):
            with open(p, "w") as f:
                f.write(val)
    EC, DMI = os.path.join(root, "ec"), os.path.join(root, "dmi")
    DEMO_BAT = os.path.join(root, "bat/charge_control_end_threshold")
    HELPER = os.path.join(APP_DIR, "systemmonitor-msi")


if DEMO:
    _make_demo()

# Brukerscenarioer som i MSI Center: (nøkkel, navn, beskrivelse, shift_mode, fan_mode, super_battery)
SCENARIOS = [
    ("extreme", "Ekstrem ytelse", "Maks ytelse for spill. CPU og GPU får full effekt, viftene går mer.",
     "turbo", "auto", "off"),
    ("balanced", "Balansert", "God ytelse og fornuftig støy – passer det meste.", "comfort", "auto", "off"),
    ("silent", "Stillegående", "Lavere ytelse og rolige vifter.", "comfort", "silent", "off"),
    ("battery", "Super Battery", "Lengst mulig batteritid. Ytelsen begrenses.", "eco", "silent", "on"),
]
CHARGE = [(100, "Best for mobilitet", "Lader til 100 %"),
          (80, "Balansert", "Lader til 80 % – anbefalt når laptopen står mye i strøm"),
          (60, "Best for batteriet", "Lader til 60 % – lengst levetid for batteriet")]
FAN_NAMES = {"auto": "Auto", "silent": "Stille", "basic": "Enkel", "advanced": "Avansert"}


def read(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def is_msi():
    if __import__("sys").platform == "win32":
        import winsupport
        return "micro-star" in winsupport.bios_info().get("SystemManufacturer", "").lower()
    return DEMO or "micro-star" in read(f"{DMI}/sys_vendor").lower() or os.environ.get("SYSTEMMONITOR_MSI_ROOT")


def ec(name):
    return read(os.path.join(EC, name))


def ec_ok():
    return os.path.isdir(EC) and bool(ec("shift_mode") or ec("fan_mode"))


def batteries():
    if DEMO:
        return [DEMO_BAT]
    return glob.glob("/sys/class/power_supply/BAT*/charge_control_end_threshold")


def helper(*args):
    if DEMO:                                   # demo: skriv bare til de simulerte filene
        if args[0] == "charge":
            with open(DEMO_BAT, "w") as f:
                f.write(args[1])
            return True, ""
        if args[0] == "gpu":
            return True, ""
        r = subprocess.run([HELPER, *args], capture_output=True, text=True,
                           env={**os.environ, "SYSTEMMONITOR_MSI_ROOT": EC})
        return r.returncode == 0, r.stderr.strip()
    try:
        r = subprocess.run(["sudo", "-n", HELPER, *args], capture_output=True, text=True, timeout=60)
        return r.returncode == 0, (r.stderr or r.stdout).strip()
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)


def kbd_proxy():
    try:
        return Gio.DBusProxy.new_for_bus_sync(Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, None,
                                              "org.freedesktop.UPower", "/org/freedesktop/UPower/KbdBacklight",
                                              "org.freedesktop.UPower.KbdBacklight", None)
    except GLib.Error:
        return None


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
    b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
    b.append(Gtk.Label(label=label, xalign=0))
    if sub:
        s = Gtk.Label(label=sub, xalign=0, wrap=True)
        s.add_css_class("caption")
        s.add_css_class("dim-label")
        b.append(s)
    r.append(b)
    widget.set_valign(Gtk.Align.CENTER)
    r.append(widget)
    return r


class MsiPage(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(12)
        self.set_child(Adw.Clamp(maximum_size=1000, child=box))
        self.box = box
        self._quiet = False
        self.build()

    def _status(self, text):
        self.status.set_label(text)
        return False

    def build(self):
        while (c := self.box.get_first_child()):
            self.box.remove(c)
        model = " ".join(x for x in (read(f"{DMI}/sys_vendor").replace("Micro-Star International Co., Ltd.", "MSI"),
                                     read(f"{DMI}/product_name")) if x) or "MSI-laptop"

        head, hi = card(model)
        info = [f"EC-fastvare {ec('fw_version')}" if ec("fw_version") else "",
                f"BIOS {read(DMI + '/bios_version')}" if read(DMI + "/bios_version") else ""]
        lab = Gtk.Label(label=" · ".join(i for i in info if i), xalign=0)
        lab.add_css_class("dim-label")
        hi.append(lab)
        top = Gtk.Box(spacing=8)
        self.status = Gtk.Label(xalign=0, hexpand=True, wrap=True)
        top.append(self.status)
        if DEMO:
            self.status.set_label("DEMO – simulerte verdier, ingenting på PC-en endres")
        import confirm
        top.append(confirm.reset_button(
            "MSI-innstillingene",
            "• Brukerscenario: Balansert\n• Vifter: Auto, Cooler Boost av\n• Ladegrense: 100 %\n"
            "• Webkamera på, Fn/Win-tastene som fra fabrikken",
            self.factory_reset))
        hi.append(top)
        self.box.append(head)

        # Mangler driver eller oppsett?
        if not ec_ok():
            c, i = card("MSI-driveren (msi-ec) mangler",
                        "Linux trenger kjernedriveren msi-ec for å styre MSI-funksjonene. Driveren som følger "
                        "med kjernen støtter ikke alle modeller (bl.a. Vector GP68HX), så den nyeste "
                        "utgaven hentes fra github.com/BeardOverflow/msi-ec og bygges for kjernen din.")
            b = Gtk.Button(label="Installer MSI-driver", halign=Gtk.Align.START)
            b.add_css_class("suggested-action")
            b.connect("clicked", lambda *_: self._setup(driver=True))
            if os.path.exists("/run/ostree-booted"):
                b.set_sensitive(False)
                b.set_tooltip_text("Bazzite/Silverblue kan ikke bygge DKMS-drivere")
            i.append(b)
            self.box.append(c)
            self._status("Installer driveren for å få tilgang til innstillingene")
            return
        if not os.path.exists(HELPER):
            c, i = card("Aktiver MSI-styring",
                        "Engangsoppsett: lar Kontrollsenter endre MSI-innstillingene. Du blir spurt om passord én gang.")
            b = Gtk.Button(label="Aktiver MSI-styring", halign=Gtk.Align.START)
            b.add_css_class("suggested-action")
            b.connect("clicked", lambda *_: self._setup(driver=False))
            i.append(b)
            self.box.append(c)

        # Brukerscenario
        c, i = card("Brukerscenario", "Som i MSI Center: velg balansen mellom ytelse, støy og batteritid.")
        grid = Gtk.Box(homogeneous=True)
        grid.add_css_class("linked")
        self.sc_btns = {}
        first = None
        avail = ec("available_shift_modes").split() or ["turbo", "comfort", "eco"]
        for key, name, desc, sm, fm, sb in SCENARIOS:
            if sm not in avail:
                continue
            b = Gtk.ToggleButton(label=name, tooltip_text=desc)
            b.set_size_request(-1, 44)
            if first:
                b.set_group(first)
            first = first or b
            b.connect("toggled", self._on_scenario, key)
            grid.append(b)
            self.sc_btns[key] = b
        i.append(grid)
        self.sc_desc = Gtk.Label(xalign=0, wrap=True)
        self.sc_desc.add_css_class("caption")
        i.append(self.sc_desc)
        self.box.append(c)

        # Vifter
        c, i = card("Vifter og temperatur")
        self.temps = Gtk.Label(xalign=0)
        self.temps.add_css_class("title-4")
        self.temps.add_css_class("numeric")
        i.append(self.temps)
        fans = ec("available_fan_modes").split() or ["auto"]
        self.fan_keys = fans
        self.fan_dd = Gtk.DropDown.new_from_strings([FAN_NAMES.get(f, f) for f in fans])
        self.fan_dd.connect("notify::selected", lambda d, _p: self._set("fan_mode", self.fan_keys[d.get_selected()]))
        i.append(row("Viftemodus", self.fan_dd, "Auto følger temperaturen. Stille holder viftene lave."))
        if ec("cooler_boost"):
            self.boost = Gtk.Switch()
            self.boost.connect("notify::active", lambda s, _p: self._set("cooler_boost", "on" if s.get_active() else "off"))
            i.append(row("Cooler Boost", self.boost, "Alle vifter på maks – for tunge spill eller når laptopen blir varm."))
        else:
            self.boost = None
        self.box.append(c)

        # Battery Master
        if batteries():
            c, i = card("Battery Master", "Begrens hvor høyt batteriet lades – det gir batteriet lengre levetid.")
            cb = Gtk.Box(homogeneous=True)
            cb.add_css_class("linked")
            self.ch_btns = {}
            first = None
            for val, name, desc in CHARGE:
                b = Gtk.ToggleButton(label=f"{name} ({val} %)", tooltip_text=desc)
                if first:
                    b.set_group(first)
                first = first or b
                b.connect("toggled", lambda b_, v=val: b_.get_active() and not self._quiet and self._charge(v))
                cb.append(b)
                self.ch_btns[val] = b
            i.append(cb)
            self.ch_lbl = Gtk.Label(xalign=0)
            self.ch_lbl.add_css_class("caption")
            i.append(self.ch_lbl)
            self.box.append(c)
        else:
            self.ch_btns = {}

        # GPU-modus
        c, i = card("GPU-modus", "Hvilket skjermkort som brukes. Krever omstart etter endring.")
        tool = (shutil.which("envycontrol", path="/usr/local/bin:/usr/bin:" + os.environ.get("PATH", ""))
                or shutil.which("supergfxctl") or (DEMO and getattr(self, "_demo_envy", False)))
        if tool:
            mode = self._gpu_mode(tool)
            if mode:
                cur = Gtk.Label(label=f"I bruk nå: {mode}", xalign=0)
                cur.add_css_class("caption")
                i.append(cur)
            gb = Gtk.Box(homogeneous=True)
            gb.add_css_class("linked")
            for mode, name in (("integrated", "Bare Intel (lengst batteritid)"), ("hybrid", "Hybrid (MSHybrid)"),
                               ("nvidia", "Bare NVIDIA (best ytelse)")):
                b = Gtk.Button(label=name)
                b.connect("clicked", lambda *_, m=mode: self._gpu(m))
                gb.append(b)
            i.append(gb)
        else:
            lab = Gtk.Label(label="For å bytte GPU-modus fra Linux trengs verktøyet EnvyControl. "
                                  "Ren dGPU-modus (MUX) kan også velges i BIOS-oppsettet.", xalign=0, wrap=True)
            lab.add_css_class("dim-label")
            i.append(lab)
            eb = Gtk.Button(label="Installer EnvyControl", halign=Gtk.Align.START)
            eb.add_css_class("suggested-action")
            eb.set_tooltip_text("Henter nyeste versjon fra github.com/bayasdev/envycontrol (passord én gang)")
            eb.connect("clicked", lambda *_: self._install_envy())
            i.append(eb)
        self.box.append(c)

        # Tastatur og webkamera
        c, i = card("Tastatur og webkamera")
        self.kbd = kbd_proxy()
        self.kbd_max = 0
        if self.kbd:
            try:
                self.kbd_max = self.kbd.call_sync("GetMaxBrightness", None, Gio.DBusCallFlags.NONE, 3000, None).unpack()[0]
            except GLib.Error:
                self.kbd_max = 0
        if self.kbd_max:
            sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, self.kbd_max, 1)
            sc.set_size_request(220, -1)
            for m in range(self.kbd_max + 1):
                sc.add_mark(m, Gtk.PositionType.BOTTOM, None)
            try:
                sc.set_value(self.kbd.call_sync("GetBrightness", None, Gio.DBusCallFlags.NONE, 3000, None).unpack()[0])
            except GLib.Error:
                pass
            sc.connect("value-changed", lambda s: self.kbd.call("SetBrightness", GLib.Variant("(i)", (int(s.get_value()),)),
                                                                Gio.DBusCallFlags.NONE, 3000, None, None, None))
            i.append(row("Bakgrunnslys på tastaturet", sc))
        if ec("win_key") or ec("fn_key"):
            self.fnwin = Gtk.Switch()
            self.fnwin.connect("notify::active", lambda s, _p: self._fnwin(s.get_active()))
            i.append(row("Bytt Fn- og Windows-tasten", self.fnwin,
                         "Nyttig hvis du er vant til et annet tastatur."))
        else:
            self.fnwin = None
        if ec("webcam"):
            self.cam = Gtk.Switch()
            self.cam.connect("notify::active", lambda s, _p: self._set("webcam", "on" if s.get_active() else "off"))
            i.append(row("Webkamera", self.cam, "Slå av for å sperre kameraet helt (personvern)."))
        else:
            self.cam = None
        self.box.append(c)

        self.refresh()
        if not getattr(self, "_ticking", False):          # bare én oppdateringsløkke
            self._ticking = True
            GLib.timeout_add_seconds(2, self._tick)

    # --- les verdier ------------------------------------------------------------
    def _tick(self):
        ct, gt = ec("cpu/realtime_temperature"), ec("gpu/realtime_temperature")
        cf, gf = ec("cpu/realtime_fan_speed"), ec("gpu/realtime_fan_speed")
        parts = []
        if ct:
            parts.append(f"CPU {ct} °C" + (f" · vifte {cf} %" if cf else ""))
        if gt:
            parts.append(f"GPU {gt} °C" + (f" · vifte {gf} %" if gf else ""))
        self.temps.set_label("   |   ".join(parts) or "Temperatur ikke tilgjengelig")
        return True

    def refresh(self):
        self._quiet = True
        sm, fm, sb = ec("shift_mode"), ec("fan_mode"), ec("super_battery")
        cur = None
        for key, _n, desc, s_, f_, b_ in SCENARIOS:
            if s_ == sm and (b_ == sb or not sb) and (f_ == fm or key in ("extreme", "balanced") and fm == "auto"):
                cur = key
                break
        cur = cur or ("balanced" if sm == "comfort" else "extreme" if sm == "turbo" else "battery" if sm == "eco" else None)
        if cur in self.sc_btns:
            self.sc_btns[cur].set_active(True)
            self.sc_desc.set_label(next(s[2] for s in SCENARIOS if s[0] == cur))
        if fm in self.fan_keys:
            self.fan_dd.set_selected(self.fan_keys.index(fm))
        if self.boost:
            self.boost.set_active(ec("cooler_boost") == "on")
        if self.cam:
            self.cam.set_active(ec("webcam") == "on")
        if self.fnwin:
            self.fnwin.set_active(ec("win_key") == "left")
        if self.ch_btns:
            lim = read(batteries()[0]) if batteries() else ""
            if lim.isdigit():
                v = int(lim)
                if v in self.ch_btns:
                    self.ch_btns[v].set_active(True)
                self.ch_lbl.set_label(f"Batteriet lades nå til {v} %")
        self._quiet = False
        self._tick()

    # --- endre -------------------------------------------------------------------
    def _run(self, args, msg):
        def work():
            ok, err = helper(*args)
            GLib.idle_add(self._status, f"{msg} ✓" if ok else f"Feil: {err}")
            GLib.idle_add(self.refresh)
        threading.Thread(target=work, daemon=True).start()

    def _set(self, attr, val):
        if not self._quiet:
            self._run(["set", attr, val], "Lagret")

    def _on_scenario(self, btn, key):
        if self._quiet or not btn.get_active():
            return
        _k, name, desc, sm, fm, sb = next(s for s in SCENARIOS if s[0] == key)
        self.sc_desc.set_label(desc)

        def work():
            errs = []
            for args in (["set", "shift_mode", sm], ["set", "fan_mode", fm] if fm in self.fan_keys else None,
                         ["set", "super_battery", sb] if ec("super_battery") else None):
                if args:
                    ok, err = helper(*args)
                    if not ok:
                        errs.append(err)
            GLib.idle_add(self._status, f"Brukerscenario: {name} ✓" if not errs else f"Feil: {errs[0]}")
            GLib.idle_add(self.refresh)
        threading.Thread(target=work, daemon=True).start()

    def _charge(self, v):
        self._run(["charge", str(v)], f"Ladegrense {v} %")

    def _fnwin(self, swap):
        if self._quiet:
            return
        self._run(["set", "win_key", "left" if swap else "right"], "Tastene er byttet" if swap else "Tastene er som fra fabrikken")

    def _gpu(self, mode):
        self._run(["gpu", mode], "GPU-modus endret – start PC-en på nytt")

    @staticmethod
    def _gpu_mode(tool):
        """Gjeldende GPU-modus (envycontrol --query), oversatt."""
        if DEMO or not isinstance(tool, str) or not tool.endswith("envycontrol"):
            return "Hybrid (MSHybrid)" if DEMO else None
        try:
            out = subprocess.run([tool, "--query"], capture_output=True, text=True, timeout=15).stdout.strip().lower()
        except (OSError, subprocess.SubprocessError):
            return None
        return {"integrated": "Bare Intel", "hybrid": "Hybrid (MSHybrid)", "nvidia": "Bare NVIDIA"}.get(out)

    def _install_envy(self):
        if DEMO:
            self._demo_envy = True
            self.build()
            self._status("DEMO: EnvyControl ville blitt installert nå ✓")
            return
        self._status("Installerer EnvyControl – skriv inn passordet ditt …")
        user = os.environ.get("USER") or os.getlogin()

        def work():
            r = subprocess.run(["pkexec", "/bin/bash", os.path.join(APP_DIR, "install-msi.sh"), user,
                                "--envycontrol"], capture_output=True, text=True)
            ok = r.returncode == 0
            msg = (r.stderr or r.stdout).strip().splitlines()[-1:] if not ok else []
            GLib.idle_add(self.build)
            GLib.idle_add(self._status, "EnvyControl er installert ✓" if ok else
                          f"Feilet: {msg[0] if msg else 'avbrutt'}")
        threading.Thread(target=work, daemon=True).start()

    def factory_reset(self):
        def work():
            for args in (["set", "shift_mode", "comfort"], ["set", "fan_mode", "auto"],
                         ["set", "cooler_boost", "off"], ["set", "super_battery", "off"],
                         ["set", "webcam", "on"], ["set", "win_key", "right"], ["charge", "100"]):
                if args[0] == "charge" and not batteries():
                    continue
                if args[0] == "set" and not ec(args[1]):
                    continue
                helper(*args)
            GLib.idle_add(self._status, "Tilbakestilt til fabrikkstandard ✓")
            GLib.idle_add(self.refresh)
        threading.Thread(target=work, daemon=True).start()

    def _setup(self, driver):
        self._status("Venter på passord …" if not driver else "Installerer driver – dette kan ta et par minutter …")
        user = os.environ.get("USER") or os.getlogin()

        def work():
            args = ["pkexec", "/bin/bash", os.path.join(APP_DIR, "install-msi.sh"), user] + (["--driver"] if driver else [])
            r = subprocess.run(args, capture_output=True, text=True)
            ok = r.returncode == 0
            msg = (r.stderr or r.stdout).strip().splitlines()[-1:] if not ok else []
            GLib.idle_add(self._status, "Ferdig ✓" if ok else f"Feilet: {msg[0] if msg else 'avbrutt'}")
            GLib.idle_add(self.build)
        threading.Thread(target=work, daemon=True).start()
