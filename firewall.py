"""Brannmuren på Linux – firewalld (Fedora, openSUSE, Bazzite) og ufw (Ubuntu, Mint, Arch, Manjaro).

Kontrollsenter trenger at maskiner på hjemmenettet (og Tailscale) når PC-en:
  27100/tcp          mobilappen, TV-en, chatten og pushvarsler
  27160–27189/udp    tale og video i chatten
VR (ALVR 9943–9944, WiVRn 9757/5353) bruker samme modul (vr.py).

Portene åpnes bare for private adresser (hjemmenettet) og Tailscale – aldri for hele internett.
"""
import os
import re
import shutil
import subprocess

KS_PORTS = ["27100/tcp", "27160-27189/udp"]
LAN = ["192.168.0.0/16", "10.0.0.0/8", "172.16.0.0/12", "100.64.0.0/10"]
MARK = os.path.expanduser("~/.config/systemmonitor/brannmur.json")


def _run(cmd, t=15):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=t)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError) as e:
        return 127, str(e)


def backend():
    """«firewalld», «ufw» eller None (ingen aktiv brannmur)."""
    if shutil.which("firewall-cmd") and _run(["firewall-cmd", "--state"], 10)[0] == 0:
        return "firewalld"
    if shutil.which("ufw") or os.path.exists("/usr/sbin/ufw"):
        try:                                             # ufw status krever root – les oppsettfila i stedet
            if re.search(r"^ENABLED\s*=\s*yes", open("/etc/ufw/ufw.conf").read(), re.M):
                return "ufw"
        except OSError:
            pass
        if _run(["systemctl", "is-active", "ufw"], 5)[1].strip() == "active":
            return "ufw"
    return None


# ------------------------------------------------------------------ firewalld
def _zones():
    _c, out = _run(["firewall-cmd", "--get-active-zones"], 10)
    zs = [ln.split()[0] for ln in out.splitlines() if ln.strip() and not ln.startswith((" ", "\t"))]
    if not zs:
        _c, d = _run(["firewall-cmd", "--get-default-zone"], 10)
        zs = [d.strip()] if d.strip() else []
    return [z for z in zs if re.fullmatch(r"[\w.-]+", z)]


def _covers(spec, port, proto):
    m = re.fullmatch(r"(\d+)(?:-(\d+))?/(\w+)", spec.strip())
    if not m or m.group(3) != proto:
        return False
    return int(m.group(1)) <= port <= int(m.group(2) or m.group(1))


def _want(ports):
    out = []
    for p in ports:
        rng, proto = p.split("/")
        a, _s, b = rng.partition("-")
        out += [(int(a), proto)] + ([(int(b), proto)] if b else [])
    return out


def _zone_open(z, ports, services=()):
    _c, ports_now = _run(["firewall-cmd", "--zone", z, "--list-ports"], 10)
    _c, svcs = _run(["firewall-cmd", "--zone", z, "--list-services"], 10)
    _c, target = _run(["firewall-cmd", "--zone", z, "--get-target"], 10)
    if target.strip().upper() == "ACCEPT" or any(s in svcs.split() for s in services):
        return True
    specs = ports_now.split()
    return all(any(_covers(sp, port, proto) for sp in specs) for port, proto in _want(ports))


# ------------------------------------------------------------------ felles
def _marked(ports):
    try:
        import json
        return set(ports) <= set(json.load(open(MARK)).get("ufw", []))
    except (OSError, ValueError):
        return False


def _mark(ports):
    import json
    try:
        d = json.load(open(MARK))
    except (OSError, ValueError):
        d = {}
    d["ufw"] = sorted(set(d.get("ufw", [])) | set(ports))
    os.makedirs(os.path.dirname(MARK), exist_ok=True)
    with open(MARK, "w") as f:
        json.dump(d, f)


def ports_open(ports=None, services=()):
    """Slipper brannmuren inn disse portene fra hjemmenettet? (True når det ikke er noen brannmur)"""
    ports = ports or KS_PORTS
    b = backend()
    if b is None:
        return True
    if b == "firewalld":
        zs = _zones()
        return all(_zone_open(z, ports, services) for z in zs) if zs else True
    return _marked(ports)                                # ufw: reglene kan ikke leses uten root


def open_cmds(ports=None):
    """Kommandoene (kjøres som root, én passordforespørsel) som åpner portene for hjemmenettet."""
    ports = ports or KS_PORTS
    b = backend()
    cmds = []
    if b == "firewalld":
        for z in _zones():
            for p in ports:
                cmds.append(f"firewall-cmd --zone={z} --add-port={p} --permanent")
        cmds.append("firewall-cmd --reload")
    elif b == "ufw":
        for p in ports:
            rng, proto = p.split("/")
            for net in LAN:
                cmds.append(f"ufw allow from {net} to any port {rng.replace('-', ':')} proto {proto}")
    return cmds


def open_ports(ports=None, label="Kontrollsenter"):
    """Åpne portene (spør etter passord). Returnerer tekst – kaster ved feil."""
    ports = ports or KS_PORTS
    if ports_open(ports):
        return f"Brannmuren slipper allerede inn {label} ✓"
    cmds = open_cmds(ports)
    if not cmds:
        return f"Brannmuren slipper inn {label} ✓"
    code, out = _run(["pkexec", "sh", "-c", " && ".join(cmds)], 120)
    if code != 0:
        raise RuntimeError("brannmuren kunne ikke endres: " + (out.strip().splitlines() or ["avbrutt"])[-1][:160])
    if backend() == "ufw":
        _mark(ports)
    return f"Brannmuren slipper nå inn {label} fra hjemmenettet ✓"


def check():
    """Til Systemsjekk: slipper brannmuren inn mobilappen, TV-en og chatten?"""
    import syscheck as S
    b = backend()
    if b is None:
        return [S.Result("Brannmur: ingen aktiv brannmur", "ok", "Mobilappen og chatten når PC-en fra hjemmenettet.")]
    if ports_open():
        return [S.Result(f"Brannmur ({b}): slipper inn Kontrollsenter", "ok",
                         "Port 27100 (mobilappen, TV-en, chatten) og 27160–27189 (tale/video) er åpne for hjemmenettet.")]
    return [S.Result(f"Brannmur ({b}): stenger ute mobilappen og chatten", "warn",
                     "Telefonen, TV-en og de andre PC-ene når ikke Kontrollsenter. Åpne port 27100 og 27160–27189 "
                     "for hjemmenettet (bare private adresser og Tailscale – ikke internett).",
                     fix_label="Åpne for hjemmenettet", root_cmds=open_cmds())]
