"""Strict Pydantic representations of public R1 Motion contracts."""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ARM_SDK_JOINTS = (
    "left_shoulder_pitch",
    "left_shoulder_roll",
    "left_shoulder_yaw",
    "left_elbow",
    "left_wrist_roll",
    "right_shoulder_pitch",
    "right_shoulder_roll",
    "right_shoulder_yaw",
    "right_elbow",
    "right_wrist_roll",
    "waist_yaw",
    "head_pitch",
    "head_yaw",
)
ArmJointName = Literal[
    "left_shoulder_pitch",
    "left_shoulder_roll",
    "left_shoulder_yaw",
    "left_elbow",
    "left_wrist_roll",
    "right_shoulder_pitch",
    "right_shoulder_roll",
    "right_shoulder_yaw",
    "right_elbow",
    "right_wrist_roll",
    "waist_yaw",
    "head_pitch",
    "head_yaw",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JointOffset(StrictModel):
    joint: ArmJointName
    offset_rad: float


class JointKeyframe(StrictModel):
    time_s: float = Field(ge=0, le=30)
    offsets: list[JointOffset] = Field(min_length=1, max_length=13)
    hold_s: float = Field(default=0, ge=0, le=5)

    @model_validator(mode="after")
    def unique_joints(self) -> "JointKeyframe":
        names = [offset.joint for offset in self.offsets]
        if len(names) != len(set(names)):
            raise ValueError("keyframe joints must be unique")
        return self


class EndEffectorTarget(StrictModel):
    side: Literal["left", "right"]
    time_s: float = Field(ge=0, le=30)
    frame: Literal["torso"] = "torso"
    position_m: tuple[float, float, float]
    quaternion_wxyz: tuple[float, float, float, float] | None = None


class ReturnPolicy(StrictModel):
    mode: Literal["return_to_initial"] = "return_to_initial"
    duration_s: float = Field(default=1.5, ge=0.8, le=5)


class MotionDesignSpec(StrictModel):
    schema_version: Literal["motion-design-spec/v1"]
    motion_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")
    title: str = Field(min_length=1, max_length=80)
    intent: str = Field(min_length=1, max_length=500)
    scope: Literal["upper_body"] = "upper_body"
    initial_pose_binding: Literal["relative_current"] = "relative_current"
    joint_keyframes: list[JointKeyframe] = Field(default_factory=list, max_length=100)
    end_effector_targets: list[EndEffectorTarget] = Field(default_factory=list, max_length=100)
    repeat: int = Field(default=1, ge=1, le=3)
    tempo: Literal["slow", "normal"] = "slow"
    return_policy: ReturnPolicy = Field(default_factory=ReturnPolicy)
    safety_profile: Literal["classroom-upper-v1"] = "classroom-upper-v1"

    @model_validator(mode="after")
    def require_targets(self) -> "MotionDesignSpec":
        if not self.joint_keyframes and not self.end_effector_targets:
            raise ValueError("at least one keyframe or end-effector target is required")
        return self


class TrajectorySample(StrictModel):
    time_s: float = Field(ge=0)
    position_rad: tuple[float, ...]
    velocity_rad_s: tuple[float, ...]

    @model_validator(mode="after")
    def fixed_width(self) -> "TrajectorySample":
        if len(self.position_rad) != 13 or len(self.velocity_rad_s) != 13:
            raise ValueError("trajectory samples must contain exactly 13 joints")
        return self


class LimitSummary(StrictModel):
    maximum_abs_offset_rad: float = Field(ge=0)
    maximum_speed_rad_s: float = Field(ge=0)
    maximum_acceleration_rad_s2: float = Field(ge=0)
    maximum_jerk_rad_s3: float = Field(ge=0)
    return_error_rad: float = Field(ge=0)


class CompiledTrajectory(StrictModel):
    schema_version: Literal["compiled-trajectory/v1"]
    trajectory_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")
    joint_order: tuple[ArmJointName, ...]
    sample_hz: Literal[100] = 100
    coordinate_mode: Literal["relative_current"] = "relative_current"
    samples: list[TrajectorySample] = Field(min_length=2)
    limits: LimitSummary
    compiler_version: str
    model_version: str
    safety_profile_version: str
    trajectory_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def fixed_order_and_time(self) -> "CompiledTrajectory":
        if tuple(self.joint_order) != ARM_SDK_JOINTS:
            raise ValueError("joint_order must match the fixed ArmSdk order")
        times = [sample.time_s for sample in self.samples]
        if any(current <= previous for previous, current in zip(times, times[1:])):
            raise ValueError("sample times must be strictly increasing")
        return self


class SayStep(StrictModel):
    type: Literal["say"]
    text: str = Field(min_length=1, max_length=200)


class ActionStep(StrictModel):
    type: Literal["action"]
    action: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    parameters: dict[str, str | int | float | bool] = Field(default_factory=dict)


class MoveForStep(StrictModel):
    type: Literal["move_for"]
    vx_mps: float = Field(ge=-0.3, le=0.5)
    vy_mps: float = Field(ge=-0.10, le=0.10)
    duration_s: float = Field(gt=0, le=2)


class TurnRelativeStep(StrictModel):
    type: Literal["turn_relative"]
    angle_deg: float = Field(ge=-30, le=30)


class WaitStep(StrictModel):
    type: Literal["wait"]
    duration_s: float = Field(ge=0.1, le=10)


PlanStep = Annotated[
    SayStep | ActionStep | MoveForStep | TurnRelativeStep | WaitStep,
    Field(discriminator="type"),
]


class MotionPlan(StrictModel):
    schema_version: Literal["motion-plan/v2"]
    plan_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{2,63}$")
    steps: list[PlanStep] = Field(min_length=1, max_length=16)
    require_operator_enable: Literal[True] = True

    @model_validator(mode="after")
    def reject_concurrent_control(self) -> "MotionPlan":
        if not any(isinstance(step, ActionStep) for step in self.steps):
            return self
        return self


class PackageFile(StrictModel):
    path: Literal[
        "motion-design.json",
        "trajectory.json",
        "cloud-simulation-report.json",
        "preview-animation.json",
    ]
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=2, le=20_000_000)


class MotionPackageManifest(StrictModel):
    schema_version: Literal["motion-package/v1"]
    package_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")
    motion_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    created_at: str
    platform_approval_id: str = Field(min_length=1, max_length=128)
    files: list[PackageFile] = Field(min_length=4, max_length=4)
    integrity_notice: Literal[
        "SHA256 integrity verified; source identity is not cryptographically authenticated."
    ]

    @model_validator(mode="after")
    def exact_files(self) -> "MotionPackageManifest":
        required = {
            "motion-design.json",
            "trajectory.json",
            "cloud-simulation-report.json",
            "preview-animation.json",
        }
        if {item.path for item in self.files} != required:
            raise ValueError("manifest must contain each required package file exactly once")
        return self


def canonical_json(value: BaseModel | dict) -> bytes:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def content_sha256(value: BaseModel | dict) -> str:
    return sha256(canonical_json(value)).hexdigest()
