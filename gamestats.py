"""Spillstatistikk – Steam (alle spill med statistikk, lest lokalt), CS2 live (Game State Integration) og
World of Warcraft (addonen KontrollsenterStats). Vises i Spill-fanen og i Android-appen.

Alt leses lokalt: ingen innlogging, ingen API-nøkkel og ingenting sendes ut av PC-en.
"""
import glob
import hmac
import json
import os
import re
import secrets
import shutil
import struct
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

APP_DIR = os.path.dirname(os.path.abspath(__file__))
IS_WIN = sys.platform == "win32"
CFG = os.path.expanduser("~/.config/systemmonitor/spillstatistikk.json")
GSI_PORT = 27102
CS2_APPID = "730"


def _load_cfg():
    try:
        with open(CFG, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_cfg(c):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    with open(CFG, "w", encoding="utf-8") as f:
        json.dump(c, f, indent=1)


# --------------------------------------------------------------------------
# Steams binære KeyValues (appcache/stats)
# --------------------------------------------------------------------------
def kv_parse(data, i=0):
    out = {}
    while i < len(data):
        t = data[i]
        i += 1
        if t in (8, 11):
            return out, i
        j = data.index(b"\0", i)
        key = data[i:j].decode("utf-8", "replace")
        i = j + 1
        if t == 0:
            v, i = kv_parse(data, i)
        elif t == 1:
            j = data.index(b"\0", i)
            v = data[i:j].decode("utf-8", "replace")
            i = j + 1
        elif t in (2, 4, 6):
            v = struct.unpack_from("<i", data, i)[0]
            i += 4
        elif t == 3:
            v = struct.unpack_from("<f", data, i)[0]
            i += 4
        elif t in (7, 10):
            v = struct.unpack_from("<q" if t == 10 else "<Q", data, i)[0]
            i += 8
        else:
            raise ValueError(f"ukjent KeyValues-type {t}")
        out[key] = v
    return out, i


def _txt(v):
    """Visningsnavn: norsk hvis det finnes, ellers engelsk."""
    if isinstance(v, dict):
        return v.get("norwegian") or v.get("english") or next((x for x in v.values() if isinstance(x, str)), "")
    return str(v or "")


def _steam():
    try:
        import games
        return games.STEAM, games.active_user()
    except Exception:  # noqa: BLE001
        return None, None


def steam_users():
    """[(kontonr, navn)] for kontoene på PC-en – den som sist var logget inn først."""
    steam, active = _steam()
    if not steam:
        return []
    names = {}
    try:
        import vdf
        for sid, u in (vdf.get(vdf.load(Path(steam) / "config/loginusers.vdf"), "users") or {}).items():
            names[str(int(sid) - 76561197960265728)] = vdf.get(u, "PersonaName", default="") or ""
    except Exception:  # noqa: BLE001
        pass
    users = sorted({re.search(r"UserGameStats_(\d+)_", f).group(1)
                    for f in glob.glob(str(Path(steam) / "appcache/stats/UserGameStats_*_*.bin"))})
    users = [u for u in users if (Path(steam) / "userdata" / u).is_dir() or u in names]
    users.sort(key=lambda u: u != active)
    return [(u, names.get(u) or u) for u in users]


def _playtimes(steam, user):
    """{appid: (minutter, sist spilt)} fra localconfig.vdf."""
    try:
        import vdf
        apps = vdf.get(vdf.load(Path(steam) / "userdata" / user / "config/localconfig.vdf"),
                       "UserLocalConfigStore", "Software", "Valve", "Steam", "apps") or {}
        return {a: (int(v.get("Playtime", 0) or 0), int(v.get("LastPlayed", 0) or 0)) for a, v in apps.items()
                if isinstance(v, dict)}
    except Exception:  # noqa: BLE001
        return {}


def _names(steam):
    out = {}
    try:
        import diskusage
        out = {a: n for a, n, _s, _d in diskusage.steam_games()}
    except Exception:  # noqa: BLE001
        pass
    return out


def steam_games_stats(user=None):
    """[{appid, name, playtime_min, last_played, stats: [(navn, verdi)], achievements: (har, av), highlights}]"""
    steam, active = _steam()
    user = user or active
    if not steam or not user:
        return []
    stats_dir = Path(steam) / "appcache" / "stats"
    play = _playtimes(steam, user)
    names = _names(steam)
    out = []
    for f in glob.glob(str(stats_dir / f"UserGameStats_{user}_*.bin")):
        appid = re.search(r"_(\d+)\.bin$", f).group(1)
        try:
            us, _ = kv_parse(Path(f).read_bytes())
            sch, _ = kv_parse((stats_dir / f"UserGameStatsSchema_{appid}.bin").read_bytes())
        except (OSError, ValueError):
            continue
        root = sch.get(appid) or next(iter(sch.values()), {})
        schema = root.get("stats", {})
        cache = us.get("cache", {})
        stats, raw, ach_have, ach_total = [], {}, 0, 0
        for sid, sdef in schema.items():
            if not isinstance(sdef, dict):
                continue
            val = cache.get(sid, {}).get("data") if isinstance(cache.get(sid), dict) else None
            if sdef.get("type") == "ACHIEVEMENTS":
                for bit, adef in (sdef.get("bits") or {}).items():
                    ach_total += 1
                    if val is not None and (val >> int(bit)) & 1:
                        ach_have += 1
                continue
            name = sdef.get("name", sid)
            if val is None:
                continue
            raw[name] = val
            disp = _txt((sdef.get("display") or {}).get("name")) or name
            if val:
                stats.append((disp, val))
        pt, last = play.get(appid, (0, 0))
        g = {"appid": appid, "name": names.get(appid) or root.get("gamename") or appid, "playtime_min": pt,
             "last_played": last, "stats": stats[:400], "achievements": [ach_have, ach_total],
             "highlights": highlights(appid, raw)}
        out.append(g)
    # spill uten statistikkfiler, men med spilletid
    for appid, (pt, last) in play.items():
        if pt and appid in names and not any(g["appid"] == appid for g in out):
            out.append({"appid": appid, "name": names[appid], "playtime_min": pt, "last_played": last, "stats": [],
                        "achievements": [0, 0], "highlights": []})
    return sorted(out, key=lambda g: -(g["last_played"] or 0))


def _pct(a, b):
    return f"{100 * a / b:.1f} %" if b else "–"


CS2_WEAPONS = {"ak47": "AK-47", "m4a1": "M4A4", "awp": "AWP", "deagle": "Desert Eagle", "glock": "Glock-18",
               "hkp2000": "P2000", "p250": "P250", "famas": "FAMAS", "galilar": "Galil AR", "aug": "AUG",
               "sg556": "SG 553", "ssg08": "SSG 08", "mp9": "MP9", "mac10": "MAC-10", "ump45": "UMP-45",
               "p90": "P90", "bizon": "PP-Bizon", "mp7": "MP7", "nova": "Nova", "xm1014": "XM1014", "mag7": "MAG-7",
               "sawedoff": "Sawed-Off", "negev": "Negev", "m249": "M249", "fiveseven": "Five-SeveN",
               "tec9": "Tec-9", "elite": "Dual Berettas", "scar20": "SCAR-20", "g3sg1": "G3SG1", "knife": "Kniv",
               "hegrenade": "Granat", "molotov": "Molotov", "taser": "Zeus", "mp5sd": "MP5-SD", "revolver": "R8"}


def highlights(appid, s):
    """Utregnede nøkkeltall (vises øverst) – foreløpig CS2."""
    if appid != CS2_APPID or not s:
        return []
    k, d = s.get("total_kills", 0), s.get("total_deaths", 0)
    out = [("Kills", k), ("Dødsfall", d), ("K/D", f"{k / d:.2f}" if d else "–"),
           ("Headshot", _pct(s.get("total_kills_headshot", 0), k)),
           ("Treffsikkerhet", _pct(s.get("total_shots_hit", 0), s.get("total_shots_fired", 0))),
           ("Runder vunnet", _pct(s.get("total_wins", 0), s.get("total_rounds_played", 0))),
           ("Kamper vunnet", f'{s.get("total_matches_won", 0)} av {s.get("total_matches_played", 0)}'),
           ("MVP", s.get("total_mvps", 0)), ("Skade totalt", s.get("total_damage_done", 0)),
           ("Bomber plantet / desarmert", f'{s.get("total_planted_bombs", 0)} / {s.get("total_defused_bombs", 0)}'),
           ("Spilt (Steam-statistikk)", f'{s.get("total_time_played", 0) / 3600:.0f} t')]
    weapons, shots_all, hits_all = [], 0, 0
    for key in CS2_WEAPONS:
        shots_all += s.get(f"total_shots_{key}", 0) if key not in ("knife", "hegrenade", "molotov") else 0
        hits_all += s.get(f"total_hits_{key}", 0) if key not in ("knife", "hegrenade", "molotov") else 0
    if not s.get("total_shots_hit") and shots_all:      # CS2 oppdaterer ikke totalen – regn ut fra våpnene
        out[4] = ("Treffsikkerhet", _pct(hits_all, shots_all))
    for key, nice in CS2_WEAPONS.items():
        kills = s.get(f"total_kills_{key}", 0)
        if kills:
            shots, hits = s.get(f"total_shots_{key}", 0), s.get(f"total_hits_{key}", 0)
            weapons.append((kills, nice, _pct(hits, shots) if shots else ""))
    weapons.sort(reverse=True)
    if weapons:
        out.append(("Favorittvåpen", f"{weapons[0][1]} ({weapons[0][0]} kills)"))
    lm = s.get("last_match_kills")
    if lm is not None:
        out.append(("Siste kamp", f'{lm} kills · {s.get("last_match_deaths", 0)} dødsfall · '
                                  f'{s.get("last_match_damage", 0)} skade · {s.get("last_match_mvps", 0)} MVP'))
    out += [(f"{nice}", f"{kills} kills" + (f" · {acc} treff" if acc else "")) for kills, nice, acc in weapons[:8]]
    return [(a, b) for a, b in out]


# --------------------------------------------------------------------------
# CS2 live – Game State Integration (Valves offisielle måte å lese kampen på)
# --------------------------------------------------------------------------
class Cs2Live:
    def __init__(self):
        self.last = None             # siste pakke fra spillet
        self.t = 0
        self.match = None            # opptelling i kampen som pågår
        self.httpd = None
        c = _load_cfg()
        self.token = c.get("gsi_token") or secrets.token_hex(16)
        if c.get("gsi_token") != self.token:
            c["gsi_token"] = self.token
            _save_cfg(c)

    def start(self):
        if self.httpd:
            return
        me = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                try:
                    data = json.loads(self.rfile.read(min(n, 1 << 20)) or b"{}")
                    if hmac.compare_digest(str((data.get("auth") or {}).get("token", "")), me.token):
                        me.feed(data)
                except ValueError:
                    pass
                self.send_response(200)
                self.end_headers()
        try:
            self.httpd = ThreadingHTTPServer(("127.0.0.1", GSI_PORT), H)       # bare lokalt
        except OSError:
            self.httpd = None
            return
        threading.Thread(target=self.httpd.serve_forever, daemon=True, name="cs2-gsi").start()

    def feed(self, d):
        self.last, self.t = d, time.time()
        mp, pl = d.get("map") or {}, d.get("player") or {}
        mine = pl.get("steamid") and pl.get("steamid") == (d.get("provider") or {}).get("steamid")
        key = (mp.get("name"), mp.get("mode"))
        if not mp:
            return
        if not self.match or self.match["key"] != key or (mp.get("round", 0) == 0 and self.match["round"] > 1):
            self.match = {"key": key, "round": 0, "hs": 0, "dmg": 0, "start": time.time(), "_r": {}}
        m = self.match
        rnd = mp.get("round", 0)
        if mine:
            st = pl.get("state") or {}
            # round_killhs / round_totaldmg nullstilles hver runde – ta vare på høyeste verdi per runde
            r = m["_r"].setdefault(rnd, {"hs": 0, "dmg": 0})
            r["hs"] = max(r["hs"], st.get("round_killhs", 0) or 0)
            r["dmg"] = max(r["dmg"], st.get("round_totaldmg", 0) or 0)
            m["hs"] = sum(x["hs"] for x in m["_r"].values())
            m["dmg"] = sum(x["dmg"] for x in m["_r"].values())
        m["round"] = rnd

    def state(self):
        """Kampen som pågår (eller None hvis CS2 ikke har sendt noe på 30 s)."""
        d = self.last
        if not d or time.time() - self.t > 30 or not d.get("map"):
            return None
        mp, pl = d["map"], d.get("player") or {}
        mine = pl.get("steamid") == (d.get("provider") or {}).get("steamid")
        ms, st = pl.get("match_stats") or {}, pl.get("state") or {}
        k = ms.get("kills", 0) if mine else None
        m = self.match or {}
        weapon = next((w for w in (pl.get("weapons") or {}).values() if w.get("state") == "active"), None)
        return {"map": mp.get("name"), "mode": mp.get("mode"), "phase": mp.get("phase"), "round": mp.get("round"),
                "ct": (mp.get("team_ct") or {}).get("score"), "t": (mp.get("team_t") or {}).get("score"),
                "team": pl.get("team"), "mine": mine,
                "kills": k, "deaths": ms.get("deaths") if mine else None, "assists": ms.get("assists") if mine else None,
                "mvps": ms.get("mvps") if mine else None, "score": ms.get("score") if mine else None,
                "hs": m.get("hs") if mine else None, "hs_pct": (f'{100 * m.get("hs", 0) / k:.0f} %' if mine and k else None),
                "dmg": m.get("dmg") if mine else None,
                "adr": (round(m.get("dmg", 0) / max(1, mp.get("round", 0))) if mine else None),
                "health": st.get("health"), "armor": st.get("armor"), "money": st.get("money"),
                "round_kills": st.get("round_kills"),
                "weapon": weapon and (weapon.get("name", "").replace("weapon_", "")),
                "ammo": weapon and weapon.get("ammo_clip"), "ammo_max": weapon and weapon.get("ammo_clip_max")}


LIVE = Cs2Live()


def cs2_cfg_dir():
    steam, _u = _steam()
    if not steam:
        return None
    try:
        import savegames
        libs = savegames._libs()
    except Exception:  # noqa: BLE001
        libs = [Path(steam) / "steamapps"]
    for lib in libs:
        d = Path(lib) / "common" / "Counter-Strike Global Offensive" / "game" / "csgo" / "cfg"
        if d.is_dir():
            return d
    return None


def install_cs2_gsi():
    """Legg gamestate_integration_kontrollsenter.cfg i CS2 (gjelder fra neste gang CS2 starter). (ok, melding)"""
    d = cs2_cfg_dir()
    if not d:
        return False, "Fant ikke CS2"
    text = ('"Kontrollsenter"\n{\n'
            f' "uri" "http://127.0.0.1:{GSI_PORT}"\n "timeout" "5.0"\n "buffer" "0.1"\n "throttle" "0.5"\n'
            ' "heartbeat" "10.0"\n'
            f' "auth"\n {{\n  "token" "{LIVE.token}"\n }}\n'
            ' "data"\n {\n  "provider" "1"\n  "map" "1"\n  "round" "1"\n  "player_id" "1"\n  "player_state" "1"\n'
            '  "player_weapons" "1"\n  "player_match_stats" "1"\n }\n}\n')
    f = d / "gamestate_integration_kontrollsenter.cfg"
    try:
        if not f.exists() or f.read_text() != text:
            f.write_text(text)
        return True, str(f)
    except OSError as e:
        return False, str(e)


# --------------------------------------------------------------------------
# World of Warcraft – addonen KontrollsenterStats
# --------------------------------------------------------------------------
ADDON_SRC = os.path.join(APP_DIR, "wow_addon", "KontrollsenterStats")
FLAVOR_PRODUCT = {"_retail_": "wow", "_ptr_": "wowt", "_xptr_": "wowxptr", "_beta_": "wow_beta",
                  "_classic_": "wow_classic", "_classic_ptr_": "wow_classic_ptr", "_classic_era_": "wow_classic_era",
                  "_anniversary_": "wow_anniversary", "_forever_": "wowf"}
FLAVOR_NAME = {"_retail_": "Retail", "_classic_": "Classic", "_classic_era_": "Classic Era",
               "_anniversary_": "Anniversary", "_forever_": "Forever", "_ptr_": "PTR", "_beta_": "Beta"}


def wow_roots():
    """Mapper som heter «World of Warcraft» (Battle.net under Wine/Proton på Linux, Program Files på Windows)."""
    home = os.path.expanduser("~")
    pats = [r"C:\Program Files (x86)\World of Warcraft", r"C:\Program Files\World of Warcraft",
            r"D:\World of Warcraft", r"D:\Games\World of Warcraft"] if IS_WIN else [
        f"{home}/Games/*/drive_c/Program Files*/World of Warcraft",
        f"{home}/Games/*/*/drive_c/Program Files*/World of Warcraft",
        f"{home}/.wine*/drive_c/Program Files*/World of Warcraft",
        f"{home}/.local/share/Steam/steamapps/compatdata/*/pfx/drive_c/Program Files*/World of Warcraft",
        f"{home}/.var/app/com.usebottles.bottles/data/bottles/bottles/*/drive_c/Program Files*/World of Warcraft",
        f"{home}/.local/share/bottles/bottles/*/drive_c/Program Files*/World of Warcraft",
        f"{home}/.var/app/net.lutris.Lutris/data/lutris/prefixes/*/drive_c/Program Files*/World of Warcraft"]
    out = []
    for p in pats:
        out += [x for x in glob.glob(p) if os.path.isdir(x)]
    seen, uniq = set(), []
    for p in out:                                  # /home og /var/home er samme mappe på Bazzite
        rp = os.path.realpath(p)
        if rp not in seen:
            seen.add(rp)
            uniq.append(p)
    return uniq


def _build_versions(root):
    out = {}
    try:
        lines = Path(root, ".build.info").read_text(errors="replace").splitlines()
        head = [h.split("!")[0] for h in lines[0].split("|")]
        for ln in lines[1:]:
            row = dict(zip(head, ln.split("|")))
            if row.get("Product") and row.get("Version"):
                out[row["Product"]] = row["Version"]
    except (OSError, IndexError):
        pass
    return out


def _interface(version):
    try:
        a, b, c = (int(x) for x in version.split(".")[:3])
        return a * 10000 + b * 100 + c
    except ValueError:
        return None


def wow_flavors():
    """[(root, flavor_dir, navn, interface)] for alle WoW-utgaver som er installert."""
    out = []
    for root in wow_roots():
        vers = _build_versions(root)
        for d in sorted(glob.glob(os.path.join(root, "_*_"))):
            fl = os.path.basename(d)
            if not glob.glob(os.path.join(d, "Wow*.exe")):
                continue
            iface = _interface(vers.get(FLAVOR_PRODUCT.get(fl, ""), ""))
            if not iface:                         # ukjent utgave: bruk det andre addons der oppgir
                nums = re.findall(r"\d{5,6}", " ".join(
                    Path(t).read_text(errors="replace")[:400] for t in glob.glob(os.path.join(
                        d, "Interface", "AddOns", "*", "*.toc"))[:40]))
                iface = max(map(int, nums)) if nums else None
            out.append((root, d, FLAVOR_NAME.get(fl, fl.strip("_").title()), iface))
    return out


def install_wow_addon():
    """Installer/oppdater addonen i alle WoW-utgaver. Returnerer liste med (utgave, ok, melding)."""
    import applog
    res = []
    for _root, d, name, iface in wow_flavors():
        dst = Path(d, "Interface", "AddOns", "KontrollsenterStats")
        try:
            dst.mkdir(parents=True, exist_ok=True)
            changed = False
            for src in Path(ADDON_SRC).iterdir():
                text = src.read_text(encoding="utf-8")
                text = text.replace("@INTERFACE@", str(iface or 11509)).replace("@VERSION@", applog.RUNNING)
                t = dst / src.name
                if not t.exists() or t.read_text(encoding="utf-8", errors="replace") != text:
                    t.write_text(text, encoding="utf-8")
                    changed = True
            res.append((name, True, "oppdatert" if changed else "allerede installert"))
        except OSError as e:
            res.append((name, False, str(e)))
    return res


def lua_parse(text):
    """Leser SavedVariables (Lua-tabeller) til Python. Tåler kommentarer og «["nøkkel"] = verdi,»."""
    i, n = 0, len(text)

    def ws():
        nonlocal i
        while i < n:
            if text[i] in " \t\r\n,;":
                i += 1
            elif text.startswith("--", i):
                j = text.find("\n", i)
                i = n if j < 0 else j + 1
            else:
                break

    def string():
        nonlocal i
        q = text[i]
        i += 1
        buf = []
        while i < n and text[i] != q:
            if text[i] == "\\" and i + 1 < n:
                c = text[i + 1]
                if c.isdigit():
                    m = re.match(r"\d{1,3}", text[i + 1:])
                    buf.append(chr(int(m.group(0))))
                    i += 1 + len(m.group(0))
                    continue
                buf.append({"n": "\n", "t": "\t", "r": "\r"}.get(c, c))
                i += 2
            else:
                buf.append(text[i])
                i += 1
        i += 1
        return "".join(buf)

    def value():
        nonlocal i
        ws()
        c = text[i]
        if c == "{":
            i += 1
            d, arr = {}, []
            while True:
                ws()
                if text[i] == "}":
                    i += 1
                    break
                if text[i] == "[":
                    i += 1
                    k = value()
                    ws()
                    i += 1          # ]
                    ws()
                    i += 1          # =
                    d[k] = value()
                else:
                    m = re.match(r"([A-Za-z_]\w*)\s*=", text[i:])
                    if m:
                        i += m.end()
                        d[m.group(1)] = value()
                    else:
                        arr.append(value())
            if arr and not d:
                return arr
            for idx, v in enumerate(arr, 1):
                d[idx] = v
            return d
        if c in "\"'":
            return string()
        m = re.match(r"-?(?:0x[0-9a-fA-F]+|\d+\.?\d*(?:[eE][-+]?\d+)?)", text[i:])
        if m:
            i += m.end()
            s = m.group(0)
            return int(s, 16) if "x" in s.lower() else (float(s) if any(x in s for x in ".eE") else int(s))
        for word, val in (("true", True), ("false", False), ("nil", None)):
            if text.startswith(word, i):
                i += len(word)
                return val
        raise ValueError(f"uventet tegn {c!r} ved {i}")

    out = {}
    while True:
        ws()
        m = re.match(r"([A-Za-z_]\w*)\s*=", text[i:])
        if not m:
            break
        i += m.end()
        out[m.group(1)] = value()
    return out


def wow_stats():
    """[karakter-ordbok + flavor/account/file] fra alle WoW-utgaver og kontoer, sist spilt først."""
    chars = []
    for _root, d, name, _iface in wow_flavors():
        for f in glob.glob(os.path.join(d, "WTF", "Account", "*", "SavedVariables", "KontrollsenterStats.lua")):
            try:
                db = lua_parse(Path(f).read_text(encoding="utf-8", errors="replace")).get("KontrollsenterStatsDB") or {}
            except (OSError, ValueError, IndexError):
                continue
            for key, c in (db.get("chars") or {}).items():
                if isinstance(c, dict):
                    c = dict(c)
                    c["flavor"], c["account"] = name, Path(f).parents[1].name
                    c["saved"] = os.path.getmtime(f)
                    chars.append(c)
    return sorted(chars, key=lambda c: -(c.get("last_seen") or 0))


def wow_summary(c):
    """Fine tall for visning: (overskrift, [(navn, verdi)], toppliste-tabeller)."""
    dist = c.get("dist") or {}
    km = {k: (v or 0) * 0.9144 / 1000 for k, v in dist.items()}
    total_km = sum(km.values())

    def dur(s):
        s = int(s or 0)
        d, h, m = s // 86400, s % 86400 // 3600, s % 3600 // 60
        return (f"{d} d " if d else "") + (f"{h} t " if h or d else "") + f"{m} min"

    def gold(cop):
        cop = int(cop or 0)
        return f"{cop // 10000} g {cop % 10000 // 100} s"
    lt = c.get("level_time") or {}
    lvl_rows = sorted(((int(k), v) for k, v in lt.items() if isinstance(v, (int, float))), reverse=True)[:12]
    rows = [("Spilt totalt", dur(c.get("played"))), (f"Spilt på level {c.get('level')}", dur(c.get("played_level"))),
            ("Tilbakelagt", f"{total_km:.1f} km"),
            ("  til fots / ridende", f"{km.get('walk', 0):.1f} / {km.get('mount', 0):.1f} km"),
            ("  svømt / flytaxi / fløyet", f"{km.get('swim', 0):.1f} / {km.get('taxi', 0):.1f} / {km.get('fly', 0):.1f} km"),
            ("Drept", c.get("kills", 0)), ("Dødsfall", c.get("deaths", 0)),
            ("Quests fullført", c.get("quests", 0)), ("XP tjent", c.get("xp", 0)),
            ("Gull tjent / brukt", f"{gold(c.get('gold_in'))} / {gold(c.get('gold_out'))}"),
            ("Gull nå", gold(c.get("money"))), ("Skade totalt", c.get("dmg", 0)),
            ("Største treff", f"{c.get('max_hit', 0)} ({c.get('max_hit_spell') or '–'})"),
            ("Healing totalt", c.get("heal", 0)), ("Kritiske treff", c.get("crits", 0)),
            ("Tid i kamp", dur(c.get("combat_time"))), ("Hopp", c.get("jumps", 0)),
            ("Soner besøkt", len(c.get("zones") or {})), ("Innlogginger", c.get("sessions", 0)),
            ("Honorable kills", c.get("hk", 0))]
    rows += [(f"Tid på level {lvl}", dur(t)) for lvl, t in lvl_rows]
    top = lambda t: sorted(((k, v) for k, v in (t or {}).items() if isinstance(v, (int, float))),  # noqa: E731
                           key=lambda x: -x[1])[:10]
    ls = c.get("last_session") or {}
    session = None
    if ls:
        session = [("Lengde", dur(ls.get("len"))), ("Drept", ls.get("kills", 0)), ("XP", ls.get("xp", 0)),
                   ("Tilbakelagt", f"{(ls.get('dist') or 0) * 0.9144 / 1000:.1f} km"),
                   ("Gull tjent", gold(ls.get("gold"))), ("Quests", ls.get("quests", 0)),
                   ("Dødsfall", ls.get("deaths", 0))]
    title = f"{c.get('name')} – level {c.get('level')} {c.get('race') or ''} {c.get('class_name') or ''}".strip()
    return {"title": title, "sub": f"{c.get('realm')} · WoW {c.get('flavor')}", "rows": rows,
            "kills_by": top(c.get("kills_by")), "killers": top(c.get("killers")), "session": session,
            "last_seen": c.get("last_seen"), "class": c.get("class")}


# --------------------------------------------------------------------------
# Samlet (for Spill-fanen og Android-appen)
# --------------------------------------------------------------------------
def snapshot():
    out = {"live": LIVE.state(), "wow": [], "steam": [], "accounts": []}
    try:
        out["wow"] = [wow_summary(c) for c in wow_stats()]
    except Exception as e:  # noqa: BLE001
        out["wow_error"] = str(e)
    try:
        for uid, name in steam_users():
            out["accounts"].append({"id": uid, "name": name, "games": steam_games_stats(uid)})
        out["steam"] = out["accounts"][0]["games"] if out["accounts"] else []
    except Exception as e:  # noqa: BLE001
        out["steam_error"] = str(e)
    return out


def setup_background():
    """Ved oppstart: lytt etter CS2, og legg inn CS2-oppsettet og WoW-addonen hvis spillene finnes."""
    def work():
        try:
            LIVE.start()
            install_cs2_gsi()
            install_wow_addon()
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("spillstatistikk")
    threading.Thread(target=work, daemon=True).start()
