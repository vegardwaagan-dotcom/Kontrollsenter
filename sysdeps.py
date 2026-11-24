"""Systembibliotekene Kontrollsenter bruker – med riktige pakkenavn for hver Linux-variant.

installer.sh legger inn det programmet trenger for å starte (GTK4/libadwaita). Resten brukes av enkeltfunksjoner og
finnes ikke alltid (Arch, Debian …). Systemsjekk viser det som mangler og installerer alt med ett trykk.
"""
import importlib
import shutil

# nøkkel: (hva det brukes til, sjekk, {pakkehåndterer: pakker})
DEPS = {
    "cairo": ("grafer og målere", lambda: _mod("cairo"),
              {"pacman": "python-cairo", "dnf": "python3-cairo", "apt": "python3-gi-cairo python3-cairo",
               "zypper": "python3-cairo", "xbps": "python3-cairo", "eopkg": "python-cairo"}),
    "psutil": ("prosessor, minne og prosesser", lambda: _mod("psutil"),
               {"pacman": "python-psutil", "dnf": "python3-psutil", "apt": "python3-psutil", "zypper": "python3-psutil",
                "xbps": "python3-psutil", "eopkg": "python-psutil"}),
    "cryptography": ("dagboken (kryptering)", lambda: _mod("cryptography"),
                     {"pacman": "python-cryptography", "dnf": "python3-cryptography", "apt": "python3-cryptography",
                      "zypper": "python3-cryptography", "xbps": "python3-cryptography", "eopkg": "python-cryptography"}),
    "evdev": ("kontrollertest og mobilen som mus", lambda: _mod("evdev"),
              {"pacman": "python-evdev", "dnf": "python3-evdev", "apt": "python3-evdev", "zypper": "python3-evdev",
               "xbps": "python3-evdev", "eopkg": "python-evdev"}),
    "gstreamer": ("mikrofontest, lydsirkel, talemeldinger og talekanaler", lambda: _gst(),
                  {"pacman": "gstreamer gst-plugins-base gst-plugins-good",
                   "dnf": "gstreamer1 gstreamer1-plugins-base gstreamer1-plugins-good",
                   "apt": "gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 gstreamer1.0-plugins-good "
                          "gstreamer1.0-pulseaudio",
                   "zypper": "typelib-1_0-Gst-1_0 gstreamer-plugins-base gstreamer-plugins-good",
                   "xbps": "gstreamer1 gst-plugins-base1 gst-plugins-good1", "eopkg": "gstreamer-1.0 gst-plugins-good"}),
    "pactl": ("lyd: utganger, volum per program, lydprofiler", lambda: bool(shutil.which("pactl")),
              {"pacman": "libpulse", "dnf": "pulseaudio-utils", "apt": "pulseaudio-utils", "zypper": "pulseaudio-utils",
               "xbps": "pulseaudio-utils", "eopkg": "pulseaudio"}),
    "smbclient": ("NAS-en (oppdateringer, chat, kalender, sikkerhetskopi)", lambda: bool(shutil.which("smbclient")),
                  {"pacman": "smbclient", "dnf": "samba-client", "apt": "smbclient", "zypper": "samba-client",
                   "xbps": "samba", "eopkg": "samba"}),
    "lspci": ("skjermkort og drivere", lambda: bool(shutil.which("lspci")),
              {"pacman": "pciutils", "dnf": "pciutils", "apt": "pciutils", "zypper": "pciutils", "xbps": "pciutils",
               "eopkg": "pciutils"}),
}


def _mod(name):
    try:
        importlib.import_module(name)
        return True
    except Exception:  # noqa: BLE001
        return False


def _gst():
    try:
        import gi
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst
        Gst.init(None)
        return all(Gst.ElementFactory.find(e) for e in ("audioconvert", "level", "audiotestsrc"))
    except Exception:  # noqa: BLE001
        return False


def pm():
    """Pakkehåndtereren: pacman, dnf, apt, zypper, xbps (Void), eopkg (Solus), ostree (Bazzite) eller None."""
    import os
    if os.path.exists("/run/ostree-booted"):
        return "ostree"
    for name, exe in (("pacman", "pacman"), ("dnf", "dnf"), ("apt", "apt-get"), ("zypper", "zypper"),
                      ("xbps", "xbps-install"), ("eopkg", "eopkg")):
        if shutil.which(exe):
            return name
    return None


def missing():
    """[(nøkkel, brukes til)] som mangler."""
    out = []
    for k, (why, ok, _p) in DEPS.items():
        try:
            if not ok():
                out.append((k, why))
        except Exception:  # noqa: BLE001
            out.append((k, why))
    return out


def install_cmd(keys):
    """Én kommando (som root) som installerer pakkene for nøklene – None hvis ukjent pakkehåndterer."""
    p = pm()
    pkgs = " ".join(DEPS[k][2].get(p, "") for k in keys if DEPS[k][2].get(p)).split()
    if not pkgs:
        return None
    return {"pacman": f"pacman -S --needed --noconfirm {' '.join(pkgs)}",
            "dnf": f"dnf install -y {' '.join(pkgs)}",
            "apt": f"apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y {' '.join(pkgs)}",
            "zypper": f"zypper -n install {' '.join(pkgs)}",
            "xbps": f"xbps-install -Sy {' '.join(pkgs)}",
            "eopkg": f"eopkg install -y {' '.join(pkgs)}"}.get(p)


def check():
    """Til Systemsjekk."""
    import syscheck as S
    miss = missing()
    if not miss:
        return [S.Result("Systembiblioteker: alt finnes", "ok", "Alle funksjonene har det de trenger.")]
    cmd = install_cmd([k for k, _w in miss])
    detail = "Mangler: " + "; ".join(f"{k} ({w})" for k, w in miss)
    if pm() == "ostree":
        detail += ". På Bazzite/Fedora Atomic: rpm-ostree install, og start på nytt."
        return [S.Result(f"Systembiblioteker: {len(miss)} mangler", "warn", detail)]
    return [S.Result(f"Systembiblioteker: {len(miss)} mangler", "warn", detail,
                     fix_label="Installer det som mangler", root_cmds=[cmd] if cmd else None)]


if __name__ == "__main__":                               # brukes av installer.sh: skriv ut installasjonskommandoen
    import sys
    miss = missing()
    if "--list" in sys.argv:
        print("\n".join(f"{k}: {w}" for k, w in miss))
    else:
        print(install_cmd([k for k, _w in miss]) or "")
