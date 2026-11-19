"""Stue-modus: fullskjerm for TV-en eller andreskjermen – stor klokke, vær, hvem som spiller og temperaturer.

Åpnes fra menyen, Ctrl+K («stue») eller F11. Esc, klikk eller F11 lukker. Bakgrunnen driver i temaets farger.
"""
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

import i18n  # noqa: E402

DAYS = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"]
MONTHS = ["januar", "februar", "mars", "april", "mai", "juni", "juli", "august", "september", "oktober",
          "november", "desember"]
CSS = """
window.ks-ambient { background-color: #05060a; }
.ks-amb { background-image: radial-gradient(ellipse 60% 50% at 15% 10%, alpha(@accent_bg_color, .38), transparent),
                            radial-gradient(ellipse 55% 45% at 90% 20%, alpha(@accent_color, .25), transparent),
                            radial-gradient(ellipse 70% 50% at 50% 110%, alpha(@accent_bg_color, .22), transparent);
  background-size: 180% 180%, 180% 180%, 180% 180%; animation: ks-amb-drift 40s steps(60) infinite alternate; }
@keyframes ks-amb-drift { 0% { background-position: 0% 0%, 100% 0%, 50% 100%; }
  100% { background-position: 30% 40%, 70% 30%, 60% 70%; } }
.ks-amb-clock { font-size: 150px; font-weight: 200; letter-spacing: -4px; color: white; }
.ks-amb-date { font-size: 30px; font-weight: 500; color: alpha(white, .75); }
.ks-amb-card { border-radius: 26px; padding: 22px 26px; background: alpha(white, .07);
  border: 1px solid alpha(white, .10); }
.ks-amb-k { font-size: 15px; font-weight: 800; letter-spacing: .12em; color: alpha(white, .55); }
.ks-amb-v { font-size: 44px; font-weight: 700; color: white; }
.ks-amb-s { font-size: 18px; color: alpha(white, .75); }
.ks-amb-row { font-size: 22px; color: white; }
"""


class Ambient(Gtk.Window):
    def __init__(self, win):
        super().__init__(title="Kontrollsenter – stue", decorated=False)
        self.win = win
        self.add_css_class("ks-ambient")
        import theme
        if not getattr(Ambient, "_css", False):
            Ambient._css = True
            theme.add_css(CSS, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 6)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=26)
        root.add_css_class("ks-amb")
        for side in ("top", "bottom", "start", "end"):
            getattr(root, f"set_margin_{side}")(0)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=26, valign=Gtk.Align.CENTER, vexpand=True,
                        margin_start=70, margin_end=70, margin_top=40, margin_bottom=40)
        root.append(inner)
        self.clock = Gtk.Label(xalign=0)
        self.clock.add_css_class("ks-amb-clock")
        inner.append(self.clock)
        self.date = Gtk.Label(xalign=0)
        self.date.add_css_class("ks-amb-date")
        inner.append(self.date)
        grid = Gtk.Box(spacing=22, homogeneous=True, margin_top=20)
        self.c_weather = self._card(grid, "VÆRET")
        self.c_temp = self._card(grid, "PC-EN")
        self.c_today = self._card(grid, "I DAG")
        inner.append(grid)
        fam = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        fam.add_css_class("ks-amb-card")
        k = Gtk.Label(label=i18n.tr("HJEMME"), xalign=0)
        k.add_css_class("ks-amb-k")
        fam.append(k)
        self.fam = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        fam.append(self.fam)
        inner.append(fam)
        self.set_child(root)
        key = Gtk.EventControllerKey()
        key.connect("key-pressed", lambda _c, kv, _k, _s: (self.close(), True)[1] if kv in (0xff1b, 0xffc8) else False)
        self.add_controller(key)
        click = Gtk.GestureClick()
        click.connect("released", lambda *_: self.close())
        self.add_controller(click)
        self._tick()
        self._data()
        self._t1 = GLib.timeout_add_seconds(1, self._tick)
        self._t2 = GLib.timeout_add_seconds(15, self._data)
        self.connect("close-request", self._closed)
        self.fullscreen()

    def _card(self, parent, title):
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        b.add_css_class("ks-amb-card")
        k = Gtk.Label(label=i18n.tr(title), xalign=0)
        k.add_css_class("ks-amb-k")
        b.append(k)
        v = Gtk.Label(xalign=0, ellipsize=3)
        v.add_css_class("ks-amb-v")
        b.append(v)
        s = Gtk.Label(xalign=0, wrap=True)
        s.add_css_class("ks-amb-s")
        b.append(s)
        parent.append(b)
        return v, s

    def _closed(self, *_):
        for t in (self._t1, self._t2):
            GLib.source_remove(t)
        return False

    def _tick(self):
        lt = time.localtime()
        self.clock.set_label(time.strftime("%H:%M", lt))
        self.date.set_label(f"{DAYS[lt.tm_wday].capitalize()} {lt.tm_mday}. {MONTHS[lt.tm_mon - 1]}")
        ct = getattr(self.win, "_cpu_t", None)
        gt = self.win.gpu_temp_now() if hasattr(self.win, "gpu_temp_now") else None
        v, s = self.c_temp
        v.set_label(f"{round(ct) if ct else '–'}° / {round(gt) if gt else '–'}°")
        game = getattr(getattr(self.win, "bg", None), "game_name", None)
        s.set_label((i18n.tr("CPU / GPU · spiller ") + game) if game else i18n.tr("CPU / GPU"))
        return True

    def _data(self):
        def work():
            out = {}
            try:
                import infotiles
                out["w"] = infotiles.weather()
            except Exception:  # noqa: BLE001
                pass
            try:
                import today
                out["t"] = today.summary()
            except Exception:  # noqa: BLE001
                pass
            try:
                import features
                out["f"] = features.family().get("pcs", [])
            except Exception:  # noqa: BLE001
                out["f"] = []
            GLib.idle_add(self._show, out)
        threading.Thread(target=work, daemon=True).start()
        return True

    def _show(self, d):
        w = d.get("w") or {}
        v, s = self.c_weather
        if w.get("temp") is not None:
            v.set_label(f"{w.get('icon', '')} {w['temp']}°")
            s.set_label(w.get("text") or w.get("place") or "")
        else:
            v.set_label("–")
            s.set_label(i18n.tr("Velg sted under Innstillinger"))
        t = d.get("t")
        v, s = self.c_today
        if t:
            v.set_label(f"{t['play_s'] // 3600} t {t['play_s'] % 3600 // 60} min")
            s.set_label(" · ".join(x for x in ((t["top"] or ""), f"{t['kr']:.2f} kr strøm" if t.get("kr") else "") if x))
        while (ch := self.fam.get_first_child()) is not None:
            self.fam.remove(ch)
        now = time.time()
        for p in d.get("f") or []:
            on = not p.get("off") and now - (p.get("time") or 0) < 900
            g = p.get("game")
            lab = Gtk.Label(xalign=0, label=("🟢  " if on else "⚫  ") + str(p.get("name")) +
                            (f"   🎮 {g}" if on and g else ("" if on else "   " + i18n.tr("av"))))
            lab.add_css_class("ks-amb-row")
            self.fam.append(lab)
        return False


def open_ambient(win):
    a = Ambient(win)
    a.set_transient_for(None)
    a.present()
    return a
