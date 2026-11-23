"""Chat for alle som har Kontrollsenter: hjemme, vennene (Tailscale) og privat.

Rom:
  hjemme        familie-chatten (de andre PC-ene hjemme, via NAS-en – som før)
  alle          alle PC-ene hjemme + alle vennene dine
  p:<navn>      privat med én PC hjemme eller én venn

Vennene får meldingene direkte (POST /api/friend/chat). Mottakeren godtar bare meldinger fra en adresse som står i
sin egen venneliste – fremmede kan ikke skrive. Er noen av (eller borte), ligger meldingen i en kø og sendes når de
svarer igjen (i opptil 3 døgn).
"""
import json
import os
import threading
import time
import urllib.parse
import urllib.request

DATA = os.path.expanduser("~/.local/share/systemmonitor")
FILE = os.path.join(DATA, "chat-rom.json")
OUTBOX = os.path.join(DATA, "chat-ut.json")
_LOCK = threading.Lock()
_LISTENERS = []
KEEP = 300


def _me():
    import savegames
    return savegames.pc_name()


def _load(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _save(path, data):
    os.makedirs(DATA, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def on_message(fn):
    _LISTENERS.append(fn)


def _fire(room, msg):
    for fn in list(_LISTENERS):
        try:
            from gi.repository import GLib
            GLib.idle_add(lambda f=fn: (f(room, msg), False)[1])
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------
# Rom og meldinger
# --------------------------------------------------------------------------
_TS = {"t": 0, "v": None}


def tailscale():
    """{"installed", "running"} – chatten med venner går over Tailscale (mellomlagret 30 s)."""
    if _TS["v"] is not None and time.time() - _TS["t"] < 30:
        return _TS["v"]
    try:
        import friends
        st = friends.tailscale_self()
        running = bool(st.get("running") and st.get("ip"))
    except Exception:  # noqa: BLE001
        running = False
    try:
        import apps
        installed = bool(apps.installed("tailscale")) or running
    except Exception:  # noqa: BLE001
        installed = running
    _TS.update(t=time.time(), v={"installed": installed, "running": running})
    return _TS["v"]


MIN_CHAT = (0, 83, 0)                                   # eldre versjoner kan ikke servere, tale eller samtaler


def _ver(v):
    try:
        return tuple(int(x) for x in str(v).split(".")[:3])
    except ValueError:
        return (0, 0, 0)


def room_groups(pins=()):
    """Direktemeldingene gruppert: [(gruppenavn, [(rom-id, navn, ikon, uleste, merknad)])]."""
    flat = {rid: (rid, name, icon, unread) for rid, name, icon, unread in rooms() if not rid.startswith("s:")}
    old = {}
    home = []
    try:
        import homepcs
        for p in homepcs.fetch() or []:
            n = p.get("name")
            if n and n != _me():
                home.append(f"p:{n}")
                if p.get("version") and _ver(p["version"]) < MIN_CHAT:
                    old[f"p:{n}"] = f"⚠️ {p['version']} – må oppdateres"
    except Exception:  # noqa: BLE001
        pass
    groups = [("Festet", [r for r in pins if r in flat]),
              ("Felles", [r for r in ("hjemme", "alle", "meg") if r in flat and r not in pins]),
              ("PC-er hjemme", [r for r in home if r in flat and r not in pins]),
              ("Venner", [r for r in flat if r.startswith("p:") and r not in home and r not in pins])]
    out = []
    for title, ids in groups:
        if ids:
            out.append((title, [(*flat[r], old.get(r, "")) for r in ids]))
    return out


def rooms():
    """[(rom-id, visningsnavn, ikon, uleste)]"""
    out = [("hjemme", "Hjemme", "🏠"), ("alle", "Alle (hjemme + venner)", "🌍"), ("meg", "Meg (notater og lenker)", "📌")]
    seen = set()
    try:
        import homepcs
        for p in homepcs.fetch() or []:
            n = p.get("name")
            if n and n != _me() and n not in seen:
                seen.add(n)
                out.append((f"p:{n}", n, "💻"))
    except Exception:  # noqa: BLE001
        pass
    try:
        import friends
        for f in friends.cfg()["friends"]:
            n = f.get("name")
            if n and n not in seen:
                seen.add(n)
                out.append((f"p:{n}", n, "👋"))
    except Exception:  # noqa: BLE001
        pass
    try:                                                  # serverkanaler («Server › #kanal»)
        import chatsrv
        for srv in chatsrv.visible_servers().values():
            for c in srv.get("categories", []):
                for ch in c.get("channels", []):
                    out.append((f"s:{srv['id']}:{ch['id']}",
                                f"{srv['name']} › {'🔊' if ch.get('kind') == 'voice' else '#'}{ch['name']}",
                                srv.get("icon", "🎮")))
    except Exception:  # noqa: BLE001
        pass
    d = _load(FILE, {})
    read = d.get("_read", {})
    res = []
    for rid, name, icon in out:
        msgs = messages(rid, 200)
        unread = sum(1 for m in msgs if m.get("t", 0) > read.get(rid, 0) and m.get("from") != _me())
        res.append((rid, name, icon, unread))
    return res


def messages(room, limit=100):
    if room == "hjemme":
        import features
        return [{**m, "room": "hjemme"} for m in features.chat_list(limit)]
    d = _load(FILE, {})
    return (d.get(room) or [])[-limit:]


def mark_read(room):
    with _LOCK:
        d = _load(FILE, {})
        d.setdefault("_read", {})[room] = time.time()
        _save(FILE, d)


def _store(room, msg):
    if room == "hjemme":
        return
    with _LOCK:
        d = _load(FILE, {})
        lst = d.setdefault(room, [])
        if any(m.get("id") == msg.get("id") for m in lst[-50:]):   # samme melding to ganger (ny sending fra kø)
            return False
        lst.append(msg)
        d[room] = lst[-KEEP:]
        _save(FILE, d)
    return True


# --------------------------------------------------------------------------
# Sende
# --------------------------------------------------------------------------
def _friend(name):
    try:
        import friends
        return next((f for f in friends.cfg()["friends"] if f.get("name") == name), None)
    except Exception:  # noqa: BLE001
        return None


def _home_pc(name):
    try:
        import homepcs
        return next((p for p in homepcs.fetch() or [] if p.get("name") == name), None)
    except Exception:  # noqa: BLE001
        return None


def _post_friend(f, payload, timeout=6):
    import friends
    last = None
    for a in friends.addrs(f)[:4]:
        url = f"http://{a}:{f.get('port', 27100)}/api/friend/chat?k=" + urllib.parse.quote(f["key"])
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": "Kontrollsenter"})
        try:
            with urllib.request.urlopen(req, timeout=min(timeout, 4)) as r:
                d = json.load(r)
            friends.good(f, a)
            return d
        except urllib.error.HTTPError:
            raise
        except Exception as e:  # noqa: BLE001
            last = e
    raise last or RuntimeError("svarer ikke")


def send(room, text, frm=None, notify=None, extra=None):
    """Send en melding i et rom. Returnerer tekst om hvordan det gikk."""
    text = str(text or "").strip()[:500]
    if not text:
        raise ValueError("tom melding")
    me = _me()
    frm = frm or me
    if room == "hjemme":
        import features
        features.send_to("*", frm, text, notify)
        return "Sendt til PC-ene hjemme"
    if room.startswith("s:"):                             # serverkanal: direkte til alle medlemmene
        import chatsrv
        _s, sid, ch = room.split(":", 2)
        srv = chatsrv.get(sid)
        if not srv or not chatsrv.channel(srv, ch):
            raise ValueError("fant ikke kanalen")
        msg = {"id": f"{chatsrv.me()['id']}-{time.time_ns()}", "t": time.time(), "from": frm, "pc": me,
               "from_id": chatsrv.me()["id"], "text": text, "room": room, **(extra or {})}
        local = dict(msg)
        if local.get("attach", {}).get("data"):
            local["attach"] = {k: v for k, v in local["attach"].items() if k != "data"}
        _store(room, local)
        _fire(room, local)
        ok, q = chatsrv.broadcast(srv, {"type": "msg", "ch": ch, **{k: v for k, v in msg.items() if k != "room"}})
        try:
            import chatplus
            chatplus.delivered(msg["id"], ok)
        except Exception:  # noqa: BLE001
            pass
        return f"Sendt til {ok}" + (f" · {q} får den når de er på igjen" if q else "")
    msg = {"id": f"{me}-{time.time_ns()}", "t": time.time(), "from": frm, "pc": me, "text": text, "room": room}
    for k in ("kind", "invite", "call_id"):                # samtaler uten server (chatcall.py)
        if (extra or {}).get(k):
            msg[k] = str(extra[k])[:400]
    _store(room, msg)
    _fire(room, msg)
    if room == "meg":                                     # bare her (og mobilappen din)
        return "Lagret i Meg"
    targets = []                                            # (type, mål)
    if room == "alle":
        try:
            import friends
            targets += [("venn", f) for f in friends.cfg()["friends"]]
        except Exception:  # noqa: BLE001
            pass
        try:
            import homepcs
            targets += [("hjem", p["name"]) for p in homepcs.fetch() or [] if p.get("name") and p["name"] != me]
        except Exception:  # noqa: BLE001
            pass
    elif room.startswith("p:"):
        name = room[2:]
        f = _friend(name)
        if _home_pc(name):                                  # i huset: hjemmenettet først (virker uten Tailscale)
            targets.append(("hjem", name))
        elif f:
            targets.append(("venn", f))
        else:
            raise ValueError("fant ikke mottakeren")
    ok = queued = 0
    for kind, t in targets:
        payload = {**msg, "room": "alle" if room == "alle" else f"p:{me}"}   # hos mottakeren heter privatrommet meg
        if _deliver(kind, t, payload):
            ok += 1
        else:
            _queue(kind, t, payload)
            queued += 1
    if not targets:
        return "Ingen å sende til ennå – legg til venner under PC-er utenfor hjemmet"
    return f"Sendt til {ok}" + (f" · {queued} får den når de er på igjen" if queued else "")


HOME_PORT = 27100


def _home_direct(name, payload):
    """Rett til PC-en hjemme over hjemmenettet (husnøkkelen) – sekunder i stedet for NAS-postkassen."""
    try:
        import homepcs
        import watch
        key = watch.house_key()
        pc = next((p for p in homepcs.fetch() or [] if p.get("name") == name), None)
        if not key or not pc:
            return False
        for ip in (pc.get("ips") or [])[:3]:
            try:
                req = urllib.request.Request(
                    f"http://{ip}:{HOME_PORT}/api/house/chat?fk=" + urllib.parse.quote(key),
                    data=json.dumps(payload, ensure_ascii=False).encode(), method="POST",
                    headers={"Content-Type": "application/json", "User-Agent": "Kontrollsenter"})
                with urllib.request.urlopen(req, timeout=3) as r:
                    if json.load(r).get("ok"):
                        return True
            except Exception:  # noqa: BLE001 – eldre versjon eller av: NAS-postkassen tar den
                continue
    except Exception:  # noqa: BLE001
        pass
    return False


def _deliver(kind, target, payload):
    try:
        if kind == "venn":
            try:
                if _post_friend(target, payload, timeout=4).get("ok"):
                    return True
            except Exception:  # noqa: BLE001 – Tailscale-adressen svarer ikke: prøv hjemmenettet
                pass
            name = target.get("name")
            if name and _home_pc(name):
                return _home_direct(name, payload) or _deliver_nas(name, payload)
            return False
        if _home_direct(target, payload):
            return True
        f = _friend(target)                                 # ikke på hjemmenettet nå: som venn over Tailscale
        if f:
            try:
                if _post_friend(f, payload, timeout=4).get("ok"):
                    return True
            except Exception:  # noqa: BLE001
                pass
        return _deliver_nas(target, payload)
    except Exception:  # noqa: BLE001
        return False


def _deliver_nas(target, payload):
    """Reserve: NAS-postkassen (PC-en henter den innen et minutt)."""
    try:
        import features
        features.nas_send(target, payload["from"], json.dumps({"_chat2": payload}, ensure_ascii=False))
        return True
    except Exception:  # noqa: BLE001
        return False


def _queue(kind, target, payload):
    with _LOCK:
        q = _load(OUTBOX, [])
        key = target.get("addr") if kind == "venn" else target.get("member") if kind == "srv" else target
        q.append({"kind": kind, "to": key, "name": target.get("name") if kind == "venn" else target,
                  "payload": payload, "t": time.time()})
        _save(OUTBOX, q[-500:])


def retry_outbox():
    """Fra bakgrunnen: prøv køen på nytt (meldinger eldre enn 3 døgn droppes)."""
    with _LOCK:
        q = _load(OUTBOX, [])
    if not q:
        return 0
    left, sent = [], 0
    for e in q:
        if time.time() - e["t"] > 3 * 86400:
            continue
        if e["kind"] == "srv":
            import chatsrv
            if chatsrv._post(e["to"], e["payload"]):
                sent += 1
                continue
            if time.time() - e["t"] > 3 * 86400:
                continue
            left.append(e)
            continue
        if e["kind"] == "venn":
            f = _friend(e.get("name")) or next((x for x in __import__("friends").cfg()["friends"]
                                                if x.get("addr") == e["to"]), None)
            if f and _deliver("venn", f, e["payload"]):
                sent += 1
                continue
        elif _deliver("hjem", e["to"], e["payload"]):
            sent += 1
            continue
        left.append(e)
    with _LOCK:
        _save(OUTBOX, left)
    return sent


def queued_count():
    return len(_load(OUTBOX, []))


# --------------------------------------------------------------------------
# Motta
# --------------------------------------------------------------------------
def _call_fields(payload, msg):
    """Samtale-invitasjon i en direktemelding: ta vare på feltene og si fra (chatcall.on_message)."""
    if payload.get("kind") in ("call", "call_end", "call_no") and payload.get("call_id"):
        for k in ("kind", "invite", "call_id"):
            if payload.get(k):
                msg[k] = str(payload[k])[:400]
        try:
            import chatcall
            chatcall.on_message(msg)
        except Exception:  # noqa: BLE001
            pass


def receive_friend(payload, src_ip, notify=None):
    """POST /api/friend/chat: bare fra adresser i vennelista."""
    import friends
    import socket

    def ip_of(a):
        try:
            return socket.gethostbyname(a)
        except OSError:
            return None
    f = next((x for x in friends.cfg()["friends"] if x.get("addr") == src_ip), None) or \
        next((x for x in friends.cfg()["friends"] if ip_of(x.get("addr", "")) == src_ip), None)
    if not f:
        raise PermissionError("du står ikke i vennelista til denne PC-en")
    import chatlink
    if chatlink.blocked(f["name"]):
        return True
    room = payload.get("room") or "alle"
    if room.startswith("p:"):
        room = f"p:{f['name']}"                           # privat: rommet heter det JEG kaller vennen
    elif room != "alle":
        room = "alle"
    msg = {"id": str(payload.get("id") or time.time_ns())[:80], "t": time.time(),
           "from": str(payload.get("from") or f["name"])[:40], "pc": f["name"], "text": str(payload.get("text"))[:500],
           "room": room}
    _call_fields(payload, msg)
    if _store(room, msg):
        _alert(room, msg, notify)
    return True


def apply_event(room, ev, sender=None):
    """Reaksjon / redigering / sletting / festing på en melding i et rom."""
    mid = str(ev.get("mid") or "")
    who = (sender or {}).get("name") or str(ev.get("from") or "?")
    who_id = (sender or {}).get("id") or ev.get("from_id")
    with _LOCK:
        d = _load(FILE, {})
        for m in d.get(room) or []:
            if m.get("id") != mid:
                continue
            t = ev.get("type")
            if t == "react":
                e = str(ev.get("emoji") or "")[:8]
                r = m.setdefault("reactions", {}).setdefault(e, [])
                (r.remove if who in r else r.append)(who)
                if not r:
                    m["reactions"].pop(e, None)
            elif t in ("edit", "delete") and (m.get("from_id") == who_id or (sender or {}).get("role") in
                                               ("owner", "admin") and t == "delete"):
                if t == "edit":
                    m["text"], m["edited"] = str(ev.get("text") or "")[:2000], time.time()
                else:
                    m["text"], m["deleted"] = "", True
            elif t == "pin":
                m["pinned"] = bool(ev.get("on", True))
            break
        _save(FILE, d)
    _fire(room, {"event": ev.get("type"), "mid": mid})


def receive_home(payload, notify=None):
    """En melding fra en PC hjemme (via NAS-postkassen)."""
    room = payload.get("room") or "alle"
    if room not in ("alle",) and not room.startswith("p:"):
        room = "alle"
    msg = {"id": str(payload.get("id"))[:80], "t": time.time(), "from": str(payload.get("from"))[:40],
           "pc": str(payload.get("pc"))[:40], "text": str(payload.get("text"))[:500], "room": room}
    _call_fields(payload, msg)
    if _store(room, msg):
        _alert(room, msg, notify)


def _alert(room, msg, notify):
    _fire(room, msg)
    quiet = False
    try:
        import chatplus
        import chatlink
        import remote
        w = getattr(remote, "win", None)
        chatplus.autoreply(room, msg, w)
        chatlink.on_incoming(room, msg, w)
        quiet = chatlink.quiet_now() and msg.get("kind") != "ring" and "🆘" not in str(msg.get("text", ""))
        if not quiet:
            chatplus.play_notify_sound(msg.get("from"))
    except Exception:  # noqa: BLE001
        pass
    if quiet:
        notify = None                                       # stille timer: ingen varsel etter leggetid
    try:                                                    # du ser på akkurat denne samtalen nå: ikke varsle
        import remote
        w = getattr(remote, "win", None)
        if w is not None and w.is_active() and w.stack.get_visible_child_name() == "chat" and \
                getattr(w, "_chat_room", None) == room:
            notify = None
    except Exception:  # noqa: BLE001
        pass
    try:
        import remote_extra
        remote_extra.event("chat", f"💬 {msg['from']}", msg["text"], "info", room=room)
    except Exception:  # noqa: BLE001
        pass
    if notify:
        try:
            from gi.repository import GLib
            where = "" if room.startswith("p:") else " (alle)"
            if room.startswith("s:"):
                import chatsrv
                srv = chatsrv.get(room.split(":")[1]) or {}
                ch = chatsrv.channel(srv, room.split(":")[2]) or {}
                where = f" · #{ch.get('name', '?')} ({srv.get('name', '')})"
            GLib.idle_add(lambda: (notify("chat", f"💬 {msg['from']}{where}", msg["text"], force=True,
                                          action="app.chat"), False)[1])
        except Exception:  # noqa: BLE001
            pass
