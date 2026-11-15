"""Klipp – opptak i bakgrunnen (som Medal/ShadowPlay): spillet tas opp hele tiden i en ringbuffer, og F8 (eller
knappen i appen) lagrer de siste sekundene som en videofil.

Linux:   GPU Screen Recorder (Flathub) i «replay»-modus – skjermkortets egen videokoder, med lyd. SIGUSR1 lagrer.
         F8 registreres via skrivebordets portal for globale hurtigtaster (KDE spør én gang).
Windows: Xbox Game Bar sitt «Ta opp det som skjedde» (innebygd i Windows). F8 registreres med RegisterHotKey og
         sender Win+Alt+G. Lengden velges i Windows-innstillingene (Spill → Opptak).
"""
import glob
import json
import os
import re
import shutil
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
    return {"enabled": False, "length": 60, "only_games": True, "hotkey": "F8", **c}


def save_cfg(c):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    with open(CFG, "w", encoding="utf-8") as f:
        json.dump(c, f, indent=1)


def clip_dir():
    if IS_WIN:
        return os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), "Videos", "Captures")
    base = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_VIDEOS) or os.path.expanduser("~/Videos")
    return os.path.join(base, "Kontrollsenter")


def clips(limit=60):
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
    p = os.path.join(clip_dir(), name)
    return p if os.path.isfile(p) else None


def installed():
    if IS_WIN:
        return True
    try:
        r = subprocess.run(["flatpak", "info", GSR_APP], capture_output=True, timeout=10)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def install():
    """Installer GPU Screen Recorder fra Flathub (bare når du trykker på knappen)."""
    r = subprocess.run(["flatpak", "install", "--user", "-y", "--noninteractive", "flathub", GSR_APP],
                       capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[-300:] or "installasjonen feilet")


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
        return self.proc is not None and self.proc.poll() is None

    def state(self):
        c = load_cfg()
        return {**c, "installed": installed() if not IS_WIN else True, "running": self.running(),
                "dir": clip_dir(), "os": "windows" if IS_WIN else "linux", "error": self.error,
                "hotkey_ok": bool(self.hotkey and self.hotkey.ok), "lengths": LENGTHS}

    # ---- styring (kalles hvert sekund fra bakgrunnen) ----
    def tick(self, game):
        self.game = game or self.game
        c = load_cfg()
        if IS_WIN:
            return
        want = c["enabled"] and (bool(game) or not c["only_games"])
        if want and not self.running():
            self.start(c)
        elif not want and self.running():
            # vent litt etter at spillet er avsluttet, så du rekker å lagre slutten
            if not game and time.time() - getattr(self, "_game_gone", time.time()) > 60:
                self.stop()
            elif not c["enabled"]:
                self.stop()
        if game:
            self._game_gone = time.time()

    def start(self, c=None):
        c = c or load_cfg()
        if IS_WIN:
            return
        if not installed():
            self.error = "GPU Screen Recorder er ikke installert"
            return
        os.makedirs(clip_dir(), exist_ok=True)
        length = max(5, min(int(c["length"]), 600))
        cmd = ["flatpak", "run", f"--command=gpu-screen-recorder", GSR_APP,
               "-w", "portal", "-restore-portal-session", "yes", "-f", "60", "-r", str(length),
               "-c", "mp4", "-k", "h264", "-ac", "aac", "-a", "default_output", "-q", "very_high",
               "-o", clip_dir(), "-v", "no"]
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
        if self.proc and self.proc.poll() is None:
            for pid in self._gsr_pids():
                try:
                    os.kill(pid, signal.SIGINT)
                except OSError:
                    pass
            try:
                self.proc.terminate()
                self.proc.wait(5)
            except (OSError, subprocess.SubprocessError):
                pass
        self.proc = None

    @staticmethod
    def _gsr_pids():
        try:
            r = subprocess.run(["pgrep", "-f", "gpu-screen-recorder -w"], capture_output=True, text=True, timeout=5)
            return [int(x) for x in r.stdout.split() if x.isdigit()]
        except (OSError, subprocess.SubprocessError):
            return []

    # ---- lagre de siste sekundene ----
    def save(self):
        """Lagre klipp nå. Returnerer (ok, melding)."""
        if time.time() - self.last_save < 2:
            return False, "Vent litt mellom hvert klipp"
        self.last_save = time.time()
        if IS_WIN:
            return self._save_windows()
        if not self.running():
            return False, "Opptaket i bakgrunnen er ikke på"
        before = {c["name"] for c in clips(200)}
        pids = self._gsr_pids()
        if not pids:
            return False, "Fant ikke opptaket"
        for pid in pids:
            try:
                os.kill(pid, signal.SIGUSR1)
            except OSError:
                pass
        threading.Thread(target=self._rename_new, args=(before, self.game), daemon=True).start()
        return True, "Klippet lagres …"

    def _rename_new(self, before, game):
        for _ in range(40):                                   # vent til filen er ferdig skrevet
            time.sleep(0.5)
            new = [c for c in clips(200) if c["name"] not in before]
            if new:
                time.sleep(1.5)
                src = os.path.join(clip_dir(), new[0]["name"])
                nice = re.sub(r'[\\/:*?"<>|]', "", game or "Klipp").strip() or "Klipp"
                dst = os.path.join(clip_dir(), f"{nice} {time.strftime('%Y-%m-%d %H.%M.%S')}.mp4")
                try:
                    os.replace(src, dst)
                except OSError:
                    dst = src
                self._saved(os.path.basename(dst))
                return

    def _saved(self, name):
        try:
            import remote_extra
            remote_extra.event("clip", "Klipp lagret", name, "game")
        except Exception:  # noqa: BLE001
            pass

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
class Hotkey:
    """Kaller cb() når F8 trykkes, også mens et spill har fokus."""

    def __init__(self, cb):
        self.cb = cb
        self.ok = False
        if IS_WIN:
            threading.Thread(target=self._win_loop, daemon=True).start()
        else:
            try:
                self._portal()
            except Exception:  # noqa: BLE001
                self.ok = False

    # Windows: RegisterHotKey + egen meldingsløkke
    def _win_loop(self):
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        if not u.RegisterHotKey(None, 0x4B53, 0x4000, 0x77):       # MOD_NOREPEAT, VK_F8
            return
        self.ok = True
        msg = wintypes.MSG()
        while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0312:                                 # WM_HOTKEY
                GLib.idle_add(lambda: (self.cb(), False)[1])

    # Linux: org.freedesktop.portal.GlobalShortcuts (KDE spør én gang om å godta F8)
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
        tok = f"ks{os.getpid()}"
        req = f"/org/freedesktop/portal/desktop/request/{sender}/{tok}"

        def created(_c, _s, _p, _i, _sig, params):
            code, res = params.unpack()
            if code == 0:
                self.session = res.get("session_handle")
                self._bind()
        bus.signal_subscribe("org.freedesktop.portal.Desktop", "org.freedesktop.portal.Request", "Response",
                             req, None, Gio.DBusSignalFlags.NO_MATCH_RULE, created)
        bus.signal_subscribe("org.freedesktop.portal.Desktop", "org.freedesktop.portal.GlobalShortcuts", "Activated",
                             "/org/freedesktop/portal/desktop", None, Gio.DBusSignalFlags.NONE, self._activated)
        bus.call_sync("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
                      "org.freedesktop.portal.GlobalShortcuts", "CreateSession",
                      GLib.Variant("(a{sv})", ({"handle_token": GLib.Variant("s", tok),
                                                 "session_handle_token": GLib.Variant("s", tok + "s")},)),
                      None, 0, 5000, None)

    def _bind(self):
        tok = f"ksb{os.getpid()}"
        sc = [("lagre-klipp", {"description": GLib.Variant("s", "Lagre klipp (Kontrollsenter)"),
                               "preferred_trigger": GLib.Variant("s", "F8")})]
        self.bus.call(("org.freedesktop.portal.Desktop"), "/org/freedesktop/portal/desktop",
                      "org.freedesktop.portal.GlobalShortcuts", "BindShortcuts",
                      GLib.Variant("(oa(sa{sv})sa{sv})", (self.session, sc, "", {"handle_token": GLib.Variant("s", tok)})),
                      None, 0, -1, None, None, None)
        self.ok = True

    def _activated(self, _c, _s, _p, _i, _sig, params):
        session, sid = params.unpack()[:2]
        if sid == "lagre-klipp":
            self.cb()


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
        r.hotkey = Hotkey(lambda: _hotkey_pressed())


def _hotkey_pressed():
    r = INSTANCE
    if r:
        threading.Thread(target=r.save, daemon=True).start()


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
