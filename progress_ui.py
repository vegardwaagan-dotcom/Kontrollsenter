"""Fremdriftslinjen nederst i vinduet: hva som skjer, prosent og tid igjen – enkel og elegant."""
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

import i18n  # noqa: E402
import progress  # noqa: E402

CSS = """
.ks-progress-dock { margin-bottom: 18px; }
.ks-progress-item { border-radius: 18px; padding: 12px 16px; min-width: 420px;
  background: alpha(@window_bg_color, .97); border: 1px solid alpha(currentColor, .12);
  box-shadow: 0 10px 34px alpha(black, .35); }
.ks-progress-item progressbar trough { min-height: 6px; border-radius: 99px; background: alpha(currentColor, .10); }
.ks-progress-item progressbar progress { min-height: 6px; border-radius: 99px;
  background-image: linear-gradient(90deg, @accent_bg_color, shade(@accent_bg_color, 1.25)); }
.ks-progress-item.ok progressbar progress { background-image: linear-gradient(90deg, #2ec27e, #57e389); }
.ks-progress-item.bad progressbar progress { background-image: linear-gradient(90deg, #e01b24, #f66151); }
.ks-progress-title { font-weight: 700; }
.ks-progress-pct { font-weight: 800; font-feature-settings: "tnum"; }
"""


class _Item(Gtk.Box):
    def __init__(self, t):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.t = t
        self.add_css_class("ks-progress-item")
        top = Gtk.Box(spacing=10)
        self.title = Gtk.Label(xalign=0, hexpand=True, ellipsize=3)
        self.title.add_css_class("ks-progress-title")
        top.append(self.title)
        self.pct = Gtk.Label(xalign=1)
        self.pct.add_css_class("ks-progress-pct")
        top.append(self.pct)
        self.append(top)
        self.bar = Gtk.ProgressBar()
        self.append(self.bar)
        bot = Gtk.Box(spacing=10)
        self.detail = Gtk.Label(xalign=0, hexpand=True, ellipsize=3)
        self.detail.add_css_class("dim-label")
        self.detail.add_css_class("caption")
        bot.append(self.detail)
        self.eta = Gtk.Label(xalign=1)
        self.eta.add_css_class("dim-label")
        self.eta.add_css_class("caption")
        bot.append(self.eta)
        self.append(bot)
        self.sync()

    def sync(self):
        t = self.t
        self.title.set_label(i18n.tr(t.title))
        if t.finished:
            self.add_css_class("ok" if t.ok else "bad")
            self.pct.set_label("✓" if t.ok else "✗")
            self.bar.set_fraction(1.0)
            self.detail.set_label(i18n.tr(t.result or ("Ferdig" if t.ok else "Feilet")))
            self.eta.set_label("")
            return
        if t.frac is None:
            self.bar.pulse()
            self.pct.set_label("")
        else:
            self.bar.set_fraction(t.frac)
            self.pct.set_label(t.pct_text())
        self.detail.set_label(i18n.tr(t.detail or ""))
        self.eta.set_label(i18n.tr(t.eta_text()))


class Dock(Gtk.Box):
    """Legges som et overlegg nederst i vinduet."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8, halign=Gtk.Align.CENTER,
                         valign=Gtk.Align.END, can_target=False)
        self.add_css_class("ks-progress-dock")
        try:
            import theme
            theme.add_css(CSS, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 5)
        except Exception:  # noqa: BLE001
            pass
        self.items = {}
        self._tid = 0
        self.set_visible(False)
        progress.on_change(lambda: GLib.idle_add(self._wake))

    def _wake(self):
        if not self._tid:
            self._tid = GLib.timeout_add(150, self._tick)
            self._tick()
        return False

    def _tick(self):
        act = progress.active()
        ids = {id(t) for t in act}
        for k in [k for k in self.items if k not in ids]:
            self.remove(self.items.pop(k))
        for t in act:
            it = self.items.get(id(t))
            if it is None:
                it = self.items[id(t)] = _Item(t)
                self.append(it)
            it.sync()
        self.set_visible(bool(act))
        if not act:
            self._tid = 0
            return False
        return True


def attach(stack):
    """Pakk inn sidene i et overlegg med fremdriftslinjen nederst. Returnerer overlegget."""
    ov = Gtk.Overlay(child=stack)
    ov.add_overlay(Dock())
    return ov
