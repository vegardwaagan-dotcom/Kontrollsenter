"""Talekommandoer fra TV-fjernkontrollen (mikrofonknappen) eller telefonen: «spillmodus på», «demp», «volum 30»,
«stille i to timer», «middag», «beskjed kom ned nå», «scene filmkveld», «lagre klipp» …

Vanlig norsk tolkes her uten AI (raskt og uten nett). Det som ikke kjennes igjen, sendes til AI-en hvis du vil.
"""
import re

NUM = {"en": 1, "ett": 1, "én": 1, "to": 2, "tre": 3, "fire": 4, "fem": 5, "seks": 6, "ti": 10, "tjue": 20,
       "tretti": 30, "førti": 40, "femti": 50, "seksti": 60, "sytti": 70, "åtti": 80, "nitti": 90, "hundre": 100}


def _num(s):
    m = re.search(r"\d+", s)
    if m:
        return int(m.group())
    for w, v in NUM.items():
        if re.search(rf"\b{w}\b", s):
            return v
    return None


def run(win, text, frm="Fjernkontrollen"):
    """→ (ok, svar). Utfører kommandoen via de vanlige handlingene (samme som knappene i appen)."""
    import remote
    t = (text or "").lower().strip().rstrip(".!?")
    if not t:
        return False, "Hørte ingenting"

    def act(a):
        return remote.do_action(win, a)
    if "spillmodus" in t or "spill modus" in t:
        on = not re.search(r"\b(av|slå av|stopp)\b", t)
        return act({"a": "gamemode", "on": on})
    if re.search(r"\b(demp|lyd av|mute)\b", t):
        return act({"a": "volume", "mute": True})
    if re.search(r"\blyd(en)? på\b|\bskru på lyden\b", t):
        return act({"a": "volume", "mute": False})
    if "volum" in t:
        n = _num(t)
        if n is None:
            return False, "Si f.eks. «volum 30»"
        return act({"a": "volume", "volume": max(0, min(100, n))})
    if "stille" in t:
        import pcplus
        h = _num(t) or 1
        return True, pcplus.quiet_for(0 if re.search(r"\bav\b", t) else min(12, h))
    if "middag" in t and "plan" not in t:
        return act({"a": "dinner"})
    m = re.match(r"(beskjed|si til alle|send beskjed)\s*(til alle)?\s*[:,]?\s*(.+)", t)
    if m:
        import hjem5
        return True, hjem5.broadcast(text.strip()[len(text.strip()) - len(m.group(3)):], frm)
    if re.search(r"\b(lagre klipp|ta klipp|klipp)\b", t):
        return act({"a": "clip"})
    if "skjermtest" in t:
        return act({"a": "skjermtest"})
    if re.search(r"\b(pause|spill av|play)\b", t):
        return act({"a": "media", "cmd": "PlayPause"})
    if re.search(r"\bneste\b", t):
        return act({"a": "media", "cmd": "Next"})
    import scenes
    for s in scenes.load()["scenes"]:                     # «scene filmkveld» eller bare «filmkveld»
        if s["name"].lower() in t:
            return act({"a": "scene", "id": s["id"]})
    return False, (f"Forstod ikke «{text}». Prøv «spillmodus på», «demp», «volum 30», «stille i to timer», "
                   "«middag», «beskjed kom ned», «lagre klipp» eller navnet på en scene.")
