"""Felles tilgang: ett passord gir Kontrollsenter de rettighetene det trenger på denne PC-en (skjermkort, strøm,
vifter, MSI) – i stedet for at hver side spør for seg. Bare det PC-en faktisk har, settes opp.
"""
import glob
import getpass
import os
import subprocess
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
NAMES = {"gpu": "skjermkort (klokker, overklokking, vifter)", "gpupower": "strømmodus for NVIDIA",
         "fan": "hovedkortvifter", "msi": "MSI-funksjoner", "autologin": "innlogging uten passord etter omstart"}


def _has_pwm():
    return bool(glob.glob("/sys/class/hwmon/hwmon*/pwm[0-9]"))


def needed():
    """Delene som gjelder denne PC-en og ikke er satt opp ennå."""
    if sys.platform == "win32":
        return []
    out = []
    try:
        import gpu as G
        gs = G.detect()
        if any(not g.get("integrated") for g in gs) and not G.helper_ready():
            out.append("gpu")
        if any(g["vendor"] == "nvidia" for g in gs) and not os.path.exists("/usr/local/bin/systemmonitor-gpu-power"):
            out.append("gpupower")
    except Exception:  # noqa: BLE001
        pass
    if _has_pwm() and not os.path.exists("/usr/local/bin/systemmonitor-fan"):
        out.append("fan")
    try:
        vendor = open("/sys/class/dmi/id/sys_vendor").read()
    except OSError:
        vendor = ""
    if "Micro-Star" in vendor and not os.path.exists("/usr/local/bin/systemmonitor-msi"):
        out.append("msi")
    try:
        import autologin
        if autologin.enabled() and not os.path.exists(autologin.HELPER):
            out.append("autologin")
    except Exception:  # noqa: BLE001
        pass
    return out


def command(parts=None):
    parts = needed() if parts is None else parts
    return ["/bin/bash", os.path.join(APP_DIR, "install-alt.sh"), getpass.getuser(), *parts] if parts else None


def setup_all(parts=None):
    """Spør om passordet én gang og sett opp alt som trengs. Returnerer en tekst."""
    cmd = command(parts)
    if not cmd:
        return "Kontrollsenter har allerede tilgangen det trenger ✓"
    r = subprocess.run(["pkexec", *cmd], capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError("Tilgangen ble ikke gitt" + (" (avbrutt?)" if r.returncode in (126, 127) else ""))
    return "Tilgang gitt ✓ – " + ", ".join(NAMES[p] for p in cmd[3:])


def check():
    """Til Systemsjekk."""
    import syscheck as S
    parts = needed()
    if not parts:
        return [S.Result("Tilgang: alt er satt opp", "ok", "Kontrollsenter kan endre det det trenger uten å spørre.")]
    import shlex
    return [S.Result(f"Tilgang: {len(parts)} ting er ikke satt opp", "info",
                     "Med ett passord kan Kontrollsenter styre " + ", ".join(NAMES[p] for p in parts) + ".",
                     fix_label="Gi tilgang (ett passord)", root_cmds=[shlex.join(command(parts))])]
