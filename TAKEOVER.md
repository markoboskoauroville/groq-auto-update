## v17 (18.11.2026): chats, provider radios, rename

Marko's words are in momentaryupdates.md (two entries, 18.11.2026). CAPI tab: "conversation" is "chat" everywhere visible; the list sorts by `created` (newest first, id tie-break): the old sort by `updated` made a new chat sink under any chat that was answering. PROVIDER radios (Anthropic, Oxyy) in Capi.swift; server keeps the choice in ~/.groq/capi_provider.json, keys in ~/.groq/capi_key and capi_key_oxyy (0600). Oxyy = oxyy.ai gateway, Messages API at https://api.oxyy.ai, no balance endpoint (credit = starting balance typed by Marko minus ~/.cache/oxyy-ledger.jsonl, Claude cost x0.4). The oxyy key of 18.11.2026 had no Claude access (only deepseek-flash, Atria-Dawn-Preview, eleven_flash_v2, OpenAI-format only, and all returned 403/404/503 "temporarily unavailable" when tried): a chat on Oxyy shows the service's error until the key gets Claude. RENAME + AUTOMATIC NAME (Haiku, /api/capi/rename, /autoname). Compiled only by the mac-app workflow.

## TRIPLE CHAT — in progress (17.11.2026)

Marko, 17.11.2026 (word for word): "Please upgrade my app and don't test it. Just write the code and I'm going to test it myself manually. It's about Queen. I want to have triple chat. And triple chat means there is me in the chat room, there is Claude over API, and there is Groq Queen, our model over API. And in this trio chat box we all can hear each other and comment on each other thoughts. I can ask for example, Queen what do you think about this and she answers. Then I can ask Claude what do you think about this and he answers. And the whole chat history is there and available for everybody. So this is like a pool of three brains where we together discuss and then also we can write the skills, we can also access the GitHub, we can use my computer, so all the skills which Queen already has, she can apply them and also can ask advice. I can for example say, Queen, please ask Claude how to do things and then he explains and she understands. So in this kind of thing, make me triple chat UI, please."
Then: "Before building anything, please write in the takeover of this application what needs to be done. First, write a takeover and then start to build. Because my credits are only 1% and I don't want to lose my prompt, etc. So, takeover needs to be written after every step and right now."

**UPDATE 17.11.2026 (Marko, word for word): "don't limit me to 8$, just on it, test everything until it works".** This REPLACES the earlier "don't test it": test for real until it works (see TEST phase below); the $8 cap is lifted.

**Decisions (the first line about NO testing is superseded by the update above).** NO testing by Claude (Marko tests by hand): only py_compile / CI. Claude's side: local Claude Code first
(`claude_link.ask`, plan, $0); switch per room "Claude via: LOCAL (plan) / API (credits)", default local; local unreachable =
"I cannot reach the local Claude Code. Do you want to use API credits?" and wait (a YES button switches the room to API).
API: key from the auto-update store (`load_auto_update_store()["keys"]["anthropic"]`, never printed), model picker
claude-haiku-5-5 / claude-sonnet-5-5 (default) / claude-opus-5-5 / claude-fable-5-2, each call into `record_spend`.
Queen-asks-Claude: a line `ASK CLAUDE: <question>` in Queen's answer -> Claude answers in the room -> Queen continues; cap 3
exchanges per turn. Claude's `ASK QUEEN:` lines only run when Marko presses on (ASK QUEEN). Claude advises, Queen executes
(her local commands + after-turn command lines run as in her normal chat).
Architecture: the window is the SwiftUI app (mac_app/, compiled ONLY by GitHub mac-app.yml); `/` serves no page. Backend =
Python on 8766; Swift proxies every unknown route there, streamed. So the room lives in Python (`/api/triple/*`, works on the VM
too) and the Swift window gets a TRIPLE mode.

**Plan (tick each, commit+push after each):**
1. [x] Request saved in momentaryupdates.md + this section.
2. [x] `qwen_app/triple_chat.py`: store `~/.groq/triple/<id>.json` {id,title,claude_via,claude_model,last_addressed,messages:[{speaker:marko|queen|claude,text,ts}]};
   routes GET /api/triple/list, GET /api/triple/get?id=, POST /api/triple/new, POST /api/triple/settings {id,claude_via,claude_model},
   POST /api/triple/turn {id,text,to:queen|claude|both|auto} -> NDJSON lines {"speaker":..,"start":1} / {"t":tok} /
   {"need_consent":msg} / {"done":1}. Addressing parser (Queen/Qwen/Quinn, Claude/Cloud/Klod; default last addressed).
   Done = py_compile passes.
3. [x] Register in `qwen_app/app.py` (try/except like brain; pass pool, build_queen_system_prompt, record_spend,
   _local_command_answer, _after_turn, DEFAULT_MODEL, MAX_OUTPUT_TOKENS); install.sh copies it.
4. [x] Swift window (written, awaiting the mac-app run colour): `mac_app/app/Triple.swift` (model + view); App.swift: word TRIPLE in the status line switches the
   conversation to the room; ASK QUEEN / ASK CLAUDE / ASK BOTH, CLAUDE VIA LOCAL|API + model picker, rooms; VERSION 9.
   Done = pushed, mac-app run green, release v9 Latest.
5. [x] `queen_skills/triple-chat.md`.
6. [x] version.json 9, LESSONS.md, skill groq-ai-studio section, ~/Downloads/API PROJECTS.md line; ./install.sh;
   `mac_app/install.sh v9`; Queen restarted.

**Where we are (17.11.2026, TESTED, v10 Latest):** all steps done and tested, see TEST RESULTS below. Older note: ALL STEPS DONE, mac-app run green, release v9 Latest, ./install.sh done; Marko tests by hand. Earlier: steps 1-4 written (Triple.swift, App.swift VERSION 9, Queen.request/json made internal, triple_chat.py got a `resume` flag for the YES-to-API button); need the mac-app run to be green, then 5 skill, 6 release/install. Earlier: steps 1-3 done (registered lazily in app.py; install.sh already copies *.py, run ./install.sh at the end of step 3 below). Earlier: steps 1-2 done (triple_chat.py written, py_compile ok, `register(app, pool, build_queen_system_prompt, record_spend, local_command_answer, after_turn, default_model, max_tokens)`). Left: 3 register + install.sh, 4 Swift, 5 skill, 6 release. Trap: Claude models have no rate in get_model_rates, so record_spend books them at its fallback rate (cost approximate).

**Hand-over (17.11.2026, plan at 1%):** Marko: "And since we are losing the credits soon, only 1%, please give a task to Queen and
API through our Queen API of Claude to finish updating the app. So they need to do, you just need to save this 1% as much as possible."
The build runs OFF the plan on the API credit (headless Claude Code, Sonnet 5.5, budget cap $8), brief `docs/TRIPLE_CHAT_BRIEF.md`:
`cd ~/Developer/groq_ai_studio && CLAUDE_API_MODEL=claude-sonnet-5-5 CLAUDE_API_BUDGET=8 nohup claude-api-mode run "$(cat docs/TRIPLE_CHAT_BRIEF.md)" > ~/.cache/triple-chat-build.log 2>&1 < /dev/null &`
Progress: the ticks above (`git pull`), `git log --oneline -5`, `tail ~/.cache/triple-chat-build.log` (its report and
`[claude-api-mode] cost $` appear only at the end), spend `claude-api-mode status` / ~/.cache/claude-api-ledger.jsonl.
Resume: run the same command again; the builder starts at the first unticked step.



## TRIPLE CHAT — TEST RESULTS (17.11.2026, real calls on 127.0.0.1:8765, v10)

| Test | Result |
|---|---|
| Marko -> Queen (live Groq) | PASS (bug found: `<think>` text streamed live; fixed, hidden now) |
| Marko -> Claude (local Claude Code, plan) | PASS |
| Ask both: Claude's answer mentions Queen's colour (sees her answer) | PASS |
| "Queen, please ask Claude ..." chain, Claude answers, Queen repeats | PASS (bug: names of both = both answered; fixed: leading name wins, "Queen and Claude" = both) |
| Addressing Qwen / Quinn / Cloud / no name = last addressed | PASS |
| Cap of 3 ASK CLAUDE exchanges per turn | PASS offline (test_triple_chat.py, deterministic); live run hit Groq 503 "over capacity" once, Queen's own refusal to loop was also seen |
| Transcript persisted, read back by GET /get, and shown again by the window after restart | PASS |
| Claude switch LOCAL -> API (claude-haiku-5-5, real Anthropic call, spend booked) | PASS |
| Local Claude unreachable -> consent text, YES resume does not duplicate the message | PASS offline (stubbed status) |
| ASK QUEEN button path | PASS offline |
| GitHub mac-app run, v10 release Latest | PASS (green, release Latest) |
| Window at 560 pt, TRIPLE mode screenshot | PASS (bug: "keys 1" broke across lines; fixed in v10, re-captured, aligned, nothing cut) |
| install.sh gate (all tests incl. new test_triple_chat.py), Queen restarted | PASS |

**Could not be tested:** the real unreachable-local-Claude case (only stubbed; I did not log Claude Code out); the live cap with a
model that really loops (Groq 503 and Queen declines to loop); YES-to-API button click in the window (route tested, not the click);
Fable/Opus models on the API (only Haiku called, to keep it cheap); Queen executing real command lines inside the room;
the VM copy of the backend; touch/trackpad feel. Cleanup: test room deleted, testclean run, window left at 560 pt.


## TRIPLE CHAT — "The room answered 404" (17.11.2026, fixed server-side, no Swift change)

**Cause:** the Swift window sends every message to `POST /api/triple/turn` with the room id it holds. The server returned 404 "no such room" because that room file in `~/.groq/triple/` was gone (`~/.groq/triple` was empty: the test room was deleted during test cleanup while Marko's window still held its id). Un-addressed messages were not the problem (they default to the last addressed speaker, Queen).
**Fix:** `triple_chat.recover_room(id)`; `/api/triple/turn` and `/api/triple/settings` now recreate a missing room empty under the same id instead of 404 (only an empty id still 404s), so the window carries on and its reload finds the room. Proof: turn on a never-created id returns 200, Queen/Claude stream answers, room then listed. `/api/triple/get` still 404s for unknown ids (read only). Not changed: Swift v10 (a Swift fallback to NEW ROOM on 404 would be nice, left for a later version).


## TRIPLE CHAT — TEST ROUND 2 (17.11.2026, API builder, real Queen v10)

| Test | Result | Fix commit |
|---|---|---|
| Real window (screencapture -l): TRIPLE mode, one grid, nothing cut, speakers coloured, ASK QUEEN / CLAUDE / BOTH visible | PASS | none needed |
| Marko -> Queen | PASS after retry (Groq 503 "over capacity" gave an ERR line) | triple_chat: Queen retries 503/429 up to 3x with backoff |
| Marko -> Claude local | PASS | |
| "Quinn, ask Cloud ..." chain (name addressing + ASK CLAUDE) | PASS | |
| Ask both (Queen blue, Claude green) | PASS | |
| Claude via API Sonnet 5.5 and Opus 5.5 (real calls) | PASS | |
| Known flaw: Claude prices | FIXED: Sonnet 522 in / 5 out booked $0.001094 (= $2/$10 per 1M) | app.py MODEL_PRICING |

**Not tested in round 2:** the real unreachable-local-Claude case (a backend with PATH stripped still found `claude`, so the consent path stays offline-tested only); the YES button click in the window (route only); the window driven by AX presses (the window already showed another room, so I tested the same routes by HTTP in my own room and only looked at the window); the live cap loop; restart-and-history in the window; a Queen skill + GitHub read inside the room; Fable on the API. No Swift change, so no new release. Test rooms deleted.

## TRIPLE CHAT — VISIBLE DEMO (17.11.2026, Sonnet headless, Macro Recorder as the only hand, Queen as judge)
Driver: `tools/triple_demo.py` (front, click, type, shot, ocr; checks the front app is GroqAIStudio before every key). Pictures: `docs/triple-demo/`.
| Step | What he saw | Queen's verdict | Fix |
|---|---|---|---|
| Ask Queen (name for a meditation app) | typed slowly; Queen's 4 names, ASK CLAUDE, Claude picks Still, Queen's final pick | right (she would rather leave the decision to Marko) | none |
| Claude via Local, own question | Claude answers: signing key first | right | none |
| Ask Both (tagline) | Queen, then Claude, in order | right | none |
| "Queen, please ask Claude how to write a skill for renaming files" | Queen asked Claude; Claude showed "..." for 5+ min (local Claude Code logged in but not answering, even a one-word Haiku call) | the one bug left: silence too long | claude_link.ask: timeout means unreachable for 5 min (NeedConsent); room waits 75 s, then "I cannot reach the local Claude Code. Do you want to use API credits?" |
| YES, USE API CREDITS (real click) | room switched to API, Claude answered in 5 lines | right | none |
| Scroll up/down, narrow to 560, wide, close and reopen | history kept; at 560 the status line wraps to two lines (nothing cut) | right | none |
| Local / Api switch | Local by click works; my click on API missed once (ax-press Api works) | right | none |
Not done: no `macroskill add` entry (the driver is a Python script, not a stored macro); Queen judged per batch of steps, not before each one; the Claude model buttons were hit by one stray click (Sonnet now). Marko's dictation at 14:59 (about the voice engine Mantra UI) landed in the Queen field; cleared there, full text in ~/Library/Logs/voice-to-text-mantra.log.


## CAPI TAB + SPEAKER ICON (17.11.2026, Sonnet headless)
Marko's request is in momentaryupdates.md. Plan (tick each, commit+push after each):
1. [x] One credit number: ledger ~/.cache/claude-api-ledger.jsonl, `capi` writes to it, claude-api-mode status and tools/credit_watch.py agree ($96.66 at 2026-11-17 13:50 minus later spend).
2. [x] Backend (tested: Haiku turn + follow-up remembered the word, ledger lines, speak render ok) qwen_app/capi_chat.py: /api/capi/* (rooms, model, cwd, run stream, stop, credit).
3. [x] Swift: CAPI mode (Capi.swift) beside TRIPLE, Markdown, tool lines, cost, Stop, model + folder pickers, "API ($NN.NN left)".
4. [x] Speaker icon on every response (one shared component), Speechify Beatrice, render-to-file, cache; /api/speak/*.
5. [x] queen_skills/capi.md; install; release via GitHub Actions; tests; registry/HANDOVER/credit-watch.md.

**RESULTS (17.11.2026, real Queen v11 window, Haiku for CAPI runs, release v11 Latest, mac-app run green first try):**
| Test | Result |
|---|---|
| CAPI tab: question + follow-up in one room (session continues: remembered PELICAN) | PASS |
| Markdown: heading, table, numbered list, bold, inline code rendered; no raw ** or backticks | PASS (screenshots docs/capi-demo/) |
| Cost per answer, "API ($93.53 left)" at the top, ledger lines `capi-tab ...` written, credit moved 93.54 -> 93.53 | PASS |
| One credit number: `claude-api-mode status`, credit_watch and the tab all say $93.5x (tools/api_credit.py in claude-code); `capi` writes its cost to the ledger | PASS |
| Speaker icon: click renders mp3 (~/.groq/speak, Speechify Beatrice via langsay), plays (amber stop icon), click stops; 2nd click cached (no new file) | PASS |
| Window at 560 pt: aligned, nothing cut | PASS |
| Queen taught: skill capi.md, asked in her chat, answered right (POST /api/capi/ask) | PASS |
**Not tested:** Stop button mid-run; room switching/ROOMS list in the window; folder picker click; models other than Haiku; Croatian audio (route logic only); speaker in normal chat and TRIPLE (same Bubble, not clicked there); Queen actually starting a run through /api/capi/ask herself; Speechify cost (per character, cached = $0; spend ask not run). Mouse/keyboard via Macro Recorder did not register in this run (CAPI click, typing): I used macro ax-press and System Events keystrokes. Note: default folder claude-code makes Claude Code obey its CLAUDE.md and speak aloud via langsay during tests.
