"""Driver- og fastvaresjekk for Systemmonitor (brukes av syscheck.py).

Sjekker og oppdaterer det som er «drivere» på Linux, på alle vanlige distroer:
  * kjerne, Mesa (AMD/Intel-grafikk), NVIDIA, linux-firmware og CPU-mikrokode via
    pakkehåndtereren (pacman, dnf, apt, zypper, rpm-ostree)
  * fastvare i selve enhetene (BIOS, SSD, USB-kontrollere, mottakere) via fwupd
  * viktige enheter uten driver, manglende fastvare i kjerneloggen
  * NVIDIA: om driveren er lastet, om den åpne nouveau brukes, om omstart trengs
  * CachyOS (chwd) og Ubuntu (ubuntu-drivers): anbefalte drivere
"""
import glob
import json
import os
import re
import shlex
import shutil
import time

import pkgcheck as P

OSTREE = P.OSTREE
DRIVER_RX = re.compile(
    r"^(linux(-cachyos\S*|-zen|-lts|-hardened|-rt)?|linux-firmware\S*|linux-image-\S+|linux-modules\S*|"
    r"kernel(-core|-modules\S*|-default)?|kernel-firmware\S*|\S*-firmware|"
    r"nvidia\S*|lib32-nvidia\S*|akmod-nvidia|xorg-x11-drv-nvidia\S*|libnvidia\S*|"
    r"mesa\S*|lib32-mesa\S*|Mesa\S*|libgl1-mesa\S*|vulkan-(radeon|intel|nouveau|mesa)\S*|lib32-vulkan\S*|"
    r"amd-ucode|intel-ucode|amd64-microcode|intel-microcode|microcode_ctl|ucode-\S+|"
    r"xf86-video-\S+|libva\S*|intel-media-driver|opencl-\S+|rocm\S*)$")


def _R(*a, **k):
    from syscheck import Result
    return Result(*a, **k)


def _pkgname(s):
    """«nvidia-utils-580.82-1.x86_64» / «nvidia-utils 580 -> 590» -> nvidia-utils"""
    s = s.split()[0]
    s = re.sub(r"\.(x86_64|noarch|i686|aarch64)$", "", s)
    s = s.split("/")[0]
    return s


def _driver_names(names):
    return sorted({n for n in names if DRIVER_RX.match(n)})


# --------------------------------------------------------------------------
# 1. Driveroppdateringer fra pakkehåndtereren
# --------------------------------------------------------------------------
def check_driver_updates():
    res = []
    if OSTREE and shutil.which("rpm-ostree"):
        code, out = P._run(["rpm-ostree", "status", "--json"], 60)
        try:
            deps = json.loads(out).get("deployments", [])
        except ValueError:
            deps = []
        staged = next((d for d in deps if d.get("staged")), None)
        booted = next((d for d in deps if d.get("booted")), {})
        if staged:
            return [_R("Nye drivere venter på omstart", "info",
                       f"Systemversjon {staged.get('version', '?')} med oppdatert kjerne, Mesa, NVIDIA og "
                       f"fastvare er lastet ned (du kjører {booted.get('version', '?')}). "
                       "Start PC-en på nytt for å ta dem i bruk.")]
        code, out = P._run(["rpm-ostree", "upgrade", "--check"], 180)
        if code == 0 and re.search(r"AvailableUpdate|Version:", out):
            ver = re.search(r"Version:\s*(\S+)", out)
            res.append(_R("Ny systemversjon med oppdaterte drivere", "warn",
                          f"Kjerne, Mesa, NVIDIA og fastvare følger med systemavbildningen"
                          f"{' (' + ver.group(1) + ')' if ver else ''}. Krever omstart etterpå.",
                          fix_label="Last ned ny systemversjon (rpm-ostree upgrade)",
                          root_cmds=["rpm-ostree upgrade"]))
        else:
            res.append(_R("Drivere (systemavbildning)", "ok",
                          "Kjerne, Mesa, NVIDIA og fastvare er nyeste i denne systemversjonen"))
        return res

    if shutil.which("pacman"):
        names = []
        if shutil.which("checkupdates"):
            code, out = P._run(["checkupdates"], 180)
            names = [_pkgname(ln) for ln in out.splitlines() if ln.strip()] if code == 0 else []
        drv = _driver_names(names)
        if drv:
            kr = " ".join(k for k in P.KEYRINGS if P._run(["pacman", "-Q", k], 10)[0] == 0) or "archlinux-keyring"
            res.append(_R(f"{len(drv)} driveroppdateringer tilgjengelig", "warn", ", ".join(drv),
                          fix_label="Oppdater drivere (hele systemet – Arch tillater ikke delvise oppdateringer)",
                          root_cmds=[f"pacman -Sy --noconfirm --needed {kr}", "pacman -Su --noconfirm"]))
        elif names or shutil.which("checkupdates"):
            res.append(_R("Drivere (pacman)", "ok", "Kjerne, Mesa, NVIDIA, fastvare og mikrokode er nyeste"))
    elif shutil.which("dnf"):
        code, out = P._run(["dnf", "-q", "check-update"], 300)
        names = [_pkgname(ln) for ln in out.splitlines() if re.match(r"^\S+\.\S+\s+\S+\s+\S+", ln)]
        drv = _driver_names(names)
        if drv:
            cmds = ["dnf -y upgrade --refresh " + " ".join(map(shlex.quote, drv))]
            if P._run(["rpm", "-q", "akmod-nvidia"], 10)[0] == 0:
                cmds.append("akmods --force && dracut -f || true")
            res.append(_R(f"{len(drv)} driveroppdateringer tilgjengelig", "warn", ", ".join(drv),
                          fix_label="Oppdater drivere (dnf)", root_cmds=cmds))
        elif code in (0, 100):
            res.append(_R("Drivere (dnf)", "ok", "Kjerne, Mesa, NVIDIA og fastvare er nyeste"))
    elif shutil.which("apt-get"):
        code, out = P._run(["apt", "list", "--upgradable"], 120)
        names = [ln.split("/")[0] for ln in out.splitlines() if "/" in ln and "upgradable" in ln]
        drv = _driver_names(names)
        if drv:
            res.append(_R(f"{len(drv)} driveroppdateringer tilgjengelig", "warn", ", ".join(drv),
                          fix_label="Oppdater drivere (apt)",
                          root_cmds=["apt-get update",
                                     "DEBIAN_FRONTEND=noninteractive apt-get install -y --only-upgrade "
                                     + " ".join(map(shlex.quote, drv))]))
        else:
            res.append(_R("Drivere (apt)", "ok", "Kjerne, Mesa, NVIDIA og fastvare er nyeste"))
        if shutil.which("ubuntu-drivers"):
            code, out = P._run(["ubuntu-drivers", "list", "--recommended"], 120)
            rec = [ln.split(",")[0].strip() for ln in out.splitlines() if ln.strip() and not ln.startswith(("ERROR", "WARNING"))]
            missing = [r for r in rec if P._run(["dpkg", "-s", r], 10)[0] != 0]
            if missing:
                res.append(_R("Anbefalte drivere er ikke installert", "warn", ", ".join(missing),
                              fix_label="Installer anbefalte drivere (ubuntu-drivers)",
                              root_cmds=["ubuntu-drivers install"]))
    elif shutil.which("zypper"):
        code, out = P._run(["zypper", "-n", "--no-refresh", "lu"], 120)
        names = [c.strip() for ln in out.splitlines() if ln.startswith("v ") for c in [ln.split("|")[2]]]
        drv = _driver_names(names)
        if drv:
            res.append(_R(f"{len(drv)} driveroppdateringer tilgjengelig", "warn", ", ".join(drv),
                          fix_label="Oppdater drivere (zypper)",
                          root_cmds=["zypper -n refresh", "zypper -n update " + " ".join(map(shlex.quote, drv))]))
        else:
            res.append(_R("Drivere (zypper)", "ok", "Kjerne, Mesa, NVIDIA og fastvare er nyeste"))
    return res


# --------------------------------------------------------------------------
# 2. Grafikkdrivere (NVIDIA / AMD / Intel)
# --------------------------------------------------------------------------
def _pci_gpus():
    code, out = P._run(["lspci", "-nn"], 20)
    return [ln for ln in out.splitlines() if re.search(r"VGA compatible|3D controller|Display controller", ln)]


def check_gpu():
    res = []
    gpus = _pci_gpus()
    has_nv = any("[10de:" in g for g in gpus)
    if has_nv:
        loaded = os.path.isdir("/sys/module/nvidia")
        nouveau = os.path.isdir("/sys/module/nouveau")
        if loaded:
            code, out = P._run(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"], 30)
            if "mismatch" in out.lower():
                res.append(_R("NVIDIA-driveren er oppdatert, men den gamle kjører fortsatt", "warn",
                              "Start PC-en på nytt for å ta i bruk den nye driveren."))
            elif code == 0:
                res.append(_R("NVIDIA-driver", "ok", out.strip().replace(", ", " · driver ")))
            else:
                res.append(_R("NVIDIA-driveren svarer ikke", "error", P._last_lines(out),
                              fix_label=_nv_fix()[0], root_cmds=_nv_fix()[1]) if _nv_fix() else
                           _R("NVIDIA-driveren svarer ikke", "error", P._last_lines(out)))
        else:
            fix = _nv_fix()
            txt = ("Skjermkortet bruker den åpne nouveau-driveren – den gir mye dårligere spillytelse."
                   if nouveau else "Ingen driver er lastet for NVIDIA-skjermkortet.")
            if fix:
                res.append(_R("NVIDIA-driveren mangler", "warn", txt, fix_label=fix[0], root_cmds=fix[1]))
            else:
                res.append(_R("NVIDIA-driveren mangler", "warn",
                              txt + " Installer den proprietære NVIDIA-driveren for distroen din."))
    for g in gpus:
        if "[1002:" in g and not os.path.isdir("/sys/module/amdgpu"):
            res.append(_R("AMD-grafikkdriveren (amdgpu) er ikke lastet", "error", g.split(": ", 1)[-1]))
        if "[8086:" in g and not (os.path.isdir("/sys/module/i915") or os.path.isdir("/sys/module/xe")):
            res.append(_R("Intel-grafikkdriveren er ikke lastet", "error", g.split(": ", 1)[-1]))
    return res


def _nv_fix():
    """(beskrivelse, root-kommandoer) for å installere NVIDIA-driveren, eller None."""
    if OSTREE:
        return None                      # Bazzite/Silverblue: bruk NVIDIA-utgaven av systemavbildningen
    if shutil.which("chwd"):
        return ("Installer NVIDIA-driveren automatisk (CachyOS chwd)", ["chwd -a"])
    if shutil.which("mhwd"):
        return ("Installer NVIDIA-driveren automatisk (Manjaro mhwd)", ["mhwd -a pci nonfree 0300"])
    if shutil.which("pacman"):
        return ("Installer NVIDIA-driveren (nvidia-open-dkms)",
                ["pacman -S --needed --noconfirm nvidia-open-dkms nvidia-utils lib32-nvidia-utils "
                 "$(pacman -Qq | grep -E '^linux(-zen|-lts|-cachyos[^ ]*)?$' | sed 's/$/-headers/' | tr '\\n' ' ')"])
    if shutil.which("ubuntu-drivers"):
        return ("Installer anbefalt NVIDIA-driver (ubuntu-drivers)", ["ubuntu-drivers install"])
    if shutil.which("dnf") and P._run(["dnf", "repolist", "--enabled"], 60)[1].lower().count("rpmfusion-nonfree"):
        return ("Installer NVIDIA-driveren (RPM Fusion akmod-nvidia)",
                ["dnf -y install akmod-nvidia xorg-x11-drv-nvidia-cuda", "akmods --force"])
    return None


# --------------------------------------------------------------------------
# 3. Enheter uten driver og manglende fastvare
# --------------------------------------------------------------------------
IMPORTANT = re.compile(r"VGA|3D|Display|Network|Ethernet|Wireless|Wi-Fi|Audio|USB controller|"
                       r"Non-Volatile|SATA|RAID|Bluetooth|Thunderbolt|USB4", re.I)


def check_missing_drivers():
    code, out = P._run(["lspci", "-k"], 30)
    blocks, cur = [], []
    for ln in out.splitlines():
        if ln and not ln.startswith(("\t", " ")):
            if cur:
                blocks.append(cur)
            cur = [ln]
        elif cur:
            cur.append(ln)
    if cur:
        blocks.append(cur)
    missing = [b[0] for b in blocks if IMPORTANT.search(b[0]) and not any("Kernel driver in use" in x for x in b)]
    res = []
    if missing:
        res.append(_R(f"{len(missing)} enheter mangler driver", "warn",
                      "\n".join(m.split(" ", 1)[-1][:110] for m in missing[:6]) +
                      "\nOppdater kjernen og linux-firmware, eller installer driveren fra produsenten.",
                      fix_label="Installer/oppdater linux-firmware", root_cmds=_firmware_cmd()))
    else:
        res.append(_R("Alle viktige enheter har driver", "ok",
                      "Grafikk, nettverk, lyd, USB og lagring er i orden"))
    code, out = P._run(["journalctl", "-k", "-b", "--no-pager", "-o", "cat"], 60)
    fw = sorted(set(re.findall(r"(?:Direct firmware load for|failed to load firmware)\s+(\S+)", out, re.I)))
    if fw:
        res.append(_R(f"{len(fw)} fastvarefiler mangler", "warn",
                      ", ".join(fw[:8]) + "\nEnheten kan virke dårlig eller ikke i det hele tatt.",
                      fix_label="Installer/oppdater linux-firmware", root_cmds=_firmware_cmd()))
    return res


def _firmware_cmd():
    if OSTREE:
        return None
    if shutil.which("pacman"):
        return ["pacman -Sy --needed --noconfirm linux-firmware"]
    if shutil.which("dnf"):
        return ["dnf -y install linux-firmware"]
    if shutil.which("apt-get"):
        return ["apt-get update", "DEBIAN_FRONTEND=noninteractive apt-get install -y linux-firmware || "
                "DEBIAN_FRONTEND=noninteractive apt-get install -y firmware-linux"]
    if shutil.which("zypper"):
        return ["zypper -n install kernel-firmware-all"]
    return None


# --------------------------------------------------------------------------
# 4. CPU-mikrokode
# --------------------------------------------------------------------------
def check_microcode():
    if OSTREE:
        return []
    vendor = ""
    try:
        for ln in open("/proc/cpuinfo"):
            if ln.startswith("vendor_id"):
                vendor = ln.split(":", 1)[1].strip()
                break
    except OSError:
        return []
    amd = "AMD" in vendor
    pkg = None
    if shutil.which("pacman"):
        pkg = "amd-ucode" if amd else "intel-ucode"
        inst = P._run(["pacman", "-Q", pkg], 10)[0] == 0
        cmd = [f"pacman -S --needed --noconfirm {pkg}"]
    elif shutil.which("apt-get"):
        pkg = "amd64-microcode" if amd else "intel-microcode"
        inst = P._run(["dpkg", "-s", pkg], 10)[0] == 0
        cmd = ["apt-get update", f"DEBIAN_FRONTEND=noninteractive apt-get install -y {pkg}"]
    elif shutil.which("dnf"):
        pkg = "linux-firmware" if amd else "microcode_ctl"
        inst = P._run(["rpm", "-q", pkg], 10)[0] == 0
        cmd = [f"dnf -y install {pkg}"]
    elif shutil.which("zypper"):
        pkg = "ucode-amd" if amd else "ucode-intel"
        inst = P._run(["rpm", "-q", pkg], 10)[0] == 0
        cmd = [f"zypper -n install {pkg}"]
    else:
        return []
    if not inst:
        return [_R("CPU-mikrokode mangler", "warn",
                   f"Pakken {pkg} retter feil og sikkerhetshull i {'AMD' if amd else 'Intel'}-prosessoren.",
                   fix_label=f"Installer {pkg}", root_cmds=cmd)]
    return [_R("CPU-mikrokode", "ok", f"{pkg} er installert")]


# --------------------------------------------------------------------------
# 5. Fastvare i enhetene (fwupd / LVFS)
# --------------------------------------------------------------------------
def check_fwupd():
    if not shutil.which("fwupdmgr"):
        return [_R("Fastvareoppdatering (fwupd) mangler", "info",
                   "Installer pakken fwupd for å oppdatere BIOS, SSD og andre enheter fra Linux.")]
    res = []
    code, out = P._run(["fwupdmgr", "get-remotes", "--json"], 60)
    age_days = None
    try:
        for r in json.loads(out).get("Remotes", []):
            if r.get("Id") == "lvfs" and r.get("Enabled") in (True, "true"):
                mt = int(r.get("Mtime", -1) or -1)
                age_days = None if mt <= 0 else (time.time() - mt) / 86400
                if mt <= 0:
                    age_days = -1
    except (ValueError, TypeError):
        pass
    refresh = "fwupdmgr refresh --force"
    if age_days == -1 or (age_days is not None and age_days > 14):
        res.append(_R("Fastvare-databasen er utdatert", "warn",
                      "Listen over fastvareoppdateringer (LVFS) er " +
                      ("aldri hentet" if age_days == -1 else f"{age_days:.0f} dager gammel") +
                      ", så nye BIOS-, SSD- og enhetsoppdateringer blir ikke funnet.",
                      fix_label="Hent ny fastvareliste (fwupd)", root_cmds=[refresh]))
    code, out = P._run(["fwupdmgr", "get-updates", "--json"], 120)
    try:
        devs = json.loads(out).get("Devices", [])
    except ValueError:
        devs = []
    for d in devs:
        rels = d.get("Releases") or []
        if not rels:
            continue
        new = rels[0].get("Version", "?")
        name = d.get("Name", "enhet")
        did = d.get("DeviceId", "")
        plugin = d.get("Plugin", "")
        flags = d.get("Flags", [])
        ver = f"{d.get('Version', '?')} → {new}"
        cmds = [f"{refresh} || true", f"fwupdmgr update {shlex.quote(did)} -y --no-reboot-check"]
        if plugin.startswith("uefi") or plugin in ("dell", "lenovo", "msi", "asus") or "System Firmware" in name:
            # BIOS/UEFI og Secure Boot-nøkler: aldri fra programmet – for stor risiko
            secure = plugin in ("uefi_dbx", "uefi_db", "uefi_kek", "uefi_pk", "uefi_sbat")
            res.append(_R(f"UEFI-oppdatering tilgjengelig: {name}", "info",
                          ver + "\n" + (
                              "Secure Boot-nøkler: kan gjøre at Linux/Windows ikke starter før Secure Boot slås av, "
                              "og kan ødelegge dual boot. Oppdateres derfor ikke herfra."
                              if secure else
                              "BIOS-oppdatering: strømbrudd underveis kan gjøre at PC-en ikke starter. "
                              "Oppdateres derfor ikke herfra. Gjør det trygt med hovedkortprodusentens verktøy "
                              "(f.eks. ASUS EZ Flash i BIOS-oppsettet) med PC-en koblet til strøm.")))
        elif "internal" in flags:
            # SSD, USB4-kontroller o.l.: bare manuelt («Rett»), aldri automatisk
            res.append(_R(f"Fastvareoppdatering: {name}", "info",
                          ver + "\nIntern enhet – ta sikkerhetskopi først (særlig for SSD). "
                          "Oppdateres bare når du trykker «Rett», aldri automatisk.",
                          fix_label=f"Oppdater fastvare for {name}", root_cmds=cmds))
        else:
            # eksterne enheter (mottakere, dokker, tastatur …): lav risiko
            res.append(_R(f"Fastvareoppdatering: {name}", "warn", ver,
                          fix_label=f"Oppdater fastvare for {name}", root_cmds=cmds))
    if not devs and age_days not in (-1,) and not (age_days and age_days > 14):
        res.append(_R("Fastvare i enhetene", "ok", "BIOS, SSD og andre enheter har nyeste fastvare"))
    return res


# --------------------------------------------------------------------------
# 6. Wi-Fi-kort (PCI/M.2 og USB)
# --------------------------------------------------------------------------
RTL_OOT_USB = {  # Realtek 8812AU/8821AU/8814AU-familien: driver utenfor kjernen
    "0bda:8812", "0bda:881a", "0bda:881b", "0bda:881c", "0bda:0811", "0bda:0821", "0bda:8822",
    "0bda:a811", "0bda:0823", "0bda:8813", "2357:0101", "2357:0103", "2357:010d", "2357:010e",
    "2357:010f", "2357:0115", "2357:0120", "0846:9052", "0846:9054", "7392:a812", "7392:a813",
    "7392:b822", "0b05:17d2", "0b05:1817", "0b05:1852", "0b05:1853", "2001:3314", "2001:3315",
    "2001:3316", "13b1:003f", "148f:9097"}
WIFI_VENDORS = {"8086": "Intel", "14c3": "MediaTek", "10ec": "Realtek", "168c": "Qualcomm Atheros",
                "17cb": "Qualcomm", "14e4": "Broadcom", "1814": "Ralink", "1ae9": "Wilocity"}


def _distro_id():
    d = P.os_release()
    return (d.get("ID", "") + " " + d.get("ID_LIKE", "")).lower()


def _headers_cmd():
    return ("$(pacman -Qq | grep -E '^linux(-zen|-lts|-cachyos[^ ]*)?$' | sed 's/$/-headers/' | tr '\\n' ' ')")


def _broadcom_fix():
    reload = "modprobe -r b43 bcma ssb brcmsmac 2>/dev/null; modprobe wl"
    if OSTREE:
        return None
    if shutil.which("pacman"):
        return ["pacman -S --needed --noconfirm broadcom-wl-dkms " + _headers_cmd(), reload]
    if shutil.which("apt-get"):
        pkg = "bcmwl-kernel-source" if "ubuntu" in _distro_id() else "broadcom-sta-dkms"
        return ["apt-get update", f"DEBIAN_FRONTEND=noninteractive apt-get install -y {pkg}", reload]
    if shutil.which("dnf") and "rpmfusion-nonfree" in P._run(["dnf", "repolist", "--enabled"], 60)[1].lower():
        return ["dnf -y install akmod-wl", "akmods --force", reload]
    if shutil.which("zypper"):
        return ["zypper -n install broadcom-wl", reload]
    return None


def _rtl_oot_fix():
    if OSTREE:
        return None
    if shutil.which("apt-get"):
        return ["apt-get update", "DEBIAN_FRONTEND=noninteractive apt-get install -y rtl8812au-dkms",
                "modprobe 88XXau || modprobe 8812au || true"]
    return None


def _kernel_fw_fix():
    """Nyere kjerne + fastvare (for kort med driver i kjernen)."""
    cmds = _firmware_cmd() or []
    if shutil.which("pacman") and not OSTREE:
        cmds = ["pacman -Syu --noconfirm --needed linux-firmware"]
    return cmds or None


def _pci_wifi():
    code, out = P._run(["lspci", "-nnk"], 30)
    cards, cur = [], None
    for ln in out.splitlines():
        if ln and not ln.startswith(("\t", " ")):
            cur = None
            if re.search(r"\[0280\]|Network controller", ln):
                m = re.search(r"\[([0-9a-f]{4}):([0-9a-f]{4})\]", ln)
                cur = {"desc": ln.split(": ", 1)[-1], "vendor": m.group(1) if m else "",
                       "id": f"{m.group(1)}:{m.group(2)}" if m else "", "driver": None,
                       "slot": ln.split()[0]}
                cards.append(cur)
        elif cur is not None and "Kernel driver in use" in ln:
            cur["driver"] = ln.split(":", 1)[1].strip()
    return cards


def _usb_wifi():
    res = []
    for d in glob.glob("/sys/bus/usb/devices/[0-9]*-[0-9]*"):
        if ":" in os.path.basename(d):
            continue
        try:
            vid = open(f"{d}/idVendor").read().strip()
            pid = open(f"{d}/idProduct").read().strip()
        except OSError:
            continue
        key = f"{vid}:{pid}"
        prod = ""
        try:
            prod = open(f"{d}/product").read().strip()
        except OSError:
            pass
        if key not in RTL_OOT_USB and not re.search(r"WLAN|Wireless LAN|802\.11|Wi-?Fi", prod, re.I):
            continue
        has_net = bool(glob.glob(f"{d}/*/net/*/wireless") or glob.glob(f"{d}/*/net/*/phy80211"))
        drv = [os.path.basename(os.readlink(i + "/driver")) for i in glob.glob(f"{d}/*:*")
               if os.path.islink(i + "/driver")]
        res.append({"id": key, "desc": prod or key, "working": has_net, "driver": ",".join(drv) or None})
    return res


def _wireless_ifaces():
    out = {}
    for n in glob.glob("/sys/class/net/*"):
        if os.path.isdir(n + "/wireless") or os.path.isdir(n + "/phy80211"):
            drv = os.path.basename(os.path.realpath(n + "/device/driver")) if os.path.exists(n + "/device/driver") else "?"
            out[os.path.basename(n)] = drv
    return out


def check_wifi():
    res = []
    pci, usb, ifaces = _pci_wifi(), _usb_wifi(), _wireless_ifaces()
    for c in pci:
        vend = WIFI_VENDORS.get(c["vendor"], "Ukjent produsent")
        if c["driver"]:
            working = any(drv == c["driver"] for drv in ifaces.values())
            if working:
                res.append(_R(f"Wi-Fi: {vend}", "ok", f"{c['desc'][:90]} · driver {c['driver']}"))
            else:
                res.append(_R(f"Wi-Fi-kortet har driver, men virker ikke ({vend})", "warn",
                              f"{c['desc'][:90]} · driver {c['driver']}\nFastvaren mangler trolig.",
                              fix_label="Installer/oppdater Wi-Fi-fastvare (linux-firmware)",
                              root_cmds=_kernel_fw_fix()))
        elif c["vendor"] == "14e4":
            fix = _broadcom_fix()
            res.append(_R("Broadcom Wi-Fi uten driver", "warn",
                          f"{c['desc'][:90]}\nTrenger den proprietære Broadcom-driveren (wl).",
                          fix_label="Installer Broadcom Wi-Fi-driver (wl)" if fix else None, root_cmds=fix))
        else:
            res.append(_R(f"Wi-Fi-kort uten driver ({vend})", "warn",
                          f"{c['desc'][:90]}\nDriveren for dette kortet følger med kjernen – "
                          "oppdater kjernen og fastvaren for å få støtte.",
                          fix_label="Oppdater kjerne og Wi-Fi-fastvare", root_cmds=_kernel_fw_fix()))
    for u in usb:
        if u["working"]:
            res.append(_R("USB Wi-Fi", "ok", f"{u['desc']} ({u['id']}) · driver {u['driver']}"))
        elif u["id"] in RTL_OOT_USB:
            fix = _rtl_oot_fix()
            aur = next((h for h in ("paru", "yay") if shutil.which(h)), None)
            res.append(_R("Realtek USB Wi-Fi uten driver", "warn",
                          f"{u['desc']} ({u['id']}) trenger en driver utenfor kjernen (8812AU-familien)." +
                          ("" if fix else (f"\nInstaller i terminal: {aur} -S rtl88xxau-aircrack-dkms-git"
                                           if aur else "\nDriveren finnes ikke i distroens pakker – se "
                                           "github.com/aircrack-ng/rtl8812au")),
                          fix_label="Installer Realtek Wi-Fi-driver (rtl8812au-dkms)" if fix else None,
                          root_cmds=fix))
        else:
            res.append(_R("USB Wi-Fi uten driver", "warn",
                          f"{u['desc']} ({u['id']})\nOppdater kjernen og fastvaren for å få støtte.",
                          fix_label="Oppdater kjerne og Wi-Fi-fastvare", root_cmds=_kernel_fw_fix()))

    # Innebygd Wi-Fi som ikke synes (slått av i BIOS)
    board = ""
    try:
        board = open("/sys/class/dmi/id/board_name").read().strip()
    except OSError:
        pass
    if not pci and not usb and re.search(r"WIFI|WI-FI|AX|BE\b", board.upper()):
        res.append(_R("Innebygd Wi-Fi er ikke synlig", "info",
                      f"Hovedkortet ({board}) har Wi-Fi, men kortet vises ikke for Linux – det er nesten "
                      "alltid slått av i BIOS. Slå det på i BIOS-oppsettet: Advanced → Onboard Devices "
                      "Configuration → Wi-Fi Controller → Enabled.",
                      fix_label="Søk etter PCI-enheter på nytt", root_cmds=["echo 1 > /sys/bus/pci/rescan"]))
    elif not pci and not usb:
        res.append(_R("Wi-Fi", "ok", "Ingen Wi-Fi-kort i maskinen (kablet nett brukes)"))

    # Sperret eller slått av
    code, out = P._run(["rfkill", "-J"], 10)
    try:
        rf = [d for d in json.loads(out).get("rfkilldevices", []) if d.get("type") == "wlan"]
    except ValueError:
        rf = []
    if any(d.get("hard") == "blocked" for d in rf):
        res.append(_R("Wi-Fi er slått av med bryter eller tast", "warn",
                      "Bruk Wi-Fi-tasten (ofte Fn + F-tast) eller bryteren på maskinen."))
    elif any(d.get("soft") == "blocked" for d in rf):
        res.append(_R("Wi-Fi er sperret (rfkill)", "warn", "Wi-Fi er slått av i programvaren.",
                      fix_label="Slå på Wi-Fi", root_cmds=["rfkill unblock wlan"]))
    if (pci or usb) and shutil.which("nmcli"):
        code, out = P._run(["nmcli", "-t", "-f", "WIFI", "radio"], 10)
        if out.strip() == "disabled":
            res.append(_R("Wi-Fi er slått av i nettverksinnstillingene", "warn", "",
                          fix=lambda: P._run(["nmcli", "radio", "wifi", "on"], 20),
                          fix_label="Slå på Wi-Fi"))
    return res


def run_all():
    out = []
    for fn in (check_driver_updates, check_gpu, check_missing_drivers, check_wifi, check_microcode, check_fwupd):
        try:
            out += fn()
        except Exception as e:  # noqa: BLE001
            out.append(_R(f"Driversjekk ({fn.__name__[6:]}) kunne ikke kjøres", "warn", str(e)))
    return out
