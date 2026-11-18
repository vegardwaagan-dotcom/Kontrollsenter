"""Programmer-fanen i Kontrollsenter: installer faste programmer med ett klikk (Flatpak/Flathub).

* «Mine programmer»: din egen liste (fylles første gang med det som er installert nå).
  «Installer alle mine» setter opp en ny PC med alt du bruker.
* «Katalog»: populære programmer i kategorier.
* «Søk»: hele Flathub.
Listen kan eksporteres til programmer.json og importeres på en annen PC
(installer.sh installerer den også automatisk hvis filen ligger i pakken).
"""
import json
import os
import queue
import shutil
import subprocess
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

LIST_FILE = Path.home() / ".config/systemmonitor/programmer.json"
ICON_DIRS = [Path("/var/lib/flatpak/appstream/flathub/x86_64/active/icons/128x128"),
             Path.home() / ".local/share/flatpak/appstream/flathub/x86_64/active/icons/128x128",
             Path("/var/lib/flatpak/exports/share/icons/hicolor/128x128/apps"),
             Path.home() / ".local/share/flatpak/exports/share/icons/hicolor/128x128/apps"]

# (flatpak-id, navn, beskrivelse, kategori, kommando hvis det også finnes som systempakke)
CATALOG = [
    ("com.valvesoftware.Steam", "Steam", "Spillbutikk og -bibliotek", "Spill", "steam"),
    ("net.lutris.Lutris", "Lutris", "Spill fra Battle.net, Epic, GOG m.m.", "Spill", "lutris"),
    ("com.heroicgameslauncher.hgl", "Heroic", "Epic, GOG og Amazon Games", "Spill", None),
    ("com.usebottles.bottles", "Bottles", "Kjør Windows-programmer", "Spill", None),
    ("com.vysp3r.ProtonPlus", "ProtonPlus", "Installer Proton-GE og andre Proton-versjoner", "Spill", None),
    ("net.davidotek.pupgui2", "ProtonUp-Qt", "Installer Proton-GE og Wine-GE", "Spill", None),
    ("com.github.Matoking.protontricks", "Protontricks", "Fiks Proton-spill (winetricks)", "Spill", None),
    ("org.prismlauncher.PrismLauncher", "Prism Launcher", "Minecraft med modpakker", "Spill", None),
    ("com.mojang.Minecraft", "Minecraft Launcher", "Offisiell Minecraft", "Spill", None),
    ("com.overwolf.curseforge", "CurseForge", "Mods og modpakker", "Spill", None),
    ("org.vinegarhq.Sober", "Sober", "Roblox på Linux", "Spill", None),
    ("org.libretro.RetroArch", "RetroArch", "Emulator for retrospill", "Spill", None),
    ("io.github.ryubing.Ryujinx", "Ryujinx", "Nintendo Switch-emulator", "Spill", None),
    ("org.DolphinEmu.dolphin-emu", "Dolphin", "GameCube/Wii-emulator", "Spill", None),
    ("com.moonlight_stream.Moonlight", "Moonlight", "Strøm spill fra en annen PC", "Spill", None),
    ("dev.lizardbyte.app.Sunshine", "Sunshine", "Strøm spill fra denne PC-en", "Spill", None),
    ("com.discordapp.Discord", "Discord", "Tale- og tekstchat", "Kommunikasjon", None),
    ("dev.vencord.Vesktop", "Vesktop", "Discord med bedre skjermdeling på Linux", "Kommunikasjon", None),
    ("org.telegram.desktop", "Telegram", "Meldinger", "Kommunikasjon", None),
    ("org.signal.Signal", "Signal", "Sikre meldinger", "Kommunikasjon", None),
    ("com.teamspeak.TeamSpeak", "TeamSpeak", "Talechat for spill", "Kommunikasjon", None),
    ("org.mozilla.Thunderbird", "Thunderbird", "E-post", "Kommunikasjon", None),
    ("org.mozilla.firefox", "Firefox", "Nettleser", "Nettlesere", "firefox"),
    ("com.google.Chrome", "Google Chrome", "Nettleser", "Nettlesere", None),
    ("com.brave.Browser", "Brave", "Nettleser med reklameblokkering", "Nettlesere", None),
    ("com.vivaldi.Vivaldi", "Vivaldi", "Nettleser", "Nettlesere", None),
    ("com.microsoft.Edge", "Microsoft Edge", "Nettleser", "Nettlesere", None),
    ("com.spotify.Client", "Spotify", "Musikk", "Media", None),
    ("org.videolan.VLC", "VLC", "Spiller alt av video og lyd", "Media", None),
    ("org.kde.haruna", "Haruna", "Videospiller", "Media", None),
    ("com.obsproject.Studio", "OBS Studio", "Opptak og strømming", "Media", None),
    ("org.gimp.GIMP", "GIMP", "Bilderedigering", "Media", None),
    ("org.kde.kdenlive", "Kdenlive", "Videoredigering", "Media", None),
    ("org.audacityteam.Audacity", "Audacity", "Lydredigering", "Media", None),
    ("org.kde.gwenview", "Gwenview", "Bildeviser", "Media", None),
    ("org.libreoffice.LibreOffice", "LibreOffice", "Kontorpakke (Word/Excel-alternativ)", "Kontor", None),
    ("org.onlyoffice.desktopeditors", "ONLYOFFICE", "Kontorpakke med god MS Office-støtte", "Kontor", None),
    ("org.kde.okular", "Okular", "PDF-leser", "Kontor", None),
    ("org.kde.kcalc", "KCalc", "Kalkulator", "Kontor", None),
    ("com.bitwarden.desktop", "Bitwarden", "Passordbehandler", "Kontor", None),
    ("com.visualstudio.code", "Visual Studio Code", "Kodeeditor", "Kontor", None),
    ("com.github.tchx84.Flatseal", "Flatseal", "Tillatelser for Flatpak-programmer", "Verktøy", None),
    ("io.github.flattool.Warehouse", "Warehouse", "Administrer Flatpak-programmer", "Verktøy", None),
    ("it.mijorus.gearlever", "Gear Lever", "Installer AppImage-programmer", "Verktøy", None),
    ("io.missioncenter.MissionCenter", "Mission Center", "Oppgavebehandler", "Verktøy", None),
    ("org.openrgb.OpenRGB", "OpenRGB", "RGB-styring (brukes av RGB-fanen)", "Verktøy", None),
    ("io.github.pwr_solaar.solaar", "Solaar", "Logitech-enheter (brukes av Logitech-fanen)", "Verktøy", None),
    ("org.freedesktop.Piper", "Piper", "Gaming-mus (ratbagd)", "Verktøy", None),
    ("io.github.DenysMb.Kontainer", "Kontainer", "Distrobox-containere", "Verktøy", None),
    ("org.gnome.Firmware", "Firmware", "Oppdater fastvare på enheter", "Verktøy", None),
    ("org.fedoraproject.MediaWriter", "Fedora Media Writer", "Lag oppstartbar minnepinne", "Verktøy", None),
]
# Programmer som installeres med skript (ikke Flatpak). ID-er starter med «script:».
APP_DIR = os.path.dirname(os.path.abspath(__file__))
HOME = str(Path.home())
SCRIPT_PATH = f"{HOME}/.local/bin:/home/linuxbrew/.linuxbrew/bin:{os.environ.get('PATH', '')}"
CODEX_INSTALL = r"""
set -e
export PATH="$HOME/.local/bin:/home/linuxbrew/.linuxbrew/bin:$PATH"
if ! command -v npm >/dev/null; then
    if command -v brew >/dev/null; then
        brew install node
    else
        echo "Installerer Node.js (npm) med pakkehåndtereren – skriv inn passordet ditt" >&2
        if   command -v pacman  >/dev/null; then pkexec pacman -S --needed --noconfirm nodejs npm
        elif command -v dnf     >/dev/null && [ ! -e /run/ostree-booted ]; then pkexec dnf install -y nodejs npm
        elif command -v apt-get >/dev/null; then pkexec sh -c 'apt-get update && apt-get install -y nodejs npm'
        elif command -v zypper  >/dev/null; then pkexec zypper -n install nodejs npm
        else echo "Fant ingen måte å installere Node.js på" >&2; exit 1; fi
    fi
fi
if [ -w "$(npm prefix -g)/lib" ] 2>/dev/null; then npm install -g @openai/codex
else npm install -g --prefix "$HOME/.local" @openai/codex; fi
"""
SCRIPTS = {
    "script:claude-code": {
        "name": "Claude Code", "desc": "Anthropics KI-assistent for koding, i terminalen",
        "bins": [f"{HOME}/.local/bin/claude", "claude"], "run": "claude",
        "install": "curl -fsSL https://claude.ai/install.sh | bash",
        "uninstall": 'rm -f "$HOME/.local/bin/claude" && rm -rf "$HOME/.local/share/claude"',
    },
    "script:codex": {
        "name": "Codex", "desc": "OpenAIs KI-assistent for koding, i terminalen",
        "bins": ["/home/linuxbrew/.linuxbrew/bin/codex", f"{HOME}/.local/bin/codex", "codex"], "run": "codex",
        "install": CODEX_INSTALL,
        "uninstall": ('export PATH="$HOME/.local/bin:/home/linuxbrew/.linuxbrew/bin:$PATH"; '
                      'npm uninstall -g @openai/codex 2>/dev/null; '
                      'npm uninstall -g --prefix "$HOME/.local" @openai/codex 2>/dev/null; '
                      'brew uninstall codex 2>/dev/null; true'),
    },
}
for sid, sc in SCRIPTS.items():
    CATALOG.append((sid, sc["name"], sc["desc"], "Utvikling og KI", None))
CAT_BY_ID = {c[0]: c for c in CATALOG}
CATEGORIES = ["Spill", "Kommunikasjon", "Nettlesere", "Media", "Kontor", "Utvikling og KI", "Verktøy"]


def script_bin(sid):
    """Stien til programmet hvis det er installert (sjekker de vanlige stedene)."""
    for b in SCRIPTS[sid]["bins"]:
        p = b if b.startswith("/") else shutil.which(b, path=SCRIPT_PATH)
        if p and os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def make_launcher(sid):
    """Menysnarvei med ikon (åpner i terminal, som snarveiene på skrivebordet)."""
    sc, b = SCRIPTS[sid], script_bin(sid)
    if not b:
        return None
    key = sid.split(":", 1)[1]
    icon = os.path.join(APP_DIR, "icons", f"{key}.svg")
    apps = Path.home() / ".local/share/applications"
    apps.mkdir(parents=True, exist_ok=True)
    f = apps / f"systemmonitor-{key}.desktop"
    f.write_text("[Desktop Entry]\nVersion=1.0\nType=Application\n"
                 f"Name={sc['name']}\nComment={sc['desc']}\nIcon={icon}\nExec={b}\n"
                 f"Path={HOME}\nTerminal=true\nCategories=Development;\n")
    return str(f)


def run_script(sid, op):
    env = {**os.environ, "PATH": SCRIPT_PATH}
    try:
        r = subprocess.run(["bash", "-c", SCRIPTS[sid][op]], capture_output=True, text=True,
                           timeout=1800, env=env)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError) as e:
        return 127, str(e)


def _run(cmd, timeout=600):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError) as e:
        return 127, str(e)


def installed_flatpaks():
    code, out = _run(["flatpak", "list", "--app", "--columns=application,name,installation"], 60)
    res = {}
    for line in out.splitlines():
        p = line.split("\t")
        if len(p) >= 2 and "." in p[0]:
            res[p[0]] = {"name": p[1], "where": p[2] if len(p) > 2 else "?"}
    return res


def system_flathub():
    code, out = _run(["flatpak", "remotes", "--system", "--columns=name"], 30)
    return code == 0 and "flathub" in out.split()


def load_list():
    try:
        return json.loads(LIST_FILE.read_text()).get("programs", [])
    except (OSError, ValueError):
        return None


def save_list(ids):
    try:
        LIST_FILE.parent.mkdir(parents=True, exist_ok=True)
        LIST_FILE.write_text(json.dumps({"programs": sorted(set(ids))}, indent=1))
    except OSError:
        pass


def icon_for(app_id):
    if app_id.startswith("script:"):
        p = os.path.join(APP_DIR, "icons", app_id.split(":", 1)[1] + ".svg")
        return p if os.path.exists(p) else None
    for d in ICON_DIRS:
        p = d / f"{app_id}.png"
        if p.exists():
            return str(p)
    return None


# --------------------------------------------------------------------------
class ProgramsPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for side in ("top", "bottom", "start", "end"):
            getattr(self, f"set_margin_{side}")(12)
        self.installed = {}
        self.names = {c[0]: (c[1], c[2]) for c in CATALOG}
        self.mine = []
        self.rows = {}                     # app_id -> list av rad-widgets (kan stå i flere lister)
        self.busy = set()
        self.q = queue.Queue()
        threading.Thread(target=self._worker, daemon=True).start()

        # verktøylinje
        top = Gtk.Box(spacing=8)
        self.search = Gtk.SearchEntry(placeholder_text="Søk i hele Flathub (f.eks. «spotify»)", hexpand=True)
        self.search.connect("activate", self._on_search)
        top.append(self.search)
        self.all_btn = Gtk.Button(label="Installer alle mine")
        self.all_btn.add_css_class("suggested-action")
        self.all_btn.connect("clicked", self._install_all)
        top.append(self.all_btn)
        menu = Gtk.MenuButton(icon_name="view-more-symbolic", tooltip_text="Flere valg")
        pop = Gtk.Popover()
        mb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for label, fn in (("Legg alle installerte til i «Mine programmer»", self._add_all_installed),
                          ("Eksporter listen til fil …", self._export),
                          ("Importer liste fra fil …", self._import),
                          ("Oppdater alle programmer", self._update_all)):
            b = Gtk.Button(label=label)
            b.add_css_class("flat")
            b.get_child().set_xalign(0)
            b.connect("clicked", lambda _b, f=fn: (pop.popdown(), f()))
            mb.append(b)
        pop.set_child(mb)
        menu.set_popover(pop)
        top.append(menu)
        self.append(top)

        self.status = Gtk.Label(xalign=0, wrap=True)
        self.status.add_css_class("dim-label")
        self.append(self.status)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, vexpand=True)
        sw = Gtk.StackSwitcher(stack=self.stack, halign=Gtk.Align.CENTER)
        self.append(sw)
        self.append(self.stack)
        self.mine_list = self._list_page("mine", "Mine programmer")
        self.cat_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        sc = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        sc.set_child(Adw.Clamp(maximum_size=900, child=self.cat_box))
        self.stack.add_titled(sc, "katalog", "Katalog")
        self.search_list = self._list_page("sok", "Søkeresultater")
        import autostart
        self.stack.add_titled(autostart.AutostartPage(), "oppstart", "Oppstart")

        self.status.set_label("Leser installerte programmer …")
        threading.Thread(target=self._load, daemon=True).start()

    def _list_page(self, name, title):
        lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, valign=Gtk.Align.START)
        lb.add_css_class("boxed-list")
        sc = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        sc.set_child(Adw.Clamp(maximum_size=900, child=lb))
        self.stack.add_titled(sc, name, title)
        return lb

    # --- data -----------------------------------------------------------------
    def _load(self):
        inst = installed_flatpaks()
        GLib.idle_add(self._loaded, inst)

    def _loaded(self, inst):
        self.installed = inst
        for app_id, info in inst.items():
            self.names.setdefault(app_id, (info["name"], ""))
        mine = load_list()
        if mine is None:                       # første gang: alt som er installert nå
            mine = list(inst) + [c[0] for c in CATALOG if c[4] and shutil.which(c[4])] + \
                [sid for sid in SCRIPTS if script_bin(sid)]
            save_list(mine)
        self.mine = sorted(set(mine), key=lambda i: self.names.get(i, (i,))[0].lower())
        self._fill_mine()
        self._fill_catalog()
        self.status.set_label(f"{len(inst)} Flatpak-programmer installert · {len(self.mine)} i «Mine programmer»")
        return False

    def is_installed(self, app_id):
        if app_id in SCRIPTS:
            return "script" if script_bin(app_id) else None
        if app_id in self.installed:
            return "flatpak"
        c = CAT_BY_ID.get(app_id)
        if c and c[4] and shutil.which(c[4]):
            return "system"
        return None

    # --- rader -----------------------------------------------------------------
    def _row(self, box, app_id, name=None, desc=None):
        name = name or self.names.get(app_id, (app_id, ""))[0]
        desc = desc if desc is not None else self.names.get(app_id, ("", ""))[1]
        row = Gtk.Box(spacing=12)
        for side, v in (("top", 8), ("bottom", 8), ("start", 10), ("end", 10)):
            getattr(row, f"set_margin_{side}")(v)
        ic = icon_for(app_id)
        img = Gtk.Image.new_from_file(ic) if ic else Gtk.Image.new_from_icon_name("application-x-executable")
        img.set_pixel_size(40)
        row.append(img)
        txt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
        t = Gtk.Label(label=name, xalign=0, ellipsize=3)
        t.add_css_class("heading")
        txt.append(t)
        d = Gtk.Label(label=desc or app_id, xalign=0, ellipsize=3)
        d.add_css_class("caption")
        d.add_css_class("dim-label")
        txt.append(d)
        row.append(txt)
        row.state_lbl = Gtk.Label()
        row.state_lbl.add_css_class("caption")
        row.append(row.state_lbl)
        row.spinner = Gtk.Spinner()
        row.append(row.spinner)
        row.star = Gtk.ToggleButton(icon_name="starred-symbolic", valign=Gtk.Align.CENTER)
        row.star.add_css_class("flat")
        row.star.set_tooltip_text("Med i «Mine programmer»")
        row.star.connect("toggled", self._on_star, app_id)
        row.append(row.star)
        row.open_btn = Gtk.Button(icon_name="media-playback-start-symbolic", valign=Gtk.Align.CENTER,
                                  tooltip_text="Åpne")
        row.open_btn.connect("clicked", lambda *_: self._open(app_id))
        row.append(row.open_btn)
        row.act = Gtk.Button(valign=Gtk.Align.CENTER)
        row.act.connect("clicked", lambda *_: self._on_action(app_id))
        row.append(row.act)
        row.app_id = app_id
        row._box = box
        self.rows.setdefault(app_id, []).append(row)
        self._sync_row(row)
        return row

    def _sync_row(self, row):
        app_id = row.app_id
        where = self.is_installed(app_id)
        busy = app_id in self.busy
        row.spinner.set_spinning(busy)
        row._quiet = True
        row.star.set_active(app_id in self.mine)
        row._quiet = False
        row.open_btn.set_visible(bool(where) and not busy)
        if busy:
            row.state_lbl.set_label("Jobber …")
            row.act.set_sensitive(False)
        elif where == "system":
            row.state_lbl.set_label("Installert (system)")
            row.act.set_label("Installer Flatpak")
            row.act.set_sensitive(True)
            row.act.remove_css_class("destructive-action")
            row.act.remove_css_class("suggested-action")
        elif where:
            row.state_lbl.set_label("✓ Installert")
            row.act.set_label("Avinstaller")
            row.act.set_sensitive(True)
            row.act.add_css_class("destructive-action")
            row.act.remove_css_class("suggested-action")
        else:
            row.state_lbl.set_label("")
            row.act.set_label("Installer")
            row.act.set_sensitive(True)
            row.act.add_css_class("suggested-action")
            row.act.remove_css_class("destructive-action")

    def _sync(self, app_id):
        for r in self.rows.get(app_id, []):
            self._sync_row(r)
        missing = [a for a in self.mine if not self.is_installed(a)]
        self.all_btn.set_label(f"Installer alle mine ({len(missing)})" if missing else "Alle mine er installert")
        self.all_btn.set_sensitive(bool(missing))
        return False

    def _clear(self, box):
        while (c := box.get_first_child()):
            box.remove(c)
        for k in list(self.rows):
            self.rows[k] = [r for r in self.rows[k] if r._box is not box]

    def _fill_mine(self):
        self._clear(self.mine_list)
        for app_id in self.mine:
            self.mine_list.append(self._row(self.mine_list, app_id))
        if not self.mine:
            self.mine_list.append(Gtk.Label(label="Ingen programmer ennå – trykk ☆ på et program i katalogen.",
                                            margin_top=20, margin_bottom=20))
        self._sync(self.mine[0] if self.mine else "")

    def _fill_catalog(self):
        self._clear(self.cat_box)
        for cat in CATEGORIES:
            h = Gtk.Label(label=cat, xalign=0)
            h.add_css_class("title-4")
            self.cat_box.append(h)
            lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
            lb.add_css_class("boxed-list")
            import hardware
            hw = hardware.present()
            needs = {"org.openrgb.OpenRGB": "rgb", "io.github.pwr_solaar.solaar": "logitech",
                     "org.freedesktop.Piper": "logitech"}      # vises bare når utstyret finnes
            for c in CATALOG:
                if c[0] in needs and not hw[needs[c[0]]]:
                    continue
                if c[3] == cat:
                    lb.append(self._row(self.cat_box, c[0], c[1], c[2]))
            self.cat_box.append(lb)

    # --- handlinger ----------------------------------------------------------------
    def _on_star(self, btn, app_id):
        if getattr(btn.get_parent(), "_quiet", False):
            return
        if btn.get_active() and app_id not in self.mine:
            self.mine.append(app_id)
        elif not btn.get_active() and app_id in self.mine:
            self.mine.remove(app_id)
        save_list(self.mine)
        self.mine.sort(key=lambda i: self.names.get(i, (i,))[0].lower())
        self._fill_mine()

    def _open(self, app_id):
        if app_id in SCRIPTS:                      # terminalprogram: åpne via menysnarveien
            f = make_launcher(app_id)
            if f:
                subprocess.Popen(["gio", "launch", f], start_new_session=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.status.set_label(f"Starter {SCRIPTS[app_id]['name']} i terminal …")
            return
        c = CAT_BY_ID.get(app_id)
        if app_id not in self.installed and c and c[4] and shutil.which(c[4]):
            cmd = [c[4]]
        else:
            cmd = ["flatpak", "run", app_id]
        subprocess.Popen(cmd, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.status.set_label(f"Starter {self.names.get(app_id, (app_id,))[0]} …")

    def _on_action(self, app_id):
        if self.is_installed(app_id) in ("flatpak", "script"):
            name = self.names.get(app_id, (app_id,))[0]
            d = Adw.AlertDialog(heading=f"Avinstallere {name}?",
                                body="Programmet fjernes. Innstillingene og dataene dine beholdes.")
            d.add_response("cancel", "Avbryt")
            d.add_response("rm", "Avinstaller")
            d.set_response_appearance("rm", Adw.ResponseAppearance.DESTRUCTIVE)
            d.connect("response", lambda _d, r: r == "rm" and self._queue("uninstall", app_id))
            d.present(self)
        else:
            self._queue("install", app_id)

    def _queue(self, op, app_id):
        if app_id in self.busy:
            return
        self.busy.add(app_id)
        self._sync(app_id)
        self.q.put((op, app_id))

    def _install_all(self, *_):
        for app_id in self.mine:
            if not self.is_installed(app_id):
                self._queue("install", app_id)

    def _update_all(self):
        self.q.put(("update", None))

    def _add_all_installed(self):
        self.mine = sorted(set(self.mine) | set(self.installed),
                           key=lambda i: self.names.get(i, (i,))[0].lower())
        save_list(self.mine)
        self._fill_mine()
        self.status.set_label(f"{len(self.mine)} programmer i «Mine programmer»")

    def _worker(self):
        while True:
            op, app_id = self.q.get()
            name = self.names.get(app_id, (app_id,))[0] if app_id else ""
            if op == "update":
                GLib.idle_add(self.status.set_label, "Oppdaterer alle Flatpak-programmer …")
                import progress as P
                pt = P.begin("Oppdaterer programmer", "Flathub")
                code, out = P.run_cmd(["flatpak", "update", "-y", "--noninteractive"], pt, 3600)
                pt.done("Alle programmer er oppdatert" if code == 0 else "Oppdateringen feilet", code == 0)
                GLib.idle_add(self.status.set_label, "Alle programmer er oppdatert ✓" if code == 0
                              else "Oppdatering feilet: " + (out.strip().splitlines() or ["?"])[-1])
                continue
            GLib.idle_add(self.status.set_label, ("Installerer " if op == "install" else "Avinstallerer ") + name + " …")
            if app_id in SCRIPTS:
                code, out = run_script(app_id, op)
                if op == "install" and script_bin(app_id):
                    make_launcher(app_id)
                elif op == "uninstall":
                    key = app_id.split(":", 1)[1]
                    (Path.home() / f".local/share/applications/systemmonitor-{key}.desktop").unlink(missing_ok=True)
                code = 0 if (op == "install") == bool(script_bin(app_id)) else (code or 1)
            elif op == "install":
                import progress as P
                pt = P.begin(f"Installerer {name}", "Flathub")
                where = ["--system"] if system_flathub() else ["--user"]
                code, out = P.run_cmd(["flatpak", "install", *where, "-y", "--noninteractive", "flathub", app_id], pt, 3600)
                if code != 0 and where == ["--system"]:     # f.eks. ingen tilgang: prøv for brukeren
                    _run(["flatpak", "remote-add", "--user", "--if-not-exists", "flathub",
                          "https://dl.flathub.org/repo/flathub.flatpakrepo"], 60)
                    code, out = P.run_cmd(["flatpak", "install", "--user", "-y", "--noninteractive",
                                           "flathub", app_id], pt, 3600)
                pt.done(f"{name} er installert" if code == 0 else "Installasjonen feilet", code == 0)
            else:
                code, out = _run(["flatpak", "uninstall", "-y", "--noninteractive", app_id], 600)
            inst = installed_flatpaks()
            ok = code == 0
            msg = (f"{name} er installert ✓" if op == "install" else f"{name} er avinstallert ✓") if ok else \
                f"{name}: " + (out.strip().splitlines() or ["feilet"])[-1]
            GLib.idle_add(self._done, app_id, inst, msg)

    def _done(self, app_id, inst, msg):
        self.installed = inst
        self.busy.discard(app_id)
        self._sync(app_id)
        self.status.set_label(msg)
        return False

    # --- søk -------------------------------------------------------------------------
    def _on_search(self, entry):
        q = entry.get_text().strip()
        if not q:
            return
        self.status.set_label(f"Søker etter «{q}» …")
        self.stack.set_visible_child_name("sok")

        def work():
            code, out = _run(["flatpak", "search", "--columns=application,name,description", q], 60)
            hits = []
            for line in out.splitlines():
                p = line.split("\t")
                if len(p) >= 2 and "." in p[0] and p[0] not in [h[0] for h in hits]:
                    hits.append((p[0], p[1], p[2] if len(p) > 2 else ""))
            GLib.idle_add(self._show_search, q, hits[:60])
        threading.Thread(target=work, daemon=True).start()

    def _show_search(self, q, hits):
        self._clear(self.search_list)
        for app_id, name, desc in hits:
            self.names.setdefault(app_id, (name, desc))
            self.search_list.append(self._row(self.search_list, app_id, name, desc))
        if not hits:
            self.search_list.append(Gtk.Label(label=f"Ingen treff for «{q}».", margin_top=20, margin_bottom=20))
        self.status.set_label(f"{len(hits)} treff for «{q}»")
        return False

    # --- eksport/import ----------------------------------------------------------------
    def _export(self):
        dlg = Gtk.FileDialog(title="Eksporter programliste", initial_name="programmer.json")

        def done(d, res):
            try:
                f = d.save_finish(res)
            except GLib.Error:
                return
            Path(f.get_path()).write_text(json.dumps({"programs": sorted(self.mine)}, indent=1))
            self.status.set_label(f"Listen er lagret: {f.get_path()}")
        dlg.save(self.get_root(), None, done)

    def _import(self):
        dlg = Gtk.FileDialog(title="Importer programliste")

        def done(d, res):
            try:
                f = d.open_finish(res)
                ids = json.loads(Path(f.get_path()).read_text()).get("programs", [])
            except (GLib.Error, OSError, ValueError, AttributeError):
                self.status.set_label("Kunne ikke lese filen")
                return
            self.mine = sorted(set(self.mine) | set(ids), key=lambda i: self.names.get(i, (i,))[0].lower())
            save_list(self.mine)
            self._fill_mine()
            self.status.set_label(f"Importerte {len(ids)} programmer – trykk «Installer alle mine»")
        dlg.open(self.get_root(), None, done)


# --------------------------------------------------------------------------
# Kommandolinje: brukes av installer.sh for skriptprogrammer (Claude, Codex …)
#   python3 programs.py --install-scripts programmer.json
# --------------------------------------------------------------------------
if __name__ == "__main__":
    import sys as _sys
    if len(_sys.argv) == 3 and _sys.argv[1] == "--install-scripts":
        ids = json.loads(Path(_sys.argv[2]).read_text()).get("programs", [])
        feil = 0
        for sid in [i for i in ids if i in SCRIPTS]:
            if script_bin(sid):
                print(f"✓ {SCRIPTS[sid]['name']} finnes allerede")
                make_launcher(sid)
                continue
            print(f"→ Installerer {SCRIPTS[sid]['name']} …", flush=True)
            code, out = run_script(sid, "install")
            if script_bin(sid):
                make_launcher(sid)
                print(f"✓ {SCRIPTS[sid]['name']} installert")
            else:
                feil += 1
                print(f"✗ {SCRIPTS[sid]['name']}: " + (out.strip().splitlines() or ["feilet"])[-1])
        _sys.exit(1 if feil else 0)
