Skill: Asana Guide builds (GitHub code mirror + Mac builder), taught by Claude Code 15.11.2026
Marko, 15.11.2026: "how to continue editing and improving my Asana guide over the cloud session" -> "yes set this up".
When Marko says "asana build status", "did the asana build finish", "build asana now", or asks what happened to the Asana Guide APK.
How it works (so you can explain it): Asana Guide (Mantra) is edited from Claude Code cloud sessions in the PRIVATE GitHub repo
markoboskoauroville/ASANA_GUIDE (code only: Kotlin, layouts, texts, pose names, tools). Images, audio, the book and the signing key stay on
Google Drive (drivegit ASANA_GUIDE). The Mac agent asana-sync (launchd, every 2 minutes) sees a new GitHub commit, merges its code into the
Drive working copy ~/Developer/ASANA_GUIDE, builds BOTH versions with Gradle (shared for Svemir, personal for Marko), bumps the whole-number
version, releases to Drive (folders LATEST shared, LATEST_PERSONAL_VERSION private), and writes the result back to GitHub (BUILDS.md and results/<sha>.md).
Your hands (chat commands, answered locally, $0), one per line, plain, no fences:
  asana build status        last builds, state, whether the agent is loaded, the log tail
  build asana now           pulls GitHub and builds now (runs in the background; ask the status after a few minutes)
Rules: never build with gradlew yourself; never put pictures, audio, PDFs, the book or keys into GitHub (the guard refuses them); never share the
personal folder LATEST_PERSONAL_VERSION. The APK is not installed on his phones by this: he installs it from Drive (the feel and the sound are his to test).
If the status shows "waiting: uncommitted code changes", a session left edits in ~/Developer/ASANA_GUIDE: tell Marko, do not discard them.
If a build FAILED the error tail is in results/<sha>.md on GitHub: give Claude Code that text; do not guess a fix.
