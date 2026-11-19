"""Offline tests for CAPI media forwarding, routing validation, and honest Google credit metadata."""
import base64
import os
import sys
import threading
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capi_model_router as Router
import capi_chat as C
import gcloud_chat as G
import gemini_hands as H
import queen_python_skills as PythonSkills
from queen_python_skills import ableton as Ableton
import pair_chat
from flask import Flask
from unittest.mock import patch


ok = True


def check(name, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + name)
    ok = ok and bool(cond)


def encoded(data):
    return base64.b64encode(data).decode("ascii")


prepared, error = G.prepare_files([
    {"name": "voice.m4a", "mime": "audio/m4a", "b64": encoded(b"audio")},
    {"name": "clip.mov", "mime": "video/quicktime", "b64": encoded(b"video")},
])
check("audio and video prepared for Gemini", not error and [f["kind"] for f in prepared] == ["audio", "video"])
check("audio and video MIME capabilities match Google Cloud's documented lists",
      G.AUDIO_MIME == {
          "audio/flac", "audio/m4a", "audio/mp3", "audio/mpeg", "audio/mp4", "audio/mpga",
          "audio/ogg", "audio/pcm", "audio/wav", "audio/webm", "audio/x-aac",
      } and G.VIDEO_MIME == {
          "video/3gpp", "video/mp4", "video/mpeg", "video/mpegs", "video/mpg", "video/quicktime",
          "video/webm", "video/wmv", "video/x-flv",
      })
parts = G._gemini_parts("Describe these recordings.", prepared)
check("Gemini inline media parts", parts[0]["inline_data"]["mime_type"] == "audio/m4a"
      and parts[1]["inline_data"]["mime_type"] == "video/quicktime")
_, error = G.prepare_files([{"name": "unsupported.aiff", "mime": "audio/aiff", "b64": encoded(b"audio")}])
check("undocumented audio MIME rejected", "unsupported file type" in error)
_, error = G.prepare_files([{"name": "unsupported.avi", "mime": "video/x-msvideo", "b64": encoded(b"video")}])
check("undocumented video MIME rejected", "unsupported file type" in error)
_, error = G.prepare_files([{"name": "archive.bin", "mime": "application/octet-stream", "b64": encoded(b"\x00\x01\x02")}])
check("unsupported binary rejected explicitly", "unsupported file type" in error)
_, error = G.prepare_files([{"name": "archive.zip", "mime": "application/zip", "b64": encoded(b"plain-looking")}])
check("unknown application MIME rejected", "unsupported file type" in error)
_, error = G.prepare_files([{"name": "bad.txt", "mime": "text/plain", "b64": "not-base64!"}])
check("invalid attachment encoding rejected", "could not be read" in error)
check("credit is explicitly not live", G.credit_info()["is_estimate"] and not G.credit_info()["live_balance_supported"])
with tempfile.TemporaryDirectory(dir=str(Path.home())) as folder:
    valid_folder, folder_error = C._validate_cwd(folder)
    check("home child accepted as workspace", valid_folder == os.path.realpath(folder) and not folder_error)
check("home root rejected as workspace", bool(C._validate_cwd(str(Path.home()))[1]))
check("outside-home workspace rejected", bool(C._validate_cwd("/tmp")[1]))

catalog = [("cheap", "1", 0.1, 0.4), ("capable", "2", 0.3, 2.5)]
check("router accepts catalog model with reason", Router.parse_choice('{"model":"cheap","reason":"Simple request."}', catalog)
      == ("cheap", "Simple request."))
try:
    Router.parse_choice('{"model":"outside","reason":"Not allowed."}', catalog)
    valid_rejection = False
except ValueError:
    valid_rejection = True
check("router rejects model outside catalog", valid_rejection)
try:
    Router.parse_choice('{"model":"cheap","reason":""}', catalog)
    missing_reason_rejection = False
except ValueError:
    missing_reason_rejection = True
check("router requires a reason", missing_reason_rejection)
try:
    Router.parse_choice('["cheap"]', catalog)
    invalid_choice_rejection = False
except ValueError:
    invalid_choice_rejection = True
check("router rejects non-object choice", invalid_choice_rejection)
local_help = PythonSkills.dispatch("  LIST   SKILLS ")
check("known local skill matches without a model", local_help is not None and local_help.skill_id == "list-skills")
current_folder = PythonSkills.dispatch("what folder is open", {"cwd": "/tmp/project"})
check("local folder skill uses chat context",
      current_folder is not None and current_folder.answer.endswith("/tmp/project"))
check("unknown local skill falls through to CAPI", PythonSkills.dispatch("summarize an attached recording") is None)
with patch.object(Ableton, "execute_text", return_value="Mock Ableton state"):
    ableton_skill = PythonSkills.dispatch("ABLETON: status")
check("Ableton command dispatches to the provider-independent Python skill",
      ableton_skill is not None and ableton_skill.skill_id == "ableton-control"
      and ableton_skill.answer == "Mock Ableton state")
judge_prompt = Router._judge_prompt("Summarize this.", catalog, [
    {"name": "voice.wav", "mime": "audio/wav", "b64": "secret-payload"},
])
check("router receives attachment metadata but not file data",
      "voice.wav (audio/wav)" in judge_prompt and "secret-payload" not in judge_prompt)
with patch.object(pair_chat, "slave_catalog", return_value=catalog), \
     patch.object(H, "text_turn", return_value=('{"model":"capable","reason":"The task needs the larger context."}', 0.0001)):
    routed = Router.choose("gcloud", "Implement a multi-file change.")
check("router uses the cheapest judge and returns its route", routed["judge_model"] == "cheap"
      and routed["model"] == "capable" and routed["router_cost_usd"] == 0.0001)

flask_app = Flask(__name__)
C.register(flask_app)
client = flask_app.test_client()
capabilities = client.get("/api/capi/capabilities").get_json()
check("capabilities endpoint advertises the same Gemini MIME lists",
      capabilities["attachments"]["audio_mime_types"] == sorted(G.AUDIO_MIME)
      and capabilities["attachments"]["video_mime_types"] == sorted(G.VIDEO_MIME))
check("router setting rejects non-boolean", client.post("/api/capi/settings", json={"router_on": "yes"}).status_code == 400)
check("new chat rejects outside-home folder", client.post("/api/capi/new", json={"cwd": "/tmp"}).status_code == 400)
check("settings rejects home folder", client.post("/api/capi/settings", json={"cwd": str(Path.home())}).status_code == 400)


class FakeConv:
    def __init__(self):
        self.room = {"id": "router-test", "total": 0.0, "router_on": True, "messages": []}
        self.lock = threading.RLock()
        self.busy = False
        self.error = ""

    def save(self):
        pass

    def running(self):
        return False

    def send(self, text, files=None):
        self.room["messages"].append({"role": "marko", "text": text})
        return True

    def state(self):
        return {"running": False, "busy": False, "error": ""}


class FakeLocalConv(FakeConv):
    def complete_local_skill(self, text, result):
        self.local_skill = (text, result.skill_id, result.answer)


fake_conv = FakeConv()
routed_choice = {"provider": "gcloud", "model": "capable", "reason": "Needs stronger reasoning.",
                 "judge_model": "cheap", "router_cost_usd": 0.000123, "catalog": ["cheap", "capable"]}
with patch.object(C, "_conv", return_value=fake_conv), patch.object(C, "get_provider", return_value="gcloud"), \
     patch.object(pair_chat, "status", return_value={"active": False}), \
     patch.object(Router, "choose", return_value=routed_choice) as choose:
    route_response = client.post("/api/capi/send", json={
        "id": "router-test", "text": "Inspect this recording.",
        "files": [{"name": "voice.wav", "mime": "audio/wav", "b64": "encoded"}],
    }).get_json()
check("send routes with attachment metadata and includes judge cost",
      route_response["route"]["model"] == "capable"
      and fake_conv.room["total"] == 0.000123
      and choose.call_args.args[2][0]["name"] == "voice.wav")

local_conv = FakeLocalConv()
with patch.object(C, "_conv", return_value=local_conv), \
     patch.object(Router, "choose", side_effect=AssertionError("local skills must not call the model router")):
    local_response = client.post("/api/capi/send", json={
        "id": "local-skill-test", "text": "list skills", "router": True,
    }).get_json()
check("known skill bypasses the model router", local_response["ok"]
      and local_response["local_skill"] == "list-skills"
      and local_conv.local_skill[1] == "list-skills")

with patch.object(Ableton, "execute_text", return_value="Ableton status confirmed"), \
     patch.object(C, "_conv", return_value=local_conv), \
     patch.object(Router, "choose", side_effect=AssertionError("Ableton skills must not call the model router")):
    ableton_response = client.post("/api/capi/send", json={
        "id": "local-skill-test", "text": "ABLETON: status", "router": True,
    }).get_json()
check("Ableton actions bypass every selected model and the model router",
      ableton_response["ok"] and ableton_response["local_skill"] == "ableton-control"
      and local_conv.local_skill[2] == "Ableton status confirmed")

old_call = H._call_with_recovery
old_cost = H._usage_cost
old_ledger = G.ledger
captured = []
try:
    def fake_call(model, body, notice_cb=None):
        captured.append(body)
        return {"candidates": [{"content": {"parts": [{"text": "done"}]}}]}, model

    H._call_with_recovery = fake_call
    H._usage_cost = lambda model, response: 0.0
    G.ledger = lambda *args, **kwargs: None
    with tempfile.TemporaryDirectory(dir=str(Path.home())) as folder:
        answer, _, _ = H.agent_turn(
            "fake-model",
            "system",
            [],
            "Summarize this audio.",
            folder,
            files=[{"kind": "audio", "name": "voice.wav", "mime": "audio/wav", "b64": encoded(b"audio")}],
        )
    check("Gemini tool loop receives initial attachments", answer == "done"
          and captured[0]["contents"][0]["parts"][0]["inline_data"]["mime_type"] == "audio/wav")
finally:
    H._call_with_recovery = old_call
    H._usage_cost = old_cost
    G.ledger = old_ledger

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
