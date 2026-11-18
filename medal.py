"""Medal (medal.tv) som klippeprogram på Windows – i stedet for Xbox Game Bar.

Medal tar opp i bakgrunnen og lagrer de siste sekundene når du trykker klippetasten (standard F8). Kontrollsenter:
* lar Medal selv eie tasten (registrerer den ikke selv, så Medal får tastetrykket),
* sender Medals tast når du trykker «Lagre klipp» i appen eller på mobilen,
* finner Medal-mappen (Innstillinger → PC Storage → Capture Folder Location i Medal) og viser klippene derfra –
  også i undermappene Medal lager per spill.
"""
import glob
import os
import re
import subprocess
import sys
import threading
import time

IS_WIN = sys.platform == "win32"


def exe():
    for p in (r"%LOCALAPPDATA%\Medal\Medal.exe", r"%LOCALAPPDATA%\Medal\app-*\Medal.exe",
              r"%ProgramFiles%\Medal\Medal.exe"):
        hits = sorted(glob.glob(os.path.expandvars(p)))
        if hits:
            return hits[-1]
    return None


def installed():
    return IS_WIN and exe() is not None


def running():
    if not IS_WIN:
        return False
    try:
        import psutil
        return any((p.info.get("name") or "").lower() == "medal.exe" for p in psutil.process_iter(["name"]))
    except Exception:  # noqa: BLE001
        return False


def start():
    """Start Medal i bakgrunnen hvis det ikke kjører."""
    if running():
        return True
    upd = os.path.expandvars(r"%LOCALAPPDATA%\Medal\Update.exe")
    cmd = [upd, "--processStart", "Medal.exe"] if os.path.exists(upd) else ([exe()] if exe() else None)
    if not cmd:
        return False
    subprocess.Popen(cmd, creationflags=0x08000000, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


def _mp4_count(root, limit=3):
    n = 0
    for _ in glob.iglob(os.path.join(root, "**", "*.mp4"), recursive=True):
        n += 1
        if n >= limit:
            break
    return n


def _from_settings():
    """Mapper nevnt i Medals egne innstillingsfiler (%APPDATA%\\Medal) som finnes på disken."""
    out = []
    base = os.path.expandvars(r"%APPDATA%\Medal")
    for f in glob.glob(os.path.join(base, "**", "*.json"), recursive=True)[:200]:
        try:
            if os.path.getsize(f) > 3_000_000:
                continue
            txt = open(f, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for m in re.finditer(r'"([A-Za-z]:(?:\\\\|/)[^"]{2,200})"', txt):
            p = m.group(1).replace("\\\\", "\\")
            if os.path.isdir(p) and ("medal" in p.lower() or "clip" in p.lower()):
                out.append(p)
    return out


_DIR = {"t": 0, "p": None}


def find_dir(cfg_dir=None):
    """Mappen Medal lagrer klipp i: valgt mappe, Medals egne innstillinger, eller vanlige standardsteder."""
    if cfg_dir and os.path.isdir(cfg_dir):
        return cfg_dir
    if _DIR["p"] and time.time() - _DIR["t"] < 300:
        return _DIR["p"]
    cands = _from_settings()
    home = os.environ.get("USERPROFILE", os.path.expanduser("~"))
    for d in ("C", "D", "E"):
        cands += [f"{d}:\\Medal", f"{d}:\\MedalTV", f"{d}:\\Medal\\Clips"]
    cands += [os.path.join(home, "Videos", "Medal"), os.path.join(home, "Videos", "MedalTV"),
              os.path.join(home, "Medal"), os.path.join(home, "Videos", "Medal", "Clips")]
    best = None
    for c in cands:
        if os.path.isdir(c):
            if _mp4_count(c):
                best = c
                break
            best = best or c
    _DIR.update(t=time.time(), p=best)
    return best


# ---- klipp i mappen (rekursivt) ----
_INDEX = {}


def clips(root, limit=60):
    out = []
    if not root:
        return out
    for f in glob.iglob(os.path.join(root, "**", "*.mp4"), recursive=True):
        try:
            st = os.stat(f)
        except OSError:
            continue
        name = os.path.basename(f)
        _INDEX[name] = f
        out.append({"name": name, "size": st.st_size, "t": st.st_mtime})
    return sorted(out, key=lambda x: -x["t"])[:limit]


def path_of(root, name):
    p = _INDEX.get(name)
    if p and os.path.isfile(p):
        return p
    clips(root, 100000)
    p = _INDEX.get(name)
    return p if p and os.path.isfile(p) else None


# ---- lagre ----
def press(spec):
    """Trykk Medals klippetast (f.eks. «F8» eller «Ctrl+Shift+F8»)."""
    import ctypes
    import clips as C
    mods, key = C.parse_key(spec)
    _m, vk = C.win_code(spec)
    mod_vk = {"Ctrl": 0x11, "Shift": 0x10, "Alt": 0x12, "Meta": 0x5B}
    u = ctypes.windll.user32
    for m in mods:
        u.keybd_event(mod_vk[m], 0, 0, 0)
    u.keybd_event(vk, 0, 0, 0)
    time.sleep(0.05)
    u.keybd_event(vk, 0, 2, 0)
    for m in reversed(mods):
        u.keybd_event(mod_vk[m], 0, 2, 0)


def watch_new(root, since, done, timeout=45):
    """Vent på at Medal skriver ferdig et nytt klipp, og kall done(sti)."""
    def work():
        end = time.time() + timeout
        seen = None
        while time.time() < end:
            time.sleep(1.5)
            new = [c for c in clips(root, 5) if c["t"] > since]
            if not new:
                continue
            p = _INDEX.get(new[0]["name"])
            try:
                size = os.path.getsize(p)
            except OSError:
                continue
            if seen == size:                              # størrelsen har sluttet å vokse → ferdig skrevet
                done(p)
                return
            seen = size
    threading.Thread(target=work, daemon=True).start()


def status(cfg):
    root = find_dir(cfg.get("medal_dir"))
    return {"installed": installed(), "running": running(), "dir": root, "key": cfg.get("medal_key") or "F8"}
