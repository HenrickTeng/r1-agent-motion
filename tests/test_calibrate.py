"""校准拟合：垂臂零位 + 关节比例。"""

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from imitate.calibrate import fit_joint_scales
from imitate.joints import READY_POSE_DEG, ready_pose_rad
from imitate.retarget import TEACHER_POSE_DEG, retarget_to_ready


def test_fit_roll_scale_from_tpose() -> None:
    standing = {name: 0.0 for name in READY_POSE_DEG}
    tpose = {name: 0.0 for name in READY_POSE_DEG}
    tpose["left_shoulder_roll"] = math.radians(40.0)
    tpose["right_shoulder_roll"] = math.radians(-40.0)
    scales = fit_joint_scales(standing, {"tpose": tpose})
    want_l = (TEACHER_POSE_DEG["tpose"]["left_shoulder_roll"] - READY_POSE_DEG["left_shoulder_roll"]) / 40.0
    assert abs(scales["left_shoulder_roll"] - want_l) < 0.05
    assert scales["left_elbow"] == 1.0


def test_tiny_delta_keeps_scale_one() -> None:
    standing = {name: 0.0 for name in READY_POSE_DEG}
    tpose = dict(standing)
    tpose["left_shoulder_roll"] = math.radians(2.0)
    scales = fit_joint_scales(standing, {"tpose": tpose})
    assert scales["left_shoulder_roll"] == 1.0


def test_ready_retarget_unchanged_at_standing() -> None:
    from imitate.retarget import standing_ik_rad

    out = retarget_to_ready(standing_ik_rad())
    ready = ready_pose_rad()
    for name, value in ready.items():
        assert abs(out[name] - value) < 1e-6, name
