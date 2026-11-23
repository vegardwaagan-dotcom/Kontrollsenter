"""Chat-tale og ekstra (runde 4): walkie-talkie, taleanrop, klistremerker, ende-til-ende-kryptering, spillrom og
automatiske temakanaler.

  37 Walkie-talkie: hold på 📢 – det du sier spilles av med en gang hos den andre (en kort talemelding som spilles
     automatisk, med mindre det er stille timer).
  36 Taleanrop 1-til-1 mellom PC-ene (Linux, GStreamer/Opus over UDP – Tailscale eller hjemmenettet). Windows: bruk
     walkie-talkie eller Discord.
  46 Klistremerker: lag fra et bilde (skjermbilde/klipp), send med ett trykk.
  51 Ende-til-ende-kryptering: tekst krypteres for hver mottaker (X25519 + ChaCha20-Poly1305) når begge har
     biblioteket «cryptography» – ellers beskytter Tailscale forbindelsen som før.
  32 Spillrom: «X og Y spiller også CS2 – send til alle som spiller».
  33 Temakanaler: tilbud fra ønskelisten og «Oppdater alt»-resultater postes i kanalene du velger.
"""
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time

IS_WIN = sys.platform == "win32"
DATA = os.path.expanduser("~/.local/share/systemmonitor")
STICK = os.path.join(DATA, "chat-klistremerker")
KEYF = os.path.expanduser("~/.config/systemmonitor/chat-nokkel.json")
_CALL = {"peer": None, "procs": [], "port": None, "room": None}


# --------------------------------------------------------------------------
# 51 – ende-til-ende-kryptering
# --------------------------------------------------------------------------
def crypto_ok():
    try:
        import cryptography  # noqa: F401,PLC0415
        return bool(cryptography)
    except ImportError:
        return False


def _keys():
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from cryptography.hazmat.primitives import serialization as S
    try:
        d = json.load(open(KEYF))
        priv = X25519PrivateKey.from_private_bytes(base64.b64decode(d["priv"]))
    except (OSError, ValueError, KeyError):
        priv = X25519PrivateKey.generate()
        raw = priv.private_bytes(S.Encoding.Raw, S.PrivateFormat.Raw, S.NoEncryption())
        os.makedirs(os.path.dirname(KEYF), exist_ok=True)
        json.dump({"priv": base64.b64encode(raw).decode()}, open(KEYF, "w"))
        try:
            os.chmod(KEYF, 0o600)
        except OSError:
            pass
    pub = priv.public_key().public_bytes(S.Encoding.Raw, S.PublicFormat.Raw)
    return priv, base64.b64encode(pub).decode()


def my_pub():
    if not crypto_ok():
        return None
    try:
        return _keys()[1]
    except Exception:  # noqa: BLE001
        return None


def _shared(their_pub):
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    priv, _pub = _keys()
    secret = priv.exchange(X25519PublicKey.from_public_bytes(base64.b64decode(their_pub)))
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"kontrollsenter-chat").derive(secret)


def encrypt_for(their_pub, text):
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    nonce = os.urandom(12)
    ct = ChaCha20Poly1305(_shared(their_pub)).encrypt(nonce, text.encode("utf-8"), None)
    return base64.b64encode(nonce + ct).decode()


def decrypt_from(their_pub, blob):
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    raw = base64.b64decode(blob)
    return ChaCha20Poly1305(_shared(their_pub)).decrypt(raw[:12], raw[12:], None).decode("utf-8")


def seal(member, payload):
    """Krypter tekst i en melding til ett medlem (hvis begge kan). Returnerer ny payload."""
    if payload.get("type") != "msg" or not member.get("pub") or not payload.get("text") or not crypto_ok():
        return payload
    try:
        return {**payload, "text": "", "enc": encrypt_for(member["pub"], payload["text"])}
    except Exception:  # noqa: BLE001
        return payload


def open_sealed(sender, payload):
    if not payload.get("enc"):
        return payload
    try:
        return {**payload, "text": decrypt_from(sender["pub"], payload["enc"]), "e2e": True}
    except Exception:  # noqa: BLE001
        return {**payload, "text": "🔒 (kunne ikke dekrypteres)"}


# --------------------------------------------------------------------------
# 37 – walkie-talkie
# --------------------------------------------------------------------------
def send_walkie(room, path, notify=None):
    import chatplus
    import chat
    data = open(path, "rb").read()
    _p, sha = chatplus.store_file(os.path.basename(path), data)
    att = {"name": os.path.basename(path), "size": len(data), "sha": sha, "kind": "audio",
           "data": base64.b64encode(data).decode()}
    return chat.send(room, "📢 Walkie-talkie", None, notify, extra={"kind": "walkie", "attach": att})


def on_walkie(msg):
    """Hos mottakeren: spill av med en gang (ikke etter leggetid)."""
    try:
        import chatlink
        import chatplus
        if chatlink.quiet_now():
            return
        chatplus.play(chatplus.file_path(msg.get("attach")))
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------
# 36 – taleanrop 1-til-1 (Linux, GStreamer)
# --------------------------------------------------------------------------
def calls_ok():
    return not IS_WIN and bool(shutil.which("gst-launch-1.0"))


def _free_udp():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for p in range(27150, 27160):
        try:
            s.bind(("0.0.0.0", p))
            s.close()
            return p
        except OSError:
            continue
    s.close()
    return 27150


def _pipes(peer_ip, peer_port, my_port):
    send = ["gst-launch-1.0", "-q", "pipewiresrc", "!", "audioconvert", "!", "audioresample", "!",
            "audio/x-raw,rate=48000,channels=1", "!", "opusenc", "bitrate=32000", "frame-size=20", "!",
            "rtpopuspay", "!", "udpsink", f"host={peer_ip}", f"port={peer_port}"]
    recv = ["gst-launch-1.0", "-q", "udpsrc", f"port={my_port}",
            "caps=application/x-rtp,media=audio,encoding-name=OPUS,clock-rate=48000,payload=96", "!",
            "rtpjitterbuffer", "latency=60", "!", "rtpopusdepay", "!", "opusdec", "!", "audioconvert", "!",
            "autoaudiosink"]
    return send, recv


def call_start(member, room):
    """Ring et medlem: send «call» med min adresse og port; lyden starter når den andre svarer."""
    if not calls_ok():
        raise RuntimeError("taleanrop virker bare på Linux – bruk walkie-talkie eller Discord")
    if _CALL["peer"]:
        raise RuntimeError("du er allerede i en samtale")
    import chatsrv
    port = _free_udp()
    _CALL.update(peer=member, port=port, room=room, t=time.time(), state="ringer")
    sid = room.split(":")[1]
    chatsrv._post(member, {"type": "call", "srv": sid, "from_id": chatsrv.me()["id"],
                           "ip": (chatsrv.my_addrs() or ["?"])[0], "port": port, "room": room})
    return f"Ringer {member.get('name')} …"


def call_incoming(sender, ev):
    """Hos den som blir ringt: varsel med «Svar» (UI) – lagres til svar eller avvis."""
    _CALL["incoming"] = {"member": sender, "ip": ev.get("ip"), "port": int(ev.get("port") or 0),
                         "room": ev.get("room"), "t": time.time()}
    try:
        import chatlink
        chatlink.start_ring(f"📞 {sender.get('name')}")
    except Exception:  # noqa: BLE001
        pass


def call_answer():
    inc = _CALL.pop("incoming", None)
    if not inc or time.time() - inc["t"] > 60:
        raise RuntimeError("ingen samtale å svare på")
    import chatlink
    import chatsrv
    chatlink.stop_ring()
    port = _free_udp()
    _start_audio(inc["ip"], inc["port"], port)
    _CALL.update(peer=inc["member"], port=port, room=inc["room"], state="i samtale")
    sid = (inc["room"] or "s:?:?").split(":")[1]
    chatsrv._post(inc["member"], {"type": "call_ok", "srv": sid, "from_id": chatsrv.me()["id"],
                                  "ip": (chatsrv.my_addrs() or ["?"])[0], "port": port})
    return f"I samtale med {inc['member'].get('name')}"


def call_accepted(sender, ev):
    """Hos den som ringte: den andre svarte – start lyd begge veier."""
    if not _CALL["peer"] or _CALL["peer"].get("id") != sender.get("id"):
        return
    _start_audio(ev.get("ip"), int(ev.get("port") or 0), _CALL["port"])
    _CALL["state"] = "i samtale"


def _start_audio(peer_ip, peer_port, my_port):
    send, recv = _pipes(peer_ip, peer_port, my_port)
    _CALL["procs"] = [subprocess.Popen(recv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
                      subprocess.Popen(send, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)]


def call_end(notify_peer=True):
    peer = _CALL.get("peer")
    for p in _CALL.get("procs") or []:
        try:
            p.terminate()
        except Exception:  # noqa: BLE001
            pass
    _CALL.update(peer=None, procs=[], port=None, state=None)
    _CALL.pop("incoming", None)
    if peer and notify_peer:
        import chatsrv
        sid = (_CALL.get("room") or "s:?:?").split(":")[1]
        threading.Thread(target=chatsrv._post, args=(peer, {"type": "call_end", "srv": sid,
                                                            "from_id": chatsrv.me()["id"]}), daemon=True).start()
    return "Samtalen er avsluttet"


def call_state():
    if _CALL.get("incoming") and time.time() - _CALL["incoming"]["t"] < 60:
        return f"📞 {_CALL['incoming']['member'].get('name')} ringer"
    if _CALL.get("peer"):
        return f"📞 {_CALL.get('state')}: {_CALL['peer'].get('name')}"
    return None


# --------------------------------------------------------------------------
# 46 – klistremerker
# --------------------------------------------------------------------------
def make_sticker(path):
    import gi
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf
    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 160, 160, True)
    os.makedirs(STICK, exist_ok=True)
    out = os.path.join(STICK, f"merke-{int(time.time() * 1000)}.png")
    pb.savev(out, "png", [], [])
    return out


def stickers():
    if not os.path.isdir(STICK):
        return []
    return sorted((os.path.join(STICK, f) for f in os.listdir(STICK) if f.endswith(".png")), reverse=True)


def send_sticker(room, path, notify=None):
    import chatplus
    import chat
    data = open(path, "rb").read()
    _p, sha = chatplus.store_file(os.path.basename(path), data)
    att = {"name": os.path.basename(path), "size": len(data), "sha": sha, "kind": "image",
           "data": base64.b64encode(data).decode()}
    return chat.send(room, "", None, notify, extra={"kind": "sticker", "attach": att})


# --------------------------------------------------------------------------
# 32 – spillrom, 33 – temakanaler
# --------------------------------------------------------------------------
def same_game(win):
    """(spill, [navn]) for andre som spiller det samme som meg nå."""
    game = getattr(getattr(win, "bg", None), "game_name", None) if win else None
    if not game:
        return None, []
    names = []
    try:
        import gamesplus
        names += [n for n, g, _w in gamesplus.who_plays() if g == game]
    except Exception:  # noqa: BLE001
        pass
    try:
        import chatlink
        names += [p["name"] for p in chatlink._PRES.values() if p.get("game") == game and time.time() - p["t"] < 600]
    except Exception:  # noqa: BLE001
        pass
    import savegames
    names = sorted({n for n in names if n and n != savegames.pc_name()})
    return game, names


def send_to_players(win, text):
    import chat
    game, names = same_game(win)
    sent = 0
    for n in names:
        try:
            chat.send(f"p:{n}", f"🎮 [{game}] {text}")
            sent += 1
        except Exception:  # noqa: BLE001
            pass
    return f"Sendt til {sent} som spiller {game}" if sent else "Ingen andre spiller det samme nå"


TOPIC = os.path.expanduser("~/.config/systemmonitor/chat-tema.json")


def topic_room(kind):
    try:
        return json.load(open(TOPIC)).get(kind)
    except (OSError, ValueError):
        return None


def set_topic_room(kind, room):
    try:
        d = json.load(open(TOPIC))
    except (OSError, ValueError):
        d = {}
    d[kind] = room
    os.makedirs(os.path.dirname(TOPIC), exist_ok=True)
    json.dump(d, open(TOPIC, "w"))


def post_topic(kind, text):
    room = topic_room(kind)
    if room:
        import chat
        threading.Thread(target=lambda: chat.send(room, text), daemon=True).start()
