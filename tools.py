"""Vedlikehold- og Innstillinger-sidene i Kontrollsenter.

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
import sys
import tarfile
import tempfile
import threading
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from tabbed import TabbedPage  # noqa: E402

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
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        kde = "Hyprland " + __import__("desktop").hypr_version()
    elif "GNOME" in desktop.upper():
        kde = run(["gnome-shell", "--version"], 10)[1].strip()
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
        info = {"name": name, "size": size, "kind": "?", "ok": None, "rows": [], "serial": drv.get("Serial") or name}
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
                info["used_pct"], info["hours"] = used, nvme.get("SmartPowerOnHours", 0)
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
PACKAGE_FILES = ["*.py", "systemmonitor-fan", "systemmonitor-gpu-power", "systemmonitor-gpu", "systemmonitor-msi", "*.sh",
                 "en.json", "VERSION", "*.ps1", "vendor", "icons", "remote_web", "wow_addon"]


def version():
    return read(os.path.join(APP_DIR, "VERSION"), "?")


DEFAULT_SOURCE = "https://github.com/vegardwaagan-dotcom/Kontrollsenter.git"


def update_source():
    try:
        return json.loads(UPDATE_CFG.read_text()).get("url", "") or DEFAULT_SOURCE
    except (OSError, ValueError):
        return DEFAULT_SOURCE


def _vkey(v):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return (0,)


def update_from_github():
    """«Oppdater fra GitHub»: sjekk GitHub (ikke NAS-en) og oppdater hvis det finnes noe nyere."""
    _SOURCE[0] = "git"
    txt, new = _check_git()
    if not new:
        return txt, False
    ok, msg = do_update()
    return ("Oppdatert fra GitHub ✓ – start Kontrollsenter på nytt" if ok else f"Feil: {msg}"), ok


def set_update_source(url):
    CFG.mkdir(parents=True, exist_ok=True)
    try:
        cfg = json.loads(UPDATE_CFG.read_text())
    except (OSError, ValueError):
        cfg = {}
    cfg["url"] = url
    UPDATE_CFG.write_text(json.dumps(cfg))


_SOURCE = ["git"]          # hvor siste «Se etter oppdatering» fant noe: «lan» eller «git»


def check_update():
    """Returnerer (status-tekst, kan_oppdatere). Hjemmenettet (NAS) sjekkes først.
    kan_oppdatere = "restart" når en nyere versjon allerede er installert men ikke startet."""
    import applog
    import lanupdate
    if applog.needs_restart():
        return lanupdate.check()[0], "restart"
    txt, new = lanupdate.check()
    if new:
        _SOURCE[0] = "lan"
        return txt, True
    _SOURCE[0] = "git"
    lan_txt = txt if txt != "Ikke på hjemmenettet" else ""
    res = _check_git()
    if lan_txt and not res[1]:
        return f"{lan_txt}\n{res[0]}" if not res[0].startswith("Du har nyeste") else lan_txt, False
    return res


def _check_git():
    url = update_source()
    is_git = os.path.isdir(os.path.join(APP_DIR, ".git")) or os.path.isfile(os.path.join(APP_DIR, ".git"))
    import lanupdate
    repo = lanupdate.github_repo(url)
    if repo and not is_git:                                # vanlig installasjon (også Windows): uten Git
        try:
            new = lanupdate.github_latest(repo)[0]
        except Exception as e:  # noqa: BLE001
            return f"Kunne ikke sjekke GitHub: {e}", False
        newer = _vkey(new) > _vkey(version())
        return (f"Versjon {new} er tilgjengelig på GitHub (du har {version()})" if newer
                else "Du har nyeste versjon"), newer
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
    if _SOURCE[0] == "lan":
        import lanupdate
        return lanupdate.apply_update(PACKAGE_FILES)
    url = update_source()
    import lanupdate
    repo = lanupdate.github_repo(url)
    if repo and not os.path.exists(os.path.join(APP_DIR, ".git")):
        return lanupdate.apply_update(PACKAGE_FILES, fetch=lanupdate.github_fetch(repo, PACKAGE_FILES),
                                      source="GitHub")
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
    if (pkg_src / "udev").is_dir():                     # udev-reglene følger programmet (veiviseren legger dem inn)
        shutil.copytree(pkg_src / "udev", prog / "udev", dirs_exist_ok=True)
    win_src = Path(APP_DIR) / "pakke-windows"         # installasjon for Windows 11
    if win_src.is_dir():
        wdst = dest / "Windows"
        shutil.rmtree(wdst, ignore_errors=True)
        shutil.copytree(win_src, wdst)
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
class _Cards:
    """Alle kortene. Vedlikehold og Innstillinger bygger hver sine faner av dem."""
    def _try(self, fn, *a):
        try:
            fn(*a)
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("kort i %s", type(self).__name__)


    # --- feilsøkingsrapport ---------------------------------------------------------
    def _diag_card(self):
        c, i = card("Feilsøkingsrapport", "Samler det som trengs for å finne ut hvorfor RGB, vifter eller Logitech ikke virker. Lagres på NAS-en én gang om dagen. Ingen personlige filer.")
        row = Gtk.Box(spacing=8)
        send = Gtk.Button(label="Send til NAS-en nå")
        send.add_css_class("suggested-action")
        copy = Gtk.Button(label="Kopier rapporten")
        row.append(send)
        row.append(copy)
        i.append(row)
        st = dim("")
        i.append(st)

        def run(to_nas):
            send.set_sensitive(False)
            copy.set_sensitive(False)
            st.set_label("Lager rapport … (ca. 20 sekunder)")

            def work():
                import diagnose
                txt = diagnose.report()
                ok = diagnose.upload(txt) if to_nas else None
                GLib.idle_add(done, txt, to_nas, ok)
            threading.Thread(target=work, daemon=True).start()

        def done(txt, to_nas, ok):
            import ui
            send.set_sensitive(True)
            copy.set_sensitive(True)
            if to_nas:
                if ok:
                    ui.status(st, "Rapporten er lagt på NAS-en ✓ (Kontrollsenter\\Diagnose)")
                else:
                    st.set_label("Kunne ikke legge rapporten på NAS-en – er du på hjemmenettet? Bruk «Kopier».")
            else:
                Gdk.Display.get_default().get_clipboard().set(txt)
                ui.status(st, "Kopiert ✓ – lim inn med Ctrl + V")
            return False
        send.connect("clicked", lambda *_: run(True))
        copy.connect("clicked", lambda *_: run(False))
        self.box.append(c)

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
        import ui
        ui.status(self.info_status, "Kopiert ✓ – lim inn med Ctrl + V")

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
        def work():
            import progress as P
            freed, errors = 0, []
            with P.task("Rydder opp", "", "Opprydding ferdig") as pt:
                for n, it in enumerate(chosen):
                    pt.step(n, len(chosen), it[1])
                    f, e = do_cleanup([it])
                    freed += f
                    errors += e
            return freed, errors
        self._bg(work, done)

    # --- diskhelse ------------------------------------------------------------
    def _health_card(self):
        c, self.health_box = card("Diskhelse", "Helsen til diskene dine – sier fra før en disk svikter.")
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
            rows = list(dsk["rows"])
            try:                                          # forventet levetid igjen (SSD)
                import pcplus
                fc = next((f for f in pcplus.disk_forecast([dsk]) if f.get("years")), None)
                if fc:
                    rows.append(("Levetid igjen", f"ca. {fc['years']:.0f} år med dagens bruk" if fc["years"] < 50
                                 else "mange år"))
            except Exception:  # noqa: BLE001
                pass
            for r, (k, v) in enumerate(rows):
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
                import ui
                ui.status(self.backup_status, f"Lagret ✓ {f.get_path()}")
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
    # --- widgets ------------------------------------------------------------------
    def _widgets_card(self):
        import desk_widgets
        import widgets as W
        c, i = card("Widgets",
                    "Små vinduer med temperatur, hurtigknapper, familien, batterier og spilletid – på skrivebordet, "
                    "i KDE-panelet og på hjemskjermen på telefonen.")
        if W.plasma_available():
            r = Gtk.Box(spacing=12)
            tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            tb.append(Gtk.Label(label="KDE Plasma-widgets", xalign=0))
            have = W.installed_plasmoids()
            self._kde_status = dim(f"{len(have)} av {len(W.KINDS)} er installert. Etterpå: høyreklikk på skrivebordet → "
                                   "«Legg til widgets» → søk «Kontrollsenter»." if have else
                                   "Legg dem på skrivebordet eller i panelet som vanlige KDE-widgets.")
            tb.append(self._kde_status)
            r.append(tb)
            b = Gtk.Button(label="Oppdater" if have else "Installer", valign=Gtk.Align.CENTER)
            b.add_css_class("suggested-action")

            def inst(_b):
                try:
                    self._kde_status.set_label(W.install_plasmoids())
                except Exception as e:  # noqa: BLE001
                    self._kde_status.set_label(str(e))
            b.connect("clicked", inst)
            r.append(b)
            i.append(r)
            i.append(Gtk.Separator())
        i.append(Gtk.Label(label="Skrivebordswidgets fra Kontrollsenter" + ("" if sys.platform == "win32" else
                                                                             " (for skrivebord uten KDE)"), xalign=0))
        cfg = W.cfg()["desk"]
        for kind, (name, desc, icon, _w, _h) in W.KINDS.items():
            r = Gtk.Box(spacing=12)
            r.append(Gtk.Label(label=icon))
            tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            tb.append(Gtk.Label(label=name, xalign=0))
            tb.append(dim(desc))
            r.append(tb)
            if sys.platform == "win32":
                top = Gtk.CheckButton(label="Alltid øverst", active=bool(cfg.get(kind, {}).get("top")),
                                      valign=Gtk.Align.CENTER)
                top.connect("toggled", lambda w, k=kind: desk_widgets.set_top(k, w.get_active()))
                r.append(top)
            sw = Gtk.Switch(active=bool(cfg.get(kind, {}).get("on")), valign=Gtk.Align.CENTER)
            sw.connect("notify::active", lambda w, _p, k=kind: desk_widgets.show(self.get_root(), k)
                       if w.get_active() else desk_widgets.hide(k))
            r.append(sw)
            i.append(r)
        i.append(dim("Android: hold fingeren på hjemskjermen → Widgets → Kontrollsenter. Seks widgets å velge mellom."))
        self.box.append(c)

    # --- bakgrunn og varsler ------------------------------------------------------
    def _switch_row(self, box, title, sub, active, cb):
        r = Gtk.Box(spacing=12)
        tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        tb.append(Gtk.Label(label=title, xalign=0))
        if sub:
            tb.append(dim(sub))
        r.append(tb)
        sw = Gtk.Switch(active=active, valign=Gtk.Align.CENTER)
        sw.connect("notify::active", cb)
        r.append(sw)
        box.append(r)
        return sw

    def _updates_card(self):
        import updates_ui
        c, i = card("Oppdater alt", "Kontrollsenter, programmene, systemet, fastvaren og de andre PC-ene – med ett "
                                    "trykk. Slå av automatikken hvis du vil gjøre alt selv.")
        i.append(updates_ui.UpdatesCard(lambda: self.get_root()))
        self.box.append(c)

    def _disk_card(self):
        import perf_ui
        c, i = card("Lagring på disk", "Hva Kontrollsenter skriver til og leser fra disken. Av = bare i minnet mens "
                                       "programmet kjører (forsvinner ved omstart).")
        i.append(perf_ui.disk_card_body())
        self.box.append(c)

    def _perf_card(self):
        import perf
        c, i = card("Ytelse – hva Kontrollsenter bruker",
                    "Hvor mye prosessor, minne og disk Kontrollsenter selv bruker. «Eget minne» er det som faktisk er programmets eget.")
        grid = Gtk.Grid(column_spacing=24, row_spacing=6)
        labs = {}
        for n, (k, name) in enumerate((("cpu", "Prosessor"), ("uss", "Eget minne"), ("rss", "Med delte bibl."),
                                       ("read", "Leser fra disk"),
                                       ("write", "Skriver til disk"), ("threads", "Tråder"))):
            a = Gtk.Label(label=name, xalign=0)
            a.add_css_class("dim-label")
            b = Gtk.Label(label="…", xalign=0)
            b.add_css_class("numeric")
            b.add_css_class("heading")
            grid.attach(a, (n % 3) * 2, n // 3, 1, 1)
            grid.attach(b, (n % 3) * 2 + 1, n // 3, 1, 1)
            labs[k] = b
        i.append(grid)

        def tick():
            if not c.get_mapped():
                return True
            u = perf.usage()
            if u.get("t"):
                labs["cpu"].set_label(f"{u['cpu']:.1f} %")
                labs["rss"].set_label(perf.human(u["rss"]))
                labs["uss"].set_label(perf.human(u.get("uss") or u["rss"]))
                labs["read"].set_label(perf.human(u["read"]) + "/s")
                labs["write"].set_label(perf.human(u["write"]) + "/s")
                labs["threads"].set_label(str(u["threads"]))
            return True
        if sys.platform == "win32":
            import winperf
            wl = dim(winperf.summary())
            i.append(wl)
            _old_tick = tick

            def tick():
                if c.get_mapped():
                    wl.set_label(winperf.summary())
                return _old_tick()
        perf.usage()
        GLib.timeout_add_seconds(2, tick)
        sws = {}

        def save_all(w, _p):
            perf.set_save_all(w.get_active(), self.get_root())
            for k, s in sws.items():                      # vis de enkelte bryterne slik de nå er
                want = perf.eco() if k == "eco" else perf.flag(k)
                if s.get_active() != want:
                    s.set_active(want)
                s.set_sensitive(not w.get_active())
        sa = self._switch_row(i, "Spar alt – minst mulig prosessor og minne",
                              "Slår på minimal prosessbruk og mindre minnebruk, og stopper alt ekstra i "
                              "bakgrunnen (prestasjoner, strømpris, hjemme/borte, VR-vakt, oppvarming). Varsler, "
                              "vifter, mobilappen og familiekontroll virker som før.",
                              perf.save_all(), save_all)
        sa.get_parent().add_css_class("ks-strong")
        why = perf.old_reason()
        self._switch_row(i, "Eldre PC – lett grafikk" + (f"  ·  anbefalt for denne PC-en ({why})" if why else ""),
                         "Slår av alt det grafiske som tar ytelse: animasjoner, overganger, skygger, glød, levende "
                         "bakgrunn, lys som følger musa og minigrafene i flisene. Vinduet oppdateres hvert 2. sekund, "
                         "og minne frigjøres når vinduet har vært lukket en stund. Alle funksjonene virker som før.",
                         perf.lowend(), lambda w, _p: perf.set_lowend(w.get_active(), self.get_root()))
        sws["eco"] = self._switch_row(i, "Minimal prosessbruk",
                         "Ingen effekter, vinduet oppdateres hvert 3. sekund, og valgfrie ting i bakgrunnen går "
                         "sjeldnere. Varsler, vifter og mobilappen virker som før. Fint på eldre eller tregere PC-er.",
                         perf.eco(), lambda w, _p: perf.set_eco(w.get_active(), self.get_root()))
        sws["mem"] = self._switch_row(i, "Mindre minnebruk",
                         "Sider du har åpnet blir liggende i minnet. Når vinduet har vært lukket i 3 minutter, "
                         "starter Kontrollsenter stille på nytt i statusfeltet og bruker bare en tredjedel så mye "
                         "minne. Aldri mens du spiller eller noe installeres. Tegner også uten skjermkortdriveren "
                         "(rundt 110 MB mindre) fra neste start.",
                         perf.flag("mem"), lambda w, _p: perf.set_flag("mem", w.get_active()))
        for s in sws.values():
            s.set_sensitive(not perf.save_all())
        self._switch_row(i, "Mindre skriving til disk",
                         "Skåner SSD/M.2: historikk, strøm og spilletid lagres samlet hvert 5.–15. minutt i stedet "
                         "for hvert 10. sekund/minutt, og loggen får bare advarsler og feil. Historikken kan mangle "
                         "de siste minuttene til den lagres.",
                         perf.flag("ssd"), lambda w, _p: perf.set_flag("ssd", w.get_active()))
        self.box.append(c)

    def _features_card(self):
        import funksjoner as F
        c, i = card("Funksjoner", "Velg hva Kontrollsenter skal ha med: Fullstendig, Medium, Minimal eller "
                                  "Egendefinert. Det som er av, vises ikke og gjør ingenting i bakgrunnen.")
        lab = Gtk.Label(xalign=0, wrap=True)
        lab.add_css_class("dim-label")

        def show():
            cf = F.cfg()
            lab.set_label(f"{F.PROFILES[cf['profile']][0]} – {len(F.enabled())} av {len(F.KEYS)} funksjoner er på")
            return False
        show()
        b = Gtk.Button(label="Velg funksjoner …", halign=Gtk.Align.START)
        b.add_css_class("pill")

        def open_(*_):
            import familylock
            import funksjoner_ui
            root = self.get_root()

            def go():
                funksjoner_ui.open_dialog(root)
                GLib.timeout_add(1500, show)
                GLib.timeout_add(6000, show)
            familylock.ask(root, "Skriv familiekoden for å endre funksjonene.", go)
        b.connect("clicked", open_)
        i.append(lab)
        i.append(b)

        def ai_toggle(w, _p):                              # AI-menyen (Claude Code og Codex) – på som standard
            if getattr(w, "_rev", False):
                return
            F.set_feature("ai", w.get_active())
            root = self.get_root()
            try:
                root.sidebar.invalidate_filter()
                root.sidebar.invalidate_headers()
            except Exception:  # noqa: BLE001
                pass
            show()
        self._switch_row(i, "AI-menyen (Claude Code, Codex og Gemini)",
                         "Viser AI i sidemenyen: spør rett i appen, eller åpne assistenten i en mappe. Slå av for å "
                         "skjule menyen.", F.on("ai"), ai_toggle)
        self.box.append(c)

    def _desktop_card(self):
        """Hyprland og GNOME: hva Kontrollsenter har tilpasset (desktop.py) – og knapper for å fikse eller fjerne."""
        import desktop
        if desktop.kind() not in ("hyprland", "gnome"):
            return
        st = desktop.status()
        if st["kind"] == "hyprland":
            c, i = card("Skrivebord: Hyprland" + (f" {st['version']}" if st.get("version") else ""),
                        "Egne vinduer er flytende, mini-vinduet og widgetene kan ligge øverst, hurtigtastene bindes "
                        "direkte i Hyprland, og nattlys bruker hyprsunset.")
        else:
            c, i = card("Skrivebord: GNOME", "Hurtigtastene legges inn som egne tastatursnarveier i GNOME, og "
                                             "skjermprofiler bruker GNOME sine egne skjerminnstillinger.")

        def line(text, ok=None):
            lab = Gtk.Label(label=("✓ " if ok else "• " if ok is None else "⚠ ") + text, xalign=0, wrap=True)
            if ok is False:
                lab.add_css_class("warning")
            i.append(lab)
            return lab

        if st["kind"] == "hyprland":
            mf = st["main_file"]
            own = "kontrollsenter.lua" if st["lua"] else "kontrollsenter.conf"
            line(("Lua-oppsett (hyprland.lua)" if st["lua"] else "Eldre oppsett (hyprland.conf)") +
                 " – Kontrollsenter skriver i samme språk")
            if st["sourced"]:
                line(f"{own} leses inn av {mf} (hurtigtaster, oppstart, skjermkort)", True)
            else:
                line(f"{mf} leser ikke inn {own} – hurtigtastene virker til neste innlogging, og oppstart ved "
                     "innlogging virker ikke", False)
                if st["can_edit"]:
                    b = Gtk.Button(label=f"Legg inn linjen i {mf}", halign=Gtk.Align.START)
                    b.add_css_class("suggested-action")

                    def add(_b):
                        d = desktop._load()
                        d.pop("hypr_source_removed", None)
                        desktop._save(d)
                        desktop.hypr_setup()
                        _b.set_label("Lagt inn ✓")
                        _b.set_sensitive(False)
                    b.connect("clicked", add)
                    i.append(b)
                else:
                    line(f"{mf} er en lenke (dotfiles) eller skrivebeskyttet – legg inn denne linjen selv:")
                    src = Gtk.Label(label=re.split(r"\s+(?:#|--)\s", st["source_line"])[0], xalign=0,
                                    selectable=True)
                    src.add_css_class("monospace")
                    i.append(src)
            line("Oppstart ved innlogging: " + ("uwsm/systemd starter oppstartsfilene" if st["autostart_by_systemd"]
                                                else "via exec-once i kontrollsenter.conf"))
            line("Nattlys: " + ("hyprsunset er installert" if st["hyprsunset"] else
                                "installer pakken «hyprsunset» for nattlys"), True if st["hyprsunset"] else False)
            line("Statusfelt-ikonet vises i Waybar (modulen «tray») og andre linjer som støtter StatusNotifier")
        else:
            ai = st["appindicator"]
            if ai == "on":
                line("Statusfelt-ikonet: AppIndicator-utvidelsen er på", True)
            elif ai == "off":
                line("Statusfelt-ikonet: AppIndicator-utvidelsen er installert, men av", False)
                b = Gtk.Button(label="Slå på AppIndicator", halign=Gtk.Align.START)
                b.add_css_class("suggested-action")
                b.connect("clicked", lambda _b: (desktop.gnome_enable_appindicator(), _b.set_label("Slått på ✓"),
                                                 _b.set_sensitive(False)))
                i.append(b)
            else:
                line("Statusfelt-ikonet krever utvidelsen «AppIndicator and KStatusNotifierItem Support» – uten den "
                     "åpner du Kontrollsenter fra programmenyen", False)
                b = Gtk.LinkButton(uri="https://extensions.gnome.org/extension/615/appindicator-support/",
                                   label="Hent utvidelsen", halign=Gtk.Align.START)
                i.append(b)
            line("Mini-vinduet og widgetene: Alt+Mellomrom → «Alltid øverst» (GNOME lar ikke programmer gjøre det selv)")
        if st.get("keys"):
            line(f"{st['keys']} hurtigtast(er) er lagt inn av Kontrollsenter", True)
        rm = Gtk.Button(label="Fjern det Kontrollsenter har lagt inn i skrivebordet", halign=Gtk.Align.START)
        rm.add_css_class("flat")

        def remove(_b):
            desktop.remove_all()
            _b.set_label("Fjernet ✓ – hurtigtastene legges inn igjen hvis du velger dem på nytt")
            _b.set_sensitive(False)
        rm.connect("clicked", remove)
        i.append(rm)
        self.box.append(c)

    def _simple_card(self):
        c, i = card("Enkel modus", "Bare det viktigste i sidemenyen – fint på barnas PC-er. Alt annet er der "
                                   "fortsatt, og søket (Ctrl+K) finner også de skjulte sidene.")
        win = self.get_root()

        def toggle(w, _p):
            import familylock
            root = self.get_root()

            def do():
                if hasattr(root, "set_simple_mode"):
                    root.set_simple_mode(w.get_active())
            if not w.get_active() and familylock.locked() and not getattr(w, "_rev", False):
                def cancel():
                    w._rev = True
                    w.set_active(True)
                    w._rev = False
                familylock.ask(root, "Skriv familiekoden for å vise alle sidene.", do, cancel)
            elif not getattr(w, "_rev", False):
                do()
        on = False
        try:
            import json as _j
            on = bool(_j.load(open(os.path.expanduser("~/.config/systemmonitor/enkel.json"))).get("on"))
        except (OSError, ValueError):
            pass
        self._switch_row(i, "Enkel modus", "Skjul de avanserte sidene i sidemenyen.", on, toggle)
        _ = win
        self.box.append(c)

    def _push_card(self):
        import push
        import socket
        c, i = card("Pushvarsler til mobilen (ntfy)",
                    "Varsler på telefonen med en gang, også når appen er lukket. Installer ntfy-appen og trykk «Legg til i ntfy» i Kontrollsenter-appen.")
        st = dim("")

        def show():
            try:
                ip = socket.gethostbyname(socket.gethostname())
            except OSError:
                ip = "PC-ens IP"
            import remote
            st.set_label((f"Server: http://{ip}:{remote.PORT}   ·   Emne: {push.topic()}") if push.enabled() else "Av")
        self._switch_row(i, "Send varsler til ntfy", "Bare telefoner som kjenner emnet (nøkkelen) får dem.",
                         push.enabled(), lambda w, _p: (push.set_enabled(w.get_active()), show()))
        st.set_selectable(True)
        st.set_wrap(True)
        i.append(st)
        b = Gtk.Button(label="Ny nøkkel", halign=Gtk.Align.START,
                       tooltip_text="Lag nytt emne – telefoner som har det gamle, slutter å få varsler")
        b.connect("clicked", lambda *_: (push.new_topic(), show()))
        i.append(b)
        show()
        self.box.append(c)

    def _rollback_card(self):
        import lanupdate as L
        if L.is_source_pc():
            return
        prev = L.backup_version()
        c, i = card("Gå tilbake til forrige versjon",
                    "Virker noe dårligere etter en oppdatering? Gå tilbake til versjonen du hadde før. "
                    "Starter en ny versjon ikke i det hele tatt, skjer dette av seg selv.")
        st = dim(f"Forrige versjon: {prev}" if prev else "Det finnes ingen forrige versjon ennå.")
        b = Gtk.Button(label=f"Gå tilbake til {prev}" if prev else "Gå tilbake", halign=Gtk.Align.START)
        b.set_sensitive(bool(prev))

        def go(*_):
            def do():
                try:
                    st.set_label(L.rollback())
                    b.set_sensitive(False)
                    win = self.get_root()
                    if hasattr(win, "restart_app"):
                        GLib.timeout_add_seconds(2, lambda: (win.restart_app(), False)[1])
                except Exception as e:  # noqa: BLE001
                    st.set_label(str(e))
            dlg = Adw.AlertDialog(heading=f"Gå tilbake til {prev}?",
                                  body="Kontrollsenter startes på nytt med forrige versjon. Innstillingene dine "
                                       "beholdes.")
            dlg.add_response("no", "Avbryt")
            dlg.add_response("yes", "Gå tilbake")
            dlg.set_response_appearance("yes", Adw.ResponseAppearance.DESTRUCTIVE)
            dlg.connect("response", lambda _d, r: r == "yes" and do())
            dlg.present(self.get_root())
        b.connect("clicked", go)
        i.append(b)
        i.append(st)
        self.box.append(c)

    def _house_errors_card(self):
        import applog
        c, i = card("Feil fra PC-ene i huset",
                    "Hver PC legger feilene sine på NAS-en (Kontrollsenter/Diagnose) – så de kan sees herfra.")
        lst = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        i.append(lst)
        lst.append(dim("Henter …"))
        view = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        sc = Gtk.ScrolledWindow(child=view, min_content_height=260, visible=False)
        i.append(sc)

        def show(rows):
            while (ch := lst.get_first_child()) is not None:
                lst.remove(ch)
            if not rows:
                lst.append(dim("Ingen feilrapporter på NAS-en ✓"))
            for r in rows:
                row = Gtk.Box(spacing=10)
                col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
                col.append(Gtk.Label(label=f"{r.get('pc')} · {r.get('version')} · "
                                           f"{time.strftime('%d.%m %H:%M', time.localtime(r.get('t', 0)))} · "
                                           f"{r.get('errors', 0)} feil", xalign=0))
                last = Gtk.Label(label=(r.get("last") or "")[-160:], xalign=0, wrap=True)
                last.add_css_class("dim-label")
                last.add_css_class("caption")
                col.append(last)
                row.append(col)
                b = Gtk.Button(label="Vis logg", valign=Gtk.Align.CENTER)

                def open_log(_b, pc=r.get("pc")):
                    self._bg(lambda: applog.house_log(pc),
                             lambda t: (view.get_buffer().set_text(t[-60000:]), sc.set_visible(True)))
                b.connect("clicked", open_log)
                row.append(b)
                lst.append(row)
        self._bg(applog.house_reports, show)
        self.box.append(c)

    def _apps_card(self):
        import apps_ui
        c, i = card("Programmer – topp 5 per funksjon", "De fem beste programmene for hver oppgave på denne PC-en. «Styres fra Kontrollsenter» betyr at du kan bruke dem rett herfra.")
        i.append(apps_ui.all_card())
        self.box.append(c)

    def _general_card(self):
        import background
        cfg = background.load()
        c, i = card("Oppstart og bakgrunn",
                    "Kontrollsenter kan fortsette i bakgrunnen når vinduet lukkes, så overlay, vifter og varsler "
                    "virker selv om vinduet er lukket.")
        for key, title, sub in (("background", "Kjør i bakgrunnen når vinduet lukkes",
                                 "Avslutt fra ikonet i statusfeltet."),
                                ("tray", "Ikon i systemstatusfeltet", "Viser temperaturer, strømmodus, overlay og Avslutt.")):
            self._switch_row(i, title, sub, cfg[key], lambda w, p, k=key: self._notify_set(w, p, k))
        self._switch_row(i, "Åpne vinduet når PC-en starter", "Av: Kontrollsenter starter bare som ikon i "
                                                              "statusfeltet ved innlogging.",
                         cfg.get("show_on_login", True), lambda w, _p: self._notify_set_val("show_on_login", w.get_active()))
        if sys.platform == "win32":
            import winsupport

            def _auto(w, _p):
                import familylock
                if w.get_active():
                    winsupport.autostart_set("Kontrollsenter", winsupport.self_command())
                elif getattr(w, "_rev", False):
                    return
                else:
                    def cancel():
                        w._rev = True
                        w.set_active(True)
                        w._rev = False
                    familylock.ask(self.get_root(), "Familiekontroll er på – skriv koden for å slå av oppstart.",
                                   lambda: winsupport.autostart_set("Kontrollsenter", None), cancel)
            self._switch_row(i, "Start Kontrollsenter ved innlogging", "Starter skjult med ikon i systemstatusfeltet.",
                             bool(winsupport.autostart_get("Kontrollsenter")), _auto)
        else:
            i.append(dim("Start Kontrollsenter skjult ved innlogging: Programmer → Oppstart → Kontrollsenter."))
        self.box.append(c)

    def _infotiles_card(self):
        import infotiles as I
        import dashboard as D
        c, i = card("Fliser i Oversikt", "Vær, strømpris og kalender. Bare stedsnavnet du skriver sendes til "
                                         "værtjenesten (open-meteo.com); strømprisen kommer fra hvakosterstrommen.no.")
        cf = I.cfg()
        st = dim("")
        r = Gtk.Box(spacing=8)
        r.append(Gtk.Label(label="Sted for været", width_chars=16, xalign=0))
        place = Gtk.Entry(text=cf.get("place", ""), placeholder_text="f.eks. Trondheim", hexpand=True)
        r.append(place)
        find = Gtk.Button(label="Lagre")

        def do_find(*_):
            name = place.get_text().strip()
            if not name:
                return

            def work():
                try:
                    nm, lat, lon = I.find_place(name)
                    I.save_cfg(place=nm, lat=lat, lon=lon)
                    return "Været hentes for " + nm + " ✓"
                except Exception as e:  # noqa: BLE001
                    return str(e)
            self._bg(work, lambda t: __import__("ui").status(st, t))
        find.connect("clicked", do_find)
        place.connect("activate", do_find)
        r.append(find)
        i.append(r)
        r = Gtk.Box(spacing=8)
        r.append(Gtk.Label(label="Strømprisområde", width_chars=16, xalign=0))
        dd = Gtk.DropDown.new_from_strings([f"{a} – {n}" for a, n in I.AREAS])
        codes = [a for a, _n in I.AREAS]
        dd.set_selected(codes.index(cf.get("area", "NO1")) if cf.get("area", "NO1") in codes else 0)
        dd.connect("notify::selected", lambda w, _p: I.save_cfg(area=codes[w.get_selected()]))
        r.append(dd)
        i.append(r)
        r = Gtk.Box(spacing=8)
        r.append(Gtk.Label(label="Kalender (iCal)", width_chars=16, xalign=0))
        ics = Gtk.Entry(text=cf.get("ics", ""), hexpand=True,
                        placeholder_text="Hemmelig adresse i iCal-format (Google Kalender → Innstillinger)")
        ics.connect("changed", lambda w: I.save_cfg(ics=w.get_text().strip()))
        r.append(ics)
        i.append(r)
        self._switch_row(i, "Oppsettet «Spill» når et spill starter", "Oversikt bytter til oppsettet Spill mens du "
                         "spiller, og tilbake etterpå.", D._load().get("_auto_game_layout", True),
                         lambda w, _p: D._save_group("_auto_game_layout", w.get_active()))
        i.append(st)
        self.box.append(c)

    def _daily_card(self):
        import theme as T
        c, i = card("Nytt tema hver dag", "Kontrollsenter velger et nytt tema hver morgen – samme hele dagen. "
                                          "Overstyres av temaer per spill.")
        lk = T.look()

        def on(w, _p):
            if w.get_active():
                T._save_look(auto="daily")
            elif T.look().get("auto") == "daily":
                T._save_look(auto=None)
            try:
                import looks
                looks.refresh(force=True)
            except Exception:  # noqa: BLE001
                pass
            today.set_label(f"I dag: {T.THEMES[T.daily_theme()]['name']}" if w.get_active() else "")
        self._switch_row(i, "Nytt tema hver dag", "Overstyrer tid-på-døgnet-temaene.", lk.get("auto") == "daily", on)

        def dark(w, _p):
            T._save_look(daily_dark=w.get_active())
            if T.look().get("auto") == "daily":
                try:
                    import looks
                    looks.refresh(force=True)
                except Exception:  # noqa: BLE001
                    pass
                today.set_label(f"I dag: {T.THEMES[T.daily_theme()]['name']}")
        self._switch_row(i, "Bare mørke temaer", "Av: bare lyse temaer.", lk.get("daily_dark", True), dark)
        today = dim(f"I dag: {T.THEMES[T.daily_theme()]['name']}" if lk.get("auto") == "daily" else "")
        i.append(today)
        self.box.append(c)

    def _fx_card(self):
        import effects
        c, i = card("Effekter og overganger", "Effekter: levende bakgrunn og knapper som gir etter. Overganger: hvordan "
                                              "sidene kommer inn når du bytter. Alt står stille når vinduet ikke er i "
                                              "fokus.")
        row = Gtk.Box(spacing=0, homogeneous=True)
        row.add_css_class("linked")
        first = None
        cur = effects.level()
        for key, label in effects.LEVELS:
            b = Gtk.ToggleButton(label=label.split(" – ")[0], tooltip_text=label)
            if first is None:
                first = b
            else:
                b.set_group(first)
            b.set_active(key == cur)
            b.connect("toggled", lambda w, k=key: w.get_active() and effects.set_level(k))
            row.append(b)
        i.append(row)
        h = Gtk.Label(label="Overganger når du bytter side", xalign=0)
        h.add_css_class("heading")
        i.append(h)
        row = Gtk.Box(spacing=0, homogeneous=True)
        row.add_css_class("linked")
        first, cur = None, effects.transition()
        for key, label in effects.TRANSITIONS:
            b = Gtk.ToggleButton(label=label.split(" – ")[0], tooltip_text=label)
            if first is None:
                first = b
            else:
                b.set_group(first)
            b.set_active(key == cur)
            b.connect("toggled", lambda w, k=key: w.get_active() and effects.set_transition(k, self.get_root()))
            row.append(b)
        i.append(row)
        self.box.append(c)

    def _design_card(self):
        """Bryteren mellom Klassisk og det nye designet (gjelder PC-en; mobilappen har sin egen under Utseende)."""
        import design
        c, i = card("Design", "Velg mellom slik Kontrollsenter alltid har sett ut, og det nye, ryddigere designet med "
                              "7 områder i menyen, faner øverst og roligere utseende. Programmet starter på nytt.")
        row = Gtk.Box(spacing=10, homogeneous=True)
        cur = design.saved_mode()
        first = None
        for key, title, desc in (("klassisk", "Klassisk", "Sidemenyen med alle sidene, slik som før"),
                                 ("ny", "Nytt design", "7 områder, faner øverst, søk i menyen og ryddigere kort")):
            b = Gtk.ToggleButton(active=(key == cur))
            b.add_css_class("ks-swatch")
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            for side in ("top", "bottom", "start", "end"):
                getattr(col, f"set_margin_{side}")(6)
            t = Gtk.Label(label=title, xalign=0)
            t.add_css_class("heading")
            col.append(t)
            d = Gtk.Label(label=desc, xalign=0, wrap=True)
            d.add_css_class("caption")
            d.add_css_class("dim-label")
            col.append(d)
            b.set_child(col)
            if first is not None:
                b.set_group(first)
            first = first or b
            b.connect("toggled", lambda w, k=key: w.get_active() and self._pick_design(k))
            row.append(b)
        i.append(row)
        self.box.append(c)

    def _pick_design(self, key):
        import design
        if key == design.saved_mode():
            return
        design.set_mode(key)
        root = self.get_root()
        if hasattr(root, "restart_app"):
            root.toast("Bytter design – programmet starter på nytt …")
            root.restart_app()

    def _theme_card(self):
        import i18n
        import theme as ks_theme
        import design
        c, i = card("Tema", "Farger på hele Kontrollsenter. Byttes med en gang – også i widgetene og detaljene. "
                            "Samme temaer finnes i mobilappen.")
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True, max_children_per_line=5,
                           min_children_per_line=2, column_spacing=10, row_spacing=10)
        cur = ks_theme.current_theme()
        first = None
        items = list(ks_theme.THEMES.items())
        more = None
        if design.is_new():                # nytt design: 8 utvalgte først, resten under «Flere temaer»
            top = [(k, ks_theme.THEMES[k]) for k in design.CURATED if k in ks_theme.THEMES]
            rest = [(k, t) for k, t in items if k not in design.CURATED]
            if cur not in design.CURATED and cur in ks_theme.THEMES:      # valgt tema vises alltid
                top.append((cur, ks_theme.THEMES[cur]))
                rest = [(k, t) for k, t in rest if k != cur]
            items = top
            more = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True, max_children_per_line=5,
                               min_children_per_line=2, column_spacing=10, row_spacing=10)
            more_items = rest
        for n, (key, t) in enumerate(items + (more_items if more is not None else [])):
            target = flow if n < len(items) else more
            b = Gtk.ToggleButton(active=(key == cur))
            b.add_css_class("flat")
            b.add_css_class("ks-swatch")
            if first:
                b.set_group(first)
            first = first or b
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            da = Gtk.DrawingArea(content_width=132, content_height=78)
            da.set_draw_func(self._draw_swatch, t)
            col.append(da)
            nm = Gtk.Label(label=i18n.tr(t["name"]), xalign=0)
            nm.add_css_class("heading")
            col.append(nm)
            ds = Gtk.Label(label=i18n.tr(t["desc"]), xalign=0, wrap=True, max_width_chars=18)
            ds.add_css_class("caption")
            ds.add_css_class("dim-label")
            col.append(ds)
            b.set_child(col)
            b.connect("toggled", lambda w, k=key: w.get_active() and self._pick_theme(k))
            target.append(b)
            self._swatches = getattr(self, "_swatches", {})
            self._swatches[key] = b
        i.append(flow)
        if more is not None and more.get_first_child() is not None:
            exp = Gtk.Expander(label=i18n.tr("Flere temaer") + f" ({len(more_items)})")
            exp.set_child(more)
            i.append(exp)
        self.box.append(c)
        self._try(self._liquid_card)
        self._try(self._custom_card)
        self._try(self._time_card)
        self._try(self._game_theme_card)

    def _liquid_card(self):
        """Liquid Glass og Aero for ALLE temaer: glanset glass, gjennomsiktig vindu, farge og uskarphet."""
        import liquid
        import theme as ks_theme
        lc = liquid.cfg()
        c, i = card("Liquid Glass og Aero", "Virker med alle temaene. Uskarpheten bak vinduet (Aero) krever "
                                            "KDE Plasma, Hyprland (blur slått på) eller Windows 11.")

        def redraw():
            ks_theme.THEMES["liquid"] = liquid.theme_entry()
            ks_theme.show(ks_theme._SHOWN[0] or ks_theme.current_theme())
        self._switch_row(i, "Flytende glass", "Glassaktige kort og knapper med lysrefleks i kanten og farger som "
                         "skinner gjennom.", ks_theme.glass_on(), lambda w, _p: ks_theme.set_glass(w.get_active()))
        self._switch_row(i, "Gjennomsiktig vindu (Aero)", "Hele vinduet blir glass i temaets farger – du ser det som "
                         "er bak. «Liquid Glass»-temaet er alltid gjennomsiktig.",
                         lc["liquid_aero"], lambda w, _p: (liquid.set_(liquid_aero=w.get_active()), redraw()))
        row = Gtk.Box(spacing=12)
        row.append(Gtk.Label(label="Gjennomsiktighet", xalign=0))
        sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 95, 5)
        sc.set_value(lc["liquid_clear"])
        sc.set_hexpand(True)
        sc.set_format_value_func(lambda _s, v: f"{v:.0f} %")
        sc.connect("value-changed", lambda s_: (liquid.set_(liquid_clear=int(s_.get_value())), redraw()))
        row.append(sc)
        i.append(row)
        tint_rows = []

        def own_tint(w, _p):
            liquid.set_(liquid_theme_tint=not w.get_active())
            for x in tint_rows:
                x.set_sensitive(w.get_active())
            redraw()
        self._switch_row(i, "Egen farge på glasset", "Av: glasset får fargen til temaet du bruker. "
                         "«Liquid Glass»-temaet bruker alltid fargen under.", not lc["liquid_theme_tint"], own_tint)
        row2 = Gtk.Box(spacing=12)
        row2.append(Gtk.Label(label="Farge på glasset", xalign=0, hexpand=True))
        rgba = Gdk.RGBA()
        rgba.parse(lc["liquid_tint"])
        cb = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False), rgba=rgba, valign=Gtk.Align.CENTER)

        def color(btn, _p):
            v = btn.get_rgba()
            liquid.set_(liquid_tint="#%02x%02x%02x" % (int(v.red * 255), int(v.green * 255), int(v.blue * 255)))
            redraw()
        cb.connect("notify::rgba", color)
        row2.append(cb)
        for hx in ("#7aa2ff", "#ff7ab8", "#7affc4", "#ffd27a", "#b48cff", "#ffffff"):
            sw = Gtk.Button(valign=Gtk.Align.CENTER, tooltip_text=hx)
            sw.add_css_class("circular")
            sw.set_size_request(26, 26)
            prov = Gtk.CssProvider()
            prov.load_from_data(f"button {{ background: {hx}; min-width: 22px; min-height: 22px; }}".encode())
            sw.get_style_context().add_provider(prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 9)
            sw.connect("clicked", lambda _b, h=hx: (rgba.parse(h), cb.set_rgba(rgba)))
            row2.append(sw)
        i.append(row2)
        tint_rows.append(row2)
        row2.set_sensitive(not lc["liquid_theme_tint"] or ks_theme.current_theme() == "liquid")
        self._switch_row(i, "Uskarphet bak vinduet", "Det bak blir mykt og uskarpt – lettere å lese, som frostet glass.",
                         lc["liquid_blur"], lambda w, _p: (liquid.set_(liquid_blur=w.get_active()), redraw(),
                                                           liquid.apply(liquid.wanted(ks_theme._t(None)))))
        b = Gtk.Button(label="Bruk Liquid Glass nå", halign=Gtk.Align.START)
        b.add_css_class("pill")
        b.add_css_class("suggested-action")
        b.connect("clicked", lambda *_: (self._swatches.get("liquid") and self._swatches["liquid"].set_active(True)))
        i.append(b)
        self.box.append(c)

    def _pick_theme(self, key):
        import theme as ks_theme
        import looks
        ks_theme.set_theme(key)
        if ks_theme.look().get("auto") == "time" and getattr(self, "_time_sw", None):
            self._time_sw.set_active(False)                 # du valgte selv – tidsplanen slås av
        looks.refresh(force=True)

    # ---- eget tema ----
    def _custom_card(self):
        import theme as ks_theme
        import looks
        c, i = card("Eget tema", "Velg to farger selv – eller la Kontrollsenter hente dem fra skrivebordsbakgrunnen din.")
        cu = ks_theme.look().get("custom") or {"a": "#ff5e9c", "b": "#5b8cff", "dark": True}

        def cbtn(h):
            b = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False), valign=Gtk.Align.CENTER)
            col = Gdk.RGBA()
            col.parse(h)
            b.set_rgba(col)
            return b
        hexof = lambda b: "#%02x%02x%02x" % tuple(round(v * 255) for v in (b.get_rgba().red, b.get_rgba().green,  # noqa: E731
                                                                          b.get_rgba().blue))
        row = Gtk.Box(spacing=10)
        a, b = cbtn(cu["a"]), cbtn(cu["b"])
        row.append(Gtk.Label(label="Farge 1"))
        row.append(a)
        row.append(Gtk.Label(label="Farge 2"))
        row.append(b)
        dark = Gtk.Switch(active=cu.get("dark", True), valign=Gtk.Align.CENTER)
        row.append(Gtk.Label(label="Mørkt", margin_start=10))
        row.append(dark)
        i.append(row)
        bb = Gtk.Box(spacing=8)
        use = Gtk.Button(label="Bruk mine farger")
        use.add_css_class("suggested-action")
        use.connect("clicked", lambda *_: (looks.set_custom(hexof(a), hexof(b), dark.get_active()), self._mark("eget")))
        bb.append(use)
        wp = Gtk.Button(label="Hent fra skrivebordsbakgrunnen")
        st = dim("")

        def from_wall(*_):
            path = looks.wallpaper_path()
            if not path:
                __import__("ui").status(st, "Fant ikke skrivebordsbakgrunnen")
                return
            try:
                ca, cb_ = looks.colors_from_image(path)
            except Exception as e:  # noqa: BLE001
                __import__("ui").status(st, f"Kunne ikke lese bildet ({e})")
                return
            for btn, h in ((a, ca), (b, cb_)):
                col = Gdk.RGBA()
                col.parse(h)
                btn.set_rgba(col)
            looks.set_custom(ca, cb_, dark.get_active())
            self._mark("eget")
            __import__("ui").status(st, "Fargene er hentet fra " + os.path.basename(path) + " ✓")
        wp.connect("clicked", from_wall)
        bb.append(wp)
        i.append(bb)
        i.append(st)
        self.box.append(c)

    def _mark(self, key):
        b = getattr(self, "_swatches", {}).get(key)
        if b is not None and not b.get_active():
            b.set_active(True)

    # ---- tid på døgnet ----
    def _time_card(self):
        import theme as ks_theme
        import looks
        c, i = card("Tema etter tid på døgnet", "Byttes av seg selv – og glir sakte over i det neste temaet de siste "
                                                "20 minuttene, som en solnedgang.")
        lk = ks_theme.look()
        times = lk.get("times") or looks.DEFAULT_TIMES
        keys = [k for k in ks_theme.THEMES if k != "standard"]

        def save():
            out = {}
            for per, (ent, dd) in self._time_rows.items():
                out[per] = [ent.get_text().strip() or looks.DEFAULT_TIMES[per][0], keys[dd.get_selected()]]
            ks_theme._save_look(times=out)
            looks.refresh(force=True)

        def on(w, _p):
            ks_theme._save_look(auto="time" if w.get_active() else "off")
            box.set_sensitive(w.get_active())
            looks.refresh(force=True)
        self._time_sw = self._switch_row(i, "Slå på", None, lk.get("auto") == "time", on)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, sensitive=lk.get("auto") == "time")
        self._time_rows = {}
        for per, label in (("day", "Morgen fra"), ("evening", "Kveld fra"), ("night", "Natt fra")):
            hhmm, th = times.get(per, looks.DEFAULT_TIMES[per])
            r = Gtk.Box(spacing=10)
            r.append(Gtk.Label(label=label, xalign=0, width_chars=11))
            ent = Gtk.Entry(text=hhmm, width_chars=6, max_width_chars=6)
            ent.connect("changed", lambda *_: save())
            r.append(ent)
            dd = Gtk.DropDown.new_from_strings([ks_theme.THEMES[k]["name"] for k in keys])
            dd.set_selected(keys.index(th) if th in keys else 0)
            dd.connect("notify::selected", lambda *_: save())
            r.append(dd)
            box.append(r)
            self._time_rows[per] = (ent, dd)
        i.append(box)
        self.box.append(c)

    # ---- tema per spill ----
    def _game_theme_card(self):
        import theme as ks_theme
        c, i = card("Tema som følger spillet", "Når spillet starter, bytter hele Kontrollsenter tema – og "
                                               "RGB-lysene i PC-en får samme farge. Alt går tilbake når du avslutter.")
        lk = ks_theme.look()
        self._switch_row(i, "RGB-lysene i samme farge", None, lk.get("game_rgb", True),
                         lambda w, _p: ks_theme._save_look(game_rgb=w.get_active()))
        self._switch_row(i, "Levende bakgrunn", "Gløden i bakgrunnen beveger seg sakte og lyser sterkere når PC-en "
                         "jobber hardt.", bool(lk.get("live")), lambda w, _p: ks_theme._save_look(live=w.get_active()))
        try:
            import games_auto
            names = []
            for x in reversed(games_auto.load_sessions()):
                n = x.get("name")
                if n and n not in names:
                    names.append(n)
            g = getattr(games_auto, "running_game", lambda: None)()
            if g and g[1] not in names:
                names.insert(0, g[1])
        except Exception:  # noqa: BLE001
            names = []
        games = dict(lk.get("games") or {})
        for n in games:
            if n not in names:
                names.append(n)
        if not names:
            i.append(dim("Spill du har spilt dukker opp her – start et spill én gang, så kan du velge tema for det."))
        keys = [None] + [k for k in ks_theme.THEMES if k != "standard"]
        labels = ["Ikke bytt"] + [ks_theme.THEMES[k]["name"] for k in keys[1:]]
        for n in names[:14]:
            r = Gtk.Box(spacing=10)
            r.append(Gtk.Label(label=n, xalign=0, hexpand=True, ellipsize=3))
            dd = Gtk.DropDown.new_from_strings(labels)
            dd.set_selected(keys.index(games.get(n)) if games.get(n) in keys else 0)

            def ch(w, _p, n=n):
                cur = dict(ks_theme.look().get("games") or {})
                k = keys[w.get_selected()]
                if k:
                    cur[n] = k
                else:
                    cur.pop(n, None)
                ks_theme._save_look(games=cur)
            dd.connect("notify::selected", ch)
            r.append(dd)
            i.append(r)
        self.box.append(c)

    @staticmethod
    def _draw_swatch(_a, cr, w, h, t):
        import cairo
        import math
        import theme as ks_theme
        rgb = lambda x: tuple(v / 255 for v in ks_theme._rgb(x))  # noqa: E731
        r = 14

        def rr(x, y, ww, hh, rad):
            cr.new_sub_path()
            cr.arc(x + ww - rad, y + rad, rad, -math.pi / 2, 0)
            cr.arc(x + ww - rad, y + hh - rad, rad, 0, math.pi / 2)
            cr.arc(x + rad, y + hh - rad, rad, math.pi / 2, math.pi)
            cr.arc(x + rad, y + rad, rad, math.pi, 3 * math.pi / 2)
            cr.close_path()
        rr(0, 0, w, h, r)
        cr.set_source_rgb(*rgb(t.get("bg", "#121320")))
        cr.fill_preserve()
        cr.save()
        cr.clip()
        for cx, cy, rad, col in ((w * .15, 0, w * .7, t["a"]), (w * .95, h * .1, w * .6, t["b"]),
                                 (w * .5, h * 1.1, w * .6, t["c"])):
            g = cairo.RadialGradient(cx, cy, 0, cx, cy, rad)
            g.add_color_stop_rgba(0, *rgb(col), .55)
            g.add_color_stop_rgba(1, *rgb(col), 0)
            cr.set_source(g)
            cr.paint()
        # et lite «kort» og en knapp med gradienten
        cr.set_source_rgba(*rgb(t.get("card", "#1c1d2b")), .85)
        rr(10, 12, w * .52, h - 24, 8)
        cr.fill()
        g = cairo.LinearGradient(w * .62, 0, w - 10, 0)
        g.add_color_stop_rgb(0, *rgb(t["a"]))
        g.add_color_stop_rgb(1, *rgb(t["b"]))
        cr.set_source(g)
        rr(w * .62, h - 30, w * .38 - 10, 16, 8)
        cr.fill()
        cr.set_source_rgba(*rgb(t.get("fg", "#f3f3f7")), .8)
        for k, ww in enumerate((.36, .26, .3)):
            rr(18, 22 + k * 12, w * ww, 5, 2.5)
            cr.fill()
        cr.restore()

    def _look_card(self):
        import i18n
        c, i = card("Utseende og språk")
        r = Gtk.Box(spacing=12)
        tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        tb.append(Gtk.Label(label="Språk", xalign=0))
        tb.append(dim("Programmet starter på nytt når du bytter språk."))
        r.append(tb)
        codes = [code for code, _s, _f in i18n.LANGS]
        names = [i18n.tr("Automatisk (som Linux)" if code == "auto" else full) for code, _s, full in i18n.LANGS]
        dd = Gtk.DropDown.new_from_strings(names)
        dd.set_valign(Gtk.Align.CENTER)
        if i18n.CHOICE in codes:
            dd.set_selected(codes.index(i18n.CHOICE))

        def pick(w, _p):
            win = self.get_root()
            if hasattr(win, "_set_lang"):
                win._set_lang(codes[w.get_selected()])
        dd.connect("notify::selected", pick)
        r.append(dd)
        i.append(r)
        self.box.append(c)

    def _share_card(self):
        import homepcs
        c, i = card("PC-er hjemme", "Hver PC med Kontrollsenter deler en liten statusfil på NAS-en hvert 5. minutt, "
                                    "så de andre PC-ene i huset kan se den under «PC-er hjemme».")

        def set_share(w, _p):
            cfg = homepcs.load_cfg()
            cfg["share"] = w.get_active()
            homepcs.save_cfg(cfg)
        self._switch_row(i, "Del denne PC-en", None, homepcs.load_cfg().get("share", True), set_share)
        self.box.append(c)

    def _notify_card(self):
        import background
        cfg = background.load()
        c, i = card("Varsler", "Kontrollsenter sier fra når noe er galt. Slå av alt her, eller velg under hvilke "
                               "varsler du vil ha.")
        kinds_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        def master(w, p):
            self._notify_set(w, p, "notify")
            kinds_box.set_sensitive(w.get_active())
            lim.set_sensitive(w.get_active())
        self._switch_row(i, "Vis varsler", "Hovedbryter for alle varsler fra Kontrollsenter på denne PC-en.",
                         cfg["notify"], master)
        self._switch_row(i, "Hold varsler tilbake mens du spiller",
                         "Du får ett samlet varsel når spillet er ferdig. Familie-chat og spilletid kommer likevel.",
                         cfg.get("game_hold", True), lambda w, p: self._notify_set_val("game_hold", w.get_active()))
        self._switch_row(i, "Sjekk systemet og oppdateringer hver 6. time",
                         "Kjører Systemsjekk i bakgrunnen og sier fra om den finner noe.", cfg["periodic"],
                         lambda w, p: self._notify_set(w, p, "periodic"))
        i.append(Gtk.Label(label="Varsle ved:", xalign=0))
        lim = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=4, column_spacing=12,
                          row_spacing=6)
        for key, title, lo, hi in (("cpu_limit", "CPU °C", 60, 100), ("gpu_limit", "GPU °C", 60, 95),
                                   ("disk_limit", "Disk %", 70, 99), ("battery_limit", "Batteri %", 5, 50)):
            one = Gtk.Box(spacing=8)
            one.append(Gtk.Label(label=title))
            sp = Gtk.SpinButton.new_with_range(lo, hi, 1)
            sp.set_value(cfg[key])
            sp.connect("value-changed", lambda w, k=key: self._notify_set_val(k, int(w.get_value())))
            one.append(sp)
            lim.append(one)
        lim.set_sensitive(cfg["notify"])
        i.append(lim)
        self.box.append(c)

        c, i = card("Velg varsler", "Slå av de typene du ikke vil ha. «Noen ser på skjermen din» vises alltid.")
        kinds_box.set_sensitive(cfg["notify"])
        i.append(kinds_box)
        on = dict(cfg.get("kinds") or {})

        def set_kind(w, _p, kid):
            cur = dict(background.load().get("kinds") or {})
            cur[kid] = w.get_active()
            self._notify_set_val("kinds", cur)
        for kid, name, desc, _keys in background.KINDS:
            self._switch_row(kinds_box, name, desc, on.get(kid, True), lambda w, p, k=kid: set_kind(w, p, k))
        self.box.append(c)

    def _notify_set(self, sw, _p, key):
        import familylock
        if key in ("background", "tray") and not sw.get_active() and familylock.locked() \
                and not getattr(self, "_reverting", False):
            def cancel():
                self._reverting = True
                sw.set_active(True)
                self._reverting = False
            familylock.ask(self.get_root(), "Familiekontroll er på – skriv koden for å slå av dette.",
                           lambda: self._notify_set_val(key, False), cancel)
            return
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
        row = Gtk.Box(spacing=8)
        chk = Gtk.Button(label="Se etter oppdatering", tooltip_text="Sjekker hjemmenettet (NAS) først, så GitHub")
        chk.add_css_class("pill")
        chk.connect("clicked", self._check_update)
        row.append(chk)
        gh = Gtk.Button(label="Oppdater fra GitHub", tooltip_text="Hent nyeste versjon direkte fra GitHub")
        gh.add_css_class("pill")
        gh.connect("clicked", self._update_github)
        row.append(gh)
        web = update_source().removesuffix(".git")
        ghl = Gtk.LinkButton(uri=web, label="🌐 GitHub-siden", valign=Gtk.Align.CENTER,
                             tooltip_text=web)
        row.append(ghl)
        adr = Gtk.Button(icon_name="emblem-system-symbolic", tooltip_text="GitHub-adresse …", valign=Gtk.Align.CENTER)
        adr.add_css_class("flat")
        adr.add_css_class("circular")
        adr.connect("clicked", self._edit_source)
        row.append(adr)
        i.append(row)
        import selfupdate
        ar = Gtk.Box(spacing=12)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        col.append(Gtk.Label(label="Oppdater automatisk når Kontrollsenter starter", xalign=0))
        col.append(dim("Når PC-en har vært av, eller du har lukket programmet helt: finnes det en ny versjon, "
                       "installeres den og Kontrollsenter starter på nytt av seg selv. Venter hvis du spiller."))
        ar.append(col)
        asw = Gtk.Switch(active=selfupdate.enabled(), valign=Gtk.Align.CENTER)
        asw.connect("notify::active", lambda s, _p: selfupdate.set_(on=s.get_active()))
        ar.append(asw)
        i.append(ar)
        self.upd_btn = Gtk.Button(label="Oppdater nå", halign=Gtk.Align.START, visible=False)
        self.upd_btn.add_css_class("suggested-action")
        self.upd_btn.connect("clicked", self._update)
        i.append(self.upd_btn)
        self.restart_btn = Gtk.Button(label="Start på nytt", halign=Gtk.Align.START, visible=False)
        self.restart_btn.add_css_class("suggested-action")
        self.restart_btn.connect("clicked", self._restart)
        i.append(self.restart_btn)
        self.upd_status = dim("")
        i.append(self.upd_status)
        pk = Gtk.Button(label="Lag installasjonspakke på skrivebordet", halign=Gtk.Align.START)
        pk.connect("clicked", self._package)
        i.append(pk)
        self.pkg_status = dim("Lager mappen «Kontrollsenter» og «Kontrollsenter.tar.gz» med alt som trengs for å "
                              "installere på en annen PC – inkludert programlisten din.")
        i.append(self.pkg_status)
        import lanupdate
        pub = Gtk.Button(label="Legg denne versjonen på hjemmenettet (NAS)", halign=Gtk.Align.START)
        pub.connect("clicked", self._publish)
        i.append(pub)
        self.pub_status = dim(f"Andre PC-er på hjemmenettet sjekker {lanupdate.location()} og får varsel om "
                              "nyere versjon. Gjelder bare når PC-en er på det lokale nettet.")
        i.append(self.pub_status)
        self.box.append(c)

    def _edit_source(self, *_):
        """GitHub-adressen ligger bak tannhjulet – dukker opp i et lite vindu."""
        dlg = Adw.AlertDialog(heading="GitHub-adresse",
                              body="Hvor Kontrollsenter henter oppdateringer fra når PC-en ikke er på hjemmenettet.")
        e = Gtk.Entry(text=update_source(), activates_default=True, width_chars=46)
        dlg.set_extra_child(e)
        dlg.add_response("cancel", "Avbryt")
        dlg.add_response("reset", "Standard")
        dlg.add_response("ok", "Lagre")
        dlg.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response("ok")

        def resp(_d, rr):
            if rr == "ok":
                set_update_source(e.get_text().strip())
            elif rr == "reset":
                set_update_source(DEFAULT_SOURCE)
            if rr in ("ok", "reset"):
                self.upd_status.set_label(f"Oppdateringer fra {update_source()}")
        dlg.connect("response", resp)
        dlg.present(self.get_root())

    def _update_github(self, *_):
        self.upd_status.set_label("Henter fra GitHub …")

        def done(res):
            txt, ok = res
            self.upd_status.set_label(txt)
            self.upd_btn.set_visible(False)
            self.restart_btn.set_visible(bool(ok))
            return False
        self._bg(update_from_github, done)

    def _check_update(self, *_):
        self.upd_status.set_label("Sjekker …")

        def done(res):
            txt, can = res
            self.upd_status.set_label(txt)
            self.upd_btn.set_visible(can is True)
            self.restart_btn.set_visible(can == "restart")
            return False
        self._bg(check_update, done)

    def _restart(self, *_):
        root = self.get_root()
        if hasattr(root, "restart_app"):
            root.restart_app()

    def _update(self, *_):
        self.upd_status.set_label("Oppdaterer …")

        def done(res):
            ok, msg = res
            self.upd_status.set_label((msg if msg.startswith("Oppdatert") else
                                       "Oppdatert ✓ – start Kontrollsenter på nytt") if ok else f"Feil: {msg}")
            self.upd_btn.set_visible(not ok)
            self.restart_btn.set_visible(ok)
            return False
        self._bg(do_update, done)

    def _publish(self, *_):
        import lanupdate
        self.pub_status.set_label("Legger på hjemmenettet …")

        def done(res):
            ok, msg = res
            self.pub_status.set_label(msg if ok else f"Feil: {msg}")
            return False
        self._bg(lambda: lanupdate.publish(make_package), done)

    def _package(self, *_):
        desk = run(["xdg-user-dir", "DESKTOP"], 5)[1].strip() or str(HOME / "Desktop")
        self.pkg_status.set_label("Lager pakke …")

        def done(res):
            if isinstance(res, Exception):
                self.pkg_status.set_label(f"Feil: {res}")
            else:
                import ui
                ui.status(self.pkg_status, f"Ferdig ✓ {res[0]} og {res[1]}")
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
        import perf_ui
        i.append(perf_ui.disk_switch("logg", compact=True))
        tv = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        tv.get_buffer().set_text(applog.tail(60) or "(tom)")
        sc = Gtk.ScrolledWindow(min_content_height=160, max_content_height=260, propagate_natural_height=True)
        sc.set_child(tv)
        i.append(sc)
        bb = Gtk.Box(spacing=6)
        cp = Gtk.Button(label="Kopier logg")
        cp.connect("clicked", lambda *_: (Gdk.Display.get_default().get_clipboard().set(applog.tail(300)),
                                          __import__("ui").status(self.log_status, "Kopiert ✓")))
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


class ToolsPage(TabbedPage, _Cards):
    """Vedlikehold: systeminfo, opprydding, gjenoppretting og feilsøking."""
    def __init__(self):
        TabbedPage.__init__(self, "vedlikehold")
        import diskusage
        win = sys.platform == "win32"
        if win:
            import wintools as W
        self.tab("system", "System")
        try:                                              # helsepoeng øverst
            import pcplus_ui
            self.box.append(pcplus_ui.health_card(card))
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("pc-helse")
        if win:
            self._try(W._info_card, self, card)
            self._try(W._health_card, self, card)
        else:
            self._try(self._info_card)
            self._try(self._health_card)
        self._try(self._boot_card)
        self._try(self._bench_card)
        try:                                              # stresstest, sammenligning og strømbudsjett
            import pcplus_ui
            self.box.append(pcplus_ui.StressCard(card))
            self.box.append(pcplus_ui.compare_card(card))
            self.box.append(pcplus_ui.budget_card(card))
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("pc-runde4")
        if not win:
            self._try(self._noise_card)
        self.tab("rydd", "Rydd opp")
        self._try(self._autoclean_card)
        self._try(W._cleanup_card, self, card) if win else self._try(self._cleanup_card)
        self._try(diskusage.build_card, self, card)
        self.tab("gjenoppretting", "Gjenoppretting")
        self._try(W._restore_card, self, card) if win else self._try(self._restore_card)
        self._try(self._nasbackup_card)
        self.tab("drivere", "Drivere")
        self._try(self._drivers_tab)
        self.tab("utstyr", "Batteri og skjerm")
        try:                                              # batterihelse og skjermkalibrering
            import equipment_ui
            c, i = card("Batteri og skjerm", "Batterihelse og ladegrense på bærbare, og kalibrering av skjermen. "
                                             "(Wi-Fi ligger under Nett og tilkobling, kontrollere under Spill.)")
            i.append(equipment_ui.EquipmentBox())
            self.box.append(c)
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("utstyr+")
        self.tab("trygghet", "Sikkerhet")
        try:
            import homeplus_ui
            c, i = card("Sikkerhet", "Be om hjelp, passordsjekk, kamera og mikrofon, svindel-skjold, "
                                            "nettverksvakt og fartstest.")
            i.append(homeplus_ui.safety_box(lambda: self.get_root()))
            self.box.append(c)
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("trygghet-kort")
        self.tab("feilsoking", "Feilsøking")
        self._try(self._slow_card)
        self._syscheck_card()
        self._try(self._diag_card)
        self._try(self._ai_help_card)
        self._try(self._house_errors_card)
        self._try(self._log_card)
        self.finish()

    # --- drivere: hovedkortets driverside, skjermkortet og systemets drivere ---------------------
    def _drivers_tab(self):
        import pcplus

        def open_url(u):
            if sys.platform == "win32":
                __import__("winsupport").open_uri(u)
            else:
                Gio.AppInfo.launch_default_for_uri(u, None)
        # hovedkortet
        c, i = card("Hovedkort", "Drivere, BIOS og verktøy for hovedkortet – rett fra produsentens side.")
        info = dim("Leser hovedkortet …")
        i.append(info)
        row = Gtk.Box(spacing=8)
        go = Gtk.Button(label="🌐 Åpne driversiden")
        go.add_css_class("suggested-action")
        go.connect("clicked", lambda *_: open_url(pcplus.driver_url()))
        row.append(go)
        gear = Gtk.Button(icon_name="emblem-system-symbolic", tooltip_text="Endre adressen til driversiden")
        row.append(gear)
        i.append(row)
        addr = dim("")
        addr.set_selectable(True)
        i.append(addr)

        def show_board(b):
            if isinstance(b, Exception) or not b:
                info.set_label("Fant ikke informasjon om hovedkortet.")
            else:
                info.set_label(f"{b['board']}\n{b['text']}")
            addr.set_label(pcplus.driver_url())
        self._bg(pcplus.bios, show_board)

        def edit_url(key, what, current, after=None):
            """⚙: endre en adresse (lagres), «Standard» setter den tilbake."""
            dlg = Adw.AlertDialog(heading=f"Adressen til {what}",
                                  body="Lim inn den nye adressen hvis siden har flyttet. «Standard» setter den tilbake.")
            e = Gtk.Entry(text=current(), hexpand=True, activates_default=True)
            e.set_size_request(460, -1)
            dlg.set_extra_child(e)
            dlg.add_response("cancel", "Avbryt")
            dlg.add_response("std", "Standard")
            dlg.add_response("ok", "Lagre")
            dlg.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
            dlg.set_default_response("ok")

            def resp(_d, r):
                if r == "ok":
                    u = e.get_text().strip()
                    if u and not u.startswith(("http://", "https://")):
                        u = "https://" + u
                    pcplus.set_(**{key: u})
                elif r == "std":
                    pcplus.set_(**{key: ""})
                if after:
                    after()
            dlg.connect("response", resp)
            dlg.present(self.get_root())

        def edit(*_):
            dlg = Adw.AlertDialog(heading="Adressen til driversiden",
                                  body="Lim inn adressen til driversiden for hovedkortet ditt. Tom = standard.")
            e = Gtk.Entry(text=pcplus.cfg().get("driver_url") or pcplus.driver_url(), hexpand=True,
                          activates_default=True)
            e.set_size_request(460, -1)
            dlg.set_extra_child(e)
            dlg.add_response("cancel", "Avbryt")
            dlg.add_response("std", "Standard")
            dlg.add_response("ok", "Lagre")
            dlg.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
            dlg.set_default_response("ok")

            def resp(_d, r):
                if r == "ok":
                    u = e.get_text().strip()
                    if u and not u.startswith(("http://", "https://")):
                        u = "https://" + u
                    pcplus.set_(driver_url=u)
                elif r == "std":
                    pcplus.set_(driver_url="")
                addr.set_label(pcplus.driver_url())
            dlg.connect("response", resp)
            dlg.present(self.get_root())
        gear.connect("clicked", edit)
        self.box.append(c)
        # skjermkortet
        c, i = card("Skjermkort", "Driveren til skjermkortet.")
        gl = dim("Leser …")
        i.append(gl)
        gr = Gtk.Box(spacing=8)
        for key, lab, what in (("nvidia_url", "🌐 NVIDIA-drivere", "NVIDIA-driversiden"),
                               ("amd_url", "🌐 AMD-drivere", "AMD-driversiden")):
            b = Gtk.Button(label=lab)
            b.connect("clicked", lambda *_, k=key: open_url(pcplus.gpu_url(k)))
            gr.append(b)
            g = Gtk.Button(icon_name="emblem-system-symbolic", tooltip_text=f"Endre adressen til {what}")
            g.connect("clicked", lambda *_, k=key, w=what: edit_url(k, w, lambda kk=k: pcplus.gpu_url(kk)))
            gr.append(g)
        i.append(gr)

        def show_gpu(d):
            if isinstance(d, Exception) or not d:
                gl.set_label("Fant ikke skjermkortdriveren (AMD/Intel: Mesa følger med systemet).")
                return
            gl.set_label(f"{d.get('gpu', '')} · driver {d.get('driver', '?')}\n{d.get('where', '')}")
        self._bg(lambda: __import__("features").driver_info(), show_gpu)
        self.box.append(c)
        # systemets drivere
        if sys.platform == "win32":
            c, i = card("Windows-drivere", "Valgfrie driveroppdateringer fra Windows Update.")
            b = Gtk.Button(label="Åpne Windows Update › Valgfrie oppdateringer", halign=Gtk.Align.START)
            b.connect("clicked", lambda *_: open_url("ms-settings:windowsupdate-optionalupdates"))
        else:
            c, i = card("Systemets drivere", "Kjerne, Mesa, NVIDIA, fastvare og CPU-mikrokode – sjekkes og oppdateres "
                                             "av Systemsjekk.")
            b = Gtk.Button(label="Kjør driversjekk", halign=Gtk.Align.START)
            b.connect("clicked", lambda *_: getattr(self.get_root(), "_open_syscheck", lambda _x: None)(None))
        i.append(b)
        self.box.append(c)

    def _ai_help_card(self):
        """AI-hjelp: siste krasj og ukas PC-lege (krever AI-funksjonen)."""
        import funksjoner
        if not funksjoner.on("ai"):
            return
        c, i = card("🤖 AI-hjelp", "La AI-en se på siste krasj eller frys, eller lag ukas rapport fra PC-legen nå. "
                                  "AI-en endrer ingenting før du sier ja.")
        row = Gtk.Box(spacing=8)
        b1 = Gtk.Button(label="Spør AI om siste krasj")
        b1.add_css_class("suggested-action")

        def crash(*_):
            import ai6
            p = ai6.crash_prompt()
            if not p:
                self.get_root().toast("Ingen krasj registrert – fint! 🎉") if hasattr(self.get_root(), "toast") else None
                return
            __import__("aiextra").quick_window(self.get_root(), p)
        b1.connect("clicked", crash)
        row.append(b1)
        b2 = Gtk.Button(label="🩺 PC-legen nå")
        msg = dim("")

        def doctor(*_):
            b2.set_sensitive(False)
            msg.set_label("PC-legen undersøker … (ca. ett minutt)")
            win = self.get_root()

            def done(r):
                b2.set_sensitive(True)
                msg.set_label(str(r))
            self._bg(lambda: __import__("ai6").weekly_doctor(win, getattr(getattr(win, "bg", None), "notify", None),
                                                               force=True), done)
        b2.connect("clicked", doctor)
        row.append(b2)
        i.append(row)
        i.append(msg)
        self.box.append(c)

    def _slow_card(self):
        c, i = card("Hvorfor er PC-en treg?", "Én knapp: Kontrollsenter ser på prosessoren, minnet, disken, "
                                              "temperaturen, strømmodusen og hva som kjører – og forteller hva som er "
                                              "galt og hva du kan gjøre.")
        b = Gtk.Button(label="Finn ut hvorfor", halign=Gtk.Align.START)
        b.add_css_class("suggested-action")
        res = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        def show(r):
            b.set_sensitive(True)
            b.set_label("Sjekk på nytt")
            while (ch := res.get_first_child()) is not None:
                res.remove(ch)
            h = Gtk.Label(label=r["summary"], xalign=0, wrap=True)
            h.add_css_class("heading")
            res.append(h)
            icon = {"bad": "❌", "warn": "⚠️", "ok": "✅"}
            for x in r["items"]:
                row = Gtk.Box(spacing=10)
                col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
                col.append(Gtk.Label(label=f"{icon[x['level']]}  {x['title']}", xalign=0, wrap=True))
                if x["detail"]:
                    col.append(dim(x["detail"]))
                row.append(col)
                if x.get("action"):
                    act = dict(x["action"])
                    lab = act.pop("label", "Fiks")
                    ab = Gtk.Button(label=lab, valign=Gtk.Align.CENTER)

                    def do(_b, a=act):
                        import remote
                        win = self.get_root()
                        threading.Thread(target=lambda: GLib.idle_add(
                            lambda: (win.toast(remote.do_action(win, a)[1]) if hasattr(win, "toast") else None,
                                     False)[1]), daemon=True).start()
                    ab.connect("clicked", do)
                    row.append(ab)
                res.append(row)

        def go(*_):
            b.set_sensitive(False)
            b.set_label("Sjekker …")
            import upkeep
            win = self.get_root()
            self._bg(lambda: upkeep.analyze(win), show)
        b.connect("clicked", go)
        i.append(b)
        i.append(res)
        self.box.append(c)

    def _boot_card(self):
        import pctools
        c, i = card("Oppstart", "Hvor lang tid PC-en bruker på å starte, og hva som tar mest tid.")
        res = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        i.append(res)

        def show(r):
            if r.get("error"):
                res.append(dim(r["error"]))
                return
            nm = {"firmware": "BIOS", "loader": "Oppstartslaster", "kernel": "Kjerne", "initrd": "Initrd",
                  "userspace": "System"}
            h = Gtk.Label(label=f"PC-en brukte {r['total']:.0f} sekunder på å starte", xalign=0)
            h.add_css_class("title-4")
            res.append(h)
            res.append(dim(" · ".join(f"{nm.get(k, k)} {v:.1f} s" for k, v in r["parts"].items())))
            slow = sorted(r["system"] + r["user"], key=lambda x: -x["s"])[:5]
            for x in slow:
                row = Gtk.Box(spacing=8)
                row.append(Gtk.Label(label=x["name"], xalign=0, hexpand=True, ellipsize=3))
                row.append(Gtk.Label(label=f"{x['s']:.1f} s"))
                res.append(row)
            for t in r["tips"]:
                res.append(Gtk.Label(label="💡 " + t, xalign=0, wrap=True))
        self._bg(pctools.boot_report, show)
        self.box.append(c)

    def _bench_card(self):
        import pctools
        c, i = card("Ytelsestest", "Måler prosessor, minne og disk – og sammenligner med forrige gang. Endrer ingenting "
                                   "på PC-en (trygt alternativ til overklokking). Tar rundt 15 sekunder.")
        st = dim("")
        out = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        b = Gtk.Button(label="Kjør ytelsestest", halign=Gtk.Align.START)
        b.add_css_class("suggested-action")

        def show(r):
            b.set_sensitive(True)
            st.set_label("")
            while (ch := out.get_first_child()) is not None:
                out.remove(ch)
            vs = r.get("vs") or {}
            for k, name, unit in (("cpu1", "Prosessor, én kjerne", "poeng"), ("cpuN", "Prosessor, alle kjerner", "poeng"),
                                  ("mem_gbs", "Minne", "GB/s"), ("disk_w", "Disk (skriving)", "MB/s")):
                row = Gtk.Box(spacing=8)
                row.append(Gtk.Label(label=name, xalign=0, hexpand=True))
                d = vs.get(k)
                tail = "" if d is None else (f"  ({d:+d} % mot sist)")
                lab = Gtk.Label(label=f"{r[k]} {unit}{tail}")
                if d is not None and d <= -10:
                    lab.add_css_class("error")
                row.append(lab)
                out.append(row)

        def go(*_):
            b.set_sensitive(False)
            self._bg(lambda: pctools.benchmark(lambda t: GLib.idle_add(st.set_label, t)), show)
        b.connect("clicked", go)
        i.append(b)
        i.append(st)
        i.append(out)
        last = (pctools.cfg().get("bench") or [None])[-1]
        if last:
            show(last)
        self.box.append(c)

    def _noise_card(self):
        import pctools
        c, i = card("Støymåler for viftene", "Mikrofonen lytter mens viftene går fortere og fortere (ca. 30 sekunder). Du får vite hvor fort de kan gå før de bråker. Lyden lagres ikke.")
        st = dim((pctools.cfg().get("noise") or {}).get("text", ""))
        b = Gtk.Button(label="Mål viftestøy", halign=Gtk.Align.START)

        def show(r):
            b.set_sensitive(True)
            st.set_label(r["text"] + "  " + " · ".join(f"{x['pct']} %: {x['db']} dB" for x in r["steps"]))

        def go(*_):
            b.set_sensitive(False)
            win = self.get_root()

            def work():
                try:
                    return pctools.noise_test(win, lambda t: GLib.idle_add(st.set_label, t))
                except Exception as e:  # noqa: BLE001
                    return {"text": f"Fikk ikke målt: {e}", "steps": []}
            self._bg(work, show)
        b.connect("clicked", go)
        i.append(b)
        i.append(st)
        self.box.append(c)

    def _nasbackup_card(self):
        import pctools
        c, i = card("Sikkerhetskopi til NAS-en", "Skjermbilder, klipp og (om du vil) dokumentene dine kopieres til "
                                                 "NAS-en – bare nye og endrede filer. Merk: de havner i fellesmappen "
                                                 "på NAS-en, som alle i huset kan se.")
        dirs = pctools.backup_dirs()
        for d in dirs:
            def toggle(w, _p, d=d):
                cur = pctools.backup_dirs()
                for x in cur:
                    if x["path"] == d["path"]:
                        x["on"] = w.get_active()
                pctools.save_cfg(backup_dirs=cur)
            self._switch_row(i, f"{d['name']}", d["path"], d.get("on"), toggle)
        if not dirs:
            i.append(dim("Fant ingen av mappene (Skjermbilder, klipp, Dokumenter)."))
        self._switch_row(i, "Automatisk hver uke", "Kjøres når strømmen er billigst om natten.",
                         bool(pctools.cfg().get("backup_auto")), lambda w, _p: pctools.save_cfg(backup_auto=w.get_active()))
        last = pctools.cfg().get("backup_last")
        st = dim(("Sist: " + time.strftime("%d.%m %H:%M", time.localtime(last["t"])) +
                  f" – {last['sent']} nye filer") if last else "Ikke kjørt ennå.")
        b = Gtk.Button(label="Ta sikkerhetskopi nå", halign=Gtk.Align.START)

        def go(*_):
            b.set_sensitive(False)

            def work():
                try:
                    r = pctools.backup_run(lambda t: GLib.idle_add(st.set_label, t))
                    return f"Ferdig ✓ – {r['sent']} nye filer ({human(r['bytes'])}), {r['skipped']} uendret"
                except Exception as e:  # noqa: BLE001
                    return f"Feilet: {e}"
            self._bg(work, lambda t: (b.set_sensitive(True), st.set_label(t)))
        b.connect("clicked", go)
        i.append(b)
        i.append(st)
        self.box.append(c)

    def _autoclean_card(self):
        import upkeep
        c, i = card("Automatisk opprydding", "Én gang i måneden ryddes det som er helt trygt: miniatyrbilder, gamle spillfiler og midlertidige filer. Aldri filene dine.")
        cf = upkeep.cfg()
        import updates_ui                                     # én felles bryter (samme som under Oppdatering)
        i.append(updates_ui.auto_row())
        hist = cf.get("history") or []
        st = dim(("Sist: " + time.strftime("%d.%m.%Y", time.localtime(hist[-1]["t"])) + " – "
                  + upkeep.report_text(hist[-1])) if hist else "Ikke kjørt ennå.")
        i.append(st)
        b = Gtk.Button(label="Rydd nå", halign=Gtk.Align.START)

        def run_now(*_):
            b.set_sensitive(False)

            def done(rep):
                b.set_sensitive(True)
                __import__("ui").status(st, (upkeep.report_text(rep) or "Ingenting å rydde") + " ✓")
            self._bg(lambda: upkeep.auto_clean(force=True), done)
        b.connect("clicked", run_now)
        i.append(b)
        self.box.append(c)

    def _syscheck_card(self):
        c, i = card("Systemsjekk", "Går gjennom drivere, disker, oppdateringer og vanlige feil, og forteller hva "
                                   "som bør fikses.")
        b = Gtk.Button(label="Kjør systemsjekk", halign=Gtk.Align.START)
        b.add_css_class("suggested-action")
        b.connect("clicked", lambda *_: self.get_root().activate_action("win.syscheck", None))
        i.append(b)
        self.box.append(c)


class SettingsPage(TabbedPage, _Cards):
    """Alle innstillingene for selve Kontrollsenter samlet på ett sted."""
    def __init__(self):
        TabbedPage.__init__(self, "innstillinger")
        self.tab("utseende", "Utseende")
        self._try(self._design_card)
        self._try(self._theme_card)
        self._try(self._fx_card)
        self._try(self._daily_card)
        self._try(self._look_card)
        self.tab("generelt", "Generelt")
        self._try(self._general_card)
        self._try(self._perf_card)
        self._try(self._disk_card)
        self._try(self._features_card)
        self._try(self._simple_card)
        self._try(self._desktop_card)
        self._try(self._apps_card)
        self._try(self._infotiles_card)
        self.tab("varsler", "Varsler")
        self._try(self._notify_card)
        self._try(self._push_card)
        self.tab("automatikk", "Automatikk")
        try:
            import house_ui
            c, i = card("Huset – natt, strøm og nye versjoner", "Oppdateringskveld, strømsparing, glemte PC-er, "
                                                                "sovemodus og testmodus.")
            i.append(house_ui.house_card(lambda: self.get_root()))
            self.box.append(c)
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("huset-kort")
        try:
            import automation
            automation.night_card(self)
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("stille om natten")
        try:                                              # flyttet hit fra Vedlikehold › Utstyr
            import equipment_ui
            c, i = card("Lyd, spill og ukens video", "Små automatikker som før lå under Vedlikehold.")
            i.append(equipment_ui.settings_box())
            self.box.append(c)
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("utstyr-valg")
        self.tab("widgets", "Widgets")
        self._try(self._widgets_card)
        self.tab("mobil", "Mobil")
        self._try(self._share_card)
        try:
            import remote_ui
            self.box.append(remote_ui.RemoteCard())
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("fjernstyring-kort")
        self.tab("oppdatering", "Oppdatering")
        self._try(self._updates_card)
        self._try(self._app_card)
        self._try(self._rollback_card)
        if sys.platform != "win32":
            self._try(self._backup_card)
        self.finish()
