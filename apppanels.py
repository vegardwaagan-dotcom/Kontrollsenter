"""PC-funksjoner for mobilappen – beskrevet som kort som appen tegner av seg selv (samme funksjoner som på PC-en).

Et panel:  {"id", "icon", "title", "desc", "rows": [[navn, verdi]], "items": [ITEM], "buttons": [KNAPP],
            "select": {"label", "options": [[verdi, tekst]], "value", "action": {...}}, "note"}
ITEM:      {"title", "sub", "img", "badge", "buttons": [KNAPP], "detail": {"what": "...", "q": {...}}}
KNAPP:     {"label", "action": {...  sendes til /api/action}, "confirm": "tekst", "primary": bool}

Handlingene går til remote.do_action (kind «panel»), som kaller run() her.
"""
import time


def _safe(fn):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        return {"id": getattr(fn, "__name__", "?").lstrip("_"), "icon": "⚠️", "title": getattr(fn, "__doc__", "")
                or "?", "desc": f"Kunne ikke lastes: {e}"}


def _btn(label, act, confirm=None, primary=False):
    return {"label": label, "action": {"a": "panel", **act}, "confirm": confirm, "primary": primary}


# --------------------------------------------------------------------------
# Hurtigkommandoer (samme som Ctrl+K på PC-en)
# --------------------------------------------------------------------------
def p_commands(win):
    """Hurtigkommandoer"""
    import search
    acts = search.actions(win)
    return {"id": "commands", "icon": "⚡", "title": "Hurtigkommandoer",
            "desc": "Samme som Ctrl+K på PC-en – trykk for å kjøre.", "search": True,
            "items": [{"title": a[0], "sub": "", "buttons": [_btn("Kjør", {"do": "cmd", "label": a[0]})],
                       "tap": {"a": "panel", "do": "cmd", "label": a[0]}} for a in acts]}


def _norm(t):
    import re
    import unicodedata
    t = unicodedata.normalize("NFKC", t.lower())
    return re.sub(r"[^a-z0-9æøå ]+", " ", t).split()


def run_text(win, text):
    """26: «demp lyden», «lagre klipp», «hvor varm er PC-en», «hvem spiller» … → svar eller handling."""
    w = _norm(text)
    s = " ".join(w)
    if any(x in s for x in ("hvor varm", "temperatur", "hvor het")):
        nv = win.nvidia.data if getattr(win, "nvidia", None) and win.nvidia.available else {}
        ct, gt = getattr(win, "_cpu_t", None), (nv or {}).get("temp")
        return f"Prosessoren er {ct:.0f} °C" + (f" og skjermkortet {gt:.0f} °C" if gt is not None else "") if ct \
            else "Vet ikke temperaturen akkurat nå"
    if "hvem" in w and any(x in s for x in ("spiller", "på")):
        import familyfun
        on = [x for x in familyfun.who_is_on() if x["online"]]
        return "; ".join(f"{x['name']}: {x['game'] or 'på'}" for x in on) or "Ingen PC-er er på"
    if any(x in s for x in ("hvorfor treg", "hvorfor hakker", "er pc en treg")):
        import assistant
        return assistant.text_summary(assistant.why_slow(win))
    if "oppdater alt" in s:
        import updates
        return "Oppdater alt er startet" if updates.update_all(win) else "Pågår allerede"
    import search
    best, score = None, 0
    for label, words, fn in search.actions(win):
        keys = set(_norm(label + " " + words))
        hit = sum(1 for x in w if x in keys or any(k.startswith(x) and len(x) >= 4 for k in keys))
        if hit > score:
            best, score = (label, fn), hit
    if not best or score == 0:
        return "Skjønte ikke – prøv f.eks. «demp lyden», «lagre klipp» eller «hvor varm er PC-en»"
    from gi.repository import GLib
    GLib.idle_add(lambda: (best[1](), False)[1])
    return f"{best[0]} ✓"


def run_cmd(win, label):
    import search
    for text, _w, fn in search.actions(win):
        if text == label:
            from gi.repository import GLib
            GLib.idle_add(lambda: (fn(), False)[1])
            return f"{text.split(' ', 1)[-1]} ✓"
    raise ValueError("fant ikke kommandoen")


# --------------------------------------------------------------------------
# Spillene (launcher)
# --------------------------------------------------------------------------
def p_games(win):
    """Spillene"""
    import launcher
    gs = launcher.all_games()
    items = []
    for g in gs[:80]:
        key = f"{g['store']}:{g['id']}"
        items.append({"title": g["name"], "sub": {"steam": "Steam", "lutris": "Lutris"}.get(g["store"], "Heroic"),
                      "img": f"/api/cover?id={key}" if g.get("cover") and not str(g["cover"]).startswith("http") else
                      (g.get("cover") if str(g.get("cover", "")).startswith("http") else None),
                      "buttons": [_btn("▶ Spill", {"do": "launch", "id": key}, primary=True),
                                  _btn("👥 Spill sammen", {"do": "invite", "id": key})]})
    return {"id": "games", "icon": "🎮", "title": "Spillene på PC-en", "desc": "Start et spill på PC-en, eller be "
            "de andre i huset om å bli med.", "items": items, "grid": True, "search": len(items) > 8}


def _game(key):
    import launcher
    store, gid = key.split(":", 1)
    g = next((x for x in launcher.all_games() if x["store"] == store and str(x["id"]) == gid), None)
    if not g:
        raise ValueError("fant ikke spillet")
    return g


def cover_path(key):
    try:
        g = _game(key)
        c = g.get("cover")
        return c if c and not str(c).startswith("http") else None
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------
# PC-er hjemme
# --------------------------------------------------------------------------
def p_homepcs(win):
    """PC-er hjemme"""
    import applog
    import homepcs
    import savegames
    pcs = homepcs.fetch() or []
    me = savegames.pc_name()
    items = []
    for p in pcs:
        on = time.time() - p.get("time", 0) < homepcs.STALE
        bits = [f"CPU {p['cpu_t']:.0f}°" if p.get("cpu_t") is not None else "",
                f"GPU {p['gpu_t']:.0f}°" if p.get("gpu_t") is not None else "", ("▶ " + p["game"]) if p.get("game") else ""]
        old = False
        try:
            from lanupdate import newer
            old = newer(applog.RUNNING, p.get("version", "0")) if p.get("version") else False
        except Exception:  # noqa: BLE001
            pass
        b = [_btn("Alt om PC-en", {"do": "noop"})]
        if old and on and p.get("name") != me:
            b.append(_btn("Oppdater", {"do": "houseupdate", "name": p.get("name")}, primary=True))
        if p.get("name") != me:
            if not on and p.get("mac"):
                b.append(_btn("⏻ Vekk", {"do": "pc_wake", "name": p.get("name")}))
            elif on:
                b.append(_btn("😴 Sov", {"do": "pc_sleep", "name": p.get("name")}, f"Legge {p.get('name')} i dvale?"))
        if on:                                             # «Oppdater alt» og automatikk per PC
            b.append(_btn("Oppdater alt", {"do": "pc_updateall", "name": p.get("name")},
                          f"Oppdatere alt på {p.get('name')}?", primary=bool(p.get("upd_n"))))
            if p.get("upd_auto") is not None or p.get("name") == me:
                au = p.get("upd_auto") if p.get("name") != me else __import__("updates").auto_on()
                b.append(_btn("Automatikk: på → slå av" if au else "Automatikk: av → slå på",
                              {"do": "pc_auto", "name": p.get("name"), "on": "0" if au else "1"}))
            if p.get("upd_n"):
                bits.append(f"🔄 {p['upd_n']} oppdateringer")
        items.append({"title": ("🟢 " if on else "⚫ ") + p.get("name", "?") + (" (denne)" if p.get("name") == me else ""),
                      "sub": " · ".join(x for x in bits if x) or ("på" if on else "av"),
                      "badge": f"v{p.get('version', '?')}" + (" – kan oppdateres" if old else ""),
                      "detail": {"what": "pclive", "q": {"name": p.get("name")}}, "buttons": b[1:]})
    return {"id": "homepcs", "icon": "🏠", "title": "PC-er hjemme",
            "desc": "Trykk på en PC for alt om den. «Oppdater alle» henter nyeste versjon og starter Kontrollsenter "
                    "på nytt på PC-ene.", "items": items,
            "buttons": [_btn("Oppdater alle PC-ene", {"do": "houseupdate_all"}, "Oppdatere og starte Kontrollsenter "
                                                                                "på nytt på alle PC-ene som er på?",
                             primary=True)]}


def pc_live(name):
    import homepcs
    p = next((x for x in homepcs.fetch() or [] if x.get("name") == name), None)
    if not p:
        raise ValueError("fant ikke PC-en")
    import friends_ui
    d = homepcs.live(p)
    return {"title": name, "online": d.get("online"), "sections": [[t, rows] for t, rows in friends_ui.rows_for(d)]}


# --------------------------------------------------------------------------
# PC-verktøy: oppstart, ytelse, støy, sikkerhetskopi
# --------------------------------------------------------------------------
def p_pctools(win):
    """PC-verktøy"""
    import pctools
    c = pctools.cfg()
    rows = []
    try:
        r = pctools.boot_report()
        if r.get("total"):
            rows.append(["Oppstart", f"{r['total']:.0f} s"])
            for x in sorted(r["system"] + r["user"], key=lambda x: -x["s"])[:3]:
                rows.append(["  " + x["name"], f"{x['s']:.1f} s"])
    except Exception:  # noqa: BLE001
        pass
    b = (c.get("bench") or [None])[-1]
    if b:
        rows += [["Prosessor (alle kjerner)", f"{b['cpuN']} poeng"], ["Minne", f"{b['mem_gbs']} GB/s"],
                 ["Disk", f"{b['disk_w']} MB/s"]]
    if c.get("noise"):
        rows.append(["Viftestøy", c["noise"]["text"]])
    bl = c.get("backup_last")
    rows.append(["Sikkerhetskopi til NAS", time.strftime("%d.%m %H:%M", time.localtime(bl["t"])) + f" ({bl['sent']} nye)"
                 if bl else "ikke kjørt ennå"])
    return {"id": "pctools", "icon": "🔧", "title": "PC-verktøy", "desc": "Oppstartsrapport, trygg ytelsestest, "
            "støymåler for viftene og sikkerhetskopi til NAS-en.", "rows": rows,
            "buttons": [_btn("Kjør ytelsestest", {"do": "bench"}, primary=True),
                        _btn("Ta sikkerhetskopi", {"do": "backup_nas"}),
                        _btn("Mål viftestøy", {"do": "noise"}, "Viftene går på 30–100 % i ca. 30 sekunder, og "
                                                               "mikrofonen på PC-en lytter. Fortsette?")]}


# --------------------------------------------------------------------------
# Programmer – topp 5 per funksjon, valg og installering
# --------------------------------------------------------------------------
def p_apps(win):
    """Programmer"""
    import apps
    items = []
    for f in apps.status():
        use = apps.get_use(f["feature"])
        names = []
        for a in f["apps"]:
            names.append(f"{a['rank']}. {a['name']}" + (" ✅" if a["installed"] else "") + (" ⭐" if a["key"] == use else ""))
        btns = [_btn(f"Installer {a['name']}", {"do": "appinstall", "key": a["key"]})
                for a in f["apps"] if not a["installed"] and a["can_install"]][:2]
        inst = [a for a in f["apps"] if a["installed"]]
        if len(inst) > 1:
            btns += [_btn(f"Bruk {a['name']}", {"do": "appuse", "feature": f["feature"], "key": a["key"]})
                     for a in inst if a["key"] != use][:2]
        items.append({"title": f["title"], "sub": "  ·  ".join(names), "buttons": btns})
    return {"id": "apps", "icon": "🧩", "title": "Programmer – topp 5 per funksjon",
            "desc": "⭐ = programmet som brukes · ✅ = installert. Installeres på PC-en med Flathub/winget.",
            "items": items}


# --------------------------------------------------------------------------
# Hovedskjermkort
# --------------------------------------------------------------------------
def p_gpu(win):
    """Hovedskjermkort"""
    import gpuswitch as G
    gs = G.gpus()
    if len(gs) < 2:
        return None
    cur = G.choice(gs)
    opts = [["", "Automatisk"]] + [[g["id"], f"{g['name']} ({G.kind(g).lower()})" +
                                    ("" if g.get("connected") is None else
                                     (" · skjerm tilkoblet" if g["connected"] else " · ingen skjerm"))] for g in gs]
    return {"id": "gpu", "icon": "🖥️", "title": "Hovedskjermkort",
            "desc": "⚠️ Skjermkabelen må sitte i kortet du velger, ellers blir skjermen svart. Linux: gjelder fra "
                    "neste innlogging (og bare hvis kortet har skjerm). Windows: må bekreftes ved PC-en.",
            "select": {"label": "Skjermkort", "options": opts, "value": cur or "",
                       "action": {"a": "panel", "do": "gpuswitch"},
                       "confirm": "Bytte hovedskjermkort? Sitter kabelen i feil kort, blir skjermen svart."}}


def p_nvidia(win):
    """NVIDIA – overklokking og vifter"""
    import gpu as G
    nv = next((g for g in G.detect() if g.get("vendor") == "nvidia"), None)
    if not nv:
        return None
    e = G.nv_extra(nv["idx"])
    if not e:
        return None
    fc = G.fan_cfg(nv["id"])
    rs = e.get("reasons") or []
    rows = [["Temperatur", f"{e.get('temp', '–')} °C"],
            ["Vifter", " / ".join(f"{f} %" for f in e.get("fans", [])) or "–"],
            ["Begrenses av", ", ".join(rs) if rs else "ingenting"],
            ["Klokke-offset", f"GPU {e.get('core', 0):+d} · minne {e.get('mem', 0):+d} MHz"],
            ["Videokoder (NVENC)", f"{e.get('nvenc', 0)} %"]]
    ready = G.helper_ready()
    fan_val = fc["mode"] if fc["mode"] != "fast" else f"fast:{fc.get('pct', 60)}"
    opts = [["auto", "Automatisk"]] + [[f"fast:{p}", f"Fast {p} %"] for p in (40, 60, 80, 100)] + [["kurve", "Egen kurve"]]
    if fan_val not in [o[0] for o in opts]:
        opts.append([fan_val, f"Fast {fc.get('pct')} %"])
    p = {"id": "nvidia", "icon": "🟩", "title": "NVIDIA – overklokking og vifter", "rows": rows,
         "desc": ("Overklokking gjelder til PC-en startes på nytt. Kurven og finjustering finner du på PC-en under "
                  "Skjermkort." if ready else
                  "⚠️ Trykk «Gi tilgang» under Skjermkort på PC-en én gang før du kan endre dette herfra.")}
    if ready and not G.IS_WIN:
        p["select"] = {"label": "Vifter", "options": opts, "value": fan_val, "action": {"a": "panel", "do": "nvfan"}}
        p["buttons"] = [_btn("Standard", {"do": "nvoc", "core": 0, "mem": 0}),
                        _btn("Stille (−100)", {"do": "nvoc", "core": -100, "mem": 0}),
                        _btn("Mild OC (+100/+500)", {"do": "nvoc", "core": 100, "mem": 500},
                             "Overklokke skjermkortet litt? Krasjer et spill, trykk «Standard»."),
                        _btn("Sterk OC (+175/+1000)", {"do": "nvoc", "core": 175, "mem": 1000},
                             "Sterk overklokking kan gi krasj i noen spill. Fortsette?")]
    return p


# --------------------------------------------------------------------------
# Smart Hjem: nettradio og hjemme/borte
# --------------------------------------------------------------------------
def p_radio(win):
    """Nettradio"""
    import smarthome
    if not smarthome._CACHE["devices"]:                 # ikke søkt ennå: søk i bakgrunnen, vis neste gang
        import threading
        threading.Thread(target=smarthome.devices, daemon=True).start()
        _CACHE.pop("radio", None)
        return None
    casts = [d for d in smarthome.devices(600) if "cast" in d.get("control", [])]
    if not casts:
        return None
    names = [n for n, _u in smarthome.radio_list()]
    items = [{"title": d.get("name") or d.get("model") or d["ip"], "sub": d.get("model") or "",
              "buttons": [_btn(f"📻 {n}", {"do": "radio", "ip": d["ip"], "name": n}) for n in names[:6]]
              + [_btn("⏹ Stopp", {"do": "radio_stop", "ip": d["ip"]})]} for d in casts]
    return {"id": "radio", "icon": "📻", "title": "Nettradio på høyttalerne",
            "desc": "Spilles rett på Chromecast/Nest – PC-en kan slås av etterpå.", "items": items}


def p_presence(win):
    """Hjemme/borte"""
    import presence
    st = presence.state()
    items = [{"title": ("🏠 " if p.get("home") else "🚶 ") + p["name"], "sub": p.get("ip", ""),
              "buttons": [_btn("Fjern", {"do": "presence_del", "name": p["name"]})]} for p in st["phones"]]
    return {"id": "presence", "icon": "🏠", "title": "Hjemme / borte",
            "desc": "Telefonene som styrer scenene «Når noen kommer hjem» og «Når alle har dratt». Velg telefoner på "
                    "PC-en (Smart Hjem → Automatikk).",
            "rows": [["Nå", "noen hjemme" if st["home"] else ("ingen hjemme" if st["home"] is False else "ukjent")],
                     ["Borte etter", f"{st['away_min']} min"]], "items": items}


# --------------------------------------------------------------------------
# Oppdatering: forrige versjon
# --------------------------------------------------------------------------
def p_version(win):
    """Versjon"""
    import applog
    import lanupdate as L
    prev = L.backup_version()
    b = []
    if prev and not L.is_source_pc():
        b.append(_btn(f"Gå tilbake til {prev}", {"do": "rollback"}, f"Gå tilbake til {prev}? Kontrollsenter startes "
                                                                     "på nytt på PC-en."))
    st = ""
    try:
        st, _new = L.check()
    except Exception:  # noqa: BLE001
        pass
    return {"id": "version", "icon": "🛡️", "title": "Kontrollsenter-versjon",
            "rows": [["Kjører", applog.RUNNING], ["NAS-en", st or "–"], ["Forrige", prev or "–"]],
            "buttons": [_btn("Oppdater denne PC-en", {"do": "selfupdate"}, primary=True)] + b}


def p_updates(win):
    """Oppdater alt"""
    import updates
    st = updates.cached()
    n = updates.total(st)
    rows = [[s["name"], ("✅ " if s["count"] == 0 else "🔄 " if s["count"] > 0 else "❔ ") + s["detail"]] for s in st]
    if updates.running():
        rows.insert(0, ["Nå", "🔄 Oppdaterer …"])
    au = updates.auto_on()
    return {"id": "updates", "icon": "🔄", "title": "Oppdater alt" + (f" · {n} klare" if n else ""),
            "desc": ("Automatisk oppdatering og opprydding er på." if au else
                     "Manuelt: ingen automatiske sjekker, oppdateringer eller diskopprydding."),
            "rows": rows or [["Status", "Ikke sjekket ennå – trykk «Se etter»"]],
            "buttons": [_btn("Oppdater alt", {"do": "updateall"}, "Oppdatere alt på denne PC-en?", primary=n > 0),
                        _btn("Se etter", {"do": "updatecheck"}),
                        _btn("Automatikk: på → slå av" if au else "Automatikk: av → slå på",
                             {"do": "updateauto", "on": "0" if au else "1"})]}


_ASSIST = {}


def p_assistant(win):
    """PC-assistent"""
    import assistant as A
    fs = _ASSIST.get("f")
    if fs is None or time.time() - _ASSIST.get("t", 0) > 120:
        fs = A.why_slow(win) if win is not None else []
        _ASSIST.update(f=fs, t=time.time())
    items = []
    for i, f in enumerate(fs):
        b = [_btn(f.fix[0], {"do": "assistfix", "key": f.key}, f"{f.fix[0]}?", primary=True)] if f.fix else []
        items.append({"title": {"ok": "✅", "info": "ℹ️", "warn": "⚠️", "error": "❌"}.get(f.level, "•") + " " + f.title,
                      "sub": f.detail, "buttons": b})
    return {"id": "assistant", "icon": "🩺", "title": "Hvorfor er PC-en treg?",
            "desc": "PC-assistenten ser på varme, minne, prosessor, disk og det som jobber i bakgrunnen.",
            "items": items, "buttons": [_btn("Sjekk nå", {"do": "assistcheck"}, primary=not items)]}


def p_family(win):
    """Hvem er på nå"""
    import familyfun as FF
    items = []
    for x in FF.who_is_on():
        if not x["online"]:
            continue
        h, m = divmod(int(x["play_s"]) // 60, 60)
        items.append({"title": ("🎮 " if x["game"] else "🟢 ") + (x["name"] or "?"),
                      "sub": (f"Spiller {x['game']} · " if x["game"] else "") + f"{h} t {m} min i dag",
                      "buttons": [_btn("Gi 30 min", {"do": "fam", "what": "bonus", "name": x["name"], "min": 30}),
                                  _btn("⏸️ Pause nå", {"do": "fam", "what": "pause", "name": x["name"]},
                                       f"Lukke spillet på {x['name']} nå?")]})
    lb = FF.leaderboard()
    rows = [[f"{('🥇', '🥈', '🥉')[i] if i < 3 else str(i + 1) + '.'} {r[0]}", f"{r[1]} poeng"] for i, r in enumerate(lb)]
    free = FF.is_free_today()
    return {"id": "family", "icon": "👨‍👩‍👧", "title": "Hvem er på nå",
            "desc": "PC-ene som er på, hva som spilles og spilletid i dag. Familiekonkurransen under.",
            "items": items or [{"title": "Ingen PC-er er på", "sub": ""}], "rows": rows,
            "buttons": [_btn("🍽️ Middag!", {"do": "fam_dinner"}, "Sende «Middag!» til alle PC-ene?", primary=True),
                        _btn("Leksetid som vanlig" if free else "📚 Fri fra lekser i dag",
                             {"do": "fam_free", "on": "0" if free else "1"})]}


PANELS = [p_commands, p_family, p_assistant, p_updates, p_games, p_homepcs, p_pctools, p_apps, p_gpu, p_nvidia, p_radio, p_presence, p_version]


_CACHE = {}
TTL = {"assistant": 60, "pctools": 120, "apps": 60, "games": 120, "radio": 300, "gpu": 60, "nvidia": 5}


def all_panels(win, only=None):
    """Bygg panelene parallelt (det tregeste bestemmer tiden) og gjenbruk de tunge en stund."""
    from concurrent.futures import ThreadPoolExecutor
    fns = [fn for fn in PANELS if not only or fn.__name__[2:] in only]

    def one(fn):
        key = fn.__name__[2:]
        hit = _CACHE.get(key)
        if hit and time.time() - hit[0] < TTL.get(key, 15):
            return hit[1]
        try:
            p = fn(win)
        except Exception as e:  # noqa: BLE001
            p = {"id": key, "icon": "⚠️", "title": (fn.__doc__ or "").strip(), "desc": f"Feil: {e}"}
        _CACHE[key] = (time.time(), p)
        return p
    with ThreadPoolExecutor(len(fns) or 1) as ex:
        res = list(ex.map(one, fns))
    return [p for p in res if p]


def invalidate(*keys):
    for k in keys or list(_CACHE):
        _CACHE.pop(k, None)


# --------------------------------------------------------------------------
# Handlinger fra appen
# --------------------------------------------------------------------------
def run(win, a):
    import threading
    do = str(a.get("do", ""))
    invalidate()
    if do == "noop":
        return ""
    if do == "cmd":
        return run_cmd(win, str(a.get("label", "")))
    if do == "cmdtext":
        return run_text(win, str(a.get("text", ""))[:200])
    if do == "launch":
        import launcher
        g = _game(str(a.get("id", "")))
        from gi.repository import GLib
        GLib.idle_add(lambda: (launcher.launch(g), False)[1])
        return f"Starter {g['name']} på PC-en"
    if do == "invite":
        import launcher
        return launcher.invite(_game(str(a.get("id", ""))))
    if do == "assistcheck":
        _ASSIST.clear()
        return "Sjekket"
    if do == "assistfix":
        import assistant as A
        fs = _ASSIST.get("f") or A.why_slow(win)
        f = next((x for x in fs if x.key == a.get("key") and x.fix), None)
        if not f:
            raise ValueError("fant ikke funnet – sjekk på nytt")
        _ASSIST.clear()
        return str(f.fix[1]())
    if do in ("nvoc", "nvfan"):
        import gpu as G
        nv = next((g for g in G.detect() if g.get("vendor") == "nvidia"), None)
        if not nv:
            raise ValueError("fant ikke NVIDIA-kortet")
        if do == "nvoc":
            core, mem = int(a.get("core", 0)), int(a.get("mem", 0))
            if not (-300 <= core <= 300 and 0 <= mem <= 1500):
                raise ValueError("ugyldig verdi")
            G.run("nv-oc", nv["idx"], core, mem)
            G.save_cmd(nv["id"], "oc", None if core == mem == 0 else ["nv-oc", nv["idx"], core, mem])
            return "Tilbake til standard ✓" if core == mem == 0 else f"Satt: GPU {core:+d}, minne {mem:+d} MHz ✓"
        v = str(a.get("value", "auto"))
        if v.startswith("fast:"):
            return G.set_fan(nv["id"], nv["idx"], "fast", pct=int(v[5:]))
        return G.set_fan(nv["id"], nv["idx"], "kurve" if v == "kurve" else "auto")
    if do == "updateall":
        import updates
        return "Oppdater alt er startet – følg fremdriften øverst" if updates.update_all(win) else "Pågår allerede"
    if do == "updatecheck":
        import updates
        st = updates.status(refresh=True)
        n = updates.total(st)
        return "Alt er oppdatert ✓" if n == 0 else f"{n} oppdateringer er klare"
    if do == "updateauto":
        import updates
        updates.set_auto(str(a.get("on")) == "1")
        return "Automatikk på" if updates.auto_on() else "Automatikk av – gjør alt manuelt"
    if do == "fam":
        import homepcs
        import savegames
        import familyfun as FF
        q = {"min": str(int(a.get("min", 30)))} if a.get("what") == "bonus" else {}
        if a.get("name") == savegames.pc_name():
            return FF.house_action(win, a.get("what"), **q)
        p = next((x for x in homepcs.fetch() or [] if x.get("name") == a.get("name")), None)
        if not p:
            raise ValueError("fant ikke PC-en")
        ok, d = homepcs.house_call(p, "family", 20, do=a.get("what"), **q)
        return (f"✓ {p['name']}: {d.get('msg', 'OK')}") if ok else f"✗ {d}"
    if do == "fam_dinner":
        import remote
        ok, msg = remote.do_action(win, {"a": "dinner"})
        return msg
    if do == "fam_free":
        import familyfun as FF
        return FF.school_free_today(str(a.get("on")) == "1")
    if do in ("pc_wake", "pc_sleep"):
        import homepcs
        import house
        p = next((x for x in homepcs.fetch() or [] if x.get("name") == a.get("name")), None)
        if not p:
            raise ValueError("fant ikke PC-en")
        if do == "pc_wake":
            if not p.get("mac"):
                raise ValueError("kjenner ikke MAC-adressen – start Kontrollsenter på den PC-en én gang")
            house.wake(p["mac"], p.get("ips"))
            return f"⏻ Vekker {p['name']} – tar et minutt"
        ok, d = house.system(p, "sleep")
        return f"😴 {p['name']} sover" if ok else f"✗ {d}"
    if do in ("pc_updateall", "pc_auto"):
        import homepcs
        import savegames
        import updates
        name = a.get("name")
        if name == savegames.pc_name():
            if do == "pc_auto":
                updates.set_auto(str(a.get("on")) == "1")
                return "Automatikk " + ("på" if updates.auto_on() else "av")
            return "Startet" if updates.update_all(win) else "Pågår allerede"
        p = next((x for x in homepcs.fetch() or [] if x.get("name") == name), None)
        if not p:
            raise ValueError("fant ikke PC-en")
        if do == "pc_auto":
            ok, d = homepcs.house_call(p, "auto", 15, on=str(a.get("on")))
            return (f"✓ Automatikk {'på' if d.get('auto') else 'av'} på {name}" if ok else f"✗ {d}")
        ok, d = homepcs.house_call(p, "updateall", 20)
        return f"✓ Oppdater alt startet på {name}" if ok else f"✗ {d}"
    if do == "houseupdate_all":
        import homepcs
        res = homepcs.update_all(homepcs.fetch() or [])
        return "  ·  ".join(f"{'✓' if ok else '✗'} {n}: {m}" for n, ok, m in res) or "Ingen andre PC-er er på"
    if do == "houseupdate":
        import homepcs
        p = next((x for x in homepcs.fetch() or [] if x.get("name") == a.get("name")), None)
        if not p:
            raise ValueError("fant ikke PC-en")
        ok, msg = homepcs.update_pc(p)
        return ("✓ " if ok else "✗ ") + msg
    if do in ("bench", "backup_nas", "noise"):
        import pctools
        fn = {"bench": pctools.benchmark, "backup_nas": pctools.backup_run,
              "noise": lambda: pctools.noise_test(win)}[do]
        threading.Thread(target=fn, daemon=True).start()
        return "Startet på PC-en – følg fremdriften øverst"
    if do == "appinstall":
        import apps
        threading.Thread(target=lambda: apps.install(str(a.get("key", ""))), daemon=True).start()
        return "Installerer på PC-en – følg fremdriften øverst"
    if do == "appuse":
        import apps
        apps.set_use(str(a.get("feature", "")), str(a.get("key", "")))
        return "Lagret ✓"
    if do == "gpuswitch":
        import gpuswitch as G
        G.set_choice(str(a.get("value") or "") or None)
        return "Lagret – gjelder fra neste innlogging" if not G.IS_WIN else "Bekreft på PC-en"
    if do == "radio":
        import smarthome
        return smarthome.cast_radio(str(a.get("ip", "")), str(a.get("name", "")))
    if do == "radio_stop":
        import smarthome
        return smarthome.cast_do(str(a.get("ip", "")), "stop")
    if do == "presence_del":
        import presence
        c = presence.cfg()
        c["phones"] = [p for p in c.get("phones") or [] if p.get("name") != a.get("name")]
        presence.save_cfg(c)
        return "Fjernet"
    if do == "rollback":
        import lanupdate as L
        msg = L.rollback()
        from gi.repository import GLib
        GLib.timeout_add_seconds(2, lambda: (win.restart_app(), False)[1])
        return msg
    if do == "selfupdate":
        import remote
        r = remote.house_update(win)
        return r.get("msg", "")
    raise ValueError("ukjent handling")
