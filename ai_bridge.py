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
import time
import sys
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


_ASK = {"fn": None}                     # AI-siden viser «Godta / Avbryt» i samtalen (ellers et vindu)


def set_confirm_handler(fn):
    _ASK["fn"] = fn


def _confirm(win, what):
    """Spør brukeren før AI-en endrer noe. True = godtatt."""
    try:
        import ai
        if not ai.cfg().get("confirm", True):
            return True
    except Exception:  # noqa: BLE001
        pass
    import threading
    import uuid
    from gi.repository import GLib
    done = threading.Event()
    res = {"ok": False}
    qid = uuid.uuid4().hex[:8]
    ui = {"dlg": None}

    def answer(ok):
        if done.is_set():
            return
        res["ok"] = bool(ok)
        done.set()
        _PENDING.pop(qid, None)
        if ui["dlg"] is not None:                          # svart fra mobilen: lukk vinduet på PC-en
            GLib.idle_add(lambda: (ui["dlg"].close(), False)[1])
    _PENDING[qid] = {"id": qid, "what": what, "answer": answer, "t": time.time()}

    def ask():
        if _ASK["fn"]:
            try:
                _ASK["fn"](what, answer)
                return False
            except Exception:  # noqa: BLE001
                pass
        from gi.repository import Adw
        dlg = Adw.AlertDialog(heading="🤖 AI-en vil endre noe", body=what)
        dlg.add_response("nei", "Avbryt")
        dlg.add_response("ja", "Godta")
        dlg.set_response_appearance("ja", Adw.ResponseAppearance.SUGGESTED)
        dlg.connect("response", lambda _d, r_: answer(r_ == "ja"))
        ui["dlg"] = dlg
        dlg.present(win)
        return False
    GLib.idle_add(ask)
    done.wait(80)
    _PENDING.pop(qid, None)
    return res["ok"]


_PENDING = {}                            # «Godta / Avbryt» som venter – mobilen kan også svare


def pending():
    return [{"id": p["id"], "what": p["what"]} for p in _PENDING.values() if time.time() - p["t"] < 85]


def answer_pending(qid, ok):
    p = _PENDING.get(qid)
    if not p:
        return False
    p["answer"](ok)
    return True


def _need_ok(win, what):
    if not _confirm(win, what):
        raise PermissionError("Brukeren sa nei – ikke prøv igjen, foreslå heller noe annet")


def run(win, cmd, args):
    """Én ks-kommando. Returnerer tekst eller et objekt (blir JSON)."""
    import remote
    cmd = (cmd or "").lower()
    if cmd == "logg":                                       # feilmeldinger: Kontrollsenter + systemet
        import applog
        own = [ln for ln in applog.tail(400).splitlines() if any(w in ln for w in ("ERROR", "Traceback", "Feil",
                                                                                     "WARNING", "Error"))][-40:]
        sysl = ""
        try:
            import subprocess
            if sys.platform == "win32":
                sysl = subprocess.run(["powershell", "-NoProfile", "-Command",
                                       "Get-WinEvent -FilterHashtable @{LogName='System','Application';Level=1,2} "
                                       "-MaxEvents 25 | Format-Table -AutoSize TimeCreated,ProviderName,Message "
                                       "-Wrap | Out-String -Width 200"], capture_output=True, text=True,
                                      timeout=40, creationflags=0x08000000).stdout
            else:
                sysl = subprocess.run(["journalctl", "-p", "err", "-b", "-n", "40", "--no-pager", "-o", "short"],
                                      capture_output=True, text=True, timeout=20).stdout
        except Exception as e:  # noqa: BLE001
            sysl = f"(kunne ikke lese systemloggen: {e})"
        return {"kontrollsenter": own or "ingen feil", "system": sysl.strip()[-6000:] or "ingen feil"}
    if cmd in ("pcer", "pc-er", "pcs"):
        out = {}
        try:
            import homepcs
            import machine
            out["hjemme"] = [{k: p.get(k) for k in ("name", "version", "cpu_t", "gpu_t", "cpu_l", "watts", "game",
                                                    "os", "uptime")} | {"på": not p.get("off")}
                             for p in machine.merge_home(homepcs.fetch() or [])]
        except Exception as e:  # noqa: BLE001
            out["hjemme"] = f"(fikk ikke lest: {e})"
        try:
            import friends
            out["venner"] = [_short(d) for d in friends.fetch_all()]
        except Exception as e:  # noqa: BLE001
            out["venner"] = f"(fikk ikke lest: {e})"
        return out
    if cmd == "wow":
        try:
            import wowplus
            return _short(wowplus._state()) or "Ingen WoW-data ennå – logg inn i spillet med tillegget på"
        except Exception as e:  # noqa: BLE001
            return f"Ingen WoW-data ({e})"
    if cmd in ("kalender", "kal"):
        import datetime as dt
        import kalender as K
        sub = (args or [""])[0].lower()
        if sub in ("ny", "legg"):
            p = {}
            for kv in args[1:]:
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    p[k.lower()] = v.strip("\"'")
            ev = {"title": p.get("tittel") or p.get("title"), "date": p.get("dato") or p.get("date"),
                  "time": p.get("tid") or p.get("time") or "", "repeat": {"uke": "weekly", "måned": "monthly",
                                                                          "år": "yearly"}.get(p.get("gjenta", ""),
                                                                                             p.get("gjenta", "")),
                  "kind": p.get("type", "event"), "note": p.get("notat", ""),
                  "remind": int(p.get("varsle", 30 if (p.get("tid") or p.get("time")) else -1))}
            _need_ok(win, f"Legge inn i kalenderen: {ev['title']} {ev['date']} {ev['time']}".strip())
            e = K.add(ev)
            return f"✓ Lagt inn ({e['id']}): {e['title']} {e['date']} {e['time']} – Hjemmet › Kalender"
        if sub in ("slett", "fjern"):
            eid = (args[1:] or [""])[0]
            _need_ok(win, f"Slette kalenderhendelsen {eid}")
            return "✓ Slettet" if K.remove(eid) else "Fant ikke hendelsen"
        if sub in ("fri", "ferie"):
            y = int((args[1:] or [dt.date.today().year])[0])
            return [{"høytid": n, "feriedager": t, "fra": a.isoformat(), "til": b.isoformat(), "dager_fri": ln}
                    for n, t, a, b, ln in K.vacation_tips(y)]
        days = int(sub) if sub.isdigit() else 14
        t = dt.date.today()
        it = K.items(t, t + dt.timedelta(days=days))
        return {d.isoformat(): [f"{x['icon']} {x['title']}" + (f" {x['time']}" if x.get("time") else "")
                                + (f" (id {x['id']})" if x.get("id") else "") for x in lst
                                if x.get("kind") not in ("moon", "weather", "stat")] for d, lst in sorted(it.items())}
    if cmd == "regler":
        import ai_rules
        return [{"id": r["id"], "regel": ai_rules.describe(r)} for r in ai_rules.load()] or "Ingen automatiske oppgaver"
    if cmd == "regel":
        import ai_rules
        sub = (args or [""])[0].lower()
        if sub in ("ny", "new", "legg"):
            params = {}
            for kv in args[1:]:
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    params[k] = v.strip("\"'")
            import ai_rules as R
            preview = R.describe({**{k: (float(v) if k in ("over", "under") else v) for k, v in params.items()},
                                  "gjør": "varsel" if params.get("gjør", params.get("gjor")) == "varsel" else
                                  ("handling" if params.get("handling") else "varsel")})
            _need_ok(win, f"Lage en automatisk oppgave:\n{preview}")
            r = ai_rules.add(params)
            return f"✓ Lagt til ({r['id']}): {ai_rules.describe(r)}. Ligger under AI › ⋯ › Automatiske oppgaver."
        if sub in ("slett", "fjern", "delete"):
            rid = (args[1:] or [""])[0]
            _need_ok(win, f"Slette den automatiske oppgaven {rid}")
            return "✓ Slettet" if ai_rules.remove(rid) else "Fant ikke regelen – se «ks regler»"
        raise ValueError("bruk: ks regel ny … / ks regel slett <id>")
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
        _need_ok(win, "Gjøre: " + " ".join(args) + "\n" + actions()[a["a"]].get("om", ""))
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
        _need_ok(win, f"Endre innstillingen {args[1]} i {os.path.basename(p)} til {' '.join(args[2:])}")
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
        _need_ok(win, "Kjøre systemsjekken (retter vanlige feil)")
        ok, msg = remote.do_action(win, {"a": "syscheck"})
        return ("✓ " if ok else "✗ ") + str(msg)
    if cmd in ("hjelp", "help", ""):
        return __doc__
    raise ValueError(f"ukjent kommando «{cmd}» – se «ks hjelp»")
