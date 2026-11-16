# Skill: tailscale-up (Mac only; local, no model, $0)

Marko, 16.11.2026: "the TAILSCALE switch is always off when I start it ... make our macro recorder check for its settings and
change them if it's not connecting." **When:** "is tailscale up", "tailscale status", "tailscale", "connect tailscale",
"turn on tailscale", "fix tailscale", "ensure tailscale up"; also when Frankfurt (the ttt-relay 100.102.86.30:8897) does not answer.
**What:** the Macro Recorder catalogue action `tailscale-ensure-up` (MACRO_SKILLS, `macroskill run tailscale-ensure-up`, command
`tailscale-ensure-up`, `--check` only reads, `--json` for code). Code: qwen_app/ops_hands.py `chat_tailscale`.
**Steps:** status first (`TAILSCALE_BE_CLI=1 Tailscale status --json`, BackendState Running = nothing to do). Off: `Tailscale up`
(no flags, settings kept, the exit node never touched), read back; still off: Macro Recorder really clicks the Tailscale icon
in the menu bar and "Connect", reads back, gives the front app back.
**Say:** the tool's one line, e.g. "tailscale: up, already connected" or "tailscale: up, turned on by the CLI".
**Check before "done":** exit 0 and BackendState Running. **Traps:** NeedsLogin = Marko signs in himself (never a script);
never `up --reset`, never logout, never change the exit node here (that is vpn-mantra); the binary without TAILSCALE_BE_CLI=1
is the GUI. Why it is off after a restart: macOS quits Tailscale.app at shut-down and the app switches its connection off
as it quits; Connection Keeper v83's guard brings it up once after login.
