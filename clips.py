"""Klipp – opptak i bakgrunnen (som Medal/ShadowPlay): spillet tas opp hele tiden i en ringbuffer, og F8 (eller
knappen i appen) lagrer de siste sekundene som en videofil.

Linux:   GPU Screen Recorder (Flathub) i «replay»-modus – skjermkortets egen videokoder, med lyd. SIGUSR1 lagrer.
         F8 registreres via skrivebordets portal for globale hurtigtaster (KDE spør én gang).
Windows: Medal (anbefalt, se medal.py) – Medal eier klippetasten selv, og «Lagre klipp» sender Medals tast.
         Eller Xbox Game Bar sitt «Ta opp det som skjedde»: F8 registreres med RegisterHotKey og sender Win+Alt+G.
"""
import glob
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time

from gi.repository import Gio, GLib

IS_WIN = sys.platform == "win32"
CFG = os.path.expanduser("~/.config/systemmonitor/klipp.json")
GSR_APP = "com.dec05eba.gpu_screen_recorder"
LENGTHS = [15, 30, 60, 120, 180, 300]


def load_cfg():
    try:
        with open(CFG, encoding="utf-8") as f:
            c = json.load(f)
    except (OSError, ValueError):
        c = {}
    d = {"enabled": False, "length": 60, "only_games": True, "hotkey": "F8",
         # Windows: «auto» = Medal hvis det er installert, ellers Game Bar
         "win_engine": "auto", "medal_dir": "", "medal_key": "F8",
         # opptak
         "fps": 60, "quality": "very_high", "scale": "", "mic": False, "tracks": "mixed", "webcam": False,
         # flere hurtigtaster («» = av)
         "keys": {"bookmark": "F7", "save30": "", "save5m": "", "record": "", "shot": "F9"},
         # automatikk
         "auto_cs2": True, "killzoom": True, "cs2_long": False, "cs2_match": False, "wow_log": True,
         "idle_pause": True, "controller": False, "sound": True,
         # rydding og deling
         "keep_days": 0, "max_gb": 0, "nas_days": 0, "share_nas": False, "watermark": ""}
    d.update(c)
    d["keys"] = {**{"bookmark": "F7", "save30": "", "save5m": "", "record": "", "shot": "F9"}, **(c.get("keys") or {})}
    return d


def save_cfg(c):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    with open(CFG, "w", encoding="utf-8") as f:
        json.dump(c, f, indent=1)


_WIN_DIR = None


def engine():
    """Klippeprogrammet som brukes (valgt under Klipp): Windows – medal, nvidiaapp, obs, steamrec eller gamebar;
    Linux – gsr (Kontrollsenter tar opp selv) eller et frittstående program (obs, kooha …)."""
    import apps
    u = apps.get_use("clips")
    if not IS_WIN:
        return u or "gsr"
    return u or "gamebar"


def app_key(eng=None):
    """Tasten som lagrer et klipp i klippeprogrammet (Windows)."""
    import apps
    eng = eng or engine()
    return load_cfg().get(f"{eng}_key") or apps.CLIP_KEYS.get(eng, "")


def _medal_root():
    import medal
    return medal.find_dir(load_cfg().get("medal_dir"))


def clip_dir():
    if IS_WIN and engine() == "medal":
        root = _medal_root()
        if root:
            return root
    if IS_WIN:
        global _WIN_DIR
        if _WIN_DIR is None:                       # «Opptak»-mappen kan være flyttet (f.eks. til OneDrive)
            try:
                import wincapture
                _WIN_DIR = wincapture.captures_dir()
            except Exception:  # noqa: BLE001
                _WIN_DIR = os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), "Videos", "Captures")
        return _WIN_DIR
    base = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_VIDEOS) or os.path.expanduser("~/Videos")
    return os.path.join(base, "Kontrollsenter")


def clips(limit=60):
    if IS_WIN and engine() == "medal":
        import medal
        return medal.clips(_medal_root(), limit)
    out = []
    for f in glob.glob(os.path.join(clip_dir(), "*.mp4")):
        try:
            st = os.stat(f)
            out.append({"name": os.path.basename(f), "size": st.st_size, "t": st.st_mtime})
        except OSError:
            continue
    return sorted(out, key=lambda x: -x["t"])[:limit]


def clip_path(name):
    """Full sti for et klipp – bare filer i klippmappen (ingen ../)."""
    if not name or "/" in name or "\\" in name or name.startswith(".") or not name.lower().endswith(".mp4"):
        return None
    if IS_WIN and engine() == "medal":                  # Medal lagrer i undermapper per spill
        import medal
        return medal.path_of(_medal_root(), name)
    p = os.path.join(clip_dir(), name)
    return p if os.path.isfile(p) else None


_INST = {"t": 0.0, "v": None}


def installed():
    """Er GPU Screen Recorder installert? (husket i 10 min – flatpak info tar tid)"""
    if IS_WIN:
        return True
    if _INST["v"] is not None and time.monotonic() - _INST["t"] < 600:
        return _INST["v"]
    _INST.update(v=_installed(), t=time.monotonic())
    return _INST["v"]


def _installed():
    try:
        r = subprocess.run(["flatpak", "info", GSR_APP], capture_output=True, timeout=10)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def install():
    """Installer GPU Screen Recorder fra Flathub (bare når du trykker på knappen)."""
    import apps
    _INST["v"] = None
    apps.install("gsr")
    _INST["v"] = None


# --------------------------------------------------------------------------
# Opptaket i bakgrunnen
# --------------------------------------------------------------------------
class Recorder:
    def __init__(self, notify=None):
        self.notify = notify or (lambda *a, **k: None)
        self.proc = None
        self.started = 0
        self.game = None
        self.last_save = 0
        self.error = None
        self.hotkey = None

    # ---- status ----
    def running(self):
        if IS_WIN:
            return load_cfg()["enabled"]
        if self.proc is not None and self.proc.poll() is None:
            return True
        return bool(self._gsr_pids())                   # f.eks. startet av en tidligere utgave – ikke start et til

    def state(self):
        c = load_cfg()
        eng = engine()
        med = {}
        if eng == "medal":
            import medal
            med = medal.status(c)
        return {**c, "engine": eng, "medal": med,
                "installed": installed() if not IS_WIN else (eng != "medal" or med.get("installed", False)),
                "running": self.running(),
                "dir": clip_dir(), "os": "windows" if IS_WIN else "linux", "error": self.error,
                "hotkey_ok": bool(self.hotkey and self.hotkey.ok), "lengths": LENGTHS,
                "hotkey_error": self.hotkey.error if self.hotkey else None,
                "hotkey_how": self.hotkey.how if self.hotkey else None,
                "hotkey_tested": self.hotkey.tested if self.hotkey else None,
                "hotkey_testing": bool(self.hotkey and time.time() < self.hotkey.test_until)}

    # ---- styring (kalles hvert sekund fra bakgrunnen) ----
    def tick(self, game):
        self.game = game or self.game
        c = load_cfg()
        try:
            import clipx
            clipx.health_tick(self, game)
            if c["enabled"] and c.get("controller") and not getattr(self, "pad", None):
                self.pad = clipx.Controller(lambda: threading.Thread(target=self.save, daemon=True).start())
            elif not c.get("controller") and getattr(self, "pad", None):
                self.pad.stop, self.pad = True, None
            if c["enabled"] and c.get("wow_log"):
                self.wowlog = getattr(self, "wowlog", None) or clipx.WowLog(self)
                if time.time() - getattr(self, "_wl_t", 0) > 2:
                    self._wl_t = time.time()
                    self.wowlog.tick(game)
        except Exception:  # noqa: BLE001
            pass
        if IS_WIN:
            return
        if engine() != "gsr":                                 # et annet klippeprogram er valgt – ikke ta opp dobbelt
            if self.running():
                self.stop()
            return
        # AFK: stopp opptaket etter 5 min uten tastetrykk/mus, start igjen når du er tilbake
        idle = False
        if c.get("idle_pause") and time.time() - getattr(self, "_idle_t", 0) > 10:
            self._idle_t = time.time()
            try:
                import clipx
                self._idle = clipx.idle_seconds() > 300
            except Exception:  # noqa: BLE001
                self._idle = False
        idle = getattr(self, "_idle", False) and c.get("idle_pause")
        # lengre buffer i CS2 Competitive/Premier
        want_len = c["length"]
        try:
            import gamestats
            cs = gamestats.LIVE.state()
            if c.get("cs2_long") and cs and str(cs.get("mode", "")).lower() in ("competitive", "premier", "scrimcomp2v2"):
                want_len = max(want_len, 180)
        except Exception:  # noqa: BLE001
            pass
        if self.running() and getattr(self, "length_now", want_len) != want_len and self.proc:
            self.stop()
        self.want_len = want_len
        if game:
            self._last_game = time.time()
        recent = time.time() - getattr(self, "_last_game", 0) < 60      # rekk å lagre slutten av spillet
        want = c["enabled"] and (bool(game) or recent or not c["only_games"]) and not idle
        if want and not self.running():
            self.start(c)
        elif not want and self.running():
            self.stop()
        elif want and len(self._gsr_pids()) > 1:
            self.dedupe()

    def start(self, c=None):
        c = c or load_cfg()
        if IS_WIN:
            return
        if not installed():
            self.error = "GPU Screen Recorder er ikke installert"
            return
        os.makedirs(clip_dir(), exist_ok=True)
        length = max(5, min(int(getattr(self, "want_len", 0) or c["length"]), 600))
        src = "portal"
        if c.get("webcam") and glob.glob("/dev/video0"):
            src = "portal|v4l2:/dev/video0"                       # webkamera i hjørnet
        if c.get("tracks") == "separate":                          # spill, Discord og mikrofon på egne spor
            audio = ["-a", "app-inverse:discord", "-a", "app:discord"] + (["-a", "default_input"] if c.get("mic") else [])
        else:
            audio = ["-a", "default_output|default_input" if c.get("mic") else "default_output"]
        os.makedirs(os.path.join(clip_dir(), "Opptak"), exist_ok=True)
        cmd = ["flatpak", "run", "--command=gpu-screen-recorder", GSR_APP,
               "-w", src, "-restore-portal-session", "yes", "-f", str(int(c.get("fps") or 60)), "-r", str(length),
               "-c", "mp4", "-k", "h264", "-ac", "aac", *audio, "-q", str(c.get("quality") or "very_high"),
               "-o", clip_dir(), "-ro", os.path.join(clip_dir(), "Opptak"), "-v", "no"]
        if c.get("scale"):
            cmd[cmd.index("-c"):cmd.index("-c")] = ["-s", str(c["scale"])]
        self.length_now = length
        self.recording = False
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, start_new_session=True)
            self.started = time.time()
            self.error = None
            threading.Thread(target=self._watch, args=(self.proc,), daemon=True).start()
        except OSError as e:
            self.error = str(e)

    def _watch(self, p):
        err = p.stderr.read().decode(errors="replace") if p.stderr else ""
        code = p.wait()
        if code not in (0, -signal.SIGTERM, -signal.SIGINT) and p is self.proc:
            self.error = (err.strip().splitlines() or [f"stoppet ({code})"])[-1][:200]

    def stop(self):
        """Stopp opptaket i bakgrunnen – alle opptak som skriver til klippmappen (de er Kontrollsenters)."""
        for pid in self._gsr_pids():
            try:
                os.kill(pid, signal.SIGINT)
            except OSError:
                pass
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(5)
            except (OSError, subprocess.SubprocessError):
                pass
        self.proc = None

    def dedupe(self):
        """Flere opptak samtidig (f.eks. etter en eldre utgave): behold det nyeste."""
        pids = sorted(self._gsr_pids())
        for pid in pids[:-1]:
            try:
                os.kill(pid, signal.SIGINT)
            except OSError:
                pass

    @staticmethod
    def _gsr_pids():
        """Selve opptaksprogrammet (ikke sandkassen rundt, som ville blitt avsluttet av SIGUSR1)."""
        import procs
        out = []
        target = b"-o\x00" + clip_dir().encode() + b"\x00"
        for pid in procs.pids_named("gpu-screen-reco", max_age=1.0):
            cmd = procs.cmdline(pid)
            if b"-r\x00" in cmd and target in cmd:
                out.append(pid)
        return out

    # ---- lagre de siste sekundene ----
    SECS = {10: 1, 30: 2, 60: 3, 300: 4, 600: 5, 1800: 6}       # SIGRTMIN+n lagrer de siste … sekundene

    def save(self, seconds=None, label=None, meta=None, keep=None, kind="clip"):
        """Lagre klipp nå. seconds: bare de siste … sekundene. keep: (fra, til) sekunder før lagring som skal
        beholdes (CS2: rundt killene). Returnerer (ok, melding)."""
        if time.time() - self.last_save < 2:
            return False, "Vent litt mellom hvert klipp"
        self.last_save = time.time()
        eng = engine()
        if IS_WIN:
            if eng == "gamebar":
                return self._save_windows()
            if eng == "medal":
                return self._save_medal()
            return self._save_key(eng)
        if eng != "gsr":
            import apps
            n = apps.APPS[eng]["name"]
            return False, f"Du bruker {n} til klipp – lagre klippet med tasten i {n} (bytt under Spill → Klipp)"
        if not self.running():
            c = load_cfg()
            if c["enabled"] and c["only_games"]:
                return False, "Ingen spill kjører – opptaket går bare mens et spill kjører"
            return False, "Opptaket i bakgrunnen er ikke på"
        before = {c["name"] for c in clips(400)}
        pids = self._gsr_pids()
        if not pids:
            return False, "Fant ikke opptaket"
        sig = signal.SIGUSR1
        if seconds and seconds in self.SECS:
            sig = signal.SIGRTMIN + self.SECS[seconds]
        for pid in pids:
            try:
                os.kill(pid, sig)
            except OSError:
                pass
        info = {"game": self.game, "kind": kind, "t": time.time(), **(meta or {})}
        try:
            import gamestats
            cs = gamestats.LIVE.state()
            if cs:
                info["cs2"] = {k: cs.get(k) for k in ("map", "mode", "round", "ct", "t", "kills", "deaths", "assists",
                                                     "hs_pct", "mvps", "team")}
        except Exception:  # noqa: BLE001
            pass
        threading.Thread(target=self._rename_new, args=(before, label or self.game, info, keep), daemon=True).start()
        return True, "Klippet lagres …"

    def toggle_record(self):
        """Start/stopp vanlig opptak (hele økta) ved siden av opptaket i bakgrunnen."""
        if IS_WIN or not self.running():
            return False, "Opptaket i bakgrunnen må være på"
        for pid in self._gsr_pids():
            try:
                os.kill(pid, signal.SIGRTMIN)
            except OSError:
                pass
        self.recording = not getattr(self, "recording", False)
        try:
            import remote_extra
            remote_extra.event("clip", "Opptak startet" if self.recording else "Opptak stoppet og lagret", "", "game")
        except Exception:  # noqa: BLE001
            pass
        return True, "Opptak startet" if self.recording else "Opptaket er lagret"

    def _rename_new(self, before, game, info=None, keep=None):
        for _ in range(60):                                   # vent til filen er ferdig skrevet
            time.sleep(0.5)
            new = [c for c in clips(400) if c["name"] not in before]
            if new:
                time.sleep(1.5)
                src = os.path.join(clip_dir(), new[0]["name"])
                nice = re.sub(r'[\\/:*?"<>|]', "", game or "Klipp").strip() or "Klipp"
                dst = os.path.join(clip_dir(), f"{nice} {time.strftime('%Y-%m-%d %H.%M.%S')}.mp4")
                try:
                    os.replace(src, dst)
                except OSError:
                    dst = src
                try:
                    import clipx
                    if keep:
                        clipx.keep_tail(dst, *keep)
                    clipx.write_meta(dst, info or {})
                    clipx.thumb(dst)
                    clipx.after_save(dst)
                except Exception:  # noqa: BLE001
                    pass
                self._saved(os.path.basename(dst))
                return

    def _saved(self, name):
        try:
            import remote_extra
            remote_extra.event("clip", "Klipp lagret", name, "game")
        except Exception:  # noqa: BLE001
            pass
        try:                                                  # bekreftelse: lyd + varsel (synlig også i spill)
            import clipx
            clipx.confirm(name)
        except Exception:  # noqa: BLE001
            pass

    def _save_key(self, eng):
        """NVIDIA App, OBS, Steam …: trykk tasten programmet lagrer klipp med."""
        import apps
        import medal
        n = apps.APPS[eng]["name"]
        key = app_key(eng)
        if not key:
            return False, f"Velg tasten {n} lagrer klipp med (Spill → Klipp → «Tast i {n}»)"
        medal.press(key)
        self._saved(n)
        return True, f"Klippet lagres av {n}"

    def _save_medal(self):
        import medal
        c = load_cfg()
        if not medal.installed():
            return False, "Medal er ikke installert – installer det under Klipp"
        if not medal.running():
            medal.start()
            return False, "Medal startet nå – prøv igjen om noen sekunder"
        since = time.time() - 1
        medal.press(c.get("medal_key") or "F8")
        root = _medal_root()

        def done(path):
            try:
                import clipx
                clipx.thumb(path)
                clipx.after_save(path)
            except Exception:  # noqa: BLE001
                pass
            self._saved(os.path.basename(path))
        if root:
            medal.watch_new(root, since, done)
        return True, "Klippet lagres av Medal"

    def _save_windows(self):
        import ctypes
        u = ctypes.windll.user32
        keys = (0x5B, 0x12, 0x47)                            # Win + Alt + G = «Ta opp det som skjedde»
        for k in keys:
            u.keybd_event(k, 0, 0, 0)
        for k in reversed(keys):
            u.keybd_event(k, 0, 2, 0)
        self._saved("Game Bar")
        return True, "Klippet lagres av Xbox Game Bar"


# --------------------------------------------------------------------------
# Windows: slå på Game Bar sitt opptak i bakgrunnen
# --------------------------------------------------------------------------
def windows_enable(on):
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\GameDVR") as k:
        winreg.SetValueEx(k, "AppCaptureEnabled", 0, winreg.REG_DWORD, 1 if on else 0)
        winreg.SetValueEx(k, "HistoricalCaptureEnabled", 0, winreg.REG_DWORD, 1 if on else 0)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"System\GameConfigStore") as k:
        winreg.SetValueEx(k, "GameDVR_Enabled", 0, winreg.REG_DWORD, 1 if on else 0)


# --------------------------------------------------------------------------
# F8 – global hurtigtast
# --------------------------------------------------------------------------
# Tastekoder: "Ctrl+Shift+F8" → Qt-kode (KDE) og (modifikatorer, VK) for Windows
QT_MOD = {"Ctrl": 0x04000000, "Shift": 0x02000000, "Alt": 0x08000000, "Meta": 0x10000000}
WIN_MOD = {"Ctrl": 0x2, "Shift": 0x4, "Alt": 0x1, "Meta": 0x8}
SPECIAL = {  # navn: (Qt, Windows VK)
    "Insert": (0x01000006, 0x2D), "Delete": (0x01000007, 0x2E), "Pause": (0x01000008, 0x13),
    "Print": (0x01000009, 0x2C), "Home": (0x01000010, 0x24), "End": (0x01000011, 0x23),
    "PageUp": (0x01000016, 0x21), "PageDown": (0x01000017, 0x22), "ScrollLock": (0x01000026, 0x91),
    "Space": (0x20, 0x20)}


def parse_key(spec):
    """«Ctrl+Shift+F8» → (modifikatorer, tastenavn) eller kaster ValueError."""
    parts = [p.strip() for p in str(spec or "").split("+") if p.strip()]
    if not parts:
        raise ValueError("ingen tast")
    mods, key = parts[:-1], parts[-1]
    for m in mods:
        if m not in QT_MOD:
            raise ValueError(f"ukjent tast {m}")
    if not (re.fullmatch(r"F([1-9]|1[0-9]|2[0-4])", key) or re.fullmatch(r"[A-Z0-9]", key) or key in SPECIAL):
        raise ValueError(f"ukjent tast {key}")
    if re.fullmatch(r"[A-Z0-9]", key) and not mods:
        raise ValueError("en bokstav eller et tall alene ville blitt fanget i spill og chat – bruk f.eks. Ctrl+Shift")
    return mods, key


def qt_code(spec):
    mods, key = parse_key(spec)
    if key.startswith("F") and len(key) > 1:
        code = 0x01000030 + int(key[1:]) - 1
    elif key in SPECIAL:
        code = SPECIAL[key][0]
    else:
        code = ord(key)
    for m in mods:
        code |= QT_MOD[m]
    return code


def win_code(spec):
    mods, key = parse_key(spec)
    if key.startswith("F") and len(key) > 1:
        vk = 0x70 + int(key[1:]) - 1
    elif key in SPECIAL:
        vk = SPECIAL[key][1]
    else:
        vk = ord(key)
    m = 0x4000                                                   # MOD_NOREPEAT
    for x in mods:
        m |= WIN_MOD[x]
    return m, vk


class Hotkey:
    """Global hurtigtast (også mens et spill har fokus). KDE: KGlobalAccel (ingen spørsmål, nøyaktig tast).
    Andre skrivebord: portalen for globale hurtigtaster. Windows: RegisterHotKey."""
    ACTION = ["kontrollsenter", "lagre-klipp", "Kontrollsenter", "Lagre klipp"]

    def __init__(self, cb, spec="F8", action=None, wid=0x4B53):
        if action:
            self.ACTION = ["kontrollsenter", action[0], "Kontrollsenter", action[1]]
        self.wid = wid
        self.cb = cb
        self.spec = spec
        self.ok = False
        self.how = None
        self.error = None
        self.test_until = 0
        self.tested = None
        if IS_WIN:
            threading.Thread(target=self._win_loop, daemon=True).start()
            return
        try:
            self._kde()
        except Exception as e:  # noqa: BLE001
            self.error = str(e)
            try:
                self._portal()
            except Exception as e2:  # noqa: BLE001
                self.error = f"{self.error} / {e2}"

    def pressed(self):
        if time.time() < self.test_until:                       # «Test tasten»: ikke lagre, bare bekreft
            self.test_until = 0
            self.tested = time.time()
            return
        self.cb()

    def set_key(self, spec):
        parse_key(spec)
        self.spec = spec
        if IS_WIN and engine() != "gamebar":                   # samme tast som i klippeprogrammet
            c = load_cfg()
            c[f"{engine()}_key"] = spec
            save_cfg(c)
        if IS_WIN:
            self._win_rebind = True
            if getattr(self, "_win_tid", None):
                import ctypes
                ctypes.windll.user32.PostThreadMessageW(self._win_tid, 0x0400, 0, 0)   # WM_USER: bytt tast
            return
        if self.how == "kde":
            self._kde_bind()
        else:
            self.error = "på dette skrivebordet velges tasten i skrivebordets innstillinger"

    # ---------------- KDE ----------------
    def _kde(self):
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.bus.call_sync("org.kde.kglobalaccel", "/kglobalaccel", "org.kde.KGlobalAccel", "doRegister",
                           GLib.Variant("(as)", (self.ACTION,)), None, 0, 3000, None)
        self._kde_bind()
        self.bus.signal_subscribe("org.kde.kglobalaccel", "org.kde.kglobalaccel.Component", "globalShortcutPressed",
                                  "/component/kontrollsenter", None, Gio.DBusSignalFlags.NONE, self._kde_signal)
        self.how = "kde"

    def _kde_bind(self):
        code = qt_code(self.spec)
        res = self.bus.call_sync("org.kde.kglobalaccel", "/kglobalaccel", "org.kde.KGlobalAccel", "setShortcutKeys",
                                 GLib.Variant("(asa(ai)u)", (self.ACTION, [([code],)], 0x2 | 0x4)),
                                 GLib.VariantType("(a(ai))"), 0, 3000, None)
        got = res.unpack()[0]
        self.ok = bool(got and got[0][0] and got[0][0][0] == code)
        self.error = None if self.ok else f"{self.spec} er allerede i bruk av en annen snarvei – velg en annen tast"

    def _kde_signal(self, _c, _s, _p, _i, _sig, params):
        comp, action = params.unpack()[:2]
        if comp == "kontrollsenter" and action == self.ACTION[1]:
            GLib.idle_add(lambda: (self.pressed(), False)[1])

    # ---------------- portal (GNOME m.fl.) ----------------
    def _portal(self):
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        try:
            bus.call_sync("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
                          "org.freedesktop.host.portal.Registry", "Register",
                          GLib.Variant("(sa{sv})", ("no.waagan.Systemmonitor", {})), None, 0, 3000, None)
        except GLib.Error:
            pass
        self.bus = bus
        sender = bus.get_unique_name()[1:].replace(".", "_")
        tok = f"ks{os.getpid()}{self.ACTION[1].replace('-', '')}"
        req = f"/org/freedesktop/portal/desktop/request/{sender}/{tok}"

        def created(_c, _s, _p, _i, _sig, params):
            code, res = params.unpack()
            if code == 0:
                self.session = res.get("session_handle")
                self._portal_bind()
        bus.signal_subscribe("org.freedesktop.portal.Desktop", "org.freedesktop.portal.Request", "Response",
                             req, None, Gio.DBusSignalFlags.NO_MATCH_RULE, created)
        bus.signal_subscribe("org.freedesktop.portal.Desktop", "org.freedesktop.portal.GlobalShortcuts", "Activated",
                             "/org/freedesktop/portal/desktop", None, Gio.DBusSignalFlags.NONE, self._portal_signal)
        bus.call_sync("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
                      "org.freedesktop.portal.GlobalShortcuts", "CreateSession",
                      GLib.Variant("(a{sv})", ({"handle_token": GLib.Variant("s", tok),
                                                 "session_handle_token": GLib.Variant("s", tok + "s")},)),
                      None, 0, 5000, None)
        self.how = "portal"

    def _portal_bind(self):
        tok = f"ksb{os.getpid()}"
        sc = [(self.ACTION[1], {"description": GLib.Variant("s", self.ACTION[3] + " (Kontrollsenter)"),
                               "preferred_trigger": GLib.Variant("s", self.spec.upper().replace("META", "LOGO"))})]
        self.bus.call("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
                      "org.freedesktop.portal.GlobalShortcuts", "BindShortcuts",
                      GLib.Variant("(oa(sa{sv})sa{sv})", (self.session, sc, "", {"handle_token": GLib.Variant("s", tok)})),
                      None, 0, -1, None, None, None)
        self.ok = True

    def _portal_signal(self, _c, _s, _p, _i, _sig, params):
        if params.unpack()[1] == self.ACTION[1]:
            GLib.idle_add(lambda: (self.pressed(), False)[1])

    # ---------------- Windows ----------------
    def _win_loop(self):
        import ctypes
        from ctypes import wintypes
        u, k = ctypes.windll.user32, ctypes.windll.kernel32
        self._win_tid = k.GetCurrentThreadId()

        def bind():
            u.UnregisterHotKey(None, self.wid)
            try:
                eng = engine()
                if eng != "gamebar" and self.spec == app_key(eng):
                    self.ok, self.how, self.error = True, eng, None      # klippeprogrammet fanger tasten selv
                    return
            except Exception:  # noqa: BLE001
                pass
            m, vk = win_code(self.spec)
            self.ok = bool(u.RegisterHotKey(None, self.wid, m, vk))
            self.how = "windows"
            self.error = None if self.ok else f"{self.spec} er allerede i bruk av et annet program – velg en annen tast"
        bind()
        msg = wintypes.MSG()
        while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0312:                                    # WM_HOTKEY
                GLib.idle_add(lambda: (self.pressed(), False)[1])
            elif msg.message == 0x0400:                                  # ny tast valgt
                bind()

INSTANCE = None


def setup(notify):
    """Kalles fra bakgrunnen ved oppstart."""
    global INSTANCE
    INSTANCE = Recorder(notify)
    if load_cfg()["enabled"]:
        enable_hotkey()
    return INSTANCE


def enable_hotkey():
    r = INSTANCE
    if r and not r.hotkey:
        r.hotkey = Hotkey(lambda: _hotkey_pressed(), load_cfg().get("hotkey") or "F8")
        enable_extra_keys()


EXTRA = {  # handling: (KDE-id, navn, Windows-id, funksjon)
    "bookmark": ("bokmerke", "Bokmerke (lagre 10 s)", 0x4B54, lambda r: r.save(10, kind="bookmark",
                                                                                label=f"Bokmerke {r.game or ''}".strip())),
    "save30": ("lagre-30s", "Lagre siste 30 s", 0x4B55, lambda r: r.save(30)),
    "save5m": ("lagre-5min", "Lagre siste 5 min", 0x4B56, lambda r: r.save(300)),
    "record": ("opptak", "Start/stopp opptak", 0x4B57, lambda r: r.toggle_record()),
    "shot": ("skjermbilde", "Skjermbilde", 0x4B58, lambda r: __import__("clipx").screenshot(r.game)),
}


def enable_extra_keys():
    r = INSTANCE
    if not r:
        return
    r.extra = getattr(r, "extra", {})
    keys = load_cfg()["keys"]
    for k, (aid, name, wid, fn) in EXTRA.items():
        spec = keys.get(k) or ""
        h = r.extra.get(k)
        if not spec:
            continue
        try:
            parse_key(spec)
        except ValueError:
            continue
        if h:
            h.set_key(spec)
        else:
            r.extra[k] = Hotkey(lambda f=fn: threading.Thread(target=f, args=(INSTANCE,), daemon=True).start(),
                                spec, (aid, name), wid)


def set_extra_key(which, spec):
    if which not in EXTRA:
        raise ValueError("ukjent hurtigtast")
    if spec:
        parse_key(spec)
    c = load_cfg()
    c["keys"][which] = spec or ""
    save_cfg(c)
    enable_extra_keys()


def set_hotkey(spec):
    """Velg tast/kombinasjon, f.eks. «F8» eller «Ctrl+Shift+S». Kaster ValueError ved ugyldig tast."""
    parse_key(spec)
    c = load_cfg()
    c["hotkey"] = spec
    save_cfg(c)
    r = INSTANCE
    if r and r.hotkey:
        r.hotkey.set_key(spec)
    elif r:
        enable_hotkey()


def test_hotkey(seconds=15):
    """Neste trykk på hurtigtasten de neste sekundene lagrer ikke klipp – det bekreftes bare."""
    r = INSTANCE
    if not r or not r.hotkey:
        enable_hotkey()
    r = INSTANCE
    r.hotkey.tested = None
    r.hotkey.test_until = time.time() + seconds


def _hotkey_pressed():
    r = INSTANCE
    if r:
        threading.Thread(target=r.save, daemon=True).start()


OPTS = {"fps": (30, 60, 120), "quality": ("medium", "high", "very_high", "ultra"),
        "scale": ("", "1920x1080", "2560x1440", "1280x720"), "tracks": ("mixed", "separate")}
BOOLS = ("mic", "webcam", "auto_cs2", "killzoom", "cs2_long", "cs2_match", "wow_log", "idle_pause", "controller",
         "sound", "share_nas")
NUMS = {"keep_days": (0, 3650), "max_gb": (0, 10000), "nas_days": (0, 3650)}


def set_options(**kw):
    """Andre valg (kvalitet, lydspor, automatikk, rydding …). Restart opptaket når noe påvirker det."""
    c = load_cfg()
    restart = False
    for k, v in kw.items():
        if k in OPTS:
            if v not in OPTS[k]:
                raise ValueError(f"ugyldig verdi for {k}")
            restart |= c.get(k) != v
            c[k] = v
        elif k in BOOLS:
            restart |= k in ("mic", "webcam") and c.get(k) != bool(v)
            c[k] = bool(v)
        elif k in NUMS:
            v = int(v)
            if not NUMS[k][0] <= v <= NUMS[k][1]:
                raise ValueError(f"ugyldig verdi for {k}")
            c[k] = v
        elif k == "watermark":
            c[k] = str(v)[:40]
        elif k == "win_engine":
            if v not in ("auto", "medal", "gamebar"):
                raise ValueError("ugyldig opptaksprogram")
            c[k] = v
        elif k == "medal_dir":
            if v and not os.path.isdir(str(v)):
                raise ValueError("mappen finnes ikke")
            c[k] = str(v or "")
        elif k.endswith("_key") and k[:-4] in __import__("apps").CLIP_KEYS:
            if v:
                parse_key(v)
            c[k] = str(v or "")
        else:
            raise ValueError(f"ukjent valg {k}")
    save_cfg(c)
    r = INSTANCE
    if restart and r and r.running() and not IS_WIN:
        r.stop()
    return c


def set_cfg(enabled=None, length=None, only_games=None):
    c = load_cfg()
    if enabled is not None:
        c["enabled"] = bool(enabled)
    if length is not None:
        if int(length) not in LENGTHS:
            raise ValueError("ugyldig lengde")
        c["length"] = int(length)
    if only_games is not None:
        c["only_games"] = bool(only_games)
    save_cfg(c)
    if IS_WIN and enabled is not None:
        if engine() == "medal":
            if c["enabled"]:
                import medal
                medal.start()
        else:
            windows_enable(c["enabled"])
    r = INSTANCE
    if r:
        if c["enabled"]:
            GLib.idle_add(lambda: (enable_hotkey(), False)[1])
        if r.running() and (length is not None or not c["enabled"]):
            r.stop()                       # starter igjen med ny lengde ved neste tick
    return c


def delete(name):
    p = clip_path(name)
    if not p:
        raise ValueError("fant ikke klippet")
    os.remove(p)
