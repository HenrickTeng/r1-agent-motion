import io
import json
import zipfile
from datetime import datetime, timezone

from imitate.joints import ARM_JOINTS, READY_POSE_DEG
from r1_agent.catalog import load_catalog
from r1_agent.executor import SimulatedBackend
from r1_studio.camera import FrameSource
from r1_studio.motion_library import export_motion, import_motion, save_library, load_library
from r1_studio.session import StudioSession
from r1_studio.skillpack import SkillError, build_skill_zip, compile_python, expand_workflow


def _frame(interval: float) -> dict:
    return {
        "interval": interval,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "source": "camera",
        "mirror": True,
        "pose_deg": dict(READY_POSE_DEG),
    }


def test_motion_export_roundtrip_keeps_human_degrees():
    group = {"id": "wave_custom", "name": "自定义挥手", "frames": [_frame(0), _frame(0.4)]}
    exported = export_motion(group)
    assert exported["schema_version"] == "r1-arm-imitate-mirror/v1"
    assert exported["angle_convention"] == "eduplatform-r1-mjcf/v1"
    assert exported["hardware_authorized"] is False
    restored = import_motion(exported)
    for name in ARM_JOINTS:
        assert abs(restored["frames"][0]["pose_deg"][name] - READY_POSE_DEG[name]) < 0.05


def test_library_file_and_skill_zip(tmp_path):
    group = {"id": "wave_custom", "name": "自定义挥手", "frames": [_frame(0)]}
    path = tmp_path / "motion_library.json"
    save_library(path, [group])
    loaded = load_library(path)
    catalog = load_catalog()
    workflow = [
        {"kind": "action", "id": "wave", "amount": 2, "source": "builtin"},
        {"kind": "action", "id": "wave_custom", "amount": 1, "source": "custom"},
        {"kind": "wait", "seconds": 0.2},
    ]
    planned = expand_workflow(workflow, {item["id"]: item for item in loaded}, catalog)
    assert [step["kind"] for step in planned] == ["catalog", "catalog", "arm", "wait"]
    blob = build_skill_zip(
        pack_id="sp_test",
        title="迎宾",
        description="",
        workflow=workflow,
        groups={item["id"]: item for item in loaded},
    )
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        skill = json.loads(archive.read("skill.json"))
        action = json.loads(archive.read("actions/wave_custom.json"))
    assert skill["schema_version"] == "eduplatform-skillpack/v3"
    assert action["schema_version"] == "r1-arm-imitate-mirror/v1"
    try:
        expand_workflow([{"kind": "action", "id": "sit", "amount": 1, "source": "builtin"}], {}, catalog)
        assert False
    except SkillError:
        pass


def test_python_and_session_playback(tmp_path):
    catalog = load_catalog()
    planned = compile_python("robot.wave(times=2)\nrobot.stop()\nrobot.nod()", catalog)
    assert [step["action"].name for step in planned] == ["wave_right", "wave_right", "stop_move"]
    try:
        compile_python("robot.sit()", catalog)
        assert False
    except SkillError:
        pass
    session = StudioSession(
        backend=SimulatedBackend(),
        camera=FrameSource(None),
        hardware=False,
        groups_path=tmp_path / "custom_groups.json",
    )
    session.set_mode("skills")
    session.save_motion_group({"id": "wave_custom", "name": "自定义挥手", "frames": [_frame(0)]})
    result = session.play_motion_group("wave_custom")
    assert result["ok"] is True
    assert any(line.startswith("TRACK") for line in session.backend.events)
