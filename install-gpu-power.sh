#!/bin/bash
# Engangsoppsett: lar Kontrollsenter endre NVIDIA-strømgrensen uten passord.
# Kjøres som root (Kontrollsenter starter det via pkexec, som spør om passord).
#  - kopierer hjelpeskriptet til /usr/local/bin (eid av root, ikke skrivbart for andre)
#  - gir brukeren lov til å kjøre NETTOPP det skriptet med sudo uten passord
set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
USER_NAME="${1:-}"
if [[ -z "$USER_NAME" && -n "${PKEXEC_UID:-}" ]]; then
    USER_NAME="$(id -nu "$PKEXEC_UID")"
fi
[[ "$USER_NAME" =~ ^[a-z_][a-z0-9_-]*$ ]] || { echo "ugyldig brukernavn" >&2; exit 1; }

install -o root -g root -m 0755 "$SRC_DIR/systemmonitor-gpu-power" /usr/local/bin/systemmonitor-gpu-power

TMP="$(mktemp)"
echo "$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/systemmonitor-gpu-power" > "$TMP"
visudo -cf "$TMP" >/dev/null
install -o root -g root -m 0440 "$TMP" /etc/sudoers.d/systemmonitor-gpu-power
rm -f "$TMP"
echo "GPU-strømstyring er satt opp for $USER_NAME."
