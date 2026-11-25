"""Lyd- og skjermprofiler, nattlys og lysstyrke.

Lydprofil  = utgang (høyttaler/hodesett/TV) + inngang (mikrofon) + volum. Byttes med ett trykk, fra mobilen eller av
             en scene. Linux: PipeWire/PulseAudio (pactl). Windows: Core Audio (samme som Lyd-innstillingene).
Skjermprofil = oppløsning, Hz, HDR og VRR per skjerm. Linux (KDE): kscreen-doctor. Windows: oppløsning og Hz.
Nattlys    = varmere farger (KDE sitt nattlys; Windows: åpner innstillingene).
Lysstyrke  = skjermens egen lysstyrke via KDE (også eksterne skjermer med DDC/CI). Windows: bærbare.
"""
import json
import os
import re
import subprocess
import sys
import time

IS_WIN = sys.platform == "win32"
CFG = os.path.expanduser("~/.config/systemmonitor/profiler.json")


def _run(cmd, t=15):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=t,
                           **({"creationflags": 0x08000000} if IS_WIN else {}))
        return r.returncode, r.stdout + r.stderr
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


def cfg():
    try:
        with open(CFG, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    d.setdefault("audio", [])
    d.setdefault("display", [])
    return d


def save_cfg(d):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    with open(CFG, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)


def _new_id(name, existing):
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "profil"
    i, pid = 1, base
    while pid in existing:
        i += 1
        pid = f"{base}-{i}"
    return pid


# ==========================================================================
# LYD
# ==========================================================================
def _pa_list(kind):
    code, out = _run(["pactl", "-f", "json", "list", kind], 10)
    try:
        return json.loads(out) if code == 0 else []
    except ValueError:
        return []


def _pa_vol(obj):
    try:
        vals = [int(str(v.get("value_percent", "0")).rstrip("%")) for v in (obj.get("volume") or {}).values()]
        return round(sum(vals) / len(vals)) if vals else None
    except (ValueError, TypeError):
        return None


def devices():
    """{"out": [{id, name}], "in": [...], "cur_out": id, "cur_in": id, "out_vol": %, "in_vol": %}"""
    if IS_WIN:
        return _win_devices()
    sinks = [s for s in _pa_list("sinks")]
    sources = [s for s in _pa_list("sources") if not s.get("name", "").endswith(".monitor")
               and s.get("monitor_of_sink") in (None, "", "n/a")]
    _c, ds = _run(["pactl", "get-default-sink"], 5)
    _c, dsrc = _run(["pactl", "get-default-source"], 5)
    ds, dsrc = ds.strip(), dsrc.strip()
    cur_s = next((s for s in sinks if s["name"] == ds), None)
    cur_i = next((s for s in sources if s["name"] == dsrc), None)
    return {"out": [{"id": s["name"], "name": s.get("description") or s["name"]} for s in sinks],
            "in": [{"id": s["name"], "name": s.get("description") or s["name"]} for s in sources],
            "cur_out": ds, "cur_in": dsrc, "out_vol": _pa_vol(cur_s or {}), "in_vol": _pa_vol(cur_i or {})}


def set_output(dev_id, vol=None):
    if IS_WIN:
        return _win_set_default(dev_id, vol, render=True)
    _run(["pactl", "set-default-sink", dev_id], 5)
    for inp in _pa_list("sink-inputs"):                     # flytt det som spilles nå også
        _run(["pactl", "move-sink-input", str(inp.get("index")), dev_id], 5)
    if vol is not None:
        _run(["pactl", "set-sink-volume", dev_id, f"{int(vol)}%"], 5)


def set_input(dev_id, vol=None):
    if IS_WIN:
        return _win_set_default(dev_id, vol, render=False)
    _run(["pactl", "set-default-source", dev_id], 5)
    for out in _pa_list("source-outputs"):
        _run(["pactl", "move-source-output", str(out.get("index")), dev_id], 5)
    if vol is not None:
        _run(["pactl", "set-source-volume", dev_id, f"{int(vol)}%"], 5)


# ---- Windows: liste enheter og bytte standardenhet (IPolicyConfig) ----
def _win_devices():
    import ctypes
    from ctypes import POINTER, byref, c_int, c_uint, c_void_p, wintypes as W
    import winaudio as WA
    out = {"out": [], "in": [], "cur_out": None, "cur_in": None, "out_vol": None, "in_vol": None}
    en = WA._enumerator()
    try:
        for flow, key in ((WA.E_RENDER, "out"), (WA.E_CAPTURE, "in")):
            coll = c_void_p()
            WA._call(en, 3, flow, 1, byref(coll), argtypes=(c_int, W.DWORD, POINTER(c_void_p)))   # EnumAudioEndpoints
            try:
                n = c_uint()
                WA._call(coll, 3, byref(n), argtypes=(POINTER(c_uint),))
                for i in range(n.value):
                    dev = c_void_p()
                    WA._call(coll, 4, i, byref(dev), argtypes=(c_uint, POINTER(c_void_p)))
                    try:
                        pid = ctypes.c_wchar_p()
                        WA._call(dev, 5, byref(pid), argtypes=(POINTER(ctypes.c_wchar_p),))       # GetId
                        out[key].append({"id": pid.value, "name": WA._device_name(dev)})
                        ctypes.windll.ole32.CoTaskMemFree(pid)
                    finally:
                        WA._release(dev)
            finally:
                WA._release(coll)
            try:
                d = WA._default_device(flow)
                pid = ctypes.c_wchar_p()
                WA._call(d, 5, byref(pid), argtypes=(POINTER(ctypes.c_wchar_p),))
                out["cur_" + key] = pid.value
                ctypes.windll.ole32.CoTaskMemFree(pid)
                WA._release(d)
                ep = WA.Endpoint(flow)
                out[key + "_vol"] = ep.get()[0]
                ep.close()
            except OSError:
                pass
    finally:
        WA._release(en)
    return out


def _win_set_default(dev_id, vol, render=True):
    import ctypes
    from ctypes import byref, c_int, c_void_p, wintypes as W
    import winaudio as WA
    WA._com()
    clsid = WA.GUID("870AF99C-171D-4F9E-AF0D-E63DF40C2BC9")          # CPolicyConfigClient
    iid = WA.GUID("F8679F50-850A-41CF-9C72-430F290290C8")            # IPolicyConfig
    pc = c_void_p()
    hr = ctypes.windll.ole32.CoCreateInstance(byref(clsid), None, WA.CLSCTX_ALL, byref(iid), byref(pc))
    if hr < 0:
        raise OSError(f"kunne ikke bytte lydenhet (0x{hr & 0xffffffff:08x})")
    try:
        for role in (0, 1, 2):                                       # konsoll, multimedia, kommunikasjon
            WA._call(pc, 13, W.LPCWSTR(dev_id), role, argtypes=(W.LPCWSTR, c_int))   # SetDefaultEndpoint
    finally:
        WA._release(pc)
    if vol is not None:
        time.sleep(0.2)
        ep = WA.Endpoint(WA.E_RENDER if render else WA.E_CAPTURE)
        try:
            ep.set_volume(int(vol))
        finally:
            ep.close()
    _ = c_void_p


def save_audio(name, icon="🎧"):
    d = devices()
    c = cfg()
    p = {"id": _new_id(name, {x["id"] for x in c["audio"]}), "name": name.strip()[:30] or "Lydprofil", "icon": icon,
         "out": d["cur_out"], "out_name": next((x["name"] for x in d["out"] if x["id"] == d["cur_out"]), ""),
         "in": d["cur_in"], "in_name": next((x["name"] for x in d["in"] if x["id"] == d["cur_in"]), ""),
         "out_vol": d["out_vol"], "in_vol": d["in_vol"]}
    c["audio"].append(p)
    save_cfg(c)
    return p


def apply_audio(pid):
    p = next((x for x in cfg()["audio"] if x["id"] == pid), None)
    if not p:
        raise ValueError("fant ikke lydprofilen")
    d = devices()
    if p.get("out"):
        if p["out"] not in {x["id"] for x in d["out"]}:
            raise RuntimeError(f"«{p.get('out_name') or 'utgangen'}» er ikke koblet til")
        set_output(p["out"], p.get("out_vol"))
    if p.get("in") and p["in"] in {x["id"] for x in d["in"]}:
        set_input(p["in"], p.get("in_vol"))
    c = cfg()
    c["audio_active"] = pid
    save_cfg(c)
    return f"Lyd: {p['name']} ✓"


# ==========================================================================
# SKJERM
# ==========================================================================
def _display_tool():
    """Hvilket verktøy som styrer skjermene her: «kde», «hypr», «gnome», «wlr» (Sway …), «x11» eller None."""
    import shutil
    import desktop
    wayland = bool(os.environ.get("WAYLAND_DISPLAY"))
    if desktop.is_hypr():
        return "hypr"
    if shutil.which("kscreen-doctor") and "KDE" in os.environ.get("XDG_CURRENT_DESKTOP", "KDE").upper():
        return "kde"
    if desktop.is_gnome() and wayland:
        return "gnome"
    if wayland and shutil.which("wlr-randr"):
        return "wlr"
    if not wayland and shutil.which("xrandr") and os.environ.get("DISPLAY"):
        return "x11"
    return None


def displays():
    """[{id, name, w, h, hz, hdr, vrr, modes: [(w,h,hz)]}] – skjermene som er koblet til."""
    if IS_WIN:
        return _win_displays()
    tool = _display_tool()
    if tool == "x11":
        return _xrandr_displays()
    if tool == "wlr":
        return _wlr_displays()
    if tool == "hypr":
        return _hypr_displays()
    if tool == "gnome":
        return _gnome_displays()
    if tool is None:
        return []
    code, out = _run(["kscreen-doctor", "-j"], 10)
    try:
        d = json.loads(out)
    except ValueError:
        return []
    res = []
    for o in d.get("outputs", []):
        if not o.get("connected") or not o.get("enabled"):
            continue
        cur = next((m for m in o["modes"] if m["id"] == o.get("currentModeId")), None)
        modes = sorted({(m["size"]["width"], m["size"]["height"], round(m["refreshRate"])) for m in o["modes"]},
                       reverse=True)
        res.append({"id": o["name"], "name": o["name"], "w": cur["size"]["width"] if cur else None,
                    "h": cur["size"]["height"] if cur else None, "hz": round(cur["refreshRate"]) if cur else None,
                    "hdr": o.get("hdr"), "vrr": o.get("vrrPolicy"), "modes": modes})
    return res


def _xrandr_displays():
    code, out = _run(["xrandr", "--query"], 10)
    res, cur = [], None
    for ln in out.splitlines():
        m = re.match(r"^(\S+) connected", ln)
        if m:
            cur = {"id": m.group(1), "name": m.group(1), "w": None, "h": None, "hz": None, "hdr": None, "vrr": None,
                   "modes": []}
            res.append(cur)
            continue
        if not ln.startswith(" ") or cur is None:
            if not ln.startswith(" "):
                cur = None
            continue
        mm = re.match(r"^\s+(\d+)x(\d+)\S*\s+(.*)$", ln)
        if not mm:
            continue
        w, h = int(mm.group(1)), int(mm.group(2))
        for rate in re.finditer(r"([\d.]+)(\*?)(\+?)", mm.group(3)):
            hz = round(float(rate.group(1)))
            if (w, h, hz) not in cur["modes"]:
                cur["modes"].append((w, h, hz))
            if rate.group(2):
                cur.update(w=w, h=h, hz=hz)
    for d in res:
        d["modes"].sort(reverse=True)
    return [d for d in res if d["w"]]


def _wlr_displays():
    code, out = _run(["wlr-randr", "--json"], 10)
    try:
        data = json.loads(out)
    except ValueError:
        return []
    res = []
    for o in data:
        if not o.get("enabled"):
            continue
        modes = sorted({(m["width"], m["height"], round(m["refresh"])) for m in o.get("modes", [])}, reverse=True)
        cur = next((m for m in o.get("modes", []) if m.get("current")), None)
        res.append({"id": o["name"], "name": o.get("description") or o["name"], "w": cur["width"] if cur else None,
                    "h": cur["height"] if cur else None, "hz": round(cur["refresh"]) if cur else None,
                    "hdr": None, "vrr": None, "modes": modes})
    return res


# ---- Hyprland: hyprctl monitors / keyword monitor (plassering og skalering beholdes) ----
def _hypr_displays():
    import desktop
    res = []
    for m in desktop.hypr_json("monitors") or []:
        if m.get("disabled"):
            continue
        modes = set()
        for txt in m.get("availableModes", []):
            mm = re.match(r"(\d+)x(\d+)@([\d.]+)", txt)
            if mm:
                modes.add((int(mm.group(1)), int(mm.group(2)), round(float(mm.group(3)))))
        res.append({"id": m["name"], "name": m.get("description") or m["name"], "w": m.get("width"),
                    "h": m.get("height"), "hz": round(m.get("refreshRate") or 0) or None, "hdr": None,
                    "vrr": 1 if m.get("vrr") else 0, "modes": sorted(modes, reverse=True),
                    "_hypr": {"x": m.get("x", 0), "y": m.get("y", 0), "scale": m.get("scale", 1),
                              "modes": m.get("availableModes", [])}})
    return res


def _hypr_set_display(o):
    import desktop
    cur = next((d for d in _hypr_displays() if d["id"] == o["id"]), None)
    if cur is None:
        raise RuntimeError("fant ikke skjermen")
    w, h, hz = o.get("w") or cur["w"], o.get("h") or cur["h"], o.get("hz") or cur["hz"]
    # bruk den nøyaktige frekvensen Hyprland oppgir (143.91 Hz, ikke 144)
    exact = next((t.split("@")[1].rstrip("Hz") for t in cur["_hypr"]["modes"]
                  if re.match(rf"{w}x{h}@", t) and round(float(re.sub(r"[^\d.]", "", t.split("@")[1]))) == hz), None)
    vrr = o.get("vrr")
    ok, out = desktop.hypr_monitor(o["id"], f"{w}x{h}@{exact or hz}", cur["_hypr"]["x"], cur["_hypr"]["y"],
                                   cur["_hypr"]["scale"], None if vrr is None else {0: 0, 1: 1, 2: 2}.get(int(vrr), 2),
                                   bool(o.get("hdr")))
    if not ok:
        raise RuntimeError(out or "Hyprland godtok ikke skjerminnstillingen")


# ---- GNOME: Mutter sin DisplayConfig over D-Bus (ApplyMonitorsConfig, midlertidig – angres som ellers) ----
_MUTTER = ("org.gnome.Mutter.DisplayConfig", "/org/gnome/Mutter/DisplayConfig", "org.gnome.Mutter.DisplayConfig")


def _gnome_state():
    from gi.repository import Gio
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    return bus, bus.call_sync(*_MUTTER, "GetCurrentState", None, None, 0, 5000, None).unpack()


def _gnome_displays():
    try:
        _bus, (_serial, monitors, logical, _props) = _gnome_state()
    except Exception:  # noqa: BLE001
        return []
    active = {spec[0] for lm in logical for spec in lm[5]}
    res = []
    for (conn, vendor, product, _ser), modes, props in monitors:
        if conn not in active:
            continue
        cur = next((m for m in modes if m[6].get("is-current")), None)
        ms = sorted({(m[1], m[2], round(m[3])) for m in modes}, reverse=True)
        res.append({"id": conn, "name": props.get("display-name") or f"{vendor} {product}".strip() or conn,
                    "w": cur[1] if cur else None, "h": cur[2] if cur else None, "hz": round(cur[3]) if cur else None,
                    "hdr": None, "vrr": None, "modes": ms})
    return res


def _gnome_set_display(o):
    from gi.repository import GLib
    bus, (serial, monitors, logical, _props) = _gnome_state()
    modes_of = {m[0][0]: m[1] for m in monitors}
    mode_id = None
    if o.get("w") and o.get("hz"):
        mode_id = next((m[0] for m in modes_of.get(o["id"], [])
                        if m[1] == o["w"] and m[2] == o["h"] and round(m[3]) == o["hz"]), None)
        if mode_id is None:
            raise RuntimeError("skjermen støtter ikke den oppløsningen og frekvensen")
    new = []
    for x, y, scale, transform, primary, specs, _p in logical:
        out_specs = []
        if mode_id and any(sp[0] == o["id"] for sp in specs):     # skaleringen må passe den nye modusen
            m = next(m for m in modes_of[o["id"]] if m[0] == mode_id)
            if not any(abs(scale - sc) < 0.01 for sc in m[5]):
                scale = m[4]
        for conn, *_rest in specs:
            mid = mode_id if conn == o["id"] and mode_id else next(
                (m[0] for m in modes_of.get(conn, []) if m[6].get("is-current")), None)
            out_specs.append((conn, mid, {}))
        new.append((x, y, scale, transform, primary, out_specs))
    bus.call_sync(*_MUTTER, "ApplyMonitorsConfig",
                  GLib.Variant("(uua(iiduba(ssa{sv}))a{sv})", (serial, 1, new, {})), None, 0, 10000, None)


def _set_display(o):
    if IS_WIN:
        return _win_set_display(o)
    tool = _display_tool()
    if tool == "hypr":
        return _hypr_set_display(o)
    if tool == "gnome":
        return _gnome_set_display(o)
    if tool in ("x11", "wlr"):
        if not o.get("w"):
            return
        if not re.fullmatch(r"[\w.-]+", str(o["id"])):
            raise ValueError("ugyldig skjermnavn")
        cmd = (["xrandr", "--output", o["id"], "--mode", f"{o['w']}x{o['h']}", "--rate", str(o["hz"])]
               if tool == "x11" else ["wlr-randr", "--output", o["id"], "--mode", f"{o['w']}x{o['h']}@{o['hz']}"])
        code, out = _run(cmd, 20)
        if code != 0:
            raise RuntimeError(out.strip().splitlines()[-1] if out.strip() else "kunne ikke endre skjermen")
        return
    if tool is None:
        raise RuntimeError("på dette skrivebordet endres oppløsningen i systemets egne skjerminnstillinger")
    args = []
    if o.get("w") and o.get("hz"):
        args.append(f"output.{o['id']}.mode.{o['w']}x{o['h']}@{o['hz']}")
    if o.get("hdr") is not None:
        args.append(f"output.{o['id']}.hdr.{'enable' if o['hdr'] else 'disable'}")
    if o.get("vrr") is not None:
        args.append(f"output.{o['id']}.vrrpolicy.{ {0: 'never', 1: 'always', 2: 'automatic'}.get(o['vrr'], 'automatic') }")
    if args:
        code, out = _run(["kscreen-doctor", *args], 20)
        if code != 0:
            raise RuntimeError(out.strip().splitlines()[-1] if out.strip() else "kunne ikke endre skjermen")


# ---- velg oppløsning og Hz direkte – med angring som i Windows (går tilbake etter 15 s uten «Behold») ----
_PENDING = {"timer": None, "old": None, "until": 0, "text": ""}


def set_mode(out_id, w=None, h=None, hz=None, hdr=None, vrr=None, revert=15):
    """Endrer én skjerm. Med revert > 0 settes forrige modus tilbake etter så mange sekunder, med mindre keep_mode()
    kalles – slik at en modus skjermen ikke klarer aldri blir stående med svart skjerm."""
    import threading
    import time
    cur = next((o for o in displays() if o["id"] == out_id), None)
    if not cur:
        raise ValueError("fant ikke skjermen")
    if w and (int(w), int(h), int(hz)) not in {tuple(m) for m in cur["modes"]}:
        raise ValueError(f"skjermen støtter ikke {w}×{h} @ {hz} Hz")
    cancel_revert()
    old = {"id": out_id, "w": cur["w"], "h": cur["h"], "hz": cur["hz"], "hdr": cur.get("hdr") if hdr is not None
           else None, "vrr": cur.get("vrr") if vrr is not None else None}
    new = {"id": out_id, "w": int(w) if w else None, "h": int(h) if h else None, "hz": int(hz) if hz else None,
           "hdr": hdr, "vrr": vrr}
    _set_display(new)
    txt = (f"{new['w']}×{new['h']} @ {new['hz']} Hz" if new["w"] else "") + \
          (f"{' · ' if new['w'] else ''}HDR {'på' if hdr else 'av'}" if hdr is not None else "")
    if revert:
        t = threading.Timer(revert, _revert)
        t.daemon = True
        _PENDING.update(timer=t, old=old, until=time.time() + revert, text=txt)
        t.start()
    return f"Skjerm: {txt or 'endret'} ✓"


def _revert():
    old = _PENDING.get("old")
    _PENDING.update(timer=None, old=None, until=0, text="")
    if old:
        try:
            _set_display(old)
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("angre skjermmodus")


def keep_mode():
    """«Behold» – modusen blir stående."""
    cancel_revert()
    return "Beholdt ✓"


def cancel_revert():
    t = _PENDING.get("timer")
    if t:
        t.cancel()
    _PENDING.update(timer=None, old=None, until=0, text="")


def undo_mode():
    """«Angre» med en gang."""
    t = _PENDING.get("timer")
    if t:
        t.cancel()
    _revert()
    return "Satt tilbake"


def pending():
    """Sekunder igjen før skjermen settes tilbake (0 = ingenting venter)."""
    import time
    return max(0, round(_PENDING["until"] - time.time())) if _PENDING.get("timer") else 0


# ---- Windows: oppløsning og Hz (ChangeDisplaySettingsEx) ----
def _devmode():
    import ctypes
    from ctypes import wintypes as W

    class DEVMODEW(ctypes.Structure):
        _fields_ = [("dmDeviceName", W.WCHAR * 32), ("dmSpecVersion", W.WORD), ("dmDriverVersion", W.WORD),
                    ("dmSize", W.WORD), ("dmDriverExtra", W.WORD), ("dmFields", W.DWORD),
                    ("dmPositionX", ctypes.c_long), ("dmPositionY", ctypes.c_long),
                    ("dmDisplayOrientation", W.DWORD), ("dmDisplayFixedOutput", W.DWORD),
                    ("dmColor", ctypes.c_short), ("dmDuplex", ctypes.c_short), ("dmYResolution", ctypes.c_short),
                    ("dmTTOption", ctypes.c_short), ("dmCollate", ctypes.c_short), ("dmFormName", W.WCHAR * 32),
                    ("dmLogPixels", W.WORD), ("dmBitsPerPel", W.DWORD), ("dmPelsWidth", W.DWORD),
                    ("dmPelsHeight", W.DWORD), ("dmDisplayFlags", W.DWORD), ("dmDisplayFrequency", W.DWORD),
                    ("dmICMMethod", W.DWORD), ("dmICMIntent", W.DWORD), ("dmMediaType", W.DWORD),
                    ("dmDitherType", W.DWORD), ("dmReserved1", W.DWORD), ("dmReserved2", W.DWORD),
                    ("dmPanningWidth", W.DWORD), ("dmPanningHeight", W.DWORD)]
    return DEVMODEW


def _win_displays():
    import ctypes
    from ctypes import wintypes as W

    class DISPLAY_DEVICEW(ctypes.Structure):
        _fields_ = [("cb", W.DWORD), ("DeviceName", W.WCHAR * 32), ("DeviceString", W.WCHAR * 128),
                    ("StateFlags", W.DWORD), ("DeviceID", W.WCHAR * 128), ("DeviceKey", W.WCHAR * 128)]
    DM = _devmode()
    u = ctypes.windll.user32
    res = []
    i = 0
    while True:
        dd = DISPLAY_DEVICEW()
        dd.cb = ctypes.sizeof(dd)
        if not u.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
            break
        i += 1
        if not dd.StateFlags & 1:                         # DISPLAY_DEVICE_ATTACHED_TO_DESKTOP
            continue
        cur = DM()
        cur.dmSize = ctypes.sizeof(DM)
        u.EnumDisplaySettingsW(dd.DeviceName, -1, ctypes.byref(cur))     # ENUM_CURRENT_SETTINGS
        modes, j = set(), 0
        while True:
            m = DM()
            m.dmSize = ctypes.sizeof(DM)
            if not u.EnumDisplaySettingsW(dd.DeviceName, j, ctypes.byref(m)):
                break
            modes.add((m.dmPelsWidth, m.dmPelsHeight, m.dmDisplayFrequency))
            j += 1
        res.append({"id": dd.DeviceName, "name": f"{dd.DeviceString} ({dd.DeviceName.split('.')[-1]})",
                    "w": cur.dmPelsWidth, "h": cur.dmPelsHeight, "hz": cur.dmDisplayFrequency, "hdr": None,
                    "vrr": None, "modes": sorted(modes, reverse=True)})
    return res


def _win_set_display(o):
    import ctypes
    DM = _devmode()
    m = DM()
    m.dmSize = ctypes.sizeof(DM)
    m.dmPelsWidth, m.dmPelsHeight, m.dmDisplayFrequency = int(o["w"]), int(o["h"]), int(o["hz"])
    m.dmFields = 0x80000 | 0x100000 | 0x400000            # DM_PELSWIDTH | DM_PELSHEIGHT | DM_DISPLAYFREQUENCY
    r = ctypes.windll.user32.ChangeDisplaySettingsExW(o["id"], ctypes.byref(m), None, 0x1, None)   # CDS_UPDATEREGISTRY
    if r != 0:
        raise RuntimeError(f"skjermen godtok ikke {o['w']}×{o['h']} @ {o['hz']} Hz (kode {r})")


def save_display(name, icon="🖥️"):
    c = cfg()
    p = {"id": _new_id(name, {x["id"] for x in c["display"]}), "name": name.strip()[:30] or "Skjermprofil",
         "icon": icon, "outputs": [{k: o[k] for k in ("id", "name", "w", "h", "hz", "hdr", "vrr")} for o in displays()]}
    c["display"].append(p)
    save_cfg(c)
    return p


def apply_display(pid):
    p = next((x for x in cfg()["display"] if x["id"] == pid), None)
    if not p:
        raise ValueError("fant ikke skjermprofilen")
    have = {o["id"]: o for o in displays()}
    done = 0
    for o in p["outputs"]:
        if o["id"] in have:
            cur = have[o["id"]]
            if (o["w"], o["h"], o["hz"]) not in cur["modes"]:
                o = {**o, "w": None}                      # modusen finnes ikke lenger – bare HDR/VRR
            _set_display(o)
            done += 1
    if not done:
        raise RuntimeError("ingen av skjermene i profilen er koblet til")
    c = cfg()
    c["display_active"] = pid
    save_cfg(c)
    return f"Skjerm: {p['name']} ✓"


def delete(kind, pid):
    c = cfg()
    c[kind] = [x for x in c[kind] if x["id"] != pid]
    save_cfg(c)


# ==========================================================================
# NATTLYS OG LYSSTYRKE
# ==========================================================================
def _gnome():
    import shutil
    return "GNOME" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper() and bool(shutil.which("gsettings"))


_GCOL = "org.gnome.settings-daemon.plugins.color"


def _hyprsunset():
    import desktop
    import shutil
    return desktop.is_hypr() and bool(shutil.which("hyprsunset"))


def _hyprsunset_running():
    return _run(["pgrep", "-x", "hyprsunset"], 5)[0] == 0


def night_state():
    if IS_WIN:
        return None
    if _hyprsunset():                                  # Hyprland: hyprsunset (styres med hyprctl hyprsunset)
        if not _hyprsunset_running():
            return {"on": False, "temp": 4000, "running": False}
        import desktop
        ok, out = desktop.hyprctl("hyprsunset", "temperature")
        m = re.search(r"\b(\d{4})\b", out)
        if ok and m:
            t = int(m.group(1))
            return {"on": t < 6000, "temp": t if t < 6000 else 4000, "running": t < 6000}
        last = cfg().get("hyprsunset", {})                # eldre/nyere hyprsunset som ikke oppgir temperaturen
        return {"on": bool(last.get("on")), "temp": int(last.get("temp", 4000)), "running": bool(last.get("on"))}
    if _gnome():
        on = _run(["gsettings", "get", _GCOL, "night-light-enabled"], 5)[1].strip() == "true"
        t = _run(["gsettings", "get", _GCOL, "night-light-temperature"], 5)[1].strip().split()[-1:]
        return {"on": on, "temp": int(t[0]) if t and t[0].isdigit() else 4000, "running": on}
    try:
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

        def prop(k):
            return bus.call_sync("org.kde.KWin", "/org/kde/KWin/NightLight", "org.freedesktop.DBus.Properties",
                                 "Get", GLib.Variant("(ss)", ("org.kde.KWin.NightLight", k)), None, 0, 2000,
                                 None).unpack()[0]
        return {"on": bool(prop("enabled")), "temp": int(prop("targetTemperature")), "running": bool(prop("running"))}
    except Exception:  # noqa: BLE001
        return None


def set_night(on, temp=None):
    """Slå nattlys på (alltid på, med temperatur) eller av."""
    if IS_WIN:
        os.startfile("ms-settings:nightlight")  # noqa: S606
        return "Nattlys-innstillingene i Windows er åpnet"
    if _hyprsunset():
        import desktop
        import subprocess
        t = max(1000, min(6500, int(temp or 4000)))
        if not _hyprsunset_running():
            if not on:
                return "Nattlys av"
            subprocess.Popen(["hyprsunset", "-t", str(t)], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            c = cfg()
            c["hyprsunset"] = {"on": True, "temp": t}
            save_cfg(c)
            return "Nattlys på ✓"
        ok, out = desktop.hyprctl("hyprsunset", "temperature", str(t)) if on else desktop.hyprctl("hyprsunset",
                                                                                                    "identity")
        if not ok:
            raise RuntimeError(out or "hyprsunset svarte ikke")
        c = cfg()
        c["hyprsunset"] = {"on": bool(on), "temp": t}
        save_cfg(c)
        return "Nattlys på ✓" if on else "Nattlys av"
    if _gnome():                                       # GNOME: alltid på (fra 0 til 24) med valgt temperatur
        _run(["gsettings", "set", _GCOL, "night-light-enabled", "true" if on else "false"], 5)
        if on:
            _run(["gsettings", "set", _GCOL, "night-light-schedule-automatic", "false"], 5)
            _run(["gsettings", "set", _GCOL, "night-light-schedule-from", "0.0"], 5)
            _run(["gsettings", "set", _GCOL, "night-light-schedule-to", "23.99"], 5)
            if temp:
                _run(["gsettings", "set", _GCOL, "night-light-temperature",
                      f"uint32 {max(1700, min(4700, int(temp)))}"], 5)
        return "Nattlys på ✓" if on else "Nattlys av"
    import shutil
    if not shutil.which("kwriteconfig6"):
        import desktop
        if desktop.is_hypr():
            raise RuntimeError("nattlys på Hyprland krever hyprsunset – installer pakken «hyprsunset»")
        raise RuntimeError("nattlys styres herfra på KDE Plasma, GNOME og Hyprland – bruk skrivebordets egne "
                           "innstillinger")
    # --notify: KWin (Plasma 6) leser nattlys-innstillingene på nytt når den får beskjed om endringen –
    # «reconfigure» alene tar dem ikke lenger inn (Plasma 6.8). Temperatur og modus først, så av/på.
    kw = ["kwriteconfig6", "--notify", "--file", "kwinrc", "--group", "NightColor", "--key"]
    args = []
    if on:
        args.append(kw + ["Mode", "Constant"])
        if temp:
            args.append(kw + ["NightTemperature", str(max(1000, min(6500, int(temp))))])
    args.append(kw + ["Active", "true" if on else "false"])
    for a in args:
        code, out = _run(a, 5)
        if code != 0:
            raise RuntimeError(out.strip() or "kunne ikke endre nattlys")
    return "Nattlys på ✓" if on else "Nattlys av"


def _bright_displays():
    try:
        from gi.repository import Gio
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        xml = bus.call_sync("org.kde.ScreenBrightness", "/org/kde/ScreenBrightness",
                            "org.freedesktop.DBus.Introspectable", "Introspect", None, None, 0, 2000,
                            None).unpack()[0]
        return re.findall(r'<node name="(display\d+)"', xml)
    except Exception:  # noqa: BLE001
        return []


def _backlight():
    """(navn, nå, maks) for den innebygde skjermen (bærbare) – eller None."""
    import glob
    for d in sorted(glob.glob("/sys/class/backlight/*")):
        try:
            mx = int(open(d + "/max_brightness").read())
            cur = int(open(d + "/brightness").read())
            if mx > 0:
                return os.path.basename(d), cur, mx
        except (OSError, ValueError):
            continue
    return None


def brightness():
    """Lysstyrke i % (første skjerm), eller None."""
    if IS_WIN:
        code, out = _run(["powershell", "-NoProfile", "-Command",
                          "(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness).CurrentBrightness"], 15)
        try:
            return int(out.strip().splitlines()[0])
        except (ValueError, IndexError):
            return None
    try:
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        for d in _bright_displays():
            path = f"/org/kde/ScreenBrightness/{d}"

            def prop(k, path=path):
                return bus.call_sync("org.kde.ScreenBrightness", path, "org.freedesktop.DBus.Properties", "Get",
                                     GLib.Variant("(ss)", ("org.kde.ScreenBrightness.Display", k)), None, 0, 2000,
                                     None).unpack()[0]
            mx = prop("MaxBrightness")
            return round(100 * prop("Brightness") / mx) if mx else None
    except Exception:  # noqa: BLE001
        pass
    bl = _backlight()                                  # andre skrivebord: bærbar-skjermen
    if bl:
        return round(100 * bl[1] / bl[2])
    return _ddc_get()                                  # eksterne skjermer (DDC/CI) med ddcutil


def _ddc_get():
    import shutil
    if not shutil.which("ddcutil"):
        return None
    code, out = _run(["ddcutil", "--brief", "getvcp", "10"], 15)
    m = re.search(r"VCP 10 C (\d+) (\d+)", out)
    return round(100 * int(m.group(1)) / int(m.group(2))) if code == 0 and m and int(m.group(2)) else None


def _ddc_set(pct):
    import shutil
    if not shutil.which("ddcutil"):
        return False
    code, out = _run(["ddcutil", "detect", "--brief"], 20)
    nums = re.findall(r"^Display (\d+)", out, re.M) or ["1"]
    ok = False
    for n in nums:
        ok = _run(["ddcutil", "--display", n, "setvcp", "10", str(pct)], 15)[0] == 0 or ok
    return ok


def set_brightness(pct):
    pct = max(1, min(100, int(pct)))
    if IS_WIN:
        code, out = _run(["powershell", "-NoProfile", "-Command",
                          f"(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods) | "
                          f"Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{Timeout=0;Brightness={pct}}}"],
                         15)
        if code != 0:
            raise RuntimeError("Denne skjermen kan ikke styres herfra på Windows (bare innebygde skjermer)")
        return f"Lysstyrke {pct} %"
    from gi.repository import Gio, GLib
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    ds = _bright_displays()
    if not ds:
        bl = _backlight()
        if bl:                                         # logind lar brukeren sette lysstyrken selv (alle distroer)
            sysbus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            sysbus.call_sync("org.freedesktop.login1", "/org/freedesktop/login1/session/auto",
                             "org.freedesktop.login1.Session", "SetBrightness",
                             GLib.Variant("(ssu)", ("backlight", bl[0], max(1, round(bl[2] * pct / 100)))),
                             None, 0, 5000, None)
            return f"Lysstyrke {pct} %"
        if _ddc_set(pct):                              # eksterne skjermer på GNOME, Hyprland m.fl.
            return f"Lysstyrke {pct} %"
        raise RuntimeError("skjermen støtter ikke lysstyrke herfra (DDC/CI av i skjermmenyen, eller installer "
                           "«ddcutil»)")
    for d in ds:
        path = f"/org/kde/ScreenBrightness/{d}"
        mx = bus.call_sync("org.kde.ScreenBrightness", path, "org.freedesktop.DBus.Properties", "Get",
                           GLib.Variant("(ss)", ("org.kde.ScreenBrightness.Display", "MaxBrightness")), None, 0, 2000,
                           None).unpack()[0]
        bus.call_sync("org.kde.ScreenBrightness", path, "org.kde.ScreenBrightness.Display", "SetBrightness",
                      GLib.Variant("(iu)", (round(mx * pct / 100), 0)), None, 0, 5000, None)
    return f"Lysstyrke {pct} %"


def state():
    """Alt på én gang – til appen og mobilen."""
    c = cfg()
    return {"audio": c["audio"], "display": c["display"], "audio_active": c.get("audio_active"),
            "display_active": c.get("display_active"), "night": night_state(), "brightness": brightness()}
