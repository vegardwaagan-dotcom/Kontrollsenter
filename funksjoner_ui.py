"""Velg funksjoner: Fullstendig / Medium / Minimal / Egendefinert (veiviseren og Innstillinger)."""
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

import funksjoner as F  # noqa: E402
import i18n  # noqa: E402


class FeaturePicker(Gtk.Box):
    def __init__(self, profile=None, keys=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        c = F.cfg()
        self.profile = profile or c["profile"]
        start = set(keys) if keys is not None else set(F.enabled())
        seg = Gtk.Box(homogeneous=True)
        seg.add_css_class("linked")
        first = None
        self.btns = {}
        for key, (name, _desc, _ks) in F.PROFILES.items():
            b = Gtk.ToggleButton(label=i18n.tr(name), active=key == self.profile)
            if first:
                b.set_group(first)
            first = first or b
            b.connect("toggled", lambda btn, k=key: btn.get_active() and self._pick(k))
            seg.append(b)
            self.btns[key] = b
        self.append(seg)
        self.desc = Gtk.Label(wrap=True, xalign=0.5, justify=Gtk.Justification.CENTER)
        self.desc.add_css_class("dim-label")
        self.append(self.desc)
        try:
            import theme
            theme.add_css(".ks-feat checkbutton check { border: 2px solid alpha(@window_fg_color, 0.45); "
                          "min-width: 16px; min-height: 16px; }"
                          ".ks-feat checkbutton check:checked { border-color: transparent; }")
        except Exception:  # noqa: BLE001
            pass
        grid = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=2, min_children_per_line=2,
                           homogeneous=True, column_spacing=6, row_spacing=2)
        grid.add_css_class("ks-feat")
        self.checks = {}
        for key, name, sub, _pages, req in F.FEATURES:
            cb = Gtk.CheckButton(label=i18n.tr(name), active=key in start or req)
            cb.set_tooltip_text(i18n.tr(sub) if sub else None)
            if req:
                cb.set_sensitive(False)
            cb.connect("toggled", lambda *_: self._manual())
            grid.append(cb)
            self.checks[key] = cb
        self.sc = Gtk.ScrolledWindow(child=grid, hscrollbar_policy=Gtk.PolicyType.NEVER, min_content_height=240,
                                     max_content_height=340, propagate_natural_height=True)
        self.append(self.sc)
        self._sync_lock = False
        self._pick(self.profile, keep=keys is not None or self.profile == "custom")

    def _pick(self, key, keep=False):
        self.profile = key
        self.desc.set_label(i18n.tr(F.PROFILES[key][1]))
        ks = F.PROFILES[key][2]
        if ks is not None and not keep:
            self._sync_lock = True
            for k, cb in self.checks.items():
                cb.set_active(k in ks or k in F.REQUIRED)
            self._sync_lock = False

    def _manual(self):
        if not self._sync_lock and self.profile != "custom":
            self.btns["custom"].set_active(True)

    def get(self):
        return self.profile, [k for k, cb in self.checks.items() if cb.get_active()]


def apply(win, profile, keys):
    """Lagre, oppdater sidemenyen med en gang, og installer/fjern programmene funksjonene trenger (med fremdrift)."""
    F.save(profile, keys)
    try:
        import komponenter_ui
        komponenter_ui.run_for(win, F.enabled())
    except Exception:  # noqa: BLE001
        pass
    try:
        win.sidebar.invalidate_filter()
        win.sidebar.invalidate_headers()
        cur = win.stack.get_visible_child_name()
        if cur and not F.page_on(cur):
            win.stack.set_visible_child_name("oversikt")
    except Exception:  # noqa: BLE001
        pass


def open_dialog(win):
    dlg = Adw.AlertDialog(heading=i18n.tr("Funksjoner"),
                          body=i18n.tr("Funksjoner du slår av, forsvinner fra menyen og gjør ingenting i "
                                       "bakgrunnen. Du kan slå dem på igjen når du vil."))
    pk = FeaturePicker()
    dlg.set_extra_child(pk)
    dlg.add_response("nei", i18n.tr("Avbryt"))
    dlg.add_response("ja", i18n.tr("Bruk"))
    dlg.set_response_appearance("ja", Adw.ResponseAppearance.SUGGESTED)
    dlg.connect("response", lambda _d, r: r == "ja" and apply(win, *pk.get()))
    dlg.present(win)
