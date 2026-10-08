"""MediaPipe Pose 世界坐标（米）→ R1 双臂 10 关节绝对角（弧度）。

MediaPipe world: x 向人的右，y 向上，z 指向相机（人正对相机时，人体前方约为 -z）。
R1: x 向前，y 向左，z 向上。

肩：先 pitch(Y) 再 roll(X)，零位大臂朝下 -Z。
肘：屈曲为正（0=伸直）。
大臂旋转 / 小臂旋转：绕大臂、前臂轴线；肘接近伸直时 yaw 不可观，置 0。
J3 yaw 在 pitch/roll 之后的关节系里计算（零位为该系 +X），避免前伸时用世界前方当零位把符号拧反。
"""

from __future__ import annotations

import math
from typing import Mapping, Sequence

import numpy as np

from imitate.joints import ARM_JOINTS, clip_pose_rad

# MediaPipe Pose 索引
L_SH, R_SH = 11, 12
L_EL, R_EL = 13, 14
L_WR, R_WR = 15, 16
L_PINKY, R_PINKY = 17, 18
L_INDEX, R_INDEX = 19, 20
L_HIP, R_HIP = 23, 24


def _as_xyz(landmarks: Sequence | np.ndarray | Mapping, index: int) -> np.ndarray:
    if isinstance(landmarks, Mapping):
        point = landmarks[index]
    else:
        point = landmarks[index]
    if hasattr(point, "x"):
        return np.array([float(point.x), float(point.y), float(point.z)], dtype=np.float64)
    return np.asarray(point, dtype=np.float64)[:3]


def mp_world_to_r1(point: np.ndarray) -> np.ndarray:
    x, y, z = float(point[0]), float(point[1]), float(point[2])
    return np.array([-z, -x, y], dtype=np.float64)


def _norm(vector: np.ndarray) -> np.ndarray:
    length = float(np.linalg.norm(vector))
    if length < 1e-8:
        return np.zeros(3, dtype=np.float64)
    return vector / length


def _angle(p1: np.ndarray, p2: np.ndarray, p3: np.ndarray) -> float:
    v1 = p1 - p2
    v2 = p3 - p2
    n1, n2 = float(np.linalg.norm(v1)), float(np.linalg.norm(v2))
    if n1 < 1e-8 or n2 < 1e-8:
        return math.pi
    cosine = float(np.clip(np.dot(v1, v2) / (n1 * n2), -1.0, 1.0))
    return math.acos(cosine)


def _torso_rotation(landmarks: Sequence | np.ndarray | Mapping) -> np.ndarray:
    """返回 3x3，列向量为躯干坐标系在 R1 世界里的 x/y/z。"""
    l_sh = mp_world_to_r1(_as_xyz(landmarks, L_SH))
    r_sh = mp_world_to_r1(_as_xyz(landmarks, R_SH))
    l_hip = mp_world_to_r1(_as_xyz(landmarks, L_HIP))
    r_hip = mp_world_to_r1(_as_xyz(landmarks, R_HIP))
    mid_sh = 0.5 * (l_sh + r_sh)
    mid_hip = 0.5 * (l_hip + r_hip)
    y_axis = _norm(l_sh - r_sh)
    z_axis = _norm(mid_sh - mid_hip)
    if float(np.linalg.norm(z_axis)) < 1e-6:
        z_axis = np.array([0.0, 0.0, 1.0])
    x_axis = _norm(np.cross(y_axis, z_axis))
    if float(np.linalg.norm(x_axis)) < 1e-6:
        x_axis = np.array([1.0, 0.0, 0.0])
        y_axis = _norm(np.cross(z_axis, x_axis))
    else:
        y_axis = _norm(np.cross(z_axis, x_axis))
        z_axis = _norm(np.cross(x_axis, y_axis))
    return np.stack([x_axis, y_axis, z_axis], axis=1)


def _in_torso(point: np.ndarray, origin: np.ndarray, rotation: np.ndarray) -> np.ndarray:
    return rotation.T @ (point - origin)


def _shoulder_pitch_roll(upper: np.ndarray) -> tuple[float, float]:
    """大臂方向（躯干系）→ pitch, roll。零位 [0,0,-1]。"""
    u = _norm(upper)
    if float(np.linalg.norm(u)) < 1e-8:
        return 0.0, 0.0
    pitch = math.atan2(-u[0], -u[2] + 1e-12)
    c, s = math.cos(pitch), math.sin(pitch)
    # Ry(-pitch) @ u
    unpitch = np.array([c * u[0] - s * u[2], u[1], s * u[0] + c * u[2]])
    roll = math.atan2(unpitch[1], -unpitch[2] + 1e-12)
    return pitch, roll


def _signed_angle_around(axis: np.ndarray, source: np.ndarray, target: np.ndarray) -> float:
    axis = _norm(axis)
    source = _norm(source - np.dot(source, axis) * axis)
    target = _norm(target - np.dot(target, axis) * axis)
    if float(np.linalg.norm(source)) < 1e-8 or float(np.linalg.norm(target)) < 1e-8:
        return 0.0
    sine = float(np.dot(axis, np.cross(source, target)))
    cosine = float(np.clip(np.dot(source, target), -1.0, 1.0))
    return math.atan2(sine, cosine)


def _rot_x(angle: float) -> np.ndarray:
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]], dtype=np.float64)


def _rot_y(angle: float) -> np.ndarray:
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]], dtype=np.float64)


def _shoulder_yaw(upper: np.ndarray, forearm: np.ndarray, pitch: float, roll: float) -> float:
    """在 pitch/roll 之后的 yaw 关节系里求 J3。零位前臂沿该系 +X（屈肘 90° 时朝前/朝上随姿态变）。"""
    u = _norm(upper)
    f = _norm(forearm)
    if float(np.linalg.norm(np.cross(u, f))) < 0.08:
        return 0.0
    # 与 MJCF 一致：Ry(pitch) Rx(roll) Rz(yaw)，yaw 轴为该姿态下的 +Z
    yaw_frame = _rot_y(pitch) @ _rot_x(roll)
    axis = yaw_frame @ np.array([0.0, 0.0, 1.0])
    zero = yaw_frame @ np.array([1.0, 0.0, 0.0])
    return _signed_angle_around(axis, zero, f)


def _wrist_roll(forearm: np.ndarray, pinky: np.ndarray, index: np.ndarray) -> float:
    axis = _norm(forearm)
    palm = index - pinky
    if float(np.linalg.norm(palm)) < 1e-6 or float(np.linalg.norm(axis)) < 1e-8:
        return 0.0
    down = np.array([0.0, 0.0, -1.0])
    return _signed_angle_around(axis, down, palm)


def _one_arm(
    landmarks: Sequence | np.ndarray | Mapping,
    *,
    sh: int,
    el: int,
    wr: int,
    pinky: int,
    index: int,
    origin: np.ndarray,
    rotation: np.ndarray,
) -> dict[str, float]:
    shoulder = _in_torso(mp_world_to_r1(_as_xyz(landmarks, sh)), origin, rotation)
    elbow = _in_torso(mp_world_to_r1(_as_xyz(landmarks, el)), origin, rotation)
    wrist = _in_torso(mp_world_to_r1(_as_xyz(landmarks, wr)), origin, rotation)
    upper = elbow - shoulder
    forearm = wrist - elbow
    pitch, roll = _shoulder_pitch_roll(upper)
    yaw = _shoulder_yaw(upper, forearm, pitch, roll)
    interior = _angle(shoulder, elbow, wrist)
    elbow_flex = math.pi - interior
    try:
        pky = _in_torso(mp_world_to_r1(_as_xyz(landmarks, pinky)), origin, rotation)
        idx = _in_torso(mp_world_to_r1(_as_xyz(landmarks, index)), origin, rotation)
        wrist_roll = _wrist_roll(forearm, pky, idx)
    except (KeyError, IndexError, TypeError):
        wrist_roll = 0.0
    # 课堂只要求“看着像”，腕旋转噪声大，幅值过大时直接丢掉
    if abs(wrist_roll) > math.radians(80):
        wrist_roll = 0.0
    return {
        "shoulder_pitch": pitch,
        "shoulder_roll": roll,
        "shoulder_yaw": yaw,
        "elbow": elbow_flex,
        "wrist_roll": wrist_roll,
    }


def landmarks_to_arm_rad(landmarks: Sequence | np.ndarray | Mapping) -> dict[str, float]:
    """33 点世界坐标 → 10 个上肢关节绝对角（rad），已限位。"""
    l_sh = mp_world_to_r1(_as_xyz(landmarks, L_SH))
    r_sh = mp_world_to_r1(_as_xyz(landmarks, R_SH))
    origin = 0.5 * (l_sh + r_sh)
    rotation = _torso_rotation(landmarks)
    left = _one_arm(landmarks, sh=L_SH, el=L_EL, wr=L_WR, pinky=L_PINKY, index=L_INDEX, origin=origin, rotation=rotation)
    right = _one_arm(landmarks, sh=R_SH, el=R_EL, wr=R_WR, pinky=R_PINKY, index=R_INDEX, origin=origin, rotation=rotation)
    pose = {
        "left_shoulder_pitch": left["shoulder_pitch"],
        "left_shoulder_roll": left["shoulder_roll"],
        "left_shoulder_yaw": left["shoulder_yaw"],
        "left_elbow": left["elbow"],
        "left_wrist_roll": left["wrist_roll"],
        "right_shoulder_pitch": right["shoulder_pitch"],
        "right_shoulder_roll": right["shoulder_roll"],
        "right_shoulder_yaw": right["shoulder_yaw"],
        "right_elbow": right["elbow"],
        "right_wrist_roll": right["wrist_roll"],
    }
    return clip_pose_rad(pose)


def empty_landmarks() -> np.ndarray:
    return np.zeros((33, 3), dtype=np.float64)


def synthetic_pose(name: str) -> np.ndarray:
    """教学用合成骨架，单位米，MediaPipe world。人正对相机站立。"""
    points = empty_landmarks()
    points[L_HIP] = (-0.10, 0.00, 0.00)
    points[R_HIP] = (0.10, 0.00, 0.00)
    points[L_SH] = (-0.18, 0.42, 0.00)
    points[R_SH] = (0.18, 0.42, 0.00)
    if name in ("down", "ready"):
        points[L_EL] = (-0.20, 0.18, 0.00)
        points[R_EL] = (0.20, 0.18, 0.00)
        points[L_WR] = (-0.21, -0.06, 0.00)
        points[R_WR] = (0.21, -0.06, 0.00)
    elif name == "tpose":
        points[L_EL] = (-0.42, 0.42, 0.00)
        points[R_EL] = (0.42, 0.42, 0.00)
        points[L_WR] = (-0.66, 0.42, 0.00)
        points[R_WR] = (0.66, 0.42, 0.00)
    elif name == "forward":
        points[L_EL] = (-0.18, 0.42, -0.24)
        points[R_EL] = (0.18, 0.42, -0.24)
        points[L_WR] = (-0.18, 0.42, -0.48)
        points[R_WR] = (0.18, 0.42, -0.48)
    elif name == "salute_right":
        points[L_EL] = (-0.20, 0.18, 0.00)
        points[L_WR] = (-0.21, -0.06, 0.00)
        points[R_EL] = (0.22, 0.52, -0.12)
        points[R_WR] = (0.10, 0.62, -0.04)
    elif name == "raise_right":
        points[L_EL] = (-0.20, 0.18, 0.00)
        points[L_WR] = (-0.21, -0.06, 0.00)
        points[R_EL] = (0.18, 0.66, 0.00)
        points[R_WR] = (0.18, 0.90, 0.00)
    elif name == "hands_chest":
        # 双手停在胸前两侧，不交叉
        points[L_EL] = (-0.18, 0.38, -0.14)
        points[R_EL] = (0.18, 0.38, -0.14)
        points[L_WR] = (-0.14, 0.32, -0.12)
        points[R_WR] = (0.14, 0.32, -0.12)
    else:
        raise KeyError(f"unknown synthetic pose: {name}")
    points[L_PINKY] = points[L_WR] + np.array([-0.02, -0.02, 0.01])
    points[R_PINKY] = points[R_WR] + np.array([0.02, -0.02, 0.01])
    points[L_INDEX] = points[L_WR] + np.array([-0.02, 0.02, 0.01])
    points[R_INDEX] = points[R_WR] + np.array([0.02, 0.02, 0.01])
    return points


SYNTHETIC_POSES = ("down", "tpose", "forward", "salute_right", "raise_right", "hands_chest")


def mediapipe_world_to_array(world_landmarks) -> np.ndarray:
    """把 MediaPipe pose_world_landmarks 转成 (33, 3) 米制坐标。"""
    points = np.zeros((33, 3), dtype=np.float64)
    seq = world_landmarks.landmark if hasattr(world_landmarks, "landmark") else world_landmarks
    for index, landmark in enumerate(list(seq)[:33]):
        points[index] = (float(landmark.x), float(landmark.y), float(landmark.z))
    return points


class PoseSmoother:
    """指数滑动平均，压 MediaPipe 抖动。"""

    def __init__(self, alpha: float = 0.35) -> None:
        self.alpha = alpha
        self._state: dict[str, float] | None = None

    def reset(self) -> None:
        self._state = None

    def update(self, pose: Mapping[str, float]) -> dict[str, float]:
        if self._state is None:
            self._state = {name: float(pose[name]) for name in ARM_JOINTS if name in pose}
            return dict(self._state)
        for name in ARM_JOINTS:
            if name not in pose:
                continue
            self._state[name] = (1.0 - self.alpha) * self._state[name] + self.alpha * float(pose[name])
        return clip_pose_rad(self._state)

