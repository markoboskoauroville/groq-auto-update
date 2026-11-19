"""Offline tests for Queen's provider-independent AbletonOSC skill."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from queen_python_skills import ableton


class FakeOSC:
    def __init__(self) -> None:
        self.tempo = 119.0
        self.playing = False
        self.names = ["Vocal", "Drums"]
        self.mutes: dict[int, int] = {}
        self.orders: list[tuple[str, tuple[object, ...]]] = []

    def ask(self, address: str, *args: object, wait: float = 0.8) -> list[object]:
        if address == "/live/test":
            return [1]
        if address == "/live/song/get/tempo":
            return [self.tempo]
        if address == "/live/song/get/is_playing":
            return [self.playing]
        if address == "/live/song/get/track_names":
            return list(self.names)
        if address == "/live/track/get/mute":
            return [args[0], self.mutes.get(int(args[0]), 0)]
        raise AssertionError(f"Unexpected OSC query: {address} {args}")

    def tell(self, address: str, *args: object) -> None:
        self.orders.append((address, args))
        if address == "/live/song/set/tempo":
            self.tempo = float(args[0])
        elif address == "/live/track/set/mute":
            self.mutes[int(args[0])] = int(args[1])


class FakeNotice:
    def __init__(self, callback=None, override: bool = False) -> None:
        self.callback = callback
        self.override = override

    def __enter__(self):
        if self.override and self.callback:
            self.callback({"lock": "overridden"})
        return self

    def __exit__(self, *_exc):
        return False


class FakeGuard:
    class Unavailable(Exception):
        pass

    class Overridden(Exception):
        pass

    def __init__(self, override: bool = False) -> None:
        self.override = override
        self.what = ""

    def held(self, what: str, seconds: int, on_override):
        self.what = what
        return FakeNotice(on_override, self.override)


def check(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(name)
    print(f"PASS {name}")


fake_osc = FakeOSC()
fake_guard = FakeGuard()
with patch.object(ableton, "_load_guard", return_value=fake_guard), \
     patch.object(ableton, "_load_liveosc", return_value=fake_osc):
    tempo = ableton.execute_action("set_tempo", {"bpm": 123.5})
    check("tempo action sends OSC and verifies Live readback",
          tempo["confirmed"] and fake_osc.tempo == 123.5
          and fake_osc.orders[-1] == ("/live/song/set/tempo", (123.5,)))
    check("every action uses the visible takeover notice",
          fake_guard.what == "Queen is taking over Ableton Live" and tempo["takeover_notice"])

    mute = ableton.execute_action("set_track_mute", {"track": "Drums", "enabled": True})
    check("track names resolve exactly and mute state is read back",
          mute["confirmed"] and mute["track"] == 2 and fake_osc.mutes[1] == 1)

try:
    ableton.execute_action("set_tempo", {"bpm": 1000})
    invalid_tempo_rejected = False
except ValueError:
    invalid_tempo_rejected = True
check("invalid tempo is rejected before loading or using integrations", invalid_tempo_rejected)

action, arguments = ableton.parse_command('ABLETON: SET TEMPO 119.5')
check("provider-independent text command parses without an AI model",
      action == "set_tempo" and arguments == {"bpm": 119.5})
action, arguments = ableton.parse_command('ABLETON: rename TRACK 1 "Lead Vocal"')
check("quoted track names preserve case", action == "set_track_name"
      and arguments == {"track": 1, "name": "Lead Vocal"})
action, arguments = ableton.parse_command(
    'ABLETON: load audio "/Music/My Song.wav" on track 1 scene 2'
)
check("quoted audio paths with spaces parse correctly",
      action == "load_audio_clip"
      and arguments == {"path": "/Music/My Song.wav", "track": 1, "scene": 2})

interrupted_osc = FakeOSC()
interrupted_guard = FakeGuard(override=True)
with patch.object(ableton, "_load_guard", return_value=interrupted_guard), \
     patch.object(ableton, "_load_liveosc", return_value=interrupted_osc):
    try:
        ableton.execute_action("play")
        cancelled = False
    except ableton.TakeoverCancelled:
        cancelled = True
check("TAKE OVER aborts before Queen sends an OSC action",
      cancelled and not interrupted_osc.orders)

schema = ableton.capabilities()
check("capabilities are model-provider independent and document the endpoint",
      schema["provider_independent"]
      and any(item["name"] == "set_device_parameter" for item in schema["actions"])
      and any(command.startswith("ABLETON:") for command in schema["text_commands"]))

print("ALL PASS")
