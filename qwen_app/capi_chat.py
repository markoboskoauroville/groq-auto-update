"""CAPI tab (17.11.2026): chat with Claude Code on Marko's $100 API credit, the same run `capi` does.

Marko: "can queen be used as capi ... add capi tab to queen software so i can have nicer ui". Each turn runs headless
`claude -p --model M --permission-mode auto --session-id|--resume <uuid> --output-format stream-json --verbose` with
ANTHROPIC_API_KEY from the ~/Downloads/API file named *100dolara* (never printed). The $100 promotional credit pays
headless runs only. Every run is written to ~/.cache/claude-api-ledger.jsonl (ONE credit number: api_credit.left()).

Routes (/api/capi/): GET list | get?id= | credit | folders ; POST new {cwd?} | settings {id,model,cwd} | stop {id} |
  turn {id,text} -> NDJSON {"text":..} {"tool":..} {"cost":c,"total":t,"left":l} {"error":..} {"done":1} |
  ask {text,cwd?,model?,id?} -> JSON {answer,cost,id} (non streaming, for Queen's skill capi.md)
Rooms: ~/.groq/capi/<id>.json {id,title,model,cwd,session,started,total,messages:[{role:marko|claude|tool,text,cost?}]}
"""
from __future__ import annotations

import glob
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from flask import Response, jsonify, request

ROOT = Path.home() / ".groq" / "capi"
MODELS = ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-2"]
DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_CWD = str(Path.home() / "Developer" / "claude-code")
LEDGER = Path.home() / ".cache" / "claude-api-ledger.jsonl"
_procs: dict[str, subprocess.Popen] = {}
_lock = threading.Lock()


def _now():
    return int(time.time())


def _path(rid):
    return ROOT / (re.sub(r"[^a-zA-Z0-9_-]", "", rid or "") + ".json")


def _load(rid):
    try:
        return json.loads(_path(rid).read_text())
    except Exception:
        return None


def _save(room):
    ROOT.mkdir(parents=True, exist_ok=True)
    p = _path(room["id"])
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(room, ensure_ascii=False))
    os.replace(tmp, p)


def _new(cwd=None, model=None):
    room = {"id": secrets.token_hex(5), "title": "CAPI chat", "model": model if model in MODELS else DEFAULT_MODEL,
            "cwd": _ok_cwd(cwd), "session": str(uuid.uuid4()), "started": False, "total": 0.0, "messages": [],
            "created": _now(), "updated": _now()}
    _save(room)
    return room


def _ok_cwd(cwd):
    home = str(Path.home())
    p = os.path.realpath(os.path.expanduser(cwd or DEFAULT_CWD))
    return p if (p == home or p.startswith(home + os.sep)) and os.path.isdir(p) else DEFAULT_CWD


def _key():
    for f in glob.glob(str(Path.home() / "Downloads" / "API" / "*")):
        if "100dolara" in os.path.basename(f).lower():
            m = re.search(r"sk-\S+", open(f, errors="ignore").read())
            if m:
                return m.group(0)
    return ""


def _credit_left():
    try:
        sys.path.insert(0, str(Path.home() / "Developer" / "claude-code" / "tools"))
        import api_credit
        return round(api_credit.left(), 2)
    except Exception:
        return None


def _ledger(cost, prompt, error=False):
    try:
        sys.path.insert(0, str(Path.home() / "Developer" / "claude-code" / "tools"))
        import api_credit
        api_credit.add(cost, "capi-tab " + prompt, error)
    except Exception:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with open(LEDGER, "a") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "cost": cost, "prompt": "capi-tab " + prompt[:70],
                                "error": error}) + "\n")


def run_turn(room, text):
    """Yield event dicts for one run; the room is updated and saved as it goes."""
    key = _key()
    if not key:
        yield {"error": "no key file (100dolara) in ~/Downloads/API"}
        return
    room["messages"].append({"role": "marko", "text": text})
    if room.get("title") == "CAPI chat":
        room["title"] = text.strip().splitlines()[0][:48] or "CAPI chat"
    _save(room)
    env = {k: v for k, v in os.environ.items() if not (k.startswith("CLAUDECODE") or k.startswith("CLAUDE_CODE_"))}
    env["ANTHROPIC_API_KEY"] = key
    sess = ["--resume", room["session"]] if room.get("started") else ["--session-id", room["session"]]
    cmd = ["claude", "-p", "--model", room["model"], "--permission-mode", "auto", *sess,
           "--output-format", "stream-json", "--verbose", text]
    cost = 0.0
    got_result = False
    try:
        p = subprocess.Popen(cmd, cwd=room["cwd"], env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True, bufsize=1)
    except Exception as exc:
        yield {"error": f"could not start claude: {exc}"}
        return
    with _lock:
        _procs[room["id"]] = p
    parts = []
    try:
        for line in p.stdout:
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("type") == "assistant":
                for b in (d.get("message") or {}).get("content") or []:
                    if b.get("type") == "text" and (b.get("text") or "").strip():
                        parts.append(b["text"].strip())
                        room["messages"].append({"role": "claude", "text": b["text"].strip()})
                        yield {"text": b["text"].strip()}
                    elif b.get("type") == "tool_use":
                        i = b.get("input") or {}
                        t = f'{b.get("name", "tool")} {str(i.get("description") or i.get("command") or i.get("file_path") or i.get("pattern") or "")[:90]}'.strip()
                        room["messages"].append({"role": "tool", "text": t})
                        yield {"tool": t}
            elif d.get("type") == "result":
                got_result = True
                cost = float(d.get("total_cost_usd") or 0)
                if d.get("is_error"):
                    yield {"error": str(d.get("result"))[:300]}
        p.wait(timeout=20)
    except Exception:
        pass
    finally:
        with _lock:
            _procs.pop(room["id"], None)
        if p.poll() is None:
            p.kill()
    if parts:
        for m in reversed(room["messages"]):
            if m["role"] == "claude":
                m["cost"] = round(cost, 4)
                break
    if got_result:
        room["started"] = True
    stopped = not got_result
    if cost:
        _ledger(cost, text)
        room["total"] = round(room.get("total", 0.0) + cost, 4)
    room["updated"] = _now()
    _save(room)
    if stopped:
        yield {"error": "stopped"}
    yield {"cost": round(cost, 4), "total": room["total"], "left": _credit_left()}
    yield {"done": 1}


def register(app):
    def ndj(o):
        return json.dumps(o, ensure_ascii=False) + "\n"

    def body():
        return request.get_json(silent=True) or {}

    @app.get("/api/capi/credit")
    def capi_credit():
        return jsonify({"left": _credit_left(), "has_key": bool(_key())})

    @app.get("/api/capi/folders")
    def capi_folders():
        base = Path.home() / "Developer"
        names = sorted(d.name for d in base.iterdir() if d.is_dir() and not d.name.startswith(".")) if base.is_dir() else []
        out = [{"name": n, "path": str(base / n)} for n in names]
        out.sort(key=lambda x: (x["path"] != DEFAULT_CWD, x["name"].lower()))
        return jsonify({"folders": out, "default": DEFAULT_CWD, "models": MODELS})

    @app.get("/api/capi/list")
    def capi_list():
        rooms = []
        for f in ROOT.glob("*.json") if ROOT.is_dir() else []:
            try:
                r = json.loads(f.read_text())
                rooms.append({"id": r["id"], "title": r.get("title", ""), "count": len(r.get("messages", [])),
                              "updated": r.get("updated", 0)})
            except Exception:
                pass
        rooms.sort(key=lambda r: -r["updated"])
        return jsonify({"rooms": rooms})

    @app.get("/api/capi/get")
    def capi_get():
        r = _load(request.args.get("id", ""))
        return (jsonify({"room": r}) if r else (jsonify({"error": "no such room"}), 404))

    @app.post("/api/capi/new")
    def capi_new():
        b = body()
        return jsonify({"room": _new(b.get("cwd"), b.get("model"))})

    @app.post("/api/capi/delete")
    def capi_delete():
        try:
            _path(body().get("id", "")).unlink()
        except Exception:
            pass
        return jsonify({"ok": True})

    @app.post("/api/capi/settings")
    def capi_settings():
        b = body()
        r = _load(b.get("id", "")) or _new(b.get("cwd"), b.get("model"))
        if b.get("model") in MODELS:
            r["model"] = b["model"]
        if b.get("cwd"):
            r["cwd"] = _ok_cwd(b["cwd"])
        _save(r)
        return jsonify({"room": r})

    @app.post("/api/capi/stop")
    def capi_stop():
        with _lock:
            p = _procs.get(body().get("id", ""))
        if p and p.poll() is None:
            p.kill()
        return jsonify({"stopped": bool(p)})

    @app.post("/api/capi/turn")
    def capi_turn():
        b = body()
        text = (b.get("text") or "").strip()
        r = _load(b.get("id", ""))
        if not r:
            r = _new(b.get("cwd"), b.get("model"))
            r["id"] = re.sub(r"[^a-zA-Z0-9_-]", "", b.get("id") or "") or r["id"]
        if not text:
            return jsonify({"error": "empty"}), 400
        return Response((ndj(e) for e in run_turn(r, text)), mimetype="application/x-ndjson",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/api/capi/ask")
    def capi_ask():
        b = body()
        text = (b.get("text") or "").strip()
        if not text:
            return jsonify({"error": "empty"}), 400
        r = _load(b.get("id", "")) or _new(b.get("cwd"), b.get("model") or "claude-haiku-5-5")
        out, cost, err = [], 0.0, None
        for e in run_turn(r, text):
            if "text" in e:
                out.append(e["text"])
            if "cost" in e:
                cost = e["cost"]
            if "error" in e:
                err = e["error"]
        return jsonify({"answer": "\n\n".join(out), "cost": cost, "id": r["id"], "left": _credit_left(), "error": err})
