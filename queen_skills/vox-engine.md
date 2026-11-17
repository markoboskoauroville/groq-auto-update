# Vox to Txt (Mantra): switch the engine for a language

Vox to Txt (Mantra) is Marko's Mac dictation app (bundle com.mantra.voicetotext, since 17.11.2026 v39; before that "Voice to Text").
Its engine is chosen per language: EN, HR, or AUTO (AUTO uses the Croatian column's engine).

Switch it (no mouse, the app must be running):
1. Notification, the same call the pill's dropdown makes:
   osascript -l JavaScript -e "ObjC.import('Foundation'); $.NSDistributedNotificationCenter.defaultCenter.postNotificationNameObjectUserInfoDeliverImmediately('com.mantra.voicetotext.engine', $(), $({lang:'en',engine:'groq_turbo'}), true)"
   lang: en, hr or auto. engine: parakeet, whisper, groq_turbo, groq_v3, cloudflare, gemini, deepgram, assemblyai, speechmatics, google_v1, google_chirp, soniox, elevenlabs.
2. Check: `defaults read com.mantra.voicetotext hearLang` and `defaults read com.mantra.voicetotext engine_en` (engine_hr for hr and auto).
3. Show the list for a photograph: notification com.mantra.voicetotext.enginemenu with object "6" (seconds open).
4. By hand: the [ENGINE] button on the pill, between the language and the text mode; best engine first.
Soniox and ElevenLabs are paid: only switch to them when Marko names them. Never touch keys.json.
Test a take without voice: "<app>/Contents/MacOS/Vox to Txt (Mantra)" --hear <engine> <file> en --only

## Since v40-v42 (17.11.2026)
- By hand: the menu bar item's menu (click it): History on top, English / Croatian / Auto, then the **Engine** submenu (best first; a pick switches the engine of the language ticked above), then Correction and Styling.
- Engine, Correction, Styling and the text mode are remembered PER LANGUAGE: defaults keys engine_en / engine_hr / engine_auto, style_<lang> (off or haiku/sonnet/opus), styleButtonOn_<lang>, textMode_<lang> (none, correct, style, style_correct). Changing one language never changes the others.
- By AX: press the status item (System Events, process 'Vox to Txt (Mantra)', menu bar 1, item 1), then menu items by index (separators count).
- Dictation only inserts at the cursor, never replaces text (v43).
