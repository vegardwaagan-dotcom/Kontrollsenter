"""Familie: felles ukeplan på NAS-en med påminnelser, og belønningsbutikk med stjerner.

Ukeplanen ligger i Kontrollsenter/Familie/ukeplan.json på NAS-en – alle PC-ene leser den, og hver PC varsler om
avtalene som gjelder den (eller alle) et valgfritt antall minutter før. Endringer skrives tilbake til NAS-en.

Stjerner: hvert godkjente mål gir stjerner (1 per 5 minutter målet er verdt). Stjernene kan løses inn i butikken mot
f.eks. ekstra spilletid eller å velge middag. Alt som løses inn må godkjennes av en voksen (familiekoden eller appen).
"""
import json
import os
import shutil
import tempfile
import threading
import time

DAYS = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"]
_CACHE = {"t": 0, "plan": None}
_LOCK = threading.Lock()


# --------------------------------------------------------------------------
# Ukeplan
# --------------------------------------------------------------------------
def _local_copy():
    return os.path.expanduser("~/.cache/systemmonitor/ukeplan.json")


def load_plan(max_age=600):
    """Ukeplanen ({"items": [...]}) – fra NAS-en, med lokal kopi når NAS-en ikke svarer."""
    if _CACHE["plan"] is not None and time.time() - _CACHE["t"] < max_age:
        return _CACHE["plan"]
    plan = None
    try:
        import lanupdate as L
        if L.on_lan():
            d = tempfile.mkdtemp()
            try:
                L._smb(f'cd "Familie"; get "ukeplan.json" "{d}/p.json"', 30)
                with open(f"{d}/p.json") as f:
                    plan = json.load(f)
            except Exception:  # noqa: BLE001
                plan = None
            finally:
                shutil.rmtree(d, ignore_errors=True)
    except Exception:  # noqa: BLE001
        pass
    if plan is None:
        try:
            with open(_local_copy()) as f:
                plan = json.load(f)
        except (OSError, ValueError):
            plan = {"items": []}
    else:
        os.makedirs(os.path.dirname(_local_copy()), exist_ok=True)
        with open(_local_copy(), "w") as f:
            json.dump(plan, f, ensure_ascii=False)
    plan.setdefault("items", [])
    _CACHE.update(t=time.time(), plan=plan)
    return plan


def _save_plan(plan):
    import lanupdate as L
    if not L.on_lan():
        raise RuntimeError("NAS-en svarer ikke – ukeplanen kan bare endres hjemme")
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "ukeplan.json")
        with open(p, "w") as f:
            json.dump(plan, f, ensure_ascii=False, indent=1)
        _h, _s, folder = L._split()
        L.smb_mkdir(f"{folder}/Familie")
        L._smb(f'cd "Familie"; put "{p}" "ukeplan.json"', 30)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    _CACHE.update(t=time.time(), plan=plan)
    with open(_local_copy(), "w") as f:
        json.dump(plan, f, ensure_ascii=False)


def plan_add(day, at, text, who="*", remind=10):
    if not (0 <= int(day) <= 6) or not text.strip():
        raise ValueError("velg dag og skriv hva det gjelder")
    hh, mm = (int(x) for x in str(at).split(":"))
    if not (0 <= hh < 24 and 0 <= mm < 60):
        raise ValueError("ugyldig klokkeslett")
    with _LOCK:
        plan = load_plan(0)
        import savegames
        plan["items"].append({"id": f"{int(time.time() * 1000)}", "day": int(day), "at": f"{hh:02d}:{mm:02d}",
                              "text": text.strip()[:80], "who": str(who or "*")[:40], "remind": int(remind),
                              "by": savegames.pc_name()})
        plan["items"].sort(key=lambda x: (x["day"], x["at"]))
        _save_plan(plan)
    return "Lagt til i ukeplanen ✓"


def plan_del(item_id):
    with _LOCK:
        plan = load_plan(0)
        plan["items"] = [x for x in plan["items"] if x["id"] != item_id]
        _save_plan(plan)
    return "Fjernet"


def for_me(item):
    import savegames
    return item.get("who", "*") in ("*", "", savegames.pc_name())


_REMINDED = {}


def plan_tick(notify):
    """Påminnelser: kalles jevnlig fra bakgrunnen."""
    lt = time.localtime()
    now_min = lt.tm_hour * 60 + lt.tm_min
    try:
        plan = load_plan()
    except Exception:  # noqa: BLE001
        return
    day_key = time.strftime("%Y-%m-%d")
    for x in plan["items"]:
        if x["day"] != lt.tm_wday or not for_me(x):
            continue
        hh, mm = (int(v) for v in x["at"].split(":"))
        at = hh * 60 + mm
        if 0 <= at - now_min <= int(x.get("remind", 10)) and _REMINDED.get(x["id"]) != day_key:
            _REMINDED[x["id"]] = day_key
            left = at - now_min
            notify("plan", f"🗓️ {x['text']} kl. {x['at']}",
                   "Nå!" if left <= 0 else f"Om {left} min" + (" – lagre spillet 🎮" if left <= 15 else ""),
                   force=True)


def today_items():
    lt = time.localtime()
    return [x for x in load_plan()["items"] if x["day"] == lt.tm_wday and for_me(x)]


# --------------------------------------------------------------------------
# Stjerner og belønningsbutikk
# --------------------------------------------------------------------------
SHOP = [{"id": "spill30", "name": "30 min ekstra spilletid", "icon": "🎮", "price": 6, "minutes": 30},
        {"id": "spill60", "name": "1 time ekstra spilletid", "icon": "🕹️", "price": 11, "minutes": 60},
        {"id": "middag", "name": "Velge middag", "icon": "🍕", "price": 10},
        {"id": "film", "name": "Velge film på filmkveld", "icon": "🎬", "price": 8},
        {"id": "sent", "name": "Være oppe 30 min lenger i helgen", "icon": "🌙", "price": 15},
        {"id": "kjop", "name": "Kjøp i spill (avtales med en voksen)", "icon": "💎", "price": 40}]


def _fc():
    import features
    return features.cfg()


def _fsave(c):
    import features
    features.save_cfg(c)


def stars():
    return int(_fc().get("stars", 0))


def add_stars(n, why=""):
    c = _fc()
    c["stars"] = max(0, int(c.get("stars", 0)) + int(n))
    log = c.setdefault("stars_log", [])
    log.append({"t": time.time(), "n": int(n), "why": why[:60]})
    c["stars_log"] = log[-40:]
    _fsave(c)
    return c["stars"]


def shop():
    c = _fc()
    return {"stars": int(c.get("stars", 0)), "items": c.get("shop") or SHOP,
            "pending": [r for r in c.get("shop_reqs", []) if r["state"] == "venter"],
            "log": (c.get("stars_log") or [])[-8:]}


def shop_request(item_id, by="PC-en"):
    it = next((x for x in shop()["items"] if x["id"] == item_id), None)
    if not it:
        raise ValueError("finnes ikke i butikken")
    c = _fc()
    have = int(c.get("stars", 0)) - sum(r["price"] for r in c.get("shop_reqs", []) if r["state"] == "venter")
    if have < it["price"]:
        raise ValueError(f"du trenger {it['price']} ⭐ (har {max(0, have)})")
    import savegames
    reqs = c.setdefault("shop_reqs", [])
    reqs.append({"id": f"{int(time.time())}-{item_id}", "item": item_id, "name": it["name"], "icon": it["icon"],
                 "price": it["price"], "minutes": it.get("minutes"), "by": str(by)[:40], "pc": savegames.pc_name(),
                 "t": time.time(), "state": "venter"})
    c["shop_reqs"] = reqs[-40:]
    _fsave(c)
    try:
        import features
        features._ev("goal", f"{it['icon']} {savegames.pc_name()} vil løse inn: {it['name']}",
                     f"{it['price']} ⭐ – godkjenn i appen eller på PC-en", "warn")
    except Exception:  # noqa: BLE001
        pass
    return f"Sendt til en voksen for godkjenning ({it['price']} ⭐)"


def shop_answer(rid, ok):
    c = _fc()
    r = next((x for x in c.get("shop_reqs", []) if x["id"] == rid), None)
    if not r or r["state"] != "venter":
        raise ValueError("forespørselen finnes ikke lenger")
    if ok and int(c.get("stars", 0)) < r["price"]:
        raise ValueError("ikke nok stjerner lenger")
    r["state"] = "godkjent" if ok else "avslått"
    _fsave(c)
    if ok:
        add_stars(-r["price"], r["name"])
        if r.get("minutes"):
            import features
            features.give_bonus(r["minutes"])
    return f"{r['name']}: " + ("godkjent ✓" if ok else "avslått")
