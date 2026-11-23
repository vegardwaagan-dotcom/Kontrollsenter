"""Servere i chatten – som Discord: egne servere med kategorier og kanaler, invitasjonslenker, roller og medlemmer
som kan komme og gå.

Modell (uten sky):
  * Den som lager en server er eier. Eieren godkjenner nye medlemmer (invitasjonslenke med kode) og sender ut
    endringer (kanaler, roller, medlemmer) til alle.
  * Meldinger går DIREKTE til alle medlemmene (ikke via eieren) – serveren virker selv om eieren er av.
    Er noen av, ligger meldingen i kø og sendes når de svarer igjen.
  * En PC godtar bare servermeldinger fra medlemmer av den serveren (adressen må stemme), med medlemmets egen
    innboks-kode – fremmede kan ikke skrive.
  * Rom-ID for en kanal: «s:<server>:<kanal>».

Medlem: {"id", "name", "addrs": [...], "port", "key" (innboks-koden), "role": owner|admin|member, "joined"}
"""
import json
import os
import re
import secrets
import threading
import time
import urllib.parse
import urllib.request

DATA = os.path.expanduser("~/.local/share/systemmonitor")
FILE = os.path.join(DATA, "chat-servere.json")
ME_FILE = os.path.expanduser("~/.config/systemmonitor/chat-meg.json")
PORT = 27100
_LOCK = threading.RLock()
ICONS = ["🎮", "🏠", "⚔️", "🚀", "🐉", "🏆", "🎧", "🍕", "🌲", "⭐", "🔥", "🐺"]


# --------------------------------------------------------------------------
# Meg: fast ID og innboks-kode for denne installasjonen
# --------------------------------------------------------------------------
def me():
    try:
        d = json.load(open(ME_FILE))
    except (OSError, ValueError):
        d = {}
    changed = False
    if not d.get("id"):
        d["id"], changed = secrets.token_hex(8), True
    if not d.get("key"):
        d["key"], changed = secrets.token_urlsafe(18), True
    if changed:
        os.makedirs(os.path.dirname(ME_FILE), exist_ok=True)
        json.dump(d, open(ME_FILE, "w"))
    import savegames
    d["name"] = d.get("display") or savegames.pc_name()
    return d


def my_addrs():
    """Adressene andre kan nå meg på: Tailscale først (virker utenfor huset), så hjemmenettet."""
    out = []
    try:
        import friends
        t = friends.tailscale_self()
        if t.get("ip"):
            out.append(t["ip"])
    except Exception:  # noqa: BLE001
        pass
    try:
        import remote
        out += [ip for ip in remote.local_ips() if ip.startswith(("192.168.", "10.", "172."))][:2]
    except Exception:  # noqa: BLE001
        pass
    return out


def me_member(role="member"):
    m = me()
    try:
        import chatvoice
        pub = chatvoice.my_pub()
    except Exception:  # noqa: BLE001
        pub = None
    return {"id": m["id"], "name": m["name"], "addrs": my_addrs(), "port": PORT, "key": m["key"], "role": role,
            "joined": time.time(), **({"pub": pub} if pub else {})}


# --------------------------------------------------------------------------
# Lagring
# --------------------------------------------------------------------------
def _load():
    try:
        return json.load(open(FILE, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(d):
    os.makedirs(DATA, exist_ok=True)
    tmp = FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, FILE)


def servers():
    return _load()


def get(sid):
    return _load().get(sid)


def _put(srv):
    with _LOCK:
        d = _load()
        d[srv["id"]] = srv
        _save(d)


def _drop(sid):
    with _LOCK:
        d = _load()
        d.pop(sid, None)
        _save(d)


def my_role(srv):
    return (srv.get("members", {}).get(me()["id"]) or {}).get("role")


def can_manage(srv):
    return my_role(srv) in ("owner", "admin")


def _nid():
    return secrets.token_hex(4)


# --------------------------------------------------------------------------
# Lage og endre (eier/admin)
# --------------------------------------------------------------------------
def _split_icon(name, icon):
    """«🎮Gaming» i ikonfeltet: emojien blir ikonet og teksten flyttes inn i navnet."""
    icon = str(icon or "").strip()
    lead = ""
    for ch in icon:
        if ch.isalnum() or ch.isspace():
            break
        lead += ch
    rest = icon[len(lead):].strip()
    name = str(name or "").strip()
    if rest and rest.lower() not in name.lower():
        name = f"{rest} {name}".strip()
    return name, lead or "🎮"


def create(name, icon="🎮"):
    name, icon = _split_icon(name, icon)
    sid = secrets.token_hex(6)
    general = _nid()
    srv = {"id": sid, "name": str(name).strip()[:40] or "Server", "icon": icon or "🎮", "v": 1, "created": time.time(),
           "owner": me()["id"], "members": {me()["id"]: me_member("owner")},
           "categories": [{"id": _nid(), "name": "Tekstkanaler", "channels": [
               {"id": general, "name": "generelt", "topic": "Alt mulig"},
               {"id": _nid(), "name": "spill", "topic": "Hva spiller vi?"}]},
               {"id": _nid(), "name": "Talekanaler", "channels": [
                   {"id": _nid(), "name": "lounge", "topic": "Prat og spill", "kind": "voice"}]},
               {"id": _nid(), "name": "Annet", "channels": [{"id": _nid(), "name": "klipp", "topic": "Høydepunkter"}]}],
           "invites": {}}
    _put(srv)
    return srv


def _bump_and_send(srv):
    srv["v"] = int(srv.get("v", 0)) + 1
    _put(srv)
    broadcast_meta(srv)
    return srv


def _need_manage(srv):
    if not srv:
        raise ValueError("fant ikke serveren")
    if not can_manage(srv):
        raise PermissionError("bare eier og admin kan endre serveren")


def rename(sid, name=None, icon=None):
    if icon is not None:
        name, icon = _split_icon(name if name is not None else get(sid)["name"], icon)
    srv = get(sid)
    _need_manage(srv)
    if name:
        srv["name"] = str(name).strip()[:40]
    if icon:
        srv["icon"] = icon
    return _bump_and_send(srv)


def add_category(sid, name):
    srv = get(sid)
    _need_manage(srv)
    srv["categories"].append({"id": _nid(), "name": str(name).strip()[:30] or "Kategori", "channels": []})
    return _bump_and_send(srv)


def rename_category(sid, cid, name):
    srv = get(sid)
    _need_manage(srv)
    for c in srv["categories"]:
        if c["id"] == cid:
            c["name"] = str(name).strip()[:30]
    return _bump_and_send(srv)


def delete_category(sid, cid):
    srv = get(sid)
    _need_manage(srv)
    srv["categories"] = [c for c in srv["categories"] if c["id"] != cid]
    return _bump_and_send(srv)


def _clean_channel(name):
    n = re.sub(r"[^a-z0-9æøå\-_]+", "-", str(name).strip().lower()).strip("-")
    return n[:30] or "kanal"


def add_channel(sid, cid, name, topic="", kind="text"):
    srv = get(sid)
    _need_manage(srv)
    cat = next((c for c in srv["categories"] if c["id"] == cid), None)
    if not cat:
        raise ValueError("fant ikke kategorien")
    ch = {"id": _nid(), "name": _clean_channel(name), "topic": str(topic)[:80]}
    if kind == "voice":                                   # talekanal: lyd og webkamera (chatvc.py)
        ch["kind"] = "voice"
    cat["channels"].append(ch)
    _bump_and_send(srv)
    return ch


def edit_channel(sid, chid, name=None, topic=None):
    srv = get(sid)
    _need_manage(srv)
    for c in srv["categories"]:
        for ch in c["channels"]:
            if ch["id"] == chid:
                if name:
                    ch["name"] = _clean_channel(name)
                if topic is not None:
                    ch["topic"] = str(topic)[:80]
    return _bump_and_send(srv)


def delete_channel(sid, chid):
    srv = get(sid)
    _need_manage(srv)
    for c in srv["categories"]:
        c["channels"] = [ch for ch in c["channels"] if ch["id"] != chid]
    return _bump_and_send(srv)


def move_channel(sid, chid, to_cid):
    srv = get(sid)
    _need_manage(srv)
    ch = None
    for c in srv["categories"]:
        for x in c["channels"]:
            if x["id"] == chid:
                ch = x
        c["channels"] = [x for x in c["channels"] if x["id"] != chid]
    for c in srv["categories"]:
        if c["id"] == to_cid and ch:
            c["channels"].append(ch)
    return _bump_and_send(srv)


def set_role(sid, mid, role):
    srv = get(sid)
    if my_role(srv) != "owner":
        raise PermissionError("bare eieren kan endre roller")
    if role not in ("admin", "member") or mid not in srv["members"] or mid == srv["owner"]:
        raise ValueError("ugyldig")
    srv["members"][mid]["role"] = role
    return _bump_and_send(srv)


def kick(sid, mid):
    srv = get(sid)
    _need_manage(srv)
    if mid == srv["owner"]:
        raise PermissionError("eieren kan ikke kastes ut")
    gone = srv["members"].pop(mid, None)
    _bump_and_send(srv)
    if gone:                                          # si fra til den som ble kastet ut
        _post(gone, {"type": "kicked", "srv": sid, "name": srv["name"], "from_id": me()["id"]})
    return srv


def delete_server(sid):
    srv = get(sid)
    if my_role(srv) != "owner":
        raise PermissionError("bare eieren kan slette serveren")
    for mid, m in srv["members"].items():
        if mid != me()["id"]:
            _send_or_queue(m, {"type": "deleted", "srv": sid, "name": srv["name"], "from_id": me()["id"]})
    _drop(sid)


def leave(sid):
    srv = get(sid)
    if not srv:
        return
    if my_role(srv) == "owner":
        raise PermissionError("du eier serveren – slett den, eller gi bort eierskapet først")
    for mid, m in srv["members"].items():
        if mid != me()["id"]:
            _send_or_queue(m, {"type": "left", "srv": sid, "member": me()["id"], "from_id": me()["id"]})
    _drop(sid)


def give_owner(sid, mid):
    srv = get(sid)
    if my_role(srv) != "owner" or mid not in srv["members"]:
        raise PermissionError("ugyldig")
    srv["members"][srv["owner"]]["role"] = "admin"
    srv["owner"] = mid
    srv["members"][mid]["role"] = "owner"
    return _bump_and_send(srv)


# --------------------------------------------------------------------------
# Invitasjoner og å bli med
# --------------------------------------------------------------------------
def make_invite(sid, uses=0, hours=168):
    srv = get(sid)
    _need_manage(srv)
    tok = secrets.token_urlsafe(9)
    srv.setdefault("invites", {})[tok] = {"by": me()["id"], "t": time.time(), "until": time.time() + hours * 3600,
                                          "uses": int(uses), "used": 0}
    _put(srv)
    addr = (my_addrs() or ["?"])[0]
    return f"ks-server://{addr}:{PORT}/{sid}/{tok}?navn={urllib.parse.quote(srv['name'])}"


def parse_invite(text):
    m = re.search(r"ks-server://([\w.\-]+):(\d+)/([0-9a-f]+)/([\w\-]+)(?:\?navn=(\S+))?", (text or "").strip())
    if not m:
        return None
    return {"addr": m.group(1), "port": int(m.group(2)), "srv": m.group(3), "tok": m.group(4),
            "name": urllib.parse.unquote(m.group(5) or "Server")}


def join(text):
    """Bli med via invitasjonslenke. Spør eieren, som legger meg til og sender serveren tilbake."""
    inv = parse_invite(text)
    if not inv:
        raise ValueError("ugyldig invitasjonslenke (skal starte med ks-server://)")
    body = json.dumps({"srv": inv["srv"], "tok": inv["tok"], "member": me_member()}).encode()
    req = urllib.request.Request(f"http://{inv['addr']}:{inv['port']}/api/chat/join", data=body, method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "Kontrollsenter"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.load(r)
    except Exception as e:  # noqa: BLE001
        if "403" in str(e) or "410" in str(e):
            raise RuntimeError("invitasjonen er brukt opp, utløpt eller ugyldig") from e
        raise RuntimeError(f"fikk ikke kontakt med eieren av serveren ({e})") from e
    srv = d.get("server")
    if not srv:
        raise RuntimeError(d.get("error") or "ble ikke med")
    with _LOCK:                       # en nyere versjon kan ha kommet fra eieren mens vi ventet på svaret
        cur = get(srv["id"])
        if cur and int(cur.get("v", 0)) > int(srv.get("v", 0)):
            srv = {**cur, "invites": srv.get("invites", cur.get("invites", {}))}
        _put(srv)
    return srv


def handle_join(body):
    """Hos eieren: godkjenn en invitasjon og legg til medlemmet."""
    srv = get(str(body.get("srv")))
    if not srv or my_role(srv) not in ("owner", "admin"):
        raise PermissionError("ukjent server")
    inv = (srv.get("invites") or {}).get(str(body.get("tok")))
    if not inv or time.time() > inv.get("until", 0) or (inv.get("uses") and inv.get("used", 0) >= inv["uses"]):
        raise PermissionError("invitasjonen er brukt opp eller utløpt")
    m = body.get("member") or {}
    mid = str(m.get("id") or "")
    if not re.fullmatch(r"[0-9a-f]{16}", mid) or not m.get("key") or not m.get("addrs"):
        raise ValueError("ugyldig medlem")
    if mid in (srv.get("banned") or []):
        raise PermissionError("utestengt")
    inv["used"] = inv.get("used", 0) + 1
    srv["members"][mid] = {"id": mid, "name": str(m.get("name"))[:40], "addrs": [str(a)[:60] for a in m["addrs"][:4]],
                           "port": int(m.get("port") or PORT), "key": str(m["key"])[:60], "role": "member",
                           "joined": time.time(), **({"pub": str(m["pub"])[:60]} if m.get("pub") else {})}
    _bump_and_send(srv)
    _system_msg(srv, f"👋 {srv['members'][mid]['name']} ble med i serveren")
    return srv


def _system_msg(srv, text):
    ch = first_channel(srv)
    if ch:
        import chat
        chat.send(f"s:{srv['id']}:{ch['id']}", text, frm="🤖 Kontrollsenter")


def first_channel(srv):
    """Første tekstkanal (talekanaler hoppes over)."""
    for c in srv.get("categories", []):
        for ch in c.get("channels", []):
            if ch.get("kind") != "voice":
                return ch
    return None


def channel(srv, chid):
    for c in srv.get("categories", []):
        for ch in c.get("channels", []):
            if ch["id"] == chid:
                return ch
    return None


# --------------------------------------------------------------------------
# Sende til medlemmene (direkte, med kø)
# --------------------------------------------------------------------------
def _post(m, payload, timeout=6):
    last = None
    for a in (m.get("addrs") or [])[:3]:
        try:
            url = f"http://{a}:{m.get('port', PORT)}/api/chat/inbox?k=" + urllib.parse.quote(m["key"])
            req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                         headers={"Content-Type": "application/json", "User-Agent": "Kontrollsenter"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if json.load(r).get("ok"):
                    return True
        except Exception as e:  # noqa: BLE001
            last = e
    if last and "403" in str(last):
        return None                                  # avvist (ikke medlem lenger) – ikke legg i kø
    return False


def _send_or_queue(m, payload):
    r = _post(m, payload)
    if r is False:
        import chat
        chat._queue("srv", {"name": m.get("name"), "member": m}, payload)
    return r


def broadcast(srv, payload):
    """Til alle medlemmer unntatt meg. Returnerer (levert, i kø)."""
    ok = q = 0
    mine = me()["id"]
    payload = {**payload, "srv": srv["id"], "from_id": mine}
    try:
        import chatvoice
        seal = chatvoice.seal
    except Exception:  # noqa: BLE001
        seal = None
    for mid, m in srv.get("members", {}).items():
        if mid == mine:
            continue
        r = _send_or_queue(m, seal(m, payload) if seal else payload)
        if r:
            ok += 1
        elif r is False:
            q += 1
    return ok, q


def broadcast_meta(srv):
    snap = {k: v for k, v in srv.items() if k != "invites"}
    return broadcast(srv, {"type": "meta", "server": snap})


# --------------------------------------------------------------------------
# Motta (POST /api/chat/inbox)
# --------------------------------------------------------------------------
def _ip_matches(m, src_ip):
    import socket
    for a in m.get("addrs") or []:
        if a == src_ip:
            return True
        try:
            if socket.gethostbyname(a) == src_ip:
                return True
        except OSError:
            pass
    return src_ip in ("127.0.0.1", "::1") and os.environ.get("KS_CHAT_TEST") == "1"


def receive(payload, src_ip, notify=None):
    """Hos et medlem. Returnerer True, eller kaster PermissionError."""
    t = payload.get("type")
    sid = str(payload.get("srv") or "")
    srv = get(sid)
    if t == "meta":
        new = payload.get("server") or {}
        if not new.get("id") or new.get("id") != sid:
            raise ValueError("ugyldig")
        sender = (srv or new).get("members", {}).get(str(payload.get("from_id")))
        if not sender or sender.get("role") not in ("owner", "admin") or not _ip_matches(sender, src_ip):
            raise PermissionError("bare eier/admin kan endre serveren")
        if srv and int(new.get("v", 0)) <= int(srv.get("v", 0)):
            return True
        new["invites"] = (srv or {}).get("invites", {})
        if me()["id"] not in new.get("members", {}):         # jeg er kastet ut
            _drop(sid)
            _alert(notify, "Du er ikke lenger med i serveren", new.get("name", ""))
            return True
        _put(new)
        _changed(sid)
        return True
    if not srv:
        raise PermissionError("ukjent server")
    sender = srv.get("members", {}).get(str(payload.get("from_id")))
    if not sender or not _ip_matches(sender, src_ip):
        raise PermissionError("ikke medlem")
    if t == "left":
        if sender["id"] == payload.get("member"):
            name = sender["name"]
            srv["members"].pop(sender["id"], None)
            _put(srv)
            if can_manage(srv):
                _bump_and_send(srv)
                _system_msg(srv, f"🚪 {name} forlot serveren")
        return True
    if t in ("kicked", "deleted"):
        if sender.get("role") not in (("owner",) if t == "deleted" else ("owner", "admin")):
            raise PermissionError("ugyldig")
        _drop(sid)
        _alert(notify, "Serveren ble slettet" if t == "deleted" else "Du ble fjernet fra serveren",
               payload.get("name", ""))
        _changed(sid)
        return True
    if t == "msg":
        import chatvoice
        payload = chatvoice.open_sealed(sender, payload)
        ch = str(payload.get("ch") or "")
        if not channel(srv, ch):
            return True                                    # kanalen er slettet
        import chat
        import chatlink
        if chatlink.blocked(sender["name"]) or chatlink.blocked(sender["id"]):
            return True                                   # blokkert: forkast stille
        msg = {k: payload.get(k) for k in ("id", "t", "from", "text", "reply", "attach", "kind", "poll", "event",
                                           "play", "setup", "screen") if payload.get(k) is not None}
        if msg.get("attach"):                              # vedlegg: lagre fila, behold bare beskrivelsen
            import chatplus
            msg["attach"] = chatplus.receive_attach(msg["attach"])
        msg["id"] = str(msg.get("id") or time.time_ns())[:80]
        msg["t"] = time.time()
        msg["from"] = str(msg.get("from") or sender["name"])[:40]
        msg["pc"] = sender["name"]
        msg["from_id"] = sender["id"]
        msg["text"] = str(msg.get("text") or "")[:2000]
        room = f"s:{sid}:{ch}"
        msg["room"] = room
        if payload.get("e2e"):
            msg["e2e"] = True
        if chat._store(room, msg):
            chat._alert(room, msg, notify if not muted(room) else None)
            if msg.get("kind") == "walkie":
                import chatvoice
                chatvoice.on_walkie(msg)
        return True
    if t == "presence":
        import chatlink
        chatlink.on_presence(sender, payload)
        if payload.get("pub") and sender.get("pub") != payload.get("pub"):     # nøkkel til kryptering
            sender["pub"] = str(payload["pub"])[:60]
            _put(srv)
        return True
    if t == "vc":                                         # talekanal: hvem er inne, porter, kamera, demping
        import chatvc
        chatvc.on_event(srv, sender, payload, src_ip)
        return True
    if t in ("call", "call_ok", "call_end"):
        import chatvoice
        if t == "call":
            chatvoice.call_incoming(sender, payload)
            _alert(notify, f"📞 {sender['name']} ringer", "Åpne Chat og trykk «Svar»")
        elif t == "call_ok":
            chatvoice.call_accepted(sender, payload)
        else:
            chatvoice.call_end(notify_peer=False)
        _changed(sid)
        return True
    if t in ("read", "typing"):
        import chatplus
        chatplus.on_event(f"s:{sid}:{payload.get('ch')}", payload, sender)
        if t == "typing":
            import chat
            chat._fire(f"s:{sid}:{payload.get('ch')}", {"event": "typing"})
        return True
    if t == "vote":
        import chatplus
        chatplus._apply_vote(f"s:{sid}:{payload.get('ch')}", payload, sender["name"])
        return True
    if t in ("react", "edit", "delete", "pin"):
        import chat
        chat.apply_event(f"s:{sid}:{payload.get('ch')}", payload, sender)
        return True
    return True


def _alert(notify, title, body):
    if notify:
        try:
            from gi.repository import GLib
            GLib.idle_add(lambda: (notify("chat", title, body, force=True), False)[1])
        except Exception:  # noqa: BLE001
            pass


_LISTENERS = []


def on_change(fn):
    _LISTENERS.append(fn)


def _changed(sid):
    for fn in list(_LISTENERS):
        try:
            from gi.repository import GLib
            GLib.idle_add(lambda f=fn: (f(sid), False)[1])
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------
# Demping per kanal/server
# --------------------------------------------------------------------------
MUTE = os.path.expanduser("~/.config/systemmonitor/chat-demp.json")


def muted(room):
    try:
        d = json.load(open(MUTE))
    except (OSError, ValueError):
        return False
    until = d.get(room) or d.get(room.rsplit(":", 1)[0] if room.startswith("s:") else room)
    return bool(until) and (until == -1 or until > time.time())


def set_mute(room, seconds):
    """seconds: 0 = av, -1 = for alltid, ellers antall sekunder."""
    try:
        d = json.load(open(MUTE))
    except (OSError, ValueError):
        d = {}
    if not seconds:
        d.pop(room, None)
    else:
        d[room] = -1 if seconds == -1 else time.time() + seconds
    os.makedirs(os.path.dirname(MUTE), exist_ok=True)
    json.dump(d, open(MUTE, "w"))
