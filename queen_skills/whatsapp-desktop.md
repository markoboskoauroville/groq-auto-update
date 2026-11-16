When: Marko asks about WhatsApp on the Mac (the real app, WhatsApp Desktop): who wrote last, what is unread, open a chat, write a draft, find a message, list photos.
Rule (16.11.2026, Marko: "teach macro recorder how the interface of WhatsApp looks; Queen will ask macro recorder"): you never click or type yourself. The hand is Macro Recorder's tool `whatsapp_ui`
(MACRO_SKILLS tools/whatsapp_ui.py, UI map MACRO_SKILLS/maps/whatsapp-desktop.md, catalogue ids whatsapp-where/chats/unread/search/open/read/box/draft/find/media). It reads by Accessibility, no screenshot.
A PERSON'S NAME ALONE = THE PRIVATE CHAT. "Santoshi group" or "Santoshi chat" (+ a person) = the GROUP (pass group). Never mix them (the Svemir mistake, 16.11.2026).
Chat commands, answered locally ($0): "what did Svemir write last", "which chats are unread", "open Natasha", "draft to Rajko: <text>", "find 'plakat' in the Santoshi group".
Route: POST /api/whatsapp/desktop/<verb> {args: [...], group: true|false}; verbs where chats unread search open read box clear draft find media. Same on the shell: `whatsapp_ui <verb> [--json]`.
Steps:
1. Ask `macroskill has "<what>"` first; the whatsapp-* ids answer it.
2. Read-only verbs (where, chats, unread, read, find, media, box) may run at once. `read`/`open` mark the chat as read in WhatsApp: say so when you used them; for "what is the last message" `chats` already shows the preview without opening.
3. `draft` puts text into the compose box and NEVER sends: the answer must say "NOT sent, Marko sends". It refuses a group unless group, a private chat if group, and text Marko already sent. Repeat the tool's READBACK MATCH/MISMATCH line.
4. Self-check: quote the header title the tool returned (the bold name at the top), never the member line. If the tool says ABORT, report the abort in one line and stop; never retry with a looser name.
5. The first click only activates the app and every `macro do` gives the front app back: the tool handles it; do not run macro clicks around it. Marko may be on a call: if `macro lock-status` says locked, wait.
6. Times are HH:MM (older bubbles carry the date); date separators are not readable by AX. Do not invent a date.
7. Media: `media <chat>` returns time and the screen frame of loaded photos; capture that rectangle with Macro Recorder if a picture is asked for; older photos need scrolling, say so.
Test for a new phrase: ask it in your own chat, compare with the real app (Claude Code reviews the answer against the window).
