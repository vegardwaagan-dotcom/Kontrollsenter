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
LOG_FILE = os.path.join(LOG_DIR, "logg.txt")
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
