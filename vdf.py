"""Leser/skriver Valves tekstbaserte KeyValues-format (VDF), som Steam bruker til
localconfig.vdf, config.vdf, libraryfolders.vdf og appmanifest_*.acf.

Rekkefølgen på nøklene beholdes, slik at filen skrives tilbake slik Steam forventer.
"""


def _tokens(text):
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c == "/" and text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif c in "{}":
            yield c
            i += 1
        elif c == '"':
            i += 1
            buf = []
            while i < n and text[i] != '"':
                if text[i] == "\\" and i + 1 < n:
                    nxt = text[i + 1]
                    buf.append({"\\": "\\", '"': '"'}.get(nxt, "\\" + nxt))   # som Steam: bare \\ og \"
                    i += 2
                else:
                    buf.append(text[i])
                    i += 1
            i += 1
            yield ("s", "".join(buf))
        else:                                           # uten anførselstegn (sjelden)
            j = i
            while j < n and text[j] not in " \t\r\n{}\"":
                j += 1
            yield ("s", text[i:j])
            i = j


def loads(text):
    it = _tokens(text)

    def obj():
        d = {}
        for tok in it:
            if tok == "}":
                return d
            if tok == "{":
                raise ValueError("uventet {")
            key = tok[1]
            val = next(it)
            d[key] = obj() if val == "{" else val[1]
        return d
    return obj()


def _esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


def dumps(d, level=0):
    out = []
    ind = "\t" * level
    for k, v in d.items():
        if isinstance(v, dict):
            out.append(f'{ind}"{_esc(k)}"\n{ind}{{\n{dumps(v, level + 1)}{ind}}}\n')
        else:
            out.append(f'{ind}"{_esc(k)}"\t\t"{_esc(v)}"\n')
    return "".join(out)


def load(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return loads(f.read())


def dump(d, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write(dumps(d))


def get(d, *keys, default=None):
    """Hent nestet verdi; nøkler sammenlignes uten hensyn til store/små bokstaver (Steam blander)."""
    for k in keys:
        if not isinstance(d, dict):
            return default
        m = next((x for x in d if x.lower() == k.lower()), None)
        if m is None:
            return default
        d = d[m]
    return d


def ensure(d, *keys):
    """Hent eller lag nestet dict (gjenbruker eksisterende nøkkel med annen store/små-skriving)."""
    for k in keys:
        m = next((x for x in d if x.lower() == k.lower()), None)
        if m is None:
            d[k] = {}
            m = k
        d = d[m]
    return d
