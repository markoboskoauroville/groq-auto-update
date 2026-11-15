# Skill: stream-preshow-vm (Mac asks chromium-vm; local, no model, $0)

Marko, 15.11.2026 (training mode). **When:** "pre-show status", "start pre-show until 18:30", "stop pre-show", "stream viewers", "go live" (+ confirm).
**What:** Meditation Room (Linux) on chromium-vm (repo MANTRA_ROOM/linux) is run by `mrlinux` over `ssh chromium-vm mrlinux ...`; the Streaming Dashboard API
http://100.102.86.30:8996/api/snapshot is read-only.
**Steps (code: ops_hands.py `chat_stream`):**
- status / pre-show status -> `mrlinux status` (services, encoder state, test relay path vmtest, site LIVE or not).
- "start pre-show until HH:MM" -> `mrlinux start --preshow-until HH:MM` (Zagreb time): private test relay + encoder, the countdown card "Live stream in N minutes";
  NOTHING public. Without a time Queen asks "Until when?".
- "stop pre-show" / "stop the stream" -> `mrlinux stop` (stops live first if any, then encoder and test relay).
- "stream viewers" -> snapshot: site live yes/no and `relay.paths[santoshi].readers` count (the site itself reports no viewer count: `site.viewers` is null; say so).
- **Going public:** "go live" only runs `mrlinux checks` and says the answer; ONLY the next message "yes go live" (or "yes go live 15" = minutes, max 120) runs
  `mrlinux go-live N`. mrlinux itself refuses 11:50-13:50 Zagreb, while the site is already live, and while santoshi has a publisher: pass its refusal on word for word. "stop live" = `mrlinux stop-live`.
**Traps:** never go live in a test; the site may already be live from the cloud mixer (that is normal, then mrlinux refuses); one ssh costs a second or two; the VM is chromium-vm over Tailscale.
