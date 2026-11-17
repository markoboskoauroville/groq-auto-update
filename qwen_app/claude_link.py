"""Queen <-> the local Claude Code (12.11.2026). Local first; API credits only with Marko's yes.

Marko, 12.11.2026: "Establish this connection between Queen and you. She can read remote sessions, she can talk to you,
and you can talk to her. She can ask you questions, and you can ask her questions and give her solutions. But if we are
online, she's not contacting the API at Anthropic. No way. Or API Google. If there is a local connection with you, Claude
Code, that's the priority. If it's missing, she's asking, 'I cannot reach the local Claude Code. Do you want to use API
credits?' Then we use API credits. We are trying to avoid using API credits."

How Queen reaches Claude Code, all on this Mac, on Marko's claude.ai plan (never an API key):
    ask        `claude -p` headless, its own process, in ~/.groq/claude_link; ANTHROPIC_API_KEY and the parent
               session's CLAUDE* variables are removed so the plan login is used (a nested call that inherits
               CLAUDECODE from a running session dies with exit 144: tested 12.11.2026).
    sessions   the live Claude Code sessions (hub tools/other_sessions.py json) and their transcripts (read only).
    tell       type a line into a live session's iTerm tab (other_sessions.py type): for when Marko wants a session
               to see Queen's question; it lands in his tab, so only on request.
How Claude Code reaches Queen: POST /api/chat, or the `queen` command in the hub (tools/queen).

The gate: every place that would spend Anthropic or Google API credits calls `route(allow_api)` first.
Local Claude reachable -> "local". Not reachable and no yes -> NeedConsent with Marko's sentence. Yes -> "api".

    GET  /api/claude/status                       reachable? (binary, plan login) and the live sessions
    GET  /api/claude/sessions                     live sessions: name, folder, last prompts
    GET  /api/claude/transcript?sid=S&n=20        the last N turns of a session, text only
    POST /api/claude/ask {question, model?, cwd?}  ask the local Claude Code; answer text
    POST /api/claude/tell {sid, text}             type into a live session's tab (Marko asked for it)
"""
import json
import os
import subprocess
import time
from pathlib import Path

from flask import jsonify, request

CLAUDE_BIN = Path.home() / ".local" / "bin" / "claude"
HUB_TOOLS = Path.home() / "Developer" / "claude-code" / "tools"
WORKDIR = Path.home() / ".groq" / "claude_link"
CONSENT_TEXT = "I cannot reach the local Claude Code. Do you want to use API credits?"
_STATUS = {"t": 0, "value": None}
# The headless run still reads Marko's CLAUDE.md (voice replies, handover, session greeting). Queen wants the answer only.
HEADLESS_NOTE = ("You are answering QUEEN, headless, through `claude -p`: no human is watching this run. "
                 "Do not speak (no langsay or voice), no handover report, no greeting, no questions back. "
                 "Do only what the request asks and answer with the result in plain text.")


class NeedConsent(Exception):
    def __init__(self):
        super().__init__(CONSENT_TEXT)


def _env():
    env = {k: v for k, v in os.environ.items()
           if not (k.startswith("CLAUDE") or k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"))}
    env["PATH"] = f"{CLAUDE_BIN.parent}:{env.get('PATH', '/usr/bin:/bin')}"
    return env


_STALL = {"until": 0, "why": ""}


def status(force=False):
    """Is the local Claude Code usable on the plan? Cached for a minute."""
    if time.time() < _STALL["until"]:
        return {"reachable": False, "why": _STALL["why"]}
    if not force and _STATUS["value"] and time.time() - _STATUS["t"] < 60:
        return _STATUS["value"]
    v = {"reachable": False, "why": ""}
    if not CLAUDE_BIN.exists():
        v["why"] = f"no Claude Code at {CLAUDE_BIN}"
    else:
        try:
            r = subprocess.run([str(CLAUDE_BIN), "auth", "status"], capture_output=True, text=True,
                               timeout=20, env=_env(), stdin=subprocess.DEVNULL)
            a = json.loads(r.stdout or "{}")
            if not a.get("loggedIn"):
                v["why"] = "Claude Code is not logged in"
            elif a.get("authMethod") != "claude.ai":
                v["why"] = f"Claude Code is logged in by {a.get('authMethod')}, not the claude.ai plan"
            else:
                v = {"reachable": True, "why": "", "auth": "claude.ai plan"}
        except Exception as exc:
            v["why"] = f"auth check failed: {type(exc).__name__}: {exc}"
    _STATUS.update(t=time.time(), value=v)
    return v


def route(allow_api=False):
    """'local' when Claude Code is reachable; 'api' only with Marko's yes; else NeedConsent."""
    if status()["reachable"]:
        return "local"
    if allow_api:
        return "api"
    raise NeedConsent()


def ask(question, model="sonnet", cwd=None, timeout=600, permission_mode=None, allowed_tools=None):
    """Ask the local Claude Code (headless, on the plan). Returns {answer, duration_ms, ...}."""
    if not status()["reachable"]:
        raise NeedConsent()
    WORKDIR.mkdir(parents=True, exist_ok=True)
    cmd = [str(CLAUDE_BIN), "-p", question, "--output-format", "json", "--no-session-persistence",
           "--model", model or "sonnet", "--append-system-prompt", HEADLESS_NOTE]
    if permission_mode:
        cmd += ["--permission-mode", permission_mode]
    if allowed_tools:
        cmd += ["--allowedTools", *allowed_tools]
    else:
        # a plain question needs no shell: without Bash it cannot try langsay or any other side effect
        cmd += ["--disallowedTools", "Bash"]
    try:
        r = subprocess.run(cmd, cwd=str(cwd or WORKDIR), capture_output=True, text=True, timeout=timeout,
                           env=_env(), stdin=subprocess.DEVNULL, start_new_session=True)
    except subprocess.TimeoutExpired:
        # logged in but not answering (plan limit, network): treat as unreachable for 5 minutes -> Marko's yes for the API
        _STALL.update(until=time.time() + 300, why=f"Claude Code did not answer in {timeout} s")
        raise NeedConsent()
    try:
        d = json.loads(r.stdout)
    except Exception:
        raise RuntimeError(f"Claude Code gave no answer (rc {r.returncode}): {(r.stderr or r.stdout)[:300]}")
    if d.get("is_error"):
        raise RuntimeError(f"Claude Code: {d.get('result') or d.get('subtype')}")
    return {"answer": d.get("result", ""), "duration_ms": d.get("duration_ms"), "via": "local Claude Code (plan)",
            "model": model, "turns": d.get("num_turns")}


def _hub(*args, timeout=30):
    r = subprocess.run(["python3", str(HUB_TOOLS / "other_sessions.py"), *args], capture_output=True, text=True,
                       timeout=timeout, env=_env(), stdin=subprocess.DEVNULL)
    return r.returncode, r.stdout, r.stderr


def sessions():
    if not (HUB_TOOLS / "other_sessions.py").exists():   # the VM has no hub (two locations, 13.11.2026): no live-session list
        return []
    code, out, err = _hub("json")
    if code != 0:
        raise RuntimeError(f"other_sessions.py json failed: {err.strip()[:200]}")
    return json.loads(out or "[]")


def transcript(sid, n=20):
    """The last n user/assistant text turns of a session (read only)."""
    sid = (sid or "").strip()
    if not sid or "/" in sid or ".." in sid:
        raise ValueError("pass sid=<session id>")
    hits = list((Path.home() / ".claude" / "projects").glob(f"*/{sid}.jsonl"))
    if not hits:
        raise ValueError(f"no transcript for {sid}")
    turns = []
    for line in hits[0].read_text(errors="replace").splitlines():
        try:
            e = json.loads(line)
        except Exception:
            continue
        if e.get("type") not in ("user", "assistant"):
            continue
        c = (e.get("message") or {}).get("content")
        if isinstance(c, list):
            c = " ".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text")
        if isinstance(c, str) and c.strip() and not c.lstrip().startswith("<"):
            turns.append({"role": e["type"], "when": e.get("timestamp", ""), "text": c.strip()[:4000]})
    return {"sid": sid, "file": str(hits[0]), "turns": turns[-int(n or 20):]}


def tell(sid, text):
    code, out, err = _hub("type", sid, f"[Queen] {text}")
    if code != 0:
        raise RuntimeError(f"could not type into {sid}: {(err or out).strip()[:200]}")
    return {"typed": True, "sid": sid}


def register(app):
    def wrap(fn):
        try:
            return jsonify(ok=True, **fn())
        except NeedConsent as exc:
            return jsonify(ok=False, need_consent=True, message=str(exc)), 409
        except (ValueError, RuntimeError) as exc:
            return jsonify(ok=False, error=str(exc)), 400
        except subprocess.TimeoutExpired:
            return jsonify(ok=False, error="Claude Code did not answer in time"), 504
        except Exception as exc:
            return jsonify(ok=False, error=f"{type(exc).__name__}: {exc}"), 500

    @app.get("/api/claude/status")
    def claude_status():
        return wrap(lambda: {**status(force=request.args.get("force") == "1"),
                             "live_sessions": len(sessions())})

    @app.get("/api/claude/sessions")
    def claude_sessions():
        return wrap(lambda: {"sessions": sessions()})

    @app.get("/api/claude/transcript")
    def claude_transcript():
        return wrap(lambda: transcript(request.args.get("sid"), request.args.get("n", 20)))

    @app.post("/api/claude/ask")
    def claude_ask():
        d = request.get_json(silent=True) or {}
        q = (d.get("question") or "").strip()
        if not q:
            return jsonify(ok=False, error="pass {question}"), 400
        return wrap(lambda: ask(q, model=d.get("model") or "sonnet"))

    @app.post("/api/claude/tell")
    def claude_tell():
        d = request.get_json(silent=True) or {}
        return wrap(lambda: tell(d.get("sid", ""), d.get("text", "")))

    return app


# ------------------------------------------------------------------------------ chat
import re  # noqa: E402

_ASK = re.compile(r"^\W*(please\W+)?ask\s+claude(\s+code)?(?P<api>\s+with\s+api\s+credits)?\s*[:,]?\s+(?P<q>.+)$", re.I | re.S)
_SESS = re.compile(r"^\W*(list|show)\s+(the\s+)?(claude\s+)?sessions\W*$", re.I)


def chat_claude_command(text):
    t = (text or "").strip()
    m = _SESS.match(t)
    if m:
        ss = sessions()
        if not ss:
            return "No Claude Code session is open on this Mac."
        return "\n".join(f"{s.get('title') or s.get('name') or s.get('sid')}: {s.get('cwd', '')}" for s in ss)
    m = _ASK.match(t)
    if not m:
        return None
    q = m["q"].strip()
    try:
        return ask(q)["answer"]
    except NeedConsent:
        if not m["api"]:
            return CONSENT_TEXT + "\n(To go ahead, write: ask claude with API credits: <your question>)"
        try:
            import brain  # noqa: PLC0415
            return brain.escalate_text(q)
        except Exception as exc:
            return f"API route failed: {exc}"
    except Exception as exc:
        return f"Claude Code did not answer: {exc}"
