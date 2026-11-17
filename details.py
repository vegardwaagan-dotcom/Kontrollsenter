"""Mye info om én kategori (CPU, GPU, minne, disk, nett, temperaturer, strøm, strømmodus, batteri).

Brukes av detaljvinduet når du trykker på en flis i Oversikt på PC-en, og av mobilappen (/api/x/detail?k=…).
Svaret er ren data:
  {"k", "title", "value", "sub",
   "series":   [{"name", "color", "unit", "max", "pts": [...]}],      # siste 10 min, ca. 120 punkter
   "sections": [{"title", "rows": [[navn, verdi], ...]}               # nøkkeltall
                {"title", "bars": [[navn, prosent, tekst], ...]}]}     # stolper (kjerner, disker …)
"""
import os
import platform
import sys
import time
from collections import deque

IS_WIN = sys.platform == "win32"
KINDS = ("cpu", "gpu", "mem", "disk", "net", "temps", "watt", "mode", "bat")
TITLES = {"cpu": "Prosessor", "gpu": "Skjermkort", "mem": "Minne (RAM)", "disk": "Disk", "net": "Nettverk",
          "temps": "Temperaturer", "watt": "Strømforbruk", "mode": "Strømmodus", "bat": "Batteri"}

# historikk for det som ikke har egen graf i vinduet (legges til hvert sekund av vinduet)
HIST = {"temp": deque(maxlen=3600), "watt": deque(maxlen=3600)}


def record(win):
    rows = (getattr(win, "_remote", None) or {}).get("temps") or []
    if rows:
        HIST["temp"].append(max(r[2] for r in rows))
    w = (getattr(win, "_power", None) or {}).get("total")
    if w:
        HIST["watt"].append(w)


def _fb(n):
    from sensors import fmt_bytes
    return fmt_bytes(n or 0)


def _fr(n):
    from sensors import fmt_rate
    return fmt_rate(n or 0)


def _pts(seq, n=120, span=600):
    v = [float(x or 0) for x in list(seq)[-span:]]
    if len(v) <= n:
        return [round(x, 2) for x in v]
    step = len(v) / n
    out = []
    for i in range(n):
        part = v[int(i * step):max(int((i + 1) * step), int(i * step) + 1)]
        out.append(round(sum(part) / len(part), 2))
    return out


def _graph(card, i=0):
    g = getattr(card, "graph", None) if card is not None else None
    return g.series[i] if g is not None and len(g.series) > i else []


def _uptime():
    try:
        import psutil
        s = int(time.time() - psutil.boot_time())
    except Exception:  # noqa: BLE001
        return "–"
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    return (f"{d} d " if d else "") + f"{h} t {s // 60} min"


_PROCS = {"t": 0, "list": [], "busy": False}


def _top(by="cpu", n=8):
    """Programmene som bruker mest – fra en liste som oppdateres i bakgrunnen (blokkerer aldri vinduet)."""
    import threading
    if time.time() - _PROCS["t"] > 3 and not _PROCS["busy"]:
        _PROCS["busy"] = True

        def work():
            try:
                import remote_extra
                _PROCS["list"] = remote_extra.processes()
                _PROCS["t"] = time.time()
            except Exception:  # noqa: BLE001
                pass
            finally:
                _PROCS["busy"] = False
        threading.Thread(target=work, daemon=True).start()
    lst = sorted(_PROCS["list"], key=lambda m: -m[by])
    return [[m["name"], (f"{m['cpu']:.1f} %  ·  " if by == "cpu" else "") + _fb(m["mem"])] for m in lst[:n]]


def _t(v, unit, digits=0):
    return "–" if v is None else f"{v:.{digits}f} {unit}"


def collect(win, k):
    k = k if k in KINDS else "cpu"
    fn = globals().get("_" + k)
    d = {"k": k, "title": TITLES[k], "value": "", "sub": "", "series": [], "sections": []}
    try:
        fn(win, d)
    except Exception as e:  # noqa: BLE001
        import applog
        applog.log.exception("detaljer %s", k)
        d["sections"].append({"title": "Feil", "rows": [["Kunne ikke hente alt", str(e)]]})
    return d


# --------------------------------------------------------------------------
def _cpu(win, d):
    import psutil
    from sensors import CpuReader, cpu_freqs_ghz, cpu_model
    load = getattr(win, "_cpu_load", 0) or 0
    t = getattr(win, "_cpu_t", None)
    d["title"] = cpu_model() or "Prosessor"
    d["value"] = f"{load:.0f} %"
    d["sub"] = " · ".join(x for x in (_t(t, "°C") if t is not None else "",
                                       f"{psutil.cpu_count()} tråder") if x)
    d["series"].append({"name": "Belastning", "color": "#5b8cff", "unit": "%", "max": 100,
                        "pts": _pts(_graph(getattr(win, "c_cpu", None)))})
    f = CpuReader.freq_ghz()
    base, mx = cpu_freqs_ghz() if not IS_WIN else (None, None)
    rows = [["Belastning", f"{load:.0f} %"], ["Temperatur", _t(t, "°C")],
            ["Frekvens nå", _t(f, "GHz", 2)]]
    if base:
        rows.append(["Grunnfrekvens", f"{base:.2f} GHz"])
    if mx:
        rows.append(["Maks turbo", f"{mx:.2f} GHz"])
    try:
        la = os.getloadavg()
        rows.append(["Last (1 / 5 / 15 min)", f"{la[0]:.2f} / {la[1]:.2f} / {la[2]:.2f}"])
    except (OSError, AttributeError):
        pass
    d["sections"].append({"title": "Nå", "rows": rows})
    d["sections"].append({"title": "Prosessoren", "rows": [
        ["Modell", cpu_model() or "–"], ["Kjerner", str(psutil.cpu_count(logical=False) or "–")],
        ["Tråder", str(psutil.cpu_count() or "–")], ["Arkitektur", platform.machine() or "–"],
        ["Prosesser", str(len(psutil.pids()))], ["Oppetid", _uptime()]]})
    bars = [[f"Tråd {i}", round(b.get_value()), f"{b.get_value():.0f} %"]
            for i, (_k, b) in enumerate(getattr(win, "core_bars", []))]
    if bars:
        d["sections"].append({"title": "Hver tråd", "bars": bars})
    top = _top("cpu")
    if top:
        d["sections"].append({"title": "Bruker mest CPU", "rows": top})


def _gpu(win, d):
    nv = getattr(getattr(win, "nvidia", None), "data", None) if getattr(getattr(win, "nvidia", None),
                                                                        "available", False) else None
    if nv:
        d["title"] = nv.get("name") or "Skjermkort"
        d["value"] = _t(nv.get("util"), "%")
        d["sub"] = _t(nv.get("temp"), "°C")
        d["series"].append({"name": "Belastning", "color": "#f58c26", "unit": "%", "max": 100,
                            "pts": _pts(_graph(getattr(win, "c_gpu", None)))})
        rows = [["Belastning", _t(nv.get("util"), "%")], ["Temperatur", _t(nv.get("temp"), "°C")],
                ["Effekt", _t(nv.get("power"), "W") + (f" av {nv['limit']:.0f} W" if nv.get("limit") else "")],
                ["Vifte", _t(nv.get("fan"), "%")]]
        if nv.get("clock"):
            rows.append(["Klokke", f"{nv['clock']:.0f} MHz" + (f" (maks {nv['clock_max']:.0f})"
                                                                 if nv.get("clock_max") else "")])
        if nv.get("mem_total"):
            rows.append(["Videominne (VRAM)", f"{nv['mem_used'] / 1024:.1f} av {nv['mem_total'] / 1024:.1f} GB"])
        lim = nv.get("limits")
        if lim and all(lim):
            rows.append(["Strømgrense (min / standard / maks)", f"{lim[0]:.0f} / {lim[1]:.0f} / {lim[2]:.0f} W"])
        d["sections"].append({"title": "Nå", "rows": rows})
        if nv.get("mem_total"):
            p = 100 * (nv.get("mem_used") or 0) / nv["mem_total"]
            d["sections"].append({"title": "Videominne", "bars": [["VRAM", round(p), f"{p:.0f} %"]]})
    amd = getattr(win, "amd", []) or []
    from sensors import read
    for dev, card in zip(amd, getattr(win, "c_amd", [])):
        busy = float(read(os.path.join(dev, "gpu_busy_percent"), "0") or 0)
        vu, vt = read(os.path.join(dev, "mem_info_vram_used")), read(os.path.join(dev, "mem_info_vram_total"))
        if not nv:
            d["title"], d["value"] = "AMD-skjermkort", f"{busy:.0f} %"
        d["series"].append({"name": "AMD", "color": "#e0454a", "unit": "%", "max": 100, "pts": _pts(_graph(card))})
        rows = [["Belastning", f"{busy:.0f} %"]]
        if vu and vt:
            rows.append(["Videominne (VRAM)", f"{_fb(int(vu))} av {_fb(int(vt))}"])
        for f, name in (("pp_dpm_sclk", "Klokke"), ("pp_dpm_mclk", "Minneklokke")):
            for line in (read(os.path.join(dev, f)) or "").splitlines():
                if line.strip().endswith("*"):
                    rows.append([name, line.split(":", 1)[-1].strip(" *")])
        d["sections"].append({"title": "AMD", "rows": rows})
    if not d["sections"]:
        d["sections"].append({"title": "Skjermkort", "rows": [["Status", "Fant ingen data fra skjermkortet"]]})
    top = _top("mem", 5)
    if top:
        d["sections"].append({"title": "Programmer som kjører nå", "rows": top})


def _mem(win, d):
    import psutil
    vm, sw = psutil.virtual_memory(), psutil.swap_memory()
    d["value"] = f"{vm.percent:.0f} %"
    d["sub"] = f"{_fb(vm.total - vm.available)} av {_fb(vm.total)}"
    d["series"].append({"name": "I bruk", "color": "#33b86b", "unit": "%", "max": 100,
                        "pts": _pts(_graph(getattr(win, "c_mem", None)))})
    rows = [["Totalt", _fb(vm.total)], ["I bruk", _fb(vm.total - vm.available)], ["Ledig", _fb(vm.available)]]
    for attr, name in (("cached", "Hurtigbuffer"), ("buffers", "Buffere"), ("shared", "Delt")):
        if getattr(vm, attr, None):
            rows.append([name, _fb(getattr(vm, attr))])
    rows.append(["Swap", f"{_fb(sw.used)} av {_fb(sw.total)}"])
    d["sections"].append({"title": "Nå", "rows": rows})
    bars = [["RAM", round(vm.percent), f"{vm.percent:.0f} %"]]
    if sw.total:
        bars.append(["Swap", round(sw.percent), f"{sw.percent:.0f} %"])
    d["sections"].append({"title": "Fylt opp", "bars": bars})
    top = _top("mem")
    if top:
        d["sections"].append({"title": "Bruker mest minne", "rows": top})


def _disk(win, d):
    import psutil
    from cards import list_filesystems, nice_mount
    g = getattr(getattr(win, "c_disk", None), "graph", None)
    rr = g.series[0][-1] if g and g.series[0] else 0
    wr = g.series[1][-1] if g and g.series[1] else 0
    d["value"] = _fr(rr + wr)
    d["sub"] = f"Les {_fr(rr)} · Skriv {_fr(wr)}"
    d["series"] += [{"name": "Les", "color": "#8a5cff", "unit": "B/s", "pts": _pts(_graph(getattr(win, "c_disk", None)))},
                    {"name": "Skriv", "color": "#21a8b3", "unit": "B/s",
                     "pts": _pts(_graph(getattr(win, "c_disk", None), 1))}]
    bars, rows = [], []
    for fs in list_filesystems():
        p = 100 * fs["used"] / fs["total"] if fs.get("total") else 0
        name = nice_mount(fs["mnt"]) if not IS_WIN else fs["mnt"]
        bars.append([name, round(p), f"{_fb(fs['free'])} ledig av {_fb(fs['total'])}"])
        rows.append([name, f"{fs.get('fs', '')} · {fs.get('dev', '')}"])
    if bars:
        d["sections"].append({"title": "Plass", "bars": bars})
    io = psutil.disk_io_counters()
    if io:
        d["sections"].append({"title": "Siden PC-en startet", "rows": [
            ["Lest", _fb(io.read_bytes)], ["Skrevet", _fb(io.write_bytes)], ["Oppetid", _uptime()]]})
    if rows:
        d["sections"].append({"title": "Partisjoner", "rows": rows})


def _net(win, d):
    import socket

    import psutil
    g = getattr(getattr(win, "c_net", None), "graph", None)
    rx = g.series[0][-1] if g and g.series[0] else 0
    tx = g.series[1][-1] if g and g.series[1] else 0
    d["value"] = _fr(rx)
    d["sub"] = f"↓ {_fr(rx)} · ↑ {_fr(tx)}"
    d["series"] += [{"name": "Ned", "color": "#33b86b", "unit": "B/s", "pts": _pts(_graph(getattr(win, "c_net", None)))},
                    {"name": "Opp", "color": "#5b8cff", "unit": "B/s",
                     "pts": _pts(_graph(getattr(win, "c_net", None), 1))}]
    io = psutil.net_io_counters()
    d["sections"].append({"title": "Nå", "rows": [
        ["Ned", _fr(rx)], ["Opp", _fr(tx)], ["Mottatt siden start", _fb(io.bytes_recv)],
        ["Sendt siden start", _fb(io.bytes_sent)], ["Navn på nettet", socket.gethostname()]]})
    stats, addrs = psutil.net_if_stats(), psutil.net_if_addrs()
    rows = []
    for name, st in sorted(stats.items()):
        if not st.isup or name == "lo" or name.startswith(("veth", "docker", "br-", "virbr", "Loopback")):
            continue
        ips = [a.address for a in addrs.get(name, []) if a.family == socket.AF_INET]
        if not ips:
            continue
        speed = f" · {st.speed} Mbit/s" if st.speed else ""
        rows.append([name, ", ".join(ips) + speed])
    if rows:
        d["sections"].append({"title": "Nettverkskort", "rows": rows})


def _temps(win, d):
    rows = (getattr(win, "_remote", None) or {}).get("temps") or []
    hot = max((r[2] for r in rows), default=None)
    d["value"] = _t(hot, "°C")
    d["sub"] = "høyeste temperatur"
    d["series"].append({"name": "Varmest", "color": "#e0454a", "unit": "°C", "pts": _pts(HIST["temp"])})
    groups = {}
    for dev, lbl, t in rows:
        groups.setdefault(dev, []).append([lbl, round(min(100, t)), f"{t:.0f} °C"])
    for dev, bars in groups.items():
        d["sections"].append({"title": dev, "bars": bars})
    if not rows:
        d["sections"].append({"title": "Temperaturer", "rows": [["Status", "Fant ingen temperaturmålere"]]})


def _watt(win, d):
    p = getattr(win, "_power", None) or {}
    tot = p.get("total")
    d["value"] = _t(tot, "W")
    d["sub"] = "målt" if p.get("measured") else "anslått"
    d["series"].append({"name": "Strøm", "color": "#f5b026", "unit": "W", "pts": _pts(HIST["watt"])})
    rows = [["Totalt nå", _t(tot, "W")], ["Prosessor", _t(p.get("cpu"), "W")], ["Skjermkort", _t(p.get("gpu"), "W")]]
    if p.get("measured") is not None:
        rows.append(["Målt fra strømforsyningen", _t(p.get("measured"), "W")])
    d["sections"].append({"title": "Nå", "rows": rows})
    en = getattr(win, "energy", None)
    if en:
        import power
        price = power.load()["price"]
        wh = en.today_wh()
        avg = en.avg_watts()
        r2 = [["I dag", f"{wh / 1000:.2f} kWh · {wh / 1000 * price:.2f} kr"], ["Strømpris", f"{price:.2f} kr/kWh"]]
        if avg:
            r2.append(["Snitt", f"{avg:.0f} W"])
            r2.append(["En måned (8 t/døgn)", f"{avg * 8 * 30 / 1000:.0f} kWh · {avg * 8 * 30 / 1000 * price:.0f} kr"])
        d["sections"].append({"title": "Kostnad", "rows": r2})


def _mode(win, d):
    import cards
    pc = getattr(win, "power", None)
    cur = None
    for key, b in (getattr(pc, "buttons", {}) or {}).items():
        if b.get_active():
            cur = key
    d["value"] = cards.MODE_NAMES.get(cur, "–")
    rows = [[name + ("  ✓" if key == cur else ""), desc] for key, name, _i, desc in cards.MODES]
    d["sections"].append({"title": "Strømmodusene", "rows": rows})
    p = getattr(win, "_power", None) or {}
    from sensors import CpuReader
    d["sections"].append({"title": "Nå", "rows": [
        ["Frekvens nå", _t(CpuReader.freq_ghz(), "GHz", 2)], ["Strømforbruk", _t(p.get("total"), "W")]]})
    d["series"].append({"name": "Strøm", "color": "#f5b026", "unit": "W", "pts": _pts(HIST["watt"])})


def _bat(win, d):
    import psutil
    b = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    if b:
        d["value"] = f"{b.percent:.0f} %"
        left = "–"
        if b.secsleft not in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN) and b.secsleft > 0:
            left = f"{b.secsleft // 3600} t {b.secsleft % 3600 // 60} min"
        d["sub"] = "lader" if b.power_plugged else "på batteri"
        d["sections"].append({"title": "Laptop", "rows": [
            ["Nivå", f"{b.percent:.0f} %"], ["Strøm", "Tilkoblet" if b.power_plugged else "På batteri"],
            ["Tid igjen", left]]})
        d["series"].append({"name": "Batteri", "color": "#33b86b", "unit": "%", "max": 100,
                            "pts": _pts(_graph(getattr(win, "c_bat", None)))})
    try:
        import batteries
        devs = batteries.cached()
    except Exception:  # noqa: BLE001
        devs = []
    bars = []
    for x in devs:
        name = (batteries.ICON.get(x.get("kind"), "") + " " + (x.get("name") or "Enhet")).strip()
        bars.append([name, x.get("pct") or 0, batteries.label(x)])
    if bars:
        d["sections"].append({"title": "Trådløse enheter", "bars": bars})
    if not d["sections"]:
        d["sections"].append({"title": "Batteri", "rows": [["Status", "Fant ingen batterier"]]})
