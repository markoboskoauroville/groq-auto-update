---
name: star-menu-computer-control
description: >-
  Control Marko's Mac through the Star Menu (STAR_API on 127.0.0.1:8863), Startup
  category (~/.config/star-autostart.json & Swift Matrix), Local Voice Engine
  with on-screen subtitles (MANTRA_VOICE on 127.0.0.1:8837 & Voice Engine),
  Sound Recorder (:8869), and Blender Control (:9876). Use whenever Queen/Groq
  or an agent needs to inspect, open, quit, press buttons, or call functions on
  any Star Menu or Startup app.
---

# Star Menu, Startup Category & Computer Control Runbook

Marko's Mac runs a unified ecosystem of Swift apps (`*(Mantra).app` in `/Applications`) organized under the **Star Menu** (`Star (Mantra).app`, `~/.config/star-rows.json`) and controlled through a single local HTTP API (**`STAR_API`** on `http://127.0.0.1:8863`) plus **Queen's proxy endpoints** (`/api/star/*` and `/api/voice/*` on `http://127.0.0.1:8765`).

---

## 1. Startup Category (`~/.config/star-autostart.json` & Swift Matrix)

Managed by **Swift Matrix (Mantra)** (`/Applications/Swift Matrix (Mantra).app`) and read at login by **Star (Mantra)**:

- **ALWAYS Started at Login (`always`):**
  1. `darken` — **Screen Brightness Darkening the Screen (Mantra)** (`⌃⌥⌘F1` toggles full screen darkness)
  2. `dock` — **Dock Switcher (Mantra)**
  3. `g815` — **G815 Lights** (`community.auroville.g815lights`, paints active keyboard LED bank)
  4. `resolveactions` — **DaVinci Resolve Actions (Mantra)** (companion to DaVinci Resolve: pages on `⌥\``, HD/UHD badge, import button, stepped actions)
  5. `speechify` — **Opening and Closing (Mantra)** (opens ticked Chrome profiles at login; closes Speechify Home popup)
  6. `starapi` — **Star API (Mantra)** (invisible background daemon serving `http://127.0.0.1:8863` so every Star app is controllable via HTTP)
- **NEVER Started Automatically at Login (`never`):**
  - `chromiumvm`, `liveactions`, `mouse`, `netaggregate`, `oxi`, `spectral`, `transcribe`, `yshai`
- **LaunchAgents (`~/Library/LaunchAgents`):**
  - `com.mantra.star` → `/Applications/Star (Mantra).app`
  - `com.mantra.starmenu` → `/Applications/Launcher (Mantra).app --login` (Pause key app launcher)
  - `com.mantra.voiced` → `~/Developer/MANTRA_VOICE/voiced.py` (`127.0.0.1:8837` local voice & Whisper ears)
  - `com.mantra.voicedoor` → Tailscale proxy for `:8837` with `X-Mantra-Token`
  - `com.ma.readerweb` → `~/.maread-web/server.py` (`127.0.0.1:8081`)

---

## 2. All 11 Star Menu Folders (`~/.config/star-rows.json` — 61 Rows, 55 Apps)

| Folder | Key Apps & Purpose |
|---|---|
| **Claude** | `agentmgr` (Agent Manager CEO), `claudevoice` (Voice Engine: TTS + on-screen subtitles), `cloning` (Voice Cloning), `transcribe` (Voice to Text F1), `answerclaude` (Answer Claude), `claudemon` (Claude Code Monitor), `sister` (Sister App / MANTRA CHAT), `enter` (Claude Enter) |
| **DaVinci Resolve** | `resolveactions` (DaVinci Resolve Actions), `gradingtutorial` (DaVinci Grading Tutorial), `resolvepages` (Resolve Pages), `mkvconverter` (MKV Converter MPA) |
| **Elevate Media** | `emmonitor` (Elevate Media Project Monitor, listener `:8871` + API Worker) |
| **Ableton Live** | `a1` (Ableton Assistant A1), `mackie` (MIDI to MK Control), `midikeys` (MIDI to Key Stroke), `miditools` (MIDI Tools) |
| **Audio Production** | `soundrecorder` (Sound Recorder `:8869` — `record.app`, `record.suno`), `stemsep` (Stem Separation), `spectral` (Spectral Analyzer), `freevoiceeq` (Free Voice Convert Equalizer), `sampleplayer` |
| **DJing** | `djaysync` (djay Sync), `djtransfer` (DJ Transfer Monitor), `screenshot2tidal` (Screenshot to TIDAL) |
| **Percussions / Mantras** | `yshai` (Yshai Afterman Percussion School), `indianmantras` (Indian Mantras), `shrutibox` |
| **Keyboard and mouse** | `macro` (Macro Recorder — AX engine), `mouse` (Automated Mouse Actions), `keymon` (Keyboard Monitor), `streamdeck` (Stream Deck Remote), `controllermapper` |
| **Mac** | `swiftmatrix` (Swift Matrix — startup & login manager), `starapi` (Star API `:8863`), `monitor` (Star Monitor), `launcher` (Launcher), `findfile` (Find a File), `download` (Download, Copy and Move `:8833`), `netaggregate` (Network Aggregate Connection Keeper), `keyringtester` (KeyringTester), `timer` (Timer Stopwatch Clock), `darken` (Screen Brightness), `codefiller` (SMS Code Filler), `uhdhddisplay` (UHD HD Display), `chromiumvm` (VM Machine Remote Viewer), `vmrouter` (VM Router), `webcamviewer` (Webcam Recorder) |
| **E16** (exclusive group) | `e16resolve` (E16 for DaVinci Resolve), `liveactions` (E16 Ableton Live Actions), `oxi` (E16 Ableton Remote) |
| **Camera** | `mantravirtualcam` (Virtual Cam), `obs` (OBS Studio), `ndimonitor` (NDI Mantra Monitor) |

---

## 3. Controlling Any Star Menu App via HTTP API

### A. Directly via `STAR_API` (`http://127.0.0.1:8863`) or CLI (`~/.local/bin/star`)

```bash
# List all 55 Star apps and their running state
curl -s http://127.0.0.1:8863/apps

# Read all Accessibility (AX) buttons/controls of an app's window
curl -s "http://127.0.0.1:8863/apps/Timer%20Stopwatch%20Clock"

# Open an app in the background (without stealing focus)
curl -s -X POST "http://127.0.0.1:8863/apps/Timer%20Stopwatch%20Clock/open"

# Press a button/control inside an app by label (case-insensitive match)
curl -s -X POST "http://127.0.0.1:8863/apps/Timer%20Stopwatch%20Clock/press" \
  -H 'Content-Type: application/json' -d '{"label": "stopwatch"}'

# Quit an app cleanly
curl -s -X POST "http://127.0.0.1:8863/apps/Timer%20Stopwatch%20Clock/quit"

# List and call registered app functions (~/.config/star-fns/*.json, e.g. Sound Recorder :8869)
curl -s http://127.0.0.1:8863/fn
curl -s -X POST "http://127.0.0.1:8863/apps/Sound%20Recorder/fn/record.status" -d '{}'
```

### B. Via Queen's Built-In Proxy Endpoints (`http://127.0.0.1:8765/api/star/*`)

- `GET http://127.0.0.1:8765/api/star/startup` — returns Startup config (`star-autostart.json`), currently running apps (`star-running.json`), all 11 folders (`star-rows.json`), and live status from `:8863/apps` + `:8863/fn`.
- `POST http://127.0.0.1:8765/api/star/action` — body:
  ```json
  {
    "app": "Timer Stopwatch Clock",
    "action": "open | quit | read | press | fn",
    "label": "stopwatch",
    "fn": "record.status",
    "args": {}
  }
  ```

---

## 4. Local Voice Engine & On-Screen Subtitles (`127.0.0.1:8837` & `/api/voice/*`)

Marko's Mac has one unified voice server (`~/Developer/MANTRA_VOICE/voiced.py` on **`127.0.0.1:8837`**) paired with **`/Applications/Voice Engine (Mantra).app`** (which draws film-style subtitles across the screen with the spoken word highlighted in red/orange, plus menu-bar controls `▶ ■ SUB`):

- **Speak text aloud (with on-screen subtitles & word timings):**
  - Direct: `POST http://127.0.0.1:8837/speak` `{"text": "Hello Marko."}`
  - Queen proxy: `POST http://127.0.0.1:8765/api/voice/speak` `{"text": "Hello Marko."}`
- **Live word-by-word highlight & playback status:**
  - Direct: `GET http://127.0.0.1:8837/speaking` → `{"on": true, "sentence": "...", "i": 0, "n": 3, "pos": 0.42, "words": [{"s": 0, "e": 5, "t": 0.0, "d": 0.38}, ...]}` (`s`/`e` = char offsets, `t` = start sec, `d` = end sec)
  - Queen proxy: `GET http://127.0.0.1:8765/api/voice/speaking`
- **Pause / Stop speaking:**
  - `POST http://127.0.0.1:8765/api/voice/pause` / `POST http://127.0.0.1:8765/api/voice/stop`
- **Speech-to-Text (Whisper MLX on GPU):**
  - `POST http://127.0.0.1:8837/hear?lang=auto&words=1`

---

## 5. Blender Control (`~/Developer/BLENDER_CONTROL`)

- **Live GUI socket server:** `127.0.0.1:9876` via `python3 ~/Developer/BLENDER_CONTROL/.agents/skills/blender-control/scripts/blender_cli.py`
- **Headless CLI:** `/Applications/Blender.app/Contents/MacOS/Blender --background <file.blend> --python <script.py>`
