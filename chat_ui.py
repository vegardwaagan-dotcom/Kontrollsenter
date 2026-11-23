"""Chat-siden – som Discord: serverlist til venstre (Direkte + dine servere), kanaler i kategorier, meldinger og
medlemmer. Lag server, bli med via lenke, inviter venner, administrer kanaler, roller og medlemmer."""
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

import chat as C  # noqa: E402
import chatsrv as CS  # noqa: E402
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
        self.msgs = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.scroll = Gtk.ScrolledWindow(child=self.msgs, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        right.append(self.scroll)
        self.reply_bar = Gtk.Box(spacing=6, visible=False)
        self.reply_lab = _dim("")
        self.reply_lab.set_hexpand(True)
        self.reply_bar.append(self.reply_lab)
        self.reply_bar.append(_btn("✕", lambda *_: self._set_reply(None), flat=True))
        right.append(self.reply_bar)
        row = Gtk.Box(spacing=8)
        self.entry = Gtk.Entry(placeholder_text=i18n.tr("Skriv en melding …"), hexpand=True, max_length=2000)
        self.entry.connect("activate", self._send)
        row.append(self.entry)
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
        C.on_message(lambda room, _m: (room == self.room and self._load(), self._rail()))
        CS.on_change(lambda sid: (self._rail(), sid == self.view and self._channels()))
        self._rail()
        self._channels(select=True)
        GLib.timeout_add_seconds(15, lambda: (self.get_mapped() and (self._channels(), self._load()), True)[1])

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
            add(srv.get("icon", "🎮"), srv.get("name", "Server"), lambda s=sid: self._open(s), self.view == sid)
        self.rail.append(Gtk.Separator())
        add("➕", "Lag en server", self._create)
        add("🔗", "Bli med i en server (lim inn invitasjonslenke)", self._join)
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
                self._rooms = [r for r in rs if not r[0].startswith("s:")]
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
        self.list.append(row)

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
            self.members.append(Gtk.Label(label=badge + m.get("name", "?") + (" (deg)" if mid == CS.me()["id"] else ""),
                                          xalign=0, ellipsize=3))

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
            who = Gtk.Label(label=("" if mine else f"{m.get('from')}  ·  ") +
                            time.strftime("%d.%m %H:%M", time.localtime(m.get("t", 0))) +
                            ("  (redigert)" if m.get("edited") else "") + ("  📌" if m.get("pinned") else ""),
                            xalign=1 if mine else 0)
            who.add_css_class("ks-chat-who")
            col.append(who)
            if m.get("reply") and by_id.get(m["reply"]):
                q = by_id[m["reply"]]
                ql = _dim(f"↪ {q.get('from')}: {str(q.get('text', ''))[:60]}")
                col.append(ql)
            text = i18n.tr("(slettet)") if m.get("deleted") else m.get("text", "")
            t = Gtk.Label(label=text, wrap=True, xalign=0, selectable=True, max_width_chars=60)
            t.add_css_class("ks-chat-me" if mine else "ks-chat-other")
            col.append(t)
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
        q = C.queued_count()
        self.status.set_label(i18n.tr("{n} meldinger venter på at mottakeren skal bli på igjen").replace(
            "{n}", str(q)) if q else "")
        GLib.timeout_add(60, lambda: (self.scroll.get_vadjustment().set_value(1e9), False)[1])
        if self.view != "direct":                       # oppdater «uleste» nå som kanalen er lest
            GLib.idle_add(lambda: (self._channels(), False)[1])

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
    def _create(self):
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
