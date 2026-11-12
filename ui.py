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
    """Tom side: stort grått ikon, én tittel og en kort forklaring."""
    import i18n
    page = Adw.StatusPage(icon_name=icon, title=i18n.tr(title), description=i18n.tr(description))
    if compact:
        page.add_css_class("compact")
    page.set_vexpand(False)
    return page
