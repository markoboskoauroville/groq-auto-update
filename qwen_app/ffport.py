"""Which port Firefox's remote control (BiDi) listens on: 9223 or 9222, whichever Firefox itself holds.
Chrome (cdp_broker) often holds 9222, so the owner of the port is checked before anything talks to it."""
import os
import subprocess


def _owner(port):
    try:
        r = subprocess.run(["lsof", "-nP", "-iTCP:%d" % port, "-sTCP:LISTEN", "-Fc"], capture_output=True, text=True, timeout=5)
        names = [l[1:] for l in r.stdout.splitlines() if l.startswith("c")]
        return names[0].lower() if names else ""
    except Exception:
        return ""


def firefox_port(default="9223"):
    """The port Firefox holds; FIREFOXCTL_PORT first if Firefox holds it; else the default."""
    cands = [os.environ.get("FIREFOXCTL_PORT"), "9223", "9222"]
    for p in [c for c in cands if c]:
        if "firefox" in _owner(int(p)):
            return p
    return default
