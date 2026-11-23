"""Spill: automatiske spillprofiler og rapport etter hver spilløkt.

- Kjenner igjen Steam-spill som kjører (prosessen «reaper SteamLaunch AppId=…»).
- Spillprofil: strømmodus, vifter og RGB byttes når spillet starter, og settes tilbake etterpå.
- Øktrapport: spilletid, snitt-FPS og «1 % low» (fra MangoHud-loggen), høyeste temperaturer og strøm.
"""
import csv
import glob
import json
import os
import re
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

import automation as A  # noqa: E402
import i18n  # noqa: E402

LOG_DIR = os.path.expanduser("~/.local/share/systemmonitor/spilllogger")
SESSIONS = os.path.expanduser("~/.config/systemmonitor/spilloekter.json")
IGNORE = {"0", "228980", "1070560", "1391110", "1628350", "1493710", "2180100", "2348590"}   # runtime/verktøy


def mangohud_log_lines():
    """Linjer som legges i MangoHud.conf så FPS logges for øktrapporten."""
    if not A.load_games().get("report", True):
        return ""
    os.makedirs(LOG_DIR, exist_ok=True)
    return f"output_folder={LOG_DIR}\nautostart_log=5\nlog_interval=500\n"


# Spill utenfor Steam (Battle.net m.fl., også under Wine/Proton på Linux): programfil → navn
OTHER_GAMES = {"wow.exe": "World of Warcraft", "wowclassic.exe": "World of Warcraft Classic",
               "wow-64.exe": "World of Warcraft", "diablo iv.exe": "Diablo IV", "d2r.exe": "Diablo II: Resurrected",
               "warcraft iii.exe": "Warcraft III", "overwatch.exe": "Overwatch 2", "hearthstone.exe": "Hearthstone",
               "league of legends.exe": "League of Legends", "valorant-win64-shipping.exe": "VALORANT",
               "fortniteclient-win64-shipping.exe": "Fortnite", "minecraft.exe": "Minecraft",
               "javaw.exe": None}


def _other_game():
    if __import__("sys").platform != "win32":
        import procs
        short = {exe[:15]: (exe, nice) for exe, nice in OTHER_GAMES.items() if nice}
        for pid, comm in procs.comm_map().items():
            hit = short.get(comm.lower())
            if hit:
                return "ext:" + hit[0], hit[1]
            if comm.lower().endswith(".exe") or comm in ("wine64-preload", "wine-preloader", "wineserver"):
                cmd = procs.cmdline(pid).replace(b"\0", b" ").decode(errors="replace").lower()
                for exe, nice in OTHER_GAMES.items():
                    if nice and (cmd.endswith("\\" + exe) or f"\\{exe} " in cmd + " " or cmd.endswith("/" + exe)):
                        return "ext:" + exe, nice
        return None
    try:
        import psutil
        for p in psutil.process_iter(["name", "cmdline"]):
            name = (p.info.get("name") or "").lower()
            cmd = " ".join(p.info.get("cmdline") or []).lower()
            for exe, nice in OTHER_GAMES.items():
                if nice and (name == exe or name == exe[:15] or cmd.endswith("\\" + exe) or f"\\{exe} " in cmd + " "
                             or cmd.endswith("/" + exe)):
                    return "ext:" + exe, nice
    except Exception:  # noqa: BLE001
        pass
    return None


def running_game():
    """(appid, navn) for spillet som kjører (Steam, Battle.net m.fl.), eller None."""
    if __import__("sys").platform == "win32":                   # Steam skriver RunningAppID i registeret
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
                aid = str(winreg.QueryValueEx(k, "RunningAppID")[0])
            if aid not in IGNORE and aid != "0":
                return aid, _name(aid)
        except OSError:
            pass
        return _other_game()
    import procs
    for pid, comm in procs.comm_map().items():
        if comm not in ("reaper", "steam-launch-wr", "SteamLaunch", "pressure-vessel", "steam-runtime-l"):
            continue
        cmd = procs.cmdline(pid).replace(b"\0", b" ").decode(errors="replace")
        if "SteamLaunch" not in cmd:
            continue
        m = re.search(r"AppId=(\d+)", cmd)
        if m and m.group(1) not in IGNORE:
            return m.group(1), _name(m.group(1))
    return _other_game()


_NAMES = {}


def _name(appid):
    if appid not in _NAMES:
        try:
            import games
            _NAMES.update({g["appid"]: g["name"] for g in games.installed_games()})
        except Exception:  # noqa: BLE001
            pass
    return _NAMES.get(appid, f"Spill {appid}")


def profile_for(appid):
    cfg = A.load_games()
    p = {k: cfg[k] for k in ("power", "fans", "rgb", "color")}
    p.update(cfg.get("games", {}).get(appid, {}))
    return cfg["enabled"], p


# --------------------------------------------------------------------------
# Øktrapport
# --------------------------------------------------------------------------
def _fps_stats(since):
    """Snitt-FPS og 1 % low fra nyeste MangoHud-logg skrevet etter «since»."""
    files = [f for f in glob.glob(os.path.join(LOG_DIR, "*.csv"))
             if os.path.getmtime(f) >= since - 5 and not f.endswith("_summary.csv")]
    if not files:
        return None, None
    f = max(files, key=os.path.getmtime)
    fps = []
    try:
        with open(f, newline="", errors="replace") as fh:
            rows = list(csv.reader(fh))
        start = next(i for i, r in enumerate(rows) if r and r[0].strip().lower() == "fps")
        for r in rows[start + 1:]:
            try:
                v = float(r[0])
                if v > 0:
                    fps.append(v)
            except (ValueError, IndexError):
                continue
    except (OSError, StopIteration):
        return None, None
    if len(fps) < 10:
        return None, None
    fps_sorted = sorted(fps)
    n = max(1, len(fps) // 100)
    return sum(fps) / len(fps), sum(fps_sorted[:n]) / n


def _prune_logs(keep=30):
    files = sorted(glob.glob(os.path.join(LOG_DIR, "*.csv")), key=os.path.getmtime)
    for f in files[:-keep]:
        try:
            os.remove(f)
        except OSError:
            pass


def load_sessions():
    try:
        with open(SESSIONS) as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def _save_session(s):
    ss = load_sessions()
    ss.append(s)
    os.makedirs(os.path.dirname(SESSIONS), exist_ok=True)
    with open(SESSIONS, "w") as f:
        json.dump(ss[-50:], f, indent=1)


class Session:
    def __init__(self, appid, name):
        self.appid, self.name = appid, name
        self.start = time.time()
        self.max_cpu = self.max_gpu = None
        self.watts = []
        self.fps_hist = []                         # FPS de siste minuttene (til å oppdage dropp)
        self.drops = []

    def _live_fps(self):
        """Siste FPS-verdier fra MangoHud-loggen som skrives nå (leser bare slutten av fila)."""
        files = [f for f in glob.glob(os.path.join(LOG_DIR, "*.csv"))
                 if os.path.getmtime(f) >= self.start - 5 and not f.endswith("_summary.csv")]
        if not files:
            return []
        f = max(files, key=os.path.getmtime)
        try:
            with open(f, "rb") as fh:
                fh.seek(0, 2)
                fh.seek(max(0, fh.tell() - 4096))
                lines = fh.read().decode("utf-8", "replace").splitlines()[1:]
        except OSError:
            return []
        out = []
        for ln in lines[-10:]:
            try:
                v = float(ln.split(",")[0])
                if v > 0:
                    out.append(v)
            except (ValueError, IndexError):
                continue
        return out

    def _check_drop(self, win, ct, gt):
        cur = self._live_fps()
        if not cur:
            return
        now = sum(cur[-3:]) / len(cur[-3:])
        self.fps_hist = (self.fps_hist + [now])[-60:]
        if len(self.fps_hist) < 8:
            return
        normal = sorted(self.fps_hist)[len(self.fps_hist) // 2]
        if normal < 30 or now >= normal * 0.6:
            return
        if self.drops and time.time() - self.drops[-1]["t"] < 30:      # samme dropp
            return
        nv = win.nvidia.data if getattr(win, "nvidia", None) and win.nvidia.available else None
        top = []
        try:
            import details                          # prosesslisten som oppdateres i bakgrunnen (blokkerer aldri)
            top = [n for n, _t in details._top("cpu", 5) if self.name.lower()[:5] not in n.lower()][:3]
        except Exception:  # noqa: BLE001
            pass
        cpu_l = getattr(win, "_cpu_load", 0) or 0
        gpu_l = (nv or {}).get("util") or 0
        why = ("CPU-en var varm" if (ct or 0) >= 90 else "skjermkortet var varmt" if (gt or 0) >= 85 else
               "skjermkortet jobbet for fullt" if gpu_l >= 97 else "CPU-en jobbet hardt" if cpu_l >= 85 else
               ("noe i bakgrunnen: " + ", ".join(top[:2])) if top else "ukjent – kanskje lasting eller nettet")
        self.drops.append({"t": time.time(), "fps": round(now), "normal": round(normal), "cpu_t": ct, "gpu_t": gt,
                           "cpu_l": round(cpu_l), "gpu_l": round(gpu_l), "top": top, "why": why})

    def sample(self, win):
        ct = getattr(win, "_cpu_t", None)
        nv = win.nvidia.data if getattr(win, "nvidia", None) and win.nvidia.available else None
        gt = nv.get("temp") if nv else None
        if ct is not None:
            self.max_cpu = max(self.max_cpu or 0, ct)
        if gt is not None:
            self.max_gpu = max(self.max_gpu or 0, gt)
        pw = (getattr(win, "_power", None) or {}).get("total")
        if pw:
            self.watts.append(pw)
        try:
            self._check_drop(win, ct, gt)
        except Exception:  # noqa: BLE001
            pass

    def finish(self):
        dur = time.time() - self.start
        avg, low = _fps_stats(self.start)
        avg_w = sum(self.watts) / len(self.watts) if self.watts else None
        import power
        s = {"appid": self.appid, "name": self.name, "start": self.start, "minutes": round(dur / 60),
             "fps": round(avg) if avg else None, "low": round(low) if low else None,
             "max_cpu": round(self.max_cpu) if self.max_cpu else None,
             "max_gpu": round(self.max_gpu) if self.max_gpu else None,
             "watts": round(avg_w) if avg_w else None,
             "kr": round(power.cost(avg_w, dur / 3600), 2) if avg_w else None,
             "drops": self.drops[-10:]}
        try:                                               # skjermkortdriver (FPS-sammenligning ved ny driver)
            import features
            s["driver"] = features.driver_info()
        except Exception:  # noqa: BLE001
            pass
        _save_session(s)
        _prune_logs()
        return s


def best_of_week(s):
    """«🏆 Lengste økt denne uka» / «🏆 Beste FPS denne uka» – sammenlignet med de siste 7 dagene i samme spill."""
    import time as _t
    week = [x for x in load_sessions() if x.get("name") == s.get("name") and x.get("start") != s.get("start")
            and _t.time() - (x.get("start") or 0) < 7 * 86400]
    if not week:
        return ""
    out = []
    if s.get("minutes", 0) > max(x.get("minutes", 0) for x in week):
        out.append("🏆 lengste økt denne uka")
    fps = [x.get("fps") for x in week if x.get("fps")]
    if s.get("fps") and fps and s["fps"] > max(fps):
        out.append("🏆 beste FPS denne uka")
    if not out:
        best = max(week, key=lambda x: x.get("minutes", 0))
        out.append(f"beste denne uka: {best.get('minutes', 0)} min")
    return " · " + " · ".join(out)


def summary(s):
    parts = [f"{s['minutes']} min"]
    if s.get("fps"):
        parts.append(f"{s['fps']} FPS (1 % low {s['low']})")
    if s.get("max_cpu") is not None:
        parts.append(f"CPU maks {s['max_cpu']} °C")
    if s.get("max_gpu") is not None:
        parts.append(f"GPU maks {s['max_gpu']} °C")
    if s.get("watts"):
        parts.append(f"{s['watts']} W snitt ≈ {s['kr']:.2f} kr")
    if s.get("drops"):
        d = s["drops"]
        from collections import Counter
        why = Counter(x["why"] for x in d).most_common(1)[0][0]
        parts.append(f"{len(d)} FPS-dropp – oftest: {why}")
    return " · ".join(i18n.tr(p) for p in parts)


# --------------------------------------------------------------------------
# Kalles fra automatikken hvert 5. sekund
# --------------------------------------------------------------------------
def tick(auto):
    g = running_game()
    win = auto.win
    if g and auto.game is None:                                    # spill startet
        auto.game = g
        auto.session = Session(*g)
        try:
            import remote_extra
            remote_extra.event("session", f"Spiller {g[1]}", "", "game")
        except Exception:  # noqa: BLE001
            pass
        bg = getattr(win, "bg", None)
        if bg:
            bg.game_name = g[1]
        win.set_badge("spill", "▶")
        try:
            import scenes
            scenes.on_event(win, "game_start", g[1])
            import assistant
            assistant.on_game_start(win, g[1])
            import gamesplus
            gamesplus.on_game_start(win, g[1])
            import looks
            looks.on_game(g[1])
            win.layout_for_game(True)
        except Exception:  # noqa: BLE001
            pass
        enabled, p = profile_for(g[0])
        if enabled:
            if auto.night_snap is not None:                       # natt settes på pause
                A.restore(win, auto.night_snap, False)
            auto.game_snap = A.snapshot(win)
            A.apply(win, p["power"], p["fans"], p["rgb"], p.get("color"))
            auto.game_snap["rgb"] = p["rgb"] not in ("keep", None)
            if p.get("gpu_pl"):                                    # strømgrense på skjermkortet for spillet
                import threading

                def pl(pct=p["gpu_pl"]):
                    try:
                        import gamegpu
                        auto.gpu_pl_back = gamegpu.pl_apply(pct)
                    except Exception as e:  # noqa: BLE001
                        import applog
                        applog.log.warning("GPU-strøm for spill: %s", e)
                threading.Thread(target=pl, daemon=True).start()
            auto.notify("game", f"Spillprofil: {g[1]}", "Strømmodus, vifter og RGB er satt for spill.")
    elif g and auto.session:
        auto.session.sample(win)
    elif not g and auto.game is not None:                           # spill avsluttet
        name = auto.game[1]
        auto.game = None
        bg = getattr(win, "bg", None)
        if bg:
            bg.game_name = None
        win.set_badge("spill", "")
        if auto.game_snap is not None:
            A.restore(win, auto.game_snap, auto.game_snap.get("rgb"))
            auto.game_snap = None
        back = getattr(auto, "gpu_pl_back", None)
        if back:
            auto.gpu_pl_back = None
            import threading

            def pl_back(b=back):
                try:
                    import gamegpu
                    gamegpu.pl_restore(b)
                except Exception:  # noqa: BLE001
                    pass
            threading.Thread(target=pl_back, daemon=True).start()
        if auto.night_snap is not None:                           # tilbake til natt om det fortsatt er natt
            auto.night_snap = None
            auto._last_night_check = 0
        try:
            import scenes
            scenes.on_event(win, "game_end", name)
            import gamesplus
            gamesplus.on_game_end(win, name)
            import looks
            looks.on_game(None)
            win.layout_for_game(False)
        except Exception:  # noqa: BLE001
            pass
        if auto.session:
            s = auto.session.finish()
            auto.session = None
            if s["minutes"] >= 1:
                try:
                    import gamesplus
                    cmp_ = gamesplus.fps_compare(s)
                except Exception:  # noqa: BLE001
                    cmp_ = ""
                auto.notify("session", f"Spilløkt: {name}", summary(s) + best_of_week(s) + cmp_)
            try:
                if bg:
                    bg.flush_held()                       # varslene som ble holdt tilbake mens du spilte
            except Exception:  # noqa: BLE001
                pass
            try:
                import savegames
                if savegames.load_cfg().get("auto") and __import__("sys").platform != "win32":
                    savegames.backup_async([s["appid"]])
            except Exception:  # noqa: BLE001
                pass


# --------------------------------------------------------------------------
# Kort på Automatikk-siden
# --------------------------------------------------------------------------
def build_cards(page):
    cfg = A.load_games()
    c, i, head = A.card("Spillprofiler",
                        "Når et Steam-spill starter, bytter Kontrollsenter til innstillingene under – og tilbake når "
                        "spillet avsluttes. Velg egne innstillinger for enkeltspill nederst.", "ks-games-symbolic")
    sw = Gtk.Switch(active=cfg["enabled"], valign=Gtk.Align.CENTER)
    head.append(sw)

    def set_(k, v):
        c2 = A.load_games()
        c2[k] = v
        A.save_games(c2)
    sw.connect("notify::active", lambda w, _p: set_("enabled", w.get_active()))
    i.append(A.row("Strømmodus", A.dropdown(A.POWER_CHOICES, cfg["power"], lambda v: set_("power", v))))
    i.append(A.row("Vifter", A.dropdown(A.FAN_CHOICES, cfg["fans"], lambda v: set_("fans", v))))
    rgbrow = Gtk.Box(spacing=8)
    col = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False))
    rgba = Gdk.RGBA()
    rgba.parse(cfg.get("color", "#ff0000"))
    col.set_rgba(rgba)

    def col_changed(b, _p):
        c_ = b.get_rgba()
        set_("color", "#%02x%02x%02x" % (int(c_.red * 255), int(c_.green * 255), int(c_.blue * 255)))
    col.connect("notify::rgba", col_changed)
    col.set_visible(cfg["rgb"] == "color")
    rgbrow.append(col)
    rgbrow.append(A.dropdown(A.RGB_CHOICES_GAME, cfg["rgb"], lambda v: (set_("rgb", v), col.set_visible(v == "color"))))
    i.append(A.row("RGB-lys", rgbrow))

    # Egne innstillinger per spill
    sep = Gtk.Label(label=i18n.tr("Egne innstillinger for enkeltspill"), xalign=0)
    sep.add_css_class("heading")
    sep.set_margin_top(8)
    i.append(sep)
    per = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    i.append(per)
    try:
        import games
        installed = games.installed_games()
    except Exception:  # noqa: BLE001
        installed = []
    names = {g["appid"]: g["name"] for g in installed}

    def rebuild():
        while (ch := per.get_first_child()):
            per.remove(ch)
        c2 = A.load_games()
        for aid, p in sorted(c2.get("games", {}).items(), key=lambda kv: names.get(kv[0], kv[0]).lower()):
            r = Gtk.Box(spacing=8)
            lab = Gtk.Label(label=names.get(aid, aid), xalign=0, hexpand=True, ellipsize=3)
            r.append(lab)

            def set_g(k, v, a=aid):
                c3 = A.load_games()
                c3.setdefault("games", {}).setdefault(a, {})[k] = v
                A.save_games(c3)
            r.append(A.dropdown(A.POWER_CHOICES, p.get("power", c2["power"]), lambda v, s=set_g: s("power", v)))
            r.append(A.dropdown(A.FAN_CHOICES, p.get("fans", c2["fans"]), lambda v, s=set_g: s("fans", v)))
            r.append(A.dropdown(A.RGB_CHOICES_GAME[:2], p.get("rgb", "keep") if p.get("rgb") != "color" else "keep",
                                lambda v, s=set_g: s("rgb", v)))
            import gamegpu
            plc = [(v, i18n.tr("GPU-strøm: standard") if not v else f"GPU-strøm {v} %") for v in gamegpu.PL_CHOICES]
            r.append(A.dropdown(plc, p.get("gpu_pl", 0), lambda v, s=set_g: s("gpu_pl", v)))
            rm = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text=i18n.tr("Fjern"))
            rm.add_css_class("flat")

            def remove(_b, a=aid):
                c3 = A.load_games()
                c3.get("games", {}).pop(a, None)
                A.save_games(c3)
                rebuild()
            rm.connect("clicked", remove)
            r.append(rm)
            per.append(r)
    rebuild()
    add = Gtk.Box(spacing=8)
    choices = [g for g in installed]
    dd = Gtk.DropDown.new_from_strings([g["name"] for g in choices] or [i18n.tr("Ingen spill funnet")])
    dd.set_hexpand(True)
    add.append(dd)
    b = Gtk.Button(label=i18n.tr("Legg til spill"))

    def do_add(*_):
        if not choices:
            return
        g = choices[dd.get_selected()]
        c3 = A.load_games()
        c3.setdefault("games", {}).setdefault(g["appid"], {"power": c3["power"], "fans": c3["fans"], "rgb": "keep"})
        A.save_games(c3)
        rebuild()
    b.connect("clicked", do_add)
    add.append(b)
    i.append(add)

    # Øktrapport
    rep = Gtk.Switch(active=cfg.get("report", True), valign=Gtk.Align.CENTER)

    def set_report(w, _p):
        set_("report", w.get_active())
        try:
            import sys
            sm = sys.modules.get("__main__")
            if sm and hasattr(sm, "set_overlay"):
                root = page.get_root()
                sm.set_overlay(root.ov_button.get_active() if root else True)
        except Exception:  # noqa: BLE001
            pass
    rep.connect("notify::active", set_report)
    i.append(A.row("Rapport etter hver spilløkt (FPS, temperaturer, strøm)", rep))
    page.box.append(c)
