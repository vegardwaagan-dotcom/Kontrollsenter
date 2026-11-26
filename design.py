"""Design-bryteren: «Klassisk» (slik Kontrollsenter har sett ut) eller «Nytt» – ryddigere meny og roligere utseende.

Alt i det nye designet bygger på ÉN liste med designverdier (TOKENS): hjørner, avstander, tekststørrelser og
statusfarger. Fra dem lages stilarket til PC-programmet (Linux og Windows) og design.css til mobilappen, så alle tre
ser like ut. Klassisk er urørt: det nye designet er et eget lag som bare legges på når det er valgt.

Det nye designet:
  * sidemenyen har 7 områder (Oversikt, Spill, Enheter, Hjemmet, Sosialt, AI, System) med faner øverst
  * «Finn alt» er et søkefelt øverst i menyen
  * én ikonstil: emoji fjernes fra overskrifter, kategorier og faner (beholdes i Familie og Chat)
  * hvert kort har høyst én fremhevet knapp; kort for feilsøking/avansert er lukket til du åpner dem
  * hjelpeteksten øverst på en side vises bare første gang
  * 8 utvalgte temaer først (resten under «Flere temaer»), og glass/overganger er av til du slår dem på
  * én skrift, tall med fast bredde; på Windows Segoe UI Variable, mindre hjørner og vindusknapper som i Windows
"""
import json
import os
import re
import sys

IS_WIN = sys.platform == "win32"
CFG = os.path.expanduser("~/.config/systemmonitor/design.json")

MODES = ("klassisk", "ny", "3d", "lett")
# «3d» og «lett» bygger på det nye designet (menyen, fanene og ryddingen) og legger sin egen stil oppå:
#   3d   – dybde overalt: kort og knapper som løfter seg ut av skjermen, 3D-animasjoner når sider og kort kommer inn
#   lett – flatt og enkelt som LXQt: ingen animasjoner, skygger eller glass, og tegning uten skjermkortet (minst minne)
SKINS = ("3d", "lett")

# ---------------------------------------------------------------------------------------------------------------
# Designverdiene – den eneste kilden til hjørner, avstander, tekst og statusfarger i det nye designet
# ---------------------------------------------------------------------------------------------------------------
TOKENS = {
    "radius": {"sm": 8, "md": 14, "lg": 22},
    "space": [4, 8, 12, 16, 24],
    "text": {"small": 0.86, "body": 1.0, "title": 1.35, "big": 1.75},      # em
    "weight": {"normal": 400, "strong": 600, "title": 700},
    "status": {"ok": "#3ccf7e", "warn": "#f5b23c", "bad": "#ff5a5f"},
    "font": '"Inter", "Adwaita Sans", "Noto Sans", system-ui, sans-serif',
}
# Windows 11 har mindre hjørner og egen skrift
TOKENS_WIN = dict(TOKENS, radius={"sm": 6, "md": 10, "lg": 16},
                  font='"Segoe UI Variable Text", "Segoe UI Variable", "Segoe UI", sans-serif')


def tokens():
    return TOKENS_WIN if IS_WIN else TOKENS


# 7 områder i sidemenyen: (nøkkel, tittel, ikon, sidene – den første som finnes er «lederen»)
AREAS = [
    ("oversikt", "Oversikt", "ks-overview-symbolic", ["oversikt", "historikk"]),
    ("spill", "Spill", "ks-games-symbolic", ["spill", "vr", "stromming"]),
    ("enheter", "Enheter", "ks-gpu-symbolic", ["gpu", "lyd", "rgb", "logitech", "cpuskjerm", "msi", "tester"]),
    ("hjemmet", "Hjemmet", "ks-smarthome-symbolic", ["smarthjem", "scener", "familie", "kalender"]),
    ("sosialt", "Sosialt", "ks-chat-symbolic", ["chat", "discord", "hjemme", "venner", "fjernhjelp"]),
    ("ai", "AI", "ks-ai-symbolic", ["ai"]),
    ("system", "System", "ks-settings-symbolic", ["innstillinger", "verktoy", "programmer", "nettverk", "wifi",
                                                   "bluetooth"]),
]
# mobilappens faner nederst får de samme navnene og den samme rekkefølgen som de 7 områdene på PC-en
MOBILE_TABS = {"oversikt": "Oversikt", "spill": "Spill", "kontroll": "Enheter", "mer": "Hjemmet", "chat": "Sosialt",
               "ai": "AI", "system": "System"}

# temaene som vises først i det nye designet (resten under «Flere temaer»)
CURATED = ["standard", "oled", "papir", "nord", "catppuccin", "nordlys", "krom", "synthwave"]

# sider der emoji er en del av innholdet og får stå
KEEP_EMOJI = {"familie", "chat"}

# kort som lukkes (åpnes med «Vis») – overskriften starter med et av disse
ADVANCED = ("Avansert", "Ekspert", "For eksperter", "Feilsøking", "Feillogg", "Utvikler")


# ---------------------------------------------------------------------------------------------------------------
# Valget
# ---------------------------------------------------------------------------------------------------------------
def _load():
    try:
        with open(CFG, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(d):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    tmp = CFG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f)
    os.replace(tmp, CFG)


_MODE = []


def mode():
    """«klassisk» eller «ny». Leses én gang per kjøring – byttet tas i bruk ved omstart."""
    if not _MODE:
        m = os.environ.get("KS_DESIGN") or _load().get("mode", "klassisk")
        _MODE.append(m if m in MODES else "klassisk")
    return _MODE[0]


def is_new():
    """Bruker menyen/fanene fra det nye designet (Nytt, 3D og Lett)."""
    return mode() in ("ny", "3d", "lett")


def skin():
    """«3d», «lett» eller None."""
    return mode() if mode() in SKINS else None


def saved_mode():
    m = _load().get("mode", "klassisk")
    return m if m in MODES else "klassisk"


def set_mode(m):
    """Lagre valget. Fra Klassisk til et av de nye: glass og overganger huskes og settes tilbake når du går tilbake.
    Nytt: rolig (glass og overganger av). 3D: overganger på. Lett: alt tungt av, og «spar minne» på."""
    if m not in MODES:
        return
    d = _load()
    old = d.get("mode", "klassisk")
    if old == m:
        return
    d["mode"] = m
    try:
        import effects
        import perf
        import theme
        if old == "klassisk" and not isinstance(d.get("prev"), dict):
            d["prev"] = {"glass": theme.glass_on(), "transition": effects.transition()}
        if old == "lett" and m != "lett":
            perf.set_save_all(False)
        if m == "ny":
            theme._save_look(glass=False)
            effects.set_transition("av")
        elif m == "3d":
            theme._save_look(glass=False)
            effects.set_transition("glid")
        elif m == "lett":
            theme._save_look(glass=False)
            effects.set_transition("av")
            perf.set_save_all(True)
        elif isinstance(d.get("prev"), dict):
            p = d.pop("prev")
            theme._save_look(glass=bool(p.get("glass", True)))
            effects.set_transition(p.get("transition", "glid"))
    except Exception:  # noqa: BLE001 – valget skal lagres uansett
        pass
    _save(d)


def help_seen(page):
    """Har hjelpeteksten øverst på denne siden vært vist før? (Markerer den som sett.)"""
    d = _load()
    seen = d.get("help_seen", [])
    if not isinstance(seen, list):                 # ødelagt/eldre fil: begynn på nytt
        seen = list(seen) if isinstance(seen, (dict, tuple, set)) else []
    if page in seen:
        return True
    if os.environ.get("KS_SELFTEST"):          # selvtesten skal ikke «se» hjelpetekstene for deg
        return False
    seen.append(page)
    d["help_seen"] = seen
    try:
        _save(d)
    except OSError:
        pass
    return False


# ---------------------------------------------------------------------------------------------------------------
# Emoji
# ---------------------------------------------------------------------------------------------------------------
_EMOJI = "[\U0001F000-\U0001FAFF☀-➿⬀-⯿⌀-⏿️‍⃣]"
_LEAD = re.compile(r"^\s*(?:" + _EMOJI + r"+\s*)+")


def strip_emoji(text):
    """Fjern emoji foran en tittel: «🎮  Spill» -> «Spill». Emoji inne i teksten får stå."""
    if not text:
        return text
    out = _LEAD.sub("", text)
    return out if out.strip() else text


# ---------------------------------------------------------------------------------------------------------------
# Stilark – PC (GTK)
# ---------------------------------------------------------------------------------------------------------------
def gtk_css():
    t = tokens()
    r, tx, w, st = t["radius"], t["text"], t["weight"], t["status"]
    return f"""
/* Nytt design – lages av design.py fra designverdiene. Fargene følger temaet (theme.recolor). */
window.ks-ny {{ font-family: {t["font"]}; }}
window.ks-ny .title-1, window.ks-ny .ks-hello {{ font-size: {tx["big"]}em; font-weight: {w["title"]}; letter-spacing: -0.01em; }}
window.ks-ny .title-2 {{ font-size: {tx["title"]}em; font-weight: {w["strong"]}; }}
window.ks-ny .title-3, window.ks-ny .title-4 {{ font-size: 1.12em; font-weight: {w["strong"]}; }}
window.ks-ny .heading, window.ks-ny .caption-heading {{ font-weight: {w["strong"]}; }}
window.ks-ny .caption {{ font-size: {tx["small"]}em; }}
window.ks-ny .numeric, window.ks-ny .ks-tile-value, window.ks-ny .ks-big, window.ks-ny .ks-pulse-value {{
  font-feature-settings: "tnum"; }}
window.ks-ny .ks-brand-title {{ font-weight: {w["title"]}; }}

/* hjørner: tre størrelser i hele programmet */
window.ks-ny .card, window.ks-ny list.boxed-list, window.ks-ny .ks-tile, window.ks-ny .tile,
window.ks-ny .ks-vtile, window.ks-ny .ks-goal, window.ks-ny popover > contents {{ border-radius: {r["md"]}px; }}
window.ks-ny button:not(.pill):not(.circular):not(.ks-swatch), window.ks-ny entry, window.ks-ny spinbutton,
window.ks-ny dropdown > button, window.ks-ny .ks-chip, window.ks-ny .ks-scene-chip {{ border-radius: {r["sm"]}px; }}
window.ks-ny dialog > .dialog-contents, window.ks-ny .ks-catbar, window.ks-ny togglebutton.ks-swatch {{
  border-radius: {r["lg"]}px; }}

/* statusfarger */
window.ks-ny .success {{ color: {st["ok"]}; }}
window.ks-ny .warning {{ color: {st["warn"]}; }}
window.ks-ny .error {{ color: {st["bad"]}; }}

/* sidemenyen: 7 områder, ingen seksjonsoverskrifter, søkefelt øverst */
window.ks-ny .navigation-sidebar.ks-sidebar > row {{ border-radius: {r["sm"]}px; min-height: 44px; margin: 2px 0; }}
window.ks-ny .navigation-sidebar.ks-sidebar > row label.ks-row-title {{ font-weight: 500; }}
window.ks-ny .navigation-sidebar.ks-sidebar > row:selected label.ks-row-title {{ font-weight: {w["strong"]}; }}
window.ks-ny entry.ks-side-search {{ margin: 2px 12px 8px 12px; min-height: 36px; }}

/* faner øverst (områdene, kategoriene og fanesidene) – samme utseende overalt */
window.ks-ny .ks-ntabs {{ padding: 2px 2px 6px 2px; }}
window.ks-ny .ks-ntabs > button.toggle:not(.pill):not(.circular),
window.ks-ny stackswitcher.ks-tabs > button.toggle:not(.pill):not(.circular) {{
  border-radius: 999px; padding: 4px 14px; min-height: 32px; min-width: 0; margin: 0 3px; font-weight: 500;
  background-image: none; background-color: alpha(currentColor, 0.05); color: inherit; box-shadow: none; }}
window.ks-ny .ks-ntabs > button.toggle:not(.pill):not(.circular):hover,
window.ks-ny stackswitcher.ks-tabs > button.toggle:not(.pill):not(.circular):hover {{
  background-color: alpha(currentColor, 0.09); }}
window.ks-ny .ks-ntabs > button.toggle:not(.pill):not(.circular):checked,
window.ks-ny stackswitcher.ks-tabs > button.toggle:not(.pill):not(.circular):checked {{
  background-image: none; background-color: alpha(#5b8cff, 0.18); color: #5b8cff; font-weight: {w["strong"]};
  box-shadow: inset 0 0 0 1px alpha(#5b8cff, 0.45); }}
window.ks-ny .ks-ntabs > button image {{ -gtk-icon-size: 16px; }}
window.ks-ny .ks-catbar.ks-catbar-new {{ background: none; border: none; padding: 0; margin: 2px 0 6px 0; }}

/* hjelpetekst og lukkede kort */
window.ks-ny .ks-pagehelp {{ font-size: {tx["small"]}em; opacity: 0.7; }}
window.ks-ny button.ks-adv-toggle {{ padding: 2px 10px; min-height: 28px; font-size: {tx["small"]}em; }}
"""


def gtk_css_3d():
    """3D: lys ovenfra, kanter med dybde, knapper som løfter seg ut mot deg og trykkes inn, kort som flyr inn.
    Fargene følger temaet (libadwaita-fargene). Bare 2D-transformer: GTK tegner ikke perspective()/rotateX() (blir
    rosa felt) – dybden lages med skygger, kanter og løft. Mobilappen har ekte 3D (CSS i nettleseren)."""
    return """
/* ---------- 3D ---------- */
@keyframes ks3d-in { 0% { opacity: 0; transform: translateY(30px) scale(0.92); }
                     70% { opacity: 1; transform: translateY(-4px) scale(1.012); }
                     100% { opacity: 1; transform: none; } }
@keyframes ks3d-pop { 0% { transform: scale(1); } 45% { transform: scale(1.09) translateY(-3px); }
                      100% { transform: scale(1.04) translateY(-2px); } }
@keyframes ks3d-glow { from { box-shadow: 0 0 0 0 alpha(@accent_bg_color, 0.55); }
                       to { box-shadow: 0 0 0 9px alpha(@accent_bg_color, 0); } }
window.ks-3d .card, window.ks-3d list.boxed-list, window.ks-3d .ks-tile, window.ks-3d .tile {
  background-image: linear-gradient(180deg, alpha(white, 0.075), alpha(white, 0.0) 42%, alpha(black, 0.10));
  border: 1px solid alpha(white, 0.10); border-bottom-color: alpha(black, 0.35);
  box-shadow: 0 1px 0 alpha(white, 0.10) inset, 0 -2px 0 alpha(black, 0.18) inset,
              0 2px 3px alpha(black, 0.22), 0 10px 22px alpha(black, 0.28), 0 22px 40px -12px alpha(black, 0.45);
  animation: ks3d-in 520ms cubic-bezier(0.2, 0.9, 0.25, 1.15) both;
  transition: transform 240ms cubic-bezier(0.2, 0.9, 0.3, 1.3), box-shadow 240ms ease; }
window.ks-3d .card:hover, window.ks-3d .ks-tile:hover, window.ks-3d .tile:hover {
  transform: translateY(-7px) scale(1.018);
  box-shadow: 0 1px 0 alpha(white, 0.14) inset, 0 -2px 0 alpha(black, 0.18) inset,
              0 4px 6px alpha(black, 0.22), 0 22px 40px alpha(black, 0.38), 0 40px 70px -14px alpha(black, 0.55),
              0 0 0 1px alpha(@accent_bg_color, 0.35), 0 0 26px alpha(@accent_bg_color, 0.18); }
/* knapper: tykk kant under (som en ekte knapp), løfter seg mot deg og trykkes inn */
window.ks-3d button:not(.flat):not(.circular):not(.ks-swatch):not(.toggle),
window.ks-3d dropdown > button, window.ks-3d menubutton > button:not(.flat), window.ks-3d togglebutton:not(.flat) {
  background-image: linear-gradient(180deg, alpha(white, 0.16), alpha(white, 0.02) 55%, alpha(black, 0.10));
  border: 1px solid alpha(black, 0.30); border-top-color: alpha(white, 0.22);
  box-shadow: 0 1px 0 alpha(white, 0.32) inset, 0 -1px 0 alpha(black, 0.25) inset, 0 5px 0 alpha(black, 0.42),
              0 8px 16px alpha(black, 0.34);
  transition: transform 160ms cubic-bezier(0.2, 0.9, 0.3, 1.5), box-shadow 160ms ease; margin-bottom: 5px; }
window.ks-3d button:not(.flat):not(.circular):not(.ks-swatch):not(.toggle):hover,
window.ks-3d dropdown > button:hover, window.ks-3d togglebutton:not(.flat):hover {
  transform: translateY(-4px) scale(1.06);
  box-shadow: 0 1px 0 alpha(white, 0.38) inset, 0 9px 0 alpha(black, 0.36), 0 18px 28px alpha(black, 0.42),
              0 0 18px alpha(@accent_bg_color, 0.35); }
window.ks-3d button:not(.flat):not(.circular):not(.ks-swatch):not(.toggle):active,
window.ks-3d dropdown > button:active, window.ks-3d togglebutton:not(.flat):active, window.ks-3d togglebutton:checked {
  transform: translateY(3px) scale(0.985);
  box-shadow: 0 2px 4px alpha(black, 0.45) inset, 0 1px 0 alpha(black, 0.30); }
window.ks-3d button.suggested-action:not(.flat), window.ks-3d button.destructive-action:not(.flat) {
  animation: ks3d-glow 1.8s ease-out infinite; }
window.ks-3d button.suggested-action:not(.flat):hover { animation: ks3d-pop 260ms ease-out both; }
window.ks-3d button.flat:hover, window.ks-3d button.circular:hover { transform: scale(1.12); transition: transform 140ms ease; }
/* brytere og glidere med volum */
window.ks-3d switch { box-shadow: 0 2px 4px alpha(black, 0.5) inset; }
window.ks-3d switch > slider { background-image: radial-gradient(circle at 35% 30%, white, alpha(white, 0.75) 55%, #c8c8d0);
  box-shadow: 0 2px 5px alpha(black, 0.5), 0 1px 0 white inset; }
window.ks-3d scale > trough { box-shadow: 0 2px 3px alpha(black, 0.45) inset; }
window.ks-3d scale > trough > slider { background-image: radial-gradient(circle at 35% 30%, white, #c8c8d0);
  box-shadow: 0 3px 6px alpha(black, 0.5); }
window.ks-3d entry, window.ks-3d spinbutton { box-shadow: 0 2px 4px alpha(black, 0.35) inset; }
/* sidemenyen: valgt rad løftes ut, de andre vipper litt mot deg */
window.ks-3d .navigation-sidebar > row { transition: transform 200ms cubic-bezier(0.2, 0.9, 0.3, 1.4), box-shadow 200ms; }
window.ks-3d .navigation-sidebar > row:hover { transform: translateX(4px) scale(1.02); }
window.ks-3d .navigation-sidebar > row:selected {
  background-image: linear-gradient(180deg, alpha(@accent_bg_color, 0.55), alpha(@accent_bg_color, 0.28));
  box-shadow: 0 1px 0 alpha(white, 0.25) inset, 0 6px 14px alpha(black, 0.4); transform: translateX(6px) scale(1.03); }
/* fanene øverst som fysiske knapper */
window.ks-3d .ks-ntabs > button.toggle:not(.pill):not(.circular),
window.ks-3d stackswitcher > button.toggle {
  box-shadow: 0 1px 0 alpha(white, 0.18) inset, 0 3px 0 alpha(black, 0.3), 0 5px 10px alpha(black, 0.25);
  transition: transform 160ms cubic-bezier(0.2, 0.9, 0.3, 1.5); }
window.ks-3d .ks-ntabs > button.toggle:hover, window.ks-3d stackswitcher > button.toggle:hover { transform: translateY(-2px) scale(1.04); }
window.ks-3d .ks-ntabs > button.toggle:checked, window.ks-3d stackswitcher > button.toggle:checked {
  transform: translateY(2px); box-shadow: 0 2px 5px alpha(black, 0.45) inset; }
/* overskrifter og store tall med dybde */
window.ks-3d .title-1, window.ks-3d .title-2, window.ks-3d .ks-hello, window.ks-3d .ks-tile-value, window.ks-3d .ks-big {
  text-shadow: 0 1px 0 alpha(white, 0.18), 0 2px 0 alpha(black, 0.35), 0 4px 8px alpha(black, 0.45); }
window.ks-3d image { -gtk-icon-shadow: 0 2px 3px alpha(black, 0.45); }
window.ks-3d popover > contents, window.ks-3d dialog > .dialog-contents {
  box-shadow: 0 30px 60px alpha(black, 0.55), 0 0 0 1px alpha(white, 0.08) inset;
  animation: ks3d-in 300ms cubic-bezier(0.2, 0.9, 0.25, 1.15) both; }
"""


def gtk_css_lett():
    """Lett (som LXQt): flatt, kompakt og raskt – ingen animasjoner, skygger, gradienter eller glass."""
    return """
/* ---------- Lett ---------- */
window.ks-lett, window.ks-lett * { transition: none; animation: none; text-shadow: none; -gtk-icon-shadow: none; }
window.ks-lett .card, window.ks-lett list.boxed-list, window.ks-lett .ks-tile, window.ks-lett .tile,
window.ks-lett popover > contents, window.ks-lett dialog > .dialog-contents {
  border-radius: 3px; box-shadow: none; background-image: none; border: 1px solid alpha(currentColor, 0.16); }
window.ks-lett button, window.ks-lett entry, window.ks-lett spinbutton, window.ks-lett dropdown > button,
window.ks-lett .ks-ntabs > button.toggle:not(.pill):not(.circular), window.ks-lett stackswitcher > button.toggle {
  border-radius: 2px; box-shadow: none; background-image: none; min-height: 26px; padding-top: 2px; padding-bottom: 2px; }
window.ks-lett button:not(.flat) { border: 1px solid alpha(currentColor, 0.22); }
window.ks-lett .navigation-sidebar > row { border-radius: 0; min-height: 30px; margin: 0; }
window.ks-lett .navigation-sidebar > row:selected { box-shadow: inset 3px 0 0 @accent_bg_color; }
window.ks-lett .title-1, window.ks-lett .ks-hello { font-size: 1.3em; }
window.ks-lett .title-2 { font-size: 1.12em; }
window.ks-lett .card { padding: 0; }
window.ks-lett, window.ks-lett .ks-main, window.ks-lett .navigation-sidebar { background-image: none; }
window.ks-lett .tile-spark, window.ks-lett .ks-sparkline { opacity: 0; min-height: 0; }
window.ks-lett switch { border-radius: 3px; } window.ks-lett switch > slider { border-radius: 2px; box-shadow: none; }
"""


# ---------------------------------------------------------------------------------------------------------------
# Stilark – mobilappen (remote_web og startskjermen i APK-en)
# ---------------------------------------------------------------------------------------------------------------
def web_css():
    t = TOKENS
    r, tx, w, st = t["radius"], t["text"], t["weight"], t["status"]
    s = t["space"]
    return f"""/* Nytt design – laget av design.py (ikke rediger for hånd). Gjelder bare når html har data-design="ny". */
:root[data-design="ny"] {{
  --r: {r["md"]}px; --r-sm: {r["sm"]}px; --r-md: {r["md"]}px; --r-lg: {r["lg"]}px; --gap: {s[2]}px;
  --ok: {st["ok"]}; --warn: {st["warn"]}; --bad: {st["bad"]};
}}
:root[data-design="ny"] body {{ font-family: {t["font"]}; font-variant-numeric: tabular-nums; }}
:root[data-design="ny"] h1 {{ font-weight: {w["title"]}; letter-spacing: -0.01em; }}
:root[data-design="ny"] h2, :root[data-design="ny"] h3 {{ font-weight: {w["strong"]}; }}
:root[data-design="ny"] .card {{ border-radius: var(--r-md); }}
:root[data-design="ny"] button:not(.icon):not(.theme-sw):not(.link), :root[data-design="ny"] input,
:root[data-design="ny"] select {{ border-radius: var(--r-sm); }}
:root[data-design="ny"] .chips button, :root[data-design="ny"] .seg button {{ border-radius: 999px; }}
:root[data-design="ny"] .dim.small, :root[data-design="ny"] small {{ font-size: {tx["small"]}em; }}
:root[data-design="ny"] .tabs button {{ border-radius: var(--r-md); }}
:root[data-design="ny"] .tabs button.on {{ background: color-mix(in srgb, var(--acc, #5b8cff) 18%, transparent);
  color: var(--acc, #5b8cff); }}
:root[data-design="ny"] .tabs button span {{ font-weight: 500; }}
:root[data-design="ny"] .tabs button.on span {{ font-weight: {w["strong"]}; }}
:root[data-design="ny"] .ks-adv > :not(h2):not(.ks-adv-btn) {{ display: none; }}
:root[data-design="ny"] .ks-adv.open > :not(h2):not(.ks-adv-btn) {{ display: revert; }}
:root[data-design="ny"] .ks-adv-btn {{ min-height: 34px; padding: 6px 14px; font-size: {tx["small"]}em; }}
:root[data-design="ny"] .ks-more-themes {{ margin-top: {s[2]}px; grid-column: 1 / -1; }}
:root[data-design="ny"] .ks-more-themes > summary {{ cursor: pointer; font-weight: {w["strong"]}; padding: {s[1]}px 0;
  color: var(--acc, #5b8cff); }}
/* ---------- 3D (mobil) ---------- */
@keyframes ks3d-in {{ from {{ opacity: 0; transform: perspective(900px) translateY(28px) rotateX(-16deg) scale(.96); }}
  to {{ opacity: 1; transform: perspective(900px) none; }} }}
@keyframes ks3d-glow {{ from {{ box-shadow: 0 0 0 0 color-mix(in srgb, var(--acc, #5b8cff) 55%, transparent); }}
  to {{ box-shadow: 0 0 0 10px transparent; }} }}
:root[data-skin="3d"] main {{ perspective: 1100px; }}
:root[data-skin="3d"] .card {{ transform-style: preserve-3d;
  background-image: linear-gradient(180deg, rgba(255,255,255,.08), rgba(255,255,255,0) 42%, rgba(0,0,0,.10));
  border: 1px solid rgba(255,255,255,.10); border-bottom-color: rgba(0,0,0,.35);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.12), inset 0 -2px 0 rgba(0,0,0,.18), 0 2px 3px rgba(0,0,0,.22),
    0 12px 24px rgba(0,0,0,.30), 0 26px 44px -14px rgba(0,0,0,.5);
  animation: ks3d-in .55s cubic-bezier(.2,.9,.25,1.15) both;
  transition: transform .25s cubic-bezier(.2,.9,.3,1.3), box-shadow .25s; }}
:root[data-skin="3d"] .card.ks3d-tilt {{ transition: transform .08s linear; }}
:root[data-skin="3d"] .card h2 {{ transform: translateZ(18px); text-shadow: 0 2px 0 rgba(0,0,0,.35), 0 6px 12px rgba(0,0,0,.4); }}
:root[data-skin="3d"] button:not(.icon):not(.link):not(.theme-sw):not(.on) {{
  background-image: linear-gradient(180deg, rgba(255,255,255,.18), rgba(255,255,255,.02) 55%, rgba(0,0,0,.12));
  border: 1px solid rgba(0,0,0,.3); border-top-color: rgba(255,255,255,.22);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.28), 0 4px 0 rgba(0,0,0,.38), 0 7px 14px rgba(0,0,0,.32);
  transform: translateZ(10px); transition: transform .16s cubic-bezier(.2,.9,.3,1.6), box-shadow .16s; }}
:root[data-skin="3d"] button:not(.icon):not(.link):not(.theme-sw):hover {{ transform: translateY(-3px) translateZ(24px) scale(1.05);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.3), 0 7px 0 rgba(0,0,0,.34), 0 16px 24px rgba(0,0,0,.4); }}
:root[data-skin="3d"] button:not(.icon):not(.link):not(.theme-sw):active {{
  transform: translateY(3px) scale(.98); box-shadow: inset 0 2px 5px rgba(0,0,0,.45), 0 1px 0 rgba(0,0,0,.3); }}
:root[data-skin="3d"] button.on:not(.icon):not(.link) {{ transform: translateY(2px) translateZ(4px);
  box-shadow: inset 0 3px 6px rgba(0,0,0,.4), inset 0 -1px 0 rgba(255,255,255,.2), 0 0 16px color-mix(in srgb, var(--acc, #5b8cff) 45%, transparent); }}
:root[data-skin="3d"] button.primary {{ animation: ks3d-glow 1.8s ease-out infinite; }}
:root[data-skin="3d"] .tabs button.on {{ transform: translateY(-4px) scale(1.08); box-shadow: 0 10px 20px rgba(0,0,0,.4); }}
:root[data-skin="3d"] .switch i, :root[data-skin="3d"] input[type=range] {{ box-shadow: inset 0 2px 4px rgba(0,0,0,.5); }}
:root[data-skin="3d"] h1, :root[data-skin="3d"] .big {{ text-shadow: 0 2px 0 rgba(0,0,0,.35), 0 6px 14px rgba(0,0,0,.45); }}
/* ---------- Lett (mobil) ---------- */
:root[data-skin="lett"] *, :root[data-skin="lett"] *::before, :root[data-skin="lett"] *::after {{
  animation: none !important; transition: none !important; backdrop-filter: none !important;
  -webkit-backdrop-filter: none !important; text-shadow: none !important; }}
:root[data-skin="lett"] .card {{ border-radius: 4px; box-shadow: none; background-image: none;
  border: 1px solid color-mix(in srgb, currentColor 14%, transparent); }}
:root[data-skin="lett"] button, :root[data-skin="lett"] input, :root[data-skin="lett"] select {{ border-radius: 3px;
  box-shadow: none; background-image: none; }}
:root[data-skin="lett"] .tabs button {{ border-radius: 0; }}
:root[data-skin="lett"] body {{ background: var(--bg) !important; }}
:root[data-skin="lett"] .card, :root[data-skin="lett"] .cat-bar, :root[data-skin="lett"] header.top {{
  background: var(--card) !important; }}
:root[data-skin="lett"] button:not(.on):not(.primary), :root[data-skin="lett"] .seg, :root[data-skin="lett"] select,
:root[data-skin="lett"] input {{ background-image: none !important; }}
:root[data-skin="lett"] button.on, :root[data-skin="lett"] button.primary {{ background: var(--acc) !important;
  box-shadow: none !important; }}
:root[data-skin="lett"] .seg, :root[data-skin="lett"] .seg button, :root[data-skin="lett"] .chips button {{
  border-radius: 3px !important; }}
:root[data-skin="lett"] .tabs button.on {{ background: color-mix(in srgb, var(--acc) 20%, transparent) !important;
  color: var(--acc) !important; }}
:root[data-skin="lett"] html, :root[data-skin="lett"] body::before, :root[data-skin="lett"] body::after {{
  background-image: none !important; }}
:root[data-skin="lett"] .tabs {{ background: var(--bg2) !important; border-radius: 0 !important; box-shadow: none !important;
  margin: 0 !important; }}
:root[data-skin="lett"] canvas.live-bg, :root[data-skin="lett"] .spark {{ display: none; }}
.design-pick {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 6px 0 4px; }}
.design-pick button {{ flex: 1 1 calc(50% - 10px); }}
.design-pick button {{ flex: 1; display: flex; flex-direction: column; align-items: flex-start; gap: 2px; text-align: left;
  padding: 12px 14px; }}
.design-pick button.on {{ box-shadow: inset 0 0 0 2px var(--acc, #5b8cff); }}
.design-pick small {{ color: var(--dim); font-weight: 400; }}
"""


def write_web():
    """design.css til remote_web og startskjermen i APK-en (kalles fra theme.write_web_themes)."""
    here = os.path.dirname(os.path.abspath(__file__))
    css = web_css()
    meta = {"tabs": MOBILE_TABS, "curated": CURATED, "keep": sorted(KEEP_EMOJI), "advanced": list(ADVANCED)}
    js = "// Laget av design.py – ikke rediger for hånd.\nwindow.KS_DESIGN = " + json.dumps(meta, ensure_ascii=False) + ";\n"
    for d in (os.path.join(here, "remote_web"), os.path.join(here, "android", "app", "src", "main", "assets")):
        if os.path.isdir(d):
            with open(os.path.join(d, "design.css"), "w", encoding="utf-8") as f:
                f.write(css)
            with open(os.path.join(d, "design-data.js"), "w", encoding="utf-8") as f:
                f.write(js)


# ---------------------------------------------------------------------------------------------------------------
# PC: legg på det nye designet
# ---------------------------------------------------------------------------------------------------------------
_APPLIED = []


def apply(window):
    """Kalles for hovedvinduet ved oppstart. Gjør ingenting i Klassisk."""
    if not is_new():
        return
    import gi
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk
    window.add_css_class("ks-ny")
    if skin():
        window.add_css_class("ks-" + skin())
    if _APPLIED:
        return
    _APPLIED.append(1)
    import theme
    theme.add_css(gtk_css(), Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 8)
    if skin() == "3d":
        theme.add_css(gtk_css_3d(), Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 9)
    elif skin() == "lett":
        theme.add_css(gtk_css_lett(), Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 9)
    if IS_WIN:
        try:      # vindusknappene til høyre, som i andre Windows-programmer
            Gtk.Settings.get_default().set_property("gtk-decoration-layout", "icon:minimize,maximize,close")
        except Exception:  # noqa: BLE001
            pass


def _gtk():
    import gi
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk
    return Gtk


def make_tabbar(items, current, on_change):
    """Fanerad: [(nøkkel, tittel, ikon eller None)] – piller som kan rulles sideveis. Har .select(nøkkel)."""
    Gtk = _gtk()
    box = Gtk.Box(spacing=6)
    box.add_css_class("ks-ntabs")
    sc = Gtk.ScrolledWindow(child=box, vscrollbar_policy=Gtk.PolicyType.NEVER,
                            hscrollbar_policy=Gtk.PolicyType.AUTOMATIC, propagate_natural_height=True,
                            hexpand=True)
    sc._buttons = {}
    sc._quiet = [False]
    first = None
    for it in items:
        key, title = it[0], it[1]
        icon = it[2] if len(it) > 2 else None
        b = Gtk.ToggleButton()
        inner = Gtk.Box(spacing=6)
        if icon:
            inner.append(Gtk.Image(icon_name=icon))
        inner.append(Gtk.Label(label=strip_emoji(title)))
        b.set_child(inner)
        if first is not None:
            b.set_group(first)
        first = first or b
        b.set_active(key == current)
        b.connect("toggled", lambda w, k=key: w.get_active() and not sc._quiet[0] and on_change(k))
        box.append(b)
        sc._buttons[key] = b

    def select(key):
        b = sc._buttons.get(key)
        if b is not None and not b.get_active():
            sc._quiet[0] = True
            b.set_active(True)
            sc._quiet[0] = False
    sc.select = select
    return sc


# ---------------------------------------------------------------------------------------------------------------
# PC: rydd en side (kalles når en side vises)
# ---------------------------------------------------------------------------------------------------------------
_TITLE_CLASSES = ("heading", "title-1", "title-2", "title-3", "title-4", "caption-heading")


def polish(page, name=""):
    """Emoji bort fra overskriftene, én fremhevet knapp per kort, avanserte kort lukket. Trygt å kalle flere ganger."""
    if not is_new() or page is None:
        return
    Gtk = _gtk()
    keep = name in KEEP_EMOJI

    def walk(w, card, depth):
        if depth > 60:
            return
        if w.has_css_class("card"):
            _card(w, Gtk)
            card = w
        if isinstance(w, Gtk.Label):
            if not keep and any(w.has_css_class(c) for c in _TITLE_CLASSES):
                txt = w.get_label()
                new = strip_emoji(txt)
                if new != txt and not w.get_use_markup():
                    w.set_label(new)
            return
        if card is not None and isinstance(w, Gtk.Button) and w.has_css_class("suggested-action") \
                and not w.has_css_class("ks-primary-kept"):
            if getattr(card, "_ks_primary", None) is None or card._ks_primary is w:
                card._ks_primary = w
            else:
                w.remove_css_class("suggested-action")
                w.add_css_class("ks-demoted")
        c = w.get_first_child()
        while c is not None:
            walk(c, card, depth + 1)
            c = c.get_next_sibling()
    try:
        walk(page, None, 0)
    except Exception:  # noqa: BLE001 – utseende skal aldri stoppe en side
        pass


def _heading_of(card, Gtk):
    inner = card.get_first_child()
    if inner is None:
        return None, None
    first = inner.get_first_child()
    if isinstance(first, Gtk.Label) and first.has_css_class("heading"):
        return inner, first
    return None, None


def _card(card, Gtk):
    """Lukk kort for feilsøking/avansert bak en «Vis»-knapp (én gang per kort)."""
    if getattr(card, "_ks_adv_done", False):
        return
    card._ks_adv_done = True
    inner, head = _heading_of(card, Gtk)
    if head is None or not strip_emoji(head.get_label() or "").startswith(ADVANCED):
        return
    kids = []
    c = head.get_next_sibling()
    while c is not None:
        kids.append(c)
        c = c.get_next_sibling()
    if not kids:
        return
    btn = Gtk.Button(label="Vis", halign=Gtk.Align.START)
    btn.add_css_class("ks-adv-toggle")
    btn.add_css_class("flat")
    state = {"open": False, "vis": {}}
    for k in kids:
        state["vis"][k] = k.get_visible()
        k.set_visible(False)

    def toggle(_b):
        state["open"] = not state["open"]
        for k in kids:
            if state["open"]:
                k.set_visible(state["vis"].get(k, True))
            else:
                state["vis"][k] = k.get_visible()
                k.set_visible(False)
        btn.set_label("Skjul" if state["open"] else "Vis")
    btn.connect("clicked", toggle)
    inner.insert_child_after(btn, head)
