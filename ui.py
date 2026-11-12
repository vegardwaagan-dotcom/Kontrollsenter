"""Felles småting for et rolig, enhetlig utseende: toast-meldinger og tomme sider."""
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402


def toast(widget, text, timeout=3):
    """Vis en kort melding nederst i vinduet som forsvinner av seg selv.
    Returnerer False hvis vinduet ikke har plass til toasts (da kan en vanlig etikett brukes)."""
    root = widget.get_root() if widget else None
    overlay = getattr(root, "toast_overlay", None)
    if overlay is None:
        return False
    import i18n
    overlay.add_toast(Adw.Toast(title=i18n.tr(text), timeout=timeout))
    return True


def status(label, text):
    """Vis meldingen som toast hvis den er en bekreftelse (✓), ellers i etiketten som før."""
    if "✓" in text and toast(label, text):
        label.set_label("")
        return
    label.set_label(text)


def empty(icon, title, description="", compact=True):
    """Tom side: stort grått ikon, én tittel og en kort forklaring (passer også inne i kort og lister)."""
    import i18n
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, halign=Gtk.Align.CENTER)
    for side in ("top", "bottom"):
        getattr(box, f"set_margin_{side}")(18 if compact else 36)
    img = Gtk.Image(icon_name=icon, pixel_size=48 if compact else 72)
    img.add_css_class("dim-label")
    img.set_margin_bottom(6)
    box.append(img)
    t = Gtk.Label(label=i18n.tr(title), wrap=True, justify=Gtk.Justification.CENTER)
    t.add_css_class("title-4")
    box.append(t)
    if description:
        d = Gtk.Label(label=i18n.tr(description), wrap=True, justify=Gtk.Justification.CENTER, max_width_chars=60)
        d.add_css_class("dim-label")
        box.append(d)
    return box
