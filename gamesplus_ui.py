"""Spill+ på Spill-siden: spillkveld, Discord og lyd per spill, delte profiler, dagbok, toppliste og verktøy."""
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

import gamesplus as G  # noqa: E402
import i18n  # noqa: E402


def _dim(t):
    lab = Gtk.Label(label=i18n.tr(t), xalign=0, wrap=True)
    lab.add_css_class("dim-label")
    lab.add_css_class("caption")
    return lab


def _h(t):
    lab = Gtk.Label(label=i18n.tr(t), xalign=0, margin_top=8)
    lab.add_css_class("heading")
    return lab


def _bg(fn, done):
    def work():
        try:
            r = fn()
        except Exception as e:  # noqa: BLE001
            r = e
        GLib.idle_add(lambda: (done(r), False)[1])
    threading.Thread(target=work, daemon=True).start()


def _btn(label, cb, primary=False):
    b = Gtk.Button(label=i18n.tr(label), valign=Gtk.Align.CENTER)
    b.add_css_class("pill")
    if primary:
        b.add_css_class("suggested-action")
    b.connect("clicked", cb)
    return b


def _last_game():
    try:
        import games_auto
        ss = games_auto.load_sessions()
        return ss[-1]["name"] if ss else None
    except Exception:  # noqa: BLE001
        return None


class GamesPlus(Gtk.Box):
    def __init__(self, win_getter):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.win_getter = win_getter
        self.msg = _dim("")
        # 10 – spillkveld
        self.append(_h("🎮 Spillkveld – hvem spiller nå"))
        self.who = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.append(self.who)
        # 44 / 50 – per spill
        self.append(_h("🔗 Per spill"))
        self.game_lab = _dim("")
        self.append(self.game_lab)
        row = Gtk.Box(spacing=6)
        row.append(_btn("Koble til Discord-kanalen jeg er i", self._link_discord))
        self.audio_dd = Gtk.DropDown.new_from_strings([i18n.tr("(ingen lydprofil)")])
        row.append(self.audio_dd)
        row.append(_btn("Bruk lydprofilen", self._link_audio))
        self.append(row)
        drow = Gtk.Box(spacing=6)
        self.dpi = Gtk.SpinButton.new_with_range(0, 25600, 100)
        self.dpi.set_tooltip_text(i18n.tr("0 = ikke endre"))
        drow.append(Gtk.Label(label=i18n.tr("Mus-DPI for spillet (Logitech/Solaar)"), xalign=0, hexpand=True))
        drow.append(self.dpi)
        drow.append(_btn("Lagre DPI", self._save_dpi))
        self.append(drow)
        self.append(_h("📦 Spill på de andre PC-ene"))
        self.elsewhere = _dim("…")
        self.append(self.elsewhere)
        self.append(_btn("Slå på lokale overføringer i Steam", lambda _b: self.msg.set_label(
            __import__("equipment").open_steam_lan_setting())))
        # 15 – delte profiler
        self.append(_h("📤 Delte spillprofiler (NAS)"))
        self.append(_dim("Startvalg og Proton for et spill – del ditt, eller bruk et som virker godt på en annen PC."))
        self.prof = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.append(self.prof)
        self.append(_btn("Del oppsettet for sist spilte", self._share))
        # 69 / 71
        self.append(_h("📖 Spill-dagbok"))
        self.diary = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.append(self.diary)
        self.append(_h("🏆 Husets toppliste denne uka"))
        self.top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.append(self.top)
        # 53 – smart oppstart
        self.append(_h("🚀 Smart oppstart"))
        self.smart = _dim("")
        self.append(self.smart)
        # 40 / 22 – verktøy
        self.append(_h("🛠️ Verktøy"))
        tr = Gtk.Box(spacing=6)
        tr.append(_btn("Finn beste FPS-grense (spillet må kjøre)", self._tune))
        self.pre_dd = Gtk.DropDown.new_from_strings([i18n.tr("(velg spill)")])
        tr.append(self.pre_dd)
        tr.append(_btn("Forvarm shadere", self._prewarm))
        self.append(tr)
        self.append(_dim("Finn beste FPS-grense prøver noen grenser i 30 sekunder hver mens du spiller (Linux med "
                         "MangoHud). Forvarm shadere starter spillet i 2 minutter og lukker det igjen."))
        # brytere
        self.append(_h("⚙️ Innstillinger"))
        c = G.cfg()
        for key, title, sub in (("ping_watch", "Ping-vakt", "Sier fra inni spillet når pingen blir dårlig – og om "
                                                            "det er Wi-Fi/ruteren eller internett."),
                                ("lightshow", "Lysshow ved høydepunkter", "RGB og Hue blinker ved ace og bosskill."),
                                ("predict", "Forutsi spillkvelden", "«Du pleier å spille nå» 10 min før."),
                                ("predict_prep", "Gjør klart av seg selv", "Max Ytelse og start Steam og Discord når "
                                                                          "spillkvelden pleier å starte."),
                                ("smart_start", "Start de vanlige programmene ved innlogging",
                                 "Det Kontrollsenter har lært at du alltid åpner."),
                                ("dnd_meetings", "Ikke forstyrr i møter", "Varsler holdes tilbake mens Teams, Zoom "
                                                                         "eller Webex kjører – vises samlet etterpå.")):
            r = Gtk.Box(spacing=12)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            col.append(Gtk.Label(label=i18n.tr(title), xalign=0))
            col.append(_dim(sub))
            r.append(col)
            sw = Gtk.Switch(active=bool(c[key]), valign=Gtk.Align.CENTER)
            sw.connect("notify::active", lambda w, _p, k=key: G.set_(**{k: w.get_active()}))
            r.append(sw)
            self.append(r)
        self.append(self.msg)
        self._audio_ids = []
        self._games = []
        self.refresh()
        GLib.timeout_add_seconds(60, lambda: (self.get_mapped() and self.refresh(), True)[1])

    @staticmethod
    def _clear(b):
        while (c := b.get_first_child()) is not None:
            b.remove(c)

    def refresh(self):
        def load():
            import avprofiles
            import launcher
            import equipment
            return (G.who_plays(), G.diary(12), G.house_toplist(), G.startup_suggestions(),
                    avprofiles.cfg().get("audio", []), [g["name"] for g in launcher.all_games()][:60],
                    G.shared_profiles(), equipment.games_elsewhere())
        _bg(load, self._show)
        return False

    def _show(self, r):
        if isinstance(r, Exception):
            self.msg.set_label(f"Feil: {r}")
            return
        who, diary, top, sugg, audio, games, profs, elsewhere = r
        try:
            import gamestats
            names = {aid: gamestats.nice_name(aid, aid) for aid in list(elsewhere)[:12]}
        except Exception:  # noqa: BLE001
            names = {}
        self.elsewhere.set_label(
            "\n".join(f"{names.get(a, a)} – finnes på {', '.join(p)}" for a, p in list(elsewhere.items())[:12]) +
            "\n\n" + i18n.tr("Med «lokale overføringer» på henter Steam disse fra PC-en hjemme i stedet for internett – "
                               "mye raskere.") if elsewhere else
            i18n.tr("Ingen spill her som mangler – eller de andre PC-ene har ikke delt listen ennå (kommer med 0.81)."))
        self._clear(self.who)
        if not who:
            self.who.append(_dim("Ingen hjemme eller blant vennene spiller akkurat nå."))
        for name, game, where in who:
            row = Gtk.Box(spacing=8)
            row.append(Gtk.Label(label=f"{'🏠' if where == 'hjemme' else '🌍'} {name}: {game}", xalign=0,
                                 hexpand=True))
            row.append(_btn("Spill sammen", lambda _b, g=game: self._together(g), True))
            self.who.append(row)
        lg = _last_game()
        self._target = lg
        c = G.cfg()
        self.game_lab.set_label(i18n.tr("Sist spilte: ") + (lg or "–") +
                                (" · Discord-kanal koblet" if lg and c["discord_map"].get(lg) else "") +
                                (" · lydprofil koblet" if lg and c["audio_map"].get(lg) else ""))
        self._audio_ids = [a["id"] for a in audio]
        self.audio_dd.set_model(Gtk.StringList.new([i18n.tr("(ingen lydprofil)")] +
                                                   [f"{a.get('icon', '')} {a['name']}" for a in audio]))
        self._clear(self.prof)
        for p in profs[:10]:
            row = Gtk.Box(spacing=8)
            row.append(Gtk.Label(label=f"{p.get('name')} – {p.get('by')}", xalign=0, hexpand=True))
            row.append(_btn("Bruk", lambda _b, pp=p: self._use(pp)))
            self.prof.append(row)
        if not profs:
            self.prof.append(_dim("Ingen delte profiler ennå."))
        self._clear(self.diary)
        for t, icon, text in diary:
            self.diary.append(Gtk.Label(label=f"{icon} {time.strftime('%d.%m', time.localtime(t))}  {text}",
                                        xalign=0, wrap=True))
        if not diary:
            self.diary.append(_dim("Spill litt, så fylles dagboka av seg selv."))
        self._clear(self.top)
        for i, (g, h, pcs) in enumerate(top):
            self.top.append(Gtk.Label(label=f"{i + 1}. {g} – {h:.1f} t ({', '.join(pcs)})", xalign=0, wrap=True))
        if not top:
            self.top.append(_dim("Ingen spilletid denne uka ennå."))
        try:
            import apps
            names = [apps.APPS[k]["name"] for k in sugg if k in apps.APPS]
        except Exception:  # noqa: BLE001
            names = sugg
        self.smart.set_label(i18n.tr("Du åpner nesten alltid: ") + ", ".join(names) if names else
                             i18n.tr("Lærer fortsatt hva du pleier å åpne etter innlogging (trenger noen oppstarter)."))
        try:
            import equipment
            self.dpi.set_value(equipment.cfg()["dpi_map"].get(lg or "", 0))
        except Exception:  # noqa: BLE001
            pass
        self._games = games
        self.pre_dd.set_model(Gtk.StringList.new([i18n.tr("(velg spill)")] + games))

    def _together(self, game):
        _bg(lambda: G.play_together(self.win_getter(), game), lambda r: self.msg.set_label(str(r)))

    def _link_discord(self, *_):
        def work():
            import discord_ctl as DC
            ch = DC.state().get("channel")
            if not ch:
                raise RuntimeError("gå inn i en talekanal i Discord først (og koble Discord til i Discord-siden)")
            if not self._target:
                raise RuntimeError("spill et spill først")
            m = G.cfg()["discord_map"]
            m[self._target] = ch["id"]
            G.set_(discord_map=m)
            return f"{self._target} → #{ch.get('name')} ✓"
        _bg(work, lambda r: (self.msg.set_label(str(r)), self.refresh()))

    def _link_audio(self, *_):
        i = self.audio_dd.get_selected()
        if not self._target:
            self.msg.set_label(i18n.tr("Spill et spill først"))
            return
        m = G.cfg()["audio_map"]
        if i == 0:
            m.pop(self._target, None)
        else:
            m[self._target] = self._audio_ids[i - 1]
        G.set_(audio_map=m)
        self.msg.set_label(f"{self._target}: " + (i18n.tr("ingen lydprofil") if i == 0 else i18n.tr("lydprofil koblet ✓")))
        self.refresh()

    def _save_dpi(self, *_):
        import equipment
        if not self._target:
            self.msg.set_label(i18n.tr("Spill et spill først"))
            return
        m = equipment.cfg()["dpi_map"]
        v = int(self.dpi.get_value())
        if v:
            m[self._target] = v
        else:
            m.pop(self._target, None)
        equipment.set_(dpi_map=m)
        self.msg.set_label(f"{self._target}: " + (f"{v} DPI når spillet starter ✓" if v else i18n.tr("DPI endres ikke")))

    def _share(self, *_):
        def work():
            import games
            if not self._target:
                raise RuntimeError("spill et spill først")
            g = next((x for x in games.installed_games() if x["name"] == self._target), None)
            if not g:
                raise RuntimeError("bare Steam-spill kan deles")
            return G.share_profile(g["appid"], g["name"])
        _bg(work, lambda r: (self.msg.set_label(str(r)), self.refresh()))

    def _use(self, p):
        _bg(lambda: G.use_profile(p), lambda r: self.msg.set_label(str(r)))

    def _tune(self, *_):
        self.msg.set_label(i18n.tr("Prøver FPS-grenser … fortsett å spille (ca. 3–4 min)"))

        def prog(f, t):
            GLib.idle_add(self.msg.set_label, f"{t} … ({f * 100:.0f} %)")
        _bg(lambda: G.tune_fps(self.win_getter(), prog), lambda r: self.msg.set_label(
            r["text"] if isinstance(r, dict) else str(r)))

    def _prewarm(self, *_):
        i = self.pre_dd.get_selected()
        if i == 0:
            self.msg.set_label(i18n.tr("Velg et spill først"))
            return
        g = self._games[i - 1]
        self.msg.set_label(f"Forvarmer {g} … (2 min)")
        _bg(lambda: G.prewarm(g), lambda r: self.msg.set_label(str(r)))
