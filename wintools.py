"""Verktøy og Systemsjekk på Windows: systeminfo, rydd opp, diskhelse, gjenopprettingspunkt og systemsjekk."""
import glob
import os
import platform
import re
import shutil
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

import i18n  # noqa: E402
import winsupport as WS  # noqa: E402


def _ps(cmd, timeout=60):
    return WS.run(["powershell", "-NoProfile", "-Command", cmd], timeout)


def _dim(text):
    lab = Gtk.Label(label=i18n.tr(text), xalign=0, wrap=True, selectable=True)
    lab.add_css_class("caption")
    lab.add_css_class("dim-label")
    return lab


def human(n):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return f"{n:.0f} {u}" if u in ("B", "KB") else f"{n:.1f} {u}"
        n /= 1024


def tree_size(path):
    total = 0
    stack = [path]
    while stack:
        p = stack.pop()
        try:
            with os.scandir(p) as it:
                for e in it:
                    try:
                        if e.is_symlink():
                            continue
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        else:
                            total += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


# --------------------------------------------------------------------------
# Systeminfo
# --------------------------------------------------------------------------
def system_info():
    import psutil
    from sensors import cpu_model
    bi = WS.bios_info()
    vm = psutil.virtual_memory()
    rows = [("System", platform.platform()), ("Maskin", f"{bi.get('SystemManufacturer', '')} "
                                                         f"{bi.get('SystemProductName', '')}".strip()),
            ("Hovedkort", f"{bi.get('BaseBoardManufacturer', '')} {bi.get('BaseBoardProduct', '')}".strip()),
            ("BIOS", bi.get("BIOSVersion", "")), ("Prosessor", f"{cpu_model()} ({psutil.cpu_count()} tråder)"),
            ("Minne", f"{vm.total / 2**30:.1f} GB")]
    code, out = _ps("Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name + ' (' + $_.DriverVersion + ')' }")
    for ln in out.strip().splitlines():
        if ln.strip():
            rows.append(("Grafikk", ln.strip()))
    for p in psutil.disk_partitions():
        try:
            u = psutil.disk_usage(p.mountpoint)
            rows.append(("Disk", f"{p.mountpoint} {human(u.used)} brukt av {human(u.total)}"))
        except OSError:
            pass
    return rows


# --------------------------------------------------------------------------
# Rydd opp
# --------------------------------------------------------------------------
def cleanup_items():
    local = os.environ.get("LOCALAPPDATA", "")
    items = [("temp", "Midlertidige filer (Temp)", "Filer programmer har lagt igjen. Trygt å slette.",
              [os.environ.get("TEMP", ""), os.path.join(local, "Temp")], True),
             ("nvcache", "NVIDIA- og DirectX-shadercache", "Lages på nytt ved behov – spill kan hakke litt første gang.",
              [os.path.join(local, "NVIDIA", "DXCache"), os.path.join(local, "NVIDIA", "GLCache"),
               os.path.join(local, "D3DSCache"), os.path.join(local, "AMD", "DxCache")], False)]
    try:
        import games
        if games.STEAM:
            items.append(("steamshader", "Steam shader-cache", "Steam lager den på nytt ved behov.",
                          [str(games.STEAM / "steamapps" / "shadercache")], False))
    except Exception:  # noqa: BLE001
        pass
    out = []
    for key, name, desc, paths, default in items:
        paths = [p for p in dict.fromkeys(paths) if p and os.path.isdir(p)]
        out.append({"key": key, "name": name, "desc": desc, "paths": paths, "size": sum(tree_size(p) for p in paths),
                    "default": default})
    code, outp = _ps("(New-Object -ComObject Shell.Application).NameSpace(10).Items() | "
                     "Measure-Object -Property Size -Sum | Select-Object -ExpandProperty Sum")
    try:
        rb = int(float(outp.strip().splitlines()[-1].replace(",", ".")))
    except (ValueError, IndexError):
        rb = 0
    out.insert(0, {"key": "trash", "name": "Papirkurven", "desc": "Filer du har slettet.", "paths": [],
                   "size": rb, "default": True})
    return out


def do_cleanup(items):
    freed, errors = 0, []
    for it in items:
        if it["key"] == "trash":
            code, out = _ps("Clear-RecycleBin -Force -ErrorAction SilentlyContinue")
            freed += it["size"]
            continue
        for p in it["paths"]:
            before = tree_size(p)
            for e in list(os.scandir(p)):
                try:
                    if e.is_dir(follow_symlinks=False):
                        shutil.rmtree(e.path, ignore_errors=True)
                    else:
                        os.remove(e.path)
                except OSError:
                    pass                              # i bruk – hoppes over
            freed += max(0, before - tree_size(p))
    return freed, errors


# --------------------------------------------------------------------------
# Kortene i Verktøy
# --------------------------------------------------------------------------
def build_cards(page, card):
    _info_card(page, card)
    _cleanup_card(page, card)
    _health_card(page, card)
    _restore_card(page, card)


def _bg(work, done):
    threading.Thread(target=lambda: GLib.idle_add(lambda: (done(work()), False)[1]), daemon=True).start()


def _info_card(page, card):
    c, i = card("Systeminfo", "Det viktigste om maskinen din – kopier og lim inn når du ber om hjelp på et forum.")
    grid = Gtk.Grid(column_spacing=18, row_spacing=4)
    i.append(grid)
    st = _dim("")
    btn = Gtk.Button(label=i18n.tr("Kopier til forum"), halign=Gtk.Align.START)
    i.append(btn)
    i.append(st)
    rows = []

    def show(r):
        rows.extend(r)
        for n, (k, v) in enumerate(r):
            a = Gtk.Label(label=i18n.tr(k), xalign=0)
            a.add_css_class("dim-label")
            grid.attach(a, 0, n, 1, 1)
            grid.attach(Gtk.Label(label=v, xalign=0, selectable=True, wrap=True), 1, n, 1, 1)

    def copy(*_):
        txt = "**Systeminfo** (fra Kontrollsenter)\n```\n" + "\n".join(f"{k:12} {v}" for k, v in rows) + "\n```"
        Gdk.Display.get_default().get_clipboard().set(txt)
        import ui
        ui.status(st, "Kopiert ✓ – lim inn med Ctrl + V")
    btn.connect("clicked", copy)
    _bg(system_info, show)
    page.box.append(c)


def _cleanup_card(page, card):
    c, i = card("Rydd opp", "Frigjør plass. Velg hva som skal slettes – ingenting slettes før du trykker «Rydd opp».")
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    i.append(box)
    btn = Gtk.Button(label=i18n.tr("Rydd opp"), halign=Gtk.Align.START, sensitive=False)
    btn.add_css_class("destructive-action")
    i.append(btn)
    st = _dim(i18n.tr("Regner ut størrelser …"))
    i.append(st)
    checks = []

    def show(items):
        for it in items:
            cb = Gtk.CheckButton(active=it["default"] and it["size"] > 0)
            lab = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            lab.append(Gtk.Label(label=f"{i18n.tr(it['name'])} – {human(it['size'])}", xalign=0))
            lab.append(_dim(it["desc"]))
            cb.set_child(lab)
            box.append(cb)
            checks.append((cb, it))
        st.set_label(i18n.tr("Totalt {} kan frigjøres").replace("{}", human(sum(it["size"] for it in items))))
        btn.set_sensitive(True)

    def run(*_):
        sel = [it for cb, it in checks if cb.get_active()]
        if not sel:
            return
        btn.set_sensitive(False)
        st.set_label(i18n.tr("Rydder opp …"))

        def done(res):
            import ui
            ui.status(st, f"Ferdig ✓ {human(res[0])} frigjort")
            btn.set_sensitive(True)
        _bg(lambda: do_cleanup(sel), done)
    btn.connect("clicked", run)
    _bg(cleanup_items, show)
    page.box.append(c)


def _health_card(page, card):
    c, i = card("Diskhelse", "Helse og slitasje fra diskene – fanger opp en disk som er i ferd med å svikte.")
    lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
    lb.add_css_class("boxed-list")
    i.append(lb)

    def work():
        import json
        code, out = _ps("Get-PhysicalDisk | ForEach-Object { $r = $_ | Get-StorageReliabilityCounter "
                        "-ErrorAction SilentlyContinue; [pscustomobject]@{Name=$_.FriendlyName; "
                        "Health=[string]$_.HealthStatus; Size=$_.Size; Wear=$r.Wear; Temp=$r.Temperature; "
                        "Hours=$r.PowerOnHours} } | ConvertTo-Json -Compress", 60)
        try:
            data = json.loads(out[out.find("["):] if "[" in out else out[out.find("{"):])
        except ValueError:
            return []
        return data if isinstance(data, list) else [data]

    def show(disks):
        if not disks:
            import ui
            lb.append(ui.empty("ks-disk-symbolic", "Fant ingen diskinformasjon"))
        for d in disks:
            ok = str(d.get("Health", "")).lower() == "healthy"
            parts = [i18n.tr("God") if ok else i18n.tr("Bør sjekkes") + f" ({d.get('Health')})"]
            if d.get("Wear") is not None:
                parts.append(i18n.tr("{} % brukt av levetiden").replace("{}", str(d["Wear"])))
            if d.get("Temp"):
                parts.append(f"{d['Temp']} °C")
            if d.get("Hours"):
                parts.append(i18n.tr("{} timer").replace("{}", str(d["Hours"])))
            r = Gtk.Box(spacing=10)
            for side, v in (("top", 8), ("bottom", 8), ("start", 12), ("end", 12)):
                getattr(r, f"set_margin_{side}")(v)
            r.append(Gtk.Label(label=("✅  " if ok else "⚠️  ") + f"{d.get('Name')} · {human(d.get('Size') or 0)}",
                               xalign=0, hexpand=True))
            r.append(_dim(" · ".join(parts)))
            lb.append(r)
    _bg(work, show)
    page.box.append(c)


def _restore_card(page, card):
    c, i = card("Gjenoppretting", "Gå tilbake hvis en oppdatering eller et program ødelegger noe.")
    st = _dim("")
    row = Gtk.Box(spacing=8)
    mk = Gtk.Button(label=i18n.tr("Lag gjenopprettingspunkt nå"))
    mk.add_css_class("suggested-action")
    op = Gtk.Button(label=i18n.tr("Åpne Systemgjenoppretting"))
    row.append(mk)
    row.append(op)
    i.append(row)
    i.append(st)

    def make(*_):
        mk.set_sensitive(False)
        st.set_label(i18n.tr("Windows ber om administratortilgang …"))
        cmd = ("Start-Process powershell -Verb RunAs -Wait -ArgumentList '-NoProfile -Command "
               "Enable-ComputerRestore -Drive C:\\; Checkpoint-Computer -Description Kontrollsenter "
               "-RestorePointType MODIFY_SETTINGS'")

        def done(res):
            mk.set_sensitive(True)
            import ui
            ui.status(st, "Gjenopprettingspunkt laget ✓" if res[0] == 0 else "Ble avbrutt eller feilet")
        _bg(lambda: _ps(cmd, 300), done)
    mk.connect("clicked", make)
    op.connect("clicked", lambda *_: WS.run(["rstrui.exe"], 5))
    page.box.append(c)


# --------------------------------------------------------------------------
# Systemsjekk (Windows)
# --------------------------------------------------------------------------
class WinSysCheckDialog(Adw.Dialog):
    def __init__(self):
        super().__init__(title=i18n.tr("Systemsjekk"), content_width=640, content_height=560)
        tv = Adw.ToolbarView()
        tv.add_top_bar(Adw.HeaderBar())
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side in ("top", "bottom", "start", "end"):
            getattr(self.box, f"set_margin_{side}")(18)
        self.status = Gtk.Label(label=i18n.tr("Sjekker …"), xalign=0)
        self.box.append(self.status)
        self.lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.lb.add_css_class("boxed-list")
        self.box.append(self.lb)
        tv.set_content(Gtk.ScrolledWindow(child=self.box, hscrollbar_policy=Gtk.PolicyType.NEVER))
        self.set_child(tv)
        _bg(self.checks, self.show)

    @staticmethod
    def checks():
        import psutil
        res = []
        from sensors_win import Lhm
        res.append(("LibreHardwareMonitor", "ok" if Lhm.ok else "warn",
                    "Svarer – temperaturer og vifter virker" if Lhm.ok else
                    "Svarer ikke – CPU-temperatur og viftestyring mangler",
                    None if Lhm.ok else ("Start LibreHardwareMonitor",
                                         lambda: WS.run(["schtasks", "/run", "/tn", Lhm.TASK], 15))))
        for p in psutil.disk_partitions():
            try:
                u = psutil.disk_usage(p.mountpoint)
            except OSError:
                continue
            pct = u.used / u.total * 100 if u.total else 0
            res.append((f"Disk {p.mountpoint}", "ok" if pct < 85 else "warn" if pct < 95 else "error",
                        f"{pct:.0f} % full · {human(u.free)} ledig", None))
        code, out = WS.run(["winget", "upgrade", "--accept-source-agreements", "--disable-interactivity"], 120)
        n = len([ln for ln in out.splitlines() if re.search(r"\s\S+\s+\S+\s+\S+\s+winget\s*$", ln)])
        res.append(("Programoppdateringer (winget)", "ok" if n == 0 else "warn",
                    "Alt er oppdatert" if n == 0 else f"{n} programmer kan oppdateres",
                    None if n == 0 else ("Oppdater alle", lambda: WS.run(
                        ["winget", "upgrade", "--all", "--silent", "--accept-package-agreements",
                         "--accept-source-agreements"], 1800))))
        code, out = _ps("$s = New-Object -ComObject Microsoft.Update.Session; "
                        "($s.CreateUpdateSearcher().Search('IsInstalled=0 and IsHidden=0')).Updates.Count", 120)
        try:
            wu = int(out.strip().splitlines()[-1])
        except (ValueError, IndexError):
            wu = -1
        res.append(("Windows Update", "ok" if wu == 0 else "warn",
                    "Ingen ventende oppdateringer" if wu == 0 else
                    (f"{wu} oppdateringer venter" if wu > 0 else "Kunne ikke sjekke"),
                    None if wu == 0 else ("Åpne Windows Update", lambda: WS.open_uri("ms-settings:windowsupdate"))))
        return res

    def show(self, res):
        bad = sum(1 for r in res if r[1] != "ok")
        self.status.set_label(i18n.tr("✓ Alt ser bra ut") if not bad else
                              i18n.tr("{} ting bør sjekkes").replace("{}", str(bad)))
        for title, level, detail, fix in res:
            r = Gtk.Box(spacing=10)
            for side, v in (("top", 8), ("bottom", 8), ("start", 12), ("end", 10)):
                getattr(r, f"set_margin_{side}")(v)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            col.append(Gtk.Label(label={"ok": "✅", "warn": "⚠️", "error": "❌"}[level] + "  " + i18n.tr(title),
                                 xalign=0))
            col.append(_dim(detail))
            r.append(col)
            if fix:
                b = Gtk.Button(label=i18n.tr(fix[0]), valign=Gtk.Align.CENTER)
                b.add_css_class("suggested-action")

                def go(btn, f=fix[1]):
                    btn.set_sensitive(False)
                    _bg(f, lambda _r: btn.set_label("✓"))
                b.connect("clicked", go)
                r.append(b)
            self.lb.append(r)
