# Gemini 404: a dead model is replaced, never a dead end (v27, 19.11.2026)

When a Gemini model answers `404 ... no longer available / not found / models/...`, the CAPI pair (master or slave) does not stop:

1. The model the error names (`models/<id>`, if different) is used instead.
2. Otherwise `ListModels` is asked and a model with `generateContent` of the same tier is taken (pro, flash, flash-lite), else the next lower tier.
3. The replacement is remembered for the rest of the run, a notice line `404: <old> is gone, using <new>` goes into the chat, and the cost is booked on the model that really answered.
4. If no replacement exists, or the replacement also fails, the run ends with `404: <old> is gone, and no replacement was found`.

Code: `qwen_app/gemini_hands.py` (`_find_replacement`, `_call_with_recovery`), used by `text_turn` (master) and `agent_turn` (slave). `gemini-2.5-pro` was retired and is out of the curated list and prices.
When Marko says a Gemini model "does not work" or "is gone": first look for this notice line in the chat before changing anything.
