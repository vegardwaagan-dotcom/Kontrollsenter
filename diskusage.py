"""«Hva tar plass?» – de største mappene i hjemmemappen og spillene, med knapper for å åpne eller avinstallere."""
import glob
import os
import subprocess
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk  # noqa: E402

import i18n  # noqa: E402

HOME = Path.home()
# Store mapper som deles opp ett nivå til (der det meste pleier å ligge)
SPLIT = [".local/share", ".var/app", ".cache", ".local/share/Steam/steamapps", ".config"]


def human(n):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return f"{n:.0f} {u}" if u in ("B", "KB") else f"{n:.1f} {u}"
        n /= 1024


def du(paths):
    """Størrelse i byte per sti (du -sxb, samme filsystem)."""
    if not paths:
        return {}
    if __import__("sys").platform == "win32":          # ingen «du» på Windows – tell selv
        import wintools
        return {str(p): wintools.tree_size(str(p)) for p in paths}
    try:
        r = subprocess.run(["du", "-sxb", "--", *map(str, paths)], capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.SubprocessError):
        return {}
    out = {}
    for line in r.stdout.splitlines():
        size, _tab, p = line.partition("\t")
        try:
            out[p] = int(size)
        except ValueError:
            pass
    return out


def folders():
    """[(sti, størrelse)] – største mapper. «Samlemapper» (som ~/.local/share) deles opp så du ser hva som
    faktisk tar plass. Spillmappen (steamapps/common) vises i spill-listen i stedet."""
    split = [HOME / s for s in SPLIT]
    skip = {str(HOME / ".local/share/Steam/steamapps/common")}

    def expand(p, depth=0):
        """Mapper som skal måles: del opp p hvis den inneholder en samlemappe."""
        sp = str(p)
        if sp in skip or p.is_symlink():
            return []
        inside = [x for x in split if str(x).startswith(sp + "/")]
        if (p in split or inside) and depth < 6:
            out = []
            try:
                for k in p.iterdir():
                    if k.is_dir() and not k.is_symlink():
                        out += expand(k, depth + 1)
            except OSError:
                pass
            return out
        return [p]

    targets = []
    for p in HOME.iterdir():
        if p.is_dir():
            targets += expand(p)
    sizes = du(targets)
    return sorted(((p, s) for p, s in sizes.items() if s > 50 * 1024 * 1024), key=lambda x: -x[1])


def steam_games():
    """[(appid, navn, størrelse, mappe)] fra Steams appmanifest (raskt – ingen skanning)."""
    try:
        import games
        import savegames
        import vdf
    except ImportError:
        return []
    out, seen = [], set()
    for lib in savegames._libs():
        for f in glob.glob(str(lib / "appmanifest_*.acf")):
            try:
                st = vdf.get(vdf.load(f), "AppState") or {}
                size = int(st.get("SizeOnDisk", 0))
                name = st.get("name", "")
                if st.get("appid") in seen:
                    continue
                seen.add(st.get("appid"))
                if size and not any(x in name for x in ("Proton", "Steam Linux Runtime", "Steamworks")):
                    out.append((st.get("appid"), name, size, lib / "common" / st.get("installdir", "")))
            except Exception:  # noqa: BLE001
                continue
    _ = games
    return sorted(out, key=lambda x: -x[2])


def nice(path):
    p = str(path)
    return "~" + p[len(str(HOME)):] if p.startswith(str(HOME)) else p


def build_card(page, card_fn):
    c, i = card_fn("Hva tar plass?", "De største mappene i hjemmemappen og spillene dine. Trykk «Åpne» for å se "
                                      "innholdet, eller avinstaller spill du ikke spiller lenger.")
    btn = Gtk.Button(label=i18n.tr("Finn ut hva som tar plass"), halign=Gtk.Align.START)
    btn.add_css_class("suggested-action")
    i.append(btn)
    status = Gtk.Label(xalign=0)
    status.add_css_class("dim-label")
    i.append(status)
    res = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    i.append(res)

    def lst(title, rows):
        lab = Gtk.Label(label=i18n.tr(title), xalign=0)
        lab.add_css_class("heading")
        res.append(lab)
        biggest = rows[0][1] if rows else 1
        box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        box.add_css_class("boxed-list")
        for name, size, actions in rows:
            r = Gtk.Box(spacing=10)
            for side, v in (("top", 6), ("bottom", 6), ("start", 12), ("end", 8)):
                getattr(r, f"set_margin_{side}")(v)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
            n = Gtk.Label(label=name, xalign=0, ellipsize=3)
            col.append(n)
            bar = Gtk.LevelBar(min_value=0, max_value=1, value=size / biggest)
            for off in ("low", "high", "full"):
                bar.remove_offset_value(off)
            bar.set_size_request(-1, 6)
            col.append(bar)
            r.append(col)
            sz = Gtk.Label(label=human(size))
            sz.add_css_class("numeric")
            sz.set_width_chars(9)
            sz.set_xalign(1)
            r.append(sz)
            for icon, tip, fn in actions:
                b = Gtk.Button(icon_name=icon, tooltip_text=i18n.tr(tip), valign=Gtk.Align.CENTER)
                b.add_css_class("flat")
                b.connect("clicked", lambda _b, f=fn: f())
                r.append(b)
            box.append(r)
        res.append(box)

    def opener(path):
        if __import__("sys").platform == "win32":
            return lambda: os.startfile(str(path))
        return lambda: subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def show(data):
        fl, gm = data
        while (ch := res.get_first_child()):
            res.remove(ch)
        lst("Største mapper", [(nice(p), s, [("folder-open-symbolic", "Åpne", opener(p))]) for p, s in fl[:14]])
        lst("Spill", [(n, s, [("folder-open-symbolic", "Åpne", opener(d)),
                              ("user-trash-symbolic", "Avinstaller i Steam", opener(f"steam://uninstall/{a}"))])
                      for a, n, s, d in gm[:14]])
        total = sum(s for _a, _n, s, _d in gm)
        status.set_label(i18n.tr("Spillene tar til sammen ") + human(total))
        btn.set_sensitive(True)
        btn.set_label(i18n.tr("Regn ut på nytt"))
        return False

    def failed(e):
        status.set_label(i18n.tr("Kunne ikke regne ut: ") + str(e))
        btn.set_sensitive(True)
        return False

    def work():
        try:
            data = (folders(), steam_games())
        except Exception as e:  # noqa: BLE001 – knappen skal ikke bli hengende
            GLib.idle_add(failed, e)
            return
        GLib.idle_add(show, data)

    def run(*_):
        btn.set_sensitive(False)
        status.set_label(i18n.tr("Regner ut … (kan ta et halvt minutt første gang)"))
        threading.Thread(target=work, daemon=True).start()
    btn.connect("clicked", run)
    page.box.append(c)
