When: Marko says "connect the camera", "start camera recording", "stop camera recording", "camera status", "is the camera recording", "open Imaging Edge Remote".
App: Sony Imaging Edge Remote (com.sony.Remote, /Applications/Imaging Edge). It shows the live view of the Sony alpha 7 V and its record button.
Steps: local chat commands answer at once (no model, $0) by calling `sonycam connect|start|stop|status` (MACRO_SKILLS tools/sonycam; macro skills
sony-connect, sony-rec-start, sony-rec-stop, sony-status). Camera needs PC Remote on (USB, or the mantra Wi-Fi), the camera in movie mode.
Check before saying "done": the answer must say REC with a counting time code after start, and STBY 00:00:00 after stop. Say the camera's battery warning if shown.
Never: say "Remote" alone to open it (it matches "Stream Deck Remote"); say "Imaging Edge Remote" or "connect the camera". Never click without the Remote window in front (sonycam checks it).
Limits: a test clip really records on the card. Wi-Fi road not tested yet (15.11.2026). Real double-click is needed to connect (list rows refuse AX press).
