#!/bin/bash
# Engangsoppsett: lar Kontrollsenter slå på engangs automatisk innlogging før en omstart, uten passord.
set -euo pipefail
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
USER_NAME="${1:-}"
if [[ -z "$USER_NAME" && -n "${PKEXEC_UID:-}" ]]; then USER_NAME="$(id -nu "$PKEXEC_UID")"; fi
[[ "$USER_NAME" =~ ^[a-z_][a-z0-9_-]*$ ]] || { echo "ugyldig brukernavn" >&2; exit 1; }
install -o root -g root -m 0755 "$SRC_DIR/systemmonitor-autologin" /usr/local/bin/systemmonitor-autologin
TMP="$(mktemp)"
echo "$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/systemmonitor-autologin" > "$TMP"
visudo -cf "$TMP" >/dev/null
install -o root -g root -m 0440 "$TMP" /etc/sudoers.d/systemmonitor-autologin
rm -f "$TMP"
echo "Automatisk innlogging etter omstart er satt opp for $USER_NAME."
