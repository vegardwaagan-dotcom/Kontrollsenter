"""Nettverk: ping til ruter, NAS og spilltjenere, hastighetstest, og hvilke programmer som bruker nettet."""
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk  # noqa: E402

import i18n  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
DOWN_URL = "https://speed.cloudflare.com/__down?bytes=50000000"
UP_URL = "https://speed.cloudflare.com/__up"


def gateway():
    if sys.platform == "win32":
        import winsupport
        code, out = winsupport.run(["powershell", "-NoProfile", "-Command",
                                    "(Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Sort-Object RouteMetric | "
                                    "Select-Object -First 1).NextHop"], 15)
        m = re.search(r"\d+\.\d+\.\d+\.\d+", out)
        return m.group(0) if m else None
    try:
        out = subprocess.run(["ip", "-4", "route", "show", "default"], capture_output=True, text=True, timeout=5).stdout
        m = re.search(r"via (\S+)", out)
        return m.group(1) if m else None
    except (OSError, subprocess.SubprocessError):
        return None


def targets():
    t = []
    gw = gateway()
    if gw:
        t.append(("Ruter", gw))
    try:
        import lanupdate
        t.append(("NAS (hjemmenett)", lanupdate._split()[0]))
    except Exception:  # noqa: BLE001
        pass
    t += [("Cloudflare (internett)", "1.1.1.1"), ("Google", "8.8.8.8"),
          ("Steam", "store.steampowered.com"), ("Battle.net (Europa)", "eu.actual.battle.net"),
          ("Discord", "discord.com")]
    return t


def ping(host, count=5):
    """(snitt ms, tap i %) eller (None, 100)."""
    if sys.platform == "win32":
        import winsupport
        code, out = winsupport.run(["ping", "-n", str(count), "-w", "2000", host], count * 3 + 6)
        times = [int(t) for t in re.findall(r"[=<](\d+)\s*ms", out, re.I)]
        loss = re.search(r"\((\d+)\s*%", out)
        replies = [t for t in times]
        avg_m = re.search(r"(?:Average|Gjennomsnitt|Middel)\w*\s*=\s*(\d+)\s*ms", out, re.I)
        avg = float(avg_m.group(1)) if avg_m else (sum(replies) / len(replies) if replies else None)
        return avg, (float(loss.group(1)) if loss else (0.0 if replies else 100.0))
    try:
        r = subprocess.run(["ping", "-n", "-q", "-c", str(count), "-i", "0.25", "-W", "2", host],
                           capture_output=True, text=True, timeout=count * 2 + 6)
    except (OSError, subprocess.SubprocessError):
        return None, 100
    loss = re.search(r"([\d.]+)% packet loss", r.stdout)
    avg = re.search(r"= [\d.]+/([\d.]+)/", r.stdout)
    return (float(avg.group(1)) if avg else None), (float(loss.group(1)) if loss else 100)


def _parallel(job, streams=4, limit=12.0):
    """Kjør job(stopp_tid, legg_til) i flere tråder samtidig. Returnerer Mbit/s."""
    got = [0]
    lock = threading.Lock()
    t0 = time.monotonic()
    stop = t0 + limit

    def add(n):
        with lock:
            got[0] += n

    th = [threading.Thread(target=job, args=(stop, add), daemon=True) for _ in range(streams)]
    for t in th:
        t.start()
    for t in th:
        t.join(limit + 15)
    return got[0] * 8 / max(time.monotonic() - t0, 1e-3) / 1e6, got[0]


def speed_down(progress=None):
    def job(stop, add):
        try:
            req = urllib.request.Request(DOWN_URL, headers=UA)
            with urllib.request.urlopen(req, timeout=20) as r:
                while time.monotonic() < stop:
                    b = r.read(256 * 1024)
                    if not b:
                        break
                    add(len(b))
        except OSError:
            pass
    mbit, n = _parallel(job)
    if n == 0:
        raise OSError(i18n.tr("ingen svar fra testtjeneren"))
    return mbit


def speed_up(size=8_000_000):
    data = os.urandom(size)

    def job(stop, add):
        while time.monotonic() < stop - 1:
            try:
                req = urllib.request.Request(UP_URL, data=data, method="POST",
                                             headers={**UA, "Content-Type": "application/octet-stream"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    r.read()
                add(size)
            except OSError:
                return
    mbit, n = _parallel(job, streams=4, limit=10.0)
    if n == 0:
        raise OSError(i18n.tr("ingen svar fra testtjeneren"))
    return mbit


def _prog_name(pid, fallback):
    try:
        exe = os.path.basename(os.readlink(f"/proc/{pid}/exe"))
        if exe and exe not in ("bwrap", "python3", "python", "node", "bash", "sh", "wine64-preloader", "wineserver"):
            return exe
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            args = [a.decode(errors="replace") for a in f.read().split(b"\0") if a]
        for a in args:
            base = os.path.basename(a)
            if base and not base.startswith("-") and base not in ("python3", "python", "node", "bash", "sh"):
                return base[:40]
    except OSError:
        pass
    return fallback


def connections():
    """[(program, antall forbindelser, eksempler på mål)] – egne programmer (uten root)."""
    if sys.platform == "win32":
        import psutil
        progs = {}
        for c in psutil.net_connections(kind="inet"):
            if c.status != "ESTABLISHED" or not c.raddr or not c.pid:
                continue
            try:
                name = psutil.Process(c.pid).name().replace(".exe", "")
            except Exception:  # noqa: BLE001
                continue
            e = progs.setdefault(name, [0, set()])
            e[0] += 1
            e[1].add(c.raddr.ip)
        return sorted(((n, c, sorted(p)[:3]) for n, (c, p) in progs.items()), key=lambda x: -x[1])
    try:
        out = subprocess.run(["ss", "-tunpH", "state", "established"], capture_output=True, text=True,
                             timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    progs = {}
    for line in out.splitlines():
        m = re.search(r'users:\(\("([^"]+)",pid=(\d+)', line)
        if not m:
            continue
        cols = line.split()
        peer = cols[4] if len(cols) > 4 else ""
        name = _prog_name(m.group(2), m.group(1))
        e = progs.setdefault(name, [0, set()])
        e[0] += 1
        e[1].add(peer.rsplit(":", 1)[0].strip("[]"))
    return sorted(((n, c, sorted(p)[:3]) for n, (c, p) in progs.items()), key=lambda x: -x[1])


def card(title, subtitle=None, icon=None):
    import automation
    return automation.card(title, subtitle, icon)


class NetworkPage(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(12)
        self.box = box
        self.set_child(box)
        self._ping_card()
        self._speed_card()
        self._conn_card()

    # --- ping -----------------------------------------------------------------
    def _ping_card(self):
        c, i, head = card("Forsinkelse (ping)", "Hvor raskt PC-en får svar. Under 20 ms er utmerket for spill, "
                                                "over 80 ms merkes. Tap betyr at pakker forsvinner.", "ks-network-symbolic")
        b = Gtk.Button(label=i18n.tr("Mål på nytt"), valign=Gtk.Align.CENTER)
        b.add_css_class("flat")
        head.append(b)
        self.ping_grid = Gtk.Grid(column_spacing=18, row_spacing=6)
        i.append(self.ping_grid)
        b.connect("clicked", lambda *_: self.run_ping())
        self.box.append(c)
        self.run_ping()

    def run_ping(self):
        g = self.ping_grid
        while (ch := g.get_first_child()):
            g.remove(ch)
        self.ping_rows = {}
        for r, (name, host) in enumerate(targets()):
            a = Gtk.Label(label=i18n.tr(name), xalign=0, hexpand=True)
            h = Gtk.Label(label=host, xalign=0)
            h.add_css_class("dim-label")
            h.add_css_class("caption")
            v = Gtk.Label(label="…", xalign=1)
            v.add_css_class("numeric")
            g.attach(a, 0, r, 1, 1)
            g.attach(h, 1, r, 1, 1)
            g.attach(v, 2, r, 1, 1)

            def work(host=host, v=v):
                ms, loss = ping(host)

                def show():
                    if ms is None:
                        v.set_label(i18n.tr("svarer ikke"))
                        v.remove_css_class("success")
                        v.add_css_class("dim-label")
                    else:
                        v.set_label(f"{ms:.0f} ms" + (f" · {loss:.0f} % tap" if loss else ""))
                        v.add_css_class("success" if ms < 30 and not loss else "warning" if ms < 80 else "error")
                    return False
                GLib.idle_add(show)
            threading.Thread(target=work, daemon=True).start()

    # --- hastighet ----------------------------------------------------------------
    def _speed_card(self):
        c, i, head = card("Hastighetstest", "Måler nedlasting og opplasting mot Cloudflare med fire forbindelser "
                                            "samtidig. Tar rundt 25 sekunder og bruker et par hundre MB data.")
        row = Gtk.Box(spacing=24, halign=Gtk.Align.START)
        self.sp = {}
        for key, name in (("down", "Nedlasting"), ("up", "Opplasting")):
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            n = Gtk.Label(label=i18n.tr(name), xalign=0)
            n.add_css_class("dim-label")
            v = Gtk.Label(label="–", xalign=0)
            v.add_css_class("title-1")
            v.add_css_class("numeric")
            col.append(n)
            col.append(v)
            row.append(col)
            self.sp[key] = v
        i.append(row)
        self.sp_btn = Gtk.Button(label=i18n.tr("Start hastighetstest"), halign=Gtk.Align.START)
        self.sp_btn.add_css_class("suggested-action")
        self.sp_btn.connect("clicked", self.run_speed)
        i.append(self.sp_btn)
        self.sp_status = Gtk.Label(xalign=0)
        self.sp_status.add_css_class("dim-label")
        i.append(self.sp_status)
        self.box.append(c)

    def run_speed(self, *_):
        self.sp_btn.set_sensitive(False)
        self.sp_status.set_label(i18n.tr("Måler nedlasting …"))
        for v in self.sp.values():
            v.set_label("…")

        def work():
            try:
                d = speed_down(lambda m: GLib.idle_add(self.sp["down"].set_label, f"{m:.0f} Mbit/s"))
                GLib.idle_add(self.sp["down"].set_label, f"{d:.0f} Mbit/s")
                GLib.idle_add(self.sp_status.set_label, i18n.tr("Måler opplasting …"))
                u = speed_up()
                GLib.idle_add(self.sp["up"].set_label, f"{u:.0f} Mbit/s")
                GLib.idle_add(self.sp_status.set_label, time.strftime(i18n.tr("Målt %H:%M")))
            except Exception as e:  # noqa: BLE001
                GLib.idle_add(self.sp_status.set_label, i18n.tr("Kunne ikke måle: ") + str(e))
            GLib.idle_add(self.sp_btn.set_sensitive, True)
        threading.Thread(target=work, daemon=True).start()

    # --- programmer -------------------------------------------------------------
    def _conn_card(self):
        c, i, head = card("Programmer som bruker nettet", "Åpne forbindelser akkurat nå, per program. "
                                                          "(Systemtjenester som kjører som root vises ikke.)")
        b = Gtk.Button(label=i18n.tr("Oppdater"), valign=Gtk.Align.CENTER)
        b.add_css_class("flat")
        head.append(b)
        self.conn_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.conn_list.add_css_class("boxed-list")
        i.append(self.conn_list)
        b.connect("clicked", lambda *_: self.run_conn())
        self.box.append(c)
        self.run_conn()

    def run_conn(self):
        def show(items):
            lb = self.conn_list
            while (ch := lb.get_first_child()):
                lb.remove(ch)
            if not items:
                import ui
                lb.append(Gtk.ListBoxRow(child=ui.empty("ks-network-symbolic", "Ingen åpne forbindelser"),
                                         activatable=False))
            for name, n, peers in items[:20]:
                r = Gtk.Box(spacing=10)
                for side, v in (("top", 6), ("bottom", 6), ("start", 12), ("end", 12)):
                    getattr(r, f"set_margin_{side}")(v)
                col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
                col.append(Gtk.Label(label=name, xalign=0, ellipsize=3))
                p = Gtk.Label(label=", ".join(peers), xalign=0, ellipsize=3)
                p.add_css_class("caption")
                p.add_css_class("dim-label")
                col.append(p)
                r.append(col)
                cnt = Gtk.Label(label=f"{n} " + i18n.tr("forbindelser" if n != 1 else "forbindelse"))
                cnt.add_css_class("numeric")
                r.append(cnt)
                lb.append(r)
            return False
        threading.Thread(target=lambda: GLib.idle_add(show, connections()), daemon=True).start()
