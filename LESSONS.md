# Groq AI Studio: lessons

11.11.2026
- The app was written by an agent in nine installer versions in four hours; four of those installers re-embedded the whole app in
  a heredoc (900 to 3000 lines). Source of truth is now this repo, not an installer. Never regenerate it from an installer.
- Keys must never be copied into code, an installer or this repo. The first installer read groq-api.txt and wrote keys.txt;
  from 09 on install loads nothing and keys come in through the Key Manager.
- A hard-coded personal path (`/Users/<name>/Downloads/API/groq-api.txt`) was in `app.py`; replaced by `Path.home()`.
- `groq_pool.py` and `DynamicKeyPool` duplicate the failover logic; a fix in one is missed in the other.
- `which qwen` found nothing in a Claude Code shell: the tool shell does not read ~/.zshrc. The command lives in ~/.groq, added to
  the PATH by .zshrc. Look in ~/.zshrc and ~/.groq before saying a command does not exist.
- Proving "no secret in the public repo": compare the real keys on disk against every file by exact match (without printing them),
  not only a `gsk_` pattern search; the prefix alone appears in the docs and the key parser.
- Backdoor chat test (11.11.2026, three turns, qwen/qwen3.8-27b, about 0.5 s each): each turn showed about 2,600 tokens and $0.0022
  even for a one-line greeting. Likely the hidden reasoning is counted as output; not verified. The ledger cannot be trusted
  until the token counts are checked against Groq's own usage.
- The model ignored the casual persona's spirit and said "I'm stuck as an AI" twice: a system prompt for a character needs a
  stronger line (stay in character, never mention being an AI) if street-talk tests matter.
- Public and unpromoted repository: no README, no description; the description lives in TAKEOVER.md (repo-privacy.md).
- Groq streaming usage lives on `chunk.x_groq.usage` (with `completion_tokens_details.reasoning_tokens`), not always top-level `chunk.usage`. Reading `x_groq.usage` fixed the inflated ~2,600-token estimate down to exact Groq invoice counts (e.g. 729 in / 71 out).
- `sys.path.insert(0, str(Path.home() / ".groq"))` before repo root caused `qwen_app/app.py` to import the stale installed `~/.groq/groq_pool.py` during pre-deploy CI checks; inserting repo root after `~/.groq` at index `0` ensures source-first resolution.
- `btnSend.disabled = true` during streaming prevented clicking the Stop (`AbortController`) button in `index.html`; keeping `btnSend.disabled = false` while `isBusy` is true restores one-click stream cancellation.
- In Python f-strings, backslash escapes inside `{...}` expressions (e.g. `f"...{\"key\": ...}"`) raise `SyntaxError` on older/strict AST parsers or when quotes collide; construct JSON test fixtures via `json.dumps({...})` instead.
- Full-file LLM code rewrites waste ~40k output tokens (~$0.60+) and risk truncation; pre-indexing file landmarks + keyword windows and streaming surgical `SEARCH -> REPLACE` blocks inside `<queen_update>` cuts auto-update cost to fractions of a cent while still running full `ci_run_all` AST + HTML validation on the resulting file in memory.
- Using a fixed `.tmp` suffix (`path.with_suffix(".tmp")`) in multi-threaded Waitress routes (`save_chat`, `save_auto_update_store`) causes `FileNotFoundError` when two concurrent saves rename the same `.tmp` file simultaneously; always include a random hex token or `pid + timestamp` in temporary atomic write filenames.
- macOS `/usr/bin/python3` is Python 3.9, which rejects escaped quotes inside f-string `{...}` expressions (`SyntaxError: f-string expression part cannot include a backslash`); bind dictionary lookups to local variables before formatting in shell-embedded Python snippets.
