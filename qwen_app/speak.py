"""Speaker icon backend (17.11.2026): the text of one chat response as speech, Speechify voice Beatrice.

Marko: "speaker icon at end of each chat response to play audio from chat text using speechify key beatrice voice".
Rendered to a file FIRST (his rule: no streamed speech, no sound drops), cached per text, then the window plays the file.
English -> `langsay --out FILE en "..."` (Speechify beatrice_32, keys from ~/Downloads/API/speechify_api.txt, found by
langsay, never printed). Croatian -> `langsay --out FILE hr "..."` (his Gabrijela rule). Markdown and code blocks are
stripped before speaking. POST /api/speak/render {text} -> {file, lang, cached, chars}; the file is also GET /api/speak/file?name=.
Cost: Speechify bills per character (spend ask "Claude" "Speechify" ...); a repeat click is cached = $0. Capped at 4000 chars.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

from flask import jsonify, request, send_file

DIR = Path.home() / ".groq" / "speak"
MAX_CHARS = 4000


def clean(text: str) -> str:
    t = re.sub(r"```.*?```", " ", text, flags=re.S)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"^\s*\|?\s*:?-{3,}[\s|:-]*$", " ", t, flags=re.M)
    t = t.replace("|", ", ")
    t = re.sub(r"^\s{0,3}#{1,6}\s+", "", t, flags=re.M)
    t = re.sub(r"^\s*[-*+]\s+", "", t, flags=re.M)
    t = re.sub(r"^\s*>\s?", "", t, flags=re.M)
    t = re.sub(r"[*_~]{1,3}", "", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{2,}", ". ", t).replace("\n", " ")
    t = re.sub(r"\.\s*\.", ".", t)
    return t.strip()[:MAX_CHARS]


def lang_of(t: str) -> str:
    low = t.lower()
    if re.search(r"[čćšžđ]", low):
        return "hr"
    words = set(re.findall(r"[a-zA-Z]+", low))
    hr = {"je", "se", "da", "ne", "sam", "što", "koji", "ali", "kako", "nije", "ovo", "sve", "za", "na", "ću", "bok", "hvala"}
    en = {"the", "is", "and", "to", "of", "that", "you", "it", "this", "for", "with", "are", "was"}
    return "hr" if len(words & hr) > len(words & en) + 1 else "en"


def register(app):
    @app.post("/api/speak/render")
    def speak_render():
        text = clean((request.get_json(silent=True) or {}).get("text") or "")
        if len(text) < 2:
            return jsonify({"error": "nothing to speak"}), 400
        lang = lang_of(text)
        name = hashlib.sha1((lang + "|" + text).encode()).hexdigest()[:20] + ".mp3"
        DIR.mkdir(parents=True, exist_ok=True)
        f = DIR / name
        cached = f.exists() and f.stat().st_size > 1000
        if not cached:
            r = subprocess.run([str(Path.home() / ".local" / "bin" / "langsay"), "--out", str(f), lang, text], capture_output=True, text=True, timeout=300)
            if not f.exists() or f.stat().st_size < 1000:
                return jsonify({"error": "render failed: " + (r.stderr or r.stdout)[-200:]}), 500
        return jsonify({"file": str(f), "name": name, "lang": lang, "cached": cached, "chars": len(text)})

    @app.get("/api/speak/file")
    def speak_file():
        name = re.sub(r"[^a-f0-9.mp3]", "", request.args.get("name", ""))
        f = DIR / name
        return send_file(str(f), mimetype="audio/mpeg") if f.exists() else (jsonify({"error": "no file"}), 404)
