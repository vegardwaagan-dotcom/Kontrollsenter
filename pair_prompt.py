"""«Spør PC-en om tilgang»: når en ny telefon/nettbrett vil pares, spør PC-en deg – Godta, Godta begrenset eller Avvis.

Vises som et eget lite vindu (også når Kontrollsenter bare ligger i statusfeltet) og som et varsel med knapper
(Linux) / varsel fra statusfeltet (Windows). Telefonen viser den samme kontrollkoden, så du ser at det er din."""
import sys
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

import i18n  # noqa: E402

_t = i18n.tr
_OPEN = {}                                            # id -> vindu


def install(app, bg):
    """Kobles på ved oppstart (background.py): handlinger for varselknappene + spørsmålet ved nye forespørsler."""
    import remote
    for name, ok, role in (("pair-ok", True, "full"), ("pair-limited", True, "begrenset"), ("pair-no", False, "")):
        act = Gio.SimpleAction.new(name, GLib.VariantType.new("s"))
        act.connect("activate", lambda _a, v, ok=ok, role=role: _decide(v.get_string(), ok, role))
        app.add_action(act)
    act = Gio.SimpleAction.new("pair-show", GLib.VariantType.new("s"))
    act.connect("activate", lambda _a, v: _show_id(v.get_string()))
    app.add_action(act)
    if remote.INSTANCE:
        remote.INSTANCE.on_request = lambda req: ask(app, bg, req)


def _decide(rid, ok, role):
    import remote
    r = remote.INSTANCE
    name = r.decide(rid, ok, role) if r else None
    w = _OPEN.pop(rid, None)
    if w:
        w.close()
    try:
        Gio.Application.get_default().withdraw_notification("pair-" + rid[:12])
    except Exception:  # noqa: BLE001
        pass
    if name and ok:
        try:
            import remote_extra
            remote_extra.event("pair", f"{name} er paret", "Godtatt på PC-en" +
                               (" (begrenset tilgang)" if role == "begrenset" else ""), "info")
        except Exception:  # noqa: BLE001
            pass
    return name


def _show_id(rid):
    import remote
    for req in (remote.INSTANCE.pending() if remote.INSTANCE else []):
        if req["id"] == rid:
            _window(req)


def ask(app, bg, req):
    rid = req["id"]
    title = _t("Ny enhet vil kobles til")
    body = (f"«{req['name']}» ({req['ip']}) " + _t("vil styre denne PC-en.") + " " +
            _t("Kontrollkode") + f": {req['check']}")
    try:
        import remote_extra
        remote_extra.event("pair", title, body, "warn")
    except Exception:  # noqa: BLE001
        pass
    if sys.platform == "win32":
        tray = getattr(bg, "tray", None)
        if tray and hasattr(tray, "notify"):
            tray.notify(title, body)
    else:                                             # varsel med knapper – sendes også mens du spiller
        n = Gio.Notification.new(title)
        n.set_body(body)
        n.set_icon(Gio.ThemedIcon.new("no.waagan.Systemmonitor"))
        n.set_priority(Gio.NotificationPriority.URGENT)
        n.set_default_action_and_target("app.pair-show", GLib.Variant("s", rid))
        n.add_button_with_target(_t("Godta"), "app.pair-ok", GLib.Variant("s", rid))
        n.add_button_with_target(_t("Begrenset"), "app.pair-limited", GLib.Variant("s", rid))
        n.add_button_with_target(_t("Avvis"), "app.pair-no", GLib.Variant("s", rid))
        app.send_notification("pair-" + rid[:12], n)
    _window(req)


def _window(req):
    import remote
    rid = req["id"]
    if rid in _OPEN:
        _OPEN[rid].present()
        return
    w = Adw.Window(title=_t("Ny enhet vil kobles til"), default_width=440, resizable=False)
    app = Gio.Application.get_default()
    if isinstance(app, Gtk.Application):
        w.set_application(app)
    w.add_css_class("ks-pair-prompt")
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=24, margin_bottom=20,
                  margin_start=24, margin_end=24)
    ic = Gtk.Image.new_from_icon_name("phone-symbolic")
    ic.set_pixel_size(48)
    box.append(ic)
    h = Gtk.Label(label=_t("Ny enhet vil kobles til"), wrap=True)
    h.add_css_class("title-2")
    box.append(h)
    who = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
    who.set_markup(f"<b>{GLib.markup_escape_text(req['name'])}</b>\n"
                   f"<span alpha='70%'>{GLib.markup_escape_text(req['ip'])}</span>")
    box.append(who)
    info = Gtk.Label(label=_t("vil styre denne PC-en fra mobilappen. Godta bare hvis det er din enhet og telefonen "
                              "viser den samme koden:"), wrap=True, justify=Gtk.Justification.CENTER)
    info.add_css_class("dim-label")
    box.append(info)
    code = Gtk.Label(label=" ".join(req["check"]))
    code.add_css_class("title-1")
    code.add_css_class("ks-mono")
    box.append(code)
    left = Gtk.Label()
    left.add_css_class("caption")
    left.add_css_class("dim-label")
    box.append(left)
    btns = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER, margin_top=6)
    no = Gtk.Button(label=_t("Avvis"))
    no.add_css_class("destructive-action")
    lim = Gtk.Button(label=_t("Godta begrenset"))
    lim.set_tooltip_text(_t("Kan se alt, starte spill og styre lyd – men ikke slå av PC-en, "
                             "endre vifter, strømmodus eller avslutte programmer"))
    ok = Gtk.Button(label=_t("Godta"))
    ok.add_css_class("suggested-action")
    for b, args in ((no, (False, "")), (lim, (True, "begrenset")), (ok, (True, "full"))):
        b.connect("clicked", lambda _b, a=args: _decide(rid, *a))
        btns.append(b)
    box.append(btns)
    w.set_content(box)

    def tick():
        if rid not in _OPEN:
            return False
        r = remote.INSTANCE
        still = r and any(x["id"] == rid for x in r.pending())
        if not still:                                 # avgjort fra varselet, eller utløpt
            _OPEN.pop(rid, None)
            w.close()
            return False
        secs = int(remote.Remote.REQ_TTL - (time.time() - req["t"]))
        left.set_label(_t("Utløper om {} s").replace("{}", str(max(0, secs))))
        return True

    w.connect("close-request", lambda *_: (_OPEN.pop(rid, None), False)[1])
    _OPEN[rid] = w
    tick()
    GLib.timeout_add_seconds(1, tick)
    w.present()
