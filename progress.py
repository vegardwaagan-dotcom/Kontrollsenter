"""Felles fremdrift for alt som tar tid: installasjoner, nedlastinger, opprydding, sjekker og retting.

    with progress.task("Installerer Discord") as t:
        t.set(0.4, "Laster ned …")            # 40 %
        t.step(3, 10, "Sjekker vifter")        # 3 av 10
    code, out = progress.run_cmd([...], t)  # prosent leses fra programmets egen utskrift (flatpak, winget …)
    progress.download(url, fil, t)          # prosent og tid fra antall byte

Vinduet viser oppgavene nederst (progress_ui.Dock): hva som skjer, prosent og estimert tid igjen.
Trådsikkert – kan kalles fra bakgrunnstråder.
"""
import contextlib
import re
import subprocess
import sys
import threading
import time

IS_WIN = sys.platform == "win32"
_LOCK = threading.Lock()
TASKS = []                                  # aktive og nettopp ferdige oppgaver
_LISTENERS = []
_PCT = re.compile(rb"(\d{1,3}(?:[.,]\d+)?)\s?%")
_FRAC = re.compile(rb"\b(\d+)\s?/\s?(\d+)\b")


def on_change(fn):
    _LISTENERS.append(fn)


def _notify():
    for fn in list(_LISTENERS):
        try:
            fn()
        except Exception:  # noqa: BLE001
            pass


class Task:
    def __init__(self, title, detail=""):
        self.title, self.detail = title, detail
        self.frac = None                         # None = vet ikke ennå (pulserer)
        self.t0 = time.monotonic()
        self.samples = []                        # (tid, andel) – til å regne ut tiden som er igjen
        self.finished = None                     # tidspunkt ferdig
        self.ok = True
        self.result = ""
        self._eta = None

    # ---- oppdatering ----
    def set(self, frac=None, detail=None):
        with _LOCK:
            if frac is not None:
                f = max(0.0, min(1.0, float(frac)))
                if self.frac is None or f >= self.frac - 0.002:        # aldri baklengs (unngår hopping)
                    self.frac = f
                    now = time.monotonic()
                    self.samples.append((now, f))
                    self.samples = [s for s in self.samples if now - s[0] < 20][-60:]
            if detail is not None:
                self.detail = detail
        return self

    def step(self, i, n, detail=None):
        return self.set(i / max(1, n), detail)

    def sub(self, lo, hi):
        """En del av oppgaven (f.eks. nedlasting = 0–70 %, installasjon = 70–100 %)."""
        return _Sub(self, lo, hi)

    def done(self, result="", ok=True):
        with _LOCK:
            self.finished = time.monotonic()
            self.ok, self.result = ok, result
            if ok:
                self.frac = 1.0
        _notify()

    # ---- visning ----
    def eta(self):
        """Sekunder igjen (glattet), eller None."""
        if self.frac is None or self.frac <= 0.02 or self.finished:
            return None
        now = time.monotonic()
        rate = None
        if len(self.samples) >= 2:
            t1, f1 = self.samples[0]
            t2, f2 = self.samples[-1]
            if t2 - t1 > 1.5 and f2 > f1:
                rate = (f2 - f1) / (t2 - t1)
        if rate is None:
            el = now - self.t0
            if el < 3:
                return None
            rate = self.frac / el
        if rate <= 0:
            return None
        est = (1 - self.frac) / rate
        self._eta = est if self._eta is None else self._eta * 0.7 + est * 0.3
        return self._eta

    def eta_text(self):
        if self.finished:
            return ""
        e = self.eta()
        if e is None:
            return "beregner tid …" if time.monotonic() - self.t0 > 2 else ""
        if e < 10:
            return "nesten ferdig"
        if e < 60:
            return f"ca. {int(round(e / 5) * 5)} s igjen"
        if e < 3600:
            m = int(round(e / 60))
            return f"ca. {m} min igjen"
        return f"ca. {e / 3600:.1f} t igjen"

    def pct_text(self):
        return "" if self.frac is None else f"{int(self.frac * 100)} %"


class _Sub:
    def __init__(self, parent, lo, hi):
        self.p, self.lo, self.hi = parent, lo, hi

    def set(self, frac=None, detail=None):
        self.p.set(None if frac is None else self.lo + (self.hi - self.lo) * max(0.0, min(1.0, frac)), detail)
        return self

    def step(self, i, n, detail=None):
        return self.set(i / max(1, n), detail)

    def sub(self, lo, hi):
        return _Sub(self.p, self.lo + (self.hi - self.lo) * lo, self.lo + (self.hi - self.lo) * hi)


class _Null:
    """Når ingen fremdrift er ønsket."""
    def set(self, *a, **k):
        return self

    def step(self, *a, **k):
        return self

    def sub(self, *a, **k):
        return self


NULL = _Null()


def begin(title, detail=""):
    t = Task(title, detail)
    with _LOCK:
        TASKS.append(t)
        # rydd bort gamle ferdige
        now = time.monotonic()
        TASKS[:] = [x for x in TASKS if not x.finished or now - x.finished < 8]
    _notify()
    return t


@contextlib.contextmanager
def task(title, detail="", done_text=None):
    t = begin(title, detail)
    try:
        yield t
    except Exception as e:  # noqa: BLE001
        t.done(str(e)[:120], ok=False)
        raise
    else:
        t.done(done_text or "Ferdig")


def active():
    now = time.monotonic()
    with _LOCK:
        return [t for t in TASKS if not t.finished or now - t.finished < (3.0 if t.ok else 7.0)]


# --------------------------------------------------------------------------
# Hjelpere
# --------------------------------------------------------------------------
def run_cmd(cmd, t=NULL, timeout=3600, detail_from_output=True, **kw):
    """Kjør et program og les prosent fra utskriften (flatpak, winget, pip …). Returnerer (kode, utskrift)."""
    flags = {"creationflags": 0x08000000} if IS_WIN else {}
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, **flags, **kw)
    out = bytearray()
    end = time.monotonic() + timeout
    buf = b""
    while True:
        chunk = p.stdout.read1(4096) if hasattr(p.stdout, "read1") else p.stdout.read(4096)
        if not chunk:
            break
        out += chunk
        buf = (buf + chunk)[-4096:]
        parts = re.split(rb"[\r\n]", buf)
        last = next((x for x in reversed(parts) if x.strip()), b"")
        m = None
        for mm in _PCT.finditer(last):
            m = mm
        if m:
            try:
                t.set(float(m.group(1).replace(b",", b".")) / 100)
            except ValueError:
                pass
        elif _FRAC.search(last) and b"MB" not in last and b"KB" not in last:
            a, b = (int(x) for x in _FRAC.search(last).groups())
            if 0 < b < 1000 and a <= b:
                t.set((a - 1) / b if a else 0)
        if detail_from_output and last.strip():
            txt = re.sub(r"[█▏▎▍▌▋▊▉░▒▓\-\\|/]{3,}", "", last.decode(errors="replace")).strip()
            if 3 < len(txt) < 90:
                t.set(None, txt)
        if time.monotonic() > end:
            p.kill()
            break
    p.wait()
    return p.returncode, out.decode(errors="replace")


def download(url, dest, t=NULL, headers=None, timeout=300):
    """Last ned med prosent og tid igjen (fra Content-Length)."""
    import urllib.request
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Kontrollsenter"})
    with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        last = 0.0
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            now = time.monotonic()
            if now - last > 0.2:
                last = now
                mb = got / 1048576
                t.set(got / total if total else None,
                      f"Laster ned … {mb:.0f} av {total / 1048576:.0f} MB" if total else f"Laster ned … {mb:.0f} MB")
    t.set(1.0)
    return dest
