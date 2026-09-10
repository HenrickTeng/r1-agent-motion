import math

import pytest

from r1_agent.catalog import load_catalog
from r1_agent.dds_robot import AMPLITUDE, LOCO, MOTIONS, READY_POSE_DEG, RSP, SHOULDER_PITCH, WALK_FSMS, _loco_issued
from r1_agent.hardware import R1Hardware


class FakeRobot:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def speak(self, text: str) -> None:
        self.calls.append(("speak", text))

    def arm(self, action) -> None:
        self.calls.append(("arm", action.name))

    def move(self, action) -> None:
        self.calls.append(("move", action.name))

    def turn(self, action) -> None:
        self.calls.append(("turn", action.name))

    def stop(self) -> None:
        self.calls.append(("stop",))

    def drive(self, vx, vy, omega, duration=0.4) -> None:
        self.calls.append(("drive", vx, vy, omega, duration))

    def soft_estop(self) -> None:
        self.calls.append(("estop",))

    def clear_estop(self) -> None:
        self.calls.append(("estop_clear",))


def test_deferred_hardware_wait_message():
    from r1_agent.hardware import DeferredHardware

    delayed = DeferredHardware()
    try:
        delayed.drive(0.1, 0, 0)
        assert False
    except RuntimeError as error:
        assert "还在连接" in str(error)
    delayed.attach(FakeRobot())
    delayed.drive(0.1, 0, 0, 0.4)
    delayed.fail("网线掉了")
    try:
        delayed.speak("hi")
        assert False
    except RuntimeError as error:
        assert "网线" in str(error)


def test_arm_uses_named_action():
    robot = FakeRobot()
    hardware = R1Hardware(robot=robot)
    hardware.arm(load_catalog().actions["hands_forward"])
    assert robot.calls == [("arm", "hands_forward")]


def test_wrist_wave_uses_same_runner():
    robot = FakeRobot()
    hardware = R1Hardware(robot=robot)
    hardware.arm(load_catalog().actions["wrist_wave"])
    assert robot.calls == [("arm", "wrist_wave")]


def test_arm_offsets_are_scaled_up():
    assert AMPLITUDE == 1.8
    assert SHOULDER_PITCH == 3.0
    pose = MOTIONS["wave_right"][0][1]
    assert pose[RSP] == pytest.approx(READY_POSE_DEG[RSP] + (-0.50 * SHOULDER_PITCH * 180.0 / math.pi))
    hug = MOTIONS["hug"][0][1]
    assert hug[1] == pytest.approx(READY_POSE_DEG[1] + (0.36 * AMPLITUDE * 180.0 / math.pi))
    assert hug[0] == pytest.approx(READY_POSE_DEG[0] + (-0.50 * SHOULDER_PITCH * 180.0 / math.pi))
    assert hug[RSP] == pytest.approx(READY_POSE_DEG[RSP] + (-0.50 * SHOULDER_PITCH * 180.0 / math.pi))


def test_loco_issued_accepts_firmware_127():
    assert _loco_issued(0)
    assert _loco_issued(127)
    assert _loco_issued(None)
    assert not _loco_issued(3203)
    assert not _loco_issued(1001)


def test_walk_fsms_include_arm_sdk_loco():
    assert 811 in WALK_FSMS
    assert 816 in WALK_FSMS
    assert 1 not in WALK_FSMS
    assert 4 not in WALK_FSMS


def test_catalog_arm_and_loco_names_match_runners():
    catalog = load_catalog()
    for action in catalog.actions.values():
        if action.kind == "arm":
            assert action.name in MOTIONS
        elif action.kind in ("move", "turn"):
            assert action.name in LOCO
            vx, vy, omega, duration = LOCO[action.name]
            assert action.args == {"vx": vx, "vy": vy, "omega": omega, "duration": duration}


def test_hardware_drive_and_estop():
    robot = FakeRobot()
    hardware = R1Hardware(robot=robot)
    hardware.drive(0.2, 0.0, 0.0, 0.4)
    hardware.soft_estop()
    assert robot.calls[0][0] == "drive"
    assert robot.calls[1] == ("estop",)
