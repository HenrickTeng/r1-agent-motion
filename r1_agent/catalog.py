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
    prompt_compositions: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class ScenePack:
    context: str
    compositions: dict[str, list[str]]
    aliases: dict[str, str]
    speech: dict[str, str]
    forbidden: tuple[str, ...]


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


def resolve_scene_dir(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate.resolve()
    if not candidate.is_absolute():
        rooted = ROOT / candidate
        if rooted.exists():
            return rooted.resolve()
    raise FileNotFoundError(f"scene directory not found: {path}")


def load_scene_pack(path: str | Path) -> ScenePack:
    directory = resolve_scene_dir(path)
    if not directory.is_dir():
        raise FileNotFoundError(f"scene path is not a directory: {directory}")
    pack_path = directory / "pack.json"
    context_path = directory / "context.txt"
    if not pack_path.exists() and not context_path.exists():
        raise FileNotFoundError(f"scene directory needs pack.json or context.txt: {directory}")
    payload: dict = {}
    if pack_path.exists():
        loaded = json.loads(pack_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError(f"pack.json must be an object: {pack_path}")
        payload = loaded
    context = ""
    if context_path.exists():
        context = context_path.read_text(encoding="utf-8").strip()
    elif isinstance(payload.get("context"), str):
        context = payload["context"].strip()
    compositions = payload.get("compositions") or {}
    aliases = payload.get("aliases") or {}
    speech = payload.get("speech") or {}
    forbidden = payload.get("forbidden") or []
    if not isinstance(compositions, dict) or not isinstance(aliases, dict) or not isinstance(speech, dict):
        raise ValueError(f"pack.json compositions/aliases/speech must be objects: {pack_path}")
    if not isinstance(forbidden, list) or not all(isinstance(item, str) for item in forbidden):
        raise ValueError(f"pack.json forbidden must be a string array: {pack_path}")
    for name, steps in compositions.items():
        if not isinstance(name, str) or not isinstance(steps, list) or not all(isinstance(step, str) for step in steps):
            raise ValueError(f"scene composition {name!r} must be a string array")
    for phrase, target in aliases.items():
        if not isinstance(phrase, str) or not isinstance(target, str):
            raise ValueError("scene aliases must map phrase strings to action or composition names")
    for key, text in speech.items():
        if not isinstance(key, str) or not isinstance(text, str):
            raise ValueError("scene speech must map names to strings")
    return ScenePack(
        context=context,
        compositions={key: list(value) for key, value in compositions.items()},
        aliases=dict(aliases),
        speech=dict(speech),
        forbidden=tuple(forbidden),
    )


def _known_step(catalog: Catalog, speech: dict[str, str], step: str) -> bool:
    if step.startswith("say:"):
        return step.split(":", 1)[1] in speech
    return step in catalog.actions


def merge_scene(catalog: Catalog, pack: ScenePack) -> Catalog:
    speech = {**catalog.speech, **pack.speech}
    compositions = {**catalog.compositions, **pack.compositions}
    extra_aliases: list[tuple[str, str]] = []
    extra_by_action: dict[str, list[str]] = {}
    prompt_compositions = {key: list(value) for key, value in pack.compositions.items()}
    for name, steps in pack.compositions.items():
        unknown = [step for step in steps if not _known_step(catalog, speech, step)]
        if unknown:
            raise ValueError(f"scene composition {name!r} uses unknown atoms: {unknown}")
    for phrase, target in pack.aliases.items():
        if target in compositions:
            prompt_compositions[phrase] = list(compositions[target])
            compositions[phrase] = list(compositions[target])
        elif target in catalog.actions:
            extra_aliases.append((phrase, target))
            extra_by_action.setdefault(target, []).append(phrase)
        else:
            raise ValueError(f"scene alias {phrase!r} targets unknown name {target!r}")
    actions = {}
    for name, action in catalog.actions.items():
        added = extra_by_action.get(name)
        if added:
            actions[name] = Action(
                name=action.name,
                title=action.title,
                kind=action.kind,
                args=dict(action.args),
                aliases=action.aliases + tuple(added),
            )
        else:
            actions[name] = action
    alias_phrases = {phrase for phrase, _ in extra_aliases}
    aliases = [(phrase, name) for phrase, name in catalog.aliases if phrase not in alias_phrases]
    aliases.extend(extra_aliases)
    aliases.sort(key=lambda item: len(item[0]), reverse=True)
    return Catalog(
        actions=actions,
        speech=speech,
        compositions=compositions,
        forbidden=catalog.forbidden + pack.forbidden,
        aliases=tuple(aliases),
        prompt_compositions=prompt_compositions,
    )
