from __future__ import annotations

import atexit
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import queen_backend
import capi_chat
import auto_updater
from queen_python_skills import ableton as Ableton
from state_paths import migrate_legacy_state


def check(name: str, ok: bool) -> None:
    if not ok:
        raise AssertionError(name)
    print(f"PASS {name}")


client = queen_backend.app.test_client()
test_home = Path(tempfile.mkdtemp(prefix="queen-backend-isolated-"))
atexit.register(shutil.rmtree, test_home, ignore_errors=True)
auto_updater.AUTO_UPDATE_KEYS_FILE = test_home / "auto_update_keys.json"
auto_updater.AUTO_UPDATE_LEDGER_FILE = test_home / "auto_update_ledger.json"
auto_updater.AUTO_UPDATE_KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
capi_chat.ROOT = test_home / "capi"
capi_chat.PROVIDER_FILE = test_home / "capi_provider.json"
check(
    "health identifies the Python runtime",
    client.get("/health").get_json()["app"] == "Queen Python skills",
)
check(
    "legacy Groq chat API is absent",
    client.post("/api/chat", json={"messages": []}).status_code == 404,
)
check(
    "legacy remote-send API is absent",
    client.post("/api/remote/send", json={"prompt": "test"}).status_code == 404,
)
check(
    "legacy key manager API is absent",
    client.get("/api/keys").status_code == 404,
)
check(
    "local API guard rejects deceptive loopback prefixes",
    client.get("/api/version", headers={"Origin": "http://127.0.0.1.attacker.example"}).status_code == 403,
)
skill_list = client.get("/api/skills/list").get_json()["skills"]
check("Python skill catalog includes the provider-independent Ableton skill",
      {item["id"] for item in skill_list} == {"list-skills", "current-folder", "ableton-control"})
ableton_capabilities = client.get("/api/ableton/capabilities").get_json()
check("Ableton capabilities expose actions for any model provider",
      ableton_capabilities["ok"] and ableton_capabilities["provider_independent"]
      and any(item["name"] == "load_audio_to_arrangement"
              for item in ableton_capabilities["actions"]))
bad_ableton_action = client.post("/api/ableton/action", json={"action": "raw_osc", "arguments": {}})
check("Ableton action endpoint rejects unallowlisted actions", bad_ableton_action.status_code == 400)
with patch.object(Ableton, "execute_action", return_value={
    "action": "status", "takeover_notice": True, "confirmed": True, "tempo": 120,
}):
    ableton_action = client.post("/api/ableton/action", json={"action": "status"}).get_json()
check("Ableton action endpoint calls the shared Python action engine",
      ableton_action["ok"] and ableton_action["takeover_notice"] and ableton_action["tempo"] == 120)
auto_update = client.get("/api/auto_update/config").get_json()
check("Auto Update exposes only external providers", set(auto_update["providers"]) == {"google", "anthropic"})

original_root = capi_chat.ROOT
with tempfile.TemporaryDirectory(dir=test_home) as temp_dir:
    capi_chat.ROOT = Path(temp_dir)
    folder = Path.home() / "Developer" / "claude-code"
    if not folder.is_dir():
        folder = Path.home() / "Developer" / "groq_ai_studio"
    created = client.post("/api/capi/new", json={"cwd": str(folder)}).get_json()
    conversation_id = created["room"]["id"]
    sent = client.post("/api/capi/send", json={
        "id": conversation_id,
        "text": "list skills",
        "router": True,
    }).get_json()
    conversation = client.get(f"/api/capi/get?id={conversation_id}").get_json()["room"]
    check("known command is handled by Python in the runtime", sent["local_skill"] == "list-skills")
    check(
        "local result is visible and costs nothing",
        conversation["messages"][-1]["label"] == "PYTHON · list-skills"
        and conversation["messages"][-1]["cost"] == 0.0,
    )
    client.post("/api/capi/close", json={"id": conversation_id})
capi_chat.ROOT = original_root

with tempfile.TemporaryDirectory() as temp_dir:
    old = Path(temp_dir) / "old"
    new = Path(temp_dir) / "new"
    old.mkdir()
    (old / "keys.txt").write_text("legacy model key", encoding="utf-8")
    (old / "capi_key").write_text("external CAPI key", encoding="utf-8")
    (old / "auto_update_keys.json").write_text(
        '{"active_provider":"groq","keys":{"google":["google-key"],"anthropic":["anthropic-key"],"groq":["legacy-key"]}}',
        encoding="utf-8",
    )
    migrated = migrate_legacy_state(old, new)
    config = __import__("json").loads((new / "auto_update_keys.json").read_text(encoding="utf-8"))
    check("state migration preserves CAPI state but filters retired model keys",
          "capi_key" in migrated and not (new / "keys.txt").exists()
          and config["active_provider"] == "google"
          and set(config["keys"]) == {"google", "anthropic"})

shutil.rmtree(test_home)
