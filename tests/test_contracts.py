import pytest
from pydantic import ValidationError

from motion_core.schemas import MotionDesignSpec, MotionPlan


def test_plan_accepts_only_public_step_union():
    plan = MotionPlan.model_validate({
        "schema_version": "motion-plan/v2", "plan_id": "safe-001", "require_operator_enable": True,
        "steps": [{"type": "move_for", "vx_mps": 0.15, "vy_mps": -0.1, "duration_s": 2}],
    })
    assert plan.steps[0].type == "move_for"


@pytest.mark.parametrize("step", [
    {"type": "shell", "command": "echo unsafe"},
    {"type": "action", "action": "wave", "parameters": {}, "dds_topic": "rt/lowcmd"},
    {"type": "move_for", "vx_mps": 0.151, "vy_mps": 0, "duration_s": 1},
    {"type": "turn_relative", "angle_deg": 31},
])
def test_plan_rejects_unknown_and_unsafe_fields(step):
    with pytest.raises(ValidationError):
        MotionPlan.model_validate({"schema_version": "motion-plan/v2", "plan_id": "bad-001", "require_operator_enable": True, "steps": [step]})


def test_design_requires_upper_body_target_and_rejects_code():
    with pytest.raises(ValidationError):
        MotionDesignSpec.model_validate({"schema_version": "motion-design-spec/v1", "motion_id": "bad-design", "title": "bad", "intent": "bad", "code": "publish lowcmd"})
