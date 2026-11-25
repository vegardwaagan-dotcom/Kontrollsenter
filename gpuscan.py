"""NVIDIA: GPU-belastning som også oppdager regnefeil – og «trygg overklokking» som finner det høyeste stabile nivået.

Belastningen er en liten CUDA-kjerne (via driverens egen libcuda/nvcuda – ingenting ekstra å installere). Hver kjøring
regner nøyaktig det samme, så svaret skal være likt bit for bit hver gang. Blir det ulikt – eller driveren melder feil
(Xid) – er klokken for høy. Skanneren går opp litt om gangen, tester hvert steg, og ender et trygt stykke under
grensen den fant. Krasjer hele PC-en underveis, huskes steget, og neste skann stopper før det.
"""
import ctypes
import hashlib
import json
import os
import subprocess
import sys
import threading
import time

IS_WIN = sys.platform == "win32"
STATE = os.path.expanduser("~/.config/systemmonitor/gpuskann.json")

PTX = rb"""
.version 7.0
.target sm_52
.address_size 64
.visible .entry burn(.param .u64 out, .param .u32 iters, .param .u32 n)
{
  .reg .pred p;
  .reg .b32 r<10>;
  .reg .f32 f<8>;
  .reg .b64 rd<6>;
  ld.param.u64 rd1, [out];
  ld.param.u32 r1, [iters];
  ld.param.u32 r9, [n];
  mov.u32 r2, %ctaid.x;
  mov.u32 r3, %ntid.x;
  mov.u32 r4, %tid.x;
  mad.lo.s32 r5, r2, r3, r4;
  setp.ge.u32 p, r5, r9;
  @p bra DONE;
  cvt.rn.f32.u32 f1, r5;
  mul.f32 f1, f1, 0f3A83126F;
  mov.f32 f4, f1;
  mov.f32 f2, 0f3F7FFFAC;
  mov.f32 f3, 0f3A83126F;
  mov.u32 r6, 0;
LOOP:
  fma.rn.f32 f1, f1, f2, f3;
  fma.rn.f32 f4, f4, f2, f1;
  fma.rn.f32 f1, f1, f2, f4;
  fma.rn.f32 f4, f4, f2, f3;
  add.u32 r6, r6, 1;
  setp.lt.u32 p, r6, r1;
  @p bra LOOP;
  add.f32 f1, f1, f4;
  cvta.to.global.u64 rd2, rd1;
  mul.wide.u32 rd3, r5, 4;
  add.u64 rd4, rd2, rd3;
  st.global.f32 [rd4], f1;
DONE:
  ret;
}
"""


class CudaError(RuntimeError):
    pass


class Burner:
    """Én CUDA-kontekst på kortet: run() regner og gir et fingeravtrykk av svaret; mem() flytter minne og sjekker."""

    def __init__(self, idx=0, mb=512):
        os.environ.setdefault("CUDA_DEVICE_ORDER", "PCI_BUS_ID")      # samme nummer som nvidia-smi
        self.cu = ctypes.CDLL("nvcuda.dll" if IS_WIN else "libcuda.so.1")
        self.n = mb * 1024 * 1024 // 4
        self._c(self.cu.cuInit(0), "init")
        dev = ctypes.c_int()
        self._c(self.cu.cuDeviceGet(ctypes.byref(dev), int(idx)), "kort")
        self.ctx = ctypes.c_void_p()
        self._c(self.cu.cuCtxCreate_v2(ctypes.byref(self.ctx), 0, dev), "kontekst")
        mod, self.fn = ctypes.c_void_p(), ctypes.c_void_p()
        self._c(self.cu.cuModuleLoadData(ctypes.byref(mod), ctypes.c_char_p(PTX + b"\0")), "kjerne")
        self._c(self.cu.cuModuleGetFunction(ctypes.byref(self.fn), mod, b"burn"), "kjerne")
        self.a, self.b = ctypes.c_uint64(), ctypes.c_uint64()
        self._c(self.cu.cuMemAlloc_v2(ctypes.byref(self.a), ctypes.c_size_t(self.n * 4)), "minne")
        self._c(self.cu.cuMemAlloc_v2(ctypes.byref(self.b), ctypes.c_size_t(self.n * 4)), "minne")
        self.host = ctypes.create_string_buffer(self.n * 4)

    def _c(self, rc, what):
        if rc:
            raise CudaError(f"CUDA-feil {rc} ({what})")

    def run(self, iters=300):
        """Regn (≈0,1–0,3 s per gang på et moderne kort) – returnerer fingeravtrykket av svaret."""
        it, n = ctypes.c_uint32(iters), ctypes.c_uint32(self.n)
        args = (ctypes.c_void_p * 3)(ctypes.addressof(self.a), ctypes.addressof(it), ctypes.addressof(n))
        self._c(self.cu.cuLaunchKernel(self.fn, (self.n + 255) // 256, 1, 1, 256, 1, 1, 0, None, args, None), "kjør")
        self._c(self.cu.cuCtxSynchronize(), "kjør")
        return self._digest(self.a)

    def mem(self, rounds=20):
        """Kopier svaret frem og tilbake i skjermkortminnet – skal fortsatt være likt."""
        for _ in range(rounds):
            self._c(self.cu.cuMemcpyDtoD_v2(self.b, self.a, ctypes.c_size_t(self.n * 4)), "minne")
            self._c(self.cu.cuMemcpyDtoD_v2(self.a, self.b, ctypes.c_size_t(self.n * 4)), "minne")
        self._c(self.cu.cuCtxSynchronize(), "minne")
        return self._digest(self.b)

    def _digest(self, ptr):
        self._c(self.cu.cuMemcpyDtoH_v2(self.host, ptr, ctypes.c_size_t(self.n * 4)), "les")
        return hashlib.blake2b(self.host.raw, digest_size=16).hexdigest()

    def close(self):
        try:
            self.cu.cuMemFree_v2(self.a)
            self.cu.cuMemFree_v2(self.b)
            self.cu.cuCtxDestroy_v2(self.ctx)
        except Exception:  # noqa: BLE001
            pass


def available():
    try:
        b = Burner(mb=8)
        b.close()
        return True
    except Exception:  # noqa: BLE001
        return False


def xid_since(t0):
    """Feilmeldinger fra NVIDIA-driveren (Xid) siden t0 – tegn på ustabil klokke."""
    if IS_WIN:
        return []
    try:
        out = subprocess.run(["journalctl", "-k", "-q", "--no-pager", "--since", f"@{int(t0)}", "--grep", "NVRM: Xid"],
                             capture_output=True, text=True, timeout=10).stdout
        return [ln for ln in out.splitlines() if "Xid" in ln]
    except Exception:  # noqa: BLE001
        return []


def test(burner, seconds, ref, memory=False):
    """Belast i N sekunder. (ok, grunn)"""
    t0, end = time.time(), time.time() + seconds
    while time.time() < end:
        if SCAN["stop"]:
            return True, "stoppet"
        try:
            if burner.run() != ref["calc"]:
                return False, "regnefeil"
            if memory and burner.mem() != ref["calc"]:
                return False, "minnefeil"
        except CudaError as e:
            return False, str(e)
    x = xid_since(t0)
    return (False, "driverfeil (Xid)") if x else (True, "")


# --------------------------------------------------------------------------
# Skanneren
# --------------------------------------------------------------------------
SCAN = {"running": False, "stop": False, "log": [], "result": None, "step": ""}


def load_state():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(s):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=1)
        f.flush()
        os.fsync(f.fileno())                     # må ligge på disken hvis PC-en krasjer i neste steg


def _log(txt):
    SCAN["log"].append(txt)
    SCAN["step"] = txt


def scan(gid, idx, seconds=20, progress=None):
    """Finn høyeste stabile GPU- og minne-offset. Returnerer {"core", "mem", "log"}."""
    import gpu as G
    if SCAN["running"]:
        raise RuntimeError("skanningen kjører allerede")
    SCAN.update(running=True, stop=False, log=[], result=None, step="")
    st = load_state()
    crashed = st.get("testing")                  # PC-en krasjet under forrige skann
    lim = st.get("limits", {})
    if crashed:
        lim[crashed["what"]] = min(lim.get(crashed["what"], 99999), crashed["value"])
    e = G.nv_extra(idx)
    clo, chi = e.get("core_range", (0, 300))
    mlo, mhi = e.get("mem_range", (0, 2000))
    core_steps = [v for v in range(60, min(chi, 360) + 1, 30) if v < lim.get("core", 99999)]
    mem_steps = [v for v in range(250, min(mhi, 3000) + 1, 250) if v < lim.get("mem", 99999)]
    total = len(core_steps) + len(mem_steps) + 1
    done = [0]
    good = {"core": 0, "mem": 0}
    burner = None

    def tick(txt):
        done[0] += 1
        _log(txt)
        if progress:
            progress(done[0], total, txt)

    def set_oc(c, m):
        G.run("nv-oc", idx, c, m)

    def fresh():
        nonlocal burner
        if burner:
            burner.close()
        burner = Burner(idx)
        return burner
    try:
        if crashed:
            _log(f"Forrige skann krasjet ved {crashed['what']} +{crashed['value']} – stopper før det nå")
        set_oc(0, 0)
        b = fresh()
        ref = {"calc": b.run()}
        if b.run() != ref["calc"]:
            raise RuntimeError("kortet regner ikke likt selv uten overklokking – sjekk varme og driver")
        tick("Fasit regnet ut ved standard klokke ✓")
        for what, steps in (("core", core_steps), ("mem", mem_steps)):
            for v in steps:
                if SCAN["stop"]:
                    break
                c, m = (v, 0) if what == "core" else (good["core"], v)
                _save_state({**st, "limits": lim, "testing": {"what": what, "value": v}})
                try:
                    set_oc(c, m)
                    ok, why = test(b, seconds, ref, memory=(what == "mem"))
                except Exception as ex:  # noqa: BLE001
                    ok, why = False, str(ex)
                name = "GPU" if what == "core" else "Minne"
                if ok:
                    good[what] = v
                    tick(f"{name} +{v} MHz ✓")
                    continue
                tick(f"{name} +{v} MHz ✗ ({why})")
                lim[what] = v
                set_oc(good["core"] if what == "mem" else good["core"], 0 if what == "mem" else 0)
                b = fresh()                      # driveren kan ha nullstilt konteksten
                break
        # trygghetsmargin: ett steg under det som holdt
        core = max(0, good["core"] - 30) if good["core"] else 0
        mem = max(0, good["mem"] - 250) if good["mem"] else 0
        set_oc(core, mem)
        if not SCAN["stop"]:
            ok, why = test(b, seconds, ref, memory=True)
            if not ok:                            # kombinasjonen holdt ikke: ta et steg ned til
                core, mem = max(0, core - 30), max(0, mem - 250)
                set_oc(core, mem)
        G.save_cmd(gid, "oc", ["nv-oc", idx, core, mem] if core or mem else None)
        st = {"limits": lim, "result": {"core": core, "mem": mem, "t": time.time()}}
        _save_state(st)
        res = {"core": core, "mem": mem, "log": SCAN["log"], "stopped": SCAN["stop"]}
        SCAN["result"] = res
        _log(f"Ferdig: GPU +{core} MHz, minne +{mem} MHz (med trygghetsmargin)")
        return res
    except Exception:
        try:
            set_oc(0, 0)
        except Exception:  # noqa: BLE001
            pass
        st.pop("testing", None)
        _save_state({**st, "limits": lim})
        raise
    finally:
        if burner:
            burner.close()
        SCAN["running"] = False


def scan_async(gid, idx, done=None):
    def work():
        try:
            r = scan(gid, idx)
        except Exception as e:  # noqa: BLE001
            r = {"error": str(e)}
            SCAN["result"] = r
            _log("Avbrutt: " + str(e))
        if done:
            done(r)
    threading.Thread(target=work, daemon=True).start()


def last_result():
    return load_state().get("result")


# --------------------------------------------------------------------------
# Ferdige profiler (spillprofiler og knapper): strømgrense i % av standard + offset
# --------------------------------------------------------------------------
PRESETS = [("", "Ikke endre", None, None, None),
           ("effektiv", "Effektiv (samme FPS, mindre strøm)", 80, 150, 500),
           ("stille", "Stille (kjølig og lavt)", 65, 0, 0),
           ("mild", "Mild overklokking", 100, 100, 500),
           ("skann", "Skannet maks (trygg overklokking)", 100, "scan", "scan"),
           ("standard", "Standard (NVIDIA)", 100, 0, 0)]


def preset_values(key):
    """(strøm-%, kjerne, minne) for en profil – «skann» bruker resultatet fra skanneren."""
    p = next((x for x in PRESETS if x[0] == key), None)
    if not p or p[2] is None:
        return None
    r = last_result() or {}
    core = r.get("core", 0) if p[3] == "scan" else p[3]
    mem = r.get("mem", 0) if p[4] == "scan" else p[4]
    if key == "effektiv" and r:                  # aldri mer enn det skanneren fant stabilt
        core, mem = min(core, r.get("core", core)), min(mem, r.get("mem", mem))
    return p[2], core, mem


def apply_preset(key):
    """Bruk en profil på NVIDIA-kortet. Returnerer det som trengs for å sette alt tilbake."""
    import gamegpu
    import gpu as G
    vals = preset_values(key)
    if vals is None:
        return None
    nv = next((g for g in G.detect() if g["vendor"] == "nvidia" and g.get("idx") is not None), None)
    if not nv:
        return None
    e = G.nv_extra(nv["idx"])
    back = {"idx": nv["idx"], "core": e.get("core", 0), "mem": e.get("mem", 0)}
    pct, core, mem = vals
    back["pl"] = gamegpu.pl_apply(pct) if pct and pct != 100 else gamegpu.pl_apply(100)
    G.run("nv-oc", nv["idx"], core, mem)
    return back


def restore_preset(back):
    import gamegpu
    import gpu as G
    if not back:
        return
    G.run("nv-oc", back["idx"], back.get("core", 0), back.get("mem", 0))
    if back.get("pl"):
        gamegpu.pl_restore(back["pl"])
