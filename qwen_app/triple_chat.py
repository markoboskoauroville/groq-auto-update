"""TRIPLE CHAT (17.11.2026): one room, three brains: Marko, Queen (Groq) and Claude (local Claude Code or API).

Marko: "there is me in the chat room, there is Claude over API, and there is Groq Queen ... we all can hear each other
and comment on each other's thoughts." The whole history is in every prompt, so each brain sees what the others said.

Routes (all under /api/triple/, the Swift app proxies unknown routes here):
    GET  /api/triple/list
    GET  /api/triple/get?id=
    POST /api/triple/new       {title?}
    POST /api/triple/settings  {id, claude_via: local|api, claude_model}
    POST /api/triple/turn      {id, text, to: queen|claude|both|auto, allow_api?, resume?}  -> NDJSON
         {"speaker":"queen","start":1} {"t":"..."} {"need_consent":"..."} {"error":"..."} {"done":1}
Rules: Claude local first (plan, $0); local unreachable -> need_consent and wait; API key never printed.
Queen may write a line `ASK CLAUDE: <question>`: Claude answers in the room and Queen continues (max 3 per turn).
Claude's `ASK QUEEN: <question>` lines run only when Marko presses ASK QUEEN (a turn with empty text, to=queen).
"""
from __future__ import annotations

import json
import re
import secrets
import time
from pathlib import Path

from flask import Response, jsonify, request

ROOT = Path.home() / ".groq" / "triple"
CLAUDE_MODELS = ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-2"]
DEFAULT_CLAUDE_MODEL = "claude-sonnet-5-5"
MAX_ASK_CHAIN = 3
HISTORY_CHARS = 24000   # the tail of the room that goes into each prompt

_QUEEN_RE = re.compile(r"\b(queen|qwen|quinn|kvin|kvin)\b[,:!]?", re.I)
_CLAUDE_RE = re.compile(r"\b(claude|cloud|klod|claud)\b[,:!]?", re.I)
_QUEEN_NAMES = ("queen", "qwen", "quinn", "kvin")
_LEAD_RE = re.compile(r"^\W*(queen|qwen|quinn|kvin|claude|cloud|klod|claud)\b(?!\s*(?:,\s*(?:and|&|\+)?|and|&|\+)\s*(?:queen|qwen|quinn|kvin|claude|cloud|klod|claud)\b)", re.I)
_BOTH_RE = re.compile(r"\b(both|everyone|everybody|you two|all of you)\b", re.I)

ROOM_NOTE = (
    "\n\nTRIPLE CHAT: you are in a room with three brains. Marko is the CEO and asks. Queen is the Groq model "
    "that runs on Marko's Mac and executes (her local commands, skills, GitHub, the computer). Claude is the Anthropic "
    "model that advises, plans and reviews. The room history below is shared: everyone hears everyone, comment on each "
    "other's thoughts when it helps, briefly, in plain text. Answer only as {me}; never write the other speakers' lines.")
QUEEN_ASK = ("\nIf you need Claude's advice, put ONE line `ASK CLAUDE: <your question>` at the end of your answer; "
             "Claude will answer in the room and you will continue.")
CLAUDE_ASK = ("\nIf Queen should do or answer something, put ONE line `ASK QUEEN: <the question or task>` at the end; "
              "it runs only when Marko presses the ASK QUEEN button.")


def _now():
    return int(time.time())


def _path(rid: str) -> Path:
    rid = re.sub(r"[^a-zA-Z0-9_-]", "", rid or "")
    return ROOT / f"{rid}.json"


def _load(rid: str):
    try:
        return json.loads(_path(rid).read_text(encoding="utf-8"))
    except Exception:
        return None


def _save(room: dict):
    ROOT.mkdir(parents=True, exist_ok=True)
    p = _path(room["id"])
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(room, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def new_room(title: str = "") -> dict:
    room = {"id": time.strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2), "title": (title or "").strip() or "Triple chat",
            "claude_via": "local", "claude_model": DEFAULT_CLAUDE_MODEL, "last_addressed": "queen",
            "created": _now(), "updated": _now(), "messages": []}
    _save(room)
    return room


def recover_room(rid: str):
    """A room id the window still holds but the server lost (deleted, cleaned, new machine): recreate it empty under the
    same id so the window keeps working instead of showing a bare 404. Returns None only for an empty id."""
    clean = re.sub(r"[^a-zA-Z0-9_-]", "", rid or "")
    if not clean:
        return None
    room = {"id": clean, "title": "Triple chat", "claude_via": "local", "claude_model": DEFAULT_CLAUDE_MODEL,
            "last_addressed": "queen", "created": _now(), "updated": _now(), "messages": [], "recovered": True}
    _save(room)
    return room


def parse_addressing(text: str, last: str = "queen") -> str:
    """queen | claude | both. Names anywhere in the text; none -> whoever was addressed last."""
    q, c = bool(_QUEEN_RE.search(text)), bool(_CLAUDE_RE.search(text))
    if _BOTH_RE.search(text):
        return "both"
    if q and c:
        # "Queen, please ask Claude ..." speaks to Queen only; "Queen and Claude, ..." speaks to both
        lead = _LEAD_RE.match(text)
        if lead:
            return "queen" if lead.group(1).lower() in _QUEEN_NAMES else "claude"
        return "both"
    if q:
        return "queen"
    if c:
        return "claude"
    return last if last in ("queen", "claude", "both") else "queen"


def _transcript(room: dict) -> str:
    names = {"marko": "Marko", "queen": "Queen", "claude": "Claude"}
    lines = [f"[{names.get(m['speaker'], m['speaker'])}]: {m['text']}" for m in room["messages"] if m.get("text")]
    out = "\n\n".join(lines)
    return out[-HISTORY_CHARS:]


def _strip_think(s: str) -> str:
    return re.sub(r"<think>.*?</think>", "", s or "", flags=re.S).strip()


class _ThinkFilter:
    """Hides <think>...</think> from the live stream (the stored text is stripped the same way)."""
    def __init__(self):
        self.buf, self.inside = "", False

    def feed(self, tok: str, final: bool = False) -> str:
        self.buf += tok
        out = ""
        while True:
            if self.inside:
                i = self.buf.find("</think>")
                if i < 0:
                    self.buf = "" if final else self.buf[-8:]
                    return out
                self.buf, self.inside = self.buf[i + 8:], False
            else:
                i = self.buf.find("<think>")
                if i >= 0:
                    out += self.buf[:i]
                    self.buf, self.inside = self.buf[i + 7:], True
                    continue
                keep = 0 if final else next((k for k in range(6, 0, -1) if "<think>".startswith(self.buf[-k:])), 0)
                out += self.buf[:len(self.buf) - keep]
                self.buf = self.buf[len(self.buf) - keep:]
                return out


def _line(kind: str, text: str):
    m = re.search(rf"^\s*{kind}\s*:\s*(.+)$", text or "", re.M | re.I)
    return m.group(1).strip() if m else ""


def register(app, pool, build_queen_system_prompt, record_spend, local_command_answer, after_turn,
             default_model, max_tokens):
    import claude_link

    def ndj(o):
        return json.dumps(o, ensure_ascii=False) + "\n"

    # ---------- the two voices ----------
    def queen_speak(room, tail):
        """Yield ('t', text) tokens, then ('end', full_text). Groq with key failover, spend recorded."""
        from groq import Groq
        model = default_model
        system = build_queen_system_prompt("") + ROOM_NOTE.format(me="Queen") + QUEEN_ASK
        user = f"ROOM SO FAR:\n{_transcript(room)}\n\n{tail}\n\nNow answer as Queen."
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        cands = pool.candidates(model)
        if not cands:
            raise RuntimeError("All Groq keys are cooling down. Wait or import another key.")
        last_exc = None
        for key in cands:
            got = []
            pt = ct = 0
            try:
                client = Groq(api_key=key, max_retries=0)
                resp = client.chat.completions.create(model=model, messages=msgs, stream=True, max_tokens=max_tokens)
                for chunk in resp:
                    if chunk.choices:
                        d = chunk.choices[0].delta
                        if getattr(d, "content", None):
                            got.append(d.content)
                            yield ("t", d.content)
                    u = getattr(chunk, "usage", None) or getattr(getattr(chunk, "x_groq", None), "usage", None)
                    if u:
                        pt = int(getattr(u, "prompt_tokens", 0) or pt)
                        ct = int(getattr(u, "completion_tokens", 0) or ct)
                pool.good(key, model)
                full = "".join(got)
                if not (pt or ct):
                    pt, ct = len(user + system) // 4, max(1, len(full) // 4)
                record_spend(model, pt, ct, f"triple_queen_{_now()}")
                yield ("end", full)
                return
            except Exception as exc:
                last_exc = exc
                pool.cool(key, model, exc)
                if got:
                    raise RuntimeError(f"Queen's stream broke: {exc}")
        raise RuntimeError(f"Queen could not be reached: {last_exc}")

    def claude_api(room, tail, model):
        import httpx
        from auto_updater import load_auto_update_store
        keys = (load_auto_update_store().get("keys") or {}).get("anthropic") or []
        if not keys:
            raise RuntimeError("No Anthropic API key in the auto-update store.")
        system = ("You are Claude, one of three brains in Marko's TRIPLE CHAT." + ROOM_NOTE.format(me="Claude") + CLAUDE_ASK)
        user = f"ROOM SO FAR:\n{_transcript(room)}\n\n{tail}\n\nNow answer as Claude."
        headers = {"x-api-key": keys[0], "anthropic-version": "2023-06-01", "content-type": "application/json"}
        payload = {"model": model, "max_tokens": 4000, "system": system, "stream": True,
                   "messages": [{"role": "user", "content": user}]}
        got, pt, ct = [], 0, 0
        with httpx.Client(timeout=240.0) as client:
            with client.stream("POST", "https://api.anthropic.com/v1/messages", headers=headers, json=payload) as resp:
                if resp.status_code >= 400:
                    body = resp.read().decode("utf-8", errors="replace")
                    body = body.replace(keys[0], "***")
                    raise RuntimeError(f"Anthropic API HTTP {resp.status_code}: {body[:300]}")
                for raw in resp.iter_lines():
                    if not raw or not raw.startswith("data:"):
                        continue
                    try:
                        evt = json.loads(raw[5:].strip())
                    except Exception:
                        continue
                    et = evt.get("type")
                    if et == "message_start":
                        u = (evt.get("message") or {}).get("usage") or {}
                        pt = int(u.get("input_tokens") or pt)
                    elif et == "content_block_delta":
                        dl = evt.get("delta") or {}
                        if dl.get("type") == "text_delta" and dl.get("text"):
                            got.append(dl["text"])
                            yield ("t", dl["text"])
                    elif et == "message_delta":
                        u = evt.get("usage") or {}
                        ct = int(u.get("output_tokens") or ct)
        record_spend(model, pt, ct, f"triple_claude_{_now()}")
        yield ("end", "".join(got))

    def claude_speak(room, tail):
        via, model = room.get("claude_via", "local"), room.get("claude_model", DEFAULT_CLAUDE_MODEL)
        if via == "api":
            yield from claude_api(room, tail, model)
            return
        if not claude_link.status()["reachable"]:
            raise claude_link.NeedConsent()
        prompt = ("You are Claude, one of three brains in Marko's TRIPLE CHAT." + ROOM_NOTE.format(me="Claude") + CLAUDE_ASK +
                  f"\n\nROOM SO FAR:\n{_transcript(room)}\n\n{tail}\n\nNow answer as Claude.")
        r = claude_link.ask(prompt, model=model)
        text = (r.get("answer") or "").strip()
        yield ("t", text)
        yield ("end", text)

    # ---------- one speaker's turn, with persistence ----------
    def speak(room, who, tail):
        """Generator of NDJSON lines; appends the message to the room when finished."""
        yield ndj({"speaker": who, "start": 1})
        gen = queen_speak(room, tail) if who == "queen" else claude_speak(room, tail)
        full = ""
        flt = _ThinkFilter()
        shown = False
        for kind, val in gen:
            if kind == "t":
                vis = flt.feed(val)
                if not shown:
                    vis = vis.lstrip()
                if vis:
                    shown = True
                    yield ndj({"t": vis})
            else:
                full = val
        tail_vis = flt.feed("", final=True)
        if tail_vis:
            yield ndj({"t": tail_vis})
        full = _strip_think(full)
        if who == "queen":
            # her own answer is her hand: command lines run, results are part of the answer (as in her normal chat)
            try:
                extra = "".join(after_turn(_last_marko(room), full, default_model, "normal"))
            except Exception as exc:
                extra = f"\n\n▶ the command could not run: {type(exc).__name__}: {exc}"
            if extra:
                full += extra
                yield ndj({"t": extra})
        room["messages"].append({"speaker": who, "text": full, "ts": _now()})
        room["updated"] = _now()
        _save(room)
        return full

    def _last_marko(room):
        for m in reversed(room["messages"]):
            if m["speaker"] == "marko":
                return m["text"]
        return ""

    def run_turn(room, text, to, allow_api, resume=False):
        if allow_api and room.get("claude_via") != "api":
            room["claude_via"] = "api"
        text = (text or "").strip()
        tail = ""
        if text:
            room["messages"].append({"speaker": "marko", "text": text, "ts": _now()})
            if to == "auto" or to not in ("queen", "claude", "both"):
                to = parse_addressing(text, room.get("last_addressed", "queen"))
            room["last_addressed"] = to
            # Queen's local chat commands (open app, rename, ...) answer straight away at $0
            if to in ("queen", "both"):
                try:
                    local = local_command_answer(text)
                except Exception:
                    local = None
                if local:
                    room["messages"].append({"speaker": "queen", "text": local, "ts": _now()})
                    _save(room)
                    yield ndj({"speaker": "queen", "start": 1})
                    yield ndj({"t": local})
                    if to == "queen":
                        yield ndj({"done": 1})
                        return
                    to = "claude"
        elif resume:
            # Marko said YES to API credits: Claude answers the message that is already in the room (no duplicate)
            to = "claude"
            tail = "Answer the latest message above that is addressed to you (or the question Queen asked you)."
        else:
            # empty text + to=queen: the ASK QUEEN button, she answers Claude's last ASK QUEEN line
            q = ""
            for m in reversed(room["messages"]):
                if m["speaker"] == "claude":
                    q = _line("ASK QUEEN", m["text"])
                    break
            if not q or to != "queen":
                yield ndj({"error": "Nothing to ask: write a message first."})
                return
            tail = f"Claude asks Queen: {q}"
            room["last_addressed"] = "queen"
        _save(room)
        order = ["queen", "claude"] if to == "both" else [to]
        chain = 0
        try:
            i = 0
            while i < len(order):
                who = order[i]
                full = yield from speak(room, who, tail)
                tail = ""
                if who == "queen" and chain < MAX_ASK_CHAIN:
                    q = _line("ASK CLAUDE", full)
                    if q:
                        chain += 1
                        # Claude answers Queen in the room, then she continues
                        full_c = yield from speak(room, "claude", f"Queen asks Claude: {q}")
                        order[i + 1:i + 1] = ["queen"]
                        tail = "Claude has answered your question above. Continue and finish the task."
                i += 1
        except claude_link.NeedConsent:
            _save(room)
            yield ndj({"need_consent": claude_link.CONSENT_TEXT})
            return
        except Exception as exc:
            _save(room)
            yield ndj({"error": f"{type(exc).__name__}: {exc}"})
            return
        yield ndj({"done": 1})

    # ---------- routes ----------
    @app.get("/api/triple/list")
    def triple_list():
        ROOT.mkdir(parents=True, exist_ok=True)
        rooms = []
        for p in ROOT.glob("*.json"):
            try:
                r = json.loads(p.read_text(encoding="utf-8"))
                rooms.append({"id": r["id"], "title": r.get("title", ""), "updated": r.get("updated", 0),
                              "count": len(r.get("messages", []))})
            except Exception:
                continue
        rooms.sort(key=lambda r: r["updated"], reverse=True)
        return jsonify(ok=True, rooms=rooms, models=CLAUDE_MODELS)

    @app.get("/api/triple/get")
    def triple_get():
        room = _load(request.args.get("id", ""))
        if not room:
            return jsonify(ok=False, error="no such room"), 404
        return jsonify(ok=True, room=room, models=CLAUDE_MODELS, local_claude=claude_link.status()["reachable"])

    @app.post("/api/triple/new")
    def triple_new():
        d = request.get_json(silent=True) or {}
        return jsonify(ok=True, room=new_room(d.get("title", "")), models=CLAUDE_MODELS)

    @app.post("/api/triple/settings")
    def triple_settings():
        d = request.get_json(silent=True) or {}
        room = _load(d.get("id", "")) or recover_room(d.get("id", ""))
        if not room:
            return jsonify(ok=False, error="no such room"), 404
        if d.get("claude_via") in ("local", "api"):
            room["claude_via"] = d["claude_via"]
        if d.get("claude_model") in CLAUDE_MODELS:
            room["claude_model"] = d["claude_model"]
        if isinstance(d.get("title"), str) and d["title"].strip():
            room["title"] = d["title"].strip()[:80]
        _save(room)
        return jsonify(ok=True, room=room)

    @app.post("/api/triple/turn")
    def triple_turn():
        d = request.get_json(silent=True) or {}
        room = _load(d.get("id", "")) or recover_room(d.get("id", ""))
        if not room:
            return jsonify(ok=False, error="no such room"), 404
        return Response(run_turn(room, d.get("text", ""), d.get("to", "auto"), bool(d.get("allow_api")),
                                 bool(d.get("resume"))),
                        mimetype="application/x-ndjson", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
