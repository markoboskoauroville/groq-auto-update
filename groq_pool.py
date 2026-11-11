"""Groq API key pool with automatic fallback.

Keys are read from ~/.groq/keys.txt (one per line). A single GROQ_API_KEY
from ~/.groq/.env or the environment is added as a last resort.

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


class AllKeysExhausted(RuntimeError):
    """Every key is cooling down or rejected."""


class KeyPool:
    def __init__(self, quiet=False):
        self.quiet = quiet
        self.keys = self._load_keys()
        if not self.keys:
            raise RuntimeError(
                "No Groq API keys found. Add them to ~/.groq/keys.txt "
                "or set GROQ_API_KEY in ~/.groq/.env."
            )
        self.state = self._load_state()

    # ----- loading and state -----
    @staticmethod
    def _id(key):
        return hashlib.sha256(key.encode()).hexdigest()[:12]

    @staticmethod
    def _mask(key):
        return f"{key[:6]}...{key[-4:]}"

    def _load_keys(self):
        keys = []
        if KEYS_FILE.exists():
            for line in KEYS_FILE.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    keys.append(line)
        env_key = os.environ.get("GROQ_API_KEY", "").strip()
        if env_key and env_key != "your_api_key_here":
            keys.append(env_key)
        seen, unique = set(), []
        for key in keys:
            if key not in seen:
                seen.add(key)
                unique.append(key)
        return unique

    def _load_state(self):
        try:
            data = json.loads(STATE_FILE.read_text())
        except (OSError, ValueError):
            data = {}
        return {
            "current": data.get("current"),
            "cooldown": data.get("cooldown", {}),
        }

    def _save_state(self):
        try:
            tmp = STATE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.state))
            os.chmod(tmp, 0o600)
            tmp.replace(STATE_FILE)
        except OSError:
            pass

    # ----- key selection -----
    def _ordered(self):
        ids = [self._id(k) for k in self.keys]
        current = self.state.get("current")
        start = ids.index(current) if current in ids else 0
        return self.keys[start:] + self.keys[:start]

    def _wait_for(self, key, model):
        """Seconds until this key may be used for this model again."""
        kid = self._id(key)
        now = time.time()
        cooldown = self.state["cooldown"]
        until = max(cooldown.get(f"{kid}:*", 0), cooldown.get(f"{kid}:{model}", 0))
        return max(0.0, until - now)

    def _candidates(self, model):
        return [k for k in self._ordered() if self._wait_for(k, model) <= 0]

    def _cool(self, key, model, exc):
        kid = self._id(key)
        if isinstance(exc, (AuthenticationError, PermissionDeniedError)):
            scope, seconds = "*", REJECTED_COOLDOWN
        else:
            scope, seconds = model, DEFAULT_RATE_COOLDOWN
            try:
                seconds = float(exc.response.headers.get("retry-after"))
            except (AttributeError, TypeError, ValueError):
                pass
            seconds = max(seconds, 5.0)
        self.state["cooldown"][f"{kid}:{scope}"] = time.time() + seconds
        self._save_state()
        if not self.quiet:
            index = self.keys.index(key) + 1
            reason = "rejected" if scope == "*" else f"rate limited on {model}"
            print(
                f"[groq] key #{index} {reason}, switching to the next key",
                file=sys.stderr,
            )

    def _good(self, key, model):
        kid = self._id(key)
        changed = self.state.get("current") != kid
        self.state["current"] = kid
        if self.state["cooldown"].pop(f"{kid}:{model}", None) is not None:
            changed = True
        if changed:
            self._save_state()

    def _exhausted(self, model):
        soonest = min(self._wait_for(k, model) for k in self.keys)
        return AllKeysExhausted(
            f"All {len(self.keys)} Groq API keys are exhausted or rejected. "
            f"The soonest one recovers in about {int(soonest)} seconds. "
            "Run groq-cli --status for details."
        )

    # ----- public API -----
    def complete(self, messages, model=None, **kwargs):
        """Non streaming chat completion with automatic key fallback."""
        model = model or DEFAULT_MODEL
        for key in self._candidates(model):
            client = Groq(api_key=key, max_retries=0)
            try:
                response = client.chat.completions.create(
                    model=model, messages=messages, **kwargs
                )
            except ROTATE_ON as exc:
                self._cool(key, model, exc)
                continue
            self._good(key, model)
            return response
        raise self._exhausted(model)

    def stream(self, messages, model=None, **kwargs):
        """Streaming chat completion. Yields chunks.

        Switching keys is only possible before the first chunk arrives. If a
        key fails halfway through a reply, the error is raised instead, so the
        output is never duplicated.
        """
        model = model or DEFAULT_MODEL
        for key in self._candidates(model):
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
                self._cool(key, model, exc)
                continue
            self._good(key, model)
            return
        raise self._exhausted(model)

    def status(self):
        """Return a list of (index, masked key, note) for every key."""
        now = time.time()
        rows = []
        for index, key in enumerate(self.keys, start=1):
            kid = self._id(key)
            notes = []
            for name, until in self.state["cooldown"].items():
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

    def reset(self):
        """Forget all cooldowns."""
        self.state["cooldown"] = {}
        self._save_state()
