"""VR-siden (under Spill): Meta Quest 3 gjennom Steam og SteamVR – trådløst eller med kabel."""
import sys
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

import i18n  # noqa: E402
import theme  # noqa: E402
import vr  # noqa: E402

_t = i18n.tr
IS_WIN = sys.platform == "win32"


def card(title, sub=None):
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    outer.add_css_class("card")
    inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    for side, v in (("top", 16), ("bottom", 16), ("start", 18), ("end", 18)):
        getattr(inner, f"set_margin_{side}")(v)
    outer.append(inner)
    t = Gtk.Label(label=_t(title), xalign=0)
    t.add_css_class("heading")
    inner.append(t)
    if sub:
        s = Gtk.Label(label=_t(sub), xalign=0, wrap=True)
        s.add_css_class("dim-label")
        s.add_css_class("caption")
        inner.append(s)
    return outer, inner


def _bg(work, done):
    def run():
        try:
            r = work()
        except Exception as e:  # noqa: BLE001
            r = e
        GLib.idle_add(lambda: (done(r), False)[1])
    threading.Thread(target=run, daemon=True).start()


HOW = {
    ("wivrn", "wireless"): "WiVRn strømmer VR-spill trådløst rett med OpenXR – ofte lavere forsinkelse enn ALVR. Steam-spill "
                           "startes fra WiVRn-dashbordet eller Steam. PC-en bør stå på kabel til ruteren, og Questen på 5/6 GHz.",
    ("wivrn", "wired"): "WiVRn over USB-kabel: bildet går gjennom kabelen (adb) – stabilt og uten Wi-Fi. Bruk en USB 3-kabel.",
    ("linux", "wireless"): "ALVR strømmer SteamVR trådløst til Questen. PC-en bør stå på kabel til ruteren, og Questen "
                           "på 5 GHz- eller 6 GHz-Wi-Fi. Første gang trengs en USB-kabel for å legge ALVR inn i brillene.",
    ("linux", "wired"): "ALVR over USB-kabel: bildet går gjennom kabelen (via adb) – stabilt og uten Wi-Fi. Bruk en "
                        "USB 3-kabel (USB-C). Første gang: slå på utviklermodus i Meta Horizon-appen på mobilen.",
    ("windows", "wireless"): "Steam Link (gratis, fra butikken i Questen) kobler rett til SteamVR på PC-en – ingen ekstra "
                             "program på PC-en. PC-en bør stå på kabel til ruteren.",
    ("windows", "wired"): "Meta Quest Link: koble til med USB 3-kabel, start Meta Horizon Link på PC-en og velg «Link» "
                          "i brillene. SteamVR-spill starter fra Steam som vanlig.",
}


class VrPage(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(18)
        self.set_child(Adw.Clamp(maximum_size=theme.PAGE_WIDTH, child=box))
        self._busy = False

        # ---- hodesettet ----
        c, i = card("Hodesettet", "Ser om Questen er koblet til med kabel eller er på Wi-Fi – og om den strømmer nå.")
        box.append(c)
        hs = Gtk.Box(spacing=12, homogeneous=True)
        self.h_usb = self._hs_tile("🔌", _t("Kabel"))
        self.h_wifi = self._hs_tile("📶", _t("Wi-Fi"))
        hs.append(self.h_usb[0])
        hs.append(self.h_wifi[0])
        i.append(hs)
        self.h_note = Gtk.Label(xalign=0, wrap=True)
        self.h_note.add_css_class("dim-label")
        self.h_note.add_css_class("caption")
        i.append(self.h_note)

        # ---- start ----
        c, i = card("Meta Quest 3", "Spill SteamVR-spill i Questen – trådløst eller med kabel. Kontrollsenter setter opp "
                                    "alt som trengs, starter det og holder det i gang.")
        box.append(c)
        if not IS_WIN:                                     # Linux: ALVR eller WiVRn
            erow = Gtk.Box(spacing=0, homogeneous=True)
            erow.add_css_class("linked")
            self.e_alvr = Gtk.ToggleButton(label="ALVR  ·  " + _t("gjennom SteamVR"))
            self.e_wivrn = Gtk.ToggleButton(label="WiVRn  ·  " + _t("OpenXR, lav forsinkelse"), group=self.e_alvr)
            (self.e_wivrn if vr.engine() == "wivrn" else self.e_alvr).set_active(True)
            for b in (self.e_alvr, self.e_wivrn):
                erow.append(b)
                b.connect("toggled", self._engine_changed)
            i.append(erow)
        mrow = Gtk.Box(spacing=0, homogeneous=True)
        mrow.add_css_class("linked")
        self.m_wl = Gtk.ToggleButton(label="📶  " + _t("Trådløst"))
        self.m_wd = Gtk.ToggleButton(label="🔌  " + _t("Med kabel"), group=self.m_wl)
        mode = vr.cfg()["mode"]
        (self.m_wd if mode == "wired" else self.m_wl).set_active(True)
        for b in (self.m_wl, self.m_wd):
            mrow.append(b)
            b.connect("toggled", self._mode_changed)
        i.append(mrow)
        self.how = Gtk.Label(xalign=0, wrap=True)
        self.how.add_css_class("ks-sub")
        i.append(self.how)
        brow = Gtk.Box(spacing=8)
        self.start_b = Gtk.Button(label=_t("Start VR"))
        self.start_b.add_css_class("suggested-action")
        self.start_b.add_css_class("pill")
        self.start_b.connect("clicked", self._start)
        brow.append(self.start_b)
        stop = Gtk.Button(label=_t("Stopp vakten"))
        stop.add_css_class("pill")
        stop.connect("clicked", lambda *_: self.msg.set_label(vr.stop()))
        brow.append(stop)
        i.append(brow)
        self.keep = Gtk.Switch(active=vr.cfg().get("keepalive", True), valign=Gtk.Align.CENTER)
        self.keep.connect("notify::active", lambda s, _p: vr.save_cfg(keepalive=s.get_active()))
        kr = Gtk.Box(spacing=10)
        kc = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        kc.append(Gtk.Label(label=_t("Hold VR i gang og rett feil automatisk"), xalign=0))
        ks = Gtk.Label(label=_t("Starter ALVR, SteamVR og kabel-tilkoblingen igjen hvis de stopper mens du spiller."),
                       xalign=0, wrap=True)
        ks.add_css_class("dim-label")
        ks.add_css_class("caption")
        kc.append(ks)
        kr.append(kc)
        kr.append(self.keep)
        i.append(kr)
        if IS_WIN:
            wa = Gtk.CheckButton(label=_t("Bruk ALVR i stedet (trådløst og kabel med samme program)"),
                                 active=vr.cfg().get("win_alvr", False))
            wa.connect("toggled", lambda b: (vr.save_cfg(win_alvr=b.get_active()), self.refresh()))
            i.append(wa)
        self.msg = Gtk.Label(xalign=0, wrap=True)
        self.msg.add_css_class("ks-sub")
        i.append(self.msg)

        # ---- sjekkliste ----
        c, i = card("Alt som trengs", "Grønt = klart. Trykk «Fiks alt», så installerer og retter Kontrollsenter det som "
                                      "kan gjøres automatisk – resten forklares.")
        box.append(c)
        top = Gtk.Box(spacing=8)
        self.fix_b = Gtk.Button(label=_t("Fiks alt"))
        self.fix_b.add_css_class("suggested-action")
        self.fix_b.add_css_class("pill")
        self.fix_b.connect("clicked", self._fix_all)
        top.append(self.fix_b)
        rb = Gtk.Button(label=_t("Sjekk på nytt"))
        rb.add_css_class("pill")
        rb.connect("clicked", lambda *_: self.refresh())
        top.append(rb)
        self.spin = Gtk.Spinner()
        top.append(self.spin)
        i.append(top)
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.list.add_css_class("boxed-list")
        i.append(self.list)
        self.fixmsg = Gtk.Label(xalign=0, wrap=True)
        self.fixmsg.add_css_class("ks-sub")
        i.append(self.fixmsg)

        # ---- tips ----
        c, i = card("Tips for best bilde")
        box.append(c)
        for t in ("PC-en på nettverkskabel til ruteren, Questen på 5 GHz eller 6 GHz – helst i samme rom som ruteren.",
                  "Med kabel: bruk en USB 3-kabel (USB-C) direkte i PC-en, ikke via hub.",
                  "Hakker det? Senk oppløsning/bitrate i ALVR (Linux) eller Steam Link-innstillingene i brillene.",
                  "Spillmodus på Oversikt gir mest ytelse til SteamVR."):
            lab = Gtk.Label(label="• " + _t(t), xalign=0, wrap=True)
            i.append(lab)
        self._update_how()
        self.refresh()
        self._hs_busy = False
        self._headset()
        GLib.timeout_add_seconds(6, lambda: (self.get_mapped() and not self._busy and self._quick(), True)[1])
        GLib.timeout_add_seconds(5, lambda: (self.get_mapped() and self._headset(), True)[1])

    # ---- hodesettet ----
    def _hs_tile(self, icon, title):
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        b.add_css_class("card")
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=10, margin_bottom=10,
                        margin_start=12, margin_end=12)
        b.append(inner)
        top = Gtk.Box(spacing=8)
        ic = Gtk.Label(label=icon)
        ic.add_css_class("title-2")
        top.append(ic)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        t = Gtk.Label(label=title, xalign=0)
        t.add_css_class("caption-heading")
        t.add_css_class("dim-label")
        col.append(t)
        st = Gtk.Label(label="…", xalign=0)
        st.add_css_class("heading")
        col.append(st)
        top.append(col)
        inner.append(top)
        sub = Gtk.Label(xalign=0, wrap=True)
        sub.add_css_class("caption")
        sub.add_css_class("dim-label")
        inner.append(sub)
        return b, st, sub

    def _headset(self):
        if self._hs_busy:
            return False
        self._hs_busy = True

        def done(h):
            self._hs_busy = False
            if isinstance(h, Exception):
                return
            ub, ust, usub = self.h_usb
            wb, wst, wsub = self.h_wifi
            for w in (ub, wb):
                w.remove_css_class("success")
            if h["usb"]:
                ust.set_label(_t("Tilkoblet"))
                ub.add_css_class("success")
                bits = [h.get("model") or "Meta Quest"]
                if h.get("battery") is not None:
                    bits.append(f"🔋 {h['battery']} %")
                if h["adb"] == "unauthorized":
                    bits.append(_t("godkjenn PC-en i brillene"))
                elif h.get("via") == "Quest Link":
                    bits.append("Quest Link")
                usub.set_label(" · ".join(bits))
            else:
                ust.set_label(_t("Ikke tilkoblet"))
                usub.set_label(_t("Koble til med USB-C-kabel"))
            if h["streaming"]:
                wst.set_label(_t("Strømmer nå"))
                wb.add_css_class("success")
                wsub.set_label(f"{h.get('via') or ''} · {h['wifi_ip']}".strip(" ·"))
            elif h["wifi_online"]:
                wst.set_label(_t("På Wi-Fi"))
                wb.add_css_class("success")
                wsub.set_label(f"{h['wifi_ip']} · " + _t("klar – start VR"))
            else:
                wst.set_label(_t("Ikke funnet"))
                wsub.set_label(_t("Slå på brillene og koble til samme nett"))
            known = h.get("wifi_ip") or vr.cfg().get("quest_ip")
            self.h_note.set_label("" if known else _t("Tips: koble Questen til med kabel én gang, så husker "
                                                      "Kontrollsenter Wi-Fi-adressen og ser den trådløst etterpå."))
        _bg(vr.headset, done)
        return False

    # ------------------------------------------------------------------
    def _mode(self):
        return "wired" if self.m_wd.get_active() else "wireless"

    def _update_how(self):
        os_ = "windows" if IS_WIN and not vr.cfg().get("win_alvr") else "linux"
        if vr.engine() == "wivrn":
            os_ = "wivrn"
        self.how.set_label(_t(HOW[(os_, self._mode())]))

    def _engine_changed(self, b):
        if not b.get_active():
            return
        vr.save_cfg(engine="wivrn" if self.e_wivrn.get_active() else "alvr")
        self._update_how()
        self.refresh()

    def _mode_changed(self, b):
        if not b.get_active():
            return
        vr.save_cfg(mode=self._mode())
        self._update_how()
        self.refresh()

    def refresh(self):
        if self._busy:
            return
        self.spin.start()
        _bg(lambda: vr.checks(self._mode()), self._show)

    def _quick(self):
        """Oppdater bare når Questen kobles til/fra (billig sjekk)."""
        q = vr._quest_usb()
        if q != getattr(self, "_last_usb", None):
            self._last_usb = q
            self.refresh()
        return False

    def _show(self, rows):
        self.spin.stop()
        if isinstance(rows, Exception):
            self.fixmsg.set_label(str(rows))
            return
        while (ch := self.list.get_first_child()) is not None:
            self.list.remove(ch)
        missing = 0
        for r in rows:
            icon = "✅" if r["ok"] else ("⚠️" if r["warn"] else "❌")
            if not r["ok"] and not r["warn"]:
                missing += 1
            row = Adw.ActionRow(title=f"{icon}  {_t(r['title'])}",
                                subtitle=GLib.markup_escape_text(_t(r["manual"] or r["info"] or "")))
            row.set_subtitle_lines(4)
            if not r["ok"] and r["fix"]:
                b = Gtk.Button(label=_t("Fiks"), valign=Gtk.Align.CENTER)
                b.add_css_class("pill")
                b.connect("clicked", lambda _b, k=r["key"]: self._fix_one(k))
                row.add_suffix(b)
            self.list.append(row)
        self.fix_b.set_sensitive(any(not r["ok"] and r["fix"] for r in rows))
        self.start_b.set_label(_t("Start VR") if missing == 0 else _t("Start VR ({n} mangler)").format(n=missing))

    def _fix_one(self, key):
        self._busy = True
        self.spin.start()
        self.fixmsg.set_label(_t("Retter …"))

        def done(r):
            self._busy = False
            self.fixmsg.set_label(str(r))
            self.refresh()
        _bg(lambda: vr.fix(key), done)

    def _fix_all(self, *_):
        self._busy = True
        self.spin.start()
        self.fix_b.set_sensitive(False)

        def work():
            return vr.fix_all(lambda t: GLib.idle_add(self.fixmsg.set_label, _t(t)), self._mode())

        def done(r):
            self._busy = False
            if isinstance(r, Exception):
                self.fixmsg.set_label(str(r))
            else:
                self.fixmsg.set_label("\n".join(f"{t}: {m}" for t, m in r) or _t("Alt som kan rettes automatisk, er klart ✓"))
            self.refresh()
        _bg(work, done)

    def _start(self, *_):
        self.msg.set_label(_t("Starter …"))
        _bg(lambda: vr.start(self._mode()), lambda r: self.msg.set_label(str(r)))
