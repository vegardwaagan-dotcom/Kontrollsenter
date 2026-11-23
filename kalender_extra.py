"""Ekstra kilder i kalenderen: spill (WoW-reset, gratis Epic-spill, Steam-salg, spilletid), PC-en (temperatur, strøm,
PC-dagbok, planlagte oppgaver), hjemmet (strømpris, vær 10 dager, hvem var hjemme, klipp) og importert
Google/Outlook-kalender. Pluss logg over når vennene og PC-ene hjemme er på (for «når pleier vennene å spille»).
"""
import datetime as dt
import json
import os
import sqlite3
import threading
import time
import urllib.parse
import urllib.request

LOG = os.path.expanduser("~/.local/share/systemmonitor/kalender-logg.json")
_C = {}
_LOCK = threading.Lock()


def _cached(key, fn, age):
    v = _C.get(key)
    if v and time.time() - v[0] < age:
        return v[1]
    try:
        r = fn()
    except Exception:  # noqa: BLE001
        r = v[1] if v else None
    _C[key] = (time.time(), r)
    return r


def _log():
    try:
        with open(LOG) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"home": {}, "friends": {}}


# --------------------------------------------------------------------------
# Spill
# --------------------------------------------------------------------------
def _play():
    try:
        import remote_extra
        return remote_extra._play_data()
    except Exception:  # noqa: BLE001
        return {}


def _plays_wow(play):
    cut = (dt.date.today() - dt.timedelta(days=45)).isoformat()
    return any("warcraft" in g.lower() for d, gs in play.items() if d >= cut for g in gs)


def steam_sales(year):
    """Omtrentlige datoer for de store Steam-salgene (Valve kunngjør eksakte datoer litt før)."""
    def nth(month, wd, n):
        d = dt.date(year, month, 1)
        return d + dt.timedelta(days=(wd - d.weekday()) % 7 + 7 * (n - 1))
    thanks = nth(11, 3, 4)                                   # amerikansk Thanksgiving (4. torsdag i november)
    return [(nth(3, 3, 3), nth(3, 3, 3) + dt.timedelta(days=7), "Steam vårsalg (ca.)"),
            (nth(6, 3, 4), nth(6, 3, 4) + dt.timedelta(days=14), "Steam sommersalg (ca.)"),
            (thanks - dt.timedelta(days=2), thanks + dt.timedelta(days=5), "Steam høstsalg (ca.)"),
            (dt.date(year, 12, 18), dt.date(year + 1, 1, 2), "Steam vintersalg (ca.)")]


def _epic():
    import freegames
    return freegames.fetch()


# --------------------------------------------------------------------------
# PC-en
# --------------------------------------------------------------------------
def _pc_days(a, b):
    """{dato: (maks CPU °C, maks GPU °C, kWh)} fra historikken."""
    try:
        import history
        con = sqlite3.connect(f"file:{history.DB}?mode=ro", uri=True, timeout=2)
        t0 = time.mktime(a.timetuple())
        t1 = time.mktime((b + dt.timedelta(days=1)).timetuple())
        rows = con.execute("SELECT date(ts, 'unixepoch', 'localtime') d, max(cpu_t), max(gpu_t), avg(watts), "
                           "count(*), min(ts), max(ts) FROM s WHERE ts >= ? AND ts < ? GROUP BY d",
                           (int(t0), int(t1))).fetchall()
        con.close()
    except Exception:  # noqa: BLE001
        return {}
    out = {}
    for d, ct, gt, w, n, t_a, t_b in rows:
        hours = max(0.0, (t_b - t_a) / 3600) if n > 1 else 0
        out[d] = (ct, gt, round((w or 0) * hours / 1000, 2))
    return out


def _pc_events():
    """PC-dagbok: oppdateringer, opprydding, krasj og systemsjekk fra tidslinjen."""
    try:
        import remote_extra
        with open(remote_extra.EVENTS, encoding="utf-8") as f:
            lines = f.readlines()[-1500:]
    except OSError:
        return {}
    out = {}
    keep = ("update", "lanupdate", "cleanup", "syscheck", "crash", "backup", "smart", "error", "driver", "temprise",
            "restart", "lan", "achievement", "weekly")
    for ln in lines:
        try:
            e = json.loads(ln)
        except ValueError:
            continue
        if not any(k in str(e.get("kind", "")) for k in keep):
            continue
        d = time.strftime("%Y-%m-%d", time.localtime(e.get("t", 0)))
        out.setdefault(d, []).append(str(e.get("title", ""))[:70])
    return out


def _planned(days):
    """Det Kontrollsenter skal gjøre av seg selv."""
    out = {}
    try:
        import upkeep
        import updates
        if updates.auto_on():
            c = upkeep.cfg()
            nxt = dt.date.fromtimestamp(c.get("last", 0) + 30 * 86400) if c.get("last") else dt.date.today()
            out.setdefault(max(nxt, dt.date.today()), []).append("🧹 Automatisk opprydding")
    except Exception:  # noqa: BLE001
        pass
    try:
        import ai_rules
        import re
        for r in ai_rules.load():
            m = re.match(r"^(\w+)\s+(\d{1,2}:\d\d)$", r.get("når", ""))
            if not m:
                continue
            for d in days:
                day = m.group(1)[:3]
                if m.group(1).startswith("daglig") or ai_rules.DAYS.get(day) == d.weekday():
                    out.setdefault(d, []).append(f"🤖 {r.get('navn') or ai_rules.describe(r)[:50]} {m.group(2)}")
    except Exception:  # noqa: BLE001
        pass
    try:
        import equipment
        if equipment.cfg().get("weekly_video"):
            for d in days:
                if d.weekday() == 6:
                    out.setdefault(d, []).append("🎬 Ukens beste øyeblikk lages")
    except Exception:  # noqa: BLE001
        pass
    return out


# --------------------------------------------------------------------------
# Hjemmet
# --------------------------------------------------------------------------
def _weather10():
    import infotiles
    c = infotiles.cfg()
    if not c.get("lat"):
        return {}
    q = urllib.parse.urlencode({"latitude": c["lat"], "longitude": c["lon"], "timezone": "auto", "forecast_days": 10,
                                "daily": "temperature_2m_max,temperature_2m_min,weather_code"})
    with urllib.request.urlopen(urllib.request.Request("https://api.open-meteo.com/v1/forecast?" + q,
                                                       headers={"User-Agent": "Kontrollsenter"}), timeout=10) as r:
        j = json.load(r)
    d = j.get("daily") or {}
    out = {}
    for i, day in enumerate(d.get("time") or []):
        ic, txt = infotiles.WMO.get(int(d["weather_code"][i]), ("🌡️", ""))
        out[day] = (ic, round(d["temperature_2m_min"][i]), round(d["temperature_2m_max"][i]), txt)
    return out


def _price():
    import infotiles
    return infotiles.price()


def _ics():
    """Alle hendelsene fra kalender-lenken (Google/Outlook) under Oversikt-flisen."""
    import infotiles
    infotiles.calendar()
    return list(getattr(infotiles, "_ICS_ALL", []) or [])


def _clips():
    try:
        import clipx
        out = {}
        for c in clipx.files():
            d = time.strftime("%Y-%m-%d", time.localtime(c.get("t", 0)))
            out.setdefault(d, []).append(c)
        return out
    except Exception:  # noqa: BLE001
        return {}


# --------------------------------------------------------------------------
# Alt inn i kalenderen
# --------------------------------------------------------------------------
def add_items(days, put, show):
    today = dt.date.today()
    play = _play() if (show.get("spill") or show.get("pc")) else {}
    if show.get("spill"):
        wow = _plays_wow(play)
        for d in days:
            if wow and d.weekday() == 2:
                put(d, title="WoW: ukentlig reset", time="", color="#c69b6d", kind="game", icon="🐉", src="spill")
            secs = sum((play.get(d.isoformat()) or {}).values())
            if d <= today and secs >= 300:
                h, m = int(secs // 3600), int(secs % 3600 // 60)
                lim = None
                try:
                    import remote_extra
                    lc = remote_extra.limit_cfg()
                    if lc.get("enabled"):
                        lim = (lc["weekend"] if d.weekday() >= 5 else lc["weekday"]) * 3600
                except Exception:  # noqa: BLE001
                    pass
                over = lim and secs > lim
                put(d, title=f"{'⚠️ ' if over else ''}{h} t {m} min spilt" + (" – over grensen" if over else ""),
                    time="", color="#ff4d4d" if over else "#8a8fa3", kind="stat", icon="🎮", src="spilletid")
        ep = _cached("epic", _epic, 6 * 3600) or {}
        for g in (ep.get("now") or []) + (ep.get("soon") or []):
            try:
                a = dt.date.fromtimestamp(g["from"])
                b = dt.date.fromtimestamp(g["until"])
            except (KeyError, TypeError, ValueError, OSError):
                continue
            for d in days:
                if d in (a, b):
                    put(d, title=f"{'Gratis fra i dag' if d == a else 'Siste dag gratis'}: {g['title']} (Epic)",
                        time="", color="#2ecc71", kind="game", icon="🎁", src="epic")
        for y in {d.year for d in days} | {min(days).year - 1}:
            for a, b, nm in steam_sales(y):
                for d in days:
                    if d in (a, b):
                        put(d, title=("Starter: " if d == a else "Slutter: ") + nm, time="", color="#1b2838",
                            kind="game", icon="🛒", src="steam")
    if show.get("pc"):
        stats = _pc_days(min(days), min(max(days), today))
        ev = _cached("pcev", _pc_events, 120) or {}
        plan = _planned(days)
        clips = _cached("clips", _clips, 120) or {}
        for d in days:
            s = stats.get(d.isoformat())
            if s and d <= today:
                ct, gt, kwh = s
                put(d, title=f"Maks CPU {round(ct or 0)}° · GPU {round(gt or 0)}° · {kwh} kWh", time="",
                    color="#8a8fa3", kind="stat", icon="🌡️", src="pc")
            for t in (ev.get(d.isoformat()) or [])[:3]:
                put(d, title=t, time="", color="#8a8fa3", kind="pclog", icon="🖥️", src="pc-dagbok")
            for t in plan.get(d, []):
                put(d, title=t, time="", color="#5b8cff", kind="planned", icon="⏱️", src="planlagt")
            cs = clips.get(d.isoformat()) or []
            if cs:
                put(d, title=f"{len(cs)} klipp/skjermbilder" + (f" – {cs[0].get('name', '')[:40]}" if len(cs) == 1
                                                                  else ""),
                    time="", color="#ff9f43", kind="clips", icon="🎬", src="klipp")
    # hjemmet
    w = (_cached("w10", _weather10, 3600) or {}) if show.get("vaer", True) else {}
    for d in days:
        x = w.get(d.isoformat())
        if x:
            put(d, title=f"{x[3]} {x[1]}–{x[2]}°", time="", color="#48dbfb", kind="weather", icon=x[0], src="vær")
    if show.get("strom", True) and (today in days or today + dt.timedelta(days=1) in days):
        p = _cached("price", _price, 600) or {}
        if p.get("cheapest") is not None:
            put(today, title=f"Strøm nå {p.get('now')} kr · billigst {p['cheapest']} kr kl. {p['cheapest_at']}",
                time="", color="#feca57", kind="price", icon="⚡", src="strøm")
    log = _log() if show.get("hjemme", True) else {}
    for d in days:
        who = log.get("home", {}).get(d.isoformat())
        if who and d <= today:
            put(d, title="Hjemme: " + ", ".join(sorted(who))[:80], time="", color="#8a8fa3", kind="stat", icon="🏠",
                src="hjemme")
    if show.get("ics"):
        for e in _cached("ics", _ics, 900) or []:
            try:
                st = e["start"].astimezone()
            except (KeyError, AttributeError):
                continue
            if st.date() in days:
                put(st.date(), title=e.get("title", "(uten tittel)"), time="" if e.get("allday") else
                    st.strftime("%H:%M"), color="#4285f4", kind="ics", icon="📆", src="importert")


# --------------------------------------------------------------------------
# Logg: hvem er hjemme / når er vennene på (kalles hvert 15. minutt i bakgrunnen)
# --------------------------------------------------------------------------
def log_tick():
    now = dt.datetime.now()
    day = now.date().isoformat()
    home, friends_on = set(), []
    try:
        import homepcs
        for p in homepcs.fetch() or []:
            if time.time() - p.get("time", 0) < 900 and not p.get("off"):
                home.add(p.get("name"))
    except Exception:  # noqa: BLE001
        pass
    try:
        import friends
        friends_on = [d.get("friend") for d in friends.fetch_all() if d.get("online")]
    except Exception:  # noqa: BLE001
        pass
    with _LOCK:
        lg = _log()
        if home:
            lg.setdefault("home", {}).setdefault(day, [])
            lg["home"][day] = sorted(set(lg["home"][day]) | home)
        slot = f"{now.weekday()}-{now.hour}"
        for f in friends_on:
            fs = lg.setdefault("friends", {}).setdefault(f, {})
            fs[slot] = fs.get(slot, 0) + 1
        cut = (now.date() - dt.timedelta(days=400)).isoformat()
        lg["home"] = {k: v for k, v in lg.get("home", {}).items() if k >= cut}
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG + ".tmp", "w") as f:
            json.dump(lg, f)
        os.replace(LOG + ".tmp", LOG)


def friends_usual(top=3):
    """{venn: ["fredag 20–22", …]} – når vennene pleier å være på (fra loggen)."""
    names = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"]
    out = {}
    for f, slots in _log().get("friends", {}).items():
        best = sorted(slots.items(), key=lambda x: -x[1])[:top]
        out[f] = [f"{names[int(k.split('-')[0])]} {int(k.split('-')[1]):02d}–{(int(k.split('-')[1]) + 1) % 24:02d}"
                  for k, _n in best]
    return out
