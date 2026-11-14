#!/bin/bash
# Bygg Android-appen Kontrollsenter.apk (mobil og nettbrett) i en container – ingenting installeres på PC-en.
#   ./bygg-android.sh      -> dist/Kontrollsenter-<versjon>.apk  (+ kopi i remote_web/kontrollsenter.apk)
#
# Signeringsnøkkelen lages én gang i ~/.local/share/kontrollsenter-android/ (ikke i Git). Ta vare på den:
# Android godtar bare oppdateringer som er signert med samme nøkkel.
set -euo pipefail
cd "$(dirname "$0")"
VER="$(cat VERSION)"
CODE="$(python3 -c "a,b,c=(list(map(int,'$VER'.split('.')))+[0,0])[:3]; print(a*10000+b*100+c)")"
IMAGE=localhost/kontrollsenter-android
KEYDIR="$HOME/.local/share/kontrollsenter-android"
mkdir -p "$KEYDIR" dist

if ! podman image exists "$IMAGE"; then
    echo "Lager byggebilde med Android SDK (én gang, ca. 1 GB) …"
    podman build -q -t localhost/ks-jdk -f - . <<'EOF'
FROM registry.fedoraproject.org/fedora:latest
RUN dnf -y install java-25-openjdk-devel unzip zip && dnf clean all
EOF
    podman build -q -t "$IMAGE" -f - . <<'EOF'
FROM localhost/ks-jdk
ENV JAVA_HOME=/usr/lib/jvm/java-25-openjdk
ENV ANDROID_HOME=/opt/android
RUN mkdir -p $ANDROID_HOME/cmdline-tools && cd /tmp && \
    curl -fsSLo tools.zip https://dl.google.com/android/repository/commandlinetools-linux-13114758_latest.zip && \
    unzip -q tools.zip -d $ANDROID_HOME/cmdline-tools && mv $ANDROID_HOME/cmdline-tools/cmdline-tools $ANDROID_HOME/cmdline-tools/latest && rm tools.zip && \
    (yes | $ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager --licenses >/dev/null || true) && \
    $ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager "platforms;android-35" "build-tools;35.0.0" | tail -2
ENV PATH=$ANDROID_HOME/build-tools/35.0.0:$PATH
EOF
fi

if [ ! -f "$KEYDIR/passord" ]; then
    head -c 24 /dev/urandom | base64 | tr -d '/+=' > "$KEYDIR/passord"
    chmod 600 "$KEYDIR/passord"
fi

OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT
podman run --rm -v "$PWD/android:/src:ro,Z" -v "$OUT:/out:Z" -v "$KEYDIR:/key:Z" \
    -e VER="$VER" -e CODE="$CODE" "$IMAGE" bash -euo pipefail -c '
    JAR=$ANDROID_HOME/platforms/android-35/android.jar
    W=/tmp/b; mkdir -p $W/gen $W/classes $W/dex; cd $W
    aapt2 compile --dir /src/res -o res.zip
    aapt2 link -o base.apk -I $JAR --manifest /src/AndroidManifest.xml -A /src/assets res.zip \
        --min-sdk-version 26 --target-sdk-version 35 --version-code "$CODE" --version-name "$VER" --java gen
    javac -nowarn -Xlint:-options --release 17 -cp $JAR -d classes $(find gen /src/src -name "*.java")
    d8 --release --min-api 26 --lib $JAR --output dex $(find classes -name "*.class")
    (cd dex && zip -q ../base.apk classes.dex)
    zipalign -f -p 4 base.apk aligned.apk
    PW=$(cat /key/passord)
    [ -f /key/kontrollsenter.jks ] || keytool -genkeypair -keystore /key/kontrollsenter.jks -alias kontrollsenter \
        -keyalg RSA -keysize 3072 -validity 10000 -storepass "$PW" -keypass "$PW" \
        -dname "CN=Kontrollsenter, O=Vegard E. Wågan, C=NO" >/dev/null 2>&1
    apksigner sign --ks /key/kontrollsenter.jks --ks-key-alias kontrollsenter --ks-pass pass:"$PW" \
        --key-pass pass:"$PW" --out /out/app.apk aligned.apk
    apksigner verify /out/app.apk
'
cp "$OUT/app.apk" "dist/Kontrollsenter-$VER.apk"
cp "$OUT/app.apk" remote_web/kontrollsenter.apk
echo "Ferdig: dist/Kontrollsenter-$VER.apk ($(du -h "dist/Kontrollsenter-$VER.apk" | cut -f1))"
