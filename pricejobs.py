"""Strømpris-smart: tunge jobber (sikkerhetskopi til NAS) og scener med «Når strømmen er billigst» kjøres i den
billigste timen om natten (22–07), ut fra spotprisen for prisområdet ditt. Uten pris brukes kl. 03.
"""
import json
import threading
import time
import urllib.request
from datetime import date, datetime, timedelta

_DONE = {}


def cheapest_night_hour():
    """Starttimen (0–23) for den billigste timen mellom 22 og 07 i natt."""
    try:
        import infotiles
        area = infotiles.cfg().get("area", "NO1")
        rows = []
        for d in (date.today(), date.today() + timedelta(days=1)):
            url = f"https://www.hvakosterstrommen.no/api/v1/prices/{d:%Y}/{d:%m-%d}_{area}.json"
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Kontrollsenter"}),
                                            timeout=8) as r:
                    rows += json.loads(r.read())
            except Exception:  # noqa: BLE001
                continue
        now = datetime.now().astimezone()
        start = now.replace(hour=22, minute=0, second=0, microsecond=0)
        if now.hour < 7:
            start -= timedelta(days=1)
        end = start + timedelta(hours=9)
        night = [(datetime.fromisoformat(p["time_start"]).astimezone(), p["NOK_per_kWh"]) for p in rows]
        night = [(t, v) for t, v in night if start <= t < end]
        if night:
            return min(night, key=lambda x: x[1])[0].hour
    except Exception:  # noqa: BLE001
        pass
    return 3


_HOUR = {"day": None, "h": 3}


def night_hour():
    key = time.strftime("%Y-%m-%d") + ("a" if time.localtime().tm_hour < 12 else "b")
    if _HOUR["day"] != key:
        _HOUR["day"] = key
        _HOUR["h"] = cheapest_night_hour()
    return _HOUR["h"]


def tick(win, notify=None):
    """Kalles jevnlig. I den billigste timen: sikkerhetskopi (hvis det er en uke siden) og «billig strøm»-scener."""
    lt = time.localtime()
    if lt.tm_min > 50:
        return
    tag = time.strftime("%Y-%m-%d")
    if _DONE.get("checked") == (tag, lt.tm_hour):
        return
    _DONE["checked"] = (tag, lt.tm_hour)

    def work():
        h = night_hour()
        if lt.tm_hour != h or _DONE.get("ran") == tag:
            return
        _DONE["ran"] = tag
        try:
            from gi.repository import GLib
            import scenes
            GLib.idle_add(lambda: (scenes.on_event(win, "cheap_power", f"kl. {h:02d}"), False)[1])
        except Exception:  # noqa: BLE001
            pass
        try:
            import pctools
            if pctools.backup_due():
                r = pctools.backup_run()
                if notify and r["sent"]:
                    notify("cleanup", "Sikkerhetskopi til NAS-en ✓",
                           f"{r['sent']} nye filer kopiert i den billigste strømtimen (kl. {h:02d}).")
        except Exception:  # noqa: BLE001
            pass
    threading.Thread(target=work, daemon=True).start()
