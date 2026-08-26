import subprocess

from motion_core.demo import DEMO_ACTIONS
from motion_core.demo_hardware import R1DemoHardware


def test_experimental_arm_action_uses_fixed_runner(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs: calls.append(command) or subprocess.CompletedProcess(command, 0))
    hardware = R1DemoHardware()
    hardware.arm(DEMO_ACTIONS["hands_forward"])
    assert calls[0][-1] == "hands_forward"


def test_validated_trial_uses_dedicated_binary(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs: calls.append(command) or subprocess.CompletedProcess(command, 0))
    hardware = R1DemoHardware()
    hardware.arm(DEMO_ACTIONS["wrist_wave"])
    assert calls[0][-1] == "full"
