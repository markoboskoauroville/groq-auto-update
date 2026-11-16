15.11.2026 (training mode, "train the Grok and macro recorder to execute everything we are doing"): taught earlier today and also missing here: router-mode (qwen_app/router_mode.py: router status, use phone / use SIM with explicit "yes, use ..."), sony-camera (qwen_app/sony_camera.py: connect, start, stop, camera status through MACRO_SKILLS sonycam), yoga-pose-images (queen_skills/yoga-pose-images.md). New today: `qwen_app/ops_hands.py` (one module, `chat_ops_command`, wired first after the volume command in `_local_command_answer`, local, $0) with skills vpn-mantra, stream-preshow-vm, talk-mode, vtt-engines, clean-up-tests, g815-light-show, meditation-room-mac. Phrases: "VPN status|Frankfurt|direct"; "pre-show status", "start pre-show until HH:MM", "stop pre-show", "stream viewers", "go live" (checks only) then "yes go live [N]"; "talk mode status|on|off", "auto", "manual", "space mode test|off"; "which engine [for hr]", "use engine <id> [for hr]", "engine ranking"; "clean up tests" (list) then "yes, clean up tests --kill"; "light show now", "stop light show", "idle light show on|off|status"; "meditation room status", "meditation room NDI on|off", "pre-show text <words>". Macro skills added: talk-auto-switch, talk-mode-switch, vpn-exit-node. Untested on purpose: "yes go live" (public), "space mode test" (Talk Mode lacked Accessibility).

14.11.2026: `/api/system/settings?pane=<name>` + chat "open the X settings page" (system_settings.py, skill open-settings-pane.md): opens a System Settings pane and verifies the window title and front app.

# Groq AI Studio: takeover

15.11.2026: `qwen_app/ndi_monitor.py` + `queen_skills/ndi-monitor-source.md`: `GET /api/ndi/sources`, `POST /api/ndi/select {source}` and local chat ("show Meditation Room in the NDI monitor", "switch NDI source to X", "which NDI sources are there") call the macro skills ndi-monitor-list / ndi-monitor-source (MACRO_SKILLS, tool ndimon). Tested through `queen` with a screenshot.

## 16.11.2026: Google Photos album + share link (`qwen_app/gphotos_album.py`, skill `queen_skills/google-photos-album.md`)
Marko: "make gallery in my Google photos and then we're going to share it with Svemir". Route `POST /api/gphotos/album {album, files, share}`; local chat command ($0): `make a Google Photos album "Title" from ~/folder` or `share link of my Google Photos album "Title"`. Firefox BiDi, real clicks, files built in the page; the link is answered, never sent. Tested through Queen's chat 16.11.2026 (answered the link of "Wyoga poses (wooden mannequin)", $0).

## 14.11.2026 (night, cloud): PHASE A, the Swift app IS Queen on 8765 (app v5)

Marko: "one Queen only, the Swift app, no Flask server behind it, done in phases." Report: `docs/PHASE_A_REPORT.md`.

**Ports.** `127.0.0.1:8765` = the Swift app (`mac_app/app/core/`, BSD sockets, no dependency). `127.0.0.1:8766` = the Python
server, internal only, no web page, started by the app as its child (`~/.groq/qwen` with `QWEN_BACKEND=1 GROQ_PORT=8766`,
log `~/.groq/qwen_backend.log`, its port in `~/.groq/backend_port`). The app writes `active_port`=8765 and `app_url`. A watchdog
checks the backend every 5 s and starts it again after 3 failed checks (at most once per 20 s). START QUEEN restarts it, OFF
stops both. If an OLD Python Queen holds 8765 when the app starts (her `/api/app/status` has no `"face"`), she gets SIGTERM
and the app takes the port. On Linux (the VM) nothing changed: `app.py` alone on 8765 (`QWEN_BACKEND` unset).

**Moved to Swift (same paths, same JSON/NDJSON/SSE shapes):** `/health`, `/api/version`, `/api/app/status` (+ `face`, `backend`,
`app_version`), `/api/models`, `/api/billing`, `/api/chat`, `/api/events`, `/api/session/messages`, `/api/remote/send`
(+ `test_bad_key:true` for a live failover test), `/api/chats`, `/api/chats/<id>`, `/api/chats/save|rename|delete`, `/api/keys`,
`/api/keys/import|upload|delete|clear|load-file`, `/api/reset-keys`, `/api/claude/ask|tell|status|sessions|transcript` (headless
`claude -p` on the plan, the consent gate 409 kept), `/api/supervisor/propose|pending|get|recent|decide`, `/api/skills/list`,
`/api/training/correct|status|build` (status/build run build_dataset through a small Python helper), `/`, and the same security
guard (Origin / Referer / Sec-Fetch-Site / X-Queen-Token).
- Key pool = port of groq_pool (same `keys.txt`, `.env`, `key_state.json`, sha256[:12] ids; 401/403 = every model 30 days,
  else this model for Retry-After, min 5 s, default 60 s; failover only before the first token). The ledger = port of
  record_spend on `spend_ledger.json`, and the Cost Agent hears every paid call (`POST /spent`).
- The system prompt is built exactly like `build_queen_system_prompt()`: the bundled helper `gen_prompt.py` reads the installed
  `~/.groq/qwen_app/app.py` with ast (again whenever it changes); every `queen_skills/*.md` is added every turn. CI compares the
  Swift prompt to Python's byte for byte.
- `/api/chat` in Swift asks the backend for the two parts that stay Python in Phase A: the local chat commands
  (`POST /api/internal/local_command`, matched before Groq is called) and the after-turn work (`POST /api/internal/after_turn`:
  training log, her command lines run, handover). Backend down = no local commands, Groq still answers.

**Proxied to 8766, unchanged and streamed:** every other route (brain, router, vision, screen, ax, whatsapp, affinity, gemini,
posters, star, voice, elevate, repo, github, news, handover, data-sync, self_update, auto_update, key_tester, system, test/live,
a multipart key upload). The backend's `/api/events` are relayed into the Swift `/api/events`.

**Install on the Mac (morning, in this order):**
1. `cd ~/Developer/groq_ai_studio && git pull --ff-only && ./install.sh` (the Python side: new `qwen` launcher, internal routes).
2. `mac_app/install.sh v5`. It does: `gh release download v5 --repo markoboskoauroville/groq_ai_studio --pattern app.zip`,
   quits the old app (`osascript -e 'tell application "Groq/Queen AI Studio (Mantra)" to quit'`), unpacks into /Applications,
   signs `codesign --force -s "Mantra Apps"` (axread, then the app).
3. `open "/Applications/Groq Queen AI Studio (Mantra).app"`. If an old Python Queen still runs on 8765, the app stops her itself.
4. `curl -s 127.0.0.1:8765/api/app/status` shows `"face": "swift"` and `"backend": {"up": true, "port": 8766}`.

**Morning tests for Marko:**
1. `queen "hello"`: an answer (Swift `/api/chat`).
2. A skill question: `queen "how do you read my WhatsApp without a screenshot?"` (skill whatsapp-accessibility in the prompt).
3. `curl -s -X POST 127.0.0.1:8765/api/claude/ask -H 'Content-Type: application/json' -d '{"question":"say hi"}'` (local Claude).
4. macro_router as usual (it calls `/api/brain/plan`, proxied), or
   `curl -s -X POST 127.0.0.1:8765/api/brain/plan -H 'Content-Type: application/json' -d '{"goal":"open Notes","catalogue":{"actions":[{"name":"open_app"}]}}'`.
5. The Swift window: type "hello", then "list sessions" (a local command through the backend).
6. Failover: `curl -s -X POST 127.0.0.1:8765/api/remote/send -H 'Content-Type: application/json' -d '{"prompt":"hi","fresh":true,"test_bad_key":true}'`
   gives `"failovers": 1`.

**Next (Phase B, by hand group; each one leaves the proxy when its Swift port is green):** affinity, ax/whatsapp, screen/vision,
gemini/CDP, skills posters, elevate, star, voice, system, repo/github, news/handover/data-sync, self_update, auto_update; then the
local chat commands and after-turn (they are Python today), then Phase C deletes Flask. Details in `docs/PHASE_A_REPORT.md`.


**14.11.2026, Mac: the Swift app and Accessibility.** Marko: "now it is time to convert our Grok AI Studio into a Swift app ... upgrade it
with new skills for accessibility ... check my last 5 WhatsApp messages ... who sent them and what was not responded to. Without taking
screenshots". (1) **Groq/Queen AI Studio (Mantra)**, `mac_app/` (SwiftUI, no web view): the face of this server (status line from the new cheap
`GET /api/app/status`, chat over `/api/chat` streamed, chats from `/api/chats`, CHATS / NEW CHAT, SEND|STOP, top row ON OFF TOP PERMISSIONS ✕,
updater at start, `let VERSION` in mac_app/app/App.swift). Down at start: the app runs `~/.groq/qwen` detached (QWEN_NO_BROWSER=1, no
CLAUDE* vars); OFF stops only a Queen it started. Compiled ONLY by GitHub: `.github/workflows/mac-app.yml` (paths mac_app/**), release vN
Latest in THIS repo (tags vN are the Mac app's, not version.json's). Install: `mac_app/install.sh [vN]` (gh release download, /Applications,
"Mantra Apps", link ~/.local/bin/axread). Bundle community.auroville.groqaistudio. (2) **axread** (mac_app/axread/main.swift, in the app
bundle): the AX tree of any app as JSON (`--app --window --depth --max --timeout --roles --frames --focused --text --query`, `--apps`,
`--trusted`); sets AXManualAccessibility/AXEnhancedUserInterface so Firefox shows its page. (3) `qwen_app/ax_read.py`: `POST /api/ax/read`,
chat `ax read <App> [for <words>]`; axread first, the same walk in Python (pyobjc, ApplicationServices loaded by hand) as fallback.
(4) `qwen_app/whatsapp_ax.py`: `POST /api/whatsapp/ax/latest {n}`, chat "check my last 5 WhatsApp messages" / "who did I not answer on
WhatsApp" / "provjeri zadnjih 3 poruke na whatsappu" (first in the local chain, Mac only): Firefox's AX table "Chat list" -> name, time,
sender, unread, answered; sorted by time, group events left out. No screenshot, no click, nothing typed; the WhatsApp tab is only opened
or selected over BiDi (9223) when the tree lacks it, and the front app is given back. Skills `queen_skills/accessibility.md`,
`queen_skills/whatsapp-accessibility.md`. Permission: Accessibility belongs to whoever started Queen (iTerm2 now; the app when it starts
her: its PERMISSIONS word). The private repo GROQ_AI_STUDIO_MAC was made first and could not build (private = billing block); the app
lives here instead.

**14.11.2026 (later), VM: WhatsApp Business on Pixel 2 is THE WhatsApp machine.** Marko: "it's better to open the WhatsApp Business inside the Android emulator, then inside the Firefox browser". The supervised route runs on ~/Developer/claude-code/tools/wa_android.py (chats, unread, open, read, draft never sent, clear) when Pixel 2 is linked, Firefox wa_remote only as the fallback (`machine` in the answer); calls (call/answer/hangup) run on the door. Skill queen_skills/whatsapp-android.md.

**14.11.2026, VM: the WhatsApp door.** `POST /api/whatsapp/supervised {text, conv}` (qwen_app/whatsapp_supervised.py): Queen plans one action (her lessons, her rules, else her Groq model), the VM's local Claude Code (sonnet, 90 s) assesses {verdict, plan, why, lesson}, the plan runs through wa_remote (new `read`), a correction's lesson is appended to queen_skills/whatsapp-lessons.md and pushed from the VM. Claude unreachable = nothing runs. The phone app WhatsApp Remote Viewer (Mantra) reaches it through WHATSAPP_REMOTE_VIEWER/vm/wa_door.py (100.102.86.30:8879, systemd --user wa-door). Calls are not possible yet (WhatsApp server flag enable_web_calling off for the account). Skill queen_skills/whatsapp-supervised.md.

**14.11.2026, VM:** the WhatsApp machine: Queen opens the VM's Firefox with remote control and WhatsApp (`open whatsapp`), reports linked/QR, and runs WhatsApp requests (`whatsapp: ...`) through wa_remote, drafts unsent. Skill queen_skills/whatsapp-machine.md, code qwen_app/whatsapp_machine.py. Waiting: Marko scans the QR code.

## 13.11.2026: the second location, Queen on the VM chromium-vm (MANTRA_MANIFEST modules/two-locations.md)
Marko: "Queen must be in the virtual machine ... any lessons or skills are written in the same repository ... we are in two locations."
- VM (`ssh ubuntu@chromium-vm`, Ubuntu aarch64): `git clone` of this repo in ~/Developer/groq_ai_studio, `./install.sh` into ~/.groq (venv, the same files),
  **`queen.service`** (systemd --user, linger on) = `~/.groq/venv/bin/python ~/.groq/qwen_app/app.py 8765`, 127.0.0.1:8765, `QUEEN_LOCATION=vm`,
  `QWEN_NO_BROWSER=1`, DISPLAY=:1. `queen "<q>"` (copy of the hub's tools/queen) in ~/.local/bin; PATH set at the top of ~/.bashrc so ssh finds it.
- Key: only ~/.groq/keys.txt, copied once by scp (chmod 600, never printed or committed). Local Claude: the VM's own ~/.local/bin/claude (plan login):
  `queen "ask claude: ..."` answers `[Queen · local · $0]`.
- What changed for Linux: requirements.txt (Quartz only `sys_platform == "darwin"`); screen_look.py (`import`/`wmctrl`/`convert` on Linux, tested:
  she read the VM's screen); claude_link.sessions() is empty without the hub; the identity line says where she runs (`_where_i_run`, QUEEN_LOCATION);
  data_sync.py mirrors only when QUEEN_LOCATION is "mac" (the VM must never overwrite the Mac's data repo with its own state).
  Mac-only hands stay Mac-only (rename/install/Star/Affinity skills would fail on the VM): a skill says "Mac only" in its first line.
- Sync: `two_locations_sync.sh`, pull-only (`--ff-only`) of groq_ai_studio, MANTRA_MACRO, MACRO_SKILLS, MANTRA_MANIFEST every 5 min; Mac LaunchAgent
  community.auroville.twolocationssync, VM two-locations-sync.timer. New queen_skills are copied (newer only) to ~/.groq/queen_skills; new Queen code is
  reinstalled+restarted on the VM and only reported on the Mac. Conflicts: ~/.cache/two-locations/conflicts.log.
- Proven: skill `queen_skills/two-locations.md` written and pushed on the VM, copied into the Mac's ~/.groq/queen_skills by the Mac sync.

## 13.11.2026: Queen reads the screen (`qwen_app/screen_look.py`, skill `queen_skills/read-screen.md`)
Marko: "don't ask me if I see something ... teach the queen to learn to read screens and ask her if there's a subtitle on the screen."
`POST /api/screen/look {question, display?: 1|2|"all", region?, window?}`: silent `screencapture -x` (-D / -R / -l of the biggest window of an
app via CGWindowList), sips downscale (1800 px), blank guard (PNG under 12 KB = capture failure, she is not asked), then /api/vision/ask with an
"only what is visible, quote exactly, else 'not visible'" guard. Chat command (local, $0): "is there a subtitle on the screen?", "look at the
MacBook screen: ...". Subtitle questions crop to the band [0,700,2560,160] and carry the subtitle definition. Screenshots: ~/.groq/work/screen_*.png.
Tested against the Voice Engine truth (GET :8837/speaking), see LESSONS.md.

## 13.11.2026: her outputs and Claude's corrections become training data
Marko: "Qwen's output and its corrections by the Opus model are recorded in a GitHub repository ... prepare a dataset for
periodic fine-tuning ... data storage, versioning, and triggering the training process." `training_log.py` records every
answer of hers (an "output" with a turn id), every approve/reject of her steps with its note ("verdict", linked to the turn
through the task and the proposal), and every better answer Claude writes (`queen correct <turn|last> "<better>" ["why"]`):
~/.groq/training/events/<date>.jsonl, mirrored to the private groq_ai_studio_data (training/). `build_dataset.py` makes
datasets/v<N>/ (sft, train/valid, dpo, lessons, manifest with sha256), tagged dataset-v<N>; the trigger builds the next
version after 25 new examples and writes jobs/v<N>.md (MLX LoRA on a local Qwen); the run waits for Marko (download, hours).
Queen's Groq model itself is not fine-tuned. `queen training [build]` shows the state. test_training.py gates install.sh.

## 13.11.2026: Queen does everything, Claude Code teaches (MANTRA_MANIFEST modules/claude-teaches-only.md)
Marko: "You stop doing anything physically in this computer ... Mantra, Macro, and Queen are doing everything ... You are the
master teacher." New hands, all chat commands, all supervised (`queen pending / show / approve / reject`):
- `rename_skill.py`: `open app` / `quit app` (Star API), `rename app "<old>" to "<new>" in <REPO>` (every letter case and file-name
  form, web addresses only by an owner/repo rename, Marko's quotes kept, version +1, push, build watched),
  `rename repo`, `install latest <REPO> [replacing "<old>"]` (Mac zip -> /Applications + "Mantra Apps" + star rows; Android APK ->
  every adb device, the Pixel 7 emulator started when none). Names are hints ranked by probability; close ones come back as a top 5.
  Tasks on one repository queue in the order written; a red build or a reject stops the rest.
- `publish_skill.py`: `make repo public <REPO>`: the three secret checks, history rewrite of personal addresses (approved), public,
  build again. A billing message means "private repo": never sent to Marko.
- Her own answer is her hand: a command line she writes is run, its result appended (placeholders and quoted lines skipped).
- `news.py`: every step is a line in ~/.groq/HANDOVER.md; the news line next to the model name summarizes it (max 4 sentences:
  now, next, done). Zoom +/- moved into the tab line next to Settings.
- `data_sync.py`: chats, approvals, handover, skills, ledgers + TAKEOVER/LESSONS/skills mirrored every minute to the PRIVATE repo
  markoboskoauroville/groq_ai_studio_data (local is the truth: a deleted chat is deleted there; keys replaced by [KEY REMOVED]).
- `test_rename_skill.py`: every lesson as a test; install.sh refuses to install while one fails.
First job done this way: VM Machine Remote Viewer -> Mantra Remote Viewing (Mac v29) and Mantra Remote VNC -> Mantra Remote Viewing
(Android v44/v45, repo MANTRA_REMOTE_VIEWING), vm-chromium made public after the checks.


## THE RULE: teach Queen (Marko, 12.11.2026, enforced)

"Every time I ask you to do something through Queen, you need to teach her, you need to write a skill so next time if I
ask directly, she's able to do it without you." Nothing done through Queen is finished until she can do it alone:
a skill file in `queen_skills/<name>.md` (read into her system prompt every turn), the route or chat command it needs,
tested by asking her in her own chat, installed, restarted, pushed. Full rule: MANTRA_MANIFEST modules/teach-queen.md.
Repository: markoboskoauroville/groq_ai_studio (public, unpromoted: no README, no description; this file is the description).
Status 11.11.2026: version v4 runs on this Mac, port 8765, `/health` answers `{"app":"groq-modern-chat","version":"v4","ok":true}`.
Marko, 11.11.2026: "We are developing this app now." Nothing is compiled: it is Python and one HTML file, so there is no
GitHub Actions build; it runs from source.
Auto-update repo: `markoboskoauroville/groq-auto-update` (public). CI-validated updates push here automatically.

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
cooldowns, `t` run live visible self-test suite, `h` help.

## Files
| File | Job |
|---|---|
| `qwen_app/app.py` | the server: unified key pool (`groq_pool.py`), Dual-Kind API loader (`Groq` chat + `Google`/`Anthropic` auto-update), failover, local Origin/CSRF + `X-Queen-Token` security guard, streaming chat with exact Groq usage (`x_groq.usage`), ledger, GitHub reads, Star Menu & Startup proxy (`/api/star/*`), Voice Engine & Subtitles proxy (`/api/voice/*`), Elevate Media production endpoints (`/api/elevate/*`), backdoor, port finder, CI pipeline, chunked & surgical auto-update routes (`/api/auto_update/*`), chat persistence, version management |
| `qwen_app/brain.py` | **the brain of Macro Recorder** (12.11.2026): `/api/brain/plan` turns a goal plus the block catalogue into a chain of macro steps and refuses to invent an id; `/api/brain/teach` and `/api/brain/training` keep graded examples it reads as few-shot; `/api/brain/escalate` is the two-strikes rule - Queen admits the limit, asks Claude through the Anthropic API, logs the cost, and the returned rule becomes a lesson. Registered in `app.py` in a try/except so the studio still runs if it fails to load. |
| `qwen_app/auto_updater.py` | pre-briefed surgical auto-update engine: noise-tolerant multi-provider key parser (`gsk_`, `AIza` / `AQ.`, `sk-ant-`), `0600` `~/.groq/auto_update_keys.json` store, Google Gemini & Anthropic Claude SSE streaming clients (`max_tokens=16000`), `<queen_update>` surgical patcher + unified diff generator, `~/.groq` local sync, and exact USD cost ledger (`~/.groq/auto_update_ledger.json`) |
| `qwen_app/index.html` | the whole client: topbar Auto-Update Provider Switch (`Google` vs `Anthropic`) + Model Switch + `⚡ Update App` + `◫` Split Toggle, automatic 50/50 "Learning by Watching" Split-Screen Software Engineer Studio (6 educational stages, live model stream, colorized unified diff, USD cost receipt card), Dual-Kind API Code Section (`Groq` vs `Google`/`Anthropic`), sidebar with sessions & spend, Prose / Code Box toggle, live Stop button, `🔊 Speak` per message, modals for Star Menu (`⭐`), Voice Engine (`🔊`), Elevate Media (`🎬`), GitHub (`🐙`), billing, settings, chunk self-update |
| `version.json` | current version number (`v4`) and update history log |
| `groq_pool.py` | unified key pool module shared by BOTH `qwen_app/app.py` (`DynamicKeyPool`) and `groq-cli` (`KeyPool`): `extract_keys_from_noise`, sticky failover, cooldown persistence |
| `groq_cli.py`, `groq-cli`, `qwen`, `groq-chat` | the terminal clients and launchers |
| `install.sh` | copies the code into ~/.groq, makes the venv, installs `requirements.txt`; reads no key |
The app expects to live in `~/.groq` (it inserts that folder in `sys.path` and keeps its state there). The repo is the source;
`install.sh` puts it there.

## State on the Mac (never in git)
`~/.groq/keys.txt` (keys, 600), `.env`, `key_state.json` (current key and cooldowns), `spend_ledger.json` (totals and the last
100 requests), `active_port`, `app_url`, `incoming_update/` (self-update staging), `chats/` (server-side chat logs), `venv/`.
`.gitignore` blocks all of these.

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
`GET /` page, `/health`, `/api/version`, `/api/models`, `/api/billing`, `/api/keys`, `/api/events` (server-sent events), `/api/session/messages`,
`/favicon.ico` (the orange Groq "thunderstrike" on dark); `POST /api/chat`, `/api/keys/import`, `/api/keys/upload`, `/api/keys/delete`
(`id` or `index`), `/api/keys/clear`, `/api/reset-keys`, `/api/keys/load-file`, `/api/remote/send`
(`{"prompt","mode","model","system_prompt"}`: a program types into the page; the open page sees it live over `/api/events` and the
reply and telemetry come back in the response), `/api/chats/*` (server-side chat persistence + auto-title + rename + delete),
`/api/self_update/*` (CI-gated chunked self-update + backup + git push to both repos),
`GET /api/star/startup` & `POST /api/star/action` (Star Menu & Startup 55-app control via `STAR_API` `:8863`),
`GET /api/voice/speaking`, `GET /api/voice/voices`, `POST /api/voice/speak`, `/api/voice/pause`, `/api/voice/stop`, `/api/voice/hear` (Local Voice Engine & on-screen subtitles via `MANTRA_VOICE` `:8837`),
`GET /api/elevate/board`, `GET /api/elevate/whatsapp`, `POST /api/elevate/whatsapp/draft`, `GET /api/elevate/drive-comments`, `POST /api/elevate/fetch-image`, `POST /api/elevate/gemini-chrome`, `GET /api/elevate/gemini-status`, `POST /api/elevate/resolve` (Elevate Media end-to-end production workflow),
`GET/POST /api/test/live` (runs 16 live self-tests and prints colorized progress to Queen's terminal window), `POST /api/terminal/log` (prints live commands/banners to Queen's terminal console),
`GET/POST /api/auto_update/config`, `GET /api/auto_update/models`, `POST /api/auto_update/keys/import`, `POST /api/auto_update/keys/load-default`, `POST /api/auto_update/keys/delete`, `GET /api/auto_update/status`, `GET /api/auto_update/ledger`, `POST /api/auto_update/run` (Dual-Kind Google/Anthropic surgical auto-update pipeline + automatic 50/50 split-screen SSE stream + USD cost receipt), `/api/github/*`.

All `/api/*` routes are protected by `local_api_security_guard` (rejects cross-origin `Origin` / `Referer` / `Sec-Fetch-Site: cross-site` with HTTP 403; accepts `X-Queen-Token` from `~/.groq/api_token` and local `curl` / `127.0.0.1` UI calls).

## What has been checked, and what has not
Checked 11.11.2026: the server is up and healthy, the keys file holds keys, the code was read through, and a three turn casual
chat through `POST /api/remote/send` worked on the first key (about 0.5 s a reply, $0.0022 a turn; the 2,600 tokens shown per turn look
inflated, probably the reasoning, see LESSONS). NOT checked by this
session: a real answer from every model, failover with a truly exhausted key, the GitHub panel, drag and drop, the stress test
`stress_test_09.py` (lives in ~/.gemini/antigravity/brain/.../scratch, not in this repo), the page on a small window.

## Dangers, named plainly
- Cross-origin browser CSRF is now blocked by `local_api_security_guard` (`Origin`/`Referer`/`Sec-Fetch-Site` check + `~/.groq/api_token` via `X-Queen-Token`). Same-machine processes running as Marko can still call `127.0.0.1:8765`.
- `run_gh` gives the page read access to every repo `gh` can see.
- Key pool failover is now unified in `groq_pool.py` (`DynamicKeyPool` + `KeyPool`).
- `MODEL_PRICING` covers the full Groq model catalog and merges any live pricing metadata returned by Groq `/models`; streaming usage now reads `chunk.x_groq.usage` so token counts match Groq's invoice.
- `launch_server` in the old installer runs `lsof -ti:PORT | xargs kill -9`, which kills whatever holds the port.

## Where it fits
Marko's Groq model research (Groq has no image model, models researched for TTT) and scribe's Groq transcription use the same
Groq keys (numbered keys in ~/Downloads/API/groq-api.txt). KeyringTester checks that these keys work and has read the image with
`qwen/qwen3.8-27b` (14.10.2026). Work on this app: edit here in ~/Developer/groq_ai_studio, run `./install.sh`, restart `qwen`.
Skills (registered in `.agents/skills.json`): `skills/groq-ai-studio/SKILL.md`, `skills/groq-ai-studio-testing/SKILL.md` (visible macOS Terminal runner: `skills/groq-ai-studio-testing/scripts/run_visible_tests.sh`), `skills/queen-auto-update-pipeline/SKILL.md` (Dual-Kind API Loader + Surgical Auto-Update Pipeline + Split-Screen UI blueprint), `skills/star-menu-computer-control/SKILL.md`, and `skills/elevate-media-production/SKILL.md`.

## Affinity (12.11.2026)

`qwen_app/affinity_bridge.py` gives Queen the Canva app: `/api/affinity/status`, `/actions?q=`, `/api?q=`,
`POST /do {action,args}`, `POST /js {script}`, `POST /render {path|selection|spread}`. It owns no logic of
its own - the client and the action database live in `~/Developer/MACRO_SKILLS` (`tools/affinity.py`,
`affinity/actions.json`, `affinity/api_index.json`) so Queen and the Macro Recorder fire the same rows.
The client is loaded **by path**: the bridge was first called `affinity.py` and `import affinity` found
itself (AttributeError: no attribute affinity_pid). Affinity's own MCP server must be switched on in its
Settings and the app restarted; the port is read from the process, never hard-coded. Skill: `affinity`.

`POST /api/affinity/open` and `/close` (12.11.2026): open says "Affinity is already open." when it is and
cancels the start-up pop-ups (Update Studios, the Welcome window); close never forces. A chat line that only
asks to open or close Affinity is answered by `chat_app_command()` in the bridge before the model is called:
model "local", cost 0. The bridge caches the client module, so Queen is restarted after a change to
`MACRO_SKILLS/tools/affinity.py`.

## Repo reader (12.11.2026): read and search any repository, never write

Marko: "teach Queen how to go to the repository and read all the files from there, not writing, only reading and
searching for information." `qwen_app/repo_reader.py`: a repository is mirrored once into `~/.groq/repo_cache/<owner>/<name>`
(shallow clone through Marko's own `gh` login, so private repos work), refreshed by a fast-forward pull when older than
10 minutes, then read and searched locally. Routes, all GET: `/api/repo/list | status | sync | tree | read | search`
(`search` takes `regex`, `case`, `context`, `path`, `limit`; `repo=all` searches every cached repo; `read` takes a line
range and cuts at 200 KB with a "read again with start=N" hint). Nothing writes to GitHub: POST answers 405.
Guards: path escapes and `.git` refused; `.env`, keys, certificates and files named secret/token/credential
are never read or listed in search hits; repos over 400 MB need `big=1`. Chat, answered locally at cost 0:
`tree R [under P]`, `read R:path [lines A-B]`, `search R for text`, `sync R`. Default branch only.
The older 🐙 panel (`/api/github/*`) stays for attaching one file to a chat.

## Queen <-> local Claude Code, local first (12.11.2026)

Marko: "If there is a local connection with you, Claude Code, that's the priority. If it's missing, she's asking, 'I cannot
reach the local Claude Code. Do you want to use API credits?'" `qwen_app/claude_link.py`: `GET /api/claude/status | sessions |
transcript?sid=`, `POST /api/claude/ask {question}` (headless `claude -p` on the claude.ai plan, ANTHROPIC_API_KEY and the
parent session's CLAUDE* variables removed, Bash disallowed for plain questions, a note so it answers only),
`POST /api/claude/tell {sid,text}` (types into a live session's tab). Chat: `ask claude <q>`, `list sessions`.
The gate `claude_link.route(allow_api)` guards every paid path: `/api/brain/escalate` and `/api/auto_update/run` go to the
local Claude Code (the update runs headless in this repo with acceptEdits and a fixed tool list, no commit, no push);
unreachable -> 409 need_consent with Marko's sentence; `allow_api: true` only after his yes.
The other way: `queen "<question>"`, `queen skills`, `queen status` (hub tools/queen, on the PATH).
Queen must be started WITHOUT the CLAUDE* variables of a Claude session (env -u ...), see LESSONS.

## Queen's eyes and the band-poster skill (12.11.2026)

- `qwen_app/vision.py`: `POST /api/vision/ask {question, path | repo+file | url, json}` sends the picture as an image_url to her
  own Qwen 3.6 (Groq has no Llama-4/vision model on this account; Qwen reads images). Cost into her ledger (~$0.004 a look).
- `qwen_app/poster_skill.py`: `POST /api/skills/band-posters {profile, max, dry_run}`, chat "make posters for the next Santoshi
  concert". Next event from santoshi_band_site/events.json; every band photo checked by her eyes against the seven members
  described by look (`queen_skills/santoshi_band.json`, from the verified photo img/photos/6829.jpg); only real photographs
  with all seven; one Affinity document per photo (the photo's own proportions, width 1800), a 55% dark band where no faces
  are, the text centred and scaled to fit; tabs left open, NOTHING saved. Answers cached in ~/.groq/skill_cache.
  Source photos are copied to ~/Desktop/Queen poster photos (Affinity scripts read the Desktop only).
- Skills folder: `queen_skills/*.md` read into her system prompt every turn; `*.json` profiles beside them (installed by install.sh).

## Gemini, the project folder, saved posters, the image catalogue (12.11.2026, evening)

- `qwen_app/gemini_skill.py`, `POST /api/gemini/image {prompt, image, out}`: Gemini in Marko's Chrome over the DevTools port
  (DevToolsActivePort gives port and path; /json is closed in this Chrome, the browser WebSocket works). The account is read
  on the page; the reference is attached through a file input filled by DOM.setFileInputFiles and pasted into the prompt;
  the result is a clipped Page.captureScreenshot at the picture's real size. Profiles in order (Local State):
  auroville.community first, the band account last; exhausted, refused, timed out (3 min) -> next profile, window opened
  if needed; at most four per picture.
- Project folder: ~/Pictures/<YYYY-MM-DD> <project>/ keeps every photo, Gemini picture and poster (.af layered + .png).
  Affinity can only read/write the Desktop (PERMISSION_DENIED on ~/Pictures, also through a symlink), so it works in
  ~/Desktop/Queen Affinity work/<same name>/ and everything is copied into Pictures (`project_dirs`, `stage_file`,
  `save_poster` in poster_skill.py; `Document.saveAs(path.af)` + `export(path.png, PNG preset)`).
- `POST /api/skills/gemini-posters`: A4 full-bleed (Gemini's extension of the real photo) and three stripes (Gemini pink
  lights / band photo / member portraits), English and Croatian, four posters.
- `qwen_app/describe_skill.py`, `POST /api/skills/describe-images`: every image of a site repo described by her eyes into
  an Excel workbook in the project folder: Index tab + one tab per image named after the file (openpyxl, in Queen's Python).

## Supervised work, task chats, photos onto a website (12.11.2026, night)

- `qwen_app/supervisor.py`: Marko: "supervise her before each move ... so she doesn't mess up my website." A step that changes
  something outside Queen is a proposal in ~/.groq/approvals/ (`/api/supervisor/propose|pending|get|decide`); a Claude Code
  session decides with `queen pending`, `queen show <id>`, `queen approve <id> ["note"]`, `queen reject <id> "why"`.
  `propose_and_wait()` blocks the skill; a reject or 30 minutes of silence stops it (silence is never a yes). An approval note
  may carry corrections as JSON (the web-photo skill reads caption_en / caption_hr / alt from it).
- `qwen_app/task_chat.py`: Marko: "Open the new chat with the title of the task." Every supervised task opens its own chat in
  her window (event "task_chat", saved in ~/.groq/chats), and writes each step, proposal and decision there.
- `qwen_app/web_photo_skill.py`, `POST /api/skills/web-photo {source, repo}`: web copy (2400 px JPEG <= 450 KB), captions EN/HR
  from her eyes with the real capture time, PLAN -> CHANGE (exact diff) -> build check (auto undo) -> DEPLOY, each approved;
  then the live page is checked. First run: the panorama of 17.12.2025 into a new Photo gallery section of KUKLJICA_ECOOASIS.

## Tabs, live self-check (12.11.2026, night)

- The page is in tabs (Marko: "each task in a different tab ... the real estate of the application is used"): Chat, Tasks
  (approvals with Approve/Reject for Marko too, task chats), Auto-update (the engineer studio, full width), Tools (Star,
  Voice, Elevate, GitHub), Skills (queen_skills), Spend, Settings (settings, keys, persona, chunk self-update). A badge on
  Tasks counts the proposals waiting. The block "QUEEN TABS" at the end of index.html; the old code is unchanged.
- Easter egg: the ⚡ next to "Groq Studio" toggles full screen.
- `qwen_app/live_check.py`, `POST /api/selfcheck/image-live`: live page in a background tab, the image found, loaded,
  screenshotted and compared by her eyes with what she made; used by the web-photo skill at the end.

## 14.11.2026: Mac output volume (system_volume.py)
`GET/POST /api/system/volume` ({percent 0-100 | change +-N | mute bool}; osascript set, then read back; device only named, never changed) and a local
chat command (first in the local chain, darwin only, $0): "reduce the output volume to 10%", "volume 30", "mute", "how loud is it", Croatian "stisaj".
Skill `queen_skills/system-volume.md`. Tested in her chat: volume read back 10, ADAM Audio D3V still default.

**14.11.2026, v4: the icon.** Marko: "please give Groq queen icon, as we always have icons". Default look for an unpromoted app (six-letter-icon.md): black, GRO / QUE in white, a cursor arrow behind. Row `groqqueen` in STAR_SWIFT/icons6/icons.json (category Between Marko and Claude); the picture is `mac_app/icon/six_1024.png`; build.sh makes AppIcon.icns with sips + iconutil and sets CFBundleIconFile. Compiled only by GitHub (release v4).

**15.11.2026: camera, Second Take and phone voice phrases (Marko: "everything we are doing please teach the queen").** All $0, local chat commands:
- `qwen_app/sony_camera.py`: "refresh the camera" / "reconnect the camera" = `sonycam connect` then `sonycam status`; "imaging edge big" / "camera full screen" / "show me on the BenQ" = `sonycam big` (Remote maximized on the BenQ, v27); "camera status" = `sonycam status`. Skill `queen_skills/sony-camera.md`.
- `qwen_app/second_take.py`: short phrases while Second Take runs: "record", "keep", "again" (POST /shoot/action), "stop" (existing branch), "watch shot N" (POST /shoot/action watch). Refused while recording. Skill `queen_skills/second-take.md`.
- `qwen_app/phone_say.py` (new, wired in app.py before system_settings): "say on the pixel <text>" / "speak on the pixel <text>" / "send to the pixel <text>" = `phonesay pixel en "<text>"`; "phone status" = `phonesay status`. Skill `queen_skills/phone-voice.md` (new).
- Tested in her chat through `/api/internal/local_command`: "camera status" (connected, STBY), "second take status" (v27, not recording), "phone status" (both phones answer). Routing of the rest checked with the hands mocked.
- Test slip: "watch shot 3" was sent for real and played shot 3's source clips; ended with "stop second take" (no camera recording).
- Queen's backend on 8766 was restarted by hand (env cleaned of Claude session variables). Her model answers through `/api/remote/send` do not run local commands: use `/api/internal/local_command` to test phrases at $0.
