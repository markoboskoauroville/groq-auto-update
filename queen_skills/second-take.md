When: Marko says "start second take", "next exercise" (or "next shot"), "stop second take", "second take status".
App: Second Take = MPA Lessons Analyzer (Mantra) v23+, local API 127.0.0.1:8965. Since 15.11.2026 the take is recorded on the Sony's card by remote
control (sonycam through Imaging Edge Remote); Second Take shows Remote's window full screen, mirrors REC and the camera's counter, and writes a
small guide track from the Mac's microphone per take. The guide (shots, clips, Beatrice's words) comes from his transcribed class of 12.11.2026,
ordered by the MPA Academy LESSON PLAN (tools/plan_sync).
Steps: local chat commands answer at once ($0, qwen_app/second_take.py): start = open the app if needed, POST /shoot/start, POST /live (picture,
no recording); next = POST /next (refused while recording); stop = POST /record/stop when recording, else POST /stop (closes the full screen);
status = GET /status (shot, mode, camera REC/STBY and counter).
Check before saying "done": after stop the status says "not recording" and the camera STBY; after start the mode is live.
Never: start a camera recording in a test (a real clip lands on the card); never comment on the camera's settings or battery (Marko handles them).
Afterwards: tools/secondtake-match <card folder> pairs each take with its card clip; tools/secondtake-finish exports.
