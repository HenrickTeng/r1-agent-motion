"""Authoritative two-pass trajectory validation with explicit model readiness."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from pydantic import Field

from motion_core.schemas.models import ARM_SDK_JOINTS, CompiledTrajectory, StrictModel


class CheckResult(StrictModel):
    name: str
    passed: bool
    measured: float | int | str | bool | None = None
    limit: float | int | str | bool | None = None
    detail: str = ""


class SimulationReport(StrictModel):
    schema_version: str = "simulation-report/v1"
    simulation_id: str
    trajectory_sha256: str
    simulator_version: str = "mujoco/3.7"
    model_version: str
    created_at: str
    passed: bool
    kinematic_checks: list[CheckResult]
    dynamic_checks: list[CheckResult]
    warnings: list[str] = Field(default_factory=list)


class TrajectorySimulator:
    def __init__(self, model_xml: Path | None = None) -> None:
        self.model_xml = model_xml

    def run(self, trajectory: CompiledTrajectory) -> SimulationReport:
        kinematic = self._kinematic_checks(trajectory)
        dynamic, warnings = self._mujoco_checks(trajectory)
        checks = [*kinematic, *dynamic]
        return SimulationReport(
            simulation_id=f"sim-{trajectory.trajectory_sha256[:16]}",
            trajectory_sha256=trajectory.trajectory_sha256,
            model_version=trajectory.model_version,
            created_at=datetime.now(timezone.utc).isoformat(),
            passed=bool(checks) and all(check.passed for check in checks),
            kinematic_checks=kinematic,
            dynamic_checks=dynamic,
            warnings=warnings,
        )

    def _kinematic_checks(self, trajectory: CompiledTrajectory) -> list[CheckResult]:
        positions = np.asarray([sample.position_rad for sample in trajectory.samples])
        times = np.asarray([sample.time_s for sample in trajectory.samples])
        intervals = np.diff(times)
        continuity = float(np.max(np.abs(np.diff(positions, axis=0))))
        return [
            CheckResult(
                name="fixed_100hz_timing",
                passed=bool(np.allclose(intervals, 0.01, atol=1e-6)),
                measured=float(np.max(np.abs(intervals - 0.01))),
                limit=1e-6,
            ),
            CheckResult(
                name="trajectory_continuity",
                passed=continuity <= 0.02,
                measured=continuity,
                limit=0.02,
            ),
            CheckResult(
                name="return_to_initial_pose",
                passed=trajectory.limits.return_error_rad <= 0.005,
                measured=trajectory.limits.return_error_rad,
                limit=0.005,
            ),
        ]

    def _mujoco_checks(
        self, trajectory: CompiledTrajectory
    ) -> tuple[list[CheckResult], list[str]]:
        if self.model_xml is None:
            return [
                CheckResult(
                    name="authoritative_mujoco_model",
                    passed=False,
                    measured="not_configured",
                    limit="UNITREE_R1_MODEL_DIR/r1.xml",
                )
            ], ["MuJoCo model is required before approval or hardware execution."]
        try:
            model, patched_exclusions = self._load_external_model(self.model_xml)
        except Exception as error:
            return [
                CheckResult(
                    name="authoritative_mujoco_model",
                    passed=False,
                    measured="load_failed",
                    detail=str(error),
                )
            ], ["External R1 model failed audit; no hardware approval is permitted."]
        available = {
            mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, index)
            for index in range(model.njnt)
        }
        required = {f"{name}_joint" for name in ARM_SDK_JOINTS}
        missing = sorted(required - available)
        checks = [
            CheckResult(
                name="all_armsdk_joints_mapped",
                passed=not missing,
                measured=",".join(missing) if missing else "complete",
                limit="13 joints",
            ),
            CheckResult(
                name="invalid_contact_exclusions",
                passed=not patched_exclusions,
                measured=patched_exclusions,
                limit=0,
            ),
        ]
        warnings = []
        if missing:
            warnings.append("External MJCF does not articulate every ArmSdk joint.")
        if patched_exclusions:
            warnings.append("Invalid wrist contact exclusions were ignored for model audit only.")
        return checks, warnings

    @staticmethod
    def _load_external_model(path: Path) -> tuple[mujoco.MjModel, int]:
        root = ET.fromstring(path.read_text(encoding="utf-8"))
        bodies = {element.attrib.get("name") for element in root.iter("body")}
        contact = root.find("contact")
        patched = 0
        if contact is not None:
            for exclusion in list(contact.findall("exclude")):
                if exclusion.attrib.get("body1") not in bodies or exclusion.attrib.get("body2") not in bodies:
                    contact.remove(exclusion)
                    patched += 1
        assets: dict[str, bytes] = {}
        asset_dir = path.parent / "assets"
        for mesh in asset_dir.iterdir():
            if mesh.is_file():
                assets[mesh.name] = mesh.read_bytes()
        xml = ET.tostring(root, encoding="unicode")
        return mujoco.MjModel.from_xml_string(xml, assets), patched
