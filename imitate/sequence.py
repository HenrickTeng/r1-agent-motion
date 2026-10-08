"""在已有 MuJoCo 上肢仿真里编排课堂动作序列（dds_robot.MOTIONS），不连真机。"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

from imitate.joints import ARM_JOINTS
from r1_agent.catalog import ROOT, load_catalog
from r1_agent.dds_robot import MOTIONS, READY_POSE_DEG
from r1_studio.programs import ProgramError, save_groups_file, validate_group_name


def pose_from_abs13(target_deg: tuple[float, ...]) -> dict[str, float]:
    if len(target_deg) < 10:
        raise ValueError("need 10 arm degrees")
    return {name: math.radians(float(target_deg[i])) for i, name in enumerate(ARM_JOINTS)}


def ready_arm_pose() -> dict[str, float]:
    return {name: math.radians(float(READY_POSE_DEG[i])) for i, name in enumerate(ARM_JOINTS)}


def lerp_pose(start: dict[str, float], end: dict[str, float], x: float) -> dict[str, float]:
    x = max(0.0, min(1.0, x))
    return {name: start[name] + (end[name] - start[name]) * x for name in ARM_JOINTS}


def iter_motion_poses(name: str, *, dt: float = 0.04):
    steps = MOTIONS.get(name)
    if not steps:
        raise KeyError(name)
    previous = ready_arm_pose()
    yield previous
    for duration, target_deg, hold in steps:
        target = pose_from_abs13(target_deg)
        elapsed = 0.0
        duration = max(duration, 0.05)
        while elapsed < duration:
            yield lerp_pose(previous, target, elapsed / duration)
            elapsed += dt
        yield target
        held = 0.0
        while held < hold:
            yield target
            held += dt
        previous = target
    back = ready_arm_pose()
    elapsed = 0.0
    while elapsed < 1.2:
        yield lerp_pose(previous, back, elapsed / 1.2)
        elapsed += dt
    yield back


def parse_sequence(text: str) -> list[str]:
    names = [part.strip() for part in text.replace("，", ",").split(",") if part.strip()]
    catalog = load_catalog()
    unknown = [name for name in names if name not in MOTIONS]
    if unknown:
        raise ProgramError(f"仿真序列只能用上肢原子动作，未知：{unknown}")
    for name in names:
        if catalog.actions[name].kind != "arm":
            raise ProgramError(f"{name} 不是上肢动作")
    return names


def apply_pose(sim, pose: dict[str, float]) -> None:
    from imitate.limits import ElectronicLimits

    limiter = getattr(sim, "_seq_limiter", None)
    if limiter is None:
        limiter = ElectronicLimits(sim)
        sim._seq_limiter = limiter
    limited, _sample, _blocked = limiter.apply(pose)
    sim.set_pose(limited)


def play_sequence(sim, names: list[str], *, dt: float = 0.04, viewer=None) -> None:
    print(f"播放序列: {' → '.join(names)}", flush=True)
    for name in names:
        print(f"  动作 {name}", flush=True)
        for pose in iter_motion_poses(name, dt=dt):
            apply_pose(sim, pose)
            if viewer is not None:
                if not viewer.is_running():
                    return
                viewer.sync()
            time.sleep(dt)


def _save_group(name: str, steps: list[str], path: Path) -> Path:
    catalog = load_catalog()
    name = validate_group_name(name, catalog)
    existing = {}
    if path.exists():
        from r1_studio.programs import load_groups_file

        existing = load_groups_file(path)
    existing[name] = list(steps)
    save_groups_file(path, existing)
    return path


def run_edit_sequence(*, full_model: bool = True, play: str = "", save_as: str = "", headless: bool = False) -> int:
    names = sorted(MOTIONS)
    sequence: list[str] = parse_sequence(play) if play else []
    index = names.index(sequence[0]) if sequence else names.index("wave_right") if "wave_right" in names else 0
    if save_as:
        if not sequence:
            raise ProgramError("--save-as 需要同时给 --play-sequence")
        path = _save_group(save_as, sequence, ROOT / "programs" / "custom_groups.json")
        print(json.dumps({"saved": save_as, "steps": sequence, "path": str(path)}, ensure_ascii=False), flush=True)
    if headless:
        for name in sequence or [names[index]]:
            n = sum(1 for _ in iter_motion_poses(name))
            print(json.dumps({"played": name, "frames": n}, ensure_ascii=False), flush=True)
        return 0

    from imitate.sim import ArmSim

    sim = ArmSim(preview_only=not full_model)
    apply_pose(sim, ready_arm_pose())
    print("课堂动作序列编辑（MuJoCo 仿真，不连真机）", flush=True)
    print("  [ ] 上一个/下一个原子   空格加入序列   退格删最后一个", flush=True)
    print("  P 播放   C 清空   S 保存到 programs/custom_groups.json   Q 退出", flush=True)
    print("  当前原子:", names[index], "  序列:", sequence or "（空）", flush=True)

    try:
        import cv2
        import mujoco.viewer
        import numpy as np
    except ImportError as error:
        if sequence:
            for name in sequence:
                list(iter_motion_poses(name))
            print("无显示环境，已在内存里走完序列。", flush=True)
            return 0
        raise SystemExit("需要 opencv-python 和 mujoco") from error

    canvas = np.zeros((280, 720, 3), dtype=np.uint8)

    def redraw() -> None:
        canvas[:] = (32, 28, 48)
        lines = [
            f"atom [{index+1}/{len(names)}] {names[index]}",
            "seq: " + (" > ".join(sequence) if sequence else "(empty)"),
            "[ ] space backspace | P play | C clear | S save | Q quit",
        ]
        for row, text in enumerate(lines):
            cv2.putText(canvas, text[:80], (16, 50 + row * 40), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (230, 230, 230), 1)
        cv2.imshow("R1 sequence editor", canvas)

    with mujoco.viewer.launch_passive(sim.model, sim.data) as viewer:
        viewer.cam.lookat[:] = (0.05, 0.0, 1.05)
        viewer.cam.distance = 2.2
        viewer.cam.azimuth = 140
        viewer.cam.elevation = -15
        if sequence:
            play_sequence(sim, sequence, viewer=viewer)
        apply_pose(sim, pose_from_abs13(MOTIONS[names[index]][-1][1]))
        viewer.sync()
        while viewer.is_running():
            redraw()
            key = cv2.waitKey(20) & 0xFF
            viewer.sync()
            if key in (ord("q"), 27):
                break
            if key in (ord("]"), 83, ord("n")):  # ] or right
                index = (index + 1) % len(names)
                apply_pose(sim, pose_from_abs13(MOTIONS[names[index]][-1][1]))
                print(json.dumps({"atom": names[index]}, ensure_ascii=False), flush=True)
            elif key in (ord("["), 81, ord("b")):
                index = (index - 1) % len(names)
                apply_pose(sim, pose_from_abs13(MOTIONS[names[index]][-1][1]))
                print(json.dumps({"atom": names[index]}, ensure_ascii=False), flush=True)
            elif key == ord(" "):
                sequence.append(names[index])
                print(json.dumps({"sequence": sequence}, ensure_ascii=False), flush=True)
            elif key in (8, 127):
                if sequence:
                    sequence.pop()
                    print(json.dumps({"sequence": sequence}, ensure_ascii=False), flush=True)
            elif key in (ord("c"), ord("C")):
                sequence.clear()
                print('{"sequence":[]}', flush=True)
            elif key in (ord("p"), ord("P")):
                if sequence:
                    play_sequence(sim, sequence, viewer=viewer)
                else:
                    play_sequence(sim, [names[index]], viewer=viewer)
            elif key in (ord("s"), ord("S")):
                if not sequence:
                    print("序列是空的，先空格加入动作", flush=True)
                    continue
                print("在终端输入动作组名字后回车（直接回车=sim_seq）：", flush=True)
                try:
                    raw = input().strip() or "sim_seq"
                except EOFError:
                    raw = "sim_seq"
                try:
                    path = _save_group(raw, sequence, ROOT / "programs" / "custom_groups.json")
                    print(json.dumps({"saved": raw, "steps": sequence, "path": str(path)}, ensure_ascii=False), flush=True)
                except ProgramError as error:
                    print(json.dumps({"error": str(error)}, ensure_ascii=False), flush=True)
    cv2.destroyAllWindows()
    return 0
