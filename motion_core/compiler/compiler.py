"""Compile relative upper-body keyframes into deterministic 100 Hz trajectories."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Callable

import numpy as np

from motion_core.errors import SafetyError
from motion_core.schemas.models import (
    ARM_SDK_JOINTS,
    CompiledTrajectory,
    LimitSummary,
    MotionDesignSpec,
    TrajectorySample,
    content_sha256,
)


TargetSolver = Callable[[MotionDesignSpec], list[tuple[float, np.ndarray]]]


@dataclass(frozen=True)
class SafetyProfile:
    version: str
    sample_hz: int
    require_return: bool
    joints: dict[str, dict]

    @classmethod
    def load(cls, path: Path) -> "SafetyProfile":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            version=payload["version"],
            sample_hz=payload["sample_hz"],
            require_return=payload["require_return"],
            joints=payload["joints"],
        )


def _quintic_blend(progress: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    position = 10 * progress**3 - 15 * progress**4 + 6 * progress**5
    derivative = 30 * progress**2 - 60 * progress**3 + 30 * progress**4
    return position, derivative


class MotionCompiler:
    version = "motion-compiler/1.0.0"

    def __init__(
        self,
        safety_profile_path: Path,
        *,
        model_version: str = "r1-edu-26dof-v1",
        target_solver: TargetSolver | None = None,
    ) -> None:
        self.profile = SafetyProfile.load(safety_profile_path)
        self.model_version = model_version
        self.target_solver = target_solver
        if self.profile.sample_hz != 100:
            raise ValueError("compiled trajectory contract requires a 100 Hz safety profile")

    def compile(self, spec: MotionDesignSpec) -> CompiledTrajectory:
        knots = self._build_knots(spec)
        times, positions, velocities = self._interpolate(knots)
        acceleration = np.gradient(velocities, 1 / self.profile.sample_hz, axis=0)
        jerk = np.gradient(acceleration, 1 / self.profile.sample_hz, axis=0)
        self._validate_limits(positions, velocities, acceleration)
        return_error = float(np.max(np.abs(positions[-1])))
        if self.profile.require_return and return_error > 1e-9:
            raise SafetyError("compiled trajectory does not return to the initial pose")
        samples = [
            TrajectorySample(
                time_s=round(float(time), 6),
                position_rad=tuple(round(float(value), 9) for value in position),
                velocity_rad_s=tuple(round(float(value), 9) for value in velocity),
            )
            for time, position, velocity in zip(times, positions, velocities)
        ]
        summary = LimitSummary(
            maximum_abs_offset_rad=float(np.max(np.abs(positions))),
            maximum_speed_rad_s=float(np.max(np.abs(velocities))),
            maximum_acceleration_rad_s2=float(np.max(np.abs(acceleration))),
            maximum_jerk_rad_s3=float(np.max(np.abs(jerk))),
            return_error_rad=return_error,
        )
        unsigned = {
            "schema_version": "compiled-trajectory/v1",
            "trajectory_id": spec.motion_id,
            "joint_order": ARM_SDK_JOINTS,
            "sample_hz": 100,
            "coordinate_mode": "relative_current",
            "samples": [sample.model_dump(mode="json") for sample in samples],
            "limits": summary.model_dump(mode="json"),
            "compiler_version": self.version,
            "model_version": self.model_version,
            "safety_profile_version": self.profile.version,
        }
        return CompiledTrajectory(**unsigned, trajectory_sha256=content_sha256(unsigned))

    def _build_knots(self, spec: MotionDesignSpec) -> list[tuple[float, np.ndarray]]:
        if spec.end_effector_targets:
            if self.target_solver is None:
                raise SafetyError("end-effector targets require the configured MuJoCo IK solver")
            source = self.target_solver(spec)
        else:
            source = []
            for keyframe in sorted(spec.joint_keyframes, key=lambda frame: frame.time_s):
                vector = np.zeros(len(ARM_SDK_JOINTS), dtype=np.float64)
                for offset in keyframe.offsets:
                    vector[ARM_SDK_JOINTS.index(offset.joint)] = offset.offset_rad
                source.append((keyframe.time_s, vector))
                if keyframe.hold_s:
                    source.append((keyframe.time_s + keyframe.hold_s, vector.copy()))
        if not source:
            raise SafetyError("motion contains no compilable targets")
        knots: list[tuple[float, np.ndarray]] = [(0.0, np.zeros(13, dtype=np.float64))]
        for time_s, vector in source:
            adjusted_time = max(float(time_s), knots[-1][0] + 0.01)
            knots.append((adjusted_time, np.asarray(vector, dtype=np.float64)))
        return_time = knots[-1][0] + spec.return_policy.duration_s
        knots.append((return_time, np.zeros(13, dtype=np.float64)))
        return knots

    def _interpolate(
        self, knots: list[tuple[float, np.ndarray]]
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        sample_period = 1 / self.profile.sample_hz
        final_time = knots[-1][0]
        sample_count = round(final_time * self.profile.sample_hz) + 1
        times = np.arange(sample_count, dtype=np.float64) * sample_period
        times[-1] = final_time
        positions = np.zeros((sample_count, 13), dtype=np.float64)
        velocities = np.zeros_like(positions)
        for start_index, ((start_time, start), (end_time, end)) in enumerate(zip(knots, knots[1:])):
            mask = (times >= start_time) & (times <= end_time)
            if start_index:
                mask &= times > start_time
            duration = end_time - start_time
            progress = np.clip((times[mask] - start_time) / duration, 0, 1)
            blend, derivative = _quintic_blend(progress)
            delta = end - start
            positions[mask] = start + blend[:, None] * delta
            velocities[mask] = derivative[:, None] * delta / duration
        return times, positions, velocities

    def _validate_limits(
        self, positions: np.ndarray, velocities: np.ndarray, acceleration: np.ndarray
    ) -> None:
        for index, name in enumerate(ARM_SDK_JOINTS):
            rules = self.profile.joints[name]
            maximum_offset = float(np.max(np.abs(positions[:, index])))
            if maximum_offset > 1e-10 and not rules["enabled"]:
                raise SafetyError(f"joint {name} has not completed hardware calibration")
            checks = (
                (maximum_offset, rules["max_offset_rad"], "offset"),
                (float(np.max(np.abs(velocities[:, index]))), rules["max_speed_rad_s"], "speed"),
                (
                    float(np.max(np.abs(acceleration[:, index]))),
                    rules["max_accel_rad_s2"],
                    "acceleration",
                ),
            )
            for observed, allowed, label in checks:
                if observed > allowed + 1e-8:
                    raise SafetyError(
                        f"joint {name} {label} exceeds classroom-upper-v1",
                        details={"observed": observed, "allowed": allowed},
                    )
