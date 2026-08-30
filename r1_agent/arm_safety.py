"""上肢真机限速与软急停策略（不发 DDS）。

官方说明：软急停进阻尼（Damp）后可能失去平衡摔倒。
因此软急停 = StopMove + 保持当前关节指令（weight 仍为 1），不要 Damp。
物理急停始终由现场遥控器负责。
"""

from __future__ import annotations

# 与 dds_robot.JOINTS 同序 13 轴：双臂 10 + 腰偏航 + 头俯仰 + 头偏航
# 单位 rad/s。跟臂略加一档（×1.25，肩俯仰约 36°/s）。
MAX_SPEED_RAD_S: tuple[float, ...] = (
    0.64,  # left_shoulder_pitch   ~37°/s
    0.54,  # left_shoulder_roll    ~31°/s
    0.64,  # left_shoulder_yaw
    0.71,  # left_elbow            ~41°/s
    0.80,  # left_wrist_roll
    0.64,  # right_shoulder_pitch
    0.54,  # right_shoulder_roll
    0.64,  # right_shoulder_yaw
    0.71,  # right_elbow
    0.80,  # right_wrist_roll
    0.31,  # waist_yaw             ~18°/s
    0.39,  # head_pitch
    0.47,  # head_yaw
)

DT_S = 0.01


def move_duration_s(start: list[float], end: list[float], requested_s: float) -> float:
    """把请求时长拉长到不超过各轴最大速度。"""
    duration = max(float(requested_s), 0.05)
    for index, (a, b) in enumerate(zip(start, end)):
        speed = MAX_SPEED_RAD_S[index] if index < len(MAX_SPEED_RAD_S) else 0.3
        duration = max(duration, abs(float(b) - float(a)) / max(speed, 1e-6))
    return duration


def slew_toward(current: list[float], target: list[float], dt: float) -> list[float]:
    """单步限速插值。"""
    out = []
    dt = max(float(dt), 1e-4)
    for index, (a, b) in enumerate(zip(current, target)):
        speed = MAX_SPEED_RAD_S[index] if index < len(MAX_SPEED_RAD_S) else 0.3
        step = speed * dt
        delta = float(b) - float(a)
        if abs(delta) <= step:
            out.append(float(b))
        else:
            out.append(float(a) + (step if delta > 0 else -step))
    if len(target) > len(out):
        out.extend(float(v) for v in target[len(out) :])
    return out
