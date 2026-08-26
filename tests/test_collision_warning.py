import json
from pathlib import Path

import pytest

from motion_core.simulator.collision_warning import scan_action_file


MODEL = Path("/home/henrick/unitree_rl_mjlab/src/assets/robots/unitree_r1/xmls/r1.xml")


def write_action(tmp_path, payload):
    path = tmp_path / "action.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_action_requires_degree_units(tmp_path):
    path = write_action(tmp_path, {"action_name": "bad", "units": "radians", "keyframes": [{"time_s": 0, "offsets_deg": {}}]})
    with pytest.raises(ValueError, match="degrees"):
        scan_action_file(MODEL, path)


def test_unknown_joint_is_rejected(tmp_path):
    path = write_action(tmp_path, {"action_name": "bad", "keyframes": [{"time_s": 0, "offsets_deg": {"finger": 1}}]})
    with pytest.raises(ValueError, match="unknown model joints"):
        scan_action_file(MODEL, path)


def test_scan_returns_warning_only_report(tmp_path):
    if not MODEL.exists():
        pytest.skip("external R1 model is not installed")
    path = write_action(tmp_path, {
        "action_name": "wrist_demo",
        "base_pose_deg": {"right_wrist_roll": 0},
        "keyframes": [
            {"time_s": 0, "offsets_deg": {"right_wrist_roll": 0}},
            {"time_s": 1, "offsets_deg": {"right_wrist_roll": 45}},
        ],
    })
    report = scan_action_file(MODEL, path, sample_hz=10)
    assert report["hardware_authorized"] is False
    assert report["mode"] == "collision_proxies"
    assert len(report["samples"]) == 11
