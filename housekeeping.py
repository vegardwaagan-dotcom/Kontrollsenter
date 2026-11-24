"""Rydding i egne prosesser (Linux):

* Etter en omstart (ny versjon) beholder Kontrollsenter samme prosessnummer. Barneprosesser fra forrige utgave som
  er avsluttet, blir da liggende som «zombier», og webkamera-overlayet fra forrige utgave fortsetter å kjøre fordi
  det tror Kontrollsenter fortsatt er der. Begge ryddes ved oppstart.
* Diskvakt: skriver Kontrollsenter (eller programmer det har startet) mer enn 500 MB på ett minutt, logges det hvilke
  programmer som kjører – så vi finner synderen.
"""
import os
import sys
import threading
import time


def reap_zombies():
    """Fjern avsluttede barneprosesser fra forrige utgave (før nye startes – derfor trygt)."""
    if sys.platform == "win32":
        return 0
    n = 0
    while True:
        try:
            pid, _st = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            break
        if pid == 0:
            break
        n += 1
    return n


def kill_stale(script="webcam_overlay.py"):
    """Stopp kopier av et hjelpeprogram som hører til dette prosessnummeret (startet av forrige utgave)."""
    if sys.platform == "win32":
        return 0
    me, n = str(os.getpid()), 0
    for d in os.listdir("/proc"):
        if not d.isdigit() or d == me:
            continue
        try:
            cmd = open(f"/proc/{d}/cmdline", "rb").read().split(b"\0")
        except OSError:
            continue
        args = [c.decode(errors="ignore") for c in cmd]
        if any(a.endswith(script) for a in args) and "--forelder" in args and \
                args[args.index("--forelder") + 1:args.index("--forelder") + 2] == [me]:
            try:
                os.kill(int(d), 15)
                n += 1
            except OSError:
                pass
    return n


def _children():
    out = []
    me = str(os.getpid())
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            st = open(f"/proc/{d}/stat").read()
            ppid = st.rsplit(")", 1)[1].split()[1]
            if ppid == me:
                cmd = open(f"/proc/{d}/cmdline", "rb").read().replace(b"\0", b" ").decode(errors="ignore")[:120]
                out.append(f"{d}: {cmd or '(zombie)'}")
        except (OSError, IndexError):
            continue
    return out


def _disk_watch():
    import applog
    last, warned = None, 0
    while True:
        try:
            w = int(next(ln.split()[1] for ln in open("/proc/self/io") if ln.startswith("write_bytes")))
        except (OSError, StopIteration, ValueError):
            return
        if last is not None and w - last > 500 * 2 ** 20 and time.time() - warned > 600:
            warned = time.time()
            applog.log.warning("Diskvakt: %.0f MB skrevet siste minutt. Barneprosesser: %s", (w - last) / 2 ** 20,
                               "; ".join(_children()) or "ingen")
        last = w
        time.sleep(60)


def start(win=None):
    """Kalles én gang ved oppstart."""
    if sys.platform == "win32":
        return
    try:
        z, k = reap_zombies(), kill_stale()
        if z or k:
            import applog
            applog.log.info("Ryddet etter forrige utgave: %d avsluttede prosesser, %d gamle overlay", z, k)
    except Exception:  # noqa: BLE001
        pass
    threading.Thread(target=_disk_watch, daemon=True, name="diskvakt").start()
