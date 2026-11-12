"""«Hva er nytt?» – innholdet vises i en dialog. Nyeste versjon øverst."""
import json
import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

import i18n  # noqa: E402

SEEN = os.path.expanduser("~/.config/systemmonitor/sett-versjon.json")

NEWS = [
    ("0.1", "Første versjon", [
        ("Nye faner", [
            "Bluetooth – søk, par og koble til hodetelefoner, kontrollere og høyttalere, og se batteriet deres",
            "Spill – startvalg per Steam-spill med avkrysning: MangoHud, GameMode, Wayland, DLSS, FSR, HDR og "
            "Proton-logg, pluss Proton-versjon per spill og egne argumenter",
            "Spill – installer nyeste GE-Proton med ett klikk (sjekksum-kontrollert), og slett gamle versjoner",
            "Spill – kontrollere med batteri og knappetest",
            "Verktøy – systeminfo med «Kopier til forum», perfekt når du ber om hjelp",
            "Verktøy – «Rydd opp»: papirkurv, Steam shader-cache, Proton-prefikser, Flatpak-rester, gamle logger "
            "og pakkecache, med størrelse på alt før noe slettes",
            "Verktøy – diskhelse (SMART): slitasje, reservekapasitet, feil og temperatur – uten passord",
            "Verktøy – gjenoppretting: gå tilbake til forrige systemversjon (Bazzite) eller ta øyeblikksbilder "
            "(snapper/Timeshift)",
            "Verktøy – sikkerhetskopi av alle Systemmonitor-innstillinger til én fil, og import på en ny PC",
            "Verktøy – oppdater Systemmonitor fra Git, og lag installasjonspakke med ett klikk",
        ]),
        ("Bakgrunn og varsler", [
            "Ikon i systemstatusfeltet med temperaturer, strømmodus, overlay og avslutt",
            "Kan kjøre i bakgrunnen når vinduet lukkes – overlay, vifter og varsler fortsetter",
            "Varsler ved høy temperatur, nesten full disk, lavt batteri i mus/hodesett/kontroller, "
            "feil i Systemsjekk og tilgjengelige oppdateringer",
            "Kan starte skjult ved innlogging (Programmer → Oppstart)",
        ]),
        ("Tryggere og raskere", [
            "Øyeblikksbilde tas automatisk før systemoppdateringer (snapper/Timeshift der det finnes)",
            "NVIDIA-data leses direkte (NVML) – over 10 ganger raskere, uten nytt program hvert sekund",
            "Feillogg i ~/.cache/systemmonitor/logg.txt – vises og kopieres fra Verktøy",
            "Koden er delt opp og lagt under versjonskontroll (Git), så endringer kan angres",
            "Fanene kan rulles sidelengs i smale vinduer",
            "Versjonsnummer under copyright, og denne «Hva er nytt?»-knappen",
        ]),
        ("Alt fra før", [
            "Oversikt: CPU, RAM, GPU, disk, nett, temperaturer, strømmodus, viftestyring, spill-overlay og batteri",
            "RGB, Logitech (som G HUB), CPU-skjerm (Thermalright), Programmer med oppstart, Lyd, Wi-Fi og MSI",
            "Systemsjekk med automatisk retting av pakke-, oppdaterings-, driver- og Wi-Fi-feil på alle distroer",
            "Norsk og engelsk, og installasjonspakke for andre PC-er",
        ]),
    ]),
]


def current_version():
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")) as f:
            return f.read().strip()
    except OSError:
        return "?"


def should_show():
    try:
        with open(SEEN) as f:
            return json.load(f).get("version") != current_version()
    except (OSError, ValueError):
        return True


def mark_seen():
    try:
        os.makedirs(os.path.dirname(SEEN), exist_ok=True)
        with open(SEEN, "w") as f:
            json.dump({"version": current_version()}, f)
    except OSError:
        pass


class WhatsNewDialog(Adw.Dialog):
    def __init__(self):
        super().__init__(title="Hva er nytt?", content_width=720, content_height=720)
        tv = Adw.ToolbarView()
        tv.add_top_bar(Adw.HeaderBar())
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(20)
        for ver, title, sections in NEWS:
            h = Gtk.Label(label=f"{i18n.tr('Versjon')} {ver} – {i18n.tr(title)}", xalign=0)
            h.add_css_class("title-2")
            box.append(h)
            for sec, items in sections:
                s = Gtk.Label(label=sec, xalign=0)
                s.add_css_class("heading")
                s.set_margin_top(6)
                box.append(s)
                for it in items:
                    row = Gtk.Box(spacing=8)
                    row.set_margin_start(8)
                    row.append(Gtk.Label(label="•", yalign=0))
                    row.append(Gtk.Label(label=it, xalign=0, wrap=True, hexpand=True))
                    box.append(row)
        sc = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        sc.set_child(box)
        tv.set_content(sc)
        self.set_child(tv)
        mark_seen()
