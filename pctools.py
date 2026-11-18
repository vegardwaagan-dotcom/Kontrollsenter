"""PC-verktøy: oppstartsrapport, støymåler for viftene, sikkerhetskopi av mapper til NAS-en og en trygg ytelsestest.

Alt kjøres i bakgrunnen og rapporterer tilbake. Ytelsestesten erstatter «overklokkingsassistent»: den endrer ingenting
på maskinvaren, men måler prosessor, minne og disk og sammenligner med forrige gang.
"""
import array
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

IS_WIN = sys.platform == "win32"
DATA = os.path.expanduser("~/.local/share/systemmonitor")
CFG = os.path.expanduser("~/.config/systemmonitor/pcverktoy.json")


def cfg():
    try:
        with open(CFG) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_cfg(**kw):
    d = cfg()
    d.update(kw)
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    with open(CFG, "w") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)


def _run(cmd, t=20):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=t).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _secs(txt):
    """«1min 2.5s» / «824ms» / «3.6s» -> sekunder."""
    total = 0.0
    for v, u in re.findall(r"([\d.]+)\s*(min|ms|s|h)", txt):
        v = float(v)
        total += v * {"h": 3600, "min": 60, "s": 1, "ms": 0.001}[u]
    return total


# --------------------------------------------------------------------------
# Oppstartsrapport
# --------------------------------------------------------------------------
NICE = {"NetworkManager-wait-online.service": "Venter på nettverket",
        "plasmalogin.service": "Innloggingsskjermen", "uupd.service": "Automatiske oppdateringer (Bazzite)",
        "app-dev.lizardbyte.app.Sunshine.service": "Sunshine (spill på telefonen)",
        "plasma-plasmashell.service": "KDE-skrivebordet", "plasma-startupsound.service": "Oppstartslyd",
        "systemd-suspend.service": "Hvilemodus (ikke oppstart)"}


def boot_report():
    if IS_WIN:
        return {"error": "Oppstartsrapporten finnes foreløpig bare på Linux."}
    head = _run(["systemd-analyze"])
    m = re.search(r"Startup finished in (.*?)= ([\d.]+(?:min )?[\d.]*s)", head.replace("\n", " "))
    parts = {}
    if m:
        for v, k in re.findall(r"([\d.]+(?:min [\d.]+)?m?s) \((\w+)\)", m.group(1)):
            parts[k] = round(_secs(v), 1)
    total = round(_secs(m.group(2)), 1) if m else None

    def blame(args):
        out = []
        for ln in _run(["systemd-analyze"] + args + ["blame"]).splitlines()[:40]:
            mm = re.match(r"\s*(.+?)\s+(\S+\.(?:service|scope|mount|timer|socket))$", ln)
            if mm:
                unit, t = mm.group(2), _secs(mm.group(1))
                if unit in ("systemd-suspend.service", "uupd.service") or unit.endswith(".timer"):
                    continue                              # ikke en del av oppstarten (kjører senere)
                out.append({"unit": unit, "name": NICE.get(unit, unit.replace(".service", "")), "s": round(t, 1)})
        return out[:6]
    sysb, userb = blame([]), blame(["--user"])
    tips = []
    for x in sysb + userb:
        if x["unit"] == "NetworkManager-wait-online.service" and x["s"] > 3:
            tips.append("«Venter på nettverket» kan slås av hvis ingenting trenger nettet før innlogging.")
        if "Sunshine" in x["name"] and x["s"] > 3:
            tips.append("Sunshine starter med PC-en – utsett eller slå den av i Strømming hvis du sjelden bruker den.")
    if parts.get("firmware", 0) > 8:
        tips.append(f"BIOS-en bruker {parts['firmware']:.0f} s – «Fast Boot» i BIOS kan korte dette ned.")
    return {"total": total, "parts": parts, "system": sysb, "user": userb, "tips": tips,
            "autostart": [os.path.basename(f) for f in os.listdir(os.path.expanduser("~/.config/autostart"))]
            if os.path.isdir(os.path.expanduser("~/.config/autostart")) else []}


# --------------------------------------------------------------------------
# Støymåler: viften på ulike hastigheter, målt med mikrofonen
# --------------------------------------------------------------------------
def _record_db(seconds=3.0):
    """Lydnivå i dBFS fra standardmikrofonen (lokalt – ingenting lagres)."""
    rate = 16000
    cmd = (["parecord", "--raw", "--format=s16le", f"--rate={rate}", "--channels=1"] if shutil.which("parecord") else
           ["pw-record", "--format", "s16", "--rate", str(rate), "--channels", "1", "-"])
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    want = int(rate * seconds) * 2
    buf = b""
    t = time.time()
    try:
        while len(buf) < want and time.time() - t < seconds + 3:
            chunk = p.stdout.read(4096)
            if not chunk:
                break
            buf += chunk
    finally:
        p.kill()
    a = array.array("h")
    a.frombytes(buf[: len(buf) - len(buf) % 2])
    if not a:
        raise RuntimeError("fikk ikke lyd fra mikrofonen")
    rms = math.sqrt(sum(x * x for x in a) / len(a)) or 1
    return round(20 * math.log10(rms / 32768), 1)


def noise_test(win, progress=None):
    """Måler støy ved 30/50/70/100 % viftefart og foreslår høyeste fart som er nesten like stille som 30 %.
    Viftene settes alltid tilbake til auto til slutt."""
    if IS_WIN:
        raise RuntimeError("støymåleren finnes foreløpig bare på Linux")
    import remote
    steps = [30, 50, 70, 100]
    res = []
    try:
        base = _record_db(2.5)
        if progress:
            progress(f"Stille rom: {base} dB")
        for v in steps:
            remote.do_action(win, {"a": "fans", "value": v})
            if progress:
                progress(f"Viftene på {v} % – lytter …")
            time.sleep(4)                                # la viftene komme opp i fart
            db = _record_db(3)
            res.append({"pct": v, "db": db, "cpu_t": getattr(win, "_cpu_t", None)})
    finally:
        try:
            remote.do_action(win, {"a": "fans", "value": "auto"})
        except Exception:  # noqa: BLE001
            pass
    quiet = res[0]["db"]
    ok = [r for r in res if r["db"] <= quiet + 3]
    best = max(ok, key=lambda r: r["pct"]) if ok else res[0]
    out = {"base": base, "steps": res, "suggest": best["pct"], "t": time.time(),
           "text": (f"Viftene høres nesten ikke opp til {best['pct']} %. Over det øker støyen merkbart"
                    f" ({res[-1]['db'] - quiet:+.0f} dB ved 100 %).")}
    save_cfg(noise=out)
    return out


# --------------------------------------------------------------------------
# Sikkerhetskopi av mapper til NAS-en (bare nye og endrede filer)
# --------------------------------------------------------------------------
DEFAULT_DIRS = [("Skjermbilder", "~/Bilder/Skjermbilder"), ("Skjermbilder", "~/Pictures/Screenshots"),
                ("Klipp", "~/Videoer/Kontrollsenter"), ("Dokumenter", "~/Dokumenter"), ("Dokumenter", "~/Documents")]


def backup_dirs():
    c = cfg().get("backup_dirs")
    if c is not None:
        return c
    dirs = list(DEFAULT_DIRS)
    try:
        import clips
        cd = clips.load_cfg().get("dir")
        if cd:
            dirs.insert(0, ("Klipp", cd))
    except Exception:  # noqa: BLE001
        pass
    seen, out = set(), []
    for n, p in dirs:
        full = os.path.realpath(os.path.expanduser(p))
        if os.path.isdir(full) and full not in seen:
            seen.add(full)
            out.append({"name": n, "path": p, "on": n != "Dokumenter"})
    return out


def backup_run(progress=None, max_files=2000):
    """Last opp nye/endrede filer til //NAS/…/Kontrollsenter/Sikkerhetskopi/<PC>/<mappe>/."""
    import lanupdate as L
    import savegames
    if not L.on_lan():
        raise RuntimeError("ikke på hjemmenettet")
    man_p = os.path.join(DATA, "nas-backup.json")
    try:
        man = json.load(open(man_p))
    except (OSError, ValueError):
        man = {}
    pc = re.sub(r"[^\w\-]", "_", savegames.pc_name())
    sent = skipped = 0
    size = 0
    for d in [x for x in backup_dirs() if x.get("on")]:
        root = os.path.expanduser(d["path"])
        if not os.path.isdir(root):
            continue
        batch = []
        for dp, _dn, fn in os.walk(root):
            for f in fn:
                full = os.path.join(dp, f)
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                key = full
                sig = [st.st_size, int(st.st_mtime)]
                if man.get(key) == sig:
                    skipped += 1
                    continue
                rel = os.path.relpath(full, root).replace("\\", "/")
                batch.append((full, rel, sig, st.st_size))
        for full, rel, sig, sz in batch[:max_files]:
            remote_dir = "/".join(["Sikkerhetskopi", pc, d["name"]] + rel.split("/")[:-1])
            try:
                L.smb_mkdir(f"{L._split()[2]}/{remote_dir}")
                L._smb(f'cd "{remote_dir}"; put "{full}" "{rel.split("/")[-1]}"', 600)
                man[full] = sig
                sent += 1
                size += sz
                if progress and sent % 10 == 0:
                    progress(f"{sent} filer lastet opp …")
            except Exception:  # noqa: BLE001
                continue
        os.makedirs(DATA, exist_ok=True)
        with open(man_p, "w") as f:
            json.dump(man, f)
    rep = {"t": time.time(), "sent": sent, "skipped": skipped, "bytes": size}
    save_cfg(backup_last=rep)
    return rep


def backup_due():
    c = cfg()
    return c.get("backup_auto") and time.time() - (c.get("backup_last") or {}).get("t", 0) > 7 * 86400


# --------------------------------------------------------------------------
# Trygg ytelsestest (endrer ingenting)
# --------------------------------------------------------------------------
def _hash_work(seconds):
    t = time.time()
    n = 0
    data = b"x" * 65536
    while time.time() - t < seconds:
        hashlib.sha256(data).digest()
        n += 1
    return n


def benchmark(progress=None):
    res = {}
    if progress:
        progress("Prosessor – én kjerne …")
    res["cpu1"] = round(_hash_work(3) / 3 / 100)
    if progress:
        progress("Prosessor – alle kjernene …")
    n = os.cpu_count() or 2
    from multiprocessing.pool import ThreadPool              # sha256 slipper GIL-en – tråder går i parallell
    with ThreadPool(n) as p:
        res["cpuN"] = round(sum(p.map(_hash_work, [3] * n)) / 3 / 100)
    if progress:
        progress("Minne …")
    blob = bytearray(256 * 1024 * 1024)
    t = time.time()
    for _ in range(4):
        bytes(blob)
    res["mem_gbs"] = round(4 * 256 / 1024 / (time.time() - t), 1)
    del blob
    if progress:
        progress("Disk …")
    d = tempfile.mkdtemp(dir=os.path.expanduser("~"))
    try:
        f = os.path.join(d, "test.bin")
        chunk = os.urandom(8 * 1024 * 1024)
        t = time.time()
        with open(f, "wb") as fh:
            for _ in range(64):
                fh.write(chunk)
            fh.flush()
            os.fsync(fh.fileno())
        res["disk_w"] = round(512 / (time.time() - t))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    res["t"] = time.time()
    hist = (cfg().get("bench") or [])[-9:] + [res]
    save_cfg(bench=hist)
    prev = hist[-2] if len(hist) > 1 else None
    if prev:
        res["vs"] = {k: round(100 * (res[k] - prev[k]) / prev[k]) for k in ("cpu1", "cpuN", "mem_gbs", "disk_w")
                     if prev.get(k)}
    return res
