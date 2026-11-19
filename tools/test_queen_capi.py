"""Offline tests for the Python CAPI client; no Queen server or API keys are needed."""
import base64
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
from queen_capi import QueenAPIError, QueenCAPI, attachment


class CapiClientTests(unittest.TestCase):
    def test_attachment_encodes_bytes_and_mime(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "take.m4a"
            path.write_bytes(b"audio bytes")
            item = attachment(path)
        self.assertEqual(item["mime"], "audio/m4a")
        self.assertEqual(base64.b64decode(item["b64"]), b"audio bytes")

    def test_attachment_rejects_files_over_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "large.bin"
            with path.open("wb") as file:
                file.truncate(20 * 1024 * 1024 + 1)
            with self.assertRaisesRegex(QueenAPIError, "20 MB"):
                attachment(path)

    def test_send_includes_files_and_router_choice(self):
        client = QueenCAPI(token_file=Path("/nonexistent/queen-token"))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "lyrics.txt"
            path.write_text("line one", encoding="utf-8")
            with patch.object(client, "_request", return_value={"ok": True}) as request:
                result = client.send("chat-id", "Read the lyrics", [path], router=True)
        self.assertTrue(result["ok"])
        payload = request.call_args.args[2]
        self.assertEqual(payload["id"], "chat-id")
        self.assertTrue(payload["router"])
        self.assertEqual(base64.b64decode(payload["files"][0]["b64"]), b"line one")

    def test_empty_prompt_is_rejected_before_request(self):
        client = QueenCAPI()
        with patch.object(client, "_request") as request:
            with self.assertRaisesRegex(QueenAPIError, "empty"):
                client.send("chat-id", "  ")
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
