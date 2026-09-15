from __future__ import annotations

import json
import re
from pathlib import Path

from r1_agent.catalog import Action, Catalog, ScenePack, merge_scene

SCHEMA = "r1-student-program/v1"
_NAME_OK = re.compile(r"^[\w\u4e00-\u9fff-]{1,20}$")


class ProgramError(ValueError):
    pass


def wait_action(seconds: float) -> Action:
    seconds = max(0.0, min(8.0, float(seconds)))
    return Action(name="wait", title=f"等待{seconds:g}秒", kind="wait", args={"seconds": seconds})


def expand_steps(steps: list[str], catalog: Catalog) -> list[Action]:
    actions: list[Action] = []
    for step in steps:
        if step.startswith("say:"):
            key = step.split(":", 1)[1]
            if key not in catalog.speech:
                raise ProgramError(f"未知台词 {key}")
            text = catalog.speech[key]
            actions.append(Action(name=step, title=text, kind="speech", args={"text": text}))
            continue
        if step not in catalog.actions:
            raise ProgramError(f"未知动作 {step}")
        actions.append(catalog.actions[step])
    return actions


def apply_custom_groups(catalog: Catalog, groups: dict[str, list[str]]) -> Catalog:
    if not groups:
        return catalog
    pack = ScenePack(context="", compositions=groups, aliases={}, speech={}, forbidden=())
    return merge_scene(catalog, pack)


def validate_group_name(name: str, catalog: Catalog) -> str:
    name = name.strip()
    if not _NAME_OK.match(name):
        raise ProgramError("动作组名字只能用中文、字母、数字、下划线，最多 20 字")
    if name in catalog.actions:
        raise ProgramError(f"{name} 是系统原子动作，请换一个名字")
    if name in catalog.forbidden:
        raise ProgramError("这个名字在禁止列表里")
    return name


def compile_blocks(blocks: list[dict], catalog: Catalog) -> list[Action]:
    if not isinstance(blocks, list):
        raise ProgramError("程序必须是方块数组")
    if len(blocks) > 40:
        raise ProgramError("一条程序最多 40 个方块")
    actions: list[Action] = []
    for block in blocks:
        if not isinstance(block, dict):
            raise ProgramError("方块格式不对")
        kind = block.get("type")
        if kind == "say":
            text = str(block.get("text") or "").strip()
            if not text or len(text) > 80:
                raise ProgramError("说话内容需要 1～80 个字")
            actions.append(Action(name="say", title=text, kind="speech", args={"text": text}))
            continue
        if kind == "wait":
            actions.append(wait_action(block.get("seconds") or 1))
            continue
        if kind in ("action", "move", "turn"):
            name = str(block.get("name") or "")
            if name not in catalog.actions:
                raise ProgramError(f"未知动作 {name}")
            atom = catalog.actions[name]
            if kind == "move" and atom.kind not in ("move",):
                raise ProgramError(f"{name} 不是移动方块")
            if kind == "turn" and atom.kind != "turn":
                raise ProgramError(f"{name} 不是转向方块")
            repeat = int(block.get("repeat") or 1)
            if repeat < 1 or repeat > 10:
                raise ProgramError("重复次数只能 1～10")
            actions.extend([atom] * repeat)
            continue
        if kind in ("group", "custom"):
            name = str(block.get("name") or "")
            steps = catalog.compositions.get(name)
            if not steps:
                raise ProgramError(f"未知动作组 {name}")
            actions.extend(expand_steps(steps, catalog))
            continue
        raise ProgramError(f"不支持的方块类型 {kind}")
    return actions


def describe_action(action: Action) -> dict:
    """给学生看：这一步实际会发给 R1 什么。只说明，不下发。"""
    kind = action.kind
    if kind == "speech":
        text = str(action.args.get("text") or action.title)
        return {
            "title": action.title,
            "kind": kind,
            "summary": f"语音：让 R1 说「{text}」",
            "command": f'AudioClient.TtsMaker("{text}")',
            "channel": "语音 RPC（不是走路）",
        }
    if kind == "wait":
        seconds = float(action.args.get("seconds") or 0)
        return {
            "title": action.title,
            "kind": kind,
            "summary": f"等待 {seconds:g} 秒，这期间不发新的走路/上肢指令",
            "command": f"time.sleep({seconds:g})",
            "channel": "教师电脑本地计时",
        }
    if kind in ("move", "turn"):
        vx = float(action.args.get("vx") or 0)
        vy = float(action.args.get("vy") or 0)
        omega = float(action.args.get("omega") or 0)
        duration = float(action.args.get("duration") or 0)
        if duration <= 0 and abs(vx) + abs(vy) + abs(omega) < 1e-6:
            return {
                "title": action.title,
                "kind": kind,
                "summary": "停步：让机器人站住",
                "command": "LocoClient.StopMove()",
                "channel": "行走 RPC · 需要已在走跑 FSM 811/816",
            }
        return {
            "title": action.title,
            "kind": kind,
            "summary": f"{action.title}：vx={vx:g} m/s，vy={vy:g} m/s，ω={omega:g} rad/s，持续 {duration:g} 秒",
            "command": (
                f"LocoClient.SetVelocity({vx:g}, {vy:g}, {omega:g}, {max(0.5, duration):g})"
            ),
            "channel": "行走 RPC · 需要已在走跑 FSM 811/816",
        }
    frames = 0
    try:
        from r1_agent.dds_robot import MOTIONS

        frames = len(MOTIONS.get(action.name) or [])
    except Exception:
        frames = 0
    extra = f"，约 {frames} 段关键姿态" if frames else ""
    return {
        "title": action.title,
        "kind": kind,
        "summary": f"上肢：{action.title}（先回课堂准备姿态，做完再回准备姿态{extra}）",
        "command": f'rt/arm_sdk ← LowCmd 关节角序列 "{action.name}"',
        "channel": "DDS 话题 rt/arm_sdk",
    }


def inspect_blocks(blocks: list[dict], catalog: Catalog, *, index: int | None = None) -> dict:
    if index is None:
        actions = compile_blocks(blocks, catalog)
        trailing = True
        scope = "program"
        heading = "整段程序会按顺序发给 R1"
    else:
        if not isinstance(index, int) or index < 0 or index >= len(blocks):
            raise ProgramError("请先点程序里的那一块")
        actions = compile_blocks([blocks[index]], catalog)
        trailing = False
        scope = "block"
        heading = "这一块会发给 R1"
    steps = [describe_action(action) for action in actions]
    if trailing:
        steps.append(
            {
                "title": "程序结束停步",
                "kind": "stop",
                "summary": "整段跑完后会再发一次停步，避免继续走",
                "command": "LocoClient.StopMove()",
                "channel": "行走 RPC",
            }
        )
    lines = [heading + "（只预览，不会真的动）："]
    for i, step in enumerate(steps, 1):
        lines.append(f"{i}. {step['summary']}")
        lines.append(f"   命令：{step['command']}")
        lines.append(f"   通道：{step['channel']}")
    return {
        "ok": True,
        "scope": scope,
        "heading": heading,
        "steps": steps,
        "titles": [action.title for action in actions],
        "text": "\n".join(lines),
    }


def load_program(payload: dict, catalog: Catalog) -> tuple[str, list[Action]]:
    if payload.get("schema") not in (SCHEMA, None):
        if payload.get("schema") and not str(payload["schema"]).startswith("r1-student-program/"):
            raise ProgramError("不是 R1 学生程序文件")
    name = str(payload.get("name") or "未命名程序").strip()[:40]
    actions = compile_blocks(payload.get("blocks") or [], catalog)
    return name, actions


def dump_program(*, name: str, author: str, blocks: list[dict]) -> dict:
    return {
        "schema": SCHEMA,
        "name": name,
        "author": author,
        "blocks": blocks,
    }


def load_groups_file(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    groups = payload.get("compositions") if isinstance(payload, dict) else payload
    if not isinstance(groups, dict):
        raise ProgramError("自定义动作组文件格式不对")
    return {str(key): [str(step) for step in value] for key, value in groups.items()}


def save_groups_file(path: Path, groups: dict[str, list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"compositions": groups}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
