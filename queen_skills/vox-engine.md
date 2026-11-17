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
- v45: when a take did not land (the strip says so), one click on the menu bar item copies its text; the next click opens the menu. Takes are joined with a space (v44).

## History and the keys (v46-v47, 17.11.2026)
- F1 records an English take, F2 a Croatian take (always; AUTO is only a menu choice). Both keys are set in Settings, Typing tab.
- Every take is in History (menu bar item, History), also the failed ones, with where it landed (typed, pasted, did not land).
- To redo a take: select it in History, choose ENGINE and LANGUAGE, tick Correction and/or Styling (each with its own Claude model), press "Re-transcribe". A new version appears under the take. There are no thumbs any more.
- Test hook to open History: `osascript -l JavaScript -e "ObjC.import('Foundation'); $.NSDistributedNotificationCenter.defaultCenter.postNotificationNameObjectUserInfoDeliverImmediately('com.mantra.voicetotext.history', $(), $(), true)"`.

## Since v48-v53 (17.11.2026): everything global, corrections, suggestions
- History's ENGINE / LANGUAGE / CORRECTION / STYLING are the SAME per-language settings as the menu bar menu and Settings: changing the engine in History changes it everywhere (defaults engine_<lang>, style_<lang>, styleButtonOn_<lang>). F1 is always English, F2 always Croatian; AUTO is only a menu choice.
- Corrections without a model (TTT's): Croatian fixed from the dictionary, his names, the spelling table, what he corrected before. They come from the private repo MANTRA_CORRECTIONS (shared with TTT on the phones; pulled every 5 minutes; this Mac writes learned/mac.jsonl). Switch: Settings, Text tab, "Corrections from the shared database"; default `tttCorrections` (true).
- Try a text without the app window: "/Applications/Vox to Txt (Mantra).app/Contents/MacOS/Vox to Txt (Mantra)" --fix en "<text>" "<chat name, optional>" prints the corrected text. --sync pulls and pushes the shared database and prints its state.
- The name of the open chat (WhatsApp Web: the box says "Type a message to <name>") is spelled as the contact spells it, and given to the engine as a keyword.
- Typing suggestions: while Marko types in any app, up to three words show under the blob and in the menu bar item; Option+Space puts in the first, a click any. Switch: menu bar menu "Typing suggestions", or Settings, Typing tab; default `typingSuggestions`. Turn on: `defaults write com.mantra.voicetotext typingSuggestions -bool true` then restart the app (or use the menu). Off in password boxes and terminals. Nothing typed is stored.
- Ask what the strip would show: "<app binary>" --suggest "<letters typed>" <the two words before>. Measure it: "<app binary>" --bench-complete 20.

## Since v54-v55 (17.11.2026)
- The Croatian dictionary fix is conservative: a valid Croatian word form is never changed (checked against the spelling dictionary in ~/Library/Spelling/hr_HR.*); only clear non-words are fixed.
- Typing suggestions are re-ranked by a small local model: gemma-3-270m (file in ~/Library/Application Support/Voice to Text (Mantra)/models) run by llama-server (brew llama.cpp) on 127.0.0.1:8869, started by the app while Marko types, stopped after 10 idle minutes. Switch: `defaults write com.mantra.voicetotext localModel -bool false` (off) / true (on). Check it: `curl -s 127.0.0.1:8869/health` and the line "Local model: ..." in Settings, Typing tab. Nothing typed leaves the Mac.
