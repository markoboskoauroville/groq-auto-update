"""CAPI tab (17.11.2026; v17 18.11.2026: chats, provider radios Anthropic / Oxyy): chat with Claude Code on Marko's $100 API credit, the same run `capi` does.

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


def _new(cwd=None, model=None, queen="off"):
    room = {"id": secrets.token_hex(5), "title": "CAPI chat", "provider": get_provider(), "model": model if model in MODELS else DEFAULT_MODEL, "gmodel": "", "queen": queen,
            "cwd": _ok_cwd(cwd), "session": str(uuid.uuid4()), "started": False, "total": 0.0, "messages": [],
            "created": time.time(), "updated": _now()}
    _save(room)
    return room


def _ok_cwd(cwd):
    home = str(Path.home())
    p = os.path.realpath(os.path.expanduser(cwd or DEFAULT_CWD))
    return p if (p == home or p.startswith(home + os.sep)) and os.path.isdir(p) else DEFAULT_CWD


# ---------------------------------------------------------------- Queen bypass (v25)
# Marko, 18.11.2026: CAPI chats on Anthropic (local Claude Code) and Google Cloud (Gemini) are a bypass of Queen: no Queen system
# prompt or queen_skills, no Groq/qwen call, nothing recorded for her training. This module never imports app.py's chat path,
# training_log, skills or Groq; the only Queen-side doors are guarded here: POST /api/capi/ask (her `capi` skill) refuses a chat
# whose switch is QUEEN: OFF (the default), and every CAPI thread sets training_log.TURN.bypass so training_log.record() drops
# anything written from it. Per chat: room["queen"] = "off" | "on" (POST /api/capi/queen {id,on}).
def _bypass_queen():
    try:
        import training_log
        training_log.TURN.bypass = True
    except Exception:
        pass


def _queen_on(room):
    return (room or {}).get("queen") == "on"


# ---------------------------------------------------------------- providers (v17)
# Marko, 18.11.2026: radio buttons at the top for all API providers, each with its key (gear), credit and cost.
# anthropic = api.anthropic.com, key sk-ant-..., credit = tools/api_credit.py (the $100 promotional credit).
# oxyy      = Oxyy (oxyy.ai), a unified gateway: Anthropic Messages API at the bare host https://api.oxyy.ai (x-api-key or
#             Bearer), OpenAI format at /v1; key shape 4 chars + "-" + 64 chars; NO balance endpoint (probed 18.11.2026), so
#             the credit is a local ledger from a starting balance Marko enters; Oxyy bills Claude at 40% of Anthropic's list
#             price (60% off), so the Claude Code cost is multiplied by OXYY_FACTOR (an estimate).
PROVIDERS = {
    "anthropic": {"name": "Anthropic", "key_file": Path.home() / ".groq" / "capi_key", "name_hint": "100dolara",
                  "base_url": "", "factor": 1.0},
    "oxyy": {"name": "Oxyy", "key_file": Path.home() / ".groq" / "capi_key_oxyy", "name_hint": "oxyy",
             "base_url": "https://api.oxyy.ai", "factor": 0.4},
}
PROVIDERS["gcloud"] = {"name": "Google Cloud", "key_file": None, "name_hint": "CGP_free_credits", "base_url": "", "factor": 1.0}
PROVIDER_FILE = Path.home() / ".groq" / "capi_provider.json"
OXYY_BALANCE = Path.home() / ".groq" / "capi_oxyy_balance.json"      # {"start_usd": 5.0, "at": epoch}
OXYY_LEDGER = Path.home() / ".cache" / "oxyy-ledger.jsonl"
KEY_FILE = PROVIDERS["anthropic"]["key_file"]      # the gear's key (0600, never printed, never in git)


def get_provider():
    try:
        p = json.loads(PROVIDER_FILE.read_text()).get("provider")
        return p if p in PROVIDERS else "anthropic"
    except Exception:
        return "anthropic"


def set_provider(p):
    if p not in PROVIDERS:
        return False
    PROVIDER_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROVIDER_FILE.write_text(json.dumps({"provider": p}))
    return True


def _anthropic_key_in(text):
    """The ONE key-by-shape reader (auto_updater.extract_multi_provider_keys): sk-ant-... found in any noisy text."""
    try:
        from auto_updater import extract_multi_provider_keys
        keys = extract_multi_provider_keys(text or "").get("anthropic") or []
    except Exception:
        keys = re.findall(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b", text or "")
    return keys[0] if keys else ""


def _oxyy_key_in(text):
    """Oxyy key by shape: 4 characters, a dash, 64 characters (69 in all); any other text around it is fine."""
    m = re.search(r"(?<![A-Za-z0-9_-])[A-Za-z0-9]{4}-[A-Za-z0-9_-]{64}(?![A-Za-z0-9_-])", text or "")
    return m.group(0) if m else ""


def _key_in(provider, text):
    return _oxyy_key_in(text) if provider == "oxyy" else _anthropic_key_in(text)


def _key(provider=None):
    """The gear's file first (~/.groq/capi_key[_oxyy]), else the ~/Downloads/API file whose name has the hint."""
    provider = provider or get_provider()
    P = PROVIDERS[provider]
    if provider == "gcloud":                 # v24: read at runtime from the CGP_free_credits file by gcloud_chat, never stored here
        import gcloud_chat
        return "set" if gcloud_chat.has_key() else ""
    try:
        k = _key_in(provider, P["key_file"].read_text(errors="ignore"))
        if k:
            return k
    except Exception:
        pass
    for f in glob.glob(str(Path.home() / "Downloads" / "API" / "*")):
        if P["name_hint"] in os.path.basename(f).lower():
            k = _key_in(provider, open(f, errors="ignore").read())
            if k:
                return k
    return ""


def load_key_file(path, provider=None):
    """The gear: read a file Marko picked, take that provider's key out of it by shape, keep it in ~/.groq/capi_key[_oxyy]."""
    provider = provider if provider in PROVIDERS else get_provider()
    if provider == "gcloud":
        return {"ok": False, "error": "Google Cloud reads its key by itself from the CGP_free_credits file in Downloads/API."}
    f = Path(os.path.expanduser(path or ""))
    if not f.is_file():
        return {"ok": False, "error": "no such file"}
    if f.stat().st_size > 2_000_000:
        return {"ok": False, "error": "file too big for a key file"}
    k = _key_in(provider, f.read_text(errors="ignore"))
    if not k:
        return {"ok": False, "error": "No Anthropic API key (sk-ant-...) in that file." if provider == "anthropic"
                else "No Oxyy API key (4 characters, a dash, 64 characters) in that file."}
    kf = PROVIDERS[provider]["key_file"]
    kf.parent.mkdir(parents=True, exist_ok=True)
    tmp = kf.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as w:
        w.write(k + "\n")
    os.replace(tmp, kf)
    return {"ok": True, "last4": k[-4:], "provider": provider}


def _oxyy_spent():
    t0 = 0
    try:
        t0 = float(json.loads(OXYY_BALANCE.read_text()).get("at") or 0)
    except Exception:
        pass
    s = 0.0
    try:
        for line in open(OXYY_LEDGER):
            try:
                r = json.loads(line)
                if r.get("at", 0) >= t0:
                    s += float(r.get("cost") or 0)
            except Exception:
                pass
    except Exception:
        pass
    return s


def set_oxyy_balance(usd):
    OXYY_BALANCE.parent.mkdir(parents=True, exist_ok=True)
    OXYY_BALANCE.write_text(json.dumps({"start_usd": float(usd), "at": time.time()}))


def _credit_left(provider=None):
    provider = provider or get_provider()
    if provider == "gcloud":
        import gcloud_chat
        return gcloud_chat.left()
    if provider == "oxyy":
        try:
            start = float(json.loads(OXYY_BALANCE.read_text()).get("start_usd"))
        except Exception:
            return None                    # no endpoint, no starting balance told: honestly unknown
        return round(max(0.0, start - _oxyy_spent()), 4)
    try:
        sys.path.insert(0, str(Path.home() / "Developer" / "claude-code" / "tools"))
        import api_credit
        return round(api_credit.left(), 2)
    except Exception:
        return None


def _ledger(cost, prompt, error=False, provider="anthropic"):
    if provider == "oxyy":
        OXYY_LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with open(OXYY_LEDGER, "a") as f:
            f.write(json.dumps({"at": time.time(), "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "cost": cost,
                                "prompt": prompt[:70], "error": error}) + "\n")
        return
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


def _stale(room):
    """No process: a prompt left 'sent' or 'received' (Queen restarted mid-answer) is a failed one."""
    for m in (room or {}).get("messages", []):
        if m.get("role") == "marko" and m.get("status") in ("sent", "received"):
            m["status"] = "failed"
            m["reason"] = "the process ended before the answer (Queen restarted?)"
    return room


class Conv:
    """One conversation's background claude process and its reader thread."""

    def __init__(self, room):
        self.room = _stale(room)
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
        self.pending = None       # the marko message being answered: status sent -> received -> done | failed
        self.pair_run = None      # v26: the MASTER / SLAVE run of this chat (pair_chat.PairRun) while it works

    def save(self):
        with self.lock:
            self.room["updated"] = _now()
            _save(self.room)

    def running(self):
        g = getattr(self, "gthread", None)
        pr = getattr(self, "pair_run", None)
        return bool((self.proc and self.proc.poll() is None) or (g and g.is_alive()) or (pr and pr.alive()))

    def start(self):
        with self.lock:
            if self.running():
                return True
            if get_provider() == "gcloud":      # v24: Google Cloud is plain HTTP calls, no process to start
                return True
            r = self.room
            prov = r.get("provider") if r.get("provider") in PROVIDERS else "anthropic"
            r["provider"] = prov
            key = _key(prov)
            if not key:
                self.error = "no " + PROVIDERS[prov]["name"] + " key: use the gear to pick its file"
                return False
            if not os.path.isdir(r.get("cwd") or ""):
                r["cwd"] = DEFAULT_CWD
            if _session_file(r.get("session")):
                sess = ["--resume", r["session"]]
                self.primer = False
            else:
                r["session"] = str(uuid.uuid4())
                sess = ["--session-id", r["session"]]
                self.primer = any(m.get("role") in ("marko", "claude") for m in r.get("messages", []))
            env = _claude_env(prov, key)
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

    def send(self, text, files=None, pair=None):
        """pair: a dict {master, slave, max_rounds?, cap_usd?} for this one turn (Queen's ask); None = the saved switch."""
        import pair_chat
        st = pair_chat.status(_key, PROVIDERS, pair) if pair is not None else pair_chat.status(_key, PROVIDERS)
        if st["active"]:
            return self._send_pair(text, files, st)
        with self.lock:
            want = get_provider()          # v17: the radio decides; a chat on the other provider restarts on this one
            if self.room.get("provider") != want:
                if self.room.get("provider") == "gcloud" and want != "gcloud":
                    self.force_primer = True       # v25: Gemini turns happened outside Claude's session: send the history again
                if self.running():
                    self.stop()
                    self.proc = None
                self.room["provider"] = want
                self.stopping = False
            if want == "gcloud":
                return self._send_gcloud(text, files)
            if not self.start():
                return False
            if getattr(self, "force_primer", False):
                self.primer = any(m.get("role") in ("marko", "claude") for m in self.room.get("messages", []))
                self.force_primer = False
            r = self.room
            if self.pending is not None:      # a turn still open (should not happen: the window waits) is closed first
                self._mark("done")
            r["messages"].append({"role": "marko", "text": text, "status": "sent"})
            self.pending = r["messages"][-1]
            if r.get("title") in ("CAPI chat", "", None):
                r["title"] = text.strip().splitlines()[0][:48] or "CAPI chat"
            payload = text
            if files:                                   # v24: attachments for Claude Code (image / document blocks, text inlined)
                import gcloud_chat
                prepared, err = gcloud_chat.prepare_files(files)
                if err:
                    self.pending["status"] = "failed"
                    self.pending["reason"] = err
                    self.pending = None
                    self.busy = False
                    self.error = err
                    self.save()
                    return False
                self.pending["files"] = [f["name"] for f in prepared]
                payload = gcloud_chat._claude_content(text, prepared)
            if self.primer and isinstance(payload, list):
                payload.insert(0, {"type": "text", "text": "(earlier conversation stored by Queen; session file gone)"})
                self.primer = False
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
                self._mark("failed", self.error)
                self.save()
                return False
            return True

    def _send_pair(self, text, files, cfg):
        """v26: MASTER / SLAVE turn in a thread; every step lands in the chat file as a labelled message."""
        import pair_chat
        with self.lock:
            if self.running() and self.busy:
                self.error = "still answering"
                return False
            if self.proc and self.proc.poll() is None:      # the single-mode Claude process is not needed meanwhile
                self.stop()
                self.proc = None
            self.stopping = False
            r = self.room
            if self.pending is not None:
                self._mark("done")
            msg = {"role": "marko", "text": text, "status": "sent",
                   "pair": f'{pair_chat.NAMES[cfg["master"]]} → {pair_chat.NAMES[cfg["slave"]]}'}
            if files:
                msg["files"] = [f.get("name", "file") for f in files]
            r["messages"].append(msg)
            self.pending = msg
            if r.get("title") in ("CAPI chat", "", None):
                r["title"] = text.strip().splitlines()[0][:48] or "CAPI chat"
            self.force_primer = True            # single mode later: Claude's own session did not see the pair turn
            self.error = ""
            self.busy = True
            self.prompt = text
            self.save()

            def model_for(p):
                if p == "gcloud":
                    import gcloud_chat
                    g = r.get("gmodel") or ""
                    if not g or gcloud_chat.is_vertex(g):
                        g = gcloud_chat.default_gemini(gcloud_chat.gemini_models())
                    return g
                return r.get("model") or DEFAULT_MODEL
            deps = {"key": _key, "providers": PROVIDERS, "ledger": _ledger, "env_for": _claude_env, "model_for": model_for,
                    "root": ROOT}
            self.pair_run = pair_chat.PairRun(self, text, files, cfg, deps)
            self.pair_run.thread = threading.Thread(target=self.pair_run.run, daemon=True)
            self.pair_run.thread.start()
            return True

    def _send_gcloud(self, text, files):
        """Google Cloud turn (v24): one HTTP call in a thread; the answer lands in the chat file like any other."""
        import gcloud_chat
        r = self.room
        if self.running() and self.busy:
            self.error = "still answering"
            return False
        prepared, err = gcloud_chat.prepare_files(files or [])
        hist = [(m["role"], m["text"] + (f' [attached: {", ".join(m["files"])}]' if m.get("files") else ""))
                for m in r["messages"] if m.get("role") in ("marko", "claude")]
        model = r.get("gmodel") or ""
        if gcloud_chat.is_vertex(model) and not gcloud_chat.VERTEX_ENABLED:
            model = ""                                    # v25: Gemini only
        if not model:
            model = gcloud_chat.default_gemini(gcloud_chat.gemini_models())
            r["gmodel"] = model
        if self.pending is not None:
            self._mark("done")
        msg = {"role": "marko", "text": text, "status": "sent"}
        if prepared:
            msg["files"] = [f["name"] for f in prepared]
        r["messages"].append(msg)
        self.pending = msg
        if r.get("title") in ("CAPI chat", "", None):
            r["title"] = text.strip().splitlines()[0][:48] or "CAPI chat"
        self.error = ""
        if err:                                           # too big / unsupported: one plain line, nothing sent
            self.error = err
            self._mark("failed", err)
            self.save()
            return False
        self.busy = True
        self.prompt = text
        self.save()
        self.gthread = threading.Thread(target=self._gworker, args=(model, hist, text, prepared), daemon=True)
        self.gthread.start()
        return True

    SOLO_SYS = ("You are Gemini, running through Google Cloud inside Queen's CAPI tab on Marko's Mac. Never call yourself Claude. You have the tools list_files, read_file, write_file and run_shell, confined to the chat's folder. Use them; never say you cannot access the computer or files. Plan, act, test by running, then report the real command output. Never print keys.")

    def _gworker(self, model, hist, text, files):
        import gcloud_chat
        _bypass_queen()
        self._mark("received")
        import gemini_hands as H
        cwd, _why = H.folder_ok(self.room.get("cwd") or "")
        if cwd:
            try:
                gh = [("user" if r == "marko" else "model", t) for r, t in hist]
                ans, cost, _n = H.agent_turn(model, self.SOLO_SYS, gh, text, cwd, label="solo gemini")
                res = {"text": ans, "cost": cost}
            except Exception as exc:
                res = {"error": str(exc)}
        else:
            res = gcloud_chat.run(model, hist, text, files)
            if "error" not in res:
                res["text"] = "No working folder is set for this chat, so I have no hands.\n\n" + res["text"]
        with self.lock:
            if "error" in res:
                self.error = res["error"]
                self._mark("failed", res["error"])
            else:
                self.room["messages"].append({"role": "claude", "text": res["text"], "cost": res["cost"], "model": model, "who": "GEMINI"})
                self.room["total"] = round(self.room.get("total", 0.0) + res["cost"], 4)
                self._mark("done")
            self.busy = False
            self.turns += 1
            self.save()
            self.done.notify_all()

    def _mark(self, status, reason=""):
        """Status of the prompt being answered (v13): received once claude shows it took it, done / failed at the end."""
        m = self.pending
        if m is None:
            return
        if status == "received" and m.get("status") != "sent":
            return
        m["status"] = status
        if reason:
            m["reason"] = reason[:300]
        if status in ("done", "failed"):
            self.pending = None

    def stop(self):
        pr = getattr(self, "pair_run", None)
        paired = bool(pr and pr.alive())
        if paired:
            pr.stop()                          # v26: STOP stops both sides of a pair at once (the running one is killed)
            pr.thread.join(timeout=8)
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
        return bool(p) or paired

    def _read(self, p):  # noqa: C901
        try:
            for line in p.stdout:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                t = d.get("type")
                with self.lock:
                    if t in ("assistant", "user", "result") or (t == "system" and d.get("subtype") == "init"):
                        if self.pending is not None and self.pending.get("status") == "sent":
                            self._mark("received")
                            self.save()
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
                        prov = self.room.get("provider", "anthropic")
                        cost = round(max(cost, 0.0) * PROVIDERS.get(prov, PROVIDERS["anthropic"])["factor"], 6)
                        if cost:
                            _ledger(cost, self.prompt or "(background)", provider=prov)
                            self.room["total"] = round(self.room.get("total", 0.0) + cost, 4)
                            for m in reversed(self.room["messages"]):
                                if m["role"] == "claude":
                                    m["cost"] = round(m.get("cost", 0) + cost, 4)
                                    break
                                if m["role"] == "marko":
                                    break
                        if d.get("is_error"):
                            self.error = str(d.get("result"))[:300]
                            self._mark("failed", self.error)
                        else:
                            self._mark("done")
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
                if self.pending is not None:
                    self._mark("failed", "stopped by STOP" if self.stopping else (self.error or "the process ended"))
                self.save()
                self.done.notify_all()

    def state(self):
        with self.lock:
            return {"running": self.running(), "busy": self.busy and self.running(), "error": self.error}



def _claude_env(prov, key):
    """The environment of a Claude Code run on this provider (session variables removed, the key set, Oxyy's base URL)."""
    env = {k: v for k, v in os.environ.items() if not (k.startswith("CLAUDECODE") or k.startswith("CLAUDE_CODE_"))}
    env["ANTHROPIC_API_KEY"] = key
    for v in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN"):
        env.pop(v, None)
    if PROVIDERS[prov]["base_url"]:
        env["ANTHROPIC_BASE_URL"] = PROVIDERS[prov]["base_url"]    # Oxyy speaks the Messages API at the bare host
    return env


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
    r = _stale(_load(rid))
    return r, {"running": False, "busy": False, "error": ""}


def _stop_all():
    for c in list(_convs.values()):
        c.stop()


atexit.register(_stop_all)


def run_turn(room, text, files=None, pair=None):
    """Streaming form of one turn (the old /api/capi/turn): send, then yield what lands until the answer is done."""
    c = _conv(room["id"])
    if not c:
        yield {"error": "no such conversation"}
        return
    with c.lock:
        n = len(c.room["messages"]) + 1
        if not c.send(text, files, pair):
            yield {"error": c.error or "could not send"}
            return
    while True:
        with c.lock:                        # never hold the lock across a yield: the reader thread must go on
            c.done.wait(timeout=0.5)
            new = [dict(m) for m in c.room["messages"][n:]]
            n += len(new)
            busy = c.busy
        for m in new:
            if m["role"] in ("master", "slave"):      # v26: a pair message, labelled with speaker and role
                yield {"text": m["text"], "role": m["role"], "speaker": m.get("speaker"), "kind": m.get("kind"),
                       "label": m.get("label", ""), "model": m.get("model", ""), "cost": m.get("cost", 0.0),
                       **({"verdict": m["verdict"]} if m.get("verdict") else {})}
            elif m["role"] == "pair":
                yield {"pair": m["text"], "end": m.get("end", ""), "pair_cost": m.get("cost", 0.0)}
            elif m["role"] == "claude":
                yield {"text": m["text"]}
            else:
                yield {"tool": m["text"]}
        if not busy:
            break
    with c.lock:
        cost = 0.0
        for m in reversed(c.room["messages"]):
            if m["role"] == "marko":
                break
            if m["role"] in ("claude", "pair"):
                cost = m.get("cost", 0.0)
                break
        err = c.error
        total = c.room.get("total", 0.0)
    if err:
        yield {"error": err}
    yield {"cost": round(cost, 4), "total": total, "left": _credit_left(), "provider": get_provider()}
    yield {"done": 1}


# Haiku 5.5 list price per million tokens (input, output); Oxyy bills 40% of it (60% off).
HAIKU = "claude-haiku-5-5"
HAIKU_RATE = (0.10, 0.50)


def autoname(room):
    """AUTOMATIC NAME (v17): one cheap Haiku call on the selected provider reads the chat (last ~8k chars) and answers a
    2-5 word title. Returns {title, cost, provider} or {error}. The cost is booked like any other prompt."""
    import urllib.request
    prov = get_provider()
    P = PROVIDERS[prov]
    if prov == "gcloud":                    # v25: Gemini names the chat (flash-lite, a few tokens)
        import gcloud_chat
        hist = "\n\n".join(("Marko: " if m["role"] == "marko" else "AI: ") + m["text"]
                            for m in room.get("messages", []) if m.get("role") in ("marko", "claude"))
        if not hist.strip():
            return {"error": "the chat is empty"}
        res = gcloud_chat.run(next((m for m in gcloud_chat.gemini_models() if "flash-lite" in m and "preview" not in m), gcloud_chat.default_gemini(gcloud_chat.gemini_models())),
                              [], "Read this chat and answer with ONLY a title of 2 to 5 words that says what it is about. No quotes, no full stop.\n\n" + hist[-8000:], [])
        if "error" in res:
            return {"error": res["error"]}
        title = re.sub(r"[\"'`*#\n]+", " ", res["text"]).strip().rstrip(".")[:60].strip()
        return {"title": title, "cost": res["cost"], "provider": prov, "left": _credit_left(prov)} if title else {"error": "Gemini gave no title"}
    key = _key(prov)
    if not key:
        return {"error": "no " + P["name"] + " key: use the gear to pick its file"}
    hist = "\n\n".join(("Marko: " if m["role"] == "marko" else "Claude: ") + m["text"]
                        for m in room.get("messages", []) if m.get("role") in ("marko", "claude"))
    if not hist.strip():
        return {"error": "the chat is empty"}
    prompt = ("Read this chat and answer with ONLY a title of 2 to 5 words that says what it is about. "
              "No quotes, no full stop.\n\n" + hist[-8000:])
    url = (P["base_url"] or "https://api.anthropic.com") + "/v1/messages"
    req = urllib.request.Request(url, method="POST", headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json", "user-agent": "queen/17"},
        data=json.dumps({"model": HAIKU, "max_tokens": 20, "messages": [{"role": "user", "content": prompt}]}).encode())
    try:
        with urllib.request.urlopen(req, timeout=40) as x:
            j = json.loads(x.read().decode())
    except Exception as exc:
        body = ""
        try:
            body = exc.read().decode()[:200]            # HTTPError body: the service's message, never the key
        except Exception:
            pass
        return {"error": (f"{P['name']} did not answer: {body or exc}").replace(key, "***")[:300]}
    text = "".join(b.get("text", "") for b in j.get("content") or [] if b.get("type") == "text")
    title = re.sub(r"[\"'`*#\n]+", " ", text).strip().rstrip(".")[:60].strip()
    u = j.get("usage") or {}
    cost = (u.get("input_tokens", 0) * HAIKU_RATE[0] + u.get("output_tokens", 0) * HAIKU_RATE[1]) / 1e6 * P["factor"]
    cost = round(cost, 6)
    if cost:
        _ledger(cost, "autoname", provider=prov)
    if not title:
        return {"error": "Haiku gave no title", "cost": cost}
    return {"title": title, "cost": cost, "provider": prov, "left": _credit_left(prov)}


def _credit_info():
    cur = get_provider()
    provs = []
    for pid, P in PROVIDERS.items():
        provs.append({"id": pid, "name": P["name"], "has_key": bool(_key(pid)), "left": _credit_left(pid),
                      "estimate": pid in ("oxyy", "gcloud")})
    left = _credit_left(cur)
    note = ""
    if cur == "oxyy" and left is None:
        note = "Oxyy has no balance endpoint: tell Queen your starting balance (click the credit) and she counts down from it."
    elif cur == "oxyy":
        note = "Oxyy has no balance endpoint: the credit is your starting balance minus what Queen booked (estimate)."
    if cur == "gcloud":
        import gcloud_chat
        c = gcloud_chat.config()
        note = (f"Google Cloud free credit, project antigravity-cloud-offload: ${c['start_usd']:.2f} on {c['read']} (Billing page) minus "
                f"Queen's ledger since; expires {gcloud_chat.expiry_text()}. The number is an estimate from token prices.")
    expires = ""
    if cur == "gcloud":
        import gcloud_chat
        expires = gcloud_chat.expiry_text()
    return {"expires": expires, "left": left, "has_key": bool(_key(cur)), "provider": cur, "name": PROVIDERS[cur]["name"],
            "providers": provs, "note": note}


def register(app):
    @app.before_request
    def _capi_bypass_flag():
        # server threads are reused: the flag is set for /api/capi/* and cleared for everything else
        try:
            import training_log
            training_log.TURN.bypass = request.path.startswith("/api/capi/")
        except Exception:
            pass

    def ndj(o):
        return json.dumps(o, ensure_ascii=False) + "\n"

    def body():
        return request.get_json(silent=True) or {}

    @app.get("/api/capi/credit")
    def capi_credit():
        return jsonify(_credit_info())

    @app.post("/api/capi/provider")
    def capi_provider():
        p = body().get("provider")
        if not set_provider(p):
            return jsonify({"ok": False, "error": "unknown provider"}), 400
        return jsonify({"ok": True, **_credit_info()})

    @app.post("/api/capi/oxyy_balance")
    def capi_oxyy_balance():
        try:
            set_oxyy_balance(float(body().get("usd")))
        except Exception:
            return jsonify({"ok": False, "error": "a number in dollars"}), 400
        return jsonify({"ok": True, **_credit_info()})

    @app.get("/api/capi/gcloud_models")
    def capi_gcloud_models():
        import gcloud_chat
        return jsonify(gcloud_chat.models_info())

    @app.post("/api/capi/gcloud_balance")
    def capi_gcloud_balance():
        import gcloud_chat
        try:
            gcloud_chat.set_balance(float(body().get("usd")))
        except Exception:
            return jsonify({"ok": False, "error": "a number in dollars"}), 400
        return jsonify({"ok": True, **_credit_info()})

    @app.get("/api/capi/pair")
    def capi_pair_get():
        import pair_chat
        st = pair_chat.status(_key, PROVIDERS)
        st["models"] = {"master_hint": "the chat's MODEL (Claude) or Gemini model (gmodel, list: GET /api/capi/gcloud_models)",
                        "slave": [
            {"id": m, "tier": t, "in": i, "out": o} for m, t, i, o in pair_chat.slave_catalog(st["slave"])]} if st["active"] else {}
        return jsonify(st)

    @app.post("/api/capi/pair")
    def capi_pair_set():
        """{master?, slave?, max_rounds?, cap_usd?} ("" = off). -> the status (active, note, label)."""
        import pair_chat
        pair_chat.set_pair(body(), PROVIDERS)
        return jsonify({"ok": True, **pair_chat.status(_key, PROVIDERS)})

    @app.post("/api/capi/queen")
    def capi_queen():
        """{id,on:true|false}: the chat's QUEEN switch. Off (default) = Queen may not use this chat (her capi skill is refused)."""
        b = body()
        c = _conv(b.get("id", ""))
        if not c:
            return jsonify({"ok": False, "error": "no such chat"}), 404
        with c.lock:
            c.room["queen"] = "on" if b.get("on") else "off"
            c.save()
        return jsonify({"ok": True, "queen": c.room["queen"]})

    @app.post("/api/capi/key")
    def capi_key():
        """{path} of a key file -> {ok, last4} or {ok:false, error}. The key itself never travels or prints."""
        b = body()
        return jsonify(load_key_file(b.get("path", ""), b.get("provider")))

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
                              "updated": r.get("updated", 0), "created": r.get("created") or r.get("updated", 0),
                              "provider": r.get("provider", "anthropic"), "model": r.get("model", ""), **st})
            except Exception:
                pass
        # v17 bug fix: the list was sorted by "updated", which every answer bumps, so a new chat fell below any chat that
        # was answering and the order changed on each poll. Now by creation time, newest first, id as the tie-break: a new
        # chat is always at the top and nothing moves afterwards.
        rooms.sort(key=lambda r: (-float(r["created"]), r["id"]))
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
            if isinstance(b.get("gmodel"), str) and re.fullmatch(r"[A-Za-z0-9@._-]{3,80}", b["gmodel"]):
                r["gmodel"] = b["gmodel"]
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

    @app.post("/api/capi/rename")
    def capi_rename():
        """{id,title}: the chat's name, kept in its file. The list is ordered by creation, so a rename never moves it."""
        b = body()
        title = re.sub(r"\s+", " ", (b.get("title") or "")).strip()[:80]
        c = _conv(b.get("id", ""))
        if not c or not title:
            return jsonify({"ok": False, "error": "no such chat" if not c else "empty name"}), 400
        with c.lock:
            c.room["title"] = title
            c.save()
        return jsonify({"ok": True, "title": title})

    @app.post("/api/capi/autoname")
    def capi_autoname():
        """{id} -> {title, cost}: suggests a name only; the window fills the field and Marko saves it (rename)."""
        r, _ = _room(body().get("id", ""))
        if not r:
            return jsonify({"error": "no such chat"}), 404
        return jsonify(autoname(r))

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
        ok = c.send(text, b.get("files") or None)
        return jsonify({"ok": ok, **c.state(), **({"error": c.error} if not ok and c.error else {})})

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
        r = _load(b.get("id", "")) or _new(b.get("cwd"), b.get("model") or "claude-haiku-5-5", queen="on")   # made by her: hers
        # The caller may always (re)choose the models of this chat: gmodel = a Google Cloud (Gemini) master's model, model = a Claude
        # master's model. Before, an existing chat kept its first gmodel and a later one was silently ignored.
        want_g = b.get("gmodel") if isinstance(b.get("gmodel"), str) and re.fullmatch(r"[A-Za-z0-9@._-]{3,80}", b["gmodel"]) else ""
        want_m = b.get("model") if b.get("model") in MODELS else ""
        if (want_g and want_g != r.get("gmodel")) or (want_m and want_m != r.get("model")):
            c0 = _conv(r["id"])
            with c0.lock:
                if want_g:
                    c0.room["gmodel"] = want_g
                if want_m:
                    c0.room["model"] = want_m
                c0.save()
            r = c0.room
        pair = None
        if b.get("master") or b.get("slave"):        # v26: a pair turn for this one ask (the saved switch is not changed)
            import pair_chat
            pair = {k: b.get(k) for k in ("master", "slave", "max_rounds", "cap_usd") if b.get(k) is not None}
            pair = {**pair_chat.get_pair(), **pair}
            st = pair_chat.status(_key, PROVIDERS, pair)
            if not st["active"]:
                return jsonify({"error": st["note"], "answer": "", "id": r["id"]}), 400
        if not _queen_on(r):
            return jsonify({"error": "This chat has QUEEN: OFF, so Queen may not use it. Marko switches it on in the chat's header.",
                            "answer": "", "id": r["id"]}), 403
        out, cost, err, end = [], 0.0, None, ""
        for e in run_turn(r, text, None, pair):
            if "text" in e:
                out.append((f'[{e["label"]}]\n' if e.get("label") else "") + e["text"])
            if "pair" in e:
                out.append(e["pair"])
                end = e.get("end", "")
            if "cost" in e:
                cost = e["cost"]
            if "error" in e:
                err = e["error"]
        return jsonify({"answer": "\n\n".join(out), "cost": cost, "id": r["id"], "left": _credit_left(), "error": err,
                        **({"pair_end": end} if pair else {})})
