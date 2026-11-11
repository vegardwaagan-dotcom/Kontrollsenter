"""RGB-fanen i Systemmonitor – styrer all RGB via OpenRGB (SDK-server på localhost).

All kommunikasjon med OpenRGB skjer i én bakgrunnstråd, så vinduet aldri fryser.
"""
import json
import os
import queue
import subprocess
import sys
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
try:
    from openrgb import OpenRGBClient  # noqa: E402
    from openrgb.utils import DeviceType, ModeColors, ModeFlags, RGBColor  # noqa: E402
except ImportError:  # biblioteket mangler
    OpenRGBClient = None

STATE_FILE = os.path.expanduser("~/.config/systemmonitor/rgb.json")
AUTOSTART = os.path.expanduser("~/.config/autostart/systemmonitor-openrgb.desktop")
PROFILE = "Systemmonitor"
OPENRGB_CMD = ["flatpak", "run", "org.openrgb.OpenRGB"]

# Felles effekter -> OpenRGB-moduser som prøves i rekkefølge for hver enhet
EFFECTS = [
    # nøkkel, navn, kandidater, bruker farge
    ("static", "Statisk", ["Static", "Direct"], True),
    ("breathing", "Pust", ["Breathing", "Color Pulse"], True),
    ("flashing", "Blink", ["Flashing"], True),
    ("cycle", "Fargesyklus", ["Spectrum Cycle", "Cycle", "Rainbow", "Color Shift"], False),
    ("rainbow", "Regnbue", ["Rainbow Wave", "Rainbow", "Spectrum Cycle Wave", "Spectrum Cycle", "Cycle"], False),
    ("off", "Av", ["Off"], False),
]
EFFECT = {e[0]: e for e in EFFECTS}

SWATCHES = [
    ("Rød", (255, 0, 0)), ("Oransje", (255, 100, 0)), ("Gul", (255, 200, 0)),
    ("Grønn", (0, 255, 0)), ("Turkis", (0, 255, 200)), ("Blå", (0, 60, 255)),
    ("Lilla", (140, 0, 255)), ("Rosa", (255, 0, 140)), ("Hvit", (255, 255, 255)),
]

GROUPS = [
    # nøkkel, tittel, ikon, enhetstyper
    ("keyboard", "Tastatur", "input-keyboard-symbolic", ("KEYBOARD",)),
    ("mouse", "Mus", "input-mouse-symbolic", ("MOUSE", "MOUSEMAT")),
    ("ram", "RAM", "media-flash-symbolic", ("DRAM",)),
    ("gpu", "Skjermkort", "video-display-symbolic", ("GPU",)),
    ("motherboard", "Hovedkort og vifter", "computer-symbolic", ("MOTHERBOARD",)),
    ("cooling", "Kjøling og vifter", "weather-windy-symbolic", ("COOLER", "LEDSTRIP", "LIGHT")),
    ("other", "Andre enheter", "applications-graphics-symbolic", None),
]
DEFAULT = {"effect": "static", "color": [0, 60, 255], "brightness": 100, "speed": 50}


# --------------------------------------------------------------------------
# Logitech mus/tastatur: styres via ratbagd og lagres i enhetens innebygde
# profil (OpenRGB setter dem i programvaremodus, som overstyres av Solaar/profiler).
# --------------------------------------------------------------------------
class _LogiMode:
    def __init__(self, name, speed):
        self.name = name
        self.flags = ModeFlags.HAS_SPEED if speed else ModeFlags(0)


class LogiDevice:
    """Ser ut som en OpenRGB-enhet for GroupCard, men er en ratbagd-enhet."""

    def __init__(self, path, name, kind):
        self.id = path
        self.name = name.replace("Logitech ", "")
        self.kind = kind
        self.type = type("T", (), {"name": kind})()
        self.modes = [_LogiMode("Static", False), _LogiMode("Breathing", True),
                      _LogiMode("Spectrum Cycle", True), _LogiMode("Off", False)]


def logitech_devices():
    try:
        import logitech as L
        out = []
        for dev in L.ratbag_devices():
            name = L.getp(dev, "Name")
            kind = "KEYBOARD" if "keyboard" in name.lower() else "MOUSE"
            out.append(LogiDevice(dev.get_object_path(), name, kind))
        return out
    except Exception:  # noqa: BLE001
        return []


# ratbag LED-moduser: 0 av, 1 fast farge, 2 fargesyklus, 3 pust
RATBAG_MODE = {"static": 1, "breathing": 3, "flashing": 3, "cycle": 2, "rainbow": 2, "off": 0}


# --------------------------------------------------------------------------
# Bakgrunnsmotor
# --------------------------------------------------------------------------
class RgbBackend:
    def __init__(self, on_status, on_ready):
        self.on_status, self.on_ready = on_status, on_ready
        self.client = None
        self.q = queue.Queue()
        self._save_timer = None
        threading.Thread(target=self._worker, daemon=True).start()
        self.q.put(("connect",))

    # --- trådsikker inngang -------------------------------------------------
    def do(self, *job):
        self.q.put(job)

    def _status(self, text, busy=False):
        GLib.idle_add(self.on_status, text, busy)

    def _worker(self):
        while True:
            job = self.q.get()
            # slå sammen gjentatte jobber for samme mål (f.eks. glidebryter)
            if job[0] in ("apply", "zone"):
                pending = []
                while not self.q.empty():
                    nxt = self.q.get()
                    if nxt[:2] == job[:2]:
                        job = nxt
                    else:
                        pending.append(nxt)
                for p in pending:
                    self.q.put(p)
            try:
                logi = job[0] == "logi_commit" or (job[0] == "apply" and job[2]
                                                   and isinstance(job[2][0], str))
                if job[0] != "connect" and not logi and not self.client and not self._reconnect():
                    continue
                getattr(self, "_" + job[0])(*job[1:])
            except Exception as e:  # noqa: BLE001 – vis feilen, ikke krasj
                if job[0] == "connect":
                    self._status(f"Feil: {e}")
                    continue
                # Forbindelsen hikket: koble til på nytt og prøv én gang til
                self._status("Mistet kontakt med OpenRGB – kobler til igjen …", True)
                if self._reconnect():
                    try:
                        getattr(self, "_" + job[0])(*job[1:])
                        continue
                    except Exception as e2:  # noqa: BLE001
                        e = e2
                self._status(f"Feil: {str(e) or type(e).__name__} – trykk «Bruk» for å prøve igjen")

    def _reconnect(self):
        """Ny forbindelse til OpenRGB (starter tjenesten om den ikke kjører)."""
        try:
            if self.client:
                self.client.disconnect()
        except Exception:  # noqa: BLE001
            pass
        self.client = None
        for attempt in range(3):
            try:
                self.client = OpenRGBClient("127.0.0.1", 6742, "Systemmonitor")
                self._status("Tilkoblet OpenRGB igjen")
                return True
            except Exception:  # noqa: BLE001
                time.sleep(1)
        self._connect()            # tjenesten kjører ikke: start den
        return self.client is not None

    # --- tilkobling --------------------------------------------------------
    def _connect(self):
        if OpenRGBClient is None:
            self._status("Biblioteket openrgb-python mangler (vendor-mappen).")
            return
        self._status("Kobler til OpenRGB …", True)
        try:
            self.client = OpenRGBClient("127.0.0.1", 6742, "Systemmonitor")
        except OSError:
            self._status("Starter OpenRGB i bakgrunnen … (kan ta 10–30 sek)", True)
            try:
                subprocess.Popen(OPENRGB_CMD + ["--server", "--noautoconnect"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
            except OSError as e:
                self._status(f"Klarte ikke å starte OpenRGB: {e}")
                return
            for _ in range(90):
                time.sleep(1)
                try:
                    self.client = OpenRGBClient("127.0.0.1", 6742, "Systemmonitor")
                    time.sleep(2)            # la enhetsdeteksjonen bli ferdig
                    self.client.update()
                    break
                except OSError:
                    continue
        if not self.client:
            self._status("Fikk ikke kontakt med OpenRGB.")
            return
        devices = list(self.client.devices)
        GLib.idle_add(self.on_ready, devices)

    # --- bruk effekt --------------------------------------------------------
    @staticmethod
    def _pick_mode(dev, effect):
        names = {m.name.lower(): m for m in dev.modes}
        for cand in EFFECT[effect][2]:
            if cand.lower() in names:
                return names[cand.lower()]
        return None

    def _apply_logitech(self, key, dev_ids, st):
        import logitech as L
        mode = RATBAG_MODE.get(st["effect"], 1)
        pct = st.get("brightness", 100) / 100
        # Logitech bruker ikke Brightness-feltet for fast farge: demp selve fargen
        r, g, b = (round(c * pct) for c in st["color"])
        bright = round(255 * pct)
        dur = int(15000 - 140 * st.get("speed", 50))          # høyere fart = kortere syklus
        for path in dev_ids:
            dev = L.proxy(path, "Device")
            for pp in L.getp(dev, "Profiles"):
                prof = L.proxy(pp, "Profile")
                for lp in L.getp(prof, "Leds"):
                    led = L.proxy(lp, "Led")
                    modes = list(L.getp(led, "Modes"))
                    m = mode if mode in modes else (1 if 1 in modes else modes[0])
                    L.setp(led, "Mode", GLib.Variant("u", m))
                    if m in (1, 3):
                        L.setp(led, "Color", GLib.Variant("(uuu)", (r, g, b)))
                    if m in (2, 3):
                        L.setp(led, "EffectDuration", GLib.Variant("u", max(1000, dur)))
                    L.setp(led, "Brightness", GLib.Variant("u", bright))
        # lagre til enhetens minne litt etter siste endring (skåner flash-minnet)
        timers = self.__dict__.setdefault("_logi_timers", {})
        if key in timers:
            timers[key].cancel()
        t = threading.Timer(1.2, lambda: self.do("logi_commit", key, list(dev_ids)))
        t.daemon = True
        timers[key] = t
        t.start()
        self._status("Sender til enheten …", True)

    def _logi_commit(self, key, dev_ids):
        import logitech as L
        def commit(dev):
            r = dev.call_sync("Commit", None, Gio.DBusCallFlags.NONE, 30000, None).unpack()[0]
            if r != 0:
                raise RuntimeError(f"lagring til {key} feilet (kode {r})")

        for path in dev_ids:
            dev = L.proxy(path, "Device")
            commit(dev)
            # Enheten leser profilens lys bare når en profil aktiveres:
            # bytt kort til en annen profil og tilbake.
            profs = [L.proxy(p, "Profile") for p in L.getp(dev, "Profiles")]
            act = next((i for i, p in enumerate(profs) if L.getp(p, "IsActive")), 0)
            other = next((i for i in range(len(profs))
                          if i != act and not L.getp(profs[i], "Disabled")), None)
            if other is not None:
                L.call(profs[other], "SetActive")
                commit(dev)
                time.sleep(0.5)
                L.call(profs[act], "SetActive")
                commit(dev)
        self._status(f"Brukt ✓ {time.strftime('%H:%M:%S')}")

    def _apply(self, key, dev_ids, st, zone_colors=None):
        if dev_ids and isinstance(dev_ids[0], str):          # Logitech via ratbagd
            return self._apply_logitech(key, dev_ids, st)
        effect = st["effect"]
        r, g, b = st["color"]
        bright = st.get("brightness", 100) / 100
        speed = st.get("speed", 50) / 100
        for did in dev_ids:
            dev = self.client.devices[did]
            if dev.type.name == "MOTHERBOARD" and effect in ("static", "off"):
                self._mb_static(dev, effect, st, zone_colors, bright)
                continue
            mode = self._pick_mode(dev, effect)
            if zone_colors and effect == "static" and len(dev.zones) > 1:
                # egen farge per uttak krever Direct (farge per LED)
                mode = next((m for m in dev.modes if m.name.lower() == "direct"), mode)
            col = (r, g, b)
            if mode is None:
                if effect == "off":                  # ingen «Off»: sett svart
                    mode, col = self._pick_mode(dev, "static"), (0, 0, 0)
                if mode is None:
                    continue
            if effect == "off" and mode.name.lower() != "off":
                col = (0, 0, 0)
            has_b = ModeFlags.HAS_BRIGHTNESS in mode.flags and mode.brightness_max is not None
            if has_b:
                lo, hi = mode.brightness_min, mode.brightness_max
                mode.brightness = round(lo + (hi - lo) * bright)
            else:
                col = tuple(round(c * bright) for c in col)
            if ModeFlags.HAS_SPEED in mode.flags and mode.speed_max is not None:
                lo, hi = mode.speed_min, mode.speed_max
                mode.speed = round(lo + (hi - lo) * speed)
            rgb = RGBColor(*col)
            if EFFECT[effect][3] and ModeFlags.HAS_MODE_SPECIFIC_COLOR in mode.flags:
                mode.color_mode = ModeColors.MODE_SPECIFIC
                n = max(1, mode.colors_min or 0)
                mode.colors = [rgb] * min(n, mode.colors_max or n)
            self._send_mode(dev, mode)
            if mode.color_mode == ModeColors.PER_LED or mode.name.lower() == "direct":
                if zone_colors and len(dev.zones) > 1:
                    for zi, zone in enumerate(dev.zones):
                        zc = zone_colors.get(str(zi)) or st["color"]
                        zc = tuple(round(c * bright) for c in zc) if not has_b else tuple(zc)
                        zone.set_color(RGBColor(*(zc if effect != "off" else (0, 0, 0))), fast=True)
                else:
                    dev.set_color(rgb, fast=True)   # fast: ikke vent på treg tilbakelesning
        self._status(f"Brukt ✓ {time.strftime('%H:%M:%S')}")
        self._schedule_profile_save()

    def _mb_static(self, dev, effect, st, zone_colors, bright):
        """ASUS Aura: «Static» farger bare logoen på hovedkortet, mens ARGB-uttakene
        (vifter, pumpe) bare følger «Direct». Send derfor begge – logoen beholder
        sin farge når Direct tar over uttakene."""
        off = effect == "off"
        col = (0, 0, 0) if off else tuple(round(c * bright) for c in st["color"])
        names = {m.name.lower(): m for m in dev.modes}
        logo = names.get("off") if off else names.get("static")
        if logo is not None:
            if not off and ModeFlags.HAS_MODE_SPECIFIC_COLOR in logo.flags:
                logo.color_mode = ModeColors.MODE_SPECIFIC
                n = max(1, logo.colors_min or 0)
                logo.colors = [RGBColor(*col)] * min(n, logo.colors_max or n)
            self._send_mode(dev, logo)
            time.sleep(0.3)
        direct = names.get("direct")
        if direct is None:
            return
        self._send_mode(dev, direct)
        for zi, zone in enumerate(dev.zones):
            zc = (zone_colors or {}).get(str(zi))
            zc = col if (off or not zc) else tuple(round(c * bright) for c in zc)
            zone.set_color(RGBColor(*zc), fast=True)

    @staticmethod
    def _send_mode(dev, mode):
        """Send moduskommandoen uten å vente på at OpenRGB sender all enhetsdata
        tilbake. Den ventingen går ut på tid for trege enheter (RAM via SMBus)
        og river ned hele forbindelsen."""
        from openrgb.utils import PacketType
        data = mode.pack(dev.comms._protocol_version)
        dev.comms.send_header(dev.id, PacketType.RGBCONTROLLER_UPDATEMODE, len(data))
        dev.comms.send_data(data)
        dev.active_mode = mode.id

    def _zone_resize(self, did, zi, size):
        zone = self.client.devices[did].zones[zi]
        if len(zone.leds) == size:
            return                                   # allerede riktig
        import struct
        from openrgb.utils import PacketType
        comms = self.client.devices[did].comms
        comms.send_header(did, PacketType.RGBCONTROLLER_RESIZEZONE, struct.calcsize("ii"))
        comms.send_data(struct.pack("ii", zi, size))
        time.sleep(1.0)
        self._reconnect()                            # hent oppdatert LED-liste
        self._status(f"Uttak {zi + 1}: {size} LED")

    def _schedule_profile_save(self):
        # lagre OpenRGB-profilen (brukes ved oppstart) når du har sluttet å justere
        if self._save_timer:
            self._save_timer.cancel()
        self._save_timer = threading.Timer(2.0, lambda: self.do("save_profile"))
        self._save_timer.daemon = True
        self._save_timer.start()

    def _save_profile(self):
        if self.client:
            self.client.save_profile(PROFILE)


# --------------------------------------------------------------------------
# Lagring
# --------------------------------------------------------------------------
def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f, indent=1)
        os.replace(tmp, STATE_FILE)
    except OSError:
        pass


def set_autostart(on):
    """Samme oppstartsfil som «Oppstart» i Programmer-fanen (minimert OpenRGB med profilen)."""
    import autostart
    app = next(a for a in autostart.apps() if a[0] == "openrgb")
    (autostart.enable if on else autostart.disable)(app)


# --------------------------------------------------------------------------
# GUI
# --------------------------------------------------------------------------
def rgba(c):
    x = Gdk.RGBA()
    x.red, x.green, x.blue, x.alpha = c[0] / 255, c[1] / 255, c[2] / 255, 1
    return x


def from_rgba(x):
    return [round(x.red * 255), round(x.green * 255), round(x.blue * 255)]


def card_box(title, icon=None, subtitle=None):
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    outer.add_css_class("card")
    inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    for side, v in (("top", 14), ("bottom", 14), ("start", 16), ("end", 16)):
        getattr(inner, f"set_margin_{side}")(v)
    outer.append(inner)
    head = Gtk.Box(spacing=8)
    if icon:
        head.append(Gtk.Image.new_from_icon_name(icon))
    t = Gtk.Label(label=title, xalign=0)
    t.add_css_class("heading")
    head.append(t)
    inner.append(head)
    if subtitle:
        s = Gtk.Label(label=subtitle, xalign=0, wrap=True)
        s.add_css_class("caption")
        s.add_css_class("dim-label")
        inner.append(s)
    return outer, inner, head


def labeled_scale(text, value, on_change):
    row = Gtk.Box(spacing=8)
    lbl = Gtk.Label(label=text, xalign=0, width_chars=10)
    lbl.add_css_class("caption")
    row.append(lbl)
    sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
    sc.set_value(value)
    sc.set_hexpand(True)
    sc.set_draw_value(False)
    pct = Gtk.Label(label=f"{int(value)} %", width_chars=5, xalign=1)
    pct.add_css_class("numeric")
    pct.add_css_class("caption")

    def changed(s):
        pct.set_label(f"{int(s.get_value())} %")
        on_change(int(s.get_value()))
    sc.connect("value-changed", changed)
    row.append(sc)
    row.append(pct)
    return row, sc


class GroupCard:
    """Ett kort for én gruppe (f.eks. Tastatur) som kan bestå av flere enheter."""

    def __init__(self, page, key, title, icon, devices):
        self.page, self.key = page, key
        self.dev_ids = [d.id for d in devices]
        self.devices = devices
        st = dict(DEFAULT, **page.state.get("groups", {}).get(key, {}))
        self.st = st
        names = sorted({d.name for d in devices})
        self.widget, inner, _head = card_box(title, icon, " · ".join(names))
        self._quiet = False

        # Effekter som minst én enhet i gruppen støtter
        self.effects = [e for e in EFFECTS
                        if e[0] == "off" or any(RgbBackend._pick_mode(d, e[0]) for d in devices)]
        if st["effect"] not in [e[0] for e in self.effects]:
            st["effect"] = self.effects[0][0]
        row = Gtk.Box(spacing=8)
        self.dropdown = Gtk.DropDown.new_from_strings([e[1] for e in self.effects])
        self.dropdown.set_selected([e[0] for e in self.effects].index(st["effect"]))
        self.dropdown.connect("notify::selected", self._on_effect)
        self.dropdown.set_hexpand(True)
        row.append(self.dropdown)
        self.color_btn = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False))
        self.color_btn.set_rgba(rgba(st["color"]))
        self.color_btn.connect("notify::rgba", self._on_color)
        row.append(self.color_btn)
        inner.append(row)

        sw = Gtk.Box(spacing=4)
        for name, c in SWATCHES:
            b = Gtk.Button()
            b.set_tooltip_text(name)
            b.add_css_class("swatch")
            b.add_css_class("circular")
            b.set_child(self._dot(c))
            b.connect("clicked", lambda _b, c=c: self.set_color(list(c)))
            sw.append(b)
        self.swatches = sw
        inner.append(sw)

        r1, self.bright = labeled_scale("Lysstyrke", st["brightness"], self._on_bright)
        r2, self.speed = labeled_scale("Fart", st["speed"], self._on_speed)
        self.speed_row = r2
        inner.append(r1)
        inner.append(r2)
        self.inner = inner
        self._sync_sensitivity()

    @staticmethod
    def _dot(c):
        d = Gtk.DrawingArea()
        d.set_content_width(16)
        d.set_content_height(16)

        def draw(_a, cr, w, h):
            cr.arc(w / 2, h / 2, min(w, h) / 2, 0, 6.2832)
            cr.set_source_rgb(c[0] / 255, c[1] / 255, c[2] / 255)
            cr.fill()
        d.set_draw_func(draw)
        return d

    def _sync_sensitivity(self):
        eff = self.st["effect"]
        uses_color = EFFECT[eff][3]
        self.color_btn.set_sensitive(uses_color)
        self.swatches.set_sensitive(uses_color)
        self.bright.get_parent().set_sensitive(eff != "off")
        has_speed = any(
            (m := RgbBackend._pick_mode(d, eff)) is not None and ModeFlags.HAS_SPEED in m.flags
            for d in self.devices)
        self.speed_row.set_sensitive(has_speed and eff != "off")

    # --- endringer fra brukeren --------------------------------------------
    def _on_effect(self, dd, _p):
        if self._quiet:
            return
        self.st["effect"] = self.effects[dd.get_selected()][0]
        self._sync_sensitivity()
        self.push()

    def _on_color(self, btn, _p):
        if self._quiet:
            return
        self.st["color"] = from_rgba(btn.get_rgba())
        self.push()

    def _on_bright(self, v):
        if not self._quiet:
            self.st["brightness"] = v
            self.push()

    def _on_speed(self, v):
        if not self._quiet:
            self.st["speed"] = v
            self.push()

    # --- fra «Alle enheter» -------------------------------------------------
    def set_color(self, c, push=True):
        self.st["color"] = list(c)
        self._quiet = True
        self.color_btn.set_rgba(rgba(c))
        self._quiet = False
        if push:
            self.push()

    def set_effect(self, eff, push=True):
        keys = [e[0] for e in self.effects]
        if eff not in keys:                      # f.eks. «Blink» på RAM
            eff = "cycle" if eff == "rainbow" and "cycle" in keys else "static"
            if eff not in keys:
                return
        self.st["effect"] = eff
        self._quiet = True
        self.dropdown.set_selected(keys.index(eff))
        self._quiet = False
        self._sync_sensitivity()
        if push:
            self.push()

    def set_brightness(self, v, push=True):
        self.st["brightness"] = v
        self._quiet = True
        self.bright.set_value(v)
        self._quiet = False
        if push:
            self.push()

    def reset(self):
        """Fabrikkstandard: regnbue (eller fargesyklus), full lysstyrke, normal fart."""
        self._quiet = True
        self.st.update({"color": list(DEFAULT["color"]), "brightness": 100, "speed": 50})
        self.color_btn.set_rgba(rgba(self.st["color"]))
        self.bright.set_value(100)
        self.speed.set_value(50)
        self._quiet = False
        self.set_effect("rainbow", push=False)

    def zone_colors(self):
        return None

    def push(self):
        self.page.remember(self.key, self.st)
        self.page.backend.do("apply", self.key, self.dev_ids, dict(self.st), self.zone_colors())


class MotherboardCard(GroupCard):
    """Hovedkort: i tillegg egen farge og LED-antall per ARGB-uttak (viftene)."""

    def __init__(self, page, key, title, icon, devices):
        super().__init__(page, key, title, icon, devices)
        self.headers = page.state.setdefault("headers", {})
        self.zone_widgets = []
        dev = devices[0]
        hdr = Gtk.Label(label="Uttak (vifter og LED-lister) – egen farge i «Statisk»", xalign=0)
        hdr.add_css_class("caption")
        hdr.add_css_class("heading")
        self.inner.append(hdr)
        grid = Gtk.Grid(column_spacing=10, row_spacing=6)
        for zi, zone in enumerate(dev.zones):
            hs = self.headers.setdefault(str(zi), {})
            name = zone.name.replace("Addressable RGB Header", "ARGB-uttak")
            grid.attach(Gtk.Label(label=name, xalign=0, hexpand=True), 0, zi, 1, 1)
            own = Gtk.CheckButton(label="Egen farge", active=bool(hs.get("color")))
            cb = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False))
            cb.set_rgba(rgba(hs.get("color") or self.st["color"]))
            cb.set_sensitive(bool(hs.get("color")))
            spin = Gtk.SpinButton.new_with_range(1, 120, 1)
            spin.set_value(hs.get("leds") or len(zone.leds))
            spin.set_tooltip_text("Antall LED på uttaket. Legg sammen LED for alle vifter i kjeden "
                                  "(vanligvis 8–24 per vifte).")
            lab = Gtk.Label(label="LED")
            lab.add_css_class("dim-label")
            own.connect("toggled", self._on_own, zi, cb)
            cb.connect("notify::rgba", self._on_zone_color, zi, own)
            spin.connect("value-changed", self._on_leds, zi)
            grid.attach(own, 1, zi, 1, 1)
            grid.attach(cb, 2, zi, 1, 1)
            grid.attach(spin, 3, zi, 1, 1)
            grid.attach(lab, 4, zi, 1, 1)
            self.zone_widgets.append((own, cb))
        self.inner.append(grid)
        self.zone_grid = grid
        self._sync_sensitivity()

    def _sync_sensitivity(self):
        super()._sync_sensitivity()
        if hasattr(self, "zone_grid"):
            self.zone_grid.set_sensitive(True)
            for own, cb in self.zone_widgets:
                own.set_sensitive(self.st["effect"] == "static")
                cb.set_sensitive(self.st["effect"] == "static" and own.get_active())

    def reset(self):
        self.headers = self.page.state.setdefault("headers", {})
        for hs in self.headers.values():
            hs["color"] = None
        self._resetting = True
        for own, cb in self.zone_widgets:
            own.set_active(False)
            cb.set_sensitive(False)
        self._resetting = False
        super().reset()

    def _on_own(self, chk, zi, cb):
        if getattr(self, "_resetting", False):
            return
        hs = self.headers.setdefault(str(zi), {})
        hs["color"] = from_rgba(cb.get_rgba()) if chk.get_active() else None
        cb.set_sensitive(chk.get_active())
        self.page.save()
        self.push()

    def _on_zone_color(self, cb, _p, zi, own):
        if own.get_active():
            self.headers.setdefault(str(zi), {})["color"] = from_rgba(cb.get_rgba())
            self.page.save()
            self.push()

    def _on_leds(self, spin, zi):
        n = int(spin.get_value())
        self.headers.setdefault(str(zi), {})["leds"] = n
        self.page.save()
        self.page.backend.do("zone_resize", self.dev_ids[0], zi, n)
        self.push()

    def zone_colors(self):
        if self.st["effect"] != "static":
            return None
        return {k: v.get("color") for k, v in self.headers.items() if v.get("color")} or None


class RgbPage(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.state = load_state()
        self.cards = []
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(12)
        self.set_child(box)
        self.box = box

        # statuslinje
        bar = Gtk.Box(spacing=8)
        self.spinner = Gtk.Spinner()
        bar.append(self.spinner)
        self.status = Gtk.Label(xalign=0, hexpand=True, wrap=True)
        self.status.add_css_class("dim-label")
        bar.append(self.status)
        auto_lbl = Gtk.Label(label="Bruk ved oppstart")
        auto_lbl.set_tooltip_text("Setter lysene dine automatisk når du logger inn, "
                                  "også uten at Systemmonitor er åpen.")
        bar.append(auto_lbl)
        self.auto_sw = Gtk.Switch(valign=Gtk.Align.CENTER,
                                  active=self.state.get("autostart", True))
        self.auto_sw.connect("notify::active", self._on_autostart)
        bar.append(self.auto_sw)
        self.apply_btn = Gtk.Button(valign=Gtk.Align.CENTER, child=Adw.ButtonContent(
            label="Bruk", icon_name="object-select-symbolic"))
        self.apply_btn.add_css_class("suggested-action")
        self.apply_btn.add_css_class("pill")
        self.apply_btn.set_tooltip_text("Sender alle fargene og effektene til alle enhetene nå.")
        self.apply_btn.connect("clicked", self.apply_all_now)
        bar.append(self.apply_btn)
        adv = Gtk.Button(label="Avansert (OpenRGB)")
        adv.set_tooltip_text("Åpner OpenRGB for effekter og innstillinger per enkelt-LED.")
        adv.connect("clicked", lambda *_: subprocess.Popen(
            OPENRGB_CMD + ["--client"], start_new_session=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        bar.append(adv)
        import confirm
        bar.append(confirm.reset_button(
            "RGB",
            "• Alle enheter settes til Regnbue (fargesyklus der regnbue ikke finnes)\n"
            "• Full lysstyrke og normal fart\n"
            "• Egne farger på vifteuttakene fjernes\n"
            "• «Bruk ved oppstart» slås på\n"
            "Antall LED på vifteuttakene beholdes, siden det beskriver viftene dine.",
            self.factory_reset))
        box.append(bar)

        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.append(self.content)
        self.backend = RgbBackend(self._on_status, self._on_ready)

    # --- status og tilkobling ----------------------------------------------
    def _on_status(self, text, busy):
        self.status.set_label(text)
        self.spinner.set_spinning(busy)
        return False

    def _on_ready(self, devices):
        while (c := self.content.get_first_child()):
            self.content.remove(c)
        self.cards = []
        if not devices:
            self._on_status("OpenRGB fant ingen RGB-enheter.", False)
            return False
        self._on_status(f"Tilkoblet OpenRGB · {len(devices)} enheter funnet", False)

        self.content.append(self._all_card())
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=False,
                           max_children_per_line=2, min_children_per_line=1,
                           column_spacing=12, row_spacing=12, valign=Gtk.Align.START)
        devices = list(devices) + logitech_devices()
        used = set()
        for key, title, icon, types in GROUPS:
            devs = [d for d in devices if d.id not in used and
                    (types is None or d.type.name in types)]
            if not devs:
                continue
            used.update(d.id for d in devs)
            cls = MotherboardCard if key == "motherboard" else GroupCard
            card = cls(self, key, title, icon, devs)
            self.cards.append(card)
            flow.append(card.widget)
            card.widget.get_parent().set_focusable(False)
        self.content.append(flow)

        # legg inn lagrede LED-antall og innstillinger igjen
        for card in self.cards:
            if isinstance(card, MotherboardCard):
                for zi, hs in self.state.get("headers", {}).items():
                    if hs.get("leds") and int(zi) < len(card.devices[0].zones) \
                            and hs["leds"] != len(card.devices[0].zones[int(zi)].leds):
                        self.backend.do("zone_resize", card.dev_ids[0], int(zi), hs["leds"])
            if card.key in self.state.get("groups", {}):
                card.push()
        if "autostart" not in self.state:
            self._on_autostart(self.auto_sw)
        return False

    def _all_card(self):
        outer, inner, _h = card_box("Alle enheter", "starred-symbolic",
                                    "Velg farge og effekt for alt samtidig. Juster hver enhet under.")
        sw = Gtk.Box(spacing=6)
        for name, c in SWATCHES:
            b = Gtk.Button()
            b.set_tooltip_text(name)
            b.add_css_class("circular")
            b.set_child(GroupCard._dot(c))
            b.connect("clicked", lambda _b, c=c: self._all_color(list(c)))
            sw.append(b)
        self.all_color = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False))
        self.all_color.set_rgba(rgba(self.state.get("all_color", DEFAULT["color"])))
        self.all_color.connect("notify::rgba", lambda b, _p: self._all_color(from_rgba(b.get_rgba()), False))
        sw.append(self.all_color)
        inner.append(sw)

        eff = Gtk.Box(spacing=0, homogeneous=True)
        eff.add_css_class("linked")
        for key, name, _c, _u in EFFECTS:
            b = Gtk.Button(label=name)
            b.connect("clicked", lambda _b, k=key: self._all_effect(k))
            eff.append(b)
        inner.append(eff)
        row, self.all_bright_sc = labeled_scale("Lysstyrke", self.state.get("all_brightness", 100),
                                                self._all_bright)
        inner.append(row)
        self._all_timer = 0
        return outer

    def _all_color(self, c, update_button=True):
        if getattr(self, "_resetting", False):
            return
        self.state["all_color"] = c
        if update_button:
            self.all_color.set_rgba(rgba(c))
            return                                   # notify::rgba kaller oss igjen
        for card in self.cards:
            if not EFFECT[card.st["effect"]][3]:
                card.set_effect("static", push=False)
            card.set_color(c)

    def _all_effect(self, eff):
        for card in self.cards:
            card.set_effect(eff)

    def _all_bright(self, v):
        if getattr(self, "_resetting", False):
            return
        self.state["all_brightness"] = v
        if self._all_timer:
            GLib.source_remove(self._all_timer)

        def fire():
            self._all_timer = 0
            for card in self.cards:
                card.set_brightness(v)
            return False
        self._all_timer = GLib.timeout_add(250, fire)

    def factory_reset(self):
        leds = {k: {"leds": v["leds"]} for k, v in self.state.get("headers", {}).items()
                if v.get("leds")}
        self.state = {"headers": leds, "autostart": True}
        self._resetting = True
        if hasattr(self, "all_color"):
            self.all_color.set_rgba(rgba(DEFAULT["color"]))
        if hasattr(self, "all_bright_sc"):
            self.all_bright_sc.set_value(100)
        self._resetting = False
        self.auto_sw.set_active(True)
        self._on_autostart(self.auto_sw)
        for card in self.cards:
            card.reset()
            card.push()
        self.save()
        self._on_status("Tilbakestilt til fabrikkstandard – sender til enhetene …", True)

    def apply_all_now(self, *_):
        """«Bruk»: send alt til alle enheter (kobler til på nytt om nødvendig)."""
        self._on_status("Bruker innstillingene …", True)
        if not self.cards:
            self.backend.do("connect")
            return
        for card in self.cards:
            if isinstance(card, MotherboardCard):
                for zi, hs in self.state.get("headers", {}).items():
                    if hs.get("leds"):
                        self.backend.do("zone_resize", card.dev_ids[0], int(zi), hs["leds"])
            card.push()

    # --- lagring ------------------------------------------------------------
    def remember(self, key, st):
        self.state.setdefault("groups", {})[key] = dict(st)
        self.save()

    def save(self):
        save_state(self.state)

    def _on_autostart(self, sw, *_):
        self.state["autostart"] = sw.get_active()
        set_autostart(sw.get_active())
        self.save()
