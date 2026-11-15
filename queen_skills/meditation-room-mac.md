# Skill: meditation-room-mac (Mac; local, no model, $0)

Marko, 15.11.2026 (training mode). **When:** "meditation room NDI on/off", "pre-show text <words>", "meditation room status".
**What:** Meditation Room (Mantra), Mac app, local door 127.0.0.1:8965 (MANTRA_ROOM mac/app/Door.swift): `GET /health`, `/api/state`; `POST /api/text {"text"}` (melting words over the picture),
`POST /api/ndi {"on":bool}`, `/api/preshow {"on","until":"HH:MM"}`, play-loop, stop, gain.
**Steps (code: ops_hands.py `chat_meditation`):** if /health does not answer the app is not running: say "say 'open Meditation Room' first" (the open command is another skill; nothing starts by itself).
Text: POST then say the words shown. NDI: POST, then read `/api/state` back. **Traps:** do not change the app; never start play-loop from this skill (it plays music); this is the Mac app,
the Linux stream on the VM is skill stream-preshow-vm (`mrlinux text "..."`).
