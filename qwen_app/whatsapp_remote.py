"""WhatsApp remote for TTT's RE Magic WhatsApp tab (13.11.2026).

Marko, 13.11.2026: "I want that this ReMagic is able to connect to the Groq or Queen to this computer and do the things
in WhatsApp, what I'm telling you to do ... I am going to use this chat to ask through my phone and TTT on any device to
work with WhatsApp on my computer inside Firefox it will be the second tab in re".

    POST /api/whatsapp/remote {text}            words -> ONE action on WhatsApp Web in his Firefox
    POST /api/whatsapp/remote {pick: "<chat>"}  the chat he chose from the list the last answer offered
    POST /api/whatsapp/send   {chat, text, photo}   "Send it": ONLY the exact approved text in the shown chat

Answer: {ok, say, image_b64 (jpeg of the WhatsApp page, taken by BiDi), chat, draft, photo, choices[], action, via}.

The hands are ~/Developer/claude-code/tools/wa_remote.py (--json): real BiDi input, drafts stay UNSENT. The brain is the
local Claude Code through claude_link (his plan, no API credits; if it cannot be reached the answer is Marko's consent
sentence and nothing runs). Common phrases are understood without any model (rules below, English and Croatian).
Sending is never planned by the model: only /send, with the exact text and chat the tab shows.
The tab reaches this route through the tailnet door tools/wa_door.py (port 8877).
"""
import base64
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from flask import jsonify, request

WA = Path.home() / "Developer" / "claude-code" / "tools" / "wa_remote.py"
SKILL = Path(__file__).resolve().parent.parent / "queen_skills" / "whatsapp-remote.md"
import ffport


def _env():
    return dict(os.environ, FIREFOXCTL_PORT=ffport.firefox_port())
LOCK = threading.Lock()
PENDING = {"plan": None, "at": 0}   # a plan waiting for his pick of a chat
ACTIONS = {"shot", "open", "scroll", "draft", "photo_draft", "chats"}


def _wa(*args, timeout=150):
    r = subprocess.run([sys.executable, str(WA), "--json", *args], capture_output=True, text=True, timeout=timeout, env=_env(), cwd=str(WA.parent))
    line = next((l for l in reversed(r.stdout.strip().splitlines()) if l.startswith("{")), "")
    try:
        return json.loads(line)
    except Exception:
        return {"ok": False, "error": (r.stderr.strip().splitlines() or ["wa_remote gave no answer"])[-1][:300]}


# ------------------------------------------------------------------ understanding the words
LATEST = re.compile(r"\b(latest|newest|last|recent|new)\b.*\b(messages?|chats?|whatsapp)\b|\bshow me (my )?(whatsapp|messages|chats)\b|\b(screenshot|screen shot)\b.*\bwhatsapp\b|^(whatsapp|show|refresh|screenshot)\W*$|najnovij|zadnj[ae] poruk|pokaži.*poruk", re.I)
SCROLL = re.compile(r"\bscroll\b\s*(up|down)|\b(up|down)\b\s*$|\bgo (up|down)\b|\bgore\b|\bdolje\b|\bprije\b", re.I)
OPEN = re.compile(r"^(?:please )?(?:open|show|go to|find|otvori|pokaži)\s+(?:me )?(?:the )?(?:chat|conversation|group|razgovor|grupu)?\s*(?:with|from|of|sa|s)?\s*(.+?)\s*$", re.I)
DRAFT = re.compile(r"^(?:please )?(?:draft|write|reply|answer|respond|type|napiši|odgovori)(?: a)?(?: reply| message| poruku)?(?: to| for| u| za)?\s*(.*?)\s*(?:,|:|\bsaying\b|\bthat says\b|\bwith the (?:text|message)\b|\bkaži\b|\bpiše\b)\s*(.+)$", re.I | re.S)
PHOTO = re.compile(r"(screenshot|picture|photo|image|snimk|slik).*(live ?stream|stream|live)|(live ?stream|stream).*(screenshot|picture|photo|image)", re.I)


def plan_by_rules(t):
    t = t.strip()
    if PHOTO.search(t):
        chat = "Santoshi"
        m = re.search(r"\b(?:send|post|share|draft)\s+(?:to\s+)?(?:the\s+)?(.+?)\s+(?:a|the)\s+(?:screenshot|picture|photo|image)", t, re.I)
        if m and not re.search(r"band|santoshi", m.group(1), re.I):
            chat = m.group(1)
        cap = ""
        m = re.search(r"(?:with (?:the )?(?:message|text|caption)|saying|that says|message|caption)\s*[:,]?\s*(.+)$", t, re.I | re.S)
        if m:
            cap = m.group(1).strip().strip('"“”')
        return {"action": "photo_draft", "chat": chat, "text": cap, "source": "live"}
    m = DRAFT.match(t)
    if m:
        return {"action": "draft", "chat": m.group(1).strip().strip('"“”'), "text": m.group(2).strip().strip('"“”')}
    m = SCROLL.search(t)
    if m and len(t) < 40:
        d = (m.group(1) or m.group(2) or m.group(3) or "").lower()
        return {"action": "scroll", "dir": "down" if d in ("down", "dolje") else "up"}
    if LATEST.search(t) and len(t) < 120:
        return {"action": "shot"}
    m = OPEN.match(t)
    if m and len(t) < 80 and m.group(1).lower() not in ("whatsapp", "latest", "messages"):
        return {"action": "open", "chat": m.group(1).strip().strip('"“”')}
    return None


def plan_by_claude(t):
    import claude_link
    skill = SKILL.read_text() if SKILL.exists() else ""
    prompt = (skill + "\n\n---\nMarko said (through the TTT keyboard's WhatsApp tab): " + json.dumps(t, ensure_ascii=False) +
              "\n\nAnswer with ONE json object and nothing else: {\"action\": one of shot|open|scroll|draft|photo_draft|chats, "
              "\"chat\": \"...\", \"text\": \"...\", \"dir\": \"up|down\"}. Keep his words verbatim in text. Never plan a send.")
    a = claude_link.ask(prompt, model="haiku", timeout=120)["answer"]
    m = re.search(r"\{.*\}", a, re.S)
    p = json.loads(m.group(0)) if m else {}
    if p.get("action") not in ACTIONS:
        raise ValueError("I did not understand what to do in WhatsApp: " + a[:120])
    return p


# ------------------------------------------------------------------ doing it
def _img(res):
    p = res.get("image")
    if p and os.path.exists(p):
        return base64.b64encode(open(p, "rb").read()).decode()
    return None


def _out(res, action, **kw):
    d = {"ok": bool(res.get("ok")), "say": res.get("text") or res.get("error") or "", "image_b64": _img(res), "chat": res.get("chat", ""),
         "draft": res.get("draft"), "photo": False, "choices": [], "action": action, "via": "Queen -> wa_remote (BiDi)"}
    d.update(kw)
    return d


def _find(query):
    r = _wa("find", query)
    return r.get("matches", []) if r.get("ok") else None


def execute(plan):
    a = plan["action"]
    if a == "shot":
        return _out(_wa("shot"), a)
    if a == "chats":
        r = _wa("chats")
        return {"ok": r.get("ok", False), "say": "Chats: " + "; ".join((r.get("chats") or [])[:12]), "choices": (r.get("chats") or [])[:12], "action": a}
    if a == "scroll":
        return _out(_wa("scroll", plan.get("dir", "up")), a)
    chat = (plan.get("chat") or "").strip()
    if a == "open" or a == "photo_draft" or (a == "draft" and chat):
        matches = _find(chat)
        if matches is None:
            return {"ok": False, "say": "WhatsApp on the Mac did not answer (is Firefox with WhatsApp Web up?)", "action": a}
        exact = [m for m in matches if m.lower() == chat.lower()]
        if not matches:
            return {"ok": False, "say": f"No chat matches \"{chat}\".", "action": a}
        if len(matches) > 1 and len(exact) != 1:
            PENDING.update(plan=dict(plan), at=time.time())
            return {"ok": True, "say": f"Several chats match \"{chat}\". Pick one.", "choices": matches[:10], "action": a}
        chat = (exact or matches)[0]
    if a == "open":
        return _out(_wa("open", chat), a)
    if a == "draft":
        if not plan.get("text"):
            return {"ok": False, "say": "What should the draft say?", "action": a}
        r = _wa("draft", chat, plan["text"])
        return _out(r, a, draft=plan["text"] if r.get("ok") else None)
    if a == "photo_draft":
        live = _wa("live")
        if not live.get("ok") or not live.get("image"):
            return {"ok": False, "say": "Could not take the picture of the live stream: " + str(live.get("error", "")), "action": a}
        r = _wa("draftphoto", chat, plan.get("text", ""), live["image"])
        cap = plan.get("text") or "(photo only)"
        return _out(r, a, draft=cap if r.get("ok") else None, photo=True)
    return {"ok": False, "say": "Unknown action " + a, "action": a}


def register(app):
    @app.route("/api/whatsapp/remote", methods=["POST"])
    def whatsapp_remote():
        d = request.get_json(force=True, silent=True) or {}
        text = (d.get("text") or "").strip()
        pick = (d.get("pick") or "").strip()
        if not text and not pick:
            return jsonify({"ok": False, "say": "Say what to do in WhatsApp."}), 400
        with LOCK:
            try:
                if pick:
                    plan = PENDING.get("plan")
                    if not plan or time.time() - PENDING["at"] > 600:
                        return jsonify({"ok": False, "say": "Nothing was waiting for a pick. Say it again."})
                    plan = dict(plan, chat=pick)
                    PENDING.update(plan=None)
                    return jsonify(execute(plan))
                plan = plan_by_rules(text)
                how = "rules"
                if not plan:
                    plan = plan_by_claude(text)
                    how = "local Claude Code"
                res = execute(plan)
                res["understood"] = how
                return jsonify(res)
            except Exception as exc:
                msg = str(exc)
                if type(exc).__name__ == "NeedConsent":
                    msg = "I cannot reach the local Claude Code. Do you want to use API credits?"
                return jsonify({"ok": False, "say": msg[:300]})

    @app.route("/api/whatsapp/send", methods=["POST"])
    def whatsapp_send():
        d = request.get_json(force=True, silent=True) or {}
        chat, text = (d.get("chat") or "").strip(), (d.get("text") or "")
        photo = bool(d.get("photo"))
        if not chat or (not text.strip() and not photo):
            return jsonify({"ok": False, "say": "Nothing to send: the chat and the exact text are needed."}), 400
        with LOCK:
            args = ["send", chat, "" if text.strip() == "(photo only)" else text]
            if photo:
                args.append("--photo")
            r = _wa(*args)
            res = _out(r, "send")
            res["say"] = r.get("text") or r.get("error") or ""
            return jsonify(res)
