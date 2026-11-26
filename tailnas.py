"""NAS-en utenfor hjemmet – gjennom Tailscale (kryptert, ingen porter åpnes mot internett).

En PC hjemme som står på «deler hjemmenettet» (Tailscale subnet route, f.eks. 192.168.1.0/24). Ruten godkjennes én
gang på login.tailscale.com. Da når de andre enhetene dine i Tailscale NAS-en på vanlig adresse (192.168.1.3) også
borte: mobilen og Windows bruker ruten av seg selv, Linux-PC-er må slå på «bruk delte nett» (accept-routes).
"""
import ipaddress
import json
import os
import shutil
import subprocess
import sys

IS_WIN = sys.platform == "win32"
ADMIN_URL = "https://login.tailscale.com/admin/machines"


def _exe():
    if IS_WIN:
        p = os.path.expandvars(r"%ProgramFiles%\Tailscale\tailscale.exe")
        return p if os.path.exists(p) else shutil.which("tailscale")
    return shutil.which("tailscale")


def _status():
    exe = _exe()
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "status", "--json"], capture_output=True, text=True, timeout=10)
        return json.loads(r.stdout) if r.stdout.strip() else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _prefs():
    exe = _exe()
    try:
        r = subprocess.run([exe, "debug", "prefs"], capture_output=True, text=True, timeout=10)
        return json.loads(r.stdout)
    except (OSError, ValueError, TypeError, subprocess.SubprocessError):
        return {}


def home_subnet():
    """Hjemmenettet NAS-en står på, f.eks. «192.168.1.0/24»."""
    try:
        import nasfiles
        ip = ipaddress.ip_address(nasfiles.host())
    except (ValueError, Exception):  # noqa: BLE001
        return None
    return str(ipaddress.ip_network(f"{ip}/24", strict=False)) if ip.is_private else None


def status():
    """{"installed", "running", "me", "here_shares", "approved", "router", "accept", "subnet"}"""
    st = _status()
    sub = home_subnet()
    out = {"installed": bool(_exe()), "running": False, "subnet": sub, "here_shares": False, "approved": False,
           "router": None, "accept": IS_WIN}
    if not st:
        return out
    out["running"] = st.get("BackendState") == "Running"
    me = st.get("Self") or {}
    out["me"] = me.get("HostName")
    pr = _prefs()
    out["here_shares"] = bool(sub and sub in (pr.get("AdvertiseRoutes") or []))
    out["approved"] = bool(sub and sub in (me.get("PrimaryRoutes") or []))
    out["accept"] = IS_WIN or bool(pr.get("RouteAll"))
    if out["approved"]:
        out["router"] = me.get("HostName")
    for p in (st.get("Peer") or {}).values():
        if sub and sub in (p.get("PrimaryRoutes") or []):
            out["router"] = p.get("HostName")
            out["router_online"] = bool(p.get("Online"))
    return out


def _root(cmd):
    """Kjør som administrator (Linux: pkexec – spør om passord; Windows: UAC)."""
    if IS_WIN:
        argl = ",".join("'" + a + "'" for a in cmd[1:])
        ps = f"Start-Process -FilePath '{cmd[0]}' -ArgumentList {argl} -Verb RunAs -Wait -WindowStyle Hidden"
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=120)
    else:
        r = subprocess.run(["pkexec", *cmd], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout).strip()
                           else "avbrutt")


def share_home(on=True):
    """Denne PC-en (hjemme) deler hjemmenettet i Tailscale. Ruten må godkjennes på login.tailscale.com én gang."""
    sub = home_subnet()
    exe = _exe()
    if not exe or not sub:
        raise RuntimeError("Tailscale er ikke installert" if not exe else "fant ikke hjemmenettet til NAS-en")
    routes = sub if on else ""
    if IS_WIN:
        _root([exe, "set", f"--advertise-routes={routes}"])
    else:
        # ruteren må videresende pakker (IP forwarding) – lagres så det gjelder etter omstart også
        script = (f'{exe} set --advertise-routes={routes} && '
                  + ("printf 'net.ipv4.ip_forward = 1\\nnet.ipv6.conf.all.forwarding = 1\\n' > "
                     "/etc/sysctl.d/99-kontrollsenter-tailscale.conf && sysctl -q -p "
                     "/etc/sysctl.d/99-kontrollsenter-tailscale.conf" if on else
                     "rm -f /etc/sysctl.d/99-kontrollsenter-tailscale.conf"))
        _root(["sh", "-c", script])
    return ("Hjemmenettet deles fra denne PC-en ✓ – godkjenn ruten én gang på login.tailscale.com (åpnes nå)"
            if on else "Hjemmenettet deles ikke lenger")


def use_home(on=True):
    """Denne PC-en (Linux) bruker hjemmenettet når den er borte (Windows og mobilen gjør det av seg selv)."""
    exe = _exe()
    if not exe:
        raise RuntimeError("Tailscale er ikke installert – installer det under Programmer")
    if IS_WIN:
        return "Windows bruker delte nett av seg selv ✓"
    _root([exe, "set", f"--accept-routes={'true' if on else 'false'}"])
    return "Denne PC-en når NAS-en gjennom Tailscale når den er borte ✓" if on else "Av"
