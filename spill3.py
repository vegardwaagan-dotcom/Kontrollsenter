"""Spill, runde 3: årsoppsummering («Wrapped»), plass per spill, før/etter-sammenligning, spilloppdatering om natten,
nettet i spillet (ping og tap til selve spillserveren) og LAN-turnering med poengtavle.

Bygger på det Kontrollsenter allerede logger: spilletid per dag (remote_extra), spilløktene med FPS (games_auto),
klippene, CS2-kampene og prestasjonene – og Steams egne filer (appmanifest, config.vdf).
"""
import json
import os
import re
import subprocess
import sys
import time

IS_WIN = sys.platform == "win32"
CFG = os.path.expanduser("~/.config/systemmonitor/spill3.json")
DEF = {"marks": [], "night_updates": False}


def cfg():
    try:
        return {**DEF, **json.load(open(CFG))}
    except (OSError, ValueError):
        return dict(DEF)


def set_(**kw):
    c = cfg()
    c.update(kw)
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    with open(CFG + ".tmp", "w") as f:
        json.dump(c, f)
    os.replace(CFG + ".tmp", CFG)
    return c


def _hours(sec):
    h = sec / 3600
    return f"{h:.1f} t" if h < 10 else f"{h:.0f} t"


# ------------------------------------------------------------------ 40 – årsoppsummering
def wrapped(year=None):
    year = int(year or time.localtime().tm_year)
    import remote_extra
    days = {d: g for d, g in remote_extra._play_data().items() if d.startswith(str(year))}
    per_game, per_month, per_wday = {}, {}, [0.0] * 7
    best_day = (None, 0)
    for d, games in days.items():
        tot = sum(games.values())
        if tot > best_day[1]:
            best_day = (d, tot)
        per_month[d[5:7]] = per_month.get(d[5:7], 0) + tot
        try:
            per_wday[time.strptime(d, "%Y-%m-%d").tm_wday] += tot
        except ValueError:
            pass
        for g, s in games.items():
            per_game[g] = per_game.get(g, 0) + s
    total = sum(per_game.values())
    top = sorted(per_game.items(), key=lambda x: -x[1])[:5]
    sessions = []
    try:
        import games_auto
        sessions = [s for s in games_auto.load_sessions() if time.localtime(s.get("start", 0)).tm_year == year]
    except Exception:  # noqa: BLE001
        pass
    longest = max(sessions, key=lambda s: s.get("minutes") or 0, default=None)
    clips_n = 0
    try:
        import clips
        clips_n = sum(1 for c in clips.clips(5000) if time.localtime(c["t"]).tm_year == year)
    except Exception:  # noqa: BLE001
        pass
    cs2 = []
    try:
        cs2 = [m for m in remote_extra._jload(remote_extra.CS2_MATCHES, []) if
               time.localtime(m.get("t", 0)).tm_year == year]
    except Exception:  # noqa: BLE001
        pass
    ach = 0
    try:
        import today
        ach = sum(1 for a in today.achievements() if a.get("unlocked"))
    except Exception:  # noqa: BLE001
        pass
    mnames = ["jan", "feb", "mar", "apr", "mai", "jun", "jul", "aug", "sep", "okt", "nov", "des"]
    wnames = ["mandager", "tirsdager", "onsdager", "torsdager", "fredager", "lørdager", "søndager"]
    top_m = max(per_month.items(), key=lambda x: x[1], default=(None, 0))
    r = {"year": year, "days_logged": len(days), "total_h": round(total / 3600, 1),
         "top": [{"game": g, "h": round(s / 3600, 1)} for g, s in top],
         "best_day": best_day[0], "best_day_h": round(best_day[1] / 3600, 1),
         "top_month": mnames[int(top_m[0]) - 1] if top_m[0] else None,
         "fav_wday": wnames[per_wday.index(max(per_wday))] if any(per_wday) else None,
         "longest": {"game": longest["name"], "min": longest.get("minutes")} if longest else None,
         "clips": clips_n, "cs2_matches": len(cs2), "cs2_kills": sum(m.get("kills") or 0 for m in cs2),
         "achievements": ach}
    r["text"] = wrapped_text(r)
    return r


def wrapped_text(r):
    if not r["total_h"]:
        return f"🎮 {r['year']}: ingen spilletid logget ennå."
    lines = [f"🎮 Mitt spillår {r['year']}: {r['total_h']:.0f} timer"]
    if r["top"]:
        lines.append("🏆 " + " · ".join(f"{i + 1}. {t['game']} ({t['h']:.0f} t)" for i, t in enumerate(r["top"][:3])))
    if r["longest"]:
        lines.append(f"⏱️ Lengste økt: {r['longest']['min'] // 60} t {r['longest']['min'] % 60} min i "
                     f"{r['longest']['game']}")
    if r["best_day"]:
        lines.append(f"📅 Mest på én dag: {r['best_day_h']:.1f} t ({r['best_day'][8:]}.{r['best_day'][5:7]})"
                     + (f" · favorittdag: {r['fav_wday']}" if r["fav_wday"] else ""))
    extra = []
    if r["clips"]:
        extra.append(f"🎬 {r['clips']} klipp")
    if r["cs2_matches"]:
        extra.append(f"🔫 {r['cs2_matches']} CS2-kamper, {r['cs2_kills']} kills")
    if r["achievements"]:
        extra.append(f"🏅 {r['achievements']} prestasjoner")
    if extra:
        lines.append(" · ".join(extra))
    return "\n".join(lines)


# ------------------------------------------------------------------ 22 – plass per spill
def storage(days=180):
    """Spill som tar mye plass og ikke er spilt på lenge – størst først."""
    import games
    now = time.time()
    out = []
    for g in games.installed_games():
        if not g.get("size") or re.search(r"Runtime|Redistributable|Proton|Steamworks", g["name"]):
            continue
        last = g.get("last_played") or 0
        age = (now - last) / 86400 if last else None
        out.append({"appid": g["appid"], "name": g["name"], "gb": round(g["size"] / 2 ** 30, 1),
                    "days": round(age) if age is not None else None,
                    "old": age is None or age >= days})
    out.sort(key=lambda x: -x["gb"])
    old = [x for x in out if x["old"]]
    return {"all": out, "old": old, "old_gb": round(sum(x["gb"] for x in old), 1),
            "total_gb": round(sum(x["gb"] for x in out), 1)}


def uninstall(appid):
    """Ber Steam avinstallere spillet (Steam spør selv om bekreftelse)."""
    if not re.fullmatch(r"\d+", str(appid)):
        raise ValueError("ugyldig spill")
    url = f"steam://uninstall/{appid}"
    if IS_WIN:
        os.startfile(url)  # noqa: S606
    else:
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return "Steam spør om du vil avinstallere"


# ------------------------------------------------------------------ 5 – før og etter
def mark(label):
    c = cfg()
    c["marks"] = (c["marks"] + [{"t": time.time(), "label": (label or "Endring").strip()[:60]}])[-10:]
    set_(marks=c["marks"])
    return "Merket – spill som vanlig, så sammenligner Kontrollsenter FPS før og etter"


def compare():
    """FPS i spilløktene før og etter siste merke, per spill."""
    c = cfg()
    if not c["marks"]:
        return {"mark": None, "games": []}
    m = c["marks"][-1]
    try:
        import games_auto
        ss = [s for s in games_auto.load_sessions() if s.get("fps")]
    except Exception:  # noqa: BLE001
        ss = []
    res = []
    for name in sorted({s["name"] for s in ss}):
        before = [s for s in ss if s["name"] == name and s["start"] < m["t"]][-5:]
        after = [s for s in ss if s["name"] == name and s["start"] >= m["t"]]
        if not before or not after:
            continue

        def avg(lst, k):
            v = [s[k] for s in lst if s.get(k)]
            return sum(v) / len(v) if v else None
        b, a = avg(before, "fps"), avg(after, "fps")
        bl, al = avg(before, "low"), avg(after, "low")
        res.append({"game": name, "before": round(b), "after": round(a), "pct": round((a - b) / b * 100, 1),
                    "low_before": round(bl) if bl else None, "low_after": round(al) if al else None,
                    "n": len(after)})
    return {"mark": m, "games": res}


# ------------------------------------------------------------------ 21 – spilloppdatering om natten (Steam)
def night_updates(on, start=2, end=6):
    """Steam oppdaterer spillene bare mellom start og end (om natten). Steam må være lukket."""
    import games
    import shutil
    import vdf
    if games.steam_running():
        raise RuntimeError("lukk Steam først – Steam skriver over innstillingene sine når den avsluttes")
    path = games.STEAM / "config/config.vdf"
    shutil.copy2(path, f"{path}.bak-systemmonitor-{time.strftime('%Y%m%d-%H%M%S')}")
    conf = vdf.load(path)
    st = vdf.ensure(conf, "InstallConfigStore", "Software", "Valve", "Steam")
    st["AutoUpdateWindowEnabled"] = "1" if on else "0"
    st["AutoUpdateWindowStart"] = str(start if on else -1)
    st["AutoUpdateWindowEnd"] = str(end if on else -1)
    vdf.dump(conf, path)
    set_(night_updates=bool(on))
    return (f"Steam oppdaterer spillene bare mellom kl. {start:02d} og {end:02d} – la PC-en og Steam stå på "
            "(oppdateringskvelden vekker PC-en)") if on else "Steam oppdaterer spillene når som helst igjen"


# ------------------------------------------------------------------ 23 – nettet i spillet: selve spillserveren
def _game_pids(appid=None):
    """Prosesser startet av Steam for spillet (miljøvariabelen SteamGameId/SteamAppId)."""
    out = []
    if IS_WIN:
        return out
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            env = open(f"/proc/{d}/environ", "rb").read()
        except OSError:
            continue
        m = re.search(rb"SteamGameId=(\d+)", env)
        if m and (appid is None or m.group(1).decode() == str(appid)) and m.group(1) != b"0":
            out.append(int(d))
    if not out:                                          # spill utenfor Steam (Battle.net, Lutris …): .exe under Wine
        skip = re.compile(r"(wineserver|services|explorer|winedevice|plugplay|svchost|rpcss|steam|steamwebhelper|"
                          r"battle\.net|agent|epicgameslauncher|galaxyclient|conhost|start|winemenubuilder|"
                          r"crashpad|easyanticheat|cefprocess)\.exe$", re.I)
        for d in os.listdir("/proc"):
            if not d.isdigit():
                continue
            try:
                cmd = open(f"/proc/{d}/cmdline", "rb").read().split(b"\0")[0].decode(errors="ignore")
            except OSError:
                continue
            path = cmd.replace("\\", "/").lower()
            exe = path.rsplit("/", 1)[-1]
            if exe.endswith(".exe") and not skip.search(exe) and "/windows/" not in path and "xalia" not in path:
                out.append(int(d))
    return out


def _private(ip):
    return ip.startswith(("10.", "192.168.", "127.", "169.254.", "100.", "::1", "fe80", "fc", "fd")) or \
        re.match(r"172\.(1[6-9]|2\d|3[01])\.", ip) is not None


def game_server(appid=None):
    """IP-adressen spillet snakker mest med (UDP foretrukket) – None hvis ingen."""
    pids = set(_game_pids(appid))
    if not pids:
        return None
    try:
        out = subprocess.run(["ss", "-Hntup"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    cand = []
    for line in out.splitlines():
        pm = re.findall(r"pid=(\d+)", line)
        if not pm or not pids & {int(p) for p in pm}:
            continue
        parts = line.split()
        if len(parts) < 6:
            continue
        peer = parts[5]
        ip = peer.rsplit(":", 1)[0].strip("[]")
        if ip in ("*", "0.0.0.0") or _private(ip):
            continue
        cand.append((0 if parts[0] == "udp" else 1, ip))
    cand.sort()
    return cand[0][1] if cand else None


def net_sample(appid=None):
    """Én måling: ping til ruteren, internett og spillserveren (3 forsøk hver)."""
    import gamesplus as G
    gw = G._gateway()

    def m(host, n=3):
        if not host:
            return None, None
        v = [G._ping(host) for _ in range(n)]
        ok = [x for x in v if x is not None]
        return (round(sum(ok) / len(ok), 1) if ok else None), round((n - len(ok)) / n * 100)
    srv = game_server(appid)
    r = {"t": time.time(), "server": srv}
    r["gw"], r["gw_loss"] = m(gw)
    r["net"], r["net_loss"] = m("1.1.1.1")
    r["srv"], r["srv_loss"] = m(srv)
    return r


NET = {"hist": [], "game": None}


def net_tick(game):
    """Kalles hvert 30. sekund mens et spill kjører (fra gamesplus.ping_tick)."""
    if not game:
        if NET["hist"] and time.time() - NET["hist"][-1]["t"] > 600:
            NET["hist"] = []
        return
    appid, name = game
    if NET["game"] != name:
        NET.update(game=name, hist=[])
    NET["hist"].append(net_sample(appid))
    del NET["hist"][:-120]                               # en time


def net_verdict(h=None):
    h = h if h is not None else NET["hist"]
    if not h:
        return ""
    last = h[-5:]

    def avg(k):
        v = [x[k] for x in last if x.get(k) is not None]
        return sum(v) / len(v) if v else None
    gw, net, srv = avg("gw"), avg("net"), avg("srv")
    loss = max((x.get("srv_loss") or 0) for x in last)
    if gw is not None and gw > 20:
        return f"Laggen kommer fra Wi-Fi/ruteren hjemme ({gw:.0f} ms bare til ruteren)"
    if net is not None and net > 80:
        return f"Internett er tregt ({net:.0f} ms) – noen laster kanskje ned"
    if srv is not None and net is not None and srv > net + 60:
        return f"Laggen kommer fra spillserveren ({srv:.0f} ms) – nettet ditt er fint ({net:.0f} ms)"
    if loss >= 34:
        return f"Pakketap til spillserveren ({loss} %)"
    return "Nettet ser bra ut ✓"


# ------------------------------------------------------------------ 43 – LAN-turnering
T_FILE = "turnering.json"


def _t_local():
    return os.path.expanduser("~/.cache/systemmonitor/turnering.json")


def t_load():
    d = None
    try:
        import lanupdate as L
        import tempfile
        if L.on_lan():
            tmp = tempfile.mkdtemp()
            L._smb(f'cd "Familie"; get "{T_FILE}" "{tmp}/t.json"', 20)
            d = json.load(open(f"{tmp}/t.json"))
            with open(_t_local(), "w") as f:
                json.dump(d, f)
    except Exception:  # noqa: BLE001
        d = None
    if d is None:
        try:
            d = json.load(open(_t_local()))
        except (OSError, ValueError):
            d = {}
    return d or {"name": "", "game": "", "teams": [], "rounds": [], "t": 0}


def t_save(d):
    d["t"] = time.time()
    os.makedirs(os.path.dirname(_t_local()), exist_ok=True)
    with open(_t_local(), "w") as f:
        json.dump(d, f)
    try:
        import lanupdate as L
        if L.on_lan():
            L._smb(f'cd "Familie"; put "{_t_local()}" "{T_FILE}"', 20)
    except Exception:  # noqa: BLE001
        pass
    return d


def t_new(name, game, teams):
    """teams = [{"name": "Lag 1", "players": ["Ola", "Kari"]}]"""
    teams = [{"name": (t.get("name") or f"Lag {i + 1}")[:30], "players": [p[:30] for p in t.get("players", [])][:8],
              "score": 0} for i, t in enumerate(teams)][:8]
    if len(teams) < 2:
        raise ValueError("minst to lag eller spillere")
    return t_save({"name": (name or "Turnering")[:40], "game": (game or "")[:40], "teams": teams, "rounds": []})


def t_score(team, delta=1):
    d = t_load()
    if not 0 <= int(team) < len(d.get("teams", [])):
        raise ValueError("ukjent lag")
    d["teams"][int(team)]["score"] = max(0, d["teams"][int(team)]["score"] + int(delta))
    d.setdefault("rounds", []).append({"t": time.time(), "team": int(team), "d": int(delta)})
    return t_save(d)


def t_end():
    d = t_load()
    if not d.get("teams"):
        return "Ingen turnering"
    best = max(d["teams"], key=lambda t: t["score"])
    t_save({"name": "", "game": "", "teams": [], "rounds": [], "last": {"name": d["name"], "winner": best["name"],
                                                                          "score": best["score"]}})
    return f"🏆 {best['name']} vant {d['name']} med {best['score']} poeng!"


def t_gamemode_all(win=None):
    """Spillmodus på alle PC-ene i huset (via husnøkkelen) og her."""
    import homepcs
    done = 0
    try:
        import remote
        remote.do_action(win or getattr(remote, "win", None), {"a": "gamemode", "on": True})
        done += 1
    except Exception:  # noqa: BLE001
        pass
    import savegames
    me = savegames.pc_name()
    for p in homepcs.fetch() or []:
        if me in (p.get("name"), p.get("host"), p.get("hostname")):
            continue
        try:
            ok, _r = homepcs.house_call(p, "gamemode", timeout=10, on=1)
            done += 1 if ok else 0
        except Exception:  # noqa: BLE001
            continue
    return f"Spillmodus på {done} PC-er"
