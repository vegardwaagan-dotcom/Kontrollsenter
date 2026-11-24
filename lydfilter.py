"""Lydfiltre med PipeWire (Linux): virtuell 7.1 i hodesettet, equalizer per utgang og støyfilter på mikrofonen.

Alt bygger på det PipeWire har innebygd (filter-chain med convolver/biquad, og WebRTC-ekkofjerning med støyfilter) –
ingenting lastes ned eller installeres. Hvert filter kjører som en egen liten «pipewire -c <fil>»-prosess som lager
en virtuell utgang/mikrofon; slås filteret av, stoppes prosessen og den virtuelle enheten forsvinner.

Virtuell surround: øre-filtrene (HRIR) regnes ut her med en enkel kulehode-modell – tidsforskjell mellom ørene
(Woodworth), lyddemping og mørkere klang på øret som vender bort, og en svak romrefleks så lyden havner utenfor hodet.

Windows har ikke noe tilsvarende API – der åpnes Windows' egne innstillinger (Windows Sonic / lydforbedringer).
"""
import array
import json
import math
import os
import signal
import struct
import subprocess
import sys

IS_WIN = sys.platform == "win32"
CFG = os.path.expanduser("~/.config/systemmonitor/lydfilter.json")
DIR = os.path.expanduser("~/.cache/systemmonitor/lydfilter")
RATE = 48000
DEF = {"surround": False, "surround_target": "", "eq": False, "eq_target": "", "eq_preset": "flat",
       "eq_gains": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], "noise": False, "noise_strength": "middels"}

# 10-bånds equalizer
EQ_FREQ = [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
PRESETS = {
    "flat": ("Flat (av)", [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
    "spill": ("Spill – fottrinn og detaljer", [-2, -1, -1, 0, 0, 1, 3, 4, 3, 1]),
    "film": ("Film – mer bass og tydelig tale", [4, 3, 1, 0, -1, 1, 2, 1, 1, 0]),
    "musikk": ("Musikk – lett V-form", [3, 2, 1, 0, -1, -1, 0, 1, 2, 3]),
    "tale": ("Tale / podkast", [-4, -3, -1, 0, 1, 2, 3, 2, 0, -2]),
    "bass": ("Ekstra bass", [6, 5, 3, 1, 0, 0, 0, 0, 0, 0]),
}
SURROUND_NAME = "ks_virtuell_surround"
EQ_NAME = "ks_equalizer"
NOISE_NAME = "ks_stoyfilter"


def cfg():
    try:
        return {**DEF, **json.load(open(CFG))}
    except (OSError, ValueError):
        return dict(DEF)


def set_(**kw):
    c = cfg()
    c.update(kw)
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    tmp = CFG + ".tmp"
    with open(tmp, "w") as f:
        json.dump(c, f)
    os.replace(tmp, CFG)
    return c


def available():
    return not IS_WIN and bool(_which("pipewire"))


def _which(n):
    import shutil
    return shutil.which(n)


# ------------------------------------------------------------------ prosessene
def _pidfile(name):
    return os.path.join(DIR, name + ".pid")


def running(name):
    try:
        pid = int(open(_pidfile(name)).read())
        cmd = open(f"/proc/{pid}/cmdline", "rb").read().decode(errors="ignore")
        return pid if name in cmd else 0
    except (OSError, ValueError):
        return 0


def _start(name, conf):
    stop(name)
    os.makedirs(DIR, exist_ok=True)
    path = os.path.join(DIR, name + ".conf")
    with open(path, "w") as f:
        f.write(conf)
    p = subprocess.Popen(["pipewire", "-c", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)                  # lever videre om Kontrollsenter lukkes
    with open(_pidfile(name), "w") as f:
        f.write(str(p.pid))
    return p.pid


def stop(name):
    pid = running(name)
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    try:
        os.remove(_pidfile(name))
    except OSError:
        pass


_HEAD = """context.properties = { log.level = 0 }
context.spa-libs = {
    audio.convert.* = audioconvert/libspa-audioconvert
    support.*       = support/libspa-support
}
context.modules = [
    { name = libpipewire-module-rt args = { } flags = [ ifexists nofail ] }
    { name = libpipewire-module-protocol-native }
    { name = libpipewire-module-client-node }
    { name = libpipewire-module-adapter }
"""


# ------------------------------------------------------------------ virtuell surround
# kanal: (vinkel i grader, 0 = rett fram, negativ = venstre)
SPK = [("FL", -30), ("FR", 30), ("FC", 0), ("LFE", 0), ("RL", -145), ("RR", 145), ("SL", -95), ("SR", 95)]


def _ear(az, ear, n=1024):
    """Impulsrespons for én høyttaler til ett øre (ear = -1 venstre, +1 høyre)."""
    a, c = 0.0875, 343.0
    th = math.radians(az)
    lat = math.asin(max(-1.0, min(1.0, math.sin(th))))          # sidevinkel (-90…90)
    side = 1 if lat > 0 else -1 if lat < 0 else 0
    far = side != 0 and side != ear                              # øret som vender bort
    itd = a / c * (abs(lat) + math.sin(abs(lat))) if far else 0.0
    d0 = int(round(itd * RATE)) + 2
    s = abs(math.sin(lat))
    gain = 10 ** ((-8.0 * s if far else 1.5 * s) / 20)            # hodeskygge og nærøre-økning
    alpha = 0.55 * s if far else 0.0                              # mørkere klang på øret bak hodet
    back = math.cos(th) < 0
    if back:
        alpha = max(alpha, 0.25)                                  # bakfra: litt mørkere (øremuslingen)
        gain *= 0.85
    h = [0.0] * n
    for k in range(n - d0):                                       # ett-pols lavpass = (1-α)·αᵏ
        v = (1 - alpha) * (alpha ** k) if alpha else (1.0 if k == 0 else 0.0)
        if v < 1e-5 and k > 0:
            break
        h[d0 + k] += gain * v
    for delay_ms, g in ((7.0, 0.18), (13.0, 0.10), (21.0, 0.05)):  # svake romreflekser → lyden utenfor hodet
        k = d0 + int(delay_ms * RATE / 1000) + (3 if far else 0)
        if k < n:
            h[k] += g * gain ** 0.5 * (0.8 if far else 1.0)
    return h


def hrir_file():
    """16-kanals WAV: for hver høyttaler i SPK – venstre øre, høyre øre."""
    os.makedirs(DIR, exist_ok=True)
    path = os.path.join(DIR, "hrir.wav")
    if os.path.exists(path):
        return path
    chans = []
    for _ch, az in SPK:
        chans.append(_ear(az, -1))
        chans.append(_ear(az, 1))
    peak = max(sum(abs(x) for x in h) for h in chans) or 1
    n, nch = len(chans[0]), len(chans)
    data = array.array("f", [0.0] * (n * nch))
    for j, h in enumerate(chans):
        for i, v in enumerate(h):
            data[i * nch + j] = v / peak * 0.9
    if sys.byteorder == "big":
        data.byteswap()
    raw = data.tobytes()
    fmt = struct.pack("<HHIIHH", 3, nch, RATE, RATE * nch * 4, nch * 4, 32)     # IEEE float
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 4 + 8 + len(fmt) + 8 + len(raw)) + b"WAVE")
        f.write(b"fmt " + struct.pack("<I", len(fmt)) + fmt)
        f.write(b"data" + struct.pack("<I", len(raw)) + raw)
    return path


def surround_conf(target=""):
    hr = hrir_file()
    nodes, links = [], []
    for k, (ch, _az) in enumerate(SPK):
        nodes.append(f'{{ type = builtin label = copy name = cp{ch} }}')
        for e, ear in enumerate(("L", "R")):
            nodes.append(f'{{ type = builtin label = convolver name = cv{ch}{ear} '
                         f'config = {{ filename = "{hr}" channel = {2 * k + e} }} }}')
            links.append(f'{{ output = "cp{ch}:Out" input = "cv{ch}{ear}:In" }}')
            links.append(f'{{ output = "cv{ch}{ear}:Out" input = "mix{ear}:In {k + 1}" }}')
    nodes += ['{ type = builtin label = mixer name = mixL }', '{ type = builtin label = mixer name = mixR }']
    inputs = " ".join(f'"cp{ch}:In"' for ch, _a in SPK)
    tgt = f'target.object = "{target}"' if target else ""
    return _HEAD + f"""    {{ name = libpipewire-module-filter-chain
        args = {{
            node.description = "Virtuell 7.1 i hodesettet (Kontrollsenter)"
            media.name = "Virtuell 7.1"
            filter.graph = {{
                nodes = [ {" ".join(nodes)} ]
                links = [ {" ".join(links)} ]
                inputs = [ {inputs} ]
                outputs = [ "mixL:Out" "mixR:Out" ]
            }}
            capture.props = {{
                node.name = "{SURROUND_NAME}"
                media.class = Audio/Sink
                audio.channels = 8
                audio.position = [ FL FR FC LFE RL RR SL SR ]
            }}
            playback.props = {{
                node.name = "{SURROUND_NAME}_ut"
                node.passive = true
                audio.channels = 2
                audio.position = [ FL FR ]
                {tgt}
            }}
        }}
    }}
]
"""


# ------------------------------------------------------------------ equalizer
def eq_conf(gains, target=""):
    nodes, links = [], []
    for i, (f, g) in enumerate(zip(EQ_FREQ, gains)):
        kind = "bq_lowshelf" if i == 0 else "bq_highshelf" if i == len(EQ_FREQ) - 1 else "bq_peaking"
        nodes.append(f'{{ type = builtin name = eq{i} label = {kind} control = {{ "Freq" = {f} "Q" = 1.0 '
                     f'"Gain" = {float(g):.1f} }} }}')
        if i:
            links.append(f'{{ output = "eq{i - 1}:Out" input = "eq{i}:In" }}')
    pre = -max(0.0, max(gains))                                    # forsterkning uten klipping
    tgt = f'target.object = "{target}"' if target else ""
    return _HEAD + f"""    {{ name = libpipewire-module-filter-chain
        args = {{
            node.description = "Equalizer (Kontrollsenter)"
            media.name = "Equalizer"
            filter.graph = {{
                nodes = [ {{ type = builtin name = pre label = linear control = {{ "Mult" = {10 ** (pre / 20):.4f} }} }} {" ".join(nodes)} ]
                links = [ {{ output = "pre:Out" input = "eq0:In" }} {" ".join(links)} ]
            }}
            audio.channels = 2
            audio.position = [ FL FR ]
            capture.props = {{
                node.name = "{EQ_NAME}"
                media.class = Audio/Sink
            }}
            playback.props = {{
                node.name = "{EQ_NAME}_ut"
                node.passive = true
                {tgt}
            }}
        }}
    }}
]
"""


# ------------------------------------------------------------------ støyfilter (WebRTC)
def noise_conf(strength="middels"):
    agc = "true"
    return _HEAD.replace("support.*       = support/libspa-support",
                         "support.*       = support/libspa-support\n    aec.*           = aec/libspa-aec-webrtc") + \
        f"""    {{ name = libpipewire-module-echo-cancel
        args = {{
            library.name = aec/libspa-aec-webrtc
            monitor.mode = true
            aec.args = {{
                webrtc.noise_suppression = true
                webrtc.high_pass_filter = true
                webrtc.gain_control = {agc}
                webrtc.extended_filter = false
                webrtc.delay_agnostic = true
            }}
            capture.props = {{ node.name = "{NOISE_NAME}_inn" node.passive = true }}
            source.props = {{ node.name = "{NOISE_NAME}" node.description = "Mikrofon med støyfilter (Kontrollsenter)" }}
            sink.props = {{ node.name = "{NOISE_NAME}_ekko" node.passive = true }}
            playback.props = {{ node.name = "{NOISE_NAME}_ekko_ut" node.passive = true }}
        }}
    }}
]
"""


# ------------------------------------------------------------------ på / av
def _pactl(*a):
    try:
        return subprocess.run(["pactl", *a], capture_output=True, text=True, timeout=8).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _wait_node(name, kind="sinks", secs=4.0):
    import time
    end = time.time() + secs
    while time.time() < end:
        if name in _pactl("list", "short", kind):
            return True
        time.sleep(0.2)
    return False


def _default_sink():
    return _pactl("get-default-sink")


def _real_sink(target):
    """Utgangen filteret skal spille på: valgt, ellers nåværende standard (som ikke er et av våre filtre)."""
    t = target or _default_sink()
    if t.startswith("ks_"):
        t = ""
    return t


def enable(kind, on, make_default=True, **kw):
    """kind = «surround», «eq» eller «noise». Returnerer en tekst til brukeren."""
    if IS_WIN:
        raise RuntimeError("på Windows: bruk «Windows Sonic» / lydforbedringer i Windows' lydinnstillinger")
    if not available():
        raise RuntimeError("PipeWire mangler")
    c = set_(**{kind: bool(on)}, **kw)
    name = {"surround": SURROUND_NAME, "eq": EQ_NAME, "noise": NOISE_NAME}[kind]
    if not on:
        prev = c.get(kind + "_prev_default")
        stop(name)
        if prev:
            _pactl("set-default-" + ("source" if kind == "noise" else "sink"), prev)
        return {"surround": "Virtuell surround er av", "eq": "Equalizeren er av", "noise": "Støyfilteret er av"}[kind]
    if kind == "surround":
        target = _real_sink(c.get("surround_target"))
        _start(name, surround_conf(target))
        ok = _wait_node(name)
    elif kind == "eq":
        target = _real_sink(c.get("eq_target"))
        _start(name, eq_conf(c["eq_gains"], target))
        ok = _wait_node(name)
    else:
        _start(name, noise_conf(c.get("noise_strength", "middels")))
        ok = _wait_node(name, "sources")
    if not ok:
        stop(name)
        set_(**{kind: False})
        raise RuntimeError("PipeWire laget ikke filteret – se loggen")
    if make_default:
        what = "source" if kind == "noise" else "sink"
        prev = _pactl("get-default-" + what)
        if not prev.startswith("ks_"):
            set_(**{kind + "_prev_default": prev})
        _pactl("set-default-" + what, name)
    return {"surround": "Virtuell 7.1 er på – spill og filmer sender nå surround til hodesettet",
            "eq": "Equalizeren er på", "noise": "Støyfilteret er på – velg «Mikrofon med støyfilter» i Discord/spill "
            "hvis de ikke følger standard"}[kind]


def set_eq(gains=None, preset=None, target=None):
    """Nye EQ-verdier – starter filteret på nytt hvis det er på."""
    kw = {}
    if preset in PRESETS:
        kw.update(eq_preset=preset, eq_gains=list(PRESETS[preset][1]))
    if gains is not None:
        kw.update(eq_gains=[max(-12.0, min(12.0, float(g))) for g in gains][:10], eq_preset="egen")
    if target is not None:
        kw.update(eq_target=target)
    c = set_(**kw)
    if c["eq"] and running(EQ_NAME):
        _start(EQ_NAME, eq_conf(c["eq_gains"], _real_sink(c.get("eq_target"))))
    return c


def tick():
    """Kalles jevnlig: start filtrene som skal være på (f.eks. etter omstart av PC-en)."""
    if not available():
        return
    c = cfg()
    for kind, name in (("surround", SURROUND_NAME), ("eq", EQ_NAME), ("noise", NOISE_NAME)):
        if c.get(kind) and not running(name):
            try:
                enable(kind, True, make_default=False)
            except Exception:  # noqa: BLE001
                import applog
                applog.log.exception("lydfilter %s", kind)


def uninstall():
    """Funksjonen slås av: stopp alt og fjern filene vi laget."""
    for name in (SURROUND_NAME, EQ_NAME, NOISE_NAME):
        stop(name)
    import shutil
    shutil.rmtree(DIR, ignore_errors=True)


def state():
    c = cfg()
    return {"available": available(), "surround": bool(running(SURROUND_NAME)), "eq": bool(running(EQ_NAME)),
            "noise": bool(running(NOISE_NAME)), "eq_gains": c["eq_gains"], "eq_preset": c["eq_preset"],
            "presets": [{"key": k, "name": v[0]} for k, v in PRESETS.items()], "freq": EQ_FREQ}
