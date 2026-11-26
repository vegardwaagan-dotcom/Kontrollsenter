#!/usr/bin/env python3
"""Kontrollsenter – et enkelt grafisk overvåkingsprogram for Linux (GTK4/libadwaita).

Hovedvinduet og fanene. Maskinvaredata ligger i sensors.py, kortene i Oversikt i cards.py.
"""
import os
import json
import shutil
import subprocess
import sys
import time as _time_mod
import threading
import time

try:                                    # «Mindre minnebruk» / «Eldre PC»: tegn uten skjermkortdriveren (sparer ~110 MB)
    import json as _j
    _y = _j.load(open(os.path.expanduser("~/.config/systemmonitor/ytelse.json")))
    if (_y.get("mem") or _y.get("lowend") or _y.get("saveall")) and not os.environ.get("GSK_RENDERER"):
        os.environ["GSK_RENDERER"] = "cairo"
except (OSError, ValueError):
    pass
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

import welcome  # noqa: E402,F401  – må sjekke «første gang» før noe lager konfig-mappen
if welcome.FIRST_RUN:                        # ny installasjon: bare Oversikt, Historikk og Oppdateringer til du velger
    try:
        import funksjoner as _fn
        _fn.init_new_install()
    except Exception:  # noqa: BLE001
        pass
import i18n  # noqa: E402
import applog  # noqa: E402
if sys.platform == "win32" or os.environ.get("KS_WINPERF_TEST"):
    import winperf  # noqa: E402  – PowerShell-kall skal aldri få vinduet til å stå stille
    winperf.install()

i18n.install()          # oversetter teksten hvis engelsk er valgt (må skje før vinduer lages)
applog.setup()          # feillogg i ~/.cache/systemmonitor/logg.txt

from sensors import *  # noqa: E402,F401,F403
from cards import *  # noqa: E402,F401,F403
from cards import _monitor_geometry  # noqa: E402


# --------------------------------------------------------------------------
# Spill-overlay (MangoHud)
# --------------------------------------------------------------------------
APP_ICON = "no.waagan.Systemmonitor"
MAX_WIDTH = 1120          # innholdet strekkes ikke bredere enn dette på store skjermer
MANGOHUD_CONF = os.path.expanduser("~/.config/MangoHud/MangoHud.conf")
MANGOHUD_ENV = os.path.expanduser("~/.config/environment.d/90-systemmonitor-mangohud.conf")

OVERLAY_SETTINGS = """\
# Denne filen styres av Kontrollsenter (~/Programmer/systemmonitor).
# Overlayet vises mens Kontrollsenter kjører, og skjules når den lukkes.
# Høyre Shift + F12 slår overlayet av/på manuelt i spillet.
toggle_hud=Shift_R+F12
position=top-left
font_size=20
background_alpha=0.45
round_corners=8
table_columns=3
fps
frametime
frame_timing
cpu_stats
cpu_temp
cpu_mhz
gpu_stats
gpu_temp
gpu_power
gpu_core_clock
vram
ram
"""


def set_overlay(visible):
    """Skriv MangoHud-oppsettet. MangoHud leser filen på nytt automatisk."""
    os.makedirs(os.path.dirname(MANGOHUD_CONF), exist_ok=True)
    try:
        import games_auto
        log = games_auto.mangohud_log_lines()      # FPS-logg til øktrapporten
    except Exception:  # noqa: BLE001
        log = ""
    text = OVERLAY_SETTINGS + log + ("" if visible else "no_display\n")
    try:
        with open(MANGOHUD_CONF) as f:
            if f.read() == text:                  # uendret: ikke skriv til disk
                return
    except OSError:
        pass
    tmp = f"{MANGOHUD_CONF}.{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, MANGOHUD_CONF)


PREF_FILE = os.path.expanduser("~/.config/systemmonitor/overlay")


def load_overlay_pref():
    """Husk om overlayet var på eller av sist (standard: på)."""
    return read(PREF_FILE, "on") != "off"


def save_overlay_pref(on):
    try:
        os.makedirs(os.path.dirname(PREF_FILE), exist_ok=True)
        with open(PREF_FILE, "w") as f:
            f.write("on" if on else "off")
    except OSError:
        pass


def overlay_env_active():
    """True hvis MangoHud er slått på for innloggingsøkten."""
    return os.environ.get("MANGOHUD") == "1"


def ensure_overlay_env():
    """Slå på MangoHud for alle Vulkan-spill (gjelder fra neste innlogging)."""
    if os.path.exists(MANGOHUD_ENV):
        return False
    os.makedirs(os.path.dirname(MANGOHUD_ENV), exist_ok=True)
    with open(MANGOHUD_ENV, "w") as f:
        f.write("# Lagt til av Kontrollsenter: laster MangoHud i Vulkan-spill.\n"
                "# Overlayet er skjult unntatt når Kontrollsenter kjører.\n"
                "MANGOHUD=1\n")
    return True


def install_app_icon():
    """Legg programikonet i ikontemaet (~/.local/share/icons), så menyen, statusfeltet og varslene viser det."""
    dst_dir = os.path.expanduser("~/.local/share/icons/hicolor/scalable/apps")
    changed = False
    for name in (APP_ICON, APP_ICON + "-symbolic"):          # logo + ensfarget ikon til statusfeltet
        src = os.path.join(APP_DIR, "icons", name + ".svg")
        dst = os.path.join(dst_dir, name + ".svg")
        try:
            if os.path.exists(src) and (not os.path.exists(dst) or
                                        open(src, "rb").read() != open(dst, "rb").read()):
                os.makedirs(dst_dir, exist_ok=True)
                shutil.copy2(src, dst)
                changed = True
        except OSError:
            pass
    if changed:                                              # så menyen og panelet ser det nye ikonet
        for cmd in (["gtk-update-icon-cache", "-qtf", os.path.dirname(os.path.dirname(os.path.dirname(dst_dir)))],
                    ["kbuildsycoca6", "--noincremental"]):
            if shutil.which(cmd[0]):
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def accent_rgb():
    """Systemets aksentfarge (KDE/GNOME), ellers blå."""
    try:
        c = Adw.StyleManager.get_default().get_accent_color_rgba()
        return (c.red, c.green, c.blue)
    except (AttributeError, TypeError):
        return BLUE


_VISITS = os.path.expanduser("~/.config/systemmonitor/sidebesok.json")


def _visits_load():
    try:
        return json.load(open(_VISITS))
    except (OSError, ValueError):
        return {}


def _visits_add(name):
    """Tell hvilke sider du bruker (lagres sjelden), så de mest brukte kan bygges på forhånd."""
    if not name:
        return
    v = _VC.setdefault("v", None) or _visits_load()
    v[name] = v.get(name, 0) + 1
    _VC["v"] = v
    _VC["n"] = _VC.get("n", 0) + 1
    if _VC["n"] % 10 == 0:
        try:
            os.makedirs(os.path.dirname(_VISITS), exist_ok=True)
            with open(_VISITS + ".tmp", "w") as f:
                json.dump(v, f)
            os.replace(_VISITS + ".tmp", _VISITS)
        except OSError:
            pass


_VC = {}


class MonitorWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        try:                                             # rydd etter forrige utgave (zombier, gamle overlay) + diskvakt
            import housekeeping
            housekeeping.start()
        except Exception:  # noqa: BLE001
            pass
        super().__init__(application=app, title="Kontrollsenter")
        geo = _monitor_geometry()
        if geo and geo.height >= 900:
            h = int(geo.height * 0.88)
            w = int(min(geo.width * 0.7, h * 1.45))
            self.set_default_size(w, h)
        else:
            self.set_default_size(1000, 760)
            self.maximize()
        self.add_css_class("sysmon")
        import theme as ks_theme
        ks_theme.load()
        if ks_theme.glass_on():
            self.add_css_class("ks-glass")
        try:                                             # Klassisk eller nytt design (Innstillinger › Utseende)
            import design
            design.apply(self)
        except Exception:  # noqa: BLE001
            applog.log.exception("design")
        if not os.environ.get("SYSTEMMONITOR_APP_ID"):   # Hyprland/GNOME: vinduer, oppstart, statusfelt (desktop.py)
            try:
                import desktop
                GLib.idle_add(lambda: (desktop.setup(self), False)[1])
            except Exception:  # noqa: BLE001
                applog.log.exception("skrivebord")
        try:                                             # tid på døgnet, spilltema, levende bakgrunn
            import looks
            GLib.idle_add(lambda: looks.start(self) and False)
            import smartauto
            GLib.idle_add(lambda: smartauto.start() and False)
            import wheel                                 # rullehjul i alle valgmenyer
            GLib.idle_add(lambda: wheel.install(self) and False)
        except Exception:  # noqa: BLE001
            applog.log.exception("temaer")
        try:                                             # lys som følger musa på knappene
            import spotlight
            spotlight.attach(self)
            import effects
            effects.apply(self)
            import scrollguard                                 # musehjulet over glidere ruller siden
            scrollguard.install(self)
            self._last_input = _time_mod.monotonic()          # brukes til å oppdatere sjeldnere når du ikke er her
            for ctl in (Gtk.EventControllerMotion(), Gtk.EventControllerKey()):
                ctl.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
                ctl.connect("motion" if isinstance(ctl, Gtk.EventControllerMotion) else "key-pressed",
                            lambda *_a: setattr(self, "_last_input", _time_mod.monotonic()) and False)
                self.add_controller(ctl)
            import perf
            if perf.lowend():                            # «Eldre PC»: animasjoner av fra start
                perf.apply_graphics(self)
        except Exception:  # noqa: BLE001
            pass
        icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        icon_theme.add_search_path(os.path.join(APP_DIR, "icons", "symbolic"))   # enhetlige ensfargede ikoner
        icon_theme.add_search_path(os.path.join(APP_DIR, "icons"))               # programikonet
        Gtk.Window.set_default_icon_name(APP_ICON)
        install_app_icon()
        self._font_css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), self._font_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
        settings_font = Gtk.Settings.get_default().get_property("gtk-font-name") or "Sans 10"
        try:
            self._base_pt = float(settings_font.split()[-1])
        except ValueError:
            self._base_pt = 10.0
        self._last_size = (0, 0)
        self._rescale(*self.get_default_size())
        GLib.timeout_add(400, self._watch_size)

        self.cpu = CpuReader()
        self.disk = DiskReader()
        self.net = NetReader()
        self.nvidia = NvidiaReader()
        self.amd = amd_gpus()
        self.nvidia.poll()

        toolbar = Adw.ToolbarView()             # innholdet (høyre side)
        header = Adw.HeaderBar()
        self.uptime_lbl = Gtk.Label()                    # beholdes for eldre kode – vises i undertittelen
        self.page_title = Adw.WindowTitle(title=i18n.tr("Oversikt"))
        header.set_title_widget(self.page_title)
        toolbar.add_css_class("ks-content")
        self.batteries = laptop_batteries()
        self.bat_lbl = Gtk.Label()
        self.bat_lbl.add_css_class("dim-label")
        self.bat_lbl.set_visible(bool(self.batteries))
        header.pack_start(self.bat_lbl)
        # Spill-overlay: lite ikon som lyser når det er på
        self.ov_button = Gtk.ToggleButton(icon_name="ks-overlay-symbolic", valign=Gtk.Align.CENTER)
        self.ov_button.connect("toggled", self._on_overlay_toggled)
        header.pack_end(self.ov_button)
        self.ov_button.set_visible(not IS_WIN)          # MangoHud finnes ikke på Windows

        # Meny: Systemsjekk, Hva er nytt?, Språk og Om
        self._menu_actions()
        menu = Gio.Menu()
        sec = Gio.Menu()
        sec.append(i18n.tr("Systemsjekk …"), "win.syscheck")
        sec.append(i18n.tr("Mini-vindu"), "win.mini")
        sec.append(i18n.tr("Stue-modus (F11)"), "win.ambient")
        sec.append(i18n.tr("Innstillinger"), "win.settings")
        sec.append(i18n.tr("Funksjoner …"), "win.features")
        menu.append_section(None, sec)
        sec = Gio.Menu()
        sec.append(i18n.tr("Hva er nytt?"), "win.whatsnew")
        sec.append(i18n.tr("Velkomstveiviser"), "win.welcome")
        menu.append_section(None, sec)
        lang = Gio.Menu()
        for code, _short, full in i18n.LANGS:
            item = Gio.MenuItem.new(i18n.tr("Automatisk (som Linux)" if code == "auto" else full), None)
            item.set_action_and_target_value("win.lang", GLib.Variant("s", code))
            lang.append_item(item)
        menu.append_submenu(i18n.tr("Språk"), lang)
        about = Gio.Menu()
        about.append(i18n.tr("Om Kontrollsenter"), "win.about")
        menu.append_section(None, about)
        self.menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, primary=True)
        self.menu_btn.set_tooltip_text("Meny")
        self.ov_button.set_active(load_overlay_pref())
        self._on_overlay_toggled(self.ov_button)
        # Bakgrunnsmodus: lukking skjuler vinduet (må kobles til før de andre lukke-handlingene)
        self.connect("close-request", lambda *_: bool(getattr(self, "bg", None) and self.bg.on_close()))
        self.connect("close-request", lambda *_: set_overlay(False) or False)
        # Skjul overlayet også om programmet avsluttes på annen måte
        import atexit
        import signal
        def _cleanup(*_):
            set_overlay(False)
            if getattr(self, "power", None):
                self.power.flush_peaks()
            if getattr(self, "fans", None):
                self.fans.all_auto_now()
            if getattr(self, "energy", None):
                self.energy.save()
            try:                                          # vanlig avslutning – ikke et krasj
                import crashlog
                crashlog.pulse(self, clean=True)
            except Exception:  # noqa: BLE001
                pass

        atexit.register(_cleanup)
        signal.signal(signal.SIGTERM, lambda *_: (_cleanup(), os._exit(0)))
        toolbar.add_top_bar(header)
        # (Copyright og versjon ligger nå i Meny → Om Kontrollsenter)

        # Ny versjon installert mens programmet kjørte (f.eks. i bakgrunnen) → tilby omstart
        self.restart_banner = Adw.Banner(button_label=i18n.tr("Start på nytt"), revealed=False)
        self.restart_banner.connect("button-clicked", self.restart_app)
        toolbar.add_top_bar(self.restart_banner)
        GLib.timeout_add_seconds(60, self.check_installed_version)

        if not IS_WIN and (ensure_overlay_env() or not overlay_env_active()):
            banner = Adw.Banner(
                title="Spill-overlay er satt opp. Logg ut og inn igjen én gang for at det skal virke i spill.",
                revealed=True,
            )
            toolbar.add_top_bar(banner)

        import dashboard
        flow = dashboard.Dash("oversikt", max_cols=4, min_col=240)

        self.c_bat = Card("Batteri", [GREEN]) if self.batteries else None
        self.c_cpu = Card(cpu_model(), [accent_rgb()])          # følger systemets aksentfarge
        self.c_mem = Card("Minne (RAM)", [GREEN])
        self.c_gpu = Card("GPU", [ORANGE]) if self.nvidia.available else None
        self.c_amd = [Card("AMD GPU", [RED]) for _ in self.amd]
        self.c_disk = Card("Disk", [PURPLE, TEAL], fixed_max=None, legend=["Les", "Skriv"], fmt=fmt_rate)
        self.c_net = Card("Nettverk", [GREEN, BLUE], fixed_max=None, legend=["Ned", "Opp"], fmt=fmt_rate)
        self.c_temp = Card("Temperaturer")

        # Per-kjerne-stolper i CPU-kortet
        self.core_bars = []
        cores = sorted(
            (k for k in self.cpu.prev if k != "cpu"), key=lambda k: int(k[3:])
        )
        grid = Gtk.Grid(column_spacing=4, row_spacing=3, column_homogeneous=True)
        cols = 8 if len(cores) > 8 else max(len(cores), 1)
        for i, k in enumerate(cores):
            bar = Gtk.LevelBar(min_value=0, max_value=100)
            bar.set_size_request(-1, 6)
            bar.set_tooltip_text(f"Kjerne {i}")
            grid.attach(bar, i % cols, i // cols, 1, 1)
            self.core_bars.append((k, bar))
        self.c_cpu.inner.insert_child_after(grid, self.c_cpu.graph)

        # Temperaturliste
        self.temp_grid = Gtk.Grid(column_spacing=12, row_spacing=4, column_homogeneous=False)
        self.c_temp.inner.insert_child_after(self.temp_grid, self.c_temp.subtitle)
        self.temp_rows = {}

        cards = ([("bat", self.c_bat)] if self.c_bat else []) + [("cpu", self.c_cpu), ("mem", self.c_mem)]
        if self.c_gpu:
            cards.append(("gpu", self.c_gpu))
        cards += [(f"amd{i}", c) for i, c in enumerate(self.c_amd)] + [("disk", self.c_disk), ("net", self.c_net)]
        self.dash = flow

        # Temperaturer i egen rad nederst, i to kolonner
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(page, f"set_margin_{side}")(12)
        self.power = PowerCard(self.nvidia.available)
        import confirm
        topbar = Gtk.Box(spacing=8)
        self.reset_lbl = Gtk.Label(xalign=1, hexpand=True)
        self.reset_lbl.add_css_class("dim-label")
        topbar.append(self.reset_lbl)
        self.reset_row = topbar
        topbar.append(confirm.reset_button(
            "Oversikt",
            "• Strømmodus settes til Balansert (skjermkort 320 W)\n"
            "• Alle vifter settes til Auto\n"
            "• Spill-overlay slås på\n"
            "• Målt toppfart for strømmodusene nullstilles",
            self._reset_overview))
        # Nøkkeltall øverst: CPU, GPU, strøm og strømmodus
        import power as power_mod
        self.meter = power_mod.PowerMeter()
        self.energy = power_mod.EnergyLog()
        power_mod._CURRENT[:] = [self.energy]
        self._power = {"cpu": None, "gpu": None, "measured": None, "total": None}
        self._cpu_load = 0.0
        tiles = flow
        self.t_cpu = Tile("Prosessor", gauge=Gauge(100, 75, 88))
        self.t_gpu = Tile("Skjermkort", gauge=Gauge(100, 75, 85)) if self.nvidia.available or self.amd else None
        self.t_pow = Tile("Strømforbruk", icon="ks-power-symbolic")
        self.t_mode = Tile("Strømmodus", icon="ks-overview-symbolic")
        for key, t in (("cpu", self.t_cpu), ("gpu", self.t_gpu), ("watt", self.t_pow), ("mode", self.t_mode)):
            if t:
                tiles.add("flis-" + key, t, 1, on_click=lambda k=key: self.open_details(k))
        # nye fliser: ping, nedlasting, spilletid i dag, strømpris nå, vær og neste avtale
        self.t_ping = Tile("Ping", icon="ks-network-symbolic")
        self.t_down = Tile("Nedlasting", icon="ks-network-symbolic")
        self.t_play = Tile("Spilletid i dag", icon="ks-games-symbolic")
        self.t_price = Tile("Strømpris nå", icon="ks-power-symbolic")
        self.t_weather = Tile("Været", icon="ks-overview-symbolic")
        self.t_cal = Tile("Neste avtale", icon="ks-history-symbolic")
        self.t_today = Tile("Dagen i dag", icon="ks-overview-symbolic")
        self.t_today.value.set_ellipsize(0)
        self.t_today.sub.set_wrap(True)
        for key, t, click, hid in (
                ("ping", self.t_ping, lambda: self.open_details("net"), False),
                ("down", self.t_down, lambda: self.open_details("net"), True),
                ("play", self.t_play, lambda: self.stack.set_visible_child_name("spill"), False),
                ("price", self.t_price, lambda: self.open_details("watt"), False),
                ("weather", self.t_weather, self._open_info_settings, False),
                ("cal", self.t_cal, self._show_calendar, True)):
            tiles.add("flis-" + key, t, 1, on_click=click, hidden=hid)
        tiles.add("flis-today", self.t_today, 2, on_click=lambda: self.stack.set_visible_child_name("spill"))
        GLib.timeout_add_seconds(3, lambda: (self._update_today(), False)[1])
        GLib.timeout_add_seconds(60, lambda: (self.get_mapped() and self._update_today(), True)[1])
        try:
            import details as _det
            import infotiles as _it
            self.t_cpu.add_spark(self.c_cpu.graph.series[0], top=100)
            if self.t_gpu and self.c_gpu:
                self.t_gpu.add_spark(self.c_gpu.graph.series[0], top=100)
            self.t_pow.add_spark(_det.HIST["watt"], top=None)
            self.t_ping.add_spark(_it._PINGS, top=None)
            self.t_down.add_spark(self.c_net.graph.series[0], top=None)
        except Exception:  # noqa: BLE001
            applog.log.exception("minigrafer")
        tiles.titles = {"flis-cpu": "Prosessor", "flis-gpu": "Skjermkort", "flis-watt": "Strømforbruk",
                        "flis-mode": "Strømmodus", "flis-ping": "Ping", "flis-down": "Nedlasting",
                        "flis-play": "Spilletid i dag", "flis-price": "Strømpris nå", "flis-weather": "Været",
                        "flis-cal": "Neste avtale", "flis-today": "Dagen i dag", "batterier": "Batterier", "strommodus": "Strømmodus (kort)",
                        "vifter": "Vifter", "cpu": "CPU-graf", "mem": "Minne", "gpu": "GPU-graf", "disk": "Disk",
                        "net": "Nettverk", "space": "Diskplass", "temps": "Temperaturer", "bat": "Batteri"}
        # hilsenen og knappene brytes til to linjer i smale vinduer (før krevde raden over 1000 px)
        hero = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, min_children_per_line=1, max_children_per_line=2,
                           column_spacing=16, row_spacing=6, homogeneous=False)
        hero.set_margin_top(6)
        hero.set_margin_bottom(4)
        hcol = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        self.hello = Gtk.Label(xalign=0, ellipsize=3)
        self.hello.add_css_class("ks-hello")
        hcol.append(self.hello)
        self.hello_sub = Gtk.Label(xalign=0, wrap=True)
        self.hello_sub.add_css_class("ks-hello-sub")
        hcol.append(self.hello_sub)
        hero.append(hcol)
        hero_r = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, min_children_per_line=1, max_children_per_line=8,
                             column_spacing=8, row_spacing=6, homogeneous=False, halign=Gtk.Align.END,
                             valign=Gtk.Align.CENTER)
        hero.append(hero_r)
        self.hello_chip = Gtk.Label(valign=Gtk.Align.CENTER)
        self.hello_chip.add_css_class("ks-chip")
        hero_r.append(self.hello_chip)
        try:
            import assistant_ui
            hero_r.append(assistant_ui.quick_button(self))
        except Exception:  # noqa: BLE001
            applog.log.exception("assistent-knapp")
        import dashboard as _db
        self.presets = ["standard", "spill", "jobb", "natt"]
        self.preset_dd = Gtk.DropDown.new_from_strings([i18n.tr(x) for x in ("Standard", "Spill", "Jobb", "Natt")])
        self.preset_dd.set_valign(Gtk.Align.CENTER)
        self.preset_dd.set_tooltip_text(i18n.tr("Oppsett av Oversikt – hvert oppsett husker sine egne fliser, "
                                                "rekkefølge og størrelser. «Spill» velges av seg selv når et spill starter."))
        cur_p = _db._load().get("_preset:oversikt", "standard")
        self.preset_dd.set_selected(self.presets.index(cur_p) if cur_p in self.presets else 0)
        self.preset_dd.connect("notify::selected", lambda d, _p: self.dash.set_preset(self.presets[d.get_selected()]))
        hero_r.append(self.preset_dd)
        self.edit_btn = Gtk.ToggleButton(icon_name="view-grid-symbolic", valign=Gtk.Align.CENTER)
        self.edit_btn.set_tooltip_text(i18n.tr("Tilpass oversikten: dra flisene til nye plasser og velg størrelse"))
        self.edit_btn.add_css_class("circular")
        self.edit_btn.connect("toggled", self._on_edit_dash)
        hero_r.append(self.edit_btn)
        self.edit_bar = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN)
        eb = Gtk.Box(spacing=10)
        eb.add_css_class("card")
        for side in ("top", "bottom", "start", "end"):
            getattr(eb, f"set_margin_{side}")(0)
        ebl = Gtk.Label(label=i18n.tr("Dra flisene og kortene dit du vil ha dem. S, M og L i hjørnet endrer "
                                      "størrelsen. Høyreklikk virker også."), xalign=0, wrap=True, hexpand=True)
        for side in ("top", "bottom", "start"):
            getattr(ebl, f"set_margin_{side}")(10)
        eb.append(ebl)
        self.hidden_btn = Gtk.MenuButton(label=i18n.tr("Vis skjulte"), valign=Gtk.Align.CENTER)
        self.hidden_btn.set_popover(Gtk.Popover())
        self.hidden_btn.get_popover().connect("show", lambda p: self._fill_hidden(p))
        eb.append(self.hidden_btn)
        rb = Gtk.Button(label=i18n.tr("Tilbakestill"), valign=Gtk.Align.CENTER)
        rb.connect("clicked", lambda *_: self.dash.reset())
        eb.append(rb)
        db = Gtk.Button(label=i18n.tr("Ferdig"), valign=Gtk.Align.CENTER)
        db.set_margin_end(10)
        db.connect("clicked", lambda *_: self.edit_btn.set_active(False))
        eb.append(db)
        self.edit_bar.set_child(eb)
        page.append(hero)
        page.append(self.edit_bar)
        try:                                  # «Oppdater alt» og automatikk av/på
            import updates_ui
            page.append(updates_ui.OverviewBar(self))
        except Exception:  # noqa: BLE001
            applog.log.exception("oppdateringslinje")
        try:                                  # batteri i mus, tastatur og hodesett
            import battery_ui
            flow.add("batterier", battery_ui.BatteryCard(), 9, on_click=lambda: self.open_details("bat"))
        except Exception:  # noqa: BLE001
            pass
        flow.add("strommodus", self.power, 9, on_click=lambda: self.open_details("mode"))
        self.fans = FanCard(self.nvidia.available)
        flow.add("vifter", self.fans, 9, on_click=lambda: self.open_details("fans"))
        # (Windows: viftene styres via LibreHardwareMonitor)
        self.connect("close-request", lambda *_: self.fans.all_auto_now() or False)
        # Tidsrom for grafene: 1 min, 10 min eller 1 time (hold musa over en graf for verdi og tid)
        rng = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)
        seg = Gtk.Box(valign=Gtk.Align.CENTER)
        seg.set_tooltip_text(i18n.tr("Hvor langt tilbake grafene viser"))
        seg.add_css_class("linked")
        first = None
        for secs, text in ((60, "1 min"), (600, "10 min"), (3600, "1 time")):
            b = Gtk.ToggleButton(label=text, active=(secs == GRAPH_WINDOW[0]))
            if first:
                b.set_group(first)
            first = first or b
            b.connect("toggled", self._on_range, secs)
            seg.append(b)
        rng.append(seg)
        hero_r.insert(rng, 1)                                   # 1 min / 10 min / 1 time etter statusen
        for key, c in cards:
            flow.add(key, c, 2, on_click=lambda k=key: self.open_details("gpu" if k.startswith("amd") else k))
        page.append(flow)
        self.diskspace = DiskSpaceCard()
        flow.add("space", self.diskspace, 9, on_click=lambda: self.open_details("disk"))
        flow.add("temps", self.c_temp, 9, on_click=lambda: self.open_details("temps"))
        flow.finish()
        flow.on_edit_request = lambda: self.edit_btn.set_active(not self.edit_btn.get_active())
        page.append(topbar)                   # Tilbakestill nederst – sjelden brukt

        import theme as _th
        _th.add_css(CSS.decode())                      # følger temaet (fargene byttes når du velger et annet)

        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.set_child(Adw.Clamp(maximum_size=MAX_WIDTH, tightening_threshold=900, child=page))

        # Faner: Oversikt og RGB
        stack = Adw.ViewStack()
        import hardware
        self.hw = hardware.present()          # RGB, Logitech, CPU-skjerm, Wi-Fi og Bluetooth vises bare hvis de finnes
        stack.add_titled_with_icon(scroller, "oversikt", "Oversikt", "ks-overview-symbolic")
        self.rgb_holder = Gtk.Box()
        if self.hw["rgb"]:
            stack.add_titled_with_icon(self.rgb_holder, "rgb", "RGB", "ks-rgb-symbolic")
        self.logi_holder = Gtk.Box()
        if self.hw["logitech"]:
            stack.add_titled_with_icon(self.logi_holder, "logitech", "Logitech", "ks-mouse-symbolic")
        self.logi_page = None
        self.lcd_holder = Gtk.Box()
        if self.hw["lcd"]:
            stack.add_titled_with_icon(self.lcd_holder, "cpuskjerm", "CPU-skjerm", "ks-lcd-symbolic")
        self.lcd_page = None
        self.prog_holder = Gtk.Box()
        stack.add_titled_with_icon(self.prog_holder, "programmer", "Programmer", "ks-programs-symbolic")
        self.prog_page = None
        self.audio_holder = Gtk.Box()
        stack.add_titled_with_icon(self.audio_holder, "lyd", "Lyd", "ks-sound-symbolic")
        self.audio_page = None
        self.wifi_holder = Gtk.Box()
        if self.hw["wifi"]:
            stack.add_titled_with_icon(self.wifi_holder, "wifi", "Wi-Fi", "ks-wifi-symbolic")
        self.wifi_page = None
        # Faner som lastes først når de åpnes: navn -> (holder, modul, klasse)
        self._lazy = {}
        for name, title, icon, mod, cls in (
                ("finn", "Finn alt", "system-search-symbolic", "finnalt", "FindAllPage"),
                ("historikk", "Historikk", "ks-history-symbolic", "history", "HistoryPage"),
                ("gpu", "GPU-innstillinger", "ks-gpu-symbolic", "gpu_page", "GpuPage"),
                ("bluetooth", "Bluetooth", "ks-bluetooth-symbolic", "bluetooth", "BluetoothPage"),
                ("nettverk", "Nettverk", "ks-network-symbolic", "netpage", "NetworkPage"),
                ("spill", "Spill", "ks-games-symbolic", "games", "GamesPage"),
                ("vr", "VR", "ks-vr-symbolic", "vr_ui", "VrPage"),
                ("stromming", "Strømming", "ks-stream-symbolic", "streaming_ui", "StreamingPage"),
                ("discord", "Discord", "ks-discord-symbolic", "discord_ui", "DiscordPage"),
                ("familie", "Familie", "ks-family-symbolic", "family_page", "FamilyPage"),
                ("kalender", "Kalender", "ks-calendar-symbolic", "kalender_ui", "CalendarPage"),
                ("tester", "Tester", "ks-test-symbolic", "tester_ui", "TesterPage"),
                ("smarthjem", "Smart Hjem", "ks-smarthome-symbolic", "smarthome_ui", "SmartHomePage"),
                ("scener", "Scener", "ks-scenes-symbolic", "scenes_ui", "ScenesPage"),
                ("hjemme", "PC-er hjemme", "ks-home-symbolic", "homepcs", "HomePage"),
                ("venner", "PC-er utenfor hjemmet", "ks-friends-symbolic", "friends_ui", "FriendsPage"),
                ("chat", "Chat", "ks-chat-symbolic", "chat_ui", "ChatPage"),
                ("fjernhjelp", "Fjernhjelp", "ks-remote-symbolic", "remotehelp_ui", "RemoteHelpPage"),
                ("ai", "AI", "ks-ai-symbolic", "ai_ui", "AiPage"),
                ("verktoy", "Vedlikehold", "ks-tools-symbolic", "tools", "ToolsPage"),
                ("innstillinger", "Innstillinger", "ks-settings-symbolic", "tools", "SettingsPage")):
            if name == "bluetooth" and not self.hw["bluetooth"]:
                continue
            if os.path.exists(os.path.join(APP_DIR, mod + ".py")):
                holder = Gtk.Box()
                stack.add_titled_with_icon(holder, name, title, icon)
                self._lazy[name] = [holder, mod, cls, None]
        if IS_WIN and "bluetooth" in self._lazy:
            self._lazy["bluetooth"][1:3] = ["win_pages", "BluetoothWinPage"]
        self.msi_page = None
        import msi
        if msi.is_msi():                      # MSI-fanen vises bare på MSI-maskiner
            self.msi_holder = Gtk.Box()
            stack.add_titled_with_icon(self.msi_holder, "msi", "MSI", "ks-laptop-symbolic")
        self.stack = stack
        try:                                                     # overgang ved sidebytte (Utseende › Overganger)
            import effects
            effects.apply(self)
        except Exception:  # noqa: BLE001
            pass
        stack.connect("notify::visible-child-name", self._on_tab)
        stack.connect("notify::visible-child-name", self._sync_sidebar)

        def _fx(s, _p):
            try:
                import effects
                effects.page_enter(s.get_visible_child())
            except Exception:  # noqa: BLE001
                pass
        stack.connect("notify::visible-child-name", _fx)
        stack.connect("notify::visible-child-name", lambda st, _p: _visits_add(st.get_visible_child_name()))
        GLib.timeout_add_seconds(20, self._prebuild)               # bygg de mest brukte sidene på forhånd
        import progress_ui
        self.toast_overlay = Adw.ToastOverlay(child=progress_ui.attach(stack))
        self.page_help = Gtk.Label(xalign=0, wrap=True)
        self.page_help.add_css_class("ks-pagehelp")
        for side, v in (("start", 18), ("end", 18), ("top", 4), ("bottom", 8)):
            getattr(self.page_help, f"set_margin_{side}")(v)
        self.page_help_clamp = Adw.Clamp(maximum_size=MAX_WIDTH, child=self.page_help, visible=False)
        toolbar.add_top_bar(self.page_help_clamp)
        self.group_clamp = Adw.Clamp(maximum_size=MAX_WIDTH, visible=False)
        for side, v in (("start", 14), ("end", 14)):
            getattr(self.group_clamp, f"set_margin_{side}")(v)
        toolbar.add_top_bar(self.group_clamp)
        self._group_bar = None
        toolbar.set_content(self.toast_overlay)
        self.content_page = Adw.NavigationPage(title=i18n.tr("Oversikt"), child=toolbar)

        # Sidemenyen: én rad per fane, med ensfarget ikon
        self.sidebar = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.sidebar.add_css_class("navigation-sidebar")
        self.sidebar.add_css_class("ks-sidebar")
        import theme as ks_theme
        self._rows = {}
        pages = stack.get_pages()
        order = ks_theme.ORDER
        all_pages = [pages.get_item(i) for i in range(pages.get_n_items())]
        all_pages.sort(key=lambda p: order.index(p.get_name()) if p.get_name() in order else 99)
        for pg in all_pages:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(spacing=12)
            for side in ("top", "bottom"):
                getattr(box, f"set_margin_{side}")(6)
            box.set_margin_start(6)
            box.append(Gtk.Image(icon_name=pg.get_icon_name()))
            tl = Gtk.Label(label=pg.get_title(), xalign=0, hexpand=True)
            tl.add_css_class("ks-row-title")
            box.append(tl)
            badge = Gtk.Label(xalign=1)
            badge.add_css_class("dim-label")
            badge.add_css_class("numeric")
            badge.add_css_class("sidebar-badge")
            badge.set_margin_end(6)
            badge.set_visible(False)
            box.append(badge)
            self._badges = getattr(self, "_badges", {})
            self._badges[pg.get_name()] = badge
            row.set_child(box)
            row.page_name = pg.get_name()
            if ks_theme.PAGE_HELP.get(pg.get_name()):
                row.set_tooltip_text(i18n.tr(ks_theme.PAGE_HELP[pg.get_name()]))
            self.sidebar.append(row)
            self._rows[pg.get_name()] = row
        self.sidebar.connect("row-activated", self._on_sidebar)

        import design as ks_design

        def section_header(row, before):
            if ks_design.is_new():                     # nytt design: 7 områder, ingen seksjonsoverskrifter
                row.set_header(None)
                return
            sec = ks_theme.SECTION_OF.get(row.page_name)
            prev = ks_theme.SECTION_OF.get(before.page_name) if before else None
            if sec and sec != prev:
                lab = Gtk.Label(label=i18n.tr(sec).upper(), xalign=0)
                lab.add_css_class("ks-section")
                if before is None:
                    lab.add_css_class("first")
                row.set_header(lab)
            else:
                row.set_header(None)
        self.sidebar.set_header_func(section_header)
        self._setup_groups()
        self.sidebar.set_filter_func(self._row_visible)
        side_tv = Adw.ToolbarView()
        side_tv.add_css_class("ks-side")
        side_header = Adw.HeaderBar(show_title=True, show_start_title_buttons=False)
        brand = Gtk.Box(spacing=10, halign=Gtk.Align.START)
        logo = Gtk.Image(icon_name="ks-overview-symbolic", pixel_size=16, valign=Gtk.Align.CENTER,
                         halign=Gtk.Align.CENTER)
        logo.add_css_class("ks-brand-logo")
        brand.append(logo)
        bcol = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        bt = Gtk.Label(label="Kontrollsenter", xalign=0)
        bt.add_css_class("ks-brand-title")
        bcol.append(bt)
        try:
            import savegames
            pcn = savegames.pc_name()
        except Exception:  # noqa: BLE001
            pcn = ""
        self.brand_sub = Gtk.Label(label=pcn, xalign=0)
        self.brand_sub.add_css_class("ks-brand-sub")
        bcol.append(self.brand_sub)
        brand.append(bcol)
        side_header.set_title_widget(brand)
        side_header.pack_end(self.menu_btn)
        sbtn = Gtk.Button(icon_name="system-search-symbolic", tooltip_text=i18n.tr("Søk (Ctrl+K)"))
        sbtn.add_css_class("flat")
        sbtn.connect("clicked", self.open_search)
        side_header.pack_end(sbtn)
        side_tv.add_top_bar(side_header)
        if ks_design.is_new():                         # «Finn alt» er et søkefelt øverst i menyen
            self.side_search = Gtk.SearchEntry(placeholder_text=i18n.tr("Finn alt …"))
            self.side_search.add_css_class("ks-side-search")
            self.side_search.connect("search-changed", self._side_search)
            self.side_search.connect("activate", lambda e: self._side_search(e, go_first=True))
            side_tv.add_top_bar(self.side_search)
        side_tv.set_content(Gtk.ScrolledWindow(child=self.sidebar, hscrollbar_policy=Gtk.PolicyType.NEVER,
                                               vexpand=True))
        # livestatus nederst: CPU, GPU og watt
        pulse = Gtk.Box(homogeneous=True)
        pulse.add_css_class("ks-pulse")
        self._pulse = {}
        for key, name in (("cpu", "CPU"), ("gpu", "GPU"), ("w", "WATT")):
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            v = Gtk.Label(label="–")
            v.add_css_class("ks-pulse-value")
            v.add_css_class("numeric")
            lab = Gtk.Label(label=name)
            lab.add_css_class("ks-pulse-label")
            col.append(v)
            col.append(lab)
            pulse.append(col)
            self._pulse[key] = v
        side_tv.add_bottom_bar(pulse)
        side_page = Adw.NavigationPage(title=i18n.tr("Kontrollsenter"), child=side_tv)
        self.split = Adw.NavigationSplitView(sidebar=side_page, content=self.content_page,
                                             min_sidebar_width=210, max_sidebar_width=250)
        # Smalt vindu: sidemenyen legger seg bort, og du går frem og tilbake mellom meny og side
        bp = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 760sp"))
        bp.add_setter(self.split, "collapsed", True)
        self.add_breakpoint(bp)
        self._sync_sidebar()
        if os.environ.get("SYSTEMMONITOR_START_TAB"):          # åpne en bestemt fane
            GLib.idle_add(lambda: (stack.set_visible_child_name(os.environ["SYSTEMMONITOR_START_TAB"]), False)[1])
        self.rgb_page = None
        self.set_content(self.split)
        # RGB: legg inn de lagrede fargene ved oppstart og etter hvilemodus – OpenRGB husker dem ikke selv
        if not os.environ.get("SYSTEMMONITOR_APP_ID"):            # lagrede GPU-innstillinger (valgfritt)
            import threading as _th
            GLib.timeout_add_seconds(15, lambda: (_th.Thread(target=__import__("gpu").apply_saved, daemon=True).start(),
                                                  False)[1])
        if not os.environ.get("SYSTEMMONITOR_APP_ID"):            # engangsinnloggingen etter omstart: fjern den
            threading.Thread(target=lambda: __import__("autologin").disarm(), daemon=True).start()
        if not os.environ.get("SYSTEMMONITOR_APP_ID"):            # skrivebordswidgetene som var på sist
            GLib.timeout_add_seconds(4, lambda: __import__("desk_widgets").restore(self))
        if self.hw.get("rgb") and not os.environ.get("SYSTEMMONITOR_APP_ID"):
            GLib.timeout_add_seconds(12, lambda: (GLib.timeout_add_seconds(5, self._rgb_when_ready)
                                                  if self._rgb_when_ready() else None, False)[1])
            self._watch_sleep()

        self.update()
        GLib.timeout_add(INTERVAL_MS, self.update)

    # ------------------------------------------------------------------
    def _reset_overview(self):
        p = self.power
        if p.active_profile() == "balanced":
            p._gpu_mode_applied = None
            p._apply_gpu("balanced")
        elif "balanced" in p.buttons:
            p.buttons["balanced"].set_active(True)
        self.fans.apply_all("auto")
        self.ov_button.set_active(True)
        self._on_overlay_toggled(self.ov_button)
        p.peaks = {}
        p._peaks_dirty = True
        p.flush_peaks()
        p.update_specs()
        self.toast("Tilbakestilt til fabrikkstandard ✓")

    def _watch_size(self):
        w, h = self.get_width(), self.get_height()
        if w > 0 and h > 0 and (w, h) != self._last_size:
            self._rescale(w, h)
        return True

    def _rescale(self, w, h):
        """Tekst og grafer følger vindusstørrelsen (og dermed skjermoppløsningen)."""
        self._last_size = (w, h)
        f = max(0.9, min(1.6, min(w / 1300, h / 950)))
        if abs(f - UI_SCALE[0]) < 0.04:
            return
        UI_SCALE[0] = f
        self._font_css.load_from_string(f"window.sysmon {{ font-size: {self._base_pt * f:.1f}pt; }}")
        for g in GRAPHS:
            if isinstance(g, Gauge):
                g.set_content_width(round(92 * f))
                g.set_content_height(round(92 * f))
            else:
                g.set_content_height(round(80 * f))

    def _set_lang(self, code):
        if code == i18n.CHOICE:
            return
        i18n.set_lang(code)
        i18n.CHOICE = code
        if i18n.resolve(code) == i18n.LANG:       # samme språk som nå – bare lagre valget
            return
        self.toast("Programmet starter på nytt med nytt språk …")
        self.restart_app()

    def restart_app(self, *_, hidden=False):
        """Start programmet på nytt (ny versjon eller nytt språk). Vinduet kommer tilbake av seg selv
        – med hidden=True blir det i statusfeltet (stille omstart for å frigjøre minne)."""
        tray = ["--tray"] if hidden else []

        def restart():
            try:
                set_overlay(False)
                self.fans.all_auto_now()
                self.power.flush_peaks()
            except Exception:  # noqa: BLE001
                pass
            for fn in (lambda: self.energy.save(), lambda: self.bg.history.flush(),     # det som er samlet opp
                       lambda: self.bg.play.save() if getattr(self.bg, "play", None) else None,
                       lambda: __import__("winperf")._save_disk() if IS_WIN else None):
                try:
                    fn()
                except Exception:  # noqa: BLE001
                    pass
            extra = ["-X", "utf8"] if IS_WIN else []
            if IS_WIN:
                # os.execv på Windows starter den nye før den gamle er borte: den nye tror da at Kontrollsenter
                # allerede kjører og avslutter seg – og ingen vindu vises. Start ny prosess som venter på at
                # denne er ferdig, og avslutt så denne.
                exe = sys.executable
                pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
                if os.path.exists(pyw):
                    exe = pyw
                import subprocess as _sp
                _sp.Popen([exe, *extra, os.path.abspath(__file__), "--restarted", *tray],
                          creationflags=0x00000008 | 0x00000200, close_fds=True)   # DETACHED | NEW_PROCESS_GROUP
                os._exit(0)
            os.execv(sys.executable, [sys.executable, *extra, os.path.abspath(__file__), "--restarted", *tray])
        GLib.timeout_add(400, restart)

    def check_installed_version(self):
        """Kalles hvert minutt: er en nyere versjon installert mens programmet har kjørt?"""
        import applog
        new = applog.needs_restart()
        bg = getattr(self, "bg", None)
        if new and not self.get_visible() and not getattr(bg, "game_name", None) \
                and not os.environ.get("SYSTEMMONITOR_APP_ID"):
            self._idle_new = getattr(self, "_idle_new", 0) + 1
            if self._idle_new >= 2:                          # skjult i minst to minutter
                applog.log.info("Ny versjon %s er installert – starter på nytt i bakgrunnen", new)
                try:
                    import remote_extra
                    remote_extra.event("update", f"Kontrollsenter {new} er tatt i bruk", "Startet på nytt av seg selv",
                                       "info")
                except Exception:  # noqa: BLE001
                    pass
                self.restart_app()
                return True
        if new and not self.restart_banner.get_revealed():
            self.restart_banner.set_title(i18n.tr("Versjon {} er installert – start på nytt for å ta den i bruk")
                                          .replace("{}", new) if i18n.LANG != "no" else
                                          f"Versjon {new} er installert – start på nytt for å ta den i bruk")
            self.restart_banner.set_revealed(True)
            if getattr(self, "bg", None):
                self.bg.notify("restart", "Ny versjon av Kontrollsenter er installert",
                               f"Versjon {new} er klar. Klikk for å starte på nytt.", action="app.restart")
        return True

    def _open_syscheck(self, _btn=None):
        if IS_WIN:
            import wintools
            wintools.WinSysCheckDialog().present(self)
            return
        import syscheck
        syscheck.SysCheckDialog().present(self)

    def ensure_rgb_page(self):
        if self.rgb_page is None:
            import rgb
            self.rgb_page = rgb.RgbPage()
            self.rgb_page.set_hexpand(True)
            self.rgb_page.set_vexpand(True)
            self.rgb_holder.append(self.rgb_page)
            return True
        return False

    def _rgb_when_ready(self, tries=[0]):
        """Ved oppstart: vent (høyst ~2 min) til OpenRGB-tjenesten svarer før fargene sendes."""
        import socket
        tries[0] += 1
        try:
            with socket.create_connection(("127.0.0.1", 6742), timeout=0.5):
                pass
        except OSError:
            if tries[0] < 24 and not IS_WIN:
                return True                              # prøv igjen om 5 s
        GLib.timeout_add_seconds(2, lambda: (self.rgb_restore("oppstart"), False)[1])
        return False

    def rgb_restore(self, why=""):
        """Send de lagrede RGB-fargene til enhetene (oppretter RGB-siden i bakgrunnen ved behov)."""
        import funksjoner
        if not funksjoner.on("utstyr"):
            return False
        try:
            import rgb
            st = rgb.load_state()
            if not st.get("groups") or not st.get("autostart", True):
                return
            if not self.ensure_rgb_page():                    # ny side legger inn fargene av seg selv
                self.rgb_page.apply_all_now()
            import applog
            applog.log.info("RGB lagt inn på nytt (%s)", why)
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("RGB ved %s", why)

    def _watch_sleep(self):
        """logind sender PrepareForSleep(false) etter hvilemodus – også når et forsøk på hvile mislykkes.
        Da har USB-kontrollerne (ASUS Aura m.fl.) mistet fargene."""
        if IS_WIN:
            return
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)

            def on_sleep(_c, _s, _p, _i, _n, params):
                if not params.unpack()[0]:
                    GLib.timeout_add_seconds(4, lambda: (self.rgb_restore("etter hvilemodus"), False)[1])
            self._sleep_sub = bus.signal_subscribe("org.freedesktop.login1", "org.freedesktop.login1.Manager",
                                                   "PrepareForSleep", "/org/freedesktop/login1", None,
                                                   Gio.DBusSignalFlags.NONE, on_sleep)
            self._sleep_bus = bus
        except Exception:  # noqa: BLE001
            pass

    # --- grupper i sidemenyen (pagecats.GROUPS) ---
    def _setup_groups(self):
        import pagecats
        import design
        import funksjoner
        self._leader = {}                       # side -> lederens navn (den som vises i sidemenyen)
        new = design.is_new()
        for key, title, icon, members in (design.AREAS if new else pagecats.GROUPS):
            present = [m for m in members if m in self._rows]
            if new:                             # nytt design: også områder med én side, og lederen må være på
                present = [m for m in present if funksjoner.page_on(m)] or present
                if not present:
                    continue
            elif len(present) < 2:
                continue
            lead = present[0]
            for m in present:
                self._leader[m] = lead
            row = self._rows[lead]
            box = row.get_child()
            img = box.get_first_child()
            lab = img.get_next_sibling() if img is not None else None
            if isinstance(lab, Gtk.Label):
                lab.set_label(i18n.tr(title))
            if isinstance(img, Gtk.Image):
                img.set_from_icon_name(icon)
            row.group_key = key
            row.group_members = present
            row.set_tooltip_text(i18n.tr(title) + ": " + ", ".join(
                self.stack.get_page(self.stack.get_child_by_name(m)).get_title() for m in present))

    def _row_visible(self, row):
        import funksjoner
        if not funksjoner.page_on(row.page_name):           # funksjonen er slått av (veiviser/innstillinger)
            return False
        if self.simple_mode() and row.page_name not in self.SIMPLE_PAGES:
            return False
        if row.page_name == "finn":
            import design
            if design.is_new():                         # nytt design: søkefeltet øverst i menyen
                return False
        lead = getattr(self, "_leader", {}).get(row.page_name)
        return lead is None or lead == row.page_name

    def _update_group_bar(self, name):
        import pagecats
        lead = getattr(self, "_leader", {}).get(name)
        if not lead:
            self.group_clamp.set_visible(False)
            return
        row = self._rows[lead]
        members = row.group_members
        import design
        if design.is_new():
            import funksjoner
            members = [m for m in members if funksjoner.page_on(m)]
            if len(members) < 2:                       # område med én side: ingen faner
                self.group_clamp.set_visible(False)
                return
        if self._group_bar is None or getattr(self._group_bar, "_lead", None) != lead:
            if design.is_new():                        # nytt design: faner med ikon
                items = [(m, self.stack.get_page(self.stack.get_child_by_name(m)).get_title(),
                          self.stack.get_page(self.stack.get_child_by_name(m)).get_icon_name()) for m in members]
                self._group_bar = design.make_tabbar(items, name, lambda m: self.stack.set_visible_child_name(m))
            else:
                items = [(m, pagecats.ICONS.get(m, "") + "  " +
                          self.stack.get_page(self.stack.get_child_by_name(m)).get_title()) for m in members]
                self._group_bar = pagecats.CatBar(items, name, lambda m: self.stack.set_visible_child_name(m))
            self._group_bar._lead = lead
            self.group_clamp.set_child(self._group_bar)
        self._group_bar.select(name)
        self.group_clamp.set_visible(True)
        pagecats._save(**{"group:" + row.group_key: name})

    PREBUILD_DEFAULT = ["spill", "lyd", "innstillinger", "verktoy", "chat", "ai", "gpu", "familie", "kalender"]

    def _prebuild(self):
        """Mens du ikke bruker vinduet: bygg én side om gangen av de du bruker mest (opptil 6), så de åpnes med en
        gang. Ikke med «Minimal prosessbruk», og ikke når vinduet er skjult eller du spiller."""
        try:
            import perf
            if perf.eco():                                       # «Minimal prosessbruk»: spar minnet
                return False
        except Exception:  # noqa: BLE001
            pass
        built = getattr(self, "_prebuilt", 0)
        if built >= 6:
            return False
        idle = _time_mod.monotonic() - getattr(self, "_last_input", 0) > 4
        playing = getattr(getattr(self, "bg", None), "game_name", None)
        if not (self.get_mapped() and idle and not playing):
            return True                                          # prøv igjen om litt
        v = _visits_load()
        order = sorted(self._lazy, key=lambda n: (-v.get(n, 0), self.PREBUILD_DEFAULT.index(n)
                                                  if n in self.PREBUILD_DEFAULT else 99))
        nxt = next((n for n in order if self._lazy[n][3] is None and n != "venner"), None)
        if nxt is None:
            return False
        try:
            self.ensure_lazy(nxt)
            self._prebuilt = built + 1
        except Exception:  # noqa: BLE001
            applog.log.exception("forhåndsbygging %s", nxt)
            self._prebuilt = built + 1
        GLib.timeout_add(2500, self._prebuild)                    # neste side om litt
        return False

    def ensure_lazy(self, name):
        """Bygg en side som ikke er åpnet ennå – uten å vise den (brukes av søket)."""
        lz = getattr(self, "_lazy", {}).get(name)
        if lz and lz[3] is None:
            import importlib
            page = getattr(importlib.import_module(lz[1]), lz[2])()
            page.set_hexpand(True)
            page.set_vexpand(True)
            lz[0].append(page)
            lz[3] = page
            try:
                import pagecats
                pagecats.attach(name, page)
            except Exception:  # noqa: BLE001
                applog.log.exception("sidekategorier")
        return lz[3] if lz else None

    def ensure_audio_page(self):
        if self.audio_page is None:
            if IS_WIN:
                import winaudio
                self.audio_page = winaudio.AudioWinPage()
            else:
                import audio
                self.audio_page = audio.AudioPage()
            self.audio_page.set_hexpand(True)
            self.audio_page.set_vexpand(True)
            self.audio_holder.append(self.audio_page)
        return self.audio_page

    def open_ambient(self, *_):
        import ambient
        ambient.open_ambient(self)

    def open_search(self, *_):
        import search
        search.SearchDialog(self).present(self)

    def _side_search(self, entry, go_first=False):
        """Nytt design: søkefeltet i menyen fyller «Finn alt»-siden og viser den (Enter = første treff)."""
        text = entry.get_text().strip()
        if not text and not go_first:
            return
        page = self.ensure_lazy("finn")
        if page is None:
            return
        if self.stack.get_visible_child_name() != "finn":
            self.stack.set_visible_child_name("finn")
            self.split.set_show_content(True)
        if page.entry.get_text() != text:
            page.entry.set_text(text)
        if go_first and text:
            page._first()
        GLib.idle_add(lambda: (entry.grab_focus_without_selecting() if not go_first else None, False)[1])

    # --- enkel modus: bare det viktigste i sidemenyen ---
    SIMPLE_PAGES = {"oversikt", "lyd", "spill", "vr", "discord", "scener", "smarthjem", "familie", "chat", "fjernhjelp",
                    "innstillinger"}

    def simple_mode(self):
        try:
            import json as _j
            return bool(_j.load(open(os.path.expanduser("~/.config/systemmonitor/enkel.json"))).get("on"))
        except (OSError, ValueError):
            return False

    def set_simple_mode(self, on):
        import json as _j
        p = os.path.expanduser("~/.config/systemmonitor/enkel.json")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            _j.dump({"on": bool(on)}, f)
        self.sidebar.invalidate_filter()
        self.sidebar.invalidate_headers()
        if on and self.stack.get_visible_child_name() not in self.SIMPLE_PAGES:
            self.stack.set_visible_child_name("oversikt")

    def _on_tab(self, stack, _p):
        # RGB-fanen (og OpenRGB) startes først når du åpner den – eller av rgb_restore ved oppstart
        if stack.get_visible_child_name() == "rgb":
            self.ensure_rgb_page()
        lz = getattr(self, "_lazy", {}).get(stack.get_visible_child_name())
        if lz and lz[3] is None:
            self.ensure_lazy(stack.get_visible_child_name())
        if stack.get_visible_child_name() == "msi" and self.msi_page is None:
            if IS_WIN:
                import winmsi
                self.msi_page = winmsi.MsiWinPage()
            else:
                import msi
                self.msi_page = msi.MsiPage()
            self.msi_page.set_hexpand(True)
            self.msi_page.set_vexpand(True)
            self.msi_holder.append(self.msi_page)
        if stack.get_visible_child_name() == "lyd" and self.audio_page is None:
            if IS_WIN:
                import winaudio
                self.audio_page = winaudio.AudioWinPage()
            else:
                import audio
                self.audio_page = audio.AudioPage()
            self.audio_page.set_hexpand(True)
            self.audio_page.set_vexpand(True)
            self.audio_holder.append(self.audio_page)
        if stack.get_visible_child_name() == "wifi" and self.wifi_page is None:
            if IS_WIN:
                import win_pages
                self.wifi_page = win_pages.WifiWinPage()
            else:
                import wifi
                self.wifi_page = wifi.WifiPage()
            self.wifi_page.set_hexpand(True)
            self.wifi_page.set_vexpand(True)
            self.wifi_holder.append(self.wifi_page)
        if stack.get_visible_child_name() == "programmer" and self.prog_page is None:
            if IS_WIN:
                import win_pages
                self.prog_page = win_pages.ProgramsWinPage()
            else:
                import programs
                self.prog_page = programs.ProgramsPage()
            self.prog_page.set_hexpand(True)
            self.prog_page.set_vexpand(True)
            self.prog_holder.append(self.prog_page)
        if stack.get_visible_child_name() == "cpuskjerm" and self.lcd_page is None:
            if IS_WIN:
                import win_pages
                self.lcd_page = win_pages.LcdWinPage()
            else:
                import lcd
                self.lcd_page = lcd.LcdPage()
            self.lcd_page.set_hexpand(True)
            self.lcd_page.set_vexpand(True)
            self.lcd_holder.append(self.lcd_page)
        if stack.get_visible_child_name() == "logitech" and self.logi_page is None:
            if IS_WIN:
                import win_pages
                self.logi_page = win_pages.LogitechWinPage()
            else:
                import logitech
                self.logi_page = logitech.LogitechPage()
            self.logi_page.set_hexpand(True)
            self.logi_page.set_vexpand(True)
            self.logi_holder.append(self.logi_page)
        # Maks bredde også på fanene som nettopp ble laget
        holder = stack.get_visible_child()
        page = holder.get_first_child() if holder else None
        if page is not None and not getattr(page, "_clamped", False):
            page._clamped = True
            try:
                self._clamp(page)
            except Exception:  # noqa: BLE001 – utseende, aldri viktig nok til å stoppe fanen
                pass
        GLib.timeout_add(400, self.rescan_cards)        # alle kortene på sidene kan dras og få ny størrelse
        import design
        if design.is_new():                             # nytt design: rydd siden (noen kort bygges litt etterpå)
            nm, h = stack.get_visible_child_name(), stack.get_visible_child()
            for ms in (450, 1600):
                GLib.timeout_add(ms, lambda h=h, nm=nm: (design.polish(h, nm), False)[1])

    def _on_overlay_toggled(self, btn):
        on = btn.get_active()
        set_overlay(on)
        save_overlay_pref(on)
        btn.set_tooltip_text(i18n.tr("Overlay i spill: PÅ" if on else "Overlay i spill: AV") + "\n" + i18n.tr(
            "Slår overlayet i spill av/på (FPS, CPU, GPU og temperaturer).\n"
            "Høyre Shift + F12 slår det også av/på inne i spillet."))
        if on:
            btn.add_css_class("suggested-action")
        else:
            btn.remove_css_class("suggested-action")

    def _on_range(self, btn, secs):
        if btn.get_active():
            GRAPH_WINDOW[0] = secs
            for g in GRAPHS:
                g.queue_draw()

    def _update_tiles(self, cpu_t, nv):
        import cards
        self.t_cpu.gauge.set_value(cpu_t)
        self.t_cpu.value.set_label(f"{cpu_t:.0f} °C" if cpu_t is not None else "–")
        self.t_cpu.sub.set_label(i18n.tr(f"{self._cpu_load:.0f} % last"))
        if self.t_gpu:
            g_t = nv.get("temp") if nv else None
            self.t_gpu.gauge.set_value(g_t)
            self.t_gpu.value.set_label(f"{g_t:.0f} °C" if g_t is not None else "–")
            self.t_gpu.sub.set_label(i18n.tr(f"{(nv.get('util') or 0):.0f} % last") if nv else "")
        pw = self.meter.read(nv.get("power") if nv else None)
        self._power = pw
        self.energy.add(pw["total"])
        if pw["total"] is not None:
            import power as power_mod
            self.t_pow.value.set_label(f"{pw['total']:.0f} W")
            wh = self.energy.today_wh()
            self.t_pow.sub.set_label(f"I dag {wh / 1000:.2f} kWh · {wh / 1000 * power_mod.load()['price']:.2f} kr")
            self.t_pow.set_tooltip_text(
                f"CPU {pw['cpu'] or 0:.0f} W · skjermkort {pw['gpu'] or 0:.0f} W · "
                f"resten av PC-en ca. {power_mod.load()['extra_w']} W (anslått)")
        else:
            self.t_pow.value.set_label("–")
        mode = self.power.active_profile()
        self.t_mode.value.set_label(i18n.tr(cards.MODE_NAMES.get(mode, "–")))
        icons = {"power-saver": "ks-night-symbolic", "balanced": "ks-overview-symbolic",
                 "performance": "ks-power-symbolic"}
        img = self.t_mode.get_first_child().get_first_child()
        if isinstance(img, Gtk.Image) and img.get_icon_name() != icons.get(mode, "ks-overview-symbolic"):
            img.set_from_icon_name(icons.get(mode, "ks-overview-symbolic"))
        game = getattr(getattr(self, "bg", None), "game_name", None)
        self.t_mode.sub.set_label(i18n.tr("Spillprofil: ") + game if game else "")
        try:
            self._update_info_tiles()
        except Exception:  # noqa: BLE001
            applog.log.exception("infofliser")

    def set_badge(self, name, text):
        """Lite tall/merke til høyre i sidemenyen (f.eks. CPU-temperatur ved Oversikt)."""
        lbl = getattr(self, "_badges", {}).get(name)
        if lbl is not None and lbl.get_label() != (text or ""):
            lbl.set_label(text or "")
        if lbl is not None:
            lbl.set_visible(bool(text))

    def _open_mini(self, *_):
        import miniwin
        if getattr(self, "mini", None) is None or not self.mini.get_visible():
            self.mini = miniwin.MiniWindow(self)
        self.mini.present()

    def _open_welcome(self, *_):
        import welcome
        welcome.WelcomeDialog(self).present(self)

    def rescan_cards(self, *_):
        """Gjør kortene på siden som vises flyttbare (kalles også når en side har bygd kortene på nytt)."""
        name = self.stack.get_visible_child_name()
        holder = self.stack.get_visible_child()
        page = holder.get_first_child() if holder else None
        if page is not None and name != "oversikt":
            try:
                import sortbox
                sortbox.scan(page, name)
            except Exception:  # noqa: BLE001
                applog.log.exception("flyttbare kort")
        return False

    def _on_edit_dash(self, btn):
        on = btn.get_active()
        self.edit_bar.set_reveal_child(on)
        self.dash.set_editing(on)

    def _fill_hidden(self, pop):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        hid = [k for k in self.dash.order if k in self.dash.hidden]
        if not hid:
            box.append(Gtk.Label(label=i18n.tr("Ingen skjulte fliser"), margin_top=6, margin_bottom=6))
        for k in hid:
            b = Gtk.Button(label="＋  " + i18n.tr(getattr(self.dash, "titles", {}).get(k, k)))
            b.add_css_class("flat")
            b.connect("clicked", lambda _b, k=k: (pop.popdown(), self.dash.unhide(k)))
            box.append(b)
        pop.set_child(box)

    def layout_for_game(self, playing):
        """Oppsettet «Spill» mens du spiller (hvis du har valgt automatikk), og tilbake etterpå."""
        import dashboard as _db
        if not _db._load().get("_auto_game_layout", True):
            return
        if playing and self.dash.preset != "spill":
            self._preset_before = self.dash.preset
            GLib.idle_add(lambda: self.preset_dd.set_selected(self.presets.index("spill")) or False)
        elif not playing and getattr(self, "_preset_before", None) is not None:
            p, self._preset_before = self._preset_before, None
            GLib.idle_add(lambda: self.preset_dd.set_selected(self.presets.index(p)) or False)

    def _open_info_settings(self):
        self._on_sidebar(None, self._rows["innstillinger"])
        page = self._lazy.get("innstillinger", [None, None, None, None])[3]
        if page is not None:
            page.show_tab("generelt")

    def _show_calendar(self):
        import infotiles
        c = infotiles.calendar() or {}
        if c.get("error"):
            self._open_info_settings()
            return
        ev = c.get("events") or []
        body = "\n".join(f"{e['when']} – {e['title']}" + (f" ({e['where']})" if e.get("where") else "") for e in ev)
        d = Adw.AlertDialog(heading=i18n.tr("Kalenderen"), body=body or i18n.tr("Ingen kommende avtaler"))
        d.add_response("ok", "OK")
        d.present(self)

    def _update_today(self):
        def work():
            try:
                import today
                s = today.summary()
                GLib.idle_add(show, s, today.text(s))
            except Exception:  # noqa: BLE001
                pass

        def show(s, txt):
            self.t_today.value.set_label(f"{s['play_s'] // 3600} t {s['play_s'] % 3600 // 60} min "
                                         + i18n.tr("spilt") + (f" · {s['kr']:.2f} kr" if s.get("kr") is not None else ""))
            rest = txt.split(" · ", 1)[1] if " · " in txt else ""
            self.t_today.sub.set_label(rest or i18n.tr("Ingen spill i dag ennå"))
            return False
        import threading
        threading.Thread(target=work, daemon=True).start()
        return False

    def _update_info_tiles(self):
        import infotiles as I
        p = I.ping() or {}
        self.t_ping.value.set_label(f"{p['ms']} ms" if p.get("ms") is not None else "–")
        self.t_ping.sub.set_label(i18n.tr("til internett") if p.get("ms") is not None else i18n.tr("ingen kontakt"))
        rx = self.c_net.graph.series[0][-1] if self.c_net.graph.series[0] else 0
        self.t_down.value.set_label(fmt_rate(rx))
        tx = self.c_net.graph.series[1][-1] if self.c_net.graph.series[1] else 0
        self.t_down.sub.set_label("↑ " + fmt_rate(tx))
        ps = I.playtime_today()
        if ps is not None:
            self.t_play.value.set_label(f"{ps // 3600} t {ps % 3600 // 60} min")
            game = getattr(getattr(self, "bg", None), "game_name", None)
            self.t_play.sub.set_label(("▶ " + game) if game else i18n.tr("ingen spill nå"))
        pr = I.price() or {}
        if pr.get("now") is not None:
            self.t_price.value.set_label(f"{pr['now']:.2f} kr")
            self.t_price.sub.set_label(i18n.tr("per kWh · billigst kl. ") + str(pr.get("cheapest_at") or "–"))
        elif pr.get("error"):
            self.t_price.value.set_label("–")
            self.t_price.sub.set_label(i18n.tr("får ikke hentet prisen"))
        w = I.weather() or {}
        if w.get("temp") is not None:
            self.t_weather.value.set_label(f"{w['icon']} {w['temp']}°")
            self.t_weather.sub.set_label(f"{w.get('place', '').split(',')[0]} · {w.get('text', '')}")
        else:
            self.t_weather.value.set_label("–")
            self.t_weather.sub.set_label(i18n.tr("Trykk for å velge sted"))
        c = I.calendar() or {}
        ev = (c.get("events") or [None])[0]
        if ev:
            self.t_cal.value.set_label(ev["title"])
            self.t_cal.sub.set_label(ev["when"])
        else:
            self.t_cal.value.set_label("–")
            self.t_cal.sub.set_label(i18n.tr("Trykk for å legge inn kalender") if c.get("error") else
                                     i18n.tr("ingen avtaler"))
        for t in (self.t_cpu, self.t_gpu, self.t_pow, self.t_ping, self.t_down):
            if t is not None and t.spark is not None:
                t.spark.queue_draw()

    def open_details(self, kind):
        import details_ui
        details_ui.DetailsDialog(self, kind).present(self)

    def _menu_actions(self):
        for name, fn in (("syscheck", lambda *_: self._open_syscheck(None)),
                         ("mini", self._open_mini), ("welcome", self._open_welcome),
                         ("whatsnew", lambda *_: self._open_whatsnew()),
                         ("ambient", lambda *_: self.open_ambient()),
                         ("about", lambda *_: self._open_about()),
                         ("settings", lambda *_: self._on_sidebar(None, self._rows["innstillinger"])),
                         ("features", lambda *_: __import__("funksjoner_ui").open_dialog(self))):
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", fn)
            self.add_action(act)
        act = Gio.SimpleAction.new_stateful("lang", GLib.VariantType.new("s"), GLib.Variant("s", i18n.CHOICE))
        act.connect("activate", lambda a, v: (a.set_state(v), self._set_lang(v.get_string())))
        self.add_action(act)

    def _open_about(self):
        import whatsnew
        ver = whatsnew.current_version()
        notes = ""
        for v, _title, sections in whatsnew.NEWS:
            if v == ver:
                for sec, items in sections:
                    notes += f"<p>{i18n.tr(sec)}</p><ul>" + "".join(
                        f"<li>{GLib.markup_escape_text(i18n.tr(it))}</li>" for it in items) + "</ul>"
        d = Adw.AboutDialog(
            application_name=i18n.tr("Kontrollsenter"), application_icon=APP_ICON,
            version=ver, developer_name="Vegard E. Wågan",
            copyright="Copyright © Vegard E. Wågan",
            comments=i18n.tr("Overvåk og styr PC-en din: ytelse, vifter, strømmodus, RGB, spill og mer."),
            release_notes_version=ver, release_notes=notes)
        d.present(self)

    def _on_sidebar(self, _lb, row):
        target = row.page_name
        if getattr(row, "group_members", None):
            import pagecats
            last = pagecats._prefs().get("group:" + row.group_key)
            cur = self.stack.get_visible_child_name()
            if cur in row.group_members:
                target = cur
            elif last in row.group_members:
                target = last
        self.stack.set_visible_child_name(target)
        self.split.set_show_content(True)

    def _sync_sidebar(self, *_):
        name = self.stack.get_visible_child_name()
        lead = getattr(self, "_leader", {}).get(name, name)
        row = self._rows.get(lead) if hasattr(self, "_rows") else None
        if hasattr(self, "group_clamp"):
            self._update_group_bar(name)
        if row and self.sidebar.get_selected_row() is not row:
            self.sidebar.select_row(row)
        pg = self.stack.get_page(self.stack.get_visible_child())
        if pg and hasattr(self, "content_page"):
            self.content_page.set_title(pg.get_title())
            if hasattr(self, "page_title"):
                self.page_title.set_title(pg.get_title())
            if hasattr(self, "page_help"):
                import theme as ks_theme
                txt = ks_theme.PAGE_HELP.get(name, "") if name != "oversikt" else ""
                if txt:
                    import design
                    if design.is_new() and design.help_seen(name):   # nytt design: bare første gang
                        txt = ""
                self.page_help.set_label(i18n.tr(txt))
                self.page_help_clamp.set_visible(bool(txt))

    def toast(self, text):
        self.toast_overlay.add_toast(Adw.Toast(title=i18n.tr(text), timeout=3))

    @staticmethod
    def _clamp(page):
        """Maks bredde på brede skjermer: innholdet sentreres i stedet for å strekkes."""
        sc = page if isinstance(page, Gtk.ScrolledWindow) else None
        if sc is None:
            c = page.get_first_child()
            while c is not None and not isinstance(c, Gtk.ScrolledWindow):
                c = c.get_next_sibling()
            sc = c
        if sc is None:
            return
        child = sc.get_child()
        if isinstance(child, Gtk.Viewport):
            child = child.get_child()
        if child is None or isinstance(child, Adw.Clamp) or isinstance(child.get_first_child(), Adw.Clamp):
            return
        holder = child.get_parent()
        if isinstance(holder, Gtk.Viewport):
            holder.set_child(None)
        else:
            sc.set_child(None)
        sc.set_child(Adw.Clamp(maximum_size=MAX_WIDTH, tightening_threshold=900, child=child))

    def _open_whatsnew(self, *_):
        import whatsnew
        whatsnew.WhatsNewDialog().present(self)

    def cpu_temp_now(self):
        return getattr(self, "_cpu_t", None)

    def gpu_temp_now(self):
        d = self.nvidia.data if self.nvidia.available else None
        return d.get("temp") if d else None

    def update(self):
        # skjult: bare det bakgrunnen trenger. Åpent men ikke i fokus (f.eks. mens du spiller): vinduet
        # oppdateres annethvert sekund – dataene samles fortsatt hvert sekund.
        self._tick_n = getattr(self, "_tick_n", 0) + 1
        try:
            import details
            details.record(self)
        except Exception:  # noqa: BLE001
            pass
        import perf
        f = perf.interval_factor()
        if not self.get_mapped() and f > 1 and self._tick_n % 2:
            return True                                  # minimal + skjult: data hvert 2. sekund er nok
        idle = _time_mod.monotonic() - getattr(self, "_last_input", 0) > 20      # ingen mus/taster på 20 s
        if not self.get_mapped() or ((not self.is_active() or idle) and self._tick_n % 2) or \
                (f > 1 and self._tick_n % f):
            try:
                self._update_quiet()
            except Exception:  # noqa: BLE001
                import applog
                applog.log.exception("oppdatering (skjult)")
            return True
        self._full_update()
        return True

    def _update_quiet(self):
        """Når vinduet er skjult: samle data til varsler, historikk, viftekurve og mobilappen – uten å oppdatere
        tekst og grafer i vinduet (det sparer CPU)."""
        temps = hwmon_temps()
        u = self.cpu.usage()
        self._cpu_load = u.get("cpu", 0)
        self.c_cpu.graph.push(self._cpu_load)
        ct = cpu_temp(temps)
        self._cpu_t = ct
        m = meminfo()
        mt, ma = m.get("MemTotal", 1), m.get("MemAvailable", 0)
        self.c_mem.graph.push(100 * (mt - ma) / mt)
        nv = None
        if self.c_gpu:
            self.nvidia.poll()
            nv = self.nvidia.data
            if nv:
                self.c_gpu.graph.push(nv.get("util") or 0)
        rr, wr = self.disk.rates()
        self.c_disk.graph.push(rr, wr)
        rx, tx = self.net.rates()
        self.c_net.graph.push(rx, tx)
        rows = [(NICE_DEVICE.get(dv, dv), lbl, tt) for dv, lbl, tt in temps if not dv.startswith("r8169")]
        if nv and nv.get("temp") is not None:
            rows.insert(0, ("NVIDIA GPU", "GPU", nv["temp"]))
        self._remote = {"mem": [mt - ma, mt], "disk": [rr, wr], "net": [rx, tx], "temps": rows,
                        "freq": CpuReader.freq_ghz()}
        pw = self.meter.read(nv.get("power") if nv else None)
        self._power = pw
        self.energy.add(pw["total"])
        self.fans.refresh(ct, (nv or {}).get("temp"), (nv or {}).get("fan"))
        if getattr(self, "mini", None) is not None and self.mini.get_visible():
            self.mini.refresh(ct, nv, self._power)

    def _full_update(self):
        temps = hwmon_temps()

        # CPU
        u = self.cpu.usage()
        total = u.get("cpu", 0)
        self._cpu_load = total
        self.c_cpu.value.set_label(f"{total:.0f} %")
        self.c_cpu.graph.push(total)
        parts = [f"{len(self.core_bars)} tråder"]
        f = CpuReader.freq_ghz()
        if f:
            parts.append(f"maks {f:.2f} GHz")
        t = cpu_temp(temps)
        self._cpu_t = t
        if t is not None:
            parts.append(f"{t:.0f} °C")
        try:
            la = os.getloadavg()                       # finnes ikke på Windows
            parts.append(f"last {la[0]:.2f}")
        except (OSError, AttributeError):
            pass
        self.c_cpu.subtitle.set_label(" · ".join(parts))
        for k, bar in self.core_bars:
            bar.set_value(u.get(k, 0))
        self.c_cpu.details.set_visible(False)

        # Minne
        m = meminfo()
        mt, ma = m.get("MemTotal", 1), m.get("MemAvailable", 0)
        used = mt - ma
        pct = 100 * used / mt
        self.c_mem.value.set_label(f"{pct:.0f} %")
        self.c_mem.graph.push(pct)
        self.c_mem.subtitle.set_label(f"{fmt_bytes(used)} av {fmt_bytes(mt)} i bruk")
        st, sf = m.get("SwapTotal", 0), m.get("SwapFree", 0)
        self.c_mem.details.set_label(
            f"Hurtigbuffer {fmt_bytes(m.get('Cached', 0))} · Swap {fmt_bytes(st - sf)} / {fmt_bytes(st)}"
        )

        # NVIDIA
        if self.c_gpu:
            self.nvidia.poll()
            d = self.nvidia.data
            if d:
                self.c_gpu.inner.get_first_child().get_first_child().set_label(
                    d["name"].replace("NVIDIA ", "")
                )
                util = d["util"] or 0
                self.c_gpu.value.set_label(f"{util:.0f} %")
                self.c_gpu.graph.push(util)
                sub = []
                if d["mem_used"] is not None and d["mem_total"]:
                    sub.append(f"VRAM {d['mem_used']/1024:.1f} / {d['mem_total']/1024:.1f} GB")
                if d["temp"] is not None:
                    sub.append(f"{d['temp']:.0f} °C")
                self.c_gpu.subtitle.set_label(" · ".join(sub))
                det = []
                if d["power"] is not None:
                    if d.get("limit"):
                        det.append(f"Effekt {d['power']:.0f} / {d['limit']:.0f} W (grense)")
                    else:
                        det.append(f"Effekt {d['power']:.0f} W")
                if d["fan"] is not None:
                    det.append(f"Vifte {d['fan']:.0f} %")
                self.c_gpu.details.set_label(" · ".join(det))
            else:
                self.c_gpu.subtitle.set_label("Henter data fra nvidia-smi …")

        # AMD
        for dev, card in zip(self.amd, self.c_amd):
            busy = float(read(os.path.join(dev, "gpu_busy_percent"), "0") or 0)
            card.value.set_label(f"{busy:.0f} %")
            card.graph.push(busy)
            vu = read(os.path.join(dev, "mem_info_vram_used"))
            vt = read(os.path.join(dev, "mem_info_vram_total"))
            sub = []
            if vu and vt:
                sub.append(f"VRAM {fmt_bytes(int(vu))} / {fmt_bytes(int(vt))}")
            for dv, _lbl, tt in temps:
                if dv == "amdgpu":
                    sub.append(f"{tt:.0f} °C")
                    break
            card.subtitle.set_label(" · ".join(sub))
            card.details.set_visible(False)

        # Disk
        rr, wr = self.disk.rates()
        self.c_disk.graph.push(rr, wr)
        self.c_disk.value.set_label(fmt_rate(rr + wr))
        try:
            du = shutil.disk_usage(os.path.expanduser("~"))     # virker på både Linux og Windows
            tot, free = du.total, du.free
            self.c_disk.subtitle.set_label(
                f"Hjemmemappe: {fmt_bytes(tot - free)} brukt, {fmt_bytes(free)} ledig av {fmt_bytes(tot)}"
            )
        except OSError:
            pass
        self.c_disk.details.set_label(f"Les {fmt_rate(rr)} · Skriv {fmt_rate(wr)}")

        # Nettverk
        rx, tx = self.net.rates()
        self.c_net.graph.push(rx, tx)
        self.c_net.value.set_label(fmt_rate(rx))
        self.c_net.subtitle.set_label("Alle nettverkskort samlet")
        self.c_net.details.set_label(f"Ned {fmt_rate(rx)} · Opp {fmt_rate(tx)}")

        # Temperaturer
        nv = self.nvidia.data
        rows = [(NICE_DEVICE.get(dv, dv), lbl, tt) for dv, lbl, tt in temps
                if not dv.startswith("r8169")]
        if nv and nv.get("temp") is not None:
            rows.insert(0, ("NVIDIA GPU", "GPU", nv["temp"]))
        hottest = max((r[2] for r in rows), default=None)
        self.c_temp.value.set_label(f"{hottest:.0f} °C" if hottest is not None else "–")
        self.c_temp.subtitle.set_label("Høyeste temperatur vises øverst til høyre · grønn < 70 °C, gul < 85 °C, rød ≥ 85 °C")
        half = (len(rows) + 1) // 2
        for i, (dv, lbl, tt) in enumerate(rows):
            key = (dv, lbl, i)
            col, row = (0, i) if i < half else (4, i - half)
            if key not in self.temp_rows:
                a = Gtk.Label(label=dv, xalign=0)
                a.add_css_class("dim-label")
                b = Gtk.Label(label=lbl, xalign=0, hexpand=True)
                c = Gtk.Label(xalign=1)
                c.add_css_class("numeric")
                c.set_margin_end(24 if col == 0 else 0)
                self.temp_grid.attach(a, col, row, 1, 1)
                self.temp_grid.attach(b, col + 1, row, 1, 1)
                self.temp_grid.attach(c, col + 2, row, 1, 1)
                self.temp_rows[key] = c
            c = self.temp_rows[key]
            c.set_label(f"{tt:.0f} °C")
            for cls in ("success", "warning", "error"):
                c.remove_css_class(cls)
            c.add_css_class("error" if tt >= 85 else "warning" if tt >= 70 else "success")
        self.c_temp.details.set_visible(False)

        # øyeblikksbilde for fjernstyringen (mobil/nettbrett)
        self._remote = {"mem": [used, mt], "disk": [rr, wr], "net": [rx, tx], "temps": rows, "freq": f}

        # Strømmodus: fart nå og målt topp
        nvd = self.nvidia.data or {}
        self.power.tick(CpuReader.freq_ghz(), nvd)

        # Diskplass
        self.diskspace.refresh()

        # Vifter
        self.fans.refresh(cpu_temp(temps), nvd.get("temp"), nvd.get("fan"))

        # Batteri (bare bærbare)
        if self.c_bat:
            b = battery_info(self.batteries)
            icon = "⚡" if b["state"] == "Charging" else "🔋"
            self.c_bat.value.set_label(f"{b['pct']} %")
            self.c_bat.graph.push(b["pct"])
            if b["state"] == "Charging":
                sub = "Lader" + (f" · {fmt_duration(b['secs'])} til fullt" if b["secs"] else "")
            elif b["state"] == "Discharging":
                sub = "På batteri" + (f" · {fmt_duration(b['secs'])} igjen" if b["secs"] else "")
            elif b["state"] in ("Full", "Not charging"):
                sub = "Fullt oppladet · koblet til strøm"
            else:
                sub = "Koblet til strøm"
            self.c_bat.subtitle.set_label(sub)
            det = []
            if b["watts"] > 0.1:
                det.append(f"Effekt {b['watts']:.1f} W")
            if b["health"]:
                det.append(f"Batterihelse {b['health']} %")
            if b["count"] > 1:
                det.append(f"{b['count']} batterier")
            self.c_bat.details.set_label(" · ".join(det))
            tid = f" · {fmt_duration(b['secs'])}" if b["secs"] and b["state"] == "Discharging" else ""
            self.bat_lbl.set_label(f"{icon} {b['pct']} %{tid}")

        # Nøkkeltall og sidemeny
        try:
            nv = self.nvidia.data if self.nvidia.available else None
            ct = self._cpu_t
            self._update_tiles(ct, nv)
            self.set_badge("oversikt", f"{ct:.0f}°" if ct is not None else "")
            if getattr(self, "mini", None) is not None and self.mini.get_visible():
                self.mini.refresh(ct, nv, self._power)
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("nøkkeltall")

        # Oppetid
        up = uptime_seconds()
        h, rem = divmod(int(up), 3600)
        self.uptime_lbl.set_label(f"Oppetid {h} t {rem // 60} min")
        d, hh = divmod(h, 24)
        up_txt = (f"{d} d {hh} t" if d else f"{h} t {rem // 60} min")
        try:
            self._refresh_chrome(up_txt)
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("design")
        return True

    def _refresh_chrome(self, up_txt):
        """Toppfelt, velkomst og livestatus i sidemenyen."""
        import time as _t
        import theme
        sub = self.brand_sub.get_label() if hasattr(self, "brand_sub") else ""
        self.page_title.set_subtitle(" · ".join(x for x in (sub, i18n.tr("oppe") + " " + up_txt) if x))
        ct = getattr(self, "_cpu_t", None)
        nv = self.nvidia.data if self.nvidia.available else {}
        gt = nv.get("temp") if nv else None
        watts = (getattr(self, "_power", None) or {}).get("total")
        self._pulse["cpu"].set_label(f"{ct:.0f}°" if ct is not None else "–")
        self._pulse["gpu"].set_label(f"{gt:.0f}°" if gt is not None else "–")
        self._pulse["w"].set_label(f"{watts:.0f}" if watts else "–")
        if hasattr(self, "hello"):
            name = os.environ.get("USER") or os.environ.get("USERNAME") or ""
            first = ""
            try:
                import pwd
                first = (pwd.getpwnam(name).pw_gecos.split(",")[0].split() or [""])[0]
            except Exception:  # noqa: BLE001
                first = ""
            hi = i18n.tr(theme.greeting(_t.localtime().tm_hour))
            self.hello.set_label(f"{hi}, {first}" if first else hi)
            game = getattr(getattr(self, "bg", None), "game_name", None)
            parts = []
            if game:
                parts.append("🎮 " + game)
            mode = self.t_mode.value.get_label() if getattr(self, "t_mode", None) else ""
            if mode:
                parts.append(mode)
            if watts:
                parts.append(f"{watts:.0f} W")
            if _t.time() - getattr(self, "_cal_t", 0) > 300 and __import__("funksjoner").on("kalender"):
                self._cal_t = _t.time()                         # dagens linje fra kalenderen (i bakgrunnen)

                def cal_work():
                    try:
                        import kalender as KAL
                        line = KAL.today_line()
                        cd = KAL.countdown() if KAL.cfg().get("countdown", True) else None
                        self._cal_line = "  ·  ".join(x for x in (("📅 " + line) if line else "",
                                                                  ("⏳ " + cd[1]) if cd else "") if x)
                    except Exception:  # noqa: BLE001
                        self._cal_line = ""
                import threading as _th
                _th.Thread(target=cal_work, daemon=True).start()
            if getattr(self, "_cal_line", ""):
                parts.append(self._cal_line)
            try:                                                  # batteri i hodesett, mus, tastatur og kontroller
                import batteries
                ic = {"headset": "🎧", "mouse": "🖱️", "keyboard": "⌨️", "gamepad": "🎮", "controller": "🎮"}
                hp = __import__("pcplus").LAST["health"] if "pcplus" in sys.modules else None
                if hp:
                    parts.append(f"❤️ {hp['score']}")
                bl = [f"{ic.get(d.get('kind'), '🔋')} {d['pct']:.0f} %" + (" ⚠" if d["pct"] <= 15 else "")
                      for d in batteries.cached() if d.get("pct") is not None][:4]
                if bl:
                    parts.append("  ".join(bl))
            except Exception:  # noqa: BLE001
                pass
            self.hello_sub.set_label("  ·  ".join(parts))
            hot = max((x for x in (ct, gt) if x is not None), default=None)
            lvl, txt = ("", i18n.tr("Alt ser bra ut"))
            if hot is not None and hot >= 85:
                lvl, txt = "bad", i18n.tr("Varm – sjekk viftene")
            elif hot is not None and hot >= 75:
                lvl, txt = "warn", i18n.tr("Litt varm")
            for c in ("warn", "bad"):
                self.hello_chip.remove_css_class(c)
            if lvl:
                self.hello_chip.add_css_class(lvl)
            self.hello_chip.set_label(("● " + txt))


class MonitorApp(Adw.Application):
    def __init__(self):
        app_id = os.environ.get("SYSTEMMONITOR_APP_ID", "no.waagan.Systemmonitor")  # for testing
        super().__init__(application_id=app_id)

    def do_startup(self):
        Adw.Application.do_startup(self)
        try:                                                                   # ✕ på alle vinduer som spretter opp
            __import__("dialogx").install()
        except Exception:  # noqa: BLE001
            pass
        for name in ("call-answer", "call-decline", "call-mute"):            # knappene i anropsvarselet
            ca = Gio.SimpleAction.new(name, GLib.VariantType.new("s"))
            ca.connect("activate", lambda _a, v, n=name: __import__("chatcall").from_notification(n, v.get_string(),
                                                                                                    self))
            self.add_action(ca)
        for name in ("chat-react", "chat-read"):                               # knappene i chatvarselet
            ca = Gio.SimpleAction.new(name, GLib.VariantType.new("s"))
            ca.connect("activate", lambda _a, v, n=name: __import__("chatextra").from_notification(n, v.get_string()))
            self.add_action(ca)
        act = Gio.SimpleAction.new("joingame", GLib.VariantType.new("s"))      # «Spill sammen» fra varselet

        def join(_a, v):
            try:
                import json as _j
                import launcher
                d = _j.loads(v.get_string())
                launcher.join(d["g"], reply_to=d.get("from"))
            except Exception:  # noqa: BLE001
                applog.log.exception("bli med i spill")
        act.connect("activate", join)
        self.add_action(act)
        hk = Gio.SimpleAction.new("hotkey", GLib.VariantType.new("s"))       # hurtigtaster fra Hyprland/GNOME
        hk.connect("activate", lambda _a, v: __import__("desktop").pressed(v.get_string()))
        self.add_action(hk)
        sa = Gio.SimpleAction.new("search", None)
        sa.connect("activate", lambda *_: getattr(self, "win", None) and self.win.open_search())
        self.add_action(sa)
        self.set_accels_for_action("app.search", ["<Control>k", "<Control>f"])
        am = Gio.SimpleAction.new("ambient", None)
        am.connect("activate", lambda *_: getattr(self, "win", None) and self.win.open_ambient())
        self.add_action(am)
        self.set_accels_for_action("app.ambient", ["F11"])
        self.set_accels_for_action("app.chat", ["<Control><Shift>c"])      # chatten med én tast

    def do_activate(self):
        win = getattr(self, "win", None)
        if win is None:
            try:                                  # tell oppstarten FØR vinduet bygges – krasjer det, rulles det tilbake
                import features
                features.check_rollback()
            except Exception:  # noqa: BLE001
                pass
            try:
                win = self.win = MonitorWindow(self)
                import background
                win.bg = background.Background(self, win)
            except Exception:  # noqa: BLE001
                applog.crash("Kontrollsenter kunne ikke starte")
                self.quit()
                return
            if IS_WIN:
                import winsupport
                winsupport.listen_for_show(win.bg.show)
            try:                                          # ny versjon? installer og start på nytt (kan slås av)
                import selfupdate
                selfupdate.run_at_start(win, getattr(win.bg, "notify", None))
            except Exception:  # noqa: BLE001
                applog.log.exception("automatisk oppdatering ved oppstart")
            if "--hidden" in sys.argv and win.bg.cfg["background"] and not win.bg.cfg.get("show_on_login", True):
                return                      # startet ved innlogging: bare ikon i statusfeltet
            if "--tray" in sys.argv and win.bg.cfg["background"]:
                return                      # stille omstart (mindre minnebruk): vinduet var lukket
            win.present()
            import welcome
            import whatsnew
            if welcome.should_show():                     # første gang på denne PC-en: veiviser
                whatsnew.mark_seen()
                GLib.timeout_add(800, lambda: win._open_welcome() or False)
            elif whatsnew.should_show():
                GLib.timeout_add(800, lambda: win._open_whatsnew() or False)
            return
        win.set_visible(True)
        win.present()


if __name__ == "__main__":
    if IS_WIN:
        import faulthandler
        try:
            _fh = open(os.path.join(os.path.dirname(applog.LOG_FILE), "krasj-lavniva.txt"), "w")
            faulthandler.enable(_fh)
        except OSError:
            pass
        import winsupport
        if "--restarted" in sys.argv:              # omstart: vent til den gamle har lukket seg
            winsupport.wait_until_free(15)
        elif winsupport.already_running():         # vis vinduet til den som kjører, og avslutt
            sys.exit(0)
    MonitorApp().run(None)
