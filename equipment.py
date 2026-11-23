"""Utstyr+ (runde 6): spill fra en annen PC, batterihelse og ladegrense, driver-tilbakerulling, Wi-Fi-signal,
nedlastinger venter mens noen spiller, kontrollere, DPI per spill, skjermkalibrering, hodesett-bytte og ukens
beste øyeblikk.

  23 Spill på en annen PC i huset: Steam kan hente dem over hjemmenettet («lokale overføringer») i stedet for
     internett – Kontrollsenter viser hvilke spill som finnes hvor, og slår det på
  33 Batterihelse på bærbare (kapasitet mot ny) og ladegrense 80 % (Linux, der maskinen støtter det)
  34 Gå tilbake til forrige systemversjon (med drivere) – Bazzite/Silverblue (rpm-ostree rollback)
  60 Wi-Fi-signal per PC over tid
  61 Når noen i huset spiller: «Oppdater alt», NAS-sikkerhetskopi og fartstest venter
  64 Kontrollere: batteri (Xbox på Windows også) og varsel når det er lavt
  65 DPI per spill (Logitech via Solaar)
  66 Skjermkalibrering: testmønstre for svart/hvitt/gamma, og lysstyrke per profil
  67 Hodesett-bytte: lyden går til hodesettet når det slås på, og tilbake når det slås av (Linux)
  68 Ukens beste øyeblikk: søndag lages en video av ukas beste klipp, og familien får beskjed
"""
import glob
import json
import os
import re
import subprocess
import sys
import threading
import time

IS_WIN = sys.platform == "win32"
CFG = os.path.expanduser("~/.config/systemmonitor/utstyr-pluss.json")
DATA = os.path.expanduser("~/.local/share/systemmonitor")
DEF = {"dpi_map": {}, "headset_switch": True, "weekly_video": True, "wait_for_gamers": True, "wifi_hist": [],
       "ctrl_low": 15}
_STATE = {"dpi_prev": None, "sinks": None, "prev_default": None, "ctrl_warned": {}}


def cfg():
    try:
        d = json.load(open(CFG))
    except (OSError, ValueError):
        d = {}
    return {**DEF, **d}


def set_(**kw):
    d = cfg()
    d.update(kw)
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    json.dump(d, open(CFG, "w"), ensure_ascii=False)
    return d


def _notify(win, key, title, body):
    bg = getattr(win, "bg", None)
    if bg:
        from gi.repository import GLib
        GLib.idle_add(lambda: (bg.notify(key, title, body, force=True), False)[1])


# --------------------------------------------------------------------------
# 23 – spill som finnes på en annen PC
# --------------------------------------------------------------------------
def my_games():
    try:
        import games
        return [g["appid"] for g in games.installed_games()]
    except Exception:  # noqa: BLE001
        return []


def games_elsewhere():
    """{appid: [PC-er som har spillet]} for spill som IKKE er installert her (fra statusen PC-ene deler)."""
    mine = set(my_games())
    out = {}
    try:
        import homepcs
        import savegames
        me = savegames.pc_name()
        for p in homepcs.fetch() or []:
            if p.get("name") == me:
                continue
            for aid in p.get("steam_apps") or []:
                if aid not in mine:
                    out.setdefault(aid, []).append(p["name"])
    except Exception:  # noqa: BLE001
        pass
    return out


def open_steam_lan_setting():
    """Steam → Innstillinger → Nedlastinger («Tillat overføringer fra enheter på det lokale nettverket»)."""
    from gi.repository import Gio
    Gio.AppInfo.launch_default_for_uri("steam://settings/downloads", None)
    return "Steam-innstillingene er åpnet – slå på «Lokale nettverksoverføringer»"


# --------------------------------------------------------------------------
# 33 – batterihelse og ladegrense
# --------------------------------------------------------------------------
def battery_health():
    """[{name, health %, cycles, limit (ladegrense eller None), can_limit}]"""
    out = []
    if IS_WIN:
        try:
            import winsupport
            ps = ("$f=(Get-CimInstance -Namespace root\\wmi -ClassName BatteryFullChargedCapacity -EA SilentlyContinue)."
                  "FullChargedCapacity; $d=(Get-CimInstance -Namespace root\\wmi -ClassName BatteryStaticData "
                  "-EA SilentlyContinue).DesignedCapacity; \"$f|$d\"")
            _c, txt = winsupport.run(["powershell", "-NoProfile", "-Command", ps], 40)
            f, _s, d = txt.strip().splitlines()[-1].partition("|")
            if f.strip().isdigit() and d.strip().isdigit() and int(d):
                out.append({"name": "Batteri", "health": round(int(f) / int(d) * 100), "cycles": None, "limit": None,
                            "can_limit": False})
        except Exception:  # noqa: BLE001
            pass
        return out
    for b in sorted(glob.glob("/sys/class/power_supply/BAT*")):
        def rd(n):
            try:
                return open(os.path.join(b, n)).read().strip()
            except OSError:
                return None
        full, design = rd("energy_full") or rd("charge_full"), rd("energy_full_design") or rd("charge_full_design")
        if not full or not design or not design.isdigit() or int(design) == 0:
            continue
        lim = rd("charge_control_end_threshold")
        out.append({"name": f"{rd('manufacturer') or ''} {rd('model_name') or os.path.basename(b)}".strip(),
                    "health": round(int(full) / int(design) * 100), "cycles": rd("cycle_count"),
                    "limit": int(lim) if lim and lim.isdigit() else None,
                    "can_limit": os.path.exists(os.path.join(b, "charge_control_end_threshold")), "path": b})
    return out


def set_charge_limit(pct):
    """Ladegrense (Linux, én pkexec-godkjenning). 100 = av."""
    if IS_WIN:
        raise RuntimeError("på Windows styres ladegrensen av produsentens program (MSI Center, Armoury Crate …)")
    pct = max(50, min(100, int(pct)))
    paths = glob.glob("/sys/class/power_supply/BAT*/charge_control_end_threshold")
    if not paths:
        raise RuntimeError("denne maskinen støtter ikke ladegrense")
    cmd = " && ".join(f"echo {pct} > {p}" for p in paths)
    r = subprocess.run(["pkexec", "sh", "-c", cmd], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError("avbrutt eller ikke tillatt")
    return f"Ladegrense {pct} %" if pct < 100 else "Lader til 100 %"


# --------------------------------------------------------------------------
# 34 – forrige systemversjon (med drivere)
# --------------------------------------------------------------------------
def can_rollback():
    return not IS_WIN and os.path.exists("/run/ostree-booted")


def system_rollback():
    if not can_rollback():
        raise RuntimeError("bare på Bazzite / Silverblue (rpm-ostree)" if not IS_WIN else
                           "på Windows: Enhetsbehandling → Skjermkort → Egenskaper → Driver → «Rull tilbake driver»")
    r = subprocess.run(["rpm-ostree", "rollback"], capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[-160:] or "feilet")
    return "Forrige systemversjon (med de gamle driverne) brukes fra neste omstart"


# --------------------------------------------------------------------------
# 60 – Wi-Fi-signal
# --------------------------------------------------------------------------
def wifi_signal():
    """(ssid, signal %) eller (None, None) når PC-en ikke bruker Wi-Fi."""
    try:
        if IS_WIN:
            import winsupport
            _c, out = winsupport.run(["netsh", "wlan", "show", "interfaces"], 15)
            ss = re.search(r"^\s*SSID\s*:\s*(.+)$", out, re.M)
            sig = re.search(r"(?:Signal|Signalstyrke)\s*:\s*(\d+)\s*%", out)
            return (ss.group(1).strip() if ss else None, int(sig.group(1)) if sig else None)
        out = subprocess.run(["nmcli", "-t", "-f", "ACTIVE,SIGNAL,SSID", "dev", "wifi"], capture_output=True, text=True,
                             timeout=10).stdout
        for ln in out.splitlines():
            p = ln.split(":")
            if p and p[0] == "yes" and len(p) >= 3 and p[1].isdigit():
                return ":".join(p[2:]), int(p[1])
    except Exception:  # noqa: BLE001
        pass
    return None, None


def wifi_tick():
    ssid, sig = wifi_signal()
    if sig is None:
        return
    h = cfg()["wifi_hist"]
    h = (h + [[int(time.time()), sig]])[-7 * 24 * 4:]          # hvert kvarter i en uke
    set_(wifi_hist=h)


def wifi_summary():
    h = cfg()["wifi_hist"]
    if not h:
        return None
    vals = [s for _t, s in h]
    return {"now": vals[-1], "avg": round(sum(vals) / len(vals)), "low": min(vals), "n": len(vals)}


def status_fields():
    ssid, sig = wifi_signal()
    out = {"steam_apps": my_games()[:400]}
    if sig is not None:
        out["wifi_sig"] = sig
    return out


# --------------------------------------------------------------------------
# 61 – vent med tunge ting mens noen spiller
# --------------------------------------------------------------------------
def someone_gaming():
    """Navnet på en PC i huset der noen spiller nå (eller None)."""
    if not cfg()["wait_for_gamers"]:
        return None
    try:
        import homepcs
        for p in homepcs.fetch() or []:
            if p.get("game") and time.time() - (p.get("time") or 0) < homepcs.STALE:
                return p.get("name")
    except Exception:  # noqa: BLE001
        pass
    return None


# --------------------------------------------------------------------------
# 64 – kontrollere
# --------------------------------------------------------------------------
def controller_batteries():
    """[(navn, prosent eller None, tekst)]"""
    out = []
    if IS_WIN:
        try:
            import ctypes

            class BI(ctypes.Structure):
                _fields_ = [("BatteryType", ctypes.c_ubyte), ("BatteryLevel", ctypes.c_ubyte)]
            x = None
            for dll in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
                try:
                    x = getattr(ctypes.windll, dll)
                    break
                except OSError:
                    continue
            if x:
                for i in range(4):
                    bi = BI()
                    if x.XInputGetBatteryInformation(i, 0, ctypes.byref(bi)) == 0 and bi.BatteryType not in (0, 1):
                        pct = {0: 5, 1: 30, 2: 65, 3: 100}.get(bi.BatteryLevel)
                        out.append((f"Xbox-kontroller {i + 1}", pct, f"{pct} %"))
        except Exception:  # noqa: BLE001
            pass
        return out
    try:
        import games
        _js, bats = games.controllers()
        pad = re.compile(r"controller|gamepad|dualsense|dualshock|xbox|8bitdo|nintendo|joy-?con|stadia|wireless "
                         r"controller|ps[345]", re.I)
        for model, txt in bats:
            if not pad.search(model or ""):                # mus, tastatur og hodesett er ikke kontrollere
                continue
            m = re.match(r"(\d+)", txt or "")
            out.append((model, int(m.group(1)) if m else None, txt))
    except Exception:  # noqa: BLE001
        pass
    return out


def controller_tick(win):
    low = cfg()["ctrl_low"]
    for name, pct, _t in controller_batteries():
        if pct is not None and pct <= low:
            if time.time() - _STATE["ctrl_warned"].get(name, 0) > 3 * 3600:
                _STATE["ctrl_warned"][name] = time.time()
                _notify(win, "battery", f"🎮 {name}: {pct} %", "Lad kontrolleren snart.")


# --------------------------------------------------------------------------
# 65 – DPI per spill (Solaar)
# --------------------------------------------------------------------------
def _solaar(*args, t=20):
    try:
        import logitech
        return logitech.solaar(*args)
    except Exception:  # noqa: BLE001
        cmd = ["solaar", *args]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=t)
        return r.returncode, r.stdout + r.stderr


def mouse_dpi():
    """(enhet, dpi) for første mus med DPI i Solaar, eller (None, None)."""
    try:
        res = _solaar("show")
        txt = res[1] if isinstance(res, tuple) else str(res)
    except Exception:  # noqa: BLE001
        return None, None
    dev = None
    for ln in txt.splitlines():
        m = re.match(r"^\s*\d+:\s*(.+?)\s*$", ln)
        if m and not ln.startswith(" " * 6):
            dev = m.group(1)
        d = re.search(r"(?:Sensitivity|dpi)\s*\(DPI\)\s*:\s*(\d+)", ln, re.I) or re.search(r"\bdpi\s*:\s*(\d+)", ln, re.I)
        if d and dev:
            return dev, int(d.group(1))
    return None, None


def set_dpi(dpi):
    dev, _cur = mouse_dpi()
    if not dev:
        raise RuntimeError("fant ingen mus med DPI i Solaar")
    res = _solaar("config", dev, "dpi", str(int(dpi)))
    code = res[0] if isinstance(res, tuple) else 0
    if code != 0:
        raise RuntimeError("Solaar kunne ikke sette DPI")
    return f"{dev}: {dpi} DPI"


def on_game_start(win, game):
    dpi = cfg()["dpi_map"].get(game)
    if not dpi:
        return

    def run():
        _dev, cur = mouse_dpi()
        _STATE["dpi_prev"] = cur
        try:
            set_dpi(dpi)
        except Exception:  # noqa: BLE001
            pass
    threading.Thread(target=run, daemon=True).start()


def on_game_end(win, game):
    prev, _STATE["dpi_prev"] = _STATE["dpi_prev"], None
    if prev:
        threading.Thread(target=lambda: set_dpi(prev), daemon=True).start()


# --------------------------------------------------------------------------
# 67 – hodesett-bytte (Linux)
# --------------------------------------------------------------------------
HEADSET = re.compile(r"headset|headphone|hodetelefon|arctis|cloud|astro|g pro x|g435|g733|nova|blackshark|kraken|"
                     r"virtuoso|hs\d|bluez|bluetooth|airpods|buds|wh-1000", re.I)


def headset_tick():
    if IS_WIN or not cfg()["headset_switch"]:
        return None
    try:
        sinks = json.loads(subprocess.run(["pactl", "-f", "json", "list", "sinks"], capture_output=True, text=True,
                                          timeout=5).stdout or "[]")
        default = subprocess.run(["pactl", "get-default-sink"], capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:  # noqa: BLE001
        return None
    names = {s["name"]: (s.get("description") or s["name"]) for s in sinks}
    prev = _STATE["sinks"]
    _STATE["sinks"] = set(names)
    if prev is None:
        return None
    new = [n for n in names if n not in prev and HEADSET.search(names[n] + " " + n)]
    gone = [n for n in prev if n not in names]
    if new:
        _STATE["prev_default"] = default
        subprocess.run(["pactl", "set-default-sink", new[0]], timeout=5)
        return f"Lyden går til {names[new[0]]}"
    if gone and default not in names and _STATE["prev_default"] in names:
        back = _STATE["prev_default"]
        _STATE["prev_default"] = None
        subprocess.run(["pactl", "set-default-sink", back], timeout=5)
        return f"Lyden er tilbake på {names[back]}"
    return None


# --------------------------------------------------------------------------
# 68 – ukens beste øyeblikk
# --------------------------------------------------------------------------
def weekly_tick(win):
    if not cfg()["weekly_video"]:
        return
    lt = time.localtime()
    if lt.tm_wday != 6 or lt.tm_hour < 19:
        return
    wk = time.strftime("%Y-%W")
    if cfg().get("weekly_done") == wk:
        return
    set_(weekly_done=wk)
    try:
        import clipx
        week = [x for x in clipx.files() if x["kind"] != "image" and time.time() - x["t"] < 7 * 86400]
        if len(week) < 2:
            return
        clipx.weekly()
    except Exception:  # noqa: BLE001
        return
    try:
        import features
        import savegames
        features.send_to("*", savegames.pc_name(), "🎬 Ukens beste øyeblikk fra " + savegames.pc_name() +
                         " er klar – se den i Klipp (Spill → Klipp) eller i appen.")
    except Exception:  # noqa: BLE001
        pass
    _notify(win, "clip", "🎬 Ukens beste øyeblikk", "Videoen med ukas beste klipp er klar i Klipp.")


_T = {"wifi": 0}


def tick(win):
    fns = [controller_tick, weekly_tick]
    for fn in fns:
        try:
            fn(win)
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("utstyr+: %s", fn.__name__)
    if time.time() - _T["wifi"] > 900:
        _T["wifi"] = time.time()
        try:
            wifi_tick()
        except Exception:  # noqa: BLE001
            pass
    try:
        msg = headset_tick()
        if msg:
            _notify(win, "audio", "🎧 Hodesett", msg)
    except Exception:  # noqa: BLE001
        pass
