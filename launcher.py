"""Alle spillene samlet: Steam, Heroic (Epic/GOG) og Lutris (Battle.net m.fl.), med cover-bilder.

Ett trykk starter spillet – scener, temaer og spillprofiler som hører til spillet slår seg på av seg selv når spillet
kjører. «Spill sammen» sender en invitasjon til de andre PC-ene i huset; de kan trykke på varselet for å bli med.
"""
import glob
import json
import os
import re
import sqlite3
import time
import urllib.request
from pathlib import Path

HOME = Path.home()
CACHE = HOME / ".cache/systemmonitor/covers"
INVITE = "🎮 Bli med?"


def _steam_cover(appid):
    import games
    lc = games.STEAM / "appcache/librarycache" if games.STEAM else None
    if lc:
        for pat in (f"{appid}/library_600x900.jpg", f"{appid}/*/library_600x900.jpg", f"{appid}_library_600x900.jpg"):
            hits = glob.glob(str(lc / pat))
            if hits:
                return hits[0]
    p = CACHE / f"steam_{appid}.jpg"
    return str(p) if p.exists() else None


def fetch_missing_covers(games_list):
    """Hent manglende Steam-cover fra Steam (i bakgrunnen). Bare appid sendes."""
    CACHE.mkdir(parents=True, exist_ok=True)
    for g in games_list:
        if g["store"] != "steam" or g.get("cover"):
            continue
        p = CACHE / f"steam_{g['id']}.jpg"
        try:
            url = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{g['id']}/library_600x900.jpg"
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Kontrollsenter"}), timeout=10) as r:
                p.write_bytes(r.read())
            g["cover"] = str(p)
        except Exception:  # noqa: BLE001
            continue


def _heroic():
    out = []
    base = HOME / ".config/heroic"
    if not base.is_dir():
        base = HOME / ".var/app/com.heroicgameslauncher.hgl/config/heroic"
    for store, f in (("legendary", "store_cache/legendary_library.json"), ("gog", "store_cache/gog_library.json")):
        try:
            d = json.loads((base / f).read_text())
        except (OSError, ValueError):
            continue
        for g in d.get("library", d if isinstance(d, list) else []):
            if not g.get("is_installed"):
                continue
            out.append({"id": g.get("app_name"), "name": g.get("title"), "store": "heroic-" + store,
                        "cover": g.get("art_square") or g.get("art_cover"), "cover_url": True})
    return out


def _lutris():
    out = []
    db = HOME / ".local/share/lutris/pga.db"
    if not db.exists():
        return out
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        for gid, name, slug in con.execute("select id, name, slug from games where installed = 1"):
            cov = None
            for d in ("coverart", "banners"):
                hits = glob.glob(str(HOME / f".local/share/lutris/{d}/{slug}.*"))
                if hits:
                    cov = hits[0]
                    break
            out.append({"id": str(gid), "name": name, "store": "lutris", "cover": cov})
        con.close()
    except sqlite3.Error:
        pass
    return out


def all_games():
    """[{id, name, store, cover, last, week_s}] sortert: sist spilt først, så alfabetisk."""
    import games
    out = []
    try:
        for g in games.installed_games():
            out.append({"id": g["appid"], "name": g["name"], "store": "steam", "cover": _steam_cover(g["appid"])})
    except Exception:  # noqa: BLE001
        pass
    out = [g for g in out if not re.search(r"Steam Linux Runtime|Legacy Steam Runtime|Steamworks|Proton|"
                                           r"Redistributable|SteamVR", g["name"] or "")]
    out += _heroic() + _lutris()
    last, week = {}, {}
    try:
        import games_auto
        for s in games_auto.load_sessions():
            last[s.get("name")] = max(last.get(s.get("name"), 0), s.get("start") or 0)
        import remote_extra
        week = dict(remote_extra.playtime_summary(7)["week"])
    except Exception:  # noqa: BLE001
        pass
    for g in out:
        g["last"] = last.get(g["name"], 0)
        g["week_s"] = week.get(g["name"], 0)
    return sorted(out, key=lambda g: (-g["last"], g["name"].lower()))


def launch_uri(g):
    if g["store"] == "steam":
        return f"steam://rungameid/{g['id']}"
    if g["store"].startswith("heroic-"):
        return f"heroic://launch/{g['store'][7:]}/{g['id']}"
    if g["store"] == "lutris":
        return f"lutris:rungameid/{g['id']}"
    return None


def launch(g):
    from gi.repository import Gio
    uri = launch_uri(g)
    if uri:
        Gio.AppInfo.launch_default_for_uri(uri, None)
        return True
    return False


# ---- «Spill sammen» -------------------------------------------------------------------------------------
def invite(g, targets="*"):
    """Send «Bli med?» til de andre PC-ene. Mottakeren kan trykke på varselet for å starte samme spill."""
    import features
    import savegames
    me = savegames.pc_name()
    payload = json.dumps({"store": g["store"], "id": g["id"], "name": g["name"]}, ensure_ascii=False)
    text = f"{INVITE} {me} vil spille {g['name']} nå. Trykk på varselet for å bli med! [invite:{payload}]"
    features.send_to(targets, me, text)
    return f"Invitasjon sendt til {'alle PC-ene' if targets == '*' else targets}"


def parse_invite(text):
    """(spill-dict, ren tekst) hvis meldingen er en invitasjon, ellers (None, tekst)."""
    if not text or "[invite:" not in text:
        return None, text
    head, _, rest = text.partition("[invite:")
    try:
        g = json.loads(rest.rsplit("]", 1)[0])
        return g, head.strip()
    except ValueError:
        return None, text


def join(g, reply_to=None):
    """Bli med: start spillet (hvis det finnes her) og si fra til den som inviterte."""
    import features
    import savegames
    here = next((x for x in all_games() if x["store"] == g.get("store") and str(x["id"]) == str(g.get("id"))), None) \
        or next((x for x in all_games() if x["name"] == g.get("name")), None)
    me = savegames.pc_name()
    if reply_to:
        features.send_to(reply_to, me, f"✅ {me} blir med i {g.get('name')}!" if here else
                         f"😕 {me} har ikke {g.get('name')} installert")
    if here:
        launch(here)
        return True
    return False



