"""IK/仿真肘：0=伸直、45≈待机弯。真机走跑编码器：45=待机弯、95=看起来伸直。

只在发给 rt/arm_sdk 时换算，限位仍在人/仿真角上做。
"""

from __future__ import annotations

import math

# 真机实测：指令 95° 时 J4 跟上且看起来伸直；待机 45° 看起来弯。
HW_ELBOW_STRAIGHT_DEG = 95.0
HUMAN_ELBOW_READY_DEG = 45.0
ELBOW_LIMIT_RAD = (-0.9757, 2.1850)

# dds_robot.READY_POSE_DEG 左/右肘
LEFT_ELBOW_READY_DEG = 45.182
RIGHT_ELBOW_READY_DEG = 45.857


def _clip_elbow(rad: float) -> float:
    lo, hi = ELBOW_LIMIT_RAD
    return max(lo, min(hi, float(rad)))


def elbow_human_deg_to_hw(human_deg: float, ready_hw_deg: float) -> float:
    t = float(human_deg) / HUMAN_ELBOW_READY_DEG
    return HW_ELBOW_STRAIGHT_DEG + t * (float(ready_hw_deg) - HW_ELBOW_STRAIGHT_DEG)


def elbow_human_rad_to_hw(human_rad: float, ready_hw_deg: float) -> float:
    return _clip_elbow(math.radians(elbow_human_deg_to_hw(math.degrees(human_rad), ready_hw_deg)))


def pose13_elbows_human_to_hw(pose: list[float]) -> list[float]:
    out = list(pose)
    if len(out) > 3:
        out[3] = elbow_human_rad_to_hw(out[3], LEFT_ELBOW_READY_DEG)
    if len(out) > 8:
        out[8] = elbow_human_rad_to_hw(out[8], RIGHT_ELBOW_READY_DEG)
    return out
