"""Fast collision warnings using R1 MJCF collision proxy geoms."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco
import numpy as np


ARM_JOINTS = {
    "left_shoulder_pitch", "left_shoulder_roll", "left_shoulder_yaw", "left_elbow", "left_wrist_roll",
    "right_shoulder_pitch", "right_shoulder_roll", "right_shoulder_yaw", "right_elbow", "right_wrist_roll",
}


@dataclass(frozen=True)
class CollisionSample:
    time_s: float
    minimum_distance_m: float
    closest_pair: tuple[str, str] | None
    contact_count: int
    status: str


def load_collision_model(path: Path) -> tuple[mujoco.MjModel, list[str]]:
    """Load an MJCF after removing only invalid body exclusions for warning mode."""
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    bodies = {element.attrib.get("name") for element in root.iter("body")}
    contact = root.find("contact")
    removed: list[str] = []
    if contact is not None:
        for exclusion in list(contact.findall("exclude")):
            body1, body2 = exclusion.attrib.get("body1"), exclusion.attrib.get("body2")
            if body1 not in bodies or body2 not in bodies:
                removed.append(f"{body1}:{body2}")
                contact.remove(exclusion)
    asset_dir = path.parent / "assets"
    assets = {item.name: item.read_bytes() for item in asset_dir.iterdir() if item.is_file()}
    return mujoco.MjModel.from_xml_string(ET.tostring(root, encoding="unicode"), assets), removed


def _joint_map(model: mujoco.MjModel) -> dict[str, int]:
    result: dict[str, int] = {}
    for index in range(model.njnt):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, index)
        if name and name.endswith("_joint"):
            result[name.removesuffix("_joint")] = index
    return result


def _collision_geoms(model: mujoco.MjModel) -> list[int]:
    return [index for index in range(model.ngeom) if model.geom_contype[index] or model.geom_conaffinity[index]]


def _is_ancestor(model: mujoco.MjModel, ancestor: int, child: int) -> bool:
    current = child
    while current > 0:
        current = int(model.body_parentid[current])
        if current == ancestor:
            return True
    return False


def _status(distance_m: float, contacts: int, warning_m: float, danger_m: float) -> str:
    if contacts:
        return "COLLISION"
    if distance_m < danger_m:
        return "DANGER"
    if distance_m < warning_m:
        return "WARNING"
    return "SAFE"


def scan_action_file(
    model_path: Path,
    action_path: Path,
    *,
    warning_distance_m: float = 0.05,
    danger_distance_m: float = 0.01,
    sample_hz: int = 50,
) -> dict:
    """Scan a named, degree-based multi-joint action against collision proxies."""
    if not 0 < danger_distance_m < warning_distance_m:
        raise ValueError("danger distance must be positive and below warning distance")
    if not 1 <= sample_hz <= 200:
        raise ValueError("sample_hz must be between 1 and 200")
    payload = json.loads(action_path.read_text(encoding="utf-8"))
    name = payload.get("action_name")
    keyframes = payload.get("keyframes")
    if not isinstance(name, str) or not name or not isinstance(keyframes, list) or not keyframes:
        raise ValueError("action file requires action_name and non-empty keyframes")
    if payload.get("units", "degrees") != "degrees":
        raise ValueError("collision warning action files must use degrees")
    model, removed_exclusions = load_collision_model(model_path)
    joints = _joint_map(model)
    requested = set(payload.get("base_pose_deg", {}))
    for frame in keyframes:
        requested.update(frame.get("offsets_deg", {}))
    unknown = sorted(requested - set(joints) - {"waist_yaw", "head_pitch", "head_yaw"})
    if unknown:
        raise ValueError(f"unknown model joints: {unknown}")
    unsupported = sorted(requested - ARM_JOINTS)
    warnings = ["warning-only result; this scan does not authorize hardware execution"]
    if removed_exclusions:
        warnings.append(f"removed {len(removed_exclusions)} invalid MJCF contact exclusions")
    if unsupported:
        warnings.append(f"requested joints are outside arm-only scope: {unsupported}")
    base = {joint: math.radians(float(value)) for joint, value in payload.get("base_pose_deg", {}).items()}
    ordered = sorted(keyframes, key=lambda item: float(item.get("time_s", 0)))
    if any(float(frame.get("time_s", -1)) < 0 for frame in ordered):
        raise ValueError("keyframe time_s must be non-negative")
    if any(float(b["time_s"]) <= float(a["time_s"]) for a, b in zip(ordered, ordered[1:])):
        raise ValueError("keyframe times must be strictly increasing")
    qpos0 = model.qpos0.copy()
    collision_geoms = _collision_geoms(model)
    samples: list[CollisionSample] = []
    frame_time = float(ordered[0]["time_s"])
    end_time = float(ordered[-1]["time_s"])
    while frame_time <= end_time + 1e-9:
        before = ordered[0]
        after = ordered[-1]
        for left, right in zip(ordered, ordered[1:]):
            if float(left["time_s"]) <= frame_time <= float(right["time_s"]):
                before, after = left, right
                break
        span = float(after["time_s"]) - float(before["time_s"])
        ratio = 0.0 if span == 0 else (frame_time - float(before["time_s"])) / span
        qpos = qpos0.copy()
        keys = set(before.get("offsets_deg", {})) | set(after.get("offsets_deg", {})) | set(base)
        for joint in keys:
            if joint not in joints:
                continue
            left = float(before.get("offsets_deg", {}).get(joint, 0.0))
            right = float(after.get("offsets_deg", {}).get(joint, left))
            qpos[model.jnt_qposadr[joints[joint]]] = base.get(joint, 0.0) + math.radians(left + (right - left) * ratio)
        data = mujoco.MjData(model)
        data.qpos[:] = qpos
        mujoco.mj_forward(model, data)
        minimum = float("inf")
        pair: tuple[str, str] | None = None
        for position, geom_a in enumerate(collision_geoms):
            for geom_b in collision_geoms[position + 1:]:
                body_a = int(model.geom_bodyid[geom_a])
                body_b = int(model.geom_bodyid[geom_b])
                if body_a == body_b or _is_ancestor(model, body_a, body_b) or _is_ancestor(model, body_b, body_a):
                    continue
                fromto = np.zeros(6, dtype=np.float64)
                distance = float(mujoco.mj_geomDistance(model, data, geom_a, geom_b, 1.0, fromto))
                if distance < minimum:
                    minimum = distance
                    pair = (
                        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, geom_a) or f"geom_{geom_a}",
                        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, geom_b) or f"geom_{geom_b}",
                    )
        samples.append(CollisionSample(frame_time, minimum, pair, int(data.ncon), _status(minimum, int(data.ncon), warning_distance_m, danger_distance_m)))
        frame_time += 1.0 / sample_hz
    worst = max(samples, key=lambda sample: ({"COLLISION": 4, "DANGER": 3, "WARNING": 2, "SAFE": 1}[sample.status], -sample.minimum_distance_m))
    return {
        "schema_version": "collision-warning/v1",
        "action_name": name,
        "model": str(model_path),
        "mode": "collision_proxies",
        "warning_distance_m": warning_distance_m,
        "danger_distance_m": danger_distance_m,
        "hardware_authorized": False,
        "passed": worst.status == "SAFE",
        "worst_status": worst.status,
        "worst_minimum_distance_m": worst.minimum_distance_m,
        "worst_closest_pair": worst.closest_pair,
        "samples": [sample.__dict__ for sample in samples],
        "warnings": warnings,
    }
