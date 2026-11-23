"""Chatten koblet til resten av Kontrollsenter (runde 3).

Status ved navnet (🟢/🎮), «Spill sammen»-kort, lobby, høydepunkter og ukens toppliste i en kanal, hurtigsvar,
viktige meldinger inni spillet (og lest høyt), barnefilter, stille timer, blokkering, @pc-spørsmål, PC-status-kort,
«Ring», oppgaver med «Gjort», handleliste (+melk), «hvor er alle», del spilloppsett, «Vis skjermen min»,
rommet «Meg», QR-vennekode, lenkeforhåndsvisning og foreldrerapport.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

IS_WIN = sys.platform == "win32"
CFG = os.path.expanduser("~/.config/systemmonitor/chat-kobling.json")
DEF = {"share_highlights": "", "weekly_room": "", "announce_games": "", "blocked": [], "read_aloud": False,
       "quiet": True, "filter": None, "quick": ["Kommer! 🏃", "5 min til ⏳", "Lagrer nå 💾", "Kan ikke nå 🙅"]}
_PRES = {}           # medlem-ID -> {"game", "status", "t", "name", "avatar", "color"}
_RING = {"on": False}
_TITLES = {}


def cfg():
    try:
        d = json.load(open(CFG))
    except (OSError, ValueError):
        d = {}
    return {**DEF, **d}


def set_(**kw):
    d = cfg()
    d.update(kw)
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    json.dump(d, open(CFG, "w"), ensure_ascii=False)
    return d


def _me():
    import chatsrv
    return chatsrv.me()


# --------------------------------------------------------------------------
# 12 / 75 / 76 – status ved navnet
# --------------------------------------------------------------------------
def my_presence(win=None):
    import chatplus
    p = chatplus.my_profile()
    game = getattr(getattr(win, "bg", None), "game_name", None) if win else None
    try:
        import chatvoice
        pub = chatvoice.my_pub()
    except Exception:  # noqa: BLE001
        pub = None
    try:
        import chatextra
        since = chatextra.game_since(game)
    except Exception:  # noqa: BLE001
        since = 0
    return {"game": game, "since": since, "status": p["status"], "avatar": p["avatar"], "color": p["color"],
            "t": time.time(),
            **({"pub": pub} if pub else {})}


def broadcast_presence(win):
    import chatsrv
    pres = my_presence(win)
    for srv in chatsrv.visible_servers().values():
        threading.Thread(target=chatsrv.broadcast, args=(srv, {"type": "presence", **pres}), daemon=True).start()


def on_presence(sender, ev):
    try:
        since = float(ev.get("since") or 0)
    except (TypeError, ValueError):
        since = 0
    _PRES[sender["id"]] = {"name": sender["name"], "game": ev.get("game"), "since": since,
                           "status": str(ev.get("status") or "")[:80],
                           "avatar": str(ev.get("avatar") or "")[:4], "color": str(ev.get("color") or "")[:9],
                           "t": time.time()}


def presence(mid):
    """(ikon, tekst) for et medlem."""
    p = _PRES.get(mid)
    if mid == _me()["id"]:
        p = {**my_presence(), "t": time.time()}
    if not p or time.time() - p["t"] > 600:
        return "⚫", "av"
    if p.get("game"):
        return "🎮", f"spiller {p['game']}"
    return "🟢", p.get("status") or "på"


def avatar(mid):
    p = _PRES.get(mid) or ({**my_presence()} if mid == _me()["id"] else {})
    return p.get("avatar") or "", p.get("color") or ""


# --------------------------------------------------------------------------
# 11 / 63 / 58 / 60 – kort: spill sammen, lobby, oppgave, middag
# --------------------------------------------------------------------------
def send_play(room, game, notify=None):
    import chat
    return chat.send(room, f"🎮 Bli med i {game}!", None, notify, extra={"kind": "play", "play": {"game": game}})


def join_play(game):
    import launcher
    g = next((x for x in launcher.all_games() if x["name"] == game), None)
    if not g:
        raise RuntimeError(f"{game} er ikke installert her")
    launcher.launch(g)
    return f"Starter {game}"


def send_lobby(room, game, need=2, notify=None):
    import chat
    return chat.send(room, f"🕹️ Lobby: {game} – trenger {need}", None, notify,
                     extra={"kind": "lobby", "poll": {"options": ["🙋 Jeg er med"], "need": int(need), "game": game}})


def lobby_check(room, msg):
    """Kalles etter en stemme: er lobbyen full? Den som laget den sier fra (én gang)."""
    poll = msg.get("poll") or {}
    if msg.get("kind") != "lobby" or msg.get("ready") or msg.get("from_id") != _me()["id"]:
        return
    who = (msg.get("votes") or {}).get("0", [])
    if len(who) >= int(poll.get("need", 2)):
        import chat
        with chat._LOCK:
            d = chat._load(chat.FILE, {})
            for m in d.get(room) or []:
                if m.get("id") == msg["id"]:
                    m["ready"] = True
            chat._save(chat.FILE, d)
        chat.send(room, f"✅ Alle er klare for {poll.get('game')}: {', '.join(who)} – start spillet! 🎮")


def send_task(room, text, notify=None):
    import chat
    return chat.send(room, f"📋 {text}", None, notify, extra={"kind": "task", "poll": {"options": ["✅ Gjort"]}})


def dinner_poll(room, notify=None):
    import chatplus
    return chatplus.send_poll(room, "🍽️ Hva skal vi spise?", ["Pizza 🍕", "Taco 🌮", "Burger 🍔", "Noe annet"], notify)


# --------------------------------------------------------------------------
# 13 / 14 / 67 – automatiske innlegg
# --------------------------------------------------------------------------
def post_highlight(clip_path, label):
    room = cfg()["share_highlights"]
    if not room:
        return
    import chatplus
    try:
        chatplus.send_file(room, clip_path, f"🏆 {label}")
    except Exception:  # noqa: BLE001
        pass


def weekly_post():
    room = cfg()["weekly_room"]
    lt = time.localtime()
    if not room or lt.tm_wday != 6 or lt.tm_hour < 20 or cfg().get("weekly_done") == time.strftime("%Y-%W"):
        return
    set_(weekly_done=time.strftime("%Y-%W"))
    try:
        import gamesplus
        import chat
        top = gamesplus.house_toplist()
        txt = "🏆 Ukens toppliste: " + " · ".join(f"{i + 1}. {g} ({h:.0f} t)" for i, (g, h, _p) in enumerate(top[:5]))
        chat.send(room, txt if top else "🏆 Ingen spilletid denne uka – neste uke!")
    except Exception:  # noqa: BLE001
        pass


def announce_game(game):
    room = cfg()["announce_games"]
    if room and game:
        import chat
        threading.Thread(target=lambda: chat.send(room, f"🎮 {_me()['name']} startet {game}"), daemon=True).start()


# --------------------------------------------------------------------------
# 17 / 39 / 18 / 20 / 21 – viktig, lest høyt, filter, stille timer, blokkering
# --------------------------------------------------------------------------
BAD = re.compile(r"\b(faen|fan|helvete|jævla|jævel|dritt|kuk|fitte|hore|idiot|fuck\w*|shit\w*|bitch\w*|"
                 r"dick\w*|ass(?:hole)?|retard\w*)\b", re.I)


def child_mode():
    v = cfg()["filter"]
    if v is not None:
        return bool(v)
    try:
        import familylock
        return familylock.locked()
    except Exception:  # noqa: BLE001
        return False


def clean(text):
    return BAD.sub(lambda m: m.group(0)[0] + "*" * (len(m.group(0)) - 1), text or "") if child_mode() else text


def quiet_now():
    if not cfg()["quiet"]:
        return False
    try:
        import features
        b = features.cfg().get("bedtime") or {}
        if not b.get("enabled"):
            return False
        lt = time.localtime()
        when = b.get("weekend") if lt.tm_wday in (4, 5) else b.get("weekday")
        hh, mm = (int(x) for x in str(when).split(":"))
        now = lt.tm_hour * 60 + lt.tm_min
        return now >= hh * 60 + mm or now < 7 * 60
    except Exception:  # noqa: BLE001
        return False


def blocked(name_or_id):
    return str(name_or_id) in cfg()["blocked"]


def block(name):
    b = cfg()["blocked"]
    if name not in b:
        b.append(name)
    set_(blocked=b)


def unblock(name):
    set_(blocked=[x for x in cfg()["blocked"] if x != name])


def speak(text):
    text = re.sub(r"[^\w\s.,!?æøåÆØÅ-]", "", text)[:200]
    try:
        if IS_WIN:
            ps = ("Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                  f"$s.Speak('{text.replace(chr(39), '')}')")
            subprocess.Popen(["powershell", "-NoProfile", "-Command", ps], creationflags=0x08000000)
        elif shutil.which("spd-say"):
            subprocess.Popen(["spd-say", "-l", "nb", text])
        elif shutil.which("espeak-ng"):
            subprocess.Popen(["espeak-ng", "-v", "nb", text])
    except Exception:  # noqa: BLE001
        pass


def on_incoming(room, msg, win):
    """Fra chat._alert: viktig inni spillet, lest høyt, ring, @pc-spørsmål, handleliste."""
    text = str(msg.get("text") or "")
    game = getattr(getattr(win, "bg", None), "game_name", None) if win else None
    me = _me()
    mention = f"@{me['name'].lower()}" in text.lower()
    important = room.startswith("p:") or mention or msg.get("kind") == "ring"
    if game and important:
        try:
            import familysafe
            familysafe.ingame(f"💬 {msg.get('from')}: {text[:80]}", 20)
        except Exception:  # noqa: BLE001
            pass
        if cfg()["read_aloud"]:
            speak(f"{msg.get('from')} sier: {text}")
    if msg.get("kind") == "ring":
        start_ring(msg.get("from"))
    m = re.match(r"@(pc|" + re.escape(me["name"]) + r")\b[\s,:]*(.+)", text, re.I)
    if m and msg.get("from_id") != me["id"] and not str(msg.get("from", "")).startswith("🤖"):
        threading.Thread(target=_answer, args=(room, m.group(2), win), daemon=True).start()
    if room == "hjemme" or room.startswith("s:"):
        for item in re.findall(r"(?m)^\+\s*(.{2,40})$", text):
            try:
                shop_add(item.strip())
            except Exception:  # noqa: BLE001
                pass


# --------------------------------------------------------------------------
# 22 – @pc: bare spørsmål (ingen styring fra chatten)
# --------------------------------------------------------------------------
QUERIES = ("hvor varm", "temperatur", "hvem spiller", "hvem er på", "hvorfor treg", "hvorfor hakker", "hvor er alle",
           "status", "handleliste")


def _answer(room, q, win):
    import chat
    ql = q.lower()
    if not any(k in ql for k in QUERIES):
        ans = "Fra chatten svarer jeg bare på spørsmål: hvor varm, hvem spiller, hvorfor treg, hvor er alle, status, " \
              "handleliste"
    elif "hvor er alle" in ql:
        ans = where_is_everyone()
    elif "status" in ql:
        ans = status_card(win)
    elif "handleliste" in ql:
        items = shop_list()
        ans = ("🛒 " + ", ".join(items)) if items else "🛒 Handlelista er tom"
    else:
        import apppanels
        ans = apppanels.run_text(win, ql)
    chat.send(room, f"🤖 {_me()['name']}: {ans}")


def where_is_everyone():
    parts = []
    try:
        import presence
        st = presence.state()
        home = [p["name"] for p in st.get("phones", []) if p.get("home")]
        away = [p["name"] for p in st.get("phones", []) if not p.get("home")]
        if home:
            parts.append("🏠 hjemme: " + ", ".join(home))
        if away:
            parts.append("🚶 borte: " + ", ".join(away))
    except Exception:  # noqa: BLE001
        pass
    try:
        import familyfun
        on = [x for x in familyfun.who_is_on() if x["online"]]
        if on:
            parts.append("💻 " + ", ".join(f"{x['name']}" + (f" (🎮 {x['game']})" if x.get("game") else "") for x in on))
    except Exception:  # noqa: BLE001
        pass
    return " · ".join(parts) or "Vet ikke – ingen telefoner eller PC-er er satt opp"


def status_card(win):
    """23: kort med PC-ens tilstand."""
    if win is None:
        return "–"
    nv = win.nvidia.data if getattr(win, "nvidia", None) and win.nvidia.available else {}
    bits = [f"CPU {getattr(win, '_cpu_t', 0) or 0:.0f} °C / {getattr(win, '_cpu_load', 0) or 0:.0f} %"]
    if nv:
        bits.append(f"GPU {nv.get('temp', 0):.0f} °C / {nv.get('util', 0):.0f} %")
    pw = (getattr(win, "_power", None) or {}).get("total")
    if pw:
        bits.append(f"{pw:.0f} W")
    game = getattr(getattr(win, "bg", None), "game_name", None)
    if game:
        bits.append(f"🎮 {game}")
        try:
            import remote
            fps = remote._live_fps(win)
            if fps:
                bits.append(f"{fps} FPS")
        except Exception:  # noqa: BLE001
            pass
    return "📊 " + " · ".join(bits)


# --------------------------------------------------------------------------
# 57 – ring
# --------------------------------------------------------------------------
def send_ring(room, notify=None):
    import chat
    return chat.send(room, "🔔 Ringer deg – svar i chatten!", None, notify, extra={"kind": "ring"})


def start_ring(who):
    if _RING["on"]:
        return
    _RING["on"] = True

    def run():
        import chatplus
        snd = "/usr/share/sounds/freedesktop/stereo/phone-incoming-call.oga"
        for _ in range(6):
            if not _RING["on"]:
                break
            if not IS_WIN and os.path.exists(snd):
                chatplus.play(snd)
            elif IS_WIN:
                try:
                    import winsound
                    winsound.MessageBeep(0x40)
                except Exception:  # noqa: BLE001
                    pass
            try:
                import familysafe
                familysafe.ingame(f"🔔 {who} ringer deg – svar i chatten", 9)
            except Exception:  # noqa: BLE001
                pass
            time.sleep(10)
        _RING["on"] = False
    threading.Thread(target=run, daemon=True).start()


def stop_ring():
    _RING["on"] = False


# --------------------------------------------------------------------------
# 59 – handleliste (felles på NAS-en)
# --------------------------------------------------------------------------
_SHOP = {"t": 0, "items": []}
SHOP_LOCAL = os.path.expanduser("~/.cache/systemmonitor/handleliste.json")


def shop_list(max_age=60):
    if time.time() - _SHOP["t"] < max_age:
        return _SHOP["items"]
    items = None
    try:
        import lanupdate as L
        if L.on_lan():
            d = tempfile.mkdtemp()
            try:
                L._smb(f'cd "Familie"; get "handleliste.json" "{d}/h.json"', 20)
                items = json.load(open(f"{d}/h.json")).get("items")
            except Exception:  # noqa: BLE001
                items = None
            finally:
                shutil.rmtree(d, ignore_errors=True)
    except Exception:  # noqa: BLE001
        pass
    if items is None:
        try:
            items = json.load(open(SHOP_LOCAL)).get("items", [])
        except (OSError, ValueError):
            items = []
    _SHOP.update(t=time.time(), items=items)
    return items


def _shop_save(items):
    os.makedirs(os.path.dirname(SHOP_LOCAL), exist_ok=True)
    json.dump({"items": items}, open(SHOP_LOCAL, "w"), ensure_ascii=False)
    _SHOP.update(t=time.time(), items=items)
    try:
        import lanupdate as L
        if L.on_lan():
            _h, _s, folder = L._split()
            L.smb_mkdir(f"{folder}/Familie")
            L._smb(f'cd "Familie"; put "{SHOP_LOCAL}" "handleliste.json"', 20)
    except Exception:  # noqa: BLE001
        pass


def shop_add(item):
    items = shop_list(0)
    if item.lower() not in [x.lower() for x in items]:
        items.append(item[:40])
        _shop_save(items)
    return items


def shop_remove(item):
    items = [x for x in shop_list(0) if x.lower() != item.lower()]
    _shop_save(items)
    return items


# --------------------------------------------------------------------------
# 68 – del spilloppsett, 38 – vis skjermen min, 69 – Meg, 65 – QR, 44 – lenker, 56 – foreldrerapport
# --------------------------------------------------------------------------
def share_setup(room, game_name, notify=None):
    import games
    import gamesplus
    import chat
    g = next((x for x in games.installed_games() if x["name"] == game_name), None)
    if not g:
        raise RuntimeError("bare Steam-spill kan deles")
    gamesplus.share_profile(g["appid"], g["name"])
    return chat.send(room, f"⚙️ Oppsettet mitt for {g['name']} er delt – trykk «Bruk» for å prøve det", None, notify,
                     extra={"kind": "setup", "setup": {"appid": g["appid"], "name": g["name"]}})


def use_setup(appid):
    import gamesplus
    prof = next((p for p in gamesplus.shared_profiles() if str(p.get("appid")) == str(appid)), None)
    if not prof:
        raise RuntimeError("fant ikke oppsettet på NAS-en")
    return gamesplus.use_profile(prof)


def share_screen(room, notify=None):
    import chat
    import savegames
    return chat.send(room, f"📺 {savegames.pc_name()} deler skjermen – trykk «Se på»", None, notify,
                     extra={"kind": "screen", "screen": {"pc": savegames.pc_name()}})


def friend_qr_text():
    import friends
    return friends.invite()


def link_title(url):
    """Tittelen på en nettside (mellomlagret). Ikke for adresser på hjemmenettet."""
    if url in _TITLES:
        return _TITLES[url]
    if re.match(r"https?://(127\.|192\.168\.|10\.|100\.|localhost)", url):
        return None
    title = None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Kontrollsenter"})
        with urllib.request.urlopen(req, timeout=6) as r:
            html = r.read(60000).decode("utf-8", "replace")
        m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', html, re.I) or \
            re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
        if m:
            import html as H
            title = H.unescape(m.group(1)).strip()[:120]
    except Exception:  # noqa: BLE001
        title = None
    _TITLES[url] = title
    return title


def parent_report():
    """Hvem barnet har chattet med denne uka (navn og antall – ikke innholdet)."""
    import chat
    d = chat._load(chat.FILE, {})
    me = _me()
    week = time.time() - 7 * 86400
    who = {}
    for room, msgs in d.items():
        if room.startswith("_") or not isinstance(msgs, list):
            continue
        for m in msgs:
            if m.get("t", 0) > week and m.get("from_id") != me["id"] and not str(m.get("from", "")).startswith("🤖"):
                who[m.get("from")] = who.get(m.get("from"), 0) + 1
    return sorted(who.items(), key=lambda kv: -kv[1])


def parent_tick():
    if not child_mode():
        return
    lt = time.localtime()
    if lt.tm_wday != 6 or lt.tm_hour < 19 or cfg().get("report_done") == time.strftime("%Y-%W"):
        return
    set_(report_done=time.strftime("%Y-%W"))
    rows = parent_report()
    txt = "Chattet med: " + (", ".join(f"{n} ({k})" for n, k in rows[:10]) if rows else "ingen denne uka")
    try:
        import push
        import savegames
        push.publish("chat", f"💬 Chat-uka på {savegames.pc_name()}", txt)
    except Exception:  # noqa: BLE001
        pass


_T = {"pres": 0}


def tick(win):
    if time.time() - _T["pres"] > 120:
        _T["pres"] = time.time()
        try:
            broadcast_presence(win)
        except Exception:  # noqa: BLE001
            pass
    for fn in (weekly_post, parent_tick):
        try:
            fn()
        except Exception:  # noqa: BLE001
            pass
