# Skill: pause-all (PAUSE / RESUME every hand; local, no model, $0)

Marko, 16.11.2026: "Please expand the pause to macro recorder and Queen. All our tools need to be paused at the same time
and need to have this kind of API calls to be stopped."
**When:** "pause", "pause everything", "pause Queen", "resume", "pause status", "are you paused".
**What:** one switch for all of Queen's hands. Claude Control presses it for every tool at once; Queen is one of its tools.
**Routes (127.0.0.1:8765):** `POST /api/pause`, `POST /api/resume`, `GET /api/pause/status`, each answers
`{"paused":bool,"since":epoch|null,"queued":N}`. Chat commands: `pause`, `resume`, `pause status`. From a session:
`queen "pause"` or `queen pause` / `queen resume` / `queen pause status`.
**While paused:** no new Groq/Claude call starts; a chat waits (queued, up to 5 minutes) and goes on at resume; a route
that would start work (backdoor `/api/remote/send`, every hand route) is answered at once `{"paused":true,...}`; a Groq
stream in flight is cancelled cleanly (nothing recorded, no key cooled) and answered "paused", never as an error; running
hands (macro calls, Firefox, adb, WhatsApp, Google Photos, connection keeper) stop BETWEEN steps, at the next command they
would start, and continue on resume. The state is `~/.groq/pause.json`, shared by the Swift app and the Python backend, so
a restart while paused stays paused.
**Check before "done":** `GET /api/pause/status` says what was asked.
**Traps:** pause/resume/status, chats bookkeeping, keys and the supervisor stay answerable while paused. A step already
running (one long command) finishes first; that is "between steps". Never stop Claude sessions with SIGSTOP; pause is Queen's
own switch only. Forgetting to resume leaves Queen silent: when she answers "paused", say so and offer `resume`.
