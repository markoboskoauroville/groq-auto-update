"""CAPI tab (17.11.2026): chat with Claude Code on Marko's $100 API credit, the same run `capi` does.

Marko: "can queen be used as capi ... add capi tab to queen software so i can have nicer ui". Then (v12, 17.11.2026):
"Instead of room, make a new conversation and conversations ... each conversation should start its own process ... running
in the background as a parallel process ... start, stop ... close".

CONVERSATIONS: each one is its own long-lived background process
`claude -p --model M --permission-mode auto --session-id|--resume <uuid> --input-format stream-json
 --output-format stream-json --verbose` (ANTHROPIC_API_KEY from the ~/Downloads/API file named *100dolara*, never printed).
A reader thread stores every answer in the conversation file as it arrives, whether the window shows it or not, so several
conversations run in parallel. START = spawn the process (resume the Claude session: it reads the whole history), STOP =
kill it (history kept), CLOSE = stop + delete the file and its Claude session file. After a backend restart nothing runs;
sending to a stopped conversation starts it. Every result is written to ~/.cache/claude-api-ledger.jsonl (api_credit).
total_cost_usd in a result is cumulative for the process: the ledger books the difference.

Routes (/api/capi/): GET list | get?id= | credit | folders ; POST new {cwd?,model?} | settings {id,model,cwd} |
  start {id} | stop {id} | close {id} (= delete) | send {id,text} -> {ok} at once (the answer lands in the file) |
  turn {id,text} -> NDJSON {"text":..} {"tool":..} {"cost":c,"total":t,"left":l} {"error":..} {"done":1} |
  ask {text,cwd?,model?,id?} -> JSON {answer,cost,id} (waits, for Queen's skill capi.md) |
  key {path} -> {ok,last4} (v13 gear: the key is taken out of the file by shape, kept in ~/.groq/capi_key 0600)
Files: ~/.groq/capi/<id>.json {id,title,model,cwd,session,started,total,messages:[{role:marko|claude|tool,text,cost?}]}
  (the CAPI rooms of v11 are the same files: they are the conversations now, nothing to migrate)
"""
from __future__ import annotations

import atexit
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


KEY_FILE = Path.home() / ".groq" / "capi_key"      # the gear's key (0600, never printed, never in git)


def _anthropic_key_in(text):
    """The ONE key-by-shape reader (auto_updater.extract_multi_provider_keys): sk-ant-... found in any noisy text."""
    try:
        from auto_updater import extract_multi_provider_keys
        keys = extract_multi_provider_keys(text or "").get("anthropic") or []
    except Exception:
        keys = re.findall(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b", text or "")
    return keys[0] if keys else ""


def _key():
    """The gear's file first (~/.groq/capi_key), else the ~/Downloads/API file named *100dolara*."""
    try:
        k = _anthropic_key_in(KEY_FILE.read_text(errors="ignore"))
        if k:
            return k
    except Exception:
        pass
    for f in glob.glob(str(Path.home() / "Downloads" / "API" / "*")):
        if "100dolara" in os.path.basename(f).lower():
            k = _anthropic_key_in(open(f, errors="ignore").read())
            if k:
                return k
    return ""


def load_key_file(path):
    """The gear: read a file Marko picked, take the Anthropic key out of it by shape, keep it in ~/.groq/capi_key."""
    f = Path(os.path.expanduser(path or ""))
    if not f.is_file():
        return {"ok": False, "error": "no such file"}
    if f.stat().st_size > 2_000_000:
        return {"ok": False, "error": "file too big for a key file"}
    k = _anthropic_key_in(f.read_text(errors="ignore"))
    if not k:
        return {"ok": False, "error": "No Anthropic API key (sk-ant-...) in that file."}
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = KEY_FILE.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as w:
        w.write(k + "\n")
    os.replace(tmp, KEY_FILE)
    return {"ok": True, "last4": k[-4:]}


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


def _session_file(session):
    """Claude Code's own transcript of this session, wherever its project folder is."""
    if not session:
        return None
    hits = glob.glob(str(Path.home() / ".claude" / "projects" / "*" / (session + ".jsonl")))
    return Path(hits[0]) if hits else None


class Conv:
    """One conversation's background claude process and its reader thread."""

    def __init__(self, room):
        self.room = room
        self.lock = threading.RLock()
        self.proc = None
        self.busy = False
        self.cum = 0.0            # cumulative cost reported by this process
        self.prompt = ""          # the turn being answered (ledger text)
        self.error = ""
        self.primer = False       # history exists but Claude's session is gone: send it with the first message
        self.done = threading.Condition(self.lock)
        self.turns = 0
        self.stopping = False     # STOP pressed: the end of the process is not an error

    def save(self):
        with self.lock:
            self.room["updated"] = _now()
            _save(self.room)

    def running(self):
        return bool(self.proc and self.proc.poll() is None)

    def start(self):
        with self.lock:
            if self.running():
                return True
            key = _key()
            if not key:
                self.error = "no key file (100dolara) in ~/Downloads/API"
                return False
            r = self.room
            if not os.path.isdir(r.get("cwd") or ""):
                r["cwd"] = DEFAULT_CWD
            if _session_file(r.get("session")):
                sess = ["--resume", r["session"]]
                self.primer = False
            else:
                r["session"] = str(uuid.uuid4())
                sess = ["--session-id", r["session"]]
                self.primer = any(m.get("role") in ("marko", "claude") for m in r.get("messages", []))
            env = {k: v for k, v in os.environ.items() if not (k.startswith("CLAUDECODE") or k.startswith("CLAUDE_CODE_"))}
            env["ANTHROPIC_API_KEY"] = key
            cmd = ["claude", "-p", "--model", r["model"], "--permission-mode", "auto", *sess,
                   "--input-format", "stream-json", "--output-format", "stream-json", "--verbose"]
            (ROOT / "logs").mkdir(parents=True, exist_ok=True)
            err = open(ROOT / "logs" / (r["id"] + ".err"), "w")
            try:
                self.proc = subprocess.Popen(cmd, cwd=r["cwd"], env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                             stderr=err, text=True, bufsize=1, start_new_session=True)
            except Exception as exc:
                self.error = f"could not start claude: {exc}"
                return False
            finally:
                err.close()
            self.cum = 0.0
            self.busy = False
            self.error = ""
            self.stopping = False
            _save(r)
            threading.Thread(target=self._read, args=(self.proc,), daemon=True).start()
            return True

    def send(self, text):
        with self.lock:
            if not self.start():
                return False
            r = self.room
            r["messages"].append({"role": "marko", "text": text})
            if r.get("title") in ("CAPI chat", "", None):
                r["title"] = text.strip().splitlines()[0][:48] or "CAPI chat"
            payload = text
            if self.primer:
                hist = "\n\n".join(f'{"Marko" if m["role"] == "marko" else "Claude"}: {m["text"]}'
                                    for m in r["messages"][:-1] if m.get("role") in ("marko", "claude"))
                payload = ("Our earlier conversation (stored by Queen; your own session file was gone), for context:\n\n"
                           + hist[-30000:] + "\n\n---\nNow: " + text)
                self.primer = False
            self.prompt = text
            self.busy = True
            self.error = ""
            self.save()
            try:
                self.proc.stdin.write(json.dumps({"type": "user", "message": {"role": "user", "content": payload}}) + "\n")
                self.proc.stdin.flush()
            except Exception as exc:
                self.busy = False
                self.error = f"the process did not take the message: {exc}"
                return False
            return True

    def stop(self):
        with self.lock:
            p = self.proc
            self.stopping = True
        if p and p.poll() is None:
            try:
                os.killpg(p.pid, 15)
            except Exception:
                p.terminate()
            try:
                p.wait(timeout=5)
            except Exception:
                try:
                    os.killpg(p.pid, 9)
                except Exception:
                    p.kill()
        return bool(p)

    def _read(self, p):
        try:
            for line in p.stdout:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                t = d.get("type")
                with self.lock:
                    if t == "assistant":
                        for b in (d.get("message") or {}).get("content") or []:
                            if b.get("type") == "text" and (b.get("text") or "").strip():
                                self.room["messages"].append({"role": "claude", "text": b["text"].strip()})
                            elif b.get("type") == "tool_use":
                                i = b.get("input") or {}
                                what = str(i.get("description") or i.get("command") or i.get("file_path") or i.get("pattern") or "")[:90]
                                self.room["messages"].append({"role": "tool", "text": f'{b.get("name", "tool")} {what}'.strip()})
                        self.save()
                    elif t == "result":
                        c = float(d.get("total_cost_usd") or 0)
                        cost = c - self.cum if c >= self.cum else c
                        self.cum = c
                        cost = round(max(cost, 0.0), 6)
                        if cost:
                            _ledger(cost, self.prompt or "(background)")
                            self.room["total"] = round(self.room.get("total", 0.0) + cost, 4)
                            for m in reversed(self.room["messages"]):
                                if m["role"] == "claude":
                                    m["cost"] = round(m.get("cost", 0) + cost, 4)
                                    break
                                if m["role"] == "marko":
                                    break
                        if d.get("is_error"):
                            self.error = str(d.get("result"))[:300]
                        self.room["started"] = True
                        self.busy = False
                        self.turns += 1
                        self.save()
                        self.done.notify_all()
        except Exception:
            pass
        with self.lock:
            if self.proc is p:
                was = self.busy
                self.busy = False
                if was and not self.error:
                    self.error = "stopped"
                if not self.error and not self.stopping:
                    try:                  # it ended by itself: the last real stderr line says why (not the ⚠ notices)
                        p.wait(timeout=5)
                        lines = [x for x in (ROOT / "logs" / (self.room["id"] + ".err")).read_text().splitlines()
                                 if x.strip() and not x.lstrip().startswith("⚠")]
                        if p.returncode not in (0, None) or lines:
                            self.error = (lines[-1] if lines else f"claude ended ({p.returncode})")[:300]
                    except Exception:
                        pass
                self.save()
                self.done.notify_all()

    def state(self):
        with self.lock:
            return {"running": self.running(), "busy": self.busy and self.running(), "error": self.error}


_convs: dict[str, Conv] = {}


def _conv(rid, create=True):
    """The live object of a conversation (made from its file on first use)."""
    with _lock:
        c = _convs.get(rid)
        if c or not create:
            return c
        room = _load(rid)
        if not room:
            return None
        c = _convs[rid] = Conv(room)
        return c


def _room(rid):
    c = _conv(rid, create=False)
    if c:
        with c.lock:
            return json.loads(json.dumps(c.room)), c.state()
    r = _load(rid)
    return r, {"running": False, "busy": False, "error": ""}


def _stop_all():
    for c in list(_convs.values()):
        c.stop()


atexit.register(_stop_all)


def run_turn(room, text):
    """Streaming form of one turn (the old /api/capi/turn): send, then yield what lands until the answer is done."""
    c = _conv(room["id"])
    if not c:
        yield {"error": "no such conversation"}
        return
    with c.lock:
        n = len(c.room["messages"]) + 1
        if not c.send(text):
            yield {"error": c.error or "could not send"}
            return
    while True:
        with c.lock:                        # never hold the lock across a yield: the reader thread must go on
            c.done.wait(timeout=0.5)
            new = [dict(m) for m in c.room["messages"][n:]]
            n += len(new)
            busy = c.busy
        for m in new:
            yield {"text": m["text"]} if m["role"] == "claude" else {"tool": m["text"]}
        if not busy:
            break
    with c.lock:
        cost = 0.0
        for m in reversed(c.room["messages"]):
            if m["role"] == "marko":
                break
            if m["role"] == "claude":
                cost = m.get("cost", 0.0)
                break
        err = c.error
        total = c.room.get("total", 0.0)
    if err:
        yield {"error": err}
    yield {"cost": round(cost, 4), "total": total, "left": _credit_left()}
    yield {"done": 1}


def register(app):
    def ndj(o):
        return json.dumps(o, ensure_ascii=False) + "\n"

    def body():
        return request.get_json(silent=True) or {}

    @app.get("/api/capi/credit")
    def capi_credit():
        return jsonify({"left": _credit_left(), "has_key": bool(_key())})

    @app.post("/api/capi/key")
    def capi_key():
        """{path} of a key file -> {ok, last4} or {ok:false, error}. The key itself never travels or prints."""
        return jsonify(load_key_file(body().get("path", "")))

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
                r, st = _room(f.stem)
                rooms.append({"id": r["id"], "title": r.get("title", ""), "count": len(r.get("messages", [])),
                              "updated": r.get("updated", 0), "model": r.get("model", ""), **st})
            except Exception:
                pass
        rooms.sort(key=lambda r: -r["updated"])
        return jsonify({"rooms": rooms, "conversations": rooms})

    @app.get("/api/capi/get")
    def capi_get():
        r, st = _room(request.args.get("id", ""))
        return (jsonify({"room": r, **st}) if r else (jsonify({"error": "no such conversation"}), 404))

    @app.post("/api/capi/new")
    def capi_new():
        b = body()
        return jsonify({"room": _new(b.get("cwd"), b.get("model")), "running": False, "busy": False, "error": ""})

    @app.post("/api/capi/delete")
    @app.post("/api/capi/close", endpoint="capi_close")
    def capi_delete():
        rid = re.sub(r"[^a-zA-Z0-9_-]", "", body().get("id", ""))
        c = _conv(rid, create=False)
        if c:
            c.stop()
        with _lock:
            _convs.pop(rid, None)
        r = _load(rid)
        sf = _session_file((r or {}).get("session"))
        for f in (_path(rid), ROOT / "logs" / (rid + ".err"), sf):
            try:
                if f:
                    f.unlink()
            except Exception:
                pass
        return jsonify({"ok": bool(r), "closed": rid})

    @app.post("/api/capi/settings")
    def capi_settings():
        b = body()
        c = _conv(b.get("id", ""))
        if not c:
            r = _new(b.get("cwd"), b.get("model"))
            c = _conv(r["id"])
        note = ""
        restart = False
        with c.lock:
            r = c.room
            if b.get("model") in MODELS and b["model"] != r.get("model"):
                r["model"] = b["model"]
                restart = c.running() and not c.busy
            if b.get("cwd"):
                want = _ok_cwd(b["cwd"])
                if want != r.get("cwd"):
                    if _session_file(r.get("session")):
                        note = "The folder is fixed once a conversation has started; NEW CONVERSATION for another folder."
                    else:
                        r["cwd"] = want
            c.save()
        if restart:
            c.stop()
            c.start()
        rr, st = _room(c.room["id"])
        return jsonify({"room": rr, **st, "notice": note})

    @app.post("/api/capi/start")
    def capi_start():
        c = _conv(body().get("id", ""))
        if not c:
            return jsonify({"error": "no such conversation"}), 404
        ok = c.start()
        return jsonify({"ok": ok, **c.state()})

    @app.post("/api/capi/stop")
    def capi_stop():
        c = _conv(body().get("id", ""), create=False)
        stopped = c.stop() if c else False
        return jsonify({"stopped": stopped, **(c.state() if c else {"running": False, "busy": False, "error": ""})})

    @app.post("/api/capi/send")
    def capi_send():
        b = body()
        text = (b.get("text") or "").strip()
        c = _conv(b.get("id", ""))
        if not c or not text:
            return jsonify({"error": "no such conversation" if not c else "empty"}), 400
        ok = c.send(text)
        return jsonify({"ok": ok, **c.state()})

    @app.post("/api/capi/turn")
    def capi_turn():
        b = body()
        text = (b.get("text") or "").strip()
        if not text:
            return jsonify({"error": "empty"}), 400
        r = _load(b.get("id", "")) or _new(b.get("cwd"), b.get("model"))
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
