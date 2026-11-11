# Groq AI Studio — Workspace Rules

## Documentation Sync (Mandatory)

After **every code change** to files in this project, you MUST:

1. **Update the handover document** — the artifact in the conversation's brain directory. Reflect the current state, what changed, and what's next.
2. **Update the skill file** at `skills/groq-ai-studio/SKILL.md` — keep it accurate with the app's current features, endpoints, and usage.

Do this at the end of every change, not deferred. If you make multiple changes in one turn, update once at the end covering all changes.

## Other Standing Rules

- **"Queen" = `qwen` = this app.** Use this terminology.
- **Keys must NEVER appear in code, commits, or repos.** Run `grep -rn 'gsk_' .` before every git commit.
- **No README in this repo** — documentation lives in `TAKEOVER.md` and the skill file.
- **Edit in `~/Developer/groq_ai_studio`, deploy with `./install.sh`, restart `qwen`.** Never edit `~/.groq` directly.
