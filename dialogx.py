"""Alle vinduer som spretter opp skal kunne lukkes: får et vindu (Adw.Dialog) ikke en lukkeknapp fra en
topplinje, legger vi på en ✕ øverst til høyre. Spørsmål med egne knapper (Adw.AlertDialog) røres ikke.
Installeres én gang ved oppstart (install())."""
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

_ORIG = {}


def _has_close(w, depth=0):
    """Finnes det en topplinje med lukkeknapp (eller en egen «Lukk»-knapp) inni vinduet?"""
    if w is None or depth > 12:
        return False
    if isinstance(w, (Adw.HeaderBar, Gtk.HeaderBar)):
        try:
            if w.get_show_end_title_buttons():
                return True
        except AttributeError:
            return True
    if isinstance(w, Gtk.Button) and (w.get_label() or "").strip().lower() in ("lukk", "close", "ferdig", "✕"):
        return True
    c = w.get_first_child()
    while c is not None:
        if _has_close(c, depth + 1):
            return True
        c = c.get_next_sibling()
    return False


def _fit_alert(dlg, parent):
    """Spørsmål med mye innhold (f.eks. Funksjoner-lista): innholdet får rullefelt, så knappene nederst
    (Avbryt/Bruk) alltid er synlige – og Esc lukker alltid."""
    extra = dlg.get_extra_child()
    if extra is not None and not isinstance(extra, Gtk.ScrolledWindow):
        h = 0
        try:
            root = parent.get_root() if parent is not None else None
            h = root.get_height() if root is not None else 0
        except AttributeError:
            pass
        dlg.set_extra_child(None)
        sw = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, propagate_natural_height=True,
                                propagate_natural_width=True, max_content_height=max(220, int((h or 800) * 0.55)))
        sw.set_child(extra)
        dlg.set_extra_child(sw)
    try:
        if not dlg.has_response(dlg.get_close_response()):
            for cand in ("cancel", "nei", "no", "avbryt", "close", "lukk", "ok"):
                if dlg.has_response(cand):
                    dlg.set_close_response(cand)
                    break
    except AttributeError:
        pass


def ensure_close(dlg, parent=None):
    if getattr(dlg, "_ks_x", False):
        return
    if isinstance(dlg, Adw.AlertDialog):
        dlg._ks_x = True
        _fit_alert(dlg, parent)
        return
    dlg._ks_x = True
    child = dlg.get_child()
    if child is None or _has_close(child):
        return
    dlg.set_child(None)
    ov = Gtk.Overlay(child=child)
    btn = Gtk.Button(icon_name="window-close-symbolic", halign=Gtk.Align.END, valign=Gtk.Align.START,
                     margin_top=8, margin_end=8, tooltip_text="Lukk (Esc)")
    btn.add_css_class("circular")
    btn.connect("clicked", lambda *_: dlg.close())
    ov.add_overlay(btn)
    dlg.set_child(ov)


def install():
    if _ORIG:
        return
    _ORIG["present"] = Adw.Dialog.present

    def present(self, *a, **k):
        try:
            ensure_close(self, a[0] if a else k.get("parent"))
        except Exception:  # noqa: BLE001
            pass
        return _ORIG["present"](self, *a, **k)
    Adw.Dialog.present = present
