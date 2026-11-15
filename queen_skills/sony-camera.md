When: Marko says "connect the camera", "refresh the camera", "reconnect the camera", "start camera recording", "stop camera recording", "camera status", "is the camera recording", "open Imaging Edge Remote", "imaging edge big", "camera full screen", "show me on the BenQ".
App: Sony Imaging Edge Remote (com.sony.Remote, /Applications/Imaging Edge). It shows the live view of the Sony alpha 7 V and its record button.
Steps: local chat commands answer at once (no model, $0) by calling `sonycam connect|start|stop|status` (MACRO_SKILLS tools/sonycam; macro skills
sony-connect, sony-rec-start, sony-rec-stop, sony-status). Camera needs PC Remote on (USB, or the mantra Wi-Fi), the camera in movie mode.
Check before saying "done": the answer must say REC with a counting time code after start, and STBY 00:00:00 after stop. Say the camera's battery warning if shown.
Never: say "Remote" alone to open it (it matches "Stream Deck Remote"); say "Imaging Edge Remote" or "connect the camera". Never click without the Remote window in front (sonycam checks it).
Limits: a test clip really records on the card. Wi-Fi road not tested yet (15.11.2026). Real double-click is needed to connect (list rows refuse AX press).
Phrases (15.11.2026, $0, local chat commands in qwen_app/sony_camera.py):
- "refresh the camera" / "reconnect the camera": `sonycam connect` then `sonycam status` (opens Imaging Edge's connect dialog and refreshes; proven 15.11.2026).
- "camera status": `sonycam status`.
- "imaging edge big" / "camera full screen" / "show me on the BenQ": `sonycam big`. This is Remote maximized on the BenQ through Rectangle, NOT macOS full screen.
v27 behaviour (15.11.2026): on RECORD, Remote goes MAXIMIZED on the BenQ with a click-through RECORDING overlay and a timer (Second Take's RecOverlay). It stays
there after the take: there is NO flip back to the MacBook. Marko moves it himself if he wants it elsewhere.
Test rule: never run start or stop in a test (a real clip lands on the card). Test only "camera status" and the connect/refresh/big phrases.
