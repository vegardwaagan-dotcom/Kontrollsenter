"""Huset: oppdateringskveld (med Wake-on-LAN), strømsparing etter pris, strøm per PC, glemte PC-er og sovemodus.

Én PC er «husets sjef» (den du slår funksjonene på i). Den vekker, oppdaterer og legger de andre i dvale via
hjemmenettet (husnøkkelen), og sender rapport til mobilen.

  3  Oppdateringskveld   én natt i uka: vekk PC-ene (WoL) → «Oppdater alt» på alle → dvale igjen → rapport
  27 Strømsparing etter pris   dyr time og PC-en står ubrukt → Strømsparing; tilbake når prisen faller/du bruker den
  28 Strøm per PC        kWh og kroner denne måneden per PC (fra statusen PC-ene deler)
  29 Glemte PC-er        står en PC ubrukt om natten → spør på mobilen, eller legg den i dvale selv
  39 Sovemodus for huset ved leggetid: 10 min varsel, så dvale på alle PC-ene (valgfritt: vekk om morgenen)
"""
import json
import os
import socket
import sys
import threading
import time

IS_WIN = sys.platform == "win32"
CFG = os.path.expanduser("~/.config/systemmonitor/huset.json")
DEFAULTS = {
    "night_update": {"on": False, "weekday": 2, "at": "cheap", "wake": True, "sleep_after": True},
    "price_saver": {"on": False, "idle_min": 10},
    "forgotten": {"on": False, "mode": "ask", "idle_min": 30, "from": "23:00", "to": "06:00"},
    "house_sleep": {"on": False, "at": "23:30", "wake_at": "", "skip_gaming": False},
    "pilot": {"on": False, "pc": "", "hours": 24},
}
_STATE = {"woken": set(), "asked": {}, "saver": None, "idle_since": {}}


def cfg():
    try:
        d = json.load(open(CFG))
    except (OSError, ValueError):
        d = {}
    for k, v in DEFAULTS.items():
        d[k] = {**v, **(d.get(k) or {})}
    return d


def save_cfg(d):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    json.dump(d, open(CFG, "w"), ensure_ascii=False, indent=1)


def set_part(part, **kw):
    d = cfg()
    d[part].update(kw)
    save_cfg(d)


# --------------------------------------------------------------------------
# Wake-on-LAN, MAC og inaktiv tid (deles i statusen)
# --------------------------------------------------------------------------
def my_mac():
    """MAC-adressen til nettverkskortet med adressen på hjemmenettet (192.168.x / 10.x)."""
    try:
        import psutil
        link = getattr(psutil, "AF_LINK", None)
        for name, addrs in psutil.net_if_addrs().items():
            ips = [a.address for a in addrs if a.family == socket.AF_INET]
            if not any(ip.startswith(("192.168.", "10.", "172.")) and not ip.startswith("172.17.") for ip in ips):
                continue
            for a in addrs:
                if (a.family == link or a.family == getattr(socket, "AF_PACKET", -1)) and a.address and \
                        a.address.replace("-", ":").lower() != "00:00:00:00:00:00":
                    return a.address.replace("-", ":").lower()
    except Exception:  # noqa: BLE001
        pass
    return None


def wake(mac, ips=()):
    """Send Wake-on-LAN («magic packet») til en MAC-adresse."""
    hexs = mac.replace(":", "").replace("-", "")
    if len(hexs) != 12:
        raise ValueError("ugyldig MAC-adresse")
    pkt = b"\xff" * 6 + bytes.fromhex(hexs) * 16
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    targets = {"255.255.255.255"}
    for ip in ips or ():
        p = ip.split(".")
        if len(p) == 4:
            targets.add(".".join(p[:3] + ["255"]))
    for t in targets:
        for port in (9, 7):
            try:
                s.sendto(pkt, (t, port))
            except OSError:
                pass
    s.close()
    return True


def idle_seconds():
    """Sekunder siden noen brukte mus/tastatur (None = ukjent)."""
    if IS_WIN:
        try:
            import ctypes

            class LII(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
            li = LII()
            li.cbSize = ctypes.sizeof(LII)
            if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(li)):
                return (ctypes.windll.kernel32.GetTickCount() - li.dwTime) / 1000
        except Exception:  # noqa: BLE001
            pass
        return None
    try:                                                  # logind: skrivebordet setter «inaktiv» (skjermen dimmes)
        import subprocess
        sid = os.environ.get("XDG_SESSION_ID")
        if not sid:
            out = subprocess.run(["loginctl", "list-sessions", "--no-legend"], capture_output=True, text=True,
                                 timeout=5).stdout
            me = os.environ.get("USER", "")
            sid = next((ln.split()[0] for ln in out.splitlines() if len(ln.split()) > 2 and ln.split()[2] == me), None)
        if not sid:
            return None
        out = subprocess.run(["loginctl", "show-session", sid, "-p", "IdleHint", "-p", "IdleSinceHint"],
                             capture_output=True, text=True, timeout=5).stdout
        d = dict(ln.split("=", 1) for ln in out.splitlines() if "=" in ln)
        if d.get("IdleHint") == "yes" and d.get("IdleSinceHint", "0") != "0":
            return max(0.0, time.time() - int(d["IdleSinceHint"]) / 1e6)
        return 0.0 if d.get("IdleHint") == "no" else None
    except Exception:  # noqa: BLE001
        return None


def kwh_month():
    """kWh og kroner denne måneden for denne PC-en."""
    try:
        import power
        e = power.current()
        mon = time.strftime("%Y-%m")
        wh = sum(e._get(d)[0] for d in e.days if d.startswith(mon))
        price = power.load().get("price", 0)
        return round(wh / 1000, 1), round(wh / 1000 * price)
    except Exception:  # noqa: BLE001
        return None, None


def status_fields():
    """Legges i statusen PC-ene deler (homepcs)."""
    kwh, kr = kwh_month()
    return {"mac": my_mac(), "idle_s": idle_seconds(), "kwh_month": kwh, "kr_month": kr}


# --------------------------------------------------------------------------
# Hjelpere mot de andre PC-ene
# --------------------------------------------------------------------------
def _pcs(online_only=False):
    import homepcs
    import savegames
    me = savegames.pc_name()
    out = []
    for p in homepcs.fetch() or []:
        if p.get("name") == me:
            continue
        on = time.time() - (p.get("time") or 0) < homepcs.STALE
        if online_only and not on:
            continue
        out.append({**p, "_on": on})
    return out


def system(p, what):
    """Be en annen PC sove / slå seg av / starte på nytt (husnøkkel)."""
    import homepcs
    return homepcs.house_call(p, "system", 15, do=what)


def _notify(win, key, title, body):
    bg = getattr(win, "bg", None)
    if bg:
        from gi.repository import GLib
        GLib.idle_add(lambda: (bg.notify(key, title, body, force=True), False)[1])
    try:
        import remote_extra
        remote_extra.event("house", title, body, "info")
    except Exception:  # noqa: BLE001
        pass


def _hhmm(s):
    try:
        h, m = (int(x) for x in s.split(":"))
        return h * 60 + m
    except (ValueError, AttributeError):
        return None


def _in_window(start, end, now_min):
    a, b = _hhmm(start), _hhmm(end)
    if a is None or b is None:
        return False
    return a <= now_min < b if a < b else (now_min >= a or now_min < b)


# --------------------------------------------------------------------------
# 3 – oppdateringskveld
# --------------------------------------------------------------------------
def night_update_due(c, now=None):
    lt = time.localtime(now or time.time())
    if lt.tm_wday != c["weekday"]:
        return False
    if c["at"] == "cheap":
        try:
            import pricejobs
            h = pricejobs.night_hour()
        except Exception:  # noqa: BLE001
            h = 3
        return lt.tm_hour == h and lt.tm_min < 10
    m = _hhmm(c["at"])
    return m is not None and 0 <= lt.tm_hour * 60 + lt.tm_min - m < 10


def run_night_update(win, report=True):
    """Vekk, oppdater alt overalt, legg de vekte i dvale igjen, og send rapport."""
    import updates
    c = cfg()["night_update"]
    woken = []
    if c["wake"]:
        for p in _pcs():
            if not p["_on"] and p.get("mac"):
                try:
                    wake(p["mac"], p.get("ips"))
                    woken.append(p["name"])
                except Exception:  # noqa: BLE001
                    pass
        if woken:
            time.sleep(180)                              # la dem starte og få Kontrollsenter i gang
    results = []
    import homepcs
    for p in _pcs(online_only=True):
        ok, d = homepcs.house_call(p, "updateall", 20)
        results.append((p["name"], ok, d.get("msg", "startet") if ok else d))
    done = threading.Event()
    local = {}
    started = updates.update_all(win, include_pcs=False,
                                 on_done=lambda r: (local.update(r=r), done.set()))
    if started:
        done.wait(3600)
    time.sleep(600 if woken else 0)                     # gi de andre tid til å bli ferdige
    if c["sleep_after"]:
        for p in _pcs(online_only=True):
            if p["name"] in woken and not p.get("game"):
                system(p, "sleep")
    lines = [f"{'✓' if ok else '✗'} {n}: {m}" for n, ok, m in results]
    lr = local.get("r") or []
    bad = [x for x in lr if not x[1]]
    lines.insert(0, "Denne PC-en: " + ("alt oppdatert" if not bad else f"{len(bad)} feilet"))
    if woken:
        lines.append("Vekket: " + ", ".join(woken))
    body = "  ·  ".join(lines)
    if report:
        _notify(win, "updates", "Oppdateringskvelden er ferdig", body)
    return body


# --------------------------------------------------------------------------
# 27 – strømsparing når strømmen er dyr og PC-en står ubrukt
# --------------------------------------------------------------------------
def price_saver_tick(win):
    c = cfg()["price_saver"]
    if not c["on"]:
        if _STATE["saver"]:
            _restore_power(win)
        return
    try:
        import infotiles
        pr = infotiles.price()
    except Exception:  # noqa: BLE001
        return
    now, avg = pr.get("now"), pr.get("avg")
    if now is None or avg is None:
        return
    dear = now >= avg * 1.25
    game = getattr(getattr(win, "bg", None), "game_name", None)
    idle = idle_seconds()
    busy = game or (idle is not None and idle < c["idle_min"] * 60) or (getattr(win, "_cpu_load", 0) or 0) > 40
    prof = win.power.active_profile() if getattr(win, "power", None) else None
    if dear and not busy and not _STATE["saver"] and prof not in ("power-saver", None):
        _STATE["saver"] = prof
        _set_power(win, "power-saver")
        _notify(win, "price", "Strømmen er dyr nå", f"{now:.2f} kr/kWh – PC-en står ubrukt, så den går i "
                                                    "Strømsparing til prisen faller eller du bruker den.")
    elif _STATE["saver"] and (not dear or busy):
        _restore_power(win)


def _set_power(win, mode):
    try:
        import remote
        remote.do_action(win, {"a": "power", "mode": mode})
    except Exception:  # noqa: BLE001
        pass


def _restore_power(win):
    prev, _STATE["saver"] = _STATE["saver"], None
    if prev:
        _set_power(win, prev)


# --------------------------------------------------------------------------
# 29 – glemte PC-er om natten
# --------------------------------------------------------------------------
def forgotten_tick(win):
    c = cfg()["forgotten"]
    if not c["on"]:
        return
    lt = time.localtime()
    if not _in_window(c["from"], c["to"], lt.tm_hour * 60 + lt.tm_min):
        _STATE["idle_since"].clear()
        return
    for p in _pcs(online_only=True):
        name = p["name"]
        idle = p.get("idle_s")
        quiet = not p.get("game") and (p.get("cpu_l") or 0) < 15
        if idle is not None:
            quiet = quiet and idle >= c["idle_min"] * 60
        else:                                            # vet ikke: krev at den har vært rolig en stund
            since = _STATE["idle_since"].setdefault(name, time.time()) if quiet else None
            if not quiet:
                _STATE["idle_since"].pop(name, None)
            quiet = quiet and since is not None and time.time() - since >= c["idle_min"] * 60
        if not quiet or time.time() - _STATE["asked"].get(name, 0) < 3 * 3600:
            continue
        _STATE["asked"][name] = time.time()
        if c["mode"] == "auto":
            ok, _d = system(p, "sleep")
            _notify(win, "house", f"{name} er lagt i dvale", "Den sto på uten å brukes." if ok else
                    f"Fikk ikke lagt den i dvale: {_d}")
        else:
            _notify(win, "house", f"{name} står på uten å brukes",
                    "Legg den i dvale fra PC-er-siden eller mobilappen (PC-er → Sov).")


# --------------------------------------------------------------------------
# 39 – sovemodus for huset
# --------------------------------------------------------------------------
def house_sleep_tick(win):
    c = cfg()["house_sleep"]
    if not c["on"]:
        return
    lt = time.localtime()
    now = lt.tm_hour * 60 + lt.tm_min
    at = _hhmm(c["at"])
    day = time.strftime("%Y-%m-%d")
    if at is None:
        return
    if now == (at - 10) % 1440 and _STATE["asked"].get("sleepwarn") != day:
        _STATE["asked"]["sleepwarn"] = day
        try:
            import features
            import savegames
            for p in _pcs(online_only=True):
                features.send_to(p["name"], savegames.pc_name(), f"😴 Sovemodus om 10 minutter (kl. {c['at']}) – "
                                                                 "lagre spillet. PC-en går i dvale.")
        except Exception:  # noqa: BLE001
            pass
    if now == at and _STATE["asked"].get("sleep") != day:
        _STATE["asked"]["sleep"] = day
        names = []
        for p in _pcs(online_only=True):
            if c["skip_gaming"] and p.get("game"):
                continue
            ok, _d = system(p, "sleep")
            if ok:
                names.append(p["name"])
        _notify(win, "house", "Sovemodus for huset", ("I dvale: " + ", ".join(names)) if names else
                "Ingen andre PC-er var på")
    wake_at = _hhmm(c.get("wake_at") or "")
    if wake_at is not None and now == wake_at and _STATE["asked"].get("wake") != day:
        _STATE["asked"]["wake"] = day
        for p in _pcs():
            if not p["_on"] and p.get("mac"):
                try:
                    wake(p["mac"], p.get("ips"))
                except Exception:  # noqa: BLE001
                    pass


def tick(win):
    """Fra bakgrunnen hvert minutt (i en tråd)."""
    c = cfg()
    if c["night_update"]["on"] and night_update_due(c["night_update"]):
        key = time.strftime("%Y-%m-%d")
        if _STATE["asked"].get("nightupd") != key:
            _STATE["asked"]["nightupd"] = key
            threading.Thread(target=run_night_update, args=(win,), daemon=True, name="oppdateringskveld").start()
    for fn in (price_saver_tick, forgotten_tick, house_sleep_tick):
        try:
            fn(win)
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("huset: %s", fn.__name__)


def power_by_pc():
    """[(navn, kWh, kr)] denne måneden for alle PC-ene (28)."""
    import savegames
    rows = []
    kwh, kr = kwh_month()
    if kwh is not None:
        rows.append((savegames.pc_name() + " (denne)", kwh, kr))
    for p in _pcs():
        if p.get("kwh_month") is not None:
            rows.append((p["name"], p["kwh_month"], p.get("kr_month") or 0))
    rows.sort(key=lambda r: -r[1])
    return rows
