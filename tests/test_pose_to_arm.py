"""MediaPipe 3D → R1 上肢关节：合成骨架符号检查。"""

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from imitate.pose_to_arm import landmarks_to_arm_rad, synthetic_pose


def test_tpose_rolls_are_outward() -> None:
    pose = landmarks_to_arm_rad(synthetic_pose("tpose"))
    assert math.degrees(pose["left_shoulder_roll"]) > 40
    assert math.degrees(pose["right_shoulder_roll"]) < -40


def test_forward_pitch_is_negative() -> None:
    pose = landmarks_to_arm_rad(synthetic_pose("forward"))
    assert math.degrees(pose["left_shoulder_pitch"]) < -40
    assert math.degrees(pose["right_shoulder_pitch"]) < -40


def test_raise_right_is_higher_than_down() -> None:
    down = landmarks_to_arm_rad(synthetic_pose("down"))
    up = landmarks_to_arm_rad(synthetic_pose("raise_right"))
    assert up["right_shoulder_pitch"] < down["right_shoulder_pitch"] - 0.4


def test_salute_bends_right_elbow() -> None:
    salute = landmarks_to_arm_rad(synthetic_pose("salute_right"))
    raise_r = landmarks_to_arm_rad(synthetic_pose("raise_right"))
    assert salute["right_elbow"] > raise_r["right_elbow"] + 0.3


def test_down_near_hanging() -> None:
    pose = landmarks_to_arm_rad(synthetic_pose("down"))
    assert abs(math.degrees(pose["left_shoulder_pitch"])) < 25
    assert abs(math.degrees(pose["right_shoulder_pitch"])) < 25


def test_hanging_forearm_outward_yaw_matches_mjcf() -> None:
    """垂臂屈肘、前臂向外：J3 与 MJCF yaw 轴 +Z 同号（左正右负）。"""
    from imitate.pose_to_arm import (
        L_EL,
        L_HIP,
        L_INDEX,
        L_PINKY,
        L_SH,
        L_WR,
        R_EL,
        R_HIP,
        R_INDEX,
        R_PINKY,
        R_SH,
        R_WR,
        empty_landmarks,
    )

    points = empty_landmarks()
    points[L_HIP] = (-0.10, 0.00, 0.00)
    points[R_HIP] = (0.10, 0.00, 0.00)
    points[L_SH] = (-0.18, 0.42, 0.00)
    points[R_SH] = (0.18, 0.42, 0.00)
    points[L_EL] = (-0.18, 0.18, 0.00)
    points[R_EL] = (0.18, 0.18, 0.00)
    points[L_WR] = (-0.42, 0.18, 0.00)
    points[R_WR] = (0.42, 0.18, 0.00)
    points[L_PINKY] = points[L_WR]
    points[L_INDEX] = points[L_WR]
    points[R_PINKY] = points[R_WR]
    points[R_INDEX] = points[R_WR]
    pose = landmarks_to_arm_rad(points)
    assert math.degrees(pose["left_shoulder_yaw"]) > 60
    assert math.degrees(pose["right_shoulder_yaw"]) < -60


def test_forward_arm_yaw_follows_mjcf_joint() -> None:
    """前伸后再拧大臂：J3 必须跟 MuJoCo yaw 同号，不能再用世界前方当零位。"""
    from imitate.sim import ArmSim
    from imitate.joints import ARM_JOINTS

    sim = ArmSim(preview_only=True)

    def set_deg(**values: float) -> None:
        pose = {name: 0.0 for name in ARM_JOINTS}
        for name, deg in values.items():
            pose[name] = math.radians(deg)
        sim.set_pose(pose)

    def r1_to_mp(point) -> tuple[float, float, float]:
        x, y, z = (float(point[0]), float(point[1]), float(point[2]))
        return (-y, z, -x)

    def body(name: str):
        return sim.data.xpos[sim.model.body(name).id].copy()

    from imitate.pose_to_arm import (
        L_EL,
        L_HIP,
        L_INDEX,
        L_PINKY,
        L_SH,
        L_WR,
        R_EL,
        R_HIP,
        R_INDEX,
        R_PINKY,
        R_SH,
        R_WR,
        empty_landmarks,
    )

    set_deg(left_shoulder_pitch=-90, left_elbow=70, left_shoulder_yaw=40)
    points = empty_landmarks()
    torso = body("torso")
    points[L_HIP] = r1_to_mp(torso + [0.0, 0.10, -0.35])
    points[R_HIP] = r1_to_mp(torso + [0.0, -0.10, -0.35])
    points[L_SH] = r1_to_mp(body("left_shoulder_pitch_link"))
    points[R_SH] = r1_to_mp(body("right_shoulder_pitch_link"))
    points[L_EL] = r1_to_mp(body("left_elbow_link"))
    points[R_EL] = r1_to_mp(body("right_elbow_link"))
    points[L_WR] = r1_to_mp(body("left_wrist_roll_link"))
    points[R_WR] = r1_to_mp(body("right_wrist_roll_link"))
    points[L_PINKY] = points[L_WR]
    points[L_INDEX] = points[L_WR]
    points[R_PINKY] = points[R_WR]
    points[R_INDEX] = points[R_WR]
    pose = landmarks_to_arm_rad(points)
    assert abs(math.degrees(pose["left_shoulder_yaw"]) - 40) < 8


def test_mediapipe_world_adapter() -> None:
    from types import SimpleNamespace
    from imitate.pose_to_arm import mediapipe_world_to_array

    raw = synthetic_pose("tpose")
    fake = SimpleNamespace(landmark=[SimpleNamespace(x=p[0], y=p[1], z=p[2]) for p in raw])
    array = mediapipe_world_to_array(fake)
    pose = landmarks_to_arm_rad(array)
    assert math.degrees(pose["left_shoulder_roll"]) > 40
