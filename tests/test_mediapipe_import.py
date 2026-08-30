"""确认本机 MediaPipe Tasks Pose 能 import，并在有模型时能构建。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_mediapipe_tasks_api() -> None:
    import mediapipe as mp
    from mediapipe.tasks.python import vision

    assert hasattr(mp, "Image")
    assert hasattr(vision, "PoseLandmarker")
    assert hasattr(vision, "PoseLandmarkerOptions")


def test_pose_model_builds_when_present() -> None:
    from imitate.camera import MODEL_PATH
    from mediapipe.tasks.python import BaseOptions, vision

    if not MODEL_PATH.is_file():
        return
    options = vision.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(MODEL_PATH)),
        running_mode=vision.RunningMode.IMAGE,
        num_poses=1,
    )
    landmarker = vision.PoseLandmarker.create_from_options(options)
    landmarker.close()
