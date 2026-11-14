"""Hvilke komponenter finnes på maskinen? Brukes til å vise (og installere) bare det som trengs.

Leser bare /sys – ingen root, ingen ekstra programmer. Sjekkes når programmet starter.
"""
import functools
import glob
import os

# Produsenter (USB-leverandør-ID) som lager RGB-utstyr OpenRGB kan styre
RGB_VENDORS = {
    "0b05",  # ASUS (Aura)
    "1b1c",  # Corsair
    "046d",  # Logitech G
    "1038",  # SteelSeries (også MSI-laptoptastatur)
    "1532",  # Razer
    "1462",  # MSI (Mystic Light)
    "048d",  # ITE (RGB på hovedkort fra Gigabyte m.fl.)
    "26ce",  # ASRock
    "2516",  # Cooler Master
    "1e71",  # NZXT
    "0cf2",  # Lian Li
    "3633",  # HyperX / HP
    "0951",  # Kingston HyperX
    "195d",  # Roccat / Turtle Beach
    "1044",  # Gigabyte / Aorus
    "0416",  # Winbond (bl.a. Thermalright / ARGB-kontrollere)
}
# Hovedkortprodusenter som nesten alltid har RGB på kortet
RGB_BOARDS = ("asus", "asustek", "micro-star", "msi", "gigabyte", "asrock")
# Thermalright-kjølere med skjerm (støttet av TRCC)
LCD_IDS = {"87ad:70db", "0416:5302", "0416:530a", "0416:53e6", "0402:3922", "0416:8001"}


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip().lower()
    except OSError:
        return ""


IS_WIN = __import__("sys").platform == "win32"


@functools.lru_cache(maxsize=1)
def _win_devices():
    import winsupport
    return winsupport.pnp_devices()


def _win_ids(prefixes=("USB\\", "HID\\")):
    import re
    out = set()
    for d in _win_devices():
        if d["id"].upper().startswith(prefixes):
            m = re.search(r"VID_([0-9A-F]{4}).*?PID_([0-9A-F]{4})", d["id"], re.I)
            if m:
                out.add(f"{m.group(1).lower()}:{m.group(2).lower()}")
            m = re.search(r"_VID&[0-9A-F]{2}([0-9A-F]{4})_PID&([0-9A-F]{4})", d["id"], re.I)   # Bluetooth-HID
            if m:
                out.add(f"{m.group(1).lower()}:{m.group(2).lower()}")
    return out


@functools.lru_cache(maxsize=1)
def usb_ids():
    if IS_WIN:
        return frozenset(_win_ids())
    out = set()
    for d in glob.glob("/sys/bus/usb/devices/*"):
        v, p = _read(f"{d}/idVendor"), _read(f"{d}/idProduct")
        if v:
            out.add(f"{v}:{p}")
    return frozenset(out)


@functools.lru_cache(maxsize=1)
def hid_vendors():
    """Leverandører av HID-enheter – også trådløse over Bluetooth (f.eks. 0005:046D:B023.0001)."""
    if IS_WIN:
        return frozenset(i.split(":")[0] for i in _win_ids())
    out = set()
    for d in glob.glob("/sys/bus/hid/devices/*"):
        parts = os.path.basename(d).split(":")
        if len(parts) >= 3:
            out.add(parts[1].lower()[-4:])
    return frozenset(out)


def vendors():
    return {i.split(":")[0] for i in usb_ids()} | set(hid_vendors())


def has_logitech():
    return "046d" in vendors()


def has_lcd():
    return bool(usb_ids() & LCD_IDS)


def has_rgb():
    if vendors() & RGB_VENDORS:
        return True
    if IS_WIN:
        import winsupport
        b = winsupport.bios_info().get("BaseBoardManufacturer", "").lower()
        import psutil
        laptop = bool(getattr(psutil, "sensors_battery", lambda: None)())
        return not laptop and any(x in b for x in RGB_BOARDS)
    board = _read("/sys/class/dmi/id/board_vendor")
    chassis = _read("/sys/class/dmi/id/chassis_type")
    desktop = chassis in ("3", "4", "5", "6", "7", "13", "15", "16", "17", "23", "24")
    return desktop and any(b in board for b in RGB_BOARDS)


def has_wifi():
    if IS_WIN:
        import re
        return any(d["cls"] == "Net" and re.search(r"wi-?fi|wireless|wlan|802\.11", d["name"], re.I)
                   for d in _win_devices())
    return bool(glob.glob("/sys/class/ieee80211/*")) or bool(glob.glob("/sys/class/net/*/wireless"))


def has_bluetooth():
    if IS_WIN:
        return any(d["cls"] == "Bluetooth" and "radio" in d["name"].lower() or
                   d["cls"] == "Bluetooth" and "adapter" in d["name"].lower() for d in _win_devices()) or \
            any(d["cls"] == "Bluetooth" for d in _win_devices())
    return bool(glob.glob("/sys/class/bluetooth/hci*"))


def present():
    """Ordbok med alt – for faner, systemsjekk, oppstart og installasjon."""
    return {"rgb": has_rgb(), "logitech": has_logitech(), "lcd": has_lcd(),
            "wifi": has_wifi(), "bluetooth": has_bluetooth()}


if __name__ == "__main__":          # brukes av installer.sh: skriver f.eks. «rgb logitech lcd bluetooth»
    print(" ".join(k for k, v in present().items() if v))
