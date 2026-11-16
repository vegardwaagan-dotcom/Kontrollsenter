"""Familiekontroll: kode for å lukke Kontrollsenter og endre familieinnstillingene på PC-en.

* Koden lagres som PBKDF2-hash med salt – aldri i klartekst.
* Når låsen er på: «Avslutt» krever koden, og lukking av vinduet legger programmet i bakgrunnen i stedet
  for å avslutte. Familieinnstillingene (spilletid, leggetid, «la andre se skjermen», oppstart) krever koden.
* Foreldre kan slå låsen av/på og nullstille koden fra telefonen (full tilgang).
* NB: Med samme brukerkonto kan et program alltid tvinges ned (Oppgavebehandling / kill). Sterkest vern får
  barnet med en egen standardkonto – da kan det heller ikke endre filene til Kontrollsenter for foreldrene.
"""
import hashlib
import hmac
import json
import os
import secrets
import sys
import time

CFG = os.path.expanduser("~/.config/systemmonitor/familielas.json")
IS_WIN = sys.platform == "win32"
_FAILS = {"n": 0, "until": 0}


def cfg():
    try:
        with open(CFG, encoding="utf-8") as f:
            c = json.load(f)
    except (OSError, ValueError):
        c = {}
    return {"on": False, "hash": "", "salt": "", **c}


def _save(c):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    tmp = CFG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(c, f)
    if not IS_WIN:
        os.chmod(tmp, 0o600)
    os.replace(tmp, CFG)


def _hash(pin, salt):
    return hashlib.pbkdf2_hmac("sha256", str(pin).encode(), bytes.fromhex(salt), 200_000).hex()


def locked():
    c = cfg()
    return bool(c["on"] and c["hash"])


def valid_pin(pin):
    return str(pin).isdigit() and 4 <= len(str(pin)) <= 8


def set_pin(pin):
    if not valid_pin(pin):
        raise ValueError("Koden må være 4–8 sifre")
    salt = secrets.token_hex(16)
    c = cfg()
    c.update(on=True, salt=salt, hash=_hash(pin, salt))
    _save(c)
    _event("Familiekontroll er slått på", "Det trengs kode for å lukke Kontrollsenter")


def turn_off():
    c = cfg()
    c.update(on=False, hash="", salt="")
    _save(c)
    _event("Familiekontroll er slått av", "")


def check(pin):
    """True hvis koden stemmer. Brems etter 5 feil (30 s)."""
    if time.time() < _FAILS["until"]:
        return False
    c = cfg()
    if not c["hash"]:
        return True
    ok = hmac.compare_digest(_hash(pin, c["salt"]), c["hash"])
    if ok:
        _FAILS["n"] = 0
    else:
        _FAILS["n"] += 1
        if _FAILS["n"] >= 5:
            _FAILS.update(n=0, until=time.time() + 30)
            _event("Feil kode for familiekontroll 5 ganger", "Noen prøvde å lukke eller endre Kontrollsenter", "warn")
    return ok


def wait_seconds():
    return max(0, int(_FAILS["until"] - time.time()))


def _event(title, body, level="info"):
    try:
        import remote_extra
        remote_extra.event("family", title, body, level)
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------
# GTK: spør om koden (kalles fra hovedtråden)
# --------------------------------------------------------------------------
def ask(parent, reason, on_ok, on_cancel=None):
    """Kjør on_ok() hvis låsen er av eller koden stemmer."""
    if not locked():
        on_ok()
        return
    import gi
    gi.require_version("Adw", "1")
    gi.require_version("Gtk", "4.0")
    from gi.repository import Adw, Gtk
    import i18n
    d = Adw.AlertDialog(heading=i18n.tr("Familiekontroll"), body=i18n.tr(reason))
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    entry = Gtk.PasswordEntry(placeholder_text=i18n.tr("Kode"), show_peek_icon=False)
    box.append(entry)
    err = Gtk.Label(xalign=0)
    err.add_css_class("error")
    box.append(err)
    d.set_extra_child(box)
    d.add_response("nei", i18n.tr("Avbryt"))
    d.add_response("ja", i18n.tr("OK"))
    d.set_response_appearance("ja", Adw.ResponseAppearance.SUGGESTED)
    d.set_default_response("ja")
    d.set_close_response("nei")
    d.set_response_enabled("ja", True)

    def done(_d, resp):
        if resp != "ja":
            if on_cancel:
                on_cancel()
            return
        if check(entry.get_text()):
            on_ok()
        else:
            w = wait_seconds()
            # vis dialogen på nytt med beskjed
            ask_again = Adw.AlertDialog(heading=i18n.tr("Feil kode"),
                                        body=(i18n.tr("Prøv igjen om {} sekunder.").replace("{}", str(w)) if w
                                              else i18n.tr("Koden stemmer ikke.")))
            ask_again.add_response("ok", "OK")
            ask_again.connect("response", lambda *_: on_cancel and on_cancel())
            ask_again.present(parent)
    d.connect("response", done)
    entry.connect("activate", lambda *_: (d.close(), done(d, "ja")))
    d.present(parent)


def ask_new_pin(parent, on_done):
    """Velg ny kode (to ganger). on_done(True/False)."""
    import gi
    gi.require_version("Adw", "1")
    gi.require_version("Gtk", "4.0")
    from gi.repository import Adw, Gtk
    import i18n
    d = Adw.AlertDialog(heading=i18n.tr("Velg kode for familiekontroll"),
                        body=i18n.tr("4–8 sifre. Koden trengs for å lukke Kontrollsenter og endre "
                                     "familieinnstillingene. Glemt den? Slå den av fra telefonen."))
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    a = Gtk.PasswordEntry(placeholder_text=i18n.tr("Ny kode"))
    b = Gtk.PasswordEntry(placeholder_text=i18n.tr("Samme kode en gang til"))
    for e in (a, b):
        box.append(e)
    d.set_extra_child(box)
    d.add_response("nei", i18n.tr("Avbryt"))
    d.add_response("ja", i18n.tr("Lagre"))
    d.set_response_appearance("ja", Adw.ResponseAppearance.SUGGESTED)

    def done(_d, resp):
        if resp != "ja":
            on_done(False)
            return
        if a.get_text() != b.get_text() or not valid_pin(a.get_text()):
            err = Adw.AlertDialog(heading=i18n.tr("Koden ble ikke lagret"),
                                  body=i18n.tr("Kodene må være like og ha 4–8 sifre."))
            err.add_response("ok", "OK")
            err.connect("response", lambda *_: on_done(False))
            err.present(parent)
            return
        set_pin(a.get_text())
        on_done(True)
    d.connect("response", done)
    d.present(parent)
