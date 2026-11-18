"""PC-er utenfor hjemmet: se hva vennene dine spiller, og temperaturer, CPU, minne og alt om PC-en deres.

Slik virker det (ingen skytjeneste – PC-ene snakker direkte sammen over Tailscale):
  * Begge har Kontrollsenter og Tailscale. Dere deler maskinene med hverandre i Tailscale («Share» på maskinen,
    eller samme tailnet), så PC-ene når hverandre.
  * Du slår på «Del med venner» og sender invitasjonen din (en lenke med adresse og en hemmelig vennekode).
  * Vennen limer den inn under «Legg til venn» – og ser PC-en din. Gjør det samme andre veien.

Vennekoden gir BARE lesetilgang til det du har valgt å dele (spill, temperaturer, maskinvare). Den kan ikke styre
noe, og du kan lage en ny kode når som helst (da mister alle gamle invitasjoner tilgang).
"""
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request

IS_WIN = sys.platform == "win32"
CFG = os.path.expanduser("~/.config/systemmonitor/venner.json")
PORT = 27100
_CACHE = {}
_LOCK = threading.Lock()


def cfg():
    try:
        with open(CFG) as f:
            c = json.load(f)
    except (OSError, ValueError):
        c = {}
    c.setdefault("share", False)
    c.setdefault("show", {"game": True, "temps": True, "hw": True})
    c.setdefault("friends", [])
    if not c.get("key"):
        c["key"] = secrets.token_urlsafe(18)
        save_cfg(c)
    return c


def save_cfg(c):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    tmp = CFG + ".tmp"
    with open(tmp, "w") as f:
        json.dump(c, f, indent=1, ensure_ascii=False)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, CFG)


def set_share(on=None, show=None, new_key=False):
    c = cfg()
    if on is not None:
        c["share"] = bool(on)
    if show:
        c["show"].update({k: bool(v) for k, v in show.items() if k in ("game", "temps", "hw")})
    if new_key:
        c["key"] = secrets.token_urlsafe(18)
    save_cfg(c)
    if c["share"]:
        try:                                       # vennene må kunne nå PC-en
            import remote
            if remote.INSTANCE and not remote.INSTANCE.httpd:
                remote.INSTANCE.start()
        except Exception:  # noqa: BLE001
            pass
    return c


def check_key(k):
    c = cfg()
    return bool(c["share"]) and bool(k) and secrets.compare_digest(str(k), c["key"])


# --------------------------------------------------------------------------
# Adressen min (Tailscale) og invitasjonen
# --------------------------------------------------------------------------
def tailscale_self():
    exe = "tailscale"
    if IS_WIN:
        p = os.path.expandvars(r"%ProgramFiles%\Tailscale\tailscale.exe")
        exe = p if os.path.exists(p) else exe
    try:
        out = subprocess.run([exe, "status", "--json"], capture_output=True, text=True, timeout=8,
                             **({"creationflags": 0x08000000} if IS_WIN else {})).stdout
        d = json.loads(out)
        s = d.get("Self") or {}
        ips = [ip for ip in s.get("TailscaleIPs") or [] if "." in ip]
        return {"dns": (s.get("DNSName") or "").rstrip("."), "ip": ips[0] if ips else None,
                "running": d.get("BackendState") == "Running"}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {"dns": None, "ip": None, "running": False}


def my_name():
    try:
        import savegames
        return savegames.pc_name()
    except Exception:  # noqa: BLE001
        return socket.gethostname()


def invite():
    """«ks-venn://adresse:port/kode?navn=…» – sendes til vennen."""
    t = tailscale_self()
    addr = t["dns"] or t["ip"]
    if not addr:
        return None
    return f"ks-venn://{addr}:{PORT}/{cfg()['key']}?navn={urllib.parse.quote(my_name())}"


def parse_invite(text):
    m = re.search(r"ks-venn://([\w.\-]+):(\d+)/([\w\-]+)(?:\?navn=([^\s]+))?", (text or "").strip())
    if not m:
        raise ValueError("ugyldig invitasjon – den skal starte med ks-venn://")
    return {"addr": m.group(1), "port": int(m.group(2)), "key": m.group(3),
            "name": urllib.parse.unquote(m.group(4) or m.group(1).split(".")[0])}


def add_friend(text, name=None):
    f = parse_invite(text)
    if name:
        f["name"] = name.strip()[:40]
    c = cfg()
    c["friends"] = [x for x in c["friends"] if not (x["addr"] == f["addr"] and x["port"] == f["port"])] + [f]
    save_cfg(c)
    return f


def remove_friend(addr):
    c = cfg()
    c["friends"] = [x for x in c["friends"] if x["addr"] != addr]
    save_cfg(c)


# --------------------------------------------------------------------------
# Det jeg deler (svar på /api/friend)
# --------------------------------------------------------------------------
def snapshot(win):
    c = cfg()
    show = c["show"]
    out = {"name": my_name(), "time": time.time(), "version": None}
    try:
        import applog
        out["version"] = applog.RUNNING
    except Exception:  # noqa: BLE001
        pass
    bg = getattr(win, "bg", None)
    if show.get("game"):
        out["game"] = getattr(bg, "game_name", None) if bg else None
        try:
            import remote
            out["fps"] = remote._live_fps(win)
        except Exception:  # noqa: BLE001
            pass
        try:
            import today
            s = today.summary()
            out["play_s"] = s["play_s"]
            out["top_game"] = s["top"]
        except Exception:  # noqa: BLE001
            pass
        try:
            ses = getattr(getattr(bg, "auto", None), "session", None)
            if ses is not None and getattr(ses, "start", None):
                out["session_min"] = int((time.time() - ses.start) / 60)
        except Exception:  # noqa: BLE001
            pass
    if show.get("temps"):
        nv = win.nvidia.data if getattr(win, "nvidia", None) and win.nvidia.available else None
        out["cpu_t"] = getattr(win, "_cpu_t", None)
        out["cpu_l"] = round(getattr(win, "_cpu_load", 0) or 0)
        out["gpu_t"] = (nv or {}).get("temp")
        out["gpu_l"] = (nv or {}).get("util")
        out["gpu_w"] = (nv or {}).get("power")
        out["watts"] = round(((getattr(win, "_power", {}) or {}).get("total")) or 0) or None
        try:
            from sensors import meminfo
            m = meminfo()
            out["ram_used"] = round((m.get("MemTotal", 0) - m.get("MemAvailable", 0)) / 1048576, 1)
            out["ram_total"] = round(m.get("MemTotal", 0) / 1048576, 1)
        except Exception:  # noqa: BLE001
            pass
        if nv:
            out["vram_used"] = nv.get("mem_used")
            out["vram_total"] = nv.get("mem_total")
        try:
            from sensors import uptime_seconds
            out["uptime"] = int(uptime_seconds())
        except Exception:  # noqa: BLE001
            pass
    if show.get("hw"):
        try:
            import homepcs
            out["model"] = homepcs._model()
            out["os"] = homepcs._distro()
        except Exception:  # noqa: BLE001
            pass
        out.update(_hw())
    return out


_HW = {"t": 0, "d": {}}


def _hw():
    """Maskinvaren (mellomlagret i 10 min – system_info kjører tregere kommandoer)."""
    if time.time() - _HW["t"] < 600:
        return _HW["d"]
    d = {}
    try:
        import tools
        info = dict(tools.system_info())
        for k_in, k_out in (("CPU", "cpu"), ("Grafikk", "gpu"), ("Minne", "ram"), ("Hovedkort", "board"),
                            ("Disker", "disks"), ("Grafikkdrivere", "driver"), ("Kjerne", "kernel")):
            if info.get(k_in):
                d[k_out] = info[k_in]
        if d.get("gpu"):                                   # «NVIDIA Corporation GB203 [GeForce RTX 5070 Ti] […]» → kort
            names = re.findall(r"\[((?:GeForce|Radeon|Arc|Quadro|RTX|Iris|UHD)[^\]]*)\]", d["gpu"])
            if names:
                d["gpu"] = " + ".join(names)
        if d.get("cpu"):
            d["cpu"] = re.sub(r"\s*\d+-Core Processor|\s*·\s*\d+ tråder", "", d["cpu"]).replace("(R)", "").replace("(TM)", "")
        if d.get("board"):
            d["board"] = d["board"].replace("ASUSTeK COMPUTER INC. ", "ASUS ").split(" · BIOS")[0]
    except Exception:  # noqa: BLE001
        pass
    _HW.update(t=time.time(), d=d)
    return d


# --------------------------------------------------------------------------
# Vennenes PC-er (henter /api/friend fra hver venn)
# --------------------------------------------------------------------------
def fetch_one(f, timeout=4):
    url = f"http://{f['addr']}:{f.get('port', PORT)}/api/friend?k={urllib.parse.quote(f['key'])}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Kontrollsenter"}),
                                    timeout=timeout) as r:
            d = json.load(r)
        d["online"] = True
        d["_seen"] = time.time()
    except Exception as e:  # noqa: BLE001
        old = _CACHE.get(f["addr"]) or {}
        d = {**{k: v for k, v in old.items() if k in ("model", "os", "cpu", "gpu", "ram", "board", "name")},
             "online": False, "error": "svarer ikke" if "timed out" in str(e) or "refused" in str(e) or
             "Errno" in str(e) else str(e)[:80], "_seen": old.get("_seen")}
    d["friend"] = f["name"]
    d["addr"] = f["addr"]
    with _LOCK:
        _CACHE[f["addr"]] = d
    return d


def fetch_all():
    fs = cfg()["friends"]
    out = [None] * len(fs)

    def one(i, f):
        out[i] = fetch_one(f)
    th = [threading.Thread(target=one, args=(i, f), daemon=True) for i, f in enumerate(fs)]
    for t in th:
        t.start()
    for t in th:
        t.join(6)
    return [x for x in out if x]


def state():
    c = cfg()
    t = tailscale_self()
    return {"share": c["share"], "show": c["show"], "invite": invite() if c["share"] else None,
            "tailscale": t, "friends": fetch_all()}
