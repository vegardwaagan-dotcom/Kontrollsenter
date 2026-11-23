"""Oppdatering for venner utenfor huset: PC-ene hjemme videresender NAS-ens versjon over Tailscale.

Hjemme (på hjemmenettet, vennedeling på):
    /api/friend/update?k=<vennekode>            → {"version", "sha256", "apk": {...}, "pilot"}
    /api/friend/update/file?k=…&f=pkg|apk → selve fila (kopiert fra NAS-en, sjekksum kontrollert)
Borte (ikke på hjemmenettet): spør vennene i vennelista, velger den nyeste versjonen og sjekker sjekksummen
før noe installeres. Ingen ny tjeneste – samme port og samme vennekode som venneoversikten bruker.
"""
import hashlib
import json
import os
import shutil
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

CACHE = Path.home() / ".cache/systemmonitor/videresend"
_LOCK = threading.Lock()
_INFO = {"t": 0, "v": None}
_REMOTE = {"t": 0, "v": None}
FILES = {"pkg": ("Kontrollsenter.tar.gz", ""), "apk": ("Kontrollsenter.apk", "Android")}


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------
# Hjemme: les fra NAS-en (mellomlagret 10 min) og server filene
# --------------------------------------------------------------------------
def serve_info(force=False):
    """Det NAS-en har nå, eller None hvis denne PC-en ikke er hjemme."""
    import lanupdate as L
    with _LOCK:
        if not force and _INFO["v"] is not None and time.time() - _INFO["t"] < 600:
            return _INFO["v"]
        if not L.on_lan():
            _INFO.update(t=time.time(), v=None)
            return None
        tmp = Path(tempfile.mkdtemp())
        try:
            L._smb(f'get VERSION "{tmp}/VERSION"; get SHA256SUMS "{tmp}/SUMS"', 30)
            sums = dict(reversed(ln.split(None, 1)) for ln in (tmp / "SUMS").read_text().splitlines() if ln.strip())
            info = {"version": (tmp / "VERSION").read_text().strip(), "sha256": sums.get(L.PKG, "").strip()}
            try:
                L._smb(f'cd "Android"; get versjon.json "{tmp}/a.json"', 30)
                a = json.loads((tmp / "a.json").read_text())
                info["apk"] = {k: a[k] for k in ("version", "code", "sha256") if k in a}
            except Exception:  # noqa: BLE001
                pass
            pil = L.pilot_info()
            info["pilot"] = bool(pil and pil.get("version") == info["version"] and pil.get("pc") and
                                 (pil.get("failed") or time.time() < pil.get("until", 0)))
        except Exception:  # noqa: BLE001
            info = None
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        _INFO.update(t=time.time(), v=info)
        return info


def serve_file(kind):
    """Lokal kopi av fila (hentes fra NAS-en når versjonen er ny). Kaster ved feil."""
    import lanupdate as L
    if kind not in FILES:
        raise ValueError("ukjent fil")
    info = serve_info()
    if not info:
        raise RuntimeError("denne PC-en er ikke på hjemmenettet nå")
    name, folder = FILES[kind]
    want = info["sha256"] if kind == "pkg" else (info.get("apk") or {}).get("sha256", "")
    dst = CACHE / f"{info['version']}-{name}"
    with _LOCK:
        if dst.exists() and (not want or _sha(dst) == want):
            return dst
        CACHE.mkdir(parents=True, exist_ok=True)
        for old in CACHE.glob(f"*-{name}"):                 # bare én versjon av hver fil ligger her
            old.unlink(missing_ok=True)
        part = dst.with_suffix(".part")
        L._smb((f'cd "{folder}"; ' if folder else "") + f'get "{name}" "{part}"', 300)
        if want and _sha(part) != want:
            part.unlink(missing_ok=True)
            raise RuntimeError("fila på NAS-en har feil sjekksum")
        os.replace(part, dst)
        return dst


# --------------------------------------------------------------------------
# Borte: spør PC-ene i vennelista
# --------------------------------------------------------------------------
def _url(fr, path, **q):
    q["k"] = fr["key"]
    return f"http://{fr['addr']}:{fr.get('port', 27100)}{path}?{urllib.parse.urlencode(q)}"


def remote(force=False):
    """Nyeste versjon en venn-PC kan videresende: {"version", "sha256", "apk", "pilot", "friend"} eller None."""
    if not force and _REMOTE["t"] and time.time() - _REMOTE["t"] < 900:
        return _REMOTE["v"]
    import friends
    import lanupdate as L
    found = []

    def ask(f):
        try:
            req = urllib.request.Request(_url(f, "/api/friend/update"), headers={"User-Agent": "Kontrollsenter"})
            with urllib.request.urlopen(req, timeout=6) as r:
                d = json.load(r)
            if d.get("version"):
                found.append({**d, "friend": f})
        except Exception:  # noqa: BLE001 – vennen er av eller ikke hjemme
            pass
    th = [threading.Thread(target=ask, args=(f,), daemon=True) for f in friends.cfg()["friends"]]
    for t in th:
        t.start()
    for t in th:
        t.join(8)
    best = max(found, key=lambda d: L.version_tuple(d["version"]), default=None)
    _REMOTE.update(t=time.time(), v=best)
    return best


def download(kind, dst, info=None):
    """Hent fila fra venn-PC-en og kontroller sjekksummen. Returnerer dst."""
    info = info or remote()
    if not info:
        raise RuntimeError("ingen venn-PC hjemme svarer")
    want = info.get("sha256") if kind == "pkg" else (info.get("apk") or {}).get("sha256") if kind == "apk" else ""
    req = urllib.request.Request(_url(info["friend"], "/api/friend/update/file", f=kind),
                                 headers={"User-Agent": "Kontrollsenter"})
    part = Path(str(dst) + ".part")
    with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as out:
        shutil.copyfileobj(r, out)
    if want and _sha(part) != want:
        part.unlink(missing_ok=True)
        raise RuntimeError("sjekksummen stemmer ikke – oppdateringen ble ikke installert")
    os.replace(part, dst)
    return Path(dst)
