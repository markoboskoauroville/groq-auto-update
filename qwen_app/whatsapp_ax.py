"""Queen reads WhatsApp Web (Marko's Firefox under remote control) through Accessibility: who wrote, what was not answered.

Marko, 14.11.2026: "ask her to check my last 5 WhatsApp messages, and it needs to understand who sent them and what was not
responded to. Without taking screenshots, it needs to use accessibility to get the text" ... "WhatsApp, as always, we are using
the Firefox browser with something we call remote control".

    POST /api/whatsapp/ax/latest {n: 5}  -> {ok, chats: [{name, time, sender, from_me, text, unread, group, kind, answered}], ...}
    chat: "check my last 5 WhatsApp messages", "who did I not answer on WhatsApp", "zadnjih 5 poruka na whatsappu"

How it reads (no screenshot, no vision, no click, nothing typed):
1. The macOS AX tree of Firefox (ax_read: the Swift axread, else the Python walk), with frames.
2. The window whose web area is WhatsApp; in it the AXTable "Chat list". Each row: the name, the time, "N unread messages",
   and the last-message preview (group chats put "~Name" + ": " before the text).
3. Who wrote the last message: WhatsApp hides its tick icon from Accessibility (aria-hidden svg "wds-ic-read"), but the
   icon still takes ~20 px, so the preview text starts ~20 px to the right of its group when the last message is Marko's.
   "You reacted ..." is Marko's too; "X reacted ..." is X's. A media preview (Photo, Video, ...) has its own icon: one more
   20 px step for it.
4. Rows sorted by time (pinned chats sit at the top of the list regardless of time), the newest N reported.
If the WhatsApp tab is not readable (no Firefox window with it, another tab selected), the tab is opened / selected over BiDi
(firefoxctl, port 9223) and the app Marko was in is given back at once.
"""
import fcntl
import json
import os
import re
import subprocess
import time

import ax_read

import ffport

FF_PORT = ffport.firefox_port()  # re-read per call in _ffctl
FIREFOXCTL = os.path.expanduser("~/.local/bin/firefoxctl")
LOCK = "/tmp/wa-bidi.lock"          # the one BiDi slot shared with wa_remote, the door, vm-whatsapp
ICON_PX = 12                        # an offset of 12 px or more before the text = an icon is there
MEDIA = re.compile(r"^(photo|video|gif|sticker|document|audio|voice message|location|contact|poll|\d+:\d\d)\b", re.I)
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
             "jedna": 1, "dvije": 2, "tri": 3, "četiri": 4, "cetiri": 4, "pet": 5, "šest": 6, "sest": 6, "deset": 10}


def _clean(s):
    return re.sub(r"[‪-‮‎‏]", "", str(s or "")).replace("\xa0", " ").strip()


def _texts(n, out=None):
    """Static texts and image descriptions in reading order (emoji are AXImage with the emoji as description)."""
    out = [] if out is None else out
    if n.get("role") == "AXStaticText" and "value" in n:
        out.append(str(n["value"]))
    elif n.get("role") == "AXImage" and "description" in n and len(str(n["description"])) <= 4:
        out.append(str(n["description"]))
    for c in n.get("children", []):
        _texts(c, out)
    return out


def _find(n, pred):
    if pred(n):
        return n
    for c in n.get("children", []):
        r = _find(c, pred)
        if r:
            return r
    return None


def _first_leaf_x(n):
    """x of the first visible child that carries content (text or image), depth first."""
    for c in n.get("children", []):
        if c.get("role") in ("AXStaticText", "AXImage") and c.get("w", 0) > 0:
            return c.get("x")
        x = _first_leaf_x(c)
        if x is not None:
            return x
    return None


def _when_key(t, idx):
    """Sort key, newest first: (days ago, -minutes). Unknown formats keep the list order."""
    s = (t or "").strip().lower()
    m = re.match(r"^(\d{1,2}):(\d\d)$", s)
    if m:
        return (0, -(int(m.group(1)) * 60 + int(m.group(2))), idx)
    if s in ("yesterday", "jučer", "jucer"):
        return (1, 0, idx)
    if s in WEEKDAYS:
        today = time.localtime().tm_wday
        return (((today - WEEKDAYS.index(s)) % 7) or 7, 0, idx)
    m = re.match(r"^(\d{1,2})[./](\d{1,2})[./](\d{2,4})\.?$", s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y += 2000 if y < 100 else 0
        day, mon = (a, b) if a > 12 or b <= 12 else (b, a)
        try:
            ts = time.mktime((y, mon, day, 12, 0, 0, 0, 0, -1))
            return (max(2, int((time.time() - ts) // 86400)), 0, idx)
        except Exception:
            pass
    return (999, 0, idx)


def parse_row(row):
    grp = row
    # row > cell > application group > [header cell, preview group, flags cell]
    for _ in range(3):
        kids = grp.get("children", [])
        if len(kids) == 1:
            grp = kids[0]
    kids = grp.get("children", [])
    header = next((k for k in kids if k.get("role") == "AXCell" and k.get("title")), None)
    if not header:
        return None
    def is_preview(k):
        return k.get("role") == "AXGroup" and _find(k, lambda n: str(n.get("title", "")).startswith("\u202a")) is not None
    preview = next((k for k in kids if k is not header and is_preview(k)), None)
    community = next((_clean(k["title"]) for k in kids if k.get("role") == "AXGroup" and k.get("title") and k is not preview), "")
    htexts = [_clean(x) for k in kids if k is not preview for x in _texts(k)]
    unread = 0
    for x in htexts:
        m = re.match(r"^(\d+) unread messages?$", x)
        if m:
            unread = int(m.group(1))
    name_node = _find(header, lambda n: n.get("role") == "AXGroup" and n.get("title") and not re.match(r"^\d+ unread", str(n["title"])))
    name = _clean(name_node["title"]) if name_node else ""
    times = [x for x in htexts if re.match(r"^(\d{1,2}:\d\d|yesterday|jučer|" + "|".join(WEEKDAYS) + r"|\d{1,2}[./]\d{1,2}[./]\d{2,4}\.?)$", x, re.I)]
    when = times[-1] if times else ""
    flags = " ".join(_clean(k.get("title", "")) for k in kids if k.get("role") == "AXCell" and k is not header)
    parts = [_clean(x) for x in _texts(preview)] if preview else []
    parts = [p for p in parts if p != ""]
    text = ""
    sender = None
    group = False
    kind = "message"
    from_me = None
    joined = " ".join(parts)
    if preview:
        titled = _find(preview, lambda n: n.get("title"))
        text = _clean(titled["title"]) if titled else joined
    # "~Name" ":" "text" (group, someone else)
    raw = [_clean(x) for x in _texts(preview)] if preview else []
    colon = next((i for i, p in enumerate(raw) if p == ":"), None)
    if colon is not None and colon > 0:
        sender = raw[colon - 1].lstrip("~").strip()
        group = True
        text = " ".join(p for p in raw[colon + 1:] if p).strip() or text
        from_me = sender.lower() in ("you", "ti", "vi")
    elif joined.startswith("You reacted") or joined.startswith("Reagirali ste"):
        kind, from_me, sender = "reaction", True, "you"
        text = re.sub(r"^You reacted\s*", "reacted ", joined).replace(' to: "', ' to "').strip()
    elif re.search(r"\breacted\b", joined):
        kind, from_me = "reaction", False
        sender = joined.split(" reacted")[0].strip().lstrip("~")
        text = joined[len(joined.split(" reacted")[0]):].strip().replace(' to: "', ' to "')
    elif re.search(r"\b(added|removed|left|joined|changed|created)\b", joined) and len(joined) < 120 and not text.endswith((".", "!", "?")):
        kind, from_me = "event", False
        sender = raw[0].lstrip("~").strip() if raw else name
        group = True
    if from_me is None and preview:
        titled = _find(preview, lambda n: n.get("title")) or preview
        gx, fx = titled.get("x"), _first_leaf_x(titled)
        if gx is not None and fx is not None:
            off = fx - gx
            if MEDIA.match(text):
                off -= 20          # the media icon (camera, mic, ...) is one icon by itself
            from_me = off >= ICON_PX
        if from_me is None:
            from_me = False
    if not sender:
        sender = "you" if from_me else name
    answered = bool(from_me) or kind in ("event", "reaction")
    return {"name": name, "community": community, "time": when, "sender": sender, "from_me": bool(from_me), "text": text[:400],
            "unread": unread, "group": group, "kind": kind, "answered": answered,
            "muted": "Muted" in flags, "pinned": "Pinned" in flags}


def _whatsapp_area(res):
    for w in res.get("windows", []):
        area = _find(w, lambda n: n.get("role") == "AXWebArea" and "whatsapp" in (str(n.get("title", "")) + str(n.get("description", ""))).lower())
        if area:
            return area
    return None


def _front():
    try:
        from AppKit import NSWorkspace
        return NSWorkspace.sharedWorkspace().frontmostApplication()
    except Exception:
        return None


def _give_back(app):
    try:
        if app is not None and (app.localizedName() or "") != "Firefox":
            app.activateWithOptions_(0)
    except Exception:
        pass


def _ffctl(*args, timeout=60):
    env = dict(os.environ, FIREFOXCTL_PORT=ffport.firefox_port())
    with open(LOCK, "a") as f:
        end = time.time() + 90
        while True:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.time() > end:
                    raise RuntimeError("another program holds Firefox's remote control (" + LOCK + ")")
                time.sleep(0.3)
        r = subprocess.run(["python3", FIREFOXCTL, *args], capture_output=True, text=True, timeout=timeout, env=env)
    return r.returncode, (r.stdout + r.stderr).strip()


def make_readable(log):
    """Open or select the WhatsApp tab so Firefox's AX tree carries it; give the front app back."""
    front = _front()
    try:
        code, out = _ffctl("tabs")
        if code != 0:
            raise RuntimeError("Firefox's remote control does not answer on port " + ffport.firefox_port() + ": " + out[-200:])
        if "web.whatsapp.com" not in out:
            log.append("no WhatsApp tab: opened https://web.whatsapp.com in Firefox (remote control)")
            _ffctl("open", "https://web.whatsapp.com", "--new", timeout=90)
        else:
            log.append("WhatsApp tab selected in Firefox (remote control)")
            _ffctl("-t", "web.whatsapp.com", "activate")
    finally:
        time.sleep(0.4)
        _give_back(front)


def latest(n=5, wait=30):
    """The newest n chats of WhatsApp Web, read through Accessibility."""
    t0 = time.time()
    log = []
    tried = False
    while True:
        res = ax_read.read("Firefox", frames=True, max_nodes=20000, timeout=20)
        if not res.get("ok"):
            if "not running" in str(res.get("error", "")) and not tried:
                tried = True
                make_readable(log)
                continue
            return {"ok": False, "error": res.get("error"), "via": res.get("via"), "log": log}
        area = _whatsapp_area(res)
        table = _find(area, lambda x: x.get("role") == "AXTable" and "chat list" in str(x.get("description", x.get("title", ""))).lower()) if area else None
        if table:
            break
        if not area and not tried:
            tried = True
            make_readable(log)
            continue
        if time.time() - t0 > wait:
            why = "WhatsApp is open but its chat list is not there (still loading, or not linked: QR code)" if area else \
                  "no Firefox window shows WhatsApp Web (a window on another Space is invisible to Accessibility)"
            return {"ok": False, "error": why, "via": res.get("via"), "log": log}
        time.sleep(2)
    rows, seen = [], set()
    for i, r in enumerate(table.get("children", [])):
        p = parse_row(r)
        if not p or not p["name"]:
            continue
        k = (p["name"], p["time"], p["text"][:60])
        if k in seen:
            continue
        seen.add(k)
        p["_k"] = _when_key(p["time"], i)
        rows.append(p)
    rows.sort(key=lambda p: p["_k"])
    # group events ("X joined", "X added Y") are not messages: left out, only counted (those newer than the last one listed)
    msgs = [p for p in rows if p["kind"] != "event"]
    top = msgs[:n]
    cut = top[-1]["_k"] if top else (999, 0, 0)
    skipped = sum(1 for p in rows if p["kind"] == "event" and p["_k"] < cut)
    for p in rows:
        p.pop("_k", None)
    return {"ok": True, "via": "accessibility/" + str(res.get("via")), "read_at": time.strftime("%H:%M:%S"),
            "chats": top, "not_answered": [p["name"] for p in top if not p["answered"]], "skipped_events": skipped,
            "rows_seen": len(rows), "log": log, "secs": round(time.time() - t0, 1)}


def say(r, n):
    if not r.get("ok"):
        return "I could not read WhatsApp through Accessibility: " + str(r.get("error")) + "."
    lines = [f"Your last {len(r['chats'])} WhatsApp chats (read from Firefox through Accessibility, no screenshot, {r['read_at']}):"]
    for i, p in enumerate(r["chats"], 1):
        who = "you" if p["from_me"] else p["sender"]
        where = p["name"] + (" (group)" if p["group"] else "")
        extra = f", {p['unread']} unread" if p["unread"] else ""
        if p["kind"] == "event":
            state = "group event, nothing to answer"
        elif p["kind"] == "reaction":
            state = "you reacted, that counts as an answer" if p["from_me"] else "only a reaction, nothing to answer"
        elif p["from_me"]:
            state = "answered (the last message is yours)"
        else:
            state = "NOT answered"
        txt = p["text"] if len(p["text"]) <= 140 else p["text"][:137] + "..."
        if p.get("community"):
            where += " in " + p["community"]
        verb = "" if p["kind"] in ("reaction", "event") else "wrote "
        said = txt if p["kind"] in ("reaction", "event") else '"' + txt + '"'
        said = said.replace('to " ', 'to "')
        if p["kind"] == "event":
            lines.append(f"{i}. {where}, {p['time']}: {said}{extra}. {state}.")
        else:
            lines.append(f"{i}. {where}, {p['time']}: {who} {verb}{said}{extra}. {state}.")
    if r.get("skipped_events"):
        lines.append(f"(left out: {r['skipped_events']} group event(s) such as 'X joined', they are not messages)")
    na = [p["name"] for p in r["chats"] if not p["answered"]]
    lines.append("Not answered: " + (", ".join(na) if na else "none, you answered all of them") + ".")
    return "\n".join(lines)


ASK = re.compile(r"(whats\s?app|whatsapp|wa\b|watsap)", re.I)
WANT = re.compile(r"\b(answer\w*|respon\w*|repl(?:y|ied)|messages?|poruk\w*|chats?|razgovor\w*|unanswered|not (?:been )?(?:answered|responded|replied)|"
                  r"did(?:n't| not) (?:answer|respond|reply)|odgovor\w*)\b", re.I)
VERB = re.compile(r"\b(check|show|read|list|tell|what|who|which|give|see|look|provjeri|pokaži|pokazi|procitaj|pročitaj|koje?|tko|last|latest|recent|newest|zadnj\w*)\b", re.I)


def chat_whatsapp_ax_command(text):
    t = (text or "").strip()
    if len(t) > 300 or not ASK.search(t) or not WANT.search(t) or not VERB.search(t):
        return None
    if re.search(r"\b(write|draft|send|reply to|type|napiši|napisi|pošalji|posalji|odgovori)\b", t, re.I):
        return None          # writing is the whatsapp-remote skill (drafts, never sent), not this reader
    m = re.search(r"\b(\d{1,2})\b", t)
    n = int(m.group(1)) if m else next((v for k, v in NUM_WORDS.items() if re.search(r"\b" + k + r"\b", t, re.I)), 5)
    n = max(1, min(n, 20))
    return say(latest(n), n)


def register(app):
    from flask import jsonify, request

    @app.post("/api/whatsapp/ax/latest")
    def wa_ax_latest():
        d = request.get_json(silent=True) or {}
        n = max(1, min(int(d.get("n", 5)), 20))
        r = latest(n)
        r["say"] = say(r, n)
        return jsonify(r)


if __name__ == "__main__":
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    r = latest(n)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    print(say(r, n))
