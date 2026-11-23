"""Lokal AI uten nett: Ollama på din egen PC (bruker skjermkortet). Gratis og privat – ingenting sendes ut.

Installeres med knappen på AI-siden (Linux: i hjemmemappa, ingen administrator; Windows: winget). Modellen hentes én
gang (llama3.2:3b, ca. 2 GB). Den lokale AI-en kan ikke styre appen med «ks», men får PC-statusen med i spørsmålet.
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request

IS_WIN = sys.platform == "win32"
HOST = "http://127.0.0.1:11434"
MODEL_DEFAULT = "llama3.2:3b"
BINS = [os.path.expanduser("~/.local/bin/ollama"), "ollama",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe")]


def binary():
    for b in BINS:
        p = b if os.path.isabs(b) else shutil.which(b)
        if p and os.path.isfile(p):
            return p
    return None


def model():
    try:
        import ai
        return ai.cfg().get("local_model") or MODEL_DEFAULT
    except Exception:  # noqa: BLE001
        return MODEL_DEFAULT


def running():
    try:
        with urllib.request.urlopen(HOST + "/api/version", timeout=2) as r:
            return json.load(r).get("version")
    except Exception:  # noqa: BLE001
        return None


def start():
    """Start Ollama i bakgrunnen hvis den ikke kjører."""
    if running():
        return True
    b = binary()
    if not b:
        raise RuntimeError("Lokal AI (Ollama) er ikke installert – trykk «Installer» på AI-siden")
    kw = {"creationflags": 0x08000000} if IS_WIN else {"start_new_session": True}
    subprocess.Popen([b, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
    for _ in range(40):
        time.sleep(0.25)
        if running():
            return True
    raise RuntimeError("Ollama startet ikke")


def models():
    try:
        with urllib.request.urlopen(HOST + "/api/tags", timeout=4) as r:
            return [m["name"] for m in json.load(r).get("models", [])]
    except Exception:  # noqa: BLE001
        return []


def has_model():
    m = model()
    return any(x == m or x.split(":")[0] == m.split(":")[0] and m.endswith(":latest") for x in models())


def pull(on_progress=None):
    """Hent modellen (første gang). on_progress(andel 0–1, tekst)."""
    start()
    req = urllib.request.Request(HOST + "/api/pull", data=json.dumps({"name": model()}).encode(), method="POST")
    with urllib.request.urlopen(req, timeout=3600) as r:
        for line in r:
            try:
                j = json.loads(line)
            except ValueError:
                continue
            if on_progress and j.get("total"):
                on_progress(j.get("completed", 0) / j["total"], j.get("status", ""))
            if j.get("error"):
                raise RuntimeError(j["error"])
    return f"{model()} er klar ✓"


class _Proc:
    """Ligner en subprocess (terminate()) så AI-siden kan stoppe svaret."""

    def __init__(self):
        self.stop = False

    def terminate(self):
        self.stop = True


def _context():
    try:
        import remote
        import homepcs
        st = homepcs.status(remote.win)
        return (f"PC-en nå: CPU {st.get('cpu_t')} °C og {st.get('cpu_l')} % last, GPU {st.get('gpu_t')} °C, "
                f"{st.get('watts')} W, spill: {st.get('game') or 'ingen'}.")
    except Exception:  # noqa: BLE001
        return ""


def ask(prompt, history="", on_text=None, on_done=None, images=None, persona=None, control=True):
    import ai
    proc = _Proc()
    sysmsg = ("Du er den lokale AI-assistenten i Kontrollsenter (kjører på brukerens egen PC uten nett). Svar på norsk, "
              "kort og vennlig. Du kan ikke endre innstillinger selv – si heller hvor i appen det gjøres.")
    pz = ai.PERSONAS.get(persona or ai.cfg().get("persona", "standard"), ai.PERSONAS["standard"])[2]
    if pz:
        sysmsg += " Stil: " + pz
    if control:
        sysmsg += " " + _context()
    msgs = [{"role": "system", "content": sysmsg}]
    if history:
        msgs.append({"role": "user", "content": "Tidligere i samtalen:\n" + history})
    user = {"role": "user", "content": prompt}
    if images:
        import base64
        user["images"] = [base64.b64encode(open(p, "rb").read()).decode() for p in images if os.path.isfile(p)]
    msgs.append(user)

    def work():
        code = 0
        try:
            start()
            if not has_model():
                if on_text:
                    on_text(f"⏬ Henter {model()} første gang (ca. 2 GB) …\n\n")
                pull()
            req = urllib.request.Request(HOST + "/api/chat", method="POST",
                                         data=json.dumps({"model": model(), "messages": msgs, "stream": True}).encode())
            with urllib.request.urlopen(req, timeout=600) as r:
                for line in r:
                    if proc.stop:
                        code = 1
                        break
                    try:
                        j = json.loads(line)
                    except ValueError:
                        continue
                    t = (j.get("message") or {}).get("content")
                    if t and on_text:
                        on_text(t)
                    if j.get("done"):
                        break
        except Exception as e:  # noqa: BLE001
            code = 1
            if on_text:
                on_text(f"✗ {e}")
        if on_done:
            on_done(code)
    threading.Thread(target=work, daemon=True).start()
    return proc
