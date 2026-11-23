"""Tale med AI-en: snakk inn spørsmålet (tale til tekst) og få svaret lest opp.

  • Les opp: spd-say på Linux, Windows sin innebygde stemme (SAPI) på Windows – ingenting å installere.
  • Tale til tekst: Whisper (faster-whisper) lokalt på PC-en – gratis og privat. Installeres med knappen
    «Installer tale til tekst» (ca. 300 MB i en egen mappe). Opptaket gjøres med GStreamer (chatextra.py).
"""
import os
import shutil
import subprocess
import sys

IS_WIN = sys.platform == "win32"
VENV = os.path.expanduser("~/.local/share/systemmonitor/whisper-venv")
PY = os.path.join(VENV, "Scripts", "python.exe") if IS_WIN else os.path.join(VENV, "bin", "python")
_SPEAK = {"p": None}


# --------------------------------------------------------------------------
# Les opp
# --------------------------------------------------------------------------
def _clean(text):
    import re
    t = re.sub(r"```.*?```", " (kode) ", text, flags=re.S)
    t = re.sub(r"[*_`#>|]", "", t)
    return re.sub(r"\s+", " ", t).strip()[:3000]


def speak(text):
    stop()
    t = _clean(text)
    if not t:
        return False
    if IS_WIN:
        ps = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              "$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'nb*' -or "
              "$_.VoiceInfo.Culture.Name -like 'no*' } | Select-Object -First 1; "
              "if ($v) { $s.SelectVoice($v.VoiceInfo.Name) }; $s.Speak([Console]::In.ReadToEnd())")
        p = subprocess.Popen(["powershell", "-NoProfile", "-Command", ps], stdin=subprocess.PIPE,
                             creationflags=0x08000000)
        p.stdin.write(t.encode("utf-8"))
        p.stdin.close()
    elif shutil.which("spd-say"):
        p = subprocess.Popen(["spd-say", "-l", "nb", "-w", t])
    elif shutil.which("espeak-ng"):
        p = subprocess.Popen(["espeak-ng", "-v", "nb", t])
    else:
        raise RuntimeError("fant ingen talesyntese (spd-say / espeak-ng)")
    _SPEAK["p"] = p
    return True


def stop():
    p = _SPEAK["p"]
    _SPEAK["p"] = None
    if p and p.poll() is None:
        try:
            p.terminate()
        except OSError:
            pass
    if not IS_WIN and shutil.which("spd-say"):
        subprocess.run(["spd-say", "-C"], capture_output=True, timeout=3)


# --------------------------------------------------------------------------
# Tale til tekst (Whisper)
# --------------------------------------------------------------------------
def stt_ready():
    return os.path.isfile(PY)


def install_stt():
    """Lag en egen Python-mappe med faster-whisper (bare det Kontrollsenter selv installerer)."""
    py = sys.executable
    subprocess.run([py, "-m", "venv", VENV], check=True, capture_output=True, timeout=300)
    r = subprocess.run([PY, "-m", "pip", "install", "--quiet", "faster-whisper"], capture_output=True, text=True,
                       timeout=1800)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip().splitlines()[-1][-200:])
    return "Tale til tekst er installert ✓ (første gang hentes en liten talemodell, ca. 150 MB)"


def uninstall_stt():
    shutil.rmtree(VENV, ignore_errors=True)
    return "Tale til tekst er fjernet"


def transcribe(path, lang="no"):
    if not stt_ready():
        raise RuntimeError("Tale til tekst er ikke installert")
    code = ("import sys; from faster_whisper import WhisperModel; "
            "m = WhisperModel('base', device='auto', compute_type='int8'); "
            "segs, _ = m.transcribe(sys.argv[1], language=sys.argv[2], vad_filter=True); "
            "print(''.join(s.text for s in segs).strip())")
    kw = {"creationflags": 0x08000000} if IS_WIN else {}
    r = subprocess.run([PY, "-c", code, path, lang], capture_output=True, text=True, timeout=600, **kw)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "").strip().splitlines()[-1][-200:] if r.stderr else "tale til tekst feilet")
    return r.stdout.strip()
