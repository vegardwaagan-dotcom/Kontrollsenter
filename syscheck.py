"""Systemsjekk for Systemmonitor: finner vanlige feil og retter dem automatisk.

Hver sjekk returnerer en liste med Result. En Result kan ha en fix() som retter
feilen. Rettinger er alltid begrenset til kjente, trygge handlinger, og brukeren
bekrefter dem før de kjøres.
"""
import glob
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

HOME = Path.home()
import deps  # noqa: E402

SYSTEM_TRCC = "/usr/bin/trcc"          # følger med Bazzite
TRCC = deps.find_trcc() or SYSTEM_TRCC
APP_DIR = os.path.dirname(os.path.abspath(__file__))
OPENRGB_CFG = HOME / ".var/app/org.openrgb.OpenRGB/config/OpenRGB/OpenRGB.json"
SOLAAR_CFG = HOME / ".var/app/io.github.pwr_solaar.solaar/config/solaar/config.yaml"
SOLAAR = ["flatpak", "run", "--command=solaar", "io.github.pwr_solaar.solaar"]
TRCC_AUTOSTART = HOME / ".config/autostart/systemmonitor-trcc.desktop"
OLD_TRCC_AUTOSTART = HOME / ".config/autostart/trcc.desktop"
LOGI_DETECTORS = {"c332": ["Logitech G502 Proteus Spectrum Gaming Mouse"],
                  "c33f": ["Logitech G815 RGB Mechanical Gaming Keyboard"]}
GENERIC_LOGI_DETECTOR = "Logitech HID++ 2.0"


class Result:
    def __init__(self, title, level, detail="", fix=None, fix_label=None, password=False,
                 root_cmds=None):
        self.title, self.level, self.detail = title, level, detail
        self.fix, self.fix_label = fix, fix_label
        self.root_cmds = root_cmds or []          # kjøres samlet som root (én passordforespørsel)
        self.password = password or bool(self.root_cmds)

    @property
    def fixable(self):
        return bool(self.fix or self.root_cmds)


def run(cmd, timeout=30, **kw):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kw)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


def must(cmd, timeout=120):
    code, out = run(cmd, timeout=timeout)
    if code != 0:
        lines = [ln for ln in out.strip().splitlines() if ln.strip()]
        raise RuntimeError(lines[-1] if lines else f"{cmd[0]} feilet")
    return out


def flatpak_installed(app):
    return run(["flatpak", "info", app], timeout=15)[0] == 0


def ratbag_pids():
    try:
        import logitech as L
        out = {}
        for d in L.ratbag_devices():
            model = L.getp(d, "Model")
            parts = model.split(":")
            if len(parts) >= 3:
                out[parts[2].lower()] = L.getp(d, "Name")
        return out
    except Exception:  # noqa: BLE001
        return {}


# --------------------------------------------------------------------------
# Sjekker
# --------------------------------------------------------------------------
def _unit_reason(args, unit):
    _c, out = run(["systemctl", *args, "show", "-p", "Result", "-p", "ExecMainStatus", "--value", unit], 10)
    vals = [v for v in out.split() if v]
    why = {"exit-code": "avsluttet med feilkode", "signal": "ble drept", "timeout": "brukte for lang tid",
           "core-dump": "krasjet", "start-limit-hit": "startet for mange ganger"}.get(vals[0] if vals else "", "")
    code = f" (kode {vals[1]})" if len(vals) > 1 and vals[1] not in ("0", "") else ""
    name = unit.split("@")[0].replace("app-", "").replace(".service", "")
    name = name.replace("\\x2d", "-")
    return f"• {name}: {why or 'feilet'}{code}"


def check_failed_units():
    import shlex
    res = []
    for scope, args in (("bruker", ["--user"]), ("system", [])):
        code, out = run(["systemctl", *args, "--failed", "--plain", "--no-legend"])
        units = [ln.split()[0] for ln in out.splitlines() if ln.strip() and not ln.startswith("0 ")]
        if not units:
            continue
        detail = "\n".join(_unit_reason(args, u) for u in units[:8])
        detail += "\nNullstilling fjerner feilstatusen. Kommer feilen tilbake, sjekk loggen: journalctl" + \
                  (" --user" if args else "") + f" -u {units[0]}"
        if args:   # brukertjenester: trenger ikke sudo
            res.append(Result(f"Tjenester som har feilet ({scope})", "warn", detail,
                              fix=lambda u=units: must(["systemctl", "--user", "reset-failed", *u]),
                              fix_label="Nullstill feilstatus for brukertjenestene"))
        else:      # systemtjenester: krever sudo
            res.append(Result(f"Tjenester som har feilet ({scope})", "warn", detail,
                              fix_label="Nullstill feilstatus for systemtjenestene (sudo)",
                              root_cmds=["systemctl reset-failed " + " ".join(map(shlex.quote, units))]))
    if not res:
        res.append(Result("Systemtjenester", "ok", "Ingen tjenester har feilet"))
    return res


def check_resources():
    res = []
    try:
        sv = os.statvfs(HOME)
        frac = 1 - sv.f_bavail / sv.f_blocks
        free_gb = sv.f_bavail * sv.f_frsize / 1e9
        lvl = "error" if frac >= 0.95 else "warn" if frac >= 0.85 else "ok"
        res.append(Result("Diskplass (hjemmemappe)", lvl, f"{free_gb:.0f} GB ledig ({frac * 100:.0f} % brukt)"))
    except OSError:
        pass
    try:
        mem = {}
        for line in open("/proc/meminfo"):
            k, v = line.split(":", 1)
            mem[k] = int(v.split()[0])
        avail = mem["MemAvailable"] / mem["MemTotal"]
        res.append(Result("Minne (RAM)", "warn" if avail < 0.1 else "ok",
                          f"{avail * 100:.0f} % ledig"))
    except (OSError, KeyError, ValueError):
        pass
    temps = []
    for h in glob.glob("/sys/class/hwmon/hwmon*"):
        try:
            if open(f"{h}/name").read().strip() in ("k10temp", "coretemp"):
                temps.append(int(open(f"{h}/temp1_input").read()) / 1000)
        except (OSError, ValueError):
            pass
    code, out = run(["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"], timeout=10)
    gpu = float(out.strip().splitlines()[0]) if code == 0 and out.strip() else None
    cpu = max(temps) if temps else None
    if cpu is not None or gpu is not None:
        hot = (cpu or 0) >= 90 or (gpu or 0) >= 85
        txt = " · ".join(t for t in (f"CPU {cpu:.0f} °C" if cpu is not None else "",
                                     f"GPU {gpu:.0f} °C" if gpu is not None else "") if t)
        res.append(Result("Temperaturer", "warn" if hot else "ok", txt))
    return res


def check_ostree():
    if not shutil.which("rpm-ostree"):
        return []
    code, out = run(["rpm-ostree", "status", "--json"], timeout=30)
    try:
        staged = any(d.get("staged") for d in json.loads(out).get("deployments", []))
    except ValueError:
        return []
    if staged:
        return [Result("Bazzite-oppdatering venter", "info",
                       "En oppdatering er lastet ned. Start PC-en på nytt for å ta den i bruk.")]
    return [Result("Bazzite-oppdatering", "ok", "Ingen oppdatering venter på omstart")]


def check_pipx():
    vdir = HOME / ".local/share/pipx/venvs"
    pipx = shutil.which("pipx")
    if not vdir.is_dir():
        return []
    cur = f"{sys.version_info.major}.{sys.version_info.minor}"
    res = []
    for cfg in sorted(vdir.glob("*/pyvenv.cfg")):
        name = cfg.parent.name
        m = re.search(r"^version\s*=\s*(\d+\.\d+)", cfg.read_text(), re.M)
        if not m or m.group(1) == cur:
            continue
        if name == "trcc-linux" and os.path.exists(SYSTEM_TRCC):
            res.append(Result(
                "TRCC-kommandoen er ødelagt", "error",
                f"En gammel trcc-linux (laget for Python {m.group(1)}) skygger for den som følger med "
                f"Bazzite, og gjør at TRCC ikke starter.",
                (lambda: must([pipx, "uninstall", "trcc-linux"])) if pipx else None,
                "Fjern den gamle (Bazzites TRCC brukes i stedet)"))
        else:
            res.append(Result(
                f"Programmet «{name}» er ødelagt", "error",
                f"Laget for Python {m.group(1)}, men systemet har Python {cur}.",
                (lambda n=name: must([pipx, "reinstall", n], timeout=600)) if pipx else None,
                "Installer på nytt for riktig Python"))
    if not res:
        res.append(Result("Python-programmer (pipx)", "ok", "Alle virker med Python " + cur))
    return res


def _trcc_daemon():
    return "is running" in run([TRCC, "daemon-status"], timeout=15)[1]


def _fix_trcc_daemon():
    subprocess.Popen([TRCC, "daemon"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    for _ in range(30):
        time.sleep(0.5)
        if _trcc_daemon():
            break
    must([TRCC, "display", "resume"], timeout=90)


def _fix_trcc_autostart():
    TRCC_AUTOSTART.parent.mkdir(parents=True, exist_ok=True)
    TRCC_AUTOSTART.write_text(
        "[Desktop Entry]\nType=Application\nName=CPU-skjerm (TRCC-tjeneste)\n"
        f"Exec=sh -c '{TRCC} daemon & sleep 4; {TRCC} display resume'\n"
        "Icon=trcc\nTerminal=false\nX-GNOME-Autostart-enabled=true\n")
    if OLD_TRCC_AUTOSTART.exists():
        txt = OLD_TRCC_AUTOSTART.read_text()
        if "Hidden=true" not in txt:
            OLD_TRCC_AUTOSTART.with_suffix(".desktop.bak").write_text(txt)
            OLD_TRCC_AUTOSTART.write_text(txt.rstrip("\n") + "\nHidden=true\n")


def check_trcc():
    if not os.path.exists(TRCC):
        return []
    code, out = run([TRCC, "device", "list"], timeout=30)
    if not re.search(r"[0-9a-f]{4}:[0-9a-f]{4}", out):
        return []                                     # ingen Thermalright-skjerm
    res = []
    if _trcc_daemon():
        res.append(Result("CPU-skjerm (TRCC)", "ok", "Tjenesten kjører og oppdaterer skjermen"))
    else:
        res.append(Result("CPU-skjerm (TRCC)", "error",
                          "Tjenesten kjører ikke – kjølerskjermen viser bare logoen.",
                          _fix_trcc_daemon, "Start TRCC-tjenesten"))
    old_ok = True
    if OLD_TRCC_AUTOSTART.exists():
        txt = OLD_TRCC_AUTOSTART.read_text()
        m = re.search(r"^Exec=(\S+)", txt, re.M)
        if m and "Hidden=true" not in txt:
            exe = m.group(1)
            old_ok = os.path.exists(exe) and run([exe, "--version"], timeout=20)[0] == 0
    if not TRCC_AUTOSTART.exists() or not old_ok:
        res.append(Result("CPU-skjerm ved oppstart", "warn" if old_ok else "error",
                          "TRCC starter ikke ved innlogging" + ("" if old_ok else
                                                                " (den gamle oppstarten er ødelagt)") +
                          ", så skjermen viser bare logoen etter omstart.",
                          _fix_trcc_autostart, "Start TRCC automatisk ved innlogging"))
    return res


def _openrgb_up():
    try:
        with socket.create_connection(("127.0.0.1", 6742), timeout=1):
            return True
    except OSError:
        return False


def _start_openrgb():
    subprocess.Popen(["flatpak", "run", "org.openrgb.OpenRGB", "--server", "--noautoconnect"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    for _ in range(60):
        time.sleep(1)
        if _openrgb_up():
            return
    raise RuntimeError("OpenRGB startet ikke")


def check_openrgb(pids):
    if not flatpak_installed("org.openrgb.OpenRGB"):
        return []
    res = []
    up = _openrgb_up()
    res.append(Result("OpenRGB (RGB-tjenesten)", "ok" if up else "warn",
                      "Kjører" if up else "Kjører ikke – RGB-fanen og lys ved oppstart virker ikke",
                      None if up else _start_openrgb, None if up else "Start OpenRGB"))
    try:
        det = json.loads(OPENRGB_CFG.read_text())["Detectors"]["detectors"]
    except (OSError, ValueError, KeyError):
        return res
    wanted = [d for pid in pids for d in LOGI_DETECTORS.get(pid, [])]
    if wanted:
        wanted.append(GENERIC_LOGI_DETECTOR)
    on = [d for d in wanted if det.get(d, True)]
    if on:
        def fix(on=on):
            run(["flatpak", "kill", "org.openrgb.OpenRGB"], timeout=20)
            time.sleep(2)
            data = json.loads(OPENRGB_CFG.read_text())
            bak = OPENRGB_CFG.with_suffix(".json.bak-systemsjekk")
            if not bak.exists():
                bak.write_text(OPENRGB_CFG.read_text())
            for d in on:
                data["Detectors"]["detectors"][d] = False
            OPENRGB_CFG.write_text(json.dumps(data, indent=4))
            _start_openrgb()
        res.append(Result("OpenRGB styrer Logitech-enhetene", "error",
                          "Da tar OpenRGB over lysene på mus/tastatur fra profilene deres. "
                          "De skal styres via ratbagd.", fix, "Slå av Logitech i OpenRGB"))
    return res


def check_solaar(pids):
    if not SOLAAR_CFG.exists() or not pids:
        return []
    res = []
    text = SOLAAR_CFG.read_text()
    for block in re.split(r"^- (?=_NAME:)", text, flags=re.M)[1:]:
        name = re.search(r"_NAME:\s*(.+)", block).group(1).strip()
        mid = re.search(r"_modelId:\s*(\w+)", block)
        pid = mid.group(1)[:4].lower() if mid else ""
        if pid not in pids:
            continue
        for key in ("led_control", "rgb_control"):
            if re.search(rf"^\s+{key}:\s*true", block, re.M):
                res.append(Result(f"Solaar tar over lysene på {name}", "error",
                                  "Da vises ikke fargene fra RGB-fanen på denne enheten.",
                                  (lambda n=name, k=key: must(SOLAAR + ["config", n, k, "false"], timeout=90)),
                                  "Slå av Solaars lysstyring"))
    if not res:
        res.append(Result("Solaar og Logitech-lys", "ok", "Solaar overstyrer ikke lysene"))
    return res


def check_fans():
    helper = os.path.exists("/usr/local/bin/systemmonitor-fan")
    chip = any(re.fullmatch(r"nct6\d{3}[a-z]?", open(f"{h}/name").read().strip())
               for h in glob.glob("/sys/class/hwmon/hwmon*") if os.path.exists(f"{h}/name"))
    if helper and not chip:
        return [Result("Viftedriveren er ikke lastet", "error",
                       "Viftestyring er satt opp, men hovedkortets viftebrikke (nct6775) er ikke lastet.",
                       fix_label="Last viftedriveren (nct6775)", root_cmds=["modprobe nct6775"])]
    if helper:
        return [Result("Viftestyring", "ok", "Driver og hjelpeprogram er på plass")]
    return [Result("Viftestyring", "info", "Ikke aktivert – trykk «Aktiver viftestyring» i Oversikt")]


def check_overlay():
    env = HOME / ".config/environment.d/90-systemmonitor-mangohud.conf"
    if env.exists() and os.environ.get("MANGOHUD") != "1":
        return [Result("Spill-overlay", "info", "Logg ut og inn igjen én gang for at overlayet skal virke i spill")]
    if env.exists():
        return [Result("Spill-overlay", "ok", "MangoHud er aktivt")]
    return []


def _drivers():
    import drivercheck
    return drivercheck.run_all()


def _pkg():
    import pkgcheck
    return pkgcheck.run_all()


def run_all(progress=None):
    pids = ratbag_pids()
    checks = [("Tjenester", check_failed_units), ("Ressurser", check_resources),
              ("Oppdateringer", check_ostree), ("Python-programmer", check_pipx),
              ("CPU-skjerm", check_trcc), ("OpenRGB", lambda: check_openrgb(pids)),
              ("Solaar", lambda: check_solaar(pids)), ("Vifter", check_fans),
              ("Spill-overlay", check_overlay), ("Pakkebehandler og oppdateringer", _pkg),
              ("Drivere og fastvare", _drivers)]
    out = []
    for i, (name, fn) in enumerate(checks):
        if progress:
            progress(f"Sjekker {name.lower()} … ({i + 1}/{len(checks)})")
        try:
            out += fn()
        except Exception as e:  # noqa: BLE001
            out.append(Result(f"{name}: kunne ikke sjekkes", "warn", str(e)))
    return out


PREFS = HOME / ".config/systemmonitor/syscheck.json"


def _load_prefs():
    try:
        return json.loads(PREFS.read_text())
    except (OSError, ValueError):
        return {}


def _save_prefs(upd):
    try:
        PREFS.parent.mkdir(parents=True, exist_ok=True)
        PREFS.write_text(json.dumps({**_load_prefs(), **upd}))
    except OSError:
        pass


def run_root(items):
    """Kjør alle root-rettinger i ett skript med én pkexec-passordforespørsel.
    Returnerer en liste med feilmeldinger (tom hvis alt gikk bra)."""
    import shlex
    import tempfile
    lines = ["#!/bin/bash", "export LC_ALL=C"]
    for i, r in enumerate(items):
        cmd = " && ".join(f"( {c} )" for c in r.root_cmds)
        lines.append(f"echo '@@START {i}'")
        lines.append(f"if bash -c {shlex.quote(cmd)} 2>&1; then echo '@@OK {i}'; else echo '@@FAIL {i}'; fi")
    fd, path = tempfile.mkstemp(prefix="systemsjekk-", suffix=".sh",
                                dir=os.environ.get("XDG_RUNTIME_DIR") or None)
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(path, 0o700)
    try:
        r = subprocess.run(["pkexec", "/bin/bash", path], capture_output=True, text=True, timeout=7200)
        out = (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError) as e:
        return [f"Kunne ikke kjøre som root: {e}"]
    finally:
        os.unlink(path)
    if r.returncode in (126, 127) and "@@START" not in out:
        return ["Avbrutt – passordet ble ikke godtatt eller vinduet ble lukket"]
    failed = []
    blocks = re.split(r"^@@START (\d+)$", out, flags=re.M)
    texts = {int(blocks[k]): blocks[k + 1] for k in range(1, len(blocks) - 1, 2)}
    for i, r_ in enumerate(items):
        t = texts.get(i, "")
        if f"@@OK {i}" not in t:
            last = [ln for ln in t.splitlines() if ln.strip() and not ln.startswith("@@")][-1:]
            failed.append(f"{r_.fix_label or r_.title}: {last[0] if last else 'feilet'}")
    return failed


# --------------------------------------------------------------------------
# Dialog
# --------------------------------------------------------------------------
ICONS = {"ok": ("emblem-ok-symbolic", "success"), "info": ("dialog-information-symbolic", "accent"),
         "warn": ("dialog-warning-symbolic", "warning"), "error": ("dialog-error-symbolic", "error")}
ORDER = {"error": 0, "warn": 1, "info": 2, "ok": 3}


class SysCheckDialog(Adw.Dialog):
    def __init__(self):
        super().__init__(title="Systemsjekk", content_width=680, content_height=640)
        tv = Adw.ToolbarView()
        tv.add_top_bar(Adw.HeaderBar())
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(14)
        self.summary = Gtk.Label(xalign=0, wrap=True)
        self.summary.add_css_class("title-4")
        box.append(self.summary)
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.list.add_css_class("boxed-list")
        sc = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        sc.set_child(self.list)
        box.append(sc)
        bar = Gtk.Box(spacing=8)
        self.spinner = Gtk.Spinner()
        bar.append(self.spinner)
        self.status = Gtk.Label(xalign=0, hexpand=True, wrap=True)
        self.status.add_css_class("dim-label")
        bar.append(self.status)
        auto_box = Gtk.Box(spacing=6)
        auto_box.append(Gtk.Label(label="Rett feil automatisk"))
        self.auto_sw = Gtk.Switch(active=_load_prefs().get("auto_fix", False), valign=Gtk.Align.CENTER)
        self.auto_sw.set_tooltip_text("Ber om passord én gang og retter alle feil og advarsler selv. "
                                      "Oppdateringer startes fortsatt med «Rett alle».")
        self.auto_sw.connect("notify::active", lambda sw, _p: _save_prefs({"auto_fix": sw.get_active()}))
        auto_box.append(self.auto_sw)
        bar.append(auto_box)
        self.again = Gtk.Button(label="Sjekk på nytt")
        self.again.connect("clicked", lambda *_: self.start())
        bar.append(self.again)
        self.fix_all = Gtk.Button(label="Rett alle")
        self.fix_all.add_css_class("suggested-action")
        self.fix_all.connect("clicked", lambda *_: self._confirm([r for r in self.results if r.fixable]))
        bar.append(self.fix_all)
        box.append(bar)
        tv.set_content(box)
        self.set_child(tv)
        self.results = []
        self.start()

    def _busy(self, on, text=""):
        self.spinner.set_spinning(on)
        self.status.set_label(text)
        self.again.set_sensitive(not on)
        self.fix_all.set_sensitive(not on and any(r.fixable for r in self.results))
        return False

    def start(self, auto_allowed=True):
        self._auto_allowed = auto_allowed
        self._busy(True, "Starter sjekk …")
        self.summary.set_label("Sjekker systemet …")

        def work():
            res = run_all(lambda t: GLib.idle_add(self._busy, True, t))
            GLib.idle_add(self._show, res)
        threading.Thread(target=work, daemon=True).start()

    def _show(self, res):
        self.results = sorted(res, key=lambda r: ORDER[r.level])
        while (c := self.list.get_first_child()):
            self.list.remove(c)
        for r in self.results:
            row = Gtk.Box(spacing=12)
            for side in ("top", "bottom", "start", "end"):
                getattr(row, f"set_margin_{side}")(10)
            icon, css = ICONS[r.level]
            img = Gtk.Image.new_from_icon_name(icon)
            img.add_css_class(css)
            img.set_valign(Gtk.Align.START)
            row.append(img)
            txt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            t = Gtk.Label(label=r.title, xalign=0, wrap=True)
            t.add_css_class("heading")
            txt.append(t)
            if r.detail:
                d = Gtk.Label(label=r.detail, xalign=0, wrap=True, selectable=True)
                d.add_css_class("caption")
                d.add_css_class("dim-label")
                txt.append(d)
            row.append(txt)
            if r.fixable:
                b = Gtk.Button(label="Rett" + (" 🔒" if r.password else ""), valign=Gtk.Align.CENTER)
                b.set_tooltip_text(r.fix_label or "Rett feilen")
                b.connect("clicked", lambda _b, r=r: self._confirm([r]))
                row.append(b)
            self.list.append(row)
        errs = sum(r.level == "error" for r in res)
        warns = sum(r.level == "warn" for r in res)
        fixable = sum(1 for r in res if r.fixable)
        if errs or warns:
            self.summary.set_label(f"Fant {errs} feil og {warns} advarsler"
                                   + (f" – {fixable} kan rettes automatisk" if fixable else ""))
        else:
            self.summary.set_label("✓ Alt ser bra ut")
        self.fix_all.set_label(f"Rett alle ({fixable})" if fixable else "Rett alle")
        self._busy(False, f"Sjekket {time.strftime('%H:%M:%S')}")
        auto = [r for r in self.results if r.fixable and r.level in ("error", "warn")]
        if not auto and self.auto_sw.get_active() and (errs or warns):
            self.summary.set_label(self.summary.get_label() +
                                   " – ingen av dem kan rettes automatisk, så sudo trengs ikke")
        elif not auto and self.auto_sw.get_active():
            self.summary.set_label(self.summary.get_label() + " – ingenting å rette, sudo trengs ikke")
        if auto and self.auto_sw.get_active() and getattr(self, "_auto_allowed", True):
            self._auto_allowed = False            # bare én automatisk runde per sjekk
            self.summary.set_label(self.summary.get_label() + " – retter automatisk …")
            self._run_fixes(auto, auto=True)
        return False

    def _confirm(self, items):
        if not items:
            return
        d = Adw.AlertDialog(
            heading="Rette disse feilene?",
            body="\n".join(f"• {r.fix_label or r.title}" + (" (krever passord)" if r.password else "")
                           for r in items))
        d.add_response("cancel", "Avbryt")
        d.add_response("fix", "Rett")
        d.set_response_appearance("fix", Adw.ResponseAppearance.SUGGESTED)
        d.set_default_response("fix")
        d.set_close_response("cancel")
        d.connect("response", lambda _d, resp: resp == "fix" and self._run_fixes(items))
        d.present(self)

    def _run_fixes(self, items, auto=False):
        self._busy(True, "Retter …")

        def work():
            failed = []
            user = [r for r in items if r.fix]
            root = [r for r in items if r.root_cmds]
            if root:
                GLib.idle_add(self._busy, True, "Retter med root – skriv inn passordet ditt …")
                failed += run_root(root)
            for i, r in enumerate(user, 1):
                GLib.idle_add(self._busy, True, f"Retter: {r.fix_label or r.title} ({i}/{len(user)})")
                try:
                    r.fix()
                except Exception as e:  # noqa: BLE001
                    failed.append(f"{r.fix_label or r.title}: {e}")
            res = run_all(lambda t: GLib.idle_add(self._busy, True, t))
            self._auto_allowed = False              # ikke start en ny automatisk runde
            GLib.idle_add(self._show, res)
            if failed:
                GLib.idle_add(self.status.set_label, "Noe kunne ikke rettes: " + " · ".join(failed))
        threading.Thread(target=work, daemon=True).start()
