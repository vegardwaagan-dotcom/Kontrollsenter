# Kontrollsenter for Windows 11 – installasjon og oppdatering.
#
# To deler, fordi administratordelen kan kjøre som en annen Windows-konto enn deg (og ikke ser NAS-en):
#   Vanlig del (deg):  henter Kontrollsenter fra NAS-en, installerer i din profil, snarveier, oppstart, logg
#   Administratordel:  MSYS2 med GTK4/libadwaita/Python, LibreHardwareMonitor + PawnIO (felles for maskinen)
param([switch]$Admin, [string]$ForUser = "", [switch]$Quiet)   # -Quiet: skjult vindu (fra Setup.exe)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
function Blue($t)  { Write-Host "`n== $t ==" -ForegroundColor Cyan }
function Green($t) { Write-Host "✓ $t" -ForegroundColor Green }
function Warn($t)  { Write-Host "! $t" -ForegroundColor Yellow }

# NAS-adressen: samme som skriptet ble startet fra (f.eks. \\PERSONALCLOUD\…). Windows lagrer påloggingen per
# navn, så IP-adressen kan gi «Brukernavnet eller passordet er feil» selv om navnet virker.
$cands = @()
if ($PSScriptRoot -like "\\*") { $cands += (Split-Path $PSScriptRoot -Parent) }
$cands += @("\\PERSONALCLOUD\Public\Kontrollsenter", "\\192.168.1.3\Public\Kontrollsenter")
$NAS = $cands[0]
foreach ($c in $cands) { if (Test-Path "$c\Kontrollsenter.tar.gz" -ErrorAction SilentlyContinue) { $NAS = $c; break } }
$SHARED = Join-Path $env:ProgramData "Kontrollsenter"          # lesbar for alle kontoer
$MSYS   = "C:\msys64"
$PY     = "$MSYS\ucrt64\bin\python.exe"
$PYW    = "$MSYS\ucrt64\bin\pythonw.exe"
$LHMDIR = Join-Path $env:ProgramFiles "LibreHardwareMonitor"
New-Item -ItemType Directory -Force -Path $SHARED | Out-Null

# =====================================================================================================
# ADMINISTRATORDEL – bare det som gjelder hele maskinen
# =====================================================================================================
if ($Admin) {
    $ALOG = Join-Path $SHARED "installasjon-admin.txt"
    Start-Transcript -Path $ALOG -Force | Out-Null
    $code = 1
    try {
        Blue "GTK4 og Python (MSYS2)"
        if (-not (Test-Path "$MSYS\usr\bin\bash.exe")) {
            if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
                throw "winget mangler – oppdater «Programinstallasjon» (App Installer) i Microsoft Store."
            }
            winget install -e --id MSYS2.MSYS2 --silent --accept-package-agreements --accept-source-agreements | Out-Host
            if (-not (Test-Path "$MSYS\usr\bin\bash.exe")) { throw "MSYS2 ble ikke installert til $MSYS" }
        }
        $pkgs = "mingw-w64-ucrt-x86_64-python mingw-w64-ucrt-x86_64-gtk4 mingw-w64-ucrt-x86_64-libadwaita " +
                "mingw-w64-ucrt-x86_64-python-gobject mingw-w64-ucrt-x86_64-python-psutil " +
                "mingw-w64-ucrt-x86_64-python-cairo mingw-w64-ucrt-x86_64-adwaita-icon-theme"
        $env:MSYSTEM = "UCRT64"; $env:CHERE_INVOKING = "1"
        & "$MSYS\usr\bin\bash.exe" -lc "pacman -Syu --noconfirm" | Out-Host     # 1. gang: kjernepakker
        & "$MSYS\usr\bin\bash.exe" -lc "pacman -Syu --noconfirm" | Out-Host     # 2. gang: resten
        & "$MSYS\usr\bin\bash.exe" -lc "pacman -S --needed --noconfirm $pkgs" | Out-Host
        & $PY -c "import gi; gi.require_version('Gtk','4.0'); gi.require_version('Adw','1'); from gi.repository import Gtk, Adw; import psutil; print('GTK', Gtk.get_major_version(), Gtk.get_minor_version())"
        if ($LASTEXITCODE -ne 0) { throw "GTK4/libadwaita virker ikke i MSYS2 – se meldingene over." }
        Green "GTK4, libadwaita og Python er klare"

        Blue "LibreHardwareMonitor (temperaturer, vifter og strøm)"
        if (-not (Test-Path "$LHMDIR\LibreHardwareMonitor.exe")) {
            $rel = Invoke-RestMethod "https://api.github.com/repos/LibreHardwareMonitor/LibreHardwareMonitor/releases/latest" `
                     -Headers @{ "User-Agent" = "Kontrollsenter" }
            # .NET Framework-utgaven (net472) følger med Windows – .NET 8-utgaven krever egen runtime
            $asset = ($rel.assets | Where-Object { $_.name -match "\.zip$" } |
                      Sort-Object { if ($_.name -match "net4") { 0 } elseif ($_.name -match "net\d") { 2 } else { 1 } }) |
                     Select-Object -First 1
            if (-not $asset) { throw "Fant ingen nedlasting av LibreHardwareMonitor" }
            $zip = Join-Path $SHARED $asset.name
            Invoke-WebRequest $asset.browser_download_url -OutFile $zip -UseBasicParsing
            Expand-Archive $zip -DestinationPath $LHMDIR -Force
            Remove-Item $zip -Force
            $exe = Get-ChildItem $LHMDIR -Recurse -Filter LibreHardwareMonitor.exe | Select-Object -First 1
            if ($exe.DirectoryName -ne $LHMDIR) { Get-ChildItem $exe.DirectoryName | Move-Item -Destination $LHMDIR -Force }
            Green "LibreHardwareMonitor $($rel.tag_name) er installert"
        }
        try {   # nyere LibreHardwareMonitor bruker PawnIO-driveren for å lese hovedkortbrikkene
            winget install -e --id namazso.PawnIO --silent --accept-package-agreements --accept-source-agreements | Out-Host
        } catch { Warn "PawnIO kunne ikke installeres automatisk: $_" }
        try {   # OpenRGB styrer RGB-lys fra Kontrollsenter (valgfritt – hoppes over hvis det feiler)
            if (-not (Get-Command OpenRGB.exe -ErrorAction SilentlyContinue) -and
                -not (Test-Path "$env:ProgramFiles\OpenRGB\OpenRGB.exe")) {
                # pakken heter OpenRGB.OpenRGB i dag (tidligere CalcProgrammer1.OpenRGB)
                foreach ($id in "OpenRGB.OpenRGB", "CalcProgrammer1.OpenRGB") {
                    winget install -e --id $id --scope machine --silent --accept-package-agreements --accept-source-agreements | Out-Host
                    if ($LASTEXITCODE -eq 0) { Green "OpenRGB er installert"; break }
                }
            }
        } catch { Warn "OpenRGB kunne ikke installeres automatisk: $_" }
        # deler målingene bare lokalt på port 8085
        @"
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <appSettings>
    <add key="startMinMenuItem" value="true" />
    <add key="minTrayMenuItem" value="true" />
    <add key="minCloseMenuItem" value="true" />
    <add key="runWebServerMenuItem" value="true" />
    <add key="listenerPort" value="8085" />
  </appSettings>
</configuration>
"@ | Set-Content -Encoding UTF8 "$LHMDIR\LibreHardwareMonitor.config"
        # starter ved innlogging for brukeren (med administratorrettigheter), med ikon i statusfeltet –
        # da vises også eventuelle spørsmål fra LibreHardwareMonitor. Uten kjent bruker: SYSTEM ved oppstart.
        $task = "Kontrollsenter - LibreHardwareMonitor"
        $act  = New-ScheduledTaskAction -Execute "$LHMDIR\LibreHardwareMonitor.exe" -WorkingDirectory $LHMDIR
        $set  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0
        if ($ForUser) {
            $trg = New-ScheduledTaskTrigger -AtLogOn -User $ForUser
            $prn = New-ScheduledTaskPrincipal -UserId $ForUser -LogonType Interactive -RunLevel Highest
        } else {
            $trg = New-ScheduledTaskTrigger -AtStartup
            $prn = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
        }
        Register-ScheduledTask -TaskName $task -Action $act -Trigger $trg -Settings $set -Principal $prn -Force | Out-Null
        Get-Process LibreHardwareMonitor -ErrorAction SilentlyContinue | Stop-Process -Force
        Start-ScheduledTask -TaskName $task
        Green "LibreHardwareMonitor kjører i bakgrunnen og starter med Windows"

        # MSI-innstillinger (brukerscenario, Cooler Boost, batterigrense …) via MSI sitt WMI-grensesnitt.
        # Skriptet legges i Program Files (bare administratorer kan endre det), og oppgaven lar Kontrollsenter
        # kjøre det med administratorrett uten UAC-spørsmål. Skriptet skriver bare faste, kjente verdier.
        $msiSrc = Join-Path $PSScriptRoot "msi_wmi.ps1"
        $isMsi = (Get-CimInstance Win32_ComputerSystem).Manufacturer -match "Micro-Star|MSI"
        if ($isMsi -and $ForUser -and (Test-Path $msiSrc)) {
            $PF = Join-Path $env:ProgramFiles "Kontrollsenter"
            New-Item -ItemType Directory -Force -Path $PF | Out-Null
            Copy-Item $msiSrc "$PF\msi_wmi.ps1" -Force
            # conhost --headless: PowerShell uten noe vindu (ikke engang et blink)
            $mact = New-ScheduledTaskAction -Execute "conhost.exe" `
                -Argument "--headless powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PF\msi_wmi.ps1`""
            $mprn = New-ScheduledTaskPrincipal -UserId $ForUser -LogonType Interactive -RunLevel Highest
            $mset = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
                -ExecutionTimeLimit (New-TimeSpan -Minutes 2) -MultipleInstances Queue
            Register-ScheduledTask -TaskName "Kontrollsenter - MSI" -Action $mact -Settings $mset -Principal $mprn `
                -Force | Out-Null
            Green "MSI-styring er satt opp"
        }
        $code = 0
    } catch {
        Write-Host "`n✗ Administratordelen stoppet: $_" -ForegroundColor Red
        Write-Host $_.ScriptStackTrace -ForegroundColor DarkGray
        if (-not $Quiet) { Read-Host "Trykk Enter for å lukke" | Out-Null }
    } finally {
        Stop-Transcript | Out-Null
        Set-Content -Path (Join-Path $SHARED "installasjon-admin.status") -Value $code
    }
    exit $code
}

# =====================================================================================================
# VANLIG DEL – kjører som deg
# =====================================================================================================
$DEST = Join-Path $env:LOCALAPPDATA "Kontrollsenter"
$PROG = Join-Path $DEST "program"
$TMP  = Join-Path $env:TEMP ("kontrollsenter-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
$LOG  = Join-Path $env:TEMP "kontrollsenter-installasjon.txt"
New-Item -ItemType Directory -Force -Path $TMP, $DEST | Out-Null
Start-Transcript -Path $LOG -Force | Out-Null
Write-Host "Kontrollsenter – installasjon for Windows" -ForegroundColor White
$ok = $false
try {
    Blue "1/5 Henter Kontrollsenter fra NAS-en"
    if (-not (Test-Path "$NAS\Kontrollsenter.tar.gz")) { throw "Ser ikke $NAS\Kontrollsenter.tar.gz – er du på hjemmenettet?" }
    $pkg = Join-Path $TMP "Kontrollsenter.tar.gz"
    Copy-Item "$NAS\Kontrollsenter.tar.gz" $pkg
    $want = (Get-Content "$NAS\SHA256SUMS" | Select-Object -First 1).Split(" ")[0].Trim().ToLower()
    $got  = (Get-FileHash $pkg -Algorithm SHA256).Hash.ToLower()
    if ($want -ne $got) { throw "Sjekksummen stemmer ikke – pakken på NAS-en er ødelagt." }
    # installeringsskriptet kopieres lokalt, så administratordelen kan kjøre det uten NAS-tilgang
    $ADMINPS = Join-Path $SHARED "installer.ps1"
    Copy-Item $PSCommandPath $ADMINPS -Force
    $msiPs = Join-Path $PSScriptRoot "msi_wmi.ps1"
    if (Test-Path $msiPs) { Copy-Item $msiPs (Join-Path $SHARED "msi_wmi.ps1") -Force }
    Green "Hentet og kontrollert"

    Blue "2/5 Felles programvare (administrator)"
    Remove-Item (Join-Path $SHARED "installasjon-admin.status") -Force -ErrorAction SilentlyContinue
    Write-Host "Windows ber nå om administratortilgang (GTK4, Python og LibreHardwareMonitor) …"
    Start-Process powershell -Verb RunAs -Wait `
        -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$ADMINPS`" -Admin -ForUser `"$env:USERDOMAIN\$env:USERNAME`""
    $st = Get-Content (Join-Path $SHARED "installasjon-admin.status") -ErrorAction SilentlyContinue
    if ("$st".Trim() -ne "0") { throw "Administratordelen ble ikke fullført (se loggen over)." }
    Get-Content (Join-Path $SHARED "installasjon-admin.txt") -ErrorAction SilentlyContinue | Out-Host
    Green "GTK4, Python og LibreHardwareMonitor er på plass"

    Blue "3/5 Kontrollsenter"
    tar -xzf $pkg -C $TMP
    if (-not (Test-Path "$TMP\Kontrollsenter\program\systemmonitor.py")) { throw "Pakken mangler programfilene." }
    Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$MSYS*" } | Stop-Process -Force
    if (Test-Path $PROG) { Remove-Item $PROG -Recurse -Force }
    Copy-Item "$TMP\Kontrollsenter\program" $PROG -Recurse
    Green "Kontrollsenter $(Get-Content "$PROG\VERSION") er installert i $PROG"

    $cfgdir = Join-Path $env:USERPROFILE ".config\systemmonitor"
    New-Item -ItemType Directory -Force -Path $cfgdir | Out-Null
    $cfgfile = Join-Path $cfgdir "oppdatering.json"
    $cfg = @{}
    if (Test-Path $cfgfile) {
        try { (Get-Content $cfgfile -Raw | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $cfg[$_.Name] = $_.Value } } catch {}
    }
    $cfg["lan"] = "//" + ($NAS -replace "\\", "/").TrimStart("/")      # \\PERSONALCLOUD\… -> //PERSONALCLOUD/…
    [IO.File]::WriteAllText($cfgfile, ($cfg | ConvertTo-Json), (New-Object Text.UTF8Encoding $false))
    Green "NAS-adresse for oppdateringer: $NAS"

    Blue "4/5 Snarveier"
    $sh = New-Object -ComObject WScript.Shell
    $icon = "$PROG\icons\kontrollsenter.ico"
    $startmenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
    foreach ($dir in @([Environment]::GetFolderPath("Desktop"), $startmenu)) {
        $lnk = $sh.CreateShortcut((Join-Path $dir "Kontrollsenter.lnk"))
        $lnk.TargetPath = $PYW; $lnk.Arguments = "-X utf8 `"$PROG\systemmonitor.py`""
        $lnk.WorkingDirectory = $PROG; $lnk.IconLocation = $icon; $lnk.Description = "Kontrollsenter"
        $lnk.Save()
    }
    # feilsøking: starter med konsoll og legger utskriften på NAS-en
    $dbg = @"
@echo off
chcp 65001 >nul
echo Starter Kontrollsenter med feilsøking ... (lukk vinduet for å avslutte)
"$PY" -X utf8 "$PROG\systemmonitor.py" > "%TEMP%\kontrollsenter-oppstart.txt" 2>&1
type "%TEMP%\kontrollsenter-oppstart.txt"
mkdir "$NAS\Diagnose" 2>nul
copy /y "%TEMP%\kontrollsenter-oppstart.txt" "$NAS\Diagnose\%COMPUTERNAME%-oppstart.txt" >nul && echo Lagt på NAS-en.
pause
"@
    [IO.File]::WriteAllText("$DEST\Feilsøk Kontrollsenter.cmd", $dbg, (New-Object Text.UTF8Encoding $false))
    $lnk = $sh.CreateShortcut((Join-Path $startmenu "Kontrollsenter (feilsøking).lnk"))
    $lnk.TargetPath = "$DEST\Feilsøk Kontrollsenter.cmd"; $lnk.IconLocation = $icon; $lnk.Save()
    Green "Snarvei på skrivebordet og i Start-menyen"

    Blue "5/5 Oppstart"
    $ans = Read-Host "Starte Kontrollsenter skjult ved innlogging? (J/n)"
    $run = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
    if ($ans -notmatch "^[nN]") {
        Set-ItemProperty $run -Name "Kontrollsenter" -Value "`"$PYW`" -X utf8 `"$PROG\systemmonitor.py`" --hidden"
        Green "Starter ved innlogging"
    } else {
        Remove-ItemProperty $run -Name "Kontrollsenter" -ErrorAction SilentlyContinue
    }
    Start-Process $PYW -ArgumentList "-X utf8 `"$PROG\systemmonitor.py`"" -WorkingDirectory $PROG
    Green "Ferdig! Kontrollsenter starter nå."
    $ok = $true
} catch {
    Write-Host "`n✗ Installasjonen stoppet: $_" -ForegroundColor Red
    Write-Host $_.ScriptStackTrace -ForegroundColor DarkGray
} finally {
    Stop-Transcript | Out-Null
    Remove-Item $TMP -Recurse -Force -ErrorAction SilentlyContinue
    # begge loggene legges på NAS-en, så feil kan finnes uten at du må kopiere noe
    try {
        New-Item -ItemType Directory -Force -Path "$NAS\Diagnose" | Out-Null
        $all = (Get-Content $LOG -Raw -ErrorAction SilentlyContinue) + "`n`n===== ADMINISTRATORDEL =====`n" +
               (Get-Content (Join-Path $SHARED "installasjon-admin.txt") -Raw -ErrorAction SilentlyContinue)
        [IO.File]::WriteAllText("$NAS\Diagnose\$env:COMPUTERNAME-installasjon.txt", $all, (New-Object Text.UTF8Encoding $false))
        Write-Host "Installasjonsloggen er lagt på NAS-en (Kontrollsenter\Diagnose)." -ForegroundColor DarkGray
    } catch { Write-Host "Kunne ikke legge loggen på NAS-en: $_" -ForegroundColor DarkGray }
}
