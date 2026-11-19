"""Tidsmaskin for innstillingene (12).

Hvert kvarter: har innstillingene i Kontrollsenter endret seg siden sist, lagres en kopi (bare de små
innstillingsfilene). Du kan se hva som endret seg og gå tilbake til et tidspunkt da alt virket.
"""
import hashlib
import json
import os
import time
import zipfile

CONF = os.path.expanduser("~/.config/systemmonitor")
DIR = os.path.expanduser("~/.local/share/systemmonitor/tidsmaskin")
KEEP = 40
SKIP = {"strom-dager.json", "peaks.json", "faner.json", "kategorier.json"}   # endres av seg selv hele tiden


def _ok():
    try:
        import perf
        return perf.disk_ok("tidsmaskin")
    except Exception:  # noqa: BLE001
        return True


def _files():
    out = {}
    if not os.path.isdir(CONF):
        return out
    for n in sorted(os.listdir(CONF)):
        p = os.path.join(CONF, n)
        if n in SKIP or not os.path.isfile(p) or os.path.getsize(p) > 2 * 1024 * 1024:
            continue
        if not n.endswith((".json", ".conf", ".txt")):
            continue
        try:
            out[n] = open(p, "rb").read()
        except OSError:
            pass
    return out


def _digest(files):
    return {n: hashlib.sha1(b).hexdigest() for n, b in files.items()}


def snapshots():
    """[(tid, filnavn, [endrede filer])] nyeste først."""
    if not os.path.isdir(DIR):
        return []
    out = []
    for n in sorted(os.listdir(DIR), reverse=True):
        if not n.endswith(".zip"):
            continue
        try:
            with zipfile.ZipFile(os.path.join(DIR, n)) as z:
                meta = json.loads(z.read("_tidsmaskin.json"))
            out.append((meta["t"], n, meta.get("changed", []), meta.get("why", "")))
        except Exception:  # noqa: BLE001
            continue
    return out


def _last_digest():
    s = snapshots()
    if not s:
        return {}
    try:
        with zipfile.ZipFile(os.path.join(DIR, s[0][1])) as z:
            return json.loads(z.read("_tidsmaskin.json")).get("digest", {})
    except Exception:  # noqa: BLE001
        return {}


def snapshot(why="", force=False):
    """Ta en kopi hvis noe er endret (eller force). Returnerer filnavnet eller None."""
    if not _ok():
        return None
    files = _files()
    dg = _digest(files)
    old = _last_digest()
    changed = sorted(n for n in set(dg) | set(old) if dg.get(n) != old.get(n))
    if not changed and not force:
        return None
    os.makedirs(DIR, exist_ok=True)
    name = time.strftime("%Y%m%d-%H%M%S") + ".zip"
    with zipfile.ZipFile(os.path.join(DIR, name), "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in files.items():
            z.writestr(n, b)
        z.writestr("_tidsmaskin.json", json.dumps({"t": time.time(), "changed": changed if old else [],
                                                   "digest": dg, "why": why}))
    for _t, n, _c, _w in snapshots()[KEEP:]:
        try:
            os.remove(os.path.join(DIR, n))
        except OSError:
            pass
    return name


def restore(name):
    """Gå tilbake til et tidspunkt (tar en kopi av slik det er nå først, så det kan angres)."""
    path = os.path.join(DIR, os.path.basename(name))
    if not os.path.isfile(path):
        raise FileNotFoundError("fant ikke kopien")
    snapshot(why="før tilbakestilling", force=True)
    n = 0
    with zipfile.ZipFile(path) as z:
        for f in z.namelist():
            if f == "_tidsmaskin.json" or "/" in f or "\\" in f or f.startswith("."):
                continue
            with open(os.path.join(CONF, f), "wb") as out:
                out.write(z.read(f))
            n += 1
    return n


NAMES = {"ytelse.json": "Ytelse", "oppdater-alt.json": "Oppdateringer", "bakgrunn.json": "Bakgrunn og varsler",
         "huset.json": "Huset", "lyd.json": "Lyd", "familie.json": "Familie", "scener.json": "Scener",
         "programvalg.json": "Programvalg", "strom.json": "Strøm", "utseende.json": "Utseende",
         "dashboard.json": "Oversikt", "enkel.json": "Enkel modus", "smarthjem.json": "Smart Hjem"}


def nice(files):
    return ", ".join(NAMES.get(f, f.rsplit(".", 1)[0]) for f in files[:5]) + (" …" if len(files) > 5 else "")
