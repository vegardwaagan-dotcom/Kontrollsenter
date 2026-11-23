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
import time
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


def _allow_exec(rel):
    """Gi «Everyone» full tilgang (inkl. kjøring) til en fil på NAS-en. Uten kjørerett nekter Windows å starte
    .exe/.cmd fra nettverksmappen («Du har ikke tilgang»). Feiler stille – bare et forsøk."""
    if sys.platform == "win32" or not shutil.which("smbcacls"):
        return
    _host, share, folder = _split()
    path = f"{folder}/{rel}" if folder else rel
    try:
        subprocess.run(["smbcacls", share, path, "-N", "--modify", "ACL:Everyone:ALLOWED/0x0/FULL"],
                       capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        pass


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


def pilot_info():
    """Testmodus: {"version", "pc", "until", "failed"} fra NAS-en, eller None."""
    import json as _j
    tmp = tempfile.mkdtemp()
    try:
        _smb(f'get PILOT.json "{tmp}/PILOT.json"', 30)
        return _j.loads(Path(tmp, "PILOT.json").read_text())
    except Exception:  # noqa: BLE001
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def pilot_failed(version):
    """Testmaskinen rullet tilbake: merk versjonen som feilet, så de andre ikke får den."""
    import json as _j
    import savegames
    pil = pilot_info()
    if not pil or pil.get("version") != version or pil.get("pc") != savegames.pc_name():
        return
    pil["failed"] = True
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "PILOT.json").write_text(_j.dumps(pil))
        _smb(f'put "{tmp}/PILOT.json" PILOT.json', 30)
    except Exception:  # noqa: BLE001
        pass
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check():
    """(status-tekst, ny_versjon eller None). Kaster ikke feil – sier fra i teksten."""
    import applog
    if applog.needs_restart():
        return (f"Versjon {local_version()} er installert, men programmet som kjører er {applog.RUNNING}. "
                "Start Kontrollsenter på nytt for å ta den i bruk."), None
    if not on_lan():
        try:                                      # borte: en venn-PC hjemme videresender NAS-ens versjon
            import relayupdate
            r = relayupdate.remote()
        except Exception:  # noqa: BLE001
            r = None
        if not r:
            return "Ikke på hjemmenettet (og ingen venn-PC hjemme svarer)", None
        if not newer(r["version"], local_version()):
            return f"Du har nyeste versjon (via {r['friend']['name']}: {r['version']})", None
        if r.get("pilot"):
            return f"Versjon {r['version']} testes først hjemme – prøv igjen senere", None
        return f"Versjon {r['version']} er tilgjengelig via {r['friend']['name']} (du har {local_version()})", r["version"]
    try:
        rv = remote_version()
    except Exception as e:  # noqa: BLE001
        if "NOT_FOUND" in str(e):
            return "Hjemmenettet: ingen versjon er lagt ut ennå", None
        return f"Hjemmenettet: fant ingen oppdatering ({e})", None
    if newer(rv, local_version()):
        pil = pilot_info()
        if pil and pil.get("version") == rv and pil.get("pc"):
            import savegames
            if pil.get("failed"):
                return f"Versjon {rv} feilet på {pil['pc']} under testing – den hoppes over", None
            if savegames.pc_name() != pil["pc"] and time.time() < pil.get("until", 0):
                return (f"Versjon {rv} testes først på {pil['pc']} (til "
                        f"{time.strftime('%d.%m kl. %H:%M', time.localtime(pil['until']))})"), None
        return f"Versjon {rv} er tilgjengelig på hjemmenettet (du har {local_version()})", rv
    return f"Du har nyeste versjon (hjemmenettet har {rv})", None


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fetch_program(tmp):
    """Hent pakken fra NAS-en (eller via en venn-PC hjemme når vi er borte), kontroller sjekksummen og pakk ut.
    Returnerer programmappen (eller kaster)."""
    if on_lan():
        _smb(f'get {PKG} "{tmp}/{PKG}"; get SHA256SUMS "{tmp}/SHA256SUMS"', 300)
        sums = dict(reversed(ln.split(None, 1)) for ln in (tmp / "SHA256SUMS").read_text().splitlines()
                    if ln.strip())
        want = sums.get(PKG, "").strip()
        if not want or want != _sha256(tmp / PKG):
            raise RuntimeError("sjekksummen stemmer ikke – oppdateringen ble ikke installert")
    else:
        import relayupdate
        info = relayupdate.remote(force=True)
        if not info or not info.get("sha256"):
            raise RuntimeError("ingen venn-PC hjemme svarer – prøv igjen senere")
        relayupdate.download("pkg", tmp / PKG, info)
    with tarfile.open(tmp / PKG) as t:
        t.extractall(tmp / "x", filter="data")
    prog = next((p for p in (tmp / "x").glob("*/program") if p.is_dir()), None)
    if not prog or not (prog / "systemmonitor.py").exists():
        raise RuntimeError("pakken mangler programfilene")
    return prog


def _install_entry(src):
    dst = Path(APP_DIR) / src.name
    if src.is_dir():
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)


def apply_update(package_files):
    """Last ned, kontroller sjekksum og bytt ut programfilene. Returnerer (ok, melding).

    ALT i pakkens programmappe kopieres – ikke bare det denne (eldre) versjonen kjenner til. Ellers mangler
    nye mapper (f.eks. remote_web i 0.7.0) etter en oppdatering fra en gammel versjon."""
    tmp = Path(tempfile.mkdtemp())
    import progress as P
    pt = P.begin("Oppdaterer Kontrollsenter", "Henter den nye versjonen fra NAS-en")
    pt.set(0.05)
    try:
        try:
            prog = _fetch_program(tmp)
        except RuntimeError as e:
            pt.done(str(e), False)
            return False, str(e)
        pt.set(0.6, "Tar vare på versjonen du har nå")
        old = local_version()
        # ta vare på versjonen som kjører nå
        BACKUP.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(BACKUP, "w:gz") as t:
            for pat in package_files:
                for src in Path(APP_DIR).glob(pat):
                    t.add(src, arcname=src.name)
        entries = sorted(prog.iterdir())
        for n, src in enumerate(entries):
            pt.set(0.7 + 0.3 * n / max(1, len(entries)), "Installerer filene")
            _install_entry(src)
        arm_rollback(old, local_version())
        pt.done(f"Oppdatert til {local_version()}")
        return True, f"Oppdatert til {local_version()} ✓ – start Kontrollsenter på nytt"
    except Exception as e:  # noqa: BLE001
        return False, str(e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


ROLLBACK = Path.home() / ".local/share/systemmonitor/oppdatering-sjekk.json"


def arm_rollback(old, new):
    """Etter en oppdatering: starter den nye versjonen ikke (krasjer ved oppstart), går vi tilbake av oss selv."""
    import json
    if is_source_pc():
        return
    ROLLBACK.parent.mkdir(parents=True, exist_ok=True)
    ROLLBACK.write_text(json.dumps({"from": old, "to": new, "t": time.time(), "starts": 0}))


def backup_version():
    """Versjonen i sikkerhetskopien (den forrige), eller None."""
    try:
        with tarfile.open(BACKUP) as t:
            f = t.extractfile("VERSION")
            return f.read().decode().strip() if f else None
    except (OSError, KeyError, tarfile.TarError):
        return None


def rollback():
    """Gå tilbake til forrige versjon (fra sikkerhetskopien som ble tatt ved siste oppdatering)."""
    if is_source_pc():
        raise RuntimeError("ikke på utviklings-PC-en")
    if not BACKUP.exists():
        raise RuntimeError("det finnes ingen forrige versjon å gå tilbake til")
    prev = backup_version() or "forrige versjon"
    bad = local_version()
    with tarfile.open(BACKUP) as t:
        t.extractall(APP_DIR, filter="data")
    try:
        ROLLBACK.unlink()
    except FileNotFoundError:
        pass
    try:                                                   # testmodus: stopp de andre PC-ene
        pilot_failed(bad)
    except Exception:  # noqa: BLE001
        pass
    return f"Tilbake på {prev} ✓ – start Kontrollsenter på nytt"


def repair_missing(package_files):
    """Ved oppstart: hent filer/mapper som mangler etter en oppdatering fra en eldre versjon (den kopierte bare
    det den kjente til). Gjør ingenting på utvikler-PC-en eller når alt er på plass. Returnerer det som ble hentet."""
    if is_source_pc():
        return []
    missing = [p for p in package_files if not any(Path(APP_DIR).glob(p))
               and not (p == "*.ps1" and sys.platform != "win32")]
    if not missing or not on_lan():
        return []
    tmp = Path(tempfile.mkdtemp())
    try:
        prog = _fetch_program(tmp)
        got = []
        for pat in missing:
            for src in prog.glob(pat):
                _install_entry(src)
                got.append(src.name)
        return got
    except Exception:  # noqa: BLE001
        return []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def publish(make_package, selftest=True):
    """Legg denne versjonen på NAS-en, så andre PC-er på hjemmenettet finner den.
    På utviklings-PC-en må selvtesten (alle sider, faner og mobilappen) være bestått først."""
    if not on_lan():
        return False, "NAS-en svarer ikke – er du på hjemmenettet?"
    if selftest and is_source_pc():
        try:
            import selftest as ST
            if not ST.passed_for_current():
                r = ST.run()
                if not r["ok"]:
                    return False, ("Selvtesten feilet – versjonen ble IKKE lagt ut:\n  " +
                                   "\n  ".join(r["errors"][:12]))
        except Exception as e:  # noqa: BLE001
            return False, f"Selvtesten kunne ikke kjøres: {e}"
    tmp = Path(tempfile.mkdtemp())
    try:
        _d, archive = make_package(tmp)
        (tmp / "VERSION").write_text(local_version() + "\n")
        (tmp / "SHA256SUMS").write_text(f"{_sha256(archive)}  {PKG}\n")
        _host, share, folder = _split()
        # lag mappen hvis den mangler (feiler stille hvis den finnes)
        smb_mkdir(folder)
        _smb(f'put "{archive}" {PKG}; put "{tmp}/SHA256SUMS" SHA256SUMS; put "{tmp}/VERSION" VERSION', 300)
        try:                                               # testmodus: én PC prøver versjonen først
            import json as _j
            import house
            pc = house.cfg()["pilot"]
            pil = {"version": local_version(), "pc": pc["pc"], "until": time.time() + pc["hours"] * 3600,
                   "failed": False} if pc["on"] and pc["pc"] else {"version": local_version(), "pc": ""}
            (tmp / "PILOT.json").write_text(_j.dumps(pil))
            _smb(f'put "{tmp}/PILOT.json" PILOT.json', 30)
        except Exception:  # noqa: BLE001
            pass
        # Windows-installasjonen ved siden av: \\NAS\Public\Kontrollsenter\Windows\Installer Kontrollsenter.cmd
        win = Path(APP_DIR) / "pakke-windows"
        if win.is_dir():
            smb_mkdir(f"{folder}/Windows")
            for f in sorted(win.iterdir()) + [Path(APP_DIR) / "msi_wmi.ps1"]:
                if f.is_file() and f.suffix in (".cmd", ".ps1"):
                    _smb(f'cd "Windows"; put "{f}" "{f.name}"', 120)
                    _allow_exec(f"Windows/{f.name}")
            # installasjonsfilen (bygges med bygg-windows-installer.sh) – alltid samme navn på NAS-en
            setup = Path(APP_DIR) / "dist" / f"Kontrollsenter-Setup-{local_version()}.exe"
            if setup.exists():
                _smb(f'cd "Windows"; put "{setup}" "Kontrollsenter-Setup.exe"', 300)
                _allow_exec("Windows/Kontrollsenter-Setup.exe")
        # Android-appen (bygges med bygg-android.sh): \\NAS\Public\Kontrollsenter\Android\Kontrollsenter.apk
        apk = Path(APP_DIR) / "dist" / f"Kontrollsenter-{local_version()}.apk"
        if apk.exists():
            smb_mkdir(f"{folder}/Android")
            _smb(f'cd "Android"; put "{apk}" "Kontrollsenter.apk"', 120)
            _allow_exec("Android/Kontrollsenter.apk")
            # versjonsfil som PC-ene leser for å si fra til appen at en oppdatering er tilgjengelig
            import json as _json
            p = [int(x) for x in (local_version().split(".") + ["0", "0"])[:3]]
            (tmp / "versjon.json").write_text(_json.dumps({
                "version": local_version(), "code": p[0] * 10000 + p[1] * 100 + p[2],
                "sha256": _sha256(apk), "size": apk.stat().st_size}))
            _smb(f'cd "Android"; put "{tmp}/versjon.json" "versjon.json"', 60)
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
    try:                                     # i bakgrunnen: bare versjoner som allerede har bestått selvtesten
        import selftest as ST
        if not ST.passed_for_current():
            return None
    except Exception:  # noqa: BLE001
        return None
    ok, _msg = publish(make_package, selftest=False)
    return local_version() if ok else None
