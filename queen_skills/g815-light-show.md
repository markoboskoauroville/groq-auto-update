# Skill: g815-light-show (Mac; local, no model, $0)

Marko, 15.11.2026 (training mode). **When:** "light show now", "stop light show", "idle light show on/off", "light show status".
**What:** G815 Lights v38 (login agent community.auroville.g815lights) HTTP on 127.0.0.1:8877: `POST /idle/start` = start the show now, `POST /stop` = back to his profile,
`POST /idle {"on":bool,"minutes":5,"show":"all"}` = the switch "show after N min of inactivity", `GET /idle`, `GET /status`.
**Steps (code: ops_hands.py `chat_lights`):** one POST, then say it; for idle on/off read `GET /idle` back and say the state. **Traps:** any real key press stops the show and it waits 5 minutes (v36);
no answer on :8877 = the agent is down (do not rebuild, say it). Never leave the show running after a test: `POST /stop`.
