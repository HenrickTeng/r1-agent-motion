"""把 MediaPipe IK（垂臂≈0）对齐到真机待机角，并处理面对面左右。"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Mapping

from imitate.joints import ARM_JOINTS, READY_POSE_DEG, clip_pose_rad, ready_pose_rad

# 官方网格肘 0° 时前臂朝前（视觉约屈 80°），约 76° 才最接近伸直。
# 指令角仍用真机约定：0=伸直、待机约 45°。写入官方模型时再换。
_OFFICIAL_ELBOW_STRAIGHT_DEG = 76.0
_HUMAN_ELBOW_READY_DEG = 45.0

# 教练示范：与字幕同一套真机角（度）。0=伸直，俯仰 -90=前平举。
TEACHER_POSE_DEG: dict[str, dict[str, float]] = {
    "down": dict(READY_POSE_DEG),
    "tpose": {
        "left_shoulder_pitch": 10.0,
        "left_shoulder_roll": 82.0,
        "left_shoulder_yaw": 0.0,
        "left_elbow": 32.0,
        "left_wrist_roll": 0.0,
        "right_shoulder_pitch": 10.0,
        "right_shoulder_roll": -82.0,
        "right_shoulder_yaw": 0.0,
        "right_elbow": 32.0,
        "right_wrist_roll": 0.0,
    },
    "forward": {
        "left_shoulder_pitch": -90.0,
        "left_shoulder_roll": 16.0,
        "left_shoulder_yaw": 0.0,
        "left_elbow": 32.0,
        "left_wrist_roll": 0.0,
        "right_shoulder_pitch": -90.0,
        "right_shoulder_roll": -16.0,
        "right_shoulder_yaw": 0.0,
        "right_elbow": 32.0,
        "right_wrist_roll": 0.0,
    },
    "hands_chest": {
        "left_shoulder_pitch": -25.0,
        "left_shoulder_roll": 12.0,
        "left_shoulder_yaw": -18.0,
        "left_elbow": 95.0,
        "left_wrist_roll": 0.0,
        "right_shoulder_pitch": -25.0,
        "right_shoulder_roll": -12.0,
        "right_shoulder_yaw": 18.0,
        "right_elbow": 95.0,
        "right_wrist_roll": 0.0,
    },
    "raise_user_right": {
        "left_shoulder_pitch": -155.0,
        "left_shoulder_roll": 18.0,
        "left_shoulder_yaw": 0.0,
        "left_elbow": 12.0,
        "left_wrist_roll": 0.0,
        "right_shoulder_pitch": 13.585,
        "right_shoulder_roll": -10.227,
        "right_shoulder_yaw": -1.279,
        "right_elbow": 45.857,
        "right_wrist_roll": 0.372,
    },
    "salute_user_right": {
        "left_shoulder_pitch": -72.0,
        "left_shoulder_roll": 32.0,
        "left_shoulder_yaw": -15.0,
        "left_elbow": 105.0,
        "left_wrist_roll": 12.0,
        "right_shoulder_pitch": 13.585,
        "right_shoulder_roll": -10.227,
        "right_shoulder_yaw": -1.279,
        "right_elbow": 45.857,
        "right_wrist_roll": 0.372,
    },
}
# 旧名只为读历史校准 JSON，不要写进问答 catalog。
TEACHER_POSE_DEG["raise_right"] = TEACHER_POSE_DEG["raise_user_right"]
TEACHER_POSE_DEG["salute_right"] = TEACHER_POSE_DEG["salute_user_right"]


def teacher_pose_rad(name: str) -> dict[str, float]:
    if name not in TEACHER_POSE_DEG:
        raise KeyError(name)
    pose = {joint: math.radians(deg) for joint, deg in TEACHER_POSE_DEG[name].items()}
    return clip_pose_rad(pose)


def elbows_human_to_official(pose_rad: Mapping[str, float]) -> dict[str, float]:
    """IK/真机肘 0=伸直 → 官方 r1.xml 肘角。"""
    out = dict(pose_rad)
    for name in ("left_elbow", "right_elbow"):
        if name not in out:
            continue
        ready = READY_POSE_DEG[name]
        human = math.degrees(float(out[name]))
        official = _OFFICIAL_ELBOW_STRAIGHT_DEG + human * (ready - _OFFICIAL_ELBOW_STRAIGHT_DEG) / _HUMAN_ELBOW_READY_DEG
        out[name] = math.radians(official)
    return clip_pose_rad(out)

HERE = Path(__file__).resolve().parent
STANDING_PATH = HERE / "assets" / "standing_ik_deg.json"
CALIB_PATH = HERE / "assets" / "calibration.json"

# 真机走跑待机：腰。此 MJCF 无头关节。
WAIST_READY_DEG = {"waist_yaw": -0.343, "waist_roll": 0.0}

_STRAIGHT_ELBOW_DEG = 22.0
_joint_scales: dict[str, float] | None = None

_SIGN_WHEN_SWAP = {
    "shoulder_pitch": 1.0,
    "shoulder_roll": -1.0,
    "shoulder_yaw": -1.0,
    "elbow": 1.0,
    "wrist_roll": -1.0,
}


def reload_calibration() -> None:
    global _joint_scales
    _joint_scales = None


def joint_scales() -> dict[str, float]:
    global _joint_scales
    if _joint_scales is None:
        scales = {name: 1.0 for name in ARM_JOINTS}
        if CALIB_PATH.is_file():
            raw = json.loads(CALIB_PATH.read_text(encoding="utf-8"))
            stored = raw.get("joint_scales") or {}
            for name in ARM_JOINTS:
                if name in stored:
                    scales[name] = float(stored[name])
        _joint_scales = scales
    return _joint_scales


def standing_ik_rad() -> dict[str, float]:
    if STANDING_PATH.is_file():
        raw = json.loads(STANDING_PATH.read_text(encoding="utf-8"))
        return {name: math.radians(float(raw[name])) for name in ARM_JOINTS if name in raw}
    from imitate.pose_to_arm import landmarks_to_arm_rad, synthetic_pose

    return landmarks_to_arm_rad(synthetic_pose("down"))


def retarget_to_ready(ik_rad: Mapping[str, float]) -> dict[str, float]:
    """人自然垂臂 → 真机待机；其余动作为相对待机的增量（可乘校准比例）。"""
    standing = standing_ik_rad()
    ready = ready_pose_rad()
    scales = joint_scales()
    pose = {}
    for name in ARM_JOINTS:
        if name not in ik_rad:
            continue
        delta = float(ik_rad[name]) - standing.get(name, 0.0)
        pose[name] = ready[name] + scales.get(name, 1.0) * delta
    # 肘接近伸直时偏航不可观，钉在待机，避免乱拧
    for side in ("left", "right"):
        elbow = ik_rad.get(f"{side}_elbow")
        yaw = f"{side}_shoulder_yaw"
        if elbow is not None and abs(math.degrees(float(elbow))) < _STRAIGHT_ELBOW_DEG and yaw in pose:
            pose[yaw] = ready[yaw]
    return clip_pose_rad(pose)


def swap_lr_facing(pose: Mapping[str, float]) -> dict[str, float]:
    """面对面：把右臂姿态画到左臂上（你的右手 ↔ 机器人左手）。"""
    out: dict[str, float] = {}
    for side, other in (("left", "right"), ("right", "left")):
        for joint, sign in _SIGN_WHEN_SWAP.items():
            src = f"{other}_{joint}"
            dst = f"{side}_{joint}"
            if src in pose:
                out[dst] = sign * float(pose[src])
    return clip_pose_rad(out)


def extra_ready_rad() -> dict[str, float]:
    return {name: math.radians(deg) for name, deg in WAIST_READY_DEG.items()}
