---
name: groq-ai-studio
description: Groq AI Studio, Marko's local browser chat for the Groq API (command `qwen`, repo groq_ai_studio, installed in ~/.groq): key pool with failover, spend ledger, Code Box, GitHub reader, backdoor API on port 8765. Use for ANY qwen command / Groq chat app / Groq key pool / groq-cli / Groq AI Studio task.
---
# Groq AI Studio

Read `TAKEOVER.md` in the repo first: it holds everything known (files, commands, HTTP API, dangers, what is untested).

## Space
- Source: ~/Developer/groq_ai_studio (public, no README by rule). Running copy: ~/.groq (`./install.sh` copies source there).
- Start: `qwen` (port 8765, first free port after it; `~/.groq/app_url` says which). Health: `curl http://127.0.0.1:8765/health`.
- Keys: ~/.groq/keys.txt and ~/Downloads/API/groq-api.txt: never print, never commit. Masked form only.
- Test a turn without the browser: `curl -s -X POST http://127.0.0.1:8765/api/remote/send -H 'content-type: application/json' -d '{"prompt":"hi"}'` (spends tokens: say so).

## Rules
1. Edit in the repo, run `./install.sh`, restart `qwen`; never edit only ~/.groq.
2. Before each commit: `grep -rn 'gsk_' .` must find nothing. State files are in `.gitignore`.
3. No Mac build (it is Python). Push to main.
4. Write every correction and new feature back into TAKEOVER.md and LESSONS.md at the close.

## Open work
Add a token or Origin check to the local API (TAKEOVER, Dangers); merge the two key pools; read real prices instead of the typed table.

## Run log
- 11.11.2026: repo created from the running v09; skill written.
