"""Familie og trygghet: nettfilter (familie-DNS), leksetid og meldinger rett i spillet.

Nettfilter  : DNS som blokkerer voksen-, gambling- og skadelige sider (Cloudflare Family, CleanBrowsing,
              AdGuard Family). Linux: NetworkManager (alle aktive kablede/trådløse tilkoblinger). Windows: alle
              aktive nettverkskort (én administratorgodkjenning). Merk: nettlesere med «sikker DNS» (DoH) slått på
              kan gå forbi – slå det av i nettleseren for full effekt.
Leksetid    : på valgte dager og klokkeslett lukkes spill (2 min varsel) – unntatt når «Ferdig med lekser» er
              godkjent i dag.
I spillet   : korte meldinger («5 minutter igjen», «Leggetid», «Leksetid») vises i MangoHud-overlayet (Linux).
              På Windows vises de som varsel over spillet.
"""
import os
import re
import subprocess
import sys
import threading
import time

IS_WIN = sys.platform == "win32"
PROVIDERS = {
    "cloudflare": ("Cloudflare Family", ["1.1.1.3", "1.0.0.3"], ["2606:4700:4700::1113", "2606:4700:4700::1003"]),
    "cleanbrowsing": ("CleanBrowsing Family", ["185.228.168.168", "185.228.169.168"],
                      ["2a0d:2a00:1::", "2a0d:2a00:2::"]),
    "adguard": ("AdGuard Family", ["94.140.14.15", "94.140.15.16"], ["2a10:50c0::bad1:ff", "2a10:50c0::bad2:ff"]),
}


def _run(cmd, t=20):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=t,
                           **({"creationflags": 0x08000000} if IS_WIN else {}))
        return r.returncode, r.stdout + r.stderr
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


def _fcfg():
    import features
    return features.cfg()


def _fsave(c):
    import features
    features.save_cfg(c)


# ==========================================================================
# Nettfilter
# ==========================================================================
def _nm_conns():
    code, out = _run(["nmcli", "-t", "-f", "UUID,TYPE,DEVICE", "con", "show", "--active"], 10)
    res = []
    for ln in out.splitlines():
        p = ln.split(":")
        if len(p) >= 3 and p[1] in ("802-3-ethernet", "802-11-wireless"):
            res.append((p[0], p[2]))
    return res


def dns_state():
    """Valgt filter (nøkkel eller None) – det som faktisk er satt på PC-en."""
    if IS_WIN:
        _c, out = _run(["powershell", "-NoProfile", "-Command",
                        "(Get-DnsClientServerAddress -AddressFamily IPv4 | Where-Object {$_.ServerAddresses}).ServerAddresses"
                        " -join ','"], 20)
        servers = set(out.strip().split(","))
    else:
        servers = set()
        for uuid, _dev in _nm_conns():
            _c, out = _run(["nmcli", "-g", "ipv4.dns", "con", "show", uuid], 10)
            servers |= set(x.strip() for x in re.split(r"[,\s|]+", out) if x.strip())
    for k, (_n, v4, _v6) in PROVIDERS.items():
        if set(v4) <= servers:
            return k
    return None


def set_dns(provider):
    """provider = nøkkel i PROVIDERS, eller None for vanlig DNS fra ruteren."""
    if provider is not None and provider not in PROVIDERS:
        raise ValueError("ukjent filter")
    if IS_WIN:
        if provider:
            v4 = ",".join(f"'{x}'" for x in PROVIDERS[provider][1])
            cmd = (f"Get-NetAdapter -Physical | Where-Object Status -eq 'Up' | "
                   f"Set-DnsClientServerAddress -ServerAddresses @({v4})")
        else:
            cmd = "Get-NetAdapter -Physical | Where-Object Status -eq 'Up' | Set-DnsClientServerAddress -ResetServerAddresses"
        ps = (f"Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList "
              f"'-NoProfile','-Command',\"{cmd}; Clear-DnsClientCache\"")
        code, out = _run(["powershell", "-NoProfile", "-Command", ps], 120)
        if code != 0:
            raise RuntimeError("Windows ga ikke administratortilgang")
    else:
        conns = _nm_conns()
        if not conns:
            raise RuntimeError("fant ingen aktiv nettverkstilkobling")
        for uuid, dev in conns:
            if provider:
                _n, v4, v6 = PROVIDERS[provider]
                args = ["ipv4.dns", " ".join(v4), "ipv4.ignore-auto-dns", "yes",
                        "ipv6.dns", " ".join(v6), "ipv6.ignore-auto-dns", "yes"]
            else:
                args = ["ipv4.dns", "", "ipv4.ignore-auto-dns", "no", "ipv6.dns", "", "ipv6.ignore-auto-dns", "no"]
            code, out = _run(["nmcli", "con", "mod", uuid, *args], 20)
            if code != 0:
                raise RuntimeError(out.strip().splitlines()[-1] if out.strip() else "kunne ikke endre DNS")
            _run(["nmcli", "dev", "reapply", dev], 20)
    c = _fcfg()
    c["dns_filter"] = provider
    _fsave(c)
    return f"Nettfilter: {PROVIDERS[provider][0]} ✓" if provider else "Nettfilteret er slått av"


# ==========================================================================
# Melding i spillet
# ==========================================================================
_MSG = {"timer": None, "had_nodisplay": False}
MANGOHUD_CONF = os.path.expanduser("~/.config/MangoHud/MangoHud.conf")
MARK = "# kontrollsenter-melding"


def _strip(lines):
    """Fjern meldingen vår (merke-linjen og linjen under)."""
    out, skip = [], False
    for ln in lines:
        if ln.strip() == MARK:
            skip = True
            continue
        if skip:
            skip = False
            continue
        out.append(ln)
    return out


def ingame(text, secs=25):
    """Vis en kort melding inne i spillet (MangoHud på Linux, varsel over spillet på Windows)."""
    if IS_WIN:
        return False
    p = MANGOHUD_CONF
    try:
        lines = open(p).read().splitlines()
    except OSError:
        return False
    lines = _strip(lines)
    had = "no_display" in lines
    lines = [ln for ln in lines if ln != "no_display"]
    safe = re.sub(r"[\r\n=]", " ", text)[:60]
    lines += [MARK, f"custom_text_center=⏰ {safe}"]
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, p)
    if _MSG["timer"]:
        _MSG["timer"].cancel()
    else:
        _MSG["had_nodisplay"] = had

    def clear():
        _MSG["timer"] = None
        try:
            cur = _strip(open(p).read().splitlines())
            if _MSG["had_nodisplay"] and "no_display" not in cur:
                cur.append("no_display")
            with open(tmp, "w") as f:
                f.write("\n".join(cur) + "\n")
            os.replace(tmp, p)
        except OSError:
            pass
    _MSG["timer"] = threading.Timer(secs, clear)
    _MSG["timer"].daemon = True
    _MSG["timer"].start()
    return True


# ==========================================================================
# Lukke spillet som kjører
# ==========================================================================
def close_game():
    """Lukk spillet som kjører (Steam-spill eller kjente andre spill). Returnerer navnet eller None."""
    import psutil
    import games_auto
    g = games_auto.running_game()
    if not g:
        return None
    aid, name = g
    victims = []
    if IS_WIN:
        gdir = None
        try:
            import games
            gdir = next((x.get("dir") for x in games.installed_games() if x["appid"] == aid), None)
        except Exception:  # noqa: BLE001
            pass
        for p in psutil.process_iter(["exe", "name"]):
            exe = (p.info.get("exe") or "").lower()
            if (gdir and exe.startswith(gdir.lower())) or (aid.startswith("ext:") and
                                                          (p.info.get("name") or "").lower() == aid[4:]):
                victims.append(p)
    else:
        for p in psutil.process_iter(["cmdline", "name"]):
            cmd = " ".join(p.info.get("cmdline") or [])
            if (not aid.startswith("ext:") and f"AppId={aid}" in cmd and "SteamLaunch" in cmd) or \
                    (aid.startswith("ext:") and (p.info.get("name") or "").lower().startswith(aid[4:][:15])):
                victims.append(p)
    procs = []
    for p in victims:
        try:
            procs += p.children(recursive=True) + [p]
        except psutil.Error:
            continue
    for p in procs:
        try:
            p.terminate()
        except psutil.Error:
            pass
    _gone, alive = psutil.wait_procs(procs, timeout=8)
    for p in alive:
        try:
            p.kill()
        except psutil.Error:
            pass
    return name if procs else None


# ==========================================================================
# Leksetid
# ==========================================================================
DEFAULT_SCHOOL = {"enabled": False, "days": [0, 1, 2, 3, 4], "from": "16:00", "to": "18:00", "goal": "lekser"}


def school_cfg():
    return {**DEFAULT_SCHOOL, **(_fcfg().get("school") or {})}


def set_school(**kw):
    c = _fcfg()
    s = {**DEFAULT_SCHOOL, **(c.get("school") or {})}
    for k, v in kw.items():
        if k == "enabled":
            s[k] = bool(v)
        elif k == "days":
            s[k] = sorted({int(x) for x in v if 0 <= int(x) <= 6})
        elif k in ("from", "to"):
            hh, mm = (int(x) for x in str(v).split(":"))
            if not (0 <= hh < 24 and 0 <= mm < 60):
                raise ValueError("ugyldig klokkeslett")
            s[k] = f"{hh:02d}:{mm:02d}"
        else:
            raise ValueError(f"ukjent valg {k}")
    c["school"] = s
    _fsave(c)
    return s


def _goal_done_today(goal):
    day = time.strftime("%Y-%m-%d")
    for r in _fcfg().get("goal_reqs", []):
        if r.get("goal") == goal and r.get("state") == "godkjent" and \
                time.strftime("%Y-%m-%d", time.localtime(r.get("answered", 0))) == day:
            return True
    return False


def in_school_time(now=None):
    s = school_cfg()
    if not s["enabled"] or s.get("free_day") == time.strftime("%Y-%m-%d", time.localtime(now)):
        return False                                        # «Fri i dag» fra en voksen
    lt = time.localtime(now)
    if lt.tm_wday not in s["days"]:
        return False
    m = lt.tm_hour * 60 + lt.tm_min
    a = int(s["from"][:2]) * 60 + int(s["from"][3:])
    b = int(s["to"][:2]) * 60 + int(s["to"][3:])
    return a <= m < b and not _goal_done_today(s["goal"])


_SCHOOL = {"warned": None}


def school_tick(game, notify):
    """Kalles jevnlig med spillet som kjører (navn eller None)."""
    if not game or not in_school_time():
        _SCHOOL["warned"] = None
        return
    s = school_cfg()
    if _SCHOOL["warned"] is None:
        _SCHOOL["warned"] = time.time()
        txt = f"Leksetid til {s['to']} – spillet lukkes om 2 minutter. Ferdig med leksene? Be om godkjenning."
        notify("playlimit", "📚 Leksetid", txt, force=True)
        ingame("Leksetid – spillet lukkes om 2 min", 60)
        try:
            import remote_extra
            remote_extra.event("playtime", "Leksetid", f"{game} – lukkes om 2 min", "warn")
        except Exception:  # noqa: BLE001
            pass
    elif time.time() - _SCHOOL["warned"] >= 120:
        _SCHOOL["warned"] = None                              # startes spillet igjen: nytt varsel
        name = close_game()
        if name:
            notify("playlimit", "📚 Spillet ble lukket", f"{name} – det er leksetid til {s['to']}", force=True)


def state():
    return {"dns": dns_state(), "providers": {k: v[0] for k, v in PROVIDERS.items()}, "school": school_cfg(),
            "school_now": in_school_time()}

