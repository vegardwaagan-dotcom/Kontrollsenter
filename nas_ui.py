"""Siden «NAS-disken»: bla i NAS-en som i en filbehandler, og sett opp tilgang utenfor hjemmet."""
import os
import sys
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

import i18n  # noqa: E402
import nasfiles as N  # noqa: E402

_t = i18n.tr
IS_WIN = sys.platform == "win32"


def _bg(fn, done):
    def work():
        try:
            r = fn()
        except Exception as e:  # noqa: BLE001
            r = e
        GLib.idle_add(lambda: (done(r), False)[1])
    threading.Thread(target=work, daemon=True).start()


def _card(title, sub=None):
    c = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    c.add_css_class("card")
    i = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    for side, v in (("top", 14), ("bottom", 14), ("start", 16), ("end", 16)):
        getattr(i, f"set_margin_{side}")(v)
    c.append(i)
    t = Gtk.Label(label=_t(title), xalign=0)
    t.add_css_class("heading")
    i.append(t)
    if sub:
        s = Gtk.Label(label=_t(sub), xalign=0, wrap=True)
        s.add_css_class("dim-label")
        s.add_css_class("caption")
        i.append(s)
    return c, i


def _open_local(path):
    if IS_WIN:
        os.startfile(path)  # noqa: S606
    else:
        Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(path).get_uri(), None)


def _downloads():
    d = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD) or os.path.expanduser("~/Downloads")
    os.makedirs(d, exist_ok=True)
    return d


class NasPage(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.share, self.path = N.default_share(), ""
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(outer, f"set_margin_{side}")(16)
        self.box = outer
        self.set_child(Adw.Clamp(maximum_size=1100, child=outer))
        self._browser()
        self._gate_card()
        self._remote_card()
        self.connect("map", lambda *_: self._first())
        self._loaded = False

    # ---------------------------------------------------------------- filbehandleren
    def _browser(self):
        c, i = _card("NAS-disken", "Bla i NAS-en, åpne og last ned filer, last opp (eller dra filer hit), lag mapper, "
                                   "gi nytt navn og slett.")
        top = Gtk.Box(spacing=8)
        self.where = Gtk.Label(xalign=0, hexpand=True)
        self.where.add_css_class("dim-label")
        top.append(self.where)
        self.share_dd = Gtk.DropDown.new_from_strings([self.share])
        self.share_dd.set_tooltip_text(_t("Delt mappe på NAS-en"))
        self.share_dd.connect("notify::selected", self._share_changed)
        top.append(self.share_dd)
        i.append(top)
        bar = Gtk.Box(spacing=6)
        self.up_btn = Gtk.Button(icon_name="go-up-symbolic", tooltip_text=_t("Opp én mappe"))
        self.up_btn.connect("clicked", lambda *_: self._go(self.path.rpartition("/")[0]))
        bar.append(self.up_btn)
        self.crumbs = Gtk.Box(spacing=2, hexpand=True)
        bar.append(self.crumbs)
        for icon, tip, fn in (("folder-new-symbolic", "Ny mappe", self._new_folder),
                              ("document-send-symbolic", "Last opp filer", self._pick_upload),
                              ("view-refresh-symbolic", "Oppdater", lambda *_: self._go(self.path))):
            b = Gtk.Button(icon_name=icon, tooltip_text=_t(tip))
            b.connect("clicked", fn)
            bar.append(b)
        i.append(bar)
        self.msg = Gtk.Label(xalign=0, wrap=True)
        self.msg.add_css_class("caption")
        i.append(self.msg)
        self.login_box = Gtk.Box(spacing=8, visible=False)
        self.user = Gtk.Entry(placeholder_text=_t("Brukernavn på NAS-en"), hexpand=True)
        self.pw = Gtk.PasswordEntry(placeholder_text=_t("Passord"), show_peek_icon=True, hexpand=True)
        lb = Gtk.Button(label=_t("Logg inn"))
        lb.add_css_class("suggested-action")
        lb.connect("clicked", self._login)
        self.pw.connect("activate", self._login)
        for w in (self.user, self.pw, lb):
            self.login_box.append(w)
        i.append(self.login_box)
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.list.add_css_class("boxed-list")
        self.list.connect("row-activated", lambda _l, r: getattr(r, "_act", lambda: None)())
        i.append(self.list)
        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop.connect("drop", self._dropped)
        c.add_controller(drop)
        self.box.append(c)

    def _first(self):
        if self._loaded:
            return
        self._loaded = True
        _bg(lambda: (N.where(), N.shares()), self._got_shares)

    def _got_shares(self, r):
        if isinstance(r, Exception):
            self.where.set_label(_t("NAS-en svarer ikke: ") + str(r))
            return
        where, shares = r
        self.where.set_label({"hjemme": _t("● Tilkoblet hjemme"), "tailscale": _t("● Tilkoblet utenfor hjemmet "
                                                                                    "(Tailscale)")}.get(
            where, _t("○ NAS-en er ikke tilgjengelig – se «Utenfor hjemmet» under")))
        names = [s["name"] for s in shares]
        d = N.default_share()                       # den åpne delingen først, så de private
        self._quiet = True
        self._shares = sorted(names, key=lambda n: (n != d, n.lower()))
        self.share_dd.set_model(Gtk.StringList.new(self._shares))
        if self.share in self._shares:
            self.share_dd.set_selected(self._shares.index(self.share))
        self._quiet = False
        if where:
            self._go("")

    def _share_changed(self, dd, _p):
        if getattr(self, "_quiet", False):
            return
        names = getattr(self, "_shares", [])
        i = dd.get_selected()
        if 0 <= i < len(names) and names[i] != self.share:
            self.share = names[i]
            self._go("")

    def _crumbs(self):
        while (c := self.crumbs.get_first_child()) is not None:
            self.crumbs.remove(c)
        parts = [p for p in self.path.split("/") if p]
        for n, label in enumerate([self.share] + parts):
            if n:
                self.crumbs.append(Gtk.Label(label="›"))
            b = Gtk.Button(label=label)
            b.add_css_class("flat")
            b.connect("clicked", lambda *_a, p="/".join(parts[:n]): self._go(p))
            self.crumbs.append(b)
        self.up_btn.set_sensitive(bool(parts))

    def _go(self, path):
        self.path = path
        self._crumbs()
        self.msg.set_label(_t("Henter …"))
        share = self.share
        _bg(lambda: N.list_dir(share, path), self._show)

    def _show(self, items):
        while (r := self.list.get_first_child()) is not None:
            self.list.remove(r)
        if isinstance(items, Exception):
            self.msg.set_label("✗ " + str(items))
            self.login_box.set_visible("logg inn" in str(items) or "passord" in str(items))
            return
        self.login_box.set_visible(False)
        self.msg.set_label(_t("{n} mapper og {f} filer").format(n=sum(x["dir"] for x in items),
                                                              f=sum(not x["dir"] for x in items)) if items else
                           _t("Mappa er tom"))
        for it in items:
            self.list.append(self._row(it))

    def _row(self, it):
        row = Gtk.ListBoxRow(activatable=True)
        b = Gtk.Box(spacing=10, margin_top=6, margin_bottom=6, margin_start=10, margin_end=6)
        b.append(Gtk.Image(icon_name="folder-symbolic" if it["dir"] else "text-x-generic-symbolic"))
        name = Gtk.Label(label=it["name"], xalign=0, hexpand=True, ellipsize=3)
        b.append(name)
        meta = Gtk.Label(label=("" if it["dir"] else N.human(it["size"]) + "  ·  ") +
                         (time.strftime("%d.%m.%Y %H:%M", time.localtime(it["t"])) if it["t"] else ""))
        meta.add_css_class("dim-label")
        meta.add_css_class("caption")
        b.append(meta)
        full = f"{self.path}/{it['name']}" if self.path else it["name"]
        if not it["dir"]:
            for icon, tip, fn in (("document-open-symbolic", "Åpne", lambda: self._open(full)),
                                  ("folder-download-symbolic", "Last ned", lambda: self._download(full))):
                bt = Gtk.Button(icon_name=icon, tooltip_text=_t(tip), valign=Gtk.Align.CENTER)
                bt.add_css_class("flat")
                bt.connect("clicked", lambda *_a, f=fn: f())
                b.append(bt)
        more = Gtk.MenuButton(icon_name="view-more-symbolic", valign=Gtk.Align.CENTER, tooltip_text=_t("Mer"))
        more.add_css_class("flat")
        pop = Gtk.Popover()
        pb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        for label, fn in (("Gi nytt navn", lambda: self._rename(full, it["name"])),
                          ("Slett", lambda: self._delete(full, it["name"], it["dir"]))):
            mb = Gtk.Button(label=_t(label))
            mb.add_css_class("flat")
            mb.connect("clicked", lambda *_a, f=fn: (pop.popdown(), f()))
            pb.append(mb)
        pop.set_child(pb)
        more.set_popover(pop)
        b.append(more)
        row.set_child(b)
        row._act = (lambda: self._go(full)) if it["dir"] else (lambda: self._open(full))
        return row

    # ---------------------------------------------------------------- handlinger
    def _do(self, fn, after=True, msg=None):
        self.msg.set_label(msg or _t("Arbeider …"))

        def done(r):
            self.msg.set_label(("✗ " + str(r)) if isinstance(r, Exception) else str(r))
            if after and not isinstance(r, Exception):
                share, path = self.share, self.path
                _bg(lambda: N.list_dir(share, path), lambda items: (self._show(items), self.msg.set_label(str(r))
                                                                     if not isinstance(items, Exception) else None))
        _bg(fn, done)

    def _open(self, full):
        share = self.share
        self._do(lambda: (_open_local(N.fetch(share, full)), _t("Åpnet ✓"))[1], after=False, msg=_t("Henter fila …"))

    def _download(self, full):
        share = self.share
        dest = os.path.join(_downloads(), full.rpartition("/")[2])
        self._do(lambda: (N.fetch(share, full, dest), _t("Lagret i Nedlastinger: ") + os.path.basename(dest))[1],
                 after=False, msg=_t("Laster ned …"))

    def _ask(self, heading, body, entry_text=None, ok="OK", danger=False, then=None):
        dlg = Adw.AlertDialog(heading=heading, body=body)
        e = None
        if entry_text is not None:
            e = Gtk.Entry(text=entry_text)
            dlg.set_extra_child(e)
        dlg.add_response("cancel", _t("Avbryt"))
        dlg.add_response("ok", ok)
        dlg.set_response_appearance("ok", Adw.ResponseAppearance.DESTRUCTIVE if danger else
                                    Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response("ok")
        dlg.connect("response", lambda _d, r: r == "ok" and then(e.get_text().strip() if e else None))
        if e is not None:
            e.connect("activate", lambda *_: (then(e.get_text().strip()), dlg.close()))
        dlg.present(self.get_root())

    def _new_folder(self, *_):
        share, path = self.share, self.path
        self._ask(_t("Ny mappe"), _t("Navnet på mappa:"), "", _t("Lag"),
                  then=lambda n: n and self._do(lambda: N.mkdir(share, path, n)))

    def _rename(self, full, old):
        share = self.share
        self._ask(_t("Gi nytt navn"), old, old, _t("Lagre"),
                  then=lambda n: n and n != old and self._do(lambda: N.rename(share, full, n)))

    def _delete(self, full, name, is_dir):
        share = self.share
        self._ask(_t("Slette «{n}»?").format(n=name),
                  _t("Mappa og alt i den slettes fra NAS-en. Det kan ikke angres.") if is_dir else
                  _t("Fila slettes fra NAS-en. Det kan ikke angres."), None, _t("Slett"), danger=True,
                  then=lambda _x: self._do(lambda: N.delete(share, full, is_dir)))

    def _upload_paths(self, paths):
        share, path = self.share, self.path
        paths = [p for p in paths if p and os.path.isfile(p)]
        if not paths:
            self.msg.set_label(_t("Bare filer kan lastes opp (ikke mapper)"))
            return

        def work():
            for n, p in enumerate(paths, 1):
                GLib.idle_add(self.msg.set_label, _t("Laster opp {n}/{t}: {f}").format(n=n, t=len(paths),
                                                                                    f=os.path.basename(p)))
                N.upload(p, share, path)
            return _t("{n} filer lastet opp ✓").format(n=len(paths)) if len(paths) > 1 else \
                _t("{f} er lastet opp ✓").format(f=os.path.basename(paths[0]))
        self._do(work)

    def _pick_upload(self, *_):
        dlg = Gtk.FileDialog(title=_t("Last opp til NAS-en"))
        dlg.open_multiple(self.get_root(), None, self._picked)

    def _picked(self, dlg, res):
        try:
            files = dlg.open_multiple_finish(res)
        except GLib.Error:
            return
        self._upload_paths([files.get_item(i).get_path() for i in range(files.get_n_items())])

    def _dropped(self, _t2, value, _x, _y):
        self._upload_paths([f.get_path() for f in value.get_files()])
        return True

    def _login(self, *_):
        share, u, p = self.share, self.user.get_text().strip(), self.pw.get_text()
        if not u or not p:
            self.msg.set_label(_t("Skriv brukernavn og passord"))
            return
        self.pw.set_text("")

        def done(r):
            self.msg.set_label(("✗ " + str(r)) if isinstance(r, Exception) else str(r))
            if not isinstance(r, Exception):
                self._go("")
        _bg(lambda: N.login_set(share, u, p), done)

    # ---------------------------------------------------------------- utenfor hjemmet
    def _remote_card(self):
        c, i = _card("Utenfor hjemmet", "Nå NAS-en når du er borte – gjennom Tailscale (kryptert, ingen porter åpnes "
                                        "mot internett). Mobilappen går via PC-en den er koblet til, så den virker borte "
                                        "så lenge PC-en hjemme er på.")
        self.ts_lbl = Gtk.Label(xalign=0, wrap=True)
        i.append(self.ts_lbl)
        self.ts_btns = Gtk.Box(spacing=8)
        i.append(self.ts_btns)
        self.box.append(c)
        self._ts_refresh()

    def _ts_refresh(self):
        import tailnas
        _bg(tailnas.status, self._ts_show)

    def _ts_show(self, st):
        import tailnas
        while (b := self.ts_btns.get_first_child()) is not None:
            self.ts_btns.remove(b)
        if isinstance(st, Exception) or not st.get("installed"):
            self.ts_lbl.set_label(_t("Tailscale er ikke installert. Installer det under Programmer (gratis), logg inn "
                                     "med samme konto på PC-ene og mobilen, og kom tilbake hit."))
            return
        if not st.get("running"):
            self.ts_lbl.set_label(_t("Tailscale er installert, men ikke på. Slå det på og logg inn."))
            return
        lines = []
        if st.get("approved"):
            lines.append(_t("✓ Denne PC-en deler hjemmenettet ({s}) – NAS-en kan nås utenfra.").format(s=st["subnet"]))
        elif st.get("here_shares"):
            lines.append(_t("⏳ Denne PC-en tilbyr hjemmenettet, men ruten er ikke godkjent ennå. Trykk «Godkjenn i "
                            "Tailscale», finn {pc} og slå på ruten {s} under «Edit route settings».").format(
                pc=st.get("me") or "PC-en", s=st["subnet"]))
        elif st.get("router"):
            lines.append(_t("✓ {pc} deler hjemmenettet ({s}).").format(pc=st["router"], s=st["subnet"]) +
                         ("" if st.get("router_online", True) else _t(" Den er av nå – NAS-en kan ikke nås utenfra.")))
        else:
            lines.append(_t("Ingen PC deler hjemmenettet ennå. Gjør det fra en PC hjemme som står på mest (f.eks. "
                            "denne): trykk «Del hjemmenettet». Det spør om passordet én gang."))
        if not IS_WIN:
            lines.append(_t("✓ Denne PC-en bruker hjemmenettet når den er borte.") if st.get("accept") else
                         _t("Denne PC-en bruker ikke delte nett ennå – slå det på hvis du tar den med deg (laptop)."))
        self.ts_lbl.set_label("\n".join(lines))

        def btn(label, fn, css=None):
            b = Gtk.Button(label=_t(label))
            if css:
                b.add_css_class(css)
            b.connect("clicked", lambda *_: fn())
            self.ts_btns.append(b)
        if not st.get("here_shares"):
            btn("Del hjemmenettet herfra", lambda: self._ts_do(lambda: tailnas.share_home(True), open_admin=True),
                "suggested-action")
        else:
            btn("Slutt å dele", lambda: self._ts_do(lambda: tailnas.share_home(False)))
        if st.get("here_shares") and not st.get("approved"):
            btn("Godkjenn i Tailscale", lambda: Gtk.UriLauncher(uri=tailnas.ADMIN_URL).launch(self.get_root(), None,
                                                                                               None, None))
        if not IS_WIN and not st.get("accept"):
            btn("Bruk hjemmenettet når jeg er borte", lambda: self._ts_do(lambda: tailnas.use_home(True)))

    def _ts_do(self, fn, open_admin=False):
        import tailnas
        self.ts_lbl.set_label(_t("Arbeider … (PC-en kan spørre om passordet)"))

        def done(r):
            if isinstance(r, Exception):
                self.ts_lbl.set_label("✗ " + str(r))
            elif open_admin:
                Gtk.UriLauncher(uri=tailnas.ADMIN_URL).launch(self.get_root(), None, None, None)
            GLib.timeout_add_seconds(2, lambda: (self._ts_refresh(), False)[1])
        _bg(fn, done)

    # ---------------------------------------------------------------- hjemmeporten (Raspberry Pi)
    def _gate_card(self):
        import hjemmeport as HP
        c, i = _card("Hjemmeport – uten at noen PC står på",
                     "En Raspberry Pi hjemme som alltid står på, gjør NAS-en tilgjengelig utenfor hjemmet: laptopen og "
                     "mobilen når den gjennom Tailscale, og mobilappen kan bla i NAS-en selv om alle PC-ene er av.")
        self.gate_lbl = Gtk.Label(xalign=0, wrap=True, label=_t("Sjekker …"))
        i.append(self.gate_lbl)
        self.gate_btns = Gtk.Box(spacing=8)
        i.append(self.gate_btns)
        self.box.append(c)
        if not HP.ssh_available():
            self.gate_lbl.set_label(_t("Trenger SSH (følger med Linux og Windows 10/11)."))
            return
        _bg(HP.status, self._gate_show)

    def _gate_show(self, st):
        import hjemmeport as HP
        while (b := self.gate_btns.get_first_child()) is not None:
            self.gate_btns.remove(b)

        def btn(label, fn, css=None):
            b = Gtk.Button(label=_t(label))
            if css:
                b.add_css_class(css)
            b.connect("clicked", lambda *_: fn())
            self.gate_btns.append(b)
        if isinstance(st, Exception) or not st.get("setup"):
            self.gate_lbl.set_label(_t("Ikke satt opp. Gjør Pi-en klar med Raspberry Pi Imager (Raspberry Pi OS Lite, "
                                       "vertsnavn «hjemmeport», SSH på), koble den til ruteren med kabel, og trykk "
                                       "«Sett opp»."))
            btn("Sett opp Raspberry Pi", self._gate_setup, "suggested-action")
            return
        lines = [_t("✓ Satt opp på {ip}").format(ip=st.get("ip"))]
        lines.append(_t("✓ NAS-tjenesten svarer") if st.get("online") else _t("✗ NAS-tjenesten svarer ikke – står Pi-en på?"))
        if st.get("ts_ip"):
            lines.append(_t("✓ I Tailscale ({ip})").format(ip=st["ts_ip"]))
            lines.append(_t("✓ Hjemmenettet deles – NAS-en kan nås utenfra") if st.get("route_ok") else
                         _t("⏳ Ruten er ikke godkjent ennå: trykk «Godkjenn ruten», finn «hjemmeport» og slå på "
                            "192.168.1.0/24 under «Edit route settings»."))
        else:
            lines.append(_t("⏳ Ikke logget inn i Tailscale ennå – trykk «Logg inn i Tailscale»."))
        self.gate_lbl.set_label("\n".join(lines))
        if not st.get("ts_ip"):
            btn("Logg inn i Tailscale", self._gate_login, "suggested-action")
        elif not st.get("route_ok"):
            import tailnas
            btn("Godkjenn ruten", lambda: Gtk.UriLauncher(uri=tailnas.ADMIN_URL).launch(self.get_root(), None, None,
                                                                                         None), "suggested-action")
        btn("Oppdater", lambda: _bg(HP.status, self._gate_show))
        btn("Sett opp på nytt", self._gate_setup)

    def _gate_login(self):
        import hjemmeport as HP
        self.gate_lbl.set_label(_t("Henter innloggingslenken fra Pi-en …"))

        def done(url):
            if isinstance(url, Exception) or not url:
                self.gate_lbl.set_label(_t("Pi-en er allerede logget inn – eller svarer ikke. Trykk «Oppdater»."))
                return
            Gtk.UriLauncher(uri=url).launch(self.get_root(), None, None, None)
            self.gate_lbl.set_label(_t("Logg inn med samme Tailscale-konto som på PC-ene i nettleseren som åpnet seg, "
                                       "og trykk «Oppdater» etterpå."))
        _bg(HP.auth_url, done)

    def _gate_setup(self):
        import hjemmeport as HP
        dlg = Adw.AlertDialog(heading=_t("Sett opp hjemmeporten"),
                              body=_t("Skriv adressen, brukernavnet og passordet du valgte i Raspberry Pi Imager. "
                                      "Passordet brukes bare nå – etterpå logger Kontrollsenter inn med egen nøkkel."))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        ip = Gtk.Entry(placeholder_text=_t("Adresse (f.eks. 192.168.1.50 eller hjemmeport.local)"))
        user = Gtk.Entry(placeholder_text=_t("Brukernavn på Pi-en"))
        pw = Gtk.PasswordEntry(placeholder_text=_t("Passord på Pi-en"), show_peek_icon=True)
        found = Gtk.Label(xalign=0, wrap=True, label=_t("Leter etter Raspberry Pi på hjemmenettet …"))
        found.add_css_class("caption")
        for w in (found, ip, user, pw):
            box.append(w)
        dlg.set_extra_child(box)
        dlg.add_response("cancel", _t("Avbryt"))
        dlg.add_response("ok", _t("Sett opp"))
        dlg.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)

        def got(r):
            if isinstance(r, Exception) or not r:
                found.set_label(_t("Fant ingen Raspberry Pi automatisk – skriv adressen (se ruteren), eller prøv "
                                   "«hjemmeport.local»."))
                return
            found.set_label(_t("Fant: ") + ", ".join(f"{a} ({n})" for a, n in r))
            if not ip.get_text():
                ip.set_text(r[0][0])
        _bg(HP.find, got)

        def resp(_d, r):
            if r != "ok":
                return
            a, u, p = ip.get_text().strip(), user.get_text().strip(), pw.get_text()
            if not (a and u and p):
                self.gate_lbl.set_label(_t("Fyll inn adresse, brukernavn og passord"))
                return
            while (b := self.gate_btns.get_first_child()) is not None:
                self.gate_btns.remove(b)

            def say(t):
                GLib.idle_add(self.gate_lbl.set_label, t)

            def done(res):
                if isinstance(res, Exception):
                    self.gate_lbl.set_label("✗ " + str(res))
                    self._gate_show({"setup": bool(HP.cfg().get("key")), **HP.cfg()})
                    return
                if res.get("auth_url"):
                    Gtk.UriLauncher(uri=res["auth_url"]).launch(self.get_root(), None, None, None)
                self._gate_show(res)
                if res.get("auth_url"):
                    self.gate_lbl.set_label(self.gate_lbl.get_label() + "\n" +
                                            _t("Logg inn i Tailscale i nettleseren som åpnet seg, og trykk «Oppdater»."))
            _bg(lambda: HP.setup(a, u, p, say), done)
        dlg.connect("response", resp)
        dlg.present(self.get_root())

