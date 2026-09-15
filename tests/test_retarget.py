"""IK 对齐真机待机零位。"""

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from imitate.joints import READY_POSE_DEG
from imitate.pose_to_arm import landmarks_to_arm_rad, synthetic_pose
from imitate.retarget import (
    elbows_human_to_official,
    retarget_to_ready,
    standing_ik_rad,
    swap_lr_facing,
    teacher_pose_rad,
)


def test_standing_maps_near_ready() -> None:
    standing = standing_ik_rad()
    out = retarget_to_ready(standing)
    for name, deg in READY_POSE_DEG.items():
        assert abs(math.degrees(out[name]) - deg) < 0.5, name


def test_tpose_roll_stays_within_limits() -> None:
    pose = retarget_to_ready(landmarks_to_arm_rad(synthetic_pose("tpose")))
    assert math.degrees(pose["left_shoulder_roll"]) > 40
    assert math.degrees(pose["right_shoulder_roll"]) < -40


def test_facing_swap_moves_right_raise_to_left() -> None:
    raw = landmarks_to_arm_rad(synthetic_pose("raise_right"))
    swapped = swap_lr_facing(raw)
    assert swapped["left_shoulder_pitch"] < raw["left_shoulder_pitch"] - 0.5


def test_teacher_tpose_and_forward_are_straight() -> None:
    tpose = teacher_pose_rad("tpose")
    forward = teacher_pose_rad("forward")
    assert 25 < math.degrees(tpose["left_elbow"]) < 40
    assert math.degrees(tpose["left_shoulder_roll"]) > 70
    assert math.degrees(forward["left_shoulder_pitch"]) < -80
    assert 25 < math.degrees(forward["left_elbow"]) < 40


def test_official_elbow_maps_straight_near_76() -> None:
    pose = {name: 0.0 for name in READY_POSE_DEG}
    pose["left_elbow"] = 0.0
    pose["right_elbow"] = 0.0
    out = elbows_human_to_official(pose)
    assert abs(math.degrees(out["left_elbow"]) - 76.0) < 1.0
    ready = {name: math.radians(deg) for name, deg in READY_POSE_DEG.items()}
    mapped = elbows_human_to_official(ready)
    assert abs(math.degrees(mapped["left_elbow"]) - READY_POSE_DEG["left_elbow"]) < 0.5
