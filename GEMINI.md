# Groq AI Studio — Workspace Rules

## 1. Documentation Sync (Mandatory After Every Step)

After **every code change or test step** in this project, you MUST immediately update:

1. **The handover document** — the artifact `handover.md` in the conversation's brain directory. Reflect the current state, exact test results, what changed, and what's next.
2. **The skill files**:
   - `skills/groq-ai-studio/SKILL.md` — architecture, endpoints, lessons, and mistakes.
   - `skills/groq-ai-studio-testing/SKILL.md` — test runbook, known issues, and latest test results.
3. **`TAKEOVER.md`** — keep the repository's primary description and API table in sync.

Do this at the end of every step in real time, never deferred.

## 2. Visible Live Testing — "In Front of My Eyes" (Mandatory)

Whenever testing Queen (`qwen`), you MUST run tests **visibly in front of the user's eyes**, never hidden silently in background subshells:

1. **Primary (macOS Terminal.app):** Run `bash skills/groq-ai-studio-testing/scripts/run_visible_tests.sh`. This uses `osascript` to open and focus macOS **Terminal.app**, prints every command (`$ ...`) and result (`✓ PASS` / `✗ FAIL`) live on screen, and tees output to `/tmp/queen_visible_test.log`.
2. **Python Server Backdoor (`/api/test/live` & `/api/terminal/log`):**
   - `POST http://127.0.0.1:8765/api/test/live` runs the 8-check built-in self-test suite inside `qwen_app/app.py` and prints colorized step-by-step output directly into Queen's own running server terminal window (or press `'t'` interactively in Queen's terminal).
   - `POST http://127.0.0.1:8765/api/terminal/log` (`{"level":"cmd|info|pass|fail","message":"..."}`) writes live behind-the-scenes command logs straight to Queen's server console.

## 3. Repository Skills Manifest (`.agents/skills.json`)

All repository skills are declared in `.agents/skills.json` pointing to `skills/`:
- `skills/groq-ai-studio/SKILL.md` — Core app & self-update skill
- `skills/groq-ai-studio-testing/SKILL.md` — Visible live testing runbook & `scripts/run_visible_tests.sh`

## 4. Other Standing Rules

- **"Queen" = `qwen` = this app.** Use this terminology.
- **Keys must NEVER appear in code, commits, or repos.** Run `grep -rn 'gsk_' .` before every git commit.
- **No README in this repo** — documentation lives in `TAKEOVER.md` and the skill files.
- **Edit in `~/Developer/groq_ai_studio`, deploy with `./install.sh`, restart `qwen`.** Never edit `~/.groq` directly.
