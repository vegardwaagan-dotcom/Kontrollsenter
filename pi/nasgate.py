#!/usr/bin/env python3
"""Hjemmeporten: NAS-disken over Tailscale når ingen PC er på (kjører på en Raspberry Pi hjemme).

Én fil, bare Python-standardbiblioteket + smbclient. Satt opp av Kontrollsenter (hjemmeport.py).
  * Svarer bare fra Tailscale (100.64.0.0/10) og hjemmenettet – og krever nøkkelen fra oppsettet.
  * Siden «/» er en enkel NAS-utforsker (mobilappen åpner den når ingen PC svarer).
  * API: /api/shares, /api/list, /api/file (nedlasting), /api/upload (rå fil), /api/do (mkdir/rename/delete/login).
Innstillinger: /etc/nasgate.json  {"host": "192.168.1.3", "share": "Public", "key": "...", "port": 27110}
Innlogging til private mapper lagres i ~/.config/nasgate/logins.json (bare lesbar for brukeren).
"""
import hmac
import ipaddress
import json
import mimetypes
import os
import re
import socket
import subprocess
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

CFG_PATH = os.environ.get("NASGATE_CFG", "/etc/nasgate.json")
LOGINS = os.path.expanduser("~/.config/nasgate/logins.json")
CACHE = os.path.expanduser("~/.cache/nasgate")
BAD = re.compile(r'["\\\x00-\x1f;|<>*?]')
NETS = [ipaddress.ip_network(n) for n in ("100.64.0.0/10", "fd7a:115c:a1e0::/48", "127.0.0.0/8", "::1/128",
                                          "192.168.0.0/16", "10.0.0.0/8", "172.16.0.0/12")]
LS = re.compile(r"^  (.+?)\s+([A-Z]*)\s+(\d+)\s+\w{3} (\w{3})\s+(\d+) (\d\d:\d\d:\d\d) (\d{4})$")
MON = {m: i for i, m in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
                                  1)}


def cfg():
    with open(CFG_PATH, encoding="utf-8") as f:
        c = json.load(f)
    c.setdefault("share", "Public")
    c.setdefault("port", 27110)
    return c


def _clean(path):
    parts = [p for p in str(path or "").replace("\\", "/").split("/") if p not in ("", ".")]
    for p in parts:
        if p == ".." or BAD.search(p) or len(p) > 255:
            raise ValueError("ugyldig navn")
    return "/".join(parts)


def _name(n):
    n = _clean(n)
    if not n or "/" in n:
        raise ValueError("ugyldig navn")
    return n


def _share(s):
    s = str(s or cfg()["share"])
    if not re.fullmatch(r"[\w .$-]{1,80}", s):
        raise ValueError("ugyldig deling")
    return s


def _logins():
    try:
        with open(LOGINS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _nice(err):
    for k, v in (("ACCESS_DENIED", "ingen tilgang – logg inn med brukeren din"),
                 ("LOGON_FAILURE", "feil brukernavn eller passord"), ("BAD_NETWORK_NAME", "fant ikke delingen"),
                 ("OBJECT_NAME_NOT_FOUND", "finnes ikke"), ("OBJECT_PATH_NOT_FOUND", "finnes ikke"),
                 ("OBJECT_NAME_COLLISION", "finnes fra før"), ("HOST_UNREACHABLE", "NAS-en svarer ikke"),
                 ("IO_TIMEOUT", "NAS-en svarer ikke"), ("CONNECTION_REFUSED", "NAS-en svarer ikke")):
        if k in err:
            return v
    return err or "ukjent feil fra NAS-en"


def smb(share, cmds, timeout=120):
    args = ["smbclient", f"//{cfg()['host']}/{share}", "-c", cmds]
    cred = _logins().get(share)
    authf = None
    try:
        if cred:
            fd, authf = tempfile.mkstemp(prefix="nasgate-")
            with os.fdopen(fd, "w") as f:
                f.write(f"username = {cred['user']}\npassword = {cred['password']}\n")
            args[1:1] = ["-A", authf]
        else:
            args[1:1] = ["-N"]
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    finally:
        if authf:
            os.unlink(authf)
    out = (r.stdout + r.stderr).strip()
    if r.returncode != 0 or "NT_STATUS_" in out:
        err = next((ln for ln in out.splitlines() if "NT_STATUS_" in ln), out.splitlines()[-1] if out else "")
        raise RuntimeError(_nice(err.strip()))
    return out


def _q(path):
    return '"' + path.replace("/", "\\") + '"'


def _cd(folder):
    return f"cd {_q(folder)}; " if folder else ""


def shares():
    r = subprocess.run(["smbclient", "-N", "-g", "-L", f"//{cfg()['host']}"], capture_output=True, text=True,
                       timeout=30)
    names = [p[1] for p in (ln.split("|") for ln in r.stdout.splitlines()) if len(p) >= 2 and p[0] == "Disk"]
    d = cfg()["share"]
    return sorted(names or [d], key=lambda n: (n != d, n.lower()))


def list_dir(share, path):
    share, path = _share(share), _clean(path)
    items = []
    for ln in smb(share, _cd(path) + "ls", 60).splitlines():
        m = LS.match(ln)
        if not m:
            continue
        name, attr, size = m.group(1), m.group(2), int(m.group(3))
        if name in (".", "..") or name.startswith(".") or "H" in attr:
            continue
        try:
            t = int(time.mktime((int(m.group(7)), MON.get(m.group(4), 1), int(m.group(5)),
                                 *map(int, m.group(6).split(":")), 0, 0, -1)))
        except (ValueError, OverflowError):
            t = 0
        items.append({"name": name, "dir": "D" in attr, "size": 0 if "D" in attr else size, "t": t})
    return sorted(items, key=lambda x: (not x["dir"], x["name"].lower()))


def fetch(share, path):
    share, path = _share(share), _clean(path)
    folder, _s, name = path.rpartition("/")
    if not name:
        raise ValueError("ingen fil valgt")
    os.makedirs(CACHE, exist_ok=True)
    fd, dest = tempfile.mkstemp(dir=CACHE)
    os.close(fd)
    smb(share, _cd(folder) + f'get "{name}" "{dest}"', 3600)
    return dest, name


def do(a):
    share, path = _share(a.get("share")), _clean(a.get("path"))
    act = a.get("do")
    folder, _s, last = path.rpartition("/")
    if act == "mkdir":
        n = _name(a.get("name"))
        smb(share, _cd(path) + f'mkdir "{n}"', 60)
        return f"Mappa «{n}» er laget"
    if act == "rename":
        n = _name(a.get("name"))
        smb(share, _cd(folder) + f'rename "{last}" "{n}"', 60)
        return f"Nytt navn: {n}"
    if act == "delete":
        if not last:
            raise ValueError("ingen fil valgt")
        smb(share, _cd(folder) + (f'deltree "{last}"' if a.get("dir") else f'del "{last}"'), 600)
        return f"{last} er slettet"
    if act == "login":
        user = str(a.get("user") or "")
        if not re.fullmatch(r"[\w.@ -]{1,64}", user):
            raise ValueError("ugyldig brukernavn")
        logins = _logins()
        old = logins.get(share)
        logins[share] = {"user": user, "password": str(a.get("password") or "")}
        os.makedirs(os.path.dirname(LOGINS), exist_ok=True)
        fd = os.open(LOGINS, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(logins, f)
        try:
            list_dir(share, "")
        except RuntimeError:
            if old:
                logins[share] = old
            else:
                logins.pop(share, None)
            fd = os.open(LOGINS, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(logins, f)
            raise
        return "Logget inn"
    raise ValueError("ukjent handling")


class H(BaseHTTPRequestHandler):
    server_version = "Hjemmeport/1"

    def log_message(self, *_a):
        pass

    def _ok_client(self):
        try:
            ip = ipaddress.ip_address(self.client_address[0].replace("::ffff:", ""))
        except ValueError:
            return False
        return any(ip in n for n in NETS)

    def _key(self):
        q = parse_qs(urlparse(self.path).query)
        k = self.headers.get("X-Key") or (q.get("k") or [""])[0]
        return bool(k) and hmac.compare_digest(k, cfg()["key"])

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        data = body if isinstance(body, bytes) else (body if isinstance(body, str) else json.dumps(body)).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _guard(self):
        if not self._ok_client():
            self._send(403, {"error": "bare Tailscale og hjemmenettet"})
            return False
        if not self._key():
            self._send(401, {"error": "feil eller manglende nøkkel"})
            return False
        return True

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        arg = lambda k: (q.get(k) or [""])[0]  # noqa: E731
        if u.path in ("/", "/index.html"):
            if not self._ok_client():
                return self._send(403, {"error": "bare Tailscale og hjemmenettet"})
            return self._send(200, PAGE, "text/html; charset=utf-8")
        if u.path == "/api/hello":
            return self._send(200, {"app": "Hjemmeport", "nas": cfg()["host"]})
        if not self._guard():
            return
        try:
            if u.path == "/api/shares":
                return self._send(200, {"shares": shares(), "default": cfg()["share"]})
            if u.path == "/api/list":
                return self._send(200, {"items": list_dir(arg("share"), arg("path"))})
            if u.path == "/api/file":
                fp, name = fetch(arg("share"), arg("path"))
                try:
                    size = os.path.getsize(fp)
                    self.send_response(200)
                    self.send_header("Content-Type", mimetypes.guess_type(name)[0] or "application/octet-stream")
                    self.send_header("Content-Length", str(size))
                    self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(name))
                    self.end_headers()
                    with open(fp, "rb") as f:
                        while chunk := f.read(262144):
                            self.wfile.write(chunk)
                finally:
                    os.unlink(fp)
                return None
        except ValueError as e:
            return self._send(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            return self._send(502, {"error": str(e)})
        return self._send(404, {"error": "finnes ikke"})

    def do_POST(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        arg = lambda k: (q.get(k) or [""])[0]  # noqa: E731
        if not self._guard():
            return
        n = int(self.headers.get("Content-Length") or 0)
        try:
            if u.path == "/api/upload":
                if not 0 < n <= 8 * 1024 ** 3:
                    return self._send(413, {"error": "fila er tom eller større enn 8 GB"})
                share, folder, name = _share(arg("share")), _clean(arg("path")), _name(arg("name"))
                os.makedirs(CACHE, exist_ok=True)
                fd, tmp = tempfile.mkstemp(dir=CACHE)
                try:
                    with os.fdopen(fd, "wb") as f:
                        left = n
                        while left > 0:
                            chunk = self.rfile.read(min(1 << 20, left))
                            if not chunk:
                                break
                            f.write(chunk)
                            left -= len(chunk)
                    if left:
                        return self._send(400, {"error": "opplastingen ble avbrutt"})
                    smb(share, _cd(folder) + f'put "{tmp}" "{name}"', 3600)
                finally:
                    os.unlink(tmp)
                return self._send(200, {"ok": True, "msg": f"{name} er lastet opp"})
            if u.path == "/api/do":
                if n > 64 * 1024:
                    return self._send(413, {"error": "for stor forespørsel"})
                return self._send(200, {"ok": True, "msg": do(json.loads(self.rfile.read(n) or b"{}"))})
        except ValueError as e:
            return self._send(400, {"ok": False, "error": str(e)})
        except Exception as e:  # noqa: BLE001
            return self._send(502, {"ok": False, "error": str(e)})
        return self._send(404, {"error": "finnes ikke"})


PAGE = """<!doctype html><html lang="nb"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>NAS-disken</title><style>
:root{--bg:#0f1016;--card:#191a23;--card2:#23242f;--fg:#f3f3f7;--dim:#9a9bab;--acc:#5b8cff;--line:rgba(255,255,255,.07)}
@media (prefers-color-scheme: light){:root{--bg:#f3f4f8;--card:#fff;--card2:#eef0f5;--fg:#17181f;--dim:#646678;--line:rgba(0,0,0,.08)}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.4 system-ui,sans-serif;padding:16px}
h1{font-size:22px;margin:0 0 4px}.dim{color:var(--dim);font-size:14px}.card{background:var(--card);border-radius:16px;padding:14px;margin-top:12px}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}select,input,button,label.b{font:inherit;color:var(--fg);background:var(--card2);
border:0;border-radius:12px;padding:10px 12px}button,label.b{cursor:pointer;font-weight:600}select{flex:1;min-width:120px}
.it{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:10px 2px;border-bottom:1px solid var(--line);cursor:pointer}
.it span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}.it button{padding:4px 12px}
#login{display:none;flex-direction:column;gap:8px;margin-top:8px}.primary{background:var(--acc);color:#fff}
</style></head><body><h1>📁 NAS-disken</h1><div class="dim" id="sub">via hjemmeporten</div>
<div class="card"><div class="row"><select id="share"></select><button id="up">⬆️</button><button id="new">＋ Mappe</button>
<label class="b">⤴ Last opp<input type="file" id="file" multiple hidden></label></div>
<div class="dim" id="path" style="margin-top:8px"></div><div id="login"><input id="user" placeholder="Brukernavn på NAS-en">
<input id="pw" type="password" placeholder="Passord"><button class="primary" id="go">Logg inn</button></div>
<div id="list"></div><div class="dim" id="msg"></div></div>
<script>
const K=(location.hash.match(/k=([^&]+)/)||[])[1]||localStorage.getItem("ng_k")||"";if(K)localStorage.setItem("ng_k",decodeURIComponent(K));
const key=localStorage.getItem("ng_k")||"";history.replaceState(null,"",location.pathname);
const $=(s)=>document.querySelector(s),esc=(s)=>String(s).replace(/[&<>"]/g,(c)=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const hum=(n)=>{const u=["B","kB","MB","GB","TB"];let i=0;while(n>=1024&&i<4){n/=1024;i++}return(i?n.toFixed(1):n)+" "+u[i]};
let share="",path="";
async function api(p,o){o=o||{};o.headers=Object.assign({"X-Key":key},o.headers||{});const r=await fetch(p,o);const j=await r.json().catch(()=>({}));
 if(!r.ok||j.ok===false)throw new Error(j.error||r.statusText);return j}
const msg=(t)=>$("#msg").textContent=t;
async function init(){try{const r=await api("/api/shares");share=r.default;$("#share").innerHTML=r.shares.map(s=>"<option"+(s===share?" selected":"")+">"+esc(s)+"</option>").join("");go("")}
 catch(e){msg("✗ "+e.message+(key?"":" – åpne siden fra Kontrollsenter-appen"))}}
async function go(p){path=p;$("#path").textContent="📁 "+share+(p?" › "+p.split("/").join(" › "):"");msg("Henter …");
 try{const r=await api("/api/list?share="+encodeURIComponent(share)+"&path="+encodeURIComponent(p));$("#login").style.display="none";msg(r.items.length?"":"Mappa er tom");
  $("#list").innerHTML=r.items.map((it,i)=>'<div class="it" data-i="'+i+'"><span>'+(it.dir?"📁 ":"📄 ")+"<b>"+esc(it.name)+"</b>"+(it.dir?"":' <small class="dim">'+hum(it.size)+"</small>")+'</span><button data-m="'+i+'">⋯</button></div>').join("");
  document.querySelectorAll(".it").forEach(row=>{const it=r.items[+row.dataset.i],full=(p?p+"/":"")+it.name;
   row.onclick=(e)=>{if(e.target.dataset.m!==undefined)return;it.dir?go(full):dl(full,it.name)};row.querySelector("[data-m]").onclick=()=>more(full,it)})}
 catch(e){$("#list").innerHTML="";msg("✗ "+e.message);$("#login").style.display=/logg inn|passord/i.test(e.message)?"flex":"none"}}
function dl(full,name){const u="/api/file?share="+encodeURIComponent(share)+"&path="+encodeURIComponent(full)+"&k="+encodeURIComponent(key);
 if(window.KS&&KS.download)KS.download(location.origin+u,name);else{const a=document.createElement("a");a.href=u;a.download=name;a.click()}msg("Laster ned "+name+" …")}
async function act(b){try{const r=await api("/api/do",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)});msg(r.msg)}catch(e){msg("✗ "+e.message)}go(path)}
function more(full,it){const c=prompt((it.dir?"Mappe: ":"Fil: ")+it.name+"\\nSkriv nytt navn – eller «slett» for å slette:",it.name);if(c===null||c.trim()===it.name)return;
 if(c.trim().toLowerCase()==="slett"){if(confirm("Slette «"+it.name+"» fra NAS-en? Det kan ikke angres."))act({do:"delete",share,path:full,dir:it.dir})}else act({do:"rename",share,path:full,name:c.trim()})}
$("#share").onchange=()=>{share=$("#share").value;go("")};$("#up").onclick=()=>go(path.includes("/")?path.slice(0,path.lastIndexOf("/")):"");
$("#new").onclick=()=>{const n=prompt("Navnet på den nye mappa:");if(n&&n.trim())act({do:"mkdir",share,path,name:n.trim()})};
$("#go").onclick=()=>{act({do:"login",share,user:$("#user").value.trim(),password:$("#pw").value});$("#pw").value=""};
$("#file").onchange=async()=>{const fs=[...$("#file").files];$("#file").value="";for(const[n,f]of fs.entries()){msg("Laster opp "+(n+1)+"/"+fs.length+": "+f.name+" …");
 try{await api("/api/upload?share="+encodeURIComponent(share)+"&path="+encodeURIComponent(path)+"&name="+encodeURIComponent(f.name),{method:"POST",headers:{"Content-Type":"application/octet-stream"},body:f})}
 catch(e){msg("✗ "+f.name+": "+e.message);return}}msg(fs.length+" fil(er) lastet opp");go(path)};
init();
</script></body></html>"""


class Server6(ThreadingHTTPServer):
    """Lytter på både IPv4 og IPv6 (Tailscale bruker begge)."""
    address_family = socket.AF_INET6
    daemon_threads = True

    def server_bind(self):
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()


def main():
    port = int(cfg()["port"])
    try:
        srv = Server6(("::", port), H)
    except OSError:                                   # uten IPv6: bare IPv4
        srv = ThreadingHTTPServer(("0.0.0.0", port), H)
        srv.daemon_threads = True
    srv.serve_forever()


if __name__ == "__main__":
    main()
