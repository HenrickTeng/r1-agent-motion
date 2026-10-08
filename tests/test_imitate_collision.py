"""简化臂模型碰撞扫描：T-pose 安全，人为穿胸不安全。"""

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from imitate.capture import build_action
from imitate.collision import scan_action, scan_pose
from imitate.joints import ARM_JOINTS
from imitate.pose_to_arm import landmarks_to_arm_rad, synthetic_pose
from imitate.sim import ArmSim


def test_tpose_is_safe() -> None:
    sim = ArmSim(preview_only=True)
    pose = landmarks_to_arm_rad(synthetic_pose("tpose"))
    sample = scan_pose(sim, pose)
    assert sample.status == "SAFE", sample


def test_arms_inward_is_closer_than_tpose() -> None:
    sim = ArmSim(preview_only=True)
    tpose = scan_pose(sim, landmarks_to_arm_rad(synthetic_pose("tpose")))
    inward = {name: 0.0 for name in ARM_JOINTS}
    inward["left_shoulder_roll"] = -0.22
    inward["right_shoulder_roll"] = 0.22
    inward["left_elbow"] = 2.0
    inward["right_elbow"] = 2.0
    inward["left_shoulder_pitch"] = -0.8
    inward["right_shoulder_pitch"] = -0.8
    sample = scan_pose(sim, inward)
    assert sample.minimum_distance_m < tpose.minimum_distance_m
    assert sample.status in {"WARNING", "DANGER", "COLLISION"}


def test_action_export_and_scan_fields() -> None:
    sim = ArmSim(preview_only=True)
    down = landmarks_to_arm_rad(synthetic_pose("down"))
    up = landmarks_to_arm_rad(synthetic_pose("raise_right"))
    payload = build_action("unit_wave", "单测挥手", [down, up, down], dt=0.5)
    assert payload["units"] == "degrees"
    assert payload["hardware_authorized"] is False
    assert payload["laterality"] == "selfie_mirror_user_right_is_robot_left"
    assert "coeffs" not in payload["keyframes"][0]
    assert payload["keyframes"][0]["abs_deg"]
    report = scan_action(sim, payload["keyframes"], sample_hz=20)
    assert report["hardware_authorized"] is False
    assert report["worst_status"] in {"SAFE", "WARNING", "DANGER", "COLLISION"}
    assert math.isfinite(report["worst_minimum_distance_m"])
