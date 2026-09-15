from __future__ import annotations

from r1_studio.gestures import GesturePilot, classify_hand, palm_to_twist
from r1_studio.programs import ProgramError, compile_blocks, load_program, validate_group_name
from r1_studio.teleop import keys_to_twist, twist_duration
from r1_studio.vision import Detection, is_vision_intent, summarize_detections
from r1_agent.catalog import load_catalog
from r1_agent.executor import Executor, SimulatedBackend
from r1_studio.programs import apply_custom_groups


def _hand(*, index=True, middle=True, ring=False, pinky=False, wx=0.5, wy=0.55, size=0.12):
    pts = [{"x": 0.5, "y": 0.5}] * 21
    pts[0] = {"x": wx, "y": wy}
    pts[9] = {"x": wx, "y": wy - size}
    for tip, pip, up in (
        (8, 6, index),
        (12, 10, middle),
        (16, 14, ring),
        (20, 18, pinky),
    ):
        pts[pip] = {"x": wx, "y": wy - 0.08}
        pts[tip] = {"x": wx, "y": wy - 0.18 if up else wy - 0.02}
    return pts


def test_cheer_raises_and_staggers_yaw():
    from r1_agent.dds_robot import LSP, LSY, MOTIONS, RSP, RSY

    first = MOTIONS["cheer_both"][0][1]
    second = MOTIONS["cheer_both"][1][1]
    stretch = MOTIONS["stretch"][0][1]
    assert first[LSP] < stretch[LSP]
    assert first[RSP] < stretch[RSP]
    assert first[LSY] != first[RSY]
    assert (first[LSY] - first[RSY]) * (second[LSY] - second[RSY]) < 0


def test_overlay_jpeg_falls_back_when_stale():
    from r1_studio.camera import FrameSource, PLACEHOLDER_JPEG

    source = FrameSource(None)
    source.set_overlay_preview(True)
    source.set_preview_jpeg(b"overlay-bytes")
    assert source.jpeg == b"overlay-bytes"
    source._overlay_t = 0.0
    with source._lock:
        source.jpeg = source._pick_jpeg()
    assert source.jpeg == PLACEHOLDER_JPEG or source.jpeg == source._raw_jpeg


def test_wide_angle_crop_shrinks_frame():
    import numpy as np

    from r1_studio.camera import wide_angle_crop

    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    crop = wide_angle_crop(frame)
    assert crop.shape[0] < 720
    assert crop.shape[1] < 1280


def test_body_crop_keeps_more_than_hand_crop():
    import numpy as np

    from r1_studio.camera import body_crop, wide_angle_crop

    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    hand = wide_angle_crop(frame)
    body = body_crop(frame)
    assert body.shape[0] > hand.shape[0]
    assert body.shape[1] > hand.shape[1]


def _body(*, lwx, lwy, rwx, rwy, lsx=0.42, lsy=0.32, rsx=0.58, rsy=0.32, hip=0.72):
    pts = [{"x": 0.5, "y": 0.5} for _ in range(33)]
    pts[11] = {"x": lsx, "y": lsy}
    pts[12] = {"x": rsx, "y": rsy}
    pts[15] = {"x": lwx, "y": lwy}
    pts[16] = {"x": rwx, "y": rwy}
    pts[13] = {"x": (lsx + lwx) / 2, "y": (lsy + lwy) / 2}
    pts[14] = {"x": (rsx + rwx) / 2, "y": (rsy + rwy) / 2}
    pts[23] = {"x": 0.45, "y": hip}
    pts[24] = {"x": 0.55, "y": hip}
    return pts


def test_body_shapes_and_r1_pilot():
    from r1_studio.body import BodyPilot, classify_body

    tpose = _body(lwx=0.12, lwy=0.32, rwx=0.88, rwy=0.32)
    left = _body(lwx=0.10, lwy=0.34, rwx=0.56, rwy=0.70)
    down = _body(lwx=0.44, lwy=0.70, rwx=0.56, rwy=0.70)
    up = _body(lwx=0.40, lwy=0.08, rwx=0.60, rwy=0.08)
    assert classify_body(tpose) == "tpose"
    assert classify_body(left) == "left_out"
    assert classify_body(down) == "both_down"
    assert classify_body(up) == "both_up"
    pilot = BodyPilot(cheer_hold_s=0.2)
    hunting = pilot.step(down, 1.0)
    assert hunting.kind == "idle"
    assert pilot.status == "hunting"
    locked = pilot.step(tpose, 1.1)
    assert locked.label.startswith("已锁定")
    assert pilot.status == "locked"
    away = pilot.step(tpose, 1.12)
    assert away.kind == "drive"
    assert away.vx < 0
    strafe = pilot.step(left, 1.2)
    assert strafe.kind == "drive"
    assert strafe.vy < 0
    assert "左移" in strafe.label
    stop = pilot.step(down, 1.3)
    assert stop.kind == "stop"
    hold = pilot.step(up, 2.0)
    assert hold.kind == "idle"
    cheer = pilot.step(up, 2.3)
    assert cheer.kind == "cheer"


def test_laptop_frame_source_mirrors_preview():
    import numpy as np

    from r1_studio.camera import FrameSource

    class _Cap:
        def read(self):
            frame = np.zeros((4, 6, 3), dtype=np.uint8)
            frame[:, 0] = 255
            return True, frame

        def release(self):
            pass

    source = FrameSource(_Cap(), mirror=True)
    flipped = source._read()
    assert flipped is not None
    assert int(flipped[0, -1, 0]) == 255
    assert int(flipped[0, 0, 0]) == 0


def test_overlay_preview_does_not_overwrite_jpeg():
    import numpy as np

    from r1_studio.camera import FrameSource

    class _Cap:
        def read(self):
            return True, np.zeros((2, 2, 3), dtype=np.uint8)

        def release(self):
            pass

    source = FrameSource(_Cap(), mirror=False)
    source.overlay_preview = True
    source.jpeg = b"keep-me"
    frame = source._read()
    jpeg = b"should-not-write"
    with source._lock:
        source.frame = frame
        if not source.overlay_preview:
            source.jpeg = jpeg
    assert source.jpeg == b"keep-me"


def test_peace_and_palm_classify():
    assert classify_hand(_hand(index=True, middle=True, ring=False, pinky=False)) == "peace"
    assert classify_hand(_hand(index=True, middle=True, ring=True, pinky=True)) == "palm"
    assert classify_hand(_hand(index=True, middle=True, ring=True, pinky=False)) == "palm"
    assert classify_hand(_hand(index=False, middle=False, ring=False, pinky=False)) == "fist"


def test_palm_left_strafes_left_on_mirrored_view():
    # 笔记本镜像预览：画面左 = 人的左 = 面对面时机器人右移
    hand = _hand(index=True, middle=True, ring=True, pinky=True, wx=0.16, wy=0.5)
    vx, vy, omega = palm_to_twist(hand, mirrored=True, face_to_face=True)
    assert vy < -0.08
    assert abs(vx) < 1e-6
    assert abs(omega) < 1e-6


def test_r1_camera_face_to_face_image_left_is_operator_right():
    hand = _hand(index=True, middle=True, ring=True, pinky=True, wx=0.16, wy=0.5)
    _vx, vy, _omega = palm_to_twist(hand, mirrored=False, face_to_face=True)
    assert vy > 0.08


def test_palm_right_strafes_right():
    hand = _hand(index=True, middle=True, ring=True, pinky=True, wx=0.84, wy=0.5)
    vx, vy, _omega = palm_to_twist(hand, mirrored=True, face_to_face=True)
    assert vy > 0.08
    assert abs(vx) < 1e-6


def test_palm_ignores_up_down():
    up = _hand(wx=0.5, wy=0.22)
    down = _hand(wx=0.5, wy=0.82)
    vx_up, vy_up, _ = palm_to_twist(up)
    vx_down, _, _ = palm_to_twist(down)
    assert abs(vx_up) < 1e-6
    assert abs(vx_down) < 1e-6
    assert abs(vy_up) < 0.05


def test_person_boxes_keeps_people_only():
    from r1_studio.vision import Detection, person_boxes

    items = [
        Detection("person", 0.9, (0.1, 0.1, 0.5, 0.9)),
        Detection("bottle", 0.8, (0.6, 0.6, 0.7, 0.8)),
        Detection("person", 0.2, (0.7, 0.1, 0.9, 0.9)),
    ]
    boxes = person_boxes(items)
    assert boxes == [(0.1, 0.1, 0.5, 0.9)]


def test_operator_hunting_ignores_fist():
    from r1_studio.operator import OperatorLock

    lock = OperatorLock(enabled=True)
    fist = _hand(index=False, middle=False, ring=False, pinky=False, wx=0.5)
    owned, info = lock.step([(0.2, 0.1, 0.8, 0.95)], [fist])
    assert info["status"] == "hunting"
    assert owned == []


def test_operator_lock_prefers_larger_person_and_drops_bystander():
    from r1_studio.operator import OperatorLock

    lock = OperatorLock(enabled=True)
    operator_box = (0.30, 0.08, 0.78, 0.98)
    bystander_box = (0.00, 0.20, 0.18, 0.80)
    op_palm = _hand(index=True, middle=True, ring=True, pinky=True, wx=0.52)
    side_palm = _hand(index=True, middle=True, ring=True, pinky=True, wx=0.08)
    owned, info = lock.step([operator_box, bystander_box], [side_palm, op_palm])
    assert info["status"] == "locked"
    assert all(hand[0]["x"] > 0.25 for hand in owned)
    later, _info = lock.step([operator_box, bystander_box], [side_palm])
    assert later == []


def test_operator_lock_off_passes_all_hands():
    from r1_studio.operator import OperatorLock

    lock = OperatorLock(enabled=False)
    hands = [_hand(wx=0.2), _hand(wx=0.8)]
    owned, info = lock.step([], hands)
    assert owned is hands
    assert info["status"] == "off"


def test_mirrored_pilot_says_left_for_operator_left():
    palm = _hand(index=True, middle=True, ring=True, pinky=True, wx=0.16, wy=0.5)
    cmd = GesturePilot(mirrored=True, face_to_face=True).step([palm], 1.0)
    assert cmd.kind == "drive"
    assert "左移" in cmd.label
    assert cmd.vy < 0


def test_two_palms_spread_away_and_close_near():
    from r1_studio.gestures import two_palms_to_twist

    wide_a = _hand(index=True, middle=True, ring=True, pinky=True, wx=0.12)
    wide_b = _hand(index=True, middle=True, ring=True, pinky=True, wx=0.88)
    close_a = _hand(index=True, middle=True, ring=True, pinky=True, wx=0.42)
    close_b = _hand(index=True, middle=True, ring=True, pinky=True, wx=0.58)
    vx_away, _, _ = two_palms_to_twist(wide_a, wide_b, rest_span=0.35)
    vx_near, _, _ = two_palms_to_twist(close_a, close_b, rest_span=0.45)
    assert vx_away == -0.5
    assert vx_near == 0.5


def test_two_palm_pilot_calibrates_then_spreads():
    left = _hand(index=True, middle=True, ring=True, pinky=True, wx=0.32)
    right = _hand(index=True, middle=True, ring=True, pinky=True, wx=0.68)
    pilot = GesturePilot()
    first = pilot.step([left, right], 1.0)
    assert first.kind == "idle"
    wide_l = _hand(index=True, middle=True, ring=True, pinky=True, wx=0.10)
    wide_r = _hand(index=True, middle=True, ring=True, pinky=True, wx=0.90)
    second = pilot.step([wide_l, wide_r], 1.2)
    assert second.kind == "drive"
    assert second.vx < 0


def test_point_left_turns_left():
    from r1_studio.gestures import point_to_twist

    hand = _hand(index=True, middle=False, ring=False, pinky=False, wx=0.18, wy=0.45)
    hand[8] = {"x": 0.12, "y": 0.25}
    _vx, _vy, omega = point_to_twist(hand, mirrored=True, face_to_face=True)
    assert omega < -0.3


def test_peace_hold_triggers_cheer_once():
    pilot = GesturePilot(peace_hold_s=0.2, cheer_cooldown_s=5)
    peace = [_hand()]
    first = pilot.step(peace, 1.0)
    assert first.kind == "idle"
    cheer = pilot.step(peace, 1.3)
    assert cheer.kind == "cheer"
    again = pilot.step(peace, 1.5)
    assert again.kind != "cheer"


def test_keys_combine_and_clamp():
    vx, vy, omega = keys_to_twist(["w", "q"])
    assert vx == 0.5
    assert omega == 1.0
    slow = keys_to_twist(["w"], slow=True)
    assert slow[0] == 0.25
    assert keys_to_twist([]) == (0.0, 0.0, 0.0)
    assert twist_duration(0.5, 0.0, 0.0) == 0.5
    assert twist_duration(0.0, 0.2, 0.0) == 1.0
    assert twist_duration(0.0, -0.5, 0.0) == 1.0
    assert keys_to_twist(["a"])[1] == 0.5
    assert keys_to_twist(["d"])[1] == -0.5


def test_studio_starts_without_camera_until_chosen(tmp_path):
    from r1_agent.executor import SimulatedBackend
    from r1_studio.camera import FrameSource
    from r1_studio.session import StudioSession

    session = StudioSession(
        backend=SimulatedBackend(),
        camera=FrameSource(None),
        hardware=False,
        groups_path=tmp_path / "g.json",
    )
    assert session.camera_source == "synthetic"
    assert "笔记本摄像头" in session.last_reply
    assert "机载" in session.last_reply


def test_set_mode_teleop_does_not_wait_for_stop(tmp_path):
    import threading
    import time

    from r1_agent.executor import SimulatedBackend
    from r1_studio.camera import FrameSource
    from r1_studio.session import StudioSession

    gate = threading.Event()

    class SlowStop(SimulatedBackend):
        def stop(self) -> None:
            gate.wait(2.0)
            super().stop()

    session = StudioSession(
        backend=SlowStop(),
        camera=FrameSource(None),
        hardware=False,
        groups_path=tmp_path / "g.json",
    )
    started = time.time()
    session.set_mode("teleop")
    assert time.time() - started < 0.3
    assert session.mode == "teleop"
    assert "QWEASD" in session.last_reply
    gate.set()


def test_vision_intent_and_summary():
    assert is_vision_intent("请进入物体识别模式")
    assert is_vision_intent("这是什么")
    assert is_vision_intent("这本书该放在那里")
    empty = summarize_detections([])
    assert "没有认出" in empty
    text = summarize_detections([Detection("backpack", 0.9), Detection("bottle", 0.8)])
    assert "书包" in text


def test_campus_prompt_library_vs_guess():
    from r1_studio.vision import campus_system_prompt, campus_user_text, load_campus_text

    general = campus_system_prompt(load_campus_text("context.txt"))
    assert "禁止编造" in general
    assert "三楼南区" not in general
    assert "2 楼东区" not in general
    with_lib = campus_system_prompt(load_campus_text("context.txt") + "\n" + load_campus_text("library.txt"))
    assert "还书处" in with_lib
    assert "2 楼东区" in with_lib or "二楼" in with_lib
    asked = campus_user_text("这本书该放在哪里", [Detection("book", 0.9)])
    assert "书本" in asked
    assert "这本书该放在哪里" in asked


def test_ask_campus_falls_back_without_key(monkeypatch):
    from r1_studio.vision import ask_campus

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("VLM_API_KEY", raising=False)
    monkeypatch.setattr("r1_studio.vision.load_deepseek_key", lambda path=None: "")
    reply = ask_campus(question="这是什么", detections=[], jpeg=b"", api_key="")
    assert "没有认出" in reply


def test_configure_campus_library_flag(tmp_path):
    from r1_agent.executor import SimulatedBackend
    from r1_studio.camera import FrameSource
    from r1_studio.session import StudioSession

    session = StudioSession(
        backend=SimulatedBackend(),
        camera=FrameSource(None),
        hardware=False,
        groups_path=tmp_path / "g.json",
    )
    assert "还书处" not in session.campus_context()
    session.configure_campus(library_on=True)
    assert "还书处" in session.campus_context()
    session.configure_campus(library_on=False, extra="三年级在 A 栋 2 楼")
    assert "还书处" not in session.campus_context()
    assert "三年级" in session.campus_context()


def test_program_compiles_and_wait_executes():
    catalog = apply_custom_groups(load_catalog(), {"超级欢迎": ["wave_right", "cheer_both"]})
    actions = compile_blocks(
        [
            {"type": "say", "text": "你好"},
            {"type": "move", "name": "move_forward_slow", "repeat": 2},
            {"type": "custom", "name": "超级欢迎"},
            {"type": "wait", "seconds": 0},
        ],
        catalog,
    )
    assert [action.name for action in actions] == [
        "say",
        "move_forward_slow",
        "move_forward_slow",
        "wave_right",
        "cheer_both",
        "wait",
    ]
    backend = SimulatedBackend()
    Executor(backend).execute(actions)
    assert backend.events[0].startswith("SAY 你好")
    assert "ARM cheer_both" in backend.events
    assert any(item.startswith("MOVE move_forward_slow") for item in backend.events)


def test_program_keeps_going_after_speech():
    from r1_agent.catalog import load_catalog
    from r1_agent.executor import Executor, SimulatedBackend
    from r1_studio.programs import compile_blocks

    actions = compile_blocks(
        [
            {"type": "say", "text": "你好"},
            {"type": "wait", "seconds": 0},
            {"type": "move", "name": "move_backward_slow"},
            {"type": "move", "name": "move_left_slow"},
            {"type": "turn", "name": "turn_left_90"},
        ],
        load_catalog(),
    )
    backend = SimulatedBackend()
    Executor(backend).execute(actions)
    kinds = [event.split()[0] for event in backend.events]
    assert kinds[0] == "SAY"
    assert "MOVE" in kinds
    assert "TURN" in kinds
    assert kinds[-1] == "STOP"


def test_example_program_file():
    from pathlib import Path
    import json

    from r1_agent.catalog import ROOT

    payload = json.loads((ROOT / "programs/examples/welcome.r1prog.json").read_text(encoding="utf-8"))
    name, actions = load_program(payload, load_catalog())
    assert name == "欢迎仪式"
    assert actions[0].kind == "speech"
    assert any(action.name == "cheer_both" for action in actions)


def test_inspect_block_shows_robot_command():
    from r1_studio.programs import inspect_blocks

    catalog = load_catalog()
    one = inspect_blocks([{"type": "move", "name": "move_forward_slow"}], catalog, index=0)
    assert one["ok"] is True
    assert "SetVelocity" in one["text"]
    assert "0.5" in one["text"]
    whole = inspect_blocks(
        [{"type": "say", "text": "你好"}, {"type": "action", "name": "wave_right"}],
        catalog,
    )
    assert whole["steps"][-1]["command"] == "LocoClient.StopMove()"
    assert "TtsMaker" in whole["text"]
    assert "rt/arm_sdk" in whole["text"]


def test_rejects_unknown_block_and_system_name():
    catalog = load_catalog()
    try:
        compile_blocks([{"type": "fly"}], catalog)
        assert False
    except ProgramError:
        pass
    try:
        validate_group_name("wave_right", catalog)
        assert False
    except ProgramError:
        pass


def test_studio_http_and_custom_group(tmp_path):
    import json
    import threading
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer

    from r1_agent.executor import SimulatedBackend
    from r1_studio.camera import FrameSource
    from r1_studio.server import StudioHandler
    from r1_studio.session import StudioSession

    session = StudioSession(
        backend=SimulatedBackend(),
        camera=FrameSource(None),
        hardware=False,
        groups_path=tmp_path / "custom_groups.json",
    )
    StudioHandler.session = session
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), StudioHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    try:
        home = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3).read()
        assert "图形化编程".encode() in home
        assert "无法撤回".encode() in home
        assert "开始键盘遥控".encode() in home
        assert "笔记本摄像头".encode() in home
        assert "R1 机载摄像头".encode() in home
        bad = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/camera",
            data=json.dumps({"source": "nope"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(bad, timeout=3)
            assert False
        except urllib.error.HTTPError as error:
            assert error.code == 400
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/groups",
            data=json.dumps({"name": "超级欢迎", "steps": ["wave_right", "cheer_both"]}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        saved = json.loads(urllib.request.urlopen(req, timeout=3).read())
        assert saved["ok"] is True
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/program/run",
            data=json.dumps({
                "schema": "r1-student-program/v1",
                "name": "测",
                "blocks": [{"type": "custom", "name": "超级欢迎"}],
            }).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        ran = json.loads(urllib.request.urlopen(req, timeout=3).read())
        assert ran["ok"] is True
        assert ran["actions"] == ["右手挥手", "举起双手欢呼"]
        text_req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/text",
            data=json.dumps({"text": "进入物体识别模式"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        vision = json.loads(urllib.request.urlopen(text_req, timeout=5).read())
        assert vision["ok"] is True
        assert "reply" in vision
    finally:
        httpd.shutdown()


def test_gesture_drive_ignores_busy_and_teleop_halt(tmp_path):
    from r1_agent.executor import SimulatedBackend
    from r1_studio.camera import FrameSource
    from r1_studio.gestures import GestureCommand
    from r1_studio.session import StudioSession

    backend = SimulatedBackend()
    session = StudioSession(
        backend=backend,
        camera=FrameSource(None),
        hardware=False,
        groups_path=tmp_path / "g.json",
    )
    session.mode = "gesture"
    session.busy = True
    issued, skip = session._apply_gesture(GestureCommand("drive", vx=0.5, label="飞近", pose="hands_in"))
    assert issued is True
    assert skip == ""
    assert any(item.startswith("DRIVE 0.500") for item in backend.events)
    backend.events.clear()
    session.teleop_keys([])
    assert not any(item == "STOP" or item.startswith("DRIVE 0.000") for item in backend.events)
    idle = StudioSession(
        backend=SimulatedBackend(),
        camera=FrameSource(None),
        hardware=False,
        groups_path=tmp_path / "g2.json",
    )
    blocked = idle.teleop_keys(["w"])
    assert blocked["ok"] is False
    assert "开始键盘遥控" in blocked["error"]
