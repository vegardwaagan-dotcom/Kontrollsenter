"""Samme chat i Windows og Linux på samme PC (dual boot).

Bare ett av systemene kjører om gangen, så chatten (identitet, samtaler, servere, krypteringsnøkler og chat-valg)
legges på NAS-en under Kontrollsenter/Chat/<maskin-ID>/: systemet som starter henter den, og sender endringer opp
underveis og når Kontrollsenter avsluttes. Første gang blir identiteten til systemet som kobler seg først den felles.

Slås bare på når maskinen faktisk har flere systemer (machine.home_aliases ser mer enn ett navn).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

IS_WIN = sys.platform == "win32"
STATE = os.path.expanduser("~/.local/share/systemmonitor/chat-synk.json")
_LOCK = threading.Lock()


def _files():
    import chat
    import chatlink
    import chatplus
    import chatsrv
    import chatvoice
    return {"meg.json": chatsrv.ME_FILE, "servere.json": chatsrv.FILE, "rom.json": chat.FILE,
            "nokkel.json": chatvoice.KEYF, "pluss.json": chatplus.CFG, "kobling.json": chatlink.CFG}


def _state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"pushed": 0, "seen": 0, "linked": False}


def _save_state(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w") as f:
        json.dump(st, f)


def active():
    """Har denne PC-en flere systemer (Windows og Linux)?"""
    try:
        import machine
        import savegames
        return bool(machine.hw_id()) and len(machine.home_aliases(savegames.pc_name())) > 1
    except Exception:  # noqa: BLE001
        return False


def _remote():
    import lanupdate as L
    import machine
    _h, _s, folder = L._split()
    return f"{folder}/Chat/{machine.hw_id()}"


def _get(names, dst):
    """Hent filer fra NAS-mappa til dst. Returnerer de som fantes."""
    import lanupdate as L
    if IS_WIN:
        import ntpath
        src = ntpath.join(L._unc_root(), "Chat", __import__("machine").hw_id())
        got = []
        for n in names:
            try:
                shutil.copy2(ntpath.join(src, n), os.path.join(dst, n))
                got.append(n)
            except OSError:
                pass
        return got
    _h, share, _f = L._split()
    cmds = "; ".join(f'get "{n}" "{os.path.join(dst, n)}"' for n in names)
    subprocess.run(["smbclient", "-N", share, "-c", f'cd "{_remote()}"; {cmds}'], capture_output=True, timeout=120)
    return [n for n in names if os.path.exists(os.path.join(dst, n))]


def _put(paths):
    import lanupdate as L
    _h, _s, folder = L._split()
    L.smb_mkdir(f"{folder}/Chat")
    L.smb_mkdir(_remote())
    if IS_WIN:
        import ntpath
        dst = ntpath.join(L._unc_root(), "Chat", __import__("machine").hw_id())
        os.makedirs(dst, exist_ok=True)
        for name, p in paths.items():
            shutil.copy2(p, ntpath.join(dst, name))
        return
    _h, share, _f = L._split()
    cmds = "; ".join(f'put "{p}" "{name}"' for name, p in paths.items())
    subprocess.run(["smbclient", "-N", share, "-c", f'cd "{_remote()}"; {cmds}'], capture_output=True, timeout=120)


def _load(p, default):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(p, d):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".synk"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, p)


def _merge_rooms(local, remote):
    out = dict(local)
    for room, msgs in remote.items():
        if room == "_read":
            r = out.setdefault("_read", {})
            for k, v in (msgs or {}).items():
                r[k] = max(r.get(k, 0), v)
            continue
        if not isinstance(msgs, list):
            out.setdefault(room, msgs)
            continue
        have = {m.get("id"): m for m in out.get(room) or [] if isinstance(m, dict)}
        for m in msgs:
            if isinstance(m, dict) and m.get("id") not in have:
                have[m.get("id")] = m
        out[room] = sorted(have.values(), key=lambda m: m.get("t", 0))[-2000:]
    return out


def _merge_servers(local, remote):
    out = dict(local)
    for sid, srv in remote.items():
        if sid not in out or int(srv.get("v", 0)) >= int(out[sid].get("v", 0)):
            out[sid] = srv
    return out


def savegames_name():
    import savegames
    return savegames.pc_name()


def pull(force=False):
    """Ved oppstart: hent den felles chatten hvis den andre systemet har nyere. Returnerer tekst."""
    if not active():
        return "ikke dual boot"
    import lanupdate as L
    if not L.on_lan():
        return "NAS-en svarer ikke"
    with _LOCK:
        st = _state()
        tmp = tempfile.mkdtemp()
        try:
            files = _files()
            got = _get(["meta.json"] + list(files), tmp)
            if "meta.json" not in got:
                st["linked"] = True                         # ingen felles chat ennå: denne blir den felles
                try:                                        # samme navn i chatten uansett hvilket system som kjører
                    import chatsrv
                    me = _load(chatsrv.ME_FILE, {})
                    if me and not me.get("display"):
                        me["display"] = savegames_name()
                        _write(chatsrv.ME_FILE, me)
                except Exception:  # noqa: BLE001
                    pass
                _save_state(st)
                push(force=True)
                return "felles chat opprettet fra denne PC-en"
            meta = _load(os.path.join(tmp, "meta.json"), {})
            import savegames
            if not force and (meta.get("t", 0) <= st.get("seen", 0) or meta.get("by") == savegames.pc_name()):
                return "allerede oppdatert"
            for name, p in files.items():
                src = os.path.join(tmp, name)
                if name not in got:
                    continue
                remote = _load(src, None)
                if remote is None:
                    continue
                if name == "rom.json":
                    _write(p, _merge_rooms(_load(p, {}), remote))
                elif name == "servere.json":
                    _write(p, _merge_servers(_load(p, {}), remote))
                else:                                       # identitet, nøkler og valg: den felles vinner
                    _write(p, remote)
            st.update(seen=meta.get("t", 0), linked=True, pushed=time.time())
            _save_state(st)
            try:
                import chatsrv
                for sid in list(chatsrv.servers()):
                    chatsrv._changed(sid)
            except Exception:  # noqa: BLE001
                pass
            return f"chatten er hentet fra {meta.get('by', 'det andre systemet')}"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def push(force=False):
    """Send chatten til NAS-en hvis noe er endret siden sist."""
    if not active():
        return False
    st = _state()
    if not st.get("linked") and not force:
        return False
    files = {n: p for n, p in _files().items() if os.path.exists(p)}
    changed = max((os.path.getmtime(p) for p in files.values()), default=0)
    if not force and changed <= st.get("pushed", 0):
        return False
    import savegames
    import machine
    tmp = tempfile.mkdtemp()
    try:
        meta = os.path.join(tmp, "meta.json")
        now = time.time()
        with open(meta, "w") as f:
            json.dump({"t": now, "by": savegames.pc_name(), "os": machine.os_name()}, f)
        _put({**files, "meta.json": meta})
        st.update(pushed=now, seen=now)
        _save_state(st)
        return True
    except Exception:  # noqa: BLE001
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
