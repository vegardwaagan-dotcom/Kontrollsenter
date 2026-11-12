"""Oppdatering fra hjemmenettet (NAS-deling over SMB).

Når PC-en er på samme lokale nett som NAS-en, sjekkes \\\\192.168.1.3\\Public\\Kontrollsenter for en nyere
versjon. Mappen inneholder:
    VERSION                 – versjonsnummeret, f.eks. 0.2
    Kontrollsenter.tar.gz   – installasjonspakken (samme som på skrivebordet)
    SHA256SUMS              – sjekksum for pakken (kontrolleres før noe byttes ut)

Leses og skrives med smbclient som gjest (Public-delingen krever ikke passord).
"""
import hashlib
import json
import re
import os
import shutil
import socket
import sys
import subprocess
import tarfile
import tempfile
from pathlib import Path

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CFG = Path.home() / ".config/systemmonitor/oppdatering.json"
DEFAULT = "//192.168.1.3/Public/Kontrollsenter"
PKG = "Kontrollsenter.tar.gz"
BACKUP = Path.home() / ".cache/systemmonitor/forrige-versjon.tar.gz"


# NAS-en kan nås både med IP og navn. Windows lagrer påloggingen per navn, så på Windows virker ofte bare
# \\PERSONALCLOUD (IP-adressen gir «Brukernavnet eller passordet er feil»).
ALTERNATIVES = ["//192.168.1.3/Public/Kontrollsenter", "//PERSONALCLOUD/Public/Kontrollsenter"]
_WIN_PICK = []


def location():
    try:
        configured = json.loads(CFG.read_text()).get("lan")
    except (OSError, ValueError):
        configured = None
    if sys.platform != "win32":
        return configured or DEFAULT
    if _WIN_PICK:
        return _WIN_PICK[0]
    for cand in ([configured] if configured else []) + [c for c in ALTERNATIVES if c != configured]:
        unc = "\\\\" + cand.strip("/").replace("/", "\\")
        try:
            if os.path.isdir(unc):
                _WIN_PICK.append(cand)
                return cand
        except OSError:
            continue
    return configured or ALTERNATIVES[-1]


def _split(loc=None):
    """//vert/deling/mappe -> (vert, //vert/deling, mappe)"""
    parts = (loc or location()).strip("/").split("/")
    host, share, folder = parts[0], parts[1], "/".join(parts[2:])
    return host, f"//{host}/{share}", folder


def version_tuple(v):
    try:
        t = tuple(int(x) for x in v.strip().split("."))
    except ValueError:
        return (0,)
    return (0,) if t == (0, 9, 0) else t      # 0.9.0 var den gamle nummereringen før 0.1


def newer(remote, local):
    return version_tuple(remote) > version_tuple(local)


def on_lan(timeout=1.0):
    """True hvis NAS-en er på samme lokale nett (ikke via ruter/internett) og svarer på SMB."""
    host = _split()[0]
    try:
        if sys.platform == "win32":
            raise OSError("ingen «ip» på Windows")
        r = subprocess.run(["ip", "-4", "route", "get", host], capture_output=True, text=True, timeout=3)
        if r.returncode != 0 or " via " in r.stdout:
            return False
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        with socket.create_connection((host, 445), timeout=timeout):
            return True
    except OSError:
        return False


def _unc_root():
    host, share, _folder = _split()
    return "\\\\" + share.strip("/").replace("/", "\\")          # \\vert\deling


def _smb_windows(cmds):
    """Samme smbclient-kommandoer (cd, get, put, mget, rename, del, mkdir, lcd) – på Windows via nettverkssti."""
    import ntpath
    _host, _share, folder = _split()
    cwd = ntpath.join(_unc_root(), *folder.split("/")) if folder else _unc_root()
    lcd = None

    def nf():
        raise RuntimeError("NT_STATUS_OBJECT_NAME_NOT_FOUND")
    for part in [p.strip() for p in re.split(r';(?=(?:[^"]*"[^"]*")*[^"]*$)', cmds) if p.strip()]:
        args = re.findall(r'"([^"]*)"|(\S+)', part)
        words = [a or b for a, b in args]
        cmd, rest = words[0].lower(), words[1:]
        if cmd == "cd":
            cwd = ntpath.join(cwd, *re.split(r"[\\/]", rest[0]))
            if not os.path.isdir(cwd):
                nf()
        elif cmd == "lcd":
            lcd = rest[0]
        elif cmd == "prompt":
            continue
        elif cmd == "get":
            src = ntpath.join(cwd, rest[0])
            if not os.path.exists(src):
                nf()
            shutil.copyfile(src, rest[1] if len(rest) > 1 else os.path.join(lcd or ".", rest[0]))
        elif cmd == "mget":
            import fnmatch
            for name in os.listdir(cwd):
                if fnmatch.fnmatch(name, rest[0]):
                    shutil.copyfile(ntpath.join(cwd, name), os.path.join(lcd or ".", name))
        elif cmd == "put":
            shutil.copyfile(rest[0], ntpath.join(cwd, rest[1] if len(rest) > 1 else os.path.basename(rest[0])))
        elif cmd == "rename":
            if not os.path.exists(ntpath.join(cwd, rest[0])):
                nf()
            os.replace(ntpath.join(cwd, rest[0]), ntpath.join(cwd, rest[1]))
        elif cmd == "del":
            if not os.path.exists(ntpath.join(cwd, rest[0])):
                nf()
            os.remove(ntpath.join(cwd, rest[0]))
        elif cmd == "mkdir":
            os.makedirs(ntpath.join(cwd, *re.split(r"[\\/]", rest[0])), exist_ok=True)
        elif cmd == "ls":
            return "\n".join(os.listdir(cwd))
    return ""


def smb_mkdir(rel):
    """Lag en mappe på NAS-en (relativt til delingen, f.eks. «Kontrollsenter/PC-er»). Stille hvis den finnes."""
    _host, share, _folder = _split()
    if sys.platform == "win32":
        import ntpath
        try:
            os.makedirs(ntpath.join(_unc_root(), *rel.split("/")), exist_ok=True)
        except OSError:
            pass
        return
    subprocess.run(["smbclient", "-N", share, "-c", f'mkdir "{rel}"'], capture_output=True, timeout=30)


def _smb(cmds, timeout=120):
    if sys.platform == "win32":
        try:
            return _smb_windows(cmds)
        except OSError as e:
            raise RuntimeError(str(e)) from e
    if not shutil.which("smbclient"):
        raise RuntimeError("smbclient mangler – installer pakken samba-client (Fedora) / smbclient (Arch, Debian)")
    _host, share, folder = _split()
    script = (f'cd "{folder}"; ' if folder else "") + cmds
    r = subprocess.run(["smbclient", "-N", share, "-c", script], capture_output=True, text=True, timeout=timeout)
    out = (r.stdout + r.stderr).strip()
    if r.returncode != 0 or "NT_STATUS_" in out:
        err = next((ln for ln in out.splitlines() if "NT_STATUS_" in ln), out.splitlines()[-1] if out else "")
        raise RuntimeError(err.strip() or "ukjent SMB-feil")
    return out


def remote_version():
    tmp = tempfile.mkdtemp()
    try:
        _smb(f'get VERSION "{tmp}/VERSION"', 30)
        return Path(tmp, "VERSION").read_text().strip()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def local_version():
    try:
        return Path(APP_DIR, "VERSION").read_text().strip()
    except OSError:
        return "?"


def check():
    """(status-tekst, ny_versjon eller None). Kaster ikke feil – sier fra i teksten."""
    import applog
    if applog.needs_restart():
        return (f"Versjon {local_version()} er installert, men programmet som kjører er {applog.RUNNING}. "
                "Start Kontrollsenter på nytt for å ta den i bruk."), None
    if not on_lan():
        return "Ikke på hjemmenettet", None
    try:
        rv = remote_version()
    except Exception as e:  # noqa: BLE001
        if "NOT_FOUND" in str(e):
            return "Hjemmenettet: ingen versjon er lagt ut ennå", None
        return f"Hjemmenettet: fant ingen oppdatering ({e})", None
    if newer(rv, local_version()):
        return f"Versjon {rv} er tilgjengelig på hjemmenettet (du har {local_version()})", rv
    return f"Du har nyeste versjon (hjemmenettet har {rv})", None


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def apply_update(package_files):
    """Last ned, kontroller sjekksum og bytt ut programfilene. Returnerer (ok, melding)."""
    tmp = Path(tempfile.mkdtemp())
    try:
        _smb(f'get {PKG} "{tmp}/{PKG}"; get SHA256SUMS "{tmp}/SHA256SUMS"', 300)
        sums = dict(reversed(ln.split(None, 1)) for ln in (tmp / "SHA256SUMS").read_text().splitlines() if ln.strip())
        want = sums.get(PKG, "").strip()
        if not want or want != _sha256(tmp / PKG):
            return False, "sjekksummen stemmer ikke – oppdateringen ble ikke installert"
        with tarfile.open(tmp / PKG) as t:
            t.extractall(tmp / "x", filter="data")
        prog = next((p for p in (tmp / "x").glob("*/program") if p.is_dir()), None)
        if not prog or not (prog / "systemmonitor.py").exists():
            return False, "pakken mangler programfilene"
        # ta vare på versjonen som kjører nå
        BACKUP.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(BACKUP, "w:gz") as t:
            for pat in package_files:
                for src in Path(APP_DIR).glob(pat):
                    t.add(src, arcname=src.name)
        for pat in package_files:
            for src in prog.glob(pat):
                dst = Path(APP_DIR) / src.name
                if src.is_dir():
                    shutil.rmtree(dst, ignore_errors=True)
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
        return True, f"Oppdatert til {local_version()} ✓ – start Kontrollsenter på nytt"
    except Exception as e:  # noqa: BLE001
        return False, str(e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def publish(make_package):
    """Legg denne versjonen på NAS-en, så andre PC-er på hjemmenettet finner den."""
    if not on_lan():
        return False, "NAS-en svarer ikke – er du på hjemmenettet?"
    tmp = Path(tempfile.mkdtemp())
    try:
        _d, archive = make_package(tmp)
        (tmp / "VERSION").write_text(local_version() + "\n")
        (tmp / "SHA256SUMS").write_text(f"{_sha256(archive)}  {PKG}\n")
        _host, share, folder = _split()
        # lag mappen hvis den mangler (feiler stille hvis den finnes)
        smb_mkdir(folder)
        _smb(f'put "{archive}" {PKG}; put "{tmp}/SHA256SUMS" SHA256SUMS; put "{tmp}/VERSION" VERSION', 300)
        # Windows-installasjonen ved siden av: \\NAS\Public\Kontrollsenter\Windows\Installer Kontrollsenter.cmd
        win = Path(APP_DIR) / "pakke-windows"
        if win.is_dir():
            smb_mkdir(f"{folder}/Windows")
            for f in sorted(win.iterdir()):
                if f.is_file() and f.suffix in (".cmd", ".ps1"):
                    _smb(f'cd "Windows"; put "{f}" "{f.name}"', 120)
            # installasjonsfilen (bygges med bygg-windows-installer.sh) – alltid samme navn på NAS-en
            setup = Path(APP_DIR) / "dist" / f"Kontrollsenter-Setup-{local_version()}.exe"
            if setup.exists():
                _smb(f'cd "Windows"; put "{setup}" "Kontrollsenter-Setup.exe"', 300)
        return True, f"Versjon {local_version()} er lagt på hjemmenettet ✓ ({location()})"
    except Exception as e:  # noqa: BLE001
        return False, str(e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def is_source_pc():
    """PC-en der programmet utvikles (Git-mappe) – den legger nye versjoner ut på NAS-en."""
    return os.path.isdir(os.path.join(APP_DIR, ".git"))      # ikke Git-arbeidskopier (der er .git en fil)


def auto_publish(make_package):
    """På utviklings-PC-en: legg ut versjonen automatisk hvis den er nyere enn den på NAS-en.
    Returnerer versjonen som ble lagt ut, eller None."""
    if not is_source_pc() or not on_lan():
        return None
    try:
        rv = remote_version()
    except Exception as e:  # noqa: BLE001
        if "NOT_FOUND" not in str(e):
            return None
        rv = "0"
    if not newer(local_version(), rv):
        return None
    ok, _msg = publish(make_package)
    return local_version() if ok else None
