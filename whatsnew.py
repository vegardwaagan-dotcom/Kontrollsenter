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
    ("0.9.2", "Appen finner PC-ene også med VPN på", [
        ("Rettet", [
            "Android-appen fant ikke PC-ene når telefonen hadde VPN på (f.eks. Tailscale): den søkte i VPN-nettet. "
            "Nå brukes alltid Wi-Fi-nettet, og de vanlige hjemmenettene (192.168.1.x og 192.168.0.x) søkes også",
        ]),
    ]),
    ("0.9.1", "Appen finner Windows-PC-er", [
        ("Rettet", [
            "Windows: Android-appen fant ikke PC-en når Windows-brannmuren blokkerte Kontrollsenter (f.eks. etter at "
            "«Tillat»-spørsmålet ble lukket). Ny knapp «Rett brannmuren» i PC-er hjemme → Mobil og nettbrett, og "
            "installasjonsfilen retter det selv",
            "Feilsøkingsrapporten fra Windows viser fjernstyring, nettverksprofil og brannmurregler",
        ]),
    ]),
    ("0.9.0", "26 nye funksjoner i Android-appen", [
        ("Varsler og overvåking", [
            "Varsler på mobilen/nettbrettet fra PC-ene: varm CPU/GPU, vifte stoppet, full disk, spilletid nådd, "
            "ferdig spilløkt – også når appen er lukket (sjekkes hvert 15. minutt)",
            "Varsel hvis en PC slutter å svare uten å ha blitt slått av (strømbrudd eller krasj)",
            "Tidslinje over alt som har skjedd, og helsekort (A–F) med «Åpne Systemsjekk på PC-en»",
            "Widget på hjemmeskjermen og hurtigfliser for strømmodus og spillmodus",
        ]),
        ("Spill", [
            "Spillmodus med én knapp: max ytelse, viftekurve, RGB-farge, overlay på og varsler av – og tilbake",
            "Andreskjerm: store tall på nettbrettet mens du spiller (starter av seg selv, skjermen holdes våken)",
            "Spilletid per dag og uke, med grense og varsel (f.eks. for William)",
            "CS2 kamp for kamp: K/D og headshot over tid, og seier/K/D per kart",
            "WoW-mål: «level 20 innen søndag» med anslått spilletid",
            "Start spill på riktig PC: alle spillene fra alle PC-ene, med hvem som er ledig",
        ]),
        ("Fjernkontroll", [
            "Slå på PC-en fra appen (Wake-on-LAN) – også borte via en annen PC",
            "Alle PC-ene på én skjerm med temperatur, watt og spill",
            "Media (spill/pause/neste) og volum per program",
            "Send lenker og tekst til PC-en, også med «Del» fra andre apper, og hent PC-ens utklippstavle",
            "Skjermbilde av PC-en, og avslutt programmer som har hengt seg",
            "Slå av om 30 min / 1 t / 2 t eller når nedlastingene er ferdige",
            "Ping til ruter, NAS, Steam og Battle.net, og hvilke programmer som bruker nettet",
            "Strømkostnad i kroner per dag, uke og måned",
            "NAS-plass og sikkerhetskopi av lagrede spill",
        ]),
        ("Appen", [
            "Fingeravtrykk før «Slå av», «Start på nytt», vifter og «Avslutt»",
            "Begrenset tilgang per enhet (se alt og start spill, men ikke slå av eller endre innstillinger)",
            "Tema: auto, lyst, mørkt og AMOLED – og enkel visning med store fliser",
            "Engelsk språk i appen",
        ]),
    ]),
    ("0.8.5", "WoW-addonen bruker ikke kamploggen", [
        ("Rettet", [
            "WoW ba fortsatt om å slå av addonen: den lyttet på kamploggen, som er låst for addons i nyere WoW. "
            "Kills telles nå fra «… dies, you gain … experience», og «drept av» er fienden du hadde valgt",
            "Hvis WoW likevel blokkerer noe, lagrer addonen hva – og Spillstatistikk viser det",
        ]),
    ]),
    ("0.8.4", "WoW-addonen uten «disable/ignore»", [
        ("Rettet", [
            "WoW spurte om å slå av addonen etter /reload: den ba om /played, som er låst for addons i nyere "
            "WoW. Nå lytter den bare på spilletiden WoW sender selv, og regner videre mellom svarene",
        ]),
    ]),
    ("0.8.3", "WoW-addonen uten «blocked»-melding", [
        ("Rettet", [
            "WoW: «KontrollsenterStats has been blocked from an action only available to the Blizzard UI». Addonen "
            "byttet ut en Blizzard-funksjon for å skjule /played i chatten – nå dempes chatten bare et øyeblikk "
            "i stedet, og ingen Blizzard-funksjoner endres",
        ]),
    ]),
    ("0.8.2", "WoW-statistikk: hva mangler?", [
        ("Rettet", [
            "Spillstatistikk sier nå hvorfor WoW-tallene ikke vises ennå – f.eks. at WoW må startes helt på nytt "
            "etter at addonen ble lagt inn, eller at tallene kommer etter utlogging eller /reload",
        ]),
    ]),
    ("0.8.1", "App-oppdatering på Samsung", [
        ("Rettet", [
            "«Oppdater» i Android-appen feilet med «self update is blocked by unknown source package» på nyere "
            "Android/Samsung. Da åpnes nedlastingen i nettleseren i stedet – trykk på filen og velg Oppdater",
        ]),
    ]),
    ("0.8.0", "Spillstatistikk og appen utenfor hjemmenettet", [
        ("Spillstatistikk", [
            "CS2 live mens du spiller: stilling, kills, dødsfall, assists, headshots (%), skade, ADR, MVP, liv, "
            "penger og våpen – i Spill-fanen og øverst i appen",
            "CS2 totalt: K/D, headshot-prosent, treffsikkerhet, seiersrate, MVP, favorittvåpen, siste kamp og "
            "treff per våpen",
            "World of Warcraft per karakter (addonen «Kontrollsenter Stats» legges inn automatisk): spilletid totalt "
            "og per level, distanse (gått, ridd, svømt, flytaxi), kills og hva du dreper mest, dødsfall og hvem som "
            "drepte deg, quests, XP, gull, skade, største treff, healing, hopp, soner og siste økt. /ks viser dem i spillet",
            "Steam: spilletid, prestasjoner og all statistikk spillene lagrer – for hver Steam-konto på PC-en",
        ]),
        ("Android-appen", [
            "Virker utenfor hjemmenettet med Tailscale (privat og kryptert) – slå det på i PC-er hjemme → Mobil og "
            "nettbrett, og bruk samme konto i Tailscale-appen på mobilen/nettbrettet",
            "Samme paring hjemme og ute – appen velger adressen som svarer",
        ]),
    ]),
    ("0.7.2", "Oppdateringer i Android-appen", [
        ("Nytt", [
            "Android-appen sier fra når en ny versjon ligger på NAS-en – banner i appen, og varsel på telefonen/"
            "nettbrettet også når appen er lukket",
            "«Oppdater nå» laster ned og installerer den nye appen via PC-en (Android godtar bare en app med "
            "samme signatur)",
            "«Se etter oppdatering» på startsiden og i System-fanen",
        ]),
    ]),
    ("0.7.1", "Android-appen kobler til", [
        ("Rettet", [
            "Appen viste «error: finnes ikke» når du trykket «Åpne»: oppdateringen fra en eldre versjon tok ikke "
            "med kontrollpanelet. Nå kopieres hele pakken ved oppdatering, og filer som mangler hentes fra "
            "NAS-en ved oppstart",
            "Android-prosjektet kan åpnes og kjøres i Android Studio",
        ]),
    ]),
    ("0.7.0", "Android-app for mobil og nettbrett", [
        ("Nytt", [
            "Android-appen «Kontrollsenter» – styr PC-ene fra mobilen eller nettbrettet (laget også for store "
            "nettbrett som Galaxy Tab S11 Ultra)",
            "Oversikt med CPU, GPU, minne, temperaturer, strøm, disk og nett – oppdateres hvert 2. sekund",
            "Kontroll: strømmodus, vifter, lyd, RGB-lys, spill-overlay og MSI-innstillinger",
            "Historikk for siste time, døgn og uke, og start Steam-spill rett fra nettbrettet",
            "System: lås skjermen, hvilemodus, start på nytt og slå av",
            "Appen finner PC-ene på hjemmenettet selv. Slå på «Tillat fjernstyring» i PC-er hjemme og par "
            "med en 6-sifret kode",
        ]),
    ]),
    ("0.6.5", "Riktige temperaturer", [
        ("Rettet", [
            "Grenseverdier ble vist som temperaturer – f.eks. RAM-ens «Critical High Limit» (85 °C) ga rødt "
            "varsel, og «Distance to TjMax» så ut som CPU-temperatur. Nå vises bare ekte målinger",
            "Frakoblede sensorer på hovedkortet (0 °C, −62 °C) skjules",
        ]),
    ]),
    ("0.6.4", "Gjennomgang av Linux og Windows", [
        ("Rettet", [
            "Windows: utskrift fra Windows-verktøy (strømplan, Wi-Fi, ping, PowerShell) med æøå gikk tapt – "
            "tegnkoden leses nå riktig",
            "Historikken mistet målinger («database is locked») når to Kontrollsenter-prosesser kjørte samtidig",
            "Feilmeldinger uten tekst («Feil:») sier nå hva som skjedde",
            "Windows-installasjonen prøver OpenRGB på flere måter",
            "Linux-installasjonen spør ikke om passord når ingenting mangler",
        ]),
    ]),
    ("0.6.3", "OpenRGB på Windows", [
        ("Rettet", [
            "Installasjonsfilen fant ikke OpenRGB (pakken har fått nytt navn i winget) – nå installeres den",
        ]),
    ]),
    ("0.6.2", "Rolig installasjon på Windows", [
        ("Rettet", [
            "Installasjonsfilen viser ikke lenger et PowerShell-vindu – fremdriften vises i installasjonsvinduet",
            "MSI-styringen på Windows kjører helt uten vindu, også når den trenger administratorrett",
        ]),
    ]),
    ("0.6.1", "MSI-innstillinger på Windows", [
        ("Nytt", [
            "MSI på Windows: brukerscenario, Cooler Boost, viftemodus, Battery Master (ladegrense), Super Battery "
            "og webkamera styres nå direkte fra Kontrollsenter – uten MSI Center",
            "MSI-fanen viser CPU- og GPU-temperatur og viftefart rett fra MSI-kontrolleren",
        ]),
        ("Rettet", [
            "Windows nektet å starte Kontrollsenter-Setup.exe fra NAS-en («ingen tilgang») – filene får nå kjørerett",
        ]),
    ]),
    ("0.6.0", "Alle funksjonene på Windows", [
        ("Nytt på Windows", [
            "Vifter – styr viftene via LibreHardwareMonitor, med vifteprofiler og egne kurver",
            "RGB – OpenRGB finnes og startes automatisk, og installeres av installasjonsfilen",
            "Lyd – volum og demping for høyttalere og mikrofon, og volum per program",
            "Logitech – se Logitech-utstyret ditt og åpne eller installer G HUB",
            "MSI – maskin- og BIOS-info, batteri og snarvei til MSI Center",
            "Bluetooth og Wi-Fi – tilkoblede enheter, nettverk og signalstyrke",
            "Programmer – installer populære programmer og oppdater alle med winget, og velg hva som starter "
            "ved innlogging",
            "Spill – Steam-spillene dine med startvalg, og spillprofiler når et spill kjører",
            "Nettverk – ping, ruter og hvilke programmer som bruker nettet",
            "Verktøy – systeminfo til forum, «Rydd opp» (papirkurv, Temp, shader-cache), diskhelse, "
            "gjenopprettingspunkt og «Hva tar plass?»",
            "Systemsjekk – LibreHardwareMonitor, diskplass, programoppdateringer og Windows Update",
        ]),
    ]),
    ("0.5.3", "Windows: raskere og CPU-temperatur", [
        ("Rettet", [
            "Windows: vinduet hakket fordi det ventet på LibreHardwareMonitor og strømplanen hvert sekund – "
            "nå leses de i bakgrunnen",
            "LibreHardwareMonitor starter ved innlogging med ikon i statusfeltet, og Kontrollsenter starter den selv "
            "hvis den ikke svarer",
            "æøå i filer og rapporter på Windows",
        ]),
    ]),
    ("0.5.2", "Windows starter", [
        ("Rettet", [
            "Windows: programmet krasjet ved oppstart fordi Windows mangler lastsnitt (getloadavg) og statvfs",
            "Hvis noe likevel feiler ved oppstart, vises feilen i en melding og legges på NAS-en (Diagnose)",
        ]),
    ]),
    ("0.5.1", "Windows: NAS-adresse", [
        ("Rettet", [
            "Windows når NAS-en med navnet (\\\\PERSONALCLOUD) når IP-adressen avvises med «Brukernavnet eller "
            "passordet er feil» – gjelder installasjon, oppdateringer, PC-er hjemme og feilsøkingsrapport",
        ]),
    ]),
    ("0.5.0", "Kontrollsenter for Windows 11", [
        ("Windows 11 (første runde)", [
            "Installer fra NAS-en: åpne \\\\192.168.1.3\\Public\\Kontrollsenter\\Windows og dobbeltklikk "
            "«Installer Kontrollsenter»",
            "Oversikt med temperaturer, last, strøm og grafer (via LibreHardwareMonitor), historikk og PC-er hjemme",
            "Strømmodus bytter Windows-strømplan (Strømsparing, Balansert, Høy ytelse)",
            "Ikon i systemstatusfeltet, Windows-varsler og oppstart ved innlogging",
            "Oppdateringer fra NAS-en og feilsøkingsrapport – som på Linux",
            "Vifter, RGB, spill, nettverk, lyd, Bluetooth, Wi-Fi og programmer kommer i de neste rundene",
        ]),
    ]),
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
