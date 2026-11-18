# Google Cloud provider and the file picker (v24, 18.11.2026)

Marko, 18.11.2026: "One more radio button and a complete setup to get API enabled ... utilize these [Google Cloud free] credits" and "a file picker for my chat box so I can send you images and files."

**What it is.** The CAPI tab has a third PROVIDER radio next to Anthropic and Oxyy: GOOGLE CLOUD. Choosing it is the consent to spend; it pays from the Google Cloud free credit ($254 on 18.11.2026, expires about 9.12.2026), project `antigravity-cloud-offload`. The credit number is an estimate (token prices x tokens, ledger ~/.cache/gcloud-ledger.jsonl, start in ~/.groq/capi_gcloud_balance.json; POST /api/capi/gcloud_balance {usd} resets it).

**Models.** The MODEL menu shows Gemini models listed live from the Gemini API (GET /api/capi/gcloud_models; text models only; default the newest plain flash, gemini-3.8-flash on 18.11.2026) and Claude on Vertex AI: claude-opus-4-5@20251101, claude-sonnet-4-5@20250929, claude-haiku-4-5@20251001. The model of a chat is its `gmodel`.

**Keys.** Gemini uses the AIza key in ~/Downloads/API/CGP_free_credits_Google API.txt, read at runtime (the AQ. key in the same file is the backup). Never print them. Claude on Vertex does NOT take API keys: it needs a Google sign-in (Application Default Credentials: `gcloud auth application-default login`, Marko's to do) AND Anthropic's access approval for the project.

**Is Claude access pending?** Pick a Claude model and send "hi". The chat shows one line: "Claude on Google Cloud is not ready yet: <reason>". "no sign-in yet" = no ADC; "access pending, Google answered 403/404" = Anthropic's form not approved yet (or the model not enabled in Model Garden). A real answer = ready. Nothing crashes; Gemini keeps working meanwhile.

**Files.** The paperclip in the input box, drag and drop onto the box, or paste (Cmd+V) an image or a file: each becomes a chip (click to remove), several allowed, 20 MB each (longer: "<name> is N MB: the limit is 20 MB per file."). Images go to Gemini as inline_data and to Claude as image blocks, PDFs as inline_data application/pdf or document blocks, text and code are inlined as text. Anthropic and Oxyy chats get the same blocks through Claude Code. An unsupported kind answers one line, "this kind of file is not supported". Server: POST /api/capi/send {id,text,files:[{name,mime,b64}]}; the answer lands in the chat file like any other.

**Test without the window:** POST /api/capi/provider {"provider":"gcloud"}, /api/capi/new, /api/capi/send, poll /api/capi/get?id=; then set the provider back to what it was and /api/capi/close the test chat.
