"""Hvilken DLSS spillet faktisk bruker – lest fra filene spillprosessen har lastet inn (Linux: /proc/PID/maps,
Windows: psutil). Viser versjonen av oppskalering (DLSS), bildegenerering (DLSS-G) og Ray Reconstruction (DLSS-D),
og om driveren har lastet ned en nyere modell (NGX-oppdatereren).
"""
import glob
import os
import re
import sys
import time

IS_WIN = sys.platform == "win32"
KIND = {"nvngx_dlss.dll": "DLSS", "nvngx_dlssg.dll": "Bildegenerering", "nvngx_dlssd.dll": "Ray Reconstruction"}
_VER = {}
_CACHE = {"t": 0, "v": None}


def dll_version(path):
    """Filversjonen fra DLL-ens versjonsressurs (f.eks. «310.4.0.0»), eller None."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = (path, st.st_mtime)
    if key in _VER:
        return _VER[key]
    v = None
    try:
        with open(path, "rb") as f:
            data = f.read()
        i = data.rfind(b"\xbd\x04\xef\xfe")                     # VS_FIXEDFILEINFO
        if i > 0:
            import struct
            ms, ls = struct.unpack_from("<II", data, i + 8)
            v = f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
    except OSError:
        pass
    _VER[key] = v
    return v


def _short(v):
    """310.4.0.0 → 310.4 (DLSS 4/4.5); 3.7.10.0 → 3.7.10"""
    if not v:
        return "?"
    p = v.split(".")
    while len(p) > 2 and p[-1] == "0":
        p.pop()
    return ".".join(p)


def generation(v):
    """Hvilken DLSS-generasjon en versjon hører til (omtrent)."""
    try:
        major, minor = (int(x) for x in v.split(".")[:2])
    except (ValueError, AttributeError):
        return ""
    if major >= 310:
        return "DLSS 4.5" if minor >= 5 else "DLSS 4"
    if major >= 3:
        return "DLSS 3"
    if major == 2:
        return "DLSS 2"
    return "DLSS 1" if major == 1 else ""


def _maps_linux():
    """{pid: [filer]} for prosesser som har lastet inn DLSS-filer."""
    out = {}
    for d in glob.glob("/proc/[0-9]*/maps"):
        try:
            with open(d, "rb") as f:
                data = f.read()
        except OSError:
            continue
        if b"nvngx" not in data.lower() and b"ngx/models" not in data.lower():
            continue
        files = {m.decode(errors="replace") for m in re.findall(rb"(/\S[^\n]*?(?:nvngx_dlss\w*\.dll|\.bin))\n", data)
                 if b"nvngx" in m.lower() or b"ngx/models" in m.lower()}
        if files:
            out[int(d.split("/")[2])] = sorted(files)
    return out


def _maps_win():
    out = {}
    try:
        import psutil
        for p in psutil.process_iter(["pid", "name"]):
            try:
                fs = [m.path for m in p.memory_maps() if "nvngx_dlss" in m.path.lower()]
            except Exception:  # noqa: BLE001
                continue
            if fs:
                out[p.info["pid"]] = fs
    except ImportError:
        pass
    return out


def in_use(max_age=10):
    """[(navn, versjon, generasjon, kilde)] for spillet som kjører nå – tom liste hvis ingen bruker DLSS."""
    if time.time() - _CACHE["t"] < max_age and _CACHE["v"] is not None:
        return _CACHE["v"]
    res = []
    for _pid, files in (_maps_win() if IS_WIN else _maps_linux()).items():
        for f in files:
            base = os.path.basename(f).lower()
            if base in KIND:
                v = dll_version(f)
                res.append((KIND[base], _short(v), generation(v), "spillets egen fil"))
            m = re.search(r"NGX/models/(dlss\w*)/versions/(\d+)/", f, re.I)
            if m:                                         # nyere modell lastet ned av driveren
                kind = {"dlss": "DLSS", "dlssg": "Bildegenerering", "dlssd": "Ray Reconstruction"}.get(m.group(1).lower(),
                                                                                                       m.group(1))
                n = int(m.group(2))
                ver = f"{n >> 48}.{(n >> 32) & 0xFFFF}.{(n >> 16) & 0xFFFF}" if n > 0xFFFFFFFF else str(n)
                res.append((kind, ver, generation(ver), "nyeste fra driveren"))
    seen, uniq = set(), []
    for r in res:
        if (r[0], r[3]) not in seen:
            seen.add((r[0], r[3]))
            uniq.append(r)
    _CACHE.update(t=time.time(), v=uniq)
    return uniq


def summary():
    """Én linje til skjermen/mobilen, f.eks. «DLSS 310.4 (DLSS 4) · Bildegenerering 310.4»."""
    u = in_use()
    if not u:
        return ""
    best = {}
    for kind, ver, gen, src in u:                         # driverens nyere modell vinner over spillets egen
        if kind not in best or src == "nyeste fra driveren":
            best[kind] = (ver, gen, src)
    return " · ".join(f"{k} {v}" + (f" ({g})" if g and k == "DLSS" else "") for k, (v, g, _s) in best.items())


def game_dlss(folder):
    """DLSS-versjonen et installert spill har med seg (for Bibliotek-listen) – eller None."""
    if not folder or not os.path.isdir(folder):
        return None
    for root, _dirs, files in os.walk(folder):
        if "nvngx_dlss.dll" in (f.lower() for f in files):
            name = next(f for f in files if f.lower() == "nvngx_dlss.dll")
            v = dll_version(os.path.join(root, name))
            return f"{_short(v)} ({generation(v)})" if v else None
        if root.count(os.sep) - folder.count(os.sep) > 6:
            _dirs[:] = []
    return None
