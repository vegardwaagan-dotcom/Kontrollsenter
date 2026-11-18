"""Spill-fanen i Kontrollsenter.

* Steam-spill: startvalg per spill med avkrysning (MangoHud, GameMode, Wayland, DLSS, FSR, HDR, logg),
  Proton-versjon og egne argumenter. Skriver localconfig.vdf / config.vdf (Steam må være lukket),
  med sikkerhetskopi.
* Proton-GE: se installerte versjoner, installer nyeste med ett klikk (SHA512-kontrollert), slett gamle.
* Kontrollere: batteri og knappetest.
"""
import glob
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402

from tabbed import TabbedPage  # noqa: E402
import i18n  # noqa: E402

import vdf  # noqa: E402

HOME = Path.home()
IS_WIN = sys.platform == "win32"


def _steam_dir():
    if IS_WIN:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
                p = Path(winreg.QueryValueEx(k, "SteamPath")[0])
            if (p / "steamapps").is_dir():
                return p
        except OSError:
            pass
        for p in (Path(r"C:\Program Files (x86)\Steam"), Path(r"C:\Program Files\Steam")):
            if (p / "steamapps").is_dir():
                return p
        return None
    return next((p for p in (HOME / ".local/share/Steam", HOME / ".steam/steam",
                             HOME / ".var/app/com.valvesoftware.Steam/data/Steam") if (p / "steamapps").is_dir()), None)


STEAM = _steam_dir()
COMPAT = STEAM / "compatibilitytools.d" if STEAM else None
GE_API = "https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases/latest"

# (nøkkel, navn, forklaring, type, verdi)
OPTIONS = [
    ("mangohud", "MangoHud", "Viser FPS, temperatur og last i spillet", "wrap", "mangohud"),
    ("gamemode", "GameMode", "Ber Linux prioritere spillet (mer jevn ytelse)", "wrap", "gamemoderun"),
    ("wayland", "Wayland", "Kjør spillet direkte i Wayland (Proton 10+/GE) – kan gi lavere forsinkelse", "env",
     "PROTON_ENABLE_WAYLAND=1"),
    ("nvapi", "DLSS / NVIDIA", "Slår på DLSS og NVIDIA Reflex i spill som støtter det", "env", "PROTON_ENABLE_NVAPI=1"),
    ("fsr", "FSR-oppskalering", "AMD FSR når spillet kjører i lavere oppløsning i fullskjerm", "env",
     "WINE_FULLSCREEN_FSR=1"),
    ("hdr", "HDR", "HDR i spill som støtter det (krever HDR-skjerm og Wayland)", "env",
     "PROTON_ENABLE_HDR=1 ENABLE_HDR_WSI=1"),
    ("log", "Proton-logg", "Lager steam-<id>.log i hjemmemappen – for feilsøking", "env", "PROTON_LOG=1"),
]
if IS_WIN:            # MangoHud, GameMode, Wayland og Proton finnes ikke på Windows – bare egne argumenter
    OPTIONS = []
BUILTIN_PROTON = {"Proton - Experimental": "proton_experimental", "Proton Hotfix": "proton_hotfix",
                  "Proton 10.0": "proton_10", "Proton 9.0 (Beta)": "proton_9", "Proton 9.0": "proton_9",
                  "Proton 8.0": "proton_8", "Proton 7.0": "proton_7"}


# --------------------------------------------------------------------------
# Steam-data
# --------------------------------------------------------------------------
def active_user():
    """Steam-kontoen som sist var logget inn (mappe under userdata)."""
    if not STEAM:
        return None
    try:
        users = vdf.get(vdf.load(STEAM / "config/loginusers.vdf"), "users") or {}
    except OSError:
        users = {}
    best = None
    for sid, u in users.items():
        recent = str(vdf.get(u, "MostRecent", default="0")) == "1"
        ts = int(vdf.get(u, "Timestamp", default="0") or 0)
        key = (recent, ts)
        if best is None or key > best[0]:
            best = (key, sid)
    if best:
        acc = int(best[1]) - 76561197960265728
        if (STEAM / "userdata" / str(acc)).is_dir():
            return str(acc)
    dirs = sorted(glob.glob(str(STEAM / "userdata/*/config/localconfig.vdf")), key=os.path.getmtime)
    return Path(dirs[-1]).parent.parent.name if dirs else None


def installed_games():
    libs = [STEAM / "steamapps"]
    try:
        lf = vdf.load(STEAM / "steamapps/libraryfolders.vdf")
        for v in (vdf.get(lf, "libraryfolders") or {}).values():
            if isinstance(v, dict) and v.get("path"):
                libs.append(Path(v["path"]) / "steamapps")
    except OSError:
        pass
    games, seen = [], set()
    for lib in libs:
        for f in glob.glob(str(lib / "appmanifest_*.acf")):
            try:
                st = vdf.get(vdf.load(f), "AppState") or {}
            except (OSError, ValueError):
                continue
            aid, name = st.get("appid"), st.get("name", "")
            if not aid or aid in seen or re.search(r"Proton|Steam Linux Runtime|Steamworks Common", name):
                continue
            seen.add(aid)
            games.append({"appid": aid, "name": name})
    return sorted(games, key=lambda g: g["name"].lower())


def compat_tools():
    tools = [("", "Standard (Steam velger)")]
    common = STEAM / "steamapps/common"
    for disp, internal in BUILTIN_PROTON.items():
        if (common / disp).is_dir():
            tools.append((internal, disp))
    if COMPAT and COMPAT.is_dir():
        for d in sorted(COMPAT.iterdir(), reverse=True):
            if (d / "compatibilitytool.vdf").exists() or (d / "proton").exists():
                tools.append((d.name, d.name))
    return tools


def header_image(appid):
    lc = STEAM / "appcache/librarycache"
    for p in (lc / appid / "header.jpg", lc / f"{appid}_header.jpg", lc / appid / "library_header.jpg"):
        if p.exists():
            return str(p)
    for p in glob.glob(str(lc / appid / "*" / "header.jpg")):
        return p
    return None


def steam_running():
    if IS_WIN:
        import psutil
        return any((p.info.get("name") or "").lower() == "steam.exe" for p in psutil.process_iter(["name"]))
    return subprocess.run(["pgrep", "-x", "steam"], capture_output=True).returncode == 0


def parse_options(s):
    """«PROTON_LOG=1 gamemoderun mangohud %command% -dx11» -> (avkryssede nøkler, ukjent prefiks, argumenter)"""
    s = s or ""
    if "%command%" in s:
        pre, post = s.split("%command%", 1)
    else:
        pre, post = "", s
    toks = pre.split()
    on, unknown = set(), []
    for key, _n, _d, kind, val in OPTIONS:
        parts = val.split()
        if all(p in toks for p in parts):
            on.add(key)
            for p in parts:
                toks.remove(p)
    unknown = toks
    return on, unknown, post.strip()


def build_options(on, unknown, args):
    env, wraps = [], []
    for key, _n, _d, kind, val in OPTIONS:
        if key in on:
            (env if kind == "env" else wraps).append(val)
    wraps.sort(key=lambda w: w != "gamemoderun")       # vanlig rekkefølge: gamemoderun mangohud %command%
    uenv = [t for t in unknown if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t)]
    uwrap = [t for t in unknown if t not in uenv]
    pre = env + uenv + wraps + uwrap
    if not pre and not args:
        return ""
    return " ".join(pre + ["%command%"] + ([args] if args else []))


def load_settings(user):
    lc = STEAM / "userdata" / user / "config/localconfig.vdf"
    cfg = STEAM / "config/config.vdf"
    local = vdf.load(lc)
    conf = vdf.load(cfg)
    apps = vdf.get(local, "UserLocalConfigStore", "Software", "Valve", "Steam", "apps") or {}
    mapping = vdf.get(conf, "InstallConfigStore", "Software", "Valve", "Steam", "CompatToolMapping") or {}
    return local, conf, apps, mapping


def save_settings(user, changes):
    """changes: {appid: {"launch": str, "proton": str}}"""
    lc = STEAM / "userdata" / user / "config/localconfig.vdf"
    cfg = STEAM / "config/config.vdf"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(lc, f"{lc}.bak-systemmonitor-{stamp}")
    shutil.copy2(cfg, f"{cfg}.bak-systemmonitor-{stamp}")
    local, conf = vdf.load(lc), vdf.load(cfg)
    apps = vdf.ensure(local, "UserLocalConfigStore", "Software", "Valve", "Steam", "apps")
    mapping = vdf.ensure(conf, "InstallConfigStore", "Software", "Valve", "Steam", "CompatToolMapping")
    for aid, ch in changes.items():
        if "launch" in ch:
            vdf.ensure(apps, aid)["LaunchOptions"] = ch["launch"]
        if "proton" in ch:
            if ch["proton"]:
                mapping[aid] = {"name": ch["proton"], "config": "", "priority": "250"}
            else:
                mapping.pop(aid, None)
    vdf.dump(local, lc)
    vdf.dump(conf, cfg)
    # behold bare de 3 nyeste sikkerhetskopiene
    for f in (lc, cfg):
        for old in sorted(glob.glob(f"{f}.bak-systemmonitor-*"))[:-3]:
            os.unlink(old)


# --------------------------------------------------------------------------
# GE-Proton
# --------------------------------------------------------------------------
def ge_installed():
    if not COMPAT or not COMPAT.is_dir():
        return []
    return sorted((d for d in COMPAT.iterdir() if d.is_dir() and d.name.lower().startswith("ge-proton")),
                  key=lambda d: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", d.name)], reverse=True)


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "Systemmonitor", "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=timeout)


def ge_latest():
    with _get(GE_API) as r:
        rel = json.load(r)
    tar = next(a for a in rel["assets"] if a["name"].endswith(".tar.gz"))
    sha = next((a for a in rel["assets"] if a["name"].endswith(".sha512sum")), None)
    return rel["tag_name"], tar["browser_download_url"], tar["size"], sha["browser_download_url"] if sha else None


def ge_install(progress):
    tag, url, size, sha_url = ge_latest()
    if (COMPAT / tag).exists():
        return tag, "allerede installert"
    COMPAT.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(dir=str(COMPAT.parent))
    path = os.path.join(tmp, f"{tag}.tar.gz")
    h = hashlib.sha512()
    done = 0
    with _get(url, timeout=60) as r, open(path, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            h.update(chunk)
            done += len(chunk)
            progress(done / size if size else 0, f"Laster ned {tag}: {done / 1e6:.0f} av {size / 1e6:.0f} MB")
    if sha_url:
        with _get(sha_url) as r:
            want = r.read().decode().split()[0]
        if want.lower() != h.hexdigest():
            shutil.rmtree(tmp, ignore_errors=True)
            raise RuntimeError("sjekksummen stemmer ikke – nedlastingen er ødelagt")
    progress(1, f"Pakker ut {tag} …")
    with tarfile.open(path) as t:
        t.extractall(COMPAT, filter="data")
    shutil.rmtree(tmp, ignore_errors=True)
    return tag, "installert"


# --------------------------------------------------------------------------
# Kontrollere
# --------------------------------------------------------------------------
def controllers():
    res = []
    for js in sorted(glob.glob("/sys/class/input/js*")):
        name = (Path(js) / "device/name").read_text().strip() if (Path(js) / "device/name").exists() else js
        if re.search(r"mouse|keyboard|touchpad|virtual", name, re.I):
            continue
        res.append({"dev": "/dev/input/" + os.path.basename(js), "name": name})
    bats = []
    for p in glob.glob("/sys/class/power_supply/*"):
        try:
            if (Path(p) / "scope").read_text().strip() != "Device":
                continue
            model = (Path(p) / "model_name").read_text().strip() if (Path(p) / "model_name").exists() else os.path.basename(p)
            cap = (Path(p) / "capacity").read_text().strip() if (Path(p) / "capacity").exists() else None
            lvl = (Path(p) / "capacity_level").read_text().strip() if (Path(p) / "capacity_level").exists() else ""
            bats.append((model, f"{cap} %" if cap else lvl))
        except OSError:
            continue
    return res, bats


class JoyTester(Gtk.Window):
    """Viser knapper og styrespaker live (leser /dev/input/jsN)."""

    def __init__(self, parent, dev, name):
        super().__init__(title=f"Knappetest – {name}", transient_for=parent, modal=True,
                         default_width=560, default_height=420)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(16)
        self.set_child(box)
        box.append(Gtk.Label(label="Trykk på knappene og beveg styrespakene.", xalign=0))
        self.btns = Gtk.FlowBox(max_children_per_line=10, selection_mode=Gtk.SelectionMode.NONE)
        box.append(self.btns)
        self.axes = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.append(self.axes)
        self.b, self.a = {}, {}
        try:
            self.fd = os.open(dev, os.O_RDONLY | os.O_NONBLOCK)
        except OSError as e:
            box.append(Gtk.Label(label=f"Kunne ikke åpne {dev}: {e}"))
            self.fd = None
            return
        self.src = GLib.unix_fd_add_full(GLib.PRIORITY_DEFAULT, self.fd, GLib.IOCondition.IN, self._read)
        self.connect("close-request", self._close)

    def _read(self, fd, _cond):
        try:
            data = os.read(fd, 8 * 64)
        except BlockingIOError:
            return True
        except OSError:
            return False
        for i in range(0, len(data) - 7, 8):
            _t, val, typ, num = struct.unpack("IhBB", data[i:i + 8])
            typ &= ~0x80
            if typ == 1:
                if num not in self.b:
                    lab = Gtk.Label(label=f" {num} ", margin_start=4, margin_end=4)
                    lab.add_css_class("card")
                    self.btns.append(lab)
                    self.b[num] = lab
                (self.b[num].add_css_class if val else self.b[num].remove_css_class)("accent")
                self.b[num].set_label(f" {'●' if val else ''}{num} ")
            elif typ == 2:
                if num not in self.a:
                    row = Gtk.Box(spacing=8)
                    row.append(Gtk.Label(label=f"Akse {num}", width_chars=7, xalign=0))
                    bar = Gtk.LevelBar(min_value=0, max_value=65535, hexpand=True)
                    row.append(bar)
                    self.axes.append(row)
                    self.a[num] = bar
                self.a[num].set_value(val + 32768)
        return True

    def _close(self, *_):
        if self.fd is not None:
            GLib.source_remove(self.src)
            os.close(self.fd)
        return False


# --------------------------------------------------------------------------
# Fanen
# --------------------------------------------------------------------------
def card(title, subtitle=None):
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    outer.add_css_class("card")
    inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    for side, v in (("top", 14), ("bottom", 14), ("start", 16), ("end", 16)):
        getattr(inner, f"set_margin_{side}")(v)
    outer.append(inner)
    t = Gtk.Label(label=title, xalign=0)
    t.add_css_class("heading")
    inner.append(t)
    if subtitle:
        s = Gtk.Label(label=subtitle, xalign=0, wrap=True)
        s.add_css_class("caption")
        s.add_css_class("dim-label")
        inner.append(s)
    return outer, inner


class GamesPage(TabbedPage):
    def __init__(self):
        super().__init__("spill")
        self.changes = {}
        self.tab("spillene", "Spillene")
        try:
            self._launcher()
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("spill-launcher")
        self.tab("statistikk", "Statistikk")
        try:
            import gamestats_ui
            stats = gamestats_ui.StatsCard(card)
            self.box.append(stats)
            if gamestats_ui.gamestats.wow_flavors():     # alt om WoW samlet i ett kort, rett under statistikken
                wow = gamestats_ui.WowPlusCard(card)
                stats.also = wow.load
                self.box.append(wow)
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("spillstatistikk")
        self._sessions_card()
        self.tab("klipp", "Klipp")
        try:
            import clips_ui
            self.box.append(clips_ui.ClipsCard(card))
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("klipp")
        self.tab("bibliotek", "Bibliotek")
        self._steam_card()
        if not IS_WIN:                                  # Proton og lagrede spill i Proton-mappene (Linux)
            self._ge_card()
            try:
                import savegames
                savegames.build_card(self, card)
            except Exception:  # noqa: BLE001
                import applog
                applog.log.exception("lagrede spill")
        self.tab("profiler", "Spillprofiler")
        try:
            import games_auto
            games_auto.build_cards(self)
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("spillprofiler")
        if not IS_WIN:
            self.tab("kontrollere", "Kontrollere")
            self._ctrl_card()
        self.finish()

    # --- Alle spillene med cover (launcher) --------------------------------------
    def _reload_launcher(self):
        import launcher

        def work():
            gs = launcher.all_games()
            GLib.idle_add(self._show_games, gs)
        threading.Thread(target=work, daemon=True).start()

    def _launcher(self):
        import launcher
        head = Gtk.Box(spacing=10)
        t = Gtk.Label(label=i18n.tr("Trykk på et spill for å starte det. Scener, temaer og spillprofiler for spillet slår "
                                    "seg på av seg selv. «Spill sammen» spør de andre i huset om de blir med."),
                      xalign=0, wrap=True, hexpand=True)
        t.add_css_class("dim-label")
        head.append(t)
        self.box.append(head)
        import apps_ui
        self.box.append(apps_ui.need("launcher", on_done=self._reload_launcher,
                                     on_change=lambda _k: self._reload_launcher(),
                                     text="Spillene dine hentes fra Steam, Heroic (Epic/GOG) og Lutris/Battle.net. "
                                          "Installer minst én spillbutikk."))
        self.lflow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True, min_children_per_line=2,
                                 max_children_per_line=8, column_spacing=14, row_spacing=16, halign=Gtk.Align.START)
        self.box.append(self.lflow)
        self.lmsg = Gtk.Label(xalign=0)
        self.lmsg.add_css_class("dim-label")
        self.box.append(self.lmsg)
        css = Gtk.CssProvider()
        css.load_from_string(""".ks-cover { border-radius: 16px; }
            .ks-cover-card { border-radius: 18px; padding: 0; }
            .ks-cover-blank { font-size: 64px; font-weight: 800; color: white; border-radius: 16px;
              background-image: linear-gradient(135deg, #5b8cff, #8a5cff); }
            .ks-cover-name { font-weight: 800; color: white; text-shadow: 0 1px 3px black; }
            .ks-cover-fade { background-image: linear-gradient(transparent 45%, alpha(black, 0.85)); border-radius: 16px; }
            button.ks-cover-play { border-radius: 99px; min-width: 44px; min-height: 44px; padding: 0; color: white;
              background-image: linear-gradient(135deg, #5b8cff, #8a5cff); }""")
        import theme
        theme.add_css(css.to_string(), Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 5)    # følger temaet

        def work():
            gs = launcher.all_games()
            GLib.idle_add(self._show_games, gs)
            if any(g["store"] == "steam" and not g.get("cover") for g in gs):
                launcher.fetch_missing_covers(gs)
                GLib.idle_add(self._show_games, gs)
        threading.Thread(target=work, daemon=True).start()

    def _show_games(self, gs):
        import launcher
        import time as _t
        while (c := self.lflow.get_first_child()) is not None:
            self.lflow.remove(c)
        try:                                            # «Vis spill fra»: bare én butikk
            import apps
            only = apps.get_use("launcher")
        except Exception:  # noqa: BLE001
            only = None
        if only:
            gs = [g for g in gs if g["store"] == only or g["store"].startswith(only + "-")]
        for g in gs:
            ov = Gtk.Overlay(halign=Gtk.Align.CENTER)
            ov.add_css_class("ks-cover-card")
            cov = g.get("cover")
            pic = None
            if cov and not str(cov).startswith("http") and os.path.exists(cov):
                try:
                    from gi.repository import Gdk, GdkPixbuf
                    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(cov, 168, 252, False)
                    pic = Gtk.Picture.new_for_paintable(Gdk.Texture.new_for_pixbuf(pb))
                except Exception:  # noqa: BLE001
                    pic = None
            if pic is None:                              # uten cover: fargefelt med forbokstaven
                pic = Gtk.Label(label=(g["name"] or "?")[:1].upper())
                pic.add_css_class("ks-cover-blank")
            else:
                pic.set_content_fit(Gtk.ContentFit.COVER)
                pic.set_can_shrink(True)
            pic.set_size_request(168, 252)
            pic.set_halign(Gtk.Align.CENTER)
            pic.add_css_class("ks-cover")
            ov.set_child(pic)
            fade = Gtk.Box(hexpand=True, vexpand=True)
            fade.add_css_class("ks-cover-fade")
            ov.add_overlay(fade)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.END, margin_start=10,
                          margin_end=10, margin_bottom=10)
            nm = Gtk.Label(label=g["name"], xalign=0, wrap=True, lines=2, ellipsize=3, max_width_chars=16)
            nm.add_css_class("ks-cover-name")
            col.append(nm)
            sub = ("sist " + _t.strftime("%d.%m", _t.localtime(g["last"]))) if g.get("last") else \
                {"steam": "Steam", "lutris": "Lutris"}.get(g["store"], "Heroic")
            sl = Gtk.Label(label=sub, xalign=0)
            sl.add_css_class("caption")
            sl.set_opacity(0.8)
            col.append(sl)
            ov.add_overlay(col)
            btns = Gtk.Box(spacing=6, halign=Gtk.Align.END, valign=Gtk.Align.START, margin_top=8, margin_end=8)
            inv = Gtk.Button(icon_name="system-users-symbolic", tooltip_text=i18n.tr("Spill sammen – inviter de andre"))
            inv.add_css_class("circular")
            inv.add_css_class("osd")
            inv.connect("clicked", lambda _b, g=g: self.lmsg.set_label(launcher.invite(g)))
            btns.append(inv)
            play = Gtk.Button(icon_name="media-playback-start-symbolic", tooltip_text=i18n.tr("Start"))
            play.add_css_class("ks-cover-play")
            play.connect("clicked", lambda _b, g=g: (launcher.launch(g), self.lmsg.set_label(
                i18n.tr("Starter ") + g["name"] + " …")))
            btns.append(play)
            ov.add_overlay(btns)
            click = Gtk.GestureClick()
            click.connect("released", lambda *_a, g=g: (launcher.launch(g), self.lmsg.set_label(
                i18n.tr("Starter ") + g["name"] + " …")))
            pic.add_controller(click)
            pic.set_cursor_from_name("pointer")
            self.lflow.append(ov)
        if not gs:
            self.lmsg.set_label(i18n.tr("Fant ingen installerte spill (Steam, Heroic eller Lutris)."))
        return False

    # --- Siste spilløkter -------------------------------------------------------
    def _sessions_card(self):
        import games_auto
        import time as _t
        ss = list(reversed(games_auto.load_sessions()))[:8]
        c, i = card("Siste spilløkter", "Rapport etter hver økt: spilletid, FPS («1 % low» = de tregeste "
                                        "bildene), høyeste temperaturer og strømforbruk. Slås av og på under "
                                        "fanen Spillprofiler.")
        if not ss:
            import ui
            i.append(ui.empty("ks-games-symbolic", "Ingen spilløkter ennå",
                              "Start et Steam-spill, så kommer rapporten her når du avslutter."))
        else:
            grid = Gtk.Grid(column_spacing=18, row_spacing=6)
            heads = ["Spill", "Når", "Tid", "FPS", "1 % low", "CPU maks", "GPU maks", "Strøm"]
            for col, h in enumerate(heads):
                lab = Gtk.Label(label=h, xalign=0 if col < 2 else 1)
                lab.add_css_class("caption-heading")
                lab.add_css_class("dim-label")
                grid.attach(lab, col, 0, 1, 1)
            for r, s_ in enumerate(ss, 1):
                vals = [s_["name"], _t.strftime("%d.%m %H:%M", _t.localtime(s_["start"])), f"{s_['minutes']} min",
                        str(s_.get("fps") or "–"), str(s_.get("low") or "–"),
                        f"{s_['max_cpu']} °C" if s_.get("max_cpu") else "–",
                        f"{s_['max_gpu']} °C" if s_.get("max_gpu") else "–",
                        f"{s_['watts']} W · {s_['kr']:.2f} kr" if s_.get("watts") else "–"]
                for col, v in enumerate(vals):
                    lab = Gtk.Label(label=v, xalign=0 if col < 2 else 1, ellipsize=3 if col == 0 else 0)
                    if col == 0:
                        lab.set_hexpand(True)
                        lab.set_max_width_chars(28)
                    else:
                        lab.add_css_class("numeric")
                    grid.attach(lab, col, r, 1, 1)
            i.append(grid)
            drops = [(s_, d) for s_ in ss[:3] for d in (s_.get("drops") or [])]
            if drops:
                h = Gtk.Label(label="FPS-dropp i de siste øktene", xalign=0)
                h.add_css_class("heading")
                h.set_margin_top(8)
                i.append(h)
                for s_, d in drops[-6:]:
                    t = _t.strftime("%H:%M", _t.localtime(d["t"]))
                    extra = [f"CPU {d['cpu_t']:.0f} °C" if d.get("cpu_t") else None,
                             f"GPU {d['gpu_t']:.0f} °C" if d.get("gpu_t") else None,
                             f"CPU {d['cpu_l']} % · GPU {d['gpu_l']} % last",
                             ("kjørte: " + ", ".join(d["top"])) if d.get("top") else None]
                    lab = Gtk.Label(label=f"{s_['name']} kl. {t}: {d['normal']} → {d['fps']} FPS – {d['why']}\n"
                                    + " · ".join(e for e in extra if e), xalign=0, wrap=True)
                    lab.add_css_class("caption")
                    i.append(lab)
        self.box.append(c)

    # --- Steam-spill ----------------------------------------------------------
    def _steam_card(self):
        c, i = card("Steam-spill", "Kryss av for det du vil bruke i hvert spill. Kontrollsenter skriver startvalgene "
                                   "inn i Steam for deg – du slipper å huske kommandoene.")
        self.box.append(c)
        if not STEAM:
            import ui
            i.append(ui.empty("ks-games-symbolic", "Fant ikke Steam.",
                              "Installer Steam, så dukker spillene dine opp her."))
            return
        bar = Gtk.Box(spacing=8)
        self.steam_status = Gtk.Label(xalign=0, hexpand=True, wrap=True)
        bar.append(self.steam_status)
        self.close_btn = Gtk.Button(label="Lukk Steam")
        self.close_btn.connect("clicked", self._close_steam)
        bar.append(self.close_btn)
        self.save_btn = Gtk.Button(label="Lagre endringer")
        self.save_btn.add_css_class("suggested-action")
        self.save_btn.connect("clicked", self._save)
        bar.append(self.save_btn)
        i.append(bar)
        self.games_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.games_list.add_css_class("boxed-list")
        i.append(self.games_list)
        self.user = active_user()
        try:
            _l, _c, self.apps, self.mapping = load_settings(self.user)
        except (OSError, ValueError, TypeError) as e:
            self.steam_status.set_label(f"Kunne ikke lese Steam-innstillingene: {e}")
            return
        self.tools = compat_tools()
        self.has_gamemode = shutil.which("gamemoderun") is not None
        for g in installed_games():
            self.games_list.append(self._game_row(g))
        self._update_steam_state()
        GLib.timeout_add_seconds(3, lambda: (self._update_steam_state(), True)[1])

    def _game_row(self, g):
        aid = g["appid"]
        cur = (vdf.get(self.apps, aid, "LaunchOptions") or "")
        on, unknown, args = parse_options(cur)
        base = build_options(on, unknown, args)        # slik programmet leser dagens valg
        prot = (vdf.get(self.mapping, aid, "name") or "")
        exp = Gtk.Expander()
        head = Gtk.Box(spacing=12)
        img = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, can_shrink=True)
        img.set_size_request(138, 64)
        hi = header_image(aid)
        if hi:
            try:
                img.set_paintable(Gdk.Texture.new_for_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(hi, 276, 128, True)))
            except GLib.Error:
                pass
        head.append(img)
        mid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, hexpand=True)
        t = Gtk.Label(label=g["name"], xalign=0, ellipsize=3)
        t.add_css_class("heading")
        mid.append(t)
        summ = Gtk.Label(xalign=0, ellipsize=3)
        summ.add_css_class("caption")
        summ.add_css_class("dim-label")
        mid.append(summ)
        head.append(mid)
        play = Gtk.Button(icon_name="media-playback-start-symbolic", valign=Gtk.Align.CENTER, tooltip_text="Start spillet")
        play.add_css_class("flat")
        play.connect("clicked", lambda *_: Gio.AppInfo.launch_default_for_uri(f"steam://rungameid/{aid}", None))
        head.append(play)
        exp.set_label_widget(head)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_start=150, margin_bottom=10, margin_end=8)
        grid = Gtk.Grid(column_spacing=16, row_spacing=4)
        checks = {}
        for n, (key, name, desc, _k, _v) in enumerate(OPTIONS):
            cb = Gtk.CheckButton(label=name, active=key in on, tooltip_text=desc)
            if key == "gamemode" and not self.has_gamemode:
                cb.set_sensitive(key in on)
                cb.set_tooltip_text("GameMode er ikke installert på denne maskinen")
            checks[key] = cb
            grid.attach(cb, n % 4, n // 4, 1, 1)
        body.append(grid)
        prow = Gtk.Box(spacing=8)
        prow.append(Gtk.Label(label="Proton-versjon"))
        keys = [k for k, _n in self.tools]
        if prot and prot not in keys:
            self.tools.append((prot, prot))
            keys.append(prot)
        dd = Gtk.DropDown.new_from_strings([n for _k, n in self.tools])
        dd.set_selected(keys.index(prot) if prot in keys else 0)
        prow.append(dd)
        prow.set_visible(not IS_WIN)                    # Proton finnes bare på Linux
        body.append(prow)
        arow = Gtk.Box(spacing=8)
        arow.append(Gtk.Label(label="Egne argumenter"))
        entry = Gtk.Entry(text=args, hexpand=True, placeholder_text="f.eks. -dx11 -skipintro")
        arow.append(entry)
        body.append(arow)
        prev = Gtk.Label(xalign=0, selectable=True, wrap=True)
        prev.add_css_class("caption")
        prev.add_css_class("monospace")
        body.append(prev)
        exp.set_child(body)

        def recompute(*_):
            new_on = {k for k, cb in checks.items() if cb.get_active()}
            s = build_options(new_on, unknown, entry.get_text().strip())
            p = keys[dd.get_selected()] if dd.get_selected() < len(keys) else ""
            prev.set_label("Startvalg: " + (s or "(ingen)"))
            names = [n for k, n, *_ in OPTIONS if k in new_on]
            pname = dict(self.tools).get(p, "") if p else ""
            summ.set_label(" · ".join(x for x in (", ".join(names), pname) if x) or "Standard")
            ch = {}
            if s != base:                        # bare ekte endringer fra deg
                ch["launch"] = s
            if p != prot:
                ch["proton"] = p
            if ch:
                self.changes[aid] = ch
            else:
                self.changes.pop(aid, None)
            self._update_steam_state()
        for cb in checks.values():
            cb.connect("toggled", recompute)
        dd.connect("notify::selected", recompute)
        entry.connect("changed", recompute)
        recompute()
        return exp

    def _update_steam_state(self):
        running = steam_running()
        n = len(self.changes)
        self.close_btn.set_visible(running)
        self.save_btn.set_sensitive(n > 0 and not running)
        self.save_btn.set_label(f"Lagre endringer ({n})" if n else "Lagre endringer")
        if running:
            self.steam_status.set_label("Steam kjører – lukk Steam for å lagre (Steam skriver over endringer mens den kjører).")
        elif n:
            self.steam_status.set_label(f"{n} spill har ulagrede endringer.")
        else:
            self.steam_status.set_label("Steam er lukket. Endringene gjelder neste gang du starter spillet.")
        return False

    def _close_steam(self, *_):
        subprocess.Popen(["steam", "-shutdown"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.steam_status.set_label("Lukker Steam …")

    def _save(self, *_):
        try:
            save_settings(self.user, self.changes)
            n = len(self.changes)
            self.changes = {}
            _l, _c, self.apps, self.mapping = load_settings(self.user)
            while (c := self.games_list.get_first_child()):
                self.games_list.remove(c)
            for g in installed_games():
                self.games_list.append(self._game_row(g))
            import ui
            ui.status(self.steam_status, f"Lagret for {n} spill ✓ (sikkerhetskopi tatt)")
        except Exception as e:  # noqa: BLE001
            self.steam_status.set_label(f"Kunne ikke lagre: {e}")

    # --- GE-Proton --------------------------------------------------------------
    def _ge_card(self):
        c, i = card("GE-Proton", "En forbedret Proton-versjon som får mange spill til å virke bedre (videoer, "
                                 "anti-juks, nye spill). Velg den per spill over, eller som standard i Steam.")
        self.ge_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        i.append(self.ge_list)
        bar = Gtk.Box(spacing=8)
        self.ge_btn = Gtk.Button(label="Installer nyeste GE-Proton")
        self.ge_btn.add_css_class("suggested-action")
        self.ge_btn.connect("clicked", self._ge_install)
        bar.append(self.ge_btn)
        self.ge_prog = Gtk.ProgressBar(hexpand=True, valign=Gtk.Align.CENTER, visible=False)
        bar.append(self.ge_prog)
        i.append(bar)
        self.ge_status = Gtk.Label(xalign=0, wrap=True)
        self.ge_status.add_css_class("caption")
        i.append(self.ge_status)
        self.box.append(c)
        self._fill_ge()

    def _fill_ge(self):
        while (c := self.ge_list.get_first_child()):
            self.ge_list.remove(c)
        inst = ge_installed()
        if not inst:
            import ui
            self.ge_list.append(ui.empty("ks-games-symbolic", "Ingen GE-Proton installert."))
        for n, d in enumerate(inst):
            row = Gtk.Box(spacing=8)
            row.append(Gtk.Label(label=d.name + ("  (nyeste)" if n == 0 else ""), xalign=0, hexpand=True))
            rm = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text="Slett denne versjonen")
            rm.add_css_class("flat")
            rm.set_sensitive(n > 0)
            rm.connect("clicked", lambda *_, d=d: self._ge_remove(d))
            row.append(rm)
            self.ge_list.append(row)

    def _ge_install(self, *_):
        self.ge_btn.set_sensitive(False)
        self.ge_prog.set_visible(True)
        self.ge_status.set_label("Ser etter nyeste versjon …")

        def prog(frac, text):
            GLib.idle_add(lambda: (self.ge_prog.set_fraction(min(frac, 1)), self.ge_status.set_label(text), False)[2])

        def work():
            try:
                tag, what = ge_install(prog)
                msg = f"{tag} er {what} ✓ – start Steam på nytt for å se den"
            except Exception as e:  # noqa: BLE001
                msg = f"Kunne ikke installere GE-Proton: {e}"
            GLib.idle_add(lambda: (self.ge_status.set_label(msg), self.ge_btn.set_sensitive(True),
                                   self.ge_prog.set_visible(False), self._fill_ge(), False)[4])
        threading.Thread(target=work, daemon=True).start()

    def _ge_remove(self, d):
        dlg = Adw.AlertDialog(heading=f"Slette {d.name}?",
                              body="Spill som er satt til denne versjonen bruker Steams standard i stedet.")
        dlg.add_response("cancel", "Avbryt")
        dlg.add_response("rm", "Slett")
        dlg.set_response_appearance("rm", Adw.ResponseAppearance.DESTRUCTIVE)

        def resp(_d, r):
            if r == "rm":
                shutil.rmtree(d, ignore_errors=True)
                self.ge_status.set_label(f"{d.name} er slettet")
                self._fill_ge()
        dlg.connect("response", resp)
        dlg.present(self)

    # --- kontrollere ------------------------------------------------------------
    def _ctrl_card(self):
        c, self.ctrl_box = card("Kontrollere", "Xbox-, PlayStation-, 8BitDo- og andre kontrollere. Fastvare for "
                                               "kontrollere oppdateres via Systemsjekk (fwupd) der det støttes.")
        self.box.append(c)
        self._fill_ctrl()
        GLib.timeout_add_seconds(5, lambda: (self._fill_ctrl(), True)[1])

    def _fill_ctrl(self):
        ch = self.ctrl_box.get_first_child().get_next_sibling().get_next_sibling()
        while ch:
            nxt = ch.get_next_sibling()
            self.ctrl_box.remove(ch)
            ch = nxt
        pads, bats = controllers()
        if not pads:
            import ui
            self.ctrl_box.append(ui.empty("ks-games-symbolic", "Ingen kontroller tilkoblet",
                                          "Koble til med USB eller via Bluetooth-fanen."))
        for p in pads:
            row = Gtk.Box(spacing=8)
            row.append(Gtk.Image.new_from_icon_name("input-gaming-symbolic"))
            row.append(Gtk.Label(label=p["name"], xalign=0, hexpand=True))
            b = Gtk.Button(label="Test knapper")
            b.connect("clicked", lambda *_, p=p: JoyTester(self.get_root(), p["dev"], p["name"]).present())
            row.append(b)
            self.ctrl_box.append(row)
        if bats:
            h = Gtk.Label(label="Batteri i trådløse enheter", xalign=0)
            h.add_css_class("caption-heading")
            self.ctrl_box.append(h)
            for model, lvl in bats:
                self.ctrl_box.append(Gtk.Label(label=f"🔋 {model}: {lvl}", xalign=0))
        return True
