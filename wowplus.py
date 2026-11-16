"""WoW-ekstra: varsel ved hvisking, oversikt over karakterene, bagsøk, questlogg, gull over tid, raid-låser,
yrker, reparasjonsvarsel og WoW-skjermbilder i Kontrollsenter.

Alt bygger på det addonen «Kontrollsenter Stats» lagrer (vanlige addon-funksjoner) og filer WoW selv skriver
(chatloggen og skjermbildene). Ingenting styrer spillet, leser minnet eller sender noe inn i WoW.
Hver funksjon – og alt samlet – kan slås av.
"""
import glob
import json
import os
import re
import shutil
import threading
import time

FEATURES = [
    ("chat", "Varsel ved hvisking", "Hvisking, gruppeinvitasjon og guild-meldinger som nevner deg – på telefonen"),
    ("alts", "Oversikt over karakterene", "Level, gull, hvor de er og uthvilt XP"),
    ("bags", "Søk i bagger og bank", "Hva som ligger hvor, på alle karakterene (banken leses når du åpner den)"),
    ("quests", "Questloggen", "Aktive quester med fremdrift"),
    ("gold", "Gull over tid", "Graf over gullet per karakter"),
    ("locks", "Raid- og dungeon-låser", "Hvilke instanser du er låst til og når de nullstilles"),
    ("profs", "Yrker", "Nivå per yrke, fremgang og varsel når du må lære neste nivå"),
    ("durability", "Reparasjonsvarsel", "Varsel når utstyret er nesten ødelagt"),
    ("shots", "WoW-skjermbilder", "Skjermbildene fra WoW kommer i skjermbildene i Kontrollsenter"),
    ("sheet", "Egenskaper og talenter", "Armor, Strength, Intellect …, talentfordeling og hva du bør ha mer av"),
]
KEYS = [k for k, _n, _d in FEATURES]
STATE = os.path.expanduser("~/.local/share/systemmonitor/wowplus-tilstand.json")
REST_RATE = 5.0           # % av en level per 8 timer uthvilt på vertshus/i by (1/4 ute i verden)
REST_CAP = 150.0          # maks uthvilt: halvannen level


# --------------------------------------------------------------------------
# innstillinger
# --------------------------------------------------------------------------
def cfg():
    import gamestats
    c = gamestats._load_cfg().get("wowplus") or {}
    return {"on": c.get("on", True), "f": {k: bool((c.get("f") or {}).get(k, True)) for k in KEYS}}


def enabled(key=None):
    c = cfg()
    return c["on"] and (key is None or c["f"].get(key, True))


def set_option(feature=None, on=True):
    """feature=None: hovedbryteren for alle WoW-funksjonene."""
    import gamestats
    allc = gamestats._load_cfg()
    c = cfg()
    if feature is None:
        c["on"] = bool(on)
    elif feature in KEYS:
        c["f"][feature] = bool(on)
    else:
        raise ValueError("ukjent WoW-funksjon")
    allc["wowplus"] = c
    gamestats._save_cfg(allc)
    write_config()
    return c


def write_config():
    """Fortell addonen hva den skal samle (gjelder etter /reload i spillet)."""
    import gamestats
    c = cfg()
    body = "-- Skrevet av Kontrollsenter – endres under Spill → World of Warcraft.\nKS_CONFIG = {\n"
    body += f"  on = {'true' if c['on'] else 'false'},\n"
    body += "".join(f"  {k} = {'true' if c['f'][k] else 'false'},\n" for k in KEYS) + "}\n"
    for _root, d, _name, _iface in gamestats.wow_flavors():
        p = os.path.join(d, "Interface", "AddOns", "KontrollsenterStats", "KontrollsenterConfig.lua")
        try:
            if os.path.isdir(os.path.dirname(p)):
                old = open(p, encoding="utf-8").read() if os.path.exists(p) else None
                if old != body:
                    with open(p, "w", encoding="utf-8") as f:
                        f.write(body)
        except OSError:
            pass


def _state():
    try:
        with open(STATE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(d):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f)
    os.replace(tmp, STATE)


def _event(title, body=""):
    try:
        import remote_extra
        remote_extra.event("wow", title, body, "game")
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------
# utregninger for visning
# --------------------------------------------------------------------------
def rested(c, now=None):
    """(prosent av en level nå, timer til fullt) – eller None (maks level / ukjent)."""
    xp_max, r = c.get("xp_max") or 0, c.get("rested")
    if not xp_max or r is None or not c.get("last_seen"):
        return None
    hours = max(0.0, ((now or time.time()) - c["last_seen"]) / 3600)
    rate = REST_RATE / 8 * (1 if c.get("resting") else 0.25)            # % per time
    pct = min(REST_CAP, r / xp_max * 100 + hours * rate)
    full = 0 if pct >= REST_CAP else (REST_CAP - pct) / rate
    return round(pct), round(full, 1)


def _profs(c):
    p = c.get("profs") or {}
    if not isinstance(p, dict):
        return []
    main = [(n, v) for n, v in p.items() if isinstance(v, dict) and str(v.get("cat") or "").lower() in
            ("professions", "secondary skills", "yrker", "sekundære ferdigheter", "berufe", "sekundäre fertigkeiten")]
    rows = main or [(n, v) for n, v in p.items() if isinstance(v, dict) and (v.get("max") or 0) >= 75]
    hist = c.get("prof_hist") or {}
    out = []
    for n, v in sorted(rows, key=lambda x: -(x[1].get("rank") or 0)):
        h = hist.get(n) or {}
        pts = sorted((int(k), t) for k, t in (h.items() if isinstance(h, dict) else enumerate(h, 1))
                     if isinstance(t, (int, float)))
        speed = None
        if len(pts) >= 2 and pts[-1][1] > pts[0][1]:
            speed = round((pts[-1][0] - pts[0][0]) / ((pts[-1][1] - pts[0][1]) / 86400), 1)   # nivå per døgn
        out.append({"name": n, "rank": v.get("rank") or 0, "max": v.get("max") or 0, "cat": v.get("cat"),
                    "capped": (v.get("rank") or 0) >= (v.get("max") or 1), "per_day": speed})
    return out


def _quests(c):
    q = c.get("quest_log") or []
    if isinstance(q, dict):
        q = [q[k] for k in sorted(q)]
    return [{"title": x.get("title"), "level": x.get("level"), "zone": x.get("zone"), "done": bool(x.get("done")),
             "obj": [str(o) for o in (x.get("obj") or [])] if isinstance(x.get("obj"), list) else []}
            for x in q if isinstance(x, dict) and x.get("title")]


def _locks(c, now=None):
    now = now or time.time()
    ls = c.get("locks") or []
    if isinstance(ls, dict):
        ls = list(ls.values())
    return [{"name": x.get("name"), "reset_at": x.get("reset_at")} for x in ls
            if isinstance(x, dict) and (x.get("reset_at") or 0) > now]


def _gold(c):
    h = c.get("gold_hist") or []
    if isinstance(h, dict):
        h = [h[k] for k in sorted(h)]
    return [[x.get("t"), x.get("g")] for x in h if isinstance(x, dict) and x.get("t")][-60:]


def details(c):
    """Ekstra for én karakter (bare det som er slått på)."""
    if not enabled():
        return None
    f, d = cfg()["f"], {}
    if f["alts"]:
        r = rested(c)
        d["rested"] = {"pct": r[0], "full_h": r[1], "resting": bool(c.get("resting"))} if r else None
        d["zone"] = " – ".join(x for x in (c.get("zone"), c.get("subzone")) if x) or None
    if f["profs"]:
        d["profs"] = _profs(c)
    if f["quests"]:
        d["quests"] = _quests(c)
    if f["locks"]:
        d["locks"] = _locks(c)
    if f["gold"]:
        d["gold"] = _gold(c)
    if f["durability"] and isinstance(c.get("durability"), dict):
        d["durability"] = c["durability"].get("min")
    if f.get("sheet", True):
        try:
            import wowsheet
            d["sheet"] = wowsheet.analyse(c)
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("wowsheet")
    return d


def overview(chars):
    """Alle karakterene samlet (oversikt + bagsøk)."""
    c = cfg()
    out = {"on": c["on"], "features": c["f"],
           "names": [{"key": k, "name": n, "desc": ds} for k, n, ds in FEATURES], "alts": [], "items": []}
    if not c["on"]:
        return out
    for ch in chars:
        if c["f"]["alts"]:
            r = rested(ch)
            out["alts"].append({"key": ch.get("key"), "name": ch.get("name"), "level": ch.get("level"),
                                "cls": ch.get("class_name"), "class": ch.get("class"), "realm": ch.get("realm"),
                                "gold": ch.get("money"), "zone": ch.get("zone"), "last_seen": ch.get("last_seen"),
                                "rested": r[0] if r else None, "full_h": r[1] if r else None,
                                "resting": bool(ch.get("resting")),
                                "durability": (ch.get("durability") or {}).get("min")
                                if c["f"]["durability"] and isinstance(ch.get("durability"), dict) else None})
        if c["f"]["bags"]:
            for where, key in (("Bagger", "bags"), ("Bank", "bank")):
                items = ch.get(key)
                if isinstance(items, dict):
                    for name, n in items.items():
                        out["items"].append([ch.get("name"), where, str(name), n if isinstance(n, int) else 1])
    out["items"].sort(key=lambda x: (x[2].lower(), x[0] or ""))
    return out


def check(chars):
    """Varsler etter en utlogging/reload: reparer utstyret, lær neste yrkesnivå. Én gang per lagring."""
    if not enabled():
        return
    f = cfg()["f"]
    st = _state()
    seen = st.setdefault("seen", {})
    changed = False
    for c in chars:
        key, ls = c.get("key"), c.get("last_seen") or 0
        if not key or seen.get(key, 0) >= ls:
            continue
        first = key not in seen
        seen[key] = ls
        changed = True
        if first:
            continue                                  # første gang: ikke varsle om gammelt
        dur = (c.get("durability") or {}).get("min") if isinstance(c.get("durability"), dict) else None
        if f["durability"] and dur is not None and dur <= 20:
            _event(f"WoW: {c.get('name')} bør reparere", f"Utstyret er nede i {dur} %")
        if f["profs"]:
            for p in _profs(c):
                if p["capped"] and p["max"] < 300 and str(p.get("cat") or "").lower() in ("professions", "yrker"):
                    _event(f"WoW: {c.get('name')} – {p['name']} {p['rank']}/{p['max']}",
                           "Lær neste nivå hos treneren")
    if changed:
        _save_state(st)


# --------------------------------------------------------------------------
# chatloggen og skjermbildene (bakgrunnstråd)
# --------------------------------------------------------------------------
_LINK = re.compile(r"\|H[^|]*\|h(.*?)\|h")
_COLOR = re.compile(r"\|c[0-9a-fA-F]{8}|\|r")
_TS = re.compile(r"^\d{1,2}/\d{1,2}(?:/\d{2,4})?\s+[\d:.]+\s+(.*)$")
_WHISPER = re.compile(r"^\[?([^\]\s:]+)\]?\s+(?:whispers|flüstert|chuchote|susurra|sussurra)\s*:\s*(.*)$", re.I)
_INVITE = re.compile(r"^\[?([^\]\s]+?)\]?\s+(?:invites you to a group|has invited you to join a group)", re.I)
_GUILD = re.compile(r"^\[(?:Guild|Gilde|Officer)\]\s*\[?([^\]:]+)\]?:\s*(.*)$", re.I)


def parse_chat(line, my_names=()):
    """(tittel, tekst) for linjer som skal varsles, ellers None."""
    m = _TS.match(line.strip())
    s = m.group(1) if m else line.strip()
    s = _COLOR.sub("", _LINK.sub(r"\1", s)).strip()
    s = re.sub(r"\[([^\]-]+)-[^\]]+\]", r"[\1]", s)              # [Navn-Realm] → [Navn]
    if (w := _WHISPER.match(s)):
        return f"WoW: {w.group(1)} hvisker", w.group(2)[:240]
    if (w := _INVITE.match(s)):
        return f"WoW: {w.group(1)} inviterer deg til en gruppe", ""
    if (w := _GUILD.match(s)) and my_names:
        text = w.group(2)
        if any(re.search(rf"\b{re.escape(n)}\b", text, re.I) for n in my_names if n):
            return f"WoW: {w.group(1)} nevnte deg i guild-chatten", text[:240]
    return None


class Watcher:
    def __init__(self):
        self.pos = {}
        self.last_from = {}
        self.names, self.names_t = set(), 0
        self.next_shots = 0

    def _my_names(self):
        if time.time() - self.names_t > 120:
            try:
                import gamestats
                self.names = {c.get("name") for c in gamestats.wow_stats(include_hidden=True) if c.get("name")}
            except Exception:  # noqa: BLE001
                pass
            self.names_t = time.time()
        return self.names

    def chat(self, flavors):
        for _root, d, _n, _i in flavors:
            p = os.path.join(d, "Logs", "WoWChatLog.txt")
            try:
                size = os.path.getsize(p)
            except OSError:
                continue
            if p not in self.pos or size < self.pos[p]:
                self.pos[p] = size                    # start fra slutten: bare nye meldinger
                continue
            if size == self.pos[p]:
                continue
            with open(p, "rb") as f:
                f.seek(self.pos[p])
                data = f.read(min(size - self.pos[p], 512_000))
            cut = data.rfind(b"\n")
            if cut < 0:
                continue
            self.pos[p] += cut + 1
            for line in data[:cut].decode("utf-8", "replace").splitlines():
                hit = parse_chat(line, self._my_names())
                if not hit:
                    continue
                who = hit[0]
                if time.time() - self.last_from.get(who, 0) < 20:
                    continue
                self.last_from[who] = time.time()
                _event(*hit)

    def shots(self, flavors):
        if time.time() < self.next_shots:
            return
        self.next_shots = time.time() + 30
        st = _state()
        since = st.setdefault("shots_since", time.time())
        done = set(st.setdefault("shots_done", []))
        try:
            import clipx
            dst = clipx.C().clip_dir()
        except Exception:  # noqa: BLE001
            return
        new = []
        for _root, d, _n, _i in flavors:
            for f in glob.glob(os.path.join(d, "Screenshots", "*")):
                if not f.lower().endswith((".jpg", ".jpeg", ".png", ".tga")) or f in done:
                    continue
                try:
                    mt = os.path.getmtime(f)
                except OSError:
                    continue
                if mt < since or time.time() - mt < 3:  # gamle bilder hoppes over; vent til fila er skrevet
                    continue
                stamp = time.strftime("%Y-%m-%d %H-%M-%S", time.localtime(mt))
                out = os.path.join(dst, f"World of Warcraft {stamp}.jpg")
                try:
                    os.makedirs(dst, exist_ok=True)
                    if f.lower().endswith((".jpg", ".jpeg")):
                        shutil.copy2(f, out)
                    else:
                        import gi
                        gi.require_version("GdkPixbuf", "2.0")
                        from gi.repository import GdkPixbuf
                        GdkPixbuf.Pixbuf.new_from_file(f).savev(out, "jpeg", ["quality"], ["90"])
                    new.append(f)
                except Exception:  # noqa: BLE001
                    new.append(f)                     # ikke prøv samme fil om og om igjen
        if new or "shots_done" not in st:
            st["shots_done"] = sorted(done | set(new))[-3000:]
            _save_state(st)

    def run(self):
        import gamestats
        flavors, ft = [], 0
        while True:
            try:
                if enabled():
                    if time.time() - ft > 300:
                        flavors, ft = gamestats.wow_flavors(), time.time()
                    if enabled("chat"):
                        self.chat(flavors)
                    if enabled("shots"):
                        self.shots(flavors)
                else:
                    self.pos.clear()                  # start på nytt fra slutten når det slås på igjen
            except Exception:  # noqa: BLE001
                import applog
                applog.log.exception("wowplus")
                time.sleep(30)
            time.sleep(3)


_STARTED = False


def start():
    global _STARTED
    if _STARTED:
        return
    _STARTED = True
    threading.Thread(target=Watcher().run, name="wowplus", daemon=True).start()
