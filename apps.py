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

# nøkkel: navn, hvorfor (kort), flatpak-id, winget-id, Linux-kommandoer, Windows-stier (glob, %VAR%),
# url (nettside når det ikke finnes en sikker pakke), builtin (følger med systemet), ks (styres fra Kontrollsenter)
W = r"%LOCALAPPDATA%"
PF = r"%ProgramFiles%"
PF86 = r"%ProgramFiles(x86)%"
APPS = {
    # ---- spill ----
    "steam": dict(name="Steam", why="Største spillbutikken, Proton for Windows-spill, Remote Play og opptak",
                  flatpak="com.valvesoftware.Steam", winget="Valve.Steam", cmds=["steam"],
                  win=[PF86 + r"\Steam\steam.exe", PF + r"\Steam\steam.exe"], ks=True),
    "heroic": dict(name="Heroic", why="Epic Games, GOG og Amazon Prime Gaming i ett lett program",
                   flatpak="com.heroicgameslauncher.hgl", winget="HeroicGamesLauncher.HeroicGamesLauncher",
                   cmds=["heroic"], win=[W + r"\Programs\heroic\Heroic.exe"], ks=True),
    "lutris": dict(name="Lutris", why="Battle.net, EA, Ubisoft og emulatorer samlet på Linux",
                   flatpak="net.lutris.Lutris", cmds=["lutris"], ks=True),
    "bottles": dict(name="Bottles", why="Kjør enkeltstående Windows-spill og -programmer på Linux",
                    flatpak="com.usebottles.bottles"),
    "alvr": dict(name="ALVR", why="Meta Quest trådløst eller med kabel gjennom SteamVR (Linux og Windows)",
                 url="https://github.com/alvr-org/ALVR/releases/latest", ks=True,
                 cmds=["alvr_dashboard"], win=[W + r"\Kontrollsenter\alvr\*\ALVR Dashboard.exe"]),
    "metalink": dict(name="Meta Horizon Link", why="Meta Quest med kabel (Quest Link) på Windows",
                     url="https://www.meta.com/help/quest/1517439565442928/", ks=True,
                     win=[PF + r"\Oculus\Support\oculus-runtime\OVRServer_x64.exe"]),
    "virtualdesktop": dict(name="Virtual Desktop", why="Den beste trådløse løsningen (betalt, kjøpes i Quest-butikken)",
                           url="https://www.vrdesktop.net/", win=[PF + r"\Virtual Desktop Streamer\VirtualDesktop.Streamer.exe"]),
    "wivrn": dict(name="WiVRn", why="Trådløs VR for Linux med OpenXR (uten SteamVR)", flatpak="io.github.wivrn.wivrn"),
    "retroarch": dict(name="RetroArch", why="Alle de gamle konsollene i én emulator",
                      flatpak="org.libretro.RetroArch", winget="Libretro.RetroArch"),
    "epic": dict(name="Epic Games", why="Gratis spill hver uke og Fortnite",
                 winget="EpicGames.EpicGamesLauncher",
                 win=[PF86 + r"\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe"]),
    "battlenet": dict(name="Battle.net", why="Blizzard-spill: WoW, Overwatch, Diablo, Call of Duty",
                      winget="Blizzard.BattleNet", ks=True,
                      win=[PF86 + r"\Battle.net\Battle.net Launcher.exe", PF + r"\Battle.net\Battle.net Launcher.exe"]),
    "eaapp": dict(name="EA app", why="EA-spill: FC, Battlefield, The Sims",
                  winget="ElectronicArts.EADesktop", win=[PF + r"\Electronic Arts\EA Desktop\EA Desktop\EADesktop.exe"]),
    "gog": dict(name="GOG Galaxy", why="DRM-frie spill og samlet bibliotek",
                winget="GOG.Galaxy", win=[PF86 + r"\GOG Galaxy\GalaxyClient.exe"]),
    # ---- tale og chat ----
    "discord": dict(name="Discord", why="Der vennene er – tale, chat og strømming",
                    flatpak="com.discordapp.Discord", winget="Discord.Discord", cmds=["discord", "Discord"],
                    win=[W + r"\Discord\Update.exe"], ks=True),
    "vesktop": dict(name="Vesktop", why="Discord med bedre skjermdeling og lyd på Linux",
                    flatpak="dev.vencord.Vesktop", winget="Vencord.Vesktop", cmds=["vesktop"],
                    win=[W + r"\Programs\Vesktop\Vesktop.exe"]),
    "teamspeak": dict(name="TeamSpeak", why="Lav forsinkelse og god lyd for klaner og egne servere",
                      flatpak="com.teamspeak.TeamSpeak", winget="TeamSpeakSystems.TeamSpeakClient",
                      win=[PF + r"\TeamSpeak\TeamSpeak.exe", W + r"\Programs\TeamSpeak\TeamSpeak.exe"]),
    "mumble": dict(name="Mumble", why="Åpen kildekode, svært lav forsinkelse, posisjonslyd i spill",
                   flatpak="info.mumble.Mumble", winget="Mumble.Mumble.Client", cmds=["mumble"],
                   win=[PF + r"\Mumble\client\mumble.exe"]),
    "element": dict(name="Element", why="Kryptert chat og samtaler (Matrix)",
                    flatpak="im.riot.Riot", winget="Element.Element", win=[W + r"\element-desktop\Element.exe"]),
    # ---- RGB ----
    "openrgb": dict(name="OpenRGB", why="Styrer nesten alle merker samtidig – hovedkort, minne, vifter, tastatur",
                    flatpak="org.openrgb.OpenRGB", winget="CalcProgrammer1.OpenRGB", cmds=["openrgb"], ks=True,
                    win=[PF + r"\OpenRGB\OpenRGB.exe", W + r"\Programs\OpenRGB\OpenRGB.exe",
                         W + r"\Microsoft\WinGet\Packages\*OpenRGB*\**\OpenRGB.exe"]),
    "signalrgb": dict(name="SignalRGB", why="Flotte effekter som følger spillet og skjermen (Windows)",
                      winget="WhirlwindFX.SignalRgb", win=[W + r"\VortxEngine\SignalRgbLauncher.exe"]),
    "icue": dict(name="Corsair iCUE", why="Alt fra Corsair: lys, vifter og pumper",
                 winget="Corsair.iCUE.5", win=[PF + r"\Corsair\Corsair iCUE5 Software\iCUE.exe"]),
    "polychromatic": dict(name="Polychromatic", why="Razer-utstyr på Linux (lys og DPI)",
                          flatpak="app.polychromatic.controller"),
    "ckbnext": dict(name="ckb-next", why="Corsair-tastatur og -mus på Linux", cmds=["ckb-next"],
                    url="https://github.com/ckb-next/ckb-next"),
    "armoury": dict(name="Armoury Crate", why="ASUS-hovedkort og -skjermkort (Aura Sync)",
                    url="https://www.asus.com/supportonly/armoury%20crate/helpdesk_download/",
                    win=[PF + r"\ASUS\ARMOURY CRATE Service\ArmouryCrate.Service.exe"]),
    # ---- mus og tastatur ----
    "solaar": dict(name="Solaar", why="Logitech: batteri, DPI, knapper og lys (Linux)",
                   flatpak="io.github.pwr_solaar.solaar", cmds=["solaar"], ks=True),
    "piper": dict(name="Piper", why="Gaming-mus fra Logitech, SteelSeries, Roccat m.fl.: DPI, knapper, profiler",
                  flatpak="org.freedesktop.Piper", cmds=["piper"]),
    "inputremapper": dict(name="Input Remapper", why="Endre hva hver knapp og tast gjør – også makroer",
                          cmds=["input-remapper-gtk"], url="https://github.com/sezanzeb/input-remapper"),
    "ghub": dict(name="Logitech G HUB", why="Alt for Logitech G: DPI, makroer, lys og hodesett",
                 winget="Logitech.GHUB", win=[PF + r"\LGHUB\lghub.exe"], ks=True),
    "optionsplus": dict(name="Logi Options+", why="Logitech MX- og kontormus og -tastatur",
                        winget="Logitech.OptionsPlus", win=[PF + r"\LogiOptionsPlus\logioptionsplus.exe"]),
    "steelseries": dict(name="SteelSeries GG", why="SteelSeries-mus, -tastatur og -hodesett (Sonar-lyd)",
                        winget="SteelSeries.GG", win=[PF + r"\SteelSeries\GG\SteelSeriesGG.exe"]),
    "synapse": dict(name="Razer Synapse", why="Alt Razer-utstyr", url="https://www.razer.com/synapse-4"),
    # ---- klipp og opptak ----
    "gsr": dict(name="GPU Screen Recorder", why="Klipp med skjermkortet nesten uten FPS-tap – som ShadowPlay",
                flatpak="com.dec05eba.gpu_screen_recorder", ks=True),
    "obs": dict(name="OBS Studio", why="Opptak og strømming til Twitch/YouTube med full kontroll",
                flatpak="com.obsproject.Studio", winget="OBSProject.OBSStudio", cmds=["obs"],
                win=[PF + r"\obs-studio\bin\64bit\obs64.exe"]),
    "steamrec": dict(name="Steam spillopptak", why="Innebygd i Steam: tar opp i bakgrunnen, enkelt å dele",
                     builtin="steam"),
    "kooha": dict(name="Kooha", why="Enkelt skjermopptak med ett klikk", flatpak="io.github.seadve.Kooha"),
    "spectacle": dict(name="Spectacle", why="KDE sitt skjermbilde- og opptaksverktøy", flatpak="org.kde.spectacle",
                      cmds=["spectacle"]),
    "medal": dict(name="Medal", why="Klipp med F8, automatisk høydepunkt og enkel deling",
                  winget="MedalB.V.Medal", ks=True,
                  win=[W + r"\Medal\Medal.exe", W + r"\Medal\app-*\Medal.exe"]),
    "nvidiaapp": dict(name="NVIDIA App (ShadowPlay)", why="NVIDIA sitt eget opptak – minst FPS-tap på GeForce",
                      url="https://www.nvidia.com/en-us/software/nvidia-app/",
                      win=[PF + r"\NVIDIA Corporation\NVIDIA App\CEF\NVIDIA App.exe"]),
    "gamebar": dict(name="Xbox Game Bar", why="Følger med Windows – virker uten å installere noe", builtin="windows",
                    ks=True),
    "outplayed": dict(name="Outplayed", why="Automatiske høydepunkter i LoL, Valorant, Fortnite m.fl.",
                      url="https://www.outplayed.tv/"),
    # ---- redigere klipp ----
    "ffmpeg": dict(name="FFmpeg", why="Motoren bak klipp-redigeringen i Kontrollsenter (GIF, montasje …)",
                   winget="Gyan.FFmpeg", cmds=["ffmpeg"], ks=True,
                   win=[W + r"\Microsoft\WinGet\Packages\*FFmpeg*\**\ffmpeg.exe"], linux_system=True),
    "losslesscut": dict(name="LosslessCut", why="Klipp til videoer på sekunder uten kvalitetstap",
                        flatpak="no.mifi.losslesscut", winget="mifi.losslesscut"),
    "kdenlive": dict(name="Kdenlive", why="Full videoredigering: tekst, overganger, musikk",
                     flatpak="org.kde.kdenlive", winget="KDE.Kdenlive", cmds=["kdenlive"]),
    "shotcut": dict(name="Shotcut", why="Enkel, men kraftig videoredigering",
                    flatpak="org.shotcut.Shotcut", winget="Meltytech.Shotcut"),
    "davinci": dict(name="DaVinci Resolve", why="Profesjonell redigering og fargekorrigering (gratis)",
                    url="https://www.blackmagicdesign.com/products/davinciresolve"),
    "clipchamp": dict(name="Clipchamp", why="Følger med Windows 11 – maler, tekst og musikk", builtin="windows"),
    # ---- strømming av spill ----
    "sunshine": dict(name="Sunshine", why="Spill PC-spillene på telefonen eller TV-en med lav forsinkelse",
                     flatpak="dev.lizardbyte.app.Sunshine", winget="LizardByte.Sunshine", cmds=["sunshine"], ks=True,
                     win=[PF + r"\Sunshine\sunshine.exe"]),
    "moonlight": dict(name="Moonlight", why="Spill fra en annen PC i huset på denne (mot Sunshine)",
                      flatpak="com.moonlight_stream.Moonlight", winget="MoonlightGameStreamingProject.Moonlight",
                      cmds=["moonlight"], ks=True, win=[PF + r"\Moonlight Game Streaming\Moonlight.exe"]),
    "steamlink": dict(name="Steam Remote Play", why="Innebygd i Steam – Steam Link-appen på TV og mobil",
                      builtin="steam"),
    "parsec": dict(name="Parsec", why="Spill sammen over nettet som om dere satt i samme rom",
                   flatpak="com.parsecgaming.parsec", winget="Parsec.Parsec", win=[PF + r"\Parsec\parsecd.exe"]),
    "chiaki": dict(name="chiaki-ng", why="Spill PlayStation 4/5 på PC-en",
                   flatpak="io.github.streetpea.Chiaki4deck", url="https://streetpea.github.io/chiaki-ng/"),
    # ---- fjernstyring ----
    "rustdesk": dict(name="RustDesk", why="Gratis, åpen og rask – fungerer fra mobilen også", ks=True,
                     flatpak="com.rustdesk.RustDesk", winget="RustDesk.RustDesk", cmds=["rustdesk"],
                     win=[PF + r"\RustDesk\rustdesk.exe"]),
    "anydesk": dict(name="AnyDesk", why="Rask og enkel fjernhjelp", flatpak="com.anydesk.Anydesk",
                    winget="AnyDesk.AnyDesk", win=[PF86 + r"\AnyDesk\AnyDesk.exe", PF + r"\AnyDesk\AnyDesk.exe"]),
    "teamviewer": dict(name="TeamViewer", why="Mest brukt til fjernhjelp, gratis privat",
                       winget="TeamViewer.TeamViewer", url="https://www.teamviewer.com/download/",
                       win=[PF + r"\TeamViewer\TeamViewer.exe"], cmds=["teamviewer"]),
    "chromerd": dict(name="Chrome Remote Desktop", why="Fjernstyring rett fra nettleseren",
                     url="https://remotedesktop.google.com/"),
    "remmina": dict(name="Remmina", why="Koble til Windows (RDP) og andre PC-er fra Linux",
                    flatpak="org.remmina.Remmina", cmds=["remmina"]),
    # ---- utenfor huset (VPN) ----
    "tailscale": dict(name="Tailscale", why="Mobilappen virker også borte – null oppsett, gratis privat",
                      winget="Tailscale.Tailscale", cmds=["tailscale"], ks=True,
                      win=[PF + r"\Tailscale\tailscale.exe"], linux_system=True),
    "zerotier": dict(name="ZeroTier", why="Eget virtuelt nettverk mellom alle enhetene",
                     winget="ZeroTier.ZeroTierOne", cmds=["zerotier-cli"], url="https://www.zerotier.com/download/"),
    "wireguard": dict(name="WireGuard", why="Raskeste VPN – krever litt oppsett på ruteren",
                      winget="WireGuard.WireGuard", cmds=["wg"], linux_system=True),
    "netbird": dict(name="NetBird", why="Som Tailscale, men kan driftes selv", url="https://netbird.io/download"),
    "kdeconnect": dict(name="KDE Connect", why="Telefon og PC sammen: varsler, filer, mediekontroll",
                       cmds=["kdeconnect-app"], winget="KDE.KDEConnect", url="https://kdeconnect.kde.org/download.html"),
}

# Topp 5 per funksjon – rangert fra 1 (best) til 5, eget for Linux og Windows
TOP5 = {
    "launcher": dict(title="Spillbutikker og launchere",
                     linux=["steam", "heroic", "lutris", "bottles", "retroarch"],
                     win=["steam", "heroic", "epic", "battlenet", "eaapp"]),
    "discord": dict(title="Tale og chat",
                    linux=["discord", "vesktop", "teamspeak", "mumble", "element"],
                    win=["discord", "teamspeak", "vesktop", "mumble", "element"]),
    "rgb": dict(title="RGB-lys",
                linux=["openrgb", "polychromatic", "solaar", "ckbnext", "piper"],
                win=["openrgb", "signalrgb", "icue", "armoury", "ghub"]),
    "logitech": dict(title="Mus og tastatur",
                     linux=["solaar", "piper", "inputremapper", "openrgb", "polychromatic"],
                     win=["ghub", "optionsplus", "steelseries", "synapse", "openrgb"]),
    "clips": dict(title="Klipp og opptak",
                  linux=["gsr", "obs", "steamrec", "kooha", "spectacle"],
                  win=["medal", "nvidiaapp", "obs", "steamrec", "gamebar"]),
    "clipedit": dict(title="Redigere klipp",
                     linux=["ffmpeg", "losslesscut", "kdenlive", "shotcut", "davinci"],
                     win=["ffmpeg", "losslesscut", "clipchamp", "kdenlive", "davinci"]),
    "stream": dict(title="Spill på TV og mobil",
                   linux=["sunshine", "moonlight", "steamlink", "parsec", "chiaki"],
                   win=["sunshine", "moonlight", "steamlink", "parsec", "chiaki"]),
    "remote": dict(title="Fjernstyring",
                   linux=["rustdesk", "anydesk", "remmina", "teamviewer", "chromerd"],
                   win=["rustdesk", "anydesk", "parsec", "teamviewer", "chromerd"]),
    "away": dict(title="Bruk appen borte (VPN)",
                 linux=["tailscale", "zerotier", "wireguard", "netbird", "kdeconnect"],
                 win=["tailscale", "zerotier", "wireguard", "netbird", "kdeconnect"]),
}
TOP5["vr"] = dict(title="VR med Meta Quest", linux=["alvr", "wivrn", "steam"],
                  win=["metalink", "alvr", "virtualdesktop", "steam"])
TOP5["medal"] = dict(title="Klipp på Windows", linux=[], win=["medal"])
TOP5["moonlight"] = dict(title="Spill fra en annen PC", linux=["moonlight", "parsec", "steamlink"],
                         win=["moonlight", "parsec", "steamlink"])


def top5(feature):
    """De rangerte programmene for funksjonen på dette operativsystemet."""
    t = TOP5.get(feature) or {}
    return [k for k in t.get("win" if IS_WIN else "linux", []) if k in APPS and available(k)]


def _feature_groups(feature):
    """Programmene Kontrollsenter styrer for funksjonen (minst ett må finnes) – de andre er frittstående valg."""
    ks = [k for k in top5(feature) if APPS[k].get("ks")]
    return [ks] if ks else []


FEATURES = {f: None for f in TOP5}

_CACHE = {}
_FP = {"t": 0, "ids": set()}


def available(key):
    """Finnes programmet for dette operativsystemet i det hele tatt?"""
    a = APPS[key]
    b = a.get("builtin")
    if b == "windows":
        return IS_WIN
    if b == "steam":
        return True
    if IS_WIN:
        return bool(a.get("winget") or a.get("win") or (a.get("url") and not a.get("flatpak") and not a.get("cmds")))
    return bool(a.get("flatpak") or a.get("cmds") or (a.get("url") and not a.get("win") and not a.get("winget")))


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
    if key == "alvr":                                  # Kontrollsenter legger ALVR i sin egen mappe
        try:
            import vr
            if vr.alvr_dashboard():
                return True
        except Exception:  # noqa: BLE001
            pass
    if a.get("builtin") == "windows":
        _CACHE[key] = (time.time(), True)
        return True
    if a.get("builtin") == "steam":
        return installed("steam", max_age)
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
    for group in _feature_groups(feature):
        group = [k for k in group if available(k)]
        if group and not any(installed(k) for k in group):
            out.append(group)
    return out


def can_install(key):
    a = APPS[key]
    if a.get("builtin"):
        return False
    if IS_WIN:
        return bool(a.get("winget")) and bool(shutil.which("winget"))
    return bool(a.get("flatpak")) and bool(shutil.which("flatpak"))


def manual_hint(key):
    a = APPS[key]
    if a.get("builtin") == "windows":
        return f"{a['name']} følger med Windows."
    if a.get("builtin") == "steam":
        return f"{a['name']} er en del av Steam – installer Steam."
    if a.get("url"):
        return f"Last ned {a['name']} fra nettsiden."
    if not IS_WIN and a.get("linux_system"):
        return f"{a['name']} installeres som systempakke – på Bazzite følger det med. Ellers: sudo dnf install {key}"
    return f"Installer {a['name']} fra produsentens nettside."


_LOCK = threading.Lock()


def install(key, progress=None):
    """Installer programmet (blokkerer – kall fra en tråd). Returnerer melding, kaster ved feil."""
    a = APPS[key]
    if not can_install(key):
        raise RuntimeError(manual_hint(key))
    import progress as P
    with _LOCK, P.task(f"Installerer {a['name']}", "Gjør klar …", f"{a['name']} er installert") as pt:
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
        kw.pop("creationflags", None)
        code, out = P.run_cmd(cmd, pt, 1800)
        # winget: «allerede installert» (0x8A15002B) teller som ok
        if code != 0 and "already installed" not in out.lower() and "allerede installert" not in out.lower():
            raise RuntimeError(f"Installasjonen av {a['name']} feilet: " + out.strip()[-240:])
    _CACHE.pop(key, None)
    _FP["t"] = 0
    return f"{a['name']} er installert ✓"


def info(k):
    a = APPS[k]
    return {"key": k, "name": a["name"], "why": a["why"], "installed": installed(k), "can_install": can_install(k),
            "url": a.get("url"), "ks": bool(a.get("ks")), "builtin": a.get("builtin")}


def status():
    """Topp 5 per funksjon for dette operativsystemet, til Innstillinger og mobilappen."""
    out = []
    for f, t in TOP5.items():
        if f in ("medal", "moonlight"):
            continue
        keys = top5(f)
        if keys:
            out.append({"feature": f, "title": t["title"], "apps": [{**info(k), "rank": i + 1} for i, k in enumerate(keys)]})
    return out


def open_url(key):
    url = APPS[key].get("url")
    if not url:
        return False
    try:
        from gi.repository import Gio
        Gio.AppInfo.launch_default_for_uri(url, None)
        return True
    except Exception:  # noqa: BLE001
        import webbrowser
        return webbrowser.open(url)


# --------------------------------------------------------------------------
# Hvilket program brukes til hver funksjon (valgt der funksjonen er)
# --------------------------------------------------------------------------
USE_CFG = os.path.join(HOME, ".config", "systemmonitor", "programvalg.json")
MULTI = {"launcher"}              # funksjoner der alle brukes samtidig – valget er et filter («Alle» = None)


def _use_all():
    try:
        import json
        with open(USE_CFG, encoding="utf-8") as f:
            return json.load(f).get("use", {})
    except (OSError, ValueError):
        return {}


def choices(feature):
    """Installerte programmer for funksjonen, i rangert rekkefølge."""
    return [k for k in top5(feature) if installed(k)]


def get_use(feature):
    """Programmet som brukes til funksjonen: ditt valg hvis det er installert, ellers det beste installerte
    som Kontrollsenter styrer, ellers det beste installerte. None = ingen (eller «Alle» for MULTI)."""
    pick = _use_all().get(feature)
    if feature in MULTI:
        return pick if pick and installed(pick) else None
    ch = choices(feature)
    if pick in ch:
        return pick
    return next((k for k in ch if APPS[k].get("ks")), ch[0] if ch else None)


def set_use(feature, key):
    import json
    if key is not None and key not in APPS:
        raise ValueError("ukjent program")
    d = {}
    try:
        with open(USE_CFG, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        pass
    d.setdefault("use", {})[feature] = key
    os.makedirs(os.path.dirname(USE_CFG), exist_ok=True)
    with open(USE_CFG, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)
    for fn in list(_LISTENERS):
        try:
            fn(feature, key)
        except Exception:  # noqa: BLE001
            pass


_LISTENERS = []



def launch(key, *args):
    """Start programmet (med f.eks. en fil som argument)."""
    a = APPS[key]
    if a.get("builtin") == "steam":
        key, a = "steam", APPS["steam"]
    if a.get("builtin") == "windows":
        uri = {"gamebar": "ms-gamebar:", "clipchamp": "ms-clipchamp:"}.get(key)
        if uri:
            os.startfile(uri)  # noqa: S606
            return True
        return False
    if IS_WIN:
        for p in a.get("win") or []:
            hits = sorted(glob.glob(os.path.expandvars(p), recursive=True))
            if hits:
                exe = hits[-1]
                if exe.lower().endswith("update.exe"):           # Squirrel-programmer (Discord)
                    subprocess.Popen([exe, "--processStart", os.path.basename(os.path.dirname(exe)) + ".exe",
                                      *(["--process-start-args", " ".join(args)] if args else [])],
                                     creationflags=0x08000000)
                else:
                    subprocess.Popen([exe, *args], creationflags=0x08000000)
                return True
        for c in a.get("cmds") or []:
            if shutil.which(c):
                subprocess.Popen([shutil.which(c), *args], creationflags=0x08000000)
                return True
        return False
    for c in a.get("cmds") or []:
        if shutil.which(c):
            subprocess.Popen([c, *args], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
    if a.get("flatpak") and a["flatpak"] in _flatpaks():
        subprocess.Popen(["flatpak", "run", a["flatpak"], *args], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    return False


# Windows: tasten som lagrer et klipp i hvert klippeprogram (kan endres under Klipp)
CLIP_KEYS = {"medal": "F8", "nvidiaapp": "Alt+F10", "obs": "", "steamrec": "", "gamebar": "Meta+Alt+G"}
