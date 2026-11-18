"""Queen's outputs and Claude Code's (Opus) corrections, recorded as training data (13.11.2026).

Marko: "an automated workflow where Qwen's output and its corrections by the Opus model are recorded in a GitHub repository.
The code should log each Qwen output, capture Opus's correction, and prepare a dataset for periodic fine-tuning. Include steps
for data storage, versioning, and triggering the training process."

STORAGE   ~/.groq/training/events/<date>.jsonl, append-only, one JSON object per line, mirrored within a minute to the PRIVATE
          repository markoboskoauroville/groq_ai_studio_data (data_sync.py; keys replaced by [KEY REMOVED]). Kinds:
            output      one chat turn: turn id, model, the prompt (Marko's words), Queen's full answer, her skills' hash
            verdict     the supervisor's decision on one of her proposals (approve/reject + note), linked to its turn
            correction  the better answer Claude Code wrote for a turn (`queen correct <turn|last> "<better answer>"`)
DATASETS  build_dataset.py -> ~/.groq/training/datasets/v<N>/ (whole numbers): sft.jsonl (chat messages to imitate),
          dpo.jsonl (prompt, chosen, rejected, why), manifest.json (counts, sha256, the events used). Git tag dataset-v<N>.
TRIGGER   maybe_build(): after every sync; when THRESHOLD new examples have come in since the last version, the next version is
          built and a training job (training/jobs/v<N>.md, the exact command) is written. The run itself waits for Marko's
          word: it downloads a base model and computes for hours (MANTRA_MANIFEST spend-guard, SIM data).
"""
import hashlib
import json
import threading
import time
import uuid
from pathlib import Path

ROOT = Path.home() / ".groq" / "training"
EVENTS = ROOT / "events"
SKILLS = Path.home() / ".groq" / "queen_skills"
TURN = threading.local()      # the chat turn whose commands are running (tasks carry it into their threads)
_LOCK = threading.Lock()


def new_turn():
    return "t" + time.strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:6]


def _skills_hash():
    h = hashlib.sha256()
    for p in sorted(SKILLS.glob("*.md")):
        h.update(p.read_bytes())
    return h.hexdigest()[:12]


def record(kind, **data):
    """Append one event. Never raises: logging must not break a chat.
    v25 (18.11.2026): a thread marked TURN.bypass (every /api/capi/* request and CAPI worker thread) records NOTHING: CAPI chats
    (Anthropic / Google Cloud) are a bypass of Queen and never train her."""
    if getattr(TURN, "bypass", False):
        return
    try:
        EVENTS.mkdir(parents=True, exist_ok=True)
        ev = {"kind": kind, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), **data}
        with _LOCK, (EVENTS / f"{time.strftime('%Y-%m-%d')}.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        from data_sync import mark_dirty  # noqa: PLC0415
        mark_dirty()
    except Exception as exc:  # pragma: no cover
        print(f"[training] not recorded: {exc}", flush=True)


def log_output(turn, prompt, output, model, mode="normal"):
    record("output", turn=turn, prompt=prompt, output=output, model=model, mode=mode, skills=_skills_hash())


def log_verdict(rec):
    record("verdict", turn=rec.get("turn"), proposal=rec.get("id"), task=rec.get("task"), step=rec.get("step"),
           summary=rec.get("summary"), detail=(rec.get("detail") or "")[:8000], decision=rec.get("status"),
           note=rec.get("note", ""), by=rec.get("by", ""))


def log_correction(turn, better, by="Claude Code (Opus)", why=""):
    record("correction", turn=turn, better=better, by=by, why=why)


def events():
    out = []
    for p in sorted(EVENTS.glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def last_turn():
    for ev in reversed(events()):
        if ev["kind"] == "output":
            return ev["turn"]
    return None


def register(app):
    from flask import jsonify, request  # noqa: PLC0415

    @app.post("/api/training/correct")
    def training_correct():
        d = request.get_json(silent=True) or {}
        turn = d.get("turn") or "last"
        if turn == "last":
            turn = last_turn()
        if not turn or not (d.get("better") or "").strip():
            return jsonify(ok=False, error="need a turn and the better answer"), 400
        log_correction(turn, d["better"].strip(), d.get("by") or "Claude Code (Opus)", d.get("why", ""))
        return jsonify(ok=True, turn=turn)

    @app.get("/api/training/status")
    def training_status():
        import build_dataset  # noqa: PLC0415
        return jsonify(ok=True, **build_dataset.status())

    @app.post("/api/training/build")
    def training_build():
        import build_dataset  # noqa: PLC0415
        return jsonify(ok=True, **build_dataset.build(force=bool((request.get_json(silent=True) or {}).get("force"))))
    return app
