"""Separate execute-mode from design-mode and enforce one repair attempt."""

from typing import Protocol

from motion_core.agent.adapters import ModelAdapter
from motion_core.agent.models import AgentResponse


class AgentTools(Protocol):
    def list_actions(self) -> list[dict]: ...
    def validate_plan(self, payload: dict) -> tuple[object | None, list[str]]: ...
    def execute_plan(self, payload: dict, session_id: str, idempotency_key: str) -> str: ...


class AgentService:
    def __init__(self, adapter: ModelAdapter, tools: AgentTools) -> None:
        self.adapter = adapter
        self.tools = tools

    def handle(self, text: str, *, mode: str = "execute", session_id: str | None = None, idempotency_key: str = "", execute: bool = False) -> dict:
        if mode not in {"execute", "design"}:
            raise ValueError("mode must be execute or design")
        response = self._validated_completion(text, mode, self.tools.list_actions())
        result = response.model_dump(mode="json")
        result["motion_sent"] = False
        if response.intent == "execute_motion":
            _, errors = self.tools.validate_plan(response.plan.model_dump(mode="json"))
            if errors:
                result.update(reply="动作计划没有通过本地安全校验，因此不会执行。", validation_errors=errors, plan=None)
                return result
            if execute:
                if not session_id:
                    raise PermissionError("operator-enabled session_id is required")
                result["execution_id"] = self.tools.execute_plan(response.plan.model_dump(mode="json"), session_id, idempotency_key)
                result["motion_sent"] = True
        return result

    def _validated_completion(self, text: str, mode: str, actions: list[dict]) -> AgentResponse:
        first = self.adapter.complete(text, mode=mode, enabled_actions=actions)
        try:
            response = AgentResponse.model_validate(first)
            self._validate_mode(response, mode)
            return response
        except Exception as first_error:
            repaired = self.adapter.complete(text, mode=mode, enabled_actions=actions, repair=str(first_error))
            response = AgentResponse.model_validate(repaired)
            self._validate_mode(response, mode)
            return response

    @staticmethod
    def _validate_mode(response: AgentResponse, mode: str) -> None:
        if mode == "execute" and response.intent == "design_motion":
            raise ValueError("execute mode cannot design trajectories")
        if mode == "design" and response.intent == "execute_motion":
            raise ValueError("design mode cannot produce execution plans")
