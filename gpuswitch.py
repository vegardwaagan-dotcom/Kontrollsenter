"""Velg hovedskjermkort – integrert eller dedikert, eller blant flere skjermkort.

Linux (KDE Plasma): KWIN_DRM_DEVICES settes i ~/.config/plasma-workspace/env/ og gjelder fra neste innlogging.
  Skriptet sjekker ved innlogging at det valgte kortet har en skjerm koblet til – ellers brukes det vanlige
  (automatisk), så skjermen aldri blir svart.
Windows: de andre skjermkortene slås av (som i Enhetsbehandling). Én administratorgodkjenning. Bekrefter du ikke
  innen 20 sekunder at du ser bildet, slås alle kortene på igjen av seg selv.
"""
import glob
import json
import os
import re
import subprocess
import sys
import tempfile
import time

IS_WIN = sys.platform == "win32"
ENV_FILE = os.path.expanduser("~/.config/plasma-workspace/env/kontrollsenter-gpu.sh")
VENDORS = {"0x10de": "nvidia", "0x1002": "amd", "0x8086": "intel"}
IGPU_NAMES = re.compile(r"610M|Radeon\(TM\) Graphics|Radeon Graphics|Vega \d+ Graphics|Granite Ridge|Raphael|"
                        r"Renoir|Cezanne|Rembrandt|Phoenix|Hawk Point|Strix|Lucienne|Barcelo|UHD|Iris|HD Graphics",
                        re.I)


def _read(p, d=""):
    try:
        with open(p) as f:
            return f.read().strip()
    except OSError:
        return d


def _run(cmd, t=20):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=t,
                           **({"creationflags": 0x08000000} if IS_WIN else {}))
        return r.returncode, r.stdout + r.stderr
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


def supported():
    if IS_WIN:
        return True
    return "KDE" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper() and \
        os.environ.get("XDG_SESSION_TYPE") == "wayland"


# --------------------------------------------------------------------------
# Linux
# --------------------------------------------------------------------------
def _kwin_devices():
    """KWIN_DRM_DEVICES i den KWin som kjører nå (None = automatisk)."""
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        if _read(f"/proc/{pid}/comm") != "kwin_wayland":
            continue
        try:
            env = open(f"/proc/{pid}/environ", "rb").read().split(b"\0")
        except OSError:
            continue
        for e in env:
            if e.startswith(b"KWIN_DRM_DEVICES="):
                return e.split(b"=", 1)[1].decode() or None
        return None
    return None


def _linux_gpus():
    out = []
    used = _kwin_devices()
    used_cards = {os.path.basename(os.path.realpath(p)) for p in (used or "").split(":") if p}
    for c in sorted(glob.glob("/sys/class/drm/card[0-9]*")):
        card = os.path.basename(c)
        if not re.fullmatch(r"card\d+", card):
            continue
        dev = os.path.join(c, "device")
        vendor = VENDORS.get(_read(os.path.join(dev, "vendor")))
        if not vendor:
            continue
        bus = os.path.basename(os.path.realpath(dev))
        _c, txt = _run(["lspci", "-s", bus], 5)
        name = re.sub(r"^\S+\s+[^:]+:\s*", "", txt.strip().splitlines()[0]) if txt.strip() else card
        m = re.search(r"\[([^\]]*(?:GeForce|Radeon|Arc|Iris|UHD|Quadro|RTX)[^\]]*)\]", name)
        short = m.group(1) if m else name
        vram = int(_read(os.path.join(dev, "mem_info_vram_total"), "0") or 0)
        integrated = vendor == "intel" and bus.startswith("0000:00:") or \
            (vendor == "amd" and (0 < vram <= 2 * 1024 ** 3 or bool(IGPU_NAMES.search(name))))
        if vendor == "intel" and re.search(r"\bArc\b", name) and not bus.startswith("0000:00:"):
            integrated = False
        outs = []
        for o in sorted(glob.glob(f"/sys/class/drm/{card}-*")):
            st = _read(os.path.join(o, "status"))
            if st in ("connected", "disconnected") and "Writeback" not in o:
                outs.append({"name": os.path.basename(o)[len(card) + 1:], "connected": st == "connected"})
        out.append({"id": bus, "card": card, "name": short, "full": name, "vendor": vendor, "integrated": integrated,
                    "outputs": outs, "connected": any(x["connected"] for x in outs),
                    "boot": _read(os.path.join(dev, "boot_vga")) == "1",
                    "in_use": (card in used_cards) if used else None})
    return out


def _linux_choice():
    m = re.search(r"by-path/pci-([0-9a-f:.]+)-card", _read(ENV_FILE))
    return m.group(1) if m else None


def _linux_set(bus):
    if bus is None:
        try:
            os.remove(ENV_FILE)
        except FileNotFoundError:
            pass
        return
    if not re.fullmatch(r"[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]", bus):
        raise ValueError("ugyldig skjermkort")
    os.makedirs(os.path.dirname(ENV_FILE), exist_ok=True)
    with open(ENV_FILE, "w") as f:
        f.write(f"""#!/bin/sh
# Kontrollsenter: hovedskjermkort (GPU-innstillinger → Hovedskjermkort). Slett filen for automatisk valg.
# Brukes bare hvis kortet har en skjerm koblet til – ellers starter skrivebordet som vanlig (aldri svart skjerm).
dev=$(readlink -f /dev/dri/by-path/pci-{bus}-card 2>/dev/null)
if [ -n "$dev" ] && [ -e "$dev" ]; then
  card=$(basename "$dev")
  for s in /sys/class/drm/"$card"-*/status; do
    if [ "$(cat "$s" 2>/dev/null)" = "connected" ]; then
      export KWIN_DRM_DEVICES="$dev"
      break
    fi
  done
fi
""")
    os.chmod(ENV_FILE, 0o755)


def logout_prompt():
    for cmd in (["qdbus6", "org.kde.LogoutPrompt", "/LogoutPrompt", "promptLogout"],
                ["qdbus", "org.kde.LogoutPrompt", "/LogoutPrompt", "promptLogout"]):
        if _run(cmd, 10)[0] == 0:
            return True
    return False


# --------------------------------------------------------------------------
# Windows
# --------------------------------------------------------------------------
def _win_gpus():
    ps = ("Get-PnpDevice -Class Display | Where-Object { $_.InstanceId -like 'PCI*' } | "
          "Select-Object FriendlyName,InstanceId,Status | ConvertTo-Json -Compress")
    _c, txt = _run(["powershell", "-NoProfile", "-Command", ps], 40)
    try:
        rows = json.loads(txt.strip() or "[]")
    except ValueError:
        rows = []
    if isinstance(rows, dict):
        rows = [rows]
    out = []
    for r in rows:
        iid, name = r.get("InstanceId", ""), r.get("FriendlyName", "")
        m = re.search(r"VEN_([0-9A-F]{4})", iid, re.I)
        vendor = VENDORS.get("0x" + m.group(1).lower()) if m else None
        if not vendor:
            continue
        integrated = (vendor == "intel" and not re.search(r"\bArc\b", name)) or \
            (vendor == "amd" and bool(IGPU_NAMES.search(name)))
        on = str(r.get("Status", "")).upper() == "OK"
        out.append({"id": iid, "card": None, "name": name, "full": name, "vendor": vendor, "integrated": integrated,
                    "outputs": [], "connected": None, "boot": False, "in_use": on, "enabled": on})
    return out


OK_FLAG = os.path.join(tempfile.gettempdir(), "ks-gpu-ok.flag")


def _win_set(iid, all_gpus):
    """Slå på valgt kort (eller alle når iid er None) og av de andre, med automatisk angring etter 20 s."""
    ids = [g["id"] for g in all_gpus]
    if iid is not None and iid not in ids:
        raise ValueError("ugyldig skjermkort")
    enable = ids if iid is None else [iid]
    disable = [] if iid is None else [x for x in ids if x != iid]
    try:
        os.remove(OK_FLAG)
    except FileNotFoundError:
        pass

    def q(s):
        return "'" + s.replace("'", "''") + "'"
    script = "$ErrorActionPreference='Continue'\n"
    for x in enable:
        script += f"pnputil /enable-device {q(x)} | Out-Null\n"
    for x in disable:
        script += f"pnputil /disable-device {q(x)} | Out-Null\n"
    if disable:                                    # angre hvis ingen bekrefter at de ser bildet
        script += (f"$t=(Get-Date).AddSeconds(20); while((Get-Date) -lt $t) {{ if (Test-Path {q(OK_FLAG)}) "
                   f"{{ exit 0 }}; Start-Sleep -Milliseconds 500 }}\n")
        for x in disable:
            script += f"pnputil /enable-device {q(x)} | Out-Null\n"
    f = os.path.join(tempfile.gettempdir(), "ks-gpu-switch.ps1")
    with open(f, "w", encoding="utf-8-sig") as fh:
        fh.write(script)
    launcher = (f"Start-Process powershell -Verb RunAs -WindowStyle Hidden -ArgumentList "
                f"'-NoProfile','-ExecutionPolicy','Bypass','-File',{q(f)}")
    code, out = _run(["powershell", "-NoProfile", "-Command", launcher], 30)
    if code != 0:
        raise RuntimeError("Fikk ikke administratortilgang" if "cancel" in out.lower() or "avbr" in out.lower()
                           else out.strip()[-200:] or "byttet feilet")
    return bool(disable)


def confirm_ok():
    """Windows: brukeren ser bildet – behold byttet."""
    with open(OK_FLAG, "w") as f:
        f.write(str(time.time()))


# --------------------------------------------------------------------------
# Felles
# --------------------------------------------------------------------------
def gpus():
    return _win_gpus() if IS_WIN else _linux_gpus()


def choice(all_gpus=None):
    """Valgt hovedskjermkort (id) eller None = automatisk."""
    if IS_WIN:
        g = all_gpus if all_gpus is not None else gpus()
        on = [x for x in g if x.get("enabled")]
        return on[0]["id"] if len(on) == 1 and len(g) > 1 else None
    return _linux_choice()


def set_choice(gid, all_gpus=None):
    """Returnerer True hvis byttet må bekreftes (Windows) – ellers gjelder det fra neste innlogging (Linux)."""
    if not supported():
        raise RuntimeError("bytte av skjermkort støttes bare på KDE Plasma (Wayland) og Windows")
    if IS_WIN:
        return _win_set(gid, all_gpus if all_gpus is not None else gpus())
    _linux_set(gid)
    return False


def kind(g):
    return "Integrert" if g["integrated"] else "Dedikert"
