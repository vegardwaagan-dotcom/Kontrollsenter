"""PC-assistenten – forklarer og fikser, på vanlig norsk.

  why_slow(win)      «Hvorfor er PC-en treg akkurat nå?» – funn med fiks-knapp
  game_check(win, g) Spillstart-sjekk: strømmodus, varme, minne, disk, oppdateringer i bakgrunnen
  learn(win)         Lærer hva som er normalt (temperatur ved samme last) → unormalt-varsel, støv og kjølepasta
  disk_watch()       Diskvakt: over 90 % → hva som tar plass, med forslag
  ssd_life()         Levetid for SSD/NVMe i klartekst
  weekly_report(win) Ukentlig helserapport (søndag kveld, på mobilen)
  stall_tick(win)    Mye hakking i vinduet → foreslå «Eldre PC»
"""
import json
import os
import sys
import threading
import time

IS_WIN = sys.platform == "win32"
HOME = os.path.expanduser("~")
STATE = os.path.join(HOME, ".local", "share", "systemmonitor", "assistent.json")
_LOCK = threading.Lock()


class Finding:
    """Et funn: tittel, nivå (ok/info/warn/error), forklaring og ev. fiks (tekst, funksjon)."""

    def __init__(self, title, level, detail, fix=None, key=None):
        self.title, self.level, self.detail, self.fix, self.key = title, level, detail, fix, key or title

# --------------------------------------------------------------------------
# Lagret læring (temperatur per lastnivå, ukerapport) – respekterer «Lagring på disk»
# --------------------------------------------------------------------------
_MEM = {}


def _disk_ok():
    try:
        import perf
        return perf.disk_ok("historikk")
    except Exception:  # noqa: BLE001
        return True


def _load():
    if _MEM:
        return _MEM
    d = {}
    if _disk_ok():
        try:
            d = json.load(open(STATE))
        except (OSError, ValueError):
            d = {}
    _MEM.update(d)
    _MEM.setdefault("weeks", {})          # "2026-W47" -> {"cpu": {bucket: [sum, n]}, "gpu": {...}}
    _MEM.setdefault("sent", {})
    return _MEM


def _save():
    if not _disk_ok():
        return
    try:
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        tmp = STATE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(_MEM, f)
        os.replace(tmp, STATE)
    except OSError:
        pass


def _week(t=None):
    import datetime
    y, w, _d = datetime.date.fromtimestamp(t or time.time()).isocalendar()
    return f"{y}-W{w:02d}"


# --------------------------------------------------------------------------
# Målinger fra vinduet
# --------------------------------------------------------------------------
def _now(win):
    nv = win.nvidia.data if getattr(win, "nvidia", None) and win.nvidia.available else {}
    return {"cpu_t": getattr(win, "_cpu_t", None), "cpu_l": getattr(win, "_cpu_load", None) or 0,
            "gpu_t": (nv or {}).get("temp"), "gpu_l": (nv or {}).get("util") or 0,
            "game": getattr(getattr(win, "bg", None), "game_name", None)}


def _top(by="cpu", n=5):
    try:
        import details
        details._top(by, n)                          # sørger for at lista hentes i bakgrunnen
        lst = sorted(details._PROCS["list"], key=lambda m: -m[by])
        return lst[:n]
    except Exception:  # noqa: BLE001
        return []


def _bucket(load):
    return str(int(min(100, max(0, load)) // 10) * 10)


def _human(n):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.0f} {u}" if u in ("B", "KB", "MB") else f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} PB"


UPDATE_PROCS = {"rpm-ostree": "Systemet oppdateres (rpm-ostree)", "dnf": "Systemet oppdateres (dnf)",
                "flatpak": "Programmer oppdateres (Flatpak)", "packagekitd": "Programmer oppdateres",
                "TiWorker.exe": "Windows Update installerer", "MoUsoCoreWorker.exe": "Windows Update jobber",
                "TrustedInstaller.exe": "Windows Update installerer", "wuauclt.exe": "Windows Update jobber",
                "MsMpEng.exe": "Microsoft Defender skanner", "SearchIndexer.exe": "Windows søkeindeksering",
                "steamwebhelper": None, "fwupd": "Fastvare oppdateres"}


def _running_names():
    """Navnene på oppdaterings-/skanneprosessene som faktisk jobber nå (bruker prosessor) – tjenester som bare
    står og venter (fwupd, packagekitd, Defender) telles ikke."""
    try:
        import psutil
        ps = [p for p in psutil.process_iter(["name"]) if p.info.get("name") in UPDATE_PROCS]
        for p in ps:
            try:
                p.cpu_percent(None)
            except psutil.Error:
                pass
        time.sleep(0.3)
        busy = set()
        for p in ps:
            try:
                if p.cpu_percent(None) >= 3:
                    busy.add(p.info["name"])
            except psutil.Error:
                pass
        return busy
    except Exception:  # noqa: BLE001
        return set()


def _kill_fix(name, pids):
    def fix():
        import psutil
        n = 0
        for pid in pids:
            try:
                psutil.Process(pid).terminate()
                n += 1
            except psutil.Error:
                pass
        return f"Lukket {name}" if n else f"Kunne ikke lukke {name}"
    return (f"Lukk {name}", fix)


def _power_fix(win, mode, label):
    def fix():
        import remote
        ok, msg = remote.do_action(win, {"a": "power", "mode": mode})
        return msg
    return (label, fix)


# --------------------------------------------------------------------------
# 1 – Hvorfor er PC-en treg akkurat nå?
# --------------------------------------------------------------------------
def why_slow(win):
    import psutil
    out = []
    m = _now(win)
    # varme
    if (m["cpu_t"] or 0) >= 92:
        out.append(Finding("Prosessoren er svært varm", "error",
                           f"{m['cpu_t']:.0f} °C – den senker farten for å beskytte seg (struping). Sjekk viftene, "
                           "og at luftinntakene ikke er tette.", key="cpuhot"))
    if (m["gpu_t"] or 0) >= 86:
        out.append(Finding("Skjermkortet er svært varmt", "error",
                           f"{m['gpu_t']:.0f} °C – det senker farten. Rengjør støv og sett viftene til «Kraftig».",
                           key="gpuhot"))
    # minne
    vm, sw = psutil.virtual_memory(), psutil.swap_memory()
    if vm.percent >= 88:
        top = _top("mem", 3)
        names = ", ".join(f"{t['name']} ({_human(t['mem'])})" for t in top)
        fix = _kill_fix(top[0]["name"], top[0]["pids"]) if top and top[0]["name"] != m["game"] else None
        out.append(Finding("Minnet er nesten fullt", "error" if vm.percent >= 95 else "warn",
                           f"{vm.percent:.0f} % brukt – PC-en må bruke disken som minne, og da går alt tregt. "
                           f"Mest: {names}.", fix, key="mem"))
    elif sw.total and sw.percent > 50 and vm.percent > 75:
        out.append(Finding("Bruker disken som minne", "warn", f"{sw.percent:.0f} % av vekselfila er i bruk.",
                           key="swap"))
    # prosessor
    load = psutil.cpu_percent(interval=0.4)
    if load >= 85:
        top = [t for t in _top("cpu", 4) if t["name"] != m["game"]]
        if top and top[0]["cpu"] >= 15:
            t = top[0]
            out.append(Finding(f"{t['name']} bruker mye prosessor", "warn",
                               f"{t['cpu']:.0f} % av hele prosessoren. Totalt {load:.0f} %.",
                               _kill_fix(t["name"], t["pids"]), key="cpuhog"))
        else:
            out.append(Finding("Prosessoren jobber for fullt", "warn", f"{load:.0f} % totalt.", key="cpufull"))
    # disk
    for p in psutil.disk_partitions(all=False):
        if any(x in p.mountpoint for x in ("/boot", "/snap", "/var/lib/flatpak", "/run")) or "loop" in p.device:
            continue
        try:
            u = psutil.disk_usage(p.mountpoint)
        except OSError:
            continue
        if u.total > 8 * 2 ** 30 and u.percent >= 90:
            out.append(Finding(f"Disken {p.mountpoint} er nesten full", "error" if u.percent >= 97 else "warn",
                               f"{u.percent:.0f} % full – bare {_human(u.free)} ledig. En full disk gjør hele "
                               "PC-en treg (og Windows trenger plass til oppdateringer).",
                               ("Rydd trygt nå", lambda: _clean_now()), key="diskfull"))
    # oppdateringer og skanning i bakgrunnen
    names = _running_names()
    seen = set()
    for proc, text in UPDATE_PROCS.items():
        if text and proc in names and text not in seen:
            seen.add(text)
            out.append(Finding(text, "info", "Dette bruker disk og prosessor en stund – det går over av seg selv. "
                                               "Vent med spill til det er ferdig om det hakker.", key="bg:" + proc))
    try:
        import updates
        if updates.running():
            out.append(Finding("«Oppdater alt» kjører", "info", "Følg fremdriften øverst i vinduet.", key="upd"))
    except Exception:  # noqa: BLE001
        pass
    # strømmodus
    try:
        prof = win.power.active_profile() if getattr(win, "power", None) else None
        if prof in ("power-saver", "powersave") and (m["game"] or load > 60):
            out.append(Finding("PC-en står i Strømsparing", "warn", "Prosessoren og skjermkortet holdes nede.",
                               _power_fix(win, "performance", "Bytt til Max Ytelse"), key="saver"))
    except Exception:  # noqa: BLE001
        pass
    # oppetid
    try:
        from sensors import uptime_seconds
        days = uptime_seconds() / 86400
        if days >= 7:
            out.append(Finding(f"PC-en har stått på i {days:.0f} dager", "info",
                               "En omstart rydder minnet og fullfører oppdateringer.", key="uptime"))
    except Exception:  # noqa: BLE001
        pass
    # hakking i vinduet (Windows-vakten måler)
    try:
        import winperf
        if winperf.HAKK["n"] >= 5:
            out.append(Finding("Kontrollsenter-vinduet har hakket", "info",
                               f"{winperf.HAKK['n']} ganger (lengst {winperf.HAKK['max'] / 1000:.1f} s). «Eldre PC» i "
                               "Innstillinger → Generelt gjør vinduet lettere.", key="hakk"))
    except Exception:  # noqa: BLE001
        pass
    # unormalt varm i forhold til vanlig
    out += [f for f in anomalies(win) if f.level != "ok"]
    if not [f for f in out if f.level in ("warn", "error")]:
        out.insert(0, Finding("Ingenting ser galt ut akkurat nå", "ok",
                              f"Prosessor {load:.0f} %, minne {vm.percent:.0f} %" +
                              (f", CPU {m['cpu_t']:.0f} °C" if m["cpu_t"] else "") +
                              (f", GPU {m['gpu_t']:.0f} °C" if m["gpu_t"] else "") +
                              ". Hakker det i et spill, se «Siste hakk» under spilløkten.", key="ok"))
    order = {"error": 0, "warn": 1, "info": 2, "ok": 3}
    out.sort(key=lambda f: order.get(f.level, 9))
    return out


def _clean_now():
    import upkeep
    rep = upkeep.auto_clean(force=True)
    return "Ryddet: " + upkeep.report_text(rep) if rep else "Ingenting å rydde"


def text_summary(findings):
    bad = [f for f in findings if f.level in ("warn", "error")]
    if not bad:
        return "✅ Ingenting ser galt ut akkurat nå"
    return "⚠️ " + " · ".join(f.title for f in bad[:3])


# --------------------------------------------------------------------------
# 2 – Spillstart-sjekk
# --------------------------------------------------------------------------
def game_check(win, game):
    """Kalles når et spill starter. Returnerer funn (bare det som bør gjøres noe med)."""
    import psutil
    out = []
    try:
        prof = win.power.active_profile() if getattr(win, "power", None) else None
        if prof in ("power-saver", "powersave"):
            out.append(Finding("Strømsparing er på", "warn", "Spillet får ikke full fart.",
                               _power_fix(win, "performance", "Max Ytelse"), key="g:saver"))
    except Exception:  # noqa: BLE001
        pass
    vm = psutil.virtual_memory()
    if vm.percent >= 85:
        top = [t for t in _top("mem", 3) if t["name"] != game]
        out.append(Finding("Lite ledig minne", "warn", f"{vm.percent:.0f} % brukt" +
                           (f" – {top[0]['name']} bruker {_human(top[0]['mem'])}" if top else ""),
                           _kill_fix(top[0]["name"], top[0]["pids"]) if top else None, key="g:mem"))
    names = _running_names()
    busy = [t for p, t in UPDATE_PROCS.items() if t and p in names]
    if busy:
        out.append(Finding("Noe jobber i bakgrunnen", "info", busy[0] + " – kan gi hakk de første minuttene.",
                           key="g:bg"))
    try:
        import updates
        if updates.running():
            out.append(Finding("«Oppdater alt» kjører", "info", "Kan gi hakk til den er ferdig.", key="g:upd"))
    except Exception:  # noqa: BLE001
        pass
    for p in psutil.disk_partitions(all=False):
        try:
            u = psutil.disk_usage(p.mountpoint)
        except OSError:
            continue
        if u.total > 8 * 2 ** 30 and u.percent >= 97 and "loop" not in p.device:
            out.append(Finding(f"{p.mountpoint} er full", "warn", f"Bare {_human(u.free)} ledig – spillet kan "
                                                                   "hakke når det lagrer.", key="g:disk"))
            break
    m = _now(win)
    if (m["cpu_t"] or 0) >= 85 and m["cpu_l"] < 30:
        out.append(Finding("Prosessoren er varm før spillet har begynt", "warn",
                           f"{m['cpu_t']:.0f} °C på lav last – sjekk vifter og støv.", key="g:warm"))
    return out


def on_game_start(win, game):
    """Fra games_auto: sjekk i bakgrunnen og gi ett varsel hvis noe bør fikses."""
    def work():
        time.sleep(20)                                   # la spillet starte først
        try:
            fs = [f for f in game_check(win, game) if f.level in ("warn", "error")]
        except Exception:  # noqa: BLE001
            return
        if not fs:
            return
        bg = getattr(win, "bg", None)
        if bg:
            from gi.repository import GLib
            body = "; ".join(f"{f.title}: {f.detail}" for f in fs[:3])
            GLib.idle_add(lambda: (bg.notify("gamecheck", f"Spillsjekk – {game}", body, force=True,
                                             action="app.assistant"), False)[1])
    threading.Thread(target=work, daemon=True, name="spillsjekk").start()


# --------------------------------------------------------------------------
# 16 / 30 / 31 – lær det normale: unormalt-varsel, støv og kjølepasta
# --------------------------------------------------------------------------
def learn(win):
    """Kalles hvert minutt fra bakgrunnen: temperatur per lastnivå, per uke."""
    m = _now(win)
    d = _load()
    wk = d["weeks"].setdefault(_week(), {"cpu": {}, "gpu": {}})
    with _LOCK:
        for kind, t, l in (("cpu", m["cpu_t"], m["cpu_l"]), ("gpu", m["gpu_t"], m["gpu_l"])):
            if t is None:
                continue
            b = wk[kind].setdefault(_bucket(l), [0.0, 0])
            b[0] += t
            b[1] += 1
        for k in sorted(d["weeks"])[:-26]:              # behold et halvt år
            d["weeks"].pop(k, None)
    if time.time() - d.get("_saved", 0) > 900:
        d["_saved"] = time.time()
        _save()


def _avg(wk, kind, bucket):
    v = (wk.get(kind) or {}).get(bucket)
    return v[0] / v[1] if v and v[1] >= 10 else None


def baseline(kind, bucket, skip_weeks=2):
    """Snitt-temperatur ved dette lastnivået fra tidligere uker (ikke de siste)."""
    d = _load()
    weeks = sorted(d["weeks"])[:-skip_weeks] if len(d["weeks"]) > skip_weeks else []
    vals = [x for x in (_avg(d["weeks"][w], kind, bucket) for w in weeks) if x is not None]
    return sum(vals) / len(vals) if len(vals) >= 2 else None


def recent(kind, bucket, weeks=1):
    d = _load()
    ws = sorted(d["weeks"])[-weeks:]
    vals = [x for x in (_avg(d["weeks"][w], kind, bucket) for w in ws) if x is not None]
    return sum(vals) / len(vals) if vals else None


def anomalies(win=None):
    """Funn når PC-en går varmere enn den pleier ved samme last (støv, kjølepasta, vifte)."""
    out = []
    names = {"cpu": "Prosessoren", "gpu": "Skjermkortet"}
    for kind in ("cpu", "gpu"):
        worst = None
        for b in ("0", "10", "20", "50", "60", "70", "80", "90", "100"):
            base, now = baseline(kind, b), recent(kind, b)
            if base is None or now is None:
                continue
            diff = now - base
            if worst is None or diff > worst[0]:
                worst = (diff, b, base, now)
        if not worst or worst[0] < 5:
            continue
        diff, b, base, now = worst
        low = int(b) <= 20
        if kind == "cpu" and low and diff >= 8:
            title, detail = ("Prosessoren går varm selv i ro", f"{now:.0f} °C ved {b} % last – pleide å være "
                             f"{base:.0f} °C. Kan bety tørr kjølepasta eller at kjøleren sitter løst.")
        else:
            title, detail = (f"{names[kind]} er {diff:.0f} °C varmere enn vanlig",
                             f"{now:.0f} °C ved {b} % last – pleide å være {base:.0f} °C. Mest sannsynlig støv: "
                             "blås ut vifter og filtre med trykkluft (PC-en av).")
        out.append(Finding(title, "warn" if diff < 10 else "error", detail, key=f"anom:{kind}"))
    return out


# --------------------------------------------------------------------------
# 8 – Diskvakt
# --------------------------------------------------------------------------
def disk_watch():
    """Hva tar plass på diskene som er over 90 % – store spill du ikke har spilt på lenge, klipp og nedlastinger."""
    import psutil
    out = []
    full = []
    for p in psutil.disk_partitions(all=False):
        if "loop" in p.device or any(x in p.mountpoint for x in ("/boot", "/snap", "/run")):
            continue
        try:
            u = psutil.disk_usage(p.mountpoint)
        except OSError:
            continue
        if u.total > 8 * 2 ** 30 and u.percent >= 90:
            full.append((p.mountpoint, u))
    if not full:
        return out
    for mnt, u in full:
        out.append(Finding(f"{mnt} er {u.percent:.0f} % full", "warn" if u.percent < 97 else "error",
                           f"{_human(u.free)} ledig av {_human(u.total)}.", ("Rydd trygt nå", _clean_now),
                           key=f"disk:{mnt}"))
    # spill du ikke har spilt på 90 dager
    try:
        import games
        old = []
        for g in games.installed_games():
            last = g.get("last_played") or 0
            size = g.get("size") or 0
            if size > 5 * 2 ** 30 and (not last or time.time() - last > 90 * 86400):
                old.append((size, g.get("name", "?"), last))
        old.sort(reverse=True)
        if old:
            out.append(Finding("Store spill du ikke har spilt på 3 måneder", "info",
                               ", ".join(f"{n} ({_human(s)})" for s, n, _l in old[:5]) +
                               ". Avinstaller fra Steam/Heroic – de kan lastes ned igjen.", key="disk:games"))
    except Exception:  # noqa: BLE001
        pass
    # klipp og nedlastinger
    for label, path in (("Klipp", _clips_dir()), ("Nedlastinger", _downloads())):
        if path and os.path.isdir(path):
            size = _dir_size(path, 20000)
            if size > 5 * 2 ** 30:
                out.append(Finding(f"{label} tar {_human(size)}", "info", path, ("Åpne mappen", lambda p=path: _open(p)),
                                   key=f"disk:{label}"))
    return out


def _clips_dir():
    try:
        import clips
        return clips.clip_dir()
    except Exception:  # noqa: BLE001
        return None


def _downloads():
    for p in (os.path.join(HOME, "Nedlastinger"), os.path.join(HOME, "Downloads")):
        if os.path.isdir(p):
            return p
    return None


def _dir_size(path, limit):
    total, n = 0, 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
            n += 1
            if n > limit:
                return total
    return total


def _open(path):
    if IS_WIN:
        os.startfile(path)  # noqa: S606
    else:
        import subprocess
        subprocess.Popen(["xdg-open", path])
    return "Åpnet"


# --------------------------------------------------------------------------
# 32 – SSD-levetid i klartekst
# --------------------------------------------------------------------------
def ssd_life():
    out = []
    if IS_WIN:
        try:
            import winsupport
            ps = ("Get-PhysicalDisk | ForEach-Object { $r = $_ | Get-StorageReliabilityCounter; "
                  "$_.FriendlyName + '|' + $_.MediaType + '|' + $r.Wear + '|' + $r.PowerOnHours }")
            _c, txt = winsupport.run(["powershell", "-NoProfile", "-Command", ps], 60)
            for ln in txt.splitlines():
                p = ln.strip().split("|")
                if len(p) >= 4 and p[2].strip().isdigit():
                    out.append(_life_row(p[0], int(p[2]), int(p[3]) if p[3].strip().isdigit() else None))
        except Exception:  # noqa: BLE001
            pass
        return out
    try:
        import tools
        for d in tools.disk_health():
            rows = dict(d["rows"])
            used = rows.get("Slitasje", "")
            hrs = rows.get("I drift", "")
            if used:
                pct = int(used.split()[0])
                h = int(hrs.split()[0]) if hrs and hrs.split()[0].isdigit() else None
                out.append(_life_row(d["name"], pct, h))
    except Exception:  # noqa: BLE001
        pass
    return out


def _life_row(name, used_pct, hours):
    left = None
    if used_pct and used_pct > 0 and hours:
        rate = used_pct / hours                       # prosent per driftstime
        left = (100 - used_pct) / rate / (24 * 365) * 3   # ca. 8 t/døgn
    if used_pct >= 90:
        lvl, txt = "error", "Nær slutten av levetiden – ta sikkerhetskopi og bytt disken snart."
    elif used_pct >= 70:
        lvl, txt = "warn", "Har brukt det meste av levetiden. Følg med."
    else:
        lvl, txt = "ok", "God helse."
    yrs = (f" Holder ca. {left:.0f} år til med dagens bruk." if left and left < 15 else
           " Holder i mange år til med dagens bruk." if used_pct < 70 else "")
    return Finding(f"{name.strip()}: {used_pct} % av levetiden brukt", lvl, txt + yrs, key=f"ssd:{name.strip()}")


# --------------------------------------------------------------------------
# 6 – ukentlig helserapport
# --------------------------------------------------------------------------
def weekly_report(win):
    lines = []
    for f in why_slow(win) + disk_watch() + ssd_life():
        if f.level in ("warn", "error"):
            lines.append(f"• {f.title}")
    try:
        import games_auto
        week = [s for s in games_auto.load_sessions() if time.time() - (s.get("start") or 0) < 7 * 86400]
        mins = sum(s.get("minutes", 0) for s in week)
        drops = sum(len(s.get("drops") or []) for s in week)
        lines.insert(0, f"Spilt {mins // 60} t {mins % 60} min i {len(week)} økter" +
                     (f", {drops} FPS-dropp" if drops else ""))
    except Exception:  # noqa: BLE001
        pass
    for kind, name in (("cpu", "CPU"), ("gpu", "GPU")):
        b = recent(kind, "90") or recent(kind, "80") or recent(kind, "60")
        if b:
            lines.append(f"{name} under last: {b:.0f} °C")
    ok = not any(ln.startswith("•") for ln in lines)
    return ("✅ Alt i orden denne uka. " if ok else "⚠️ Bør sees på: ") + "  ".join(lines)


def weekly_tick(win):
    """Søndag etter kl. 19: én rapport (varsel + mobil)."""
    t = time.localtime()
    if t.tm_wday != 6 or t.tm_hour < 19:
        return
    d = _load()
    if d["sent"].get("weekly") == _week():
        return
    d["sent"]["weekly"] = _week()
    _save()
    try:
        txt = weekly_report(win)
    except Exception as e:  # noqa: BLE001
        txt = f"Kunne ikke lage rapporten: {e}"
    bg = getattr(win, "bg", None)
    if bg:
        from gi.repository import GLib
        GLib.idle_add(lambda: (bg.notify("weekly", "Ukens helserapport", txt, force=True, action="app.assistant"),
                               False)[1])


def anomaly_tick(win):
    """Én gang i døgnet: varsle om PC-en går varmere enn vanlig (støv/kjølepasta)."""
    d = _load()
    day = time.strftime("%Y-%m-%d")
    if d["sent"].get("anom_day") == day:
        return
    d["sent"]["anom_day"] = day
    fs = anomalies(win)
    if not fs:
        return
    f = fs[0]
    if d["sent"].get("anom_last") and time.time() - d["sent"]["anom_last"] < 7 * 86400:
        return                                            # høyst én gang i uka
    d["sent"]["anom_last"] = time.time()
    _save()
    bg = getattr(win, "bg", None)
    if bg:
        from gi.repository import GLib
        GLib.idle_add(lambda: (bg.notify("anomaly", f.title, f.detail, force=True, action="app.assistant"), False)[1])


# --------------------------------------------------------------------------
# 7 – foreslå «Eldre PC» når vinduet hakker mye
# --------------------------------------------------------------------------
def stall_tick(win):
    try:
        import perf
        import winperf
    except Exception:  # noqa: BLE001
        return
    if perf.lowend() or winperf.HAKK["n"] < 15:
        return
    d = _load()
    if d["sent"].get("lowend_hint"):
        return
    d["sent"]["lowend_hint"] = time.time()
    _save()
    bg = getattr(win, "bg", None)
    if bg:
        from gi.repository import GLib
        GLib.idle_add(lambda: (bg.notify(
            "lowend", "Vinduet hakker på denne PC-en",
            f"Kontrollsenter har hakket {winperf.HAKK['n']} ganger. Slå på «Eldre PC – lett grafikk» i "
            "Innstillinger → Generelt, så blir det jevnere.", force=True), False)[1])


def tick(win):
    """Fra bakgrunnen hvert minutt."""
    for fn in (learn, weekly_tick, anomaly_tick, stall_tick):
        try:
            fn(win)
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("assistent: %s", fn.__name__)
