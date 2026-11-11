"""Modern Groq Chatbot Server — Version 10.

Features:
- Groq Thunderstrike SVG Favicon & Brand Icon
- Noise-Tolerant Key Parser (extracts clean Groq keys from messy logs, configs, .env, json)
- Key Manager with interactive key pool, live failover, and key deletion
- Automatic Code Box Detection (detects 'in the code box' in prompts and activates code mode)
- Full SSE Streaming /api/chat & Backdoor /api/remote/send
- Dynamic Port Allocation (checks busy ports, binds first free)
- Live Groq API Spend Ledger & Token Tracking
- Raw Terminal Keyboard Controls ('q' to quit, 'c' for browser)
- Self-Update Payload Dispatcher (chunked code updates to work around token limits)
"""
import base64
import hashlib
import json
import logging
import os
import queue
import re
import select
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import warnings
import webbrowser
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path.home() / ".groq"))

from flask import Flask, Response, jsonify, request  # noqa: E402
from groq import APIError, AuthenticationError, Groq, PermissionDeniedError, RateLimitError  # noqa: E402
from waitress.server import create_server  # noqa: E402

HOME = Path.home() / ".groq"
KEYS_FILE = HOME / "keys.txt"
STATE_FILE = HOME / "key_state.json"
LEDGER_FILE = HOME / "spend_ledger.json"
PORT_FILE = HOME / "active_port"
URL_FILE = HOME / "app_url"
REPO_DIR = Path(__file__).resolve().parent          # qwen_app/ directory — may be source or installed copy
# Detect whether we are running from the git repo or the installed copy (~/.groq).
# Git operations and version tracking must always target the source repo.
_candidate_git_root = REPO_DIR.parent
if (_candidate_git_root / ".git").is_dir():
    GIT_ROOT = _candidate_git_root                  # running from source repo
else:
    # Installed copy: look for the source repo at the standard dev location
    _dev_repo = Path.home() / "Developer" / "groq_ai_studio"
    if (_dev_repo / ".git").is_dir():
        GIT_ROOT = _dev_repo
    else:
        GIT_ROOT = _candidate_git_root              # fallback — git ops will fail gracefully
UPDATE_DIR = HOME / "incoming_update"
CHATS_DIR = HOME / "chats"
VERSION_FILE = GIT_ROOT / "version.json"

# ── Version Management ──────────────────────────────
def load_app_version() -> int:
    """Read the current version number from version.json."""
    try:
        if VERSION_FILE.exists():
            data = json.loads(VERSION_FILE.read_text(encoding="utf-8"))
            return int(data.get("version", 1))
    except Exception:
        pass
    return 1

def bump_app_version(files_changed: list[str], message: str = "") -> int:
    """Increment the version, write version.json, return new version."""
    global VERSION
    try:
        if VERSION_FILE.exists():
            data = json.loads(VERSION_FILE.read_text(encoding="utf-8"))
        else:
            data = {"version": 0, "log": []}
    except Exception:
        data = {"version": 0, "log": []}

    new_v = int(data.get("version", 0)) + 1
    data["version"] = new_v
    data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    log = data.get("log", [])
    log.append({
        "version": new_v,
        "timestamp": data["updated_at"],
        "message": message or f"Update v{new_v}",
        "files": files_changed
    })
    data["log"] = log[-50:]  # keep last 50 entries

    tmp = VERSION_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(VERSION_FILE)

    VERSION = f"v{new_v}"
    return new_v

VERSION = f"v{load_app_version()}"
AUTO_UPDATE_REPO = "markoboskoauroville/groq-auto-update"
DEFAULT_MODEL = "qwen/qwen3.8-27b"
DEFAULT_PORT = 8765
MAX_MESSAGES = 80

# Thunderstrike SVG Favicon
GROQ_FAVICON_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="gb" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#181c24"/>
      <stop offset="100%" stop-color="#090c10"/>
    </linearGradient>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#ff7a45"/>
      <stop offset="50%" stop-color="#f55036"/>
      <stop offset="100%" stop-color="#d6301a"/>
    </linearGradient>
    <filter id="gw" x="-30%" y="-30%" width="160%" height="160%">
      <feGaussianBlur stdDeviation="1.8" result="b"/>
      <feMerge>
        <feMergeNode in="b"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
  </defs>
  <rect width="64" height="64" rx="16" fill="url(#gb)" stroke="#f55036" stroke-opacity="0.45" stroke-width="2"/>
  <path d="M35 7 L17 34 L31 34 L25 57 L47 26 L33 26 Z" fill="url(#bg)" filter="url(#gw)"/>
  <path d="M33 13 L22 32 L31 32 L28 49 L42 28 L32 28 Z" fill="#ffffff" fill-opacity="0.32"/>
</svg>'''

# Dynamic Port Allocator
def find_first_available_port(preferred_port=DEFAULT_PORT, max_range=200):
    for p in range(preferred_port, preferred_port + max_range):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(('127.0.0.1', p))
                return p
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

# Pricing per 1M tokens in USD
MODEL_PRICING = {
    "qwen/qwen3.8-27b": (0.80, 4.00),
    "qwen/qwen3.6-27b": (0.80, 4.00),
    "openai/gpt-oss-120b": (0.15, 0.60),
    "openai/gpt-oss-20b": (0.075, 0.30),
    "allam-2-7b": (0.20, 0.20),
    "meta-llama/llama-prompt-guard-2-86m": (0.04, 0.04),
    "meta-llama/llama-prompt-guard-2-22m": (0.03, 0.03),
    "canopylabs/orpheus-v1-english": (0.20, 0.20),
    "default": (0.50, 1.50)
}

ROTATE_ON = (RateLimitError, AuthenticationError, PermissionDeniedError)
REJECTED_COOLDOWN = 30 * 24 * 3600
DEFAULT_RATE_COOLDOWN = 60.0

def extract_keys_from_noise(text: str) -> list[str]:
    """Parse noisy text, .env files, json, logs, bash exports, and extract clean Groq keys."""
    if not text:
        return []
    matches = re.findall(r"gsk_[A-Za-z0-9_-]+", text)
    valid_keys = []
    for raw in matches:
        clean = re.sub(r"[^A-Za-z0-9_-].*$", "", raw).rstrip("-_'\",.;:()[]{}")
        if clean.startswith("gsk_") and len(clean) >= 20:
            valid_keys.append(clean)
    return list(dict.fromkeys(valid_keys))

def build_queen_system_prompt(user_persona: str = "") -> str:
    """
    Build Queen's always-on identity and self-update architecture prompt so the
    model always knows who it is and how its CI-gated self-update pipeline works.
    """
    base = (
        f"You are Queen (`qwen`), the AI assistant powering Marko's local Groq AI Studio "
        f"(currently running version {VERSION} on macOS at http://127.0.0.1:8765).\n"
        f"Your local source repository is `~/Developer/groq_ai_studio` (installed to `~/.groq`), "
        f"and your two core source files are `qwen_app/app.py` (Python/Flask backend) and "
        f"`qwen_app/index.html` (web UI).\n\n"
        f"YES — YOU CAN SELF-UPDATE! Never say you cannot self-update. You have a built-in, "
        f"CI-gated Self-Update Pipeline:\n"
        f"1. Web UI (`🔧` Self-Update button in topbar) or HTTP API:\n"
        f"   - Stage code chunks: `POST http://127.0.0.1:8765/api/self_update/chunk` with "
        f"`{{\"file\": \"app.py\" or \"index.html\", \"part\": 1, \"content\": \"...\"}}`\n"
        f"   - Assemble & deploy: `POST http://127.0.0.1:8765/api/self_update/assemble` with "
        f"`{{\"file\": \"app.py\" or \"index.html\", \"commit_message\": \"...\"}}`\n"
        f"2. CI Gate (`ci_run_all`): Automatically validates Python AST syntax, HTML tag balance, "
        f"truncation, and file size (>=30% of existing file) BEFORE touching disk. Broken or truncated "
        f"code is rejected with HTTP 422.\n"
        f"3. Deploy & GitHub Sync: When CI passes, the pipeline backs up the old file, writes the new "
        f"file to both `~/.groq/qwen_app/` and `~/Developer/groq_ai_studio/qwen_app/`, bumps `version.json` "
        f"(shown in the green `{VERSION}` badge in the top-right corner), and commits + pushes to BOTH "
        f"public GitHub repos: `markoboskoauroville/groq_ai_studio` and `{AUTO_UPDATE_REPO}`.\n"
        f"4. GitHub Reader (`🐙` button in topbar): Can load and attach your own live files from "
        f"`{AUTO_UPDATE_REPO}` or `markoboskoauroville/groq_ai_studio` into this chat so you can inspect "
        f"and modify your own code.\n"
        f"5. Live Visible Self-Test Backdoor: `POST http://127.0.0.1:8765/api/test/live` (or pressing `'t'` "
        f"in the server terminal).\n"
    )
    if user_persona:
        return f"{base}\nAdditional Persona / Instructions:\n{user_persona}"
    return base


def detect_code_intent(text: str) -> bool:
    """Detect if the prompt intends or requests output in a code box."""
    if not text:
        return False
    lower = text.lower()
    patterns = [
        r"\b(in\s+(the\s+|a\s+)?code\s*box)\b",
        r"\b(write\s+(answer\s+|it\s+|response\s+)?in\s+(the\s+|a\s+)?code\s*box)\b",
        r"\b(put\s+(it\s+|answer\s+)?in\s+(the\s+|a\s+)?code\s*box)\b",
        r"\b(code\s*box\s+format|code\s*box\s+mode)\b",
        r"\b(only\s+code|code\s+only|just\s+the\s+code)\b",
        r"\b(as\s+a\s+code\s*block|in\s+a\s+code\s*block)\b",
        r"\b(provide\s+only\s+(the\s+)?code)\b",
        r"\b(pure\s+code\s+without\s+explanation)\b"
    ]
    for p in patterns:
        if re.search(p, lower):
            return True
    return False

class DynamicKeyPool:
    def __init__(self):
        self.keys = []
        self.state = {"current": None, "cooldown": {}}
        self.reload()

    @staticmethod
    def _id(key):
        return hashlib.sha256(key.encode()).hexdigest()[:12]

    @staticmethod
    def _mask(key):
        return f"{key[:6]}...{key[-4:]}" if len(key) >= 10 else key

    def reload(self):
        keys = []
        if KEYS_FILE.exists():
            try:
                content = KEYS_FILE.read_text(encoding="utf-8")
                keys = extract_keys_from_noise(content)
            except Exception:
                pass
        self.keys = list(dict.fromkeys(keys))
        self._load_state()

    def save_keys(self):
        try:
            HOME.mkdir(parents=True, exist_ok=True)
            tmp = KEYS_FILE.with_suffix(".tmp")
            tmp.write_text("\n".join(self.keys) + "\n" if self.keys else "", encoding="utf-8")
            os.chmod(tmp, 0o600)
            tmp.replace(KEYS_FILE)
        except Exception:
            pass

    def add_keys(self, new_keys: list[str]) -> tuple[int, int]:
        before = len(self.keys)
        valid_incoming = [k for k in new_keys if k.startswith("gsk_") and len(k) >= 20]
        combined = list(dict.fromkeys(self.keys + valid_incoming))
        self.keys = combined
        self.save_keys()
        self._load_state()
        return len(self.keys) - before, len(self.keys)

    def remove_key_by_id(self, key_id: str) -> bool:
        target_idx = None
        for idx, k in enumerate(self.keys):
            if self._id(k) == key_id or self._mask(k) == key_id or k == key_id:
                target_idx = idx
                break
        if target_idx is not None:
            removed = self.keys.pop(target_idx)
            kid = self._id(removed)
            self.state.get("cooldown", {}).pop(f"{kid}:*", None)
            for k in list(self.state.get("cooldown", {}).keys()):
                if k.startswith(kid + ":"):
                    self.state["cooldown"].pop(k, None)
            if self.state.get("current") == kid:
                self.state["current"] = self._id(self.keys[0]) if self.keys else None
            self.save_keys()
            self._save_state()
            return True
        return False

    def remove_key_by_index(self, index: int) -> bool:
        if 1 <= index <= len(self.keys):
            return self.remove_key_by_id(self._id(self.keys[index - 1]))
        return False

    def clear(self):
        self.keys = []
        self.save_keys()
        self.state = {"current": None, "cooldown": {}}
        self._save_state()

    def _load_state(self):
        if STATE_FILE.exists():
            try:
                self.state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                self.state = {"current": None, "cooldown": {}}
        else:
            self.state = {"current": None, "cooldown": {}}
        valid_ids = [self._id(k) for k in self.keys]
        if not self.keys:
            self.state["current"] = None
        elif self.state.get("current") not in valid_ids:
            self.state["current"] = valid_ids[0]

    def _save_state(self):
        try:
            tmp = STATE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.state), encoding="utf-8")
            os.chmod(tmp, 0o600)
            tmp.replace(STATE_FILE)
        except Exception:
            pass

    def _wait_for(self, key, model):
        kid = self._id(key)
        now = time.time()
        cooldown = self.state.get("cooldown", {})
        until = max(cooldown.get(f"{kid}:*", 0), cooldown.get(f"{kid}:{model}", 0))
        return max(0.0, until - now)

    def candidates(self, model):
        if not self.keys:
            return []
        ids = [self._id(k) for k in self.keys]
        curr = self.state.get("current")
        start = ids.index(curr) if curr in ids else 0
        ordered = self.keys[start:] + self.keys[:start]
        ready = [k for k in ordered if self._wait_for(k, model) <= 0]
        return ready if ready else ordered

    def cool(self, key, model, exc):
        kid = self._id(key)
        if isinstance(exc, (AuthenticationError, PermissionDeniedError)):
            scope, seconds = "*", REJECTED_COOLDOWN
        else:
            scope, seconds = model, DEFAULT_RATE_COOLDOWN
            try:
                seconds = float(exc.response.headers.get("retry-after"))
            except Exception:
                pass
            seconds = max(seconds, 5.0)
        self.state.setdefault("cooldown", {})[f"{kid}:{scope}"] = time.time() + seconds
        other = [k for k in self.keys if k != key]
        if other:
            self.state["current"] = self._id(other[0])
        self._save_state()

    def good(self, key, model):
        kid = self._id(key)
        changed = self.state.get("current") != kid
        self.state["current"] = kid
        if self.state.setdefault("cooldown", {}).pop(f"{kid}:{model}", None) is not None:
            changed = True
        if changed:
            self._save_state()

    def reset(self):
        self.state["cooldown"] = {}
        if self.keys:
            self.state["current"] = self._id(self.keys[0])
        self._save_state()

    def status_rich(self):
        now = time.time()
        items = []
        curr = self.state.get("current")
        for index, key in enumerate(self.keys, start=1):
            kid = self._id(key)
            is_active = (kid == curr)
            cooldowns = []
            for name, until in self.state.get("cooldown", {}).items():
                if not name.startswith(kid + ":") or until <= now:
                    continue
                scope = name.split(":", 1)[1]
                wait = int(until - now)
                cooldowns.append({"scope": scope, "seconds_left": wait})

            if cooldowns:
                state_type = "cooling"
                status_text = f"Cooling ({cooldowns[0]['scope']}, {cooldowns[0]['seconds_left']}s)"
            elif is_active:
                state_type = "active"
                status_text = "Active (Primary)"
            else:
                state_type = "ready"
                status_text = "Ready (Failover Pool)"

            items.append({
                "index": index,
                "id": kid,
                "masked": self._mask(key),
                "status": status_text,
                "state_type": state_type,
                "is_active": is_active,
                "cooldowns": cooldowns
            })
        return items

    def status_legacy(self):
        return [(item["index"], item["masked"], item["status"]) for item in self.status_rich()]

pool = DynamicKeyPool()

active_messages = []
event_subscribers = []
subscribers_lock = threading.Lock()

def broadcast_event(data):
    with subscribers_lock:
        dead = []
        for q in event_subscribers:
            try:
                q.put_nowait(data)
            except Exception:
                dead.append(q)
        for q in dead:
            event_subscribers.remove(q)

def calculate_cost(model, prompt_tokens, completion_tokens):
    rates = MODEL_PRICING.get(model, MODEL_PRICING["default"])
    p_cost = (prompt_tokens * rates[0]) / 1_000_000.0
    c_cost = (completion_tokens * rates[1]) / 1_000_000.0
    return {
        "prompt_cost": p_cost,
        "completion_cost": c_cost,
        "total_cost": p_cost + c_cost,
        "rate_in": rates[0],
        "rate_out": rates[1]
    }

def load_ledger():
    if LEDGER_FILE.exists():
        try:
            return json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "total_spent": 0.0,
        "total_prompt_tokens": 0,
        "total_completion_tokens": 0,
        "total_tokens": 0,
        "prompts_count": 0,
        "history": []
    }

def record_spend(model, prompt_tokens, completion_tokens, req_id=""):
    cost_info = calculate_cost(model, prompt_tokens, completion_tokens)
    ledger = load_ledger()
    ledger["total_spent"] = round(ledger.get("total_spent", 0.0) + cost_info["total_cost"], 6)
    ledger["total_prompt_tokens"] = ledger.get("total_prompt_tokens", 0) + prompt_tokens
    ledger["total_completion_tokens"] = ledger.get("total_completion_tokens", 0) + completion_tokens
    ledger["total_tokens"] = ledger["total_prompt_tokens"] + ledger["total_completion_tokens"]
    ledger["prompts_count"] = ledger.get("prompts_count", 0) + 1

    entry = {
        "timestamp": time.time(),
        "time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "cost": cost_info["total_cost"],
        "req_id": req_id
    }
    history = ledger.get("history", [])
    history.append(entry)
    ledger["history"] = history[-100:]

    try:
        tmp = LEDGER_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(LEDGER_FILE)
    except Exception:
        pass

    return cost_info, ledger

app = Flask(__name__)

# --- Groq Thunderstrike Favicon Route ---
@app.get("/favicon.ico")
def favicon():
    return Response(GROQ_FAVICON_SVG, mimetype="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})

# --- Backdoor Remote Testing Endpoints ---
@app.get("/api/events")
def sse_events():
    def stream():
        q = queue.Queue(maxsize=100)
        with subscribers_lock:
            event_subscribers.append(q)
        try:
            yield f"data: {json.dumps({'type': 'init', 'messages': active_messages, 'count': len(active_messages)})}\n\n"
            while True:
                try:
                    event = q.get(timeout=20.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except queue.Empty:
                    yield ": ping\n\n"
        finally:
            with subscribers_lock:
                if q in event_subscribers:
                    event_subscribers.remove(q)

    return Response(stream(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.get("/api/session/messages")
def get_session_messages():
    return jsonify(messages=active_messages, count=len(active_messages))

@app.post("/api/keys/load-file")
def load_key_file_backdoor():
    data = request.get_json(silent=True) or {}
    path_str = (data.get("path") or "").strip()
    if not path_str:
        candidate = Path.cwd() / "groq-api.txt"
        if not candidate.exists():
            candidate = Path.home() / "Downloads" / "API" / "groq-api.txt"
        path_str = str(candidate)

    p = Path(path_str)
    if not p.exists():
        return jsonify(ok=False, error=f"File not found: {path_str}"), 404

    content = p.read_text(encoding="utf-8")
    found = extract_keys_from_noise(content)
    if not found:
        return jsonify(ok=False, error=f"No valid Groq keys found in {path_str}"), 400

    added, total = pool.add_keys(found)
    broadcast_event({"type": "key_loaded", "count": total, "active_key": pool._mask(pool.keys[0])})

    return jsonify(
        ok=True,
        added=added,
        count=total,
        active_key=pool._mask(pool.keys[0]),
        file=path_str,
        message=f"Loaded {added} new key(s) (total {total}) from {path_str}."
    )

@app.post("/api/remote/send")
def remote_send():
    if not pool.keys:
        return jsonify(ok=False, error="No API key configured. Call /api/keys/load-file first."), 400

    data = request.get_json(silent=True) or {}
    prompt = (data.get("prompt") or "").strip()
    mode = data.get("mode", "normal")
    model = data.get("model") or DEFAULT_MODEL
    system_prompt = (data.get("system_prompt") or "").strip()

    if not prompt:
        return jsonify(ok=False, error="Prompt is required"), 400

    # Auto-detect Code Box intent in prompt
    auto_detected_code = detect_code_intent(prompt)
    if auto_detected_code and mode != "code":
        mode = "code"

    broadcast_event({
        "type": "invisible_hand_typing",
        "prompt": prompt,
        "mode": mode,
        "auto_detected_code": auto_detected_code,
        "timestamp": time.time()
    })

    user_msg = {"role": "user", "content": prompt, "mode": mode, "timestamp": time.time()}
    active_messages.append(user_msg)

    groq_msgs = [{"role": "system", "content": build_queen_system_prompt(system_prompt)}]
    if mode == "code":
        groq_msgs.append({
            "role": "system",
            "content": "You are in CODE BOX mode. Provide ONLY the code solution. Format the code inside a single clean markdown code block with appropriate language tag. No pleasantries, no conversational preamble, no closing text."
        })
    for m in active_messages[-MAX_MESSAGES:]:
        groq_msgs.append({"role": m["role"], "content": m["content"]})

    candidates = pool.candidates(model)
    if not candidates:
        return jsonify(ok=False, error="All keys are cooling down"), 503

    start_time = time.time()
    raw_text = []
    reasoning = []
    prompt_tokens = 0
    completion_tokens = 0
    req_id = ""
    served_key = None
    failovers = 0

    for attempt, key in enumerate(candidates, start=1):
        served_key = key
        client = Groq(api_key=key, max_retries=0)
        try:
            if attempt > 1:
                failovers += 1
                broadcast_event({
                    "type": "key_failover",
                    "attempt": attempt,
                    "from_key": pool._mask(candidates[attempt - 2]),
                    "to_key": pool._mask(key)
                })
            resp = client.chat.completions.create(model=model, messages=groq_msgs, stream=True)
            for chunk in resp:
                if chunk.choices:
                    d = chunk.choices[0].delta
                    if getattr(d, "reasoning", None):
                        reasoning.append(d.reasoning)
                    if d.content:
                        raw_text.append(d.content)
                        broadcast_event({"type": "stream_chunk", "token": d.content})

                usage = getattr(chunk, "usage", None)
                if usage:
                    prompt_tokens = getattr(usage, "prompt_tokens", 0) or prompt_tokens
                    completion_tokens = getattr(usage, "completion_tokens", 0) or completion_tokens

                x_groq = getattr(chunk, "x_groq", None)
                if x_groq and getattr(x_groq, "id", None):
                    req_id = x_groq.id

            pool.good(key, model)
            break
        except ROTATE_ON as exc:
            pool.cool(key, model, exc)
            if not raw_text and not reasoning:
                continue
            return jsonify(ok=False, error=f"Interrupted on {pool._mask(key)}: {exc}"), 500
        except Exception as exc:
            pool.cool(key, model, exc)
            if not raw_text and not reasoning:
                continue
            return jsonify(ok=False, error=str(exc)), 500

    full_reply = "".join(raw_text)
    full_reason = "".join(reasoning)
    elapsed = time.time() - start_time
    total_tokens = prompt_tokens + completion_tokens
    if total_tokens == 0:
        total_tokens = int(len(full_reply) / 3.8) + 10
        prompt_tokens = max(5, total_tokens - len(full_reply) // 4)
        completion_tokens = max(1, total_tokens - prompt_tokens)

    cost_info, ledger = record_spend(model, prompt_tokens, completion_tokens, req_id)
    speed = round(completion_tokens / max(elapsed, 0.05), 1)

    telemetry = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cost": cost_info["total_cost"],
        "prompt_cost": cost_info["prompt_cost"],
        "completion_cost": cost_info["completion_cost"],
        "total_spent": ledger["total_spent"],
        "elapsed": round(elapsed, 2),
        "speed": speed,
        "req_id": req_id or f"groq_bt_{int(time.time()*1000)}",
        "confirmed": True,
        "model": model,
        "mode": mode,
        "served_by_key": pool._mask(served_key) if served_key else "unknown",
        "failovers": failovers,
        "auto_detected_code": auto_detected_code
    }

    asst_msg = {
        "role": "assistant",
        "content": full_reply,
        "reasoning": full_reason,
        "telemetry": telemetry,
        "mode": mode,
        "timestamp": time.time()
    }
    active_messages.append(asst_msg)

    broadcast_event({
        "type": "turn_complete",
        "user_message": user_msg,
        "assistant_message": asst_msg,
        "telemetry": telemetry,
        "total_spent": ledger["total_spent"]
    })

    return jsonify(
        ok=True,
        reply=full_reply,
        reasoning=full_reason,
        telemetry=telemetry,
        total_spent=ledger["total_spent"],
        messages_count=len(active_messages)
    )

# --- Standard Chatbot Streaming Route with Failover ---
@app.post("/api/chat")
def chat():
    if not pool.keys:
        return jsonify(error="No Groq API keys loaded. Please click '📥 Import Keys' or '⚙️' to add your key."), 400

    data = request.get_json(silent=True) or {}
    messages = data.get("messages", [])
    model = data.get("model") or DEFAULT_MODEL
    output_mode = data.get("output_mode", "normal")
    system_prompt = (data.get("system_prompt") or "").strip()

    # Check last user message for automatic Code Box intent
    last_user_text = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user_text = m.get("content", "")
            break

    auto_detected_code = detect_code_intent(last_user_text)
    if auto_detected_code and output_mode != "code":
        output_mode = "code"

    groq_msgs = [{"role": "system", "content": build_queen_system_prompt(system_prompt)}]
    if output_mode == "code":
        groq_msgs.append({
            "role": "system",
            "content": "You are in CODE BOX mode. Provide ONLY executable code formatted in a single clean markdown code block with appropriate language tag. No pleasantries, no conversational preamble, no closing text."
        })
    for m in messages[-MAX_MESSAGES:]:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role in ("user", "assistant", "system") and content:
            groq_msgs.append({"role": role, "content": content})

    def stream():
        candidates = pool.candidates(model)
        if not candidates:
            yield json.dumps({"error": "All API keys in key manager are currently cooling down. Wait or import another key."}) + "\n"
            return

        full_content = []
        full_reasoning = []
        prompt_tokens = 0
        completion_tokens = 0
        req_id = ""
        served_key = None
        failovers = 0
        start_time = time.time()

        for attempt, key in enumerate(candidates, start=1):
            served_key = key
            client = Groq(api_key=key, max_retries=0)
            try:
                if attempt > 1:
                    failovers += 1
                    broadcast_event({
                        "type": "key_failover",
                        "attempt": attempt,
                        "from_key": pool._mask(candidates[attempt - 2]),
                        "to_key": pool._mask(key)
                    })
                resp = client.chat.completions.create(model=model, messages=groq_msgs, stream=True)
                for chunk in resp:
                    if chunk.choices:
                        d = chunk.choices[0].delta
                        if getattr(d, "reasoning", None):
                            r_token = d.reasoning
                            full_reasoning.append(r_token)
                            yield json.dumps({"r": r_token}) + "\n"
                        if d.content:
                            c_token = d.content
                            full_content.append(c_token)
                            yield json.dumps({"t": c_token}) + "\n"

                    usage = getattr(chunk, "usage", None)
                    if usage:
                        prompt_tokens = getattr(usage, "prompt_tokens", 0) or prompt_tokens
                        completion_tokens = getattr(usage, "completion_tokens", 0) or completion_tokens

                    x_groq = getattr(chunk, "x_groq", None)
                    if x_groq and getattr(x_groq, "id", None):
                        req_id = x_groq.id

                pool.good(key, model)
                break
            except ROTATE_ON as exc:
                pool.cool(key, model, exc)
                if not full_content and not full_reasoning:
                    continue
                yield json.dumps({"error": f"Stream interrupted on {pool._mask(key)}: {exc}"}) + "\n"
                return
            except Exception as exc:
                pool.cool(key, model, exc)
                if not full_content and not full_reasoning:
                    continue
                yield json.dumps({"error": str(exc)}) + "\n"
                return

        elapsed = time.time() - start_time
        total_tokens = prompt_tokens + completion_tokens
        if total_tokens == 0:
            total_tokens = int(len("".join(full_content)) / 3.8) + 10
            prompt_tokens = max(5, total_tokens - len("".join(full_content)) // 4)
            completion_tokens = max(1, total_tokens - prompt_tokens)

        cost_info, ledger = record_spend(model, prompt_tokens, completion_tokens, req_id)
        speed = round(completion_tokens / max(elapsed, 0.05), 1)

        telemetry = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cost": cost_info["total_cost"],
            "prompt_cost": cost_info["prompt_cost"],
            "completion_cost": cost_info["completion_cost"],
            "total_spent": ledger["total_spent"],
            "elapsed": round(elapsed, 2),
            "speed": speed,
            "req_id": req_id or f"groq_stm_{int(time.time()*1000)}",
            "confirmed": True,
            "model": model,
            "mode": output_mode,
            "served_by_key": pool._mask(served_key) if served_key else "unknown",
            "failovers": failovers,
            "auto_detected_code": auto_detected_code
        }

        yield json.dumps({"u": telemetry}) + "\n"

    return Response(stream(), mimetype="application/x-ndjson", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# --- Key Manager & Failover Endpoints ---
@app.get("/api/keys")
def get_keys():
    configured = len(pool.keys) > 0
    active_masked = pool._mask(pool.keys[0]) if configured else None
    return jsonify(
        configured=configured,
        count=len(pool.keys),
        keys=pool.status_legacy(),
        items=pool.status_rich(),
        active_key=active_masked,
        version=VERSION
    )

@app.post("/api/keys/import")
def import_keys():
    content = ""
    filename = "key_file.txt"

    if "file" in request.files:
        f = request.files["file"]
        filename = f.filename or filename
        content = f.read().decode("utf-8", errors="replace")
    else:
        data = request.get_json(silent=True) or {}
        content = data.get("content") or data.get("text") or ""
        filename = data.get("filename", filename)

    content = content.strip()
    if not content:
        return jsonify(ok=False, error="Key input is empty"), 400

    found = extract_keys_from_noise(content)
    if not found:
        return jsonify(ok=False, error="No valid Groq API keys found. Keys must start with 'gsk_' followed by alphanumeric characters."), 400

    added, total = pool.add_keys(found)
    broadcast_event({"type": "keys_updated", "count": total, "added": added})

    return jsonify(
        ok=True,
        added=added,
        count=total,
        total=total,
        items=pool.status_rich(),
        message=f"Parsed {len(found)} key(s): added {added} new key(s) to Key Manager (total {total})."
    )

@app.post("/api/keys/upload")
def upload_keys():
    return import_keys()

@app.post("/api/keys/delete")
def delete_key():
    data = request.get_json(silent=True) or {}
    key_id = data.get("id") or data.get("key") or ""
    index = data.get("index")

    removed = False
    if index is not None:
        try:
            removed = pool.remove_key_by_index(int(index))
        except Exception:
            pass
    elif key_id:
        removed = pool.remove_key_by_id(str(key_id))

    if not removed:
        return jsonify(ok=False, error="Key not found in pool"), 404

    broadcast_event({"type": "keys_updated", "count": len(pool.keys)})
    return jsonify(
        ok=True,
        count=len(pool.keys),
        items=pool.status_rich(),
        message="Key removed from Key Manager."
    )

@app.post("/api/keys/clear")
def clear_keys():
    pool.clear()
    broadcast_event({"type": "keys_cleared"})
    return jsonify(ok=True, count=0, items=[], message="All API keys cleared from manager.")

@app.post("/api/reset-keys")
def reset_keys():
    pool.reset()
    return jsonify(ok=True, count=len(pool.keys), items=pool.status_rich(), message="Key cooldowns reset.")

# ─────────────── CHAT PERSISTENCE ────────────────
# Saves all chats to ~/.groq/chats/ as JSON files.
# Not mirrored to GitHub — local only.

def _chat_path(chat_id: str) -> Path:
    """Safe path for a chat file. Rejects traversal."""
    safe = re.sub(r"[^A-Za-z0-9_-]", "", chat_id)
    if not safe:
        safe = "unknown"
    return CHATS_DIR / f"{safe}.json"

def _auto_title(messages: list) -> str:
    """Generate a title from the first user message."""
    for m in messages:
        if m.get("role") == "user":
            text = (m.get("content") or "").strip()
            # Strip attached file content
            if "--- FILE:" in text:
                text = text.split("\n\n")[-1].strip()
            if text:
                title = text[:50]
                if len(text) > 50:
                    title = title.rsplit(" ", 1)[0] + "…"
                return title
    return "New Chat"

@app.get("/api/chats")
def list_chats():
    """List all saved chats (metadata only, no messages)."""
    CHATS_DIR.mkdir(parents=True, exist_ok=True)
    chats = []
    for f in sorted(CHATS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            chats.append({
                "id": data.get("id", f.stem),
                "title": data.get("title", "Untitled"),
                "message_count": len(data.get("messages", [])),
                "updated_at": data.get("updated_at", ""),
                "created_at": data.get("created_at", ""),
            })
        except Exception:
            pass
    return jsonify(ok=True, chats=chats, count=len(chats))

@app.get("/api/chats/<chat_id>")
def get_chat(chat_id):
    """Load a specific chat with all messages."""
    path = _chat_path(chat_id)
    if not path.exists():
        return jsonify(error=f"Chat '{chat_id}' not found"), 404
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return jsonify(ok=True, chat=data)
    except Exception as exc:
        return jsonify(error=str(exc)), 500

@app.post("/api/chats/save")
def save_chat():
    """
    Save or update a chat.
    JSON Body: { "id": "s_123", "title": "...", "messages": [...] }
    If title is empty/missing, auto-generates from first user message.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify(error="No data"), 400

    chat_id = (data.get("id") or "").strip()
    if not chat_id:
        return jsonify(error="Missing chat id"), 400

    messages = data.get("messages", [])
    title = (data.get("title") or "").strip()

    # Auto-title if empty
    if not title:
        title = _auto_title(messages)

    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    path = _chat_path(chat_id)

    # Preserve created_at if chat already exists
    created_at = now
    if path.exists():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
            created_at = old.get("created_at", now)
        except Exception:
            pass

    chat_data = {
        "id": chat_id,
        "title": title,
        "messages": messages,
        "message_count": len(messages),
        "created_at": created_at,
        "updated_at": now,
    }

    CHATS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(chat_data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)

    return jsonify(ok=True, id=chat_id, title=title, message_count=len(messages))

@app.post("/api/chats/rename")
def rename_chat():
    """Rename a chat. JSON Body: { "id": "...", "title": "New Title" }"""
    data = request.get_json(silent=True) or {}
    chat_id = (data.get("id") or "").strip()
    new_title = (data.get("title") or "").strip()

    if not chat_id:
        return jsonify(error="Missing chat id"), 400
    if not new_title:
        return jsonify(error="Missing new title"), 400

    path = _chat_path(chat_id)
    if not path.exists():
        return jsonify(error=f"Chat '{chat_id}' not found"), 404

    try:
        chat_data = json.loads(path.read_text(encoding="utf-8"))
        chat_data["title"] = new_title
        chat_data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(chat_data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
        return jsonify(ok=True, id=chat_id, title=new_title)
    except Exception as exc:
        return jsonify(error=str(exc)), 500

@app.post("/api/chats/delete")
def delete_chat():
    """Delete a chat. JSON Body: { "id": "..." }"""
    data = request.get_json(silent=True) or {}
    chat_id = (data.get("id") or "").strip()
    if not chat_id:
        return jsonify(error="Missing chat id"), 400

    path = _chat_path(chat_id)
    if path.exists():
        path.unlink()
        return jsonify(ok=True, id=chat_id, message="Chat deleted")
    return jsonify(error="Chat not found"), 404

# ─────────────── SELF-UPDATE ENGINE ───────────────
# Accepts code in chunks, assembles them, and writes the final file.
# This works around output token limits by letting an AI send large
# files in 3-4 small pieces that are stitched together server-side.
#
# CI PIPELINE: every assembled file must pass all checks before it
# can be written. If any check fails the write is rejected and the
# chunks stay in staging so the sender can fix them.

import ast as _ast  # for Python CI validation

# Allowlist: only these files may be updated (relative to REPO_DIR)
UPDATABLE_FILES = {"app.py", "index.html"}

# ── CI Validation ────────────────────────────────────
def ci_validate_python(code: str, filename: str) -> tuple[bool, list[str]]:
    """Validate Python code: syntax, truncation, structural sanity."""
    errors = []

    # 1. Non-empty
    if not code.strip():
        errors.append("EMPTY: file is empty or whitespace-only")
        return False, errors

    # 2. AST parse — catches all syntax errors
    try:
        _ast.parse(code, filename=filename)
    except SyntaxError as exc:
        errors.append(f"SYNTAX ERROR: {exc.msg} (line {exc.lineno}, col {exc.offset})")
        return False, errors

    # 3. Truncation heuristics (informational only when AST passed)
    #    Raw text counting hits false positives on brackets inside strings,
    #    comments, f-strings, regex, etc.  Since AST passed above, these are
    #    logged as warnings for human review but never block the update.
    stripped = code.rstrip()
    # Ends mid-line (no newline at end, last line not a comment/blank/closing)
    last_line = stripped.split("\n")[-1].strip() if stripped else ""
    if last_line and not last_line.startswith("#") and last_line not in ("", ")", "]", "}", "pass", "..."):
        if not last_line.endswith(":") and not last_line.endswith(")") and not last_line.endswith("'") \
           and not last_line.endswith('"') and "main()" not in last_line and "if __name__" not in last_line:
            # Not conclusive on its own, just a warning
            pass

    # 4. Structural sanity — must have basic Python structure
    if "import " not in code and "from " not in code:
        errors.append("STRUCTURE: no import statements found — likely truncated or wrong file")
    if "def " not in code and "class " not in code:
        errors.append("STRUCTURE: no function or class definitions found")

    return len(errors) == 0, errors


def ci_validate_html(code: str, filename: str) -> tuple[bool, list[str]]:
    """Validate HTML code: tag balance, truncation, structural sanity."""
    errors = []

    # 1. Non-empty
    if not code.strip():
        errors.append("EMPTY: file is empty or whitespace-only")
        return False, errors

    lower = code.lower()

    # 2. Must end with </html>
    if not lower.rstrip().endswith("</html>"):
        errors.append("TRUNCATED: file does not end with </html>")

    # 3. Critical tags must be present and balanced
    for tag in ("html", "head", "body"):
        opens = lower.count(f"<{tag}")
        closes = lower.count(f"</{tag}>")
        if opens == 0:
            errors.append(f"STRUCTURE: missing <{tag}> tag")
        elif opens != closes:
            errors.append(f"TRUNCATED: unbalanced <{tag}> ({opens} open vs {closes} close)")

    # 4. Script tags balanced
    script_opens = lower.count("<script")
    script_closes = lower.count("</script>")
    if script_opens != script_closes:
        errors.append(f"TRUNCATED: unbalanced <script> ({script_opens} open vs {script_closes} close)")

    # 5. JS brace balance inside <script> blocks (rough check)
    import re as _re
    scripts = _re.findall(r"<script[^>]*>(.*?)</script>", code, _re.DOTALL | _re.IGNORECASE)
    for i, scr in enumerate(scripts):
        opens = scr.count("{")
        closes = scr.count("}")
        if opens != closes:
            errors.append(f"TRUNCATED: JS braces unbalanced in <script> block {i+1} ({opens} open vs {closes} close)")

    # 6. Must have a <title>
    if "<title>" not in lower:
        errors.append("STRUCTURE: missing <title> tag")

    return len(errors) == 0, errors


def ci_validate_size(new_code: str, old_path: Path, filename: str) -> tuple[bool, list[str]]:
    """Size sanity check: new file must not be dramatically smaller than old."""
    errors = []
    if old_path.exists():
        old_size = old_path.stat().st_size
        new_size = len(new_code.encode("utf-8"))
        if old_size > 0:
            ratio = new_size / old_size
            if ratio < 0.30:
                errors.append(
                    f"SIZE: new {filename} is {new_size:,} bytes vs old {old_size:,} bytes "
                    f"({ratio:.0%}) — looks like severe truncation"
                )
            elif ratio < 0.50:
                errors.append(
                    f"SIZE WARNING: new {filename} is {new_size:,} bytes vs old {old_size:,} bytes "
                    f"({ratio:.0%}) — possibly truncated"
                )
    return len(errors) == 0, errors


def ci_run_all(code: str, filename: str) -> tuple[bool, list[str]]:
    """Run the full CI pipeline on assembled code. Returns (passed, errors)."""
    all_errors = []

    # File-type-specific checks
    if filename.endswith(".py"):
        ok, errs = ci_validate_python(code, filename)
        all_errors.extend(errs)
    elif filename.endswith(".html") or filename.endswith(".htm"):
        ok, errs = ci_validate_html(code, filename)
        all_errors.extend(errs)

    # Size check against current file on disk
    ok, errs = ci_validate_size(code, REPO_DIR / filename, filename)
    all_errors.extend(errs)

    passed = len(all_errors) == 0
    return passed, all_errors


# ── Git Operations ───────────────────────────────────
def git_run(args: list[str], timeout: int = 30) -> tuple[bool, str]:
    """Run a git command in the repo root. Returns (success, output)."""
    try:
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        res = subprocess.run(
            ["git"] + args,
            capture_output=True, text=True, timeout=timeout,
            cwd=str(GIT_ROOT), env=env
        )
        combined = (res.stdout + "\n" + res.stderr).strip()
        return res.returncode == 0, combined
    except Exception as exc:
        return False, str(exc)


def git_commit_and_push(files: list[str], message: str) -> tuple[bool, list[str]]:
    """Stage files, commit, and push to both origin AND the auto-update repo."""
    log = []

    # Stage the specific files
    for f in files:
        ok, out = git_run(["add", f])
        log.append(f"git add {f}: {'OK' if ok else 'FAIL'} — {out}")
        if not ok:
            return False, log

    # Also stage version.json
    ok, out = git_run(["add", "version.json"])
    log.append(f"git add version.json: {'OK' if ok else 'FAIL'} — {out}")

    # Check if there is anything to commit
    ok, out = git_run(["diff", "--cached", "--stat"])
    if not out.strip():
        log.append("Nothing to commit (files unchanged)")
        return True, log

    # Commit
    ok, out = git_run(["commit", "-m", message])
    log.append(f"git commit: {'OK' if ok else 'FAIL'} — {out[:200]}")
    if not ok:
        return False, log

    # Push to origin (dev repo)
    ok, out = git_run(["push", "origin", "main"])
    log.append(f"git push origin: {'OK' if ok else 'FAIL'} — {out[:200]}")

    # Ensure the auto-update remote exists
    ok_remote, _ = git_run(["remote", "get-url", "auto-update"])
    if not ok_remote:
        git_run(["remote", "add", "auto-update",
                 f"https://github.com/{AUTO_UPDATE_REPO}.git"])
        log.append(f"Added remote 'auto-update' → {AUTO_UPDATE_REPO}")

    # Push to auto-update repo
    ok2, out2 = git_run(["push", "auto-update", "main"])
    log.append(f"git push auto-update: {'OK' if ok2 else 'FAIL'} — {out2[:200]}")

    return (ok or ok2), log

@app.get("/api/self_update/status")
def update_status():
    """Return current chunks in the staging area and updatable files."""
    UPDATE_DIR.mkdir(parents=True, exist_ok=True)
    chunks = sorted(UPDATE_DIR.glob("chunk_*_part*.txt"))
    staged = {}
    for c in chunks:
        # Parse: chunk_{filename}_part{NNN}.txt
        name = c.name
        parts = name.split("_part")
        if len(parts) == 2:
            file_part = name[len("chunk_"):]
            file_name = file_part.rsplit("_part", 1)[0]
            part_num = parts[1].replace(".txt", "")
            staged.setdefault(file_name, []).append({
                "part": int(part_num),
                "size": c.stat().st_size,
                "path": str(c)
            })
    # Sort each file's parts
    for fname in staged:
        staged[fname].sort(key=lambda x: x["part"])

    return jsonify(
        ok=True,
        updatable_files=list(UPDATABLE_FILES),
        staged=staged,
        update_dir=str(UPDATE_DIR)
    )

@app.post("/api/self_update/chunk")
def update_chunk():
    """
    Receives a chunk of code.
    JSON Body: { "file": "app.py", "part": 1, "content": "..." }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify(error="No JSON data received"), 400

    filename = (data.get("file") or "").strip()
    part = data.get("part", 0)
    content = data.get("content", "")

    if not filename:
        return jsonify(error="Missing 'file' field"), 400

    # Validate filename against allowlist
    if filename not in UPDATABLE_FILES:
        return jsonify(error=f"File '{filename}' is not in the updatable allowlist: {sorted(UPDATABLE_FILES)}"), 403

    # Sanitize: reject path traversal
    if "/" in filename or "\\" in filename or filename.startswith("."):
        return jsonify(error="Invalid filename"), 400

    if not content:
        return jsonify(error="Empty content — nothing to save"), 400

    try:
        part = int(part)
    except (TypeError, ValueError):
        return jsonify(error="'part' must be an integer"), 400

    # Save chunk
    UPDATE_DIR.mkdir(parents=True, exist_ok=True)
    chunk_path = UPDATE_DIR / f"chunk_{filename}_part{part:03d}.txt"
    chunk_path.write_text(content, encoding="utf-8")

    # Compute hash for verification
    chunk_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    # Count existing chunks for this file
    existing = sorted(UPDATE_DIR.glob(f"chunk_{filename}_part*.txt"))
    parts_list = [c.name for c in existing]

    broadcast_event({
        "type": "self_update_chunk",
        "file": filename,
        "part": part,
        "size": len(content),
        "hash": chunk_hash,
        "total_parts": len(existing)
    })

    return jsonify(
        ok=True,
        status="chunk_saved",
        file=filename,
        saved_part=part,
        bytes=len(content),
        hash=chunk_hash,
        total_chunks=len(existing),
        existing_parts=parts_list
    )

@app.post("/api/self_update/assemble")
def assemble_update():
    """
    CI-gated assembly: stitch chunks → run CI → backup → write → git commit+push → bump version.
    JSON Body: { "file": "app.py" }
    Optional: { "expected_hash": "abc123...", "commit_message": "..." }
    """
    data = request.get_json(silent=True) or {}
    filename = (data.get("file") or "").strip()
    expected_hash = (data.get("expected_hash") or "").strip()
    commit_msg = (data.get("commit_message") or "").strip()

    if not filename:
        return jsonify(error="Missing 'file' field"), 400

    if filename not in UPDATABLE_FILES:
        return jsonify(error=f"File '{filename}' is not in the updatable allowlist"), 403

    target_path = REPO_DIR / filename
    chunks = sorted(UPDATE_DIR.glob(f"chunk_{filename}_part*.txt"))

    if not chunks:
        return jsonify(error=f"No chunks found for '{filename}' in staging area"), 404

    # ── STITCH ──
    final_content = ""
    part_details = []
    for c in chunks:
        part_text = c.read_text(encoding="utf-8")
        final_content += part_text
        part_details.append({"name": c.name, "size": len(part_text)})

    assembled_hash = hashlib.sha256(final_content.encode("utf-8")).hexdigest()

    # ── HASH CHECK ──
    if expected_hash and not assembled_hash.startswith(expected_hash):
        return jsonify(
            error="HASH MISMATCH — assembled content does not match expected hash. Chunks NOT written.",
            ci_passed=False,
            assembled_hash=assembled_hash,
            expected_hash=expected_hash,
            total_size=len(final_content),
            parts_used=len(chunks)
        ), 409

    # ── CI PIPELINE ──
    ci_passed, ci_errors = ci_run_all(final_content, filename)
    if not ci_passed:
        broadcast_event({
            "type": "self_update_ci_failed",
            "file": filename,
            "errors": ci_errors
        })
        return jsonify(
            ok=False,
            ci_passed=False,
            status="ci_failed",
            error="CI VALIDATION FAILED — file NOT written. Fix the errors and try again.",
            ci_errors=ci_errors,
            file=filename,
            size=len(final_content),
            hash=assembled_hash
        ), 422

    # ── BACKUP ──
    backup_name = None
    if target_path.exists():
        backup_dir = UPDATE_DIR / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_name = f"{filename}.backup_{int(time.time())}"
        backup_path = backup_dir / backup_name
        shutil.copy2(str(target_path), str(backup_path))

    # ── WRITE ──
    # Write to the running copy (REPO_DIR — may be ~/.groq/qwen_app/)
    target_path.write_text(final_content, encoding="utf-8")
    # Also write to the source repo if different (so git commit sees the change)
    git_target = GIT_ROOT / "qwen_app" / filename
    if git_target.resolve() != target_path.resolve() and git_target.parent.is_dir():
        git_target.write_text(final_content, encoding="utf-8")

    # ── CLEANUP CHUNKS ──
    for c in chunks:
        c.unlink()

    # ── BUMP VERSION ──
    new_version = bump_app_version(
        files_changed=[filename],
        message=commit_msg or f"Update {filename}"
    )

    # ── GIT COMMIT + PUSH ──
    git_msg = commit_msg or f"v{new_version}: Update {filename} via Self-Update CI pipeline"
    git_ok, git_log = git_commit_and_push(
        files=[f"qwen_app/{filename}"],
        message=git_msg
    )

    broadcast_event({
        "type": "self_update_complete",
        "file": filename,
        "size": len(final_content),
        "hash": assembled_hash[:16],
        "parts_assembled": len(part_details),
        "version": new_version,
        "ci_passed": True,
        "git_pushed": git_ok
    })

    return jsonify(
        ok=True,
        ci_passed=True,
        status="deployed",
        message=f"CI PASSED ✓ — {filename} deployed as v{new_version} ({len(final_content):,} chars, {len(part_details)} parts)",
        file=filename,
        size=len(final_content),
        hash=assembled_hash,
        version=new_version,
        version_str=f"v{new_version}",
        backup=backup_name,
        parts_assembled=part_details,
        git_ok=git_ok,
        git_log=git_log,
        ci_errors=[]
    )

@app.post("/api/self_update/discard")
def discard_chunks():
    """
    Discard all staged chunks for a specific file (or all files).
    JSON Body: { "file": "app.py" } or { "file": "*" } for all.
    """
    data = request.get_json(silent=True) or {}
    filename = (data.get("file") or "").strip()

    if not filename:
        return jsonify(error="Missing 'file' field"), 400

    if filename == "*":
        # Discard everything
        chunks = list(UPDATE_DIR.glob("chunk_*_part*.txt"))
    else:
        chunks = list(UPDATE_DIR.glob(f"chunk_{filename}_part*.txt"))

    removed = 0
    for c in chunks:
        c.unlink()
        removed += 1

    return jsonify(ok=True, discarded=removed, file=filename)

@app.get("/api/self_update/preview")
def preview_assembled():
    """
    Preview what the assembled file would look like without writing it.
    Query param: ?file=app.py
    """
    filename = (request.args.get("file") or "").strip()
    if not filename:
        return jsonify(error="Missing 'file' query param"), 400

    chunks = sorted(UPDATE_DIR.glob(f"chunk_{filename}_part*.txt"))
    if not chunks:
        return jsonify(error=f"No chunks found for '{filename}'"), 404

    final_content = ""
    for c in chunks:
        final_content += c.read_text(encoding="utf-8")

    assembled_hash = hashlib.sha256(final_content.encode("utf-8")).hexdigest()

    return jsonify(
        ok=True,
        file=filename,
        size=len(final_content),
        lines=final_content.count("\n") + 1,
        hash=assembled_hash,
        preview_head=final_content[:500],
        preview_tail=final_content[-500:] if len(final_content) > 500 else ""
    )

@app.get("/api/self_update/backups")
def list_backups():
    """List available backups for all updatable files."""
    backup_dir = UPDATE_DIR / "backups"
    if not backup_dir.exists():
        return jsonify(ok=True, backups=[])

    backups = []
    for b in sorted(backup_dir.iterdir(), reverse=True):
        backups.append({
            "name": b.name,
            "size": b.stat().st_size,
            "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(b.stat().st_mtime))
        })

    return jsonify(ok=True, backups=backups)

@app.post("/api/self_update/restore")
def restore_backup():
    """
    Restore a file from backup.
    JSON Body: { "backup": "app.py.backup_1699700000" }
    """
    data = request.get_json(silent=True) or {}
    backup_name = (data.get("backup") or "").strip()

    if not backup_name:
        return jsonify(error="Missing 'backup' field"), 400

    # Sanitize
    if "/" in backup_name or "\\" in backup_name:
        return jsonify(error="Invalid backup name"), 400

    backup_path = UPDATE_DIR / "backups" / backup_name
    if not backup_path.exists():
        return jsonify(error=f"Backup '{backup_name}' not found"), 404

    # Determine the original filename from backup name (e.g. "app.py.backup_123")
    original_name = backup_name.split(".backup_")[0]
    if original_name not in UPDATABLE_FILES:
        return jsonify(error=f"Cannot restore: '{original_name}' not in updatable allowlist"), 403

    target_path = REPO_DIR / original_name
    content = backup_path.read_text(encoding="utf-8")
    target_path.write_text(content, encoding="utf-8")

    return jsonify(
        ok=True,
        message=f"Restored '{original_name}' from backup '{backup_name}'",
        file=original_name,
        size=len(content)
    )
# ──────────────────────────────────────────────────

# GitHub Read-Only Operations
def run_gh(args, timeout=15):
    try:
        cmd = ["gh"] + args
        env = os.environ.copy()
        env["GH_PROMPT_DISABLED"] = "1"
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
        if res.returncode == 0:
            return True, res.stdout
        return False, res.stderr or res.stdout
    except Exception as exc:
        return False, str(exc)

@app.get("/api/github/repos")
def github_repos():
    limit = request.args.get("limit", "100")
    ok, out = run_gh(["repo", "list", "--limit", str(limit),
                      "--json", "name,nameWithOwner,description,isPrivate,updatedAt,stargazerCount,primaryLanguage"])
    if not ok:
        return jsonify(error=f"GitHub read failed: {out}"), 500
    try:
        return jsonify(repos=json.loads(out))
    except Exception as exc:
        return jsonify(error=str(exc)), 500

@app.get("/api/github/contents")
def github_contents():
    repo = request.args.get("repo", "").strip()
    path = request.args.get("path", "").strip()
    if not repo:
        return jsonify(error="Repository is required"), 400

    api_path = f"repos/{repo}/contents"
    if path:
        api_path = f"{api_path}/{path.lstrip('/')}"

    ok, out = run_gh(["api", api_path])
    if not ok:
        return jsonify(error=f"Failed to read from GitHub: {out}"), 400

    try:
        data = json.loads(out)
        if isinstance(data, dict) and data.get("type") == "file":
            encoded = data.get("content", "")
            try:
                decoded = base64.b64decode(encoded).decode("utf-8")
            except UnicodeDecodeError:
                decoded = "(Binary file content cannot be displayed as UTF-8)"
            return jsonify(
                type="file",
                name=data.get("name"),
                path=data.get("path"),
                size=data.get("size"),
                content=decoded,
                repo=repo
            )
        elif isinstance(data, list):
            items = [{"name": i.get("name"), "path": i.get("path"), "type": i.get("type"), "size": i.get("size", 0)} for i in data]
            return jsonify(type="dir", repo=repo, path=path, items=items)
        return jsonify(data=data)
    except Exception as exc:
        return jsonify(error=str(exc)), 500

@app.post("/api/github/read-url")
def github_read_url():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify(error="URL is required"), 400

    match = re.search(r"github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)", url)
    if match:
        owner, repo, branch, path = match.groups()
        full_repo = f"{owner}/{repo}"
        api_path = f"repos/{full_repo}/contents/{path}?ref={branch}"
        ok, out = run_gh(["api", api_path])
        if ok:
            try:
                res = json.loads(out)
                decoded = base64.b64decode(res.get("content", "")).decode("utf-8")
                return jsonify(
                    name=res.get("name", path.split("/")[-1]),
                    repo=full_repo,
                    path=path,
                    size=res.get("size", len(decoded)),
                    content=decoded
                )
            except Exception as exc:
                return jsonify(error=f"Decode error: {exc}"), 500
        return jsonify(error=f"Could not read GitHub URL: {out}"), 400

    raw_url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
    try:
        import urllib.request
        req = urllib.request.Request(raw_url, headers={"User-Agent": "GroqChat/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read().decode("utf-8", errors="replace")
            filename = url.split("/")[-1].split("?")[0] or "github_file.txt"
            return jsonify(name=filename, repo="github", path=url, size=len(content), content=content)
    except Exception as exc:
        return jsonify(error=f"Failed to read URL: {exc}"), 400

@app.get("/")
def index():
    page = Path(__file__).with_name("index.html").read_text(encoding="utf-8")
    page = page.replace("__DEFAULT_MODEL__", DEFAULT_MODEL).replace("__VERSION__", VERSION)
    return Response(page, mimetype="text/html", headers={"Cache-Control": "no-store"})

@app.get("/api/version")
def get_version():
    """Return current version info, update history, and auto-update repo."""
    try:
        data = json.loads(VERSION_FILE.read_text(encoding="utf-8")) if VERSION_FILE.exists() else {}
    except Exception:
        data = {}
    return jsonify(
        version=data.get("version", 1),
        version_str=VERSION,
        updated_at=data.get("updated_at", ""),
        auto_update_repo=AUTO_UPDATE_REPO,
        log=data.get("log", [])[-10:]
    )

@app.get("/health")
def health():
    return jsonify(app="groq-modern-chat", version=VERSION, ok=True, default_model=DEFAULT_MODEL, has_keys=len(pool.keys) > 0)


# ── Live Visible Testing & Terminal Backdoor ─────────────────────────
def _term_print(line: str):
    """Write a line to the server terminal stdout immediately (cbreak-safe)."""
    sys.stdout.write(f"\r{line}\r\n")
    sys.stdout.flush()


@app.post("/api/terminal/log")
def terminal_log():
    """
    Backdoor entry point allowing external scripts/agents to print live
    commands and test status directly into Queen's running server window.
    JSON Body: { "message": "...", "level": "info|cmd|pass|fail" }
    """
    data = request.get_json(silent=True) or {}
    msg = str(data.get("message") or "").strip()
    level = str(data.get("level") or "info").lower()
    if not msg:
        return jsonify(error="Missing 'message'"), 400

    colors = {
        "cmd": "\033[1;36m$ ",
        "pass": "\033[1;32m✓ ",
        "fail": "\033[1;31m✗ ",
        "info": "\033[1;33m[LIVE] ",
    }
    prefix = colors.get(level, colors["info"])
    ts = time.strftime("%H:%M:%S")
    _term_print(f"\033[90m[{ts}]\033[0m {prefix}{msg}\033[0m")
    broadcast_event({"type": "terminal_log", "level": level, "message": msg, "ts": ts})
    return jsonify(ok=True, ts=ts, level=level, message=msg)


def run_live_selftest() -> dict:
    """
    Execute the non-destructive live verification suite while printing every
    step, HTTP status, and outcome directly to Queen's server terminal window.
    """
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    _term_print("\033[1;35m" + "═" * 70 + "\033[0m")
    _term_print(f"\033[1;35m  QUEEN LIVE SELF-TEST SUITE — {VERSION} ({ts})\033[0m")
    _term_print("\033[1;35m" + "═" * 70 + "\033[0m")

    results = []
    passed = 0
    failed = 0

    def record(name: str, cmd_desc: str, ok: bool, detail: str = ""):
        nonlocal passed, failed
        _term_print(f"\033[1;36m  $ {cmd_desc}\033[0m")
        if ok:
            passed += 1
            _term_print(f"\033[1;32m    ✓ PASS:\033[0m {name} {f'— {detail}' if detail else ''}")
        else:
            failed += 1
            _term_print(f"\033[1;31m    ✗ FAIL:\033[0m {name} {f'— {detail}' if detail else ''}")
        results.append({"name": name, "command": cmd_desc, "ok": ok, "detail": detail})

    with app.test_client() as c:
        # 1. Health
        r = c.get("/health")
        j = r.get_json(silent=True) or {}
        record("Health check", "GET /health", r.status_code == 200 and j.get("ok") is True, f"HTTP {r.status_code}, version={j.get('version')}")

        # 2. Version
        r = c.get("/api/version")
        j = r.get_json(silent=True) or {}
        record("Version endpoint", "GET /api/version", r.status_code == 200 and "version_str" in j, f"HTTP {r.status_code}, {j.get('version_str')} (repo={j.get('auto_update_repo')})")

        # 3. CI Reject: Broken Python
        c.post("/api/self_update/chunk", json={"file": "app.py", "part": 1, "content": 'print("hello"'})
        r = c.post("/api/self_update/assemble", json={"file": "app.py"})
        j = r.get_json(silent=True) or {}
        c.post("/api/self_update/discard", json={"file": "app.py"})
        record("CI rejects broken Python", "POST /api/self_update/assemble (bad app.py)", r.status_code == 422 and j.get("ci_passed") is False, f"HTTP {r.status_code}, {len(j.get('ci_errors', []))} CI error(s)")

        # 4. CI Reject: Truncated HTML
        c.post("/api/self_update/chunk", json={"file": "index.html", "part": 1, "content": "<html><head></head><body><p>hi</p></body>"})
        r = c.post("/api/self_update/assemble", json={"file": "index.html"})
        j = r.get_json(silent=True) or {}
        c.post("/api/self_update/discard", json={"file": "index.html"})
        record("CI rejects truncated HTML", "POST /api/self_update/assemble (bad index.html)", r.status_code == 422 and j.get("ci_passed") is False, f"HTTP {r.status_code}, {len(j.get('ci_errors', []))} CI error(s)")

        # 5. Allowlist enforcement
        r = c.post("/api/self_update/chunk", json={"file": "evil.py", "part": 1, "content": "x=1"})
        record("Self-update allowlist blocks evil.py", "POST /api/self_update/chunk (evil.py)", r.status_code == 403, f"HTTP {r.status_code}")

        # 6. Staging status
        r = c.get("/api/self_update/status")
        j = r.get_json(silent=True) or {}
        record("Self-update staging status", "GET /api/self_update/status", r.status_code == 200 and j.get("ok") is True, f"HTTP {r.status_code}, staged={len(j.get('staged', {}))}")

        # 7. Chat persistence CRUD
        tid = f"live-selftest-{int(time.time())}"
        r_save = c.post("/api/chats/save", json={"id": tid, "title": "", "messages": [{"role": "user", "content": "Live self-test ping"}]})
        r_get = c.get(f"/api/chats/{tid}")
        j_get = (r_get.get_json(silent=True) or {}).get("chat", {})
        r_ren = c.post("/api/chats/rename", json={"id": tid, "title": "Renamed Self-Test"})
        r_get2 = c.get(f"/api/chats/{tid}")
        j_get2 = (r_get2.get_json(silent=True) or {}).get("chat", {})
        r_del = c.post("/api/chats/delete", json={"id": tid})
        r_404 = c.get(f"/api/chats/{tid}")
        crud_ok = (
            r_save.status_code == 200
            and j_get.get("title") == "Live self-test ping"
            and r_ren.status_code == 200
            and j_get2.get("title") == "Renamed Self-Test"
            and r_del.status_code == 200
            and r_404.status_code == 404
        )
        record("Chat persistence CRUD (save/auto-title/rename/delete)", "POST+GET /api/chats/*", crud_ok, f"auto-title='{j_get.get('title')}', delete→HTTP {r_404.status_code}")

        # 8. Key pool endpoint
        r = c.get("/api/keys")
        record("Key pool status (masked)", "GET /api/keys", r.status_code == 200, f"HTTP {r.status_code}, keys={len(pool.keys)}")

        # 9. Self-update identity awareness in system prompt
        sp = build_queen_system_prompt()
        sp_ok = "/api/self_update/chunk" in sp and "/api/self_update/assemble" in sp and AUTO_UPDATE_REPO in sp
        record("Queen self-update awareness in system prompt", "build_queen_system_prompt()", sp_ok, f"len={len(sp)} chars, repo={AUTO_UPDATE_REPO}")

    summary_color = "\033[1;32m" if failed == 0 else "\033[1;31m"
    _term_print("\033[1;35m" + "─" * 70 + "\033[0m")
    _term_print(f"{summary_color}  RESULT: {passed} passed, {failed} failed (total {len(results)})\033[0m")
    _term_print("\033[1;35m" + "═" * 70 + "\033[0m")

    payload = {
        "ok": failed == 0,
        "version": VERSION,
        "timestamp": ts,
        "passed": passed,
        "failed": failed,
        "results": results,
    }
    broadcast_event({"type": "live_selftest", **payload})
    return payload


@app.route("/api/test/live", methods=["GET", "POST"])
def api_test_live():
    """Run the visible live self-test suite, printing output in Queen's server window."""
    return jsonify(run_live_selftest())

@app.get("/api/models")
def get_models():
    if not pool.keys:
        return jsonify(models=[DEFAULT_MODEL, "openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.6-27b"], default=DEFAULT_MODEL, pricing=MODEL_PRICING, needs_key=True)
    try:
        client = Groq(api_key=pool.keys[0], max_retries=0)
        data = client.models.list()
        chat_models = [m.id for m in data.data if "whisper" not in m.id and "guard" not in m.id]
        if not chat_models:
            chat_models = [DEFAULT_MODEL, "openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.6-27b"]
        return jsonify(models=chat_models, default=DEFAULT_MODEL, pricing=MODEL_PRICING)
    except Exception as exc:
        return jsonify(models=[DEFAULT_MODEL, "openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.6-27b"], default=DEFAULT_MODEL, pricing=MODEL_PRICING, error=str(exc))

@app.get("/api/billing")
def get_billing():
    ledger = load_ledger()
    api_info = {"confirmed": False, "ok": False}

    if not pool.keys:
        return jsonify(
            total_spent=round(ledger.get("total_spent", 0.0), 6),
            total_tokens=ledger.get("total_tokens", 0),
            total_prompt_tokens=ledger.get("total_prompt_tokens", 0),
            total_completion_tokens=ledger.get("total_completion_tokens", 0),
            prompts_count=ledger.get("prompts_count", 0),
            recent_history=ledger.get("history", [])[-15:],
            api={"ok": False, "confirmed": False, "error": "No API key configured. Click '📥 Import Keys' to add your key file."},
            pricing=MODEL_PRICING
        )

    for key in pool.keys:
        try:
            client = Groq(api_key=key, max_retries=0)
            raw = client.models.with_raw_response.list()
            h = dict(raw.headers)
            api_info = {
                "ok": True,
                "confirmed": True,
                "region": h.get("x-groq-region", "fra"),
                "request_id": h.get("x-request-id", "live-check"),
                "rate_limit_limit_requests": h.get("x-ratelimit-limit-requests", "500000"),
                "rate_limit_limit_tokens": h.get("x-ratelimit-limit-tokens", "250000"),
                "rate_limit_remaining_requests": h.get("x-ratelimit-remaining-requests", "N/A"),
                "rate_limit_remaining_tokens": h.get("x-ratelimit-remaining-tokens", "N/A"),
                "rate_limit_reset_tokens": h.get("x-ratelimit-reset-tokens", "0ms"),
                "verified_at": time.strftime("%H:%M:%S"),
                "active_key": pool._mask(key)
            }
            break
        except Exception as exc:
            api_info["error"] = str(exc)

    return jsonify(
        total_spent=round(ledger.get("total_spent", 0.0), 6),
        total_tokens=ledger.get("total_tokens", 0),
        total_prompt_tokens=ledger.get("total_prompt_tokens", 0),
        total_completion_tokens=ledger.get("total_completion_tokens", 0),
        prompts_count=ledger.get("prompts_count", 0),
        recent_history=ledger.get("history", [])[-15:],
        api=api_info,
        pricing=MODEL_PRICING
    )

def raw_keyboard_listener(server, url):
    if not sys.stdin.isatty():
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        return

    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            rlist, _, _ = select.select([sys.stdin], [], [], 0.3)
            if rlist:
                ch = sys.stdin.read(1)
                if ch in ('q', 'Q', '\x03', '\x04'):
                    print("\r\n\033[1;31m[q pressed] Quitting Groq Chat server cleanly...\033[0m")
                    break
                elif ch in ('c', 'C', 'o', 'O'):
                    print(f"\r\n\033[1;36m[c pressed] Kicking in browser with {url}...\033[0m")
                    webbrowser.open(url)
                elif ch in ('g', 'G'):
                    print("\r\n\033[1;35m[GitHub] Reading repositories...\033[0m")
                    ok, out = run_gh(["repo", "list", "--limit", "5"])
                    print(out if ok else f"Error: {out}")
                elif ch in ('s', 'S'):
                    ledger = load_ledger()
                    spent_str = f"${ledger.get('total_spent', 0.0):.6f}"
                    toks = ledger.get('total_tokens', 0)
                    key_count = len(pool.keys)
                    active = pool._mask(pool.keys[0]) if key_count else "None configured"
                    print(f"\r\n\033[1;32m[Status] Spend: {spent_str} | Tokens: {toks:,} | Active Key: {active}\033[0m")
                elif ch in ('r', 'R'):
                    pool.reset()
                    print("\r\n\033[1;32m[Reset] Key pool cooldowns cleared.\033[0m")
                elif ch in ('t', 'T'):
                    run_live_selftest()
                elif ch in ('h', '?', '\r', '\n'):
                    print("\r\n\033[1m[Controls]\033[0m \033[1;31m'q'\033[0m: quit | \033[1;36m'c'\033[0m: browser | \033[1;35m'g'\033[0m: github | \033[1;32m's'\033[0m: spend | \033[1;33m'r'\033[0m: reset | \033[1;35m't'\033[0m: live test")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

def main():
    requested_port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    port = find_first_available_port(requested_port)
    url = f"http://127.0.0.1:{port}"

    try:
        HOME.mkdir(parents=True, exist_ok=True)
        PORT_FILE.write_text(str(port), encoding="utf-8")
        URL_FILE.write_text(url, encoding="utf-8")
    except Exception:
        pass

    for name in ("waitress", "werkzeug", "flask.app"):
        logging.getLogger(name).setLevel(logging.ERROR)

    server = create_server(
        app,
        host="127.0.0.1",
        port=port,
        threads=8,
        channel_timeout=600,
        ident=f"groq-modern-chat-v{VERSION}",
    )

    def run_safe():
        try:
            server.run()
        except Exception:
            pass

    server_thread = threading.Thread(target=run_safe, daemon=True)
    server_thread.start()

    def kick_in_browser():
        time.sleep(0.35)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=kick_in_browser, daemon=True).start()

    print("\033[1;36m" + "=" * 74 + "\033[0m")
    print(f"\033[1;32m  Groq Modern AI Studio & Chatbot — Version {VERSION} is LIVE\033[0m")
    if port != requested_port:
        print(f"\033[1;33m  Notice:\033[0m Port {requested_port} was busy. Bound to first free port: \033[1;32m{port}\033[0m")
    print(f"\033[1m  URL:\033[0m \033[4;34m{url}\033[0m (kicking in browser)")
    key_info = f"\033[1;32m{len(pool.keys)} key(s) in Key Manager\033[0m" if pool.keys else "\033[1;33mNo keys configured (click '📥 Import Keys')\033[0m"
    print(f"\033[1m  Key Manager:\033[0m {key_info}")
    print(f"\033[1;35m  Back Door:\033[0m POST {url}/api/remote/send | POST {url}/api/test/live | POST {url}/api/terminal/log")
    print(f"\033[1;33m  Raw keyboard controls in this terminal:\033[0m")
    print(f"    • Press \033[1;31m'q'\033[0m to quit the server cleanly")
    print(f"    • Press \033[1;36m'c'\033[0m to kick in browser with this page")
    print(f"    • Press \033[1;35m'g'\033[0m to inspect GitHub repositories")
    print(f"    • Press \033[1;32m's'\033[0m to show spend & billing stats")
    print(f"    • Press \033[1;35m't'\033[0m to run the live visible self-test suite")
    print("\033[1;36m" + "=" * 74 + "\033[0m")

    try:
        raw_keyboard_listener(server, url)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            server.close()
        except Exception:
            pass
        print("\033[1;32mServer stopped cleanly. Goodbye!\033[0m")

if __name__ == "__main__":
    main()
