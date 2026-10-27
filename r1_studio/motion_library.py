"""人机联动动作组：与平台 poseMotion 同一份导出 JSON。

浏览器里的姿态是弧度。导出文件用角度，schema 为 r1-arm-imitate-mirror/v1，
angle_convention 为 eduplatform-r1-mjcf/v1。肘关节按官方模型记录（约 76° 为伸直）；
发给真机 arm_sdk 之前再换回本机跟臂用的人体系角度。其余关节沿用跟臂指令角。
"""

from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from imitate.joints import ARM_JOINTS, LIMITS_RAD, READY_POSE_DEG, clip_rad

SCHEMA = "r1-arm-imitate-mirror/v1"
ANGLE_CONVENTION = "eduplatform-r1-mjcf/v1"
LIBRARY_SCHEMA = "r1-motion-library/v1"
MAX_FRAMES = 500
_OFFICIAL_ELBOW_STRAIGHT_DEG = 76.0
_HUMAN_ELBOW_READY_DEG = 45.0
_ELBOWS = {"left_elbow", "right_elbow"}


class MotionError(ValueError):
    pass


def _round(value: float) -> float:
    return round(float(value), 6)


def human_elbow_to_official_deg(human_deg: float, ready_deg: float) -> float:
    return _OFFICIAL_ELBOW_STRAIGHT_DEG + float(human_deg) * (
        float(ready_deg) - _OFFICIAL_ELBOW_STRAIGHT_DEG
    ) / _HUMAN_ELBOW_READY_DEG


def official_elbow_to_human_deg(official_deg: float, ready_deg: float) -> float:
    span = float(ready_deg) - _OFFICIAL_ELBOW_STRAIGHT_DEG
    return (float(official_deg) - _OFFICIAL_ELBOW_STRAIGHT_DEG) * _HUMAN_ELBOW_READY_DEG / span


def human_deg_to_official(pose_deg: Mapping[str, float]) -> dict[str, float]:
    out = {}
    for name in ARM_JOINTS:
        value = float(pose_deg[name])
        if name in _ELBOWS:
            value = human_elbow_to_official_deg(value, READY_POSE_DEG[name])
        out[name] = _round(value)
    return out


def official_deg_to_human(abs_deg: Mapping[str, float]) -> dict[str, float]:
    out = {}
    for name in ARM_JOINTS:
        value = float(abs_deg[name])
        if name in _ELBOWS:
            value = official_elbow_to_human_deg(value, READY_POSE_DEG[name])
        out[name] = _round(math.degrees(clip_rad(name, math.radians(value))))
    return out


def clip_human_deg(pose_deg: Mapping[str, float]) -> dict[str, float]:
    out = {}
    for name in ARM_JOINTS:
        if name not in pose_deg:
            raise MotionError("关键帧必须包含 10 个关节角度。")
        rad = clip_rad(name, math.radians(float(pose_deg[name])))
        lo, hi = LIMITS_RAD[name]
        if rad < lo - 1e-6 or rad > hi + 1e-6:
            raise MotionError(f"{name} 超出关节限位。")
        out[name] = _round(math.degrees(rad))
    return out


def _check_interval(index: int, interval: float) -> float:
    interval = float(interval)
    if index == 0:
        if abs(interval) > 1e-9:
            raise MotionError("第一帧从 0 秒开始。")
        return 0.0
    if not math.isfinite(interval) or interval < 0.05 or interval > 3600:
        raise MotionError("后续帧间时长需要在 0.05–3600 秒之间。")
    return _round(interval)


def timeline(frames: list[dict]) -> list[float]:
    time = 0.0
    out = []
    for index, frame in enumerate(frames):
        time = _round(time + (float(frame["interval"]) if index else 0.0))
        out.append(time)
    return out


def sample_human_deg(frames: list[dict], seconds: float) -> dict[str, float]:
    if not frames:
        raise MotionError("动作组为空。")
    times = timeline(frames)
    seconds = max(0.0, float(seconds))
    if len(frames) == 1 or seconds >= times[-1]:
        return dict(frames[-1]["pose_deg"])
    next_index = next(i for i, time in enumerate(times) if time > seconds)
    previous = max(0, next_index - 1)
    span = times[next_index] - times[previous]
    alpha = 0.0 if span <= 0 else (seconds - times[previous]) / span
    left = frames[previous]["pose_deg"]
    right = frames[next_index]["pose_deg"]
    return {
        name: _round(float(left[name]) + (float(right[name]) - float(left[name])) * alpha)
        for name in ARM_JOINTS
    }


def human_deg_to_rad(pose_deg: Mapping[str, float]) -> dict[str, float]:
    return {name: math.radians(float(pose_deg[name])) for name in ARM_JOINTS}


def export_motion(group: Mapping) -> dict:
    name = str(group.get("name") or "").strip()
    if not name or len(name) > 40:
        raise MotionError("请输入 1–40 字的动作组名称。")
    frames = list(group.get("frames") or [])
    if not frames or len(frames) > MAX_FRAMES:
        raise MotionError(f"动作组需要 1–{MAX_FRAMES} 个关键帧。")
    cleaned = []
    for index, frame in enumerate(frames):
        pose = clip_human_deg(frame.get("pose_deg") or {})
        interval = _check_interval(index, frame.get("interval") or 0)
        captured = str(frame.get("captured_at") or "")
        if not captured:
            raise MotionError("关键帧采集时间无效。")
        try:
            datetime.fromisoformat(captured.replace("Z", "+00:00"))
        except ValueError as error:
            raise MotionError("关键帧采集时间无效。") from error
        source = frame.get("source") if frame.get("source") in ("camera", "demo", "simulation") else "simulation"
        cleaned.append(
            {
                "interval": interval,
                "captured_at": captured,
                "source": source,
                "mirror": bool(frame.get("mirror", True)),
                "pose_deg": pose,
            }
        )
    times = timeline(cleaned)
    modes = {frame["mirror"] for frame in cleaned}
    if len(modes) > 1:
        laterality = "mixed_per_keyframe"
    elif cleaned[0]["mirror"]:
        laterality = "selfie_mirror_user_right_is_robot_left"
    else:
        laterality = "anatomical_same_side"
    keyframes = []
    for index, frame in enumerate(cleaned):
        official = human_deg_to_official(frame["pose_deg"])
        keyframes.append(
            {
                "time_s": times[index],
                "transition_s": frame["interval"],
                "captured_at": frame["captured_at"],
                "source": frame["source"],
                "mirror": frame["mirror"],
                "abs_deg": official,
                "offsets_deg": {
                    joint: _round(official[joint] - READY_POSE_DEG[joint]) for joint in ARM_JOINTS
                },
            }
        )
    return {
        "schema_version": SCHEMA,
        "laterality": laterality,
        "action_name": str(group.get("id") or uuid.uuid4()),
        "title": name,
        "aliases": [name],
        "kind": "arm",
        "units": "degrees",
        "hardware_authorized": False,
        "angle_convention": ANGLE_CONVENTION,
        "base_pose_deg": {joint: READY_POSE_DEG[joint] for joint in ARM_JOINTS},
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "keyframes": keyframes,
        "collision": {"checked": False, "hardware_authorized": False},
        "not_agent_catalog": (
            "Simulation only. Platform MJCF angles, not hardware encoder commands. "
            "Do not add to actions.json or MOTIONS."
        ),
    }


def import_motion(payload: Mapping) -> dict:
    if (
        payload.get("schema_version") != SCHEMA
        or payload.get("units") != "degrees"
        or payload.get("kind") != "arm"
    ):
        raise MotionError("不是支持的 R1 上肢动作文件。")
    if payload.get("angle_convention") != ANGLE_CONVENTION:
        raise MotionError("角度坐标约定不一致，不能直接回放外部真机或其他模型的动作。")
    keyframes = payload.get("keyframes")
    if not isinstance(keyframes, list) or not keyframes or len(keyframes) > MAX_FRAMES:
        raise MotionError("关键帧列表无效或超过 500 帧。")
    title = str(payload.get("title") or "").strip()
    if not title or len(title) > 40:
        raise MotionError("动作组名称无效。")
    frames = []
    previous = 0.0
    for index, frame in enumerate(keyframes):
        if not isinstance(frame, Mapping):
            raise MotionError("关键帧格式不对。")
        time_s = frame.get("time_s")
        if not isinstance(time_s, (int, float)) or not math.isfinite(float(time_s)):
            raise MotionError("动作时间轴无效。")
        if index == 0 and float(time_s) != 0:
            raise MotionError("动作时间轴无效。")
        interval = _round(float(time_s) - previous)
        previous = float(time_s)
        transition = frame.get("transition_s")
        if transition is not None and abs(float(transition) - interval) > 1e-4:
            raise MotionError("帧间时长与时间轴不一致。")
        raw_deg = frame.get("abs_deg") or {}
        abs_deg = {}
        if isinstance(raw_deg, Mapping):
            for name in ARM_JOINTS:
                if name in raw_deg:
                    abs_deg[name] = raw_deg[name]
                elif f"{name}_joint" in raw_deg:
                    abs_deg[name] = raw_deg[f"{name}_joint"]
        if len(abs_deg) != len(ARM_JOINTS):
            raise MotionError("关键帧需要完整的 10 个角度。")
        pose = official_deg_to_human(abs_deg)
        _check_interval(index, interval)
        frames.append(
            {
                "interval": interval,
                "captured_at": str(frame.get("captured_at") or datetime.now(timezone.utc).isoformat()),
                "source": frame.get("source") if frame.get("source") in ("camera", "demo", "simulation") else "simulation",
                "mirror": frame.get("mirror") is True,
                "pose_deg": pose,
            }
        )
    return {
        "id": str(payload.get("action_name") or uuid.uuid4()),
        "name": title,
        "frames": frames,
    }


def load_library(path: Path) -> list[dict]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    groups = payload.get("groups") if isinstance(payload, dict) else None
    if not isinstance(groups, list):
        raise MotionError("动作库文件格式不对。")
    return [import_motion(item) for item in groups]


def save_library(path: Path, groups: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exported = [export_motion(group) for group in groups]
    path.write_text(
        json.dumps({"schema": LIBRARY_SCHEMA, "groups": exported}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def summarize(groups: list[dict]) -> list[dict]:
    return [
        {"id": group["id"], "name": group["name"], "frames": len(group["frames"])}
        for group in groups
    ]
