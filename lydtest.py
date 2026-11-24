"""Test av hodesett og høyttalere – fra mono til 9.1 (og takhøyttalere 5.1.2 / 5.1.4 / 7.1.2).

Hver høyttaler får sin egen lyd: en stemme som sier hvilken høyttaler det er (espeak-ng/spd-say på Linux,
Windows sin innebygde stemme), fulgt av rosa støy – samme metode som Windows og AV-receivere bruker. Subwooferen
får en lav tone-sveip. Lydfilene lages én gang (WAV med riktig kanalkart) og spilles med pw-play/paplay på Linux
og PlaySound på Windows. Ingenting installeres, ingen innstillinger endres.
"""
import array
import math
import os
import random
import shutil
import struct
import subprocess
import sys
import threading
import time

IS_WIN = sys.platform == "win32"
RATE = 48000
DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.cache"),
                   "Kontrollsenter" if IS_WIN else "systemmonitor", "lydtest")

# kanal: (navn, Windows-maskebit, plassering i rutenettet (kol 0–6, rad 0–4))
CH = {
    "MONO": ("Mono", 0x4, (3, 0)),
    "FL": ("Venstre foran", 0x1, (1, 0)),
    "FR": ("Høyre foran", 0x2, (5, 0)),
    "FC": ("Senter", 0x4, (3, 0)),
    "LFE": ("Subwoofer", 0x8, (6, 0)),
    "RL": ("Venstre bak", 0x10, (1, 4)),
    "RR": ("Høyre bak", 0x20, (5, 4)),
    "FLW": ("Venstre bred", 0x40, (0, 1)),          # Windows har ingen «bred»-bit – FLC/FRC brukes for 9.1
    "FRW": ("Høyre bred", 0x80, (6, 1)),
    "RC": ("Senter bak", 0x100, (3, 4)),
    "SL": ("Venstre side", 0x200, (0, 2)),
    "SR": ("Høyre side", 0x400, (6, 2)),
    "TFL": ("Venstre tak foran", 0x1000, (2, 1)),
    "TFR": ("Høyre tak foran", 0x4000, (4, 1)),
    "TRL": ("Venstre tak bak", 0x8000, (2, 3)),
    "TRR": ("Høyre tak bak", 0x20000, (4, 3)),
}

# korte navn til små skjermer (mobilappen)
SHORT = {"MONO": "Mono", "FL": "V foran", "FR": "H foran", "FC": "Senter", "LFE": "Sub", "RL": "V bak", "RR": "H bak",
         "FLW": "V bred", "FRW": "H bred", "RC": "S bak", "SL": "V side", "SR": "H side", "TFL": "V tak f.",
         "TFR": "H tak f.", "TRL": "V tak b.", "TRR": "H tak b."}

# oppsett: (nøkkel, navn, kanaler) – kanalene i Windows-rekkefølge (maskebitene stigende), som WAV krever
LAYOUTS = [
    ("1.0", "Mono (1.0)", ["MONO"]),
    ("2.0", "Stereo / hodesett (2.0)", ["FL", "FR"]),
    ("2.1", "2.1", ["FL", "FR", "LFE"]),
    ("3.0", "3.0", ["FL", "FR", "FC"]),
    ("3.1", "3.1", ["FL", "FR", "FC", "LFE"]),
    ("4.0", "4.0 (kvadrofoni)", ["FL", "FR", "RL", "RR"]),
    ("4.1", "4.1", ["FL", "FR", "LFE", "RL", "RR"]),
    ("5.0", "5.0", ["FL", "FR", "FC", "RL", "RR"]),
    ("5.1", "5.1", ["FL", "FR", "FC", "LFE", "RL", "RR"]),
    ("6.0", "6.0", ["FL", "FR", "FC", "RC", "SL", "SR"]),
    ("6.1", "6.1", ["FL", "FR", "FC", "LFE", "RC", "SL", "SR"]),
    ("7.0", "7.0", ["FL", "FR", "FC", "RL", "RR", "SL", "SR"]),
    ("7.1", "7.1", ["FL", "FR", "FC", "LFE", "RL", "RR", "SL", "SR"]),
    ("5.1.2", "5.1.2 (Atmos, 2 i taket)", ["FL", "FR", "FC", "LFE", "RL", "RR", "TFL", "TFR"]),
    ("5.1.4", "5.1.4 (Atmos, 4 i taket)", ["FL", "FR", "FC", "LFE", "RL", "RR", "TFL", "TFR", "TRL", "TRR"]),
    ("7.1.2", "7.1.2 (Atmos, 2 i taket)", ["FL", "FR", "FC", "LFE", "RL", "RR", "SL", "SR", "TFL", "TFR"]),
    ("9.0", "9.0 (7.0 + brede foran)", ["FL", "FR", "FC", "RL", "RR", "FLW", "FRW", "SL", "SR"]),
    ("9.1", "9.1 (7.1 + brede foran)", ["FL", "FR", "FC", "LFE", "RL", "RR", "FLW", "FRW", "SL", "SR"]),
]
LAYOUT = {k: (n, ch) for k, n, ch in LAYOUTS}
SOUNDS = [("voice", "Stemme + støy"), ("noise", "Rosa støy"), ("tone", "Tone (440 Hz)")]

# PipeWire/Pulse-navn → våre kanaler (for å foreslå oppsett ut fra lydkortet)
_PA = {"mono": "MONO", "front-left": "FL", "front-right": "FR", "front-center": "FC", "lfe": "LFE",
       "rear-left": "RL", "rear-right": "RR", "rear-center": "RC", "side-left": "SL", "side-right": "SR",
       "front-left-of-center": "FLW", "front-right-of-center": "FRW", "top-front-left": "TFL",
       "top-front-right": "TFR", "top-rear-left": "TRL", "top-rear-right": "TRR"}

_lock = threading.Lock()
_proc = None
_stop = threading.Event()
state = {"playing": None}                              # kanalen som spilles nå (for markering i vinduet/appen)


# ------------------------------------------------------------------ lydene
def _noise(secs, seed=1):
    """Rosa støy (Paul Kellet), 500 Hz–8 kHz-aktig, med myk inn/ut."""
    rnd = random.Random(seed)
    n = int(RATE * secs)
    b0 = b1 = b2 = b3 = b4 = b5 = b6 = 0.0
    out = [0.0] * n
    for i in range(n):
        w = rnd.uniform(-1, 1)
        b0 = 0.99886 * b0 + w * 0.0555179
        b1 = 0.99332 * b1 + w * 0.0750759
        b2 = 0.96900 * b2 + w * 0.1538520
        b3 = 0.86650 * b3 + w * 0.3104856
        b4 = 0.55000 * b4 + w * 0.5329522
        b5 = -0.7616 * b5 - w * 0.0168980
        out[i] = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + w * 0.5362) * 0.11
        b6 = w * 0.115926
    return _fade(out)


def _tone(secs, f=440.0):
    n = int(RATE * secs)
    return _fade([0.5 * math.sin(2 * math.pi * f * i / RATE) for i in range(n)])


def _sweep(secs=4.0, f0=20.0, f1=120.0):
    """Bass-sveip for subwooferen (logaritmisk fra f0 til f1)."""
    n = int(RATE * secs)
    k = math.log(f1 / f0)
    return _fade([0.7 * math.sin(2 * math.pi * f0 * secs / k * (math.exp(k * i / n) - 1)) for i in range(n)])


def _fade(x, ms=40):
    m = min(len(x) // 2, int(RATE * ms / 1000))
    for i in range(m):
        g = i / m
        x[i] *= g
        x[-1 - i] *= g
    return x


def _voice(text):
    """Stemmen som sier navnet på høyttaleren, som mono 48 kHz – eller [] hvis ingen talesyntese finnes."""
    os.makedirs(DIR, exist_ok=True)
    path = os.path.join(DIR, "tale-" + "".join(c if c.isalnum() else "_" for c in text) + ".wav")
    try:
        if not os.path.exists(path):
            if IS_WIN:
                ps = ("Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                      "try{$s.SelectVoiceByHints('NotSet','NotSet',0,[Globalization.CultureInfo]'nb-NO')}catch{}; "
                      f"$s.SetOutputToWaveFile('{path}'); $s.Speak('{text}'); $s.Dispose()")
                subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=20,
                               creationflags=0x08000000)
            elif shutil.which("espeak-ng"):
                subprocess.run(["espeak-ng", "-v", "nb", "-s", "150", "-w", path, text], capture_output=True, timeout=20)
            else:
                return []
        return _read_mono(path)
    except Exception:  # noqa: BLE001
        return []


def _read_mono(path):
    import wave
    with wave.open(path) as w:
        ch, sw, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if sw != 2:
        return []
    a = array.array("h")
    a.frombytes(raw)
    if sys.byteorder == "big":
        a.byteswap()
    mono = [a[i] / 32768.0 for i in range(0, len(a), ch)]
    if rate == RATE or not mono:
        return mono
    step = rate / RATE                                     # enkel lineær omsampling til 48 kHz
    out = []
    t = 0.0
    while t < len(mono) - 1:
        i = int(t)
        f = t - i
        out.append(mono[i] * (1 - f) + mono[i + 1] * f)
        t += step
    return out


def _write(path, chans, idx, samples, sign=None):
    """WAV (WAVE_FORMAT_EXTENSIBLE, 16 bit) med lyd bare i kanalene i idx (sign: fortegn per kanal)."""
    n = len(chans)
    mask = 0
    for c in chans:
        mask |= CH[c][1]
    a = array.array("h", bytes(2 * n * len(samples)))
    for k, j in enumerate(idx):
        s = (sign or [1] * len(idx))[k]
        for i, v in enumerate(samples):
            a[i * n + j] = max(-32767, min(32767, int(v * s * 32767)))
    if sys.byteorder == "big":
        a.byteswap()
    data = a.tobytes()
    fmt = struct.pack("<HHIIHHHHIH14s", 0xFFFE, n, RATE, RATE * n * 2, n * 2, 16, 22, 16, mask, 1,
                      b"\x00\x00\x00\x00\x10\x00\x80\x00\x00\xaa\x00\x38\x9b\x71")   # KSDATAFORMAT_SUBTYPE_PCM
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 4 + 8 + len(fmt) + 8 + len(data)) + b"WAVE")
        f.write(b"fmt " + struct.pack("<I", len(fmt)) + fmt)
        f.write(b"data" + struct.pack("<I", len(data)) + data)
    os.replace(tmp, path)


def make(layout, ch, sound="voice"):
    """Lager (eller gjenbruker) lydfila for én høyttaler. ch kan også være «bass», «hp-phase» eller «all»."""
    chans = LAYOUT[layout][1]
    os.makedirs(DIR, exist_ok=True)
    path = os.path.join(DIR, f"{layout}-{ch}-{sound}.wav")
    if os.path.exists(path):
        return path
    if ch == "bass":
        idx = [chans.index("LFE")] if "LFE" in chans else list(range(len(chans)))
        _write(path, chans, idx, _sweep())
        return path
    if ch in ("all", "hp-phase"):
        idx = list(range(len(chans)))
        sign = None
        if ch == "hp-phase":                               # venstre og høyre i motfase – skal høres «diffus» ut
            sign = [(-1 if c in ("FR", "RR", "SR", "FRW", "TFR", "TRR") else 1) for c in chans]
        _write(path, chans, idx, [v * 0.6 for v in _noise(2.5, 7)], sign)
        return path
    j = chans.index(ch)
    if ch == "LFE":
        body = _tone(2.0, 50.0)
    elif sound == "tone":
        body = _tone(1.6)
    else:
        body = _noise(1.6, j + 2)
    if sound == "voice":
        v = _voice(CH[ch][0])
        if v:
            body = v + [0.0] * int(RATE * 0.25) + (body if ch != "LFE" else body)
    _write(path, chans, [j], body)
    return path


# ------------------------------------------------------------------ avspilling
def sinks():
    """[(navn, beskrivelse, kanaler)] for utgangene (Linux). Windows: standardutgangen."""
    if IS_WIN:
        return [("", "Standard lydutgang", [])]
    try:
        import json
        r = subprocess.run(["pactl", "-f", "json", "list", "sinks"], capture_output=True, text=True, timeout=5)
        out = []
        for s in json.loads(r.stdout or "[]"):
            m = [_PA.get(x, x) for x in (s.get("channel_map") or "").split(",") if x]
            out.append((s["name"], s.get("description") or s["name"], m))
        return out
    except Exception:  # noqa: BLE001
        return []


def default_sink():
    if IS_WIN:
        return ""
    try:
        return subprocess.run(["pactl", "get-default-sink"], capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def suggest(chmap):
    """Oppsettet som passer best med kanalene utgangen har."""
    have = set(chmap or [])
    if len(have) <= 1:
        return "1.0" if have else "2.0"
    best = "2.0"
    for k, _n, chans in LAYOUTS:
        if k != "1.0" and set(chans) <= have and len(chans) >= len(LAYOUT[best][1]):
            best = k
    return best


def stop():
    global _proc
    _stop.set()
    with _lock:
        p, _proc = _proc, None
    if IS_WIN:
        try:
            import winsound
            winsound.PlaySound(None, 0)
        except Exception:  # noqa: BLE001
            pass
    elif p and p.poll() is None:
        p.terminate()
    state["playing"] = None


def _play_file(path, chans, sink, wait=True):
    global _proc
    if IS_WIN:
        import winsound
        flags = winsound.SND_FILENAME | (0 if wait else winsound.SND_ASYNC)
        winsound.PlaySound(path, flags)
        return
    cmap = ",".join(chans)
    if shutil.which("pw-play"):
        cmd = ["pw-play", "--channels", str(len(chans)), "--channel-map", cmap]
        if sink:
            cmd += ["--target", sink]
        cmd.append(path)
    else:
        pa = {"MONO": "mono", "FL": "front-left", "FR": "front-right", "FC": "front-center", "LFE": "lfe",
              "RL": "rear-left", "RR": "rear-right", "RC": "rear-center", "SL": "side-left", "SR": "side-right",
              "FLW": "front-left-of-center", "FRW": "front-right-of-center", "TFL": "top-front-left",
              "TFR": "top-front-right", "TRL": "top-rear-left", "TRR": "top-rear-right"}
        cmd = ["paplay", "--channels", str(len(chans)), "--channel-map", ",".join(pa[c] for c in chans)]
        if sink:
            cmd += ["--device", sink]
        cmd.append(path)
    with _lock:
        _proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        p = _proc
    if wait:
        while p.poll() is None and not _stop.is_set():
            time.sleep(0.05)


def play(layout, ch, sound="voice", sink=None, on_change=None):
    """Spiller én høyttaler (ch), «seq» (alle etter tur), «bass», «all» eller «hp-phase». Returnerer med en gang."""
    if layout not in LAYOUT:
        raise ValueError(f"ukjent oppsett {layout}")
    chans = LAYOUT[layout][1]
    if ch not in chans and ch not in ("seq", "bass", "all", "hp-phase"):
        raise ValueError(f"{ch} finnes ikke i {layout}")
    stop()
    _stop.clear()

    def run():
        seq = chans if ch == "seq" else [ch]
        try:
            for c in seq:
                if _stop.is_set():
                    break
                state["playing"] = c
                on_change and on_change(c)
                _play_file(make(layout, c, sound), chans, sink if sink is not None else default_sink())
                if ch == "seq":
                    time.sleep(0.3)
        except Exception:  # noqa: BLE001
            import applog
            applog.log.exception("lydtest")
        finally:
            state["playing"] = None
            on_change and on_change(None)
    threading.Thread(target=run, daemon=True).start()
    return f"Spiller {CH[ch][0] if ch in CH else {'seq': 'alle høyttalerne etter tur', 'bass': 'bass-sveip', 'all': 'alle samtidig', 'hp-phase': 'motfase-test'}[ch]}"


def info():
    """For mobilappen: oppsett, plasseringer, utganger og forslag."""
    ss = sinks()
    d = default_sink()
    cur = next((s for s in ss if s[0] == d), ss[0] if ss else ("", "", []))
    return {"layouts": [{"key": k, "name": n, "ch": c} for k, n, c in LAYOUTS],
            "ch": {k: {"name": v[0], "short": SHORT[k], "pos": v[2]} for k, v in CH.items()},
            "sinks": [{"name": s[0], "desc": s[1], "n": len(s[2])} for s in ss],
            "sink": cur[0], "suggest": suggest(cur[2]), "playing": state["playing"],
            "sounds": [{"key": k, "name": n} for k, n in SOUNDS]}
