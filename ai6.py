"""AI, runde 6: «Hva har jeg gått glipp av?» i chatten, «Spør om spillet», AI-hjelp etter krasj og ukentlig PC-lege.

Bruker samme AI som resten av appen (Claude, Codex, Gemini eller lokal AI). Ingenting endres uten at du godtar det.
"""
import json
import os
import threading
import time

STATE = os.path.expanduser("~/.config/systemmonitor/ai6.json")


def _state():
    try:
        return json.load(open(STATE))
    except (OSError, ValueError):
        return {}


def _save_state(**kw):
    d = _state()
    d.update(kw)
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w") as f:
        json.dump(d, f)


# ------------------------------------------------------------------ 56 – hva har jeg gått glipp av?
def missed(room, me=None, hours=24, limit=150):
    """Meldingene fra andre siden ditt siste innlegg (maks et døgn tilbake)."""
    import chat
    import savegames
    me = me or savegames.pc_name()
    ms = chat.messages(room, 400)
    since = time.time() - hours * 3600
    mine = [m.get("t", 0) for m in ms if m.get("from") == me]
    if mine:
        since = max(since, max(mine))
    return [m for m in ms if m.get("t", 0) > since and m.get("from") != me and m.get("text")][-limit:]


def summarize(room, me=None):
    import aiextra
    ms = missed(room, me)
    if not ms:
        return "Du har ikke gått glipp av noe 🙂"
    lines = "\n".join(f"{time.strftime('%H:%M', time.localtime(m['t']))} {m['from']}: {str(m['text'])[:300]}"
                      for m in ms)
    prompt = ("Oppsummer chatten under for meg på norsk, kort (maks 6 punkter med emojier): hva skjedde, hva ble "
              "bestemt, og om noen spurte meg om noe eller venter på svar fra meg. Ikke bruk verktøy.\n\n" + lines)
    _tool, text, _t = aiextra.ask_sync(prompt, timeout=120, control=False)
    return text or "Fikk ikke noe svar fra AI-en"


# ------------------------------------------------------------------ 35 – spør om spillet
def game_context():
    """Tekst om spillet som kjører nå (eller sist spilte) + maskinvaren, til å starte et spørsmål med."""
    game = None
    try:
        import remote
        bg = getattr(getattr(remote, "win", None), "bg", None)
        game = getattr(bg, "game_name", None)
    except Exception:  # noqa: BLE001
        pass
    if not game:
        try:
            import games_auto
            ss = games_auto.load_sessions()
            game = ss[-1]["name"] if ss else None
        except Exception:  # noqa: BLE001
            pass
    hw = ""
    try:
        import sensors
        hw = f"CPU {sensors.cpu_model()}"
        import gpu
        gs = [g.get("name") for g in gpu.detect()] if hasattr(gpu, "detect") else []
        if gs:
            hw += ", GPU " + " / ".join(x for x in gs if x)
    except Exception:  # noqa: BLE001
        pass
    if not game:
        return f"Jeg har en PC med {hw}. Spørsmål om et spill: " if hw else "Spørsmål om et spill: "
    return f"Jeg spiller {game} nå ({hw}). "


# ------------------------------------------------------------------ 36 – AI-hjelp etter krasj
def crash_prompt():
    """Spørsmål til AI-en om siste krasj/frys – med det krasjloggen og loggene vet."""
    import crashlog
    ev = (crashlog.history() or [None])[-1]
    if not ev:
        return None
    return ("PC-en min krasjet eller frøs " + crashlog.text(ev) + ". Finn ut hvorfor: se i «ks logg» og «ks diagnose», "
            "forklar kort hva som sannsynligvis skjedde, og foreslå hva jeg kan gjøre. Ikke endre noe før jeg sier ja.")


def crash_check(notify):
    """Ved oppstart: var det et krasj siden sist vi spurte? Tilby AI-hjelp (én gang per krasj)."""
    try:
        import crashlog
        import funksjoner
        if not funksjoner.on("ai"):
            return
        ev = (crashlog.history() or [None])[-1]
        if not ev or ev.get("t", 0) <= _state().get("crash_seen", 0) or time.time() - ev.get("t", 0) > 2 * 86400:
            return
        _save_state(crash_seen=ev.get("t", 0))
        notify("crash_ai", "🤖 Vil du at AI-en ser på krasjet?",
               "PC-en krasjet eller frøs " + crashlog.text(ev) + ". Åpne Vedlikehold › Feilsøking › «Spør AI om "
               "siste krasj».")
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------ 16 – ukentlig PC-lege
def doctor_due():
    lt = time.localtime()
    if lt.tm_wday != 6 or lt.tm_hour < 12:                # søndag etter kl. 12
        return False
    return _state().get("doctor_week") != time.strftime("%G-%V")


def weekly_doctor(win=None, notify=None, force=False):
    if not force and not doctor_due():
        return None
    _save_state(doctor_week=time.strftime("%G-%V"))
    import aiextra
    try:
        import pcplus
        h = pcplus.health(win)
        hs = f"Helsepoeng {h['score']}/100. " + "; ".join(f"{x['title']} (−{x['minus']})" for x in h["items"])
    except Exception:  # noqa: BLE001
        hs = ""
    prompt = ("Du er PC-legen min. Lag ukas helserapport for PC-en (maks 10 linjer, punktvis, med emojier). Bruk "
              "«ks status», «ks diagnose», «ks logg» og «ks systemsjekk» (bare les). " + hs +
              " Ta med de 3 viktigste tingene å fikse denne uka, og for hver: hvordan, og hvilken «ks gjør …»-kommando "
              "jeg kan godta hvis du kan fikse det. Ikke endre noe nå.")
    tool, text, tools = aiextra.ask_sync(prompt)
    if not text:
        return "Fikk ingen rapport"
    import ai_store as S
    c = S.new(tool)
    c["title"] = time.strftime("🩺 PC-legen uke %V")
    c["emoji"] = "🩺"
    c["messages"] = [{"role": "user", "text": "Ukas helserapport", "t": time.time()},
                     {"role": "assistant", "text": text, "t": time.time(), "tool": tool, "tools": tools}]
    S.save(c)
    if notify:
        from gi.repository import GLib
        first = next((ln for ln in text.splitlines() if ln.strip()), text)[:160]
        GLib.idle_add(lambda: (notify("ai_doctor", "🩺 Ukas rapport fra PC-legen", first + " – svar «fiks det» i "
                                      "AI-samtalen", force=True, action="app.show"), False)[1])
    return "Rapporten ligger under AI"


def tick(win, notify):
    """Kalles hvert 10. minutt."""
    try:
        import ai
        import funksjoner
        if not funksjoner.on("ai") or not ai.cfg().get("doctor", True):
            return
    except Exception:  # noqa: BLE001
        return
    if doctor_due():
        threading.Thread(target=lambda: weekly_doctor(win, notify), daemon=True).start()
