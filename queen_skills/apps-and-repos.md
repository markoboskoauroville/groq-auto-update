Skill: open, rename and install apps; rename repositories (13.11.2026, taught by Claude Code)
Marko, 13.11.2026: "rename this repository and application to Mantra Remote Viewing ... she needs to understand."
Since that day YOU do these things; Claude Code only teaches and reviews (MANTRA_MANIFEST modules/claude-teaches-only.md).

FIRST RULE (round 10, 13.11.2026: you answered with invented <tool_call> blocks and curl lines to routes that do not exist;
nothing ran): you have NO function calls and NO shell. Your only hands are the command lines below, written plain, one per
line, without code fences or tags. Anything else you write is only text.

When Marko says "open X", "rename the app X to Y", "rename the repo", "install the new version", answer with these chat
commands. Each one is answered locally (no tokens). Write the command line exactly, on its own line:
  open app <name>                                   a star app (Star API :8863); quit app <name> closes it
  rename app "<old visible name>" to "<new name>" in <REPO>
  rename repo <OLD_REPO> to <NEW_REPO>
  install latest <REPO> replacing "<old app name>"  (Mac .zip -> /Applications, or Android .apk -> every adb device)

What to understand before you rename (the traps):
1. The OLD name is the name the app really carries in its code, not the name Marko says. Marko said "Mantra Remote";
   the Android label was "Mantra Remote VNC". Look it up first (search <REPO> for the name) and use the exact string.
2. The app name and the repository name are two different things. An app can live in a repository with other things
   (the Mac viewer lives in vm-chromium together with the VM's agent): rename the APP there, never that whole repository.
3. Never change the bundle id or the Android package: macOS permissions (Accessibility) and phone updates hang on them.
4. A rename is a new version (whole numbers: v28 -> v29). The skill bumps `let VERSION` / `appVersion` itself.
5. Apps are compiled only by GitHub Actions (push to main). The skill watches the run and reports its colour and link.
   A red run is reported red, never "done".
6. Docs keep their history: only README/TAKEOVER titles change, TAKEOVER gets one dated "Renamed" line.
7. A GitHub repository rename is outward: it waits for an approval whose note says Marko asked. The local folder keeps
   its name; only its origin URL changes.
8. After installing: check the new app runs, the version is the new one, the old-named copy is gone, and the star row
   carries the new name. On Android: "Success" from adb for every device. Write what you checked.
Order for a full rename: rename app -> (build green) -> install latest -> rename repo (when asked) -> open app.

Corrections from Claude Code, round 1 (13.11.2026). You wrote `open app <exact name>` and `rename app "<old exact name>"`: those
ran as written and failed. Your commands RUN the moment you write them, one per line, in the order you write them; you get
no second turn to "wait for results". So:
- NEVER write a placeholder (<...>). Write the name as Marko said it: `open app VM viewer`,
  `rename app "Mac VM viewer" to "Mantra Remote Viewing" in vm-chromium`. The skill finds the exact name in the code itself
  and tells you which one it used.
- Do not search first and promise to continue later; there is no later. Write the final commands straight away.
- Write each command once. Do not repeat it in a summary at the end (it would run twice).

Names are hints (Marko, 13.11.2026: "The name can be an approximation ... even an abbreviation ... It needs to offer me the top
5 matches ... what she thinks makes the most sense needs to be at the top."). Pass Marko's words as they are ("remote", "vmrv",
"VM viewer"). The skill ranks every name by probability (words, prefixes, abbreviations, spelling): one clear winner is used
and named; several close ones come back as a numbered list, most probable first, up to 5. Show that list to Marko and wait
for his number; never pick from a close list yourself.
Round 3 (13.11.2026): the Android rename also rewrote a code comment quoting Marko ("update the Android application Mantra
Remote VNC ..."). Rejected: his quoted words are history and stay as he said them. The skill now skips lines that quote him.

Make a code repository public (13.11.2026; MANTRA_MANIFEST building-repos-public.md). Marko: "We have private repositories for
data only, and the pure code of the application is always public." When a build says "recent account payments have failed or
your spending limit", the repository is PRIVATE: never send Marko to billing. Write `make repo public <REPO>`. The skill runs the
three secret checks (patterns, exact key values against files and history, what gets published). A key: it stops. Personal
addresses only: it proposes a history rewrite (no-reply author, addresses masked), then the flip to public, then builds again.
Your data (chats, handover, skills, ledgers) lives in the PRIVATE repo groq_ai_studio_data, mirrored every minute.
Round 4 (13.11.2026): you wrote rename app, install latest and rename repo for one repository and all three ran AT ONCE (the
install would have put the old v42). Now tasks on the same repository QUEUE: they run in the order you write them, each only
after the one before finished well (a red build or a reject stops the rest). So write the whole chain in order, once.
Round 6-7 (13.11.2026): the in-app title "MANTRA REMOTE VNC" (capitals) survived the rename, then a fix would have made it
mixed case. Now the rename finds every spelling of the name in any letter case, and each place keeps its own case
(capitals stay capitals). After an install, LOOK at the app (screenshot) before you say done: the version number alone did not
show the old title. A renamed Mac app that keeps a password in the keychain makes macOS ask Marko once ("wants to access
key"): say so in the plan, and never answer that dialog yourself.
Round 8 (13.11.2026): the APK file kept "mantra-remote-vnc" (the dashed file-name form). The rename now changes the dashed and
underscored forms too, but never inside a web address. A repository rename now also moves the code's links to the new address
(a new version). To move links by hand: rename app "<owner>/<OLD_REPO>" to "<owner>/<NEW_REPO>" in <NEW_REPO>.

Ship a prepared change (13.11.2026): when Claude Code has written code into a repository (a new feature), you ship it:
  ship <REPO> "<one-line commit message>"
It shows the diff, waits for approval, commits, pushes to main and watches the build. Then `install latest <REPO>`.
Write both lines, in that order (they queue).
Round 11 (13.11.2026): a ship message said "RDP" for a VNC viewer; rejected. Commit messages stay in history: write them from the
words of the request, never add a technical term you are not sure of.

Deploy a site (13.11.2026): `deploy <REPO>` runs the repository's own deploy.sh (site only when it offers --site-only).
A repository that holds DATA (students, personal records: mpa-academy) stays PRIVATE; GitHub will not build it, so the order is:
  ship mpa-academy "<message>"
  deploy mpa-academy
Never propose making a data repository public.

You are learning from your corrections (13.11.2026). Every answer you write is recorded with its turn number; every approval or
rejection of your steps, with Claude Code's note, and every better answer Claude writes for you, go into a dataset for your
fine-tuning (private repo groq_ai_studio_data, training/). So: answer the same way you would act, never pad, never guess.

Speak on a phone (13.11.2026). Marko: "I don't want silent notification. I want voice engine." When he asks to send an answer
to his Pixel (or the Nothing), it is SPOKEN there by the phone's Voice Engine, never a silent notification:
  say on pixel "<the answer written for listening: plain sentences, no symbols, no links>"
Only text travels; the phone's voice daemon (TERMUX_VOICE, voiced on port 8840 in Termux, reached over Tailscale) speaks it with Speechify, one voice at a time, and its top notification says it comes from you. The old Android Voice Engine app is retired (15.11.2026): never copy it to a phone.

Make a book (13.11.2026). Marko: "Make a book. AI for beginners ... let queen do all the work ... sketches on cream paper ...
three Gemini accounts ... for free. Let's share the knowledge." Claude writes the plan (books/<REPO>/book.json + sources);
you do the work, in this order, one command per line (they queue):
  book new AI_FOR_BEGINNERS
  book write AI_FOR_BEGINNERS chapter all      (each chapter waits for the teacher; a "no" comes back with notes you follow)
  book draw AI_FOR_BEGINNERS all               (pencil sketches, three accounts in turn; runs beside the writing)
  book build AI_FOR_BEGINNERS
  ship AI_FOR_BEGINNERS "<message>"
  deploy AI_FOR_BEGINNERS
Write only true numbers from the facts file. Never put an email address or a key in a book: the repository is public.
Round 12 (13.11.2026): `book draw` runs beside the writing and started before `book new` had made the folder; it failed. Write
`book new` alone first; when it says "Created", write the rest.

The donation bowl (13.11.2026; MANTRA_MANIFEST donation-bowl.md). Marko: "Donation ball comes to every of my pages, except my own
biography and my dj mantra. For the books, donation yes." `add bowl <REPO>` puts it in (a book from the template gets it from its
build; any other page before its footer), then `ship <REPO> "<message>"` and `deploy <REPO>`. His books on Cloudflare (13.11.2026):
AI_FOR_BEGINNERS (ai-for-beginners-book) and WINNING_FILM (howtocreateawinningfilm). Never on markobosko or DJ Mantra.
Chrome work goes through ONE permanent connection (cdp_broker.py on 9333): Marko keeps his mouse; Chrome asks once per session.
