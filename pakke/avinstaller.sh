#!/bin/bash
# Fjerner Kontrollsenter for denne brukeren.
# Kjør:  bash avinstaller.sh
set -uo pipefail
ID="no.waagan.Systemmonitor"
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
spør() { read -r -p "$1 [j/N] " s; [[ "$s" =~ ^[jJyY] ]]; }

echo "=== Avinstaller Kontrollsenter ==="
rm -rf "$HOME/.local/share/systemmonitor"
rm -f "$HOME/.local/share/applications/$ID.desktop" "$DESKTOP_DIR/Systemmonitor.desktop" "$DESKTOP_DIR/Kontrollsenter.desktop"
# oppstartsfiler programmet kan ha laget
rm -f "$HOME/.config/autostart/systemmonitor-openrgb.desktop" \
      "$HOME/.config/autostart/systemmonitor-trcc.desktop" \
      "$HOME/.config/environment.d/90-systemmonitor-mangohud.conf"
echo "✓ Program, snarveier og oppstartsfiler er fjernet"

if spør "Slette lagrede innstillinger også (~/.config/systemmonitor)?"; then
    rm -rf "$HOME/.config/systemmonitor"
    echo "✓ Innstillinger slettet"
fi

if [ -e /etc/sudoers.d/systemmonitor-fan ] || [ -e /etc/sudoers.d/systemmonitor-gpu-power ]; then
    echo
    echo "Viftestyring/GPU-styring ble satt opp med root. Fjern det med:"
    echo "  sudo rm -f /etc/sudoers.d/systemmonitor-fan /etc/sudoers.d/systemmonitor-gpu-power /etc/sudoers.d/systemmonitor-msi \\"
    echo "             /usr/local/bin/systemmonitor-fan /usr/local/bin/systemmonitor-gpu-power /usr/local/bin/systemmonitor-msi \\"
    echo "             /etc/modules-load.d/systemmonitor-fans.conf /etc/modules-load.d/systemmonitor-msi.conf"
fi
echo "Ferdig."
