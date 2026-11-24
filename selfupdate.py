"""Oppdater Kontrollsenter automatisk når programmet starter (bryter i Innstillinger › Oppdatering).

Når Kontrollsenter starter «fra kaldt» – etter at PC-en har vært slått av, eller etter at du lukket programmet helt –
ser det etter en ny versjon (hjemmenettet/NAS først, så GitHub). Finnes det en, installeres den, og programmet
starter på nytt av seg selv. Ved en omstart som Kontrollsenter selv gjør (--restarted) sjekkes det ikke, så det
aldri kan gå i ring. Venter hvis et spill kjører.
"""
import json
import os
import sys
import threading
import time

CFG = os.path.expanduser("~/.config/systemmonitor/selvoppdatering.json")
DEF = {"on": True, "last": "", "t": 0}


def cfg():
    try:
        return {**DEF, **json.load(open(CFG))}
    except (OSError, ValueError):
        return dict(DEF)


def set_(**kw):
    c = cfg()
    c.update(kw)
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    with open(CFG + ".tmp", "w") as f:
        json.dump(c, f)
    os.replace(CFG + ".tmp", CFG)
    return c


def enabled():
    return bool(cfg()["on"])


def fresh_start():
    """Startet programmet fra kaldt (ikke en omstart Kontrollsenter selv gjorde)?"""
    return "--restarted" not in sys.argv and not os.environ.get("SYSTEMMONITOR_APP_ID")


def run_at_start(win, notify=None, delay=10):
    """Kalles én gang ved oppstart. Sjekker i bakgrunnen og starter på nytt hvis noe ble installert."""
    if not (enabled() and fresh_start()):
        return False

    def work():
        time.sleep(delay)                                 # gi nettet og NAS-en litt tid etter oppstart
        import applog
        import lanupdate
        import tools
        try:
            if lanupdate.is_source_pc():                  # utviklings-PC-en legger selv ut versjonene
                return
        except Exception:  # noqa: BLE001
            pass
        for _ in range(30):                               # ikke midt i et spill – vent (maks 30 min)
            if not getattr(getattr(win, "bg", None), "game_name", None):
                break
            time.sleep(60)
        try:
            txt, can = tools.check_update()
        except Exception as e:  # noqa: BLE001
            applog.log.info("Automatisk oppdatering ved oppstart: kunne ikke sjekke (%s)", e)
            return
        if can == "restart":                              # nyere versjon er allerede installert
            ok, msg = True, "allerede installert"
        elif can:
            try:
                ok, msg = tools.do_update()
            except Exception as e:  # noqa: BLE001
                ok, msg = False, str(e)
        else:
            set_(t=time.time())
            return
        new = tools.read(os.path.join(tools.APP_DIR, "VERSION"), "?").strip()
        applog.log.info("Automatisk oppdatering ved oppstart: %s (%s)", "OK" if ok else "feilet", msg)
        if not ok:
            return
        set_(last=new, t=time.time())
        from gi.repository import GLib

        def restart():
            if notify:
                try:
                    notify("selfupdate", "Kontrollsenter er oppdatert", f"Versjon {new} – starter på nytt.")
                except Exception:  # noqa: BLE001
                    pass
            win.restart_app(hidden=not win.get_visible())
            return False
        GLib.timeout_add(1500, restart)
    threading.Thread(target=work, daemon=True, name="selvoppdatering").start()
    return True
