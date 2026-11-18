"""Ekstra funksjoner for Android-appen (og PC-en): hendelser/varsler, spilltid med grenser, kamp- og
WoW-historikk, strømkostnad, planlagt avslåing, nettverk, programmer, media, volum per program, lenker og
utklippstavle, skjermbilde, NAS/backup, helsekort, spillmodus og Wake-on-LAN.
"""
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time

from gi.repository import GLib

IS_WIN = sys.platform == "win32"
DATA = os.path.expanduser("~/.local/share/systemmonitor")
EVENTS = os.path.join(DATA, "hendelser.jsonl")
PLAYTIME = os.path.join(DATA, "spilltid.json")
LIMITS = os.path.expanduser("~/.config/systemmonitor/spillgrenser.json")
CS2_MATCHES = os.path.join(DATA, "cs2-kamper.json")
WOW_HIST = os.path.join(DATA, "wow-historikk.json")
WOW_GOALS = os.path.expanduser("~/.config/systemmonitor/wow-mal.json")
_LOCK = threading.RLock()                  # RLock: record_wow kaller event() mens låsen holdes


def _jload(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _jsave(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


# --------------------------------------------------------------------------
# 21 / 1 – hendelser (tidslinje + varsler til appen)
# --------------------------------------------------------------------------
def event(kind, title, body="", level="info"):
    """Legg til en hendelse. level: info | warn | error | game."""
    e = {"t": time.time(), "kind": kind, "title": title, "body": body, "level": level}
    with _LOCK:
        try:
            os.makedirs(DATA, exist_ok=True)
            with open(EVENTS, "a", encoding="utf-8") as f:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
            if os.path.getsize(EVENTS) > 600_000:          # hold fila liten: behold de siste 2000
                lines = open(EVENTS, encoding="utf-8").read().splitlines()[-2000:]
                open(EVENTS, "w", encoding="utf-8").write("\n".join(lines) + "\n")
        except OSError:
            pass
    return e


def events(since=0, limit=300):
    out = []
    try:
        with open(EVENTS, encoding="utf-8") as f:
            for ln in f:
                try:
                    e = json.loads(ln)
                except ValueError:
                    continue
                if e.get("t", 0) > since:
                    out.append(e)
    except OSError:
        pass
    return out[-limit:]


# --------------------------------------------------------------------------
# 7 – spilltid per dag, med grenser
# --------------------------------------------------------------------------
class PlayTracker:
    def __init__(self, notify):
        self.notify = notify
        self.data = _jload(PLAYTIME, {})
        self.saved = time.time()
        self.warned = {}

    def tick(self, game, dt):
        if not game:
            return
        day = time.strftime("%Y-%m-%d")
        d = self.data.setdefault(day, {})
        d[game] = d.get(game, 0) + dt
        if time.time() - self.saved > 60:
            self.save()
        lim = limit_today()
        if lim:
            total = sum(d.values())
            if total >= lim * 3600 and self.warned.get(day) != "over":
                self.warned[day] = "over"
                txt = f"Spilletiden i dag er {total / 3600:.1f} t – grensen er {lim:g} t"
                event("playtime", "Spilletid nådd", txt, "warn")
                self.notify("playlimit", "Spilletid nådd", txt, force=True)
                _ingame("Spilletiden for i dag er brukt opp")
            elif total >= lim * 3600 - 300 and self.warned.get(day) in (None, "soon"):
                self.warned[day] = "5min"
                self.notify("playlimit", "5 minutter spilletid igjen", "Lagre spillet nå", force=True)
                _ingame("5 minutter igjen – lagre spillet", 40)
            elif total >= lim * 3600 - 900 and not self.warned.get(day):
                self.warned[day] = "soon"
                event("playtime", "15 minutter igjen", f"Grensen for spilletid i dag er {lim:g} t", "info")
                self.notify("playlimit", "15 minutter spilletid igjen", f"Grensen i dag er {lim:g} t", force=True)
                _ingame("15 minutter spilletid igjen")

    def save(self):
        self.saved = time.time()
        keep = sorted(self.data)[-120:]
        self.data = {k: self.data[k] for k in keep}
        _jsave(PLAYTIME, self.data)


def _ingame(text, secs=25):
    try:
        import familysafe
        familysafe.ingame(text, secs)
    except Exception:  # noqa: BLE001
        pass


def limit_cfg():
    return {"enabled": False, "weekday": 2.0, "weekend": 4.0, **_jload(LIMITS, {})}


def limit_today():
    c = limit_cfg()
    if not c["enabled"]:
        return None
    base = c["weekend"] if time.localtime().tm_wday >= 5 else c["weekday"]
    try:
        import features
        return base + features.bonus_today() / 60
    except Exception:  # noqa: BLE001
        return base


def playtime_summary(days=14):
    data = _jload(PLAYTIME, {})
    out = []
    for i in range(days - 1, -1, -1):
        day = time.strftime("%Y-%m-%d", time.localtime(time.time() - i * 86400))
        games = data.get(day, {})
        out.append({"day": day, "total": round(sum(games.values())), "games": {k: round(v) for k, v in games.items()}})
    week = {}
    for d in out[-7:]:
        for g, s in d["games"].items():
            week[g] = week.get(g, 0) + s
    return {"days": out, "week": sorted(week.items(), key=lambda x: -x[1]), "limits": limit_cfg(),
            "today_limit": limit_today()}


# --------------------------------------------------------------------------
# 6 / 18 – CS2-kamper (lagres når kampen er over) og WoW-historikk / mål (17)
# --------------------------------------------------------------------------
def record_cs2_match(st):
    """st = gamestats.LIVE.state() ved gameover."""
    if not st or not st.get("mine") or st.get("kills") is None:
        return
    with _LOCK:
        ms = _jload(CS2_MATCHES, [])
        key = (st.get("map"), st.get("kills"), st.get("deaths"), st.get("ct"), st.get("t"))
        if ms and tuple(ms[-1].get("key", [])) == key and time.time() - ms[-1]["t"] < 600:
            return
        team = (st.get("team") or "").upper()
        mine, theirs = (st.get("ct"), st.get("t")) if team == "CT" else (st.get("t"), st.get("ct"))
        res = "win" if (mine or 0) > (theirs or 0) else "loss" if (mine or 0) < (theirs or 0) else "draw"
        k, d = st.get("kills") or 0, st.get("deaths") or 0
        ms.append({"t": time.time(), "key": list(key), "map": st.get("map"), "mode": st.get("mode"), "kills": k,
                   "deaths": d, "assists": st.get("assists"), "mvps": st.get("mvps"), "hs": st.get("hs"),
                   "dmg": st.get("dmg"), "adr": st.get("adr"), "score": f"{mine}-{theirs}", "result": res})
        _jsave(CS2_MATCHES, ms[-500:])
    event("cs2", f"CS2: {'seier' if res == 'win' else 'tap' if res == 'loss' else 'uavgjort'} på {st.get('map')}",
          f"{k} kills · {d} dødsfall · {st.get('hs_pct') or '–'} headshot · {st.get('dmg') or 0} skade", "game")


def cs2_history():
    ms = _jload(CS2_MATCHES, [])
    maps = {}
    for m in ms:
        e = maps.setdefault(m.get("map") or "?", {"played": 0, "won": 0, "kills": 0, "deaths": 0})
        e["played"] += 1
        e["won"] += m.get("result") == "win"
        e["kills"] += m.get("kills") or 0
        e["deaths"] += m.get("deaths") or 0
    per_map = [{"map": k, **v, "kd": round(v["kills"] / v["deaths"], 2) if v["deaths"] else None,
                "winrate": round(100 * v["won"] / v["played"]) if v["played"] else None} for k, v in maps.items()]
    return {"matches": ms[-100:], "maps": sorted(per_map, key=lambda x: -x["played"])}


def record_wow(chars):
    """Kalles når WoW-data er lest: lagrer (tid, spilt, level) per karakter når noe er endret."""
    with _LOCK:
        h = _jload(WOW_HIST, {})
        changed = False
        for c in chars:
            key = f"{c.get('realm')}-{c.get('name')}"
            pts = h.setdefault(key, [])
            p = [round(c.get("last_seen") or time.time()), int(c.get("played") or 0), int(c.get("level") or 0)]
            if not pts or pts[-1][1:] != p[1:]:
                pts.append(p)
                h[key] = pts[-400:]
                changed = True
                if len(pts) > 1 and p[2] > pts[-2][2]:
                    event("wow", f"WoW: {c.get('name')} nådde level {p[2]}", c.get("realm") or "", "game")
        if changed:
            _jsave(WOW_HIST, h)


def wow_goals():
    return _jload(WOW_GOALS, {})


def wow_goal_progress(c):
    """Fremdrift mot målet for én karakter (eller None)."""
    key = f"{c.get('realm')}-{c.get('name')}"
    g = wow_goals().get(key)
    if not g:
        return None
    lt = [v for v in (c.get("level_time") or {}).values() if isinstance(v, (int, float)) and v > 0]
    avg = sum(lt[-5:]) / len(lt[-5:]) if lt else None
    left = max(0, int(g["level"]) - int(c.get("level") or 0))
    need = None
    if avg is not None and left:
        need = max(0, left * avg - (c.get("played_level") or 0))
    days = max(0.0, (g.get("by", 0) - time.time()) / 86400) if g.get("by") else None
    return {"key": key, "target": g["level"], "by": g.get("by"), "levels_left": left, "avg_level_s": avg,
            "est_play_s": need, "days_left": days,
            "per_day_s": (need / days) if need is not None and days else None}


def set_wow_goal(key, level, by):
    g = wow_goals()
    if level is None:
        g.pop(key, None)
    else:
        g[key] = {"level": int(level), "by": float(by) if by else None}
    _jsave(WOW_GOALS, g)


# --------------------------------------------------------------------------
# 19 – strømkostnad
# --------------------------------------------------------------------------
def energy(win):
    import power
    price = power.load()["price"]
    log = getattr(win, "energy", None)
    days = []
    for k in sorted((log.days if log else {}))[-31:]:
        wh = log._get(k)[0]
        days.append({"day": k, "kwh": round(wh / 1000, 2), "kr": round(wh / 1000 * price, 2)})
    week = sum(d["kr"] for d in days[-7:])
    month = sum(d["kr"] for d in days if d["day"][:7] == time.strftime("%Y-%m"))
    return {"price": price, "days": days, "today_kr": days[-1]["kr"] if days else 0, "week_kr": round(week, 2),
            "month_kr": round(month, 2), "month_estimate_kwh": log.month_estimate_kwh() if log else None}


# --------------------------------------------------------------------------
# 20 – slå av om X minutter / når nedlastingene er ferdige
# --------------------------------------------------------------------------
class ShutdownTimer:
    def __init__(self, win):
        self.win = win
        self.at = None            # tidspunkt (epoch) for «om X min»
        self.when_idle = False    # «når nedlastingene er ferdige»
        self.quiet_since = None
        GLib.timeout_add_seconds(15, self._tick)

    def state(self):
        return {"at": self.at, "when_idle": self.when_idle,
                "idle_for": round(time.time() - self.quiet_since) if self.quiet_since else 0}

    def set(self, minutes=None, when_idle=False):
        self.at = time.time() + minutes * 60 if minutes else None
        self.when_idle = bool(when_idle)
        self.quiet_since = None
        if self.at:
            event("timer", f"PC-en slås av kl. {time.strftime('%H:%M', time.localtime(self.at))}", "", "info")
        elif self.when_idle:
            event("timer", "PC-en slås av når nedlastingene er ferdige", "Når nettet har vært stille i 5 min", "info")
        else:
            event("timer", "Planlagt avslåing er avbrutt", "", "info")

    def _tick(self):
        now = time.time()
        if self.when_idle:
            rx = ((getattr(self.win, "_remote", {}) or {}).get("net") or [0, 0])[0] or 0
            if rx > 150 * 1024:
                self.quiet_since = None
            elif self.quiet_since is None:
                self.quiet_since = now
            elif now - self.quiet_since > 300:
                self._go("Nedlastingene er ferdige")
        if self.at and now >= self.at:
            self._go("Planlagt avslåing")
        return True

    def _go(self, why):
        self.at, self.when_idle = None, False
        event("timer", f"{why} – PC-en slås av", "", "warn")
        import remote
        remote._system("shutdown")


# --------------------------------------------------------------------------
# 16 – nettverk
# --------------------------------------------------------------------------
def network():
    import netpage
    gw = netpage.gateway()
    targets = [("Ruter", gw), ("NAS", "192.168.1.3"), ("Internett (Cloudflare)", "1.1.1.1"),
               ("Steam", "steamcommunity.com"), ("Battle.net", "eu.battle.net")]
    res = {}

    def one(name, host):
        if host:
            avg, loss = netpage.ping(host, 3)
            res[name] = {"host": host, "ms": round(avg, 1) if avg is not None else None, "loss": loss}
    th = [threading.Thread(target=one, args=t, daemon=True) for t in targets]
    for t in th:
        t.start()
    for t in th:
        t.join(20)
    conns = []
    try:
        conns = [{"name": n, "count": c, "targets": p} for n, c, p in netpage.connections()[:12]]
    except Exception:  # noqa: BLE001
        pass
    return {"ping": [{"name": n, **res[n]} for n, _h in targets if n in res], "programs": conns}


# --------------------------------------------------------------------------
# 11 – programmer (bare dine egne) og avslutt
# --------------------------------------------------------------------------
PROTECT = {"systemd", "kwin_wayland", "plasmashell", "gnome-shell", "Xwayland", "pipewire", "wireplumber",
           "explorer.exe", "dwm.exe", "csrss.exe", "winlogon.exe", "svchost.exe", "sddm", "gdm"}


def processes():
    import psutil
    me = psutil.Process().username()
    procs = []
    for p in psutil.process_iter(["pid", "name", "username", "memory_info", "cpu_percent"]):
        try:
            if p.info["username"] != me or p.pid == os.getpid():
                continue
            procs.append(p)
        except (psutil.Error, KeyError):
            continue
    time.sleep(0.6)                                   # cpu_percent trenger to målinger
    out = []
    for p in procs:
        try:
            out.append({"pid": p.pid, "name": p.name(), "cpu": round(p.cpu_percent() / (psutil.cpu_count() or 1), 1),
                        "mem": p.memory_info().rss})
        except psutil.Error:
            continue
    # slå sammen prosesser med samme navn (nettlesere har mange)
    merged = {}
    for x in out:
        m = merged.setdefault(x["name"], {"name": x["name"], "pids": [], "cpu": 0, "mem": 0})
        m["pids"].append(x["pid"])
        m["cpu"] += x["cpu"]
        m["mem"] += x["mem"]
    lst = sorted(merged.values(), key=lambda m: (-m["cpu"], -m["mem"]))[:12]
    for m in lst:
        m["cpu"] = round(m["cpu"], 1)
        m["protected"] = m["name"] in PROTECT
    return lst


def kill(name):
    import psutil
    if name in PROTECT:
        raise ValueError("dette programmet kan ikke avsluttes herfra")
    me = psutil.Process().username()
    n = 0
    for p in psutil.process_iter(["name", "username"]):
        try:
            if p.info["name"] == name and p.info["username"] == me and p.pid != os.getpid():
                p.terminate()
                n += 1
        except psutil.Error:
            continue
    if not n:
        raise ValueError("fant ikke programmet")

    def hard():
        time.sleep(4)
        for p in psutil.process_iter(["name", "username"]):
            try:
                if p.info["name"] == name and p.info["username"] == me:
                    p.kill()
            except psutil.Error:
                continue
    threading.Thread(target=hard, daemon=True).start()
    event("process", f"Avsluttet {name}", f"{n} prosess(er) fra appen", "info")
    return n


# --------------------------------------------------------------------------
# 9 – media (MPRIS på Linux, medietaster på Windows) og volum per program
# --------------------------------------------------------------------------
def media_state():
    if IS_WIN:
        return {"players": [], "keys": True}
    from gi.repository import Gio
    out = []
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        names = bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "ListNames",
                              None, None, 0, 2000, None).unpack()[0]
        for n in names:
            if not n.startswith("org.mpris.MediaPlayer2."):
                continue
            try:
                props = bus.call_sync(n, "/org/mpris/MediaPlayer2", "org.freedesktop.DBus.Properties", "GetAll",
                                      GLib.Variant("(s)", ("org.mpris.MediaPlayer2.Player",)), None, 0, 1500,
                                      None).unpack()[0]
                md = props.get("Metadata") or {}
                out.append({"id": n, "app": n.split(".")[3] if n.count(".") >= 3 else n,
                            "status": props.get("PlaybackStatus"), "title": md.get("xesam:title") or "",
                            "artist": ", ".join(md.get("xesam:artist") or [])})
            except GLib.Error:
                continue
    except GLib.Error:
        pass
    return {"players": out, "keys": False}


def media_cmd(cmd, player=None):
    if cmd not in ("PlayPause", "Next", "Previous", "Stop"):
        raise ValueError("ukjent mediekommando")
    if IS_WIN:
        import ctypes
        vk = {"PlayPause": 0xB3, "Next": 0xB0, "Previous": 0xB1, "Stop": 0xB2}[cmd]
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
        return
    from gi.repository import Gio
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    players = [p["id"] for p in media_state()["players"]]
    target = player if player in players else next(
        (p["id"] for p in media_state()["players"] if p["status"] == "Playing"), players[0] if players else None)
    if not target:
        raise ValueError("ingen mediespiller kjører")
    bus.call_sync(target, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player", cmd, None, None, 0, 2000, None)


def app_volumes():
    if IS_WIN:
        import winaudio
        out = []
        for name, _v, pct, mute in winaudio.sessions():
            out.append({"id": name, "name": name, "volume": pct, "mute": mute})
        return out
    import audio
    out = []
    for s in audio.pjson("sink-inputs"):
        p = s.get("properties", {})
        out.append({"id": str(s.get("index")), "name": p.get("application.name") or p.get("media.name") or "?",
                    "volume": audio.vol_pct(s), "mute": bool(s.get("mute"))})
    return out


def set_app_volume(sid, vol=None, mute=None):
    if vol is not None and not (isinstance(vol, int) and 0 <= vol <= 150):
        raise ValueError("ugyldig volum")
    if IS_WIN:
        import winaudio
        for name, v, _pct, _m in winaudio.sessions():
            if name == sid:
                winaudio.session_set(v, vol, mute)
        return
    import audio
    if not str(sid).isdigit():
        raise ValueError("ugyldig program")
    if vol is not None:
        audio.pactl("set-sink-input-volume", str(sid), f"{vol}%")
    if mute is not None:
        audio.pactl("set-sink-input-mute", str(sid), "1" if mute else "0")


# --------------------------------------------------------------------------
# 10 – lenker og utklippstavle
# --------------------------------------------------------------------------
def open_url(url):
    if not re.match(r"^https?://\S+$", url or "") or len(url) > 2000:
        raise ValueError("bare http- og https-lenker kan åpnes")
    if IS_WIN:
        os.startfile(url)
    else:
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    event("link", "Lenke åpnet fra appen", url[:120], "info")


def set_clipboard(text):
    from gi.repository import Gdk
    Gdk.Display.get_default().get_clipboard().set(str(text)[:100000])


def get_clipboard(call_main):
    from gi.repository import Gdk
    box, ev = {}, threading.Event()

    def start():
        cb = Gdk.Display.get_default().get_clipboard()

        def done(c, res):
            try:
                box["v"] = c.read_text_finish(res)
            except GLib.Error as e:
                box["e"] = str(e)
            ev.set()
        cb.read_text_async(None, done)
    call_main(start)
    ev.wait(3)
    return box.get("v") or ""


# --------------------------------------------------------------------------
# 8 – skjermbilde
# --------------------------------------------------------------------------
def screenshot():
    """JPEG (bytes) av skjermen, skalert til høyst 1920 piksler bredt."""
    import shutil
    import tempfile
    if IS_WIN:                                       # Windows' egen skjermkopi (GDI) – raskt, uten PowerShell
        import wincapture
        return wincapture.jpeg(1920, 80)
    d = tempfile.mkdtemp()
    png = os.path.join(d, "skjerm.png")
    try:
        if IS_WIN:
            ps = ("Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
                  "$b=[System.Windows.Forms.SystemInformation]::VirtualScreen;"
                  "$i=New-Object System.Drawing.Bitmap $b.Width,$b.Height;"
                  "$g=[System.Drawing.Graphics]::FromImage($i);$g.CopyFromScreen($b.Left,$b.Top,0,0,$i.Size);"
                  f"$i.Save('{png}')")
            import winsupport as WS
            WS.run(["powershell", "-NoProfile", "-Command", ps], 30)
        else:
            for cmd in (["spectacle", "-b", "-n", "-f", "-o", png], ["grim", png], ["gnome-screenshot", "-f", png]):
                if shutil.which(cmd[0]):
                    subprocess.run(cmd, capture_output=True, timeout=20)
                    if os.path.exists(png):
                        break
        if not os.path.exists(png):
            raise RuntimeError("fant ikke et verktøy for skjermbilde")
        import gi
        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import GdkPixbuf
        pb = GdkPixbuf.Pixbuf.new_from_file(png)
        w, h = pb.get_width(), pb.get_height()
        if w > 1920:
            pb = pb.scale_simple(1920, int(h * 1920 / w), GdkPixbuf.InterpType.BILINEAR)
        ok, data = pb.save_to_bufferv("jpeg", ["quality"], ["80"])
        return bytes(data)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --------------------------------------------------------------------------
# 12 – NAS og sikkerhetskopi av lagrede spill
# --------------------------------------------------------------------------
def nas_state():
    out = {"online": False}
    try:
        import lanupdate as L
        out["online"] = L.on_lan()
        out["where"] = L.location()
        if out["online"]:
            if IS_WIN:
                import shutil
                for p in (r"\\PERSONALCLOUD\Public", r"\\192.168.1.3\Public"):
                    try:
                        du = shutil.disk_usage(p)
                        out["total"], out["free"] = du.total, du.free
                        break
                    except OSError:
                        continue
            else:
                txt = L._smb("du", 60)
                m = re.search(r"(\d+) blocks of size (\d+)\. (\d+) blocks available", txt)
                if m:
                    blocks, size, free = map(int, m.groups())
                    out["total"], out["free"] = blocks * size, free * size
    except Exception as e:  # noqa: BLE001
        out["error"] = str(e)
    try:
        import savegames
        out["backup_last"] = savegames.load_cfg().get("last")
        out["backup_auto"] = savegames.load_cfg().get("auto")
    except Exception:  # noqa: BLE001
        pass
    return out


def backup_now():
    import savegames

    def done(*_a):
        event("backup", "Lagrede spill er sikkerhetskopiert til NAS-en", "", "info")
    savegames.backup_async(done=done)


# --------------------------------------------------------------------------
# 22 – helsekort (karakter A–F)
# --------------------------------------------------------------------------
_HEALTH = {"t": 0, "v": None}


def health(force=False):
    if not force and time.time() - _HEALTH["t"] < 600 and _HEALTH["v"]:
        return _HEALTH["v"]
    items = []
    try:
        if IS_WIN:
            import wintools
            for title, level, detail, _fix in wintools.WinSysCheckDialog.checks():
                items.append({"title": title, "level": level, "detail": detail})
        else:
            import syscheck
            for r in syscheck.run_all():
                items.append({"title": r.title, "level": r.level, "detail": r.detail})
    except Exception as e:  # noqa: BLE001
        items.append({"title": "Systemsjekk", "level": "warn", "detail": str(e)})
    pts = sum(2 if i["level"] == "error" else 1 if i["level"] == "warn" else 0 for i in items)
    grade = "A" if pts == 0 else "B" if pts <= 1 else "C" if pts <= 3 else "D" if pts <= 5 else "E" if pts <= 8 else "F"
    _HEALTH["t"], _HEALTH["v"] = time.time(), {"grade": grade, "items": items, "t": time.time()}
    return _HEALTH["v"]


# --------------------------------------------------------------------------
# 14 – spillmodus (én knapp) og tilbake
# --------------------------------------------------------------------------
class GameMode:
    def __init__(self, win):
        self.win = win
        self.snap = None
        self.rgb = False

    @property
    def on(self):
        return self.snap is not None

    def set(self, on, color=None):
        import automation
        w = self.win
        bg = getattr(w, "bg", None)
        if on and not self.snap:
            self.snap = automation.snapshot(w)
            self.snap["overlay"] = w.ov_button.get_active() if getattr(w, "ov_button", None) else None
            self.snap["notify"] = bg.cfg.get("notify") if bg else None
            fans = "curve" if getattr(w, "fans", None) and w.fans.rows else "keep"
            self.rgb = bool(color)
            automation.apply(w, power="performance", fans=fans, rgb="color" if color else "keep", color=color)
            if getattr(w, "ov_button", None) and w.ov_button.get_visible():
                w.ov_button.set_active(True)
            if bg:
                bg.cfg["notify"] = False
            event("gamemode", "Spillmodus på", "Max ytelse, viftekurve, overlay på og varsler av", "info")
        elif not on and self.snap:
            automation.restore(w, self.snap, self.rgb)
            if self.snap.get("overlay") is not None and getattr(w, "ov_button", None):
                w.ov_button.set_active(self.snap["overlay"])
            if bg and self.snap.get("notify") is not None:
                bg.cfg["notify"] = self.snap["notify"]
            self.snap = None
            event("gamemode", "Spillmodus av", "Alt er satt tilbake", "info")


# --------------------------------------------------------------------------
# 2 – Wake-on-LAN
# --------------------------------------------------------------------------
def lan_mac():
    """MAC-adressen til nettverkskortet som har hjemmenett-adressen."""
    try:
        import psutil
        import remote
        ips = set(remote.local_ips())
        for name, addrs in psutil.net_if_addrs().items():
            if any(a.family == socket.AF_INET and a.address in ips for a in addrs):
                for a in addrs:
                    if a.family == getattr(psutil, "AF_LINK", -1) and re.fullmatch(r"([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}",
                                                                                   a.address or ""):
                        return a.address.replace("-", ":").lower(), name
    except Exception:  # noqa: BLE001
        pass
    return None, None


def send_wol(mac):
    m = re.fullmatch(r"([0-9A-Fa-f]{2})[:-]?([0-9A-Fa-f]{2})[:-]?([0-9A-Fa-f]{2})[:-]?([0-9A-Fa-f]{2})[:-]?"
                     r"([0-9A-Fa-f]{2})[:-]?([0-9A-Fa-f]{2})", mac or "")
    if not m:
        raise ValueError("ugyldig MAC-adresse")
    pkt = b"\xff" * 6 + bytes(int(x, 16) for x in m.groups()) * 16
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        import remote
        targets = {"255.255.255.255"} | {ip.rsplit(".", 1)[0] + ".255" for ip in remote.local_ips()}
        for t in targets:
            for port in (9, 7):
                s.sendto(pkt, (t, port))
    finally:
        s.close()
    event("wol", "Wake-on-LAN sendt", mac, "info")


def wol_status():
    """Linux: er Wake-on-LAN slått på for nettverkstilkoblingen (NetworkManager)?"""
    mac, iface = lan_mac()
    out = {"mac": mac, "iface": iface, "enabled": None, "conn": None}
    if IS_WIN or not iface:
        return out
    try:
        r = subprocess.run(["nmcli", "-t", "-f", "NAME,DEVICE", "connection", "show", "--active"],
                           capture_output=True, text=True, timeout=10)
        conn = next((ln.rsplit(":", 1)[0] for ln in r.stdout.splitlines() if ln.endswith(":" + iface)), None)
        out["conn"] = conn
        if conn:
            r = subprocess.run(["nmcli", "-g", "802-3-ethernet.wake-on-lan", "connection", "show", conn],
                               capture_output=True, text=True, timeout=10)
            out["enabled"] = "magic" in r.stdout
    except (OSError, subprocess.SubprocessError):
        pass
    return out


def enable_wol():
    st = wol_status()
    if IS_WIN or not st["conn"]:
        raise RuntimeError("slå på Wake-on-LAN i nettverkskortets innstillinger og i BIOS")
    r = subprocess.run(["pkexec", "nmcli", "connection", "modify", st["conn"], "802-3-ethernet.wake-on-lan", "magic"],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "avbrutt")
    event("wol", "Wake-on-LAN er slått på", st["conn"], "info")
