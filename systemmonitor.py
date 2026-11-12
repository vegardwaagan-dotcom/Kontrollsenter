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
    text = OVERLAY_SETTINGS + ("" if visible else "no_display\n")
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

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.uptime_lbl = Gtk.Label()
        self.uptime_lbl.add_css_class("dim-label")
        header.pack_start(self.uptime_lbl)
        self.batteries = laptop_batteries()
        self.bat_lbl = Gtk.Label()
        self.bat_lbl.add_css_class("dim-label")
        self.bat_lbl.set_visible(bool(self.batteries))
        header.pack_start(self.bat_lbl)
        chk = Gtk.Button(child=Adw.ButtonContent(label="Systemsjekk", icon_name="system-search-symbolic"))
        chk.set_tooltip_text("Sjekk hele systemet for feil og rett dem automatisk")
        chk.connect("clicked", self._open_syscheck)
        header.pack_start(chk)
        news = Gtk.Button(child=Adw.ButtonContent(label="Hva er nytt?", icon_name="starred-symbolic"))
        news.set_tooltip_text("Se alt som er nytt i denne versjonen")
        news.connect("clicked", self._open_whatsnew)
        header.pack_start(news)

        # Bryter for spill-overlay
        self.ov_content = Adw.ButtonContent(icon_name="input-gaming-symbolic")
        self.ov_button = Gtk.ToggleButton(child=self.ov_content, valign=Gtk.Align.CENTER)
        self.ov_button.set_tooltip_text(
            "Slår overlayet i spill av/på (FPS, CPU, GPU og temperaturer).\n"
            "Høyre Shift + F12 slår det også av/på inne i spillet."
        )
        self.ov_button.connect("toggled", self._on_overlay_toggled)
        header.pack_end(self.ov_button)

        # Språkvalg NO | EN – programmet starter på nytt med det nye språket
        lang_box = Gtk.Box(valign=Gtk.Align.CENTER)
        lang_box.add_css_class("linked")
        lang_box.set_tooltip_text("Språk / Language")
        first = None
        for code, short, full in i18n.LANGS:
            b = Gtk.ToggleButton(label=short, active=(code == i18n.CHOICE), tooltip_text=full)
            if first:
                b.set_group(first)
            first = first or b
            b.connect("toggled", self._on_lang, code)
            lang_box.append(b)
        header.pack_end(lang_box)
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

        atexit.register(_cleanup)
        signal.signal(signal.SIGTERM, lambda *_: (_cleanup(), os._exit(0)))
        toolbar.add_top_bar(header)

        # Egen rad til fanene (fylles når fanene er laget) – alltid synlig
        self.tab_row = Gtk.Box(halign=Gtk.Align.CENTER)
        self.tab_row.set_margin_top(4)
        self.tab_row.set_margin_bottom(2)
        tab_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
                                        vscrollbar_policy=Gtk.PolicyType.NEVER, propagate_natural_height=True)
        tab_scroll.set_child(self.tab_row)          # mange faner: kan rulles sidelengs i smale vinduer
        toolbar.add_top_bar(tab_scroll)

        # Opphavsrett – vises øverst på alle faner
        import whatsnew
        copyright_lbl = Gtk.Label(label=f"Copyright © Vegard E. Wågan · Versjon {whatsnew.current_version()}")
        copyright_lbl.add_css_class("caption")
        copyright_lbl.add_css_class("dim-label")
        copyright_lbl.set_margin_top(4)
        copyright_lbl.set_margin_bottom(4)
        toolbar.add_top_bar(copyright_lbl)

        if ensure_overlay_env() or not overlay_env_active():
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
        self.c_cpu = Card(cpu_model(), [BLUE])
        self.c_mem = Card("Minne (RAM)", [GREEN])
        self.c_gpu = Card("GPU", [ORANGE]) if self.nvidia.available else None
        self.c_amd = [Card("AMD GPU", [RED]) for _ in self.amd]
        self.c_disk = Card("Disk", [PURPLE, TEAL], fixed_max=None, legend=["Les", "Skriv"])
        self.c_net = Card("Nettverk", [GREEN, BLUE], fixed_max=None, legend=["Ned", "Opp"])
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
        topbar.append(confirm.reset_button(
            "Oversikt",
            "• Strømmodus settes til Balansert (skjermkort 320 W)\n"
            "• Alle vifter settes til Auto\n"
            "• Spill-overlay slås på\n"
            "• Målt toppfart for strømmodusene nullstilles",
            self._reset_overview))
        page.append(topbar)
        page.append(self.power)
        self.fans = FanCard(self.nvidia.available)
        page.append(self.fans)
        self.connect("close-request", lambda *_: self.fans.all_auto_now() or False)
        page.append(flow)
        self.diskspace = DiskSpaceCard()
        page.append(self.diskspace)
        page.append(self.c_temp)

        css = Gtk.CssProvider()
        if hasattr(css, "load_from_string"):
            css.load_from_string(CSS.decode())
        else:
            css.load_from_data(CSS, -1)
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.set_child(page)

        # Faner: Oversikt og RGB
        stack = Adw.ViewStack()
        import hardware
        self.hw = hardware.present()          # RGB, Logitech, CPU-skjerm, Wi-Fi og Bluetooth vises bare hvis de finnes
        stack.add_titled_with_icon(scroller, "oversikt", "Oversikt", "utilities-system-monitor-symbolic")
        self.rgb_holder = Gtk.Box()
        if self.hw["rgb"]:
            stack.add_titled_with_icon(self.rgb_holder, "rgb", "RGB", "applications-graphics-symbolic")
        self.logi_holder = Gtk.Box()
        if self.hw["logitech"]:
            stack.add_titled_with_icon(self.logi_holder, "logitech", "Logitech", "input-mouse-symbolic")
        self.logi_page = None
        self.lcd_holder = Gtk.Box()
        if self.hw["lcd"]:
            stack.add_titled_with_icon(self.lcd_holder, "cpuskjerm", "CPU-skjerm", "video-display-symbolic")
        self.lcd_page = None
        self.prog_holder = Gtk.Box()
        stack.add_titled_with_icon(self.prog_holder, "programmer", "Programmer", "system-software-install-symbolic")
        self.prog_page = None
        self.audio_holder = Gtk.Box()
        stack.add_titled_with_icon(self.audio_holder, "lyd", "Lyd", "audio-speakers-symbolic")
        self.audio_page = None
        self.wifi_holder = Gtk.Box()
        if self.hw["wifi"]:
            stack.add_titled_with_icon(self.wifi_holder, "wifi", "Wi-Fi", "network-wireless-symbolic")
        self.wifi_page = None
        # Faner som lastes først når de åpnes: navn -> (holder, modul, klasse)
        self._lazy = {}
        for name, title, icon, mod, cls in (
                ("bluetooth", "Bluetooth", "bluetooth-symbolic", "bluetooth", "BluetoothPage"),
                ("spill", "Spill", "input-gaming-symbolic", "games", "GamesPage"),
                ("verktoy", "Verktøy", "applications-utilities-symbolic", "tools", "ToolsPage")):
            if name == "bluetooth" and not self.hw["bluetooth"]:
                continue
            if os.path.exists(os.path.join(APP_DIR, mod + ".py")):
                holder = Gtk.Box()
                stack.add_titled_with_icon(holder, name, title, icon)
                self._lazy[name] = [holder, mod, cls, None]
        self.msi_page = None
        import msi
        if msi.is_msi():                      # MSI-fanen vises bare på MSI-maskiner
            self.msi_holder = Gtk.Box()
            stack.add_titled_with_icon(self.msi_holder, "msi", "MSI", "computer-laptop-symbolic")
        stack.connect("notify::visible-child-name", self._on_tab)
        header.set_title_widget(Adw.WindowTitle(title="Kontrollsenter"))
        switcher = Adw.ViewSwitcher(stack=stack, policy=Adw.ViewSwitcherPolicy.WIDE)
        self.tab_row.append(switcher)
        toolbar.set_content(stack)
        if os.environ.get("SYSTEMMONITOR_START_TAB"):          # åpne en bestemt fane
            GLib.idle_add(lambda: (stack.set_visible_child_name(os.environ["SYSTEMMONITOR_START_TAB"]), False)[1])
        self.rgb_page = None
        self.set_content(toolbar)

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
        self.reset_lbl.set_label(f"Tilbakestilt til fabrikkstandard ✓ {time.strftime('%H:%M')}")

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
            g.set_content_height(round(80 * f))

    def _on_lang(self, btn, code):
        if not btn.get_active() or code == i18n.CHOICE:
            return
        i18n.set_lang(code)
        i18n.CHOICE = code
        if i18n.resolve(code) == i18n.LANG:       # samme språk som nå – bare lagre valget
            return
        self.reset_lbl.set_label(i18n.tr("Programmet starter på nytt med nytt språk …"))

        def restart():
            import sys
            try:
                set_overlay(False)
                self.fans.all_auto_now()
            except Exception:  # noqa: BLE001
                pass
            os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)])
        GLib.timeout_add(400, restart)

    def _open_syscheck(self, _btn):
        import syscheck
        syscheck.SysCheckDialog().present(self)

    def _on_tab(self, stack, _p):
        # RGB-fanen (og OpenRGB) startes først når du åpner den
        if stack.get_visible_child_name() == "rgb" and self.rgb_page is None:
            import rgb
            self.rgb_page = rgb.RgbPage()
            self.rgb_page.set_hexpand(True)
            self.rgb_page.set_vexpand(True)
            self.rgb_holder.append(self.rgb_page)
        lz = getattr(self, "_lazy", {}).get(stack.get_visible_child_name())
        if lz and lz[3] is None:
            import importlib
            page = getattr(importlib.import_module(lz[1]), lz[2])()
            page.set_hexpand(True)
            page.set_vexpand(True)
            lz[0].append(page)
            lz[3] = page
        if stack.get_visible_child_name() == "msi" and self.msi_page is None:
            import msi
            self.msi_page = msi.MsiPage()
            self.msi_page.set_hexpand(True)
            self.msi_page.set_vexpand(True)
            self.msi_holder.append(self.msi_page)
        if stack.get_visible_child_name() == "lyd" and self.audio_page is None:
            import audio
            self.audio_page = audio.AudioPage()
            self.audio_page.set_hexpand(True)
            self.audio_page.set_vexpand(True)
            self.audio_holder.append(self.audio_page)
        if stack.get_visible_child_name() == "wifi" and self.wifi_page is None:
            import wifi
            self.wifi_page = wifi.WifiPage()
            self.wifi_page.set_hexpand(True)
            self.wifi_page.set_vexpand(True)
            self.wifi_holder.append(self.wifi_page)
        if stack.get_visible_child_name() == "programmer" and self.prog_page is None:
            import programs
            self.prog_page = programs.ProgramsPage()
            self.prog_page.set_hexpand(True)
            self.prog_page.set_vexpand(True)
            self.prog_holder.append(self.prog_page)
        if stack.get_visible_child_name() == "cpuskjerm" and self.lcd_page is None:
            import lcd
            self.lcd_page = lcd.LcdPage()
            self.lcd_page.set_hexpand(True)
            self.lcd_page.set_vexpand(True)
            self.lcd_holder.append(self.lcd_page)
        if stack.get_visible_child_name() == "logitech" and self.logi_page is None:
            import logitech
            self.logi_page = logitech.LogitechPage()
            self.logi_page.set_hexpand(True)
            self.logi_page.set_vexpand(True)
            self.logi_holder.append(self.logi_page)

    def _on_overlay_toggled(self, btn):
        on = btn.get_active()
        set_overlay(on)
        save_overlay_pref(on)
        self.ov_content.set_label("Overlay i spill: PÅ" if on else "Overlay i spill: AV")
        if on:
            btn.add_css_class("suggested-action")
        else:
            btn.remove_css_class("suggested-action")

    def _open_whatsnew(self, *_):
        import whatsnew
        whatsnew.WhatsNewDialog().present(self)

    def cpu_temp_now(self):
        return getattr(self, "_cpu_t", None)

    def gpu_temp_now(self):
        d = self.nvidia.data if self.nvidia.available else None
        return d.get("temp") if d else None

    def update(self):
        temps = hwmon_temps()

        # CPU
        u = self.cpu.usage()
        total = u.get("cpu", 0)
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
            la = os.getloadavg()
            parts.append(f"last {la[0]:.2f}")
        except OSError:
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
            sv = os.statvfs(os.path.expanduser("~"))
            tot = sv.f_blocks * sv.f_frsize
            free = sv.f_bavail * sv.f_frsize
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

        # Oppetid
        up = float((read("/proc/uptime", "0") or "0").split()[0])
        h, rem = divmod(int(up), 3600)
        self.uptime_lbl.set_label(f"Oppetid {h} t {rem // 60} min")
        return True


class MonitorApp(Adw.Application):
    def __init__(self):
        app_id = os.environ.get("SYSTEMMONITOR_APP_ID", "no.waagan.Systemmonitor")  # for testing
        super().__init__(application_id=app_id)

    def do_activate(self):
        win = getattr(self, "win", None)
        if win is None:
            win = self.win = MonitorWindow(self)
            import background
            win.bg = background.Background(self, win)
            if "--hidden" in sys.argv and win.bg.cfg["background"]:
                return                      # startet ved innlogging: bare ikon i statusfeltet
            win.present()
            import whatsnew
            if whatsnew.should_show():
                GLib.timeout_add(800, lambda: win._open_whatsnew() or False)
            return
        win.set_visible(True)
        win.present()


if __name__ == "__main__":
    MonitorApp().run(None)
