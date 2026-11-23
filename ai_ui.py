"""AI-siden – som iMessage: samtalene til venstre, bobler i midten, skrivefeltet nederst.

Samtalene og arbeidsmappa ligger på NAS-en (eller lokalt) – se ai_store.py. Assistenten styrer Kontrollsenter med
«ks» (ai_bridge.py): leser temperaturer, endrer innstillinger, retter feil og sier hvor ting ligger.
"""
import os
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

import ai  # noqa: E402
import ai_store as S  # noqa: E402
import i18n  # noqa: E402

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CSS = """
.ks-bub-me { background: #0a84ff; color: #ffffff; border-radius: 18px 18px 5px 18px; padding: 8px 13px; }
.ks-bub-ai { background: alpha(@window_fg_color, 0.11); border-radius: 18px 18px 18px 5px; padding: 8px 13px; }
.ks-bub-me label, .ks-bub-ai label { font-size: 1.02em; }
.ks-code { font-family: monospace; font-size: 0.92em; background: alpha(#000000, 0.28); border-radius: 8px;
  padding: 6px 9px; }
.ks-bub-time { font-size: 0.78em; opacity: 0.55; margin: 8px 0 2px; }
.ks-bub-who { font-size: 0.75em; opacity: 0.6; margin: 0 10px; }
.ks-ai-input { border-radius: 22px; background: alpha(@window_fg_color, 0.08); padding: 3px 4px 3px 14px; }
.ks-send-round { border-radius: 999px; min-width: 34px; min-height: 34px; padding: 0; background: #0a84ff;
  color: #ffffff; font-weight: 800; }
.ks-send-round:disabled { background: alpha(@window_fg_color, 0.15); }
.ks-ai-side { background: alpha(@window_fg_color, 0.035); }
.ks-typing { font-size: 1.3em; letter-spacing: 3px; opacity: 0.7; }
.ks-transparent, .ks-transparent text { background: transparent; }
"""


def _bg(fn, done):
    def work():
        try:
            r = fn()
        except Exception as e:  # noqa: BLE001
            r = e
        GLib.idle_add(lambda: (done(r), False)[1])
    threading.Thread(target=work, daemon=True).start()


def _dim(t, small=False):
    lab = Gtk.Label(label=i18n.tr(t), xalign=0, ellipsize=Pango.EllipsizeMode.END)
    lab.add_css_class("dim-label")
    if small:
        lab.add_css_class("caption")
    return lab


def _when(t):
    lt, now = time.localtime(t), time.localtime()
    if lt.tm_yday == now.tm_yday and lt.tm_year == now.tm_year:
        return time.strftime("%H:%M", lt)
    if time.time() - t < 6 * 86400:
        return ["man.", "tir.", "ons.", "tor.", "fre.", "lør.", "søn."][lt.tm_wday] + time.strftime(" %H:%M", lt)
    return time.strftime("%d.%m.%Y", lt)


def _bubble_content(text, mine, width=70):
    """Tekst og ```kode``` hver for seg (kode i egen boks med fast bredde). width: tegn per linje i boblene."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    parts = text.split("```")
    for i, part in enumerate(parts):
        part = part.strip("\n")
        if not part.strip():
            continue
        code = i % 2 == 1
        if code and "\n" in part and not part.split("\n", 1)[0].strip().count(" "):
            first, rest = part.split("\n", 1)                # «```python» – språknavnet
            part = rest if first.strip().isidentifier() else part
        lab = Gtk.Label(label=part, xalign=0, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, selectable=True,
                        max_width_chars=width if not code else int(width * 1.3))
        if code:
            lab.add_css_class("ks-code")
        box.append(lab)
    return box


class AiPage(Gtk.Box):
    def __init__(self):
        super().__init__(spacing=0)
        try:
            import theme
            theme.add_css(CSS)
        except Exception:  # noqa: BLE001
            pass
        c = ai.cfg()
        self.tools = list(ai.TOOLS)
        self.tool = c["tool"] if c["tool"] in ai.TOOLS else "claude"
        self.conv = None
        self.proc = None
        self._st = {}
        self._buf = []
        self._live = None

        # ======== venstre: samtalene
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, width_request=170)
        self.side = side
        side.add_css_class("ks-ai-side")
        for s_, v in (("top", 12), ("bottom", 10), ("start", 10), ("end", 10)):
            getattr(side, f"set_margin_{s_}")(v)
        sh = Gtk.Box(spacing=6)
        t = Gtk.Label(label=i18n.tr("Samtaler"), xalign=0, hexpand=True)
        t.add_css_class("title-4")
        sh.append(t)
        newb = Gtk.Button(icon_name="document-edit-symbolic", tooltip_text=i18n.tr("Ny samtale"))
        newb.add_css_class("flat")
        newb.connect("clicked", lambda *_: self._new())
        sh.append(newb)
        side.append(sh)
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.list.add_css_class("navigation-sidebar")
        self.list.connect("row-activated", lambda _l, r: self._open(r._cid))
        side.append(Gtk.ScrolledWindow(child=self.list, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER))
        side.append(Gtk.Label(label=i18n.tr("Lagres på"), xalign=0))
        self.store_dd = Gtk.DropDown.new_from_strings([i18n.tr("☁️ NAS (standard)"), i18n.tr("💻 Lokalt på PC-en")])
        self.store_dd.set_selected(1 if S.mode() == "local" else 0)
        self.store_dd.connect("notify::selected", self._store_changed)
        side.append(self.store_dd)
        self.where = _dim("", small=True)
        self.where.set_wrap(True)
        self.where.set_ellipsize(Pango.EllipsizeMode.NONE)
        side.append(self.where)
        ob = Gtk.Button(label=i18n.tr("📂 Åpne arbeidsmappa"))
        ob.add_css_class("flat")
        ob.connect("clicked", lambda *_: Gtk.FileLauncher.new(Gio.File.new_for_path(S.workdir())).launch(
            self.get_root(), None, None))
        side.append(ob)
        # dra i skillet for å gjøre lista smalere/bredere (huskes), ☰ skjuler den helt
        self.paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, hexpand=True, wide_handle=True,
                               shrink_start_child=False, resize_start_child=False, shrink_end_child=False)
        self.paned.set_start_child(side)
        self.paned.set_position(int(c.get("list_width", 260)))
        self.paned.connect("notify::position", self._paned_moved)
        side.set_visible(c.get("list_visible", True))
        self.append(self.paned)

        # ======== høyre: samtalen
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, hexpand=True)
        for s_, v in (("top", 10), ("bottom", 12), ("start", 14), ("end", 14)):
            getattr(right, f"set_margin_{s_}")(v)
        top = Gtk.Box(spacing=8)
        self.icon = Gtk.Image(pixel_size=28)
        self.list_btn = Gtk.ToggleButton(icon_name="sidebar-show-symbolic", active=c.get("list_visible", True),
                                         valign=Gtk.Align.CENTER, tooltip_text=i18n.tr("Vis/skjul samtalene"))
        self.list_btn.add_css_class("flat")
        self.list_btn.connect("toggled", lambda w: (self.side.set_visible(w.get_active()),
                                                    ai.set_(list_visible=w.get_active())))
        top.append(self.list_btn)
        top.append(self.icon)
        self.dd = Gtk.DropDown.new_from_strings([ai.TOOLS[t]["name"] for t in self.tools])
        self.dd.set_selected(self.tools.index(self.tool))
        self.dd.set_valign(Gtk.Align.CENTER)
        self.dd.connect("notify::selected", self._pick_tool)
        top.append(self.dd)
        self.state = _dim("…")
        self.state.set_hexpand(True)
        top.append(self.state)
        self.ctl = Gtk.ToggleButton(label=i18n.tr("🛠️ Styrer appen"), active=c.get("control", True),
                                    valign=Gtk.Align.CENTER,
                                    tooltip_text=i18n.tr("På: assistenten kan lese temperaturer, endre innstillinger, "
                                                         "rette feil og vise hvor ting ligger i Kontrollsenter."))
        self.ctl.add_css_class("flat")
        self.ctl.connect("toggled", lambda w: ai.set_(control=w.get_active()))
        top.append(self.ctl)
        self.edit = Gtk.ToggleButton(label=i18n.tr("✏️ Endre filer"), active=c["allow_edit"], valign=Gtk.Align.CENTER,
                                     tooltip_text=i18n.tr("På: assistenten kan også skrive og endre filer i "
                                                          "arbeidsmappa."))
        self.edit.add_css_class("flat")
        self.edit.connect("toggled", lambda w: ai.set_(allow_edit=w.get_active()))
        top.append(self.edit)
        self.main_btn = Gtk.Button(valign=Gtk.Align.CENTER, visible=False)
        self.main_btn.add_css_class("pill")
        self.main_btn.connect("clicked", lambda *_: self._main_action())
        top.append(self.main_btn)
        self.more = Gtk.MenuButton(icon_name="view-more-symbolic", valign=Gtk.Align.CENTER)
        self.more.add_css_class("flat")
        top.append(self.more)
        right.append(top)
        self.title = Gtk.Label(xalign=0.5, ellipsize=Pango.EllipsizeMode.END)
        self.title.add_css_class("heading")
        right.append(self.title)
        self.msgs = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        for s_ in ("start", "end"):
            getattr(self.msgs, f"set_margin_{s_}")(6)
        self.sc = Gtk.ScrolledWindow(child=self.msgs, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        right.append(self.sc)
        self.status = _dim("", small=True)
        right.append(self.status)
        inrow = Gtk.Box(spacing=6)
        inrow.add_css_class("ks-ai-input")
        self.prompt = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, top_margin=8, bottom_margin=8, accepts_tab=False)
        self.prompt.add_css_class("ks-transparent")
        key = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        key.connect("key-pressed", self._key)
        self.prompt.add_controller(key)
        isc = Gtk.ScrolledWindow(child=self.prompt, hexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER,
                                 propagate_natural_height=True, min_content_height=38, max_content_height=170)
        inrow.append(isc)
        self.send_btn = Gtk.Button(label="↑", valign=Gtk.Align.END, tooltip_text=i18n.tr("Send (Enter)"))
        self.send_btn.add_css_class("ks-send-round")
        self.send_btn.set_margin_bottom(2)
        self.send_btn.connect("clicked", lambda *_: self._send_or_stop())
        inrow.append(self.send_btn)
        right.append(inrow)
        right.append(_dim("Enter sender · Shift+Enter gir ny linje", small=True))
        self.paned.set_end_child(right)
        self._apply_look()

        self._show_tool()
        self.connect("map", lambda *_: self._on_map())

    # ================= samtalelista og lagring
    def _on_map(self):
        self.where.set_label(S.where())
        self._reload_list()
        self.prompt.grab_focus()
        self._refresh()
        _bg(lambda: S.pull(), lambda _r: (self.where.set_label(S.where()), self._reload_list()))

    def _store_changed(self, dd, _p):
        S.set_mode("local" if dd.get_selected() == 1 else "nas")
        self.conv = None
        self._render_conv()
        self.where.set_label(S.where())
        _bg(lambda: S.pull(force=True), lambda _r: (self.where.set_label(S.where()), self._reload_list()))

    def _reload_list(self):
        def done(convs):
            if isinstance(convs, Exception):
                return
            while (c := self.list.get_first_child()) is not None:
                self.list.remove(c)
            for cv in convs:
                row = Gtk.ListBoxRow()
                row._cid = cv["id"]
                b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1, margin_top=4, margin_bottom=4)
                tl = Gtk.Label(label=cv["title"], xalign=0, ellipsize=Pango.EllipsizeMode.END)
                b.append(tl)
                b.append(_dim(f"{_when(cv['updated'])} · {ai.TOOLS.get(cv['tool'], {}).get('name', '')}", True))
                row.set_child(b)
                g = Gtk.GestureClick(button=3)
                g.connect("pressed", lambda *_a, cid=cv["id"], w=row: self._conv_menu(w, cid))
                row.add_controller(g)
                self.list.append(row)
                if self.conv and self.conv["id"] == cv["id"]:
                    self.list.select_row(row)
            if self.conv is None and convs:
                self._open(convs[0]["id"])
            elif self.conv is None:
                self._render_conv()
        _bg(S.conversations, done)

    def _conv_menu(self, widget, cid):
        pop = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=6, margin_bottom=6, margin_start=6,
                      margin_end=6)
        for label, fn in (("✏️ Gi nytt navn", lambda: self._rename(cid)), ("🗑️ Slett samtalen", lambda: self._delete(cid))):
            b = Gtk.Button(label=i18n.tr(label))
            b.add_css_class("flat")
            b.get_child().set_xalign(0)
            b.connect("clicked", lambda _b, f=fn: (pop.popdown(), f()))
            box.append(b)
        pop.set_child(box)
        pop.set_parent(widget)
        pop.connect("closed", lambda p: GLib.idle_add(p.unparent))
        pop.popup()

    def _rename(self, cid):
        cv = S.load(cid) or {}
        dlg = Adw.AlertDialog(heading=i18n.tr("Gi samtalen nytt navn"))
        e = Gtk.Entry(text=cv.get("title", ""))
        dlg.set_extra_child(e)
        dlg.add_response("nei", i18n.tr("Avbryt"))
        dlg.add_response("ja", i18n.tr("Lagre"))
        dlg.set_response_appearance("ja", Adw.ResponseAppearance.SUGGESTED)
        dlg.connect("response", lambda _d, r: r == "ja" and (S.rename(cid, e.get_text()), self._reload_list(),
                                                            self.conv and self.conv["id"] == cid and
                                                            self.title.set_label(e.get_text())))
        dlg.present(self.get_root())

    def _delete(self, cid):
        dlg = Adw.AlertDialog(heading=i18n.tr("Slette samtalen?"))
        dlg.add_response("nei", i18n.tr("Avbryt"))
        dlg.add_response("ja", i18n.tr("Slett"))
        dlg.set_response_appearance("ja", Adw.ResponseAppearance.DESTRUCTIVE)

        def go():
            S.delete(cid)
            if self.conv and self.conv["id"] == cid:
                self.conv = None
            self._reload_list()
        dlg.connect("response", lambda _d, r: r == "ja" and go())
        dlg.present(self.get_root())

    def _new(self):
        if self.proc is not None:
            return
        self.conv = None
        self.list.unselect_all()
        self._render_conv()
        self.prompt.grab_focus()

    def _open(self, cid):
        if self.proc is not None:
            return
        cv = S.load(cid)
        if not cv:
            return
        self.conv = cv
        if cv.get("tool") in self.tools and cv["tool"] != self.tool:
            self.dd.set_selected(self.tools.index(cv["tool"]))
        self._render_conv()

    # ================= boblene
    def _clear(self):
        while (c := self.msgs.get_first_child()) is not None:
            self.msgs.remove(c)

    def _render_conv(self):
        self._clear()
        cv = self.conv
        self.title.set_label(cv["title"] if cv else i18n.tr("Ny samtale"))
        if not cv or not cv.get("messages"):
            hint = Gtk.Label(label=i18n.tr("Spør om hva som helst – f.eks. «Hvor varm er CPU-en?», «Sett viftene på "
                                           "stille», «Hvor slår jeg av varsler?» eller «Hvorfor er PC-en treg?»"),
                             wrap=True, justify=Gtk.Justification.CENTER, max_width_chars=60, vexpand=True,
                             valign=Gtk.Align.CENTER)
            hint.add_css_class("dim-label")
            self.msgs.append(hint)
            return
        last = 0
        for m in cv["messages"]:
            if m.get("t", 0) - last > 600:
                tl = Gtk.Label(label=_when(m.get("t", 0)), halign=Gtk.Align.CENTER)
                tl.add_css_class("ks-bub-time")
                self.msgs.append(tl)
            last = m.get("t", 0)
            self._bubble(m["text"], m["role"] == "user", m.get("tool"))
        self._scroll_end()

    def _bubble(self, text, mine, tool=None):
        wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, halign=Gtk.Align.END if mine else Gtk.Align.START)
        if not mine and tool:
            who = Gtk.Label(label=ai.TOOLS.get(tool, {}).get("name", ""), xalign=0)
            who.add_css_class("ks-bub-who")
            wrap.append(who)
        b = Gtk.Box()
        b.add_css_class("ks-bub-me" if mine else "ks-bub-ai")
        b.append(_bubble_content(text, mine, self._width()))
        wrap.append(b)
        gap = 40 if self._width() > 90 else 80
        wrap.set_margin_start(0 if mine is False else gap)
        wrap.set_margin_end(gap if mine is False else 0)
        self.msgs.append(wrap)
        return b

    def _scroll_end(self):
        adj = self.sc.get_vadjustment()
        GLib.timeout_add(60, lambda: (adj.set_value(adj.get_upper()), False)[1])

    # ================= assistent og knapper
    def _pick_tool(self, dd, _p):
        i = dd.get_selected()
        if 0 <= i < len(self.tools):
            self.tool = self.tools[i]
            ai.set_(tool=self.tool)
            self._show_tool()

    def _show_tool(self):
        self.icon.set_from_file(os.path.join(APP_DIR, "icons", ai.TOOLS[self.tool]["icon"]))
        self._render_state(self._st.get(self.tool))
        self._refresh()

    def _refresh(self):
        tool = self.tool
        _bg(lambda: ai.status(tool), lambda st: (not isinstance(st, Exception) and self._st.__setitem__(tool, st),
                                                 tool == self.tool and self._render_state(st)))

    def _render_state(self, st):
        t = ai.TOOLS[self.tool]
        self.main_btn.set_visible(False)
        items = []
        if not st or isinstance(st, Exception):
            self.state.set_label(i18n.tr("Sjekker …"))
        elif not st["installed"]:
            self.state.set_label(i18n.tr(f"{t['name']} er ikke installert"))
            self._main = ("Installerer", lambda: ai.install(self.tool))
            self.main_btn.set_label(i18n.tr("Installer"))
            self.main_btn.set_visible(True)
        else:
            self.state.set_label(f"{t['by']} · {st['version']}" + ("" if st["login"] else " · " +
                                                                   i18n.tr("ikke pålogget")))
            if not st["login"]:
                self._main = ("Logg inn", lambda: ai.login(self.tool))
                self.main_btn.set_label(i18n.tr("Logg inn"))
                self.main_btn.set_visible(True)
            items = [("Åpne i terminal (arbeidsmappa)", lambda: ai.open_terminal(self.tool, S.workdir())),
                     ("Logg inn på nytt", lambda: ai.login(self.tool)), ("Oppdater", lambda: ai.update(self.tool))]
            if not ai.IS_WIN:
                items.append(("Avinstaller …", None))
        pop = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=6, margin_bottom=6, margin_start=6,
                      margin_end=6)
        for label, fn in items:
            b = Gtk.Button(label=i18n.tr(label))
            b.add_css_class("flat")
            b.get_child().set_xalign(0)
            b.connect("clicked", lambda _b, f=fn, lab=label: (pop.popdown(), self._confirm_uninstall() if f is None
                                                              else self._run(lab, f)))
            box.append(b)
        if items:
            box.append(Gtk.Separator(margin_top=4, margin_bottom=4))
        box.append(self._look_box(pop))
        pop.set_child(box)
        self.more.set_popover(pop)
        self.more.set_visible(True)

    # ================= utseende: listebredde, tekststørrelse, boblebredde
    def _paned_moved(self, paned, _p):
        pos = paned.get_position()
        if self.side.get_visible() and 140 <= pos <= 700:
            if abs(pos - int(ai.cfg().get("list_width", 260))) >= 10:
                GLib.timeout_add(400, self._save_width, pos)

    def _save_width(self, pos):
        if self.paned.get_position() == pos:
            ai.set_(list_width=pos)
        return False

    def _width(self):
        return int(ai.cfg().get("bubble_width", 70))

    def _apply_look(self):
        size = int(ai.cfg().get("text_size", 100))
        if not hasattr(self, "_size_css"):
            self._size_css = Gtk.CssProvider()
            Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self._size_css,
                                                      Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 2)
        css = (f".ks-bub-me label, .ks-bub-ai label {{ font-size: {size / 100:.2f}em; }} "
               f".ks-code {{ font-size: {size * 0.92 / 100:.2f}em; }} "
               f".ks-ai-input textview {{ font-size: {size / 100:.2f}em; }}")
        if hasattr(self._size_css, "load_from_string"):
            self._size_css.load_from_string(css)
        else:
            self._size_css.load_from_data(css.encode())

    def _look_box(self, pop):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=4)
        c = ai.cfg()
        box.append(Gtk.Label(label=i18n.tr("Tekststørrelse"), xalign=0))
        tr = Gtk.Box(spacing=6)
        lab = Gtk.Label(label=f"{c.get('text_size', 100)} %", hexpand=True)

        def size(d):
            v = max(70, min(200, int(ai.cfg().get("text_size", 100)) + d))
            ai.set_(text_size=v)
            lab.set_label(f"{v} %")
            self._apply_look()
        for t, d in (("A−", -10), ("A+", 10)):
            b = Gtk.Button(label=t)
            b.connect("clicked", lambda _b, dd=d: size(dd))
            tr.append(b)
            if d < 0:
                tr.append(lab)
        box.append(tr)
        box.append(Gtk.Label(label=i18n.tr("Bredde på boblene"), xalign=0))
        sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 40, 160, 5)
        sc.set_value(self._width())
        sc.set_size_request(220, -1)
        sc.set_format_value_func(lambda _s, v: f"{v:.0f} tegn")

        def width(s_):
            ai.set_(bubble_width=int(s_.get_value()))
            if getattr(self, "_wt", None):
                GLib.source_remove(self._wt)
            self._wt = GLib.timeout_add(250, lambda: (setattr(self, "_wt", None), self._render_conv(), False)[2])
        sc.connect("value-changed", width)
        box.append(sc)
        rs = Gtk.Button(label=i18n.tr("Tilbakestill utseendet"))
        rs.add_css_class("flat")
        rs.connect("clicked", lambda *_: (ai.set_(text_size=100, bubble_width=70, list_width=260, list_visible=True),
                                          pop.popdown(), self._apply_look(), sc.set_value(70),
                                          self.paned.set_position(260), self.list_btn.set_active(True),
                                          self._render_conv()))
        box.append(rs)
        return box

    def _main_action(self):
        self._run(*self._main)

    def _run(self, label, fn):
        self.status.set_label(i18n.tr(label) + " …")
        tool = self.tool
        _bg(fn, lambda r: (self.status.set_label(("✗ " if isinstance(r, Exception) else "") + str(r)),
                           self._st.pop(tool, None), self._refresh()))

    def _confirm_uninstall(self):
        name = ai.TOOLS[self.tool]["name"]
        dlg = Adw.AlertDialog(heading=i18n.tr(f"Avinstallere {name}?"))
        dlg.add_response("nei", i18n.tr("Avbryt"))
        dlg.add_response("ja", i18n.tr("Avinstaller"))
        dlg.set_response_appearance("ja", Adw.ResponseAppearance.DESTRUCTIVE)
        tool = self.tool
        dlg.connect("response", lambda _d, r: r == "ja" and self._run("Avinstallerer", lambda: ai.uninstall(tool)))
        dlg.present(self.get_root())

    # ================= sende
    def _key(self, _c, keyval, _code, state):
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if state & Gdk.ModifierType.SHIFT_MASK:
                return False                                # Shift+Enter: ny linje
            self._send()
            return True
        return False

    def _send_or_stop(self):
        if self.proc is not None:
            try:
                self.proc.terminate()
            except OSError:
                pass
        else:
            self._send()

    def _send(self):
        if self.proc is not None:
            return
        pb = self.prompt.get_buffer()
        q = pb.get_text(pb.get_start_iter(), pb.get_end_iter(), False).strip()
        if not q:
            return
        pb.set_text("")
        if self.conv is None:
            self.conv = S.new(self.tool)
        if not self.conv.get("messages"):
            self._clear()
        self.conv["tool"] = self.tool
        self.conv["messages"].append({"role": "user", "text": q, "t": time.time()})
        S.save(self.conv)
        if len(self.conv["messages"]) == 1:
            self.title.set_label(self.conv.get("title") or q[:48])
            self._reload_list()
        self._bubble(q, True)
        # «skriver …»-boble som fylles med svaret
        self._live = self._bubble("• • •", False, self.tool)
        self._live_text = ""
        self._scroll_end()
        c = ai.cfg()
        self.status.set_label(f"{ai.TOOLS[self.tool]['name']} {i18n.tr('tenker')} …")
        self.send_btn.set_label("■")
        self.send_btn.set_tooltip_text(i18n.tr("Stopp"))
        self._t0 = time.time()
        try:
            self.proc = ai.ask(self.tool, q, S.workdir(), c["allow_edit"], on_text=self._append,
                               on_done=lambda code: GLib.idle_add(lambda: (self._done(code), False)[1]),
                               history=S.history_text(self.conv), control=c.get("control", True))
        except Exception as e:  # noqa: BLE001
            self._done(None, str(e))

    def _append(self, text):
        self._buf.append(text)
        if len(self._buf) == 1:
            GLib.timeout_add(90, self._flush)

    def _flush(self):
        text, self._buf = "".join(self._buf), []
        self._live_text += text
        if self._live is not None:
            while (ch := self._live.get_first_child()) is not None:
                self._live.remove(ch)
            self._live.append(_bubble_content(self._live_text.strip() or "• • •", False, self._width()))
            self._scroll_end()
        return False

    def _done(self, code, err=None):
        if self._buf:
            self._flush()
        self.proc = None
        self.send_btn.set_label("↑")
        self.send_btn.set_tooltip_text(i18n.tr("Send (Enter)"))
        text = (self._live_text or "").strip()
        if err:
            text = text or f"✗ {err}"
        elif code not in (0, None) and not text:
            text = i18n.tr("✗ Fikk ikke svar – er du pålogget? Se ⋯ → Logg inn på nytt.")
        if self.conv is not None and text:
            self.conv["messages"].append({"role": "assistant", "text": text, "t": time.time(), "tool": self.tool})
            S.save(self.conv)
            t0 = getattr(self, "_t0", time.time())
            threading.Thread(target=S.push_changed, args=(t0,), daemon=True).start()
        if self._live is not None:
            while (ch := self._live.get_first_child()) is not None:
                self._live.remove(ch)
            self._live.append(_bubble_content(text or "…", False, self._width()))
        self._live = None
        self.status.set_label("" if code == 0 else (i18n.tr("Stoppet") if code else ""))
        self._reload_list()
        self.prompt.grab_focus()
