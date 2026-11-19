# Queen CAPI Python API

Queen's Swift app serves the local API at `http://127.0.0.1:8765`. Its Python backend supplies the `/api/capi/*` routes. The supported client is [tools/queen_capi.py](./tools/queen_capi.py); it uses only Python's standard library and reads the optional local API token from `~/.groq/api_token` without printing it.

## Use the client

```python
from tools.queen_capi import QueenCAPI

queen = QueenCAPI()
chat = queen.create_chat(
    folder="/Users/markobosko/Developer/my-project",
    provider="gcloud",
)
chat_id = chat["room"]["id"]
result = queen.send_and_wait(
    chat_id,
    "Inspect the project and summarize its structure.",
    timeout=600,
)
print(result["room"]["messages"][-1]["text"])
```

Attach explicitly selected files with `files=["/path/to/file.pdf"]`. `send()` returns once Queen accepts the prompt; `wait()` or `send_and_wait()` polls until that chat is no longer busy. The command-line client can inspect the server and capabilities, create chats, send prompts, wait, stop, and close:

```sh
python3 tools/queen_capi.py health
python3 tools/queen_capi.py capabilities
python3 tools/queen_capi.py new --provider gcloud --folder "$HOME/Developer/my-project"
python3 tools/queen_capi.py send CHAT_ID "Run the focused tests" --wait
```

## API and safety boundaries

- `GET /api/capi/capabilities` describes providers, attachment limits, workspace behavior, routing, and the current Google Cloud credit source.
- Chats use `GET /api/capi/list`, `GET /api/capi/get?id=…`, `POST /api/capi/new`, `POST /api/capi/settings`, and `POST /api/capi/send`. `POST /api/capi/start`, `/stop`, and `/close` manage a chat process/history.
- A selected working folder must already exist below the user's home directory; the home directory itself and paths outside it are rejected. The folder becomes the Claude Code working directory. Gemini's file and shell tools are separately confined to that folder; choosing a folder is not a general sandbox for Claude Code.
- Images, PDF, text, and code are supported within the per-file size limit. The current Gemini audio allowlist is `audio/flac`, `audio/m4a`, `audio/mp3`, `audio/mpeg`, `audio/mp4`, `audio/mpga`, `audio/ogg`, `audio/pcm`, `audio/wav`, `audio/webm`, and `audio/x-aac`. The video allowlist is `video/3gpp`, `video/mp4`, `video/mpeg`, `video/mpegs`, `video/mpg`, `video/quicktime`, `video/webm`, `video/wmv`, and `video/x-flv`. These are based on Google's [audio understanding](https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/audio-understanding) and [video understanding](https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/video-understanding) MIME tables; model and endpoint limits still apply. Audio/video are not sent through Anthropic/Oxyy or pair mode; unsupported binary formats return an error rather than being treated as text.
- The optional per-chat model router is off by default. When enabled, the selected provider's cheapest catalog model judges the task, then Queen routes to the least expensive suitable model in that catalog. Its chosen model, reason, and router cost are returned by `/api/capi/send` and recorded in the chat. A routing failure is surfaced; it does not silently fall back.
- Google Cloud credit is an estimate based on a dated Billing snapshot and Queen's token-price ledger, not a live remaining-credit value.
- The separate Auto Update tab uses `/api/auto_update/*`. Its current surgical-patch allowlist is backend-only (`qwen_app/app.py`, `qwen_app/index.html`, and `qwen_app/auto_updater.py`); Swift app source is built and released by the GitHub mac-app workflow. A run requires an explicit UI confirmation, and a paid API route requires a separate consent when the backend requests it.

Run the offline client tests with `python3 tools/test_queen_capi.py`; CAPI media/router tests run with `python3 qwen_app/test_capi_features.py`.
