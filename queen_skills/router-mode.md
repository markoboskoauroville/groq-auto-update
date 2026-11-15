# Skill: router-mode (Mac; local, no model, $0)

Marko, 15.11.2026: Queen answers which internet the house is on, and switches the router only after an explicit yes.

**Design (background):** the TP-Link router stays in Wireless Router Mode for good. Its own LTE backup carries the house on the
SIM automatically when the Nothing phone's cable has no internet (no reboot, works also when the Mac is away). The Mac watcher
(LaunchAgent com.mantra.routermode) only reports and warns; the menu-bar app "Router Mode (Mantra)" shows it.

**When:** "router status", "router", "which internet", "internet status" -> `routermode state` (the watcher's last reading,
instant, no router login), answered in one plain sentence ("The house is on the SIM backup; 210 MB of SIM today; the phone is home
but Ethernet tethering is off. Router mode is PHONE."). A WARNING from the watcher is appended.
If the reading is older than 3 minutes or missing: `routermode status --json` (fresh, logs into the router).
**Switching:** "use phone internet" / "use phone" / "use SIM" / "use sim only". `routermode set phone --yes` = Wireless Router Mode
(internet from the phone's cable); `routermode set sim --yes` = 3G/4G Router Mode (SIM only). A set REBOOTS the router: the whole
house is offline 1-2 minutes. So Queen first ONLY asks: "This reboots the router, the house is offline 1-2 minutes. Say 'yes, use SIM'
to go on." and runs the set only when the next message is exactly "yes, use SIM" / "yes, use phone".
**Code:** qwen_app/router_mode.py `chat_router_command`, wired first in `_local_command_answer` (app.py).
**Traps:** never run `routermode set` without that explicit confirm; never in tests. Normal mode is PHONE with SIM as automatic backup,
so "use SIM only" is rarely right: say so if asked why.
