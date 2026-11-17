"""Widgets for Android, Linux (KDE Plasma) og Windows/Linux (egne skrivebordswidgets i Kontrollsenter).

* data(win) samler alt widgetene viser i én liten ordbok (samme for alle plattformer).
* Plasma-widgetene henter dataene fra http://127.0.0.1:27100/api/local/widgets – bare fra denne PC-en,
  og bare med hodet «X-KS-Local» (nettsider i nettleseren kan ikke sende det, så de får ikke tilgang).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

IS_WIN = sys.platform == "win32"
CFG = os.path.expanduser("~/.config/systemmonitor/widgets.json")

# type -> (navn, beskrivelse, ikon, bredde, høyde (gridUnits i Plasma))
KINDS = {
    "status": ("Kontrollsenter", "Temperatur, strøm og spillet som kjører – alt i ett", "🖥️", 16, 7),
    "temp": ("Temperaturer", "CPU, GPU og strøm i store tall", "🌡️", 16, 6),
    "quick": ("Hurtigknapper", "Spillmodus, lagre klipp, lås PC-en og demp lyden", "⚡", 16, 6),
    "family": ("Familien", "Hva de andre PC-ene spiller – og «Middag!»", "👨‍👩‍👦", 16, 9),
    "battery": ("Batterier", "Batteriet i mus, tastatur og hodesett", "🔋", 14, 6),
    "playtime": ("Spilletid i dag", "Hvor mye som er spilt i dag, og grensen", "⏱️", 14, 6),
}
LOCAL_ACTIONS = {"gamemode", "clip", "system", "volume", "power", "dinner", "clipshot"}


def cfg():
    try:
        with open(CFG, encoding="utf-8") as f:
            c = json.load(f)
    except (OSError, ValueError):
        c = {}
    return {"desk": {}, **c}


def save_cfg(c):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    with open(CFG, "w", encoding="utf-8") as f:
        json.dump(c, f, indent=1)


# --------------------------------------------------------------------------
# Data (kalles i GTK-tråden)
# --------------------------------------------------------------------------
_FAM = {"t": 0, "pcs": []}


def _family_bg():
    if time.time() - _FAM["t"] < 60 or _FAM.get("busy"):
        return
    _FAM["busy"] = True

    def work():
        try:
            import homepcs
            import savegames
            me = savegames.pc_name()
            pcs = []
            for p in homepcs.fetch() or []:
                on = time.time() - (p.get("time") or 0) < 900 and not p.get("off")
                pcs.append({"name": p.get("name"), "on": on, "game": p.get("game") if on else None,
                            "me": p.get("name") == me})
            _FAM.update(t=time.time(), pcs=pcs)
        except Exception:  # noqa: BLE001
            pass
        finally:
            _FAM["busy"] = False
    threading.Thread(target=work, daemon=True).start()


def data(win):
    import remote
    s = remote.build_status(win)
    cpu, gpu = s.get("cpu") or {}, s.get("gpu") or {}
    out = {"name": s.get("name"), "cpu_t": cpu.get("temp"), "cpu_l": cpu.get("load"),
           "gpu_t": gpu.get("temp"), "gpu_l": gpu.get("util"), "watts": s.get("watts"),
           "game": s.get("game"), "gamemode": bool(s.get("gamemode")),
           "mode": ((s.get("power") or {}).get("active")), "time": time.time()}
    try:
        from cards import MODE_NAMES
        out["mode_name"] = MODE_NAMES.get(out["mode"], "")
    except Exception:  # noqa: BLE001
        pass
    try:
        out["batteries"] = [{"name": d["name"], "pct": d.get("pct"), "kind": d.get("kind"),
                             "charging": d.get("charging"), "full": d.get("full")} for d in (s.get("batteries") or {}).get("devices", [])]
    except Exception:  # noqa: BLE001
        out["batteries"] = []
    try:
        import remote_extra as X
        pt = X.playtime_summary(1)
        out["play_s"] = pt["days"][-1]["total"]
        out["limit_h"] = X.limit_today()
        out["top_game"] = max(pt["days"][-1]["games"].items(), key=lambda x: x[1])[0] if pt["days"][-1]["games"] else None
    except Exception:  # noqa: BLE001
        pass
    try:
        import power
        log = power.EnergyLog()
        wh = log._get(time.strftime("%Y-%m-%d"))[0]
        out["kwh"] = round(wh / 1000, 2)
        out["kr"] = round(wh / 1000 * power.load()["price"], 2)
    except Exception:  # noqa: BLE001
        pass
    try:
        import features
        last = features.chat_list(1)
        out["chat"] = last[-1] if last else None
    except Exception:  # noqa: BLE001
        pass
    _family_bg()
    out["pcs"] = _FAM["pcs"]
    return out


def local_action(win, body):
    import remote
    kind = body.get("a")
    if kind not in LOCAL_ACTIONS:
        raise ValueError("ikke tillatt fra widget")
    if kind == "system" and body.get("do") != "lock":
        raise ValueError("bare låsing er tillatt fra widget")
    body = dict(body)
    body["_dev"] = "Skrivebordet"
    return remote.do_action(win, body)


# --------------------------------------------------------------------------
# KDE Plasma-widgets (Linux)
# --------------------------------------------------------------------------
QML_HEAD = r'''import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root
    property var d: ({})
    property bool ok: false
    preferredRepresentation: fullRepresentation
    Plasmoid.backgroundHints: PlasmaCore.Types.NoBackground
    toolTipMainText: "Kontrollsenter"
    toolTipSubText: ok ? (d.name || "") : "Kontrollsenter kjører ikke"

    function t(v) { return (v === null || v === undefined) ? "–" : Math.round(v) + "°" }
    function load() {
        var x = new XMLHttpRequest()
        x.onreadystatechange = function() {
            if (x.readyState === XMLHttpRequest.DONE) {
                if (x.status === 200) { try { root.d = JSON.parse(x.responseText); root.ok = true } catch (e) { root.ok = false } }
                else root.ok = false
            }
        }
        x.open("GET", "http://127.0.0.1:27100/api/local/widgets")
        x.setRequestHeader("X-KS-Local", "1")
        x.send()
    }
    function act(body) {
        var x = new XMLHttpRequest()
        x.onreadystatechange = function() { if (x.readyState === XMLHttpRequest.DONE) root.load() }
        x.open("POST", "http://127.0.0.1:27100/api/local/action")
        x.setRequestHeader("X-KS-Local", "1")
        x.setRequestHeader("Content-Type", "application/json")
        x.send(JSON.stringify(body))
    }
    Timer { interval: 3000; running: true; repeat: true; triggeredOnStart: true; onTriggered: root.load() }

    component Glass: Rectangle {
        radius: 22
        border.width: 1
        border.color: Qt.rgba(1, 1, 1, 0.16)
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.rgba(0.30, 0.36, 0.62, 0.62) }
            GradientStop { position: 0.55; color: Qt.rgba(0.08, 0.09, 0.16, 0.72) }
            GradientStop { position: 1.0; color: Qt.rgba(0.20, 0.13, 0.36, 0.70) }
        }
        Rectangle {          // lysrefleks øverst
            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
            anchors.margins: 1
            height: parent.height * 0.45
            radius: parent.radius
            gradient: Gradient {
                GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.16) }
                GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.0) }
            }
        }
    }
    component Big: ColumnLayout {
        property string label: ""
        property string value: "–"
        spacing: 0
        Text { text: parent.label; color: Qt.rgba(1, 1, 1, 0.6); font.pixelSize: 11; font.bold: true; font.letterSpacing: 1.2 }
        Text { text: parent.value; color: "white"; font.pixelSize: 30; font.bold: true }
    }
    component Btn: Rectangle {
        id: b
        property string icon: ""
        property string label: ""
        property bool on: false
        signal clicked()
        Layout.fillWidth: true
        Layout.fillHeight: true
        radius: 16
        color: on ? Qt.rgba(0.42, 0.48, 1.0, 0.85) : (ma.containsMouse ? Qt.rgba(1, 1, 1, 0.16) : Qt.rgba(1, 1, 1, 0.08))
        border.width: 1
        border.color: ma.containsMouse ? Qt.rgba(0.55, 0.62, 1.0, 0.95) : Qt.rgba(1, 1, 1, 0.14)
        Behavior on color { ColorAnimation { duration: 160 } }
        Rectangle {          // glød når musa er over
            anchors.fill: parent; anchors.margins: -4; radius: parent.radius + 4; z: -1
            color: "transparent"; border.width: 4
            border.color: Qt.rgba(0.48, 0.42, 1.0, ma.containsMouse ? 0.45 : 0.0)
            Behavior on border.color { ColorAnimation { duration: 180 } }
        }
        ColumnLayout {
            anchors.centerIn: parent; spacing: 2
            Text { Layout.alignment: Qt.AlignHCenter; text: b.icon; font.pixelSize: 22 }
            Text { Layout.alignment: Qt.AlignHCenter; text: b.label; color: "white"; font.pixelSize: 11; font.bold: true }
        }
        MouseArea { id: ma; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: b.clicked() }
    }

    fullRepresentation: Item {
        Layout.preferredWidth: Kirigami.Units.gridUnit * __W__
        Layout.preferredHeight: Kirigami.Units.gridUnit * __H__
        Layout.minimumWidth: Kirigami.Units.gridUnit * 8
        Layout.minimumHeight: Kirigami.Units.gridUnit * 4
        Glass { anchors.fill: parent }
        Text {
            visible: !root.ok
            anchors.centerIn: parent; width: parent.width - 24; wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
            color: Qt.rgba(1, 1, 1, 0.75); font.pixelSize: 13
            text: "Kontrollsenter kjører ikke"
        }
        ColumnLayout {
            visible: root.ok
            anchors.fill: parent; anchors.margins: 16; spacing: 8
            Text { text: "__TITLE__".toUpperCase(); color: Qt.rgba(1, 1, 1, 0.6); font.pixelSize: 11; font.bold: true; font.letterSpacing: 1.4 }
__BODY__
        }
    }
}
'''

BODIES = {
    "status": r'''            Text { text: root.d.name || ""; color: "white"; font.pixelSize: 18; font.bold: true }
            RowLayout {
                spacing: 18
                Big { label: "CPU"; value: root.t(root.d.cpu_t) }
                Big { label: "GPU"; value: root.t(root.d.gpu_t) }
                Big { label: "STRØM"; value: (root.d.watts || 0) + " W" }
            }
            Text { text: root.d.game ? "🎮 " + root.d.game : (root.d.mode_name || ""); color: Qt.rgba(1, 1, 1, 0.8); font.pixelSize: 13; elide: Text.ElideRight; Layout.fillWidth: true }
            Item { Layout.fillHeight: true }''',
    "temp": r'''            RowLayout {
                spacing: 18; Layout.fillWidth: true
                Big { label: "CPU"; value: root.t(root.d.cpu_t) }
                Big { label: "GPU"; value: root.t(root.d.gpu_t) }
                Big { label: "STRØM"; value: (root.d.watts || 0) + " W" }
            }
            Text { text: (root.d.kwh !== undefined ? "I dag " + root.d.kwh + " kWh · " + root.d.kr + " kr" : ""); color: Qt.rgba(1, 1, 1, 0.65); font.pixelSize: 12 }
            Item { Layout.fillHeight: true }''',
    "quick": r'''            RowLayout {
                spacing: 8; Layout.fillWidth: true; Layout.fillHeight: true
                Btn { icon: "🎮"; label: "Spillmodus"; on: !!root.d.gamemode; onClicked: root.act({ a: "gamemode", on: !root.d.gamemode }) }
                Btn { icon: "🎬"; label: "Lagre klipp"; onClicked: root.act({ a: "clip" }) }
                Btn { icon: "🔒"; label: "Lås"; onClicked: root.act({ a: "system", do: "lock" }) }
                Btn { icon: "🔇"; label: "Demp"; onClicked: root.act({ a: "volume", mute: true }) }
            }''',
    "family": r'''            Repeater {
                model: (root.d.pcs || []).filter(function(p) { return !p.me })
                delegate: RowLayout {
                    required property var modelData
                    Layout.fillWidth: true; spacing: 10
                    Rectangle { width: 9; height: 9; radius: 5; color: modelData.on ? "#3ddc97" : Qt.rgba(1, 1, 1, 0.3) }
                    Text { text: modelData.name; color: "white"; font.pixelSize: 14; font.bold: true }
                    Text { Layout.fillWidth: true; elide: Text.ElideRight; color: Qt.rgba(1, 1, 1, 0.7); font.pixelSize: 13
                           text: modelData.on ? (modelData.game ? "🎮 " + modelData.game : "på") : "av" }
                }
            }
            Item { Layout.fillHeight: true }
            Btn { Layout.preferredHeight: 44; Layout.fillHeight: false; icon: ""; label: "🍽️  Middag!"; onClicked: root.act({ a: "dinner", to: "*" }) }''',
    "battery": r'''            Repeater {
                model: root.d.batteries || []
                delegate: RowLayout {
                    required property var modelData
                    Layout.fillWidth: true; spacing: 10
                    Text { text: modelData.kind === "headset" ? "🎧" : modelData.kind === "keyboard" ? "⌨️" : "🖱️"; font.pixelSize: 16 }
                    Text { Layout.fillWidth: true; elide: Text.ElideRight; text: modelData.name; color: "white"; font.pixelSize: 13 }
                    Rectangle {
                        width: 70; height: 8; radius: 4; color: Qt.rgba(1, 1, 1, 0.15)
                        Rectangle { width: parent.width * Math.max(0, Math.min(1, (modelData.pct || 0) / 100)); height: parent.height; radius: 4
                                    color: modelData.charging || modelData.full ? "#57e389" : (modelData.pct || 0) <= 20 ? "#ff6b7a" : "#3ddc97" }
                    }
                    Text { text: (modelData.charging ? "⚡ " : modelData.full ? "🔌 " : "") + (modelData.pct === null ? (modelData.charging ? "lader" : "av") : modelData.pct + " %")
                           color: modelData.charging || modelData.full ? "#57e389" : "white"; font.pixelSize: 13; font.bold: true }
                }
            }
            Text { visible: !(root.d.batteries || []).length; text: "Ingen trådløse enheter"; color: Qt.rgba(1, 1, 1, 0.6); font.pixelSize: 13 }
            Item { Layout.fillHeight: true }''',
    "playtime": r'''            Text { text: Math.floor((root.d.play_s || 0) / 3600) + " t " + Math.round(((root.d.play_s || 0) % 3600) / 60) + " min"; color: "white"; font.pixelSize: 30; font.bold: true }
            Rectangle {
                visible: !!root.d.limit_h
                Layout.fillWidth: true; height: 8; radius: 4; color: Qt.rgba(1, 1, 1, 0.15)
                Rectangle { height: parent.height; radius: 4; width: parent.width * Math.min(1, (root.d.play_s || 0) / ((root.d.limit_h || 1) * 3600))
                            gradient: Gradient { orientation: Gradient.Horizontal
                                GradientStop { position: 0; color: "#5b8cff" } GradientStop { position: 1; color: "#8a5cff" } } }
            }
            Text { text: root.d.limit_h ? "Grense i dag: " + root.d.limit_h + " t" : (root.d.top_game ? "Mest: " + root.d.top_game : "Ingen grense i dag"); color: Qt.rgba(1, 1, 1, 0.7); font.pixelSize: 12 }
            Item { Layout.fillHeight: true }''',
}


def plasmoid_id(kind):
    return f"no.waagan.kontrollsenter.{kind}"


def build_plasmoids(dest):
    """Lag én Plasma-pakke per widget i mappen dest. Returnerer [(id, mappe)]."""
    out = []
    for kind, (name, desc, _ic, w, h) in KINDS.items():
        pid = plasmoid_id(kind)
        d = os.path.join(dest, pid)
        os.makedirs(os.path.join(d, "contents", "ui"), exist_ok=True)
        meta = {"KPackageStructure": "Plasma/Applet",
                "KPlugin": {"Authors": [{"Name": "Kontrollsenter"}], "Category": "System Information",
                            "Description": desc, "Icon": "utilities-system-monitor", "Id": pid, "License": "GPL",
                            "Name": f"Kontrollsenter – {name}" if kind != "status" else "Kontrollsenter",
                            "Version": "1.0"},
                "X-Plasma-API-Minimum-Version": "6.0"}
        with open(os.path.join(d, "metadata.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)
        qml = (QML_HEAD.replace("__W__", str(w)).replace("__H__", str(h)).replace("__TITLE__", name)
               .replace("__BODY__", BODIES[kind]))
        with open(os.path.join(d, "contents", "ui", "main.qml"), "w", encoding="utf-8") as f:
            f.write(qml)
        out.append((pid, d))
    return out


def plasma_available():
    return not IS_WIN and bool(shutil.which("kpackagetool6"))


def install_plasmoids():
    """Installer (eller oppdater) alle Plasma-widgetene for denne brukeren. Returnerer tekst."""
    if not plasma_available():
        raise RuntimeError("KDE Plasma ble ikke funnet – bruk skrivebordswidgetene i stedet")
    tmp = tempfile.mkdtemp()
    done = []
    try:
        for pid, d in build_plasmoids(tmp):
            r = subprocess.run(["kpackagetool6", "-t", "Plasma/Applet", "-u", d], capture_output=True, text=True,
                               timeout=60)
            if r.returncode != 0:
                r = subprocess.run(["kpackagetool6", "-t", "Plasma/Applet", "-i", d], capture_output=True,
                                   text=True, timeout=60)
            if r.returncode == 0:
                done.append(pid)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if not done:
        raise RuntimeError("kpackagetool6 kunne ikke installere widgetene")
    return (f"{len(done)} widgets er installert ✓ – høyreklikk på skrivebordet → «Legg til widgets» og søk etter "
            "«Kontrollsenter»")


def installed_plasmoids():
    base = os.path.expanduser("~/.local/share/plasma/plasmoids")
    return [k for k in KINDS if os.path.isdir(os.path.join(base, plasmoid_id(k)))]
