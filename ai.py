"""AI-assistentene Claude Code (Anthropic) og Codex (OpenAI): status, installer/oppdater, logg inn, åpne i
terminal i en mappe – og «Spør» rett fra Kontrollsenter (claude -p / codex exec), med svaret strømmet inn.

Som standard får AI-en bare lese filene i mappa; «La AI-en endre filer» må slås på.
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

IS_WIN = sys.platform == "win32"
CFG = os.path.expanduser("~/.config/systemmonitor/ai.json")
HOME = str(Path.home())
PATH = f"{HOME}/.local/bin:/home/linuxbrew/.linuxbrew/bin:{os.environ.get('PATH', '')}"

TOOLS = {
    "claude": {"name": "Claude Code", "by": "Anthropic", "icon": "claude-code.svg", "script": "script:claude-code",
               "bins": [f"{HOME}/.local/bin/claude", "claude"],
               "login_cmd": "claude", "update_cmd": "claude update",
               "win_install": "irm https://claude.ai/install.ps1 | iex",
               "auth": [f"{HOME}/.claude/.credentials.json", f"{HOME}/.claude.json"]},
    "codex": {"name": "Codex", "by": "OpenAI", "icon": "codex.svg", "script": "script:codex",
              "bins": ["/home/linuxbrew/.linuxbrew/bin/codex", f"{HOME}/.local/bin/codex", "codex"],
              "login_cmd": "codex login", "update_cmd": None,
              "win_install": "npm install -g @openai/codex",
              "auth": [f"{HOME}/.codex/auth.json"]},
    "gemini": {"name": "Gemini", "by": "Google", "icon": "gemini.svg", "script": "script:gemini",
               "bins": ["/home/linuxbrew/.linuxbrew/bin/gemini", f"{HOME}/.local/bin/gemini", "gemini"],
               "login_cmd": "gemini", "update_cmd": None,
               "win_install": "npm install -g @google/gemini-cli",
               "auth": [f"{HOME}/.gemini/oauth_creds.json", f"{HOME}/.gemini/google_accounts.json"],
               "env_auth": ["GEMINI_API_KEY", "GOOGLE_API_KEY"]},
}
_VER = {}


def cfg():
    try:
        with open(CFG, encoding="utf-8") as f:
            c = json.load(f)
    except (OSError, ValueError):
        c = {}
    c.setdefault("folder", HOME)
    c.setdefault("recent", [])
    c.setdefault("allow_edit", False)
    c.setdefault("tool", "claude")
    if c["tool"] not in TOOLS:                         # (f.eks. «lokal» fra før den lokale AI-en ble fjernet)
        c["tool"] = "claude"
    c.setdefault("storage", "nas")                     # samtaler og arbeidsmappe: NAS-en som standard
    c.setdefault("control", True)                      # assistenten kan styre Kontrollsenter med «ks»
    return c


def set_(**kw):
    c = cfg()
    c.update(kw)
    if "folder" in kw:
        c["recent"] = ([kw["folder"]] + [r for r in c["recent"] if r != kw["folder"]])[:8]
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    with open(CFG, "w", encoding="utf-8") as f:
        json.dump(c, f, indent=1, ensure_ascii=False)
    return c


def binary(tool):
    for b in TOOLS[tool]["bins"]:
        p = b if os.path.isabs(b) else shutil.which(b, path=PATH)
        if p and os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    if IS_WIN:
        return shutil.which(tool)
    return None


def version(tool, force=False):
    b = binary(tool)
    if not b:
        return None
    v = _VER.get(tool)
    if v and not force and time.time() - v[1] < 600:
        return v[0]
    try:
        out = subprocess.run([b, "--version"], capture_output=True, text=True, timeout=15,
                             env={**os.environ, "PATH": PATH}).stdout.strip().splitlines()
        ver = (out[0] if out else "?").replace("(Claude Code)", "").replace("codex-cli", "").strip()
    except (OSError, subprocess.SubprocessError):
        ver = "?"
    _VER[tool] = (ver, time.time())
    return ver


def logged_in(tool):
    t = TOOLS[tool]
    return any(os.path.exists(p) for p in t["auth"]) or any(os.environ.get(k) for k in t.get("env_auth", []))


def status(tool):
    b = binary(tool)
    return {"installed": bool(b), "version": version(tool) if b else None, "login": logged_in(tool) if b else False,
            "path": b}


# --------------------------------------------------------------------------
# Installer, oppdater, avinstaller (samme skript som Programmer-fanen)
# --------------------------------------------------------------------------
def _terminal(cmd, folder=None):
    """Vis en kommando i et terminalvindu (innlogging og samtaler skjer der)."""
    folder = folder if folder and os.path.isdir(folder) else HOME
    if IS_WIN:
        subprocess.Popen(["cmd", "/c", "start", "", "cmd", "/k", cmd], cwd=folder,
                         creationflags=0x08000000)
        return True
    full = f'export PATH="{PATH}"; cd {json.dumps(folder)}; {cmd}; echo; read -p "Trykk Enter for å lukke …"'
    for t, args in (("ptyxis", ["--", "bash", "-c"]), ("konsole", ["-e", "bash", "-c"]),
                    ("gnome-terminal", ["--", "bash", "-c"]), ("kgx", ["--", "bash", "-c"]),
                    ("xterm", ["-e", "bash", "-c"])):
        if shutil.which(t):
            subprocess.Popen([t, *args, full], start_new_session=True, cwd=folder)
            return True
    raise RuntimeError("fant ingen terminal (ptyxis, konsole, gnome-terminal …)")


def open_terminal(tool, folder=None):
    b = binary(tool)
    if not b:
        raise RuntimeError(f"{TOOLS[tool]['name']} er ikke installert")
    _terminal(json.dumps(b) if not IS_WIN else f'"{b}"', folder or cfg()["folder"])
    return f"{TOOLS[tool]['name']} åpnet i terminalen ({folder or cfg()['folder']})"


def login(tool):
    _terminal(TOOLS[tool]["login_cmd"])
    return "Logg inn i terminalvinduet – kom tilbake hit når du er ferdig"


def install(tool):
    if IS_WIN:
        cmd = TOOLS[tool]["win_install"]
        _terminal(f'powershell -NoProfile -Command "{cmd}"' if "irm" in cmd else cmd)
        return "Installasjonen kjører i terminalvinduet"
    import programs
    code, out = programs.run_script(TOOLS[tool]["script"], "install")
    _VER.pop(tool, None)
    if code != 0:
        raise RuntimeError(out.strip().splitlines()[-1][-200:] if out.strip() else f"feilkode {code}")
    return f"{TOOLS[tool]['name']} er installert ✓"


def update(tool):
    b = binary(tool)
    if not b:
        return install(tool)
    if tool == "claude":
        r = subprocess.run([b, "update"], capture_output=True, text=True, timeout=600, env={**os.environ, "PATH": PATH})
        out = (r.stdout + r.stderr).strip()
    elif "linuxbrew" in b and tool == "codex" and os.path.realpath(b).startswith("/home/linuxbrew/.linuxbrew/Cellar"):
        r = subprocess.run(["bash", "-c", f'export PATH="{PATH}"; brew upgrade codex'], capture_output=True,
                           text=True, timeout=900)
        out = (r.stdout + r.stderr).strip()
    else:
        return install(tool)
    _VER.pop(tool, None)
    return (out.splitlines()[-1] if out else "Oppdatert") + f" · versjon {version(tool, True)}"


def uninstall(tool):
    if IS_WIN:
        raise RuntimeError("Avinstaller under Innstillinger → Apper i Windows")
    import programs
    code, out = programs.run_script(TOOLS[tool]["script"], "uninstall")
    _VER.pop(tool, None)
    return f"{TOOLS[tool]['name']} er fjernet" if code == 0 else out.strip()[-200:]


# --------------------------------------------------------------------------
# «ks»: assistentens hender i Kontrollsenter (ks.py → /api/local/ai → ai_bridge.py)
# --------------------------------------------------------------------------
BIN = os.path.expanduser("~/.local/share/systemmonitor/ai-bin")
SYSTEM = """Du er assistenten i Kontrollsenter – appen brukeren styrer PC-en med (temperaturer, vifter, strømmodus,
skjermkort, RGB, lyd, spill, chat, Smart Hjem, familie, oppdateringer m.m.). Svar på norsk, kort og vennlig.

Du har full tilgang til Kontrollsenter med kommandoen «ks» i terminalen (kjør den med skallverktøyet ditt):
  ks status                       temperaturer, last, strøm, vifter, strømmodus – bruk denne når brukeren spør om PC-en
  ks finn <ord>                   hvor en innstilling ligger i appen («Side › Fane»), nummerert
  ks vis <nr>                     åpne Kontrollsenter akkurat der (etter «ks finn»)
  ks sider / ks side <navn>       lista over sider / åpne en side
  ks handlinger [ord]             alt appen kan gjøre (samme som knappene), med parametre
  ks gjør <handling> nøkkel=verdi …   gjør det, f.eks. «ks gjør power mode=performance»
  ks innstillinger / ks les <fil> / ks sett <fil> <nøkkel> <verdi>   innstillingsfilene
  ks diagnose                     hva er galt / hvorfor er PC-en treg
  ks systemsjekk                  kjør systemsjekken (retter vanlige feil)
Regler: Når brukeren spør hvor noe er, bruk «ks finn» og si «Side › Fane», og tilby «ks vis». Når brukeren ber deg
endre noe, gjør det med ks og si hva du endret og hvor det kan endres tilbake. Spør før du slår av, starter på nytt
eller sletter noe. Ikke vis nøkler eller passord."""


SYSTEM += """
Mer du kan:
  ks logg                         feilmeldinger fra Kontrollsenter og systemet (bruk når noe krasjer eller feiler)
  ks pcer                         de andre PC-ene hjemme og vennene (status, temperatur, versjon)
  ks wow                          World of Warcraft-dataene fra tillegget (karakterer, gull, quests, låser)
  ks kalender [dager]             det som skjer (røde dager, hendelser, bursdager, ukeplan) – standard 14 dager
  ks kalender ny tittel="Tannlege" dato=2026-12-01 tid=14:00 [gjenta=uke|måned|år] [type=trash|dinner|routine|…]
  ks kalender slett <id> / ks kalender fri [år]     slett hendelse / ferieplanlegger (lange fri rundt røde dager)
  ks scener / ks scene kjør <id> / ks scene ny navn=Filmkveld power=power-saver vifter=35 rgb=av hue=på
      hue_lys=30 hue_farge=#ff8800 volum=40 demp=nei nattlys=på lysstyrke=60   lag scener (lys, lyd, strøm)
  ks regler / ks regel ny … / ks regel slett <id>   automatiske oppgaver, f.eks.
      ks regel ny hvis=gpu_temp over=85 spill=ja gjør=varsel tekst="GPU-en er varm"
      ks regel ny når="søn 12:00" gjør=handling handling=clean
    (hvis: cpu_temp, gpu_temp, cpu_load, gpu_load, watt · gjør: varsel eller handling=<ks-handling> med parametre)
Endringer (ks gjør / ks sett / ks systemsjekk / ks regel) kan kreve at brukeren godtar dem – sier brukeren nei, får
du «Brukeren sa nei»: ikke prøv igjen, foreslå heller noe annet."""

PERSONAS = {
    "standard": ("Standard", "✨", ""),
    "kort": ("Kort og teknisk", "⚡", "Svar så kort som mulig, gjerne punktvis, med tekniske detaljer og tall."),
    "rolig": ("Forklarende og rolig", "🧘", "Forklar steg for steg i et rolig, enkelt språk – som til en som "
                                         "ikke kan så mye om PC-er. Ingen faguttrykk uten forklaring."),
    "morsom": ("Morsom", "😄", "Vær leken og morsom med litt humor og emojier – men fortsatt riktig og nyttig."),
}

# hvordan svarene ser ut: farge og ikon per assistent
TOOL_COLOR = {"claude": "#d97757", "codex": "#10a37f", "gemini": "#4285f4"}


def describe_tool(name, inp):
    """Én kort linje om hva assistenten gjorde («🌡️ Leste temperaturene»)."""
    inp = inp if isinstance(inp, dict) else {}
    cmd = str(inp.get("command") or inp.get("cmd") or "")
    if name in ("Bash", "run_shell_command", "shell", "command_execution", "exec_command") or cmd:
        c = cmd.strip()
        for pre in ("bash -lc ", "sh -c "):
            if c.startswith(pre):
                c = c[len(pre):].strip("'\"")
        if c.startswith("ks "):
            parts = c.split()
            sub = parts[1] if len(parts) > 1 else ""
            rest = " ".join(parts[2:])
            return {"status": "🌡️ Leste temperaturer, last og vifter", "temp": "🌡️ Leste temperaturene",
                    "finn": f"🔎 Søkte etter «{rest}» i appen", "vis": "👉 Viste deg hvor det ligger",
                    "side": f"📄 Åpnet siden {rest}", "sider": "📄 Så på sidene i appen",
                    "handlinger": "📋 Så hva appen kan gjøre", "gjør": f"⚙️ Handling: {rest}",
                    "gjor": f"⚙️ Handling: {rest}", "innstillinger": "🗂️ Så på innstillingsfilene",
                    "les": f"🗂️ Leste {rest}", "sett": f"✏️ Innstilling: {rest}",
                    "diagnose": "🩺 Undersøkte hvorfor PC-en er treg", "systemsjekk": "🛠️ Kjørte systemsjekken",
                    "logg": "📜 Leste feilloggene", "pcer": "🖥️ Sjekket de andre PC-ene",
                    "wow": "🐉 Leste WoW-dataene", "regler": "🤖 Så på de automatiske oppgavene",
                    "regel": f"🤖 Automatisk oppgave: {rest}", "kalender": f"📅 Kalender {rest}".strip(),
                    "kal": f"📅 Kalender {rest}".strip()}.get(sub, f"💻 ks {sub} {rest}".strip())[:90]
        return f"💻 Kjørte: {c[:70]}"
    path = str(inp.get("file_path") or inp.get("path") or inp.get("absolute_path") or "")
    base = os.path.basename(path) if path else ""
    if name in ("Read", "read_file", "read_many_files"):
        return f"📄 Leste {base or 'en fil'}"
    if name in ("Edit", "Write", "MultiEdit", "write_file", "replace", "file_change"):
        return f"✏️ Endret {base or 'en fil'}"
    if name in ("Grep", "Glob", "search_file_content", "glob", "list_directory", "LS"):
        return "🔎 Søkte i filene"
    if name in ("WebFetch", "WebSearch", "web_fetch", "google_web_search", "web_search"):
        return "🌐 Søkte på nettet"
    return f"🔧 {name}"[:60]


QUOTA_F = os.path.expanduser("~/.cache/systemmonitor/ai-kvote.json")


def quota():
    """Siste kjente bruk per assistent: {"claude": {"five_hour": 0.84, "seven_day": 0.5, "t": …}, …}"""
    try:
        with open(QUOTA_F) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_quota(tool, info):
    q = quota()
    q[tool] = {**q.get(tool, {}), **info, "t": time.time()}
    try:
        os.makedirs(os.path.dirname(QUOTA_F), exist_ok=True)
        with open(QUOTA_F, "w") as f:
            json.dump(q, f)
    except OSError:
        pass


def ks_bin():
    """Lag «ks» i en egen mappe som legges først i PATH for assistentene."""
    os.makedirs(BIN, exist_ok=True)
    here = os.path.dirname(os.path.abspath(__file__))
    if IS_WIN:
        p = os.path.join(BIN, "ks.cmd")
        body = f'@"{sys.executable}" "{os.path.join(here, "ks.py")}" %*\r\n'
    else:
        p = os.path.join(BIN, "ks")
        body = f'#!/bin/sh\nexec "{sys.executable}" "{os.path.join(here, "ks.py")}" "$@"\n'
    try:
        if not os.path.exists(p) or open(p).read() != body:
            with open(p, "w") as f:
                f.write(body)
            os.chmod(p, 0o755)
    except OSError:
        pass
    return BIN


# --------------------------------------------------------------------------
# «Spør» – uten terminal, svaret strømmes inn
# --------------------------------------------------------------------------
def ask(tool, prompt, folder=None, allow_edit=False, on_text=None, on_done=None, history="", control=True,
        images=None, on_event=None, persona=None):
    """Start en forespørsel. history: det som er sagt før i samtalen (så assistenten husker). control: gi tilgang
    til Kontrollsenter med «ks». images: bildefiler brukeren la ved. on_event(kind, data): «tool» (tekstlinje om hva
    assistenten gjorde) og «quota» (bruk). Svaret strømmes inn ord for ord via on_text.
    Returnerer prosessen (kan stoppes med .terminate())."""
    b = binary(tool)
    if not b:
        raise RuntimeError(f"{TOOLS[tool]['name']} er ikke installert")
    prompt = str(prompt or "").strip()
    if not prompt:
        raise ValueError("skriv et spørsmål")
    folder = folder if folder and os.path.isdir(folder) else HOME
    rules = SYSTEM if control else ""
    pz = PERSONAS.get(persona or cfg().get("persona", "standard"), PERSONAS["standard"])[2]
    if pz:
        rules += "\nStil: " + pz
    if not allow_edit:
        rules += "\nIkke opprett eller endre filer i mappa (brukeren har ikke slått på «Kan endre filer»)."
    images = [p for p in (images or []) if os.path.isfile(p)]
    if images and tool != "codex":
        prompt += "\n\nBrukeren la ved bilde(r) – se på dem: " + " ".join(
            ("@" + p) if tool == "gemini" else p for p in images)
    asked = (f"Tidligere i samtalen:\n{history}\n\nNytt fra brukeren:\n{prompt}" if history else prompt)
    if tool == "claude":
        cmd = [b, "-p", asked, "--output-format", "stream-json", "--verbose", "--include-partial-messages",
               "--append-system-prompt", rules]
        allowed = (["Bash(ks:*)", "Bash(ks *)"] if control else []) + (["Read"] if images else [])
        if allowed:
            cmd += ["--allowedTools", *allowed]
        if allow_edit:
            cmd += ["--permission-mode", "acceptEdits"]
    elif tool == "gemini":
        cmd = [b, "-p", f"{rules}\n\n{asked}", "-o", "stream-json"]
        if allow_edit:
            cmd += ["--approval-mode", "auto_edit"]
        if control:
            cmd += ["--allowed-tools", "run_shell_command(ks)"]
    else:
        # ks snakker med appen over 127.0.0.1 – det krever nettilgang i Codex sin sandkasse
        sandbox = "workspace-write" if (allow_edit or control) else "read-only"
        cmd = [b, "exec", "--skip-git-repo-check", "--sandbox", sandbox, "--json"]
        if control:
            cmd += ["-c", "sandbox_workspace_write.network_access=true"]
        for im in images:
            cmd += ["-i", im]
        cmd += [f"{rules}\n\n{asked}"]
    kw = {"creationflags": 0x08000000} if IS_WIN else {"start_new_session": True}
    env = {**os.environ, "PATH": (ks_bin() + os.pathsep if control else "") + PATH, "NO_COLOR": "1"}
    try:
        import remote
        env["KS_PORT"] = str(remote.PORT)
    except Exception:  # noqa: BLE001
        pass
    p = subprocess.Popen(cmd, cwd=folder, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         env=env, **kw)

    def ev(kind, data):
        if on_event:
            try:
                on_event(kind, data)
            except Exception:  # noqa: BLE001
                pass

    def text(t):
        if on_text and t:
            on_text(t)

    def pump():
        got = {"delta": False, "final": None, "tools": set()}
        for raw in iter(p.stdout.readline, b""):
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                j = json.loads(line)
            except ValueError:
                if not line.startswith(("Reading additional input", "Loaded cached")):
                    text(line + "\n")                      # feilmelding o.l. i ren tekst
                continue
            if not isinstance(j, dict):
                continue
            t = j.get("type")
            if tool == "claude":
                if t == "stream_event":
                    e = j.get("event") or {}
                    d = e.get("delta") or {}
                    if e.get("type") == "content_block_delta" and d.get("type") == "text_delta":
                        got["delta"] = True
                        text(d.get("text", ""))
                    elif e.get("type") == "content_block_start" and got["delta"]:
                        text("\n\n")                       # ny tekstblokk etter et verktøy
                elif t == "assistant":
                    for c in (j.get("message") or {}).get("content") or []:
                        if c.get("type") == "tool_use" and c.get("id") not in got["tools"]:
                            got["tools"].add(c.get("id"))
                            ev("tool", describe_tool(c.get("name"), c.get("input")))
                elif t == "rate_limit_event":
                    info = j.get("rate_limit_info") or {}
                    w = info.get("unifiedWindows") or {}
                    q = {k: (w.get(k) or {}).get("utilization") for k in ("five_hour", "seven_day")}
                    q["resets"] = {k: (w.get(k) or {}).get("resetsAt") for k in ("five_hour", "seven_day")}
                    _save_quota(tool, q)
                    ev("quota", q)
                elif t == "result":
                    got["final"] = j.get("result")
                    if j.get("is_error") and not got["delta"]:
                        text(str(j.get("result") or "Noe gikk galt"))
            elif tool == "codex":
                it = j.get("item") or {}
                if t in ("item.started", "item.completed") and it.get("type") == "command_execution" and \
                        it.get("id") not in got["tools"]:
                    got["tools"].add(it.get("id"))
                    ev("tool", describe_tool("command_execution", {"command": it.get("command")}))
                elif t == "item.completed" and it.get("type") == "file_change":
                    for ch in it.get("changes") or [{}]:
                        ev("tool", describe_tool("file_change", {"path": ch.get("path")}))
                elif t == "item.completed" and it.get("type") == "agent_message":
                    text(("\n\n" if got["delta"] else "") + str(it.get("text") or ""))
                    got["delta"] = True
                elif t == "turn.completed":
                    u = j.get("usage") or {}
                    _save_quota(tool, {"tokens": u.get("input_tokens", 0) + u.get("output_tokens", 0)})
                elif t in ("error", "turn.failed"):
                    text("✗ " + str(j.get("message") or (j.get("error") or {}).get("message") or "feil"))
            else:                                           # gemini
                if t == "message" and j.get("role") == "assistant":
                    got["delta"] = True
                    text(str(j.get("content") or ""))
                elif t == "tool_use":
                    ev("tool", describe_tool(j.get("tool_name"), j.get("parameters")))
                elif t == "result":
                    st = j.get("stats") or {}
                    if st.get("total_tokens"):
                        _save_quota(tool, {"tokens": st["total_tokens"]})
                elif t == "error":
                    text("✗ " + str(j.get("message") or "feil"))
        if not got["delta"] and got["final"]:
            text(str(got["final"]))
        code = p.wait()
        if on_done:
            on_done(code)
    threading.Thread(target=pump, daemon=True).start()
    return p
