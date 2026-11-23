"""Smart Hjem-automatikk:

* Hue følger spillet – når et spill starter, får lysene spillets temafarge (dempet); de settes tilbake etterpå.
* TV-en slås av når PC-en går i hvilemodus eller slås av (Linux: logind sier fra, og vi får et par sekunder).
* Synk RGB og Hue – lysene i rommet og i PC-en har alltid samme farge. Endrer du farge i Kontrollsenter, følger Hue
  etter; endrer du farge i Hue-appen, følger RGB-lysene i PC-en etter (sjekkes hvert 10. sekund).

Valgene lagres i smarthjem.json (game_hue, tv_off_sleep, sync_rgb_hue).
"""
import sys
import threading
import time

from gi.repository import Gio, GLib

_STATE = {"snap": None, "last_hex": None, "inhibit": None, "started": False}


def opt(key, default=False):
    try:
        import smarthome
        return bool(smarthome.cfg().get(key, default))
    except Exception:  # noqa: BLE001
        return default


def set_opt(key, val):
    import smarthome
    c = smarthome.cfg()
    c[key] = bool(val)
    smarthome.save_cfg(c)
    if key == "tv_off_sleep":
        _sleep_inhibit(bool(val))


def _bg(fn):
    threading.Thread(target=fn, daemon=True).start()


# ---- Hue følger spillet ----------------------------------------------------------------------------------
def on_game(name, color=None):
    """name = spillet som startet (None = avsluttet). color = temafargen (hex) for spillet, eller None."""
    if not __import__("funksjoner").on("smarthjem"):          # funksjonen er slått av
        return
    if not opt("game_hue"):
        return

    def work():
        import features as F
        import smarthome
        try:
            if name and color:
                if _STATE["snap"] is None:                      # husk hvordan lysene var
                    _STATE["snap"] = {k: v.get("state", {}) for k, v in F._hue("lights").items()}
                smarthome.hue_light(None, None, True, 90, color)
            elif not name and _STATE["snap"]:
                for lid, st in _STATE["snap"].items():
                    body = {k: st[k] for k in ("on", "bri", "xy", "ct") if k in st}
                    if not body.get("on"):
                        body = {"on": False}
                    try:
                        F._hue(f"lights/{int(lid)}/state", body)
                    except Exception:  # noqa: BLE001
                        continue
                _STATE["snap"] = None
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("hue følger spillet")
    _bg(work)


# ---- TV av når PC-en sover ---------------------------------------------------------------------------------
def _tv_off():
    try:
        import smarthome
        for ip in list((smarthome.cfg().get("tvs") or {}).keys()):
            if smarthome.tv_state(ip).get("power") == "on":
                smarthome.tv_key(ip, "power")
    except Exception:  # noqa: BLE001
        import applog
        applog.log.exception("TV av ved hvilemodus")


def _sleep_inhibit(on):
    """Be logind om å vente litt før hvilemodus, så vi rekker å slå av TV-en."""
    if sys.platform == "win32":
        return
    if not on:
        _STATE["inhibit"] = None
        return
    if _STATE["inhibit"] is not None:
        return
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        res, fds = bus.call_with_unix_fd_list_sync(
            "org.freedesktop.login1", "/org/freedesktop/login1", "org.freedesktop.login1.Manager", "Inhibit",
            GLib.Variant("(ssss)", ("sleep:shutdown", "Kontrollsenter", "Slår av TV-en først", "delay")),
            GLib.VariantType.new("(h)"), Gio.DBusCallFlags.NONE, 3000, None, None)
        _STATE["inhibit"] = fds          # holdes åpen til vi har gjort jobben
    except Exception:  # noqa: BLE001
        _STATE["inhibit"] = None


def _on_prepare(_c, _s, _p, _i, sig, params):
    going = params.unpack()[0]
    if going and opt("tv_off_sleep"):
        _tv_off()
        _STATE["inhibit"] = None                         # slipp – nå kan PC-en sove
    elif not going and opt("tv_off_sleep"):
        GLib.timeout_add_seconds(2, lambda: (_sleep_inhibit(True), False)[1])   # våknet: ta ny «vent litt»


# ---- synk RGB og Hue -----------------------------------------------------------------------------------------
def rgb_changed(color):
    """Kalles når Kontrollsenter setter RGB-farge (r, g, b) – eller None for «av»."""
    if not __import__("funksjoner").on("smarthjem"):          # funksjonen er slått av
        return
    if not opt("sync_rgb_hue"):
        return
    hexc = None if color is None else "#%02x%02x%02x" % tuple(int(c) for c in color)
    if hexc == _STATE["last_hex"]:
        return
    _STATE["last_hex"] = hexc

    def work():
        try:
            import smarthome
            if hexc is None:
                smarthome.hue_light(None, None, False)
            else:
                smarthome.hue_light(None, None, True, None, hexc)
        except Exception:  # noqa: BLE001
            pass
    _bg(work)


def _poll_hue():
    """Hue-appen endret farge? Da får RGB-lysene i PC-en samme farge."""
    if not opt("sync_rgb_hue"):
        return True

    def work():
        try:
            import smarthome
            st = smarthome.hue_state()
            cols = [x["color"] for x in st.get("lights", []) if x.get("on") and x.get("color")]
            if not cols:
                return
            hexc = max(set(cols), key=cols.count)
            if hexc != _STATE["last_hex"]:
                _STATE["last_hex"] = hexc
                import automation
                automation.rgb_set(automation.hex_rgb(hexc), _from_sync=True)
        except Exception:  # noqa: BLE001
            pass
    _bg(work)
    return True


def start():
    if not __import__("funksjoner").on("smarthjem"):          # funksjonen er slått av
        return
    if _STATE["started"]:
        return
    _STATE["started"] = True
    if sys.platform != "win32":
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            bus.signal_subscribe("org.freedesktop.login1", "org.freedesktop.login1.Manager", "PrepareForSleep",
                                 "/org/freedesktop/login1", None, Gio.DBusSignalFlags.NONE, _on_prepare)
            bus.signal_subscribe("org.freedesktop.login1", "org.freedesktop.login1.Manager", "PrepareForShutdown",
                                 "/org/freedesktop/login1", None, Gio.DBusSignalFlags.NONE, _on_prepare)
            _STATE["bus"] = bus
            if opt("tv_off_sleep"):
                _sleep_inhibit(True)
        except Exception:  # noqa: BLE001
            pass
    GLib.timeout_add_seconds(10, _poll_hue)
