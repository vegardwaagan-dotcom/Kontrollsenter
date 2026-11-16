"""Kontrollsenter-designet: ett stilark for hele programmet (Linux og Windows, lyst og mørkt).

Bygger på libadwaitas fargevariabler, så lyst/mørkt og høykontrast følger systemet, men med egen
merkevare: blå–lilla gradient (samme som appen på mobil og nettbrett), mykere kort, ryddig sidemeny
med seksjoner og roligere typografi.
"""
import json
import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gtk  # noqa: E402

PAGE_WIDTH = 1120          # alle sider har samme bredde på store skjermer

CSS = """
:root {
  --accent-bg-color: #6a7bff;
  --ks-a: #5b8cff;
  --ks-b: #8a5cff;
  --ks-radius: 18px;
}

window.sysmon {
  font-family: "Adwaita Sans", "Inter", "Segoe UI Variable Text", "Segoe UI", "Noto Sans", sans-serif;
}

/* ---------- innholdet: rolig bakgrunn med et svakt lys øverst ---------- */
.ks-content {
  background-color: var(--window-bg-color);
  background-image: radial-gradient(ellipse 70% 40% at 50% 0%, alpha(#6a7bff, 0.09), transparent);
  background-size: 100% 100%;
  background-repeat: no-repeat;
}
.ks-content > headerbar, .ks-content headerbar {
  background: transparent;
  box-shadow: none;
}
.ks-content scrolledwindow, .ks-content viewport { background: transparent; }

/* ---------- sidemenyen ---------- */
.ks-side { background-color: var(--sidebar-bg-color, var(--window-bg-color)); }
.ks-side headerbar { background: transparent; box-shadow: none; }
.ks-brand-logo {
  min-width: 30px; min-height: 30px; border-radius: 10px;
  background-image: linear-gradient(135deg, #5b8cff, #8a5cff);
  box-shadow: 0 4px 14px -4px alpha(#6a7bff, 0.8);
  color: white;
}
.ks-brand-title { font-weight: 800; font-size: 1.05em; letter-spacing: -0.01em; }
.ks-brand-sub { font-size: 0.8em; opacity: 0.55; }

.navigation-sidebar.ks-sidebar { background: transparent; padding: 2px 10px 10px 10px; }
.navigation-sidebar.ks-sidebar > row {
  border-radius: 12px; min-height: 38px; margin: 1px 0; padding: 0 8px;
  transition: background-color 160ms ease;
}
.navigation-sidebar.ks-sidebar > row:hover { background-color: alpha(currentColor, 0.06); }
.navigation-sidebar.ks-sidebar > row:selected {
  background-color: transparent;
  background-image: linear-gradient(90deg, alpha(#5b8cff, 0.22), alpha(#8a5cff, 0.12));
  color: inherit;
}
.navigation-sidebar.ks-sidebar > row:selected image { color: var(--accent-color); }
.navigation-sidebar.ks-sidebar > row:selected label.ks-row-title { font-weight: 700; }
.navigation-sidebar.ks-sidebar > row image { opacity: 0.85; }
.ks-section {
  font-size: 0.7em; font-weight: 800; letter-spacing: 0.09em;
  opacity: 0.45; margin: 16px 12px 4px 12px;
}
.ks-section.first { margin-top: 8px; }
.sidebar-badge {
  font-size: 0.78em; font-weight: 700; padding: 1px 7px; border-radius: 99px;
  background-color: alpha(currentColor, 0.07);
}
.sidebar-badge:disabled, .sidebar-badge.empty { background: none; }

/* livestatus nederst i sidemenyen */
.ks-pulse {
  margin: 8px 12px 12px 12px; padding: 10px 12px; border-radius: 14px;
  background-color: alpha(currentColor, 0.045);
}
.ks-pulse-value { font-weight: 800; font-size: 1.05em; }
.ks-pulse-label { font-size: 0.72em; opacity: 0.55; letter-spacing: 0.04em; }

/* ---------- kort ---------- */
.card {
  border-radius: var(--ks-radius);
  background-color: var(--card-bg-color);
  box-shadow: 0 0 0 1px alpha(currentColor, 0.06),
              0 1px 2px alpha(black, 0.04),
              0 12px 28px -14px alpha(black, 0.22);
}
.card.activatable:hover, .card.tile:hover {
  box-shadow: 0 0 0 1px alpha(#6a7bff, 0.30),
              0 1px 2px alpha(black, 0.04),
              0 16px 32px -14px alpha(#6a7bff, 0.35);
}
.boxed-list, .boxed-list-separate > row { border-radius: 14px; }
.heading { font-weight: 750; letter-spacing: -0.005em; }
.title-1, .title-2, .title-3 { letter-spacing: -0.02em; }
.caption.dim-label { opacity: 0.62; }

/* nøkkeltall øverst i Oversikt */
.card.tile .title-3 { font-size: 1.45em; font-weight: 800; }
.tile-icon {
  color: white; padding: 10px; border-radius: 14px;
  background-image: linear-gradient(135deg, #5b8cff, #8a5cff);
  box-shadow: 0 6px 16px -6px alpha(#6a7bff, 0.8);
  -gtk-icon-size: 26px;
}

/* velkomst øverst i Oversikt */
.ks-hello { font-size: 2.0em; font-weight: 800; letter-spacing: -0.03em; }
.ks-hello-sub { font-size: 1.0em; opacity: 0.65; }
.ks-chip {
  padding: 4px 12px; border-radius: 99px; font-weight: 700; font-size: 0.85em;
  background-color: alpha(#2ec27e, 0.14); color: #26a269;
}
.ks-chip.warn { background-color: alpha(#e5a50a, 0.16); color: #c88800; }
.ks-chip.bad { background-color: alpha(#e01b24, 0.14); color: #e01b24; }

/* ---------- knapper og brytere ---------- */
button { border-radius: 10px; }
button.pill, button.circular { border-radius: 99px; }
/* knapper uten av/på er vanlige – lilla bare mens du holder musa/fingeren nede (som i appen).
   Bare knapper som er slått på (:checked, brytere, avkrysning) er lilla hele tiden. */
button.suggested-action {
  background-color: color-mix(in srgb, var(--window-fg-color) 10%, transparent);
  background-image: none;
  color: var(--window-fg-color);
  box-shadow: none;
}
button.suggested-action:hover { background-color: color-mix(in srgb, var(--window-fg-color) 15%, transparent); }
button.suggested-action:disabled { background-color: alpha(currentColor, 0.1); }
button:active:not(:disabled), button.suggested-action:active:not(:disabled), button.flat:active:not(:disabled) {
  background-color: transparent;
  background-image: linear-gradient(135deg, #4f7ef0, #7c50ef);
  color: white;
}

/* alle knapper som er slått på blir lilla – samme som «Auto» på viftene */
button:checked, togglebutton:checked, button.toggle:checked,
.linked > button:checked, .linked > togglebutton:checked, .linked > button.toggle:checked {
  background-color: transparent;
  background-image: linear-gradient(135deg, #5b8cff, #8a5cff);
  color: white;
}
button:checked:hover, togglebutton:checked:hover { background-image: linear-gradient(135deg, #6b98ff, #9868ff); }
/* menyknapper og sidemeny-knapper er «checked» bare mens menyen er åpen – de skal ikke bli lilla */
menubutton > button:checked, dropdown > button:checked, combobox > box > button:checked,
headerbar menubutton > button:checked, splitbutton > menubutton > button:checked {
  background-image: none; color: inherit;
}
switch:checked { background-color: transparent; background-image: linear-gradient(135deg, #5b8cff, #8a5cff); }
scale highlight { background-color: transparent; background-image: linear-gradient(90deg, #5b8cff, #8a5cff); }
checkbutton check:checked, radiobutton radio:checked, check:checked, radio:checked {
  background-color: transparent; background-image: linear-gradient(135deg, #5b8cff, #8a5cff); color: white;
}
progressbar > trough > progress { background-image: linear-gradient(90deg, #5b8cff, #8a5cff); }

entry, spinbutton, dropdown > button, combobox > box > button { border-radius: 10px; }
popover > contents { border-radius: 14px; }

/* kort i rutenett (Smart Hjem): ingen markering bak kortene */
flowbox.ks-cards > flowboxchild { padding: 0; background: none; box-shadow: none; outline: none; }
flowbox.ks-cards > flowboxchild:hover, flowbox.ks-cards > flowboxchild:selected { background: none; }

/* tynn rullefelt */
scrollbar slider { min-width: 6px; min-height: 6px; border-radius: 99px; }

/* ---------- skrift: luft, faste størrelser og rolige forklaringer ---------- */
label { line-height: 1.28; }
.caption { font-size: 0.86em; line-height: 1.4; }
box > label.caption:not(:first-child), box > label.dim-label:not(:first-child) { margin-top: 2px; }
.card .heading { margin-bottom: 2px; }
.title-4 { font-size: 1.16em; font-weight: 750; letter-spacing: -0.01em; }
.ks-desc { opacity: 0.72; line-height: 1.5; }
.ks-sub { opacity: 0.62; font-size: 0.9em; line-height: 1.4; }
.ks-mono { font-family: monospace; opacity: 0.8; }
.ks-step {
  min-width: 24px; min-height: 24px; border-radius: 99px; font-weight: 800; font-size: 0.82em; color: white;
  background-image: linear-gradient(135deg, #5b8cff, #8a5cff);
}
.ks-ok { color: #2ec27e; }
.ks-off { color: alpha(currentColor, 0.35); }
.ks-pagehelp { opacity: 0.68; line-height: 1.5; font-size: 0.95em; }
expander title > label { font-weight: 600; }

/* «Se på» */
.ks-watch-bg { background-color: black; }
.ks-watch-status {
  background-color: alpha(black, 0.65); color: white; padding: 8px 16px; border-radius: 99px; font-weight: 600;
}

/* GPU-innstillinger */
.ks-vendor { font-weight: 900; font-size: 0.75em; letter-spacing: 0.08em; padding: 4px 10px; border-radius: 99px; color: white; }
.ks-vendor-nvidia { background-color: #76b900; }
.ks-vendor-amd { background-color: #ed1c24; }
.ks-vendor-intel { background-color: #0071c5; }
.ks-gpu-stat { padding: 10px 12px; border-radius: 14px; background-color: alpha(currentColor, 0.05); }
.ks-gpu-k { font-size: 0.68em; font-weight: 800; letter-spacing: 0.08em; opacity: 0.55; }
.ks-gpu-v { font-weight: 700; }

levelbar.disk-ok block.filled { background-color: var(--accent-bg-color); }
levelbar.disk-warn block.filled { background-color: var(--warning-bg-color); }
levelbar.disk-crit block.filled { background-color: var(--error-bg-color); }
"""

# Flytende glass: lysrefleks i kanten, mykt skinn over flatene og farger som skinner gjennom.
GLASS_CSS = """
window.ks-glass .ks-content {
  background-image:
    radial-gradient(ellipse 55% 45% at 10% 0%, alpha(#5b8cff, 0.30), transparent),
    radial-gradient(ellipse 45% 40% at 95% 6%, alpha(#9a6bff, 0.26), transparent),
    radial-gradient(ellipse 70% 40% at 55% 100%, alpha(#00c8b4, 0.12), transparent);
  background-size: 100% 100%;
  background-repeat: no-repeat;
}
window.ks-glass .card {
  background-color: color-mix(in srgb, var(--card-bg-color) 60%, transparent);
  background-image: linear-gradient(160deg, alpha(white, 0.11), alpha(white, 0.02) 38%, transparent 62%, alpha(white, 0.05));
  box-shadow: inset 0 1px alpha(white, 0.32), inset 0 -1px alpha(black, 0.10), inset 1px 0 alpha(white, 0.06),
              0 0 0 1px alpha(currentColor, 0.08), 0 20px 40px -20px alpha(black, 0.45);
}
window.ks-glass .card.tile:hover {
  box-shadow: inset 0 1px alpha(white, 0.40), 0 0 0 1px alpha(#6a7bff, 0.35), 0 22px 40px -18px alpha(#6a7bff, 0.45);
}
window.ks-glass button:not(.flat):not(.destructive-action):not(.circular):not(.image-button) {
  background-color: color-mix(in srgb, currentColor 7%, transparent);
  background-image: linear-gradient(180deg, alpha(white, 0.13), alpha(white, 0) 62%);
  box-shadow: inset 0 1px alpha(white, 0.26), 0 0 0 1px alpha(currentColor, 0.08);
}
window.ks-glass togglebutton:checked, window.ks-glass button:checked,
window.ks-glass .linked > togglebutton:checked,
window.ks-glass .linked > button:checked {
  box-shadow: inset 0 1px alpha(white, 0.50), inset 0 -3px 8px alpha(black, 0.14), 0 10px 22px -10px alpha(#6a7bff, 0.95);
}
window.ks-glass .ks-side {
  background-color: color-mix(in srgb, var(--sidebar-bg-color, var(--window-bg-color)) 72%, transparent);
  background-image: linear-gradient(180deg, alpha(white, 0.07), transparent 35%),
                    radial-gradient(circle farthest-side at 0% 0%, alpha(#5b8cff, 0.18), transparent);
  background-size: 100% 100%, 100% 420px; background-repeat: no-repeat;
  box-shadow: inset -1px 0 alpha(white, 0.08);
}
window.ks-glass .navigation-sidebar.ks-sidebar > row:selected {
  box-shadow: inset 0 1px alpha(white, 0.32), 0 0 0 1px alpha(#6a7bff, 0.28);
}
window.ks-glass .ks-pulse, window.ks-glass .ks-chip, window.ks-glass .sidebar-badge {
  background-image: linear-gradient(160deg, alpha(white, 0.12), transparent 70%);
  box-shadow: inset 0 1px alpha(white, 0.28), 0 0 0 1px alpha(currentColor, 0.06);
}
window.ks-glass switch slider { box-shadow: inset 0 1px alpha(white, 0.7), 0 2px 6px alpha(black, 0.28); }
window.ks-glass .tile-icon, window.ks-glass .ks-brand-logo, window.ks-glass .ks-step {
  box-shadow: inset 0 1px alpha(white, 0.55), inset 0 -2px 5px alpha(black, 0.18), 0 8px 18px -8px alpha(#6a7bff, 0.9);
}
window.ks-glass popover > contents, window.ks-glass dialog-host floating-sheet > sheet, window.ks-glass .dialog-contents {
  box-shadow: inset 0 1px alpha(white, 0.25), 0 0 0 1px alpha(currentColor, 0.08), 0 24px 48px -16px alpha(black, 0.5);
}
/* glass: knapper som er på er lilla, og alle knapper lyser lilla mens de holdes nede */
window.ks-glass button:not(.flat):not(.destructive-action):not(.circular):not(.image-button):checked, window.ks-glass button:not(.flat):not(.destructive-action):not(.circular):not(.image-button):active:not(:disabled) {
  background-color: transparent; background-image: linear-gradient(135deg, #5b8cff, #8a5cff); color: white;
}
window.ks-glass menubutton > button:not(.flat):not(.destructive-action):not(.circular):not(.image-button):checked,
window.ks-glass dropdown > button:not(.flat):not(.destructive-action):not(.circular):not(.image-button):checked {
  background-color: color-mix(in srgb, currentColor 7%, transparent);
  background-image: linear-gradient(180deg, alpha(white, 0.13), alpha(white, 0) 62%); color: inherit;
}
"""
# Tøff glød når musa er over knapper, brytere og valg – på eller av. Egen kilde med høyere prioritet,
# så den vinner over glass-stilen.
GLOW_CSS = """
button, switch, checkbutton check, radiobutton radio, .navigation-sidebar > row, .card.tile, dropdown > button {
  transition: box-shadow 220ms ease, background-color 160ms ease, border-color 160ms ease;
}
button:hover:not(:disabled), dropdown > button:hover {
  box-shadow: inset 0 1px alpha(white, 0.28), 0 0 0 1px alpha(#9aa8ff, 0.85),
              0 0 16px 3px alpha(#6a7bff, 0.75), 0 0 40px 10px alpha(#8a5cff, 0.40);
}
button.flat:hover:not(:disabled), button.circular:hover:not(:disabled), button.image-button:hover:not(:disabled) {
  box-shadow: 0 0 0 1px alpha(#8a9bff, 0.45), 0 0 14px alpha(#6a7bff, 0.45);
}
button:checked:hover, .linked > button:checked:hover, button:active:not(:disabled) {
  box-shadow: inset 0 1px alpha(white, 0.6), 0 0 0 1px alpha(white, 0.45),
              0 0 22px 5px alpha(#6a7bff, 0.95), 0 0 56px 14px alpha(#8a5cff, 0.55);
}
button:checked, .linked > button:checked {
  box-shadow: inset 0 1px alpha(white, 0.45), 0 0 14px alpha(#6a7bff, 0.55);
}
switch:hover { box-shadow: 0 0 0 1px alpha(#8a9bff, 0.6), 0 0 16px 2px alpha(#6a7bff, 0.6); }
switch:checked:hover { box-shadow: 0 0 0 1px alpha(white, 0.35), 0 0 22px 4px alpha(#8a5cff, 0.75); }
checkbutton:hover check, radiobutton:hover radio { box-shadow: 0 0 12px 2px alpha(#6a7bff, 0.65); }
.navigation-sidebar > row:hover { box-shadow: 0 0 0 1px alpha(#8a9bff, 0.35), 0 0 16px alpha(#6a7bff, 0.30); }
scale:hover slider { box-shadow: 0 0 14px 2px alpha(#6a7bff, 0.7); }

/* skrivebordswidgets */
window.ks-desk { background: transparent; }
window.ks-desk > windowhandle { border-radius: 22px; }
.ks-desk-body {
  padding: 16px 18px 18px 18px; border-radius: 22px; min-width: 220px;
  background-color: alpha(#141626, 0.82);
  background-image: linear-gradient(155deg, alpha(#5b8cff, 0.30), alpha(white, 0.03) 45%, alpha(#8a5cff, 0.22));
  box-shadow: inset 0 1px alpha(white, 0.35), inset 0 0 0 1px alpha(white, 0.10), 0 18px 40px -16px alpha(black, 0.7);
  color: white;
}
.ks-desk-title { font-size: 0.72em; font-weight: 800; letter-spacing: 0.12em; color: alpha(white, 0.6); }
.ks-desk-name { font-weight: 800; font-size: 1.15em; color: white; }
.ks-desk-big { font-size: 1.9em; font-weight: 800; color: white; letter-spacing: -0.02em; }
.ks-desk-k { font-size: 0.7em; font-weight: 800; letter-spacing: 0.1em; color: alpha(white, 0.6); }
.ks-desk-sub { color: alpha(white, 0.72); font-size: 0.9em; }
.ks-desk-row { color: white; font-weight: 600; }
.ks-desk-btn { min-height: 64px; border-radius: 16px; color: white; background-color: alpha(white, 0.08);
  background-image: linear-gradient(180deg, alpha(white, 0.12), transparent); }
.ks-desk-btn.slim { min-height: 40px; }
.ks-desk-btn.on { background-image: linear-gradient(135deg, #5b8cff, #8a5cff); }
.ks-desk-ic { font-size: 1.5em; } .ks-desk-bl { font-size: 0.8em; font-weight: 700; color: white; }
.ks-desk-x { min-width: 26px; min-height: 26px; padding: 0; background-color: alpha(black, 0.4); color: white; }
"""
LOOK = os.path.expanduser("~/.config/systemmonitor/utseende.json")


def glass_on():
    try:
        return bool(json.load(open(LOOK)).get("glass", True))
    except (OSError, ValueError):
        return True


def set_glass(on, window=None):
    os.makedirs(os.path.dirname(LOOK), exist_ok=True)
    json.dump({"glass": bool(on)}, open(LOOK, "w"))
    for w in ([window] if window else Gtk.Window.list_toplevels()):
        if w is not None:
            (w.add_css_class if on else w.remove_css_class)("ks-glass")


_LOADED = False


def load():
    """Legg inn designet for hele programmet (én gang)."""
    global _LOADED
    if _LOADED:
        return
    css = Gtk.CssProvider()
    if hasattr(css, "load_from_string"):
        css.load_from_string(CSS)
    else:
        css.load_from_data(CSS.encode(), -1)
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css,
                                              Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    g = Gtk.CssProvider()
    g.load_from_string(GLASS_CSS) if hasattr(g, "load_from_string") else g.load_from_data(GLASS_CSS.encode(), -1)
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), g,
                                              Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
    gl = Gtk.CssProvider()
    gl.load_from_string(GLOW_CSS) if hasattr(gl, "load_from_string") else gl.load_from_data(GLOW_CSS.encode(), -1)
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), gl,
                                              Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 2)
    _LOADED = True


# Sidemenyens seksjoner: fane -> seksjon (rekkefølgen her er rekkefølgen i menyen)
SECTIONS = [
    ("Overvåking", ["oversikt", "historikk"]),
    ("Enheter", ["gpu", "rgb", "logitech", "cpuskjerm", "lyd", "bluetooth", "wifi", "msi"]),
    ("Spill", ["spill", "stromming"]),
    ("Hjemmet", ["familie", "hjemme", "smarthjem"]),
    ("System", ["nettverk", "programmer", "verktoy", "innstillinger"]),
]
ORDER = [n for _s, names in SECTIONS for n in names]
SECTION_OF = {n: s for s, names in SECTIONS for n in names}


# Kort forklaring øverst på hver side (og som verktøytips i sidemenyen)
PAGE_HELP = {
    "oversikt": "Temperaturer, strømforbruk, vifter og strømmodus – alt det viktigste på ett sted.",
    "historikk": "Temperatur, belastning og strømforbruk over tid. Finn ut når PC-en ble varm eller brukte mye strøm.",
    "gpu": "Innstillinger for skjermkortene som finnes i PC-en: NVIDIA (strøm, klokker), AMD (OverDrive, "
           "ytelsesnivå) og Intel – og spillinnstillinger.",
    "rgb": "Farger og effekter på alle lysene – hovedkort, vifter, CPU-kjøler, RAM, skjermkort, mus og tastatur.",
    "logitech": "Batteri, DPI, rapporteringsfrekvens, profiler og knapper på Logitech-musen og -tastaturet.",
    "cpuskjerm": "Hva skjermen på CPU-kjøleren viser: temperaturer, bilder, video eller et tema.",
    "lyd": "Velg høyttalere og mikrofon, juster volum per program og lag lydprofiler.",
    "bluetooth": "Koble til og fra hodetelefoner, kontrollere og andre Bluetooth-enheter.",
    "wifi": "Trådløse nett i nærheten, signalstyrke og tilkobling.",
    "msi": "Ytelsesmodus, viftene, Cooler Boost og ladegrense på MSI-laptopen.",
    "spill": "Statistikk og spilløkter, klipp, Steam-biblioteket, spillprofiler som slår på spillmodus "
             "automatisk, og kontrollere.",
    "stromming": "Spill og se PC-skjermen på telefonen (Sunshine + Moonlight), og fjernhjelp med RustDesk.",
    "familie": "Familiekontroll med kode, «Se på» skjermen til de andre PC-ene, familie-chat, «Middag!», "
               "ekstra spilletid og leggetid.",
    "nettverk": "Hastighet, ping, hvilke programmer som bruker nettet, og enhetene på hjemmenettet.",
    "programmer": "Installer, oppdater og velg hvilke programmer som starter med PC-en.",
    "smarthjem": "Alle smartenhetene på hjemmenettet: styr Hue-lys, Samsung-TV og Chromecast/Nest, og se alt annet som er koblet til.",
    "hjemme": "De andre PC-ene i huset med Kontrollsenter: status, temperatur og hvem som spiller.",
    "verktoy": "Hold PC-en i form: systeminfo, diskhelse, opprydding, gjenoppretting og feilsøking.",
    "innstillinger": "Alt du kan stille inn i Kontrollsenter: oppstart, utseende, språk, varsler, stille om natten, "
                     "widgets, mobilappen og oppdateringer.",
}


def greeting(hour):
    if hour < 5:
        return "God natt"
    if hour < 10:
        return "God morgen"
    if hour < 18:
        return "God dag"
    return "God kveld"
