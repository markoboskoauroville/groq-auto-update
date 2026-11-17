"""WhatsApp Desktop by Accessibility (16.11.2026): Marko, "teach macro recorder how the interface of WhatsApp looks; Queen will ask macro recorder".
Hands: ~/Developer/MACRO_SKILLS/tools/whatsapp_ui.py (macro skills whatsapp-where/chats/unread/search/open/read/box/draft/find/media; UI map in
MACRO_SKILLS/maps/whatsapp-desktop.md). Nothing here ever sends a message.

    POST /api/whatsapp/desktop/<verb> {args: [...], group?: bool}   verb: where chats unread search open read box clear draft find media
        -> {ok, result}   (the tool's --json output)
Chat (local, no model, $0): "what did Svemir write last", "which chats are unread", "open Natasha", "draft to Rajko: ...",
"find 'plakat' in the Santoshi group". A person's name alone = the PRIVATE chat; "<X> group" or "Santoshi chat" = the group."""
import json, os, re, shutil, subprocess, sys

from flask import jsonify, request

TOOL = os.path.expanduser("~/Developer/MACRO_SKILLS/tools/whatsapp_ui.py")
VERBS = {"where", "chats", "unread", "search", "open", "read", "box", "clear", "draft", "find", "media"}


def run_tool(verb, args, timeout=150):
    r = subprocess.run(["python3", "-I", TOOL, verb, "--json"] + (["--loose"] if verb in ("open", "read", "find", "media") else []) + [str(a) for a in args], capture_output=True, text=True, timeout=timeout)
    out = r.stdout.strip()
    try:
        return json.loads(out)
    except Exception:
        return {"error": (r.stderr.strip() or out or "whatsapp_ui failed")[:400]}


def split_group(name):
    """-> (name, group?). 'Santoshi group' / 'Santoshi chat' / '<X> group' = a group; a person's name alone = private (memory group-vs-person-chat)."""
    n = name.strip().strip("\"'“”")
    n = re.sub(r"^(the|chat with|chat|with)\s+", "", n, flags=re.I)
    m = re.match(r"(.+?)\s+(group|group chat|chat)$", n, re.I)
    if m:
        base, kind = m.group(1).strip(), m.group(2).lower()
        if kind != "chat" or re.search(r"santoshi|kirtan|band", base, re.I):
            return base, True
        return base, False
    return n, False


def _app_exists(name):
    return any(os.path.isdir(os.path.join(d, name + ".app")) for d in ("/Applications", os.path.expanduser("~/Applications"), "/System/Applications"))


def register(app):
    @app.post("/api/whatsapp/desktop/<verb>")
    def wa_desktop(verb):
        if verb not in VERBS:
            return jsonify(ok=False, error="unknown verb"), 404
        d = request.get_json(silent=True) or {}
        args = list(d.get("args") or []) + (["--group"] if d.get("group") else [])
        res = run_tool(verb, args)
        if isinstance(res, dict) and res.get("error"):
            return jsonify(ok=False, error=res["error"]), 200
        return jsonify(ok=True, result=res)


def _read_answer(res, who, want_last_from=None):
    msgs = res.get("messages", [])
    if not msgs:
        return "The chat %s is open but I read no messages." % res.get("chat")
    lines = ["%s%s %s [%s]: %s" % ("(new day) " if m.get("day_break_before") else "", m["time"], "Marko" if m["mine"] else (m["from"] or "?"), m["kind"], m["text"][:300].replace("\n", " / ")) for m in msgs]
    theirs = [m for m in msgs if not m["mine"]]
    head = "%s (%s chat), last %d messages (read by Accessibility; opening a chat marks it read in WhatsApp):" % (res["chat"], res["kind"], len(msgs))
    if want_last_from and theirs:
        t = theirs[-1]
        head = "%s wrote last at %s: \"%s\"\n\n" % (t["from"] or res["chat"], t["time"], t["text"][:400].replace("\n", " / ")) + head
    return head + "\n" + "\n".join(lines)


def chat_whatsapp_desktop_command(text):
    if sys.platform != "darwin":
        return None
    t = (text or "").strip()
    low = t.lower()
    if len(t) > 400 or "\n" in t:
        return None
    try:
        # unread chats
        if re.search(r"\b(which|what|list|show)\b.*\b(chats?|conversations?|messages)\b.*\bunread\b|\bunread (chats|messages|whatsapp)\b|\bwho (wrote|messaged) me\b", low) and "reddit" not in low:
            r = run_tool("unread", [])
            if isinstance(r, dict) and r.get("error"):
                return "I could not read WhatsApp: " + r["error"]
            if not r:
                return "No unread chats in WhatsApp Desktop."
            tot = sum(x["unread"] for x in r)
            return "%d unread chats (%d messages):\n" % (len(r), tot) + "\n".join("- %s: %d unread; last: %s" % (x["title"], x["unread"], (x.get("preview") or "")[:70].replace("\n", " ")) for x in r[:25])
        # find 'text' in <chat>
        m = re.match(r"\s*(?:find|search(?: for)?)\s+[\"'“‘]?(.+?)[\"'”’]?\s+in\s+(?:the\s+)?(.+?)\s*[.?!]*$", t, re.I)
        if m and re.search(r"whatsapp|group|chat|santoshi|\bwith\b", low) or (m and not re.search(r"\.(py|md|txt|html)\b|repo|file|folder|page|site", low) and re.search(r"group|chat", low)):
            what, where = m.group(1), m.group(2)
            where = re.sub(r"\s+(on|in)\s+whatsapp(?: desktop)?$", "", where, flags=re.I)
            chat, grp = split_group(where)
            r = run_tool("find", [what, "--in", chat] + (["--group"] if grp else []))
            if r.get("error"):
                return "I could not search in %s: %s" % (chat, r["error"])
            ms = r.get("messages", [])
            return "%d matches for \"%s\" in %s (%s):\n" % (r.get("matches", 0), what, chat, "group" if grp else "private") + "\n".join("- %s %s: %s" % (x["time"], x["from"], x["text"][:200].replace("\n", " / ")) for x in ms)
        # what did X write last / last message from X
        m = (re.match(r"\s*what did (.+?) (?:write|say|send|text)(?: to me)?(?: last| most recently| recently)?\s*[.?!]*$", t, re.I)
             or re.match(r"\s*(?:what is |what's |show |read )?(?:the )?last (\d+ )?messages? (?:from|of|in|with) (.+?)\s*(?:on whatsapp)?[.?!]*$", t, re.I)
             or re.match(r"\s*read (?:the )?(.+?) (?:chat|group)(?: on whatsapp)?\s*[.?!]*$", t, re.I))
        if m:
            g = m.groups()
            who = (g[-1] if g[-1] else g[0]).strip()
            n = int(g[0]) if len(g) == 2 and g[0] and g[0].strip().isdigit() else 5
            if re.match(r"\s*read ", t, re.I): who = m.group(1) + (" group" if re.search(r"\bgroup\b", low) else "")
            chat, grp = split_group(who)
            r = run_tool("read", [n, "--chat", chat] + (["--group"] if grp else []))
            if r.get("error"):
                return "I could not read %s: %s" % (chat, r["error"])
            return _read_answer(r, chat, want_last_from=True)
        # open <name>
        m = re.match(r"\s*open\s+(?:the\s+)?(?:whatsapp\s+)?(?:chat\s+(?:with\s+)?)?(.+?)(?:\s+(?:chat|group))?(?:\s+(?:in|on)\s+whatsapp(?: desktop)?)?\s*[.?!]*$", t, re.I)
        if m and not re.search(r"\b(page|tab|site|file|folder|settings|http|\.com)\b", low):
            nm = m.group(1).strip()
            whole = re.match(r"\s*open\s+(?:the\s+)?(?:whatsapp\s+)?(?:chat\s+(?:with\s+)?)?(.+?)(?:\s+(?:in|on)\s+whatsapp(?: desktop)?)?\s*[.?!]*$", t, re.I).group(1)
            explicit = bool(re.search(r"whatsapp|\bchat\b|\bgroup\b", low))
            if (explicit or not _app_exists(nm)) and nm and nm.lower() not in ("whatsapp", "chrome", "firefox", "safari", "finder", "terminal"):
                chat, grp = split_group(whole)
                r = run_tool("open", [chat] + (["--group"] if grp else []))
                if r.get("error"):
                    return "WhatsApp did not open %s: %s" % (chat, r["error"])
                return "Opened %s (%s chat) in WhatsApp Desktop (header title checked)." % (r["opened"], r["kind"])
    except Exception as e:
        return "WhatsApp Desktop command failed: %s" % e
    return None
