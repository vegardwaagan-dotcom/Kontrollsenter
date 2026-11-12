#!/bin/bash
# Bygg Kontrollsenter-Setup-<versjon>.exe for Windows 11 (NSIS i en Fedora-container – ingenting installeres på PC-en).
# Bruk: ./bygg-windows-installer.sh            -> dist/Kontrollsenter-Setup-<versjon>.exe
set -euo pipefail
cd "$(dirname "$0")"
HERE="$PWD"
VER="$(cat VERSION)"
VIVER="$(python3 -c "p='$VER'.split('.'); print('.'.join((p + ['0']*4)[:4]))")"
IMAGE=localhost/kontrollsenter-nsis

if ! podman image exists "$IMAGE"; then
    echo "Lager byggebilde med NSIS (én gang) …"
    printf 'FROM registry.fedoraproject.org/fedora:latest\nRUN dnf -y install mingw32-nsis && dnf clean all\n' |
        podman build -q -t "$IMAGE" -f - .
fi

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
python3 - "$STAGE" <<'EOF'
import os, sys
sys.path.insert(0, os.getcwd())
import tools
tools.make_package(sys.argv[1])
EOF
B="$STAGE/bygg"
mkdir -p "$B"
cp -r "$STAGE/Kontrollsenter/program" "$B/program"
rm -rf "$B/program/Windows"
cp pakke-windows/installer.ps1 pakke-windows/kontrollsenter.nsi icons/kontrollsenter.ico "$B/"
python3 pakke-windows/lag-velkomstbilde.py "$HERE/icons/no.waagan.Systemmonitor.svg" "$B/velkommen.bmp" >/dev/null 2>&1
podman run --rm -v "$B:/b:Z" "$IMAGE" makensis -V2 -DVERSION="$VER" -DVIVERSION="$VIVER" /b/kontrollsenter.nsi
mkdir -p dist
mv "$B/Kontrollsenter-Setup-$VER.exe" dist/
ls -la "dist/Kontrollsenter-Setup-$VER.exe"
