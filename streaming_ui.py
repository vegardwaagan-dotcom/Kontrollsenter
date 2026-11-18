"""Fanen «Strømming»: spill fra PC-en på telefonen (Sunshine + Moonlight), innstillinger, Moonlight på PC-en
og RustDesk for fjernhjelp."""
import threading
import webbrowser

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

import i18n  # noqa: E402
import streaming as S  # noqa: E402
import theme  # noqa: E402


def _t(x):
    return i18n.tr(x)


def card(title, desc=None):
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    outer.add_css_class("card")
    inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    for side, v in (("top", 18), ("bottom", 18), ("start", 20), ("end", 20)):
        getattr(inner, f"set_margin_{side}")(v)
    outer.append(inner)
    h = Gtk.Label(label=_t(title), xalign=0)
    h.add_css_class("title-4")
    inner.append(h)
    if desc:
        d = Gtk.Label(label=_t(desc), xalign=0, wrap=True)
        d.add_css_class("ks-desc")
        inner.append(d)
    return outer, inner


def row(title, sub, widget):
    r = Gtk.Box(spacing=16)
    col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True, valign=Gtk.Align.CENTER)
    t = Gtk.Label(label=_t(title), xalign=0, wrap=True)
    col.append(t)
    if sub:
        s = Gtk.Label(label=_t(sub), xalign=0, wrap=True)
        s.add_css_class("ks-sub")
        col.append(s)
    r.append(col)
    widget.set_valign(Gtk.Align.CENTER)
    r.append(widget)
    return r


def steps(items):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    for i, txt in enumerate(items, 1):
        r = Gtk.Box(spacing=12)
        n = Gtk.Label(label=str(i), valign=Gtk.Align.START)
        n.add_css_class("ks-step")
        r.append(n)
        lab = Gtk.Label(label=_t(txt), xalign=0, wrap=True, hexpand=True)
        r.append(lab)
        box.append(r)
    return box


class StreamingPage(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(18)
        self.set_child(Adw.Clamp(maximum_size=theme.PAGE_WIDTH, child=box))
        self.msg = Gtk.Label(xalign=0, wrap=True)
        self.msg.add_css_class("ks-sub")

        # ---- spill på telefonen ----
        c, i = card("Spill på telefonen",
                    "Se og spill det som skjer på PC-en, på telefonen eller nettbrettet – også spillet du spiller nå. "
                    "Sunshine sender bildet fra PC-en, og Moonlight-appen viser det på telefonen med lav forsinkelse.")
        box.append(c)
        import apps_ui
        i.append(apps_ui.need("stream", on_done=lambda: self.refresh() if hasattr(self, "refresh") else None))
        status = Gtk.Box(spacing=10)
        self.dot = Gtk.Label(label="●")
        status.append(self.dot)
        self.st_lbl = Gtk.Label(xalign=0, hexpand=True)
        self.st_lbl.add_css_class("heading")
        status.append(self.st_lbl)
        for label, fn in (("Start", S.sunshine_start), ("Start på nytt", S.sunshine_restart), ("Stopp", S.sunshine_stop)):
            b = Gtk.Button(label=_t(label))
            b.connect("clicked", lambda _b, f=fn, lab=label: self._do(f, _t(lab) + " ✓"))
            status.append(b)
        i.append(status)
        self.auto_sw = Gtk.Switch()
        self.auto_sw.connect("notify::active", lambda s, _p: self._busy or self._do(
            lambda: S.sunshine_autostart(s.get_active())))
        i.append(row("Start Sunshine med PC-en", "Klar til strømming med en gang du logger inn.", self.auto_sw))
        self.keep_sw = Gtk.Switch()
        self.keep_sw.connect("notify::active", lambda s, _p: self._busy or self._keep(s.get_active()))
        i.append(row("Hold Sunshine i gang", "Starter Sunshine igjen av seg selv hvis den stopper – den kan krasje "
                     "når en strøm avsluttes.", self.keep_sw))
        i.append(Gtk.Separator())
        how = Gtk.Label(label=_t("Slik kobler du til telefonen første gang"), xalign=0)
        how.add_css_class("heading")
        i.append(how)
        i.append(steps(["Installer Moonlight på telefonen (Google Play) – eller trykk «Spill på telefonen» i "
                        "Kontrollsenter-appen.",
                        "Åpne Moonlight. PC-en dukker opp av seg selv på hjemmenettet. Utenfor hjemmet: legg til "
                        "Tailscale-adressen under.",
                        "Trykk på PC-en i Moonlight. Den viser en kode med 4 sifre – skriv den inn her og trykk «Par».",
                        "Velg «Desktop» for å se hele skjermen og spillet som kjører."]))
        self.addr = Gtk.Label(xalign=0, wrap=True, selectable=True)
        self.addr.add_css_class("ks-mono")
        i.append(self.addr)
        prow = Gtk.Box(spacing=10)
        self.pin = Gtk.Entry(placeholder_text=_t("PIN fra Moonlight"), max_length=4, width_chars=10,
                             input_purpose=Gtk.InputPurpose.DIGITS)
        self.pin.connect("activate", lambda *_: self._pair())
        prow.append(self.pin)
        pb = Gtk.Button(label=_t("Par"))
        pb.add_css_class("suggested-action")
        pb.connect("clicked", lambda *_: self._pair())
        prow.append(pb)
        web = Gtk.Button(label=_t("Åpne Sunshine-nettsiden"))
        web.connect("clicked", lambda *_: webbrowser.open(S.SUN_API))
        prow.append(web)
        i.append(prow)
        self.devs = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        i.append(self.devs)
        exp = Gtk.Expander(label=_t("Innlogging til Sunshine (trengs for paring herfra og fra appen)"))
        lb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        lb.set_margin_top(8)
        lb.append(Gtk.Label(label=_t("Samme brukernavn og passord som på Sunshine-nettsiden. Lagres bare på denne "
                                     "PC-en, lesbart kun for deg."), xalign=0, wrap=True, css_classes=["ks-sub"]))
        self.user = Gtk.Entry(placeholder_text=_t("Brukernavn"), text=S.cfg()["user"])
        self.pw = Gtk.PasswordEntry(placeholder_text=_t("Passord"), show_peek_icon=True)
        lb.append(self.user)
        lb.append(self.pw)
        sb = Gtk.Button(label=_t("Lagre og test"), halign=Gtk.Align.START)
        sb.connect("clicked", lambda *_: self._do(lambda: S.set_login(self.user.get_text(), self.pw.get_text()),
                                                  _t("Innloggingen virker ✓")))
        lb.append(sb)
        exp.set_child(lb)
        i.append(exp)
        i.append(self.msg)

        # ---- innstillinger ----
        c, i = card("Innstillinger for strømmingen",
                    "Gjelder bildet PC-en sender. Oppløsning og bilder per sekund velger du i Moonlight på telefonen.")
        box.append(c)
        conf = S.read_conf()
        self.widgets = {}
        for key, name, desc, choices in S.SETTINGS:
            if choices:
                w = Gtk.DropDown.new_from_strings([_t(n) for _v, n in choices])
                vals = [v for v, _n in choices]
                cur = conf.get(key, "")
                w.set_selected(vals.index(cur) if cur in vals else 0)
                self.widgets[key] = (w, vals)
            else:
                w = Gtk.Entry(text=conf.get(key, ""), width_chars=14,
                              placeholder_text=__import__("socket").gethostname() if key == "sunshine_name" else "")
                self.widgets[key] = (w, None)
            i.append(row(name, desc, w))
        save = Gtk.Button(label=_t("Lagre innstillingene"), halign=Gtk.Align.START)
        save.add_css_class("suggested-action")
        save.connect("clicked", lambda *_: self._save())
        i.append(save)

        # ---- Moonlight på PC-en ----
        c, i = card("Moonlight på denne PC-en",
                    "Spill fra en annen PC i huset på denne – for eksempel et tungt spill som kjører på den kraftige "
                    "PC-en, mens du sitter ved en annen. Den andre PC-en må ha Sunshine.")
        box.append(c)
        mrow = Gtk.Box(spacing=10)
        self.moon_btn = Gtk.Button(label=_t("Åpne Moonlight"))
        self.moon_btn.connect("clicked", lambda *_: self._do(S.moonlight_open))
        mrow.append(self.moon_btn)
        self.moon_inst = Gtk.Button(label=_t("Installer Moonlight"))
        self.moon_inst.connect("clicked", lambda *_: self._do(lambda: S.install("moonlight"),
                                                              _t("Moonlight er installert ✓")))
        mrow.append(self.moon_inst)
        i.append(mrow)

        # ---- RustDesk ----
        c, i = card("RustDesk – fjernhjelp",
                    "Styr PC-en fra en annen PC eller telefon – eller la noen hjelpe deg. Den andre trenger ID-en "
                    "under og passordet som vises i RustDesk. Til spill er Moonlight raskere; RustDesk er best til "
                    "vanlig bruk og hjelp.")
        box.append(c)
        i.append(apps_ui.need("remote", on_done=lambda: self.refresh() if hasattr(self, "refresh") else None))
        rrow = Gtk.Box(spacing=12)
        idcol = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        idcol.append(Gtk.Label(label=_t("RustDesk-ID"), xalign=0, css_classes=["ks-sub"]))
        self.rid = Gtk.Label(label="…", xalign=0, selectable=True)
        self.rid.add_css_class("title-2")
        self.rid.add_css_class("numeric")
        idcol.append(self.rid)
        rrow.append(idcol)
        cp = Gtk.Button(icon_name="edit-copy-symbolic", tooltip_text=_t("Kopier ID"), valign=Gtk.Align.CENTER)
        cp.connect("clicked", lambda *_: Gdk.Display.get_default().get_clipboard().set(self.rid.get_label()))
        rrow.append(cp)
        self.rust_btn = Gtk.Button(label=_t("Åpne RustDesk"), valign=Gtk.Align.CENTER)
        self.rust_btn.connect("clicked", lambda *_: self._do(S.rustdesk_open))
        rrow.append(self.rust_btn)
        self.rust_inst = Gtk.Button(label=_t("Installer RustDesk"), valign=Gtk.Align.CENTER)
        self.rust_inst.connect("clicked", lambda *_: self._do(lambda: S.install("rustdesk"),
                                                              _t("RustDesk er installert ✓")))
        rrow.append(self.rust_inst)
        i.append(rrow)

        self._busy = False
        self.refresh()
        GLib.timeout_add_seconds(10, lambda: self.get_mapped() and self.refresh() or True)

    # ------------------------------------------------------------------
    def refresh(self):
        def work():
            st = S.sunshine_state()
            rd = S.rustdesk_state()
            ml = S.moonlight_installed()
            cl = S.clients() if st["running"] and st["has_login"] else None
            GLib.idle_add(self._show, st, rd, ml, cl)
        threading.Thread(target=work, daemon=True).start()
        return False

    def _show(self, st, rd, ml, cl):
        self._busy = True
        if not st["installed"]:
            self.st_lbl.set_label(_t("Sunshine er ikke installert"))
        else:
            self.st_lbl.set_label(_t("Sunshine kjører – klar til strømming") if st["running"]
                                  else _t("Sunshine er av"))
        for c in ("ks-ok", "ks-off"):
            self.dot.remove_css_class(c)
        self.dot.add_css_class("ks-ok" if st["running"] else "ks-off")
        self.auto_sw.set_active(st["autostart"])
        self.keep_sw.set_active(st["keep_running"])
        self.addr.set_label("\n".join(f"{a['kind']}: {a['ip']}" for a in st["addresses"]))
        while (ch := self.devs.get_first_child()) is not None:
            self.devs.remove(ch)
        if cl:
            self.devs.append(Gtk.Label(label=_t("Parede enheter"), xalign=0, css_classes=["heading"]))
            for d in cl:
                r = Gtk.Box(spacing=8)
                r.append(Gtk.Label(label="📱 " + d["name"], xalign=0, hexpand=True))
                b = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text=_t("Fjern"))
                b.add_css_class("flat")
                b.connect("clicked", lambda _b, u=d["id"]: self._do(lambda: S.unpair(u), _t("Fjernet ✓")))
                r.append(b)
                self.devs.append(r)
        self.moon_btn.set_visible(ml)
        self.moon_inst.set_visible(not ml)
        self.rid.set_label(rd["id"] or ("–" if rd["installed"] else _t("ikke installert")))
        self.rust_btn.set_visible(rd["installed"])
        self.rust_inst.set_visible(not rd["installed"])
        self._busy = False
        return False

    def _do(self, fn, ok=None):
        self.msg.set_label(_t("Arbeider …"))

        def work():
            try:
                r = fn()
                txt = ok or (_t("Ferdig ✓") if r is not False else _t("Det gikk ikke"))
            except Exception as e:  # noqa: BLE001
                txt = str(e)
            GLib.idle_add(lambda: (self.msg.set_label(txt), False)[1])
            GLib.timeout_add_seconds(2, self.refresh)
        threading.Thread(target=work, daemon=True).start()
        return False

    def _keep(self, on):
        c = S.cfg()
        c["keep_running"] = on
        S.save_cfg(c)

    def _pair(self):
        pin = self.pin.get_text()
        self.pin.set_text("")
        self._do(lambda: S.pair(pin, "Telefon"), _t("Paret ✓ – Moonlight er klar"))

    def _save(self):
        ch = {}
        for key, (w, vals) in self.widgets.items():
            ch[key] = vals[w.get_selected()] if vals else w.get_text().strip()
        self._do(lambda: S.write_conf(ch), _t("Lagret ✓ – Sunshine starter på nytt"))
