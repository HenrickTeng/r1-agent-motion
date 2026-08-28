import math

import pytest

from r1_agent.catalog import load_catalog
from r1_agent.dds_robot import AMPLITUDE, LOCO, MOTIONS, READY_POSE_DEG, RSP, SHOULDER_PITCH, _loco_issued
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


def test_catalog_arm_and_loco_names_match_runners():
    catalog = load_catalog()
    for action in catalog.actions.values():
        if action.kind == "arm":
            assert action.name in MOTIONS
        elif action.kind in ("move", "turn"):
            assert action.name in LOCO
            vx, vy, omega, duration = LOCO[action.name]
            assert action.args == {"vx": vx, "vy": vy, "omega": omega, "duration": duration}
