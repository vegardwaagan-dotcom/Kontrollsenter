"""Liten QR-kode-generator (byte-modus, feilretting M, versjon 1–10) – uten eksterne pakker.

Brukes til gjeste-Wi-Fi («WIFI:T:WPA;S:navn;P:passord;;») og koblinger som skal skannes med mobilen.
Følger ISO/IEC 18004 (samme algoritme som de vanlige bibliotekene).
"""

# (totalt antall kodeord, feilrettingskodeord per blokk, [(antall blokker, datakodeord per blokk)]) for nivå M
_M = {1: (26, 10, [(1, 16)]), 2: (44, 16, [(1, 28)]), 3: (70, 26, [(1, 44)]), 4: (100, 18, [(2, 32)]),
      5: (134, 24, [(2, 43)]), 6: (172, 16, [(4, 27)]), 7: (196, 18, [(4, 31)]),
      8: (242, 22, [(2, 38), (2, 39)]), 9: (292, 22, [(3, 36), (2, 37)]), 10: (346, 26, [(4, 43), (1, 44)])}
_ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42],
          9: [6, 26, 46], 10: [6, 28, 50]}

# ---- GF(256) ----
_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _mul(a, b):
    return 0 if a == 0 or b == 0 else _EXP[_LOG[a] + _LOG[b]]


def _rs_gen(n):
    g = [1]
    for i in range(n):
        ng = [0] * (len(g) + 1)
        for j, c in enumerate(g):
            ng[j] ^= c
            ng[j + 1] ^= _mul(c, _EXP[i])
        g = ng
    return g


def _rs_ec(data, n):
    gen = _rs_gen(n)
    res = list(data) + [0] * n
    for i in range(len(data)):
        c = res[i]
        if c:
            for j in range(1, len(gen)):
                res[i + j] ^= _mul(gen[j], c)
    return res[len(data):]


def _data_cw(data, ver):
    total, ecn, groups = _M[ver]
    nd = sum(k * d for k, d in groups)
    bits = []

    def put(v, n):
        bits.extend((v >> (n - 1 - i)) & 1 for i in range(n))
    put(0b0100, 4)
    put(len(data), 8 if ver < 10 else 16)
    for b in data:
        put(b, 8)
    cap = nd * 8
    put(0, min(4, cap - len(bits)))
    while len(bits) % 8:
        bits.append(0)
    cw = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    i = 0
    while len(cw) < nd:                                  # utfylling: 0xEC, 0x11, 0xEC …
        cw.append(0xEC if i % 2 == 0 else 0x11)
        i += 1
    return cw


def _interleave(cw, ver):
    _total, ecn, groups = _M[ver]
    blocks, i = [], 0
    for k, d in groups:
        for _ in range(k):
            blocks.append(cw[i:i + d])
            i += d
    ecs = [_rs_ec(b, ecn) for b in blocks]
    out = []
    for j in range(max(len(b) for b in blocks)):
        for b in blocks:
            if j < len(b):
                out.append(b[j])
    for j in range(ecn):
        for e in ecs:
            out.append(e[j])
    return out


def _bch(value, poly, bits_poly):
    v = value << (bits_poly - 1)
    while v.bit_length() >= bits_poly:
        v ^= poly << (v.bit_length() - bits_poly)
    return v


class _Grid:
    def __init__(self, ver):
        self.n = n = 17 + 4 * ver
        self.ver = ver
        self.m = [[False] * n for _ in range(n)]
        self.f = [[False] * n for _ in range(n)]          # funksjonsmoduler

    def set(self, x, y, v):
        self.m[y][x] = v
        self.f[y][x] = True

    def functions(self):
        n = self.n
        for i in range(n):
            self.set(6, i, i % 2 == 0)
            self.set(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < n and 0 <= y < n:
                        d = max(abs(dx), abs(dy))
                        self.set(x, y, d not in (2, 4))
        al = _ALIGN[self.ver]
        for i, a in enumerate(al):
            for j, b in enumerate(al):
                if (i == 0 and j == 0) or (i == 0 and j == len(al) - 1) or (i == len(al) - 1 and j == 0):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self.set(a + dx, b + dy, max(abs(dx), abs(dy)) != 1)
        self.format_bits(0)
        if self.ver >= 7:
            rem = _bch(self.ver, 0x1F25, 13)
            bits = self.ver << 12 | rem
            for i in range(18):
                bit = (bits >> i) & 1 == 1
                a, b = n - 11 + i % 3, i // 3
                self.set(a, b, bit)
                self.set(b, a, bit)

    def format_bits(self, mask):
        n = self.n
        data = (0b00 << 3) | mask                        # nivå M = 00
        bits = ((data << 10) | _bch(data, 0x537, 11)) ^ 0x5412
        for i in range(6):
            self.set(8, i, (bits >> i) & 1 == 1)
        self.set(8, 7, (bits >> 6) & 1 == 1)
        self.set(8, 8, (bits >> 7) & 1 == 1)
        self.set(7, 8, (bits >> 8) & 1 == 1)
        for i in range(9, 15):
            self.set(14 - i, 8, (bits >> i) & 1 == 1)
        for i in range(8):
            self.set(n - 1 - i, 8, (bits >> i) & 1 == 1)
        for i in range(8, 15):
            self.set(8, n - 15 + i, (bits >> i) & 1 == 1)
        self.set(8, n - 8, True)

    def place(self, cws):
        n = self.n
        bits = [(c >> (7 - i)) & 1 for c in cws for i in range(8)]
        i = 0
        right = n - 1
        while right >= 1:
            if right == 6:
                right = 5
            for vert in range(n):
                for j in range(2):
                    x = right - j
                    upward = ((right + 1) & 2) == 0
                    y = n - 1 - vert if upward else vert
                    if not self.f[y][x] and i < len(bits):
                        self.m[y][x] = bits[i] == 1
                        i += 1
                    elif not self.f[y][x]:
                        self.m[y][x] = False
            right -= 2

    def apply_mask(self, mask):
        fns = [lambda x, y: (x + y) % 2 == 0, lambda x, y: y % 2 == 0, lambda x, y: x % 3 == 0,
               lambda x, y: (x + y) % 3 == 0, lambda x, y: (x // 3 + y // 2) % 2 == 0,
               lambda x, y: x * y % 2 + x * y % 3 == 0, lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
               lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0]
        f = fns[mask]
        for y in range(self.n):
            for x in range(self.n):
                if not self.f[y][x] and f(x, y):
                    self.m[y][x] = not self.m[y][x]

    def penalty(self):
        n, m, p = self.n, self.m, 0
        for rows in (m, [list(c) for c in zip(*m)]):
            for row in rows:
                run, col = 1, row[0]
                for x in range(1, n):
                    if row[x] == col:
                        run += 1
                        if run == 5:
                            p += 3
                        elif run > 5:
                            p += 1
                    else:
                        run, col = 1, row[x]
                s = "".join("1" if v else "0" for v in row)
                for pat in ("10111010000", "00001011101"):
                    i = s.find(pat)
                    while i != -1:
                        p += 40
                        i = s.find(pat, i + 1)
        for y in range(n - 1):
            for x in range(n - 1):
                c = m[y][x]
                if c == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                    p += 3
        dark = sum(v for row in m for v in row)
        k = abs(dark * 20 - n * n * 10) // (n * n)
        p += k * 10
        return p


def matrix(text, mask=None, version=None):
    """QR-matrise ([[bool]]) for teksten (UTF-8)."""
    data = text.encode("utf-8")
    ver = version
    if ver is None:
        for v in range(1, 11):
            nd = sum(k * d for k, d in _M[v][2])
            if 4 + (8 if v < 10 else 16) + 8 * len(data) <= nd * 8:
                ver = v
                break
    if ver is None:
        raise ValueError("for mye tekst til QR-koden")
    cws = _interleave(_data_cw(data, ver), ver)
    best = None
    for msk in ([mask] if mask is not None else range(8)):
        g = _Grid(ver)
        g.functions()
        g.place(cws)
        g.apply_mask(msk)
        g.format_bits(msk)
        if mask is not None:
            return g.m
        p = g.penalty()
        if best is None or p < best[0]:
            best = (p, g.m)
    return best[1]


def wifi_text(ssid, password, kind="WPA", hidden=False):
    def esc(s):
        return "".join("\\" + c if c in '\\;,":' else c for c in s)
    return f"WIFI:T:{kind if password else 'nopass'};S:{esc(ssid)};" + (f"P:{esc(password)};" if password else "") + \
        ("H:true;" if hidden else "") + ";"


def draw(cr, m, size, fg=(0, 0, 0), bg=(1, 1, 1), quiet=4):
    """Tegn matrisen med cairo i et kvadrat på size × size."""
    n = len(m) + 2 * quiet
    s = size / n
    cr.set_source_rgb(*bg)
    cr.rectangle(0, 0, size, size)
    cr.fill()
    cr.set_source_rgb(*fg)
    for y, row in enumerate(m):
        for x, v in enumerate(row):
            if v:
                cr.rectangle((x + quiet) * s, (y + quiet) * s, s + 0.5, s + 0.5)
    cr.fill()
