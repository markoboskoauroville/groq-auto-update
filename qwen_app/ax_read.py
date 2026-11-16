"""Queen reads apps through the macOS Accessibility API: text, never a screenshot (14.11.2026, Mac only).

Marko, 14.11.2026: "upgrade it with new skills for accessibility ... Without taking screenshots, it needs to use accessibility
to get the text".

    POST /api/ax/read {app, window?, query?, depth?, roles?, max?, timeout?, frames?, focused?}
        -> {ok, app, pid, via: "axread"|"python", trusted, windows: [tree], matches?: [...], nodes, secs}
        A node: {role, title?, value?, description?, x?, y?, w?, h?, children?: [...]}

The reader is the Swift CLI `axread` (repo groq_ai_studio, folder mac_app, built by GitHub, shipped inside
"Queen.app/Contents/MacOS/axread", linked as ~/.local/bin/axread). When it is not there the same walk runs here
in Python (pyobjc, ApplicationServices loaded by hand: no extra package). Both print the same JSON.

Firefox: its web content (AXWebArea) appears only after an assistive client asks; we set AXManualAccessibility (and
AXEnhancedUserInterface for Chromium apps) on the app element first. Only the SELECTED tab of a window is in the tree, and only
windows on the current Space are listed (macOS AX). Permission: the process that started Queen (iTerm2, or the app) must be
allowed under Privacy & Security > Accessibility; otherwise `trusted` is false and nothing is read.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

AXREAD_PATHS = [
    os.path.expanduser("~/.local/bin/axread"),
    "/Applications/Queen.app/Contents/MacOS/axread",
]
TEXT_KEYS = ("title", "value", "description")


def axread_binary():
    for p in AXREAD_PATHS:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return shutil.which("axread")


# ---------- the Python walk (fallback, same output as the Swift axread) ----------
_AX = {}


def _ax():
    if _AX:
        return _AX
    import objc
    from Foundation import NSBundle
    b = NSBundle.bundleWithPath_("/System/Library/Frameworks/ApplicationServices.framework")
    g = {}
    objc.loadBundleFunctions(b, g, [("AXUIElementGetTypeID", b"Q")])
    try:
        objc.registerCFSignature("AXUIElementRef", b"^{__AXUIElement=}", g["AXUIElementGetTypeID"]())
    except Exception:
        pass
    objc.loadBundleFunctions(b, g, [
        ("AXIsProcessTrusted", b"Z"),
        ("AXUIElementCreateApplication", b"^{__AXUIElement=}i"),
        ("AXUIElementCopyAttributeValue", b"i^{__AXUIElement=}^{__CFString=}o^@"),
        ("AXUIElementSetAttributeValue", b"i^{__AXUIElement=}^{__CFString=}@"),
        ("AXUIElementSetMessagingTimeout", b"i^{__AXUIElement=}f"),
        ("AXValueGetValue", b"i^{__AXValue=}I^v"),
    ])
    _AX.update(g)
    return _AX


def _attr(e, k):
    err, v = _ax()["AXUIElementCopyAttributeValue"](e, k, None)
    return v if err == 0 else None


def _point(e, k):
    """AXPosition / AXSize as two floats (parsed from the AXValue description: no struct bridging needed)."""
    v = _attr(e, k)
    if v is None:
        return None
    s = str(v)
    import re
    m = re.search(r"[xw]:\s*(-?[\d.]+)\s+[yh]:\s*(-?[\d.]+)", s)
    return (float(m.group(1)), float(m.group(2))) if m else None


def find_app(name):
    from AppKit import NSWorkspace
    n = (name or "").lower().replace(" ", "")
    apps = [a for a in NSWorkspace.sharedWorkspace().runningApplications() if a.activationPolicy() != 2]

    def nm(a):
        return (a.localizedName() or "").lower().replace(" ", "")
    for test in (lambda a: nm(a) == n, lambda a: nm(a).startswith(n), lambda a: n in nm(a),
                 lambda a: n in (a.bundleIdentifier() or "").lower()):
        hit = [a for a in apps if test(a)]
        if hit:
            return hit[0]
    return None


def python_read(app, window=None, depth=60, roles=None, max_nodes=8000, timeout=15.0, frames=False, focused=False):
    ax = _ax()
    trusted = bool(ax["AXIsProcessTrusted"]())
    if not trusted:
        return {"ok": False, "trusted": False, "via": "python",
                "error": "Accessibility is not allowed for the process that runs Queen (System Settings > Privacy & Security > Accessibility)"}
    a = find_app(app)
    if not a:
        return {"ok": False, "trusted": True, "via": "python", "error": "not running: " + str(app)}
    root = ax["AXUIElementCreateApplication"](a.processIdentifier())
    ax["AXUIElementSetMessagingTimeout"](root, 3.0)
    for k in ("AXManualAccessibility", "AXEnhancedUserInterface"):
        ax["AXUIElementSetAttributeValue"](root, k, True)   # Firefox / Chromium: expose the web content
    t0 = time.time()
    count = [0]
    roles = set(roles or [])

    def node(e, d):
        if count[0] >= max_nodes or time.time() - t0 > timeout:
            return None
        count[0] += 1
        o = {"role": str(_attr(e, "AXRole") or "")}
        for k, ak in (("title", "AXTitle"), ("value", "AXValue"), ("description", "AXDescription")):
            v = _attr(e, ak)
            if isinstance(v, (str, int, float, bool)) and str(v).strip() != "":
                o[k] = v if not isinstance(v, bool) else bool(v)
        if frames:
            p, s = _point(e, "AXPosition"), _point(e, "AXSize")
            if p and s:
                o.update(x=p[0], y=p[1], w=s[0], h=s[1])
        if d < depth:
            kids = []
            for c in _attr(e, "AXChildren") or []:
                k = node(c, d + 1)
                if k is not None:
                    kids.append(k)
            if kids:
                o["children"] = kids
        if roles and o["role"] not in roles and "children" not in o:
            return None
        return o

    if focused:
        f = _attr(root, "AXFocusedUIElement")
        tops = [f] if f is not None else []
    else:
        tops = list(_attr(root, "AXWindows") or [])
        if window:
            tops = [w for w in tops if str(window).lower() in str(_attr(w, "AXTitle") or "").lower()]
    trees = [t for t in (node(w, 0) for w in tops) if t]
    return {"ok": True, "trusted": True, "via": "python", "app": a.localizedName(), "pid": a.processIdentifier(),
            "windows": trees, "nodes": count[0], "secs": round(time.time() - t0, 2),
            "truncated": count[0] >= max_nodes or time.time() - t0 > timeout}


# ---------- the one entry ----------
def read(app, window=None, depth=60, roles=None, max_nodes=8000, timeout=15.0, frames=False, focused=False, prefer="axread"):
    exe = axread_binary() if prefer == "axread" else None
    if exe:
        cmd = [exe, "--app", app, "--depth", str(depth), "--max", str(max_nodes), "--timeout", str(timeout)]
        if window:
            cmd += ["--window", window]
        if roles:
            cmd += ["--roles", ",".join(roles)]
        if frames:
            cmd.append("--frames")
        if focused:
            cmd.append("--focused")
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10)
            out = json.loads(r.stdout or "{}")
            out.setdefault("via", "axread")
            if out.get("ok") or out.get("trusted") is not False:
                return out
            # axread is not trusted (its starter has no permission) but this process may be: try here
            py = python_read(app, window, depth, roles, max_nodes, timeout, frames, focused)
            return py if py.get("ok") else out
        except Exception as e:
            print(f"[ax] axread failed, Python walk instead: {e}", flush=True)
    return python_read(app, window, depth, roles, max_nodes, timeout, frames, focused)


def flatten(tree, out=None, depth=0):
    """Every node with text as one line: (depth, role, text)."""
    out = [] if out is None else out
    txt = " | ".join(str(tree[k]) for k in TEXT_KEYS if k in tree)
    if txt:
        out.append((depth, tree.get("role", ""), txt))
    for c in tree.get("children", []):
        flatten(c, out, depth + 1)
    return out


def search(result, query, limit=200):
    q = (query or "").lower()
    hits = []
    for w in result.get("windows", []):
        for d, role, txt in flatten(w):
            if q in txt.lower():
                hits.append({"role": role, "text": txt[:500]})
                if len(hits) >= limit:
                    return hits
    return hits


def as_text(result, limit=400):
    lines = []
    for w in result.get("windows", []):
        for d, role, txt in flatten(w):
            lines.append("  " * min(d, 12) + role.replace("AX", "") + ": " + txt[:300])
    return "\n".join(lines[:limit])


AX_CHAT = None


def chat_ax_command(text):
    """Chat: "ax read Finder", "read the accessibility text of Firefox", "ax read Firefox for Svemir" (only lines with it)."""
    import re
    global AX_CHAT
    AX_CHAT = AX_CHAT or re.compile(r"^\s*(?:ax\s+read|read\s+(?:the\s+)?(?:accessibility|ax)(?:\s+(?:text|tree))?\s+(?:of|from|in)(?:\s+the)?)\s+"
                                    r"(.+?)(?:\s+(?:app|window))?(?:\s+(?:for|with|containing)\s+[\"']?(.+?)[\"']?)?\s*[.?!]?\s*$", re.I)
    m = AX_CHAT.match(text or "")
    if not m:
        return None
    name, query = m.group(1).strip(), (m.group(2) or "").strip()
    r = read(name)
    if not r.get("ok"):
        return f"I could not read {name} through Accessibility: {r.get('error')}"
    if query:
        hits = search(r, query, 40)
        body = "\n".join(f"- {h['role'].replace('AX', '')}: {h['text'][:300]}" for h in hits) or "(no line contains it)"
        return f"{r['app']} through Accessibility ({r['via']}, {r['nodes']} elements, {r['secs']} s), lines with \"{query}\":\n{body}"
    return f"{r['app']} through Accessibility ({r['via']}, {r['nodes']} elements, {r['secs']} s):\n" + as_text(r, 150)


def register(app):
    from flask import jsonify, request

    @app.post("/api/ax/read")
    def ax_read_route():
        d = request.get_json(silent=True) or {}
        name = (d.get("app") or "").strip()
        if not name:
            return jsonify(ok=False, error="app is required (e.g. Firefox)"), 400
        r = read(name, window=d.get("window"), depth=int(d.get("depth", 60)), roles=d.get("roles"),
                 max_nodes=int(d.get("max", 8000)), timeout=float(d.get("timeout", 15)),
                 frames=bool(d.get("frames")), focused=bool(d.get("focused")))
        if d.get("query") and r.get("ok"):
            r["matches"] = search(r, d["query"])
            if not d.get("tree"):
                r.pop("windows", None)
        elif d.get("text") and r.get("ok"):
            r["text"] = as_text(r)
            r.pop("windows", None)
        return jsonify(r)


if __name__ == "__main__":   # python3 ax_read.py Firefox [query]
    r = read(sys.argv[1] if len(sys.argv) > 1 else "Finder", frames=True)
    if len(sys.argv) > 2:
        print(json.dumps(search(r, sys.argv[2]), ensure_ascii=False, indent=1))
    else:
        print(as_text(r) if r.get("ok") else json.dumps(r))
