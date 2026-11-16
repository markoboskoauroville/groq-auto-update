"""pause_state.py: PAUSE / RESUME / STATUS for every hand of Queen (Marko, 16.11.2026: "All our tools need to be paused at
the same time and need to have this kind of API calls to be stopped.").

One shared truth: ~/.groq/pause.json {"paused": bool, "since": epoch|null}. The Swift app (8765) and this Python backend
(8766) both read and write it, so a pause on either side reaches the other and survives a restart.

What paused means in Python:
  * subprocess (macro, firefoxctl, adb, osascript ...) and outgoing urllib calls wait at a checkpoint BEFORE they start
    (running hands stop between steps and go on at resume);
  * an outgoing HTTP call already in flight is abandoned at once (PausedError, answered as "paused", never as an error);
  * a Groq/Claude call through an SDK is gated at the route entry (app.py).
Loopback calls to Queen herself (8765/8766) are never held: pause/resume/status must always answer.
"""
import json
import os
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

STATE = Path(os.environ.get("QUEEN_PAUSE_FILE", str(Path.home() / ".groq" / "pause.json")))
_lock = threading.Lock()
_cache = {"mtime": None, "paused": False, "since": None}
_queued = 0
_installed = False


class PausedError(RuntimeError):
    """Raised in place of an outgoing call when Queen is paused. Report as 'paused', never as a failure."""


def _read():
    try:
        m = STATE.stat().st_mtime_ns
    except OSError:
        m = None
    with _lock:
        if m != _cache["mtime"]:
            _cache["mtime"] = m
            try:
                d = json.loads(STATE.read_text())
                _cache["paused"] = bool(d.get("paused"))
                _cache["since"] = d.get("since") if _cache["paused"] else None
            except Exception:
                _cache["paused"] = False
                _cache["since"] = None
        return _cache["paused"], _cache["since"]


def is_paused():
    return _read()[0]


def set_paused(on):
    cur, _since = _read()
    if bool(on) == cur:
        return status()
    data = {"paused": bool(on), "since": time.time() if on else None, "by": "queen-python"}
    tmp = STATE.with_suffix(".tmp")
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(data))
    os.replace(tmp, STATE)   # atomic: never a half-written pause file
    return status()


def status():
    p, since = _read()
    return {"paused": p, "since": since, "queued": _queued}


def checkpoint(max_wait=None):
    """Blocks while paused. Returns True when resumed, False when max_wait ran out still paused."""
    global _queued
    if not is_paused():
        return True
    t0 = time.time()
    with _lock:
        _queued += 1
    try:
        while is_paused():
            if max_wait is not None and time.time() - t0 > max_wait:
                return False
            time.sleep(0.25)
        return True
    finally:
        with _lock:
            _queued -= 1


def paused_reply(extra=None):
    d = dict(status())
    d.update({"ok": False, "paused": True, "error": "paused"})
    if extra:
        d.update(extra)
    return d


def chat_command(text):
    """'pause' / 'resume' / 'pause status' as a chat line: answered locally, $0. None = not a pause command."""
    t = " ".join((text or "").lower().replace("!", " ").replace(".", " ").split())
    if t in ("pause", "pause all", "pause everything", "pause queen", "pause tools", "pause all tools"):
        set_paused(True)
        return "Paused. No new model or tool calls start; running ones stop between steps. Say 'resume' to go on."
    if t in ("resume", "resume all", "resume everything", "resume queen", "unpause"):
        set_paused(False)
        return "Resumed. Queued work goes on."
    if t in ("pause status", "paused", "am i paused", "are you paused", "queen pause status"):
        s = status()
        if s["paused"]:
            return f"Paused since {time.strftime('%H:%M:%S', time.localtime(s['since']))}; {s['queued']} waiting."
        return "Not paused."
    return None


def _loopback_queen(url):
    u = url if isinstance(url, str) else getattr(url, "full_url", "")
    return u.startswith(("http://127.0.0.1:8765", "http://127.0.0.1:8766", "http://localhost:8765", "http://localhost:8766"))


def install():
    """Wraps subprocess starts and urllib.request.urlopen so every hand honours the pause. Idempotent."""
    global _installed
    if _installed:
        return
    _installed = True

    orig_popen_init = subprocess.Popen.__init__

    def popen_init(self, *a, **k):
        checkpoint()
        orig_popen_init(self, *a, **k)

    subprocess.Popen.__init__ = popen_init   # run, check_output, call, check_call all go through Popen

    orig_urlopen = urllib.request.urlopen

    def urlopen(url, *a, **k):
        if _loopback_queen(url):
            return orig_urlopen(url, *a, **k)
        checkpoint()
        box = {}

        def work():
            try:
                box["r"] = orig_urlopen(url, *a, **k)
            except BaseException as e:   # noqa: BLE001
                box["e"] = e

        th = threading.Thread(target=work, daemon=True)
        th.start()
        while th.is_alive():
            th.join(0.2)
            if is_paused():
                # in flight when the pause came: abandon it. The worker finishes alone and its answer is dropped.
                def _drop(th=th, box=box):
                    th.join(120)
                    r = box.get("r")
                    try:
                        r and r.close()
                    except Exception:
                        pass
                threading.Thread(target=_drop, daemon=True).start()
                raise PausedError("paused")
        if "e" in box:
            raise box["e"]
        return box["r"]

    urllib.request.urlopen = urlopen
