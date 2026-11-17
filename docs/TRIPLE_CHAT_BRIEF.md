# Brief for the API builder (17.11.2026)

Read ~/Developer/groq_ai_studio/TAKEOVER.md section "TRIPLE CHAT — in progress (17.11.2026)" and build it step by step,
starting at the first unticked step. After EVERY step: tick it in TAKEOVER.md, update "Where we are" with one line of what
is left and any trap found, commit and push to main (end commit messages with
"Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>").

Rules:
- NO testing: Marko tests by hand. Only free static checks: `python3 -m py_compile`, `swiftc -parse` is NOT allowed (no
  compiling on the Mac); the GitHub workflow mac-app.yml is the Swift check (`gh run list --workflow mac-app.yml -L 1`, read its colour).
- Never send a chat to Groq or Claude, never a paid call, never open a browser. Never print or commit a key (`grep -rn 'gsk_\|sk-ant-' .` before every commit).
- Read only what a step needs: qwen_app/app.py around `_local_command_answer`, `_after_turn`, `chat()`, brain registration (~line 537);
  qwen_app/claude_link.py (`route`, `ask`, CONSENT_TEXT); qwen_app/auto_updater.py `load_auto_update_store`, `_stream_anthropic_surgical`
  (headers/endpoint to copy for a plain Messages call); mac_app/app/App.swift + Queen.swift (the window; reuse Bubble, Word, Hairline,
  pressHover, axButton, Ink: one module, no second copy; speaker colours Marko=Ink.dim, Queen=Ink.accent, Claude=a new Ink.claude);
  mac_app/app/core/QueenServer.swift only to confirm /api/triple/* falls through to the proxy (it does: unknown routes are proxied).
- Swift: whole-number VERSION 9 in mac_app/app/App.swift; the push builds release v9 Latest. Controls on one grid (MANTRA_MANIFEST
  modules/alignment.md), every word an axButton with pressHover, text wraps, nothing cut at 560 pt.
- Python: `./install.sh` after step 3 (tests gate it; if a test fails, read why, fix, do not skip). Restart Queen's backend:
  `curl -s -X POST 127.0.0.1:8765/api/...` is NOT needed; the Swift app's watchdog restarts the backend: kill only the backend pid
  (`lsof -ti tcp:8766`), it comes back within 20 s. Step 6: `mac_app/install.sh v9` only after the run is green.
- Registry: one dated line in ~/Downloads/API/PROJECTS.md under groq_ai_studio (never read the other files there).
- You may ask Queen for advice with `queen "<question>"` (costs her Groq tokens, cheap); not needed.
End with a 5-line report: steps done, commit, run link + colour, what is left.
