from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from apps.teacher_bridge.api import create_app
from apps.teacher_bridge.database import MotionLifecycle, MotionRecord
from motion_core.errors import ApprovalError


def test_bridge_is_fail_closed_and_seeds_unpublished_actions():
    app = create_app("sqlite:///:memory:")
    client = TestClient(app)
    assert client.get("/healthz").json()["binding"] == "loopback-only"
    assert client.get("/v1/robot/actions").json() == {"actions": []}
    plan = {"schema_version": "motion-plan/v2", "plan_id": "dance-001", "require_operator_enable": True, "steps": [{"type": "action", "action": "dance", "parameters": {}}]}
    report = client.post("/v1/robot/plans:validate", json={"plan": plan}).json()
    assert report["valid"] is False and report["motion_sent"] is False


def test_expanded_wrist_template_requires_revalidation_before_publication():
    app = create_app("sqlite:///:memory:")
    service = app.state.service
    with service.session_factory() as session:
        wrist = session.scalar(select(MotionRecord).where(MotionRecord.motion_id == "wrist_wave"))
        database_id = wrist.id
    with pytest.raises(ApprovalError, match="cannot be skipped"):
        service.transition_motion(
            database_id,
            MotionLifecycle.CLASSROOM_ENABLED,
            "teacher",
            "expanded template not revalidated",
        )
    assert service.list_actions() == []
