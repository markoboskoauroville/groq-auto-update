# Skill: claude-control (pause all Claude, resume Claude; local command, $0)

Marko, 16.11.2026: "I can pause all the tasks which are happening and also resume them. Play pause button, simple." And: "All our tools need to be paused at the same time."
**When:** "pause all Claude", "pause Claude", "pause everything", "resume Claude", "is Claude paused", "claude status".
**What:** Claude Control (Mantra), the menu-bar play/pause, freezes every Claude Code session and everything it started (SIGSTOP, children first) and pauses the registered tools (Macro Recorder, you) through their own pause APIs; resume continues exactly where each stopped.
**How:** run the shell command `claudectl pause`, `claudectl resume` or `claudectl status` (in ~/.local/bin) and read back its lines. `status` first when unsure. `claudectl pause` also pauses you: after it, only `claudectl resume` or POST /api/resume continues, so say "paused, say resume Claude to continue".
**Rules:** never pause by killing processes yourself; if paused over 10 minutes tell Marko that API connections may time out and sessions may retry or report errors; never touch the Voice Engine, Macro Recorder's app, Talk Mode, Voice to Text, Firefox, Tailscale or Connection Keeper (Claude Control already protects them).
Rule: MANTRA_MANIFEST modules/pause-all.md. App repo markoboskoauroville/CLAUDE_CONTROL.
