"""Kortet «Klipp» i Spill-fanen: opptak i bakgrunnen, lengde og «Lagre klipp nå (F8)»."""
import os
import subprocess
import sys
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk  # noqa: E402

import clips  # noqa: E402
import i18n  # noqa: E402

IS_WIN = sys.platform == "win32"


def _dim(t):
    lab = Gtk.Label(label=i18n.tr(t), xalign=0, wrap=True)
    lab.add_css_class("dim-label")
    lab.add_css_class("caption")
    return lab


def _open(path):
    if IS_WIN:
        os.startfile(path)
    else:
        subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class ClipsCard(Gtk.Box):
    def __init__(self, card_fn):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        how = ("Xbox Game Bar tar opp spillet i bakgrunnen" if IS_WIN else
               "GPU Screen Recorder tar opp skjermen i bakgrunnen med skjermkortets videokoder")
        c, i = card_fn(i18n.tr("Klipp"), i18n.tr(how) + ". " + i18n.tr("Trykk F8 – eller «Lagre klipp» i appen på "
                                                                        "mobilen – for å lagre de siste sekundene."))
        self.append(c)
        row = Gtk.Box(spacing=10)
        row.append(Gtk.Label(label=i18n.tr("Opptak i bakgrunnen"), xalign=0, hexpand=True))
        cfg = clips.load_cfg()
        self.sw = Gtk.Switch(active=cfg["enabled"], valign=Gtk.Align.CENTER)
        self.sw.connect("notify::active", self._on_switch)
        row.append(self.sw)
        i.append(row)
        if not IS_WIN:
            r2 = Gtk.Box(spacing=10)
            r2.append(Gtk.Label(label=i18n.tr("Lengde på klippet"), xalign=0, hexpand=True))
            names = [f"{s} s" if s < 60 else f"{s // 60} min" for s in clips.LENGTHS]
            self.dd = Gtk.DropDown.new_from_strings(names)
            self.dd.set_selected(clips.LENGTHS.index(cfg["length"]) if cfg["length"] in clips.LENGTHS else 2)
            self.dd.connect("notify::selected", lambda d, _p: clips.set_cfg(length=clips.LENGTHS[d.get_selected()]))
            r2.append(self.dd)
            i.append(r2)
            r3 = Gtk.Box(spacing=10)
            r3.append(Gtk.Label(label=i18n.tr("Bare mens et spill kjører"), xalign=0, hexpand=True))
            og = Gtk.Switch(active=cfg["only_games"], valign=Gtk.Align.CENTER)
            og.connect("notify::active", lambda s, _p: clips.set_cfg(only_games=s.get_active()))
            r3.append(og)
            i.append(r3)
        hk = Gtk.Box(spacing=8)
        hk.append(Gtk.Label(label=i18n.tr("Hurtigtast"), xalign=0, hexpand=True))
        self.key_lab = Gtk.Label(label=cfg.get("hotkey") or "F8")
        self.key_lab.add_css_class("heading")
        hk.append(self.key_lab)
        kb = Gtk.Button(label=i18n.tr("Velg tast"))
        kb.connect("clicked", self._choose_key)
        hk.append(kb)
        self.test_btn = Gtk.Button(label=i18n.tr("Test tasten"))
        self.test_btn.connect("clicked", self._test_key)
        hk.append(self.test_btn)
        i.append(hk)
        self.status = Gtk.Label(xalign=0, wrap=True)
        i.append(self.status)
        btns = Gtk.Box(spacing=8)
        self.save_btn = Gtk.Button(label=i18n.tr("Lagre klipp nå (F8)"))
        self.save_btn.add_css_class("suggested-action")
        self.save_btn.connect("clicked", self._save)
        btns.append(self.save_btn)
        ob = Gtk.Button(label=i18n.tr("Åpne mappen"))
        ob.connect("clicked", lambda *_: (os.makedirs(clips.clip_dir(), exist_ok=True), _open(clips.clip_dir())))
        btns.append(ob)
        if IS_WIN:
            wb = Gtk.Button(label=i18n.tr("Lengde og kvalitet (Windows)"))
            wb.connect("clicked", lambda *_: _open("ms-settings:gaming-gamedvr"))
            btns.append(wb)
        else:
            self.inst = Gtk.Button(label=i18n.tr("Installer GPU Screen Recorder"))
            self.inst.connect("clicked", self._install)
            btns.append(self.inst)
        i.append(btns)
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.list.add_css_class("boxed-list")
        i.append(self.list)
        self.refresh()
        GLib.timeout_add_seconds(5, lambda: (self.refresh() if self.get_mapped() else None, True)[1])

    def refresh(self):
        def work():
            st = clips.INSTANCE.state() if clips.INSTANCE else {**clips.load_cfg(), "installed": True}
            GLib.idle_add(self._show, st, clips.clips(6))
        threading.Thread(target=work, daemon=True).start()

    def _show(self, st, items):
        if not IS_WIN:
            self.inst.set_visible(not st.get("installed"))
        if not st.get("enabled"):
            txt = i18n.tr("Av")
        elif not IS_WIN and not st.get("installed"):
            txt = i18n.tr("GPU Screen Recorder må installeres først")
        elif st.get("running"):
            txt = "🔴 " + i18n.tr("Tar opp i bakgrunnen") + (f" · {st['length']} s" if not IS_WIN else "")
        else:
            txt = i18n.tr("Venter på et spill") if st.get("only_games") else i18n.tr("Starter …")
        if st.get("error"):
            txt += " · " + st["error"]
        if st.get("hotkey_error"):
            txt += " · " + st["hotkey_error"]
        elif st.get("enabled") and not st.get("hotkey_ok"):
            txt += " · " + i18n.tr("Hurtigtasten er ikke registrert ennå (godta snarveien hvis skrivebordet spør)")
        self.key_lab.set_label(st.get("hotkey") or "F8")
        self.status.set_label(txt)
        while (ch := self.list.get_first_child()):
            self.list.remove(ch)
        for c in items:
            r = Gtk.Box(spacing=10)
            for side, v in (("top", 6), ("bottom", 6), ("start", 12), ("end", 8)):
                getattr(r, f"set_margin_{side}")(v)
            r.append(Gtk.Label(label="🎬  " + c["name"], xalign=0, hexpand=True, ellipsize=3))
            r.append(_dim(f"{c['size'] / 2**20:.0f} MB · " + time.strftime("%d.%m %H:%M", time.localtime(c["t"]))))
            pb = Gtk.Button(icon_name="media-playback-start-symbolic", valign=Gtk.Align.CENTER)
            pb.add_css_class("flat")
            pb.connect("clicked", lambda _b, n=c["name"]: _open(os.path.join(clips.clip_dir(), n)))
            r.append(pb)
            self.list.append(r)
        self.list.set_visible(bool(items))
        return False

    # ---- velg tast: trykk kombinasjonen du vil bruke ----
    NAMES = {"Page_Up": "PageUp", "Page_Down": "PageDown", "Scroll_Lock": "ScrollLock", "space": "Space",
             "Print": "Print", "Insert": "Insert", "Delete": "Delete", "Home": "Home", "End": "End", "Pause": "Pause"}

    def _choose_key(self, *_):
        from gi.repository import Adw, Gdk
        dlg = Adw.Dialog(title=i18n.tr("Velg hurtigtast"), content_width=420, content_height=220)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(24)
        lab = Gtk.Label(label=i18n.tr("Trykk tasten eller kombinasjonen du vil bruke …\n(f.eks. F8, F9, Alt+F10 eller Ctrl+Shift+S)"),
                        justify=Gtk.Justification.CENTER, wrap=True)
        lab.add_css_class("title-4")
        box.append(lab)
        msg = Gtk.Label(wrap=True)
        msg.add_css_class("dim-label")
        box.append(msg)
        tv = Adw.ToolbarView()
        tv.add_top_bar(Adw.HeaderBar())
        tv.set_content(box)
        dlg.set_child(tv)
        ctl = Gtk.EventControllerKey()

        def key(_c, keyval, _code, state):
            name = Gdk.keyval_name(keyval) or ""
            if name in ("Control_L", "Control_R", "Shift_L", "Shift_R", "Alt_L", "Alt_R", "Super_L", "Super_R",
                        "Meta_L", "Meta_R", "ISO_Level3_Shift"):
                return False
            if name == "Escape":
                dlg.close()
                return True
            name = self.NAMES.get(name, name)
            if len(name) == 1:
                name = name.upper()
            mods = [m for m, mask in (("Ctrl", Gdk.ModifierType.CONTROL_MASK), ("Alt", Gdk.ModifierType.ALT_MASK),
                                      ("Shift", Gdk.ModifierType.SHIFT_MASK), ("Meta", Gdk.ModifierType.SUPER_MASK))
                    if state & mask]
            spec = "+".join(mods + [name])
            try:
                clips.set_hotkey(spec)
            except ValueError as e:
                msg.set_label(str(e))
                return True
            self.key_lab.set_label(spec)
            dlg.close()
            GLib.timeout_add(600, lambda: (self.refresh(), False)[1])
            return True
        ctl.connect("key-pressed", key)
        dlg.add_controller(ctl)
        dlg.present(self.get_root())

    def _test_key(self, *_):
        try:
            clips.test_hotkey(15)
        except Exception as e:  # noqa: BLE001
            self.status.set_label(str(e))
            return
        self.test_btn.set_sensitive(False)
        self.status.set_label(i18n.tr("Trykk hurtigtasten nå") + f" ({self.key_lab.get_label()}) …")
        t0 = time.time()

        def poll():
            r = clips.INSTANCE
            hk = r.hotkey if r else None
            if hk and hk.tested and hk.tested >= t0:
                self.status.set_label("✅ " + i18n.tr("Tasten virker! Den lagrer klipp når opptaket er på."))
                self.test_btn.set_sensitive(True)
                return False
            if time.time() - t0 > 15:
                self.status.set_label("❌ " + i18n.tr("Fikk ikke tastetrykket. Prøv en annen tast (noen taster brukes av "
                                                       "skrivebordet eller spillet)."))
                self.test_btn.set_sensitive(True)
                return False
            return True
        GLib.timeout_add(250, poll)

    def _on_switch(self, sw, _p):
        try:
            clips.set_cfg(enabled=sw.get_active())
        except Exception as e:  # noqa: BLE001
            self.status.set_label(str(e))
        self.refresh()

    def _save(self, *_):
        if not clips.INSTANCE:
            return
        ok, msg = clips.INSTANCE.save()
        self.status.set_label(i18n.tr(msg))
        GLib.timeout_add_seconds(4, lambda: (self.refresh(), False)[1])

    def _install(self, *_):
        self.inst.set_sensitive(False)
        self.status.set_label(i18n.tr("Installerer GPU Screen Recorder fra Flathub …"))

        def work():
            try:
                clips.install()
                msg = i18n.tr("GPU Screen Recorder er installert ✓")
            except Exception as e:  # noqa: BLE001
                msg = str(e)
            GLib.idle_add(lambda: (self.status.set_label(msg), self.inst.set_sensitive(True), self.refresh(), False)[3])
        threading.Thread(target=work, daemon=True).start()
