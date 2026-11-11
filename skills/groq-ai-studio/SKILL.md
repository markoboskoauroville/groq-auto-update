---
name: groq-ai-studio
description: Groq AI Studio, Marko's local browser chat for the Groq API (command `qwen` / "Queen", repo groq_ai_studio, installed in ~/.groq): key pool with failover, spend ledger, Code Box, GitHub reader, backdoor API, CI-gated self-update pipeline, server-side chat persistence, auto-update GitHub repo. Use for ANY qwen command / Queen / Groq chat app / Groq key pool / groq-cli / Groq AI Studio task.
---
# Groq AI Studio

**Note:** "Queen" = `qwen` command. When Marko says "Queen", he means this qwen application.

Read `TAKEOVER.md` in the repo first: it holds everything known (files, commands, HTTP API, dangers, what is untested).

## Space
- Source: ~/Developer/groq_ai_studio (public, no README by rule). Running copy: ~/.groq (`./install.sh` copies source there).
- Auto-update repo: `markoboskoauroville/groq-auto-update` (public). CI-validated updates are pushed here automatically.
- Start: `qwen` (port 8765, first free port after it; `~/.groq/app_url` says which). Health: `curl http://127.0.0.1:8765/health`.
- Keys: ~/.groq/keys.txt and ~/Downloads/API/groq-api.txt: never print, never commit. Masked form only.
- Chats: ~/.groq/chats/ — server-side JSON files, local only, NOT in git.
- Test a turn without the browser: `curl -s -X POST http://127.0.0.1:8765/api/remote/send -H 'content-type: application/json' -d '{"prompt":"hi"}'` (spends tokens: say so).

## Version System
- Version stored in `version.json` at repo root: `{"version": N, ...}`
- Displayed as `vN` badge in the top-right corner of the web UI
- Bumps by 1 on every successful CI-validated update
- Check current version: `GET /api/version`

## Self-Update Pipeline (CI-gated)
The app can update its own source files through a chunked transfer system:
1. Code is sent in chunks via `POST /api/self_update/chunk` (file, part number, content)
2. `POST /api/self_update/assemble` runs the CI pipeline before writing:
   - **Python:** AST parse, truncation detection (unbalanced quotes/brackets), structural checks
   - **HTML:** tag balance (`<html>`, `<body>`, `<script>`), must end with `</html>`, JS brace balance
   - **Size:** new file must be ≥30% of old file size
3. If CI passes: backup → write → version bump → git commit+push to both repos
4. If CI fails: **nothing is written**, errors returned, chunks stay in staging

## Chat Persistence
- All chats saved to `~/.groq/chats/` as JSON files (local only, not in git)
- Auto-titled from first user message
- Double-click session name in sidebar to rename
- Server syncs on every save, loads from server on page load
- Endpoints: `GET /api/chats`, `GET /api/chats/<id>`, `POST /api/chats/save`, `POST /api/chats/rename`, `POST /api/chats/delete`

## HTTP API (127.0.0.1)
| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Main page |
| GET | `/health` | Health check |
| GET | `/api/version` | Version info + update log |
| POST | `/api/chat` | Streaming chat (NDJSON) |
| POST | `/api/remote/send` | Backdoor: inject a prompt |
| GET | `/api/events` | SSE live events |
| GET/POST | `/api/keys/*` | Key management |
| GET/POST | `/api/chats/*` | Chat persistence |
| GET/POST | `/api/self_update/*` | Self-update pipeline |
| GET/POST | `/api/github/*` | GitHub reader |
| GET | `/api/models` | Available models |
| GET | `/api/billing` | Spend + rate limits |
| GET/POST | `/api/test/live` | Built-in visible self-test backdoor (prints 9 checks to Queen's terminal + returns JSON) |
| POST | `/api/terminal/log` | Print live `$ command` / status banners into Queen's terminal console |

## Rules
1. Edit in the repo, run `./install.sh`, restart `qwen`; never edit only ~/.groq.
2. Before each commit: `grep -rn 'gsk_' .` must find nothing. State files are in `.gitignore`.
3. No Mac build (it is Python). Push to main.
4. Write every correction and new feature back into TAKEOVER.md and LESSONS.md at the close.
5. **Never commit truncated code.** The CI pipeline rejects it automatically.

## Open work
Add a token or Origin check to the local API (TAKEOVER, Dangers); merge the two key pools; read real prices instead of the typed table.

## Run log
- 11.11.2026: repo created from the running v09; skill written. Backdoor chat tested (3 turns, works); token count per turn looks inflated, check it.
- 11.11.2026: v1 upgrade — CI pipeline, self-update panel, auto-update GitHub repo, version tracking, server-side chat persistence, chat rename.
- 11.11.2026: Added `GEMINI.md` workspace rule — mandatory handover + skill update after every code change. Both repos now public.
- 11.11.2026: Testing session — fixed 3 bugs: CI false positives (bracket counting demoted to warnings), GIT_ROOT now detects installed vs source repo, assemble writes to both copies. All tests pass. Version bumped to v2. Testing skill written at `skills/groq-ai-studio-testing/SKILL.md`.
- 11.11.2026: Added `.agents/skills.json` manifest, visible macOS Terminal test runner (`skills/groq-ai-studio-testing/scripts/run_visible_tests.sh`), Python server live-test backdoors (`POST /api/test/live`, `POST /api/terminal/log`, `'t'` terminal key), and `build_queen_system_prompt()` so Queen always knows how she self-updates. Verified 9/9 live checks + backdoor chat in Terminal.app.

## Mistakes already made
- Looking for `qwen` with `which` in a tool shell: it is in ~/.groq, on the PATH only through ~/.zshrc.
- Treating a `gsk_` grep as a secret check: compare the real keys by exact match instead (script in the 11.11.2026 close).
- CI truncation heuristics (raw bracket/quote counting) block valid code: AST parse is the real gate; raw counts are informational only.
- Starting Queen headless without `< /dev/null`: the keyboard listener kills the process when stdin closes. Use `nohup ... < /dev/null > /tmp/qwen.log 2>&1 &`.
- `GIT_ROOT` resolved to `~/.groq` (installed copy) instead of source repo: git operations fail. Fixed with `.git` directory detection.

## Talking to it
`/api/remote/send` keeps the whole conversation in the server (`active_messages`, last 80 sent), so a test chat continues across
calls and also shows live in the open page. Send `system_prompt` each time. Each turn costs about $0.002 on qwen3.8-27b.

The Qwen model can read the auto-update repo (`markoboskoauroville/groq-auto-update`) through the GitHub Reader (🐙) in the UI. It knows this repo exists and can browse its files.
