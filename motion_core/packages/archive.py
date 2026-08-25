"""Verify package structure, SHA256 integrity and embedded contracts."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from motion_core.errors import ContractError
from motion_core.schemas.models import (
    CompiledTrajectory,
    MotionDesignSpec,
    MotionPackageManifest,
    content_sha256,
)


REQUIRED_FILES = {
    "manifest.json",
    "motion-design.json",
    "trajectory.json",
    "cloud-simulation-report.json",
    "preview-animation.json",
}
MAX_ARCHIVE_BYTES = 25_000_000


@dataclass(frozen=True)
class MotionPackage:
    path: Path
    archive_sha256: str
    manifest: MotionPackageManifest
    design: MotionDesignSpec
    trajectory: CompiledTrajectory
    cloud_report: dict
    preview: dict


def verify_package(path: Path) -> MotionPackage:
    if not path.is_file() or path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ContractError("motion package is missing or exceeds 25 MB")
    archive_bytes = path.read_bytes()
    try:
        with ZipFile(path) as archive:
            names = set(archive.namelist())
            if names != REQUIRED_FILES or any("/" in name or "\\" in name for name in names):
                raise ContractError("package must contain exactly five root-level files")
            if any(info.file_size > 20_000_000 for info in archive.infolist()):
                raise ContractError("package member exceeds size limit")
            raw = {name: archive.read(name) for name in REQUIRED_FILES}
    except BadZipFile as error:
        raise ContractError("invalid ZIP archive") from error
    try:
        manifest = MotionPackageManifest.model_validate_json(raw["manifest.json"])
        design = MotionDesignSpec.model_validate_json(raw["motion-design.json"])
        trajectory = CompiledTrajectory.model_validate_json(raw["trajectory.json"])
        cloud_report = json.loads(raw["cloud-simulation-report.json"])
        preview = json.loads(raw["preview-animation.json"])
    except Exception as error:
        raise ContractError("package contains invalid JSON or contract data") from error
    members = {item.path: item for item in manifest.files}
    for name, item in members.items():
        observed = sha256(raw[name]).hexdigest()
        if observed != item.sha256 or len(raw[name]) != item.size_bytes:
            raise ContractError(f"package member integrity failed: {name}")
    unsigned = trajectory.model_dump(mode="json", exclude={"trajectory_sha256"})
    if content_sha256(unsigned) != trajectory.trajectory_sha256:
        raise ContractError("embedded trajectory SHA256 is invalid")
    if cloud_report.get("trajectory_sha256") != trajectory.trajectory_sha256:
        raise ContractError("cloud report does not bind the embedded trajectory")
    if cloud_report.get("passed") is not True:
        raise ContractError("cloud simulation report did not pass")
    if preview.get("trajectory_sha256") != trajectory.trajectory_sha256:
        raise ContractError("preview does not bind the embedded trajectory")
    return MotionPackage(
        path=path,
        archive_sha256=sha256(archive_bytes).hexdigest(),
        manifest=manifest,
        design=design,
        trajectory=trajectory,
        cloud_report=cloud_report,
        preview=preview,
    )
