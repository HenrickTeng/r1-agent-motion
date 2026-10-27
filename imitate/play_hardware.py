"""真机播一个校准上肢姿势。走跑 + arm_sdk，不连续播六个，不行走。"""

from __future__ import annotations

import math
import time

from imitate.calibrate import CALIB_POSES
from imitate.joints import ARM_JOINTS
from imitate.laterality import POSE_ALIASES
from imitate.retarget import TEACHER_POSE_DEG
from r1_agent.dds_robot import READY_POSE_DEG, DdsRobot
from r1_agent.elbow_map import pose13_elbows_human_to_hw


def _teacher_to_13_rad(name: str) -> list[float]:
    pose10 = TEACHER_POSE_DEG[name]
    out = [math.radians(deg) for deg in READY_POSE_DEG]
    for index, joint in enumerate(ARM_JOINTS):
        out[index] = math.radians(float(pose10[joint]))
    return pose13_elbows_human_to_hw(out)


def run_play_calib(*, pose: str, interface: str = "auto", move_s: float = 5.0, hold_s: float = 2.5) -> None:
    pose = POSE_ALIASES.get(pose, pose)
    names = list(CALIB_POSES) if pose in ("all", "*") else [pose]
    if pose not in ("all", "*") and pose not in CALIB_POSES:
        raise RuntimeError(f"未知姿势 {pose}。可选：{', '.join(CALIB_POSES)} 或 all")
    print(f"走跑 + arm_sdk 播放：{', '.join(names)}。不行走、不进调试。物理急停请握在手里。")
    robot = DdsRobot(interface)
    print(f"网卡 {robot._interface}")
    robot.require_walk_run()
    ready = [math.radians(deg) for deg in READY_POSE_DEG]
    previous = ready
    try:
        print("回待机")
        robot.goto_ready(4.0)
        for name in names:
            target = _teacher_to_13_rad(name)
            print(f"去 {name}  指令肘 LE={math.degrees(target[3]):.1f}° RE={math.degrees(target[8]):.1f}°")
            robot._move_pose(previous, target, move_s)
            t_hold = time.time()
            last_print = 0.0
            while time.time() - t_hold < hold_s:
                robot._publish(target, 1.0)
                robot._check()
                elapsed = time.time() - t_hold
                if elapsed - last_print >= 0.5:
                    q = robot._pose()
                    print(
                        f"  保持 {elapsed:4.1f}s  指令肘 L{math.degrees(target[3]):.1f} R{math.degrees(target[8]):.1f}  "
                        f"实测J4/J9 L{math.degrees(q[3]):.1f} R{math.degrees(q[8]):.1f}"
                    )
                    last_print = elapsed
                time.sleep(0.01)
            previous = target
        print("回待机并交还 arm_sdk")
        robot._move_pose(previous, ready, move_s)
        robot._release()
    except Exception:
        try:
            robot._release()
        except Exception:
            pass
        raise
    print("完成。")
