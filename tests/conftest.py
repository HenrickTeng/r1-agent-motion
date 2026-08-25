from pathlib import Path

import pytest

from motion_core.compiler import MotionCompiler
from motion_core.schemas import MotionDesignSpec


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def wrist_spec():
    return MotionDesignSpec.model_validate({
        "schema_version": "motion-design-spec/v1",
        "motion_id": "wrist-test-v1",
        "title": "Right wrist test",
        "intent": "slow right wrist roll",
        "joint_keyframes": [{"time_s": 2.0, "offsets": [{"joint": "right_wrist_roll", "offset_rad": 0.3}]}],
        "return_policy": {"mode": "return_to_initial", "duration_s": 2.0},
    })


@pytest.fixture
def wrist_trajectory(wrist_spec):
    return MotionCompiler(ROOT / "config" / "classroom-upper-v1.json").compile(wrist_spec)
