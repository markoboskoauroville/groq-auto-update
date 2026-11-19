## v30 (19.11.2026)
- The router must receive attachment metadata to assess a file-oriented task, but never the base64/file contents; its response must be a JSON object selecting only a catalog model.
- Count the router judge in the chat total as well as the provider ledger, retaining enough decimal places for a small judge call to remain visible.
- A missing paid API key must not block the Auto Update chat before its local-Claude route is tried; the backend owns the explicit consent and paid-key checks.
- Reject unknown `application/*` MIME types and malformed base64 rather than accidentally decoding an opaque attachment as text. Google audio/video MIME support must remain a provider-specific allowlist.
- Local Python checks do not compile SwiftUI. The v30 app release must wait for the GitHub mac-app workflow, then the installed app and API should be checked before processing the song folder.

## v29 (19.11.2026)
- Gemini with folder tools must receive the current turn's prepared attachments in its initial user parts; forwarding attachments only in the no-folder path leaves folder-enabled chats unable to read the files.
- Decode unknown files as text only after valid UTF-8 and control-character checks. Binary files that happen to decode (for example NUL bytes) must not be sent as text.
- Keep media MIME support explicit and provider-specific. Unsupported formats or Anthropic/pair media must produce a visible error, not be silently omitted.
- A selected folder is a working-directory choice, not a universal sandbox. Validate it on the server as an existing folder below home; describe Claude Code as using it for `cwd` and Gemini tools as folder-confined.
- A model router spends one judge call before the user turn. Record that cost, show the selected model and reason, keep it off by default, and fail visibly if the judge returns an invalid model.
- The Auto Update endpoint can publish and sync code. Its desktop chat requires explicit run confirmation and separately honors the backend's paid-API consent; its existing allowlist is backend-only.
- Swift UI is compiled by the GitHub mac-app workflow, not on this Mac; local Python tests cannot validate App.swift or AutoUpdate.swift.

## v24 (18.11.2026)
- Gemini via Google Cloud key: "Reply with exactly: PONG" -> PONG, $0.0002; a 64x64 red PNG attached -> "Red", $0.0004; 21 MB file -> "big.bin is 21.0 MB: the limit is 20 MB per file."; Claude on Vertex without ADC -> "Claude on Google Cloud is not ready yet: no sign-in yet (gcloud auth application-default login)".
- Trap: `pgrep -f "qwen_app/app.py"` inside a Bash command matches the shell's own command line and kills it; use `pgrep -f "[q]wen_app/app.py"`. Killing Queen's Python child makes the Swift app restart it within about 20 s (that is the restart).
- Trap: the backend's Python (Homebrew 3.13) is not the python3 of the shell: install libraries for it (pip --break-system-packages) and read the real ImportError.
- Trap: another session edited Capi.swift in the same minutes; always git diff before patching a shared file.

16.11.2026: GOOGLE PHOTOS ALBUM (qwen_app/gphotos_album.py, skill google-photos-album). (1) Google Photos refuses BiDi input.setFiles (InvalidStateError) like Gmail and WhatsApp: catch the file input's click with a hook and build the Files in the page (base64 -> File -> DataTransfer -> change). (2) A BiDi script that dies without session.end blocks Firefox until it restarts ("Maximum number of active sessions"); every Page ends its session in finally and closes the tab it opened. (3) Create link opens a SECOND dialog "Create link to share" with its own Create link button; an album that already has a link shows Copy link instead. (4) Once shared, the album card links to /share/...?key=, not /album/: find the album by its title element. (5) The album grid loads lazily: retry the lookup up to 15 s.

15.11.2026: TRAINING MODE hands. (1) Talk Mode's AUTO/MANUAL checkbox has NO fixed label: its AX label is its current state, so `ax-press "AUTO"` on a MANUAL app answers `no control called "AUTO"`; press the label of the current state (read state.json first) and poll state.json up to 5 s. (2) Tailscale.app's binary is the GUI unless TAILSCALE_BE_CLI=1 and stdin is /dev/null. (3) The Streaming Dashboard snapshot has no viewer count (site.viewers is null); readers of relay path santoshi is the honest number. (4) A local chat answer must keep the user's own capitals (pre-show text was lowercased until the original sentence was passed along). (5) Restarting the backend on the Mac: ./install.sh, then kill the python app.py (port 8766); the Swift app starts it again in ~20 s; the first queen call before that returns empty. (6) Public actions (go live, router set, --kill) need their own next-message "yes ..." confirm; tests only touched private paths and restored every setting (Talk Mode AUTO, engines groq_v3 en+hr, idle light show off, VPN FRANKFURT, Meditation Room quit).

# Groq AI Studio: lessons

16.11.2026: PAUSE. (1) Two processes (Swift 8765, Python 8766) must share one switch: a file ~/.groq/pause.json written by tmp+rename and read by mtime on each side, never an in-memory flag per process. (2) Cancelling a Groq stream raises an error on the line stream: check the pause flag BEFORE treating it as a broken key, or the key is cooled for nothing. (3) A held chat request is bounded (300 s), a held route is not: routes that start work answer paused at once. (4) Wrapping subprocess.Popen.__init__ covers run/check_output/call at once; wrapping urlopen needs a worker thread to be able to abandon a call in flight. (5) Pause/resume/status and the page's bookkeeping must never be gated by the pause itself.

14.11.2026 (night, cloud): PHASE A. (1) Two key pools on the same files: the Python pool kept key_state.json in memory and
wrote it back whole, so it could undo a cooldown the Swift pool had just written. Both pools now read keys.txt and
key_state.json from disk before every candidates/cool/good (groq_pool `_sync`). (2) The system prompt is not copied into Swift
by hand: a stdlib-only helper (`mac_app/tools/gen_prompt.py`) takes it out of app.py with ast and the CI test compares the
Swift prompt with Python's byte for byte; a hand copy would drift at the first skill or prompt edit. (3) Port ownership: BSD
sockets with SO_REUSEADDR only, never SO_REUSEPORT, so two Queens can never share 8765. (4) Talking to waitress from Swift:
ask HTTP/1.0 and the answer is never chunked; the proxy re-sends the request with `Connection: close` and pipes the bytes, so
NDJSON and SSE stream unchanged. (5) After a release vN, a change under mac_app/ rebuilds and overwrites the same vN: docs and
Python changes after a release stay outside mac_app/, a code change gets vN+1.


14.11.2026: WHATSAPP ON ANDROID. uiautomator says "could not get idle state" on WhatsApp until the animations are off (window/transition/animator scale 0; the door re-applies them after every Android restart), and a failed dump leaves the OLD file: always rm it first, never reuse it. A tap that missed the search bar opened Snoopy Badjan's chat and the name was typed into his box (and a test pasted text into Svemir's box): type only after checking that the field you mean is open, end every test with clear and a look for "Draft:" rows. Unread counts live in content-desc ("14 unread messages"), not text. `adb input text` cannot type č ć š đ ž: the clipboard helper watext.dex + KEYCODE_PASTE can.

14.11.2026: THE WHATSAPP DOOR. (1) Rules alone planned "show me the last messages from Svemir" as a screenshot; Claude corrected it to read {chat}, and the lesson now plans it right first (plan_by_lessons), with no duplicate lessons when two phones ask at once. (2) wa_remote's span[title] matched message previews too, so "Svemir" gave nine choices: chat titles are [data-testid=cell-frame-title] only. (3) An open Archived panel covered the search box and a click opened a wrong chat: the box must really be visible (Escape closes a panel) and a wrong header stops. (4) A door started Firefox inside its own cgroup, so restarting the door killed WhatsApp: Firefox starts in its own systemd scope, KillMode=process. (5) vm-whatsapp opened two WhatsApp tabs (home page + URL), which fight ("open in another window"): one tab only. (6) WhatsApp Web calls: browser support can be met in Firefox (Chrome UA + COOP same-origin for SharedArrayBuffer) but calling is a per-account server flag (enable_web_calling); do not chase it with browser settings.

13.11.2026: SPEAK WAS DEAD. The voice engine answers {"ok": true, ...}; six proxy routes did jsonify(ok=ok, **res), a duplicate
  keyword, so every Speak was a 500, and the page swallowed the error (its status sat in the Tools tab). Now {**res, "ok": ok}
  and a failed Speak shows a red message where Marko clicked.

13.11.2026: ONE TAB. Every restart opened another Chrome tab (Marko: "please don't open Grok in 155 tabs. Always open Grok in
  one tab"). QWEN_NO_BROWSER existed and was forgotten; now the server opens a tab only when no Queen page reconnects within
  8 s of the start. Proven: restart -> "a Queen tab is already open: no new tab", Chrome still one tab.

13.11.2026 (Queen's first renames, ten correction rounds; each one is now a test or a skill line)
- Queen's chat commands only ran when typed by a person; her answers could not act. Now a command line in her answer runs.
- She wrote placeholders (<exact name>) and they ran; she promised to "continue when the search answers" (there is no second turn).
- She fired rename, install and repo rename at once: tasks on one repo now queue, a failure stops the rest.
- Short names: the old app name, the install's "replacing" name: every name goes through best_name (probability, top 5 when close).
- Exact text replace missed "MANTRA REMOTE VNC" (capitals) and "mantra-remote-vnc" (file name); then a fix made capitals mixed
  case; then the underscore form changed a GitHub link into a repo that does not exist. Each place keeps its case; addresses move
  only by owner/repo.
- A Claude Code edit deleted the line that applies the rename (a plan with only a version bump): hence test_rename_skill.py
  gating install.sh, and "a version bump alone is not a rename".
- Once she answered with invented <tool_call> / curl blocks: her skill now opens with "you have no tools but the command lines".
- A renamed Mac app that keeps a keychain password makes macOS ask Marko once ("wants to access key"); tell him in the plan.
- A GitHub job "not started because recent account payments have failed" = the repo is private. Code is public (after three checks).

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
- Google Gemini / Cloud API keys in `~/Downloads/API/` come in two shapes: `AIza[0-9A-Za-z_-]{20,}` AND `AQ\.[A-Za-z0-9_.-]{20,}` (from `KEY_RING_TESTER`); matching only `AIza` misses `AQ.` keys.
- Multi-file surgical updates (`app.py` + `index.html`) need `max_tokens >= 16000` (not `4096`) and must include `#sidebar` + `app.py` imports/globals in `build_surgical_context` so the external model never truncates JSON or guesses helper names.
- Never include "orphan" landmarks in `build_surgical_context` whose line numbers are not inside the provided verbatim code slices: if a model sees `L946: @app.post("/api/keys/clear")` in a landmark header without lines 946-951 in the excerpt, it will guess the function body and fail strict `search` matching. Filter landmarks strictly to excerpted windows and include a unique decorator-block fallback + 1-round self-heal loop.
- When an LLM updates an existing function surgically, it may emit two overlapping `replace` edits on the same function (`L957` and `L961`), causing Edit #2's `search` anchor to fail or corrupt indentation after Edit #1 mutates the lines. Enforce `ONE edit per function` in the system prompt, add whitespace-normalized multi-line matching in `_find_normalized_span`, and inject exact line-numbered context into the self-heal prompt.
- Google's `models/gemini-2.5-flash` returns HTTP `404` (`no longer available to new users; use models/gemini-3.8-flash`) on newer Google API keys even when `GET /models` lists it; always try `models/gemini-flash-lite-latest` / `models/gemini-3.8-flash` and follow `use (models/...)` hints on 404 in Key Tester.
- **12.11.2026, `install.sh` copies files by name.** `qwen_app/brain.py` was written, `app.py` imported it, and the
  routes 404ed because install.sh never copied it to `~/.groq`. Any new file in `qwen_app/` must be added to the `cp`
  line in install.sh in the same commit.
- **12.11.2026, the pricing table was two generations behind.** It knew `claude-sonnet-4-5` (deprecated, retires
  30.11.2026) but none of the current models, so every auto-update cost was priced at the default. Extended with
  Fable 5.2, Opus 5.5, Sonnet 5.5, Haiku 5.5 and the rest, and the active model moved to `claude-sonnet-5-5`.
- **12.11.2026, Queen passes the gate now.** `verify ~/Developer/groq_ai_studio/qwen_app` is CLEAR. It was not: the
  first run reported 18 errors, all of them false - unused imports counted as defects, and macOS tidy from 2006
  calling `<main>` and `<svg>` errors. The checker was wrong, not the code.
- **12.11.2026, install.sh named its files one by one, and that bit twice.** `brain.py` and then `model_router.py`
  were written, imported by `app.py`, and silently absent from `~/.groq`, so their routes 404ed. Now it copies
  `qwen_app/*.py`. A list of filenames in an install script is a trap that springs on the next new file.
- **12.11.2026, naming the exact mistake cures it.** Queen failed the same three Chrome manifest checks three times
  out of three. Writing those three mistakes into her system prompt, by name, took the ladder to 7/7. The cost of
  the longer prompt is real: the same run went from $0.013 to $0.101 on qwen3.8-27b, which is why the model router
  now sends that work to gpt-oss-20b at $0.0108.
- **12.11.2026, `bool({})` is False.** My own grader marked `"action": {}` - which is correct and complete - as a
  missing key, and blamed Queen for it. Test for the KEY, not its truthiness.
- **12.11.2026, the server that looked alive.** `create_server()` binds the socket before `run()`, and `run()` was
  wrapped in `except Exception: pass`. Queen printed "LIVE", held port 8765, and answered nothing. The real cause was
  thread starvation: `threads=8` with one long-lived `/api/events` stream per open page, and a NEW browser tab opened
  on every restart. Never swallow a server exception; never let unbounded long-lived streams share a small pool.
- **12.11.2026, the benchmark that measured itself.** `/api/remote/send` appended every turn to `active_messages`, so
  each task carried all the earlier ones: costs grew down the list and a model benchmarked later paid for the one
  before it. Worse, a model could read its own earlier correct answers as worked examples - which is why the
  "cure" first looked like 7/7 and was 3/7 on clean turns. Independent work needs `fresh: true`.
- **12.11.2026, no token cap.** With none sent, Groq's default cut the hardest answer off mid-thinking: 8 KB of
  reasoning, no closing tag, no code. `MAX_OUTPUT_TOKENS` now gives room to think AND answer.
- **12.11.2026, do not read the model's thinking as its output.** qwen emits `<think>...</think>` and quotes the
  requested output format inside it. The harness saved that prose as `content.js` and reported a broken file when the
  model had correctly reasoned "only manifest.json is needed". Strip the thinking first; when a filename repeats,
  keep the last block.
- **12.11.2026, rules are weaker than an example.** Naming the three Chrome mistakes in the system prompt fixed them
  only while the channel was feeding the model its own earlier answers. A short worked example of a complete correct
  extension did the real work.

12.11.2026, the rule that outranks the rest: teach Queen
- Marko: "Every time I ask you to do something through Queen, you need to teach her, you need to write a skill so next time
  if I ask directly, she's able to do it without you." Claude Code finding the way once is fine; leaving the way only in a
  Claude transcript is not. Every task ends with `queen_skills/<name>.md` + its route/chat command + a test through her chat.
- Her model only writes text. A skill that needs action needs a route (her hands), not just a paragraph in her prompt.
- Her eyes lie in a specific way: asked "is the whole band here?", Qwen 3.6 said yes to concerts/img/10.jpg, an AI
  illustration with other people in it. A count is not an identity: compare against a verified reference photo.
- Groq lists no Llama-4/vision model on this account, but Qwen 3.6/3.8 take image_url and see well (counts, instruments,
  left-to-right). Nothing had to be enabled: /api/vision/ask.
- 12.11.2026, the hub's SessionEnd hook `exit_all.sh` killed Queen: it ends the shell above `claude` when a session closes, and
  for a headless `claude -p` started by Queen that "shell" was Queen herself (SIGTERM, then SIGKILL a second later: no log line).
  Fixed in the hook: never for a -p/--print run, and only a real shell (zsh, bash, login...). Same cause as a nested
  `claude -p` in a Claude Code Bash tool dying with exit 144.
- A headless Claude still reads Marko's CLAUDE.md and tries to speak every answer (langsay). --append-system-prompt alone
  did not stop it; removing Bash (--disallowedTools Bash) for plain questions did.
- `--bare` would skip the hooks, but it accepts only ANTHROPIC_API_KEY (never the claude.ai login): that is API credits. Not used.
- One headless question costs about 70k context tokens of the plan (hooks + CLAUDE.md) and 3-10 s; no API money.
- 12.11.2026, posters: a colour's alpha is ignored by a shape's brush fill; transparency is `doc.setOpacity(value, node)`.
  Text colour is `StoryDelta.createBrushFill(FillDescriptor.createSolid(colour, BlendMode.Normal))`; centring is
  `StoryDelta.createAlignX(ParagraphAlignXType.Centre)`; Affinity's enums are native objects (JSON.stringify shows
  nothing: list them with Object.getOwnPropertyNames).
- A text band on the top of a stage photo covered every face: the band sits where the faces are not, which only her eyes
  can tell (people_top / people_bottom / free_area).
- Text overflowed the page (text_end 1256 on a 1200 px page): sizes are fitted to the band and each line to the width.
- Two images in one question (reference + candidate) confused Qwen ("a collage", 7 counted where 6 were). One image with the
  seven described people answered right on all four test photos.

12.11.2026, evening: Gemini by DevTools, the traps (each one cost a failed run)
- Chrome asks "Allow remote debugging?" for every new DevTools client; unanswered, the connection times out (30 s) and the
  skill failed. Now Macro Recorder presses Allow in natural motion while (and only while) Queen connects
  (MACRO_SKILLS tools/chrome_allow_debugging.py, catalogue chrome-allow-remote-debugging). Proven unattended.
- A skill exception fell through to the model, which answered "This will take a few minutes ... 🎨". Failed skills now
  answer with the error. Never let the model cover for a tool.
- Gemini ignores a synthetic paste AND a synthetic drop. What works: trusted DevTools clicks on "Upload and tools" ->
  "Upload files", Page.setInterceptFileChooserDialog, DOM.setFileInputFiles on the chooser's backendNodeId.
- That menu never opens in a background tab until Emulation.setFocusEmulationEnabled(true): the tab then behaves as
  focused, nothing comes in front of Marko.
- DevTools creates tabs only in Chrome's DEFAULT context = the profile whose window opened last. A profile is chosen by
  opening its window (open -na ... --profile-directory=X); every tab of that window is closed afterwards, or the profile
  stays the default (father.aya's ad-blocker "Updated" page kept it so).
- Saving a poster over a file that is open in another Affinity tab fails silently (~lock~): new names get whole-number
  versions (v2, v3), and existing versions are skipped unless force.
- Affinity scripts may touch the Desktop only (Pictures denied, even through a symlink): stage on the Desktop, keep in Pictures.
- Gemini's picture came back 765 x 1024: enough for screens, soft for print. For print, ask Gemini for "high resolution" or
  upscale outside Canva's paid tools.
- 12.11.2026, supervised website work: her first captions said "cloudy dawn" for a 12:45 photo, wrote "Bačinskoj uvali" (wrong
  Croatian) and named a ridge and bay she could not see. Rejected; the skill now gives her the capture time from the file and
  forbids unverifiable place names; the supervisor's approval note can correct the words without restarting the task.
- The site repo had moved on (v4, another session's work) and my local copy was behind: the skill pulls first and refuses to
  work on top of uncommitted changes.
- 12.11.2026, self-check on the live page: the first screenshot was blank (viewport coordinates given to a page-coordinate
  clip) and her eyes still answered "different framing". A blank capture is now caught by size before she judges; the second
  capture showed the panorama and she said "identical scene and framing" (true).
- 12.11.2026, the tabbed interface: the pop-ups (Star, Voice, Elevate, GitHub, Billing, Settings, Keys, Persona, Self-update)
  were MOVED into tabs with their ids, and openModal()/closeModal() switch tabs; each tab runs the old buttons' load code on
  arrival (the Star card said "Loading..." until it did). The auto-update split opens the Auto-update tab instead.

13.11.2026, Queen reads the screen
- First lie: Voice Engine idle, but a terminal's white text sat in the subtitle band and she quoted it as "subtitle text" (even in
  invented broken lines). Fix: the question now defines a subtitle (orange, centred, large, spoken word red; window text is not one) and the
  skill says so. After the fix: 4 negatives and 6 positives right (no reading playing = "no subtitle on screen"; playing = exact sentence).
- The Voice Engine's phase flips between sentences ("making"): ask only while GET /speaking says playing; truth = its "sentence".
- Cropping the band makes the negative easy; a whole-display question was tried too and also answered right.
- Her python venv has no Quartz/PIL: the window list runs in /usr/bin/python3, resizing in sips, blank check by file size.

## Two locations (13.11.2026)
- The VM has no `rsync`: shell scripts there use `cp -p` with `-nt`. macOS `cp` has no `-u`, so the same script tests `-nt` itself.
- A second Queen with `data_sync.py` unguarded would mirror its own empty chats over the Mac's data repo (rsync --delete): any new location needs a guard first.
- Her Mac skills (read-screen: "display 1 = BenQ") bleed into answers on the VM: a skill true on one machine only must say so in its first line.
- Non-interactive `ssh host cmd` has no ~/.local/bin on the PATH: put the export at the very top of ~/.bashrc (Ubuntu's returns early when not interactive).

## 14.11.2026: the WhatsApp machine on the VM
- The VM's Firefox (profile ~/.config/vm-firefox, class VMFirefox) is WhatsApp only: `vm-whatsapp start|status|qr` (vm-chromium/desktop),
  BiDi on 127.0.0.1:9223 like the Mac, home page web.whatsapp.com in user.js. Queen: `open whatsapp`, `whatsapp status`, `whatsapp qr`,
  `whatsapp: <request>` (qwen_app/whatsapp_machine.py, VM only), skill queen_skills/whatsapp-machine.md. Tested through `queen` on the VM,
  from a closed Firefox too.
- The hands on the VM are the Mac's: a sparse clone of claude-code (tools/wa_remote.py) and firefox-control (firefoxctl), both pulled by
  two_locations_sync.sh on Linux only. wa_remote used `sips`: now ImageMagick on Linux.

## 14.11.2026: Accessibility instead of screenshots (Swift app + WhatsApp)
- WhatsApp Web hides its ticks from Accessibility (`<span aria-hidden="true"><svg><title>wds-ic-read`): "the last message is Marko's" is
  not a word in the tree. The icon still takes ~20 px, so the preview text starts ~20 px right of its group: that offset (AXPosition with
  `frames`) is the tick. Checked against the DOM (BiDi, cross-check only): Yhshai (tick) yes, four incoming rows no tick, all right.
- "You reacted 🙏 to: ..." is Marko's; "X reacted ..." is X's; groups put "~Name" ":" "text"; communities put the community name in a
  separate group of the row (Udruga Ethno Hrvatska > Etno orkestar Zagreb) with the time: the first parse took the community group as the
  preview and lost the time. Pinned chats sit at the top: sort by the time, never by the list order. The list is virtual: the same row can
  appear twice (dedupe by name+time+text).
- Firefox's AX tree has only windows on the current Space and only the selected tab; the web area's name is in AXDescription, not AXTitle.
- A private code repo cannot build on GitHub (billing): the Mac app went into this public repo (mac_app/, its own workflow with a paths filter).
- The Swift app was tested through Accessibility too: axread on the app's own window, AXValue set on the field, AXPress on Send.


- 14.11.2026 (v3): renamed to Groq/Queen AI Studio (Mantra). A '/' cannot be in a file name, so the bundle is `Groq Queen AI Studio (Mantra).app` and CFBundleName/DisplayName, window title and APP_NAME carry the slash. Bundle id community.auroville.groqaistudio kept (permissions, updater). The updater finds the asset `app.zip` and the bundle by the running bundle's file name, so v1/v2 (old file name) cannot self-update to v3: install by hand once. The leftover repo GROQ_AI_STUDIO_MAC is kept on GitHub, unused; its local folder was deleted.

- 14.11.2026: asked to set the Mac volume, Queen invented an endpoint (/api/system/volume) that did not exist. A missing hand is built (route + local
  chat command + skill), and her answer is the read-back value, not the number requested. The output device is never changed.

- 14.11.2026 (v4): the app shipped v1-v3 without an icon; no Swift app ships without its icon row + icon/six_1024.png + CFBundleIconFile (six-letter-icon.md). Render with icons6/six_icon.swift for ONE key only, then `git checkout icons6/out/sheet.png` (it overwrites the contact sheet with one icon).

## 14.11.2026: open-settings-pane
Queen said "Done" after a bare `open x-apple.systempreferences:` that landed on "Accessibility". Now `/api/system/settings?pane=` (qwen_app/system_settings.py) opens, fronts, reads the window title via System Events and retries once; ok only when the title matches. The title follows the system language here ("Control Centre"), so titles compare with centre = center. Skill: queen_skills/open-settings-pane.md.

15.11.2026, NDI monitor: the source is picked by the menu bar (AX), and the window title only follows a frame, so "confirmed" is honest only for a sending source; Queen says so and points to a screenshot. Restarting: killing the Python backend did not bring it back (the Swift app was not running); started `~/.groq/venv/bin/python qwen_app/app.py 8765` by hand.

- 15.11.2026: Asana Guide builder hand (chat_asana in ops_hands.py, skill asana-guide-sync.md): "asana build status" / "build asana now", $0, local; tested in her chat (status). Bridge: ~/Developer/ASANA_GUIDE/mac/asana_sync.py.

15.11.2026, teaching round: `/api/remote/send` goes to the MODEL, not the local chain. A test of a local phrase there costs about $0.02 per turn and the model invents tool calls it does not have. Test phrases with `/api/internal/local_command` (token in X-Queen-Token). Bare words ("record", "keep", "stop") are answered only while the app they belong to is running, otherwise they fall through to the model.

## 16.11.2026: Firefox port and the name Queen (v6)
- Her WhatsApp/Firefox route forced port 9223 (whatsapp_ax.py, whatsapp_remote.py); Firefox (firefoxctl) now listens on 9222 and
  nothing answered on 9223 ("Firefox is not listening on 127.0.0.1:9223"). qwen_app/ffport.py asks lsof which process holds 9223/9222
  and returns the one Firefox holds (Chrome's cdp_broker may hold 9222), checked on every call; wa_remote.py tries env, 9223, 9222.
- Rename: Marko, 16.11.2026: "rename the Groq Queen to be Queen". Mac app is now `/Applications/Queen.app`, shown "Queen" (window,
  top row, menu, API text); v6. Repo, folders, bundle id and the `qwen` command unchanged.

## 17.11.2026: WhatsApp contact names
Skill queen_skills/whatsapp-contact-names.md: the contact is the spelling authority (Vasil -> Vasyl Ros, greeting "Bok Vasyl,"); tool wa_type.py --find; tested by asking her in her chat, answered Vasyl Ros / Vasyl.

## 17.11.2026: TRIPLE CHAT (v9)
Marko: one room with himself, Queen (Groq) and Claude; everyone hears everyone. Backend qwen_app/triple_chat.py (/api/triple/*, rooms in ~/.groq/triple/), window mac_app/app/Triple.swift (word TRIPLE). Claude via the local Claude Code first; unreachable -> consent question, YES switches the room to API (`resume` turn, no duplicate message). Queen's `ASK CLAUDE:` line is answered in the room (max 3); Claude's `ASK QUEEN:` runs only on the ASK QUEEN button. Built without tests (Marko tests by hand). Trap: Claude models have no rate in get_model_rates, so spend is booked at a fallback rate. Skill queen_skills/triple-chat.md.

## 17.11.2026: CAPI tab (v11) + speaker
One chat module: MessageList + Bubble + MarkdownView + SpeakerButton serve normal chat, TRIPLE and CAPI. CAPI = qwen_app/capi_chat.py running `claude -p` stream-json on the 100dolara key, ledger via claude-code/tools/api_credit.py (ONE credit number). Speaker = qwen_app/speak.py (langsay --out, cached) + Speaker.swift. Trap: Macro Recorder mouse clicks did not reach the window; `macro ax-press Queen <label>` and System Events keystroke worked. Skill queen_skills/capi.md.

- 18.11.2026 (v17): sorting a list by "updated" makes it jump on every answer; a list the user thinks of as "newest first" is sorted by creation time with a stable tie-break. Oxyy: /v1/models lists only what THIS key may call (the website lists 130+); non-Claude models answer only on the OpenAI route (/v1/chat/completions), not /v1/messages; no balance endpoint, so a local ledger from a starting balance. Test with one call (max_tokens 5) and read /v1/models first.

- 18.11.2026 (v18/v19): an HStack of Text breaks letters when the window is narrow; use .lineLimit(1).fixedSize(horizontal: true) + FlowLayout. A fixed .frame(width:) pane next to a minWidth pane overflows and cuts its left edge at the minimum window width: give it minWidth + idealWidth/maxWidth so it squeezes. A 1 pt Rectangle overlay is not in the AX tree: drag-test the divider with cliclick (dd/dm/du) and read the saved default.

- 18.11.2026 (v20/v21): a separator inside a group's HStack is left at the start of a wrapped row; make the pipe its own layout child tied to the next one, and hide it when the pair starts a row. Several buttons that must wrap together (the four tabs) are one HStack unit. Screen-capture from `open -a Queen` can land the window on another screen: capture by window id, never the screen.

- 18.11.2026 (v22): "floating text" = items in a row aligned by top/centre. Use baselines: HStack(alignment: .firstTextBaseline) and, in a custom Layout, ViewDimensions[.firstTextBaseline]. An Image has no text baseline: use Text(Image(systemName:)). Never remove a control that was only to be moved (CHATS in v20). Verify by cropping and zooming the screenshot.

- 18.11.2026 (v23): a SwiftUI TextField(axis: .vertical).lineLimit(1...8) caps the box; for an unlimited, resizable box with a scroll bar use NSTextView in NSScrollView (legacy scroller). A drag test with cliclick needs the window active first: the first mouse-down on an inactive window only activates it. Queen has two AX windows (an empty-named 37 pt one and "Queen"): `set size of window "Queen"`, not window 1. AX cannot set a text view's value here: click in the box, then Edit > Paste through System Events.

## v24 (18.11.2026)
- The Python backend Queen runs on is Homebrew 3.13 under the Swift app: a library installed for the shell's python3 is not there. Check with that interpreter (the Python.app binary in `ps`), install with pip --break-system-packages, then kill the backend child (the Swift app restarts it within 20 s). A kill right after pip once still showed the old "not installed" line: retest after the new pid.
- Vertex AI refuses API keys (401 "API keys are not supported"): Claude there needs ADC plus Anthropic's access; a missing sign-in is a plain "not ready yet" line, never a stack trace.
- The CAPI "main chat" is Swift (Capi.swift) over capi_chat.py, not index.html: provider radios and the file picker live there, and the Swift part is compiled only by the mac-app workflow.

## v25 (18.11.2026)
- pgrep -f on this Mac did not find the Queen backend although it ran (lsof -iTCP:8766 finds it): kill by the pid from lsof, the Swift app restarts it within 20 s.
- A brief's "about 16:30" can be later than the Mac clock (16:14): anchor a credit base to a time that has passed, and say so.

## v26 (18.11.2026): MASTER / SLAVE
- A Claude Code run started by Queen still reads Marko's global CLAUDE.md and its hooks: a slave ran `langsay` (spoke aloud) and its final `result` was a note about that speech job, not the REPORT. In a pair: tell it it is headless (no voice, no other sessions, last message = the full answer), block `Bash(langsay:*)`, and never trust `result` blindly: pick the text that carries REPORT / VERDICT / SLAVE_MODEL (pair_chat.pick_answer).
- The review loop catches a bad report by itself: the Gemini master answered VERDICT: FIX to the side note and round 2 was right. Keep the verdict machine-read (last `VERDICT: DONE|FIX` line wins, markdown around it ignored; none = FIX, flagged).
- `claude --tools` and `--disallowedTools` are variadic: give the prompt on stdin, never as the last argument after them.
- Gemini function calling: send the model's parts back verbatim (thought signatures), answer every functionCall in ONE user turn of functionResponse parts (with the call's id when there is one).
- STOP of a Claude run has no result event, so its partial cost is unknown: say so, it is booked $0.
- Model choice by the master: give it the list with tier and price, parse `SLAVE_MODEL:` leniently (a near name maps to the listed id), an unknown id falls back to the cheapest with a visible note; check a step up against what is left of the cap before the round.
