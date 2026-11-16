When: Marko says "draft in WhatsApp to <chat>: <text>" (also write/type/put ... in/into WhatsApp [Desktop] to <chat>: <text>), or asks for any message to a person to be written in WhatsApp. Always the real WhatsApp Desktop app, never Firefox or Web.
Rule (Marko, 16.11.2026): a message is TYPED into the chat's box and left unsent; he presses Send himself. Never Enter on a finished message.
Steps (the hand is Macro Recorder, qwen_app/whatsapp_draft.py runs ~/Developer/MACRO_SKILLS/tools/whatsapp_draft.py, $0, no model):
1. The macro fronts WhatsApp Desktop by a real click on a blank sidebar spot (the first click on an inactive app only activates it).
2. Cmd+F, Cmd+A, type the chat name; OCR the first result under "Chats"; click it; check by OCR that the header shows the name.
3. Click the message box, Cmd+A + Backspace (clears an old draft), paste the text from the clipboard (ž š ć arrive exactly, new lines do not send), restore his clipboard.
4. OCR the box and compare words (accents stripped, OCR drops them): answer carries "MATCH" or "MISMATCH" and a capture path in /tmp/wa_draft_<chat>.png.
Check before saying done: "READBACK ... MATCH" and "NOT SENT". Read the capture if MISMATCH. If the header is not found it aborts: say which chat was not found; with two chats of the same name (Rajko) list them and ask.
Traps: each `macro do` hands the front app back at its end, so one script per phase starts with the blank-sidebar click; Talk Mode Space Bar Mode holds the input lock: wait, never override; WhatsApp ignores JavaScript, only Macro Recorder input.
Tested 16.11.2026: Svemir Vranko and Natasha drafts, readback MATCH.
