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
    ("updates", "Oppdateringer", "Nye programoppdateringer og nye versjoner av Kontrollsenter.",
     ["updates", "lanupdate", "lanpublish", "restart"]),
    ("chat", "Familie-chat og «Middag!»", "Meldinger fra de andre i huset.", ["chat"]),
    ("game", "Spillprofil", "Når spillmodus slås på automatisk fordi et spill startet.", ["game"]),
    ("session", "Rapport etter spilløkt", "FPS, temperaturer og strøm når du er ferdig med et spill.", ["session"]),
    ("clip", "Klipp lagret", "Når et klipp av de siste minuttene er lagret.", ["clip"]),
    ("night", "Stille om natten", "Når PC-en går over til stille nattmodus.", ["night"]),
    ("playtime", "Spilletid og leggetid", "Snart tom for spilletid, og leggetid om 10 minutter. "
     "Kan ikke slås av mens familiekontroll er på.", ["playlimit", "bedtime"]),
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
        # fjernstyring fra mobil/nettbrett (av til den slås på i Hjemme-fanen)
        try:
            import remote
            remote.INSTANCE = remote.Remote(win)
            import remote_extra
            remote_extra.event("power", "Kontrollsenter startet", "", "info")
            if remote.load_cfg()["enabled"]:
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
                self.notify("bg", "Kontrollsenter kjører i bakgrunnen",
                            "Overlay, vifter og varsler fortsetter. Åpne igjen fra ikonet i statusfeltet, "
                            "eller velg Avslutt der.", force=True)
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
    def notify(self, key, title, body, force=False, action=None):
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
        self.app.send_notification(key, n)

    def _tick(self):
        c = self.cfg
        try:                                              # spilletid per dag (grenser og oversikt)
            now = time.monotonic()
            dt = min(30.0, now - getattr(self, "_play_t", now))
            self._play_t = now
            if not hasattr(self, "play"):
                import remote_extra
                self.play = remote_extra.PlayTracker(self.notify)
            self.play.tick(getattr(self, "game_name", None), dt)
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
                else:
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

        def work():
            found, upd = 0, 0
            try:
                import syscheck
                found = len([r for r in syscheck.run_all() if r.level in ("warn", "error")])
            except Exception:  # noqa: BLE001
                pass
            upd = flatpak_updates()
            GLib.idle_add(done, found, upd)

        def done(found, upd):
            if found:
                self.notify("syscheck", "Systemsjekk fant noe",
                            f"{found} ting bør sjekkes. Klikk for å åpne Systemsjekk.", action="app.syscheck")
            if upd:
                self.notify("updates", "Oppdateringer tilgjengelig",
                            f"{upd} Flatpak-programmer kan oppdateres.")
            return False

        threading.Thread(target=work, daemon=True).start()
        return True
