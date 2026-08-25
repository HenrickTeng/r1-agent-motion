from pathlib import Path
import subprocess

import pytest

from motion_core.voice import SupervisedHardwareTrialTools, TRIAL_CONFIRMATION


def plan(action: str, parameters=None):
    return {
        "schema_version": "motion-plan/v2",
        "plan_id": "trial-plan",
        "require_operator_enable": True,
        "steps": [{"type": "action", "action": action, "parameters": parameters or {}}],
    }


def make_tools(tmp_path: Path, runner, confirmation=TRIAL_CONFIRMATION):
    binary = tmp_path / "trial"
    binary.write_text("test")
    binary.chmod(0o700)
    return SupervisedHardwareTrialTools(
        action_name="wrist_wave",
        title="移动右手腕关节",
        binary=binary,
        interface="test0",
        scale="full",
        authorized_session_id="video-001",
        confirmation=confirmation,
        runner=runner,
    )


def test_trial_requires_explicit_confirmation(tmp_path):
    with pytest.raises(PermissionError):
        make_tools(tmp_path, lambda *args, **kwargs: None, confirmation="wrong")


def test_trial_rejects_other_actions_and_parameters(tmp_path):
    tools = make_tools(tmp_path, lambda *args, **kwargs: None)
    assert tools.validate_plan(plan("other"))[1]
    assert tools.validate_plan(plan("wrist_wave", {"scale": 2}))[1]


def test_trial_executes_fixed_binary_once(tmp_path):
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="return_error_rad=0.001\n", stderr="")

    tools = make_tools(tmp_path, runner)
    execution_id = tools.execute_plan(plan("wrist_wave"), "video-001", "once")
    assert execution_id.startswith("hardware-trial-")
    assert calls[0][0][1:] == ["test0", "full"]
    assert calls[0][1]["input"] == "START\n"
    with pytest.raises(PermissionError):
        tools.execute_plan(plan("wrist_wave"), "video-001", "twice")


def test_trial_rejects_wrong_session(tmp_path):
    tools = make_tools(tmp_path, lambda *args, **kwargs: None)
    with pytest.raises(PermissionError):
        tools.execute_plan(plan("wrist_wave"), "wrong-session", "once")
