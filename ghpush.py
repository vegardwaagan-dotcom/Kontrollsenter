"""Send nye versjoner til GitHub (samme repo som oppdatering.json peker på), sammen med NAS-publiseringen.

Bruker innloggingen til GitHub-verktøyet «gh» (gh auth login) – ingen passord eller nøkler lagres av Kontrollsenter.
Første gang erstattes historikken på GitHub (som kom fra opplastinger via nettsiden) med den lokale; etterpå er det
vanlige push. Gjør ingenting hvis gh mangler eller ikke er innlogget.
"""
import json
import os
import shutil
import subprocess

APP = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.expanduser("~/.local/share/systemmonitor/github-synk.json")


def _url():
    try:
        with open(os.path.expanduser("~/.config/systemmonitor/oppdatering.json")) as f:
            return json.load(f).get("url") or ""
    except (OSError, ValueError):
        return ""


def _gh():
    for p in (shutil.which("gh"), "/home/linuxbrew/.linuxbrew/bin/gh"):
        if p and os.path.exists(p):
            return p
    return None


def ready():
    """(True, '') hvis vi kan sende til GitHub, ellers (False, grunn)."""
    gh = _gh()
    if not gh:
        return False, "GitHub-verktøyet «gh» er ikke installert"
    if "github.com" not in _url():
        return False, "ingen GitHub-adresse i oppdatering.json"
    r = subprocess.run([gh, "auth", "status"], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        return False, "ikke logget inn i gh (kjør «gh auth login»)"
    if not os.path.isdir(os.path.join(APP, ".git")):
        return False, "programmappa er ikke et git-repo"
    return True, ""


def _git(*a, timeout=180):
    gh = _gh()
    # gh som innloggingshjelper bare for dette kallet – ingenting lagres i git-oppsettet
    cmd = ["git", "-c", "credential.helper=", "-c", f"credential.helper=!{gh} auth git-credential", *a]
    return subprocess.run(cmd, cwd=APP, capture_output=True, text=True, timeout=timeout)


def push():
    """Send main til GitHub. Returnerer (ok, tekst)."""
    ok, why = ready()
    if not ok:
        return False, why
    try:
        with open(STATE) as f:
            st = json.load(f)
    except (OSError, ValueError):
        st = {}
    url = _url()
    args = ["push", url, "HEAD:refs/heads/main"]
    if st.get("url") != url:                      # første gang: erstatt historikken fra nettopplastingene
        args.insert(1, "--force")
    r = _git(*args)
    if r.returncode != 0:
        lines = (r.stderr or r.stdout).strip().splitlines()
        return False, lines[-1] if lines else "ukjent feil"
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w") as f:
        json.dump({"url": url}, f)
    return True, "sendt til GitHub ✓"


if __name__ == "__main__":
    print(push())
