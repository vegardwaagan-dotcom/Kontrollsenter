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
.ks-bub-ai { border-left: 3px solid alpha(@accent_bg_color, 0.6); }
.ks-code-box { background: alpha(#000000, 0.30); border-radius: 10px; }
.ks-code-head { font-size: .78em; opacity: .7; padding: 3px 4px 0 10px; }
.ks-code-box .ks-code { background: none; }
.ks-ai-tool { font-size: .82em; opacity: .62; margin: 0 12px; }
.ks-ai-act button { min-height: 22px; min-width: 22px; padding: 0 6px; font-size: .85em; opacity: .7; }
.ks-ai-card { border-radius: 14px; padding: 10px 12px; background: alpha(@window_fg_color, 0.07); }
.ks-ai-card .big { font-size: 1.35em; font-weight: 800; }
.ks-sugg { border-radius: 14px; padding: 12px; background: alpha(@window_fg_color, 0.06); }
.ks-sugg:hover { background: alpha(@accent_bg_color, 0.18); }
.ks-quota { font-size: .78em; opacity: .75; }
.ks-ai-ask { border-radius: 14px; padding: 10px 12px; background: alpha(#ff9f43, 0.16);
  border: 1px solid alpha(#ff9f43, 0.5); }
.ks-chip { border-radius: 99px; padding: 2px 8px; background: alpha(@window_fg_color, 0.08); font-size: .85em; }
.ks-ai-panel { background: alpha(@window_fg_color, 0.035); }
"""

SUGGESTIONS = [("🐢", "Hvorfor er PC-en treg?"), ("🌡️", "Sjekk temperaturene og si om noe er for varmt"),
               ("🧹", "Rydd disken – hva kan jeg trygt slette?"), ("🎮", "Gjør PC-en klar for spilling"),
               ("🔍", "Hvor slår jeg av varsler?"), ("📜", "Se etter feil i loggene og forklar dem"),
               ("🤖", "Si fra hvis GPU-en går over 85 °C mens jeg spiller"), ("🖥️", "Hvordan har de andre PC-ene det?")]

_KW = {"python": r"\b(def|class|return|if|elif|else|for|while|in|import|from|as|with|try|except|finally|raise|"
                  r"lambda|None|True|False|and|or|not|is|pass|break|continue|yield|async|await|global)\b",
       "js": r"\b(function|const|let|var|return|if|else|for|while|of|in|new|class|import|from|export|await|async|"
              r"null|undefined|true|false|try|catch|throw|this)\b",
       "sh": r"\b(if|then|else|fi|for|do|done|while|case|esac|function|export|sudo|echo|cd|ls|rm|cp|mv|grep|"
              r"systemctl|flatpak|dnf|pacman|apt|ks)\b"}


def _highlight(code, lang):
    """Enkel fargekoding (Pango-markup): nøkkelord, strenger, tall og kommentarer."""
    import re
    lang = (lang or "").lower()
    kw = _KW["python"] if lang in ("py", "python", "") else _KW["js"] if lang in ("js", "javascript", "ts", "json") \
        else _KW["sh"] if lang in ("sh", "bash", "shell", "zsh", "console", "powershell", "ps1") else _KW["python"]
    tok = re.compile(r"(?P<c>#[^\n]*|//[^\n]*)|(?P<s>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')|"
                     r"(?P<n>\b\d+(?:\.\d+)?\b)|(?P<k>" + kw + ")")
    out, last = [], 0
    for m in tok.finditer(code):
        out.append(GLib.markup_escape_text(code[last:m.start()]))
        t = GLib.markup_escape_text(m.group(0))
        col = {"c": "#7f8c98", "s": "#a5d6a7", "n": "#f6c177", "k": "#c792ea"}[m.lastgroup]
        out.append(f'<span foreground="{col}"' + (' font_style="italic"' if m.lastgroup == "c" else "") + f">{t}</span>")
        last = m.end()
    out.append(GLib.markup_escape_text(code[last:]))
    return "".join(out)


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
        lang = ""
        if code and "\n" in part and not part.split("\n", 1)[0].strip().count(" "):
            first, rest = part.split("\n", 1)                # «```python» – språknavnet
            if first.strip().replace("-", "").isalnum():
                part, lang = rest, first.strip()
        lab = Gtk.Label(label=part, xalign=0, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, selectable=True,
                        max_width_chars=width if not code else int(width * 1.3))
        if code:
            lab.add_css_class("ks-code")
            try:
                lab.set_markup(_highlight(part, lang))
            except Exception:  # noqa: BLE001
                lab.set_label(part)
            cb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            cb.add_css_class("ks-code-box")
            hd = Gtk.Box(spacing=6)
            hl = Gtk.Label(label=lang or i18n.tr("kode"), xalign=0, hexpand=True)
            hl.add_css_class("ks-code-head")
            hd.append(hl)
            cp = Gtk.Button(label="📋 " + i18n.tr("Kopier"))
            cp.add_css_class("flat")
            cp.add_css_class("ks-code-head")
            cp.connect("clicked", lambda b, t=part: (Gdk.Display.get_default().get_clipboard().set(t),
                                                     b.set_label("✓ " + i18n.tr("Kopiert"))))
            hd.append(cp)
            cb.append(hd)
            cb.append(lab)
            box.append(cb)
            continue
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
        self._images = []

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
        sb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
        self.state = _dim("…")
        sb.append(self.state)
        self.quota = Gtk.Label(xalign=0, visible=False)
        self.quota.add_css_class("ks-quota")
        sb.append(self.quota)
        top.append(sb)
        self.panel_btn = Gtk.ToggleButton(label="📊", valign=Gtk.Align.CENTER, active=bool(c.get("panel", False)),
                                          tooltip_text=i18n.tr("Vis hva AI-en gjør og PC-en nå (ved siden av)"))
        self.panel_btn.add_css_class("flat")
        self.panel_btn.connect("toggled", lambda w: (self.panel.set_reveal_child(w.get_active()),
                                                     ai.set_(panel=w.get_active()),
                                                     w.get_active() and self._panel_tick()))
        top.append(self.panel_btn)
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
        self.chips = Gtk.Box(spacing=6, visible=False)                       # bilder som er lagt ved
        right.append(self.chips)
        inrow = Gtk.Box(spacing=6)
        inrow.add_css_class("ks-ai-input")
        att = Gtk.Button(label="📎", valign=Gtk.Align.END, tooltip_text=i18n.tr("Legg ved bilde (eller lim inn med Ctrl+V)"))
        att.add_css_class("flat")
        att.connect("clicked", lambda *_: self._attach())
        inrow.append(att)
        self.prompt = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, top_margin=8, bottom_margin=8, accepts_tab=False)
        self.prompt.add_css_class("ks-transparent")
        key = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        key.connect("key-pressed", self._key)
        self.prompt.add_controller(key)
        isc = Gtk.ScrolledWindow(child=self.prompt, hexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER,
                                 propagate_natural_height=True, min_content_height=38, max_content_height=170)
        inrow.append(isc)
        self.mic = Gtk.Button(label="🎙️", valign=Gtk.Align.END, tooltip_text=i18n.tr("Snakk inn spørsmålet"))
        self.mic.add_css_class("flat")
        self.mic.connect("clicked", lambda *_: self._mic())
        inrow.append(self.mic)
        self.send_btn = Gtk.Button(label="↑", valign=Gtk.Align.END, tooltip_text=i18n.tr("Send (Enter)"))
        self.send_btn.add_css_class("ks-send-round")
        self.send_btn.set_margin_bottom(2)
        self.send_btn.connect("clicked", lambda *_: self._send_or_stop())
        inrow.append(self.send_btn)
        right.append(inrow)
        right.append(_dim("Enter sender · Shift+Enter gir ny linje", small=True))
        holder = Gtk.Box(hexpand=True)
        holder.append(right)
        self.panel = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_LEFT,
                                  reveal_child=bool(c.get("panel", False)))
        pv = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, width_request=250)
        pv.add_css_class("ks-ai-panel")
        for s_, v in (("top", 12), ("bottom", 12), ("start", 12), ("end", 12)):
            getattr(pv, f"set_margin_{s_}")(v)
        ph = Gtk.Label(label=i18n.tr("PC-en nå"), xalign=0)
        ph.add_css_class("heading")
        pv.append(ph)
        self.panel_status = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        pv.append(self.panel_status)
        lh = Gtk.Label(label=i18n.tr("Hva AI-en har gjort"), xalign=0, margin_top=8)
        lh.add_css_class("heading")
        pv.append(lh)
        self.panel_log = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        pv.append(Gtk.ScrolledWindow(child=self.panel_log, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER))
        self.panel.set_child(pv)
        holder.append(self.panel)
        self.paned.set_end_child(holder)
        self._apply_look()
        try:                                                 # «Godta / Avbryt» i samtalen når AI-en vil endre noe
            import ai_bridge
            ai_bridge.set_confirm_handler(self._confirm_here)
        except Exception:  # noqa: BLE001
            pass
        GLib.idle_add(lambda: (self._show_quota(), self.panel_btn.get_active() and self._panel_tick(), False)[2])

        self._show_tool()
        self.connect("map", lambda *_: self._on_map())

    # ================= bilder, tale, panel og «Godta / Avbryt»
    def _chips(self):
        while (c := self.chips.get_first_child()) is not None:
            self.chips.remove(c)
        for p in self._images:
            b = Gtk.Button(label="🖼️ " + os.path.basename(p)[:22] + "  ✕", tooltip_text=i18n.tr("Fjern"))
            b.add_css_class("ks-chip")
            b.add_css_class("flat")
            b.connect("clicked", lambda _b, pp=p: (self._images.remove(pp), self._chips()))
            self.chips.append(b)
        self.chips.set_visible(bool(self._images))

    def _attach(self):
        fd = Gtk.FileDialog(title=i18n.tr("Legg ved bilde"))
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
                self._images.append(f.get_path())
                self._chips()
        fd.open(self.get_root(), None, done)

    def _paste_image(self):
        cb = Gdk.Display.get_default().get_clipboard()
        if not cb.get_formats().contain_gtype(Gdk.Texture):
            return False

        def got(c, res):
            try:
                tex = c.read_texture_finish(res)
            except GLib.Error:
                return
            d = os.path.join(S.workdir(), "bilder")
            os.makedirs(d, exist_ok=True)
            p = os.path.join(d, time.strftime("innlimt-%Y%m%d-%H%M%S.png"))
            tex.save_to_png(p)
            self._images.append(p)
            self._chips()
        cb.read_texture_async(None, got)
        return True

    def _mic(self):
        """Snakk inn spørsmålet: opptak (GStreamer) → Whisper lokalt → teksten i skrivefeltet."""
        import aitale
        import chatextra as CX
        if CX.recording():
            self.mic.set_label("🎙️")
            res = CX.rec_stop()
            if not res:
                self.status.set_label(i18n.tr("For kort opptak"))
                return
            self.status.set_label(i18n.tr("Gjør tale om til tekst …"))
            _bg(lambda: aitale.transcribe(res[0]), lambda t: (
                self.status.set_label(f"✗ {t}") if isinstance(t, Exception) else
                (self.prompt.get_buffer().insert_at_cursor(t + " "), self.status.set_label(""),
                 ai.cfg().get("voice_send", True) and t and self._send())))
            return
        if not aitale.stt_ready():
            dlg = Adw.AlertDialog(heading=i18n.tr("Tale til tekst"),
                                  body=i18n.tr("For å snakke med AI-en trengs Whisper – tale til tekst som kjører på "
                                               "din egen PC (gratis og privat, ca. 300 MB). Installere nå?"))
            dlg.add_response("nei", i18n.tr("Avbryt"))
            dlg.add_response("ja", i18n.tr("Installer"))
            dlg.set_response_appearance("ja", Adw.ResponseAppearance.SUGGESTED)
            dlg.connect("response", lambda _d, r_: r_ == "ja" and self._run("Installerer tale til tekst",
                                                                             aitale.install_stt))
            dlg.present(self.get_root())
            return
        try:
            CX.rec_start()
        except Exception as e:  # noqa: BLE001
            self.status.set_label(f"✗ {e}")
            return
        self.mic.set_label("⏹️")
        self.status.set_label(i18n.tr("🔴 Snakk nå … trykk ⏹️ når du er ferdig"))

    def _log(self, line):
        lab = Gtk.Label(label=time.strftime("%H:%M ") + line, xalign=0, wrap=True, max_width_chars=34)
        lab.add_css_class("caption")
        self.panel_log.prepend(lab)

    def _panel_tick(self):
        if not self.panel_btn.get_active() or not self.get_mapped():
            return False
        while (c := self.panel_status.get_first_child()) is not None:
            self.panel_status.remove(c)
        self.panel_status.append(self._status_card())
        if not getattr(self, "_ptick", None):
            def again():
                if not self.panel_btn.get_active() or not self.get_mapped():
                    self._ptick = None
                    return False
                while (c := self.panel_status.get_first_child()) is not None:
                    self.panel_status.remove(c)
                self.panel_status.append(self._status_card())
                return True
            self._ptick = GLib.timeout_add_seconds(3, again)
        return False

    def _confirm_here(self, what, answer):
        """AI-en vil endre noe: kort med «Godta / Avbryt» rett i samtalen."""
        if not self.get_mapped():
            raise RuntimeError("AI-siden er ikke åpen")          # ai_bridge viser et vindu i stedet
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, halign=Gtk.Align.START, margin_top=4)
        box.add_css_class("ks-ai-ask")
        box.append(Gtk.Label(label="🤖 " + i18n.tr("AI-en vil:") + " " + what, xalign=0, wrap=True,
                             max_width_chars=60))
        row = Gtk.Box(spacing=8)
        ok = Gtk.Button(label=i18n.tr("Godta"))
        ok.add_css_class("suggested-action")
        no = Gtk.Button(label=i18n.tr("Avbryt"))
        done = {"v": False}

        def pick(v):
            if done["v"]:
                return
            done["v"] = True
            ok.set_sensitive(False)
            no.set_sensitive(False)
            box.append(_dim(("✓ " + i18n.tr("Godtatt")) if v else ("✗ " + i18n.tr("Avbrutt")), True))
            self._log(("✓ " if v else "✗ ") + what.splitlines()[0])
            answer(v)
        ok.connect("clicked", lambda *_: pick(True))
        no.connect("clicked", lambda *_: pick(False))
        row.append(ok)
        row.append(no)
        box.append(row)
        if self._live is not None:
            self._live._wrap.append(box)
        else:
            self.msgs.append(box)
        self._scroll_end()
        try:
            self.get_root().present()
        except Exception:  # noqa: BLE001
            pass

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
                tl = Gtk.Label(label=("📌 " if cv.get("pinned") else "") + (cv.get("emoji") + " " if cv.get("emoji")
                                                                          else "") + cv["title"],
                               xalign=0, ellipsize=Pango.EllipsizeMode.END)
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
        cv = next((x for x in S.conversations() if x["id"] == cid), {})
        items = [("📌 Løsne" if cv.get("pinned") else "📌 Fest øverst",
                  lambda: (S.set_meta(cid, pinned=not cv.get("pinned")), self._reload_list())),
                 ("😀 Velg emoji …", lambda: self._emoji_for(cid)),
                 ("✏️ Gi nytt navn", lambda: self._rename(cid)), ("🗑️ Slett samtalen", lambda: self._delete(cid))]
        for label, fn in items:
            b = Gtk.Button(label=i18n.tr(label))
            b.add_css_class("flat")
            b.get_child().set_xalign(0)
            b.connect("clicked", lambda _b, f=fn: (pop.popdown(), f()))
            box.append(b)
        pop.set_child(box)
        pop.set_parent(widget)
        pop.connect("closed", lambda p: GLib.idle_add(p.unparent))
        pop.popup()

    def _emoji_for(self, cid):
        dlg = Adw.AlertDialog(heading=i18n.tr("Emoji for samtalen"))
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=8)
        for e in "💡 🎮 🛠️ 🌡️ 📚 💻 🎵 🏠 ❤️ ⭐ 🔥 🚀 🐉 🧪 📝".split() + [""]:
            b = Gtk.Button(label=e or i18n.tr("Ingen"))
            b.add_css_class("flat")
            b.connect("clicked", lambda _b, ee=e: (S.set_meta(cid, emoji=ee), dlg.close(), self._reload_list()))
            flow.append(b)
        dlg.set_extra_child(flow)
        dlg.add_response("close", i18n.tr("Lukk"))
        dlg.present(self.get_root())

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
        if not cv or not cv.get("messages"):                 # forslagskort
            outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, vexpand=True, valign=Gtk.Align.CENTER)
            hint = Gtk.Label(label=i18n.tr("Hva kan jeg hjelpe med?"))
            hint.add_css_class("title-2")
            outer.append(hint)
            flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=4, min_children_per_line=2,
                               column_spacing=8, row_spacing=8, homogeneous=True, halign=Gtk.Align.CENTER)
            for emo, q in SUGGESTIONS:
                b = Gtk.Button()
                b.add_css_class("flat")
                b.add_css_class("ks-sugg")
                v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                e = Gtk.Label(label=emo, xalign=0)
                e.add_css_class("title-3")
                v.append(e)
                v.append(Gtk.Label(label=i18n.tr(q), xalign=0, wrap=True, max_width_chars=22, lines=3,
                                   ellipsize=Pango.EllipsizeMode.END))
                b.set_child(v)
                b.set_size_request(170, 90)
                b.connect("clicked", lambda _b, qq=q: (self.prompt.get_buffer().set_text(i18n.tr(qq)), self._send()))
                flow.append(b)
            outer.append(flow)
            self.msgs.append(outer)
            return
        last = 0
        for m in cv["messages"]:
            if m.get("t", 0) - last > 600:
                tl = Gtk.Label(label=_when(m.get("t", 0)), halign=Gtk.Align.CENTER)
                tl.add_css_class("ks-bub-time")
                self.msgs.append(tl)
            last = m.get("t", 0)
            self._bubble(m["text"], m["role"] == "user", m.get("tool"), m.get("tools"), m.get("images"))
        self._scroll_end()

    def _bubble(self, text, mine, tool=None, tools=None, images=None):
        wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, halign=Gtk.Align.END if mine else Gtk.Align.START)
        if not mine and tool:                                # ikon og farge per assistent
            wh = Gtk.Box(spacing=5, margin_start=8)
            ic = Gtk.Image(pixel_size=16)
            try:
                ic.set_from_file(os.path.join(APP_DIR, "icons", ai.TOOLS.get(tool, {}).get("icon", "")))
            except Exception:  # noqa: BLE001
                pass
            wh.append(ic)
            pz = ai.PERSONAS.get(ai.cfg().get("persona", "standard"), ai.PERSONAS["standard"])
            who = Gtk.Label(xalign=0)
            who.set_markup(f'<span foreground="{ai.TOOL_COLOR.get(tool, "#888")}" weight="bold">'
                           f'{GLib.markup_escape_text(ai.TOOLS.get(tool, {}).get("name", ""))}</span>'
                           + (f"  {pz[1]}" if pz[2] else ""))
            who.add_css_class("ks-bub-who")
            wh.append(who)
            wrap.append(wh)
        for im in images or []:                              # bilder du la ved
            try:
                from gi.repository import GdkPixbuf
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(im, 220, 160, True)
                pic = Gtk.Picture.new_for_paintable(Gdk.Texture.new_for_pixbuf(pb))
                pic.set_can_shrink(False)
                pic.set_halign(Gtk.Align.END if mine else Gtk.Align.START)
                wrap.append(pic)
            except Exception:  # noqa: BLE001
                pass
        tl = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)     # «hva AI-en gjorde»
        for line in tools or []:
            lab = Gtk.Label(label=line, xalign=0)
            lab.add_css_class("ks-ai-tool")
            tl.append(lab)
        wrap.append(tl)
        b = Gtk.Box()
        b.add_css_class("ks-bub-me" if mine else "ks-bub-ai")
        if not mine and tool:
            prov = Gtk.CssProvider()
            prov.load_from_data(f"box {{ border-left-color: {ai.TOOL_COLOR.get(tool, '#888')}; }}".encode())
            b.get_style_context().add_provider(prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 5)
        b.append(_bubble_content(text, mine, self._width()))
        wrap.append(b)
        b._tools, b._wrap = tl, wrap
        if not mine:
            wrap.append(self._actions(lambda: b._text if hasattr(b, "_text") else text))
            if any(str(t).startswith("🌡️") for t in tools or []):
                wrap.append(self._status_card())
        gap = 40 if self._width() > 90 else 80
        wrap.set_margin_start(0 if mine is False else gap)
        wrap.set_margin_end(gap if mine is False else 0)
        self.msgs.append(wrap)
        return b

    def _actions(self, get_text):
        """🔊 Les opp · 📋 Kopier under svaret."""
        row = Gtk.Box(spacing=2, margin_start=6)
        row.add_css_class("ks-ai-act")
        sp = Gtk.Button(label="🔊", tooltip_text=i18n.tr("Les opp"))
        sp.add_css_class("flat")

        def speak(_b):
            import aitale
            if aitale._SPEAK["p"] and aitale._SPEAK["p"].poll() is None:
                aitale.stop()
                return
            _bg(lambda: aitale.speak(get_text()), lambda r_: isinstance(r_, Exception) and
                self.status.set_label(f"✗ {r_}"))
        sp.connect("clicked", speak)
        row.append(sp)
        cp = Gtk.Button(label="📋", tooltip_text=i18n.tr("Kopier svaret"))
        cp.add_css_class("flat")
        cp.connect("clicked", lambda b_: (Gdk.Display.get_default().get_clipboard().set(get_text()),
                                          b_.set_label("✓")))
        row.append(cp)
        return row

    def _status_card(self):
        """Svar som kort: målere for det AI-en nettopp leste (oppdateres ikke – viser verdiene nå)."""
        card_ = Gtk.Box(spacing=18, margin_top=6)
        card_.add_css_class("ks-ai-card")
        try:
            import homepcs
            st = homepcs.status(self.get_root())
        except Exception:  # noqa: BLE001
            st = {}
        for title, v, unit, warn in (("CPU", st.get("cpu_t"), "°C", 85), ("GPU", st.get("gpu_t"), "°C", 83),
                                     ("Last", st.get("cpu_l"), "%", 90), ("Strøm", st.get("watts"), "W", 10 ** 6)):
            if v is None:
                continue
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            big = Gtk.Label(label=f"{round(float(v))} {unit}", xalign=0)
            big.add_css_class("big")
            if float(v) >= warn:
                big.add_css_class("error")
            col.append(big)
            col.append(_dim(title, True))
            if unit in ("°C", "%"):
                lb = Gtk.LevelBar(min_value=0, max_value=100, value=min(100, float(v)))
                lb.set_size_request(70, -1)
                col.append(lb)
            card_.append(col)
        return card_

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

    def _settings_box(self, pop):
        """Personlighet, Godta før endringer, morgenrapport, hurtigtast, les opp, automatiske oppgaver."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        c = ai.cfg()
        box.append(Gtk.Label(label=i18n.tr("Personlighet"), xalign=0))
        keys = list(ai.PERSONAS)
        dd = Gtk.DropDown.new_from_strings([f"{ai.PERSONAS[k][1]} {i18n.tr(ai.PERSONAS[k][0])}" for k in keys])
        dd.set_selected(keys.index(c.get("persona", "standard")) if c.get("persona", "standard") in keys else 0)
        dd.connect("notify::selected", lambda d, _p: ai.set_(persona=keys[d.get_selected()]))
        box.append(dd)
        for key, label, default in (("confirm", "Spør meg før AI-en endrer noe", True),
                                    ("daily", "Morgenrapport om PC-en hver dag kl. 08", True),
                                    ("hotkey", "Hurtigtast Ctrl+Shift+A – spør AI-en fra hvor som helst", True),
                                    ("speak_all", "Les opp alle svar", False),
                                    ("voice_send", "Send med en gang etter at du har snakket", True)):
            row = Gtk.Box(spacing=8)
            row.append(Gtk.Label(label=i18n.tr(label), xalign=0, hexpand=True, wrap=True, max_width_chars=30))
            sw = Gtk.Switch(active=bool(c.get(key, default)), valign=Gtk.Align.CENTER)
            sw.connect("notify::active", lambda w, _p, k=key: (ai.set_(**{k: w.get_active()}),
                                                               k == "hotkey" and self._hotkey_changed()))
            row.append(sw)
            box.append(row)
        rb = Gtk.Button(label="🤖 " + i18n.tr("Automatiske oppgaver …"))
        rb.add_css_class("flat")
        rb.connect("clicked", lambda *_: (pop.popdown(), self._rules_dialog()))
        box.append(rb)
        db = Gtk.Button(label="☀️ " + i18n.tr("Lag morgenrapporten nå"))
        db.add_css_class("flat")
        db.connect("clicked", lambda *_: (pop.popdown(), _bg(lambda: __import__("aiextra").daily_report(
            self.get_root(), force=True), lambda r_: (self.status.set_label(str(r_)), self._reload_list()))))
        box.append(db)
        box.append(Gtk.Separator(margin_top=4, margin_bottom=4))
        return box

    def _hotkey_changed(self):
        try:
            import aiextra
            aiextra.hotkey_setup(self.get_root())
        except Exception:  # noqa: BLE001
            pass

    def _rules_dialog(self):
        import ai_rules
        dlg = Adw.AlertDialog(heading=i18n.tr("Automatiske oppgaver"),
                              body=i18n.tr("Lages av AI-en – f.eks. «Si fra hvis GPU-en går over 85 °C mens jeg "
                                           "spiller» eller «Rydd hver søndag kl. 12»."))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        def fill():
            while (c := box.get_first_child()) is not None:
                box.remove(c)
            rules = ai_rules.load()
            if not rules:
                box.append(_dim(i18n.tr("Ingen ennå – spør AI-en om å lage en.")))
            for r_ in rules:
                row = Gtk.Box(spacing=8)
                row.append(Gtk.Label(label=ai_rules.describe(r_), xalign=0, hexpand=True, wrap=True,
                                     max_width_chars=44))
                d = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text=i18n.tr("Slett"))
                d.add_css_class("flat")
                d.connect("clicked", lambda _b, rid=r_["id"]: (ai_rules.remove(rid), fill()))
                row.append(d)
                box.append(row)
        fill()
        dlg.set_extra_child(box)
        dlg.add_response("close", i18n.tr("Lukk"))
        dlg.present(self.get_root())

    def _look_box(self, pop):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=4)
        box.append(self._settings_box(pop))
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
        if keyval in (Gdk.KEY_v, Gdk.KEY_V) and state & Gdk.ModifierType.CONTROL_MASK and self._paste_image():
            return True
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
        imgs = list(self._images)
        self._images = []
        self._chips()
        self.conv["messages"].append({"role": "user", "text": q, "t": time.time(), **({"images": imgs} if imgs else {})})
        S.save(self.conv)
        if len(self.conv["messages"]) == 1:
            self.title.set_label(self.conv.get("title") or q[:48])
            self._reload_list()
        self._bubble(q, True, images=imgs)
        # «skriver …»-boble som fylles med svaret
        self._live = self._bubble("• • •", False, self.tool)
        self._live_text = ""
        self._live_tools = []
        self._scroll_end()
        c = ai.cfg()
        self.status.set_label(f"{ai.TOOLS[self.tool]['name']} {i18n.tr('tenker')} …")
        self.send_btn.set_label("■")
        self.send_btn.set_tooltip_text(i18n.tr("Stopp"))
        self._t0 = time.time()
        try:
            self.proc = ai.ask(self.tool, q, S.workdir(), c["allow_edit"], on_text=self._append,
                               on_done=lambda code: GLib.idle_add(lambda: (self._done(code), False)[1]),
                               history=S.history_text(self.conv), control=c.get("control", True), images=imgs,
                               on_event=lambda k, d: GLib.idle_add(lambda: (self._event(k, d), False)[1]))
        except Exception as e:  # noqa: BLE001
            self._done(None, str(e))

    def _event(self, kind, data):
        """Underveis: «hva AI-en gjør» og bruk av kvoten."""
        if kind == "tool" and self._live is not None:
            self._live_tools.append(str(data))
            lab = Gtk.Label(label=str(data), xalign=0)
            lab.add_css_class("ks-ai-tool")
            self._live._tools.append(lab)
            self.status.set_label(str(data))
            self._log(str(data))
            self._scroll_end()
        elif kind == "quota":
            self._show_quota()

    def _show_quota(self):
        q = ai.quota().get(self.tool) or {}
        if self.tool == "claude" and q.get("five_hour") is not None:
            txt = (f"⏱️ {round(q['five_hour'] * 100)} % av 5-timers grensen · "
                   f"{round((q.get('seven_day') or 0) * 100)} % av uka")
        elif q.get("tokens"):
            txt = f"🔢 {q['tokens']:,} tegnbiter sist".replace(",", " ")
        else:
            txt = ""
        self.quota.set_label(txt)
        self.quota.set_visible(bool(txt))

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
            self.conv["messages"].append({"role": "assistant", "text": text, "t": time.time(), "tool": self.tool,
                                          **({"tools": self._live_tools} if getattr(self, "_live_tools", None) else {})})
            S.save(self.conv)
            t0 = getattr(self, "_t0", time.time())
            threading.Thread(target=S.push_changed, args=(t0,), daemon=True).start()
        if self._live is not None:
            while (ch := self._live.get_first_child()) is not None:
                self._live.remove(ch)
            self._live.append(_bubble_content(text or "…", False, self._width()))
            self._live._text = text
            if any(t.startswith("🌡️") for t in getattr(self, "_live_tools", [])):
                self._live._wrap.append(self._status_card())
            if ai.cfg().get("speak_all"):
                import aitale
                _bg(lambda t=text: aitale.speak(t), lambda _r: None)
        self._live = None
        self.status.set_label("" if code == 0 else (i18n.tr("Stoppet") if code else ""))
        self._reload_list()
        self.prompt.grab_focus()
