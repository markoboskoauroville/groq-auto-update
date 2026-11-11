---
name: queen-auto-update-pipeline
description: >-
  Exhaustive minute-detail blueprint and skill for Groq AI Studio (Queen / qwen)
  Dual-Kind API Loader (Groq LPU Chat vs. Google Cloud/Gemini & Anthropic/Claude
  Auto-Update APIs), Topbar Auto-Update Provider + Model Switch, Pre-Briefed
  Surgical Patch Pipeline with USD Cost Receipt, and "Learning by Watching"
  Automatic Split-Screen Software Engineer Studio. Use whenever updating Queen
  via external APIs, working on auto_updater.py, managing multi-provider keys,
  or inspecting Queen's full architecture.
---

# Queen (`qwen`) — Dual-Kind API Loader & Surgical Auto-Update Pipeline

> **Terminology:** **"Queen"** = **`qwen`** = **Groq AI Studio**.
> Everything in this skill is written in minute detail so any external LLM API
> (Anthropic Claude or Google Cloud / Gemini) or coding agent understands the
> entire repository, local macOS installation, CI gates, git remotes, pricing,
> and surgical code-patching protocol **without wasting tokens reading 5,000+ lines**.

---

## 1. Complete Repository & Runtime Topology

| Item | Exact Location / Value | Purpose |
|---|---|---|
| **Primary Git Repo (`origin`)** | `https://github.com/markoboskoauroville/groq_ai_studio.git` | Source of truth (public, unpromoted: **no `README.md`** by rule; `TAKEOVER.md` is the primary doc). |
| **Auto-Update Mirror (`auto-update`)** | `https://github.com/markoboskoauroville/groq-auto-update.git` | Public mirror pushed automatically on every CI-validated update. |
| **Local Source Checkout** | `~/Developer/groq_ai_studio` | Where all edits, `version.json` bumps, and `git commit` / `git push` happen. |
| **Installed Runtime Directory** | `~/.groq` | Deployed copy executed by `qwen`, `groq-chat`, and `groq-cli`. Created/synced by `./install.sh`. |
| **Python Virtualenv** | `~/.groq/venv/bin/python` | Python 3 venv (`Flask`, `waitress`, `groq`, `httpx`, `python-dotenv`). |
| **Backend Server Entry** | `qwen_app/app.py` | Flask + Waitress (`threads=8`, bound to `127.0.0.1:8765`, auto-increments up to `+200` if port busy). |
| **Surgical Auto-Updater Module** | `qwen_app/auto_updater.py` | Dual-kind key parser, Google/Anthropic streaming clients, surgical patch engine, CI/git/deploy orchestrator, USD cost ledger. |
| **Frontend Single-Page App** | `qwen_app/index.html` | Complete CSS + HTML + vanilla JS client (`__VERSION__`, `__DEFAULT_MODEL__`, `__API_TOKEN__` injected by server). |
| **Shared Groq Key Pool** | `groq_pool.py` | `DynamicKeyPool` (web server) + `KeyPool` (`groq-cli`) + `extract_keys_from_noise`. |
| **Version Ledger** | `version.json` | `{"version": N, "updated_at": "...", "log": [...]}` — rendered as `vN` badge in `#topbar`. |
| **Skills Manifest** | `.agents/skills.json` | Points to `skills/` (`groq-ai-studio`, `groq-ai-studio-testing`, `queen-auto-update-pipeline`, `star-menu-computer-control`, `elevate-media-production`). |

### Local State Files in `~/.groq/` (NEVER committed to Git — `.gitignore` enforced)

| File / Folder | Mode | Format & Contents |
|---|---|---|
| `~/.groq/keys.txt` | `0600` | Kind 1 (Groq Chat API) keys — one `gsk_...` key per line. |
| `~/.groq/key_state.json` | `0600` | Sticky active key index & per-model rate-limit / rejection cooldown timestamps. |
| `~/.groq/auto_update_keys.json` | `0600` | Kind 2 (Auto-Update API) keys & config: `{"active_provider": "anthropic"\|"google", "active_models": {"anthropic": "...", "google": "..."}, "keys": {"anthropic": [...], "google": [...]}}`. |
| `~/.groq/auto_update_ledger.json` | `0600` | Cumulative USD spend & per-update receipts for Google & Anthropic surgical updates. |
| `~/.groq/spend_ledger.json` | `0600` | Groq LPU chat token & USD spend ledger (`total_spent`, `history`). |
| `~/.groq/api_token` | `0600` | 48-hex-char secret for `X-Queen-Token` CSRF/local auth header. |
| `~/.groq/active_port` & `app_url` | `0644` | Active bound port (e.g. `8765`) and URL (`http://127.0.0.1:8765`). |
| `~/.groq/chats/*.json` | `0644` | Server-side persistent chat sessions (`id`, `title`, `messages`, timestamps). |
| `~/.groq/incoming_update/` | `0755` | Chunk staging (`chunk_<file>_part<NNN>.txt`) + automatic backups (`backups/<file>.backup_<ts>`). |

---

## 2. Dual-Kind API Architecture

Queen understands and separates **two distinct kinds of APIs** from any pasted text, `.env`, `.json`, shell script, or uploaded file:

### Kind 1 — Groq Chat API (`kind: "groq"`)
- **Purpose:** Ultra-fast LPU conversational chat, Code Box generation, and `/api/remote/send` backdoor turns.
- **Key Pattern:** `gsk_[A-Za-z0-9_-]{20,}`
- **Default Discovery File:** `~/Downloads/API/groq-api.txt`
- **Storage:** `~/.groq/keys.txt` (`DynamicKeyPool` with sticky rotation & cooldowns).

### Kind 2 — Auto-Update Engineering API (`kind: "auto_update"`)
- **Purpose:** Autonomous surgical code updates, repo syncing, CI validation, local `~/.groq` deployment, and educational split-screen live streaming — **without relying on Groq models**.
- **Supported Providers:**
  1. **Google (`google` — Google Cloud / Gemini API)**
     - **Key Pattern:** `AIza[0-9A-Za-z_-]{30,}` (standard 39-char Google Cloud / Gemini API key) or `ya29.[0-9A-Za-z._-]+` (Google Cloud OAuth bearer token).
     - **Default Discovery Files in `~/Downloads/API/`:** `gemini_key.txt`, `VOICES_gemini-free-tier-api.txt`.
     - **Streaming Endpoint:** `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse&key={API_KEY}`
     - **Live Model List Endpoint:** `GET https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}`
     - **Curated Default Models:** `gemini-2.5-flash` (fast/cheap surgical default), `gemini-2.5-pro`, `gemini-2.5-flash-lite`, `gemini-2.0-flash`.
  2. **Anthropic (`anthropic` — Claude API)**
     - **Key Pattern:** `sk-ant-[A-Za-z0-9_-]{20,}`
     - **Default Discovery Files in `~/Downloads/API/`:** `Claude.api.txt`, `HAIKU-KEY.txt`.
     - **Streaming Endpoint:** `POST https://api.anthropic.com/v1/messages` with headers `x-api-key`, `anthropic-version: 2023-06-01`, `content-type: application/json`, `"stream": true`.
     - **Live Model List Endpoint:** `GET https://api.anthropic.com/v1/models`
     - **Curated Default Models:** `claude-sonnet-4-5`, `claude-haiku-4-5`, `claude-opus-4-5`, `claude-3-7-sonnet-latest`, `claude-3-5-haiku-latest`.

> **Security Invariant:** Keys are **NEVER** returned unmasked over HTTP, **NEVER** printed to terminal logs, and **NEVER** written inside `~/Developer/groq_ai_studio`. Mask format: `prefix[:7] + "…" + suffix[-4:]`.

---

## 3. Pre-Briefed Surgical Update Protocol (Why Updates Cost Pennies)

Instead of feeding 5,000+ lines of source code and asking the LLM to regenerate entire files (which wastes ~40,000 output tokens, risks truncation, and costs `$0.60+`), `qwen_app/auto_updater.py` prepares everything in advance:

1. **Repo & Local Clone Verification (Stage 1):**
   - Checks `~/Developer/groq_ai_studio`. If missing on a new machine, clones `https://github.com/markoboskoauroville/groq_ai_studio.git` automatically; otherwise runs `git status` and fast-forwards if clean.
2. **Smart Pre-Briefed Context Slice Extraction:**
   - Builds a compact structural map of `qwen_app/app.py`, `qwen_app/auto_updater.py`, and `qwen_app/index.html` (section banners, Flask `@app` routes with line numbers, HTML `#id` landmarks) plus targeted code windows matching keywords in the user's update request.
3. **Surgical Patch Output Schema (Stage 2):**
   - The selected Google or Anthropic model streams a concise JSON specification wrapped in `<queen_update>...</queen_update>` (or fenced JSON) containing:
     ```json
     {
       "summary": "One-line summary of the feature/fix",
       "educational_notes": [
         "Plain-English explanation of how and why a senior engineer makes this change"
       ],
       "commit_message": "feat: concise git commit message",
       "edits": [
         {
           "file": "index.html",
           "section": "#topbar controls",
           "explanation": "Add button/element right next to existing control",
           "action": "replace",
           "search": "exact existing snippet from target file",
           "content": "updated snippet replacing search"
         }
       ]
     }
     ```
   - Supported `action` values:
     - `"replace"`: Replaces exact `search` block with `content` (falls back to trailing-whitespace-normalized line match if exact match misses by spaces).
     - `"insert_after"`: Keeps `search` intact and injects `content` immediately after it.
     - `"insert_before"`: Injects `content` immediately before `search`.
4. **In-Memory Patching & Unified Diff Generation (Stage 3):**
   - Applies each surgical edit in memory and computes `difflib.unified_diff` (`--- a/<file>`, `+++ b/<file>`) for the live split-screen viewer.
   - Allowable target files (`UPDATABLE_FILES`): `app.py`, `index.html`, `auto_updater.py`.
5. **CI Gate Validation (`ci_run_all` — Stage 4):**
   - `.py` files: non-empty + `ast.parse()` syntax check + structural `import`/`def` sanity + size ratio `>= 30%` of current file.
   - `.html` files: non-empty + ends with `</html>` + balanced `<html>`, `<head>`, `<body>`, `<script>` tags + balanced `{` / `}` inside `<script>` blocks + `<title>` present + size ratio `>= 30%`.
   - If CI fails: **nothing is written to disk**, HTTP 422 / error event emitted.
6. **Backup, Repo Write, Version Bump, Dual-Remote Push & `~/.groq` Sync (Stage 5):**
   - Saves timestamped backups in `~/.groq/incoming_update/backups/`.
   - Writes updated files to `~/Developer/groq_ai_studio/qwen_app/`.
   - Bumps `version.json` (`vN` → `vN+1`).
   - Runs `./install.sh` (or direct atomic file copy into `~/.groq/qwen_app/` + `~/.groq/version.json`) so the local installation is updated immediately.
   - Commits & pushes `main` to both `origin` (`markoboskoauroville/groq_ai_studio`) and `auto-update` (`markoboskoauroville/groq-auto-update`) after verifying zero secret leaks (`gsk_`, `sk-ant-`, `AIza`).
7. **Exact USD Cost Calculation & Terminal + UI Printout (Stage 6):**
   - Reads exact `input_tokens`, `output_tokens`, `cache_read_input_tokens`, and `cache_creation_input_tokens` from Anthropic SSE (`message_start` + `message_delta`) or Google Gemini SSE (`usageMetadata.promptTokenCount` + `candidatesTokenCount` + `thoughtsTokenCount`).
   - Multiplies by exact per-1M-token USD rates, appends receipt to `~/.groq/auto_update_ledger.json`, broadcasts `cost_receipt` SSE event to the split-screen UI, and prints a formatted USD cost box in Queen's server terminal.

---

## 4. Provider Token Pricing Table (USD per 1,000,000 Tokens)

| Provider | Model ID / Prefix | Input / 1M | Output / 1M | Notes |
|---|---|---:|---:|---|
| **Google** | `gemini-2.5-flash` | `$0.30` | `$2.50` | Default fast surgical model |
| **Google** | `gemini-2.5-flash-lite` | `$0.10` | `$0.40` | Ultra-low-cost surgical edits |
| **Google** | `gemini-2.5-pro` | `$1.25` | `$10.00` | Complex multi-file architecture edits |
| **Google** | `gemini-2.0-flash` | `$0.10` | `$0.40` | Fast general edits |
| **Anthropic** | `claude-sonnet-4-5` / `claude-3-7-sonnet*` / `claude-3-5-sonnet*` | `$3.00` | `$15.00` | Cache write `$3.75`, cache read `$0.30` |
| **Anthropic** | `claude-haiku-4-5` | `$1.00` | `$5.00` | Fast surgical patching |
| **Anthropic** | `claude-3-5-haiku*` | `$0.80` | `$4.00` | Ultra-cheap Claude surgical patching |
| **Anthropic** | `claude-opus-4-5` | `$5.00` | `$25.00` | Flagship deep reasoning |
| **Anthropic** | `claude-opus-4-1` / `claude-opus-4*` | `$15.00` | `$75.00` | Legacy Opus tier |

---

## 5. Complete UI & Split-Screen ("Learning by Watching") Specification

### Top Navigation Bar (`#topbar` in `qwen_app/index.html`)
1. **Left (`Groq Chat`):** Sidebar expand button + `#model-select` (Groq LPU chat model picker).
2. **Center-Left (`Auto-Update Controls`):**
   - **Provider Switch (`#au-provider-switch`):** Segmented pill toggling **`Google`** vs **`Anthropic`** (`POST /api/auto_update/config`).
   - **Auto-Update Model Switch (`#au-model-select`):** Dynamic `<select>` right next to the provider switch showing models for the active provider (`gemini-2.5-flash`, `claude-sonnet-4-5`, etc.).
   - **`⚡ Auto-Update` Button (`#btn-auto-update-open`):** Opens the split-screen Engineer Studio and focuses the surgical update instruction bar.
   - **`◫` Split Toggle (`#btn-toggle-split`):** Manually toggles the 50/50 split-screen educational view at any time.
3. **Right:** Zoom `− / 100% / +`, `vN` `#version-badge`, `⭐` Star Menu, `🔊` Voice Engine, `🎬` Elevate Media, `🐙` GitHub, `🔧` Chunk Self-Update, `🎭` Persona, `💰` Billing, `⚙️` Settings.

### Automatic Split-Screen Workspace (`#workspace-split`)
Inside `#main`, below `#topbar` and `#status-bar`:
- **Left Pane (`#chat-pane`):** Standard Groq AI Studio chat scroll view + prompt dock.
- **Right Pane (`#engineer-pane` — "Invisible Software Engineer · Learning by Watching"):**
  - Automatically slides open (`50%` width) whenever an auto-update starts via UI or HTTP API (`auto_update_event` SSE).
  - **Live Status Strip:** Flask Server status (`http://127.0.0.1:8765`, `PID`, `version`, `CI Gate`), active Provider badge (`Google` / `Anthropic`), active Model badge, and current target (`Working on: ...`).
  - **6-Stage Educational Stepper:**
    1. `1. Repo & Context Map` — Explains how engineers pull `main` and locate exact line anchors instead of guessing.
    2. `2. Model Thinking & Surgical Plan` — Streams real-time model reasoning & architectural plan.
    3. `3. Surgical Code Injection` — Explains why small `SEARCH → REPLACE` diffs beat full-file rewrites.
    4. `4. Automated CI Gate` — Shows AST syntax, HTML tag/brace balance, and truncation checks running before disk write.
    5. `5. Git Push & Local ~/.groq Sync` — Shows backup creation, `version.json` bump, `./install.sh` sync, and dual GitHub push.
    6. `6. USD Cost Receipt & Live Verify` — Displays exact token counts, per-million rates, and total cost in dollars (`$0.00XXXX`).
  - **Live Verbose Stream Console (`#au-stream-log`)** + **Colorized Unified Diff Viewer (`#au-diff-view`)** + **USD Receipt Card (`#au-cost-card`)**.

---

## 6. Auto-Update HTTP API Reference (`127.0.0.1:8765`)

| Method | Endpoint | Request / Purpose |
|---|---|---|
| `GET` | `/api/auto_update/config` | Returns active provider (`google`\|`anthropic`), active model per provider, masked key status for both providers, model catalogs, pricing table, and Flask server status. |
| `POST` | `/api/auto_update/config` | Body `{"provider": "google"\|"anthropic", "model": "..."}` — switches active topbar auto-update provider and/or model immediately and broadcasts SSE `auto_update_config`. |
| `GET` | `/api/auto_update/models?provider=google\|anthropic` | Fetches live models from Google Gemini or Anthropic API (if key configured) merged with curated surgical defaults + USD rates. |
| `POST` | `/api/auto_update/keys/import` | Body `{"content": "...", "provider": "auto"}` — noise-tolerant extraction of `AIza...` (Google), `sk-ant-...` (Anthropic), and `gsk_...` (Groq, forwarded to `DynamicKeyPool`). |
| `POST` | `/api/auto_update/keys/load-default` | Scans `~/Downloads/API/` (`Claude.api.txt`, `HAIKU-KEY.txt`, `gemini_key.txt`, `VOICES_gemini-free-tier-api.txt`, `groq-api.txt`) and loads masked keys into Kind 1 + Kind 2 pools without exposing raw secrets. |
| `POST` | `/api/auto_update/keys/delete` | Body `{"provider": "google"\|"anthropic", "id": "..."}` — deletes a specific key or clears a provider slot. |
| `POST` | `/api/auto_update/run` | Body `{"instruction": "...", "provider": "...", "model": "...", "dry_run": false, "target_files": ["index.html"]}` — runs the full 6-stage surgical update pipeline, streaming `auto_update_event` SSE messages to the split-screen UI and returning the final JSON + USD cost receipt. |
| `GET` | `/api/auto_update/status` | Returns current/last auto-update job state, recent events, Flask server health/uptime/PID, and repo git status. |
| `GET` | `/api/auto_update/ledger` | Returns cumulative auto-update spend in USD and history of completed surgical updates from `~/.groq/auto_update_ledger.json`. |
