"""FastAPI routes exposed only on the teacher computer loopback interface."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict

from apps.teacher_bridge.database import MotionLifecycle, create_session_factory
from apps.teacher_bridge.gateway_client import GatewayClient, MockGatewayClient
from apps.teacher_bridge.service import TeacherBridgeService
from motion_core.config import Settings
from motion_core.errors import R1MotionError
from motion_core.library import seed_action_library


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlanRequest(StrictRequest):
    plan: dict
    session_id: str | None = None


class CancelRequest(StrictRequest):
    execution_id: str


class TransitionRequest(StrictRequest):
    target: MotionLifecycle
    approved_by: str
    note: str = ""


class ClassroomSessionRequest(StrictRequest):
    session_id: str
    operator: str
    confirmation: str


class PackagePathRequest(StrictRequest):
    path: str


class LocalSimulationRequest(StrictRequest):
    package_path: str
    model_xml: str | None = None


def create_app(database_url: str | None = None, gateway: GatewayClient | None = None) -> FastAPI:
    settings = Settings.from_env()
    session_factory = create_session_factory(database_url or settings.database_url)
    seed_action_library(session_factory)
    service = TeacherBridgeService(session_factory, gateway or MockGatewayClient())
    app = FastAPI(title="R1 Teacher Bridge", version="1.0.0")
    app.state.service = service

    @app.get("/healthz")
    def health() -> dict:
        return {"status": "ok", "binding": "loopback-only"}

    @app.get("/v1/robot/status")
    def robot_get_status() -> dict:
        return service.gateway.get_status()

    @app.get("/v1/robot/actions")
    def robot_list_actions() -> dict:
        return {"actions": service.list_actions()}

    @app.post("/v1/robot/plans:validate")
    def robot_validate_plan(request: PlanRequest) -> dict:
        plan, errors = service.validate_plan(request.plan)
        return {"valid": plan is not None and not errors, "errors": errors, "motion_sent": False}

    @app.post("/v1/robot/plans:execute")
    def robot_execute_plan(
        request: PlanRequest, idempotency_key: str = Header(alias="Idempotency-Key")
    ) -> dict:
        if not request.session_id:
            raise HTTPException(403, "session_id is required")
        try:
            execution_id = service.execute_plan(request.plan, request.session_id, idempotency_key)
        except R1MotionError as error:
            raise HTTPException(403, error.as_dict()) from error
        except ConnectionError as error:
            raise HTTPException(503, str(error)) from error
        return {"execution_id": execution_id}

    @app.post("/v1/robot/executions:cancel")
    def robot_cancel(request: CancelRequest) -> dict:
        return {"cancelled": service.gateway.cancel(request.execution_id)}

    @app.post("/v1/classroom-sessions")
    def start_classroom_session(request: ClassroomSessionRequest) -> dict:
        try:
            record = service.start_classroom_session(
                request.session_id, request.operator, request.confirmation
            )
        except R1MotionError as error:
            raise HTTPException(403, error.as_dict()) from error
        return {"session_id": record.session_id, "enabled": record.enabled}

    @app.delete("/v1/classroom-sessions/{session_id}")
    def stop_classroom_session(session_id: str) -> dict:
        return {"stopped": service.stop_classroom_session(session_id)}

    @app.post("/v1/motions/{database_id}:transition")
    def motion_transition(database_id: int, request: TransitionRequest) -> dict:
        try:
            record = service.transition_motion(
                database_id, request.target, request.approved_by, request.note
            )
        except LookupError as error:
            raise HTTPException(404, str(error)) from error
        except R1MotionError as error:
            raise HTTPException(409, error.as_dict()) from error
        return {"id": record.id, "lifecycle": record.lifecycle}

    @app.post("/v1/motions/packages:validate")
    def motion_validate_package(request: PackagePathRequest) -> dict:
        try:
            package = service.validate_package(Path(request.path))
        except R1MotionError as error:
            raise HTTPException(422, error.as_dict()) from error
        return {
            "valid": True,
            "package_id": package.manifest.package_id,
            "archive_sha256": package.archive_sha256,
            "source_authenticated": False,
            "notice": package.manifest.integrity_notice,
        }

    @app.post("/v1/motions/packages:import")
    def motion_import_package(request: PackagePathRequest) -> dict:
        try:
            record = service.import_package(Path(request.path))
        except R1MotionError as error:
            raise HTTPException(422, error.as_dict()) from error
        return {"id": record.id, "lifecycle": record.lifecycle, "package_sha256": record.package_sha256}

    @app.post("/v1/motions/{database_id}:simulate-local")
    def motion_simulate_local(database_id: int, request: LocalSimulationRequest) -> dict:
        try:
            report = service.simulate_package_local(
                database_id,
                Path(request.package_path),
                Path(request.model_xml) if request.model_xml else None,
            )
        except LookupError as error:
            raise HTTPException(404, str(error)) from error
        except R1MotionError as error:
            raise HTTPException(409, error.as_dict()) from error
        return report.model_dump(mode="json")

    return app


app = create_app()
