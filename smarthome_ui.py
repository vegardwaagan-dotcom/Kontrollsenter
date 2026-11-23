"""Smart Hjem-siden: alle smartenhetene på hjemmenettet – Hue-lys, TV-er, Chromecast/Nest og resten."""
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

import i18n  # noqa: E402
import smarthome as SH  # noqa: E402

GROUPS = {"hub": "Lys", "light": "Lys", "tv": "Andre TV-er og høyttalere", "cast": "Andre TV-er og høyttalere",
          "speaker": "Andre TV-er og høyttalere", "plug": "Smartenheter", "camera": "Smartenheter",
          "pc": "PC-er og konsoller", "console": "PC-er og konsoller", "nas": "Nettverk", "router": "Nettverk",
          "printer": "Nettverk", "phone": "Mobiler og nettbrett", "other": "Andre enheter"}


def _emoji(text):
    lab = Gtk.Label(label=text)
    lab.add_css_class("title-2")
    lab.set_size_request(40, -1)
    return lab


def _btn(label, cb, tip=None):
    b = Gtk.Button(label=label, tooltip_text=i18n.tr(tip) if tip else None, hexpand=True)
    b.connect("clicked", lambda *_: cb())
    return b


class SmartHomePage(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.hold_until = 0
        self.data = None
        self.show_anon = False
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for side in ("top", "bottom", "start", "end"):
            getattr(outer, f"set_margin_{side}")(12)
        self.set_child(Adw.Clamp(maximum_size=1000, child=outer))

        top = Gtk.Box(spacing=12)
        info = Gtk.Label(label=i18n.tr("Lys, TV-er, høyttalere og alt annet som er koblet til hjemmenettet. "
                                       "Trykk på en enhet for å gi den et navn."), xalign=0, wrap=True, hexpand=True)
        info.add_css_class("ks-desc")
        top.append(info)
        self.when = Gtk.Label(xalign=1)
        self.when.add_css_class("dim-label")
        self.when.add_css_class("caption")
        top.append(self.when)
        self.scan_btn = Gtk.Button(label=i18n.tr("Søk på nytt"), valign=Gtk.Align.CENTER)
        self.scan_btn.add_css_class("pill")
        self.scan_btn.connect("clicked", lambda *_: self.load(rescan=True))
        top.append(self.scan_btn)
        outer.append(top)
        self.status = Gtk.Label(xalign=0, wrap=True)
        self.status.add_css_class("dim-label")
        outer.append(self.status)
        outer.append(self._auto_card())
        try:
            import homeplus_ui
            outer.append(homeplus_ui.guest_box())
        except Exception:  # noqa: BLE001
            pass
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.body.set_margin_top(6)
        outer.append(self.body)
        import ui
        self.body.append(ui.empty("ks-smarthome-symbolic", "Leter etter enheter …",
                                  "Første søk tar 5–10 sekunder.", compact=False))
        self.load()
        GLib.timeout_add_seconds(10, self._tick)

    def _auto_card(self):
        import smartauto
        grp = Adw.PreferencesGroup(title=i18n.tr("Automatikk"))
        grp.set_margin_top(6)
        for key, title, sub in (
                ("game_hue", "Hue-lysene følger spillet",
                 "Når et spill starter, får lysene spillets farge (temaet du har valgt for spillet). Tilbake etterpå."),
                ("tv_off_sleep", "Slå av TV-en når PC-en går i hvilemodus",
                 "Også når PC-en slås av. Gjelder Samsung-TV-er Kontrollsenter har funnet."),
                ("sync_rgb_hue", "Synk RGB og Hue",
                 "Lysene i rommet og i PC-en har alltid samme farge – uansett om du endrer i Kontrollsenter eller "
                 "i Hue-appen.")):
            row = Adw.SwitchRow(title=i18n.tr(title), subtitle=i18n.tr(sub), active=smartauto.opt(key))
            row.set_subtitle_lines(3)
            row.connect("notify::active", lambda r, _p, k=key: smartauto.set_opt(k, r.get_active()))
            grp.add(row)
        self.pres_row = Adw.ExpanderRow(title=i18n.tr("Hjemme / borte"),
                                        subtitle=i18n.tr("Velg telefonene i huset. Scener kan slå seg på «Når noen "
                                                         "kommer hjem» eller «Når alle har dratt» (Scener → Når). "
                                                         "Tips: gi telefonene navn i lista lenger ned først."))
        self.pres_row.set_subtitle_lines(3)
        grp.add(self.pres_row)
        import presence
        ar = Adw.SpinRow.new_with_range(5, 120, 5)
        ar.set_title(i18n.tr("Borte etter (minutter uten livstegn)"))
        ar.set_value(presence.cfg().get("away_min", 20))

        def set_away(r, _p):
            c = presence.cfg()
            c["away_min"] = int(r.get_value())
            presence.save_cfg(c)
        ar.connect("notify::value", set_away)
        self.pres_row.add_row(ar)
        self._pres_rows = []
        return grp

    def _fill_presence(self, devs):
        import presence
        for r in self._pres_rows:
            self.pres_row.remove(r)
        self._pres_rows = []
        chosen = {p.get("mac") or p.get("ip"): p for p in presence.cfg().get("phones") or []}
        st = {p["name"]: p.get("home") for p in presence.state()["phones"]}
        phones = [d for d in devs if d.get("kind") == "phone"]
        for key, p in chosen.items():                       # valgte telefoner som ikke ble funnet nå
            if not any((d.get("mac") or d["ip"]) == key for d in phones):
                phones.append({"mac": p.get("mac", ""), "ip": p.get("ip", ""), "name": p["name"], "kind_name": ""})
        if not phones:
            r = Adw.ActionRow(title=i18n.tr("Fant ingen telefoner på nettet ennå"),
                              subtitle=i18n.tr("Telefonen må være koblet til wifi-en hjemme. Trykk «Søk på nytt»."))
            self.pres_row.add_row(r)
            self._pres_rows.append(r)
            return
        for d in phones:
            key = d.get("mac") or d["ip"]
            name = d.get("name") or f"{i18n.tr('Mobil')} …{d['ip'].rsplit('.', 1)[-1]}"
            here = st.get(chosen[key]["name"]) if key in chosen else None
            r = Adw.SwitchRow(title=GLib.markup_escape_text(name),
                              subtitle=GLib.markup_escape_text(d["ip"] + ("  ·  🏠 " + i18n.tr("hjemme") if here else "")),
                              active=key in chosen)

            def toggle(w, _p, d=d, key=key, name=name):
                c = presence.cfg()
                ph = [p for p in c.get("phones") or [] if (p.get("mac") or p.get("ip")) != key]
                if w.get_active():
                    ph.append({"name": name, "mac": d.get("mac", ""), "ip": d["ip"]})
                c["phones"] = ph
                presence.save_cfg(c)
            r.connect("notify::active", toggle)
            self.pres_row.add_row(r)
            self._pres_rows.append(r)

    # ---------- henting ----------
    def _tick(self):
        if self.get_mapped() and time.time() > self.hold_until:
            self.load()
        return True

    def load(self, rescan=False):
        if rescan:
            self.status.set_label(i18n.tr("Søker etter enheter … (tar 5–10 sekunder)"))
            self.scan_btn.set_sensitive(False)

        def work():
            try:
                d = SH.state(rescan=rescan)
                err = None
            except Exception as e:  # noqa: BLE001
                d, err = None, str(e)
            GLib.idle_add(self._loaded, d, err, rescan)
        threading.Thread(target=work, daemon=True).start()

    def _loaded(self, d, err, rescan):
        self.scan_btn.set_sensitive(True)
        if rescan:
            self.status.set_label("")
        if err:
            self.status.set_label(i18n.tr("Feil: ") + err)
            return False
        if time.time() < self.hold_until and not rescan:
            return False
        self.data = d
        self.render(d)
        return False

    def act(self, body, quiet=True):
        self.hold_until = time.time() + 3

        def work():
            try:
                msg = SH.action(body)
                ok = True
            except Exception as e:  # noqa: BLE001
                msg, ok = str(e), False
            GLib.idle_add(done, ok, msg)

        def done(ok, msg):
            if not ok or (not quiet and msg and msg != "OK"):
                import ui
                if not ui.toast(self, msg if ok else i18n.tr("Feil: ") + msg, 4):
                    self.status.set_label(msg)
            GLib.timeout_add(1200, lambda: (self.load(), False)[1])
            return False
        threading.Thread(target=work, daemon=True).start()

    # ---------- tegning ----------
    def _section(self, title):
        lab = Gtk.Label(label=i18n.tr(title).upper(), xalign=0)
        lab.add_css_class("ks-section")
        lab.add_css_class("caption-heading")
        lab.add_css_class("dim-label")
        self.body.append(lab)

    def render(self, d):
        try:
            self._fill_presence(d.get("devices") or [])
        except Exception:  # noqa: BLE001
            pass
        while (ch := self.body.get_first_child()):
            self.body.remove(ch)
        devs = d.get("devices") or []
        t = d.get("scanned")
        self.when.set_label((time.strftime("%H:%M", time.localtime(t)) if t else "") + (" · søker …" if d.get("scanning") else ""))
        hub = next((x for x in devs if "hue" in x["control"]), None)
        tvs = [x for x in devs if "samsung" in x["control"]]
        casts = [x for x in devs if "cast" in x["control"]]
        done = {id(x) for x in [hub, *tvs, *casts] if x}
        rest = [x for x in devs if id(x) not in done]
        hue = d.get("hue") or {}
        if hub or hue.get("paired"):
            self._section("Lys")
            self.body.append(self._hue_card(hue, hub))
        if tvs or casts:
            self._section("TV, strømming og høyttalere")
            flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True, max_children_per_line=2,
                               min_children_per_line=1, column_spacing=12, row_spacing=12)
            flow.add_css_class("ks-cards")
            for x in tvs:
                flow.append(self._tv_card(x))
            for x in casts:
                flow.append(self._cast_card(x))
            self.body.append(flow)
        named = [x for x in rest if x["name"] or x["kind"] not in ("phone", "other")]
        anon = [x for x in rest if x not in named]
        groups = {}
        for x in named:
            groups.setdefault(GROUPS.get(x["kind"], "Andre enheter"), []).append(x)
        for g, items in groups.items():
            self._section(g)
            lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
            lb.add_css_class("boxed-list")
            for x in items:
                lb.append(self._dev_row(x))
            self.body.append(lb)
        if anon:
            lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
            lb.add_css_class("boxed-list")
            exp = Adw.ExpanderRow(title=i18n.tr("Uten navn") + f" ({len(anon)})",
                                  subtitle=i18n.tr("Mobiler, nettbrett og annet – trykk for å gi dem navn"),
                                  expanded=self.show_anon)
            exp.connect("notify::expanded", lambda e, _p: setattr(self, "show_anon", e.get_expanded()))
            for x in anon:
                exp.add_row(self._dev_row(x))
            lb.append(exp)
            self._section("Andre")
            self.body.append(lb)
        if not devs:
            import ui
            self.body.append(ui.empty("ks-smarthome-symbolic", "Fant ingen enheter ennå",
                                      "Trykk «Søk på nytt» om litt.", compact=False))
        try:                                      # TV-/høyttalerkortene kan dras til ny plass
            import sortbox
            sortbox.scan(self, "smarthjem")
        except Exception:  # noqa: BLE001
            pass

    def _card(self):
        c = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        c.add_css_class("card")
        for side in ("top", "bottom", "start", "end"):
            getattr(c, f"set_margin_{side}")(0)
        c.set_valign(Gtk.Align.START)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side in ("top", "bottom", "start", "end"):
            getattr(inner, f"set_margin_{side}")(14)
        c.append(inner)
        return c, inner

    def _head(self, icon, title, sub, extra=None):
        h = Gtk.Box(spacing=12)
        h.append(_emoji(icon))
        tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
        t = Gtk.Label(label=title, xalign=0, ellipsize=3)
        t.add_css_class("heading")
        tb.append(t)
        s = Gtk.Label(label=sub, xalign=0, ellipsize=3)
        s.add_css_class("dim-label")
        s.add_css_class("caption")
        tb.append(s)
        h.append(tb)
        if extra:
            extra.set_valign(Gtk.Align.CENTER)
            h.append(extra)
        return h

    # ---- Hue ----
    def _hue_card(self, h, hub):
        c, box = self._card()
        if not h.get("paired"):
            box.append(self._head("💡", "Philips Hue", hub["ip"] if hub else ""))
            lab = Gtk.Label(label=i18n.tr("Trykk på den runde knappen på Hue-broen, og trykk «Koble til» innen 30 sekunder."),
                            xalign=0, wrap=True)
            lab.add_css_class("dim-label")
            box.append(lab)
            b = Gtk.Button(label=i18n.tr("Koble til Hue"), halign=Gtk.Align.START)
            b.add_css_class("pill")
            b.connect("clicked", lambda *_: self.act({"do": "huepair"}, quiet=False))
            box.append(b)
            return c
        if h.get("error"):
            box.append(self._head("💡", "Philips Hue", h["error"]))
            return c
        lights = h.get("lights") or []
        n_on = sum(1 for x in lights if x["on"])
        sw = Gtk.Switch(active=n_on > 0)
        sw.connect("state-set", lambda _w, st: self.act({"do": "hue", "on": st}) or False)
        box.append(self._head("💡", i18n.tr("Lys"), f"{n_on} av {len(lights)} er på · Philips Hue", sw))
        if h.get("rooms"):
            fb = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=8, column_spacing=6, row_spacing=6)
            for r in h["rooms"]:
                tb = Gtk.ToggleButton(label=r["name"], active=r["any_on"])
                tb.add_css_class("pill")
                tb.connect("toggled", lambda w, rid=r["id"]: self.act({"do": "hue", "room": rid, "on": w.get_active()}))
                fb.append(tb)
            box.append(fb)
        lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        lb.add_css_class("boxed-list")
        for x in lights:
            row = Adw.ActionRow(title=x["name"] or "?", subtitle="" if x["reachable"] else i18n.tr("Svarer ikke (strømmen av?)"))
            if x.get("can_dim"):
                sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 254, 1)
                sc.set_draw_value(False)
                sc.set_size_request(160, -1)
                sc.set_value(x.get("bri") or 1)
                sc.set_valign(Gtk.Align.CENTER)
                sc.set_sensitive(x["reachable"])
                self._debounce(sc, lambda v, lid=x["id"]: self.act({"do": "hue", "light": lid, "bri": int(v)}))
                row.add_suffix(sc)
            if x.get("can_color") and hasattr(Gtk, "ColorDialogButton"):
                cb = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False), valign=Gtk.Align.CENTER)
                rgba = Gdk.RGBA()
                rgba.parse(x.get("color") or "#ffd9a0")
                cb.set_rgba(rgba)
                cb.set_sensitive(x["reachable"])

                def on_col(w, _p, lid=x["id"]):
                    c = w.get_rgba()
                    self.act({"do": "hue", "light": lid,
                              "color": "#%02x%02x%02x" % (int(c.red * 255), int(c.green * 255), int(c.blue * 255))})
                cb.connect("notify::rgba", on_col)
                row.add_suffix(cb)
            s = Gtk.Switch(active=x["on"], valign=Gtk.Align.CENTER, sensitive=x["reachable"])
            s.connect("state-set", lambda _w, st, lid=x["id"]: self.act({"do": "hue", "light": lid, "on": st}) or False)
            row.add_suffix(s)
            lb.append(row)
        box.append(lb)
        return c

    def _debounce(self, scale, cb):
        st = {"t": 0}

        def changed(w):
            self.hold_until = time.time() + 3
            if st["t"]:
                GLib.source_remove(st["t"])

            def fire():
                st["t"] = 0
                cb(w.get_value())
                return False
            st["t"] = GLib.timeout_add(400, fire)
        scale.connect("value-changed", changed)

    # ---- Samsung-TV ----
    def _tv_card(self, x):
        c, box = self._card()
        L = x.get("live") or {}
        on = L.get("power") == "on"
        pw = Gtk.ToggleButton(icon_name="system-shutdown-symbolic", active=on, tooltip_text=i18n.tr("Av/på"))
        pw.add_css_class("circular")
        pw.connect("clicked", lambda *_: self.act({"do": "tv", "ip": x["ip"], "key": "power" if on else "on"}, quiet=False))
        state = i18n.tr("På") if on else i18n.tr("Hvilemodus") if L.get("power") == "standby" else i18n.tr("Av")
        box.append(self._head("📺", x["name"] or "TV", f"{state} · {x.get('model') or x.get('maker', '')}", pw))
        if on:
            for keys in ((("audio-volume-low-symbolic", None, "voldown", "Volum ned"),
                          ("audio-volume-muted-symbolic", None, "mute", "Demp"),
                          ("audio-volume-high-symbolic", None, "volup", "Volum opp")),
                         (("go-home-symbolic", "Hjem", "home", None), ("view-dual-symbolic", "Kilde", "source", None),
                          ("media-playback-start-symbolic", None, "play", "Spill"),
                          ("media-playback-pause-symbolic", None, "pause", "Pause"))):
                row = Gtk.Box(spacing=6, homogeneous=True)
                for icon, lab, key, tip in keys:
                    b = Gtk.Button(tooltip_text=i18n.tr(tip) if tip else None, hexpand=True)
                    b.set_child(Adw.ButtonContent(icon_name=icon, label=i18n.tr(lab)) if lab else Gtk.Image(icon_name=icon))
                    b.connect("clicked", lambda *_, k=key: self.act({"do": "tv", "ip": x["ip"], "key": k}))
                    row.append(b)
                box.append(row)
        if not L.get("paired"):
            h = Gtk.Label(label=i18n.tr("Første gang du trykker: velg «Tillat» på TV-en."), xalign=0, wrap=True)
            h.add_css_class("dim-label")
            h.add_css_class("caption")
            box.append(h)
        return c

    # ---- Chromecast / Nest ----
    def _cast_card(self, x):
        c, box = self._card()
        L = x.get("live")
        if not L:
            box.append(self._head(x["icon"], x["name"], f"{x.get('model') or x['kind_name']} · " + i18n.tr("i hvilemodus eller svarer ikke")))
            return c
        mute = Gtk.ToggleButton(icon_name="audio-volume-muted-symbolic", active=L["muted"], tooltip_text=i18n.tr("Demp"))
        mute.add_css_class("circular")
        mute.connect("toggled", lambda w: self.act({"do": "cast", "ip": x["ip"], "what": "mute", "value": w.get_active()}))
        box.append(self._head(x["icon"], x["name"], x.get("model") or x["kind_name"], mute))
        if L.get("app"):
            now = Gtk.Label(label="▶ " + L["app"] + (" – " + L["title"] if L.get("title") and L["title"] != L["app"] else ""),
                            xalign=0, wrap=True)
            now.add_css_class("ks-chip")
            box.append(now)
            row = Gtk.Box(spacing=6, homogeneous=True)
            playing = L.get("playing") is True
            pp = Gtk.ToggleButton(label="⏸ " + i18n.tr("Pause") if playing else "⏵ " + i18n.tr("Spill"), active=playing)
            pp.connect("clicked", lambda *_: self.act({"do": "cast", "ip": x["ip"], "what": "pause" if playing else "play"}))
            row.append(pp)
            row.append(_btn("⏹ " + i18n.tr("Stopp"), lambda: self.act({"do": "cast", "ip": x["ip"], "what": "stop"})))
            box.append(row)
        else:
            n = Gtk.Label(label=i18n.tr("Ingenting spilles nå"), xalign=0)
            n.add_css_class("dim-label")
            box.append(n)
        vb = Gtk.Box(spacing=8)
        vb.append(Gtk.Image(icon_name="audio-volume-medium-symbolic"))
        sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        sc.set_hexpand(True)
        sc.set_draw_value(True)
        sc.set_value_pos(Gtk.PositionType.RIGHT)
        sc.set_value(L["volume"])
        self._debounce(sc, lambda v: self.act({"do": "cast", "ip": x["ip"], "what": "volume", "value": int(v)}))
        vb.append(sc)
        box.append(vb)
        import smarthome
        names = [n for n, _u in smarthome.radio_list()]
        rb = Gtk.Box(spacing=6)
        rb.append(Gtk.Image(icon_name="audio-x-generic-symbolic"))
        dd = Gtk.DropDown.new_from_strings(names)
        dd.set_hexpand(True)
        dd.set_tooltip_text(i18n.tr("Nettradio rett på høyttaleren – PC-en kan slås av etterpå"))
        rb.append(dd)
        rb.append(_btn("📻 " + i18n.tr("Spill radio"),
                       lambda: self.act({"do": "cast", "ip": x["ip"], "what": "radio",
                                         "value": names[dd.get_selected()]}, quiet=False)))
        box.append(rb)
        return c

    # ---- vanlige enheter ----
    def _dev_row(self, x):
        sub = " · ".join(p for p in (x["kind_name"] if x["name"] else "", x.get("model") or x.get("maker", "")) if p)
        row = Adw.ActionRow(title=GLib.markup_escape_text(x["name"] or x["kind_name"]), subtitle=GLib.markup_escape_text(sub),
                            activatable=x["id"] != "self")
        row.add_prefix(_emoji(x["icon"]))
        ip = Gtk.Label(label=x["ip"])
        ip.add_css_class("dim-label")
        ip.add_css_class("numeric")
        ip.add_css_class("caption")
        row.add_suffix(ip)
        row.connect("activated", lambda *_: self._rename(x))
        return row

    def _rename(self, x):
        dlg = Adw.AlertDialog(heading=i18n.tr("Gi enheten et navn"), body=f"{x['ip']}  {x.get('mac', '')}")
        ent = Gtk.Entry(text=x["name"] or "", activates_default=True)
        dlg.set_extra_child(ent)
        dlg.add_response("cancel", i18n.tr("Avbryt"))
        dlg.add_response("ok", i18n.tr("Lagre"))
        dlg.set_default_response("ok")
        dlg.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)

        def resp(_d, r):
            if r == "ok" and ent.get_text().strip():
                self.act({"do": "rename", "id": x["id"], "name": ent.get_text().strip()})
        dlg.connect("response", resp)
        dlg.present(self.get_root())
