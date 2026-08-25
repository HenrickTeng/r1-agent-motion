"""Versioned action registry and database seeding."""

import json
from pathlib import Path

from motion_core.schemas import MotionPlan

DEFAULT_LIBRARY = Path(__file__).resolve().parents[1] / "motion-library" / "actions.json"


def load_action_library(path: Path = DEFAULT_LIBRARY) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "action-library/v1" or not isinstance(payload.get("actions"), list):
        raise ValueError("unsupported action library")
    names = [action["name"] for action in payload["actions"]]
    if len(names) != len(set(names)):
        raise ValueError("action names must be unique")
    known = set(names)
    for action in payload["actions"]:
        if action.get("kind") == "locomotion_macro":
            MotionPlan.model_validate({
                "schema_version": "motion-plan/v2",
                "plan_id": f"macro-{action['name']}",
                "steps": action.get("plan_template", []),
                "require_operator_enable": True,
            })
            if action.get("parameters"):
                raise ValueError("locomotion macros cannot expose raw runtime parameters")
        for step in action.get("steps", []):
            if not step.startswith("say:") and step not in known:
                raise ValueError(f"composition references unknown action: {step}")
    return payload


def seed_action_library(session_factory, path: Path = DEFAULT_LIBRARY) -> int:
    from sqlalchemy import select

    from apps.teacher_bridge.database import MotionRecord

    added = 0
    with session_factory() as session:
        for action in load_action_library(path)["actions"]:
            existing = session.scalar(
                select(MotionRecord).where(
                    MotionRecord.motion_id == action["name"], MotionRecord.version == action["version"]
                )
            )
            if existing is not None:
                continue
            session.add(
                MotionRecord(
                    motion_id=action["name"], version=action["version"], title=action["title"],
                    lifecycle=action["lifecycle"], parameters=action.get("parameters", {}), design=action,
                )
            )
            added += 1
        session.commit()
    return added


def expand_locomotion_macros(plan: MotionPlan, enabled_registry: dict[str, dict]) -> MotionPlan:
    steps = []
    for step in plan.steps:
        action = enabled_registry.get(step.action) if step.type == "action" else None
        if action and action.get("kind") == "locomotion_macro":
            if step.parameters:
                raise ValueError("locomotion macros accept no runtime parameters")
            steps.extend(action["plan_template"])
        else:
            steps.append(step.model_dump(mode="json"))
    return MotionPlan.model_validate({
        "schema_version": plan.schema_version,
        "plan_id": plan.plan_id,
        "steps": steps,
        "require_operator_enable": True,
    })
