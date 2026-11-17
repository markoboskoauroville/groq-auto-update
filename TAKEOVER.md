## TRIPLE CHAT — in progress (17.11.2026)

Marko, 17.11.2026 (word for word): "Please upgrade my app and don't test it. Just write the code and I'm going to test it myself manually. It's about Queen. I want to have triple chat. And triple chat means there is me in the chat room, there is Claude over API, and there is Groq Queen, our model over API. And in this trio chat box we all can hear each other and comment on each other thoughts. I can ask for example, Queen what do you think about this and she answers. Then I can ask Claude what do you think about this and he answers. And the whole chat history is there and available for everybody. So this is like a pool of three brains where we together discuss and then also we can write the skills, we can also access the GitHub, we can use my computer, so all the skills which Queen already has, she can apply them and also can ask advice. I can for example say, Queen, please ask Claude how to do things and then he explains and she understands. So in this kind of thing, make me triple chat UI, please."
Then: "Before building anything, please write in the takeover of this application what needs to be done. First, write a takeover and then start to build. Because my credits are only 1% and I don't want to lose my prompt, etc. So, takeover needs to be written after every step and right now."

**Decisions.** NO testing by Claude (Marko tests by hand): only py_compile / CI. Claude's side: local Claude Code first
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
2. [ ] `qwen_app/triple_chat.py`: store `~/.groq/triple/<id>.json` {id,title,claude_via,claude_model,last_addressed,messages:[{speaker:marko|queen|claude,text,ts}]};
   routes GET /api/triple/list, GET /api/triple/get?id=, POST /api/triple/new, POST /api/triple/settings {id,claude_via,claude_model},
   POST /api/triple/turn {id,text,to:queen|claude|both|auto} -> NDJSON lines {"speaker":..,"start":1} / {"t":tok} /
   {"need_consent":msg} / {"done":1}. Addressing parser (Queen/Qwen/Quinn, Claude/Cloud/Klod; default last addressed).
   Done = py_compile passes.
3. [ ] Register in `qwen_app/app.py` (try/except like brain; pass pool, build_queen_system_prompt, record_spend,
   _local_command_answer, _after_turn, DEFAULT_MODEL, MAX_OUTPUT_TOKENS); install.sh copies it.
4. [ ] Swift window: `mac_app/app/Triple.swift` (model + view); App.swift: word TRIPLE in the status line switches the
   conversation to the room; ASK QUEEN / ASK CLAUDE / ASK BOTH, CLAUDE VIA LOCAL|API + model picker, rooms; VERSION 9.
   Done = pushed, mac-app run green, release v9 Latest.
5. [ ] `queen_skills/triple-chat.md`.
6. [ ] version.json 9, LESSONS.md, skill groq-ai-studio section, ~/Downloads/API PROJECTS.md line; ./install.sh;
   `mac_app/install.sh v9`; Queen restarted.

**Where we are:** step 1 done.

**Hand-over (17.11.2026, plan at 1%):** Marko: "And since we are losing the credits soon, only 1%, please give a task to Queen and
API through our Queen API of Claude to finish updating the app. So they need to do, you just need to save this 1% as much as possible."
The build runs OFF the plan on the API credit (headless Claude Code, Sonnet 5.5, budget cap $8), brief `docs/TRIPLE_CHAT_BRIEF.md`:
`cd ~/Developer/groq_ai_studio && CLAUDE_API_MODEL=claude-sonnet-5-5 CLAUDE_API_BUDGET=8 nohup claude-api-mode run "$(cat docs/TRIPLE_CHAT_BRIEF.md)" > ~/.cache/triple-chat-build.log 2>&1 < /dev/null &`
Progress: the ticks above (`git pull`), `git log --oneline -5`, `tail ~/.cache/triple-chat-build.log` (its report and
`[claude-api-mode] cost $` appear only at the end), spend `claude-api-mode status` / ~/.cache/claude-api-ledger.jsonl.
Resume: run the same command again; the builder starts at the first unticked step.

