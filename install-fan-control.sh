#!/bin/bash
# Engangsoppsett for viftestyring i Kontrollsenter (kjøres som root via pkexec).
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
modprobe nct6775 2>/dev/null || true

has_chip() {
    for h in /sys/class/hwmon/hwmon*; do
        [[ "$(cat "$h/name" 2>/dev/null)" =~ ^nct6[0-9]{3}[a-z]?$ ]] && return 0
    done
    return 1
}
NEED_REBOOT=0
KARG="acpi_enforce_resources=lax"
if ! has_chip && ! grep -qw "$KARG" /proc/cmdline; then
    # Viftebrikken (Nuvoton NCT67xx) er reservert av BIOS via ACPI – vanlig på ASUS-kort med Intel-brikkesett
    # (f.eks. PRIME Z270). Oppstartsvalget acpi_enforce_resources=lax lar Linux bruke den.
    if [ -e /run/ostree-booted ] && command -v rpm-ostree >/dev/null; then
        rpm-ostree kargs --append-if-missing="$KARG" >/dev/null && NEED_REBOOT=1
    elif command -v grubby >/dev/null; then
        grubby --update-kernel=ALL --args="$KARG" && NEED_REBOOT=1
    elif [ -f /etc/kernel/cmdline ]; then                     # systemd-boot (f.eks. CachyOS)
        grep -qw "$KARG" /etc/kernel/cmdline || sed -i "s/\$/ $KARG/" /etc/kernel/cmdline
        { command -v reinstall-kernels >/dev/null && reinstall-kernels; } || \
            { command -v kernel-install >/dev/null && for k in /usr/lib/modules/*/vmlinuz; do
                  kernel-install add "$(basename "$(dirname "$k")")" "$k"; done; } || true
        NEED_REBOOT=1
    elif [ -f /etc/default/grub ]; then
        grep -q "$KARG" /etc/default/grub || \
            sed -i "s/^GRUB_CMDLINE_LINUX_DEFAULT=\"/GRUB_CMDLINE_LINUX_DEFAULT=\"$KARG /" /etc/default/grub
        if command -v update-grub >/dev/null; then update-grub
        elif command -v grub-mkconfig >/dev/null; then grub-mkconfig -o /boot/grub/grub.cfg
        elif command -v grub2-mkconfig >/dev/null; then grub2-mkconfig -o /boot/grub2/grub.cfg; fi
        NEED_REBOOT=1
    else
        echo "Fant ikke hvordan oppstartsvalg legges inn på denne distroen. Legg inn $KARG selv." >&2
    fi
fi

install -o root -g root -m 0755 "$SRC_DIR/systemmonitor-fan" /usr/local/bin/systemmonitor-fan

TMP="$(mktemp)"
echo "$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/systemmonitor-fan" > "$TMP"
visudo -cf "$TMP" >/dev/null
install -o root -g root -m 0440 "$TMP" /etc/sudoers.d/systemmonitor-fan
rm -f "$TMP"
echo "Viftestyring er satt opp for $USER_NAME."
if [ "$NEED_REBOOT" = 1 ]; then
    echo "OMSTART: hovedkortets viftebrikke blir tilgjengelig etter omstart." >&2
    exit 3
fi
