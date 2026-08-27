from __future__ import annotations

from typing import Protocol

from r1_agent.catalog import Action


class Backend(Protocol):
    def speak(self, text: str) -> None: ...
    def arm(self, action: Action) -> None: ...
    def move(self, action: Action) -> None: ...
    def turn(self, action: Action) -> None: ...
    def stop(self) -> None: ...


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


class Executor:
    def __init__(self, backend: Backend) -> None:
        self.backend = backend

    def execute(self, actions: list[Action]) -> None:
        try:
            for action in actions:
                if action.kind == "speech":
                    self.backend.speak(action.args["text"])
                elif action.kind == "move":
                    self.backend.move(action)
                elif action.kind == "turn":
                    self.backend.turn(action)
                elif action.kind == "arm":
                    self.backend.arm(action)
                else:
                    raise RuntimeError(f"unknown action kind: {action.kind}")
                self.backend.stop()
        finally:
            self.backend.stop()
