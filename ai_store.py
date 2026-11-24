"""Hvor AI-en jobber og husker: NAS-en (standard) eller lokalt på PC-en.

NAS: Kontrollsenter/AI/<PC-navn>/samtaler (én JSON per samtale) og …/arbeid (mappa AI-en jobber i).
  Linux: en lokal speilkopi synkroniseres med smbclient (henter når AI-siden åpnes, sender etter hvert svar).
  Windows: NAS-mappa brukes direkte (\\\\NAS\\Public\\Kontrollsenter\\AI\\…).
Lokalt: ~/.local/share/systemmonitor/ai/.
"""
import json
import os
import subprocess
import sys
import threading
import time
import uuid

IS_WIN = sys.platform == "win32"
LOCAL = os.path.expanduser("~/.local/share/systemmonitor/ai")
MIRROR = os.path.expanduser("~/.cache/systemmonitor/ai-nas")
_LOCK = threading.RLock()
_SYNC = {"t": 0, "ok": None, "msg": ""}


def _pc():
    try:
        import savegames
        return savegames.pc_name()
    except Exception:  # noqa: BLE001
        import socket
        return socket.gethostname()


def mode():
    import ai
    return ai.cfg().get("storage", "nas")


def set_mode(m):
    import ai
    ai.set_(storage="local" if m == "local" else "nas")
    _SYNC.update(t=0, ok=None)
    if m != "local":
        pull()


def _unc():
    import lanupdate as L
    try:
        import ntpath
        return ntpath.join(L._unc_root(), "AI", _pc())
    except Exception:  # noqa: BLE001
        return None


def root():
    """Mappa med «samtaler» og «arbeid» (lokal sti – på Linux med NAS: speilkopien)."""
    if mode() == "local":
        r = LOCAL
    elif IS_WIN:
        r = _unc() or LOCAL
    else:
        r = os.path.join(MIRROR, _pc())
    for sub in ("samtaler", "arbeid"):
        try:
            os.makedirs(os.path.join(r, sub), exist_ok=True)
        except OSError:
            pass
    return r


def workdir():
    return os.path.join(root(), "arbeid")


def where():
    """Tekst til brukeren: hvor ligger det nå?"""
    if mode() == "local":
        return f"💻 Lokalt ({LOCAL})"
    import lanupdate as L
    loc = L.location().replace("/", "\\") if IS_WIN else L.location()
    return f"☁️ NAS ({loc}/AI/{_pc()})" + ("" if _SYNC["ok"] in (None, True) else " – " + _SYNC["msg"])


# --------------------------------------------------------------------------
# Synkronisering med NAS-en (Linux)
# --------------------------------------------------------------------------
def _smb_on():
    return mode() == "nas" and not IS_WIN


def _remote(rel=""):
    import lanupdate as L
    _h, _s, folder = L._split()
    return "/".join(x for x in (folder, "AI", _pc(), rel) if x)


def _ensure_remote():
    import lanupdate as L
    _h, _s, folder = L._split()
    for rel in ("AI", f"AI/{_pc()}", f"AI/{_pc()}/samtaler", f"AI/{_pc()}/arbeid"):
        L.smb_mkdir(f"{folder}/{rel}" if folder else rel)


def pull(force=False):
    """Hent samtalene og arbeidsmappa fra NAS-en til speilkopien. Returnerer (ok, melding)."""
    if not _smb_on():
        return True, ""
    if not force and time.time() - _SYNC["t"] < 20 and _SYNC["ok"]:
        return True, _SYNC["msg"]
    import lanupdate as L
    with _LOCK:
        try:
            if not L.on_lan():
                raise RuntimeError("NAS-en svarer ikke – lagres på PC-en til den er tilbake")
            _ensure_remote()
            r = root()
            _h, share, _f = L._split()
            out = subprocess.run(["smbclient", "-N", share, "-c",
                                  f'recurse ON; prompt OFF; cd "{_remote()}"; lcd "{r}"; mget *'],
                                 capture_output=True, text=True, timeout=120)
            if out.returncode != 0 and "NT_STATUS_NO_SUCH_FILE" not in out.stdout + out.stderr:
                raise RuntimeError((out.stdout + out.stderr).strip().splitlines()[-1][:160])
            _SYNC.update(t=time.time(), ok=True, msg="synkronisert med NAS-en")
            return True, _SYNC["msg"]
        except Exception as e:  # noqa: BLE001
            _SYNC.update(t=time.time(), ok=False, msg=str(e))
            return False, str(e)


def push(paths):
    """Send filer (stier under root()) til NAS-en."""
    if not _smb_on() or not paths:
        return True
    import lanupdate as L
    r = root()
    cmds = []
    for p in paths:
        rel = os.path.relpath(p, r).replace(os.sep, "/")
        if rel.startswith(".."):
            continue
        d = os.path.dirname(rel)
        if d:
            parts = d.split("/")
            for i in range(1, len(parts) + 1):
                cmds.append(f'mkdir "{"/".join(parts[:i])}"')
        cmds.append(f'put "{p}" "{rel}"')
    if not cmds:
        return True
    try:
        _h, share, _f = L._split()
        subprocess.run(["smbclient", "-N", share, "-c", f'cd "{_remote()}"; ' + "; ".join(cmds)],
                       capture_output=True, text=True, timeout=120)
        return True
    except Exception as e:  # noqa: BLE001
        _SYNC.update(ok=False, msg=f"fikk ikke lagret på NAS-en ({e})")
        return False


def push_changed(since):
    """Etter et svar: send filer i arbeidsmappa som er endret siden «since»."""
    if not _smb_on():
        return
    changed = []
    for dp, _dn, fn in os.walk(workdir()):
        for f in fn:
            p = os.path.join(dp, f)
            try:
                if os.path.getmtime(p) >= since - 1:
                    changed.append(p)
            except OSError:
                pass
    push(changed[:400])


def _smb_del(rel):
    if not _smb_on():
        return
    import lanupdate as L
    try:
        _h, share, _f = L._split()
        subprocess.run(["smbclient", "-N", share, "-c", f'cd "{_remote()}"; del "{rel}"'], capture_output=True,
                       timeout=30)
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------
# Samtaler
# --------------------------------------------------------------------------
def _path(cid):
    return os.path.join(root(), "samtaler", f"{cid}.json")


def conversations():
    """[{id, title, tool, updated, count}] – nyeste først."""
    out = []
    d = os.path.join(root(), "samtaler")
    try:
        names = os.listdir(d)
    except OSError:
        names = []
    for n in names:
        if not n.endswith(".json"):
            continue
        try:
            with open(os.path.join(d, n), encoding="utf-8") as f:
                c = json.load(f)
            out.append({"id": c["id"], "title": c.get("title") or "Ny samtale", "tool": c.get("tool", "claude"),
                        "updated": c.get("updated", 0), "count": len(c.get("messages", [])),
                        "pinned": bool(c.get("pinned")), "emoji": c.get("emoji") or ""})
        except (OSError, ValueError, KeyError):
            continue
    return sorted(out, key=lambda c: (not c["pinned"], -c["updated"]))       # festede øverst


def set_meta(cid, **kw):
    """Fest / emoji på en samtale (uten å endre «sist brukt»)."""
    c = load(cid)
    if not c:
        return
    c.update({k: v for k, v in kw.items() if k in ("pinned", "emoji")})
    p = _path(cid)
    with _LOCK:
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump(c, f, ensure_ascii=False, indent=1)
        os.replace(p + ".tmp", p)
    threading.Thread(target=push, args=([p],), daemon=True).start()


def new(tool):
    c = {"id": time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6], "title": "Ny samtale", "tool": tool,
         "created": time.time(), "updated": time.time(), "messages": []}
    save(c, push_now=False)
    return c


def load(cid):
    try:
        with open(_path(cid), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save(c, push_now=True):
    c["updated"] = time.time()
    if c.get("title") in (None, "", "Ny samtale"):
        first = next((m["text"] for m in c.get("messages", []) if m["role"] == "user"), "")
        if first:
            c["title"] = first.strip().splitlines()[0][:48]
    p = _path(c["id"])
    with _LOCK:
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(c, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
    if push_now:
        threading.Thread(target=push, args=([p],), daemon=True).start()


def rename(cid, title):
    c = load(cid)
    if c:
        c["title"] = str(title).strip()[:60] or c["title"]
        save(c)


def delete(cid):
    try:
        os.remove(_path(cid))
    except OSError:
        pass
    threading.Thread(target=_smb_del, args=(f"samtaler/{cid}.json",), daemon=True).start()


def history_text(c, limit=7000):
    """De siste delene av samtalen som tekst (sendes med, så assistenten husker – også på en annen PC)."""
    msgs = c.get("messages", [])[:-1]                     # ikke det nye spørsmålet
    lines, n = [], 0
    for m in reversed(msgs):
        who = "Bruker" if m["role"] == "user" else "Assistent"
        t = f"{who}: {m['text'].strip()}"
        if n + len(t) > limit:
            break
        lines.append(t)
        n += len(t)
    return "\n\n".join(reversed(lines))


