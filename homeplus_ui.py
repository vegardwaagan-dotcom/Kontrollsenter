"""Hjem+ i vinduet: trygghet og nett (Vedlikehold), gjeste-Wi-Fi og rommet (Smart Hjem), oppsett mellom PC-er."""
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

import homeplus as HP  # noqa: E402
import i18n  # noqa: E402


def _dim(t):
    lab = Gtk.Label(label=i18n.tr(t), xalign=0, wrap=True)
    lab.add_css_class("dim-label")
    lab.add_css_class("caption")
    return lab


def _h(t):
    lab = Gtk.Label(label=i18n.tr(t), xalign=0, margin_top=8)
    lab.add_css_class("heading")
    return lab


def _bg(fn, done):
    def work():
        try:
            r = fn()
        except Exception as e:  # noqa: BLE001
            r = e
        GLib.idle_add(lambda: (done(r), False)[1])
    threading.Thread(target=work, daemon=True).start()


def _btn(label, cb, primary=False):
    b = Gtk.Button(label=i18n.tr(label), valign=Gtk.Align.CENTER)
    b.add_css_class("pill")
    if primary:
        b.add_css_class("suggested-action")
    b.connect("clicked", cb)
    return b


def _switch(box, title, sub, active, cb):
    r = Gtk.Box(spacing=12)
    col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
    col.append(Gtk.Label(label=i18n.tr(title), xalign=0))
    if sub:
        col.append(_dim(sub))
    r.append(col)
    sw = Gtk.Switch(active=active, valign=Gtk.Align.CENTER)
    sw.connect("notify::active", lambda w, _p: cb(w.get_active()))
    r.append(sw)
    box.append(r)
    return sw


def safety_box(win_getter):
    """Vedlikehold → Trygghet og nett."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    msg = _dim("")
    # 46 – hjelp
    box.append(_h("🆘 Trenger du hjelp?"))
    hr = Gtk.Box(spacing=8)
    ht = Gtk.Entry(placeholder_text=i18n.tr("Hva gjelder det? (valgfritt)"), hexpand=True)
    hr.append(ht)
    hr.append(_btn("Be om hjelp", lambda b: (b.set_sensitive(False), _bg(lambda: HP.ask_help(ht.get_text().strip()),
                                                                        lambda r: msg.set_label(str(r)))), True))
    box.append(hr)
    box.append(_dim("Sender beskjed til de voksne (familie-chat og mobilen) med RustDesk-ID, så de kan hjelpe deg."))
    # 56 – passordsjekk
    box.append(_h("🔑 Har passordet lekket?"))
    pr = Gtk.Box(spacing=8)
    pw = Gtk.PasswordEntry(show_peek_icon=True, hexpand=True)
    pr.append(pw)
    res = _dim("")

    def check(_b):
        p = pw.get_text()
        pw.set_text("")
        res.set_label(i18n.tr("Sjekker …"))

        def done(n):
            if isinstance(n, Exception):
                res.set_label(f"Kunne ikke sjekke: {n}")
            elif n:
                res.set_label(f"⚠️ Dette passordet finnes {n:,} ganger i kjente lekkasjer – bytt det der du bruker det."
                              .replace(",", " "))
            else:
                res.set_label("✅ Ikke funnet i kjente lekkasjer.")
        _bg(lambda: HP.pwned(p), done)
    pr.append(_btn("Sjekk", check))
    box.append(pr)
    box.append(res)
    box.append(_dim("Passordet forlater aldri PC-en: bare de 5 første tegnene av en hash sendes til «Have I Been "
                    "Pwned», og svaret sjekkes her."))
    # 58 – kamera og mikrofon
    box.append(_h("📷 Kamera og mikrofon"))
    cm = _dim("…")
    box.append(cm)
    cr = Gtk.Box(spacing=8)

    def refresh_cm(*_):
        _bg(HP.cam_mic, lambda r: cm.set_label(
            "Kunne ikke sjekke" if isinstance(r, Exception) else
            ("🎙️ Mikrofon: " + (", ".join(r["mic"]) or "ingen") + "   ·   📷 Kamera: " + (", ".join(r["cam"]) or "ingen"))))
    cr.append(_btn("Sjekk nå", refresh_cm))
    cr.append(_btn("Demp mikrofonen", lambda _b: _bg(lambda: HP.mic_mute(True), lambda r: msg.set_label(
        r[1] if isinstance(r, tuple) else str(r)))))
    box.append(cr)
    refresh_cm()
    # 57 / 19 / 63
    box.append(_h("🛡️ Nett"))
    try:
        import familysafe
        cur = familysafe.dns_state()
    except Exception:  # noqa: BLE001
        cur = None

    def scam(on):
        import familysafe
        _bg(lambda: familysafe.set_dns("quad9" if on else None), lambda r: msg.set_label(
            ("Svindel-skjold på (Quad9)" if on else "Vanlig DNS fra ruteren") if not isinstance(r, Exception)
            else f"✗ {r}"))
    _switch(box, "Svindel-skjold", "DNS som blokkerer kjente svindel- og skadevaresider (Quad9). For barnas PC-er: "
                                   "bruk familiefilteret i Familie i stedet.", cur == "quad9", scam)
    c = HP.cfg()
    _switch(box, "Nettverksvakt", "Varsel når en ukjent enhet kobler seg til hjemmenettet.", c["lan_notify"],
            lambda on: HP.set_(lan_notify=on))
    _switch(box, "Nattlig fartstest", "Måler nedlasting, opplasting og ping hver natt (i den billigste "
                                      "strømtimen) – så du ser om leverandøren leverer.", c["speedtest"],
            lambda on: HP.set_(speedtest=on))
    sp = _dim(HP.speed_report())
    box.append(sp)
    box.append(_btn("Test farten nå", lambda b: (b.set_sensitive(False), sp.set_label(i18n.tr("Måler … (ca. 20 s)")),
                                                 _bg(HP.speedtest, lambda r: (b.set_sensitive(True), sp.set_label(
                                                     f"✗ {r}" if isinstance(r, Exception) else
                                                     f"⬇ {r['down']} Mbit/s · ⬆ {r['up']} Mbit/s · {r['ping']} ms"))))))
    box.append(msg)
    return box


class QrView(Gtk.DrawingArea):
    def __init__(self, text, size=260):
        super().__init__(content_width=size, content_height=size, halign=Gtk.Align.CENTER)
        import qr
        self.m = qr.matrix(text)
        self.set_draw_func(lambda _a, cr, w, h: __import__("qr").draw(cr, self.m, min(w, h)))


def guest_box():
    """Smart Hjem → Gjeste-Wi-Fi og rommet."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    c = HP.cfg()
    box.append(_h("📶 Gjeste-Wi-Fi"))
    r = Gtk.Box(spacing=8)
    ss = Gtk.Entry(text=c["guest_ssid"], placeholder_text=i18n.tr("Navn på nettet"), hexpand=True)
    pw = Gtk.PasswordEntry(text=c["guest_pass"], show_peek_icon=True, hexpand=True)
    r.append(ss)
    r.append(pw)

    def show(_b):
        HP.set_(guest_ssid=ss.get_text().strip(), guest_pass=pw.get_text())
        if not ss.get_text().strip():
            return
        import qr
        dlg = Adw.Dialog(title=i18n.tr("Skann for å koble til"), content_width=420, content_height=480)
        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, valign=Gtk.Align.CENTER, margin_top=20,
                    margin_bottom=20)
        v.append(QrView(qr.wifi_text(ss.get_text().strip(), pw.get_text()), 300))
        t = Gtk.Label(label=f"📶 {ss.get_text().strip()}")
        t.add_css_class("title-3")
        v.append(t)
        v.append(_dim("Åpne kameraet på mobilen og pek på koden."))
        dlg.set_child(v)
        dlg.present(box.get_root())
    r.append(_btn("Vis QR-kode", show, True))
    box.append(r)
    box.append(_dim("Navn og passord lagres bare på denne PC-en."))
    box.append(_h("💡 Rommet følger PC-en"))
    _switch(box, "Slukk lyset når PC-en går i dvale", "Hue-lysene slukkes når PC-en sover og tennes når den våkner "
                                                      "(Linux).", c["room_follow"], lambda on: HP.set_(room_follow=on))
    return box


def send_setup_dialog(parent, p):
    """14: velg hva som skal sendes til PC-en p."""
    dlg = Adw.Dialog(title=i18n.tr("Send oppsettet mitt til ") + p.get("name", "?"), content_width=420)
    v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=16, margin_bottom=16, margin_start=16,
                margin_end=16)
    checks = {}
    for key, name in (("vifter", "Vifter og viftekurve"), ("rgb", "RGB-lys"), ("overlay", "Overlay i spill"),
                      ("lyd", "Lyd og lydprofiler"), ("utseende", "Tema og utseende"), ("oversikt", "Oversikt (fliser)"),
                      ("scener", "Scener"), ("varsler", "Varsler")):
        cb = Gtk.CheckButton(label=i18n.tr(name), active=key in ("vifter", "rgb", "utseende"))
        checks[key] = cb
        v.append(cb)
    msg = _dim("Den andre PC-en tar en kopi av sine innstillinger først (tidsmaskinen), og starter Kontrollsenter på "
               "nytt.")
    v.append(msg)

    def go(b):
        parts = [k for k, cb in checks.items() if cb.get_active()]
        b.set_sensitive(False)
        _bg(lambda: HP.send_setup(p, parts), lambda r: msg.set_label(("✗ " if isinstance(r, Exception) else "✓ ") +
                                                                     str(r)))
    v.append(_btn("Send", go, True))
    dlg.set_child(v)
    dlg.present(parent)


def new_pc_dialog(parent):
    """13: hent oppsett fra en annen PC (sikkerhetskopi på NAS-en) og installer de samme programmene."""
    dlg = Adw.Dialog(title=i18n.tr("Ny PC? Hent oppsett"), content_width=460, content_height=420)
    v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=16, margin_bottom=16, margin_start=16,
                margin_end=16)
    v.append(_dim("Velg en sikkerhetskopi av innstillingene fra en annen PC. Programmene den bruker installeres også."))
    lst = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    v.append(lst)
    msg = _dim("Henter liste …")
    v.append(msg)

    def show(rows):
        if isinstance(rows, Exception) or not rows:
            msg.set_label("Fant ingen sikkerhetskopier på NAS-en. Ta en på den andre PC-en (Innstillinger → Oppdatering).")
            return
        msg.set_label("")
        for name in rows[:12]:
            r = Gtk.Box(spacing=8)
            r.append(Gtk.Label(label=str(name), xalign=0, hexpand=True, wrap=True))

            def use(b, n=name):
                b.set_sensitive(False)
                msg.set_label(i18n.tr("Henter og installerer … (kan ta noen minutter)"))
                _bg(lambda: HP.setup_from(n), lambda res: msg.set_label(("✗ " if isinstance(res, Exception) else "✓ ")
                                                                        + str(res) + " – start Kontrollsenter på nytt"))
            r.append(_btn("Bruk", use, True))
            lst.append(r)

    def load():
        import features
        return features.list_backups()
    _bg(load, show)
    sc = Gtk.ScrolledWindow(child=v, vexpand=True)
    dlg.set_child(sc)
    dlg.present(parent)
