from __future__ import annotations

import os
from pathlib import Path
import subprocess

from r1_agent.catalog import Action, ROOT


class R1Hardware:
    def __init__(self, interface: str = "enp7s0", root: Path | None = None) -> None:
        self.interface = interface
        self.root = root or ROOT

    def _binary(self, env_name: str, relative: str) -> Path:
        configured = os.getenv(env_name)
        path = Path(configured) if configured else self.root / relative
        if not path.is_file() or not os.access(path, os.X_OK):
            raise RuntimeError(f"hardware binary is not executable: {path}")
        return path

    def _run(self, binary: Path, *args: str, stdin: str | None = None) -> None:
        result = subprocess.run(
            [str(binary), self.interface, *args],
            input=stdin,
            text=True,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(f"{binary.name} failed with exit code {result.returncode}")

    def speak(self, text: str) -> None:
        self._run(self._binary("R1_TTS_SAY_BIN", "build/robot/r1_tts_say"), text, "0")

    def arm(self, action: Action) -> None:
        self._run(self._binary("R1_FIXED_ACTION_BIN", "build/robot/r1_fixed_action"), action.name, stdin="START\n")

    def move(self, action: Action) -> None:
        self._run(self._binary("R1_LOCO_BIN", "build/robot/r1_loco"), action.name, stdin="START\n")

    def turn(self, action: Action) -> None:
        self.move(action)

    def stop(self) -> None:
        return None
