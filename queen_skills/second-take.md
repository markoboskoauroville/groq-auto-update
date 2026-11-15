When: Marko says "start second take", "next exercise" (or "next shot"), "stop second take", "second take status", and, while Second Take runs, the short phrases "record", "keep", "again", "stop", "watch shot N".
App: Second Take = MPA Lessons Analyzer (Mantra) v23+, local API 127.0.0.1:8965. Since 15.11.2026 the take is recorded on the Sony's card by remote
control (sonycam through Imaging Edge Remote). v26: for a take the REAL Remote comes to the front on the MacBook screen, almost-maximized by Rectangle
(`sonycam front`, never full screen); after the take it goes to the other screen (`sonycam away`) and Second Take comes back. Second Take mirrors REC
and the camera's counter and writes a small guide track from the Mac's microphone per take. Never copy or capture Remote's window (Marko: "disaster"). The guide (shots, clips, Beatrice's words) comes from his transcribed class of 12.11.2026,
ordered by the MPA Academy LESSON PLAN (tools/plan_sync).
Steps: local chat commands answer at once ($0, qwen_app/second_take.py): start = open the app if needed, POST /shoot/start, POST /live (Remote to the
front, no recording); next = POST /next (refused while recording); stop = POST /record/stop when recording, else POST /stop (closes the full screen);
status = GET /status (shot, mode, camera REC/STBY and counter).
Check before saying "done": after stop the status says "not recording" and the camera STBY; after start the mode is live.
Never: start a camera recording in a test (a real clip lands on the card); never comment on the camera's settings or battery (Marko handles them).
Afterwards: tools/secondtake-match <card folder> pairs each take with its card clip; tools/secondtake-finish exports.
Short phrases (15.11.2026, qwen_app/second_take.py; they act only while Second Take is running, otherwise they are not answered here):
- "record" = POST /shoot/action {"action":"record"} (starts the take on the card; Remote maximized on the BenQ with the RECORDING overlay, v27).
- "keep" = POST /shoot/action {"action":"keep"} (keeps the take, moves to the next shot). "again" = {"action":"again"} (readies the same shot again).
- "stop" = the existing stop branch (POST /record/stop when recording, else POST /stop).
- "watch shot N" = POST /shoot/action {"action":"watch","shot":N} (plays the shot's guide; no camera recording).
- "keep", "again" and "record" are refused while a take records ("say stop first"). Never run record or stop in a test.
