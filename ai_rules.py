"""Automatiske oppgaver som AI-en (eller du) lager: «Si fra hvis GPU-en går over 85 °C mens jeg spiller»,
«Rydd hver søndag kl. 12». Sjekkes av bakgrunnen hvert halve minutt. Lagres i ai-regler.json.

Regel: {id, navn, hvis: cpu_temp|gpu_temp|cpu_load|gpu_load|watt, over|under: tall, spill: bool,
        når: «søn 12:00» / «daglig 08:00», gjør: varsel|handling, tekst, handling: {a: …, …}, sist: tid}
"""
import json
import os
import re
import time

CFG = os.path.expanduser("~/.config/systemmonitor/ai-regler.json")
METRICS = {"cpu_temp": "CPU-temperatur", "gpu_temp": "GPU-temperatur", "cpu_load": "CPU-last",
           "gpu_load": "GPU-last", "watt": "Strømforbruk"}
DAYS = {"man": 0, "tir": 1, "ons": 2, "tor": 3, "fre": 4, "lør": 5, "lor": 5, "søn": 6, "son": 6}


def load():
    try:
        with open(CFG, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def save(rules):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    with open(CFG + ".tmp", "w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=1)
    os.replace(CFG + ".tmp", CFG)


def describe(r):
    if r.get("når"):
        cond = f"hver {r['når']}"
    else:
        op = "over" if "over" in r else "under"
        unit = "°C" if r.get("hvis", "").endswith("temp") else "W" if r.get("hvis") == "watt" else "%"
        cond = f"når {METRICS.get(r.get('hvis'), r.get('hvis'))} er {op} {r.get(op)} {unit}" + \
            (" mens du spiller" if r.get("spill") else "")
    act = (f"varsel «{r.get('tekst') or 'Sjekk PC-en'}»" if r.get("gjør") == "varsel" else
           "handling " + " ".join(f"{k}={v}" for k, v in (r.get("handling") or {}).items()))
    return f"{cond}: {act}"


def add(params):
    """Fra «ks regel ny nøkkel=verdi …». Returnerer regelen."""
    r = {"id": f"r{int(time.time() * 1000) % 10 ** 9}", "sist": 0}
    hand = {}
    for k, v in params.items():
        k = k.lower()
        if k == "hvis" and v in METRICS:
            r["hvis"] = v
        elif k in ("over", "under"):
            r[k] = float(v)
        elif k == "spill":
            r["spill"] = str(v).lower() in ("ja", "1", "true", "yes")
        elif k in ("når", "nar"):
            if not re.match(r"^(daglig|man|tir|ons|tor|fre|lør|lor|søn|son)\w*\s+\d{1,2}:\d\d$", str(v).lower()):
                raise ValueError("når= må være f.eks. «søn 12:00» eller «daglig 08:00»")
            r["når"] = str(v).lower()
        elif k in ("gjør", "gjor"):
            r["gjør"] = "varsel" if v == "varsel" else "handling"
        elif k == "tekst":
            r["tekst"] = str(v)[:120]
        elif k == "navn":
            r["navn"] = str(v)[:60]
        elif k == "handling":
            hand["a"] = str(v)
        else:
            hand[k] = v
    if hand:
        r["handling"] = hand
        r.setdefault("gjør", "handling")
    r.setdefault("gjør", "varsel")
    if not r.get("når") and not (r.get("hvis") and ("over" in r or "under" in r)):
        raise ValueError("regelen trenger enten hvis=… over=/under=… eller når=…")
    if r["gjør"] == "handling" and not (r.get("handling") or {}).get("a"):
        raise ValueError("gjør=handling trenger handling=<navn> (se «ks handlinger»)")
    rules = load()
    rules.append(r)
    save(rules)
    return r


def remove(rid):
    rules = load()
    left = [r for r in rules if r.get("id") != rid]
    save(left)
    return len(rules) != len(left)


def _value(win, metric):
    try:
        import homepcs
        st = homepcs.status(win)
        if metric == "gpu_load":
            nv = win.nvidia.data if getattr(win, "nvidia", None) and win.nvidia.available else {}
            v = (nv or {}).get("util")
        else:
            v = st.get({"cpu_temp": "cpu_t", "gpu_temp": "gpu_t", "cpu_load": "cpu_l", "watt": "watts"}[metric])
        return float(v) if v is not None else None
    except Exception:  # noqa: BLE001
        return None


def tick(win, notify=None):
    """Kalles fra bakgrunnen (hovedtråden). Kjører regler som slår til."""
    rules = load()
    if not rules:
        return
    now = time.time()
    lt = time.localtime(now)
    changed = False
    gaming = bool(getattr(getattr(win, "bg", None), "game_name", None))
    for r in rules:
        fire = False
        if r.get("når"):
            m = re.match(r"^(\w+)\s+(\d{1,2}):(\d\d)$", r["når"])
            if m:
                day = m.group(1)[:3]
                hh, mm = int(m.group(2)), int(m.group(3))
                right_day = day == "dag" or day == "dai" or m.group(1).startswith("daglig") or \
                    DAYS.get(day) == lt.tm_wday
                if right_day and (lt.tm_hour, lt.tm_min) >= (hh, mm) and now - r.get("sist", 0) > 20 * 3600 and \
                        (lt.tm_hour * 60 + lt.tm_min) - (hh * 60 + mm) < 60:
                    fire = True
        elif r.get("hvis"):
            if r.get("spill") and not gaming:
                continue
            v = _value(win, r["hvis"])
            if v is None:
                continue
            hit = (v > r["over"]) if "over" in r else (v < r["under"])
            if hit and now - r.get("sist", 0) > 600:       # høyst hvert 10. minutt
                fire = True
                r["verdi"] = round(v, 1)
        if not fire:
            continue
        r["sist"] = now
        changed = True
        if r.get("gjør") == "varsel":
            if notify:
                extra = f" ({r['verdi']})" if r.get("verdi") is not None else ""
                notify("ai_rule", "🤖 " + (r.get("navn") or "Automatisk oppgave"),
                       (r.get("tekst") or describe(r)) + extra, force=True)
        else:
            try:
                import remote
                remote.do_action(win, {k: v for k, v in (r.get("handling") or {}).items()})
            except Exception:  # noqa: BLE001
                pass
    if changed:
        save(rules)
