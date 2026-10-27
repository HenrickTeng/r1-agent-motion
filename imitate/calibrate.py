"""摄像头 / 身材校准：跟 R1 画面，不看文字。结果写入 assets。"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Mapping

from imitate.joints import ARM_JOINTS, READY_POSE_DEG
from imitate.retarget import TEACHER_POSE_DEG, STANDING_PATH, reload_calibration

from imitate.laterality import MIRROR_LIBRARY

HERE = Path(__file__).resolve().parent
CALIB_PATH = HERE / "assets" / "calibration.json"

CALIB_POSES: tuple[str, ...] = (
    "down",
    "tpose",
    "forward",
    "hands_chest",
    "raise_user_right",
    "salute_user_right",
)
CALIB_DEMO_S = 24.0
CALIB_SAMPLES = 3
SCALE_MIN = 0.4
SCALE_MAX = 2.5
MIN_DELTA_DEG = 8.0

# 用哪些示范课拟合哪些关节的比例
_SCALE_SOURCES: dict[str, tuple[str, ...]] = {
    "tpose": ("left_shoulder_roll", "right_shoulder_roll"),
    "forward": ("left_shoulder_pitch", "right_shoulder_pitch"),
    "hands_chest": ("left_elbow", "right_elbow"),
    "raise_user_right": ("left_shoulder_pitch",),
    "raise_right": ("left_shoulder_pitch",),
}


def mean_pose_rad(frames: list[Mapping[str, float]]) -> dict[str, float]:
    out = {}
    for name in ARM_JOINTS:
        values = [float(frame[name]) for frame in frames if name in frame]
        if values:
            out[name] = sum(values) / len(values)
    return out


def pose_rad_to_deg(pose: Mapping[str, float]) -> dict[str, float]:
    return {name: round(math.degrees(float(pose[name])), 3) for name in ARM_JOINTS if name in pose}


def write_standing_ik(standing_rad: Mapping[str, float]) -> Path:
    payload = {
        "source": "calibrate",
        "note": "人自然垂臂时的 IK 绝对角（度）。cmd = ready + scale * (ik - standing)",
        **{name: round(math.degrees(float(standing_rad[name])), 3) for name in ARM_JOINTS if name in standing_rad},
    }
    STANDING_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return STANDING_PATH


def fit_joint_scales(
    standing_rad: Mapping[str, float],
    pose_means_rad: Mapping[str, Mapping[str, float]],
) -> dict[str, float]:
    """teacher - ready ≈ scale * (ik - standing)。分母太小则保持 1。"""
    scales = {name: 1.0 for name in ARM_JOINTS}
    used: dict[str, str] = {}
    for pose_name, joints in _SCALE_SOURCES.items():
        ik = pose_means_rad.get(pose_name)
        teacher = TEACHER_POSE_DEG.get(pose_name)
        if ik is None or teacher is None:
            continue
        for joint in joints:
            if joint not in ik or joint not in standing_rad:
                continue
            denom = math.degrees(float(ik[joint]) - float(standing_rad[joint]))
            numer = float(teacher[joint]) - float(READY_POSE_DEG[joint])
            if abs(denom) < MIN_DELTA_DEG:
                continue
            scale = numer / denom
            scales[joint] = max(SCALE_MIN, min(SCALE_MAX, scale))
            used[joint] = pose_name
    return scales


def save_calibration(
    *,
    camera: int,
    standing_rad: Mapping[str, float],
    pose_means_rad: Mapping[str, Mapping[str, float]],
    scales: Mapping[str, float],
    raw_by_pose: Mapping[str, list[dict[str, float]]],
) -> Path:
    CALIB_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "r1-arm-calib/v1",
        "saved_at": int(time.time()),
        "camera": camera,
        "demo_s": CALIB_DEMO_S,
        "samples_per_pose": CALIB_SAMPLES,
        "poses": list(CALIB_POSES),
        "standing_ik_deg": pose_rad_to_deg(standing_rad),
        "joint_scales": {name: round(float(scales[name]), 4) for name in ARM_JOINTS},
        "pose_ik_mean_deg": {
            name: pose_rad_to_deg(mean) for name, mean in pose_means_rad.items()
        },
        "teacher_deg": {name: dict(TEACHER_POSE_DEG[name]) for name in CALIB_POSES},
        "raw_ik_deg": {
            name: [pose_rad_to_deg(frame) for frame in frames]
            for name, frames in raw_by_pose.items()
        },
    }
    CALIB_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    MIRROR_LIBRARY.mkdir(parents=True, exist_ok=True)
    archive = MIRROR_LIBRARY / f"calib_{payload['saved_at']}.json"
    archive.write_text(CALIB_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    write_standing_ik(standing_rad)
    reload_calibration()
    return CALIB_PATH
