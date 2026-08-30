"""人肘角 ↔ 真机编码器。"""

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from r1_agent.elbow_map import (
    HUMAN_ELBOW_READY_DEG,
    HW_ELBOW_STRAIGHT_DEG,
    LEFT_ELBOW_READY_DEG,
    elbow_human_deg_to_hw,
    pose13_elbows_human_to_hw,
)


def test_straight_maps_to_measured_hw() -> None:
    assert elbow_human_deg_to_hw(0.0, LEFT_ELBOW_READY_DEG) == HW_ELBOW_STRAIGHT_DEG


def test_ready_stays_ready() -> None:
    assert abs(elbow_human_deg_to_hw(HUMAN_ELBOW_READY_DEG, LEFT_ELBOW_READY_DEG) - LEFT_ELBOW_READY_DEG) < 1e-6


def test_bent_chest_goes_below_ready() -> None:
    hw = elbow_human_deg_to_hw(95.0, LEFT_ELBOW_READY_DEG)
    assert hw < 25.0
    assert hw < LEFT_ELBOW_READY_DEG


def test_pose13_only_changes_elbows() -> None:
    pose = [0.1] * 13
    pose[3] = 0.0
    pose[8] = 0.0
    out = pose13_elbows_human_to_hw(pose)
    assert abs(math.degrees(out[3]) - HW_ELBOW_STRAIGHT_DEG) < 1.0
    assert out[0] == pose[0]
