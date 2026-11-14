"""Kortet «Mobil og nettbrett» i Hjemme-fanen: slå fjernstyring av/på, par nye enheter og fjern gamle."""
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk  # noqa: E402

import i18n  # noqa: E402
import remote  # noqa: E402


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
        # utenfor hjemmenettet
        sep = Gtk.Label(label=i18n.tr("Utenfor hjemmenettet (Tailscale)"), xalign=0)
        sep.add_css_class("heading")
        sep.set_margin_top(8)
        inner.append(sep)
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
            s = Gtk.Label(label=i18n.tr("Sist brukt") + f": {when}", xalign=0)
            s.add_css_class("caption")
            s.add_css_class("dim-label")
            col.append(s)
            b.append(col)
            rm = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text=i18n.tr("Fjern tilgangen"),
                            valign=Gtk.Align.CENTER)
            rm.add_css_class("flat")
            rm.connect("clicked", lambda _b, h=d.get("hash"): self._remove(h))
            b.append(rm)
            self.lb.append(b)
        self.lb.set_visible(bool(devs))
        self._ts_refresh()

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
            else:
                r.stop()
                self.msg.set_label("")
        self.refresh()

    def _pair(self, *_):
        r = remote.INSTANCE
        if not r:
            return
        code = r.new_code()
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

    def _remove(self, h):
        c = remote.load_cfg()
        c["devices"] = [d for d in c["devices"] if d.get("hash") != h]
        remote.save_cfg(c)
        self.refresh()
