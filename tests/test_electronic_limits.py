"""电子限位：危险方向走到包络就卡住，输出仍为 SAFE。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from imitate.collision import scan_pose
from imitate.joints import ARM_JOINTS
from imitate.limits import ElectronicLimits
from imitate.pose_to_arm import landmarks_to_arm_rad, synthetic_pose
from imitate.sim import ArmSim


def _inward() -> dict[str, float]:
    pose = {name: 0.0 for name in ARM_JOINTS}
    pose["left_shoulder_roll"] = -0.22
    pose["right_shoulder_roll"] = 0.22
    pose["left_elbow"] = 2.0
    pose["right_elbow"] = 2.0
    pose["left_shoulder_pitch"] = -0.8
    pose["right_shoulder_pitch"] = -0.8
    return pose


def test_tpose_not_limited() -> None:
    sim = ArmSim(preview_only=True)
    limiter = ElectronicLimits(sim)
    pose, sample, blocked = limiter.apply(landmarks_to_arm_rad(synthetic_pose("tpose")))
    assert blocked is False
    assert sample.status == "SAFE"
    assert scan_pose(sim, pose).status == "SAFE"


def test_straight_forward_not_limited() -> None:
    """双臂伸直朝前：合成骨架过限位，输出仍是 -90° pitch。"""
    import math

    sim = ArmSim(preview_only=True)
    limiter = ElectronicLimits(sim)
    desired = landmarks_to_arm_rad(synthetic_pose("forward"))
    pose, sample, blocked = limiter.apply(desired)
    assert blocked is False
    assert sample.status == "SAFE"
    assert sample.minimum_distance_m >= 0.03
    assert math.degrees(pose["left_shoulder_pitch"]) < -80
    assert math.degrees(pose["right_shoulder_pitch"]) < -80
    assert abs(math.degrees(pose["left_shoulder_roll"])) < 8
    assert abs(math.degrees(pose["right_shoulder_roll"])) < 8


def test_forward_inward_roll_hits_envelope() -> None:
    """朝相机伸时手腕往中间收，内收约 8° 就会碰到 30mm 包络。"""
    import math

    sim = ArmSim(preview_only=True)
    pose = landmarks_to_arm_rad(synthetic_pose("forward"))
    pose["left_shoulder_roll"] = math.radians(-8)
    pose["right_shoulder_roll"] = math.radians(8)
    assert scan_pose(sim, pose).status == "WARNING"
    limiter = ElectronicLimits(sim)
    limited, raw, blocked = limiter.apply(pose)
    assert blocked is True
    assert raw.status == "WARNING"
    assert scan_pose(sim, limited).status == "SAFE"


def test_inward_is_clamped_to_safe() -> None:
    sim = ArmSim(preview_only=True)
    limiter = ElectronicLimits(sim)
    limiter.apply(landmarks_to_arm_rad(synthetic_pose("tpose")))
    inward = _inward()
    assert scan_pose(sim, inward).status != "SAFE"
    limited, raw, blocked = limiter.apply(inward)
    assert blocked is True
    assert raw.status != "SAFE"
    assert scan_pose(sim, limited).status == "SAFE"
