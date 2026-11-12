# Kontrollsenter for Windows 11 – installasjon og oppdatering.
#
#  1. MSYS2 (GTK4 + libadwaita + Python + PyGObject + psutil) – samme brukerflate som på Linux
#  2. LibreHardwareMonitor – temperaturer, vifter og watt; starter ved innlogging med administratorrettigheter
#     og deler målingene bare lokalt (http://127.0.0.1:8085)
#  3. Kontrollsenter hentes fra NAS-en (Kontrollsenter.tar.gz, sjekksum kontrolleres) til %LOCALAPPDATA%
#  4. Snarveier på skrivebordet og i Start-menyen, og (valgfritt) oppstart ved innlogging
param([string]$Source = $PSScriptRoot, [switch]$Elevated)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
function Blue($t)  { Write-Host "`n== $t ==" -ForegroundColor Cyan }
function Green($t) { Write-Host "✓ $t" -ForegroundColor Green }
function Warn($t)  { Write-Host "! $t" -ForegroundColor Yellow }

# --- administratorrettigheter (trengs for LibreHardwareMonitor og planlagt oppgave) ---------------
$NAS     = "\\192.168.1.3\Public\Kontrollsenter"
$LOG     = Join-Path $env:TEMP "kontrollsenter-installasjon.txt"
# Administratordelen kjører i en egen Windows-økt som IKKE ser NAS-delingen (påloggingen mot NAS-en gjelder bare
# den vanlige økten). Derfor kopierer den vanlige delen alt som trengs til en lokal mappe først.
if (-not $Elevated) {
    $STAGE = Join-Path $env:TEMP "kontrollsenter-installer"
    Remove-Item $STAGE -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $STAGE | Out-Null
    Write-Host "Henter Kontrollsenter fra NAS-en …"
    try {
        foreach ($f in @("Kontrollsenter.tar.gz", "SHA256SUMS", "VERSION")) { Copy-Item (Join-Path $NAS $f) $STAGE }
        Copy-Item $PSCommandPath (Join-Path $STAGE "installer.ps1")
    } catch {
        Write-Host "✗ Fikk ikke hentet filene fra NAS-en ($NAS): $_" -ForegroundColor Red
        Read-Host "Trykk Enter for å lukke" | Out-Null
        exit 1
    }
    Write-Host "Kontrollsenter trenger administratortilgang én gang (Windows spør nå)."
    $argList = "-NoProfile -ExecutionPolicy Bypass -File `"$STAGE\installer.ps1`" -Source `"$STAGE`" -Elevated"
    Start-Process powershell -Verb RunAs -ArgumentList $argList -Wait
    # loggen legges på NAS-en herfra (den vanlige økten ser NAS-en)
    try {
        New-Item -ItemType Directory -Force -Path "$NAS\Diagnose" | Out-Null
        Copy-Item $LOG "$NAS\Diagnose\$env:COMPUTERNAME-installasjon.txt" -Force
        Write-Host "Installasjonsloggen er lagt på NAS-en (Kontrollsenter\Diagnose)." -ForegroundColor DarkGray
    } catch { Write-Host "Kunne ikke legge loggen på NAS-en: $LOG" -ForegroundColor DarkGray }
    exit
}

$MSYS    = "C:\msys64"
$PY      = "$MSYS\ucrt64\bin\python.exe"
$PYW     = "$MSYS\ucrt64\bin\pythonw.exe"
$DEST    = Join-Path $env:LOCALAPPDATA "Kontrollsenter"
$PROG    = Join-Path $DEST "program"
$LHMDIR  = Join-Path $env:ProgramFiles "LibreHardwareMonitor"
$TMP     = Join-Path $env:TEMP ("kontrollsenter-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Force -Path $TMP, $DEST | Out-Null
Start-Transcript -Path $LOG -Force | Out-Null
Write-Host "Kontrollsenter – installasjon for Windows" -ForegroundColor White
$ok = $false
try {

# --- 1. MSYS2 + GTK4 ----------------------------------------------------------------------------------
Blue "1/5 GTK4 og Python (MSYS2)"
if (-not (Test-Path "$MSYS\usr\bin\bash.exe")) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw "winget mangler – oppdater «Programinstallasjon» i Microsoft Store." }
    winget install -e --id MSYS2.MSYS2 --silent --accept-package-agreements --accept-source-agreements
    if (-not (Test-Path "$MSYS\usr\bin\bash.exe")) { throw "MSYS2 ble ikke installert til $MSYS" }
}
$pkgs = "mingw-w64-ucrt-x86_64-python mingw-w64-ucrt-x86_64-gtk4 mingw-w64-ucrt-x86_64-libadwaita " +
        "mingw-w64-ucrt-x86_64-python-gobject mingw-w64-ucrt-x86_64-python-psutil " +
        "mingw-w64-ucrt-x86_64-python-cairo mingw-w64-ucrt-x86_64-adwaita-icon-theme"
$env:MSYSTEM = "UCRT64"; $env:CHERE_INVOKING = "1"
& "$MSYS\usr\bin\bash.exe" -lc "pacman -Syu --noconfirm" | Out-Host          # første gang: kjernepakker
& "$MSYS\usr\bin\bash.exe" -lc "pacman -Syu --noconfirm" | Out-Host          # andre gang: resten
& "$MSYS\usr\bin\bash.exe" -lc "pacman -S --needed --noconfirm $pkgs" | Out-Host
& $PY -c "import gi; gi.require_version('Gtk','4.0'); gi.require_version('Adw','1'); from gi.repository import Gtk, Adw; import psutil; print('GTK', Gtk.get_major_version(), Gtk.get_minor_version())"
if ($LASTEXITCODE -ne 0) { throw "GTK4/libadwaita virker ikke i MSYS2 – se meldingene over." }
Green "GTK4, libadwaita og Python er klare"

# --- 2. LibreHardwareMonitor ----------------------------------------------------------------------------
Blue "2/5 LibreHardwareMonitor (temperaturer, vifter og strøm)"
if (-not (Test-Path "$LHMDIR\LibreHardwareMonitor.exe")) {
    $rel = Invoke-RestMethod "https://api.github.com/repos/LibreHardwareMonitor/LibreHardwareMonitor/releases/latest" `
             -Headers @{ "User-Agent" = "Kontrollsenter" }
    # .NET Framework-utgaven (net472) følger med Windows – .NET 8-utgaven krever egen runtime
    $asset = ($rel.assets | Where-Object { $_.name -match "\.zip$" } |
              Sort-Object { if ($_.name -match "net4") { 0 } elseif ($_.name -match "net\d") { 2 } else { 1 } }) |
             Select-Object -First 1
    if (-not $asset) { throw "Fant ingen nedlasting av LibreHardwareMonitor" }
    $zip = Join-Path $TMP $asset.name
    Invoke-WebRequest $asset.browser_download_url -OutFile $zip -UseBasicParsing
    Expand-Archive $zip -DestinationPath $LHMDIR -Force
    $exe = Get-ChildItem $LHMDIR -Recurse -Filter LibreHardwareMonitor.exe | Select-Object -First 1
    if ($exe.DirectoryName -ne $LHMDIR) { Get-ChildItem $exe.DirectoryName | Move-Item -Destination $LHMDIR -Force }
    Green "LibreHardwareMonitor $($rel.tag_name) er installert"
}
# nyere LibreHardwareMonitor bruker PawnIO-driveren for å lese hovedkortbrikkene
try {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install -e --id namazso.PawnIO --silent --accept-package-agreements --accept-source-agreements | Out-Host
    }
} catch { Warn "PawnIO kunne ikke installeres automatisk: $_" }
# start minimert i statusfeltet, med lokal webdeling på port 8085
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
$task = "Kontrollsenter - LibreHardwareMonitor"
$act  = New-ScheduledTaskAction -Execute "$LHMDIR\LibreHardwareMonitor.exe" -WorkingDirectory $LHMDIR
$trg  = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$set  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0
$prn  = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName $task -Action $act -Trigger $trg -Settings $set -Principal $prn -Force | Out-Null
Get-Process LibreHardwareMonitor -ErrorAction SilentlyContinue | Stop-Process -Force
Start-ScheduledTask -TaskName $task
Green "LibreHardwareMonitor starter ved innlogging (minimert, deler målinger lokalt)"

# --- 3. Kontrollsenter fra NAS-en ------------------------------------------------------------------------
Blue "3/5 Kontrollsenter"
$pkg = Join-Path $Source "Kontrollsenter.tar.gz"          # lokal kopi hentet fra NAS-en
if (-not (Test-Path $pkg)) { throw "Fant ikke $pkg – start «Installer Kontrollsenter» på nytt." }
$want = (Get-Content (Join-Path $Source "SHA256SUMS") | Select-Object -First 1).Split(" ")[0].Trim().ToLower()
$got  = (Get-FileHash $pkg -Algorithm SHA256).Hash.ToLower()
if ($want -ne $got) { throw "Sjekksummen stemmer ikke – pakken på NAS-en er ødelagt." }
tar -xzf $pkg -C $TMP
if (-not (Test-Path "$TMP\Kontrollsenter\program\systemmonitor.py")) { throw "Pakken mangler programfilene." }
Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$MSYS*" } | Stop-Process -Force
if (Test-Path $PROG) { Remove-Item $PROG -Recurse -Force }
Copy-Item "$TMP\Kontrollsenter\program" $PROG -Recurse
Green "Kontrollsenter $(Get-Content "$PROG\VERSION") er installert i $PROG"

# --- 4. Snarveier -----------------------------------------------------------------------------------------
Blue "4/5 Snarveier"
$sh = New-Object -ComObject WScript.Shell
$icon = "$PROG\icons\kontrollsenter.ico"
foreach ($dir in @([Environment]::GetFolderPath("Desktop"), (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"))) {
    $lnk = $sh.CreateShortcut((Join-Path $dir "Kontrollsenter.lnk"))
    $lnk.TargetPath = $PYW; $lnk.Arguments = "`"$PROG\systemmonitor.py`""
    $lnk.WorkingDirectory = $PROG; $lnk.IconLocation = $icon; $lnk.Description = "Kontrollsenter"
    $lnk.Save()
}
# feilsøking: starter med konsoll og legger utskriften på NAS-en
@"
@echo off
chcp 65001 >nul
echo Starter Kontrollsenter med feilsøking ... (lukk vinduet for å avslutte)
"$PY" "$PROG\systemmonitor.py" > "%TEMP%\kontrollsenter-oppstart.txt" 2>&1
type "%TEMP%\kontrollsenter-oppstart.txt"
mkdir "$NAS\Diagnose" 2>nul
copy /y "%TEMP%\kontrollsenter-oppstart.txt" "$NAS\Diagnose\%COMPUTERNAME%-oppstart.txt" >nul && echo Lagt på NAS-en.
pause
"@ | ForEach-Object { [IO.File]::WriteAllText("$DEST\Feilsøk Kontrollsenter.cmd", $_, (New-Object Text.UTF8Encoding $false)) }
$lnk = $sh.CreateShortcut((Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Kontrollsenter (feilsøking).lnk"))
$lnk.TargetPath = "$DEST\Feilsøk Kontrollsenter.cmd"; $lnk.IconLocation = $icon; $lnk.Save()
Green "Snarvei på skrivebordet og i Start-menyen"

# --- 5. Oppstart ved innlogging og start ---------------------------------------------------------------------
Blue "5/5 Oppstart"
$ans = Read-Host "Starte Kontrollsenter skjult ved innlogging? (J/n)"
$run = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
if ($ans -notmatch "^[nN]") {
    Set-ItemProperty $run -Name "Kontrollsenter" -Value "`"$PYW`" `"$PROG\systemmonitor.py`" --hidden"
    Green "Starter ved innlogging"
} else {
    Remove-ItemProperty $run -Name "Kontrollsenter" -ErrorAction SilentlyContinue
}
Remove-Item $TMP -Recurse -Force -ErrorAction SilentlyContinue
Start-Process $PYW -ArgumentList "`"$PROG\systemmonitor.py`"" -WorkingDirectory $PROG
Green "Ferdig! Kontrollsenter starter nå."
$ok = $true
} catch {
    Write-Host "`n✗ Installasjonen stoppet: $_" -ForegroundColor Red
    Write-Host $_.ScriptStackTrace -ForegroundColor DarkGray
} finally {
    Stop-Transcript | Out-Null
    if (-not $ok) { Read-Host "Trykk Enter for å lukke" | Out-Null }
}
