"""Move one file on the Mac (17.11.2026). Marko asked Queen to move a LaunchAgent plist to the Desktop; she had no hand for it.

    POST /api/system/move {src, dst}  -> {ok, src, dst, src_gone, dst_exists, dst_size}
Rules: ~ is expanded; both paths must be inside the home folder; src must exist and be a file (a symlink is moved as the link,
never followed); if dst is an existing folder the file goes into it; an existing destination is never overwritten; nothing is deleted.
After shutil.move the answer is the READ-BACK of the real filesystem, never what was asked.
Chat (local, no model, $0): "move <src> to <dst>", "move <src> to desktop", Croatian "premjesti <src> na desktop / u <dst>".
"""
import os
import re
import shutil
import sys

from flask import jsonify, request

HOME = os.path.realpath(os.path.expanduser("~"))
_WORDS = {"desktop": "~/Desktop", "downloads": "~/Downloads", "documents": "~/Documents", "home": "~"}


def _clean(p):
    p = (p or "").strip().strip("\"'`").strip()
    low = p.lower().replace("the ", "", 1) if p.lower().startswith("the ") else p.lower()
    if low in _WORDS:
        p = _WORDS[low]
    return os.path.abspath(os.path.expanduser(p))


def _inside_home(p):
    real = os.path.realpath(os.path.dirname(p)) if os.path.islink(p) else os.path.realpath(p)
    return real == HOME or real.startswith(HOME + os.sep)


def move_file(src, dst):
    """Returns (ok, dict). Raises nothing for rule violations; they come back as ok False with an error."""
    if not src or not dst:
        return False, {"error": "src and dst are required"}
    s, d = _clean(src), _clean(dst)
    if not (_inside_home(s) and _inside_home(d)):
        return False, {"error": "both paths must be inside the home folder", "src": s, "dst": d}
    if not os.path.lexists(s):
        return False, {"error": "source does not exist", "src": s}
    if os.path.isdir(s) and not os.path.islink(s):
        return False, {"error": "source is a folder; only files are moved", "src": s}
    if os.path.isdir(d):
        d = os.path.join(d, os.path.basename(s))
    if os.path.lexists(d):
        return False, {"error": "destination already exists; nothing overwritten", "src": s, "dst": d}
    if not os.path.isdir(os.path.dirname(d)):
        return False, {"error": "destination folder does not exist", "src": s, "dst": d}
    try:
        shutil.move(s, d)
    except Exception as e:
        return False, {"error": f"move failed: {e}", "src": s, "dst": d, "src_gone": not os.path.lexists(s), "dst_exists": os.path.lexists(d)}
    gone, exists = not os.path.lexists(s), os.path.lexists(d)
    size = os.lstat(d).st_size if exists else None
    return gone and exists, {"src": s, "dst": d, "src_gone": gone, "dst_exists": exists, "dst_size": size}


def register(app):
    @app.post("/api/system/move")
    def system_move():
        dd = request.get_json(silent=True) or {}
        ok, res = move_file(dd.get("src"), dd.get("dst"))
        return jsonify(ok=ok, **res), (200 if ok else 400)


def _say(ok, r):
    if not ok:
        return f"I did not move it: {r.get('error')}" + (f" ({r['src']})" if r.get("src") else "") + "."
    return f"Moved. Read back: {r['src']} is gone: {'yes' if r['src_gone'] else 'NO'}; {r['dst']} exists: {'yes' if r['dst_exists'] else 'NO'}, {r['dst_size']} bytes."


def chat_move_command(text):
    """Local chat command; returns None when the sentence is not 'move X to Y'."""
    if sys.platform != "darwin":
        return None
    t = (text or "").strip()
    if len(t) > 400:
        return None
    m = re.match(r"^(?:please\s+|can you\s+|molim te\s+)?(?:move|premjesti|prebaci)\s+(?:the\s+file\s+)?(.+?)\s+(?:to|into|na|u)\s+(.+?)[\s.!?]*$", t, re.I | re.S)
    if not m:
        return None
    src, dst = m.group(1).strip(), m.group(2).strip()
    if not re.match(r"^[\"'`]?[~/]", src):
        return None
    ok, r = move_file(src, dst)
    return _say(ok, r)
