"""Skrivebordet Kontrollsenter kjører på – og det som er tilpasset hvert av dem.

KDE Plasma har mest fra før (KWin-skript, KGlobalAccel, kscreen-doctor). Her ligger det som gjør Kontrollsenter like
godt på Hyprland og GNOME:

Hyprland
  * egne vinduer (mini-vindu, widgets, webkamera, AI …) blir flytende i stedet for å legges inn i rutenettet;
    mini-vinduet og widgetene kan ligge øverst (pin), og widgetene husker plasseringen
  * hurtigtaster (klipp, opptak, skjermbilde …) bindes direkte i Hyprland – nøyaktig tast, også i spill
  * egen fil med hurtigtastene, oppstart ved innlogging (Hyprland kjører ikke ~/.config/autostart selv) og valgt
    hovedskjermkort – i samme språk som brukerens oppsett:
      - Lua (hyprland.lua, standard fra Hyprland 0.55): kontrollsenter.lua, lastet med pcall(require, "kontrollsenter");
        endringer mens Hyprland kjører går via «hyprctl eval» med hl.*-kall
      - eldre oppsett (hyprland.conf): kontrollsenter.conf, lastet med «source = …»; hyprctl keyword/dispatch
    Linjen legges bare inn hvis hovedfilen er en vanlig fil vi kan skrive i (ikke en lenke til dotfiles); ellers vises
    den i Innstillinger.
GNOME
  * hurtigtastene legges inn som egne tastatursnarveier i GNOME (ingen spørsmål, nøyaktig tast)
  * statusfelt-ikonet: utvidelsen AppIndicator slås på hvis den er installert

Alt Kontrollsenter legger inn, fjernes igjen med remove_all() (Innstillinger › Generelt › Skrivebord).
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys

IS_WIN = sys.platform == "win32"
APP_ID = os.environ.get("SYSTEMMONITOR_APP_ID", "no.waagan.Systemmonitor")
CFG = os.path.expanduser("~/.config/systemmonitor/skrivebord.json")
HYPR_DIR = os.path.expanduser("~/.config/hypr")
HYPR_CONF = os.path.join(HYPR_DIR, "kontrollsenter.conf")
HYPR_MAIN = os.path.join(HYPR_DIR, "hyprland.conf")
HYPR_LUA_OWN = os.path.join(HYPR_DIR, "kontrollsenter.lua")
HYPR_LUA_MAIN = os.path.join(HYPR_DIR, "hyprland.lua")
SOURCE_LINE = "source = ~/.config/hypr/kontrollsenter.conf   # Kontrollsenter (hurtigtaster og oppstart)"
LUA_LINE = 'pcall(require, "kontrollsenter")   -- Kontrollsenter (hurtigtaster og oppstart)'
GNOME_KB = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"
GNOME_MK = "org.gnome.settings-daemon.plugins.media-keys"
APPINDICATOR = ("appindicatorsupport@rgcjonas.gmail.com", "ubuntu-appindicators@ubuntu.com")


# ---------------------------------------------------------------------------------------------------------------
# Hvilket skrivebord
# ---------------------------------------------------------------------------------------------------------------
def kind():
    """«windows», «hyprland», «gnome», «kde» eller «other»."""
    if IS_WIN:
        return "windows"
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return "hyprland"
    d = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    if "HYPRLAND" in d:
        return "hyprland"
    if "GNOME" in d:
        return "gnome"
    if "KDE" in d:
        return "kde"
    return "other"


def is_hypr():
    return kind() == "hyprland" and bool(shutil.which("hyprctl"))


def is_gnome():
    return kind() == "gnome"


def name():
    return {"windows": "Windows", "hyprland": "Hyprland", "gnome": "GNOME", "kde": "KDE Plasma"}.get(
        kind(), os.environ.get("XDG_CURRENT_DESKTOP") or "ukjent")


def _run(cmd, t=5):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=t)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


def _load():
    try:
        with open(CFG, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(d):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    with open(CFG + ".tmp", "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(CFG + ".tmp", CFG)


# ---------------------------------------------------------------------------------------------------------------
# Hyprland: hyprctl
# ---------------------------------------------------------------------------------------------------------------
def hyprctl(*args, t=5):
    """Kjør hyprctl; returnerer (ok, tekst). «ok» betyr at Hyprland svarte «ok» (eller ga JSON)."""
    code, out = _run(["hyprctl", *args], t)
    out = out.strip()
    return code == 0 and not out.lower().startswith(("invalid", "error", "unknown")), out


def hypr_lua():
    """Bruker Hyprland Lua-oppsett (hyprland.lua finnes – da ignoreres hyprland.conf)?"""
    return os.path.exists(HYPR_LUA_MAIN)


def lua_str(text):
    """Lua-streng uten escaping: [==[ … ]==]."""
    text = str(text)
    if "]==]" in text:
        raise ValueError("ugyldig tekst")
    return "[==[" + text + "]==]"


def hypr_eval(code):
    """Kjør Lua i Hyprland (hyprctl eval). Svarer «ok» når det gikk."""
    code_, out = _run(["hyprctl", "eval", code], 5)
    out = out.strip()
    return code_ == 0 and out.lower() in ("ok", ""), out


def _win_ops(addr, ops):
    """[(«float»|«pin»|«move»|«resize», x, y)] -> én kommando i riktig språk for oppsettet."""
    if hypr_lua():
        w = f'window = "address:{addr}"'
        lines = []
        for op, x, y in ops:
            if op in ("float", "pin"):
                lines.append(f"hl.dispatch(hl.dsp.window.{op}({{ {w} }}))")
            else:
                lines.append(f"hl.dispatch(hl.dsp.window.{op}({{ {w}, x = {int(x)}, y = {int(y)}, relative = false }}))")
        return hypr_eval("\n".join(lines))
    a = "address:" + addr
    cmds = []
    for op, x, y in ops:
        cmds.append({"float": f"dispatch setfloating {a}", "pin": f"dispatch pin {a}",
                     "move": f"dispatch movewindowpixel exact {int(x or 0)} {int(y or 0)},{a}",
                     "resize": f"dispatch resizewindowpixel exact {int(x or 0)} {int(y or 0)},{a}"}[op])
    return hyprctl("--batch", " ; ".join(cmds))


def hypr_monitor(name, mode, x, y, scale, vrr=None, hdr=False):
    """Sett én skjerm (oppløsning@Hz, plassering, skalering, VRR, HDR) – Lua eller hyprland.conf."""
    if not re.fullmatch(r"[\w.:-]+", str(name)) or not re.fullmatch(r"\d+x\d+@[\d.]+", str(mode)):
        raise ValueError("ugyldig skjerm")
    if hypr_lua():
        f = [f'output = "{name}"', f'mode = "{mode}"', f'position = "{int(x)}x{int(y)}"', f"scale = {float(scale):g}"]
        if vrr is not None:
            f.append(f"vrr = {int(vrr)}")
        if hdr:
            f += ["bitdepth = 10", 'cm = "hdr"']
        return hypr_eval("hl.monitor({ " + ", ".join(f) + " })")
    rule = f"{name},{mode},{int(x)}x{int(y)},{float(scale):g}"
    if vrr is not None:
        rule += f",vrr,{int(vrr)}"
    if hdr:
        rule += ",bitdepth,10,cm,hdr"
    return hyprctl("keyword", "monitor", rule)


def hypr_json(what):
    ok, out = hyprctl("-j", what)
    try:
        return json.loads(out)
    except ValueError:
        return None


def hypr_version():
    v = hypr_json("version") or {}
    return v.get("tag") or v.get("version") or ""


def hypr_clients(title=None):
    """Vinduene til DENNE prosessen (valgfritt med tittel)."""
    pid = os.getpid()
    out = []
    for c in hypr_json("clients") or []:
        if c.get("pid") != pid:
            continue
        if title is not None and c.get("title") != title and c.get("initialTitle") != title:
            continue
        out.append(c)
    return out


def _monitor_of(c):
    for m in hypr_json("monitors") or []:
        if m.get("id") == c.get("monitor"):
            return m
    return None


def hypr_window(title, floating=True, pin=None, pos=None, size=None, center=False):
    """Gjør et av våre vinduer flytende (og eventuelt festet øverst, flyttet eller sentrert). True hvis funnet."""
    cs = hypr_clients(title)
    if not cs:
        return False
    for c in cs:
        ops = []
        if floating and not c.get("floating"):
            ops.append(("float", None, None))
        if size and size[0] > 0 and size[1] > 0:
            ops.append(("resize", size[0], size[1]))
        if pos is not None:
            ops.append(("move", pos[0], pos[1]))
        elif center:
            m = _monitor_of(c)
            if m:
                sc = m.get("scale") or 1
                mw, mh = m["width"] / sc, m["height"] / sc
                w, h = size or c.get("size") or (600, 400)
                ops.append(("move", m["x"] + (mw - w) / 2, m["y"] + (mh - h) / 2))
        if pin is not None and bool(c.get("pinned")) != bool(pin):      # pin er av/på-bryter i Hyprland
            ops.append(("pin", None, None))
        if ops:
            _win_ops(c["address"], ops)
    return True


def hypr_pos(title):
    cs = hypr_clients(title)
    return tuple(cs[0]["at"]) if cs and cs[0].get("at") else None


def hypr_follow(win, title=None, **kw):
    """Kall hypr_window når vinduet vises (Hyprland trenger et øyeblikk på å registrere det)."""
    if not is_hypr():
        return
    from gi.repository import GLib

    def go(tries=[0]):
        t = title or win.get_title() or ""
        tries[0] += 1
        if hypr_window(t, **kw) or tries[0] > 12:
            return False
        return True

    def on_map(*_):
        GLib.timeout_add(150, go, [0])
    win.connect("map", on_map)
    if win.get_mapped():
        on_map()


def install_windows(main_win):
    """Hyprland: alle andre vinduer fra Kontrollsenter blir flytende og sentrert (hovedvinduet flislegges som vanlig)."""
    if not is_hypr():
        return
    from gi.repository import GLib, Gtk
    seen = set()

    def decide(w):
        # vinduer som styrer seg selv (mini-vindu, widgets, webkamera) setter _ks_hypr_own i __init__
        if getattr(w, "_ks_hypr_own", False) or w.get_transient_for() is not None:
            return False                                     # dialoger følger hovedvinduet selv
        dw, dh = w.get_default_size()
        hypr_follow(w, floating=True, center=True, size=(dw, dh) if dw > 0 and dh > 0 else None)
        return False

    def check(*_):
        model = Gtk.Window.get_toplevels()
        for i in range(model.get_n_items()):
            w = model.get_item(i)
            if w is main_win or id(w) in seen or not isinstance(w, Gtk.Window):
                continue
            seen.add(id(w))
            GLib.idle_add(decide, w)                         # etter at vinduet er ferdig laget
    Gtk.Window.get_toplevels().connect("items-changed", check)
    check()


# ---------------------------------------------------------------------------------------------------------------
# Hurtigtaster (Hyprland og GNOME): skrivebordet kjører «gdbus …» som aktiverer app.hotkey i Kontrollsenter
# ---------------------------------------------------------------------------------------------------------------
HOTKEYS = {}         # handling -> funksjon (i denne prosessen)
_KEYSYM = {"PageUp": "Page_Up", "PageDown": "Page_Down", "ScrollLock": "Scroll_Lock", "Space": "space"}


def _split(spec):
    parts = [p.strip() for p in str(spec).split("+") if p.strip()]
    return parts[:-1], _KEYSYM.get(parts[-1], parts[-1])


def hypr_key(spec):
    """«Ctrl+Shift+F8» -> («CTRL SHIFT», «F8»)."""
    mods, key = _split(spec)
    return " ".join({"Ctrl": "CTRL", "Shift": "SHIFT", "Alt": "ALT", "Meta": "SUPER"}[m] for m in mods), key


def hypr_lua_key(spec):
    """«Ctrl+Shift+F8» -> «CTRL + SHIFT + F8» (Lua-oppsett)."""
    m, k = hypr_key(spec)
    return " + ".join(m.split() + [k])


def _hypr_bind_now(spec, cmd):
    if hypr_lua():
        return hypr_eval(f'hl.bind("{hypr_lua_key(spec)}", hl.dsp.exec_cmd({lua_str(cmd)}))')
    m, k = hypr_key(spec)
    return hyprctl("keyword", "bind", f"{m},{k},exec,{cmd}")


def _hypr_unbind_now(spec):
    if hypr_lua():
        return hypr_eval(f'hl.unbind("{hypr_lua_key(spec)}")')
    m, k = hypr_key(spec)
    return hyprctl("keyword", "unbind", f"{m},{k}")


def gnome_key(spec):
    """«Ctrl+Shift+F8» -> «<Control><Shift>F8»."""
    mods, key = _split(spec)
    return "".join({"Ctrl": "<Control>", "Shift": "<Shift>", "Alt": "<Alt>", "Meta": "<Super>"}[m] for m in mods) + key


def hotkey_command(action):
    if not re.fullmatch(r"[a-z0-9-]+", action):
        raise ValueError("ugyldig handling")
    path = "/" + APP_ID.replace(".", "/")
    return (f"gdbus call --session --dest {APP_ID} --object-path {path} --method org.gtk.Actions.Activate "
            f"hotkey \"[<'{action}'>]\" \"{{}}\"")


def pressed(action):
    """Kalles av app.hotkey."""
    fn = HOTKEYS.get(action)
    if fn:
        fn()


def bind(action, spec, fn, title=""):
    """Bind en global hurtigtast på Hyprland eller GNOME. Returnerer «hypr»/«gnome» eller kaster feil."""
    HOTKEYS[action] = fn
    d = _load()
    keys = d.setdefault("keys", {})
    old = keys.get(action)
    keys[action] = {"spec": spec, "title": title}
    _save(d)
    if is_hypr():
        if old and old.get("spec") and old["spec"] != spec:
            _hypr_unbind_now(old["spec"])
        hypr_write_conf()                         # varig (leses ved neste innlogging), selv om tasten under feiler
        ok, out = _hypr_bind_now(spec, hotkey_command(action))
        if not ok:
            raise RuntimeError(out or "Hyprland godtok ikke tasten")
        return "hypr"
    if is_gnome() and shutil.which("gsettings"):
        _gnome_bind(action, spec, title)
        return "gnome"
    raise RuntimeError("ikke Hyprland eller GNOME")


def unbind(action):
    """Ta bort én hurtigtast igjen."""
    HOTKEYS.pop(action, None)
    d = _load()
    old = d.get("keys", {}).pop(action, None)
    _save(d)
    if not old:
        return
    if is_hypr():
        try:
            _hypr_unbind_now(old["spec"])
        except (KeyError, ValueError):
            pass
        hypr_write_conf()
    elif shutil.which("gsettings"):
        path = f"{GNOME_KB}kontrollsenter-{action}/"
        cur = _gnome_list()
        if path in cur:
            _run(["gsettings", "reset-recursively", f"{GNOME_MK}.custom-keybinding:{path}"])
            _run(["gsettings", "set", GNOME_MK, "custom-keybindings",
                  "[" + ", ".join(f"'{p}'" for p in cur if p != path) + "]"])


def _gnome_list():
    code, out = _run(["gsettings", "get", GNOME_MK, "custom-keybindings"])
    return re.findall(r"'([^']+)'", out) if code == 0 else []


def _gnome_bind(action, spec, title):
    path = f"{GNOME_KB}kontrollsenter-{action}/"
    schema = f"{GNOME_MK}.custom-keybinding:{path}"
    for k, v in (("name", f"{title or action} (Kontrollsenter)"), ("command", hotkey_command(action)),
                 ("binding", gnome_key(spec))):
        code, out = _run(["gsettings", "set", schema, k, v])
        if code != 0:
            raise RuntimeError(out.strip() or "gsettings feilet")
    cur = _gnome_list()
    if path not in cur:
        cur.append(path)
        _run(["gsettings", "set", GNOME_MK, "custom-keybindings", "[" + ", ".join(f"'{p}'" for p in cur) + "]"])


def _gnome_unbind_all():
    cur = _gnome_list()
    mine = [p for p in cur if "/kontrollsenter-" in p]
    for p in mine:
        _run(["gsettings", "reset-recursively", f"{GNOME_MK}.custom-keybinding:{p}"])
    if mine:
        rest = [p for p in cur if p not in mine]
        _run(["gsettings", "set", GNOME_MK, "custom-keybindings", "[" + ", ".join(f"'{p}'" for p in rest) + "]"])


# ---------------------------------------------------------------------------------------------------------------
# Hyprland: kontrollsenter.conf
# ---------------------------------------------------------------------------------------------------------------
def gpu_choice():
    return _load().get("hypr_gpu")


def set_gpu_choice(bus):
    d = _load()
    if bus:
        d["hypr_gpu"] = bus
    else:
        d.pop("hypr_gpu", None)
    _save(d)
    hypr_write_conf()


def _drm_devices(bus):
    """AQ_DRM_DEVICES: valgt kort først, så de andre – skjermer på de andre kortene virker fortsatt."""
    first = os.path.realpath(f"/dev/dri/by-path/pci-{bus}-card")
    if not os.path.exists(first):
        return None
    cards = sorted(p for p in (os.path.join("/dev/dri", n) for n in os.listdir("/dev/dri"))
                   if re.fullmatch(r"/dev/dri/card\d+", p))
    return ":".join([first] + [c for c in cards if c != first])


def _ks_autostart_on():
    import glob
    for f in glob.glob(os.path.expanduser("~/.config/autostart/systemmonitor-*.desktop")):
        if not _hidden(f):
            return True
    return False


def _hidden(f):
    try:
        txt = open(f, encoding="utf-8", errors="replace").read()
    except OSError:
        return True
    return bool(re.search(r"^Hidden\s*=\s*true", txt, re.M | re.I) or
                re.search(r"^X-GNOME-Autostart-enabled\s*=\s*false", txt, re.M | re.I))


def _hypr_items():
    """Det som skal i Kontrollsenter sin Hyprland-fil: (oppstart-kommando|None, [(spec, kommando)], AQ_DRM_DEVICES)."""
    d = _load()
    auto = None
    if _ks_autostart_on():
        auto = f"{shlex.quote(sys.executable)} {shlex.quote(os.path.abspath(__file__))} --autostart"
    keys = []
    for action, k in sorted(d.get("keys", {}).items()):
        try:
            hypr_key(k["spec"])
            keys.append((k["spec"], hotkey_command(action)))
        except (KeyError, ValueError):
            continue
    dev = _drm_devices(d["hypr_gpu"]) if d.get("hypr_gpu") else None
    return auto, keys, dev


def hypr_conf_text(lua=None):
    lua = hypr_lua() if lua is None else lua
    auto, keys, dev = _hypr_items()
    c = "--" if lua else "#"
    lines = [f"{c} Laget av Kontrollsenter – skrives på nytt automatisk. Endre i Kontrollsenter, ikke her.",
             f"{c} Fjernes med Innstillinger › Generelt › Skrivebord › «Fjern det Kontrollsenter har lagt inn».", ""]
    if auto:
        lines.append(f"{c} oppstart ved innlogging (Hyprland kjører ikke ~/.config/autostart selv)")
        lines += ([f'hl.on("hyprland.start", function()', f"  hl.exec_cmd({lua_str(auto)})", "end)"] if lua else
                  [f"exec-once = {auto}"])
        lines.append("")
    if keys:
        lines.append(f"{c} hurtigtaster")
        for spec, cmd in keys:
            if lua:
                lines.append(f'hl.bind("{hypr_lua_key(spec)}", hl.dsp.exec_cmd({lua_str(cmd)}))')
            else:
                m, key = hypr_key(spec)
                lines.append(f"bind = {m}, {key}, exec, {cmd}")
        lines.append("")
    if dev:
        lines.append(f"{c} hovedskjermkort (GPU-innstillinger › Hovedskjermkort) – gjelder fra neste innlogging")
        lines.append(f'hl.env("AQ_DRM_DEVICES", "{dev}")' if lua else f"env = AQ_DRM_DEVICES,{dev}")
        lines.append("")
    return "\n".join(lines) + "\n"


def _own_file():
    return HYPR_LUA_OWN if hypr_lua() else HYPR_CONF


def _main_file():
    return HYPR_LUA_MAIN if hypr_lua() else HYPR_MAIN


def source_line():
    return LUA_LINE if hypr_lua() else SOURCE_LINE


def hypr_write_conf():
    if not is_hypr() and not (os.path.exists(HYPR_CONF) or os.path.exists(HYPR_LUA_OWN)):
        return
    os.makedirs(HYPR_DIR, exist_ok=True)
    path, txt = _own_file(), hypr_conf_text()
    try:
        if open(path, encoding="utf-8").read() == txt:
            return
    except OSError:
        pass
    with open(path, "w", encoding="utf-8") as f:
        f.write(txt)


_SRC_RE = {False: r"^\s*source\s*=\s*\S*kontrollsenter\.conf",
           True: r"^[^-\n]*require\s*\(?\s*[,\s]*[\"']kontrollsenter[\"']"}


def hypr_sourced():
    """Leser hovedfilen (hyprland.lua eller hyprland.conf) inn Kontrollsenter sin fil?"""
    try:
        txt = open(_main_file(), encoding="utf-8", errors="replace").read()
    except OSError:
        return False
    return bool(re.search(_SRC_RE[hypr_lua()], txt, re.M))


def hypr_can_edit_main():
    m = _main_file()
    return os.path.isfile(m) and not os.path.islink(m) and os.access(m, os.W_OK)


def hypr_setup():
    """Ved oppstart på Hyprland: skriv Kontrollsenter sin fil og sørg for at den leses inn (hvis vi får lov)."""
    if not is_hypr():
        return
    hypr_write_conf()
    if hypr_sourced() or not hypr_can_edit_main():
        return
    if _load().get("hypr_source_removed"):             # brukeren har fjernet den – ikke legg den inn igjen
        return
    with open(_main_file(), "a", encoding="utf-8") as f:
        f.write("\n" + source_line() + "\n")


def hypr_remove():
    for main, lua in ((HYPR_MAIN, False), (HYPR_LUA_MAIN, True)):
        try:
            txt = open(main, encoding="utf-8").read()
        except OSError:
            continue
        pat = (r"\n?^[^-\n]*require\s*\(?\s*[,\s]*[\"']kontrollsenter[\"'].*$\n?" if lua else
               r"\n?^\s*source\s*=\s*\S*kontrollsenter\.conf.*$\n?")
        new = re.sub(pat, "\n", txt, flags=re.M)
        if new != txt and os.path.isfile(main) and not os.path.islink(main) and os.access(main, os.W_OK):
            with open(main, "w", encoding="utf-8") as f:
                f.write(new)
    for f in (HYPR_CONF, HYPR_LUA_OWN):
        try:
            os.remove(f)
        except FileNotFoundError:
            pass
    if is_hypr():
        for k in _load().get("keys", {}).values():
            try:
                _hypr_unbind_now(k["spec"])
            except (KeyError, ValueError):
                pass


def remove_all():
    """Fjern alt Kontrollsenter har lagt inn i Hyprland og GNOME (hurtigtaster, kontrollsenter.conf, source-linjen)."""
    if is_hypr() or os.path.exists(HYPR_CONF) or os.path.exists(HYPR_LUA_OWN):
        hypr_remove()
    if shutil.which("gsettings"):
        _gnome_unbind_all()
    d = _load()
    d.pop("keys", None)
    d.pop("hypr_gpu", None)
    d["hypr_source_removed"] = True
    _save(d)


# ---------------------------------------------------------------------------------------------------------------
# Oppstart ved innlogging på Hyprland: kjør Kontrollsenter sine oppstartsfiler (hvis ingen andre gjør det)
# ---------------------------------------------------------------------------------------------------------------
def _xdg_autostart_handled():
    """uwsm / systemd sin xdg-autostart-generator kjører ~/.config/autostart selv."""
    code, out = _run(["systemctl", "--user", "is-active", "xdg-desktop-autostart.target"], 5)
    return out.strip() == "active"


def run_autostart():
    import glob
    if _xdg_autostart_handled():
        return 0
    n = 0
    for f in sorted(glob.glob(os.path.expanduser("~/.config/autostart/systemmonitor-*.desktop"))):
        if _hidden(f):
            continue
        txt = open(f, encoding="utf-8", errors="replace").read()
        m = re.search(r"^Exec\s*=\s*(.+)$", txt, re.M)
        if not m:
            continue
        cmd = re.sub(r"\s%[fFuUdDnNickvm]", "", m.group(1)).strip()
        subprocess.Popen(["sh", "-c", cmd], start_new_session=True, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        n += 1
    return n


# ---------------------------------------------------------------------------------------------------------------
# GNOME: statusfelt-ikonet (AppIndicator)
# ---------------------------------------------------------------------------------------------------------------
def gnome_appindicator():
    """(«on»/«off»/«missing», uuid) for AppIndicator-utvidelsen i GNOME."""
    if not shutil.which("gnome-extensions"):
        return "missing", None
    code, out = _run(["gnome-extensions", "list"], 8)
    have = [u for u in APPINDICATOR if u in out]
    if not have:
        return "missing", None
    code, en = _run(["gnome-extensions", "list", "--enabled"], 8)
    return ("on" if have[0] in en else "off"), have[0]


def gnome_enable_appindicator():
    state, uuid = gnome_appindicator()
    if state == "off":
        return _run(["gnome-extensions", "enable", uuid], 10)[0] == 0
    return state == "on"


# ---------------------------------------------------------------------------------------------------------------
# Ved oppstart av Kontrollsenter
# ---------------------------------------------------------------------------------------------------------------
def setup(main_win):
    try:
        _setup(main_win)
    except Exception:  # noqa: BLE001 – skrivebordstilpasningen skal aldri stoppe programmet
        import logging
        logging.getLogger("systemmonitor").exception("skrivebord (desktop.setup)")


def _setup(main_win):
    k = kind()
    if k == "hyprland":
        try:
            hypr_setup()
        except OSError:
            pass
        install_windows(main_win)
    elif k == "gnome":
        d = _load()
        if not d.get("appindicator_tried"):          # én gang: slå på statusfelt-ikoner hvis utvidelsen finnes
            d["appindicator_tried"] = True
            _save(d)
            gnome_enable_appindicator()


def status():
    """Til Innstillinger: hva som er tilpasset på dette skrivebordet."""
    k = kind()
    s = {"kind": k, "name": name()}
    if k == "hyprland":
        s.update(version=hypr_version(), lua=hypr_lua(), conf=os.path.exists(_own_file()), sourced=hypr_sourced(),
                 can_edit=hypr_can_edit_main(), source_line=source_line(), main_file=os.path.basename(_main_file()), keys=len(_load().get("keys", {})),
                 autostart_by_systemd=_xdg_autostart_handled(), hyprsunset=bool(shutil.which("hyprsunset")))
    elif k == "gnome":
        s.update(appindicator=gnome_appindicator()[0], keys=len(_load().get("keys", {})))
    return s


if __name__ == "__main__":
    if "--autostart" in sys.argv:
        run_autostart()
