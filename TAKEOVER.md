## v30 (19.11.2026): CAPI-first release candidate

The Swift status line now has only two top-level choices: CAPI first and AUTO UPDATE last. TRIPLE, CHATS, and NEW CHAT were removed from that line; CAPI retains its own saved-chat list and NEW CHAT control. The prior tab is remembered, with older saved modes opening CAPI by default.

The Auto Update tab wraps the existing `/api/auto_update/*` pipeline with a local chat history, provider/model selectors, progress polling, final reports, an explicit update confirmation, and separate paid-API consent when requested by the backend. Its current surgical-patch allowlist is backend-only (`qwen_app/app.py`, `qwen_app/index.html`, and `qwen_app/auto_updater.py`); Swift app source is built and released by the GitHub mac-app workflow. The full pipeline validates, bumps a version, publishes, and syncs local files; the local Claude route instead edits and reports without pushing.

CAPI now has a per-chat model-router switch. The cheapest model in the selected provider's catalog judges each prompt (including attachment names and MIME types, never file contents); the selected model, reason, and router cost are shown in the chat total and in the conversation. The router is off by default, is incompatible with pair mode, and reports errors instead of silently falling back. Google Cloud credit is explicitly labeled an estimate, not a live balance.

The Python API client is `tools/queen_capi.py`; capabilities are at `GET /api/capi/capabilities` and usage is documented in `CAPI_PYTHON_API.md`. CAPI folders can be selected with a directory picker and must be existing directories below the home directory. Gemini tool calls receive the prompt's file attachments in the selected folder; Google Cloud Gemini supports only the allowlisted audio/video MIME types, while Claude/Oxyy and pair mode reject media they cannot process.

Validation: all Python install-gate tests, the CAPI feature/API tests, Python compilation, JSON parsing, and `git diff --check` pass. Swift UI, the GitHub mac-app workflow, local installation, live API routing, and the requested song-to-PDF stress test remain pending. Swift UI is compiled by the GitHub mac-app workflow, not on this Mac.

## v29 work: CAPI-first navigation, Auto Update chat, and Python API

These features were implemented as v29 work and are released together under v30 after the attachment-routing, MIME validation, and cost-accounting refinements above.

## v28 (19.11.2026): Quit guard

Marko asked that Queen never quits without asking. App.swift `Delegate`: `applicationShouldTerminate` shows an NSAlert "Are you sure you want to quit?" (Quit / Cancel) after activating the app; Cancel returns `.terminateCancel`. `applicationWillTerminate` (runs only after a confirmed quit) calls `Queen.shared.stopIfOurs()`: the OFF button used to stop the server and backend BEFORE terminate, so a Cancel would have left a dead Queen; it now only calls `NSApp.terminate`. Bypasses: `Delegate.quitWithoutAsking` (set by `Updater.install` before its terminate, because the detached swap script waits for the PID and the auto-update has nobody to click) and system log out / restart / shut down (quit-reason attribute 'why?' on the current Apple event). CI: `mac_app/test.sh` compiles only app/core/*.swift, not App.swift, so the guard cannot hang it. Side effect: Cmd-Q and Dock Quit now also stop the backend (before, only OFF did). Anything that quits Queen by AppleScript or AX (a session relaunching after a build) now meets the dialog and must press Quit. Not tested live: the dialog itself (compiled only by GitHub).

## v27 (19.11.2026): Gemini 404 recovery and pair model fixes

Code: qwen_app/gemini_hands.py (_find_replacement, _call_with_recovery; text_turn and agent_turn take notice_cb), pair_chat.py (notice lines into the chat, PAIR summary shows the master model and the slave model chain), capi_chat.py (/api/capi/ask: an existing chat can be given a new gmodel or model later), auto_updater.py (retired gemini-2.5-pro out of the list and prices), Capi.swift (MASTER MODEL list retried when the first load failed; models newer than the default in their own section "Newer than the default"). Skill: queen_skills/gemini-404-recovery.md. Compiled by GitHub (mac-app.yml), not on the Mac. Not tested live: the 404 path against a real dead model; py_compile and test_pair_chat.py pass.

## v26 (18.11.2026): MASTER / SLAVE pair of CAPI providers

Marko's words: momentaryupdates.md (two v26 entries: the pair, and "he decides which of Google's models to use ... Vice versa also applies"). Code: qwen_app/pair_chat.py (state, status, prompts, SLAVE_MODEL / VERDICT parsing, PairRun loop, chat words), qwen_app/gemini_hands.py (Gemini with hands), capi_chat.py (Conv._send_pair, Conv.stop stops the pair, run_turn yields labelled pair events, routes GET/POST /api/capi/pair, /api/capi/ask takes master/slave/gmodel/cap_usd/max_rounds), app.py (chat words `pair status | pair master X slave Y | pair off`, $0), test_pair_chat.py (offline, 28 checks, in the install.sh gate). Swift: RoleSwitch beside each radio (OFF → MASTER → SLAVE → OFF), PAIR | A → B + ROUNDS n + CAP $x groups in CapiHeader (or PAIR | SINGLE dim when only one side is set, the note as tooltip), Bubble shows m.label for master (amber) / slave (green) messages, role "pair" end line (green when DONE, amber otherwise), MASTER MODEL in the input row (the master's provider's model picker), placeholder "Write to the master ...". Msg got `label`.

State ~/.groq/capi_pair.json {master, slave, max_rounds 5, cap_usd 0.50}. Active only when both set, different and keyed; otherwise single mode and `note` says why. A pair turn: PLAN (+ `SLAVE_MODEL: id - reason`) -> REPORT n -> REVIEW n (`VERDICT: DONE` ends; `VERDICT: FIX` + next SLAVE_MODEL; no verdict line = FIX, flagged in the label) until DONE / max rounds / cap / STOP. Messages role master|slave with speaker, kind, model, round, verdict, slave_model, label, cost; tool lines prefixed with the provider; one role "pair" end line; room["pair"] keeps sessions (one Claude session per role:provider, resumed) , ghist (Gemini text history per role) and last (rounds with slave model, cost, verdict). Model choice (Marko's addition): the master's system prompt lists the slave's models with tier and $/Mtok (Gemini: newest flash-lite / flash / pro from the live list, prices from gcloud_chat.RATES; Claude: haiku 0.10/0.50, sonnet 2/10, opus 4/20, fable 8/40), policy cheapest first, step up after FIX, cheaper to experiment; invalid id -> the cheapest with a note; a step up whose estimate (12k in + 2.5k out) is over 1.5x what is left of the cap is refused with a pair line and the slave stays on the cheapest.

HANDS, the choice: Claude Code already has hands, so Anthropic / Oxyy run as one-shot `claude -p --resume <role session>` (prompt on stdin, stream-json read for tool lines and cost, `--max-budget-usd` = cap left / provider factor, `--append-system-prompt` role rules + HEADLESS note, `--disallowedTools Bash(langsay:*)`; master `--tools Read Glob Grep`). Google Cloud was text only (one generateContent call). I gave Gemini its own function-calling loop (gemini_hands.agent_turn) instead of routing Gemini through some agent CLI: no new install, the same key file and ledger, every call priced and booked, STOP and the cap checked between calls, and the confinement is ours to read. Four tools: list_files, read_file, write_file, run_shell (zsh -lc in the folder, 1-180 s timeout, process group killed on timeout or STOP). Confinement: realpath inside the chat folder; the folder inside home and never home itself; run_shell refuses sudo/su/launchctl/diskutil/osascript/..., `..`, and ~ or absolute paths outside the folder except system tool folders (/usr, /bin, /opt/homebrew, /tmp, /dev/null). A guard against mistakes, not a sandbox against a hostile model. The model's parts (with thought signatures) are sent back verbatim; max 30 steps. A Gemini master is text only (gemini_hands.text_turn with a systemInstruction) and sees the slave's report in its prompt.

Real tests 18.11.2026 (folder ~/pairtest_v26, deleted after): (1) Anthropic master claude-haiku-5-5 + Google Cloud slave (chose gemini-3.5-flash-lite) "create hello.py that prints 2+2 and run it": DONE after 1 round, $0.0065 (master $0.0061, slave $0.0004). (2) Google Cloud master gemini-3.5-flash-lite + Anthropic slave (chose claude-haiku-5-5): round 1 report was a side note about a background speech job (Claude Code followed Marko's global voice rule and ran langsay), Gemini answered VERDICT: FIX, round 2 correct, DONE after 2 rounds, $0.0178. Fixed afterwards: HEADLESS note + langsay blocked + pick_answer (the result text is used only when it is the real REPORT / REVIEW). (3) Step up: Anthropic master told to fail round 1 on purpose: slave gemini-3.5-flash-lite, FIX, next slave gemini-3.8-flash ("stepped up one tier"), DONE after 2 rounds, $0.0138. (4) STOP during the master's plan (Claude Haiku running): stopped in 1 s, process gone, end line "PAIR STOPPED by STOP (both sides)"; STOP during the slave (Claude Code, after its first tool line, Gemini master): stopped in 1 s, process gone. (5) Single mode regression with only a master set: Gemini flash-lite PONG and Claude Haiku PING, no pair messages, $0.0043. Total spent on tests about $0.045 (plus the unbooked part of the two killed Claude runs, under $0.01). Queen: `queen "pair status"` answered by her chat word (see LESSONS v26). The pair switch was left OFF afterwards (v25 behaviour until Marko switches it).

Left / not tested: the Swift window compiled only by the mac-app workflow; the switch, ROUNDS and CAP were looked at in screenshots but not clicked by hand; Oxyy as master or slave (its key has no Claude access); a Claude master's own SessionStart hook still adds a line about other sessions to its plan (harmless, seen in tests); files attached to a pair prompt are named to the master but not passed to either side; a killed Claude run's partial cost is not known (booked $0).

## v25 (18.11.2026): Gemini only, Queen bypassed

Marko's words: momentaryupdates.md (v25 entry). Google Cloud = Gemini only (gcloud_chat.VERTEX_ENABLED=False keeps the Vertex code dormant; /api/capi/gcloud_models has claude: []). Credit base lives in ONE dict, gcloud_chat.CREDIT ($225.31 read from Billing 18.11.2026 about 16:10, expires 2.12.2026; ~/.groq/capi_gcloud_balance.json overrides): Queen shows "Google Cloud ($225.31 left, to 2.12.2026)". QUEEN BYPASS: CAPI chats (Anthropic = local Claude Code process, Google Cloud = Gemini HTTP) never use Queen's system prompt, queen_skills, Groq/qwen, after_turn or training: capi_chat.py imports none of them, and training_log.record() drops anything written from a thread with TURN.bypass (set for every /api/capi/* request and the Gemini worker). Per-chat switch room["queen"] off|on (default off, POST /api/capi/queen, header word QUEEN: OFF/ON): off also makes POST /api/capi/ask (Queen's capi skill) answer 403; chats created by that ask start "on". Status line shows "Queen bypassed · not trained" while the CAPI tab is open. Switching the radio on the same chat works both ways; gcloud to anthropic sends the history again (force_primer) because Claude's session did not see the Gemini turns. AUTOMATIC NAME on Google Cloud uses Gemini flash-lite. Real test 18.11.2026: Gemini, Claude Code, Gemini, PNG (blue square described), training/skill_cache/queen_skills/chats and the ledgers byte-identical before and after. No queen_skills teaching step by Marko's rule.

## v24 (18.11.2026): Google Cloud provider + file picker

Marko's words: momentaryupdates.md (two v24 entries). Third PROVIDER radio `gcloud` (Google Cloud): qwen_app/gcloud_chat.py (Gemini API with the AIza key read at runtime from ~/Downloads/API/CGP_free_credits_Google API.txt, AQ. backup; Claude on Vertex AI rawPredict with ADC bearer via google-auth, global then us-east5; ledger ~/.cache/gcloud-ledger.jsonl, credit = $254 minus ledger, estimate). capi_chat.py: Conv._send_gcloud/_gworker (a thread, no claude process), room `gmodel`, GET /api/capi/gcloud_models, POST /api/capi/gcloud_balance, /api/capi/send takes `files:[{name,mime,b64}]` (Gemini inline_data, Claude blocks, text inlined, 20 MB each; Anthropic/Oxyy chats get Claude blocks too, untested). Capi.swift: paperclip, drop, paste (PasteView), chips, gmodel Menu. google-auth + requests added to requirements.txt (installed for the Homebrew Python 3.13 that runs the backend). Skill: queen_skills/google-cloud-provider.md. Tested over HTTP (see LESSONS v24). Left: Swift compiled only by the mac-app workflow; no UI screenshot yet; Claude on Vertex waits for ADC and Anthropic's access (clean "not ready yet" line shown); Anthropic/Oxyy file blocks and the 20 MB chip path in the window not tried; drag onto the text view itself not tried.

## v23 (18.11.2026): input inside the chat pane, unlimited

Marko's words: momentaryupdates.md (v23 entry). `CapiPane` = CapiConversation + CapiInput (one right pane); Root no longer has a bottom input for CAPI. `PromptEditor` = NSTextView in NSScrollView (legacy scroller, autohides when it fits), no lineLimit; the only cap of v22 was `.lineLimit(1...8)`. Height handle `ui.capiInputH` (default 110, min 58, max 70% of the pane). Server path checked: Swift proxy reads Content-Length with no cap, Flask/waitress no cap, stdin JSON line unbounded; test: 50,077 characters sent to a Haiku chat via /api/capi/ask, stored whole, cost $0.0059 (first try with random words was refused by Haiku's safety filter, $0.0075). Screenshots: /tmp/q18/v23_default_empty.png, v23_long_text.png (long text, scroll bar), v23_enlarged.png (box dragged taller), v23_min.png and v23_min_empty.png (560 pt). Left: Shift+Return not tried by hand; Return-to-send not tried (the text was pasted, not typed); window geometry restored to 1510x944 afterwards.

## v22 (18.11.2026): one baseline, outline, TOPIC, CHATS back

Marko's words: momentaryupdates.md (v22 entry). FlowLayout now reads each child's `.firstTextBaseline` and places every child at rowBaseline - childBaseline; header groups are `HStack(alignment: .firstTextBaseline)`; the gear is `Text(Image(systemName:))`; the status dot has an alignmentGuide (cap-height centre). Active chat row: green RoundedRectangle outline. CapiConversation starts with a TOPIC | title row. CHATS toggle (`ui.capiShowList`, default true) after NEW CHAT hides list + divider. Rule written in ~/.claude/skills/align/SKILL.md and MANTRA_MANIFEST modules/no-broken-words.md. Screenshots: /tmp/q18/v22_default.png, v22_min.png, v22_chats_hidden.png, zooms v22_zoom_left.png / v22_zoom_right.png. Left: the FOLDER menu text (claude-code) is not bold monospaced like its neighbours (Menu style), baseline is right; RENAME / AUTOMATIC NAME / divider not clicked by hand.

## v20/v21 (18.11.2026): one-line actions, pipes

Marko's words are in momentaryupdates.md (v20 entry). Flow.swift: `.pipeGroup()` (pipe + group as two layout children; FlowLayout keeps them together and hides a pipe that would start a row, clipped), `.flowRight()` (sits at the row's right end). Chat row: RENAME START STOP CLOSE one flow line. CAPI header: groups PROVIDER radios | credit gear | this chat | FOLDER ... | NEW CHAT (right); CAPI CHATS button removed, list always shown (`showCapiRooms` state is unused now). Status line: v21 | Queen | model | keys | spent, the four tabs TRIPLE CAPI CHATS NEW CHAT one right-aligned unit. Screenshots of the real window (screencapture -l) at 1100 and 560 pt looked at: /tmp/q18/v21_default.png, v21_min.png. Left: normal chat list and Triple rooms still have no draggable divider.

## v18/v19 (18.11.2026): no broken words, draggable divider

momentaryupdates.md has Marko's words. Flow.swift: `.unit()` (one line, fixedSize) on every label and `Word`, `FlowLayout` (whole units wrap), `SplitHandle` (draggable divider, `ui.capiListWidth`, 230-520, default 330). Chat row = title, START row, STOP RENAME CLOSE flow. v19 fixed the list pane overflowing at the minimum window width (minWidth 230 squeezes instead of cutting). Rule in MANTRA_MANIFEST modules/no-broken-words.md. Screenshots of the real window (screencapture -l, MacBook screen) at 560 pt and 1100 pt looked at: clean. Left: the status line text (v19 Queen . qwen/... . keys) wraps between words at 560 pt with dangling dots; ChatList (normal chat) and Triple RoomList have no draggable divider yet.

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
