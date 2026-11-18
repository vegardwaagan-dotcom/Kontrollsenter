"""Siden «Scener»: store kort i scenens farge – trykk «Kjør», eller rediger hva scenen gjør og når."""
import copy
import math

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

import i18n  # noqa: E402
import scenes as S  # noqa: E402

CSS = """
.ks-scene { border-radius: 22px; }
.ks-scene.ks-scene-active { box-shadow: 0 0 0 2px #8a5cff, 0 18px 40px -16px alpha(#8a5cff, 0.9); }
.ks-scene-icon { font-size: 44px; }
.ks-scene-chip { font-size: 0.8em; font-weight: 700; padding: 3px 10px; border-radius: 99px;
  background-color: alpha(currentColor, 0.10); }
.ks-scene-chip.on { background-image: linear-gradient(135deg, #5b8cff, #8a5cff); color: white; }
button.ks-scene-run, window.ks-glass button.ks-scene-run { border-radius: 99px; padding: 6px 18px; font-weight: 800;
  color: white; background-color: transparent; background-image: linear-gradient(135deg, #5b8cff, #8a5cff);
  box-shadow: 0 10px 22px -10px alpha(#8a5cff, 0.9); }
button.ks-scene-run:hover { box-shadow: 0 12px 28px -8px alpha(#8a5cff, 1); }
"""
_css = [False]


def _hex(c):
    c = (c or "#8a5cff").lstrip("#")
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _rgba_hex(rgba):
    return "#%02x%02x%02x" % (round(rgba.red * 255), round(rgba.green * 255), round(rgba.blue * 255))


def _color_btn(hexc):
    b = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False), valign=Gtk.Align.CENTER)
    c = Gdk.RGBA()
    c.parse(hexc or "#8a5cff")
    b.set_rgba(c)
    return b


class ScenesPage(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        if not _css[0]:
            _css[0] = True
            import theme
            theme.add_css(CSS, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 5)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(14)
        self.set_child(box)
        top = Gtk.Box(spacing=12)
        top.append(Gtk.Box(hexpand=True))
        add = Gtk.Button(label=i18n.tr("Ny scene"), valign=Gtk.Align.CENTER)
        add.add_css_class("suggested-action")
        add.connect("clicked", lambda *_: self.edit(None))
        top.append(add)
        box.append(top)
        self.flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True, max_children_per_line=3,
                                min_children_per_line=1, column_spacing=14, row_spacing=14)
        box.append(self.flow)
        S.listen(lambda _sid: self.render())
        self.render()

    # ---- kortene ----
    def render(self):
        while (c := self.flow.get_first_child()) is not None:
            self.flow.remove(c)
        d = S.load()
        for s in d["scenes"]:
            self.flow.append(self._card(s, s["id"] == d.get("active")))
        try:
            import sortbox
            sortbox.scan(self, "scener")
        except Exception:  # noqa: BLE001
            pass
        return False

    def _card(self, s, active):
        c = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        c.add_css_class("card")
        c.add_css_class("ks-scene")
        if active:
            c.add_css_class("ks-scene-active")
        ov = Gtk.Overlay()
        da = Gtk.DrawingArea(content_height=118, hexpand=True)
        da.set_draw_func(self._draw_banner, s.get("color"))
        ov.set_child(da)
        ic = Gtk.Label(label=s.get("icon") or "✨", halign=Gtk.Align.START, valign=Gtk.Align.CENTER, margin_start=20)
        ic.add_css_class("ks-scene-icon")
        ov.add_overlay(ic)
        if active:
            chip = Gtk.Label(label=i18n.tr("Aktiv nå"), halign=Gtk.Align.END, valign=Gtk.Align.START,
                             margin_end=12, margin_top=12)
            chip.add_css_class("ks-scene-chip")
            chip.add_css_class("on")
            ov.add_overlay(chip)
        c.append(ov)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for side, v in (("top", 12), ("bottom", 14), ("start", 16), ("end", 16)):
            getattr(inner, f"set_margin_{side}")(v)
        t = Gtk.Label(label=s["name"], xalign=0, ellipsize=3, max_width_chars=20)
        t.add_css_class("title-3")
        t.add_css_class("heading")
        inner.append(t)
        sm = Gtk.Label(label=i18n.tr(S.summary(s)), xalign=0, wrap=True, lines=3, ellipsize=3, max_width_chars=28,
                       width_chars=20)
        sm.add_css_class("dim-label")
        sm.add_css_class("caption")
        inner.append(sm)
        auto = (s.get("trigger") or {}).get("auto") and (s.get("trigger") or {}).get("type") != "manual"
        tr = Gtk.Label(label=("⚡ " if auto else "") + i18n.tr(S.trigger_text(s)), xalign=0, halign=Gtk.Align.START,
                       ellipsize=3, max_width_chars=26)
        tr.add_css_class("ks-scene-chip")
        if auto:
            tr.add_css_class("on")
        inner.append(tr)
        row = Gtk.Box(spacing=8, margin_top=6)
        run = Gtk.Button(label=i18n.tr("Kjør"), hexpand=True)
        run.add_css_class("ks-scene-run")
        run.connect("clicked", lambda b, sid=s["id"]: self.run(b, c, sid))
        row.append(run)
        ed = Gtk.Button(icon_name="document-edit-symbolic", tooltip_text=i18n.tr("Rediger"))
        ed.add_css_class("circular")
        ed.connect("clicked", lambda *_, sid=s["id"]: self.edit(sid))
        row.append(ed)
        inner.append(row)
        c.append(inner)
        return c

    @staticmethod
    def _draw_banner(_a, cr, w, h, color):
        import cairo
        r = 22
        cr.new_sub_path()
        cr.arc(w - r, r, r, -math.pi / 2, 0)
        cr.line_to(w, h)
        cr.line_to(0, h)
        cr.arc(r, r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()
        cr.clip()
        cr.set_source_rgb(0.07, 0.07, 0.10)
        cr.paint()
        rgb = _hex(color)
        for cx, cy, rad, a in ((w * .15, -h * .1, w * .75, .95), (w * .95, h * .2, w * .55, .65),
                               (w * .55, h * 1.2, w * .6, .45)):
            g = cairo.RadialGradient(cx, cy, 0, cx, cy, rad)
            g.add_color_stop_rgba(0, *rgb, a)
            g.add_color_stop_rgba(1, *rgb, 0)
            cr.set_source(g)
            cr.paint()
        g = cairo.LinearGradient(0, h * .55, 0, h)
        g.add_color_stop_rgba(0, 0, 0, 0, 0)
        g.add_color_stop_rgba(1, 0, 0, 0, .25)
        cr.set_source(g)
        cr.paint()

    def run(self, btn, card, sid):
        btn.set_sensitive(False)
        btn.set_label(i18n.tr("Setter …"))
        card.add_css_class("ks-sort-dropped")
        GLib.timeout_add(600, lambda: card.remove_css_class("ks-sort-dropped") or False)
        win = self.get_root()

        def done(name, ok, n, errs):
            if win and hasattr(win, "toast"):
                win.toast(f"«{name}» er satt ✓" if not errs else f"«{name}»: {ok} av {n} – " + errs[0])
        try:
            S.run(win, sid, done=done)
        except Exception as e:  # noqa: BLE001
            if win and hasattr(win, "toast"):
                win.toast(str(e))
            btn.set_sensitive(True)
            btn.set_label(i18n.tr("Kjør"))

    # ---- redigering ----
    def edit(self, sid):
        s = copy.deepcopy(S.get(sid)) if sid else {
            "id": None, "name": i18n.tr("Ny scene"), "icon": "✨", "color": "#8a5cff", "power": None, "fans": None,
            "rgb": None, "hue": None, "tv": None, "volume": None, "mute": None, "theme": None, "quiet": None,
            "trigger": {"type": "manual", "auto": False, "at": "20:00"}}
        SceneEditor(self, s).present(self.get_root())


def _combo(title, items, cur, sub=None):
    names = Gtk.StringList.new([i18n.tr(t) for _k, t in items])
    row = Adw.ComboRow(title=i18n.tr(title), model=names)
    if sub:
        row.set_subtitle(i18n.tr(sub))
    keys = [k for k, _t in items]
    row.set_selected(keys.index(cur) if cur in keys else 0)
    row.keys = keys
    return row


class SceneEditor(Adw.Dialog):
    def __init__(self, page, s):
        super().__init__(title=i18n.tr("Rediger scene") if s["id"] else i18n.tr("Ny scene"),
                         content_width=560, content_height=760)
        self.page, self.s = page, s
        tv = Adw.ToolbarView()
        hb = Adw.HeaderBar(show_end_title_buttons=False, show_start_title_buttons=False)
        cancel = Gtk.Button(label=i18n.tr("Avbryt"))
        cancel.connect("clicked", lambda *_: self.close())
        hb.pack_start(cancel)
        save = Gtk.Button(label=i18n.tr("Lagre"))
        save.add_css_class("suggested-action")
        save.connect("clicked", self._save)
        hb.pack_end(save)
        tv.add_top_bar(hb)
        pp = Adw.PreferencesPage()
        tv.set_content(pp)
        self.set_child(tv)

        g = Adw.PreferencesGroup(title=i18n.tr("Scene"))
        self.name = Adw.EntryRow(title=i18n.tr("Navn"), text=s["name"])
        g.add(self.name)
        self.icon = Adw.EntryRow(title=i18n.tr("Ikon (emoji)"), text=s.get("icon") or "✨")
        g.add(self.icon)
        cr = Adw.ActionRow(title=i18n.tr("Farge på kortet"))
        self.color = _color_btn(s.get("color"))
        cr.add_suffix(self.color)
        g.add(cr)
        pp.add(g)

        import theme
        g = Adw.PreferencesGroup(title=i18n.tr("PC-en"))
        self.power = _combo("Strømmodus", S.POWER, s.get("power"))
        g.add(self.power)
        self.fans = _combo("Vifter", S.FANS, s.get("fans"))
        g.add(self.fans)
        rgbv = s.get("rgb")
        self.rgb = _combo("RGB-lys", [(None, "Ikke endre"), ("off", "Av"), ("color", "Farge")],
                          None if rgbv is None else "off" if rgbv == "off" else "color")
        self.rgb_col = _color_btn(rgbv if rgbv not in (None, "off") else s.get("color"))
        self.rgb.add_suffix(self.rgb_col)
        g.add(self.rgb)
        self.theme = _combo("Tema", [(None, "Ikke endre")] + [(k, t["name"]) for k, t in theme.THEMES.items()],
                            s.get("theme"))
        g.add(self.theme)
        self.quiet = _combo("Varsler", S.QUIET, s.get("quiet"))
        g.add(self.quiet)
        pp.add(g)

        g = Adw.PreferencesGroup(title=i18n.tr("Rommet"), description=i18n.tr("Philips Hue og Samsung-TV fra Smart Hjem."))
        h = s.get("hue")
        self.hue = _combo("Hue-lys", [(None, "Ikke endre"), ("off", "Av"), ("on", "På")],
                          None if h is None else ("on" if h.get("on") else "off"))
        self.hue_col = _color_btn((h or {}).get("color") or "#ffc58a")
        self.hue.add_suffix(self.hue_col)
        g.add(self.hue)
        self.bri = Adw.SpinRow.new_with_range(1, 100, 1)
        self.bri.set_title(i18n.tr("Lysstyrke (%)"))
        self.bri.set_value((h or {}).get("bri", 70))
        g.add(self.bri)
        self.tv = _combo("TV", S.TV, s.get("tv"))
        g.add(self.tv)
        pp.add(g)

        g = Adw.PreferencesGroup(title=i18n.tr("Lyd"))
        lyd = None if s.get("mute") is None and s.get("volume") is None else ("mute" if s.get("mute") else "vol")
        self.sound = _combo("Lyd", [(None, "Ikke endre"), ("mute", "Demp"), ("vol", "Sett volum")], lyd)
        g.add(self.sound)
        self.vol = Adw.SpinRow.new_with_range(0, 100, 5)
        self.vol.set_title(i18n.tr("Volum (%)"))
        self.vol.set_value(s.get("volume") if s.get("volume") is not None else 40)
        g.add(self.vol)
        import avprofiles as AP
        apc = AP.cfg()
        self.aprof = _combo("Lydprofil", [(None, "Ikke endre")] + [(p["id"], p["name"]) for p in apc["audio"]],
                            s.get("audio_profile"))
        g.add(self.aprof)
        pp.add(g)

        g = Adw.PreferencesGroup(title=i18n.tr("Skjermen"),
                                 description=i18n.tr("Skjermprofiler lages under GPU-innstillinger."))
        self.dprof = _combo("Skjermprofil", [(None, "Ikke endre")] + [(p["id"], p["name"]) for p in apc["display"]],
                            s.get("display_profile"))
        g.add(self.dprof)
        self.night = _combo("Nattlys", [(None, "Ikke endre"), (True, "På"), (False, "Av")], s.get("night"))
        g.add(self.night)
        bri = s.get("brightness")
        self.sbri_on = _combo("Lysstyrke på skjermen", [(None, "Ikke endre"), ("set", "Sett")],
                              None if bri is None else "set")
        g.add(self.sbri_on)
        self.sbri = Adw.SpinRow.new_with_range(1, 100, 5)
        self.sbri.set_title(i18n.tr("Lysstyrke (%)"))
        self.sbri.set_value(bri if bri is not None else 60)
        g.add(self.sbri)
        pp.add(g)

        t = s.get("trigger") or {}
        g = Adw.PreferencesGroup(title=i18n.tr("Automatisk"))
        self.trig = _combo("Når", S.TRIGGERS, t.get("type", "manual"))
        g.add(self.trig)
        self.at = Adw.EntryRow(title=i18n.tr("Klokkeslett (TT:MM)"), text=t.get("at", "20:00"))
        g.add(self.at)
        self.auto = Adw.SwitchRow(title=i18n.tr("Slå på automatikken"), active=bool(t.get("auto")),
                                  subtitle=i18n.tr("Av: scenen kjører bare når du trykker «Kjør»."))
        g.add(self.auto)
        pp.add(g)

        g = Adw.PreferencesGroup()
        row = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER, margin_top=6)
        test = Gtk.Button(label=i18n.tr("Lagre og prøv nå"))
        test.add_css_class("pill")
        test.connect("clicked", lambda *_: self._save(None, run=True))
        row.append(test)
        if s["id"]:
            dl = Gtk.Button(label=i18n.tr("Slett scenen"))
            dl.add_css_class("destructive-action")
            dl.add_css_class("pill")
            dl.connect("clicked", self._delete)
            row.append(dl)
        g.add(row)
        pp.add(g)
        for w, fn in ((self.hue, self._sync), (self.sound, self._sync), (self.trig, self._sync), (self.rgb, self._sync),
                      (self.sbri_on, self._sync)):
            w.connect("notify::selected", fn)
        self._sync()

    @staticmethod
    def _val(row):
        return row.keys[row.get_selected()]

    def _sync(self, *_):
        self.hue_col.set_visible(self._val(self.hue) == "on")
        self.bri.set_visible(self._val(self.hue) == "on")
        self.vol.set_visible(self._val(self.sound) == "vol")
        self.at.set_visible(self._val(self.trig) == "time")
        self.auto.set_visible(self._val(self.trig) != "manual")
        self.rgb_col.set_visible(self._val(self.rgb) == "color")
        self.sbri.set_visible(self._val(self.sbri_on) == "set")

    def _save(self, _b, run=False):
        s = self.s
        s["name"] = self.name.get_text().strip() or i18n.tr("Scene")
        s["icon"] = (self.icon.get_text().strip() or "✨")[:4]
        s["color"] = _rgba_hex(self.color.get_rgba())
        s["power"] = self._val(self.power)
        s["fans"] = self._val(self.fans)
        rv = self._val(self.rgb)
        s["rgb"] = None if rv is None else "off" if rv == "off" else _rgba_hex(self.rgb_col.get_rgba())
        s["theme"] = self._val(self.theme)
        s["quiet"] = self._val(self.quiet)
        hv = self._val(self.hue)
        s["hue"] = None if hv is None else {"on": False} if hv == "off" else \
            {"on": True, "bri": int(self.bri.get_value()), "color": _rgba_hex(self.hue_col.get_rgba())}
        s["tv"] = self._val(self.tv)
        sv = self._val(self.sound)
        s["mute"] = True if sv == "mute" else (False if sv == "vol" else None)
        s["volume"] = int(self.vol.get_value()) if sv == "vol" else None
        s["audio_profile"] = self._val(self.aprof)
        s["display_profile"] = self._val(self.dprof)
        s["night"] = self._val(self.night)
        s["brightness"] = int(self.sbri.get_value()) if self._val(self.sbri_on) == "set" else None
        at = self.at.get_text().strip()
        if self._val(self.trig) == "time":
            try:
                hh, mm = (int(x) for x in at.split(":"))
                at = f"{hh:02d}:{mm:02d}" if 0 <= hh < 24 and 0 <= mm < 60 else "20:00"
            except ValueError:
                at = "20:00"
        s["trigger"] = {"type": self._val(self.trig), "auto": self.auto.get_active(), "at": at}
        if not s["id"]:
            s["id"] = S.new_id(s["name"])
        S.put(s)
        self.page.render()
        self.close()
        if run:
            win = self.page.get_root()
            S.run(win, s["id"], done=lambda name, ok, n, errs: win.toast(
                f"«{name}» er satt ✓" if not errs else f"«{name}»: {ok} av {n} – " + errs[0]))

    def _delete(self, _b):
        S.delete(self.s["id"])
        self.page.render()
        self.close()
