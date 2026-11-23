"""Chat-siden – som Discord: serverlist til venstre (Direkte + dine servere), kanaler i kategorier, meldinger og
medlemmer. Lag server, bli med via lenke, inviter venner, administrer kanaler, roller og medlemmer."""
import os
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Graphene", "1.0")
from gi.repository import Adw, Gdk, Gio, GLib, Graphene, Gtk  # noqa: E402

import chat as C  # noqa: E402
import chatplus as CP  # noqa: E402
import chatlink as CL  # noqa: E402
import chatsrv as CS  # noqa: E402
import chatvoice as CV  # noqa: E402

EMOJI = ("😀 😂 🤣 😊 😍 😎 🤔 😮 😢 😡 👍 👎 👏 🙌 🙏 💪 🔥 🎉 🥳 ❤️ 💯 ✅ ❌ ⭐ 🎮 🕹️ 🎯 🏆 ⚔️ 🛡️ "
         "🐉 🍕 🍔 🍿 ☕ 🍺 🎧 🎤 📸 🎬 💻 🖥️ ⏰ 📅 🏠 🚀 👀 🤝 😴 🤖").split()
import i18n  # noqa: E402

_CSS = """
.ks-chat-me { background: alpha(@accent_bg_color, 0.85); color: @accent_fg_color; border-radius: 16px 16px 4px 16px;
  padding: 8px 12px; }
.ks-chat-other { background: alpha(@window_fg_color, 0.08); border-radius: 16px 16px 16px 4px; padding: 8px 12px; }
.ks-chat-sys { opacity: .7; font-style: italic; padding: 2px 8px; }
.ks-chat-who { font-size: 0.8em; opacity: 0.7; }
.ks-rail { background: alpha(@window_fg_color, 0.04); padding: 10px 6px; }
.ks-rail button { min-width: 46px; min-height: 46px; border-radius: 16px; font-size: 22px; padding: 0; }
.ks-rail button.ks-on { background: alpha(@accent_bg_color, 0.55); border-radius: 14px; }
.ks-chan-cat { font-size: .78em; font-weight: 800; letter-spacing: .06em; opacity: .6; margin: 10px 6px 2px; }
.ks-chan row { padding: 7px 10px; min-height: 34px; border-radius: 8px; }
.ks-chan row.ks-cat-row { min-height: 0; padding: 0 4px 0 0; }
.ks-chan row.ks-vc-row { min-height: 0; padding: 1px 10px; }
.ks-cat-add { min-height: 22px; min-width: 22px; padding: 0 4px; margin-top: 8px; opacity: .7; }
.ks-react { padding: 0 6px; min-height: 22px; border-radius: 11px; font-size: .9em; }
/* nytt utseende: grupperte bobler, datoskiller, store emojier, «Nye meldinger» */
.ks-chat-me { border-radius: 18px 18px 6px 18px; padding: 8px 13px;
  background-image: linear-gradient(160deg, alpha(white, 0.16), alpha(white, 0) 60%);
  box-shadow: 0 2px 8px -4px alpha(black, 0.45); }
.ks-chat-other { border-radius: 18px 18px 18px 6px; padding: 8px 13px;
  box-shadow: inset 0 1px alpha(white, 0.06); }
.ks-chat-me.ks-cont { border-radius: 18px 6px 6px 18px; }
.ks-chat-other.ks-cont { border-radius: 6px 18px 18px 6px; }
.ks-chat-emoji { font-size: 2.6em; background: none; box-shadow: none; padding: 0 4px; }
.ks-chat-day { font-size: .78em; font-weight: 700; opacity: .65; padding: 3px 12px; border-radius: 99px;
  background: alpha(@window_fg_color, 0.07); margin: 8px 0 2px; }
.ks-chat-new { color: #ff5b5b; font-size: .78em; font-weight: 800; letter-spacing: .04em; }
.ks-chat-newline { background: alpha(#ff5b5b, 0.7); min-height: 1px; }
.ks-chat-time { font-size: .72em; opacity: .55; }
.ks-chat-name { font-size: .82em; font-weight: 700; }
.ks-chat-compact .ks-chat-me, .ks-chat-compact .ks-chat-other { padding: 3px 9px; border-radius: 9px; }
.ks-chat-compact .ks-chat-emoji { font-size: 1.6em; }
.ks-chat-jump { border-radius: 99px; padding: 4px 12px; margin: 10px; font-weight: 700;
  box-shadow: 0 4px 14px -4px alpha(black, 0.5); }
.ks-dnd { color: #ff9f43; font-weight: 700; font-size: .85em; }
.ks-pinbar { border-radius: 10px; padding: 4px 10px; background: alpha(@accent_bg_color, 0.14); }
.ks-playing { padding: 2px 0; }
.ks-playing button { border-radius: 99px; padding: 2px 10px; font-size: .85em; }
.ks-linkcard { border-radius: 12px; padding: 8px; background: alpha(@window_fg_color, 0.06);
  border-left: 3px solid @accent_bg_color; }
.ks-voice { border-radius: 18px; padding: 4px 10px 4px 4px; background: alpha(@window_fg_color, 0.07); }
.ks-chat-me + .ks-voice, .ks-voice.mine { background: alpha(@accent_bg_color, 0.30); }
.ks-gif-pick { padding: 0; border-radius: 8px; }
.ks-thumb { border-radius: 12px; }
window.ks-glass .ks-chat-other { background-color: alpha(@window_fg_color, 0.10); border: 1px solid alpha(white, 0.10); }
window.ks-glass .ks-chat-me { border: 1px solid alpha(white, 0.20); }
"""


def _bg(fn, done):
    def work():
        try:
            r = fn()
        except Exception as e:  # noqa: BLE001
            r = e
        GLib.idle_add(lambda: (done(r), False)[1])
    threading.Thread(target=work, daemon=True).start()


def _short_icon(icon, name):
    """Bare ikonet på serverstripa: «🎮Gaming» → «🎮», ingen emoji → forbokstaven i navnet."""
    lead = ""
    for ch in str(icon or ""):
        if ch.isalnum() or ch.isspace():
            break
        lead += ch
    return lead[:8] or (str(name or "?").strip()[:1].upper() or "?")


def _thumb(path, w, h, cover=False):
    """Bilde skalert ned (ellers ber et stort bilde om full bredde og strekker hele meldingen)."""
    try:
        from gi.repository import GdkPixbuf
        if cover:
            pb = GdkPixbuf.Pixbuf.new_from_file(path)
            k = max(w / pb.get_width(), h / pb.get_height())
            pb = pb.scale_simple(max(1, int(pb.get_width() * k)), max(1, int(pb.get_height() * k)),
                                 GdkPixbuf.InterpType.BILINEAR)
            pb = pb.new_subpixbuf((pb.get_width() - w) // 2, (pb.get_height() - h) // 2, w, h)
        else:
            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, w, h, True)
        pic = Gtk.Picture.new_for_paintable(Gdk.Texture.new_for_pixbuf(pb))
        pic.set_can_shrink(False)
        pic.add_css_class("ks-thumb")
        return pic
    except Exception:  # noqa: BLE001
        return None


def _dim(t):
    lab = Gtk.Label(label=i18n.tr(t), xalign=0, wrap=True)
    lab.add_css_class("dim-label")
    lab.add_css_class("caption")
    return lab


def _btn(label, cb, primary=False, flat=False):
    b = Gtk.Button(label=i18n.tr(label), valign=Gtk.Align.CENTER)
    b.add_css_class("flat" if flat else "pill")
    if primary:
        b.add_css_class("suggested-action")
    b.connect("clicked", cb)
    return b


def _ask(parent, heading, body, fields, on_ok, ok_label="OK"):
    """Liten dialog med tekstfelt. fields: [(nøkkel, plassholder, standard)]."""
    dlg = Adw.AlertDialog(heading=i18n.tr(heading), body=i18n.tr(body or ""))
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    ents = {}
    for k, ph, val in fields:
        e = Gtk.Entry(placeholder_text=i18n.tr(ph), text=val or "")
        ents[k] = e
        box.append(e)
    dlg.set_extra_child(box)
    dlg.add_response("nei", i18n.tr("Avbryt"))
    dlg.add_response("ja", i18n.tr(ok_label))
    dlg.set_response_appearance("ja", Adw.ResponseAppearance.SUGGESTED)
    dlg.connect("response", lambda _d, r: r == "ja" and on_ok({k: e.get_text().strip() for k, e in ents.items()}))
    dlg.present(parent)


class ChatPage(Gtk.Box):
    def __init__(self):
        super().__init__(spacing=0)
        try:
            import theme
            theme.add_css(_CSS)
            import chatvc_ui
            theme.add_css(chatvc_ui.CSS)
        except Exception:  # noqa: BLE001
            pass
        self.view = "direct"                 # «direct» eller server-ID
        self.room = "alle"
        self._rooms = []
        # ---- serverlist (rail) ----
        self.rail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.rail.add_css_class("ks-rail")
        rs = Gtk.ScrolledWindow(child=self.rail, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER,
                                propagate_natural_width=True)
        self.append(rs)
        # ---- kanaler / samtaler ----
        mid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, width_request=240, hexpand=False)
        for side in ("top", "bottom", "start", "end"):
            getattr(mid, f"set_margin_{side}")(10)
        head = Gtk.Box(spacing=6)
        self.head = Gtk.Label(xalign=0, hexpand=True, ellipsize=3)
        self.head.add_css_class("heading")
        head.append(self.head)
        self.gear = Gtk.MenuButton(icon_name="emblem-system-symbolic", valign=Gtk.Align.CENTER,
                                   tooltip_text=i18n.tr("Serverinnstillinger"))
        self.gear.add_css_class("flat")
        head.append(self.gear)
        mid.append(head)
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.list.add_css_class("navigation-sidebar")
        self.list.add_css_class("ks-chan")
        self.list.connect("row-selected", self._pick)
        self.list.connect("row-activated", self._activate)
        self._last_press = 0
        gp = Gtk.GestureClick(button=0, propagation_phase=Gtk.PropagationPhase.CAPTURE)
        gp.connect("pressed", lambda *_a: setattr(self, "_last_press", time.monotonic()))
        self.list.add_controller(gp)
        self._sig = None
        self._vc_labels = {}
        ls = Gtk.ScrolledWindow(child=self.list, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER,
                                propagate_natural_width=False)
        ls.set_size_request(240, -1)
        mid.append(ls)
        self.mid_hint = _dim("")
        self.mid_hint.set_max_width_chars(28)
        mid.append(self.mid_hint)
        import chatvc_ui
        self.status = _dim("")
        self.vcbar = chatvc_ui.VoiceBar(self.status, self._av_settings)
        mid.append(self.vcbar)
        self.append(mid)
        self.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        # ---- meldinger ----
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, hexpand=True)
        for side in ("top", "bottom", "start", "end"):
            getattr(right, f"set_margin_{side}")(12)
        th = Gtk.Box(spacing=8)
        self.title = Gtk.Label(xalign=0, hexpand=True, ellipsize=3)
        self.title.add_css_class("title-3")
        th.append(self.title)
        self.topic = _dim("")
        th.append(self.topic)
        self.mem_btn = Gtk.ToggleButton(icon_name="system-users-symbolic", tooltip_text=i18n.tr("Medlemmer"),
                                        valign=Gtk.Align.CENTER)
        self.mem_btn.add_css_class("flat")
        self.mem_btn.connect("toggled", lambda b: self.members_rev.set_reveal_child(b.get_active()))
        th.append(self.mem_btn)
        self.call_btn = Gtk.Button(label="📞", tooltip_text=i18n.tr("Ring (tale og webkamera – uten server)"),
                                   valign=Gtk.Align.CENTER, visible=False)
        self.call_btn.add_css_class("flat")
        self.call_btn.connect("clicked", lambda *_: self._call_room_now())
        th.append(self.call_btn)
        self.group_call_btn = Gtk.Button(label="👥📞", tooltip_text=i18n.tr("Gruppesamtale – velg hvem"),
                                         valign=Gtk.Align.CENTER, visible=False)
        self.group_call_btn.add_css_class("flat")
        self.group_call_btn.connect("clicked", lambda *_: self._group_call())
        th.append(self.group_call_btn)
        right.append(th)
        self.pinbar = Gtk.Button(visible=False, halign=Gtk.Align.FILL)        # 📌 festet melding øverst
        self.pinbar.add_css_class("ks-pinbar")
        self.pinbar.connect("clicked", lambda *_: self._pins_dialog())
        right.append(self.pinbar)
        self.playing = Gtk.Box(spacing=6, visible=False)                      # 🎮 hvem spiller nå (servere)
        self.playing.add_css_class("ks-playing")
        right.append(self.playing)
        self.callbar = Gtk.Box(spacing=8, visible=False)
        self.callbar.add_css_class("card")
        self.call_lab = Gtk.Label(xalign=0, hexpand=True, margin_start=12)
        self.callbar.append(self.call_lab)
        self._inc = None
        self.call_ans = _btn("📞 Svar", lambda *_: self._answer(self._inc) if self._inc else
                             self._call_do(CV.call_answer), True)
        self.callbar.append(self.call_ans)
        self.callbar.append(_btn("Avvis / legg på", lambda *_: (__import__("chatcall").decline(self._inc), self._bars())
                                 if self._inc else self._call_do(CV.call_end)))
        right.append(self.callbar)
        self.phonebar = Gtk.Box(spacing=8, visible=False)
        self.phonebar.add_css_class("card")
        self.phone_lab = Gtk.Label(xalign=0, hexpand=True, margin_start=12, ellipsize=3)
        self.phonebar.append(self.phone_lab)
        self.phonebar.append(_btn("Vis", lambda *_: __import__("phonecam").open_window(self.get_root()), flat=True))
        self.phonebar.append(_btn("Bruk i talekanalen", lambda *_: self._phone_to_voice(), flat=True))
        right.append(self.phonebar)
        self.video = chatvc_ui.VideoGrid()
        right.append(self.video)
        self.gamebar = Gtk.Box(spacing=8, visible=False)
        self.game_lab = _dim("")
        self.game_lab.set_hexpand(True)
        self.gamebar.append(self.game_lab)
        self.gamebar.append(_btn("Send til alle som spiller", self._to_players, flat=True))
        right.append(self.gamebar)
        self.msgs = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.scroll = Gtk.ScrolledWindow(child=self.msgs, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.msg_ov = Gtk.Overlay(child=self.scroll, vexpand=True)
        self.jump = Gtk.Button(label="↓ " + i18n.tr("Nye meldinger"), halign=Gtk.Align.CENTER,
                               valign=Gtk.Align.END, visible=False)
        self.jump.add_css_class("suggested-action")
        self.jump.add_css_class("ks-chat-jump")
        self.jump.connect("clicked", lambda *_: self._jump_new())
        self.msg_ov.add_overlay(self.jump)
        self.scroll.get_vadjustment().connect("value-changed", self._scrolled)
        self._bg_prov = Gtk.CssProvider()
        self.msg_ov.get_style_context().add_provider(self._bg_prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 5)
        self.msg_ov.add_css_class("ks-chat-area")
        self._newmark, self._seen, self._new_w, self._shown_room = {}, {}, None, None
        right.append(self.msg_ov)
        self.reply_bar = Gtk.Box(spacing=6, visible=False)
        self.reply_lab = _dim("")
        self.reply_lab.set_hexpand(True)
        self.reply_bar.append(self.reply_lab)
        self.reply_bar.append(_btn("✕", lambda *_: self._set_reply(None), flat=True))
        right.append(self.reply_bar)
        self.typing_lab = _dim("")
        right.append(self.typing_lab)
        row = Gtk.Box(spacing=6)
        self.emoji_btn = Gtk.MenuButton(label="😊", tooltip_text=i18n.tr("Emoji"), valign=Gtk.Align.CENTER)
        self.emoji_btn.add_css_class("flat")
        self.emoji_btn.set_popover(self._emoji_pop())
        row.append(self.emoji_btn)
        self.attach_btn = _btn("📎", self._attach, flat=True)
        self.attach_btn.set_tooltip_text(i18n.tr("Legg ved bilde, fil eller klipp"))
        row.append(self.attach_btn)
        self.mic_btn = _btn("🎙️", self._voice, flat=True)
        self.mic_btn.set_tooltip_text(i18n.tr("Talemelding: trykk for å starte, trykk igjen for å sende"))
        row.append(self.mic_btn)
        self.walkie_btn = _btn("📢", self._walkie, flat=True)
        self.walkie_btn.set_tooltip_text(i18n.tr("Walkie-talkie: trykk og snakk, trykk igjen – spilles av med en gang hos "
                                                 "de andre"))
        row.append(self.walkie_btn)
        self.entry = Gtk.Entry(placeholder_text=i18n.tr("Skriv en melding …"), hexpand=True, max_length=2000)
        self.entry.connect("activate", self._send)
        pk = Gtk.EventControllerKey()
        pk.connect("key-pressed", self._paste_key)
        self.entry.add_controller(pk)
        self.entry.connect("changed", lambda e: self.room.startswith("s:") and e.get_text() and
                           threading.Thread(target=CP.typing, args=(self.room,), daemon=True).start())
        row.append(self.entry)
        self._quick_items = CL.cfg()["quick"] + ["🆘 Hjelp", "🍕 Sulten"]
        self.quick_dd = Gtk.DropDown.new_from_strings(["⚡"] + self._quick_items)
        self.quick_dd.set_tooltip_text(i18n.tr("Hurtigsvar"))
        self.quick_dd.set_valign(Gtk.Align.CENTER)
        self.quick_dd.connect("notify::selected", self._quick_pick)
        row.append(self.quick_dd)
        more = Gtk.MenuButton(label="⋯", tooltip_text=i18n.tr("Mer: avstemning, avtale, påminnelse …"),
                              valign=Gtk.Align.CENTER)
        more.add_css_class("flat")
        more.set_popover(self._more_pop())
        row.append(more)
        row.append(_btn("Send", self._send, True))
        right.append(row)
        right.append(self.status)
        self.append(right)
        # ---- medlemmer ----
        self.members = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, width_request=200)
        for side in ("top", "bottom", "start", "end"):
            getattr(self.members, f"set_margin_{side}")(12)
        self.members_rev = Gtk.Revealer(child=self.members, transition_type=Gtk.RevealerTransitionType.SLIDE_LEFT)
        self.append(self.members_rev)
        self.reply_to = None
        self._parts = [c for c in self._children()]
        self.gate = self._gate_box()
        self.append(self.gate)
        self.connect("map", lambda *_: self._gate_check())
        C.on_message(lambda room, m: (room == self.room and (self._typing() if m.get("event") == "typing"
                                                             else self._load()), m.get("event") or self._rail()))
        CS.on_change(lambda sid: (self._rail(), sid == self.view and self._channels()))
        self._rail()
        self._channels(select=True)
        GLib.timeout_add_seconds(15, lambda: (self.get_mapped() and (self._channels(), self._load()), True)[1])
        import chatvc
        chatvc.on_change(self._vc_changed)
        __import__("chatcall").on_change(lambda: (self._bars(), self.view == "direct" and self._channels()))
        GLib.timeout_add_seconds(2, lambda: (self.get_mapped() and self._bars(), True)[1])
        CS.on_change(lambda _sid: self._bars())

    def _children(self):
        out, c = [], self.get_first_child()
        while c is not None:
            out.append(c)
            c = c.get_next_sibling()
        return out

    def _gate_box(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, hexpand=True, vexpand=True,
                      valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER, visible=False)
        icon = Gtk.Label(label="🔒")
        icon.add_css_class("title-1")
        box.append(icon)
        t = Gtk.Label(label=i18n.tr("Installer Tailscale først"))
        t.add_css_class("title-2")
        box.append(t)
        d = Gtk.Label(label=i18n.tr("Chatten går over Tailscale – et gratis, privat nettverk mellom PC-ene og vennene "
                                    "dine. Installer det, logg inn, og kom tilbake hit."), wrap=True,
                      max_width_chars=50, justify=Gtk.Justification.CENTER)
        d.add_css_class("dim-label")
        box.append(d)
        self.gate_msg = _dim("")
        self.gate_msg.set_halign(Gtk.Align.CENTER)
        row = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
        row.append(_btn("Installer Tailscale", lambda *_: self._ts_install(), True))
        row.append(_btn("Jeg har logget inn – sjekk igjen", lambda *_: self._gate_check(force=True)))
        box.append(row)
        box.append(self.gate_msg)
        return box

    def _ts_install(self):
        self.gate_msg.set_label(i18n.tr("Installerer …"))

        def work():
            import apps
            apps.install("tailscale")
            return i18n.tr("Installert – start Tailscale og logg inn (gratis konto), så trykk «sjekk igjen»")
        _bg(work, lambda r: self.gate_msg.set_label(("✗ " if isinstance(r, Exception) else "") + str(r)))

    def _gate_check(self, force=False):
        if force:
            C._TS["t"] = 0

        def done(st):
            ok = not isinstance(st, Exception) and st.get("running")
            for c in self._parts:
                c.set_visible(bool(ok) if c is not self.members_rev else bool(ok))
            self.gate.set_visible(not ok)
            if not ok and not isinstance(st, Exception) and st.get("installed"):
                self.gate_msg.set_label(i18n.tr("Tailscale er installert, men ikke pålogget – åpne Tailscale og logg "
                                                "inn."))
        _bg(C.tailscale, done)
        return False

    # ------------------------------------------------------------------ serverlist
    def _rail(self):
        while (c := self.rail.get_first_child()) is not None:
            self.rail.remove(c)

        def add(icon, tip, cb, on=False):
            b = Gtk.Button(label=icon, tooltip_text=i18n.tr(tip))
            if on:
                b.add_css_class("ks-on")
            b.connect("clicked", lambda *_: cb())
            self.rail.append(b)
        add("💬", "Direkte: hjemme, alle og privat", lambda: self._open("direct"), self.view == "direct")
        self.rail.append(Gtk.Separator())
        for sid, srv in sorted(CS.visible_servers().items(), key=lambda kv: kv[1].get("created", 0)):
            add(_short_icon(srv.get("icon"), srv.get("name", "Server")), srv.get("name", "Server"),
                lambda s=sid: self._open(s), self.view == sid)
        self.rail.append(Gtk.Separator())
        add("➕", "Lag en server", self._create)
        add("🔗", "Bli med i en server (lim inn invitasjonslenke)", self._join)
        add("🔍", "Søk i alle samtalene", self._search)
        add("👤", "Profil, status og chat-innstillinger", self._profile)
        add("🎛️", "Lyd og video: mikrofon, høyttaler og webkamera", self._av_settings)
        add("📱", "Mobilkamera: bruk mobilen som webkamera", self._phonecam)
        return False

    def _open(self, view):
        self.view = view
        self._rail()
        self._channels(select=True)

    # ------------------------------------------------------------------ kanaler
    def _channels(self, select=False, force=False):
        """force: bygg med en gang (et trykk i selve lista, f.eks. «Må oppdateres»)."""
        if self.view == "direct":
            self._vc_labels = {}
            self.head.set_label(i18n.tr("Direkte"))
            self.gear.set_visible(False)
            self.mem_btn.set_visible(False)
            self.members_rev.set_reveal_child(False)
            self.mid_hint.set_label(i18n.tr("Venner legges til under PC-er utenfor hjemmet. Bare vennene dine kan "
                                            "skrive til deg."))

            pins = tuple(CP.cfg()["pinned_rooms"])

            def load():
                import chatcall
                calls = [(sid, chid, name, tuple((p["id"], p["name"], p["mute"], p["cam"] and (p.get("vmode") or True))
                                                 for p in ppl)) for sid, chid, name, ppl in chatcall.active()]
                return C.room_groups(pins), calls

            def done(res):
                if isinstance(res, Exception):
                    return
                groups, calls = res
                sig = ("direct", tuple((g, tuple(rs)) for g, rs in groups), tuple(calls))
                if self.view != "direct" or (not select and not force and (
                        sig == self._sig or time.monotonic() - self._last_press < 1.5)):
                    return
                self._sig = sig
                self._rooms = [(rid, name, icon, unread) for _g, rs in groups for rid, name, icon, unread, _n in rs]
                self._building = True
                self._vc_labels = {}
                while (c := self.list.get_first_child()) is not None:
                    self.list.remove(c)

                def header(title):
                    lab = Gtk.Label(label=i18n.tr(title).upper(), xalign=0)
                    lab.add_css_class("ks-chan-cat")
                    hr = Gtk.ListBoxRow(child=lab, selectable=False, activatable=False)
                    hr.add_css_class("ks-cat-row")
                    self.list.append(hr)
                if calls:                                   # samtaler uten server (📞)
                    header("Samtaler")
                    for sid, chid, name, people in calls:
                        self._row(f"s:{sid}:{chid}", f"🔊  {name.lstrip('📞 ')}", 0, voice=True,
                                  extra=self._leave_btn("✕", "Legg på og fjern samtalen",
                                                        lambda s_=sid: __import__("chatcall").forget(s_)))
                        for pid, pname, pmute, pcam in people:
                            cam = f"  📷 {pcam}" if isinstance(pcam, str) else "  📷" if pcam else ""
                            pl = Gtk.Label(label=f"{'🔇' if pmute else '🎙️'} {pname}{cam}", xalign=0, ellipsize=3)
                            pl.add_css_class("ks-vc-user")
                            self._vc_labels[pid] = pl
                            pr = Gtk.ListBoxRow(child=pl, selectable=False, activatable=False)
                            pr.add_css_class("ks-vc-row")
                            self.list.append(pr)
                for title, rs in groups:
                    if title == "Må oppdateres":            # egen undermeny, lukket som standard
                        open_ = getattr(self, "_old_open", False)
                        tb = Gtk.Button(label=("▾ " if open_ else "▸ ") + i18n.tr("Må oppdateres").upper() +
                                        f" ({len(rs)})", halign=Gtk.Align.START)
                        tb.add_css_class("flat")
                        tb.add_css_class("ks-chan-cat")
                        tb.set_tooltip_text(i18n.tr("PC-er med for gammel Kontrollsenter – oppdater dem for å chatte"))
                        tb.connect("clicked", lambda *_: (setattr(self, "_old_open", not getattr(self, "_old_open",
                                                                                                  False)),
                                                          self._channels(force=True)))
                        hr = Gtk.ListBoxRow(child=tb, selectable=False, activatable=False)
                        hr.add_css_class("ks-cat-row")
                        self.list.append(hr)
                        if not open_:
                            continue
                    else:
                        header(title)
                    for rid, name, icon, unread, note in rs:
                        self._row(rid, f"{icon}  {name}", unread, note=note)
                ids = [r[0] for r in self._rooms]
                if select and (self.room not in ids):
                    self.room = "alle"
                self._select_current()
                self._building = False
                self._vc_speak()
                if select:
                    self._load()
            _bg(load, done)
            return
        srv = CS.get(self.view)
        if not srv:
            self._open("direct")
            return
        self._building = True
        import chatvc
        read = (C._load(C.FILE, {}).get("_read") or {})
        manage = CS.can_manage(srv)
        layout = []
        for cat in srv.get("categories", []):
            chans = []
            for ch in cat.get("channels", []):
                rid = f"s:{srv['id']}:{ch['id']}"
                unread = sum(1 for m in C.messages(rid, 100) if m.get("t", 0) > read.get(rid, 0)
                             and m.get("from_id") != CS.me()["id"])
                voice = ch.get("kind") == "voice"
                people = tuple((p["id"], p["name"], p["mute"], p["deaf"], p["cam"] and (p.get("vmode") or True))
                               for p in chatvc.roster(srv["id"], ch["id"])) if voice else ()
                chans.append((rid, ch["name"], voice, unread, CS.muted(rid), people))
            layout.append((cat["id"], cat["name"], tuple(chans)))
        sig = (srv["id"], srv.get("v"), manage, tuple(layout), srv.get("name"), srv.get("icon"), chatvc.current())
        # bygg bare om når noe faktisk er endret – og aldri rett etter et klikk (da forsvant klikket)
        if not select and not force and sig == self._sig:
            self._building = False
            return
        if not select and not force and time.monotonic() - self._last_press < 1.5:
            self._building = False
            GLib.timeout_add(1600, lambda: (self._channels(), False)[1])
            return
        self._sig = sig
        while (c := self.list.get_first_child()) is not None:
            self.list.remove(c)
        self.head.set_label(f"{_short_icon(srv.get('icon'), srv['name'])} {srv['name']}")
        self.gear.set_visible(True)
        self.gear.set_popover(self._server_menu(srv))
        self.mem_btn.set_visible(True)
        self.mid_hint.set_label("")
        self._vc_labels = {}
        first = None
        for cid, cname, chans in layout:
            hb = Gtk.Box(spacing=2)
            lab = Gtk.Label(label=cname.upper(), xalign=0, hexpand=True, ellipsize=3)
            lab.add_css_class("ks-chan-cat")
            hb.append(lab)
            if manage:
                add = Gtk.MenuButton(icon_name="list-add-symbolic", tooltip_text=i18n.tr("Ny kanal i ") + cname,
                                     valign=Gtk.Align.END)
                add.add_css_class("flat")
                add.add_css_class("ks-cat-add")
                add.set_popover(self._cat_menu(srv["id"], cid, cname))
                hb.append(add)
            r = Gtk.ListBoxRow(child=hb, selectable=False, activatable=False)
            r.add_css_class("ks-cat-row")
            self.list.append(r)
            if not chans and manage:
                hint = _dim("Tom – trykk + for å legge til en kanal")
                hint.add_css_class("caption")
                hint.set_margin_start(8)
                hr = Gtk.ListBoxRow(child=hint, selectable=False, activatable=False)
                hr.add_css_class("ks-vc-row")
                self.list.append(hr)
            for rid, name, voice, unread, muted, people in chans:
                if not voice:
                    first = first or rid
                here = voice and chatvc.current() == (srv["id"], rid.split(":")[2])
                self._row(rid, ("🔊  " if voice else "#  ") + name + ("  🔕" if muted else ""), unread, voice=voice,
                          extra=self._leave_btn(i18n.tr("Forlat"), "Forlat talekanalen", chatvc.leave) if here else None)
                for pid, pname, pmute, pdeaf, pcam in people:
                    cam = f"  📷 {pcam}" if isinstance(pcam, str) else "  📷" if pcam else ""
                    pl = Gtk.Label(label=f"{'🔇' if pmute or pdeaf else '🎙️'} {CP.display(pname, pid)}{cam}",
                                   xalign=0, ellipsize=3)
                    pl.add_css_class("ks-vc-user")
                    self._vc_labels[pid] = pl
                    pr = Gtk.ListBoxRow(child=pl, selectable=False, activatable=False)
                    pr.add_css_class("ks-vc-row")
                    self.list.append(pr)
        if not first:
            first = next((c[0] for _i, _n, chans in layout for c in chans), None)
        if select or not self.room.startswith(f"s:{srv['id']}:"):
            self.room = first or self.room
        self._select_current()
        self._show_members(srv)
        self._building = False
        self._vc_speak()
        if select:
            self._load()

    def _leave_btn(self, label, tip, fn):
        b = Gtk.Button(label=label, tooltip_text=i18n.tr(tip))
        b.add_css_class("flat")
        b.add_css_class("ks-react")
        b.connect("clicked", lambda *_: _bg(fn, lambda res: (self.status.set_label(
            ("✗ " if isinstance(res, Exception) else "") + str(res)), self.vcbar.refresh(), self._channels(force=True))))
        return b

    def _vc_changed(self, what):
        if what == "speak":
            self._vc_speak()
        elif what in ("roster", "error") and self.view != "direct":
            self._channels()
        return False

    def _vc_speak(self):
        import chatvc
        cur = chatvc.current()
        speaking = {p["id"] for p in chatvc.roster(*cur) if p["speaking"]} if cur else set()
        for pid, lab in self._vc_labels.items():
            (lab.add_css_class if pid in speaking else lab.remove_css_class)("speaking")
        if speaking:
            GLib.timeout_add(700, lambda: (self._vc_speak(), False)[1])

    def _cat_menu(self, sid, cid, cname):
        pop = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=6, margin_bottom=6, margin_start=6,
                      margin_end=6)
        for label, fn in (("# Ny tekstkanal", lambda: self._new_channel("text", cid)),
                          ("🔊 Ny talekanal", lambda: self._new_channel("voice", cid)),
                          ("✏️ Gi kategorien nytt navn", lambda: _ask(
                              self.get_root(), "Kategori", "", [("n", "Navn", cname)],
                              lambda v: self._call(lambda: CS.rename_category(sid, cid, v["n"])), "Lagre")),
                          ("🗑️ Slett kategorien", lambda: self._confirm(
                              f"Slette «{cname}» og kanalene i den?",
                              lambda: self._call(lambda: CS.delete_category(sid, cid))))):
            b = Gtk.Button(label=i18n.tr(label))
            b.add_css_class("flat")
            b.get_child().set_xalign(0)
            b.connect("clicked", lambda _b, f=fn: (pop.popdown(), f()))
            box.append(b)
        pop.set_child(box)
        return pop

    def _phone_to_voice(self):
        import chatvc
        chatvc.set_(camera="phone")
        if chatvc.current() and not chatvc.state()["cam"]:
            _bg(chatvc.toggle_camera, lambda r: (self.status.set_label(
                ("✗ " + str(r)) if isinstance(r, Exception) else "📷 Mobilkameraet vises nå i talekanalen"),
                self.vcbar.refresh()))
        else:
            self.status.set_label(i18n.tr("📱 Mobilkameraet er valgt – trykk 📷 i talelinjen når du er i en talekanal"))

    def _phonecam(self):
        import phonecam
        dlg = Adw.AlertDialog(heading=i18n.tr("📱 Mobilen som webkamera"))
        dlg.set_body(i18n.tr("1. Åpne Kontrollsenter-appen på mobilen (Android, versjon 0.90 eller nyere).\n"
                             "2. Gå til Chat og trykk «📷 Kamera».\n"
                             "3. Gi appen lov til å bruke kameraet – bildet kommer hit.\n\n") + phonecam.status())
        dlg.add_response("lukk", i18n.tr("Lukk"))
        dlg.add_response("vindu", i18n.tr("Vis i vindu"))
        dlg.add_response("tale", i18n.tr("Bruk i talekanalen"))
        import sys as _sys
        if _sys.platform != "win32" and phonecam.loopback_devices():
            dlg.add_response("virt", i18n.tr("Slå av webkamera for andre programmer") if phonecam.virtual_on()
                             else i18n.tr("Webkamera for andre programmer"))
        dlg.set_response_appearance("tale", Adw.ResponseAppearance.SUGGESTED)

        def resp(_d, r):
            if r == "vindu":
                phonecam.open_window(self.get_root())
            elif r == "tale":
                self._phone_to_voice()
            elif r == "virt":
                try:
                    self.status.set_label(phonecam.set_virtual(not phonecam.virtual_on()))
                except Exception as e:  # noqa: BLE001
                    self.status.set_label(f"✗ {e}")
        dlg.connect("response", resp)
        dlg.present(self.get_root())

    def _av_settings(self):
        import chatvc_ui
        chatvc_ui.open_settings(self.get_root())

    def _row(self, rid, text, unread, voice=False, note="", extra=None):
        r = Gtk.Box(spacing=8)
        if note:
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            col.append(Gtk.Label(label=text, xalign=0, ellipsize=3))
            nl = Gtk.Label(label=note, xalign=0, ellipsize=3)
            nl.add_css_class("caption")
            nl.add_css_class("warning")
            col.append(nl)
            r.append(col)
        else:
            r.append(Gtk.Label(label=text, xalign=0, hexpand=True, ellipsize=3))
        if unread:
            u = Gtk.Label(label=str(unread))
            u.add_css_class("ks-chip")
            r.append(u)
        if extra is not None:
            extra.set_valign(Gtk.Align.CENTER)
            r.append(extra)
        row = Gtk.ListBoxRow(child=r)
        row._rid = rid
        row._voice = voice
        if voice:
            row.set_tooltip_text(i18n.tr("Trykk for å gå inn i talekanalen"))
        if rid.startswith("p:") or rid in ("alle", "hjemme", "meg"):
            g = Gtk.GestureClick(button=3)
            g.connect("pressed", lambda *_a, rr=rid, w=row: self._room_menu(w, rr))
            row.add_controller(g)
        self.list.append(row)

    def _member_menu(self, widget, m):
        pop = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=6, margin_bottom=6, margin_start=6,
                      margin_end=6)
        items = [("✏️ Gi kallenavn …", lambda: self._nick_dialog(name=m.get("name"), mid=m.get("id")), True),
                 ("📞 Ring med tale", lambda: self._call_do(lambda: CV.call_start(m, self.room)), CV.calls_ok()),
                 ("🎵 Egen varsellyd …", lambda: self._pick_sound(m.get("name")), True),
                 ("🚫 Blokker", lambda: CL.block(m.get("name")), True)]
        for label, fn, ok in items:
            if ok:
                b = Gtk.Button(label=i18n.tr(label))
                b.add_css_class("flat")
                b.connect("clicked", lambda _b, f=fn: (pop.popdown(), f()))
                box.append(b)
        pop.set_child(box)
        pop.set_parent(widget)
        pop.connect("closed", lambda p: GLib.idle_add(p.unparent))
        pop.popup()

    def _room_menu(self, widget, rid):
        pop = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=6, margin_bottom=6, margin_start=6,
                      margin_end=6)
        pins = CP.cfg()["pinned_rooms"]
        items = [("📌 Løsne" if rid in pins else "📌 Fest øverst", lambda: CP.set_(
            pinned_rooms=[x for x in pins if x != rid] if rid in pins else pins + [rid]))]
        items.append(("🎨 Bakgrunn …", lambda: self._bg_dialog(rid)))
        if rid.startswith("p:"):
            name = rid[2:]
            items += [("✏️ Gi kallenavn …", lambda: self._nick_dialog(name=name)),
                      ("🔕 Demp 1 time / av", lambda: CS.set_mute(rid, 0 if CS.muted(rid) else 3600)),
                      ("🎵 Egen varsellyd …", lambda: self._pick_sound(name)),
                      ("🚫 Blokker", lambda: CL.block(name))]
        for label, fn in items:
            b = Gtk.Button(label=i18n.tr(label))
            b.add_css_class("flat")
            b.connect("clicked", lambda _b, f=fn: (pop.popdown(), f(), self._channels()))
            box.append(b)
        pop.set_child(box)
        pop.set_parent(widget)
        pop.connect("closed", lambda p: GLib.idle_add(p.unparent))
        pop.popup()

    def _nick_dialog(self, name=None, mid=None):
        """Ditt eget navn på personen (bare hos deg). Tomt = bruk det vanlige navnet igjen."""
        dlg = Adw.AlertDialog(heading=i18n.tr("Gi kallenavn"),
                              body=i18n.tr("Bare du ser kallenavnet. La feltet stå tomt for å bruke «{}» igjen.")
                              .format(name or "?"))
        e = Gtk.Entry(text=CP.nick(name, mid) or "", placeholder_text=name or "", activates_default=True)
        dlg.set_extra_child(e)
        dlg.add_response("nei", i18n.tr("Avbryt"))
        dlg.add_response("ja", i18n.tr("Lagre"))
        dlg.set_default_response("ja")
        dlg.set_response_appearance("ja", Adw.ResponseAppearance.SUGGESTED)

        def save():
            v = CP.set_nick(name=name, mid=mid, value=e.get_text())
            self.status.set_label(i18n.tr("Kallenavn: ") + v if v else i18n.tr("Kallenavnet er fjernet"))
            self._sig = None
            self._channels(force=True)
            self._load()
            srv = CS.get(self.view) if self.view != "direct" else None
            if srv:
                self._show_members(srv)
        dlg.connect("response", lambda _d, r: r == "ja" and save())
        dlg.present(self.get_root())
        e.grab_focus()

    def _pick_sound(self, name):
        dlg = Gtk.FileDialog(title=i18n.tr("Varsellyd for ") + name)

        def done(d, res):
            try:
                f = d.open_finish(res)
            except GLib.Error:
                return
            snd = CP.cfg()["sounds"]
            snd[name] = f.get_path()
            CP.set_(sounds=snd)
            self.status.set_label(f"🎵 Egen lyd for {name}")
        dlg.open(self.get_root(), None, done)

    def _select_current(self):
        row = self.list.get_first_child()
        while row is not None:
            if getattr(row, "_rid", None) == self.room:
                self.list.select_row(row)
                break
            row = row.get_next_sibling()

    def _pick(self, _l, row):
        if row is None or getattr(self, "_building", False) or not getattr(row, "_rid", None):
            return
        if row._rid != self.room:
            self.room = row._rid
            self._load()

    def _activate(self, _l, row):
        """Klikk på en kanal (også en som allerede er valgt): åpne den – talekanal: gå inn i talen."""
        if row is None or not getattr(row, "_rid", None):
            return
        if row._rid != self.room:
            self.room = row._rid
            self._load()
        if getattr(row, "_voice", False):
            import chatvc
            _x, sid, ch = row._rid.split(":", 2)
            if chatvc.current() != (sid, ch):
                self.status.set_label(i18n.tr("Kobler til talekanalen …"))
                _bg(lambda: chatvc.join(sid, ch),
                    lambda r: (self.status.set_label(("✗ " if isinstance(r, Exception) else "") + str(r)),
                               self.vcbar.refresh()))

    def _show_members(self, srv):
        while (c := self.members.get_first_child()) is not None:
            self.members.remove(c)
        h = Gtk.Label(label=i18n.tr("MEDLEMMER") + f" – {len(srv.get('members', {}))}", xalign=0)
        h.add_css_class("ks-chan-cat")
        self.members.append(h)
        order = {"owner": 0, "admin": 1, "member": 2}
        for mid, m in sorted(srv.get("members", {}).items(), key=lambda kv: (order.get(kv[1].get("role"), 3),
                                                                             kv[1].get("name", ""))):
            badge = {"owner": "👑 ", "admin": "🛡️ "}.get(m.get("role"), "")
            icon, what = CL.presence(mid)
            av, _col = CL.avatar(mid)
            row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            row.append(Gtk.Label(label=f"{icon} {av + ' ' if av else ''}{badge}{CP.display(m.get('name', '?'), mid)}" +
                                 (" (deg)" if mid == CS.me()["id"] else ""), xalign=0, ellipsize=3))
            sub = _dim(what)
            sub.set_margin_start(22)
            row.append(sub)
            if mid != CS.me()["id"]:
                g = Gtk.GestureClick(button=3)
                g.connect("pressed", lambda *_a, mm=m, w=row: self._member_menu(w, mm))
                row.add_controller(g)
            self.members.append(row)

    # ------------------------------------------------------------------ meldinger
    def _load(self):
        room = self.room
        try:                                                # chat.py: ikke varsle for rommet du ser på
            self.get_root()._chat_room = room
        except Exception:  # noqa: BLE001
            pass
        if room.startswith("s:"):
            srv = CS.get(room.split(":")[1]) or {}
            ch = CS.channel(srv, room.split(":")[2]) or {}
            self.title.set_label(f"{'🔊' if ch.get('kind') == 'voice' else '#'} {ch.get('name', '?')}")
            self.topic.set_label(ch.get("topic", ""))
        else:
            self.title.set_label(CP.display(room[2:]) if room.startswith("p:") else
                                 next((n for r, n, _i, _u in self._rooms if r == room), room))
            self.topic.set_label("")

        def work():
            m = C.messages(room, 150)
            if room not in self._newmark:                   # «Nye meldinger»-streken: der du slapp sist
                try:
                    rd = C._load(C.FILE, {}).get("_read", {})
                    self._newmark[room] = max([rd.get(a, 0) for a in C.aliases(room)] or [0])
                except Exception:  # noqa: BLE001
                    self._newmark[room] = 0
            if room.startswith("p:") and time.time() - getattr(self, "_rdp", {}).get(room, 0) > 20 and any(
                    mm.get("t", 0) > self._newmark.get(room, 0) and mm.get("pc") != C._me() for mm in m):
                self.__dict__.setdefault("_rdp", {})[room] = time.time()
                try:
                    C.send_event(room, {"type": "read", "t": time.time()})
                except Exception:  # noqa: BLE001
                    pass
            C.mark_read(room)
            if room.startswith("s:") and time.time() - getattr(self, "_rd", {}).get(room, 0) > 20:
                self.__dict__.setdefault("_rd", {})[room] = time.time()
                CP.mark_read(room)
            return m
        _bg(work, lambda msgs: self._show(room, msgs))
        return False

    def _avatar(self, name, mid, size):
        """Rundt profilbilde: emoji fra profilen eller initialer i personens faste farge, med pålogget-prikk."""
        import chatlook as LK
        emo, colr = CL.avatar(mid) if mid else ("", "")
        colr = colr or LK.color_for(name)
        dot = None
        if mid:
            ic, _t = CL.presence(mid)
            dot = {"🟢": (0.18, 0.8, 0.44), "🎮": (1.0, 0.62, 0.26)}.get(ic)
        da = Gtk.DrawingArea(content_width=size, content_height=size, valign=Gtk.Align.START, margin_top=2)
        rgba = Gdk.RGBA()
        rgba.parse(colr)
        label = emo or LK.initials(name)

        def draw(_a, cr, w, h):
            import math
            cr.arc(w / 2, h / 2, min(w, h) / 2, 0, 2 * math.pi)
            cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, 0.95 if not emo else 0.30)
            cr.fill()
            from gi.repository import Pango, PangoCairo
            lay = PangoCairo.create_layout(cr)
            fd = Pango.FontDescription.from_string(f"Sans Bold {max(6, int(size * (0.48 if emo else 0.36)))}px")
            lay.set_font_description(fd)
            lay.set_text(label, -1)
            tw, th = lay.get_pixel_size()
            cr.move_to((w - tw) / 2, (h - th) / 2)
            cr.set_source_rgb(1, 1, 1)
            PangoCairo.show_layout(cr, lay)
            if dot:
                r_ = max(3, size * 0.15)
                cr.arc(w - r_, h - r_, r_ + 1.5, 0, 2 * math.pi)
                cr.set_source_rgb(0.1, 0.1, 0.12)
                cr.fill()
                cr.arc(w - r_, h - r_, r_, 0, 2 * math.pi)
                cr.set_source_rgb(*dot)
                cr.fill()
        da.set_draw_func(draw)
        da.set_tooltip_text(name)
        return da

    def _set_room_bg(self, room):
        import chatlook as LK
        key = CP.cfg().get("room_bg", {}).get(room, "")
        css = ".ks-chat-area { background: none; }"
        if key.startswith("bilde:"):
            path = key[6:].replace('"', "")
            css = (f'.ks-chat-area {{ background: linear-gradient(alpha(@window_bg_color,0.55), '
                   f'alpha(@window_bg_color,0.55)), url("file://{path}"); background-size: cover; '
                   f'background-position: center; }}')
        elif key in LK.BACKGROUNDS and key:
            css = f".ks-chat-area {{ background: {LK.BACKGROUNDS[key][1]}; }}"
        self._bg_prov.load_from_data(css.encode())

    def _scrolled(self, adj):
        if adj.get_value() + adj.get_page_size() >= adj.get_upper() - 40:
            self.jump.set_visible(False)

    def _jump_new(self):
        w = self._new_w
        adj = self.scroll.get_vadjustment()
        if w is not None and w.get_parent() is not None:
            ok, pt = w.compute_point(self.msgs, Graphene.Point())
            if ok:
                adj.set_value(max(0, pt.y - 40))
                self._new_w = None
                self.jump.set_label("↓ " + i18n.tr("Til bunnen"))
                return
        adj.set_value(adj.get_upper())
        self.jump.set_visible(False)

    def _show(self, room, msgs):
        if isinstance(msgs, Exception) or room != self.room:
            return
        import chatlook as LK
        same_room = self._shown_room == room
        seen_before = self._seen.get(room, set()) if same_room else None
        self._shown_room = room
        self._set_room_bg(room)
        compact = CP.cfg().get("compact")
        (self.msgs.add_css_class if compact else self.msgs.remove_css_class)("ks-chat-compact")
        self.msgs.set_spacing(2 if compact else 3)
        while (c := self.msgs.get_first_child()) is not None:
            self.msgs.remove(c)
        if not msgs:
            e = Gtk.Label(label=i18n.tr("Ingen meldinger her ennå – si hei! 👋"), vexpand=True)
            e.add_css_class("dim-label")
            self.msgs.append(e)
        import savegames
        me_pc, me_id = savegames.pc_name(), CS.me()["id"]
        by_id = {m.get("id"): m for m in msgs}
        mark = self._newmark.get(room, 0)
        new_w, last_day, prev = None, None, None
        av_size = 22 if compact else 32
        for m in msgs:
            t = m.get("t", 0)
            day = LK.day_label(t)
            if day != last_day:                              # datoskiller
                dl = Gtk.Label(label=i18n.tr(day), halign=Gtk.Align.CENTER)
                dl.add_css_class("ks-chat-day")
                self.msgs.append(dl)
                last_day, prev = day, None
            if str(m.get("from", "")).startswith("🤖"):
                lab = Gtk.Label(label=m.get("text", ""), xalign=0.5, wrap=True)
                lab.add_css_class("ks-chat-sys")
                lab.add_css_class("caption")
                self.msgs.append(lab)
                prev = None
                continue
            mine = m.get("from_id") == me_id or (not m.get("from_id") and (m.get("pc") == me_pc or
                                                                            m.get("from") == me_pc))
            if not mine and mark and t > mark and new_w is None and not same_room:   # «Nye meldinger»
                nl = Gtk.Box(spacing=8, margin_top=6)
                for side in (0, 1):
                    ln = Gtk.Box(hexpand=True, valign=Gtk.Align.CENTER)
                    ln.add_css_class("ks-chat-newline")
                    nl.append(ln)
                    if side == 0:
                        tl = Gtk.Label(label=i18n.tr("NYE MELDINGER"))
                        tl.add_css_class("ks-chat-new")
                        nl.append(tl)
                self.msgs.append(nl)
                new_w, prev = nl, None
            sender = m.get("from_id") or m.get("pc") or m.get("from")
            cont = (prev is not None and prev[0] == sender and t - prev[1] < 300)   # samme person rett etter
            prev = (sender, t)
            name = (CP.display(m.get("pc") or m.get("from"), m.get("from_id"))
                    if CP.nick(m.get("pc") or m.get("from"), m.get("from_id")) else m.get("from"))
            outer = Gtk.Box(spacing=8, halign=Gtk.Align.END if mine else Gtk.Align.START,
                            margin_top=0 if cont else (2 if compact else 6))
            if not mine:
                if cont:
                    outer.append(Gtk.Box(width_request=av_size))
                else:
                    av_w = self._avatar(name, m.get("from_id"), av_size)
                    av_w.set_margin_top(18 if not compact else 14)      # på høyde med første boble
                    outer.append(av_w)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2,
                          halign=Gtk.Align.END if mine else Gtk.Align.START)
            outer.append(col)
            stamp = time.strftime("%H:%M", time.localtime(t))
            extra = (("  · " + i18n.tr("redigert")) if m.get("edited") else "") + ("  📌" if m.get("pinned") else "") + \
                ("  🔒" if m.get("e2e") else "")
            if not cont:
                hb = Gtk.Box(spacing=6, halign=Gtk.Align.END if mine else Gtk.Align.START)
                if not mine:
                    nm = Gtk.Label(label=name, xalign=0)
                    nm.add_css_class("ks-chat-name")
                    nm.set_markup(f'<span foreground="{LK.color_for(name)}">{GLib.markup_escape_text(name)}</span>')
                    hb.append(nm)
                tm = Gtk.Label(label=stamp + extra)
                tm.add_css_class("ks-chat-time")
                hb.append(tm)
                col.append(hb)
            elif extra:
                tm = Gtk.Label(label=extra.strip(), xalign=1 if mine else 0)
                tm.add_css_class("ks-chat-time")
                col.append(tm)
            if m.get("reply") and by_id.get(m["reply"]):
                q = by_id[m["reply"]]
                ql = _dim(f"↪ {q.get('from')}: {str(q.get('text', ''))[:60]}")
                col.append(ql)
            text = i18n.tr("(slettet)") if m.get("deleted") else CL.clean(m.get("text", ""))
            t_ = Gtk.Label(label=text, wrap=True, xalign=0, selectable=True, max_width_chars=60,
                           tooltip_text=time.strftime("%d.%m.%Y %H:%M", time.localtime(t)))
            big = not m.get("deleted") and LK.emoji_count(text)
            att_k = (m.get("attach") or {}).get("kind")
            auto_txt = not m.get("deleted") and ((att_k == "audio" and text.startswith("🎙️")) or
                                                 (att_k == "image" and text in ("🖼️ Bilde", "")))
            t_.set_visible(not auto_txt)
            t_.add_css_class("ks-chat-emoji" if big else ("ks-chat-me" if mine else "ks-chat-other"))
            if cont and not big:
                t_.add_css_class("ks-cont")
            col.append(t_)
            if not m.get("deleted"):
                self._extras(col, room, m, mine)
            if "ks-server://" in text and not m.get("deleted") and not mine and m.get("kind") != "call":
                col.append(_btn("Bli med i serveren", lambda _b, x=text: self._do_join(x), True))
            if m.get("reactions"):
                rr = Gtk.Box(spacing=4, halign=Gtk.Align.END if mine else Gtk.Align.START)
                for e, who_l in m["reactions"].items():
                    b = Gtk.Button(label=f"{e} {len(who_l)}", tooltip_text=", ".join(who_l))
                    b.add_css_class("ks-react")
                    b.connect("clicked", lambda _b, mm=m, ee=e: self._react(mm, ee))
                    rr.append(b)
                col.append(rr)
            if not m.get("deleted"):
                self._menu_for(col, m, mine)
            if seen_before is not None and m.get("id") not in seen_before:   # ny melding: glir mykt inn
                rv = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_UP, transition_duration=220,
                                  child=outer, reveal_child=False)
                self.msgs.append(rv)
                GLib.timeout_add(16, lambda r_=rv: (r_.set_reveal_child(True), False)[1])
            else:
                self.msgs.append(outer)
        self._seen[room] = {m.get("id") for m in msgs}
        self._update_top(room, msgs)
        mine_last = [m for m in msgs if m.get("from_id") == me_id and not m.get("deleted")]
        if room.startswith("s:") and mine_last:
            rc = _dim(CP.receipt(room, mine_last[-1]))
            rc.set_xalign(1)
            self.msgs.append(rc)
        if room.startswith("p:") and msgs:                   # direktemelding: ✓ sendt / ✓✓ lest
            mm = [m for m in msgs if (m.get("pc") == me_pc or m.get("from") == me_pc) and not m.get("deleted")]
            if mm and mm[-1] is msgs[-1]:
                seen = C.seen_by(room)
                rc = _dim(("✓✓ " + i18n.tr("Lest") + " " + time.strftime("%H:%M", time.localtime(seen)))
                          if seen >= mm[-1].get("t", 0) else "✓ " + i18n.tr("Sendt"))
                rc.set_xalign(1)
                self.msgs.append(rc)
        if msgs and CP.is_celebration(msgs[-1].get("text")) and time.time() - msgs[-1].get("t", 0) < 30:
            self._confetti()
        q = C.queued_count()
        dnd = LK.dnd_text()
        self.status.set_label((("🚫 " + i18n.tr(dnd) + "   ") if dnd else "") +
                              (i18n.tr("{n} meldinger venter på at mottakeren skal bli på igjen").replace(
                                  "{n}", str(q)) if q else ""))
        adj = self.scroll.get_vadjustment()
        at_bottom = adj.get_value() + adj.get_page_size() >= adj.get_upper() - 60
        if not same_room and new_w is not None:              # første gang: hopp til første uleste
            self._new_w = new_w

            def first():
                self._jump_new()
                ad = self.scroll.get_vadjustment()
                more = ad.get_value() + ad.get_page_size() < ad.get_upper() - 40   # mer under? vis «Til bunnen»
                self.jump.set_label("↓ " + i18n.tr("Til bunnen"))
                self.jump.set_visible(more)
                return False
            GLib.timeout_add(80, first)
        elif same_room and not at_bottom and seen_before is not None and \
                any(mm.get("id") not in seen_before for mm in msgs):
            self.jump.set_label("↓ " + i18n.tr("Nye meldinger"))
            self.jump.set_visible(True)                      # du har scrollet opp: ikke dra deg ned
        else:
            self.jump.set_visible(False)
            GLib.timeout_add(60, lambda: (self.scroll.get_vadjustment().set_value(1e9), False)[1])
        self._newmark[room] = time.time()                    # neste gang: streken der du slapp
        if self.view != "direct":                       # oppdater «uleste» nå som kanalen er lest
            GLib.idle_add(lambda: (self._channels(), False)[1])

    def _extras(self, col, room, m, mine):
        """Vedlegg, avstemning, avtale og lenker under en melding."""
        al = Gtk.Align.END if mine else Gtk.Align.START
        att = m.get("attach")
        if att:
            path = CP.file_path(att)
            if att.get("kind") == "image" and path:
                pic = _thumb(path, *((110, 110) if m.get("kind") == "sticker" else (300, 220)))
                if pic:
                    pic.set_halign(al)
                    col.append(pic)
            elif att.get("kind") == "audio":
                col.append(self._voice_widget(path, att, mine))
                path = None                                  # ingen fil-knapp under talemeldinger
            if path:
                col.append(_btn(f"📂 {att.get('name')} ({att.get('size', 0) // 1024} KB)",
                                lambda _b, p=path: self._open_path(p), flat=True))
        for key in ("poll", "event"):
            data = m.get(key)
            if not data:
                continue
            votes = m.get("votes" if key == "poll" else "rsvp") or {}
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, halign=al)
            for i, opt in enumerate(data.get("options", [])):
                who = votes.get(str(i), [])
                b = Gtk.Button(label=f"{opt}   {len(who)}" + (f"  ({', '.join(who[:3])})" if who else ""))
                b.add_css_class("pill")
                b.connect("clicked", lambda _b, mm=m, ii=i: (CP.vote(self.room, mm, ii), self._load()))
                box.append(b)
            col.append(box)
        if m.get("play") and not mine:
            col.append(_btn(f"🎮 Bli med i {m['play'].get('game')}", lambda _b, g=m["play"].get("game"): _bg(
                lambda: CL.join_play(g), lambda r: self.status.set_label(str(r))), True))
        if m.get("setup") and not mine:
            col.append(_btn("⚙️ Bruk oppsettet", lambda _b, a=m["setup"].get("appid"): _bg(
                lambda: CL.use_setup(a), lambda r: self.status.set_label(("✗ " if isinstance(r, Exception) else "") +
                                                                         str(r))), True))
        if m.get("screen") and not mine:
            col.append(_btn("📺 Se på", lambda _b, pc=m["screen"].get("pc"): self._watch(pc), True))
        if m.get("kind") == "ring" and not mine:
            col.append(_btn("📞 Svar", lambda _b: (CL.stop_ring(), self._quick("Kommer! 🏃")), True))
        if m.get("kind") == "call" and not mine and m.get("invite"):   # samtale uten server: bli med
            def join_call(_b, mm=m):
                import chatcall
                cid = mm.get("call_id")
                if cid not in dict((c, 1) for c, _f, _r in chatcall.incoming()):
                    chatcall._IN[cid] = {"from": mm.get("from"), "room": self.room, "invite": mm["invite"],
                                         "t": time.time()}
                self._answer(cid)
            col.append(_btn("📞 Bli med i samtalen", join_call, True))
        import re
        for url in re.findall(r"https?://\S+", m.get("text", ""))[:2]:
            if "/api/clipfile" in url:
                col.append(_btn("🎬 Se klippet", lambda _b, u=url: self._open_url(u), True))
            else:
                b = _btn("🔗 " + url[:50], lambda _b, u=url: self._open_url(u), flat=True)
                b.set_halign(al)
                col.append(b)
                import chatextra as CX
                _bg(lambda u=url: CX.link_preview(u),
                    lambda pv, bb=b, u=url: pv and not isinstance(pv, Exception) and self._link_card(bb, u, pv))

    def _link_card(self, btn, url, pv):
        """Bytt lenke-knappen ut med et kort: bilde, tittel, beskrivelse og nettsted."""
        par = btn.get_parent()
        if par is None:
            return
        card_ = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, halign=btn.get_halign())
        card_.add_css_class("ks-linkcard")
        card_.set_size_request(280, -1)
        if pv.get("site"):
            st = Gtk.Label(label=pv["site"], xalign=0)
            st.add_css_class("ks-chat-time")
            card_.append(st)
        tl = Gtk.Label(label=pv.get("title") or url, xalign=0, wrap=True, max_width_chars=42)
        tl.add_css_class("heading")
        card_.append(tl)
        if pv.get("desc"):
            card_.append(Gtk.Label(label=pv["desc"], xalign=0, wrap=True, max_width_chars=42, lines=3,
                                   ellipsize=3, css_classes=["dim-label", "caption"]))
        if pv.get("image"):
            pic = _thumb(pv["image"], 280, 150, cover=True)
            if pic:
                card_.append(pic)
        g = Gtk.GestureClick()
        g.connect("released", lambda *_: self._open_url(url))
        card_.add_controller(g)
        card_.set_cursor_from_name("pointer")
        par.insert_child_after(card_, btn)
        par.remove(btn)

    def _voice_widget(self, path, att, mine):
        """Talemelding: ▶ + lydbølge + lengde."""
        box = Gtk.Box(spacing=8, halign=Gtk.Align.END if mine else Gtk.Align.START)
        box.add_css_class("ks-voice")
        if mine:
            box.add_css_class("mine")
        play = Gtk.Button(label="▶")
        play.add_css_class("circular")
        play.add_css_class("suggested-action")
        play.set_sensitive(bool(path))
        play.connect("clicked", lambda *_: path and CP.play(path))
        box.append(play)
        wv = att.get("wave") or [3, 5, 2, 6, 4, 7, 3, 5, 2, 4, 6, 3, 5, 2, 4, 3, 6, 2, 4, 3]
        da = Gtk.DrawingArea(content_width=max(80, len(wv) * 4), content_height=28, valign=Gtk.Align.CENTER)
        fg = self.get_color()

        def draw(_a, cr, w, h):
            n = len(wv)
            bw = w / n
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.75)
            for i, v in enumerate(wv):
                bh = max(2, h * (0.15 + 0.85 * v / 9))
                cr.rectangle(i * bw + bw * 0.2, (h - bh) / 2, bw * 0.6, bh)
            cr.fill()
        da.set_draw_func(draw)
        box.append(da)
        secs = att.get("secs")
        tl = Gtk.Label(label=(f"{int(secs // 60)}:{int(secs % 60):02d}" if secs else "🎙️"))
        tl.add_css_class("ks-chat-time")
        box.append(tl)
        return box

    def _pins_dialog(self):
        pins = [m for m in getattr(self, "_last_msgs", []) if m.get("pinned") and not m.get("deleted")]
        dlg = Adw.AlertDialog(heading=f"📌 {i18n.tr('Festet')} ({len(pins)})")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for m in reversed(pins):
            lab = Gtk.Label(label=f"{m.get('from')} · {time.strftime('%d.%m %H:%M', time.localtime(m.get('t', 0)))}\n"
                                  f"{m.get('text', '')}", xalign=0, wrap=True, max_width_chars=50, selectable=True)
            lab.add_css_class("card")
            lab.set_margin_bottom(2)
            box.append(lab)
        dlg.set_extra_child(box)
        dlg.add_response("close", i18n.tr("Lukk"))
        dlg.present(self.get_root())

    def _help_dialog(self, txt):
        dlg = Adw.AlertDialog(heading=i18n.tr("Kommandoer i chatten"), body=txt)
        dlg.add_response("close", i18n.tr("Lukk"))
        dlg.present(self.get_root())

    def _gif_dialog(self, query=""):
        """Søk etter GIF-er (Tenor) og send den du trykker på."""
        import chatextra as CX
        if not CX.gif_key():
            dlg = Adw.AlertDialog(heading=i18n.tr("GIF-søk"),
                                  body=i18n.tr("GIF-søket bruker Tenor (gratis). Lag en nøkkel én gang på "
                                               "developers.google.com/tenor (Get a key) og lim den inn her."))
            e = Gtk.Entry(placeholder_text="Tenor API-nøkkel", width_chars=40)
            dlg.set_extra_child(e)
            dlg.add_response("cancel", i18n.tr("Avbryt"))
            dlg.add_response("ok", i18n.tr("Lagre"))
            dlg.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
            dlg.connect("response", lambda _d, r: r == "ok" and e.get_text().strip() and (
                CP.set_(tenor_key=e.get_text().strip()), self._gif_dialog(query)))
            dlg.present(self.get_root())
            return
        dlg = Adw.Dialog(title="GIF", content_width=560, content_height=520)
        tv = Adw.ToolbarView()
        tv.add_top_bar(Adw.HeaderBar())
        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_start=12, margin_end=12,
                    margin_bottom=12)
        se = Gtk.SearchEntry(text=query, placeholder_text=i18n.tr("Søk etter GIF …"))
        v.append(se)
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=4, row_spacing=6,
                           column_spacing=6, homogeneous=True)
        sc = Gtk.ScrolledWindow(child=flow, vexpand=True)
        v.append(sc)
        info = _dim("")
        v.append(info)
        tv.set_content(v)
        dlg.set_child(tv)

        def send(big):
            dlg.close()
            self.status.set_label(i18n.tr("Sender GIF …"))
            bg = getattr(self.get_root(), "bg", None)
            _bg(lambda: CP.send_file(self.room, CX.gif_file(big), "", bg.notify if bg else None),
                lambda r: (self.status.set_label(("✗ " if isinstance(r, Exception) else "") + str(r)), self._load()))

        def show(res):
            while (c := flow.get_first_child()) is not None:
                flow.remove(c)
            if isinstance(res, Exception):
                info.set_label(f"✗ {res}")
                return
            info.set_label("" if res else i18n.tr("Ingen treff"))
            for tiny_path, big in res:
                b = Gtk.Button()
                b.add_css_class("ks-gif-pick")
                pic = Gtk.Picture.new_for_filename(tiny_path)
                pic.set_content_fit(Gtk.ContentFit.COVER)
                pic.set_size_request(120, 90)
                b.set_child(pic)
                b.connect("clicked", lambda _b, u=big: send(u))
                flow.append(b)

        def search(*_):
            q = se.get_text().strip() or "hello"
            info.set_label(i18n.tr("Søker …"))
            _bg(lambda: [(CX.gif_file(t), b) for t, b in CX.gif_search(q)], show)
        se.connect("activate", search)
        dlg.present(self.get_root())
        search()

    def _update_top(self, room, msgs):
        """📌 siste festede melding og 🎮 hvem som spiller nå (servere)."""
        import chatextra as CX
        self._last_msgs = msgs
        pins = [m for m in msgs if m.get("pinned") and not m.get("deleted")]
        self.pinbar.set_visible(bool(pins))
        if pins:
            last = pins[-1]
            self.pinbar.set_label(f"📌 {last.get('from')}: {str(last.get('text', ''))[:80]}" +
                                  (f"   (+{len(pins) - 1})" if len(pins) > 1 else ""))
        while (c := self.playing.get_first_child()) is not None:
            self.playing.remove(c)
        players = []
        if room.startswith("s:"):
            srv = CS.get(room.split(":")[1]) or {}
            for mid, mem in (srv.get("members") or {}).items():
                p = CL._PRES.get(mid) if mid != CS.me()["id"] else None
                if p and p.get("game") and time.time() - p.get("t", 0) < 600:
                    players.append((mem.get("name") or p.get("name"), p["game"], p.get("since") or 0))
        for name, game, since in players[:6]:
            lbl = f"🎮 {name} · {game}" + (f" · {CX.fmt_dur(time.time() - since)}" if since else "")
            b = Gtk.Button(label=lbl, tooltip_text=i18n.tr("Bli med i spillet"))
            b.connect("clicked", lambda _b, g=game: _bg(lambda: CL.join_play(g),
                                                       lambda r: self.status.set_label(str(r))))
            self.playing.append(b)
        self.playing.set_visible(bool(players))

    def _open_url(self, url):
        from gi.repository import Gio
        Gio.AppInfo.launch_default_for_uri(url, None)

    def _open_path(self, path):
        from gi.repository import Gio
        Gio.AppInfo.launch_default_for_uri("file://" + path, None)

    def _confetti(self):
        if getattr(self, "_conf_t", 0) > time.time() - 10:
            return
        self._conf_t = time.time()
        self.typing_lab.set_label("🎉 🎊 🥳 🎉 🎊 🥳 🎉 🎊 🥳")
        GLib.timeout_add_seconds(4, lambda: (self.typing_lab.set_label(""), False)[1])

    def _call_room_now(self):
        import chatcall
        room = self.room
        self.status.set_label(i18n.tr("Ringer …"))
        _bg(lambda: chatcall.call([room]), lambda r: (self.status.set_label(("✗ " if isinstance(r, Exception) else "")
                                                                          + str(r)), self.vcbar.refresh(),
                                                      self._channels()))

    def _group_call(self):
        import chatcall
        people = [(rid, name) for rid, name, _i, _u in self._rooms if rid.startswith("p:")] if self._rooms else []
        if not people:
            self.status.set_label(i18n.tr("Ingen å ringe ennå"))
            return
        dlg = Adw.AlertDialog(heading=i18n.tr("Gruppesamtale"),
                              body=i18n.tr("Velg hvem som skal være med – de får «📞 Svar» med en gang."))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        checks = []
        for rid, name in people:
            cb = Gtk.CheckButton(label=name, active=rid == self.room)
            box.append(cb)
            checks.append((cb, rid))
        sc = Gtk.ScrolledWindow(child=box, hscrollbar_policy=Gtk.PolicyType.NEVER, propagate_natural_height=True,
                                max_content_height=320)
        dlg.set_extra_child(sc)
        dlg.add_response("nei", i18n.tr("Avbryt"))
        dlg.add_response("ja", i18n.tr("📞 Ring"))
        dlg.set_response_appearance("ja", Adw.ResponseAppearance.SUGGESTED)

        def go():
            rooms = [rid for cb, rid in checks if cb.get_active()]
            _bg(lambda: chatcall.call(rooms),
                lambda r: (self.status.set_label(("✗ " if isinstance(r, Exception) else "") + str(r)),
                           self.vcbar.refresh(), self._channels()))
        dlg.connect("response", lambda _d, r: r == "ja" and go())
        dlg.present(self.get_root())

    def _answer(self, cid):
        import chatcall
        _bg(lambda: chatcall.answer(cid), lambda r: (self.status.set_label(("✗ " if isinstance(r, Exception) else "")
                                                                           + str(r)), self.vcbar.refresh(),
                                                     self._bars(), self._channels()))

    def _bars(self):
        import phonecam
        live = phonecam.live()
        self.phonebar.set_visible(live)
        if live:
            self.phone_lab.set_label(phonecam.status())
        st = CV.call_state()
        import chatcall
        inc = chatcall.incoming()
        self._inc = inc[0][0] if inc else None
        self.callbar.set_visible(bool(st) or bool(inc))
        if inc:
            self.call_lab.set_label(f"📞 {inc[0][1]} ringer deg")
            self.call_ans.set_visible(True)
        elif st:
            self.call_lab.set_label(st)
            self.call_ans.set_visible(bool(CV._CALL.get("incoming")))
        in_dm = self.view == "direct" and self.room.startswith("p:")
        self.call_btn.set_visible(in_dm)
        self.group_call_btn.set_visible(self.view == "direct")
        game, names = CV.same_game(self.get_root())
        self.gamebar.set_visible(bool(names))
        if names:
            self.game_lab.set_label(f"🎮 {', '.join(names[:3])} spiller også {game}")
        return False

    def _call_do(self, fn):
        _bg(fn, lambda r: (self.status.set_label(("✗ " if isinstance(r, Exception) else "") + str(r)), self._bars()))

    def _to_players(self, *_):
        t = self.entry.get_text().strip() or i18n.tr("Bli med? 🎮")
        self.entry.set_text("")
        _bg(lambda: CV.send_to_players(self.get_root(), t), lambda r: self.status.set_label(str(r)))

    def _walkie(self, *_):
        if not self._need_server():
            return
        if CP._REC["p"] is None:
            try:
                CP.record_start()
                self.walkie_btn.set_label("🔴")
                self.status.set_label(i18n.tr("Snakk nå … trykk 🔴 for å sende"))
            except Exception as e:  # noqa: BLE001
                self.status.set_label(f"✗ {e}")
            return
        self.walkie_btn.set_label("📢")
        path = CP.record_stop()
        if not path:
            self.status.set_label(i18n.tr("For kort"))
            return
        _bg(lambda: CV.send_walkie(self.room, path), lambda r: (self.status.set_label(str(r)), self._load()))

    def _typing(self):
        who = CP.who_typing(self.room)
        self.typing_lab.set_label((", ".join(who) + " " + i18n.tr("skriver …")) if who else "")
        if who:
            GLib.timeout_add_seconds(5, lambda: (self._typing(), False)[1])

    def _emoji_pop(self):
        pop = Gtk.Popover()
        grid = Gtk.FlowBox(max_children_per_line=10, selection_mode=Gtk.SelectionMode.NONE, margin_top=6,
                           margin_bottom=6, margin_start=6, margin_end=6)
        for e in EMOJI:
            b = Gtk.Button(label=e)
            b.add_css_class("flat")
            b.connect("clicked", lambda _b, ee=e: (self.entry.set_text(self.entry.get_text() + ee),
                                                   self.entry.set_position(-1)))
            grid.append(b)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.append(grid)
        box.append(Gtk.Separator())
        sl = Gtk.Label(label=i18n.tr("Klistremerker"), xalign=0, margin_start=6)
        sl.add_css_class("caption-heading")
        box.append(sl)
        self.stick_box = Gtk.FlowBox(max_children_per_line=6, selection_mode=Gtk.SelectionMode.NONE, margin_start=6,
                                     margin_end=6)
        box.append(self.stick_box)
        box.append(_btn("➕ Lag klistremerke av et bilde …", lambda *_: (pop.popdown(), self._make_sticker()), flat=True))
        pop.set_child(box)
        pop.connect("show", lambda *_: self._fill_stickers(pop))
        return pop

    def _fill_stickers(self, pop):
        while (c := self.stick_box.get_first_child()) is not None:
            self.stick_box.remove(c)
        for path in CV.stickers()[:18]:
            b = Gtk.Button()
            b.add_css_class("flat")
            pic = Gtk.Picture.new_for_filename(path)
            pic.set_size_request(56, 56)
            b.set_child(pic)
            b.connect("clicked", lambda _b, pp=path: (pop.popdown(), self._call_room(lambda: CV.send_sticker(
                self.room, pp))))
            self.stick_box.append(b)

    def _make_sticker(self):
        dlg = Gtk.FileDialog(title=i18n.tr("Velg et bilde"))

        def done(d, res):
            try:
                f = d.open_finish(res)
            except GLib.Error:
                return
            try:
                CV.make_sticker(f.get_path())
                self.status.set_label(i18n.tr("Klistremerket er laget – finn det under 😊"))
            except Exception as e:  # noqa: BLE001
                self.status.set_label(f"✗ {e}")
        dlg.open(self.get_root(), None, done)

    def _need_server(self, dm=False):
        if dm and self.room.startswith("p:"):                # virker også i direktemeldinger
            return True
        if not self.room.startswith("s:"):
            self.status.set_label(i18n.tr("Dette virker i serverkanaler – lag en server med ➕"))
            return False
        return True

    def _attach(self, *_):
        if not self._need_server(dm=True):
            return
        dlg = Gtk.FileDialog(title=i18n.tr("Legg ved"))
        try:
            import clips
            d = clips.clip_dir()
            if d and os.path.isdir(d):
                dlg.set_initial_folder(Gio.File.new_for_path(d))
        except Exception:  # noqa: BLE001
            pass

        def done(d, res):
            try:
                f = d.open_finish(res)
            except GLib.Error:
                return
            path = f.get_path()
            self.status.set_label(i18n.tr("Sender …"))
            _bg(lambda: CP.send_file(self.room, path), lambda r: (self.status.set_label(
                ("✗ " if isinstance(r, Exception) else "") + str(r)), self._load()))
        dlg.open(self.get_root(), None, done)

    def _voice(self, *_):
        if not self._need_server(dm=True):
            return
        import chatextra as CX
        if CX.rec_available() and CP._REC["p"] is None:     # talemelding med lydbølge (GStreamer, også Windows)
            if not CX.recording():
                try:
                    CX.rec_start()
                except Exception as e:  # noqa: BLE001
                    self.status.set_label(f"✗ {e}")
                    return
                self.mic_btn.set_label("⏺️")
                t0 = time.time()

                def tick():
                    if not CX.recording():
                        return False
                    bars = "▁▂▃▄▅▆▇█"
                    self.status.set_label(f"🔴 {int(time.time() - t0)} s  " + bars[int(CX.rec_level() * 7)] * 6 +
                                          "  " + i18n.tr("trykk 🎙️ for å sende · Esc avbryter"))
                    return True
                GLib.timeout_add(120, tick)
                return
            self.mic_btn.set_label("🎙️")
            res = CX.rec_stop()
            if not res:
                self.status.set_label(i18n.tr("For kort opptak"))
                return
            path, wv, secs = res
            bg = getattr(self.get_root(), "bg", None)
            _bg(lambda: CX.send_voice(self.room, path, wv, secs, bg.notify if bg else None),
                lambda r: (self.status.set_label(("✗ " if isinstance(r, Exception) else "") + str(r)), self._load()))
            return
        if CP._REC["p"] is None:
            try:
                CP.record_start()
                self.mic_btn.set_label("⏺️")
                self.status.set_label(i18n.tr("Tar opp … trykk 🎙️ igjen for å sende"))
            except Exception as e:  # noqa: BLE001
                self.status.set_label(f"✗ {e}")
            return
        self.mic_btn.set_label("🎙️")
        path = CP.record_stop()
        if not path:
            self.status.set_label(i18n.tr("For kort opptak"))
            return
        _bg(lambda: CP.send_file(self.room, path), lambda r: (self.status.set_label(
            ("✗ " if isinstance(r, Exception) else "") + str(r)), self._load()))

    def _more_pop(self):
        pop = Gtk.Popover()
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=6, margin_bottom=6, margin_start=6,
                        margin_end=6)
        groups = (
            ("Lag", (("📊 Avstemning", self._poll), ("📅 Avtale med svar", self._event_inv),
                     ("📋 Oppgave med «Gjort»", self._task), ("🎮 Spill sammen …", self._play),
                     ("🕹️ Lobby …", self._lobby),
                     ("🍽️ Middagsavstemning", lambda: self._call_room(lambda: CL.dinner_poll(self.room))))),
            ("Del", (("📊 PC-status", lambda: self._call_any(lambda: C.send(self.room, CL.status_card(self.get_root())))),
                     ("⚙️ Spilloppsettet (sist spilte)", self._share_setup),
                     ("📺 Vis skjermen min", lambda: self._call_room(lambda: CL.share_screen(self.room))),
                     ("🔔 Ring", lambda: self._call_room(lambda: CL.send_ring(self.room))),
                     ("🆘 Be om hjelp", lambda: self._call_any(lambda: __import__("homeplus").ask_help())))),
            ("Verktøy", (("🎛️ Lyd og video", self._av_settings), ("📱 Mobilkamera", self._phonecam), ("⏰ Påminnelse", self._remind), ("🕒 Send senere", self._schedule),
                         ("📝 Notater", self._notes), ("🛒 Handleliste", self._shop),
                         ("🌐 Oversett siste melding", self._translate),
                         ("🏠 Hvor er alle?", lambda: self.status.set_label(CL.where_is_everyone())),
                         ("🎲 Terning", lambda: self._call_room(lambda: CP.dice(self.room))),
                         ("✊ Stein–saks–papir", self._rps))),
            ("Visning", (("🎨 Bakgrunn i samtalen …", lambda: self._bg_dialog(self.room)),
                         ("📏 Kompakt visning av/på", self._toggle_compact),
                         ("🚫 Ikke forstyrr …", self._dnd_dialog))),
            ("Kanalen", (("💨 Meldinger forsvinner …", self._vanish), ("💾 Eksporter", self._export),
                         ("📣 Høydepunkter og toppliste hit", self._use_for_posts),
                         ("🏷️ Tilbud fra ønskelisten hit", lambda: self._topic("tilbud")),
                         ("🎁 Gratis spill (Epic) hit", lambda: self._topic("gratis")),
                         ("🔄 Oppdateringer hit", lambda: self._topic("oppdateringer")))))
        sc = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, propagate_natural_height=True,
                                max_content_height=520)
        for title, items in groups:
            h = Gtk.Label(label=i18n.tr(title).upper(), xalign=0, margin_top=6, margin_start=6)
            h.add_css_class("ks-chan-cat")
            outer.append(h)
            for label, fn in items:
                b = Gtk.Button(label=i18n.tr(label))
                b.add_css_class("flat")
                b.get_child().set_xalign(0)
                b.connect("clicked", lambda _b, f=fn: (pop.popdown(), f()))
                outer.append(b)
        sc.set_child(outer)
        pop.set_child(sc)
        return pop

    def _toggle_compact(self):
        CP.set_(compact=not CP.cfg().get("compact"))
        self._shown_room = None
        self._load()

    def _bg_dialog(self, room):
        """Egen bakgrunn per samtale: ferdige fargebakgrunner eller et eget bilde."""
        import chatlook as LK
        dlg = Adw.AlertDialog(heading=i18n.tr("Bakgrunn i samtalen"),
                              body=i18n.tr("Vises bare hos deg. Velg en bakgrunn eller et eget bilde."))
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=4, column_spacing=6,
                           row_spacing=6)

        def pick(key):
            bgs = dict(CP.cfg().get("room_bg", {}))
            if key:
                bgs[room] = key
            else:
                bgs.pop(room, None)
            CP.set_(room_bg=bgs)
            if room == self.room:
                self._set_room_bg(room)
            dlg.close()
        for key, (name, css) in LK.BACKGROUNDS.items():
            b = Gtk.Button(label=i18n.tr(name))
            b.set_size_request(96, 56)
            pr = Gtk.CssProvider()
            pr.load_from_data(f"button {{ background: {css if key else 'alpha(@window_fg_color,0.06)'}; "
                              f"background-color: alpha(@window_fg_color,0.06); }}".encode())
            b.get_style_context().add_provider(pr, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 9)
            b.connect("clicked", lambda _b, k=key: pick(k))
            flow.append(b)
        img = Gtk.Button(label="🖼️ " + i18n.tr("Eget bilde …"))
        img.set_size_request(96, 56)

        def choose(*_):
            fd = Gtk.FileDialog(title=i18n.tr("Velg et bilde"))
            flt = Gtk.FileFilter()
            flt.add_mime_type("image/*")
            fs = Gio.ListStore.new(Gtk.FileFilter)
            fs.append(flt)
            fd.set_filters(fs)

            def done(d, res):
                try:
                    f = d.open_finish(res)
                except GLib.Error:
                    return
                if f and f.get_path():
                    pick("bilde:" + f.get_path())
            fd.open(self.get_root(), None, done)
        img.connect("clicked", choose)
        flow.append(img)
        dlg.set_extra_child(flow)
        dlg.add_response("close", i18n.tr("Lukk"))
        dlg.present(self.get_root())

    def _dnd_dialog(self):
        import chatlook as LK
        dlg = Adw.AlertDialog(heading=i18n.tr("Ikke forstyrr"),
                              body=(LK.dnd_text() or i18n.tr("Ingen varsler for chatmeldinger – de kommer fortsatt "
                                                             "inn, og du ser dem når du åpner chatten.")))
        sw = Gtk.CheckButton(label=i18n.tr("Alltid når jeg spiller"), active=bool(CP.cfg().get("dnd_game")))
        sw.connect("toggled", lambda w: CP.set_(dnd_game=w.get_active()))
        dlg.set_extra_child(sw)
        for rid, label in (("1", "1 time"), ("2", "2 timer"), ("8", "8 timer"), ("-1", "Til i morgen"),
                           ("0", "Av")):
            dlg.add_response(rid, i18n.tr(label))
        dlg.set_close_response("close")
        dlg.connect("response", lambda _d, r: r != "close" and (LK.set_dnd(int(r)), self._load()))
        dlg.present(self.get_root())

    def _call_any(self, fn):
        _bg(fn, lambda r: (self.status.set_label(("✗ " if isinstance(r, Exception) else "") + str(r)), self._load()))

    def _quick_pick(self, dd, _p):
        i = dd.get_selected()
        if i <= 0:
            return
        text = self._quick_items[i - 1]
        GLib.idle_add(lambda: (dd.set_selected(0), False)[1])
        self._quick(text)

    def _quick(self, text):
        if text.startswith("🆘"):
            self._call_any(lambda: __import__("homeplus").ask_help("fra chatten"))
            return
        if text.startswith("🍕"):
            import savegames
            self._call_any(lambda: __import__("features").send_to("*", savegames.pc_name(), "🍕 Sulten! Er det mat snart?",
                                                                   urgent=True) or "Sendt til alle hjemme")
            return
        CL.stop_ring()
        self._call_any(lambda: C.send(self.room, text))

    def _watch(self, pc):
        try:
            import homepcs
            import watch_ui
            p = next((x for x in homepcs.fetch() or [] if x.get("name") == pc), None)
            if not p or not p.get("ips"):
                self.status.set_label(i18n.tr("«Se på» virker bare for PC-ene hjemme"))
                return
            watch_ui.WatchWindow(self.get_root(), pc, p["ips"][0], None).present()
        except Exception as e:  # noqa: BLE001
            self.status.set_label(f"✗ {e}")

    def _games(self):
        try:
            import launcher
            return [g["name"] for g in launcher.all_games()][:40]
        except Exception:  # noqa: BLE001
            return []

    def _pick_game(self, title, cb, extra=None):
        names = self._games()
        if not names:
            self.status.set_label(i18n.tr("Fant ingen spill"))
            return
        dlg = Adw.AlertDialog(heading=i18n.tr(title))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        dd = Gtk.DropDown.new_from_strings(names)
        box.append(dd)
        sp = None
        if extra:
            sp = Gtk.SpinButton.new_with_range(2, 10, 1)
            sp.set_value(4)
            box.append(Gtk.Label(label=i18n.tr(extra), xalign=0))
            box.append(sp)
        dlg.set_extra_child(box)
        dlg.add_response("nei", i18n.tr("Avbryt"))
        dlg.add_response("ja", i18n.tr("Send"))
        dlg.set_response_appearance("ja", Adw.ResponseAppearance.SUGGESTED)
        dlg.connect("response", lambda _d, r: r == "ja" and cb(names[dd.get_selected()],
                                                                int(sp.get_value()) if sp else None))
        dlg.present(self.get_root())

    def _play(self):
        if self._need_server():
            self._pick_game("Spill sammen", lambda g, _n: self._call_room(lambda: CL.send_play(self.room, g)))

    def _lobby(self):
        if self._need_server():
            self._pick_game("Lobby", lambda g, n: self._call_room(lambda: CL.send_lobby(self.room, g, n)),
                            "Hvor mange trengs?")

    def _task(self):
        if self._need_server():
            _ask(self.get_root(), "Oppgave", "Alle ser hvem som har trykket «Gjort».", [("t", "F.eks. Søppelet ut i kveld", "")],
                 lambda v: self._call_room(lambda: CL.send_task(self.room, v["t"])), "Send")

    def _share_setup(self):
        if not self._need_server():
            return
        try:
            import games_auto
            last = (games_auto.load_sessions() or [{}])[-1].get("name")
        except Exception:  # noqa: BLE001
            last = None
        if not last:
            self.status.set_label(i18n.tr("Spill et spill først"))
            return
        self._call_room(lambda: CL.share_setup(self.room, last))

    def _shop(self):
        items = CL.shop_list(0)
        dlg = Adw.Dialog(title=i18n.tr("Handleliste"), content_width=380, content_height=440)
        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=12, margin_bottom=12, margin_start=12,
                    margin_end=12)
        v.append(_dim("Felles for alle hjemme. Skriv «+melk» i chatten for å legge til."))
        lst = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        def fill(its):
            while (c := lst.get_first_child()) is not None:
                lst.remove(c)
            for it in its:
                rr = Gtk.Box(spacing=6)
                rr.append(Gtk.Label(label="🛒 " + it, xalign=0, hexpand=True))
                rr.append(_btn("✓", lambda _b, x=it: fill(CL.shop_remove(x)), flat=True))
                lst.append(rr)
        fill(items)
        v.append(lst)
        e = Gtk.Entry(placeholder_text=i18n.tr("Legg til …"))
        e.connect("activate", lambda en: (fill(CL.shop_add(en.get_text().strip())), en.set_text("")) if
                  en.get_text().strip() else None)
        v.append(e)
        dlg.set_child(Gtk.ScrolledWindow(child=v, vexpand=True))
        dlg.present(self.get_root())

    def _topic(self, kind):
        if self._need_server():
            CV.set_topic_room(kind, self.room)
            self.status.set_label(i18n.tr("Kanalen brukes nå til ") + kind)

    def _use_for_posts(self):
        if not self._need_server():
            return
        CL.set_(share_highlights=self.room, weekly_room=self.room)
        self.status.set_label(i18n.tr("Høydepunkter og ukens toppliste postes nå i denne kanalen"))

    def _paste_key(self, _c, keyval, _code, state):
        if keyval == Gdk.KEY_Escape:                         # Esc avbryter en talemelding
            import chatextra as CX
            if CX.recording():
                CX.rec_cancel()
                self.mic_btn.set_label("🎙️")
                self.status.set_label(i18n.tr("Talemeldingen ble avbrutt"))
                return True
            return False
        if not (state & Gdk.ModifierType.CONTROL_MASK) or keyval not in (Gdk.KEY_v, Gdk.KEY_V):
            return False
        cb = Gdk.Display.get_default().get_clipboard()
        if not cb.get_formats().contain_gtype(Gdk.Texture) or not self.room.startswith(("s:", "p:")):
            return False

        def got(c, res):
            try:
                tex = c.read_texture_finish(res)
            except GLib.Error:
                return
            path = os.path.join(CP.FILES, f"innlimt-{int(time.time())}.png")
            os.makedirs(CP.FILES, exist_ok=True)
            tex.save_to_png(path)
            _bg(lambda: CP.send_file(self.room, path), lambda r: (self.status.set_label(str(r)), self._load()))
        cb.read_texture_async(None, got)
        return True

    def _call_room(self, fn):
        if not self._need_server(dm=True):
            return
        _bg(fn, lambda r: (self.status.set_label(("✗ " if isinstance(r, Exception) else "") + str(r)), self._load()))

    def _poll(self):
        if not self._need_server():
            return
        _ask(self.get_root(), "Avstemning", "Skriv valgene adskilt med komma.",
             [("q", "Spørsmål, f.eks. Hva spiller vi i kveld?", ""), ("o", "CS2, Minecraft, WoW", "")],
             lambda v: self._call_room(lambda: CP.send_poll(self.room, v["q"], v["o"].split(","))), "Send")

    def _event_inv(self):
        if not self._need_server():
            return
        _ask(self.get_root(), "Avtale", "Alle kan svare Kommer / Kanskje / Nei. Den legges også i ukeplanen.",
             [("t", "Hva, f.eks. LAN", ""), ("w", "Når, f.eks. lørdag 18:00", "")],
             lambda v: self._call_room(lambda: CP.send_event_invite(self.room, v["t"], v["w"])), "Send")

    def _remind(self):
        _ask(self.get_root(), "Påminnelse", "", [("t", "Hva", ""), ("w", "Når – «i morgen 17:00» / «om 10 min»", "")],
             lambda v: _bg(lambda: CP.remind(self.room, v["t"], v["w"]),
                           lambda r: self.status.set_label(("✗ " if isinstance(r, Exception) else "") + str(r))),
             "Lagre")

    def _schedule(self):
        _ask(self.get_root(), "Send senere", "", [("t", "Melding", self.entry.get_text()),
                                                  ("w", "Når – «i morgen 07:00»", "")],
             lambda v: _bg(lambda: CP.schedule(self.room, v["t"], v["w"]),
                           lambda r: (self.entry.set_text(""), self.status.set_label(
                               ("✗ " if isinstance(r, Exception) else "") + str(r)))), "Planlegg")

    def _rps(self):
        _ask(self.get_root(), "Stein–saks–papir", "Skriv stein, saks eller papir.", [("c", "stein / saks / papir", "")],
             lambda v: self._call_room(lambda: CP.rps(self.room, v["c"])), "Spill")

    def _notes(self):
        dlg = Adw.Dialog(title=i18n.tr("Notater for samtalen"), content_width=480, content_height=420)
        tv = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, left_margin=12, right_margin=12, top_margin=12)
        tv.get_buffer().set_text(CP.notes(self.room))
        room = self.room
        dlg.connect("closed", lambda *_: CP.set_notes(room, tv.get_buffer().get_property("text")))
        dlg.set_child(Gtk.ScrolledWindow(child=tv, vexpand=True))
        dlg.present(self.get_root())

    def _translate(self):
        msgs = [m for m in C.messages(self.room, 20) if m.get("text")]
        if msgs:
            self._open_url(CP.translate_url(msgs[-1]["text"]))

    def _vanish(self):
        opts = [(0, "Av"), (86400, "Etter 24 timer"), (7 * 86400, "Etter en uke")]
        dlg = Adw.AlertDialog(heading=i18n.tr("Meldinger forsvinner"), body=i18n.tr("Gjelder denne samtalen på denne "
                                                                                      "PC-en. Festede meldinger blir."))
        for sec, label in opts:
            dlg.add_response(str(sec), i18n.tr(label))
        dlg.connect("response", lambda _d, r: r in [str(x[0]) for x in opts] and CP.set_vanish(self.room, int(r)))
        dlg.present(self.get_root())

    def _export(self):
        dlg = Gtk.FileDialog(title=i18n.tr("Eksporter samtalen"), initial_name="chat.txt")

        def done(d, res):
            try:
                f = d.save_finish(res)
            except GLib.Error:
                return
            n = CP.export(self.room, f.get_path())
            self.status.set_label(f"✓ {n} meldinger lagret")
        dlg.save(self.get_root(), None, done)

    def _search(self):
        dlg = Adw.Dialog(title=i18n.tr("Søk i chatten"), content_width=560, content_height=520)
        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12, margin_start=12,
                    margin_end=12)
        e = Gtk.SearchEntry(placeholder_text=i18n.tr("Søk etter ord eller navn"))
        v.append(e)
        res = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        v.append(Gtk.ScrolledWindow(child=res, vexpand=True))

        def go(*_):
            while (c := res.get_first_child()) is not None:
                res.remove(c)
            for room, m in CP.search(e.get_text()):
                b = Gtk.Button()
                b.add_css_class("flat")
                lab = Gtk.Label(xalign=0, wrap=True, label=f"{time.strftime('%d.%m %H:%M', time.localtime(m.get('t', 0)))}"
                                f"  {m.get('from')}: {str(m.get('text', ''))[:120]}")
                b.set_child(lab)
                b.connect("clicked", lambda _b, rr=room: (dlg.close(), self._goto(rr)))
                res.append(b)
        e.connect("search-changed", go)
        dlg.set_child(v)
        dlg.present(self.get_root())

    def _goto(self, room):
        if room.startswith("s:"):
            self.view = room.split(":")[1]
            self.room = room
            self._rail()
            self._channels()
            self._load()
        else:
            self.view, self.room = "direct", room
            self._rail()
            self._channels()
            self._load()

    def _profile(self):
        c = CP.cfg()
        dlg = Adw.Dialog(title=i18n.tr("Profil og chat"), content_width=520, content_height=600)
        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=16, margin_bottom=16, margin_start=16,
                    margin_end=16)
        name = Gtk.Entry(text=CS.me()["name"], placeholder_text=i18n.tr("Visningsnavn"))
        av = Gtk.Entry(text=c["avatar"], placeholder_text=i18n.tr("Avatar (én emoji), f.eks. 🦊"), max_length=4)
        status = Gtk.Entry(text=c["status"], placeholder_text=i18n.tr("Status, f.eks. «På skolen til 15»"))
        ar = Gtk.Entry(text=c["autoreply_text"], placeholder_text=i18n.tr("Autosvar mens du spiller (tom = standard)"))
        for lab, w in (("Navn i chatten", name), ("Avatar", av), ("Status", status), ("Autosvar", ar)):
            v.append(Gtk.Label(label=i18n.tr(lab), xalign=0, css_classes=["heading"]))
            v.append(w)
        sw_rows = []
        lc = CL.cfg()
        link_rows = []
        for key, title in (("read_aloud", "Les viktige meldinger høyt mens jeg spiller"),
                           ("quiet", "Stille etter leggetid (unntatt 🆘, Ring og Middag)")):
            rr = Gtk.Box(spacing=8)
            rr.append(Gtk.Label(label=i18n.tr(title), xalign=0, hexpand=True))
            s2 = Gtk.Switch(active=bool(lc[key]), valign=Gtk.Align.CENTER)
            rr.append(s2)
            v.append(rr)
            link_rows.append((key, s2))
        fr = Gtk.Box(spacing=8)
        fr.append(Gtk.Label(label=i18n.tr("Barnefilter (stygge ord blir ***)"), xalign=0, hexpand=True))
        fsw = Gtk.Switch(active=CL.child_mode(), valign=Gtk.Align.CENTER)

        def fchange(w, _p):
            import familylock
            if not w.get_active() and familylock.locked() and not getattr(w, "_ok", False):
                def cancel():
                    w._ok = True
                    w.set_active(True)
                    w._ok = False
                familylock.ask(self.get_root(), "Familiekontroll er på – skriv koden for å slå av filteret.",
                               lambda: CL.set_(filter=False), cancel)
                return
            CL.set_(filter=w.get_active())
        fsw.connect("notify::active", fchange)
        fr.append(fsw)
        v.append(fr)
        if lc["blocked"]:
            v.append(Gtk.Label(label=i18n.tr("Blokkert"), xalign=0, css_classes=["heading"]))
            for b_ in lc["blocked"]:
                rr = Gtk.Box(spacing=8)
                rr.append(Gtk.Label(label=b_, xalign=0, hexpand=True))
                rr.append(_btn("Opphev", lambda _b, x=b_: (CL.unblock(x), dlg.close()), flat=True))
                v.append(rr)
        try:
            inv = CL.friend_qr_text()
        except Exception:  # noqa: BLE001
            inv = None
        if inv:
            import homeplus_ui
            v.append(Gtk.Label(label=i18n.tr("Vennekoden din – skann med mobilen eller del lenken"), xalign=0,
                               css_classes=["heading"]))
            v.append(homeplus_ui.QrView(inv, 200))
            cpb = _btn("Kopier vennelenken", lambda _b: Gdk.Display.get_default().get_clipboard().set(inv), flat=True)
            v.append(cpb)
        for key, title in (("autoreply", "Svar automatisk når jeg spiller"), ("celebrate", "Feiring ved «gg», «gratulerer» og 🎉")):
            r = Gtk.Box(spacing=8)
            r.append(Gtk.Label(label=i18n.tr(title), xalign=0, hexpand=True))
            s_ = Gtk.Switch(active=bool(c[key]), valign=Gtk.Align.CENTER)
            r.append(s_)
            v.append(r)
            sw_rows.append((key, s_))
        st = CP.stats()
        v.append(Gtk.Label(label=i18n.tr("Statistikk"), xalign=0, css_classes=["heading"]))
        v.append(_dim(f"{st['total']} meldinger · mest aktive: " + ", ".join(f"{n} ({k})" for n, k in st["top"][:3]) +
                      ("  ·  mest brukte emoji: " + " ".join(e for e, _n in st["emoji"]) if st["emoji"] else "")))
        mem = CP.memories()
        if mem:
            v.append(Gtk.Label(label=i18n.tr("Minner"), xalign=0, css_classes=["heading"]))
            for label, _room, m in mem[:3]:
                v.append(_dim(f"{label}: {m.get('from')}: «{str(m.get('text'))[:80]}»"))
        summ = CP.summary()
        if summ:
            v.append(Gtk.Label(label=i18n.tr("Mens du var borte"), xalign=0, css_classes=["heading"]))
            for line in summ[:6]:
                v.append(_dim(line))

        def save(*_):
            me_f = CS.ME_FILE
            try:
                import json as _j
                d = _j.load(open(me_f))
                d["display"] = name.get_text().strip()[:40]
                _j.dump(d, open(me_f, "w"))
            except Exception:  # noqa: BLE001
                pass
            CP.set_(status=status.get_text().strip()[:80], autoreply_text=ar.get_text().strip()[:120],
                    avatar=av.get_text().strip()[:4], **{k: w.get_active() for k, w in sw_rows})
            CL.set_(**{k: w.get_active() for k, w in link_rows})
            dlg.close()
        v.append(_btn("Lagre", save, True))
        dlg.set_child(Gtk.ScrolledWindow(child=v, vexpand=True))
        dlg.present(self.get_root())

    def _menu_for(self, widget, m, mine):
        """Høyreklikk på en melding: svar, reaksjoner, rediger, slett, fest."""
        g = Gtk.GestureClick(button=3)

        def pressed(_g, _n, _x, _y):
            pop = Gtk.Popover()
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, margin_top=6, margin_bottom=6,
                          margin_start=6, margin_end=6)
            er = Gtk.Box(spacing=2)
            for e in ("👍", "😂", "❤️", "😮", "🎉", "🔥"):
                b = Gtk.Button(label=e)
                b.add_css_class("flat")
                b.connect("clicked", lambda _b, ee=e: (pop.popdown(), self._react(m, ee)))
                er.append(b)
            box.append(er)
            for label, fn, ok in (("↪ Svar", lambda: self._set_reply(m), True),
                                  ("✏️ Rediger", lambda: self._edit(m), mine),
                                  ("📌 Fest / løsne", lambda: self._event(m, "pin", on=not m.get("pinned")), True),
                                  ("🗑️ Slett", lambda: self._event(m, "delete"), mine or self._is_admin())):
                if ok:
                    b = Gtk.Button(label=i18n.tr(label))
                    b.add_css_class("flat")
                    b.connect("clicked", lambda _b, f=fn: (pop.popdown(), f()))
                    box.append(b)
            pop.set_child(box)
            pop.set_parent(widget)
            pop.connect("closed", lambda p: GLib.idle_add(p.unparent))
            pop.popup()
        g.connect("pressed", pressed)
        widget.add_controller(g)

    def _is_admin(self):
        srv = CS.get(self.room.split(":")[1]) if self.room.startswith("s:") else None
        return bool(srv) and CS.can_manage(srv)

    def _event(self, m, kind, **kw):
        room = self.room
        if not room.startswith("s:"):                       # direktemelding: til den andre (chat.send_event)
            ev = {"type": kind, "mid": m["id"], **kw}
            _bg(lambda: C.send_event(room, ev), lambda _r: None)
            GLib.timeout_add(150, lambda: (self._load(), False)[1])
            return
        _s, sid, ch = room.split(":", 2)
        ev = {"type": kind, "mid": m["id"], "ch": ch, "from": CS.me()["name"], "from_id": CS.me()["id"], **kw}
        srv = CS.get(sid)
        me_m = (srv or {}).get("members", {}).get(CS.me()["id"])
        C.apply_event(room, ev, me_m)
        _bg(lambda: CS.broadcast(srv, ev), lambda _r: None)
        self._load()

    def _react(self, m, emoji):
        self._event(m, "react", emoji=emoji)

    def _edit(self, m):
        _ask(self.get_root(), "Rediger meldingen", "", [("t", "Melding", m.get("text", ""))],
             lambda v: v["t"] and self._event(m, "edit", text=v["t"]), "Lagre")

    def _set_reply(self, m):
        self.reply_to = m
        self.reply_bar.set_visible(bool(m))
        if m:
            self.reply_lab.set_label(f"↪ {i18n.tr('Svarer')} {m.get('from')}: {str(m.get('text', ''))[:60]}")
            self.entry.grab_focus()

    def _send(self, *_):
        t = self.entry.get_text().strip()
        if not t:
            return
        self.entry.set_text("")
        bg = getattr(self.get_root(), "bg", None)
        if t.startswith("/") and not t.startswith("//"):     # /-kommandoer: /poll /påminn /terning /gif …
            import chatextra as CX

            def cmd():
                return CX.command(self.room, t, self.get_root(), bg.notify if bg else None)

            def done(res):
                if isinstance(res, Exception):
                    self.status.set_label(f"✗ {res}")
                    return
                txt, special = res
                if special and special[0] == "gif":
                    self._gif_dialog(special[1])
                elif txt:
                    self.status.set_label(str(txt)[:300])
                    if t.split()[0].lower() in ("/hjelp", "/help", "/?"):
                        self._help_dialog(txt)
                self._load()
            _bg(cmd, done)
            return
        extra = {"reply": self.reply_to["id"]} if self.reply_to and self.room not in ("hjemme", "meg") else None
        self._set_reply(None)
        self.status.set_label(i18n.tr("Sender …"))
        _bg(lambda: C.send(self.room, t, None, bg.notify if bg else None, extra=extra),
            lambda r: (self.status.set_label(("✗ " if isinstance(r, Exception) else "") + str(r)), self._load()))

    # ------------------------------------------------------------------ servere
    def _guard(self, fn):
        try:
            import familylock
            if familylock.locked():
                familylock.ask(self.get_root(), "Familiekontroll er på – en voksen må godkjenne nye servere og venner.",
                               fn)
                return
        except Exception:  # noqa: BLE001
            pass
        fn()

    def _create(self):
        self._guard(self._create2)

    def _create2(self):
        def ok(v):
            def done(srv):
                if isinstance(srv, Exception):
                    self.status.set_label(f"✗ {srv}")
                    return
                self._open(srv["id"])
            _bg(lambda: CS.create(v["name"] or "Min server", v["icon"] or "🎮"), done)
        _ask(self.get_root(), "Lag en server", "Du blir eier. Inviter venner med en lenke etterpå.",
             [("name", "Navn på serveren", ""), ("icon", "Ikon (emoji), f.eks. 🎮 🏠 ⚔️ 🐉", "🎮")], ok, "Lag")

    def _join(self):
        self._guard(self._join2)

    def _join2(self):
        _ask(self.get_root(), "Bli med i en server", "Lim inn invitasjonslenken (ks-server://…).",
             [("link", "ks-server://…", "")], lambda v: self._do_join(v["link"]), "Bli med")

    def _do_join(self, link):
        self.status.set_label(i18n.tr("Kobler til eieren …"))

        def done(srv):
            if isinstance(srv, Exception):
                self.status.set_label(f"✗ {srv}")
                return
            self.status.set_label(f"✓ Du er med i {srv['name']}")
            self._open(srv["id"])
        import re
        m = re.search(r"ks-server://\S+", link or "")
        _bg(lambda: CS.join(m.group(0) if m else link), done)

    def _server_menu(self, srv):
        pop = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=6, margin_bottom=6, margin_start=6,
                      margin_end=6)
        sid = srv["id"]
        manage = CS.can_manage(srv)
        owner = CS.my_role(srv) == "owner"
        items = [("🔗 Inviter (lag lenke)", self._invite, manage),
                 ("✉️ Send invitasjon til en venn", self._invite_friend, manage),
                 ("# Ny tekstkanal", lambda: self._new_channel("text"), manage),
                 ("🔊 Ny talekanal", lambda: self._new_channel("voice"), manage),
                 ("📁 Ny kategori", lambda: _ask(self.get_root(), "Ny kategori", "", [("n", "Navn", "")],
                                                lambda v: self._call(lambda: CS.add_category(sid, v["n"]))), manage),
                 ("✏️ Rediger kanalen", self._edit_channel, manage),
                 ("🗑️ Slett kanalen", lambda: self._call(lambda: CS.delete_channel(sid, self.room.split(":")[2])),
                  manage and self.room.startswith(f"s:{sid}:")),
                 ("🏷️ Endre navn og ikon", lambda: _ask(self.get_root(), "Serveren", "", [
                     ("n", "Navn", srv["name"]), ("i", "Ikon", srv.get("icon", ""))],
                     lambda v: self._call(lambda: CS.rename(sid, v["n"], v["i"]))), manage),
                 ("👥 Medlemmer og roller", self._members_dialog, manage),
                 ("🔕 Demp kanalen (1 time / av)", self._toggle_mute, True),
                 ("🚪 Forlat serveren", lambda: self._call(lambda: CS.leave(sid), back=True), not owner),
                 ("💥 Slett serveren", lambda: self._confirm("Slette serveren for alle?",
                                                            lambda: self._call(lambda: CS.delete_server(sid),
                                                                               back=True)), owner)]
        for label, fn, ok in items:
            if not ok:
                continue
            b = Gtk.Button(label=i18n.tr(label))
            b.add_css_class("flat")
            b.get_child().set_xalign(0)
            b.connect("clicked", lambda _b, f=fn: (pop.popdown(), f()))
            box.append(b)
        pop.set_child(box)
        return pop

    def _call(self, fn, back=False):
        def done(r):
            if isinstance(r, Exception):
                self.status.set_label(f"✗ {r}")
                return
            if back:
                self._open("direct")
            else:
                self._channels()
        _bg(fn, done)

    def _confirm(self, q, fn):
        dlg = Adw.AlertDialog(heading=i18n.tr(q))
        dlg.add_response("nei", i18n.tr("Avbryt"))
        dlg.add_response("ja", i18n.tr("Ja"))
        dlg.set_response_appearance("ja", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.connect("response", lambda _d, r: r == "ja" and fn())
        dlg.present(self.get_root())

    def _invite(self):
        def done(link):
            if isinstance(link, Exception):
                self.status.set_label(f"✗ {link}")
                return
            Gdk.Display.get_default().get_clipboard().set(link)
            self.status.set_label(i18n.tr("Invitasjonslenken er kopiert – send den til vennen (gjelder i 7 dager)"))
        _bg(lambda: CS.make_invite(self.view), done)

    def _invite_friend(self):
        import friends
        names = [f["name"] for f in friends.cfg()["friends"]]
        try:
            import homepcs
            import savegames
            names += [p["name"] for p in homepcs.fetch() or [] if p.get("name") != savegames.pc_name()]
        except Exception:  # noqa: BLE001
            pass
        if not names:
            self.status.set_label(i18n.tr("Ingen venner eller PC-er å invitere ennå"))
            return
        dlg = Adw.AlertDialog(heading=i18n.tr("Send invitasjon til"))
        dd = Gtk.DropDown.new_from_strings(names)
        dlg.set_extra_child(dd)
        dlg.add_response("nei", i18n.tr("Avbryt"))
        dlg.add_response("ja", i18n.tr("Send"))
        dlg.set_response_appearance("ja", Adw.ResponseAppearance.SUGGESTED)

        def go():
            who = names[dd.get_selected()]
            srv = CS.get(self.view)
            _bg(lambda: C.send(f"p:{who}", f"Bli med i serveren {srv.get('icon', '')} {srv['name']}: "
                                           f"{CS.make_invite(self.view)}"),
                lambda r: self.status.set_label(("✗ " if isinstance(r, Exception) else "✓ ") + str(r)))
        dlg.connect("response", lambda _d, r: r == "ja" and go())
        dlg.present(self.get_root())

    def _new_channel(self, kind="text", cid=None):
        """Ny tekst- eller talekanal. Uten kategori: velg den i lista (ingen nedtrekksliste – den kunne gjemme seg
        bak dialogen)."""
        srv = CS.get(self.view)
        if not srv:
            return
        cats = srv.get("categories", [])
        if not cats:
            CS.add_category(self.view, "Talekanaler" if kind == "voice" else "Tekstkanaler")
            cats = CS.get(self.view)["categories"]
        voice = kind == "voice"
        dlg = Adw.AlertDialog(heading=i18n.tr("Ny talekanal" if voice else "Ny tekstkanal"))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        name = Gtk.Entry(placeholder_text=i18n.tr("navn, f.eks. " + ("raid-prat" if voice else "cs2-kveld")),
                         activates_default=True)
        topic = Gtk.Entry(placeholder_text=i18n.tr("Emne (valgfritt)"))
        box.append(name)
        box.append(topic)
        picked = {"cid": cid or cats[0]["id"]}
        if not cid and len(cats) > 1:
            box.append(Gtk.Label(label=i18n.tr("Kategori"), xalign=0))
            group = None
            for c in cats:
                rb = Gtk.CheckButton(label=c["name"], active=c["id"] == picked["cid"])
                if group:
                    rb.set_group(group)
                group = group or rb
                rb.connect("toggled", lambda b, i=c["id"]: b.get_active() and picked.update(cid=i))
                box.append(rb)
        elif cid:
            box.append(_dim(i18n.tr("I kategorien ") + next((c["name"] for c in cats if c["id"] == cid), "")))
        dlg.set_extra_child(box)
        dlg.add_response("nei", i18n.tr("Avbryt"))
        dlg.add_response("ja", i18n.tr("Lag"))
        dlg.set_default_response("ja")
        dlg.set_response_appearance("ja", Adw.ResponseAppearance.SUGGESTED)
        dlg.connect("response", lambda _d, r: r == "ja" and self._call(lambda: CS.add_channel(
            self.view, picked["cid"], name.get_text() or ("lounge" if voice else "kanal"), topic.get_text(), kind)))
        dlg.present(self.get_root())
        name.grab_focus()

    def _edit_channel(self):
        if not self.room.startswith(f"s:{self.view}:"):
            return
        srv = CS.get(self.view)
        chid = self.room.split(":")[2]
        ch = CS.channel(srv, chid) or {}
        _ask(self.get_root(), "Rediger kanalen", "", [("n", "Navn", ch.get("name", "")), ("t", "Emne", ch.get("topic", ""))],
             lambda v: self._call(lambda: CS.edit_channel(self.view, chid, v["n"], v["t"])), "Lagre")

    def _toggle_mute(self):
        CS.set_mute(self.room, 0 if CS.muted(self.room) else 3600)
        self._channels()

    def _members_dialog(self):
        srv = CS.get(self.view)
        dlg = Adw.Dialog(title=i18n.tr("Medlemmer"), content_width=440, content_height=420)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=16, margin_bottom=16,
                      margin_start=16, margin_end=16)
        owner = CS.my_role(srv) == "owner"
        for mid, m in srv.get("members", {}).items():
            r = Gtk.Box(spacing=8)
            badge = {"owner": "👑 eier", "admin": "🛡️ admin"}.get(m.get("role"), "medlem")
            r.append(Gtk.Label(label=f"{m.get('name')}  ·  {badge}", xalign=0, hexpand=True))
            if mid != srv["owner"] and mid != CS.me()["id"]:
                if owner:
                    to = "member" if m.get("role") == "admin" else "admin"
                    r.append(_btn("Gjør til medlem" if to == "member" else "Gjør til admin",
                                  lambda _b, x=mid, y=to: (dlg.close(), self._call(lambda: CS.set_role(self.view, x, y)))))
                    r.append(_btn("Gi eierskap", lambda _b, x=mid: (dlg.close(), self._call(
                        lambda: CS.give_owner(self.view, x))), flat=True))
                r.append(_btn("Kast ut", lambda _b, x=mid: (dlg.close(), self._call(lambda: CS.kick(self.view, x)))))
            box.append(r)
        dlg.set_child(Gtk.ScrolledWindow(child=box, vexpand=True))
        dlg.present(self.get_root())
