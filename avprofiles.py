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
def displays():
    """[{id, name, w, h, hz, hdr, vrr, modes: [(w,h,hz)]}] – skjermene som er koblet til."""
    if IS_WIN:
        return _win_displays()
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


def _set_display(o):
    if IS_WIN:
        return _win_set_display(o)
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
def night_state():
    if IS_WIN:
        return None
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
    args = [["kwriteconfig6", "--file", "kwinrc", "--group", "NightColor", "--key", "Active", "true" if on else "false"]]
    if on:
        args.append(["kwriteconfig6", "--file", "kwinrc", "--group", "NightColor", "--key", "Mode", "Constant"])
        if temp:
            t = max(1000, min(6500, int(temp)))
            args.append(["kwriteconfig6", "--file", "kwinrc", "--group", "NightColor", "--key", "NightTemperature",
                         str(t)])
    for a in args:
        _run(a, 5)
    from gi.repository import Gio
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    bus.call_sync("org.kde.KWin", "/KWin", "org.kde.KWin", "reconfigure", None, None, 0, 5000, None)
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
        return None
    return None


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
        raise RuntimeError("skjermen støtter ikke lysstyrke herfra (DDC/CI av i skjermmenyen?)")
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
