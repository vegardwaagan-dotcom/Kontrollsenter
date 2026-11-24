"""PC-en, runde 4: helsepoeng, strømbudsjett, diskprognose, BIOS-alder, stresstest, sammenligning med
de andre PC-ene og «Stille nå» i X timer.

Bygger på det Kontrollsenter allerede har: temperaturhistorikken, SMART-dataene (Diskhelse), strømloggen
(win.energy), krasjloggen, oppdateringene, ytelsestesten og PC-statusene på NAS-en.
"""
import hashlib
import json
import os
import sys
import threading
import time

IS_WIN = sys.platform == "win32"
DATA = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/share"),
                    "Kontrollsenter" if IS_WIN else "systemmonitor")
CFG = os.path.expanduser("~/.config/systemmonitor/pcplus.json")
DISKLOG = os.path.join(DATA, "diskslitasje.json")
DEF = {"budget_kr": 0, "budget_warned": "", "driver_url": "", "nvidia_url": "", "amd_url": ""}
GPU_URLS = {"nvidia_url": "https://www.nvidia.com/en-eu/drivers/",
            "amd_url": "https://www.amd.com/en/support/download/drivers.html"}


def gpu_url(key):
    """Driversiden for NVIDIA/AMD: adressen du har lagt inn, ellers standard."""
    return (cfg().get(key) or "").strip() or GPU_URLS[key]
# kjente driversider per hovedkort (resten: produsentens søk)
BOARD_URLS = {"ROG STRIX X870E-E GAMING WIFI": "https://rog.asus.com/motherboards/rog-strix/rog-strix-x870e-e-gaming-wifi/"
                                               "helpdesk_download/?model2name=rog%20strix%20x870e-e%20gaming%20wifi"}


def driver_url():
    """Driversiden for hovedkortet: adressen du har lagt inn, ellers produsentens søk (fra bios())."""
    u = (cfg().get("driver_url") or "").strip()
    if u:
        return u
    b = bios()
    return b["url"] if b else "https://www.asus.com/support/"


def _board_url(board):
    up = (board or "").upper()
    return next((u for k, u in BOARD_URLS.items() if k in up), None)


def cfg():
    try:
        return {**DEF, **json.load(open(CFG))}
    except (OSError, ValueError):
        return dict(DEF)


def set_(**kw):
    c = cfg()
    c.update(kw)
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    with open(CFG + ".tmp", "w") as f:
        json.dump(c, f)
    os.replace(CFG + ".tmp", CFG)
    return c


def _jload(p, d):
    try:
        return json.load(open(p))
    except (OSError, ValueError):
        return d


def _jsave(p, d):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p + ".tmp", "w") as f:
        json.dump(d, f)
    os.replace(p + ".tmp", p)


# ------------------------------------------------------------------ 26 – diskprognose
def disk_forecast(disks=None):
    """Forventet levetid igjen for SSD-ene, ut fra slitasjen (SMART «brukt %») og hvor fort den har økt."""
    if disks is None:
        import tools
        disks = tools.disk_health()
    lg = _jload(DISKLOG, {})
    now = time.time()
    out = []
    for d in disks:
        used = d.get("used_pct")
        hours = d.get("hours")
        if used is None:
            continue
        key = d.get("serial") or d["name"]
        hist = lg.setdefault(key, [])
        if not hist or now - hist[-1][0] > 86400:
            hist.append([now, used, hours])
            del hist[:-400]
        rate = None                                          # prosent per år
        if len(hist) >= 2 and hist[-1][1] > hist[0][1] and now - hist[0][0] > 30 * 86400:
            rate = (hist[-1][1] - hist[0][1]) / ((hist[-1][0] - hist[0][0]) / (365 * 86400))
        elif hours and used:                                 # første gang: ut fra driftstimer, ~10 t/dag
            rate = used / (hours / (10 * 365))
        years = None if not rate else max(0.0, (100 - used) / rate)
        txt = (f"{d['name']}: {used} % slitt" + (f" – ca. {years:.0f} år igjen med dagens bruk" if years and years < 50
                                                    else " – mange år igjen" if years else ""))
        out.append({"name": d["name"], "used": used, "years": round(years, 1) if years else None, "text": txt})
    _jsave(DISKLOG, lg)
    return out


# ------------------------------------------------------------------ 25 – BIOS-alder
def bios():
    """BIOS-versjon, dato og hvor gammel den er – med lenke til produsentens side."""
    if IS_WIN:
        try:
            import subprocess
            out = subprocess.run(["powershell", "-NoProfile", "-Command",
                                  "Get-CimInstance Win32_BIOS | Select SMBIOSBIOSVersion,ReleaseDate | ConvertTo-Json;"
                                  "Get-CimInstance Win32_BaseBoard | Select Manufacturer,Product | ConvertTo-Json"],
                                 capture_output=True, text=True, timeout=20, creationflags=0x08000000).stdout
            parts = [json.loads(x) for x in out.replace("}\n{", "}\x00{").split("\x00") if x.strip()]
            ver, rel = parts[0].get("SMBIOSBIOSVersion"), str(parts[0].get("ReleaseDate") or "")
            vendor, board = parts[1].get("Manufacturer", ""), parts[1].get("Product", "")
            import re
            m = re.search(r"(\d{4})(\d{2})(\d{2})", rel) or re.search(r"Date\((\d+)\)", rel)
            date = time.strftime("%Y-%m-%d", time.gmtime(int(m.group(1)) / 1000)) if m and m.re.pattern.startswith(
                "Date") else (f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None)
        except Exception:  # noqa: BLE001
            return None
    else:
        def rd(n):
            try:
                return open(f"/sys/class/dmi/id/{n}").read().strip()
            except OSError:
                return ""
        ver, vendor, board = rd("bios_version"), rd("board_vendor"), rd("board_name")
        try:
            mm, dd, yy = rd("bios_date").split("/")
            date = f"{yy}-{mm}-{dd}"
        except ValueError:
            date = None
    age = None
    if date:
        try:
            age = round((time.time() - time.mktime(time.strptime(date, "%Y-%m-%d"))) / (30.4 * 86400))
        except ValueError:
            pass
    from urllib.parse import quote
    v = (vendor or "").lower()
    url = ("https://www.asus.com/support/search-results/?keyword=" + quote(board) if "asus" in v else
           "https://www.msi.com/search/" + quote(board) if "micro-star" in v or "msi" in v else
           "https://www.gigabyte.com/Search?kw=" + quote(board) if "gigabyte" in v else
           "https://www.asrock.com/support/index.asp?cat=BIOS" if "asrock" in v else
           "https://duckduckgo.com/?q=" + quote(f"{vendor} {board} BIOS"))
    txt = f"BIOS {ver} fra {date or '?'}" + (f" ({age} måneder gammel)" if age is not None else "")
    if age is not None and age >= 12:
        txt += " – det finnes sannsynligvis en nyere. Sjekk produsentens side (oppdater bare hvis noe er galt, " \
               "eller nyere CPU/minne krever det)."
    url = (cfg().get("driver_url") or "").strip() or _board_url(board) or url    # din adresse / kjent side
    return {"version": ver, "date": date, "age_months": age, "board": f"{vendor} {board}".strip(), "url": url,
            "text": txt}


# ------------------------------------------------------------------ 9 – strømbudsjett
def budget(win=None):
    import remote_extra
    e = remote_extra.energy(win or _win())
    b = cfg()["budget_kr"]
    month, est_kwh = e["month_kr"], e.get("month_estimate_kwh")
    est = round(est_kwh * e["price"], 0) if est_kwh else None
    if est is None:
        day = int(time.strftime("%d")) or 1
        import calendar
        est = round(month / day * calendar.monthrange(int(time.strftime("%Y")), int(time.strftime("%m")))[1])
    pct = round(month / b * 100) if b else None
    return {"budget": b, "month_kr": round(month), "estimate_kr": est, "pct": pct, "price": e["price"],
            "text": (f"{round(month)} kr brukt denne måneden, ca. {est:.0f} kr ved månedsslutt" +
                     (f" – budsjett {b} kr ({pct} %)" if b else ""))}


def budget_tick(notify):
    c = cfg()
    if not c["budget_kr"]:
        return
    try:
        r = budget()
    except Exception:  # noqa: BLE001
        return
    key = time.strftime("%Y-%m")
    lvl = "100" if r["month_kr"] >= r["budget"] else "80" if r["month_kr"] >= r["budget"] * 0.8 else \
        "est" if r["estimate_kr"] and r["estimate_kr"] > r["budget"] * 1.1 else ""
    mark = f"{key}:{lvl}"
    if lvl and c["budget_warned"] != mark:
        set_(budget_warned=mark)
        msg = {"100": f"Strømbudsjettet på {r['budget']} kr er brukt opp ({r['month_kr']} kr).",
               "80": f"80 % av strømbudsjettet er brukt ({r['month_kr']} av {r['budget']} kr).",
               "est": f"Med dagens bruk blir det ca. {r['estimate_kr']:.0f} kr denne måneden – over budsjettet "
                      f"på {r['budget']} kr."}[lvl]
        notify("budget", "Strømbudsjett", msg + " Tips: Stille om natten og strømsparing gir mest.")


def _win():
    try:
        import remote
        return remote.win
    except Exception:  # noqa: BLE001
        return None


# ------------------------------------------------------------------ 7 – helsepoeng
def health(win=None, disks=None):
    """0–100 og hva som trekker ned – med hvor du fikser det."""
    pts, items = 100, []

    def minus(n, level, title, page=None, detail=""):
        nonlocal pts
        pts -= n
        items.append({"level": level, "title": title, "detail": detail, "page": page, "minus": n})
    try:
        import history
        st = history.stats(86400) or (None, None)
        mc, mg = st[0] or 0, st[1] or 0
        if mc >= 95 or mg >= 90:
            minus(20, "bad", f"Svært varm siste døgn (CPU {mc:.0f}°, GPU {mg:.0f}°)", "oversikt")
        elif mc >= 85 or mg >= 83:
            minus(8, "warn", f"Varm siste døgn (CPU {mc:.0f}°, GPU {mg:.0f}°)", "oversikt")
    except Exception:  # noqa: BLE001
        pass
    try:
        if disks is None:
            import tools
            disks = tools.disk_health()
        for d in disks:
            if d.get("ok") is False:
                minus(30, "bad", f"Disken {d['name']} melder feil (SMART)", "verktoy")
            elif (d.get("used_pct") or 0) >= 80:
                minus(10, "warn", f"SSD-en {d['name']} er {d['used_pct']} % slitt", "verktoy")
    except Exception:  # noqa: BLE001
        pass
    try:
        import shutil
        for p in (("C:\\",) if IS_WIN else (os.path.expanduser("~"),)):     # «/» er skrivebeskyttet på Bazzite
            u = shutil.disk_usage(p)
            free = u.free / u.total * 100
            if free < 5:
                minus(15, "bad", f"Nesten full disk ({free:.0f} % ledig på {p})", "verktoy")
                break
            if free < 12:
                minus(6, "warn", f"Lite plass ({free:.0f} % ledig på {p})", "verktoy")
                break
    except OSError:
        pass
    try:
        import crashlog
        n = len([x for x in crashlog.history() if time.time() - (x.get("t") or 0) < 30 * 86400])
        if n >= 3:
            minus(15, "bad", f"{n} krasj/frys siste måned", "verktoy")
        elif n:
            minus(5, "warn", f"{n} krasj/frys siste måned", "verktoy")
    except Exception:  # noqa: BLE001
        pass
    try:
        import updates
        s = updates.summary_json()
        n = s.get("total") or 0
        if n >= 30:
            minus(8, "warn", f"{n} oppdateringer venter", "verktoy")
        elif n:
            minus(3, "warn", f"{n} oppdateringer venter", "verktoy")
    except Exception:  # noqa: BLE001
        pass
    try:                                                  # varmere enn vanlig ved samme last (støv, kjølepasta)
        import assistant
        for f in assistant.anomalies():
            minus(10, "warn", f.title, "verktoy", f.detail)
    except Exception:  # noqa: BLE001
        pass
    try:
        import pctools
        if pctools.backup_due():
            minus(5, "warn", "Sikkerhetskopien er gammel", "verktoy")
    except Exception:  # noqa: BLE001
        pass
    b = bios()
    if b and (b.get("age_months") or 0) >= 30:
        minus(2, "info", f"BIOS-en er {b['age_months']} måneder gammel", None, b["text"])
    pts = max(0, pts)
    word = "Utmerket" if pts >= 90 else "Bra" if pts >= 75 else "Ok" if pts >= 55 else "Trenger stell"
    return {"score": pts, "word": word, "items": items}


# ------------------------------------------------------------------ 46 – stresstest
STRESS = {"running": False, "log": [], "result": None, "stop": False}


def stress(minutes=5, progress=None):
    """Prosessor (alle kjernene) og minne på full guffe i N minutter. Regnestykkene sjekkes – blir svaret feil, er
    PC-en ustabil (typisk for hard overklokking/undervolting eller for varmt). Temperaturen logges hvert sekund."""
    import sensors
    if STRESS["running"]:
        raise RuntimeError("stresstesten kjører allerede")
    n = os.cpu_count() or 2
    STRESS.update(running=True, log=[], result=None, stop=False)
    errors = [0]
    ref = hashlib.sha256(b"ks" * 4096).hexdigest()
    end = time.time() + minutes * 60

    def worker():
        blk = b"ks" * 4096
        while time.time() < end and not STRESS["stop"]:
            for _ in range(200):
                if hashlib.sha256(blk).hexdigest() != ref:
                    errors[0] += 1

    def mem():
        size = 512 * 1024 * 1024
        pat = bytes(range(256)) * (size // 256)
        buf = bytearray(pat)
        while time.time() < end and not STRESS["stop"]:
            if hashlib.md5(buf).digest() != hashlib.md5(pat).digest():  # noqa: S324 – bare sjekksum
                errors[0] += 1
            time.sleep(0.5)
        del buf
    ts = [threading.Thread(target=worker, daemon=True) for _ in range(n)] + [threading.Thread(target=mem, daemon=True)]
    for t in ts:
        t.start()
    t0 = time.time()
    try:
        while time.time() < end and not STRESS["stop"]:
            try:
                ct = sensors.cpu_temp(sensors.hwmon_temps())
                fr = sensors.cpu_freqs_ghz() or []
                mhz = round(sum(fr) / len(fr) * 1000) if fr else None
            except Exception:  # noqa: BLE001
                ct = mhz = None
            STRESS["log"].append([round(time.time() - t0), ct, mhz])
            if progress:
                progress(time.time() - t0, minutes * 60, ct)
            time.sleep(1)
    finally:
        STRESS["stop"] = True
        for t in ts:
            t.join(2)
        STRESS["running"] = False
    temps = [x[1] for x in STRESS["log"] if x[1]]
    clocks = [x[2] for x in STRESS["log"] if x[2]]
    mx = max(temps) if temps else None
    throttle = bool(clocks) and len(clocks) > 20 and (min(clocks[len(clocks) // 2:]) < max(clocks[:10]) * 0.8)
    verdict = ("❌ Ustabil: regnefeil under belastning – skru ned overklokking/undervolting" if errors[0] else
               "⚠ Blir for varm – sjekk kjølepasta, vifter og støv" if mx and mx >= 95 else
               "⚠ Klokken faller under belastning (struping)" if throttle else "✓ Stabil og kjølig nok")
    res = {"minutes": round((time.time() - t0) / 60, 1), "errors": errors[0], "max_temp": mx,
           "avg_temp": round(sum(temps) / len(temps), 1) if temps else None, "throttle": throttle,
           "verdict": verdict, "log": STRESS["log"][-600:]}
    STRESS["result"] = res
    return res


# ------------------------------------------------------------------ 47 – sammenlign med de andre PC-ene
def compare_pcs():
    """Ytelsestesten her mot de andre PC-ene i huset (fra statusene på NAS-en)."""
    import pctools
    mine = (pctools.cfg().get("bench") or [None])[-1]
    others = []
    try:
        import homepcs
        import savegames
        me = savegames.pc_name()
        for p in homepcs.fetch() or []:
            b = p.get("bench")
            if b and p.get("name") != me:
                others.append({"name": p.get("name"), "cpu": p.get("cpu") or "", **b})
    except Exception:  # noqa: BLE001
        pass
    return {"mine": mine, "others": others}


def bench_for_status():
    """Siste ytelsestest – legges i PC-statusen på NAS-en så de andre kan sammenligne."""
    try:
        import pctools
        b = (pctools.cfg().get("bench") or [None])[-1]
        return {k: b[k] for k in ("cpu1", "cpuN", "mem_gbs", "disk_w", "t") if k in b} if b else None
    except Exception:  # noqa: BLE001
        return None


# ------------------------------------------------------------------ 27 – stille nå
def quiet_for(hours):
    """Stille vifter og lavere effekt i X timer (samme som «Stille om natten»). 0 = av."""
    import automation
    c = automation.load_night()
    c["quiet_until"] = time.time() + float(hours) * 3600 if hours else 0
    automation.save_night(c)
    return (f"Stille til kl. {time.strftime('%H:%M', time.localtime(c['quiet_until']))}" if hours else
            "Stille-modus er av")


def quiet_left():
    import automation
    u = automation.load_night().get("quiet_until") or 0
    return max(0, round((u - time.time()) / 60))


def tick(notify):
    """Kalles hvert 10. minutt fra bakgrunnen (støvvarselet ligger i PC-assistenten)."""
    budget_tick(notify)
    try:
        LAST["health"] = health()
    except Exception:  # noqa: BLE001
        pass


LAST = {"health": None}                                   # siste helsepoeng (vises på Oversikt)
