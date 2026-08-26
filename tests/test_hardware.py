import subprocess
from pathlib import Path

from r1_agent.catalog import load_catalog
from r1_agent.hardware import R1Hardware


def test_arm_uses_fixed_runner(monkeypatch):
    calls = []
    monkeypatch.setattr(R1Hardware, "_binary", lambda self, env_name, relative: Path(relative))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: calls.append((command, kwargs.get("input"))) or subprocess.CompletedProcess(command, 0),
    )
    hardware = R1Hardware()
    hardware.arm(load_catalog().actions["hands_forward"])
    assert calls[0][0][-1] == "hands_forward"
    assert calls[0][1] == "START\n"
    assert "r1_fixed_action" in calls[0][0][0]


def test_wrist_wave_uses_same_fixed_runner(monkeypatch):
    calls = []
    monkeypatch.setattr(R1Hardware, "_binary", lambda self, env_name, relative: Path(relative))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: calls.append(command) or subprocess.CompletedProcess(command, 0),
    )
    hardware = R1Hardware()
    hardware.arm(load_catalog().actions["wrist_wave"])
    assert calls[0][-1] == "wrist_wave"
