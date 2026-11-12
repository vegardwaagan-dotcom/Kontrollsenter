"""Bakgrunnsmodus, varsler og ikon i systemstatusfeltet.

- Når «Kjør i bakgrunnen» er på, skjules vinduet i stedet for å avslutte når det lukkes.
- Varsler: høy CPU-/GPU-temperatur, nesten full disk, lavt batteri i trådløse enheter,
  funn i Systemsjekk og tilgjengelige oppdateringer (sjekkes hver 6. time).
"""
import json
import os
import shutil
import subprocess
import threading
import time

from gi.repository import Gio, GLib

CFG = os.path.expanduser("~/.config/systemmonitor/bakgrunn.json")
DEFAULTS = {"background": True, "tray": True, "notify": True, "cpu_limit": 90, "gpu_limit": 85,
            "disk_limit": 90, "battery_limit": 15, "periodic": True}
REPEAT = 30 * 60           # samme varsel tidligst igjen etter 30 min
PERIODIC = 6 * 3600


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
                import tray
                import i18n
                self.tray = tray.Tray("Kontrollsenter", "utilities-system-monitor", self.toggle,
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
        if self.cfg["background"]:
            self.win.set_visible(False)
            if not self.sent.get("_bg_info"):
                self.sent["_bg_info"] = time.time()
                self.notify("bg", "Kontrollsenter kjører i bakgrunnen",
                            "Overlay, vifter og varsler fortsetter. Åpne igjen fra ikonet i statusfeltet, "
                            "eller velg Avslutt der.", force=True)
            return True
        return False

    def quit(self):
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
                  (6, "-", None), (7, "Avslutt", self.quit)]
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
        if not force and not self.cfg["notify"]:
            return
        now = time.time()
        if not force and now - self.sent.get(key, 0) < REPEAT:
            return
        self.sent[key] = now
        import i18n
        n = Gio.Notification.new(i18n.tr(title))
        n.set_body(i18n.tr(body))
        n.set_icon(Gio.ThemedIcon.new("utilities-system-monitor"))
        n.set_default_action(action or "app.show")
        self.app.send_notification(key, n)

    def _tick(self):
        c = self.cfg
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
                                    "Verktøy → Rydd opp kan frigjøre plass.")
                for path, name, pct in device_batteries():
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
                    f"Versjon {new} ligger på hjemmenettet. Verktøy → Se etter oppdatering → Oppdater nå.",
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
