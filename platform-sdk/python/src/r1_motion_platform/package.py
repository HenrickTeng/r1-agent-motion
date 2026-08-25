"""Reference `.r1motion` writer with per-file SHA256 integrity."""

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


NOTICE = "SHA256 integrity verified; source identity is not cryptographically authenticated."


def _json_bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def build_motion_package(
    output: Path,
    *,
    package_id: str,
    motion_version: str,
    platform_approval_id: str,
    design: dict,
    trajectory: dict,
    cloud_report: dict,
    preview: dict,
) -> Path:
    payloads = {
        "motion-design.json": _json_bytes(design),
        "trajectory.json": _json_bytes(trajectory),
        "cloud-simulation-report.json": _json_bytes(cloud_report),
        "preview-animation.json": _json_bytes(preview),
    }
    manifest = {
        "schema_version": "motion-package/v1",
        "package_id": package_id,
        "motion_version": motion_version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "platform_approval_id": platform_approval_id,
        "files": [
            {"path": name, "sha256": sha256(data).hexdigest(), "size_bytes": len(data)}
            for name, data in payloads.items()
        ],
        "integrity_notice": NOTICE,
    }
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", _json_bytes(manifest))
        for name, data in payloads.items():
            archive.writestr(name, data)
    return output
