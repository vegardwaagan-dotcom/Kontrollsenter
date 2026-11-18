"""«Dagen i dag» og prestasjoner.

summary()      – spilletid, mest spilte spill, økter, klipp, strøm (kWh og kr) og varmeste temperatur i dag.
achievements() – merker du låser opp (🏆) ut fra det Kontrollsenter allerede vet: spilletid, økter, klipp,
                 temaer, scener, VR, mål og stjerner. check() finner nye og varsler.
"""
import json
import os
import time

DATA = os.path.expanduser("~/.local/share/systemmonitor/prestasjoner.json")


def _midnight():
    return time.mktime(time.strptime(time.strftime("%Y-%m-%d"), "%Y-%m-%d"))


def _sessions():
    try:
        import games_auto
        return games_auto.load_sessions()
    except Exception:  # noqa: BLE001
        return []


def _playtime():
    try:
        import remote_extra
        return json.load(open(remote_extra.PLAYTIME))
    except (OSError, ValueError, ImportError):
        return {}


def _clips():
    try:
        import clips
        return clips.clips(5000)
    except Exception:  # noqa: BLE001
        return []


def summary():
    day = time.strftime("%Y-%m-%d")
    games = _playtime().get(day, {})
    play = round(sum(games.values()))
    top = max(games.items(), key=lambda kv: kv[1])[0] if games else None
    mid = _midnight()
    ses = [s for s in _sessions() if (s.get("start") or 0) >= mid]
    clips_today = [c for c in _clips() if c.get("t", 0) >= mid]
    out = {"play_s": play, "top": top, "games": len(games), "sessions": len(ses),
           "longest_min": max((s.get("minutes") or 0 for s in ses), default=0), "clips": len(clips_today),
           "kwh": None, "kr": None, "max_cpu": None, "max_gpu": None, "avg_w": None}
    try:
        import power
        wh = power.EnergyLog()._get(day)[0]
        out["kwh"] = round(wh / 1000, 2)
        out["kr"] = round(wh / 1000 * power.load()["price"], 2)
    except Exception:  # noqa: BLE001
        pass
    try:
        import history
        st = history.stats(int(time.time() - mid))
        if st:
            out["max_cpu"], out["max_gpu"] = (round(st[0]) if st[0] else None), (round(st[1]) if st[1] else None)
            out["avg_w"] = round(st[3]) if st[3] else None
    except Exception:  # noqa: BLE001
        pass
    return out


def text(s=None):
    s = s or summary()
    h, m = s["play_s"] // 3600, s["play_s"] % 3600 // 60
    bits = [f"🎮 {h} t {m} min" + (f" · mest {s['top']}" if s["top"] else "")]
    if s["clips"]:
        bits.append(f"🎬 {s['clips']} klipp")
    if s["kwh"] is not None:
        bits.append(f"⚡ {s['kwh']} kWh" + (f" ({s['kr']:.2f} kr)" if s["kr"] is not None else ""))
    if s["max_cpu"]:
        bits.append(f"🌡️ maks {s['max_cpu']}° / {s['max_gpu'] or '–'}°")
    return " · ".join(bits)


# --------------------------------------------------------------------------
# Prestasjoner
# --------------------------------------------------------------------------
def _facts():
    ses = _sessions()
    pt = _playtime()
    total_h = sum(sum(d.values()) for d in pt.values()) / 3600
    days = sorted(d for d, g in pt.items() if sum(g.values()) > 300)
    streak, best = 0, 0
    prev = None
    for d in days:
        t = time.mktime(time.strptime(d, "%Y-%m-%d"))
        streak = streak + 1 if prev and abs(t - prev - 86400) < 7200 else 1
        best = max(best, streak)
        prev = t
    hours = [time.localtime(s.get("start") or 0).tm_hour for s in ses]
    f = {"sessions": len(ses), "total_h": total_h, "longest": max((s.get("minutes") or 0 for s in ses), default=0),
         "night": any(0 <= h < 4 for h in hours), "early": any(5 <= h < 7 for h in hours), "streak": best,
         "clips": len(_clips()), "games": len({s.get("name") for s in ses}),
         "cool": any((s.get("minutes") or 0) >= 30 and (s.get("max_gpu") or 99) < 65 for s in ses)}
    try:
        import theme
        f["themes"] = len(set(theme.look().get("themes_tried") or []))
    except Exception:  # noqa: BLE001
        f["themes"] = 0
    try:
        import scenes
        f["scenes"] = len([s for s in scenes.load()["scenes"] if s["id"] not in {d["id"] for d in scenes.DEFAULTS}])
    except Exception:  # noqa: BLE001
        f["scenes"] = 0
    try:
        import vr
        f["vr"] = bool(vr.cfg().get("started"))
    except Exception:  # noqa: BLE001
        f["vr"] = False
    try:
        import features
        f["homework"] = sum(1 for r in features.cfg().get("goal_reqs", []) if r.get("state") == "godkjent")
        import familyplus
        f["stars"] = familyplus.stars()
    except Exception:  # noqa: BLE001
        f["homework"], f["stars"] = 0, 0
    return f


ACH = [
    ("first", "🎮", "Første økt", "Spill din første økt med Kontrollsenter", lambda f: f["sessions"] >= 1),
    ("ten_h", "⏱️", "10 timer", "10 timer spilt", lambda f: f["total_h"] >= 10),
    ("hundred_h", "💯", "100 timer", "100 timer spilt", lambda f: f["total_h"] >= 100),
    ("marathon", "🏃", "Maraton", "En økt på 3 timer eller mer", lambda f: f["longest"] >= 180),
    ("night", "🦉", "Nattugle", "Spilt etter midnatt", lambda f: f["night"]),
    ("early", "🌅", "Morgenfugl", "Spilt før kl. 7", lambda f: f["early"]),
    ("streak", "🔥", "På rad", "Spilt 7 dager på rad", lambda f: f["streak"] >= 7),
    ("explorer", "🧭", "Utforsker", "Spilt 10 forskjellige spill", lambda f: f["games"] >= 10),
    ("clipper", "🎬", "Regissør", "10 klipp lagret", lambda f: f["clips"] >= 10),
    ("cool", "🧊", "Kald hjerne", "30 min spill med skjermkortet under 65 °C", lambda f: f["cool"]),
    ("themes", "🎨", "Stilikon", "Prøvd 5 temaer", lambda f: f["themes"] >= 5),
    ("scenes", "✨", "Regissør av rommet", "Laget din egen scene", lambda f: f["scenes"] >= 1),
    ("vr", "🥽", "Inn i VR", "Startet VR fra Kontrollsenter", lambda f: f["vr"]),
    ("homework", "📚", "Lekse-helt", "5 mål godkjent", lambda f: f["homework"] >= 5),
    ("stars", "⭐", "Stjernesamler", "20 stjerner samlet", lambda f: f["stars"] >= 20),
]


def _state():
    try:
        return json.load(open(DATA))
    except (OSError, ValueError):
        return {}


def achievements():
    """[{id, icon, name, desc, unlocked: tid|None}]"""
    st = _state()
    return [{"id": a[0], "icon": a[1], "name": a[2], "desc": a[3], "unlocked": st.get(a[0])} for a in ACH]


def check(notify=None):
    """Lås opp nye prestasjoner. Returnerer de nye."""
    st = _state()
    try:
        f = _facts()
    except Exception:  # noqa: BLE001
        return []
    new = []
    for aid, icon, name, desc, test in ACH:
        if aid in st:
            continue
        try:
            ok = test(f)
        except Exception:  # noqa: BLE001
            ok = False
        if ok:
            st[aid] = time.time()
            new.append((icon, name, desc))
    if new:
        os.makedirs(os.path.dirname(DATA), exist_ok=True)
        with open(DATA, "w") as fh:
            json.dump(st, fh)
        if notify:
            for icon, name, desc in new[:3]:
                notify("goal", f"🏆 Ny prestasjon: {icon} {name}", desc)
    return new
