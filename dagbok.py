"""Dagbok – privat for hver enkelt, låst med egen kode (4–6 sifre).

Innholdet krypteres med AES-256-GCM. Nøkkelen lages av koden med scrypt (bevisst tregt), så filene på NAS-en
(Kontrollsenter/Familie/Dagbok/<id>.json) ikke kan leses uten koden. Koden lagres ingen steder.
Fem feil koder på rad: dagboken låses i 5 minutter (så 15, 60 …). Glemt kode kan IKKE hentes tilbake.
"""
import base64
import datetime as dt
import hashlib
import json
import os
import secrets
import shutil
import tempfile
import threading
import time

LOCAL = os.path.expanduser("~/.local/share/systemmonitor/dagbok")
LOCKF = os.path.expanduser("~/.local/share/systemmonitor/dagbok-sperre.json")
IDLE = 300                                              # låses igjen etter 5 min uten bruk
_LOCK = threading.Lock()
_SESS = {}                                              # token -> {pid, key, t}
MOODS = ["😄", "🙂", "😐", "😕", "😢", "😡", "😴", "🤩"]


def _b64(b):
    return base64.b64encode(b).decode()


def _ub64(s):
    return base64.b64decode(s)


def _kdf(pin, salt):
    return hashlib.scrypt(pin.encode(), salt=salt, n=2 ** 15, r=8, p=1, maxmem=64 * 1024 * 1024, dklen=32)


def _enc(key, data):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = secrets.token_bytes(12)
    return _b64(nonce + AESGCM(key).encrypt(nonce, data, None))


def _dec(key, blob):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    raw = _ub64(blob)
    return AESGCM(key).decrypt(raw[:12], raw[12:], None)


def _check_pin(pin):
    pin = str(pin or "")
    if not pin.isdigit() or not 4 <= len(pin) <= 6:
        raise ValueError("koden må være 4 til 6 sifre")
    return pin


# --------------------------------------------------------------------------
# Lagring (NAS med lokal kopi – filene er krypterte uansett)
# --------------------------------------------------------------------------
def _nas():
    try:
        import lanupdate as L
        return L if L.on_lan() else None
    except Exception:  # noqa: BLE001
        return None


def _path(pid):
    return os.path.join(LOCAL, f"{pid}.json")


def sync_down():
    """Hent dagbøkene fra NAS-en (nyeste vinner)."""
    L = _nas()
    if not L:
        return
    os.makedirs(LOCAL, exist_ok=True)
    tmp = tempfile.mkdtemp()
    try:
        L._smb(f'cd "Familie/Dagbok"; lcd "{tmp}"; mget *.json', 60)
        for n in os.listdir(tmp):
            src = os.path.join(tmp, n)
            try:
                with open(src, encoding="utf-8") as f:
                    remote = json.load(f)
                local = _read(remote["id"])
                if not local or remote.get("t", 0) >= local.get("t", 0):
                    shutil.copy2(src, _path(remote["id"]))
            except (OSError, ValueError, KeyError):
                continue
    except Exception:  # noqa: BLE001
        pass
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _push(pid):
    def work():
        L = _nas()
        if not L:
            return
        try:
            _h, _s, folder = L._split()
            L.smb_mkdir(f"{folder}/Familie")
            L.smb_mkdir(f"{folder}/Familie/Dagbok")
            L._smb(f'cd "Familie/Dagbok"; put "{_path(pid)}" "{pid}.json"', 30)
        except Exception:  # noqa: BLE001
            pass
    threading.Thread(target=work, daemon=True).start()


def _read(pid):
    try:
        with open(_path(pid), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write(d):
    os.makedirs(LOCAL, exist_ok=True)
    d["t"] = time.time()
    p = _path(d["id"])
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(d, f)
    os.replace(p + ".tmp", p)
    _push(d["id"])


def people():
    """[{id, name}] – navnene er ikke hemmelige, innholdet er det."""
    out = []
    try:
        for n in sorted(os.listdir(LOCAL)):
            if n.endswith(".json"):
                d = _read(n[:-5])
                if d:
                    out.append({"id": d["id"], "name": d["name"]})
    except OSError:
        pass
    return out


# --------------------------------------------------------------------------
# Sperre etter feil kode
# --------------------------------------------------------------------------
def _locks():
    try:
        with open(LOCKF) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_locks(d):
    os.makedirs(os.path.dirname(LOCKF), exist_ok=True)
    with open(LOCKF, "w") as f:
        json.dump(d, f)


def locked_for(pid):
    """Sekunder til du kan prøve igjen (0 = kan prøve nå)."""
    return max(0, int(_locks().get(pid, {}).get("until", 0) - time.time()))


def _fail(pid):
    d = _locks()
    x = d.get(pid, {"fails": 0, "until": 0})
    x["fails"] += 1
    if x["fails"] % 5 == 0:
        x["until"] = time.time() + 60 * {5: 5, 10: 15}.get(x["fails"], 60)
    d[pid] = x
    _save_locks(d)
    return x


def _ok(pid):
    d = _locks()
    d.pop(pid, None)
    _save_locks(d)


# --------------------------------------------------------------------------
# Lage, låse opp, skrive
# --------------------------------------------------------------------------
def create(name, pin):
    name = str(name or "").strip()[:40]
    if not name:
        raise ValueError("skriv navnet")
    pin = _check_pin(pin)
    if any(p["name"].lower() == name.lower() for p in people()):
        raise ValueError("det finnes allerede en dagbok med det navnet")
    pid = "d" + secrets.token_hex(6)
    salt = secrets.token_bytes(16)
    key = _kdf(pin, salt)
    _write({"id": pid, "name": name, "salt": _b64(salt), "check": _enc(key, b"kontrollsenter-dagbok"),
            "data": _enc(key, b"[]")})
    return unlock(pid, pin)


def unlock(pid, pin):
    """Riktig kode → økt-token (holdes åpen i 5 min uten bruk)."""
    wait = locked_for(pid)
    if wait:
        raise PermissionError(f"for mange feil – prøv igjen om {wait // 60 + 1} min")
    pin = _check_pin(pin)
    d = _read(pid)
    if not d:
        raise ValueError("fant ikke dagboken")
    key = _kdf(pin, _ub64(d["salt"]))
    try:
        _dec(key, d["check"])
    except Exception:  # noqa: BLE001
        x = _fail(pid)
        left = 5 - x["fails"] % 5
        raise PermissionError("feil kode" + (f" – {left} forsøk igjen før dagboken låses en stund"
                                             if left < 5 else " – dagboken er låst en stund")) from None
    _ok(pid)
    tok = secrets.token_urlsafe(18)
    _SESS[tok] = {"pid": pid, "key": key, "t": time.time()}
    return tok


def _sess(tok):
    s = _SESS.get(tok or "")
    if not s or time.time() - s["t"] > IDLE:
        _SESS.pop(tok or "", None)
        raise PermissionError("dagboken er låst – skriv koden igjen")
    s["t"] = time.time()
    return s


def lock(tok):
    _SESS.pop(tok or "", None)


def entries(tok):
    s = _sess(tok)
    d = _read(s["pid"])
    return {"name": d["name"], "entries": json.loads(_dec(s["key"], d["data"]))}


def write(tok, text, mood="", day=None, eid=None):
    """Nytt innlegg (eller endre et med eid)."""
    s = _sess(tok)
    text = str(text or "").strip()[:20000]
    if not text:
        raise ValueError("skriv noe først")
    with _LOCK:
        d = _read(s["pid"])
        lst = json.loads(_dec(s["key"], d["data"]))
        if eid:
            for e in lst:
                if e["id"] == eid:
                    e.update(text=text, mood=mood if mood in MOODS else e.get("mood", ""), edited=time.time())
        else:
            lst.append({"id": secrets.token_hex(5), "day": str(day or dt.date.today()), "t": time.time(),
                        "text": text, "mood": mood if mood in MOODS else ""})
        lst.sort(key=lambda e: (e["day"], e["t"]))
        d["data"] = _enc(s["key"], json.dumps(lst, ensure_ascii=False).encode())
        _write(d)
    return "Lagret 🔒"


def delete_entry(tok, eid):
    s = _sess(tok)
    with _LOCK:
        d = _read(s["pid"])
        lst = [e for e in json.loads(_dec(s["key"], d["data"])) if e["id"] != eid]
        d["data"] = _enc(s["key"], json.dumps(lst, ensure_ascii=False).encode())
        _write(d)
    return "Slettet"


def change_pin(tok, new_pin):
    s = _sess(tok)
    new_pin = _check_pin(new_pin)
    with _LOCK:
        d = _read(s["pid"])
        data = _dec(s["key"], d["data"])
        salt = secrets.token_bytes(16)
        key = _kdf(new_pin, salt)
        d.update(salt=_b64(salt), check=_enc(key, b"kontrollsenter-dagbok"), data=_enc(key, data))
        _write(d)
        s["key"] = key
    return "Ny kode er lagret – den gamle virker ikke lenger"


def delete_diary(pid, pin):
    """Slett hele dagboken (krever koden)."""
    tok = unlock(pid, pin)
    lock(tok)
    try:
        os.remove(_path(pid))
    except OSError:
        pass
    L = _nas()
    if L:
        try:
            L._smb(f'cd "Familie/Dagbok"; del "{pid}.json"', 30)
        except Exception:  # noqa: BLE001
            pass
    return "Dagboken er slettet"
