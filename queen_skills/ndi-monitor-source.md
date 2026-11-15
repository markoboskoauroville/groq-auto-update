When: Marko says "show <X> in the NDI monitor", "switch NDI source to <X>", "change the NDI source", "which NDI sources are there",
"list NDI sources" (X = a part of the name: "Meditation Room", "Pixel 7 Camera", "Test Patterns"; names are hints, one clear match is used).
App: the official NDI Video Monitor (NDI Tools). Its window shows ONE source; the source is picked in the menu bar NDI > machine > source.
Steps: local chat commands answer these at once (no model). Or `GET /api/ndi/sources` and `POST /api/ndi/select {"source": "Meditation Room"}`.
Behind them the macro skills `ndi-monitor-list` and `ndi-monitor-source` (`macroskill run ndi-monitor-source --arg source="..."`,
tool `ndimon`): Accessibility menu press, no keys, no mouse, the front app is not touched, the app is opened in the background if needed.
Check before saying "done": the answer says "confirmed" (window title follows the new source). "menu item pressed, title still ..." means
the source sends no frames: say so, then look at the window (`ndimon shot`, then the screenshot) and tell Marko what you see.
If no source matches, read him the list. A phone source (Pixel 7 Camera) exists only while the app on the phone is sending.
