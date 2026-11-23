"""Kontrollsenter-designet: ett stilark for hele programmet (Linux og Windows, lyst og mørkt).

Bygger på libadwaitas fargevariabler, så lyst/mørkt og høykontrast følger systemet, men med egen
merkevare: blå–lilla gradient (samme som appen på mobil og nettbrett), mykere kort, ryddig sidemeny
med seksjoner og roligere typografi.
"""
import json
import time
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
/* enheter som lader: grønt, pulserende lyn */
image.ks-charging { color: #2ec27e; animation: ks-charge-pulse 1.6s steps(4) infinite; }
label.ks-charging { color: #26a269; font-weight: 700; }
levelbar.ks-charging block.filled { background: linear-gradient(90deg, #2ec27e, #57e389); }
@keyframes ks-charge-pulse { 0% { opacity: 1; } 50% { opacity: .35; } 100% { opacity: 1; } }
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
/* flisene og kortene gløder som knappene */
.ks-dash-item > .card, .ks-dash-item > .tile, .card.ks-scene { transition: box-shadow 260ms ease; }
.ks-dash-item:hover > .card, .ks-dash-item:hover > .tile, .card.ks-scene:hover,
window.ks-glass .ks-dash-item:hover > .card, window.ks-glass .ks-dash-item:hover > .tile,
window.ks-glass .card.tile:hover, window.ks-glass .card.ks-scene:hover {
  box-shadow: inset 0 1px alpha(white, 0.35), 0 0 0 1px alpha(#6a7bff, 0.95),
              0 0 22px 4px alpha(#6a7bff, 0.70), 0 0 58px 14px alpha(#8a5cff, 0.40);
}
.ks-dash-item:active > .card, .ks-dash-item:active > .tile, .card.ks-scene:active {
  box-shadow: inset 0 1px alpha(white, 0.55), 0 0 0 1px alpha(white, 0.45),
              0 0 24px 5px alpha(#6a7bff, 0.85), 0 0 60px 14px alpha(#8a5cff, 0.45);
}

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

# ---------------------------------------------------------------------------------------------------------------
# Temaer – samme sett på PC (Linux/Windows) og i appen (Android). a/b = gradienten, c = tredje glød,
# bg/side/card = flatene, fg/dim = tekst. dark=None betyr «følg systemet».
# ---------------------------------------------------------------------------------------------------------------
THEMES = {
    "standard":   {"name": "Kontrollsenter", "desc": "Blått og lilla – som før", "dark": None,
                   "a": "#5b8cff", "b": "#8a5cff", "c": "#00c8b4"},
    "nordlys":    {"name": "Nordlys", "desc": "Grønt og fiolett lys over en polarnatt", "dark": True,
                   "a": "#2ef2b3", "b": "#7c5cff", "c": "#22d3ee",
                   "bg": "#06111a", "side": "#091822", "card": "#0e1f2b", "fg": "#e8fbf6", "dim": "#8fb3ad"},
    "synthwave":  {"name": "Synthwave", "desc": "Neonrosa og cyan – rett fra 1986", "dark": True,
                   "a": "#ff2bd6", "b": "#22e4ff", "c": "#ffb02e",
                   "bg": "#110621", "side": "#16092a", "card": "#1e0f35", "fg": "#fbe9ff", "dim": "#b49ac9"},
    "solnedgang": {"name": "Solnedgang", "desc": "Glødende oransje mot rosa", "dark": True,
                   "a": "#ff8a3d", "b": "#ff3d7f", "c": "#ffd166",
                   "bg": "#170b10", "side": "#1d0e15", "card": "#27131b", "fg": "#fff1ea", "dim": "#c8a59a"},
    "dyphav":     {"name": "Dyphav", "desc": "Turkis lys i dypblått vann", "dark": True,
                   "a": "#00c2ff", "b": "#3a5bff", "c": "#00e0b8",
                   "bg": "#03111b", "side": "#051826", "card": "#0a2234", "fg": "#e6f6ff", "dim": "#8fb0c4"},
    "skog":       {"name": "Skog", "desc": "Mose, lime og kveldslys", "dark": True,
                   "a": "#5bd68a", "b": "#c3e35a", "c": "#3fb6a8",
                   "bg": "#0a130d", "side": "#0d1a11", "card": "#142219", "fg": "#ecf7ee", "dim": "#9db7a3"},
    "gull":       {"name": "Midnatt og gull", "desc": "Svart, børstet gull – luksus", "dark": True,
                   "a": "#f5c76b", "b": "#c9862b", "c": "#fff1c1",
                   "bg": "#08080a", "side": "#0e0e11", "card": "#161618", "fg": "#f7f2e7", "dim": "#a59e8f"},
    "lava":       {"name": "Lava", "desc": "Glødende rødt og gult på svart stein", "dark": True,
                   "a": "#ff4d1a", "b": "#ffb21a", "c": "#ff2e63",
                   "bg": "#130706", "side": "#190a08", "card": "#23100c", "fg": "#fff0ea", "dim": "#c39a8e"},
    "cyberpunk":  {"name": "Cyberpunk", "desc": "Gul neon og cyan i en regnvåt by", "dark": True,
                   "a": "#fcee0a", "b": "#00f0ff", "c": "#ff2a6d",
                   "bg": "#0a0a0d", "side": "#0f0f14", "card": "#16161d", "fg": "#f6f6e9", "dim": "#a3a38f"},
    "galakse":    {"name": "Galakse", "desc": "Magenta tåker og stjernestøv", "dark": True,
                   "a": "#c86bff", "b": "#ff5fa2", "c": "#5f8bff",
                   "bg": "#0b0716", "side": "#100a1f", "card": "#18102c", "fg": "#f3eaff", "dim": "#a998c4"},
    "matrix":     {"name": "Matrix", "desc": "Grønn kode på svart", "dark": True,
                   "a": "#00ff7b", "b": "#00c060", "c": "#9dff00",
                   "bg": "#020604", "side": "#040a06", "card": "#08120c", "fg": "#d8ffe8", "dim": "#6f9c80"},
    "oled":       {"name": "OLED-sort", "desc": "Helt svart – sparer strøm på OLED-skjermer", "dark": True,
                   "a": "#8ab4ff", "b": "#c58aff", "c": "#7ff0e0",
                   "bg": "#000000", "side": "#000000", "card": "#0b0b0f", "fg": "#f2f2f5", "dim": "#8d8d99"},
    "ametyst":    {"name": "Ametyst", "desc": "Dyp lilla krystall", "dark": True,
                   "a": "#b388ff", "b": "#7c4dff", "c": "#ea80fc",
                   "bg": "#0f0a18", "side": "#140d20", "card": "#1c1430", "fg": "#f1eaff", "dim": "#a597c2"},
    "smaragd":    {"name": "Smaragd og gull", "desc": "Mørkegrønt med gylne detaljer", "dark": True,
                   "a": "#2ecc8f", "b": "#e8c35a", "c": "#1fa3a3",
                   "bg": "#06110d", "side": "#081610", "card": "#0e2019", "fg": "#ecfaf3", "dim": "#93b3a5"},
    "koralrev":   {"name": "Koralrev", "desc": "Korall og turkis under vann", "dark": True,
                   "a": "#ff7a6b", "b": "#1fd1c1", "c": "#ffc46b",
                   "bg": "#071216", "side": "#09181d", "card": "#0f2228", "fg": "#ebfbfa", "dim": "#91b3b2"},
    "midnatt":    {"name": "Midnattsblå", "desc": "Marineblått og sølv – rolig og stilrent", "dark": True,
                   "a": "#7aa7ff", "b": "#c0cad8", "c": "#5cc8ff",
                   "bg": "#0a0f1c", "side": "#0d1324", "card": "#131b30", "fg": "#eaf0fb", "dim": "#93a0b8"},
    "tokyo":      {"name": "Tokyo Night", "desc": "Det populære fargesettet fra kodeverdenen", "dark": True,
                   "a": "#7aa2f7", "b": "#bb9af7", "c": "#7dcfff",
                   "bg": "#1a1b26", "side": "#16161e", "card": "#24283b", "fg": "#c0caf5", "dim": "#7f88b0"},
    "dracula":    {"name": "Dracula", "desc": "Lilla og rosa på mørkegrått", "dark": True,
                   "a": "#bd93f9", "b": "#ff79c6", "c": "#50fa7b",
                   "bg": "#282a36", "side": "#21222c", "card": "#343746", "fg": "#f8f8f2", "dim": "#a3a8c3"},
    "nord":       {"name": "Nord", "desc": "Kjølig, arktisk og dempet", "dark": True,
                   "a": "#88c0d0", "b": "#81a1c1", "c": "#a3be8c",
                   "bg": "#2e3440", "side": "#2a2f3a", "card": "#3b4252", "fg": "#eceff4", "dim": "#a6aebf"},
    "gruvbox":    {"name": "Gruvbox", "desc": "Varme retrofarger", "dark": True,
                   "a": "#fabd2f", "b": "#fe8019", "c": "#b8bb26",
                   "bg": "#282828", "side": "#1d2021", "card": "#32302f", "fg": "#ebdbb2", "dim": "#a89984"},
    "catppuccin": {"name": "Catppuccin", "desc": "Myke pastellfarger på mørkt (Mocha)", "dark": True,
                   "a": "#cba6f7", "b": "#f5c2e7", "c": "#94e2d5",
                   "bg": "#1e1e2e", "side": "#181825", "card": "#313244", "fg": "#cdd6f4", "dim": "#9399b2"},
    "rosepine":   {"name": "Rosé Pine", "desc": "Rosa og lavendel – lunt og mørkt", "dark": True,
                   "a": "#ebbcba", "b": "#c4a7e7", "c": "#9ccfd8",
                   "bg": "#191724", "side": "#1f1d2e", "card": "#26233a", "fg": "#e0def4", "dim": "#908caa"},
    "sand":       {"name": "Sand", "desc": "Lyst beige og terrakotta", "dark": False,
                   "a": "#d9733b", "b": "#c2a06b", "c": "#e8b04d",
                   "bg": "#faf5ee", "side": "#f3ebdf", "card": "#ffffff", "fg": "#2d2218", "dim": "#8a7765"},
    "mint":       {"name": "Mint", "desc": "Friskt, lyst og grønt", "dark": False,
                   "a": "#14b38a", "b": "#2dbfd6", "c": "#8fe3c5",
                   "bg": "#f1fbf7", "side": "#e6f6f0", "card": "#ffffff", "fg": "#10291f", "dim": "#5e7d71"},
    "papir":      {"name": "Papir", "desc": "Rent og lyst med blå detaljer", "dark": False,
                   "a": "#3367d6", "b": "#6b8ef0", "c": "#9db4ff",
                   "bg": "#f7f7f5", "side": "#efefec", "card": "#ffffff", "fg": "#1d1f24", "dim": "#6b6f78"},
    "latte":      {"name": "Catppuccin Latte", "desc": "Myke pastellfarger på lyst", "dark": False,
                   "a": "#8839ef", "b": "#ea76cb", "c": "#179299",
                   "bg": "#eff1f5", "side": "#e6e9ef", "card": "#ffffff", "fg": "#4c4f69", "dim": "#7c7f93"},
    "sakura":     {"name": "Kirsebærblomst", "desc": "Lyst, rosa og lavendel", "dark": False,
                   "a": "#ff6fa3", "b": "#a97bff", "c": "#ffb3c7",
                   "bg": "#fff5f8", "side": "#ffecf3", "card": "#ffffff", "fg": "#2a1a22", "dim": "#8a6a78"},
    "arktis":     {"name": "Arktis", "desc": "Lyst og iskaldt blått", "dark": False,
                   "a": "#2f9bff", "b": "#29d3e8", "c": "#8fb8ff",
                   "bg": "#f0f6fb", "side": "#e6f0f8", "card": "#ffffff", "fg": "#102330", "dim": "#5d7486"},
}
_BASE = {"#5b8cff": "a", "#8a5cff": "b", "#9a6bff": "b", "#00c8b4": "c"}


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _mix(x, y):
    a, b = _rgb(x), _rgb(y)
    return "#%02x%02x%02x" % tuple((i + j) // 2 for i, j in zip(a, b))


def _t(x):
    """Navn eller ferdig tema-dict -> dict."""
    if isinstance(x, dict):
        return x
    return THEMES.get(x or current_theme(), THEMES["standard"])


DARK_DEFAULT = {"bg": "#0f1016", "side": "#14151d", "card": "#191a23", "fg": "#f3f3f7", "dim": "#9a9bab"}


def blend(x, y, f):
    """Tema midt mellom x og y (f = 0 … 1) – til myke overganger."""
    ta, tb = dict(DARK_DEFAULT, **_t(x)), dict(DARK_DEFAULT, **_t(y))
    out = {"name": "", "desc": "", "dark": tb["dark"] if f >= 0.5 else ta["dark"]}
    if out["dark"] is None:
        out["dark"] = True
    for k in ("a", "b", "c", "bg", "side", "card", "fg", "dim"):
        a, b = _rgb(ta[k]), _rgb(tb[k])
        out[k] = "#%02x%02x%02x" % tuple(round(i + (j - i) * f) for i, j in zip(a, b))
    return out


def _lum(h):
    r, g, b = (v / 255 for v in _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _shade(h, f):
    """Mørkere (f<0) eller lysere (f>0) variant av en farge."""
    r = _rgb(h)
    if f < 0:
        return "#%02x%02x%02x" % tuple(round(v * (1 + f)) for v in r)
    return "#%02x%02x%02x" % tuple(round(v + (255 - v) * f) for v in r)


def make_custom(a, b, dark=True):
    """Eget tema av to farger: flatene blandes av fargene, mørkt eller lyst."""
    m = _mix(a, b)
    if dark:
        bg = _shade(m, -0.90)
        return {"name": "Eget", "desc": "Dine egne farger", "dark": True, "a": a, "b": b, "c": _shade(m, 0.35),
                "bg": bg, "side": _shade(m, -0.86), "card": _shade(m, -0.80), "fg": "#f4f4f8", "dim": "#a3a3b5"}
    return {"name": "Eget", "desc": "Dine egne farger", "dark": False, "a": a, "b": b, "c": _shade(m, 0.4),
            "bg": _shade(m, 0.94), "side": _shade(m, 0.90), "card": "#ffffff", "fg": "#17181f", "dim": "#666878"}


def _load_custom():
    try:
        c = json.load(open(LOOK)).get("custom")
    except (OSError, ValueError):
        c = None
    if c and c.get("a") and c.get("b"):
        THEMES["eget"] = make_custom(c["a"], c["b"], c.get("dark", True))


def current_theme():
    try:
        t = json.load(open(LOOK)).get("theme", "standard")
    except (OSError, ValueError):
        t = "standard"
    return t if t in THEMES else "standard"


def recolor(css, name=None):
    """Bytt standardfargene i et stilark med temaets farger."""
    t = _t(name)
    if t is THEMES["standard"]:
        return css
    for hx, k in _BASE.items():
        css = css.replace(hx, t[k])
    return css.replace("#6a7bff", _mix(t["a"], t["b"]))


def theme_css(name=None):
    """Ekstra stilark for temaet: flater, tekst og en bakgrunn med glød i temaets farger."""
    t = _t(name)
    if "bg" not in t:
        return ""
    mid = _mix(t["a"], t["b"])
    dark = t["dark"]
    return f"""
:root {{
  --window-bg-color: {t['bg']}; --window-fg-color: {t['fg']};
  --view-bg-color: {t['bg']}; --view-fg-color: {t['fg']};
  --headerbar-bg-color: {t['side']}; --headerbar-fg-color: {t['fg']};
  --sidebar-bg-color: {t['side']}; --sidebar-fg-color: {t['fg']};
  --secondary-sidebar-bg-color: {t['side']};
  --card-bg-color: {t['card']}; --card-fg-color: {t['fg']};
  --popover-bg-color: {t['card']}; --popover-fg-color: {t['fg']};
  --dialog-bg-color: {t['card']}; --dialog-fg-color: {t['fg']};
  --accent-bg-color: {mid}; --accent-color: {t['a']}; --accent-fg-color: {'#111' if not dark else 'white'};
}}
window.sysmon, window.background {{ background-color: {t['bg']}; color: {t['fg']}; }}
.dim-label, .ks-sub, .ks-hello-sub {{ color: alpha({t['dim']}, 1); opacity: 1; }}
.ks-content {{
  background-image: radial-gradient(ellipse 60% 42% at 8% 0%, alpha({t['a']}, {0.20 if dark else 0.14}), transparent),
                    radial-gradient(ellipse 50% 40% at 100% 8%, alpha({t['b']}, {0.18 if dark else 0.12}), transparent),
                    radial-gradient(ellipse 70% 40% at 50% 100%, alpha({t['c']}, 0.10), transparent);
}}
.ks-side {{ background-color: {t['side']};
  background-image: radial-gradient(circle farthest-side at 0% 0%, alpha({t['a']}, 0.16), transparent); }}
.ks-brand-logo {{ background-image: linear-gradient(135deg, {t['a']}, {t['b']}); }}
"""


def web_css():
    """Samme temaer for appen (remote_web/themes.css og startskjermen i APK-en)."""
    out = ["/* Laget av theme.web_css() – ikke rediger for hånd. */",
           ":root { --ga: #5b8cff; --gb: #8a5cff; --gc: #00c8b4; }"]
    for key, t in THEMES.items():
        if key == "standard":
            continue
        ra, rb, rc = _rgb(t["a"]), _rgb(t["b"]), _rgb(t["c"])
        dark = t["dark"]
        line = "rgba(255,255,255,.075)" if dark else "rgba(20,24,60,.08)"
        hi = "rgba(255,255,255,.06)" if dark else "rgba(255,255,255,.9)"
        card = (f"rgba({','.join(map(str, _rgb(t['card'])))},.62)" if dark
                else "rgba(255,255,255,.80)")
        out.append(
            f':root[data-ks="{key}"][data-ks] {{ --bg: {t["bg"]}; --bg2: {t["side"]}e0; --card: {card}; '
            f'--card-solid: {t["card"]}; --card2: {"rgba(255,255,255,.07)" if dark else "rgba(20,24,60,.055)"}; '
            f'--fg: {t["fg"]}; --dim: {t["dim"]}; --line: {line}; --hi: {hi}; '
            f'--ga: {t["a"]}; --gb: {t["b"]}; --gc: {t["c"]}; --acc: {t["a"]}; --acc2: {t["b"]}; --c1: {t["a"]}; '
            f'--grad: linear-gradient(135deg, {t["a"]} 0%, {t["b"]} 100%); '
            f'--aurora: radial-gradient(60% 45% at 8% -5%, rgba({ra[0]},{ra[1]},{ra[2]},{.34 if dark else .22}), transparent 70%), '
            f'radial-gradient(50% 40% at 100% 0%, rgba({rb[0]},{rb[1]},{rb[2]},{.30 if dark else .18}), transparent 70%), '
            f'radial-gradient(70% 50% at 50% 115%, rgba({rc[0]},{rc[1]},{rc[2]},.16), transparent 70%); '
            f'color-scheme: {"dark" if dark else "light"}; }}')
    return "\n".join(out) + "\n"



def write_web_themes():
    """Skriv themes.css og themes.js til mobilappen (remote_web) og startskjermen i APK-en."""
    import json as _j
    here = os.path.dirname(os.path.abspath(__file__))
    css = web_css()
    rows = []
    for k, t in THEMES.items():
        rows.append({"k": k, "name": t["name"], "desc": t["desc"], "a": t["a"], "b": t["b"], "c": t["c"],
                     "bg": t.get("bg", "#121320"), "card": t.get("card", "#1c1d2b"), "fg": t.get("fg", "#f3f3f7"),
                     "dark": t.get("dark")})
    js = "// Laget av theme.py – ikke rediger for hånd.\nwindow.KS_THEMES = " + _j.dumps(rows, ensure_ascii=False) + ";\n"
    for d in (os.path.join(here, "remote_web"), os.path.join(here, "android", "app", "src", "main", "assets")):
        if os.path.isdir(d):
            with open(os.path.join(d, "themes.css"), "w", encoding="utf-8") as f:
                f.write(css)
            with open(os.path.join(d, "themes.js"), "w", encoding="utf-8") as f:
                f.write(js)
    return len(rows)


def daily_theme(date=None):
    """«Nytt tema hver dag»: samme tema hele dagen, nytt i morgen (mørke eller lyse etter valg)."""
    import random
    lk = look()
    want_dark = lk.get("daily_dark", True)
    keys = [k for k, t in THEMES.items() if k != "standard" and (t.get("dark") is not False) == bool(want_dark)]
    return random.Random(date or time.strftime("%Y-%m-%d")).choice(keys) if keys else "standard"


def _save_look(**kw):
    try:
        d = json.load(open(LOOK))
    except (OSError, ValueError):
        d = {}
    d.update(kw)
    os.makedirs(os.path.dirname(LOOK), exist_ok=True)
    json.dump(d, open(LOOK, "w"))


def glass_on():
    try:
        return bool(json.load(open(LOOK)).get("glass", True))
    except (OSError, ValueError):
        return True


def set_glass(on, window=None):
    _save_look(glass=bool(on))
    for w in ([window] if window else Gtk.Window.list_toplevels()):
        if w is not None:
            (w.add_css_class if on else w.remove_css_class)("ks-glass")


_LOADED = False


SWATCH_CSS = """
togglebutton.ks-swatch, window.ks-glass togglebutton.ks-swatch { padding: 8px; border-radius: 18px;
  background-image: none; background-color: transparent; box-shadow: none; }
togglebutton.ks-swatch:hover, window.ks-glass togglebutton.ks-swatch:hover { background-color: alpha(currentColor, 0.06); }
togglebutton.ks-swatch:checked, window.ks-glass togglebutton.ks-swatch:checked,
window.ks-glass .linked > togglebutton.ks-swatch:checked {
  background-image: none; background-color: alpha(#8a5cff, 0.16); color: inherit;
  box-shadow: inset 0 0 0 2px #8a5cff, 0 10px 24px -12px alpha(#8a5cff, 0.9); }
"""
_SHEETS = []          # [(css, prioritet, provider)] – lastes på nytt når temaet byttes


def _provider(css):
    p = Gtk.CssProvider()
    p.load_from_string(css) if hasattr(p, "load_from_string") else p.load_from_data(css.encode(), -1)
    return p


def add_css(css, priority=Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION):
    """Legg inn et stilark som følger temaet (fargene byttes når du velger et annet tema)."""
    p = _provider(recolor(css))
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), p, priority)
    _SHEETS.append([css, priority, p])
    return p


def _scheme(name):
    try:
        from gi.repository import Adw
        dark = THEMES.get(name, {}).get("dark")
        Adw.StyleManager.get_default().set_color_scheme(
            Adw.ColorScheme.DEFAULT if dark is None else
            Adw.ColorScheme.FORCE_DARK if dark else Adw.ColorScheme.FORCE_LIGHT)
    except Exception:  # noqa: BLE001
        pass


def load():
    """Legg inn designet for hele programmet (én gang)."""
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    _load_custom()
    add_css(CSS)
    add_css(GLASS_CSS, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
    add_css(GLOW_CSS, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 2)
    _THEME[0] = _provider(theme_css())
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), _THEME[0],
                                              Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 4)
    add_css(SWATCH_CSS, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 5)
    _scheme(current_theme())


_THEME = [None]


_SHOWN = [None]


def show(t):
    """Vis et tema (navn eller dict) uten å lagre det – brukt av spill, tid på døgnet og overganger."""
    disp = Gdk.Display.get_default()
    for sh in _SHEETS:
        Gtk.StyleContext.remove_provider_for_display(disp, sh[2])
        sh[2] = _provider(recolor(sh[0], t))
        Gtk.StyleContext.add_provider_for_display(disp, sh[2], sh[1])
    if _THEME[0] is not None:
        Gtk.StyleContext.remove_provider_for_display(disp, _THEME[0])
    _THEME[0] = _provider(theme_css(t))
    Gtk.StyleContext.add_provider_for_display(disp, _THEME[0], Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 4)
    td = _t(t)
    try:
        from gi.repository import Adw
        dark = td.get("dark")
        Adw.StyleManager.get_default().set_color_scheme(
            Adw.ColorScheme.DEFAULT if dark is None else
            Adw.ColorScheme.FORCE_DARK if dark else Adw.ColorScheme.FORCE_LIGHT)
    except Exception:  # noqa: BLE001
        pass
    _SHOWN[0] = t


def set_theme(name):
    """Bytt tema med en gang i hele programmet, og husk valget."""
    if name not in THEMES:
        return
    tried = list(dict.fromkeys((look().get("themes_tried") or []) + [name]))
    _save_look(theme=name, themes_tried=tried)
    show(name)
    try:
        import looks
        looks._STATE["last"] = name
    except Exception:  # noqa: BLE001
        pass
    for cb in list(_LISTENERS):
        try:
            cb(name)
        except Exception:  # noqa: BLE001
            pass


def look():
    try:
        return json.load(open(LOOK))
    except (OSError, ValueError):
        return {}


_LISTENERS = []


# Sidemenyens seksjoner: fane -> seksjon (rekkefølgen her er rekkefølgen i menyen)
SECTIONS = [
    ("Overvåking", ["oversikt", "historikk"]),
    ("Enheter", ["gpu", "rgb", "logitech", "cpuskjerm", "lyd", "bluetooth", "wifi", "msi"]),
    ("Spill", ["spill", "vr", "discord", "stromming"]),
    ("Hjemmet", ["scener", "smarthjem", "familie", "chat", "hjemme", "venner"]),
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
    "discord": "Mikrofon, lyd av og forlat samtalen med ett trykk – og volum, mikrofon, høyttalere, støydemping, "
               "ekkodemping og overlay for Discord.",
    "venner": "Vennenes PC-er utenfor hjemmet – hva de spiller, temperaturer, CPU og minne (over Tailscale).",
    "chat": "Chat med alle som har Kontrollsenter: de hjemme, vennene dine, og privat med hver enkelt.",
    "vr": "Meta Quest 3 gjennom Steam og SteamVR – trådløst eller med kabel. Kontrollsenter installerer og retter alt.",
    "stromming": "Spill og se PC-skjermen på telefonen (Sunshine + Moonlight), og fjernhjelp med RustDesk.",
    "familie": "Familiekontroll med kode, «Se på» skjermen til de andre PC-ene, familie-chat, «Middag!», "
               "ekstra spilletid og leggetid.",
    "nettverk": "Hastighet, ping, hvilke programmer som bruker nettet, og enhetene på hjemmenettet.",
    "programmer": "Installer, oppdater og velg hvilke programmer som starter med PC-en.",
    "smarthjem": "Alle smartenhetene på hjemmenettet: styr Hue-lys, Samsung-TV og Chromecast/Nest, og se alt annet som er koblet til.",
    "scener": "Én knapp setter hele rommet og PC-en: strømmodus, vifter, RGB, Hue-lys, TV, lyd, tema og varsler – "
              "også automatisk når et spill starter eller på et klokkeslett.",
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
