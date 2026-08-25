"""One-shot, operator-authorized voice tools for staged hardware trials."""

from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Callable
from uuid import uuid4

from motion_core.schemas import MotionPlan


TRIAL_CONFIRMATION = "ENABLE SUPERVISED HARDWARE TRIAL"


class SupervisedHardwareTrialTools:
    def __init__(
        self,
        *,
        action_name: str,
        title: str,
        binary: Path,
        interface: str,
        scale: str,
        authorized_session_id: str,
        confirmation: str,
        runner: Callable = subprocess.run,
    ) -> None:
        if confirmation != TRIAL_CONFIRMATION:
            raise PermissionError("supervised hardware trial confirmation is required")
        if not authorized_session_id.strip():
            raise PermissionError("a supervised hardware trial session_id is required")
        if scale != "full":
            raise ValueError("supervised video trials use only the fixed full profile")
        self.action_name = action_name
        self.title = title
        self.binary = binary
        self.interface = interface
        self.scale = scale
        self.authorized_session_id = authorized_session_id
        self.runner = runner
        self.executed = False
        self.last_output = ""

    def list_actions(self) -> list[dict]:
        return [{"name": self.action_name, "title": self.title, "version": "hardware-trial/v1", "parameters": {}}]

    def validate_plan(self, payload: dict) -> tuple[MotionPlan | None, list[str]]:
        try:
            plan = MotionPlan.model_validate(payload)
        except Exception as error:
            return None, [str(error)]
        if not plan.require_operator_enable:
            return None, ["hardware trial plan must require operator enable"]
        if len(plan.steps) != 1:
            return None, ["hardware trial plan must contain exactly one step"]
        step = plan.steps[0]
        if step.type != "action" or step.action != self.action_name or step.parameters:
            return None, ["plan does not match the one authorized hardware trial"]
        return plan, []

    def execute_plan(self, payload: dict, session_id: str, idempotency_key: str) -> str:
        del idempotency_key
        _, errors = self.validate_plan(payload)
        if errors:
            raise PermissionError("; ".join(errors))
        if session_id != self.authorized_session_id:
            raise PermissionError("hardware trial session_id does not match authorization")
        if self.executed:
            raise PermissionError("this hardware trial process has already executed once")
        if not self.binary.is_file() or not self.binary.stat().st_mode & 0o111:
            raise FileNotFoundError(f"hardware trial binary is not executable: {self.binary}")
        self.executed = True
        completed = self.runner(
            [str(self.binary), self.interface, self.scale],
            input="START\n",
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
        self.last_output = completed.stdout + completed.stderr
        print(self.last_output, end="", flush=True)
        if completed.returncode:
            raise RuntimeError(f"hardware trial failed with exit code {completed.returncode}")
        return f"hardware-trial-{uuid4().hex}"
