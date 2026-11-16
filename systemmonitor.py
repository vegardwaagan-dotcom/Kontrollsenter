#!/usr/bin/env python3
"""Kontrollsenter – et enkelt grafisk overvåkingsprogram for Linux (GTK4/libadwaita).

Hovedvinduet og fanene. Maskinvaredata ligger i sensors.py, kortene i Oversikt i cards.py.
"""
import glob
import os
import shutil
import subprocess
import sys
import threading
import time
from collections import deque

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

import welcome  # noqa: E402,F401  – må sjekke «første gang» før noe lager konfig-mappen
import i18n  # noqa: E402
import applog  # noqa: E402

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
    tmp = MANGOHUD_CONF + ".tmp"
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


class MonitorWindow(Adw.ApplicationWindow):
    def __init__(self, app):
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

        flow = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            homogeneous=True, max_children_per_line=3, min_children_per_line=1,
            column_spacing=12, row_spacing=12,
        )
        flow.set_valign(Gtk.Align.START)

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

        cards = ([self.c_bat] if self.c_bat else []) + [self.c_cpu, self.c_mem]
        if self.c_gpu:
            cards.append(self.c_gpu)
        cards += self.c_amd + [self.c_disk, self.c_net]
        for c in cards:
            flow.append(c)
            c.get_parent().set_focusable(False)

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
        self._power = {"cpu": None, "gpu": None, "measured": None, "total": None}
        self._cpu_load = 0.0
        tiles = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                            max_children_per_line=4, min_children_per_line=2, column_spacing=12, row_spacing=12)
        self.t_cpu = Tile("Prosessor", gauge=Gauge(100, 75, 88))
        self.t_gpu = Tile("Skjermkort", gauge=Gauge(100, 75, 85)) if self.nvidia.available or self.amd else None
        self.t_pow = Tile("Strømforbruk", icon="ks-power-symbolic")
        self.t_pow.set_tooltip_text("Klikk for detaljer og strømpris")
        click = Gtk.GestureClick()
        click.connect("released", lambda *_: power_mod.dialog(self))
        self.t_pow.add_controller(click)
        self.t_pow.set_cursor_from_name("pointer")
        self.t_mode = Tile("Strømmodus", icon="ks-overview-symbolic")
        for t in (self.t_cpu, self.t_gpu, self.t_pow, self.t_mode):
            if t:
                tiles.append(t)
                t.get_parent().set_focusable(False)
        hero = Gtk.Box(spacing=16)
        hero.set_margin_top(6)
        hero.set_margin_bottom(4)
        hcol = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        self.hello = Gtk.Label(xalign=0)
        self.hello.add_css_class("ks-hello")
        hcol.append(self.hello)
        self.hello_sub = Gtk.Label(xalign=0, wrap=True)
        self.hello_sub.add_css_class("ks-hello-sub")
        hcol.append(self.hello_sub)
        hero.append(hcol)
        self.hello_chip = Gtk.Label(valign=Gtk.Align.CENTER)
        self.hello_chip.add_css_class("ks-chip")
        hero.append(self.hello_chip)
        page.append(hero)
        page.append(tiles)
        try:                                  # batteri i mus, tastatur og hodesett
            import battery_ui
            page.append(battery_ui.BatteryCard())
        except Exception:  # noqa: BLE001
            pass
        page.append(self.power)
        self.fans = FanCard(self.nvidia.available)
        page.append(self.fans)
        # (Windows: viftene styres via LibreHardwareMonitor)
        self.connect("close-request", lambda *_: self.fans.all_auto_now() or False)
        # Tidsrom for grafene: 1 min, 10 min eller 1 time (hold musa over en graf for verdi og tid)
        rng = Gtk.Box(spacing=8)
        lbl = Gtk.Label(label="Grafer", xalign=0, hexpand=True)
        lbl.add_css_class("heading")
        rng.append(lbl)
        seg = Gtk.Box()
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
        page.append(rng)
        page.append(flow)
        self.diskspace = DiskSpaceCard()
        page.append(self.diskspace)
        page.append(self.c_temp)
        page.append(topbar)                   # Tilbakestill nederst – sjelden brukt

        css = Gtk.CssProvider()
        if hasattr(css, "load_from_string"):
            css.load_from_string(CSS.decode())
        else:
            css.load_from_data(CSS, -1)
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

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
                ("historikk", "Historikk", "ks-history-symbolic", "history", "HistoryPage"),
                ("gpu", "GPU-innstillinger", "ks-gpu-symbolic", "gpu_page", "GpuPage"),
                ("bluetooth", "Bluetooth", "ks-bluetooth-symbolic", "bluetooth", "BluetoothPage"),
                ("nettverk", "Nettverk", "ks-network-symbolic", "netpage", "NetworkPage"),
                ("spill", "Spill", "ks-games-symbolic", "games", "GamesPage"),
                ("stromming", "Strømming", "ks-stream-symbolic", "streaming_ui", "StreamingPage"),
                ("familie", "Familie", "ks-family-symbolic", "family_page", "FamilyPage"),
                ("automatikk", "Automatikk", "ks-auto-symbolic", "automation", "AutomationPage"),
                ("hjemme", "PC-er hjemme", "ks-home-symbolic", "homepcs", "HomePage"),
                ("verktoy", "Verktøy", "ks-tools-symbolic", "tools", "ToolsPage")):
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
        stack.connect("notify::visible-child-name", self._on_tab)
        stack.connect("notify::visible-child-name", self._sync_sidebar)
        self.toast_overlay = Adw.ToastOverlay(child=stack)
        self.page_help = Gtk.Label(xalign=0, wrap=True)
        self.page_help.add_css_class("ks-pagehelp")
        for side, v in (("start", 18), ("end", 18), ("top", 4), ("bottom", 8)):
            getattr(self.page_help, f"set_margin_{side}")(v)
        self.page_help_clamp = Adw.Clamp(maximum_size=MAX_WIDTH, child=self.page_help, visible=False)
        toolbar.add_top_bar(self.page_help_clamp)
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

        def section_header(row, before):
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
        side_tv.add_top_bar(side_header)
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
        if not os.environ.get("SYSTEMMONITOR_APP_ID"):            # skrivebordswidgetene som var på sist
            GLib.timeout_add_seconds(4, lambda: __import__("desk_widgets").restore(self))
        if self.hw.get("rgb") and not os.environ.get("SYSTEMMONITOR_APP_ID"):
            GLib.timeout_add_seconds(12, lambda: (self.rgb_restore("oppstart"), False)[1])
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

    def restart_app(self, *_):
        """Start programmet på nytt (ny versjon eller nytt språk). Vinduet kommer tilbake av seg selv."""
        def restart():
            try:
                set_overlay(False)
                self.fans.all_auto_now()
                self.power.flush_peaks()
            except Exception:  # noqa: BLE001
                pass
            extra = ["-X", "utf8"] if IS_WIN else []
            os.execv(sys.executable, [sys.executable, *extra, os.path.abspath(__file__)])
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

    def _open_syscheck(self, _btn):
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

    def rgb_restore(self, why=""):
        """Send de lagrede RGB-fargene til enhetene (oppretter RGB-siden i bakgrunnen ved behov)."""
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

    def _on_tab(self, stack, _p):
        # RGB-fanen (og OpenRGB) startes først når du åpner den – eller av rgb_restore ved oppstart
        if stack.get_visible_child_name() == "rgb":
            self.ensure_rgb_page()
        lz = getattr(self, "_lazy", {}).get(stack.get_visible_child_name())
        if lz and lz[3] is None:
            import importlib
            page = getattr(importlib.import_module(lz[1]), lz[2])()
            page.set_hexpand(True)
            page.set_vexpand(True)
            lz[0].append(page)
            lz[3] = page
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

    def _menu_actions(self):
        for name, fn in (("syscheck", lambda *_: self._open_syscheck(None)),
                         ("mini", self._open_mini), ("welcome", self._open_welcome),
                         ("whatsnew", lambda *_: self._open_whatsnew()),
                         ("about", lambda *_: self._open_about())):
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
        self.stack.set_visible_child_name(row.page_name)
        self.split.set_show_content(True)

    def _sync_sidebar(self, *_):
        name = self.stack.get_visible_child_name()
        row = self._rows.get(name) if hasattr(self, "_rows") else None
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
        if not self.get_mapped():                      # skjult: bare det bakgrunnen trenger, ingen tegning/tekst
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

    def do_activate(self):
        win = getattr(self, "win", None)
        if win is None:
            try:
                win = self.win = MonitorWindow(self)
                import background
                win.bg = background.Background(self, win)
                try:
                    import features
                    features.check_rollback()
                except Exception:  # noqa: BLE001
                    pass
            except Exception:  # noqa: BLE001
                applog.crash("Kontrollsenter kunne ikke starte")
                self.quit()
                return
            if IS_WIN:
                import winsupport
                winsupport.listen_for_show(win.bg.show)
            if "--hidden" in sys.argv and win.bg.cfg["background"]:
                return                      # startet ved innlogging: bare ikon i statusfeltet
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
        if winsupport.already_running():           # vis vinduet til den som kjører, og avslutt
            sys.exit(0)
    MonitorApp().run(None)
