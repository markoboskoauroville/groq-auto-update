# Skill: vtt-engines (Mac; local, no model, $0)

Marko, 15.11.2026 (training mode). **When:** "which engine", "which engine for hr", "use engine whisper", "use engine deepgram for hr", "engine ranking".
**What:** Voice to Text (Mantra) v31 local API on 127.0.0.1:8865: `GET /engines` (id, label with time and stars, `selected_en`, `selected_hr`, `available`, `stats_en/hr.quality_pct`),
`POST /engines/select {"id","lang":"en"|"hr"}` (same as a card in its Settings), `GET /status` (`engine`, `language`).
**Steps (code: ops_hands.py `chat_engine`):** "which engine" = the selected label for en (hr if asked) and the other language. "engine ranking" = available engines sorted by quality %,
then median seconds, unrated ones listed last. "use engine <name>": match the id or the label's first word; exactly one hit, must be `available`; select; READ BACK `/engines` and say the new label.
Default language en (English only with Claude); hr only when Marko says hr / Croatian.
**Traps:** the app not running = say so (nothing on :8865), never start a second Whisper; ids: parakeet, whisper, groq_turbo, groq_v3, cloudflare, gemini, deepgram, assemblyai, speechmatics,
google_v1, google_chirp, soniox, elevenlabs. Names are hints: 2 hits = list the top 5, ask.
