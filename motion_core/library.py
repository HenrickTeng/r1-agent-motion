"""Versioned action registry and database seeding."""

import json
from pathlib import Path

DEFAULT_LIBRARY = Path(__file__).resolve().parents[1] / "motion-library" / "actions.json"


def load_action_library(path: Path = DEFAULT_LIBRARY) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "action-library/v1" or not isinstance(payload.get("actions"), list):
        raise ValueError("unsupported action library")
    names = [action["name"] for action in payload["actions"]]
    if len(names) != len(set(names)):
        raise ValueError("action names must be unique")
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
