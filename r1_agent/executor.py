from __future__ import annotations

import threading
import time
from typing import Protocol

from r1_agent.catalog import Action


class Backend(Protocol):
    def speak(self, text: str) -> None: ...
    def arm(self, action: Action) -> None: ...
    def move(self, action: Action) -> None: ...
    def turn(self, action: Action) -> None: ...
    def stop(self) -> None: ...
    def drive(self, vx: float, vy: float, omega: float, duration: float = 0.4) -> None: ...


class SimulatedBackend:
    def __init__(self) -> None:
        self.events: list[str] = []

    def _record(self, event: str) -> None:
        self.events.append(event)
        print(event)

    def speak(self, text: str) -> None:
        self._record(f"SAY {text}")

    def arm(self, action: Action) -> None:
        self._record(f"ARM {action.name}")

    def move(self, action: Action) -> None:
        self._record(f"MOVE {action.name} {action.args}")

    def turn(self, action: Action) -> None:
        self._record(f"TURN {action.name} {action.args}")

    def stop(self) -> None:
        self._record("STOP")

    def drive(self, vx: float, vy: float, omega: float, duration: float = 0.4) -> None:
        if abs(vx) + abs(vy) + abs(omega) < 1e-3:
            self.stop()
            return
        self._record(f"DRIVE {vx:.3f} {vy:.3f} {omega:.3f} {duration:.2f}")

    def soft_estop(self) -> None:
        self._record("ESTOP")

    def clear_estop(self) -> None:
        self._record("ESTOP_CLEAR")


class Executor:
    def __init__(self, backend: Backend) -> None:
        self.backend = backend

    def execute(self, actions: list[Action]) -> None:
        index = 0
        while index < len(actions):
            action = actions[index]
            if action.kind == "speech":
                print(f"PROGRAM say {action.args.get('text')}", flush=True)
                self.backend.speak(action.args["text"])
                index += 1
                continue
            if action.kind == "wait":
                seconds = max(0.0, float(action.args.get("seconds") or 0))
                print(f"PROGRAM wait {seconds:g}s", flush=True)
                time.sleep(seconds)
                index += 1
                continue
            group: list[Action] = []
            while index < len(actions) and actions[index].kind not in ("speech", "wait"):
                group.append(actions[index])
                index += 1
            self._execute_body(group)
        self.backend.stop()

    def _run_locos(self, locos: list[Action], errors: list[BaseException]) -> None:
        try:
            for action in locos:
                print(f"PROGRAM {action.kind} {action.name}", flush=True)
                if action.kind == "move":
                    self.backend.move(action)
                else:
                    self.backend.turn(action)
        except BaseException as error:
            errors.append(error)

    def _execute_body(self, group: list[Action]) -> None:
        locos = [action for action in group if action.kind in ("move", "turn")]
        arms = [action for action in group if action.kind == "arm"]
        errors: list[BaseException] = []
        if locos and arms:
            thread = threading.Thread(target=self._run_locos, args=(locos, errors))
            thread.start()
            try:
                for action in arms:
                    self.backend.arm(action)
            except BaseException as error:
                errors.append(error)
            thread.join()
        elif locos:
            self._run_locos(locos, errors)
        else:
            for action in arms:
                print(f"PROGRAM arm {action.name}", flush=True)
                self.backend.arm(action)
        if errors:
            raise errors[0]
