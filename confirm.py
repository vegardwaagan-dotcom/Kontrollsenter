"""Felles «Tilbakestill til fabrikkstandard»-knapp med bekreftelsesdialog."""
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402


def confirm_reset(parent, what, details, on_yes):
    """Viser en dialog. on_yes() kalles bare hvis brukeren bekrefter."""
    d = Adw.AlertDialog(
        heading=f"Tilbakestille {what} til fabrikkstandard?",
        body=details + "\n\nDette kan ikke angres.",
    )
    d.add_response("cancel", "Avbryt")
    d.add_response("reset", "Tilbakestill")
    d.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)
    d.set_default_response("cancel")
    d.set_close_response("cancel")
    d.connect("response", lambda _d, r: on_yes() if r == "reset" else None)
    d.present(parent)
    return d


def reset_button(what, details, on_yes):
    """Knapp som åpner bekreftelsen. Plasser den der du vil i fanen."""
    b = Gtk.Button(child=Adw.ButtonContent(label="Tilbakestill", icon_name="edit-undo-symbolic"),
                   valign=Gtk.Align.CENTER)
    b.add_css_class("destructive-action")
    b.set_tooltip_text(f"Tilbakestill {what} til fabrikkstandard")
    b.connect("clicked", lambda btn: confirm_reset(btn, what, details, on_yes))
    return b
