"""Selvtest før en ny versjon legges ut: åpner ALLE sider og faner i Kontrollsenter og mobilappen, og feiler hvis
noe krasjer. Kjøres av lanupdate.publish() på utviklings-PC-en (eller for hånd: python3 selftest.py).

Sjekker
  1. kodesjekk: udefinerte navn i Python-filene (pyflakes, hvis den finnes) og syntaks i JavaScript (node)
  2. PC-appen: hver side og hver fane vises – alle «Uventet feil» og feil i kort fanges opp
  3. mobilappen (samme nettside som Android-appen viser): lastes og hver fane åpnes – JavaScript-feil fanges opp

Resultatet skrives til ~/.cache/systemmonitor/selvtest.json (versjon, ok, feil). Bruker en egen app-ID og egen
port, så den kjørende Kontrollsenter ikke påvirkes.
"""
import glob
import json
import logging
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
RESULT = os.path.expanduser("~/.cache/systemmonitor/selvtest.json")
KEEP = [os.path.expanduser("~/.config/systemmonitor/" + f) for f in ("faner.json", "fliser.json", "programvalg.json")]
PYFLAKES = [os.path.expanduser("~/.cache/ks-test/venv/bin/pyflakes"), shutil.which("pyflakes") or ""]
BAD_FLAKES = ("undefined name", "referenced before assignment", "syntax", "unexpected indent", "may be undefined")


def version():
    try:
        return open(os.path.join(HERE, "VERSION")).read().strip()
    except OSError:
        return "?"


def code_check():
    errs = []
    flakes = next((p for p in PYFLAKES if p and os.path.exists(p)), None)
    if flakes:
        r = subprocess.run([flakes, *sorted(glob.glob(os.path.join(HERE, "*.py")))], capture_output=True, text=True)
        for ln in (r.stdout + r.stderr).splitlines():
            if any(b in ln.lower() for b in BAD_FLAKES) and "star imports" not in ln and "unable to detect" not in ln:
                errs.append("kode: " + ln.replace(HERE + "/", ""))
    if shutil.which("node"):
        for f in sorted(glob.glob(os.path.join(HERE, "remote_web", "*.js"))):
            r = subprocess.run(["node", "--check", f], capture_output=True, text=True)
            if r.returncode:
                errs.append("js: " + os.path.basename(f) + ": " + (r.stderr.strip().splitlines() or ["?"])[-1])
    return errs


def ui_check(timeout=240):
    """Start en egen Kontrollsenter-prosess som går gjennom alt (se _child)."""
    env = dict(os.environ, SYSTEMMONITOR_APP_ID="no.waagan.KsSelftest", KS_SELFTEST="1")
    out = os.path.expanduser("~/.cache/systemmonitor/selvtest-ui.json")
    try:
        os.remove(out)
    except FileNotFoundError:
        pass
    keep = {}                                    # selvtesten bytter faner – legg brukerens valg tilbake etterpå
    for f in KEEP:
        try:
            keep[f] = open(f, "rb").read()
        except OSError:
            pass
    try:
        subprocess.run([sys.executable, os.path.abspath(__file__), "--child", out], cwd=HERE, env=env,
                       timeout=timeout, capture_output=True)
    except subprocess.TimeoutExpired:
        return ["ui: selvtesten ble ikke ferdig (hang?)"], {}
    finally:
        for f, data in keep.items():
            with open(f, "wb") as fh:
                fh.write(data)
    try:
        d = json.load(open(out))
    except (OSError, ValueError):
        return ["ui: selvtesten krasjet før den ble ferdig"], {}
    seen = d.get("seen", {})
    errs = list(d["errors"])
    if seen.get("pages", 0) < 10:
        errs.append(f"ui: bare {seen.get('pages', 0)} sider ble åpnet")
    if seen.get("web_tabs", 0) < 5:
        errs.append("ui: mobilappen ble ikke testet")
    return errs, seen


def run(ui=True):
    t = time.time()
    errs = code_check()
    seen = {}
    if ui:
        e2, seen = ui_check()
        errs += e2
    res = {"version": version(), "ok": not errs, "errors": errs[:60], "seen": seen, "t": time.time(),
           "secs": round(time.time() - t)}
    os.makedirs(os.path.dirname(RESULT), exist_ok=True)
    with open(RESULT, "w") as f:
        json.dump(res, f, indent=1, ensure_ascii=False)
    return res


def passed_for_current():
    try:
        r = json.load(open(RESULT))
        return r.get("ok") and r.get("version") == version() and time.time() - r.get("t", 0) < 6 * 3600
    except (OSError, ValueError):
        return False


# --------------------------------------------------------------------------
# Barneprosessen: selve gjennomgangen av appen
# --------------------------------------------------------------------------
def _child(out):
    sys.path.insert(0, HERE)
    sys.argv = ["systemmonitor.py"]
    errors = []
    seen = {"pages": 0, "tabs": 0, "web_tabs": 0}

    class Catch(logging.Handler):
        def emit(self, rec):
            if rec.levelno >= logging.ERROR:
                msg = rec.getMessage()
                if rec.exc_info:
                    import traceback
                    msg += " | " + "".join(traceback.format_exception(*rec.exc_info)).strip().splitlines()[-1]
                errors.append(f"[{STATE['where']}] {msg}"[:400])
    STATE = {"where": "oppstart"}
    import systemmonitor as S
    logging.getLogger("systemmonitor").addHandler(Catch())
    import whatsnew
    whatsnew.mark_seen()
    import remote
    remote.PORT = 27198
    from gi.repository import GLib, Gtk

    def finish():
        with open(out, "w") as f:
            json.dump({"errors": errors, "seen": seen}, f, ensure_ascii=False)
        os._exit(0)

    def tabbed_in(widget):
        import tabbed
        found = []

        def walk(w, depth=0):
            if isinstance(w, tabbed.TabbedPage):
                found.append(w)
                return
            if depth > 14:
                return
            c = w.get_first_child()
            while c is not None:
                walk(c, depth + 1)
                c = c.get_next_sibling()
        walk(widget)
        return found

    class T(S.MonitorApp):
        def do_activate(self):
            S.MonitorApp.do_activate(self)
            win = self.win
            pages = win.stack.get_pages()
            names = [pages.get_item(i).get_name() for i in range(pages.get_n_items())]
            steps = []
            for n in names:
                steps.append(("page", n, None))
                steps.append(("tabs", n, None))
            steps.append(("web", None, None))
            sched = list(steps)

            def nxt():
                if not sched:
                    finish()
                    return False
                kind, name, _ = sched.pop(0)
                try:
                    if kind == "page":
                        STATE["where"] = f"side {name}"
                        win.stack.set_visible_child_name(name)
                        seen["pages"] += 1
                        GLib.timeout_add(1500, nxt)
                    elif kind == "tabs":
                        child = win.stack.get_child_by_name(name)
                        tabs = []
                        for tp in tabbed_in(child) if child else []:
                            p = tp.stack.get_pages()
                            tabs += [(tp, p.get_item(j).get_name()) for j in range(p.get_n_items())]

                        def tab_step():
                            if not tabs:
                                GLib.idle_add(nxt)
                                return False
                            tp, tn = tabs.pop(0)
                            STATE["where"] = f"side {name} → fane {tn}"
                            try:
                                tp.show_tab(tn)
                                seen["tabs"] += 1
                            except Exception as e:  # noqa: BLE001
                                errors.append(f"[{STATE['where']}] {e}")
                            GLib.timeout_add(900, tab_step)
                            return False
                        tab_step()
                    elif kind == "web":
                        STATE["where"] = "mobilappen"
                        _web(self, errors, nxt, seen)
                except Exception as e:  # noqa: BLE001
                    errors.append(f"[{STATE['where']}] {type(e).__name__}: {e}")
                    GLib.timeout_add(300, nxt)
                return False
            GLib.timeout_add(5000, nxt)
            GLib.timeout_add_seconds(200, lambda: (errors.append("ui: tidsavbrudd"), finish()))

    def _web(app, errors, done, seen):
        import gc
        import gi
        try:
            gi.require_version("WebKit", "6.0")
            from gi.repository import WebKit, Adw
        except (ValueError, ImportError):
            done()
            return
        srv = next((o for o in gc.get_objects() if type(o).__name__ == "Remote" and getattr(o, "httpd", None)), None)
        if srv is None:
            done()
            return
        real = srv.check
        srv.check = lambda tok: {"name": "Selvtest", "role": "full"} if tok == "selvtest" else real(tok)
        w = Adw.ApplicationWindow(application=app, default_width=412, default_height=900)
        wv = WebKit.WebView()
        pre = ('localStorage.setItem("ks_token","selvtest");window.__e=[];window.addEventListener("error",function(e)'
               '{window.__e.push((e.filename||"").split("/").pop()+":"+e.lineno+" "+e.message)});'
               'window.addEventListener("unhandledrejection",function(e){var m=String(e.reason&&e.reason.message||'
               'e.reason);if(!/fetch|network|abort|401|403|404|tidsavbrudd/i.test(m))window.__e.push("promise: "+m)});')
        wv.get_user_content_manager().add_script(WebKit.UserScript.new(
            pre, WebKit.UserContentInjectedFrames.TOP_FRAME, WebKit.UserScriptInjectionTime.START, None, None))
        w.set_content(wv)
        w.present()
        wv.load_uri(f"http://127.0.0.1:{remote.PORT}/app/")
        tabs = ["oversikt", "kontroll", "spill", "mer", "system", "oversikt"]

        def step():
            if tabs:
                t = tabs.pop(0)
                seen["web_tabs"] += 1
                wv.evaluate_javascript(f'document.querySelector("[data-tab={t}]")&&document.querySelector('
                                       f'"[data-tab={t}]").click()', -1, None, None, None, None)
                GLib.timeout_add(1500, step)
                return False

            def got(v, res):
                try:
                    r = v.evaluate_javascript_finish(res)
                    for e in json.loads(r.to_string() or "[]"):
                        errors.append(f"[mobilappen] {e}")
                except Exception as e:  # noqa: BLE001
                    errors.append(f"[mobilappen] kunne ikke lese feil: {e}")
                done()
            wv.evaluate_javascript("JSON.stringify(window.__e||[])", -1, None, None, None, got)
            return False
        GLib.timeout_add(6000, step)

    T().run([])


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--child":
        _child(sys.argv[2])
    else:
        r = run(ui="--kode" not in sys.argv)
        print(("✓ Selvtest OK" if r["ok"] else "✗ Selvtest feilet") + f" ({r['version']}, {r['secs']} s, "
              f"{r['seen'].get('pages', 0)} sider, {r['seen'].get('tabs', 0)} faner, "
              f"{r['seen'].get('web_tabs', 0)} mobilfaner)")
        for e in r["errors"]:
            print("  -", e)
        sys.exit(0 if r["ok"] else 1)
