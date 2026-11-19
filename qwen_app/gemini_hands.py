"""Gemini with hands (v26, 18.11.2026): the Google Cloud side of a MASTER / SLAVE pair.

Marko: "When Google executes and tests the application, it gives you back the report". Before v26 the Google Cloud provider
was text only (gcloud_chat.gemini_turn: one generateContent call, no tools). A slave must really work in the chat's folder,
so this module gives Gemini a function-calling loop with four tools:

    list_files(path=".")              entries of a folder (max 300)
    read_file(path, start=1, end=0)   a text file (max 60,000 characters)
    write_file(path, content)         create or overwrite a text file (parent folders made)
    run_shell(command, timeout=60)    /bin/zsh -lc in the folder, timeout max 180 s, output tail 8,000 characters

Confinement: every path is resolved (symlinks too) and must stay inside the chat's folder; the folder itself must be inside
the home folder and is never the home folder itself. run_shell runs with the folder as cwd, refuses sudo / su / shutdown /
launchctl / diskutil and absolute or ~ paths outside the folder (system tool folders like /usr, /bin, /opt/homebrew and
/dev/null are allowed). This is a guard against mistakes, not a sandbox against a hostile model: the slave is Marko's own
Gemini on Marko's own task. Every call is booked on the Google Cloud ledger (gcloud_chat.ledger), the loop stops between
calls when STOP is pressed or the pair's cost cap is reached, and a running shell command is killed (its process group).
Keys come from gcloud_chat._keys() and are never printed.
"""
from __future__ import annotations
import re

import json
import os
import shlex
import signal
import subprocess
import time
import urllib.error
from pathlib import Path

import gcloud_chat as G

MAX_STEPS = 30
MAX_READ = 60_000
MAX_OUT = 8_000
ALLOWED_ABS = ("/usr/", "/bin/", "/sbin/", "/opt/homebrew/", "/dev/null", "/tmp/", "/private/tmp/", "/Library/Developer/",
               "/Applications/Xcode")
REFUSED_WORDS = {"sudo", "su", "shutdown", "reboot", "halt", "launchctl", "diskutil", "mkfs", "dd", "csrutil", "osascript"}

DECLS = [
    {"name": "list_files", "description": "List the files and folders at a path inside the working folder.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "relative path, default ."}}}},
    {"name": "read_file", "description": "Read a text file inside the working folder (optionally a line range).",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "start": {"type": "integer"},
                                                      "end": {"type": "integer"}}, "required": ["path"]}},
    {"name": "write_file", "description": "Create or overwrite a text file inside the working folder with the full content.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                    "required": ["path", "content"]}},
    {"name": "run_shell", "description": "Run a shell command in the working folder (zsh). Use it to run and test programs. "
                                         "Output (stdout+stderr) and the exit code come back.",
     "parameters": {"type": "object", "properties": {"command": {"type": "string"},
                                                      "timeout": {"type": "integer", "description": "seconds, max 180"}},
                    "required": ["command"]}},
]


class Stopped(Exception):
    pass


def folder_ok(cwd):
    """-> (realpath, '') or ('', reason). The slave's folder: inside home, not home itself, exists."""
    home = os.path.realpath(str(Path.home()))
    p = os.path.realpath(os.path.expanduser(cwd or ""))
    if not os.path.isdir(p):
        return "", "the folder does not exist"
    if p == home:
        return "", "the home folder itself is too wide for the slave's hands: pick a project folder"
    if not p.startswith(home + os.sep):
        return "", "the folder must be inside the home folder"
    return p, ""


def _inside(root, rel):
    p = os.path.realpath(os.path.join(root, os.path.expanduser(rel or ".")))
    if p != root and not p.startswith(root + os.sep):
        raise ValueError(f"{rel}: outside the working folder")
    return p


def _shell_guard(root, cmd):
    try:
        toks = shlex.split(cmd, posix=True)
    except ValueError:
        toks = cmd.split()
    for t in toks:
        w = os.path.basename(t)
        if w in REFUSED_WORDS:
            return f"refused: '{w}' is not allowed for the slave"
        for part in t.replace("=", " ").split():
            if part.startswith("~") or part.startswith("/"):
                full = os.path.realpath(os.path.expanduser(part))
                if full == root or full.startswith(root + os.sep):
                    continue
                if any(full.startswith(a.rstrip("/")) for a in ALLOWED_ABS) or any(part.startswith(a) for a in ALLOWED_ABS):
                    continue
                return f"refused: the path {part} is outside the working folder"
    if ".." in cmd.replace("...", ""):
        return "refused: '..' would leave the working folder"
    return ""


def tool(root, name, args, stop_event=None):
    """Run one tool call. -> (result dict for Gemini, one short line for the chat)."""
    args = args or {}
    try:
        if name == "list_files":
            p = _inside(root, args.get("path") or ".")
            names = sorted(os.listdir(p))[:300]
            out = [n + ("/" if os.path.isdir(os.path.join(p, n)) else "") for n in names]
            return {"entries": out}, f"list_files {args.get('path') or '.'}"
        if name == "read_file":
            p = _inside(root, args.get("path"))
            text = Path(p).read_text(errors="replace")
            s, e = int(args.get("start") or 1), int(args.get("end") or 0)
            if s > 1 or e:
                lines = text.splitlines()
                text = "\n".join(lines[max(0, s - 1):(e or len(lines))])
            return {"content": text[:MAX_READ], "truncated": len(text) > MAX_READ}, f"read_file {args.get('path')}"
        if name == "write_file":
            p = _inside(root, args.get("path"))
            content = str(args.get("content") or "")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            Path(p).write_text(content)
            return {"ok": True, "bytes": len(content.encode())}, f"write_file {args.get('path')} ({len(content)} chars)"
        if name == "run_shell":
            cmd = str(args.get("command") or "").strip()
            if not cmd:
                return {"error": "empty command"}, "run_shell (empty)"
            why = _shell_guard(root, cmd)
            if why:
                return {"error": why}, f"run_shell REFUSED {cmd[:70]}"
            t = max(1, min(180, int(args.get("timeout") or 60)))
            env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "ANTHROPIC", "GEMINI", "GOOGLE"))}
            pr = subprocess.Popen(["/bin/zsh", "-lc", cmd], cwd=root, env=env, stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
            t0 = time.time()
            while pr.poll() is None:
                if stop_event is not None and stop_event.is_set():
                    _kill(pr)
                    raise Stopped()
                if time.time() - t0 > t:
                    _kill(pr)
                    out = (pr.stdout.read() or "") if pr.stdout else ""
                    return {"exit_code": None, "timed_out": True, "output": out[-MAX_OUT:]}, f"run_shell {cmd[:70]} (timed out {t}s)"
                time.sleep(0.1)
            out = pr.stdout.read() if pr.stdout else ""
            return {"exit_code": pr.returncode, "output": out[-MAX_OUT:]}, f"run_shell {cmd[:70]} -> exit {pr.returncode}"
        return {"error": f"unknown tool {name}"}, f"{name}?"
    except Stopped:
        raise
    except Exception as exc:
        return {"error": str(exc)[:300]}, f"{name} error: {str(exc)[:60]}"


def _kill(pr):
    try:
        os.killpg(pr.pid, signal.SIGTERM)
        pr.wait(timeout=3)
    except Exception:
        try:
            os.killpg(pr.pid, signal.SIGKILL)
        except Exception:
            pass


def _call(model, body, timeout=120):
    """One generateContent call with key failover. -> json. Raises RuntimeError(line without keys)."""
    keys = G._keys()
    if not keys:
        raise RuntimeError("no Google Cloud key found in the CGP_free_credits file")
    last = ""
    for k in keys:
        try:
            return G._post(f"{G.GEMINI}/models/{model}:generateContent", body, {"x-goog-api-key": k}, timeout=timeout)
        except urllib.error.HTTPError as exc:
            code, msg = G._http_err(exc)
            last = f"Gemini {code}: {msg}"
            if code in (400, 404):
                break
        except Exception as exc:
            last = G._scrub(f"Gemini did not answer: {exc}")[:200]
    raise RuntimeError(last or "Gemini did not answer")


def _usage_cost(model, j):
    u = j.get("usageMetadata") or {}
    tin = int(u.get("promptTokenCount") or 0)
    tout = int(u.get("candidatesTokenCount") or 0) + int(u.get("thoughtsTokenCount") or 0)
    return G._cost(model, tin, tout)


# 404 dead-model recovery
_REPLACEMENTS = {}
_CACHED_MODELS = None

def _find_replacement(old_model, err_text):
    global _CACHED_MODELS
    if old_model in _REPLACEMENTS:
        return _REPLACEMENTS[old_model]
    
    # 1. Suggested replacement in error text (e.g. 'models/gemini-3.1-pro-preview')
    matches = re.findall(r'models/([a-zA-Z0-9_.-]+)', err_text)
    for target in matches:
        if target != old_model:
            _REPLACEMENTS[old_model] = target
            return target

    # 2. Query ListModels via G.gemini_models()
    try:
        if _CACHED_MODELS is None:
            _CACHED_MODELS = G.gemini_models() or []
    except Exception:
        _CACHED_MODELS = []

    candidates = []
    for item in _CACHED_MODELS:
        name = item.get('name', '') if isinstance(item, dict) else str(item)
        mid = name.replace('models/', '')
        methods = item.get('supportedGenerationMethods', []) if isinstance(item, dict) else ['generateContent']
        if 'generateContent' in methods and mid != old_model:
            candidates.append(mid)

    def tier(name):
        n = name.lower()
        if 'pro' in n: return 3
        if 'flash-lite' in n or 'lite' in n: return 1
        if 'flash' in n: return 2
        return 0

    old_tier = tier(old_model)
    same_tier = [c for c in candidates if tier(c) == old_tier]
    if same_tier:
        rep = sorted(same_tier)[0]
        _REPLACEMENTS[old_model] = rep
        return rep

    for t in range(old_tier - 1, 0, -1):
        lower = [c for c in candidates if tier(c) == t]
        if lower:
            rep = sorted(lower)[0]
            _REPLACEMENTS[old_model] = rep
            return rep

    return None

def _call_with_recovery(model, body, timeout=120, notice_cb=None):
    current = _REPLACEMENTS.get(model, model)
    try:
        return _call(current, body, timeout=timeout), current
    except RuntimeError as exc:
        msg = str(exc)
        is_404 = 'Gemini 404' in msg and any(x in msg.lower() for x in ['no longer available', 'not found', 'models/'])
        if not is_404:
            raise
        try:
            import gcloud_chat as _G
            _G.RETIRED.add(current)
            rf = Path(__file__).parent / "retired_models.json"
            with open(rf, "w", encoding="utf-8") as f:
                json.dump(sorted(_G.RETIRED), f, indent=2)
        except Exception:
            pass
        new_model = _find_replacement(current, msg)
        if not new_model or new_model == current:
            raise RuntimeError(f"404: {current} is gone, and no replacement was found ({msg})")
        notice = f"404: {current} is gone, using {new_model}"
        print(f"[33m{notice}[0m")
        if notice_cb:
            try:
                notice_cb(notice)
            except Exception:
                pass
        try:
            res = _call(new_model, body, timeout=timeout)
            _REPLACEMENTS[model] = new_model
            _REPLACEMENTS[current] = new_model
            return res, new_model
        except RuntimeError as exc2:
            raise RuntimeError(f"404: {current} is gone, and replacement {new_model} also failed: {exc2}")


def text_turn(model, system, history, text, label="pair", notice_cb=None):
    """Gemini as MASTER (plans, reviews): text only. history [(user|model, text)]. -> (answer, cost)."""
    contents = [{"role": r, "parts": [{"text": t}]} for r, t in history if t.strip()]
    contents.append({"role": "user", "parts": [{"text": text}]})
    j, effective_model = _call_with_recovery(model, {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents}, notice_cb=notice_cb)
    cost = _usage_cost(effective_model, j)
    G.ledger(cost, label + " " + text, effective_model)
    cand = (j.get("candidates") or [{}])[0]
    ans = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []) if not p.get("thought"))
    if not ans.strip():
        raise RuntimeError("Gemini gave no text (" + str(cand.get("finishReason") or "empty") + ")")
    return ans.strip(), cost


def agent_turn(model, system, history, text, cwd, on_tool=None, stop_event=None, budget=None, label="pair slave", notice_cb=None, files=None):
    """Gemini as SLAVE: the tool loop. -> (final text, cost, steps). budget(): dollars still allowed for this pair turn.
    Raises Stopped on STOP, RuntimeError on a service error (cost so far already booked; see .cost on the error)."""
    system = system + f"\n\nYou have at most {MAX_STEPS} tool steps. Always end with a plain-text report (no tool call): what you did, the commands with their real output, what is left."
    root, why = folder_ok(cwd)
    if not root:
        raise RuntimeError("Gemini slave: " + why)
    contents = [{"role": r, "parts": [{"text": t}]} for r, t in history if t.strip()]
    contents.append({"role": "user", "parts": G._gemini_parts(text, files or [])})
    total = 0.0
    for step in range(1, MAX_STEPS + 1):
        if stop_event is not None and stop_event.is_set():
            raise Stopped()
        if budget is not None and budget() - total <= 0:
            return f"(the slave stopped: the pair's cost cap was reached after {step - 1} steps)", total, step - 1
        try:
            j, model = _call_with_recovery(model, {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents,
                                           "tools": [{"functionDeclarations": DECLS}]}, notice_cb=notice_cb)
        except RuntimeError as exc:
            exc.cost = total
            raise
        c = _usage_cost(model, j)
        total += c
        G.ledger(c, f"{label} step {step}", model)
        if stop_event is not None and stop_event.is_set():
            raise Stopped()
        cand = (j.get("candidates") or [{}])[0]
        content = cand.get("content") or {}
        parts = content.get("parts") or []
        calls = [p["functionCall"] for p in parts if p.get("functionCall")]
        if not calls:
            ans = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
            if not ans:
                ans = "(Gemini ended without a report: " + str(cand.get("finishReason") or "empty") + ")"
            return ans, total, step
        contents.append({"role": "model", "parts": parts})          # verbatim, thought signatures included
        replies = []
        for fc in calls:
            res, line = tool(root, fc.get("name"), fc.get("args") or {}, stop_event)
            if on_tool:
                on_tool(line)
            fr = {"name": fc.get("name"), "response": res}
            if fc.get("id"):
                fr["id"] = fc["id"]
            replies.append({"functionResponse": fr})
        replies.append({"text": f"[step {step} of {MAX_STEPS}. Report by step {MAX_STEPS - 3}: what was done, the commands with their real output, what is left.]"})
        contents.append({"role": "user", "parts": replies})
    contents.append({"role": "user", "parts": [{"text": "Tool steps are used up. Write your final report now: what you did, the commands with their real output, what is not done."}]})
    try:
        j, model = _call_with_recovery(model, {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": contents,
            "tools": [{"functionDeclarations": DECLS}],
            "toolConfig": {"functionCallingConfig": {"mode": "NONE"}},
        }, notice_cb=notice_cb)
    except RuntimeError as exc:
        exc.cost = total
        raise
    c = _usage_cost(model, j)
    total += c
    G.ledger(c, f"{label} final report", model)
    cand = (j.get("candidates") or [{}])[0]
    parts = (cand.get("content") or {}).get("parts") or []
    ans = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    if ans:
        return ans, total, MAX_STEPS
    return f"(the slave used all {MAX_STEPS} tool steps without a final report)", total, MAX_STEPS
