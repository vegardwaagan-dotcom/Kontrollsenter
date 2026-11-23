"""Programmene funksjonene trenger: installeres etter velkomstveiviseren (og når funksjonene endres), og
avinstalleres når en funksjon slås av – men bare det Kontrollsenter selv har installert.

Installasjonsskriptet (Linux) og Setup.exe (Windows) legger bare inn selve Kontrollsenter (+ GTK/Python, og på
Windows LibreHardwareMonitor som Oversikt trenger for temperaturene). Resten kommer herfra, med fremdrift:
prosent, tid igjen og nedlastingshastighet.

Hva Kontrollsenter har installert, huskes i komponenter.json – programmer du hadde fra før, røres aldri.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

IS_WIN = sys.platform == "win32"
CFG = os.path.expanduser("~/.config/systemmonitor/komponenter.json")
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DEST_TRCC = os.path.expanduser("~/.local/share/systemmonitor/trcc-venv")
TEST = os.environ.get("KS_KOMP_TEST") == "1"            # tester: falske komponenter, ingenting installeres

# (id, navn, funksjoner som trenger den, plattform, maskinvare som må finnes, type, data, ca. MB å laste ned)
COMPONENTS = [
    ("openrgb", "OpenRGB (RGB-lys)", {"utstyr"}, "all", "rgb", "app", "openrgb", 45),
    ("solaar", "Solaar (Logitech)", {"utstyr"}, "linux", "logitech", "app", "solaar", 40),
    ("ratbagd", "ratbagd (Logitech-mus)", {"utstyr"}, "linux", "logitech", "pkg",
     {"pacman": "libratbag", "dnf": "libratbag-ratbagd", "apt": "ratbagd", "zypper": "libratbag-tools",
      "cmd": "ratbagd"}, 2),
    ("udev_rgb", "Enhetstilgang for RGB og Logitech (udev, i2c)", {"utstyr"}, "linux", "rgb", "udev", None, 0),
    ("trcc", "TRCC (CPU-skjermen)", {"cpuskjerm"}, "linux", "lcd", "trcc", None, 30),
    ("rustdesk", "RustDesk (fjernhjelp)", {"fjernhjelp"}, "all", None, "app", "rustdesk", 30),
    ("tailscale", "Tailscale (chat og PC-er utenfor huset)", {"chat", "pcer"}, "all", None, "app", "tailscale", 35),
    ("discord", "Discord", {"discord"}, "all", None, "app", "discord", 110),
    ("sunshine", "Sunshine (strømming til TV og mobil)", {"stromming"}, "all", None, "app", "sunshine", 40),
    ("mangohud", "MangoHud (spill-overlay)", {"spill"}, "linux", None, "pkg",
     {"pacman": "mangohud", "dnf": "mangohud", "apt": "mangohud", "zypper": "mangohud", "cmd": "mangohud"}, 5),
    ("ffmpeg", "FFmpeg (klipp og talemeldinger)", {"spill", "chat"}, "win", None, "winget", "Gyan.FFmpeg", 90),
    ("smbclient", "smbclient (oppdateringer fra NAS-en)", {"oversikt"}, "linux", None, "pkg",
     {"pacman": "smbclient", "dnf": "samba-client", "apt": "smbclient", "zypper": "samba-client",
      "cmd": "smbclient"}, 3),
]
if TEST:
    COMPONENTS = [
        ("t_rgb", "Test-RGB", {"utstyr"}, "all", None, "fake", None, 6),
        ("t_trcc", "Test-TRCC", {"cpuskjerm"}, "all", None, "fake", None, 3),
        ("t_rd", "Test-RustDesk", {"fjernhjelp"}, "all", None, "fake", None, 4),
        ("t_dc", "Test-Discord", {"discord"}, "all", None, "fake", None, 5),
    ]
_FAKE = os.path.expanduser("~/.cache/ks-test/komp-fake.json")


# --------------------------------------------------------------------------
# Hva er installert, og hva har Kontrollsenter installert?
# --------------------------------------------------------------------------
def _state():
    try:
        with open(CFG, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"ours": []}


def _save_state(d):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    tmp = CFG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)
    os.replace(tmp, CFG)


def _mark(cid, ours):
    d = _state()
    s = set(d.get("ours", []))
    (s.add if ours else s.discard)(cid)
    d["ours"] = sorted(s)
    _save_state(d)


def asked(cid):
    """Har vi allerede spurt om å fjerne dette (var installert før Kontrollsenter)?"""
    return cid in _state().get("asked", [])


def mark_asked(cids):
    d = _state()
    d["asked"] = sorted(set(d.get("asked", [])) | set(cids))
    _save_state(d)


def unmark_asked(cids):
    d = _state()
    d["asked"] = sorted(set(d.get("asked", [])) - set(cids))
    _save_state(d)


def ours(cid):
    return cid in _state().get("ours", [])


def _pm():
    if os.path.exists("/run/ostree-booted"):
        return "ostree"
    for pm, exe in (("pacman", "pacman"), ("dnf", "dnf"), ("apt", "apt-get"), ("zypper", "zypper")):
        if shutil.which(exe):
            return pm
    return None


_HW = {"v": None}


def hardware():
    """{"rgb", "logitech", "lcd", …} – det som finnes i PC-en (hardware.py)."""
    if _HW["v"] is None:
        try:
            out = subprocess.run([sys.executable, os.path.join(APP_DIR, "hardware.py")], capture_output=True,
                                 text=True, timeout=20).stdout
            _HW["v"] = set(out.split())
        except (OSError, subprocess.SubprocessError):
            _HW["v"] = set()
        if IS_WIN:
            _HW["v"] |= {"rgb"}                         # Windows: OpenRGB er nyttig uansett
    return _HW["v"]


def _trcc_bin():
    for p in ("/usr/bin/trcc", "/usr/local/bin/trcc", os.path.expanduser("~/.local/bin/trcc"),
              os.path.join(DEST_TRCC, "bin", "trcc")):
        if os.access(p, os.X_OK):
            return p
    return None


def installed(c):
    cid, _n, _f, _p, _hw, kind, data, _mb = c
    if kind == "fake":
        try:
            return cid in json.load(open(_FAKE))
        except (OSError, ValueError):
            return False
    if kind == "app":
        import apps
        return bool(apps.installed(data, max_age=0))
    if kind == "pkg":
        return bool(shutil.which(data["cmd"]) or os.path.exists(f"/usr/sbin/{data['cmd']}"))
    if kind == "winget":
        return bool(shutil.which("ffmpeg"))
    if kind == "trcc":
        return bool(_trcc_bin())
    if kind == "udev":
        rules = ("/etc/udev/rules.d/60-openrgb.rules", "/usr/lib/udev/rules.d/60-openrgb.rules")
        return any(os.path.exists(r) for r in rules)
    return False


def _applies(c):
    plat, hw = c[3], c[4]
    if plat == "linux" and IS_WIN or plat == "win" and not IS_WIN:
        return False
    if hw and hw not in hardware():
        return False
    if c[5] == "app":
        import apps
        a = apps.APPS.get(c[6]) or {}
        if IS_WIN and not a.get("winget") or not IS_WIN and not a.get("flatpak"):
            return False                              # f.eks. Tailscale på Linux er en systemtjeneste
    return True


def removable(c):
    """Kan dette fjernes trygt hvis det var der før Kontrollsenter? (Ikke systempakker fra Linux selv.)"""
    if c[5] in ("app", "winget", "fake"):
        return True
    if c[5] == "trcc":
        b = _trcc_bin() or ""
        return b.startswith(DEST_TRCC)
    return False


def plan(enabled):
    """{"install": [...], "remove": [...], "keep": [...], "have": [...]} for funksjonene som er på."""
    enabled = set(enabled)
    out = {"install": [], "remove": [], "keep": [], "have": []}
    for c in COMPONENTS:
        if not _applies(c):
            continue
        need = bool(c[2] & enabled)
        has = installed(c)
        if need and not has:
            out["install"].append(c)
        elif need:
            out["have"].append(c)
            if asked(c[0]):
                unmark_asked([c[0]])
        elif has and ours(c[0]):
            out["remove"].append(c)
        elif has:
            out["keep"].append(c)                       # var der før Kontrollsenter – røres ikke uten å spørre
    return out


# --------------------------------------------------------------------------
# Kjøring med fremdrift
# --------------------------------------------------------------------------
def _net_bytes():
    try:
        import psutil
        return psutil.net_io_counters().bytes_recv
    except Exception:  # noqa: BLE001
        return 0


class Runner:
    """Installerer/avinstallerer i en tråd. state: pct, eta (s), speed (B/s), step, items [(navn, status)], done."""

    def __init__(self, todo, on_change=None):
        self.todo = list(todo)                  # [(handling «install»/«remove», komponent)]
        self.on_change = on_change
        self.cancelled = False
        w = [max(1.0, c[7]) if act == "install" else 1.0 for act, c in self.todo]
        self.weights = w
        self.state = {"pct": 0.0, "eta": None, "speed": 0.0, "step": "Gjør klar …", "done": False,
                      "items": [(("Installerer " if a == "install" else "Fjerner ") + c[1], "venter")
                                for a, c in self.todo], "errors": [], "reboot": False}
        self._t0 = time.monotonic()
        self._samples = []

    # ---- framdrift
    def _emit(self):
        if self.on_change:
            try:
                self.on_change(dict(self.state))
            except Exception:  # noqa: BLE001
                pass

    def _progress(self, i, frac):
        done_w = sum(self.weights[:i]) + self.weights[i] * max(0.0, min(1.0, frac))
        tot = sum(self.weights) or 1
        pct = 100.0 * done_w / tot
        self.state["pct"] = max(self.state["pct"], min(99.5, pct))
        now = time.monotonic()
        nb = _net_bytes()
        self._samples.append((now, nb, self.state["pct"]))
        self._samples = [s for s in self._samples if now - s[0] < 6]
        if len(self._samples) > 1:
            (t0, b0, p0), (t1, b1, p1) = self._samples[0], self._samples[-1]
            if t1 - t0 > 0.5:
                self.state["speed"] = max(0.0, (b1 - b0) / (t1 - t0))
                rate = (p1 - p0) / (t1 - t0)                 # prosent per sekund
                if rate > 0.01:
                    self.state["eta"] = (100 - self.state["pct"]) / rate
                elif now - self._t0 > 3 and self.state["pct"] > 1:
                    self.state["eta"] = (now - self._t0) * (100 - self.state["pct"]) / self.state["pct"]
        self._emit()

    def _run_cmd(self, i, cmd, est_mb, root=False):
        """Kjør et program; prosent fra utskriften, ellers fra hvor mye som er lastet ned."""
        flags = {"creationflags": 0x08000000} if IS_WIN else {}
        if root and not IS_WIN:
            cmd = ["pkexec"] + cmd
        start_b = _net_bytes()
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, **flags)
        out = bytearray()
        reader_done = threading.Event()

        def reader():
            while True:
                ch = p.stdout.read1(4096) if hasattr(p.stdout, "read1") else p.stdout.read(4096)
                if not ch:
                    break
                out.extend(ch)
            reader_done.set()
        threading.Thread(target=reader, daemon=True).start()
        frac = 0.0
        while not reader_done.wait(0.4):
            tail = bytes(out[-600:]).decode("utf-8", "replace")
            m = re.findall(r"(\d{1,3}(?:[.,]\d)?)\s?%", tail)
            if m:
                frac = max(frac, min(1.0, float(m[-1].replace(",", ".")) / 100))
            elif est_mb:
                frac = max(frac, min(0.95, (_net_bytes() - start_b) / (est_mb * 1e6)))
            else:
                frac = min(0.9, frac + 0.02)
            self._progress(i, frac)
        p.wait()
        return p.returncode, bytes(out).decode("utf-8", "replace")

    # ---- én komponent
    def _do(self, i, act, c):
        cid, name, _f, _p, _hw, kind, data, mb = c
        inst = act == "install"
        if kind == "fake":
            n = 0
            while n < 20 and not self.cancelled:
                time.sleep(0.08)
                n += 1
                self._progress(i, n / 20)
            try:
                have = set(json.load(open(_FAKE)))
            except (OSError, ValueError):
                have = set()
            (have.add if inst else have.discard)(cid)
            os.makedirs(os.path.dirname(_FAKE), exist_ok=True)
            json.dump(sorted(have), open(_FAKE, "w"))
            return
        if kind == "app":
            import apps
            a = apps.APPS[data]
            if IS_WIN:
                verb = "install" if inst else "uninstall"
                cmd = ["winget", verb, "-e", "--id", a["winget"], "--silent", "--accept-source-agreements",
                       "--disable-interactivity"] + (["--accept-package-agreements"] if inst else [])
            else:
                if inst:
                    subprocess.run(["flatpak", "remote-add", "--user", "--if-not-exists", "flathub",
                                    "https://dl.flathub.org/repo/flathub.flatpakrepo"], capture_output=True,
                                   timeout=60)
                    cmd = ["flatpak", "install", "--user", "-y", "--noninteractive", "flathub", a["flatpak"]]
                else:                                   # bruker- eller systeminstallasjon – flatpak finner den
                    cmd = ["flatpak", "uninstall", "-y", "--noninteractive", a["flatpak"]]
            code, out = self._run_cmd(i, cmd, mb if inst else 0)
            if code != 0 and "already" not in out.lower() and "allerede" not in out.lower() \
                    and "not installed" not in out.lower():
                raise RuntimeError(out.strip().splitlines()[-1][-200:] if out.strip() else f"feilkode {code}")
            try:
                apps._CACHE.pop(data, None)
                apps._FP["t"] = 0
            except Exception:  # noqa: BLE001
                pass
            return
        if kind == "winget":
            verb = "install" if inst else "uninstall"
            code, out = self._run_cmd(i, ["winget", verb, "-e", "--id", data, "--silent",
                                          "--accept-source-agreements", "--disable-interactivity"] +
                                      (["--accept-package-agreements"] if inst else []), mb if inst else 0)
            if code != 0 and "already" not in out.lower():
                raise RuntimeError(f"winget: feilkode {code}")
            return
        if kind == "pkg":
            pm = _pm()
            pkg = data.get(pm if pm != "ostree" else "dnf")
            if not pm or not pkg:
                raise RuntimeError("ukjent pakkehåndterer – installer selv")
            if pm == "ostree":
                cmd = (["rpm-ostree", "install", "--idempotent", "--allow-inactive", pkg] if inst else
                       ["rpm-ostree", "uninstall", pkg])
                code, out = self._run_cmd(i, cmd, mb if inst else 0)
                self.state["reboot"] = True
            else:
                cmd = {"pacman": (["pacman", "-S", "--needed", "--noconfirm", pkg] if inst else
                                  ["pacman", "-R", "--noconfirm", pkg]),
                       "dnf": ["dnf", "install" if inst else "remove", "-y", pkg],
                       "apt": (["apt-get", "install", "-y", pkg] if inst else ["apt-get", "remove", "-y", pkg]),
                       "zypper": ["zypper", "-n", "install" if inst else "remove", pkg]}[pm]
                self.state["step"] = name + " – skriv passordet ditt når Linux spør"
                self._emit()
                code, out = self._run_cmd(i, cmd, mb if inst else 0, root=True)
            if code != 0:
                raise RuntimeError(out.strip().splitlines()[-1][-200:] if out.strip() else f"feilkode {code}")
            return
        if kind == "trcc":
            if inst:
                if not os.path.exists(os.path.join(DEST_TRCC, "bin", "pip")):
                    code, out = self._run_cmd(i, [sys.executable, "-m", "venv", DEST_TRCC], 0)
                    if code:
                        raise RuntimeError("kunne ikke lage Python-miljø for TRCC")
                code, out = self._run_cmd(i, [os.path.join(DEST_TRCC, "bin", "pip"), "install", "trcc-linux"], mb)
                if code:
                    raise RuntimeError(out.strip().splitlines()[-1][-200:] if out.strip() else "pip feilet")
                exe = os.path.join(DEST_TRCC, "bin", "trcc")
                self.state["step"] = "TRCC: enhetstilgang – skriv passordet ditt når Linux spør"
                self._emit()
                self._run_cmd(i, [exe, "system", "setup", "-y"], 0, root=True)
            else:
                shutil.rmtree(DEST_TRCC, ignore_errors=True)
            return
        if kind == "udev":
            src = next((d for d in (os.path.join(APP_DIR, "udev"), os.path.join(APP_DIR, "pakke", "udev"))
                        if os.path.isdir(d)), os.path.join(APP_DIR, "udev"))
            rules = ["60-openrgb.rules", "42-logitech-unify-permissions.rules"]
            if inst:
                lines = ["set -e"] + [f"[ -f '{src}/{r}' ] && install -m 644 '{src}/{r}' /etc/udev/rules.d/{r} || true"
                                      for r in rules] + \
                    ["echo i2c-dev > /etc/modules-load.d/systemmonitor-i2c.conf", "modprobe i2c-dev || true",
                     "udevadm control --reload-rules && udevadm trigger || true"]
            else:
                lines = [f"rm -f /etc/udev/rules.d/{r}" for r in rules] + \
                    ["rm -f /etc/modules-load.d/systemmonitor-i2c.conf", "udevadm control --reload-rules || true"]
            self.state["step"] = name + " – skriv passordet ditt når Linux spør"
            self._emit()
            code, out = self._run_cmd(i, ["bash", "-c", "\n".join(lines)], 0, root=True)
            if code:
                raise RuntimeError("avbrutt eller feilet")
            return
        raise RuntimeError("ukjent type")

    def run(self):
        for i, (act, c) in enumerate(self.todo):
            if self.cancelled:
                self.state["items"][i] = (self.state["items"][i][0], "avbrutt")
                continue
            self.state["items"][i] = (self.state["items"][i][0], "kjører")
            self.state["step"] = self.state["items"][i][0] + " …"
            self._progress(i, 0)
            try:
                self._do(i, act, c)
                _mark(c[0], act == "install")             # husk hva Kontrollsenter selv har installert
                self.state["items"][i] = (self.state["items"][i][0], "ferdig")
            except Exception as e:  # noqa: BLE001
                self.state["errors"].append(f"{c[1]}: {e}")
                self.state["items"][i] = (self.state["items"][i][0], "feilet")
            self._progress(i, 1.0)
        self.state.update(pct=100.0, eta=0, done=True,
                          step="Ferdig" if not self.state["errors"] else "Ferdig – noe feilet")
        self._emit()
        return self.state


def todo_for(p):
    return [("install", c) for c in p["install"]] + [("remove", c) for c in p["remove"]]


def human_speed(bps):
    if bps >= 1e6:
        return f"{bps / 1e6:.1f} MB/s"
    if bps >= 1e3:
        return f"{bps / 1e3:.0f} kB/s"
    return "–"


def human_eta(s):
    if s is None:
        return "beregner tid …"
    s = int(s)
    if s < 60:
        return f"ca. {max(1, s)} s igjen"
    return f"ca. {s // 60} min {s % 60:02d} s igjen"
