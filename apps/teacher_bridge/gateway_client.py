"""Gateway boundary with an offline mock for development."""

from __future__ import annotations

from typing import Protocol
from uuid import uuid4

from motion_core.schemas import MotionPlan


class GatewayClient(Protocol):
    def get_status(self) -> dict: ...
    def validate_plan(self, plan: MotionPlan, enabled_actions: set[str]) -> list[str]: ...
    def execute_plan(self, plan: MotionPlan, operator_enabled: bool, idempotency_key: str) -> str: ...
    def cancel(self, execution_id: str) -> bool: ...


class MockGatewayClient:
    def __init__(self) -> None:
        self.executions: dict[str, str] = {}

    def get_status(self) -> dict:
        return {
            "connected": False,
            "mode": "mock",
            "fsm_id": None,
            "lowstate_fresh": False,
            "motion_enabled": False,
        }

    def validate_plan(self, plan: MotionPlan, enabled_actions: set[str]) -> list[str]:
        errors = []
        for step in plan.steps:
            if step.type == "action" and step.action not in enabled_actions:
                errors.append(f"action is not classroom_enabled: {step.action}")
        return errors

    def execute_plan(self, plan: MotionPlan, operator_enabled: bool, idempotency_key: str) -> str:
        if not operator_enabled:
            raise PermissionError("operator-enabled classroom session is required")
        if not idempotency_key:
            raise ValueError("idempotency key is required")
        raise ConnectionError("mock gateway never executes hardware")

    def cancel(self, execution_id: str) -> bool:
        if execution_id not in self.executions:
            return False
        self.executions[execution_id] = "cancelled"
        return True
