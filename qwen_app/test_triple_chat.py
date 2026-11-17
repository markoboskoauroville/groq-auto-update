"""Offline test of the Triple Chat logic (no model calls): addressing, think filter, ASK CLAUDE cap, consent/resume,
ASK QUEEN button, persistence. Run: python3 qwen_app/test_triple_chat.py"""
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import triple_chat as tc
import claude_link
from flask import Flask

tc.ROOT = Path(tempfile.mkdtemp(prefix="triple_test_"))
tc.groq = None


class Pool:
    def candidates(self, m): return ["k"]
    def good(self, *a): pass
    def cool(self, *a): pass


# addressing
P = tc.parse_addressing
assert P("Queen, please ask Claude how", "claude") == "queen"
assert P("Claude, tell Queen", "queen") == "claude"
assert P("Queen and Claude, hi") == "both" and P("Queen, Claude: hi") == "both" and P("both of you") == "both"
assert P("Qwen hi") == "queen" and P("Quinn hi") == "queen" and P("Cloud hi") == "claude"
assert P("no name", "claude") == "claude" and P("no name", "zzz") == "queen"
# think filter
f = tc._ThinkFilter(); o = ""
for t in ["<th", "ink>x</thi", "nk>ok <b", ">"]: o += f.feed(t)
assert o + f.feed("", True) == "ok <b>", o

app = Flask(__name__)
calls = {"queen": 0, "claude": 0}
state = {"reachable": True}
claude_link.status = lambda force=False: {"reachable": state["reachable"]}
claude_link.ask = lambda prompt, model=None: (calls.__setitem__("claude", calls["claude"] + 1) or
                                              {"answer": "Claude says X.\nASK QUEEN: list files"})
tc.register(app, Pool(), lambda s: "SYS", lambda *a: None, lambda t: None, lambda *a: iter(()), "m", 100)

# register() built queen_speak inside; patch the groq call by replacing the Groq class
import types
class FakeGroq:
    def __init__(self, **k): pass
    class chat:
        class completions:
            @staticmethod
            def create(**k):
                calls["queen"] += 1
                d = types.SimpleNamespace(content="asking\nASK CLAUDE: q%d" % calls["queen"])
                yield types.SimpleNamespace(choices=[types.SimpleNamespace(delta=d)], usage=None)
sys.modules["groq"] = types.SimpleNamespace(Groq=type("G", (), {"__init__": lambda s, **k: None,
    "chat": types.SimpleNamespace(completions=types.SimpleNamespace(create=FakeGroq.chat.completions.create))}))

c = app.test_client()
def turn(**d):
    r = c.post("/api/triple/turn", json=d)
    return [json.loads(l) for l in r.get_data(as_text=True).splitlines()]

rid = c.post("/api/triple/new", json={"title": "t"}).get_json()["room"]["id"]
ev = turn(id=rid, text="Queen, please ask Claude something", to="auto")
room = c.get("/api/triple/get?id=" + rid).get_json()["room"]
who = [m["speaker"] for m in room["messages"]]
assert who == ["marko", "queen", "claude", "queen", "claude", "queen", "claude", "queen"], who  # cap: 3 Claude answers
assert calls["claude"] == 3 and ev[-1] == {"done": 1}, (calls, ev[-1])
assert "<think>" not in json.dumps(room)
# persistence: a second client reads the same room from disk
assert len(tc._load(rid)["messages"]) == 8
# consent flow
state["reachable"] = False
ev = turn(id=rid, text="Claude, hello", to="auto")
assert any("need_consent" in e for e in ev), ev
n = len(tc._load(rid)["messages"])
ev = turn(id=rid, text="", to="claude", allow_api=False, resume=True)
assert any("need_consent" in e for e in ev)
assert tc._load(rid)["messages"][-1]["speaker"] == "marko" and len(tc._load(rid)["messages"]) == n
# ASK QUEEN button needs a Claude line with ASK QUEEN
state["reachable"] = True
calls["claude"] = 0
turn(id=rid, text="Claude, hello again", to="auto")
assert calls["claude"] == 1
ev = turn(id=rid, text="", to="queen")
assert tc._load(rid)["messages"][-1]["speaker"] in ("queen", "claude"), ev
print("triple chat offline tests OK")
