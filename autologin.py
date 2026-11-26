"""Engangs automatisk innlogging etter en omstart fra Kontrollsenter (PC-appen eller mobilen).

Når det er slått på: rett før omstarten skriver root-hjelperen (systemmonitor-autologin) en innloggingsregel for
innloggingsskjermen (Plasma Login, SDDM, LightDM eller GDM). Etter oppstarten blir du logget inn uten passord, og
regelen fjernes igjen – av en systemtjeneste etter ~45 sekunder og av Kontrollsenter når det starter. Neste vanlige
oppstart spør om passord som før. Bare Linux: Windows krever at passordet lagres i klartekst for å logge inn selv.
"""
import json
import os
import subprocess
import sys

IS_WIN = sys.platform == "win32"
HELPER = "/usr/local/bin/systemmonitor-autologin"
CFG = os.path.expanduser("~/.config/systemmonitor/autologin.json")
NAME = "zz-kontrollsenter-autologin.conf"
ARMED = ["/etc/plasmalogin.conf.d/" + NAME, "/etc/sddm.conf.d/" + NAME, "/etc/lightdm/lightdm.conf.d/" + NAME,
         "/etc/gdm/custom.conf.kontrollsenter-bak", "/etc/gdm3/custom.conf.kontrollsenter-bak",
         "/etc/gdm3/daemon.conf.kontrollsenter-bak"]


def supported():
    return not IS_WIN


def enabled():
    try:
        return bool(json.load(open(CFG, encoding="utf-8")).get("on"))
    except (OSError, ValueError):
        return False


def helper_ready():
    return os.path.exists(HELPER) and subprocess.run(["sudo", "-n", "-l", HELPER], capture_output=True,
                                                     timeout=10).returncode == 0


def set_enabled(on):
    """Slå valget på/av. Første gang: ett passord for å installere hjelperen (pkexec)."""
    if IS_WIN:
        raise RuntimeError("bare på Linux – Windows må lagre passordet i klartekst for å logge inn selv")
    if on and not helper_ready():
        import accesshub
        accesshub.setup_all(["autologin"])
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    with open(CFG, "w", encoding="utf-8") as f:
        json.dump({"on": bool(on)}, f)
    return ("Du logges inn automatisk etter omstart fra Kontrollsenter ✓" if on else
            "Passord ved innlogging som vanlig")


def arm():
    """Rett før omstart: slå på engangsinnloggingen (hvis valgt). Returnerer True hvis det ble gjort."""
    if IS_WIN or not enabled():
        return False
    try:
        r = subprocess.run(["sudo", "-n", HELPER, "once"], capture_output=True, text=True, timeout=20)
        if r.returncode != 0:
            import applog
            applog.log.warning("automatisk innlogging: %s", (r.stderr or r.stdout).strip())
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def armed():
    return any(os.path.exists(p) for p in ARMED)


def disarm():
    """Ved oppstart: fjern engangsinnloggingen hvis den fortsatt ligger der."""
    if IS_WIN or not armed():
        return False
    try:
        return subprocess.run(["sudo", "-n", HELPER, "off"], capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def status():
    """{"supported", "on", "ready", "dm"} – til appen og mobilen."""
    dm = None
    if not IS_WIN:
        try:
            dm = os.path.basename(os.path.realpath("/etc/systemd/system/display-manager.service")).replace(".service", "")
        except OSError:
            pass
    return {"supported": supported(), "on": enabled(), "ready": (not IS_WIN) and os.path.exists(HELPER), "dm": dm}
