"""Data til de nye flisene i Oversikt: ping, strømpris nå, vær, neste kalenderavtale og spilletid i dag.

Alt hentes i bakgrunnen og mellomlagres, så vinduet aldri venter på nettet. Innstillinger (utseende.json →
"info"): {"place": "Oslo", "lat": .., "lon": .., "area": "NO1", "ics": "https://…"}.

Kilder (gratis, uten nøkkel): hvakosterstrommen.no (spotpris), open-meteo.com (vær og stedsoppslag).
"""
import json
import os
import socket
import threading
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

CFG = os.path.expanduser("~/.config/systemmonitor/infofliser.json")
UA = {"User-Agent": "Kontrollsenter (hjemme-PC)"}
_C = {}


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
    for k in ("price", "weather", "cal"):
        _C.pop(k, None)


def _get(url, timeout=10):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def _cached(key, fn, max_age):
    """Siste svar med en gang; ny henting i bakgrunnen når det er gammelt."""
    c = _C.setdefault(key, {"t": 0, "v": None, "busy": False})
    if time.time() - c["t"] > max_age and not c["busy"]:
        c["busy"] = True

        def work():
            try:
                c["v"] = fn()
            except Exception as e:  # noqa: BLE001
                c["v"] = {"error": str(e)[:120]}
            c["t"] = time.time()
            c["busy"] = False
        threading.Thread(target=work, daemon=True).start()
    return c["v"]


# ---- ping --------------------------------------------------------------------
_PINGS = []


def _ping_once():
    best = None
    for host in ("1.1.1.1", "8.8.8.8"):
        t = time.perf_counter()
        try:
            with socket.create_connection((host, 443), timeout=2):
                ms = (time.perf_counter() - t) * 1000
                best = ms if best is None else min(best, ms)
        except OSError:
            continue
    _PINGS.append(best)
    del _PINGS[:-60]
    return {"ms": None if best is None else round(best), "hist": list(_PINGS)}


def ping():
    return _cached("ping", _ping_once, 8)


# ---- strømpris -----------------------------------------------------------------
AREAS = [("NO1", "Øst-Norge"), ("NO2", "Sør-Norge"), ("NO3", "Midt-Norge"), ("NO4", "Nord-Norge"), ("NO5", "Vest-Norge")]


def _price():
    area = cfg().get("area", "NO1")
    out = []
    for d in (date.today(), date.today() + timedelta(days=1)):
        try:
            raw = _get(f"https://www.hvakosterstrommen.no/api/v1/prices/{d:%Y}/{d:%m-%d}_{area}.json")
            out += json.loads(raw)
        except Exception:  # noqa: BLE001
            if d == date.today():
                raise
    vat = 1.0 if area == "NO4" else 1.25
    now = datetime.now(timezone.utc)
    rows = []
    for p in out:
        a = datetime.fromisoformat(p["time_start"])
        b = datetime.fromisoformat(p["time_end"])
        rows.append((a, b, p["NOK_per_kWh"] * vat))
    cur = next((r for r in rows if r[0] <= now < r[1]), None)
    future = [r for r in rows if r[1] > now]
    cheap = min(future[:24], key=lambda r: r[2]) if future else None
    day = [r[2] for r in rows if r[0].astimezone().date() == date.today()]
    return {"area": area, "now": round(cur[2], 2) if cur else None,
            "cheapest": round(cheap[2], 2) if cheap else None,
            "cheapest_at": cheap[0].astimezone().strftime("%H:%M") if cheap else None,
            "avg": round(sum(day) / len(day), 2) if day else None,
            "hist": [round(r[2], 2) for r in rows if r[0].astimezone().date() == date.today()]}


def price():
    return _cached("price", _price, 600)


# ---- vær ------------------------------------------------------------------------
WMO = {0: ("☀️", "Klart"), 1: ("🌤️", "Lettskyet"), 2: ("⛅", "Delvis skyet"), 3: ("☁️", "Overskyet"), 45: ("🌫️", "Tåke"),
       48: ("🌫️", "Rimtåke"), 51: ("🌦️", "Lett yr"), 53: ("🌦️", "Yr"), 55: ("🌧️", "Tett yr"), 61: ("🌦️", "Litt regn"),
       63: ("🌧️", "Regn"), 65: ("🌧️", "Kraftig regn"), 66: ("🌧️", "Underkjølt regn"), 67: ("🌧️", "Underkjølt regn"),
       71: ("🌨️", "Litt snø"), 73: ("🌨️", "Snø"), 75: ("❄️", "Mye snø"), 77: ("🌨️", "Snøkorn"), 80: ("🌦️", "Regnbyger"),
       81: ("🌧️", "Regnbyger"), 82: ("⛈️", "Kraftige byger"), 85: ("🌨️", "Snøbyger"), 86: ("❄️", "Snøbyger"),
       95: ("⛈️", "Torden"), 96: ("⛈️", "Torden med hagl"), 99: ("⛈️", "Torden med hagl")}


def find_place(name):
    """Stedsnavn -> (navn, lat, lon). Sender bare navnet du skrev inn."""
    q = urllib.parse.urlencode({"name": name, "count": 1, "language": "no", "format": "json"})
    j = json.loads(_get("https://geocoding-api.open-meteo.com/v1/search?" + q))
    r = (j.get("results") or [None])[0]
    if not r:
        raise ValueError(f"fant ikke «{name}»")
    return f"{r['name']}" + (f", {r.get('admin1')}" if r.get("admin1") else ""), r["latitude"], r["longitude"]


def _weather():
    c = cfg()
    if not c.get("lat"):
        return {"error": "velg sted"}
    q = urllib.parse.urlencode({"latitude": c["lat"], "longitude": c["lon"], "timezone": "auto",
                                "current": "temperature_2m,weather_code,wind_speed_10m,apparent_temperature",
                                "daily": "temperature_2m_max,temperature_2m_min,weather_code", "forecast_days": 2})
    j = json.loads(_get("https://api.open-meteo.com/v1/forecast?" + q))
    cur = j["current"]
    icon, text = WMO.get(int(cur.get("weather_code", 0)), ("🌡️", ""))
    d = j.get("daily") or {}
    tm = None
    if d.get("time") and len(d["time"]) > 1:
        ti, tt = WMO.get(int(d["weather_code"][1]), ("", ""))
        tm = f"{ti} {round(d['temperature_2m_min'][1])}–{round(d['temperature_2m_max'][1])}°"
    return {"place": c.get("place", ""), "temp": round(cur["temperature_2m"]), "feels": round(cur["apparent_temperature"]),
            "wind": round(cur["wind_speed_10m"] / 3.6, 1), "icon": icon, "text": text,
            "max": round(d["temperature_2m_max"][0]) if d.get("temperature_2m_max") else None,
            "min": round(d["temperature_2m_min"][0]) if d.get("temperature_2m_min") else None, "tomorrow": tm}


def weather():
    return _cached("weather", _weather, 900)


# ---- kalender (ICS-adresse, f.eks. «hemmelig adresse i iCal-format» fra Google Kalender) ----------------------
def _ics_time(val, params):
    val = val.strip()
    if "VALUE=DATE" in params or len(val) == 8:
        return datetime.strptime(val[:8], "%Y%m%d").replace(tzinfo=datetime.now().astimezone().tzinfo), True
    if val.endswith("Z"):
        return datetime.strptime(val, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc), False
    try:
        from zoneinfo import ZoneInfo
        tz = next((p.split("=", 1)[1] for p in params.split(";") if p.startswith("TZID=")), None)
        tzinfo = ZoneInfo(tz) if tz else datetime.now().astimezone().tzinfo
    except Exception:  # noqa: BLE001
        tzinfo = datetime.now().astimezone().tzinfo
    return datetime.strptime(val[:15], "%Y%m%dT%H%M%S").replace(tzinfo=tzinfo), False


def _cal():
    url = cfg().get("ics")
    if not url:
        return {"error": "legg inn kalender"}
    if url.startswith("webcal://"):
        url = "https://" + url[9:]
    text = _get(url, 20).decode("utf-8", "replace").replace("\r\n ", "").replace("\n ", "")
    now = datetime.now(timezone.utc)
    events, cur = [], None
    for line in text.splitlines():
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT" and cur is not None:
            if cur.get("start"):
                events.append(cur)
            cur = None
        elif cur is not None and ":" in line:
            k, v = line.split(":", 1)
            name, _, params = k.partition(";")
            if name == "DTSTART":
                try:
                    cur["start"], cur["allday"] = _ics_time(v, params)
                except ValueError:
                    pass
            elif name == "SUMMARY":
                cur["title"] = v.replace("\\,", ",").replace("\\n", " ")
            elif name == "LOCATION":
                cur["where"] = v.replace("\\,", ",")
            elif name == "RRULE":
                cur["rrule"] = v
    # gjentakende hendelser: neste ukentlige/daglige forekomst (enkel støtte)
    for e in events:
        r = e.get("rrule", "")
        if e["start"] < now and ("FREQ=WEEKLY" in r or "FREQ=DAILY" in r):
            step = timedelta(days=7 if "WEEKLY" in r else 1)
            while e["start"] < now:
                e["start"] += step
    up = sorted((e for e in events if e["start"] >= now - timedelta(minutes=5)), key=lambda e: e["start"])
    out = []
    for e in up[:5]:
        loc = e["start"].astimezone()
        days = (loc.date() - date.today()).days
        when = ("i dag" if days == 0 else "i morgen" if days == 1 else loc.strftime("%d.%m"))
        out.append({"title": e.get("title", "(uten tittel)"), "where": e.get("where", ""),
                    "when": when + ("" if e.get("allday") else " kl. " + loc.strftime("%H:%M")),
                    "in_min": int((e["start"] - now).total_seconds() // 60)})
    return {"events": out}


def calendar():
    return _cached("cal", _cal, 900)


# ---- spilletid i dag ----------------------------------------------------------------------------
def playtime_today():
    try:
        import remote_extra
        pt = remote_extra.playtime_summary(1)
        return pt["days"][-1]["total"]
    except Exception:  # noqa: BLE001
        return None


def snapshot():
    """Alt samlet (til mobilappen)."""
    return {"ping": ping(), "price": price(), "weather": weather(), "cal": calendar(), "play_s": playtime_today()}
