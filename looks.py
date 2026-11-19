"""Temaer som lever: tid på døgnet (med myk overgang), tema per spill (+ RGB i samme farge), eget tema hentet
fra skrivebordsbakgrunnen, og en levende bakgrunn som pulserer med CPU-belastningen.

Innstillingene ligger i utseende.json (samme fil som temaet):
  "auto": "off" | "time"
  "times": {"day": ["07:00", "arktis"], "evening": ["18:00", "solnedgang"], "night": ["22:30", "nordlys"]}
  "games": {"Counter-Strike 2": "lava", ...}, "game_rgb": true
  "live": true
"""
import os
import sys
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

import theme  # noqa: E402

FADE_MIN = 20                     # overgangen mellom to temaer tar 20 minutter
DEFAULT_TIMES = {"day": ["07:00", "arktis"], "evening": ["18:00", "solnedgang"], "night": ["22:30", "nordlys"]}
_STATE = {"game": None, "win": None, "live": None, "phase": 0.0, "last": None}


def _mins(hhmm):
    try:
        h, m = (int(x) for x in hhmm.split(":"))
        return h * 60 + m
    except (ValueError, AttributeError):
        return 0


def time_theme(now=None):
    """(tema eller blanding) for akkurat nå etter tidsplanen."""
    lk = theme.look()
    times = lk.get("times") or DEFAULT_TIMES
    pts = sorted(((_mins(v[0]), v[1]) for v in times.values() if v and v[1] in theme.THEMES), key=lambda x: x[0])
    if not pts:
        return None
    lt = time.localtime(now)
    cur = lt.tm_hour * 60 + lt.tm_min + lt.tm_sec / 60
    # hvilket tema gjelder nå, og hvilket kommer neste?
    idx = max((i for i, (m, _t) in enumerate(pts) if m <= cur), default=len(pts) - 1)
    this, nxt = pts[idx], pts[(idx + 1) % len(pts)]
    until = (nxt[0] - cur) % (24 * 60)
    if until < FADE_MIN and nxt[1] != this[1]:
        return theme.blend(this[1], nxt[1], 1 - until / FADE_MIN)
    return this[1]


def wanted():
    """Temaet som skal vises nå: spillets tema > tid på døgnet > valgt tema."""
    lk = theme.look()
    g = _STATE["game"]
    if g and (lk.get("games") or {}).get(g) in theme.THEMES:
        return lk["games"][g]
    if lk.get("auto") == "time":
        t = time_theme()
        if t:
            return t
    if lk.get("auto") == "daily":
        return theme.daily_theme()
    return theme.current_theme()


def refresh(force=False):
    t = wanted()
    key = t if isinstance(t, str) else tuple(sorted(t.items()))
    if force or key != _STATE["last"]:
        _STATE["last"] = key
        theme.show(t)
    return True


def on_game(name):
    """Kalles når et spill starter (navn) eller slutter (None)."""
    _STATE["game"] = name
    lk = theme.look()
    th = (lk.get("games") or {}).get(name) if name else None
    if lk.get("game_rgb", True):
        try:
            import automation
            if th in theme.THEMES:
                automation.rgb_set(automation.hex_rgb(theme.THEMES[th]["a"]))
            elif name is None and _STATE.get("rgb_set"):
                automation.rgb_restore()
            _STATE["rgb_set"] = th in theme.THEMES
        except Exception:  # noqa: BLE001
            pass
    try:                                                      # Hue-lysene følger spillet
        import smartauto
        col = theme.THEMES[th]["a"] if th in theme.THEMES else theme._t(theme.current_theme()).get("a", "#8a5cff")
        smartauto.on_game(name, col if name else None)
    except Exception:  # noqa: BLE001
        pass
    GLib.idle_add(lambda: refresh() and False)


# --------------------------------------------------------------------------
# Levende bakgrunn: gløden puster sakte og blir sterkere når PC-en jobber
# --------------------------------------------------------------------------
_LIVE = [None]


def _live_tick():
    try:
        import perf
        if perf.light():
            return
    except Exception:  # noqa: BLE001
        pass
    lk = theme.look()
    disp = Gdk.Display.get_default()
    if not lk.get("live"):
        if _LIVE[0] is not None:
            Gtk.StyleContext.remove_provider_for_display(disp, _LIVE[0])
            _LIVE[0] = None
        return True
    win = _STATE["win"]
    load = getattr(win, "_cpu_load", 0) or 0
    _STATE["phase"] = (_STATE["phase"] + 0.05 + load / 900) % 1.0
    import math
    ph = _STATE["phase"] * 2 * math.pi
    t = theme._t(_STATE["last"] if isinstance(_STATE["last"], str) else theme.current_theme())
    if _STATE["last"] and not isinstance(_STATE["last"], str):
        t = dict(_STATE["last"])
    a, b, c = t.get("a", "#5b8cff"), t.get("b", "#8a5cff"), t.get("c", "#00c8b4")
    k = 0.16 + 0.22 * min(1, load / 80)                     # sterkere glød når CPU-en jobber
    x1, y1 = 10 + 18 * math.sin(ph), 0 + 8 * math.cos(ph)
    x2, y2 = 92 + 8 * math.cos(ph * 0.7), 8 + 10 * math.sin(ph * 0.7)
    x3 = 50 + 30 * math.sin(ph * 0.5)
    css = f""".ks-content, window.ks-glass .ks-content {{ background-image:
      radial-gradient(ellipse 60% 45% at {x1:.1f}% {y1:.1f}%, alpha({a}, {k:.3f}), transparent),
      radial-gradient(ellipse 50% 42% at {x2:.1f}% {y2:.1f}%, alpha({b}, {k * 0.9:.3f}), transparent),
      radial-gradient(ellipse 70% 40% at {x3:.1f}% 100%, alpha({c}, {k * 0.55:.3f}), transparent); }}"""
    p = theme._provider(css)
    Gtk.StyleContext.add_provider_for_display(disp, p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 6)
    if _LIVE[0] is not None:
        Gtk.StyleContext.remove_provider_for_display(disp, _LIVE[0])
    _LIVE[0] = p
    return True


def start(win):
    _STATE["win"] = win
    refresh(force=True)
    GLib.timeout_add_seconds(30, refresh)                    # tid på døgnet / overganger
    GLib.timeout_add(2000, lambda: (win.get_mapped() and _live_tick(), True)[1])


# --------------------------------------------------------------------------
# Eget tema: farger hentet fra skrivebordsbakgrunnen
# --------------------------------------------------------------------------
def wallpaper_path():
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop") as k:
                return winreg.QueryValueEx(k, "WallPaper")[0] or None
        except OSError:
            return None
    # KDE Plasma
    p = os.path.expanduser("~/.config/plasma-org.kde.plasma.desktop-appletsrc")
    try:
        img = None
        for line in open(p, encoding="utf-8", errors="ignore"):
            if line.startswith("Image="):
                img = line.split("=", 1)[1].strip()
        if img:
            img = img.replace("file://", "")
            if os.path.isdir(img):                         # bakgrunnspakke: ta største bilde
                files = []
                for root, _d, fs in os.walk(img):
                    files += [os.path.join(root, f) for f in fs if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
                img = max(files, key=os.path.getsize) if files else None
            if img and os.path.isfile(img):
                return img
    except OSError:
        pass
    # GNOME
    try:
        import subprocess
        out = subprocess.run(["gsettings", "get", "org.gnome.desktop.background", "picture-uri-dark"],
                             capture_output=True, text=True, timeout=3).stdout.strip().strip("'")
        out = out.replace("file://", "")
        if out and os.path.isfile(out):
            return out
    except (OSError, Exception):  # noqa: BLE001
        pass
    return None


def colors_from_image(path):
    """To klare, ulike farger fra bildet (de mest fargerike i hver sin fargetone)."""
    import colorsys
    from gi.repository import GdkPixbuf
    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 64, 64, True)
    px, n, rs = pb.get_pixels(), pb.get_n_channels(), pb.get_rowstride()
    buckets = {}
    for y in range(pb.get_height()):
        for x in range(pb.get_width()):
            i = y * rs + x * n
            r, g, b = px[i] / 255, px[i + 1] / 255, px[i + 2] / 255
            h, s, v = colorsys.rgb_to_hsv(r, g, b)
            if v < 0.25 or s < 0.25:
                continue
            k = int(h * 12)
            w = s * v
            acc = buckets.setdefault(k, [0, 0, 0, 0])
            acc[0] += w
            acc[1] += r * w
            acc[2] += g * w
            acc[3] += b * w
    if not buckets:
        return "#5b8cff", "#8a5cff"
    top = sorted(buckets.items(), key=lambda kv: -kv[1][0])

    def col(acc):
        w = acc[0] or 1
        r, g, b = acc[1] / w, acc[2] / w, acc[3] / w
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        r, g, b = colorsys.hsv_to_rgb(h, max(s, 0.6), max(v, 0.85))     # klare, lysende farger
        return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))
    first = top[0]
    second = next((kv for kv in top[1:] if min(abs(kv[0] - first[0]), 12 - abs(kv[0] - first[0])) >= 2), None)
    a = col(first[1])
    b = col(second[1]) if second else theme._shade(a, 0.35)
    return a, b


def set_custom(a, b, dark=True, use=True):
    theme._save_look(custom={"a": a, "b": b, "dark": bool(dark)})
    theme.THEMES["eget"] = theme.make_custom(a, b, dark)
    if use:
        theme.set_theme("eget")
    refresh(force=True)
