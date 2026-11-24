"""Gratis spill denne uken: Epic Games gir bort spill hver uke (offentlig liste, ingen nøkkel eller konto).

Varsler når et nytt gratisspill dukker opp, og poster det i chat-kanalen du har valgt («🎁 Gratis spill hit»).
"""
import json
import os
import time
import urllib.request

URL = ("https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
       "?locale=no&country=NO&allowCountries=NO")
CFG = os.path.expanduser("~/.config/systemmonitor/gratisspill.json")
_C = {"t": 0, "v": None}


def _date(s):
    try:
        return time.mktime(time.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone
    except (TypeError, ValueError):
        return 0


def parse(d):
    """{"now": [...], "soon": [...]} der hvert spill er {"title", "until"/"from", "url"} – bare 100 % rabatt."""
    now, soon = [], []
    for e in (((d.get("data") or {}).get("Catalog") or {}).get("searchStore") or {}).get("elements") or []:
        promo = e.get("promotions") or {}
        maps = ((e.get("catalogNs") or {}).get("mappings") or [{}])
        slug = (maps[0] or {}).get("pageSlug") or e.get("productSlug") or ""
        url = f"https://store.epicgames.com/p/{slug}" if slug else "https://store.epicgames.com/free-games"
        for key, out in (("promotionalOffers", now), ("upcomingPromotionalOffers", soon)):
            for g in promo.get(key) or []:
                for o in g.get("promotionalOffers") or []:
                    if (o.get("discountSetting") or {}).get("discountPercentage") == 0:
                        out.append({"title": e.get("title", "?"), "from": _date(o.get("startDate")),
                                    "until": _date(o.get("endDate")), "url": url})
    for lst in (now, soon):
        seen = set()
        lst[:] = [x for x in sorted(lst, key=lambda x: x["from"]) if not (x["title"] in seen or seen.add(x["title"]))]
    return {"now": now, "soon": soon}


def fetch(force=False):
    if not force and _C["v"] is not None and time.time() - _C["t"] < 6 * 3600:
        return _C["v"]
    req = urllib.request.Request(URL, headers={"User-Agent": "Kontrollsenter"})
    with urllib.request.urlopen(req, timeout=15) as r:
        v = parse(json.load(r))
    _C.update(t=time.time(), v=v)
    return v


def text(v=None):
    v = v or fetch()
    day = lambda t: time.strftime("%d.%m", time.localtime(t)) if t else "?"  # noqa: E731
    lines = [f"🎁 {g['title']} – gratis til {day(g['until'])}" for g in v["now"]]
    lines += [f"⏳ {g['title']} – gratis fra {day(g['from'])}" for g in v["soon"]]
    return "\n".join(lines) or "Ingen gratisspill akkurat nå"


def _seen():
    try:
        with open(CFG) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"on": True, "seen": []}


def tick():
    """Hver 6. time: si fra om nye gratisspill (varsel + chat-kanalen «gratis» om valgt)."""
    c = _seen()
    if not c.get("on", True):
        return []
    try:
        import perf
        if not perf.disk_ok("hendelser"):
            return []
    except Exception:  # noqa: BLE001
        pass
    try:
        v = fetch()
    except Exception:  # noqa: BLE001 – ikke på nett
        return []
    seen = set(c.get("seen", []))
    new = [g for g in v["now"] if g["title"] not in seen]
    for g in new:
        until = time.strftime("%d.%m", time.localtime(g["until"])) if g["until"] else ""
        try:
            import remote_extra
            remote_extra.event("game", f"Gratis spill: {g['title']}", f"Hent det på Epic Games før {until}", "game")
        except Exception:  # noqa: BLE001
            pass
        try:
            import chatvoice
            chatvoice.post_topic("gratis", f"🎁 Gratis nå: {g['title']} (til {until}) {g['url']}")
        except Exception:  # noqa: BLE001
            pass
        seen.add(g["title"])
    if new:
        c["seen"] = sorted(seen)[-200:]
        os.makedirs(os.path.dirname(CFG), exist_ok=True)
        with open(CFG, "w") as f:
            json.dump(c, f)
    return new
