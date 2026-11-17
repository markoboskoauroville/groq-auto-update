# capi (Claude Code on the API credit, the CAPI tab)

Marko, 17.11.2026: "can queen be used as capi ... add capi tab to queen software so i can have nicer ui". `capi` (command in
~/.local/bin) is a chat with Claude Code that runs headless `claude -p` on his $100 promotional API credit (that credit pays only
headless runs, not a normal Claude Code window). The CAPI tab (word CAPI in the Queen window, beside TRIPLE) is its nicer face:
Markdown answers, one line per tool, cost per answer, "API ($NN.NN left)" at the top, model picker (HAIKU, SONNET default,
OPUS, FABLE), folder picker (default ~/Developer/claude-code), Stop, rooms (one Claude Code session each, so the conversation continues).

When you send a task there: Marko asks for real work in a project folder (edit files, run commands, review code) that needs Claude
Code's hands and is not a question for you or for the TRIPLE room. Cheapest model first: haiku for small things, sonnet to code,
opus for hard debugging; fable only with a reason. Every run costs real credit: say the model and the folder before you start.

How you start a run (one call, answer comes back whole):
`POST /api/capi/ask {"text": "<the task>", "cwd": "/Users/markobosko/Developer/<project>", "model": "claude-haiku-5-5", "id": "<room id to continue, optional>"}`
-> `{answer, cost, id, left, error}`. Keep the `id` to continue the same conversation. The streaming form for the window is
`POST /api/capi/turn {id, text}` (NDJSON). Other routes: `GET /api/capi/credit`, `/folders`, `/list`, `/get?id=`, `POST /new`, `/settings`, `/stop`, `/delete`.

ONE credit number: every run (capi, claude-api-mode, the tab) is a line in ~/.cache/claude-api-ledger.jsonl; the balance is
`tools/api_credit.py` (calibrated $96.66 at 17.11.2026 13:50 minus later spend). Never quote another number. Credit expires 15.12.2026.
Traps: the key is never printed; the run's folder must be inside the home folder; Stop kills the run, the cost so far is still booked.
