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
    ("0.83.0", "Servere i chatten – som Discord", [
        ("Nytt (Chat)", [
            "Lag egne servere (➕) med kategorier og kanaler – venner blir med via invitasjonslenke (🔗), eller du "
            "sender invitasjonen rett i en privat melding med «Bli med»-knapp",
            "Roller: eier 👑, admin 🛡️ og medlem – admin kan lage og endre kanaler og kaste ut; eieren kan gi bort "
            "eierskapet. Medlemmer kan forlate serveren når de vil",
            "Meldinger går direkte til alle medlemmene – serveren virker selv om eieren er av, og de som er av får "
            "meldingene når de er på igjen. Bare medlemmer kan skrive",
            "Høyreklikk på en melding: svar, reaksjoner (👍😂❤️😮🎉🔥), rediger, slett og fest",
            "Demp en kanal, medlemslisten ved siden av, og uleste per kanal",
        ]),
    ]),
    ("0.82.2", "Fjernhjelp i sidemenyen", [
        ("Nytt", [
            "🛟 Fjernhjelp har fått sin egen side i sidemenyen (under Hjemmet): RustDesk-ID-en din stort og tydelig, "
            "kopier, åpne eller installer RustDesk, og «Be om hjelp»",
            "Koble til en annen PC med ID – eller trykk «Koble til» på en PC hjemme (ID-ene deles automatisk)",
            "Andre programmer for fjernstyring (topp 5) samme sted",
            "Strømming handler nå bare om å spille på telefonen og TV-en",
        ]),
    ]),
    ("0.82.1", "Større rullehjul", [
        ("Bedre", [
            "Rullehjulet for valg er like bredt som valget du trykker på, med større tekst og høyere rader som følger "
            "størrelsen på vinduet – og lavere når det bare er noen få valg",
        ]),
    ]),
    ("0.82.0", "Chat for alle", [
        ("Nytt", [
            "💬 Chat i sidemenyen (under Hjemmet): chat med alle som har Kontrollsenter – «Hjemme» (familie-chatten), "
            "«Alle» (hjemme + vennene dine) og privat med hver PC og hver venn",
            "Vennene utenfor huset får meldingene direkte over Tailscale – bare de som står i vennelista di kan "
            "skrive til deg",
            "Er noen av, venter meldingen og sendes når de er på igjen (i opptil 3 døgn)",
            "Varsel ved ny melding (trykk for å åpne chatten), og antall uleste per samtale",
            "Mobilappen: velg «Alle» eller en privat samtale i chatten under Familie",
        ]),
    ]),
    ("0.81.0", "Utstyr+", [
        ("Nytt (Vedlikehold → Utstyr)", [
            "Batterihelse på bærbare (kapasitet mot ny) og ladegrense 80 % der maskinen støtter det",
            "Wi-Fi-signal med snitt og laveste siste uke",
            "Kontrollere: batteri (også Xbox-kontrollere på Windows) og varsel når det er lavt",
            "Skjermkalibrering: testmønstre for svartnivå, hvitnivå og gamma, med lysstyrke",
            "Gå tilbake til forrige systemversjon med de gamle driverne (Bazzite)",
            "Lyden følger hodesettet: går dit når det slås på, tilbake når det slås av",
            "Vent mens noen spiller: oppdateringskvelden, NAS-kopien og fartstesten venter til ingen spiller",
            "Ukens beste øyeblikk: video av ukas beste klipp søndag kveld, med beskjed til familien",
        ]),
        ("Spill+", [
            "Mus-DPI per spill (Logitech/Solaar) – settes når spillet starter, tilbake etterpå",
            "Spill på de andre PC-ene: se hvilke spill som finnes hjemme – Steam kan hente dem over hjemmenettet",
        ]),
    ]),
    ("0.80.0", "Hjem+: trygghet, mobil og stue", [
        ("Nytt", [
            "🥽 «Klar for VR» med ett trykk (VR-siden, søket og mobilappen): Max Ytelse, sjekk og fiks, start alt",
            "Vedlikehold → Trygghet og nett: be om hjelp (med RustDesk-ID), passordsjekk mot kjente lekkasjer "
            "(passordet forlater aldri PC-en), kamera og mikrofon i bruk, svindel-skjold (Quad9), nettverksvakt og "
            "fartstest (også hver natt)",
            "PC-er: «Send oppsettet mitt» (vifter, RGB, overlay, lyd, utseende …) til en annen PC, og «Ny PC? Hent "
            "oppsett» som også installerer de samme programmene",
            "Smart Hjem: QR-kode for gjeste-Wi-Fi, og lysene slukkes når PC-en går i dvale (Linux)",
            "Stue-modus viser også strømprisen, ukeplanen i dag og husets mest spilte",
            "Mobilappen: si eller skriv hva PC-en skal gjøre («demp lyden», «hvor varm er PC-en», «hvem spiller»)",
            "Familien-widgeten viser temperaturen på PC-ene",
        ]),
        ("Rettet", ["Varsel om ny enhet på hjemmenettet var aldri slått på – nå virker nettverksvakten"]),
    ]),
    ("0.79.0", "Spill+", [
        ("Nytt (Spill → Spillene → Spill+)", [
            "Spillkveld: hvem hjemme og blant vennene spiller hva – «Spill sammen» starter spillet, inviterer og blir "
            "med i Discord-kanalen",
            "Discord-kanal og lydprofil per spill – byttes når spillet starter (og lyden tilbake etterpå)",
            "Delte spillprofiler via NAS-en: startvalg og Proton som virker godt på en annen PC",
            "Spill-dagbok (første gang, lengste økt, timer-milepæler) og husets toppliste",
            "Ping-vakt: sier fra inni spillet når pingen blir dårlig – og om det er Wi-Fi/ruteren eller internett",
            "Lysshow: RGB og Hue blinker ved ace i CS2 og bosskill i WoW",
            "Forutsi spillkvelden («du pleier å spille nå»), og gjør klart om du vil",
            "Smart oppstart: lærer hvilke programmer du alltid åpner, og kan starte dem selv",
            "Ikke forstyrr i møter (Teams, Zoom, Webex) – varslene kommer samlet etterpå",
            "Retrospill fra RetroArch vises sammen med de andre spillene",
            "Finn beste FPS-grense (Linux) og Forvarm shadere – knapper du trykker selv",
            "Øktrapporten sammenligner FPS med snittet ditt, og sier fra om ny skjermkortdriver",
        ]),
    ]),
    ("0.78.0", "Familie+", [
        ("Nytt (Familie → Familie+)", [
            "Gjøremål fra ukeplanen kan krysses av – en voksen godkjenner, og det gir stjerner og ekstra spilletid",
            "Spillkø på én PC: hvem som står for tur, med beskjed inni spillet når tiden er ute",
            "Familiekonkurranse (stjerner + dager under spilletiden) med premie, og husprestasjoner for hele huset",
            "Leggetid som trapper ned: nattlys og varmt lys 30 min før, lavere lyd 15 min før, «lagre nå» 5 min før",
            "Pausevarsel inni spillet etter 3 timer (på som standard der familiekontroll er på)",
            "«Fri fra leksetid i dag» med ett trykk",
            "Bursdager: konfetti, bursdagsfarger på RGB og ekstra spilletid i gave",
            "Ukens oppsummering til barna søndag kveld, med en utfordring for neste uke",
        ]),
        ("Mobilappen", [
            "«Hvem er på nå»: hver PC med spill og spilletid i dag – «Gi 30 min» og «Pause nå», «Middag!» og "
            "«Fri fra lekser»",
            "«Middag!» trapper opp: etter 5 min dempes lyden og RGB blinker på PC-ene",
        ]),
        ("Rettet", ["Innstillinger kunne fryse et par sekunder når NAS-en var treg (PC-lista hentes nå i bakgrunnen)"]),
    ]),
    ("0.77.0", "Huset: natt, strøm og trygghet", [
        ("Nytt (Innstillinger → Automatikk → Huset)", [
            "Oppdateringskveld: én natt i uka vekkes PC-ene (Wake-on-LAN), alt oppdateres, de går i dvale igjen – "
            "rapport på mobilen",
            "Strømsparing når strømmen er dyr og PC-en står ubrukt",
            "Glemte PC-er om natten: beskjed, eller dvale automatisk",
            "Sovemodus for huset: 10 min varsel, så dvale på alle (og vekking om morgenen om du vil)",
            "Testmodus: nye versjoner prøves på én PC i 24 timer først – rulles den tilbake, får ingen andre den",
            "Strøm denne måneden per PC",
        ]),
        ("Også nytt", [
            "PC-er og mobilappen: ⏻ Vekk og 😴 Sov for hver PC",
            "Shelly-smartplugg: ekte strømmåling av hele PC-en (strøminnstillingene)",
            "Krasj og strømbrudd: Kontrollsenter merker når PC-en stoppet uten å avslutte, og hva som skjedde rett før",
            "Tidsmaskin for innstillingene: se hva som ble endret og gå tilbake (PC-assistenten)",
        ]),
    ]),
    ("0.76.0", "PC-assistenten", [
        ("Nytt", [
            "🩺 «Hvorfor treg?» på Oversikt, i søket (Ctrl+K) og i mobilappen: ser på varme, minne, prosessor, full "
            "disk, oppdateringer og skanning i bakgrunnen, strømmodus og oppetid – med fiks-knapp",
            "Spillsjekk: 20 sekunder etter at et spill starter sjekkes strømmodus, minne, disk og bakgrunnsjobber – "
            "ett varsel bare hvis noe bør fikses",
            "Lærer hva som er normalt: varsel når CPU/GPU går varmere enn vanlig ved samme last (støv) eller er "
            "varm selv i ro (kjølepasta)",
            "Diskvakt: hva som tar plass – store spill du ikke har spilt på 3 måneder, klipp og nedlastinger",
            "Levetid for SSD-ene i klartekst",
            "Ukens helserapport søndag kveld (også på mobilen)",
            "Foreslår «Eldre PC» av seg selv når vinduet hakker mye",
        ]),
    ]),
    ("0.75.0", "Eldre PC – lett grafikk", [
        ("Nytt (Innstillinger → Generelt → Ytelse)", [
            "«Eldre PC – lett grafikk»: ingen animasjoner, overganger, skygger, glød, levende bakgrunn eller "
            "minigrafer, vinduet oppdateres hvert 2. sekund og minne frigjøres når vinduet er lukket. Alle "
            "funksjonene virker. Står «anbefalt» på PC-er med få kjerner eller lite minne",
        ]),
        ("Raskere for alle", [
            "Effektnivå «Full» tegnet hele vinduet på nytt i full skjermfrekvens (179 ganger i sekundet) for den "
            "levende bakgrunnen – nå i små trinn: 6 ganger mindre tegning og 12 ganger mindre prosessor, nesten likt "
            "utseende",
            "Stue-modus, ladeikonet og bakgrunnen i mobilappen animeres på samme sparsomme måte (sparer batteri)",
        ]),
    ]),
    ("0.74.0", "Full kontroll over disk, prosessor og minne", [
        ("Nytt (Innstillinger → Generelt)", [
            "«Lagring på disk»: egen bryter for historikk, strøm, spilletid, hendelser, logg og toppverdier – av = "
            "verken skrives eller leses, bare i minnet mens programmet kjører. Bryteren finnes også på Historikk, "
            "i strøminnstillingene, på Familie og i feilloggen",
            "«Ingen lesing og skriving til disk»: slår av alt over, og oppdateringer og diskopprydding blir manuelle",
            "«Spar alt – minst mulig prosessor og minne»: minimal prosessbruk og mindre minnebruk, og alt ekstra i "
            "bakgrunnen stoppes. Slås den av, blir alt som før",
        ]),
    ]),
    ("0.73.0", "Oppdater alt med ett trykk", [
        ("Nytt", [
            "«Oppdater alt»: Kontrollsenter, programmene (Flatpak/winget), systemet med drivere, fastvare og de "
            "andre PC-ene – på Oversikt, i Innstillinger → Oppdatering og i mobilappen",
            "Bryter «Automatisk oppdatering og opprydding»: av = ingen automatiske sjekker, oppdateringer eller "
            "diskopprydding – du gjør alt selv",
            "PC-er: «Oppdater alt» og automatikk av/på for hver PC, og «Oppdater alt på alle»",
            "Funksjonene (Discord, klipp, VR, RGB, strømming, spill …) viser «Oppdatering klar» for programmet de "
            "bruker, med egen Oppdater-knapp",
        ]),
    ]),
    ("0.72.1", "WoW-addonen krasjer ikke lenger", [
        ("Rettet", [
            "WoW: Kontrollsenter Stats-addonen ga Lua-feil flere ganger i sekundet i WoW Forever, fordi nyere WoW "
            "skjuler farten («secret values») for addons. Addonen tåler nå skjulte verdier",
            "WoW: når farten er skjult, regnes distansen ut fra hvor langt du har flyttet deg i stedet",
        ]),
    ]),
    ("0.72.0", "Mindre minne og skåning av SSD", [
        ("Nytt (Innstillinger → Generelt → Ytelse)", [
            "«Mindre minnebruk»: når vinduet har vært lukket i 3 minutter, starter Kontrollsenter stille på nytt i "
            "statusfeltet – fra rundt 350 MB til rundt 120 MB. Aldri mens du spiller eller noe installeres",
            "«Mindre skriving til disk»: historikk, strøm og spilletid lagres samlet, og loggen får bare advarsler "
            "og feil – halverer det Kontrollsenter skriver til SSD/M.2",
        ]),
        ("Raskere", ["Historikken lagres uten å tvinge disken til å skrive hver gang (gjelder alle)"]),
    ]),
    ("0.71.2", "Finner hakking av seg selv", [
        ("Nytt", [
            "Windows: Kontrollsenter merker når vinduet hakker og hva som holdt det, og viser det i «Ytelse»-kortet",
            "Den månedlige oppryddingen skriver i loggen hvor mye plass den frigjorde",
        ]),
    ]),
    ("0.71.1", "Enda mindre prosessorbruk", [
        ("Raskere", [
            "Minimal prosessbruk: sensorene på Windows leses hvert 3. sekund, og i bakgrunnen samles data "
            "annethvert sekund",
        ]),
        ("Rettet", ["PC-er hjemme / venner: drivernummeret for NVIDIA på Windows vises igjen"]),
    ]),
    ("0.71.0", "Windows: raskere og jevnere", [
        ("Raskere på Windows", [
            "PowerShell-spørsmål får aldri vinduet til å stå stille: svar huskes, og vinduet får forrige svar "
            "med en gang mens et nytt hentes i bakgrunnen – også etter omstart",
            "Etter en reparasjon eller endring spør Kontrollsenter alltid på nytt",
            "Lydsiden og batterikortet spør ikke Windows når de ikke vises",
            "«Ytelse»-kortet viser hvor ofte vinduet har måttet vente",
        ]),
        ("Rettet", [
            "Windows: den månedlige oppryddingen krasjet",
            "Varsler mens du spiller kunne gi feil i bakgrunnen (og «Disken er nesten full» kom ikke)",
            "PC-er hjemme / venner: Windows-PC-er viste feil prosessornavn og manglet skjermkort, minne, "
            "hovedkort og disker",
        ]),
    ]),
    ("0.70.0", "Raskere og ryddigere", [
        ("Raskere", [
            "Spill-siden åpnes 7 ganger raskere (583 → 87 ms), Ny CPU-skjerm-siden 40 ganger (521 → 12 ms)",
            "Ingen hakk over 0,12 s når du bytter side (før: to på over 0,6 s)",
            "Rullehjulene koster ingenting lenger – vinduet skannes ikke hvert sekund",
            "Helse og panelene til mobilappen varmes opp i bakgrunnen, så appen slipper å vente",
        ]),
        ("Rettet", [
            "Knapper og hurtigkommandoer som styrer PC-en kunne gi «vinduet svarte ikke»",
            "Discord-kanaler/-chat i appen ga serverfeil uten valgt server",
            "Helsesjekken fra mobilen viste ikke lenger en fremdriftslinje på PC-en",
        ]),
        ("Ryddet", [
            "Kortere og tydeligere tekster på Discord, Familie, Opprydding, MSI, WoW, Pushvarsler og Enkel modus",
        ]),
    ]),
    ("0.69.0", "Raskere, særlig på Windows", [
        ("Nytt", [
            "Innstillinger → Generelt → «Ytelse»: se hvor mye prosessor, minne og lesing/skriving til disk "
            "Kontrollsenter selv bruker – live",
            "Bryter «Minimal prosessbruk»: ingen effekter, vinduet oppdateres hvert 3. sekund og valgfrie ting går "
            "sjeldnere – mer enn halverer prosessorbruken. Varsler, vifter og mobilappen virker som før",
            "«Åpne vinduet når PC-en starter» (på som standard) – av: bare ikon i statusfeltet",
        ]),
        ("Rettet", [
            "Windows: vinduet kom ikke tilbake etter en oppdatering (den nye trodde den gamle fortsatt kjørte). Nå "
            "venter den nye til den gamle er borte, og vinduet åpnes",
            "Windows: vinduet åpnes ved innlogging i stedet for bare ikon i statusfeltet",
            "Hakking: VR-siden og GPU-siden ventet på PowerShell i vinduet – nå i bakgrunnen",
            "Windows: effektene står på «Rolig» som standard (levende bakgrunn er tung for GTK på Windows)",
        ]),
    ]),
    ("0.68.2", "Tydelig beskjed om gamle PC-er", [
        ("Rettet", [
            "«Oppdater» på PC-er hjemme ga «svarer ikke (HTTP Error 401)» for PC-er med en versjon eldre enn 0.64. Nå står "
            "det at PC-en er for gammel til å oppdateres herfra, og den får en melding (familie-chatten) om å trykke "
            "«Oppdater» én gang – etter det virker knappen herfra",
            "«Oppdater alle PC-ene» hopper over PC-er som allerede har nyeste versjon",
        ]),
    ]),
    ("0.68.1", "Volumrullen på headsettet virker", [
        ("Rettet", [
            "Volumrullen på headsettet (og volumtastene) viste volumvinduet, men lyden endret seg ikke: standardutgangen "
            "var en annen enn den spillet og Discord brukte. Nå følger volumtastene utgangen der lyden faktisk spilles",
            "Ny bryter på Lyd-siden: «Volumtastene følger lyden» (på som standard)",
        ]),
    ]),
    ("0.68.0", "VR: WiVRn som alternativ til ALVR", [
        ("Nytt", [
            "VR-siden (Linux): velg mellom ALVR (gjennom SteamVR) og WiVRn (OpenXR rett til brillene – ofte lavere "
            "forsinkelse). Både trådløst og med kabel",
            "Sjekklisten og «Fiks alt» følger valget: WiVRn fra Flathub, Avahi, brannmur (9757 og 5353), adb og "
            "WiVRn-appen i brillene i nøyaktig samme versjon som PC-en",
            "«Start VR» starter WiVRn og – med kabel – setter opp tilkoblingen gjennom USB og åpner WiVRn i brillene. "
            "VR-vakten starter WiVRn og kabel-tilkoblingen igjen hvis de stopper",
            "Samme valg i VR-kortet i mobilappen",
        ]),
    ]),
    ("0.67.0", "Ryddig PC-app", [
        ("Nytt", [
            "Sidemenyen er ryddet fra 23 til 14 linjer: sider som hører sammen er gruppert – Spill (Spill, VR, "
            "Strømming), Utstyr (RGB, Logitech, CPU-skjerm, MSI), Nett og tilkobling (Nettverk, Wi-Fi, Bluetooth), "
            "Scener og Smart Hjem, og PC-er (hjemme og utenfor hjemmet)",
            "Øverst i en gruppe: ‹ rullehjul › for å bytte mellom sidene – som i mobilappen. Linjen i sidemenyen husker "
            "hvilken side du var på sist",
            "Lange sider er delt i kategorier med samme rullehjul: Familie (Kontroll og trygghet · Sammen · Mål og "
            "belønning), GPU-innstillinger (Skjermkortene · Skjerm og lys) og Discord (Samtalen · Lyd, mikrofon og "
            "overlay · Servere og chat · Tilkobling)",
        ]),
    ]),
    ("0.66.0", "Ryddig mobilapp", [
        ("Nytt", [
            "Hver fane i appen er delt i kategorier – velg med rullehjulet øverst (eller pilene / sveip). Bare kortene "
            "i valgt kategori vises, så du slipper å rulle langt ned. Appen husker valget",
            "Styr: PC-en · Lyd og skjerm · Scener og hjemmet · Discord. Spill: Spillene · Klipp · Prestasjoner · VR og "
            "strømming · Familie · Venner og PC-er. Verktøy: PC-verktøy · Historikk og strøm · Nett og NAS · "
            "Fjernstyring. Innstillinger: Utseende · Varsler · PC-en og appen",
            "PC-funksjonene ligger nå der de hører hjemme (spillene under Spill, radio og hjemme/borte under Styr …), "
            "og hurtigkommandoene er et rullehjul på Hjem",
            "Lange valglister (kommandoer, radiokanaler) er rullehjul i stedet for lange lister",
        ]),
    ]),
    ("0.65.0", "Mobilappen: alt fra PC-en", [
        ("Nytt", [
            "Ny seksjon «Alt fra PC-en» øverst i Verktøy i appen: hurtigkommandoer (samme som Ctrl+K), spillene med "
            "cover (start dem eller «Spill sammen»), PC-er hjemme med «Alt om PC-en» og «Oppdater alle PC-ene», "
            "PC-verktøy (ytelsestest, sikkerhetskopi, støymåler, oppstart), topp 5 programmer med installering og "
            "valg, hovedskjermkort, nettradio, hjemme/borte og versjon med «Gå tilbake»",
            "Fremdriftslinjen fra PC-en vises også i appen – prosent og tid igjen når PC-en installerer, rydder eller sjekker",
            "Stue-modus på telefonen/nettbrettet (hurtigknapp på Hjem): stor klokke, vær, temperaturer, dagens spilletid "
            "og hvem som spiller",
            "«Nytt tema hver dag» også i appen (Innstillinger → Effekter)",
            "Nye PC-funksjoner kommer automatisk i appen – PC-en beskriver kortene, appen tegner dem",
        ]),
    ]),
    ("0.64.0", "PC-er hjemme: alt om PC-en og oppdater alle", [
        ("Nytt", [
            "PC-er hjemme: «Alt om PC-en» på hver PC – live temperaturer, CPU, minne, skjermkort, hva som spilles, "
            "maskinvare og system (samme detaljer som for venner, hentet direkte fra PC-en)",
            "«Oppdater alle PC-ene»: henter nyeste versjon fra NAS-en på alle PC-ene som er på, og starter Kontrollsenter "
            "på nytt der. Er den nye versjonen allerede installert, startes den bare på nytt. «Oppdater» finnes også på "
            "hver PC som har en eldre versjon",
        ]),
        ("Rettet", ["Minnet hos venner ble vist med feil enhet"]),
    ]),
    ("0.63.0", "PC-er utenfor hjemmet", [
        ("Nytt", [
            "Ny side «PC-er utenfor hjemmet» (under Hjemmet): se vennenes PC-er – hva de spiller, FPS, CPU- og "
            "GPU-temperatur, minne og strøm. Trykk på en venns flis for alt om PC-en: prosessor, skjermkort, "
            "hovedkort, disker, driver, system og hvor lenge den har vært på – oppdateres live",
            "Del PC-en din med en vennekode: velg hva du deler (spill, temperaturer, maskinvare), kopier invitasjonen "
            "og send den. Vennene kan bare se – ikke styre noe. «Ny kode» stenger ute gamle invitasjoner",
            "PC-ene snakker direkte sammen over Tailscale – ingen skytjeneste. Del maskinen med vennen i Tailscale",
            "Venner-kort i mobilappen (Spill): trykk på en venn for detaljene, og legg til venner fra telefonen",
        ]),
    ]),
    ("0.62.0", "Hurtigkommandoer, prestasjoner og stue-modus", [
        ("Nytt", [
            "Hurtigkommandoer i søket (Ctrl+K): skriv «spillmodus», «klipp», «skjermbilde», «VR», «nattlys», «middag», "
            "en scene, et tema eller en lyd-/skjermprofil – og trykk Enter. Over 40 kommandoer",
            "«Dagen i dag» på Oversikt og i mobilappen: spilletid, mest spilte spill, klipp, strøm i kWh og kroner og "
            "varmeste temperatur",
            "🏆 Prestasjoner (Spill → Prestasjoner og i appen): 15 merker å låse opp – maraton, nattugle, 100 timer, "
            "kald hjerne, stilikon, inn i VR, lekse-helt m.fl. Du får varsel når du låser opp et nytt",
            "📺 Stue-modus (F11 eller menyen): fullskjerm til TV/andreskjerm med stor klokke, vær, temperaturer, dagens "
            "spilletid og hvem i huset som spiller – med levende bakgrunn",
        ]),
    ]),
    ("0.61.0", "18 nye temaer", [
        ("Nytt", [
            "Nå 28 temaer på PC (Linux og Windows) og i mobilappen: Cyberpunk, Galakse, Matrix, OLED-sort, Ametyst, "
            "Smaragd og gull, Koralrev, Midnattsblå, Tokyo Night, Dracula, Nord, Gruvbox, Catppuccin, Rosé Pine – og "
            "de lyse Sand, Mint, Papir og Catppuccin Latte",
            "«Nytt tema hver dag» (Innstillinger → Utseende): et nytt tema hver morgen, bare mørke eller bare lyse",
        ]),
    ]),
    ("0.60.0", "Nytt liv i utseendet", [
        ("Nytt", [
            "Levende bakgrunn som sakte driver i temaets farger – står stille når vinduet ikke er i fokus, så den "
            "ikke tar ytelse fra spill",
            "Kortene glir inn når du bytter side eller fane, knapper gir etter når du trykker, fliser løfter seg, "
            "sidemenyen glir og brytere spretter",
            "Samme effekter i mobilappen: kort som glir inn ved fanebytte, trykk-effekt og levende bakgrunn",
            "Innstillinger → Utseende → «Effekter»: Full, Rolig eller Av (også i appen)",
        ]),
    ]),
    ("0.59.3", "VR: riktig sjekk for trådløst og kabel", [
        ("Forbedret", [
            "Trådløst: sjekklisten viser «Questen funnet på Wi-Fi» i stedet for å be om USB-kabel",
            "Med kabel: «Questen koblet til med kabel» – eller «Kabel ikke koblet til» med hva du skal gjøre",
            "ALVR-appen i brillene regnes som installert når ALVR allerede kjenner brillene – ellers bare et tips",
        ]),
    ]),
    ("0.59.2", "VR: se hodesettet", [
        ("Nytt", [
            "VR-siden viser hodesettet øverst: 🔌 kabel (tilkoblet, modell og batteri) og 📶 Wi-Fi (på nettet, eller "
            "«Strømmer nå» med ALVR / Steam Link). Oppdateres hvert 5. sekund – også i mobilappen",
            "Koble Questen til med kabel én gang, så husker Kontrollsenter Wi-Fi-adressen og ser den trådløst etterpå",
        ]),
    ]),
    ("0.59.1", "VR: brannmur-rettingen virker", [
        ("Rettet", [
            "VR → «Fiks alt»: brannmur-rettingen feilet fordi sonenavnet ble lest feil («FedoraWorkstation (default)»)",
            "Brannmur-sjekken forstår nå portområder – på Bazzite/Fedora er VR-portene allerede åpne (1025–65535), så "
            "det trengs ingen endring",
            "Tydeligere feilmeldinger: avbrutt passord og feil fra firewall-cmd vises hver for seg",
        ]),
    ]),
    ("0.59.0", "Fremdriftslinje", [
        ("Nytt", [
            "Når Kontrollsenter installerer, laster ned, rydder, sjekker eller retter noe, vises en enkel fremdriftslinje "
            "nederst i vinduet: hva som skjer, prosent og omtrent hvor lang tid som er igjen. Grønn ✓ når det er ferdig",
            "Gjelder programinstallasjoner (Flathub/winget), Programmer-siden, Rydd opp, Systemsjekk, «Hvorfor er PC-en "
            "treg?», ytelsestest, støymåler, sikkerhetskopi til NAS, oppdateringer, GE-Proton og VR-oppsettet",
        ]),
    ]),
    ("0.58.0", "VR med Meta Quest 3", [
        ("Nytt", [
            "Ny side «VR» under Spill: Meta Quest 3 gjennom Steam og SteamVR – trådløst eller med kabel, på Linux og "
            "Windows. Linux: ALVR (trådløst og over USB). Windows: Steam Link (trådløst) og Meta Quest Link (kabel), "
            "eller ALVR",
            "Sjekkliste over alt som trengs – Steam, SteamVR, ALVR/Meta Link, brannmur, SteamVR-rettigheter, OpenXR, "
            "adb, ALVR-appen i brillene, videokoding og nettverk – og «Fiks alt» som installerer og retter automatisk",
            "«Start VR» starter alt i riktig rekkefølge, og VR-vakten starter ALVR, SteamVR og kabel-tilkoblingen "
            "igjen av seg selv hvis noe stopper mens du spiller",
            "VR-kort i mobilappen (Spill): start, fiks og stopp fra telefonen",
        ]),
    ]),
    ("0.57.1", "Rullehjulet følger musehjulet", [
        ("Forbedret", [
            "Rullehjulet i valgmenyene (PC og app): ett hakk på musehjulet = ett valg. Styreplate ruller fortsatt "
            "mykt og stopper på nærmeste valg",
        ]),
    ]),
    ("0.57.0", "Søk, enkel modus og ny «Hva er nytt»", [
        ("Nytt", [
            "Søk i hele Kontrollsenter: Ctrl+K (eller forstørrelsesglasset i sidemenyen) finner alle kort, brytere og "
            "valg – og hopper rett dit, med riktig fane og kortet markert",
            "Enkel modus (Innstillinger → Generelt): viser bare Oversikt, Lyd, Spill, Discord, Scener, Smart Hjem, "
            "Familie og Innstillinger. Fint på barnas PC-er – familiekoden trengs for å slå den av",
            "Ny «Hva er nytt»: det nye siden sist som kort med illustrasjon og «Vis meg»-knapp rett til funksjonen; "
            "eldre versjoner sammenfoldet og søkbare",
        ]),
    ]),
    ("0.56.0", "Mobilen: widget, snarveier og push", [
        ("Nytt", [
            "Ny widget «Spillstatus» på Android-hjemskjermen: hva som spilles nå, FPS, CPU- og GPU-temperatur, "
            "spilletid i dag – og hva de andre i huset spiller",
            "Scenene blir snarveier på app-ikonet (hold inne) – og kan brukes i Google Assistant- og Bixby-rutiner. "
            "«Hey Google, åpne Spillmodus i Kontrollsenter» virker også",
            "Pushvarsler med ntfy: varslene kommer med en gang, uten at appen er åpen og uten skytjenester – ntfy "
            "kobler seg direkte til PC-en. Slå på i Innstillinger → Varsler, og trykk «Legg til i ntfy» i appen",
        ]),
    ]),
    ("0.55.0", "Trygg på nettet og leksetid", [
        ("Nytt", [
            "Nettfilter (Familie-siden og mobilen): Cloudflare Family, CleanBrowsing eller AdGuard Family blokkerer "
            "voksen-, gambling- og skadelige sider for hele PC-en. Krever familiekoden når familiekontroll er på",
            "Leksetid: velg dager og klokkeslett – spill lukkes etter 2 minutters varsel, unntatt når «Ferdig med "
            "lekser» er godkjent i dag",
            "Meldinger rett i spillet (MangoHud på Linux): «15 minutter igjen», «5 minutter igjen – lagre spillet», "
            "«Leggetid om 10 min» og «Leksetid» – også når overlayet er skjult",
        ]),
    ]),
    ("0.54.0", "Lyd- og skjermprofiler", [
        ("Nytt", [
            "Lydprofiler (Lyd-siden): lagre utgang (høyttalere, hodesett, TV), mikrofon og volum – bytt med ett trykk. "
            "Det som spiller nå flyttes med",
            "Skjermprofiler (GPU-innstillinger): oppløsning, Hz, HDR og VRR – f.eks. «Spill» og «Film». Windows: "
            "oppløsning og Hz",
            "Nattlys og lysstyrke (GPU-innstillinger) – også eksterne skjermer via KDE (DDC/CI)",
            "Alt kan styres fra mobilen (Styr → «Lyd og skjerm») og brukes i scener: lydprofil, skjermprofil, nattlys "
            "og lysstyrke – f.eks. automatisk når et spill starter eller kl. 22",
        ]),
    ]),
    ("0.53.0", "Skjermkort og ytelse per spill", [
        ("Nytt", [
            "Spill → Bibliotek: velg skjermkort per spill (integrert eller dedikert) når PC-en har flere. Linux: "
            "legges i spillets oppstartsvalg; Windows: Windows' egen GPU-preferanse for spillets programfiler",
            "FPS-tak per spill (30–240) – sparer strøm og varme i lette spill (Linux, Windows-spill via Proton)",
            "Spillprofiler: «GPU-strøm» per spill (60–100 % av standard strømgrense) – settes når spillet starter og "
            "tilbake når det avsluttes. NVIDIA og AMD",
        ]),
    ]),
    ("0.52.0", "Tryggere oppdateringer", [
        ("Nytt", [
            "Selvtest før hver ny versjon: alle sider, faner og mobilappen åpnes automatisk, og versjonen legges ikke "
            "ut hvis noe krasjer (feilen i Innstillinger i 0.47 ville blitt stoppet)",
            "Starter en ny versjon ikke, går PC-en tilbake til forrige versjon av seg selv – nå for alle oppdateringer, "
            "ikke bare den nattlige. Krasjer den med en gang, skjer det umiddelbart",
            "Innstillinger → Oppdatering: «Gå tilbake til forrige versjon» med ett trykk",
            "Feil sendes til NAS-en (Diagnose) hver halvtime når det har kommet nye – og Vedlikehold → Feilsøking → "
            "«Feil fra PC-ene i huset» viser dem for alle PC-ene",
        ]),
    ]),
    ("0.51.0", "Velg skjermkort", [
        ("Nytt", [
            "GPU-innstillinger → «Hovedskjermkort» (når PC-en har flere skjermkort): velg Automatisk, integrert eller "
            "dedikert – eller mellom flere dedikerte. Viser hvilket kort skjermen er koblet til",
            "Advarsel om at skjermkabelen må sitte i kortet du velger, ellers blir skjermen svart",
            "Linux (KDE): byttet skjer ved neste innlogging, og bare hvis det valgte kortet har en skjerm koblet til – "
            "ellers starter skrivebordet som vanlig, så du aldri står uten bilde",
            "Windows: de andre skjermkortene slås av, og byttet angres av seg selv hvis du ikke trykker «Behold» "
            "innen 20 sekunder",
        ]),
    ]),
    ("0.50.0", "Velg program i hver funksjon", [
        ("Nytt", [
            "Øverst i hver funksjon: «Program» – velg hvilket av de installerte programmene du vil bruke, og bytt når du "
            "vil (f.eks. Medal ↔ Xbox Game Bar). «Åpne» starter programmet, og «Flere programmer – topp 5» lar deg "
            "installere flere",
            "Klipp følger valget: på Windows trykker «Lagre klipp» og F8 tasten til Medal, NVIDIA App (Alt+F10), OBS, "
            "Steam eller Game Bar. Tasten kan endres per program. På Linux stoppes Kontrollsenters eget opptak når du "
            "velger et annet program, så det ikke tas opp dobbelt",
            "Spill-launcheren: «Vis spill fra» – alle, eller bare Steam / Heroic / Lutris",
            "Fjernstyr-knappen på mobilen åpner programmet du har valgt (RustDesk, AnyDesk, TeamViewer, Parsec …)",
        ]),
    ]),
    ("0.49.0", "Topp 5 programmer per funksjon", [
        ("Nytt", [
            "Hver funksjon som trenger et program viser de fem beste valgene, rangert fra 1 til 5 – eget for Linux og "
            "Windows: spillbutikker, tale og chat, RGB, mus og tastatur, klipp, redigering, strømming, fjernstyring og VPN",
            "Merket «styres fra Kontrollsenter» på programmene Kontrollsenter kan styre direkte. Installer med ett trykk "
            "(Flathub/winget), eller «Nettside» der programmet må lastes ned fra produsenten",
            "Samlet oversikt i Innstillinger → Generelt – funksjoner som mangler program er slått opp",
        ]),
        ("Rettet", [
            "Innstillinger åpnet seg ikke (feil fra 0.47)",
        ]),
    ]),
    ("0.48.0", "Medal og «Se på» som virker", [
        ("Nytt", [
            "Windows: Medal brukes til klipp i stedet for Xbox Game Bar (kan byttes under Spill → Klipp). Mangler Medal, "
            "kommer «Installer Medal». Medal eier F8 selv, «Lagre klipp» i appen og på mobilen trykker Medals tast, og "
            "klippene vises fra Medal-mappen (finnes av seg selv, eller velg den)",
        ]),
        ("Rettet", [
            "«Se på» på Linux ga svart skjerm med en tynn strek: bildet hentes nå med GPU Screen Recorder (samme som "
            "klippene), som leser skjermkortets bilde riktig – også på NVIDIA. Første bilde kommer etter ca. 1,5 sekunder",
            "Gjenkjenner svarte bilder og prøver neste metode av seg selv, og husker metoden som virket",
        ]),
    ]),
    ("0.47.0", "Riktig program til hver funksjon", [
        ("Nytt", [
            "Funksjoner som trenger et program viser «Installer …» rett i funksjonen når programmet mangler – med det "
            "beste valget for Linux (Flathub) og Windows (winget): Spill-launcheren (Steam, Heroic, Lutris, Battle.net), "
            "Discord, RGB (OpenRGB), Logitech (Solaar / G HUB), klipp (GPU Screen Recorder, FFmpeg), Strømming "
            "(Sunshine, Moonlight) og fjernstyring (RustDesk)",
            "Ny oversikt i Innstillinger → Generelt: alle programmene funksjonene bruker, hva de er til, og om de er "
            "installert",
            "Alle installasjoner går nå samme vei, og programmer som er installert på andre måter blir funnet",
        ]),
    ]),
    ("0.46.0", "Familieplan og belønningsbutikk", [
        ("Nytt", [
            "Felles ukeplan (Familie-siden og mobilappen): legg inn avtaler som «Fotballtrening tirsdag 17:30». Planen "
            "ligger på NAS-en, og hver PC varsler 15 minutter før – også midt i et spill – så man rekker å lagre",
            "Belønningsbutikk: godkjente mål gir stjerner (1 ⭐ per 5 minutter). Stjernene løses inn mot ekstra "
            "spilletid, å velge middag eller film, være oppe lenger i helgen m.m. – en voksen godkjenner",
            "Ny varseltype «Ukeplan» under Innstillinger → Varsler",
        ]),
    ]),
    ("0.45.0", "Smartere hjem", [
        ("Nytt", [
            "Hjemme/borte (Smart Hjem → Automatikk): velg telefonene i huset, så kan scener slå seg på «Når noen kommer "
            "hjem» eller «Når alle har dratt». Alt skjer lokalt på hjemmenettet",
            "Strømpris-smart: ny scene-utløser «Når strømmen er billigst i natt», og den ukentlige sikkerhetskopien til "
            "NAS-en kjøres i den billigste timen mellom 22 og 07",
            "Nettradio rett på Chromecast/Nest: NRK P1, P2, P3, mP3, Klassisk og Jazz – høyttaleren spiller selv, så "
            "PC-en kan slås av. Egne kanaler kan legges i radio.json",
        ]),
    ]),
    ("0.44.0", "Mobilen mens du spiller", [
        ("Nytt", [
            "Levende varsel på telefonen mens et spill kjører: spillet, FPS, CPU-/GPU-temperatur og spilletid i dag – "
            "også på låseskjermen, med knapp for «Lagre klipp». Stopper av seg selv når spillet avsluttes",
            "Får du ikke varselet med en gang, kommer et «Trykk for live-status»-varsel når PC-en begynner å spille",
            "Ny hurtigknapp «Del klipp» på Hjem: deler det siste klippet med ett trykk (Snap, Messenger osv.)",
            "Ny hurtigknapp «Fjernstyr»: kopierer PC-ens RustDesk-ID og åpner RustDesk-appen på telefonen",
        ]),
    ]),
    ("0.43.0", "PC-verktøy", [
        ("Nytt", [
            "Oppstartsrapport (Vedlikehold → System): hvor lang tid PC-en bruker på å starte, hva som tar mest tid, og "
            "konkrete tips (f.eks. «Fast Boot» i BIOS eller utsette Sunshine)",
            "Trygg ytelsestest: måler prosessor (én og alle kjerner), minne og disk og sammenligner med forrige gang – "
            "endrer ingenting på maskinvaren (i stedet for overklokking)",
            "Støymåler for viftene (Linux): mikrofonen lytter mens viftene går på 30–100 %, og du får vite hvor raskt "
            "de kan gå før de bråker. Viftene settes tilbake til auto etterpå",
            "Sikkerhetskopi til NAS-en (Vedlikehold → Gjenoppretting): skjermbilder, klipp og dokumenter – bare nye og "
            "endrede filer, med automatikk hver uke",
        ]),
    ]),
    ("0.42.0", "Spill-launcher", [
        ("Nytt", [
            "Ny fane «Spillene» under Spill: alle spillene dine med cover-bilder – Steam, Heroic (Epic/GOG) og Lutris "
            "(f.eks. Battle.net). Ett trykk starter spillet, og scener, tema og spillprofil for spillet slår seg på av seg selv",
            "«Spill sammen»: trykk på personer-knappen på et spill, så får de andre PC-ene i huset et varsel – trykker de "
            "på det, starter samme spill hos dem og du får beskjed om at de blir med",
            "YouTube og Twitch i nettleseren telles som skjermtid i spilletiden og familiegrensene (Linux). Kan slås av "
            "på Familie-siden (krever familiekoden når familiekontroll er på)",
            "Høydepunkt-klipp i CS2 ved 3+ kills eller ace lagres fortsatt av seg selv",
        ]),
    ]),
    ("0.41.0", "Discord: servere og chat", [
        ("Nytt", [
            "Discord-siden viser nå serverne du er med i og kanalene på hver server. Trykk på en tekstkanal for å lese "
            "chatten – den oppdateres av seg selv, med navn i fargene fra Discord og dine egne meldinger til høyre",
            "«Åpne i Discord» / «Svar i Discord» åpner kanalen rett i Discord-appen (på PC-en og telefonen)",
            "I appen: «💬 Servere og chat» i Discord-kortet under Styr",
            "Merk: Discord tillater ikke at andre programmer sender meldinger som deg eller viser vennelisten din – "
            "det ville krevd innloggingsnøkkelen din og bryter vilkårene deres. Har du koblet til før: trykk «Koble "
            "til på nytt» én gang, så får Kontrollsenter lov til å lese chatten",
        ]),
    ]),
    ("0.40.1", "Glød på flisene", [
        ("Nytt", [
            "Flisene og kortene i Oversikt, kortene på sidene og scenekortene gløder nå som knappene: en lysende kant "
            "i temaets farger når musa er over, og et mykt lys som følger pekeren",
            "I appen: flisene, snarveiene, scenene, Discord-knappene og målene lyser opp der fingeren trykker, med glød "
            "rundt – og følger musa på nettbrett/PC",
        ]),
    ]),
    ("0.40.0", "Rullehjul og Discord", [
        ("Nytt", [
            "Alle valgmenyer er nå et rullehjul – som den gamle iPhone-velgeren, men med flytende glass: valgene ligger "
            "på en sylinder som snurrer, det valgte står i et lysende glassbånd og hjulet snapper mykt på plass. Rull, "
            "dra, trykk eller bruk piltastene. Også i mobilappen, med et lite tikk for hvert valg",
            "Ny side «Discord» (under Spill) og et Discord-kort i appen (Styr): mikrofon av, lyd av og forlat samtalen "
            "med ett trykk, og hvem som er i samtalen",
            "Med full tilkobling til Discord: mikrofonvolum, volum på samtalen, valg av mikrofon og høyttalere, "
            "stemmeaktivering eller trykk for å snakke, støydemping, ekkodemping og automatisk forsterkning",
            "Uten oppsett styres Discord via lydsystemet: Discord-volum, mikrofon av og lyd av",
            "Overlay: Discord har ikke eget overlay på Linux – knappen slår på spill-overlayet i Kontrollsenter i stedet",
        ]),
    ]),
    ("0.39.0", "Ytelse og vedlikehold", [
        ("Nytt", [
            "«Hvorfor er PC-en treg?» – én knapp (Vedlikehold → Feilsøking, og i appen under Verktøy) som ser på "
            "prosessor, minne, disk, temperatur, strømmodus og oppdateringer i bakgrunnen, forklarer hva som er galt og "
            "har en knapp for å fikse det (avslutt programmet, kraftigere vifter, bytt strømmodus)",
            "Automatisk opprydding én gang i måneden – bare det som er helt trygt (miniatyrbilder og shader-cache for "
            "spill som ikke er installert; på Windows også midlertidige filer). Aldri papirkurven eller filene dine. "
            "Rapport som varsel og i Vedlikehold → Rydd opp",
            "Overvåking av FPS-dropp: når FPS-en faller kraftig mens du spiller, lagres hva som skjedde – temperaturer, "
            "belastning og hva som kjørte. Øktrapporten sier hvor mange dropp det var og den vanligste årsaken, og "
            "detaljene står under Spill → Statistikk",
        ]),
        ("Rettet", [
            "Feil på Logitech-siden (Solaar-enheter) når kortene ble bygd på nytt",
        ]),
    ]),
    ("0.38.0", "Familie og spill", [
        ("Nytt", [
            "Ukesrapport søndag kveld: spilletid per person, mest spilte spill, antall økter, lengste økt og strøm – for "
            "alle PC-ene i huset. Også som kort på Familie-siden og i appen (Spill)",
            "Mål og belønning: «Ferdig med lekser», «Ryddet rommet», «Gått tur» og «Hjulpet til hjemme». Barna trykker, "
            "foreldrene får varsel på telefonen og godkjenner – ekstra spilletid kommer med en gang. På PC-en krever "
            "godkjenning familiekoden når familiekontroll er på",
            "Ranking på tvers av PC-ene: mest spilt denne uka, flest økter, lengste økt og flest CS2-kills – i tillegg til "
            "K/D og WoW-levels. Vises på Familie-siden og i appen",
        ]),
    ]),
    ("0.37.0", "Smart Hjem-automatikk", [
        ("Nytt", [
            "Hue-lysene følger spillet: når et spill starter, får lysene spillets farge – og settes tilbake slik de var "
            "når du avslutter",
            "TV-en slås av når PC-en går i hvilemodus eller slås av (Linux) – Kontrollsenter ber om et par sekunder "
            "så den rekker det",
            "Synk RGB og Hue: lysene i rommet og i PC-en har alltid samme farge, enten du endrer i Kontrollsenter "
            "eller i Hue-appen",
            "Slås på øverst på siden Smart Hjem. Scenene fra forrige versjon kan fortsatt gjøre alt på én gang",
        ]),
    ]),
    ("0.36.0", "Mobilappen", [
        ("Nytt", [
            "Ny widget «Velg selv»: fire fliser du velger – CPU/GPU-temperatur, strømforbruk, ping, strømpris nå, været, "
            "spilt i dag, kWh i dag, batteri eller neste avtale. Hold på widgeten → Innstillinger for å bytte",
            "Nye hurtigfliser (sveip ned – virker også fra låseskjermen): «Demp PC-en» og «Middag!»",
            "Nye snarveier på app-ikonet (hold fingeren på ikonet): Spillmodus, Demp PC-en, Middag! og Lås PC-en. Dra dem "
            "ut på hjemskjermen, eller bruk dem i Bixby-rutiner",
            "Klokka (Wear OS / Galaxy Watch): varslene fra Kontrollsenter – temperatur, batteri, chat og «Middag!» – "
            "vises på klokka når telefonen viser dem",
        ]),
    ]),
    ("0.35.0", "Smartere varsler", [
        ("Nytt", [
            "«Musa er fulladet» – varsel når mus, headset eller tastatur er ferdig ladet, så du kan ta ut kabelen",
            "Øktrapporten etter et spill sier fra når du har satt rekord: «🏆 lengste økt denne uka» eller "
            "«🏆 beste FPS denne uka»",
            "Diskhelse: én gang i døgnet sjekkes SMART – du får varsel hvis disken nærmer seg slitt eller har feil",
            "Varsel hvis prosessoren eller skjermkortet blir mye varmere på under ett minutt uten at noe jobber "
            "(vifte som har stoppet, støv …)",
            "Mens du spiller holdes varslene tilbake – du får ett samlet varsel når spillet er ferdig. Familie-chat og "
            "spilletid kommer likevel. Kan slås av i Innstillinger → Varsler",
        ]),
    ]),
    ("0.34.0", "Flere fliser", [
        ("Nytt", [
            "Nye fliser i Oversikt: ping, nedlasting, spilletid i dag, strømpris nå (med billigste time), været og neste "
            "kalenderavtale. Sted, strømprisområde og kalender velger du i Innstillinger → Generelt",
            "Minigraf for siste minutt rett i CPU-, GPU-, strøm-, ping- og nedlastingsflisen",
            "Oppsett: Standard, Spill, Jobb og Natt – hvert oppsett husker sine egne fliser, rekkefølge og størrelser. "
            "«Spill» velges av seg selv mens du spiller, og byttes tilbake etterpå",
            "Skjul fliser du ikke trenger (✕ i tilpass-modus eller høyreklikk) – og hent dem fram igjen med «Vis skjulte»",
        ]),
    ]),
    ("0.33.0", "Levende temaer", [
        ("Nytt", [
            "Tema etter tid på døgnet: Arktis om morgenen, Solnedgang om kvelden og Nordlys om natten (du velger tider og "
            "temaer). På PC-en glir fargene sakte over i det neste temaet de siste 20 minuttene",
            "Tema som følger spillet: velg et tema per spill – når spillet starter, bytter Kontrollsenter tema og RGB-lysene "
            "i PC-en får samme farge. Alt går tilbake når du avslutter",
            "Eget tema: velg to farger selv, eller la Kontrollsenter hente fargene fra skrivebordsbakgrunnen din",
            "Levende bakgrunn: gløden beveger seg sakte og lyser sterkere når PC-en jobber hardt (PC og app)",
        ]),
        ("Rettet", [
            "Kortene på sidene fikk tom luft nederst etter at de ble flyttbare",
        ]),
    ]),
    ("0.32.0", "Scener", [
        ("Nytt", [
            "Scener: én knapp som setter hele rommet og PC-en på én gang – strømmodus, vifter, RGB, Hue-lysene, "
            "Samsung-TV-en, lyden, fargetemaet og varslene. Fem ferdige: Spillkveld, Etter spillet, Filmkveld, Fokus og "
            "God natt – og du kan lage dine egne",
            "Scener kan slå seg på av seg selv: når et spill starter, når det avsluttes, eller hver dag på et klokkeslett",
            "Ny side «Scener» under Hjemmet på PC-en, og et Scener-kort øverst i Styr i mobilappen",
            "«Ingen varsler» i en scene holder varslene unna til en annen scene slår dem på igjen (familie-chat og "
            "spilletid slipper fortsatt gjennom)",
        ]),
    ]),
    ("0.31.0", "Temaer", [
        ("Nytt", [
            "Ti fargetemaer på PC-en (Linux og Windows) og i mobilappen: Nordlys, Synthwave, Solnedgang, Dyphav, Skog, "
            "Midnatt og gull, Lava, Kirsebærblomst, Arktis – og det gamle Kontrollsenter. Hvert tema farger alt: "
            "bakgrunnen med glød, kortene, sidemenyen, knappene, bryterne, grafene og det som er «på»",
            "PC-en: Innstillinger → Utseende. Temaet byttes med en gang, uten omstart",
            "Appen: Innstillinger → Utseende. Temaet glir over på et øyeblikk og gjelder også startskjermen og alle PC-ene",
        ]),
    ]),
    ("0.30.5", "Musa blir værende", [
        ("Rettet", [
            "Musa kunne fortsatt forsvinne når ladekabelen ble tatt ut og satt i igjen, fordi UPower mistet den. Nå leses "
            "batteriet også rett fra Linux-kjernen, så musa vises alltid – med «⚡ Lader · 70 %» mens den lader, enten "
            "den lader trådløst via mottakeren eller står koblet med kabelen",
        ]),
    ]),
    ("0.30.4", "Mus i ladekabelen", [
        ("Rettet", [
            "En Logitech-mus (f.eks. PRO X2 SUPERSTRIKE) forsvant fra batterilisten når ladekabelen ble satt i – den "
            "snakker da direkte over USB i stedet for via mottakeren. Nå vises den som «⚡ Lader · 68 %», og nivået "
            "oppdateres hvert 8. sekund mens den lader (via Solaar)",
        ]),
    ]),
    ("0.30.3", "Lading med en gang", [
        ("Rettet", [
            "Når du setter inn eller tar ut laderen, endres batteriet med en gang: mus og tastatur (UPower sier fra "
            "umiddelbart) og hodesett (sjekkes hvert 4. sekund). Før kunne det ta opptil halvannet minutt",
        ]),
    ]),
    ("0.30.2", "Lading", [
        ("Nytt", [
            "Enheter som lader viser et grønt, pulserende lyn og «Lader · 64 %» – på PC-en, i appen, i detaljene og i "
            "widgetene (skrivebord, KDE og Android). Fulladet vises med støpsel og «Fulladet · 100 %»",
        ]),
        ("Rettet", [
            "Batterier-kortet i appen var borte etter at Hjem ble ombygd – nå ligger det blant flisene igjen. "
            "Feilen stoppet også resten av familie- og knappebord-funksjonene i appen",
            "Hodesett som ikke oppgir nivå mens de lader, viste «-1 %»",
        ]),
    ]),
    ("0.30.1", "Batteri i hodesettet", [
        ("Rettet", [
            "«Installer» i Batterier-kortet feilet fordi Homebrew ikke lenger har HeadsetControl. Nå hentes ferdig "
            "versjon rett fra HeadsetControl på GitHub – på både Linux og Windows. Da vises batteriet i hodesett som "
            "Logitech G PRO X 2 LIGHTSPEED",
        ]),
    ]),
    ("0.30.0", "Flytt og endre alt", [
        ("Nytt", [
            "Alle kort i alle fanene kan nå få ny størrelse, ikke bare på Hjem: S, M og L. I appen: hold fingeren på et "
            "kort (Styr, Spill, Verktøy, Innstillinger) og trykk S/M/L i hjørnet. På PC-en: høyreklikk på et kort, eller "
            "velg «Vis S / M / L i hjørnet»",
            "PC-en: kortene på alle sidene ligger nå i samme rutenett som Oversikt – dra for å flytte, og små kort "
            "legger seg ved siden av hverandre",
        ]),
        ("Rettet", [
            "Appen: langt trykk virket bare på overskriften i kort som er fulle av knapper (Styr, Spill, Verktøy, "
            "Innstillinger). Nå virker det også på knappene – trykket på knappen blir ikke utført",
        ]),
    ]),
    ("0.29.0", "Flytt på alt", [
        ("Nytt", [
            "PC-en: dra et hvilket som helst kort på alle sidene til en ny plass med musa – Spill, Vedlikehold, "
            "Innstillinger, Nettverk, Lyd, GPU, RGB, Logitech, CPU-skjerm, Familie, PC-er hjemme, Smart Hjem, Historikk og "
            "resten. Målet lyser lilla, kortet spretter på plass, og rekkefølgen huskes",
            "Appen: hold fingeren på et kort i hvilken som helst fane (Hjem, Styr, Spill, Verktøy, Innstillinger) og dra "
            "det dit du vil – også snarveiene øverst på Hjem. «Tilbakestill» setter fanen tilbake",
            "Startskjermen i appen: hold fingeren på en PC, en TV/høyttaler eller en enhet i Smart Hjem for å flytte den",
        ]),
    ]),
    ("0.28.1", "Alle flisene", [
        ("Nytt", [
            "Alle flisene og kortene i Oversikt kan nå trykkes på for detaljer – også Strømmodus, Vifter (hver vifte, "
            "turtall over tid og styring), Helse (hele systemsjekken) og Maskin (system, hovedkort, BIOS, grafikk, disker)",
        ]),
        ("Rettet", [
            "Lange forklaringer i detaljene vises under tittelen i stedet for å klemme den",
            "Detaljarket i appen er ikke lenger gjennomsiktig med flytende glass i lyst tema",
        ]),
    ]),
    ("0.28.0", "Din egen oversikt", [
        ("Nytt", [
            "Oversikt kan ordnes som du vil – på PC-en og i mobilappen: dra flisene og kortene til nye plasser. "
            "Flisen løftes når du drar, de andre glir unna, og den «spretter» på plass med en lilla glød når du slipper",
            "Velg størrelse på hver flis og hvert kort: S, M, L (og XL i appen). På PC-en: trykk på rutenett-knappen øverst "
            "eller høyreklikk på et kort. I appen: hold fingeren på en flis",
            "Trykk på en flis eller et kort for mye mer info: graf for de siste 10 minuttene, nøkkeltall, hver tråd, "
            "hva som bruker mest CPU og minne, alle disker, nettverkskort med IP, alle temperaturer, strømkostnad og batterier",
            "Velg hvilke varsler du vil ha – eller slå av alle: Innstillinger → Varsler på PC-en. I appen kan du "
            "velge både hva PC-en varsler om og hva telefonen varsler om (Innstillinger)",
        ]),
        ("Endret", [
            "Batterier, Strømmodus og Vifter er nå kort i Oversikt som kan flyttes på, og 1 min / 10 min / 1 time for "
            "grafene ligger øverst",
            "Hovedbryteren for varsler slår nå av alle varsler (også chat, klipp og spilletid). Spilletid og leggetid "
            "vises alltid når familiekontroll er på, og «noen ser på skjermen din» vises alltid",
        ]),
    ]),
    ("0.27.0", "Ryddet opp", [
        ("Endret", [
            "Ny side «Innstillinger» nederst i sidemenyen – alt du stiller inn i Kontrollsenter er samlet der i faner: "
            "Generelt (oppstart, bakgrunn, glass og språk), Varsler, Automatikk (stille om natten), Widgets, "
            "Mobil (mobilappen, fjernstyring og «Del denne PC-en») og Oppdatering (oppdatering og sikkerhetskopi)",
            "«Verktøy» heter nå «Vedlikehold» og har faner: System, Rydd opp, Gjenoppretting og Feilsøking "
            "(med Systemsjekk)",
            "Spill har fått faner: Statistikk, Klipp, Bibliotek, Spillprofiler og Kontrollere. Spillprofiler er flyttet "
            "hit fra Automatikk",
            "Sidemenyen er ryddet: Familie, PC-er hjemme og Smart Hjem ligger sammen under «Hjemmet», og siden "
            "«Automatikk» er borte (innholdet ligger i Spill og Innstillinger)",
            "Sidene husker hvilken fane du var på sist",
        ]),
    ]),
    ("0.26.0", "Smart Hjem", [
        ("Nytt", [
            "Ny side «Smart Hjem» på PC-en: finner alle enhetene på hjemmenettet – lys, TV-er, Chromecast/Nest, "
            "høyttalere, konsoller, NAS, ruter og resten – og sorterer dem etter type. Gi dem navn ved å trykke på dem",
            "Styr Philips Hue (alle lys, rom, hvert lys med lysstyrke og farge), Samsung-TV (av/på, volum, demp, hjem, "
            "kilde, pause/spill) og Chromecast/Google Nest (hva som spilles, volum, demp, pause, stopp)",
            "Android-appen: ny fane «Smart Hjem» nederst på startskjermen ved siden av «PC-er» – hentes fra en PC som er på",
        ]),
        ("Endret", [
            "Startskjermen i Android-appen er ryddet: fanelinje nederst, små verktøyknapper (Søk, Legg til, Spill) "
            "og mindre tekst",
        ]),
    ]),
    ("0.25.0", "Lilla betyr «på»", [
        ("Endret", [
            "Lilla betyr nå alltid at noe er slått på – på PC-en, i appen og på startsiden i Android-appen. "
            "Vanlige knapper (Lagre, Åpne, Søk …) er ikke lenger lilla hele tiden, men lyser lilla mens du holder på dem",
            "Vifter: 50 % og Maks blir lilla når viftene står slik (som Auto og Kurve)",
            "«Slå av senere»: tiden du valgte er lilla til avslåingen er avbrutt",
            "Snarveiene (Spillmodus, Demp av/på, Vifter maks og Vifter auto) blir lilla når de er på",
            "Tasten for klipp: valgt tast er lilla",
        ]),
        ("Rettet", [
            "Med glass-utseendet på PC-en ble knapper som var slått på ikke lilla",
        ]),
    ]),
    ("0.24.3", "Lilla også på hjemmeskjermen", [
        ("Endret", [
            "Android-widgeten «Hurtigknapper»: Demp blir lilla når lyden er dempet (som Spillmodus), "
            "og et nytt trykk slår lyden på igjen",
        ]),
    ]),
    ("0.24.2", "Lilla når det er på", [
        ("Endret", [
            "Alle knapper som er slått på blir nå lilla – på PC-en og i appen på mobil og nettbrett, "
            "akkurat som «Auto» på viftene (f.eks. dempeknappen, profiler, tidsrom i grafene og stjerner)",
        ]),
    ]),
    ("0.24.1", "Alt om WoW på ett sted", [
        ("Endret", [
            "Spill: alt om World of Warcraft er samlet i ett kort rett under statistikken – karakterene, bagsøk, mål og "
            "«Innstillinger for WoW» (alle brytere, også klipp av boss-kills og dødsfall)",
        ]),
        ("Nytt", [
            "Oppdateringsknapp på statistikken i appen – henter ferske tall for alle spill (WoW, Steam og CS2). "
            "På PC-en oppdaterer knappen også WoW-kortet",
        ]),
    ]),
    ("0.24.0", "WoW: egenskaper, talenter og råd", [
        ("Nytt", [
            "Ny fane «Egenskaper og talenter» under WoW-statistikken – i appen og på PC-en: Armor, Strength, Agility, "
            "Stamina, Intellect, Spirit, Attack/Spell Power, Crit, Hit, Defense, motstand og talentfordelingen",
            "Råd ut fra klasse og spec: hva du bør prioritere, ubrukte talentpoeng, for lite Hit/Spell hit/Defense på "
            "level 60 og om du har mer av en egenskap som gir lite for spec-en din",
            "Kan slås av under Spill → World of Warcraft → «Egenskaper og talenter». Skriv /reload i WoW etter oppdateringen",
        ]),
    ]),
    ("0.23.0", "Mer World of Warcraft – i appen og på PC-en", [
        ("Nytt", [
            "Varsel på telefonen når noen hvisker til deg i WoW, inviterer deg til en gruppe eller nevner deg i guild-chatten",
            "Oversikt over alle karakterene: level, gull, hvor de er og uthvilt XP (regnes ut fram til nå, også når du ikke spiller)",
            "Søk i bagger og bank på alle karakterene («Hvor ligger Linen Cloth?»)",
            "Questloggen, yrker med fremgang, raid- og dungeon-låser og gull over tid per karakter",
            "Varsel når utstyret må repareres og når et yrke må læres videre hos treneren",
            "WoW-skjermbildene kommer i skjermbildene i Kontrollsenter, klare til å deles",
            "Alt kan slås av – én bryter for alt og én per funksjon (Spill → World of Warcraft). "
            "Bare lesing av det WoW og addonen lagrer, ingen automatisering. Skriv /reload i WoW etter en endring",
        ]),
    ]),
    ("0.22.3", "WoW-statistikken oppdateres igjen", [
        ("Rettet", [
            "WoW-statistikken låste seg når en karakter gikk opp i level, så nye tall og karakterer kom aldri fram",
            "En ny karakter med samme navn som en slettet arver ikke lenger den gamles statistikk (addonen kjenner "
            "igjen karakteren på ID-en)",
        ]),
        ("Nytt", [
            "Appen: «Fjern fra listen» på WoW-karakterer du har slettet. Spiller du med den igjen, kommer den tilbake",
        ]),
    ]),
    ("0.22.2", "Samme farge sendes på nytt", [
        ("Rettet", [
            "RGB: et trykk på fargen som allerede er valgt under «Alle enheter» gjorde ingenting. Nå sendes den på nytt "
            "til alle enhetene – nyttig når tastatur, mus eller andre lys har kommet ut av takt",
        ]),
    ]),
    ("0.22.1", "CPU-kjøleren lyser i fast farge", [
        ("Rettet", [
            "RGB: med en fast farge (f.eks. grønn) ble lys på hovedkortets uttak – som CPU-kjøleren – slått av. "
            "Fargene ble sendt før hovedkortet var ferdig med å bytte modus. Nå venter Kontrollsenter litt og sender "
            "fargene to ganger",
        ]),
    ]),
    ("0.22.0", "Del skjermbilder og klipp", [
        ("Nytt", [
            "Appen: Del-knapp på skjermbilder og klipp – også klipp fra de andre PC-ene. Bildet eller klippet hentes "
            "fra PC-en og åpnes i Androids delemeny (Messenger, Snapchat, Disk …). Krever den nye Android-appen",
        ]),
        ("Rettet", [
            "Statistikk på Spill-fanen var kuttet og rotete til du trykket «Vis all statistikk»",
            "«Måneden i tall» viser tekst til venstre og tall til høyre igjen",
        ]),
    ]),
    ("0.21.1", "Jevn dra-bevegelse på fanelinjen", [
        ("Rettet", [
            "Når du drar fingeren langs fanelinjen i appen, hopper ikke glasslinsen lenger tilbake til fanen du startet på",
        ]),
    ]),
    ("0.21.0", "Sveip mellom faner og lys som følger musa", [
        ("Nytt", [
            "Appen: dra fingeren bortover skjermen for å bytte fane – eller dra langs fanelinjen, så følger glasslinsen "
            "fingeren. Trykk virker som før",
            "Knappene i Kontrollsenter (Windows og Linux) lyser sterkest der musepekeren er, som knappene i Windows 11",
        ]),
    ]),
    ("0.20.5", "Verktøy i appen passer skjermen", [
        ("Rettet", [
            "Verktøy-fanen i appen kunne bli bredere enn skjermen mot Windows-PC-er, så fanelinjen ble for lang og "
            "siden kunne skrolles sidelengs. Innholdet klippes nå til skjermbredden",
            "Appen sier fra i feilloggen på PC-en hvis noe likevel blir for bredt, så det kan rettes",
        ]),
    ]),
    ("0.20.4", "Oppdater PC-en fra telefonen", [
        ("Nytt", [
            "Appen: Innstillinger → «Oppdater PC-en» henter siste versjon fra NAS-en og starter Kontrollsenter på nytt "
            "på PC-en – du slipper å gå bort til den",
        ]),
        ("Rettet", [
            "Fanelinjen nederst i appen holder seg alltid innenfor skjermen",
        ]),
    ]),
    ("0.20.3", "Windows-PC-ene og appen fungerer som de skal", [
        ("Rettet", [
            "Appen skalerte feil mot Windows-PC-er: lange Windows-stier og nettverksnavn gjorde siden bredere enn "
            "skjermen, så telefonen zoomet ut. Lange tekster brytes nå, og siden er aldri bredere enn skjermen",
            "Skjermbilder og klipp fra Windows-PC-er: Kontrollsenter finner nå Windows-mappen «Opptak» der den faktisk "
            "ligger (også i OneDrive), og skjermbilder tas med Windows' egen skjermkopi – uten Xbox Game Bar og PowerShell",
            "Skjermbilder får miniatyrbilde uten ffmpeg, og klipp uten miniatyrbilde vises med et pent ikon",
            "«Se på» og skjermbildet på Windows bruker riktige 64-bits typer mot Windows (kunne feile før)",
            "«Se på» på Linux husker tillatelsen til skjermdeling for Kontrollsenter",
            "RGB etter omstart: venter til OpenRGB er klar i stedet for å vise «Mistet kontakt»",
        ]),
    ]),
    ("0.20.2", "Enda lettere, og «Se på» på Linux", [
        ("Forbedret", [
            "Trege sensorer (RAM, NVMe og hovedkortbrikken) leses sjeldnere – CPU og GPU fortsatt hvert sekund – og "
            "vifteturtallet leses bare når du ser på det. Det fjerner små CPU-topper annethvert sekund",
            "Vinduet oppdateres annethvert sekund når det er åpent men ikke i fokus (f.eks. mens du spiller)",
            "Tyngre jobber (hjemmenett, prestasjoner, ønskeliste) spres utover etter oppstart i stedet for å kjøre samtidig",
        ]),
        ("Rettet", [
            "«Se på» på Linux kunne stoppe med «forhandlingsproblem» – bildet hentes nå på en måte som virker med "
            "skjermkortminne, og flere oppsett prøves automatisk",
        ]),
    ]),
    ("0.20.1", "Raskere og lettere", [
        ("Forbedret", [
            "Bruker langt mindre CPU: rundt 60 % mindre med vinduet åpent og rundt 90 % mindre når det ligger i "
            "bakgrunnen – vinduet oppdateres bare når det vises, mens varsler, viftekurve, historikk og mobilappen "
            "fortsatt får ferske tall",
            "Temperaturer, NVIDIA-data og prosessøk (spill, klipp, shadere) leses smartere og mellomlagres",
            "Appen: bakgrunnen står stille (mindre GPU-bruk), og «Batterisparing» – eller under 20 % batteri – slår av "
            "uskarpheten bak kortene",
        ]),
        ("Rettet", [
            "«Skjermen live» i appen er nå én knapp som åpner «Se på» (den gamle bilde-for-bilde-visningen er fjernet)",
            "Prestasjoner vises som merker i stedet for knapper som ikke gjorde noe",
            "Ubrukt kode er ryddet bort, og alle knapper er sjekket – på PC-en og i appen",
        ]),
    ]),
    ("0.20.0", "GPU-innstillinger for NVIDIA, AMD og Intel", [
        ("Nytt", [
            "Ny fane «GPU-innstillinger» som bare viser skjermkortene PC-en faktisk har – kraftigste først",
            "NVIDIA: live-tall (temperatur, last, strøm, klokker, VRAM, vifte, PCIe), strømgrense, låst GPU- og "
            "minneklokke og «persistence mode»",
            "AMD: ytelsesnivå, strømprofil og strømgrense (der kortet har det), og OverDrive – GPU- og minneklokke "
            "og spenningsavvik (undervolt), med «Tilbakestill» til fabrikk",
            "Intel: laveste, høyeste og boost-klokke",
            "Spillinnstillinger for Linux (DLSS i Proton, nyeste DLSS, stor shader-cache, raytracing på AMD, FSR, "
            "MangoHud) og Windows-grafikk (GPU-planlegging, spill i vindu, VRR)",
            "Valgfritt: bruk innstillingene dine igjen hver gang PC-en starter",
        ]),
    ]),
    ("0.19.0", "Widgets overalt og glød på knappene", [
        ("Nytt", [
            "Seks widgets: Kontrollsenter, Temperaturer, Hurtigknapper (spillmodus, klipp, lås, demp), Familien "
            "(hva de andre spiller + «Middag!»), Batterier og Spilletid i dag",
            "Android: hold fingeren på hjemskjermen → Widgets → Kontrollsenter",
            "Linux (KDE): Verktøy → Widgets → Installer, så «Legg til widgets» og søk «Kontrollsenter» – virker på "
            "skrivebordet og i panelet",
            "Windows (og Linux uten KDE): glass-widgets på skrivebordet fra Verktøy → Widgets – dra dem dit du vil, "
            "valgfritt «Alltid øverst»",
            "Tøff glød når musa er over knapper, brytere og valg – på eller av – på PC-en og i appen på nettbrett med mus",
        ]),
    ]),
    ("0.18.1", "Familie-fanen og «Se på» på Hjem", [
        ("Nytt", [
            "Ny fane «Familie» i sidemenyen: familiekontroll med kode øverst, «Se på» skjermen til de andre PC-ene "
            "(med forklaring hvis en PC trenger nyere versjon), og familie-chat, «Middag!», ekstra spilletid og leggetid",
            "I appen: «📺 Se på» først blant hurtigknappene på Hjem, og familiekontroll rett i Familie-kortet",
            "Kontrollsenter starter seg selv på nytt etter en oppdatering når vinduet er skjult og ingen spill kjører – "
            "så nye funksjoner faktisk blir tatt i bruk",
        ]),
    ]),
    ("0.18.0", "Flytende glass og familiekontroll med kode", [
        ("Nytt", [
            "Flytende glass på Linux, Windows og i mobilappen: glassaktige kort og knapper med lysrefleks i kanten, "
            "speilende skinn og farger som skinner gjennom. I appen glir en glasslinse mellom fanene. "
            "Kan slås av (Verktøy → Bakgrunn og varsler, og Innstillinger → Utseende i appen)",
            "Familiekontroll: velg en kode som trengs for å lukke Kontrollsenter. Lukkes vinduet, fortsetter "
            "programmet i bakgrunnen. Koden beskytter også familieinnstillingene, ekstra spilletid og bakgrunn/oppstart",
            "Slå familiekontroll av og på – og nullstill en glemt kode – fra telefonen (Spill → Familie)",
        ]),
    ]),
    ("0.17.1", "Elegante valglister og ryddige spillnavn", [
        ("Nytt", [
            "Alle nedtrekkslister i appen er byttet ut med en pen velger som glir opp nedenfra – med grupper, "
            "bilder, undertekst, hake på det valgte og søk i lange lister",
            "Statistikk: spillene er gruppert (World of Warcraft, Steam per konto) med Steam-bilde og timer spilt, "
            "og WoW-figurene vises som «Arthur – Level 1 · Human Warrior · Realm 8 PvP» med klasseikon",
            "Riktige spillnavn: «Counter-Strike 2» i stedet for «ValveTestApp260», «PUBG: Battlegrounds» osv.",
            "Tilbakeknappen på telefonen lukker velgeren, «Se på» og søket før den går til PC-lista",
        ]),
        ("Rettet", [
            "En feil i appen siden 0.15.0 stoppet mye av Verktøy- og Innstillinger-fanen (knappebord, hjemmenett, "
            "sikkerhetssjekk, Hue, RustDesk, søk og mer) – alt er tilbake",
            "Klipp-knappene står to og to, valgt hurtigtast vises tydelig, og lengdevalgene brytes ikke",
        ]),
    ]),
    ("0.17.0", "Ny drakt for mobilappen", [
        ("Nytt", [
            "Mobilappen har fått et helt nytt utseende: nattblå bakgrunn med nordlys, glasskort, flytende fanelinje "
            "og rolig, ryddig tekst – i mørkt og lyst tema",
            "PC-lista er bygget om: navn og status øverst, temperatur og strøm i egne bokser, og knappene "
            "(Åpne, Slå på) på en egen rad – de står aldri over teksten lenger",
            "Hurtigknappene på Hjem kan skyves sidelengs og viser hele teksten; målerne står i et jevnt rutenett",
            "Knapper på rad deler plassen likt, og lange statistikklister foldes sammen («Vis all statistikk»)",
        ]),
    ]),
    ("0.16.0", "Se på hva de andre spiller", [
        ("Nytt", [
            "«📺 Se på»: se skjermen til en annen PC i huset live – som casting fra Meta Quest. Bare visning, ingen kan "
            "styre PC-en, og den som blir sett på får beskjed",
            "Fra telefonen: Spill → Familie → «📺 Se på» ved PC-en (fullskjerm, snu telefonen for stort bilde). "
            "Telefonen trenger bare å være paret med én PC",
            "Fra PC-ene: «Se på»-knapp på kortene under PC-er hjemme (dobbeltklikk for fullskjerm)",
            "«Skjermen live» i appen viser nå jevn video i stedet for et bilde hvert par sekunder",
            "Kan slås av per PC: «La andre i huset se skjermen min» (Familie-kortet). Første gang på Linux spør "
            "PC-en om lov til å dele skjermen",
        ]),
    ]),
    ("0.15.0", "Strømming til telefonen, RustDesk og ryddigere skrift", [
        ("Nytt", [
            "Ny fane «Strømming»: spill og se PC-skjermen på telefonen med Sunshine og Moonlight – start/stopp, "
            "start med PC-en, hold i gang (starter igjen hvis den krasjer), paring med PIN og innstillinger",
            "I appen: «Spill på telefonen» åpner Moonlight direkte, og du kan pare telefonen uten å gå til PC-en",
            "RustDesk for fjernhjelp: ID-en vises på PC-en og i appen, og RustDesk kan åpnes og startes herfra",
            "Moonlight på PC-en: spill fra en annen PC i huset",
            "Hver side har en kort forklaring øverst, og kortene på Oversikt forklarer hva de gjør",
        ]),
        ("Rettet", [
            "Ryddigere skrift: mer luft mellom linjene, fast avstand mellom tittel og forklaring og like størrelser overalt",
            "Sunshine sto stoppet etter et krasj – Kontrollsenter starter den nå igjen av seg selv",
        ]),
    ]),
    ("0.14.0", "Nytt design", [
        ("Nytt", [
            "Helt nytt utseende på Linux og Windows: blå–lilla merkevare som i mobilappen, mykere kort med dybde, "
            "rolig lys bakgrunn og samme bredde på alle sider",
            "Sidemenyen er delt i Overvåking, Enheter, Spill og System, med logo, PC-navn og livestatus "
            "(CPU, GPU og watt) nederst",
            "Oversikt starter med en hilsen og en statusbrikke («Alt ser bra ut»), og toppfeltet viser PC-navn og oppetid",
            "Knapper, brytere, glidebrytere og valg følger det nye designet, i både lyst og mørkt tema",
        ]),
    ]),
    ("0.13.2", "RGB tilbake etter hvilemodus", [
        ("Rettet", [
            "RGB (bl.a. CPU-kjøleren på hovedkortets ARGB-uttak) ble mørk etter hvilemodus og etter omstart til du "
            "åpnet RGB-fanen. Nå legges de lagrede fargene inn av seg selv ved oppstart og hver gang PC-en våkner",
        ]),
    ]),
    ("0.13.1", "Batteri i mus og hodesett", [
        ("Nytt", [
            "Batteriprosent for alle trådløse enheter – mus, tastatur og hodesett – øverst på Oversikt, på "
            "Logitech-siden og på Hjem i appen",
            "Hodesett (Logitech G PRO X 2, G733, G535, G435, G933/G935 m.fl.) leses med HeadsetControl, som kan "
            "installeres med én knapp. Varsel om lavt batteri gjelder nå også hodesettet",
        ]),
    ]),
    ("0.13.0", "Familie, knappebord og mye mer", [
        ("Nytt", [
            "Familie: chat og «Middag!» til én eller alle PC-ene (vises over spillet med lyd), ekstra spilletid som "
            "belønning, leggetid som slår av PC-en, oversikt og ranking for alle PC-ene, og «Bli med» i samme spill",
            "Sikkerhetskopi og gjenoppretting av alle innstillinger på NAS-en, selvtest, feilrapport med ett trykk, "
            "og automatisk oppdatering om natten som rulles tilbake hvis den nye versjonen ikke starter",
            "Ytelse per spill (FPS, temperatur, strømkostnad), skjermkortdriver og varsel når Steam lager shadere",
            "Oppstartsprogrammer, enheter på hjemmenettet (varsel om nye), sikkerhetssjekk og Philips Hue-lys",
            "Tilbud på Steam-ønskelisten, prestasjoner og «Måneden i tall»",
            "Appen: knappebord (Stream Deck), søk, vis og skjul kort, dashbord for nettbrett, PC-skjermen live, "
            "batterisparing, offline-visning (meldinger sendes når PC-en svarer) og snarveien «Status»",
        ]),
    ]),
    ("0.12.1", "«Bare mens et spill kjører» virker", [
        ("Rettet", [
            "Klipp: «Bare mens et spill kjører» stoppet ikke opptaket, så F8 virket uten spill. Nå stopper opptaket "
            "når ingen spill kjører (60 s etter at spillet er avsluttet), og F8 sier fra",
            "Spill utenfor Steam gjenkjennes: World of Warcraft, Diablo, Warcraft III, Overwatch, Hearthstone m.fl.",
            "Flere opptak samtidig (fra en eldre utgave) ryddes bort automatisk",
        ]),
    ]),
    ("0.12.0", "Klipp: galleri, redigering og automatikk", [
        ("Nytt", [
            "Slett, favoritt (★) og miniatyrbilder for klipp – i Spill-fanen på PC-en og i appen",
            "CS2: klipp av seg selv ved 3K, 4K og ACE, kortet ned rundt killene, og hele kampen beholdes ved seier/MVP",
            "WoW: klipp av boss-kills og dødsfall fra kamploggen (skriv /combatlog i spillet)",
            "Flere hurtigtaster: bokmerke (10 s), siste 30 s, siste 5 min, start/stopp opptak og skjermbilde",
            "Kvalitet, bilder per sekund, oppløsning, mikrofon, egne lydspor (spill/Discord/mikrofon) og webkamera",
            "Redigering: klipp til, GIF, kort 720p, jevn lyd, vannmerke, skjul chat, HDR → SDR, montasje med musikk "
            "og «Beste fra uka»",
            "Rydding etter dager eller plass (favoritter beholdes), flytting og deling via NAS-en, delingslenke i 24 t",
            "Lyd og varsel når klipp lagres, pause når du er borte, kontroller (Select + Start), varsel om opptakshelse",
            "Appen: galleri med filter, avspilling med spilldata, last ned til telefonen, statistikk og «denne dagen»",
        ]),
    ]),
    ("0.11.1", "Velg hurtigtast for klipp", [
        ("Nytt", [
            "Velg hurtigtasten selv – en tast eller kombinasjon (F8, F9, Alt+F10, Ctrl+Shift+S …) – og «Test tasten»",
            "Hurtigtasten kan velges og testes fra appen på mobilen også",
        ]),
        ("Rettet", [
            "F8 virket ikke på KDE: hurtigtasten registreres nå direkte hos KDE (uten spørsmål), og virker i spill",
            "Opptaket i bakgrunnen kunne starte flere ganger samtidig",
        ]),
    ]),
    ("0.11.0", "Klipp – opptak i bakgrunnen", [
        ("Nytt", [
            "Klipp (som Medal/ShadowPlay): spillet tas opp i bakgrunnen, og F8 lagrer de siste sekundene som video",
            "Velg lengden selv (15 s – 5 min) og om opptaket bare skal gå mens et spill kjører",
            "Linux: GPU Screen Recorder (skjermkortets videokoder, med lyd) – installeres med én knapp. "
            "Windows: Xbox Game Bar sitt «Ta opp det som skjedde»",
            "Android: «Lagre klipp» på Hjem, hurtigflis i nedtrekksmenyen, og se eller slett klippene i appen",
        ]),
    ]),
    ("0.10.1", "Enkel visning kan slås av igjen", [
        ("Rettet", [
            "Appen: i enkel visning forsvant innstillingene, så den kunne ikke slås av. Innstillinger vises nå alltid, "
            "og Hjem har knappen «Avslutt enkel visning»",
        ]),
    ]),
    ("0.10.0", "Ny, enklere Android-app", [
        ("Nytt utseende", [
            "Appen er ryddet: fem faner – Hjem, Styr, Spill, Verktøy og Innstillinger – nederst på mobilen og som "
            "sidemeny på nettbrettet",
            "Hjem har hurtigknapper for spillmodus, strømmodus, andreskjerm og lås PC-en",
            "Roligere og mer elegant design med mørkt tema som standard; sjeldne valg er foldet sammen",
            "Ny startside med samme utseende",
        ]),
    ]),
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


def last_seen():
    try:
        with open(SEEN) as f:
            return json.load(f).get("version")
    except (OSError, ValueError):
        return None


def _vt(v):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return (0,)


# Illustrasjon og «Vis meg»-side ut fra hva punktet handler om (første treff vinner)
ART = [
    (r"skjermkort|GPU|FPS|HDR|oppløsning|Hz\b", "🖥️", "gpu"), (r"lyd|mikrofon|hodesett|høyttaler", "🎧", "lyd"),
    (r"nattlys|lysstyrke", "🌙", "gpu"), (r"klipp|Medal|opptak|Game Bar", "🎬", "spill"),
    (r"spill|Steam|launcher|Heroic|Lutris", "🎮", "spill"), (r"Discord", "💬", "discord"),
    (r"Familie|leksetid|nettfilter|ukeplan|stjern|belønning|spilletid|leggetid", "👨‍👩‍👧", "familie"),
    (r"Scene", "✨", "scener"), (r"Smart Hjem|Hue|Chromecast|radio|hjemme/borte|strømpris", "🏠", "smarthjem"),
    (r"Strømming|Sunshine|Moonlight|RustDesk|«Se på»", "📡", "stromming"),
    (r"mobil|Android|widget|telefon|ntfy|push", "📱", None), (r"NAS|sikkerhetskopi|oppdatering|selvtest|versjon", "🛡️", "innstillinger"),
    (r"Innstillinger|søk|enkel modus", "⚙️", "innstillinger"), (r"Vedlikehold|oppstart|ytelsestest|vifte", "🔧", "verktoy"),
]


def _art(text):
    import re as _re
    for rx, emoji, page in ART:
        if _re.search(rx, text, _re.I):
            return emoji, page
    return "✨", None


CSS = """
.ks-news-hero { border-radius: 22px; padding: 18px 20px; background-image: linear-gradient(135deg, alpha(@accent_bg_color, .55), alpha(@accent_bg_color, .12)); }
.ks-news-card { border-radius: 18px; padding: 14px; }
.ks-news-art { font-size: 34px; min-width: 56px; min-height: 56px; border-radius: 16px; background: alpha(currentColor, .07); }
.ks-news-ver { font-weight: 800; }
"""


class WhatsNewDialog(Adw.Dialog):
    """«Hva er nytt?» – det nye siden sist øverst som kort med illustrasjon og «Vis meg», eldre versjoner
    sammenfoldet og søkbare."""

    def __init__(self):
        super().__init__(title=i18n.tr("Hva er nytt?"), content_width=760, content_height=760)
        try:
            import theme
            theme.add_css(CSS, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 4)
        except Exception:  # noqa: BLE001
            pass
        seen = last_seen()
        tv = Adw.ToolbarView()
        tv.add_top_bar(Adw.HeaderBar())
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(20)
        new = [n for n in NEWS if seen is None or _vt(n[0]) > _vt(seen)] or NEWS[:1]
        old = [n for n in NEWS if n not in new]
        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        hero.add_css_class("ks-news-hero")
        ht = Gtk.Label(label=i18n.tr("Nytt siden sist") if seen and len(new) > 1 else
                       f"{i18n.tr('Versjon')} {new[0][0]} – {i18n.tr(new[0][1])}", xalign=0, wrap=True)
        ht.add_css_class("title-1")
        hero.append(ht)
        n_items = sum(len(items) for _v, _t, secs in new for _s, items in secs)
        hs = Gtk.Label(label=(f"{len(new)} " + i18n.tr("versjoner") + " · " if len(new) > 1 else "") +
                       f"{n_items} " + i18n.tr("nyheter og forbedringer"), xalign=0)
        hs.add_css_class("dim-label")
        hero.append(hs)
        box.append(hero)
        for ver, title, sections in new:
            if len(new) > 1:
                h = Gtk.Label(label=f"{ver} – {i18n.tr(title)}", xalign=0, margin_top=6)
                h.add_css_class("ks-news-ver")
                h.add_css_class("title-4")
                box.append(h)
            flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=2,
                               min_children_per_line=1, column_spacing=10, row_spacing=10, homogeneous=True)
            for sec, items in sections:
                for it in items:
                    flow.append(self._card(it, sec))
            box.append(flow)
        if old:
            oh = Gtk.Label(label=i18n.tr("Tidligere versjoner"), xalign=0, margin_top=12)
            oh.add_css_class("title-4")
            box.append(oh)
            self.find = Gtk.SearchEntry(placeholder_text=i18n.tr("Søk i alt som er nytt, f.eks. «Discord»"))
            box.append(self.find)
            self.old_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            box.append(self.old_box)
            self.old = old
            self.find.connect("search-changed", lambda *_: self._fill_old())
            self._fill_old()
        sc = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        sc.set_child(box)
        tv.set_content(sc)
        self.set_child(tv)
        mark_seen()

    def _card(self, text, sec):
        emoji, page = _art(text)
        c = Gtk.Box(spacing=12)
        c.add_css_class("card")
        c.add_css_class("ks-news-card")
        art = Gtk.Label(label=emoji, valign=Gtk.Align.START)
        art.add_css_class("ks-news-art")
        c.append(art)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, hexpand=True)
        tag = Gtk.Label(label=i18n.tr(sec).upper(), xalign=0)
        tag.add_css_class("caption-heading")
        tag.add_css_class("dim-label")
        col.append(tag)
        col.append(Gtk.Label(label=i18n.tr(text), xalign=0, wrap=True))
        if page:
            b = Gtk.Button(label=i18n.tr("Vis meg"), halign=Gtk.Align.START)
            b.add_css_class("pill")
            b.add_css_class("suggested-action")
            b.connect("clicked", lambda *_: self._show(page))
            col.append(b)
        c.append(col)
        return c

    def _show(self, page):
        win = self.get_root()
        app_win = win.get_transient_for() if hasattr(win, "get_transient_for") else None
        self.close()
        for w in (app_win, win, Gtk.Application.get_default() and Gtk.Application.get_default().get_active_window()):
            if w is not None and hasattr(w, "stack"):
                w.stack.set_visible_child_name(page)
                break

    def _fill_old(self):
        while (ch := self.old_box.get_first_child()) is not None:
            self.old_box.remove(ch)
        q = self.find.get_text().strip().lower()
        shown = 0
        for ver, title, sections in self.old:
            items = [(sec, it) for sec, its in sections for it in its if not q or q in (it + title).lower()]
            if not items:
                continue
            exp = Gtk.Expander(label=f"{ver} – {i18n.tr(title)}", expanded=bool(q) and shown < 6)
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, margin_start=18, margin_top=4)
            for sec, it in items:
                row = Gtk.Box(spacing=8)
                row.append(Gtk.Label(label=_art(it)[0], yalign=0))
                row.append(Gtk.Label(label=i18n.tr(it), xalign=0, wrap=True, hexpand=True))
                inner.append(row)
            exp.set_child(inner)
            self.old_box.append(exp)
            shown += 1
            if shown >= 60:
                break
