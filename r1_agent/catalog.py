from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Action:
    name: str
    title: str
    kind: str
    args: dict = field(default_factory=dict)
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class Catalog:
    actions: dict[str, Action]
    speech: dict[str, str]
    compositions: dict[str, list[str]]
    forbidden: tuple[str, ...]
    aliases: tuple[tuple[str, str], ...]


def _action(item: dict) -> Action:
    return Action(
        name=item["name"],
        title=item["title"],
        kind=item["kind"],
        args=dict(item.get("args") or {}),
        aliases=tuple(item.get("aliases") or ()),
    )


@cache
def load_catalog(path: Path | None = None) -> Catalog:
    payload = json.loads((path or ROOT / "actions.json").read_text(encoding="utf-8"))
    actions = {item["name"]: _action(item) for item in payload["actions"]}
    aliases: list[tuple[str, str]] = []
    for action in actions.values():
        for phrase in action.aliases:
            aliases.append((phrase, action.name))
    aliases.sort(key=lambda item: len(item[0]), reverse=True)
    return Catalog(
        actions=actions,
        speech=dict(payload.get("speech") or {}),
        compositions={key: list(value) for key, value in (payload.get("compositions") or {}).items()},
        forbidden=tuple(payload.get("forbidden") or ()),
        aliases=tuple(aliases),
    )
