"""Offline tests of the v26 MASTER / SLAVE pair (no network, no cost): verdict and SLAVE_MODEL parsing, pair state rules,
the Gemini slave's folder confinement and shell guard."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pair_chat as P  # noqa: E402
import gemini_hands as H  # noqa: E402

ok = True


def check(name, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + name)
    ok = ok and bool(cond)


check("verdict done", P.parse_verdict("All good.\n\nVERDICT: DONE") == "DONE")
check("verdict bold markdown", P.parse_verdict("**VERDICT:** FIX") == "FIX")
check("verdict last wins", P.parse_verdict("VERDICT: FIX\n...\nVERDICT: DONE") == "DONE")
check("pick report over side note", P.pick_answer("slave", "The background speech job finished.",
      ["REPORT: wrote hello.py, ran it: 4", "The background speech job finished."]).startswith("REPORT"))
check("pick final when good", P.pick_answer("master", "x" * 250 + "\nVERDICT: DONE", ["plan"]).endswith("DONE"))
check("verdict missing", P.parse_verdict("looks fine") == "")
cat = [("gemini-3.5-flash-lite", "1", .1, .4), ("gemini-3.8-flash", "2", .3, 2.5), ("gemini-3.1-pro-preview", "3", 1.25, 10)]
check("slave model + reason", P.parse_slave_model("plan\nSLAVE_MODEL: gemini-3.8-flash - needs care", cat, "")[:2]
      == ("gemini-3.8-flash", "needs care"))
check("slave model backticks", P.parse_slave_model("`SLAVE_MODEL: gemini-3.1-pro-preview`", cat, "")[0] == "gemini-3.1-pro-preview")
m, why, note = P.parse_slave_model("SLAVE_MODEL: gpt-9 - x", cat, "")
check("slave model invalid -> cheapest with note", m == "gemini-3.5-flash-lite" and note)
check("slave model missing keeps current", P.parse_slave_model("no line", cat, "gemini-3.8-flash")[0] == "gemini-3.8-flash")
provs = {"anthropic": {}, "oxyy": {}, "gcloud": {}}
key = lambda p: "k" if p in ("anthropic", "gcloud") else ""
check("pair active", P.status(key, provs, {"master": "anthropic", "slave": "gcloud"})["active"])
check("pair same -> single", not P.status(key, provs, {"master": "gcloud", "slave": "gcloud"})["active"])
check("pair no key -> single", not P.status(key, provs, {"master": "oxyy", "slave": "gcloud"})["active"])
check("pair only master -> single", not P.status(key, provs, {"master": "anthropic", "slave": ""})["active"])
check("label", P.status(key, provs, {"master": "gcloud", "slave": "anthropic"})["label"] == "PAIR | GOOGLE CLOUD → ANTHROPIC")

with tempfile.TemporaryDirectory(dir=str(Path.home())) as d:
    root, why = H.folder_ok(d)
    check("folder ok", root and not why)
    check("home refused", not H.folder_ok(str(Path.home()))[0])
    check("outside home refused", not H.folder_ok("/tmp")[0])
    res, line = H.tool(root, "write_file", {"path": "a/hello.py", "content": "print(2+2)\n"})
    check("write inside", res.get("ok"))
    res, line = H.tool(root, "run_shell", {"command": "python3 a/hello.py"})
    check("run shell", res.get("exit_code") == 0 and res.get("output", "").strip() == "4")
    res, _ = H.tool(root, "write_file", {"path": "../escape.txt", "content": "x"})
    check("write outside refused", "error" in res and not os.path.exists(os.path.join(os.path.dirname(root), "escape.txt")))
    res, _ = H.tool(root, "read_file", {"path": "/etc/hosts"})
    check("read outside refused", "error" in res)
    check("sudo refused", "error" in H.tool(root, "run_shell", {"command": "sudo ls"})[0])
    check("abs path refused", "error" in H.tool(root, "run_shell", {"command": "cat ~/.zshrc"})[0])
    check("dotdot refused", "error" in H.tool(root, "run_shell", {"command": "ls ../"})[0])
    check("usr bin allowed", H.tool(root, "run_shell", {"command": "/usr/bin/true"})[0].get("exit_code") == 0)
    res, _ = H.tool(root, "run_shell", {"command": "sleep 5", "timeout": 1})
    check("timeout", res.get("timed_out"))
    check("list", "a/" in H.tool(root, "list_files", {})[0].get("entries", []))

import gcloud_chat as G
old_gm = G.gemini_models
try:
    G.gemini_models = lambda: ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-2.5-pro", "gemini-3.1-pro-preview"]
    sc = P.slave_catalog("gcloud")
    t3 = [m for m, tier, _, _ in sc if "3" in tier]
    check("slave catalog skips retired pro", t3 == ["gemini-3.1-pro-preview"])
finally:
    G.gemini_models = old_gm

old_recovery = H._call_with_recovery
old_cost = H._usage_cost
old_ledger = G.ledger
try:
    def mock_recovery(model, body, notice_cb=None):
        if body.get("toolConfig"):
            return {"candidates": [{"content": {"parts": [{"text": "FINAL REPORT"}]}}]}, model
        return {"candidates": [{"content": {"parts": [{"functionCall": {"name": "list_files", "args": {}}}]}}]}, model

    H._call_with_recovery = mock_recovery
    H._usage_cost = lambda model, j: 0.0
    G.ledger = lambda *a, **k: None

    with tempfile.TemporaryDirectory(dir=str(Path.home())) as d:
        ans, total, steps = H.agent_turn("dummy-model", "system", [], "test task", d)
        check("forced final report on step cap", ans == "FINAL REPORT" and steps == H.MAX_STEPS)
finally:
    H._call_with_recovery = old_recovery
    H._usage_cost = old_cost
    G.ledger = old_ledger

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
