#!/usr/bin/env python3
"""Small Python client for Queen's local CAPI HTTP API."""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

MAX_FILE_BYTES = 20 * 1024 * 1024
MIME_OVERRIDES = {
    ".3gp": "video/3gpp",
    ".aac": "audio/x-aac",
    ".flac": "audio/flac",
    ".flv": "video/x-flv",
    ".m4a": "audio/m4a",
    ".mp3": "audio/mp3",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".mp4": "video/mp4",
    ".mpga": "audio/mpga",
    ".mpg": "video/mpg",
    ".mpeg": "video/mpeg",
    ".ogg": "audio/ogg",
    ".pcm": "audio/pcm",
    ".wav": "audio/wav",
    ".webm": "video/webm",
    ".wmv": "video/wmv",
}


class QueenAPIError(RuntimeError):
    """A local Queen API request failed."""


def attachment(path: str | os.PathLike[str]) -> dict[str, str]:
    file_path = Path(path).expanduser()
    if not file_path.is_file():
        raise QueenAPIError(f"Attachment is not a file: {file_path}")
    size = file_path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise QueenAPIError(f"{file_path.name} is {size / 1048576:.1f} MB; the per-file limit is 20 MB.")
    suffix = file_path.suffix.lower()
    mime = MIME_OVERRIDES.get(suffix) or mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    return {
        "name": file_path.name,
        "mime": mime,
        "b64": base64.b64encode(file_path.read_bytes()).decode("ascii"),
    }


class QueenCAPI:
    def __init__(self, base_url: str = "http://127.0.0.1:8765", token_file: str | os.PathLike[str] | None = None):
        self.base_url = base_url.rstrip("/")
        self.token_file = Path(token_file or Path.home() / ".groq" / "api_token").expanduser()

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        timeout: float = 30,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        try:
            token = self.token_file.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            token = ""
        if token:
            headers["X-Queen-Token"] = token
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            try:
                message = json.loads(detail).get("error") or detail
            except (json.JSONDecodeError, AttributeError):
                message = detail
            raise QueenAPIError(f"Queen API returned HTTP {exc.code}: {message}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise QueenAPIError(f"Could not reach Queen at {self.base_url}: {exc}") from exc
        try:
            result = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise QueenAPIError("Queen returned an invalid JSON response.") from exc
        if not isinstance(result, dict):
            raise QueenAPIError("Queen returned a JSON response with an unexpected shape.")
        return result

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def capabilities(self) -> dict[str, Any]:
        return self._request("GET", "/api/capi/capabilities")

    def list_chats(self) -> dict[str, Any]:
        return self._request("GET", "/api/capi/list")

    def get_chat(self, chat_id: str) -> dict[str, Any]:
        query = urllib.parse.urlencode({"id": chat_id})
        return self._request("GET", f"/api/capi/get?{query}")

    def create_chat(
        self,
        folder: str | os.PathLike[str] | None = None,
        model: str | None = None,
        provider: str | None = None,
        gmodel: str | None = None,
        router_on: bool | None = None,
    ) -> dict[str, Any]:
        if provider:
            self._request("POST", "/api/capi/provider", {"provider": provider})
        payload: dict[str, Any] = {}
        if folder is not None:
            payload["cwd"] = str(Path(folder).expanduser())
        if model:
            payload["model"] = model
        result = self._request("POST", "/api/capi/new", payload)
        chat = result.get("room")
        if not isinstance(chat, dict) or not chat.get("id"):
            raise QueenAPIError("Queen did not return the new chat.")
        settings: dict[str, Any] = {"id": chat["id"]}
        if gmodel:
            settings["gmodel"] = gmodel
        if router_on is not None:
            settings["router_on"] = router_on
        if len(settings) > 1:
            result.update(self._request("POST", "/api/capi/settings", settings))
        return result

    def set_provider(self, provider: str) -> dict[str, Any]:
        return self._request("POST", "/api/capi/provider", {"provider": provider})

    def set_settings(self, chat_id: str, **settings: Any) -> dict[str, Any]:
        return self._request("POST", "/api/capi/settings", {"id": chat_id, **settings})

    def send(
        self,
        chat_id: str,
        text: str,
        files: list[str | os.PathLike[str] | dict[str, str]] | None = None,
        router: bool | None = None,
        timeout: float = 60,
    ) -> dict[str, Any]:
        prompt = text.strip()
        if not prompt:
            raise QueenAPIError("Prompt must not be empty.")
        payload: dict[str, Any] = {"id": chat_id, "text": prompt}
        if files:
            payload["files"] = [f if isinstance(f, dict) else attachment(f) for f in files]
        if router is not None:
            payload["router"] = router
        return self._request("POST", "/api/capi/send", payload, timeout=timeout)

    def wait(self, chat_id: str, poll_interval: float = 1.0, timeout: float = 1200) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self.get_chat(chat_id)
            if not result.get("busy"):
                return result
            time.sleep(poll_interval)
        raise QueenAPIError(f"Timed out waiting for chat {chat_id}.")

    def send_and_wait(
        self,
        chat_id: str,
        text: str,
        files: list[str | os.PathLike[str] | dict[str, str]] | None = None,
        router: bool | None = None,
        timeout: float = 1200,
    ) -> dict[str, Any]:
        sent = self.send(chat_id, text, files=files, router=router, timeout=min(timeout, 60))
        if sent.get("ok") is False:
            raise QueenAPIError(str(sent.get("error") or "Queen did not accept the prompt."))
        return self.wait(chat_id, timeout=timeout)

    def stop(self, chat_id: str) -> dict[str, Any]:
        return self._request("POST", "/api/capi/stop", {"id": chat_id})

    def close(self, chat_id: str) -> dict[str, Any]:
        return self._request("POST", "/api/capi/close", {"id": chat_id})


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("health", "capabilities", "list"):
        sub.add_parser(name)
    get_parser = sub.add_parser("get")
    get_parser.add_argument("chat_id")
    new_parser = sub.add_parser("new")
    new_parser.add_argument("--folder")
    new_parser.add_argument("--provider", choices=("anthropic", "oxyy", "gcloud"))
    new_parser.add_argument("--model")
    new_parser.add_argument("--gmodel")
    new_parser.add_argument("--router", action=argparse.BooleanOptionalAction, default=None)
    send_parser = sub.add_parser("send")
    send_parser.add_argument("chat_id")
    send_parser.add_argument("text")
    send_parser.add_argument("--file", action="append", default=[])
    send_parser.add_argument("--router", action=argparse.BooleanOptionalAction, default=None)
    send_parser.add_argument("--wait", action="store_true")
    send_parser.add_argument("--timeout", type=float, default=1200)
    for name in ("stop", "close"):
        item = sub.add_parser(name)
        item.add_argument("chat_id")
    args = parser.parse_args()
    client = QueenCAPI(args.base_url)
    try:
        if args.command == "health":
            result = client.health()
        elif args.command == "capabilities":
            result = client.capabilities()
        elif args.command == "list":
            result = client.list_chats()
        elif args.command == "get":
            result = client.get_chat(args.chat_id)
        elif args.command == "new":
            result = client.create_chat(args.folder, args.model, args.provider, args.gmodel, args.router)
        elif args.command == "send":
            result = client.send(args.chat_id, args.text, args.file, args.router)
            if args.wait and result.get("ok") is not False:
                result = client.wait(args.chat_id, timeout=args.timeout)
        elif args.command == "stop":
            result = client.stop(args.chat_id)
        else:
            result = client.close(args.chat_id)
        _print(result)
        return 0
    except QueenAPIError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
