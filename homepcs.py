"""PC-er hjemme: hver PC med Kontrollsenter legger en liten statusfil på NAS-en hvert 5. minutt
(\\\\192.168.1.3\\Public\\Kontrollsenter\\PC-er\\<navn>.json), og alle PC-ene vises her.

Bare navn, system, versjon, temperaturer, last, strøm, oppetid og spill som kjører – ingen filer eller passord.
"""
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk  # noqa: E402

import i18n  # noqa: E402

CFG = os.path.expanduser("~/.config/systemmonitor/hjemme.json")
REMOTE = "PC-er"
EVERY = 300
STALE = 15 * 60


def load_cfg():
    try:
        with open(CFG) as f:
            return {"share": True, **json.load(f)}
    except (OSError, ValueError):
        return {"share": True}


def save_cfg(c):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    with open(CFG, "w") as f:
        json.dump(c, f)


def _distro():
    if sys.platform == "win32":
        ver = platform.version().split(".")
        return "Windows 11" if len(ver) > 2 and int(ver[2]) >= 22000 else f"Windows {platform.release()}"
    try:
        for line in open("/etc/os-release"):
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return platform.system()


def _model():
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\BIOS") as k:
                for name in ("BaseBoardProduct", "SystemProductName"):
                    try:
                        v = winreg.QueryValueEx(k, name)[0].strip()
                        if v and "system product name" not in v.lower():
                            return v
                    except OSError:
                        continue
        except OSError:
            pass
        return ""
    for p in ("/sys/class/dmi/id/product_name", "/sys/class/dmi/id/board_name"):
        try:
            v = open(p).read().strip()
            if v and not any(x in v.lower() for x in ("to be filled", "system product name", "default string", "o.e.m")):
                return v
        except OSError:
            pass
    return ""


def status(win):
    import applog
    import savegames
    nv = win.nvidia.data if getattr(win, "nvidia", None) and win.nvidia.available else None
    from sensors import uptime_seconds
    up = uptime_seconds()
    bg = getattr(win, "bg", None)
    bats = []
    try:
        from sensors import battery_info
        b = battery_info(win.batteries) if getattr(win, "batteries", None) else None
        if b:
            bats = [b["pct"], b["state"]]
    except Exception:  # noqa: BLE001
        pass
    return {"name": savegames.pc_name(), "model": _model(), "distro": _distro(), "version": applog.RUNNING,
            "cpu_t": getattr(win, "_cpu_t", None), "gpu_t": nv.get("temp") if nv else None,
            "cpu_l": round(getattr(win, "_cpu_load", 0) or 0), "watts": round((getattr(win, "_power", {}) or {})
                                                                              .get("total") or 0),
            "uptime": int(up), "game": getattr(bg, "game_name", None) if bg else None, "battery": bats,
            "time": time.time(), **_extra()}


def _extra():
    out = {}
    try:
        import features
        out.update(features.share_fields())
    except Exception:  # noqa: BLE001
        pass
    try:
        import remote
        import watch
        out["ips"] = [ip for ip in remote.local_ips() if ip.startswith(("192.168.", "10.", "172."))][:2]
        out["watch"] = bool(watch.cfg()["allow"]) and remote.load_cfg().get("enabled", False)
    except Exception:  # noqa: BLE001
        pass
    return out


def publish(win, off=False):
    """Legg denne PC-ens status på NAS-en (kalles fra bakgrunnen hvert 5. minutt)."""
    import lanupdate as L
    if os.environ.get("SYSTEMMONITOR_APP_ID"):            # test- og demoutgaver deler ikke
        return False
    if not load_cfg().get("share") or not L.on_lan():
        return False
    tmp = Path(tempfile.mkdtemp())
    try:
        st = status(win)
        st["off"] = off
        f = tmp / f"{st['name']}.json"
        f.write_text(json.dumps(st))
        _host, share, folder = L._split()
        L.smb_mkdir(f"{folder}/{REMOTE}")
        L._smb(f'cd "{REMOTE}"; put "{f}" "{f.name}"', 60)
        return True
    except Exception:  # noqa: BLE001
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def fetch():
    """Alle PC-er fra NAS-en: [dict]. Tom liste hvis NAS-en ikke svarer."""
    import lanupdate as L
    if not L.on_lan():
        return None
    tmp = Path(tempfile.mkdtemp())
    try:
        L._smb(f'cd "{REMOTE}"; prompt OFF; lcd "{tmp}"; mget *.json', 60)
        out = []
        for f in tmp.glob("*.json"):
            try:
                out.append(json.loads(f.read_text()))
            except ValueError:
                pass
        return sorted(out, key=lambda d: d.get("name", "").lower())
    except Exception:  # noqa: BLE001
        return []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class Sharer:
    """Kobles til bakgrunnsløkka: deler status hvert 5. minutt."""

    def __init__(self, win):
        self.win = win
        self.last = time.time() - EVERY + 60          # første gang ett minutt etter oppstart

    def tick(self):
        if time.time() - self.last >= EVERY:
            self.last = time.time()
            threading.Thread(target=publish, args=(self.win,), daemon=True).start()


def _ago(t):
    s = time.time() - t
    if s < 90:
        return i18n.tr("nå")
    if s < 3600:
        return f"{s // 60:.0f} " + i18n.tr("min siden")
    if s < 86400:
        return f"{s // 3600:.0f} " + i18n.tr("t siden")
    return time.strftime("%d.%m %H:%M", time.localtime(t))


class HomePage(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(12)
        self.set_child(box)
        top = Gtk.Box(spacing=12)
        info = Gtk.Label(label=i18n.tr("PC-ene som har Kontrollsenter og er på hjemmenettet. Hver PC deler en liten "
                                       "statusfil på NAS-en hvert 5. minutt."), xalign=0, wrap=True, hexpand=True)
        info.add_css_class("dim-label")
        top.append(info)
        sw = Gtk.Switch(active=load_cfg().get("share", True), valign=Gtk.Align.CENTER)

        def set_share(w, _p):
            c = load_cfg()
            c["share"] = w.get_active()
            save_cfg(c)
        sw.connect("notify::active", set_share)
        top.append(Gtk.Label(label=i18n.tr("Del denne PC-en")))
        top.append(sw)
        ref = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text=i18n.tr("Oppdater"), valign=Gtk.Align.CENTER)
        ref.add_css_class("flat")
        ref.connect("clicked", lambda *_: self.refresh(publish_first=True))
        top.append(ref)
        box.append(top)
        try:
            import remote_ui
            box.append(remote_ui.RemoteCard())
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("fjernstyring-kort")
        hint = Gtk.Label(label=i18n.tr("Familie-chat, familiekontroll og «Se på» ligger i fanen Familie."), xalign=0)
        hint.add_css_class("ks-sub")
        box.append(hint)
        self.flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True, max_children_per_line=3,
                                min_children_per_line=1, column_spacing=12, row_spacing=12)
        box.append(self.flow)
        self.refresh(publish_first=True)
        GLib.timeout_add_seconds(60, lambda: self.refresh() or True)

    def refresh(self, publish_first=False):
        root = self.get_root()

        def work():
            if publish_first and root is not None:
                publish(root)
            GLib.idle_add(self.show, fetch())
        threading.Thread(target=work, daemon=True).start()

    def show(self, pcs):
        while (ch := self.flow.get_first_child()):
            self.flow.remove(ch)
        import ui
        if pcs is None:
            self.flow.append(ui.empty("ks-home-symbolic", "Ikke på hjemmenettet",
                                      "NAS-en (192.168.1.3) svarer ikke. PC-ene vises når du er hjemme."))
            return False
        if not pcs:
            self.flow.append(ui.empty("ks-home-symbolic", "Ingen PC-er ennå",
                                      "Når Kontrollsenter kjører på en PC på hjemmenettet, dukker den opp her."))
            return False
        import applog
        import savegames
        me = savegames.pc_name()
        for p in pcs:
            on = time.time() - p.get("time", 0) < STALE
            c = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            c.add_css_class("card")
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            for side, v in (("top", 14), ("bottom", 14), ("start", 16), ("end", 16)):
                getattr(inner, f"set_margin_{side}")(v)
            c.append(inner)
            head = Gtk.Box(spacing=8)
            icon = "ks-laptop-symbolic" if p.get("battery") else "ks-lcd-symbolic"
            img = Gtk.Image(icon_name=icon, pixel_size=24)
            img.add_css_class("tile-icon" if on else "dim-label")
            head.append(img)
            name = Gtk.Label(label=p.get("name", "?") + ("  (" + i18n.tr("denne") + ")" if p.get("name") == me else ""),
                             xalign=0, hexpand=True, ellipsize=3)
            name.add_css_class("heading")
            head.append(name)
            dot = Gtk.Label(label="● " + (i18n.tr("på") if on else i18n.tr("av")))
            dot.add_css_class("success" if on else "dim-label")
            head.append(dot)
            inner.append(head)
            sub = Gtk.Label(label=" · ".join(x for x in (p.get("model"), p.get("distro")) if x), xalign=0,
                            wrap=True)
            sub.add_css_class("caption")
            sub.add_css_class("dim-label")
            inner.append(sub)
            if on:
                vals = []
                if p.get("cpu_t") is not None:
                    vals.append(f"CPU {p['cpu_t']:.0f} °C · {p.get('cpu_l', 0)} %")
                if p.get("gpu_t") is not None:
                    vals.append(f"GPU {p['gpu_t']:.0f} °C")
                if p.get("watts"):
                    vals.append(f"{p['watts']} W")
                if p.get("battery"):
                    vals.append(f"🔋 {p['battery'][0]} %")
                v = Gtk.Label(label="  ·  ".join(vals), xalign=0, wrap=True)
                v.add_css_class("numeric")
                inner.append(v)
                if p.get("game"):
                    g = Gtk.Label(label="▶ " + p["game"], xalign=0, ellipsize=3)
                    inner.append(g)
                if p.get("name") != me and p.get("watch") and p.get("ips"):
                    wb = Gtk.Button(label="📺 " + i18n.tr("Se på"), halign=Gtk.Align.START)
                    wb.set_tooltip_text(i18n.tr("Se skjermen live – bare visning, den andre får beskjed"))
                    wb.add_css_class("suggested-action" if p.get("game") else "flat")
                    wb.connect("clicked", lambda _b, pp=p: __import__("watch_ui").WatchWindow(
                        self.get_root(), pp["name"], pp["ips"][0], pp.get("game")).present())
                    inner.append(wb)
            ver = p.get("version", "?")
            from lanupdate import newer
            old = newer(applog.RUNNING, ver) if ver != "?" else False
            foot = Gtk.Label(label=f"{i18n.tr('Versjon')} {ver}" + (" – " + i18n.tr("kan oppdateres") if old else "")
                             + f" · {i18n.tr('sist sett')} {_ago(p.get('time', 0))}", xalign=0)
            foot.add_css_class("caption")
            foot.add_css_class("warning" if old else "dim-label")
            inner.append(foot)
            self.flow.append(c)
        return False
