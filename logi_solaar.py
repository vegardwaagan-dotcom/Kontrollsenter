"""Hjelpeskript som kjøres INNE i Solaar-Flatpaken (bruker Solaars eget bibliotek).

  python3 - get <enhetsnavn>                      -> JSON med innstillinger
  python3 - set <enhetsnavn> <innstilling> <verdi> -> skriver én innstilling

Brukes av Systemmonitor for Logitech-enheter som ratbagd ikke støtter
(f.eks. trådløse PRO X2 SUPERSTRIKE).
"""
import json
import sys

from solaar import configuration  # noqa: F401
from solaar.cli import _find_device, _receivers_and_devices

WANTED = ("onboard_profiles", "report_rate_extended", "report_rate", "dpi_extended", "dpi",
          "analog-button-tuning_")


def find(name):
    recs = list(_receivers_and_devices())
    for dev in _find_device(recs, name.lower()):
        return dev
    sys.exit(json.dumps({"error": f"fant ikke {name}"}))


def describe(s):
    v = s.read()
    out = {"label": str(s.label), "value": None, "choices": None, "min": None, "max": None}
    if isinstance(v, dict) or hasattr(v, "items"):
        out["value"] = {str(k): (str(x) if not isinstance(x, int) else int(x)) for k, x in dict(v).items()}
    ch = getattr(s, "choices", None)
    if ch and not isinstance(out["value"], dict):
        out["choices"] = [str(c) for c in ch]
        if v is not None:
            out["value"] = next((str(c) for c in ch if int(c) == int(v)), str(v))
    elif v is not None and not isinstance(out["value"], dict):
        out["value"] = int(v)
    val = getattr(s, "_validator", None)
    for a in ("min_value", "max_value"):
        if val is not None and hasattr(val, a):
            out["min" if a.startswith("min") else "max"] = int(getattr(val, a))
    return out


def list_devices():
    out = []
    for r in _receivers_and_devices():
        try:
            if r.isDevice:
                r.ping()
                devs = [r]
            else:
                devs = [d for d in r if d]
            for d in devs:
                kind = str(d.kind).lower()
                if kind not in ("mouse", "keyboard"):
                    continue
                out.append({"name": d.name, "codename": d.codename, "kind": kind,
                            "pid": (getattr(d, "product_id", None) or "").lower(),
                            "wpid": (d.wpid or "").lower(), "online": bool(d.online)})
        except Exception:  # noqa: BLE001
            continue
    print(json.dumps(out))


def main():
    if sys.argv[1] == "list":
        return list_devices()
    op, name = sys.argv[1], sys.argv[2]
    dev = find(name)
    sets = {s.name: s for s in (dev.settings or [])}
    if op == "get":
        res = {"name": dev.name, "battery": None, "settings": {}}
        try:
            b = dev.battery()
            res["battery"] = getattr(b, "level", None)
        except Exception:
            pass
        for n, s in sets.items():
            if n.startswith(WANTED):
                try:
                    res["settings"][n] = describe(s)
                except Exception as e:  # noqa: BLE001
                    res["settings"][n] = {"error": str(e)}
        print(json.dumps(res))
    elif op == "set":
        key, raw = sys.argv[3], sys.argv[4]
        s = sets.get(key)
        if s is None:
            sys.exit(json.dumps({"error": f"ukjent innstilling {key}"}))
        cur = s.read()
        if key.startswith("dpi_extended"):
            val = dict(cur)
            dpi = int(raw)
            for k in list(val):
                if int(k) in (0, 1):            # 0 = X, 1 = Y (2 = LOD)
                    val[k] = dpi
            new = type(cur)(val) if not isinstance(cur, dict) else val
        elif getattr(s, "choices", None):
            new = next((c for c in s.choices if str(c) == raw), None)
            if new is None:
                sys.exit(json.dumps({"error": f"ugyldig verdi {raw}"}))
        else:
            new = int(raw)
        r = s.write(new, save=True)
        print(json.dumps({"ok": r is not None, "value": describe(s)["value"]}))


main()
