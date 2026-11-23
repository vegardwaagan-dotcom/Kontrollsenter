"""Skrivebordswidgets i Kontrollsenter (Windows, og Linux uten KDE): små glassvinduer uten ramme.

Dra dem dit du vil ha dem (Windows husker plasseringen), og lukk med ✕ som kommer fram når musa er over.
"""
import sys

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

import i18n  # noqa: E402
import widgets as W  # noqa: E402

IS_WIN = sys.platform == "win32"
OPEN = {}


def _lbl(text="", cls=(), xalign=0, **kw):
    lab = Gtk.Label(label=text, xalign=xalign, **kw)
    for c in cls:
        lab.add_css_class(c)
    return lab


def t(v):
    return "–" if v is None else f"{round(v)}°"


class DeskWidget(Gtk.Window):
    def __init__(self, app_win, kind):
        name, _desc, _ic, w, _h = W.KINDS[kind]
        super().__init__(title=f"KS-widget-{kind}", decorated=False, resizable=False,
                         default_width=w * 18 + 40)
        self.app_win, self.kind = app_win, kind
        self.add_css_class("ks-desk")
        self.add_css_class("ks-glass")
        try:
            import spotlight
            spotlight.attach(self)
        except Exception:  # noqa: BLE001
            pass
        handle = Gtk.WindowHandle()                          # dra hvor som helst for å flytte
        self.set_child(handle)
        ov = Gtk.Overlay()
        handle.set_child(ov)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.body.add_css_class("ks-desk-body")
        ov.set_child(self.body)
        self.close_btn = Gtk.Button(icon_name="window-close-symbolic", halign=Gtk.Align.END, valign=Gtk.Align.START,
                                    margin_top=6, margin_end=6, opacity=0, tooltip_text=i18n.tr("Fjern widgeten"))
        self.close_btn.add_css_class("circular")
        self.close_btn.add_css_class("ks-desk-x")
        self.close_btn.connect("clicked", lambda *_: self.remove_widget())
        ov.add_overlay(self.close_btn)
        mo = Gtk.EventControllerMotion()
        mo.connect("enter", lambda *_: self.close_btn.set_opacity(1))
        mo.connect("leave", lambda *_: self.close_btn.set_opacity(0))
        self.add_controller(mo)
        self.body.append(_lbl(i18n.tr(name).upper(), ("ks-desk-title",)))
        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.body.append(self.content)
        self._sig = None
        self.refresh()
        self._timer = GLib.timeout_add_seconds(3, self.refresh)
        self.connect("close-request", self._on_close)
        if IS_WIN:
            GLib.timeout_add(400, self._win_setup)

    # --- data ---
    def refresh(self):
        try:
            d = W.data(self.app_win)
        except Exception:  # noqa: BLE001
            return True
        sig = repr({k: v for k, v in d.items() if k != "time"})
        if sig != self._sig:
            self._sig = sig
            while (c := self.content.get_first_child()) is not None:
                self.content.remove(c)
            getattr(self, "_draw_" + self.kind)(d)
        return True

    def _bigrow(self, items):
        row = Gtk.Box(spacing=22)
        for label, value in items:
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            col.append(_lbl(label, ("ks-desk-k",)))
            col.append(_lbl(value, ("ks-desk-big", "numeric")))
            row.append(col)
        self.content.append(row)

    def _draw_status(self, d):
        self.content.append(_lbl(d.get("name") or "", ("ks-desk-name",)))
        self._bigrow([("CPU", t(d.get("cpu_t"))), ("GPU", t(d.get("gpu_t"))), (i18n.tr("STRØM"), f"{d.get('watts') or 0} W")])
        self.content.append(_lbl(("🎮 " + d["game"]) if d.get("game") else (d.get("mode_name") or ""), ("ks-desk-sub",),
                                 ellipsize=3))

    def _draw_temp(self, d):
        self._bigrow([("CPU", t(d.get("cpu_t"))), ("GPU", t(d.get("gpu_t"))), (i18n.tr("STRØM"), f"{d.get('watts') or 0} W")])
        if d.get("kwh") is not None:
            self.content.append(_lbl(i18n.tr("I dag") + f" {d['kwh']} kWh · {d['kr']} kr", ("ks-desk-sub",)))

    def _draw_quick(self, d):
        row = Gtk.Box(spacing=8, homogeneous=True)
        for icon, label, body, on in (("🎮", "Spillmodus", {"a": "gamemode", "on": not d.get("gamemode")}, d.get("gamemode")),
                                      ("🎬", "Lagre klipp", {"a": "clip"}, False),
                                      ("🔒", "Lås", {"a": "system", "do": "lock"}, False),
                                      ("🔇", "Demp", {"a": "volume", "mute": True}, False)):
            b = Gtk.Button()
            b.add_css_class("ks-desk-btn")
            if on:
                b.add_css_class("on")
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            col.append(_lbl(icon, ("ks-desk-ic",), xalign=0.5))
            col.append(_lbl(i18n.tr(label), ("ks-desk-bl",), xalign=0.5))
            b.set_child(col)
            b.connect("clicked", lambda _b, bd=body: self._act(bd))
            row.append(b)
        self.content.append(row)

    def _draw_family(self, d):
        others = [p for p in d.get("pcs") or [] if not p.get("me")]
        if not others:
            self.content.append(_lbl(i18n.tr("Ingen andre PC-er ennå"), ("ks-desk-sub",)))
        for p in others:
            r = Gtk.Box(spacing=10)
            r.append(_lbl("●", ("ks-ok" if p.get("on") else "ks-off",)))
            r.append(_lbl(p.get("name") or "?", ("ks-desk-row",)))
            r.append(_lbl(("🎮 " + p["game"]) if p.get("game") else (i18n.tr("på") if p.get("on") else i18n.tr("av")),
                          ("ks-desk-sub",), hexpand=True, ellipsize=3))
            self.content.append(r)
        b = Gtk.Button(label="🍽️  " + i18n.tr("Middag!"))
        b.add_css_class("ks-desk-btn")
        b.add_css_class("slim")
        b.connect("clicked", lambda *_: self._act({"a": "dinner", "to": "*"}))
        self.content.append(b)

    def _draw_battery(self, d):
        bats = d.get("batteries") or []
        if not bats:
            self.content.append(_lbl(i18n.tr("Ingen trådløse enheter"), ("ks-desk-sub",)))
        for b in bats:
            r = Gtk.Box(spacing=10)
            r.append(_lbl({"headset": "🎧", "keyboard": "⌨️"}.get(b.get("kind"), "🖱️")))
            r.append(_lbl(b.get("name") or "", ("ks-desk-row",), hexpand=True, ellipsize=3))
            chg = b.get("charging") or b.get("full")
            lb = Gtk.LevelBar(min_value=0, max_value=100, value=b.get("pct") or (100 if chg else 0), valign=Gtk.Align.CENTER)
            lb.set_size_request(70, 8)
            r.append(lb)
            import batteries
            txt = batteries.label(b).replace(" · ", " ").replace("Lader ", "").replace("Fulladet ", "") \
                if b.get("pct") is not None else batteries.label(b)
            t = _lbl(txt, ("ks-desk-row", "numeric"))
            if chg:
                for w in (lb, t):
                    w.add_css_class("ks-charging")
            r.append(t)
            self.content.append(r)

    def _draw_calendar(self, d):
        self.content.append(_lbl(d.get("cal_date") or "", ("ks-desk-name",)))
        self.content.append(_lbl(d.get("cal_today") or i18n.tr("Ingenting i dag"), ("ks-desk-sub",), wrap=True))
        self.content.append(_lbl(d.get("cal_red") or "", ("ks-desk-sub",)))

    def _draw_playtime(self, d):
        s = d.get("play_s") or 0
        self.content.append(_lbl(f"{s // 3600} t {(s % 3600) // 60} min", ("ks-desk-big", "numeric")))
        lim = d.get("limit_h")
        if lim:
            lb = Gtk.LevelBar(min_value=0, max_value=1, value=min(1, s / (lim * 3600)))
            lb.set_size_request(-1, 8)
            self.content.append(lb)
            self.content.append(_lbl(i18n.tr("Grense i dag:") + f" {lim:g} t", ("ks-desk-sub",)))
        elif d.get("top_game"):
            self.content.append(_lbl(i18n.tr("Mest:") + " " + d["top_game"], ("ks-desk-sub",), ellipsize=3))

    def _act(self, body):
        try:
            W.local_action(self.app_win, body)
        except Exception as e:  # noqa: BLE001
            self.app_win.toast(str(e)) if hasattr(self.app_win, "toast") else None
        GLib.timeout_add(500, lambda: (setattr(self, "_sig", None), self.refresh(), False)[2])

    # --- lukking og plassering ---
    def remove_widget(self):
        c = W.cfg()
        c["desk"].setdefault(self.kind, {})["on"] = False
        W.save_cfg(c)
        self.close()

    def _on_close(self, *_):
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0
        if IS_WIN:
            self._win_save()
        OPEN.pop(self.kind, None)
        return False

    def _hwnd(self):
        import ctypes
        return ctypes.windll.user32.FindWindowW(None, self.get_title())

    def _win_setup(self):
        try:
            import ctypes
            u = ctypes.windll.user32
            h = self._hwnd()
            if not h:
                return False
            GWL_EXSTYLE, WS_EX_TOOLWINDOW, WS_EX_APPWINDOW = -20, 0x80, 0x40000
            ex = u.GetWindowLongW(h, GWL_EXSTYLE)
            u.SetWindowLongW(h, GWL_EXSTYLE, (ex | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW)   # ikke i oppgavelinjen
            p = W.cfg()["desk"].get(self.kind, {})
            top = -1 if p.get("top") else -2                                              # TOPMOST / NOTOPMOST
            flags = 0x0001 | 0x0010 | (0 if "x" in p else 0x0002)                         # NOSIZE|NOACTIVATE(|NOMOVE)
            u.SetWindowPos(h, top, int(p.get("x", 0)), int(p.get("y", 0)), 0, 0, flags)
        except Exception:  # noqa: BLE001
            pass
        GLib.timeout_add_seconds(20, lambda: (self._win_save(), self.get_visible())[1])
        return False

    def _win_save(self):
        try:
            import ctypes
            from ctypes import wintypes
            h = self._hwnd()
            if not h:
                return
            r = wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(h, ctypes.byref(r))
            c = W.cfg()
            d = c["desk"].setdefault(self.kind, {})
            if (d.get("x"), d.get("y")) != (r.left, r.top):
                d.update(x=r.left, y=r.top)
                W.save_cfg(c)
        except Exception:  # noqa: BLE001
            pass


def show(app_win, kind, save=True):
    if kind in OPEN:
        OPEN[kind].present()
        return
    w = DeskWidget(app_win, kind)
    if app_win is not None and app_win.get_application():
        w.set_application(app_win.get_application())
    OPEN[kind] = w
    w.present()
    if save:
        c = W.cfg()
        c["desk"].setdefault(kind, {})["on"] = True
        W.save_cfg(c)


def hide(kind):
    w = OPEN.get(kind)
    if w:
        w.remove_widget()
    else:
        c = W.cfg()
        c["desk"].setdefault(kind, {})["on"] = False
        W.save_cfg(c)


def set_top(kind, on):
    c = W.cfg()
    c["desk"].setdefault(kind, {})["top"] = bool(on)
    W.save_cfg(c)
    w = OPEN.get(kind)
    if w and IS_WIN:
        w._win_setup()


def restore(app_win):
    """Ved oppstart: åpne widgetene som var på sist."""
    for kind, p in W.cfg()["desk"].items():
        if p.get("on") and kind in W.KINDS:
            show(app_win, kind, save=False)
    return False
