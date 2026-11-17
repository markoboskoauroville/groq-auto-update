# Skill: move-file (Mac only; on the VM it does nothing)

Marko, 17.11.2026: asked to move ~/Library/LaunchAgents/community.auroville.loginstart.plist to ~/Desktop so iTerm stops opening at login.

**When:** he asks to move a file to another place on the Mac ("move ~/x/file.txt to desktop", Croatian "premjesti ... na desktop").
**How:** the chat sentence "move <src> to <dst>" is answered locally, no model, $0. `dst` may be a path, a folder, or desktop/downloads/documents.
Route: `POST /api/system/move` with `{"src":"~/a/file.txt","dst":"~/Desktop"}` -> {ok, src, dst, src_gone, dst_exists, dst_size}.
**Check:** say the READ-BACK (source gone, destination exists, size), never what was asked. ok is true only when both are confirmed.
**Traps:** never move anything outside the home folder (the route refuses). Never overwrite: an existing destination is an error. Never delete.
Files only, not folders. A folder destination means "into it". Do not invent another endpoint (no /api/system/mv).
