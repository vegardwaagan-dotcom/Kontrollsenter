"""Skjermtid i nettleseren: YouTube, Twitch og annen video som spilles i Firefox/Chrome/Edge/Brave (Linux, MPRIS).

Nettleserne melder fra om avspilling til systemet (det er det samme som gjør at medietastene virker). Spiller noe,
telles tiden som «YouTube», «Twitch» eller «Video i nettleseren» i spilletiden og familiegrensene – men bare når
det ikke kjører et spill samtidig (da teller spillet). Slås av og på under Familie.
"""
import sys

BROWSERS = ("firefox", "chrom", "brave", "edge", "vivaldi", "opera", "librewolf", "zen")


def playing_video():
    """Navnet på det som spilles i nettleseren nå («YouTube», «Twitch», «Video i nettleseren»), eller None."""
    if sys.platform == "win32":
        return None
    try:
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        names = bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "ListNames",
                              None, None, Gio.DBusCallFlags.NONE, 2000, None).unpack()[0]
        for n in names:
            if not n.startswith("org.mpris.MediaPlayer2."):
                continue
            low = n.lower()
            if not any(b in low for b in BROWSERS):
                continue

            def prop(iface, key):
                return bus.call_sync(n, "/org/mpris/MediaPlayer2", "org.freedesktop.DBus.Properties", "Get",
                                     GLib.Variant("(ss)", (iface, key)), None, Gio.DBusCallFlags.NONE, 1500,
                                     None).unpack()[0]
            try:
                if prop("org.mpris.MediaPlayer2.Player", "PlaybackStatus") != "Playing":
                    continue
                md = prop("org.mpris.MediaPlayer2.Player", "Metadata") or {}
            except GLib.Error:
                continue
            url = str(md.get("xesam:url", "")).lower()
            title = str(md.get("xesam:title", "")).lower()
            artist = " ".join(md.get("xesam:artist", []) or []).lower()
            blob = " ".join((url, title, artist))
            if "youtube" in blob or "youtu.be" in blob:
                return "YouTube"
            if "twitch" in blob:
                return "Twitch"
            if "netflix" in blob:
                return "Netflix"
            return "Video i nettleseren"
    except Exception:  # noqa: BLE001
        return None
    return None
