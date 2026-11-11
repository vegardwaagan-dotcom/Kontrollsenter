#!/bin/bash
# Engangsoppsett for viftestyring i Systemmonitor (kjøres som root via pkexec).
#  - laster nct6775-driveren (hovedkortvifter) nå og ved hver oppstart
#  - installerer hjelpeskriptet /usr/local/bin/systemmonitor-fan (eid av root)
#  - gir brukeren lov til å kjøre NETTOPP det skriptet med sudo uten passord
set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
USER_NAME="${1:-}"
if [[ -z "$USER_NAME" && -n "${PKEXEC_UID:-}" ]]; then
    USER_NAME="$(id -nu "$PKEXEC_UID")"
fi
[[ "$USER_NAME" =~ ^[a-z_][a-z0-9_-]*$ ]] || { echo "ugyldig brukernavn" >&2; exit 1; }

echo nct6775 > /etc/modules-load.d/systemmonitor-fans.conf
modprobe nct6775 || echo "Advarsel: kunne ikke laste nct6775 (hovedkortvifter)" >&2

install -o root -g root -m 0755 "$SRC_DIR/systemmonitor-fan" /usr/local/bin/systemmonitor-fan

TMP="$(mktemp)"
echo "$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/systemmonitor-fan" > "$TMP"
visudo -cf "$TMP" >/dev/null
install -o root -g root -m 0440 "$TMP" /etc/sudoers.d/systemmonitor-fan
rm -f "$TMP"
echo "Viftestyring er satt opp for $USER_NAME."
