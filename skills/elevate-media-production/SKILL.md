---
name: elevate-media-production
description: >-
  Complete end-to-end Elevate Media production workflow for Damjan (UGC
  supplement ads HIR_xx in DaVinci Resolve): reading WhatsApp messages ("AI
  Videos"), reading timestamped video comments on Google Drive, updating
  timelines in DaVinci Resolve, finding high-resolution product images online,
  and generating free images inside Gemini in Chrome. Use for any Elevate Media,
  HIR_xx, Damjan, Drive comments, or DaVinci Resolve timeline task.
---

# Elevate Media — End-to-End Production Skill for Queen (`qwen`)

This skill teaches Queen (`Groq AI Studio`) and any connected agent how to take an **Elevate Media** project (`HIR_xx_<Name>_UGC_EN` for client **Damjan** / **LongevityStore**) from start to finish using Marko's local tools and Queen's `/api/elevate/*` HTTP endpoints.

---

## Overview of an Elevate Media Project

- **What it is:** A UGC supplement ad (`HIR_95`, `HIR_96`, `HIR_97`, `HIR_98`, `HIR_99`, ...) featuring a speaker on camera comparing 4 competitor products with **Longevity One**, plus an off-screen **Journalist** voice naming each product.
- **Deliverables per round (`V1`, `V2`, `V3`...):** 4 hooks (`A`, `B`, `C`, `D`) × 2 aspect ratios (`9x16` vertical 1080×1920, `4x5` 1080×1350) = **8 timelines / MP4s**:
  `V<n>-HIR_xx_<Name>_UGC_EN_<A..D>_<9x16|4x5>`
- **Key Locations:**
  - **Code & Tools Repo:** `~/ElevateMedia` (`tools/`, `production/damjan/HIR_xx/scripts/hirXX_plan.py` & `hirXX_resolve.py`, `ELEVATE_MEDIA_MANIFEST.md`)
  - **Monitor & Agent Repo:** `~/Developer/ELEVATE_MEDIA_MONITOR` (`127.0.0.1:8871`, `tools/drive_comments.py`, `agent/emagent.py`, `agent/PIPELINE.md`)
  - **Local Project Media:** `~/Movies/ElevateMedia/HIR_xx_<Name>_UGC_EN/` (`Brief/`, `Footage/`, `Products/`, `Graphics/`, `Subtitles/`, `Resolve/plan.json`, `Exports/ALL_VERSIONS_<date>/`)
  - **NEVER TOUCH:** `~/ElevateMedia/production/damjan/skills/ugc-ad/` (Marko's backup only — never read or use) and never touch Marko's BenQ monitor, mouse, or keyboard.

---

## Stage 1: Reading WhatsApp Messages (`"AI Videos"`)

Damjan posts project briefs and revision requests in the WhatsApp Web group **"AI Videos"** (synced live by the Firefox extension `SYNCING_ELEVATE_MEDIA_MESSAGES` into `~/Library/Application Support/ElevateMediaMonitor/messages.jsonl` and `~/ElevateMedia/production/damjan/chat/AI_VIDEOS.md`).

- **Via Queen HTTP API:**
  - `GET http://127.0.0.1:8765/api/elevate/whatsapp?count=30` — returns the latest messages from `"AI Videos"`.
  - `GET http://127.0.0.1:8765/api/elevate/board` — returns the Project Watcher board (`watcher.json`: each `HIR_xx` project's Drive stage `01 RAW`, `02 FOR REVIEW`, `03 AGENCY REVIEW`, `04 APPROVED`, and next steps).
- **Drafting an Unsent Reply in WhatsApp (Human Gate: NEVER auto-send):**
  - `POST http://127.0.0.1:8765/api/elevate/whatsapp/draft` `{"chat": "AI Videos", "text": "Hello Damjan,\nHIR_98 V3: https://drive.google.com/drive/folders/<FINAL_ID>"}`
  - Underlying CLI: `python3 ~/ElevateMedia/tools/whatsapp_draft.py "AI Videos" <message_file.txt>` (types the message unsent into WhatsApp Web; Marko presses Send himself).

---

## Stage 2: Reading Comments on Google Drive (`LongevityStore`)

Damjan also leaves timestamped revision comments directly on the exported `.mp4` videos in Google Drive (`LongevityStore`).

- **Via Queen HTTP API:**
  - `GET http://127.0.0.1:8765/api/elevate/drive-comments?project=HIR_98` (add `&all=1` to include resolved comments).
- **Underlying CLI:**
  ```bash
  ~/Applications/GDriveDownloader/.venv/bin/python -I \
    ~/Developer/ELEVATE_MEDIA_MONITOR/tools/drive_comments.py HIR_98
  ```
- **Output format:** JSON listing every file in the project folder / `FINAL` that has comments:
  `{code, folder, stage, files: [{name, path, id, comments: [{author, time, text, resolved, at: "0:14", quoted, replies}]}]}` where `at` is the exact `m:ss` timestamp inside the video!
- **Rule:** Always compare both **WhatsApp messages** and **Drive comments** after the last delivery timestamp. If they conflict, ask Marko via `emask` (`POST http://127.0.0.1:8871/question`).

---

## Stage 3: Finding High-Resolution Product Images Online

When a new product or correction requires a cleaner/higher-resolution product bottle or pack photo:

1. **Search the brand's official store first:**
   - For Shopify stores, append `.json` to the product URL (`/products/<handle>.json`) to get the raw uncompressed studio PNG/WebP URLs (`images[0].src`).
2. **Download & Verify Dimensions (`fetch_image`):**
   - **Via Queen HTTP API:**
     `POST http://127.0.0.1:8765/api/elevate/fetch-image`
     `{"url": "https://...", "project": "HIR_98", "name": "competitor_1_bottle"}`
   - Downloads into `~/Movies/ElevateMedia/<project>/refs/web/`, verifies MIME type (`image/*`), and checks pixel dimensions via macOS `sips -g pixelWidth -g pixelHeight` (must be high-res, typically ≥1000 px).

---

## Stage 4: Generating Images for Free Inside Gemini in Chrome

When a custom scene, background, or product composite needs to be generated **for free** (without spending paid Kie/Higgsfield/imgtoimg credits):

1. **Method A — Local Chrome Browser (`mode: "chrome"`):**
   - **Via Queen HTTP API:**
     `POST http://127.0.0.1:8765/api/elevate/gemini-chrome`
     `{"prompt": "Create a clean studio photo of...", "project": "HIR_98", "name": "shot_01", "mode": "chrome"}`
   - Copies the prompt to the clipboard, opens `https://gemini.google.com/app` in **Google Chrome** (or connects over CDP port `9222` if launched via `chrome-debug`), and focuses the Gemini prompt box so Gemini's free **Nano Banana / Imagen 3** model generates the image in the browser at zero cost.
2. **Method B — Automated Multi-Account Gemini Batch (`mode: "vm"`):**
   - **Via Queen HTTP API:**
     `POST http://127.0.0.1:8765/api/elevate/gemini-chrome`
     `{"prompt": "...", "project": "HIR_98", "name": "shot_01", "mode": "vm", "refs": ["~/Movies/ElevateMedia/HIR_98/refs/ref1.png"]}`
   - Uploads reference images and `batch.json` via `rclone` to `gdrive:Chromium Downloads/Gemini/_batch/batch.json`. The Chromium-VM worker automatically rotates through Marko's Gemini accounts (`~/.config/elevate-media/gemini_accounts.json`) and writes completed high-res images to `gdrive:Chromium Downloads/Gemini/em-<project>/`.
   - Check status: `GET http://127.0.0.1:8765/api/elevate/gemini-status?project=HIR_98`.

---

## Stage 5: Updating Timelines in DaVinci Resolve & Rendering

All DaVinci Resolve operations go through the single-instance router `resolve-run --who elevate` on project `ELEVATE_MEDIA`:

1. **Plan & Graphics Generation (`hirNN_plan.py`):**
   - Generates `Resolve/plan.json`, `Graphics/*.png` (product packs on V3, 400×200 score badges on V4 at `x=840`, price chips on V5 28 px above, headline box, disclaimer), and 2-word `Subtitles/*.srt` from Whisper word timings (`http://127.0.0.1:8837/hear?words=1`).
2. **Build / Update Timeline (`hirNN_resolve.py` via `resolve-run`):**
   - **Rule:** Always build **one version first (`V<n> A 9x16`)**! Never build or render all 8 before Marko watches `A 9x16`.
   - Runs `resolve-run --who elevate ~/ElevateMedia/production/damjan/HIR_xx/scripts/hirXX_resolve.py`.
3. **Apply Fades & Automated Numeric Checks (Mandatory Before Render):**
   - `resolve-run --who elevate ~/ElevateMedia/tools/resolve_fades.py fix` — sets 12-frame in/out fades on all V2+ graphics (except `vignette_*`) on the **Edit page**. (Note: Resolve API fades do not survive a restart, so `resolve_render.py` also sets them during the render launch.)
   - `python3 ~/ElevateMedia/tools/layout_check.py` — verifies **0 problems**: no two graphics touching (≥24 px gap, ≥8 px inside a block), equal gaps `g` between caption → headline → product block, centered on `W/2` (±2 px), nothing outside frame.
   - `python3 ~/ElevateMedia/tools/resolve_checklist.py` — verifies markers `VOICE 2`, `SILENT`, `CAPTIONS`.
   - **Via Queen HTTP API:** `POST http://127.0.0.1:8765/api/elevate/resolve` `{"tool": "layout_check.py", "args": []}`.
4. **Build Remaining 7 Versions (`B`, `C`, `D` × `9x16`, `4x5`):**
   - Once Marko approves `A 9x16`, generate `B/C/D` hooks and convert to `4x5` (`resolve_to_4x5.py`, `fit_4x5.py` — shrinks headline & product block by uniform factor ≥0.85).
5. **Gated 2-Pass H.265 Render & Drive Delivery:**
   - **Human Gate 1 (Watch):** Ask Marko via `emask` (`WATCHED · RENDER`). Never render without his approval.
   - **Render:** `python3 ~/ElevateMedia/tools/render_one_restart.py --passes 2 "<timeline>=<out_dir>"` (H.265 MP4, 10 Mbit/s, bit depth matched to footage, old export `rm`'d first).
   - **Delivery QC:** `python3 ~/ElevateMedia/tools/delivery_check.py --look` (verifies burned-in captions, audio stream, bitrate ≥5 Mbit/s, non-black middle frame).
   - **Human Gate 2 (Upload CONFIRM):** `zsh ~/ElevateMedia/tools/drive_replace_final.sh <ALL_VERSIONS_dir> <FINAL_id> "<name>"` (pops up the Monitor CONFIRM box + SIM balance gate, uploads over AX cable, verifies MD5 via `drive_verify.py`, deletes old FINAL files).
   - **Human Gate 3 (WhatsApp Draft):** Type the single summary link message unsent into `"AI Videos"` with `whatsapp_draft.py`.
