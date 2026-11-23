"""AI-ens hender i Kontrollsenter: kommandoen «ks» (ks.py) sender hit via /api/local/ai (bare fra denne PC-en).

  ks status                 temperaturer, last, strøm, vifter, strømmodus (alt Oversikt viser)
  ks finn <ord>             hvor en innstilling ligger («Side › Fane › kort»), nummerert
  ks vis <nr>               åpne Kontrollsenter akkurat der (etter «ks finn»)
  ks side <navn>            åpne en side (ks sider for lista)
  ks handlinger [ord]       alt Kontrollsenter kan gjøre, med parametre
  ks gjør <handling> [nøkkel=verdi …]   gjør det (samme som knappene og mobilappen)
  ks innstillinger          innstillingsfilene
  ks les <fil>              les en innstillingsfil
  ks sett <fil> <nøkkel> <verdi>   endre én verdi i en innstillingsfil
  ks diagnose               hvorfor er PC-en treg / hva er galt nå
  ks systemsjekk            kjør systemsjekken (retter vanlige feil)
"""
import json
import os
import re
import threading

CONF = os.path.expanduser("~/.config/systemmonitor")
APP_DIR = os.path.dirname(os.path.abspath(__file__))
_FOUND = {"rows": []}
_ACTIONS = {"v": None}


def _main(fn, timeout=20):
    """Kjør i hovedtråden (GTK) og vent på svaret."""
    from gi.repository import GLib
    if threading.current_thread() is threading.main_thread():
        return fn()
    box, ev = {}, threading.Event()

    def w():
        try:
            box["r"] = fn()
        except Exception as e:  # noqa: BLE001
            box["e"] = e
        ev.set()
        return False
    GLib.idle_add(w)
    if not ev.wait(timeout):
        raise TimeoutError("Kontrollsenter svarte ikke i tide")
    if "e" in box:
        raise box["e"]
    return box.get("r")


def _short(v, depth=0):
    """Gjør status kompakt (ingen lange lister med historikk) og alt om til JSON-vennlige verdier."""
    import dataclasses
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        v = dataclasses.asdict(v)
    elif hasattr(v, "__dict__") and not isinstance(v, (str, int, float, bool, type(None))):
        v = {k: x for k, x in vars(v).items() if not k.startswith("_")}
    if isinstance(v, tuple):
        v = list(v)
    if isinstance(v, dict):
        return {k: _short(x, depth + 1) for k, x in list(v.items())[:60] if not k.startswith("_")}
    if isinstance(v, list):
        return [_short(x, depth + 1) for x in v[:12]]
    if isinstance(v, float):
        return round(v, 1)
    return v


def actions():
    """{handling: [parametre]} – lest fra koden til do_action (samme som knappene og mobilappen)."""
    if _ACTIONS["v"] is None:
        src = open(os.path.join(APP_DIR, "remote.py"), encoding="utf-8").read()
        start = src.index("def do_action(win, a):")
        body = src[start:src.index("\ndef ", start + 10)]
        out = {}
        parts = re.split(r'\n    if kind == "([a-z_0-9]+)":', body)
        for i in range(1, len(parts) - 1, 2):
            kind, block = parts[i], parts[i + 1]
            keys = sorted(set(re.findall(r'a\.get\("([a-z_0-9]+)"', block) + re.findall(r'a\["([a-z_0-9]+)"\]', block))
                          - {"a"})
            doc = re.search(r"#\s*(.+)", block.split("\n")[0]) or re.search(r'"""(.+?)"""', block)
            out[kind] = {"parametre": keys, "om": (doc.group(1).strip() if doc else "")[:120]}
        _ACTIONS["v"] = out
    return _ACTIONS["v"]


def _coerce(v):
    if v in ("true", "ja", "på"):
        return True
    if v in ("false", "nei", "av"):
        return False
    try:
        return int(v)
    except ValueError:
        try:
            return float(v)
        except ValueError:
            pass
    try:
        return json.loads(v)
    except ValueError:
        return v


def _safe_file(name):
    name = os.path.basename(str(name))
    if not name.endswith(".json"):
        name += ".json"
    p = os.path.join(CONF, name)
    if not os.path.isfile(p):
        raise ValueError(f"fant ikke {name} – se «ks innstillinger»")
    return p


def run(win, cmd, args):
    """Én ks-kommando. Returnerer tekst eller et objekt (blir JSON)."""
    import remote
    cmd = (cmd or "").lower()
    if cmd in ("status", "temp", "temperatur"):
        st = _main(lambda: remote.build_status(win))
        return _short(st)
    if cmd == "sider":
        return [{"navn": n, "tittel": win.stack.get_page(win.stack.get_child_by_name(n)).get_title()}
                for n in (getattr(win, "_lazy", {}) or {}) | {"oversikt": 1}
                if win.stack.get_child_by_name(n) is not None]
    if cmd == "side":
        name = (args or [""])[0]

        def go():
            if win.stack.get_child_by_name(name) is None:
                raise ValueError("ukjent side – se «ks sider»")
            win.ensure_lazy(name)
            win.stack.set_visible_child_name(name)
            win.present()
        _main(go)
        return f"Åpnet {name}"
    if cmd == "finn":
        q = " ".join(args or [])
        if not q:
            raise ValueError("bruk: ks finn <ord>")
        import search

        def find():
            for n, lz in (getattr(win, "_lazy", {}) or {}).items():   # bygg sidene så alt kan søkes i
                if lz[3] is None and n not in getattr(search, "SKIP_PAGES", ()):
                    try:
                        win.ensure_lazy(n)
                    except Exception:  # noqa: BLE001
                        pass
            rows = search.search(search.build_index(win), q, 15)
            _FOUND["rows"] = rows
            return [{"nr": i + 1, "hvor": f"{r[1]}" + (f" › {r[3]}" if r[3] else ""),
                     "tekst": r[4].splitlines()[0][:100]} for i, r in enumerate(rows)]
        res = _main(find, 60)
        return res or "Fant ingenting – prøv et annet ord"
    if cmd == "vis":
        i = int((args or ["1"])[0]) - 1
        rows = _FOUND["rows"]
        if not (0 <= i < len(rows)):
            raise ValueError("kjør «ks finn …» først")
        import search
        _main(lambda: (search.go_to(win, rows[i]), win.present()))
        return f"Viser {rows[i][1]}" + (f" › {rows[i][3]}" if rows[i][3] else "")
    if cmd == "handlinger":
        acts = actions()
        if args:
            q = " ".join(args).lower()
            acts = {k: v for k, v in acts.items() if q in k or q in v["om"].lower()}
        if "power" in acts:                                 # gyldige verdier der vi vet dem
            try:
                acts = {**acts, "power": {**acts["power"], "mode": sorted(win.power.buttons)}}
            except Exception:  # noqa: BLE001
                pass
        return acts
    if cmd in ("gjør", "gjor", "handling"):
        if not args:
            raise ValueError("bruk: ks gjør <handling> [nøkkel=verdi …]")
        a = {"a": args[0]}
        for kv in args[1:]:
            if "=" in kv:
                k, v = kv.split("=", 1)
                a[k] = _coerce(v)
        if a["a"] not in actions():
            raise ValueError("ukjent handling – se «ks handlinger»")
        ok, msg = remote.do_action(win, a)
        return ("✓ " if ok else "✗ ") + str(msg)
    if cmd == "innstillinger":
        return sorted(f for f in os.listdir(CONF) if f.endswith(".json"))
    if cmd == "les":
        with open(_safe_file((args or [""])[0]), encoding="utf-8") as f:
            d = json.load(f)
        for secret in ("key", "token", "password", "passord", "secret", "user", "hash"):
            if isinstance(d, dict) and secret in d:
                d[secret] = "(skjult)"
        return d
    if cmd == "sett":
        if len(args or []) < 3:
            raise ValueError("bruk: ks sett <fil> <nøkkel> <verdi>")
        p = _safe_file(args[0])
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict):
            raise ValueError("fila er ikke en innstillingsliste")
        keys = args[1].split(".")
        cur = d
        for k in keys[:-1]:
            cur = cur.setdefault(k, {})
        old = cur.get(keys[-1])
        cur[keys[-1]] = _coerce(" ".join(args[2:]))
        try:                                                # tidsmaskinen: kan angres
            import timemachine
            timemachine.snapshot(why=f"før AI endret {os.path.basename(p)}", force=True)
        except Exception:  # noqa: BLE001
            pass
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump(d, f, indent=1, ensure_ascii=False)
        os.replace(p + ".tmp", p)
        return f"✓ {os.path.basename(p)}: {args[1]} = {cur[keys[-1]]!r} (var {old!r}). Noen innstillinger trer i " \
               "kraft når siden åpnes på nytt eller Kontrollsenter startes på nytt."
    if cmd == "diagnose":
        import assistant
        return _short(_main(lambda: assistant.why_slow(win), 60))
    if cmd == "systemsjekk":
        ok, msg = remote.do_action(win, {"a": "syscheck"})
        return ("✓ " if ok else "✗ ") + str(msg)
    if cmd in ("hjelp", "help", ""):
        return __doc__
    raise ValueError(f"ukjent kommando «{cmd}» – se «ks hjelp»")
