# Google Cloud provider (v24, 18.11.2026)

Marko: "One more radio button and a complete setup to get API enabled ... utilize these [Google Cloud free] credits" and
"a file picker for my chat box so I can send you images and files."

## What it is
The third PROVIDER radio in the CAPI tab: ANTHROPIC | OXYY | GOOGLE CLOUD. Choosing it IS the consent to spend: it pays from the
Google Cloud free credit ($225.31 on 18.11.2026 per the Billing page, expires 2.12.2026; base and expiry are the CREDIT dict in qwen_app/gcloud_chat.py), project `antigravity-cloud-offload`. The credit shown
is an estimate (starting balance minus a ledger of token prices, ~/.cache/gcloud-ledger.jsonl; `POST /api/capi/gcloud_balance
{usd}` resets the start). Code: qwen_app/gcloud_chat.py, wired into qwen_app/capi_chat.py (no process: one HTTP call per turn).

## Models (MODEL menu, per chat)
- Gemini, listed live from the Gemini API /models (text models only); default is the newest plain flash.
  Key: the AIza... line of ~/Downloads/API/CGP_free_credits_Google API.txt, read at run time; the AQ.... key is the backup.
  Never print, log or copy either key.
- Claude on Vertex AI: claude-opus-4-5@20251101, claude-sonnet-4-5@20250929, claude-haiku-4-5@20251001
  (publishers/anthropic, region global, then us-east5). Needs OAuth from Application Default Credentials
  (`gcloud auth application-default login`, done by Marko); API keys do not work there (401).

## Is Claude access pending?
The chat then shows ONE line: "Claude on Google Cloud is not ready yet: <reason>". Reasons: "no sign-in yet (gcloud auth
application-default login)" = no ADC; "access pending, Google answered 403/404 ..." = Anthropic's access form on the project
is not approved yet. Gemini works without any of that. Check: pick a Claude model, send "hi".

## Files
Paperclip button, drag and drop onto the box, paste (an image on the clipboard or a file copied in Finder); several at once; chips
above the buttons, click a chip to remove it. Images -> Gemini inline_data / Claude image blocks; PDF -> inline_data
application/pdf / Claude document blocks; text and code are inlined as text. 20 MB per file, otherwise the line
"<name> is N MB: the limit is 20 MB per file." Anthropic and Oxyy chats get the same files as Claude blocks.
Server: `POST /api/capi/send {id,text,files:[{name,mime,b64}]}`.

## Traps
- The room keeps `gmodel` (Google Cloud model) apart from `model` (Claude Code model).
- google-auth must be installed for the Python that runs Queen's backend (requirements.txt).
- Tests are tiny on purpose: one "PONG" turn costs about $0.0002.

**Queen is bypassed (v25).** CAPI chats on Anthropic and Google Cloud never touch Queen: no Queen prompt or skills, no Groq call, nothing recorded for her training (training_log.record drops anything from /api/capi/* and CAPI threads). Per-chat switch QUEEN: OFF (default) / ON in the header; OFF also makes POST /api/capi/ask (her capi skill) answer 403. This skill only documents it; Marko decided Queen is not asked or trained about this work.

**Queen is bypassed (v25).** CAPI chats on Anthropic and Google Cloud never touch Queen: no Queen prompt or skills, no Groq call, nothing recorded for her training (training_log.record drops anything from /api/capi/* and CAPI threads). Per-chat switch QUEEN: OFF (default) / ON in the header; OFF also makes POST /api/capi/ask (her capi skill) answer 403. Marko decided Queen is not asked or trained about this work.
