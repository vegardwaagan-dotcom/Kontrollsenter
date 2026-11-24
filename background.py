"""Bakgrunnsmodus, varsler og ikon i systemstatusfeltet.

- Når «Kjør i bakgrunnen» er på, skjules vinduet i stedet for å avslutte når det lukkes.
- Varsler: høy CPU-/GPU-temperatur, nesten full disk, lavt batteri i trådløse enheter,
  funn i Systemsjekk og tilgjengelige oppdateringer (sjekkes hver 6. time).
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time

from gi.repository import Gio, GLib

CFG = os.path.expanduser("~/.config/systemmonitor/bakgrunn.json")
DEFAULTS = {"background": True, "tray": True, "notify": True, "cpu_limit": 90, "gpu_limit": 85,
            "disk_limit": 90, "battery_limit": 15, "periodic": True}
REPEAT = 30 * 60           # samme varsel tidligst igjen etter 30 min
PERIODIC = 6 * 3600

# Varseltyper du kan slå av og på hver for seg (Innstillinger → Varsler, og i mobilappen).
# (id, navn, forklaring, varselnøkler – nøkler som slutter på * matcher alt som starter slik)
KINDS = [
    ("temp", "Høy temperatur", "Prosessoren eller skjermkortet blir for varmt.", ["cpu", "gpu"]),
    ("disk", "Nesten full disk", "En disk har lite ledig plass igjen.", ["disk*"]),
    ("battery", "Lavt batteri", "Mus, tastatur, hodesett eller kontroller må lades.", ["bat*"]),
    ("syscheck", "Systemsjekk", "Systemsjekken i bakgrunnen fant noe som bør fikses.", ["syscheck"]),
    ("assistant", "PC-assistent", "Spillsjekk, ukens helserapport, varmere enn vanlig (støv) og tips når vinduet hakker.",
     ["gamecheck", "weekly", "anomaly", "lowend", "crash", "house", "price"]),
    ("updates", "Oppdateringer", "Nye programoppdateringer og nye versjoner av Kontrollsenter.",
     ["updates", "lanupdate", "lanpublish", "restart"]),
    ("chat", "Chat og anrop", "Meldinger i servere og direkte, anrop (Svar / Legg på / Demp), «Middag!» og «Spill "
     "sammen». Virker også når de andre varslene er slått av.",
     ["chat", "invite", "call"]),
    ("game", "Spillprofil", "Når spillmodus slås på automatisk fordi et spill startet.", ["game"]),
    ("session", "Rapport etter spilløkt", "FPS, temperaturer og strøm når du er ferdig med et spill.", ["session"]),
    ("clip", "Klipp lagret", "Når et klipp av de siste minuttene er lagret.", ["clip"]),
    ("night", "Stille om natten", "Når PC-en går over til stille nattmodus.", ["night"]),
    ("playtime", "Spilletid og leggetid", "Snart tom for spilletid, og leggetid om 10 minutter. "
     "Kan ikke slås av mens familiekontroll er på.", ["playlimit", "bedtime"]),
    ("batfull", "Fulladet batteri", "Når musa, headsettet eller tastaturet er ferdig ladet – så du kan ta ut kabelen.",
     ["full*"]),
    ("health", "Diskhelse og rask oppvarming", "Disken nærmer seg slitt, eller temperaturen stiger unormalt raskt.",
     ["smart*", "temprise*"]),
    ("goal", "Mål og belønning", "Når noen er ferdig med lekser e.l. og ber om ekstra spilletid – og svaret.", ["goal"]),
    ("vr", "VR", "Når VR-vakten har startet ALVR, SteamVR eller kabel-tilkoblingen igjen.", ["vr"]),
    ("plan", "Ukeplan", "Påminnelser om avtaler i familiens ukeplan (trening, middag, lekser …).", ["plan"]),
    ("weekly", "Ukesrapport", "Søndag kveld: spilletid per person, mest spilte spill og strøm denne uka.", ["weekly"]),
    ("pcplus", "PC-lege, strømbudsjett og krasjhjelp", "Ukas rapport fra AI-PC-legen, strømbudsjettet og tilbud om "
     "AI-hjelp etter et krasj.", ["ai_doctor", "crash_ai", "budget"]),
    ("cleanup", "Månedlig opprydding", "Rapport når Kontrollsenter har ryddet trygge ting (cache, miniatyrbilder).",
     ["cleanup"]),
    ("bg", "«Kjører i bakgrunnen»", "Beskjed første gang vinduet lukkes og programmet fortsetter i bakgrunnen.",
     ["bg"]),
]
ALWAYS = ("watch",)        # «noen ser på skjermen din» – personvern, vises alltid


def kind_of(key):
    for kid, _n, _d, keys in KINDS:
        for k in keys:
            if key == k or (k.endswith("*") and key.startswith(k[:-1])):
                return kid
    return None


def wants(cfg, key):
    """Skal varselet med denne nøkkelen vises? Følger hovedbryteren og valget per type."""
    if key in ALWAYS:
        return True
    kid = kind_of(key)
    if kid == "playtime":
        try:
            import familylock
            if familylock.locked():
                return True
        except Exception:  # noqa: BLE001
            pass
    if kid == "chat":                                      # chat og anrop: egen bryter (Chat → profil), ikke hovedbryteren
        return bool((cfg.get("kinds") or {}).get("chat", True))
    if not cfg.get("notify", True):
        return False
    if cfg.get("dnd") and kid not in ("playtime", "chat"):    # scene med «ingen varsler» (chat slipper gjennom)
        return False
    return bool((cfg.get("kinds") or {}).get(kid, True)) if kid else True


def load():
    try:
        with open(CFG) as f:
            return {**DEFAULTS, **json.load(f)}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save(cfg):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    with open(CFG, "w") as f:
        json.dump(cfg, f, indent=1)


def device_batteries():
    """Trådløse enheter med batteri fra UPower (mus, tastatur, hodesett, kontroller …)."""
    out = []
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        devs = bus.call_sync("org.freedesktop.UPower", "/org/freedesktop/UPower", "org.freedesktop.UPower",
                             "EnumerateDevices", None, None, Gio.DBusCallFlags.NONE, 3000, None).unpack()[0]
        for p in devs:
            props = bus.call_sync("org.freedesktop.UPower", p, "org.freedesktop.DBus.Properties", "GetAll",
                                  GLib.Variant("(s)", ("org.freedesktop.UPower.Device",)), None,
                                  Gio.DBusCallFlags.NONE, 3000, None).unpack()[0]
            # 1 = strømadapter, 2 = laptopbatteri, 3 = UPS – resten er tilkoblede enheter
            if props.get("Type") in (0, 1, 2, 3) or not props.get("IsPresent", True):
                continue
            if props.get("State") == 1:          # lader
                continue
            name = props.get("Model") or props.get("NativePath") or "Enhet"
            out.append((p, name, float(props.get("Percentage", 100))))
    except GLib.Error:
        pass
    return out


def flatpak_updates():
    if not shutil.which("flatpak"):
        return 0
    try:
        r = subprocess.run(["flatpak", "remote-ls", "--updates", "--columns=application"],
                           capture_output=True, text=True, timeout=120)
        return len([x for x in r.stdout.splitlines() if x.strip()])
    except (OSError, subprocess.SubprocessError):
        return 0



def _tray_host():
    """Finnes det et statusfelt for ikoner (KDE, GNOME med AppIndicator, XFCE, Cinnamon …)?"""
    try:
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        return bool(bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                                  "NameHasOwner", GLib.Variant("(s)", ("org.kde.StatusNotifierWatcher",)),
                                  None, 0, 2000, None).unpack()[0])
    except Exception:  # noqa: BLE001
        return True

class Background:
    """Kobles til hovedvinduet. win må ha: cpu_temp_now(), gpu_temp_now(), power (PowerCard)."""

    def __init__(self, app, win):
        self.app, self.win = app, win
        self.cfg = load()
        self.sent = {}
        self.tray = None
        self.held = False
        act = Gio.SimpleAction.new("show", None)
        act.connect("activate", lambda *_: self.show())
        app.add_action(act)
        act = Gio.SimpleAction.new("restart", None)
        act.connect("activate", lambda *_: self.win.restart_app())
        app.add_action(act)
        act = Gio.SimpleAction.new("syscheck", None)
        act.connect("activate", lambda *_: (self.show(), win._open_syscheck()))
        app.add_action(act)
        act = Gio.SimpleAction.new("chat", None)
        act.connect("activate", lambda *_: (self.show(), win.stack.set_visible_child_name("chat")
                                            if "chat" in getattr(win, "_lazy", {}) else None))
        app.add_action(act)
        act = Gio.SimpleAction.new("assistant", None)
        act.connect("activate", lambda *_: (self.show(), __import__("assistant_ui").open_dialog(win)))
        app.add_action(act)
        self.apply()
        import automation
        self.auto = automation.Automation(win, self.notify)
        import history
        self.history = history.Recorder()
        import homepcs
        self.sharer = homepcs.Sharer(win)
        # klipp: opptak i bakgrunnen + F8 (av til det slås på)
        try:
            import clips
            clips.setup(self.notify)
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("klipp")
        # spillstatistikk: CS2 live (lytter bare lokalt) og WoW-addonen
        try:
            import gamestats
            gamestats.setup_background()
        except Exception:  # noqa: BLE001
            pass
        # filer som mangler etter oppdatering fra en eldre versjon (f.eks. remote_web) hentes fra NAS-en
        def _repair():
            try:
                import lanupdate
                import tools
                got = lanupdate.repair_missing(tools.PACKAGE_FILES)
                if got:
                    import applog
                    applog.log.info("Hentet manglende programfiler fra NAS-en: %s", ", ".join(got))
            except Exception:  # noqa: BLE001
                pass
        threading.Thread(target=_repair, daemon=True).start()
        def _warm():
            import time as _t
            _t.sleep(45)
            if not __import__("updates").auto_on() or __import__("perf").save_all():   # manuelt / spar alt
                return
            for fn in (lambda: __import__("remote_extra").health(), lambda: __import__("apppanels").all_panels(win)):
                try:
                    fn()
                except Exception:  # noqa: BLE001
                    pass
        threading.Thread(target=_warm, daemon=True, name="varm-opp").start()
        try:                                               # webkamera-overlay i spill + hurtigtasten (hvis på)
            import chatvc
            if chatvc.ov_cfg()["on"]:
                GLib.timeout_add_seconds(8, lambda: (chatvc.ov_sync(), False)[1])
        except Exception:  # noqa: BLE001
            pass

        def _crash_check():                                # stoppet PC-en uten å avslutte sist?
            try:
                import crashlog
                ev = crashlog.check_at_start()
                if ev:
                    import remote_extra
                    txt = crashlog.text(ev)
                    remote_extra.event("crash", "PC-en stoppet uventet", txt, "error")
                    GLib.idle_add(lambda: (self.notify("crash", "PC-en stoppet uventet sist", txt, force=True,
                                                       action="app.assistant"), False)[1])
            except Exception:  # noqa: BLE001
                pass
        threading.Thread(target=_crash_check, daemon=True, name="krasjsjekk").start()
        try:                                               # rommet følger PC-en (dvale → lys av)
            import homeplus
            homeplus.watch_sleep(win)
        except Exception:  # noqa: BLE001
            pass
        try:                                               # smart oppstart (om slått på)
            import gamesplus
            gamesplus.at_start(win)
        except Exception:  # noqa: BLE001
            pass
        if sys.platform == "win32":                       # ytelsesrapport til NAS-en etter 10 min (finne treghet)
            def _perf_report():
                import time as _t
                __import__("perf").usage()                # start målingen av eget forbruk
                _t.sleep(600)
                last = None
                while True:                               # 10 min etter start, så hver time når noe er nytt
                    try:
                        import winperf
                        import applog
                        now = (winperf.STATS["waits"], winperf.STATS["hits"] + winperf.STATS["stale"], winperf.HAKK["n"])
                        if now != last:
                            last = now
                            winperf.report()
                            applog.upload_errors(force=True)
                    except Exception:  # noqa: BLE001
                        pass
                    _t.sleep(3600)
            threading.Thread(target=_perf_report, daemon=True, name="ytelse-rapport").start()
        # fjernstyring fra mobil/nettbrett (av til den slås på i Hjemme-fanen)
        try:
            import remote
            remote.INSTANCE = remote.Remote(win)
            import remote_extra
            remote_extra.event("power", "Kontrollsenter startet", "", "info")
            # chatten trenger tjenesten (meldinger, servere, talekanaler) – også når fjernstyring fra mobilen er av
            chat_on = __import__("funksjoner").on("chat")
            if remote.load_cfg()["enabled"] or chat_on:
                ok, err = remote.INSTANCE.start()
                if not ok:
                    import applog
                    applog.log.warning("Fjernstyring: %s", err)
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("fjernstyring")
        # feilsøkingsrapport til NAS-en (én gang per versjon og døgn) – så feil på andre PC-er kan finnes
        GLib.timeout_add_seconds(120, lambda: (__import__("diagnose").auto_upload(), False)[1])
        win.ov_button.connect("toggled", lambda *_: self.refresh_menu())
        if win.power.proxy:
            win.power.proxy.connect("g-properties-changed", lambda *_: self.refresh_menu())
        GLib.timeout_add_seconds(5, self._tick)
        GLib.timeout_add_seconds(600, self._periodic_first)
        GLib.timeout_add_seconds(90, lambda: self._lan_check() or False)       # rask sjekk etter oppstart

    # --- innstillinger -----------------------------------------------------
    def set(self, key, value):
        self.cfg[key] = value
        save(self.cfg)
        self.apply()

    def apply(self):
        bg = self.cfg["background"]
        if bg and not self.held:
            self.app.hold()
            self.held = True
        elif not bg and self.held:
            self.app.release()
            self.held = False
        if self.cfg["tray"] and not self.tray:
            try:
                import i18n
                if sys.platform == "win32":
                    import winsupport
                    self.tray = winsupport.WinTray("Kontrollsenter", None, self.toggle, self._menu(), tr=i18n.tr)
                else:
                    import tray
                    self.tray = tray.Tray("Kontrollsenter", "no.waagan.Systemmonitor-symbolic", self.toggle,
                                          self._menu(), tr=i18n.tr)
            except Exception:  # noqa: BLE001 – uten statusfelt virker resten som før
                self.tray = None
        elif not self.cfg["tray"] and self.tray:
            self.tray.close()
            self.tray = None

    # --- vindu ---------------------------------------------------------------
    def show(self):
        self.win.set_visible(True)
        self.win.present()

    def toggle(self):
        if self.win.get_visible() and self.win.is_active():
            self.win.set_visible(False)
        else:
            self.show()

    def on_close(self):
        """True = vinduet skjules og programmet kjører videre."""
        import familylock
        if self.cfg["background"] or familylock.locked():
            self.win.set_visible(False)
            if not self.sent.get("_bg_info"):
                self.sent["_bg_info"] = time.time()
                tray = _tray_host()
                self.notify("bg", "Kontrollsenter kjører i bakgrunnen",
                            "Overlay, vifter og varsler fortsetter. " +
                            ("Åpne igjen fra ikonet i statusfeltet, eller velg Avslutt der." if tray else
                             "Åpne igjen ved å starte Kontrollsenter fra menyen (dette skrivebordet har ikke "
                             "statusfelt-ikoner – på GNOME: installer utvidelsen «AppIndicator»)."), force=True)
            return True
        return False

    def request_quit(self):
        """Avslutt fra menyen – med familiekontroll må koden tastes først."""
        import familylock
        if not familylock.locked():
            self.quit()
            return
        self.show()
        familylock.ask(self.win, "Skriv koden for å lukke Kontrollsenter.", self.quit)

    def quit(self):
        try:
            self.history.flush()
        except Exception:  # noqa: BLE001
            pass
        try:
            import clips
            if clips.INSTANCE:
                clips.INSTANCE.stop()
        except Exception:  # noqa: BLE001
            pass
        try:                                              # si fra at PC-en ble slått av med vilje (appen)
            import homepcs
            import remote_extra
            remote_extra.event("power", "Kontrollsenter avsluttet", "", "info")
            if hasattr(self, "play"):
                self.play.save()
            homepcs.publish(self.win, off=True)
            if __import__("funksjoner").on("chat"):          # dual boot: chatten til det andre systemet
                __import__("chat_sync").push()
        except Exception:  # noqa: BLE001
            pass
        if self.held:
            self.app.release()
            self.held = False
        self.win.destroy()
        self.app.quit()

    # --- meny i statusfeltet ---------------------------------------------------
    def _menu(self):
        from cards import MODES
        cur = self.win.power.proxy.get_cached_property("ActiveProfile") if self.win.power.proxy else None
        cur = cur.unpack() if cur else None
        items = [(1, "Vis / skjul Kontrollsenter", self.toggle), (2, "-", None)]
        for i, (key, name, _icon, _d) in enumerate(MODES):
            items.append((10 + i, name, lambda k=key: self._set_mode(k), key == cur))
        items += [(3, "-", None),
                  (4, "Overlay i spill", lambda: self.win.ov_button.set_active(not self.win.ov_button.get_active()),
                   self.win.ov_button.get_active(), "checkmark"),
                  (5, "Systemsjekk …", lambda: (self.show(), self.win._open_syscheck())),
                  (8, "Mini-vindu", lambda: self.win._open_mini()),
                  (6, "-", None), (7, "Avslutt", self.request_quit)]
        return items

    def _set_mode(self, key):
        b = self.win.power.buttons.get(key)
        if b:
            b.set_active(True)

    def refresh_menu(self):
        if self.tray:
            items = self._menu()
            sig = [(i[0], i[1], i[3] if len(i) > 3 else None) for i in items]
            if sig != getattr(self, "_menu_sig", None):
                self._menu_sig = sig
                self.tray.set_items(items)

    # --- varsler ---------------------------------------------------------------
    def notify(self, key, title, body, force=False, action=None, buttons=None, urgent=False):
        try:                                              # alt som varsles havner også i tidslinjen (appen)
            import remote_extra
            if key not in ("bg",) and time.time() - self.sent.get("ev:" + key, 0) > REPEAT:
                self.sent["ev:" + key] = time.time()
                lvl = "game" if key == "session" else "info" if key in ("updates", "playlimit") else "warn"
                remote_extra.event(key, title, body, lvl)
        except Exception:  # noqa: BLE001
            pass
        if not wants(self.cfg, key):
            return
        try:                                              # push til mobilen (ntfy) – også mens du spiller
            import push
            push.publish(key, __import__("i18n").tr(title), __import__("i18n").tr(body))
        except Exception:  # noqa: BLE001
            pass
        # mens du spiller: hold varslene tilbake og vis dem samlet etterpå (ikke chat, spilletid eller personvern)
        meeting = False
        try:
            import gamesplus
            meeting = not getattr(self, "game_name", None) and gamesplus.in_meeting()
        except Exception:  # noqa: BLE001
            pass
        if (self.cfg.get("game_hold", True) and (getattr(self, "game_name", None) or meeting) and key not in ALWAYS
                and kind_of(key) not in ("playtime", "chat") and key not in ("game", "session", "held", "bg", "invite")):
            held = self.__dict__.setdefault("_game_held", [])
            if all(h[0] != key for h in held):
                held.append((key, title, body))
            return
        now = time.time()
        if not force and now - self.sent.get(key, 0) < REPEAT:
            return
        self.sent[key] = now
        import i18n
        if sys.platform == "win32":                     # Windows: varsel fra ikonet i statusfeltet
            if self.tray and hasattr(self.tray, "notify"):
                self.tray.notify(i18n.tr(title), i18n.tr(body))
            return
        n = Gio.Notification.new(i18n.tr(title))
        n.set_body(i18n.tr(body))
        n.set_icon(Gio.ThemedIcon.new("no.waagan.Systemmonitor"))
        n.set_default_action(action or "app.show")
        for label, act, target in buttons or []:            # f.eks. Svar / Legg på / Demp ved anrop
            n.add_button_with_target(i18n.tr(label), act, GLib.Variant("s", str(target)))
        if urgent:
            n.set_priority(Gio.NotificationPriority.URGENT)
        self.app.send_notification(key, n)

    def flush_held(self):
        """Spillet er ferdig: ett varsel med det som skjedde mens du spilte."""
        held = self.__dict__.get("_game_held") or []
        self._game_held = []
        if not held:
            return
        titles = [t for _k, t, _b in held]
        body = "; ".join(titles[:5]) + (f" og {len(titles) - 5} til" if len(titles) > 5 else "")
        self.notify("held", f"Mens du spilte: {len(held)} varsel" + ("" if len(held) == 1 else "er"), body, force=True)

    def _watch_extra(self):
        """Fulladet batteri og temperatur som stiger unormalt raskt (kalles hvert tick)."""
        try:
            import batteries
            seen = self.__dict__.setdefault("_full_seen", set())
            for d in batteries.cached():
                full = d.get("full") or (d.get("plugged") and d.get("pct") is not None and d["pct"] >= 100)
                if full and d["id"] not in seen:
                    seen.add(d["id"])
                    if getattr(self, "_full_ready", False):           # ikke ved oppstart
                        self.notify("full" + d["id"], f"{d['name']} er fulladet",
                                    "Ferdig ladet – du kan ta ut kabelen.")
                elif not (d.get("plugged") or d.get("charging") or full):
                    seen.discard(d["id"])
            self._full_ready = True
        except Exception:  # noqa: BLE001
            pass
        try:
            from collections import deque
            hist = self.__dict__.setdefault("_temp_hist", deque(maxlen=40))
            w = self.win
            nv = w.nvidia.data if w.nvidia.available else None
            now = time.time()
            hist.append((now, w.cpu_temp_now(), w.gpu_temp_now(), getattr(w, "_cpu_load", 0) or 0,
                         (nv or {}).get("util") or 0))
            recent = [h for h in hist if now - h[0] <= 40]
            for idx, util_idx, name, key in ((1, 3, "Prosessoren", "cpu"), (2, 4, "Skjermkortet", "gpu")):
                vals = [h[idx] for h in recent if h[idx] is not None]
                if len(vals) < 4:
                    continue
                rise = vals[-1] - min(vals)
                busy = max(h[util_idx] for h in recent)
                if rise >= 15 and busy < 35 and vals[-1] >= 60:   # varmere uten at noe jobber: vifte? støv?
                    self.notify("temprise-" + key, "Temperaturen stiger raskt",
                                f"{name} gikk fra {min(vals):.0f} til {vals[-1]:.0f} °C på under ett minutt uten "
                                "at noe jobber hardt. Sjekk at viftene går.")
        except Exception:  # noqa: BLE001
            pass

    def _smart_check(self):
        """Diskhelse (SMART) én gang i døgnet – i bakgrunnen."""
        if time.time() - self.sent.get("_smart", 0) < 24 * 3600 or sys.platform == "win32":
            return
        import perf
        import updates
        if not updates.auto_on() or perf.no_disk():          # manuelt: ingen automatisk disksjekk
            return
        self.sent["_smart"] = time.time()

        def work():
            try:
                import tools
                for d in tools.disk_health():
                    rows = dict(d.get("rows") or [])
                    used = 0
                    try:
                        used = int(str(rows.get("Slitasje", "0")).split()[0])
                    except (ValueError, IndexError):
                        pass
                    if d.get("ok") is False or used >= 80:
                        txt = (f"{d['name']}: " + ", ".join(f"{k.lower()} {v}" for k, v in
                                                             list(rows.items())[:3]))
                        GLib.idle_add(lambda t=txt, n=d["name"]: self.notify(
                            "smart" + n, "Disken bør sjekkes", t + ". Ta sikkerhetskopi av det viktigste.") and False)
            except Exception:  # noqa: BLE001
                pass
        import threading
        threading.Thread(target=work, daemon=True).start()

    def _tick(self):
        c = self.cfg
        try:
            import upkeep
            upkeep.monthly_tick(self.notify)
        except Exception:  # noqa: BLE001
            pass
        self._watch_extra()
        self._smart_check()
        if time.time() - getattr(self, "_errup_t", 0) > 1800:        # nye feil → NAS-en (Diagnose)
            self._errup_t = time.time()
            import threading as _th
            _th.Thread(target=lambda: __import__("applog").upload_errors(), daemon=True).start()
        if time.time() - getattr(self, "_plan_t", 0) > 55:            # ukeplanen: sjekk hvert minutt
            self._plan_t = time.time()

            def plan():
                try:
                    import familyplus
                    familyplus.plan_tick(lambda *a, **k: GLib.idle_add(lambda: (self.notify(*a, **k), False)[1]))
                except Exception:  # noqa: BLE001
                    pass
            import threading
            threading.Thread(target=plan, daemon=True).start()
        if time.time() - getattr(self, "_school_t", 0) > 20:           # leksetid
            self._school_t = time.time()
            g = getattr(self, "game_name", None)
            if g:
                import threading as _th

                def school(g=g):
                    try:
                        import familysafe
                        familysafe.school_tick(g, lambda *a, **k: GLib.idle_add(lambda: (self.notify(*a, **k), False)[1]))
                    except Exception:  # noqa: BLE001
                        pass
                _th.Thread(target=school, daemon=True).start()
        import perf
        if time.time() - getattr(self, "_mem_t", 0) > 30:                         # mindre minnebruk
            self._mem_t = time.time()
            perf.mem_tick(self.win)
        if time.time() - getattr(self, "_pulse_t", 0) > 60:                      # livstegn (krasjlogg) + tidsmaskin
            self._pulse_t = time.time()
            import threading as _th

            def _pt():
                try:
                    __import__("crashlog").pulse(self.win)
                    if time.time() - getattr(self, "_tm_t", 0) > 900:
                        self._tm_t = time.time()
                        __import__("timemachine").snapshot()
                except Exception:  # noqa: BLE001
                    pass
            _th.Thread(target=_pt, daemon=True).start()
        if self.__dict__.get("_game_held") and not getattr(self, "game_name", None):   # møtet er over: vis varslene
            try:
                import gamesplus
                if not gamesplus.in_meeting():
                    self.flush_held()
            except Exception:  # noqa: BLE001
                pass
        if time.time() - getattr(self, "_chatl_t", 0) > 60:                      # chat: status, ukesinnlegg …
            self._chatl_t = time.time()
            import threading as _th
            if __import__("funksjoner").on("chat"):
                _th.Thread(target=lambda: __import__("chatlink").tick(self.win), daemon=True).start()
        if time.time() - getattr(self, "_chatp_t", 0) > 60:                      # chat+: påminnelser, planlagte …
            self._chatp_t = time.time()
            import threading as _th
            if __import__("funksjoner").on("chat"):
                _th.Thread(target=lambda: __import__("chatplus").tick(self.win), daemon=True).start()
        if time.time() - getattr(self, "_aiday_t", 0) > 600 and __import__("funksjoner").on("ai"):
            self._aiday_t = time.time()                                          # morgenrapport + hurtigtast
            try:
                import aiextra
                aiextra.daily_tick(self.win, self.notify)
                aiextra.hotkey_setup(self.win)
            except Exception:  # noqa: BLE001
                pass
        if time.time() - getattr(self, "_kallog_t", 0) > 900 and __import__("funksjoner").on("kalender"):
            self._kallog_t = time.time()                                         # hvem er hjemme / når er vennene på
            import threading as _th
            _th.Thread(target=lambda: __import__("kalender_extra").log_tick(), daemon=True).start()
        if time.time() - getattr(self, "_kal_t", 0) > 55 and __import__("funksjoner").on("kalender"):
            self._kal_t = time.time()                                            # kalender: påminnelser og scener
            import threading as _th
            _th.Thread(target=lambda: __import__("kalender").tick(
                lambda *a, **k: GLib.idle_add(lambda: (self.notify(*a, **k), False)[1]), self.win),
                daemon=True).start()
        if time.time() - getattr(self, "_airule_t", 0) > 30 and __import__("funksjoner").on("ai"):
            self._airule_t = time.time()                                         # automatiske oppgaver fra AI-en
            try:
                __import__("ai_rules").tick(self.win, self.notify)
            except Exception:  # noqa: BLE001
                pass
        if __import__("funksjoner").on("chat") and time.time() - getattr(self, "_cbak_t", 0) > 3600:
            self._cbak_t = time.time()                                           # chatten tas vare på (NAS) daglig
            try:
                __import__("chatextra").backup_tick()
            except Exception:  # noqa: BLE001
                pass
        if __import__("funksjoner").on("chat") and time.time() - getattr(self, "_csync_t", time.time() - 3550) > 120:
            first = not getattr(self, "_csync_done", False)                     # dual boot: samme chat i begge
            self._csync_t = time.time()
            self._csync_done = True
            import threading as _th
            _th.Thread(target=lambda f=first: (__import__("chat_sync").pull() if f else None,
                                               __import__("chat_sync").push()), daemon=True).start()
        if time.time() - getattr(self, "_callc_t", 0) > 3600 and __import__("funksjoner").on("chat"):
            self._callc_t = time.time()                                          # gamle samtaler uten server
            import threading as _th
            _th.Thread(target=lambda: __import__("chatcall").cleanup(), daemon=True).start()
        if time.time() - getattr(self, "_chatq_t", 0) > 60:                      # chat: send det som ligger i kø
            self._chatq_t = time.time()
            import threading as _th
            if __import__("funksjoner").on("chat"):
                _th.Thread(target=lambda: __import__("chat").retry_outbox(), daemon=True).start()
        if time.time() - getattr(self, "_eq_t", 0) > 15:                         # utstyr+: hodesett, kontrollere …
            self._eq_t = time.time()
            import threading as _th
            _th.Thread(target=lambda: __import__("equipment").tick(self.win), daemon=True).start()
        if time.time() - getattr(self, "_hp_t", 0) > 60:                         # hjem+: nettverksvakt, fartstest
            self._hp_t = time.time()
            import threading as _th
            _th.Thread(target=lambda: __import__("homeplus").tick(self.win), daemon=True).start()
        if time.time() - getattr(self, "_gp_t", 0) > 30:                         # spill+: ping-vakt, spillkveld …
            self._gp_t = time.time()
            import threading as _th
            if __import__("funksjoner").on("spill"):
                _th.Thread(target=lambda: __import__("gamesplus").tick(self.win), daemon=True).start()
        if time.time() - getattr(self, "_fam_t", 0) > 50:                        # familie+: leggetid, kø, pause …
            self._fam_t = time.time()
            import threading as _th
            if __import__("funksjoner").on("familie"):
                _th.Thread(target=lambda: __import__("familyfun").tick(self.win), daemon=True).start()
        if time.time() - getattr(self, "_house_t", 0) > 55:                      # huset: kveld, pris, glemte, sov
            self._house_t = time.time()
            import threading as _th
            if __import__("funksjoner").on("pcer"):
                _th.Thread(target=lambda: __import__("house").tick(self.win), daemon=True).start()
        if time.time() - getattr(self, "_assist_t", 0) > 60:                     # PC-assistenten lærer og varsler
            self._assist_t = time.time()
            import threading as _th
            _th.Thread(target=lambda: __import__("assistant").tick(self.win), daemon=True).start()
        lite = perf.save_all()                           # «Spar alt»: hopp over det som ikke er nødvendig
        if not lite and time.time() - getattr(self, "_ach_t", time.time() - 240) > (1800 if perf.eco() else 300):
            self._ach_t = time.time()
            import threading as _th

            def ach():
                try:
                    import today
                    today.check(lambda *a, **k: GLib.idle_add(lambda: (self.notify(*a, **k, force=True), False)[1]))
                except Exception:  # noqa: BLE001
                    pass
            _th.Thread(target=ach, daemon=True).start()
        if sys.platform != "win32" and time.time() - getattr(self, "_af_t", 0) > (15 if lite else 4):  # volumtastene
            self._af_t = time.time()
            import threading as _th
            _th.Thread(target=lambda: __import__("audiofollow").tick(), daemon=True).start()
        if time.time() - getattr(self, "_h5_t", 0) > 60:     # hjemmet: TV av ved leggetid (hvert min), søvnlogg
            self._h5_t = time.time()
            import threading as _th

            def h5():
                import hjem5
                hjem5.tv_tick()
                if time.time() - getattr(self, "_h5s_t", 0) > 600:
                    self._h5s_t = time.time()
                    hjem5.tick()
            _th.Thread(target=h5, daemon=True).start()
        if time.time() - getattr(self, "_pcp_t", time.time() - 540) > 600:   # støvlogg, strømbudsjett (hvert 10. min)
            self._pcp_t = time.time()
            import threading as _th
            _nf = lambda *a, **k: GLib.idle_add(lambda: (self.notify(*a, **k), False)[1])  # noqa: E731
            _th.Thread(target=lambda: __import__("pcplus").tick(_nf), daemon=True).start()
            _th.Thread(target=lambda: __import__("ai6").tick(getattr(self, "win", None), _nf), daemon=True).start()
            if not getattr(self, "_crash_ai_done", False):        # krasj siden sist: tilby AI-hjelp (én gang)
                self._crash_ai_done = True
                _th.Thread(target=lambda: __import__("ai6").crash_check(_nf), daemon=True).start()
        if sys.platform != "win32" and time.time() - getattr(self, "_lf_t", 0) > 60:  # lydfiltrene (7.1, EQ, støy)
            self._lf_t = time.time()
            import threading as _th
            if __import__("funksjoner").on("lyd"):
                _th.Thread(target=lambda: __import__("lydfilter").tick(), daemon=True).start()
        if not lite and time.time() - getattr(self, "_vr_t", 0) > 20:  # VR-vakten: hold VR i gang
            self._vr_t = time.time()
            import threading as _th

            def vrw():
                try:
                    import vr
                    vr.watch_tick(lambda *a, **k: GLib.idle_add(lambda: (self.notify(*a, **k), False)[1]))
                except Exception:  # noqa: BLE001
                    pass
            if __import__("funksjoner").on("vr"):
                _th.Thread(target=vrw, daemon=True).start()
        for mod in (() if lite else ("presence", "pricejobs")):
            try:
                m = __import__(mod)
                m.tick(self.win, self.notify) if mod == "pricejobs" else m.tick(self.win)
            except Exception:  # noqa: BLE001
                pass
        try:                                              # spilletid per dag (grenser og oversikt)
            now = time.monotonic()
            dt = min(30.0, now - getattr(self, "_play_t", now))
            self._play_t = now
            if not hasattr(self, "play"):
                import remote_extra
                self.play = remote_extra.PlayTracker(self.notify)
            game = getattr(self, "game_name", None)
            if not game:                                  # YouTube/Twitch i nettleseren teller som skjermtid
                try:
                    import features
                    if features.cfg().get("count_video", True):
                        import mediawatch
                        game = mediawatch.playing_video()
                except Exception:  # noqa: BLE001
                    pass
            self.play.tick(game, dt)
        except Exception:  # noqa: BLE001
            pass
        try:
            import clips
            if clips.INSTANCE:
                clips.INSTANCE.tick(getattr(self, "game_name", None))
        except Exception:  # noqa: BLE001
            pass
        try:                                              # familie, leggetid, oppdatering, hjemmenett, tilbud …
            import features
            features.tick(self.notify, self.win)
        except Exception:  # noqa: BLE001
            pass
        try:
            w = self.win
            nv = w.nvidia.data if w.nvidia.available else None
            self.history.add(getattr(w, "_cpu_t", None), nv.get("temp") if nv else None,
                             getattr(w, "_cpu_load", None), nv.get("util") if nv else None,
                             (getattr(w, "_power", None) or {}).get("total"))
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("historikk")
        try:
            self.sharer.tick()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.auto.tick()
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("automatikk")
        try:
            t = self.win.cpu_temp_now()
            if t is not None and t >= c["cpu_limit"]:
                self.notify("cpu", "Prosessoren er varm", f"CPU-temperaturen er {t:.0f} °C "
                            f"(grense {c['cpu_limit']} °C). Sjekk viftene eller bytt til Balansert.")
            g = self.win.gpu_temp_now()
            if g is not None and g >= c["gpu_limit"]:
                self.notify("gpu", "Skjermkortet er varmt", f"GPU-temperaturen er {g:.0f} °C "
                            f"(grense {c['gpu_limit']} °C).")
            if self.tray:
                parts = []
                if t is not None:
                    parts.append(f"CPU {t:.0f} °C")
                if g is not None:
                    parts.append(f"GPU {g:.0f} °C")
                self.tray.set_tooltip(" · ".join(parts))
            now = time.time()
            if now - self.sent.get("_slow", 0) > 60:            # disk og batteri: hvert minutt
                self.sent["_slow"] = now
                from cards import list_filesystems, nice_mount
                for d in list_filesystems():
                    if d["total"] < 10 * 1024 ** 3:             # små partisjoner (EFI, /boot) hoppes over
                        continue
                    pct = 100 * (d["total"] - d["free"]) / d["total"]
                    if pct >= c["disk_limit"]:
                        self.notify("disk" + d["dev"], "Disken er nesten full",
                                    f"{nice_mount(d['mnt'])} er {pct:.0f} % full. "
                                    "Vedlikehold → Rydd opp kan frigjøre plass.")
                try:
                    import bluetooth
                    objs = bluetooth.objects()
                    n = sum(1 for _p, ifs in objs.items()
                            if ifs.get("org.bluez.Device1", {}).get("Connected"))
                    self.win.set_badge("bluetooth", str(n) if n else "")
                except Exception:  # noqa: BLE001
                    pass
                try:
                    import batteries
                    devs = [(d["id"], d["name"], d["pct"]) for d in batteries.cached()
                            if d.get("pct") is not None and not d.get("charging")]
                except Exception:  # noqa: BLE001
                    devs = device_batteries()
                for path, name, pct in devs:
                    if pct <= c["battery_limit"]:
                        self.notify("bat" + path, f"Lavt batteri: {name}", f"{pct:.0f} % igjen – lad snart.")
                self.refresh_menu()
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("bakgrunn")
        return True

    def _lan_check(self):
        """Ny versjon på hjemmenettet (NAS)? Bare når PC-en er på det lokale nettet."""

        def work():
            new = None
            try:
                import lanupdate
                import tools
                pub = lanupdate.auto_publish(tools.make_package)      # bare på utviklings-PC-en
                if pub:
                    GLib.idle_add(lambda: self.notify(
                        "lanpublish", "Ny versjon lagt på hjemmenettet",
                        f"Kontrollsenter {pub} ligger nå på NAS-en, og de andre PC-ene får varsel.") and False)
                elif __import__("updates").auto_on():
                    _txt, new = lanupdate.check()
            except Exception:  # noqa: BLE001
                new = None
            if new:
                GLib.idle_add(lambda: self.notify(
                    "lanupdate", "Ny versjon av Kontrollsenter",
                    f"Versjon {new} ligger på hjemmenettet. Innstillinger → Oppdatering → Se etter oppdatering.",
                    action="app.show") and False)
        threading.Thread(target=work, daemon=True).start()

    def _periodic_first(self):
        self._periodic()
        GLib.timeout_add_seconds(PERIODIC, self._periodic)
        return False

    def _periodic(self):
        if not (self.cfg["periodic"] and self.cfg["notify"]):
            return True
        self._lan_check()
        import updates
        if not updates.auto_on():                  # manuelt: ingen automatiske sjekker av disk og oppdateringer
            return True

        def work():
            found, upd = 0, 0
            try:
                import syscheck
                found = len([r for r in syscheck.run_all() if r.level in ("warn", "error")])
            except Exception:  # noqa: BLE001
                pass
            ksv = None
            try:
                st = updates.status(refresh=True, only=("apps", "ks"))
                upd = sum(max(0, s["count"]) for s in st)
                ksv = next((v for s in st if s["key"] == "ks" for k, v in s.get("items") or [] if k == "ks"), None)
            except Exception:  # noqa: BLE001
                upd = 0
            GLib.idle_add(done, found, upd, ksv)

        def done(found, upd, ksv=None):
            if found:
                self.notify("syscheck", "Systemsjekk fant noe",
                            f"{found} ting bør sjekkes. Klikk for å åpne Systemsjekk.", action="app.syscheck")
            if upd:
                self.notify("updates", "Oppdateringer tilgjengelig",
                            (f"Kontrollsenter {ksv} er klar. " if ksv else "") +
                            f"{upd} oppdateringer er klare. Trykk «Oppdater alt» på Oversikt.", action="app.show")
            return False

        threading.Thread(target=work, daemon=True).start()
        return True
