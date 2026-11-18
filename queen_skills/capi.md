# capi (Claude Code on the API credit, the CAPI tab)

Marko, 17.11.2026: "can queen be used as capi ... add capi tab to queen software so i can have nicer ui". `capi` (command in
~/.local/bin) is a chat with Claude Code that runs headless `claude -p` on his $100 promotional API credit (that credit pays only
headless runs, not a normal Claude Code window). The CAPI tab (word CAPI in the Queen window, beside TRIPLE) is its nicer face:
Markdown answers, one line per tool, cost per answer, "API ($NN.NN left)" at the top, model picker (HAIKU, SONNET default,
OPUS, FABLE), folder picker (default ~/Developer/claude-code), Stop, chats (one Claude Code session each, so the chat continues).

When you send a task there: Marko asks for real work in a project folder (edit files, run commands, review code) that needs Claude
Code's hands and is not a question for you or for the TRIPLE room. Cheapest model first: haiku for small things, sonnet to code,
opus for hard debugging; fable only with a reason. Every run costs real credit: say the model and the folder before you start.

How you start a run (one call, answer comes back whole):
`POST /api/capi/ask {"text": "<the task>", "cwd": "/Users/markobosko/Developer/<project>", "model": "claude-haiku-5-5", "id": "<room id to continue, optional>"}`
-> `{answer, cost, id, left, error}`. Keep the `id` to continue the same chat. The streaming form for the window is
`POST /api/capi/turn {id, text}` (NDJSON). Other routes: `GET /api/capi/credit`, `/folders`, `/list`, `/get?id=`, `POST /new`, `/settings`, `/stop`, `/delete`.

ONE credit number: every run (capi, claude-api-mode, the tab) is a line in ~/.cache/claude-api-ledger.jsonl; the balance is
`tools/api_credit.py` (calibrated $96.66 at 17.11.2026 13:50 minus later spend). Never quote another number. Credit expires 15.12.2026.
Traps: the key is never printed; the run's folder must be inside the home folder; Stop kills the run, the cost so far is still booked.

v17 (18.11.2026), chats, providers, rename. Marko: "change conversation to chat", new chat always at the top; "radio buttons at the top for all API providers"; "a Rename action ... an Automatic Name button".
- The tab says CHATS / NEW CHAT. The list is ordered by creation time, newest first, and never reorders itself (before v17 it was sorted by last activity, so a new chat sank below any chat that was answering).
- PROVIDER radios at the top: Anthropic and Oxyy (oxyy.ai, a gateway: Claude through the Messages API at https://api.oxyy.ai, 60% cheaper than Anthropic's list). To switch: `POST /api/capi/provider {"provider":"anthropic"|"oxyy"}` (kept by the server); the next prompt of any chat runs on it (the chat's Claude Code process restarts by itself). Each provider has its own key: the gear picks the file for the CHOSEN provider (`POST /api/capi/key {path, provider}`, key found by shape; Oxyy = 4 characters, a dash, 64 characters).
- Credit: `GET /api/capi/credit` -> {left, provider, providers[], note}. Anthropic = tools/api_credit.py. Oxyy has no balance endpoint: the credit is a starting balance (click the credit in the window, or `POST /api/capi/oxyy_balance {"usd":N}`) minus the costs Queen booked (~/.cache/oxyy-ledger.jsonl); say it is an estimate. Cost per answer is shown the same way for both. Oxyy's key (18.11.2026) could not call Claude: /v1/models listed only deepseek-flash, Atria-Dawn-Preview, eleven_flash_v2 and those are OpenAI-format only; Claude Code on it needs a key with Claude access.
- RENAME (beside START / STOP / CLOSE): `POST /api/capi/rename {"id","title"}`. AUTOMATIC NAME: `POST /api/capi/autoname {"id"}` -> {title, cost}: one Haiku call (max_tokens 20, the last ~8k characters of the chat, on the chosen provider) that only suggests; then rename saves it. Renaming does not move the chat in the list.

v18/v19 (18.11.2026), layout. Marko: "Please don't break the lines in the user interface ... the divider between the chats in the left and right windows should be resizable." In the CAPI tab every label and button is one unbreakable line; whole buttons wrap to the next row, never letters. A chat in the list: the title, then START on its own row, then STOP RENAME CLOSE. The divider between the list and the chat is draggable (230 to 520 points, double-click = 330, remembered). If Marko says a word is broken in the window, it is a bug: tell Claude Code.

v20/v21 (18.11.2026), layout again. Marko: "put everything in one line ... Rename, then Start, then Stop, and then lastly Close ... Put New Chat on the right side ... one pipe symbol ... to divide logical groupings of every text." A chat in the list: its title, then ONE line RENAME START STOP CLOSE (only a very narrow pane wraps, whole buttons). The CAPI tab has no CHATS button: the list is always shown, the divider sizes it. NEW CHAT is at the right end of the header line after a pipe. Pipes "|" divide the groups of the header and the status line (v21 | Queen | model | keys | spent); a pipe belongs to the group after it and is hidden when it would start a row.

v22 (18.11.2026). Marko: green outline on the active chat, the title once more at the top of the chat, the CHATS button back, all text on one baseline. The active chat in the list has a full green rounded outline. The chat pane starts with "TOPIC | <chat title>". In the header after NEW CHAT there is "| CHATS": it hides the whole list pane (and the divider) so the chat fills the window; clicking again shows it; remembered. Every row of text sits on ONE baseline (FlowLayout aligns by text baseline; the gear is a Text(Image), the status dot is centred on the cap height). Never remove a control Marko did not ask to remove.

v23 (18.11.2026). Marko: "Chat box at the bottom ... resize it to be at the size of chat stream ... extend chat list to the bottom ... don't make any limitation in the length of the text ... Resizable, and if there is more text, I want to see scroll bar." The text box and its MODEL / SEND row are inside the right pane, exactly as wide as the chat stream; the chat list runs to the bottom of the window; with CHATS hidden the box is full width. The box has no character or line limit (a 50,000 character text arrived whole), a drag handle on its top edge sets its height (about 2 lines to 70% of the pane, double-click resets, remembered), and a scroll bar shows when the text is longer than the box. Return sends, Shift+Return (or Option+Return) is a new line.
