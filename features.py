"""Flere funksjoner for hele appen (PC + Android): sikkerhetskopi av innstillinger, feilrapport, selvtest,
automatisk oppdatering, familie (chat, «Middag!», leggetid, belønning, kalender, ranking), ytelse per spill,
shader-varsel, oppstartsprogrammer, ukjente enheter, sikkerhetssjekk, Steam-tilbud, Hue-lys, prestasjoner og
månedlig Wrapped.
"""
import glob
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.request

from gi.repository import GLib

IS_WIN = sys.platform == "win32"
CONF_DIR = os.path.expanduser("~/.config/systemmonitor")
DATA = os.path.expanduser("~/.local/share/systemmonitor")
FCFG = os.path.join(CONF_DIR, "funksjoner.json")
CHAT = os.path.join(DATA, "chat.json")
KNOWN = os.path.join(DATA, "kjente-enheter.json")
ACH = os.path.join(DATA, "prestasjoner.json")


def cfg():
    try:
        with open(FCFG, encoding="utf-8") as f:
            c = json.load(f)
    except (OSError, ValueError):
        c = {}
    return {"bedtime": {"enabled": False, "weekday": "22:00", "weekend": "23:30"}, "auto_update": False,
            "update_at": "04:00", "wishlist": False, "hue": {}, "deck": [], "bonus": {}, **c}


def save_cfg(c):
    os.makedirs(CONF_DIR, exist_ok=True)
    with open(FCFG, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=1)


def _ev(kind, title, body="", level="info"):
    try:
        import remote_extra
        return remote_extra.event(kind, title, body, level)
    except Exception:  # noqa: BLE001
        return None


def _pc():
    try:
        import savegames
        return savegames.pc_name()
    except Exception:  # noqa: BLE001
        return "PC"


# --------------------------------------------------------------------------
# 2 – sikkerhetskopi av alle innstillinger til NAS-en, og gjenoppretting
# --------------------------------------------------------------------------
def backup_settings():
    import lanupdate as L
    if not L.on_lan():
        raise RuntimeError("NAS-en svarer ikke")
    buf = os.path.join(tempfile.mkdtemp(), f"{_pc()} {time.strftime('%Y-%m-%d %H.%M')}.tar.gz")
    with tarfile.open(buf, "w:gz") as t:
        for f in glob.glob(os.path.join(CONF_DIR, "*")):
            if os.path.isfile(f) and not f.endswith((".tmp", ".bak")):
                t.add(f, arcname=os.path.basename(f))
    _h, _s, folder = L._split()
    L.smb_mkdir(f"{folder}/Innstillinger")
    L._smb(f'cd "Innstillinger"; put "{buf}" "{os.path.basename(buf)}"', 120)
    shutil.rmtree(os.path.dirname(buf), ignore_errors=True)
    _ev("backup", "Innstillingene er sikkerhetskopiert", os.path.basename(buf))
    return os.path.basename(buf)


def _nas_ls(sub, suffix):
    import lanupdate as L
    try:
        txt = L._smb(f'cd "{sub}"; ls', 60)
    except Exception:  # noqa: BLE001
        return []
    out = set()
    for ln in txt.splitlines():
        m = re.match(r"^\s+(.+?)\s+[ADHNRS]+\s+\d+\s", ln)
        name = m.group(1) if m else (ln.strip() if IS_WIN else "")
        if name.endswith(suffix):
            out.add(name)
    return sorted(out)


def list_backups():
    import lanupdate as L
    if not L.on_lan():
        return []
    return sorted(_nas_ls("Innstillinger", ".tar.gz"), reverse=True)


def restore_settings(name):
    if not re.fullmatch(r"[^/\\]+\.tar\.gz", name or ""):
        raise ValueError("ugyldig navn")
    import lanupdate as L
    d = tempfile.mkdtemp()
    try:
        L._smb(f'cd "Innstillinger"; get "{name}" "{d}/b.tar.gz"', 120)
        os.makedirs(CONF_DIR, exist_ok=True)
        # ta vare på dagens innstillinger først
        with tarfile.open(os.path.join(CONF_DIR, "før-gjenoppretting.tar.gz"), "w:gz") as t:
            for f in glob.glob(os.path.join(CONF_DIR, "*.json")):
                t.add(f, arcname=os.path.basename(f))
        with tarfile.open(f"{d}/b.tar.gz") as t:
            for m in t.getmembers():
                if m.isfile() and "/" not in m.name and not m.name.startswith("."):
                    t.extract(m, CONF_DIR, filter="data")
    finally:
        shutil.rmtree(d, ignore_errors=True)
    _ev("backup", "Innstillinger gjenopprettet", name + " – start Kontrollsenter på nytt", "warn")


# --------------------------------------------------------------------------
# 3 – feilrapport med ett trykk, 4 – selvtest
# --------------------------------------------------------------------------
def send_report(note=""):
    import diagnose
    if note:
        _ev("report", "Feilrapport fra appen", note[:300], "warn")
    text = diagnose.report()
    if note:
        text = f"=== Melding fra appen ===\n{note}\n\n" + text
    return diagnose.upload(text)


def selftest(win=None):
    res = []
    try:
        import remote
        res.append(("Fjernstyring", bool(remote.INSTANCE and remote.INSTANCE.running) or not remote.load_cfg()["enabled"]))
    except Exception:  # noqa: BLE001
        res.append(("Fjernstyring", False))
    try:
        import clips
        c = clips.load_cfg()
        r = clips.INSTANCE
        res.append(("Hurtigtast for klipp", not c["enabled"] or bool(r and r.hotkey and r.hotkey.ok)))
    except Exception:  # noqa: BLE001
        res.append(("Hurtigtast for klipp", False))
    if win is not None and getattr(win, "fans", None) and win.fans.rows:
        res.append(("Viftestyring", bool(win.fans.ready())))
    bad = [n for n, ok in res if not ok]
    if bad:
        _ev("selftest", "Selvtest: noe virker ikke", ", ".join(bad), "warn")
    return [{"name": n, "ok": ok} for n, ok in res]


# --------------------------------------------------------------------------
# 1 – automatisk oppdatering om natten, med tilbakerulling hvis den nye versjonen krasjer
# --------------------------------------------------------------------------
ROLLBACK = os.path.join(DATA, "oppdatering-sjekk.json")


def auto_update_tick():
    c = cfg()
    if not c["auto_update"] or IS_WIN:
        return
    now = time.strftime("%H:%M")
    if now != c["update_at"] or time.time() - c.get("_last_upd", 0) < 3600:
        return
    c["_last_upd"] = time.time()
    save_cfg(c)
    import lanupdate as L
    import tools
    _st, new = L.check()
    if not new:
        return
    ok, msg = L.apply_update(tools.PACKAGE_FILES)
    if ok:
        with open(ROLLBACK, "w") as f:
            json.dump({"from": L.local_version(), "t": time.time()}, f)
        _ev("update", f"Oppdatert til {new} i natt", "Kontrollsenter startes på nytt", "info")
        if WIN is not None:
            GLib.idle_add(lambda: (WIN.restart_app(), False)[1])


def check_rollback():
    """Ved oppstart: hvis forrige oppstart etter en nattlig oppdatering krasjet, rull tilbake."""
    try:
        with open(ROLLBACK) as f:
            st = json.load(f)
    except (OSError, ValueError):
        return
    st["starts"] = st.get("starts", 0) + 1
    if st["starts"] >= 3:                                  # krasjet to ganger på rad etter oppdateringen
        try:
            import lanupdate as L
            backup = getattr(L, "BACKUP", None)
            if backup and os.path.exists(backup):
                with tarfile.open(backup) as t:
                    t.extractall(L.APP_DIR, filter="data")
                _ev("update", "Oppdateringen ble rullet tilbake", "Den nye versjonen startet ikke", "error")
        finally:
            os.remove(ROLLBACK)
        return
    with open(ROLLBACK, "w") as f:
        json.dump(st, f)

    def ok():                                              # kjørte i 2 min uten krasj → godkjent
        try:
            os.remove(ROLLBACK)
        except OSError:
            pass
        return False
    GLib.timeout_add_seconds(120, ok)


# --------------------------------------------------------------------------
# 24, 12 – chat og «Middag!» (vises over spillet som varsel med lyd)
# --------------------------------------------------------------------------
def chat_list(limit=100):
    try:
        with open(CHAT, encoding="utf-8") as f:
            return json.load(f)[-limit:]
    except (OSError, ValueError):
        return []


def chat_send(frm, text, notify=None, urgent=False):
    text = str(text or "").strip()[:500]
    if not text:
        raise ValueError("tom melding")
    msgs = chat_list(500)
    msgs.append({"t": time.time(), "from": str(frm)[:40], "text": text, "urgent": bool(urgent)})
    os.makedirs(DATA, exist_ok=True)
    with open(CHAT, "w", encoding="utf-8") as f:
        json.dump(msgs[-500:], f, ensure_ascii=False)
    title = ("📣 " if urgent else "💬 ") + str(frm)[:40]
    if notify:
        GLib.idle_add(lambda: (notify("chat", title, text, force=True), False)[1])
    if urgent:
        for snd in ("/usr/share/sounds/freedesktop/stereo/bell.oga", "/usr/share/sounds/freedesktop/stereo/complete.oga"):
            if not IS_WIN and os.path.exists(snd) and shutil.which("paplay"):
                subprocess.Popen(["paplay", snd])
                break
        if IS_WIN:
            try:
                import winsound
                winsound.MessageBeep(0x30)
            except Exception:  # noqa: BLE001
                pass
    _ev("chat", title, text, "game" if urgent else "info")


def _safe(name):
    return re.sub(r"[^\w.-]", "_", str(name))[:40]


def nas_send(target, frm, text, urgent=False):
    """Legg en melding til en annen PC i postkassen på NAS-en. Den henter den innen et minutt."""
    import lanupdate as L
    if not L.on_lan():
        raise RuntimeError("NAS-en svarer ikke – meldingen kom ikke fram")
    d = tempfile.mkdtemp()
    try:
        f = os.path.join(d, f"{_safe(target)}__{int(time.time() * 1000)}.json")
        with open(f, "w", encoding="utf-8") as fh:
            json.dump({"from": str(frm)[:40], "text": str(text)[:500], "urgent": bool(urgent), "t": time.time()}, fh,
                      ensure_ascii=False)
        _h, _s, folder = L._split()
        L.smb_mkdir(f"{folder}/Meldinger")
        L._smb(f'cd "Meldinger"; put "{f}" "{os.path.basename(f)}"', 60)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def send_to(target, frm, text, notify=None, urgent=False):
    """target: None/denne PC-en, et PC-navn, eller «*» for alle PC-ene."""
    me = _pc()
    if not target or target == me:
        return chat_send(frm, text, notify, urgent)
    targets = [target]
    if target == "*":
        import homepcs
        targets = [p["name"] for p in (homepcs.fetch() or []) if p.get("name") and p["name"] != me]
        chat_send(frm, text, notify, urgent)
    for t in targets:
        nas_send(t, frm, text, urgent)


def mailbox_tick(notify):
    import lanupdate as L
    if not L.on_lan():
        return
    mine = [n for n in _nas_ls("Meldinger", ".json") if n.startswith(_safe(_pc()) + "__")]
    if not mine:
        return
    d = tempfile.mkdtemp()
    try:
        for n in mine:
            try:
                L._smb(f'cd "Meldinger"; get "{n}" "{d}/m.json"; del "{n}"', 60)
                with open(f"{d}/m.json", encoding="utf-8") as fh:
                    m = json.load(fh)
                chat_send(m.get("from", "?"), m.get("text", ""), notify, bool(m.get("urgent")))
            except Exception:  # noqa: BLE001
                continue
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --------------------------------------------------------------------------
# 13 – leggetid, 11 – belønning (ekstra spilletid i dag)
# --------------------------------------------------------------------------
def bedtime_tick(notify):
    b = cfg()["bedtime"]
    if not b.get("enabled"):
        return
    wd = time.localtime().tm_wday
    when = b["weekend"] if wd in (4, 5) else b["weekday"]              # fredag og lørdag = helg-kveld
    try:
        hh, mm = map(int, when.split(":"))
    except ValueError:
        return
    now = time.localtime()
    mins = (hh * 60 + mm) - (now.tm_hour * 60 + now.tm_min)
    key = time.strftime("%Y-%m-%d")
    st = bedtime_tick.__dict__.setdefault("sent", {})
    if mins == 10 and st.get(key) != 10:
        st[key] = 10
        notify("bedtime", "Leggetid om 10 minutter", f"PC-en slås av kl. {when}", force=True)
        _ev("bedtime", "Leggetid om 10 minutter", when, "warn")
    elif mins == 0 and st.get(key) != 0:
        st[key] = 0
        _ev("bedtime", "Leggetid – PC-en slås av", when, "warn")
        import remote
        remote._system("shutdown")


def give_bonus(minutes):
    if not 5 <= int(minutes) <= 240:
        raise ValueError("ugyldig antall minutter")
    c = cfg()
    key = time.strftime("%Y-%m-%d")
    c["bonus"] = {key: c["bonus"].get(key, 0) + int(minutes)}
    save_cfg(c)
    _ev("playtime", f"{minutes} min ekstra spilletid i dag", "Belønning fra appen", "game")


def bonus_today():
    return cfg()["bonus"].get(time.strftime("%Y-%m-%d"), 0)


# --------------------------------------------------------------------------
# 10, 36 – familiekalender og ranking (fra statusen alle PC-ene deler på NAS-en)
# --------------------------------------------------------------------------
def family():
    import homepcs
    pcs = homepcs.fetch() or []
    out = []
    for p in pcs:
        out.append({"name": p.get("name"), "today": p.get("play_today", 0), "week": p.get("play_week", {}),
                    "kd": p.get("cs2_kd"), "wow_levels": p.get("wow_levels"), "cpu_t": p.get("cpu_t"),
                    "game": p.get("game"), "time": p.get("time"), "off": p.get("off"),
                    "watch": bool(p.get("watch")) and time.time() - (p.get("time") or 0) < 900})
    rank = {"Mest spilt i dag": sorted(((x["name"], round(x["today"] / 60)) for x in out), key=lambda y: -y[1]),
            "Høyest CS2 K/D": sorted(((x["name"], x["kd"]) for x in out if x["kd"]), key=lambda y: -y[1]),
            "Flest WoW-levels": sorted(((x["name"], x["wow_levels"]) for x in out if x["wow_levels"]), key=lambda y: -y[1]),
            "Kaldeste CPU": sorted(((x["name"], x["cpu_t"]) for x in out if x["cpu_t"]), key=lambda y: y[1])}
    return {"pcs": out, "ranking": rank}


def share_fields():
    """Ekstra felt i statusen som deles med de andre PC-ene (spilletid, CS2 K/D, WoW-levels)."""
    out = {}
    try:
        import remote_extra as X
        pt = X.playtime_summary(7)
        out["play_today"] = pt["days"][-1]["total"]
        out["play_week"] = dict(pt["week"][:8])
    except Exception:  # noqa: BLE001
        pass
    try:
        import gamestats
        for acc in gamestats.snapshot().get("accounts", [])[:1]:
            for g in acc["games"]:
                if g["appid"] == "730":
                    kd = dict(g["highlights"]).get("K/D")
                    out["cs2_kd"] = float(kd) if kd not in (None, "–") else None
        out["wow_levels"] = sum(int(c.get("level") or 0) for c in gamestats.wow_stats())
    except Exception:  # noqa: BLE001
        pass
    return out


# --------------------------------------------------------------------------
# 5 – ytelse per spill (fra spilløktene)
# --------------------------------------------------------------------------
def perf_per_game():
    import games_auto
    per = {}
    for s in games_auto.load_sessions():
        e = per.setdefault(s.get("name") or "?", {"sessions": 0, "minutes": 0, "fps": [], "low": [], "cpu": [], "gpu": [],
                                                    "kr": 0.0, "last": 0})
        e["sessions"] += 1
        e["minutes"] += s.get("minutes") or 0
        for k, src in (("fps", "fps"), ("low", "low"), ("cpu", "max_cpu"), ("gpu", "max_gpu")):
            if s.get(src):
                e[k].append(s[src])
        e["kr"] += s.get("kr") or 0
        e["last"] = max(e["last"], s.get("start") or 0)
    avg = lambda v: round(sum(v) / len(v)) if v else None  # noqa: E731
    return sorted(({"game": g, "sessions": e["sessions"], "hours": round(e["minutes"] / 60, 1), "fps": avg(e["fps"]),
                    "low": avg(e["low"]), "cpu": max(e["cpu"]) if e["cpu"] else None,
                    "gpu": max(e["gpu"]) if e["gpu"] else None, "kr": round(e["kr"], 2), "last": e["last"],
                    "trend": e["fps"][-10:]} for g, e in per.items()), key=lambda x: -x["last"])


# --------------------------------------------------------------------------
# 8 – Steam lager shadere, 7 – skjermkortdriver
# --------------------------------------------------------------------------
def shader_tick():
    if IS_WIN:
        return
    busy = False
    for d in glob.glob("/proc/[0-9]*/comm"):
        try:
            if open(d).read().strip() == "fossilize_repla":
                busy = True
                break
        except OSError:
            continue
    was = shader_tick.__dict__.get("busy", False)
    if busy and not was:
        _ev("shader", "Steam lager shadere", "Spill kan hakke til det er ferdig", "info")
    elif was and not busy:
        _ev("shader", "Steam er ferdig med shaderne", "", "info")
    shader_tick.busy = busy


def driver_info():
    out = {}
    nv = shutil.which("nvidia-smi")
    if nv:
        try:
            r = subprocess.run([nv, "--query-gpu=name,driver_version", "--format=csv,noheader"], capture_output=True,
                               text=True, timeout=10)
            n, v = (r.stdout.strip().splitlines() or [","])[0].split(",")[:2]
            out = {"gpu": n.strip(), "driver": v.strip(), "vendor": "NVIDIA",
                   "where": "Oppdateres med systemet (Bazzite)" if not IS_WIN else "NVIDIA-appen / GeForce Experience"}
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    return out


# --------------------------------------------------------------------------
# 9 – oppstartsprogrammer
# --------------------------------------------------------------------------
def startup_list():
    out = []
    if IS_WIN:
        import winreg
        for root, name in ((winreg.HKEY_CURRENT_USER, "HKCU"),):
            try:
                with winreg.OpenKey(root, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
                    i = 0
                    while True:
                        try:
                            n, v, _t = winreg.EnumValue(k, i)
                        except OSError:
                            break
                        out.append({"id": n, "name": n, "on": True, "cmd": str(v)[:120]})
                        i += 1
            except OSError:
                pass
        return out
    for f in sorted(glob.glob(os.path.expanduser("~/.config/autostart/*.desktop"))):
        txt = open(f, encoding="utf-8", errors="replace").read()
        name = (re.search(r"^Name=(.*)$", txt, re.M) or re.search(r"^Exec=(\S+)", txt, re.M))
        hidden = re.search(r"^(Hidden|X-GNOME-Autostart-enabled)=(true|false)$", txt, re.M)
        on = not (hidden and ((hidden.group(1) == "Hidden" and hidden.group(2) == "true") or
                              (hidden.group(1) != "Hidden" and hidden.group(2) == "false")))
        out.append({"id": os.path.basename(f), "name": name.group(1) if name else os.path.basename(f), "on": on})
    return out


def startup_set(sid, on):
    if IS_WIN:
        raise RuntimeError("på Windows slås oppstartsprogrammer av i Oppgavebehandling → Oppstart")
    f = os.path.expanduser(f"~/.config/autostart/{sid}")
    if "/" in sid or not os.path.isfile(f):
        raise ValueError("finnes ikke")
    txt = open(f, encoding="utf-8").read()
    txt = re.sub(r"^Hidden=.*\n?", "", txt, flags=re.M)
    if not on:
        txt = txt.rstrip("\n") + "\nHidden=true\n"
    open(f, "w", encoding="utf-8").write(txt)


# --------------------------------------------------------------------------
# 17 – ukjente enheter på hjemmenettet, 18 – sikkerhetssjekk
# --------------------------------------------------------------------------
def lan_devices():
    devs = {}
    if IS_WIN:
        import winsupport as WS
        _c, out = WS.run(["arp", "-a"], 15)
        for m in re.finditer(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-f]{2}(?:-[0-9a-f]{2}){5})\s+dynamic", out, re.I):
            devs[m.group(2).replace("-", ":").lower()] = m.group(1)
    else:
        try:
            out = subprocess.run(["ip", "neigh"], capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.SubprocessError):
            out = ""
        for m in re.finditer(r"^(\d+\.\d+\.\d+\.\d+) .*lladdr ([0-9a-f:]{17})", out, re.M):
            devs[m.group(2).lower()] = m.group(1)
    known = _known()
    return [{"mac": mac, "ip": ip, "name": known.get(mac, {}).get("name", ""), "known": mac in known,
             "first": known.get(mac, {}).get("first")} for mac, ip in sorted(devs.items(), key=lambda x: x[1])]


def _known():
    try:
        with open(KNOWN, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def lan_tick():
    known = _known()
    first_run = not known
    changed = False
    for d in lan_devices():
        if d["mac"] not in known:
            known[d["mac"]] = {"first": time.time(), "name": ""}
            changed = True
            if not first_run:
                _ev("lan", "Ny enhet på hjemmenettet", f"{d['ip']} ({d['mac']})", "warn")
    if changed:
        os.makedirs(DATA, exist_ok=True)
        with open(KNOWN, "w", encoding="utf-8") as f:
            json.dump(known, f)


def name_device(mac, name):
    k = _known()
    if mac not in k:
        raise ValueError("ukjent enhet")
    k[mac]["name"] = str(name)[:40]
    with open(KNOWN, "w", encoding="utf-8") as f:
        json.dump(k, f)


def security():
    items = []
    try:
        import psutil
        ports = sorted({(c.laddr.port, c.pid) for c in psutil.net_connections("inet")
                        if c.status == "LISTEN" and c.laddr and c.laddr.ip not in ("127.0.0.1", "::1")})
        names = []
        for port, pid in ports:
            try:
                names.append(f"{port} ({psutil.Process(pid).name()})" if pid else str(port))
            except Exception:  # noqa: BLE001
                names.append(str(port))
        items.append({"title": "Åpne porter mot hjemmenettet", "level": "warn" if len(ports) > 12 else "ok",
                      "detail": ", ".join(names[:30]) or "ingen"})
    except Exception as e:  # noqa: BLE001
        items.append({"title": "Åpne porter", "level": "warn", "detail": str(e)})
    if not IS_WIN:
        try:
            r = subprocess.run(["firewall-cmd", "--state"], capture_output=True, text=True, timeout=10)
            items.append({"title": "Brannmur", "level": "ok" if "running" in r.stdout else "warn",
                          "detail": r.stdout.strip() or r.stderr.strip()})
        except (OSError, subprocess.SubprocessError):
            pass
    unknown = [d for d in lan_devices() if not d["name"]]
    items.append({"title": "Enheter på hjemmenettet uten navn", "level": "ok" if len(unknown) < 15 else "warn",
                  "detail": f"{len(unknown)} enheter – gi dem navn i appen (Verktøy → Hjemmenett)"})
    return items


# --------------------------------------------------------------------------
# 30 – tilbud på ønskelisten (Steam, offentlig ønskeliste)
# --------------------------------------------------------------------------
def wishlist_check():
    try:
        import games
        import vdf
        users = vdf.get(vdf.load(os.path.join(str(games.STEAM), "config/loginusers.vdf")), "users") or {}
    except Exception:  # noqa: BLE001
        return []
    out = []
    for sid in list(users)[:3]:
        url = f"https://api.steampowered.com/IWishlistService/GetWishlist/v1/?steamid={sid}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Kontrollsenter"})
            items = json.loads(urllib.request.urlopen(req, timeout=15).read()).get("response", {}).get("items", [])
        except Exception:  # noqa: BLE001
            continue
        ids = [str(i["appid"]) for i in items][:60]
        for chunk in (ids[i:i + 20] for i in range(0, len(ids), 20)):
            try:
                u = ("https://store.steampowered.com/api/appdetails?filters=price_overview&cc=no&appids="
                     + ",".join(chunk))           # flere appid-er virker bare med price_overview
                det = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Kontrollsenter"}),
                                                        timeout=20).read())
            except Exception:  # noqa: BLE001
                continue
            for aid, d in det.items():
                data = (d or {}).get("data")
                p = (data.get("price_overview") or {}) if isinstance(data, dict) else {}
                if p.get("discount_percent"):
                    out.append({"appid": aid, "name": _app_name(aid), "pct": p["discount_percent"],
                                "price": p.get("final_formatted")})
    return sorted(out, key=lambda x: -x["pct"])


def _app_name(aid):
    try:
        import games_auto
        n = games_auto._name(aid)
        if n and not str(n).isdigit() and not str(n).startswith("Spill "):
            return n
    except Exception:  # noqa: BLE001
        pass
    try:
        u = f"https://store.steampowered.com/api/appdetails?filters=basic&appids={aid}"
        d = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Kontrollsenter"}),
                                              timeout=15).read())
        return d[str(aid)]["data"]["name"]
    except Exception:  # noqa: BLE001
        return f"Spill {aid}"


def wishlist_tick():
    c = cfg()
    if not c["wishlist"] or time.time() - c.get("_wl", 0) < 12 * 3600:
        return
    c["_wl"] = time.time()
    save_cfg(c)
    seen = set(c.get("_wl_seen", []))
    sales = wishlist_check()
    for s in sales:
        if f"{s['appid']}:{s['pct']}" not in seen:
            _ev("steam", f"Tilbud: {s['name']} −{s['pct']} %", s.get("price") or "", "game")
            seen.add(f"{s['appid']}:{s['pct']}")
    c = cfg()
    c["_wl_seen"] = sorted(seen)[-300:]
    save_cfg(c)


# --------------------------------------------------------------------------
# 14 – Philips Hue (lokalt API): koble til broen, styr lys, følg spillmodus og klipp
# --------------------------------------------------------------------------
def hue_find():
    for d in lan_devices():
        if d["mac"].startswith(("00:17:88", "ec:b5:fa")):
            return d["ip"]
    return None


def _hue(path, body=None, method=None):
    h = cfg()["hue"]
    ip, user = h.get("ip"), h.get("user")
    if not ip or not user:
        raise RuntimeError("Hue er ikke koblet til ennå")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://{ip}/api/{user}/{path}", data=data, method=method or ("PUT" if data else "GET"))
    return json.loads(urllib.request.urlopen(req, timeout=5).read())


def hue_pair():
    ip = cfg()["hue"].get("ip") or hue_find()
    if not ip:
        raise RuntimeError("fant ingen Hue-bro på hjemmenettet")
    req = urllib.request.Request(f"http://{ip}/api", data=json.dumps({"devicetype": "kontrollsenter#pc"}).encode())
    r = json.loads(urllib.request.urlopen(req, timeout=5).read())
    if r and "success" in r[0]:
        c = cfg()
        c["hue"] = {"ip": ip, "user": r[0]["success"]["username"]}
        save_cfg(c)
        return True
    raise RuntimeError("Trykk på den runde knappen på Hue-broen, og prøv igjen innen 30 sekunder")


def hue_lights():
    try:
        return [{"id": k, "name": v.get("name"), "on": v.get("state", {}).get("on")} for k, v in _hue("lights").items()]
    except Exception:  # noqa: BLE001
        return []


def hue_set(on=None, color=None, ids=None):
    body = {}
    if on is not None:
        body["on"] = bool(on)
    if color:
        r, g, b = (int(color.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4))
        X = r * 0.649926 + g * 0.103455 + b * 0.197109
        Y = r * 0.234327 + g * 0.743075 + b * 0.022598
        Z = g * 0.053077 + b * 1.035763
        s = X + Y + Z or 1
        body.update({"xy": [round(X / s, 4), round(Y / s, 4)], "bri": 254, "on": True})
    for i in ids or [x["id"] for x in hue_lights()]:
        _hue(f"lights/{i}/state", body)


# --------------------------------------------------------------------------
# 34 – prestasjoner, 35 – månedlig Wrapped
# --------------------------------------------------------------------------
def achievements():
    got = {}
    try:
        with open(ACH, encoding="utf-8") as f:
            got = json.load(f)
    except (OSError, ValueError):
        pass
    checks = []
    try:
        import clipx
        n = len([x for x in clipx.files() if x["kind"] != "image"])
        checks += [("clips10", "🎬 10 klipp", n >= 10), ("clips100", "🎬 100 klipp", n >= 100)]
    except Exception:  # noqa: BLE001
        pass
    try:
        import remote_extra as X
        pt = X.playtime_summary(30)
        total = sum(d["total"] for d in pt["days"])
        checks += [("play10", "🎮 10 timer spilt på en måned", total >= 36000),
                   ("play50", "🎮 50 timer spilt på en måned", total >= 180000)]
    except Exception:  # noqa: BLE001
        pass
    try:
        import psutil
        up = time.time() - psutil.boot_time()
        checks += [("up24", "⏱️ 24 timer uten omstart", up >= 86400), ("up7d", "⏱️ En uke uten omstart", up >= 604800)]
    except Exception:  # noqa: BLE001
        pass
    try:
        import gamestats
        cs = next((g for a in gamestats.snapshot().get("accounts", []) for g in a["games"] if g["appid"] == "730"), None)
        hs = dict(cs["highlights"]).get("Headshot", "0").split()[0].replace(",", ".") if cs else "0"
        checks += [("hs40", "🎯 Over 40 % headshot i CS2", float(hs or 0) >= 40)]
    except Exception:  # noqa: BLE001
        pass
    for k, name, ok in checks:
        if ok and k not in got:
            got[k] = time.time()
            _ev("achievement", "Prestasjon låst opp: " + name, "", "game")
    os.makedirs(DATA, exist_ok=True)
    with open(ACH, "w", encoding="utf-8") as f:
        json.dump(got, f)
    return [{"id": k, "name": n, "done": k in got, "t": got.get(k)} for k, n, _ok in checks]


def wrapped(month=None):
    month = month or time.strftime("%Y-%m")
    out = {"month": month}
    try:
        import remote_extra as X
        data = X._jload(X.PLAYTIME, {})
        per = {}
        for day, g in data.items():
            if day.startswith(month):
                for k, v in g.items():
                    per[k] = per.get(k, 0) + v
        out["hours"] = round(sum(per.values()) / 3600, 1)
        out["top"] = sorted(((k, round(v / 3600, 1)) for k, v in per.items()), key=lambda y: -y[1])[:5]
    except Exception:  # noqa: BLE001
        pass
    try:
        import clipx
        cl = [x for x in clipx.files() if time.strftime("%Y-%m", time.localtime(x["t"])) == month and x["kind"] != "image"]
        out["clips"] = len(cl)
        best = sorted(cl, key=lambda x: (not x["fav"], x["kind"] != "highlight", -x["t"]))
        out["best_clip"] = best[0]["name"] if best else None
    except Exception:  # noqa: BLE001
        pass
    try:
        import power
        log = power.EnergyLog()
        wh = sum(log._get(d)[0] for d in log.days if d.startswith(month))
        out["kwh"] = round(wh / 1000, 1)
        out["kr"] = round(wh / 1000 * power.load()["price"], 2)
    except Exception:  # noqa: BLE001
        pass
    try:
        import games_auto
        ss = [s for s in games_auto.load_sessions() if time.strftime("%Y-%m", time.localtime(s.get("start", 0))) == month]
        out["sessions"] = len(ss)
        out["hottest"] = max((s.get("max_cpu") or 0 for s in ss), default=None)
    except Exception:  # noqa: BLE001
        pass
    return out


# --------------------------------------------------------------------------
# Bakgrunn (kalles hvert sekund; tunge ting sjeldnere)
# --------------------------------------------------------------------------
_T = {}
WIN = None


def tick(notify, win=None):
    global WIN
    WIN = win
    now = time.time()

    def every(key, secs):
        if now - _T.get(key, 0) >= secs:
            _T[key] = now
            return True
        return False
    try:
        if every("bed", 30):
            bedtime_tick(notify)
        if every("upd", 50):
            auto_update_tick()
        if every("shader", 20):
            shader_tick()
        if every("stream", 60):
            def _wd():
                try:
                    import streaming
                    streaming.watchdog()
                except Exception:  # noqa: BLE001
                    pass
            threading.Thread(target=_wd, daemon=True).start()
        if every("mail", 60):
            threading.Thread(target=mailbox_tick, args=(notify,), daemon=True).start()
        if every("lan", 600):
            threading.Thread(target=lan_tick, daemon=True).start()
        if every("wish", 3600):
            threading.Thread(target=wishlist_tick, daemon=True).start()
        if every("ach", 1800):
            threading.Thread(target=achievements, daemon=True).start()
        if every("self", 10 ** 9) and win is not None:          # én gang, 90 s etter oppstart
            GLib.timeout_add_seconds(90, lambda: (threading.Thread(target=selftest, args=(win,), daemon=True).start(),
                                                  False)[1])
    except Exception:  # noqa: BLE001
        pass
