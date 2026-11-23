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
    try:                                                   # spill som er installert (23) og Wi-Fi-signal (60)
        import equipment
        out.update(equipment.status_fields())
    except Exception:  # noqa: BLE001
        pass
    try:                                                   # familiekonkurransen
        import familyfun
        out.update(familyfun.status_fields())
    except Exception:  # noqa: BLE001
        pass
    try:                                                   # huset: WoL, inaktiv tid, strøm per måned
        import house
        out.update(house.status_fields())
    except Exception:  # noqa: BLE001
        pass
    try:                                                   # oppdateringer og automatikk (PC-er-siden)
        import updates
        out["upd_auto"] = updates.auto_on()
        out["upd_n"] = updates.total() if updates.cached() else None
        out["upd_running"] = updates.running()
    except Exception:  # noqa: BLE001
        pass
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


def live(p, timeout=3):
    """Full live-status direkte fra en PC hjemme (husnøkkelen), med NAS-dataene som reserve."""
    import json as _j
    import urllib.request
    import watch
    base = {**p, "friend": p.get("name"), "online": False}
    for ip in (p.get("ips") or [])[:2]:
        try:
            url = f"http://{ip}:27100/api/house/status?fk={watch.house_key()}"
            with urllib.request.urlopen(url, timeout=timeout) as r:
                d = _j.load(r)
            return {**base, **d, "online": True, "_seen": time.time(), "addr": ip}
        except Exception:  # noqa: BLE001
            continue
    base["_seen"] = p.get("time")
    return base


def update_pc(p, timeout=180):
    """Be en PC hjemme oppdatere seg fra NAS-en og starte Kontrollsenter på nytt. Returnerer (ok, melding)."""
    import json as _j
    import urllib.request
    import watch
    for ip in (p.get("ips") or [])[:2]:
        try:
            url = f"http://{ip}:27100/api/house/update?fk={watch.house_key()}"
            with urllib.request.urlopen(url, timeout=timeout) as r:
                d = _j.load(r)
            return bool(d.get("ok")), d.get("msg", "")
        except Exception as e:  # noqa: BLE001
            last = str(e)
            if "403" in last:
                return False, "husnøkkelen stemmer ikke (start Kontrollsenter på nytt der)"
            if "401" in last or "404" in last:            # svarer, men kjenner ikke kommandoen (eldre enn 0.64)
                return False, _too_old(p)
            continue
    return False, "svarer ikke" + (f" ({last[:60]})" if p.get("ips") else " (ingen adresse)")


def house_call(p, what, timeout=60, **q):
    """Kall /api/house/<what> på en annen PC hjemme. Returnerer (ok, svar eller feilmelding)."""
    import json as _j
    import urllib.parse
    import urllib.request
    import watch
    last = "ingen adresse"
    qs = urllib.parse.urlencode({"fk": watch.house_key(), **q})
    for ip in (p.get("ips") or [])[:2]:
        try:
            with urllib.request.urlopen(f"http://{ip}:27100/api/house/{what}?{qs}", timeout=timeout) as r:
                return True, _j.load(r)
        except Exception as e:  # noqa: BLE001
            last = str(e)
            if "403" in last:
                return False, "husnøkkelen stemmer ikke"
            if "401" in last or "404" in last:
                return False, f"har {p.get('version', '?')} – oppdater Kontrollsenter der først"
    return False, "svarer ikke" if "timed out" in last or "refused" in last else last[:80]


def _too_old(p):
    """PC-en har en versjon fra før fjernoppdatering fantes: si fra til den som sitter der (familie-chatten)."""
    import applog
    import savegames
    ver = p.get("version", "?")
    try:
        import features
        features.send_to(p.get("name"), savegames.pc_name(),
                         f"🔄 Ny versjon av Kontrollsenter ({applog.RUNNING}) er klar på NAS-en. Åpne Kontrollsenter "
                         f"og trykk «Oppdater» (Innstillinger → Oppdatering) – etter det kan PC-ene oppdateres "
                         f"herfra med ett trykk.")
        sent = " – beskjed er sendt til PC-en"
    except Exception:  # noqa: BLE001
        sent = ""
    return f"har {ver} – for gammel til å oppdateres herfra. Oppdater én gang på PC-en selv{sent}"


def update_all(pcs, progress=None):
    """Oppdater alle PC-ene som er på (ikke denne). [(navn, ok, melding)]"""
    import savegames
    me = savegames.pc_name()
    import applog
    from lanupdate import newer
    todo = [p for p in pcs if p.get("name") != me and time.time() - p.get("time", 0) < STALE
            and (not p.get("version") or newer(applog.RUNNING, p["version"]) or p["version"] != applog.RUNNING)]
    out = []
    import progress as P
    pt = P.begin("Oppdaterer PC-ene hjemme", f"{len(todo)} PC-er")
    for n, p in enumerate(todo):
        pt.step(n, len(todo), p.get("name"))
        if progress:
            progress(f"Oppdaterer {p.get('name')} …")
        ok, msg = update_pc(p)
        out.append((p.get("name"), ok, msg))
    bad = [x for x in out if not x[1]]
    pt.done(f"{len(out) - len(bad)} av {len(out)} er oppdatert" if out else "Ingen andre PC-er er på", not bad)
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
        ref = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text=i18n.tr("Oppdater"), valign=Gtk.Align.CENTER)
        ref.add_css_class("flat")
        ref.connect("clicked", lambda *_: self.refresh(publish_first=True))
        top.append(ref)
        box.append(top)
        ur = Gtk.Box(spacing=10)
        self.upd_btn = Gtk.Button(label=i18n.tr("Oppdater alle PC-ene"))
        self.upd_btn.add_css_class("suggested-action")
        self.upd_btn.add_css_class("pill")
        self.upd_btn.set_tooltip_text(i18n.tr("Henter nyeste versjon fra NAS-en på alle PC-ene som er på, og starter "
                                              "Kontrollsenter på nytt der"))
        self.upd_btn.connect("clicked", self._update_all)
        ur.append(self.upd_btn)
        self.all_btn = Gtk.Button(label=i18n.tr("Oppdater alt på alle"))
        self.all_btn.add_css_class("pill")
        self.all_btn.set_tooltip_text(i18n.tr("«Oppdater alt» på hver PC som er på: Kontrollsenter, programmer, "
                                              "system og fastvare"))
        self.all_btn.connect("clicked", self._update_everything)
        ur.append(self.all_btn)
        npc = Gtk.Button(label=i18n.tr("Ny PC? Hent oppsett"))
        npc.add_css_class("pill")
        npc.connect("clicked", lambda *_: __import__("homeplus_ui").new_pc_dialog(self.get_root()))
        ur.append(npc)
        self.upd_msg = Gtk.Label(xalign=0, wrap=True, hexpand=True)
        self.upd_msg.add_css_class("ks-sub")
        ur.append(self.upd_msg)
        box.append(ur)
        self._pcs = []
        hint = Gtk.Label(label=i18n.tr("Mobilappen, fjernstyring og «Del denne PC-en» ligger i Innstillinger → Mobil. "
                                       "Familie-chat og «Se på» ligger i Familie."), xalign=0, wrap=True)
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

    def _update_all(self, *_):
        self.upd_btn.set_sensitive(False)
        self.upd_msg.set_label(i18n.tr("Oppdaterer …"))

        def work():
            res = update_all(self._pcs or fetch() or [], lambda t: GLib.idle_add(self.upd_msg.set_label, t))
            GLib.idle_add(done, res)

        def done(res):
            self.upd_btn.set_sensitive(True)
            self.upd_msg.set_label("  ·  ".join(f"{'✓' if ok else '✗'} {n}: {m}" for n, ok, m in res)
                                   or i18n.tr("Ingen andre PC-er er på akkurat nå"))
            GLib.timeout_add_seconds(25, lambda: (self.refresh(), False)[1])     # se nye versjoner etter omstart
            return False
        threading.Thread(target=work, daemon=True).start()

    def _update_everything(self, *_):
        """«Oppdater alt» her og på alle de andre PC-ene som er på."""
        import savegames
        import updates
        self.all_btn.set_sensitive(False)
        self.upd_msg.set_label(i18n.tr("Starter «Oppdater alt» på alle PC-ene …"))
        me = savegames.pc_name()

        def work():
            out = []
            for p in self._pcs or fetch() or []:
                if time.time() - p.get("time", 0) >= STALE:
                    continue
                if p.get("name") == me:
                    ok = updates.update_all(self.get_root(), include_pcs=False)
                    out.append((me, True, "startet" if ok else "pågår allerede"))
                else:
                    ok, d = house_call(p, "updateall", 20)
                    out.append((p.get("name"), ok, d.get("msg", "startet") if ok else d))
            GLib.idle_add(done, out)

        def done(out):
            self.all_btn.set_sensitive(True)
            self.upd_msg.set_label("  ·  ".join(f"{'✓' if ok else '✗'} {n}: {m}" for n, ok, m in out)
                                   or i18n.tr("Ingen PC-er er på akkurat nå"))
            GLib.timeout_add_seconds(60, lambda: (self.refresh(publish_first=True), False)[1])
            return False
        threading.Thread(target=work, daemon=True).start()

    def _pc_updates(self, p, me, inner):
        """Per PC: «Oppdater alt» og automatikk av/på (denne PC-en direkte, de andre via hjemmenettet)."""
        import updates
        mine = p.get("name") == me
        row = Gtk.Box(spacing=8)
        n = updates.total() if mine and updates.cached() else p.get("upd_n")
        auto = updates.auto_on() if mine else p.get("upd_auto")
        lab = Gtk.Label(xalign=0, hexpand=True, wrap=True)
        lab.add_css_class("caption")
        if p.get("upd_running") or (mine and updates.running()):
            lab.set_label("🔄 " + i18n.tr("Oppdaterer …"))
        elif n is None:
            lab.set_label(i18n.tr("Oppdateringer: ikke sjekket"))
        else:
            lab.set_label("✅ " + i18n.tr("Alt oppdatert") if n == 0 else
                          "🔄 " + i18n.tr("{n} oppdateringer").replace("{n}", str(n)))
        row.append(lab)
        b = Gtk.Button(label=i18n.tr("Oppdater alt"), valign=Gtk.Align.CENTER)
        b.add_css_class("pill")
        if n:
            b.add_css_class("suggested-action")

        def go(btn):
            btn.set_sensitive(False)
            btn.set_label(i18n.tr("Starter …"))

            def work():
                if mine:
                    ok = updates.update_all(self.get_root())
                    msg = "startet" if ok else "pågår allerede"
                else:
                    ok, d = house_call(p, "updateall", 20)
                    msg = d.get("msg", "startet") if ok else d
                GLib.idle_add(lambda: (btn.set_label(("✓ " if ok else "✗ ") + str(msg)[:40]), False)[1])
            threading.Thread(target=work, daemon=True).start()
        b.connect("clicked", go)
        row.append(b)
        inner.append(row)
        if auto is None and not mine:                      # eldre versjon: vet ikke
            return
        ar = Gtk.Box(spacing=8)
        al = Gtk.Label(label=i18n.tr("Automatisk oppdatering og opprydding"), xalign=0, hexpand=True, wrap=True)
        al.add_css_class("caption")
        ar.append(al)
        sw = Gtk.Switch(active=bool(auto), valign=Gtk.Align.CENTER)

        def toggled(w, _p):
            on = w.get_active()
            if mine:
                if on != updates.auto_on():
                    updates.set_auto(on)
                return
            if getattr(w, "_rev", False):
                w._rev = False
                return

            def work():
                ok, d = house_call(p, "auto", 15, on="1" if on else "0")
                if not ok:
                    def back():
                        w._rev = True
                        w.set_active(not on)
                        al.set_label(i18n.tr("Automatisk oppdatering og opprydding") + f" – ✗ {d}")
                    GLib.idle_add(lambda: (back(), False)[1])
            threading.Thread(target=work, daemon=True).start()
        sw.connect("notify::active", toggled)
        ar.append(sw)
        inner.append(ar)

    def _open(self, p):
        import friends_ui
        on = time.time() - p.get("time", 0) < STALE
        dlg = friends_ui.FriendDialog({**p, "friend": p.get("name"), "online": on, "_seen": p.get("time")},
                                      fetch=lambda pp=p: live(pp))
        dlg.present(self.get_root())
        dlg._tick()                                    # hent live-data med en gang

    def show(self, pcs):
        self._pcs = pcs or []
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
            if p.get("name") != me:                      # vekk (WoL) eller legg i dvale
                pb = Gtk.Box(spacing=6)
                if not on and p.get("mac"):
                    wk = Gtk.Button(label="⏻ " + i18n.tr("Vekk"))
                    wk.add_css_class("pill")
                    wk.set_tooltip_text(i18n.tr("Wake-on-LAN – PC-en må ha det slått på (Nettverk i Kontrollsenter)"))

                    def do_wake(b, pp=p):
                        import house
                        try:
                            house.wake(pp["mac"], pp.get("ips"))
                            b.set_label("✓ " + i18n.tr("Vekket – tar et minutt"))
                        except Exception as e:  # noqa: BLE001
                            b.set_label(f"✗ {e}")
                        GLib.timeout_add_seconds(70, lambda: (self.refresh(), False)[1])
                    wk.connect("clicked", do_wake)
                    pb.append(wk)
                if on:
                    so = Gtk.Button(label="📤 " + i18n.tr("Send oppsettet mitt"))
                    so.add_css_class("pill")
                    so.connect("clicked", lambda _b, pp=p: __import__("homeplus_ui").send_setup_dialog(
                        self.get_root(), pp))
                    pb.append(so)
                    sl = Gtk.Button(label="😴 " + i18n.tr("Sov"))
                    sl.add_css_class("pill")

                    def do_sleep(b, pp=p):
                        b.set_sensitive(False)

                        def work():
                            import house
                            ok, d = house.system(pp, "sleep")
                            GLib.idle_add(lambda: (b.set_label(("✓ " if ok else "✗ ") + (i18n.tr("Sover") if ok
                                                                                          else str(d)[:30])), False)[1])
                        threading.Thread(target=work, daemon=True).start()
                    sl.connect("clicked", do_sleep)
                    pb.append(sl)
                if pb.get_first_child() is not None:
                    inner.append(pb)
            if on:
                try:
                    self._pc_updates(p, me, inner)
                except Exception:  # noqa: BLE001
                    applog.log.exception("oppdateringer per PC")
            ver = p.get("version", "?")
            from lanupdate import newer
            old = newer(applog.RUNNING, ver) if ver != "?" else False
            br = Gtk.Box(spacing=6)
            more = Gtk.Button(label=i18n.tr("Alt om PC-en"), halign=Gtk.Align.START)
            more.add_css_class("flat")
            more.connect("clicked", lambda _b, pp=p: self._open(pp))
            br.append(more)
            if old and on and p.get("name") != me:
                ub = Gtk.Button(label=i18n.tr("Oppdater"), halign=Gtk.Align.START)
                ub.add_css_class("suggested-action")

                def upd(_b, pp=p, btn=None):
                    _b.set_sensitive(False)
                    _b.set_label(i18n.tr("Oppdaterer …"))

                    def work():
                        ok, msg = update_pc(pp)
                        GLib.idle_add(lambda: (_b.set_label(("✓ " if ok else "✗ ") + msg[:40]), False)[1])
                        GLib.timeout_add_seconds(25, lambda: (self.refresh(), False)[1])
                    threading.Thread(target=work, daemon=True).start()
                ub.connect("clicked", upd)
                br.append(ub)
            inner.append(br)
            foot = Gtk.Label(label=f"{i18n.tr('Versjon')} {ver}" + (" – " + i18n.tr("kan oppdateres") if old else "")
                             + f" · {i18n.tr('sist sett')} {_ago(p.get('time', 0))}", xalign=0)
            foot.add_css_class("caption")
            foot.add_css_class("warning" if old else "dim-label")
            inner.append(foot)
            self.flow.append(c)
        try:                                     # kortene kan dras til ny plass – behold rekkefølgen etter oppdatering
            import sortbox
            sortbox.scan(self, "hjemme")
        except Exception:  # noqa: BLE001
            pass
        return False
