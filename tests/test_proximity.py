from r1_agent.catalog import load_catalog
from r1_agent.executor import SimulatedBackend
from r1_studio.camera import FrameSource
from r1_studio.depth import (
    bbox_distance_m,
    classify_zone,
    disparity_to_depth_m,
    looks_side_by_side,
    split_stereo,
)
from r1_studio.proximity import DANGER_TEXT, GreetPilot, WARN_TEXT, drop_locomotion, map_hand_pose, pick_pose
from r1_studio.session import StudioSession


def test_pose_shoulder_is_much_closer_than_full_body_on_torso_box():
    from r1_studio.depth import bbox_distance_m, estimate_distance, pose_distance_m

    landmarks = [{"x": 0.5, "y": 0.5} for _ in range(33)]
    landmarks[11] = {"x": 0.42, "y": 0.32, "visibility": 0.99}
    landmarks[12] = {"x": 0.58, "y": 0.32, "visibility": 0.99}
    landmarks[23] = {"x": 0.44, "y": 0.58, "visibility": 0.99}
    landmarks[24] = {"x": 0.56, "y": 0.58, "visibility": 0.99}
    close, src = pose_distance_m(landmarks, 1280, 720, fov_deg=120)
    far_box = bbox_distance_m((0.38, 0.24, 0.62, 0.62), 720, fy=400, frame_width=1280)
    assert close is not None and far_box is not None
    assert src == "pose-shoulder"
    assert close < far_box
    wider = [{"x": 0.5, "y": 0.5} for _ in range(33)]
    wider[11] = {"x": 0.30, "y": 0.32, "visibility": 0.99}
    wider[12] = {"x": 0.70, "y": 0.32, "visibility": 0.99}
    nearer, _src = pose_distance_m(wider, 1280, 720, fov_deg=120)
    assert nearer is not None and nearer < close
    import numpy as np

    frame = np.zeros((720, 1280, 3), dtype="uint8")
    estimate, _preview = estimate_distance(frame, [], landmarks=landmarks, fov_deg=120)
    assert estimate.source == "pose-shoulder"
    assert estimate.meters is not None
    assert abs(estimate.meters - close) < 1e-6


def test_split_stereo_and_zones():
    import numpy as np

    frame = np.zeros((120, 400, 3), dtype="uint8")
    assert looks_side_by_side(frame)
    left, right = split_stereo(frame)
    assert left.shape[1] == 200
    assert right.shape[1] == 200
    mono = np.zeros((240, 320, 3), dtype="uint8")
    only, missing = split_stereo(mono)
    assert missing is None
    assert only.shape == mono.shape
    assert classify_zone(0.2) == "danger"
    assert classify_zone(0.4) == "caution"
    assert classify_zone(1.0) == "greet"
    assert classify_zone(3.0) == "far"
    assert classify_zone(None) == "unknown"
    assert disparity_to_depth_m(30, fx=400, baseline_m=0.06) == 400 * 0.06 / 30
    near = bbox_distance_m((0.2, 0.05, 0.8, 0.95), 480, fy=400, frame_width=640)
    far = bbox_distance_m((0.35, 0.35, 0.55, 0.62), 480, fy=400, frame_width=640)
    assert near is not None and far is not None
    assert near < far


def test_pair_from_shift_and_inspect_shape():
    import numpy as np

    from r1_studio.depth import inspect_stereo, pair_from_shift

    frame = np.zeros((120, 200, 3), dtype="uint8")
    frame[:, 20:40] = 200
    left, right = pair_from_shift(frame, 10)
    assert left is not None and right is not None
    assert left.shape[1] == 190
    assert right.shape[1] == 190
    info, _preview = inspect_stereo(frame, shift_px=10)
    assert info["shape"] == [120, 200]
    assert info["native_sbs"] is False


def test_greet_pilot_safety_and_wave():
    pilot = GreetPilot()
    first = pilot.step(1.1, "none", 20.0)
    assert first.kind == "greet"
    assert "wave_right" in first.actions
    again = pilot.step(1.1, "none", 20.2)
    assert again.kind == "idle"
    close = pilot.step(0.22, "palm", 21.0)
    assert close.kind == "freeze"
    assert close.reply == DANGER_TEXT
    assert not close.actions
    assert not pilot.allows_arm()
    mid = pilot.step(0.42, "palm", 28.0)
    assert mid.kind == "warn"
    assert mid.reply == WARN_TEXT
    wave = GreetPilot().step(1.0, "palm", 10.0)
    assert wave.kind == "gesture"
    assert wave.actions == ("wave_right",)


def test_hand_pose_mapping():
    assert map_hand_pose("peace") == ("cheer_both",)
    palm = [{"x": 0.5, "y": 0.5}] * 21
    palm[0] = {"x": 0.5, "y": 0.7}
    palm[9] = {"x": 0.5, "y": 0.55}
    for tip, pip in ((8, 6), (12, 10), (16, 14), (20, 18)):
        palm[pip] = {"x": 0.5, "y": 0.5}
        palm[tip] = {"x": 0.5, "y": 0.32}
    assert pick_pose(hands=[palm], body_pose="none") == "palm"


def test_drop_locomotion_keeps_arms():
    catalog = load_catalog()
    kept = drop_locomotion([catalog.actions["wave_right"], catalog.actions["move_forward_slow"]])
    assert [item.name for item in kept] == ["wave_right"]


def test_greet_mode_blocks_walk_and_close_range_arms(tmp_path):
    backend = SimulatedBackend()
    session = StudioSession(
        backend=backend,
        camera=FrameSource(None),
        hardware=False,
        groups_path=tmp_path / "g.json",
    )
    session.set_mode("greet")
    assert session.mode == "greet"
    session._greet.zone = "greet"
    session._greet.meters = 1.0
    backend.events.clear()
    walked = session.handle_text("向前走")
    assert walked["ok"] is True
    assert not any(item.startswith("MOVE") for item in backend.events)
    backend.events.clear()
    waved = session.handle_text("打招呼")
    assert waved["ok"] is True
    assert any("wave_right" in item for item in backend.events)
    session._greet.zone = "danger"
    session._greet.meters = 0.18
    backend.events.clear()
    blocked = session.handle_text("打招呼")
    assert "贴" in (blocked.get("reply") or "") or "远" in (blocked.get("reply") or "")
    assert not any(item.startswith("ARM") for item in backend.events)


def test_apply_greet_event_records_dialog_without_walking(tmp_path):
    backend = SimulatedBackend()
    session = StudioSession(
        backend=backend,
        camera=FrameSource(None),
        hardware=False,
        groups_path=tmp_path / "g.json",
    )
    from r1_studio.proximity import GreetEvent

    session._apply_greet_event(
        GreetEvent("greet", "greet", 1.2, "你好，很高兴见到你。", ("say:greeting", "wave_right"), "none", "迎宾")
    )
    assert any(item.startswith("ARM wave_right") for item in backend.events)
    assert not any(item.startswith("MOVE") for item in backend.events)
    assert any(item.startswith("SAY") for item in backend.events)
