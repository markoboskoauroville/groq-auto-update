"""Second Take (MPA Lessons Analyzer (Mantra) v23+, 15.11.2026): local chat commands, $0, no model.
The hand is the app's own loopback API http://127.0.0.1:8965 (port in ~/.mantra/ports/mpa-lessons-analyzer).
Since v23 RECORD/STOP start and stop the Sony on its card through Imaging Edge Remote (sonycam)."""
import json, os, re, subprocess, sys, time, urllib.request

APP = "/Applications/MPA Lessons Analyzer (Mantra).app"


def _port():
    try:
        return int(open(os.path.expanduser("~/.mantra/ports/mpa-lessons-analyzer")).read().strip())
    except Exception:
        return 8965


def _call(method, path, body=None, timeout=20):
    req = urllib.request.Request(f"http://127.0.0.1:{_port()}{path}", method=method,
                                 data=json.dumps(body or {}).encode() if method == "POST" else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def _up():
    try:
        return _call("GET", "/status", timeout=3)
    except Exception:
        return None


def _status_line(s):
    shot = s.get("currentShot") or s.get("shot") or 0
    cam = s.get("cameraState", "?")
    line = f"Second Take v{s.get('version')}: shot {shot} of {s.get('shots')}, mode {s.get('mode')}, "
    line += f"camera {('REC ' + s.get('cameraCounter', '')) if cam == 'REC' else cam}"
    line += ", recording" if s.get("recording") else ", not recording"
    if s.get("message"): line += f". {s['message']}"
    return line


def chat_second_take_command(text):
    """None when the sentence is not about Second Take."""
    if sys.platform != "darwin":
        return None
    t = (text or "").strip(); low = t.lower()
    if len(t) > 120 or not re.search(r"\bsecond[- ]?take\b|\bnext (exercise|shot)\b", low):
        return None
    s = _up()
    if re.search(r"\bstatus\b|\bwhere am i\b|\bis .* recording\b", low):
        return _status_line(s) if s else "Second Take is not running."
    if s is None and re.search(r"\b(start|begin|open)\b", low):
        subprocess.run(["open", APP]); time.sleep(6); s = _up()
    if s is None:
        return "Second Take is not running. Say 'start second take' to open it."
    try:
        if re.search(r"\bnext (exercise|shot)\b", low):
            if s.get("recording"): return "A take is recording. Say 'stop second take' first."
            r = _call("POST", "/next")
            st = _up() or {}
            return f"Next: shot {r.get('current')}. {st.get('message', '')}".strip()
        if re.search(r"\b(stop|end|finish)\b", low):
            if s.get("recording"):
                _call("POST", "/record/stop")
                for _ in range(20):
                    time.sleep(1); st = _up() or {}
                    if not st.get("recording"): break
                return "Take stopped. " + _status_line(st)
            _call("POST", "/stop")
            return "Nothing was recording; the full-screen view is closed."
        if re.search(r"\b(start|begin|open)\b", low):
            r = _call("POST", "/shoot/start")
            _call("POST", "/live", {"shot": r.get("current")})
            time.sleep(3)
            return f"Second Take is ready on shot {r.get('current')}: the camera picture is full screen. Press RECORD (or say record) when you are ready. " + _status_line(_up() or {})
    except Exception as e:
        return f"Second Take did not answer: {e}"
    return None
