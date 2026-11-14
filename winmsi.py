"""MSI-fanen på Windows – brukerscenario, Cooler Boost, viftemodus, Battery Master, Super Battery og webkamera
via MSI sitt eget WMI-grensesnitt (MSI_ACPI, det samme som MSI Center bruker). Selve kallene gjøres av
msi_wmi.ps1, som bare skriver faste verdier til faste adresser på kjent EC-fastvare.

Krever Windows administratorrett for WMI-kallene, brukes den planlagte oppgaven «Kontrollsenter - MSI» som
installasjonsfilen lager (kjører skriptet fra Program Files med høyeste rettigheter, uten UAC-spørsmål)."""
import json
import os
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk  # noqa: E402

import i18n  # noqa: E402
import winsupport as WS  # noqa: E402

APP_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(APP_DIR, "msi_wmi.ps1")
DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Kontrollsenter")
REQ, RES = os.path.join(DIR, "msi-req.json"), os.path.join(DIR, "msi-res.json")
TASK = "Kontrollsenter - MSI"

# Registerkart fra msi-ec (CONF_G2_10 – Vector GP68 HX 12V/13V, EC-fastvare 15M1IMS1/15M1IMS2)
A_SHIFT, A_FAN, A_CHARGE, A_BOOST, A_SB, A_CAM = 0xd2, 0xd4, 0xd7, 0x98, 0xeb, 0x2e
A_CPU_T, A_CPU_F, A_GPU_T, A_GPU_F = 0x68, 0x71, 0x80, 0x89
SHIFT = {"turbo": 0xc4, "comfort": 0xc1, "eco": 0xc2}
SHIFT_R = {0xc4: "turbo", 0xc0: "turbo", 0xc1: "comfort", 0xc2: "eco"}
FAN = {"auto": 0x0d, "silent": 0x1d, "advanced": 0x8d}
FAN_R = {v: k for k, v in FAN.items()}
BITS = {A_BOOST: 0x80, A_SB: 0x0f, A_CAM: 0x02}

_lock = threading.Lock()
_mode = {"via": None}          # "direkte" eller "oppgave" når det har virket


def _denied(err):
    e = (err or "").lower()
    return any(s in e for s in ("denied", "nektet", "0x80041003", "0x80070005", "ikke tilgang", "access"))


def _read_res():
    try:
        with open(RES, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def call(ops, timeout=40):
    """Kjør en liste operasjoner i msi_wmi.ps1. Returnerer svaret som ordbok (alltid med «ok»)."""
    with _lock:
        os.makedirs(DIR, exist_ok=True)
        with open(REQ, "w", encoding="utf-8") as f:
            json.dump({"ops": ops}, f)
        r = None
        if _mode["via"] != "oppgave":
            try:
                os.remove(RES)
            except OSError:
                pass
            code, out = WS.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", SCRIPT,
                                "-Req", REQ, "-Res", RES], timeout)
            r = _read_res() or {"ok": False, "error": out.strip()[-400:] or "ingen svar fra PowerShell"}
            if r.get("ok"):
                _mode["via"] = "direkte"
                return r
        # trenger (trolig) administratorrett → den planlagte oppgaven (laget av installasjonsfilen). Uten
        # administratorrett kan Windows både nekte og skjule MSI_ACPI, så alle feil prøves på nytt her.
        try:
            os.remove(RES)
        except OSError:
            pass
        code, out = WS.run(["schtasks", "/run", "/tn", TASK], 15)
        if code != 0:
            if r is not None and not _denied(r.get("error")) and "finnes ikke" not in r.get("error", ""):
                return r
            return {"ok": False, "needs_task": True,
                    "error": (r or {}).get("error", "") or "oppgaven «Kontrollsenter - MSI» mangler"}
        end = time.time() + timeout
        while time.time() < end:
            time.sleep(0.4)
            res = _read_res()
            if res is not None:
                if res.get("ok"):
                    _mode["via"] = "oppgave"
                return res
        return {"ok": False, "error": "Oppgaven «Kontrollsenter - MSI» svarte ikke"}


def state():
    """Les alt på én gang: {ok, fw, known, shift, fan, charge, boost, sb, cam, cpu_t, cpu_f, gpu_t, gpu_f, rpm}."""
    addrs = [A_SHIFT, A_FAN, A_CHARGE, A_BOOST, A_SB, A_CAM, A_CPU_T, A_CPU_F, A_GPU_T, A_GPU_F]
    r = call([["get", a] for a in addrs] + [["fan"]])
    if not r.get("ok"):
        return r
    vals = {x["a"]: x["v"] for x in r.get("results", []) if "a" in x and x.get("s") == 1}
    rpm = next((x["fan"] for x in r.get("results", []) if "fan" in x), [])
    r.update(shift=SHIFT_R.get(vals.get(A_SHIFT)), fan=FAN_R.get(vals.get(A_FAN)),
             charge=(vals[A_CHARGE] & 0x7f) if A_CHARGE in vals else None,
             boost=bool(vals.get(A_BOOST, 0) & 0x80), sb=bool(vals.get(A_SB, 0) & 0x0f),
             cam=bool(vals.get(A_CAM, 0) & 0x02), cpu_t=vals.get(A_CPU_T), cpu_f=vals.get(A_CPU_F),
             gpu_t=vals.get(A_GPU_T), gpu_f=vals.get(A_GPU_F), rpm=rpm, raw=vals)
    return r


def set_shift(mode):
    return call([["set", A_SHIFT, SHIFT[mode]]])


def set_fan(mode):
    return call([["set", A_FAN, FAN[mode]]])


def set_charge(pct):
    pct = max(50, min(100, int(pct)))
    return call([["set", A_CHARGE, pct | 0x80]])


def set_bit(addr, on):
    assert addr in BITS
    return call([["bit", addr, bool(on)]])


def scenario(sm, fm, sb):
    return call([["set", A_SHIFT, SHIFT[sm]], ["set", A_FAN, FAN[fm]], ["bit", A_SB, sb == "on"]])


def diagnose():
    """Kort tekst til diagnoserapporten."""
    r = state()
    if not r.get("ok"):
        return f"MSI WMI: FEIL – {r.get('error')}" + (" (oppgaven mangler)" if r.get("needs_task") else "")
    return (f"MSI WMI: OK via {_mode['via']} · EC {r.get('fw')} · kjent={r.get('known')} · admin={r.get('admin')}\n"
            f"  rå: {', '.join(f'0x{a:02x}=0x{v:02x}' for a, v in sorted(r['raw'].items()))} · rpm {r.get('rpm')}")


# --------------------------------------------------------------------------
# Siden
# --------------------------------------------------------------------------
class MsiWinPage(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        import msi
        self.M = msi
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(self.box, f"set_margin_{side}")(12)
        self.set_child(self.box)
        self._quiet = False
        self._busy = False
        self._built = False
        bi = WS.bios_info()
        c, i = msi.card(bi.get("SystemProductName", "MSI"),
                        f"{bi.get('BaseBoardProduct', '')} · BIOS {bi.get('BIOSVersion', '')}")
        self.info = Gtk.Label(xalign=0, wrap=True, selectable=True)
        self.info.add_css_class("caption")
        i.append(self.info)
        self.status = Gtk.Label(label=i18n.tr("Kobler til MSI-kontrolleren …"), xalign=0, wrap=True)
        self.status.add_css_class("dim-label")
        i.append(self.status)
        btns = Gtk.Box(spacing=8)
        for label, fn in (("Åpne MSI Center", lambda *_: WS.run(
                ["explorer.exe", "shell:AppsFolder\\9426MICRO-STARINTERNATION.MSICenter_kzh8wxbdkxb8p!App"])),
                          ("Strøm og batteri", lambda *_: WS.open_uri("ms-settings:powersleep"))):
            b = Gtk.Button(label=i18n.tr(label))
            b.connect("clicked", fn)
            btns.append(b)
        i.append(btns)
        self.box.append(c)
        self.controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.box.append(self.controls)
        self._load()
        GLib.timeout_add_seconds(6, self._tick)

    # ---- lasting -------------------------------------------------------
    def _bg(self, work, done):
        threading.Thread(target=lambda: GLib.idle_add(lambda: (done(work()), False)[1]), daemon=True).start()

    def _load(self):
        self._busy = True
        self._bg(state, self._show)

    def _tick(self):
        # via oppgaven (administrator) startes PowerShell hver gang – oppdater sjeldnere da
        self._n = getattr(self, "_n", 0) + 1
        if _mode["via"] == "oppgave" and self._n % 3:
            return True
        if self.get_mapped() and not self._busy and self._built:
            self._load()
        return True

    def _battery(self):
        try:
            import psutil
            b = psutil.sensors_battery()
            if b:
                return f"🔋 {b.percent:.0f} % · " + (i18n.tr("lader") if b.power_plugged else i18n.tr("på batteri"))
        except Exception:  # noqa: BLE001
            pass
        return ""

    def _show(self, r):
        self._busy = False
        bat = self._battery()
        if not r.get("ok"):
            if r.get("needs_task"):
                msg = i18n.tr("Windows krever administratorrett for MSI-innstillingene. Kjør installasjonsfilen "
                              "(Kontrollsenter-Setup.exe) på nytt – da lages en oppgave som gir Kontrollsenter "
                              "tilgang uten å spørre hver gang.")
            else:
                msg = i18n.tr("Fikk ikke kontakt med MSI-kontrolleren:") + " " + str(r.get("error", ""))
            self.status.set_label(msg)
            self.info.set_label(bat)
            return
        fw = r.get("fw", "")
        self.info.set_label(" · ".join(x for x in (f"EC-fastvare {fw}", bat) if x))
        if not r.get("known"):
            self.status.set_label(i18n.tr("EC-fastvaren {} er ikke kjent for Kontrollsenter, så ingenting endres "
                                          "herfra. Bruk MSI Center.").replace("{}", fw))
            return
        self.status.set_label("")
        self.status.set_visible(False)
        if not self._built:
            self._build()
        self._refresh(r)

    def _build(self):
        M = self.M
        self._built = True
        # Brukerscenario
        c, i = M.card("Brukerscenario", "Som i MSI Center: velg balansen mellom ytelse, støy og batteritid.")
        grid = Gtk.Box(homogeneous=True)
        grid.add_css_class("linked")
        self.sc_btns, first = {}, None
        for key, name, desc, sm, fm, sb in M.SCENARIOS:
            b = Gtk.ToggleButton(label=i18n.tr(name), tooltip_text=i18n.tr(desc))
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
        self.controls.append(c)

        # Vifter og temperatur
        c, i = M.card("Vifter og temperatur")
        self.temps = Gtk.Label(xalign=0, wrap=True)
        self.temps.add_css_class("title-4")
        self.temps.add_css_class("numeric")
        i.append(self.temps)
        self.fan_keys = list(FAN)
        self.fan_dd = Gtk.DropDown.new_from_strings([i18n.tr(M.FAN_NAMES.get(f, f)) for f in self.fan_keys])
        self.fan_dd.connect("notify::selected", lambda d, _p: self._apply(
            lambda: set_fan(self.fan_keys[d.get_selected()])))
        i.append(M.row("Viftemodus", self.fan_dd, "Auto følger temperaturen. Stille holder viftene lave."))
        self.boost = Gtk.Switch()
        self.boost.connect("notify::active", lambda s, _p: self._apply(lambda: set_bit(A_BOOST, s.get_active())))
        i.append(M.row("Cooler Boost", self.boost, "Alle vifter på maks – for tunge spill eller når laptopen blir varm."))
        self.controls.append(c)

        # Battery Master
        c, i = M.card("Battery Master", "Begrens hvor høyt batteriet lades – det gir batteriet lengre levetid.")
        cb = Gtk.Box(homogeneous=True)
        cb.add_css_class("linked")
        self.ch_btns, first = {}, None
        for val, name, desc in M.CHARGE:
            b = Gtk.ToggleButton(label=f"{i18n.tr(name)} ({val} %)", tooltip_text=i18n.tr(desc))
            if first:
                b.set_group(first)
            first = first or b
            b.connect("toggled", lambda b_, v=val: b_.get_active() and self._apply(lambda: set_charge(v)))
            cb.append(b)
            self.ch_btns[val] = b
        i.append(cb)
        self.sb = Gtk.Switch()
        self.sb.connect("notify::active", lambda s, _p: self._apply(lambda: set_bit(A_SB, s.get_active())))
        i.append(M.row("Super Battery", self.sb, "Sparer strøm ved å begrense ytelsen."))
        self.controls.append(c)

        # Annet
        c, i = M.card("Annet")
        self.cam = Gtk.Switch()
        self.cam.connect("notify::active", lambda s, _p: self._apply(lambda: set_bit(A_CAM, s.get_active())))
        i.append(M.row("Webkamera", self.cam, "Slå av kameraet helt (som Fn-tasten for kamera)."))
        self.msg = Gtk.Label(xalign=0, wrap=True)
        self.msg.add_css_class("caption")
        self.msg.add_css_class("dim-label")
        i.append(self.msg)
        self.controls.append(c)

    def _refresh(self, r):
        self._quiet = True
        try:
            cur = next((s[0] for s in self.M.SCENARIOS
                        if s[3] == r.get("shift") and s[4] == r.get("fan") and (s[5] == "on") == r.get("sb")), None)
            for key, b in self.sc_btns.items():
                b.set_active(key == cur)
            self.sc_desc.set_label(i18n.tr(next(s[2] for s in self.M.SCENARIOS if s[0] == cur)) if cur else
                                   i18n.tr("Egendefinert"))
            if r.get("fan") in self.fan_keys:
                self.fan_dd.set_selected(self.fan_keys.index(r["fan"]))
            self.boost.set_active(r.get("boost", False))
            self.sb.set_active(r.get("sb", False))
            self.cam.set_active(r.get("cam", False))
            ch = r.get("charge")
            for v, b in self.ch_btns.items():
                b.set_active(v == ch)
            rpm = r.get("rpm") or []
            parts = []
            for name, t, f, n in (("CPU", r.get("cpu_t"), r.get("cpu_f"), 0), ("GPU", r.get("gpu_t"), r.get("gpu_f"), 1)):
                if t:
                    s = f"{name} {t} °C"
                    if f is not None:
                        s += f" · {i18n.tr('vifte')} {f} %"
                    if len(rpm) > n and rpm[n]:
                        s += f" ({rpm[n]} rpm)"
                    parts.append(s)
            self.temps.set_label("   ".join(parts))
        finally:
            self._quiet = False

    # ---- endringer -----------------------------------------------------
    def _apply(self, fn):
        if self._quiet:
            return
        self.msg.set_label(i18n.tr("Lagrer …"))

        def done(r):
            if r.get("ok"):
                self.msg.set_label(i18n.tr("Lagret ✓"))
            else:
                self.msg.set_label(i18n.tr("Kunne ikke endre:") + " " + str(r.get("error", "")))
            self._load()
        self._bg(fn, done)

    def _on_scenario(self, btn, key):
        if self._quiet or not btn.get_active():
            return
        _k, _name, desc, sm, fm, sb = next(s for s in self.M.SCENARIOS if s[0] == key)
        self.sc_desc.set_label(i18n.tr(desc))
        self._apply(lambda: scenario(sm, fm, sb))
