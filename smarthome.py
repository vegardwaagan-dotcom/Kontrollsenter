"""Smart Hjem: finner smartenheter på hjemmenettet og styrer dem som kan styres.

Finner enheter med ARP-tabellen, SSDP (UPnP) og mDNS, og spør hver enhet hva den er.
Styring (bare lokalt nett, ingen sky):
  • Philips Hue – lys av/på, lysstyrke og farge, rom
  • Samsung-TV (Tizen, 2016+) – av/på, volum, demp, hjem, kilde, pause/spill
  • Chromecast / Google TV / Nest-høyttalere – hva som spilles, volum, demp, pause/spill, stopp
Virker likt på Linux og Windows (bare Python-standardbiblioteket).
"""
import base64
import ipaddress
import json
import os
import re
import socket
import ssl
import struct
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from xml.etree import ElementTree

CFG = os.path.expanduser("~/.config/systemmonitor/smarthjem.json")
_LOCK = threading.Lock()
_CACHE = {"devices": [], "at": 0, "busy": False}

# Produsenter vi kjenner sikkert på MAC-adressen (første tre byte)
OUI = {
    "00:17:88": "Philips Hue", "ec:b5:fa": "Philips Hue",
    "b8:27:eb": "Raspberry Pi", "dc:a6:32": "Raspberry Pi", "e4:5f:01": "Raspberry Pi", "2c:cf:67": "Raspberry Pi",
    "00:0e:58": "Sonos", "5c:aa:fd": "Sonos", "48:a6:b8": "Sonos", "94:9f:3e": "Sonos",
    "00:11:32": "Synology", "90:09:d0": "Synology", "24:5e:be": "QNAP",
    "00:10:75": "Seagate",
}

KINDS = {  # type -> (ikon i appen, navn)
    "light": ("💡", "Lys"), "hub": ("🔗", "Smartbro"), "tv": ("📺", "TV"), "cast": ("📡", "Strømming"),
    "speaker": ("🔊", "Høyttaler"), "pc": ("🖥️", "PC"), "nas": ("🗄️", "NAS"), "router": ("🌐", "Ruter"),
    "printer": ("🖨️", "Skriver"), "phone": ("📱", "Mobil/nettbrett"), "console": ("🎮", "Spillkonsoll"),
    "plug": ("🔌", "Smartenhet"), "camera": ("📷", "Kamera"), "other": ("❔", "Ukjent"),
}


# --------------------------------------------------------------------------
# innstillinger (Hue-nøkkel ligger i features.cfg; TV-nøkler her)
# --------------------------------------------------------------------------
def cfg():
    try:
        with open(CFG, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_cfg(c):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    tmp = CFG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(c, f)
    os.replace(tmp, CFG)


def _get(url, timeout=1.2):
    req = urllib.request.Request(url, headers={"User-Agent": "Kontrollsenter"})
    with urllib.request.urlopen(req, timeout=timeout, context=ssl._create_unverified_context()) as r:
        return r.read(200000)


def _getjson(url, timeout=1.2):
    return json.loads(_get(url, timeout))


def _open(ip, port, timeout=0.6):
    try:
        with socket.create_connection((ip, port), timeout):
            return True
    except OSError:
        return False


# --------------------------------------------------------------------------
# finne enheter
# --------------------------------------------------------------------------
def _my_net():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ipaddress.ip_network(ip + "/24", strict=False), ip
    except OSError:
        return None, None


def _gateway():
    try:
        if os.name == "nt":
            import winsupport as WS
            _c, out = WS.run(["route", "print", "0.0.0.0"], 10)
            m = re.search(r"0\.0\.0\.0\s+0\.0\.0\.0\s+(\d+\.\d+\.\d+\.\d+)", out)
        else:
            import subprocess
            out = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True, timeout=5).stdout
            m = re.search(r"default via (\d+\.\d+\.\d+\.\d+)", out)
        return m.group(1) if m else None
    except Exception:  # noqa: BLE001
        return None


def _wake_arp(net):
    """Send en tom UDP-pakke til alle adressene, så ARP-tabellen fylles med alle som er på."""
    if not net:
        return
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setblocking(False)
    for h in net.hosts():
        try:
            s.sendto(b"", (str(h), 9))
        except OSError:
            pass
    s.close()
    time.sleep(1.5)


def _ssdp(wait=3.0):
    msg = (b'M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: "ssdp:discover"\r\n'
           b"MX: 2\r\nST: ssdp:all\r\n\r\n")
    out = {}
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.4)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        for _ in range(2):
            s.sendto(msg, ("239.255.255.250", 1900))
        end = time.time() + wait
        while time.time() < end:
            try:
                d, a = s.recvfrom(4096)
            except socket.timeout:
                continue
            t = d.decode(errors="ignore")
            hd = {k.lower(): v.strip() for k, v in re.findall(r"(?m)^([A-Za-z0-9-]+):(.*)$", t)}
            e = out.setdefault(a[0], {"server": "", "locations": set(), "st": set()})
            e["server"] = e["server"] or hd.get("server", "")
            if hd.get("location"):
                e["locations"].add(hd["location"])
            if hd.get("st"):
                e["st"].add(hd["st"])
        s.close()
    except OSError:
        pass
    return out


# ---- mDNS (Bonjour): spør etter de vanligste smarthjem-tjenestene ----
MDNS_TYPES = ["_googlecast._tcp", "_hap._tcp", "_airplay._tcp", "_raop._tcp", "_hue._tcp", "_shelly._tcp",
              "_esphomelib._tcp", "_wled._tcp", "_elg._tcp", "_ipp._tcp", "_printer._tcp", "_sonos._tcp",
              "_spotify-connect._tcp", "_androidtvremote2._tcp", "_matter._tcp", "_homekit._tcp", "_amzn-wplay._tcp"]


def _dns_name(buf, off):
    labels, jumped, end = [], False, off
    for _ in range(64):
        ln = buf[off]
        if ln == 0:
            off += 1
            break
        if ln & 0xC0 == 0xC0:
            ptr = ((ln & 0x3F) << 8) | buf[off + 1]
            if not jumped:
                end = off + 2
            jumped, off = True, ptr
            continue
        labels.append(buf[off + 1:off + 1 + ln].decode("utf-8", "replace"))
        off += 1 + ln
    return ".".join(labels), (end if jumped else off)


def _mdns(wait=2.5):
    out = {}
    q = bytearray(struct.pack(">HHHHHH", 0, 0, len(MDNS_TYPES), 0, 0, 0))
    for t in MDNS_TYPES:
        for part in (t + ".local").split("."):
            q += bytes([len(part)]) + part.encode()
        q += b"\x00" + struct.pack(">HH", 12, 1)          # PTR, IN
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.4)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
        s.sendto(bytes(q), ("224.0.0.251", 5353))
        end = time.time() + wait
        while time.time() < end:
            try:
                d, a = s.recvfrom(9000)
            except socket.timeout:
                continue
            try:
                _parse_mdns(d, out.setdefault(a[0], {"services": set(), "names": set(), "txt": {}}))
            except (IndexError, struct.error, UnicodeError):
                pass
        s.close()
    except OSError:
        pass
    return out


def _parse_mdns(d, e):
    _id, _fl, qd, an, ns, ar = struct.unpack(">HHHHHH", d[:12])
    off = 12
    for _ in range(qd):
        _n, off = _dns_name(d, off)
        off += 4
    for _ in range(an + ns + ar):
        name, off = _dns_name(d, off)
        typ, _cls, _ttl, ln = struct.unpack(">HHIH", d[off:off + 10])
        off += 10
        rd = d[off:off + ln]
        if typ == 12:                                   # PTR: tjeneste -> navn på enheten
            target, _ = _dns_name(d, off)
            m = re.match(r"(.+?)\.(_[^.]+\._(?:tcp|udp))\.local$", target)
            if m:
                e["services"].add(m.group(2))
                e["names"].add(m.group(1))
        elif typ == 16:                                 # TXT: f.eks. fn=Stue, md=Chromecast
            i = 0
            while i < len(rd):
                ln2 = rd[i]
                kv = rd[i + 1:i + 1 + ln2].decode("utf-8", "replace")
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    e["txt"].setdefault(k.lower(), v)
                i += 1 + ln2
        off += ln


def _upnp_desc(url):
    try:
        x = ElementTree.fromstring(_get(url, 1.5))
    except Exception:  # noqa: BLE001
        return {}
    ns = {"u": "urn:schemas-upnp-org:device-1-0"}
    dev = x.find("u:device", ns)
    if dev is None:
        return {}
    g = lambda k: (dev.findtext("u:" + k, default="", namespaces=ns) or "").strip()  # noqa: E731
    return {"friendly": g("friendlyName"), "maker": g("manufacturer"), "model": g("modelName"),
            "type": g("deviceType")}


def _probe(ip, mac, ssdp, mdns, gw):
    """Finn ut hva enheten er. Returnerer en ordbok med navn, type, produsent og hva som kan styres."""
    d = {"ip": ip, "mac": mac or "", "name": "", "kind": "other", "maker": "", "model": "", "control": []}
    sd, md = ssdp.get(ip) or {}, mdns.get(ip) or {}
    services = md.get("services", set())
    txt = md.get("txt", {})
    if mac:
        d["maker"] = OUI.get(mac[:8], "")
        if int(mac[1], 16) & 2:                         # tilfeldig (privat) MAC = som regel mobil/nettbrett
            d["kind"], d["private_mac"] = "phone", True
    if ip == gw:
        d.update(kind="router", name="Ruter")
    server = sd.get("server", "")

    # Kontrollsenter-PC
    if _open(ip, 27100, 0.4):
        try:
            h = _getjson(f"http://{ip}:27100/api/hello", 1.2)
            if h.get("app") == "Kontrollsenter":
                d.update(kind="pc", name=h.get("name", ""), model="Kontrollsenter " + h.get("version", ""),
                         maker="Windows" if h.get("os") == "windows" else "Linux")
                return d
        except Exception:  # noqa: BLE001
            pass
    # Philips Hue-bro
    if "IpBridge" in server or d["maker"] == "Philips Hue" or "_hue._tcp" in services:
        try:
            c = _getjson(f"http://{ip}/api/config", 1.5)
            d.update(kind="hub", name=c.get("name") or "Hue Bridge", maker="Philips Hue", model=c.get("modelid", ""),
                     control=["hue"])
            return d
        except Exception:  # noqa: BLE001
            pass
    # Samsung-TV
    if _open(ip, 8001, 0.4):
        try:
            j = _getjson(f"http://{ip}:8001/api/v2/", 1.5)
            dv = j.get("device", {})
            d.update(kind="tv", name=j.get("name") or dv.get("name", "Samsung-TV"), maker="Samsung",
                     model=dv.get("modelName", ""), power=dv.get("PowerState", "on"), control=["samsung"],
                     tvmac=(dv.get("wifiMac") or mac or "").lower())
            d["name"] = d["name"].replace("[TV] ", "")
            return d
        except Exception:  # noqa: BLE001
            pass
    # Chromecast / Google TV / Nest
    if "_googlecast._tcp" in services or _open(ip, 8009, 0.4):
        d.update(kind="cast", maker="Google", control=["cast"])
        d["name"] = txt.get("fn", "")
        d["model"] = txt.get("md", "")
        try:
            e = _getjson(f"http://{ip}:8008/setup/eureka_info?params=name,device_info", 1.2)
            d["name"] = d["name"] or e.get("name", "")
            d["model"] = d["model"] or (e.get("device_info") or {}).get("model_name", "")
        except Exception:  # noqa: BLE001
            pass
        mdl = d["model"].lower()
        if "tv" in mdl or "_androidtvremote2._tcp" in services or _open(ip, 6466, 0.4):
            d["kind"] = "tv"
            d["name"] = d["name"] or "Google TV"
        elif any(w in mdl for w in ("nest", "home", "audio", "speaker", "mini", "hub")):
            d["kind"] = "speaker"
        d["name"] = d["name"] or "Chromecast"
        return d
    # Sonos
    if "_sonos._tcp" in services or d["maker"] == "Sonos" or "Sonos" in server:
        try:
            x = _upnp_desc(f"http://{ip}:1400/xml/device_description.xml")
            d.update(kind="speaker", maker="Sonos", name=x.get("friendly", "Sonos").split(" - ")[0], model=x.get("model", ""))
        except Exception:  # noqa: BLE001
            d.update(kind="speaker", maker="Sonos", name="Sonos")
        return d
    # andre ting som sier fra om seg selv
    if services & {"_shelly._tcp", "_esphomelib._tcp", "_wled._tcp", "_hap._tcp", "_homekit._tcp", "_matter._tcp"}:
        d["kind"] = "light" if "_wled._tcp" in services else "plug"
        d["maker"] = d["maker"] or ("Shelly" if "_shelly._tcp" in services else "ESPHome" if "_esphomelib._tcp" in services
                                    else "WLED" if "_wled._tcp" in services else "HomeKit/Matter")
    elif "_elg._tcp" in services:
        d.update(kind="light", maker="Elgato")
    elif services & {"_ipp._tcp", "_printer._tcp"}:
        d["kind"] = "printer"
    elif services & {"_airplay._tcp", "_raop._tcp", "_spotify-connect._tcp"}:
        d["kind"] = "speaker" if d["kind"] != "phone" else "phone"
    if md.get("names") and not d["name"]:
        n = sorted(md["names"], key=len)[0]
        d["name"] = re.sub(r"^[0-9A-F]{12}@", "", n)       # AirPlay-navn starter med MAC@
        d["name"] = txt.get("fn") or txt.get("n") or d["name"]
    # UPnP-beskrivelse (NAS, skrivere, mediaspillere, TV-er fra andre merker)
    for loc in sorted(sd.get("locations", ()))[:2]:
        x = _upnp_desc(loc)
        if not x:
            continue
        d["name"] = d["name"] or x.get("friendly", "")
        d["maker"] = d["maker"] or x.get("maker", "")
        d["model"] = d["model"] or x.get("model", "")
        t = (x.get("type", "") + " " + x.get("model", "") + " " + x.get("maker", "")).lower()
        if d["kind"] in ("other", "phone"):
            if "mediaserver" in t or "nas" in t or "personal cloud" in t or "synology" in t or "qnap" in t:
                d["kind"] = "nas"
            elif "printer" in t:
                d["kind"] = "printer"
            elif "xbox" in t or "playstation" in t or "nintendo" in t:
                d["kind"] = "console"
            elif "mediarenderer" in t and "microsoft" in t:
                d["kind"] = "pc"
            elif "tv" in t or "mediarenderer" in t:
                d["kind"] = "tv"
            elif "internetgatewaydevice" in t or "wfadevice" in t:
                d["kind"] = "router"
        if d["name"]:
            break
    if str(txt.get("model", "")).startswith("AppleTV") or "apple tv" in d["name"].lower():
        d.update(kind="tv", maker="Apple")
    elif str(txt.get("model", "")).startswith(("HomePod", "AudioAccessory")):
        d.update(kind="speaker", maker="Apple")
    if d["kind"] in ("other", "phone") and _open(ip, 6466, 0.4):      # Android TV / Google TV (fjernkontroll-port)
        d.update(kind="tv", name=d["name"] or "Google TV / Android TV")
    if "Microsoft-Windows" in server and d["kind"] in ("other", "phone"):
        d["kind"] = "pc"
    if d["maker"] in ("Synology", "QNAP", "Seagate") and d["kind"] == "other":
        d["kind"] = "nas"
    if d["kind"] == "other" and not d["name"] and d["maker"] == "Raspberry Pi":
        d["name"] = "Raspberry Pi"
    if d["kind"] == "other" and not d["name"] and _open(ip, 80, 0.4):   # nettside: bruk tittelen som hint
        try:
            m = re.search(rb"<title>([^<]{2,60})</title>", _get(f"http://{ip}/", 1.2), re.I)
            t = m.group(1).decode("utf-8", "replace").strip() if m else ""
            if t and not re.search(r"\d{3}|unauthori|forbidden|login|index", t, re.I):
                d["name"] = t
        except Exception:  # noqa: BLE001
            pass
    return d


def scan():
    """Finn alle enhetene på hjemmenettet (tar 5–10 sekunder)."""
    net, myip = _my_net()
    _wake_arp(net)
    res = {}
    with ThreadPoolExecutor(2) as ex:
        f1, f2 = ex.submit(_ssdp), ex.submit(_mdns)
        ssdp, mdns = f1.result(), f2.result()
    import features as F
    known = {x["mac"]: x for x in F.lan_devices()}
    ips = {x["ip"]: x["mac"] for x in known.values()}
    for ip in list(ssdp) + list(mdns):
        if net and ipaddress.ip_address(ip) in net:
            ips.setdefault(ip, "")
    ips.pop(myip, None)
    gw = _gateway()
    with ThreadPoolExecutor(24) as ex:
        found = list(ex.map(lambda kv: _probe(kv[0], kv[1], ssdp, mdns, gw), ips.items()))
    names = cfg().get("names", {})
    for d in found:
        key = d["mac"] or d["ip"]
        own = names.get(key) or (known.get(d["mac"], {}).get("name") if d["mac"] else "")
        if own:
            d["name"] = own
        d["icon"], d["kind_name"] = KINDS.get(d["kind"], KINDS["other"])
        d["id"] = key
        res[key] = d
    if myip:                                            # denne PC-en
        res["self"] = {"id": "self", "ip": myip, "mac": "", "name": socket.gethostname(), "kind": "pc",
                       "icon": "🖥️", "kind_name": "PC", "maker": "Denne PC-en", "model": "", "control": []}
    order = ["hub", "light", "tv", "cast", "speaker", "plug", "camera", "pc", "console", "nas", "printer", "router",
             "phone", "other"]
    devs = sorted(res.values(), key=lambda d: (order.index(d["kind"]) if d["kind"] in order else 99,
                                               not d["name"], d["name"].lower(),
                                               tuple(int(x) for x in d["ip"].split("."))))
    # husk TV-ens MAC, så den kan slås på igjen med Wake-on-LAN når den er av (og ikke svarer)
    c = cfg()
    tvs = c.setdefault("tvs", {})
    for d in devs:
        if d["kind"] == "tv" and "samsung" in d["control"] and d.get("tvmac"):
            tvs[d["ip"]] = {**tvs.get(d["ip"], {}), "mac": d["tvmac"], "name": d["name"], "model": d["model"]}
    seen_tv = {d["ip"] for d in devs if "samsung" in d["control"]}
    for ip, t in tvs.items():                            # TV-er som er helt av (svarer ikke), men som vi kjenner
        if ip not in seen_tv:
            devs.insert(0, {"id": t.get("mac") or ip, "ip": ip, "mac": t.get("mac", ""), "name": t.get("name", "TV"),
                            "kind": "tv", "icon": "📺", "kind_name": "TV", "maker": "Samsung", "model": t.get("model", ""),
                            "power": "off", "control": ["samsung"], "tvmac": t.get("mac", "")})
    save_cfg(c)
    return devs


def devices(max_age=120, wait=False):
    """Siste søk (fra minnet). Starter et nytt søk i bakgrunnen når det er eldre enn max_age sekunder."""
    with _LOCK:
        old = time.time() - _CACHE["at"] > max_age
        start = old and not _CACHE["busy"]
        if start:
            _CACHE["busy"] = True

    def work():
        try:
            devs = scan()
            now = time.time()
            ids = {d["id"] for d in devs}
            for d in devs:
                d["seen"] = now
            # enheter som ikke svarte akkurat nå (sover), beholdes en stund så lista ikke blinker
            keep = [d for d in _CACHE["devices"] if d["id"] not in ids and now - d.get("seen", 0) < 900]
            with _LOCK:
                _CACHE.update(devices=devs + keep, at=now)
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("smarthjem-søk")
        finally:
            with _LOCK:
                _CACHE["busy"] = False
    if start:
        if wait or not _CACHE["devices"]:
            work()
        else:
            threading.Thread(target=work, daemon=True).start()
    return _CACHE["devices"]


def rename(dev_id, name):
    c = cfg()
    c.setdefault("names", {})[str(dev_id)] = str(name)[:40]
    save_cfg(c)
    for d in _CACHE["devices"]:
        if d["id"] == dev_id:
            d["name"] = str(name)[:40]


# --------------------------------------------------------------------------
# Philips Hue
# --------------------------------------------------------------------------
def _xy_to_hex(xy, bri=254):
    x, y = xy
    z = 1.0 - x - y
    Y = 1.0
    X, Z = (Y / y) * x if y else 0, (Y / y) * z if y else 0
    r = X * 1.656492 - Y * 0.354851 - Z * 0.255038
    g = -X * 0.707196 + Y * 1.655397 + Z * 0.036152
    b = X * 0.051713 - Y * 0.121364 + Z * 1.011530
    m = max(r, g, b, 1e-6)
    r, g, b = (max(0.0, c / m) for c in (r, g, b))
    r, g, b = ((12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055) for c in (r, g, b))
    return "#%02x%02x%02x" % tuple(int(max(0, min(1, c)) * 255) for c in (r, g, b))


def hue_state():
    import features as F
    h = F.cfg().get("hue") or {}
    out = {"paired": bool(h.get("user")), "ip": h.get("ip"), "lights": [], "rooms": []}
    if not out["paired"]:
        return out
    try:
        lights = F._hue("lights")
        groups = F._hue("groups")
    except Exception as e:  # noqa: BLE001
        out["error"] = f"Får ikke kontakt med Hue-broen ({e})"
        return out
    for k, v in lights.items():
        st = v.get("state", {})
        col = _xy_to_hex(st["xy"]) if st.get("xy") and st.get("colormode") in ("xy", "hs") else None
        out["lights"].append({"id": k, "name": v.get("name"), "on": bool(st.get("on")), "bri": st.get("bri"),
                              "reachable": st.get("reachable", True), "color": col,
                              "can_color": "xy" in st, "can_dim": "bri" in st})
    for k, v in groups.items():
        if v.get("type") in ("Room", "Zone"):
            out["rooms"].append({"id": k, "name": v.get("name"), "lights": v.get("lights", []),
                                 "any_on": bool(v.get("state", {}).get("any_on")),
                                 "all_on": bool(v.get("state", {}).get("all_on"))})
    out["lights"].sort(key=lambda x: x["name"] or "")
    out["rooms"].sort(key=lambda x: x["name"] or "")
    return out


def hue_light(light_id=None, room_id=None, on=None, bri=None, color=None):
    import features as F
    body = {}
    if on is not None:
        body["on"] = bool(on)
    if bri is not None:
        body["bri"] = max(1, min(254, int(bri)))
        body.setdefault("on", True)
    if color:
        if not re.fullmatch(r"#?[0-9a-fA-F]{6}", color):
            raise ValueError("ugyldig farge")
        r, g, b = (int(color.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4))
        r, g, b = ((c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4) for c in (r, g, b))
        X = r * 0.649926 + g * 0.103455 + b * 0.197109
        Y = r * 0.234327 + g * 0.743075 + b * 0.022598
        Z = g * 0.053077 + b * 1.035763
        s = X + Y + Z or 1
        body.update({"xy": [round(X / s, 4), round(Y / s, 4)], "on": True})
    if not body:
        return
    if room_id is not None:
        F._hue(f"groups/{int(room_id)}/action", body)
    elif light_id is not None:
        F._hue(f"lights/{int(light_id)}/state", body)
    else:
        F._hue("groups/0/action", body)                 # alle lysene


# --------------------------------------------------------------------------
# Samsung-TV (Tizen) – fjernkontroll over WebSocket (port 8002) med nøkkel
# --------------------------------------------------------------------------
TV_KEYS = {"power": "KEY_POWER", "volup": "KEY_VOLUP", "voldown": "KEY_VOLDOWN", "mute": "KEY_MUTE",
           "home": "KEY_HOME", "source": "KEY_SOURCE", "play": "KEY_PLAY", "pause": "KEY_PAUSE",
           "chup": "KEY_CHUP", "chdown": "KEY_CHDOWN", "back": "KEY_RETURN", "ok": "KEY_ENTER",
           "up": "KEY_UP", "down": "KEY_DOWN", "left": "KEY_LEFT", "right": "KEY_RIGHT"}


def _ws_frame(text):
    data = text.encode()
    mask = os.urandom(4)
    hdr = bytearray([0x81])
    n = len(data)
    if n < 126:
        hdr.append(0x80 | n)
    elif n < 65536:
        hdr += bytes([0x80 | 126]) + struct.pack(">H", n)
    else:
        hdr += bytes([0x80 | 127]) + struct.pack(">Q", n)
    return bytes(hdr) + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data))


def _recv_exact(s, n):
    buf = b""
    while len(buf) < n:
        ch = s.recv(n - len(buf))
        if not ch:
            raise ConnectionError("TV-en lukket forbindelsen")
        buf += ch
    return buf


def _ws_read(s):
    b1, b2 = _recv_exact(s, 2)
    n = b2 & 0x7F
    if n == 126:
        n = struct.unpack(">H", _recv_exact(s, 2))[0]
    elif n == 127:
        n = struct.unpack(">Q", _recv_exact(s, 8))[0]
    if b2 & 0x80:
        _recv_exact(s, 4)
    data = _recv_exact(s, n)
    return b1 & 0x0F, data


def _tv_connect(ip, wait_allow=30):
    c = cfg()
    tok = c.get("tvtokens", {}).get(ip, "")
    name = base64.b64encode("Kontrollsenter".encode()).decode()
    path = f"/api/v2/channels/samsung.remote.control?name={name}" + (f"&token={tok}" if tok else "")
    raw = socket.create_connection((ip, 8002), 5)
    s = ssl._create_unverified_context().wrap_socket(raw, server_hostname=ip)
    key = base64.b64encode(os.urandom(16)).decode()
    s.sendall((f"GET {path} HTTP/1.1\r\nHost: {ip}:8002\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
    hdr = b""
    while b"\r\n\r\n" not in hdr:
        ch = s.recv(1024)
        if not ch:
            raise ConnectionError("TV-en svarte ikke")
        hdr += ch
    if b" 101 " not in hdr.split(b"\r\n")[0]:
        raise ConnectionError("TV-en godtok ikke tilkoblingen")
    s.settimeout(wait_allow)                               # første gang: venter på «Tillat» på TV-en
    while True:
        op, data = _ws_read(s)
        if op == 8:
            raise PermissionError("TV-en avviste Kontrollsenter – velg «Tillat» på TV-en og prøv igjen")
        if op != 1:
            continue
        try:
            msg = json.loads(data)
        except ValueError:
            continue
        ev = msg.get("event")
        if ev == "ms.channel.connect":
            t = (msg.get("data") or {}).get("token")
            if t and t != tok:
                c = cfg()
                c.setdefault("tvtokens", {})[ip] = t
                save_cfg(c)
            s.settimeout(5)
            return s
        if ev == "ms.channel.unauthorized":
            raise PermissionError("TV-en avviste Kontrollsenter – velg «Tillat» på TV-en og prøv igjen")
        if ev == "ms.channel.timeOut":
            raise TimeoutError("Ingen svarte på TV-en – trykk «Tillat» når spørsmålet dukker opp")


def tv_key(ip, key):
    if key == "on":
        return tv_power_on(ip)
    code = TV_KEYS.get(key)
    if not code:
        raise ValueError("ukjent tast")
    try:
        return _send_key(ip, code)
    except (OSError, ConnectionError) as e:
        if key == "power":                                 # TV-en er helt av: prøv å vekke den
            return tv_power_on(ip)
        raise RuntimeError(f"Får ikke kontakt med TV-en ({e})") from e


def _send_key(ip, code):
    s = _tv_connect(ip)
    try:
        s.sendall(_ws_frame(json.dumps({"method": "ms.remote.control", "params": {
            "Cmd": "Click", "DataOfCmd": code, "Option": "false", "TypeOfRemote": "SendRemoteKey"}})))
        time.sleep(0.3)
    finally:
        s.close()
    return "OK"


def tv_power_on(ip):
    t = cfg().get("tvs", {}).get(ip, {})
    try:
        j = _getjson(f"http://{ip}:8001/api/v2/", 1.5)
        if (j.get("device") or {}).get("PowerState", "on") != "on":
            _send_key(ip, "KEY_POWER")                     # i hvilemodus: av/på-tasten vekker den
            return "TV-en slås på"
        return "TV-en er allerede på"
    except Exception:  # noqa: BLE001
        pass
    if not t.get("mac"):
        raise RuntimeError("Kjenner ikke TV-ens MAC-adresse ennå – slå den på én gang med fjernkontrollen")
    import remote_extra as X
    for _ in range(3):
        X.send_wol(t["mac"])
        time.sleep(0.2)
    return "Sendte «slå på» til TV-en"


def tv_state(ip):
    try:
        j = _getjson(f"http://{ip}:8001/api/v2/", 1.5)
        return {"power": (j.get("device") or {}).get("PowerState", "on"), "paired": bool(cfg().get("tvtokens", {}).get(ip))}
    except Exception:  # noqa: BLE001
        return {"power": "off", "paired": bool(cfg().get("tvtokens", {}).get(ip))}


# --------------------------------------------------------------------------
# Chromecast / Google TV / Nest (Cast v2: TLS på 8009 med små protobuf-meldinger)
# --------------------------------------------------------------------------
NS_CONN = "urn:x-cast:com.google.cast.tp.connection"
NS_RECV = "urn:x-cast:com.google.cast.receiver"
NS_MEDIA = "urn:x-cast:com.google.cast.media"


def _varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _pb_str(field, s):
    b = s.encode()
    return _varint(field << 3 | 2) + _varint(len(b)) + b


def _cast_msg(src, dst, ns, payload):
    body = (_varint(1 << 3) + _varint(0) + _pb_str(2, src) + _pb_str(3, dst) + _pb_str(4, ns)
            + _varint(5 << 3) + _varint(0) + _pb_str(6, json.dumps(payload)))
    return struct.pack(">I", len(body)) + body


def _cast_parse(body):
    i, out = 0, {}
    while i < len(body):
        key, i = _read_varint(body, i)
        f, wt = key >> 3, key & 7
        if wt == 0:
            v, i = _read_varint(body, i)
            out[f] = v
        elif wt == 2:
            ln, i = _read_varint(body, i)
            out[f] = body[i:i + ln]
            i += ln
        else:
            break
    return out


def _read_varint(b, i):
    n = shift = 0
    while True:
        c = b[i]
        i += 1
        n |= (c & 0x7F) << shift
        shift += 7
        if not c & 0x80:
            return n, i


class _Cast:
    def __init__(self, ip):
        raw = socket.create_connection((ip, 8009), 4)
        self.s = ssl._create_unverified_context().wrap_socket(raw)
        self.s.settimeout(4)
        self.rid = 0
        self.connected = set()
        self.connect("receiver-0")

    def close(self):
        try:
            self.s.close()
        except OSError:
            pass

    def send(self, dst, ns, payload):
        self.s.sendall(_cast_msg("sender-0", dst, ns, payload))

    def connect(self, dst):
        if dst not in self.connected:
            self.send(dst, NS_CONN, {"type": "CONNECT"})
            self.connected.add(dst)

    def request(self, dst, ns, payload, want):
        self.rid += 1
        payload = {**payload, "requestId": self.rid}
        self.send(dst, ns, payload)
        end = time.time() + 4
        while time.time() < end:
            ln = struct.unpack(">I", _recv_exact(self.s, 4))[0]
            m = _cast_parse(_recv_exact(self.s, ln))
            try:
                p = json.loads(m.get(6, b"{}"))
            except ValueError:
                continue
            if p.get("type") == "PING":
                self.send(m.get(2, b"receiver-0").decode(), "urn:x-cast:com.google.cast.tp.heartbeat", {"type": "PONG"})
                continue
            if p.get("type") in want and p.get("requestId") in (self.rid, None, 0):
                return p
        raise TimeoutError("enheten svarte ikke")


def _cast_status(c):
    st = c.request("receiver-0", NS_RECV, {"type": "GET_STATUS"}, ("RECEIVER_STATUS",))["status"]
    vol = st.get("volume") or {}
    apps = [a for a in st.get("applications") or [] if not a.get("isIdleScreen")]
    out = {"volume": round((vol.get("level") or 0) * 100), "muted": bool(vol.get("muted")), "app": None,
           "title": "", "playing": None}
    if apps:
        a = apps[0]
        out["app"] = a.get("displayName")
        out["title"] = a.get("statusText", "")
        out["_app"] = a
    return out


def _cast_media(c, app):
    if "urn:x-cast:com.google.cast.media" not in [n.get("name") for n in app.get("namespaces") or []]:
        return None
    t = app["transportId"]
    c.connect(t)
    st = c.request(t, NS_MEDIA, {"type": "GET_STATUS"}, ("MEDIA_STATUS",)).get("status") or []
    return st[0] if st else None


def cast_state(ip):
    c = _Cast(ip)
    try:
        out = _cast_status(c)
        app = out.pop("_app", None)
        if app:
            try:
                m = _cast_media(c, app)
                if m:
                    meta = (m.get("media") or {}).get("metadata") or {}
                    out["title"] = meta.get("title") or out["title"]
                    if meta.get("artist") or meta.get("subtitle"):
                        out["title"] += " – " + (meta.get("artist") or meta.get("subtitle"))
                    out["playing"] = m.get("playerState") == "PLAYING"
            except Exception:  # noqa: BLE001
                pass
        return out
    finally:
        c.close()


def cast_do(ip, what, value=None):
    c = _Cast(ip)
    try:
        if what == "volume":
            c.request("receiver-0", NS_RECV, {"type": "SET_VOLUME", "volume": {"level": max(0, min(100, int(value))) / 100}},
                      ("RECEIVER_STATUS",))
            return "OK"
        if what == "mute":
            c.request("receiver-0", NS_RECV, {"type": "SET_VOLUME", "volume": {"muted": bool(value)}}, ("RECEIVER_STATUS",))
            return "OK"
        st = _cast_status(c)
        app = st.get("_app")
        if not app:
            return "Ingenting spilles"
        if what == "stop":
            c.request("receiver-0", NS_RECV, {"type": "STOP", "sessionId": app["sessionId"]}, ("RECEIVER_STATUS",))
            return "Stoppet"
        m = _cast_media(c, app)
        if not m:
            raise RuntimeError(f"{app.get('displayName', 'Appen')} kan ikke settes på pause herfra")
        typ = {"pause": "PAUSE", "play": "PLAY"}.get(what)
        if not typ:
            raise ValueError("ukjent kommando")
        c.request(app["transportId"], NS_MEDIA, {"type": typ, "mediaSessionId": m["mediaSessionId"]}, ("MEDIA_STATUS",))
        return "OK"
    finally:
        c.close()


# --------------------------------------------------------------------------
# samlet for appen og fjernstyring
# --------------------------------------------------------------------------
def state(rescan=False):
    devs = devices(0 if rescan else 120, wait=rescan)
    out = {"devices": devs, "scanned": _CACHE["at"], "scanning": _CACHE["busy"], "hue": hue_state()}
    hub = next((d for d in devs if "hue" in d["control"]), None)
    out["hue"]["found"] = bool(hub)

    def live(d):
        try:
            if "cast" in d["control"]:
                d["live"] = cast_state(d["ip"])
            elif "samsung" in d["control"]:
                d["live"] = tv_state(d["ip"])
        except Exception:  # noqa: BLE001
            d["live"] = None
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(live, [d for d in devs if set(d["control"]) & {"cast", "samsung"}]))
    return out


def action(a):
    """a = {"do": ..., ...} fra appen. Returnerer en melding til brukeren."""
    do = a.get("do")
    ip = str(a.get("ip", ""))
    if ip and not re.fullmatch(r"\d+\.\d+\.\d+\.\d+", ip):
        raise ValueError("ugyldig adresse")
    if do == "huepair":
        import features as F
        F.hue_pair()
        return "Hue er koblet til ✓"
    if do == "hue":
        hue_light(a.get("light"), a.get("room"), a.get("on"), a.get("bri"), a.get("color"))
        return "OK"
    if do == "tv":
        return tv_key(ip, str(a.get("key", "")))
    if do == "cast":
        return cast_do(ip, str(a.get("what", "")), a.get("value"))
    if do == "rename":
        rename(str(a.get("id", "")), a.get("name", ""))
        return "Lagret"
    if do == "rescan":
        devices(0)
        return "Søker …"
    raise ValueError("ukjent kommando")
