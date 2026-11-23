"""Fremdrift når programmene til funksjonene installeres eller fjernes: prosent, tid igjen og nedlastingshastighet."""
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

import i18n  # noqa: E402
import komponenter as K  # noqa: E402

ICON = {"venter": "⏳", "kjører": "▶️", "ferdig": "✅", "feilet": "❌", "avbrutt": "⏹"}
_RUNNING = {"r": None}


class ProgressDialog(Adw.Dialog):
    def __init__(self, todo, keep=()):
        inst = any(a == "install" for a, _c in todo)
        rem = any(a == "remove" for a, _c in todo)
        title = ("Installerer og fjerner programmer" if inst and rem else
                 "Installerer programmer" if inst else "Fjerner programmer")
        super().__init__(title=i18n.tr(title), content_width=560)
        tv = Adw.ToolbarView()
        tv.add_top_bar(Adw.HeaderBar())
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=8, margin_bottom=18,
                      margin_start=22, margin_end=22)
        h = Gtk.Label(label=i18n.tr(title), xalign=0)
        h.add_css_class("title-2")
        box.append(h)
        self.step = Gtk.Label(xalign=0, wrap=True)
        self.step.add_css_class("dim-label")
        box.append(self.step)
        self.bar = Gtk.ProgressBar(show_text=True)
        self.bar.set_size_request(-1, 18)
        box.append(self.bar)
        info = Gtk.Box(spacing=12)
        self.pct = Gtk.Label(xalign=0)
        self.pct.add_css_class("title-3")
        info.append(self.pct)
        self.eta = Gtk.Label(xalign=0, hexpand=True)
        info.append(self.eta)
        self.speed = Gtk.Label(xalign=1)
        self.speed.add_css_class("numeric")
        info.append(self.speed)
        box.append(info)
        self.rows = []
        lst = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        for a, c in todo:
            lab = Gtk.Label(xalign=0, ellipsize=3)
            lst.append(lab)
            self.rows.append(lab)
        for c in keep:
            k = Gtk.Label(label="•  " + c[1] + i18n.tr(" – beholdes (var installert fra før)"), xalign=0,
                          ellipsize=3)
            k.add_css_class("dim-label")
            lst.append(k)
        box.append(lst)
        self.err = Gtk.Label(xalign=0, wrap=True, visible=False)
        self.err.add_css_class("error")
        box.append(self.err)
        btns = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        self.bg_btn = Gtk.Button(label=i18n.tr("Kjør i bakgrunnen"))
        self.bg_btn.connect("clicked", lambda *_: self.close())
        btns.append(self.bg_btn)
        self.done_btn = Gtk.Button(label=i18n.tr("Ferdig"), visible=False)
        self.done_btn.add_css_class("suggested-action")
        self.done_btn.connect("clicked", lambda *_: self.close())
        btns.append(self.done_btn)
        box.append(btns)
        tv.set_content(box)
        self.set_child(tv)
        self._pending = None
        self._title = title
        self._bgtask = None
        self.connect("closed", self._to_background)
        self.runner = K.Runner(todo, self._changed)
        self._show(self.runner.state)
        _RUNNING["r"] = self.runner
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self):
        try:
            self.runner.run()
        finally:
            _RUNNING["r"] = None

    def _to_background(self, *_a):
        """Lukket mens det pågår: fortsett i fremdriftslinja øverst i Kontrollsenter."""
        if not self.runner.state["done"] and self._bgtask is None:
            import progress as P
            self._bgtask = P.begin(i18n.tr(self._title), i18n.tr(self.runner.state["step"]))

    def _changed(self, st):
        first = self._pending is None
        self._pending = st
        if first:
            GLib.timeout_add(150, self._flush)

    def _flush(self):
        st, self._pending = self._pending, None
        if st:
            self._show(st)
        return False

    def _show(self, st):
        if self._bgtask:
            if st["done"]:
                self._bgtask.done(i18n.tr("Ferdig") if not st["errors"] else st["errors"][-1][:120],
                                  ok=not st["errors"])
                self._bgtask = False
            else:
                self._bgtask.set(st["pct"] / 100, f"{st['pct']:.0f} % · {K.human_eta(st['eta'])} · "
                                                  f"{K.human_speed(st['speed'])}")
        self.bar.set_fraction(st["pct"] / 100)
        self.bar.set_text(f"{st['pct']:.0f} %")
        self.pct.set_label(f"{st['pct']:.0f} %")
        self.eta.set_label("" if st["done"] else K.human_eta(st["eta"]))
        self.speed.set_label("" if st["done"] else "⬇ " + K.human_speed(st["speed"]))
        self.step.set_label(i18n.tr(st["step"]))
        for lab, (name, status) in zip(self.rows, st["items"]):
            lab.set_label(f"{ICON.get(status, '')}  {name}")
        if st["errors"]:
            self.err.set_label("\n".join(st["errors"][-4:]))
            self.err.set_visible(True)
        if st["done"]:
            self.bg_btn.set_visible(False)
            self.done_btn.set_visible(True)
            if st.get("reboot"):
                self.step.set_label(i18n.tr("Ferdig – start PC-en på nytt for at systempakkene skal tas i bruk "
                                            "(Bazzite/Silverblue)"))


def run_for(win, enabled):
    """Finn ut hva funksjonene trenger, og vis fremdriften hvis noe skal installeres eller fjernes."""
    if _RUNNING["r"] is not None:
        return None

    def work():
        p = K.plan(enabled)
        GLib.idle_add(lambda: (show(p), False)[1])

    def show(p):
        todo = K.todo_for(p)
        new_keep = [c for c in p["keep"] if not K.asked(c[0]) and K.removable(c)]
        if not new_keep:
            if todo:
                ProgressDialog(todo, p["keep"]).present(win)
            return
        # programmer som fantes før Kontrollsenter: spør én gang om de skal fjernes også (ingen er krysset av)
        dlg = Adw.AlertDialog(heading=i18n.tr("Fjerne programmer du hadde fra før?"),
                              body=i18n.tr("Funksjonene som bruker disse er slått av, men programmene var installert "
                                           "før Kontrollsenter tok over. Kryss av for dem som skal fjernes."))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        checks = []
        for c in new_keep:
            cb = Gtk.CheckButton(label=c[1])
            box.append(cb)
            checks.append((cb, c))
        dlg.set_extra_child(box)
        dlg.add_response("behold", i18n.tr("Behold alle"))
        dlg.add_response("ok", i18n.tr("Fortsett"))
        dlg.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)

        def resp(_d, r):
            K.mark_asked([c[0] for c in new_keep])
            extra = [("remove", c) for cb, c in checks if r == "ok" and cb.get_active()]
            keep = [c for c in p["keep"] if not any(c is e[1] for e in extra)]
            if todo or extra:
                ProgressDialog(todo + extra, keep).present(win)
        dlg.connect("response", resp)
        dlg.present(win)
    threading.Thread(target=work, daemon=True).start()
    return True
