# Skill: connection-keeper (Mac only; local, no model, $0)

Marko, 16.11.2026: "Please use my queen to do the tasks from now on." **When:** "connection keeper status", "is the keeper
aggregating", "keeper cable" / "keeper both" / "keeper wifi" (also "switch keeper to both"), "restart speed test".
**What:** Network Aggregate Connection Keeper (Mantra), v84+. Code: qwen_app/ops_hands.py `chat_keeper`.
**Steps:** status = the files in ~/Library/Application Support/connection-keeper: `mode` (aggregate = BOTH, one = one
connection), `nothing-only` (on = only the Nothing phone carries, the cable waits on STANDBY), `aggregate-lines.json` (each
line, standby or carrying). Choice = the distributed notification `ConnectionKeeperChoose` with object wifi | cable | both
(the same as the tick on the stripe), then read the state back after 4 s. Speed test restart = `ConnectionKeeperSpeedRestart`
(opens the speedtest.net window if closed and presses GO itself).
**Say:** one line with the mode, NOTHING ONLY and the lines. **Check before "done":** the read-back shows what was asked.
**Traps:** never press the CABLE word by AX (it opens a list and hangs); the Wi-Fi "mantra" and the cable go to the same
router, so BOTH over those two adds no speed; real aggregation needs NOTHING ONLY off and the Nothing + cable ticked; every
test download costs SIM data (keep it to a few MB). PING VM is Marko's button on the stripe (a terminal with ping).
