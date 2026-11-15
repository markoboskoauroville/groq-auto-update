"""Speak on a phone (15.11.2026): local chat commands, $0, no model.
"say on the pixel <text>" / "speak on the pixel <text>" / "send to the pixel <text>" run `phonesay pixel en "<text>"`
(the phone's Voice Engine renders and speaks it). "say on the nothing ..." does the same for the Nothing Phone.
"phone status" runs `phonesay status`. The hand is ~/.local/bin/phonesay (argv list, no shell)."""
import os, re, subprocess, sys

PHONESAY = os.path.expanduser("~/.local/bin/phonesay")
PHONES = {"pixel": "pixel", "nothing": "nothing"}


def _run(args, timeout=30):
    env = dict(os.environ); env["PATH"] = os.path.expanduser("~/.local/bin") + ":" + env.get("PATH", "")
    r = subprocess.run([PHONESAY] + args, capture_output=True, text=True, timeout=timeout, env=env)
    out = (r.stdout + r.stderr).strip()
    return out or f"phonesay {' '.join(args[:1])}: exit {r.returncode}"


def chat_phone_say_command(text):
    """None when the sentence is not about speaking on a phone."""
    if sys.platform != "darwin":
        return None
    t = (text or "").strip(); low = t.lower()
    if re.fullmatch(r"\s*phone status\s*[.!?]*", low):
        try:
            return _run(["status"], timeout=15)
        except Exception as e:
            return f"The phone voice did not answer: {e}"
    m = re.match(r"\s*(?:say|speak|send)(?: it)? (?:on|to) (?:the )?(pixel|nothing)\b[:,]?\s*(.+)$", t, re.I | re.S)
    if not m:
        return None
    who, msg = PHONES[m.group(1).lower()], m.group(2).strip().strip('"').strip()
    if not msg or len(msg) > 600:
        return "Say what the phone should speak, up to 600 characters."
    try:
        return "Spoken on the " + who + ": " + _run([who, "en", msg], timeout=60)
    except Exception as e:
        return f"The phone voice did not answer: {e}"
