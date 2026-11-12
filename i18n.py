"""Språkstøtte for Kontrollsenter (norsk / engelsk).

Programmet er skrevet med norsk tekst. Når engelsk er valgt, oversettes teksten idet den
settes på etiketter, knapper, dialoger, faner, menyer og verktøytips – uten at resten av
koden må endres. Oversettelsene ligger i en.json. Tekster med tall/navn i (f.eks.
«Lagret til musen ✓») står der med {} som plassholder.

Kall i18n.install() før noe vindu lages.
"""
import json
import os
import re

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.expanduser("~/.config/systemmonitor/language.json")
LANGS = [("no", "NO", "Norsk"), ("en", "EN", "English"), ("auto", "Auto", "Følger språket i Linux")]

LANG = "no"
CHOICE = "auto"         # «auto» = følg språket i Linux
_EXACT = {}
_PATTERNS = []          # (regex, mal)
MISSING = set()         # for utvikling: tekster uten oversettelse
COLLECT = False


def os_lang():
    """Språket i Linux: norsk (nb/nn/no) gir norsk, alle andre språk gir engelsk."""
    for name in GLib.get_language_names():
        code = name.split("_")[0].split(".")[0].split("@")[0].lower()
        if code in ("c", "posix", ""):
            continue
        return "no" if code in ("nb", "nn", "no") else "en"
    return "en"


def get_choice():
    """Brukerens valg: «auto», «no» eller «en». (Gamle filer med «lang» regnes som «auto».)"""
    try:
        with open(CFG) as f:
            c = json.load(f).get("choice", "auto")
            return c if c in ("auto", "no", "en") else "auto"
    except (OSError, ValueError):
        return "auto"


def resolve(choice):
    return os_lang() if choice == "auto" else choice


def get_lang():
    return resolve(get_choice())


def set_lang(choice):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    with open(CFG, "w") as f:
        json.dump({"choice": choice}, f)


def _load(lang):
    _EXACT.clear()
    _PATTERNS.clear()
    if lang == "no":
        return
    try:
        with open(os.path.join(APP_DIR, f"{lang}.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return
    for src, dst in data.items():
        if "{}" in src:
            parts = [re.escape(p) for p in src.split("{}")]
            _PATTERNS.append((re.compile("^" + "(.+?)".join(parts) + "$", re.S), dst))
        else:
            _EXACT[src] = dst
    _PATTERNS.sort(key=lambda p: -len(p[0].pattern))       # mest spesifikke først


def tr(s):
    """Oversett én tekst (returnerer originalen hvis den ikke finnes)."""
    if LANG == "no" or not isinstance(s, str) or not s.strip():
        return s
    if s in _EXACT:
        return _EXACT[s]
    st = s.strip()
    if st != s and st in _EXACT:                            # behold mellomrom rundt
        return s.replace(st, _EXACT[st])
    for rx, dst in _PATTERNS:
        m = rx.match(s)
        if m:
            vals = [tr(v) for v in m.groups()]               # f.eks. «musen» i «Lagret til musen ✓»
            try:
                return dst.format(*vals)
            except (IndexError, KeyError):
                return s
    if COLLECT and re.search(r"[A-Za-zÆØÅæøå]{2,}", s):
        MISSING.add(s)
    return s


def tr_markup(s):
    """Oversett teksten mellom taggene i Pango-markup."""
    if LANG == "no" or not isinstance(s, str):
        return s
    return re.sub(r"(^|>)([^<]+)", lambda m: m.group(1) + _tr_keep_space(m.group(2)), s)


def _tr_keep_space(t):
    core = t.strip()
    if not core:
        return t
    return t.replace(core, tr(core), 1)


# --------------------------------------------------------------------------
# Kroker inn i GTK
# --------------------------------------------------------------------------
_TEXT_KW = ("label", "title", "tooltip_text", "placeholder_text", "heading", "body", "subtitle",
            "text", "initial_name")


def _wrap_init(cls):
    orig = cls.__init__

    def __init__(self, *a, **kw):
        for k in _TEXT_KW:
            if k in kw and isinstance(kw[k], str):
                kw[k] = tr(kw[k])
        orig(self, *a, **kw)
    cls.__init__ = __init__


def _wrap_method(cls, name, argi=0, fn=None):
    orig = getattr(cls, name, None)
    if orig is None:
        return
    fn = fn or tr

    def wrapper(self, *a, **kw):
        a = list(a)
        if len(a) > argi and isinstance(a[argi], str):
            a[argi] = fn(a[argi])
        return orig(self, *a, **kw)
    setattr(cls, name, wrapper)


def _wrap_static(cls, name):
    orig = getattr(cls, name)

    def wrapper(strings, *a, **kw):
        return orig([tr(x) if isinstance(x, str) else x for x in (strings or [])], *a, **kw)
    setattr(cls, name, staticmethod(wrapper))


_INSTALLED = [False]


def install():
    global LANG, CHOICE
    if _INSTALLED[0]:            # krokene skal bare legges på én gang
        return
    _INSTALLED[0] = True
    CHOICE = get_choice()
    LANG = get_lang()
    _load(LANG)
    if LANG == "no":
        return
    for cls in (Gtk.Label, Gtk.Button, Gtk.ToggleButton, Gtk.CheckButton, Gtk.MenuButton,
                Adw.ButtonContent, Adw.Banner, Adw.AlertDialog, Adw.Dialog, Gtk.FileDialog,
                Gtk.SearchEntry, Gtk.Entry, Gtk.PasswordEntry, Gtk.Window, Adw.ApplicationWindow, Adw.WindowTitle):
        _wrap_init(cls)
    for cls, name in ((Gtk.Label, "set_label"), (Gtk.Label, "set_text"), (Gtk.Button, "set_label"),
                      (Gtk.CheckButton, "set_label"), (Gtk.MenuButton, "set_label"),
                      (Adw.ButtonContent, "set_label"), (Gtk.Widget, "set_tooltip_text"),
                      (Gtk.Window, "set_title"), (Adw.Dialog, "set_title"),
                      (Adw.AlertDialog, "set_heading"), (Adw.AlertDialog, "set_body"),
                      (Adw.Banner, "set_title"), (Adw.WindowTitle, "set_title"),
                      (Gtk.Entry, "set_placeholder_text"),
                      (Gtk.SearchEntry, "set_placeholder_text")):
        _wrap_method(cls, name)
    _wrap_method(Gtk.Label, "set_markup", fn=tr_markup)
    _wrap_method(Adw.AlertDialog, "add_response", argi=1)
    _wrap_method(Gtk.Stack, "add_titled", argi=2)
    _wrap_method(Adw.ViewStack, "add_titled", argi=2)
    _wrap_method(Adw.ViewStack, "add_titled_with_icon", argi=2)
    _wrap_static(Gtk.DropDown, "new_from_strings")
    _wrap_static(Gtk.StringList, "new")
