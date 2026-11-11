# Groq AI Studio: takeover

Repository: markoboskoauroville/groq_ai_studio (public, unpromoted: no README, no description; this file is the description).
Status 11.11.2026: version 09 runs on this Mac, port 8765, `/health` answers `{"app":"groq-modern-chat","version":"09","ok":true}`.
Marko, 11.11.2026: "We are developing this app now." Nothing is compiled: it is Python and one HTML file, so there is no
GitHub Actions build; it runs from source.

## What it is
A local chat studio for the Groq API in the browser, started from the terminal with the command `qwen`. A small Flask server
(served by waitress, bound to 127.0.0.1 only) serves one page (`qwen_app/index.html`) and streams Groq chat completions to it.
Default model `qwen/qwen3.8-27b`; the model list is read live from Groq (whisper and guard models filtered out).
Around the chat it has: a key pool with automatic failover, a live spend ledger, multi chat sessions, file attach, a Code Box
mode, a system prompt (persona), a GitHub reader and a "backdoor" so another program (or a Claude session) can type into the
open page. It was generated on 11.11.2026 (04:00 to 08:30) in versions 01 to 09 by an agent in Google Antigravity from
Marko's prompts; the installers `01`..`09` are in ~/Downloads/API (not in this repo; they hold no keys). Only `09` matters
now; `05` to `07` were large self-contained installers, `09` just installs the dependencies and the already written files.

## The commands (on the PATH through ~/.groq in ~/.zshrc)
| Command | What |
|---|---|
| `qwen` | start the studio (`qwen` = `qwen_app/app.py 8765`; env `GROQ_PORT` changes the preferred port). Opens the browser. |
| `groq-chat` | same app, passes its arguments (the port) through. |
| `groq-cli "question"` | one question in the terminal, streamed, with the key pool. `--status` lists the keys masked, `--reset` clears cooldowns. Default model there is `llama-3.3-70b-versatile` (`GROQ_MODEL` changes it). |
Terminal keys while the server runs: `q` quit, `c` (or `o`) open the browser, `g` list 5 GitHub repos, `s` spend, `r` reset
cooldowns, `h` help.

## Files
| File | Job |
|---|---|
| `qwen_app/app.py` | the server: key manager, failover, streaming chat, ledger, GitHub reads, backdoor, port finder, keyboard listener (about 1100 lines) |
| `qwen_app/index.html` | the whole client: sidebar with sessions, spend, model select, zoom, Prose / Code Box toggle, attach and drag-drop, modals for keys, persona, GitHub, billing, settings (about 1700 lines, `__VERSION__` and `__DEFAULT_MODEL__` are replaced by the server) |
| `groq_pool.py` | the older key pool module used by `groq-cli`, importable from any Python: `KeyPool().complete(messages)` / `.stream(messages)` |
| `groq_cli.py`, `groq-cli`, `qwen`, `groq-chat` | the terminal clients and launchers |
| `install.sh` | copies the code into ~/.groq, makes the venv, installs `requirements.txt`; reads no key |
The app expects to live in `~/.groq` (it inserts that folder in `sys.path` and keeps its state there). The repo is the source;
`install.sh` puts it there.

## State on the Mac (never in git)
`~/.groq/keys.txt` (keys, 600), `.env`, `key_state.json` (current key and cooldowns), `spend_ledger.json` (totals and the last
100 requests), `active_port`, `app_url`, `venv/`. `.gitignore` blocks all of these.

## Keys
Keys start with `gsk_`. The parser (`extract_keys_from_noise`) pulls every `gsk_...` of at least 20 characters out of any text:
`.env`, JSON, bash exports, logs. Keys are added in the page (📥 Key Manager: pick a file, or paste into the password field),
or with `POST /api/keys/load-file`, which reads `groq-api.txt` (current folder, else ~/Downloads/API) when no path is sent.
Install does NOT load keys (09 says so). The pool is sticky: it keeps the last working key, cools a key on rate limit
(`retry-after`, minimum 5 s, default 60 s) or for 30 days when rejected, and moves to the next before the first token arrives.
After a failure halfway through a reply the error is shown instead, so text is never doubled. Keys appear only masked
(first 6 and last 4).

## Key behaviours
- **Code Box mode**: toggle under the prompt, or automatic when the prompt says "in the code box", "code only", "just the code",
  "as a code block" and similar (`detect_code_intent`). Adds a system message: only code, one fenced block, no talk.
- **System prompt**: 🎭 persona, saved in the browser.
- **Streaming**: `/api/chat` answers newline-delimited JSON: `{"r":...}` reasoning token, `{"t":...}` text token, `{"u":{...}}`
  final telemetry, `{"error":...}`. Only the last 80 messages are sent.
- **Spend ledger**: per request tokens x price per million (table `MODEL_PRICING`: qwen3.8-27b and qwen3.6-27b 0.80 in / 4.00 out,
  gpt-oss-120b 0.15 / 0.60, gpt-oss-20b 0.075 / 0.30, allam-2-7b 0.20, prompt-guard 0.04 and 0.03, orpheus 0.20, default 0.50 / 1.50).
  Prices are typed in by hand, not read from Groq. If Groq sends no usage the tokens are estimated from the text length.
- **Billing panel** 💰: totals, last 15 requests, and a live check with the first working key (region, rate limits from the response headers).
- **Sessions**: kept in the browser's localStorage (`groq_sessions_v3`, `groq_session_id_v3`, `groq_output_mode`, `groq_persona`, `groq_zoom`).
- **GitHub reader** 🐙: runs the `gh` CLI on this Mac (so it sees private repos Marko is logged in to): `/api/github/repos`,
  `/api/github/contents`, `/api/github/read-url`. Read only. Attaches a file to the chat.
- **Port**: starts at 8765 and takes the first free port up to 200 higher; writes it to `~/.groq/active_port` and the URL to `~/.groq/app_url`.

## HTTP API (127.0.0.1)
`GET /` page, `/health`, `/api/models`, `/api/billing`, `/api/keys`, `/api/events` (server-sent events), `/api/session/messages`,
`/favicon.ico` (the orange Groq "thunderstrike" on dark); `POST /api/chat`, `/api/keys/import`, `/api/keys/upload`, `/api/keys/delete`
(`id` or `index`), `/api/keys/clear`, `/api/reset-keys`, `/api/keys/load-file`, `/api/remote/send`
(`{"prompt","mode","model","system_prompt"}`: a program types into the page; the open page sees it live over `/api/events` and the
reply and telemetry come back in the response), `/api/github/*`.

## What has been checked, and what has not
Checked 11.11.2026: the server is up and healthy, the keys file holds keys, the code was read through, and a three turn casual
chat through `POST /api/remote/send` worked on the first key (about 0.5 s a reply, $0.0022 a turn; the 2,600 tokens shown per turn look
inflated, probably the reasoning, see LESSONS). NOT checked by this
session: a real answer from every model, failover with a truly exhausted key, the GitHub panel, drag and drop, the stress test
`stress_test_09.py` (lives in ~/.gemini/antigravity/brain/.../scratch, not in this repo), the page on a small window.

## Dangers, named plainly
- `/api/keys/load-file` reads any file path the caller sends, and `/api/keys/clear`, `/api/keys/delete`, `/api/remote/send`
  have no password. Safe only because it listens on 127.0.0.1; any local program or web page open in the browser can call it
  (no CORS or origin check). Add a token or an Origin check before anything else is built on it.
- `run_gh` gives the page read access to every repo `gh` can see.
- Two key code paths exist (`groq_pool.py` for the CLI, `DynamicKeyPool` in `app.py`): they must stay in step.
- Cost is shown from a hand-typed price table, so the ledger can drift from Groq's real invoice.
- `launch_server` in the old installer runs `lsof -ti:PORT | xargs kill -9`, which kills whatever holds the port.

## Where it fits
Marko's Groq model research (Groq has no image model, models researched for TTT) and scribe's Groq transcription use the same
Groq keys (numbered keys in ~/Downloads/API/groq-api.txt). KeyringTester checks that these keys work and has read the image with
`qwen/qwen3.8-27b` (14.10.2026). Work on this app: edit here in ~/Developer/groq_ai_studio, run `./install.sh`, restart `qwen`.
Skill: `skills/groq-ai-studio/SKILL.md`.
