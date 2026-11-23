#!/usr/bin/env python3
"""ks – styr Kontrollsenter fra terminalen (brukes av AI-assistentene). Se «ks hjelp»."""
import json
import os
import sys
import urllib.error
import urllib.request

PORT = int(os.environ.get("KS_PORT", "27100"))


def main(argv):
    cmd, args = (argv[0] if argv else "hjelp"), argv[1:]
    body = json.dumps({"cmd": cmd, "args": args}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/api/local/ai", data=body, method="POST",
                                 headers={"Content-Type": "application/json", "X-KS-Local": "1",
                                          "User-Agent": "ks"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        try:
            d = json.load(e)
        except ValueError:
            d = {"error": str(e)}
    except OSError:
        print("Kontrollsenter kjører ikke (eller er for gammelt) – start Kontrollsenter og prøv igjen.")
        return 2
    if "error" in d:
        print("Feil:", d["error"])
        return 1
    r = d.get("result")
    print(r if isinstance(r, str) else json.dumps(r, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
