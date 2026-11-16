# Skill: skeleton (Mac; local, no model, $0)

Marko, 16.11.2026: "I want to have one swift app, we call it skeleton, which will just look at my image from any camera I choose and follow me with the skeleton."
**When:** "open skeleton", "start skeleton", "show me the skeleton", "skeleton on the Sony / FaceTime / Iriun".
**What:** Skeleton (Mantra), /Applications/Skeleton (Mantra).app (repo SKELETON): any camera, a skeleton drawn on the body, pose matching (green / yellow / red),
RECORD (key R) and Render Mannequin through Blender.
**Steps:** write the plain command line `open app skeleton` (a star app, Star API :8863). The app opens on the camera it had last (the popup top left
chooses another). For a named camera, ask Claude Code: `open -a "Skeleton (Mantra)" --args --camera "ILCE-7M5"` after quitting it (the argument is read at launch).
**Traps:** the first start asks macOS for camera access: that prompt is Marko's, never answer it, say "PERMISSIONS (amber, top right) shows while it is missing".
Space = full screen; the window X quits the app. Do not record video; the RECORD button only writes a skeleton file in ~/Movies/Skeleton.
