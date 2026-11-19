"""Windows: PowerShell-kall skal aldri få vinduet til å stå stille.

På Windows bruker Kontrollsenter PowerShell til mye (skjermkort, VR-hodesett, brannmur, lyd, disker …). Hvert kall
tar 0,5–2 sekunder. Mange skjer mens en side bygges – og da står vinduet stille.

Dette laget legger seg rundt subprocess.run (én gang ved oppstart) og gjør tre ting:
  1. Lese-spørringer (Get-…, ingen endringer) huskes i 8 sekunder, så samme spørsmål ikke kjøres flere ganger.
  2. Spør vinduet (GTK-tråden) om noe den har fått svar på før (også fra forrige gang programmet kjørte, lagret på
     disk), får den det forrige svaret med en gang – og et nytt svar hentes i bakgrunnen.
  3. Alt som endrer noe (Set-/Enable-/RunAs/pnputil/netsh …) tømmer minnet, så en sjekk etter en reparasjon alltid
     ser det nye.
I tillegg måles hvert kall som får vinduet til å vente; det står i loggen og vises i «Ytelse»-kortet.
"""
import base64
import json
import logging
import os
import re
import subprocess
import threading
import time
import traceback

log = logging.getLogger("systemmonitor")
FRESH = 8                 # sekunder et svar regnes som nytt
STALE_MAX = 24 * 3600     # så gammelt svar kan vinduet få (mens et nytt hentes)
CACHE_FILE = os.path.join(os.path.expanduser("~"), ".cache", "systemmonitor", "ps-svar.json")
_MUTATE = re.compile(r"\b(Set|Start|Stop|Remove|Enable|Disable|Add|Clear|Invoke|Restart|Install|Uninstall|Register|"
                     r"Unregister|Update|Mount|Dismount|Rename|Move|Copy|Out|Export|Suspend|Resume|Reset|Repair|"
                     r"Send|Write|Grant|Revoke|Lock|Unlock)-|RunAs|pnputil|netsh|\breg(\.exe)?\s+(add|delete|import)|"
                     r"New-(?!Object)|\.(Set|Put|Delete|Save|Invoke)\w*\(|shutdown|bcdedit", re.I)
_READ = re.compile(r"\b(Get|Test|Measure|Resolve|Select|Find|Search)-|NameSpace\(|CreateUpdateSearcher", re.I)
_ORIG = subprocess.run
_LOCK = threading.Lock()
_MEM = {}                 # nøkkel -> (tid, returncode, stdout, stderr)
_BUSY = set()
_DIRTY = [False]
STATS = {"waits": 0, "wait_ms": 0, "max_ms": 0, "worst": "", "hits": 0, "stale": 0, "runs": 0}
_WAITED = {}              # kommando -> (antall, sum ms) – for loggen


def _main():
    return threading.current_thread() is threading.main_thread()


def _ps_text(args):
    """PowerShell-kommandoteksten hvis args er et rent lese-kall, ellers None."""
    if not isinstance(args, (list, tuple)) or not args:
        return None
    exe = os.path.basename(str(args[0])).lower()
    if exe not in ("powershell", "powershell.exe", "pwsh", "pwsh.exe"):
        return None
    a = [str(x) for x in args]
    if "-File" in a or "-file" in a:
        return None
    try:
        i = next(n for n, x in enumerate(a) if x.lower() == "-command")
    except StopIteration:
        return None
    return " ".join(a[i + 1:])


def is_read(args):
    t = _ps_text(args)
    return bool(t) and bool(_READ.search(t)) and not _MUTATE.search(t)


def _mutating(args):
    if not isinstance(args, (list, tuple)) or not args:
        return False
    exe = os.path.basename(str(args[0])).lower()
    if exe in ("pnputil", "pnputil.exe", "netsh", "netsh.exe", "reg", "reg.exe", "sc", "sc.exe", "bcdedit"):
        return True
    t = _ps_text(args)
    if t is None and exe.startswith(("powershell", "pwsh")):
        return True                                        # -File-skript o.l.: kan endre hva som helst
    return bool(t) and bool(_MUTATE.search(t))


def _key(args, kw):
    text = bool(kw.get("text") or kw.get("universal_newlines") or kw.get("encoding"))
    return json.dumps([list(map(str, args)), text, str(kw.get("input") or "")])


def _enc(v):
    if isinstance(v, bytes):
        return {"b": base64.b64encode(v).decode()}
    return v


def _dec(v):
    if isinstance(v, dict) and "b" in v:
        return base64.b64decode(v["b"])
    return v


def _disk():
    try:
        import perf
        return perf.disk_ok("pssvar")
    except Exception:  # noqa: BLE001
        return True


def _load_disk():
    if not _disk():
        return
    try:
        d = json.load(open(CACHE_FILE, encoding="utf-8"))
        now = time.time()
        for k, (t, rc, out, err) in d.items():
            if now - t < STALE_MAX:
                _MEM.setdefault(k, (t, rc, _dec(out), _dec(err)))
    except (OSError, ValueError, TypeError):
        pass


def _save_disk():
    if not _DIRTY[0] or not _disk():
        return
    _DIRTY[0] = False
    try:
        with _LOCK:
            d = {k: (t, rc, _enc(o), _enc(e)) for k, (t, rc, o, e) in _MEM.items()
                 if len(o or "") < 200000}
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        tmp = CACHE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.replace(tmp, CACHE_FILE)
    except OSError:
        pass


def clear():
    with _LOCK:
        _MEM.clear()
    _DIRTY[0] = True


def _store(k, cp):
    with _LOCK:
        _MEM[k] = (time.time(), cp.returncode, cp.stdout, cp.stderr)
    _DIRTY[0] = True


def _cp(args, ent):
    return subprocess.CompletedProcess(args, ent[1], ent[2], ent[3])


def _where():
    for f in reversed(traceback.extract_stack()[:-3]):
        n = os.path.basename(f.filename)
        if n not in ("winperf.py", "subprocess.py", "winsupport.py", "threading.py"):
            return f"{n}:{f.lineno} {f.name}"
    return "?"


def _note_wait(args, ms):
    STATS["waits"] += 1
    STATS["wait_ms"] += ms
    cmd = (_ps_text(args) or " ".join(map(str, args)))[:90]
    if ms > STATS["max_ms"]:
        STATS["max_ms"], STATS["worst"] = ms, f"{_where()} – {cmd}"
    n, tot = _WAITED.get(cmd, (0, 0))
    _WAITED[cmd] = (n + 1, tot + ms)
    if n < 3:                                              # ikke fyll loggen
        log.warning("Vinduet ventet %d ms på %s (%s)", ms, cmd, _where())


def run(args, *a, **kw):
    """Erstatter subprocess.run (bare på Windows)."""
    if kw.get("check") or a:
        return _ORIG(args, *a, **kw)
    main = _main()
    if _mutating(args):
        clear()
    elif is_read(args):
        k = _key(args, kw)
        with _LOCK:
            ent = _MEM.get(k)
        now = time.time()
        if ent and now - ent[0] < FRESH:
            STATS["hits"] += 1
            return _cp(args, ent)
        if ent and main:                                   # vinduet venter ikke: forrige svar nå, nytt i bakgrunnen
            STATS["stale"] += 1
            if k not in _BUSY:
                _BUSY.add(k)

                def refresh():
                    try:
                        _store(k, _ORIG(args, **kw))
                    except Exception:  # noqa: BLE001
                        pass
                    finally:
                        _BUSY.discard(k)
                threading.Thread(target=refresh, daemon=True, name="ps-oppdater").start()
            return _cp(args, ent)
        t0 = time.monotonic()
        cp = _ORIG(args, **kw)
        STATS["runs"] += 1
        _store(k, cp)
        if main:
            _note_wait(args, round((time.monotonic() - t0) * 1000))
        return cp
    t0 = time.monotonic()
    cp = _ORIG(args, **kw)
    if main:
        ms = round((time.monotonic() - t0) * 1000)
        if ms > 150:
            _note_wait(args, ms)
    return cp


# --------------------------------------------------------------------------
# Hakk-vakt: merker når vinduet står stille, og hvilken kodelinje som holdt det
# --------------------------------------------------------------------------
_BEAT = [0.0]
HAKK = {"n": 0, "ms": 0, "max": 0}
_WHERE = {}                # kodelinje -> ms


def _beat():
    now = time.monotonic()
    gap = (now - _BEAT[0]) * 1000 if _BEAT[0] else 0
    _BEAT[0] = now
    if gap > 400:          # 100 ms forventet – over 0,4 s er et hakk du merker
        HAKK["n"] += 1
        HAKK["ms"] += round(gap)
        HAKK["max"] = max(HAKK["max"], round(gap))
    return True


def _watch():
    import sys as _s
    main_id = threading.main_thread().ident
    while True:
        time.sleep(0.1)
        if not _BEAT[0] or time.monotonic() - _BEAT[0] < 0.35:
            continue
        fr = _s._current_frames().get(main_id)
        if fr is None:
            continue
        here = os.path.dirname(os.path.abspath(__file__))
        own = [f for f in traceback.extract_stack(fr) if os.path.dirname(os.path.abspath(f.filename)) == here
               and not f.filename.endswith(("winperf.py", "systemmonitor.py"))]
        if not own:
            own = [f for f in traceback.extract_stack(fr) if os.path.dirname(os.path.abspath(f.filename)) == here]
        if own:
            f = own[-1]
            k = f"{os.path.basename(f.filename)}:{f.lineno} {f.name}"
            _WHERE[k] = _WHERE.get(k, 0) + 100


def start_watch():
    from gi.repository import GLib
    GLib.timeout_add(100, _beat)
    threading.Thread(target=_watch, daemon=True, name="hakk-vakt").start()


def summary():
    """Kort tekst til «Ytelse»-kortet."""
    s = STATS
    hk = (f" Vinduet hakket {HAKK['n']} ganger (lengst {HAKK['max'] / 1000:.1f} s)." if HAKK["n"]
          else " Ingen hakk over 0,4 s.")
    if not s["waits"]:
        return f"Vinduet har ikke ventet på Windows-kommandoer ({s['hits'] + s['stale']} svar fra minnet)." + hk
    return (f"Vinduet ventet {s['waits']} ganger på Windows, til sammen {s['wait_ms'] / 1000:.1f} s (lengst "
            f"{s['max_ms']} ms). {s['hits'] + s['stale']} svar kom fra minnet." + hk)


def report():
    """Skriv de verste ventingene i loggen (sendes til NAS-en sammen med loggen)."""
    log.warning("Ytelse: %s", summary())
    for cmd, (n, tot) in sorted(_WAITED.items(), key=lambda kv: -kv[1][1])[:10]:
        log.warning("Ytelse:   %5d ms (%d×) %s", tot, n, cmd)
    for k, ms in sorted(_WHERE.items(), key=lambda kv: -kv[1])[:12]:
        log.warning("Ytelse: hakk %5d ms i %s", ms, k)
    try:
        import perf
        u = perf.usage()
        log.warning("Ytelse: Kontrollsenter bruker %.1f %% CPU, %s minne, leser %s/s, %d tråder (minimal: %s)",
                    u["cpu"], perf.human(u["rss"]), perf.human(u["read"]), u["threads"], perf.eco())
    except Exception:  # noqa: BLE001
        pass


def _saver():
    while True:
        time.sleep(30)
        try:
            import perf
            if perf.flag("ssd") and time.time() - _SAVED[0] < 900:
                continue
        except Exception:  # noqa: BLE001
            pass
        _SAVED[0] = time.time()
        _save_disk()


_INSTALLED = []
_SAVED = [0.0]


def install():
    if _INSTALLED:
        return
    _INSTALLED.append(True)
    _load_disk()
    subprocess.run = run
    try:
        start_watch()
    except Exception:  # noqa: BLE001
        pass
    threading.Thread(target=_saver, daemon=True, name="ps-lagre").start()
