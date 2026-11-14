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


def running_game():
    """(appid, navn) for Steam-spillet som kjører, eller None."""
    if __import__("sys").platform == "win32":                   # Steam skriver RunningAppID i registeret
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
                aid = str(winreg.QueryValueEx(k, "RunningAppID")[0])
            return (aid, _name(aid)) if aid not in IGNORE else None
        except OSError:
            return None
    for p in glob.glob("/proc/[0-9]*/cmdline"):
        try:
            with open(p, "rb") as f:
                cmd = f.read().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            continue
        if "SteamLaunch" not in cmd:
            continue
        m = re.search(r"AppId=(\d+)", cmd)
        if m and m.group(1) not in IGNORE:
            return m.group(1), _name(m.group(1))
    return None


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
             "kr": round(power.cost(avg_w, dur / 3600), 2) if avg_w else None}
        _save_session(s)
        _prune_logs()
        return s


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
        bg = getattr(win, "bg", None)
        if bg:
            bg.game_name = g[1]
        win.set_badge("spill", "▶")
        enabled, p = profile_for(g[0])
        if enabled:
            if auto.night_snap is not None:                       # natt settes på pause
                A.restore(win, auto.night_snap, False)
            auto.game_snap = A.snapshot(win)
            A.apply(win, p["power"], p["fans"], p["rgb"], p.get("color"))
            auto.game_snap["rgb"] = p["rgb"] not in ("keep", None)
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
        if auto.night_snap is not None:                           # tilbake til natt om det fortsatt er natt
            auto.night_snap = None
            auto._last_night_check = 0
        if auto.session:
            s = auto.session.finish()
            auto.session = None
            if s["minutes"] >= 1:
                auto.notify("session", f"Spilløkt: {name}", summary(s))
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
