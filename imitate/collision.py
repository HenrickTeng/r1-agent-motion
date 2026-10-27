"""上肢关键帧离线碰撞预警。不连真机，hardware_authorized 恒为 false。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

import mujoco
import numpy as np

from imitate.joints import ARM_JOINTS
from imitate.sim import ArmSim


@dataclass(frozen=True)
class CollisionSample:
    time_s: float
    minimum_distance_m: float
    closest_pair: tuple[str, str] | None
    contact_count: int
    status: str


def _status(distance_m: float, contacts: int, warning_m: float, danger_m: float) -> str:
    if contacts or distance_m < 0:
        return "COLLISION"
    if distance_m < danger_m:
        return "DANGER"
    if distance_m < warning_m:
        return "WARNING"
    return "SAFE"


_UPPER_BODY_TOKENS = (
    "torso",
    "head",
    "shoulder",
    "elbow",
    "wrist",
    "hand",
    "upper",
    "forearm",
)


def _collision_geoms(model: mujoco.MjModel) -> list[int]:
    geoms = []
    for index in range(model.ngeom):
        if not (model.geom_contype[index] or model.geom_conaffinity[index]):
            continue
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, index) or ""
        lowered = name.lower()
        if not any(token in lowered for token in _UPPER_BODY_TOKENS):
            continue
        geoms.append(index)
    return geoms


def _same_arm(name_a: str, name_b: str) -> bool:
    left = name_a.startswith("left_") and name_b.startswith("left_")
    right = name_a.startswith("right_") and name_b.startswith("right_")
    return left or right


def scan_pose(
    sim: ArmSim,
    pose_rad: Mapping[str, float],
    *,
    warning_m: float = 0.03,
    danger_m: float = 0.01,
) -> CollisionSample:
    sim.set_pose(pose_rad)
    model, data = sim.model, sim.data
    geoms = _collision_geoms(model)
    minimum = float("inf")
    pair: tuple[str, str] | None = None
    penetrating = 0
    for i, geom_a in enumerate(geoms):
        for geom_b in geoms[i + 1 :]:
            body_a = int(model.geom_bodyid[geom_a])
            body_b = int(model.geom_bodyid[geom_b])
            if body_a == body_b:
                continue
            if int(model.body_parentid[body_a]) == body_b or int(model.body_parentid[body_b]) == body_a:
                continue
            name_a = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, geom_a) or f"geom_{geom_a}"
            name_b = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, geom_b) or f"geom_{geom_b}"
            if _same_arm(name_a, name_b):
                continue
            fromto = np.zeros(6, dtype=np.float64)
            distance = float(mujoco.mj_geomDistance(model, data, geom_a, geom_b, 1.0, fromto))
            if distance < 0:
                penetrating += 1
            if distance < minimum:
                minimum = distance
                pair = (name_a, name_b)
    return CollisionSample(0.0, minimum, pair, penetrating, _status(minimum, penetrating, warning_m, danger_m))


def interpolate_abs_deg(
    keyframes: Sequence[Mapping],
    time_s: float,
) -> dict[str, float]:
    ordered = sorted(keyframes, key=lambda item: float(item["time_s"]))
    if time_s <= float(ordered[0]["time_s"]):
        return {k: float(v) for k, v in ordered[0]["abs_deg"].items()}
    if time_s >= float(ordered[-1]["time_s"]):
        return {k: float(v) for k, v in ordered[-1]["abs_deg"].items()}
    for left, right in zip(ordered, ordered[1:]):
        t0, t1 = float(left["time_s"]), float(right["time_s"])
        if t0 <= time_s <= t1:
            ratio = 0.0 if t1 == t0 else (time_s - t0) / (t1 - t0)
            keys = set(left["abs_deg"]) | set(right["abs_deg"])
            return {
                name: float(left["abs_deg"].get(name, 0.0))
                + ratio * (float(right["abs_deg"].get(name, left["abs_deg"].get(name, 0.0))) - float(left["abs_deg"].get(name, 0.0)))
                for name in keys
            }
    return {k: float(v) for k, v in ordered[-1]["abs_deg"].items()}


def scan_action(
    sim: ArmSim,
    keyframes: Sequence[Mapping],
    *,
    sample_hz: int = 50,
    warning_m: float = 0.03,
    danger_m: float = 0.01,
) -> dict:
    if not keyframes:
        raise ValueError("keyframes must not be empty")
    ordered = sorted(keyframes, key=lambda item: float(item["time_s"]))
    start, end = float(ordered[0]["time_s"]), float(ordered[-1]["time_s"])
    samples: list[CollisionSample] = []
    t = start
    while t <= end + 1e-9:
        abs_deg = interpolate_abs_deg(ordered, t)
        pose = {name: math.radians(abs_deg[name]) for name in ARM_JOINTS if name in abs_deg}
        sample = scan_pose(sim, pose, warning_m=warning_m, danger_m=danger_m)
        samples.append(CollisionSample(t, sample.minimum_distance_m, sample.closest_pair, sample.contact_count, sample.status))
        t += 1.0 / sample_hz
    rank = {"COLLISION": 4, "DANGER": 3, "WARNING": 2, "SAFE": 1}
    worst = max(samples, key=lambda item: (rank[item.status], -item.minimum_distance_m))
    return {
        "schema_version": "collision-warning/v1",
        "mode": "arm_preview_proxies",
        "hardware_authorized": False,
        "passed": worst.status == "SAFE",
        "worst_status": worst.status,
        "worst_minimum_distance_m": worst.minimum_distance_m,
        "worst_closest_pair": worst.closest_pair,
        "samples": [sample.__dict__ for sample in samples],
        "warnings": ["warning-only result; this scan does not authorize hardware execution"],
    }
