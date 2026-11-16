"""Vinduet «Se på»: viser skjermen til en annen PC i huset live (bare visning). Dobbeltklikk = fullskjerm."""
import threading
import urllib.parse
import urllib.request

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

import i18n  # noqa: E402


class WatchWindow(Gtk.Window):
    def __init__(self, parent, pc_name, ip, game=None, port=27100):
        super().__init__(title=f"📺 {pc_name}" + (f" – {game}" if game else ""), default_width=1280,
                         default_height=760, transient_for=None)
        self.add_css_class("ks-watch")
        overlay = Gtk.Overlay()
        self.pic = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN, hexpand=True, vexpand=True)
        bg = Gtk.Box()
        bg.add_css_class("ks-watch-bg")
        bg.append(self.pic)
        overlay.set_child(bg)
        self.status = Gtk.Label(label=i18n.tr("Kobler til {} …").replace("{}", pc_name), halign=Gtk.Align.CENTER,
                                valign=Gtk.Align.END, margin_bottom=18, wrap=True)
        self.status.add_css_class("ks-watch-status")
        overlay.add_overlay(self.status)
        self.set_child(overlay)
        dbl = Gtk.GestureClick()
        dbl.connect("pressed", lambda _g, n, *_: n == 2 and (self.unfullscreen() if self.is_fullscreen()
                                                              else self.fullscreen()))
        self.add_controller(dbl)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._key)
        self.add_controller(keys)
        self.stop = threading.Event()
        self.connect("close-request", lambda *_: self.stop.set() or False)
        import savegames
        import watch
        self.url = (f"http://{ip}:{port}/api/watch?fk={urllib.parse.quote(watch.house_key())}"
                    f"&by={urllib.parse.quote(savegames.pc_name())}")
        self.frames = 0
        threading.Thread(target=self._read, daemon=True).start()

    def _key(self, _c, keyval, _code, _state):
        if keyval in (Gdk.KEY_Escape,):
            if self.is_fullscreen():
                self.unfullscreen()
            else:
                self.close()
            return True
        if keyval in (Gdk.KEY_f, Gdk.KEY_F, Gdk.KEY_F11):
            self.unfullscreen() if self.is_fullscreen() else self.fullscreen()
            return True
        return False

    def _read(self):
        try:
            with urllib.request.urlopen(self.url, timeout=150) as r:
                if r.status != 200:
                    raise RuntimeError(r.reason)
                buf = b""
                while not self.stop.is_set():
                    head_end = buf.find(b"\r\n\r\n")
                    if head_end < 0:
                        chunk = r.read(65536)
                        if not chunk:
                            break
                        buf += chunk
                        continue
                    head = buf[:head_end].decode("latin-1")
                    length = 0
                    for ln in head.split("\r\n"):
                        if ln.lower().startswith("content-length:"):
                            length = int(ln.split(":", 1)[1])
                    start = head_end + 4
                    while len(buf) < start + length and not self.stop.is_set():
                        chunk = r.read(65536)
                        if not chunk:
                            return
                        buf += chunk
                    jpeg = buf[start:start + length]
                    buf = buf[start + length + 2:]
                    GLib.idle_add(self._show, jpeg)
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")
            GLib.idle_add(self._fail, msg if "error" in msg else str(e))
        except Exception as e:  # noqa: BLE001
            if not self.stop.is_set():
                GLib.idle_add(self._fail, str(e))

    def _show(self, jpeg):
        try:
            tex = Gdk.Texture.new_from_bytes(GLib.Bytes.new(jpeg))
        except GLib.Error:
            return False
        self.pic.set_paintable(tex)
        self.frames += 1
        if self.frames == 1:
            self.status.set_label(i18n.tr("Bare visning · dobbeltklikk for fullskjerm · Esc lukker"))
            GLib.timeout_add_seconds(4, lambda: (self.status.set_visible(False), False)[1])
        return False

    def _fail(self, text):
        import json
        try:
            text = json.loads(text).get("error", text)
        except ValueError:
            pass
        self.status.set_visible(True)
        self.status.set_label(i18n.tr("Fikk ikke vist skjermen: ") + text)
        return False
