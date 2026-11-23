"""Ring og vær i tale uten å lage en server: en skjult «samtale-server» med én talekanal (lyd, webkamera og overlay
fra talekanalene virker også her).

Den som ringer lager samtalen, går inn i talen og sender «📞 ringer deg» som direktemelding til hver person (med en
invitasjon). Mottakeren får «Svar / Avvis»; Svar blir med i samtalen og går rett inn i talen.
Samtaler eldre enn et døgn ryddes bort av seg selv.
"""
import threading
import time

_IN = {}                       # call_id -> {"from", "room", "invite", "t"} – samtaler som ringer hos meg nå
_LISTENERS = []
RING_SECONDS = 60


def on_change(fn):
    _LISTENERS.append(fn)


def _fire():
    for fn in list(_LISTENERS):
        try:
            from gi.repository import GLib
            GLib.idle_add(lambda f=fn: (f(), False)[1])
        except Exception:  # noqa: BLE001
            pass


def _voice_channel(srv):
    for c in srv.get("categories", []):
        for ch in c.get("channels", []):
            if ch.get("kind") == "voice":
                return ch
    return None


def call(rooms):
    """Ring én eller flere (direktemelding-rom «p:<navn>»). Returnerer tekst."""
    import chat
    import chatsrv
    import chatvc
    rooms = [r for r in rooms if r.startswith("p:")]
    if not rooms:
        raise ValueError("velg hvem du vil ringe")
    if not chatvc.gst_ok():
        raise RuntimeError(chatvc.why_not())
    names = [r[2:] for r in rooms]
    title = "📞 " + ", ".join([chatsrv.me()["name"]] + names)[:60]
    srv = chatsrv.create(title, "📞", hidden=True)
    ch = _voice_channel(srv)
    link = chatsrv.make_invite(srv["id"], uses=0, hours=12)
    chatvc.join(srv["id"], ch["id"])
    sent = []
    for r in rooms:
        try:
            chat.send(r, "📞 Ringer deg – trykk «Svar» for å bli med", extra={"kind": "call", "invite": link,
                                                                              "call_id": srv["id"]})
            sent.append(r[2:])
        except Exception:  # noqa: BLE001
            pass
    _fire()
    return f"Ringer {', '.join(sent) or '…'} – du er i samtalen"


def on_message(msg):
    """En direktemelding med samtale (fra chat._call_fields)."""
    import chatsrv
    cid = msg.get("call_id")
    if msg.get("kind") == "call":
        if chatsrv.get(cid) and chatsrv.my_role(chatsrv.get(cid)) == "owner":
            return                                          # min egen samtale
        _IN[cid] = {"from": msg.get("from"), "room": msg.get("room"), "invite": msg.get("invite"), "t": time.time()}
        try:
            import chatlink
            chatlink.start_ring(f"📞 {msg.get('from')}")
        except Exception:  # noqa: BLE001
            pass
        _notify_call(cid, msg.get("from"))
    elif msg.get("kind") in ("call_end", "call_no"):
        if _IN.pop(cid, None):
            _stop_ring()
            _withdraw()
    _fire()


def _notify_call(cid, who):
    """Varsel med Svar / Legg på / Demp (vises selv om andre varsler er av – egen bryter for chat og anrop)."""
    try:
        import remote
        from gi.repository import GLib
        bg = getattr(getattr(remote, "win", None), "bg", None)
        if not bg:
            return
        GLib.idle_add(lambda: (bg.notify("call", f"📞 {who} ringer deg", "Svar, legg på eller demp ringingen",
                                         force=True, action="app.chat",
                                         buttons=[("📞 Svar", "app.call-answer", cid),
                                                  ("🔕 Demp", "app.call-mute", cid),
                                                  ("❌ Legg på", "app.call-decline", cid)], urgent=True), False)[1])
    except Exception:  # noqa: BLE001
        pass


def _withdraw():
    try:
        from gi.repository import Gio
        app = Gio.Application.get_default()
        if app:
            app.withdraw_notification("call")
    except Exception:  # noqa: BLE001
        pass


def from_notification(action, cid, app=None):
    """Knappene i varselet."""
    if action == "call-mute":                               # bare stopp ringelyden – Svar/Legg på virker fortsatt
        _stop_ring()
        if cid in _IN:
            _IN[cid]["muted"] = True
        return
    if action == "call-decline":
        decline(cid)
        return

    def work():
        try:
            answer(cid)
        except Exception as e:  # noqa: BLE001
            import applog
            applog.log.warning("svar på anrop: %s", e)
    threading.Thread(target=work, daemon=True).start()
    try:                                                    # vis chatten
        win = app.get_active_window() if app else None
        if win:
            win.present()
            win.stack.set_visible_child_name("chat")
    except Exception:  # noqa: BLE001
        pass


def _stop_ring():
    try:
        import chatlink
        chatlink.stop_ring()
    except Exception:  # noqa: BLE001
        pass


def incoming():
    """[(call_id, fra, rom)] som ringer nå (det nyeste først)."""
    now = time.time()
    for cid in [c for c, v in _IN.items() if now - v["t"] > RING_SECONDS]:
        _IN.pop(cid, None)
        _stop_ring()
        _withdraw()
    return sorted(((c, v["from"], v["room"]) for c, v in _IN.items()), key=lambda x: -_IN[x[0]]["t"])


def answer(cid):
    import chatsrv
    import chatvc
    inc = _IN.pop(cid, None)
    _stop_ring()
    _withdraw()
    if not inc:
        raise RuntimeError("samtalen ringer ikke lenger")
    srv = chatsrv.get(cid) or chatsrv.join(inc["invite"])
    ch = _voice_channel(srv)
    if not ch:
        raise RuntimeError("fant ikke samtalen")
    r = chatvc.join(srv["id"], ch["id"])
    _fire()
    return r


def decline(cid):
    import chat
    inc = _IN.pop(cid, None)
    _stop_ring()
    _withdraw()
    if inc and inc.get("room"):
        threading.Thread(target=lambda: _quiet(lambda: chat.send(inc["room"], "📵 Kan ikke ta samtalen nå",
                                                                 extra={"kind": "call_no", "call_id": cid})),
                         daemon=True).start()
    _fire()
    return "Avvist"


def _quiet(fn):
    try:
        fn()
    except Exception:  # noqa: BLE001
        pass


def forget(sid):
    """Legg på og fjern samtalen fra lista (eieren sletter den for alle, andre forlater den)."""
    import chatsrv
    import chatvc
    if chatvc.current() and chatvc.current()[0] == sid:
        chatvc.leave()
    srv = chatsrv.get(sid)
    if not srv:
        return "Samtalen er borte"
    try:
        if chatsrv.my_role(srv) == "owner":
            chatsrv.delete_server(sid)
        else:
            chatsrv.leave(sid)
    except Exception:  # noqa: BLE001
        chatsrv._drop(sid)
    _fire()
    return "Du forlot samtalen"


def active():
    """Samtaler (skjulte servere) med talekanalen og hvem som er inne: [(sid, kanal-id, navn, deltakere)]."""
    import chatsrv
    import chatvc
    out = []
    for sid, srv in chatsrv.servers().items():
        if not srv.get("hidden"):
            continue
        ch = _voice_channel(srv)
        if ch:
            out.append((sid, ch["id"], srv.get("name", "Samtale"), chatvc.roster(sid, ch["id"])))
    return out


def cleanup(max_age=86400):
    """Fjern samtaler eldre enn et døgn som ingen er i."""
    import chatsrv
    import chatvc
    now = time.time()
    for sid, srv in list(chatsrv.servers().items()):
        if not srv.get("hidden") or now - srv.get("created", now) < max_age:
            continue
        ch = _voice_channel(srv)
        if chatvc.current() and chatvc.current()[0] == sid:
            continue
        if ch and chatvc.roster(sid, ch["id"]):
            continue
        try:
            if chatsrv.my_role(srv) == "owner":
                chatsrv.delete_server(sid)
            else:
                chatsrv._drop(sid)
        except Exception:  # noqa: BLE001
            chatsrv._drop(sid)
