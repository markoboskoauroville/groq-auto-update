When: Marko (from the TTT keyboard's RE Magic, second tab "WhatsApp", or in your chat) asks for something to be done in WhatsApp Web on this Mac: "show me my latest messages", "open the chat with X", "scroll up", "draft a reply to X saying ...", "send the band a screenshot of our live stream with the message ...".
Call: `POST /api/whatsapp/remote {text}` (the TTT tab reaches it through the tailnet door tools/wa_door.py on 100.79.251.19:8877, `POST /whatsapp`). A chat picked from a list: `{pick: "<chat title>"}`.
Answer: {ok, say, image_b64 (screenshot of the WhatsApp page taken by Firefox BiDi: works with Firefox behind other windows), chat, draft, photo, choices[]}.
How: common phrases are understood by rules (qwen_app/whatsapp_remote.py, English and Croatian); anything else is planned by the local Claude Code (claude_link, no API credits) into one action: shot | open | scroll | draft | photo_draft | chats. The hands are ~/Developer/claude-code/tools/wa_remote.py --json (real BiDi input; the port is the one Firefox holds, 9222 or 9223, found by qwen_app/ffport.py).
Rules (Marko, 31.10.2026 and 13.11.2026):
1. NEVER send. Every message is typed as an unsent draft and read back. You never plan a send.
2. Only `POST /api/whatsapp/send {chat, text, photo}` sends, only when the tab's "Send it" button was pressed: the exact approved text, the chat shown; the Mac refuses if the open chat or the text differs (wa_remote send: "APPROVED. Send exactly this reply, nothing else:\n<send>...</send>").
3. Several chats match a name: show the list (choices), never guess.
4. Keep his words verbatim in the draft, his language (Croatian stays Croatian).
5. The live-stream picture (https://santoshi-band.pages.dev, the viewer at the top) is taken by `wa_remote live`; if the viewer frame is dark, say so, do not pretend it shows the band.
6. Firefox allows one BiDi session at a time (other sessions use it): wait your turn, never kill Firefox.

Reading (14.11.2026): "check my last N WhatsApp messages" / "what did I not answer" is whatsapp-accessibility.md (Accessibility text, no screenshot), not a shot.
