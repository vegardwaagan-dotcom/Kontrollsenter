"""Skjermkort og FPS-tak per spill.

Linux (Steam): legges i spillets oppstartsvalg (Bibliotek-fanen) som miljøvariabler:
  * skjermkort: PRIME-offload for NVIDIA, DRI_PRIME/Mesa-valg for AMD og Intel – laget ut fra kortene PC-en har
  * FPS-tak: DXVK_FRAME_RATE / VKD3D_FRAME_RATE (virker i Windows-spill via Proton, uten overlay)
Windows: Windows' egen GPU-preferanse per program (Innstillinger → System → Skjerm → Grafikk), satt for
  spillets .exe-filer i spillmappen.
"""
import glob
import os
import re
import sys

IS_WIN = sys.platform == "win32"
FPS_CHOICES = [0, 30, 45, 60, 90, 120, 144, 165, 240]
OURS = ("DRI_PRIME=", "__NV_PRIME_RENDER_OFFLOAD=", "__GLX_VENDOR_LIBRARY_NAME=", "__VK_LAYER_NV_optimus=",
        "MESA_VK_DEVICE_SELECT=", "DXVK_FILTER_DEVICE_NAME=", "DXVK_FRAME_RATE=", "VKD3D_FRAME_RATE=")


def gpus():
    """Skjermkortene som kan velges (bare når det finnes flere)."""
    try:
        import gpuswitch
        gs = gpuswitch.gpus()
    except Exception:  # noqa: BLE001
        return []
    return gs if len(gs) > 1 else []


def _pci_ids(bus):
    d = f"/sys/bus/pci/devices/{bus}"
    try:
        return open(d + "/vendor").read().strip()[2:], open(d + "/device").read().strip()[2:]
    except OSError:
        return None, None


def gpu_env(g):
    """Miljøvariablene som får et spill til å bruke skjermkortet g (Linux)."""
    if g is None:
        return []
    if g["vendor"] == "nvidia":
        return ["__NV_PRIME_RENDER_OFFLOAD=1", "__GLX_VENDOR_LIBRARY_NAME=nvidia", "__VK_LAYER_NV_optimus=NVIDIA_only"]
    vid, did = _pci_ids(g["id"])
    out = ["DRI_PRIME=pci-" + re.sub(r"[:.]", "_", g["id"]), "__GLX_VENDOR_LIBRARY_NAME=mesa",
           "__VK_LAYER_NV_optimus=non_NVIDIA_only"]
    if vid and did:
        out.append(f"MESA_VK_DEVICE_SELECT={vid}:{did}!")
    word = (g["name"].split() or [""])[-1]
    if re.fullmatch(r"[\w-]+", word):
        out.append(f"DXVK_FILTER_DEVICE_NAME={word}")
    return out


def fps_env(n):
    return [f"DXVK_FRAME_RATE={n}", f"VKD3D_FRAME_RATE={n}"] if n else []


def split(unknown):
    """Plukk ut våre variabler fra resten av oppstartsvalgene: (gpu-id|None, fps|0, resten)."""
    rest, gid, fps = [], None, 0
    toks = list(unknown)
    gs = gpus()
    for t in toks:
        if not t.startswith(OURS):
            rest.append(t)
            continue
        if t.startswith("__NV_PRIME_RENDER_OFFLOAD=1"):
            gid = next((g["id"] for g in gs if g["vendor"] == "nvidia"), gid)
        elif t.startswith("DRI_PRIME=pci-"):
            bus = t.split("pci-", 1)[1]
            gid = next((g["id"] for g in gs if re.sub(r"[:.]", "_", g["id"]) == bus), gid)
        elif t.startswith("DXVK_FRAME_RATE="):
            try:
                fps = int(t.split("=", 1)[1])
            except ValueError:
                pass
    return gid, fps, rest


def tokens(gid, fps):
    g = next((x for x in gpus() if x["id"] == gid), None)
    return gpu_env(g) + fps_env(fps)


# --------------------------------------------------------------------------
# DLSS, bildegenerering og Reflex per spill (NVIDIA, Linux) – samme valg som GPU-innstillinger, men bare for ett spill
# --------------------------------------------------------------------------
DLSS_KEYS = ("dlss", "dlssmode", "dlss5", "fg", "fgmodel", "reflex")


def _dlss_vars():
    import gpu as G
    return {k for _k, _n, _d, opts in G.NV_CHOICES for _i, _t, v in opts for k in v} | {"PROTON_ENABLE_NGX_UPDATER"}


def has_nvidia():
    try:
        import gpu as G
        return any(g["vendor"] == "nvidia" for g in G.detect())
    except Exception:  # noqa: BLE001
        return False


def split_dlss(unknown):
    """({nøkkel: valg}, resten) – plukker DLSS-variablene ut av oppstartsvalgene."""
    import gpu as G
    names = _dlss_vars()
    cur, rest = {}, []
    for t in unknown:
        k, eq, v = t.partition("=")
        if eq and k in names:
            cur[k] = v
        else:
            rest.append(t)
    return {k: G.nv_choice(k, cur) for k in DLSS_KEYS}, rest


def dlss_tokens(sel):
    import gpu as G
    cur = {}
    for k in DLSS_KEYS:
        G.nv_apply(cur, k, (sel or {}).get(k, "spill"))
    if any(k.startswith(G._D) for k in cur):
        cur["PROTON_ENABLE_NGX_UPDATER"] = "1"
    return [f"{k}={v}" for k, v in cur.items()]


# --------------------------------------------------------------------------
# Windows: GPU-preferanse per .exe
# --------------------------------------------------------------------------
DX_KEY = r"Software\Microsoft\DirectX\UserGpuPreferences"
SKIP = re.compile(r"unins|setup|crash|report|redist|vc_redist|dxsetup|launcher_helper|ue4prereq|easyanticheat"
                  r"|battleye|eac_|helper|updater", re.I)


def game_exes(game_dir, limit=12):
    if not game_dir or not os.path.isdir(game_dir):
        return []
    found = []
    for depth in ("*.exe", "*/*.exe", "*/*/*.exe", "*/*/*/*.exe"):
        for f in glob.glob(os.path.join(game_dir, depth)):
            if not SKIP.search(os.path.basename(f)):
                found.append(f)
        if len(found) >= limit:
            break
    return found[:limit]


def win_set(game_dir, pref):
    """pref: 0 = la Windows velge, 1 = strømsparing (integrert), 2 = høy ytelse (dedikert)."""
    import winreg
    exes = game_exes(game_dir)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, DX_KEY) as k:
        for e in exes:
            if pref:
                winreg.SetValueEx(k, e, 0, winreg.REG_SZ, f"GpuPreference={int(pref)};")
            else:
                try:
                    winreg.DeleteValue(k, e)
                except OSError:
                    pass
    return len(exes)


def win_get(game_dir):
    import winreg
    exes = game_exes(game_dir)
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, DX_KEY) as k:
            for e in exes:
                try:
                    v = winreg.QueryValueEx(k, e)[0]
                    m = re.search(r"GpuPreference=(\d)", v)
                    if m:
                        return int(m.group(1))
                except OSError:
                    continue
    except OSError:
        pass
    return 0


# --------------------------------------------------------------------------
# Strømgrense på skjermkortet per spill (settes når spillet starter, tilbake når det slutter)
# --------------------------------------------------------------------------
PL_CHOICES = [0, 60, 75, 90, 100]          # 0 = ikke endre; ellers prosent av standard strømgrense


def pl_apply(pct):
    """Sett strømgrensen på det kraftigste skjermkortet til pct % av standard. Returnerer det som trengs for å
    sette den tilbake, eller None."""
    if not pct:
        return None
    import gpu as G
    gs = [g for g in G.detect() if not g.get("integrated")]
    nv = next((g for g in gs if g["vendor"] == "nvidia" and g.get("idx") is not None), None)
    if nv:
        st = G.nvidia_state(nv["idx"])
        dflt, lo, hi, cur = (st.get("power.default_limit"), st.get("power.min_limit"), st.get("power.max_limit"),
                             st.get("power.limit"))
        if not dflt:
            return None
        w = int(max(lo or 0, min(hi or dflt, dflt * pct / 100)))
        G.run("nv-pl", nv["idx"], w)
        return {"kind": "nv", "idx": nv["idx"], "back": int(cur or dflt)}
    amd = next((g for g in gs if g["vendor"] == "amd" and g.get("card")), None)
    if amd:
        st = G.amd_state(amd["card"])
        dflt = st.get("cap_default") or st.get("cap")
        if not dflt:
            return None
        cur = st.get("cap") or dflt
        G.run("amd-cap", amd["card"], int(dflt * pct / 100))
        return {"kind": "amd", "card": amd["card"], "back": int(cur)}
    return None


def pl_restore(info):
    if not info:
        return
    import gpu as G
    if info["kind"] == "nv":
        G.run("nv-pl", info["idx"], info["back"])
    else:
        G.run("amd-cap", info["card"], info["back"])
