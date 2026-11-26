"""NAS-disken i Kontrollsenter: bla i mappene, åpne, last ned, last opp, lag mapper, gi nytt navn og slett.

Linux: smbclient (samme som oppdateringene). Windows: nettverksstien \\\\vert\\deling. Den åpne delingen (Public)
virker uten innlogging; de private (f.eks. ens egen) trenger brukernavn og passord – lagres i systemets nøkkelring
(Linux: Secret Service / KWallet via libsecret), aldri i klartekst.

Utenfor hjemmet: NAS-en nås gjennom Tailscale når en PC hjemme deler hjemmenettet (se tailnas.py). Mobilappen går
alltid via PC-en den er koblet til, så den virker borte så lenge den PC-en når NAS-en.
"""
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

IS_WIN = sys.platform == "win32"
CACHE = os.path.join(os.path.expanduser("~/.cache/systemmonitor"), "nas")
BAD = re.compile(r'["\\\x00-\x1f;|<>*?]')
_SHARES = {"t": 0, "v": None}


def host():
    import lanupdate
    return lanupdate._split()[0]


def default_share():
    import lanupdate
    return lanupdate._split()[1].strip("/").split("/")[-1] or "Public"


def _clean(path):
    """«a/b/c» uten «..», tomme ledd eller tegn smbclient ikke tåler. Kaster ValueError."""
    parts = [p for p in str(path or "").replace("\\", "/").split("/") if p not in ("", ".")]
    for p in parts:
        if p == ".." or BAD.search(p) or len(p) > 255:
            raise ValueError("ugyldig navn")
    return "/".join(parts)


def _name(name):
    n = _clean(name)
    if not n or "/" in n:
        raise ValueError("ugyldig navn")
    return n


def _share(share):
    s = str(share or default_share())
    if not re.fullmatch(r"[\w .$-]{1,80}", s):
        raise ValueError("ugyldig deling")
    return s


# ------------------------------------------------------------------ nås den?
def reachable(timeout=2.0):
    try:
        with socket.create_connection((host(), 445), timeout=timeout):
            return True
    except OSError:
        return False


def where():
    """«hjemme», «tailscale» (utenfor hjemmet) eller None (ikke tilgjengelig)."""
    if not reachable():
        return None
    try:
        import lanupdate
        return "hjemme" if lanupdate.on_lan() else "tailscale"
    except Exception:  # noqa: BLE001
        return "hjemme"


# ------------------------------------------------------------------ innlogging (private delinger)
def _secret_schema():
    import gi
    gi.require_version("Secret", "1")
    from gi.repository import Secret
    return Secret, Secret.Schema.new("no.waagan.Kontrollsenter.NAS", Secret.SchemaFlags.NONE,
                                     {"host": Secret.SchemaAttributeType.STRING,
                                      "share": Secret.SchemaAttributeType.STRING})


def login_get(share):
    """(bruker, passord) for delingen – eller None."""
    if IS_WIN:
        return None                                    # Windows husker selv (Utforsker / «net use»)
    try:
        Secret, schema = _secret_schema()
        v = Secret.password_lookup_sync(schema, {"host": host(), "share": share}, None)
        if v and "\n" in v:
            u, p = v.split("\n", 1)
            return u, p
    except Exception:  # noqa: BLE001
        pass
    return None


def login_set(share, user, password):
    share = _share(share)
    if not re.fullmatch(r"[\w.@ -]{1,64}", user or ""):
        raise ValueError("ugyldig brukernavn")
    if IS_WIN:
        r = subprocess.run(["net", "use", f"\\\\{host()}\\{share}", password, f"/user:{user}", "/persistent:yes"],
                           capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            raise RuntimeError((r.stderr or r.stdout).strip() or "innloggingen ble ikke godtatt")
        return "Logget inn ✓"
    Secret, schema = _secret_schema()
    Secret.password_store_sync(schema, {"host": host(), "share": share}, Secret.COLLECTION_DEFAULT,
                               f"Kontrollsenter – NAS {share}", f"{user}\n{password}", None)
    list_dir(share, "")                                # sjekk at det virker
    return "Logget inn ✓ – husket i nøkkelringen"


def login_forget(share):
    if IS_WIN:
        subprocess.run(["net", "use", f"\\\\{host()}\\{_share(share)}", "/delete", "/y"], capture_output=True, timeout=20)
        return "Glemt"
    try:
        Secret, schema = _secret_schema()
        Secret.password_clear_sync(schema, {"host": host(), "share": _share(share)}, None)
    except Exception:  # noqa: BLE001
        pass
    return "Glemt"


# ------------------------------------------------------------------ smbclient (Linux)
def _smb(share, cmds, timeout=120):
    if not shutil.which("smbclient"):
        raise RuntimeError("smbclient mangler – se Systemsjekk")
    args = ["smbclient", f"//{host()}/{share}", "-c", cmds]
    cred = login_get(share)
    authf = None
    try:
        if cred:
            fd, authf = tempfile.mkstemp(prefix="ks-nas-")
            with os.fdopen(fd, "w") as f:
                f.write(f"username = {cred[0]}\npassword = {cred[1]}\n")
            args[1:1] = ["-A", authf]
        else:
            args[1:1] = ["-N"]
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    finally:
        if authf:
            os.unlink(authf)
    out = (r.stdout + r.stderr).strip()
    if r.returncode != 0 or "NT_STATUS_" in out:
        err = next((ln for ln in out.splitlines() if "NT_STATUS_" in ln), out.splitlines()[-1] if out else "")
        raise RuntimeError(_nice(err.strip()))
    return out


def _nice(err):
    for k, v in (("ACCESS_DENIED", "ingen tilgang – logg inn med brukeren din"),
                 ("LOGON_FAILURE", "feil brukernavn eller passord"),
                 ("BAD_NETWORK_NAME", "fant ikke delingen"),
                 ("OBJECT_NAME_NOT_FOUND", "finnes ikke"), ("OBJECT_PATH_NOT_FOUND", "finnes ikke"),
                 ("OBJECT_NAME_COLLISION", "finnes fra før"), ("DIRECTORY_NOT_EMPTY", "mappa er ikke tom"),
                 ("HOST_UNREACHABLE", "NAS-en svarer ikke"), ("IO_TIMEOUT", "NAS-en svarer ikke"),
                 ("CONNECTION_REFUSED", "NAS-en svarer ikke")):
        if k in err:
            return v
    return err or "ukjent feil fra NAS-en"


def _q(path):
    return '"' + path.replace("/", "\\") + '"'


LS = re.compile(r"^  (.+?)\s+([A-Z]*)\s+(\d+)\s+\w{3} (\w{3})\s+(\d+) (\d\d:\d\d:\d\d) (\d{4})$")
MON = {m: i for i, m in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
                                  1)}


# ------------------------------------------------------------------ det appen bruker
def shares():
    """De delte mappene på NAS-en: [{"name", "open"}] (open = uten innlogging)."""
    if _SHARES["v"] is not None and time.time() - _SHARES["t"] < 300:
        return _SHARES["v"]
    out = []
    if IS_WIN:
        r = subprocess.run(["net", "view", f"\\\\{host()}"], capture_output=True, text=True, timeout=30)
        for ln in r.stdout.splitlines():
            m = re.match(r"^(\S[^\s].*?)\s{2,}(Disk|Plate|Disque|Datenträger)", ln)
            if m:
                out.append({"name": m.group(1).strip(), "open": None})
    elif shutil.which("smbclient"):
        r = subprocess.run(["smbclient", "-N", "-g", "-L", f"//{host()}"], capture_output=True, text=True, timeout=30)
        for ln in r.stdout.splitlines():
            p = ln.split("|")
            if len(p) >= 2 and p[0] == "Disk":
                out.append({"name": p[1], "open": None})
    if not out:
        out = [{"name": default_share(), "open": True}]
    _SHARES.update(t=time.time(), v=out)
    return out


def list_dir(share, path):
    """[{"name", "dir", "size", "t"}] – mapper først, så filer, alfabetisk. Skjulte filer (.navn) tas ikke med."""
    share, path = _share(share), _clean(path)
    items = []
    if IS_WIN:
        base = "\\\\" + host() + "\\" + share + ("\\" + path.replace("/", "\\") if path else "")
        try:
            for e in os.scandir(base):
                if e.name.startswith("."):
                    continue
                st = e.stat()
                items.append({"name": e.name, "dir": e.is_dir(), "size": 0 if e.is_dir() else st.st_size,
                              "t": int(st.st_mtime)})
        except PermissionError as e:
            raise RuntimeError("ingen tilgang – logg inn med brukeren din") from e
        except FileNotFoundError as e:
            raise RuntimeError("finnes ikke") from e
    else:
        out = _smb(share, (f"cd {_q(path)}; " if path else "") + "ls", 60)
        for ln in out.splitlines():
            m = LS.match(ln)
            if not m:
                continue
            name, attr, size = m.group(1), m.group(2), int(m.group(3))
            if name in (".", "..") or name.startswith(".") or "H" in attr:
                continue
            try:
                t = int(time.mktime((int(m.group(7)), MON.get(m.group(4), 1), int(m.group(5)),
                                     *map(int, m.group(6).split(":")), 0, 0, -1)))
            except (ValueError, OverflowError):
                t = 0
            items.append({"name": name, "dir": "D" in attr, "size": 0 if "D" in attr else size, "t": t})
    return sorted(items, key=lambda x: (not x["dir"], x["name"].lower()))


def fetch(share, path, dest=None):
    """Hent en fil til PC-en (dest, eller hurtiglageret). Returnerer den lokale stien."""
    share, path = _share(share), _clean(path)
    if not path:
        raise ValueError("ingen fil valgt")
    folder, _sep, name = path.rpartition("/")
    if dest is None:
        d = os.path.join(CACHE, share, folder)
        os.makedirs(d, exist_ok=True)
        dest = os.path.join(d, name)
    if IS_WIN:
        shutil.copy2("\\\\" + host() + "\\" + share + "\\" + path.replace("/", "\\"), dest)
    else:
        _smb(share, (f"cd {_q(folder)}; " if folder else "") + f'get "{name}" "{dest}"', 3600)
    return dest


def upload(local, share, folder, name=None):
    share, folder = _share(share), _clean(folder)
    name = _name(name or os.path.basename(local))
    if IS_WIN:
        shutil.copy2(local, "\\\\" + host() + "\\" + share + ("\\" + folder.replace("/", "\\") if folder else "")
                     + "\\" + name)
    else:
        _smb(share, (f"cd {_q(folder)}; " if folder else "") + f'put "{local}" "{name}"', 3600)
    return f"{name} er lastet opp ✓"


def mkdir(share, folder, name):
    share, folder, name = _share(share), _clean(folder), _name(name)
    if IS_WIN:
        os.mkdir("\\\\" + host() + "\\" + share + ("\\" + folder.replace("/", "\\") if folder else "") + "\\" + name)
    else:
        _smb(share, (f"cd {_q(folder)}; " if folder else "") + f'mkdir "{name}"', 60)
    return f"Mappa «{name}» er laget ✓"


def rename(share, path, new):
    share, path, new = _share(share), _clean(path), _name(new)
    folder, _sep, old = path.rpartition("/")
    if not old:
        raise ValueError("ingen fil valgt")
    if IS_WIN:
        base = "\\\\" + host() + "\\" + share + ("\\" + folder.replace("/", "\\") if folder else "")
        os.rename(base + "\\" + old, base + "\\" + new)
    else:
        _smb(share, (f"cd {_q(folder)}; " if folder else "") + f'rename "{old}" "{new}"', 60)
    return f"Nytt navn: {new} ✓"


def delete(share, path, is_dir=False):
    share, path = _share(share), _clean(path)
    folder, _sep, name = path.rpartition("/")
    if not name:
        raise ValueError("ingen fil valgt")
    if IS_WIN:
        full = "\\\\" + host() + "\\" + share + "\\" + path.replace("/", "\\")
        shutil.rmtree(full) if is_dir else os.remove(full)
    else:
        _smb(share, (f"cd {_q(folder)}; " if folder else "") + (f'deltree "{name}"' if is_dir else f'del "{name}"'),
             600)
    return f"{name} er slettet"


def human(n):
    for u in ("B", "kB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024
    return str(n)
