from pathlib import Path

import pytest

from motion_core.compiler import MotionCompiler
from motion_core.errors import SafetyError
from motion_core.schemas import MotionDesignSpec
from motion_core.simulator import TrajectorySimulator


ROOT = Path(__file__).resolve().parents[1]


def test_compiler_is_deterministic_and_returns(wrist_spec):
    compiler = MotionCompiler(ROOT / "config" / "classroom-upper-v1.json")
    first = compiler.compile(wrist_spec)
    second = compiler.compile(wrist_spec)
    assert first.trajectory_sha256 == second.trajectory_sha256
    assert first.sample_hz == 100
    assert len(first.samples[0].position_rad) == 13
    assert first.limits.return_error_rad == 0


def test_compiler_rejects_uncalibrated_joint():
    spec = MotionDesignSpec.model_validate({
        "schema_version": "motion-design-spec/v1", "motion_id": "unsafe-left", "title": "left", "intent": "left",
        "joint_keyframes": [{"time_s": 2, "offsets": [{"joint": "left_elbow", "offset_rad": 0.1}]}],
    })
    with pytest.raises(SafetyError, match="calibration"):
        MotionCompiler(ROOT / "config" / "classroom-upper-v1.json").compile(spec)


def test_simulator_fails_closed_without_authoritative_model(wrist_trajectory):
    report = TrajectorySimulator().run(wrist_trajectory)
    assert report.passed is False
    assert report.dynamic_checks[0].name == "authoritative_mujoco_model"


def test_external_model_audit_exposes_known_mapping_gap(wrist_trajectory):
    model = Path("/home/henrick/unitree_rl_mjlab/src/assets/robots/unitree_r1/xmls/r1.xml")
    if not model.exists():
        pytest.skip("external model is not installed")
    report = TrajectorySimulator(model).run(wrist_trajectory)
    assert report.passed is False
    assert "head_pitch_joint" in str(report.dynamic_checks[0].measured)
