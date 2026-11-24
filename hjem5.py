"""Hjemmet, runde 5: middagsplan med handleliste, beskjed til alle skjermer, søvnrapport, TV av ved leggetid,
pakkesporing og minnevegg.

Middagsplanen og pakkene ligger på NAS-en (Familie/), så alle PC-er og mobiler ser det samme. Søvnrapporten bygger på
når PC-ene i huset sist var på om kvelden (PC-statusene på NAS-en). Pakkesporing: Posten/Bring og PostNord krever
API-nøkkel for automatisk status, så Kontrollsenter lagrer nummeret, kjenner igjen transportøren og åpner riktig
sporingsside – og legger forventet levering i kalenderen.
"""
import json
import os
import re
import tempfile
import threading
import time

DATA = os.path.expanduser("~/.local/share/systemmonitor")
CACHE = os.path.expanduser("~/.cache/systemmonitor")
SLEEP = os.path.join(DATA, "sovelogg.json")
CFG = os.path.expanduser("~/.config/systemmonitor/hjem5.json")
DEF = {"tv_bedtime": False, "tv_done": ""}
_LOCK = threading.Lock()


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


# ------------------------------------------------------------------ felles JSON på NAS-en (med lokal kopi)
def _nas_load(name, default):
    local = os.path.join(CACHE, name)
    d = None
    try:
        import lanupdate as L
        if L.on_lan():
            tmp = tempfile.mkdtemp()
            L._smb(f'cd "Familie"; get "{name}" "{tmp}/x.json"', 20)
            d = json.load(open(f"{tmp}/x.json"))
    except Exception:  # noqa: BLE001
        d = None
    if d is None:
        try:
            d = json.load(open(local))
        except (OSError, ValueError):
            d = default
    else:
        os.makedirs(CACHE, exist_ok=True)
        with open(local, "w") as f:
            json.dump(d, f)
    return d


def _nas_save(name, d):
    local = os.path.join(CACHE, name)
    os.makedirs(CACHE, exist_ok=True)
    with open(local + ".tmp", "w") as f:
        json.dump(d, f)
    os.replace(local + ".tmp", local)
    try:
        import lanupdate as L
        if L.on_lan():
            L._smb(f'cd "Familie"; put "{local}" "{name}"', 20)
    except Exception:  # noqa: BLE001
        pass
    return d


# ------------------------------------------------------------------ 28 / 10 – middagsplan og handleliste
MEALS = "middag.json"
FAVS = [("Taco", "kjøttdeig, tacokrydder, tortilla, salat, tomat, agurk, mais, rømme, ost"),
        ("Pizza", "pizzadeig, tomatsaus, ost, skinke, paprika"),
        ("Laks med poteter", "laks, poteter, brokkoli, smør"),
        ("Spaghetti bolognese", "spaghetti, kjøttdeig, hakkede tomater, løk, hvitløk, parmesan"),
        ("Fiskegrateng", "fiskegrateng, poteter, gulrøtter"),
        ("Kyllingwok", "kylling, wokgrønnsaker, nudler, soyasaus"),
        ("Pølser i lompe", "pølser, lomper, sennep, ketchup, sprøstekt løk"),
        ("Kjøttkaker", "kjøttkaker, poteter, brun saus, ertestuing, tyttebær"),
        ("Fiskepinner", "fiskepinner, poteter, remulade, gulrøtter"),
        ("Grøt", "risgrøt, kanel, sukker, smør")]


def meals():
    d = _nas_load(MEALS, {})
    d.setdefault("days", {})
    d.setdefault("favs", [{"dish": n, "ing": i} for n, i in FAVS])
    return d


def set_meal(day, dish, ing=""):
    """day = «2026-11-27». Tom rett = fjern."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(day)):
        raise ValueError("ugyldig dato")
    with _LOCK:
        d = meals()
        dish = (dish or "").strip()[:60]
        if not dish:
            d["days"].pop(day, None)
        else:
            fav = next((f for f in d["favs"] if f["dish"].lower() == dish.lower()), None)
            ing = (ing or (fav["ing"] if fav else "")).strip()[:300]
            d["days"][day] = {"dish": dish, "ing": ing}
            if not fav:
                d["favs"] = (d["favs"] + [{"dish": dish, "ing": ing}])[-40:]
            elif ing:
                fav["ing"] = ing
        cut = time.strftime("%Y-%m-%d", time.localtime(time.time() - 30 * 86400))
        d["days"] = {k: v for k, v in d["days"].items() if k >= cut}
        _nas_save(MEALS, d)
    return d


def week_menu(start=None):
    import datetime as dt
    s = start or dt.date.today()
    d = meals()
    out = []
    for i in range(7):
        day = s + dt.timedelta(days=i)
        m = d["days"].get(day.isoformat())
        out.append({"day": day.isoformat(), "wd": ["Man", "Tir", "Ons", "Tor", "Fre", "Lør", "Søn"][day.weekday()],
                    "dish": m["dish"] if m else "", "ing": m["ing"] if m else ""})
    return out


def menu_to_shop(start=None):
    """Alle ingrediensene for de neste 7 dagene i handlelista (uten dobbelt)."""
    import chatlink
    seen, n = set(), 0
    for m in week_menu(start):
        for i in re.split(r"[,\n;]", m["ing"] or ""):
            i = i.strip()
            if i and i.lower() not in seen:
                seen.add(i.lower())
                chatlink.shop_add(i)
                n += 1
    return f"🛒 {n} ting lagt i handlelista" if n else "Ingen ingredienser å legge til – skriv dem på rettene"


def suggest():
    """Forslag til en rett som ikke er spist på en stund."""
    d = meals()
    recent = {v["dish"].lower() for v in d["days"].values()}
    pool = [f for f in d["favs"] if f["dish"].lower() not in recent] or d["favs"]
    import random
    return random.choice(pool) if pool else None


# ------------------------------------------------------------------ 51 – beskjed til alle skjermer
def broadcast(text, frm="Kontrollsenter"):
    text = (text or "").strip()[:200]
    if not text:
        raise ValueError("skriv en beskjed")
    import features
    features.send_to("*", frm, "📢 " + text, urgent=True)           # alle PC-ene, over spillet med lyd
    try:
        import push
        if push.enabled():
            push.publish("broadcast", f"📢 Beskjed fra {frm}", text)  # telefonene (og TV-er med ntfy)
    except Exception:  # noqa: BLE001
        pass
    BROADCAST.update(text=text, frm=frm, t=time.time())             # appen på TV-en viser den i stort
    return "Beskjeden er sendt til alle skjermene"


BROADCAST = {"text": "", "frm": "", "t": 0}


# ------------------------------------------------------------------ 49 – søvnrapport
def _night_key(lt):
    """Kvelden en sen time hører til: kl. 01 natt til fredag = torsdag."""
    t = time.mktime(lt) - (86400 if lt.tm_hour < 12 else 0)
    return time.strftime("%Y-%m-%d", time.localtime(t))


def sleep_tick():
    """Hvert 10. minutt: hvilke PC-er er på sent (etter kl. 20)? Siste tidspunkt per kveld lagres."""
    lt = time.localtime()
    if 6 <= lt.tm_hour < 20:
        return
    try:
        import homepcs
        on = [p.get("name") for p in homepcs.fetch() or []
              if time.time() - (p.get("time") or 0) < homepcs.STALE and not p.get("off") and p.get("name")]
    except Exception:  # noqa: BLE001
        return
    if not on:
        return
    key = _night_key(lt)
    with _LOCK:
        try:
            d = json.load(open(SLEEP))
        except (OSError, ValueError):
            d = {}
        night = d.setdefault(key, {})
        stamp = time.strftime("%H:%M")
        for n in on:
            night[n] = stamp
        d = dict(sorted(d.items())[-60:])
        os.makedirs(DATA, exist_ok=True)
        with open(SLEEP + ".tmp", "w") as f:
            json.dump(d, f)
        os.replace(SLEEP + ".tmp", SLEEP)


def _mins(hhmm):
    h, m = (int(x) for x in hhmm.split(":"))
    return (h + (24 if h < 12 else 0)) * 60 + m              # 01:30 regnes som 25:30 (etter midnatt)


def sleep_report(nights=7):
    """Per PC: når den sist var på hver kveld, og hvor mye etter leggetid."""
    try:
        d = json.load(open(SLEEP))
    except (OSError, ValueError):
        d = {}
    try:
        import features
        b = features.cfg()["bedtime"]
        bt = {"weekday": b.get("weekday") or "22:00", "weekend": b.get("weekend") or "23:30"}
    except Exception:  # noqa: BLE001
        bt = {"weekday": "22:00", "weekend": "23:30"}
    days = sorted(d)[-nights:]
    pcs = sorted({p for k in days for p in d[k]})
    rows = []
    for p in pcs:
        late = []
        for k in days:
            t = d[k].get(p)
            wd = time.strptime(k, "%Y-%m-%d").tm_wday
            bed = bt["weekend"] if wd in (4, 5) else bt["weekday"]          # fredag og lørdag kveld = helg
            over = (_mins(t) - _mins(bed)) if t and re.fullmatch(r"\d\d:\d\d", bed) else None
            late.append({"day": k, "off": t, "over": over})
        overs = [x["over"] for x in late if x["over"] is not None and x["over"] > 0]
        rows.append({"pc": p, "nights": late, "late_n": len(overs),
                     "avg_over": round(sum(overs) / len(overs)) if overs else 0})
    return {"days": days, "rows": rows, "bedtime": bt}


# ------------------------------------------------------------------ 12 – TV av ved leggetid
def tv_tick():
    """TV-en (Samsung, koblet til under Smart Hjem) slås av ved leggetid – 10 min varsel på PC-ene først."""
    c = cfg()
    if not c["tv_bedtime"]:
        return
    try:
        import features
        b = features.cfg()["bedtime"]
        wd = time.localtime().tm_wday
        bed = b.get("weekend", "23:30") if wd in (4, 5) else b.get("weekday", "22:00")
        bh, bm = (int(x) for x in bed.split(":"))
    except Exception:  # noqa: BLE001
        return
    lt = time.localtime()
    now = lt.tm_hour * 60 + lt.tm_min
    tag = time.strftime("%Y-%m-%d")
    if bh * 60 + bm - 10 <= now < bh * 60 + bm - 5 and c["tv_done"] not in (tag + "w", tag):
        set_(tv_done=tag + "w")
        try:
            features.send_to("*", "Leggetid", "📺 TV-en slås av om 10 minutter – leggetid!", urgent=True)
        except Exception:  # noqa: BLE001
            pass
    if bh * 60 + bm <= now < bh * 60 + bm + 10 and c["tv_done"] != tag:
        set_(tv_done=tag)
        import smartauto
        smartauto._tv_off()


# ------------------------------------------------------------------ 31 – pakkesporing
PKG = "pakker.json"


def carrier(nr):
    n = nr.strip().upper().replace(" ", "")
    if re.fullmatch(r"(37|70)\d{16}|\d{17,20}|[A-Z]{2}\d{9}NO|CS\d{9}NO", n):
        return "Posten/Bring", f"https://sporing.posten.no/sporing/{n}"
    if re.fullmatch(r"[A-Z]{2}\d{9}(SE|DK|FI)|00\d{18}|\d{11}", n):
        return "PostNord", f"https://tracking.postnord.com/no/?id={n}"
    if re.fullmatch(r"1Z[0-9A-Z]{16}", n):
        return "UPS", f"https://www.ups.com/track?tracknum={n}"
    if re.fullmatch(r"\d{10}|JJD\d+|JVGL\d+", n):
        return "DHL", f"https://www.dhl.com/no-no/home/tracking.html?tracking-id={n}"
    from urllib.parse import quote
    return "Ukjent", f"https://duckduckgo.com/?q={quote(n + ' sporing')}"


def packages():
    d = _nas_load(PKG, {"items": []})
    return d.get("items", [])


def add_package(nr, name="", eta=""):
    nr = re.sub(r"\s", "", str(nr or ""))[:40]
    if len(nr) < 6:
        raise ValueError("sporingsnummeret er for kort")
    if eta and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", eta):
        raise ValueError("dato som 2026-11-30")
    car, url = carrier(nr)
    with _LOCK:
        items = [p for p in packages() if p["nr"] != nr]
        items.append({"nr": nr, "name": (name or "").strip()[:40] or "Pakke", "eta": eta, "carrier": car,
                      "url": url, "added": time.time(), "done": False})
        _nas_save(PKG, {"items": items[-30:]})
    return f"📦 Lagt til ({car})"


def done_package(nr, remove=False):
    with _LOCK:
        items = packages()
        items = [p for p in items if p["nr"] != nr] if remove else \
            [{**p, "done": True} if p["nr"] == nr else p for p in items]
        _nas_save(PKG, {"items": items})
    return "Fjernet" if remove else "Merket som hentet"


# ------------------------------------------------------------------ 50 – minnevegg
def memories(limit=80):
    """Bilder fra chatten (nyeste først) – til lysbildeshow på TV-en eller PC-en."""
    out = []
    try:
        import chatplus
        root = chatplus.FILES
        for f in sorted(os.listdir(root), key=lambda n: -os.path.getmtime(os.path.join(root, n))):
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
                out.append({"name": f, "path": os.path.join(root, f), "t": os.path.getmtime(os.path.join(root, f))})
            if len(out) >= limit:
                break
    except OSError:
        pass
    return out


# ------------------------------------------------------------------ kalender: middag og pakker
def calendar_items(days, put):
    try:
        d = meals()
        for day in days:
            m = d["days"].get(day.isoformat())
            if m:
                put(day, title=f"🍽️ {m['dish']}", time="", color="#ff9f43", kind="meal", icon="🍽️", src="middag")
        for p in packages():
            if p.get("eta") and not p.get("done"):
                for day in days:
                    if day.isoformat() == p["eta"]:
                        put(day, title=f"📦 {p['name']} ({p['carrier']})", time="", color="#8e7cc3", kind="pkg",
                            icon="📦", src="middag")
    except Exception:  # noqa: BLE001
        pass


def tick():
    """Hvert 10. minutt fra bakgrunnen (TV-en sjekkes hvert minutt: tv_tick)."""
    for fn in (sleep_tick,):
        try:
            fn()
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("hjem5 %s", fn.__name__)
