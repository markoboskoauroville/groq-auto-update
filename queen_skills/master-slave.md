# master-slave (v26, 18.11.2026): two CAPI providers linked as MASTER and SLAVE

Marko, 18.11.2026: "next to each provider of the API key. We have a switch master or slave ... if non-master or no slave is
selected, it means just this one provider is working ... Anthropic master, Google Cloud slave ... I am giving all the prompts to
the master ... the master is developing a working plan for the slave ... it gives you back the report ... you suggest future
improvements, or you say this is okay ... If in the report there are some issues, you advise Google how to solve the issues,
and then he executes." And: "if Anthropic is master, he decides which of Google's models to use depending on the task ... a
higher model or ... lower models. Vice versa also applies."

## What it is
In the CAPI tab every provider radio (ANTHROPIC, OXYY, GOOGLE CLOUD) has a small switch OFF / MASTER / SLAVE. One master and
one slave, different providers, both with a key = a PAIR (header: "PAIR | ANTHROPIC → GOOGLE CLOUD", then ROUNDS n and CAP $x).
Anything else = single mode, exactly as before (the radio decides).

A pair turn: Marko's prompt goes to the MASTER -> PLAN (+ `SLAVE_MODEL: <id> - reason`) -> the SLAVE works in the chat's
folder and sends a REPORT -> the MASTER reviews: `VERDICT: DONE` ends it, `VERDICT: FIX` + fixes (+ SLAVE_MODEL for the next
round) sends the slave again. Ends at DONE, max rounds (default 5), the cost cap (default $0.50 per pair turn) or STOP.
The master chooses the slave's model every round from the slave's list (cheapest first, with tier and price): Gemini
flash-lite / flash / pro; Claude haiku / sonnet / opus / fable. Cheapest first, a step up after a failed round, a cheaper one to
experiment; a step up that would pass the cap is refused (the slave stays on the cheapest).

## Routes (127.0.0.1:8765)
- `GET /api/capi/pair` -> {master, slave, max_rounds, cap_usd, active, note, label, models.slave[]}
- `POST /api/capi/pair {"master":"anthropic"|"oxyy"|"gcloud"|"", "slave":..., "max_rounds":1-10, "cap_usd":0.01-20}`
  (setting a provider as master clears it as slave; "" = off). Chat words, $0: `pair status`, `pair master anthropic slave
  google`, `pair off`.
- A pair run for you (one call, waits, spends credit on BOTH providers: say so first):
  `POST /api/capi/ask {"text":"<task>", "cwd":"/Users/markobosko/<folder>", "master":"anthropic", "slave":"gcloud",
  "model":"claude-haiku-5-5", "gmodel":"gemini-3.5-flash-lite", "cap_usd":0.20, "max_rounds":3}`
  -> {answer (every labelled message + the PAIR line), cost, id, pair_end ("DONE after 1 round" | "STOPPED ..." | "COST CAP ..."
  | "MAX ROUNDS ..." | "ERROR: ...")}. `model` = a Claude master's model, `gmodel` = a Gemini master's model; the slave's model
  is chosen by the master. The saved switch is not changed by an ask. The chat is made with QUEEN: ON (yours), as in capi.md.
- The window's path: `POST /api/capi/send {id,text}` with the saved pair active; STOP = `POST /api/capi/stop {id}` (both sides).

## Hands
Anthropic / Oxyy = Claude Code (a master gets only Read Glob Grep, a slave everything in auto mode). Google Cloud = Gemini:
master text only, slave a tool loop (list_files, read_file, write_file, run_shell) confined to the chat's folder (inside home,
never home itself; no sudo / launchctl / paths outside; 180 s per command; 30 steps).

## Checks and traps
- The folder must be a project folder: Gemini's hands refuse the home folder itself.
- Costs land on each provider's own ledger (Anthropic api_credit, Oxyy ledger, Google Cloud ledger) and on each message.
- A STOP during a Claude run cannot know the run's partial cost (no result event): it is booked as $0.
- Claude Code reads Marko's global CLAUDE.md; the pair prompt tells it not to speak (langsay is also blocked) and to end with
  the full answer. If a REPORT looks like a side note, the review will say FIX: that is the loop working.
