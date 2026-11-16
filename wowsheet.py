"""WoW: karakterarket (Armor, Strength, Intellect …), talentfordeling og råd om hva du bør ha mer av
ut fra klasse og spec (Classic). Tallene kommer fra addonen; rådene er en innebygd tabell + enkle sjekker.
"""

NAMES = {"str": "Strength", "agi": "Agility", "sta": "Stamina", "int": "Intellect", "spi": "Spirit",
         "armor": "Armor", "ap": "Attack Power", "rap": "Ranged Attack Power", "crit": "Crit (nærkamp)",
         "rcrit": "Crit (avstand)", "scrit": "Crit (magi)", "dodge": "Dodge", "parry": "Parry", "block": "Block",
         "hit": "Hit (fra utstyr)", "shit": "Spell hit (fra utstyr)", "sp": "Spell Power", "heal": "Healing",
         "def": "Defense", "hp": "Liv", "mana": "Mana"}
RES = {2: "Fire", 3: "Nature", 4: "Frost", 5: "Shadow", 6: "Arcane"}
PCT = {"crit", "rcrit", "scrit", "dodge", "parry", "block", "hit", "shit"}
BASE = ("str", "agi", "sta", "int", "spi")

# klasse -> [(spec (tre 1, 2, 3), prioritet, kort forklaring)]
# prioritet bruker nøklene over + «mp5» og «weapon» (våpenferdighet) som bare vises som tekst
PRIO = {
    "WARRIOR": [("Arms", ["hit", "str", "crit", "agi", "sta"], "To-hånds skade: Hit til 6 %, så Strength og Crit."),
                ("Fury", ["hit", "str", "crit", "agi", "sta"], "To våpen: Hit er viktigst (opptil 9 %), så Strength og Crit."),
                ("Protection", ["def", "sta", "armor", "hit", "str", "agi"], "Tank: Defense (440 for raid), Stamina og Armor. Hit og Strength gir trusselnivå.")],
    "PALADIN": [("Holy", ["heal", "int", "mp5", "scrit", "sta"], "Healer: Healing og Intellect, så mana per 5 sek og Crit."),
                ("Protection", ["sta", "def", "sp", "armor", "int"], "Tank: Stamina, Defense og Spell Power (Holy-skade gir trussel)."),
                ("Retribution", ["str", "hit", "crit", "agi", "int", "sta"], "Skade: Strength, Hit og Crit. Litt Intellect for mana.")],
    "HUNTER": [("Beast Mastery", ["agi", "hit", "crit", "rap", "int", "sta"], "Agility først, så Hit (6 %) og Crit. Intellect for mana."),
               ("Marksmanship", ["agi", "hit", "crit", "rap", "int", "sta"], "Agility først, så Hit (6 %) og Crit. Intellect for mana."),
               ("Survival", ["agi", "hit", "crit", "rap", "int", "sta"], "Agility gir mest (talentene øker den), så Hit og Crit.")],
    "ROGUE": [("Assassination", ["hit", "agi", "crit", "ap", "str", "sta"], "Hit (opptil 9 % med to våpen), så Agility og Crit."),
              ("Combat", ["hit", "agi", "crit", "weapon", "ap", "sta"], "Hit først, så Agility, Crit og våpenferdighet."),
              ("Subtlety", ["hit", "agi", "crit", "ap", "sta"], "Hit, Agility og Crit.")],
    "PRIEST": [("Discipline", ["heal", "int", "spi", "mp5", "sta"], "Healer: Healing, Intellect og Spirit."),
               ("Holy", ["heal", "spi", "int", "mp5", "sta"], "Healer: Healing og Spirit (talentene gjør Spirit sterk), så Intellect."),
               ("Shadow", ["shit", "sp", "int", "sta", "spi", "scrit"], "Skade: Spell hit, Spell Power (Shadow), Intellect og Stamina.")],
    "SHAMAN": [("Elemental", ["shit", "sp", "scrit", "int", "mp5"], "Spell hit, Spell Power og Crit, så Intellect."),
               ("Enhancement", ["hit", "str", "crit", "agi", "ap", "int"], "Hit, Strength og Crit. Litt Intellect for mana."),
               ("Restoration", ["heal", "mp5", "int", "scrit", "sta"], "Healer: Healing og mana per 5 sek, så Intellect.")],
    "MAGE": [("Arcane", ["shit", "sp", "int", "scrit", "spi", "sta"], "Spell hit, Spell Power, Intellect (Arcane gjør Intellect sterk)."),
             ("Fire", ["shit", "sp", "scrit", "int", "sta"], "Spell hit, Spell Power og Crit (Fire elsker Crit)."),
             ("Frost", ["shit", "sp", "int", "scrit", "sta"], "Spell hit, Spell Power og Intellect.")],
    "WARLOCK": [("Affliction", ["shit", "sp", "sta", "int", "spi"], "Spell hit, Spell Power og Stamina (Life Tap)."),
                ("Demonology", ["shit", "sp", "sta", "int"], "Spell hit, Spell Power og Stamina."),
                ("Destruction", ["shit", "sp", "scrit", "int", "sta"], "Spell hit, Spell Power og Crit.")],
    "DRUID": [("Balance", ["shit", "sp", "scrit", "int", "mp5"], "Spell hit, Spell Power og Crit, så Intellect."),
              ("Feral Combat", ["str", "agi", "hit", "crit", "sta", "armor"], "Katt: Strength/Agility, Hit og Crit. Bjørn: Stamina, Armor og Agility."),
              ("Restoration", ["heal", "int", "spi", "mp5", "sta"], "Healer: Healing, Intellect og Spirit.")],
}
LEVELING = {
    "WARRIOR": "Strength og Stamina", "PALADIN": "Strength, Stamina og litt Intellect", "HUNTER": "Agility, så Stamina og Intellect",
    "ROGUE": "Agility og Stamina", "PRIEST": "Intellect, Spirit og Stamina", "SHAMAN": "Strength/Intellect og Stamina",
    "MAGE": "Intellect, Spirit og Stamina", "WARLOCK": "Stamina og Spirit (Life Tap), så Intellect",
    "DRUID": "Strength/Agility (katt) eller Intellect og Spirit (Balance)"}
EXTRA = {"mp5": "mana per 5 sek", "weapon": "våpenferdighet (Swords/Maces …)"}


def _fmt(k, v):
    if v is None:
        return "–"
    if k in PCT:
        return f"{v:.1f} %"
    return f"{int(round(v)):,}".replace(",", " ")


def spec(c):
    """(indeks 0–2, navn, poeng per tre) – eller None før talentene starter (level 10)."""
    t = c.get("talents") or {}
    rows = [t[k] for k in sorted(t)] if isinstance(t, dict) else list(t)
    pts = [int((r or {}).get("points") or 0) for r in rows if isinstance(r, dict)]
    if not pts or max(pts) == 0:
        return None
    i = pts.index(max(pts))
    return i, (rows[i] or {}).get("name") or "", pts


def analyse(c):
    """Karakterarket + råd for én karakter, eller None hvis addonen ikke har lest det ennå."""
    s = c.get("sheet")
    if not isinstance(s, dict):
        return None
    cls = str(c.get("class") or "").upper()
    lvl = int(c.get("level") or 0)
    sp = spec(c)
    table = PRIO.get(cls) or []
    prio_spec = table[sp[0]] if sp and sp[0] < len(table) else None
    rows = [(NAMES[k], _fmt(k, s.get(k))) for k in BASE if s.get(k) is not None]
    rows += [(NAMES[k], _fmt(k, s.get(k))) for k in ("armor", "hp", "mana", "ap", "rap", "sp", "heal", "def",
                                                      "crit", "rcrit", "scrit", "hit", "shit", "dodge", "parry", "block")
             if s.get(k) not in (None, 0) or k in ("armor", "hp")]
    res = s.get("res") or {}
    if isinstance(res, list):
        res = {i + 1: v for i, v in enumerate(res)}
    res_rows = [(RES[int(k)], int(v)) for k, v in res.items() if str(k).isdigit() and int(k) in RES and v]

    tips = []
    unspent = int(c.get("unspent") or 0)
    if unspent > 0:
        tips.append(f"Du har {unspent} talentpoeng som ikke er brukt – trykk N i spillet og bruk dem.")
    if lvl and lvl < 10:
        tips.append("Talenter får du fra level 10.")
    if sp and len(sp[2]) == 3 and sorted(sp[2])[-1] - sorted(sp[2])[-2] <= 2 and sum(sp[2]) >= 10:
        tips.append("Talentene er spredt jevnt – du får mest ut av å satse på ett tre.")
    prio = []
    if prio_spec:
        name, keys, why = prio_spec
        prio = [NAMES.get(k) or EXTRA.get(k, k) for k in keys]
        # hovedegenskapen: den første av de fem grunnegenskapene i prioriteringen
        main = next((k for k in keys if k in BASE), None)
        if main and s.get(main) is not None:
            others = [k for k in BASE if k not in (main, "sta") and k not in keys[:4] and (s.get(k) or 0) > (s.get(main) or 0) * 1.15]
            if others:
                tips.append(f"Du har mer {', '.join(NAMES[k] for k in others)} enn {NAMES[main]} – som {name} gir "
                            f"{NAMES[main]} mest. Velg utstyr med {NAMES[main]}.")
        if lvl >= 60:
            if "hit" in keys[:2] and (s.get("hit") or 0) < 6:
                tips.append(f"Hit fra utstyret er {s.get('hit') or 0:.0f} % – prøv å komme opp i 6 % (så du bommer mindre).")
            if "shit" in keys[:2] and (s.get("shit") or 0) < 10:
                tips.append(f"Spell hit fra utstyret er {s.get('shit') or 0:.0f} % – opptil 10 % (16 % uten talenter) "
                            "gjør at færre trylleformler bommer på bosser.")
            if keys[0] == "def" and (s.get("def") or 0) < 440:
                tips.append(f"Defense er {int(s.get('def') or 0)} – tanker trenger 440 for at bosser ikke skal få kritiske treff.")
        if lvl < 60:
            tips.append(f"Mens du levler: {LEVELING.get(cls, 'hovedegenskapen og Stamina')} gir mest.")
    elif lvl < 60 and cls in LEVELING:
        tips.append(f"Mens du levler: {LEVELING[cls]} gir mest.")
    if not tips:
        tips.append("Bra balanse ut fra spec-en – fortsett å velge utstyr etter prioriteringen.")
    return {"rows": rows, "res": res_rows, "spec": (prio_spec[0] if prio_spec else (sp[1] if sp else None)),
            "talents": [{"name": (r or {}).get("name"), "points": p} for r, p in
                        zip([c["talents"][k] for k in sorted(c["talents"])] if isinstance(c.get("talents"), dict)
                            else (c.get("talents") or []), sp[2] if sp else [])] if sp else [],
            "unspent": unspent, "prio": prio, "why": prio_spec[2] if prio_spec else None, "tips": tips,
            "updated": c.get("sheet_t")}
