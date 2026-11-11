"""Modern Groq Chatbot Server — Version 09.

Features:
- Groq Thunderstrike SVG Favicon & Brand Icon
- Noise-Tolerant Key Parser (extracts clean Groq keys from messy logs, configs, .env, json)
- Key Manager with interactive key pool, live failover, and key deletion
- Automatic Code Box Detection (detects 'in the code box' in prompts and activates code mode)
- Full SSE Streaming /api/chat & Backdoor /api/remote/send
- Dynamic Port Allocation (checks busy ports, binds first free)
- Live Groq API Spend Ledger & Token Tracking
- Raw Terminal Keyboard Controls ('q' to quit, 'c' for browser)
"""
import base64
import hashlib
import json
import logging
import os
import queue
import re
import select
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

VERSION = "09"
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

    groq_msgs = []
    if system_prompt:
        groq_msgs.append({"role": "system", "content": system_prompt})
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

    groq_msgs = []
    if system_prompt:
        groq_msgs.append({"role": "system", "content": system_prompt})
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

@app.get("/health")
def health():
    return jsonify(app="groq-modern-chat", version=VERSION, ok=True, default_model=DEFAULT_MODEL, has_keys=len(pool.keys) > 0)

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
                elif ch in ('h', '?', '\r', '\n'):
                    print("\r\n\033[1m[Controls]\033[0m \033[1;31m'q'\033[0m: quit | \033[1;36m'c'\033[0m: browser | \033[1;35m'g'\033[0m: github | \033[1;32m's'\033[0m: spend | \033[1;33m'r'\033[0m: reset")
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
    print(f"\033[1;35m  Back Door:\033[0m POST {url}/api/remote/send | POST {url}/api/keys/load-file")
    print(f"\033[1;33m  Raw keyboard controls in this terminal:\033[0m")
    print(f"    • Press \033[1;31m'q'\033[0m to quit the server cleanly")
    print(f"    • Press \033[1;36m'c'\033[0m to kick in browser with this page")
    print(f"    • Press \033[1;35m'g'\033[0m to inspect GitHub repositories")
    print(f"    • Press \033[1;32m's'\033[0m to show spend & billing stats")
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
