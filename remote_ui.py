"""Kortet «Mobil og nettbrett» i Hjemme-fanen: slå fjernstyring av/på, par nye enheter og fjern gamle."""
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk  # noqa: E402

import i18n  # noqa: E402
import remote  # noqa: E402


FIX_PS = r'''$ErrorActionPreference = "Continue"
# 1) blokkeringsregler Windows lagde for Kontrollsenters Python (når «Tillat»-spørsmålet ble avbrutt)
Get-NetFirewallApplicationFilter | Where-Object { $_.Program -like "*msys64*python*" } | ForEach-Object {
  $r = $_ | Get-NetFirewallRule
  if ($r.Direction -eq "Inbound" -and $r.Action -eq "Block") { Remove-NetFirewallRule -Name $r.Name }
}
# 2) tillat Kontrollsenter (Python fra MSYS2) og port 27100 – hjemmenett og Tailscale
foreach ($n in "Kontrollsenter fjernstyring", "Kontrollsenter fjernstyring (Tailscale)", "Kontrollsenter (Python)") {
  Remove-NetFirewallRule -DisplayName $n -ErrorAction SilentlyContinue
}
New-NetFirewallRule -DisplayName "Kontrollsenter fjernstyring" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 27100 -Profile Private,Domain | Out-Null
New-NetFirewallRule -DisplayName "Kontrollsenter fjernstyring (Tailscale)" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 27100 -RemoteAddress 100.64.0.0/10 -Profile Any | Out-Null
foreach ($exe in "C:\msys64\ucrt64\bin\pythonw.exe", "C:\msys64\ucrt64\bin\python.exe") {
  if (Test-Path $exe) {
    New-NetFirewallRule -DisplayName "Kontrollsenter (Python)" -Direction Inbound -Action Allow -Program $exe -Protocol TCP -LocalPort 27100 -Profile Private,Domain | Out-Null
  }
}
# 3) hjemmenettet som «Privat» (ellers gjelder ikke reglene over) – bare nettverk med en vanlig ruter
Get-NetConnectionProfile | Where-Object { $_.NetworkCategory -eq "Public" -and $_.IPv4Connectivity -ne "Disconnected" -and $_.InterfaceAlias -notlike "*Tailscale*" } |
  ForEach-Object { Set-NetConnectionProfile -InterfaceIndex $_.InterfaceIndex -NetworkCategory Private }
'''


def _dim(text, wrap=True):
    lab = Gtk.Label(label=i18n.tr(text), xalign=0, wrap=wrap)
    lab.add_css_class("dim-label")
    return lab


class RemoteCard(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("card")
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side, v in (("top", 14), ("bottom", 14), ("start", 16), ("end", 16)):
            getattr(inner, f"set_margin_{side}")(v)
        self.append(inner)
        head = Gtk.Box(spacing=10)
        t = Gtk.Label(label=i18n.tr("Mobil og nettbrett"), xalign=0, hexpand=True)
        t.add_css_class("heading")
        head.append(t)
        head.append(Gtk.Label(label=i18n.tr("Tillat fjernstyring")))
        self.sw = Gtk.Switch(active=remote.load_cfg()["enabled"], valign=Gtk.Align.CENTER)
        self.sw.connect("notify::active", self._on_switch)
        head.append(self.sw)
        inner.append(head)
        inner.append(_dim("Styr PC-en og se alt fra Android-appen «Kontrollsenter» (mobil og nettbrett). Bare "
                          "enheter på hjemmenettet som er paret med en kode fra denne PC-en, får tilgang."))
        self.addr = Gtk.Label(xalign=0, selectable=True, wrap=True)
        self.addr.add_css_class("title-4")
        inner.append(self.addr)
        self.apk = _dim("")
        self.apk.set_selectable(True)
        inner.append(self.apk)
        row = Gtk.Box(spacing=8)
        self.pair_btn = Gtk.Button(label=i18n.tr("Par ny enhet"))
        self.pair_btn.add_css_class("suggested-action")
        self.pair_btn.connect("clicked", self._pair)
        row.append(self.pair_btn)
        self.pair_lim = Gtk.Button(label=i18n.tr("Par begrenset enhet"),
                                   tooltip_text=i18n.tr("Kan se alt, starte spill og styre lyd – men ikke slå av PC-en, "
                                                        "endre vifter, strømmodus eller avslutte programmer"))
        self.pair_lim.connect("clicked", lambda *_: self._pair(None, "begrenset"))
        row.append(self.pair_lim)
        inner.append(row)
        self.code = Gtk.Label(xalign=0, selectable=True)
        self.code.add_css_class("title-1")
        self.code.add_css_class("numeric")
        self.code.set_visible(False)
        inner.append(self.code)
        self.code_info = _dim("")
        self.code_info.set_visible(False)
        inner.append(self.code_info)
        self.msg = _dim("")
        inner.append(self.msg)
        self.lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.lb.add_css_class("boxed-list")
        inner.append(self.lb)
        import sys
        if sys.platform == "win32":
            fw = Gtk.Box(spacing=8)
            fl = _dim("Finner ikke appen PC-en? Windows-brannmuren kan blokkere Kontrollsenter (særlig hvis "
                      "«Tillat»-spørsmålet ble lukket). Denne knappen retter det, og setter hjemmenettet som privat.")
            fl.set_hexpand(True)
            fw.append(fl)
            fb = Gtk.Button(label=i18n.tr("Rett brannmuren"), valign=Gtk.Align.CENTER)
            fb.connect("clicked", self._fix_firewall)
            fw.append(fb)
            inner.append(fw)
        # utenfor hjemmenettet
        sep = Gtk.Label(label=i18n.tr("Utenfor hjemmenettet (Tailscale)"), xalign=0)
        sep.add_css_class("heading")
        sep.set_margin_top(8)
        inner.append(sep)
        try:
            import apps_ui
            inner.append(apps_ui.need("away"))
        except Exception:  # noqa: BLE001
            pass
        inner.append(_dim("Tailscale er et privat, kryptert nett mellom dine egne enheter – gratis for privat bruk. "
                          "Slå det på her og installer Tailscale-appen på mobilen/nettbrettet med samme konto. "
                          "Da virker Kontrollsenter-appen overalt, uten å åpne noe i ruteren."))
        tsrow = Gtk.Box(spacing=8)
        self.ts_lab = Gtk.Label(xalign=0, hexpand=True, wrap=True, selectable=True)
        tsrow.append(self.ts_lab)
        self.ts_btn = Gtk.Button(label=i18n.tr("Slå på Tailscale"), valign=Gtk.Align.CENTER)
        self.ts_btn.connect("clicked", self._ts_on)
        tsrow.append(self.ts_btn)
        inner.append(tsrow)
        self.ts_msg = _dim("")
        inner.append(self.ts_msg)
        wsep = Gtk.Label(label=i18n.tr("Slå på PC-en fra appen (Wake-on-LAN)"), xalign=0)
        wsep.add_css_class("heading")
        wsep.set_margin_top(8)
        inner.append(wsep)
        wrow = Gtk.Box(spacing=8)
        self.wol_lab = Gtk.Label(xalign=0, hexpand=True, wrap=True)
        wrow.append(self.wol_lab)
        self.wol_btn = Gtk.Button(label=i18n.tr("Slå på Wake-on-LAN"), valign=Gtk.Align.CENTER)
        self.wol_btn.connect("clicked", self._wol_on)
        wrow.append(self.wol_btn)
        inner.append(wrow)
        self._timer = 0
        r = remote.INSTANCE
        if r:
            r.on_paired = self._paired
        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self):
        r = remote.INSTANCE
        on = bool(r and r.running)
        ips = remote.local_ips()
        if on and ips:
            self.addr.set_label("  ·  ".join(f"http://{ip}:{remote.PORT}" for ip in ips[:2]))
            self.apk.set_label(i18n.tr("Appen: åpne {} i nettleseren på mobilen/nettbrettet for å laste ned "
                                       "Kontrollsenter.apk – eller hent den fra NAS-en (Kontrollsenter → Android).")
                               .replace("{}", f"http://{ips[0]}:{remote.PORT}/app/kontrollsenter.apk"))
        else:
            self.addr.set_label(i18n.tr("Av") if not on else i18n.tr("Fant ingen adresse på hjemmenettet"))
            self.apk.set_label("")
        self.pair_btn.set_sensitive(on)
        self.pair_lim.set_sensitive(on)
        while (ch := self.lb.get_first_child()):
            self.lb.remove(ch)
        devs = remote.load_cfg()["devices"]
        for d in devs:
            b = Gtk.Box(spacing=10)
            for side, v in (("top", 8), ("bottom", 8), ("start", 12), ("end", 8)):
                getattr(b, f"set_margin_{side}")(v)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            col.append(Gtk.Label(label="📱  " + d.get("name", "?"), xalign=0))
            last = d.get("last") or 0
            when = time.strftime("%d.%m %H:%M", time.localtime(last)) if last else i18n.tr("aldri")
            role = d.get("role", "full")
            s = Gtk.Label(label=i18n.tr("Sist brukt") + f": {when} · " +
                          (i18n.tr("begrenset tilgang") if role == "begrenset" else i18n.tr("full tilgang")), xalign=0)
            s.add_css_class("caption")
            s.add_css_class("dim-label")
            col.append(s)
            b.append(col)
            tg = Gtk.Button(label=i18n.tr("Gi full tilgang") if role == "begrenset" else i18n.tr("Begrens"),
                            valign=Gtk.Align.CENTER)
            tg.add_css_class("flat")
            tg.connect("clicked", lambda _b, h=d.get("hash"), r=role: self._role(h, "full" if r == "begrenset" else "begrenset"))
            b.append(tg)
            rm = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text=i18n.tr("Fjern tilgangen"),
                            valign=Gtk.Align.CENTER)
            rm.add_css_class("flat")
            rm.connect("clicked", lambda _b, h=d.get("hash"): self._remove(h))
            b.append(rm)
            self.lb.append(b)
        self.lb.set_visible(bool(devs))
        self._ts_refresh()
        self._wol_refresh()

    # ---- Windows-brannmuren -------------------------------------------
    def _fix_firewall(self, *_):
        import os
        import tempfile
        import threading
        self.msg.set_label(i18n.tr("Windows ber om administratortilgang …"))
        script = os.path.join(tempfile.gettempdir(), "kontrollsenter-brannmur.ps1")
        with open(script, "w", encoding="utf-8-sig") as f:
            f.write(FIX_PS)

        def work():
            import winsupport as WS
            code, out = WS.run(["powershell", "-NoProfile", "-Command",
                                f"Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList "
                                f"'-NoProfile -ExecutionPolicy Bypass -File \"{script}\"'"], 180)
            msg = (i18n.tr("Brannmuren er rettet ✓ – prøv appen igjen") if code == 0 else
                   i18n.tr("Ble avbrutt") + f" ({out.strip()[:120]})")
            GLib.idle_add(lambda: (self.msg.set_label(msg), False)[1])
        threading.Thread(target=work, daemon=True).start()

    # ---- Wake-on-LAN --------------------------------------------------
    def _wol_refresh(self):
        import threading

        def work():
            import remote_extra
            st = remote_extra.wol_status()
            GLib.idle_add(self._wol_show, st)
        threading.Thread(target=work, daemon=True).start()

    def _wol_show(self, st):
        import sys
        if sys.platform == "win32":
            self.wol_lab.set_label(i18n.tr("Slå på «Wake on Magic Packet» i nettverkskortets innstillinger (Enhetsbehandling) "
                                           "og Wake-on-LAN i BIOS. Appen sender signalet."))
            self.wol_btn.set_visible(False)
        elif st.get("enabled"):
            self.wol_lab.set_label("✅ " + i18n.tr("På for") + f" {st.get('conn')} ({st.get('mac')}). " +
                                   i18n.tr("Wake-on-LAN må også være på i BIOS."))
            self.wol_btn.set_visible(False)
        else:
            self.wol_lab.set_label(i18n.tr("Av") + (f" ({st.get('conn')})" if st.get("conn") else "") + ". " +
                                   i18n.tr("Slå det på her, og sjekk at Wake-on-LAN er på i BIOS."))
            self.wol_btn.set_visible(bool(st.get("conn")))
        return False

    def _wol_on(self, *_):
        import threading

        def work():
            import remote_extra
            try:
                remote_extra.enable_wol()
                msg = i18n.tr("Wake-on-LAN er slått på ✓")
            except Exception as e:  # noqa: BLE001
                msg = str(e)
            GLib.idle_add(lambda: (self.msg.set_label(msg), self._wol_refresh(), False)[2])
        threading.Thread(target=work, daemon=True).start()

    # ---- Tailscale ----------------------------------------------------
    def _ts_refresh(self):
        import threading

        def work():
            info = remote.tailscale_info(force=True)
            GLib.idle_add(self._ts_show, info)
        threading.Thread(target=work, daemon=True).start()

    def _ts_show(self, info):
        if info["running"]:
            self.ts_lab.set_label("✅ " + i18n.tr("Tailscale er på") + f": {info['ip']}"
                                  + (f" · {info['name']}" if info.get("name") else "")
                                  + (f" · {info['login']}" if info.get("login") else ""))
            self.ts_btn.set_visible(False)
        elif info["installed"]:
            self.ts_lab.set_label(i18n.tr("Tailscale er installert, men ikke på") +
                                  (f" ({info['state']})" if info.get("state") else ""))
            self.ts_btn.set_visible(True)
        else:
            self.ts_lab.set_label(i18n.tr("Tailscale er ikke installert"))
            self.ts_btn.set_label(i18n.tr("Installer Tailscale"))
            self.ts_btn.set_visible(True)
        return False

    def _ts_on(self, *_):
        import os
        import re
        import subprocess
        import sys
        import threading
        self.ts_btn.set_sensitive(False)
        self.ts_msg.set_label(i18n.tr("Starter Tailscale … (innloggingssiden åpnes i nettleseren)"))

        def say(t):
            GLib.idle_add(lambda: (self.ts_msg.set_label(t), False)[1])

        def open_url(u):
            if sys.platform == "win32":
                os.startfile(u)
            else:
                subprocess.Popen(["xdg-open", u], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        def work():
            try:
                if sys.platform == "win32":
                    b = remote.tailscale_bin()
                    if not b:
                        import winsupport as WS
                        say(i18n.tr("Installerer Tailscale (Windows spør om tilgang) …"))
                        WS.run(["winget", "install", "-e", "--id", "Tailscale.Tailscale", "--silent",
                                "--accept-package-agreements", "--accept-source-agreements"], 900)
                        b = remote.tailscale_bin()
                    if not b:
                        say(i18n.tr("Tailscale ble ikke installert"))
                        return
                    gui = os.path.join(os.path.dirname(b), "tailscale-ipn.exe")
                    if os.path.exists(gui):
                        subprocess.Popen([gui])
                    cmd = [b, "up"]
                else:
                    if not remote.tailscale_bin():
                        say(i18n.tr("Tailscale mangler – installer pakken «tailscale» (Bazzite har den allerede)"))
                        return
                    user = os.environ.get("USER") or os.getlogin()
                    if not re.fullmatch(r"[a-z_][a-z0-9_.-]*", user):
                        say(i18n.tr("Ugyldig brukernavn"))
                        return
                    # én passordforespørsel: start tjenesten og la deg styre Tailscale uten root etterpå
                    cmd = ["pkexec", "sh", "-c", "systemctl enable --now tailscaled && "
                           f"exec tailscale up --operator={user} --timeout=600s"]
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                     errors="replace")
                opened = False
                for line in p.stdout:
                    m = re.search(r"https://login\.tailscale\.com/\S+", line)
                    if m and not opened:
                        opened = True
                        open_url(m.group(0))
                        say(i18n.tr("Logg inn i nettleseren – samme konto som på mobilen/nettbrettet"))
                code = p.wait()
                say(i18n.tr("Tailscale er på ✓") if code == 0 else
                    i18n.tr("Tailscale ble ikke startet (avbrutt eller feil)"))
            except Exception as e:  # noqa: BLE001
                say(str(e))
            finally:
                GLib.idle_add(lambda: (self.ts_btn.set_sensitive(True), self._ts_refresh(), False)[2])
        threading.Thread(target=work, daemon=True).start()

    def _on_switch(self, sw, _p):
        c = remote.load_cfg()
        c["enabled"] = sw.get_active()
        remote.save_cfg(c)
        r = remote.INSTANCE
        if r:
            if sw.get_active():
                ok, err = r.start()
                self.msg.set_label("" if ok else err)
            elif __import__("funksjoner").on("chat"):     # chatten trenger tjenesten – mobilen stenges ute
                self.msg.set_label("Mobilappen kan ikke lenger styre PC-en (chatten virker fortsatt)")
            else:
                r.stop()
                self.msg.set_label("")
        self.refresh()

    def _pair(self, _btn=None, role="full"):
        r = remote.INSTANCE
        if not r:
            return
        code = r.new_code(role)
        self.code.set_label(f"{code[:3]} {code[3:]}")
        self.code.set_visible(True)
        self.code_info.set_visible(True)
        if self._timer:
            GLib.source_remove(self._timer)
        self._timer = GLib.timeout_add_seconds(1, self._tick)
        self._tick()

    def _tick(self):
        r = remote.INSTANCE
        left = int(r.code_until - time.time()) if r and r.code else 0
        if left <= 0:
            self.code.set_visible(False)
            self.code_info.set_visible(False)
            self._timer = 0
            return False
        self.code_info.set_label(i18n.tr("Skriv koden i appen. Gyldig i {} til.").replace(
            "{}", f"{left // 60}:{left % 60:02d}"))
        return True

    def _paired(self, name):
        self.code.set_visible(False)
        self.code_info.set_visible(False)
        self.msg.set_label(i18n.tr("«{}» er paret ✓").replace("{}", name))
        self.refresh()

    def _role(self, h, role):
        c = remote.load_cfg()
        for d in c["devices"]:
            if d.get("hash") == h:
                d["role"] = role
        remote.save_cfg(c)
        self.refresh()

    def _remove(self, h):
        c = remote.load_cfg()
        c["devices"] = [d for d in c["devices"] if d.get("hash") != h]
        remote.save_cfg(c)
        self.refresh()
