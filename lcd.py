"""CPU-skjerm-fanen i Systemmonitor – styrer LCD-skjermen på Thermalright-kjølere
(her GrandVision 360 AIO, 480×480) via trcc-linux som følger med Bazzite.

* All styring går gjennom `trcc`-tjenesten (daemon), som eier USB-tilkoblingen og
  sender bilder til skjermen hele tiden (ellers faller den tilbake til logoen).
* Live forhåndsvisning leses rett fra tjenestens delte bildebuffer.
"""
import json
import os
import queue
import re
import subprocess
import threading
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402

import deps  # noqa: E402

TRCC = deps.find_trcc() or "/usr/bin/trcc"
HOME = Path.home()
CLOUD_PREVIEWS = HOME / ".trcc/data/web"
BUILTIN_THEME1 = HOME / ".trcc/data/theme480480/Theme1"
STATE_FILE = HOME / ".config/systemmonitor/lcd.json"
AUTOSTART = HOME / ".config/autostart/systemmonitor-trcc.desktop"
OLD_AUTOSTART = HOME / ".config/autostart/trcc.desktop"

CATEGORIES = [("", "Alle"), ("a", "Galleri"), ("b", "Teknologi"), ("c", "HUD"),
              ("d", "Lys"), ("e", "Natur"), ("y", "Estetikk")]
SENSOR_WORDS = {
    "temp": "temperatur", "usage": "bruk", "freq": "klokke", "clock": "klokke",
    "power": "effekt", "used": "brukt", "available": "ledig", "total": "totalt",
    "percent": "prosent", "fan": "vifte", "fan_rpm": "vifte RPM", "rpm": "RPM",
    "vram_used": "VRAM brukt", "vram_total": "VRAM totalt",
}


# --------------------------------------------------------------------------
# trcc-kommandoer
# --------------------------------------------------------------------------
def trcc(*args, timeout=60):
    r = subprocess.run([TRCC, *map(str, args)], capture_output=True, text=True, timeout=timeout)
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        lines = [ln for ln in out.strip().splitlines() if ln.strip()]
        raise RuntimeError(lines[-1] if lines else f"trcc feilet ({r.returncode})")
    return out


def daemon_running():
    try:
        return "is running" in trcc("daemon-status", timeout=15)
    except Exception:  # noqa: BLE001
        return False


def start_daemon():
    subprocess.Popen([TRCC, "daemon"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    for _ in range(30):
        time.sleep(0.5)
        if daemon_running():
            return True
    return False


def find_key():
    out = trcc("device", "list")
    m = re.search(r"\b([0-9a-f]{4}:[0-9a-f]{4})\b", out)
    name = re.search(r"[0-9a-f]{4}:[0-9a-f]{4}\s+(.+?)\s+\(", out)
    return (m.group(1) if m else None), (name.group(1) if name else "Kjølerskjerm")


def parse_status(out):
    st = {}
    for key, rx in (("orientation", r"orientation:\s+(\d+)"), ("brightness", r"brightness:\s+(\d+)"),
                    ("theme", r"current theme:\s+(.+)"), ("overlay", r"overlay enabled:\s+(\w+)"),
                    ("fit", r"fit mode:\s+(\w+)"), ("game", r"game mode:\s+(\w+)"),
                    ("showing", r"showing:\s+(.+)")):
        m = re.search(rx, out)
        if m:
            st[key] = m.group(1).strip()
    return st


def parse_themes(out):
    res = []
    for line in out.splitlines():
        m = re.match(r"\s+(\S+)\s+\S+\s+(/\S.*)$", line)
        if m:
            res.append((m.group(1), m.group(2).strip()))
    return res


def parse_cloud(out):
    return re.findall(r"^\s+([a-z]\d{3})\s+(\w+)", out, re.M)


def parse_overlay(out):
    els = []
    for line in out.splitlines():
        m = re.match(r"\s+(el_\w+)\s+(\w+)\s+\(\s*(-?\d+),\s*(-?\d+)\)\s+(.*?)\s+size=(\d+)\s+(#[0-9a-fA-F]{6})", line)
        if m:
            eid, typ, x, y, what, size, color = m.groups()
            els.append({"id": eid, "type": typ, "x": int(x), "y": int(y),
                        "what": what.strip().strip("'"), "size": int(size), "color": color})
    return els


def parse_sensors(out):
    res = []
    for line in out.splitlines():
        m = re.match(r"\s+(\S+:\S+)\s+([-\d.]+)\s+(\S+)\s+\((\w+)\)", line)
        if m:
            res.append((m.group(1), m.group(2), m.group(3)))
    return res


def sensor_label(mid):
    parts = mid.split(":")
    dev = {"cpu": "CPU", "memory": "RAM", "gpu": "GPU", "fan": "Vifte", "disk": "Disk",
           "net": "Nett"}.get(parts[0], parts[0])
    if parts[0] == "gpu" and len(parts) > 2:
        dev = {"primary": "GPU", "nvidia": "NVIDIA", "amd": "AMD"}.get(parts[1], parts[1])
    if parts[0] == "fan" and len(parts) >= 4:
        dev = f"Vifte {parts[3]}"
    if parts[0] == "memory" and parts[1] == "dimm":
        dev = "RAM-brikke"
    word = SENSOR_WORDS.get(parts[-1], parts[-1])
    return f"{dev} {word}"


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return {}


def save_state(st):
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(st, indent=1))
    except OSError:
        pass


def hexcolor(rgba):
    return "{:02x}{:02x}{:02x}".format(*(round(c * 255) for c in (rgba.red, rgba.green, rgba.blue)))


def to_rgba(hexs):
    c = Gdk.RGBA()
    c.parse(hexs if hexs.startswith("#") else "#" + hexs)
    return c


# --------------------------------------------------------------------------
# GUI-hjelpere
# --------------------------------------------------------------------------
def card(title, subtitle=None):
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    outer.add_css_class("card")
    inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    for side, v in (("top", 14), ("bottom", 14), ("start", 16), ("end", 16)):
        getattr(inner, f"set_margin_{side}")(v)
    outer.append(inner)
    if title:
        t = Gtk.Label(label=title, xalign=0)
        t.add_css_class("heading")
        inner.append(t)
    if subtitle:
        s = Gtk.Label(label=subtitle, xalign=0, wrap=True)
        s.add_css_class("caption")
        s.add_css_class("dim-label")
        inner.append(s)
    return outer, inner


def row(label, widget, sub=None):
    r = Gtk.Box(spacing=12)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
    box.append(Gtk.Label(label=label, xalign=0))
    if sub:
        s = Gtk.Label(label=sub, xalign=0, wrap=True)
        s.add_css_class("caption")
        s.add_css_class("dim-label")
        box.append(s)
    r.append(box)
    widget.set_valign(Gtk.Align.CENTER)
    r.append(widget)
    return r


def scroller(child):
    sc = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
    sc.set_child(child)
    return sc


def vbox(spacing=12):
    b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)
    for side in ("top", "bottom", "start", "end"):
        getattr(b, f"set_margin_{side}")(4)
    return b


# --------------------------------------------------------------------------
# Fanen
# --------------------------------------------------------------------------
class LcdPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(self, f"set_margin_{side}")(12)
        self.key = None
        self.state = load_state()
        self.q = queue.Queue()
        self._timers = {}
        self._quiet = False
        self._alarm_on = False
        self._cast = None

        # ---------- venstre: forhåndsvisning og tjeneste ----------
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        left.set_size_request(340, -1)
        pc, pi = card(None)
        self.dev_lbl = Gtk.Label(label="Kjølerskjerm", xalign=0)
        self.dev_lbl.add_css_class("heading")
        pi.append(self.dev_lbl)
        self.preview = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN, can_shrink=True)
        self.preview.set_size_request(300, 300)
        self.preview.set_overflow(Gtk.Overflow.HIDDEN)
        self.preview.add_css_class("lcd-preview")
        pi.append(self.preview)
        self.prev_lbl = Gtk.Label(label="Live forhåndsvisning av skjermen", xalign=0.5)
        self.prev_lbl.add_css_class("caption")
        self.prev_lbl.add_css_class("dim-label")
        pi.append(self.prev_lbl)
        left.append(pc)

        sc_, si = card("TRCC-tjenesten",
                       "Tjenesten sender bilder til skjermen hele tiden. Uten den viser "
                       "skjermen bare Thermalright-logoen.")
        self.svc_lbl = Gtk.Label(xalign=0, wrap=True)
        si.append(self.svc_lbl)
        b = Gtk.Box(spacing=6, homogeneous=True)
        self.start_btn = Gtk.Button(label="Start")
        self.start_btn.connect("clicked", lambda *_: self.do("start"))
        self.stop_btn = Gtk.Button(label="Stopp")
        self.stop_btn.connect("clicked", lambda *_: self.do("stop"))
        b.append(self.start_btn)
        b.append(self.stop_btn)
        si.append(b)
        self.auto_sw = Gtk.Switch(active=AUTOSTART.exists())
        self.auto_sw.connect("notify::active", self._on_autostart)
        si.append(row("Start ved innlogging", self.auto_sw))
        sleep_box = Gtk.Box(spacing=6, homogeneous=True)
        off = Gtk.Button(label="Skjerm av")
        off.connect("clicked", lambda *_: self.do("cmd", ["display", "sleep", "{key}"], "Skjermen er slått av"))
        on = Gtk.Button(label="Skjerm på")
        on.connect("clicked", lambda *_: self.do("cmd", ["display", "resume"], "Skjermen er slått på"))
        sleep_box.append(off)
        sleep_box.append(on)
        si.append(sleep_box)
        adv = Gtk.Button(label="Åpne TRCC (full tema-editor)")
        adv.connect("clicked", lambda *_: subprocess.Popen(
            [TRCC, "gui"], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        si.append(adv)
        left.append(sc_)
        self.append(scroller(left))
        left.get_parent().get_parent().set_size_request(360, -1)
        left.get_parent().get_parent().set_vexpand(True)

        # ---------- høyre: undersider ----------
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, hexpand=True)
        top = Gtk.Box(spacing=8)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, vexpand=True)
        sw = Gtk.StackSwitcher(stack=self.stack, hexpand=True)
        top.append(sw)
        self.status = Gtk.Label(xalign=0, wrap=True)
        self.status.add_css_class("dim-label")
        import confirm
        top.append(confirm.reset_button(
            "CPU-skjermen",
            "• Tema 1 (innebygd) vises igjen\n• Lysstyrke 100 %, rotasjon 0°, tilpass bredde\n"
            "• Sensorer på, bakgrunn fra tema\n• Spillmodus, lysbildeserie og video av\n"
            "• Nattmodus og temperaturalarm av",
            self.factory_reset))
        right.append(top)
        right.append(self.status)
        right.append(self.stack)
        self.append(right)

        self.stack.add_titled(scroller(self._screen_page()), "skjerm", "Skjerm")
        self.stack.add_titled(scroller(self._themes_page()), "temaer", "Temaer")
        self.stack.add_titled(scroller(self._cloud_page()), "sky", "Skytemaer")
        self.stack.add_titled(scroller(self._media_page()), "media", "Bilde og video")
        self.stack.add_titled(scroller(self._overlay_page()), "sensorer", "Sensorer")
        self.stack.add_titled(scroller(self._extra_page()), "ekstra", "Ekstra")

        css = Gtk.CssProvider()
        css.load_from_string(".lcd-preview { border-radius: 50%; background: black; }"
                             ".thumb { border-radius: 12px; }")
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        threading.Thread(target=self._worker, daemon=True).start()
        threading.Thread(target=self._preview_loop, daemon=True).start()
        self.do("init")
        GLib.timeout_add_seconds(30, self._tick_extras)

    # =====================================================================
    # Undersider
    # =====================================================================
    def _screen_page(self):
        box = vbox()
        c, i = card("Skjerm")
        self.bright = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.bright.set_size_request(240, -1)
        self.bright.set_draw_value(True)
        self.bright.set_value_pos(Gtk.PositionType.RIGHT)
        self.bright.connect("value-changed", lambda s: not self._quiet and self._deb(
            "bright", lambda: self.do("cmd", ["display", "set-brightness", "{key}", int(s.get_value())],
                                      f"Lysstyrke {int(s.get_value())} %")))
        i.append(row("Lysstyrke", self.bright))

        rot = Gtk.Box(homogeneous=True)
        rot.add_css_class("linked")
        self.rot_btns = {}
        first = None
        for deg in (0, 90, 180, 270):
            b = Gtk.ToggleButton(label=f"{deg}°")
            if first:
                b.set_group(first)
            first = first or b
            b.connect("toggled", lambda b, d=deg: b.get_active() and not self._quiet and self.do(
                "cmd", ["display", "set-orientation", "{key}", d], f"Rotasjon {d}°"))
            rot.append(b)
            self.rot_btns[deg] = b
        i.append(row("Rotasjon", rot, "Snu bildet hvis kjøleren er montert på skrå eller opp ned."))

        self.fit_modes = [("width", "Tilpass bredde"), ("height", "Tilpass høyde"), ("stretch", "Strekk")]
        self.fit = Gtk.DropDown.new_from_strings([n for _k, n in self.fit_modes])
        self.fit.connect("notify::selected", lambda d, _p: not self._quiet and self.do(
            "cmd", ["display", "set-fit-mode", "{key}", self.fit_modes[d.get_selected()][0]], "Tilpasning endret"))
        i.append(row("Bildetilpasning", self.fit, "Hvordan bilder og video fyller den runde skjermen."))

        self.bg_modes = [("theme", "Fra temaet"), ("color", "Ensfarget"), ("transparent", "Gjennomsiktig")]
        bgrow = Gtk.Box(spacing=6)
        self.bg = Gtk.DropDown.new_from_strings([n for _k, n in self.bg_modes])
        self.bg.connect("notify::selected", self._on_bg)
        self.bg_color = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False))
        self.bg_color.set_rgba(to_rgba(self.state.get("bg_color", "000000")))
        self.bg_color.connect("notify::rgba", self._on_bg)
        bgrow.append(self.bg)
        bgrow.append(self.bg_color)
        i.append(row("Bakgrunn bak sensorene", bgrow))

        self.ov_sw = Gtk.Switch()
        self.ov_sw.connect("notify::active", lambda s, _p: not self._quiet and self.do(
            "cmd", ["display", "overlay", "{key}", "on" if s.get_active() else "off"],
            "Sensorer " + ("på" if s.get_active() else "av")))
        i.append(row("Vis sensorer og klokke", self.ov_sw))
        box.append(c)

        c2, i2 = card("Spillmodus", "Når CPU-bruken holder seg over grensen, viser skjermen "
                                    "spillstatistikk automatisk.")
        self.game_sw = Gtk.Switch()
        self.game_sw.connect("notify::active", lambda s, _p: not self._quiet and self.do(
            "cmd", ["display", "game", "{key}", "on" if s.get_active() else "off",
                    "--threshold", int(self.game_thr.get_value())], "Spillmodus endret"))
        i2.append(row("Spillmodus", self.game_sw))
        self.game_thr = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 5, 99, 1)
        self.game_thr.set_value(self.state.get("game_threshold", 50))
        self.game_thr.set_size_request(240, -1)
        self.game_thr.set_draw_value(True)
        self.game_thr.set_value_pos(Gtk.PositionType.RIGHT)
        self.game_thr.connect("value-changed", lambda s: self._deb("gthr", lambda: (
            self.state.__setitem__("game_threshold", int(s.get_value())), save_state(self.state),
            self.do("cmd", ["display", "game", "{key}", "--threshold", int(s.get_value())],
                    f"Spillmodus-grense {int(s.get_value())} %"))))
        i2.append(row("Grense for CPU-bruk (%)", self.game_thr))
        box.append(c2)

        c3, i3 = card("Test")
        tb = Gtk.Box(spacing=6)
        for name, hx in (("Rød", "ff0000"), ("Grønn", "00ff00"), ("Blå", "0000ff"), ("Hvit", "ffffff")):
            b = Gtk.Button(label=name)
            b.connect("clicked", lambda *_, hx=hx, n=name: self.do(
                "cmd", ["display", "color", "{key}", hx], f"Viser {n.lower()} – trykk «Tilbake til tema»"))
            tb.append(b)
        back = Gtk.Button(label="Tilbake til tema")
        back.add_css_class("suggested-action")
        back.connect("clicked", lambda *_: self.do("cmd", ["display", "restore-theme", "{key}"], "Tema gjenopprettet"))
        tb.append(back)
        i3.append(tb)
        box.append(c3)
        return box

    def _themes_page(self):
        box = vbox()
        c, i = card("Dine temaer", "Klikk et tema for å vise det på skjermen.")
        self.theme_flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=6,
                                      min_children_per_line=2, column_spacing=10, row_spacing=10,
                                      homogeneous=True)
        i.append(self.theme_flow)
        bb = Gtk.Box(spacing=6)
        imp = Gtk.Button(label="Importer tema …")
        imp.connect("clicked", self._on_import)
        bb.append(imp)
        ref = Gtk.Button(label="Oppdater")
        ref.connect("clicked", lambda *_: self.do("themes"))
        bb.append(ref)
        i.append(bb)
        box.append(c)
        return box

    def _cloud_page(self):
        box = vbox()
        c, i = card("Skytemaer fra Thermalright",
                    "Klikk et tema for å laste det ned og vise det. Det kan ta noen sekunder.")
        self.cat = Gtk.DropDown.new_from_strings([n for _k, n in CATEGORIES])
        self.cat.connect("notify::selected", lambda *_: self._fill_cloud())
        i.append(row("Kategori", self.cat))
        self.cloud_flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=8,
                                      min_children_per_line=3, column_spacing=8, row_spacing=8,
                                      homogeneous=True)
        i.append(self.cloud_flow)
        box.append(c)
        self.cloud = []
        return box

    def _media_page(self):
        box = vbox()
        c, i = card("Eget bilde")
        b = Gtk.Button(label="Velg bilde …")
        b.connect("clicked", lambda *_: self._pick_file("Velg bilde", ["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.webp"],
                                                        lambda p: self.do("cmd", ["display", "load-image", "{key}", p],
                                                                          "Bildet vises")))
        i.append(row("Vis et bilde på skjermen", b, "PNG, JPG, BMP eller WEBP. Best med kvadratiske bilder."))
        box.append(c)

        c2, i2 = card("Video")
        vb = Gtk.Button(label="Velg video …")
        vb.connect("clicked", lambda *_: self._pick_file(
            "Velg video", ["*.mp4", "*.mov", "*.webm", "*.mkv", "*.avi", "*.zt", "*.gif"],
            lambda p: self.do("cmd", ["display", "load-video", "{key}", p], "Videoen spilles av", timeout=300)))
        i2.append(row("Spill en video på skjermen", vb, "MP4, MOV, WEBM, MKV, AVI eller GIF."))
        ctl = Gtk.Box(spacing=6)
        for label, args, msg in (("⏯ Pause / fortsett", ["display", "toggle-video", "{key}"], "Pause/fortsett"),
                                 ("⏹ Stopp video", ["display", "stop-video", "{key}"], "Video stoppet")):
            bt = Gtk.Button(label=label)
            bt.connect("clicked", lambda *_, a=args, m=msg: self.do("cmd", a, m))
            ctl.append(bt)
        i2.append(ctl)
        self.loop_sw = Gtk.Switch(active=self.state.get("loop", True))
        self.loop_sw.connect("notify::active", lambda s, _p: (
            self.state.__setitem__("loop", s.get_active()), save_state(self.state),
            self.do("cmd", ["display", "loop-video", "{key}", "on" if s.get_active() else "off"],
                    "Løkke " + ("på" if s.get_active() else "av"))))
        i2.append(row("Spill i løkke", self.loop_sw))
        box.append(c2)

        c3, i3 = card("Skjermdeling", "Vis en del av PC-skjermen din live på kjøleren. "
                                      "KDE spør om tillatelse første gang.")
        g = Gtk.Grid(column_spacing=8, row_spacing=6)
        self.cast_spins = []
        for n, (lab, val) in enumerate((("X", 0), ("Y", 0), ("Bredde", 480), ("Høyde", 480))):
            g.attach(Gtk.Label(label=lab, xalign=0), n, 0, 1, 1)
            sp = Gtk.SpinButton.new_with_range(0, 7680, 10)
            sp.set_value(self.state.get("cast", [0, 0, 480, 480])[n] if self.state.get("cast") else val)
            g.attach(sp, n, 1, 1, 1)
            self.cast_spins.append(sp)
        i3.append(g)
        cb = Gtk.Box(spacing=6)
        st = Gtk.Button(label="Start skjermdeling")
        st.connect("clicked", self._start_cast)
        sp_ = Gtk.Button(label="Stopp")
        sp_.connect("clicked", self._stop_cast)
        cb.append(st)
        cb.append(sp_)
        i3.append(cb)
        box.append(c3)
        return box

    def _overlay_page(self):
        box = vbox()
        c, i = card("Sensorer på skjermen",
                    "Alt som tegnes oppå bildet. Endre plassering (X/Y fra 0 til 480), størrelse og farge, "
                    "eller slett. Endringer vises med en gang i forhåndsvisningen.")
        self.ov_grid = Gtk.Grid(column_spacing=8, row_spacing=6)
        i.append(self.ov_grid)
        box.append(c)

        c2, i2 = card("Legg til")
        self.add_types = [("metric", "Sensorverdi"), ("text", "Tekst"), ("clock", "Klokke / dato")]
        self.add_type = Gtk.DropDown.new_from_strings([n for _k, n in self.add_types])
        self.add_type.connect("notify::selected", lambda *_: self._sync_add())
        i2.append(row("Type", self.add_type))
        self.add_metric = Gtk.DropDown.new_from_strings(["(laster sensorer …)"])
        self.add_metric.set_enable_search(True)
        self.metric_ids = []
        self.add_metric_row = row("Sensor", self.add_metric)
        i2.append(self.add_metric_row)
        self.add_text = Gtk.Entry(placeholder_text="F.eks. CPU")
        self.add_text_row = row("Tekst", self.add_text)
        i2.append(self.add_text_row)
        self.clock_src = [("time", "Klokkeslett"), ("date", "Dato"), ("weekday", "Ukedag")]
        self.add_clock = Gtk.DropDown.new_from_strings([n for _k, n in self.clock_src])
        self.add_clock_row = row("Vis", self.add_clock)
        i2.append(self.add_clock_row)
        g = Gtk.Box(spacing=8)
        self.add_x = Gtk.SpinButton.new_with_range(0, 480, 5)
        self.add_x.set_value(200)
        self.add_y = Gtk.SpinButton.new_with_range(0, 480, 5)
        self.add_y.set_value(200)
        self.add_size = Gtk.SpinButton.new_with_range(8, 200, 2)
        self.add_size.set_value(32)
        self.add_color = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False))
        self.add_color.set_rgba(to_rgba("ffffff"))
        for lab, w in (("X", self.add_x), ("Y", self.add_y), ("Størrelse", self.add_size)):
            g.append(Gtk.Label(label=lab))
            g.append(w)
        g.append(self.add_color)
        i2.append(g)
        addb = Gtk.Button(label="Legg til på skjermen")
        addb.add_css_class("suggested-action")
        addb.connect("clicked", self._on_add)
        i2.append(addb)
        box.append(c2)
        self._sync_add()
        return box

    def _extra_page(self):
        box = vbox()
        c, i = card("Lysbildeserie", "Bytt automatisk mellom flere av temaene dine.")
        self.slide_checks = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=4)
        i.append(self.slide_checks)
        self.slide_int = Gtk.SpinButton.new_with_range(5, 3600, 5)
        self.slide_int.set_value(self.state.get("slide_interval", 60))
        i.append(row("Sekunder mellom hvert tema", self.slide_int))
        self.slide_sw = Gtk.Switch(active=self.state.get("slideshow", False))
        self.slide_sw.connect("notify::active", self._on_slideshow)
        i.append(row("Lysbildeserie på", self.slide_sw))
        box.append(c)

        c2, i2 = card("Nattmodus (ekstra)", "Demper skjermen automatisk om natten. "
                                            "Virker mens Systemmonitor er åpen.")
        self.night_sw = Gtk.Switch(active=self.state.get("night", False))
        self.night_sw.connect("notify::active", lambda s, _p: self._save_extra())
        i2.append(row("Nattmodus på", self.night_sw))
        tb = Gtk.Box(spacing=6)
        self.night_from = Gtk.SpinButton.new_with_range(0, 23, 1)
        self.night_from.set_value(self.state.get("night_from", 23))
        self.night_to = Gtk.SpinButton.new_with_range(0, 23, 1)
        self.night_to.set_value(self.state.get("night_to", 7))
        self.night_b = Gtk.SpinButton.new_with_range(0, 100, 5)
        self.night_b.set_value(self.state.get("night_brightness", 20))
        for lab, w in (("Fra kl.", self.night_from), ("til kl.", self.night_to), ("lysstyrke %", self.night_b)):
            tb.append(Gtk.Label(label=lab))
            tb.append(w)
            w.connect("value-changed", lambda *_: self._save_extra())
        i2.append(tb)
        box.append(c2)

        c3, i3 = card("Temperaturalarm (ekstra)", "Skjermen blir rød når CPU-en blir for varm, "
                                                  "og går tilbake til temaet når den har kjølt seg ned.")
        self.alarm_sw = Gtk.Switch(active=self.state.get("alarm", False))
        self.alarm_sw.connect("notify::active", lambda s, _p: self._save_extra())
        i3.append(row("Temperaturalarm på", self.alarm_sw))
        self.alarm_t = Gtk.SpinButton.new_with_range(50, 105, 1)
        self.alarm_t.set_value(self.state.get("alarm_temp", 90))
        self.alarm_t.connect("value-changed", lambda *_: self._save_extra())
        i3.append(row("Alarm ved CPU-temperatur (°C)", self.alarm_t))
        box.append(c3)
        return box

    # =====================================================================
    # Bakgrunnsarbeid
    # =====================================================================
    def do(self, *job, **kw):
        self.q.put((job, kw))

    def _set_status(self, text):
        self.status.set_label(text)
        return False

    def _worker(self):
        while True:
            job, kw = self.q.get()
            try:
                getattr(self, "_job_" + job[0])(*job[1:], **kw)
            except Exception as e:  # noqa: BLE001
                GLib.idle_add(self._set_status, f"Feil: {e}")

    def _job_init(self):
        GLib.idle_add(self._set_status, "Starter …")
        if not daemon_running():
            GLib.idle_add(self.svc_lbl.set_label, "Starter TRCC-tjenesten …")
            start_daemon()
            trcc("display", "resume", timeout=90)
        self.key, name = find_key()
        if not self.key:
            GLib.idle_add(self._set_status, "Fant ingen Thermalright-skjerm")
            return
        GLib.idle_add(self.dev_lbl.set_label, f"{name} · {self.key}")
        self._job_status()
        self._job_themes()
        self._job_overlay()
        self._job_sensors()
        self._job_cloud()
        GLib.idle_add(self._set_status, "Klar")

    def _job_status(self):
        running = daemon_running()
        st = parse_status(trcc("status")) if self.key else {}
        GLib.idle_add(self._apply_status, running, st)

    def _apply_status(self, running, st):
        self.svc_lbl.set_label("● Kjører – skjermen oppdateres" if running else
                               "○ Stoppet – skjermen viser bare logoen")
        self.start_btn.set_sensitive(not running)
        self.stop_btn.set_sensitive(running)
        self._quiet = True
        if "brightness" in st:
            self.bright.set_value(int(st["brightness"]))
        if st.get("orientation") and int(st["orientation"]) in self.rot_btns:
            self.rot_btns[int(st["orientation"])].set_active(True)
        if "fit" in st:
            keys = [k for k, _n in self.fit_modes]
            if st["fit"] in keys:
                self.fit.set_selected(keys.index(st["fit"]))
        if "overlay" in st:
            self.ov_sw.set_active(st["overlay"].lower() == "true")
        if "game" in st:
            self.game_sw.set_active(st["game"].lower() == "on")
        self._quiet = False
        return False

    def _job_start(self):
        GLib.idle_add(self._set_status, "Starter tjenesten …")
        start_daemon()
        trcc("display", "resume", timeout=90)
        self._job_status()
        GLib.idle_add(self._set_status, "Tjenesten kjører")

    def _job_stop(self):
        trcc("kill", timeout=30)
        time.sleep(1)
        self._job_status()
        GLib.idle_add(self._set_status, "Tjenesten er stoppet")

    def _job_cmd(self, args, msg=None, timeout=60, refresh=None):
        if not self.key:
            return
        trcc(*[self.key if a == "{key}" else a for a in args], timeout=timeout)
        if msg:
            GLib.idle_add(self._set_status, f"{msg} ✓")
        if refresh:
            getattr(self, "_job_" + refresh)()

    def _job_themes(self):
        themes = parse_themes(trcc("theme", "list", self.key))
        # brukerens egne (trcc-user) foran innebygde, uten duplikater av samme sti
        GLib.idle_add(self._fill_themes, themes)

    def _job_overlay(self):
        els = parse_overlay(trcc("display", "overlay-list", self.key))
        GLib.idle_add(self._fill_overlay, els)

    def _job_sensors(self):
        sens = parse_sensors(trcc("system", "sensors"))
        GLib.idle_add(self._fill_sensors, sens)

    def _job_cloud(self):
        self.cloud = parse_cloud(trcc("theme", "cloud-list", timeout=120))
        GLib.idle_add(self._fill_cloud)

    # =====================================================================
    # Fylle inn lister
    # =====================================================================
    def _thumb(self, path, size, label, on_click, tooltip=None):
        btn = Gtk.Button()
        btn.add_css_class("flat")
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        pic = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, can_shrink=True)
        pic.set_size_request(size, size)
        pic.add_css_class("thumb")
        pic.set_overflow(Gtk.Overflow.HIDDEN)
        b.append(pic)
        lab = Gtk.Label(label=label, ellipsize=3, max_width_chars=14)
        lab.add_css_class("caption")
        b.append(lab)
        btn.set_child(b)
        btn.set_tooltip_text(tooltip or label)
        btn.connect("clicked", lambda *_: on_click())

        def load():
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), size, size, True)
                GLib.idle_add(lambda: (pic.set_paintable(Gdk.Texture.new_for_pixbuf(pb)), False)[1])
            except GLib.Error:
                pass
        if path and Path(path).exists():
            self._thumb_q.put(load)
        return btn

    @property
    def _thumb_q(self):
        if not hasattr(self, "_tq"):
            self._tq = queue.Queue()

            def run():
                while True:
                    self._tq.get()()
            threading.Thread(target=run, daemon=True).start()
        return self._tq

    def _fill_themes(self, themes):
        self.themes = themes
        while (c := self.theme_flow.get_first_child()):
            self.theme_flow.remove(c)
        while (c := self.slide_checks.get_first_child()):
            self.slide_checks.remove(c)
        chosen = set(self.state.get("slides", []))
        for name, path in themes:
            src = "dine" if ".trcc-user" in path else "innebygd"
            prev = Path(path) / "Theme.png"
            self.theme_flow.append(self._thumb(
                prev, 120, f"{name} ({src})",
                lambda p=path, n=name: self.do("cmd", ["display", "load-theme", "{key}", p],
                                               f"Tema {n} vises", refresh="overlay"), path))
            chk = Gtk.CheckButton(label=f"{name} ({src})", active=name in chosen)
            chk.theme_name = name
            chk.connect("toggled", lambda *_: self._save_slides())
            self.slide_checks.append(chk)
        return False

    def _fill_cloud(self):
        while (c := self.cloud_flow.get_first_child()):
            self.cloud_flow.remove(c)
        cat = CATEGORIES[self.cat.get_selected()][0]
        names = dict(CATEGORIES)
        for tid, _catname in self.cloud:
            if cat and not tid.startswith(cat):
                continue
            prev = None
            for d in ("480480", "zt480480"):
                p = CLOUD_PREVIEWS / d / f"{tid}.png"
                if p.exists():
                    prev = p
                    break
            self.cloud_flow.append(self._thumb(
                prev, 96, tid, lambda t=tid: self.do("cmd", ["theme", "cloud-load", "{key}", t],
                                                     f"Skytema {t} vises", timeout=180, refresh="overlay"),
                f"{names.get(tid[0], '')} {tid} – klikk for å vise"))
        return False

    def _fill_sensors(self, sens):
        self.metric_ids = [m for m, _v, _u in sens]
        labels = [f"{sensor_label(m)} – {v} {u}  ({m})" for m, v, u in sens]
        self.add_metric.set_model(Gtk.StringList.new(labels or ["(ingen sensorer)"]))
        return False

    def _fill_overlay(self, els):
        self.ov_els = els
        while (c := self.ov_grid.get_first_child()):
            self.ov_grid.remove(c)
        heads = ["Hva", "X", "Y", "Størrelse", "Farge", ""]
        for col, h in enumerate(heads):
            lab = Gtk.Label(label=h, xalign=0)
            lab.add_css_class("caption-heading")
            self.ov_grid.attach(lab, col, 0, 1, 1)
        for r, el in enumerate(els, start=1):
            what = el["what"]
            if el["type"] == "metric":
                what = f"{sensor_label(what)}"
            elif el["type"] == "text":
                what = f"Tekst «{what}»"
            elif el["type"] == "clock":
                what = {"time": "Klokkeslett", "date": "Dato", "weekday": "Ukedag"}.get(what, f"Klokke ({what})")
            self.ov_grid.attach(Gtk.Label(label=what, xalign=0, hexpand=True), 0, r, 1, 1)
            for col, (field, mx) in enumerate((("x", 480), ("y", 480), ("size", 200)), start=1):
                sp = Gtk.SpinButton.new_with_range(0, mx, 2)
                sp.set_value(el[field])
                sp.connect("value-changed", lambda s, e=el, f=field: self._deb(
                    f"ov{e['id']}{f}", lambda: self.do(
                        "cmd", ["display", "overlay-update", "{key}", e["id"], f"--{f}", int(s.get_value())],
                        "Sensor flyttet")))
                self.ov_grid.attach(sp, col, r, 1, 1)
            cb = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False))
            cb.set_rgba(to_rgba(el["color"]))
            cb.connect("notify::rgba", lambda b, _p, e=el: self.do(
                "cmd", ["display", "overlay-update", "{key}", e["id"], "--color", "#" + hexcolor(b.get_rgba())],
                "Farge endret"))
            self.ov_grid.attach(cb, 4, r, 1, 1)
            dl = Gtk.Button(icon_name="user-trash-symbolic")
            dl.add_css_class("flat")
            dl.set_tooltip_text("Slett")
            dl.connect("clicked", lambda *_, e=el: self.do(
                "cmd", ["display", "overlay-delete", "{key}", e["id"]], "Slettet", refresh="overlay"))
            self.ov_grid.attach(dl, 5, r, 1, 1)
        if not els:
            self.ov_grid.attach(Gtk.Label(label="Ingen sensorer på skjermen ennå.", xalign=0), 0, 1, 6, 1)
        return False

    # =====================================================================
    # Handlinger
    # =====================================================================
    def _deb(self, key, fn, ms=400):
        if key in self._timers:
            GLib.source_remove(self._timers[key])

        def fire():
            self._timers.pop(key, None)
            fn()
            return False
        self._timers[key] = GLib.timeout_add(ms, fire)

    def _on_bg(self, *_):
        if self._quiet:
            return
        mode = self.bg_modes[self.bg.get_selected()][0]
        hx = hexcolor(self.bg_color.get_rgba())
        self.state["bg_color"] = hx
        save_state(self.state)
        self.do("cmd", ["display", "background-mode", "{key}", mode], "Bakgrunn endret")
        if mode == "color":
            self.do("cmd", ["display", "overlay-background", "{key}", hx], "Bakgrunnsfarge endret")

    def _sync_add(self):
        t = self.add_types[self.add_type.get_selected()][0]
        self.add_metric_row.set_visible(t == "metric")
        self.add_text_row.set_visible(t == "text")
        self.add_clock_row.set_visible(t == "clock")

    def _on_add(self, *_):
        t = self.add_types[self.add_type.get_selected()][0]
        args = ["display", "overlay-add", "{key}", t, "--x", int(self.add_x.get_value()),
                "--y", int(self.add_y.get_value()), "--size", int(self.add_size.get_value()),
                "--color", "#" + hexcolor(self.add_color.get_rgba())]
        if t == "metric":
            if not self.metric_ids:
                return
            args += ["--metric", self.metric_ids[self.add_metric.get_selected()], "--show-unit"]
        elif t == "text":
            txt = self.add_text.get_text().strip()
            if not txt:
                self._set_status("Skriv inn en tekst først")
                return
            args += ["--text", txt]
        else:
            args += ["--source", self.clock_src[self.add_clock.get_selected()][0]]
        self.do("cmd", args, "Lagt til på skjermen", refresh="overlay")

    def _pick_file(self, title, patterns, cb):
        dlg = Gtk.FileDialog(title=title)
        f = Gtk.FileFilter()
        for p in patterns:
            f.add_pattern(p)
            f.add_pattern(p.upper())
        f.set_name(title)
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(f)
        dlg.set_filters(store)

        def done(d, res):
            try:
                file = d.open_finish(res)
            except GLib.Error:
                return
            if file and file.get_path():
                cb(file.get_path())
        dlg.open(self.get_root(), None, done)

    def _on_import(self, *_):
        self._pick_file("Velg temaarkiv", ["*.zip", "*.zt", "*.tar", "*.tar.gz", "*.7z"],
                        lambda p: self.do("cmd", ["theme", "import", "{key}", p], "Tema importert",
                                          refresh="themes"))

    def _start_cast(self, *_):
        if not self.key:
            return
        vals = [int(s.get_value()) for s in self.cast_spins]
        self.state["cast"] = vals
        save_state(self.state)
        self._stop_cast()
        self._cast = subprocess.Popen([TRCC, "display", "screencast", self.key, *map(str, vals)],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                      start_new_session=True)
        self._set_status("Skjermdeling startet ✓")

    def _stop_cast(self, *_):
        if self._cast and self._cast.poll() is None:
            self._cast.terminate()
        self._cast = None
        if self.key:
            self.do("cmd", ["display", "stop-screencast", "{key}"], "Skjermdeling stoppet")

    def _save_slides(self):
        c = self.slide_checks.get_first_child()
        chosen = []
        while c:
            chk = c.get_child()
            if chk.get_active():
                chosen.append(chk.theme_name)
            c = c.get_next_sibling()
        self.state["slides"] = chosen
        save_state(self.state)
        return chosen

    def _on_slideshow(self, sw, _p):
        chosen = self._save_slides()
        self.state["slideshow"] = sw.get_active()
        self.state["slide_interval"] = int(self.slide_int.get_value())
        save_state(self.state)
        if sw.get_active():
            if len(chosen) < 2:
                self._set_status("Velg minst to temaer først")
                sw.set_active(False)
                return
            self.do("cmd", ["display", "configure-slideshow", "{key}", *chosen, "--interval",
                            int(self.slide_int.get_value())], None)
        self.do("cmd", ["display", "slideshow", "{key}", "on" if sw.get_active() else "off"],
                "Lysbildeserie " + ("på" if sw.get_active() else "av"))

    def _save_extra(self):
        self.state.update({
            "night": self.night_sw.get_active(), "night_from": int(self.night_from.get_value()),
            "night_to": int(self.night_to.get_value()), "night_brightness": int(self.night_b.get_value()),
            "alarm": self.alarm_sw.get_active(), "alarm_temp": int(self.alarm_t.get_value()),
        })
        save_state(self.state)
        self._tick_extras()

    def _on_autostart(self, sw, _p):
        if sw.get_active():
            AUTOSTART.parent.mkdir(parents=True, exist_ok=True)
            AUTOSTART.write_text(
                "[Desktop Entry]\nType=Application\nName=CPU-skjerm (TRCC-tjeneste)\n"
                "Comment=Starter TRCC-tjenesten slik at kjølerskjermen viser temaet ditt\n"
                f"Exec=sh -c '{TRCC} daemon & sleep 4; {TRCC} display resume'\n"
                "Icon=trcc\nTerminal=false\nX-GNOME-Autostart-enabled=true\n")
            # den gamle oppstarten peker til en ødelagt installasjon – slå den av
            if OLD_AUTOSTART.exists():
                txt = OLD_AUTOSTART.read_text()
                if "Hidden=true" not in txt:
                    OLD_AUTOSTART.with_suffix(".desktop.bak").write_text(txt)
                    OLD_AUTOSTART.write_text(txt.rstrip("\n") + "\nHidden=true\n")
            self._set_status("Starter automatisk ved innlogging ✓")
        else:
            if AUTOSTART.exists():
                AUTOSTART.unlink()
            self._set_status("Starter ikke lenger ved innlogging")

    # --- nattmodus og temperaturalarm (sjekkes hvert 30. sekund) ------------
    def _tick_extras(self):
        if not self.key:
            return True
        st = self.state
        if st.get("night"):
            h = time.localtime().tm_hour
            a, b = st.get("night_from", 23), st.get("night_to", 7)
            night = (a <= h or h < b) if a > b else (a <= h < b)
            want = st.get("night_brightness", 20) if night else st.get("day_brightness", 100)
            if night and not st.get("_was_night"):
                st["day_brightness"] = int(self.bright.get_value())
            if st.get("_was_night") != night or int(self.bright.get_value()) != want:
                self.bright.set_value(want)
            st["_was_night"] = night
        if st.get("alarm"):
            try:
                from systemmonitor import cpu_temp, hwmon_temps
                t = cpu_temp(hwmon_temps())
            except Exception:  # noqa: BLE001
                t = None
            if t is not None:
                limit = st.get("alarm_temp", 90)
                if t >= limit and not self._alarm_on:
                    self._alarm_on = True
                    self.do("cmd", ["display", "color", "{key}", "ff0000"], f"⚠ CPU {t:.0f} °C – alarm!")
                elif t < limit - 5 and self._alarm_on:
                    self._alarm_on = False
                    self.do("cmd", ["display", "restore-theme", "{key}"], "Temperaturen er normal igjen")
        return True

    # --- tilbakestilling ----------------------------------------------------
    def factory_reset(self):
        self._quiet = True
        for w, v in ((self.slide_sw, False), (self.night_sw, False), (self.alarm_sw, False),
                     (self.game_sw, False), (self.ov_sw, True)):
            w.set_active(v)
        self.bright.set_value(100)
        self.rot_btns[0].set_active(True)
        self.fit.set_selected(0)
        self.bg.set_selected(0)
        self._quiet = False
        keep = {k: self.state[k] for k in ("cast",) if k in self.state}
        self.state = keep
        save_state(self.state)
        self._alarm_on = False
        for args in (["display", "stop-video", "{key}"], ["display", "slideshow", "{key}", "off"],
                     ["display", "game", "{key}", "off"], ["display", "background-mode", "{key}", "theme"],
                     ["display", "set-fit-mode", "{key}", "width"], ["display", "set-orientation", "{key}", 0],
                     ["display", "set-brightness", "{key}", 100]):
            self.do("cmd", args, None)
        if BUILTIN_THEME1.exists():
            self.do("cmd", ["display", "load-theme", "{key}", str(BUILTIN_THEME1)], None)
        self.do("cmd", ["display", "overlay", "{key}", "on"], "Tilbakestilt til fabrikkstandard",
                refresh="overlay")

    # =====================================================================
    # Live forhåndsvisning
    # =====================================================================
    def _preview_loop(self):
        try:
            deps.enable_trcc_import()
            from trcc import frame_share, ipc
        except ImportError:
            GLib.idle_add(self.prev_lbl.set_label, "Forhåndsvisning krever trcc-linux")
            return
        reader = frame_share.FrameReader(Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "trcc" / "frames")
        while True:
            try:
                sock = ipc.open_event_stream(["FrameSent"], shared_frames=True, timeout=5)
                f = sock.makefile("r")
                last = 0.0
                for line in f:
                    if time.monotonic() - last < 0.1:          # maks 10 bilder/s
                        continue
                    ev = json.loads(line).get("fields", {})
                    shape = ev.get("shared_shape")
                    if not ev.get("shared_seq") or not shape:
                        continue
                    w, h, stride = shape
                    px = reader.read(ev["key"], ev["shared_seq"], w, h, stride)
                    if not px:
                        continue
                    last = time.monotonic()
                    tex = Gdk.MemoryTexture.new(w, h, Gdk.MemoryFormat.B8G8R8A8, GLib.Bytes.new(bytes(px)), stride)
                    GLib.idle_add(self._show_frame, tex)
            except Exception:  # noqa: BLE001 – tjenesten kjører ikke ennå
                GLib.idle_add(self.prev_lbl.set_label, "Venter på TRCC-tjenesten …")
            time.sleep(2)

    def _show_frame(self, tex):
        self.preview.set_paintable(tex)
        if self.prev_lbl.get_label() != "Live forhåndsvisning av skjermen":
            self.prev_lbl.set_label("Live forhåndsvisning av skjermen")
        return False
