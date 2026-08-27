from __future__ import annotations

from r1_agent.catalog import Action


class R1Hardware:
    def __init__(self, interface: str = "enp7s0", robot=None) -> None:
        if robot is None:
            from r1_agent.dds_robot import DdsRobot
            robot = DdsRobot(interface)
        self.robot = robot

    def speak(self, text: str) -> None:
        self.robot.speak(text)

    def arm(self, action: Action) -> None:
        self.robot.arm(action)

    def move(self, action: Action) -> None:
        self.robot.move(action)

    def turn(self, action: Action) -> None:
        self.robot.turn(action)

    def stop(self) -> None:
        self.robot.stop()
