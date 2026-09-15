"""动作 JSON 组装、无摄像头自检、可选 MediaPipe 摄像头关键帧采集。"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Mapping

from imitate.collision import scan_action, scan_pose
from imitate.limits import ElectronicLimits
from imitate.joints import (
    ARM_JOINTS,
    READY_POSE_DEG,
    offsets_deg_from_abs,
    pose_rad_to_abs_deg,
)
from imitate.laterality import LATERALITY, MIRROR_LIBRARY


def build_action(
    name: str,
    title: str,
    poses_rad: list[Mapping[str, float]],
    *,
    dt: float = 1.0,
    aliases: list[str] | None = None,
) -> dict:
    keyframes = []
    for index, pose in enumerate(poses_rad):
        abs_deg = {joint: round(deg, 2) for joint, deg in pose_rad_to_abs_deg(pose).items()}
        keyframes.append(
            {
                "time_s": round(index * dt, 3),
                "abs_deg": abs_deg,
                "offsets_deg": {k: round(v, 2) for k, v in offsets_deg_from_abs(abs_deg).items()},
            }
        )
    return {
        "schema_version": "r1-arm-imitate-mirror/v1",
        "laterality": LATERALITY,
        "action_name": name,
        "title": title,
        "aliases": aliases or [title],
        "kind": "arm",
        "units": "degrees",
        "hardware_authorized": False,
        "base_pose_deg": dict(READY_POSE_DEG),
        "keyframes": keyframes,
        "not_agent_catalog": (
            "自拍镜像：人的右=机器人左。不要把本文件写进 actions.json / dds_robot.MOTIONS。"
        ),
    }


def save_action(payload: dict, path: Path | None = None) -> Path:
    MIRROR_LIBRARY.mkdir(parents=True, exist_ok=True)
    dest = path or (MIRROR_LIBRARY / f"{payload['action_name']}.json")
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return dest


def attach_collision(payload: dict, sim: ArmSim) -> dict:
    """关键帧轨迹必须做碰撞扫描。未通过只预警，不授权真机。"""
    report = scan_action(sim, payload["keyframes"])
    payload["collision"] = {
        "passed": report["passed"],
        "worst_status": report["worst_status"],
        "worst_minimum_distance_m": report["worst_minimum_distance_m"],
        "worst_closest_pair": report["worst_closest_pair"],
        "hardware_authorized": False,
    }
    status = report["worst_status"]
    dist_mm = report["worst_minimum_distance_m"] * 1000.0
    if report["passed"]:
        print(f"  碰撞: SAFE  最小间距 {dist_mm:.0f} mm")
    else:
        print(f"  碰撞未通过: {status}  最小间距 {dist_mm:.0f} mm  最近 {report['worst_closest_pair']}")
        print("  此动作不能上真机（hardware_authorized=false）")
    return report


def _fmt_pose(pose: Mapping[str, float]) -> str:
    parts = []
    for side, prefix in (("L", "left_"), ("R", "right_")):
        pitch = math.degrees(pose[f"{prefix}shoulder_pitch"])
        roll = math.degrees(pose[f"{prefix}shoulder_roll"])
        yaw = math.degrees(pose[f"{prefix}shoulder_yaw"])
        elbow = math.degrees(pose[f"{prefix}elbow"])
        wrist = math.degrees(pose[f"{prefix}wrist_roll"])
        parts.append(f"{side} P{pitch:+5.0f} R{roll:+5.0f} Y{yaw:+5.0f} E{elbow:5.0f} W{wrist:+5.0f}")
    return "  ".join(parts)


def run_self_test() -> int:
    sim = ArmSim(preview_only=True)
    print("模型:", sim.model_path)
    print("合成姿态 → 关节角（度）")
    poses = {name: landmarks_to_arm_rad(synthetic_pose(name)) for name in SYNTHETIC_POSES}
    for name, pose in poses.items():
        sample = scan_pose(sim, pose)
        print(f"  {name:<14} {_fmt_pose(pose)}  {sample.status}  {sample.minimum_distance_m*1000:.0f}mm")

    down, tpose, forward, salute, raise_r = (
        poses["down"],
        poses["tpose"],
        poses["forward"],
        poses["salute_right"],
        poses["raise_right"],
    )
    checks: list[tuple[str, bool, str]] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        checks.append((label, ok, detail))
        print(("  OK  " if ok else "  FAIL") + f" {label}" + (f"  ({detail})" if detail else ""))

    check("垂臂 pitch 接近 0", abs(math.degrees(down["left_shoulder_pitch"])) < 25, f"{math.degrees(down['left_shoulder_pitch']):.1f}")
    check("T pose 左 roll > 40°", math.degrees(tpose["left_shoulder_roll"]) > 40, f"{math.degrees(tpose['left_shoulder_roll']):.1f}")
    check("T pose 右 roll < -40°", math.degrees(tpose["right_shoulder_roll"]) < -40, f"{math.degrees(tpose['right_shoulder_roll']):.1f}")
    check("前伸 pitch < -40°", math.degrees(forward["left_shoulder_pitch"]) < -40, f"{math.degrees(forward['left_shoulder_pitch']):.1f}")
    check("举手右肘较直", math.degrees(raise_r["right_elbow"]) < 40, f"{math.degrees(raise_r['right_elbow']):.1f}")
    check("敬礼右肘更弯", math.degrees(salute["right_elbow"]) > math.degrees(raise_r["right_elbow"]) + 20,
          f"salute {math.degrees(salute['right_elbow']):.0f} vs raise {math.degrees(raise_r['right_elbow']):.0f}")

    tpose_scan = scan_pose(sim, tpose)
    check("T pose 碰撞 SAFE", tpose_scan.status == "SAFE", tpose_scan.status)

    inward = {name: 0.0 for name in tpose}
    inward.update({
        "left_shoulder_roll": -0.22,
        "right_shoulder_roll": 0.22,
        "left_elbow": 2.0,
        "right_elbow": 2.0,
        "left_shoulder_pitch": -0.8,
        "right_shoulder_pitch": -0.8,
    })
    inward_scan = scan_pose(sim, inward)
    check("双臂内收更近/预警", inward_scan.status != "SAFE" and inward_scan.minimum_distance_m < tpose_scan.minimum_distance_m,
          f"{inward_scan.status} {inward_scan.minimum_distance_m*1000:.0f}mm")

    limiter = ElectronicLimits(sim)
    limiter.apply(tpose)
    limited, raw_sample, blocked = limiter.apply(inward)
    limited_scan = scan_pose(sim, limited)
    check("电子限位挡住内收", blocked and limited_scan.status == "SAFE" and raw_sample.status != "SAFE",
          f"blocked={blocked} out={limited_scan.status} raw={raw_sample.status}")

    action = build_action("demo_wave", "演示挥手", [down, raise_r, salute, down], dt=0.8)
    report = attach_collision(action, sim)
    path = save_action(action, MIRROR_LIBRARY / "demo_wave.json")
    check("导出 JSON", path.is_file(), str(path))
    check("轨迹已做碰撞扫描", report["worst_status"] in {"SAFE", "WARNING", "DANGER", "COLLISION"}, report["worst_status"])
    check("hardware_authorized=false", action["collision"]["hardware_authorized"] is False)

    failed = [item for item in checks if not item[1]]
    print()
    print(f"自检 {len(checks) - len(failed)}/{len(checks)} 通过")
    return 1 if failed else 0


def run_demo_keys() -> None:
    try:
        import cv2
    except ImportError as error:
        raise SystemExit("需要 opencv-python") from error

    sim = ArmSim(preview_only=True)
    limiter = ElectronicLimits(sim)
    names = list(SYNTHETIC_POSES)
    index = 0
    frames: list[dict] = []
    canvas = None
    print("键: 1-6 切姿态  空格关键帧  S 保存  Q 退出（无摄像头 demo）")
    while True:
        name = names[index]
        pose, sample, limited = limiter.apply(landmarks_to_arm_rad(synthetic_pose(name)))
        canvas = (canvas if canvas is not None else __import__("numpy").zeros((360, 720, 3), dtype=__import__("numpy").uint8))
        canvas[:] = (32, 32, 36)
        lines = [
            f"pose: {name}",
            _fmt_pose(pose),
            f"collision: {'LIMIT '+sample.status if limited else sample.status}  {sample.minimum_distance_m*1000:.0f}mm",
            f"keyframes: {len(frames)}",
            "1-6 pose | SPACE capture | S save | Q quit",
        ]
        for row, text in enumerate(lines):
            cv2.putText(canvas, text, (20, 50 + row * 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (220, 220, 220), 2)
        cv2.imshow("R1 imitate demo", canvas)
        key = cv2.waitKey(30) & 0xFF
        if key in (ord("q"), 27):
            break
        if ord("1") <= key <= ord("6"):
            index = min(key - ord("1"), len(names) - 1)
        elif key == ord(" "):
            frames.append(dict(pose))
            print(f"  keyframe {len(frames)} <- {name}")
        elif key in (ord("s"), ord("S")):
            if not frames:
                print("  没有关键帧")
                continue
            payload = build_action("student_demo", "学生演示动作", frames)
            attach_collision(payload, sim)
            path = save_action(payload)
            print(f"  已保存 {path}")
    cv2.destroyAllWindows()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="R1 上肢动作模仿：仿真或走跑 arm_sdk 真机跟臂")
    parser.add_argument("--self-test", action="store_true", help="无摄像头自检")
    parser.add_argument("--view", action="store_true", help="打开 MuJoCo 窗口循环播放合成姿态")
    parser.add_argument("--demo", action="store_true", help="合成姿态键盘 demo")
    parser.add_argument("--camera", type=int, default=-1, help="笔记本摄像头编号；默认 -1 表示无摄像头自检")
    parser.add_argument(
        "--edit-sequence",
        action="store_true",
        help="MuJoCo 里编排课堂动作序列（空格加入、P 播放、S 保存动作组）",
    )
    parser.add_argument(
        "--play-sequence",
        default="",
        help="要播放或作为编辑起点的上肢动作名，逗号分隔，如 wave_right,cheer_both",
    )
    parser.add_argument("--save-as", default="", help="配合 --play-sequence 直接保存自定义动作组名字")
    parser.add_argument(
        "--r1-camera",
        action="store_true",
        help="用 R1 头部图传（Go2 VideoClient JPEG），不要笔记本摄像头",
    )
    parser.add_argument("--no-mujoco", action="store_true", help="只开摄像头窗口，不跟 MuJoCo")
    parser.add_argument("--no-mirror", action="store_true", help="不镜像画面")
    parser.add_argument("--no-capture", action="store_true", help="只跟臂，不采集关键帧（录视频用）")
    parser.add_argument("--coach", action="store_true", help="模型先演示，再模仿；每动作采 3 帧")
    parser.add_argument(
        "--calibrate",
        action="store_true",
        help="标准校准：R1 每个姿势示范 15 秒，只跟画面；换摄像头或换人时重做",
    )
    parser.add_argument("--full-model", action="store_true", help="加载官方 R1 网格模型（不是胶囊预览）")
    parser.add_argument("--hardware", action="store_true", help="经 ubuntu-safe-context-demo 同款 DDS 上真机（限速+软急停）")
    parser.add_argument("--interface", default="auto", help="机器人网卡；默认 auto")
    parser.add_argument("--goto-ready", action="store_true", help="真机只慢速回到走跑待机，不跟摄像头")
    parser.add_argument(
        "--play-calib",
        action="store_true",
        help="真机慢速播一个校准上肢姿势（须加 --pose，不连续播六个）",
    )
    parser.add_argument(
        "--pose",
        default="",
        help="校准姿势名：down tpose forward hands_chest raise_user_right salute_user_right",
    )
    parser.add_argument("--hold", type=float, default=2.5, help="每个姿势到位后保持秒数")
    parser.add_argument(
        "--read-lowstate",
        action="store_true",
        help="只订阅 rt/lowstate 打印关节角；走跑模式即可，不进调试、不发 arm_sdk",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return run_self_test()
    if args.view:
        from imitate.view import run_view
        run_view(full_model=args.full_model)
        return 0
    if args.demo:
        run_demo_keys()
        return 0
    if args.edit_sequence or args.play_sequence:
        from imitate.sequence import run_edit_sequence

        return run_edit_sequence(
            full_model=args.full_model,
            play=args.play_sequence,
            save_as=args.save_as,
            headless=args.no_mujoco,
        )
    if args.read_lowstate:
        from imitate.read_lowstate import run_read_lowstate

        return run_read_lowstate(interface=args.interface)
    if args.play_calib:
        if not args.hardware:
            parser.error("--play-calib 需要同时加 --hardware")
        if not args.pose:
            parser.error("--play-calib 请加 --pose 名字，或 --pose all 按仿真顺序播六个")
        from imitate.play_hardware import run_play_calib

        run_play_calib(pose=args.pose, interface=args.interface, hold_s=args.hold)
        return 0
    if args.goto_ready:
        if not args.hardware:
            parser.error("--goto-ready 需要同时加 --hardware")
        from r1_agent.dds_robot import DdsRobot

        robot = DdsRobot(args.interface)
        robot.require_walk_run()
        print(f"网卡 {robot._interface}，fsm 811，慢速回待机。物理急停在手。回车退出。")
        robot.goto_ready(4.0)
        try:
            input()
        except EOFError:
            time.sleep(2)
        robot._release()
        return 0
    from imitate.camera import run_camera, run_coach
    if args.calibrate:
        if args.hardware:
            parser.error("校准不要开 --hardware")
        run_coach(
            0 if args.camera < 0 else args.camera,
            mirror=not args.no_mirror,
            full_model=args.full_model,
            calibrate=True,
        )
        return 0
    if args.coach:
        run_coach(0 if args.camera < 0 else args.camera, mirror=not args.no_mirror, full_model=args.full_model)
        return 0
    if args.r1_camera:
        run_camera(
            0,
            mirror=not args.no_mirror,
            mujoco_view=not args.no_mujoco,
            capture=not args.no_capture,
            full_model=args.full_model,
            hardware=args.hardware,
            interface=args.interface,
            r1_stream=True,
        )
        return 0
    if args.camera < 0:
        return run_self_test()
    run_camera(
        args.camera,
        mirror=not args.no_mirror,
        mujoco_view=not args.no_mujoco,
        capture=not args.no_capture,
        full_model=args.full_model,
        hardware=args.hardware,
        interface=args.interface,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
