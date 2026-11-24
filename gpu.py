"""GPU-innstillinger: NVIDIA, AMD (OverDrive) og Intel – bare for skjermkort som faktisk finnes i maskinen.

Linux: leser sysfs og nvidia-smi; endringer går gjennom root-hjelperen /usr/local/bin/systemmonitor-gpu
(satt opp én gang med passord, godtar bare faste kommandoer med kontrollerte verdier).
Windows: nvidia-smi (spør om administrator), og knapper til AMD Software / Intel Graphics Software.
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys

IS_WIN = sys.platform == "win32"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
HELPER = "/usr/local/bin/systemmonitor-gpu"
CFG = os.path.expanduser("~/.config/systemmonitor/gpu.json")
ENV_FILE = os.path.expanduser("~/.config/environment.d/90-kontrollsenter-gpu.conf")
VENDORS = {"0x10de": "nvidia", "0x1002": "amd", "0x8086": "intel"}
FLAGS = {"creationflags": 0x08000000} if IS_WIN else {}


def _run(cmd, timeout=20):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **FLAGS)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


def _read(path, default=None):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def cfg():
    try:
        with open(CFG, encoding="utf-8") as f:
            c = json.load(f)
    except (OSError, ValueError):
        c = {}
    return {"apply_on_start": False, "saved": {}, **c}


def save_cfg(c):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    with open(CFG, "w", encoding="utf-8") as f:
        json.dump(c, f, indent=1)


def remember(gpu_id, key, value):
    c = cfg()
    c["saved"].setdefault(gpu_id, {})[key] = value
    save_cfg(c)


# --------------------------------------------------------------------------
# Finn skjermkortene
# --------------------------------------------------------------------------
def nvidia_smi():
    if IS_WIN:
        for p in (shutil.which("nvidia-smi"), r"C:\Windows\System32\nvidia-smi.exe",
                  r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"):
            if p and os.path.exists(p):
                return p
        return None
    return shutil.which("nvidia-smi")


def _nv_list():
    smi = nvidia_smi()
    if not smi:
        return []
    code, out = _run([smi, "--query-gpu=index,name,pci.bus_id", "--format=csv,noheader"])
    res = []
    if code == 0:
        for ln in out.strip().splitlines():
            parts = [x.strip() for x in ln.split(",")]
            if len(parts) >= 3 and parts[0].isdigit():
                res.append({"idx": int(parts[0]), "name": parts[1], "bus": parts[2].lower()[-12:]})
    return res


def detect():
    """[{id, vendor, name, card, idx, driver, integrated}] – bare kort som finnes."""
    out = []
    nv = _nv_list()
    if IS_WIN:
        ps = ("Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name + '|' + $_.PNPDeviceID + '|' + "
              "$_.DriverVersion }")
        code, txt = _run(["powershell", "-NoProfile", "-Command", ps], 30)
        for ln in txt.splitlines():
            parts = ln.strip().split("|")
            if len(parts) < 3:
                continue
            name, pnp, drv = parts
            m = re.search(r"VEN_([0-9A-F]{4})", pnp, re.I)
            vendor = VENDORS.get("0x" + m.group(1).lower()) if m else None
            if not vendor:
                continue                                       # virtuelle skjermer o.l.
            g = {"id": f"{vendor}-{len(out)}", "vendor": vendor, "name": name, "driver": drv, "card": None,
                 "idx": None, "integrated": vendor == "intel" or "Radeon(TM) Graphics" in name or "610M" in name}
            if vendor == "nvidia" and nv:
                g["idx"] = nv[min(len([x for x in out if x["vendor"] == "nvidia"]), len(nv) - 1)]["idx"]
            out.append(g)
        return out
    for c in sorted(glob.glob("/sys/class/drm/card[0-9]*")):
        if not re.fullmatch(r"card\d+", os.path.basename(c)):
            continue
        dev = os.path.join(c, "device")
        vendor = VENDORS.get(_read(os.path.join(dev, "vendor"), ""))
        if not vendor:
            continue
        bus = os.path.basename(os.path.realpath(dev))
        drv = os.path.basename(os.path.realpath(os.path.join(dev, "driver"))) if os.path.exists(
            os.path.join(dev, "driver")) else "?"
        name = _read(os.path.join(dev, "product_name"))
        idx = None
        if vendor == "nvidia":
            for g in nv:
                if g["bus"] and bus.lower().endswith(g["bus"][-7:]):
                    idx, name = g["idx"], g["name"]
            if idx is None and nv:
                idx, name = nv[0]["idx"], nv[0]["name"]
        if not name:
            code, txt = _run(["lspci", "-s", bus], 10)
            m = re.search(r"\[(?:AMD/ATI|Intel Corporation)?\]?\s*(.*?)(?:\(rev|$)", txt.split(":", 2)[-1]) if code == 0 else None
            name = (txt.split(": ", 1)[-1].split("(rev")[0].strip() if code == 0 and txt else vendor.upper())
            name = re.sub(r"^(Advanced Micro Devices, Inc\. \[AMD/ATI\]|Intel Corporation)\s*", "", name)
            br = re.search(r"\[(.*?)\]", name)                      # «Granite Ridge [Radeon 610M]» → «Radeon 610M»
            if br:
                name = br.group(1)
            if vendor == "amd" and not name.lower().startswith(("amd", "radeon")):
                name = "AMD " + name
            elif vendor == "amd" and name.lower().startswith("radeon"):
                name = "AMD " + name
        integrated = vendor == "intel" or (vendor == "amd" and _read(os.path.join(dev, "mem_info_vram_total"), "0")
                                            and int(_read(os.path.join(dev, "mem_info_vram_total"), "0")) < 2 ** 31)
        out.append({"id": f"{vendor}-{os.path.basename(c)}", "vendor": vendor, "name": name, "driver": drv,
                    "card": os.path.basename(c), "idx": idx, "integrated": bool(integrated)})
    return out


# --------------------------------------------------------------------------
# NVIDIA
# --------------------------------------------------------------------------
NV_FIELDS = ["name", "driver_version", "vbios_version", "pcie.link.gen.current", "pcie.link.gen.max",
             "pcie.link.width.current", "pcie.link.width.max", "memory.total", "memory.used", "temperature.gpu",
             "power.draw", "power.limit", "power.min_limit", "power.max_limit", "power.default_limit",
             "clocks.gr", "clocks.mem", "clocks.max.graphics", "clocks.max.memory", "persistence_mode",
             "fan.speed", "utilization.gpu", "pstate"]


def nvidia_state(idx):
    smi = nvidia_smi()
    code, out = _run([smi, "-i", str(idx), "--query-gpu=" + ",".join(NV_FIELDS), "--format=csv,noheader,nounits"])
    if code != 0:
        raise RuntimeError(out.strip()[-200:])
    vals = [x.strip() for x in out.strip().splitlines()[0].split(",")]
    st = dict(zip(NV_FIELDS, vals))

    def num(k):
        try:
            return float(st.get(k))
        except (TypeError, ValueError):
            return None
    for k in NV_FIELDS[3:]:
        if k not in ("persistence_mode", "pstate"):
            st[k] = num(k)
    st["persistence"] = str(vals[NV_FIELDS.index("persistence_mode")]).lower() == "enabled"
    return st


def nvidia_settings_app():
    if IS_WIN:
        for p in (r"%ProgramFiles%\NVIDIA Corporation\NVIDIA app\CEF\NVIDIA app.exe",
                  r"%ProgramFiles%\NVIDIA Corporation\Control Panel Client\nvcplui.exe"):
            p = os.path.expandvars(p)
            if os.path.exists(p):
                return [p]
        return None
    return ["nvidia-settings"] if shutil.which("nvidia-settings") else None


# --------------------------------------------------------------------------
# AMD
# --------------------------------------------------------------------------
LEVELS = [("auto", "Automatisk"), ("low", "Lavest (sparer strøm)"), ("high", "Høyest (full fart hele tiden)"),
          ("manual", "Manuelt (OverDrive/profil)"), ("profile_standard", "Profil: standard"),
          ("profile_peak", "Profil: topp"), ("profile_min_sclk", "Profil: laveste GPU-klokke"),
          ("profile_min_mclk", "Profil: laveste minneklokke")]


def _hwmon(dev):
    h = sorted(glob.glob(os.path.join(dev, "hwmon", "hwmon*")))
    return h[0] if h else None


def parse_od(text):
    """pp_od_clk_voltage → {"sclk": [(idx, mhz)], "mclk": [...], "range": {"sclk": (lo, hi), ...}, "vo": mv|None}"""
    od = {"sclk": [], "mclk": [], "range": {}, "vo": None, "vo_range": None}
    sec = None
    for ln in (text or "").splitlines():
        s = ln.strip()
        if s.endswith(":") and s[:-1].isupper():
            sec = s[:-1]
            continue
        m = re.match(r"^(\d+):\s*(\d+)\s*Mhz", s, re.I)
        if m and sec in ("OD_SCLK", "OD_MCLK"):
            od["sclk" if sec == "OD_SCLK" else "mclk"].append((int(m.group(1)), int(m.group(2))))
            continue
        m = re.match(r"^(SCLK|MCLK):\s*(\d+)\s*Mhz\s+(\d+)\s*Mhz", s, re.I)
        if m and sec == "OD_RANGE":
            od["range"][m.group(1).lower()] = (int(m.group(2)), int(m.group(3)))
            continue
        m = re.match(r"^VDDGFX_OFFSET:\s*(-?\d+)\s*mV\s+(-?\d+)\s*mV", s, re.I)
        if m and sec == "OD_RANGE":
            od["vo_range"] = (int(m.group(1)), int(m.group(2)))
            continue
        m = re.match(r"^(-?\d+)\s*mV", s, re.I)
        if m and sec == "OD_VDDGFX_OFFSET":
            od["vo"] = int(m.group(1))
    return od


def parse_profiles(text):
    out, cur = [], None
    for ln in (text or "").splitlines():
        m = re.match(r"^\s*(\d+)\s+([A-Z0-9][A-Z0-9_]+)\s*(\*)?", ln)
        if m:
            out.append((int(m.group(1)), m.group(2)))
            if m.group(3):
                cur = int(m.group(1))
    return out, cur


def amd_state(card):
    dev = f"/sys/class/drm/{card}/device"
    st = {"level": _read(os.path.join(dev, "power_dpm_force_performance_level"))}
    od_txt = _read(os.path.join(dev, "pp_od_clk_voltage"))
    st["od"] = parse_od(od_txt) if od_txt else None
    st["profiles"], st["profile"] = parse_profiles(_read(os.path.join(dev, "pp_power_profile_mode")))
    for f, k in (("pp_dpm_sclk", "sclk"), ("pp_dpm_mclk", "mclk")):
        txt = _read(os.path.join(dev, f)) or ""
        cur = re.search(r"(\d+)\s*Mhz\s*\*", txt, re.I)
        st[k] = int(cur.group(1)) if cur else None
    h = _hwmon(dev)
    if h:
        def r(name, div=1):
            v = _read(os.path.join(h, name))
            try:
                return round(int(v) / div, 1)
            except (TypeError, ValueError):
                return None
        st.update(temp=r("temp1_input", 1000), power=r("power1_average", 1e6) or r("power1_input", 1e6),
                  cap=r("power1_cap", 1), cap_min=r("power1_cap_min", 1), cap_max=r("power1_cap_max", 1),
                  cap_default=r("power1_cap_default", 1))
    st["busy"] = _read(os.path.join(dev, "gpu_busy_percent"))
    vt = _read(os.path.join(dev, "mem_info_vram_total"))
    vu = _read(os.path.join(dev, "mem_info_vram_used"))
    st["vram"] = (int(vu) // 2 ** 20, int(vt) // 2 ** 20) if vt and vu else None
    return st


# --------------------------------------------------------------------------
# Intel
# --------------------------------------------------------------------------
def intel_state(card):
    c = f"/sys/class/drm/{card}"
    g = lambda n: (int(_read(os.path.join(c, f"gt_{n}_freq_mhz"), "0") or 0) or None)  # noqa: E731
    return {"cur": g("act") or g("cur"), "min": g("min"), "max": g("max"), "boost": g("boost"),
            "lo": g("RPn"), "hi": g("RP0")}


def intel_app():
    if not IS_WIN:
        return None
    for p in (r"%ProgramFiles%\Intel\Intel Graphics Software\IntelGraphicsSoftware.exe",):
        p = os.path.expandvars(p)
        if os.path.exists(p):
            return [p]
    return ["explorer.exe", "shell:AppsFolder\\AppUp.IntelGraphicsExperience_8j3eq9eme6ctt!App"]


def amd_app():
    if not IS_WIN:
        return None
    p = os.path.expandvars(r"%ProgramFiles%\AMD\CNext\CNext\RadeonSoftware.exe")
    return [p] if os.path.exists(p) else None


# --------------------------------------------------------------------------
# Endre innstillinger
# --------------------------------------------------------------------------
class NeedSetup(Exception):
    pass


HELPER_VERSION = "3"


def helper_ready():
    """Er root-hjelperen installert – og ny nok? (Er den gammel, vises «Gi tilgang» igjen og oppdaterer den.)"""
    if IS_WIN:
        return True
    if not os.path.exists(HELPER) or _run(["sudo", "-n", "-l", HELPER], 10)[0] != 0:
        return False
    return _run(["sudo", "-n", HELPER, "version"], 10)[1].strip() == HELPER_VERSION


def setup_helper():
    """Én gang: installer root-hjelperen (pkexec spør om passord)."""
    import getpass
    code, out = _run(["pkexec", "/bin/bash", os.path.join(APP_DIR, "install-gpu.sh"), getpass.getuser()], 300)
    if code != 0:
        raise RuntimeError("Tilgangen ble ikke gitt (avbrutt?)")
    return True


def run(*args):
    """Kjør en kommando i root-hjelperen (Linux) – kaster med feilteksten hvis det ikke gikk."""
    args = [str(a) for a in args]
    if IS_WIN:
        return _win_nv(args)
    if not os.path.exists(HELPER):
        raise NeedSetup("Kontrollsenter trenger tilgang én gang – trykk «Gi tilgang» øverst")
    code, out = _run(["sudo", "-n", HELPER, *args], 30)
    if code != 0:
        if "password" in out.lower() or "passord" in out.lower():
            raise NeedSetup("Kontrollsenter trenger tilgang én gang – trykk «Gi tilgang» øverst")
        if "ukjent kommando" in out:
            raise NeedSetup("GPU-tilgangen må oppdateres for de nye funksjonene – trykk «Gi tilgang» øverst")
        raise RuntimeError(out.strip().splitlines()[-1] if out.strip() else "feilet")
    return out.strip()


def _win_nv(args):
    """Windows: bare NVIDIA-kommandoene, kjørt som administrator (Windows spør)."""
    smi = nvidia_smi()
    if not smi:
        raise RuntimeError("nvidia-smi finnes ikke")
    cmd, rest = args[0], args[1:]
    m = {"nv-pl": ["-i", rest[0], "-pl", rest[1]] if len(rest) > 1 else None,
         "nv-lgc": ["-i", rest[0], "-lgc", f"{rest[1]},{rest[2]}"] if len(rest) > 2 else None,
         "nv-rgc": ["-i", rest[0], "-rgc"] if rest else None,
         "nv-lmc": ["-i", rest[0], "-lmc", f"{rest[1]},{rest[2]}"] if len(rest) > 2 else None,
         "nv-rmc": ["-i", rest[0], "-rmc"] if rest else None,
         "nv-pm": ["-i", rest[0], "-pm", rest[1]] if len(rest) > 1 else None}.get(cmd)
    if not m or not all(re.fullmatch(r"[\w.,-]+", x) for x in m):
        raise ValueError("ikke støttet på Windows")
    argl = ",".join("'" + x + "'" for x in m)
    ps = f"Start-Process -FilePath '{smi}' -ArgumentList {argl} -Verb RunAs -Wait -WindowStyle Hidden"
    code, out = _run(["powershell", "-NoProfile", "-Command", ps], 120)
    if code != 0:
        raise RuntimeError("Windows ga ikke administratortilgang")
    return "OK"


def apply_saved():
    """Ved oppstart (valgfritt): legg inn de lagrede innstillingene igjen – de nullstilles ved omstart."""
    c = cfg()
    if not c["apply_on_start"] or IS_WIN or not helper_ready():
        return
    for gid, s in c["saved"].items():
        for cmd in s.get("cmds", []):
            try:
                run(*cmd)
            except Exception:  # noqa: BLE001
                pass


def save_cmd(gid, key, cmd):
    """Husk siste kommando per innstilling (for «bruk ved oppstart»)."""
    c = cfg()
    s = c["saved"].setdefault(gid, {})
    keyed = {k: v for k, v in s.get("keyed", {}).items()}
    if cmd is None:
        keyed.pop(key, None)
    else:
        keyed[key] = cmd
    s["keyed"] = keyed
    order = ["level", "profile", "cap", "pl", "pm", "lgc", "lmc", "od_s", "od_m", "od_vo", "od_c", "freq_min",
             "freq_max", "freq_boost"]
    s["cmds"] = [keyed[k] for k in order if k in keyed] + [v for k, v in keyed.items() if k not in order]
    save_cfg(c)


# --------------------------------------------------------------------------
# Spillinnstillinger (Linux): miljøvariabler for nye spill (gjelder etter ny innlogging)
# --------------------------------------------------------------------------
ENV_OPTS = [
    # nøkkel, verdi, navn, forklaring, gjelder (None = alle)
    ("PROTON_ENABLE_NVAPI", "1", "DLSS og NVIDIA Reflex i Proton-spill",
     "Lar Windows-spill i Proton bruke DLSS og Reflex.", "nvidia"),
    ("PROTON_ENABLE_NGX_UPDATER", "1", "Nyeste DLSS automatisk",
     "Proton henter nyeste DLSS-versjon til spill som har eldre.", "nvidia"),
    ("__GL_SHADER_DISK_CACHE_SIZE", "12000000000", "Stor shader-cache (12 GB)",
     "Færre hakk første gang et spill tegner noe nytt.", "nvidia"),
    ("__GL_MaxFramesAllowed", "1", "Lavere forsinkelse (OpenGL/Vulkan)",
     "Færre bilder i kø – raskere respons, litt lavere FPS.", "nvidia"),
    ("NVPRESENT_ENABLE_SMOOTH_MOTION", "1", "NVIDIA Smooth Motion",
     "Dobler bildefrekvensen i spill som ikke har egen bildegenerering (RTX 40/50, driver 570+).", "nvidia"),
    ("DXVK_NVAPI_DRS_NGX_DLSS_SR_OVERRIDE",
     {"DXVK_NVAPI_DRS_NGX_DLSS_SR_OVERRIDE": "on",
      "DXVK_NVAPI_DRS_NGX_DLSS_SR_OVERRIDE_RENDER_PRESET_SELECTION": "render_preset_latest"},
     "Nyeste DLSS-modell (DLSS 4)", "Skarpere bilde: alle spill med DLSS bruker den nyeste modellen. Slå på «Nyeste "
     "DLSS automatisk» også.", "nvidia"),
    ("DXVK_NVAPI_SET_NGX_DEBUG_OPTIONS", "DLSSIndicator=1024,DLSSGIndicator=2", "Vis DLSS-info i spillet",
     "Viser hvilken DLSS-versjon og modus spillet bruker, nede i hjørnet.", "nvidia"),
    ("__GL_THREADED_OPTIMIZATIONS", "1", "Trådede optimaliseringer (OpenGL)",
     "Kan gi høyere FPS i eldre OpenGL-spill som bruker mye prosessor.", "nvidia"),
    ("VKD3D_CONFIG", "dxr", "Raytracing i DX12-spill (AMD)",
     "Slår på raytracing via VKD3D for AMD-kort.", "amd"),
    ("RADV_PERFTEST", "gpl", "Raskere shader-bygging (AMD)",
     "Mindre hakk når spill bygger shadere.", "amd"),
    ("WINE_FULLSCREEN_FSR", "1", "AMD FSR i fullskjerm (Proton-GE)",
     "Skalerer opp med FSR når spillet kjører i lavere oppløsning.", None),
    ("MANGOHUD", "1", "MangoHud i alle spill", "Viser FPS og temperaturer i alle Vulkan/OpenGL-spill.", None),
]


def env_get():
    out = {}
    try:
        with open(ENV_FILE, encoding="utf-8") as f:
            for ln in f:
                m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$", ln.strip())
                if m:
                    out[m.group(1)] = m.group(2)
    except OSError:
        pass
    return out


def env_on(key):
    """Er valget på? (alle variablene det setter må være der)"""
    val = next((v for k, v, *_ in ENV_OPTS if k == key), None)
    cur = env_get()
    if isinstance(val, dict):
        return all(cur.get(k) == v for k, v in val.items())
    return key in cur


def env_set(key, on):
    allowed = {k: v for k, v, *_ in ENV_OPTS}
    if key not in allowed:
        raise ValueError("ukjent innstilling")
    cur = env_get()
    pairs = allowed[key] if isinstance(allowed[key], dict) else {key: allowed[key]}
    for k, v in pairs.items():
        if on:
            cur[k] = v
        else:
            cur.pop(k, None)
    os.makedirs(os.path.dirname(ENV_FILE), exist_ok=True)
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write("# Satt av Kontrollsenter (GPU-innstillinger → Spillinnstillinger). Gjelder etter ny innlogging.\n")
        for k, v in cur.items():
            f.write(f"{k}={v}\n")


# --------------------------------------------------------------------------
# Windows-grafikk
# --------------------------------------------------------------------------
DX_KEY = r"Software\Microsoft\DirectX\UserGpuPreferences"


def win_graphics():
    import winreg
    st = {"hags": None, "windowed": False, "vrr": False}
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers") as k:
            st["hags"] = winreg.QueryValueEx(k, "HwSchMode")[0] == 2
    except OSError:
        pass
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, DX_KEY) as k:
            v = winreg.QueryValueEx(k, "DirectXUserGlobalSettings")[0]
            st["windowed"] = "SwapEffectUpgradeEnable=1" in v
            st["vrr"] = "VRROptimizeEnable=1" in v
    except OSError:
        pass
    return st


def win_dx_set(key, on):
    import winreg
    if key not in ("SwapEffectUpgradeEnable", "VRROptimizeEnable"):
        raise ValueError("ukjent")
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, DX_KEY) as k:
            v = winreg.QueryValueEx(k, "DirectXUserGlobalSettings")[0]
    except OSError:
        v = ""
    parts = dict(p.split("=", 1) for p in v.split(";") if "=" in p)
    parts[key] = "1" if on else "0"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, DX_KEY) as k:
        winreg.SetValueEx(k, "DirectXUserGlobalSettings", 0, winreg.REG_SZ,
                          "".join(f"{a}={b};" for a, b in parts.items()))


def win_hags(on):
    ps = ("Start-Process reg -ArgumentList 'add','HKLM\\SYSTEM\\CurrentControlSet\\Control\\GraphicsDrivers',"
          f"'/v','HwSchMode','/t','REG_DWORD','/d','{2 if on else 1}','/f' -Verb RunAs -Wait -WindowStyle Hidden")
    code, _out = _run(["powershell", "-NoProfile", "-Command", ps], 120)
    if code != 0:
        raise RuntimeError("Windows ga ikke administratortilgang")


# --------------------------------------------------------------------------
# NVIDIA via NVML: klokke-offset, vifter, hva som bremser kortet, videokoderen
# --------------------------------------------------------------------------
_NV = {"lib": None}
REASONS = [(0x1, "tomgang"), (0x2, "låst klokke"), (0x4, "strømgrensen"), (0x8, "maskinvare-brems"),
           (0x20, "for varmt (driveren)"), (0x40, "for varmt (kortet)"), (0x80, "strømtilførselen"),
           (0x100, "skjerminnstilling")]


def _nvml():
    import ctypes
    if _NV["lib"] is None:
        try:
            lib = ctypes.CDLL("nvml.dll" if IS_WIN else "libnvidia-ml.so.1")
            _NV["lib"] = lib if lib.nvmlInit_v2() == 0 else False
        except OSError:
            _NV["lib"] = False
    return _NV["lib"] or None


def nv_extra(idx):
    """{offsets, grenser, vifter, hva som bremser, videokoder} – eller {} hvis NVML ikke finnes."""
    import ctypes
    nv = _nvml()
    if nv is None:
        return {}
    h = ctypes.c_void_p()
    if nv.nvmlDeviceGetHandleByIndex_v2(int(idx), ctypes.byref(h)):
        return {}
    out = {}
    a, b, o = ctypes.c_int(), ctypes.c_int(), ctypes.c_int()
    if not nv.nvmlDeviceGetGpcClkMinMaxVfOffset(h, ctypes.byref(a), ctypes.byref(b)):
        out["core_range"] = (a.value, b.value)
    if not nv.nvmlDeviceGetMemClkMinMaxVfOffset(h, ctypes.byref(a), ctypes.byref(b)):
        out["mem_range"] = (a.value, b.value)
    if not nv.nvmlDeviceGetGpcClkVfOffset(h, ctypes.byref(o)):
        out["core"] = o.value
    if not nv.nvmlDeviceGetMemClkVfOffset(h, ctypes.byref(o)):
        out["mem"] = o.value
    n, sp = ctypes.c_uint(), ctypes.c_uint()
    if not nv.nvmlDeviceGetNumFans(h, ctypes.byref(n)):
        out["fans"] = [sp.value for f in range(n.value) if not nv.nvmlDeviceGetFanSpeed_v2(h, f, ctypes.byref(sp))]
        mi, ma = ctypes.c_uint(), ctypes.c_uint()
        if not nv.nvmlDeviceGetMinMaxFanSpeed(h, ctypes.byref(mi), ctypes.byref(ma)):
            out["fan_range"] = (mi.value, ma.value)
    rs = ctypes.c_ulonglong()
    if not nv.nvmlDeviceGetCurrentClocksEventReasons(h, ctypes.byref(rs)):
        out["reasons"] = [t for bit, t in REASONS if rs.value & bit]
    u, p = ctypes.c_uint(), ctypes.c_uint()
    if not nv.nvmlDeviceGetEncoderUtilization(h, ctypes.byref(u), ctypes.byref(p)):
        out["nvenc"] = u.value
    t = ctypes.c_uint()
    if not nv.nvmlDeviceGetTemperature(h, 0, ctypes.byref(t)):
        out["temp"] = t.value
    return out


FAN_DEF = {"mode": "auto", "pct": 60, "curve": [[40, 30], [60, 45], [75, 70], [85, 100]]}
_FAN = {"last": None}


def fan_cfg(gid):
    return {**FAN_DEF, **(cfg().get("nvfan", {}).get(gid) or {})}


def set_fan(gid, idx, mode, pct=None, curve=None):
    """mode = auto | fast | kurve"""
    c = cfg()
    f = {**FAN_DEF, **(c.get("nvfan", {}).get(gid) or {}), "mode": mode, "idx": int(idx)}
    if pct is not None:
        f["pct"] = max(0, min(100, int(pct)))
    if curve:
        f["curve"] = sorted([[int(a), max(0, min(100, int(b)))] for a, b in curve])[:6]
    c.setdefault("nvfan", {})[gid] = f
    save_cfg(c)
    _FAN["last"] = None
    if mode == "auto":
        run("nv-fan", idx, "auto")
        save_cmd(gid, "fan", None)
        return "Viftene styres av kortet selv igjen"
    if mode == "fast":
        run("nv-fan", idx, f["pct"])
        save_cmd(gid, "fan", ["nv-fan", idx, f["pct"]])
        return f"Viftene går fast på {f['pct']} %"
    save_cmd(gid, "fan", None)
    fan_tick()
    return "Viftene følger kurven"


def _curve_pct(curve, t):
    pts = sorted(curve)
    if t <= pts[0][0]:
        return pts[0][1]
    for (t1, p1), (t2, p2) in zip(pts, pts[1:]):
        if t <= t2:
            return round(p1 + (p2 - p1) * (t - t1) / max(1, t2 - t1))
    return pts[-1][1]


def fan_tick():
    """Hvert 5. sekund (bakgrunnen): viftekurve for NVIDIA-kort som er satt til «kurve»."""
    if IS_WIN:
        return
    for gid, f in (cfg().get("nvfan") or {}).items():
        if f.get("mode") != "kurve":
            continue
        e = nv_extra(f.get("idx", 0))
        if "temp" not in e:
            continue
        pct = _curve_pct(f.get("curve") or FAN_DEF["curve"], e["temp"])
        last = _FAN["last"]
        if last is None or abs(pct - last) >= 3:            # ikke mas på kortet for små endringer
            try:
                run("nv-fan", f.get("idx", 0), pct)
                _FAN["last"] = pct
            except Exception:  # noqa: BLE001
                pass
