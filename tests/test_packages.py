from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from motion_core.errors import ContractError
from motion_core.packages import verify_package


NOTICE = "SHA256 integrity verified; source identity is not cryptographically authenticated."


def build_package(path: Path, trajectory, *, tamper: bool = False):
    payloads = {
        "motion-design.json": json.dumps({
            "schema_version": "motion-design-spec/v1", "motion_id": "package-wrist", "title": "Package wrist", "intent": "wrist",
            "scope": "upper_body", "initial_pose_binding": "relative_current",
            "joint_keyframes": [{"time_s": 2, "offsets": [{"joint": "right_wrist_roll", "offset_rad": 0.3}], "hold_s": 0}],
            "end_effector_targets": [], "repeat": 1, "tempo": "slow", "return_policy": {"mode": "return_to_initial", "duration_s": 2}, "safety_profile": "classroom-upper-v1",
        }, ensure_ascii=False, separators=(",", ":")).encode(),
        "trajectory.json": trajectory.model_dump_json().encode(),
        "cloud-simulation-report.json": json.dumps({"passed": True, "trajectory_sha256": trajectory.trajectory_sha256}, separators=(",", ":")).encode(),
        "preview-animation.json": json.dumps({"trajectory_sha256": trajectory.trajectory_sha256, "frames": []}, separators=(",", ":")).encode(),
    }
    manifest = {
        "schema_version": "motion-package/v1", "package_id": "package-wrist", "motion_version": "1.0.0",
        "created_at": "2026-08-25T00:00:00Z", "platform_approval_id": "approval-1",
        "files": [{"path": name, "sha256": sha256(data).hexdigest(), "size_bytes": len(data)} for name, data in payloads.items()],
        "integrity_notice": NOTICE,
    }
    if tamper:
        payloads["preview-animation.json"] += b" "
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, separators=(",", ":")))
        for name, data in payloads.items(): archive.writestr(name, data)


def test_package_verifies_all_hashes(tmp_path, wrist_trajectory):
    path = tmp_path / "safe.r1motion"
    build_package(path, wrist_trajectory)
    package = verify_package(path)
    assert package.trajectory.trajectory_sha256 == wrist_trajectory.trajectory_sha256


def test_package_rejects_tampering(tmp_path, wrist_trajectory):
    path = tmp_path / "tampered.r1motion"
    build_package(path, wrist_trajectory, tamper=True)
    with pytest.raises(ContractError, match="integrity"):
        verify_package(path)
