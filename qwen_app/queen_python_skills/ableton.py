"""Provider-independent Ableton Live control through the installed AbletonOSC surface."""
from __future__ import annotations

import importlib.util
import math
import os
import shlex
import sys
import threading
import time
from pathlib import Path
from types import ModuleType
from typing import Any


class AbletonControlError(RuntimeError):
    """A requested Ableton action could not be completed safely."""


class AbletonUnavailable(AbletonControlError):
    """AbletonOSC or the required takeover guard is unavailable."""


class TakeoverCancelled(AbletonControlError):
    """Marko took control before the requested action finished."""


_ACTION_SPECS: dict[str, dict[str, Any]] = {
    "status": {"description": "Read Live transport, tempo, tracks, and scenes.", "arguments": {}},
    "play": {"description": "Start Live playback.", "arguments": {}},
    "stop": {"description": "Stop Live playback.", "arguments": {}},
    "continue": {"description": "Continue Live playback.", "arguments": {}},
    "set_tempo": {"description": "Set tempo in beats per minute.", "arguments": {"bpm": "number"}},
    "set_metronome": {"description": "Enable or disable the metronome.", "arguments": {"enabled": "boolean"}},
    "create_audio_track": {"description": "Create an audio track at the end of the set.", "arguments": {}},
    "create_midi_track": {"description": "Create a MIDI track at the end of the set.", "arguments": {}},
    "set_track_name": {"description": "Rename a track by its one-based number or exact name.",
                       "arguments": {"track": "one-based integer or exact track name", "name": "string"}},
    "set_track_mute": {"description": "Set a track's mute state.",
                       "arguments": {"track": "one-based integer or exact track name", "enabled": "boolean"}},
    "set_track_solo": {"description": "Set a track's solo state.",
                       "arguments": {"track": "one-based integer or exact track name", "enabled": "boolean"}},
    "set_track_arm": {"description": "Set a track's record-arm state.",
                      "arguments": {"track": "one-based integer or exact track name", "enabled": "boolean"}},
    "set_track_volume": {"description": "Set track mixer volume, normalized 0..1 (0.85 is about 0 dB).",
                         "arguments": {"track": "one-based integer or exact track name", "value": "number 0..1"}},
    "set_track_pan": {"description": "Set track panning, -1 left through 1 right.",
                      "arguments": {"track": "one-based integer or exact track name", "value": "number -1..1"}},
    "fire_scene": {"description": "Fire a scene by its one-based number.",
                   "arguments": {"scene": "one-based integer"}},
    "fire_clip": {"description": "Fire an existing session clip.",
                  "arguments": {"track": "one-based integer or exact track name", "scene": "one-based integer"}},
    "stop_clip": {"description": "Stop a clip slot.",
                  "arguments": {"track": "one-based integer or exact track name", "scene": "one-based integer"}},
    "load_audio_clip": {"description": "Load an existing audio file into an empty session clip slot.",
                        "arguments": {"track": "one-based integer or exact track name",
                                      "scene": "one-based integer", "path": "existing audio file path"}},
    "load_audio_to_arrangement": {
        "description": "Create a new arrangement track and load an audio file at a beat position.",
        "arguments": {"path": "existing audio file path", "track_name": "optional string",
                      "position_beats": "optional non-negative number"},
    },
    "list_devices": {"description": "List devices already loaded on a track.",
                     "arguments": {"track": "one-based integer or exact track name"}},
    "device_parameters": {"description": "Read parameter names, current values, and ranges for a loaded device.",
                          "arguments": {"track": "one-based integer or exact track name",
                                        "device": "one-based integer or exact device name"}},
    "set_device_parameter": {"description": "Set a loaded device/plugin parameter in its native value range.",
                             "arguments": {"track": "one-based integer or exact track name",
                                           "device": "one-based integer or exact device name",
                                           "parameter": "one-based integer or exact parameter name",
                                           "value": "number within the parameter's reported min/max"}},
    "stop_all_clips": {"description": "Stop all session clips.", "arguments": {}},
}

_AUDIO_EXTENSIONS = {".aif", ".aiff", ".flac", ".m4a", ".mp3", ".ogg", ".wav"}
_MODULES: dict[str, ModuleType] = {}


def capabilities() -> dict[str, Any]:
    """Return the common, model-agnostic action contract."""
    return {
        "provider_independent": True,
        "transport": "AbletonOSC on 127.0.0.1:11000; replies use the shared liveosc turn on UDP 11001.",
        "takeover": "Every action uses Macro Recorder's input guard and shows 'Queen is taking over Ableton Live'. "
                    "TAKE OVER aborts further OSC messages.",
        "indexing": "Track, scene, device, and parameter numbers are one-based in this API; names must match exactly.",
        "actions": [
            {"name": name, **spec}
            for name, spec in _ACTION_SPECS.items()
        ],
        "limitations": [
            "The skill only sends allowlisted, typed AbletonOSC actions; it does not accept arbitrary OSC addresses.",
            "Loading audio and controlling already-loaded devices/plugins are supported. Loading third-party plugins, "
            "saving/exporting, and Live's Separate Stems menu command are not OSC actions and are not automated here.",
        ],
        "text_commands": [
            "ABLETON: status",
            "ABLETON: play | stop | continue",
            "ABLETON: set tempo 120",
            "ABLETON: metronome on",
            "ABLETON: create audio track",
            "ABLETON: mute track 1",
            "ABLETON: volume track 1 0.85",
            "ABLETON: fire scene 2",
            "ABLETON: load audio \"/path/to/song.wav\" on track 1 scene 1",
        ],
    }


def _load_module(name: str, path: Path) -> ModuleType:
    if name in _MODULES:
        return _MODULES[name]
    if not path.is_file():
        raise AbletonUnavailable(f"Required local integration is missing: {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AbletonUnavailable(f"Cannot load required local integration: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except (ImportError, OSError) as exc:
        raise AbletonUnavailable(f"Cannot load required local integration {path}: {exc}") from exc
    _MODULES[name] = module
    return module


def _load_guard() -> ModuleType:
    return _load_module(
        "queen_ableton_macro_guard",
        Path.home() / "Developer" / "MANTRA_MACRO" / "tools" / "guard.py",
    )


def _load_liveosc() -> ModuleType:
    return _load_module(
        "queen_ableton_liveosc",
        Path.home() / "Developer" / "ABLETON_LIVE_ACTIONS" / "helpers" / "liveosc.py",
    )


def _require_args(
    action: str,
    args: Any,
    required: set[str],
    optional: set[str] | frozenset[str] = frozenset(),
) -> dict[str, Any]:
    if not isinstance(args, dict):
        raise ValueError("arguments must be a JSON object")
    missing = required - args.keys()
    extra = args.keys() - required - optional
    if missing:
        raise ValueError(f"{action} is missing argument(s): {', '.join(sorted(missing))}")
    if extra:
        raise ValueError(f"{action} does not accept argument(s): {', '.join(sorted(extra))}")
    return args


def _number(value: Any, label: str, low: float | None = None, high: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{label} must be a finite number")
    value = float(value)
    if low is not None and value < low or high is not None and value > high:
        span = f"{low:g}..{high:g}" if low is not None and high is not None else (
            f"at least {low:g}" if low is not None else f"at most {high:g}"
        )
        raise ValueError(f"{label} must be {span}")
    return value


def _selector(value: Any, label: str) -> int | str:
    if type(value) is int and value > 0:
        return value
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ValueError(f"{label} must be a positive one-based number or a non-empty exact name")


def _audio_path(value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("path must be a non-empty audio file path")
    try:
        path = Path(value).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"audio file does not exist or cannot be read: {exc}") from exc
    if not path.is_file():
        raise ValueError("path must point to a file")
    if path.suffix.casefold() not in _AUDIO_EXTENSIONS:
        raise ValueError(f"unsupported audio extension: {path.suffix or '(none)'}")
    return path


def _normalize(action: Any, arguments: Any) -> tuple[str, dict[str, Any]]:
    if not isinstance(action, str) or not action.strip():
        raise ValueError("action must be a non-empty string")
    action = action.strip().casefold().replace("-", "_")
    if action not in _ACTION_SPECS:
        raise ValueError(f"unknown Ableton action {action!r}; query /api/ableton/capabilities")
    args = dict(arguments) if isinstance(arguments, dict) else arguments

    no_args = {"status", "play", "stop", "continue", "create_audio_track", "create_midi_track", "stop_all_clips"}
    if action in no_args:
        return action, _require_args(action, args, set())
    if action == "set_tempo":
        args = _require_args(action, args, {"bpm"})
        return action, {"bpm": _number(args["bpm"], "bpm", 20, 999)}
    if action == "set_metronome":
        args = _require_args(action, args, {"enabled"})
        if type(args["enabled"]) is not bool:
            raise ValueError("enabled must be a boolean")
        return action, args
    if action == "set_track_name":
        args = _require_args(action, args, {"track", "name"})
        if not isinstance(args["name"], str) or not args["name"].strip() or len(args["name"]) > 120:
            raise ValueError("name must be a non-empty string of at most 120 characters")
        return action, {"track": _selector(args["track"], "track"), "name": args["name"].strip()}
    if action in {"set_track_mute", "set_track_solo", "set_track_arm"}:
        args = _require_args(action, args, {"track", "enabled"})
        if type(args["enabled"]) is not bool:
            raise ValueError("enabled must be a boolean")
        return action, {"track": _selector(args["track"], "track"), "enabled": args["enabled"]}
    if action in {"set_track_volume", "set_track_pan"}:
        args = _require_args(action, args, {"track", "value"})
        low, high = (0, 1) if action == "set_track_volume" else (-1, 1)
        return action, {"track": _selector(args["track"], "track"),
                        "value": _number(args["value"], "value", low, high)}
    if action in {"fire_scene"}:
        args = _require_args(action, args, {"scene"})
        if type(args["scene"]) is not int or args["scene"] < 1:
            raise ValueError("scene must be a positive one-based integer")
        return action, args
    if action in {"fire_clip", "stop_clip"}:
        args = _require_args(action, args, {"track", "scene"})
        if type(args["scene"]) is not int or args["scene"] < 1:
            raise ValueError("scene must be a positive one-based integer")
        return action, {"track": _selector(args["track"], "track"), "scene": args["scene"]}
    if action == "load_audio_clip":
        args = _require_args(action, args, {"track", "scene", "path"})
        if type(args["scene"]) is not int or args["scene"] < 1:
            raise ValueError("scene must be a positive one-based integer")
        return action, {"track": _selector(args["track"], "track"),
                        "scene": args["scene"], "path": str(_audio_path(args["path"]))}
    if action == "load_audio_to_arrangement":
        args = _require_args(action, args, {"path"}, {"track_name", "position_beats"})
        name = args.get("track_name")
        if name is not None and (not isinstance(name, str) or not name.strip() or len(name) > 120):
            raise ValueError("track_name must be a non-empty string of at most 120 characters")
        position = _number(args.get("position_beats", 0), "position_beats", 0)
        return action, {"path": str(_audio_path(args["path"])),
                        "track_name": name.strip() if name else "",
                        "position_beats": position}
    if action == "list_devices":
        args = _require_args(action, args, {"track"})
        return action, {"track": _selector(args["track"], "track")}
    if action == "device_parameters":
        args = _require_args(action, args, {"track", "device"})
        return action, {"track": _selector(args["track"], "track"),
                        "device": _selector(args["device"], "device")}
    if action == "set_device_parameter":
        args = _require_args(action, args, {"track", "device", "parameter", "value"})
        return action, {
            "track": _selector(args["track"], "track"),
            "device": _selector(args["device"], "device"),
            "parameter": _selector(args["parameter"], "parameter"),
            "value": _number(args["value"], "value"),
        }
    raise ValueError(f"action {action!r} is not implemented")


def _check_cancelled(cancelled: threading.Event) -> None:
    if cancelled.is_set():
        raise TakeoverCancelled("Marko pressed TAKE OVER; Queen stopped sending OSC actions.")


def _ask(osc: ModuleType, address: str, *args: Any, cancelled: threading.Event) -> list[Any]:
    _check_cancelled(cancelled)
    try:
        answer = osc.ask(address, *args, wait=0.8)
    except (OSError, TimeoutError) as exc:
        raise AbletonUnavailable(f"AbletonOSC question failed at {address}: {exc}") from exc
    except RuntimeError as exc:
        raise AbletonControlError(f"Ableton Live rejected {address}: {exc}") from exc
    if answer is None:
        raise AbletonUnavailable(f"AbletonOSC did not answer {address}")
    return list(answer)


def _tell(osc: ModuleType, address: str, *args: Any, cancelled: threading.Event) -> None:
    _check_cancelled(cancelled)
    try:
        osc.tell(address, *args)
    except (OSError, TimeoutError, RuntimeError) as exc:
        raise AbletonUnavailable(f"Could not send AbletonOSC order {address}: {exc}") from exc


def _first(osc: ModuleType, address: str, *args: Any, cancelled: threading.Event) -> Any:
    answer = _ask(osc, address, *args, cancelled=cancelled)
    if not answer:
        raise AbletonControlError(f"AbletonOSC returned an empty answer for {address}")
    return answer[0]


def _track_names(osc: ModuleType, cancelled: threading.Event) -> list[str]:
    return [str(name) for name in _ask(
        osc, "/live/song/get/track_names", cancelled=cancelled,
    )]


def _track_index(osc: ModuleType, selector: int | str, cancelled: threading.Event) -> tuple[int, str]:
    names = _track_names(osc, cancelled)
    if type(selector) is int:
        index = selector - 1
        if index >= len(names):
            raise ValueError(f"track {selector} does not exist; Live has {len(names)} tracks")
        return index, names[index]
    matches = [i for i, name in enumerate(names) if name.casefold() == selector.casefold()]
    if not matches:
        raise ValueError(f"no Live track is named {selector!r}")
    if len(matches) > 1:
        raise ValueError(f"track name {selector!r} is ambiguous; use its one-based number")
    return matches[0], names[matches[0]]


def _track_value(osc: ModuleType, address: str, track: int, cancelled: threading.Event) -> Any:
    answer = _ask(osc, address, track, cancelled=cancelled)
    if len(answer) < 2 or answer[0] != track:
        raise AbletonControlError(f"Unexpected AbletonOSC answer for {address}")
    return answer[1]


def _set_track_value(osc: ModuleType, track: int, property_name: str, value: Any,
                     cancelled: threading.Event) -> Any:
    _tell(osc, f"/live/track/set/{property_name}", track, value, cancelled=cancelled)
    actual = _track_value(osc, f"/live/track/get/{property_name}", track, cancelled)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isclose(float(actual), float(value), rel_tol=1e-4, abs_tol=0.01):
            raise AbletonControlError(f"Live set {property_name} to {actual}, not the requested {value}")
    elif actual != value:
        raise AbletonControlError(f"Live did not confirm {property_name}={value!r} (read back {actual!r})")
    return actual


def _scene_index(osc: ModuleType, scene: int, cancelled: threading.Event) -> int:
    total = int(_first(osc, "/live/song/get/num_scenes", cancelled=cancelled))
    if scene > total:
        raise ValueError(f"scene {scene} does not exist; Live has {total} scenes")
    return scene - 1


def _device_names(osc: ModuleType, track: int, cancelled: threading.Event) -> list[str]:
    answer = _ask(osc, "/live/track/get/devices/name", track, cancelled=cancelled)
    if not answer or answer[0] != track:
        raise AbletonControlError("Unexpected AbletonOSC answer while listing devices")
    return [str(name) for name in answer[1:]]


def _device_index(osc: ModuleType, track: int, selector: int | str,
                  cancelled: threading.Event) -> tuple[int, str]:
    names = _device_names(osc, track, cancelled)
    if type(selector) is int:
        index = selector - 1
        if index < 0 or index >= len(names):
            raise ValueError(f"device {selector} does not exist; Live has {len(names)} devices on that track")
        return index, names[index]
    matches = [i for i, name in enumerate(names) if name.casefold() == selector.casefold()]
    if not matches:
        raise ValueError(f"no loaded device is named {selector!r} on that track")
    if len(matches) > 1:
        raise ValueError(f"device name {selector!r} is ambiguous; use its one-based number")
    return matches[0], names[matches[0]]


def _device_array(osc: ModuleType, prop: str, track: int, device: int,
                  cancelled: threading.Event) -> list[Any]:
    answer = _ask(osc, f"/live/device/get/parameters/{prop}", track, device, cancelled=cancelled)
    if len(answer) < 2 or answer[0] != track or answer[1] != device:
        raise AbletonControlError(f"Unexpected AbletonOSC answer for device parameter {prop}")
    return answer[2:]


def _device_parameters(osc: ModuleType, track: int, device: int,
                       cancelled: threading.Event) -> list[dict[str, Any]]:
    names = _device_array(osc, "name", track, device, cancelled)
    values = _device_array(osc, "value", track, device, cancelled)
    minimums = _device_array(osc, "min", track, device, cancelled)
    maximums = _device_array(osc, "max", track, device, cancelled)
    if not (len(names) == len(values) == len(minimums) == len(maximums)):
        raise AbletonControlError("AbletonOSC returned inconsistent device parameter lists")
    return [
        {"number": index + 1, "name": str(name), "value": value,
         "min": minimum, "max": maximum}
        for index, (name, value, minimum, maximum)
        in enumerate(zip(names, values, minimums, maximums))
    ]


def _parameter_index(parameters: list[dict[str, Any]], selector: int | str) -> int:
    if type(selector) is int:
        index = selector - 1
        if index < 0 or index >= len(parameters):
            raise ValueError(f"parameter {selector} does not exist; the device has {len(parameters)} parameters")
        return index
    matches = [i for i, item in enumerate(parameters) if item["name"].casefold() == selector.casefold()]
    if not matches:
        raise ValueError(f"no parameter is named {selector!r}")
    if len(matches) > 1:
        raise ValueError(f"parameter name {selector!r} is ambiguous; use its one-based number")
    return matches[0]


def _perform(action: str, args: dict[str, Any], osc: ModuleType,
             cancelled: threading.Event) -> dict[str, Any]:
    if action == "status":
        tempo = float(_first(osc, "/live/song/get/tempo", cancelled=cancelled))
        playing = bool(_first(osc, "/live/song/get/is_playing", cancelled=cancelled))
        scenes = int(_first(osc, "/live/song/get/num_scenes", cancelled=cancelled))
        names = _track_names(osc, cancelled)
        return {
            "summary": f"{tempo:g} BPM; {'playing' if playing else 'stopped'}; "
                       f"{len(names)} tracks; {scenes} scenes",
            "confirmed": True,
            "tempo": tempo,
            "playing": playing,
            "tracks": [{"number": index + 1, "name": name} for index, name in enumerate(names)],
            "scenes": scenes,
        }

    if action in {"play", "stop", "continue"}:
        address = {
            "play": "/live/song/start_playing",
            "stop": "/live/song/stop_playing",
            "continue": "/live/song/continue_playing",
        }[action]
        _tell(osc, address, cancelled=cancelled)
        actual = bool(_first(osc, "/live/song/get/is_playing", cancelled=cancelled))
        expected = action != "stop"
        if actual != expected:
            raise AbletonControlError(f"Live did not confirm {action} (is_playing={actual})")
        verb = {"play": "started", "stop": "stopped", "continue": "continued"}[action]
        return {"summary": f"Live playback {verb}.",
                "confirmed": True, "playing": actual}

    if action == "set_tempo":
        _tell(osc, "/live/song/set/tempo", args["bpm"], cancelled=cancelled)
        actual = float(_first(osc, "/live/song/get/tempo", cancelled=cancelled))
        if not math.isclose(actual, args["bpm"], rel_tol=1e-5, abs_tol=0.02):
            raise AbletonControlError(f"Live tempo read back as {actual:g} BPM, not {args['bpm']:g}")
        return {"summary": f"Tempo set to {actual:g} BPM.", "confirmed": True, "bpm": actual}

    if action == "set_metronome":
        target = int(args["enabled"])
        _tell(osc, "/live/song/set/metronome", target, cancelled=cancelled)
        actual = bool(_first(osc, "/live/song/get/metronome", cancelled=cancelled))
        if actual != args["enabled"]:
            raise AbletonControlError(f"Live did not confirm metronome {'on' if args['enabled'] else 'off'}")
        return {"summary": f"Metronome {'on' if actual else 'off'}.", "confirmed": True, "enabled": actual}

    if action in {"create_audio_track", "create_midi_track"}:
        before = _track_names(osc, cancelled)
        kind = "audio" if action == "create_audio_track" else "midi"
        _tell(osc, f"/live/song/create_{kind}_track", -1, cancelled=cancelled)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            names = _track_names(osc, cancelled)
            if len(names) == len(before) + 1:
                return {"summary": f"Created {kind} track {len(names)}: {names[-1]}.",
                        "confirmed": True, "track": len(names), "name": names[-1]}
            time.sleep(0.1)
        raise AbletonControlError(f"OSC sent, but Live did not confirm creation of the {kind} track")

    if action in {"set_track_name", "set_track_mute", "set_track_solo", "set_track_arm",
                  "set_track_volume", "set_track_pan"}:
        track, previous_name = _track_index(osc, args["track"], cancelled)
        if action == "set_track_name":
            prop, value, label = "name", args["name"], f"track {track + 1} name"
        elif action == "set_track_mute":
            prop, value, label = "mute", int(args["enabled"]), f"track {track + 1} mute"
        elif action == "set_track_solo":
            prop, value, label = "solo", int(args["enabled"]), f"track {track + 1} solo"
        elif action == "set_track_arm":
            prop, value, label = "arm", int(args["enabled"]), f"track {track + 1} arm"
        elif action == "set_track_volume":
            prop, value, label = "volume", args["value"], f"track {track + 1} volume"
        else:
            prop, value, label = "panning", args["value"], f"track {track + 1} pan"
        actual = _set_track_value(osc, track, prop, value, cancelled)
        if action == "set_track_name":
            summary = f"Renamed track {track + 1} from {previous_name!r} to {actual!r}."
        else:
            summary = f"Set {label} to {actual}."
        return {"summary": summary, "confirmed": True, "track": track + 1,
                "track_name": str(actual) if prop == "name" else previous_name, "value": actual}

    if action == "fire_scene":
        index = _scene_index(osc, args["scene"], cancelled)
        _tell(osc, "/live/scene/fire", index, cancelled=cancelled)
        return {"summary": f"Sent OSC fire for scene {args['scene']}.",
                "confirmed": False, "scene": args["scene"]}

    if action in {"fire_clip", "stop_clip", "load_audio_clip"}:
        track, track_name = _track_index(osc, args["track"], cancelled)
        scene = _scene_index(osc, args["scene"], cancelled)
        slot = _ask(osc, "/live/clip_slot/get/has_clip", track, scene, cancelled=cancelled)
        if len(slot) < 3 or slot[0] != track or slot[1] != scene:
            raise AbletonControlError("Unexpected AbletonOSC answer while checking the clip slot")
        occupied = bool(slot[2])
        if action == "load_audio_clip":
            if occupied:
                raise ValueError(f"track {track + 1}, scene {scene + 1} already contains a clip")
            _tell(osc, "/live/clip_slot/create_audio_clip", track, scene, args["path"], cancelled=cancelled)
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                _check_cancelled(cancelled)
                slot = _ask(osc, "/live/clip_slot/get/has_clip", track, scene, cancelled=cancelled)
                if len(slot) >= 3 and bool(slot[2]):
                    return {"summary": f"Loaded {Path(args['path']).name} into track {track + 1}, "
                                       f"scene {scene + 1} ({track_name}).",
                            "confirmed": True, "track": track + 1, "scene": scene + 1}
                time.sleep(0.1)
            raise AbletonControlError("OSC sent, but Live did not confirm that the audio clip loaded")
        if not occupied:
            raise ValueError(f"track {track + 1}, scene {scene + 1} is empty")
        if action == "fire_clip":
            _tell(osc, "/live/clip_slot/fire", track, scene, cancelled=cancelled)
            return {"summary": f"Sent OSC fire for the clip on track {track + 1}, scene {scene + 1}.",
                    "confirmed": False, "track": track + 1, "scene": scene + 1}
        _tell(osc, "/live/clip_slot/stop", track, scene, cancelled=cancelled)
        return {"summary": f"Sent OSC stop for the clip on track {track + 1}, scene {scene + 1}.",
                "confirmed": False, "track": track + 1, "scene": scene + 1}

    if action == "load_audio_to_arrangement":
        path = args["path"]
        name = args["track_name"] or Path(path).stem
        response = _ask(
            osc, "/live/arrangement/audio_clip", path, name, args["position_beats"],
            cancelled=cancelled,
        )
        if len(response) < 2:
            raise AbletonControlError("Live did not confirm the arrangement audio clip")
        track, clip_count = int(response[0]), int(response[1])
        return {"summary": f"Loaded {Path(path).name} onto new arrangement track {track + 1} "
                           f"({name}); Live reports {clip_count} clip(s).",
                "confirmed": True, "track": track + 1, "track_name": name, "clips": clip_count}

    if action in {"list_devices", "device_parameters", "set_device_parameter"}:
        track, track_name = _track_index(osc, args["track"], cancelled)
        if action == "list_devices":
            names = _device_names(osc, track, cancelled)
            return {"summary": f"Track {track + 1} ({track_name}) has {len(names)} loaded device(s).",
                    "confirmed": True, "track": track + 1,
                    "devices": [{"number": i + 1, "name": name} for i, name in enumerate(names)]}
        device, device_name = _device_index(osc, track, args["device"], cancelled)
        parameters = _device_parameters(osc, track, device, cancelled)
        if action == "device_parameters":
            return {"summary": f"Read {len(parameters)} parameter(s) from {device_name} on {track_name}.",
                    "confirmed": True, "track": track + 1, "track_name": track_name,
                    "device": device + 1, "device_name": device_name, "parameters": parameters}
        parameter = _parameter_index(parameters, args["parameter"])
        selected = parameters[parameter]
        value = _number(args["value"], "value", float(selected["min"]), float(selected["max"]))
        _tell(osc, "/live/device/set/parameter/value", track, device, parameter, value,
              cancelled=cancelled)
        readback = _ask(osc, "/live/device/get/parameter/value", track, device, parameter,
                        cancelled=cancelled)
        if len(readback) < 4 or readback[0] != track or readback[1] != device or readback[2] != parameter:
            raise AbletonControlError("Unexpected AbletonOSC answer while verifying the device parameter")
        actual = float(readback[3])
        if not math.isclose(actual, value, rel_tol=1e-4, abs_tol=0.01):
            raise AbletonControlError(f"Live set {selected['name']} to {actual:g}, not the requested {value:g}")
        return {"summary": f"Set {device_name} · {selected['name']} to {actual:g} on {track_name}.",
                "confirmed": True, "track": track + 1, "device": device + 1,
                "device_name": device_name, "parameter": selected["name"], "value": actual}

    if action == "stop_all_clips":
        _tell(osc, "/live/song/stop_all_clips", cancelled=cancelled)
        return {"summary": "Sent OSC stop-all-clips order.", "confirmed": False}

    raise ValueError(f"action {action!r} is not implemented")


def execute_action(action: Any, arguments: Any = None) -> dict[str, Any]:
    """Execute one validated action; all app control is guarded and provider-independent."""
    action, args = _normalize(action, {} if arguments is None else arguments)
    if os.environ.get("GUARD") == "0":
        raise AbletonUnavailable("Refusing to control Live while GUARD=0 disables the takeover notice")
    guard = _load_guard()
    osc = _load_liveosc()
    cancelled = threading.Event()
    try:
        notice = guard.held(
            "Queen is taking over Ableton Live",
            seconds=60,
            on_override=lambda _status: cancelled.set(),
        )
        with notice:
            _check_cancelled(cancelled)
            _ask(osc, "/live/test", cancelled=cancelled)
            result = _perform(action, args, osc, cancelled)
            _check_cancelled(cancelled)
    except guard.Overridden as exc:
        raise TakeoverCancelled("Marko took over; Queen did not continue the Ableton action") from exc
    except guard.Unavailable as exc:
        raise AbletonUnavailable(f"Macro Recorder takeover guard is unavailable: {exc}") from exc
    return {"action": action, "takeover_notice": True, **result}


def parse_command(text: str) -> tuple[str, dict[str, Any]]:
    """Parse the deliberately small, explicit command syntax used before any model routing."""
    if not isinstance(text, str) or not text.strip().casefold().startswith("ableton:"):
        raise ValueError("local Ableton commands must start with 'ABLETON:'")
    try:
        words = shlex.split(text.strip().split(":", 1)[1].strip())
    except ValueError as exc:
        raise ValueError(f"invalid Ableton command quoting: {exc}") from exc
    lower = [word.casefold() for word in words]
    if not words:
        raise ValueError("ABLETON: needs an action; use 'ABLETON: status' or query /api/ableton/capabilities")
    if lower == ["status"]:
        return "status", {}
    if len(words) == 1 and lower[0] in {"play", "stop", "continue"}:
        return lower[0], {}
    if lower[:2] == ["set", "tempo"] and len(words) == 3:
        try:
            return "set_tempo", {"bpm": float(words[2])}
        except ValueError as exc:
            raise ValueError("tempo must be a number, for example 'ABLETON: set tempo 120'") from exc
    if lower[:1] == ["metronome"] and len(words) == 2 and lower[1] in {"on", "off"}:
        return "set_metronome", {"enabled": lower[1] == "on"}
    if lower in (["create", "audio", "track"], ["create", "midi", "track"]):
        return f"create_{lower[1]}_track", {}
    if len(words) == 3 and lower[0] in {"mute", "unmute", "solo", "unsolo", "arm", "disarm"} \
            and lower[1] == "track":
        selector = _parse_selector(words[2])
        kind = {"mute": "mute", "unmute": "mute", "solo": "solo", "unsolo": "solo",
                "arm": "arm", "disarm": "arm"}[lower[0]]
        enabled = lower[0] in {"mute", "solo", "arm"}
        return f"set_track_{kind}", {"track": selector, "enabled": enabled}
    if len(words) == 4 and lower[0] in {"volume", "pan"} and lower[1] == "track":
        try:
            value = float(words[3])
        except ValueError as exc:
            raise ValueError(f"{lower[0]} must be a number") from exc
        return f"set_track_{'volume' if lower[0] == 'volume' else 'pan'}", {
            "track": _parse_selector(words[2]), "value": value,
        }
    if len(words) >= 4 and lower[:2] == ["rename", "track"]:
        return "set_track_name", {"track": _parse_selector(words[2]), "name": " ".join(words[3:])}
    if len(words) == 3 and lower[:2] == ["fire", "scene"]:
        return "fire_scene", {"scene": _parse_positive_int(words[2], "scene")}
    if len(words) == 4 and lower[:2] in (["fire", "clip"], ["stop", "clip"]):
        return ("fire_clip" if lower[0] == "fire" else "stop_clip"), {
            "track": _parse_selector(words[2]), "scene": _parse_positive_int(words[3], "scene"),
        }
    if len(words) == 3 and lower[:2] == ["devices", "track"]:
        return "list_devices", {"track": _parse_selector(words[2])}
    if len(words) == 6 and lower[0:2] == ["device", "parameters"] \
            and lower[2] == "track" and lower[4] == "device":
        return "device_parameters", {"track": _parse_selector(words[3]),
                                     "device": _parse_selector(words[5])}
    if (len(words) == 10 and lower[:2] == ["set", "parameter"]
            and lower[2] == "track" and lower[4] == "device" and lower[6] == "parameter"
            and lower[8] == "value"):
        try:
            value = float(words[9])
        except ValueError as exc:
            raise ValueError("parameter value must be a number") from exc
        return "set_device_parameter", {
            "track": _parse_selector(words[3]), "device": _parse_selector(words[5]),
            "parameter": _parse_selector(words[7]), "value": value,
        }
    if len(words) == 8 and lower[:2] == ["load", "audio"] \
            and lower[3:5] == ["on", "track"] and lower[6] == "scene":
        return "load_audio_clip", {
            "path": words[2], "track": _parse_selector(words[5]),
            "scene": _parse_positive_int(words[7], "scene"),
        }
    raise ValueError("unsupported Ableton command; query /api/ableton/capabilities for the exact action list")


def _parse_selector(value: str) -> int | str:
    if value.isdecimal():
        return int(value)
    return value


def _parse_positive_int(value: str, label: str) -> int:
    try:
        result = int(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be a positive integer") from exc
    if result < 1:
        raise ValueError(f"{label} must be a positive integer")
    return result


def execute_text(text: str) -> str:
    """Run one explicit text command and return a truthful result for Queen's chat."""
    try:
        action, arguments = parse_command(text)
        result = execute_action(action, arguments)
    except (ValueError, AbletonControlError) as exc:
        return f"NOT DONE: {exc}"
    if action == "status":
        tracks = "\n".join(f"  {item['number']}. {item['name']}" for item in result["tracks"])
        return f"Ableton Live via AbletonOSC: {result['summary']}." + (f"\n{tracks}" if tracks else "")
    if result.get("confirmed"):
        return f"Done and verified through AbletonOSC: {result['summary']}"
    return f"OSC order sent but not confirmed by Live: {result['summary']}"
