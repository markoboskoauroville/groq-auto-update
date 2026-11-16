"""Draft in WhatsApp Desktop (16.11.2026): local chat command, $0, no model, NEVER sends.
"draft in WhatsApp to <chat>: <text>" (also "write in WhatsApp to ...") puts <text> into the message box of that chat in the real
WhatsApp Desktop app through the Macro Recorder tool ~/Developer/MACRO_SKILLS/tools/whatsapp_draft.py (front by click, search,
header check, paste, OCR readback). The answer repeats the tool's MATCH/MISMATCH line. Marko presses Send himself."""
import os, re, subprocess, sys, tempfile

TOOL = os.path.expanduser("~/Developer/MACRO_SKILLS/tools/whatsapp_draft.py")


def chat_whatsapp_draft_command(text):
    if sys.platform != "darwin":
        return None
    m = re.match(r"\s*(?:draft|write|type|put)(?: a message| it)? (?:in|into) whatsapp(?: desktop)? to (.+?)\s*:\s*(.+)$", text or "", re.I | re.S)
    if not m:
        return None
    chat, body = m.group(1).strip().strip('"'), m.group(2).strip()
    if not chat or not body:
        return "Say the chat and the text: draft in WhatsApp to <chat>: <text>."
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(body)
    try:
        r = subprocess.run(["python3", "-I", TOOL, chat, f.name], capture_output=True, text=True, timeout=180)
        out = (r.stdout + r.stderr).strip()
    except Exception as e:
        return f"The draft did not run: {e}"
    finally:
        try: os.unlink(f.name)
        except OSError: pass
    return "Draft in WhatsApp Desktop (NOT sent, Marko sends): " + out
