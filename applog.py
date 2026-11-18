"""Feillogg for Kontrollsenter: ~/.cache/systemmonitor/logg.txt (roteres, maks ~2 MB totalt).

Logger
  * oppstart (versjon, distro, kjerne)
  * alle uventede feil – også i bakgrunnstråder
  * alle feilmeldinger som vises i programmet («Feil: …», «Kunne ikke …» osv.)
"""
import logging
import logging.handlers
import os
import platform
import re
import sys
import threading

LOG_DIR = os.path.expanduser("~/.cache/systemmonitor")
LOG_FILE = os.path.join(LOG_DIR, "logg-test.txt" if os.environ.get("SYSTEMMONITOR_APP_ID") else "logg.txt")
log = logging.getLogger("systemmonitor")
_ERR_RX = re.compile(r"^\s*(⚠\s*)?(Feil|Kunne ikke|Feilet|Fikk ikke|Klarte ikke|Mistet kontakt|Noe kunne ikke|"
                     r"Error|Could not|Failed|Lost contact)", re.I)
_last = {"msg": None}


def version():
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")) as f:
            return f.read().strip()
    except OSError:
        return "?"


RUNNING = version()          # versjonen som kjører nå – filene på disken kan være nyere etter en oppdatering


def needs_restart():
    """Ny versjon ligger på disken, men programmet som kjører er eldre (f.eks. i bakgrunnen siden i går)."""
    disk = version()
    return disk if disk not in ("?", RUNNING) else None


def setup():
    if getattr(setup, "done", False):
        return
    setup.done = True
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        h = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=512_000, backupCount=3, encoding="utf-8")
    except OSError:
        return
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(h)

    def hook(t, v, tb):
        log.error("Uventet feil", exc_info=(t, v, tb))
        sys.__excepthook__(t, v, tb)
    sys.excepthook = hook

    def thook(args):
        log.error("Uventet feil i tråd %s", getattr(args.thread, "name", "?"),
                  exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
    threading.excepthook = thook

    distro = ""
    try:
        for ln in open("/etc/os-release"):
            if ln.startswith("PRETTY_NAME="):
                distro = ln.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    log.info("Kontrollsenter %s startet · %s · kjerne %s · Python %s", version(), distro,
             platform.release(), platform.python_version())

    # Alle feilmeldinger som vises i grensesnittet havner også i loggen
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk
        orig = Gtk.Label.set_label

        def set_label(self, text, *a, **k):
            if isinstance(text, str) and _ERR_RX.match(text) and text != _last["msg"]:
                _last["msg"] = text
                log.warning("Vist feilmelding: %s", text)
            return orig(self, text, *a, **k)
        Gtk.Label.set_label = set_label
    except Exception:  # noqa: BLE001
        pass


def tail(lines=300):
    try:
        with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-lines:])
    except OSError:
        return ""


def upload_errors(force=False):
    """Legg de siste linjene av feilloggen på NAS-en (Kontrollsenter/Diagnose/<PC>-logg.txt) når det har kommet
    nye feil siden sist – så feil på de andre PC-ene kan finnes herfra. Kalles fra bakgrunnen."""
    import json
    import socket
    import time
    state_p = os.path.join(LOG_DIR, "feil-sendt.json")
    try:
        st = json.load(open(state_p))
    except (OSError, ValueError):
        st = {}
    try:
        lines = open(LOG_FILE, encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return False
    errs = [ln for ln in lines if " ERROR " in ln]
    last = errs[-1] if errs else ""
    if not force and (not errs or last == st.get("last")):
        return False
    import shutil
    import tempfile
    import lanupdate as L
    if not L.on_lan():
        return False
    host = socket.gethostname()
    tmp = tempfile.mkdtemp()
    try:
        p = os.path.join(tmp, f"{host}-logg.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write(f"Kontrollsenter {RUNNING} på {host} – {time.strftime('%Y-%m-%d %H:%M')}\n"
                    f"{len(errs)} feil i loggen. Siste 400 linjer:\n\n" + "\n".join(lines[-400:]))
        s = os.path.join(tmp, f"{host}-status.json")
        with open(s, "w") as f:
            json.dump({"pc": host, "version": RUNNING, "t": time.time(), "errors": len(errs), "last": last[-300:]}, f)
        _h, _s, folder = L._split()
        L.smb_mkdir(f"{folder}/Diagnose")
        L._smb(f'cd "Diagnose"; put "{p}" "{os.path.basename(p)}"; put "{s}" "{os.path.basename(s)}"', 60)
        st["last"] = last
        with open(state_p, "w") as f:
            json.dump(st, f)
        return True
    except Exception:  # noqa: BLE001
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def house_reports():
    """Feilrapportene alle PC-ene har lagt på NAS-en: [{pc, version, t, errors, last}]."""
    import json
    import shutil
    import tempfile
    import lanupdate as L
    out = []
    if not L.on_lan():
        return out
    tmp = tempfile.mkdtemp()
    try:
        try:
            L._smb(f'cd "Diagnose"; prompt OFF; lcd "{tmp}"; mget *-status.json', 60)
        except Exception:  # noqa: BLE001
            return out
        for f in sorted(os.listdir(tmp)):
            try:
                out.append(json.load(open(os.path.join(tmp, f))))
            except (OSError, ValueError):
                continue
        return sorted(out, key=lambda x: -x.get("t", 0))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def house_log(pc):
    """Hele feilloggen en PC har lagt på NAS-en."""
    import re as _re
    import shutil
    import tempfile
    import lanupdate as L
    if not _re.fullmatch(r"[\w.\-]+", pc or ""):
        raise ValueError("ugyldig navn")
    tmp = tempfile.mkdtemp()
    try:
        L._smb(f'cd "Diagnose"; get "{pc}-logg.txt" "{tmp}/l.txt"', 60)
        return open(os.path.join(tmp, "l.txt"), encoding="utf-8", errors="replace").read()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def crash(title):
    """Uventet feil under oppstart: skriv den til krasj.txt, legg den på NAS-en og vis en melding.
    På Windows (uten konsoll) er dette den eneste måten å se hvorfor programmet ikke startet."""
    import traceback
    text = f"{title} – Kontrollsenter {RUNNING}\n\n" + traceback.format_exc()
    log.error(text)
    path = os.path.join(os.path.dirname(LOG_FILE), "krasj.txt")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError:
        pass
    try:                                                   # på NAS-en, så feilen kan finnes herfra
        import shutil
        import socket
        import tempfile
        import lanupdate as L
        if L.on_lan():
            tmp = tempfile.mkdtemp()
            p = os.path.join(tmp, f"{socket.gethostname()}-krasj.txt")
            shutil.copyfile(path, p)
            _h, _s, folder = L._split()
            L.smb_mkdir(f"{folder}/Diagnose")
            L._smb(f'cd "Diagnose"; put "{p}" "{os.path.basename(p)}"', 60)
    except Exception:  # noqa: BLE001
        pass
    try:                                                   # nettopp oppdatert? gå tilbake til forrige versjon
        import lanupdate as L
        if L.ROLLBACK.exists():
            text += "\n\n" + L.rollback() + " (den nye versjonen startet ikke)."
    except Exception:  # noqa: BLE001
        pass
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, text[-1800:] + "\n\nFeilen er lagt på NAS-en (Kontrollsenter\\"
                                             "Diagnose) og i " + path, title, 0x10)
        except Exception:  # noqa: BLE001
            pass
