"""Queen (`qwen`) — Dual-Kind API Loader & Pre-Briefed Surgical Auto-Update Engine.

Supports:
1. Noise-tolerant multi-provider key extraction (Kind 1: Groq `gsk_...`, Kind 2: Google Cloud/Gemini `AIza...` & Anthropic Claude `sk-ant-...`).
2. Secure `0600` key & provider/model configuration persistence in `~/.groq/auto_update_keys.json` (masked in all API responses).
3. Live model catalog discovery + exact per-1M USD token pricing for Google & Anthropic.
4. Pre-briefed surgical context slicing so external APIs update Queen in pennies via `<queen_update>` JSON patches (`replace`, `insert_after`, `insert_before`).
5. End-to-end 6-stage educational pipeline ("Learning by Watching"):
   Repo check/clone/pull -> Streaming model plan -> Surgical patch + unified diff -> CI validation (`ci_run_all`) -> Backup + Git push (origin & auto-update) + local `~/.groq` sync -> Exact USD cost receipt printed in terminal & split-screen UI.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

import httpx

HOME = Path.home() / ".groq"
AUTO_UPDATE_KEYS_FILE = HOME / "auto_update_keys.json"
AUTO_UPDATE_LEDGER_FILE = HOME / "auto_update_ledger.json"
DOWNLOADS_API_DIR = Path.home() / "Downloads" / "API"

PRIMARY_GITHUB_REPO = "markoboskoauroville/groq_ai_studio"
MIRROR_GITHUB_REPO = "markoboskoauroville/groq-auto-update"
DEV_REPO_DEFAULT = Path.home() / "Developer" / "groq_ai_studio"

# Regex extractors (compiled without literal secret prefixes that look like real keys)
RE_GROQ_KEY = re.compile(r"\bgsk_[A-Za-z0-9_-]{20,}\b")
RE_ANTHROPIC_KEY = re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")
RE_GOOGLE_KEY = re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")
RE_GCLOUD_BEARER = re.compile(r"\bya29\.[0-9A-Za-z._-]{30,}\b")

# Curated models per provider (ordered best surgical default first)
CURATED_PROVIDER_MODELS: dict[str, list[dict[str, Any]]] = {
    "google": [
        {"id": "gemini-2.5-flash", "label": "Gemini 2.5 Flash (Fast Surgical · $0.30/$2.50)"},
        {"id": "gemini-2.5-pro", "label": "Gemini 2.5 Pro (Deep Architect · $1.25/$10.00)"},
        {"id": "gemini-2.5-flash-lite", "label": "Gemini 2.5 Flash-Lite (Ultra-Cheap · $0.10/$0.40)"},
        {"id": "gemini-2.0-flash", "label": "Gemini 2.0 Flash ($0.10/$0.40)"},
    ],
    "anthropic": [
        {"id": "claude-sonnet-4-5", "label": "Claude Sonnet 4.5 (Surgical Engineer · $3/$15)"},
        {"id": "claude-haiku-4-5", "label": "Claude Haiku 4.5 (Fast & Cheap · $1/$5)"},
        {"id": "claude-opus-4-5", "label": "Claude Opus 4.5 (Flagship · $5/$25)"},
        {"id": "claude-3-7-sonnet-latest", "label": "Claude 3.7 Sonnet ($3/$15)"},
        {"id": "claude-3-5-haiku-latest", "label": "Claude 3.5 Haiku ($0.80/$4)"},
    ],
}

# Exact USD per 1,000,000 tokens: (input_usd, output_usd, cache_write_usd, cache_read_usd)
AUTO_UPDATE_PRICING: dict[str, tuple[float, float, float, float]] = {
    # Google Gemini / Cloud
    "gemini-2.5-flash": (0.30, 2.50, 0.30, 0.075),
    "gemini-2.5-flash-lite": (0.10, 0.40, 0.10, 0.025),
    "gemini-2.5-pro": (1.25, 10.00, 1.25, 0.31),
    "gemini-2.0-flash": (0.10, 0.40, 0.10, 0.025),
    "gemini-1.5-pro": (1.25, 5.00, 1.25, 0.31),
    "gemini-1.5-flash": (0.075, 0.30, 0.075, 0.018),
    # Anthropic Claude
    "claude-sonnet-4-5": (3.00, 15.00, 3.75, 0.30),
    "claude-sonnet-4-20250514": (3.00, 15.00, 3.75, 0.30),
    "claude-3-7-sonnet-latest": (3.00, 15.00, 3.75, 0.30),
    "claude-3-5-sonnet-latest": (3.00, 15.00, 3.75, 0.30),
    "claude-haiku-4-5": (1.00, 5.00, 1.25, 0.10),
    "claude-3-5-haiku-latest": (0.80, 4.00, 1.00, 0.08),
    "claude-opus-4-5": (5.00, 25.00, 6.25, 0.50),
    "claude-opus-4-1": (15.00, 75.00, 18.75, 1.50),
}

EDUCATIONAL_STAGES = [
    {
        "stage": 1,
        "id": "repo_context",
        "title": "1. Repo Sync & Pre-Briefed Code Map",
        "lesson": "Real engineers never edit blind. First we verify the git repository (`~/Developer/groq_ai_studio`), check branch health, and index exact line numbers & anchors so we only touch the lines that need changing.",
    },
    {
        "stage": 2,
        "id": "model_plan",
        "title": "2. AI Architect Plan & Streaming Patch Spec",
        "lesson": "Instead of rewriting a 2,600-line file (slow & expensive), the model receives a pre-prepared map and streams compact surgical `SEARCH -> REPLACE` blocks—using ~95% fewer tokens.",
    },
    {
        "stage": 3,
        "id": "surgical_patch",
        "title": "3. Surgical In-Memory Patching & Unified Diff",
        "lesson": "Patches are applied in memory first—never straight onto live disk files—and converted into a standard Unified Diff (`-` removed, `+` added) so every single line change is inspectable.",
    },
    {
        "stage": 4,
        "id": "ci_gate",
        "title": "4. Automated CI Validation Gate",
        "lesson": "Before saving anything, Continuous Integration (`ci_run_all`) parses Python into an Abstract Syntax Tree (`ast.parse`), verifies HTML/JS tag & brace balance, and blocks truncated files.",
    },
    {
        "stage": 5,
        "id": "deploy_sync",
        "title": "5. Backup, Dual-Remote Git Push & Local `~/.groq` Sync",
        "lesson": "Once CI passes, we snapshot a rollback backup, write to the git repo, bump `version.json`, sync the installed runtime in `~/.groq`, and push to GitHub (`origin` + `auto-update`).",
    },
    {
        "stage": 6,
        "id": "cost_complete",
        "title": "6. Exact Token Accounting & USD Cost Receipt",
        "lesson": "Production systems meter every API call. We read exact input/output/cached token counts from the provider stream and log the USD cost in `~/.groq/auto_update_ledger.json`.",
    },
]

_STATE_LOCK = threading.Lock()
_JOB_STATE: dict[str, Any] = {
    "running": False,
    "job_id": None,
    "provider": "google",
    "model": "gemini-2.5-flash",
    "instruction": "",
    "current_stage": 0,
    "working_on": "Idle — Ready for surgical update",
    "events": [],
    "last_result": None,
    "started_at": None,
}
_SERVER_BOOT_TS = time.time()


def mask_secret(key: str) -> str:
    """Mask any API key safely for UI/terminal display."""
    if not key:
        return ""
    k = key.strip()
    if len(k) <= 12:
        return k[:3] + "…" + k[-2:]
    return f"{k[:7]}…{k[-4:]}"


def key_fingerprint(key: str) -> str:
    """Short non-reversible ID for deleting a specific key from the UI."""
    return hashlib.sha256(key.strip().encode("utf-8")).hexdigest()[:12]


def redact_secrets(text: str) -> str:
    """Scrub any accidental raw key pattern from error/log strings."""
    if not text:
        return ""
    out = RE_GROQ_KEY.sub(lambda m: mask_secret(m.group(0)), text)
    out = RE_ANTHROPIC_KEY.sub(lambda m: mask_secret(m.group(0)), out)
    out = RE_GOOGLE_KEY.sub(lambda m: mask_secret(m.group(0)), out)
    out = RE_GCLOUD_BEARER.sub("ya29.…REDACTED", out)
    return out


def extract_multi_provider_keys(raw_text: str) -> dict[str, list[str]]:
    """Extract Kind 1 (`groq`) and Kind 2 (`google`, `anthropic`) keys from any noisy text."""
    if not raw_text:
        return {"groq": [], "anthropic": [], "google": []}

    def _dedupe(items: list[str]) -> list[str]:
        seen: set[str] = set()
        res: list[str] = []
        for item in items:
            cleaned = item.strip().strip("'\"`,;)")
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                res.append(cleaned)
        return res

    groq_keys = _dedupe(RE_GROQ_KEY.findall(raw_text))
    anthropic_keys = _dedupe(RE_ANTHROPIC_KEY.findall(raw_text))
    google_keys = _dedupe(RE_GOOGLE_KEY.findall(raw_text) + RE_GCLOUD_BEARER.findall(raw_text))
    return {
        "groq": groq_keys,
        "anthropic": anthropic_keys,
        "google": google_keys,
    }


def _default_config() -> dict[str, Any]:
    return {
        "active_provider": "google",
        "active_models": {
            "google": "gemini-2.5-flash",
            "anthropic": "claude-sonnet-4-5",
        },
        "keys": {
            "google": [],
            "anthropic": [],
        },
    }


def load_auto_update_store(path: Path = AUTO_UPDATE_KEYS_FILE) -> dict[str, Any]:
    """Load Kind 2 auto-update config & keys (`0600`)."""
    cfg = _default_config()
    try:
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if raw.get("active_provider") in ("google", "anthropic"):
                cfg["active_provider"] = raw["active_provider"]
            if isinstance(raw.get("active_models"), dict):
                for p in ("google", "anthropic"):
                    if raw["active_models"].get(p):
                        cfg["active_models"][p] = str(raw["active_models"][p])
            if isinstance(raw.get("keys"), dict):
                for p in ("google", "anthropic"):
                    vals = raw["keys"].get(p, [])
                    if isinstance(vals, list):
                        cfg["keys"][p] = [str(v).strip() for v in vals if str(v).strip()]
    except Exception:
        pass
    return cfg


def save_auto_update_store(cfg: dict[str, Any], path: Path = AUTO_UPDATE_KEYS_FILE) -> None:
    """Atomically write `~/.groq/auto_update_keys.json` with mode `0600`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.stem}.{os.getpid()}.{int(time.time()*1000000)}.tmp")
    tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def get_public_auto_update_config(
    flask_port: int = 8765,
    app_version: str = "v4",
    groq_key_count: int = 0,
    store_path: Path = AUTO_UPDATE_KEYS_FILE,
) -> dict[str, Any]:
    """Return masked, UI-safe configuration for both API kinds + Flask status."""
    cfg = load_auto_update_store(store_path)
    provider = cfg["active_provider"]
    active_model = cfg["active_models"].get(provider) or CURATED_PROVIDER_MODELS[provider][0]["id"]

    masked_keys: dict[str, list[dict[str, Any]]] = {"google": [], "anthropic": []}
    for p in ("google", "anthropic"):
        for idx, k in enumerate(cfg["keys"].get(p, [])):
            masked_keys[p].append({
                "id": key_fingerprint(k),
                "index": idx,
                "provider": p,
                "masked": mask_secret(k),
                "active": idx == 0,
                "auth_type": "oauth_bearer" if k.startswith("ya29.") else "api_key",
            })

    ledger = load_auto_update_ledger()
    return {
        "ok": True,
        "active_provider": provider,
        "active_model": active_model,
        "active_models": cfg["active_models"],
        "providers": {
            "google": {
                "name": "Google Cloud / Gemini",
                "configured": len(masked_keys["google"]) > 0,
                "count": len(masked_keys["google"]),
                "active_key": masked_keys["google"][0]["masked"] if masked_keys["google"] else None,
                "items": masked_keys["google"],
                "models": CURATED_PROVIDER_MODELS["google"],
            },
            "anthropic": {
                "name": "Anthropic / Claude",
                "configured": len(masked_keys["anthropic"]) > 0,
                "count": len(masked_keys["anthropic"]),
                "active_key": masked_keys["anthropic"][0]["masked"] if masked_keys["anthropic"] else None,
                "items": masked_keys["anthropic"],
                "models": CURATED_PROVIDER_MODELS["anthropic"],
            },
        },
        "groq_chat_api": {
            "kind": "groq",
            "name": "Groq LPU Chat API",
            "configured": groq_key_count > 0,
            "count": groq_key_count,
        },
        "pricing_per_1m_usd": {
            m: {"input": r[0], "output": r[1], "cache_write": r[2], "cache_read": r[3]}
            for m, r in AUTO_UPDATE_PRICING.items()
        },
        "ledger_summary": {
            "total_spent_usd": round(float(ledger.get("total_spent_usd", 0.0)), 6),
            "updates_count": int(ledger.get("updates_count", 0)),
        },
        "flask_server": {
            "status": "online",
            "port": flask_port,
            "pid": os.getpid(),
            "uptime_sec": int(time.time() - _SERVER_BOOT_TS),
            "version": app_version,
            "primary_repo": PRIMARY_GITHUB_REPO,
            "mirror_repo": MIRROR_GITHUB_REPO,
        },
        "stages": EDUCATIONAL_STAGES,
    }


def set_auto_update_selection(
    provider: str | None = None,
    model: str | None = None,
    store_path: Path = AUTO_UPDATE_KEYS_FILE,
) -> dict[str, Any]:
    """Update active provider ('google' or 'anthropic') and/or active model."""
    with _STATE_LOCK:
        cfg = load_auto_update_store(store_path)
        if provider:
            p = provider.strip().lower()
            if p not in ("google", "anthropic"):
                raise ValueError("Provider must be 'google' or 'anthropic'")
            cfg["active_provider"] = p
        target_p = cfg["active_provider"]
        if model and model.strip():
            cfg["active_models"][target_p] = model.strip()
        save_auto_update_store(cfg, store_path)
        return cfg


def add_auto_update_keys(
    extracted: dict[str, list[str]],
    store_path: Path = AUTO_UPDATE_KEYS_FILE,
) -> dict[str, int]:
    """Store extracted Google and Anthropic keys into `~/.groq/auto_update_keys.json`."""
    added_counts = {"google": 0, "anthropic": 0}
    with _STATE_LOCK:
        cfg = load_auto_update_store(store_path)
        for p in ("google", "anthropic"):
            existing = cfg["keys"].setdefault(p, [])
            for k in extracted.get(p, []):
                if k not in existing:
                    existing.append(k)
                    added_counts[p] += 1
        # Auto-select newly populated provider if current active provider has no key yet
        cur = cfg["active_provider"]
        if not cfg["keys"].get(cur):
            if cfg["keys"].get("google"):
                cfg["active_provider"] = "google"
            elif cfg["keys"].get("anthropic"):
                cfg["active_provider"] = "anthropic"
        save_auto_update_store(cfg, store_path)
    return added_counts


def delete_auto_update_key(
    provider: str,
    key_id: str = "",
    clear_all: bool = False,
    store_path: Path = AUTO_UPDATE_KEYS_FILE,
) -> bool:
    p = (provider or "").strip().lower()
    if p not in ("google", "anthropic"):
        return False
    with _STATE_LOCK:
        cfg = load_auto_update_store(store_path)
        old = list(cfg["keys"].get(p, []))
        if clear_all:
            cfg["keys"][p] = []
            save_auto_update_store(cfg, store_path)
            return len(old) > 0
        kept = [k for k in old if key_fingerprint(k) != key_id]
        if len(kept) == len(old):
            return False
        cfg["keys"][p] = kept
        save_auto_update_store(cfg, store_path)
        return True


def discover_keys_from_downloads(
    api_dir: Path = DOWNLOADS_API_DIR,
    groq_pool: Any = None,
    store_path: Path = AUTO_UPDATE_KEYS_FILE,
) -> dict[str, Any]:
    """Scan `~/Downloads/API/` for Groq, Google Gemini, and Anthropic Claude key files safely."""
    candidate_files = [
        "groq-api.txt",
        "gemini_key.txt",
        "VOICES_gemini-free-tier-api.txt",
        "Claude.api.txt",
        "HAIKU-KEY.txt",
    ]
    combined_extracted: dict[str, list[str]] = {"groq": [], "anthropic": [], "google": []}
    scanned: list[str] = []

    if api_dir.is_dir():
        for fname in candidate_files:
            fpath = api_dir / fname
            if fpath.is_file():
                try:
                    txt = fpath.read_text(encoding="utf-8", errors="replace")
                    ext = extract_multi_provider_keys(txt)
                    for k_type in ("groq", "anthropic", "google"):
                        for k in ext[k_type]:
                            if k not in combined_extracted[k_type]:
                                combined_extracted[k_type].append(k)
                    scanned.append(fname)
                except Exception:
                    pass

    groq_added = 0
    if groq_pool is not None and combined_extracted["groq"]:
        groq_added, _ = groq_pool.add_keys(combined_extracted["groq"])

    au_added = add_auto_update_keys(combined_extracted, store_path=store_path)
    return {
        "ok": True,
        "scanned_files": scanned,
        "added": {
            "groq": groq_added,
            "google": au_added["google"],
            "anthropic": au_added["anthropic"],
        },
        "found_totals": {
            "groq": len(combined_extracted["groq"]),
            "google": len(combined_extracted["google"]),
            "anthropic": len(combined_extracted["anthropic"]),
        },
    }


def fetch_provider_models(provider: str, store_path: Path = AUTO_UPDATE_KEYS_FILE) -> dict[str, Any]:
    """Return curated + live API models for Google or Anthropic."""
    p = (provider or "google").strip().lower()
    if p not in ("google", "anthropic"):
        p = "google"
    cfg = load_auto_update_store(store_path)
    curated = list(CURATED_PROVIDER_MODELS[p])
    curated_ids = [m["id"] for m in curated]
    keys = cfg["keys"].get(p, [])
    live_ids: list[str] = []
    live_ok = False
    live_err = None

    if keys:
        key = keys[0]
        try:
            with httpx.Client(timeout=8.0) as client:
                if p == "google":
                    headers = {}
                    url = "https://generativelanguage.googleapis.com/v1beta/models"
                    if key.startswith("ya29."):
                        headers["Authorization"] = f"Bearer {key}"
                    else:
                        url = f"{url}?key={key}"
                    r = client.get(url, headers=headers)
                    if r.status_code == 200:
                        live_ok = True
                        for item in r.json().get("models", []):
                            methods = item.get("supportedGenerationMethods") or []
                            name = (item.get("name") or "").replace("models/", "")
                            if "generateContent" in methods and "gemini" in name and "tts" not in name and "image" not in name:
                                live_ids.append(name)
                    else:
                        live_err = f"HTTP {r.status_code}"
                else:
                    r = client.get(
                        "https://api.anthropic.com/v1/models",
                        headers={
                            "x-api-key": key,
                            "anthropic-version": "2023-06-01",
                        },
                    )
                    if r.status_code == 200:
                        live_ok = True
                        for item in r.json().get("data", []):
                            mid = item.get("id") or ""
                            if mid.startswith("claude-"):
                                live_ids.append(mid)
                    else:
                        live_err = f"HTTP {r.status_code}"
        except Exception as exc:
            live_err = redact_secrets(str(exc))

    merged_models = list(curated)
    for mid in live_ids:
        if mid not in curated_ids:
            rates = get_auto_update_rates(p, mid)
            merged_models.append({
                "id": mid,
                "label": f"{mid} (${rates[0]:g}/${rates[1]:g})",
            })

    return {
        "ok": True,
        "provider": p,
        "active_model": cfg["active_models"].get(p) or curated[0]["id"],
        "configured": len(keys) > 0,
        "live_verified": live_ok,
        "live_error": live_err,
        "models": merged_models,
    }


# ── Pricing & Auto-Update Spend Ledger ───────────────────────────────────────
def get_auto_update_rates(provider: str, model: str) -> tuple[float, float, float, float]:
    """Return `(input_per_1m, output_per_1m, cache_write_per_1m, cache_read_per_1m)` in USD."""
    m = (model or "").strip()
    if m in AUTO_UPDATE_PRICING:
        return AUTO_UPDATE_PRICING[m]
    low = m.lower()
    if provider == "google" or "gemini" in low:
        if "flash-lite" in low:
            return (0.10, 0.40, 0.10, 0.025)
        if "pro" in low:
            return (1.25, 10.00, 1.25, 0.31)
        if "2.0-flash" in low:
            return (0.10, 0.40, 0.10, 0.025)
        return (0.30, 2.50, 0.30, 0.075)
    # Anthropic fallback heuristics
    if "haiku-4-5" in low:
        return (1.00, 5.00, 1.25, 0.10)
    if "haiku" in low:
        return (0.80, 4.00, 1.00, 0.08)
    if "opus-4-5" in low:
        return (5.00, 25.00, 6.25, 0.50)
    if "opus" in low:
        return (15.00, 75.00, 18.75, 1.50)
    return (3.00, 15.00, 3.75, 0.30)


def calculate_auto_update_cost(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_write_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> dict[str, Any]:
    """Compute exact USD cost breakdown for an auto-update API call."""
    in_r, out_r, cw_r, cr_r = get_auto_update_rates(provider, model)
    in_cost = (max(0, input_tokens) / 1_000_000.0) * in_r
    out_cost = (max(0, output_tokens) / 1_000_000.0) * out_r
    cw_cost = (max(0, cache_write_tokens) / 1_000_000.0) * cw_r
    cr_cost = (max(0, cache_read_tokens) / 1_000_000.0) * cr_r
    total_cost = in_cost + out_cost + cw_cost + cr_cost
    return {
        "provider": provider,
        "model": model,
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "cache_write_tokens": int(cache_write_tokens),
        "cache_read_tokens": int(cache_read_tokens),
        "total_tokens": int(input_tokens + output_tokens + cache_write_tokens + cache_read_tokens),
        "rates_per_1m_usd": {
            "input": in_r,
            "output": out_r,
            "cache_write": cw_r,
            "cache_read": cr_r,
        },
        "input_cost_usd": round(in_cost, 8),
        "output_cost_usd": round(out_cost, 8),
        "cache_cost_usd": round(cw_cost + cr_cost, 8),
        "total_cost_usd": round(total_cost, 8),
        "formatted_usd": f"${total_cost:.6f}",
    }


def load_auto_update_ledger(path: Path = AUTO_UPDATE_LEDGER_FILE) -> dict[str, Any]:
    default = {"total_spent_usd": 0.0, "updates_count": 0, "history": []}
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                default.update(data)
    except Exception:
        pass
    return default


def record_auto_update_receipt(
    cost_info: dict[str, Any],
    summary: str,
    files_changed: list[str],
    new_version: str,
    dry_run: bool = False,
    path: Path = AUTO_UPDATE_LEDGER_FILE,
) -> dict[str, Any]:
    with _STATE_LOCK:
        ledger = load_auto_update_ledger(path)
        ledger["total_spent_usd"] = round(
            float(ledger.get("total_spent_usd", 0.0)) + float(cost_info["total_cost_usd"]), 8
        )
        ledger["updates_count"] = int(ledger.get("updates_count", 0)) + 1
        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "provider": cost_info["provider"],
            "model": cost_info["model"],
            "summary": summary,
            "files": files_changed,
            "version": new_version,
            "dry_run": dry_run,
            "input_tokens": cost_info["input_tokens"],
            "output_tokens": cost_info["output_tokens"],
            "total_cost_usd": cost_info["total_cost_usd"],
            "formatted_usd": cost_info["formatted_usd"],
        }
        hist = ledger.get("history", [])
        hist.append(entry)
        ledger["history"] = hist[-100:]
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.stem}.{os.getpid()}.{int(time.time()*1000000)}.tmp")
        tmp.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(path)
        return ledger


# ── Pre-Briefed Code Map & Surgical Patch Engine ─────────────────────────────
def build_surgical_context(
    git_root: Path,
    instruction: str,
    target_files: list[str] | None = None,
) -> tuple[str, list[str]]:
    """Extract compact, exact code slices around relevant anchors so prompts stay small & fast."""
    qwen_dir = git_root / "qwen_app"
    available = ["index.html", "app.py", "auto_updater.py"]
    if target_files:
        chosen = [f for f in target_files if f in available] or available[:2]
    else:
        low = instruction.lower()
        chosen = []
        if any(w in low for w in ("ui", "button", "topbar", "modal", "css", "color", "badge", "html", "banner", "footer", "sidebar", "split", "panel", "title", "header")):
            chosen.append("index.html")
        if any(w in low for w in ("route", "endpoint", "flask", "/api/", "backend", "server", "python", "app.py", "header", "health")):
            chosen.append("app.py")
        if "auto_updater" in low:
            chosen.append("auto_updater.py")
        if not chosen:
            chosen = ["index.html", "app.py"]

    keywords = [
        w.lower()
        for w in re.findall(r"[A-Za-z0-9_#-]{3,}", instruction)
        if w.lower() not in {"the", "and", "for", "with", "into", "from", "that", "this", "add", "please", "update", "make", "app", "queen", "groq"}
    ]

    blocks: list[str] = []
    for fname in chosen:
        fpath = qwen_dir / fname
        if not fpath.exists():
            continue
        lines = fpath.read_text(encoding="utf-8").splitlines()
        total = len(lines)

        # Collect structural landmarks + keyword match windows
        landmarks: list[str] = []
        hit_indices: list[int] = []
        for i, line in enumerate(lines):
            s = line.strip()
            if fname.endswith(".py") and (s.startswith("@app.") or s.startswith("def ") or s.startswith("class ")):
                landmarks.append(f"L{i+1}: {s[:95]}")
            elif fname.endswith(".html") and (
                "id=\"" in s or "<!-- ══" in s or "// ═══" in s
            ):
                if len(landmarks) < 90:
                    landmarks.append(f"L{i+1}: {s[:95]}")
            low_line = line.lower()
            if keywords and any(kw in low_line for kw in keywords):
                hit_indices.append(i)

        # Merge windows around keyword hits (up to 6 windows of +-18 lines) + key structural anchors
        windows: list[tuple[int, int]] = []
        anchor_seeds = hit_indices[:10]
        if fname == "index.html":
            for i, line in enumerate(lines):
                if 'id="topbar"' in line or 'id="status-bar"' in line or "//  INIT" in line:
                    anchor_seeds.append(i)
        elif fname == "app.py":
            for i, line in enumerate(lines):
                if '@app.get("/health")' in line or '@app.get("/api/version")' in line:
                    anchor_seeds.append(i)

        for idx in sorted(set(anchor_seeds)):
            start = max(0, idx - 16)
            end = min(total, idx + 22)
            if windows and start <= windows[-1][1] + 4:
                windows[-1] = (windows[-1][0], max(windows[-1][1], end))
            else:
                windows.append((start, end))
            if len(windows) >= 8:
                break

        # Always include tail of file so appending routes/JS handlers is effortless
        tail_start = max(0, total - 35)
        if not windows or windows[-1][1] < tail_start:
            windows.append((tail_start, total))

        slice_text_parts: list[str] = []
        for s_idx, e_idx in windows:
            snippet = "\n".join(lines[s_idx:e_idx])
            slice_text_parts.append(f"--- {fname} lines {s_idx+1}-{e_idx} (exact verbatim text) ---\n{snippet}")

        blocks.append(
            f"=== FILE: {fname} (total {total} lines) ===\n"
            f"Landmarks:\n" + "\n".join(landmarks[:55]) + "\n\n"
            + "\n\n".join(slice_text_parts)
        )

    return "\n\n".join(blocks), chosen


SURGICAL_SYSTEM_PROMPT = """You are Queen's Principal Auto-Update Software Engineer.
You are updating Groq AI Studio ("Queen" / `qwen`), a local macOS Flask + single-file HTML/JS application:
- Primary GitHub repo: `markoboskoauroville/groq_ai_studio` (local checkout `~/Developer/groq_ai_studio`)
- Auto-update mirror repo: `markoboskoauroville/groq-auto-update`
- Installed runtime: `~/.groq` (`qwen_app/app.py`, `qwen_app/auto_updater.py`, `qwen_app/index.html`)

CRITICAL EFFICIENCY & SAFETY RULES:
1. NEVER rewrite whole files! Output ONLY surgical patches (`replace`, `insert_after`, or `insert_before`).
2. Every `search` string MUST match verbatim lines from the provided file excerpts (including indentation). Keep `search` compact (3 to 15 lines) and unique.
3. Preserve valid Python 3 AST syntax in `.py` files and balanced tags + balanced `{}` braces inside `<script>` in `index.html`.
4. NEVER output fake keys or secrets (`gsk_`, `sk-ant-`, `AIza`).
5. Wrap your final response inside `<queen_update>` and `</queen_update>` tags containing strictly valid JSON with this exact schema:

<queen_update>
{
  "summary": "Concise 1-sentence description of what was updated",
  "educational_notes": [
    "Step-by-step explanation for a student watching in split-screen: what part of the codebase we chose and why this surgical change is clean and safe."
  ],
  "commit_message": "feat: concise git commit summary",
  "edits": [
    {
      "file": "index.html",
      "section": "#topbar or route name",
      "explanation": "Why this specific snippet is being patched",
      "action": "replace",
      "search": "exact verbatim existing lines",
      "content": "new replacement lines (or lines to insert for insert_after / insert_before)"
    }
  ]
}
</queen_update>
"""


def parse_surgical_plan(raw_output: str) -> dict[str, Any]:
    """Extract and parse the JSON payload from `<queen_update>...</queen_update>` or fenced JSON."""
    if not raw_output or not raw_output.strip():
        raise ValueError("Model returned empty output")

    m = re.search(r"<queen_update>\s*(\{.*\})\s*</queen_update>", raw_output, re.DOTALL)
    candidate = m.group(1) if m else ""
    if not candidate:
        m_fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_output, re.DOTALL)
        if m_fence:
            candidate = m_fence.group(1)
    if not candidate:
        first = raw_output.find("{")
        last = raw_output.rfind("}")
        if first != -1 and last > first:
            candidate = raw_output[first : last + 1]

    if not candidate:
        raise ValueError("Could not find JSON surgical plan in model output")

    plan = json.loads(candidate)
    if not isinstance(plan, dict) or not isinstance(plan.get("edits"), list):
        raise ValueError("Parsed JSON is missing 'edits' list")
    return plan


def _find_normalized_span(source: str, search: str) -> tuple[int, int] | None:
    """Fallback line-by-line trailing-whitespace-insensitive locator."""
    src_lines = source.splitlines(keepends=True)
    needle_lines = [ln.rstrip() for ln in search.splitlines()]
    if not needle_lines:
        return None
    n = len(needle_lines)
    for i in range(len(src_lines) - n + 1):
        if [src_lines[i + j].rstrip() for j in range(n)] == needle_lines:
            start_char = sum(len(x) for x in src_lines[:i])
            end_char = sum(len(x) for x in src_lines[: i + n])
            return start_char, end_char
    return None


def apply_surgical_edits(
    originals: dict[str, str],
    edits: list[dict[str, Any]],
    allowed_files: set[str],
) -> tuple[dict[str, str], dict[str, str], list[dict[str, Any]]]:
    """Apply surgical edits in memory. Returns `(updated_contents, unified_diffs, applied_meta)`."""
    working = dict(originals)
    applied_meta: list[dict[str, Any]] = []

    for idx, edit in enumerate(edits, start=1):
        fname = (edit.get("file") or "").strip()
        if fname.startswith("qwen_app/"):
            fname = fname.split("/", 1)[1]
        if fname not in allowed_files:
            raise ValueError(f"Edit #{idx}: file '{fname}' is not in updatable allowlist {sorted(allowed_files)}")
        if fname not in working:
            raise ValueError(f"Edit #{idx}: target file '{fname}' not loaded")

        action = (edit.get("action") or "replace").strip().lower()
        search = edit.get("search") or ""
        content = edit.get("content") if edit.get("content") is not None else ""
        if not search:
            raise ValueError(f"Edit #{idx} on {fname}: 'search' anchor must not be empty")

        src = working[fname]
        pos = src.find(search)
        span: tuple[int, int] | None = None
        if pos != -1:
            span = (pos, pos + len(search))
        else:
            span = _find_normalized_span(src, search)

        if span is None:
            preview = search.splitlines()[0][:80] if search.splitlines() else search[:80]
            raise ValueError(f"Edit #{idx} on {fname}: search anchor not found near `{preview}`")

        s_char, e_char = span
        matched_text = src[s_char:e_char]
        if action == "replace":
            new_src = src[:s_char] + content + src[e_char:]
        elif action == "insert_after":
            sep = "" if matched_text.endswith("\n") or content.startswith("\n") else "\n"
            new_src = src[:e_char] + sep + content + src[e_char:]
        elif action == "insert_before":
            sep = "" if content.endswith("\n") else "\n"
            new_src = src[:s_char] + content + sep + src[s_char:]
        else:
            raise ValueError(f"Edit #{idx}: unsupported action '{action}'")

        working[fname] = new_src
        line_no = src[:s_char].count("\n") + 1
        applied_meta.append({
            "index": idx,
            "file": fname,
            "line": line_no,
            "action": action,
            "section": edit.get("section") or f"line {line_no}",
            "explanation": edit.get("explanation") or "",
        })

    diffs: dict[str, str] = {}
    changed_files: dict[str, str] = {}
    for fname, new_text in working.items():
        old_text = originals[fname]
        if new_text != old_text:
            changed_files[fname] = new_text
            diff_lines = difflib.unified_diff(
                old_text.splitlines(),
                new_text.splitlines(),
                fromfile=f"a/qwen_app/{fname}",
                tofile=f"b/qwen_app/{fname}",
                lineterm="",
                n=3,
            )
            diffs[fname] = "\n".join(diff_lines)

    return changed_files, diffs, applied_meta


# ── Streaming LLM Clients (Anthropic & Google Gemini) ────────────────────────
def _stream_anthropic_surgical(
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    on_delta: Callable[[str, str], None],
) -> tuple[str, dict[str, int]]:
    """Stream surgical patch JSON from Anthropic Messages API (`/v1/messages`)."""
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": 4096,
        "temperature": 0.1,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
        "stream": True,
    }
    chunks: list[str] = []
    usage = {"input_tokens": 0, "output_tokens": 0, "cache_write_tokens": 0, "cache_read_tokens": 0}

    with httpx.Client(timeout=120.0) as client:
        with client.stream("POST", "https://api.anthropic.com/v1/messages", headers=headers, json=payload) as resp:
            if resp.status_code >= 400:
                body = resp.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"Anthropic API HTTP {resp.status_code}: {redact_secrets(body[:320])}")
            for raw_line in resp.iter_lines():
                if not raw_line or not raw_line.startswith("data:"):
                    continue
                data_str = raw_line[5:].strip()
                if not data_str or data_str == "[DONE]":
                    continue
                try:
                    evt = json.loads(data_str)
                except Exception:
                    continue
                etype = evt.get("type")
                if etype == "message_start":
                    u = (evt.get("message") or {}).get("usage") or {}
                    usage["input_tokens"] = int(u.get("input_tokens") or usage["input_tokens"])
                    usage["output_tokens"] = int(u.get("output_tokens") or usage["output_tokens"])
                    usage["cache_write_tokens"] = int(u.get("cache_creation_input_tokens") or 0)
                    usage["cache_read_tokens"] = int(u.get("cache_read_input_tokens") or 0)
                elif etype == "content_block_delta":
                    delta = evt.get("delta") or {}
                    dtype = delta.get("type")
                    if dtype == "thinking_delta" and delta.get("thinking"):
                        on_delta("thinking", delta["thinking"])
                    elif dtype == "text_delta" and delta.get("text"):
                        txt = delta["text"]
                        chunks.append(txt)
                        on_delta("text", txt)
                elif etype == "message_delta":
                    u = evt.get("usage") or {}
                    if u.get("output_tokens") is not None:
                        usage["output_tokens"] = int(u["output_tokens"])
                    if u.get("input_tokens") is not None:
                        usage["input_tokens"] = int(u["input_tokens"])

    full_text = "".join(chunks)
    if usage["input_tokens"] == 0:
        usage["input_tokens"] = max(1, (len(system_prompt) + len(user_prompt)) // 4)
    if usage["output_tokens"] == 0:
        usage["output_tokens"] = max(1, len(full_text) // 4)
    return full_text, usage


def _stream_google_surgical(
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    on_delta: Callable[[str, str], None],
) -> tuple[str, dict[str, int]]:
    """Stream surgical patch JSON from Google Cloud / Gemini `streamGenerateContent?alt=sse`."""
    headers = {"content-type": "application/json"}
    base_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse"
    if api_key.startswith("ya29."):
        headers["Authorization"] = f"Bearer {api_key}"
        url = base_url
    else:
        url = f"{base_url}&key={api_key}"

    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 4096,
        },
    }
    chunks: list[str] = []
    usage = {"input_tokens": 0, "output_tokens": 0, "cache_write_tokens": 0, "cache_read_tokens": 0}

    with httpx.Client(timeout=120.0) as client:
        with client.stream("POST", url, headers=headers, json=payload) as resp:
            if resp.status_code >= 400:
                body = resp.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"Google Gemini API HTTP {resp.status_code}: {redact_secrets(body[:320])}")
            for raw_line in resp.iter_lines():
                if not raw_line or not raw_line.startswith("data:"):
                    continue
                data_str = raw_line[5:].strip()
                if not data_str or data_str == "[DONE]":
                    continue
                try:
                    evt = json.loads(data_str)
                except Exception:
                    continue
                for cand in evt.get("candidates") or []:
                    parts = ((cand.get("content") or {}).get("parts")) or []
                    for part in parts:
                        txt = part.get("text") or ""
                        if not txt:
                            continue
                        if part.get("thought"):
                            on_delta("thinking", txt)
                        else:
                            chunks.append(txt)
                            on_delta("text", txt)
                um = evt.get("usageMetadata") or {}
                if um:
                    if um.get("promptTokenCount") is not None:
                        usage["input_tokens"] = int(um["promptTokenCount"])
                    cand_tok = int(um.get("candidatesTokenCount") or 0)
                    thought_tok = int(um.get("thoughtsTokenCount") or 0)
                    if cand_tok or thought_tok:
                        usage["output_tokens"] = cand_tok + thought_tok
                    if um.get("cachedContentTokenCount") is not None:
                        usage["cache_read_tokens"] = int(um["cachedContentTokenCount"])

    full_text = "".join(chunks)
    if usage["input_tokens"] == 0:
        usage["input_tokens"] = max(1, (len(system_prompt) + len(user_prompt)) // 4)
    if usage["output_tokens"] == 0:
        usage["output_tokens"] = max(1, len(full_text) // 4)
    return full_text, usage


# ── End-to-End 6-Stage Surgical Auto-Update Orchestrator ─────────────────────
def get_job_status(flask_port: int = 8765, app_version: str = "v4") -> dict[str, Any]:
    with _STATE_LOCK:
        snap = dict(_JOB_STATE)
        snap["events"] = list(_JOB_STATE.get("events", []))[-60:]
    snap["flask_server"] = {
        "status": "online",
        "port": flask_port,
        "pid": os.getpid(),
        "uptime_sec": int(time.time() - _SERVER_BOOT_TS),
        "version": app_version,
    }
    snap["stages"] = EDUCATIONAL_STAGES
    return snap


def ensure_local_repo_ready(git_root: Path, git_run_fn: Callable[[list[str]], tuple[bool, str]]) -> tuple[Path, list[str]]:
    """Verify local source repo exists (cloning from GitHub if needed) and report git status."""
    notes: list[str] = []
    target_root = git_root
    if not (target_root / ".git").is_dir():
        target_root = DEV_REPO_DEFAULT
        if not (target_root / ".git").is_dir():
            target_root.parent.mkdir(parents=True, exist_ok=True)
            res = subprocess.run(
                ["git", "clone", f"https://github.com/{PRIMARY_GITHUB_REPO}.git", str(target_root)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if res.returncode != 0:
                raise RuntimeError(f"Failed to clone {PRIMARY_GITHUB_REPO}: {res.stderr[:200]}")
            notes.append(f"Cloned {PRIMARY_GITHUB_REPO} -> {target_root}")

    ok_branch, branch_out = git_run_fn(["rev-parse", "--abbrev-ref", "HEAD"])
    notes.append(f"Repo: {target_root} (branch: {branch_out.strip() if ok_branch else 'main'})")
    ok_st, st_out = git_run_fn(["status", "--short"])
    if ok_st and not st_out.strip():
        ok_pull, pull_out = git_run_fn(["pull", "--ff-only", "origin", "main"])
        notes.append(f"git pull --ff-only: {'up-to-date' if ok_pull else pull_out[:120]}")
    else:
        notes.append(f"Working tree has local changes ({len(st_out.splitlines())} file(s)) — preserving local state")
    return target_root, notes


def sync_local_installation(git_root: Path, installed_home: Path = HOME) -> list[str]:
    """Copy updated source files into `~/.groq` immediately so local runtime stays in sync."""
    logs: list[str] = []
    qwen_dst = installed_home / "qwen_app"
    qwen_dst.mkdir(parents=True, exist_ok=True)
    for rel in ("qwen_app/app.py", "qwen_app/auto_updater.py", "qwen_app/index.html"):
        src = git_root / rel
        dst = installed_home / rel
        if src.is_file() and src.resolve() != dst.resolve():
            shutil.copy2(str(src), str(dst))
            logs.append(f"Synced {rel} -> {dst}")
    for root_f in ("version.json", "groq_pool.py"):
        src = git_root / root_f
        dst = installed_home / root_f
        if src.is_file() and src.resolve() != dst.resolve():
            shutil.copy2(str(src), str(dst))
            logs.append(f"Synced {root_f} -> {dst}")
    return logs


def run_surgical_auto_update(
    instruction: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    dry_run: bool = False,
    target_files: list[str] | None = None,
    mock_plan: dict[str, Any] | None = None,
    git_root: Path,
    repo_dir: Path,
    update_dir: Path,
    updatable_files: set[str],
    ci_run_all_fn: Callable[[str, str], tuple[bool, list[str]]],
    bump_version_fn: Callable[[list[str], str], int],
    git_run_fn: Callable[[list[str]], tuple[bool, str]],
    git_commit_and_push_fn: Callable[[list[str], str], tuple[bool, list[str]]],
    broadcast_fn: Callable[[dict[str, Any]], None],
    term_print_fn: Callable[[str], None],
    flask_port: int = 8765,
    current_version_str: str = "v4",
    store_path: Path = AUTO_UPDATE_KEYS_FILE,
    ledger_path: Path = AUTO_UPDATE_LEDGER_FILE,
) -> tuple[int, dict[str, Any]]:
    """Execute the full 6-stage surgical update pipeline with live split-screen SSE telemetry."""
    instruction = (instruction or "").strip()
    if not instruction:
        return 400, {"ok": False, "error": "Update instruction is required."}

    with _STATE_LOCK:
        if _JOB_STATE["running"]:
            return 409, {"ok": False, "error": "An auto-update job is already running."}
        cfg = load_auto_update_store(store_path)
        chosen_provider = (provider or cfg["active_provider"] or "google").strip().lower()
        if chosen_provider not in ("google", "anthropic"):
            return 400, {"ok": False, "error": f"Unsupported provider '{chosen_provider}'"}
        chosen_model = (
            (model or "").strip()
            or cfg["active_models"].get(chosen_provider)
            or CURATED_PROVIDER_MODELS[chosen_provider][0]["id"]
        )
        keys = cfg["keys"].get(chosen_provider, [])
        if not keys and mock_plan is None:
            return 400, {
                "ok": False,
                "error": f"No {chosen_provider.title()} API key configured. Open 🔑 Key Manager -> Auto-Update API section or click 'Auto-Load ~/Downloads/API'.",
            }
        job_id = f"au_{int(time.time() * 1000)}"
        _JOB_STATE.update({
            "running": True,
            "job_id": job_id,
            "provider": chosen_provider,
            "model": chosen_model,
            "instruction": instruction,
            "current_stage": 1,
            "working_on": "Initializing Invisible Software Engineer…",
            "events": [],
            "started_at": time.time(),
        })

    started_ts = time.time()

    def emit(subtype: str, **payload: Any) -> None:
        evt = {
            "type": "auto_update_event",
            "subtype": subtype,
            "job_id": job_id,
            "provider": chosen_provider,
            "model": chosen_model,
            "timestamp": round(time.time(), 3),
            "flask_server": {
                "status": "online",
                "port": flask_port,
                "pid": os.getpid(),
                "version": current_version_str,
            },
            **payload,
        }
        with _STATE_LOCK:
            if "stage" in payload:
                _JOB_STATE["current_stage"] = payload["stage"]
            if "working_on" in payload:
                _JOB_STATE["working_on"] = payload["working_on"]
            _JOB_STATE["events"].append(evt)
            _JOB_STATE["events"] = _JOB_STATE["events"][-120:]
        broadcast_fn(evt)

    term_print_fn("\033[1;36m" + "═" * 74 + "\033[0m")
    term_print_fn(
        f"\033[1;35m  ⚡ QUEEN AUTO-UPDATE PIPELINE STARTED\033[0m "
        f"[{chosen_provider.upper()} · {chosen_model}]{' (DRY RUN)' if dry_run else ''}"
    )
    term_print_fn(f"\033[1;37m  Task:\033[0m {instruction}")
    term_print_fn("\033[1;36m" + "─" * 74 + "\033[0m")

    try:
        # ── STAGE 1: Repo & Pre-Briefed Context Map ──
        emit(
            "stage",
            stage=1,
            status="active",
            title=EDUCATIONAL_STAGES[0]["title"],
            lesson=EDUCATIONAL_STAGES[0]["lesson"],
            working_on="Checking git repository & indexing line-numbered anchors…",
        )
        active_git_root, repo_notes = ensure_local_repo_ready(git_root, git_run_fn)
        context_blob, inspected_files = build_surgical_context(active_git_root, instruction, target_files)
        for note in repo_notes:
            term_print_fn(f"  \033[1;34m[Stage 1 · Repo]\033[0m {note}")
        emit(
            "log",
            stage=1,
            message="Repo verified: " + " | ".join(repo_notes) + f" | Indexed slices: {', '.join(inspected_files)} ({len(context_blob):,} chars)",
            working_on=f"Prepared surgical slices for {', '.join(inspected_files)}",
        )

        # ── STAGE 2: Stream Model Plan & Surgical Patch Spec ──
        emit(
            "stage",
            stage=2,
            status="active",
            title=EDUCATIONAL_STAGES[1]["title"],
            lesson=EDUCATIONAL_STAGES[1]["lesson"],
            working_on=f"Streaming surgical patches from {chosen_provider.title()} ({chosen_model})…",
        )

        user_prompt = (
            f"USER UPDATE REQUEST:\n{instruction}\n\n"
            f"CURRENT VERSION: {current_version_str}\n"
            f"PRE-INDEXED REPOSITORY CODE SLICES:\n{context_blob}\n\n"
            f"Produce minimal, exact surgical edits inside <queen_update>...</queen_update>."
        )

        stream_buf = {"chars": 0, "last_emit": 0.0}

        def _on_stream_delta(kind: str, delta_txt: str) -> None:
            stream_buf["chars"] += len(delta_txt)
            now = time.time()
            # Stream every delta chunk smoothly to split-screen UI
            emit(
                "model_delta",
                stage=2,
                delta_kind=kind,
                text=delta_txt,
                streamed_chars=stream_buf["chars"],
                working_on=f"{chosen_model} writing surgical patch ({stream_buf['chars']:,} chars)…",
            )
            stream_buf["last_emit"] = now

        if mock_plan is not None:
            raw_model_output = "<queen_update>\n" + json.dumps(mock_plan, indent=2) + "\n</queen_update>"
            _on_stream_delta("text", raw_model_output)
            usage = {
                "input_tokens": max(120, len(user_prompt) // 4),
                "output_tokens": max(40, len(raw_model_output) // 4),
                "cache_write_tokens": 0,
                "cache_read_tokens": 0,
            }
        else:
            last_err: Exception | None = None
            raw_model_output = ""
            usage = {"input_tokens": 0, "output_tokens": 0, "cache_write_tokens": 0, "cache_read_tokens": 0}
            for attempt_idx, api_key in enumerate(keys, start=1):
                try:
                    term_print_fn(
                        f"  \033[1;36m[Stage 2 · API]\033[0m Calling {chosen_provider} ({chosen_model}) with key {mask_secret(api_key)}…"
                    )
                    if chosen_provider == "anthropic":
                        raw_model_output, usage = _stream_anthropic_surgical(
                            api_key, chosen_model, SURGICAL_SYSTEM_PROMPT, user_prompt, _on_stream_delta
                        )
                    else:
                        raw_model_output, usage = _stream_google_surgical(
                            api_key, chosen_model, SURGICAL_SYSTEM_PROMPT, user_prompt, _on_stream_delta
                        )
                    last_err = None
                    break
                except Exception as exc:
                    last_err = exc
                    emit(
                        "log",
                        stage=2,
                        message=f"Key #{attempt_idx} ({mask_secret(api_key)}) failed: {redact_secrets(str(exc))}",
                    )
            if last_err is not None:
                raise RuntimeError(redact_secrets(str(last_err)))

        plan = parse_surgical_plan(raw_model_output)
        summary = (plan.get("summary") or instruction)[:200]
        edu_notes = plan.get("educational_notes") or []
        commit_msg = (plan.get("commit_message") or f"feat(auto-update): {summary}")[:140]
        edits = plan.get("edits") or []

        emit(
            "plan_ready",
            stage=2,
            summary=summary,
            educational_notes=edu_notes,
            edits_count=len(edits),
            working_on=f"Plan ready: {len(edits)} surgical edit(s) — {summary}",
        )
        term_print_fn(f"  \033[1;32m[Stage 2 · Plan]\033[0m {summary} ({len(edits)} surgical edit(s))")

        # ── STAGE 3: Apply Surgical Edits In Memory & Build Unified Diff ──
        emit(
            "stage",
            stage=3,
            status="active",
            title=EDUCATIONAL_STAGES[2]["title"],
            lesson=EDUCATIONAL_STAGES[2]["lesson"],
            working_on="Applying surgical patches in memory & computing unified diff…",
        )
        qwen_src_dir = active_git_root / "qwen_app"
        originals: dict[str, str] = {}
        for fname in updatable_files:
            p = qwen_src_dir / fname
            if not p.exists():
                p = repo_dir / fname
            if p.exists():
                originals[fname] = p.read_text(encoding="utf-8")

        changed_files, diffs, applied_meta = apply_surgical_edits(originals, edits, updatable_files)
        if not changed_files:
            raise ValueError("Surgical edits produced no net file changes.")

        for meta in applied_meta:
            term_print_fn(
                f"  \033[1;33m[Stage 3 · Patch]\033[0m {meta['file']}:L{meta['line']} ({meta['action']}) — {meta['section']}"
            )
            emit(
                "patch_applied",
                stage=3,
                patch=meta,
                working_on=f"Patched {meta['file']} at line {meta['line']} ({meta['section']})",
            )

        combined_diff = "\n\n".join(diffs.values())
        emit(
            "diff",
            stage=3,
            diffs=diffs,
            combined_diff=combined_diff,
            files_changed=list(changed_files.keys()),
        )

        # ── STAGE 4: Automated CI Validation Gate ──
        emit(
            "stage",
            stage=4,
            status="active",
            title=EDUCATIONAL_STAGES[3]["title"],
            lesson=EDUCATIONAL_STAGES[3]["lesson"],
            working_on="Running Python AST & HTML/JS structural CI checks…",
        )
        ci_report: dict[str, Any] = {}
        all_ci_errors: list[str] = []
        for fname, new_code in changed_files.items():
            # Secret leak check on generated patch before CI passes
            leaked = extract_multi_provider_keys(new_code)
            if leaked["groq"] or leaked["anthropic"] or leaked["google"]:
                all_ci_errors.append(f"{fname}: SECURITY BLOCK — raw API key detected in generated code")
            passed, errs = ci_run_all_fn(new_code, fname)
            ci_report[fname] = {"passed": passed, "errors": errs, "bytes": len(new_code.encode("utf-8"))}
            if not passed:
                all_ci_errors.extend([f"{fname}: {e}" for e in errs])

        if all_ci_errors:
            cost_info = calculate_auto_update_cost(
                chosen_provider,
                chosen_model,
                usage["input_tokens"],
                usage["output_tokens"],
                usage["cache_write_tokens"],
                usage["cache_read_tokens"],
            )
            emit("ci_result", stage=4, passed=False, errors=all_ci_errors, report=ci_report)
            emit("error", stage=4, error="CI Validation Failed: " + "; ".join(all_ci_errors), cost=cost_info)
            term_print_fn(f"  \033[1;31m[Stage 4 · CI FAILED]\033[0m {'; '.join(all_ci_errors)}")
            term_print_fn(f"  \033[1;33m[Update Cost]\033[0m {cost_info['formatted_usd']} USD")
            return 422, {
                "ok": False,
                "ci_passed": False,
                "error": "CI Validation Failed — no files were modified.",
                "ci_errors": all_ci_errors,
                "cost": cost_info,
            }

        emit("ci_result", stage=4, passed=True, errors=[], report=ci_report, working_on="CI Gate PASSED ✓")
        term_print_fn("  \033[1;32m[Stage 4 · CI]\033[0m AST & HTML structural validation PASSED ✓")

        # ── STAGE 5: Backup, Write, Version Bump, Git Push & Local `~/.groq` Sync ──
        emit(
            "stage",
            stage=5,
            status="active",
            title=EDUCATIONAL_STAGES[4]["title"],
            lesson=EDUCATIONAL_STAGES[4]["lesson"],
            working_on="Dry-run verification complete (skipping disk write)" if dry_run else "Backing up, writing files, pushing to GitHub & syncing ~/.groq…",
        )

        backups_created: list[str] = []
        git_logs: list[str] = []
        sync_logs: list[str] = []
        final_version_str = current_version_str

        if not dry_run:
            backup_dir = update_dir / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            ts_int = int(time.time())
            for fname, new_code in changed_files.items():
                src_target = active_git_root / "qwen_app" / fname
                run_target = repo_dir / fname
                if src_target.exists():
                    bname = f"{fname}.backup_{ts_int}"
                    shutil.copy2(str(src_target), str(backup_dir / bname))
                    backups_created.append(bname)
                src_target.parent.mkdir(parents=True, exist_ok=True)
                src_target.write_text(new_code, encoding="utf-8")
                if run_target.resolve() != src_target.resolve() and run_target.parent.is_dir():
                    run_target.write_text(new_code, encoding="utf-8")

            new_v_num = bump_version_fn(list(changed_files.keys()), summary)
            final_version_str = f"v{new_v_num}"
            sync_logs = sync_local_installation(active_git_root)
            _, git_logs = git_commit_and_push_fn(
                [f"qwen_app/{f}" for f in changed_files.keys()],
                f"{final_version_str}: {commit_msg}",
            )
            for gl in git_logs:
                term_print_fn(f"  \033[1;34m[Stage 5 · Git]\033[0m {gl}")
        else:
            git_logs.append("Dry-run enabled: skipped disk write, version bump, and git push.")

        emit(
            "deploy_sync",
            stage=5,
            dry_run=dry_run,
            version=final_version_str,
            backups=backups_created,
            git_logs=git_logs,
            sync_logs=sync_logs,
            working_on=f"Deployed {final_version_str} to repo & ~/.groq" if not dry_run else "Dry-run verified",
        )

        # ── STAGE 6: Exact USD Cost Receipt & Completion ──
        elapsed = round(time.time() - started_ts, 2)
        cost_info = calculate_auto_update_cost(
            chosen_provider,
            chosen_model,
            usage["input_tokens"],
            usage["output_tokens"],
            usage["cache_write_tokens"],
            usage["cache_read_tokens"],
        )
        ledger = record_auto_update_receipt(
            cost_info=cost_info,
            summary=summary,
            files_changed=list(changed_files.keys()),
            new_version=final_version_str,
            dry_run=dry_run,
            path=ledger_path,
        )

        result_payload = {
            "ok": True,
            "job_id": job_id,
            "dry_run": dry_run,
            "provider": chosen_provider,
            "model": chosen_model,
            "summary": summary,
            "educational_notes": edu_notes,
            "commit_message": commit_msg,
            "files_changed": list(changed_files.keys()),
            "patches": applied_meta,
            "diffs": diffs,
            "combined_diff": combined_diff,
            "ci_passed": True,
            "ci_report": ci_report,
            "backups": backups_created,
            "git_logs": git_logs,
            "sync_logs": sync_logs,
            "old_version": current_version_str,
            "version": final_version_str,
            "elapsed_sec": elapsed,
            "cost": cost_info,
            "cumulative_auto_update_usd": round(float(ledger.get("total_spent_usd", 0.0)), 6),
        }

        emit(
            "cost_receipt",
            stage=6,
            status="complete",
            title=EDUCATIONAL_STAGES[5]["title"],
            lesson=EDUCATIONAL_STAGES[5]["lesson"],
            cost=cost_info,
            elapsed_sec=elapsed,
            version=final_version_str,
            cumulative_auto_update_usd=result_payload["cumulative_auto_update_usd"],
            working_on=f"Complete ({final_version_str}) · Update Cost: {cost_info['formatted_usd']} USD",
        )
        emit("complete", stage=6, result=result_payload)

        term_print_fn("\033[1;32m" + "─" * 74 + "\033[0m")
        term_print_fn(
            f"\033[1;32m  ✓ AUTO-UPDATE COMPLETE ({current_version_str} -> {final_version_str}) in {elapsed}s\033[0m"
        )
        term_print_fn(
            f"\033[1;33m  💵 UPDATE COST IN USD: {cost_info['formatted_usd']}\033[0m "
            f"({cost_info['input_tokens']:,} in / {cost_info['output_tokens']:,} out on {chosen_provider}/{chosen_model})"
        )
        term_print_fn(
            f"\033[1;36m  📊 Cumulative Auto-Update Ledger:\033[0m ${result_payload['cumulative_auto_update_usd']:.6f} USD"
        )
        term_print_fn("\033[1;36m" + "═" * 74 + "\033[0m")

        with _STATE_LOCK:
            _JOB_STATE["last_result"] = result_payload
        return 200, result_payload

    except Exception as exc:
        safe_err = redact_secrets(str(exc))
        emit("error", error=safe_err, working_on=f"Error: {safe_err[:120]}")
        term_print_fn(f"  \033[1;31m[AUTO-UPDATE ERROR]\033[0m {safe_err}")
        return 500, {"ok": False, "error": safe_err, "job_id": job_id}
    finally:
        with _STATE_LOCK:
            _JOB_STATE["running"] = False
