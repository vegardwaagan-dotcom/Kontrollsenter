"""Lager funksjoner.nsh for Windows-installasjonen ut fra funksjoner.py (installasjonstyper + én boks per funksjon)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import funksjoner as F  # noqa: E402

TYPES = ["full", "medium", "minimal"]                 # InstType 1, 2, 3 (rekkefølgen under)
out = ['; Laget av lag-funksjoner-nsh.py – ikke rediger for hånd', '!include "Sections.nsh"',
       'InstType "Fullstendig – alle funksjoner"',
       'InstType "Medium – uten Discord, Scener, Smart Hjem og CPU-skjerm"',
       'InstType "Minimal – Oversikt, Historikk, GPU, Lyd, Spill, Chat, PC-er, Fjernhjelp og System"',
       'InstType /CUSTOMSTRING=Egendefinert', '']
FEATS = [f for f in F.FEATURES if not f[4]]
out.append('Function .onInit')
out.append('  SetCurInstType ${NSIS_MAX_INST_TYPES}     ; Egendefinert: ingenting valgt på forhånd')
out.append('FunctionEnd')
out.append('')
out.append('!macro KS_FUNKSJONER')
out.append('SectionGroup /e "Funksjoner (kan endres senere under Innstillinger)" SecFeat')
for key, name, _sub, _pages, _req in FEATS:
    types = " ".join(str(i + 1) for i, t in enumerate(TYPES) if key in F.PROFILES[t][2])
    out.append(f'  Section /o "{name}" SecF_{key}')
    if types:
        out.append(f'    SectionIn {types}')
    out.append('  SectionEnd')
out.append('SectionGroupEnd')
out.append('')
# skjult siste seksjon: skriv valget (programmet leser det første gang og viser det i velkomstveiviseren)
out.append('Section "-Funksjonsvalg"')
out.append('  StrCpy $R1 ""')
for key in [f[0] for f in F.FEATURES]:
    if key in F.REQUIRED:
        out.append(f'  StrCpy $R1 \'$R1"{key}",\'')
    else:
        out.append(f'  ${{If}} ${{SectionIsSelected}} ${{SecF_{key}}}')
        out.append(f'    StrCpy $R1 \'$R1"{key}",\'')
        out.append('  ${EndIf}')
out.append('  StrCpy $R1 $R1 -1')
out.append('  GetCurInstType $R2')
out.append('  StrCpy $R3 "custom"')
for i, t in enumerate(TYPES):
    out.append(f'  ${{If}} $R2 == {i}')
    out.append(f'    StrCpy $R3 "{t}"')
    out.append('  ${EndIf}')
out.append('  CreateDirectory "$LOCALAPPDATA\\Kontrollsenter"')
out.append('  FileOpen $0 "$LOCALAPPDATA\\Kontrollsenter\\funksjonsvalg.json" w')
out.append('  FileWrite $0 \'{"profile": "$R3", "on": [$R1]}\'')
out.append('  FileClose $0')
out.append('  DetailPrint "Funksjoner: $R3"')
out.append('SectionEnd')
out.append('!macroend')
open(sys.argv[1], "w", encoding="utf-8").write("\n".join(out) + "\n")
