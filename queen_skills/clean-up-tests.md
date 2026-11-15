# Skill: clean-up-tests (Mac; local, no model, $0)

Marko, 15.11.2026 (training mode; skill clean-up-after-tests). **When:** "clean up tests", "testclean", "what did the tests leave behind".
**Steps (code: ops_hands.py `chat_cleanup`):** run `testclean` (list only: headless/debug browsers, recorders, emulator, test tmux, debug flag files, phone touch overlays, temporary GitHub repos, VM test tmux/browsers)
and report the output as it is. `testclean --kill` (headless browsers + phone overlays) ONLY after Marko's explicit "yes, clean up tests --kill". Recorders, emulators, repos and VM items are stopped by hand
after checking whose they are (a live take or stream may be in the list): never guess.
**Traps:** a headless Chrome listed may belong to another running session: say whose it looks like (user-data-dir) and do not kill it without the yes.
