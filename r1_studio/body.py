"""R1 机载超广角用手势：跟臂同一套 MediaPipe Pose，认肩/肘/腕，不抠手指。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from r1_studio.gestures import GestureCommand, drive_label, face_to_face_strafe
from r1_studio.teleop import MAX_VX

L_SH, R_SH = 11, 12
L_EL, R_EL = 13, 14
L_WR, R_WR = 15, 16
L_HIP, R_HIP = 23, 24
LOCK_SHAPES = frozenset({"tpose", "both_up"})


def _xy(landmarks: list, index: int) -> tuple[float, float]:
    point = landmarks[index]
    if isinstance(point, dict):
        return float(point["x"]), float(point["y"])
    return float(point.x), float(point.y)


def torso_box(landmarks: list) -> tuple[float, float, float, float] | None:
    if not landmarks or len(landmarks) < 25:
        return None
    xs, ys = [], []
    for index in (L_SH, R_SH, L_WR, R_WR, L_HIP, R_HIP, L_EL, R_EL):
        x, y = _xy(landmarks, index)
        xs.append(x)
        ys.append(y)
    return (
        max(0.0, min(xs) - 0.06),
        max(0.0, min(ys) - 0.08),
        min(1.0, max(xs) + 0.06),
        min(1.0, max(ys) + 0.08),
    )


def wrist_span(landmarks: list) -> float:
    lx, _ly = _xy(landmarks, L_WR)
    rx, _ry = _xy(landmarks, R_WR)
    return abs(rx - lx)


def classify_body(landmarks: list) -> str:
    """粗分类：机载分辨率只够看整条手臂，不看掌心/食指。"""
    if not landmarks or len(landmarks) < 25:
        return "none"
    lsh, rsh = _xy(landmarks, L_SH), _xy(landmarks, R_SH)
    lwr, rwr = _xy(landmarks, L_WR), _xy(landmarks, R_WR)
    lhp, rhp = _xy(landmarks, L_HIP), _xy(landmarks, R_HIP)
    mid_x = (lsh[0] + rsh[0]) / 2
    sh_w = max(abs(rsh[0] - lsh[0]), 0.08)
    mid_sh_y = (lsh[1] + rsh[1]) / 2
    hip_y = (lhp[1] + rhp[1]) / 2
    torso = max(hip_y - mid_sh_y, 0.12)

    def raised(wrist, shoulder) -> bool:
        return wrist[1] < shoulder[1] - 0.32 * torso

    def hanging(wrist) -> bool:
        return wrist[1] > hip_y - 0.28 * torso

    def lateral(wrist) -> bool:
        return abs(wrist[0] - mid_x) > 1.45 * sh_w

    left_up, right_up = raised(lwr, lsh), raised(rwr, rsh)
    left_down, right_down = hanging(lwr), hanging(rwr)
    left_out, right_out = lateral(lwr) and not left_up, lateral(rwr) and not right_up
    if left_up and right_up:
        return "both_up"
    if left_down and right_down:
        return "both_down"
    if left_out and right_out:
        return "tpose"
    if left_out and not right_out:
        return "left_out"
    if right_out and not left_out:
        return "right_out"
    if abs(lwr[0] - rwr[0]) < 0.95 * sh_w and not left_down and not right_down:
        return "hands_in"
    return "other"


class BodyPilot:
    """机载：侧平举锁定 → 单臂侧举横移、双臂开合进退、下垂停下、双臂上举欢呼。"""

    def __init__(self, *, cheer_hold_s: float = 0.4, cheer_cooldown_s: float = 4.0, lost_frames: int = 28) -> None:
        self.cheer_hold_s = cheer_hold_s
        self.cheer_cooldown_s = cheer_cooldown_s
        self.lost_frames = lost_frames
        self.status = "hunting"
        self.box = None
        self._lost = 0
        self._rest_span: float | None = None
        self._cheer_since: float | None = None
        self._last_cheer = -1e9

    def reset(self) -> None:
        self.status = "hunting"
        self.box = None
        self._lost = 0
        self._rest_span = None
        self._cheer_since = None

    def step(self, landmarks: list | None, now: float) -> GestureCommand:
        shape = classify_body(landmarks or [])
        self.box = torso_box(landmarks) if landmarks else None
        if shape == "none":
            self._lost += 1
            if self.status == "locked" and self._lost < self.lost_frames:
                return GestureCommand("idle", label="已锁定操控者（短暂丢骨架）", pose="none")
            self.reset()
            return GestureCommand("idle", label="请侧平举或双手上举，用全身姿势锁定", pose="none")
        self._lost = 0
        if self.status != "locked":
            if shape in LOCK_SHAPES:
                self.status = "locked"
                if shape == "tpose" and landmarks:
                    # 锁定时的侧平举当作「略收」，再张开才会后退；避免跟距=当前张开永远走不了
                    self._rest_span = max(wrist_span(landmarks) * 0.86, 0.12)
                return GestureCommand("idle", label="已锁定操控者（全身 Pose）", pose=shape)
            return GestureCommand("idle", label="请侧平举或双手上举，用全身姿势锁定", pose=shape)

        if shape == "both_down":
            self._rest_span = None
            self._cheer_since = None
            return GestureCommand("stop", label="双臂下垂停下", pose="both_down")
        if shape == "both_up":
            self._rest_span = None
            if now - self._last_cheer < self.cheer_cooldown_s:
                return GestureCommand("idle", label="欢呼冷却中", pose="both_up")
            if self._cheer_since is None:
                self._cheer_since = now
            if now - self._cheer_since >= self.cheer_hold_s:
                self._last_cheer = now
                self._cheer_since = None
                return GestureCommand("cheer", label="双臂上举 → 欢呼", pose="both_up")
            return GestureCommand("idle", label="双臂上举保持中…", pose="both_up")
        self._cheer_since = None
        if shape == "left_out":
            self._rest_span = None
            vy = face_to_face_strafe(-1.0)
            return GestureCommand("drive", vy=vy, label=drive_label(0.0, vy, 0.0, operator_nx=-1.0), pose="left_out")
        if shape == "right_out":
            self._rest_span = None
            vy = face_to_face_strafe(1.0)
            return GestureCommand("drive", vy=vy, label=drive_label(0.0, vy, 0.0, operator_nx=1.0), pose="right_out")
        if shape == "hands_in":
            return GestureCommand("drive", vx=MAX_VX, label="飞近（前进）", pose="hands_in")
        if shape == "tpose":
            if landmarks is None:
                return GestureCommand("idle", label="侧平举 · 悬停（这姿态不下发走路）", pose="tpose")
            span = wrist_span(landmarks)
            if self._rest_span is None:
                self._rest_span = max(span * 0.86, 0.12)
                return GestureCommand("idle", label="侧平举跟距：再分开才后退，收拢才前进", pose="tpose")
            ratio = (span - self._rest_span) / max(self._rest_span, 1e-4)
            if ratio > 0.10:
                return GestureCommand("drive", vx=-MAX_VX, label="飞远（后退）", pose="tpose")
            if ratio < -0.10:
                return GestureCommand("drive", vx=MAX_VX, label="飞近（前进）", pose="tpose")
            return GestureCommand("idle", label="侧平举 · 悬停（这姿态不下发走路）", pose="tpose")
        return GestureCommand("idle", label="已锁定 · 换个大动作", pose=shape)


class PoseTracker:
    def __init__(self, model_path: Path | None = None) -> None:
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python.vision import PoseLandmarker, PoseLandmarkerOptions, RunningMode

        from imitate.camera import ensure_pose_model

        path = model_path or ensure_pose_model()
        options = PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(path)),
            running_mode=RunningMode.IMAGE,
            num_poses=1,
            min_pose_detection_confidence=0.35,
            min_pose_presence_confidence=0.35,
            min_tracking_confidence=0.35,
        )
        self._landmarker = PoseLandmarker.create_from_options(options)
        self._mp = mp

    def detect_bgr(self, frame) -> list[Any] | None:
        import cv2
        import numpy as np

        from r1_studio.camera import shrink_frame

        small = shrink_frame(frame, 640)
        rgb = np.ascontiguousarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect(image)
        poses = result.pose_landmarks or []
        if not poses:
            return None
        return list(poses[0])


def overlay_pose(frame, landmarks: list | None, label: str, box=None):
    try:
        import cv2
    except Exception:
        return frame
    h, w = frame.shape[:2]
    if box and len(box) == 4:
        x1, y1, x2, y2 = int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (40, 220, 90), 3)
        cv2.putText(frame, "pose operator", (x1, max(22, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (40, 220, 90), 2)
    if landmarks and len(landmarks) >= 17:
        joints = (L_SH, R_SH, L_EL, R_EL, L_WR, R_WR, L_HIP, R_HIP)
        pts = {}
        for index in joints:
            x, y = _xy(landmarks, index)
            px, py = int(x * w), int(y * h)
            pts[index] = (px, py)
            cv2.circle(frame, (px, py), 5, (80, 220, 120), -1)
        for a, b in ((L_SH, R_SH), (L_SH, L_EL), (L_EL, L_WR), (R_SH, R_EL), (R_EL, R_WR), (L_SH, L_HIP), (R_SH, R_HIP), (L_HIP, R_HIP)):
            if a in pts and b in pts:
                cv2.line(frame, pts[a], pts[b], (80, 180, 255), 2)
    cv2.rectangle(frame, (8, 8), (w - 8, 78), (20, 12, 40), -1)
    cv2.putText(frame, label[:48], (16, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 240, 220), 2)
    cv2.putText(frame, "R1 pose (imitate)  |  E-stop in browser", (16, 66), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 200), 1)
    return frame
