"""AI-siden: Claude Code, Codex og Gemini.

Øverst: valghjul for assistenten, status og knapper på én linje, mappe og «kan endre filer».
I midten: svaret (fyller siden). Nederst: skrivefeltet – Enter sender, Shift+Enter gir ny linje.
"""
import os
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

import ai  # noqa: E402
import i18n  # noqa: E402

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CSS = """
.ks-ai-out { font-family: monospace; font-size: 0.97em; padding: 12px; }
.ks-ai-outbox { border-radius: 12px; background: alpha(@window_fg_color, 0.05); }
.ks-ai-in { border-radius: 12px; background: alpha(@window_fg_color, 0.08); padding: 6px 10px; }
.ks-ai-bar { padding: 2px 0; }
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


class AiPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for side in ("top", "bottom", "start", "end"):
            getattr(self, f"set_margin_{side}")(14)
        try:
            import theme
            theme.add_css(CSS)
        except Exception:  # noqa: BLE001
            pass
        c = ai.cfg()
        self.tools = list(ai.TOOLS)
        self.tool = c["tool"] if c["tool"] in ai.TOOLS else "claude"

        # ---- linje 1: valghjul · status · knapper
        top = Gtk.Box(spacing=8)
        top.add_css_class("ks-ai-bar")
        self.icon = Gtk.Image(pixel_size=30)
        top.append(self.icon)
        self.dd = Gtk.DropDown.new_from_strings([ai.TOOLS[t]["name"] for t in self.tools])
        self.dd.set_selected(self.tools.index(self.tool))
        self.dd.set_valign(Gtk.Align.CENTER)
        self.dd.set_tooltip_text(i18n.tr("Velg assistent"))
        self.dd.connect("notify::selected", self._pick_tool)
        top.append(self.dd)
        self.state = _dim("…")
        self.state.set_hexpand(True)
        top.append(self.state)
        self.main_btn = Gtk.Button(valign=Gtk.Align.CENTER)
        self.main_btn.add_css_class("pill")
        self.main_btn.connect("clicked", lambda *_: self._main_action())
        top.append(self.main_btn)
        self.more = Gtk.MenuButton(icon_name="view-more-symbolic", valign=Gtk.Align.CENTER,
                                   tooltip_text=i18n.tr("Logg inn, oppdater, installer …"))
        self.more.add_css_class("flat")
        top.append(self.more)
        self.append(top)

        # ---- linje 2: mappe · kan endre filer · kopier/tøm
        row2 = Gtk.Box(spacing=8)
        self.folder_btn = Gtk.MenuButton(valign=Gtk.Align.CENTER, tooltip_text=i18n.tr("Mappa AI-en jobber i"))
        self.folder_btn.add_css_class("flat")
        row2.append(self.folder_btn)
        row2.append(Gtk.Box(hexpand=True))
        self.edit = Gtk.ToggleButton(label=i18n.tr("✏️ Kan endre filer"), active=c["allow_edit"],
                                     valign=Gtk.Align.CENTER,
                                     tooltip_text=i18n.tr("Av: AI-en kan bare lese og svare. På: den kan skrive og "
                                                          "endre filer i mappa (ikke utenfor)."))
        self.edit.add_css_class("flat")
        self.edit.connect("toggled", lambda w: (ai.set_(allow_edit=w.get_active()), self._edit_style()))
        row2.append(self.edit)
        cp = Gtk.Button(icon_name="edit-copy-symbolic", tooltip_text=i18n.tr("Kopier svaret"), valign=Gtk.Align.CENTER)
        cp.add_css_class("flat")
        cp.connect("clicked", lambda *_: Gdk.Display.get_default().get_clipboard().set(self._out_text()))
        row2.append(cp)
        clr = Gtk.Button(icon_name="edit-clear-all-symbolic", tooltip_text=i18n.tr("Tøm"), valign=Gtk.Align.CENTER)
        clr.add_css_class("flat")
        clr.connect("clicked", lambda *_: self.out.get_buffer().set_text(""))
        row2.append(clr)
        self.append(row2)
        self._edit_style()

        # ---- svaret (fyller siden)
        self.out = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR,
                                monospace=True)
        self.out.add_css_class("ks-ai-out")
        self.out.set_name("ks-ai-out")
        self.osc = Gtk.ScrolledWindow(child=self.out, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.osc.add_css_class("ks-ai-outbox")
        self.append(self.osc)
        self.status = _dim("", small=True)
        self.append(self.status)

        # ---- skrivefeltet nederst
        inrow = Gtk.Box(spacing=8)
        inrow.add_css_class("ks-ai-in")
        self.prompt = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, top_margin=8, bottom_margin=8, left_margin=4,
                                   right_margin=4, accepts_tab=False)
        self.prompt.set_tooltip_text(i18n.tr("Enter sender · Shift+Enter gir ny linje"))
        key = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        key.connect("key-pressed", self._key)
        self.prompt.add_controller(key)
        self.isc = Gtk.ScrolledWindow(child=self.prompt, hexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER,
                                      propagate_natural_height=True, min_content_height=44, max_content_height=170)
        inrow.append(self.isc)
        btns = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, valign=Gtk.Align.END)
        self.send_btn = Gtk.Button(label=i18n.tr("Send"))
        self.send_btn.add_css_class("suggested-action")
        self.send_btn.connect("clicked", lambda *_: self._ask())
        btns.append(self.send_btn)
        self.stop_btn = Gtk.Button(label=i18n.tr("Stopp"), visible=False)
        self.stop_btn.add_css_class("destructive-action")
        self.stop_btn.connect("clicked", lambda *_: self._stop())
        btns.append(self.stop_btn)
        inrow.append(btns)
        self.append(inrow)
        self.append(_dim("Enter sender · Shift+Enter gir ny linje", small=True))

        self.proc = None
        self._buf = []
        self._st = {}
        self._folder_menu()
        self._show_tool()
        self.connect("map", lambda *_: (self._refresh(), self.prompt.grab_focus()))

    # ---------------- assistent
    def _pick_tool(self, dd, _p):
        i = dd.get_selected()
        if 0 <= i < len(self.tools):
            self.tool = self.tools[i]
            ai.set_(tool=self.tool)
            self._show_tool()

    def _show_tool(self):
        t = ai.TOOLS[self.tool]
        self.icon.set_from_file(os.path.join(APP_DIR, "icons", t["icon"]))
        st = self._st.get(self.tool)
        self._render(st)
        self._refresh()

    def _refresh(self):
        tool = self.tool
        _bg(lambda: ai.status(tool), lambda st: (self._st.__setitem__(tool, st) if not isinstance(st, Exception)
                                                 else None, tool == self.tool and self._render(st)))

    def _render(self, st):
        t = ai.TOOLS[self.tool]
        if not st or isinstance(st, Exception):
            self.state.set_label(i18n.tr("Sjekker …"))
            self.main_btn.set_visible(False)
            self.more.set_popover(None)
            return
        items = []
        if not st["installed"]:
            self.state.set_label(i18n.tr(f"Ikke installert – kodeassistent fra {t['by']}"))
            self.main_btn.set_label(i18n.tr("Installer"))
            self.main_btn.add_css_class("suggested-action")
            self._main = ("Installerer", lambda: ai.install(self.tool))
        else:
            self.state.set_label(f"{t['by']} · {i18n.tr('versjon')} {st['version']} · " +
                                 (i18n.tr("pålogget ✓") if st["login"] else i18n.tr("ikke pålogget")))
            if st["login"]:
                self.main_btn.set_label(i18n.tr("Åpne i terminal"))
                self.main_btn.remove_css_class("suggested-action")
                self._main = ("Åpner", lambda: ai.open_terminal(self.tool, ai.cfg()["folder"]))
                items.append(("Logg inn på nytt", lambda: ai.login(self.tool)))
            else:
                self.main_btn.set_label(i18n.tr("Logg inn"))
                self.main_btn.add_css_class("suggested-action")
                self._main = ("Logg inn", lambda: ai.login(self.tool))
                items.append(("Åpne i terminal", lambda: ai.open_terminal(self.tool, ai.cfg()["folder"])))
            items.append(("Oppdater", lambda: ai.update(self.tool)))
            if not ai.IS_WIN:
                items.append(("Avinstaller …", None))
        self.main_btn.set_visible(True)
        self._menu(items)

    def _menu(self, items):
        if not items:
            self.more.set_visible(False)
            return
        self.more.set_visible(True)
        pop = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=6, margin_bottom=6, margin_start=6,
                      margin_end=6)
        for label, fn in items:
            b = Gtk.Button(label=i18n.tr(label))
            b.add_css_class("flat")
            b.get_child().set_xalign(0)
            if fn is None:                                  # avinstaller: spør først
                b.connect("clicked", lambda *_: (pop.popdown(), self._confirm_uninstall()))
            else:
                b.connect("clicked", lambda _b, f=fn, lab=label: (pop.popdown(), self._run(lab, f)))
            box.append(b)
        pop.set_child(box)
        self.more.set_popover(pop)

    def _main_action(self):
        label, fn = self._main
        self._run(label, fn)

    def _run(self, label, fn):
        self.status.set_label(i18n.tr(label) + " …")
        tool = self.tool

        def done(r):
            self.status.set_label(("✗ " if isinstance(r, Exception) else "") + str(r))
            self._st.pop(tool, None)
            self._refresh()
        _bg(fn, done)

    def _confirm_uninstall(self):
        name = ai.TOOLS[self.tool]["name"]
        dlg = Adw.AlertDialog(heading=i18n.tr(f"Avinstallere {name}?"))
        dlg.add_response("nei", i18n.tr("Avbryt"))
        dlg.add_response("ja", i18n.tr("Avinstaller"))
        dlg.set_response_appearance("ja", Adw.ResponseAppearance.DESTRUCTIVE)
        tool = self.tool
        dlg.connect("response", lambda _d, r: r == "ja" and self._run("Avinstallerer", lambda: ai.uninstall(tool)))
        dlg.present(self.get_root())

    # ---------------- mappe og «kan endre filer»
    def _edit_style(self):
        (self.edit.add_css_class if self.edit.get_active() else self.edit.remove_css_class)("warning")

    def _folder_menu(self):
        c = ai.cfg()
        name = os.path.basename(c["folder"].rstrip("/")) or c["folder"]
        self.folder_btn.set_label(f"📁 {name}")
        self.folder_btn.set_tooltip_text(c["folder"])
        pop = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=6, margin_bottom=6, margin_start=6,
                      margin_end=6)
        pick = Gtk.Button(label=i18n.tr("Velg mappe …"))
        pick.add_css_class("flat")
        pick.get_child().set_xalign(0)
        pick.connect("clicked", lambda *_: (pop.popdown(), self._pick_folder()))
        box.append(pick)
        for r in c["recent"] or [ai.HOME]:
            b = Gtk.Button(label=r)
            b.add_css_class("flat")
            b.get_child().set_xalign(0)
            b.connect("clicked", lambda _b, f=r: (pop.popdown(), self._set_folder(f)))
            box.append(b)
        pop.set_child(box)
        self.folder_btn.set_popover(pop)

    def _set_folder(self, f):
        ai.set_(folder=f)
        GLib.idle_add(lambda: (self._folder_menu(), False)[1])

    def _pick_folder(self):
        dlg = Gtk.FileDialog(title=i18n.tr("Velg mappe for AI-en"))
        try:
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
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if state & Gdk.ModifierType.SHIFT_MASK:
                return False                                # Shift+Enter: ny linje
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
            return
        c = ai.cfg()
        name = ai.TOOLS[self.tool]["name"]
        b = self.out.get_buffer()
        if b.get_char_count():
            b.insert(b.get_end_iter(), "\n\n")
        b.insert(b.get_end_iter(), f"› {q}\n\n")
        pb.set_text("")
        self.status.set_label(f"{name} {i18n.tr('tenker')} … ({c['folder']})")
        self.send_btn.set_sensitive(False)
        self.stop_btn.set_visible(True)
        try:
            self.proc = ai.ask(self.tool, q, c["folder"], c["allow_edit"], on_text=self._append,
                               on_done=lambda code: GLib.idle_add(lambda: (self._done(code), False)[1]))
        except Exception as e:  # noqa: BLE001
            self._done(None, str(e))

    def _done(self, code, err=None):
        self.proc = None
        self.send_btn.set_sensitive(True)
        self.stop_btn.set_visible(False)
        if err:
            self.status.set_label("✗ " + err)
        elif code == 0:
            self.status.set_label(i18n.tr("Ferdig ✓"))
        else:
            self.status.set_label(i18n.tr("Stoppet eller feilet") + f" ({code}) – " +
                                  i18n.tr("er du pålogget? Se ⋯ → Logg inn"))
        self.prompt.grab_focus()

    def _stop(self):
        if self.proc is not None:
            try:
                self.proc.terminate()
            except OSError:
                pass
