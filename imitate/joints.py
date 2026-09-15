"""R1 上肢 10 关节：名称、限位、ready_pose、与 r1-agent-motion 系数换算。"""

from __future__ import annotations

import math
from typing import Mapping

ARM_JOINTS: tuple[str, ...] = (
    "left_shoulder_pitch",
    "left_shoulder_roll",
    "left_shoulder_yaw",
    "left_elbow",
    "left_wrist_roll",
    "right_shoulder_pitch",
    "right_shoulder_roll",
    "right_shoulder_yaw",
    "right_elbow",
    "right_wrist_roll",
)

# 与 dds_robot.JOINTS / MOTIONS 短名对齐
SHORT_NAMES: dict[str, str] = {
    "left_shoulder_pitch": "LSP",
    "left_shoulder_roll": "LSR",
    "left_shoulder_yaw": "LSY",
    "left_elbow": "LE",
    "left_wrist_roll": "LWR",
    "right_shoulder_pitch": "RSP",
    "right_shoulder_roll": "RSR",
    "right_shoulder_yaw": "RSY",
    "right_elbow": "RE",
    "right_wrist_roll": "RWR",
}

# 官方限位（rad），来自 R1 开发文档
LIMITS_RAD: dict[str, tuple[float, float]] = {
    "left_shoulder_pitch": (-3.1416, 2.0944),
    "left_shoulder_roll": (-0.2269, 2.4784),
    "left_shoulder_yaw": (-1.9199, 1.9199),
    "left_elbow": (-0.9757, 2.1850),
    "left_wrist_roll": (-1.9199, 1.9199),
    "right_shoulder_pitch": (-3.1416, 2.0944),
    "right_shoulder_roll": (-2.4784, 0.2269),
    "right_shoulder_yaw": (-1.9199, 1.9199),
    "right_elbow": (-0.9757, 2.1850),
    "right_wrist_roll": (-1.9199, 1.9199),
}

# 真机课堂准备姿态（度），与 r1_agent/dds_robot.py READY_POSE_DEG 一致
READY_POSE_DEG: dict[str, float] = {
    "left_shoulder_pitch": 13.381,
    "left_shoulder_roll": 10.569,
    "left_shoulder_yaw": 1.323,
    "left_elbow": 45.182,
    "left_wrist_roll": -0.25,
    "right_shoulder_pitch": 13.585,
    "right_shoulder_roll": -10.227,
    "right_shoulder_yaw": -1.279,
    "right_elbow": 45.857,
    "right_wrist_roll": 0.372,
}

SHOULDER_PITCH_SCALE = 3.0
OTHER_SCALE = 1.8
PITCH_JOINTS = {"left_shoulder_pitch", "right_shoulder_pitch"}


def clip_rad(joint: str, value: float) -> float:
    lo, hi = LIMITS_RAD[joint]
    return max(lo, min(hi, value))


def clip_pose_rad(pose: Mapping[str, float]) -> dict[str, float]:
    return {name: clip_rad(name, float(pose[name])) for name in ARM_JOINTS if name in pose}


def ready_pose_rad() -> dict[str, float]:
    return {name: math.radians(deg) for name, deg in READY_POSE_DEG.items()}


def scale_for(joint: str) -> float:
    return SHOULDER_PITCH_SCALE if joint in PITCH_JOINTS else OTHER_SCALE


def abs_deg_to_coeff(joint: str, abs_deg: float) -> float:
    """绝对角度(度) → dds_robot MOTIONS 用的系数。"""
    offset_rad = math.radians(abs_deg - READY_POSE_DEG[joint])
    return offset_rad / scale_for(joint)


def coeff_to_abs_deg(joint: str, coeff: float) -> float:
    return READY_POSE_DEG[joint] + math.degrees(coeff * scale_for(joint))


def pose_rad_to_abs_deg(pose: Mapping[str, float]) -> dict[str, float]:
    return {name: math.degrees(float(pose[name])) for name in ARM_JOINTS if name in pose}


def offsets_deg_from_abs(abs_deg: Mapping[str, float]) -> dict[str, float]:
    return {name: float(abs_deg[name]) - READY_POSE_DEG[name] for name in ARM_JOINTS if name in abs_deg}


def coeffs_from_abs_deg(abs_deg: Mapping[str, float]) -> dict[str, float]:
    return {SHORT_NAMES[name]: round(abs_deg_to_coeff(name, float(abs_deg[name])), 4) for name in ARM_JOINTS if name in abs_deg}
