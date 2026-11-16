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
