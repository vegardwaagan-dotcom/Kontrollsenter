"""AI-siden: Claude Code og Codex – status, installer/oppdater, logg inn, åpne i terminal, og «Spør» rett herfra."""
import os
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk, Pango  # noqa: E402

import ai  # noqa: E402
import i18n  # noqa: E402

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CSS = """
.ks-ai-out { font-family: monospace; font-size: 0.95em; padding: 10px; border-radius: 10px;
  background: alpha(@window_fg_color, 0.05); }
.ks-ai-card { padding: 4px; }
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
    return lab


class ToolCard(Gtk.Box):
    """Ett kort per assistent: status og knapper."""

    def __init__(self, page, tool):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add_css_class("card")
        self.page, self.tool = page, tool
        t = ai.TOOLS[tool]
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=14, margin_bottom=14,
                        margin_start=16, margin_end=16)
        self.append(inner)
        head = Gtk.Box(spacing=12)
        icon = Gtk.Image.new_from_file(os.path.join(APP_DIR, "icons", t["icon"]))
        icon.set_pixel_size(40)
        head.append(icon)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        name = Gtk.Label(label=t["name"], xalign=0)
        name.add_css_class("title-3")
        col.append(name)
        self.state = _dim("…")
        col.append(self.state)
        head.append(col)
        inner.append(head)
        self.btns = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=5, column_spacing=6,
                                row_spacing=6, homogeneous=False)
        inner.append(self.btns)
        self.msg = _dim("")
        inner.append(self.msg)
        self.refresh()

    def _btn(self, label, fn, primary=False):
        b = Gtk.Button(label=i18n.tr(label))
        if primary:
            b.add_css_class("suggested-action")
        b.add_css_class("pill")
        b.connect("clicked", lambda *_: self._run(label, fn))
        self.btns.append(b)

    def _run(self, label, fn):
        self.msg.set_label(i18n.tr(label) + " …")
        _bg(fn, lambda r: (self.msg.set_label(("✗ " if isinstance(r, Exception) else "") + str(r)), self.refresh()))

    def refresh(self):
        _bg(lambda: ai.status(self.tool), self._show)

    def _show(self, st):
        if isinstance(st, Exception):
            self.state.set_label(str(st))
            return
        while (c := self.btns.get_first_child()) is not None:
            self.btns.remove(c)
        t = ai.TOOLS[self.tool]
        if not st["installed"]:
            self.state.set_label(i18n.tr(f"Ikke installert – kodeassistent fra {t['by']} som jobber i mappa du velger"))
            self._btn("Installer", lambda: ai.install(self.tool), True)
            return
        self.state.set_label(f"{i18n.tr('Versjon')} {st['version']} · " +
                             (i18n.tr("pålogget ✓") if st["login"] else i18n.tr("ikke pålogget")))
        self._btn("Åpne i terminal", lambda: ai.open_terminal(self.tool, ai.cfg()["folder"]), True)
        if not st["login"]:
            self._btn("Logg inn", lambda: ai.login(self.tool), True)
        self._btn("Oppdater", lambda: ai.update(self.tool))
        self._btn("Logg inn på nytt" if st["login"] else "Hjelp", lambda: ai.login(self.tool))
        if not ai.IS_WIN:
            b = Gtk.Button(label=i18n.tr("Avinstaller"))
            b.add_css_class("pill")
            b.add_css_class("flat")
            b.connect("clicked", lambda *_: self.page.confirm(
                f"Avinstallere {t['name']}?", lambda: self._run("Avinstaller", lambda: ai.uninstall(self.tool))))
            self.btns.append(b)


class AiPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        try:
            import theme
            theme.add_css(CSS)
        except Exception:  # noqa: BLE001
            pass
        sc = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        clamp = Adw.Clamp(maximum_size=980, tightening_threshold=700)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin_top=16, margin_bottom=24,
                      margin_start=16, margin_end=16)
        clamp.set_child(box)
        sc.set_child(clamp)
        self.append(sc)
        c = ai.cfg()
        # mappe
        frow = Gtk.Box(spacing=8)
        flab = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        flab.append(Gtk.Label(label=i18n.tr("Mappe AI-en jobber i"), xalign=0))
        self.folder = _dim(c["folder"])
        self.folder.set_ellipsize(Pango.EllipsizeMode.START)
        flab.append(self.folder)
        frow.append(flab)
        recent = Gtk.MenuButton(label=i18n.tr("Nylige"), valign=Gtk.Align.CENTER)
        recent.add_css_class("flat")
        self.recent_btn = recent
        frow.append(recent)
        pick = Gtk.Button(label=i18n.tr("Velg mappe …"), valign=Gtk.Align.CENTER)
        pick.add_css_class("pill")
        pick.connect("clicked", self._pick_folder)
        frow.append(pick)
        box.append(frow)
        self._recent_menu()
        erow = Gtk.Box(spacing=12)
        ecol = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        ecol.append(Gtk.Label(label=i18n.tr("La AI-en endre filer i mappa"), xalign=0))
        ecol.append(_dim("Av: AI-en kan bare lese og svare. På: den kan også skrive og endre filer i mappa (ikke "
                         "utenfor)."))
        erow.append(ecol)
        self.edit = Gtk.Switch(active=c["allow_edit"], valign=Gtk.Align.CENTER)
        self.edit.connect("notify::active", lambda w, _p: ai.set_(allow_edit=w.get_active()))
        erow.append(self.edit)
        box.append(erow)
        # kortene
        cards = Gtk.Box(spacing=12, homogeneous=True, valign=Gtk.Align.START)
        self.cards = [ToolCard(self, t) for t in ai.TOOLS]
        for card in self.cards:
            card.set_valign(Gtk.Align.START)
            cards.append(card)
        box.append(cards)
        # spør
        h = Gtk.Label(label=i18n.tr("Spør"), xalign=0)
        h.add_css_class("title-3")
        box.append(h)
        box.append(_dim("Skriv hva du lurer på eller vil ha gjort – svaret kommer her. Ctrl+Enter sender."))
        trow = Gtk.Box(spacing=8)
        seg = Gtk.Box()
        seg.add_css_class("linked")
        first = None
        self.tool = c["tool"] if c["tool"] in ai.TOOLS else "claude"
        for t, info in ai.TOOLS.items():
            b = Gtk.ToggleButton(label=info["name"], active=t == self.tool)
            if first:
                b.set_group(first)
            first = first or b
            b.connect("toggled", lambda btn, k=t: btn.get_active() and (setattr(self, "tool", k), ai.set_(tool=k)))
            seg.append(b)
        trow.append(seg)
        trow.append(Gtk.Box(hexpand=True))
        self.stop_btn = Gtk.Button(label=i18n.tr("Stopp"), sensitive=False)
        self.stop_btn.connect("clicked", lambda *_: self._stop())
        trow.append(self.stop_btn)
        self.send_btn = Gtk.Button(label=i18n.tr("Send"))
        self.send_btn.add_css_class("suggested-action")
        self.send_btn.connect("clicked", lambda *_: self._ask())
        trow.append(self.send_btn)
        box.append(trow)
        self.prompt = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, top_margin=8, bottom_margin=8, left_margin=10,
                                   right_margin=10)
        self.prompt.add_css_class("card")
        self.prompt.set_size_request(-1, 90)
        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._key)
        self.prompt.add_controller(key)
        box.append(self.prompt)
        self.out = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR, monospace=True)
        self.out.add_css_class("ks-ai-out")
        osc = Gtk.ScrolledWindow(child=self.out, min_content_height=240, max_content_height=600,
                                 propagate_natural_height=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        box.append(osc)
        self.osc = osc
        orow = Gtk.Box(spacing=8)
        self.status = _dim("")
        self.status.set_hexpand(True)
        orow.append(self.status)
        cp = Gtk.Button(label=i18n.tr("Kopier svaret"))
        cp.add_css_class("flat")
        cp.connect("clicked", lambda *_: Gdk.Display.get_default().get_clipboard().set(self._out_text()))
        orow.append(cp)
        box.append(orow)
        self.proc = None
        self._buf = []
        self.connect("map", lambda *_: [card.refresh() for card in self.cards])

    # ---------------- mappe
    def _recent_menu(self):
        pop = Gtk.Popover()
        lst = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=6, margin_bottom=6, margin_start=6,
                      margin_end=6)
        for r in ai.cfg()["recent"] or [ai.HOME]:
            b = Gtk.Button(label=r)
            b.add_css_class("flat")
            b.get_child().set_xalign(0)
            b.connect("clicked", lambda _b, f=r: (pop.popdown(), self._set_folder(f)))
            lst.append(b)
        pop.set_child(lst)
        self.recent_btn.set_popover(pop)

    def _set_folder(self, f):
        ai.set_(folder=f)
        self.folder.set_label(f)
        self._recent_menu()

    def _pick_folder(self, *_):
        dlg = Gtk.FileDialog(title=i18n.tr("Velg mappe for AI-en"))
        try:
            from gi.repository import Gio
            dlg.set_initial_folder(Gio.File.new_for_path(ai.cfg()["folder"]))
        except Exception:  # noqa: BLE001
            pass

        def done(d, res):
            try:
                f = d.select_folder_finish(res)
            except GLib.Error:
                return
            if f and f.get_path():
                self._set_folder(f.get_path())
        dlg.select_folder(self.get_root(), None, done)

    # ---------------- spør
    def _key(self, _c, keyval, _code, state):
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and state & Gdk.ModifierType.CONTROL_MASK:
            self._ask()
            return True
        return False

    def _out_text(self):
        b = self.out.get_buffer()
        return b.get_text(b.get_start_iter(), b.get_end_iter(), False)

    def _append(self, text):
        self._buf.append(text)
        if len(self._buf) == 1:
            GLib.timeout_add(80, self._flush)

    def _flush(self):
        text, self._buf = "".join(self._buf), []
        b = self.out.get_buffer()
        b.insert(b.get_end_iter(), text)
        adj = self.osc.get_vadjustment()
        GLib.idle_add(lambda: (adj.set_value(adj.get_upper()), False)[1])
        return False

    def _ask(self):
        if self.proc is not None:
            return
        pb = self.prompt.get_buffer()
        q = pb.get_text(pb.get_start_iter(), pb.get_end_iter(), False).strip()
        if not q:
            self.status.set_label(i18n.tr("Skriv et spørsmål først"))
            return
        self.out.get_buffer().set_text("")
        c = ai.cfg()
        name = ai.TOOLS[self.tool]["name"]
        self.status.set_label(f"{name} {i18n.tr('tenker')} … ({c['folder']})")
        self.send_btn.set_sensitive(False)
        self.stop_btn.set_sensitive(True)
        try:
            self.proc = ai.ask(self.tool, q, c["folder"], c["allow_edit"], on_text=self._append,
                               on_done=lambda code: GLib.idle_add(lambda: (self._done(code), False)[1]))
        except Exception as e:  # noqa: BLE001
            self._done(None, str(e))

    def _done(self, code, err=None):
        self.proc = None
        self.send_btn.set_sensitive(True)
        self.stop_btn.set_sensitive(False)
        if err:
            self.status.set_label("✗ " + err)
        elif code == 0:
            self.status.set_label(i18n.tr("Ferdig ✓"))
        else:
            self.status.set_label(i18n.tr("Stoppet eller feilet") + f" ({code}) – " +
                                  i18n.tr("er du pålogget? Trykk «Logg inn»"))

    def _stop(self):
        if self.proc is not None:
            try:
                self.proc.terminate()
            except OSError:
                pass

    def confirm(self, q, fn):
        dlg = Adw.AlertDialog(heading=i18n.tr(q))
        dlg.add_response("nei", i18n.tr("Avbryt"))
        dlg.add_response("ja", i18n.tr("Ja"))
        dlg.set_response_appearance("ja", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.connect("response", lambda _d, r: r == "ja" and fn())
        dlg.present(self.get_root())
