"""Chat-siden – som Discord: serverlist til venstre (Direkte + dine servere), kanaler i kategorier, meldinger og
medlemmer. Lag server, bli med via lenke, inviter venner, administrer kanaler, roller og medlemmer."""
import os
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

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
.ks-chan row { padding: 4px 6px; border-radius: 8px; }
.ks-react { padding: 0 6px; min-height: 22px; border-radius: 11px; font-size: .9em; }
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
        ls = Gtk.ScrolledWindow(child=self.list, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER,
                                propagate_natural_width=False)
        ls.set_size_request(240, -1)
        mid.append(ls)
        self.mid_hint = _dim("")
        self.mid_hint.set_max_width_chars(28)
        mid.append(self.mid_hint)
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
        right.append(th)
        self.callbar = Gtk.Box(spacing=8, visible=False)
        self.callbar.add_css_class("card")
        self.call_lab = Gtk.Label(xalign=0, hexpand=True, margin_start=12)
        self.callbar.append(self.call_lab)
        self.call_ans = _btn("📞 Svar", lambda *_: self._call_do(CV.call_answer), True)
        self.callbar.append(self.call_ans)
        self.callbar.append(_btn("Legg på", lambda *_: self._call_do(CV.call_end)))
        right.append(self.callbar)
        self.gamebar = Gtk.Box(spacing=8, visible=False)
        self.game_lab = _dim("")
        self.game_lab.set_hexpand(True)
        self.gamebar.append(self.game_lab)
        self.gamebar.append(_btn("Send til alle som spiller", self._to_players, flat=True))
        right.append(self.gamebar)
        self.msgs = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.scroll = Gtk.ScrolledWindow(child=self.msgs, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        right.append(self.scroll)
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
        self.status = _dim("")
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
        for sid, srv in sorted(CS.servers().items(), key=lambda kv: kv[1].get("created", 0)):
            add(_short_icon(srv.get("icon"), srv.get("name", "Server")), srv.get("name", "Server"),
                lambda s=sid: self._open(s), self.view == sid)
        self.rail.append(Gtk.Separator())
        add("➕", "Lag en server", self._create)
        add("🔗", "Bli med i en server (lim inn invitasjonslenke)", self._join)
        add("🔍", "Søk i alle samtalene", self._search)
        add("👤", "Profil, status og chat-innstillinger", self._profile)
        return False

    def _open(self, view):
        self.view = view
        self._rail()
        self._channels(select=True)

    # ------------------------------------------------------------------ kanaler
    def _channels(self, select=False):
        self._building = True
        while (c := self.list.get_first_child()) is not None:
            self.list.remove(c)
        if self.view == "direct":
            self.head.set_label(i18n.tr("Direkte"))
            self.gear.set_visible(False)
            self.mem_btn.set_visible(False)
            self.members_rev.set_reveal_child(False)
            self.mid_hint.set_label(i18n.tr("Venner legges til under PC-er utenfor hjemmet. Bare vennene dine kan "
                                            "skrive til deg."))

            def done(rs):
                if isinstance(rs, Exception):
                    return
                pins = CP.cfg()["pinned_rooms"]
                self._rooms = sorted([r for r in rs if not r[0].startswith("s:")], key=lambda r: r[0] not in pins)
                self._building = True
                while (c := self.list.get_first_child()) is not None:
                    self.list.remove(c)
                for rid, name, icon, unread in self._rooms:
                    self._row(rid, f"{icon}  {name}", unread)
                if select and not self.room.startswith("s:") and self.room not in [r[0] for r in self._rooms]:
                    self.room = "alle"
                if select and self.room.startswith("s:"):
                    self.room = "alle"
                self._select_current()
                self._building = False
                if select:
                    self._load()
            _bg(C.rooms, done)
            return
        srv = CS.get(self.view)
        if not srv:
            self._open("direct")
            return
        self.head.set_label(f"{srv.get('icon', '')} {srv['name']}")
        self.gear.set_visible(True)
        self.gear.set_popover(self._server_menu(srv))
        self.mem_btn.set_visible(True)
        self.mid_hint.set_label("")
        read = (C._load(C.FILE, {}).get("_read") or {})
        first = None
        for cat in srv.get("categories", []):
            lab = Gtk.Label(label=cat["name"].upper(), xalign=0)
            lab.add_css_class("ks-chan-cat")
            r = Gtk.ListBoxRow(child=lab, selectable=False, activatable=False)
            self.list.append(r)
            for ch in cat.get("channels", []):
                rid = f"s:{srv['id']}:{ch['id']}"
                first = first or rid
                unread = sum(1 for m in C.messages(rid, 100) if m.get("t", 0) > read.get(rid, 0)
                             and m.get("from_id") != CS.me()["id"])
                self._row(rid, f"#  {ch['name']}" + ("  🔕" if CS.muted(rid) else ""), unread)
        if select or not self.room.startswith(f"s:{srv['id']}:"):
            self.room = first or self.room
        self._select_current()
        self._show_members(srv)
        self._building = False
        if select:
            self._load()

    def _row(self, rid, text, unread):
        r = Gtk.Box(spacing=8)
        r.append(Gtk.Label(label=text, xalign=0, hexpand=True, ellipsize=3))
        if unread:
            u = Gtk.Label(label=str(unread))
            u.add_css_class("ks-chip")
            r.append(u)
        row = Gtk.ListBoxRow(child=r)
        row._rid = rid
        if rid.startswith("p:") or rid in ("alle", "hjemme", "meg"):
            g = Gtk.GestureClick(button=3)
            g.connect("pressed", lambda *_a, rr=rid, w=row: self._room_menu(w, rr))
            row.add_controller(g)
        self.list.append(row)

    def _member_menu(self, widget, m):
        pop = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=6, margin_bottom=6, margin_start=6,
                      margin_end=6)
        items = [("📞 Ring med tale", lambda: self._call_do(lambda: CV.call_start(m, self.room)), CV.calls_ok()),
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
        if rid.startswith("p:"):
            name = rid[2:]
            items += [("🔕 Demp 1 time / av", lambda: CS.set_mute(rid, 0 if CS.muted(rid) else 3600)),
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
        self.room = row._rid
        self._load()

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
            row.append(Gtk.Label(label=f"{icon} {av + ' ' if av else ''}{badge}{m.get('name', '?')}" +
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
        if room.startswith("s:"):
            srv = CS.get(room.split(":")[1]) or {}
            ch = CS.channel(srv, room.split(":")[2]) or {}
            self.title.set_label(f"# {ch.get('name', '?')}")
            self.topic.set_label(ch.get("topic", ""))
        else:
            self.title.set_label(next((n for r, n, _i, _u in self._rooms if r == room), room))
            self.topic.set_label("")

        def work():
            m = C.messages(room, 150)
            C.mark_read(room)
            if room.startswith("s:") and time.time() - getattr(self, "_rd", {}).get(room, 0) > 20:
                self.__dict__.setdefault("_rd", {})[room] = time.time()
                CP.mark_read(room)
            return m
        _bg(work, lambda msgs: self._show(room, msgs))
        return False

    def _show(self, room, msgs):
        if isinstance(msgs, Exception) or room != self.room:
            return
        while (c := self.msgs.get_first_child()) is not None:
            self.msgs.remove(c)
        if not msgs:
            e = Gtk.Label(label=i18n.tr("Ingen meldinger her ennå – si hei! 👋"), vexpand=True)
            e.add_css_class("dim-label")
            self.msgs.append(e)
        import savegames
        me_pc, me_id = savegames.pc_name(), CS.me()["id"]
        by_id = {m.get("id"): m for m in msgs}
        for m in msgs:
            if str(m.get("from", "")).startswith("🤖"):
                lab = Gtk.Label(label=m.get("text", ""), xalign=0.5, wrap=True)
                lab.add_css_class("ks-chat-sys")
                lab.add_css_class("caption")
                self.msgs.append(lab)
                continue
            mine = m.get("from_id") == me_id or (not m.get("from_id") and (m.get("pc") == me_pc or
                                                                            m.get("from") == me_pc))
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2,
                          halign=Gtk.Align.END if mine else Gtk.Align.START)
            av, colr = CL.avatar(m.get("from_id")) if m.get("from_id") else ("", "")
            who = Gtk.Label(label=("" if mine else f"{av + ' ' if av else ''}{m.get('from')}  ·  ") +
                            time.strftime("%d.%m %H:%M", time.localtime(m.get("t", 0))) +
                            ("  (redigert)" if m.get("edited") else "") + ("  📌" if m.get("pinned") else "") +
                            ("  🔒" if m.get("e2e") else ""),
                            xalign=1 if mine else 0)
            who.add_css_class("ks-chat-who")
            col.append(who)
            if m.get("reply") and by_id.get(m["reply"]):
                q = by_id[m["reply"]]
                ql = _dim(f"↪ {q.get('from')}: {str(q.get('text', ''))[:60]}")
                col.append(ql)
            text = i18n.tr("(slettet)") if m.get("deleted") else CL.clean(m.get("text", ""))
            if colr and not mine:
                who.add_css_class("accent")
            t = Gtk.Label(label=text, wrap=True, xalign=0, selectable=True, max_width_chars=60)
            t.add_css_class("ks-chat-me" if mine else "ks-chat-other")
            col.append(t)
            if not m.get("deleted"):
                self._extras(col, room, m, mine)
            if "ks-server://" in text and not m.get("deleted"):
                col.append(_btn("Bli med i serveren", lambda _b, x=text: self._do_join(x), True))
            if m.get("reactions"):
                rr = Gtk.Box(spacing=4, halign=Gtk.Align.END if mine else Gtk.Align.START)
                for e, who_l in m["reactions"].items():
                    b = Gtk.Button(label=f"{e} {len(who_l)}", tooltip_text=", ".join(who_l))
                    b.add_css_class("ks-react")
                    b.connect("clicked", lambda _b, mm=m, ee=e: self._react(mm, ee))
                    rr.append(b)
                col.append(rr)
            if room.startswith("s:") and not m.get("deleted"):
                self._menu_for(col, m, mine)
            self.msgs.append(col)
        mine_last = [m for m in msgs if m.get("from_id") == me_id and not m.get("deleted")]
        if room.startswith("s:") and mine_last:
            rc = _dim(CP.receipt(room, mine_last[-1]))
            rc.set_xalign(1)
            self.msgs.append(rc)
        if msgs and CP.is_celebration(msgs[-1].get("text")) and time.time() - msgs[-1].get("t", 0) < 30:
            self._confetti()
        q = C.queued_count()
        self.status.set_label(i18n.tr("{n} meldinger venter på at mottakeren skal bli på igjen").replace(
            "{n}", str(q)) if q else "")
        GLib.timeout_add(60, lambda: (self.scroll.get_vadjustment().set_value(1e9), False)[1])
        if self.view != "direct":                       # oppdater «uleste» nå som kanalen er lest
            GLib.idle_add(lambda: (self._channels(), False)[1])

    def _extras(self, col, room, m, mine):
        """Vedlegg, avstemning, avtale og lenker under en melding."""
        al = Gtk.Align.END if mine else Gtk.Align.START
        att = m.get("attach")
        if att:
            path = CP.file_path(att)
            if att.get("kind") == "image" and path:
                pic = Gtk.Picture.new_for_filename(path)
                pic.set_size_request(*((110, 110) if m.get("kind") == "sticker" else (260, 180)))
                pic.set_content_fit(Gtk.ContentFit.CONTAIN)
                pic.set_halign(al)
                col.append(pic)
            elif att.get("kind") == "audio":
                col.append(_btn("▶ Spill av", lambda _b, p=path: CP.play(p), flat=True))
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
        import re
        for url in re.findall(r"https?://\S+", m.get("text", ""))[:2]:
            if "/api/clipfile" in url:
                col.append(_btn("🎬 Se klippet", lambda _b, u=url: self._open_url(u), True))
            else:
                b = _btn("🔗 " + url[:50], lambda _b, u=url: self._open_url(u), flat=True)
                col.append(b)
                _bg(lambda u=url: CL.link_title(u), lambda t, bb=b: t and not isinstance(t, Exception) and
                    bb.set_label("🔗 " + t[:70]))

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

    def _bars(self):
        st = CV.call_state()
        self.callbar.set_visible(bool(st))
        if st:
            self.call_lab.set_label(st)
            self.call_ans.set_visible(bool(CV._CALL.get("incoming")))
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

    def _need_server(self):
        if not self.room.startswith("s:"):
            self.status.set_label(i18n.tr("Dette virker i serverkanaler – lag en server med ➕"))
            return False
        return True

    def _attach(self, *_):
        if not self._need_server():
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
        if not self._need_server():
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
            ("Verktøy", (("⏰ Påminnelse", self._remind), ("🕒 Send senere", self._schedule),
                         ("📝 Notater", self._notes), ("🛒 Handleliste", self._shop),
                         ("🌐 Oversett siste melding", self._translate),
                         ("🏠 Hvor er alle?", lambda: self.status.set_label(CL.where_is_everyone())),
                         ("🎲 Terning", lambda: self._call_room(lambda: CP.dice(self.room))),
                         ("✊ Stein–saks–papir", self._rps))),
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
        if not (state & Gdk.ModifierType.CONTROL_MASK) or keyval not in (Gdk.KEY_v, Gdk.KEY_V):
            return False
        cb = Gdk.Display.get_default().get_clipboard()
        if not cb.get_formats().contain_gtype(Gdk.Texture) or not self.room.startswith("s:"):
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
        if not self._need_server():
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
        _s, sid, ch = room.split(":", 2)
        ev = {"type": kind, "mid": m["id"], "ch": ch, "from": CS.me()["name"], "from_id": CS.me()["id"], **kw}
        srv = CS.get(sid)
        me_m = (srv or {}).get("members", {}).get(CS.me()["id"])
        C.apply_event(room, ev, me_m)
        _bg(lambda: CS.broadcast(srv, ev), lambda _r: None)
        self._load()

    def _react(self, m, emoji):
        if self.room.startswith("s:"):
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
        extra = {"reply": self.reply_to["id"]} if self.reply_to and self.room.startswith("s:") else None
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
                 ("➕ Ny kanal", self._new_channel, manage),
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

    def _new_channel(self):
        srv = CS.get(self.view)
        cats = srv.get("categories", [])
        if not cats:
            CS.add_category(self.view, "Tekstkanaler")
            srv = CS.get(self.view)
            cats = srv["categories"]
        dlg = Adw.AlertDialog(heading=i18n.tr("Ny kanal"))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        name = Gtk.Entry(placeholder_text=i18n.tr("navn, f.eks. cs2-kveld"))
        topic = Gtk.Entry(placeholder_text=i18n.tr("Emne (valgfritt)"))
        dd = Gtk.DropDown.new_from_strings([c["name"] for c in cats])
        for w in (name, topic, dd):
            box.append(w)
        dlg.set_extra_child(box)
        dlg.add_response("nei", i18n.tr("Avbryt"))
        dlg.add_response("ja", i18n.tr("Lag"))
        dlg.set_response_appearance("ja", Adw.ResponseAppearance.SUGGESTED)
        dlg.connect("response", lambda _d, r: r == "ja" and self._call(lambda: CS.add_channel(
            self.view, cats[dd.get_selected()]["id"], name.get_text(), topic.get_text())))
        dlg.present(self.get_root())

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
