#!/bin/bash
# Engangsoppsett for MSI-fanen (kjøres som root via pkexec).
#   install-msi.sh <bruker>            hjelpeprogram + sudo-regel
#   install-msi.sh <bruker> --driver   + nyeste msi-ec-driver (DKMS) fra github.com/BeardOverflow/msi-ec
#   install-msi.sh <bruker> --envycontrol  + EnvyControl (GPU-modus) fra github.com/bayasdev/envycontrol
set -euo pipefail
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
USER_NAME="${1:-}"
[[ -z "$USER_NAME" && -n "${PKEXEC_UID:-}" ]] && USER_NAME="$(id -nu "$PKEXEC_UID")"
[[ "$USER_NAME" =~ ^[a-z_][a-z0-9_-]*$ ]] || { echo "ugyldig brukernavn" >&2; exit 1; }

install -o root -g root -m 0755 "$SRC_DIR/systemmonitor-msi" /usr/local/bin/systemmonitor-msi
TMP="$(mktemp)"
echo "$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/systemmonitor-msi" > "$TMP"
visudo -cf "$TMP" >/dev/null
install -o root -g root -m 0440 "$TMP" /etc/sudoers.d/systemmonitor-msi
rm -f "$TMP"
echo "msi-ec" > /etc/modules-load.d/systemmonitor-msi.conf
echo "MSI-styring er satt opp for $USER_NAME."

if [ "${2:-}" = "--envycontrol" ]; then
    # EnvyControl (GPU-modus: integrated / hybrid / nvidia) – ett Python-skript, virker på alle distroer
    command -v curl >/dev/null || { echo "curl mangler" >&2; exit 1; }
    TAG="$(curl -fsSL --max-time 30 https://api.github.com/repos/bayasdev/envycontrol/releases/latest \
           | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])' 2>/dev/null || echo main)"
    TMPF="$(mktemp)"
    curl -fsSL --max-time 60 "https://raw.githubusercontent.com/bayasdev/envycontrol/$TAG/envycontrol.py" -o "$TMPF"
    head -1 "$TMPF" | grep -q python || { echo "Nedlastingen ser ikke ut som EnvyControl" >&2; rm -f "$TMPF"; exit 1; }
    install -o root -g root -m 0755 "$TMPF" /usr/local/bin/envycontrol
    rm -f "$TMPF"
    echo "EnvyControl $TAG er installert i /usr/local/bin/envycontrol."
fi

if [ "${2:-}" = "--driver" ]; then
    if [ -e /run/ostree-booted ]; then
        echo "Bazzite/Silverblue: DKMS-drivere kan ikke bygges her. Bruk en distro med DKMS (f.eks. CachyOS)." >&2
        exit 3
    fi
    echo "Installerer verktøy for å bygge driveren …"
    if   command -v pacman  >/dev/null; then
        pacman -S --needed --noconfirm git dkms base-devel \
            $(pacman -Qq | grep -E '^linux(-zen|-lts|-cachyos[^ ]*)?$' | sed 's/$/-headers/' | tr '\n' ' ')
    elif command -v dnf     >/dev/null; then dnf -y install git dkms make gcc "kernel-devel-$(uname -r)"
    elif command -v apt-get >/dev/null; then apt-get update && apt-get install -y git dkms build-essential "linux-headers-$(uname -r)"
    elif command -v zypper  >/dev/null; then zypper -n install git dkms make gcc kernel-default-devel
    fi
    W=/var/tmp/msi-ec-src
    rm -rf "$W"
    git clone --depth 1 https://github.com/BeardOverflow/msi-ec "$W"
    cd "$W"
    make dkms-uninstall >/dev/null 2>&1 || true
    make dkms-install
    modprobe -r msi_ec 2>/dev/null || true
    modprobe msi-ec
    echo "Den nyeste msi-ec-driveren er installert og lastet."
fi
