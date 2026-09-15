from __future__ import annotations

import threading

from r1_agent.catalog import Action


class DeferredHardware:
    """网页先起来，机器人在后台握手。未就绪时下发会明确报错，而不是卡住。"""

    def __init__(self) -> None:
        self._inner = None
        self._error = ""
        self._lock = threading.Lock()
        self.ready = False

    def attach(self, inner) -> None:
        with self._lock:
            self._inner = inner
            self._error = ""
            self.ready = True

    def fail(self, message: str) -> None:
        with self._lock:
            self._error = message
            self.ready = False

    def _use(self):
        with self._lock:
            if self._error:
                raise RuntimeError(self._error)
            if self._inner is None:
                raise RuntimeError("机器人还在连接 DDS，请等终端出现「机器人已就绪」后再控制")
            return self._inner

    def speak(self, text: str) -> None:
        self._use().speak(text)

    def arm(self, action: Action) -> None:
        self._use().arm(action)

    def move(self, action: Action) -> None:
        self._use().move(action)

    def turn(self, action: Action) -> None:
        self._use().turn(action)

    def stop(self) -> None:
        with self._lock:
            inner = self._inner
        if inner is None:
            return
        inner.stop()

    def drive(self, vx: float, vy: float, omega: float, duration: float = 0.4) -> None:
        self._use().drive(vx, vy, omega, duration)

    def soft_estop(self) -> None:
        self._use().soft_estop()

    def clear_estop(self) -> None:
        self._use().clear_estop()


class R1Hardware:
    def __init__(self, interface: str = "auto", robot=None) -> None:
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

    def drive(self, vx: float, vy: float, omega: float, duration: float = 0.4) -> None:
        self.robot.drive(vx, vy, omega, duration)

    def soft_estop(self) -> None:
        self.robot.soft_estop()

    def clear_estop(self) -> None:
        self.robot.clear_estop()
