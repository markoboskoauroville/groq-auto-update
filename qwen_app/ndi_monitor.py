"""NDI Video Monitor source switch (15.11.2026). Marko: "teach our queen and our macro recorder to change these sources".

    GET  /api/ndi/sources              -> {ok, sources: ["MACHINE (Name)", ...]}
    POST /api/ndi/select {source}      -> {ok, answer}   first source containing the text (case-insensitive)
Both call the macro skills `ndi-monitor-list` / `ndi-monitor-source` (MACRO_SKILLS: `macroskill run ndi-monitor-source --arg
source="..."`, the tool is `ndimon`, an Accessibility menu press, no keys, no mouse). Chat (local, no model, $0):
"show Meditation Room in the NDI monitor", "switch NDI source to Pixel 7 Camera", "which NDI sources are there".
"""
import re
import shutil
import subprocess
import sys

from flask import jsonify, request


def _ndimon(*args, timeout=60):
    exe = shutil.which("ndimon") or __import__("os").path.expanduser("~/.local/bin/ndimon")
    r = subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout + r.stderr).strip()


def sources():
    code, out = _ndimon("list")
    return [l for l in out.splitlines() if l.strip()] if code == 0 else []


def select(text):
    return _ndimon("select", text)[1]


def register(app):
    @app.get("/api/ndi/sources")
    def ndi_sources():
        try:
            return jsonify(ok=True, sources=sources())
        except Exception as e:
            return jsonify(ok=False, error=str(e)), 500

    @app.post("/api/ndi/select")
    def ndi_select():
        d = request.get_json(silent=True) or {}
        s = (d.get("source") or "").strip()
        if not s:
            return jsonify(ok=False, error="source is required"), 400
        try:
            return jsonify(ok=True, answer=select(s))
        except Exception as e:
            return jsonify(ok=False, error=str(e)), 500


def chat_ndi_command(text):
    """Local chat command; None when the sentence is not about the NDI monitor."""
    if sys.platform != "darwin":
        return None
    t = (text or "").strip()
    low = t.lower()
    if len(t) > 200 or "ndi" not in low:
        return None
    try:
        if re.search(r"\b(which|what|list|show me|available)\b.*\bndi\b.*\bsources?\b|\bndi sources\b.*(are there|available|list)|\blist (the )?ndi\b", low) \
                and not re.search(r"\bin the ndi\b|\bto\b", low):
            s = sources()
            return ("NDI sources on the network:\n" + "\n".join("- " + x for x in s)) if s else "I see no NDI sources on the network."
        m = (re.search(r"\b(?:show|display|put|open|select|pick|choose)\s+(?:the\s+)?(.+?)\s+(?:in|on|into)\s+(?:the\s+)?ndi(?: video)?(?: monitor)?\b", t, re.I)
             or re.search(r"\b(?:switch|change|set)\s+(?:the\s+)?ndi(?: video)?(?: monitor)?(?: source)?\s+(?:to|on)\s+(.+?)[.!?]*$", t, re.I)
             or re.search(r"\bndi(?: video)?(?: monitor)?\s+source\s+(?:to\s+)?(.+?)[.!?]*$", t, re.I))
        if m:
            name = m.group(1).strip(" \"'.!?")
            name = re.sub(r"^(the\s+)?source\s+", "", name, flags=re.I)
            if name:
                return select(name) + "\nNDI Video Monitor does the picture; ask me for a screenshot to see it."
    except Exception as e:
        return f"I could not switch the NDI source: {e}"
    return None
