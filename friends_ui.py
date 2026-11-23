"""«PC-er utenfor hjemmet»: vennenes PC-er – hva de spiller, temperaturer, CPU, minne og alt om PC-en."""
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

import friends as F  # noqa: E402
import i18n  # noqa: E402

_t = i18n.tr


def _card(title, sub=None):
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    outer.add_css_class("card")
    inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    for side, v in (("top", 16), ("bottom", 16), ("start", 18), ("end", 18)):
        getattr(inner, f"set_margin_{side}")(v)
    outer.append(inner)
    t = Gtk.Label(label=_t(title), xalign=0)
    t.add_css_class("heading")
    inner.append(t)
    if sub:
        s = Gtk.Label(label=_t(sub), xalign=0, wrap=True)
        s.add_css_class("dim-label")
        s.add_css_class("caption")
        inner.append(s)
    return outer, inner


def _ago(t):
    if not t:
        return _t("aldri sett")
    s = int(time.time() - t)
    if s < 90:
        return _t("nå nettopp")
    if s < 3600:
        return f"{s // 60} min " + _t("siden")
    if s < 86400:
        return f"{s // 3600} t " + _t("siden")
    return time.strftime("%d.%m %H:%M", time.localtime(t))


def _hm(sec):
    sec = int(sec or 0)
    return f"{sec // 3600} t {sec % 3600 // 60} min"


def rows_for(d):
    """[(seksjon, [(navn, verdi)])] – alt vi vet om vennens PC."""
    def f(v, unit="", nd=0):
        return "–" if v is None else (f"{v:.{nd}f}{unit}" if isinstance(v, (int, float)) else f"{v}{unit}")
    out = []
    play = []
    if d.get("game"):
        play.append((_t("Spiller nå"), "🎮 " + d["game"] + (f" · {d['session_min']} min" if d.get("session_min") else "")))
    if d.get("fps"):
        play.append(("FPS", str(d["fps"])))
    if d.get("play_s") is not None:
        play.append((_t("Spilt i dag"), _hm(d["play_s"]) + (f" · mest {d['top_game']}" if d.get("top_game") else "")))
    if play:
        out.append((_t("Spill"), play))
    live = []
    if d.get("cpu_t") is not None or d.get("cpu_l") is not None:
        live.append(("CPU", f"{f(d.get('cpu_t'), ' °C')} · {f(d.get('cpu_l'), ' %')}"))
    if d.get("gpu_t") is not None:
        live.append(("GPU", f"{f(d.get('gpu_t'), ' °C')} · {f(d.get('gpu_l'), ' %')}" +
                     (f" · {f(d.get('gpu_w'), ' W')}" if d.get("gpu_w") else "")))
    if d.get("ram_used") is not None:
        live.append((_t("Minne"), f"{d['ram_used']} / {d.get('ram_total')} GB"))
    if d.get("vram_used") is not None:
        live.append(("VRAM", f"{d['vram_used'] / 1024:.1f} / {(d.get('vram_total') or 0) / 1024:.1f} GB"))
    if d.get("watts"):
        live.append((_t("Strøm"), f"{d['watts']} W"))
    if d.get("uptime"):
        live.append((_t("Oppe"), _hm(d["uptime"])))
    if live:
        out.append((_t("Akkurat nå"), live))
    hw = [(k, d[key]) for k, key in ((_t("Prosessor"), "cpu"), (_t("Skjermkort"), "gpu"), (_t("Minne"), "ram"),
                                     (_t("Hovedkort"), "board"), (_t("Disker"), "disks"), (_t("Driver"), "driver"),
                                     (_t("System"), "os"), (_t("Maskin"), "model"), (_t("Kjerne"), "kernel"))
          if d.get(key)]
    if hw:
        out.append((_t("PC-en"), hw))
    if d.get("version"):
        out.append(("Kontrollsenter", [(_t("Versjon"), d["version"])]))
    return out


class FriendDialog(Adw.Dialog):
    """Alt om én PC – oppdateres hvert 5. sekund mens det er åpent. fetch() henter nye data (i en tråd)."""

    def __init__(self, f, fetch=None):
        super().__init__(title=f.get("friend") or f.get("name") or "?", content_width=560, content_height=640)
        self.addr = f.get("addr")
        self.fetch = fetch
        tv = Adw.ToolbarView()
        tv.add_top_bar(Adw.HeaderBar())
        self.page = Adw.PreferencesPage()
        tv.set_content(self.page)
        self.set_child(tv)
        self.groups = []
        self._show(f)
        self._tid = GLib.timeout_add_seconds(5, self._tick)
        self.connect("closed", lambda *_: GLib.source_remove(self._tid))

    def _tick(self):
        if self.fetch:
            threading.Thread(target=lambda: GLib.idle_add(self._show, self.fetch()), daemon=True).start()
            return True
        fr = next((x for x in F.cfg()["friends"] if x["addr"] == self.addr), None)
        if fr:
            threading.Thread(target=lambda: GLib.idle_add(self._show, F.fetch_one(fr)), daemon=True).start()
        return True

    def _show(self, d):
        for g in self.groups:
            self.page.remove(g)
        self.groups = []
        head = Adw.PreferencesGroup(title=("🟢 " if d.get("online") else "⚫ ") + (d.get("name") or d.get("friend", "")),
                                    description=_t("På nett") if d.get("online") else
                                    _t("Svarer ikke") + " · " + _t("sist sett") + " " + _ago(d.get("_seen")))
        self.page.add(head)
        self.groups.append(head)
        for title, rows in rows_for(d):
            g = Adw.PreferencesGroup(title=title)
            for k, v in rows:
                r = Adw.ActionRow(title=GLib.markup_escape_text(str(k)))
                lab = Gtk.Label(label=str(v), wrap=True, xalign=1, max_width_chars=34, selectable=True)
                lab.add_css_class("numeric")
                r.add_suffix(lab)
                g.add(r)
            self.page.add(g)
            self.groups.append(g)
        return False


class FriendsPage(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        import theme
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(18)
        self.set_child(Adw.Clamp(maximum_size=theme.PAGE_WIDTH, child=box))

        # ---- vennenes PC-er ----
        top = Gtk.Box(spacing=12)
        info = Gtk.Label(label=_t("Vennenes PC-er – hva de spiller, temperaturer, CPU og minne. Trykk på en PC for "
                                  "alt om den. PC-ene snakker direkte sammen over Tailscale."),
                         xalign=0, wrap=True, hexpand=True)
        info.add_css_class("dim-label")
        top.append(info)
        ref = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text=_t("Oppdater"), valign=Gtk.Align.CENTER)
        ref.add_css_class("flat")
        ref.connect("clicked", lambda *_: self.refresh())
        top.append(ref)
        box.append(top)
        self.flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True, max_children_per_line=3,
                                min_children_per_line=1, column_spacing=12, row_spacing=12)
        box.append(self.flow)

        # ---- legg til venn ----
        c, i = _card("Legg til venn", "Lim inn invitasjonen vennen sendte deg (starter med ks-venn://).")
        row = Gtk.Box(spacing=8)
        self.inv = Gtk.Entry(placeholder_text="ks-venn://…", hexpand=True)
        self.nick = Gtk.Entry(placeholder_text=_t("Navn (valgfritt)"), width_chars=14)
        add = Gtk.Button(label=_t("Legg til"))
        add.add_css_class("suggested-action")
        add.connect("clicked", self._add)
        self.inv.connect("activate", self._add)
        for w in (self.inv, self.nick, add):
            row.append(w)
        i.append(row)
        self.add_msg = Gtk.Label(xalign=0, wrap=True)
        self.add_msg.add_css_class("ks-sub")
        i.append(self.add_msg)
        box.append(c)

        # ---- del min PC ----
        c, i = _card("Del PC-en din med venner",
                     "Vennene ser bare det du velger – de kan ikke styre noe. Lag ny kode for å stenge ute alle "
                     "gamle invitasjoner.")
        cfg = F.cfg()
        r = Gtk.Box(spacing=10)
        r.append(Gtk.Label(label=_t("Del med venner"), xalign=0, hexpand=True))
        self.share = Gtk.Switch(active=cfg["share"], valign=Gtk.Align.CENTER)
        self.share.connect("notify::active", lambda s, _p: (F.set_share(on=s.get_active()), self._show_invite()))
        r.append(self.share)
        i.append(r)
        sr = Gtk.Box(spacing=16)
        for key, label in (("game", "Hva jeg spiller"), ("temps", "Temperaturer, CPU og minne"), ("hw", "Maskinvaren")):
            cb = Gtk.CheckButton(label=_t(label), active=cfg["show"].get(key, True))
            cb.connect("toggled", lambda b, k=key: F.set_share(show={k: b.get_active()}))
            sr.append(cb)
        i.append(sr)
        ir = Gtk.Box(spacing=8)
        self.inv_lab = Gtk.Label(xalign=0, wrap=True, hexpand=True, selectable=True)
        self.inv_lab.add_css_class("monospace")
        self.inv_lab.add_css_class("caption")
        ir.append(self.inv_lab)
        self.copy_b = Gtk.Button(label=_t("Kopier invitasjon"), valign=Gtk.Align.CENTER)
        self.copy_b.connect("clicked", self._copy)
        ir.append(self.copy_b)
        nk = Gtk.Button(label=_t("Ny kode"), valign=Gtk.Align.CENTER)
        nk.connect("clicked", lambda *_: (F.set_share(new_key=True), self._show_invite()))
        ir.append(nk)
        i.append(ir)
        self.ts_lab = Gtk.Label(xalign=0, wrap=True)
        self.ts_lab.add_css_class("ks-sub")
        i.append(self.ts_lab)
        box.append(c)
        self._show_invite()
        self.refresh()
        GLib.timeout_add_seconds(15, lambda: (self.get_mapped() and self.refresh(), True)[1])

    # ------------------------------------------------------------------
    def _show_invite(self):
        def work():
            t = F.tailscale_self()
            inv = F.invite() if F.cfg()["share"] else None
            GLib.idle_add(done, t, inv)

        def done(t, inv):
            self.inv_lab.set_label(inv or (_t("Slå på «Del med venner» for å få en invitasjon") if t["running"] else ""))
            self.copy_b.set_sensitive(bool(inv))
            if not t["running"]:
                self.ts_lab.set_label(_t("Tailscale er ikke på. Venner utenfor huset når PC-en din via Tailscale – "
                                         "slå det på under Innstillinger → Mobil, og del maskinen med vennen i "
                                         "Tailscale («Share»)."))
            else:
                self.ts_lab.set_label(_t("Tailscale: {a}. Del maskinen med vennen i Tailscale (Machines → Share), "
                                         "så kan PC-en deres nå din.").format(a=t["dns"] or t["ip"]))
            return False
        threading.Thread(target=work, daemon=True).start()

    def _copy(self, *_):
        inv = F.invite()
        if inv:
            Gdk.Display.get_default().get_clipboard().set(inv)
            self.copy_b.set_label(_t("Kopiert ✓"))
            GLib.timeout_add_seconds(2, lambda: (self.copy_b.set_label(_t("Kopier invitasjon")), False)[1])

    def _add(self, *_):
        try:
            f = F.add_friend(self.inv.get_text(), self.nick.get_text().strip() or None)
            self.add_msg.set_label(_t("{n} er lagt til – henter PC-en …").format(n=f["name"]))
            self.inv.set_text("")
            self.nick.set_text("")
            self.refresh()
        except ValueError as e:
            self.add_msg.set_label(str(e))

    def refresh(self):
        threading.Thread(target=lambda: GLib.idle_add(self._show, F.fetch_all()), daemon=True).start()
        return False

    def _show(self, fs):
        while (ch := self.flow.get_first_child()) is not None:
            self.flow.remove(ch)
        if not fs:
            import ui
            self.flow.append(ui.empty("ks-friends-symbolic", "Ingen venner ennå",
                                      "Be en venn sende invitasjonen sin, og lim den inn under «Legg til venn».",
                                      compact=False))
            return False
        import machine
        for d in machine.merge_friends(fs):                 # samme maskin (Windows og Linux) = ett kort
            self.flow.append(self._tile(d))
        return False

    def _tile(self, d):
        on = d.get("online")
        b = Gtk.Button()
        b.add_css_class("card")
        b.add_css_class("ks-friend")
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=12, margin_bottom=12,
                        margin_start=14, margin_end=14)
        head = Gtk.Box(spacing=8)
        img = Gtk.Image(icon_name="ks-friends-symbolic", pixel_size=22)
        img.add_css_class("tile-icon" if on else "dim-label")
        head.append(img)
        name = Gtk.Label(label=d.get("friend") or d.get("name") or "?", xalign=0, hexpand=True, ellipsize=3)
        name.add_css_class("heading")
        head.append(name)
        if d.get("systems"):
            import machine
            sysl = Gtk.Label(label="  ·  ".join(f"{machine.os_icon(o)} {o or n}" + (" ●" if s_on else "")
                                                for n, o, s_on in d["systems"]), xalign=0, wrap=True)
            sysl.add_css_class("caption")
            sysl.add_css_class("dim-label")
        else:
            sysl = None
        dot = Gtk.Label(label="● " + (_t("på") if on else _t("av")))
        dot.add_css_class("success" if on else "dim-label")
        head.append(dot)
        inner.append(head)
        if sysl is not None:
            inner.append(sysl)
        if on and d.get("game"):
            g = Gtk.Label(label="🎮 " + d["game"] + (f"  ·  {d['fps']} FPS" if d.get("fps") else ""), xalign=0,
                          ellipsize=3)
            g.add_css_class("ks-chip")
            inner.append(g)
        if on:
            bits = []
            if d.get("cpu_t") is not None:
                bits.append(f"CPU {d['cpu_t']:.0f}°")
            if d.get("gpu_t") is not None:
                bits.append(f"GPU {d['gpu_t']:.0f}°")
            if d.get("ram_used") is not None:
                bits.append(f"{d['ram_used']}/{d.get('ram_total')} GB")
            v = Gtk.Label(label="  ·  ".join(bits) or _t("Deler ikke temperaturer"), xalign=0)
            v.add_css_class("numeric")
            inner.append(v)
        sub = Gtk.Label(label=(d.get("gpu") or d.get("model") or "") if on else
                        (_t("Svarer ikke") + " · " + _t("sist sett") + " " + _ago(d.get("_seen"))),
                        xalign=0, ellipsize=3)
        sub.add_css_class("caption")
        sub.add_css_class("dim-label")
        inner.append(sub)
        b.set_child(inner)
        b.connect("clicked", lambda *_: FriendDialog(d).present(self.get_root()))
        rm = Gtk.GestureClick(button=3)
        rm.connect("pressed", lambda *_: self._remove(d))
        b.add_controller(rm)
        b.set_tooltip_text(_t("Trykk for alt om PC-en · høyreklikk for å fjerne"))
        return b

    def _remove(self, d):
        dlg = Adw.AlertDialog(heading=_t("Fjerne {n}?").format(n=d.get("friend")), body=_t("Du kan legge til igjen senere."))
        dlg.add_response("no", _t("Avbryt"))
        dlg.add_response("yes", _t("Fjern"))
        dlg.set_response_appearance("yes", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.connect("response", lambda _d, r: r == "yes" and (F.remove_friend(d["addr"]), self.refresh()))
        dlg.present(self.get_root())
