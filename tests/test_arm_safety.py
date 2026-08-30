"""上肢限速：不连真机。"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from r1_agent.arm_safety import MAX_SPEED_RAD_S, move_duration_s, slew_toward


def test_move_duration_stretches_when_too_fast() -> None:
    start = [0.0] * 13
    end = [0.0] * 13
    end[0] = 1.0
    duration = move_duration_s(start, end, 0.1)
    assert duration == pytest.approx(1.0 / MAX_SPEED_RAD_S[0])


def test_move_duration_keeps_slow_request() -> None:
    start = [0.0] * 13
    end = [0.0] * 13
    end[0] = 0.05
    assert move_duration_s(start, end, 2.0) == 2.0


def test_slew_caps_step() -> None:
    current = [0.0] * 13
    target = [2.0] * 13
    out = slew_toward(current, target, 0.01)
    assert out[0] == pytest.approx(MAX_SPEED_RAD_S[0] * 0.01)
    assert out[0] < 2.0
