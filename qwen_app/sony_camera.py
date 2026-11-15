"""Sony camera through Imaging Edge Remote (15.11.2026): local chat commands, $0, no model.
The hand is MACRO_SKILLS tools/sonycam (macro skills sony-connect / sony-rec-start / sony-rec-stop / sony-status)."""
import re, subprocess, sys

SONYCAM = "sonycam"

def _run(arg):
    import os
    env = dict(os.environ); env["PATH"] = os.path.expanduser("~/.local/bin") + ":" + env.get("PATH", "")
    r = subprocess.run([SONYCAM, arg], capture_output=True, text=True, timeout=90, env=env)
    out = (r.stdout + r.stderr).strip()
    lines = [l for l in out.splitlines() if not l.startswith('{"label"') and l.strip() != "ok"]
    return "\n".join(lines) or f"sonycam {arg}: exit {r.returncode}"

def chat_sony_command(text):
    """None when the sentence is not about the Sony camera."""
    if sys.platform != "darwin":
        return None
    t = (text or "").strip(); low = t.lower()
    if len(t) > 120:
        return None
    cam = re.search(r"\b(camera|sony|alpha|a7|imaging edge)\b", low)
    if not cam and not re.search(r"\bopen (imaging edge )?remote\b|\bshow me on the benq\b", low):
        return None
    try:
        # 15.11.2026: "refresh/reconnect the camera" = connect (opens Imaging Edge's connect dialog), then status
        if cam and re.search(r"\b(refresh|reconnect)\b", low) and not re.search(r"\b(start|stop)\b", low):
            return _run("connect") + "\n" + _run("status")
        # v27: Remote maximized on the BenQ (not macOS full screen), for recording
        if re.search(r"\bimaging edge\b.*\b(big|full|benq)\b|\bcamera (full screen|fullscreen|big)\b|\bshow me on the benq\b|\bon the benq\b.*\b(camera|sony|imaging edge)\b", low):
            return _run("big")
        if re.search(r"\b(connect|open|pair)\b.*\b(camera|sony|imaging edge( remote)?|remote)\b|\bimaging edge remote\b", low) and not re.search(r"\b(start|stop)\b", low):
            return _run("connect")
        if re.search(r"\b(start|begin|press|hit)\b.*\b(camera|sony)?.*\b(record|recording|rec)\b|\brecord\b.*\b(on )?(the )?(camera|sony)\b", low) and re.search(r"camera|sony", low) and not re.search(r"\bstop\b", low):
            return _run("start")
        if re.search(r"\b(stop|end|finish)\b.*\b(record|recording|rec)\b", low) and re.search(r"camera|sony", low):
            return _run("stop")
        if re.search(r"\b(status|state|is it recording|connected)\b", low) and re.search(r"camera|sony", low):
            return _run("status")
    except Exception as e:
        return f"I could not reach the camera hand: {e}"
    return None
