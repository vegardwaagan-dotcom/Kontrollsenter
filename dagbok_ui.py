"""Dagboken i Kalender: velg hvem du er, skriv koden (4–6 sifre), skriv dagens innlegg. Låses når du går fra siden
eller etter 5 minutter uten bruk."""
import datetime as dt
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

import dagbok as D  # noqa: E402
import i18n  # noqa: E402

MONTHS = ["jan.", "feb.", "mars", "april", "mai", "juni", "juli", "aug.", "sep.", "okt.", "nov.", "des."]


def _bg(fn, done):
    def work():
        try:
            r = fn()
        except Exception as e:  # noqa: BLE001
            r = e
        GLib.idle_add(lambda: (done(r), False)[1])
    threading.Thread(target=work, daemon=True).start()


def _dim(t):
    lab = Gtk.Label(label=t, xalign=0, wrap=True)
    lab.add_css_class("dim-label")
    lab.add_css_class("caption")
    return lab


class DiaryView(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        self.tok = None
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=16, margin_bottom=16,
                           margin_start=16, margin_end=16)
        clamp = Adw.Clamp(maximum_size=760, child=self.box)
        self.set_child(clamp)
        self.connect("map", lambda *_: self._show_people(sync=True))
        GLib.timeout_add_seconds(30, self._idle_check)

    def _clear(self):
        while (c := self.box.get_first_child()) is not None:
            self.box.remove(c)

    def lock(self):
        if self.tok:
            D.lock(self.tok)
            self.tok = None
            self._show_people()

    def _idle_check(self):
        if self.tok and self.tok not in D._SESS:             # låst av seg selv (5 min uten bruk)
            self.tok = None
            self._show_people()
        return True

    # ---- velg person
    def _show_people(self, sync=False):
        if self.tok:
            return
        self._clear()
        ic = Gtk.Label(label="🔒")
        ic.add_css_class("ks-diary-lock")
        self.box.append(ic)
        t = Gtk.Label(label=i18n.tr("Dagbok"))
        t.add_css_class("title-1")
        self.box.append(t)
        self.box.append(_dim(i18n.tr("Hver i familien har sin egen dagbok med egen kode (4–6 sifre). Den er kryptert – "
                                     "ingen kan lese den uten koden, heller ikke fra NAS-en. Glemmer du koden, kan den "
                                     "ikke hentes tilbake.")))
        self.list = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=4, column_spacing=10,
                                row_spacing=10, homogeneous=True)
        self.box.append(self.list)
        new = Gtk.Button(label="＋ " + i18n.tr("Ny dagbok"), halign=Gtk.Align.START)
        new.add_css_class("pill")
        new.connect("clicked", lambda *_: self._create())
        self.box.append(new)
        self._fill_people()
        if sync:
            _bg(D.sync_down, lambda _r: (not self.tok and self._fill_people()))

    def _fill_people(self):
        while (c := self.list.get_first_child()) is not None:
            self.list.remove(c)
        ps = D.people()
        if not ps:
            self.list.append(_dim(i18n.tr("Ingen dagbøker ennå – lag din egen.")))
        for p in ps:
            b = Gtk.Button()
            b.add_css_class("card")
            v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, margin_top=12, margin_bottom=12)
            e = Gtk.Label(label="📔")
            e.add_css_class("title-1")
            v.append(e)
            v.append(Gtk.Label(label=p["name"]))
            b.set_child(v)
            b.connect("clicked", lambda _b, pp=p: self._ask_pin(pp))
            self.list.append(b)

    def _pin_entry(self, ph):
        e = Gtk.PasswordEntry(placeholder_text=ph, show_peek_icon=True)
        e.set_input_purpose(Gtk.InputPurpose.PIN)
        return e

    def _ask_pin(self, p):
        dlg = Adw.AlertDialog(heading=f"📔 {p['name']}", body=i18n.tr("Skriv koden din"))
        e = self._pin_entry(i18n.tr("4–6 sifre"))
        e.set_activates_default(True)
        dlg.set_extra_child(e)
        dlg.add_response("cancel", i18n.tr("Avbryt"))
        dlg.add_response("ok", i18n.tr("Lås opp"))
        dlg.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response("ok")

        def resp(_d, r):
            if r != "ok":
                return
            pin = e.get_text()
            _bg(lambda: D.unlock(p["id"], pin), lambda tok: self._opened(tok, p))
        dlg.connect("response", resp)
        dlg.present(self.get_root())
        wait = D.locked_for(p["id"])
        if wait:
            dlg.set_body(i18n.tr("For mange feil – prøv igjen om") + f" {wait // 60 + 1} min")

    def _create(self):
        dlg = Adw.AlertDialog(heading=i18n.tr("Ny dagbok"),
                              body=i18n.tr("Velg en kode på 4–6 sifre som bare du kan. Den kan ikke hentes tilbake."))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        name = Gtk.Entry(placeholder_text=i18n.tr("Navnet ditt"))
        p1 = self._pin_entry(i18n.tr("Kode (4–6 sifre)"))
        p2 = self._pin_entry(i18n.tr("Kode en gang til"))
        for w in (name, p1, p2):
            box.append(w)
        dlg.set_extra_child(box)
        dlg.add_response("cancel", i18n.tr("Avbryt"))
        dlg.add_response("ok", i18n.tr("Lag dagboken"))
        dlg.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)

        def resp(_d, r):
            if r != "ok":
                return
            if p1.get_text() != p2.get_text():
                self._toast("Kodene er ikke like")
                return
            nm, pin = name.get_text(), p1.get_text()
            _bg(lambda: (D.create(nm, pin), nm), lambda res: isinstance(res, Exception) and self._toast(str(res)) or
                (not isinstance(res, Exception) and self._opened(res[0], {"id": D._SESS[res[0]]["pid"], "name": nm})))
        dlg.connect("response", resp)
        dlg.present(self.get_root())

    def _toast(self, t):
        root = self.get_root()
        if hasattr(root, "toast"):
            root.toast(t)
        else:
            dlg = Adw.AlertDialog(heading=t)
            dlg.add_response("ok", "OK")
            dlg.present(root)

    # ---- åpen dagbok
    def _opened(self, tok, p):
        if isinstance(tok, Exception):
            self._toast(f"✗ {tok}")
            return
        self.tok = tok
        self.person = p
        self._show_diary()

    def _show_diary(self):
        try:
            data = D.entries(self.tok)
        except PermissionError:
            self.tok = None
            self._show_people()
            return
        self._clear()
        top = Gtk.Box(spacing=8)
        t = Gtk.Label(label=f"📔 {data['name']}", xalign=0, hexpand=True)
        t.add_css_class("title-2")
        top.append(t)
        cp = Gtk.Button(label=i18n.tr("Bytt kode"))
        cp.add_css_class("flat")
        cp.connect("clicked", lambda *_: self._change_pin())
        top.append(cp)
        lk = Gtk.Button(label="🔒 " + i18n.tr("Lås"))
        lk.add_css_class("suggested-action")
        lk.connect("clicked", lambda *_: self.lock())
        top.append(lk)
        self.box.append(top)
        # skriv
        today = dt.date.today()
        self.box.append(Gtk.Label(label=f"{i18n.tr('I dag')} – {today.day}. {MONTHS[today.month - 1]} {today.year}",
                                  xalign=0, css_classes=["heading"]))
        moods = Gtk.Box(spacing=4)
        self.mood = {"v": ""}
        first = None
        for m in D.MOODS:
            b = Gtk.ToggleButton(label=m)
            b.add_css_class("flat")
            if first:
                b.set_group(first)
            first = first or b
            b.connect("toggled", lambda w, mm=m: w.get_active() and self.mood.update(v=mm))
            moods.append(b)
        self.box.append(moods)
        tv = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, top_margin=8, bottom_margin=8, left_margin=8,
                          right_margin=8)
        tv.add_css_class("ks-diary-text")
        tv.set_size_request(-1, 140)
        self.box.append(tv)
        save = Gtk.Button(label="💾 " + i18n.tr("Lagre innlegget"), halign=Gtk.Align.START)
        save.add_css_class("pill")
        save.add_css_class("suggested-action")

        def do_save(*_):
            b = tv.get_buffer()
            text = b.get_text(b.get_start_iter(), b.get_end_iter(), False)
            _bg(lambda: D.write(self.tok, text, self.mood["v"]), lambda r: (
                self._toast(f"✗ {r}") if isinstance(r, Exception) else self._show_diary()))
        save.connect("clicked", do_save)
        self.box.append(save)
        # tidligere innlegg
        es = list(reversed(data["entries"]))
        self.box.append(Gtk.Label(label=i18n.tr("Tidligere") + f" ({len(es)})", xalign=0, css_classes=["heading"],
                                  margin_top=8))
        if not es:
            self.box.append(_dim(i18n.tr("Ingen innlegg ennå.")))
        last_day = None
        for e in es[:200]:
            d = dt.date.fromisoformat(e["day"])
            if e["day"] != last_day:
                self.box.append(_dim(f"{d.day}. {MONTHS[d.month - 1]} {d.year}"))
                last_day = e["day"]
            row = Gtk.Box(spacing=8)
            row.add_css_class("card")
            lab = Gtk.Label(label=(e.get("mood") + " " if e.get("mood") else "") + e["text"], xalign=0, wrap=True,
                            selectable=True, hexpand=True, margin_top=8, margin_bottom=8, margin_start=10)
            row.append(lab)
            db = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.START, tooltip_text=i18n.tr("Slett"))
            db.add_css_class("flat")
            db.connect("clicked", lambda _b, eid=e["id"]: self._delete(eid))
            row.append(db)
            self.box.append(row)

    def _delete(self, eid):
        dlg = Adw.AlertDialog(heading=i18n.tr("Slette innlegget?"))
        dlg.add_response("no", i18n.tr("Avbryt"))
        dlg.add_response("yes", i18n.tr("Slett"))
        dlg.set_response_appearance("yes", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.connect("response", lambda _d, r: r == "yes" and _bg(lambda: D.delete_entry(self.tok, eid),
                                                                  lambda _r: self._show_diary()))
        dlg.present(self.get_root())

    def _change_pin(self):
        dlg = Adw.AlertDialog(heading=i18n.tr("Bytt kode"), body=i18n.tr("Ny kode på 4–6 sifre."))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        p1 = self._pin_entry(i18n.tr("Ny kode"))
        p2 = self._pin_entry(i18n.tr("Ny kode en gang til"))
        box.append(p1)
        box.append(p2)
        dlg.set_extra_child(box)
        dlg.add_response("cancel", i18n.tr("Avbryt"))
        dlg.add_response("ok", i18n.tr("Lagre"))
        dlg.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)

        def resp(_d, r):
            if r != "ok":
                return
            if p1.get_text() != p2.get_text():
                self._toast("Kodene er ikke like")
                return
            pin = p1.get_text()
            _bg(lambda: D.change_pin(self.tok, pin), lambda res: self._toast(str(res)))
        dlg.connect("response", resp)
        dlg.present(self.get_root())
