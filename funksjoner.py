"""Hvilke funksjoner Kontrollsenter har på: Fullstendig, Medium, Minimal eller Egendefinert.

Velges i velkomstveiviseren første gang programmet starter (og i Windows-installasjonen), og kan endres under
Innstillinger. En funksjon som er av, er helt av: siden vises ikke i menyen og lastes aldri, og arbeidet den gjør i
bakgrunnen (tidsstyrte scener, Smart Hjem-automatikk, RGB ved oppstart, chat-varsler …) stopper.

Lagres i ~/.config/systemmonitor/funksjonsvalg.json: {"profile": "full|medium|minimal|custom", "off": [nøkler]}.
Uten fila er alt på (slik det alltid har vært).
"""
import json
import os

CFG = os.path.expanduser("~/.config/systemmonitor/funksjonsvalg.json")
# valget i Windows-installasjonen (veiviseren starter med det, og lagrer så i CFG)
SETUP = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Kontrollsenter", "funksjonsvalg.json") \
    if os.environ.get("LOCALAPPDATA") else ""

# (nøkkel, navn, forklaring, sider i menyen, alltid på)
FEATURES = [
    ("oversikt", "Oversikt", "Temperaturer, last og strøm", ["oversikt"], True),
    ("historikk", "Historikk", "Grafer over tid", ["historikk"], False),
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
    ("ai", "AI: Claude Code, Codex og Gemini", "Kodeassistenter i terminalen og «Spør» i appen", ["ai"], False),
    ("nettverk", "Nett og tilkobling", "Nettverk, Wi-Fi og Bluetooth", ["nettverk", "wifi", "bluetooth"], False),
    ("programmer", "Programmer", "Installer og oppdater programmer", ["programmer"], False),
    ("verktoy", "Vedlikehold", "Opprydding, oppstart, sikkerhetskopi og verktøy", ["verktoy"], False),
    ("innstillinger", "Innstillinger", "", ["innstillinger"], True),
]
KEYS = [f[0] for f in FEATURES]
REQUIRED = {f[0] for f in FEATURES if f[4]}
PAGE_FEATURE = {p: f[0] for f in FEATURES for p in f[3]}

MINIMAL = {"oversikt", "historikk", "gpu", "lyd", "spill", "chat", "pcer", "fjernhjelp", "nettverk", "programmer",
           "verktoy", "innstillinger"}
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
        want = (set(keys or KEYS) | REQUIRED) & set(KEYS)
        for prof, (_n, _d, ks) in PROFILES.items():           # samme som en fast profil: bruk den
            if ks is not None and ks == want:
                profile = prof
                break
    else:
        want = PROFILES[profile][2]
    d = {"profile": profile, "off": sorted(set(KEYS) - want)}
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    tmp = CFG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)
    os.replace(tmp, CFG)
    _C["v"] = None
    _stop_disabled()
    return cfg()


def set_feature(key, on):
    """Slå én funksjon av/på (f.eks. AI-menyen under Innstillinger) – resten beholdes som før."""
    keys = set(enabled())
    (keys.add if on else keys.discard)(key)
    return save("custom", sorted(keys))


def _stop_disabled():
    """Slå av det som går i bakgrunnen for funksjoner som nettopp ble slått av."""
    if not on("chat"):
        try:
            import chatvc
            chatvc.leave() if chatvc.current() else None
        except Exception:  # noqa: BLE001
            pass
