#!/bin/bash
# Installerer bare selve Kontrollsenter (og GTK4/libadwaita hvis det mangler – uten det kan programmet ikke starte).
#
# Programmene funksjonene trenger (OpenRGB, Solaar, TRCC, RustDesk, Tailscale, Discord, MangoHud …) installeres
# av velkomstveiviseren første gang Kontrollsenter starter – bare for funksjonene du velger, med fremdrift.
#
#   bash installer.sh          spør før GTK installeres (Enter = ja)
#   bash installer.sh --alle   uten å spørre
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
  pacman) P_GTK="python-gobject gtk4 libadwaita"; P_RATBAG=libratbag; P_PIPX=python-pipx; P_EXTRA="pacman-contrib"; P_SMB=smbclient ;;
  dnf|ostree) P_GTK="python3-gobject gtk4 libadwaita"; P_RATBAG=libratbag-ratbagd; P_PIPX=pipx; P_EXTRA=""; P_SMB=samba-client ;;
  apt)    P_GTK="python3-gi gir1.2-gtk-4.0 gir1.2-adw-1"; P_RATBAG=ratbagd; P_PIPX="pipx python3-venv"; P_EXTRA=""; P_SMB=smbclient ;;
  zypper) P_GTK="python3-gobject typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1"; P_RATBAG=libratbag-tools; P_PIPX=python3-pipx; P_EXTRA=""; P_SMB=samba-client ;;
  *)      P_GTK=""; P_RATBAG=""; P_PIPX=""; P_EXTRA=""; P_SMB="" ;;
esac
. /etc/os-release 2>/dev/null || true
echo "Kontrollsenter – installasjon på ${PRETTY_NAME:-ukjent distro} (pakkehåndterer: $PM)"

gtk_ok() { python3 -c "import gi; gi.require_version('Gtk','4.0'); gi.require_version('Adw','1'); from gi.repository import Gtk, Adw" 2>/dev/null; }

# --------------------------------------------------------------------------
# 1. GTK4/libadwaita (det eneste programmet trenger for å starte)
# --------------------------------------------------------------------------
blå "1/2 GTK4 og libadwaita"
if gtk_ok; then
    grønn "✓ GTK4/libadwaita finnes"
elif [ -n "$P_GTK" ] && spør "Installere $P_GTK (krever sudo-passordet ditt)?"; then
    case $PM in
      pacman) sudo pacman -Sy --needed --noconfirm $P_GTK ;;
      dnf)    sudo dnf install -y $P_GTK ;;
      apt)    sudo apt-get update && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y $P_GTK ;;
      zypper) sudo zypper -n install $P_GTK ;;
      ostree) sudo rpm-ostree install --idempotent --allow-inactive $P_GTK
              gul "Bazzite/Silverblue: start PC-en på nytt, og kjør installer.sh igjen." ;;
    esac
fi

# --------------------------------------------------------------------------
# 4. Selve programmet
# --------------------------------------------------------------------------
blå "2/2 Kontrollsenter"
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
Icon=no.waagan.Systemmonitor
Terminal=false
Categories=System;Monitor;
StartupWMClass=$ID
EOF
mkdir -p "$HOME/.local/share/icons/hicolor/scalable/apps"
cp "$DEST/icons/no.waagan.Systemmonitor.svg" "$DEST/icons/no.waagan.Systemmonitor-symbolic.svg" \
   "$HOME/.local/share/icons/hicolor/scalable/apps/" 2>/dev/null || true
gtk-update-icon-cache -qtf "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
command -v kbuildsycoca6 >/dev/null && kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
update-desktop-database "$APPS" 2>/dev/null || true
if [ -d "$DESKTOP_DIR" ]; then
    rm -f "$DESKTOP_DIR/Systemmonitor.desktop"          # gammelt navn
    cp "$APPS/$ID.desktop" "$DESKTOP_DIR/Kontrollsenter.desktop"
    chmod +x "$DESKTOP_DIR/Kontrollsenter.desktop"
    gio set "$DESKTOP_DIR/Kontrollsenter.desktop" metadata::trusted true 2>/dev/null || true
fi
grønn "✓ Kontrollsenter er installert i $DEST, med snarvei i menyen og på skrivebordet"

# --------------------------------------------------------------------------
blå "Ferdig"
echo "Start Kontrollsenter fra menyen eller skrivebordet."
echo "Første gang spør velkomstveiviseren hvilke funksjoner du vil ha, og installerer programmene de"
echo "trenger (med fremdrift). Du kan endre det senere under Innstillinger → Funksjoner."
