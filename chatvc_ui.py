"""Talekanaler i chatten: talelinjen (demp, lyd av, kamera, innstillinger, legg på), videorutene og innstillingene
for mikrofon, høyttaler og kamera."""
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

import chatvc as VC  # noqa: E402
import i18n  # noqa: E402

CSS = """
.ks-vcbar { background: alpha(@window_fg_color, 0.06); border-radius: 12px; padding: 8px; }
.ks-vcbar button { min-width: 36px; min-height: 34px; padding: 0 6px; font-size: 1.05em; }
.ks-vcbar button.ks-off { background: alpha(#e5484d, 0.35); }
.ks-vcbar button.ks-cam-on { background: alpha(#3ad16b, 0.35); }
.ks-vc-ok { color: #3ad16b; font-weight: 700; }
.ks-vc-user { font-size: .93em; margin-left: 22px; }
.ks-vc-user.speaking { color: #3ad16b; font-weight: 800; }
.ks-vtile { border-radius: 12px; background: #000; }
.ks-vtile-name { background: alpha(#000, 0.55); color: #fff; border-radius: 8px; padding: 2px 8px; margin: 6px;
  font-size: .85em; }
.ks-vtile-wrap.speaking { box-shadow: 0 0 0 3px #3ad16b; border-radius: 12px; }
"""


def _texture(fr):
    data, w, h, stride = fr[:4]
    return Gdk.MemoryTexture.new(w, h, Gdk.MemoryFormat.R8G8B8A8, GLib.Bytes.new(data), stride)


def _status(err_or_text, lab):
    lab.set_label(("✗ " if isinstance(err_or_text, Exception) else "") + str(err_or_text))


def _bg(fn, done):
    def work():
        try:
            r = fn()
        except Exception as e:  # noqa: BLE001
            r = e
        GLib.idle_add(lambda: (done(r), False)[1])
    threading.Thread(target=work, daemon=True).start()


# --------------------------------------------------------------------------
# Talelinjen nederst i kanallista (som i Discord)
# --------------------------------------------------------------------------
class VoiceBar(Gtk.Box):
    def __init__(self, status_label, open_settings):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6, visible=False)
        self.add_css_class("ks-vcbar")
        self.status = status_label
        self.lab = Gtk.Label(xalign=0, ellipsize=3)
        self.lab.add_css_class("ks-vc-ok")
        self.append(self.lab)
        self.sub = Gtk.Label(xalign=0, ellipsize=3)
        self.sub.add_css_class("dim-label")
        self.sub.add_css_class("caption")
        self.append(self.sub)
        row = Gtk.Box(spacing=4, homogeneous=True)
        self.b_mute = self._b(row, "🎙️", "Demp mikrofonen", VC.toggle_mute)
        self.b_deaf = self._b(row, "🎧", "Slå av lyden (du hører ingen og blir dempet)", VC.toggle_deaf)
        self.b_cam = self._b(row, "📷", "Webkamera av/på", VC.toggle_camera)
        self.b_ov = Gtk.MenuButton(label="🖼️", tooltip_text=i18n.tr("Webkamera-overlay i spill"))
        self.b_ov.set_popover(overlay_popover(lambda: self.refresh()))
        row.append(self.b_ov)
        s = Gtk.Button(label="🎛️", tooltip_text=i18n.tr("Lyd og video"))
        s.connect("clicked", lambda *_: open_settings())
        row.append(s)
        self._b(row, "📞", "Forlat talekanalen", VC.leave).add_css_class("ks-off")
        self.append(row)
        VC.on_change(lambda what: what in ("roster", "error") and self.refresh())
        self.refresh()

    def _b(self, row, label, tip, fn):
        b = Gtk.Button(label=label, tooltip_text=i18n.tr(tip))
        b.connect("clicked", lambda *_: _bg(fn, lambda r: (isinstance(r, Exception) and _status(r, self.status),
                                                           self.refresh())))
        row.append(b)
        return b

    def refresh(self):
        st = VC.state()
        self.set_visible(st["in"])
        if not st["in"]:
            return False
        import chatsrv
        srv = chatsrv.get(st["sid"]) or {}
        ch = chatsrv.channel(srv, st["ch"]) or {}
        err = VC._S.get("error")
        self.lab.set_label(("⚠️ " + err) if err else i18n.tr("🔊 Tilkoblet til tale"))
        self.sub.set_label(f"{ch.get('name', '?')} / {srv.get('name', '?')}")
        for b, on, txt in ((self.b_mute, st["mute"], ("🔇", "🎙️")), (self.b_deaf, st["deaf"], ("🔕", "🎧"))):
            b.set_label(txt[0] if on else txt[1])
            (b.add_css_class if on else b.remove_css_class)("ks-off")
        (self.b_cam.add_css_class if st["cam"] else self.b_cam.remove_css_class)("ks-cam-on")
        (self.b_ov.add_css_class if VC.ov_cfg()["on"] else self.b_ov.remove_css_class)("ks-cam-on")
        return False


# --------------------------------------------------------------------------
# Webkamera-overlay i spill: av/på, hvem som vises, hjørne og størrelse
# --------------------------------------------------------------------------
def _seg(box, items, current, on_pick):
    row = Gtk.Box(homogeneous=True)
    row.add_css_class("linked")
    first = None
    for key, label in items:
        b = Gtk.ToggleButton(label=i18n.tr(label), active=key == current)
        if first:
            b.set_group(first)
        first = first or b
        b.connect("toggled", lambda btn, k=key: btn.get_active() and on_pick(k))
        row.append(b)
    box.append(row)


def overlay_controls(changed=None):
    """Kontrollene for overlayet (brukes i talelinjen og under Lyd og video)."""
    c = VC.ov_cfg()
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    sup = VC.ov_supported()
    top = Gtk.Box(spacing=12)
    col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
    t = Gtk.Label(label=i18n.tr("Webkamera-overlay i spill"), xalign=0)
    t.add_css_class("heading")
    col.append(t)
    sub = Gtk.Label(xalign=0, wrap=True, max_width_chars=36)
    sub.add_css_class("dim-label")
    sub.add_css_class("caption")
    sub.set_label(i18n.tr("Ligger over spillet (også fullskjerm) – klikk går rett gjennom" if sup == "layer-shell" else
                          "Ligger øverst over vinduer – spill i «uten ramme»-modus" if sup == "vindu" else
                          "Virker foreløpig bare på Linux"))
    col.append(sub)
    top.append(col)
    sw = Gtk.Switch(active=c["on"], valign=Gtk.Align.CENTER, sensitive=bool(sup))
    sw.connect("notify::active", lambda w, _p: (VC.ov_set(on=w.get_active()), changed and changed()))
    top.append(sw)
    box.append(top)
    box.append(Gtk.Label(label=i18n.tr("Vis"), xalign=0))
    _seg(box, [("me", "Bare meg"), ("peer", "Bare motparten"), ("both", "Begge")], c["show"],
         lambda k: VC.ov_set(show=k))
    box.append(Gtk.Label(label=i18n.tr("Hjørne"), xalign=0))
    _seg(box, [("top-left", "↖"), ("top-right", "↗"), ("bottom-left", "↙"), ("bottom-right", "↘")], c["corner"],
         lambda k: VC.ov_set(corner=k))
    box.append(Gtk.Label(label=i18n.tr("Størrelse"), xalign=0))
    _seg(box, [("liten", "Liten"), ("middels", "Middels"), ("stor", "Stor")], c["size"],
         lambda k: VC.ov_set(size=k))
    op = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 20, 100, 5)
    op.set_value(c["opacity"])
    op.set_format_value_func(lambda _s, v: f"{v:.0f} % synlig")
    op.connect("value-changed", lambda sc: VC.ov_set(opacity=int(sc.get_value())))
    box.append(op)
    return box


def overlay_popover(changed=None):
    pop = Gtk.Popover()
    box = overlay_controls(changed)
    for side in ("top", "bottom", "start", "end"):
        getattr(box, f"set_margin_{side}")(12)
    box.set_size_request(320, -1)
    pop.set_child(box)
    return pop


# --------------------------------------------------------------------------
# Videorutene over meldingene
# --------------------------------------------------------------------------
class VideoGrid(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, visible=False)
        self.flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=4, min_children_per_line=1,
                                homogeneous=False, column_spacing=8, row_spacing=8, halign=Gtk.Align.CENTER)
        self.append(self.flow)
        self.tiles = {}                     # mid -> (wrap, picture, label)
        self.big = None
        self._pending = False
        VC.on_change(self._changed)

    def _changed(self, what):
        if what in ("video", "speak", "roster") and not self._pending:
            self._pending = True
            GLib.timeout_add(60, self._update)

    def _tile(self, mid, name):
        pic = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN, can_shrink=True, hexpand=False, vexpand=False)
        pic.add_css_class("ks-vtile")
        pic.set_size_request(320, 180)
        clamp = Adw.Clamp(child=pic, maximum_size=360, tightening_threshold=360)
        ov = Gtk.Overlay(child=clamp, halign=Gtk.Align.CENTER, valign=Gtk.Align.START)
        ov._clamp = clamp
        lab = Gtk.Label(label=name, halign=Gtk.Align.START, valign=Gtk.Align.END)
        lab.add_css_class("ks-vtile-name")
        ov.add_overlay(lab)
        ov.add_css_class("ks-vtile-wrap")
        g = Gtk.GestureClick()
        g.connect("released", lambda *_a, m=mid: self._toggle_big(m))
        ov.add_controller(g)
        ov.set_tooltip_text(i18n.tr("Klikk for større bilde"))
        self.flow.append(ov)
        self.tiles[mid] = (ov, pic, lab)

    def _toggle_big(self, mid):
        self.big = None if self.big == mid else mid
        for m, (ov, pic, _l) in self.tiles.items():
            big = m == self.big
            ov._clamp.set_maximum_size(720 if big else 360)
            ov._clamp.set_tightening_threshold(720 if big else 360)
            pic.set_size_request(*((640, 360) if big else (320, 180)))

    def _update(self):
        self._pending = False
        cur = VC.current()
        frames = VC.frames() if cur else {}
        people = {p["id"]: p for p in VC.roster(*cur)} if cur else {}
        live = {m for m in frames if m in people and (people[m]["cam"] or m == "me")}
        for mid in [m for m in self.tiles if m not in live]:
            wrap = self.tiles.pop(mid)[0]
            self.flow.remove(wrap.get_parent() or wrap)
        for mid in sorted(live, key=lambda m: m != "me"):
            if mid not in self.tiles:
                p = people.get(mid, {})
                self._tile(mid, (p.get("name") or "?") + (i18n.tr(" (deg)") if mid == "me" else ""))
            wrap, pic, _lab = self.tiles[mid]
            try:
                pic.set_paintable(_texture(frames[mid]))
            except (TypeError, ValueError, GLib.Error):
                pass
            (wrap.add_css_class if people.get(mid, {}).get("speaking") else wrap.remove_css_class)("speaking")
        self.set_visible(bool(self.tiles))
        return False


# --------------------------------------------------------------------------
# Lyd og video – innstillinger
# --------------------------------------------------------------------------
def _combo(title, sub, items, current, on_pick):
    row = Adw.ComboRow(title=i18n.tr(title), subtitle=i18n.tr(sub) if sub else "")
    model = Gtk.StringList.new([n for _i, n in items])
    row.set_model(model)
    ids = [i for i, _n in items]
    row.set_selected(ids.index(current) if current in ids else 0)
    row.connect("notify::selected", lambda r, _p: on_pick(ids[r.get_selected()]) if r.get_selected() < len(ids)
                else None)
    return row


def _scale_row(title, sub, lo, hi, val, on_change, fmt="{:.0f} %"):
    row = Adw.ActionRow(title=i18n.tr(title), subtitle=i18n.tr(sub) if sub else "")
    sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, 1)
    sc.set_value(val)
    sc.set_hexpand(True)
    sc.set_size_request(220, -1)
    sc.set_draw_value(True)
    sc.set_format_value_func(lambda _s, v: fmt.format(v))
    sc.connect("value-changed", lambda s: on_change(s.get_value()))
    row.add_suffix(sc)
    return row


def _switch_row(title, sub, active, on_change):
    row = Adw.SwitchRow(title=i18n.tr(title), subtitle=i18n.tr(sub) if sub else "", active=bool(active))
    row.connect("notify::active", lambda r, _p: on_change(r.get_active()))
    return row


def open_settings(parent):
    """Mikrofon, høyttaler og kamera – med lydmåler, «hør deg selv» og forhåndsvisning av kameraet."""
    c = VC.cfg()
    dev = VC.devices()
    dlg = Adw.PreferencesDialog(title=i18n.tr("Lyd og video"))
    dlg.set_content_width(620)
    page = Adw.PreferencesPage(title=i18n.tr("Lyd og video"), icon_name="audio-input-microphone-symbolic")
    dlg.add(page)
    ok = VC.gst_ok()
    if not ok:
        g0 = Adw.PreferencesGroup(description=i18n.tr(VC.why_not()))
        page.add(g0)

    # --- mikrofon
    g = Adw.PreferencesGroup(title=i18n.tr("Mikrofon"))
    page.add(g)
    g.add(_combo("Mikrofon", "", dev["mic"], c["mic"], lambda v: (VC.set_(mic=v), restart_test())))
    g.add(_scale_row("Mikrofonvolum", "", 0, 200, c["mic_vol"], lambda v: VC.set_(mic_vol=int(v))))
    meter_row = Adw.ActionRow(title=i18n.tr("Lydnivå"), subtitle=i18n.tr("Snakk – stolpen skal gå godt over midten"))
    meter = Gtk.LevelBar(min_value=0, max_value=1, hexpand=True, valign=Gtk.Align.CENTER)
    meter.set_size_request(220, 10)
    meter_row.add_suffix(meter)
    g.add(meter_row)
    hear = _switch_row("Hør deg selv", "Mikrofonen spilles av i høyttaleren mens dette vinduet er åpent – bruk "
                                       "hodetelefoner", False, lambda _v: restart_test())
    g.add(hear)

    # --- lydbehandling
    g2 = Adw.PreferencesGroup(title=i18n.tr("Lydbehandling"))
    page.add(g2)
    g2.add(_switch_row("Støyreduksjon", "Fjerner vifte- og tastaturstøy",
                       c["noise"], lambda v: VC.set_(noise=v)))
    g2.add(_switch_row("Automatisk forsterkning", "Jevner ut stemmen når du snakker lavt eller høyt", c["agc"],
                       lambda v: VC.set_(agc=v)))
    g2.add(_switch_row("Stemmeaktivering", "Mikrofonen sender bare når lyden er over terskelen under", c["vad"],
                       lambda v: VC.set_(vad=v)))
    g2.add(_scale_row("Terskel for stemmeaktivering", "Lavere = mer følsom", -70, -20, c["vad_level"],
                      lambda v: VC.set_(vad_level=int(v)), "{:.0f} dB"))

    # --- høyttaler
    g3 = Adw.PreferencesGroup(title=i18n.tr("Høyttaler / hodetelefoner"))
    page.add(g3)
    g3.add(_combo("Lyd ut", "", dev["speaker"], c["speaker"],
                  lambda v: (VC.set_(speaker=v), restart_test())))
    g3.add(_scale_row("Volum på de andre", "", 0, 200, c["out_vol"], lambda v: VC.set_(out_vol=int(v))))
    tb = Adw.ActionRow(title=i18n.tr("Testlyd"), subtitle=i18n.tr("Spiller en kort tone i valgt høyttaler"))
    tbtn = Gtk.Button(label=i18n.tr("Spill av"), valign=Gtk.Align.CENTER)
    tbtn.connect("clicked", lambda *_: VC.play_test())
    tb.add_suffix(tbtn)
    g3.add(tb)

    # --- kamera
    g4 = Adw.PreferencesGroup(title=i18n.tr("Webkamera"))
    page.add(g4)
    g4.add(_combo("Kamera", "" if len(dev["camera"]) > 1 else "Fant ikke noe kamera", dev["camera"], c["camera"],
                  lambda v: (VC.set_(camera=v), restart_cam(), info())))
    q_items = [(k, v[2]) for k, v in VC.QUALITY.items()]
    cur_q = VC._OLD_Q.get(c["quality"], c["quality"])
    g4.add(_combo("Oppløsning", "", q_items, cur_q, lambda v: (VC.set_(quality=v), restart_cam(), info())))
    g4.add(_combo("Bilder per sekund", "", [(f, f"{f} bilder/s") for f in VC.FPS_CHOICES],
                  c["fps"] if c["fps"] in VC.FPS_CHOICES else 30,
                  lambda v: (VC.set_(fps=int(v)), restart_cam(), info())))
    g4.add(_combo("Koding", "", [("auto", "Automatisk (skjermkortet når det kan)"), ("vp8", "VP8 i prosessoren")],
                  c.get("codec", "auto"), lambda v: (VC.set_(codec=v), restart_cam(), info())))
    enc_row = Adw.ActionRow(title=i18n.tr("Maskinvarekoding"), subtitle=i18n.tr(VC.encoder_name()))
    g4.add(enc_row)
    cam_row = Adw.ActionRow(title=i18n.tr("Kameraet klarer"), subtitle="…")
    g4.add(cam_row)
    send_row = Adw.ActionRow(title=i18n.tr("Sendes som"), subtitle="…")
    g4.add(send_row)

    def info():
        try:
            cc = VC.cfg()
            dev = VC.camera_choice(cc)
            w, h, fr, codec = VC.quality(cc)
            kb = VC.bitrate_kbps(w, h, fr, codec)
            cam_row.set_subtitle(i18n.tr("mobilkameraet – inntil 1080p fra Android-appen") if dev == "phone" else
                                 VC.mode_summary(dev) or i18n.tr("ukjent (ingen kameramoduser funnet)"))
            note = ""
            want = VC.QUALITY.get(VC._OLD_Q.get(cc["quality"], cc["quality"]), (0, 0))
            if (w, h) != tuple(want[:2]) or fr != int(cc["fps"]):
                note = i18n.tr(" (begrenset av kameraet eller kodingen)")
            send_row.set_subtitle(f"{w}×{h} · {fr} bilder/s · {codec.upper()} · ≈ {kb / 1000:.1f} Mbit/s "
                                  + i18n.tr("per deltaker") + note)
        except Exception as e:  # noqa: BLE001
            send_row.set_subtitle(str(e))
        return False
    GLib.idle_add(info)
    prev_row = _switch_row("Forhåndsvis kameraet", "", False, lambda _v: restart_cam())
    g4.add(prev_row)
    pic = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN, can_shrink=True, visible=False)
    pic.add_css_class("ks-vtile")
    pic.set_size_request(-1, 220)
    g4.add(pic)

    # --- overlay i spill
    g6 = Adw.PreferencesGroup(title=i18n.tr("🖼️ Webkamera-overlay i spill"),
                              description=i18n.tr("Vis deg selv, motparten eller begge i et hjørne over spillet mens "
                                                  "du er i en talekanal."))
    page.add(g6)
    ovc = overlay_controls()
    ovc.set_margin_top(4)
    g6.add(ovc)

    # --- mobilen som webkamera
    import phonecam
    g5 = Adw.PreferencesGroup(title=i18n.tr("📱 Mobilen som webkamera"),
                              description=i18n.tr("I Android-appen: Chat → «📷 Kamera». Bildet kommer hit, og kan "
                                                  "brukes i talekanalene (velg «📱 Mobilkamera» som kamera over), i "
                                                  "et eget vindu, eller som webkamera i andre programmer."))
    page.add(g5)
    st_row = Adw.ActionRow(title=i18n.tr("Status"), subtitle=i18n.tr(phonecam.status()))
    g5.add(st_row)
    wrow = Adw.ActionRow(title=i18n.tr("Vis i eget vindu"),
                         subtitle=i18n.tr("Virker også på Windows – kan fanges som vindu i OBS eller Discord"))
    wb = Gtk.Button(label=i18n.tr("Åpne"), valign=Gtk.Align.CENTER)
    wb.connect("clicked", lambda *_: phonecam.open_window(parent))
    wrow.add_suffix(wb)
    g5.add(wrow)
    if not VC.IS_WIN:
        loops = phonecam.loopback_devices()
        vsub = (i18n.tr("Vises som «{}» i Discord, nettleseren, OBS …").format(loops[0][1]) if loops else
                i18n.tr("Krever v4l2loopback (f.eks. OBS sitt virtuelle kamera) – fant ingen"))
        vrow = Adw.SwitchRow(title=i18n.tr("Bruk som webkamera i andre programmer"), subtitle=vsub,
                             active=phonecam.virtual_on(), sensitive=bool(loops) and ok)
        vmsg = st_row

        def virt(r, _p):
            try:
                vmsg.set_subtitle(phonecam.set_virtual(r.get_active()))
            except Exception as e:  # noqa: BLE001
                vmsg.set_subtitle("✗ " + str(e))
        vrow.connect("notify::active", virt)
        g5.add(vrow)
    ph_tick = GLib.timeout_add_seconds(2, lambda: (st_row.set_subtitle(i18n.tr(phonecam.status())), True)[1])

    def level(db):
        GLib.idle_add(lambda: (meter.set_value(max(0.0, min(1.0, (db + 60) / 60))), False)[1])

    def restart_test():
        if ok:
            VC.mic_test(True, hear=hear.get_active(), cb=level)

    def frame(data, w, h, stride):
        GLib.idle_add(lambda: (pic.set_paintable(_texture((data, w, h, stride))), False)[1])

    def restart_cam():
        on = prev_row.get_active() and ok
        pic.set_visible(on)
        VC.cam_test(on, cb=frame)

    def closed(*_a):
        GLib.source_remove(ph_tick)
        VC.mic_test(False)
        VC.cam_test(False)
    dlg.connect("closed", closed)
    restart_test()
    dlg.present(parent)
    return dlg
