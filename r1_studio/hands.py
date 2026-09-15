from __future__ import annotations

from pathlib import Path
from typing import Any

from r1_studio.gestures import GesturePilot, classify_hand


class HandTracker:
    def __init__(self, model_path: Path | None = None, *, num_hands: int = 2) -> None:
        import urllib.request

        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions, RunningMode

        from r1_agent.catalog import ROOT

        path = model_path or (ROOT / "r1_studio" / "assets" / "hand_landmarker.task")
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_file() or path.stat().st_size < 100_000:
            url = (
                "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
                "hand_landmarker/float16/1/hand_landmarker.task"
            )
            urllib.request.urlretrieve(url, path)
        options = HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(path)),
            running_mode=RunningMode.IMAGE,
            num_hands=max(1, int(num_hands)),
            min_hand_detection_confidence=0.45,
            min_hand_presence_confidence=0.45,
            min_tracking_confidence=0.45,
        )
        self._landmarker = HandLandmarker.create_from_options(options)
        self._mp = mp

    def detect_bgr(self, frame) -> list[list[Any]]:
        import cv2
        import numpy as np

        from r1_studio.camera import shrink_frame

        small = shrink_frame(frame, 480)
        rgb = np.ascontiguousarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect(image)
        hands = []
        for landmarks in result.hand_landmarks or []:
            hands.append(list(landmarks))
        return hands


def overlay_hands(frame, hands: list[list], label: str):
    try:
        import cv2
    except Exception:
        return frame
    h, w = frame.shape[:2]
    for hand in hands:
        pose = classify_hand(hand)
        color = (80, 220, 120) if pose == "palm" else (80, 180, 255) if pose == "peace" else (40, 40, 220) if pose == "fist" else (200, 200, 200)
        xs = [int(getattr(p, "x", p["x"]) * w) for p in hand]
        ys = [int(getattr(p, "y", p["y"]) * h) for p in hand]
        if xs and ys:
            cv2.rectangle(frame, (min(xs), min(ys)), (max(xs), max(ys)), color, 2)
        for point in hand:
            px, py = getattr(point, "x", None), getattr(point, "y", None)
            if px is None:
                px, py = point["x"], point["y"]
            cv2.circle(frame, (int(px * w), int(py * h)), 3, color, -1)
        wrist = hand[0]
        wx = getattr(wrist, "x", None)
        wy = getattr(wrist, "y", None)
        if wx is None:
            wx, wy = wrist["x"], wrist["y"]
        cv2.putText(
            frame,
            pose,
            (int(wx * w), max(24, int(wy * h) - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            color,
            2,
        )
    cv2.rectangle(frame, (8, 8), (w - 8, 78), (20, 12, 40), -1)
    cv2.putText(frame, label[:48], (16, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 240, 220), 2)
    cv2.putText(frame, "Q in preview does not quit robot  |  E-stop in browser", (16, 66), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 200), 1)
    return frame


def overlay_operator(frame, persons: list, operator_box=None, status: str = ""):
    try:
        import cv2
    except Exception:
        return frame
    h, w = frame.shape[:2]
    for box in persons or []:
        if len(box) < 4:
            continue
        x1, y1, x2, y2 = int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (90, 90, 90), 1)
    if operator_box and len(operator_box) == 4:
        x1, y1, x2, y2 = (
            int(operator_box[0] * w),
            int(operator_box[1] * h),
            int(operator_box[2] * w),
            int(operator_box[3] * h),
        )
        color = (40, 220, 90) if status == "locked" else (40, 180, 255)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
        cv2.putText(frame, "operator", (x1, max(22, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    return frame


def overlay_detections(frame, items: list[dict]):
    try:
        import cv2
    except Exception:
        return frame
    h, w = frame.shape[:2]
    for item in items:
        box = item.get("box") or []
        if len(box) != 4:
            continue
        x1, y1, x2, y2 = [int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)]
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 200, 255), 2)
        title = f"{item.get('title') or item.get('label')} {int((item.get('score') or 0)*100)}%"
        cv2.putText(frame, title, (x1, max(20, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1)
    return frame


__all__ = ["GesturePilot", "HandTracker", "overlay_hands", "overlay_operator"]
