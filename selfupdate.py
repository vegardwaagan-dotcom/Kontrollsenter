"""Oppdatering når Kontrollsenter starter: NAS-en (hjemmenettet) og GitHub sjekkes. Automatisk på (bryter i
Innstillinger › Oppdatering): installeres og startes på nytt. Av: «Oppdatering klar» med knappen «Oppdater nå».

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
    """Kalles én gang ved oppstart. Ser etter ny versjon (NAS-en først, så GitHub) i bakgrunnen:
    automatisk oppdatering på → installer og start på nytt; av → «Oppdatering klar» (banner + varsel)."""
    if not fresh_start():
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
        try:
            txt, can = tools.check_update()
        except Exception as e:  # noqa: BLE001
            applog.log.info("Oppdatering ved oppstart: kunne ikke sjekke (%s)", e)
            return
        if not can:
            set_(t=time.time())
            return
        if not enabled():                                 # bare si fra – du bestemmer selv
            if can != "restart":                          # («restart»: banneret «Start på nytt» sier fra selv)
                from gi.repository import GLib
                GLib.idle_add(lambda: (show_ready(win, txt, notify), False)[1])
            return
        for _ in range(30):                               # ikke midt i et spill – vent (maks 30 min)
            if not getattr(getattr(win, "bg", None), "game_name", None):
                break
            time.sleep(60)
        if can == "restart":                              # nyere versjon er allerede installert
            ok, msg = True, "allerede installert"
        else:
            try:
                ok, msg = tools.do_update()
            except Exception as e:  # noqa: BLE001
                ok, msg = False, str(e)
        new = tools.read(os.path.join(tools.APP_DIR, "VERSION"), "?").strip()
        applog.log.info("Automatisk oppdatering ved oppstart: %s (%s)", "OK" if ok else "feilet", msg)
        if not ok:
            from gi.repository import GLib                # installasjonen feilet: vis i det minste at den finnes
            GLib.idle_add(lambda: (show_ready(win, txt, notify), False)[1])
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


def show_ready(win, txt, notify=None):
    """«Oppdatering klar»: banner øverst i vinduet + varsel med knapp (kjøres i GTK-tråden)."""
    import i18n
    title = txt.splitlines()[0] if txt else i18n.tr("En ny versjon av Kontrollsenter er klar")
    b = getattr(win, "update_banner", None)
    if b is not None:
        b.set_title(title)
        b.set_button_label(i18n.tr("Oppdater nå"))
        b.set_revealed(True)
    try:
        from gi.repository import Gio, GLib
        app = win.get_application()
        if app is not None and app.lookup_action("ks-update") is None:
            act = Gio.SimpleAction.new("ks-update", GLib.VariantType.new("s"))
            act.connect("activate", lambda *_: (win.present(), install_now(win)))
            app.add_action(act)
    except Exception:  # noqa: BLE001
        pass
    if notify:
        try:
            notify("selfupdate-ready", "Oppdatering klar", title, force=True,
                   buttons=[("Oppdater nå", "app.ks-update", "1")])
        except Exception:  # noqa: BLE001
            pass
    return False


def install_now(win):
    """Knappen «Oppdater nå»: installer (fra der sjekken fant den) og start på nytt."""
    import i18n
    b = getattr(win, "update_banner", None)
    if getattr(install_now, "busy", False):
        return
    install_now.busy = True
    if b is not None:
        b.set_title(i18n.tr("Oppdaterer Kontrollsenter …"))
        b.set_button_label("")

    def work():
        import applog
        import tools
        try:
            ok, msg = tools.do_update()
        except Exception as e:  # noqa: BLE001
            ok, msg = False, str(e)
        applog.log.info("Oppdater nå: %s (%s)", "OK" if ok else "feilet", msg)
        from gi.repository import GLib

        def done():
            install_now.busy = False
            if ok:
                set_(last=tools.read(os.path.join(tools.APP_DIR, "VERSION"), "?").strip(), t=time.time())
                win.restart_app(hidden=not win.get_visible())
            elif b is not None:
                b.set_title(i18n.tr("Oppdateringen feilet") + f": {str(msg)[:120]}")
                b.set_button_label(i18n.tr("Prøv igjen"))
            return False
        GLib.idle_add(done)
    threading.Thread(target=work, daemon=True, name="oppdater-naa").start()
