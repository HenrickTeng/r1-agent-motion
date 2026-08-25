"""Export authoritative JSON Schema 2020-12 documents."""

import json
from pathlib import Path

from motion_core.schemas.models import (
    CompiledTrajectory,
    MotionDesignSpec,
    MotionPackageManifest,
    MotionPlan,
)


MODELS = {
    "motion-design-spec-v1.schema.json": MotionDesignSpec,
    "compiled-trajectory-v1.schema.json": CompiledTrajectory,
    "motion-plan-v2.schema.json": MotionPlan,
    "motion-package-v1.schema.json": MotionPackageManifest,
}


def export(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for filename, model in MODELS.items():
        schema = model.model_json_schema(mode="validation")
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = f"https://r1-motion.local/schemas/{filename}"
        (destination / filename).write_text(
            json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    export(Path(__file__).resolve().parent)
