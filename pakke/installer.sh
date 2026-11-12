#!/bin/bash
# Installerer Kontrollsenter OG alt den bruker:
#   OpenRGB (RGB), Solaar (trådløse Logitech), TRCC / trcc-linux (CPU-skjerm),
#   ratbagd (Logitech mus/tastatur), MangoHud (spill-overlay), udev-regler og i2c-tilgang.
#
#   bash installer.sh          spør før hvert hovedsteg (Enter = ja)
#   bash installer.sh --alle   installerer alt uten å spørre
#
# Støtter: Arch / CachyOS / EndeavourOS / Manjaro, Fedora, Bazzite / Silverblue,
#          Debian / Ubuntu / Mint, openSUSE.
set -uo pipefail

ALLE=0; [[ "${1:-}" =~ ^(--alle|-y|--yes)$ ]] && ALLE=1
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/program"; UDEV="$HERE/udev"
DEST="$HOME/.local/share/systemmonitor"
APPS="$HOME/.local/share/applications"
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
ID="no.waagan.Systemmonitor"

grønn() { printf '\e[32m%s\e[0m\n' "$*"; }
gul()   { printf '\e[33m%s\e[0m\n' "$*"; }
rød()   { printf '\e[31m%s\e[0m\n' "$*"; }
blå()   { printf '\n\e[1;34m=== %s ===\e[0m\n' "$*"; }
spør()  { [ "$ALLE" = 1 ] && return 0; read -r -p "$1 [J/n] " s; [[ ! "$s" =~ ^[nN] ]]; }
har()   { command -v "$1" >/dev/null 2>&1; }

[ -f "$SRC/systemmonitor.py" ] || { rød "Fant ikke programfilene i $SRC"; exit 1; }
[ "$(id -u)" = 0 ] && { rød "Kjør som vanlig bruker (ikke sudo). Skriptet ber selv om passord."; exit 1; }

# --------------------------------------------------------------------------
# Distro og pakkenavn
# --------------------------------------------------------------------------
OSTREE=0; [ -e /run/ostree-booted ] && OSTREE=1
if   [ "$OSTREE" = 1 ];  then PM=ostree
elif har pacman;         then PM=pacman
elif har dnf;            then PM=dnf
elif har apt-get;        then PM=apt
elif har zypper;         then PM=zypper
else PM=ukjent; fi
[ -n "${SM_TEST_PM:-}" ] && { PM=$SM_TEST_PM; OSTREE=0; }   # kun for testing

case $PM in
  pacman) P_GTK="python-gobject gtk4 libadwaita"; P_RATBAG=libratbag; P_PIPX=python-pipx; P_EXTRA="pacman-contrib" ;;
  dnf|ostree) P_GTK="python3-gobject gtk4 libadwaita"; P_RATBAG=libratbag-ratbagd; P_PIPX=pipx; P_EXTRA="" ;;
  apt)    P_GTK="python3-gi gir1.2-gtk-4.0 gir1.2-adw-1"; P_RATBAG=ratbagd; P_PIPX="pipx python3-venv"; P_EXTRA="" ;;
  zypper) P_GTK="python3-gobject typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1"; P_RATBAG=libratbag-tools; P_PIPX=python3-pipx; P_EXTRA="" ;;
  *)      P_GTK=""; P_RATBAG=""; P_PIPX=""; P_EXTRA="" ;;
esac
. /etc/os-release 2>/dev/null || true
echo "Kontrollsenter – installasjon på ${PRETTY_NAME:-ukjent distro} (pakkehåndterer: $PM)"

gtk_ok() { python3 -c "import gi; gi.require_version('Gtk','4.0'); gi.require_version('Adw','1'); from gi.repository import Gtk, Adw" 2>/dev/null; }
TRCC_BIN=""
trcc_ok() {
    for p in /usr/bin/trcc /usr/local/bin/trcc "$HOME/.local/bin/trcc" "$DEST/trcc-venv/bin/trcc"; do
        if [ -x "$p" ] && "$p" --version >/dev/null 2>&1; then TRCC_BIN="$p"; return 0; fi
    done
    return 1
}
flatpak_har() { har flatpak && flatpak info "$1" >/dev/null 2>&1; }
ratbag_ok() { [ -x /usr/bin/ratbagd ] || [ -x /usr/sbin/ratbagd ] || har ratbagd; }

# --------------------------------------------------------------------------
# 1. Systempakker + udev-regler + i2c (én sudo-økt)
# --------------------------------------------------------------------------
blå "1/5 Systempakker, enhetstilgang (udev) og i2c"
need=()
gtk_ok || need+=($P_GTK)
har flatpak || need+=(flatpak)
ratbag_ok || need+=($P_RATBAG)
har mangohud || need+=(mangohud)
trcc_ok || har pipx || need+=($P_PIPX)
[ "$PM" = pacman ] && ! har checkupdates && need+=($P_EXTRA)

ROOT=$'set -e\n'
if [ ${#need[@]} -gt 0 ]; then
    echo "Mangler: ${need[*]}"
    case $PM in
      pacman) ROOT+="pacman -Sy --needed --noconfirm ${need[*]}"$'\n' ;;
      dnf)    ROOT+="dnf install -y ${need[*]}"$'\n' ;;
      apt)    ROOT+="apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y ${need[*]}"$'\n' ;;
      zypper) ROOT+="zypper -n install ${need[*]}"$'\n' ;;
      ostree) gul "Bazzite/Silverblue: pakkene legges inn med rpm-ostree og krever omstart."
              ROOT+="rpm-ostree install --idempotent --allow-inactive ${need[*]}"$'\n' ;;
      *)      rød "Ukjent pakkehåndterer – installer selv: ${need[*]}" ;;
    esac
else
    grønn "✓ Alle systempakker finnes"
fi
# udev-regler (bare hvis distroen ikke allerede har dem)
for r in 60-openrgb.rules 42-logitech-unify-permissions.rules; do
    if [ ! -e "/usr/lib/udev/rules.d/$r" ] && [ ! -e "/etc/udev/rules.d/$r" ] && [ -f "$UDEV/$r" ]; then
        ROOT+="install -m 644 '$UDEV/$r' /etc/udev/rules.d/$r"$'\n'; echo "Legger inn udev-regel: $r"
    fi
done
# i2c-tilgang (RAM- og skjermkort-RGB i OpenRGB)
if [ ! -e /etc/modules-load.d/systemmonitor-i2c.conf ] && ! grep -rqs '^i2c[-_]dev' /etc/modules-load.d /usr/lib/modules-load.d; then
    ROOT+="echo i2c-dev > /etc/modules-load.d/systemmonitor-i2c.conf"$'\n'; echo "Slår på i2c-dev ved oppstart"
fi
ROOT+="modprobe i2c-dev || true"$'\n'
ROOT+="udevadm control --reload-rules && udevadm trigger || true"$'\n'

if spør "Installere dette nå (krever sudo-passordet ditt)?"; then
    if sudo bash -c "$ROOT"; then grønn "✓ Systemdelen er ferdig"; else rød "✗ Noe i systemdelen feilet – se meldingene over"; fi
else
    gul "Hoppet over systemdelen"
fi

# --------------------------------------------------------------------------
# 2. OpenRGB og Solaar (Flathub)
# --------------------------------------------------------------------------
blå "2/5 OpenRGB og Solaar"
if har flatpak; then
    flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo 2>/dev/null || true
    fp=()
    flatpak_har org.openrgb.OpenRGB || fp+=(org.openrgb.OpenRGB)
    flatpak_har io.github.pwr_solaar.solaar || fp+=(io.github.pwr_solaar.solaar)
    if [ ${#fp[@]} -eq 0 ]; then
        grønn "✓ OpenRGB og Solaar er installert"
    elif spør "Installere ${fp[*]} fra Flathub?"; then
        flatpak install --user -y --noninteractive flathub "${fp[@]}" && grønn "✓ Installert: ${fp[*]}" || rød "✗ Flatpak-installasjonen feilet"
    fi
else
    rød "Flatpak mangler – OpenRGB og Solaar kan ikke installeres (kjør steg 1)"
fi

# --------------------------------------------------------------------------
# 3. TRCC (trcc-linux) for CPU-skjermen
# --------------------------------------------------------------------------
blå "3/5 TRCC (Thermalright LCD-kjølere)"
if trcc_ok; then
    grønn "✓ TRCC finnes ($TRCC_BIN)"
elif spør "Installere trcc-linux?"; then
    if har pipx; then
        pipx install --force trcc-linux || true
    else
        python3 -m venv "$DEST/trcc-venv" && "$DEST/trcc-venv/bin/pip" install -q trcc-linux || true
    fi
    trcc_ok && grønn "✓ TRCC installert ($TRCC_BIN)" || rød "✗ Klarte ikke å installere trcc-linux"
fi
if [ -n "$TRCC_BIN" ] && ! ls /etc/udev/rules.d/*trcc* /usr/lib/udev/rules.d/*trcc* >/dev/null 2>&1; then
    if spør "Sette opp enhetstilgang for TRCC (sudo)?"; then
        sudo "$TRCC_BIN" system setup -y && grønn "✓ TRCC-oppsett ferdig" || rød "✗ TRCC-oppsett feilet"
    fi
fi

# --------------------------------------------------------------------------
# 4. Selve programmet
# --------------------------------------------------------------------------
blå "4/5 Kontrollsenter"
if ! gtk_ok; then
    rød "✗ Python GTK4/libadwaita mangler fortsatt – programmet kan ikke starte. Pakker: $P_GTK"
    exit 1
fi
mkdir -p "$DEST" "$APPS"
cp -r "$SRC/." "$DEST/"
chmod +x "$DEST/systemmonitor.py" "$DEST"/*.sh "$DEST/systemmonitor-fan" "$DEST/systemmonitor-gpu-power" "$DEST/systemmonitor-msi"
cat > "$APPS/$ID.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Control Center
Name[nb]=Kontrollsenter
Name[nn]=Kontrollsenter
Name[no]=Kontrollsenter
Comment=CPU, GPU, fans, power mode, RGB, Logitech, games and system check
Comment[nb]=CPU, GPU, vifter, strømmodus, RGB, Logitech, spill og systemsjekk
Comment[nn]=CPU, GPU, vifter, straummodus, RGB, Logitech, spel og systemsjekk
Comment[no]=CPU, GPU, vifter, strømmodus, RGB, Logitech, spill og systemsjekk
Exec=python3 $DEST/systemmonitor.py
Icon=utilities-system-monitor
Terminal=false
Categories=System;Monitor;
StartupWMClass=$ID
EOF
update-desktop-database "$APPS" 2>/dev/null || true
if [ -d "$DESKTOP_DIR" ]; then
    rm -f "$DESKTOP_DIR/Systemmonitor.desktop"          # gammelt navn
    cp "$APPS/$ID.desktop" "$DESKTOP_DIR/Kontrollsenter.desktop"
    chmod +x "$DESKTOP_DIR/Kontrollsenter.desktop"
    gio set "$DESKTOP_DIR/Kontrollsenter.desktop" metadata::trusted true 2>/dev/null || true
fi
grønn "✓ Kontrollsenter er installert i $DEST, med snarvei i menyen og på skrivebordet"

# --------------------------------------------------------------------------
# 5. Dine faste programmer (programmer.json, laget i Programmer-fanen)
# --------------------------------------------------------------------------
blå "5/5 Dine programmer"
LISTE="$HERE/programmer.json"
if [ -f "$LISTE" ] && har flatpak; then
    mkdir -p "$HOME/.config/systemmonitor"
    [ -f "$HOME/.config/systemmonitor/programmer.json" ] || cp "$LISTE" "$HOME/.config/systemmonitor/programmer.json"
    mapfile -t PROGS < <(python3 -c "import json,sys; print('\n'.join(json.load(open(sys.argv[1]))['programs']))" "$LISTE")
    mangler=()
    declare -A SYS=([com.valvesoftware.Steam]=steam [net.lutris.Lutris]=lutris [org.mozilla.firefox]=firefox)
    for a in "${PROGS[@]}"; do
        [[ "$a" == script:* ]] && continue                          # Claude/Codex: egne skript under
        flatpak info "$a" >/dev/null 2>&1 && continue
        [ -n "${SYS[$a]:-}" ] && har "${SYS[$a]}" && continue      # finnes som systempakke
        mangler+=("$a")
    done
    if [ ${#mangler[@]} -eq 0 ]; then
        grønn "✓ Alle ${#PROGS[@]} programmene dine er installert"
    elif spør "Installere ${#mangler[@]} av programmene dine fra Flathub (${mangler[*]:0:5} …)?"; then
        if flatpak remotes --system --columns=name 2>/dev/null | grep -qx flathub; then HVOR=--system; else HVOR=--user; fi
        feil=()
        for a in "${mangler[@]}"; do
            echo "  → $a"
            flatpak install $HVOR -y --noninteractive flathub "$a" >/dev/null 2>&1 \
              || flatpak install --user -y --noninteractive flathub "$a" >/dev/null 2>&1 || feil+=("$a")
        done
        [ ${#feil[@]} -eq 0 ] && grønn "✓ Programmene er installert" || gul "Kunne ikke installere: ${feil[*]}"
    fi
    if grep -q '"script:' "$LISTE"; then
        if spør "Installere Claude Code og Codex (KI-assistenter i terminalen)?"; then
            python3 "$DEST/programs.py" --install-scripts "$LISTE" || gul "Noe kunne ikke installeres – se over"
        fi
    fi
else
    echo "Ingen programliste i pakken (lag en med «Eksporter listen» i Programmer-fanen)."
fi

# --------------------------------------------------------------------------
blå "Oppsummering"
gtk_ok && grønn "✓ GTK4/libadwaita" || rød "✗ GTK4/libadwaita"
flatpak_har org.openrgb.OpenRGB && grønn "✓ OpenRGB" || gul "– OpenRGB"
flatpak_har io.github.pwr_solaar.solaar && grønn "✓ Solaar" || gul "– Solaar"
trcc_ok && grønn "✓ TRCC" || gul "– TRCC"
ratbag_ok && grønn "✓ ratbagd" || gul "– ratbagd"
har mangohud && grønn "✓ MangoHud" || gul "– MangoHud"
echo
echo "Viktig:"
echo " • Logg ut og inn (eller start PC-en på nytt) så enhetstilgang, i2c og grupper trer i kraft."
[ "$PM" = ostree ] && echo " • Bazzite/Silverblue: start PC-en på nytt hvis det ble lagt inn systempakker."
echo " • Viftestyring og GPU-strømgrense slås på inne i programmet (passord én gang)."
echo " • Kjør «Systemsjekk» i programmet etterpå – den retter f.eks. at Solaar tar over Logitech-lysene."
