"""Klipp – alt rundt selve opptaket: spilldata og miniatyrbilder per klipp, favoritter, rydding (dager, plass,
NAS), redigering med ffmpeg (klipp til, GIF, kort, lyd, vannmerke, tåke, SDR, montasje, beste fra uka),
statistikk, delingslenker, opptakshelse, AFK-pause, WoW-kamplogg, kontroller-knapper og skjermbilder.
"""
import glob
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import struct
import subprocess
import sys
import threading
import time

IS_WIN = sys.platform == "win32"
THUMBS = os.path.expanduser("~/.cache/systemmonitor/klipp-bilder")
NAS_CACHE = os.path.expanduser("~/.cache/systemmonitor/klipp-nas")
VIDEO = (".mp4",)
IMAGE = (".png", ".jpg", ".gif")
JOBS = {}
_LOCK = threading.Lock()


def C():
    import clips
    return clips


def ffmpeg():
    f = shutil.which("ffmpeg")
    if f:
        return f
    if IS_WIN:
        for p in glob.glob(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\*FFmpeg*\**\ffmpeg.exe"),
                           recursive=True):
            return p
    return None


def run_ff(args, timeout=1800):
    ff = ffmpeg()
    if not ff:
        raise RuntimeError("ffmpeg mangler")
    kw = {"creationflags": 0x08000000} if IS_WIN else {}
    r = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", *args], capture_output=True, text=True,
                       timeout=timeout, **kw)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "ffmpeg feilet").strip().splitlines()[-1][:200])


def duration(path):
    ff = ffmpeg()
    try:
        r = subprocess.run([ff, "-hide_banner", "-i", path], capture_output=True, text=True, timeout=30)
        m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else None
    except (OSError, subprocess.SubprocessError, TypeError):
        return None


# --------------------------------------------------------------------------
# Spilldata, favoritter og miniatyrbilder (19, 9, 18)
# --------------------------------------------------------------------------
def meta_path(path):
    return path + ".json"


def read_meta(path):
    try:
        with open(meta_path(path), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def write_meta(path, info):
    m = read_meta(path)
    m.update(info or {})
    with open(meta_path(path), "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False)


def thumb(path):
    os.makedirs(THUMBS, exist_ok=True)
    t = os.path.join(THUMBS, os.path.basename(path) + ".jpg")
    if os.path.exists(t):
        return t
    try:
        if path.lower().endswith(IMAGE):
            try:                                     # bilder: GdkPixbuf – trenger ikke ffmpeg (Windows har det sjelden)
                import gi
                gi.require_version("GdkPixbuf", "2.0")
                from gi.repository import GdkPixbuf
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 360, -1, True)
                if pb.get_has_alpha():
                    pb = pb.composite_color_simple(pb.get_width(), pb.get_height(), GdkPixbuf.InterpType.BILINEAR,
                                                   255, 64, 0, 0)
                pb.savev(t, "jpeg", ["quality"], ["80"])
                return t
            except Exception:  # noqa: BLE001
                run_ff(["-i", path, "-vf", "scale=360:-2", "-frames:v", "1", t], 60)
        else:
            run_ff(["-ss", "1", "-i", path, "-frames:v", "1", "-vf", "scale=360:-2", "-q:v", "5", t], 60)
        return t
    except Exception:  # noqa: BLE001
        return None


def files():
    """Alle klipp og skjermbilder: [{name, size, t, kind, game, fav, meta, thumb}] nyeste først."""
    d = C().clip_dir()
    out = []
    for f in glob.glob(os.path.join(d, "*")):
        if not f.lower().endswith(VIDEO + IMAGE):
            continue
        try:
            st = os.stat(f)
        except OSError:
            continue
        m = read_meta(f)
        name = os.path.basename(f)
        game = m.get("game") or re.sub(r"\s+\d{4}-\d{2}-\d{2}.*$", "", os.path.splitext(name)[0]) or "Klipp"
        out.append({"name": name, "size": st.st_size, "t": m.get("t") or st.st_mtime,
                    "kind": "image" if f.lower().endswith(IMAGE) else m.get("kind", "clip"), "game": game,
                    "fav": bool(m.get("fav")), "meta": {k: v for k, v in m.items() if k in ("cs2", "wow", "label")},
                    "thumb": os.path.exists(os.path.join(THUMBS, name + ".jpg"))})
    return sorted(out, key=lambda x: -x["t"])


def set_fav(name, on):
    p = C().clip_path(name) or _image_path(name)
    if not p:
        raise ValueError("fant ikke klippet")
    write_meta(p, {"fav": bool(on)})


def _image_path(name):
    if not name or "/" in name or "\\" in name or name.startswith(".") or not name.lower().endswith(IMAGE):
        return None
    p = os.path.join(C().clip_dir(), name)
    return p if os.path.isfile(p) else None


def any_path(name):
    return C().clip_path(name) or _image_path(name)


def delete(name):
    p = any_path(name)
    if not p:
        raise ValueError("fant ikke klippet")
    for x in (p, meta_path(p), os.path.join(THUMBS, name + ".jpg")):
        try:
            os.remove(x)
        except OSError:
            pass


# --------------------------------------------------------------------------
# Etter lagring: kort ned, bekreftelse, rydding og deling (33, 12, 8, 10, 22)
# --------------------------------------------------------------------------
def keep_tail(path, start_before, end_before):
    """Behold bare [slutt-start_before, slutt-end_before] – f.eks. 3 s før første kill til 2 s etter siste."""
    dur = duration(path)
    if not dur:
        return
    a = max(0.0, dur - start_before)
    b = max(a + 1, dur - end_before)
    tmp = path + ".tmp.mp4"
    run_ff(["-ss", f"{a:.2f}", "-to", f"{b:.2f}", "-i", path, "-c", "copy", tmp])
    os.replace(tmp, path)


def confirm(name):
    c = C().load_cfg()
    if c.get("sound"):
        for cmd in (["canberra-gtk-play", "-i", "camera-shutter"],
                    ["paplay", "/usr/share/sounds/freedesktop/stereo/camera-shutter.oga"]):
            if not IS_WIN and shutil.which(cmd[0]):
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                break
        if IS_WIN:
            try:
                import winsound
                winsound.MessageBeep(0x40)
            except Exception:  # noqa: BLE001
                pass
    r = C().INSTANCE
    if r and r.notify:
        r.notify("clip", "🎬 Klipp lagret", name, force=True)


def after_save(path):
    threading.Thread(target=housekeeping, daemon=True).start()
    if C().load_cfg().get("share_nas"):
        threading.Thread(target=lambda: nas_upload(path), daemon=True).start()


def housekeeping():
    """Slett gamle klipp (ikke favoritter), hold under plassgrensen, flytt gamle klipp til NAS-en."""
    c = C().load_cfg()
    items = [x for x in files() if not x["fav"]]
    now = time.time()
    if c.get("nas_days"):
        for x in items:
            if now - x["t"] > c["nas_days"] * 86400:
                p = any_path(x["name"])
                if p and nas_upload(p):
                    delete(x["name"])
        items = [x for x in files() if not x["fav"]]
    if c.get("keep_days"):
        for x in items:
            if now - x["t"] > c["keep_days"] * 86400:
                delete(x["name"])
        items = [x for x in files() if not x["fav"]]
    if c.get("max_gb"):
        total = sum(x["size"] for x in files())
        for x in sorted(items, key=lambda y: y["t"]):
            if total <= c["max_gb"] * 2**30:
                break
            total -= x["size"]
            delete(x["name"])


def _pc():
    try:
        import savegames
        return savegames.pc_name()
    except Exception:  # noqa: BLE001
        return "PC"


def nas_upload(path):
    try:
        import lanupdate as L
        if not L.on_lan():
            return False
        _h, _share, folder = L._split()
        L.smb_mkdir(f"{folder}/Klipp")
        L.smb_mkdir(f"{folder}/Klipp/{_pc()}")
        L._smb(f'cd "Klipp/{_pc()}"; put "{path}" "{os.path.basename(path)}"', 1800)
        return True
    except Exception:  # noqa: BLE001
        return False


def nas_list():
    """Klipp alle PC-ene har lagt på NAS-en: [{pc, name, size}]."""
    out = []
    try:
        import lanupdate as L
        if not L.on_lan():
            return out
        txt = L._smb('cd "Klipp"; ls', 60)
        pcs = [m.group(1).strip() for m in re.finditer(r"^\s+(.+?)\s+D\s+0\s", txt, re.M) if m.group(1).strip() not in (".", "..")]
        for pc in pcs:
            t = L._smb(f'cd "Klipp/{pc}"; ls', 60)
            for m in re.finditer(r"^\s+(.+?\.(?:mp4|png))\s+A?N?\s+(\d+)\s", t, re.M):
                out.append({"pc": pc, "name": m.group(1).strip(), "size": int(m.group(2))})
    except Exception:  # noqa: BLE001
        pass
    return out


def nas_fetch(pc, name):
    """Hent et klipp fra NAS-en til hurtigbufferen (for avspilling i appen)."""
    if not re.fullmatch(r"[^/\\]+", pc or "") or not re.fullmatch(r"[^/\\]+\.(mp4|png)", name or ""):
        raise ValueError("ugyldig navn")
    os.makedirs(NAS_CACHE, exist_ok=True)
    dst = os.path.join(NAS_CACHE, f"{pc}__{name}")
    if not os.path.exists(dst):
        import lanupdate as L
        L._smb(f'cd "Klipp/{pc}"; get "{name}" "{dst}.part"', 1800)
        os.replace(dst + ".part", dst)
    return dst


# --------------------------------------------------------------------------
# Redigering (4, 6, 7, 28, 30, 32, 37, 42) – kjører i bakgrunnen som «jobber»
# --------------------------------------------------------------------------
BLUR = {"chat-venstre": "0:ih*0.55:iw*0.32:ih*0.4", "chat-hoyre": "iw*0.68:ih*0.55:iw*0.32:ih*0.4",
        "topp": "0:0:iw:ih*0.08", "bunn": "0:ih*0.9:iw:ih*0.1"}


def _out(path, suffix, ext=".mp4"):
    base = os.path.splitext(os.path.basename(path))[0]
    return os.path.join(C().clip_dir(), f"{base} – {suffix}{ext}")


def _venc():
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p"]


def export(name, kind, **kw):
    """kind: trim | gif | short | loud | watermark | blur | sdr. Returnerer jobb-id."""
    p = C().clip_path(name)
    if not p:
        raise ValueError("fant ikke klippet")
    if kind not in ("trim", "gif", "short", "loud", "watermark", "blur", "sdr"):
        raise ValueError("ukjent redigering")

    def work():
        if kind == "trim":
            a, b = float(kw["start"]), float(kw["end"])
            if b <= a:
                raise ValueError("slutt må være etter start")
            out = _out(p, "klippet")
            run_ff(["-ss", f"{a:.2f}", "-to", f"{b:.2f}", "-i", p, "-c", "copy", out])
        elif kind == "gif":
            out = _out(p, "GIF", ".gif")
            vf = "fps=15,scale=480:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse"
            run_ff(["-t", str(min(float(kw.get("seconds", 8)), 15)), "-i", p, "-vf", vf, out])
        elif kind == "short":
            out = _out(p, "kort 720p")
            run_ff(["-sseof", f"-{min(float(kw.get('seconds', 15)), 60)}", "-i", p, "-vf", "scale=-2:720", *_venc(),
                    "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out])
        elif kind == "loud":
            out = _out(p, "lyd")
            run_ff(["-i", p, "-c:v", "copy", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "160k", out])
        elif kind == "watermark":
            text = (kw.get("text") or C().load_cfg().get("watermark") or _pc()).replace("'", "").replace(":", " ")[:40]
            out = _out(p, "merket")
            vf = (f"drawtext=text='{text}':x=w-tw-24:y=h-th-24:fontsize=h/28:fontcolor=white@0.85:"
                  "box=1:boxcolor=black@0.35:boxborderw=10")
            run_ff(["-i", p, "-vf", vf, *_venc(), "-c:a", "copy", out])
        elif kind == "blur":
            area = BLUR.get(kw.get("area", "chat-venstre"))
            if not area:
                raise ValueError("ukjent område")
            x, y, w, h = area.split(":")
            ox, oy = x.replace("iw", "W").replace("ih", "H"), y.replace("iw", "W").replace("ih", "H")
            out = _out(p, "tåke")
            fc = (f"[0:v]split[a][b];[b]crop={w}:{h}:{x}:{y},boxblur=lr='min(20,min(w,h)/5)':lp=2[bl];[a][bl]overlay={ox}:{oy}")
            run_ff(["-i", p, "-filter_complex", fc, *_venc(), "-c:a", "copy", out])
        elif kind == "sdr":
            info = subprocess.run([ffmpeg(), "-hide_banner", "-i", p], capture_output=True, text=True).stderr
            if not re.search(r"smpte2084|arib-std-b67|bt2020", info):
                raise ValueError("klippet er allerede SDR (ikke HDR) – ingen endring trengs")
            out = _out(p, "SDR")
            vf = ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,"
                  "zscale=t=bt709:m=bt709:r=tv,format=yuv420p")
            run_ff(["-i", p, "-vf", vf, *_venc(), "-c:a", "copy", out])
        write_meta(out, {**read_meta(p), "kind": kind, "t": time.time(), "fav": False})
        thumb(out)
        return os.path.basename(out)
    return _job(f"{kind}: {name}", work)


def montage(names, music=None, title=None, kind="montasje"):
    """Sett sammen klipp (med tittel og evt. musikk). Ikke takt-synkronisert – musikken legges under."""
    paths = [C().clip_path(n) for n in names]
    paths = [x for x in paths if x]
    if not paths:
        raise ValueError("ingen klipp valgt")
    mp = None
    if music:
        mp = music_path(music)
        if not mp:
            raise ValueError("fant ikke musikken")

    def work():
        d = C().clip_dir()
        out = os.path.join(d, f"{title or 'Montasje'} {time.strftime('%Y-%m-%d %H.%M')}.mp4")
        inputs, parts = [], []
        for i, x in enumerate(paths[:20]):
            inputs += ["-i", x]
            label = os.path.splitext(os.path.basename(x))[0].replace("'", "").replace(":", " ")[:50]
            parts.append(f"[{i}:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,"
                         f"fps=60,drawtext=text='{label}':x=40:y=40:fontsize=36:fontcolor=white:box=1:"
                         f"boxcolor=black@0.4:boxborderw=12:enable='lt(t,3)'[v{i}];[{i}:a]aresample=48000[a{i}]")
        n = len(parts)
        fc = ";".join(parts) + ";" + "".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[v][a]"
        args = [*inputs]
        if mp:
            args += ["-stream_loop", "-1", "-i", mp]
            fc += f";[{n}:a]volume=0.35[m];[a][m]amix=inputs=2:duration=first[ao]"
            amap = "[ao]"
        else:
            amap = "[a]"
        run_ff([*args, "-filter_complex", fc, "-map", "[v]", "-map", amap, *_venc(), "-c:a", "aac", "-b:a", "160k",
                "-movflags", "+faststart", out], 3600)
        write_meta(out, {"kind": kind, "t": time.time(), "game": title or "Montasje"})
        thumb(out)
        return os.path.basename(out)
    return _job(f"{kind} ({len(paths)} klipp)", work)


def weekly():
    """«Beste fra uka»: favoritter og CS2/WoW-høydepunkter fra de siste 7 dagene (høyst 12)."""
    week = [x for x in files() if x["kind"] != "image" and time.time() - x["t"] < 7 * 86400
            and not x["name"].startswith(("Beste fra uka", "Montasje"))]
    best = sorted(week, key=lambda x: (not x["fav"], x["kind"] not in ("highlight", "boss"), -x["t"]))[:12]
    return montage([x["name"] for x in sorted(best, key=lambda x: x["t"])], title="Beste fra uka", kind="weekly")


def music_files():
    from gi.repository import GLib
    d = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_MUSIC) or os.path.expanduser("~/Music")
    out = []
    for ext in ("mp3", "ogg", "flac", "m4a", "wav", "opus"):
        out += glob.glob(os.path.join(d, "**", f"*.{ext}"), recursive=True)
    return [os.path.relpath(x, d) for x in sorted(out)[:300]], d


def music_path(rel):
    lst, d = music_files()
    return os.path.join(d, rel) if rel in lst else None


def _job(title, fn):
    jid = secrets.token_hex(4)
    JOBS[jid] = {"title": title, "state": "kjører", "t": time.time()}

    def run():
        try:
            JOBS[jid].update(state="ferdig", out=fn())
            try:
                import remote_extra
                remote_extra.event("clip", "Ferdig: " + title, JOBS[jid]["out"], "game")
            except Exception:  # noqa: BLE001
                pass
        except Exception as e:  # noqa: BLE001
            JOBS[jid].update(state="feil", error=str(e))
    threading.Thread(target=run, daemon=True).start()
    return jid


# --------------------------------------------------------------------------
# Statistikk og «denne dagen» (21, 20)
# --------------------------------------------------------------------------
def stats():
    fs = [x for x in files() if x["kind"] != "image"]
    per_game, per_week, total = {}, {}, 0
    for x in fs:
        per_game[x["game"]] = per_game.get(x["game"], 0) + 1
        wk = time.strftime("%G-uke %V", time.localtime(x["t"]))
        per_week[wk] = per_week.get(wk, 0) + 1
        total += x["size"]
    maps = {}
    for x in fs:
        mp = (x["meta"].get("cs2") or {}).get("map")
        if mp:
            maps[mp] = maps.get(mp, 0) + 1
    today = time.strftime("%m-%d")
    on_day = [x for x in fs if time.strftime("%m-%d", time.localtime(x["t"])) == today
              and time.localtime(x["t"]).tm_year < time.localtime().tm_year]
    return {"count": len(fs), "size": total, "favs": sum(1 for x in fs if x["fav"]),
            "per_game": sorted(per_game.items(), key=lambda y: -y[1])[:10],
            "per_week": sorted(per_week.items())[-8:], "maps": sorted(maps.items(), key=lambda y: -y[1])[:8],
            "best_week": max(per_week.items(), key=lambda y: y[1]) if per_week else None,
            "on_this_day": on_day[:5]}


# --------------------------------------------------------------------------
# Delingslenke som virker i 24 timer (41) – bare på hjemmenettet og Tailscale
# --------------------------------------------------------------------------
def _secret():
    c = C().load_cfg()
    if not c.get("share_secret"):
        c["share_secret"] = secrets.token_hex(16)
        C().save_cfg(c)
    return c["share_secret"].encode()


def share_token(name, hours=24):
    exp = int(time.time() + hours * 3600)
    sig = hmac.new(_secret(), f"{name}|{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    return f"{exp}.{sig}"


def check_share(name, tok):
    try:
        exp, sig = tok.split(".", 1)
        if int(exp) < time.time():
            return False
        good = hmac.new(_secret(), f"{name}|{exp}".encode(), hashlib.sha256).hexdigest()[:32]
        return hmac.compare_digest(sig, good)
    except (ValueError, AttributeError):
        return False


# --------------------------------------------------------------------------
# Opptakshelse og AFK (40, 15)
# --------------------------------------------------------------------------
_HEALTH = {"t": 0, "sent": {}}


def health_tick(rec, game):
    now = time.time()
    if now - _HEALTH["t"] < 60:
        return
    _HEALTH["t"] = now
    c = C().load_cfg()
    if not c["enabled"] or IS_WIN:
        return
    probs = []
    if (game or not c["only_games"]) and not rec.running() and C().installed():
        probs.append(("stopped", "Opptaket i bakgrunnen har stoppet", rec.error or "Kontrollsenter prøver å starte det igjen"))
    try:
        free = shutil.disk_usage(C().clip_dir() if os.path.isdir(C().clip_dir()) else os.path.expanduser("~")).free
        if free < 10 * 2**30:
            probs.append(("disk", "Lite plass til klipp", f"{free / 2**30:.1f} GB ledig – slett gamle klipp eller slå på rydding"))
    except OSError:
        pass
    for key, title, body in probs:
        if now - _HEALTH["sent"].get(key, 0) > 1800:
            _HEALTH["sent"][key] = now
            try:
                import remote_extra
                remote_extra.event("clip", title, body, "warn")
            except Exception:  # noqa: BLE001
                pass


def idle_seconds():
    """Sekunder siden siste tastetrykk/musebevegelse (KDE/GNOME via ScreenSaver-grensesnittet)."""
    if IS_WIN:
        import ctypes

        class LII(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
        li = LII(ctypes.sizeof(LII), 0)
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(li))
        return (ctypes.windll.kernel32.GetTickCount() - li.dwTime) / 1000
    try:
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        r = bus.call_sync("org.freedesktop.ScreenSaver", "/org/freedesktop/ScreenSaver", "org.freedesktop.ScreenSaver",
                          "GetSessionIdleTime", None, GLib.VariantType("(u)"), 0, 1000, None)
        return r.unpack()[0] / 1000
    except Exception:  # noqa: BLE001
        return 0


# --------------------------------------------------------------------------
# Skjermbilde (38)
# --------------------------------------------------------------------------
def screenshot(game=None):
    d = C().clip_dir()
    os.makedirs(d, exist_ok=True)
    nice = re.sub(r'[\\/:*?"<>|]', "", game or "Skjermbilde").strip() or "Skjermbilde"
    out = os.path.join(d, f"{nice} {time.strftime('%Y-%m-%d %H.%M.%S')}.png")
    if IS_WIN:                                       # Windows' egen skjermkopi – virker uten Game Bar og på skrivebordet
        try:
            import wincapture
            out = out[:-4] + ".jpg"
            wincapture.grab().savev(out, "jpeg", ["quality"], ["90"])
        except Exception as e:  # noqa: BLE001
            return False, f"Skjermbildet feilet: {e}"
    elif shutil.which("spectacle"):
        subprocess.run(["spectacle", "-b", "-n", "-f", "-o", out], capture_output=True, timeout=20)
    elif shutil.which("grim"):
        subprocess.run(["grim", out], capture_output=True, timeout=20)
    if not os.path.exists(out):
        return False, "Fant ikke et verktøy for skjermbilde"
    write_meta(out, {"game": game, "kind": "image", "t": time.time()})
    thumb(out)
    confirm(os.path.basename(out))
    return True, "Skjermbilde lagret"


# --------------------------------------------------------------------------
# WoW: boss-kills og dødsfall fra kamploggen (34, 2) – krever /combatlog i spillet
# --------------------------------------------------------------------------
class WowLog:
    def __init__(self, rec):
        self.rec = rec
        self.f = None
        self.path = None
        self.names = set()

    def _find(self):
        try:
            import gamestats
            logs = []
            for _r, d, _n, _i in gamestats.wow_flavors():
                logs += glob.glob(os.path.join(d, "Logs", "WoWCombatLog*.txt"))
            self.names = {c.get("name") for c in gamestats.wow_stats() if c.get("name")}
        except Exception:  # noqa: BLE001
            logs = []
        logs = [x for x in logs if time.time() - os.path.getmtime(x) < 120]
        return max(logs, key=os.path.getmtime) if logs else None

    def tick(self, game):
        if not game or "warcraft" not in (game or "").lower() and "wow" not in (game or "").lower():
            if self.f:
                self.f.close()
                self.f = None
            return
        if not self.f:
            p = self._find()
            if not p:
                return
            self.f, self.path = open(p, encoding="utf-8", errors="replace"), p
            self.f.seek(0, 2)
        for ln in self.f.readlines()[-500:]:
            if "ENCOUNTER_END" in ln:
                parts = ln.split(",")
                if len(parts) >= 6 and parts[-1].strip() == "1":     # suksess
                    boss = parts[2].strip('"') if len(parts) > 2 else "boss"
                    self.rec.save(label=f"WoW {boss}", kind="boss", meta={"wow": {"boss": boss}})
            elif "UNIT_DIED" in ln and "Player-" in ln:
                m = re.search(r'Player-[^,]+,"([^"-]+)', ln)
                if m and m.group(1) in self.names:
                    self.rec.save(30, label=f"WoW død {m.group(1)}", kind="death", meta={"wow": {"death": m.group(1)}})


# --------------------------------------------------------------------------
# Kontroller: Select + Start (eller Share-knappen) lagrer klipp (27)
# --------------------------------------------------------------------------
class Controller:
    BTN_SELECT, BTN_START, KEY_RECORD = 314, 315, 167

    def __init__(self, cb):
        self.cb = cb
        self.stop = False
        threading.Thread(target=self._win if IS_WIN else self._linux, daemon=True).start()

    def _linux(self):
        import fcntl
        import select
        held, fds = set(), {}
        while not self.stop:
            for dev in glob.glob("/dev/input/event*"):
                if dev in fds:
                    continue
                try:
                    fd = os.open(dev, os.O_RDONLY | os.O_NONBLOCK)
                    buf = bytearray(256)
                    fcntl.ioctl(fd, 0x80ff4506, buf)                   # EVIOCGNAME(256)
                    name = buf.split(b"\0")[0].decode(errors="replace").lower()
                    if any(w in name for w in ("controller", "gamepad", "xbox", "dualsense", "dualshock", "joystick", "8bitdo")):
                        fds[dev] = fd
                    else:
                        os.close(fd)
                        fds[dev] = None
                except OSError:
                    fds[dev] = None
            live = [fd for fd in fds.values() if fd]
            if not live:
                time.sleep(10)
                continue
            r, _w, _x = select.select(live, [], [], 10)
            for fd in r:
                try:
                    data = os.read(fd, 24 * 64)
                except OSError:
                    for k, v in list(fds.items()):
                        if v == fd:
                            fds.pop(k)
                    continue
                for i in range(0, len(data) - 23, 24):
                    _s, _u, typ, code, val = struct.unpack("llHHi", data[i:i + 24])
                    if typ != 1:
                        continue
                    if val:
                        held.add(code)
                    else:
                        held.discard(code)
                    if val == 1 and (code == self.KEY_RECORD or {self.BTN_SELECT, self.BTN_START} <= held):
                        self.cb()

    def _win(self):
        import ctypes

        class GP(ctypes.Structure):
            _fields_ = [("buttons", ctypes.c_ushort), ("lt", ctypes.c_ubyte), ("rt", ctypes.c_ubyte),
                        ("lx", ctypes.c_short), ("ly", ctypes.c_short), ("rx", ctypes.c_short), ("ry", ctypes.c_short)]

        class ST(ctypes.Structure):
            _fields_ = [("packet", ctypes.c_uint), ("gp", GP)]
        try:
            x = ctypes.windll.xinput1_4
        except OSError:
            return
        was = False
        while not self.stop:
            down = False
            for i in range(4):
                st = ST()
                if x.XInputGetState(i, ctypes.byref(st)) == 0 and (st.gp.buttons & 0x30) == 0x30:   # Back + Start
                    down = True
            if down and not was:
                self.cb()
            was = down
            time.sleep(0.05)
