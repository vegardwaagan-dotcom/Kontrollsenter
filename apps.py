"""Programmene funksjonene i Kontrollsenter trenger – det beste valget på Linux og Windows – og installasjon av dem.

Hver funksjon som trenger et program viser et «Installer»-felt når programmet mangler (se apps_ui.need).
Linux: Flathub (bruker-installasjon, trenger ikke passord). Windows: winget (Microsofts egen pakkebrønn).
Programmer som allerede er installert på en annen måte (systempakke, Bazzite, egen installer) blir funnet.
"""
import glob
import os
import shutil
import subprocess
import sys
import threading
import time

IS_WIN = sys.platform == "win32"
HOME = os.path.expanduser("~")

# nøkkel: navn, hva det brukes til, flatpak-id, winget-id, Linux-kommandoer, Windows-stier (glob, med %VAR%)
APPS = {
    "steam": dict(name="Steam", why="Spillene, Spill-launcheren, spilletid og spillprofiler",
                  flatpak="com.valvesoftware.Steam", winget="Valve.Steam", cmds=["steam"],
                  win=[r"%ProgramFiles(x86)%\Steam\steam.exe", r"%ProgramFiles%\Steam\steam.exe"]),
    "heroic": dict(name="Heroic", why="Epic Games- og GOG-spill i Spill-launcheren",
                   flatpak="com.heroicgameslauncher.hgl", winget="HeroicGamesLauncher.HeroicGamesLauncher",
                   cmds=["heroic"], win=[r"%LOCALAPPDATA%\Programs\heroic\Heroic.exe",
                                         r"%ProgramFiles%\Heroic\Heroic.exe"]),
    "lutris": dict(name="Lutris", why="Battle.net, EA, Ubisoft og andre spill på Linux",
                   flatpak="net.lutris.Lutris", cmds=["lutris"]),
    "battlenet": dict(name="Battle.net", why="Blizzard-spill (WoW, Overwatch, Diablo) på Windows",
                      winget="Blizzard.BattleNet",
                      win=[r"%ProgramFiles(x86)%\Battle.net\Battle.net Launcher.exe",
                           r"%ProgramFiles%\Battle.net\Battle.net Launcher.exe"]),
    "discord": dict(name="Discord", why="Discord-siden: mikrofon, lyd, overlay, servere og chat",
                    flatpak="com.discordapp.Discord", winget="Discord.Discord", cmds=["discord", "Discord"],
                    win=[r"%LOCALAPPDATA%\Discord\Update.exe"]),
    "openrgb": dict(name="OpenRGB", why="RGB-lys på hovedkort, minne, vifter og tastatur",
                    flatpak="org.openrgb.OpenRGB", winget="CalcProgrammer1.OpenRGB", cmds=["openrgb"],
                    win=[r"%ProgramFiles%\OpenRGB\OpenRGB.exe", r"%LOCALAPPDATA%\Programs\OpenRGB\OpenRGB.exe",
                         r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\*OpenRGB*\**\OpenRGB.exe"]),
    "solaar": dict(name="Solaar", why="Logitech-mus og -tastatur: batteri, DPI og knapper (Linux)",
                   flatpak="io.github.pwr_solaar.solaar", cmds=["solaar"]),
    "ghub": dict(name="Logitech G HUB", why="Logitech-mus, -tastatur og -hodesett (Windows)",
                 winget="Logitech.GHUB", win=[r"%ProgramFiles%\LGHUB\lghub.exe"]),
    "gsr": dict(name="GPU Screen Recorder", why="Klipp av de siste minuttene og høydepunkter (Linux)",
                flatpak="com.dec05eba.gpu_screen_recorder"),
    "ffmpeg": dict(name="FFmpeg", why="Redigere klipp: klippe til, GIF, montasje og «beste fra uka»",
                   winget="Gyan.FFmpeg", cmds=["ffmpeg"],
                   win=[r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\*FFmpeg*\**\ffmpeg.exe"], linux_system=True),
    "sunshine": dict(name="Sunshine", why="Spill PC-spillene på telefonen eller TV-en",
                     flatpak="dev.lizardbyte.app.Sunshine", winget="LizardByte.Sunshine", cmds=["sunshine"],
                     win=[r"%ProgramFiles%\Sunshine\sunshine.exe"]),
    "moonlight": dict(name="Moonlight", why="Spill fra en annen PC i huset på denne",
                      flatpak="com.moonlight_stream.Moonlight", winget="MoonlightGameStreamingProject.Moonlight",
                      cmds=["moonlight"], win=[r"%ProgramFiles%\Moonlight Game Streaming\Moonlight.exe"]),
    "rustdesk": dict(name="RustDesk", why="Fjernstyr PC-en fra telefonen eller en annen PC",
                     flatpak="com.rustdesk.RustDesk", winget="RustDesk.RustDesk", cmds=["rustdesk"],
                     win=[r"%ProgramFiles%\RustDesk\rustdesk.exe"]),
    "tailscale": dict(name="Tailscale", why="Bruk mobilappen når du ikke er hjemme",
                      winget="Tailscale.Tailscale", cmds=["tailscale"],
                      win=[r"%ProgramFiles%\Tailscale\tailscale.exe"], linux_system=True),
}

# hvilke programmer hver funksjon trenger (minst ett av dem i en gruppe holder)
FEATURES = {
    "launcher": [["steam", "heroic", "lutris", "battlenet"]],
    "games": [["steam"]],
    "discord": [["discord"]],
    "rgb": [["openrgb"]],
    "logitech": [["solaar", "ghub"]],
    "clips": [["gsr"]],
    "clipedit": [["ffmpeg"]],
    "stream": [["sunshine"]],
    "moonlight": [["moonlight"]],
    "remote": [["rustdesk"]],
    "away": [["tailscale"]],
}

_CACHE = {}
_FP = {"t": 0, "ids": set()}


def available(key):
    """Finnes programmet for dette operativsystemet i det hele tatt?"""
    a = APPS[key]
    if IS_WIN:
        return bool(a.get("winget") or a.get("win"))
    return bool(a.get("flatpak") or a.get("cmds"))


def _flatpaks():
    if time.time() - _FP["t"] > 20:
        try:
            out = subprocess.run(["flatpak", "list", "--app", "--columns=application"], capture_output=True,
                                 text=True, timeout=20).stdout
            _FP["ids"] = set(out.split())
        except (OSError, subprocess.SubprocessError):
            _FP["ids"] = set()
        _FP["t"] = time.time()
    return _FP["ids"]


def _win_found(a):
    for p in a.get("win") or []:
        if glob.glob(os.path.expandvars(p), recursive=True):
            return True
    for c in a.get("cmds") or []:
        if shutil.which(c):
            return True
    return False


def installed(key, max_age=20):
    """True hvis programmet er installert (uansett hvordan)."""
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < max_age:
        return hit[1]
    a = APPS[key]
    if IS_WIN:
        ok = _win_found(a)
    else:
        ok = bool(a.get("flatpak") and a["flatpak"] in _flatpaks()) or any(shutil.which(c) for c in a.get("cmds") or [])
        if not ok and key == "steam":
            ok = os.path.isdir(os.path.join(HOME, ".local/share/Steam/steamapps")) or \
                 os.path.isdir(os.path.join(HOME, ".steam/steam/steamapps"))
    _CACHE[key] = (time.time(), ok)
    return ok


def missing(feature):
    """Programmene som mangler for en funksjon: [[nøkkel, …], …] – én liste per gruppe der ingen er installert."""
    out = []
    for group in FEATURES.get(feature, []):
        group = [k for k in group if available(k)]
        if group and not any(installed(k) for k in group):
            out.append(group)
    return out


def can_install(key):
    a = APPS[key]
    if IS_WIN:
        return bool(a.get("winget")) and bool(shutil.which("winget"))
    return bool(a.get("flatpak")) and bool(shutil.which("flatpak"))


def manual_hint(key):
    a = APPS[key]
    if not IS_WIN and a.get("linux_system"):
        return f"{a['name']} installeres som systempakke – på Bazzite følger det med. Ellers: sudo dnf install {key}"
    return f"Installer {a['name']} fra produsentens nettside."


_LOCK = threading.Lock()


def install(key, progress=None):
    """Installer programmet (blokkerer – kall fra en tråd). Returnerer melding, kaster ved feil."""
    a = APPS[key]
    if not can_install(key):
        raise RuntimeError(manual_hint(key))
    with _LOCK:
        if progress:
            progress(f"Installerer {a['name']} … (kan ta noen minutter)")
        if IS_WIN:
            cmd = ["winget", "install", "-e", "--id", a["winget"], "--silent", "--accept-package-agreements",
                   "--accept-source-agreements", "--disable-interactivity"]
            kw = {"creationflags": 0x08000000}
        else:
            subprocess.run(["flatpak", "remote-add", "--user", "--if-not-exists", "flathub",
                            "https://dl.flathub.org/repo/flathub.flatpakrepo"], capture_output=True, timeout=60)
            cmd = ["flatpak", "install", "--user", "-y", "--noninteractive", "flathub", a["flatpak"]]
            kw = {}
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, **kw)
        out = (r.stdout or "") + (r.stderr or "")
        # winget: «allerede installert» (0x8A15002B) teller som ok
        if r.returncode != 0 and "already installed" not in out.lower() and "allerede installert" not in out.lower():
            raise RuntimeError(f"Installasjonen av {a['name']} feilet: " + out.strip()[-240:])
    _CACHE.pop(key, None)
    _FP["t"] = 0
    return f"{a['name']} er installert ✓"


def status():
    """Alle programmene for dette operativsystemet, til Innstillinger og mobilappen."""
    return [{"key": k, "name": a["name"], "why": a["why"], "installed": installed(k), "can_install": can_install(k)}
            for k, a in APPS.items() if available(k)]
