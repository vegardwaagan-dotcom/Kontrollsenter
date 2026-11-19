"""Oppdater alt – ett sted for alle oppdateringer Kontrollsenter kan gjøre, og én bryter for automatikken.

Kilder (det som finnes på PC-en):
  ks        Kontrollsenter selv (fra hjemmenettet / NAS-en)
  apps      Programmene – Flatpak på Linux, winget på Windows (også de funksjonene i Kontrollsenter bruker)
  system    Linux: ny systemversjon (rpm-ostree, med drivere) eller dnf · Windows: Windows Update
  firmware  Linux: fastvare (fwupd) – BIOS, SSD, mus/tastatur m.m.
  pcs       Kontrollsenter på de andre PC-ene hjemme

Automatikk (bryteren «Automatisk oppdatering og opprydding»):
  på  – som før: Kontrollsenter ser etter oppdateringer, oppdaterer seg selv om natten (om valgt) og rydder disken
        én gang i måneden.
  av  – alt gjøres manuelt: ingen automatiske sjekker, oppdateringer eller opprydding. Bruk «Oppdater alt».
Windows Update og systemets egne automatiske oppdateringer styres fortsatt av Windows/Linux.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

IS_WIN = sys.platform == "win32"
CFG = os.path.expanduser("~/.config/systemmonitor/oppdater-alt.json")
_FLAGS = {"creationflags": 0x08000000} if IS_WIN else {}
_STATE = {"t": 0, "v": None, "busy": False, "running": False, "last": None}
_LOCK = threading.Lock()
_LISTENERS = []


# --------------------------------------------------------------------------
# Innstilling: automatikk av/på
# --------------------------------------------------------------------------
def cfg():
    try:
        d = json.load(open(CFG))
    except (OSError, ValueError):
        d = {}
    d.setdefault("auto", True)
    return d


def auto_on():
    return bool(cfg()["auto"])


def set_auto(on):
    d = cfg()
    d["auto"] = bool(on)
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    json.dump(d, open(CFG, "w"))
    _changed()


def on_change(fn):
    _LISTENERS.append(fn)


def _changed():
    for fn in list(_LISTENERS):
        try:
            from gi.repository import GLib
            GLib.idle_add(lambda f=fn: (f(), False)[1])
        except Exception:  # noqa: BLE001
            pass


def _run(cmd, t=120):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=t, encoding="utf-8", errors="replace",
                           **_FLAGS)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


# --------------------------------------------------------------------------
# Programmer: Flatpak (Linux) og winget (Windows)
# --------------------------------------------------------------------------
def flatpak_updates():
    """[(id, navn)] med ventende oppdateringer."""
    if not shutil.which("flatpak"):
        return []
    code, out = _run(["flatpak", "remote-ls", "--updates", "--columns=application,name"], 180)
    res = []
    for ln in out.splitlines():
        p = ln.split("\t")
        if p and re.fullmatch(r"[A-Za-z0-9_.-]+\.[A-Za-z0-9_.-]+", p[0].strip()):
            res.append((p[0].strip(), (p[1].strip() if len(p) > 1 else p[0].split(".")[-1])))
    return res


def winget_updates():
    """[(id, navn)] fra «winget upgrade» (tabellen leses etter overskriftens kolonner – også på norsk)."""
    if not shutil.which("winget"):
        return []
    code, out = _run(["winget", "upgrade", "--accept-source-agreements", "--disable-interactivity",
                      "--include-unknown"], 180)
    return parse_winget(out)


def parse_winget(out):
    lines = [ln.split("\r")[-1].rstrip() for ln in out.splitlines()]
    try:
        hi = next(i for i, ln in enumerate(lines) if i + 1 < len(lines) and re.fullmatch(r"-{10,}", lines[i + 1]))
    except StopIteration:
        return []
    starts = [m.start() for m in re.finditer(r"\S+", lines[hi])]
    if len(starts) < 4:
        return []
    res = []
    for ln in lines[hi + 2:]:
        if not ln.strip() or re.match(r"^\d+ (upgrades?|oppgraderinger?|pakker?)", ln, re.I) or len(ln) < starts[2]:
            continue
        name = ln[:starts[1]].strip()
        pid = ln[starts[1]:starts[2]].strip()
        if pid and re.fullmatch(r"[\w.+-]+", pid):
            res.append((pid, name))
    return res


def app_updates(refresh=False):
    """{id: navn} for programmer med oppdatering (mellomlagret 30 min)."""
    st = status(refresh=refresh, only=("apps",))
    src = next((s for s in st if s["key"] == "apps"), None)
    return dict(src["items"]) if src else {}


def update_ids(ids, t=None):
    """Oppdater bestemte programmer (Flatpak- eller winget-id-er)."""
    import progress as P
    t = t or P.NULL
    if not ids:
        return True, "Ingenting å oppdatere"
    if IS_WIN:
        bad = []
        for i, pid in enumerate(ids):
            t.step(i, len(ids), f"Oppdaterer {pid}")
            code, _o = P.run_cmd(["winget", "upgrade", "--id", pid, "-e", "--silent", "--accept-package-agreements",
                                  "--accept-source-agreements", "--disable-interactivity"], t.sub(i / len(ids),
                                                                                                  (i + 1) / len(ids)), 1800)
            if code != 0:
                bad.append(pid)
        ok = not bad
        msg = "Oppdatert" if ok else f"Feilet: {', '.join(bad)}"
    else:
        code, out = P.run_cmd(["flatpak", "update", "-y", "--noninteractive", *ids], t, 3600)
        ok = code == 0
        msg = "Oppdatert" if ok else (out.strip().splitlines() or ["feilet"])[-1][:120]
    _forget("apps")
    return ok, msg


# --------------------------------------------------------------------------
# System og fastvare
# --------------------------------------------------------------------------
def _ostree():
    return os.path.exists("/run/ostree-booted") and shutil.which("rpm-ostree")


def system_check():
    """(antall, tekst) – 0 = oppdatert, -1 = ukjent."""
    if IS_WIN:
        ps = ("$s = New-Object -ComObject Microsoft.Update.Session; "
              "($s.CreateUpdateSearcher().Search('IsInstalled=0 and IsHidden=0')).Updates.Count")
        code, out = _run(["powershell", "-NoProfile", "-Command", ps], 240)
        try:
            n = int(out.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return -1, "Kunne ikke spørre Windows Update"
        return n, "Oppdatert" if n == 0 else f"{n} oppdateringer i Windows Update"
    if _ostree():
        code, out = _run(["rpm-ostree", "status", "--json"], 60)
        try:
            deps = json.loads(out).get("deployments", [])
            staged = next((d for d in deps if d.get("staged")), None)
        except ValueError:
            staged = None
        if staged:
            return 0, f"Systemversjon {staged.get('version', '')} er lastet ned – start PC-en på nytt"
        code, out = _run(["rpm-ostree", "upgrade", "--check"], 240)
        if code == 77 or "No updates available" in out:
            return 0, "Oppdatert"
        if code == 0:
            v = re.search(r"Version:\s*(\S+)", out)
            return 1, f"Ny systemversjon {v.group(1) if v else ''} (kjerne, drivere, Mesa, NVIDIA)".replace("  ", " ")
        return -1, "Kunne ikke sjekke systemet"
    if shutil.which("dnf"):
        code, out = _run(["dnf", "-q", "check-update"], 240)
        if code == 100:
            n = len([ln for ln in out.splitlines() if re.match(r"^\S+\.\S+\s+\S+\s+\S+", ln)])
            return n, f"{n} systempakker kan oppdateres"
        return (0, "Oppdatert") if code == 0 else (-1, "Kunne ikke sjekke systemet")
    return -1, "Ikke støttet på denne Linux-varianten"


def system_apply(t):
    import progress as P
    if IS_WIN:
        try:
            subprocess.Popen(["UsoClient.exe", "StartInteractiveScan"], **_FLAGS)
        except OSError:
            pass
        import winsupport
        winsupport.open_uri("ms-settings:windowsupdate")
        return True, "Windows Update er startet (installeres av Windows)"
    if _ostree():
        code, out = P.run_cmd(["rpm-ostree", "upgrade"], t, 3600)
        return code == 0, ("Lastet ned – start PC-en på nytt for å bruke den nye versjonen" if code == 0
                           else (out.strip().splitlines() or ["feilet"])[-1][:120])
    if shutil.which("dnf"):
        code, out = P.run_cmd(["pkexec", "dnf", "upgrade", "-y", "--refresh"], t, 3600)
        return code == 0, "Oppdatert" if code == 0 else "Feilet eller avbrutt"
    return False, "Ikke støttet"


def firmware_check():
    if IS_WIN or not shutil.which("fwupdmgr"):
        return None
    code, out = _run(["fwupdmgr", "get-updates", "--json"], 180)
    try:
        devs = [d for d in json.loads(out).get("Devices", []) if d.get("Releases")]
    except ValueError:
        return 0, "Oppdatert"
    names = [d.get("Name", "?") for d in devs]
    return len(devs), ("Oppdatert" if not devs else "Ny fastvare: " + ", ".join(names[:3]))


def firmware_apply(t):
    import progress as P
    code, out = P.run_cmd(["pkexec", "fwupdmgr", "update", "-y", "--no-reboot-check"], t, 3600)
    return code == 0, "Oppdatert (noe tas i bruk ved omstart)" if code == 0 else "Feilet eller avbrutt"


# --------------------------------------------------------------------------
# Kontrollsenter og de andre PC-ene
# --------------------------------------------------------------------------
def ks_check():
    import lanupdate as L
    try:
        _txt, new = L.check()
    except Exception:  # noqa: BLE001
        return -1, "Fant ikke hjemmenettet", None
    if new:
        return 1, f"Versjon {new} er klar", new
    return 0, "Oppdatert", None


def _ver(v):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return (0,)


def pcs_check():
    try:
        import applog
        import homepcs
        import savegames
        mine = _ver(applog.RUNNING)
        me = savegames.pc_name()
        pcs = [p for p in (homepcs.fetch() or []) if p.get("name") != me
               and time.time() - (p.get("time") or 0) < homepcs.STALE]          # bare de som er på
        old = [p for p in pcs if p.get("version") and _ver(p["version"]) < mine]
    except Exception:  # noqa: BLE001
        return None
    if not pcs:
        return None
    return len(old), ("Alle har nyeste versjon" if not old else
                      "Eldre versjon på " + ", ".join(p["name"] for p in old[:4])), old


# --------------------------------------------------------------------------
# Status for alle kildene
# --------------------------------------------------------------------------
NAMES = {"ks": "Kontrollsenter", "apps": "Programmer", "system": "Windows Update" if IS_WIN else "System og drivere",
         "firmware": "Fastvare", "pcs": "De andre PC-ene hjemme"}
_PART = {}


def _forget(key=None):
    with _LOCK:
        if key:
            _PART.pop(key, None)
        else:
            _PART.clear()
        _STATE["t"] = 0


def _check_one(key):
    if key == "ks":
        n, txt, new = ks_check()
        return {"count": n, "detail": txt, "items": [("ks", new)] if new else []}
    if key == "apps":
        items = winget_updates() if IS_WIN else flatpak_updates()
        return {"count": len(items), "items": items,
                "detail": "Oppdatert" if not items else ", ".join(n for _i, n in items[:4]) +
                (f" og {len(items) - 4} til" if len(items) > 4 else "")}
    if key == "system":
        n, txt = system_check()
        return {"count": n, "detail": txt, "items": []}
    if key == "firmware":
        r = firmware_check()
        return None if r is None else {"count": r[0], "detail": r[1], "items": []}
    if key == "pcs":
        r = pcs_check()
        return None if r is None else {"count": r[0], "detail": r[1], "items": [(p["name"], p) for p in r[2]]}
    return None


def status(refresh=False, only=None, max_age=1800):
    """[{key, name, count, detail, items}] – sjekkes parallelt og huskes i 30 min. count -1 = ukjent."""
    with _CHECK:
        return _status(refresh, only, max_age)


_CHECK = threading.Lock()


def _status(refresh, only, max_age):
    keys = list(only or NAMES)
    now = time.time()
    need = [k for k in keys if refresh or k not in _PART or now - _PART[k][0] > max_age]
    if need:
        res = {}

        def one(k):
            try:
                res[k] = _check_one(k)
            except Exception as e:  # noqa: BLE001
                res[k] = {"count": -1, "detail": str(e)[:100], "items": []}
        th = [threading.Thread(target=one, args=(k,), daemon=True) for k in need]
        for x in th:
            x.start()
        for x in th:
            x.join(300)
        with _LOCK:
            for k in need:
                _PART[k] = (time.time(), res.get(k))
            _STATE["t"] = time.time()
    out = []
    for k in keys:
        v = (_PART.get(k) or (0, None))[1]
        if v is not None:
            out.append({"key": k, "name": NAMES[k], **v})
    return out


def cached():
    """Det som allerede er sjekket (uten å vente)."""
    out = []
    for k in NAMES:
        v = (_PART.get(k) or (0, None))[1]
        if v is not None:
            out.append({"key": k, "name": NAMES[k], **v})
    return out


def total(st=None):
    return sum(max(0, s["count"]) for s in (st if st is not None else cached()))


def running():
    return _STATE["running"]


# --------------------------------------------------------------------------
# Oppdater alt
# --------------------------------------------------------------------------
def update_all(win=None, include_pcs=True, on_done=None):
    """Oppdater alt som har oppdateringer. Kjøres i en tråd; fremdrift vises i vinduet og i appen."""
    if _STATE["running"]:
        return False
    _STATE["running"] = True

    def work():
        import progress as P
        t = P.begin("Oppdaterer alt", "Ser etter oppdateringer …")
        results, restart = [], False
        try:
            st = [s for s in status(refresh=True) if s["count"] > 0 and (include_pcs or s["key"] != "pcs")]
            order = ["apps", "firmware", "system", "pcs", "ks"]           # Kontrollsenter sist (starter på nytt)
            st.sort(key=lambda s: order.index(s["key"]))
            if not st:
                t.done("Alt er allerede oppdatert ✓")
                results.append(("Alt", True, "Allerede oppdatert"))
            for i, s in enumerate(st):
                sub = t.sub(i / len(st), (i + 1) / len(st))
                t.set(None, f"{s['name']} …")
                try:
                    if s["key"] == "apps":
                        ok, msg = update_ids([x[0] for x in s["items"]], sub)
                    elif s["key"] == "system":
                        ok, msg = system_apply(sub)
                    elif s["key"] == "firmware":
                        ok, msg = firmware_apply(sub)
                    elif s["key"] == "pcs":
                        import homepcs
                        res = homepcs.update_all([p for _n, p in s["items"]])
                        ok = all(x[1] for x in res)
                        msg = "; ".join(f"{n}: {m}" for n, _o, m in res) or "Ingen andre PC-er er på"
                    elif s["key"] == "ks":
                        import lanupdate as L
                        import tools
                        ok, msg = L.apply_update(tools.PACKAGE_FILES)
                        restart = ok
                    else:
                        continue
                except Exception as e:  # noqa: BLE001
                    ok, msg = False, str(e)[:120]
                results.append((s["name"], ok, msg))
            if st:
                bad = [r for r in results if not r[1]]
                t.done("Alt er oppdatert ✓" if not bad else f"{len(bad)} av {len(results)} feilet", ok=not bad)
        except Exception as e:  # noqa: BLE001
            t.done(f"Feil: {e}", ok=False)
            results.append(("Oppdater alt", False, str(e)[:120]))
        finally:
            _STATE["running"] = False
            _STATE["last"] = {"t": time.time(), "results": results}
            _forget()
            try:
                import applog
                applog.log.info("Oppdater alt: %s", "; ".join(f"{n}: {'OK' if o else 'FEIL'} {m}" for n, o, m in results))
            except Exception:  # noqa: BLE001
                pass
            _changed()
            from gi.repository import GLib
            if on_done:
                GLib.idle_add(lambda: (on_done(results), False)[1])
            if restart and win is not None:
                GLib.timeout_add(1500, lambda: (win.restart_app(hidden=not win.get_visible()), False)[1])
    threading.Thread(target=work, daemon=True, name="oppdater-alt").start()
    return True


def summary_json():
    """Til mobilappen og de andre PC-ene."""
    return {"auto": auto_on(), "running": running(), "total": total(), "sources": cached(),
            "last": _STATE["last"], "checked": _STATE["t"]}
