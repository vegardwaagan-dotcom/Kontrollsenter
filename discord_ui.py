"""Siden «Discord»: mikrofon, lyd av, forlat samtalen, volum, enheter, mikrofonmodus, støy-/ekkodemping og overlay."""
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

import discord_ctl as D  # noqa: E402
import i18n  # noqa: E402

CSS = """
togglebutton.ks-dc-big, button.ks-dc-big { min-height: 64px; border-radius: 20px; font-weight: 800; font-size: 1.05em; }
label.ks-bubble { padding: 8px 12px; border-radius: 16px; background-color: alpha(currentColor, 0.08); }
label.ks-bubble.mine { color: white; background-image: linear-gradient(135deg, #5b8cff, #8a5cff); }
"""
_css = [False]


class DiscordPage(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        if not _css[0]:
            _css[0] = True
            import theme
            theme.add_css(CSS, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 5)
        self._quiet = False
        self.st = {}
        pp = Adw.PreferencesPage()
        self.set_child(pp)

        # ---- status og hurtigknapper ----
        g = Adw.PreferencesGroup()
        self.status = Adw.ActionRow(title=i18n.tr("Discord"), subtitle=i18n.tr("Sjekker …"))
        self.open_btn = Gtk.Button(label=i18n.tr("Åpne Discord"), valign=Gtk.Align.CENTER)
        self.open_btn.connect("clicked", lambda *_: self._open_discord())
        self.status.add_suffix(self.open_btn)
        g.add(self.status)
        pp.add(g)
        g = Adw.PreferencesGroup(title=i18n.tr("Samtalen"))
        row = Gtk.Box(spacing=10, homogeneous=True, margin_top=4, margin_bottom=4)
        self.mic = Gtk.ToggleButton(label="🎙️  " + i18n.tr("Mikrofon av"))
        self.deaf = Gtk.ToggleButton(label="🎧  " + i18n.tr("Lyd av"))
        self.leave = Gtk.Button(label="📞  " + i18n.tr("Forlat samtalen"))
        for b in (self.mic, self.deaf, self.leave):
            b.add_css_class("ks-dc-big")
            row.append(b)
        self.leave.add_css_class("destructive-action")
        self.mic.connect("toggled", lambda b: self._quiet or self._mute("mic", b.get_active()))
        self.deaf.connect("toggled", lambda b: self._quiet or self._mute("deaf", b.get_active()))
        self.leave.connect("clicked", lambda *_: self._do({"do": "leave"}))
        g.add(row)
        self.channel = Gtk.Label(xalign=0, wrap=True, margin_top=6)
        self.channel.add_css_class("dim-label")
        g.add(self.channel)
        self.members = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, margin_top=6)
        self.members.add_css_class("boxed-list")
        g.add(self.members)
        pp.add(g)

        # ---- lyd ----
        g = Adw.PreferencesGroup(title=i18n.tr("Lyd"))
        self.in_vol = self._scale_row(g, "Mikrofonvolum", 0, 100, lambda v: self._do({"do": "in_vol", "value": v}))
        self.out_vol = self._scale_row(g, "Volum på samtalen", 0, 200, lambda v: self._do({"do": "out_vol", "value": v}))
        self.sys_vol = self._scale_row(g, "Discord-volum (lydsystemet)", 0, 150,
                                       lambda v: self._do({"do": "out_vol_sys", "value": int(v)}))
        self.in_dev = Adw.ComboRow(title=i18n.tr("Mikrofon"))
        self.out_dev = Adw.ComboRow(title=i18n.tr("Høyttalere / headset"))
        self.in_dev.connect("notify::selected", lambda r, _p: self._dev("in_dev", r))
        self.out_dev.connect("notify::selected", lambda r, _p: self._dev("out_dev", r))
        g.add(self.in_dev)
        g.add(self.out_dev)
        self.audio_grp = g
        pp.add(g)

        # ---- mikrofon ----
        g = Adw.PreferencesGroup(title=i18n.tr("Mikrofon"))
        self.mode = Adw.ComboRow(title=i18n.tr("Når snakker du?"),
                                 model=Gtk.StringList.new([i18n.tr("Stemmeaktivering"), i18n.tr("Trykk for å snakke")]))
        self.mode.connect("notify::selected", lambda r, _p: self._quiet or self._do(
            {"do": "mode", "value": "PUSH_TO_TALK" if r.get_selected() == 1 else "VOICE_ACTIVITY"}))
        g.add(self.mode)
        self.sw = {}
        for key, title, sub in (("noise", "Støydemping", "Fjerner tastatur, vifter og bakgrunnsstøy fra mikrofonen."),
                                ("echo", "Ekkodemping", "Hindrer at de andre hører seg selv fra høyttalerne dine."),
                                ("agc", "Automatisk forsterkning", "Jevner ut stemmen når du snakker lavt eller høyt.")):
            r = Adw.SwitchRow(title=i18n.tr(title), subtitle=i18n.tr(sub))
            r.connect("notify::active", lambda w, _p, k=key: self._quiet or self._do({"do": k, "on": w.get_active()}))
            g.add(r)
            self.sw[key] = r
        self.mic_grp = g
        pp.add(g)

        # ---- servere og chat ----
        g = Adw.PreferencesGroup(title=i18n.tr("Servere og chat"),
                                 description=i18n.tr("Les chatten i kanalene dine her. Svar i Discord med «Åpne i "
                                                     "Discord» – Discord tillater ikke at andre programmer sender "
                                                     "meldinger eller viser vennelisten for deg."))
        self.guild_box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.guild_box.add_css_class("boxed-list")
        g.add(self.guild_box)
        self.guild_msg = Gtk.Label(xalign=0, wrap=True, margin_top=6)
        self.guild_msg.add_css_class("dim-label")
        g.add(self.guild_msg)
        self.chat_grp = g
        self._guilds_loaded = False
        pp.add(g)

        # ---- overlay ----
        g = Adw.PreferencesGroup(title=i18n.tr("Overlay"))
        self.ov = Adw.ActionRow(title=i18n.tr("Overlay i spill"))
        self.ov.set_subtitle_lines(3)
        ob = Gtk.Button(label=i18n.tr("Spill-overlay i Kontrollsenter"), valign=Gtk.Align.CENTER)
        ob.connect("clicked", lambda *_: self._toggle_overlay())
        self.ov.add_suffix(ob)
        g.add(self.ov)
        pp.add(g)

        # ---- oppsett ----
        g = Adw.PreferencesGroup(title=i18n.tr("Full tilkobling til Discord"),
                                 description=i18n.tr(
                                     "For volum, enheter, mikrofonmodus og demping må Discord gi Kontrollsenter lov. "
                                     "Det gjøres én gang: 1) Gå til discord.com/developers/applications og trykk "
                                     "«New Application» (kall den f.eks. Kontrollsenter). 2) Under OAuth2: kopier "
                                     "Client ID og Client Secret, og legg til Redirect «http://localhost». 3) Lim inn "
                                     "her og trykk «Koble til» – Discord spør om du godkjenner."))
        c = D.cfg()
        self.cid = Adw.EntryRow(title="Client ID", text=c.get("client_id", ""))
        self.secret = Adw.PasswordEntryRow(title="Client Secret", text=c.get("client_secret", ""))
        g.add(self.cid)
        g.add(self.secret)
        br = Gtk.Box(spacing=8, margin_top=8)
        self.link_btn = Gtk.Button(label=i18n.tr("Koble til"))
        self.link_btn.add_css_class("suggested-action")
        self.link_btn.connect("clicked", self._link)
        br.append(self.link_btn)
        web = Gtk.Button(label=i18n.tr("Åpne Discord Developer Portal"))
        web.connect("clicked", lambda *_: Gio.AppInfo.launch_default_for_uri(
            "https://discord.com/developers/applications", None))
        br.append(web)
        self.unlink_btn = Gtk.Button(label=i18n.tr("Koble fra"))
        self.unlink_btn.connect("clicked", lambda *_: (D.disconnect_app(), self.refresh()))
        br.append(self.unlink_btn)
        g.add(br)
        self.link_msg = Gtk.Label(xalign=0, wrap=True, margin_top=6)
        self.link_msg.add_css_class("dim-label")
        g.add(self.link_msg)
        pp.add(g)

        self.refresh()
        GLib.timeout_add_seconds(3, lambda: (self.get_mapped() and self.refresh(), True)[1])

    # ---- hjelpere ----
    def _scale_row(self, grp, title, lo, hi, cb):
        row = Adw.ActionRow(title=i18n.tr(title))
        sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, 1)
        sc.set_size_request(260, -1)
        sc.set_valign(Gtk.Align.CENTER)
        sc.set_draw_value(True)
        sc._t = 0

        def changed(s):
            if self._quiet:
                return
            s._t = time.monotonic()
            v = s.get_value()

            def fire():
                if time.monotonic() - s._t >= 0.25:
                    cb(v)
                return False
            GLib.timeout_add(280, fire)
        sc.connect("value-changed", changed)
        row.add_suffix(sc)
        grp.add(row)
        row.scale = sc
        return row

    def _toast(self, txt):
        w = self.get_root()
        if w is not None and hasattr(w, "toast"):
            w.toast(txt)

    def _do(self, a):
        def work():
            try:
                D.action(a)
                err = None
            except Exception as e:  # noqa: BLE001
                err = str(e)
            GLib.idle_add(lambda: (err and self._toast("Discord: " + err), self.refresh(), False)[2])
        threading.Thread(target=work, daemon=True).start()

    def _mute(self, which, on):
        if D.linked() and self.st.get("voice"):
            self._do({"do": "mute" if which == "mic" else "deaf", "on": on})
        else:
            self._do({"do": "mic_mute_sys" if which == "mic" else "out_mute_sys", "on": on})

    def _dev(self, key, row):
        if self._quiet or not getattr(row, "ids", None):
            return
        self._do({"do": key, "value": row.ids[row.get_selected()]})

    def _open_discord(self):
        try:
            Gio.AppInfo.launch_default_for_uri("discord://", None)
        except GLib.Error:
            import subprocess
            subprocess.Popen(["flatpak", "run", "com.discordapp.Discord"])

    def _toggle_overlay(self):
        w = self.get_root()
        b = getattr(w, "ov_button", None)
        if b is not None and b.get_visible():
            b.set_active(not b.get_active())
            self._toast("Spill-overlay " + ("på" if b.get_active() else "av"))
        else:
            self._open_discord()

    def _link(self, *_):
        cid, sec = self.cid.get_text().strip(), self.secret.get_text().strip()
        if not cid.isdigit() or not sec:
            self.link_msg.set_label(i18n.tr("Lim inn Client ID (bare tall) og Client Secret først."))
            return
        self.link_btn.set_sensitive(False)
        self.link_msg.set_label(i18n.tr("Se i Discord – godkjenn tilkoblingen der …"))

        def work():
            try:
                who = D.connect_app(cid, sec)
                msg = f"Koblet til som {who} ✓"
            except Exception as e:  # noqa: BLE001
                msg = f"Fikk ikke koblet til: {e}"
            GLib.idle_add(lambda: (self.link_msg.set_label(msg), self.link_btn.set_sensitive(True), self.refresh(),
                                   False)[3])
        threading.Thread(target=work, daemon=True).start()

    # ---- servere og chat ----
    def _load_guilds(self):
        if self._guilds_loaded:
            return
        self._guilds_loaded = True

        def work():
            try:
                gs, err = D.guilds(), None
            except Exception as e:  # noqa: BLE001
                gs, err = [], str(e)
            GLib.idle_add(self._show_guilds, gs, err)
        threading.Thread(target=work, daemon=True).start()

    def _show_guilds(self, gs, err):
        while (c := self.guild_box.get_first_child()) is not None:
            self.guild_box.remove(c)
        self.guild_msg.set_label(i18n.tr("Fikk ikke hentet serverne: ") + err if err else "")
        for g in gs:
            ex = Adw.ExpanderRow(title=GLib.markup_escape_text(g["name"] or "?"))
            ex._gid, ex._loaded = g["id"], False
            ex.connect("notify::expanded", self._expand)
            self.guild_box.append(ex)
        self.guild_box.set_visible(bool(gs))
        return False

    def _expand(self, ex, _p):
        if not ex.get_expanded() or ex._loaded:
            return
        ex._loaded = True

        def work():
            try:
                chs, err = D.channels(ex._gid), None
            except Exception as e:  # noqa: BLE001
                chs, err = [], str(e)
            GLib.idle_add(self._show_channels, ex, chs, err)
        threading.Thread(target=work, daemon=True).start()

    def _show_channels(self, ex, chs, err):
        if err:
            ex.add_row(Adw.ActionRow(title=GLib.markup_escape_text(err)))
        icon = {"text": "#", "news": "📣", "forum": "💬", "voice": "🔊", "stage": "🎙️"}
        for c in chs:
            r = Adw.ActionRow(title=GLib.markup_escape_text(f"{icon[c['kind']]}  {c['name']}"), activatable=True)
            if c["kind"] in ("text", "news"):
                r.connect("activated", lambda _r, c=c, g=ex._gid: ChatDialog(g, c["id"], c["name"]).present(self.get_root()))
                r.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
            else:
                r.connect("activated", lambda _r, c=c, g=ex._gid: Gio.AppInfo.launch_default_for_uri(
                    D.open_url(g, c["id"]), None))
            ex.add_row(r)
        return False

    # ---- oppdatering ----
    def refresh(self):
        def work():
            st = D.state()
            GLib.idle_add(self._show, st)
        threading.Thread(target=work, daemon=True).start()
        return False

    def _show(self, st):
        self.st = st
        self._quiet = True
        try:
            v, a = st.get("voice"), st.get("audio") or {}
            if not st["running"]:
                self.status.set_subtitle(i18n.tr("Discord er ikke startet"))
            elif st["linked"] and v:
                self.status.set_subtitle(i18n.tr("Koblet til – full kontroll"))
            elif st["linked"] and st.get("error"):
                self.status.set_subtitle(i18n.tr("Får ikke kontakt: ") + st["error"])
            else:
                self.status.set_subtitle(i18n.tr("Kjører – lyd og mikrofon styres via lydsystemet. Koble til nederst "
                                                 "for alle innstillingene."))
            self.open_btn.set_visible(not st["running"])
            if v:
                self.mic.set_active(bool(v["mute"]))
                self.deaf.set_active(bool(v["deaf"]))
            else:
                self.mic.set_active(bool((a.get("mic") or [0, False])[1]))
                self.deaf.set_active(bool((a.get("out") or [0, False])[1]))
            self.mic.set_sensitive(bool(v) or bool(a.get("mic")))
            self.deaf.set_sensitive(bool(v) or bool(a.get("out")))
            ch = st.get("channel")
            self.leave.set_sensitive(bool(ch))
            self.channel.set_label(("🔊 " + (ch.get("name") or i18n.tr("Samtale"))) if ch else
                                   i18n.tr("Ikke i en samtale akkurat nå." if v else
                                           "Bli med i en samtale i Discord, så kan du styre den her."))
            while (c := self.members.get_first_child()) is not None:
                self.members.remove(c)
            for m in (ch or {}).get("members", []):
                r = Adw.ActionRow(title=GLib.markup_escape_text(m.get("name") or "?"))
                r.add_suffix(Gtk.Label(label=("🔇" if m.get("mute") else "") + ("🎧❌" if m.get("deaf") else "")))
                self.members.append(r)
            self.members.set_visible(bool((ch or {}).get("members")))
            for row, key in ((self.in_vol, "in_vol"), (self.out_vol, "out_vol")):
                row.set_visible(bool(v))
                if v and time.monotonic() - row.scale._t > 2:
                    row.scale.set_value(v[key])
            self.sys_vol.set_visible(not v and bool(a.get("out")))
            if a.get("out") and time.monotonic() - self.sys_vol.scale._t > 2:
                self.sys_vol.scale.set_value(a["out"][0])
            for row, devs, cur in ((self.in_dev, "in_devs", "in_dev"), (self.out_dev, "out_devs", "out_dev")):
                ds = (v or {}).get(devs) or []
                row.set_visible(bool(ds))
                ids = [d[0] for d in ds]
                if ids != getattr(row, "ids", None):
                    row.ids = ids
                    row.set_model(Gtk.StringList.new([d[1] for d in ds]))
                if v and v.get(cur) in ids:
                    row.set_selected(ids.index(v[cur]))
            self.mic_grp.set_visible(bool(v))
            self.audio_grp.set_visible(bool(v) or bool(a.get("out")))
            if v:
                self.mode.set_selected(1 if v["mode"] == "PUSH_TO_TALK" else 0)
                for k in ("noise", "echo", "agc"):
                    self.sw[k].set_active(bool(v.get(k)))
            self.ov.set_subtitle(i18n.tr(st.get("overlay_note") or ""))
            self.unlink_btn.set_visible(st["linked"])
            ok = st["linked"] and st["running"] and not st.get("error")
            self.chat_grp.set_visible(st["linked"])
            if ok and D.can_read_chat():
                self._load_guilds()
            elif st["linked"] and not D.can_read_chat():
                self.guild_msg.set_label(i18n.tr("Trykk «Koble til på nytt» nederst én gang til, så får Kontrollsenter "
                                                 "lov til å lese chatten også."))
            self.link_btn.set_label(i18n.tr("Koble til på nytt") if st["linked"] else i18n.tr("Koble til"))
        finally:
            self._quiet = False
        return False


class ChatDialog(Adw.Dialog):
    """Chatten i én kanal – oppdateres hvert 4. sekund. Svar i Discord."""

    def __init__(self, guild_id, channel_id, name):
        super().__init__(title="# " + (name or ""), content_width=560, content_height=720)
        self.gid, self.cid = guild_id, channel_id
        tv = Adw.ToolbarView()
        hb = Adw.HeaderBar()
        tv.add_top_bar(hb)
        self.sc = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for side in ("top", "bottom", "start", "end"):
            getattr(self.box, f"set_margin_{side}")(14)
        self.sc.set_child(self.box)
        tv.set_content(self.sc)
        bar = Gtk.Box(spacing=8, margin_top=8, margin_bottom=10, margin_start=12, margin_end=12)
        hint = Gtk.Label(label=i18n.tr("Svar i Discord-appen"), xalign=0, hexpand=True)
        hint.add_css_class("dim-label")
        bar.append(hint)
        ob = Gtk.Button(label=i18n.tr("Åpne i Discord"))
        ob.add_css_class("suggested-action")
        ob.connect("clicked", lambda *_: Gio.AppInfo.launch_default_for_uri(D.open_url(self.gid, self.cid), None))
        bar.append(ob)
        tv.add_bottom_bar(bar)
        self.set_child(tv)
        self._last = None
        self._load()
        self._tid = GLib.timeout_add_seconds(4, lambda: (self._load(), True)[1])
        self.connect("closed", lambda *_: GLib.source_remove(self._tid))

    def _load(self):
        def work():
            try:
                d, err = D.messages(self.cid), None
            except Exception as e:  # noqa: BLE001
                d, err = None, str(e)
            GLib.idle_add(self._show, d, err)
        threading.Thread(target=work, daemon=True).start()

    def _show(self, d, err):
        if err:
            if self._last is None:
                self.box.append(Gtk.Label(label=err, wrap=True))
                self._last = "err"
            return False
        ms = d["messages"]
        sig = ms[-1]["id"] if ms else ""
        if sig == self._last:
            return False
        at_bottom = self.sc.get_vadjustment().get_value() >= self.sc.get_vadjustment().get_upper() - \
            self.sc.get_vadjustment().get_page_size() - 40
        self._last = sig
        while (c := self.box.get_first_child()) is not None:
            self.box.remove(c)
        prev = None
        for m in ms:
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2,
                          halign=Gtk.Align.END if m["mine"] else Gtk.Align.START)
            if m["author"] != prev:
                who = Gtk.Label(xalign=0)
                c = m.get("color") or "#9aa8ff"
                who.set_markup(f'<b><span foreground="{GLib.markup_escape_text(c)}">'
                               f'{GLib.markup_escape_text(m["author"])}</span></b>  <small>'
                               f'{time.strftime("%H:%M", time.localtime(m["t"]))}</small>')
                col.append(who)
            txt = Gtk.Label(label=m["content"], xalign=0, wrap=True, selectable=True, max_width_chars=60)
            txt.add_css_class("ks-bubble")
            if m["mine"]:
                txt.add_css_class("mine")
            col.append(txt)
            self.box.append(col)
            prev = m["author"]
        if at_bottom or len(ms) and self._last == sig:
            GLib.idle_add(lambda: self.sc.get_vadjustment().set_value(self.sc.get_vadjustment().get_upper()) or False)
        return False
