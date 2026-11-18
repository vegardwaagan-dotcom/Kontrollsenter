"""Fanen «Familie»: familiekontroll (kode), «Se på» skjermen til de andre PC-ene, og familiekortet (chat,
«Middag!», ekstra spilletid, leggetid)."""
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

import familylock  # noqa: E402
import i18n  # noqa: E402
import theme  # noqa: E402

STALE = 15 * 60


def _card(title, desc):
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    outer.add_css_class("card")
    inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    for side, v in (("top", 18), ("bottom", 18), ("start", 20), ("end", 20)):
        getattr(inner, f"set_margin_{side}")(v)
    outer.append(inner)
    h = Gtk.Label(label=i18n.tr(title), xalign=0)
    h.add_css_class("title-4")
    inner.append(h)
    d = Gtk.Label(label=i18n.tr(desc), xalign=0, wrap=True)
    d.add_css_class("ks-desc")
    inner.append(d)
    return outer, inner


class FamilyPage(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(18)
        self.set_child(Adw.Clamp(maximum_size=theme.PAGE_WIDTH, child=box))

        # ---- familiekontroll ----
        c, i = _card("Familiekontroll",
                     "Velg en kode som trengs for å lukke Kontrollsenter på denne PC-en. Lukkes vinduet, fortsetter "
                     "programmet i bakgrunnen. Koden beskytter også familieinnstillingene, ekstra spilletid og "
                     "bakgrunn/oppstart. Glemt koden? Slå den av fra telefonen (Spill → Familie).")
        box.append(c)
        r = Gtk.Box(spacing=16)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
        self.lock_title = Gtk.Label(xalign=0)
        self.lock_title.add_css_class("heading")
        col.append(self.lock_title)
        self.lock_sub = Gtk.Label(xalign=0, wrap=True)
        self.lock_sub.add_css_class("ks-sub")
        col.append(self.lock_sub)
        r.append(col)
        self.lock_sw = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.lock_sw.connect("notify::active", self._lock_toggle)
        r.append(self.lock_sw)
        i.append(r)
        self.chg = Gtk.Button(label=i18n.tr("Bytt kode"), halign=Gtk.Align.START)
        self.chg.connect("clicked", self._change)
        i.append(self.chg)
        self.msg = Gtk.Label(xalign=0, wrap=True)
        self.msg.add_css_class("ks-sub")
        i.append(self.msg)

        # ---- se på ----
        c, i = _card("Se på skjermen til de andre PC-ene",
                     "Som å caste fra Meta Quest: se live hva som skjer på en annen PC i huset. Bare visning – ingen "
                     "kan styre PC-en, og den som blir sett på får beskjed. Fra telefonen: «📺 Se på» på Hjem.")
        box.append(c)
        self.watch_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        i.append(self.watch_list)

        # ---- chat, middag, belønning, leggetid ----
        try:
            import family_ui
            box.append(family_ui.FamilyCard())
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("familie-kort")

        # ---- mål og belønning ----
        c, i = _card("Mål og belønning",
                     "Ferdig med lekser? Trykk, så får foreldrene beskjed på telefonen – godkjenner de, får du ekstra "
                     "spilletid i dag med en gang.")
        box.append(c)
        gb = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=4, min_children_per_line=2,
                         column_spacing=10, row_spacing=10, homogeneous=True)
        import features as F
        for g in F.goals()["goals"]:
            b = Gtk.Button()
            b.add_css_class("ks-goal")
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            ic = Gtk.Label(label=g["icon"])
            ic.add_css_class("title-1")
            col.append(ic)
            col.append(Gtk.Label(label=i18n.tr(g["name"]), wrap=True, justify=Gtk.Justification.CENTER))
            sub = Gtk.Label(label=f"+{g['minutes']} min")
            sub.add_css_class("dim-label")
            sub.add_css_class("caption")
            col.append(sub)
            b.set_child(col)
            b.connect("clicked", lambda _b, gid=g["id"]: self._goal(gid))
            gb.append(b)
        i.append(gb)
        self.goal_msg = Gtk.Label(xalign=0, wrap=True)
        self.goal_msg.add_css_class("ks-sub")
        i.append(self.goal_msg)
        self.goal_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        i.append(self.goal_list)
        vr = Gtk.Box(spacing=12, margin_top=6)
        vl = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        vl.append(Gtk.Label(label=i18n.tr("Tell YouTube og Twitch som skjermtid"), xalign=0))
        vs = Gtk.Label(label=i18n.tr("Video i nettleseren telles i spilletiden og grensene (ikke mens et spill kjører)."),
                       xalign=0, wrap=True)
        vs.add_css_class("ks-sub")
        vl.append(vs)
        vr.append(vl)
        sw = Gtk.Switch(active=F.cfg().get("count_video", True), valign=Gtk.Align.CENTER)

        def set_video(w, _p):
            def do():
                c = F.cfg()
                c["count_video"] = w.get_active()
                F.save_cfg(c)
            if not w.get_active() and familylock.locked() and not getattr(w, "_rev", False):
                def cancel():
                    w._rev = True
                    w.set_active(True)
                    w._rev = False
                familylock.ask(self.get_root(), "Skriv familiekoden for å slå av dette.", do, cancel)
            else:
                do()
        sw.connect("notify::active", set_video)
        vr.append(sw)
        i.append(vr)

        # ---- ukeplan ----
        c, i = _card("Ukeplan", "Felles for hele huset (ligger på NAS-en). Hver PC minner om avtalene sine – f.eks. "
                                "«Fotballtrening 17:30» med varsel 15 minutter før, så rekker man å lagre spillet.")
        box.append(c)
        form = Gtk.Box(spacing=6)
        import familyplus
        self.p_day = Gtk.DropDown.new_from_strings([i18n.tr(d) for d in familyplus.DAYS])
        self.p_day.set_selected(time.localtime().tm_wday)
        self.p_at = Gtk.Entry(text="17:00", width_chars=5, max_length=5)
        self.p_text = Gtk.Entry(placeholder_text=i18n.tr("Hva skjer? (f.eks. Fotballtrening)"), hexpand=True)
        self.p_who = Gtk.Entry(placeholder_text=i18n.tr("Hvem (tomt = alle)"), width_chars=12)
        add = Gtk.Button(label=i18n.tr("Legg til"))
        add.add_css_class("suggested-action")
        add.connect("clicked", lambda *_: self._plan_add())
        for w in (self.p_day, self.p_at, self.p_text, self.p_who, add):
            form.append(w)
        i.append(form)
        self.plan_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        i.append(self.plan_box)

        # ---- belønningsbutikk ----
        c, i = _card("Belønningsbutikk", "Hvert godkjente mål gir stjerner (1 ⭐ per 5 minutter). Stjernene kan løses "
                                         "inn her – en voksen må godkjenne.")
        box.append(c)
        self.shop_head = Gtk.Label(xalign=0)
        self.shop_head.add_css_class("title-3")
        i.append(self.shop_head)
        self.shop_flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=3,
                                     min_children_per_line=2, column_spacing=10, row_spacing=10, homogeneous=True)
        i.append(self.shop_flow)
        self.shop_msg = Gtk.Label(xalign=0, wrap=True)
        self.shop_msg.add_css_class("ks-sub")
        i.append(self.shop_msg)
        self.shop_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        i.append(self.shop_list)

        # ---- ukesrapport og ranking ----
        c, i = _card("Ukesrapport og ranking", "Spilletid per person, mest spilte spill og strøm denne uka – for alle "
                                               "PC-ene i huset. Kommer også som varsel søndag kveld.")
        box.append(c)
        self.week_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.week_box.append(Gtk.Label(label=i18n.tr("Henter …"), xalign=0))
        i.append(self.week_box)

        self._busy = False
        self._show_lock()
        self._show_goals()
        self._load_week()
        self._load_plan()
        self._show_shop()
        self.refresh()
        GLib.timeout_add_seconds(30, lambda: (self.get_mapped() and (self.refresh(), self._show_goals(),
                                                                     self._show_shop()), True)[1])

    # ---- familiekontroll ----
    def _show_lock(self):
        self._busy = True
        on = familylock.locked()
        self.lock_sw.set_active(on)
        self.lock_title.set_label(i18n.tr("Kode for å lukke Kontrollsenter") + (" – " + i18n.tr("på") if on else ""))
        self.lock_sub.set_label(i18n.tr("Kontrollsenter kan bare lukkes med koden." if on else
                                        "Av – alle kan lukke Kontrollsenter."))
        self.chg.set_visible(on)
        self._busy = False

    def _lock_toggle(self, sw, _p):
        if self._busy:
            return
        if sw.get_active() and not familylock.locked():
            familylock.ask_new_pin(self.get_root(), lambda ok: (self.msg.set_label(
                i18n.tr("Familiekontroll er på ✓") if ok else ""), self._show_lock()))
        elif not sw.get_active() and familylock.locked():
            familylock.ask(self.get_root(), "Skriv koden for å slå av familiekontroll.",
                           lambda: (familylock.turn_off(), self.msg.set_label(i18n.tr("Familiekontroll er av")),
                                    self._show_lock()), self._show_lock)

    def _change(self, *_):
        familylock.ask(self.get_root(), "Skriv den nåværende koden.",
                       lambda: familylock.ask_new_pin(self.get_root(), lambda ok: self.msg.set_label(
                           i18n.tr("Ny kode er lagret ✓") if ok else "")))

    # ---- se på ----
    # ---- mål ----
    def _goal(self, gid):
        import features as F
        try:
            self.goal_msg.set_label(i18n.tr(F.goal_request(gid, "PC-en")))
        except Exception as e:  # noqa: BLE001
            self.goal_msg.set_label(str(e))
        self._show_goals()

    def _show_goals(self):
        import features as F
        while (ch := self.goal_list.get_first_child()) is not None:
            self.goal_list.remove(ch)
        g = F.goals()
        for r in g["pending"]:
            row = Gtk.Box(spacing=10)
            row.append(Gtk.Label(label=f"{r['icon']} {r['name']} · +{r['minutes']} min · {r.get('by', '')}",
                                 xalign=0, hexpand=True, wrap=True))
            for lab, ok in (("Godkjenn", True), ("Avslå", False)):
                b = Gtk.Button(label=i18n.tr(lab))
                if ok:
                    b.add_css_class("suggested-action")
                b.connect("clicked", lambda _b, rid=r["id"], ok=ok: self._answer(rid, ok))
                row.append(b)
            self.goal_list.append(row)
        for r in reversed(g["done"][-3:]):
            lab = Gtk.Label(label=f"{r['icon']} {r['name']} – {r['state']}", xalign=0)
            lab.add_css_class("dim-label")
            self.goal_list.append(lab)
        return False

    def _answer(self, rid, ok):
        import features as F

        def do():
            try:
                self.goal_msg.set_label(i18n.tr(F.goal_answer(rid, ok)))
            except Exception as e:  # noqa: BLE001
                self.goal_msg.set_label(str(e))
            self._show_goals()
        if familylock.locked():                         # barna kan ikke godkjenne sine egne
            familylock.ask(self.get_root(), "Skriv familiekoden for å svare.", do, lambda: None)
        else:
            do()

    # ---- ukeplan ----
    def _load_plan(self, max_age=600):
        def work():
            import familyplus
            try:
                p, err = familyplus.load_plan(max_age), None
            except Exception as e:  # noqa: BLE001
                p, err = {"items": []}, str(e)
            GLib.idle_add(self._show_plan, p, err)
        threading.Thread(target=work, daemon=True).start()
        return False

    def _show_plan(self, plan, err=None):
        import familyplus
        while (ch := self.plan_box.get_first_child()) is not None:
            self.plan_box.remove(ch)
        today = time.localtime().tm_wday
        if err:
            self.plan_box.append(Gtk.Label(label=err, xalign=0))
        if not plan["items"]:
            lab = Gtk.Label(label=i18n.tr("Ingen avtaler ennå."), xalign=0)
            lab.add_css_class("dim-label")
            self.plan_box.append(lab)
        last = None
        for x in plan["items"]:
            if x["day"] != last:
                last = x["day"]
                h = Gtk.Label(label=i18n.tr(familyplus.DAYS[x["day"]]) + (" · " + i18n.tr("i dag") if x["day"] == today else ""),
                              xalign=0, margin_top=6)
                h.add_css_class("heading")
                self.plan_box.append(h)
            row = Gtk.Box(spacing=10)
            who = "" if x.get("who") in ("*", "", None) else f" · {x['who']}"
            row.append(Gtk.Label(label=f"{x['at']}  {x['text']}{who}", xalign=0, hexpand=True, wrap=True))
            sub = Gtk.Label(label=f"🔔 {x.get('remind', 10)} min")
            sub.add_css_class("dim-label")
            row.append(sub)
            rm = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text=i18n.tr("Fjern"))
            rm.add_css_class("flat")
            rm.connect("clicked", lambda _b, iid=x["id"]: self._plan_do(lambda: familyplus.plan_del(iid)))
            row.append(rm)
            self.plan_box.append(row)
        return False

    def _plan_add(self):
        import familyplus
        day, at = self.p_day.get_selected(), self.p_at.get_text().strip()
        text, who = self.p_text.get_text(), self.p_who.get_text().strip() or "*"
        self._plan_do(lambda: familyplus.plan_add(day, at, text, who, 15))
        self.p_text.set_text("")

    def _plan_do(self, fn):
        def work():
            try:
                msg = fn()
            except Exception as e:  # noqa: BLE001
                msg = str(e)
            GLib.idle_add(lambda: (self.msg.set_label(i18n.tr(msg)), self._load_plan(0), False)[2])
        threading.Thread(target=work, daemon=True).start()

    # ---- butikk ----
    def _show_shop(self):
        import familyplus
        s = familyplus.shop()
        self.shop_head.set_label(f"⭐ {s['stars']} " + i18n.tr("stjerner"))
        while (ch := self.shop_flow.get_first_child()) is not None:
            self.shop_flow.remove(ch)
        for it in s["items"]:
            b = Gtk.Button()
            b.add_css_class("ks-goal")
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            ic = Gtk.Label(label=it["icon"])
            ic.add_css_class("title-1")
            col.append(ic)
            col.append(Gtk.Label(label=i18n.tr(it["name"]), wrap=True, justify=Gtk.Justification.CENTER))
            pr = Gtk.Label(label=f"{it['price']} ⭐")
            pr.add_css_class("dim-label")
            col.append(pr)
            b.set_child(col)
            b.set_sensitive(s["stars"] >= it["price"])
            b.connect("clicked", lambda _b, iid=it["id"]: self._shop_req(iid))
            self.shop_flow.append(b)
        while (ch := self.shop_list.get_first_child()) is not None:
            self.shop_list.remove(ch)
        for r in s["pending"]:
            row = Gtk.Box(spacing=10)
            row.append(Gtk.Label(label=f"{r['icon']} {r['name']} · {r['price']} ⭐ · {r.get('by', '')}",
                                 xalign=0, hexpand=True, wrap=True))
            for lab, ok in (("Godkjenn", True), ("Avslå", False)):
                bb = Gtk.Button(label=i18n.tr(lab))
                if ok:
                    bb.add_css_class("suggested-action")
                bb.connect("clicked", lambda _b, rid=r["id"], ok=ok: self._shop_answer(rid, ok))
                row.append(bb)
            self.shop_list.append(row)
        return False

    def _shop_req(self, iid):
        import familyplus
        try:
            self.shop_msg.set_label(i18n.tr(familyplus.shop_request(iid, "PC-en")))
        except Exception as e:  # noqa: BLE001
            self.shop_msg.set_label(str(e))
        self._show_shop()

    def _shop_answer(self, rid, ok):
        import familyplus

        def do():
            try:
                self.shop_msg.set_label(i18n.tr(familyplus.shop_answer(rid, ok)))
            except Exception as e:  # noqa: BLE001
                self.shop_msg.set_label(str(e))
            self._show_shop()
        if familylock.locked():
            familylock.ask(self.get_root(), "Skriv familiekoden for å svare.", do, lambda: None)
        else:
            do()

    # ---- ukesrapport ----
    def _load_week(self):
        def work():
            try:
                import features as F
                r, fam = F.weekly_report(), F.family()
            except Exception as e:  # noqa: BLE001
                r, fam = {"error": str(e)}, {}
            GLib.idle_add(self._show_week, r, fam)
        threading.Thread(target=work, daemon=True).start()
        return False

    def _show_week(self, r, fam):
        while (ch := self.week_box.get_first_child()) is not None:
            self.week_box.remove(ch)
        if r.get("error") or not r.get("rows"):
            self.week_box.append(Gtk.Label(label=i18n.tr("Ingen tall ennå – PC-ene deler status på hjemmenettet hvert "
                                                         "5. minutt."), xalign=0, wrap=True))
            return False
        hm = lambda s: f"{int(s) // 3600} t {int(s) % 3600 // 60} min"  # noqa: E731
        top = max(x["play_s"] for x in r["rows"]) or 1
        for x in r["rows"]:
            row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            head = Gtk.Box(spacing=8)
            nm = Gtk.Label(label=x["name"], xalign=0, hexpand=True)
            nm.add_css_class("heading")
            head.append(nm)
            head.append(Gtk.Label(label=hm(x["play_s"])))
            row.append(head)
            bar = Gtk.LevelBar(min_value=0, max_value=1, value=x["play_s"] / top)
            bar.set_size_request(-1, 8)
            row.append(bar)
            extra = [f"mest {x['top']}" if x["top"] else None, f"{x['sessions']} økter" if x["sessions"] else None,
                     f"lengste {x['longest']} min" if x["longest"] else None,
                     f"{x['kwh']} kWh" if x.get("kwh") else None]
            sub = Gtk.Label(label=" · ".join(e for e in extra if e), xalign=0)
            sub.add_css_class("dim-label")
            sub.add_css_class("caption")
            row.append(sub)
            self.week_box.append(row)
        if r.get("top_games"):
            lab = Gtk.Label(label=i18n.tr("Mest spilt i huset: ") + ", ".join(f"{g} ({hm(v)})" for g, v in r["top_games"][:3]),
                            xalign=0, wrap=True)
            self.week_box.append(lab)
        grid = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=3, min_children_per_line=1,
                           column_spacing=16, row_spacing=10)
        for title, rows in (fam.get("ranking") or {}).items():
            if not rows:
                continue
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            t = Gtk.Label(label=i18n.tr(title), xalign=0)
            t.add_css_class("caption-heading")
            col.append(t)
            for n, (name, v) in enumerate(rows[:3]):
                col.append(Gtk.Label(label=f"{['🥇', '🥈', '🥉'][n]} {name}  ·  {v}", xalign=0))
            grid.append(col)
        self.week_box.append(grid)
        return False

    def refresh(self):
        def work():
            try:
                import homepcs
                import savegames
                pcs, me = homepcs.fetch() or [], savegames.pc_name()
            except Exception:  # noqa: BLE001
                pcs, me = [], ""
            GLib.idle_add(self._show_pcs, pcs, me)
        threading.Thread(target=work, daemon=True).start()
        return False

    def _show_pcs(self, pcs, me):
        while (ch := self.watch_list.get_first_child()) is not None:
            self.watch_list.remove(ch)
        others = [p for p in pcs if p.get("name") and p["name"] != me]
        if not others:
            lab = Gtk.Label(label=i18n.tr("Fant ingen andre PC-er på hjemmenettet ennå."), xalign=0)
            lab.add_css_class("ks-sub")
            self.watch_list.append(lab)
        for p in others:
            on = time.time() - (p.get("time") or 0) < STALE and not p.get("off")
            row = Gtk.Box(spacing=14)
            img = Gtk.Image(icon_name="ks-lcd-symbolic", pixel_size=22, valign=Gtk.Align.CENTER)
            img.add_css_class("tile-icon" if on else "dim-label")
            row.append(img)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True, valign=Gtk.Align.CENTER)
            t = Gtk.Label(label=p["name"], xalign=0)
            t.add_css_class("heading")
            col.append(t)
            if not on:
                why = i18n.tr("Av")
            elif p.get("watch"):
                why = ("🎮 " + p["game"]) if p.get("game") else i18n.tr("Ingen spill nå")
            elif "watch" not in p:
                why = i18n.tr("Trenger Kontrollsenter 0.16 eller nyere – oppdater og start den på nytt")
            else:
                why = i18n.tr("Deling er slått av på den PC-en (eller fjernstyring er av)")
            s = Gtk.Label(label=why, xalign=0, wrap=True)
            s.add_css_class("ks-sub")
            col.append(s)
            row.append(col)
            b = Gtk.Button(label="📺 " + i18n.tr("Se på"), valign=Gtk.Align.CENTER,
                           sensitive=bool(on and p.get("watch") and p.get("ips")))
            if p.get("game"):
                b.add_css_class("suggested-action")
            b.connect("clicked", lambda _b, pp=p: __import__("watch_ui").WatchWindow(
                self.get_root(), pp["name"], pp["ips"][0], pp.get("game")).present())
            row.append(b)
            self.watch_list.append(row)
        return False
