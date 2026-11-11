"""Finner eksterne verktøy uansett hvordan de er installert (systempakke, pipx eller egen venv).

Systemmonitor bruker TRCC (trcc-linux) for CPU-skjermen. På Bazzite følger den med i
/usr/bin, på andre distroer installeres den med pipx av installer.sh.
"""
import functools
import glob
import os
import subprocess
import sys

HOME = os.path.expanduser("~")
TRCC_CANDIDATES = [
    "/usr/bin/trcc",
    "/usr/local/bin/trcc",
    os.path.join(HOME, ".local/bin/trcc"),
    os.path.join(HOME, ".local/share/systemmonitor/trcc-venv/bin/trcc"),
]


def _works(path):
    if not (os.path.isfile(path) and os.access(path, os.X_OK)):
        return False
    try:
        return subprocess.run([path, "--version"], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


@functools.lru_cache(maxsize=1)
def find_trcc():
    """Første trcc-kommando som faktisk virker (en ødelagt gammel installasjon hoppes over)."""
    for p in TRCC_CANDIDATES:
        if _works(p):
            return p
    return None


def enable_trcc_import():
    """Gjør `import trcc` mulig også når trcc-linux er installert med pipx/venv
    (brukes til live forhåndsvisning av LCD-skjermen)."""
    try:
        import trcc  # noqa: F401
        return True
    except ImportError:
        pass
    ver = f"python{sys.version_info.major}.{sys.version_info.minor}"
    for venv in (os.path.join(HOME, ".local/share/pipx/venvs/trcc-linux"),
                 os.path.join(HOME, ".local/share/systemmonitor/trcc-venv")):
        for sp in glob.glob(os.path.join(venv, "lib", ver, "site-packages")):
            if sp not in sys.path:
                sys.path.append(sp)
            try:
                import trcc  # noqa: F401
                return True
            except ImportError:
                sys.path.remove(sp)
    return False
