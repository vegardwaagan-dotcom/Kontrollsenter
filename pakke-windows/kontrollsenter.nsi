; Kontrollsenter for Windows 11 – installasjonsfil (NSIS).
; Bygges på Linux med bygg-windows-installer.sh (makensis i en Fedora-container).
;
; Installerer Kontrollsenter i din profil (%LOCALAPPDATA%\Kontrollsenter), og kjører et administratortrinn for det
; som gjelder hele maskinen: MSYS2 med GTK4/libadwaita/Python og LibreHardwareMonitor (installer.ps1 -Admin).

Unicode true
ManifestDPIAware true
SetCompressor /SOLID lzma
!include "MUI2.nsh"
!include "LogicLib.nsh"

!ifndef VIVERSION
  !define VIVERSION "0.0.0.0"
!endif
!ifndef VERSION
  !define VERSION "0.0"
!endif
!define PYW "C:\msys64\ucrt64\bin\pythonw.exe"
!define PY  "C:\msys64\ucrt64\bin\python.exe"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\Kontrollsenter"

Name "Kontrollsenter ${VERSION}"
OutFile "Kontrollsenter-Setup-${VERSION}.exe"
InstallDir "$LOCALAPPDATA\Kontrollsenter\program"
RequestExecutionLevel user
BrandingText "Kontrollsenter ${VERSION} · Vegard E. Wågan"
VIProductVersion "${VIVERSION}"
VIAddVersionKey /LANG=1044 "ProductName" "Kontrollsenter"
VIAddVersionKey /LANG=1044 "FileDescription" "Kontrollsenter – installasjon"
VIAddVersionKey /LANG=1044 "CompanyName" "Vegard E. Wågan"
VIAddVersionKey /LANG=1044 "LegalCopyright" "Copyright © Vegard E. Wågan"
VIAddVersionKey /LANG=1044 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=1044 "ProductVersion" "${VERSION}"

!define MUI_ICON "kontrollsenter.ico"
!define MUI_UNICON "kontrollsenter.ico"
!define MUI_WELCOMEFINISHPAGE_BITMAP "velkommen.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "velkommen.bmp"
!define MUI_ABORTWARNING
!define MUI_COMPONENTSPAGE_NODESC

!define MUI_WELCOMEPAGE_TITLE "Velkommen til Kontrollsenter ${VERSION}"
!define MUI_WELCOMEPAGE_TEXT "Kontrollsenter viser og styrer PC-en din: ytelse, temperaturer, strøm, strømmodus, historikk og PC-ene på hjemmenettet.$\r$\n$\r$\nFørste gang lastes GTK4 (MSYS2) og LibreHardwareMonitor ned. Det tar noen minutter, og Windows ber om administratortilgang én gang.$\r$\n$\r$\nTrykk Neste for å fortsette."
!define MUI_FINISHPAGE_TITLE "Kontrollsenter er installert"
!define MUI_FINISHPAGE_TEXT "Du finner Kontrollsenter på skrivebordet og i Start-menyen. Det kan også ligge som ikon i systemstatusfeltet nede til høyre."
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_FUNCTION StartKontrollsenter
!define MUI_FINISHPAGE_RUN_TEXT "Start Kontrollsenter nå"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Norwegian"

Var Shared

Function StartKontrollsenter
  Exec '"${PYW}" -X utf8 "$INSTDIR\systemmonitor.py"'
FunctionEnd

; ---------------------------------------------------------------------------------------------
Section "Kontrollsenter (påkrevd)" SecMain
  SectionIn RO

  ; 1) Felles programvare (administrator): MSYS2 + GTK4 + Python, LibreHardwareMonitor
  SetShellVarContext all
  StrCpy $Shared "$APPDATA\Kontrollsenter"            ; C:\ProgramData\Kontrollsenter – lesbar for alle kontoer
  SetShellVarContext current
  CreateDirectory "$Shared"
  SetOutPath "$Shared"
  File "installer.ps1"
  File "msi_wmi.ps1"
  Delete "$Shared\installasjon-admin.status"
  DetailPrint "Installerer GTK4, Python og LibreHardwareMonitor (administrator) – kan ta noen minutter første gang …"
  ReadEnvStr $2 USERDOMAIN
  ReadEnvStr $3 USERNAME
  ; skjult PowerShell-vindu – fremdriften vises her, og loggen ligger i installasjon-admin.txt
  ExecShellWait "runas" "powershell.exe" '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "$Shared\installer.ps1" -Admin -Quiet -ForUser "$2\$3"' SW_HIDE
  ClearErrors
  FileOpen $0 "$Shared\installasjon-admin.status" r
  ${If} ${Errors}
    MessageBox MB_ICONSTOP "Administratortrinnet ble ikke fullført (avbrutt, eller Windows ga ikke tilgang).$\r$\n$\r$\nLoggen ligger i $Shared\installasjon-admin.txt"
    Abort
  ${EndIf}
  FileRead $0 $1
  FileClose $0
  StrCpy $1 $1 1
  ${If} $1 != "0"
    MessageBox MB_ICONSTOP "Administratortrinnet feilet. Loggen ligger i $Shared\installasjon-admin.txt"
    Abort
  ${EndIf}
  DetailPrint "GTK4, Python og LibreHardwareMonitor er på plass"

  ; 2) Selve programmet (lukk en kjørende Kontrollsenter først)
  nsExec::Exec 'powershell.exe -NoProfile -Command "Get-Process pythonw -EA 0 | ? { $$_.Path -like ''C:\msys64*'' } | Stop-Process -Force"'
  RMDir /r "$INSTDIR"
  SetOutPath "$INSTDIR"
  File /r "program\*.*"
  DetailPrint "Kontrollsenter ${VERSION} er installert i $INSTDIR"

  ; 3) Start-menyen og feilsøking
  CreateShortCut "$SMPROGRAMS\Kontrollsenter.lnk" "${PYW}" '-X utf8 "$INSTDIR\systemmonitor.py"' "$INSTDIR\icons\kontrollsenter.ico" 0
  FileOpen $0 "$LOCALAPPDATA\Kontrollsenter\Feilsøk Kontrollsenter.cmd" w
  FileWrite $0 "@echo off$\r$\nchcp 65001 >nul$\r$\necho Starter Kontrollsenter med feilsøking ... (lukk vinduet for å avslutte)$\r$\n"
  FileWrite $0 '"${PY}" -X utf8 "$INSTDIR\systemmonitor.py" > "%LOCALAPPDATA%\Kontrollsenter\oppstart.txt" 2>&1$\r$\n'
  FileWrite $0 'type "%LOCALAPPDATA%\Kontrollsenter\oppstart.txt"$\r$\n'
  FileWrite $0 'for %%N in (PERSONALCLOUD 192.168.1.3) do (mkdir "\\%%N\Public\Kontrollsenter\Diagnose" 2>nul & copy /y "%LOCALAPPDATA%\Kontrollsenter\oppstart.txt" "\\%%N\Public\Kontrollsenter\Diagnose\%COMPUTERNAME%-oppstart.txt" >nul 2>&1 && (echo Lagt på NAS-en. & goto ferdig))$\r$\n'
  FileWrite $0 ":ferdig$\r$\npause$\r$\n"
  FileClose $0
  CreateShortCut "$SMPROGRAMS\Kontrollsenter (feilsøking).lnk" "$LOCALAPPDATA\Kontrollsenter\Feilsøk Kontrollsenter.cmd" "" "$INSTDIR\icons\kontrollsenter.ico" 0

  ; 4) Avinstallering (Innstillinger → Apper)
  WriteUninstaller "$LOCALAPPDATA\Kontrollsenter\Avinstaller Kontrollsenter.exe"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayName" "Kontrollsenter"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINST_KEY}" "Publisher" "Vegard E. Wågan"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\icons\kontrollsenter.ico"
  WriteRegStr HKCU "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINST_KEY}" "UninstallString" '"$LOCALAPPDATA\Kontrollsenter\Avinstaller Kontrollsenter.exe"'
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair" 1
SectionEnd

Section "Snarvei på skrivebordet" SecDesktop
  CreateShortCut "$DESKTOP\Kontrollsenter.lnk" "${PYW}" '-X utf8 "$INSTDIR\systemmonitor.py"' "$INSTDIR\icons\kontrollsenter.ico" 0
SectionEnd

Section "Start Kontrollsenter ved innlogging (skjult i systemstatusfeltet)" SecAutostart
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "Kontrollsenter" '"${PYW}" -X utf8 "$INSTDIR\systemmonitor.py" --hidden'
SectionEnd

; ---------------------------------------------------------------------------------------------
Section "Uninstall"
  nsExec::Exec 'powershell.exe -NoProfile -Command "Get-Process pythonw -EA 0 | ? { $$_.Path -like ''C:\msys64*'' } | Stop-Process -Force"'
  RMDir /r "$LOCALAPPDATA\Kontrollsenter\program"
  Delete "$LOCALAPPDATA\Kontrollsenter\Feilsøk Kontrollsenter.cmd"
  Delete "$LOCALAPPDATA\Kontrollsenter\oppstart.txt"
  Delete "$DESKTOP\Kontrollsenter.lnk"
  Delete "$SMPROGRAMS\Kontrollsenter.lnk"
  Delete "$SMPROGRAMS\Kontrollsenter (feilsøking).lnk"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "Kontrollsenter"
  DeleteRegKey HKCU "${UNINST_KEY}"
  Delete "$LOCALAPPDATA\Kontrollsenter\Avinstaller Kontrollsenter.exe"
  RMDir "$LOCALAPPDATA\Kontrollsenter"
  MessageBox MB_ICONINFORMATION "Kontrollsenter er fjernet.$\r$\n$\r$\nInnstillingene dine (.config\systemmonitor), MSYS2 og LibreHardwareMonitor er beholdt – de kan fjernes under Innstillinger → Apper."
SectionEnd
