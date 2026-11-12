"""Sikkerhetskopi av lagrede spill til NAS-en (\\\\192.168.1.3\\Public\\Kontrollsenter\\Lagrede spill\\<PC>).

Lagrede spill i Proton-prefikset (Windows-mappene AppData, Documents, Saved Games) og Steams egne
lagringer (userdata) pakkes per spill. Cache, skyggefiler, logger og filer over 100 MB hoppes over.
"""
import io
import json
import os
import re
import shutil
import socket
import tarfile
import tempfile
import threading
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

import i18n  # noqa: E402

CFG = os.path.expanduser("~/.config/systemmonitor/lagrede-spill.json")
LOCAL_SAFETY = Path.home() / ".cache/systemmonitor/lagrede-spill-før-gjenoppretting"
SAVE_DIRS = ["AppData/Roaming", "AppData/LocalLow", "AppData/Local", "Documents", "Saved Games"]
SKIP = re.compile(r"^(cache|caches|shadercache|shader_cache|d3dscache|nvidia|nv_cache|temp|tmp|crashes|crashdumps|"
                  r"crashreportclient|logs|webcache|gpucache|code cache|microsoft|packages|unrealengine|"
                  r"cefcache|htmlcache|steam)$", re.I)
MAX_FILE = 100 * 1024 * 1024
MAX_GAME_FILE = 1024 * 1024 * 1024          # lagrede verdener i spillmappen kan være store (f.eks. ARK)
GAME_SAVE = re.compile(r"^(saved|savegames?|saves?|savedarkslocal)$", re.I)
GAME_SKIP = re.compile(r"^(logs?|crashes|webcache|shadercache|cache|demos|screenshots|config)$", re.I)
REMOTE_ROOT = "Lagrede spill"


def load_cfg():
    try:
        with open(CFG) as f:
            return {"auto": False, **json.load(f)}
    except (OSError, ValueError):
        return {"auto": False}


def save_cfg(c):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    with open(CFG, "w") as f:
        json.dump(c, f)


def pc_name():
    return re.sub(r"[^\w.-]", "_", socket.gethostname() or "PC")


def safe(name):
    return re.sub(r'[\\/:*?"<>|]', "", name).strip()[:60] or "spill"


def _libs():
    import games
    libs = [games.STEAM / "steamapps"]
    try:
        import vdf
        lf = vdf.load(games.STEAM / "steamapps/libraryfolders.vdf")
        for v in (vdf.get(lf, "libraryfolders") or {}).values():
            if isinstance(v, dict) and v.get("path"):
                libs.append(Path(v["path"]) / "steamapps")
    except Exception:  # noqa: BLE001
        pass
    out, seen = [], set()
    for lib in libs:                       # samme bibliotek kan stå to ganger (symlenke / libraryfolders)
        key = os.path.realpath(lib)
        if key not in seen:
            seen.add(key)
            out.append(lib)
    return out


def _user_dir(appid):
    for lib in _libs():
        p = lib / "compatdata" / appid / "pfx/drive_c/users/steamuser"
        if p.is_dir():
            return p
    return None


def _install_dir(appid):
    import vdf
    for lib in _libs():
        m = lib / f"appmanifest_{appid}.acf"
        if m.exists():
            try:
                d = (vdf.get(vdf.load(m), "AppState") or {}).get("installdir")
                if d and (lib / "common" / d).is_dir():
                    return lib / "common" / d
            except Exception:  # noqa: BLE001
                pass
    return None


def _game_dir_saves(appid):
    """«Saved»/«SaveGames»-mapper inne i spillmappen (Unreal-spill som ARK lagrer der)."""
    out = []
    inst = _install_dir(appid)
    if not inst:
        return out
    for root, dirs, _files in os.walk(inst):
        depth = len(Path(root).relative_to(inst).parts)
        if depth > 3:
            dirs[:] = []
            continue
        for d in list(dirs):
            if GAME_SAVE.match(d):
                base = Path(root) / d
                for r2, ds2, fs2 in os.walk(base):
                    ds2[:] = [x for x in ds2 if not GAME_SKIP.match(x)]
                    for fn in fs2:
                        p = Path(r2) / fn
                        try:
                            if p.is_symlink() or p.stat().st_size > MAX_GAME_FILE:
                                continue
                        except OSError:
                            continue
                        out.append((p, "game/" + str(p.relative_to(inst))))
                dirs.remove(d)
    return out


def _files(appid):
    """(sti på disk, navn i arkivet) for alle lagringsfiler til spillet."""
    out = _game_dir_saves(appid)
    ud = _user_dir(appid)
    if ud:
        for sub in SAVE_DIRS:
            base = ud / sub
            if not base.is_dir():
                continue
            for root, dirs, files in os.walk(base):
                dirs[:] = [d for d in dirs if not SKIP.match(d)]
                for fn in files:
                    p = Path(root) / fn
                    try:
                        if p.is_symlink() or p.stat().st_size > MAX_FILE:
                            continue
                    except OSError:
                        continue
                    out.append((p, "pfx/" + str(p.relative_to(ud))))
    try:
        import games
        user = games.active_user()
        ud2 = games.STEAM / "userdata" / user / appid
        if user and ud2.is_dir():
            for root, _dirs, files in os.walk(ud2):
                for fn in files:
                    p = Path(root) / fn
                    out.append((p, "userdata/" + str(p.relative_to(ud2))))
    except Exception:  # noqa: BLE001
        pass
    return out


def games_with_saves():
    """[{appid, name, size, files}] – spill som har noe å ta vare på."""
    import games
    out = []
    for g in games.installed_games():
        fs = _files(g["appid"])
        if fs:
            size = 0
            for p, _a in fs:
                try:
                    size += p.stat().st_size
                except OSError:
                    pass
            out.append({"appid": g["appid"], "name": g["name"], "size": size, "files": len(fs)})
    return out


def _archive(appid, dest):
    with tarfile.open(dest, "w:gz") as t:
        for p, arc in _files(appid):
            try:
                t.add(p, arcname=arc, recursive=False)
            except OSError:
                continue
        info = tarfile.TarInfo("kontrollsenter.json")
        data = json.dumps({"appid": appid, "pc": pc_name(), "time": time.time()}).encode()
        info.size = len(data)
        t.addfile(info, io.BytesIO(data))


def _remote_dir():
    return f"{REMOTE_ROOT}/{pc_name()}"


def backup(appids=None, progress=None):
    """Ta sikkerhetskopi til NAS-en. Returnerer (antall ok, feilmelding eller None)."""
    import lanupdate as L
    if not L.on_lan():
        return 0, "NAS-en svarer ikke – er du på hjemmenettet?"
    items = [g for g in games_with_saves() if appids is None or g["appid"] in appids]
    if not items:
        return 0, None
    _host, share, folder = L._split()
    import subprocess
    for part in (folder, f"{folder}/{REMOTE_ROOT}", f"{folder}/{_remote_dir()}"):
        L.smb_mkdir(part)
    tmp = Path(tempfile.mkdtemp())
    ok = 0
    try:
        for n, g in enumerate(items, 1):
            if progress:
                progress(f"{n}/{len(items)} {g['name']}")
            fn = f"{g['appid']} - {safe(g['name'])}.tar.gz"
            _archive(g["appid"], tmp / "a.tar.gz")
            # behold forrige kopi som «.forrige»
            try:
                L._smb(f'cd "{_remote_dir()}"; del "{fn}.forrige"', 60)
            except Exception:  # noqa: BLE001
                pass
            try:
                L._smb(f'cd "{_remote_dir()}"; rename "{fn}" "{fn}.forrige"', 60)
            except Exception:  # noqa: BLE001
                pass
            L._smb(f'cd "{_remote_dir()}"; put "{tmp / "a.tar.gz"}" "{fn}"', 600)
            ok += 1
        cfg = load_cfg()
        cfg["last"] = time.time()
        save_cfg(cfg)
        return ok, None
    except Exception as e:  # noqa: BLE001
        return ok, str(e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def backup_async(appids=None, done=None):
    def work():
        res = backup(appids)
        if done:
            GLib.idle_add(done, res)
    threading.Thread(target=work, daemon=True).start()


def restore(appid, name):
    """Hent sikkerhetskopien fra NAS-en og legg den tilbake. Det som ligger der nå tas vare på lokalt først."""
    import lanupdate as L
    ud = _user_dir(appid)
    if not ud and not _install_dir(appid):
        return False, "Fant ikke spillet – er det installert?"
    ud = ud or Path(tempfile.gettempdir())
    tmp = Path(tempfile.mkdtemp())
    try:
        fn = f"{appid} - {safe(name)}.tar.gz"
        L._smb(f'cd "{_remote_dir()}"; get "{fn}" "{tmp / "a.tar.gz"}"', 600)
        # sikkerhet: ta vare på det som ligger lokalt nå
        LOCAL_SAFETY.mkdir(parents=True, exist_ok=True)
        _archive(appid, LOCAL_SAFETY / f"{appid}-{time.strftime('%Y%m%d-%H%M%S')}.tar.gz")
        import games
        user = games.active_user()
        with tarfile.open(tmp / "a.tar.gz") as t:
            for m in t.getmembers():
                if m.name.startswith("pfx/"):
                    base, rel = ud, m.name[4:]
                elif m.name.startswith("userdata/") and user:
                    base, rel = games.STEAM / "userdata" / user / appid, m.name[9:]
                elif m.name.startswith("game/") and _install_dir(appid):
                    base, rel = _install_dir(appid), m.name[5:]
                else:
                    continue
                if not m.isfile() or ".." in Path(rel).parts or rel.startswith("/"):
                    continue
                dest = base / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                src = t.extractfile(m)
                with open(dest, "wb") as f:
                    shutil.copyfileobj(src, f)
                os.utime(dest, (m.mtime, m.mtime))
        return True, f"Lagrede spill for {name} er hentet tilbake ✓"
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if "NOT_FOUND" in msg:
            msg = "Ingen sikkerhetskopi av dette spillet på NAS-en ennå."
        return False, msg
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


# --------------------------------------------------------------------------
# Kort i Spill-fanen
# --------------------------------------------------------------------------
def build_card(page, card_fn):
    c, i = card_fn("Sikkerhetskopi av lagrede spill",
                   "Lagrede spill i Proton-mappene ligger ikke alltid i Steam Cloud. Kontrollsenter kan ta vare på dem "
                   f"på NAS-en (Kontrollsenter\\{REMOTE_ROOT}\\{pc_name()}). Bare på hjemmenettet.")
    cfg = load_cfg()
    top = Gtk.Box(spacing=8)
    auto = Gtk.Switch(active=cfg.get("auto", False), valign=Gtk.Align.CENTER)

    def set_auto(w, _p):
        c2 = load_cfg()
        c2["auto"] = w.get_active()
        save_cfg(c2)
    auto.connect("notify::active", set_auto)
    lab = Gtk.Label(label=i18n.tr("Automatisk etter hver spilløkt"), xalign=0, hexpand=True)
    top.append(lab)
    top.append(auto)
    i.append(top)
    status = Gtk.Label(xalign=0, wrap=True)
    status.add_css_class("dim-label")
    lst = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
    lst.add_css_class("boxed-list")
    i.append(lst)
    btns = Gtk.Box(spacing=8)
    allb = Gtk.Button(label=i18n.tr("Ta sikkerhetskopi av alle nå"))
    allb.add_css_class("suggested-action")
    btns.append(allb)
    i.append(btns)
    i.append(status)
    if cfg.get("last"):
        status.set_label(i18n.tr("Siste sikkerhetskopi: ") + time.strftime("%d.%m.%Y %H:%M", time.localtime(cfg["last"])))

    def fill(items):
        while (ch := lst.get_first_child()):
            lst.remove(ch)
        if not items:
            import ui
            lst.append(Gtk.ListBoxRow(child=ui.empty("ks-games-symbolic", "Ingen lagrede spill funnet"),
                                      activatable=False))
        for g in items:
            r = Gtk.Box(spacing=10)
            for side, v in (("top", 6), ("bottom", 6), ("start", 12), ("end", 8)):
                getattr(r, f"set_margin_{side}")(v)
            n = Gtk.Label(label=g["name"], xalign=0, hexpand=True, ellipsize=3)
            r.append(n)
            sz = Gtk.Label(label=f"{human(g['size'])} · {g['files']} filer")
            sz.add_css_class("dim-label")
            sz.add_css_class("numeric")
            r.append(sz)
            b1 = Gtk.Button(icon_name="document-save-symbolic", tooltip_text=i18n.tr("Ta sikkerhetskopi nå"))
            b1.add_css_class("flat")
            b1.connect("clicked", lambda _b, a=g["appid"]: run([a]))
            r.append(b1)
            b2 = Gtk.Button(icon_name="document-revert-symbolic", tooltip_text=i18n.tr("Hent tilbake fra NAS-en"))
            b2.add_css_class("flat")
            b2.connect("clicked", lambda b, a=g["appid"], nm=g["name"]: ask_restore(b, a, nm))
            r.append(b2)
            lst.append(r)
        return False

    def run(appids):
        allb.set_sensitive(False)
        status.set_label(i18n.tr("Tar sikkerhetskopi …"))

        def done(res):
            ok, err = res
            allb.set_sensitive(True)
            import ui
            if err:
                status.set_label(i18n.tr("Feil: ") + err)
            else:
                ui.status(status, f"Sikkerhetskopi tatt av {ok} spill ✓")
            return False
        backup_async(appids, done)

    def ask_restore(btn, appid, name):
        d = Adw.AlertDialog(heading=i18n.tr("Hente tilbake lagrede spill?"),
                            body=i18n.tr("De lagrede spillene for {} erstattes med sikkerhetskopien fra NAS-en. Det som "
                                         "ligger på PC-en nå, tas vare på i ~/.cache/systemmonitor først.")
                            .replace("{}", name))
        d.add_response("cancel", i18n.tr("Avbryt"))
        d.add_response("ok", i18n.tr("Hent tilbake"))
        d.set_response_appearance("ok", Adw.ResponseAppearance.DESTRUCTIVE)

        def resp(_d, r):
            if r != "ok":
                return

            def work():
                res = restore(appid, name)
                GLib.idle_add(lambda: (status.set_label(("" if res[0] else i18n.tr("Feil: ")) + i18n.tr(res[1])),
                                       False)[1])
            threading.Thread(target=work, daemon=True).start()
        d.connect("response", resp)
        d.present(btn.get_root())

    allb.connect("clicked", lambda *_: run(None))
    threading.Thread(target=lambda: GLib.idle_add(fill, games_with_saves()), daemon=True).start()
    page.box.append(c)
