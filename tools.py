"""Verktøy-fanen i Kontrollsenter.

* Systeminfo – med «Kopier til forum» (perfekt når du ber om hjelp på Reddit/forum)
* Rydd opp – papirkurv, Steam shader-cache, Proton-prefikser, Flatpak-rester, logger, pakkecache
* Diskhelse – SMART via UDisks2 (uten root): slitasje, reservekapasitet, feil, temperatur
* Gjenoppretting – rpm-ostree tilbakerulling eller snapper/Timeshift-øyeblikksbilder
* Sikkerhetskopi av alle Kontrollsenter-innstillinger (eksport/import)
* Kontrollsenter – versjon, oppdatering fra Git, lag installasjonspakke
* Feillogg – vis, kopier, åpne mappe
"""
import glob
import json
import os
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

APP_DIR = os.path.dirname(os.path.abspath(__file__))
HOME = Path.home()
CFG = HOME / ".config/systemmonitor"
STEAM = next((p for p in (HOME / ".local/share/Steam", HOME / ".steam/steam",
                          HOME / ".var/app/com.valvesoftware.Steam/data/Steam") if p.is_dir()), None)
OSTREE = os.path.exists("/run/ostree-booted")


def run(cmd, timeout=60):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError) as e:
        return 127, str(e)


def read(p, d=""):
    try:
        return Path(p).read_text().strip()
    except OSError:
        return d


def human(n):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return f"{n:.0f} {u}" if u in ("B", "KB") else f"{n:.1f} {u}"
        n /= 1024


def du(paths):
    tot = 0
    for p in paths:
        p = str(p)
        if os.path.isfile(p):
            tot += os.path.getsize(p)
            continue
        for root, _d, files in os.walk(p, onerror=lambda e: None):
            for f in files:
                try:
                    tot += os.lstat(os.path.join(root, f)).st_size
                except OSError:
                    pass
    return tot


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


def dim(text):
    lab = Gtk.Label(label=text, xalign=0, wrap=True, selectable=True)
    lab.add_css_class("caption")
    lab.add_css_class("dim-label")
    return lab


def run_root(cmds):
    """Kjør root-kommandoer med én pkexec-forespørsel. Returnerer (ok, melding)."""
    script = "set -e\n" + "\n".join(cmds) + "\n"
    fd, path = tempfile.mkstemp(suffix=".sh", dir=os.environ.get("XDG_RUNTIME_DIR") or None)
    with os.fdopen(fd, "w") as f:
        f.write(script)
    try:
        code, out = run(["pkexec", "/bin/bash", path], timeout=3600)
    finally:
        os.unlink(path)
    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    return code == 0, (lines[-1] if lines else "")


# --------------------------------------------------------------------------
# 1. Systeminfo
# --------------------------------------------------------------------------
def system_info():
    osr = {}
    for ln in read("/etc/os-release").splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1)
            osr[k] = v.strip('"')
    cpu = next((ln.split(":", 1)[1].strip() for ln in read("/proc/cpuinfo").splitlines()
                if ln.startswith("model name")), platform.processor())
    mem = 0
    for ln in read("/proc/meminfo").splitlines():
        if ln.startswith("MemTotal"):
            mem = int(ln.split()[1]) * 1024
    code, out = run(["lspci", "-nn"], 20)
    gpus = [re.sub(r"\s*\(rev [0-9a-f]+\)", "", ln.split(": ", 1)[1]) for ln in out.splitlines()
            if re.search(r"VGA compatible|3D controller|Display controller", ln)]
    drivers = []
    nv = run(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"], 15)[1].strip()
    if nv and "not" not in nv.lower():
        drivers.append(f"NVIDIA {nv.splitlines()[0]}")
    code, out = run(["glxinfo", "-B"], 15)
    m = re.search(r"Mesa (\S+)", out)
    if m:
        drivers.append(f"Mesa {m.group(1)}")
    dmi = lambda n: read(f"/sys/class/dmi/id/{n}")  # noqa: E731
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "?") + " (" + os.environ.get("XDG_SESSION_TYPE", "?") + ")"
    kde = run(["plasmashell", "--version"], 10)[1].strip() if "KDE" in desktop else ""
    disks = []
    code, out = run(["lsblk", "-dno", "NAME,SIZE,MODEL,TYPE"], 10)
    for ln in out.splitlines():
        p = ln.split()
        if p and p[-1] == "disk" and not p[0].startswith("zram"):
            disks.append(" ".join(p[1:-1]))
    rows = [
        ("System", f"{osr.get('PRETTY_NAME', '?')}" + (f" (rpm-ostree)" if OSTREE else "")),
        ("Kjerne", platform.release()),
        ("Skrivebord", (desktop + (" · " + kde if kde else "")).strip()),
        ("Maskin", " ".join(x for x in (dmi("sys_vendor"), dmi("product_name")) if x and "System" not in x)
         or " ".join(x for x in (dmi("board_vendor"), dmi("board_name")) if x)),
        ("Hovedkort", f"{dmi('board_vendor')} {dmi('board_name')} · BIOS {dmi('bios_version')} ({dmi('bios_date')})"),
        ("CPU", f"{cpu} · {os.cpu_count()} tråder"),
        ("Minne", human(mem)),
        ("Grafikk", " / ".join(gpus) or "?"),
        ("Grafikkdrivere", ", ".join(drivers) or "?"),
        ("Disker", " / ".join(disks) or "?"),
    ]
    return rows


def info_text(rows):
    return "**Systeminfo** (fra Kontrollsenter)\n```\n" + "\n".join(f"{k:15} {v}" for k, v in rows) + "\n```"


# --------------------------------------------------------------------------
# 2. Rydd opp
# --------------------------------------------------------------------------
def steam_installed_appids():
    ids = set()
    if not STEAM:
        return ids
    libs = [STEAM / "steamapps"]
    vdf = read(STEAM / "steamapps/libraryfolders.vdf")
    for m in re.finditer(r'"path"\s+"([^"]+)"', vdf):
        libs.append(Path(m.group(1)) / "steamapps")
    for lib in libs:
        for f in glob.glob(str(lib / "appmanifest_*.acf")):
            m = re.search(r"appmanifest_(\d+)\.acf", f)
            if m:
                ids.add(m.group(1))
    return ids


def cleanup_items():
    """(nøkkel, navn, forklaring, stier/None, størrelse, root?, kommando/funksjon, standard på?, advarsel)"""
    items = []
    trash = [HOME / ".local/share/Trash"]
    items.append(("trash", "Papirkurven", "Filer du har slettet.", trash, du(trash), False, None, True, None))
    if STEAM:
        inst = steam_installed_appids()
        sc = STEAM / "steamapps/shadercache"
        orphan_sc = [p for p in sc.glob("*") if p.name.isdigit() and p.name not in inst] if sc.is_dir() else []
        items.append(("shader_orphan", "Steam shader-cache for avinstallerte spill",
                      "Rester etter spill som ikke er installert lenger. Trygt å slette.",
                      orphan_sc, du(orphan_sc), False, None, True, None))
        all_sc = [p for p in sc.glob("*") if p.name.isdigit() and p.name in inst] if sc.is_dir() else []
        items.append(("shader_all", "Steam shader-cache for installerte spill",
                      "Steam lager den på nytt. Første gang du spiller kan det hakke litt og ta tid å starte.",
                      all_sc, du(all_sc), False, None, False, None))
        cd = STEAM / "steamapps/compatdata"
        orphan_cd = [p for p in cd.glob("*") if p.name.isdigit() and p.name not in inst and p.name != "0"] \
            if cd.is_dir() else []
        items.append(("proton_orphan", "Proton-prefikser for avinstallerte spill",
                      "Windows-miljøene til spill som ikke er installert.", orphan_cd, du(orphan_cd), False, None,
                      False, "Kan inneholde lagrede spill (savegames) som ikke ligger i Steam Cloud!"))
    thumbs = [HOME / ".cache/thumbnails"]
    items.append(("thumbs", "Miniatyrbilder", "Forhåndsvisninger av bilder og videoer. Lages på nytt ved behov.",
                  thumbs, du(thumbs), False, None, True, None))
    items.append(("flatpak", "Flatpak-rester", "Kjøretidsmiljøer som ingen programmer bruker lenger.",
                  None, None, False, ["flatpak", "uninstall", "--unused", "-y", "--noninteractive"], True, None))
    code, out = run(["journalctl", "--disk-usage"], 20)
    m = re.search(r"take up ([\d.]+)([KMGT])", out)
    jsize = float(m.group(1)) * {"K": 1e3, "M": 1e6, "G": 1e9, "T": 1e12}[m.group(2)] if m else None
    items.append(("journal", "Systemlogger eldre enn 2 uker", "Gamle loggfiler fra systemet.", None, jsize, True,
                  ["journalctl --vacuum-time=2weeks"], True, None))
    if not OSTREE:
        if shutil.which("pacman"):
            cmd = ["paccache -rk1 && paccache -ruk0"] if shutil.which("paccache") else ["pacman -Sc --noconfirm"]
            items.append(("pkg", "Gamle pakker i pakkecachen", "Beholder siste versjon av hver pakke.",
                          [Path("/var/cache/pacman/pkg")], du([Path("/var/cache/pacman/pkg")]), True, cmd, True, None))
        elif shutil.which("dnf"):
            items.append(("pkg", "Pakkecache (dnf)", "Nedlastede pakker som allerede er installert.", None, None,
                          True, ["dnf clean packages"], True, None))
        elif shutil.which("apt-get"):
            items.append(("pkg", "Pakkecache (apt)", "Nedlastede pakker som allerede er installert.",
                          [Path("/var/cache/apt/archives")], du([Path("/var/cache/apt/archives")]), True,
                          ["apt-get clean", "apt-get -y autoremove"], True, None))
        elif shutil.which("zypper"):
            items.append(("pkg", "Pakkecache (zypper)", "Nedlastede pakker.", None, None, True,
                          ["zypper -n clean --all"], True, None))
    else:
        items.append(("ostree", "Gammel nedlastingscache (rpm-ostree)", "Metadata og nedlastinger. "
                      "Den forrige systemversjonen beholdes (for tilbakerulling).", None, None, True,
                      ["rpm-ostree cleanup -m"], True, None))
    return items


def do_cleanup(items):
    """Utfører valgte opprydninger. Returnerer (frigjort, feil)."""
    freed, errors, root_cmds = 0, [], []
    for key, name, _d, paths, size, root, cmd, _on, _w in items:
        try:
            if root:
                root_cmds += cmd
                freed += size or 0
            elif key == "trash":
                code, out = run(["gio", "trash", "--empty"], 300)
                if code != 0:
                    raise RuntimeError(out.strip())
                freed += size or 0
            elif cmd:
                code, out = run(cmd, 1800)
                if code != 0:
                    raise RuntimeError(out.strip().splitlines()[-1] if out.strip() else "feilet")
            else:
                for p in paths or []:
                    if os.path.isdir(p) and not os.path.islink(p):
                        shutil.rmtree(p, ignore_errors=True)
                    elif os.path.exists(p):
                        os.unlink(p)
                freed += size or 0
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: {e}")
    if root_cmds:
        ok, msg = run_root(root_cmds)
        if not ok:
            errors.append(f"Root-rydding: {msg or 'avbrutt'}")
    return freed, errors


# --------------------------------------------------------------------------
# 3. Diskhelse (SMART via UDisks2)
# --------------------------------------------------------------------------
def disk_health():
    res = []
    try:
        om = Gio.DBusProxy.new_for_bus_sync(Gio.BusType.SYSTEM, 0, None, "org.freedesktop.UDisks2",
                                            "/org/freedesktop/UDisks2", "org.freedesktop.DBus.ObjectManager", None)
        objs = om.call_sync("GetManagedObjects", None, 0, 10000, None).unpack()[0]
    except GLib.Error:
        return res
    for path, ifaces in objs.items():
        drv = ifaces.get("org.freedesktop.UDisks2.Drive")
        if not drv or drv.get("Removable") and not drv.get("Size"):
            continue
        name = f"{drv.get('Vendor', '')} {drv.get('Model', '')}".strip() or path.rsplit("/", 1)[-1]
        size = drv.get("Size", 0)
        info = {"name": name, "size": size, "kind": "?", "ok": None, "rows": []}
        nvme = ifaces.get("org.freedesktop.UDisks2.NVMe.Controller")
        ata = ifaces.get("org.freedesktop.UDisks2.Drive.Ata")
        try:
            if nvme:
                info["kind"] = "NVMe"
                p = Gio.DBusProxy.new_for_bus_sync(Gio.BusType.SYSTEM, 0, None, "org.freedesktop.UDisks2", path,
                                                   "org.freedesktop.UDisks2.NVMe.Controller", None)
                a = p.call_sync("SmartGetAttributes", GLib.Variant("(a{sv})", ({},)), 0, 10000, None).unpack()[0]
                warn = nvme.get("SmartCriticalWarning") or []
                used, spare = a.get("percent_used", 0), a.get("avail_spare", 100)
                errs = a.get("media_errors", 0)
                info["ok"] = not warn and errs == 0 and spare > a.get("spare_thresh", 10) and used < 90
                t = nvme.get("SmartTemperature", 0)
                info["rows"] = [
                    ("Helse", "God" if info["ok"] else ("Advarsel: " + ", ".join(warn) if warn else "Bør sjekkes")),
                    ("Slitasje", f"{used} % brukt av levetiden"),
                    ("Reservekapasitet", f"{spare} %"),
                    ("Mediefeil", str(errs)),
                    ("Temperatur", f"{t - 273} °C" if t else "?"),
                    ("I drift", f"{nvme.get('SmartPowerOnHours', 0)} timer"),
                    ("Skrevet totalt", human(a.get("total_data_written", 0))),
                    ("Usikre avslutninger", str(a.get("unsafe_shutdowns", 0))),
                ]
            elif ata and ata.get("SmartSupported"):
                info["kind"] = "SATA"
                failing = ata.get("SmartFailing")
                bad = ata.get("SmartNumBadSectors", 0)
                info["ok"] = not failing and bad == 0
                t = ata.get("SmartTemperature", 0)
                info["rows"] = [
                    ("Helse", "God" if info["ok"] else "Advarsel: disken kan være i ferd med å svikte"),
                    ("Dårlige sektorer", str(bad)),
                    ("Temperatur", f"{t - 273.15:.0f} °C" if t else "?"),
                    ("I drift", f"{ata.get('SmartPowerOnSeconds', 0) // 3600} timer"),
                ]
            else:
                continue
        except GLib.Error as e:
            info["rows"] = [("Helse", f"Kunne ikke lese SMART: {e.message}")]
        res.append(info)
    return res


# --------------------------------------------------------------------------
# 4. Gjenoppretting
# --------------------------------------------------------------------------
def snapshot_cmd(desc="Før oppdatering (Kontrollsenter)"):
    """Kommando som tar et øyeblikksbilde før en oppdatering, eller None."""
    if OSTREE:
        return None
    if shutil.which("snapper") and os.path.exists("/etc/snapper/configs/root"):
        return f"snapper -c root create -t pre -d '{desc}' -c number || true"
    if shutil.which("timeshift"):
        return f"timeshift --create --scripted --comments '{desc}' || true"
    return None


def restore_info():
    if OSTREE:
        code, out = run(["rpm-ostree", "status", "--json"], 30)
        try:
            deps = json.loads(out).get("deployments", [])
        except ValueError:
            deps = []
        return {"kind": "ostree", "deps": [(d.get("version", "?"), d.get("booted"), d.get("staged"),
                                            d.get("pinned")) for d in deps]}
    if shutil.which("snapper") and os.path.exists("/etc/snapper/configs/root"):
        code, out = run(["snapper", "-c", "root", "list", "--columns", "number,date,description"], 30)
        snaps = [ln for ln in out.splitlines()[2:] if ln.strip()]
        return {"kind": "snapper", "snaps": snaps[-8:], "count": len(snaps)}
    if shutil.which("timeshift"):
        return {"kind": "timeshift"}
    return {"kind": "none"}


# --------------------------------------------------------------------------
# 5. Sikkerhetskopi av innstillinger
# --------------------------------------------------------------------------
BACKUP_FILES = [".config/systemmonitor", ".config/MangoHud/MangoHud.conf",
                ".config/environment.d/90-systemmonitor-mangohud.conf"]


def backup_paths():
    out = [HOME / p for p in BACKUP_FILES if (HOME / p).exists()]
    out += [Path(p) for p in glob.glob(str(HOME / ".config/autostart/systemmonitor-*.desktop"))]
    return out


def export_settings(dest):
    with tarfile.open(dest, "w:gz") as t:
        for p in backup_paths():
            t.add(p, arcname=str(p.relative_to(HOME)))


def import_settings(src):
    allowed = tuple(BACKUP_FILES) + (".config/autostart/systemmonitor-",)
    n = 0
    with tarfile.open(src, "r:gz") as t:
        for m in t.getmembers():
            name = os.path.normpath(m.name)
            if name.startswith(("/", "..")) or not name.startswith(allowed) or not (m.isfile() or m.isdir()):
                continue
            t.extract(m, HOME, filter="data")
            n += 1
    return n


# --------------------------------------------------------------------------
# 6. Kontrollsenter: versjon, oppdatering, installasjonspakke
# --------------------------------------------------------------------------
UPDATE_CFG = CFG / "oppdatering.json"
PACKAGE_FILES = ["*.py", "systemmonitor-fan", "systemmonitor-gpu-power", "systemmonitor-msi", "*.sh",
                 "en.json", "VERSION", "vendor", "icons"]


def version():
    return read(os.path.join(APP_DIR, "VERSION"), "?")


def update_source():
    try:
        return json.loads(UPDATE_CFG.read_text()).get("url", "")
    except (OSError, ValueError):
        return ""


def set_update_source(url):
    CFG.mkdir(parents=True, exist_ok=True)
    UPDATE_CFG.write_text(json.dumps({"url": url}))


def check_update():
    """Returnerer (status-tekst, kan_oppdatere)."""
    url = update_source()
    is_git = os.path.isdir(os.path.join(APP_DIR, ".git")) or os.path.isfile(os.path.join(APP_DIR, ".git"))
    if is_git:
        code, remotes = run(["git", "-C", APP_DIR, "remote"], 10)
        if not remotes.strip() and url:
            run(["git", "-C", APP_DIR, "remote", "add", "origin", url], 10)
            remotes = "origin"
        if not remotes.strip():
            return "Ingen oppdateringskilde. Legg inn adressen til Git-repoet ditt (f.eks. på GitHub).", False
        code, out = run(["git", "-C", APP_DIR, "fetch", "--quiet", "origin"], 120)
        if code != 0:
            return f"Kunne ikke hente: {out.strip().splitlines()[-1] if out.strip() else 'ukjent feil'}", False
        code, n = run(["git", "-C", APP_DIR, "rev-list", "--count", "HEAD..@{u}"], 10)
        if code != 0:
            return "Ingen oppdateringsgren satt opp (git branch -u origin/main)", False
        n = int(n.strip() or 0)
        return (f"{n} nye endringer er tilgjengelige" if n else "Du har nyeste versjon"), n > 0
    if not url:
        return "Ingen oppdateringskilde. Legg inn adressen til Git-repoet ditt.", False
    tmp = tempfile.mkdtemp()
    code, out = run(["git", "clone", "--depth", "1", "--quiet", url, tmp], 300)
    if code != 0:
        shutil.rmtree(tmp, ignore_errors=True)
        return f"Kunne ikke hente: {out.strip().splitlines()[-1] if out.strip() else 'ukjent feil'}", False
    new = read(os.path.join(tmp, "VERSION"), "?")
    shutil.rmtree(tmp, ignore_errors=True)
    return (f"Versjon {new} er tilgjengelig (du har {version()})" if new != version() else "Du har nyeste versjon"), \
        new != version()


def do_update():
    url = update_source()
    if os.path.exists(os.path.join(APP_DIR, ".git")):
        code, out = run(["git", "-C", APP_DIR, "pull", "--ff-only", "--quiet"], 300)
        return code == 0, out.strip()
    tmp = tempfile.mkdtemp()
    code, out = run(["git", "clone", "--depth", "1", "--quiet", url, tmp], 300)
    if code != 0:
        return False, out.strip()
    for pat in PACKAGE_FILES:
        for src in glob.glob(os.path.join(tmp, pat)):
            dst = os.path.join(APP_DIR, os.path.basename(src))
            if os.path.isdir(src):
                shutil.rmtree(dst, ignore_errors=True)
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
    shutil.rmtree(tmp, ignore_errors=True)
    return True, ""


def make_package(dest_dir):
    """Lag installasjonsmappe + .tar.gz (som den på skrivebordet)."""
    dest = Path(dest_dir) / "Kontrollsenter"
    prog = dest / "program"
    if prog.exists():
        shutil.rmtree(prog)
    prog.mkdir(parents=True)
    for pat in PACKAGE_FILES:
        for src in glob.glob(os.path.join(APP_DIR, pat)):
            if os.path.isdir(src):
                shutil.copytree(src, prog / os.path.basename(src),
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                shutil.copy2(src, prog / os.path.basename(src))
    pkg_src = Path(APP_DIR) / "pakke"                  # installer.sh, LES MEG, udev-regler
    if pkg_src.is_dir():
        for f in pkg_src.iterdir():
            d = dest / f.name
            if f.is_dir():
                shutil.rmtree(d, ignore_errors=True)
                shutil.copytree(f, d)
            else:
                shutil.copy2(f, d)
    lst = CFG / "programmer.json"
    if lst.exists():
        shutil.copy2(lst, dest / "programmer.json")
    archive = Path(dest_dir) / "Kontrollsenter.tar.gz"
    with tarfile.open(archive, "w:gz") as t:
        t.add(dest, arcname="Kontrollsenter")
    return dest, archive


# --------------------------------------------------------------------------
# Fanen
# --------------------------------------------------------------------------
class ToolsPage(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(12)
        self.set_child(Adw.Clamp(maximum_size=1000, child=box))
        self.box = box
        self._info_card()
        self._cleanup_card()
        self._health_card()
        self._restore_card()
        self._backup_card()
        self._notify_card()
        self._app_card()
        self._log_card()

    def _bg(self, fn, done):
        threading.Thread(target=lambda: GLib.idle_add(done, fn()), daemon=True).start()

    # --- systeminfo -----------------------------------------------------------
    def _info_card(self):
        c, i = card("Systeminfo", "Det viktigste om maskinen din – kopier og lim inn når du ber om hjelp på et forum.")
        self.info_grid = Gtk.Grid(column_spacing=16, row_spacing=4)
        i.append(self.info_grid)
        bb = Gtk.Box(spacing=6)
        cp = Gtk.Button(label="Kopier til forum")
        cp.add_css_class("suggested-action")
        cp.connect("clicked", self._copy_info)
        bb.append(cp)
        i.append(bb)
        self.info_status = dim("")
        i.append(self.info_status)
        self.box.append(c)
        self.info_rows = []
        self._bg(system_info, self._show_info)

    def _show_info(self, rows):
        self.info_rows = rows
        for r, (k, v) in enumerate(rows):
            a = Gtk.Label(label=k, xalign=0)
            a.add_css_class("dim-label")
            b = Gtk.Label(label=v, xalign=0, wrap=True, selectable=True, hexpand=True)
            self.info_grid.attach(a, 0, r, 1, 1)
            self.info_grid.attach(b, 1, r, 1, 1)
        return False

    def _copy_info(self, *_):
        Gdk.Display.get_default().get_clipboard().set(info_text(self.info_rows))
        self.info_status.set_label("Kopiert ✓ – lim inn med Ctrl + V")

    # --- rydd opp -------------------------------------------------------------
    def _cleanup_card(self):
        c, i = card("Rydd opp", "Frigjør plass. Velg hva som skal slettes – ingenting slettes før du trykker «Rydd opp».")
        self.clean_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.clean_list.append(dim("Regner ut størrelser …"))
        i.append(self.clean_list)
        bb = Gtk.Box(spacing=8)
        self.clean_btn = Gtk.Button(label="Rydd opp")
        self.clean_btn.add_css_class("suggested-action")
        self.clean_btn.connect("clicked", self._confirm_clean)
        bb.append(self.clean_btn)
        ref = Gtk.Button(label="Regn ut på nytt")
        ref.connect("clicked", lambda *_: self._refresh_clean())
        bb.append(ref)
        self.clean_status = Gtk.Label(xalign=0, hexpand=True, wrap=True)
        bb.append(self.clean_status)
        i.append(bb)
        self.box.append(c)
        self._refresh_clean()

    def _refresh_clean(self):
        self.clean_btn.set_sensitive(False)
        self._bg(cleanup_items, self._show_clean)

    def _show_clean(self, items):
        self.clean_items = items
        while (ch := self.clean_list.get_first_child()):
            self.clean_list.remove(ch)
        self.clean_checks = []
        for it in items:
            key, name, desc, _p, size, root, _c, on, warn = it
            row = Gtk.Box(spacing=10)
            chk = Gtk.CheckButton(active=on and (size is None or size > 0), valign=Gtk.Align.CENTER)
            row.append(chk)
            mid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            t = Gtk.Label(label=name + (" 🔒" if root else ""), xalign=0)
            mid.append(t)
            d = dim(desc)
            mid.append(d)
            if warn:
                w = Gtk.Label(label="⚠ " + warn, xalign=0, wrap=True)
                w.add_css_class("caption")
                w.add_css_class("warning")
                mid.append(w)
            row.append(mid)
            sz = Gtk.Label(label=human(size) if size is not None else "–", xalign=1)
            sz.add_css_class("numeric")
            if size and size > 1e9:
                sz.add_css_class("heading")
            row.append(sz)
            self.clean_list.append(row)
            self.clean_checks.append((chk, it))
        total = sum((it[4] or 0) for it in items)
        self.clean_status.set_label(f"Totalt {human(total)} kan frigjøres")
        self.clean_btn.set_sensitive(True)
        return False

    def _confirm_clean(self, *_):
        chosen = [it for chk, it in self.clean_checks if chk.get_active()]
        if not chosen:
            self.clean_status.set_label("Ingenting valgt")
            return
        size = sum((it[4] or 0) for it in chosen)
        d = Adw.AlertDialog(heading="Rydde opp nå?",
                            body="\n".join(f"• {it[1]}" + (f" ({human(it[4])})" if it[4] else "") for it in chosen) +
                            f"\n\nOmtrent {human(size)} frigjøres. Det slettede kan ikke hentes tilbake.")
        d.add_response("cancel", "Avbryt")
        d.add_response("ok", "Rydd opp")
        d.set_response_appearance("ok", Adw.ResponseAppearance.DESTRUCTIVE)
        d.connect("response", lambda _d, r: r == "ok" and self._do_clean(chosen))
        d.present(self)

    def _do_clean(self, chosen):
        self.clean_btn.set_sensitive(False)
        self.clean_status.set_label("Rydder opp …")

        def done(res):
            freed, errors = res
            self.clean_status.set_label((f"Ferdig ✓ – frigjorde omtrent {human(freed)}" if not errors else
                                         "Noe feilet: " + " · ".join(errors)))
            self._refresh_clean()
            return False
        self._bg(lambda: do_cleanup(chosen), done)

    # --- diskhelse ------------------------------------------------------------
    def _health_card(self):
        c, self.health_box = card("Diskhelse", "SMART-data fra diskene dine – fanger opp en disk som er i ferd med å dø.")
        self.health_box.append(dim("Leser SMART-data …"))
        self.box.append(c)
        self._bg(disk_health, self._show_health)

    def _show_health(self, disks):
        ch = self.health_box.get_first_child().get_next_sibling().get_next_sibling()
        while ch:
            nxt = ch.get_next_sibling()
            self.health_box.remove(ch)
            ch = nxt
        if not disks:
            self.health_box.append(dim("Fant ingen disker med SMART-data (UDisks2 mangler eller diskene støtter det ikke)."))
        for dsk in disks:
            head = Gtk.Box(spacing=8)
            icon = "✅" if dsk["ok"] else "⚠️" if dsk["ok"] is False else "❔"
            t = Gtk.Label(label=f"{icon}  {dsk['name']} · {dsk['kind']} · {human(dsk['size'])}", xalign=0)
            t.add_css_class("heading")
            head.append(t)
            self.health_box.append(head)
            g = Gtk.Grid(column_spacing=16, row_spacing=2, margin_start=28)
            for r, (k, v) in enumerate(dsk["rows"]):
                a = Gtk.Label(label=k, xalign=0)
                a.add_css_class("dim-label")
                g.attach(a, 0, r, 1, 1)
                g.attach(Gtk.Label(label=v, xalign=0), 1, r, 1, 1)
            self.health_box.append(g)
        return False

    # --- gjenoppretting -------------------------------------------------------
    def _restore_card(self):
        c, self.restore_box = card("Gjenoppretting",
                                   "Gå tilbake hvis en oppdatering ødelegger noe.")
        self.box.append(c)
        self._bg(restore_info, self._show_restore)

    def _show_restore(self, info):
        i = self.restore_box
        if info["kind"] == "ostree":
            for ver, booted, staged, pinned in info["deps"]:
                tag = "i bruk nå" if booted else "lastet ned – tas i bruk ved omstart" if staged else "forrige versjon"
                i.append(Gtk.Label(label=f"• {ver} ({tag})" + (" 📌" if pinned else ""), xalign=0))
            b = Gtk.Button(label="Gå tilbake til forrige systemversjon", halign=Gtk.Align.START)
            b.add_css_class("destructive-action")
            b.connect("clicked", lambda *_: self._root_action(
                ["rpm-ostree rollback"], "Forrige systemversjon tas i bruk ved neste omstart ✓", i))
            i.append(b)
            i.append(dim("Bazzite/Silverblue tar automatisk vare på forrige systemversjon. Du kan også velge den i "
                         "oppstartsmenyen (GRUB) når PC-en starter."))
        elif info["kind"] == "snapper":
            i.append(Gtk.Label(label=f"{info['count']} øyeblikksbilder (snapper). Siste:", xalign=0))
            for s in info["snaps"]:
                i.append(dim(s))
            b = Gtk.Button(label="Ta øyeblikksbilde nå", halign=Gtk.Align.START)
            b.connect("clicked", lambda *_: self._root_action(
                ["snapper -c root create -d 'Manuelt (Kontrollsenter)' -c number"], "Øyeblikksbilde tatt ✓", i))
            i.append(b)
            i.append(dim("Før hver systemoppdatering fra Systemsjekk tas det automatisk et øyeblikksbilde. For å gå "
                         "tilbake: velg øyeblikksbildet i oppstartsmenyen, eller bruk Btrfs Assistant."))
        elif info["kind"] == "timeshift":
            b = Gtk.Button(label="Ta øyeblikksbilde nå (Timeshift)", halign=Gtk.Align.START)
            b.connect("clicked", lambda *_: self._root_action(
                ["timeshift --create --scripted --comments 'Manuelt (Kontrollsenter)'"], "Øyeblikksbilde tatt ✓", i))
            i.append(b)
            i.append(dim("Før hver systemoppdatering fra Systemsjekk tas det automatisk et øyeblikksbilde. "
                         "Gjenopprett med Timeshift-programmet."))
        else:
            i.append(dim("Ingen øyeblikksbilder er satt opp. På Arch/CachyOS anbefales «snapper» med Btrfs "
                         "(CachyOS kan sette det opp i installasjonen), ellers «timeshift»."))
        return False

    def _root_action(self, cmds, okmsg, box):
        st = dim("Venter på passord …")
        box.append(st)

        def done(res):
            ok, msg = res
            st.set_label(okmsg if ok else f"Feilet: {msg or 'avbrutt'}")
            return False
        self._bg(lambda: run_root(cmds), done)

    # --- sikkerhetskopi -------------------------------------------------------
    def _backup_card(self):
        c, i = card("Sikkerhetskopi av innstillinger",
                    "RGB-farger, vifter, strømmodus, programliste, oppstart, overlay og språk – i én fil. "
                    "Ta den med til en ny PC og importer den der.")
        bb = Gtk.Box(spacing=6)
        e = Gtk.Button(label="Eksporter innstillinger …")
        e.connect("clicked", self._export)
        bb.append(e)
        im = Gtk.Button(label="Importer innstillinger …")
        im.connect("clicked", self._import)
        bb.append(im)
        i.append(bb)
        self.backup_status = dim("")
        i.append(self.backup_status)
        self.box.append(c)

    def _export(self, *_):
        dlg = Gtk.FileDialog(title="Lagre innstillinger",
                             initial_name=f"systemmonitor-innstillinger-{time.strftime('%Y-%m-%d')}.tar.gz")

        def done(d, res):
            try:
                f = d.save_finish(res)
            except GLib.Error:
                return
            try:
                export_settings(f.get_path())
                self.backup_status.set_label(f"Lagret ✓ {f.get_path()}")
            except OSError as e:
                self.backup_status.set_label(f"Feil: {e}")
        dlg.save(self.get_root(), None, done)

    def _import(self, *_):
        dlg = Gtk.FileDialog(title="Velg sikkerhetskopi")

        def done(d, res):
            try:
                f = d.open_finish(res)
            except GLib.Error:
                return
            try:
                n = import_settings(f.get_path())
                self.backup_status.set_label(f"Importerte {n} filer ✓ – start Kontrollsenter på nytt")
            except (OSError, tarfile.TarError) as e:
                self.backup_status.set_label(f"Feil: {e}")
        dlg.open(self.get_root(), None, done)

    # --- Kontrollsenter --------------------------------------------------------
    # --- bakgrunn og varsler ------------------------------------------------------
    def _notify_card(self):
        import background
        cfg = background.load()
        c, i = card("Bakgrunn og varsler",
                    "Kontrollsenter kan fortsette i bakgrunnen når vinduet lukkes, og si fra når noe er galt.")
        rows = [("background", "Kjør i bakgrunnen når vinduet lukkes",
                 "Overlay, vifter og varsler fortsetter. Avslutt fra ikonet i statusfeltet."),
                ("tray", "Ikon i systemstatusfeltet", "Viser temperaturer, strømmodus, overlay og Avslutt."),
                ("notify", "Varsler", "Høy temperatur, nesten full disk og lavt batteri i trådløse enheter."),
                ("periodic", "Sjekk systemet og oppdateringer hver 6. time",
                 "Kjører Systemsjekk i bakgrunnen og sier fra om den finner noe.")]
        for key, title, sub in rows:
            r = Gtk.Box(spacing=12)
            tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            tb.append(Gtk.Label(label=title, xalign=0))
            tb.append(dim(sub))
            r.append(tb)
            sw = Gtk.Switch(active=cfg[key], valign=Gtk.Align.CENTER)
            sw.connect("notify::active", self._notify_set, key)
            r.append(sw)
            i.append(r)
        lim = Gtk.Box(spacing=8)
        for key, title, lo, hi in (("cpu_limit", "CPU °C", 60, 100), ("gpu_limit", "GPU °C", 60, 95),
                                   ("disk_limit", "Disk %", 70, 99), ("battery_limit", "Batteri %", 5, 50)):
            lim.append(Gtk.Label(label=title))
            sp = Gtk.SpinButton.new_with_range(lo, hi, 1)
            sp.set_value(cfg[key])
            sp.connect("value-changed", lambda w, k=key: self._notify_set_val(k, int(w.get_value())))
            lim.append(sp)
        i.append(Gtk.Label(label="Varsle ved:", xalign=0))
        i.append(lim)
        i.append(dim("Start Kontrollsenter skjult ved innlogging: Programmer → Oppstart → Kontrollsenter."))
        self.box.append(c)

    def _notify_set(self, sw, _p, key):
        self._notify_set_val(key, sw.get_active())

    def _notify_set_val(self, key, val):
        import background
        bg = getattr(self.get_root(), "bg", None)
        if bg:
            bg.set(key, val)
        else:
            cfg = background.load()
            cfg[key] = val
            background.save(cfg)

    def _app_card(self):
        c, i = card("Kontrollsenter", f"Versjon {version()} · {APP_DIR}")
        row = Gtk.Box(spacing=6)
        self.url = Gtk.Entry(placeholder_text="Git-adresse for oppdateringer (f.eks. https://github.com/navn/systemmonitor)",
                             hexpand=True, text=update_source())
        row.append(self.url)
        chk = Gtk.Button(label="Se etter oppdatering")
        chk.connect("clicked", self._check_update)
        row.append(chk)
        i.append(row)
        self.upd_btn = Gtk.Button(label="Oppdater nå", halign=Gtk.Align.START, visible=False)
        self.upd_btn.add_css_class("suggested-action")
        self.upd_btn.connect("clicked", self._update)
        i.append(self.upd_btn)
        self.upd_status = dim("")
        i.append(self.upd_status)
        pk = Gtk.Button(label="Lag installasjonspakke på skrivebordet", halign=Gtk.Align.START)
        pk.connect("clicked", self._package)
        i.append(pk)
        self.pkg_status = dim("Lager mappen «Kontrollsenter» og «Kontrollsenter.tar.gz» med alt som trengs for å "
                              "installere på en annen PC – inkludert programlisten din.")
        i.append(self.pkg_status)
        self.box.append(c)

    def _check_update(self, *_):
        set_update_source(self.url.get_text().strip())
        self.upd_status.set_label("Sjekker …")

        def done(res):
            txt, can = res
            self.upd_status.set_label(txt)
            self.upd_btn.set_visible(can)
            return False
        self._bg(check_update, done)

    def _update(self, *_):
        self.upd_status.set_label("Oppdaterer …")

        def done(res):
            ok, msg = res
            self.upd_status.set_label("Oppdatert ✓ – start Kontrollsenter på nytt" if ok else f"Feil: {msg}")
            self.upd_btn.set_visible(not ok)
            return False
        self._bg(do_update, done)

    def _package(self, *_):
        desk = run(["xdg-user-dir", "DESKTOP"], 5)[1].strip() or str(HOME / "Desktop")
        self.pkg_status.set_label("Lager pakke …")

        def done(res):
            if isinstance(res, Exception):
                self.pkg_status.set_label(f"Feil: {res}")
            else:
                self.pkg_status.set_label(f"Ferdig ✓ {res[0]} og {res[1]}")
            return False

        def work():
            try:
                return make_package(desk)
            except Exception as e:  # noqa: BLE001
                return e
        self._bg(work, done)

    # --- logg -----------------------------------------------------------------
    def _log_card(self):
        import applog
        c, i = card("Feillogg", applog.LOG_FILE)
        tv = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        tv.get_buffer().set_text(applog.tail(60) or "(tom)")
        sc = Gtk.ScrolledWindow(min_content_height=160, max_content_height=260, propagate_natural_height=True)
        sc.set_child(tv)
        i.append(sc)
        bb = Gtk.Box(spacing=6)
        cp = Gtk.Button(label="Kopier logg")
        cp.connect("clicked", lambda *_: (Gdk.Display.get_default().get_clipboard().set(applog.tail(300)),
                                          self.log_status.set_label("Kopiert ✓")))
        bb.append(cp)
        op = Gtk.Button(label="Åpne loggmappen")
        op.connect("clicked", lambda *_: Gio.AppInfo.launch_default_for_uri(
            Gio.File.new_for_path(applog.LOG_DIR).get_uri(), None))
        bb.append(op)
        rf = Gtk.Button(label="Oppdater")
        rf.connect("clicked", lambda *_: tv.get_buffer().set_text(applog.tail(60) or "(tom)"))
        bb.append(rf)
        self.log_status = Gtk.Label(xalign=0)
        bb.append(self.log_status)
        i.append(bb)
        self.box.append(c)
