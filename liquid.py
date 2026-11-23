"""«Liquid Glass»-temaet: hele vinduet er gjennomsiktig glass – du ser det som er bak – med justerbar
gjennomsiktighet og farge på glasset.

  • Utseende: farget, gjennomsiktig glass med lys kant, myk glans og dybde (theme.theme_css bruker css()).
  • Linux/KDE: ekte uskarphet bak vinduet (som Aero i Windows 7) med KWin sin blur-protokoll
    (org_kde_kwin_blur) – snakket med direkte via libwayland-client på en egen kø, så GTK ikke forstyrres.
  • Windows 11: Mica/Acrylic-bakgrunn med DwmSetWindowAttribute.

Innstillingene ligger i utseende.json: liquid_clear (0–95 % gjennomsiktig), liquid_tint (#rrggbb), liquid_blur.
"""
import ctypes
import json
import os
import sys

IS_WIN = sys.platform == "win32"
LOOK = os.path.expanduser("~/.config/systemmonitor/utseende.json")
DEFAULT = {"liquid_clear": 50, "liquid_tint": "#7aa2ff", "liquid_blur": True}


def cfg():
    try:
        with open(LOOK) as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    return {k: d.get(k, v) for k, v in DEFAULT.items()}


def set_(**kw):
    try:
        with open(LOOK) as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    d.update({k: v for k, v in kw.items() if k in DEFAULT})
    os.makedirs(os.path.dirname(LOOK), exist_ok=True)
    with open(LOOK, "w") as f:
        json.dump(d, f)


def _rgb(hx):
    hx = (hx or "#7aa2ff").lstrip("#")
    try:
        return tuple(int(hx[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return (122, 162, 255)


def native_blur():
    """GTK 4.22+ ber selv skrivebordet om uskarphet bak vinduet (CSS backdrop-filter → ext-background-effect)."""
    try:
        from gi.repository import Gtk
        return (Gtk.get_major_version(), Gtk.get_minor_version()) >= (4, 22) and not IS_WIN
    except Exception:  # noqa: BLE001
        return False


def css():
    """Stilarket for glasset. Jo mer gjennomsiktig, jo mer av det bak skinner gjennom."""
    c = cfg()
    blur = (f"backdrop-filter: blur({18 + int(c['liquid_clear']) // 4}px);"
            if c["liquid_blur"] and native_blur() else "")
    r, g, b = _rgb(c["liquid_tint"])
    a = max(0.05, 1 - min(95, max(0, int(c["liquid_clear"]))) / 100)     # dekkevne for selve vinduet
    dark = (0.299 * r + 0.587 * g + 0.114 * b) < 215          # mørkt glass med lys tekst – med mindre glasset er nesten hvitt
    t = f"{r},{g},{b}"
    # glasset: en mørk (eller lys) flate farget av glassfargen – dekkevnen følger gjennomsiktigheten
    br, bg_, bb = (12, 14, 22) if dark else (245, 247, 252)
    mix = 0.30
    base = f"{int(br * (1 - mix) + r * mix)},{int(bg_ * (1 - mix) + g * mix)},{int(bb * (1 - mix) + b * mix)}"
    fg = "#f5f7ff" if dark else "#14161f"
    dim = "rgba(235,240,255,0.72)" if dark else "rgba(20,24,40,0.62)"
    # vinduet: glass i glassfargen, blandet med en mørk/lys base så teksten alltid kan leses
    win = f"rgba({base},{a:.3f})"
    side = f"rgba({base},{min(0.95, a + 0.12):.3f})"
    card = f"rgba(255,255,255,{0.05 + a * 0.06:.3f})" if dark else f"rgba(255,255,255,{0.25 + a * 0.2:.3f})"
    pop = f"rgba({base},{max(0.88, a):.3f})"
    shadow = "label { text-shadow: 0 1px 2px rgba(0,0,0,0.35); }" if dark else ""
    return f"""
:root {{
  --window-bg-color: {win}; --window-fg-color: {fg};
  --view-bg-color: transparent; --view-fg-color: {fg};
  --headerbar-bg-color: transparent; --headerbar-fg-color: {fg}; --headerbar-shade-color: transparent;
  --sidebar-bg-color: {side}; --sidebar-fg-color: {fg}; --secondary-sidebar-bg-color: {side};
  --card-bg-color: {card}; --card-fg-color: {fg};
  --popover-bg-color: {pop}; --popover-fg-color: {fg};
  --dialog-bg-color: {pop}; --dialog-fg-color: {fg};
  --accent-bg-color: rgb({t}); --accent-color: rgb({t}); --accent-fg-color: {'white' if dark else '#111'};
}}
window.sysmon, window.background {{
  background-color: {win}; color: {fg}; {blur}
  background-image: linear-gradient(160deg, rgba(255,255,255,0.10), rgba(255,255,255,0.0) 38%),
                    radial-gradient(ellipse 80% 55% at 12% -10%, rgba({t},{0.22 + a * 0.2:.2f}), transparent 70%);
}}
.ks-content {{ background-image: none; background-color: transparent; }}
.ks-side {{ background-color: {side}; background-image: linear-gradient(180deg, rgba(255,255,255,0.08),
  rgba(255,255,255,0.0) 30%); box-shadow: inset -1px 0 rgba(255,255,255,0.14); }}
headerbar {{ background: transparent; box-shadow: none; }}
.card, .ks-card, .boxed-list, list.boxed-list, .ks-tile {{
  background-color: {card};
  background-image: linear-gradient(150deg, rgba(255,255,255,0.14), rgba(255,255,255,0.02) 55%);
  border: 1px solid rgba(255,255,255,0.20);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.32), inset 0 -1px 0 rgba(0,0,0,0.12),
              0 10px 30px -12px rgba(0,0,0,0.45);
}}
button:not(.flat):not(.suggested-action):not(.destructive-action), .ks-swatch {{
  background-image: linear-gradient(180deg, rgba(255,255,255,0.18), rgba(255,255,255,0.05));
  border: 1px solid rgba(255,255,255,0.18);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.30);
}}
entry, textview text, .ks-ai-input {{ background-color: rgba({base},0.35); }}
popover > contents, dialog > box, .dialog-contents {{ border: 1px solid rgba(255,255,255,0.18); }}
.dim-label, .ks-sub, .ks-hello-sub {{ color: {dim}; opacity: 1; }}
.ks-brand-logo {{ background-image: linear-gradient(135deg, rgb({t}), rgba({t},0.6)); }}
{shadow}
"""


def theme_entry():
    c = cfg()
    tint = c["liquid_tint"]
    return {"name": "Liquid Glass", "desc": "Gjennomsiktig glass – du ser det som er bak", "dark": True,
            "a": tint, "b": tint, "c": "#ffffff", "bg": "#101420", "side": "#121726", "card": "#1a2033",
            "fg": "#f5f7ff", "dim": "#b9c2dc", "liquid": True}


# --------------------------------------------------------------------------
# Uskarphet bak vinduet – KDE/KWin (Wayland)
# --------------------------------------------------------------------------
class _Msg(ctypes.Structure):
    _fields_ = [("name", ctypes.c_char_p), ("signature", ctypes.c_char_p), ("types", ctypes.POINTER(ctypes.c_void_p))]


class _Iface(ctypes.Structure):
    pass


_Iface._fields_ = [("name", ctypes.c_char_p), ("version", ctypes.c_int), ("method_count", ctypes.c_int),
                   ("methods", ctypes.POINTER(_Msg)), ("event_count", ctypes.c_int),
                   ("events", ctypes.POINTER(_Msg))]
_W = {"init": False, "ok": False, "manager": None, "blurs": {}, "keep": []}


def _types(*ptrs):
    arr = (ctypes.c_void_p * max(1, len(ptrs)))(*[ctypes.cast(p, ctypes.c_void_p) if p is not None else None
                                                  for p in ptrs])
    _W["keep"].append(arr)
    return ctypes.cast(arr, ctypes.POINTER(ctypes.c_void_p))


def _gptr(obj):
    """C-pekeren til et GObject (for å kalle GTK sine C-funksjoner)."""
    ctypes.pythonapi.PyCapsule_GetPointer.restype = ctypes.c_void_p
    ctypes.pythonapi.PyCapsule_GetPointer.argtypes = [ctypes.py_object, ctypes.c_char_p]
    return ctypes.pythonapi.PyCapsule_GetPointer(obj.__gpointer__, None)


def _wayland_init(display):
    """Finn tjenesten for uskarphet bak vinduer én gang (egen kø – rører ikke GTK sine hendelser).
    Ny standard: ext_background_effect_manager_v1 (KDE Plasma 6.4+ m.fl.). Eldre KDE: org_kde_kwin_blur_manager."""
    if _W["init"]:
        return _W["ok"]
    _W["init"] = True
    try:
        wl = ctypes.CDLL("libwayland-client.so.0")
        gtk = ctypes.CDLL("libgtk-4.so.1")
        gtk.gdk_wayland_display_get_wl_display.restype = ctypes.c_void_p
        gtk.gdk_wayland_display_get_wl_display.argtypes = [ctypes.c_void_p]
        gtk.gdk_wayland_surface_get_wl_surface.restype = ctypes.c_void_p
        gtk.gdk_wayland_surface_get_wl_surface.argtypes = [ctypes.c_void_p]
        wld = gtk.gdk_wayland_display_get_wl_display(_gptr(display))
        if not wld:
            return False
        surf_if = _Iface.in_dll(wl, "wl_surface_interface")
        region_if = _Iface.in_dll(wl, "wl_region_interface")
        reg_if = _Iface.in_dll(wl, "wl_registry_interface")
        comp_if = _Iface.in_dll(wl, "wl_compositor_interface")
        # ny standard
        eff_methods = (_Msg * 2)(_Msg(b"destroy", b"", _types()),
                                 _Msg(b"set_blur_region", b"?o", _types(ctypes.pointer(region_if))))
        eff_if = _Iface(b"ext_background_effect_surface_v1", 1, 2, eff_methods, 0, None)
        bm_methods = (_Msg * 2)(_Msg(b"destroy", b"", _types()),
                                _Msg(b"get_background_effect", b"no",
                                     _types(ctypes.pointer(eff_if), ctypes.pointer(surf_if))))
        bm_events = (_Msg * 1)(_Msg(b"capabilities", b"u", _types(None)))
        bm_if = _Iface(b"ext_background_effect_manager_v1", 1, 2, bm_methods, 1, bm_events)
        # gammel KDE-protokoll
        blur_methods = (_Msg * 3)(_Msg(b"commit", b"", _types()),
                                  _Msg(b"set_region", b"?o", _types(ctypes.pointer(region_if))),
                                  _Msg(b"release", b"", _types()))
        blur_if = _Iface(b"org_kde_kwin_blur", 1, 3, blur_methods, 0, None)
        mgr_methods = (_Msg * 2)(_Msg(b"create", b"no", _types(ctypes.pointer(blur_if), ctypes.pointer(surf_if))),
                                 _Msg(b"unset", b"o", _types(ctypes.pointer(surf_if))))
        mgr_if = _Iface(b"org_kde_kwin_blur_manager", 1, 2, mgr_methods, 0, None)
        _W["keep"] += [eff_methods, eff_if, bm_methods, bm_events, bm_if, blur_methods, mgr_methods, blur_if, mgr_if]
        mf = wl.wl_proxy_marshal_flags
        mf.restype = ctypes.c_void_p
        wl.wl_display_create_queue.restype = ctypes.c_void_p
        wl.wl_display_create_queue.argtypes = [ctypes.c_void_p]
        wl.wl_proxy_create_wrapper.restype = ctypes.c_void_p
        wl.wl_proxy_create_wrapper.argtypes = [ctypes.c_void_p]
        wl.wl_proxy_set_queue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        wl.wl_proxy_add_listener.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        wl.wl_display_roundtrip_queue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        wl.wl_display_flush.argtypes = [ctypes.c_void_p]
        queue = wl.wl_display_create_queue(wld)
        wrapper = wl.wl_proxy_create_wrapper(wld)
        wl.wl_proxy_set_queue(wrapper, queue)
        registry = mf(ctypes.c_void_p(wrapper), ctypes.c_uint32(1), ctypes.byref(reg_if), ctypes.c_uint32(1),
                      ctypes.c_uint32(0), None)
        found = {}
        GLOBAL = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p,
                                  ctypes.c_uint32)
        REMOVE = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32)

        def on_global(_d, _r, name, iface, ver):
            if iface in (b"ext_background_effect_manager_v1", b"org_kde_kwin_blur_manager", b"wl_compositor"):
                found[iface] = (name, ver)
        cb = (GLOBAL(on_global), REMOVE(lambda *_a: None))
        listener = (ctypes.c_void_p * 2)(ctypes.cast(cb[0], ctypes.c_void_p), ctypes.cast(cb[1], ctypes.c_void_p))
        _W["keep"] += [cb, listener]
        wl.wl_proxy_add_listener(registry, ctypes.cast(listener, ctypes.c_void_p), None)
        wl.wl_display_roundtrip_queue(wld, queue)

        def bind(iface, ifc, ver):
            name, _v = found[iface]
            return mf(ctypes.c_void_p(registry), ctypes.c_uint32(0), ctypes.byref(ifc), ctypes.c_uint32(ver),
                      ctypes.c_uint32(0), ctypes.c_uint32(name), ctypes.c_char_p(iface), ctypes.c_uint32(ver), None)
        _W.update(wl=wl, gtk=gtk, wld=wld, mf=mf)
        if b"ext_background_effect_manager_v1" in found and b"wl_compositor" in found:
            _W.update(kind="ext", manager=bind(b"ext_background_effect_manager_v1", bm_if, 1),
                      comp=bind(b"wl_compositor", comp_if, min(4, found[b"wl_compositor"][1])),
                      eff_if=eff_if, region_if=region_if)
        elif b"org_kde_kwin_blur_manager" in found:
            _W.update(kind="kde", manager=bind(b"org_kde_kwin_blur_manager", mgr_if, 1), blur_if=blur_if)
        else:
            return False
        _W["ok"] = bool(_W["manager"])
        return _W["ok"]
    except (OSError, AttributeError, ValueError, TypeError):
        return False


def _blur_linux(win, on):
    try:
        import gi
        gi.require_version("GdkWayland", "4.0")
        from gi.repository import GdkWayland
    except (ValueError, ImportError):
        return False
    disp = win.get_display()
    surface = win.get_surface()
    if not isinstance(disp, GdkWayland.WaylandDisplay) or surface is None or not _wayland_init(disp):
        return False
    wl, mf = _W["wl"], _W["mf"]
    wsurf = _W["gtk"].gdk_wayland_surface_get_wl_surface(_gptr(surface))
    if not wsurf:
        return False
    key = int(wsurf)
    u = ctypes.c_uint32
    if _W["kind"] == "ext":
        if on and key not in _W["blurs"]:
            eff = mf(ctypes.c_void_p(_W["manager"]), u(1), ctypes.byref(_W["eff_if"]), u(1), u(0), None,
                     ctypes.c_void_p(wsurf))
            region = mf(ctypes.c_void_p(_W["comp"]), u(1), ctypes.byref(_W["region_if"]), u(1), u(0), None)
            mf(ctypes.c_void_p(region), u(1), None, u(1), u(0), ctypes.c_int(0), ctypes.c_int(0),
               ctypes.c_int(32767), ctypes.c_int(32767))                                                     # add
            mf(ctypes.c_void_p(eff), u(1), None, u(1), u(0), ctypes.c_void_p(region))                        # set_blur_region
            mf(ctypes.c_void_p(region), u(0), None, u(1), u(1))                                              # destroy
            _W["blurs"][key] = eff
        elif not on and key in _W["blurs"]:
            eff = _W["blurs"].pop(key)
            mf(ctypes.c_void_p(eff), u(1), None, u(1), u(0), None)                                           # ingen blur
            mf(ctypes.c_void_p(eff), u(0), None, u(1), u(1))                                                 # destroy
    else:
        if on and key not in _W["blurs"]:
            blur = mf(ctypes.c_void_p(_W["manager"]), u(0), ctypes.byref(_W["blur_if"]), u(1), u(0), None,
                      ctypes.c_void_p(wsurf))
            mf(ctypes.c_void_p(blur), u(1), None, u(1), u(0), None)
            mf(ctypes.c_void_p(blur), u(0), None, u(1), u(0))
            _W["blurs"][key] = blur
        elif not on and key in _W["blurs"]:
            mf(ctypes.c_void_p(_W["manager"]), u(1), None, u(1), u(0), ctypes.c_void_p(wsurf))
            mf(ctypes.c_void_p(_W["blurs"].pop(key)), u(2), None, u(1), u(1))
    wl.wl_display_flush(ctypes.c_void_p(_W["wld"]))
    win.queue_draw()                                       # neste bilde fra GTK tar uskarpheten i bruk
    return True


# --------------------------------------------------------------------------
# Windows 11: Mica/Acrylic
# --------------------------------------------------------------------------
def _blur_windows(win, on):
    try:
        import gi
        gi.require_version("GdkWin32", "4.0")
        from gi.repository import GdkWin32
        hwnd = GdkWin32.Win32Surface.get_handle(win.get_surface())
        val = ctypes.c_int(3 if on else 1)                 # 3 = Acrylic, 1 = ingen
        ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), 38, ctypes.byref(val), 4)
        dark = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), 20, ctypes.byref(dark), 4)
        return True
    except Exception:  # noqa: BLE001
        return False


def set_blur(win, on):
    """Uskarphet bak vinduet av/på. Returnerer True hvis skrivebordet støtter det."""
    if win is None or win.get_surface() is None:
        return False
    if native_blur():                                       # GTK gjør det selv ut fra stilarket (css())
        return True
    on = on and cfg()["liquid_blur"]
    return _blur_windows(win, on) if IS_WIN else _blur_linux(win, on)


def apply(on):
    """Kalles når temaet byttes: uskarphet på alle vinduene i programmet (eller av)."""
    from gi.repository import Gtk
    res = []
    for w in Gtk.Window.list_toplevels():
        if w.get_mapped():
            res.append(set_blur(w, on))
        else:
            w.connect("map", lambda ww, o=on: set_blur(ww, o))
    return any(res)
