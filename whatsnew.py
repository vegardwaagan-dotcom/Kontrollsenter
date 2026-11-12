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
    ("0.4.2", "RGB og Logitech på flere PC-er", [
        ("Rettet", [
            "RGB virket ikke med OpenRGB 1.x: Effects-tillegget fikk tilkoblingen til å feile uten feilmelding",
            "Feilmeldinger i RGB-fanen sier nå hva som er galt i stedet for bare «Feil:»",
            "Logitech-fanen tilpasser seg enhetene som finnes, og viser en tydelig side når ingen har innstillinger",
        ]),
        ("Nytt", [
            "Corsair-hubber som OpenRGB ikke støtter (f.eks. iCUE COMMANDER DUO) – installer og åpne OpenLinkHub "
            "rett fra RGB-fanen",
            "Egne ikoner også i RGB-fanen",
        ]),
    ]),
    ("0.4.1", "Nytt ikon og feilsøking", [
        ("Nytt", [
            "Ny logo med lysende ring og pulslinje – på snarveien, i menyen og i Om-vinduet",
            "Eget ensfarget ikon i systemstatusfeltet som følger fargen på panelet",
            "Ikonene installeres automatisk",
            "Feilsøkingsrapport (Verktøy): maskinvare, drivere, OpenRGB, ratbagd og Solaar – legges på NAS-en "
            "så feil på andre PC-er kan finnes",
        ]),
        ("Rettet", [
            "Viftestyring på ASUS-hovedkort med Intel (f.eks. PRIME Z270): viftebrikken er sperret av BIOS – "
            "«Rett viftebrikken» legger inn oppstartsvalget som løser det",
        ]),
    ]),
    ("0.4", "Mer automatikk, mer oversikt", [
        ("Spill", [
            "Automatiske spillprofiler: strømmodus, vifter og RGB byttes når et Steam-spill starter – og tilbake "
            "når det avsluttes. Egne innstillinger per spill",
            "Rapport etter hver spilløkt: spilletid, snitt-FPS, «1 % low», høyeste temperaturer og strømkostnad",
            "Sikkerhetskopi av lagrede spill til NAS-en – også spill som ikke ligger i Steam Cloud – og henting tilbake",
        ]),
        ("Vifter og strøm", [
            "Viftekurver: dra punkter på en graf, så følger viftene temperaturen",
            "Stille om natten: rolig PC i tidsrommet du velger, med stille vifter, Strømsparing og RGB av",
            "Strømforbruk med pris: målt watt for CPU og skjermkort, kWh og kroner i dag, og anslag per måned",
        ]),
        ("Oversikt og system", [
            "Historikk: temperaturer, last og strøm for siste time, døgn eller uke",
            "Hva tar plass? De største mappene og spillene, med Åpne og Avinstaller",
            "Nettverk: ping til ruter, NAS og spilltjenere, hastighetstest og programmer som bruker nettet",
            "PC-er hjemme: se temperatur, strøm, spill og versjon på alle PC-ene på hjemmenettet",
        ]),
        ("Utseende", [
            "Eget programikon",
            "Nøkkeltall øverst i Oversikt med runde temperaturmål i grønt, gult og rødt",
            "Grafer: velg 1 min, 10 min eller 1 time, og hold musa over for verdi og tidspunkt",
            "Mini-vindu som ligger øverst med temperaturer og strøm (Meny → Mini-vindu)",
            "Levende sidemeny: temperatur ved Oversikt, ▶ ved Spill når et spill kjører, antall Bluetooth-enheter",
            "Velkomstveiviser første gang (og i Meny → Velkomstveiviser)",
        ]),
    ]),
    ("0.3.1", "Riktig versjon etter oppdatering", [
        ("Rettet", [
            "«Se etter oppdatering» sammenligner nå med versjonen som faktisk kjører – ikke bare filene på disken",
            "Kjører Kontrollsenter i bakgrunnen når en ny versjon installeres, kommer et varsel og et banner "
            "med «Start på nytt»",
            "«Start på nytt»-knapp i Verktøy etter oppdatering",
        ]),
    ]),
    ("0.3", "Enkelt og elegant", [
        ("Nytt utseende", [
            "Sidemeny til venstre i stedet for fanerad – roligere, og plass til flere sider",
            "Meny (☰) med Systemsjekk, Hva er nytt?, Språk og Om Kontrollsenter",
            "Om-vindu med versjon, copyright og nyheter – copyright-linjen øverst er borte",
            "Spill-overlay er et lite ikon øverst til høyre som lyser når det er på",
            "Egne, enhetlige ikoner som passer i både lyst og mørkt tema",
        ]),
        ("Ryddigere", [
            "Vifter som står stille (0 RPM) skjules – «Vis vifter som står stille» viser dem",
            "Tilbakestill er flyttet nederst og gjort diskret",
            "Korte meldinger («Lagret ✓», «Kopiert ✓») glir opp nederst og forsvinner av seg selv",
            "Pene tomme sider når noe mangler, f.eks. ingen kontroller eller Bluetooth-enheter",
            "CPU-grafen følger systemets aksentfarge",
            "Innholdet strekkes ikke ut på brede skjermer, men holdes samlet i midten",
            "Smalt vindu: sidemenyen legger seg bort, og du blar mellom meny og side",
        ]),
    ]),
    ("0.2", "Bare det du har", [
        ("Tilpasset maskinen din", [
            "RGB, Logitech, CPU-skjerm, Wi-Fi og Bluetooth vises bare når utstyret finnes i maskinen",
            "Installasjonen legger bare inn OpenRGB, Solaar, ratbagd, TRCC og tilhørende regler når utstyret finnes",
            "Systemsjekk, Programmer og Oppstart hopper over RGB-, Logitech- og CPU-skjerm-programmer du ikke trenger",
        ]),
        ("Oppdateringer på hjemmenettet", [
            "Ser etter nye versjoner på NAS-en (\\\\192.168.1.3\\Public\\Kontrollsenter) når PC-en er på hjemmenettet",
            "Varsler om ny versjon, og oppdaterer med ett klikk – pakken sjekksum-kontrolleres og forrige versjon tas vare på",
            "Nye versjoner legges ut på NAS-en automatisk",
        ]),
    ]),
    ("0.1", "Første versjon", [
        ("Nytt navn og språk", [
            "Programmet heter nå Kontrollsenter (Control Center på engelsk)",
            "Språket følger Linux automatisk (Auto) – du kan fortsatt velge NO eller EN selv",
        ]),
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
            "Verktøy – sikkerhetskopi av alle Kontrollsenter-innstillinger til én fil, og import på en ny PC",
            "Verktøy – oppdater Kontrollsenter fra Git, og lag installasjonspakke med ett klikk",
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
