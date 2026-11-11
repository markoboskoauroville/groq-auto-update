"""Groq API key pool with automatic fallback (shared by Queen web studio and groq-cli).

Keys are read from ~/.groq/keys.txt (noise-tolerant: extracts clean `gsk_...` keys
from .txt, .env, JSON, bash exports, or logs). A single GROQ_API_KEY from
~/.groq/.env or the environment is added as a fallback.

The pool is sticky: it keeps using the last key that worked and only moves
to the next one when the current key is rate limited, out of quota, or
rejected. Cooldowns are remembered between runs in ~/.groq/key_state.json.

Use from your own Python code:

    import os, sys
    sys.path.insert(0, os.path.expanduser("~/.groq"))
    from groq_pool import KeyPool

    pool = KeyPool()
    reply = pool.complete([{"role": "user", "content": "Hello"}])
    print(reply.choices[0].message.content)
"""
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from groq import (
    AuthenticationError,
    Groq,
    PermissionDeniedError,
    RateLimitError,
)

HOME = Path.home() / ".groq"
KEYS_FILE = HOME / "keys.txt"
STATE_FILE = HOME / "key_state.json"

load_dotenv(HOME / ".env")
DEFAULT_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

# Errors that mean "this key cannot serve the request right now".
ROTATE_ON = (RateLimitError, AuthenticationError, PermissionDeniedError)
REJECTED_COOLDOWN = 30 * 24 * 3600  # invalid or blocked keys: retry in 30 days
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


class AllKeysExhausted(RuntimeError):
    """Every key is cooling down or rejected."""


class DynamicKeyPool:
    """Unified mutable key pool used by Queen (`qwen_app/app.py`) and `KeyPool` (`groq-cli`)."""

    def __init__(self, quiet: bool = True, include_env: bool = True):
        self.quiet = quiet
        self.include_env = include_env
        self.keys: list[str] = []
        self.state: dict = {"current": None, "cooldown": {}}
        self.reload()

    @staticmethod
    def _id(key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest()[:12]

    @staticmethod
    def _mask(key: str) -> str:
        return f"{key[:6]}...{key[-4:]}" if len(key) >= 10 else key

    def reload(self):
        keys: list[str] = []
        if KEYS_FILE.exists():
            try:
                content = KEYS_FILE.read_text(encoding="utf-8")
                keys = extract_keys_from_noise(content)
            except Exception:
                pass
        if self.include_env:
            env_key = os.environ.get("GROQ_API_KEY", "").strip()
            if env_key and env_key != "your_api_key_here":
                keys.extend(extract_keys_from_noise(env_key))
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
        self.keys = list(dict.fromkeys(self.keys + valid_incoming))
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
                data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                self.state = {
                    "current": data.get("current"),
                    "cooldown": data.get("cooldown", {}),
                }
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
            HOME.mkdir(parents=True, exist_ok=True)
            tmp = STATE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.state), encoding="utf-8")
            os.chmod(tmp, 0o600)
            tmp.replace(STATE_FILE)
        except Exception:
            pass

    def _ordered(self) -> list[str]:
        if not self.keys:
            return []
        ids = [self._id(k) for k in self.keys]
        curr = self.state.get("current")
        start = ids.index(curr) if curr in ids else 0
        return self.keys[start:] + self.keys[:start]

    def _wait_for(self, key: str, model: str) -> float:
        kid = self._id(key)
        now = time.time()
        cooldown = self.state.get("cooldown", {})
        until = max(cooldown.get(f"{kid}:*", 0), cooldown.get(f"{kid}:{model}", 0))
        return max(0.0, until - now)

    def candidates(self, model: str, strict: bool = False) -> list[str]:
        if not self.keys:
            return []
        ordered = self._ordered()
        ready = [k for k in ordered if self._wait_for(k, model) <= 0]
        if strict:
            return ready
        return ready if ready else ordered

    def cool(self, key: str, model: str, exc: Exception):
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
        if not self.quiet and key in self.keys:
            index = self.keys.index(key) + 1
            reason = "rejected" if scope == "*" else f"rate limited on {model}"
            print(
                f"[groq] key #{index} {reason}, switching to the next key",
                file=sys.stderr,
            )

    def good(self, key: str, model: str):
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

    def status_rich(self) -> list[dict]:
        now = time.time()
        items = []
        curr = self.state.get("current")
        for index, key in enumerate(self.keys, start=1):
            kid = self._id(key)
            is_active = kid == curr
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
                "cooldowns": cooldowns,
            })
        return items

    def status_legacy(self) -> list[tuple[int, str, str]]:
        return [(item["index"], item["masked"], item["status"]) for item in self.status_rich()]


class KeyPool(DynamicKeyPool):
    """CLI-compatible wrapper around `DynamicKeyPool` (raises on empty pool, strict cooldowns)."""

    def __init__(self, quiet: bool = False):
        super().__init__(quiet=quiet, include_env=True)
        if not self.keys:
            raise RuntimeError(
                "No Groq API keys found. Add them to ~/.groq/keys.txt "
                "or set GROQ_API_KEY in ~/.groq/.env."
            )

    def _exhausted(self, model: str) -> AllKeysExhausted:
        soonest = min(self._wait_for(k, model) for k in self.keys)
        return AllKeysExhausted(
            f"All {len(self.keys)} Groq API keys are exhausted or rejected. "
            f"The soonest one recovers in about {int(soonest)} seconds. "
            "Run groq-cli --status for details."
        )

    def complete(self, messages, model=None, **kwargs):
        """Non-streaming chat completion with automatic key fallback."""
        model = model or DEFAULT_MODEL
        for key in self.candidates(model, strict=True):
            client = Groq(api_key=key, max_retries=0)
            try:
                response = client.chat.completions.create(
                    model=model, messages=messages, **kwargs
                )
            except ROTATE_ON as exc:
                self.cool(key, model, exc)
                continue
            self.good(key, model)
            return response
        raise self._exhausted(model)

    def stream(self, messages, model=None, **kwargs):
        """Streaming chat completion. Yields chunks; rotates only before first chunk."""
        model = model or DEFAULT_MODEL
        for key in self.candidates(model, strict=True):
            client = Groq(api_key=key, max_retries=0)
            started = False
            try:
                response = client.chat.completions.create(
                    model=model, messages=messages, stream=True, **kwargs
                )
                for chunk in response:
                    started = True
                    yield chunk
            except ROTATE_ON as exc:
                if started:
                    raise
                self.cool(key, model, exc)
                continue
            self.good(key, model)
            return
        raise self._exhausted(model)

    def status(self):
        """Return a list of (index, masked key, note) for every key."""
        now = time.time()
        rows = []
        for index, key in enumerate(self.keys, start=1):
            kid = self._id(key)
            notes = []
            for name, until in self.state.get("cooldown", {}).items():
                if not name.startswith(kid + ":") or until <= now:
                    continue
                scope = name.split(":", 1)[1]
                wait = int(until - now)
                if scope == "*":
                    notes.append("rejected or blocked")
                else:
                    notes.append(f"rate limited on {scope} for {wait}s")
            if kid == self.state.get("current") and not notes:
                notes.append("ready (current)")
            rows.append((index, self._mask(key), "; ".join(notes) or "ready"))
        return rows
