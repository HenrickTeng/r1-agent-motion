"""Hardware backend for the minimal named-action demo."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

from motion_core.demo import DemoAction


class R1DemoHardware:
    def __init__(self, interface: str = "enp7s0", root: Path | None = None) -> None:
        self.interface = interface
        self.root = root or Path(__file__).resolve().parents[1]

    def _run(self, env_name: str, *args: str) -> None:
        defaults = {
            "R1_TTS_SAY_BIN": self.root / "build/hardware-tests/r1_tts_say",
            "R1_SAFE_WRIST_WAVE_BIN": self.root / "build/hardware-tests/r1_safe_wrist_wave",
            "R1_SAFE_RIGHT_SHOULDER_PITCH_BIN": self.root / "build/hardware-tests/r1_safe_right_shoulder_pitch_trial",
            "R1_FIXED_ACTION_BIN": self.root / "build/hardware-tests/r1_fixed_action",
            "R1_FIXED_LOCOMOTION_BIN": self.root / "build/gateway-full/r1-fixed-locomotion",
        }
        binary = os.getenv(env_name) or str(defaults[env_name])
        if not binary:
            raise RuntimeError(f"{env_name} is not configured")
        path = Path(binary)
        if not path.is_file() or not os.access(path, os.X_OK):
            raise RuntimeError(f"hardware binary is not executable: {path}")
        result = subprocess.run([str(path), self.interface, *args], input="START\n", text=True, check=False)
        if result.returncode:
            raise RuntimeError(f"hardware trial failed with exit code {result.returncode}")

    def speak(self, text: str) -> None:
        self._run("R1_TTS_SAY_BIN", text, "0")

    def arm(self, action: DemoAction) -> None:
        if action.name == "wrist_wave":
            self._run("R1_SAFE_WRIST_WAVE_BIN", "full")
        elif action.name == "right_shoulder_pitch":
            self._run("R1_SAFE_RIGHT_SHOULDER_PITCH_BIN", "full")
        else:
            self._run("R1_FIXED_ACTION_BIN", action.name)

    def move(self, action: DemoAction) -> None:
        self._run("R1_FIXED_LOCOMOTION_BIN", action.name)

    def turn(self, action: DemoAction) -> None:
        self._run("R1_FIXED_LOCOMOTION_BIN", action.name)

    def stop(self) -> None:
        # Fixed arm trials perform their own release; locomotion requires the Gateway.
        return None
