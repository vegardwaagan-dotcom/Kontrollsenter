"""Fanen «GPU-innstillinger»: ett kort per skjermkort som faktisk finnes (NVIDIA, AMD med OverDrive, Intel),
spillinnstillinger (Linux) og Windows-grafikk (Windows)."""
import subprocess
import sys
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

import gpu as G  # noqa: E402
import i18n  # noqa: E402
import theme  # noqa: E402

IS_WIN = sys.platform == "win32"
VENDOR = {"nvidia": ("NVIDIA", "#76b900"), "amd": ("AMD", "#ed1c24"), "intel": ("Intel", "#0071c5")}


def _t(x):
    return i18n.tr(x)


def _card(title, desc=None, badge=None):
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    outer.add_css_class("card")
    inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    for side, v in (("top", 18), ("bottom", 18), ("start", 20), ("end", 20)):
        getattr(inner, f"set_margin_{side}")(v)
    outer.append(inner)
    head = Gtk.Box(spacing=10)
    if badge:
        b = Gtk.Label(label=badge[0])
        b.add_css_class("ks-vendor")
        b.add_css_class("ks-vendor-" + badge[0].lower())
        head.append(b)
    h = Gtk.Label(label=_t(title), xalign=0, hexpand=True, wrap=True)
    h.add_css_class("title-4")
    head.append(h)
    inner.append(head)
    if desc:
        d = Gtk.Label(label=_t(desc), xalign=0, wrap=True)
        d.add_css_class("ks-desc")
        inner.append(d)
    return outer, inner, head


def _row(title, sub, *widgets):
    r = Gtk.Box(spacing=12)
    col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True, valign=Gtk.Align.CENTER)
    col.append(Gtk.Label(label=_t(title), xalign=0, wrap=True))
    if sub:
        s = Gtk.Label(label=_t(sub), xalign=0, wrap=True)
        s.add_css_class("ks-sub")
        col.append(s)
    r.append(col)
    for w in widgets:
        w.set_valign(Gtk.Align.CENTER)
        r.append(w)
    return r


def _spin(lo, hi, val, step=5):
    sp = Gtk.SpinButton.new_with_range(lo, hi, step)
    sp.set_value(val if val is not None else lo)
    sp.set_numeric(True)
    return sp


def _info_grid():
    g = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=6, min_children_per_line=2,
                    column_spacing=10, row_spacing=10, homogeneous=True)
    g.add_css_class("ks-gpu-info")
    return g


def _info_set(grid, items):
    while (c := grid.get_first_child()) is not None:
        grid.remove(c)
    for k, v in items:
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        b.add_css_class("ks-gpu-stat")
        kl = Gtk.Label(label=_t(k).upper(), xalign=0)
        kl.add_css_class("ks-gpu-k")
        vl = Gtk.Label(label=v, xalign=0, ellipsize=3)
        vl.add_css_class("ks-gpu-v")
        vl.add_css_class("numeric")
        b.append(kl)
        b.append(vl)
        grid.append(b)


def _fmt(v, unit="", digits=0):
    if v is None:
        return "–"
    return f"{v:.{digits}f}{unit}"


class GpuPage(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        for side in ("top", "bottom", "start", "end"):
            getattr(self.box, f"set_margin_{side}")(18)
        self.set_child(Adw.Clamp(maximum_size=theme.PAGE_WIDTH, child=self.box))
        self.msg = Gtk.Label(xalign=0, wrap=True)
        self.msg.add_css_class("ks-sub")
        self.updaters = []
        self.gpus = sorted(G.detect(), key=lambda g: (g.get("integrated"), g["vendor"] != "nvidia"))   # kraftigste først

        # tilgang (Linux)
        if not IS_WIN and not G.helper_ready():
            c, i, _h = _card("Gi Kontrollsenter tilgang til skjermkortene",
                             "Endringer i klokker, strøm og OverDrive krever administrator. Skriv passordet én gang, "
                             "så kan Kontrollsenter endre NETTOPP disse innstillingene uten å spørre igjen.")
            b = Gtk.Button(label=_t("Gi tilgang"), halign=Gtk.Align.START)
            b.add_css_class("suggested-action")
            b.connect("clicked", lambda *_: self._do(G.setup_helper, _t("Tilgang er gitt ✓"), rebuild=True))
            i.append(b)
            self.box.append(c)
        self.box.append(self.msg)
        try:
            self._switch_card()
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("gpu-bytte")
        try:                                                 # skjermprofiler, nattlys og lysstyrke
            import avprofiles_ui
            cf = lambda t, d=None: _card(t, d)[:2]  # noqa: E731
            import skjerm_ui
            self.box.append(skjerm_ui.ModeCard(cf))              # velg oppløsning og Hz direkte
            self.box.append(avprofiles_ui.ProfileCard("display", cf))
            self.box.append(avprofiles_ui.NightCard(cf))
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("skjermprofiler")

        if not self.gpus:
            c, i, _h = _card("Fant ingen skjermkort", "Kontrollsenter fant ingen NVIDIA-, AMD- eller Intel-skjermkort.")
            self.box.append(c)
        for g in self.gpus:
            try:
                getattr(self, "_" + g["vendor"])(g)
            except Exception as e:  # noqa: BLE001
                c, i, _h = _card(g["name"], f"Kunne ikke lese skjermkortet: {e}", VENDOR[g["vendor"]])
                self.box.append(c)

        vendors = {g["vendor"] for g in self.gpus}
        if not IS_WIN:
            if "nvidia" in vendors:
                self._dlss()
                self._dlss5_list()
            self._games(vendors)
        else:
            if "nvidia" in vendors:
                self._dlss()
                self._dlss5_list()
            self._windows()
        if not IS_WIN:
            c, i, _h = _card("Ved oppstart", "Klokker, OverDrive og ytelsesnivå nullstilles når PC-en starter på nytt.")
            sw = Gtk.Switch(active=G.cfg()["apply_on_start"])
            sw.connect("notify::active", lambda s, _p: self._apply_on_start(s.get_active()))
            i.append(_row("Bruk innstillingene mine hver gang PC-en starter", None, sw))
            self.box.append(c)
        self.refresh()
        GLib.timeout_add_seconds(3, lambda: (self.get_mapped() and self.refresh(), True)[1])

    # ------------------------------------------------------------------
    # Hovedskjermkort: integrert / dedikert (eller flere dedikerte)
    # ------------------------------------------------------------------
    def _switch_card(self):
        """Bygges når skjermkortlista er hentet (i en tråd – på Windows tar det et par sekunder)."""
        import gpuswitch as SW
        holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        holder._ks_title = "Hovedskjermkort"               # kategorien vet hva som kommer (bygges i en tråd)
        self.box.append(holder)

        def work():
            try:
                gs = SW.gpus()
            except Exception:  # noqa: BLE001
                gs = []
            GLib.idle_add(lambda: (self._switch_card_build(SW, gs, holder), False)[1])
        threading.Thread(target=work, daemon=True).start()

    def _switch_card_build(self, SW, gs, holder):
        if len(gs) < 2:
            return
        c, i, _h = _card("Hovedskjermkort",
                         "Velg hvilket skjermkort som skal drive skjermen og skrivebordet. "
                         + ("Byttet skjer når du logger inn igjen." if not IS_WIN else
                            "Bekreft innen 20 sekunder at du ser bildet – ellers angres byttet av seg selv."))
        holder.append(c)
        warn = Gtk.Label(xalign=0, wrap=True, label="⚠️ " + _t(
            "Skjermkabelen må sitte i skjermkortet du velger. Sitter den i et annet kort, blir skjermen svart. "
            "Integrert skjermkort = kabelen i hovedkortet; dedikert = kabelen i skjermkortet."))
        warn.add_css_class("warning")
        i.append(warn)
        if not SW.supported():
            i.append(Gtk.Label(xalign=0, wrap=True, label=_t(
                "Bytte støttes bare på KDE Plasma (Wayland) og Windows. Bruk BIOS-innstillingen «Primary display».")))
            return
        cur = SW.choice(gs)
        opts = [(None, "Automatisk", "Standard – systemet velger selv", None)] + \
            [(g["id"], g["name"], _t(SW.kind(g)) + (
                "" if g["connected"] is None else
                (" · 🖥️ " + _t("skjerm koblet til") if g["connected"] else " · " + _t("ingen skjerm koblet til"))),
              g) for g in gs]
        row = Gtk.Box(spacing=0, homogeneous=True)
        row.add_css_class("linked")
        btns = []
        first = None
        for gid, name, sub, g in opts:
            b = Gtk.ToggleButton()
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=6, margin_bottom=6)
            t = Gtk.Label(label=_t(name) if g is None else name, wrap=True, justify=Gtk.Justification.CENTER)
            t.add_css_class("heading")
            col.append(t)
            st = Gtk.Label(label=_t(sub), wrap=True, justify=Gtk.Justification.CENTER)
            st.add_css_class("caption")
            col.append(st)
            b.set_child(col)
            if first is None:
                first = b
            else:
                b.set_group(first)
            b.set_active(gid == cur)
            b._gid, b._g = gid, g
            btns.append(b)
            row.append(b)
        i.append(row)
        self.sw_msg = Gtk.Label(xalign=0, wrap=True)
        self.sw_msg.add_css_class("ks-sub")
        i.append(self.sw_msg)
        if not IS_WIN and SW._kwin_devices():
            self.sw_msg.set_label(_t("I bruk nå: {d}").format(d=SW._kwin_devices()))
        self._sw_busy = False

        def toggled(b):
            if not b.get_active() or self._sw_busy or b._gid == SW.choice(gs):
                return
            g = b._g
            if g is not None and g.get("connected") is False:
                body = _t("Ingen skjerm er koblet til {n}. Flytt skjermkabelen til {n} før du logger inn igjen – "
                          "ellers blir skjermen svart.").format(n=g["name"])
                if not IS_WIN:
                    body += " " + _t("(Kontrollsenter sjekker kabelen ved innlogging og bruker det vanlige "
                                     "skjermkortet hvis ingen skjerm er koblet til, så du står ikke uten bilde.)")
            elif g is not None:
                body = _t("Skjermen må være koblet til {n}. Sitter kabelen i et annet skjermkort, blir skjermen "
                          "svart.").format(n=g["name"])
            else:
                body = _t("Systemet velger skjermkort selv igjen.")
            dlg = Adw.AlertDialog(heading=_t("Bytte hovedskjermkort?"), body=body)
            dlg.add_response("no", _t("Avbryt"))
            dlg.add_response("yes", _t("Bytt") if IS_WIN else _t("Bytt ved neste innlogging"))
            dlg.set_response_appearance("yes", Adw.ResponseAppearance.DESTRUCTIVE if g is not None and
                                        g.get("connected") is False else Adw.ResponseAppearance.SUGGESTED)

            def resp(_d, r):
                if r != "yes":
                    self._sw_busy = True
                    for x in btns:
                        x.set_active(x._gid == SW.choice(gs))
                    self._sw_busy = False
                    return
                self._apply_switch(SW, b._gid, gs)
            dlg.connect("response", resp)
            dlg.present(self.get_root())
        for b in btns:
            b.connect("toggled", toggled)

    def _apply_switch(self, SW, gid, gs):
        try:
            need_ok = SW.set_choice(gid, gs)
        except Exception as e:  # noqa: BLE001
            self.sw_msg.set_label(str(e))
            return
        if IS_WIN:
            if not need_ok:
                self.sw_msg.set_label(_t("Alle skjermkortene er på igjen ✓"))
                return
            left = [20]
            dlg = Adw.AlertDialog(heading=_t("Ser du bildet?"),
                                  body=_t("Trykk «Behold» hvis skjermen virker. Ellers angres byttet om 20 sekunder."))
            dlg.add_response("undo", _t("Angre"))
            dlg.add_response("keep", _t("Behold"))
            dlg.set_response_appearance("keep", Adw.ResponseAppearance.SUGGESTED)

            def tick():
                left[0] -= 1
                dlg.set_body(_t("Trykk «Behold» hvis skjermen virker. Ellers angres byttet om {n} sekunder.")
                             .format(n=max(0, left[0])))
                return left[0] > 0

            def resp(_d, r):
                if r == "keep":
                    SW.confirm_ok()
                    self.sw_msg.set_label(_t("Skjermkortet er byttet ✓"))
                else:
                    self.sw_msg.set_label(_t("Byttet angres …"))
            GLib.timeout_add_seconds(1, tick)
            dlg.connect("response", resp)
            dlg.present(self.get_root())
            return
        self.sw_msg.set_label(_t("Lagret ✓ – byttet skjer når du logger ut og inn igjen."))
        lo = Gtk.Button(label=_t("Logg ut nå"), halign=Gtk.Align.START)
        lo.connect("clicked", lambda *_: SW.logout_prompt())
        par = self.sw_msg.get_parent()
        if par is not None and not getattr(self, "_lo_added", False):
            par.append(lo)
            self._lo_added = True

    # ------------------------------------------------------------------
    def _do(self, fn, ok=None, rebuild=False, gid=None, key=None, cmd=None):
        self.msg.set_label(_t("Arbeider …"))

        def work():
            try:
                r = fn()
                if gid and key:
                    G.save_cmd(gid, key, cmd)
                txt = ok or (r if isinstance(r, str) and r != "OK" else _t("Ferdig ✓"))
            except G.NeedSetup as e:
                txt = str(e)
            except Exception as e:  # noqa: BLE001
                txt = _t("Det gikk ikke: ") + str(e)
            GLib.idle_add(self._done, txt, rebuild)
        threading.Thread(target=work, daemon=True).start()

    def _done(self, txt, rebuild):
        self.msg.set_label(txt)
        if rebuild:
            parent = self.get_parent()
            while parent is not None and not isinstance(parent, Gtk.Box):
                parent = parent.get_parent()
            if parent is not None:
                parent.remove(self)
                parent.append(GpuPage())
        self.refresh()
        return False

    def _cmd(self, gid, key, *cmd, ok=None):
        self._do(lambda: G.run(*cmd), ok, gid=gid, key=key, cmd=list(cmd))

    def _apply_on_start(self, on):
        c = G.cfg()
        c["apply_on_start"] = on
        G.save_cfg(c)

    def refresh(self):
        def work():
            res = []
            for fn in self.updaters:
                try:
                    res.append((fn, fn(None)))
                except Exception:  # noqa: BLE001
                    pass
            GLib.idle_add(lambda: ([f(v) for f, v in res], False)[1])
        threading.Thread(target=work, daemon=True).start()
        return False

    def _open(self, cmd):
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             **({"creationflags": 0x08000000} if IS_WIN else {"start_new_session": True}))
        except OSError as e:
            self.msg.set_label(str(e))

    # ------------------------------------------------------------------ NVIDIA
    def _nvidia(self, g):
        idx, gid = g["idx"], g["id"]
        st = G.nvidia_state(idx)
        c, i, head = _card(st.get("name") or g["name"],
                           f"Driver {st.get('driver_version')} · VBIOS {st.get('vbios_version')}", VENDOR["nvidia"])
        app = G.nvidia_settings_app()
        if app:
            b = Gtk.Button(label=_t("NVIDIA-innstillinger"), valign=Gtk.Align.CENTER)
            b.connect("clicked", lambda *_: self._open(app))
            head.append(b)
        grid = _info_grid()
        i.append(grid)

        def upd(v):
            if v is None:
                return G.nvidia_state(idx)
            _info_set(grid, [("Temperatur", _fmt(v.get("temperature.gpu"), " °C")),
                             ("Last", _fmt(v.get("utilization.gpu"), " %")),
                             ("Strøm", f"{_fmt(v.get('power.draw'), ' W')} / {_fmt(v.get('power.limit'), ' W')}"),
                             ("GPU-klokke", _fmt(v.get("clocks.gr"), " MHz")),
                             ("Minneklokke", _fmt(v.get("clocks.mem"), " MHz")),
                             ("VRAM", f"{_fmt(v.get('memory.used'))} / {_fmt(v.get('memory.total'))} MB"),
                             ("Vifte", _fmt(v.get("fan.speed"), " %")),
                             ("PCIe", f"Gen {_fmt(v.get('pcie.link.gen.current'))} x{_fmt(v.get('pcie.link.width.current'))}"),
                             ("Ytelsestilstand", v.get("pstate") or "–")])
        self.updaters.append(upd)
        upd(st)

        lo, hi = st.get("power.min_limit") or 50, st.get("power.max_limit") or 600
        sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, 5)
        sc.set_value(st.get("power.limit") or hi)
        sc.set_hexpand(True)
        sc.set_size_request(260, -1)
        sc.add_mark(st.get("power.default_limit") or hi, Gtk.PositionType.BOTTOM, _t("standard"))
        val = Gtk.Label(label=f"{sc.get_value():.0f} W", width_chars=6)
        sc.connect("value-changed", lambda s: val.set_label(f"{s.get_value():.0f} W"))
        b = Gtk.Button(label=_t("Bruk"))
        b.connect("clicked", lambda *_: self._cmd(gid, "pl", "nv-pl", idx, int(sc.get_value()),
                                                  ok=_t("Strømgrensen er satt ✓")))
        i.append(_row("Strømgrense", f"{lo:.0f}–{hi:.0f} W. Lavere = kjøligere og stillere, høyere = mer ytelse. "
                      "Strømmodus på Oversikt kan overstyre denne.", sc, val, b))

        mg = int(st.get("clocks.max.graphics") or 3000)
        gmin, gmax = _spin(200, mg, 210, 15), _spin(200, mg, mg, 15)
        lock = Gtk.Button(label=_t("Lås"))
        lock.connect("clicked", lambda *_: self._cmd(gid, "lgc", "nv-lgc", idx, int(gmin.get_value()),
                                                     int(gmax.get_value()), ok=_t("GPU-klokken er låst ✓")))
        free = Gtk.Button(label=_t("Frigi"))
        free.connect("clicked", lambda *_: (self._do(lambda: G.run("nv-rgc", idx), _t("GPU-klokken er frigitt ✓")),
                                            G.save_cmd(gid, "lgc", None)))
        i.append(_row("Lås GPU-klokke (MHz)", "Hold klokken innenfor et område – jevnere FPS, eller lavere maks for "
                      "mindre varme og støy.", gmin, gmax, lock, free))

        mm = int(st.get("clocks.max.memory") or 10000)
        mmin, mmax = _spin(100, mm, mm, 50), _spin(100, mm, mm, 50)
        mlock = Gtk.Button(label=_t("Lås"))
        mlock.connect("clicked", lambda *_: self._cmd(gid, "lmc", "nv-lmc", idx, int(mmin.get_value()),
                                                      int(mmax.get_value()), ok=_t("Minneklokken er låst ✓")))
        mfree = Gtk.Button(label=_t("Frigi"))
        mfree.connect("clicked", lambda *_: (self._do(lambda: G.run("nv-rmc", idx), _t("Minneklokken er frigitt ✓")),
                                             G.save_cmd(gid, "lmc", None)))
        i.append(_row("Lås minneklokke (MHz)", "Maks minneklokke hele tiden kan hjelpe mot hakking i noen spill.",
                      mmin, mmax, mlock, mfree))

        pm = Gtk.Switch(active=bool(st.get("persistence")))
        pm.connect("notify::active", lambda s, _p: self._cmd(gid, "pm", "nv-pm", idx, 1 if s.get_active() else 0))
        i.append(_row("Hold driveren klar (persistence mode)", "Raskere oppstart av spill og færre små hakk – bruker "
                      "litt mer strøm når PC-en står stille.", pm))
        self.box.append(c)
        self._nv_more(g)

    def _nv_more(self, g):
        """Overklokking, vifter og «hva bremser kortet» – via NVML (virker også på Wayland)."""
        idx, gid = g["idx"], g["id"]
        e = G.nv_extra(idx)
        if not e:
            return
        c, i, _h = _card("Overklokking og vifter", "Gjelder til PC-en startes på nytt – slå på «Bruk ved oppstart» "
                         "øverst for å beholde dem.", VENDOR["nvidia"])
        why = Gtk.Label(xalign=0, wrap=True)
        dlss_l = Gtk.Label(xalign=0, wrap=True, label=_t("Ingen spill med DLSS kjører nå"))

        def upd(v):
            if v is None:
                import dlssinfo
                d = G.nv_extra(idx)
                d["dlss_now"] = dlssinfo.summary()
                return d
            if "dlss_now" in v:
                dlss_l.set_label(v["dlss_now"] or _t("Ingen spill med DLSS kjører nå"))
            rs = v.get("reasons") or []
            fans = v.get("fans") or []
            why.set_label(_t("Bremses nå av: ") + ", ".join(rs) if rs and rs != ["tomgang"] else
                          _t("Kortet går fritt – ingenting bremser det") if not rs else _t("Kortet hviler"))
            why.set_tooltip_text(f"Vifter: {' / '.join(str(f) + ' %' for f in fans)} · "
                                 f"Videokoder (NVENC): {v.get('nvenc', 0)} %")
        self.updaters.append(upd)
        upd(e)
        i.append(_row("Hva begrenser ytelsen", "Viser om strømgrensen, varme eller noe annet holder kortet tilbake.",
                      why))
        i.append(_row("DLSS i bruk nå", "Versjonen spillet som kjører faktisk har lastet inn – så du ser at valgene "
                      "dine virker.", dlss_l))
        if IS_WIN:
            note = Gtk.Label(label=_t("Overklokking og vifter på Windows: bruk NVIDIA-appen eller MSI Afterburner."),
                             xalign=0, wrap=True)
            note.add_css_class("ks-sub")
            i.append(note)
            self.box.append(c)
            return

        clo, chi = e.get("core_range", (-500, 500))
        mlo, mhi = e.get("mem_range", (-1000, 2000))
        core = _spin(max(clo, -500), min(chi, 500), e.get("core", 0), 15)
        mem = _spin(max(mlo, -1000), min(mhi, 3000), e.get("mem", 0), 50)
        ok_b = Gtk.Button(label=_t("Bruk"))
        ok_b.add_css_class("suggested-action")
        ok_b.connect("clicked", lambda *_: self._cmd(gid, "oc", "nv-oc", idx, int(core.get_value()),
                                                     int(mem.get_value()), ok=_t("Overklokkingen er satt ✓")))
        zero = Gtk.Button(label=_t("Nullstill"))
        zero.connect("clicked", lambda *_: (core.set_value(0), mem.set_value(0),
                                            self._do(lambda: G.run("nv-oc", idx, 0, 0), _t("Tilbake til standard ✓")),
                                            G.save_cmd(gid, "oc", None)))
        i.append(_row("Klokke-offset (MHz): GPU og minne",
                      "Start forsiktig (+100 GPU, +500 minne) og test i et spill. Krasjer det, gå ned igjen. "
                      "Minus = kjøligere og stillere (undervolt-effekt).", core, mem, ok_b, zero))

        # ---- ferdige profiler og trygg overklokking ----
        import gpuscan
        prof = Gtk.DropDown.new_from_strings([_t(t) for k, t, *_r in gpuscan.PRESETS if k])
        pkeys = [k for k, *_r in gpuscan.PRESETS if k]
        if not gpuscan.last_result():
            prof.set_selected(0)
        pb = Gtk.Button(label=_t("Bruk"))
        pb.connect("clicked", lambda *_: self._do(lambda: (gpuscan.apply_preset(pkeys[prof.get_selected()]),
                                                           G.save_cmd(gid, "oc", None))[1] or
                                                  _t("Profilen er satt ✓ – gjelder til PC-en startes på nytt")))
        i.append(_row("Ferdige profiler", "Effektiv = omtrent samme FPS med mindre strøm, varme og støy. Stille = "
                      "lavest mulig. «Skannet maks» bruker resultatet fra trygg overklokking under.", prof, pb))
        res = gpuscan.last_result()
        scan_lbl = Gtk.Label(xalign=0, wrap=True, label=_t("Sist funnet: GPU +{c} MHz, minne +{m} MHz").format(
            c=res["core"], m=res["mem"]) if res else _t("Ikke skannet ennå. Tar 5–8 minutter – kortet går for fullt."))
        scan_lbl.add_css_class("ks-sub")
        sb = Gtk.Button(label=_t("Start trygg overklokking"))
        sb.add_css_class("suggested-action")
        stop = Gtk.Button(label=_t("Stopp"), sensitive=False)

        def start(*_):
            if not G.helper_ready():
                self.msg.set_label(_t("Trykk «Gi tilgang» øverst først"))
                return
            sb.set_sensitive(False)
            stop.set_sensitive(True)

            def prog(n, tot, txt):
                GLib.idle_add(lambda: (scan_lbl.set_label(f"{n}/{tot} · {txt}"), False)[1])

            def done(r):
                def ui():
                    sb.set_sensitive(True)
                    stop.set_sensitive(False)
                    scan_lbl.set_label(r.get("error") and _t("Avbrutt: ") + r["error"] or
                                       _t("Ferdig ✓ GPU +{c} MHz, minne +{m} MHz – satt nå, og brukes ved oppstart "
                                          "hvis det er slått på").format(c=r["core"], m=r["mem"]))
                    core.set_value(r.get("core", 0))
                    mem.set_value(r.get("mem", 0))
                    return False
                GLib.idle_add(ui)

            def work():
                try:
                    r = gpuscan.scan(gid, idx, progress=prog)
                except Exception as ex:  # noqa: BLE001
                    r = {"error": str(ex)}
                done(r)
            threading.Thread(target=work, daemon=True).start()
        sb.connect("clicked", start)
        stop.connect("clicked", lambda *_: gpuscan.SCAN.update(stop=True))
        i.append(_row("Trygg overklokking", "Går opp litt om gangen og tester hvert steg for regnefeil. Ender et "
                      "trygt stykke under grensen. Lukk spill først.", sb, stop))
        i.append(scan_lbl)

        fc = G.fan_cfg(gid)
        fmin, fmax = e.get("fan_range", (30, 100))
        mode = Gtk.DropDown.new_from_strings([_t("Automatisk"), _t("Fast fart"), _t("Egen kurve")])
        modes = ["auto", "fast", "kurve"]
        mode.set_selected(modes.index(fc.get("mode", "auto")) if fc.get("mode") in modes else 0)
        pct = _spin(fmin, fmax, max(fmin, fc.get("pct", 60)), 5)
        fb = Gtk.Button(label=_t("Bruk"))
        fb.connect("clicked", lambda *_: self._do(lambda: G.set_fan(gid, idx, modes[mode.get_selected()],
                                                                    pct=int(pct.get_value()))))
        i.append(_row("Vifter", f"Automatisk = kortet bestemmer. Fast fart: {fmin}–{fmax} %. Egen kurve: farten "
                      "følger temperaturen (under).", mode, pct, fb))
        curve = fc.get("curve") or G.FAN_DEF["curve"]
        spins = []
        box = Gtk.Box(spacing=6)
        for t, p in curve:
            ts, ps = _spin(20, 100, t, 1), _spin(fmin, 100, max(fmin, p), 5)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            col.append(ts)
            col.append(ps)
            box.append(col)
            spins.append((ts, ps))
        cb = Gtk.Button(label=_t("Bruk kurven"), valign=Gtk.Align.CENTER)
        cb.connect("clicked", lambda *_: (mode.set_selected(2), self._do(lambda: G.set_fan(
            gid, idx, "kurve", curve=[[int(a.get_value()), int(b.get_value())] for a, b in spins]))))
        i.append(_row("Viftekurve", "Øverst: temperatur (°C). Under: viftefart (%). Kontrollsenter må kjøre (også i "
                      "bakgrunnen) for at kurven skal virke.", box, cb))
        note = Gtk.Label(label=_t("G-SYNC/VRR slås av og på under Skjerm. Bildeskarphet og digital vibrans finnes "
                                  "bare i NVIDIA-innstillingene på X11."), xalign=0, wrap=True)
        note.add_css_class("ks-sub")
        i.append(note)
        self.box.append(c)

    # ------------------------------------------------------------------ AMD
    def _amd(self, g):
        gid = g["id"]
        title = g["name"] + (" (" + _t("integrert") + ")" if g.get("integrated") else "")
        if IS_WIN:
            c, i, head = _card(title, f"Driver {g.get('driver')}", VENDOR["amd"])
            app = G.amd_app()
            b = Gtk.Button(label=_t("Åpne AMD Software"), halign=Gtk.Align.START, sensitive=bool(app))
            b.connect("clicked", lambda *_: app and self._open(app))
            i.append(b)
            i.append(Gtk.Label(label=_t("Radeon Boost, Anti-Lag, FreeSync og overklokking styres i AMD Software."),
                               xalign=0, wrap=True, css_classes=["ks-sub"]))
            self.box.append(c)
            return
        card = g["card"]
        st = G.amd_state(card)
        c, i, _head = _card(title, f"{card} · {g.get('driver')}", VENDOR["amd"])
        grid = _info_grid()
        i.append(grid)

        def upd(v):
            if v is None:
                return G.amd_state(card)
            _info_set(grid, [("Temperatur", _fmt(v.get("temp"), " °C")), ("Last", (v.get("busy") or "–") + " %"),
                             ("GPU-klokke", _fmt(v.get("sclk"), " MHz")), ("Minneklokke", _fmt(v.get("mclk"), " MHz")),
                             ("Strøm", _fmt(v.get("power"), " W", 1)),
                             ("VRAM", f"{v['vram'][0]} / {v['vram'][1]} MB" if v.get("vram") else "–"),
                             ("Ytelsesnivå", dict(G.LEVELS).get(v.get("level"), v.get("level") or "–"))])
        self.updaters.append(upd)
        upd(st)

        keys = [k for k, _n in G.LEVELS]
        dd = Gtk.DropDown.new_from_strings([_t(n) for _k, n in G.LEVELS])
        dd.set_selected(keys.index(st["level"]) if st.get("level") in keys else 0)
        dd.connect("notify::selected", lambda d, _p: self._cmd(gid, "level", "amd-level", card, keys[d.get_selected()],
                                                               ok=_t("Ytelsesnivået er satt ✓")))
        i.append(_row("Ytelsesnivå", "Automatisk passer det meste. «Høyest» gir full fart hele tiden.", dd))

        if st.get("profiles"):
            pids = [p for p, _n in st["profiles"]]
            pdd = Gtk.DropDown.new_from_strings([n.replace("_", " ").title() for _p, n in st["profiles"]])
            pdd.set_selected(pids.index(st["profile"]) if st.get("profile") in pids else 0)
            pdd.connect("notify::selected", lambda d, _p: self._cmd(gid, "profile", "amd-profile", card,
                                                                    pids[d.get_selected()], ok=_t("Profilen er satt ✓")))
            i.append(_row("Strømprofil", "3D Full Screen for spill, Power Saving for stille drift, Compute for "
                          "beregninger.", pdd))

        if st.get("cap") and st.get("cap_max"):
            lo, hi = (st.get("cap_min") or 1) / 1e6, st["cap_max"] / 1e6
            sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, 1)
            sc.set_value(st["cap"] / 1e6)
            sc.set_hexpand(True)
            sc.set_size_request(240, -1)
            val = Gtk.Label(label=f"{sc.get_value():.0f} W", width_chars=6)
            sc.connect("value-changed", lambda s: val.set_label(f"{s.get_value():.0f} W"))
            b = Gtk.Button(label=_t("Bruk"))
            b.connect("clicked", lambda *_: self._cmd(gid, "cap", "amd-cap", card, int(sc.get_value() * 1e6),
                                                      ok=_t("Strømgrensen er satt ✓")))
            i.append(_row("Strømgrense", f"{lo:.0f}–{hi:.0f} W (Power Limit).", sc, val, b))

        od = st.get("od")
        h = Gtk.Label(label=_t("OverDrive"), xalign=0)
        h.add_css_class("heading")
        i.append(h)
        if not od:
            ln = Gtk.Label(label=_t("OverDrive er ikke slått på i Linux-kjernen. Slå det på med kjerneparameteren "
                                    "amdgpu.ppfeaturemask=0xffffffff (på Bazzite: «rpm-ostree kargs "
                                    "--append=amdgpu.ppfeaturemask=0xffffffff») og start PC-en på nytt."),
                           xalign=0, wrap=True, selectable=True)
            ln.add_css_class("ks-sub")
            i.append(ln)
            self.box.append(c)
            return
        warn = Gtk.Label(label=_t("Øk forsiktig – for høye klokker kan gi krasj eller svart skjerm. «Tilbakestill» "
                                  "setter alt tilbake til fabrikk."), xalign=0, wrap=True)
        warn.add_css_class("ks-sub")
        i.append(warn)
        spins = []
        for kind, label in (("sclk", "GPU-klokke"), ("mclk", "Minneklokke")):
            rng = od["range"].get(kind)
            for pidx, mhz in od[kind]:
                lo, hi = rng if rng else (100, 5000)
                sp = _spin(lo, hi, mhz, 25)
                spins.append(("s" if kind == "sclk" else "m", pidx, sp))
                nm = _t(label) + (" – " + (_t("laveste") if pidx == 0 else _t("høyeste")) if len(od[kind]) == 2 else
                                  f" – trinn {pidx}")
                i.append(_row(nm, f"{lo}–{hi} MHz", sp))
        vo = None
        if od.get("vo") is not None:
            lo, hi = od.get("vo_range") or (-200, 0)
            vo = _spin(lo, hi, od["vo"], 5)
            i.append(_row("Spenningsavvik (mV)", "Negativt tall = lavere spenning (undervolt): kjøligere og ofte like "
                          "raskt.", vo))
        btns = Gtk.Box(spacing=8)
        apply = Gtk.Button(label=_t("Bruk OverDrive"))
        apply.add_css_class("suggested-action")
        reset = Gtk.Button(label=_t("Tilbakestill"))
        reset.add_css_class("destructive-action")

        def do_apply(*_):
            def work():
                for k, pidx, sp in spins:
                    G.run("amd-od", card, k, pidx, int(sp.get_value()))
                    G.save_cmd(gid, f"od_{k}{pidx}", ["amd-od", card, k, pidx, int(sp.get_value())])
                if vo is not None:
                    G.run("amd-od", card, "vo", int(vo.get_value()))
                    G.save_cmd(gid, "od_vo", ["amd-od", card, "vo", int(vo.get_value())])
                G.run("amd-od", card, "c")
                G.save_cmd(gid, "od_c", ["amd-od", card, "c"])
                return _t("OverDrive er brukt ✓")
            self._confirm(_t("Bruke disse klokkene på skjermkortet?"), lambda: self._do(work))

        def do_reset(*_):
            def work():
                G.run("amd-od", card, "r")
                c2 = G.cfg()
                s = c2["saved"].get(gid, {})
                s["keyed"] = {k: v for k, v in s.get("keyed", {}).items() if not k.startswith("od_")}
                s["cmds"] = [v for v in s["keyed"].values()]
                G.save_cfg(c2)
                return _t("Tilbakestilt til fabrikk ✓")
            self._do(work, rebuild=True)
        apply.connect("clicked", do_apply)
        reset.connect("clicked", do_reset)
        btns.append(apply)
        btns.append(reset)
        i.append(btns)
        self.box.append(c)

    # ------------------------------------------------------------------ Intel
    def _intel(self, g):
        gid = g["id"]
        if IS_WIN:
            c, i, _h = _card(g["name"], f"Driver {g.get('driver')}", VENDOR["intel"])
            app = G.intel_app()
            b = Gtk.Button(label=_t("Åpne Intel Graphics Software"), halign=Gtk.Align.START)
            b.connect("clicked", lambda *_: app and self._open(app))
            i.append(b)
            self.box.append(c)
            return
        card = g["card"]
        st = G.intel_state(card)
        c, i, _h = _card(g["name"], f"{card} · {g.get('driver')}", VENDOR["intel"])
        grid = _info_grid()
        i.append(grid)

        def upd(v):
            if v is None:
                return G.intel_state(card)
            _info_set(grid, [("GPU-klokke", _fmt(v.get("cur"), " MHz")), ("Min", _fmt(v.get("min"), " MHz")),
                             ("Maks", _fmt(v.get("max"), " MHz")), ("Boost", _fmt(v.get("boost"), " MHz"))])
        self.updaters.append(upd)
        upd(st)
        lo, hi = st.get("lo") or 100, st.get("hi") or 2000
        for key, label, sub in (("min", "Laveste GPU-klokke", "Høyere = jevnere, men mer strøm."),
                                ("max", "Høyeste GPU-klokke", "Lavere = kjøligere og lengre batteritid."),
                                ("boost", "Boost-klokke", "Klokken GPU-en kan gå opp til ved høy last.")):
            sp = _spin(lo, hi, st.get(key) or hi, 50)
            b = Gtk.Button(label=_t("Bruk"))
            b.connect("clicked", lambda *_, k=key, s=sp: self._cmd(gid, f"freq_{k}", "intel-freq", card, k,
                                                                    int(s.get_value())))
            i.append(_row(label, f"{lo}–{hi} MHz. {sub}", sp, b))
        self.box.append(c)

    # ------------------------------------------------------------------ felles
    def _games(self, vendors):
        c, i, _h = _card("Spillinnstillinger", "Gjelder alle spill du starter etter neste innlogging (Proton, Vulkan "
                         "og OpenGL). Påvirker ikke skrivebordet.")
        cur = G.env_get()
        for key, _v, name, desc, who in G.ENV_OPTS:
            if who and who not in vendors:
                continue
            sw = Gtk.Switch(active=G.env_on(key) if isinstance(_v, dict) else key in cur)
            sw.connect("notify::active", lambda s, _p, k=key: self._env(k, s.get_active()))
            i.append(_row(name, desc, sw))
        self.box.append(c)

    def _dlss(self):
        """DLSS (versjon og kvalitet), bildegenerering, Ray Reconstruction, Reflex og G-SYNC for alle Proton-spill."""
        c, i, _h = _card("DLSS, Reflex og G-SYNC",
                         "Gjelder alle spill (samme som DLSS-overstyring i NVIDIA-appen). Start spillet på nytt etter "
                         "endring. Hvert spill kan ha egne valg under Spill → Bibliotek." if IS_WIN else
                         "Gjelder alle Windows-spill i Steam/Proton du starter etter neste innlogging. Hvert spill kan "
                         "ha egne valg under Spill → Bibliotek. «Spillet bestemmer» = som før.", VENDOR["nvidia"])
        for key, name, desc, opts in G.NV_CHOICES:
            if IS_WIN and key not in G.WIN_KEYS:
                continue
            dd = Gtk.DropDown.new_from_strings([_t(t) for _i, t, _v in opts])
            dd.set_valign(Gtk.Align.CENTER)
            ids = [o[0] for o in opts]
            dd.set_selected(ids.index(G.nv_choice(key)))

            def changed(d, _p, k=key, ids=ids):
                try:
                    t = G.nv_choice_set(k, ids[d.get_selected()])
                    self.msg.set_label(_t("Lagret: ") + t + (_t(" – start spillet på nytt") if IS_WIN else
                                                             _t(" – gjelder etter neste innlogging")))
                except Exception as e:  # noqa: BLE001
                    self.msg.set_label(str(e))
            dd.connect("notify::selected", changed)
            i.append(_row(name, desc, dd))
        self.box.append(c)

    def _dlss5_list(self):
        """Spillene som har DLSS 5 – NVIDIA sin offisielle liste, hentes på nytt hver 12. time."""
        import dlsslist
        c, i, _h = _card("Spill med DLSS 5", "Fra NVIDIA sin offisielle liste. Oppdateres av seg selv, og du får "
                         "varsel når et nytt spill får DLSS 5.", VENDOR["nvidia"])
        lst = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        i.append(lst)
        when = Gtk.Label(xalign=0)
        when.add_css_class("ks-sub")
        i.append(when)
        btns = Gtk.Box(spacing=8)
        upd = Gtk.Button(label=_t("Oppdater nå"))
        web = Gtk.Button(label=_t("Hele lista hos NVIDIA"))
        web.connect("clicked", lambda *_: self._open(["xdg-open" if not IS_WIN else "explorer", dlsslist.PAGE]))
        btns.append(upd)
        btns.append(web)
        i.append(btns)

        def show(gs):
            while (ch := lst.get_first_child()):
                lst.remove(ch)
            if not gs:
                lst.append(Gtk.Label(label=_t("Fikk ikke hentet lista ennå (krever nett)."), xalign=0))
            for g in gs:
                row = Gtk.Box(spacing=8)
                row.append(Gtk.Label(label=("✅ " if g["installed"] else "• ") + g["name"], xalign=0, hexpand=True))
                extra = ", ".join(x for x in (g["mfg"].split(",")[-1].strip().replace("X", "× bildegenerering")
                                              if g["mfg"] else "", "path tracing" if g["rt"] == "Path Tracing"
                                              else "strålesporing" if g["rt"] else "") if x)
                sub = Gtk.Label(label=(_t("installert · ") if g["installed"] else "") + extra, xalign=1)
                sub.add_css_class("ks-sub")
                row.append(sub)
                lst.append(row)
            when.set_label(_t("Oppdatert ") + (dlsslist.updated() or "–") +
                           _t(" · ✅ = installert her. Slå på DLSS 5 i spillets grafikkmeny (krever RTX 50)."))

        def load(force=False):
            def work():
                dlsslist.refresh(force)
                gs = dlsslist.dlss5_games()
                GLib.idle_add(lambda: (show(gs), False)[1])
            threading.Thread(target=work, daemon=True).start()
        upd.connect("clicked", lambda *_: load(True))
        show(dlsslist.dlss5_games())
        load()
        self.box.append(c)

    def _env(self, key, on):
        try:
            G.env_set(key, on)
            self.msg.set_label(_t("Lagret ✓ – gjelder etter neste innlogging"))
        except Exception as e:  # noqa: BLE001
            self.msg.set_label(str(e))

    def _windows(self):
        c, i, _h = _card("Windows-grafikk", "Innstillinger i Windows som gjelder alle skjermkort.")
        st = G.win_graphics()
        hags = Gtk.Switch(active=bool(st.get("hags")))
        hags.connect("notify::active", lambda s, _p: self._do(lambda: G.win_hags(s.get_active()),
                                                              _t("Lagret ✓ – start PC-en på nytt")))
        i.append(_row("Maskinvareakselerert GPU-planlegging", "Kan gi litt lavere forsinkelse. Krever omstart og "
                      "administrator.", hags))
        for key, name, desc in (("SwapEffectUpgradeEnable", "Optimaliseringer for spill i vindu",
                                 "Lavere forsinkelse og VRR i spill som kjører i vindu eller rammeløst."),
                                ("VRROptimizeEnable", "Variabel oppdateringsfrekvens", "G-SYNC/FreeSync også i spill "
                                 "som ikke støtter det selv.")):
            sw = Gtk.Switch(active=bool(st.get("windowed" if key.startswith("Swap") else "vrr")))
            sw.connect("notify::active", lambda s, _p, k=key: self._do(lambda: G.win_dx_set(k, s.get_active()),
                                                                       _t("Lagret ✓")))
            i.append(_row(name, desc, sw))
        self.box.append(c)

    def _confirm(self, text, on_ok):
        d = Adw.AlertDialog(heading=_t("GPU-innstillinger"), body=text)
        d.add_response("nei", _t("Avbryt"))
        d.add_response("ja", _t("Bruk"))
        d.set_response_appearance("ja", Adw.ResponseAppearance.SUGGESTED)
        d.connect("response", lambda _d, r: r == "ja" and on_ok())
        d.present(self.get_root())
