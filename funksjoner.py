"""Hvilke funksjoner Kontrollsenter har på: Fullstendig, Medium, Minimal eller Egendefinert.

Velges i velkomstveiviseren første gang programmet starter (og i Windows-installasjonen), og kan endres under
Innstillinger. En funksjon som er av, er helt av: siden vises ikke i menyen og lastes aldri, og arbeidet den gjør i
bakgrunnen (tidsstyrte scener, Smart Hjem-automatikk, RGB ved oppstart, chat-varsler …) stopper.

Lagres i ~/.config/systemmonitor/funksjonsvalg.json: {"profile": "full|medium|minimal|custom", "off": [nøkler]}.
Uten fila er alt på (slik det alltid har vært).
"""
import json
import os
import sys

CFG = os.path.expanduser("~/.config/systemmonitor/funksjonsvalg.json")
_REAL_CFG = CFG                                      # tester bytter CFG – da stoppes aldri ekte tjenester
# autostart Kontrollsenter selv har laget for en funksjon (fjernes og stoppes når funksjonen slås av)
AUTOSTART_OF = {"utstyr": ["openrgb", "solaar"], "cpuskjerm": ["trcc"]}
# valget i Windows-installasjonen (veiviseren starter med det, og lagrer så i CFG)
SETUP = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Kontrollsenter", "funksjonsvalg.json") \
    if os.environ.get("LOCALAPPDATA") else ""

# (nøkkel, navn, forklaring, sider i menyen, alltid på)
FEATURES = [
    ("oversikt", "Oversikt", "Temperaturer, last og strøm", ["oversikt"], True),
    ("historikk", "Historikk", "Grafer over tid", ["historikk"], True),
    ("oppdateringer", "Oppdateringer", "Nye versjoner av Kontrollsenter og «Oppdater alt» for appene – alltid med",
     [], True),
    ("gpu", "GPU-innstillinger", "Strømgrense, klokke og vifter for skjermkortet", ["gpu"], False),
    ("utstyr", "Utstyr: RGB, Logitech og MSI", "Lys, mus/tastatur og bærbar-innstillinger", ["rgb", "logitech", "msi"],
     False),
    ("cpuskjerm", "CPU-skjerm (TRCC)", "Skjermen på CPU-kjøleren (Thermalright)", ["cpuskjerm"], False),
    ("lyd", "Lyd", "Lydenheter, volum og profiler", ["lyd"], False),
    ("spill", "Spill", "Spill, spilltid, spillmodus og Spill+", ["spill"], False),
    ("vr", "VR", "VR-briller og VR-vakten", ["vr"], False),
    ("stromming", "Strømming", "Strømming til TV og andre PC-er", ["stromming"], False),
    ("chat", "Chat", "Chat, servere, talekanaler og webkamera", ["chat"], False),
    ("discord", "Discord", "Styr Discord fra Kontrollsenter", ["discord"], False),
    ("pcer", "PC-er", "PC-ene hjemme og venner utenfor huset", ["hjemme", "venner"], False),
    ("fjernhjelp", "Fjernhjelp", "RustDesk – hjelp andre og få hjelp", ["fjernhjelp"], False),
    ("scener", "Scener", "Én knapp som gjør mange ting, også på tid", ["scener"], False),
    ("smarthjem", "Smart Hjem", "Lys, stikkontakter og Hue", ["smarthjem"], False),
    ("familie", "Familie", "Ukeplan, skjermtid og leggetid", ["familie"], False),
    ("kalender", "Kalender og dagbok", "Røde dager, hendelser for hele huset og egen dagbok med kode", ["kalender"],
     False),
    ("ai", "AI: Claude, Codex, Gemini og lokal AI", "Spør og styr PC-en med AI – også uten nett (Ollama)", ["ai"],
     False),
    ("nettverk", "Nett og tilkobling", "Nettverk, Wi-Fi og Bluetooth", ["nettverk", "wifi", "bluetooth"], False),
    ("programmer", "Programmer", "Installer og oppdater programmer", ["programmer"], False),
    ("verktoy", "Vedlikehold", "Opprydding, oppstart, sikkerhetskopi og verktøy", ["verktoy"], False),
    ("innstillinger", "Innstillinger", "Skjult kan den fortsatt åpnes fra ☰-menyen", ["innstillinger"], False),
]
KEYS = [f[0] for f in FEATURES]
REQUIRED = {f[0] for f in FEATURES if f[4]}
PAGE_FEATURE = {p: f[0] for f in FEATURES for p in f[3]}

MINIMAL = {"oversikt", "historikk", "oppdateringer", "gpu", "lyd", "spill", "chat", "pcer", "fjernhjelp", "nettverk",
           "programmer", "verktoy", "innstillinger"}
PROFILES = {
    "full": ("Fullstendig", "Alle funksjoner", set(KEYS)),
    "medium": ("Medium", "Alt unntatt Discord, Scener, Smart Hjem og CPU-skjerm (TRCC)",
               set(KEYS) - {"discord", "scener", "smarthjem", "cpuskjerm"}),
    "minimal": ("Minimal", "Oversikt, Historikk, GPU, Lyd, Spill, Chat, PC-er, Fjernhjelp og alt under System",
                set(MINIMAL)),
    "custom": ("Egendefinert", "Velg selv hvilke funksjoner du vil ha", None),
}
_C = {"v": None, "mt": None}


def cfg():
    path = CFG
    if SETUP and os.path.exists(SETUP):                  # ny installasjon med nytt valg: det vinner
        try:
            if not os.path.exists(CFG) or os.path.getmtime(SETUP) > os.path.getmtime(CFG):
                path = SETUP
        except OSError:
            pass
    try:
        mt = (path, os.path.getmtime(path))
    except OSError:
        mt = None
    if _C["v"] is None or mt != _C["mt"]:
        try:
            with open(path, encoding="utf-8-sig") as f:
                d = json.load(f)
        except (OSError, ValueError):
            d = {}
        if path == SETUP and isinstance(d.get("on"), list):          # installasjonen lister det som er PÅ
            d = {"profile": d.get("profile", "custom"), "off": [k for k in KEYS if k not in d["on"]]}
        prof = d.get("profile") if d.get("profile") in PROFILES else "full"
        if prof == "custom":
            off = {k for k in d.get("off") or [] if k in KEYS} - REQUIRED
        else:
            off = set(KEYS) - PROFILES[prof][2]
        _C.update(v={"profile": prof, "off": off, "chosen": bool(d)}, mt=mt)
    return _C["v"]


def chosen():
    """Har brukeren valgt (veiviseren/installasjonen)? Ellers er alt på."""
    return cfg()["chosen"]


def on(key):
    """Er funksjonen på? Ukjente nøkler er alltid på."""
    return key not in cfg()["off"]


def page_on(page):
    return on(PAGE_FEATURE.get(page, ""))


def enabled():
    return [k for k in KEYS if on(k)]


def save(profile, keys=None):
    """profile: full|medium|minimal|custom; keys = funksjonene som skal være på (bare for custom)."""
    if profile not in PROFILES:
        raise ValueError("ukjent profil")
    if profile == "custom":
        want = (set(KEYS if keys is None else keys) | REQUIRED) & set(KEYS)
        for prof, (_n, _d, ks) in PROFILES.items():           # samme som en fast profil: bruk den
            if ks is not None and ks == want:
                profile = prof
                break
    else:
        want = PROFILES[profile][2]
    before = set(enabled())
    d = {"profile": profile, "off": sorted(set(KEYS) - want)}
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    tmp = CFG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)
    os.replace(tmp, CFG)
    _C["v"] = None
    _stop_disabled(before - set(enabled()))
    return cfg()


def init_new_install():
    """Første gang Kontrollsenter starter på en PC: bare det som alltid er med er på – resten velges i
    velkomstveiviseren (eller senere under ☰ → Funksjoner). PC-er som allerede bruker Kontrollsenter berøres ikke."""
    if os.path.exists(CFG) or (SETUP and os.path.exists(SETUP)):
        return False
    save("custom", sorted(REQUIRED))
    return True


def set_feature(key, on):
    """Slå én funksjon av/på (f.eks. AI-menyen under Innstillinger) – resten beholdes som før."""
    keys = set(enabled())
    (keys.add if on else keys.discard)(key)
    return save("custom", sorted(keys))


def _undo_autostart(key):
    """Fjern Kontrollsenter sin autostart for et program, stopp den, og gi tilbake brukerens egen (fra .bak)."""
    import glob
    import shutil
    import subprocess
    import autostart
    own = autostart.own_file(key)
    if os.path.exists(own):
        unit = os.path.basename(own)[:-len(".desktop")]
        try:
            esc = subprocess.run(["systemd-escape", unit], capture_output=True, text=True, timeout=5).stdout.strip()
            subprocess.run(["systemctl", "--user", "stop", f"app-{esc}@autostart.service"], capture_output=True,
                           timeout=15)
        except (OSError, subprocess.SubprocessError):
            pass
        os.remove(own)
    app = next((a for a in autostart.apps() if a[0] == key), None)
    if app:                                            # brukerens egne oppføringer som Kontrollsenter skjulte
        for bak in glob.glob(os.path.join(autostart.AUTOSTART, "*.desktop.bak")):
            orig = bak[:-4]
            try:
                txt = open(bak, errors="replace").read()
            except OSError:
                continue
            exec_rx, name_rx = app[5], app[6]
            import re
            if (exec_rx and re.search(exec_rx, txt)) or (name_rx and re.search(name_rx, txt)):
                shutil.move(bak, orig)


def _stop_disabled(newly_off=()):
    """Slå av det funksjonene som nettopp ble slått av gjør i bakgrunnen – og det Kontrollsenter satte opp for
    dem (tjenester og autostart). Programmer avinstalleres av komponenter.py (bare de Kontrollsenter installerte)."""
    if CFG != _REAL_CFG or os.environ.get("KS_KOMP_TEST") or os.environ.get("KS_CHAT_TEST"):
        return
    newly_off = set(newly_off)
    if "chat" in newly_off:
        try:
            import chatvc
            if chatvc.current():
                chatvc.leave()
            chatvc.ov_sync()
        except Exception:  # noqa: BLE001
            pass
    if "ai" in newly_off:                                   # tale til tekst er installert av Kontrollsenter: fjern
        try:
            import aitale
            if aitale.stt_ready():
                aitale.uninstall_stt()
        except Exception:  # noqa: BLE001
            pass
    if "lyd" in newly_off:                                  # lydfiltrene (7.1, EQ, støyfilter): stopp og fjern
        try:
            import lydfilter
            for k in ("surround", "eq", "noise"):
                if lydfilter.cfg().get(k):
                    lydfilter.enable(k, False)
            lydfilter.uninstall()
        except Exception:  # noqa: BLE001
            pass
    if sys.platform == "win32":
        return
    for feat in newly_off:
        for key in AUTOSTART_OF.get(feat, []):
            try:
                _undo_autostart(key)
            except Exception:  # noqa: BLE001
                pass
