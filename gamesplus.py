"""Spill+ (runde 4).

  10 Spillkveld: hvem i huset og blant vennene spiller hva – «Spill sammen» starter samme spill, inviterer PC-ene
     hjemme og blir med i Discord-kanalen for spillet
  15 Delte spillprofiler (Steam-startvalg + Proton) via NAS-en
  21 FPS-sammenligning etter økta: «5 % dårligere enn snittet – ny driver siden sist?»
  42 Ping-vakt mens du spiller: sier fra når pingen blir dårlig, og om det er Wi-Fi/ruteren eller internett
  44 Discord-kanal per spill: blir med i riktig talekanal når spillet starter
  49 Lysshow ved høydepunkter (RGB + Hue blinker ved ace/bosskill)
  50 Lydprofil per spill (byttes når spillet starter, tilbake etterpå)
  51 Retrospill: RetroArch-spillelistene vises sammen med de andre spillene
  52 Forutsi spillkvelden: «Du pleier å spille nå» – gjør klart (strømmodus, Steam og Discord)
  53 Smart oppstart: lærer hvilke programmer du alltid åpner, og kan starte dem selv
  54 Ikke forstyrr: varsler holdes tilbake også under møter (Teams, Zoom, Webex …)
  69 Spill-dagbok: første gang, lengste økt, timer-milepæler
  71 Husets toppliste (mest spilt denne uka)
  40 Finn beste FPS-grense (Linux, MangoHud – du trykker selv mens spillet kjører)
  22 Forvarm shadere (starter spillet en kort stund når du ber om det)
"""
import glob
import json
import os
import socket
import subprocess
import sys
import threading
import time

IS_WIN = sys.platform == "win32"
HOME = os.path.expanduser("~")
CFG = os.path.expanduser("~/.config/systemmonitor/spill-pluss.json")
DEF = {"discord_map": {}, "audio_map": {}, "ping_watch": True, "lightshow": True, "predict": True, "predict_prep": False,
       "smart_start": False, "seen_start": [], "dnd_meetings": True}
_STATE = {"ping": {}, "prev_audio": None, "predicted": None, "boot_seen": False}


def cfg():
    try:
        d = json.load(open(CFG))
    except (OSError, ValueError):
        d = {}
    return {**DEF, **d}


def set_(**kw):
    d = cfg()
    d.update(kw)
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    json.dump(d, open(CFG, "w"), ensure_ascii=False, indent=1)
    return d


def _ingame(text, secs=25):
    try:
        import familysafe
        familysafe.ingame(text, secs)
    except Exception:  # noqa: BLE001
        pass


def _notify(win, key, title, body, action=None):
    bg = getattr(win, "bg", None)
    if bg:
        from gi.repository import GLib
        GLib.idle_add(lambda: (bg.notify(key, title, body, force=True, action=action or "app.show"), False)[1])


# --------------------------------------------------------------------------
# 21 – FPS-sammenligning
# --------------------------------------------------------------------------
def fps_compare(s):
    """Tekst som sammenligner økta med snittet av de 5 forrige i samme spill (eller "")."""
    try:
        import games_auto
        prev = [x for x in games_auto.load_sessions() if x.get("name") == s.get("name")
                and x.get("start") != s.get("start") and x.get("fps")][-5:]
    except Exception:  # noqa: BLE001
        return ""
    if not s.get("fps") or len(prev) < 2:
        return ""
    avg = sum(x["fps"] for x in prev) / len(prev)
    diff = (s["fps"] - avg) / avg * 100
    if abs(diff) < 5:
        return ""
    txt = f" · {abs(diff):.0f} % {'bedre' if diff > 0 else 'dårligere'} FPS enn snittet ({avg:.0f})"
    if diff < 0:
        try:
            import features
            drv = features.driver_info()
            last_drv = prev[-1].get("driver")
            if last_drv and drv and drv != last_drv:
                txt += " – ny skjermkortdriver siden sist?"
        except Exception:  # noqa: BLE001
            pass
    return txt


# --------------------------------------------------------------------------
# 42 – ping-vakt
# --------------------------------------------------------------------------
def _gateway():
    try:
        if IS_WIN:
            import winsupport
            _c, out = winsupport.run(["powershell", "-NoProfile", "-Command",
                                      "(Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Sort-Object RouteMetric | "
                                      "Select-Object -First 1).NextHop"], 20)
            return out.strip().splitlines()[-1].strip() or None
        out = subprocess.run(["ip", "-4", "route", "show", "default"], capture_output=True, text=True, timeout=5).stdout
        return out.split()[2] if out.split()[:2] == ["default", "via"] else None
    except Exception:  # noqa: BLE001
        return None


def _tcp_ping(host, port=53, timeout=1.5):
    t = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
        return (time.monotonic() - t) * 1000
    except OSError:
        return None


def _ping(host):
    """Ping i ms (ICMP via systemets ping; faller tilbake til TCP)."""
    try:
        args = ["ping", "-n", "1", "-w", "1500", host] if IS_WIN else ["ping", "-c", "1", "-W", "2", host]
        out = subprocess.run(args, capture_output=True, text=True, timeout=4,
                             **({"creationflags": 0x08000000} if IS_WIN else {})).stdout
        import re
        m = re.search(r"(?:time|tid)[=<]\s*([\d.,]+)\s*ms", out, re.I)
        if m:
            return float(m.group(1).replace(",", "."))
    except Exception:  # noqa: BLE001
        pass
    return _tcp_ping(host, 53 if host.count(".") == 3 else 443)


def ping_tick(win, game):
    """Hvert 30. sekund mens et spill kjører: 3 målinger mot ruteren og internett."""
    if not game or not cfg()["ping_watch"]:
        _STATE["ping"] = {}
        return
    gw = _STATE["ping"].get("gw") or _gateway()
    _STATE["ping"]["gw"] = gw
    net = [_ping("1.1.1.1") for _ in range(3)]
    loc = [_ping(gw) for _ in range(3)] if gw else []
    lost = sum(1 for x in net if x is None)
    good = [x for x in net if x is not None]
    avg = sum(good) / len(good) if good else None
    lavg = sum(x for x in loc if x is not None) / max(1, len([x for x in loc if x is not None])) if loc else None
    bad = lost >= 2 or (avg is not None and avg > 90) or (lavg is not None and lavg > 30)   # treg Wi-Fi gir hakk
    hist = _STATE["ping"].setdefault("bad", [])
    hist.append(bad)
    del hist[:-4]
    if sum(hist) >= 3 and time.time() - _STATE["ping"].get("said", 0) > 900:
        _STATE["ping"]["said"] = time.time()
        if lavg is not None and lavg > 30:
            why = f"Wi-Fi eller ruteren ({lavg:.0f} ms bare til ruteren) – prøv kabel eller nærmere ruteren"
        elif lost >= 2:
            why = "internett faller ut – sjekk ruteren eller leverandøren"
        else:
            why = f"internett er tregt ({avg:.0f} ms) – noen i huset laster kanskje ned"
        _ingame(f"📶 Dårlig ping: {why}", 30)
        _notify(win, "game", "Dårlig ping i spillet", why)
    return avg


# --------------------------------------------------------------------------
# 44 – Discord-kanal per spill
# --------------------------------------------------------------------------
def discord_join(channel_id):
    import discord_ctl as DC
    return DC._call("SELECT_VOICE_CHANNEL", {"channel_id": str(channel_id), "force": True})


# --------------------------------------------------------------------------
# 49 – lysshow
# --------------------------------------------------------------------------
def celebrate(win, kind="highlight"):
    if not cfg()["lightshow"]:
        return

    def run():
        cols = {"boss": ["#ffd23d", "#ff8a3d", "#ffd23d"], "ace": ["#ff2a6d", "#05d9e8", "#ff2a6d"]}.get(
            kind, ["#3dff8a", "#3dd6ff", "#3dff8a"])
        try:
            import remote
            win_ = win or getattr(remote, "win", None)
            for c in cols * 2:
                remote.do_action(win_, {"a": "rgb", "mode": "color", "color": c})
                time.sleep(0.35)
            remote.do_action(win_, {"a": "rgb", "mode": "restore"})
        except Exception:  # noqa: BLE001
            pass
        try:                                              # Hue blinker én gang
            import features
            features._hue("groups/0/action", {"alert": "select"}, "PUT")
        except Exception:  # noqa: BLE001
            pass
    threading.Thread(target=run, daemon=True, name="lysshow").start()


# --------------------------------------------------------------------------
# 50 – lydprofil per spill / 44 Discord ved spillstart
# --------------------------------------------------------------------------
def on_game_start(win, game):
    c = cfg()
    pid = c["audio_map"].get(game)
    if pid:
        try:
            import avprofiles
            d = avprofiles.devices()
            _STATE["prev_audio"] = {"out": d["cur_out"], "in": d["cur_in"], "out_vol": d["out_vol"]}
            avprofiles.apply_audio(pid)
        except Exception:  # noqa: BLE001
            pass
    ch = c["discord_map"].get(game)
    if ch:
        def j():
            time.sleep(10)
            try:
                discord_join(ch)
            except Exception:  # noqa: BLE001
                pass
        threading.Thread(target=j, daemon=True).start()


def on_game_end(win, game):
    prev, _STATE["prev_audio"] = _STATE["prev_audio"], None
    if prev:
        try:
            import avprofiles
            avprofiles.set_output(prev["out"], prev.get("out_vol"))
            if prev.get("in"):
                avprofiles.set_input(prev["in"])
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------
# 15 – delte spillprofiler (NAS)
# --------------------------------------------------------------------------
def share_profile(appid, name):
    """Legg startvalg + Proton for et Steam-spill på NAS-en."""
    import games
    import lanupdate as L
    import savegames
    import tempfile
    user = games.active_user()
    _l, _c, apps, mapping = games.load_settings(user)
    from vdf import get as vget
    prof = {"appid": str(appid), "name": name, "launch": vget(apps, str(appid), "LaunchOptions") or "",
            "proton": vget(mapping, str(appid), "name") or "", "by": savegames.pc_name(), "t": time.time()}
    tmp = tempfile.mkdtemp()
    p = os.path.join(tmp, f"{appid}.json")
    json.dump(prof, open(p, "w"), ensure_ascii=False)
    _h, _s, folder = L._split()
    L.smb_mkdir(f"{folder}/Spillprofiler")
    L._smb(f'cd "Spillprofiler"; put "{p}" "{appid}.json"', 60)
    return f"Delt: {name} ({prof['launch'] or 'standard startvalg'}" + (f", {prof['proton']}" if prof["proton"] else "") + ")"


def shared_profiles():
    """[profil] fra NAS-en."""
    import lanupdate as L
    import tempfile
    tmp = tempfile.mkdtemp()
    try:
        L._smb(f'cd "Spillprofiler"; prompt OFF; lcd "{tmp}"; mget *.json', 60)
    except Exception:  # noqa: BLE001
        return []
    out = []
    for f in glob.glob(os.path.join(tmp, "*.json")):
        try:
            out.append(json.load(open(f)))
        except (OSError, ValueError):
            pass
    return sorted(out, key=lambda p: p.get("name", ""))


def use_profile(prof):
    import games
    if games.steam_running():
        raise RuntimeError("Lukk Steam først – startvalgene kan bare endres når Steam er lukket")
    ch = {"launch": prof.get("launch", "")}
    if prof.get("proton") is not None:
        ch["proton"] = prof["proton"]
    games.save_settings(games.active_user(), {str(prof["appid"]): ch})
    return f"Bruker {prof.get('by')} sitt oppsett for {prof.get('name')} ✓"


# --------------------------------------------------------------------------
# 51 – retrospill (RetroArch)
# --------------------------------------------------------------------------
RA_DIRS = [os.path.join(HOME, ".config/retroarch"), os.path.join(HOME, ".var/app/org.libretro.RetroArch/config/retroarch"),
           os.path.join(os.environ.get("APPDATA", ""), "RetroArch")]


def retro_games():
    out = []
    for base in RA_DIRS:
        for pl in glob.glob(os.path.join(base, "playlists", "*.lpl")):
            try:
                d = json.load(open(pl, encoding="utf-8"))
            except (OSError, ValueError):
                continue
            system = os.path.basename(pl)[:-4]
            for it in d.get("items", []):
                if not it.get("path"):
                    continue
                label = it.get("label") or os.path.splitext(os.path.basename(it["path"]))[0]
                safe = "".join("_" if ch in '&*/:`<>?\\|' else ch for ch in label)
                cov = os.path.join(base, "thumbnails", system, "Named_Boxarts", safe + ".png")
                out.append({"id": it["path"], "name": label, "store": "retro", "system": system,
                            "core": it.get("core_path") or d.get("default_core_path") or "",
                            "cover": cov if os.path.exists(cov) else None, "flatpak": ".var/app" in base})
    return out


def retro_launch(g):
    core, rom = g.get("core"), g["id"]
    if g.get("flatpak"):
        cmd = ["flatpak", "run", "org.libretro.RetroArch"]
    else:
        cmd = ["retroarch"]
    if core and core != "DETECT":
        cmd += ["-L", core]
    subprocess.Popen(cmd + [rom], start_new_session=True)
    return True


# --------------------------------------------------------------------------
# 52 – forutsi spillkvelden
# --------------------------------------------------------------------------
def predicted_start(now=None):
    """Timen (0–23) du pleier å begynne å spille på denne ukedagen, eller None (minst 3 av de siste 4 ukene)."""
    try:
        import games_auto
        ss = games_auto.load_sessions()
    except Exception:  # noqa: BLE001
        return None
    now = now or time.time()
    wd = time.localtime(now).tm_wday
    hours = {}
    for w in range(1, 5):
        day = now - w * 7 * 86400
        dkey = time.strftime("%Y-%m-%d", time.localtime(day))
        starts = sorted(s["start"] for s in ss if s.get("start") and
                        time.strftime("%Y-%m-%d", time.localtime(s["start"])) == dkey)
        if starts and time.localtime(starts[0]).tm_wday == wd:
            h = time.localtime(starts[0]).tm_hour
            hours[h] = hours.get(h, 0) + 1
    best = max(hours.items(), key=lambda kv: kv[1]) if hours else None
    return best[0] if best and best[1] >= 3 else None


def predict_tick(win):
    c = cfg()
    if not c["predict"] or getattr(getattr(win, "bg", None), "game_name", None):
        return
    h = predicted_start()
    lt = time.localtime()
    if h is None or not (lt.tm_hour == (h - 1) % 24 and lt.tm_min >= 50):
        return
    key = time.strftime("%Y-%m-%d")
    if _STATE["predicted"] == key:
        return
    _STATE["predicted"] = key
    done = []
    if c["predict_prep"]:
        try:
            import remote
            remote.do_action(win, {"a": "power", "mode": "performance"})
            done.append("Max Ytelse")
        except Exception:  # noqa: BLE001
            pass
        try:
            import apps
            for k in ("steam", "discord"):
                if apps.installed(k):
                    apps.launch(k)
                    done.append(apps.APPS[k]["name"])
        except Exception:  # noqa: BLE001
            pass
    _notify(win, "game", f"Spillkveld kl. {h}?", "Du pleier å spille nå på denne dagen." +
            (f" Gjort klart: {', '.join(done)}." if done else " Slå på «Gjør klart» i Spill+ så starter Steam og "
                                                             "Discord av seg selv."))


# --------------------------------------------------------------------------
# 53 – smart oppstart
# --------------------------------------------------------------------------
LEARN_APPS = ("steam", "discord", "heroic", "lutris", "obs", "medal", "spotify", "firefox", "chrome", "openrgb",
              "teamspeak", "vesktop", "signalrgb", "ghub", "wivrn", "alvr")
_PROC = {"steam": ("steam", "steam.exe"), "discord": ("Discord", "discord", "Discord.exe"), "heroic": ("heroic",),
         "lutris": ("lutris",), "obs": ("obs", "obs64.exe"), "medal": ("Medal.exe",), "spotify": ("spotify",
                                                                                              "Spotify.exe"),
         "firefox": ("firefox", "firefox.exe"), "chrome": ("chrome", "chrome.exe"), "openrgb": ("openrgb",
                                                                                                "OpenRGB.exe"),
         "teamspeak": ("ts3client_linux_amd64", "ts3client_win64.exe"), "vesktop": ("vesktop",),
         "signalrgb": ("SignalRgb.exe",), "ghub": ("lghub.exe",), "wivrn": ("wivrn-server",),
         "alvr": ("alvr_dashboard",)}


def learn_startup():
    """10 min etter innlogging: hvilke programmer kjører? (husker de 10 siste oppstartene)"""
    try:
        import psutil
        names = {p.info["name"] for p in psutil.process_iter(["name"]) if p.info.get("name")}
    except Exception:  # noqa: BLE001
        return
    seen = sorted(k for k in LEARN_APPS if any(n in names for n in _PROC.get(k, ())))
    c = cfg()
    c["seen_start"] = (c["seen_start"] + [seen])[-10:]
    set_(seen_start=c["seen_start"])


def startup_suggestions():
    """Programmer du har åpnet ved minst 4 av 5 av de siste oppstartene."""
    runs = cfg()["seen_start"][-5:]
    if len(runs) < 3:
        return []
    count = {}
    for r in runs:
        for k in r:
            count[k] = count.get(k, 0) + 1
    return [k for k, n in sorted(count.items(), key=lambda kv: -kv[1]) if n >= max(3, len(runs) - 1)]


def smart_start():
    """Start programmene du pleier å åpne (med litt pause mellom), hvis de ikke allerede kjører."""
    try:
        import apps
        import psutil
        names = {p.info["name"] for p in psutil.process_iter(["name"]) if p.info.get("name")}
    except Exception:  # noqa: BLE001
        return []
    started = []
    for k in startup_suggestions():
        if any(n in names for n in _PROC.get(k, ())) or k not in apps.APPS or not apps.installed(k):
            continue
        try:
            apps.launch(k)
            started.append(apps.APPS[k]["name"])
            time.sleep(5)
        except Exception:  # noqa: BLE001
            pass
    return started


def startup_tick(win, uptime_s):
    """Lær bare når Kontrollsenter startet ved innlogging (de første 15 min etter oppstart av PC-en)."""
    _STATE.setdefault("start_up", uptime_s)
    if _STATE["boot_seen"] or uptime_s < 600 or _STATE["start_up"] > 900:
        return
    _STATE["boot_seen"] = True
    learn_startup()


def at_start(win):
    """Ved oppstart av Kontrollsenter (rett etter innlogging): start de vanlige programmene om det er slått på."""
    try:
        from sensors import uptime_seconds
        if uptime_seconds() > 900 or not cfg()["smart_start"]:
            return
    except Exception:  # noqa: BLE001
        return

    def run():
        time.sleep(30)
        s = smart_start()
        if s:
            _notify(win, "game", "Smart oppstart", "Startet: " + ", ".join(s))
    threading.Thread(target=run, daemon=True).start()


# --------------------------------------------------------------------------
# 54 – ikke forstyrr under møter
# --------------------------------------------------------------------------
MEETING = ("zoom", "Zoom.exe", "Teams", "ms-teams", "ms-teams.exe", "teams-for-linux", "webex", "CiscoCollabHost.exe",
           "Webex.exe", "skypeforlinux", "gotomeeting")


def in_meeting():
    if not cfg()["dnd_meetings"]:
        return False
    try:
        import procs
        names = set(procs.comm_map().values())
    except Exception:  # noqa: BLE001
        try:
            import psutil
            names = {p.info["name"] for p in psutil.process_iter(["name"])}
        except Exception:  # noqa: BLE001
            return False
    return any(any(m.lower() in (n or "").lower() for n in names) for m in MEETING)


# --------------------------------------------------------------------------
# 69 – spill-dagbok og 71 – husets toppliste
# --------------------------------------------------------------------------
def diary(limit=40):
    """[(tid, ikon, tekst)] nyeste først."""
    try:
        import games_auto
        ss = sorted(games_auto.load_sessions(), key=lambda s: s.get("start") or 0)
    except Exception:  # noqa: BLE001
        ss = []
    out, first, total, longest = [], {}, {}, {}
    for s in ss:
        n, t, m = s.get("name"), s.get("start") or 0, s.get("minutes") or 0
        if not n:
            continue
        if n not in first:
            first[n] = t
            out.append((t, "🆕", f"Spilte {n} for første gang"))
        before = total.get(n, 0)
        total[n] = before + m
        for ms in (10, 25, 50, 100, 250, 500, 1000):
            if before < ms * 60 <= total[n]:
                out.append((t, "⏱️", f"{ms} timer i {n}"))
        if m >= 60 and m > longest.get(n, 0):
            if n in longest:
                out.append((t, "🏃", f"Lengste økt i {n}: {m // 60} t {m % 60} min"))
            longest[n] = m
        if s.get("fps") and s.get("low") and s["low"] >= 0.8 * s["fps"] and m >= 30:
            pass
    out.sort(key=lambda x: -x[0])
    return out[:limit]


def house_toplist():
    """[(spill, timer denne uka, [PC-er])]"""
    tot = {}
    try:
        import homepcs
        for p in homepcs.fetch() or []:
            for g, s in (p.get("play_week") or {}).items():
                if g in ("SteamVR",):
                    continue
                e = tot.setdefault(g, [0, set()])
                e[0] += s
                e[1].add(p.get("name"))
    except Exception:  # noqa: BLE001
        pass
    return [(g, v[0] / 3600, sorted(v[1])) for g, v in sorted(tot.items(), key=lambda kv: -kv[1][0])][:8]


def who_plays():
    """[(navn, spill, hvor)] – PC-ene hjemme og vennene som spiller nå."""
    out = []
    try:
        import homepcs
        for p in homepcs.fetch() or []:
            if p.get("game") and time.time() - (p.get("time") or 0) < homepcs.STALE:
                out.append((p.get("name"), p["game"], "hjemme"))
    except Exception:  # noqa: BLE001
        pass
    try:
        import friends
        for f in friends.fetch_all() or []:
            if f and f.get("online") and f.get("game"):
                out.append((f.get("friend"), f["game"], "venn"))
    except Exception:  # noqa: BLE001
        pass
    return out


def play_together(win, game):
    """10: start samme spill her, inviter PC-ene hjemme og bli med i Discord-kanalen for spillet."""
    import launcher
    g = next((x for x in launcher.all_games() if x["name"] == game), None)
    msgs = []
    if g and launcher.launch(g):
        msgs.append(f"Starter {game}")
        try:
            launcher.invite(g)
            msgs.append("invitasjon sendt hjemme")
        except Exception:  # noqa: BLE001
            pass
    elif not g:
        msgs.append(f"{game} er ikke installert her")
    ch = cfg()["discord_map"].get(game)
    if ch:
        try:
            discord_join(ch)
            msgs.append("ble med i Discord-kanalen")
        except Exception as e:  # noqa: BLE001
            msgs.append(f"Discord: {e}")
    return " · ".join(msgs)


# --------------------------------------------------------------------------
# 40 – finn beste FPS-grense (MangoHud) og 22 – forvarm shadere
# --------------------------------------------------------------------------
FPS_STEPS = (0, 165, 144, 120, 90, 60)


def tune_fps(win, progress=None, seconds=30):
    """Prøv FPS-grenser mens spillet kjører; finn den høyeste som holder jevnt (1 % low ≥ 85 % av grensen)."""
    if IS_WIN:
        raise RuntimeError("bare på Linux (bruker MangoHud)")
    game = getattr(getattr(win, "bg", None), "game_name", None)
    if not game:
        raise RuntimeError("start spillet først")
    conf = os.path.expanduser("~/.config/MangoHud/MangoHud.conf")
    try:
        orig = open(conf).read()
    except OSError:
        orig = ""
    import games_auto
    sess = getattr(getattr(getattr(win, "bg", None), "auto", None), "session", None)
    results = []
    try:
        for i, cap in enumerate(FPS_STEPS):
            lines = [ln for ln in orig.splitlines() if not ln.strip().startswith("fps_limit")]
            open(conf, "w").write("\n".join(lines + [f"fps_limit={cap}"]) + "\n")     # MangoHud leser fila på nytt
            if progress:
                progress(i / len(FPS_STEPS), f"Prøver {'ingen grense' if not cap else f'{cap} FPS'}")
            time.sleep(5)
            samples, temps = [], []
            end = time.time() + seconds
            while time.time() < end:
                if sess:
                    samples += sess._live_fps()[-2:]
                temps.append(getattr(win, "_cpu_t", None) or 0)
                time.sleep(1)
            if not samples:
                continue
            ss = sorted(samples)
            avg = sum(ss) / len(ss)
            low = ss[max(0, len(ss) // 100)]
            results.append({"cap": cap, "avg": round(avg), "low": round(low), "temp": round(max(temps or [0]))})
    finally:
        open(conf, "w").write(orig)
    if not results:
        raise RuntimeError("fikk ingen FPS-målinger (er MangoHud på for spillet?)")
    unl = next((r for r in results if r["cap"] == 0), results[0])
    stable = [r for r in results if r["cap"] and r["low"] >= 0.85 * r["cap"] and r["avg"] >= 0.95 * r["cap"]]
    best = max(stable, key=lambda r: r["cap"]) if stable else None
    if best and unl["low"] >= 0.85 * unl["avg"] and unl["avg"] < best["cap"]:
        best = None
    return {"game": game, "results": results, "best": best["cap"] if best else None,
            "text": (f"Beste for {game}: {best['cap']} FPS – jevnt (1 % low {best['low']}) og "
                     f"{max(0, unl['temp'] - best['temp'])} °C kjøligere enn uten grense." if best else
                     f"Ingen grense gir best resultat i {game} (snitt {unl['avg']} FPS).")}


def prewarm(game_name, minutes=2):
    """Start spillet, la Steam/Proton bygge shadere en kort stund, og lukk det igjen."""
    import launcher
    g = next((x for x in launcher.all_games() if x["name"] == game_name), None)
    if not g:
        raise RuntimeError("fant ikke spillet")
    launcher.launch(g)
    time.sleep(minutes * 60)
    import familysafe
    name = familysafe.close_game()
    return f"Forvarmet {game_name}" + ("" if name else " (fant ikke spillet å lukke – lukk det selv)")


def tick(win):
    game = getattr(getattr(win, "bg", None), "game_name", None)
    try:
        ping_tick(win, game)
    except Exception:  # noqa: BLE001
        pass
    for fn in (predict_tick,):
        try:
            fn(win)
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("spill+: %s", fn.__name__)
    try:
        from sensors import uptime_seconds
        startup_tick(win, uptime_seconds())
    except Exception:  # noqa: BLE001
        pass
