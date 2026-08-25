"""Regenerate public OpenAPI and JSON Schema artifacts from authoritative code."""

import json
from pathlib import Path
import shutil

from apps.simulation_service.api import create_app
from motion_core.schemas.export import export


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    schema_dir = ROOT / "platform-sdk" / "schemas"
    export(schema_dir)
    openapi_dir = ROOT / "platform-sdk" / "openapi"
    openapi_dir.mkdir(parents=True, exist_ok=True)
    (openapi_dir / "simulation-service.openapi.json").write_text(
        json.dumps(create_app().openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    typescript_schemas = ROOT / "platform-sdk" / "typescript" / "schemas"
    typescript_schemas.mkdir(parents=True, exist_ok=True)
    for source in schema_dir.glob("*.schema.json"):
        shutil.copy2(source, typescript_schemas / source.name)


if __name__ == "__main__":
    main()
