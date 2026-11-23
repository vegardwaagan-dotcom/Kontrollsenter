"""AI rundt omkring i appen: morgenrapport, hurtigtast med lite spørsmålsvindu (som Spotlight), @ai i chatten
og «Spør AI om denne». Samme på Linux og Windows.
"""
import json
import os
import threading
import time

STATE = os.path.expanduser("~/.local/share/systemmonitor/ai-morgen.json")
_HK = {"h": None, "win": None}


def _tool():
    import ai
    t = ai.cfg().get("tool", "claude")
    if ai.binary(t) and ai.logged_in(t):
        return t
    for x in ai.TOOLS:                                     # første som er installert og pålogget
        if ai.binary(x) and ai.logged_in(x):
            return x
    return None


def ask_sync(prompt, timeout=240, control=True, history=""):
    """Spør AI-en og vent på hele svaret (brukes i bakgrunnen). Returnerer (verktøy, tekst, linjer)."""
    import ai
    import ai_store as S
    tool = _tool()
    if not tool:
        raise RuntimeError("ingen AI er installert og pålogget")
    out, tools, done = [], [], threading.Event()
    ai.ask(tool, prompt, S.workdir(), False, on_text=out.append, on_done=lambda _c: done.set(), history=history,
           control=control, on_event=lambda k, d: k == "tool" and tools.append(str(d)))
    done.wait(timeout)
    return tool, "".join(out).strip(), tools


# --------------------------------------------------------------------------
# Morgenrapport
# --------------------------------------------------------------------------
def daily_due():
    import ai
    if not ai.cfg().get("daily", True):
        return False
    lt = time.localtime()
    if lt.tm_hour < 8:
        return False
    try:
        with open(STATE) as f:
            return json.load(f).get("day") != time.strftime("%Y-%m-%d")
    except (OSError, ValueError):
        return True


def daily_report(win=None, force=False, notify=None):
    """Kort rapport om PC-en (temperaturer, feil, oppdateringer, disk) – lagres som en AI-samtale og varsles."""
    if not force and not daily_due():
        return None
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w") as f:                            # én gang i døgnet, også om det feiler
        json.dump({"day": time.strftime("%Y-%m-%d"), "t": time.time()}, f)
    prompt = ("Lag en kort morgenrapport om PC-en min (maks 8 linjer, punktvis, med emojier): bruk «ks status», "
              "«ks diagnose» og «ks logg». Ta med temperaturer, om noe er galt, feil i loggene og om noe bør "
              "oppdateres eller ryddes. Ikke endre noe. Avslutt med ett konkret råd for dagen.")
    tool, text, tools = ask_sync(prompt)
    if not text:
        return "Fikk ingen rapport"
    import ai_store as S
    c = S.new(tool)
    c["title"] = time.strftime("☀️ Morgenrapport %d.%m")
    c["emoji"] = "☀️"
    c["messages"] = [{"role": "user", "text": "Morgenrapport", "t": time.time()},
                     {"role": "assistant", "text": text, "t": time.time(), "tool": tool, "tools": tools}]
    S.save(c)
    if notify:
        from gi.repository import GLib
        first = next((ln for ln in text.splitlines() if ln.strip()), text)[:160]
        GLib.idle_add(lambda: (notify("ai_daily", "☀️ Morgenrapport fra AI-en", first, force=True,
                                      action="app.show"), False)[1])
    return "Morgenrapporten ligger under AI"


def daily_tick(win, notify=None):
    if daily_due():
        threading.Thread(target=lambda: _safe(lambda: daily_report(win, notify=notify)), daemon=True).start()


def _safe(fn):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------
# Hurtigtast: lite spørsmålsvindu oppå alt
# --------------------------------------------------------------------------
def hotkey_setup(win):
    import ai
    _HK["win"] = win
    if not ai.cfg().get("hotkey", True) or _HK["h"] is not None:
        return
    try:
        import clips
        from gi.repository import GLib
        _HK["h"] = clips.Hotkey(lambda: GLib.idle_add(lambda: (_hotkey_pressed(), False)[1]),
                                ai.cfg().get("hotkey_key") or "Ctrl+Shift+A", ("spor-ai", "Spør AI-en"), 0x4B5A)
    except Exception as e:  # noqa: BLE001
        _HK["err"] = str(e)


def _hotkey_pressed():
    import ai
    if ai.cfg().get("hotkey", True):
        quick_window(_HK["win"])


def quick_window(win=None, text=""):
    """Spør AI-en raskt: et lite vindu med skrivefelt, svaret strømmes inn. «Åpne i AI» tar samtalen videre."""
    import gi
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gdk, GLib, Gtk
    import ai
    import ai_store as S
    w = Gtk.Window(title="Spør AI-en", default_width=560, default_height=120, resizable=True)
    w.add_css_class("ks-quick-ai")
    if win is not None:
        w.set_transient_for(win)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12, margin_start=12,
                  margin_end=12)
    e = Gtk.Entry(placeholder_text="Spør om hva som helst … (Enter sender, Esc lukker)", text=text)
    box.append(e)
    clip = Gtk.Button(label="📋 Forklar det jeg har kopiert", halign=Gtk.Align.START)
    clip.add_css_class("flat")
    box.append(clip)
    ans = Gtk.Label(xalign=0, wrap=True, selectable=True, max_width_chars=70, visible=False)
    sc = Gtk.ScrolledWindow(child=ans, propagate_natural_height=True, max_content_height=420,
                            hscrollbar_policy=Gtk.PolicyType.NEVER)
    box.append(sc)
    row = Gtk.Box(spacing=8, visible=False)
    st = Gtk.Label(xalign=0, hexpand=True)
    st.add_css_class("dim-label")
    row.append(st)
    op = Gtk.Button(label="Åpne i AI")
    row.append(op)
    box.append(row)
    w.set_child(box)
    state = {"conv": None, "text": ""}

    def go(q):
        q = q.strip()
        if not q:
            return
        tool = _tool()
        if not tool:
            ans.set_label("Ingen AI er installert og pålogget – se AI-siden.")
            ans.set_visible(True)
            return
        c = S.new(tool)
        c["messages"].append({"role": "user", "text": q, "t": time.time()})
        S.save(c, push_now=False)
        state.update(conv=c, text="")
        ans.set_label("• • •")
        ans.set_visible(True)
        row.set_visible(True)
        st.set_label(ai.TOOLS[tool]["name"] + " tenker …")

        def add(t):
            state["text"] += t
            GLib.idle_add(lambda: (ans.set_label(state["text"].strip() or "• • •"), False)[1])

        def done(_code):
            def fin():
                c["messages"].append({"role": "assistant", "text": state["text"].strip(), "t": time.time(),
                                      "tool": tool})
                S.save(c)
                st.set_label("")
                return False
            GLib.idle_add(fin)
        ai.ask(tool, q, S.workdir(), False, on_text=add, on_done=done, control=ai.cfg().get("control", True),
               on_event=lambda k, d: k == "tool" and GLib.idle_add(lambda: (st.set_label(str(d)), False)[1]))

    e.connect("activate", lambda *_: go(e.get_text()))

    def explain_clip(*_):
        cb = Gdk.Display.get_default().get_clipboard()

        def got(c, res):
            try:
                t = c.read_text_finish(res) or ""
            except GLib.Error:
                t = ""
            if t.strip():
                go("Forklar dette kort og enkelt:\n\n" + t[:4000])
        cb.read_text_async(None, got)
    clip.connect("clicked", explain_clip)

    def open_ai(*_):
        if win is not None and state["conv"]:
            try:
                page = win.ensure_lazy("ai")
                win.stack.set_visible_child_name("ai")
                win.present()
                if page is not None:
                    page._reload_list()
                    page._open(state["conv"]["id"])
            except Exception:  # noqa: BLE001
                pass
        w.close()
    op.connect("clicked", open_ai)
    k = Gtk.EventControllerKey()
    k.connect("key-pressed", lambda _c, kv, _co, _s: (w.close(), True)[1] if kv == Gdk.KEY_Escape else False)
    w.add_controller(k)
    w.present()
    e.grab_focus()
    if text:
        go(text)
    return w


# --------------------------------------------------------------------------
# @ai i chatten – svaret kommer fra AI-en på PC-en som spurte
# --------------------------------------------------------------------------
def chat_ai(room, question, notify=None):
    import chat
    import savegames
    hist = "\n".join(f"{m.get('from')}: {m.get('text', '')}" for m in chat.messages(room, 20)[-20:])
    tool, text, _tools = ask_sync(
        f"Du svarer i en chat mellom venner (Kontrollsenter). Svar kort (maks 6 linjer), vennlig og på norsk. "
        f"Ikke endre noe på PC-en.\n\nSpørsmål: {question}", history=hist, control=True)
    import ai
    name = ai.TOOLS.get(tool, {}).get("name", "AI")
    return chat.send(room, text or "(fikk ikke svar)", f"✨ {name} (for {savegames.pc_name()})", notify,
                     extra={"kind": "ai"})
