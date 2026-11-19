"""Groq-free runtime: CAPI, deterministic Python skills, and the supervised updater."""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from flask import Flask, jsonify, request
from waitress import serve

from state_paths import QUEEN_HOME, migrate_legacy_state

import auto_updater
import capi_chat


PACKAGE_DIR = Path(__file__).resolve().parent
HOME = QUEEN_HOME
UPDATE_DIR = HOME / "incoming_update"
_source_root = PACKAGE_DIR.parent
if not (_source_root / ".git").exists():
    _source_root = Path.home() / "Developer" / "groq_ai_studio"
REPO_ROOT = _source_root
REPO_DIR = REPO_ROOT / "qwen_app"
VERSION_FILE = REPO_ROOT / "version.json"
if not VERSION_FILE.is_file():
    VERSION_FILE = HOME / "version.json"
AUTO_UPDATE_REPO = auto_updater.MIRROR_GITHUB_REPO
UPDATABLE_FILES = {
    "app.py",
    "auto_updater.py",
    "capi_chat.py",
    "queen_backend.py",
    "queen_python_skills/__init__.py",
    "queen_python_skills/ableton.py",
}
app = Flask("queen")
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
capi_chat.register(app)


def _version_data() -> dict[str, Any]:
    try:
        value = json.loads(VERSION_FILE.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeError(f"Cannot read Queen version file {VERSION_FILE}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Queen version file {VERSION_FILE} is invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"Queen version file {VERSION_FILE} must contain a JSON object")
    if type(value.get("version")) is not int or value["version"] < 1:
        raise RuntimeError(f"Queen version file {VERSION_FILE} must contain a positive integer version")
    return value


def _version() -> str:
    return f"v{int(_version_data().get('version', 1))}"


def _current_port() -> int:
    try:
        return int(os.environ.get("QUEEN_PORT", "8766"))
    except ValueError:
        return 8766


def _broadcast(event: dict[str, Any]) -> None:
    print(json.dumps(event, ensure_ascii=False), flush=True)


def _term_print(line: str) -> None:
    print(line, flush=True)


def _git(args: list[str], timeout: int = 30) -> tuple[bool, str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    return result.returncode == 0, (result.stdout + "\n" + result.stderr).strip()


def _commit_and_push(files: list[str], message: str) -> tuple[bool, list[str]]:
    log: list[str] = []
    for relative in files:
        path = str(Path(relative))
        ok, output = _git(["add", path])
        log.append(f"git add {path}: {'OK' if ok else 'FAIL'} — {output}")
        if not ok:
            return False, log
    ok, output = _git(["add", "version.json"])
    log.append(f"git add version.json: {'OK' if ok else 'FAIL'} — {output}")
    if not ok:
        return False, log
    ok, output = _git(["diff", "--cached", "--stat"])
    if not output.strip():
        return True, [*log, "Nothing to commit (files unchanged)"]
    commit_message = message.strip() or "Update Queen Python runtime"
    if "Co-authored-by:" not in commit_message:
        commit_message += "\n\nCo-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
    ok, output = _git(["commit", "-m", commit_message])
    log.append(f"git commit: {'OK' if ok else 'FAIL'} — {output[:200]}")
    if not ok:
        return False, log
    ok, output = _git(["push", "origin", "main"], timeout=120)
    log.append(f"git push origin: {'OK' if ok else 'FAIL'} — {output[:200]}")
    remote_ok, _ = _git(["remote", "get-url", "auto-update"])
    if not remote_ok:
        remote_ok, output = _git(["remote", "add", "auto-update", f"https://github.com/{AUTO_UPDATE_REPO}.git"])
        log.append(f"add auto-update remote: {'OK' if remote_ok else 'FAIL'} — {output[:200]}")
    if remote_ok:
        pushed, output = _git(["push", "auto-update", "main"], timeout=120)
        log.append(f"git push auto-update: {'OK' if pushed else 'FAIL'} — {output[:200]}")
        ok = ok or pushed
    return ok, log


def _bump_version(files: list[str], message: str) -> int:
    data = _version_data()
    version = int(data.get("version", 0)) + 1
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    history = data.get("log", [])
    if not isinstance(history, list):
        history = []
    history.append({
        "version": version,
        "timestamp": timestamp,
        "message": message or f"Update v{version}",
        "files": files,
    })
    data.update(version=version, updated_at=timestamp, log=history[-50:])
    tmp = VERSION_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(VERSION_FILE)
    return version


def _ci(code: str, filename: str) -> tuple[bool, list[str]]:
    try:
        ast.parse(code, filename=filename)
    except SyntaxError as exc:
        return False, [f"{filename}:{exc.lineno}: {exc.msg}"]
    return True, []


@app.before_request
def _local_api_guard():
    if not request.path.startswith("/api/"):
        return None
    if request.method == "OPTIONS":
        return jsonify(ok=False, error="Cross-origin preflight rejected"), 403
    origin = request.headers.get("Origin", "")
    if origin:
        try:
            parsed_origin = urlsplit(origin)
        except ValueError:
            return jsonify(ok=False, error="Invalid Origin blocked by Queen"), 403
        if parsed_origin.scheme != "http" or parsed_origin.hostname not in ("127.0.0.1", "localhost", "::1"):
            return jsonify(ok=False, error="Untrusted Origin blocked by Queen"), 403
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return jsonify(ok=False, error="Queen's API is local-only"), 403
    token_file = HOME / "api_token"
    token = token_file.read_text(encoding="utf-8").strip() if token_file.is_file() else ""
    supplied = request.headers.get("X-Queen-Token", "").strip()
    if token and supplied and supplied != token:
        return jsonify(ok=False, error="Invalid Queen API token"), 403
    return None


@app.get("/health")
def health():
    return jsonify(app="Queen Python skills", version=_version(), ok=True)


@app.get("/api/skills/list")
def list_python_skills():
    from queen_python_skills import catalog
    return jsonify(ok=True, skills=catalog())


@app.get("/api/ableton/capabilities")
def ableton_capabilities():
    from queen_python_skills import ableton
    return jsonify(ok=True, **ableton.capabilities())


@app.post("/api/ableton/action")
def ableton_action():
    from queen_python_skills import ableton
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(ok=False, error="Expected a JSON object"), 400
    extra = body.keys() - {"action", "arguments"}
    if extra:
        return jsonify(ok=False, error=f"Unknown field(s): {', '.join(sorted(extra))}"), 400
    try:
        result = ableton.execute_action(body.get("action"), body.get("arguments", {}))
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400
    except ableton.TakeoverCancelled as exc:
        return jsonify(ok=False, cancelled=True, error=str(exc)), 409
    except ableton.AbletonUnavailable as exc:
        return jsonify(ok=False, error=str(exc)), 503
    except ableton.AbletonControlError as exc:
        return jsonify(ok=False, error=str(exc)), 502
    return jsonify(ok=True, **result)


@app.get("/api/version")
def version():
    data = _version_data()
    return jsonify(
        version=data.get("version", 1),
        version_str=_version(),
        updated_at=data.get("updated_at", ""),
        auto_update_repo=AUTO_UPDATE_REPO,
        log=data.get("log", [])[-10:],
    )


@app.get("/api/auto_update/config")
def get_auto_update_config():
    return jsonify(auto_updater.get_public_auto_update_config(
        flask_port=_current_port(),
        app_version=_version(),
    ))


@app.post("/api/auto_update/config")
def set_auto_update_config():
    body = request.get_json(silent=True) or {}
    try:
        auto_updater.set_auto_update_selection(
            provider=body.get("provider"),
            model=body.get("model"),
        )
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400
    return get_auto_update_config()


@app.get("/api/auto_update/models")
def auto_update_models():
    provider = (request.args.get("provider") or "").strip().lower()
    if not provider:
        provider = auto_updater.load_auto_update_store()["active_provider"]
    return jsonify(auto_updater.fetch_provider_models(provider))


@app.post("/api/auto_update/keys/import")
def import_auto_update_keys():
    body = request.get_json(silent=True) or {}
    content = (body.get("content") or body.get("text") or "").strip()
    if not content and body.get("path"):
        try:
            content = Path(str(body["path"])).expanduser().read_text(encoding="utf-8")
        except OSError as exc:
            return jsonify(ok=False, error=f"Could not read the selected key file: {exc}"), 400
    extracted = auto_updater.extract_multi_provider_keys(content)
    added = auto_updater.add_auto_update_keys(extracted)
    if not any(added.values()):
        return jsonify(ok=False, error="No new Google or Anthropic keys were found."), 400
    return jsonify(ok=True, auto_update_added=added)


@app.post("/api/auto_update/keys/load-default")
def load_auto_update_keys():
    return jsonify(auto_updater.discover_keys_from_downloads())


@app.post("/api/auto_update/keys/delete")
def delete_auto_update_key():
    body = request.get_json(silent=True) or {}
    provider = (body.get("provider") or "").strip().lower()
    removed = auto_updater.delete_auto_update_key(
        provider=provider,
        key_id=(body.get("id") or "").strip(),
        clear_all=bool(body.get("clear_all")),
    )
    if not removed and not body.get("clear_all"):
        return jsonify(ok=False, error="Auto Update key not found"), 404
    return jsonify(ok=True, auto_update=auto_updater.get_public_auto_update_config(
        flask_port=_current_port(),
        app_version=_version(),
    ))


@app.get("/api/auto_update/status")
def auto_update_status():
    return jsonify(ok=True, **auto_updater.get_job_status(
        flask_port=_current_port(),
        app_version=_version(),
    ))


@app.get("/api/auto_update/ledger")
def auto_update_ledger():
    ledger = auto_updater.load_auto_update_ledger()
    return jsonify(
        ok=True,
        total_spent_usd=round(float(ledger.get("total_spent_usd", 0.0)), 6),
        updates_count=int(ledger.get("updates_count", 0)),
        history=ledger.get("history", [])[-30:],
    )


@app.post("/api/auto_update/run")
def run_auto_update():
    body = request.get_json(silent=True) or {}
    instruction = (body.get("instruction") or "").strip()
    try:
        import claude_link
        route = claude_link.route(bool(body.get("allow_api")))
    except Exception as exc:
        return jsonify(ok=False, error=f"Could not determine the update route: {exc}"), 502
    if route == "local" and not body.get("dry_run", False):
        try:
            result = claude_link.ask(
                f"Update the Queen Python runtime in {REPO_ROOT}. Instruction: {instruction}\n"
                "Make only the requested change. Run the focused tests and report what changed; do not commit or push.",
                model="sonnet",
                cwd=REPO_ROOT,
                timeout=1200,
                permission_mode="acceptEdits",
                allowed_tools=["Read", "Edit", "Write", "Grep", "Glob", "Bash(python3:*)", "Bash(git diff:*)"],
            )
        except Exception as exc:
            return jsonify(ok=False, error=f"Local Claude Code did not finish: {exc}"), 502
        return jsonify(ok=True, via="local Claude Code", cost_usd=0, report=result["answer"])
    target_files = body.get("target_files")
    status, payload = auto_updater.run_surgical_auto_update(
        instruction=instruction,
        provider=body.get("provider"),
        model=body.get("model"),
        dry_run=bool(body.get("dry_run", False)),
        target_files=target_files if isinstance(target_files, list) else None,
        git_root=REPO_ROOT,
        repo_dir=REPO_DIR,
        update_dir=UPDATE_DIR,
        updatable_files=UPDATABLE_FILES,
        ci_run_all_fn=_ci,
        bump_version_fn=_bump_version,
        git_run_fn=_git,
        git_commit_and_push_fn=_commit_and_push,
        broadcast_fn=_broadcast,
        term_print_fn=_term_print,
        flask_port=_current_port(),
        current_version_str=_version(),
    )
    return jsonify(payload), status


def main() -> None:
    migrate_legacy_state()
    HOME.mkdir(parents=True, exist_ok=True)
    port = _current_port()
    (HOME / "backend_port").write_text(f"{port}\n", encoding="utf-8")
    serve(app, host="127.0.0.1", port=port, threads=8)


if __name__ == "__main__":
    main()
