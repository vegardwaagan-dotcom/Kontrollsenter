"""Automatikk: spillprofiler og stille om natten.

Begge bytter strømmodus, vifter og RGB midlertidig – og setter alt tilbake slik det var etterpå.
Spill har forrang foran natt: starter du et spill om natten, gjelder spillprofilen til spillet slutter.
"""
import json
import os
import sys
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk  # noqa: E402

import i18n  # noqa: E402

CFG_DIR = os.path.expanduser("~/.config/systemmonitor")
NIGHT_CFG = os.path.join(CFG_DIR, "natt.json")
GAME_CFG = os.path.join(CFG_DIR, "spillprofiler.json")
NIGHT_DEFAULT = {"enabled": False, "start": "23:00", "end": "07:00", "power": "power-saver", "fans": "35",
                 "rgb": "off"}
GAME_DEFAULT = {"enabled": False, "power": "performance", "fans": "70", "rgb": "keep", "color": "#ff0000",
                "games": {}}
POWER_CHOICES = [("keep", "Uendret"), ("power-saver", "Strømsparing"), ("balanced", "Balansert"),
                 ("performance", "Max Ytelse")]
FAN_CHOICES = [("keep", "Uendret"), ("auto", "Auto"), ("35", "Stille (35 %)"), ("70", "Kraftig (70 %)"),
               ("100", "Max"), ("curve", "Viftekurve")]
RGB_CHOICES_NIGHT = [("keep", "Uendret"), ("off", "Av")]
RGB_CHOICES_GAME = [("keep", "Uendret"), ("off", "Av"), ("color", "Egen farge")]


def _load(path, default):
    try:
        with open(path) as f:
            return {**json.loads(json.dumps(default)), **json.load(f)}
    except (OSError, ValueError):
        return json.loads(json.dumps(default))


def _save(path, data):
    os.makedirs(CFG_DIR, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, path)


def load_night():
    return _load(NIGHT_CFG, NIGHT_DEFAULT)


def save_night(c):
    _save(NIGHT_CFG, c)


def load_games():
    return _load(GAME_CFG, GAME_DEFAULT)


def save_games(c):
    _save(GAME_CFG, c)


# --------------------------------------------------------------------------
# RGB via OpenRGB (RAM, skjermkort, hovedkort/vifter)
# --------------------------------------------------------------------------
def _rgb_client():
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
    from openrgb import OpenRGBClient  # noqa: E402
    return OpenRGBClient("127.0.0.1", 6742, "Kontrollsenter-auto")


def rgb_set(color, _from_sync=False):
    """color = (r, g, b), eller None for «av». Kjøres i bakgrunnen; stille hvis OpenRGB ikke svarer."""
    if not _from_sync:
        try:
            import smartauto
            smartauto.rgb_changed(color)              # synk RGB og Hue (hvis slått på)
        except Exception:  # noqa: BLE001
            pass
    def work():
        try:
            from openrgb.utils import RGBColor
            c = _rgb_client()
            col = RGBColor(*(color or (0, 0, 0)))
            for dev in c.devices:
                try:
                    modes = {m.name.lower(): m for m in dev.modes}
                    for name in ("direct", "static", "custom"):
                        if name in modes:
                            dev.set_mode(modes[name])
                            break
                    dev.set_color(col)
                except Exception:  # noqa: BLE001
                    continue
            c.disconnect()
        except Exception:  # noqa: BLE001
            pass
    threading.Thread(target=work, daemon=True).start()


def rgb_restore():
    """Legg inn RGB-profilen fra RGB-fanen igjen."""
    def work():
        try:
            import rgb
            c = _rgb_client()
            c.load_profile(rgb.PROFILE)
            c.disconnect()
        except Exception:  # noqa: BLE001
            pass
    threading.Thread(target=work, daemon=True).start()


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# --------------------------------------------------------------------------
# Lagre og bytte tilstand
# --------------------------------------------------------------------------
def snapshot(win):
    fans = getattr(win, "fans", None)
    return {"power": win.power.active_profile() if getattr(win, "power", None) else None,
            "fans": {k: r.value() for k, r in fans.rows.items()} if fans else {},
            "curve": bool(fans and fans.curve_on)}


def apply(win, power="keep", fans="keep", rgb="keep", color=None):
    if power not in (None, "keep") and getattr(win, "power", None) and power in win.power.buttons:
        win.power.buttons[power].set_active(True)
    fc = getattr(win, "fans", None)
    if fc and fc.ready() and fans not in (None, "keep"):
        if fans == "curve":
            fc.set_curve(True)
        else:
            fc.apply_all("auto" if fans == "auto" else int(fans))
    if rgb == "off":
        rgb_set(None)
    elif rgb == "color" and color:
        rgb_set(hex_rgb(color))


def restore(win, snap, rgb_changed):
    if snap.get("power") and getattr(win, "power", None) and snap["power"] in win.power.buttons:
        win.power.buttons[snap["power"]].set_active(True)
    fc = getattr(win, "fans", None)
    if fc and fc.ready():
        if snap.get("curve"):
            fc.set_curve(True)
        else:
            if fc.curve_on:
                fc.set_curve(False, apply_auto=False)
            for k, v in snap.get("fans", {}).items():
                if k in fc.rows:
                    fc.rows[k].set_value(v, send=True)
    if rgb_changed:
        rgb_restore()


# --------------------------------------------------------------------------
# Stille om natten
# --------------------------------------------------------------------------
def _minutes(hhmm):
    h, m = (int(x) for x in hhmm.split(":"))
    return h * 60 + m


def in_night(cfg, now=None):
    t = time.localtime(now or time.time())
    cur = t.tm_hour * 60 + t.tm_min
    a, b = _minutes(cfg["start"]), _minutes(cfg["end"])
    return (a <= cur < b) if a < b else (cur >= a or cur < b)


class Automation:
    """Kalles fra bakgrunnsløkka hvert 5. sekund."""

    def __init__(self, win, notify):
        self.win, self.notify = win, notify
        self.night_snap = None          # tilstand før natt
        self.game_snap = None           # tilstand før spill
        self.game = None                # (appid, navn)
        self.session = None
        self._last_night_check = 0

    # --- natt ---------------------------------------------------------------
    def check_night(self):
        cfg = load_night()
        quiet = (cfg.get("quiet_until") or 0) > time.time()        # «Stille nå» i X timer
        active = (cfg["enabled"] and in_night(cfg)) or quiet
        if self.game:                                  # spill har forrang
            return
        if active and self.night_snap is None:
            self.night_snap = snapshot(self.win)
            apply(self.win, cfg["power"], cfg["fans"], cfg["rgb"])
            self.night_snap["rgb"] = cfg["rgb"] not in ("keep", None)
            until = time.strftime("%H:%M", time.localtime(cfg["quiet_until"])) if quiet else cfg["end"]
            self.notify("night", "Stille-modus" if quiet else "Stille om natten",
                        f"Til {until}: rolige vifter og lavere strømforbruk.")
        elif not active and self.night_snap is not None:
            restore(self.win, self.night_snap, self.night_snap.get("rgb"))
            self.night_snap = None

    def tick(self):
        try:
            import games_auto
            games_auto.tick(self)
        except ImportError:
            pass
        now = time.time()
        if now - self._last_night_check >= 30:
            self._last_night_check = now
            self.check_night()
        if now - getattr(self, "_last_scene_check", 0) >= 5:       # scener med klokkeslett
            self._last_scene_check = now
            try:
                import scenes
                scenes.tick(self.win)
            except Exception:  # noqa: BLE001
                import applog
                applog.log.exception("scener")


# --------------------------------------------------------------------------
# Siden «Automatikk»
# --------------------------------------------------------------------------
def card(title, subtitle=None, icon=None):
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    outer.add_css_class("card")
    inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    for side, v in (("top", 14), ("bottom", 14), ("start", 16), ("end", 16)):
        getattr(inner, f"set_margin_{side}")(v)
    outer.append(inner)
    head = Gtk.Box(spacing=8)
    if icon:
        img = Gtk.Image(icon_name=icon)
        img.add_css_class("tile-icon")
        head.append(img)
    t = Gtk.Label(label=title, xalign=0, hexpand=True)
    t.add_css_class("heading")
    head.append(t)
    inner.append(head)
    if subtitle:
        s = Gtk.Label(label=subtitle, xalign=0, wrap=True)
        s.add_css_class("caption")
        s.add_css_class("dim-label")
        inner.append(s)
    return outer, inner, head


def dropdown(choices, current, on_change):
    dd = Gtk.DropDown.new_from_strings([i18n.tr(c[1]) for c in choices])
    keys = [c[0] for c in choices]
    dd.set_selected(keys.index(current) if current in keys else 0)
    dd.connect("notify::selected", lambda d, _p: on_change(keys[d.get_selected()]))
    return dd


def row(label, widget):
    r = Gtk.Box(spacing=12)
    lab = Gtk.Label(label=i18n.tr(label), xalign=0, hexpand=True)
    r.append(lab)
    widget.set_valign(Gtk.Align.CENTER)
    r.append(widget)
    return r


class AutomationPage(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(12)
        self.box = box
        self.set_child(box)
        try:
            import games_auto
            games_auto.build_cards(self)
        except ImportError:
            pass
        self._night_card()

    def _night_card(self):
        cfg = load_night()
        c, i, head = card("Stille om natten",
                          "I tidsrommet du velger blir PC-en roligere: lavere strømforbruk, stille vifter og RGB av. "
                          "Alt settes tilbake om morgenen. Spillprofiler går foran mens du spiller.", "ks-night-symbolic")
        sw = Gtk.Switch(active=cfg["enabled"], valign=Gtk.Align.CENTER)
        head.append(sw)

        def set_(k, v):
            c2 = load_night()
            c2[k] = v
            save_night(c2)
        sw.connect("notify::active", lambda w, _p: set_("enabled", w.get_active()))
        times = Gtk.Box(spacing=8)
        for key, lbl in (("start", "Fra"), ("end", "Til")):
            times.append(Gtk.Label(label=i18n.tr(lbl)))
            h, m = cfg[key].split(":")
            sh = Gtk.SpinButton.new_with_range(0, 23, 1)
            sh.set_value(int(h))
            sm = Gtk.SpinButton.new_with_range(0, 59, 5)
            sm.set_value(int(m))
            for sp in (sh, sm):                      # alltid to siffer: 07:00, 23:05
                sp.connect("output", lambda w: (w.set_text(f"{int(w.get_value()):02d}"), True)[1])

            def upd(_w, k=key, a=sh, b=sm):
                set_(k, f"{int(a.get_value()):02d}:{int(b.get_value()):02d}")
            sh.connect("value-changed", upd)
            sm.connect("value-changed", upd)
            times.append(sh)
            times.append(Gtk.Label(label=":"))
            times.append(sm)
        i.append(row("Tidsrom", times))
        i.append(row("Strømmodus", dropdown(POWER_CHOICES, cfg["power"], lambda v: set_("power", v))))
        i.append(row("Vifter", dropdown(FAN_CHOICES, cfg["fans"], lambda v: set_("fans", v))))
        i.append(row("RGB-lys", dropdown(RGB_CHOICES_NIGHT, cfg["rgb"], lambda v: set_("rgb", v))))
        note = Gtk.Label(label=i18n.tr("RGB gjelder lys styrt av OpenRGB (RAM, skjermkort og hovedkort). "
                                       "Krever at Kontrollsenter kjører (gjerne i bakgrunnen)."), xalign=0, wrap=True)
        note.add_css_class("caption")
        note.add_css_class("dim-label")
        i.append(note)
        try:                                               # «Stille nå» i X timer
            import pcplus_ui
            i.append(Gtk.Separator())
            i.append(pcplus_ui.quiet_row())
        except Exception:  # noqa: BLE001
            pass
        self.box.append(c)


def night_card(page):
    """«Stille om natten»-kortet i en annen side (Innstillinger → Automatikk). Skriver til page.box."""
    AutomationPage._night_card(page)
