"""Router mode (15.11.2026): Queen reads the house router state and, only on an explicit confirm, switches it.
Local chat commands, no model, $0. Tool: `routermode` on the PATH (~/Developer/ROUTER_MODE)."""
import json, re, shutil, subprocess, sys
from pathlib import Path

RM = shutil.which("routermode") or str(Path.home() / ".local/bin/routermode")


def _run(args, timeout=60):
    return subprocess.run([RM, *args], capture_output=True, text=True, timeout=timeout)


def state():
    p = _run(["state", "--json"], 20)
    return json.loads(p.stdout)


def sentence(s):
    if not s.get("ok", True) and s.get("error"):
        return f"I cannot read the router state: {s['error']}"
    via = s.get("internet_via")
    if via == "SIM":
        head = "The house is on the SIM backup"
    elif via == "cable":
        head = "The house is on the phone's cable internet"
    else:
        head = "The house has no internet right now"
    parts = [head]
    if s.get("sim_today_mb") is not None:
        parts.append(f"{s['sim_today_mb']:.0f} MB of SIM today")
    out = "; ".join(parts)
    ph = "the phone is home" if s.get("phone_home") else "the phone is not home"
    teth = "Ethernet tethering is " + ("on" if (s.get("phone") or {}).get("tethering") else "off")
    out += f"; {ph} but {teth}." if s.get("phone_home") and "off" in teth else f"; {ph}; {teth}."
    out += f" Router mode is {s.get('mode')}."
    if s.get("warning"):
        out += f" Warning: {s['warning']}"
    return out


def chat_router_command(text):
    t = (text or "").strip()
    low = t.lower().strip(" .!?")
    if len(t) > 120:
        return None
    try:
        m = re.match(r"^yes,?\s+use\s+(sim|phone)(\s+only)?$", low)
        if m:
            which = m.group(1)
            p = _run(["set", which, "--yes"], 180)
            tail = (p.stdout + p.stderr).strip()[-300:]
            return f"Router set to {which.upper()} mode. It reboots, the house is offline 1-2 minutes. {tail}"
        m = re.match(r"^(please )?(use|switch to|change to)\s+(the\s+)?(phone|sim)(\s+only)?(\s+internet)?$", low)
        if m:
            which = m.group(4)
            return (f"This reboots the router, the house is offline 1-2 minutes. "
                    f"Say 'yes, use {which}' to go on.")
        if re.match(r"^(router|router status|router mode|router state|which internet|what internet|which internet are we on|"
                    r"what is the router (doing|on)|internet status)$", low):
            return sentence(state())
    except Exception as e:
        return f"The router skill failed: {type(e).__name__}: {e}"
    return None
