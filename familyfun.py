"""Familie+ (runde 3): belønning for gjøremål, leggetid som trapper ned, hvem er på nå, fri fra lekser, ukens
oppsummering til barna, familiekonkurranse, «Middag!» som trapper opp, spillkø, husprestasjoner, pausevarsel og
bursdager.

  4  Gjøremål i ukeplanen kan krysses av → stjerner og ekstra spilletid (godkjennes av en voksen i appen)
  5  Leggetid som trapper ned: 30 min før nattlys + varm RGB + beskjed, 15 min før lavere lyd, 5 min før «lagre nå»
  18 Hvem er på nå (mobilen): hver PC med spill og spilletid i dag – «Gi 30 min» og «Pause nå»
  35 Leksetid med unntak: «Fri i dag» (f.eks. fredag) med ett trykk
  36 Ukens oppsummering til barna søndag: spilletid, mest spilt, stjerner og en utfordring for neste uke
  37 Familiekonkurranse: stjerner + dager under spilletiden denne uka, med premie
  38 «Middag!» trapper opp: etter 5 min dempes lyden og RGB blinker på PC-ene
  43 Spillkø på én PC: hvem som står for tur, med tid og beskjed når det er din tur
  48 Husprestasjoner: felles mål for hele huset
  55 Pausevarsel etter 3 timer sammenhengende spilling (på som standard der familiekontroll er på)
  70 Bursdager: konfetti, bursdagsfarger på RGB og ekstra spilletid i gave
"""
import json
import os
import random
import threading
import time

CFG = os.path.expanduser("~/.config/systemmonitor/familie-pluss.json")
DEF = {"birthdays": [], "bday_minutes": 60, "prize": "", "queue": [], "break_h": 3, "break_on": None,
       "winddown": True, "chores_reward": 15, "done": {}}
CHALLENGES = ["Spill 30 min mindre enn denne uka", "Fullfør ett gjøremål hver dag", "Prøv et spill du ikke har "
              "spilt på lenge", "Hjelp til med middagen to ganger", "Gå tur uten mobil i 30 min", "Lær bort et spill "
              "til noen i familien", "Les 15 min hver kveld", "Ingen skjerm etter leggetid hele uka"]
_STATE = {"dinner": None, "winddown": {}, "break": {}, "kids": None, "bday": None}


def cfg():
    try:
        d = json.load(open(CFG))
    except (OSError, ValueError):
        d = {}
    return {**DEF, **d}


def save(d):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    json.dump(d, open(CFG, "w"), ensure_ascii=False, indent=1)


def set_(**kw):
    d = cfg()
    d.update(kw)
    save(d)
    return d


def _ev(kind, title, body="", level="info"):
    try:
        import remote_extra
        remote_extra.event(kind, title, body, level)
    except Exception:  # noqa: BLE001
        pass


def _ingame(text, secs=30):
    try:
        import familysafe
        familysafe.ingame(text, secs)
    except Exception:  # noqa: BLE001
        pass


def _me():
    import savegames
    return savegames.pc_name()


def _locked():
    try:
        import familylock
        return familylock.locked()
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------
# 4 – gjøremål → stjerner og ekstra tid
# --------------------------------------------------------------------------
def chore_done(item_id, by=None):
    """Barnet krysser av et gjøremål fra ukeplanen → forespørsel til en voksen (godkjennes i appen)."""
    import familyplus
    import features
    item = next((x for x in familyplus.load_plan()["items"] if x["id"] == item_id), None)
    if not item:
        raise ValueError("fant ikke gjøremålet")
    day = time.strftime("%Y-%m-%d")
    d = cfg()
    if d["done"].get(item_id) == day:
        return "Allerede krysset av i dag"
    d["done"][item_id] = day
    d["done"] = {k: v for k, v in d["done"].items() if v == day}
    save(d)
    c = features.cfg()
    reqs = c.setdefault("goal_reqs", [])
    rid = f"{int(time.time())}-chore"
    reqs.append({"id": rid, "goal": "chore:" + item_id, "name": item["text"], "icon": "✅",
                 "minutes": int(d["chores_reward"]), "by": str(by or _me())[:40], "pc": _me(), "t": time.time(),
                 "state": "venter"})
    c["goal_reqs"] = reqs[-40:]
    features.save_cfg(c)
    _ev("goal", f"✅ {_me()}: {item['text']}", f"Ferdig – ber om {d['chores_reward']} min og stjerner. "
                                               "Godkjenn i appen.", "warn")
    return f"Sendt til en voksen – {d['chores_reward']} min og stjerner når det er godkjent"


def chores_today():
    import familyplus
    day = time.strftime("%Y-%m-%d")
    done = cfg()["done"]
    return [{**x, "done": done.get(x["id"]) == day} for x in familyplus.today_items()]


# --------------------------------------------------------------------------
# 5 – leggetid som trapper ned
# --------------------------------------------------------------------------
def winddown_tick(win):
    import features
    b = features.cfg().get("bedtime") or {}
    if not b.get("enabled") or not cfg()["winddown"]:
        return
    wd = time.localtime().tm_wday
    when = b.get("weekend") if wd in (4, 5) else b.get("weekday")
    try:
        hh, mm = map(int, str(when).split(":"))
    except ValueError:
        return
    lt = time.localtime()
    mins = (hh * 60 + mm) - (lt.tm_hour * 60 + lt.tm_min)
    key = time.strftime("%Y-%m-%d")
    st = _STATE["winddown"].setdefault(key, set())
    if mins == 30 and 30 not in st:
        st.add(30)
        _ingame(f"🌙 Leggetid om 30 min (kl. {when}) – fin tid å runde av", 40)
        try:                                               # nattlys og varmt lys
            import avprofiles
            avprofiles.set_night(True)
        except Exception:  # noqa: BLE001
            pass
        _rgb(win, "#ff8a3d")
    elif mins == 15 and 15 not in st:
        st.add(15)
        _volume_step(win, -20)
    elif mins == 5 and 5 not in st:
        st.add(5)
        _ingame("💾 Lagre spillet nå – PC-en slås av om 5 minutter", 60)


def _rgb(win, color):
    try:
        import remote
        remote.do_action(win, {"a": "rgb", "mode": "color", "color": color})
    except Exception:  # noqa: BLE001
        pass


def _volume_step(win, delta):
    try:
        import remote
        cur = (remote.audio_state(win) or {}).get("volume")
        if cur is not None:
            remote.do_action(win, {"a": "volume", "volume": int(max(5, min(100, int(cur) + delta)))})
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------
# 35 – fri fra leksetid i dag
# --------------------------------------------------------------------------
def school_free_today(on=True):
    import familysafe
    c = familysafe._fcfg()
    s = {**familysafe.DEFAULT_SCHOOL, **(c.get("school") or {})}
    s["free_day"] = time.strftime("%Y-%m-%d") if on else ""
    c["school"] = s
    familysafe._fsave(c)
    _ev("playtime", "📚 Fri fra leksetid i dag" if on else "Leksetid som vanlig i dag", "", "info")
    return "Fri fra leksetid i dag ✓" if on else "Leksetid som vanlig"


def is_free_today():
    try:
        import familysafe
        return familysafe.school_cfg().get("free_day") == time.strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------
# 36 / 37 – ukens oppsummering og familiekonkurranse
# --------------------------------------------------------------------------
def my_week():
    """Denne PC-ens uke: spilletid, mest spilt, stjerner, dager under spilletiden."""
    import remote_extra
    import familyplus
    data = remote_extra._play_data()
    days = [time.strftime("%Y-%m-%d", time.localtime(time.time() - i * 86400)) for i in range(7)]
    games = {}
    under = 0
    lim = remote_extra.limit_cfg()
    for d in days:
        g = data.get(d, {})
        tot = sum(g.values())
        for k, v in g.items():
            games[k] = games.get(k, 0) + v
        if lim.get("enabled"):
            wd = time.strptime(d, "%Y-%m-%d").tm_wday
            limit_h = lim["weekend"] if wd >= 5 else lim["weekday"]
            if tot <= float(limit_h) * 3600:
                under += 1
    week_ago = time.time() - 7 * 86400
    stars_week = sum(x.get("n", 0) for x in (familyplus._fc().get("stars_log") or [])
                     if x.get("t", 0) > week_ago and x.get("n", 0) > 0)
    top = sorted(games.items(), key=lambda kv: -kv[1])
    return {"name": _me(), "play_s": sum(games.values()), "top": top[:3], "stars": familyplus.stars(),
            "stars_week": stars_week, "under_days": under if lim.get("enabled") else None,
            "points": stars_week + under * 3}


def status_fields():
    try:
        w = my_week()
        return {"fam_points": w["points"], "fam_stars_week": w["stars_week"], "fam_under": w["under_days"]}
    except Exception:  # noqa: BLE001
        return {}


def leaderboard():
    """[(navn, poeng, stjerner, dager under)] for alle PC-ene i huset denne uka."""
    rows = []
    try:
        w = my_week()
        rows.append((w["name"], w["points"], w["stars_week"], w["under_days"]))
    except Exception:  # noqa: BLE001
        pass
    try:
        import homepcs
        for p in homepcs.fetch() or []:
            if p.get("name") != _me() and p.get("fam_points") is not None:
                rows.append((p["name"], p["fam_points"], p.get("fam_stars_week", 0), p.get("fam_under")))
    except Exception:  # noqa: BLE001
        pass
    rows.sort(key=lambda r: -r[1])
    return rows


def kids_summary_text():
    w = my_week()
    h, m = divmod(int(w["play_s"]) // 60, 60)
    top = ", ".join(f"{n} ({int(s) // 3600} t {int(s) % 3600 // 60} min)" for n, s in w["top"]) or "ingen spill"
    lb = leaderboard()
    place = next((i + 1 for i, r in enumerate(lb) if r[0] == w["name"]), None)
    ch = random.Random(time.strftime("%Y-%W")).choice(CHALLENGES)
    return (f"Denne uka spilte du {h} t {m} min. Mest: {top}. Du fikk {w['stars_week']} ⭐ og holdt deg under "
            f"spilletiden {w['under_days'] or 0} av 7 dager." + (f" Du er nr. {place} i familiekonkurransen!" if place and
                                                             len(lb) > 1 else "") + f"\n\nUkens utfordring: {ch}")


def kids_weekly_tick(win):
    lt = time.localtime()
    if lt.tm_wday != 6 or lt.tm_hour < 18:
        return
    wk = time.strftime("%Y-%W")
    d = cfg()
    if d.get("kids_sent") == wk:
        return
    d["kids_sent"] = wk
    save(d)
    txt = kids_summary_text()
    bg = getattr(win, "bg", None)
    if bg:
        from gi.repository import GLib
        GLib.idle_add(lambda: (bg.notify("weekly", "🏆 Uka di", txt, force=True), False)[1])
    _ingame("🏆 Uka di er klar – se varselet", 20)


# --------------------------------------------------------------------------
# 38 – «Middag!» som trapper opp
# --------------------------------------------------------------------------
def dinner_sent():
    _STATE["dinner"] = time.time()


def dinner_step2(win):
    """5 min etter «Middag!»: lavere lyd og blinkende RGB (på denne PC-en)."""
    _volume_step(win, -40)
    for i in range(6):
        _rgb(win, "#ff2a2a" if i % 2 == 0 else "#000000")
        time.sleep(0.6)
    _rgb(win, "#ff8a3d")
    _ingame("🍽️ MIDDAG! Kom nå 😄", 40)


def dinner_tick(win):
    t = _STATE["dinner"]
    if t and time.time() - t >= 300:
        _STATE["dinner"] = None
        import homepcs
        for p in homepcs.fetch() or []:
            if p.get("name") != _me() and time.time() - (p.get("time") or 0) < homepcs.STALE:
                homepcs.house_call(p, "family", 15, do="dinner2")


# --------------------------------------------------------------------------
# 43 – spillkø
# --------------------------------------------------------------------------
def queue():
    return cfg()["queue"]


def queue_add(name, minutes=30):
    d = cfg()
    q = d["queue"]
    q.append({"name": str(name)[:30], "minutes": max(5, min(240, int(minutes))), "start": None})
    if len(q) == 1:
        q[0]["start"] = time.time()
    save(d)
    return q


def queue_next():
    d = cfg()
    q = d["queue"]
    if q:
        q.pop(0)
    if q:
        q[0]["start"] = time.time()
    save(d)
    return q


def queue_clear():
    set_(queue=[])


def queue_tick(win):
    q = queue()
    if not q or not q[0].get("start"):
        return
    cur = q[0]
    left = cur["start"] + cur["minutes"] * 60 - time.time()
    nxt = q[1]["name"] if len(q) > 1 else None
    key = (cur["name"], cur["start"])
    st = _STATE.setdefault("queue", {}).setdefault(key, set())
    if 0 < left <= 300 and 5 not in st:
        st.add(5)
        _ingame(f"⏳ 5 min igjen for {cur['name']}" + (f" – så er det {nxt} sin tur" if nxt else ""), 40)
    if left <= 0 and 0 not in st:
        st.add(0)
        msg = f"⏰ Tiden er ute for {cur['name']}" + (f" – nå er det {nxt} sin tur!" if nxt else "")
        _ingame(msg, 60)
        bg = getattr(win, "bg", None)
        if bg:
            from gi.repository import GLib
            GLib.idle_add(lambda: (bg.notify("playlimit", "Spillkø", msg, force=True), False)[1])
        queue_next()


# --------------------------------------------------------------------------
# 48 – husprestasjoner
# --------------------------------------------------------------------------
def house_achievements():
    """[(ikon, tittel, oppnådd, fremdrift-tekst)]"""
    out = []
    lb = leaderboard()
    try:
        import homepcs
        pcs = homepcs.fetch() or []
        week_play = sum(p.get("play_week_s") or 0 for p in pcs)
    except Exception:  # noqa: BLE001
        pcs, week_play = [], 0
    h = week_play / 3600
    out.append(("🎮", "100 timer spilt i huset på en uke", h >= 100, f"{h:.0f} av 100 t"))
    lim = [r for r in lb if r[3] is not None]
    if lim:                                              # bare der spilletidsgrense er på
        out.append(("🧘", "Alle under spilletiden en hel uke", all(r[3] >= 7 for r in lim),
                    ", ".join(f"{r[0]} {r[3]}/7" for r in lim[:4])))
    stars = sum(r[2] for r in lb)
    out.append(("⭐", "50 stjerner i huset på en uke", stars >= 50, f"{stars} av 50"))
    try:
        import applog
        same = pcs and all(p.get("version") == applog.RUNNING for p in pcs)
    except Exception:  # noqa: BLE001
        same = False
    out.append(("🔄", "Alle PC-ene oppdatert", bool(same), f"{len(pcs)} PC-er"))
    try:
        import crashlog
        month = [e for e in crashlog.history() if time.time() - (e.get("t") or 0) < 30 * 86400]
        out.append(("🛡️", "En måned uten krasj", not month, f"{len(month)} krasj siste 30 dager"))
    except Exception:  # noqa: BLE001
        pass
    return out


# --------------------------------------------------------------------------
# 55 – pausevarsel
# --------------------------------------------------------------------------
def break_on():
    v = cfg()["break_on"]
    return _locked() if v is None else bool(v)


def break_tick(win):
    if not break_on():
        return
    sess = getattr(getattr(getattr(win, "bg", None), "auto", None), "session", None)
    if not sess:
        return
    hrs = (time.time() - sess.start) / 3600
    step = int(hrs // cfg()["break_h"])
    if step >= 1 and _STATE["break"].get(sess.start, 0) < step:
        _STATE["break"][sess.start] = step
        _ingame(f"🥤 Du har spilt i {hrs:.0f} timer – ta en pause: strekk på deg og drikk vann", 45)


# --------------------------------------------------------------------------
# 70 – bursdager
# --------------------------------------------------------------------------
def birthday_today():
    """Navnet som har bursdag i dag (og hører til denne PC-en eller alle), ellers None."""
    md = time.strftime("%m-%d")
    for b in cfg()["birthdays"]:
        if str(b.get("date", ""))[-5:] == md and b.get("pc") in (None, "", "*", _me()):
            return b.get("name")
    return None


def birthday_tick(win):
    name = birthday_today()
    day = time.strftime("%Y-%m-%d")
    if not name or _STATE["bday"] == day:
        return
    d = cfg()
    if d.get("bday_given") == day:
        _STATE["bday"] = day
        return
    _STATE["bday"] = day
    d["bday_given"] = day
    save(d)
    try:
        import features
        features.give_bonus(int(d["bday_minutes"]))
    except Exception:  # noqa: BLE001
        pass
    for col in ("#ff3d7f", "#ffd23d", "#3dd6ff", "#9b3dff"):
        _rgb(win, col)
        time.sleep(0.8)
    from gi.repository import GLib
    GLib.idle_add(lambda: (_confetti(win, name), False)[1])
    _ev("game", f"🎂 Gratulerer med dagen, {name}!", f"{d['bday_minutes']} min ekstra spilletid i gave", "game")


def _confetti(win, name):
    try:
        import familyfun_ui
        familyfun_ui.confetti(win, name, cfg()["bday_minutes"])
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------
# Hvem er på nå (18) og handlinger fra en annen PC / mobilen
# --------------------------------------------------------------------------
def house_action(win, what, **q):
    """Fra /api/house/family (husnøkkel): bonus, pause, dinner2."""
    if what == "bonus":
        import features
        features.give_bonus(int(q.get("min", 30)))
        _ingame(f"🎁 Du fikk {q.get('min', 30)} min ekstra spilletid!", 30)
        return f"{q.get('min', 30)} min ekstra"
    if what == "pause":
        import familysafe
        _ingame("⏸️ Pause – en voksen ba om det", 30)
        time.sleep(3)
        name = familysafe.close_game()
        _ev("playtime", "⏸️ Pause fra mobilen", name or "", "warn")
        return f"Pause – {name} lukket" if name else "Pause (ingen spill kjørte)"
    if what == "dinner2":
        threading.Thread(target=dinner_step2, args=(win,), daemon=True).start()
        return "OK"
    raise ValueError("ukjent")


def who_is_on():
    """[{name, game, play_s, online}] for alle PC-ene (inkludert denne)."""
    import homepcs
    out = []
    for p in homepcs.fetch() or []:
        on = time.time() - (p.get("time") or 0) < homepcs.STALE
        out.append({"name": p.get("name"), "game": p.get("game"), "play_s": p.get("play_s") or 0, "online": on})
    out.sort(key=lambda x: (not x["online"], not x["game"], x["name"] or ""))
    return out


def tick(win):
    for fn in (winddown_tick, kids_weekly_tick, dinner_tick, queue_tick, break_tick, birthday_tick):
        try:
            fn(win)
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("familie+: %s", fn.__name__)
