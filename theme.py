"""Kontrollsenter-designet: ett stilark for hele programmet (Linux og Windows, lyst og mørkt).

Bygger på libadwaitas fargevariabler, så lyst/mørkt og høykontrast følger systemet, men med egen
merkevare: blå–lilla gradient (samme som appen på mobil og nettbrett), mykere kort, ryddig sidemeny
med seksjoner og roligere typografi.
"""
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
  background-image: radial-gradient(circle farthest-side at 50% 0%, alpha(#6a7bff, 0.09), transparent);
  background-size: 100% 520px;
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
button.suggested-action {
  background-color: transparent;
  background-image: linear-gradient(135deg, #5b8cff, #8a5cff);
  color: white;
  box-shadow: 0 6px 16px -8px alpha(#6a7bff, 0.9);
}
button.suggested-action:hover { background-image: linear-gradient(135deg, #6b98ff, #9868ff); }
button.suggested-action:active { background-image: linear-gradient(135deg, #4f7ef0, #7c50ef); }
button.suggested-action:disabled { background-image: none; background-color: alpha(currentColor, 0.1); box-shadow: none; }

.linked > button:checked, .linked > togglebutton:checked, .linked > button.toggle:checked {
  background-color: transparent;
  background-image: linear-gradient(135deg, #5b8cff, #8a5cff);
  color: white;
}
switch:checked { background-color: transparent; background-image: linear-gradient(135deg, #5b8cff, #8a5cff); }
scale highlight { background-color: transparent; background-image: linear-gradient(90deg, #5b8cff, #8a5cff); }
checkbutton check:checked, radiobutton radio:checked, check:checked, radio:checked {
  background-color: transparent; background-image: linear-gradient(135deg, #5b8cff, #8a5cff); color: white;
}
progressbar > trough > progress { background-image: linear-gradient(90deg, #5b8cff, #8a5cff); }

entry, spinbutton, dropdown > button, combobox > box > button { border-radius: 10px; }
popover > contents { border-radius: 14px; }

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

levelbar.disk-ok block.filled { background-color: var(--accent-bg-color); }
levelbar.disk-warn block.filled { background-color: var(--warning-bg-color); }
levelbar.disk-crit block.filled { background-color: var(--error-bg-color); }
"""

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
    _LOADED = True


# Sidemenyens seksjoner: fane -> seksjon (rekkefølgen her er rekkefølgen i menyen)
SECTIONS = [
    ("Overvåking", ["oversikt", "historikk"]),
    ("Enheter", ["rgb", "logitech", "cpuskjerm", "lyd", "bluetooth", "wifi", "msi"]),
    ("Spill", ["spill", "stromming"]),
    ("System", ["nettverk", "automatikk", "programmer", "hjemme", "verktoy"]),
]
ORDER = [n for _s, names in SECTIONS for n in names]
SECTION_OF = {n: s for s, names in SECTIONS for n in names}


# Kort forklaring øverst på hver side (og som verktøytips i sidemenyen)
PAGE_HELP = {
    "oversikt": "Temperaturer, strømforbruk, vifter og strømmodus – alt det viktigste på ett sted.",
    "historikk": "Temperatur, belastning og strømforbruk over tid. Finn ut når PC-en ble varm eller brukte mye strøm.",
    "rgb": "Farger og effekter på alle lysene – hovedkort, vifter, CPU-kjøler, RAM, skjermkort, mus og tastatur.",
    "logitech": "Batteri, DPI, rapporteringsfrekvens, profiler og knapper på Logitech-musen og -tastaturet.",
    "cpuskjerm": "Hva skjermen på CPU-kjøleren viser: temperaturer, bilder, video eller et tema.",
    "lyd": "Velg høyttalere og mikrofon, juster volum per program og lag lydprofiler.",
    "bluetooth": "Koble til og fra hodetelefoner, kontrollere og andre Bluetooth-enheter.",
    "wifi": "Trådløse nett i nærheten, signalstyrke og tilkobling.",
    "msi": "Ytelsesmodus, viftene, Cooler Boost og ladegrense på MSI-laptopen.",
    "spill": "Spillstatistikk, klipp av de beste øyeblikkene, spilløkter og oppsett av spill.",
    "stromming": "Spill og se PC-skjermen på telefonen (Sunshine + Moonlight), og fjernhjelp med RustDesk.",
    "nettverk": "Hastighet, ping, hvilke programmer som bruker nettet, og enhetene på hjemmenettet.",
    "automatikk": "Ting som skjer av seg selv: spillmodus når et spill starter, nattmodus, profiler per spill.",
    "programmer": "Installer, oppdater og velg hvilke programmer som starter med PC-en.",
    "hjemme": "De andre PC-ene i huset, mobilappen, familie-chat og fjernstyring.",
    "verktoy": "Rydding, oppdateringer, varsler, feilsøking og innstillinger for Kontrollsenter.",
}


def greeting(hour):
    if hour < 5:
        return "God natt"
    if hour < 10:
        return "God morgen"
    if hour < 18:
        return "God dag"
    return "God kveld"
