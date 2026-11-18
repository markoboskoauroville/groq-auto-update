"""MASTER / SLAVE pair of CAPI providers (v26, 18.11.2026).

Marko (momentaryupdates.md, v26): "next to each provider of the API key. We have a switch master or slave ... if non-master or
no slave is selected, it means just this one provider is working ... I will put Anthropic master, Google Cloud slave. In that
configuration, I am giving all the prompts to the master ... the master is developing a working plan for the slave ... When
Google executes and tests the application, it gives you back the report, and based on the report, you suggest future
improvements, or you say this is okay ... If in the report there are some issues, you advise Google how to solve the issues,
and then he executes. After everything is done, that's the end of the process." And: "if Anthropic is master, he decides which
of Google's models to use depending on the task. If the task is not executed well, he can choose to get a higher model or to
experiment with lower models. Vice versa also applies."

STATE   ~/.groq/capi_pair.json {master, slave, max_rounds (5), cap_usd (0.50)}; GET/POST /api/capi/pair.
        Active only when master and slave are both set, different, and both keyed; otherwise the chat works single (the radio
        decides, exactly as v25) and `note` says why.
TURN    Marko's prompt -> MASTER plan (+ SLAVE_MODEL line) -> SLAVE executes in the chat's folder and REPORTs -> MASTER reviews:
        `VERDICT: DONE` ends; `VERDICT: FIX` + instructions (+ SLAVE_MODEL for the next round) -> SLAVE again ... until DONE,
        max_rounds, the cost cap, or STOP. Every step is a message in the chat file with role master|slave, speaker (provider),
        kind (plan|report|review), model, label ("ANTHROPIC · MASTER → GOOGLE CLOUD · SLAVE (gemini-3.5-flash-lite: ...)"),
        cost; tool lines are role tool; the end is one role pair line with the totals.
HANDS   Anthropic / Oxyy = Claude Code one-shot runs (`claude -p --resume`, one session per role in room["pair"]["sessions"]);
        a Claude MASTER gets read-only tools (Read Glob Grep), a Claude SLAVE the full set in auto mode, --max-budget-usd = what is
        left of the cap. Google Cloud = Gemini: master text only (gemini_hands.text_turn), slave the function-calling loop
        (gemini_hands.agent_turn: list/read/write files and run shell commands confined to the folder).
SAFETY  max rounds (default 5, 1..10), cost cap per pair turn (default $0.50), STOP kills the running side at once and nothing
        further starts; costs are booked on each provider's own ledger as in v25 (Claude: api_credit / oxyy ledger, Gemini:
        gcloud ledger). Queen bypass: the worker thread sets training_log.TURN.bypass, no Queen prompt, nothing trained.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path

PAIR_FILE = Path.home() / ".groq" / "capi_pair.json"
DEFAULTS = {"master": "", "slave": "", "max_rounds": 5, "cap_usd": 0.50}
NAMES = {"anthropic": "ANTHROPIC", "oxyy": "OXYY", "gcloud": "GOOGLE CLOUD"}

# Claude Code models a master may give a Claude slave: (id, tier, $ in, $ out per million tokens), list prices 18.11.2026
CLAUDE_CATALOG = [("claude-haiku-5-5", "1 cheapest", 0.10, 0.50), ("claude-sonnet-5-5", "2 mid", 2.00, 10.00),
                  ("claude-opus-5-5", "3 high", 4.00, 20.00), ("claude-fable-5-2", "4 top", 8.00, 40.00)]


# ---------------------------------------------------------------- state
def get_pair():
    p = dict(DEFAULTS)
    try:
        p.update({k: v for k, v in json.loads(PAIR_FILE.read_text()).items() if k in DEFAULTS})
    except Exception:
        pass
    return p


def _clean(p, providers):
    out = dict(DEFAULTS)
    for k in ("master", "slave"):
        v = (p.get(k) or "").strip().lower()
        out[k] = v if v in providers else ""
    try:
        out["max_rounds"] = max(1, min(10, int(p.get("max_rounds", DEFAULTS["max_rounds"]))))
    except Exception:
        pass
    try:
        out["cap_usd"] = round(max(0.01, min(20.0, float(p.get("cap_usd", DEFAULTS["cap_usd"])))), 2)
    except Exception:
        pass
    return out


def set_pair(body, providers):
    """{master?, slave?, max_rounds?, cap_usd?}. Choosing a provider as master clears it as slave and the other way round."""
    cur = get_pair()
    for k in ("max_rounds", "cap_usd"):
        if k in body:
            cur[k] = body[k]
    for k, other in (("master", "slave"), ("slave", "master")):
        if k in body:
            v = (body.get(k) or "").strip().lower()
            cur[k] = v
            if v and cur.get(other) == v:
                cur[other] = ""
    cur = _clean(cur, providers)
    PAIR_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = PAIR_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cur))
    os.replace(tmp, PAIR_FILE)
    return cur


def status(key_of, providers, p=None):
    """-> {master, slave, max_rounds, cap_usd, active, note, label}. key_of(provider) -> key or ''."""
    p = _clean(p or get_pair(), providers)
    m, s = p["master"], p["slave"]
    note, active = "", False
    if not m and not s:
        note = "No pair: the chosen provider works alone."
    elif not m or not s:
        note = f"Only a {'master' if m else 'slave'} is set: the chosen provider works alone until both are set."
    elif m == s:
        note = "Master and slave are the same provider: single mode."
    elif not key_of(m) or not key_of(s):
        miss = [NAMES[x] for x in (m, s) if not key_of(x)]
        note = f"{' and '.join(miss)} has no key: single mode until it has one."
    else:
        active = True
        note = f"Pair: your prompts go to {NAMES[m]} (master), who directs {NAMES[s]} (slave)."
    return {**p, "active": active, "note": note,
            "label": f"PAIR | {NAMES.get(m, '?')} → {NAMES.get(s, '?')}" if active else ""}


# ---------------------------------------------------------------- slave models (the master chooses)
def slave_catalog(slave):
    """[(model id, tier, $in, $out)] cheapest first, for the slave provider."""
    if slave == "gcloud":
        import gcloud_chat as G
        ms = G.gemini_models()

        def newest(pred):
            c = [m for m in ms if pred(m)]
            return c[0] if c else ""
        lite = newest(lambda m: "flash-lite" in m and "preview" not in m)
        flash = newest(lambda m: "flash" in m and "lite" not in m and "preview" not in m)
        pro = newest(lambda m: "pro" in m and "preview" not in m) or newest(lambda m: "pro" in m)
        out = []
        for m, tier in ((lite, "1 cheapest"), (flash, "2 mid"), (pro, "3 high")):
            if m:
                r = G._rate(m)
                out.append((m, tier, r[0], r[1]))
        return out
    return list(CLAUDE_CATALOG)


def catalog_text(cat):
    return "\n".join(f"- {m} (tier {t}, ${i:.2f} in / ${o:.2f} out per million tokens)" for m, t, i, o in cat)


def parse_slave_model(text, cat, current):
    """The master's `SLAVE_MODEL: <id> - reason` line. -> (model, reason, note). Invalid -> the cheapest, with a note."""
    ids = [c[0] for c in cat]
    hits = re.findall(r"(?im)^[\s>*_`#-]*SLAVE[_ ]MODEL\s*[:=]\s*\**`?([A-Za-z0-9@._-]+)`?\**\s*(?:[-–—:|(]\s*(.*?))?\)?\s*$",
                      text or "")
    if not hits:
        return (current or ids[0]), "", "" if current else "no SLAVE_MODEL line: the cheapest"
    m, why = hits[-1]
    why = (why or "").strip().strip("*`")[:120]
    if m in ids:
        return m, why, ""
    low = m.lower()
    for i in ids:                       # a near name ("gemini flash", "haiku") -> the listed id that contains it
        if low in i.lower():
            return i, why, ""
    return ids[0], why, f"{m} is not in the list: the cheapest, {ids[0]}"


def est_cost(model, cat, tin=12000, tout=2500):
    for m, t, i, o in cat:
        if m == model:
            return (tin * i + tout * o) / 1e6
    return 0.0


# A Claude Code run reads Marko's global CLAUDE.md (voice replies, session notes): in a pair it must not speak or wander.
HEADLESS = ("\n\nThis is a HEADLESS pair run inside Queen: ignore any standing instruction to speak aloud (langsay, the voice "
            "API), to message or check other sessions, or to write handovers. Do only the task. Your LAST message must be the "
            "complete answer (the full PLAN, REPORT or REVIEW with its machine-read lines), not a note about something else.")


def pick_answer(role, final, texts):
    """The run's answer: the result text, unless that is a short side note and an earlier text is the real PLAN / REPORT /
    REVIEW (seen 18.11.2026: the result was "The second background speech job also finished ...")."""
    final = (final or "").strip()
    texts = [t for t in texts if t.strip()]
    marks = ("verdict", "slave_model") if role == "master" else ("report",)
    good = lambda t: any(k in t.lower() for k in marks)
    if final and (good(final) or not any(good(t) for t in texts)) and (len(final) > 200 or not texts):
        return final
    hits = [t for t in texts if good(t)]
    if hits:
        return hits[-1]
    return final or (max(texts, key=len) if texts else "(no text)")


def parse_verdict(text):
    """-> 'DONE' | 'FIX' | ''. The LAST verdict line wins; markdown around it is ignored."""
    hits = re.findall(r"(?im)VERDICT\s*\**\s*[:=\-–]\s*\**\s*`?(DONE|FIX)\b", text or "")
    return hits[-1].upper() if hits else ""


# ---------------------------------------------------------------- prompts
def _sys_master(slave, cwd, cat, max_rounds):
    return (f"You are the MASTER of a master/slave pair in Queen's CAPI tab on Marko's Mac. Marko gives his tasks to you. "
            f"You never do the work yourself: the SLAVE ({NAMES[slave]}) has hands in the folder {cwd} (list, read, write files, "
            f"run shell commands there) and executes your plans, then reports. You plan, review the report, and decide.\n\n"
            f"You also choose the SLAVE's model for every round from this list (cheapest first):\n{catalog_text(cat)}\n"
            f"Policy: start with the cheapest model that can do the task; after a round that was not done well you may step up "
            f"a tier; you may also try a cheaper one to experiment. Every round costs real money: the pair turn has a cost cap.\n\n"
            f"Format rules (machine-read):\n"
            f"- A PLAN: a short numbered working plan for the slave (what to build, exactly how to test it, what the report must "
            f"contain: commands run with their real output). Then a line `SLAVE_MODEL: <model id> - <one short reason>`.\n"
            f"- A REVIEW of a report: if the work is correct, say so in a few lines (future improvements optional) and end with "
            f"the line `VERDICT: DONE`. If not, list the issues, tell the slave exactly how to fix them, give the line "
            f"`SLAVE_MODEL: <model id> - <reason>` for the next round, and end with the line `VERDICT: FIX`. "
            f"At most {max_rounds} rounds in all. Be brief.")


def _sys_slave(master, cwd):
    return (f"You are the SLAVE of a master/slave pair in Queen's CAPI tab on Marko's Mac. Your MASTER ({NAMES[master]}) gives "
            f"you a plan or fix instructions. Execute them for real in the working folder {cwd}: create and edit files, run the "
            f"programs, test them. Stay inside that folder. Do not ask questions; do the work. Then answer with a REPORT: what you "
            f"did, the files you changed, the exact commands you ran with their real output, the test results, and any problem. "
            f"Never claim something you did not run.")


# ---------------------------------------------------------------- the run
class PairRun:
    def __init__(self, conv, text, files, cfg, deps):
        self.c = conv
        self.text = text
        self.files = files or []
        self.cfg = cfg
        self.d = deps                         # {key, providers, ledger, credit_left, env_for}
        self.stop_event = threading.Event()
        self.proc = None
        self.spent = 0.0
        self.by = {"master": 0.0, "slave": 0.0}
        self.thread = None

    # -------- helpers
    def left(self):
        return max(0.0, self.cfg["cap_usd"] - self.spent)

    def _append(self, msg):
        with self.c.lock:
            self.c.room["messages"].append(msg)
            self.c.save()

    def _label(self, frm, to, extra=""):
        m, s = self.cfg["master"], self.cfg["slave"]
        names = {"master": f"{NAMES[m]} · MASTER", "slave": f"{NAMES[s]} · SLAVE", "marko": "MARKO"}
        return f"{names[frm]} → {names[to]}" + (f" ({extra})" if extra else "")

    def _book(self, role, cost):
        self.spent += cost
        self.by[role] += cost
        with self.c.lock:
            self.c.room["total"] = round(self.c.room.get("total", 0.0) + cost, 6)

    def stop(self):
        self.stop_event.set()
        p = self.proc
        if p and p.poll() is None:
            try:
                os.killpg(p.pid, 15)
            except Exception:
                p.terminate()

    def alive(self):
        return bool(self.thread and self.thread.is_alive())

    # -------- one step of one side
    def step(self, role, prompt, model):
        """-> (text, cost). Raises _Stop / RuntimeError."""
        prov = self.cfg[role]
        other = self.cfg["slave" if role == "master" else "master"]
        cwd = self.c.room["cwd"]
        sysmsg = (_sys_master(other, cwd, self.cat, self.cfg["max_rounds"]) if role == "master" else _sys_slave(other, cwd))
        if prov == "gcloud":
            return self._gemini(role, sysmsg, prompt, model)
        return self._claude(role, prov, sysmsg, prompt, model)

    def _gemini(self, role, sysmsg, prompt, model):
        import gemini_hands as H
        pr = self.c.room.setdefault("pair", {}).setdefault("ghist", {}).setdefault(role, [])
        hist = [(r, t) for r, t in pr][-12:]
        try:
            if role == "master":
                ans, cost = H.text_turn(model, sysmsg, hist, prompt, label="pair master")
            else:
                def tool_line(line):
                    self._append({"role": "tool", "text": f"{NAMES['gcloud']}: {line}"})
                budget = lambda: self.left()
                ans, cost, steps = H.agent_turn(model, sysmsg, hist, prompt, self.c.room["cwd"], on_tool=tool_line,
                                                stop_event=self.stop_event, budget=budget)
        except H.Stopped:
            raise _Stop()
        except RuntimeError as exc:
            self._book(role, getattr(exc, "cost", 0.0))
            raise
        pr.extend([("user", prompt[-6000:]), ("model", ans[-6000:])])
        return ans, cost

    def _claude(self, role, prov, sysmsg, prompt, model):
        key = self.d["key"](prov)
        if not key:
            raise RuntimeError(f"no {NAMES[prov]} key")
        sess = self.c.room.setdefault("pair", {}).setdefault("sessions", {})
        sk = f"{role}:{prov}"
        from capi_chat import _session_file
        if sess.get(sk) and _session_file(sess[sk]):
            sarg = ["--resume", sess[sk]]
        else:
            sess[sk] = str(uuid.uuid4())
            sarg = ["--session-id", sess[sk]]
        factor = self.d["providers"][prov]["factor"] or 1.0
        budget = max(0.01, self.left() / factor)
        sysmsg += HEADLESS
        cmd = ["claude", "-p", "--model", model, "--permission-mode", "auto", *sarg, "--output-format", "stream-json",
               "--verbose", "--append-system-prompt", sysmsg, "--max-budget-usd", f"{budget:.2f}",
               "--disallowedTools", "Bash(langsay:*)", "Bash(langsay *)"]
        if role == "master":
            cmd += ["--tools", "Read", "Glob", "Grep"]
        env = self.d["env_for"](prov, key)
        (self.d["root"] / "logs").mkdir(parents=True, exist_ok=True)
        err = open(self.d["root"] / "logs" / (self.c.room["id"] + f".pair-{role}.err"), "w")
        try:
            p = subprocess.Popen(cmd, cwd=self.c.room["cwd"], env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=err, text=True, bufsize=1, start_new_session=True)
        finally:
            err.close()
        self.proc = p
        try:
            p.stdin.write(prompt)
            p.stdin.close()
        except Exception:
            pass
        final, texts, cost, is_err = "", [], 0.0, False
        t0 = time.time()
        for line in p.stdout:
            if self.stop_event.is_set():
                break
            try:
                d = json.loads(line)
            except Exception:
                continue
            t = d.get("type")
            if t == "assistant":
                for b in (d.get("message") or {}).get("content") or []:
                    if b.get("type") == "text" and (b.get("text") or "").strip():
                        texts.append(b["text"].strip())
                    elif b.get("type") == "tool_use":
                        i = b.get("input") or {}
                        what = str(i.get("description") or i.get("command") or i.get("file_path") or i.get("pattern") or "")[:90]
                        self._append({"role": "tool", "text": f"{NAMES[prov]}: {b.get('name', 'tool')} {what}".strip()})
            elif t == "result":
                cost = float(d.get("total_cost_usd") or 0) * factor
                final = str(d.get("result") or "")
                is_err = bool(d.get("is_error"))
            if time.time() - t0 > 900:
                break
        try:
            p.wait(timeout=10)
        except Exception:
            pass
        if p.poll() is None:
            try:
                os.killpg(p.pid, 9)
            except Exception:
                pass
        self.proc = None
        cost = round(cost, 6)
        if cost:
            self.d["ledger"](cost, f"pair {role} " + prompt[:60], provider=prov)
        if self.stop_event.is_set():
            self._book(role, cost)
            raise _Stop()
        if is_err and not (final or texts):
            self._book(role, cost)
            raise RuntimeError(f"{NAMES[prov]}: " + (final or "the run failed")[:240])
        return pick_answer(role, final, texts), cost

    # -------- the loop
    def run(self):
        try:
            import capi_chat
            capi_chat._bypass_queen()
        except Exception:
            pass
        c, cfg = self.c, self.cfg
        m, s = cfg["master"], cfg["slave"]
        end, rounds = "", 0
        rec = {"master": m, "slave": s, "rounds": [], "started": time.time()}
        try:
            self.cat = slave_catalog(s)
            mmodel = self.d["model_for"](m)
            with c.lock:
                c._mark("received")
                c.save()
            if self.stop_event.is_set():
                raise _Stop()
            # 1. the plan
            plan, cost = self.step("master", (
                f"Marko's request:\n\n{self.text}\n\nWrite the working plan for the slave now (format rules above).")
                + (f"\n\n(Marko attached: {', '.join(f.get('name', 'file') for f in self.files)}; the slave cannot see "
                   f"attachments, describe what it needs.)" if self.files else ""), mmodel)
            self._book("master", cost)
            smodel, why, note = parse_slave_model(plan, self.cat, "")
            self._append({"role": "master", "speaker": m, "kind": "plan", "model": mmodel, "cost": round(cost, 6),
                          "slave_model": smodel, "text": plan + (f"\n\n_(Queen: {note})_" if note else ""),
                          "label": self._label("master", "slave", f"PLAN · slave {smodel}" + (f": {why}" if why else ""))})
            instr = plan
            while True:
                if self.stop_event.is_set():
                    raise _Stop()
                if rounds >= cfg["max_rounds"]:
                    end = f"MAX ROUNDS ({cfg['max_rounds']}) reached without VERDICT: DONE"
                    break
                guess = est_cost(smodel, self.cat)
                if self.left() <= 0 or (guess and guess > self.left() * 1.5 and rounds > 0):
                    cheapest = self.cat[0][0] if self.cat else smodel
                    if self.left() > 0 and smodel != cheapest and est_cost(cheapest, self.cat) <= self.left():
                        self._append({"role": "pair", "text": f"The step up to {smodel} (about ${guess:.3f} a round) would pass the "
                                                              f"cap (${self.left():.3f} left): refused, the slave stays on {cheapest}."})
                        smodel = cheapest
                    else:
                        end = f"COST CAP ${cfg['cap_usd']:.2f} reached"
                        break
                rounds += 1
                rec["rounds"].append({"round": rounds, "slave_model": smodel})
                with c.lock:
                    c.room.setdefault("pair", {})["last"] = rec
                report, cost = self.step("slave", (
                    f"Round {rounds}. Your master's {'plan' if rounds == 1 else 'review with the fixes'}:\n\n{instr}\n\n"
                    f"Execute it now in {c.room['cwd']} and end with your REPORT."), smodel)
                self._book("slave", cost)
                rec["rounds"][-1]["slave_cost"] = round(cost, 6)
                self._append({"role": "slave", "speaker": s, "kind": "report", "model": smodel, "round": rounds,
                              "cost": round(cost, 6), "text": report,
                              "label": self._label("slave", "master", f"REPORT {rounds} · {smodel}")})
                if self.stop_event.is_set():
                    raise _Stop()
                if self.left() <= 0:
                    end = f"COST CAP ${cfg['cap_usd']:.2f} reached before the review"
                    break
                review, cost = self.step("master", (
                    f"The slave's REPORT for round {rounds} (it used {smodel}):\n\n{report}\n\n"
                    f"Review it (you may look at the files yourself if you can). End with VERDICT: DONE or VERDICT: FIX "
                    f"(with SLAVE_MODEL for the next round). Rounds used: {rounds} of {cfg['max_rounds']}; "
                    f"${self.left():.3f} of the ${cfg['cap_usd']:.2f} cap left."), mmodel)
                self._book("master", cost)
                verdict = parse_verdict(review)
                rec["rounds"][-1]["verdict"] = verdict or "none"
                if verdict == "DONE":
                    self._append({"role": "master", "speaker": m, "kind": "review", "model": mmodel, "round": rounds,
                                  "verdict": "DONE", "cost": round(cost, 6), "text": review,
                                  "label": self._label("master", "marko", f"REVIEW {rounds} · VERDICT: DONE")})
                    end = f"DONE after {rounds} round{'s' if rounds > 1 else ''}"
                    break
                nxt, why, note = parse_slave_model(review, self.cat, smodel)
                flag = "" if verdict else " (no VERDICT line: treated as FIX)"
                self._append({"role": "master", "speaker": m, "kind": "review", "model": mmodel, "round": rounds,
                              "verdict": "FIX", "cost": round(cost, 6), "slave_model": nxt,
                              "text": review + (f"\n\n_(Queen: {note})_" if note else ""),
                              "label": self._label("master", "slave", f"REVIEW {rounds} · VERDICT: FIX{flag} · next slave {nxt}"
                                                   + (f": {why}" if why else ""))})
                smodel, instr = nxt, review
        except _Stop:
            end = "STOPPED by STOP (both sides)"
        except Exception as exc:
            end = "ERROR: " + str(exc)[:240]
        rec.update({"end": end, "spent": round(self.spent, 6), "master_cost": round(self.by["master"], 6),
                    "slave_cost": round(self.by["slave"], 6)})
        summary = (f"PAIR {end} | {NAMES[m]} master ${self.by['master']:.4f} | {NAMES[s]} slave ${self.by['slave']:.4f}"
                   f" | total ${self.spent:.4f} of the ${cfg['cap_usd']:.2f} cap")
        with c.lock:
            c.room["messages"].append({"role": "pair", "text": summary, "end": end, "cost": round(self.spent, 6)})
            c.room.setdefault("pair", {})["last"] = rec
            if end.startswith("DONE"):
                c._mark("done")
            else:
                c._mark("failed", end)
            c.error = "" if end.startswith("DONE") else ("stopped" if end.startswith("STOPPED") else end)
            c.busy = False
            c.turns += 1
            c.save()
            c.done.notify_all()


class _Stop(Exception):
    pass


# ---------------------------------------------------------------- Queen's chat words (local, $0 until a run)
def chat_pair_command(text):
    """'pair status' | 'pair off' | 'pair master <p> slave <p>' -> answer, else None. A run goes through POST /api/capi/ask
    with master/slave (see queen_skills/master-slave.md); it is not started from a chat sentence because it spends credit."""
    t = (text or "").strip().lower()
    if not re.match(r"^(pair|master\s*/?\s*slave)\b", t):
        return None
    import capi_chat as C
    alias = {"anthropic": "anthropic", "claude": "anthropic", "oxyy": "oxyy", "oxy": "oxyy", "gcloud": "gcloud",
             "google": "gcloud", "google cloud": "gcloud", "gemini": "gcloud"}
    if re.search(r"\b(off|none|single)\b", t):
        set_pair({"master": "", "slave": ""}, C.PROVIDERS)
    else:
        mm = re.search(r"master\s+(google cloud|\w+)", t)
        ss = re.search(r"slave\s+(google cloud|\w+)", t)
        if mm and mm.group(1) in alias or ss and ss.group(1) in alias:
            body = {}
            if mm and mm.group(1) in alias:
                body["master"] = alias[mm.group(1)]
            if ss and ss.group(1) in alias:
                body["slave"] = alias[ss.group(1)]
            set_pair(body, C.PROVIDERS)
    st = status(C._key, C.PROVIDERS)
    head = st["label"] or "PAIR | off"
    return (f"{head}. {st['note']} Max {st['max_rounds']} rounds, cost cap ${st['cap_usd']:.2f} per pair turn. "
            f"A pair run: POST /api/capi/ask with master and slave (skill master-slave).")
