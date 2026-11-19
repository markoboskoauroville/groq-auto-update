"""Queen's private state directory and one-time migration from the retired engine directory."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any


QUEEN_HOME = Path.home() / ".queen"
LEGACY_HOME = Path.home() / ".groq"


def migrate_legacy_state(
    legacy_home: Path = LEGACY_HOME,
    queen_home: Path = QUEEN_HOME,
) -> list[str]:
    """Copy only CAPI and updater state; never carry legacy model keys into Queen's runtime."""
    migrated: list[str] = []
    queen_home.mkdir(parents=True, exist_ok=True)

    for name in (
        "capi_key",
        "capi_key_oxyy",
        "capi_provider.json",
        "capi_oxyy_balance.json",
        "auto_update_ledger.json",
    ):
        source = legacy_home / name
        destination = queen_home / name
        if source.is_file() and not destination.exists():
            shutil.copy2(source, destination)
            os.chmod(destination, 0o600)
            migrated.append(name)

    source_rooms = legacy_home / "capi"
    destination_rooms = queen_home / "capi"
    if source_rooms.is_dir():
        destination_rooms.mkdir(parents=True, exist_ok=True)
        for source in source_rooms.glob("*.json"):
            destination = destination_rooms / source.name
            if source.is_file() and not destination.exists():
                shutil.copy2(source, destination)
                os.chmod(destination, 0o600)
                migrated.append(f"capi/{source.name}")

    source_store = legacy_home / "auto_update_keys.json"
    destination_store = queen_home / "auto_update_keys.json"
    if source_store.is_file() and not destination_store.exists():
        raw: Any = json.loads(source_store.read_text(encoding="utf-8"))
        active_provider = raw.get("active_provider", "google") if isinstance(raw, dict) else "google"
        active_models = raw.get("active_models", {}) if isinstance(raw, dict) else {}
        keys = raw.get("keys", {}) if isinstance(raw, dict) else {}
        migrated_store = {
            "active_provider": active_provider if active_provider in ("google", "anthropic") else "google",
            "active_models": {
                provider: str(active_models.get(provider, ""))
                for provider in ("google", "anthropic")
                if isinstance(active_models, dict) and active_models.get(provider)
            },
            "keys": {
                provider: [str(key).strip() for key in keys.get(provider, []) if str(key).strip()]
                for provider in ("google", "anthropic")
                if isinstance(keys, dict) and isinstance(keys.get(provider, []), list)
            },
        }
        tmp = destination_store.with_name(
            f"{destination_store.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp"
        )
        tmp.write_text(json.dumps(migrated_store, indent=2), encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(destination_store)
        migrated.append("auto_update_keys.json")

    return migrated
