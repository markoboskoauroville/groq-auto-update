# Groq Queen AI Studio (Mantra)

Queen is Marko's AI assistant on Groq (default model `qwen/qwen3.6-27b`). She answers on **http://127.0.0.1:8765**.

## One Queen, in phases (Marko, 14.11.2026)

"One Queen only, the Swift app, no Flask server behind it, done in phases."

| Phase | What | State |
|---|---|---|
| A | The Swift app serves 8765 itself. Core routes are Swift. Everything else is proxied to the Python server, now an internal backend on 8766. | **done, v5** (14.11.2026) |
| B | The hands move from Python to Swift, group by group. | next |
| C | Flask is deleted. Small Python helper scripts may stay; a Python server may not. | later |

## How it runs

**On the Mac**

- `/Applications/Groq Queen AI Studio (Mantra).app` (source `mac_app/`, compiled only by GitHub: `.github/workflows/mac-app.yml`).
- The app listens on `127.0.0.1:8765` (`mac_app/app/core/QueenServer.swift`).
- It starts `~/.groq/qwen` as its child with `QWEN_BACKEND=1 GROQ_PORT=8766`. That is the Python server, internal, no web page.
- Routes the Swift server does not have yet are passed to 8766 unchanged, streaming included.
- A plain `qwen` in a terminal now opens the Swift app. `QWEN_STANDALONE=1 qwen` runs the old Python-only Queen.

**On the Linux VM (chromium-vm)**

- Nothing changed: `queen.service` runs `app.py` alone on 8765.

## Current interface

- The Swift status line has CAPI first and AUTO UPDATE last. CAPI keeps its own chat list; the old TRIPLE/CHATS/NEW CHAT top-level choices are gone.
- CAPI supports provider-aware chats, an optional per-chat model router, folder selection, and explicit file attachments. Gemini audio/video support is limited to the MIME types documented in `CAPI_PYTHON_API.md`; other unsupported binary files are rejected.
- Google Cloud credit is a historical Billing snapshot minus Queen's estimated usage ledger, not a live balance.
- Auto Update is a chat front end for the existing backend-only update pipeline. Swift app source is built and released by GitHub Actions, not patched by that backend pipeline.
- The standard-library Python client and API boundaries are documented in [CAPI_PYTHON_API.md](./CAPI_PYTHON_API.md).

## Files Queen keeps (`~/.groq`, never in the repo)

`keys.txt`, `.env`, `key_state.json`, `spend_ledger.json`, `api_token`, `chats/`, `approvals/`, `training/`, `queen_skills/`.
Swift and Python read and write the same files in the same formats. No key is ever printed or logged.

## Install

Python side (both locations): `./install.sh` (into `~/.groq`).

Mac app: `mac_app/install.sh v30` (gh release download, quit the old copy, /Applications, sign "Mantra Apps"), then
`open "/Applications/Groq Queen AI Studio (Mantra).app"`.

More: `TAKEOVER.md` (what is where, how to test), `LESSONS.md`, `CAPI_PYTHON_API.md`, `docs/PHASE_A_REPORT.md`.
