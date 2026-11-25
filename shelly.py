"""Ekte strømmåling fra en Shelly-smartplugg bak PC-en (73).

Shelly har et åpent, lokalt grensesnitt (ingen sky, ingen konto):
  Gen2/Gen3 (Plus Plug S m.fl.): http://<ip>/rpc/Switch.GetStatus?id=0  → «apower»
  Gen1 (Plug S):                  http://<ip>/status                     → «meters[0].power»
Målingen hentes i en bakgrunnstråd hvert 2. sekund, og brukes i stedet for beregnet strøm når den virker.
"""
import json
import threading
import time
import urllib.request

_STATE = {"ip": None, "w": None, "t": 0, "err": None, "run": False}


def ip():
    try:
        import power
        return (power.load().get("shelly") or "").strip() or None
    except Exception:  # noqa: BLE001
        return None


def read_once(addr, timeout=2.5):
    """Watt fra pluggen (kaster feil hvis den ikke svarer)."""
    last = "ingen watt i svaret"
    for url, pick in ((f"http://{addr}/rpc/Switch.GetStatus?id=0", lambda d: d.get("apower")),
                      (f"http://{addr}/status", lambda d: (d.get("meters") or [{}])[0].get("power"))):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                v = pick(json.load(r))
            if v is not None:
                return float(v)
        except Exception as e:  # noqa: BLE001
            last = e
    raise RuntimeError(f"Shelly på {addr} svarer ikke ({last})")


def _loop():
    while True:
        addr = ip()
        if not addr:
            _STATE.update(w=None, err=None)
            time.sleep(10)
            continue
        try:
            _STATE.update(w=read_once(addr), t=time.time(), err=None, ip=addr)
        except Exception as e:  # noqa: BLE001
            _STATE.update(w=None, err=str(e))
        time.sleep(2)


def watts():
    """Siste måling (None = ikke satt opp eller svarer ikke)."""
    if not _STATE["run"]:
        _STATE["run"] = True
        threading.Thread(target=_loop, daemon=True, name="shelly").start()
    if _STATE["w"] is not None and time.time() - _STATE["t"] < 10:
        return _STATE["w"]
    return None


