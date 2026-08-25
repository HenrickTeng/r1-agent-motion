import json
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "r1ctl"


def run_cli(*arguments, env=None):
    return subprocess.run([str(CLI), *arguments], cwd=ROOT, text=True, capture_output=True, env=env, check=False)


def test_cli_lists_pack_without_dance_or_jump():
    result = run_cli("list-actions")
    assert result.returncode == 0
    names = [action["name"] for action in json.loads(result.stdout)["actions"]]
    assert "wrist_wave" in names and "dance" not in names and "jump" not in names
    assert len(names) == 36
    assert {"move_forward_slow", "move_left_slow", "turn_left_10"} <= set(names)


def test_cli_rejects_unregistered_action(tmp_path):
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"schema_version": "motion-plan/v2", "plan_id": "bad-001", "require_operator_enable": True, "steps": [{"type": "action", "action": "dance", "parameters": {}}]}))
    result = run_cli("plan", "--file", str(plan))
    assert result.returncode == 2
    assert json.loads(result.stdout)["motion_sent"] is False


def test_motion_binary_never_runs_without_confirmation():
    env = {**os.environ, "R1_SAFE_WRIST_WAVE_BIN": "/bin/true"}
    result = run_cli("hardware-test", "wrist-wave", "--run", env=env)
    assert result.returncode == 2
    assert json.loads(result.stdout)["motion_sent"] is False
