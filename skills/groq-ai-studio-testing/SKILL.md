---
name: groq-ai-studio-testing
description: >-
  Complete test runbook for Groq AI Studio (Queen / qwen). Covers health,
  version, self-update CI pipeline (chunk → assemble → CI reject → CI pass),
  chat persistence, key management, and the backdoor API. All tests use curl
  from the terminal — no browser needed.
---

# Groq AI Studio — Test Runbook

> **Mandatory Rule ("In Front of My Eyes"):** Always run tests **visibly** in
> macOS `Terminal.app` and/or Queen's live server terminal window so Marko can
> see every command and result in real time.

## Fastest Visible Run (One Command — Opens macOS Terminal.app)

```bash
bash ~/Developer/groq_ai_studio/skills/groq-ai-studio-testing/scripts/run_visible_tests.sh
```

What this script does automatically:
1. Uses `osascript` to open and activate macOS **Terminal.app** right in front of the user's eyes.
2. Runs `./install.sh` and restarts Queen (`qwen_app/app.py`) on port 8765.
3. Calls `POST /api/terminal/log` to print a live banner in Queen's server console.
4. Calls `POST /api/test/live` (Queen's built-in Python server self-test backdoor), which runs all 9 non-destructive checks and prints colorized `$ command` + `✓ PASS` / `✗ FAIL` lines in **both** the Terminal window and Queen's server log.
5. Sends a live verification prompt via `POST /api/remote/send` asking Queen to confirm her self-update pipeline awareness (visible live in both the browser UI and Terminal).
6. Tees the complete output to `/tmp/queen_visible_test.log` and waits for completion so the agent can verify exit code `0`.

## Python Server Live-Test Backdoor Endpoints

When Queen is running, you can also trigger visible tests directly through her HTTP API or terminal keyboard:
- **`POST /api/test/live`** (or `GET /api/test/live`): Runs all 9 built-in checks inside `qwen_app/app.py` and prints colorized progress directly to Queen's server terminal window.
- **`POST /api/terminal/log`**: Body `{"level": "cmd|info|pass|fail", "message": "..."}` — prints a timestamped line directly into Queen's terminal console and broadcasts it over SSE (`/api/events`).
- **Press `'t'` in Queen's terminal window**: Triggers `run_live_selftest()` interactively.

## Prerequisites

```bash
# 1. Deploy latest code
cd ~/Developer/groq_ai_studio && ./install.sh

# 2. Start the app (if not already running)
# IMPORTANT: redirect stdin from /dev/null when running headless (no terminal).
# The app has a keyboard listener that kills the process if stdin closes.
cd ~/.groq && nohup ./venv/bin/python -W ignore qwen_app/app.py 8765 < /dev/null > /tmp/qwen.log 2>&1 &

# 3. Wait for startup, then verify
sleep 3
PORT=$(cat ~/.groq/app_url | grep -oE '[0-9]+$')
BASE="http://127.0.0.1:${PORT}"
curl -s "$BASE/health"
echo "Queen is at $BASE"
```

> [!IMPORTANT]
> The `< /dev/null` is critical. Without it, the keyboard listener detects
> stdin EOF, runs the cleanup handler, and kills the server immediately.

---

## Test 1 — Health Check

```bash
curl -s "$BASE/health" | python3 -m json.tool
```

**Expected:** `{"status": "ok", ...}` with 200.

---

## Test 2 — Version Endpoint

```bash
curl -s "$BASE/api/version" | python3 -m json.tool
```

**Expected:** `{"version": N, "version_str": "vN", "auto_update_repo": "...", "log": [...]}`.

---

## Test 3 — Self-Update: CI Rejection (bad Python)

Send deliberately broken Python to verify CI blocks it.

```bash
# Step 3a: Send a broken chunk (missing close-paren, no imports, no defs)
curl -s -X POST "$BASE/api/self_update/chunk" \
  -H 'content-type: application/json' \
  -d '{"file":"app.py","part":1,"content":"print(\"hello\""}' \
  | python3 -m json.tool

# Step 3b: Try to assemble — should FAIL CI
curl -s -X POST "$BASE/api/self_update/assemble" \
  -H 'content-type: application/json' \
  -d '{"file":"app.py"}' \
  | python3 -m json.tool
```

**Expected 3a:** `{"ok": true, "status": "chunk_saved", ...}` — chunk is accepted into staging.
**Expected 3b:** HTTP 422, `{"ok": false, "ci_passed": false, "ci_errors": [...]}` — file NOT written. Errors should mention syntax or structural issues.

```bash
# Step 3c: Discard the bad chunks
curl -s -X POST "$BASE/api/self_update/discard" \
  -H 'content-type: application/json' \
  -d '{"file":"app.py"}' \
  | python3 -m json.tool
```

**Expected 3c:** `{"ok": true, "discarded": 1}`.

---

## Test 4 — Self-Update: CI Rejection (bad HTML)

```bash
# Unbalanced HTML — missing </html>
curl -s -X POST "$BASE/api/self_update/chunk" \
  -H 'content-type: application/json' \
  -d '{"file":"index.html","part":1,"content":"<html><head></head><body><p>hi</p></body>"}' \
  | python3 -m json.tool

curl -s -X POST "$BASE/api/self_update/assemble" \
  -H 'content-type: application/json' \
  -d '{"file":"index.html"}' \
  | python3 -m json.tool
```

**Expected:** HTTP 422, CI errors mention missing `</html>` or size too small.

```bash
# Cleanup
curl -s -X POST "$BASE/api/self_update/discard" \
  -H 'content-type: application/json' \
  -d '{"file":"index.html"}' | python3 -m json.tool
```

---

## Test 5 — Self-Update: File Not in Allowlist

```bash
curl -s -X POST "$BASE/api/self_update/chunk" \
  -H 'content-type: application/json' \
  -d '{"file":"evil.py","part":1,"content":"import os; os.system(\"rm -rf /\")"}' \
  | python3 -m json.tool
```

**Expected:** HTTP 403, error mentions `not in the updatable allowlist`.

---

## Test 6 — Self-Update: Status + Preview

```bash
# Check staging status (should be empty after discards)
curl -s "$BASE/api/self_update/status" | python3 -m json.tool

# List backups (from any prior assemblies)
curl -s "$BASE/api/self_update/backups" | python3 -m json.tool
```

---

## Test 7 — Self-Update: Successful Update (CAUTION — writes real files)

> [!CAUTION]
> This test **actually writes to `qwen_app/app.py`**, bumps the version, and
> pushes a git commit. Only run it with content you want deployed.

To test safely, use the current file as the "update":

```bash
# Use the current app.py as the chunk content (no actual change)
CONTENT=$(cat ~/.groq/app.py | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")

curl -s -X POST "$BASE/api/self_update/chunk" \
  -H 'content-type: application/json' \
  -d "{\"file\":\"app.py\",\"part\":1,\"content\":$CONTENT}" \
  | python3 -m json.tool

# Preview before assembling
curl -s "$BASE/api/self_update/preview?file=app.py" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'Preview: {d.get(\"size\",0)} chars, hash={d.get(\"hash\",\"?\")[:16]}')
"

# Assemble — will CI-check, backup, write, bump version, git push
curl -s -X POST "$BASE/api/self_update/assemble" \
  -H 'content-type: application/json' \
  -d '{"file":"app.py","commit_message":"Test: self-update roundtrip (no-op)"}' \
  | python3 -m json.tool
```

**Expected:** `{"ok": true, "ci_passed": true, "status": "deployed", "version": N+1, ...}`.

Then verify version bumped:
```bash
curl -s "$BASE/api/version" | python3 -m json.tool
```

---

## Test 8 — Chat Persistence

```bash
# 8a: Save a test chat
curl -s -X POST "$BASE/api/chats/save" \
  -H 'content-type: application/json' \
  -d '{
    "id": "test-chat-001",
    "title": "",
    "messages": [
      {"role":"user","content":"What is 2+2?"},
      {"role":"assistant","content":"4"}
    ]
  }' | python3 -m json.tool

# 8b: List all chats — should include test-chat-001
curl -s "$BASE/api/chats" | python3 -m json.tool

# 8c: Load the chat by ID (note: response wraps in "chat" key)
curl -s "$BASE/api/chats/test-chat-001" | python3 -c "
import sys, json
d = json.load(sys.stdin)
chat = d['chat']
print(f'Title: {chat[\"title\"]}')
print(f'Messages: {len(chat[\"messages\"])}')
"

# 8d: Rename it
curl -s -X POST "$BASE/api/chats/rename" \
  -H 'content-type: application/json' \
  -d '{"id":"test-chat-001","title":"Math Test"}' \
  | python3 -m json.tool

# 8e: Verify rename
curl -s "$BASE/api/chats/test-chat-001" | python3 -c "
import sys, json
d = json.load(sys.stdin)
title = d['chat']['title']
print(f'Title: {title}')
assert title == 'Math Test', 'RENAME FAILED'
print('✓ Rename OK')
"

# 8f: Delete it
curl -s -X POST "$BASE/api/chats/delete" \
  -H 'content-type: application/json' \
  -d '{"id":"test-chat-001"}' \
  | python3 -m json.tool

# 8g: Confirm deletion — should 404
curl -s -o /dev/null -w "%{http_code}" "$BASE/api/chats/test-chat-001"
echo ""  # Should print 404
```

---

## Test 9 — Backdoor Chat (spends tokens!)

```bash
curl -s -X POST "$BASE/api/remote/send" \
  -H 'content-type: application/json' \
  -d '{"prompt":"Say exactly: SELFTEST_OK"}' \
  | python3 -c "
import sys, json
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try:
        d = json.loads(line)
        if 'content' in d: print(d['content'], end='')
        if d.get('done'): print()
    except: pass
"
```

**Expected:** Model responds with something containing `SELFTEST_OK`. Costs ~\$0.002.

---

## Test 10 — Key Management (read-only)

```bash
# List keys (masked)
curl -s "$BASE/api/keys" | python3 -m json.tool
```

---

## Quick Smoke Test (all non-destructive tests in one go)

```bash
PORT=$(cat ~/.groq/app_url | grep -oE '[0-9]+$')
BASE="http://127.0.0.1:${PORT}"
PASS=0; FAIL=0

check() {
  local name="$1" code="$2" expect="$3"
  if [ "$code" = "$expect" ]; then
    echo "✓ $name (HTTP $code)"
    PASS=$((PASS+1))
  else
    echo "✗ $name (HTTP $code, expected $expect)"
    FAIL=$((FAIL+1))
  fi
}

check "Health"   "$(curl -s -o /dev/null -w '%{http_code}' $BASE/health)" "200"
check "Version"  "$(curl -s -o /dev/null -w '%{http_code}' $BASE/api/version)" "200"
check "Chats"    "$(curl -s -o /dev/null -w '%{http_code}' $BASE/api/chats)" "200"
check "Status"   "$(curl -s -o /dev/null -w '%{http_code}' $BASE/api/self_update/status)" "200"
check "Keys"     "$(curl -s -o /dev/null -w '%{http_code}' $BASE/api/keys)" "200"
check "Models"   "$(curl -s -o /dev/null -w '%{http_code}' $BASE/api/models)" "200"
check "Allowlist" "$(curl -s -o /dev/null -w '%{http_code}' -X POST $BASE/api/self_update/chunk -H 'content-type: application/json' -d '{"file":"evil.py","part":1,"content":"x"}')" "403"

echo ""
echo "Results: $PASS passed, $FAIL failed"
```

---

## After Testing

- If Test 7 was run (successful update), the version bumped — check with `curl $BASE/api/version`
- Check `~/.groq/chats/` for any leftover test chat files
- Check `~/.groq/incoming_update/backups/` for any backups created
- To reset the version after a test bump, edit `version.json` manually

---

## Known Issues & Findings (11 Nov 2026)

| # | Finding | Status |
|---|---------|--------|
| 1 | CI truncation heuristics (bracket/quote counting) gave false positives on valid code — raw `count()` hits brackets inside strings/comments/f-strings | **Fixed** — demoted to non-blocking warnings when AST parse passes |
| 2 | `GIT_ROOT` resolved to `~/.groq` (installed copy), not the source repo → git operations failed with "not a git repository" | **Fixed** — added detection: checks for `.git` dir, falls back to `~/Developer/groq_ai_studio` |
| 3 | `assemble` wrote only to the running copy (`~/.groq/qwen_app/`), so git saw no changes to commit | **Fixed** — now writes to both running copy and source repo |
| 4 | `GET /api/chats/<id>` wraps response in `{"chat": {...}, "ok": true}` — tests must access `d["chat"]["title"]` not `d["title"]` | **Noted** — test skill updated |
| 5 | Starting Queen headless requires `< /dev/null` — keyboard listener kills process when stdin closes (EOF) | **Noted** — test skill documents this |
| 6 | `_auto_title()` works — saved chat with empty title got auto-titled "What is 2+2?" from first user message | **Verified** ✓ |
| 7 | Queen answered "No, I do not have the ability to self-update" when `system_prompt` was empty in browser | **Fixed** — added `build_queen_system_prompt()` in `app.py` so `/api/chat` and `/api/remote/send` always inject Queen's identity, version, repos, and CI self-update instructions |
| 8 | Python 3.10 f-string in `run_visible_tests.sh` rejected backslashes inside `{...}` | **Fixed** — extracted dict lookups to variables before printing |

## Test Results (11 Nov 2026, v2 — Visible Terminal Run)

| Test | Result | Notes |
|------|--------|-------|
| 1. Health check | ✓ PASS | `{"ok":true,"version":"v2"}` |
| 2. Version endpoint | ✓ PASS | Returns `v2`, `auto_update_repo=markoboskoauroville/groq-auto-update` |
| 3. CI reject (bad Python) | ✓ PASS | HTTP 422, 2 CI errors (syntax + size) |
| 4. CI reject (bad HTML) | ✓ PASS | HTTP 422, 4 CI errors (missing `</html>`, tag balance, title, size) |
| 5. Allowlist enforcement | ✓ PASS | HTTP 403 for `evil.py` |
| 6. Status + backups | ✓ PASS | HTTP 200, `staged=0`, backups listed |
| 7. Successful self-update | ✓ PASS | CI passed, v1→v2, git pushed to both repos |
| 8. Chat CRUD | ✓ PASS | save, auto-title (`Live self-test ping`), rename (`Renamed Self-Test`), delete→HTTP 404 |
| 9. System prompt awareness | ✓ PASS | `build_queen_system_prompt()` (1,746 chars) verified + live `/api/remote/send` confirmed Queen explains her CI self-update pipeline |
