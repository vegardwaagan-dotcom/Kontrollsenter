"""Chat-siden: rom til venstre (Hjemme, Alle, privat), meldinger og skrivefelt til høyre."""
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk  # noqa: E402

import chat as C  # noqa: E402
import i18n  # noqa: E402

_CSS = """
.ks-chat-me { background: alpha(@accent_bg_color, 0.85); color: @accent_fg_color; border-radius: 16px 16px 4px 16px;
  padding: 8px 12px; }
.ks-chat-other { background: alpha(@window_fg_color, 0.08); border-radius: 16px 16px 16px 4px; padding: 8px 12px; }
.ks-chat-who { font-size: 0.8em; opacity: 0.7; }
.ks-chat-rooms row { padding: 6px 4px; }
"""


def _bg(fn, done):
    def work():
        try:
            r = fn()
        except Exception as e:  # noqa: BLE001
            r = e
        GLib.idle_add(lambda: (done(r), False)[1])
    threading.Thread(target=work, daemon=True).start()


class ChatPage(Gtk.Box):
    def __init__(self):
        super().__init__(spacing=0)
        try:
            import theme
            theme.add_css(_CSS)
        except Exception:  # noqa: BLE001
            pass
        self.room = "alle"
        self._rooms = []
        # rom
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, width_request=240, hexpand=False)
        for side in ("top", "bottom", "start"):
            getattr(left, f"set_margin_{side}")(12)
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.list.add_css_class("navigation-sidebar")
        self.list.add_css_class("ks-chat-rooms")
        self.list.connect("row-selected", self._pick)
        sc = Gtk.ScrolledWindow(child=self.list, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER,
                                propagate_natural_width=False, hexpand=False)
        sc.set_size_request(240, -1)
        left.append(sc)
        hint = Gtk.Label(label=i18n.tr("Venner legges til under PC-er utenfor hjemmet. Bare vennene dine kan skrive "
                                       "til deg."), wrap=True, xalign=0, max_width_chars=28)
        hint.add_css_class("dim-label")
        hint.add_css_class("caption")
        left.append(hint)
        self.append(left)
        self.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        # meldinger
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, hexpand=True)
        for side in ("top", "bottom", "start", "end"):
            getattr(right, f"set_margin_{side}")(12)
        self.title = Gtk.Label(xalign=0)
        self.title.add_css_class("title-3")
        right.append(self.title)
        self.msgs = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.scroll = Gtk.ScrolledWindow(child=self.msgs, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        right.append(self.scroll)
        row = Gtk.Box(spacing=8)
        self.entry = Gtk.Entry(placeholder_text=i18n.tr("Skriv en melding …"), hexpand=True, max_length=500)
        self.entry.connect("activate", self._send)
        row.append(self.entry)
        b = Gtk.Button(label=i18n.tr("Send"))
        b.add_css_class("suggested-action")
        b.add_css_class("pill")
        b.connect("clicked", self._send)
        row.append(b)
        right.append(row)
        self.status = Gtk.Label(xalign=0)
        self.status.add_css_class("dim-label")
        self.status.add_css_class("caption")
        right.append(self.status)
        self.append(right)
        C.on_message(lambda room, _m: (self._load_rooms(), room == self.room and self._load()))
        self._load_rooms(select=True)
        GLib.timeout_add_seconds(15, lambda: (self.get_mapped() and (self._load_rooms(), self._load()), True)[1])

    def _load_rooms(self, select=False):
        def done(rs):
            if isinstance(rs, Exception):
                return
            self._rooms = rs
            cur = self.room
            self._building = True
            while (c := self.list.get_first_child()) is not None:
                self.list.remove(c)
            for rid, name, icon, unread in rs:
                r = Gtk.Box(spacing=8)
                r.append(Gtk.Label(label=icon))
                r.append(Gtk.Label(label=name, xalign=0, hexpand=True, ellipsize=3))
                if unread:
                    u = Gtk.Label(label=str(unread))
                    u.add_css_class("ks-chip")
                    r.append(u)
                row = Gtk.ListBoxRow(child=r)
                row._rid = rid
                self.list.append(row)
                if rid == cur:
                    self.list.select_row(row)
            self._building = False
            if select:
                self._load()
        _bg(C.rooms, done)
        return False

    def _pick(self, _l, row):
        if row is None or getattr(self, "_building", False):
            return
        self.room = row._rid
        self._load()

    def _load(self):
        room = self.room
        name = next((n for r, n, _i, _u in self._rooms if r == room), room)
        self.title.set_label(name)

        def work():
            m = C.messages(room, 120)
            C.mark_read(room)
            return m

        def done(msgs):
            if isinstance(msgs, Exception) or room != self.room:
                return
            while (c := self.msgs.get_first_child()) is not None:
                self.msgs.remove(c)
            if not msgs:
                e = Gtk.Label(label=i18n.tr("Ingen meldinger her ennå – si hei! 👋"), vexpand=True)
                e.add_css_class("dim-label")
                self.msgs.append(e)
            import savegames
            me = savegames.pc_name()
            for m in msgs:
                mine = m.get("pc", m.get("from")) == me or m.get("from") == me
                col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2,
                              halign=Gtk.Align.END if mine else Gtk.Align.START)
                who = Gtk.Label(label=("" if mine else f"{m.get('from')}  ·  ") +
                                time.strftime("%d.%m %H:%M", time.localtime(m.get("t", 0))),
                                xalign=1 if mine else 0)
                who.add_css_class("ks-chat-who")
                col.append(who)
                t = Gtk.Label(label=m.get("text", ""), wrap=True, xalign=0, selectable=True, max_width_chars=60)
                t.add_css_class("ks-chat-me" if mine else "ks-chat-other")
                col.append(t)
                self.msgs.append(col)
            q = C.queued_count()
            self.status.set_label(i18n.tr("{n} meldinger venter på at mottakeren skal bli på igjen").replace(
                "{n}", str(q)) if q else "")
            GLib.timeout_add(60, lambda: (self.scroll.get_vadjustment().set_value(1e9), False)[1])
            self._load_rooms()
        _bg(work, done)
        return False

    def _send(self, *_):
        t = self.entry.get_text().strip()
        if not t:
            return
        self.entry.set_text("")
        root = self.get_root()
        bg = getattr(root, "bg", None)
        self.status.set_label(i18n.tr("Sender …"))
        _bg(lambda: C.send(self.room, t, None, bg.notify if bg else None),
            lambda r: (self.status.set_label(("✗ " if isinstance(r, Exception) else "") + str(r)), self._load()))
