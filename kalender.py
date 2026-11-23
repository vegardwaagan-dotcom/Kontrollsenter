"""Kalenderen: egne hendelser (delt med huset på NAS-en), og alt annet som hører hjemme i en kalender –
bursdager og ukeplanen fra Familie, røde dager og flaggdager, skoleferier, månefaser, sol opp/ned, ferieplanlegger,
arbeidsdager, varsler og søk. Samme for Linux, Windows og mobilappen (app_api → /api/x/kal…).

Hendelse: {id, title, date "YYYY-MM-DD", time "HH:MM" eller "", end "YYYY-MM-DD" (flere dager), color,
           repeat: "" | "weekly" | "monthly" | "yearly" | "days:N" | "months:N", remind: minutter før (-1 = nei),
           kind: event|trash|dinner|routine|warranty|sub|stream|gamenight|scene, scene, who, note, by, done}
"""
import datetime as dt
import json
import math
import os
import shutil
import tempfile
import threading
import time

import helligdager as H

LOCAL = os.path.expanduser("~/.cache/systemmonitor/kalender.json")
CFG = os.path.expanduser("~/.config/systemmonitor/kalender-valg.json")
_LOCK = threading.Lock()
_CACHE = {"t": 0, "d": None}
COLORS = ["#5b8cff", "#2ecc71", "#ff9f43", "#ff5b8a", "#a970ff", "#1dd1a1", "#feca57", "#ff4d4d"]
KINDS = {"event": ("📌", "Hendelse"), "trash": ("🗑️", "Søppel"), "dinner": ("🍽️", "Middag"),
         "routine": ("🔁", "Rutine"), "warranty": ("🧾", "Garanti"), "sub": ("💳", "Abonnement"),
         "stream": ("🎥", "Strømming"), "gamenight": ("🎮", "Spillkveld"), "scene": ("✨", "Scene"),
         "todo": ("✅", "Gjøremål"), "vacation": ("🏖️", "Ferie")}
DEF_CFG = {"vinter_uke": 8, "host_uke": 40, "sommer": ["06-20", "08-17"], "jul": ["12-21", "01-02"],
           "show": {"flagg": True, "ferie": True, "mane": True, "sol": True, "familie": True, "ukeplan": True,
                    "spill": True, "pc": True, "ics": True}, "countdown": True}


def cfg():
    try:
        with open(CFG) as f:
            c = json.load(f)
    except (OSError, ValueError):
        c = {}
    out = {**DEF_CFG, **c}
    out["show"] = {**DEF_CFG["show"], **(c.get("show") or {})}
    return out


def set_cfg(**kw):
    c = cfg()
    c.update(kw)
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    with open(CFG, "w") as f:
        json.dump(c, f, ensure_ascii=False)
    return c


# --------------------------------------------------------------------------
# Lagring: Kontrollsenter/Familie/kalender.json på NAS-en (alle PC-ene og mobilene ser det samme)
# --------------------------------------------------------------------------
def load(max_age=300):
    if _CACHE["d"] is not None and time.time() - _CACHE["t"] < max_age:
        return _CACHE["d"]
    d = None
    try:
        import lanupdate as L
        if L.on_lan():
            tmp = tempfile.mkdtemp()
            try:
                L._smb(f'cd "Familie"; get "kalender.json" "{tmp}/k.json"', 30)
                with open(f"{tmp}/k.json", encoding="utf-8") as f:
                    d = json.load(f)
            except Exception:  # noqa: BLE001
                d = None
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
    except Exception:  # noqa: BLE001
        pass
    try:
        with open(LOCAL, encoding="utf-8") as f:
            local = json.load(f)
    except (OSError, ValueError):
        local = None
    if d is None or (local and local.get("t", 0) > d.get("t", 0)):   # nyeste vinner (NAS kan henge etter)
        d = local or {"events": []}
    else:
        _write_local(d)
    d.setdefault("events", [])
    _CACHE.update(t=time.time(), d=d)
    return d


def _write_local(d):
    os.makedirs(os.path.dirname(LOCAL), exist_ok=True)
    with open(LOCAL + ".tmp", "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(LOCAL + ".tmp", LOCAL)


def _save(d):
    d["t"] = time.time()
    _write_local(d)
    _CACHE.update(t=time.time(), d=d)

    def push():
        try:
            import lanupdate as L
            if not L.on_lan():
                return
            tmp = tempfile.mkdtemp()
            try:
                p = os.path.join(tmp, "kalender.json")
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(d, f, ensure_ascii=False, indent=1)
                _h, _s, folder = L._split()
                L.smb_mkdir(f"{folder}/Familie")
                L._smb(f'cd "Familie"; put "{p}" "kalender.json"', 30)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        except Exception:  # noqa: BLE001
            pass
    threading.Thread(target=push, daemon=True).start()


def add(ev):
    """Legg til (eller endre, hvis id finnes). Returnerer hendelsen."""
    title = str(ev.get("title") or "").strip()[:120]
    if not title:
        raise ValueError("skriv hva det gjelder")
    tm = str(ev.get("time") or "").strip().replace(".", ":").replace(" ", "")
    if tm:                                                  # «14», «1400», «14.00» og «14:00» virker
        import re
        m = re.match(r"^(\d{1,2}):?(\d{2})?$", tm)
        if not m or int(m.group(1)) > 23 or int(m.group(2) or 0) > 59:
            raise ValueError("skriv klokkeslett som 14:00")
        tm = f"{int(m.group(1)):02d}:{int(m.group(2) or 0):02d}"
    try:
        dt.date.fromisoformat(str(ev.get("date")))
    except ValueError:                                      # «24.11.2026» / «24.11»
        import re
        m = re.match(r"^(\d{1,2})\.(\d{1,2})\.?(\d{4})?$", str(ev.get("date") or "").strip())
        if not m:
            raise ValueError("ugyldig dato") from None
        ev = {**ev, "date": dt.date(int(m.group(3) or dt.date.today().year), int(m.group(2)),
                                    int(m.group(1))).isoformat()}
    import savegames
    e = {"id": ev.get("id") or f"e{int(time.time() * 1000)}{os.urandom(2).hex()}", "title": title, "date": str(ev["date"]), "time": tm,
         "end": str(ev.get("end") or ""), "color": str(ev.get("color") or COLORS[0])[:9],
         "repeat": str(ev.get("repeat") or ""), "remind": int(ev.get("remind", 30 if tm else -1)),
         "kind": ev.get("kind") if ev.get("kind") in KINDS else "event", "scene": str(ev.get("scene") or ""),
         "who": str(ev.get("who") or "*")[:40], "note": str(ev.get("note") or "")[:1000],
         "by": ev.get("by") or savegames.pc_name(), "done": list(ev.get("done") or [])}
    with _LOCK:
        d = load(0)
        d["events"] = [x for x in d["events"] if x.get("id") != e["id"]] + [e]
        _save(d)
    return e


def remove(eid):
    with _LOCK:
        d = load(0)
        n = len(d["events"])
        d["events"] = [x for x in d["events"] if x.get("id") != eid]
        _save(d)
    return n != len(d["events"])


def mark_done(eid, day, on=True):
    """Gjøremål / rutine krysset av for én dag."""
    with _LOCK:
        d = load(0)
        for e in d["events"]:
            if e.get("id") == eid:
                s = set(e.get("done") or [])
                (s.add if on else s.discard)(str(day))
                e["done"] = sorted(s)[-200:]
        _save(d)


# --------------------------------------------------------------------------
# Gjentakelser
# --------------------------------------------------------------------------
def _occurs(e, day):
    try:
        start = dt.date.fromisoformat(e["date"])
    except (KeyError, ValueError):
        return False
    if day < start:
        return False
    end = e.get("end")
    if end and not e.get("repeat"):
        try:
            return start <= day <= dt.date.fromisoformat(end)
        except ValueError:
            return day == start
    rep = e.get("repeat") or ""
    if not rep:
        return day == start
    if rep == "weekly":
        return (day - start).days % 7 == 0
    if rep == "yearly":
        return (day.month, day.day) == (start.month, start.day) or (
            start.month == 2 and start.day == 29 and day.month == 2 and day.day == 28 and not _leap(day.year))
    if rep in ("monthly",) or rep.startswith("months:"):
        n = 1 if rep == "monthly" else max(1, int(rep.split(":")[1]))
        months = (day.year - start.year) * 12 + day.month - start.month
        return months % n == 0 and day.day == min(start.day, _mdays(day.year, day.month))
    if rep.startswith("days:"):
        n = max(1, int(rep.split(":")[1]))
        return (day - start).days % n == 0
    return False


def _leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _mdays(y, m):
    import calendar
    return calendar.monthrange(y, m)[1]


# --------------------------------------------------------------------------
# Flaggdager, skoleferier, månefaser, sol
# --------------------------------------------------------------------------
def flag_days(year):
    e = H.easter(year)
    d = {dt.date(year, 1, 1): "Nyttårsdag", dt.date(year, 1, 21): "Prinsesse Ingrid Alexandras fødselsdag",
         dt.date(year, 2, 6): "Samefolkets dag", dt.date(year, 2, 21): "Kong Harald V's fødselsdag",
         e: "1. påskedag", dt.date(year, 5, 1): "Offentlig høytidsdag", dt.date(year, 5, 8): "Frigjøringsdagen 1945",
         dt.date(year, 5, 17): "Grunnlovsdagen", e + dt.timedelta(days=49): "1. pinsedag",
         dt.date(year, 6, 7): "Unionsoppløsningen 1905", dt.date(year, 7, 4): "Dronning Sonjas fødselsdag",
         dt.date(year, 7, 20): "Kronprins Haakons fødselsdag", dt.date(year, 7, 29): "Olsokdagen",
         dt.date(year, 8, 19): "Kronprinsesse Mette-Marits fødselsdag", dt.date(year, 12, 25): "1. juledag"}
    return d


def _week_monday(year, week):
    return dt.date.fromisocalendar(year, week, 1)


def school_holidays(year):
    """[(fra, til, navn)] – omtrentlige uker (vinter- og høstferie kan endres under ⚙️ – de varierer fra kommune
    til kommune)."""
    c = cfg()
    e = H.easter(year)
    out = []
    try:
        m = _week_monday(year, int(c["vinter_uke"]))
        out.append((m, m + dt.timedelta(days=6), "Vinterferie"))
    except ValueError:
        pass
    out.append((e - dt.timedelta(days=6), e + dt.timedelta(days=1), "Påskeferie"))
    try:
        a = dt.date.fromisoformat(f"{year}-{c['sommer'][0]}")
        b = dt.date.fromisoformat(f"{year}-{c['sommer'][1]}")
        out.append((a, b, "Sommerferie (ca.)"))
    except ValueError:
        pass
    try:
        m = _week_monday(year, int(c["host_uke"]))
        out.append((m, m + dt.timedelta(days=6), "Høstferie"))
    except ValueError:
        pass
    try:
        a = dt.date.fromisoformat(f"{year}-{c['jul'][0]}")
        b = dt.date.fromisoformat(f"{year + 1}-{c['jul'][1]}")
        out.append((a, b, "Juleferie (ca.)"))
        a0 = dt.date.fromisoformat(f"{year - 1}-{c['jul'][0]}")
        b0 = dt.date.fromisoformat(f"{year}-{c['jul'][1]}")
        out.append((a0, b0, "Juleferie (ca.)"))
    except ValueError:
        pass
    return out


def moon(day):
    """(fase 0–1, ikon, navn eller "") – 0 = nymåne, 0.5 = fullmåne."""
    ref = dt.datetime(2000, 1, 6, 18, 14)
    days = (dt.datetime(day.year, day.month, day.day, 12) - ref).total_seconds() / 86400
    ph = (days % 29.530588853) / 29.530588853
    icons = "🌑🌒🌓🌔🌕🌖🌗🌘"
    ic = icons[int((ph * 8 + 0.5)) % 8]
    name = ""
    for target, nm in ((0, "Nymåne"), (0.5, "Fullmåne")):
        diff = abs(((ph - target + 0.5) % 1) - 0.5) * 29.53
        if diff < 0.5:
            name = nm
    return ph, ic, name


def sun(day, lat=None, lon=None):
    """(soloppgang, solnedgang) som «HH:MM» lokal tid – eller None (midnattssol/mørketid eller ukjent sted)."""
    if lat is None:
        try:
            import infotiles
            c = infotiles.cfg()
            lat, lon = c.get("lat"), c.get("lon")
        except Exception:  # noqa: BLE001
            lat = None
    if lat is None or lon is None:
        lat, lon = 59.91, 10.75                              # Oslo som standard
    n = day.timetuple().tm_yday
    g = 2 * math.pi / 365 * (n - 1)
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g) +
            0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    eqt = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g) - 0.014615 * math.cos(2 * g) -
                    0.040849 * math.sin(2 * g))
    la = math.radians(float(lat))
    cos_h = (math.cos(math.radians(90.833)) / (math.cos(la) * math.cos(decl))) - math.tan(la) * math.tan(decl)
    if cos_h > 1 or cos_h < -1:
        return None
    ha = math.degrees(math.acos(cos_h))
    noon = 720 - 4 * float(lon) - eqt
    off = dt.datetime(day.year, day.month, day.day, 12).astimezone().utcoffset().total_seconds() / 60

    def fmt(minutes):
        m = int(round(minutes + off)) % 1440
        return f"{m // 60:02d}:{m % 60:02d}"
    return fmt(noon - 4 * ha), fmt(noon + 4 * ha)


# --------------------------------------------------------------------------
# Ferieplanlegger og arbeidsdager
# --------------------------------------------------------------------------
def _off(day):
    return day.weekday() >= 5 or day in H.red_days(day.year)


def workdays(year, month=None):
    d = dt.date(year, month or 1, 1)
    end = dt.date(year + (1 if not month or month == 12 else 0), (month % 12 + 1) if month else 1, 1)
    n = 0
    while d < end:
        n += not _off(d)
        d += dt.timedelta(days=1)
    return n


def vacation_tips(year, max_take=4):
    """Beste måter å få lange ferier med få feriedager rundt de røde dagene:
    [(høytid, feriedager du tar, fra, til, sammenhengende fridager)] – sortert etter dato."""
    start = dt.date(year, 1, 1)
    n = 366 if _leap(year) else 365
    days = [start + dt.timedelta(days=i) for i in range(-3, n + 12)]
    off = [_off(d) for d in days]
    reds = {**H.red_days(year), **H.red_days(year + 1)}
    cands = []
    for i in range(1, len(days) - 1):
        if off[i - 1] and not (i == 1):                   # start rett etter en arbeidsdag (maksimal blokk)
            continue
        took = 0
        for j in range(i, min(i + 21, len(days) - 1)):
            took += not off[j]
            if took > max_take:
                break
            if off[j + 1] or not off[j] and False:
                continue
            length = j - i + 1
            if took and length >= 4 and any(days[k] in reds for k in range(i, j + 1)) and \
                    days[i].year == year:
                cands.append((took, days[i], days[j], length))
    # per høytid (første røde dag i blokka): beste lengde for hvert antall feriedager
    groups = {}
    for took, a_, b_, length in cands:
        red = next((d for d in sorted(reds) if a_ <= d <= b_), None)
        if red is None:
            continue
        g = groups.setdefault(reds[red] if red.month != 12 or red.day < 25 else "Jul", {})
        if took not in g or g[took][3] < length:
            g[took] = (took, a_, b_, length)
    res = []
    for name, g in groups.items():                       # mest lønnsomt + lengst (maks 4 feriedager)
        opts = list(g.values())
        eff = max(opts, key=lambda t: (t[3] / t[0], t[3]))
        lng = max(opts, key=lambda t: (t[3], -t[0]))
        res.append((name, *eff))
        if lng != eff:
            res.append((name, *lng))
    return sorted(res, key=lambda t: (t[2], t[1]))


# --------------------------------------------------------------------------
# Alt på en dag (alle kildene)
# --------------------------------------------------------------------------
def items(start, end=None, extra=True):
    """{dato: [ {title, time, color, kind, icon, src, id?, red?} ]} for datoene fra start til end (med)."""
    end = end or start
    c = cfg()
    sh = c["show"]
    out = {}

    def put(day, **it):
        out.setdefault(day, []).append(it)
    days = [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]
    evs = load()["events"]
    for day in days:
        for e in evs:
            if _occurs(e, day):
                icon = KINDS.get(e.get("kind"), ("📌", ""))[0]
                put(day, title=e["title"], time=e.get("time", ""), color=e.get("color"), kind=e.get("kind"),
                    icon=icon, src="egen", id=e["id"], done=str(day) in (e.get("done") or []), note=e.get("note"),
                    who=e.get("who"))
        rd = H.red_days(day.year).get(day)
        if rd:
            put(day, title=rd, time="", color="#ff4d4d", kind="red", icon="🔴", src="rød", red=True)
        sp = H.special_days(day.year).get(day)
        if sp:
            put(day, title=sp, time="", color="#ff9f43", kind="special", icon="⭐", src="merkedag")
        if sh["flagg"] and day in flag_days(day.year) and not rd:
            put(day, title="🇳🇴 Flaggdag: " + flag_days(day.year)[day], time="", color="#ba0c2f", kind="flag",
                icon="🇳🇴", src="flagg")
        if sh["mane"]:
            _ph, ic, nm = moon(day)
            if nm:
                put(day, title=nm, time="", color="#9aa4b5", kind="moon", icon=ic, src="måne")
    if sh["ferie"]:
        for y in {d.year for d in days}:
            for a, b, nm in school_holidays(y):
                for day in days:
                    if a <= day <= b and not any(x.get("kind") == "school" and x["title"] == nm
                                                  for x in out.get(day, [])):
                        put(day, title=nm, time="", color="#1dd1a1", kind="school", icon="🎒", src="ferie")
    if sh["familie"]:
        try:
            import familyfun
            for b in familyfun.cfg().get("birthdays") or []:
                try:
                    bd = dt.date.fromisoformat(str(b.get("date"))[:10])
                except ValueError:
                    continue
                for day in days:
                    if (day.month, day.day) == (bd.month, bd.day):
                        age = day.year - bd.year
                        put(day, title=f"🎂 {b.get('name')}" + (f" fyller {age}" if 0 < age < 130 else ""),
                            time="", color="#ff5b8a", kind="birthday", icon="🎂", src="familie")
        except Exception:  # noqa: BLE001
            pass
    if sh["ukeplan"]:
        try:
            import familyplus
            for it in familyplus.load_plan().get("items", []):
                for day in days:
                    if day.weekday() == int(it.get("day", -1)):
                        put(day, title=it.get("text", ""), time=it.get("at", ""), color="#a970ff", kind="plan",
                            icon="🗓️", src="ukeplan", who=it.get("who"))
        except Exception:  # noqa: BLE001
            pass
    if extra:
        try:
            import kalender_extra
            kalender_extra.add_items(days, put, sh)
        except Exception:  # noqa: BLE001
            pass
    for k in out:
        out[k].sort(key=lambda x: (x.get("time") or "99", 0 if x.get("red") else 1))
    return out


def day_info(day):
    """Tekstlinjer om dagen: ukedag, uke, måne, sol."""
    ph, ic, nm = moon(day)
    s = sun(day)
    return {"week": day.isocalendar()[1], "moon": ic, "moon_name": nm, "sun": s,
            "red": H.is_red(day), "name": H.name(day)}


def search(q, years=2):
    """Finn hendelser og merkedager (egne hendelser, bursdager, ukeplan, røde dager) – neste og forrige år."""
    q = q.strip().lower()
    if not q:
        return []
    today = dt.date.today()
    start = dt.date(today.year - 1, 1, 1)
    end = dt.date(today.year + years, 12, 31)
    hits = []
    evs = [e for e in load()["events"] if q in (e.get("title", "") + " " + e.get("note", "")).lower()]
    d = start
    while d <= end and len(hits) < 80:
        for e in evs:
            if _occurs(e, d):
                hits.append((d, e.get("time", ""), e["title"]))
        for y_name in (H.red_days(d.year).get(d), H.special_days(d.year).get(d)):
            if y_name and q in y_name.lower():
                hits.append((d, "", y_name))
        d += dt.timedelta(days=1)
    return hits


def upcoming(n=6, days=60):
    """Neste hendelser fra i dag: [(dato, item)]."""
    today = dt.date.today()
    it = items(today, today + dt.timedelta(days=days), extra=False)
    out = []
    for d in sorted(it):
        for x in it[d]:
            if x.get("kind") in ("moon", "school", "special") or (x.get("kind") == "red" and d != today):
                continue
            out.append((d, x))
    return out[:n]


def today_line():
    """«I dag: Tannlege 14:00 · 🗑️ Papir · 🎂 Bestemor fyller 80» – til Oversikt."""
    today = dt.date.today()
    it = items(today, today, extra=False).get(today, [])
    parts = [f"{x['icon']} {x['title']}" + (f" {x['time']}" if x.get("time") else "") for x in it
             if x.get("kind") not in ("moon", "school")]
    return " · ".join(parts)


def countdown():
    """Nedtelling til neste store dag: (dager, tekst) – jul, påske, 17. mai, sommerferie, neste bursdag."""
    today = dt.date.today()
    cands = []
    for y in (today.year, today.year + 1):
        e = H.easter(y)
        cands += [(dt.date(y, 12, 24), "🎄 jul"), (e, "🐣 påske"), (dt.date(y, 5, 17), "🇳🇴 17. mai")]
        for a, _b, nm in school_holidays(y):
            if nm.startswith("Sommer"):
                cands.append((a, "☀️ sommerferie"))
    cands = sorted((d, t) for d, t in cands if d > today)
    if not cands:
        return None
    d, t = cands[0]
    return (d - today).days, f"{(d - today).days} dager til {t}"


# --------------------------------------------------------------------------
# Varsler
# --------------------------------------------------------------------------
_SENT = {}


def tick(notify, win=None):
    """Kalles hvert minutt fra bakgrunnen: påminnelser, søppel kvelden før og scener på tid."""
    now = dt.datetime.now()
    today = now.date()
    try:
        evs = load()["events"]
    except Exception:  # noqa: BLE001
        return
    for e in evs:
        for day in (today, today + dt.timedelta(days=1)):
            if not _occurs(e, day):
                continue
            key = f"{e['id']}:{day}"
            if e.get("kind") == "trash":                    # søppel: kvelden før kl. 18
                if day == today + dt.timedelta(days=1) and now.hour >= 18 and key not in _SENT:
                    _SENT[key] = 1
                    notify and notify("calendar", "🗑️ Søppeltømming i morgen", f"Sett ut: {e['title']}", force=True)
                continue
            if not e.get("time"):
                if day == today and e.get("remind", -1) >= 0 and now.hour >= 8 and key not in _SENT:
                    _SENT[key] = 1
                    notify and notify("calendar", f"{KINDS.get(e.get('kind'), ('📌',))[0]} I dag", e["title"],
                                      force=True)
                continue
            hh, mm = (int(x) for x in e["time"].split(":"))
            at = dt.datetime(day.year, day.month, day.day, hh, mm)
            if e.get("kind") == "scene" and e.get("scene") and at <= now < at + dt.timedelta(minutes=2) and \
                    key + ":scene" not in _SENT:
                _SENT[key + ":scene"] = 1
                try:
                    import scenes
                    from gi.repository import GLib
                    GLib.idle_add(lambda sid=e["scene"]: (scenes.run(win, sid, why="kalender"), False)[1])
                except Exception:  # noqa: BLE001
                    pass
            r = e.get("remind", 30)
            if r >= 0 and at - dt.timedelta(minutes=r) <= now < at and key not in _SENT:
                _SENT[key] = 1
                mins = int((at - now).total_seconds() // 60)
                notify and notify("calendar", f"⏰ {e['title']}", f"Kl. {e['time']}" + (f" – om {mins} min" if mins
                                                                                          else " – nå"), force=True)
