from r1_agent.catalog import load_catalog
from r1_agent.dds_robot import LOCO, MOTIONS
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


def test_catalog_arm_and_loco_names_match_runners():
    catalog = load_catalog()
    for action in catalog.actions.values():
        if action.kind == "arm":
            assert action.name in MOTIONS
        elif action.kind in ("move", "turn"):
            assert action.name in LOCO
