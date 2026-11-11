"""Pakkehåndteringssjekk for Systemmonitor (brukes av syscheck.py).

Finner og retter vanlige oppdaterings- og pakkefeil på:
  Arch / CachyOS / EndeavourOS / Manjaro (pacman), Fedora (dnf), Debian / Ubuntu / Mint (apt),
  openSUSE (zypper), Bazzite / Silverblue / Kinoite (rpm-ostree) og Flatpak (alle).

Sjekkene kjører uten root. Rettinger som trenger root legges i Result.root_cmds og kjøres
samlet med én passordforespørsel (pkexec).
"""
import glob
import json
import os
import re
import shlex
import shutil
import subprocess

OSTREE = os.path.exists("/run/ostree-booted")


def _run(cmd, timeout=60):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, "LC_ALL": "C", "LANG": "C"})
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError) as e:
        return 127, str(e)


def _R(*a, **k):
    from syscheck import Result
    return Result(*a, **k)


def _busy(names):
    return any(_run(["pgrep", "-x", n], 5)[0] == 0 for n in names)


def os_release():
    d = {}
    try:
        for line in open("/etc/os-release"):
            if "=" in line:
                k, v = line.rstrip("\n").split("=", 1)
                d[k] = v.strip('"')
    except OSError:
        pass
    return d


def _last_lines(out, n=2):
    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    return "\n".join(lines[-n:])


def _kernel_reboot():
    rel = os.uname().release
    if not OSTREE and os.path.isdir("/usr/lib/modules") and not os.path.isdir(f"/usr/lib/modules/{rel}"):
        return [_R("Kjernen er oppdatert", "info",
                   f"Den kjørende kjernen ({rel}) er fjernet av en oppdatering. Start PC-en på nytt, "
                   "ellers kan USB-enheter og drivere slutte å virke.")]
    return []


# --------------------------------------------------------------------------
# Arch / CachyOS (pacman)
# --------------------------------------------------------------------------
PACMAN_BUSY = ("pacman", "yay", "paru", "pamac", "pamac-daemon", "octopi", "packagekitd",
               "cachyos-pi", "pikaur", "trizen")
KEYRINGS = ("archlinux-keyring", "cachyos-keyring", "chaotic-keyring", "endeavouros-keyring",
            "manjaro-keyring", "garuda-keyring")
SIG_RX = re.compile(r"unknown trust|invalid or corrupted package \(PGP|signature from .* is "
                    r"(invalid|marginal)|could not be looked up remotely|is disabled|"
                    r"keyring is not writable|key .* could not be imported", re.I)
MIRROR_RX = re.compile(r"failed retrieving file|failed to synchronize|could not resolve host|"
                       r"download library error|operation too slow|404", re.I)


def _pacman_log():
    try:
        with open("/var/log/pacman.log", errors="replace") as f:
            lines = f.read().splitlines()[-5000:]
    except OSError:
        return None, None
    ok = [i for i, ln in enumerate(lines) if "transaction completed" in ln]
    after = lines[(ok[-1] + 1 if ok else 0):]
    sig = next((ln for ln in reversed(after) if SIG_RX.search(ln)), None)
    mir = next((ln for ln in reversed(after) if MIRROR_RX.search(ln)), None)
    return sig, mir


def _mirror_fix():
    if shutil.which("cachyos-rate-mirrors"):
        return "cachyos-rate-mirrors && pacman -Syy --noconfirm"
    if shutil.which("reflector"):
        return ("reflector --latest 20 --protocol https --sort rate --save /etc/pacman.d/mirrorlist "
                "&& pacman -Syy --noconfirm")
    if shutil.which("pacman-mirrors"):                   # Manjaro
        return "pacman-mirrors --fasttrack && pacman -Syy --noconfirm"
    return "pacman -Syy --noconfirm"


def check_pacman():
    if OSTREE or not shutil.which("pacman"):
        return []
    res = []
    keyrings = [k for k in KEYRINGS if _run(["pacman", "-Q", k], 10)[0] == 0]
    kr = " ".join(keyrings) or "archlinux-keyring"
    keyring_cmd = f"pacman-key --init && pacman-key --populate && pacman -Sy --noconfirm --needed {kr}"

    # 1. Låst database
    if os.path.exists("/var/lib/pacman/db.lck"):
        if _busy(PACMAN_BUSY):
            res.append(_R("pacman: en installasjon pågår", "info",
                          "Pakkedatabasen er låst fordi et program installerer eller oppdaterer nå."))
        else:
            res.append(_R("pacman: databasen er låst", "error",
                          "En tidligere oppdatering ble avbrutt og etterlot /var/lib/pacman/db.lck. "
                          "Da feiler alle nye oppdateringer med «unable to lock database».",
                          fix_label="Fjern den gamle låsen", root_cmds=["rm -f /var/lib/pacman/db.lck"]))

    # 2. Signatur-/nøkkelringfeil og speilfeil fra siste forsøk
    sig, mir = _pacman_log()
    if sig:
        res.append(_R("pacman: feil med pakkesignaturer (PGP)", "error",
                      "Siste oppdatering feilet på signaturer – nøkkelringen er utdatert eller ødelagt.\n"
                      + sig.strip()[-200:],
                      fix_label="Lag nøkkelringen på nytt og hent nye nøkler (" + kr + ")",
                      root_cmds=[keyring_cmd]))

    # 3. Ventende oppdateringer (checkupdates bruker egen database – trygt uten root)
    mirror_bad = False
    if shutil.which("checkupdates"):
        code, out = _run(["checkupdates"], timeout=180)
        if code == 0 and out.strip():
            pkgs = [ln.split()[0] for ln in out.strip().splitlines() if ln.strip()]
            kr_upd = [p for p in pkgs if p in KEYRINGS]
            res.append(_R(f"pacman: {len(pkgs)} oppdateringer tilgjengelig", "info",
                          ", ".join(pkgs[:12]) + (" …" if len(pkgs) > 12 else "") +
                          ("\nNøkkelringen oppdateres først, så du slipper PGP-feil." if kr_upd else ""),
                          fix_label="Oppdater hele systemet (nøkkelring først, så pacman -Syu)",
                          root_cmds=[f"pacman -Sy --noconfirm --needed {kr}",
                                     "pacman -Su --noconfirm"]))
        elif code == 1:
            mirror_bad = True
            res.append(_R("pacman: kunne ikke hente oppdateringslister", "warn",
                          _last_lines(out) + "\nSpeilserverne svarer ikke eller er utdaterte.",
                          fix_label="Finn raskeste speilservere og hent listene på nytt",
                          root_cmds=[_mirror_fix()]))
        elif code == 2:
            res.append(_R("pacman: systemet er oppdatert", "ok", "Ingen ventende oppdateringer"))
    else:
        res.append(_R("pacman: kan ikke sjekke oppdateringer", "info",
                      "Verktøyet checkupdates (pakken pacman-contrib) mangler.",
                      fix_label="Installer pacman-contrib",
                      root_cmds=["pacman -S --noconfirm --needed pacman-contrib"]))
    if mir and not mirror_bad:
        res.append(_R("pacman: speilservere feilet ved siste oppdatering", "warn", mir.strip()[-200:],
                      fix_label="Finn raskeste speilservere", root_cmds=[_mirror_fix()]))

    # 4. Foreldreløse pakker
    code, out = _run(["pacman", "-Qdtq"], 30)
    orphans = out.split() if code == 0 else []
    if orphans:
        res.append(_R(f"pacman: {len(orphans)} foreldreløse pakker", "warn",
                      "Avhengigheter som ingen pakker trenger lenger: " + ", ".join(orphans[:10]) +
                      (" …" if len(orphans) > 10 else ""),
                      fix_label="Fjern foreldreløse pakker",
                      root_cmds=["pacman -Rns --noconfirm " + " ".join(map(shlex.quote, orphans))]))

    # 5. Stor pakkecache
    size = 0
    try:
        for e in os.scandir("/var/cache/pacman/pkg"):
            if e.is_file(follow_symlinks=False):
                size += e.stat().st_size
    except OSError:
        pass
    if size > 5e9:
        res.append(_R(f"pacman: pakkecachen er {size / 1e9:.0f} GB", "warn",
                      "Gamle pakkeversjoner tar plass.",
                      fix_label="Behold bare de 2 siste versjonene" if shutil.which("paccache")
                      else "Tøm gamle pakker fra cachen",
                      root_cmds=["paccache -rk2" if shutil.which("paccache") else "pacman -Sc --noconfirm"]))

    # 6. .pacnew-filer (må flettes for hånd)
    pacnew = []
    for p in glob.glob("/etc/**/*.pacnew", recursive=True):
        pacnew.append(p)
    if pacnew:
        res.append(_R(f"pacman: {len(pacnew)} nye konfigurasjonsfiler (.pacnew)", "info",
                      "Disse må flettes for hånd: " + ", ".join(pacnew[:6]) +
                      "\nKjør i terminal:  sudo DIFFPROG=meld pacdiff"))

    # 7. Databasefeil
    code, out = _run(["pacman", "-Dk"], 180)
    if code != 0 and "error" in out.lower():
        res.append(_R("pacman: pakkedatabasen har feil", "error", _last_lines(out, 3),
                      fix_label="Hent databasene på nytt", root_cmds=["pacman -Syy --noconfirm"]))
    return res + _kernel_reboot()


# --------------------------------------------------------------------------
# Fedora (dnf) – ikke på rpm-ostree-systemer
# --------------------------------------------------------------------------
def check_dnf():
    if OSTREE or not shutil.which("dnf"):
        return []
    res = []
    if _busy(("dnf", "dnf5", "packagekitd", "rpm")):
        return [_R("dnf: en installasjon pågår", "info", "Prøv igjen når den er ferdig.")]
    code, out = _run(["rpm", "-qa", "--quiet"], 60)
    if code != 0 or re.search(r"rpmdb|BDB|sqlite.*error|database.*(corrupt|error)", out, re.I):
        res.append(_R("dnf: RPM-databasen er ødelagt", "error", _last_lines(out),
                      fix_label="Bygg RPM-databasen på nytt", root_cmds=["rpm --rebuilddb"]))
    code, out = _run(["dnf", "-q", "check"], 240)
    if code == 0 and out.strip() and "unknown" not in out.lower():
        if "duplicate" in out.lower():
            res.append(_R("dnf: dupliserte pakker", "error", _last_lines(out, 3),
                          fix_label="Fjern duplikater", root_cmds=["dnf -y remove --duplicates"]))
        else:
            res.append(_R("dnf: avhengighetsfeil", "error", _last_lines(out, 3),
                          fix_label="Synkroniser med distroens versjoner (distro-sync)",
                          root_cmds=["dnf -y distro-sync"]))
    code, out = _run(["dnf", "-q", "check-update"], 300)
    if code == 100:
        n = len([ln for ln in out.splitlines() if re.match(r"^\S+\.\S+\s+\S+\s+\S+", ln)])
        res.append(_R(f"dnf: {n} oppdateringer tilgjengelig", "info", "",
                      fix_label="Oppdater hele systemet (dnf upgrade)",
                      root_cmds=["dnf -y upgrade --refresh"]))
    elif code == 1:
        res.append(_R("dnf: kunne ikke hente pakkelister", "warn", _last_lines(out),
                      fix_label="Tøm cache og hent metadata på nytt",
                      root_cmds=["dnf clean all", "dnf -y makecache"]))
    elif code == 0:
        res.append(_R("dnf: systemet er oppdatert", "ok", "Ingen ventende oppdateringer"))
    if shutil.which("dnf") and _run(["dnf", "needs-restarting", "-r"], 60)[0] == 1:
        res.append(_R("dnf: omstart anbefales", "info", "Kjerne eller systembiblioteker er oppdatert."))
    return res


# --------------------------------------------------------------------------
# Debian / Ubuntu / Mint (apt)
# --------------------------------------------------------------------------
def check_apt():
    if not shutil.which("apt-get") or not shutil.which("dpkg"):
        return []
    res = []
    NL = ["-o", "Debug::NoLocking=1"]
    code, out = _run(["dpkg", "--audit"], 60)
    if out.strip():
        res.append(_R("apt: en installasjon ble avbrutt", "error", _last_lines(out, 3),
                      fix_label="Fullfør avbrutte installasjoner (dpkg --configure -a)",
                      root_cmds=["DEBIAN_FRONTEND=noninteractive dpkg --configure -a"]))
    code, out = _run(["apt-get", "-s", *NL, "check"], 120)
    if code != 0 or "broken" in out.lower() or "unmet" in out.lower():
        res.append(_R("apt: brutte avhengigheter", "error", _last_lines(out, 3),
                      fix_label="Reparer avhengigheter (apt -f install)",
                      root_cmds=["DEBIAN_FRONTEND=noninteractive apt-get -y -f install"]))
    code, out = _run(["apt", "list", "--upgradable"], 120)
    n = len([ln for ln in out.splitlines() if "/" in ln and "upgradable" in ln])
    if n:
        res.append(_R(f"apt: {n} oppdateringer tilgjengelig", "info", "",
                      fix_label="Oppdater hele systemet (apt full-upgrade)",
                      root_cmds=["apt-get update",
                                 "DEBIAN_FRONTEND=noninteractive apt-get -y full-upgrade"]))
    else:
        res.append(_R("apt: systemet er oppdatert", "ok",
                      "Ingen ventende oppdateringer (ifølge sist hentede pakkelister)"))
    code, out = _run(["apt-get", "-s", *NL, "autoremove"], 120)
    rm = [ln.split()[1] for ln in out.splitlines() if ln.startswith("Remv ")]
    if rm:
        res.append(_R(f"apt: {len(rm)} overflødige pakker", "warn", ", ".join(rm[:10]),
                      fix_label="Fjern overflødige pakker (autoremove)",
                      root_cmds=["DEBIAN_FRONTEND=noninteractive apt-get -y autoremove"]))
    if os.path.exists("/var/run/reboot-required"):
        res.append(_R("apt: omstart kreves", "info", "En oppdatering krever at PC-en startes på nytt."))
    return res


# --------------------------------------------------------------------------
# openSUSE (zypper)
# --------------------------------------------------------------------------
def check_zypper():
    if not shutil.which("zypper"):
        return []
    tw = "tumbleweed" in os_release().get("ID", "")
    res = []
    code, out = _run(["zypper", "-n", "--no-refresh", "lu"], 120)
    if "root" in out.lower() and code != 0:
        return [_R("zypper: kan ikke sjekkes uten root", "info", "")]
    n = len([ln for ln in out.splitlines() if ln.startswith("v ")])
    upd = "zypper -n refresh && zypper -n " + ("dup" if tw else "update")
    if n:
        res.append(_R(f"zypper: {n} oppdateringer tilgjengelig", "info", "",
                      fix_label="Oppdater hele systemet", root_cmds=[upd]))
    code, out = _run(["zypper", "-n", "--no-refresh", "verify", "--dry-run"], 120)
    if code != 0 or "problem" in out.lower():
        res.append(_R("zypper: avhengighetsfeil", "error", _last_lines(out, 3),
                      fix_label="Reparer avhengigheter (zypper verify)", root_cmds=["zypper -n verify"]))
    return res or [_R("zypper: systemet er oppdatert", "ok", "")]


# --------------------------------------------------------------------------
# Bazzite / Silverblue / Kinoite (rpm-ostree)
# --------------------------------------------------------------------------
def check_rpmostree():
    if not OSTREE or not shutil.which("rpm-ostree"):
        return []
    res = []
    code, out = _run(["rpm-ostree", "status", "--json"], 60)
    try:
        st = json.loads(out)
    except ValueError:
        st = {}
    if st.get("transaction") and not _busy(("rpm-ostree",)):
        res.append(_R("rpm-ostree: en oppdatering henger", "error",
                      "En transaksjon står fast uten at noe kjører, så nye oppdateringer blokkeres.",
                      fix_label="Avbryt den fastlåste oppdateringen og rydd opp",
                      root_cmds=["rpm-ostree cancel", "rpm-ostree cleanup -m"]))
    for unit in ("rpm-ostreed-automatic.service", "uupd.service", "ublue-update.service"):
        if _run(["systemctl", "is-failed", unit], 10)[1].strip() == "failed":
            _c, log = _run(["journalctl", "-u", unit, "-n", "5", "--no-pager", "-o", "cat"], 20)
            res.append(_R(f"Automatisk systemoppdatering feilet ({unit})", "error",
                          _last_lines(log, 2) or "Se journalctl -u " + unit,
                          fix_label="Rydd opp i oppdateringen og oppdater nå",
                          root_cmds=["rpm-ostree cancel || true", "rpm-ostree cleanup -m",
                                     f"systemctl reset-failed {unit}", "rpm-ostree upgrade"]))
    if not res:
        res.append(_R("rpm-ostree: oppdateringer fungerer", "ok", "Ingen fastlåste eller feilede oppdateringer"))
    return res


# --------------------------------------------------------------------------
# Flatpak (alle distroer)
# --------------------------------------------------------------------------
def check_flatpak():
    if not shutil.which("flatpak"):
        return []
    res = []
    code, out = _run(["flatpak", "repair", "--user", "--dry-run"], 180)
    bad = [ln for ln in out.splitlines()
           if re.search(r"missing|invalid|corrupt|error|problem", ln, re.I) and "0 " not in ln[:3]]
    if bad:
        res.append(_R("Flatpak: installasjonen har feil", "error", _last_lines("\n".join(bad), 3),
                      fix=lambda: _must(["flatpak", "repair", "--user"]),
                      fix_label="Reparer Flatpak (bruker)"))
    code, out = _run(["flatpak", "remote-ls", "--updates", "--columns=application"], 90)
    apps = [ln.strip() for ln in out.splitlines() if ln.strip() and "." in ln]
    if code == 0 and apps:
        res.append(_R(f"Flatpak: {len(apps)} oppdateringer tilgjengelig", "info",
                      ", ".join(apps[:10]) + (" …" if len(apps) > 10 else ""),
                      fix=lambda: _must(["flatpak", "update", "-y", "--noninteractive"], 3600),
                      fix_label="Oppdater alle Flatpak-programmer"))
    elif code != 0 and out.strip():
        res.append(_R("Flatpak: kunne ikke sjekke oppdateringer", "warn", _last_lines(out),
                      fix=lambda: _must(["flatpak", "repair", "--user"]),
                      fix_label="Reparer Flatpak (bruker)"))
    else:
        res.append(_R("Flatpak: alt er oppdatert", "ok", ""))
    return res


def _must(cmd, timeout=600):
    code, out = _run(cmd, timeout)
    if code != 0:
        raise RuntimeError(_last_lines(out, 1) or f"{cmd[0]} feilet")
    return out


def run_all():
    out = []
    for fn in (check_pacman, check_dnf, check_apt, check_zypper, check_rpmostree, check_flatpak):
        try:
            out += fn()
        except Exception as e:  # noqa: BLE001
            out.append(_R(f"Pakkesjekk ({fn.__name__[6:]}) kunne ikke kjøres", "warn", str(e)))
    return out
