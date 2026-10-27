"""技能包与具身 Python 指令。动作 id 与平台技能封装一致。

真机只执行已经在走跑白名单里的动作，以及动作库里的上肢关键帧。
坐下、蹲下不发给 R1。if 条件平台自己也不在仿真里求值，真机运行会拒绝带 if 的流程；
导出的 ZIP 仍按 eduplatform-skillpack/v3 原样保留。
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import zipfile
from typing import Mapping

from r1_agent.catalog import Action, Catalog
from r1_studio.motion_library import ANGLE_CONVENTION, MotionError, export_motion

SKILLPACK_SCHEMA = "eduplatform-skillpack/v3"
MAX_STEPS = 40
MAX_NEST = 3

# 平台积木 id → 真机白名单。None 表示真机拒绝。
BUILTIN_ACTIONS: dict[str, str | None] = {
    "walk_forward": "move_forward_slow",
    "walk_back": "move_backward_slow",
    "turn_left": "turn_left",
    "turn_right": "turn_right",
    "stand": "ready_pose",
    "sit": None,
    "crouch": None,
    "toss": "cheer_both",
    "wave": "wave_right",
    "raise_hand": "raise_hand_right",
    "salute": "salute_right",
    "nod": "nod",
    "shake_head": "shake_head",
    "stretch": "stretch",
}

BUILTIN_LABELS = {
    "walk_forward": "前进",
    "walk_back": "后退",
    "turn_left": "左转",
    "turn_right": "右转",
    "stand": "站立",
    "sit": "坐下",
    "crouch": "蹲下",
    "toss": "抛手",
    "wave": "招手",
    "raise_hand": "举手",
    "salute": "抱拳",
    "nod": "点头",
    "shake_head": "摇头",
    "stretch": "伸懒腰",
}

PYTHON_GUIDE = """# 可组合以下指令。注释不会执行。
# robot.stand()
# robot.sit()          # 真机不执行坐下
# robot.move(vx=0.2, seconds=2)
# robot.turn(degrees=90)   # 正数左转，负数右转
# robot.wave(times=2)
# robot.raise_hand()
# robot.salute()
# robot.nod(times=2)
# robot.stop()
"""


class SkillError(ValueError):
    pass


def _count(steps: list) -> int:
    total = 0
    for step in steps:
        total += 1
        if step.get("kind") == "for":
            total += _count(step.get("children") or [])
        elif step.get("kind") == "if":
            total += _count(step.get("then") or []) + _count(step.get("else") or [])
    return total


def _unit(action_id: str, source: str) -> str:
    if source == "custom":
        return "次"
    if action_id in ("walk_forward", "walk_back"):
        return "步"
    if action_id in ("turn_left", "turn_right"):
        return "度"
    if action_id in ("stand", "sit", "crouch"):
        return "秒"
    return "次"


def _check_amount(action_id: str, source: str, amount: float) -> float:
    if source == "custom":
        if int(amount) != amount or not 1 <= int(amount) <= 5:
            raise SkillError("自己录的动作只能重复 1～5 次。")
        return float(int(amount))
    if action_id in ("walk_forward", "walk_back"):
        if int(amount) != amount or not 1 <= int(amount) <= 10:
            raise SkillError("前进和后退是 1～10 步。")
        return float(int(amount))
    if action_id in ("turn_left", "turn_right"):
        value = int(amount)
        if value != amount or value < 15 or value > 360 or value % 15:
            raise SkillError("转向是 15～360 度，每 15 度一档。")
        return float(value)
    if action_id in ("stand", "sit", "crouch"):
        if amount < 0.5 or amount > 10:
            raise SkillError("站立、坐下、蹲下的保持时间是 0.5～10 秒。")
        return float(amount)
    if int(amount) != amount or not 1 <= int(amount) <= 20:
        raise SkillError("这个动作的次数超出范围。")
    return float(int(amount))


def validate_workflow(steps: list, groups: Mapping[str, dict], *, depth: int = 0) -> None:
    if not isinstance(steps, list):
        raise SkillError("技能流程必须是数组。")
    if _count(steps) > MAX_STEPS:
        raise SkillError(f"积木最多 {MAX_STEPS} 块。")
    for step in steps:
        if not isinstance(step, dict):
            raise SkillError("积木格式不对。")
        kind = step.get("kind")
        if kind == "wait":
            seconds = float(step.get("seconds") or 0)
            if seconds < 0.1 or seconds > 10:
                raise SkillError("等待要在 0.1～10 秒之间。")
            continue
        if kind == "for":
            if depth + 1 >= MAX_NEST:
                raise SkillError("循环最多嵌套 3 层。")
            times = step.get("times")
            if not isinstance(times, int) or not 2 <= times <= 10:
                raise SkillError("循环次数要在 2～10 之间。")
            validate_workflow(step.get("children") or [], groups, depth=depth + 1)
            continue
        if kind == "if":
            validate_workflow(step.get("then") or [], groups, depth=depth + 1)
            validate_workflow(step.get("else") or [], groups, depth=depth + 1)
            continue
        if kind != "action":
            raise SkillError(f"不支持的积木 {kind}")
        source = "custom" if step.get("source") == "custom" else "builtin"
        action_id = str(step.get("id") or "")
        if source == "builtin" and action_id not in BUILTIN_ACTIONS:
            raise SkillError(f"未知动作 {action_id}")
        if source == "custom" and action_id not in groups:
            raise SkillError(f"动作库里没有 {action_id}")
        _check_amount(action_id, source, float(step.get("amount") or 1))


def _turn_action(action_id: str, degrees: float) -> Action:
    sign = 1.0 if action_id == "turn_left" else -1.0
    duration = abs(degrees) * math.pi / 180.0
    title = f"{'向左转' if sign > 0 else '向右转'}{int(degrees)}度"
    return Action(
        name=action_id,
        title=title,
        kind="turn",
        args={"vx": 0.0, "vy": 0.0, "omega": sign, "duration": round(duration, 3)},
    )


def _hold_ready(seconds: float) -> list[dict]:
    return [{"kind": "wait", "seconds": seconds}]


def expand_workflow(steps: list, groups: Mapping[str, dict], catalog: Catalog) -> list[dict]:
    """展开成可执行步骤。遇到 if 直接拒绝，避免在真机上猜条件。"""
    validate_workflow(steps, groups)
    planned: list[dict] = []

    def walk(items: list) -> None:
        for step in items:
            kind = step.get("kind")
            if kind == "if":
                raise SkillError("真机不判断 if 条件。请去掉判断后再运行；导出的技能包仍会保留 if。")
            if kind == "wait":
                planned.append({"kind": "wait", "seconds": float(step["seconds"])})
                continue
            if kind == "for":
                for _ in range(int(step["times"])):
                    walk(step.get("children") or [])
                continue
            source = "custom" if step.get("source") == "custom" else "builtin"
            action_id = str(step["id"])
            amount = _check_amount(action_id, source, float(step.get("amount") or 1))
            if source == "custom":
                frames = groups[action_id]["frames"]
                for _ in range(int(amount)):
                    planned.append({"kind": "arm", "name": groups[action_id]["name"], "frames": frames})
                continue
            mapped = BUILTIN_ACTIONS[action_id]
            if mapped is None:
                label = BUILTIN_LABELS[action_id]
                raise SkillError(f"真机不执行{label}。这个动作只留在仿真技能包里。")
            if action_id in ("turn_left", "turn_right"):
                planned.append({"kind": "catalog", "action": _turn_action(action_id, amount)})
                continue
            if action_id == "stand":
                planned.append({"kind": "catalog", "action": catalog.actions[mapped]})
                planned.extend(_hold_ready(amount))
                continue
            if action_id in ("walk_forward", "walk_back"):
                atom = catalog.actions[mapped]
                for _ in range(int(amount)):
                    planned.append({"kind": "catalog", "action": atom})
                continue
            atom = catalog.actions[mapped]
            repeats = int(amount) if _unit(action_id, "builtin") == "次" else 1
            for _ in range(repeats):
                planned.append({"kind": "catalog", "action": atom})

    walk(steps)
    return planned


def _stamp(steps: list) -> list:
    stamped = []
    for step in steps:
        kind = step.get("kind")
        if kind == "for":
            stamped.append({**step, "children": _stamp(step.get("children") or [])})
        elif kind == "if":
            stamped.append(
                {
                    **step,
                    "then": _stamp(step.get("then") or []),
                    "else": _stamp(step.get("else") or []),
                }
            )
        elif kind == "action":
            source = "custom" if step.get("source") == "custom" else "builtin"
            stamped.append({**step, "source": source, "unit": _unit(str(step.get("id")), source)})
        else:
            stamped.append(dict(step))
    return stamped


def _ids(steps: list, source: str) -> list[str]:
    found = []
    for step in steps:
        if step.get("kind") == "action" and (step.get("source") == "custom") == (source == "custom"):
            if step.get("source", "builtin") == source or (source == "builtin" and step.get("source") != "custom"):
                found.append(str(step["id"]))
        elif step.get("kind") == "for":
            found.extend(_ids(step.get("children") or [], source))
        elif step.get("kind") == "if":
            found.extend(_ids(step.get("then") or [], source))
            found.extend(_ids(step.get("else") or [], source))
    return found


def _py_call(step: Mapping) -> str:
    action_id = str(step["id"])
    amount = step.get("amount")
    if step.get("source") == "custom":
        return f'robot.play({json.dumps(action_id)}, times={int(amount)})'
    unit = _unit(action_id, "builtin")
    if unit == "步":
        return f"robot.{action_id}(steps={int(amount)})"
    if unit == "度":
        return f"robot.{action_id}(degrees={int(amount)})"
    if unit == "秒":
        return f"robot.{action_id}(hold={amount:g})"
    return f"robot.{action_id}(times={int(amount)})"


def _render_py(steps: list, indent: int = 1) -> list[str]:
    pad = "    " * indent
    lines = []
    for step in steps:
        if step.get("kind") == "wait":
            lines.append(f"{pad}robot.wait({float(step['seconds']):g})")
        elif step.get("kind") == "for":
            var_name = str(step.get("var") or step.get("varName") or "i")
            lines.append(f"{pad}for {var_name} in range({int(step['times'])}):")
            nested = _render_py(step.get("children") or [], indent + 1)
            lines.extend(nested or [f"{pad}    pass"])
        elif step.get("kind") == "if":
            lines.append(f"{pad}if robot.{step.get('cond') or 'condition'}():")
            lines.extend(_render_py(step.get("then") or [], indent + 1) or [f"{pad}    pass"])
            lines.append(f"{pad}else:")
            lines.extend(_render_py(step.get("else") or [], indent + 1) or [f"{pad}    pass"])
        elif step.get("kind") == "action":
            lines.append(f"{pad}{_py_call(step)}")
    return lines


def build_skill_zip(
    *,
    pack_id: str,
    title: str,
    description: str,
    workflow: list,
    groups: Mapping[str, dict],
    trigger: Mapping | None = None,
) -> bytes:
    validate_workflow(workflow, groups)
    if not str(pack_id).replace("_", "").isalnum():
        raise SkillError("技能包 id 只能含字母、数字和下划线。")
    stamped = _stamp(workflow)
    skill = {
        "schema_version": SKILLPACK_SCHEMA,
        "id": pack_id,
        "title": title.strip() or "未命名技能",
        "description": description.strip(),
        "model": "r1",
        "workflow": stamped,
        "estimated_duration_s": None,
    }
    if trigger:
        skill["trigger"] = trigger
    skill_bytes = (json.dumps(skill, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    used = []
    for action_id in _ids(stamped, "custom"):
        if action_id not in used:
            used.append(action_id)
    entries: list[tuple[str, bytes]] = [("skill.json", skill_bytes)]
    checksums = {"skill.json": hashlib.sha256(skill_bytes).hexdigest()}
    for action_id in used:
        name = f"actions/{action_id}.json"
        payload = (json.dumps(export_motion(groups[action_id]), ensure_ascii=False, indent=2) + "\n").encode()
        entries.append((name, payload))
        checksums[name] = hashlib.sha256(payload).hexdigest()
    builtin = []
    for action_id in _ids(stamped, "builtin"):
        if action_id not in builtin:
            builtin.append(action_id)
    manifest = {
        "schema_version": SKILLPACK_SCHEMA,
        "pack_id": pack_id,
        "title": skill["title"],
        "model": "r1",
        "angle_convention": ANGLE_CONVENTION,
        "hardware_authorized": False,
        "intended_runtime": "simulation",
        "blocks_used": builtin,
        "custom_actions": used,
        "checksums": checksums,
        "generator": {"platform": "r1-teacher-studio", "page": "skills"},
        "notes": "Simulation artifact. Angles follow the platform MJCF convention, not hardware encoder commands.",
    }
    py_lines = [
        "# 参考实现。robot 由运行方提供。平台不承诺真机语义。",
        f"# {SKILLPACK_SCHEMA}",
        "def run(robot):",
        *_render_py(stamped),
        "    pass" if not stamped else "",
    ]
    readme = (
        f"技能：{skill['title']}\n"
        f"格式：{SKILLPACK_SCHEMA}\n"
        "skill.json 是积木流程。actions/ 里是用到的自定义动作组，格式与人机联动导出 JSON 相同。\n"
        "hardware_authorized 为 false。真机播放前要换算肘关节，不能把文件直接当成编码器指令。\n"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries:
            archive.writestr(name, data)
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        archive.writestr("skill.py", "\n".join(line for line in py_lines if line != "") + "\n")
        archive.writestr("README.txt", readme)
    return buffer.getvalue()


def _numeric(args: str, key: str, default: float) -> float:
    for part in args.split(","):
        piece = part.strip()
        if not piece:
            continue
        if "=" in piece:
            name, value = piece.split("=", 1)
            if name.strip() != key:
                continue
            return float(value.strip())
        if key == "degrees":
            return float(piece)
    return default


def compile_python(source: str, catalog: Catalog) -> list[dict]:
    """把教学 Python 编成和技能运行相同的步骤。不调用学生录的动作组。"""
    planned: list[dict] = []
    for index, raw in enumerate(source.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if not line.startswith("robot.") or "(" not in line or not line.endswith(")"):
            raise SkillError(f"第 {index} 行：只支持 robot 的教学控制指令。")
        call = line[len("robot.") :]
        name, args = call[:-1].split("(", 1)
        if name == "stop":
            planned.append({"kind": "catalog", "action": catalog.actions["stop_move"]})
            break
        if name == "sit":
            raise SkillError(f"第 {index} 行：真机不执行坐下。")
        if name == "move":
            vx = max(-0.5, min(0.5, _numeric(args, "vx", 0.0)))
            seconds = _numeric(args, "seconds", 1.0)
            vy = _numeric(args, "vy", 0.0)
            if abs(vy) > 1e-3:
                raise SkillError(f"第 {index} 行：真机教学指令不支持横移 vy。")
            if seconds <= 0 or seconds > 10:
                raise SkillError(f"第 {index} 行：seconds 需在 0 到 10 秒之间。")
            if abs(vx) > 1e-3:
                title = "缓慢向前移动" if vx > 0 else "缓慢向后移动"
                planned.append(
                    {
                        "kind": "catalog",
                        "action": Action(
                            name="move_python",
                            title=title,
                            kind="move",
                            args={"vx": vx, "vy": 0.0, "omega": 0.0, "duration": seconds},
                        ),
                    }
                )
            continue
        if name == "turn":
            degrees = _numeric(args, "degrees", 0.0)
            if not degrees:
                raise SkillError(f"第 {index} 行：turn 需要 degrees 参数。")
            action_id = "turn_left" if degrees > 0 else "turn_right"
            planned.append({"kind": "catalog", "action": _turn_action(action_id, abs(degrees))})
            continue
        mapping = {
            "stand": "ready_pose",
            "wave": "wave_right",
            "raise_hand": "raise_hand_right",
            "salute": "salute_right",
            "nod": "nod",
        }
        if name not in mapping:
            raise SkillError(f"第 {index} 行：只支持 robot 的教学控制指令。")
        times = 1
        if name in ("wave", "nod"):
            times = int(round(_numeric(args, "times", 1)))
            times = max(1, min(5, times))
        atom = catalog.actions[mapping[name]]
        for _ in range(times):
            planned.append({"kind": "catalog", "action": atom})
    if not planned:
        raise SkillError("没有可执行指令。")
    return planned


def groups_by_id(groups: list[dict]) -> dict[str, dict]:
    return {group["id"]: group for group in groups}


def ensure_motion(group: Mapping) -> dict:
    try:
        return export_motion(group)
    except MotionError as error:
        raise SkillError(str(error)) from error
