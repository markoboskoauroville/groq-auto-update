"""Deterministic, local skills for commands Queen can execute without a model call."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class SkillResult:
    skill_id: str
    answer: str


@dataclass(frozen=True)
class Skill:
    skill_id: str
    description: str
    commands: frozenset[str]
    handler: Callable[[dict | None], SkillResult]


def _list_skills(_context: dict | None = None) -> SkillResult:
    lines = ["Available local Python skills:"]
    for skill in SKILLS:
        if skill.skill_id != "list-skills":
            lines.append(f"- {skill.skill_id}: {skill.description}")
    lines.append("Unmatched tasks continue to the selected CAPI provider.")
    return SkillResult("list-skills", "\n".join(lines))


def _current_folder(context: dict | None = None) -> SkillResult:
    cwd = str((context or {}).get("cwd") or "")
    if not cwd:
        return SkillResult("current-folder", "No working folder is selected for this chat.")
    return SkillResult("current-folder", f"This chat's working folder is:\n{cwd}")


def _ableton_help(_context: dict | None = None) -> SkillResult:
    from . import ableton
    examples = "\n".join(f"- {command}" for command in ableton.capabilities()["text_commands"])
    return SkillResult(
        "ableton-control",
        "Provider-independent AbletonOSC control is available. Use an explicit `ABLETON:` command; "
        "structured callers can use GET /api/ableton/capabilities and POST /api/ableton/action.\n"
        + examples,
    )


SKILLS = (
    Skill(
        skill_id="list-skills",
        description="List predefined actions that run locally without a model call.",
        commands=frozenset({
            "list skills",
            "show skills",
            "show available actions",
            "what skills do you have",
            "what can you do",
        }),
        handler=_list_skills,
    ),
    Skill(
        skill_id="current-folder",
        description="Show this chat's selected working folder.",
        commands=frozenset({
            "current folder",
            "what folder is open",
            "which folder am i working in",
        }),
        handler=_current_folder,
    ),
    Skill(
        skill_id="ableton-control",
        description=(
            "Provider-independent Ableton Live control through guarded AbletonOSC. Use `ABLETON: <action>` "
            "or the structured /api/ableton/action interface; supports transport, tempo, tracks, clips, audio "
            "loading, and parameters of already-loaded devices/plugins."
        ),
        commands=frozenset({"ableton help", "ableton actions"}),
        handler=_ableton_help,
    ),
)


def catalog() -> list[dict[str, str]]:
    return [
        {"id": skill.skill_id, "description": skill.description}
        for skill in SKILLS
    ]


def dispatch(text: str, context: dict | None = None) -> SkillResult | None:
    """Run an exact, registered command; return None for tasks requiring CAPI."""
    command = " ".join((text or "").split()).casefold()
    if not command:
        return None
    if command.startswith("ableton:"):
        from . import ableton
        return SkillResult("ableton-control", ableton.execute_text(text))
    for skill in SKILLS:
        if command in skill.commands:
            return skill.handler(context)
    return None
