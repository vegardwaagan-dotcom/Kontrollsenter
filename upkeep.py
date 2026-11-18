"""Ytelse og vedlikehold:

* Automatisk opprydding én gang i måneden – bare det som er helt trygt (miniatyrbilder, shader-cache for spill som
  ikke er installert, midlertidige filer på Windows). Aldri papirkurven, aldri noe som krever passord. Rapport som
  varsel og i Vedlikehold.
* «Hvorfor er PC-en treg?» – én knapp som ser på CPU, minne, disk, temperatur, strømmodus og hva som kjører, og
  forklarer hva som er galt og hva du kan gjøre.
"""
import json
import os
import shutil
import sys
import threading
import time

IS_WIN = sys.platform == "win32"
CFG = os.path.expanduser("~/.config/systemmonitor/vedlikehold.json")
SAFE_LINUX = ("thumbs", "shader_orphan")
SAFE_WIN = ("temp", "nvcache")


def cfg():
    try:
        with open(CFG) as f:
            return {"auto": True, **json.load(f)}
    except (OSError, ValueError):
        return {"auto": True}


def save_cfg(**kw):
    d = cfg()
    d.update(kw)
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    with open(CFG, "w") as f:
        json.dump(d, f, indent=1)


def _human(n):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.0f} {u}" if u in ("B", "KB") else f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} PB"


# --------------------------------------------------------------------------
# Månedlig opprydding
# --------------------------------------------------------------------------
def auto_clean(force=False):
    """Kjør den trygge oppryddingen hvis det er over 30 dager siden sist. Returnerer rapport eller None."""
    c = cfg()
    if not force and (not c.get("auto", True) or time.time() - c.get("last", 0) < 30 * 86400):
        return None
    if IS_WIN:
        import wintools as T
        safe = SAFE_WIN
    else:
        import tools as T
        safe = SAFE_LINUX
    items = [it for it in T.cleanup_items() if it[0] in safe and not it[5]]
    freed, errors = T.do_cleanup(items)
    rep = {"t": time.time(), "freed": freed, "what": [it[1] for it in items if it[4]], "errors": errors[:3]}
    hist = (c.get("history") or [])[-11:] + [rep]
    save_cfg(last=time.time(), history=hist)
    return rep


def report_text(rep):
    if not rep:
        return ""
    s = f"Frigjorde {_human(rep['freed'])}"
    if rep.get("what"):
        s += " (" + ", ".join(rep["what"]).lower() + ")"
    return s


def monthly_tick(notify):
    """Kalles fra bakgrunnen; sjekker én gang i timen og rydder i en egen tråd."""
    if time.time() - cfg().get("checked", 0) < 3600:
        return
    save_cfg(checked=time.time())

    def work():
        try:
            rep = auto_clean()
            if rep and rep["freed"] > 0:
                from gi.repository import GLib
                GLib.idle_add(lambda: notify("cleanup", "Månedlig opprydding er gjort",
                                             report_text(rep) + ". Papirkurven og filene dine er ikke rørt.") and False)
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("månedlig opprydding")
    threading.Thread(target=work, daemon=True).start()


# --------------------------------------------------------------------------
# «Hvorfor er PC-en treg?»
# --------------------------------------------------------------------------
def analyze(win=None):
    """Liste med funn: {"level": "bad"|"warn"|"ok", "title", "detail", "action": {...} eller None}."""
    import psutil
    out = []

    def add(level, title, detail, action=None):
        out.append({"level": level, "title": title, "detail": detail, "action": action})

    # CPU og hva som bruker den
    psutil.cpu_percent(None)
    procs = []
    for p in psutil.process_iter(["pid", "name", "memory_info", "username"]):
        try:
            p.cpu_percent(None)
            procs.append(p)
        except psutil.Error:
            continue
    time.sleep(1.0)
    load = psutil.cpu_percent(None)
    ncpu = psutil.cpu_count() or 1
    rows = []
    for p in procs:
        try:
            rows.append((p.info["name"], p.cpu_percent(None) / ncpu, p.info["memory_info"].rss if p.info["memory_info"] else 0,
                         p.info.get("username")))
        except psutil.Error:
            continue
    merged = {}
    for n, c, m, u in rows:
        x = merged.setdefault(n, [0, 0, u])
        x[0] += c
        x[1] += m
    top_cpu = sorted(merged.items(), key=lambda kv: -kv[1][0])[:3]
    top_mem = sorted(merged.items(), key=lambda kv: -kv[1][1])[:3]
    me = psutil.Process().username()
    if load >= 85:
        n, (c, _m, u) = top_cpu[0]
        add("bad", f"Prosessoren jobber for fullt ({load:.0f} %)",
            f"Mest: {n} ({c:.0f} %)" + (f", {top_cpu[1][0]} ({top_cpu[1][1][0]:.0f} %)" if len(top_cpu) > 1 else "")
            + ". Lukk det du ikke trenger.",
            {"a": "kill", "name": n, "label": f"Avslutt {n}"} if u == me else None)
    elif load >= 50:
        add("warn", f"Prosessoren er ganske opptatt ({load:.0f} %)",
            "Mest: " + ", ".join(f"{n} ({v[0]:.0f} %)" for n, v in top_cpu[:2]))
    else:
        add("ok", f"Prosessoren har god kapasitet ({load:.0f} %)", "")

    # minne
    vm, sw = psutil.virtual_memory(), psutil.swap_memory()
    if vm.percent >= 90 or (sw.total and sw.percent > 50 and vm.percent > 80):
        n, (_c, m, u) = top_mem[0]
        add("bad", f"Nesten fullt minne ({vm.percent:.0f} % brukt)",
            f"PC-en må flytte ting til disken (swap {sw.percent:.0f} %), og da går alt tregt. Mest: {n} "
            f"({_human(m)}). Nettlesere med mange faner bruker mye.",
            {"a": "kill", "name": n, "label": f"Avslutt {n}"} if u == me else None)
    elif vm.percent >= 75:
        add("warn", f"Mye minne i bruk ({vm.percent:.0f} %)",
            "Mest: " + ", ".join(f"{n} ({_human(v[1])})" for n, v in top_mem[:2]))
    else:
        add("ok", f"Nok minne ({vm.percent:.0f} % i bruk)", "")

    # disk: plass og hvor travelt den har det
    try:
        du = shutil.disk_usage(os.path.expanduser("~"))
        pct = 100 * (du.total - du.free) / du.total
        if pct >= 95:
            add("bad", f"Disken er nesten full ({pct:.0f} %)", "Med under 5 % ledig blir alt tregere. Vedlikehold → "
                "Rydd opp, eller «Hva tar plass?».")
        elif pct >= 88:
            add("warn", f"Lite ledig plass ({pct:.0f} % brukt)", "Rydd opp før det blir fullt.")
    except OSError:
        pass
    try:
        a = psutil.disk_io_counters()
        time.sleep(0.5)
        b = psutil.disk_io_counters()
        busy_ms = (getattr(b, "busy_time", 0) - getattr(a, "busy_time", 0))
        rate = (b.read_bytes + b.write_bytes - a.read_bytes - a.write_bytes) * 2
        if busy_ms >= 400:
            add("warn", "Disken jobber hardt", f"{_human(rate)}/s akkurat nå – en oppdatering, nedlasting eller "
                "sikkerhetskopi kan gjøre PC-en treg en stund.")
    except Exception:  # noqa: BLE001
        pass

    # temperatur og strømmodus
    if win is not None:
        ct = getattr(win, "_cpu_t", None)
        nv = win.nvidia.data if getattr(win, "nvidia", None) and win.nvidia.available else None
        gt = (nv or {}).get("temp")
        if ct is not None and ct >= 90:
            add("bad", f"Prosessoren er for varm ({ct:.0f} °C)", "Den bremser seg selv ned for å ikke bli ødelagt. "
                "Sjekk viftene, eller sett viftene på Kraftig.", {"a": "fans", "value": 70, "label": "Vifter kraftig"})
        if gt is not None and gt >= 85:
            add("bad", f"Skjermkortet er for varmt ({gt:.0f} °C)", "Det bremser seg selv ned. Sjekk luftstrømmen i kabinettet.")
        try:
            mode = win.power.active_profile()
            if mode == "power-saver":
                add("warn", "Strømsparing er på", "PC-en er bevisst bremset for å spare strøm.",
                    {"a": "power", "mode": "balanced", "label": "Bytt til Balansert"})
        except Exception:  # noqa: BLE001
            pass

    # oppdateringer og tunge bakgrunnsjobber
    names = {n.lower() for n in merged}
    for key, text in (("rpm-ostree", "Systemet oppdateres i bakgrunnen (rpm-ostree)"), ("dnf", "Systemet oppdateres (dnf)"),
                      ("packagekitd", "Programvare oppdateres i bakgrunnen"), ("tiwork", "Windows Update jobber"),
                      ("msmpeng.exe", "Windows Defender skanner"), ("baloo_file", "KDE indekserer filene dine"),
                      ("tracker-miner-f", "GNOME indekserer filene dine"), ("steamwebhelper", None)):
        if key in names and text and merged.get(next(n for n in merged if n.lower() == key), [0])[0] > 5:
            add("warn", text, "Det går over av seg selv – PC-en blir raskere når den er ferdig.")

    level = {"bad": 0, "warn": 1, "ok": 2}
    out.sort(key=lambda x: level[x["level"]])
    bad = [x for x in out if x["level"] != "ok"]
    summary = ("Fant ikke noe som gjør PC-en treg akkurat nå 👍" if not bad else
               f"{len(bad)} ting kan gjøre PC-en treg" + (" – start øverst" if len(bad) > 1 else ""))
    return {"summary": summary, "items": out, "t": time.time()}
