"""Hjemmeporten: en Raspberry Pi hjemme som gjør NAS-en tilgjengelig utenfor hjemmet uten at noen PC står på.

Kontrollsenter setter den opp over SSH (passordet til Pi-en skrives én gang; deretter brukes en egen nøkkel):
  * Tailscale med «del hjemmenettet» (subnet route) – laptoper og mobilen når NAS-en direkte gjennom Tailscale
  * nasgate.py – en liten NAS-utforsker for mobilappen (svarer bare fra Tailscale/hjemmenettet, med egen nøkkel)
  * automatiske sikkerhetsoppdateringer (unattended-upgrades)
Nøkkelen til nasgate deles bare med mobiler med full tilgang (gjennom PC-en de er paret med), aldri via NAS-en.
"""
import json
import os
import re
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request

IS_WIN = sys.platform == "win32"
HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.expanduser("~/.config/systemmonitor/hjemmeport.json")
KEYFILE = os.path.expanduser("~/.config/systemmonitor/hjemmeport_id")
KNOWN = os.path.expanduser("~/.config/systemmonitor/hjemmeport_known_hosts")
PORT = 27110
PI_MACS = ("b8:27:eb", "dc:a6:32", "e4:5f:01", "d8:3a:dd", "2c:cf:67", "28:cd:c1")


def cfg():
    try:
        with open(CFG, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(c):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    fd = os.open(CFG, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(c, f, indent=1)


# ------------------------------------------------------------------ finn Pi-en
def find():
    """[(ip, navn)] for Raspberry Pi-er på hjemmenettet."""
    out = []
    try:
        ip = socket.gethostbyname("hjemmeport.local")
        out.append((ip, "hjemmeport"))
    except OSError:
        pass
    if IS_WIN:
        r = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=10)
        for m in re.finditer(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-f-]{17})", r.stdout, re.I):
            if m.group(2).lower().replace("-", ":").startswith(PI_MACS):
                out.append((m.group(1), "Raspberry Pi"))
        return list(dict.fromkeys(out))
    try:
        import nasfiles
        base = nasfiles.host().rsplit(".", 1)[0]
    except Exception:  # noqa: BLE001
        base = "192.168.1"
    procs = [subprocess.Popen(["ping", "-c1", "-W1", f"{base}.{i}"], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL) for i in range(1, 255)]
    for p in procs:
        try:
            p.wait(3)
        except subprocess.TimeoutExpired:
            p.kill()
    r = subprocess.run(["ip", "neigh", "show"], capture_output=True, text=True, timeout=10)
    for ln in r.stdout.splitlines():
        parts = ln.split()
        if "lladdr" in parts:
            mac = parts[parts.index("lladdr") + 1].lower()
            if mac.startswith(PI_MACS):
                out.append((parts[0], "Raspberry Pi"))
    return list(dict.fromkeys(out))


# ------------------------------------------------------------------ SSH
def _ssh_base(ip, user):
    port = os.environ.get("KS_PI_SSH_PORT")            # (bare for testing mot en container)
    return ["ssh", "-o", f"UserKnownHostsFile={KNOWN}", "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=15"] + (["-p", port] if port else []) + \
        [f"{user}@{ip}"]


def _run_ssh(ip, user, command, password=None, stdin=None, timeout=900):
    """Kjør en kommando på Pi-en. Med passord: via SSH_ASKPASS (aldri på kommandolinja). Uten: med nøkkelen."""
    args = _ssh_base(ip, user)
    env = dict(os.environ)
    askpass = None
    if password is not None:
        fd, askpass = tempfile.mkstemp(prefix="ks-askpass-", suffix=".cmd" if IS_WIN else ".sh")
        with os.fdopen(fd, "w") as f:
            f.write("@echo off\r\necho %KS_PI_PW%\r\n" if IS_WIN else '#!/bin/sh\nprintf "%s\\n" "$KS_PI_PW"\n')
        os.chmod(askpass, stat.S_IRWXU)
        env.update(SSH_ASKPASS=askpass, SSH_ASKPASS_REQUIRE="force", KS_PI_PW=password, DISPLAY=env.get("DISPLAY", ":0"))
        args[1:1] = ["-o", "PreferredAuthentications=password,keyboard-interactive", "-o", "PubkeyAuthentication=no"]
    else:
        args[1:1] = ["-i", KEYFILE, "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes"]
    try:
        r = subprocess.run(args + [command], input=stdin, capture_output=True, text=True, timeout=timeout, env=env)
    finally:
        if askpass:
            os.unlink(askpass)
    if r.returncode == 255:
        err = (r.stderr or "").strip().splitlines()
        e = err[-1] if err else "ingen kontakt"
        if "Permission denied" in e:
            raise RuntimeError("feil brukernavn eller passord til Pi-en")
        raise RuntimeError("fikk ikke kontakt med Pi-en: " + e)
    return r


def _keypair():
    if not os.path.exists(KEYFILE):
        os.makedirs(os.path.dirname(KEYFILE), exist_ok=True)
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "kontrollsenter-hjemmeport",
                        "-f", KEYFILE], check=True, timeout=30)
    with open(KEYFILE + ".pub", encoding="utf-8") as f:
        return f.read().strip()


SETUP = r"""
set -e
export DEBIAN_FRONTEND=noninteractive
step() { echo "@@STEG $*"; }
step "Oppdaterer pakkelisten"
apt-get update -qq
step "Installerer smbclient og automatiske sikkerhetsoppdateringer"
apt-get install -y -qq smbclient unattended-upgrades curl python3 >/dev/null
printf 'APT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";\n' > /etc/apt/apt.conf.d/20auto-upgrades
step "Installerer Tailscale"
command -v tailscale >/dev/null || curl -fsSL https://tailscale.com/install.sh | sh >/dev/null
systemctl enable --now tailscaled >/dev/null 2>&1
step "Slår på videresending (hjemmenettet deles)"
printf 'net.ipv4.ip_forward = 1\nnet.ipv6.conf.all.forwarding = 1\n' > /etc/sysctl.d/99-hjemmeport.conf
sysctl -q -p /etc/sysctl.d/99-hjemmeport.conf
step "Installerer NAS-tjenesten"
install -m 0755 /tmp/nasgate.py /usr/local/bin/nasgate.py
install -m 0640 -o root -g "$KSUSER" /tmp/nasgate.json /etc/nasgate.json
rm -f /tmp/nasgate.py /tmp/nasgate.json
cat > /etc/systemd/system/nasgate.service <<EOF
[Unit]
Description=Hjemmeport – NAS-disken over Tailscale (Kontrollsenter)
After=network-online.target tailscaled.service
Wants=network-online.target

[Service]
User=$KSUSER
ExecStart=/usr/bin/python3 /usr/local/bin/nasgate.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now nasgate.service >/dev/null
step "Kobler til Tailscale"
tailscale up --hostname=hjemmeport --advertise-routes="$KSSUBNET" --accept-dns=false --timeout=8s >/dev/null 2>&1 || true
echo "@@FERDIG"
"""


def setup(ip, user, password, progress=None):
    """Sett opp Pi-en. progress(tekst). Returnerer {"auth_url"} hvis Tailscale-innlogging trengs."""
    import nasfiles
    import tailnas
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", user or ""):
        raise ValueError("ugyldig brukernavn")
    if not re.fullmatch(r"[\d.]{7,15}|[\w.-]+\.local", ip or ""):
        raise ValueError("ugyldig adresse")
    say = progress or (lambda _t: None)
    say("Kobler til Pi-en …")
    pub = _keypair()
    r = _run_ssh(ip, user, "mkdir -p ~/.ssh && chmod 700 ~/.ssh && grep -qxF '%s' ~/.ssh/authorized_keys 2>/dev/null "
                           "|| echo '%s' >> ~/.ssh/authorized_keys; chmod 600 ~/.ssh/authorized_keys; uname -m"
                 % (pub, pub), password=password, timeout=60)
    if r.returncode != 0:
        raise RuntimeError("Pi-en godtok ikke nøkkelen: " + (r.stderr or r.stdout).strip()[-200:])
    c = cfg()
    key = c.get("key") or secrets.token_urlsafe(24)
    subnet = tailnas.home_subnet() or "192.168.1.0/24"
    gate_cfg = json.dumps({"host": nasfiles.host(), "share": nasfiles.default_share(), "key": key, "port": PORT})
    with open(os.path.join(HERE, "pi", "nasgate.py"), encoding="utf-8") as f:
        code = f.read()
    say("Sender NAS-tjenesten til Pi-en …")
    for name, body in (("nasgate.py", code), ("nasgate.json", gate_cfg)):
        r = _run_ssh(ip, user, f"umask 077; cat > /tmp/{name}", stdin=body, timeout=60)
        if r.returncode != 0:
            raise RuntimeError("kunne ikke sende filene: " + r.stderr.strip()[-200:])
    say("Installerer (tar 3–8 minutter på en Pi 3) …")
    script = f"export KSUSER='{user}' KSSUBNET='{subnet}'\n" + SETUP
    args = _ssh_base(ip, user)
    args[1:1] = ["-i", KEYFILE, "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes"]
    p = subprocess.Popen(args + ["sudo -S -p '' bash -s"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True)
    p.stdin.write(password + "\n" + script)
    p.stdin.close()
    tail = []
    for ln in p.stdout:
        ln = ln.rstrip()
        tail = (tail + [ln])[-15:]
        if ln.startswith("@@STEG "):
            say(ln[7:] + " …")
    p.wait(1800)
    if p.returncode != 0 or "@@FERDIG" not in "\n".join(tail):
        raise RuntimeError("oppsettet stoppet: " + " / ".join(x for x in tail if x and not x.startswith("@@"))[-300:])
    c.update(ip=ip, user=user, key=key, port=PORT, subnet=subnet, t=time.time())
    _save(c)
    say("Ser etter Tailscale-innlogging …")
    return {"auth_url": auth_url(), **status()}


def _ts_status():
    c = cfg()
    if not c.get("ip"):
        return None
    try:
        r = _run_ssh(c["ip"], c["user"], "tailscale status --json 2>/dev/null", timeout=30)
        return json.loads(r.stdout) if r.stdout.strip() else None
    except (RuntimeError, ValueError, subprocess.SubprocessError, OSError):
        return None


def auth_url():
    """Innloggingslenken til Tailscale på Pi-en (første gang), eller None når den er logget inn."""
    st = _ts_status()
    if not st:
        return None
    if st.get("BackendState") == "Running":
        return None
    return st.get("AuthURL") or None


def _hello(host, timeout=3):
    try:
        with urllib.request.urlopen(f"http://{host}:{PORT}/api/hello", timeout=timeout) as r:
            return json.loads(r.read()).get("app") == "Hjemmeport"
    except (OSError, ValueError):
        return False


def status():
    """{"setup", "ip", "ts_ip", "online", "nas_url", "route_ok"} – det appen viser."""
    c = cfg()
    out = {"setup": bool(c.get("key")), "ip": c.get("ip"), "ts_ip": c.get("ts_ip")}
    if not out["setup"]:
        return out
    # Tailscale-adressen til Pi-en (fra denne PC-ens Tailscale)
    try:
        import tailnas
        st = tailnas._status() or {}
        for p in (st.get("Peer") or {}).values():
            if (p.get("HostName") or "").startswith("hjemmeport"):
                ips = [i for i in p.get("TailscaleIPs") or [] if "." in i]
                if ips:
                    out["ts_ip"] = ips[0]
                    out["ts_online"] = bool(p.get("Online"))
                    out["route_ok"] = (c.get("subnet") in (p.get("PrimaryRoutes") or []))
        if out.get("ts_ip") and out["ts_ip"] != c.get("ts_ip"):
            c["ts_ip"] = out["ts_ip"]
            _save(c)
    except Exception:  # noqa: BLE001
        pass
    out["online"] = _hello(c["ip"]) or bool(out.get("ts_ip") and _hello(out["ts_ip"]))
    return out


def gate_for_phone():
    """Adressen og nøkkelen mobilen bruker når ingen PC svarer – bare til mobiler med full tilgang."""
    c = cfg()
    if not c.get("key"):
        return None
    host = c.get("ts_ip") or c.get("ip")
    return {"url": f"http://{host}:{PORT}/", "lan": f"http://{c.get('ip')}:{PORT}/", "key": c["key"]}


def forget():
    c = cfg()
    for k in ("key", "ip", "user", "ts_ip"):
        c.pop(k, None)
    _save(c)
    return "Hjemmeporten er glemt her (Pi-en er urørt)"


def ssh_available():
    return bool(shutil.which("ssh") and shutil.which("ssh-keygen"))
