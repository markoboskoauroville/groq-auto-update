# Skill: talk-mode (Mac; local, no model, $0)

Marko, 15.11.2026 (training mode). **When:** "talk mode status", "talk mode on/off", "auto" / "manual" (also "talk mode auto"), "space mode test", "space mode off".
**What:** Talk Mode (Mantra) v11, menu-bar app; state in `~/Library/Application Support/Talk Mode (Mantra)/state.json` (`on`, `mode` AUTO|MANUAL, `space_mode`, `state`, `target`).
**Steps (code: ops_hands.py `chat_talkmode`):** if the app is not running, say so (never start it by myself: the star starts apps). on/off = `open -g talkmode://on|off`
(URL scheme; the voice confirms). AUTO/MANUAL has NO URL: Macro Recorder presses the checkbox `AUTO` (`macro ax-press "Talk Mode (Mantra)" "AUTO"`, macro skill talk-auto-switch); read state.json first and press
only when the mode differs, then read it back from state.json. "space mode test" = `open -g talkmode://space-test` (Space Mode 10 s, ends by itself) and only if `space_mode` is false;
`talkmode://space-off` ends it. **Space Mode is never turned on** by Queen without the 10 s test URL (it switches off his keyboard and mouse).
**Check:** the summary line from state.json (ON/OFF, AUTO/MANUAL, target session, Space Mode). **Traps:** Space Mode needs Accessibility for Talk Mode; on 15.11.2026 it was MISSING (window shows
"Space Mode needs Accessibility ..."), so the test cannot run until Marko grants it; the TALK MODE and SPACE MODE checkboxes could be pressed the same way but on/off by URL is cleaner.

**v12 (15.11.2026):** "talk mode status" answers state.json `plain` (one sentence in Marko's words: LISTENING, "Voice to Text (Vox) is recording; I wait", "You are recording with Talk Mode" ...) plus on/off, AUTO/MANUAL, target, Space Mode. The word PAUSED no longer exists; never say "paused" for a recording.

**v15 (15.11.2026):** in Space Mode Esc pressed twice (within 1 s) exits it; one Esc while dictating cancels the take (nothing sent). There is no "hold Esc 2 s" any more.
