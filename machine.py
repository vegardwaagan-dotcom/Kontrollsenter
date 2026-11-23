"""Samme maskin i flere systemer (dual boot: Windows og Linux på samme PC).

Hver installasjon regner ut en maskin-ID fra MAC-adressen til nettverkskortet den bruker på hjemmenettet (samme
maskinvare = samme ID i både Windows og Linux). ID-en deles i statusen PC-ene legger på NAS-en og i venne-statusen, så
• PC-er hjemme og PC-er utenfor hjemmet viser maskinen som ÉN PC (med systemet som kjører nå),
• chatten viser den som ÉN samtale og leverer til systemet som er på,
• chat_sync.py kan gi begge systemene samme chat (identitet, samtaler og servere).
"""
import hashlib
import re
import sys
import time

IS_WIN = sys.platform == "win32"
_V = {"id": None, "t": 0}
_VIRTUAL = re.compile(r"docker|veth|br-|virbr|tailscale|vmnet|vbox|zt|wg|tun|tap|loopback|vethernet|hyper-v|"
                      r"bluetooth|npcap|lo$", re.I)


def _primary_mac():
    import psutil
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    cands = []
    for name, lst in addrs.items():
        if _VIRTUAL.search(name):
            continue
        mac = next((a.address for a in lst if a.family == psutil.AF_LINK), None)
        if not mac:
            continue
        mac = mac.replace("-", ":").lower()
        if mac in ("00:00:00:00:00:00", "") or len(mac) != 17:
            continue
        if int(mac[:2], 16) & 0x02:                       # lokalt administrert (tilfeldig/virtuell) – ikke maskinvare
            continue
        lan = any(a.family == 2 and a.address.startswith(("192.168.", "10.", "172.")) for a in lst)
        up = getattr(stats.get(name), "isup", False)
        cands.append((not lan, not up, name, mac))
    cands.sort()
    return cands[0][3] if cands else None


def hw_id():
    """Kort ID for maskinvaren (samme i Windows og Linux på samme PC), eller None."""
    if _V["id"] is None or time.time() - _V["t"] > 3600:
        try:
            mac = _primary_mac()
        except Exception:  # noqa: BLE001
            mac = None
        _V.update(id=hashlib.sha256(f"ks:{mac}".encode()).hexdigest()[:12] if mac else "", t=time.time())
    return _V["id"] or None


def os_name():
    if IS_WIN:
        return "Windows"
    try:
        with open("/etc/os-release") as f:
            m = re.search(r'^NAME="?([^"\n]+)', f.read(), re.M)
            return m.group(1) if m else "Linux"
    except OSError:
        return "Linux"


def os_icon(name):
    return "🪟" if "windows" in (name or "").lower() else "🐧"


# --------------------------------------------------------------------------
# PC-er hjemme: slå sammen oppføringer for samme maskin
# --------------------------------------------------------------------------
def _groups(pcs):
    """Grupper PC-ene per maskin: samme maskin-ID – eller (for eldre versjoner uten ID) samme adresse på
    hjemmenettet, som et dual boot-system får fordi det er samme nettverkskort."""
    groups = []
    for p in pcs:
        ips = set(p.get("ips") or [])
        hw = p.get("hw")
        g = next((g for g in groups if (hw and hw in g["hw"]) or ((not hw or not g["hw"]) and ips & g["ips"])), None)
        if g is None:
            g = {"hw": set(), "ips": set(), "pcs": []}
            groups.append(g)
        g["pcs"].append(p)
        g["ips"] |= ips
        if hw:
            g["hw"].add(hw)
    return [g["pcs"] for g in groups]


def merge_home(pcs, stale=900):
    """[{…}] fra homepcs.fetch() → én oppføring per maskin. Den som kjører nå (eller sist) vises; de andre
    systemene ligger i «systems»: [(navn, os, på)]."""
    if not pcs:
        return pcs
    out = []
    now = time.time()
    for g in _groups(pcs):
        on = [p for p in g if now - p.get("time", 0) < stale and not p.get("off")]
        best = max(on or g, key=lambda p: p.get("time", 0))
        if len(g) > 1:
            best = dict(best)
            best["systems"] = [(p.get("name"), p.get("os") or ("Windows" if "windows" in str(p.get("distro", "")).lower()
                                                               else "Linux"), p in on) for p in g]
            best["aliases"] = [p.get("name") for p in g]
        out.append(best)
    return out


_PCS = {"t": 0, "v": []}


def _pcs():
    """PC-lista fra NAS-en, mellomlagret i ett minutt (chatten spør ofte)."""
    if time.time() - _PCS["t"] > 60:
        try:
            import homepcs
            _PCS.update(t=time.time(), v=homepcs.fetch() or [])
        except Exception:  # noqa: BLE001
            _PCS["t"] = time.time()
    return _PCS["v"]


def home_aliases(name):
    """Alle navnene samme maskin har hjemme (f.eks. «William-PC» og «bazzite-William»)."""
    for g in _groups(_pcs()):
        names = [p.get("name") for p in g]
        if name in names:
            return names
    return [name]


def online_alias(name, stale=900):
    """Navnet til systemet som kjører nå på samme maskin (for å levere meldinger dit)."""
    pcs = _pcs()
    al = set(home_aliases(name))
    now = time.time()
    on = [p for p in pcs if p.get("name") in al and now - p.get("time", 0) < stale and not p.get("off")]
    return max(on, key=lambda p: p.get("time", 0))["name"] if on else name


# --------------------------------------------------------------------------
# PC-er utenfor hjemmet: venner med samme maskin
# --------------------------------------------------------------------------
def merge_friends(rows):
    """[{friend, online, hw, …}] fra friends.fetch_all() → én kort per maskin (den som er på vises)."""
    groups, order = {}, []
    for d in rows or []:
        key = d.get("hw") or f"adr:{d.get('addr')}"
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(d)
    out = []
    for key in order:
        g = groups[key]
        best = next((d for d in g if d.get("online")), g[0])
        if len(g) > 1:
            best = dict(best)
            best["systems"] = [(d.get("friend"), d.get("os") or "", bool(d.get("online"))) for d in g]
            best["aliases"] = [d.get("friend") for d in g]
        out.append(best)
    return out
