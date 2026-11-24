"""Det Android-appen trenger fra PC-en for den nye chatten og AI-siden (samme funksjoner som på PC-en):
lenkeforhåndsvisning, GIF-søk, reaksjoner/rediger/slett/fest/lest, vedlegg og talemeldinger, Ikke forstyrr, status,
og AI-en: samtaler, spør (svaret følges live), «Godta / Avbryt».

remote.py sender /api/x/<navn> hit (X) og handlinger fra /api/action (action).
"""
import base64
import os
import threading
import time
import uuid

JOBS = {}                                  # AI-forespørsler fra mobilen: id -> {text, tools, done, cid, tool}


# --------------------------------------------------------------------------
# Chat
# --------------------------------------------------------------------------
def chatroom(arg):
    import chat
    import chatlink
    import chatlook
    import chatsrv
    room = arg("room", "alle")
    rd = chat._load(chat.FILE, {}).get("_read", {})
    mark = max([rd.get(a, 0) for a in chat.aliases(room)] or [0])          # «Nye meldinger»-streken
    msgs = chat.messages(room, 120)
    chat.mark_read(room)
    if room.startswith("p:") and any(m.get("t", 0) > mark and m.get("pc") != chat._me() for m in msgs):
        threading.Thread(target=lambda: _safe(lambda: chat.send_event(room, {"type": "read", "t": time.time()})),
                         daemon=True).start()
    me = chatsrv.me()
    out = {"room": room, "messages": msgs, "me_id": me["id"], "me": me["name"], "me_pc": chat._me(),
           "newmark": mark, "seen_by": chat.seen_by(room) if room.startswith("p:") else 0,
           "dnd": chatlook.dnd_text(), "playing": [], "colors": {}}
    names = {m.get("from") for m in msgs if m.get("from")}
    out["colors"] = {n: chatlook.color_for(n) for n in names}
    if room.startswith("s:"):
        srv = chatsrv.get(room.split(":")[1]) or {}
        for mid, mem in (srv.get("members") or {}).items():
            p = chatlink._PRES.get(mid)
            if p and p.get("game") and time.time() - p.get("t", 0) < 600:
                out["playing"].append({"name": mem.get("name"), "game": p["game"], "since": p.get("since") or 0})
        out["avatars"] = {mid: chatlink.avatar(mid)[0] for mid in (srv.get("members") or {})}
        out["presence"] = {mid: chatlink.presence(mid)[0] for mid in (srv.get("members") or {})}
    return out


def linkprev(arg):
    import chatextra
    pv = chatextra.link_preview(arg("url", ""))
    if not pv:
        return {"ok": False}
    img = None
    if pv.get("image") and os.path.getsize(pv["image"]) < 1_500_000:
        with open(pv["image"], "rb") as f:
            img = "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
    return {"ok": True, "title": pv.get("title"), "desc": pv.get("desc"), "site": pv.get("site"), "image": img}


def gifs(arg):
    import chatextra
    if not chatextra.gif_key():
        return {"key": False, "results": []}
    return {"key": True, "results": [{"tiny": t, "big": b} for t, b in chatextra.gif_search(arg("q", "hei"), 20)]}


def chat_send(win, a, notify):
    """Fra mobilen: vanlig melding, /-kommando eller @ai."""
    import chat
    room, text = str(a.get("room") or "alle"), str(a.get("text") or "").strip()
    extra = {"reply": str(a["reply"])[:80]} if a.get("reply") else None
    if text.lower().startswith("@ai "):
        chat.send(room, text, a.get("_dev") or None, notify, extra=extra)

        def run():
            import aiextra
            aiextra.chat_ai(room, text[4:].strip(), notify)
        threading.Thread(target=lambda: _safe(run), daemon=True).start()
        return "✨ AI-en svarer om litt …"
    if text.startswith("/") and not text.startswith("//"):
        import chatextra
        txt, special = chatextra.command(room, text, win, notify)
        if special and special[0] == "gif":
            return "GIF:" + (special[1] or "")
        return txt or "OK"
    return chat.send(room, text, a.get("_dev") or None, notify, extra=extra)


def chat_event(win, a):
    """Reaksjon / rediger / slett / fest fra mobilen."""
    import chat
    room, kind, mid = str(a.get("room") or ""), str(a.get("type") or ""), str(a.get("mid") or "")
    if kind not in ("react", "edit", "delete", "pin"):
        raise ValueError("ukjent hendelse")
    kw = {k: a[k] for k in ("emoji", "text", "on") if k in a}
    if room.startswith("s:"):
        import chatsrv
        _s, sid, ch = room.split(":", 2)
        srv = chatsrv.get(sid)
        me = chatsrv.me()
        ev = {"type": kind, "mid": mid, "ch": ch, "from": me["name"], "from_id": me["id"], **kw}
        chat.apply_event(room, ev, (srv or {}).get("members", {}).get(me["id"]))
        threading.Thread(target=lambda: _safe(lambda: chatsrv.broadcast(srv, ev)), daemon=True).start()
    else:
        threading.Thread(target=lambda: _safe(lambda: chat.send_event(room, {"type": kind, "mid": mid, **kw})),
                         daemon=True).start()
    return "OK"


def chat_upload(body, notify):
    """Bilde, fil eller talemelding fra mobilen (base64)."""
    import chatplus
    room = str(body.get("room") or "")
    name = os.path.basename(str(body.get("name") or "fil"))[:80]
    data = base64.b64decode(body.get("data") or "")
    if not data or len(data) > chatplus.MAX_FILE:
        raise ValueError("filen er tom eller for stor (maks 8 MB)")
    if body.get("kind") == "audio":
        path = os.path.join(chatplus.FILES, f"tale-mobil-{int(time.time())}" + (os.path.splitext(name)[1] or ".webm"))
        os.makedirs(chatplus.FILES, exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        import chatextra
        wv = [max(0, min(9, int(x))) for x in (body.get("wave") or [])][:64] or None
        return chatextra.send_voice(room, path, wv or [3] * 30, float(body.get("secs") or 0), notify)
    d = os.path.join(chatplus.FILES, "fra-mobil")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name)
    with open(path, "wb") as f:
        f.write(data)
    return chatplus.send_file(room, path, str(body.get("text") or ""), notify)


def chat_gif(a, notify):
    import chatextra
    import chatplus
    url = str(a.get("url") or "")
    if not url.startswith("https://") or "tenor" not in url:
        raise ValueError("ugyldig GIF")
    return chatplus.send_file(str(a.get("room") or ""), chatextra.gif_file(url), "", notify)


# --------------------------------------------------------------------------
# AI fra mobilen (kjører på PC-en: samme assistenter, samme samtaler)
# --------------------------------------------------------------------------
def ai_state(arg):
    import ai
    import ai_store as S
    c = ai.cfg()
    tools = [{"id": t, "name": v["name"], "color": ai.TOOL_COLOR.get(t, "#888"),
              "ok": bool(ai.binary(t)) and ai.logged_in(t)} for t, v in ai.TOOLS.items()]
    return {"tool": c.get("tool"), "tools": tools, "persona": c.get("persona", "standard"),
            "personas": [{"id": k, "name": v[0], "emoji": v[1]} for k, v in ai.PERSONAS.items()],
            "confirm": c.get("confirm", True), "quota": ai.quota(), "convs": S.conversations()[:60],
            "suggestions": _suggestions()}


def _suggestions():
    try:
        import ai_ui
        return [{"emoji": e, "text": t} for e, t in ai_ui.SUGGESTIONS]
    except Exception:  # noqa: BLE001
        return []


def ai_conv(arg):
    import ai_store as S
    c = S.load(arg("id", "")) or {}
    return {"id": c.get("id"), "title": c.get("title"), "tool": c.get("tool"),
            "messages": [{k: m.get(k) for k in ("role", "text", "t", "tool", "tools")} for m in c.get("messages", [])]}


def ai_ask(a):
    import ai
    import ai_store as S
    tool = a.get("tool") if a.get("tool") in ai.TOOLS else ai.cfg().get("tool", "claude")
    c = S.load(a.get("cid") or "") or S.new(tool)
    q = str(a.get("text") or "").strip()
    if not q:
        raise ValueError("skriv et spørsmål")
    imgs = []
    for i, b64 in enumerate(a.get("images") or []):        # bilder fra mobilen
        d = os.path.join(S.workdir(), "bilder")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, time.strftime(f"mobil-%Y%m%d-%H%M%S-{i}.jpg"))
        with open(p, "wb") as f:
            f.write(base64.b64decode(str(b64).split(",")[-1]))
        imgs.append(p)
    c["tool"] = tool
    c["messages"].append({"role": "user", "text": q, "t": time.time()})
    S.save(c)
    jid = uuid.uuid4().hex[:10]
    job = {"text": "", "tools": [], "done": False, "cid": c["id"], "tool": tool, "t": time.time()}
    JOBS[jid] = job

    def done(code):
        txt = job["text"].strip() or ("✗ Fikk ikke svar – er AI-en pålogget på PC-en?" if code else "")
        c["messages"].append({"role": "assistant", "text": txt, "t": time.time(), "tool": tool,
                              **({"tools": job["tools"]} if job["tools"] else {})})
        S.save(c)
        job["done"] = True
    cfg = ai.cfg()
    job["proc"] = ai.ask(tool, q, S.workdir(), cfg["allow_edit"], on_text=lambda t: job.__setitem__(
        "text", job["text"] + t), on_done=done, history=S.history_text(c), control=cfg.get("control", True),
        images=imgs, on_event=lambda k, d: k == "tool" and job["tools"].append(str(d)),
        persona=a.get("persona"))
    for k in [k for k, v in JOBS.items() if time.time() - v["t"] > 3600]:
        JOBS.pop(k, None)
    return {"job": jid, "cid": c["id"]}


def ai_job(arg):
    import ai_bridge
    j = JOBS.get(arg("id", ""))
    if not j:
        return {"done": True, "text": "", "tools": [], "gone": True}
    return {"done": j["done"], "text": j["text"], "tools": j["tools"], "cid": j["cid"], "tool": j["tool"],
            "confirm": ai_bridge.pending()}


def ai_stop(a):
    j = JOBS.get(str(a.get("job") or ""))
    if j and j.get("proc"):
        try:
            j["proc"].terminate()
        except OSError:
            pass
    return "Stoppet"


def _safe(fn):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------
# Kalender og dagbok
# --------------------------------------------------------------------------
def kal(arg):
    import calendar as C
    import datetime as dt
    import kalender as K
    y, m = int(arg("y", dt.date.today().year)), int(arg("m", dt.date.today().month))
    a = dt.date(y, m, 1) - dt.timedelta(days=7)
    b = dt.date(y, m, C.monthrange(y, m)[1]) + dt.timedelta(days=14)
    it = K.items(a, b)
    out = {d.isoformat(): [{k: v for k, v in x.items() if k in ("title", "time", "color", "kind", "icon", "src", "id",
                                                                "done", "note", "red")} for x in lst]
           for d, lst in it.items()}
    cd = K.countdown()
    return {"items": out, "countdown": cd[1] if cd else "", "workdays": K.workdays(y, m),
            "vacation": [{"name": n, "took": t, "from": f.isoformat(), "to": e.isoformat(), "len": ln}
                         for n, t, f, e, ln in K.vacation_tips(y)],
            "events": [e for e in K.load()["events"]], "kinds": {k: list(v) for k, v in K.KINDS.items()},
            "colors": K.COLORS}


def kalsok(arg):
    import kalender as K
    return {"hits": [{"d": d.isoformat(), "time": t, "title": n} for d, t, n in K.search(arg("q", ""))[:60]]}


def dagbok_people(arg):
    import dagbok as D
    try:
        D.sync_down()
    except Exception:  # noqa: BLE001
        pass
    return {"people": [{**p, "wait": D.locked_for(p["id"])} for p in D.people()], "moods": D.MOODS}


def pcplus(_arg):
    import pcplus as P
    h = P.LAST["health"]
    if h is None and not P.LAST.get("busy"):               # første gang: regn ut i bakgrunnen (tar noen sekunder)
        import threading
        P.LAST["busy"] = True

        def run():
            try:
                P.LAST["health"] = P.health()
            finally:
                P.LAST["busy"] = False
        threading.Thread(target=run, daemon=True).start()
    try:
        b = P.budget()
    except Exception:  # noqa: BLE001
        b = None
    r = P.STRESS["result"]
    return {"health": h, "budget": b, "quiet": P.quiet_left(), "bios": P.bios(),
            "stress": {"running": P.STRESS["running"], "t": (P.STRESS["log"][-1][0] if P.STRESS["log"] else 0),
                       "temp": (P.STRESS["log"][-1][1] if P.STRESS["log"] else None),
                       "result": {k: r[k] for k in r if k != "log"} if r else None}}


def spill3(_arg):
    import spill3 as S
    st = S.storage()
    return {"wrapped": S.wrapped(), "compare": S.compare(), "net": {"hist": S.NET["hist"][-30:],
            "game": S.NET["game"], "verdict": S.net_verdict()}, "storage": {k: st[k] for k in ("old", "old_gb",
            "total_gb")}, "tourney": S.t_load(), "night": S.cfg()["night_updates"], "win": S.IS_WIN}


def skjerm(_arg):
    import avprofiles as P
    return {"displays": [{"id": d["id"], "name": d["name"], "w": d["w"], "h": d["h"], "hz": d["hz"],
                          "modes": [list(m) for m in d["modes"]]} for d in P.displays()], "pending": P.pending()}


def lydtest(_arg):
    import lydtest as L
    import lydfilter as F
    return {**L.info(), "cal": {"running": L.CAL["running"], "step": L.CAL["step"], "result": L.CAL["result"]},
            "filter": F.state() if not F.IS_WIN else {"available": False}}


X = {"pcplus": pcplus, "spill3": spill3, "skjerm": skjerm, "lydtest": lydtest, "kal": kal, "kalsok": kalsok, "dagbok": dagbok_people, "chatroom2": chatroom, "linkprev": linkprev, "gifs": gifs, "ai": ai_state, "aiconv": ai_conv, "aijob": ai_job}


def action(win, kind, a, notify):
    """Handlingene fra mobilen. Returnerer (ok, tekst) eller None hvis ukjent."""
    if kind == "chatev":
        return True, chat_event(win, a)
    if kind == "chatgif":
        return True, chat_gif(a, notify)
    if kind == "chatdnd":
        import chatlook
        chatlook.set_dnd(float(a.get("hours", 0)))
        return True, chatlook.dnd_text() or "Ikke forstyrr er av"
    if kind == "chatstatus":
        import chatplus
        chatplus.set_(status=str(a.get("text") or "")[:80])
        return True, "Status lagret"
    if kind == "tenorkey":
        import chatplus
        chatplus.set_(tenor_key=str(a.get("key") or "").strip()[:100])
        return True, "Lagret"
    if kind == "aiask":
        import json
        return True, json.dumps(ai_ask(a))
    if kind in ("pcquiet", "pcbudget", "pcstress"):     # PC runde 4 fra mobilen
        import pcplus as P
        if kind == "pcquiet":
            return True, P.quiet_for(float(a.get("hours") or 0))
        if kind == "pcbudget":
            P.set_(budget_kr=max(0, int(a.get("kr") or 0)), budget_warned="")
            return True, "Budsjett lagret"
        if a.get("stop"):
            P.STRESS["stop"] = True
            return True, "Stopper stresstesten"
        import threading
        threading.Thread(target=lambda: P.stress(int(a.get("minutes") or 5)), daemon=True).start()
        return True, "Stresstesten er startet på PC-en"
    if kind.startswith("spill3") or kind.startswith("turn"):   # spill runde 3 fra mobilen
        import spill3 as S
        if kind == "spill3mark":
            return True, S.mark(str(a.get("label") or ""))
        if kind == "spill3uninst":
            return True, S.uninstall(str(a.get("appid")))
        if kind == "spill3night":
            return True, S.night_updates(bool(a.get("on")))
        if kind == "spill3share":
            import chat
            chat.send("alle", S.wrapped()["text"])
            return True, "Delt i chatten"
        if kind == "turnnew":
            S.t_new(str(a.get("name") or ""), str(a.get("game") or ""),
                    [{"name": x.strip()} for x in str(a.get("teams") or "").split(",") if x.strip()])
            return True, "Turneringen er i gang"
        if kind == "turnscore":
            S.t_score(int(a.get("team", -1)), int(a.get("d", 1)))
            return True, "Poeng"
        if kind == "turnend":
            msg = S.t_end()
            try:
                import chat
                chat.send("hjemme", msg)
            except Exception:  # noqa: BLE001
                pass
            return True, msg
        if kind == "turngm":
            return True, S.t_gamemode_all(win)
        raise ValueError("ukjent")
    if kind == "skjermmodus":                            # oppløsning og Hz fra mobilen (settes tilbake etter 20 s)
        import avprofiles as P
        return True, P.set_mode(str(a.get("id")), a.get("w"), a.get("h"), a.get("hz"), revert=20)
    if kind == "skjermbehold":
        import avprofiles as P
        return True, P.keep_mode()
    if kind == "skjermangre":
        import avprofiles as P
        return True, P.undo_mode()
    if kind == "skjermtest":                             # skjermtesten i fullskjerm på PC-en
        from gi.repository import GLib

        def show():
            import skjerm_ui
            skjerm_ui.ScreenTest(win).present()
            return False
        GLib.idle_add(show)
        return True, "Skjermtesten er startet på PC-en (Esc avslutter)"
    if kind == "lydfilter":                              # 7.1 / EQ / støyfilter fra mobilen
        import lydfilter as F
        if a.get("preset"):
            F.set_eq(preset=str(a["preset"]))
            return True, "Equalizer: " + F.PRESETS.get(str(a["preset"]), ("",))[0]
        return True, F.enable(str(a.get("kind")), bool(a.get("on")))
    if kind == "lydkal":                                 # nivåkalibrering med mikrofonen (tar ca. 20 s)
        import threading
        import lydtest as L
        if L.CAL["running"]:
            return True, "Kalibrerer allerede"
        if a.get("reset"):
            return True, L.apply_levels({}, a.get("sink"), a.get("layout"))

        def run():
            try:
                r = L.calibrate(str(a.get("layout") or "7.1"), a.get("sink"))
                if len(r["weak"]) < len(r["levels"]):
                    L.apply_levels(r["adjust"], r["sink"], r["layout"])
            except Exception as e:  # noqa: BLE001
                L.CAL.update(running=False, step="", result={"error": str(e)})
        threading.Thread(target=run, daemon=True).start()
        return True, "Kalibrerer – vær stille og hold telefonen der du sitter"
    if kind == "lydtest":                                # test av høyttalerne på PC-en fra mobilen
        import lydtest as L
        if a.get("ch") == "stop":
            L.stop()
            return True, "Stoppet"
        return True, L.play(str(a.get("layout") or "2.0"), str(a.get("ch") or "seq"),
                            str(a.get("sound") or "voice"), a.get("sink"))
    if kind == "aistop":
        return True, ai_stop(a)
    if kind == "aiconfirm":
        import ai_bridge
        return True, "OK" if ai_bridge.answer_pending(str(a.get("id") or ""), bool(a.get("ok"))) else "Allerede svart"
    if kind == "aiset":
        import ai
        kw = {k: a[k] for k in ("tool", "persona", "confirm") if k in a}
        ai.set_(**kw)
        return True, "Lagret"
    if kind == "aipin":
        import ai_store as S
        S.set_meta(str(a.get("id") or ""), **{k: a[k] for k in ("pinned", "emoji") if k in a})
        return True, "OK"
    if kind == "kaladd":
        import kalender as K
        e = K.add({k: a.get(k) for k in ("id", "title", "date", "time", "end", "repeat", "remind", "color", "kind",
                                         "note", "done") if a.get(k) is not None})
        return True, f"Lagret: {e['title']}"
    if kind == "kaldel":
        import kalender as K
        K.remove(str(a.get("id") or ""))
        return True, "Slettet"
    if kind == "kaldone":
        import datetime as dt
        import kalender as K
        K.mark_done(str(a.get("id") or ""), dt.date.fromisoformat(str(a.get("day"))), bool(a.get("on", True)))
        return True, "OK"
    if kind.startswith("dagbok_"):
        import json
        import dagbok as D
        sub = kind[7:]
        if sub == "open":
            return True, json.dumps({"tok": D.unlock(str(a.get("id")), str(a.get("pin")))})
        if sub == "create":
            return True, json.dumps({"tok": D.create(str(a.get("name")), str(a.get("pin")))})
        if sub == "list":
            return True, json.dumps(D.entries(str(a.get("tok"))), ensure_ascii=False)
        if sub == "write":
            return True, D.write(str(a.get("tok")), a.get("text"), str(a.get("mood") or ""))
        if sub == "delete":
            return True, D.delete_entry(str(a.get("tok")), str(a.get("eid")))
        if sub == "pin":
            return True, D.change_pin(str(a.get("tok")), str(a.get("pin")))
        if sub == "lock":
            D.lock(str(a.get("tok")))
            return True, "Låst"
        raise ValueError("ukjent dagbok-handling")
    if kind == "aidelete":
        import ai_store as S
        S.delete(str(a.get("id") or ""))
        return True, "Slettet"
    return None
