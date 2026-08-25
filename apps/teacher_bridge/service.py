"""Local approval and execution orchestration rules."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from apps.teacher_bridge.database import (
    ApprovalRecord,
    ClassroomSession,
    ExecutionRecord,
    LIFECYCLE_ORDER,
    MotionLifecycle,
    MotionRecord,
)
from apps.teacher_bridge.gateway_client import GatewayClient
from motion_core.errors import ApprovalError, ContractError
from motion_core.schemas import MotionPlan
from motion_core.packages import MotionPackage, verify_package
from motion_core.simulator import TrajectorySimulator


class TeacherBridgeService:
    def __init__(self, session_factory, gateway: GatewayClient) -> None:
        self.session_factory = session_factory
        self.gateway = gateway

    def list_actions(self) -> list[dict]:
        with self.session_factory() as session:
            records = session.scalars(
                select(MotionRecord).where(
                    MotionRecord.lifecycle == MotionLifecycle.CLASSROOM_ENABLED.value
                )
            ).all()
            return [
                {
                    "name": record.motion_id,
                    "version": record.version,
                    "title": record.title,
                    "parameters": record.parameters,
                    "trajectory_sha256": record.trajectory_sha256,
                }
                for record in records
            ]

    def validate_plan(self, payload: dict) -> tuple[MotionPlan | None, list[str]]:
        try:
            plan = MotionPlan.model_validate(payload)
        except Exception as error:
            return None, [str(error)]
        enabled = {action["name"] for action in self.list_actions()}
        return plan, self.gateway.validate_plan(plan, enabled)

    def execute_plan(self, payload: dict, session_id: str, idempotency_key: str) -> str:
        plan, errors = self.validate_plan(payload)
        if plan is None or errors:
            raise ContractError("plan failed bridge validation", details={"errors": errors})
        with self.session_factory() as database:
            classroom = database.scalar(
                select(ClassroomSession).where(ClassroomSession.session_id == session_id)
            )
            if classroom is None or not classroom.enabled or classroom.ended_at is not None:
                raise ApprovalError("an active operator-enabled classroom session is required")
        execution_id = self.gateway.execute_plan(
            plan, operator_enabled=True, idempotency_key=idempotency_key
        )
        with self.session_factory() as database:
            database.add(
                ExecutionRecord(
                    execution_id=execution_id,
                    plan_id=plan.plan_id,
                    session_id=session_id,
                    plan=plan.model_dump(mode="json"),
                )
            )
            database.commit()
        return execution_id

    def transition_motion(
        self, database_id: int, target: MotionLifecycle, approved_by: str, note: str
    ) -> MotionRecord:
        with self.session_factory() as session:
            record = session.get(MotionRecord, database_id)
            if record is None:
                raise LookupError("motion not found")
            current = MotionLifecycle(record.lifecycle)
            if target == MotionLifecycle.REVOKED:
                pass
            elif current == MotionLifecycle.REVOKED:
                raise ApprovalError("revoked motions cannot be restored")
            elif LIFECYCLE_ORDER.index(target) != LIFECYCLE_ORDER.index(current) + 1:
                raise ApprovalError("motion lifecycle transitions cannot be skipped")
            if target in {
                MotionLifecycle.HARDWARE_SMALL_AMPLITUDE_PASSED,
                MotionLifecycle.HARDWARE_FULL_TEMPLATE_PASSED,
                MotionLifecycle.CLASSROOM_ENABLED,
            } and not approved_by.strip():
                raise ApprovalError("on-site teacher identity is required")
            record.lifecycle = target.value
            session.add(
                ApprovalRecord(
                    motion_id=record.id,
                    approval_type=target.value,
                    approved_by=approved_by,
                    approved=True,
                    note=note,
                )
            )
            session.commit()
            return record
    def start_classroom_session(self, session_id: str, operator: str, confirmation: str):
        if confirmation != "ENABLE CLASSROOM MOTION":
            raise ApprovalError("physical operator confirmation phrase is required")
        with self.session_factory() as session:
            existing = session.scalar(
                select(ClassroomSession).where(ClassroomSession.session_id == session_id)
            )
            if existing is not None:
                raise ApprovalError("classroom session_id already exists")
            record = ClassroomSession(session_id=session_id, operator=operator, enabled=True)
            session.add(record)
            session.commit()
            return record

    def stop_classroom_session(self, session_id: str) -> bool:
        with self.session_factory() as session:
            record = session.scalar(
                select(ClassroomSession).where(ClassroomSession.session_id == session_id)
            )
            if record is None or record.ended_at is not None:
                return False
            record.enabled = False
            record.ended_at = datetime.now(timezone.utc)
            session.commit()
            return True

    def validate_package(self, path: Path) -> MotionPackage:
        return verify_package(path)

    def import_package(self, path: Path) -> MotionRecord:
        package = verify_package(path)
        with self.session_factory() as session:
            existing = session.scalar(
                select(MotionRecord).where(
                    MotionRecord.motion_id == package.manifest.package_id,
                    MotionRecord.version == package.manifest.motion_version,
                )
            )
            if existing is not None:
                if existing.package_sha256 != package.archive_sha256:
                    raise ContractError("package id/version already exists with different content")
                return existing
            record = MotionRecord(
                motion_id=package.manifest.package_id,
                version=package.manifest.motion_version,
                title=package.design.title,
                lifecycle=MotionLifecycle.IMPORTED.value,
                trajectory_sha256=package.trajectory.trajectory_sha256,
                package_sha256=package.archive_sha256,
                design=package.design.model_dump(mode="json"),
                cloud_report=package.cloud_report,
            )
            session.add(record)
            session.commit()
            return record

    def simulate_package_local(self, database_id: int, package_path: Path, model_xml: Path | None):
        package = verify_package(package_path)
        with self.session_factory() as session:
            record = session.get(MotionRecord, database_id)
            if record is None:
                raise LookupError("motion not found")
            if record.package_sha256 != package.archive_sha256:
                raise ContractError("selected package does not match imported record")
            report = TrajectorySimulator(model_xml).run(package.trajectory)
            record.local_report = report.model_dump(mode="json")
            if report.passed:
                record.lifecycle = MotionLifecycle.LOCAL_SIMULATION_PASSED.value
            session.commit()
            return report
