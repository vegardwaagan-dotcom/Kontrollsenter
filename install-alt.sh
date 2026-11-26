#!/bin/bash
# Felles tilgang: kjører de engangsoppsettene Kontrollsenter trenger på DENNE PC-en – med ett passord.
#   install-alt.sh BRUKER gpu gpupower fan msi    (bare delene som er nevnt)
set -uo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
USER_NAME="${1:-}"; shift || true
[[ "$USER_NAME" =~ ^[a-z_][a-z0-9_-]*$ ]] || { echo "ugyldig brukernavn" >&2; exit 1; }
feil=0
for del in "$@"; do
  case "$del" in
    gpu)      bash "$DIR/install-gpu.sh" "$USER_NAME" || feil=1 ;;
    gpupower) bash "$DIR/install-gpu-power.sh" "$USER_NAME" || feil=1 ;;
    fan)      bash "$DIR/install-fan-control.sh" "$USER_NAME" || feil=1 ;;
    msi)      bash "$DIR/install-msi.sh" "$USER_NAME" || feil=1 ;;
    autologin) bash "$DIR/install-autologin.sh" "$USER_NAME" || feil=1 ;;
    *) echo "ukjent del: $del" >&2; feil=1 ;;
  esac
done
exit $feil
