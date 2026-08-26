#!/usr/bin/env python3
"""R1 ASR -> Agent -> TTS loop; motion remains Teacher Bridge gated."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
if VENV_PYTHON.exists() and Path(sys.prefix).resolve() != (ROOT / ".venv").resolve():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), __file__, *sys.argv[1:]])
sys.path.insert(0, str(ROOT))

import httpx

from apps.teacher_bridge.api import create_app
from motion_core.agent.adapters import DeepSeekAdapter, LocalSafetyAdapter
from motion_core.agent.service import AgentService
from motion_core.demo import DEMO_ACTIONS, DemoExecutor
from motion_core.demo_hardware import R1DemoHardware
from motion_core.schemas import MotionPlan
from motion_core.voice import PcMicRecognizer, SupervisedHardwareTrialTools, select_transcript


class HttpTools:
    def __init__(self, base_url: str) -> None:
        self.client = httpx.Client(base_url=base_url, timeout=10)

    def list_actions(self) -> list[dict]:
        response = self.client.get("/v1/robot/actions")
        response.raise_for_status()
        return response.json()["actions"]

    def validate_plan(self, payload: dict):
        response = self.client.post("/v1/robot/plans:validate", json={"plan": payload})
        response.raise_for_status()
        report = response.json()
        return payload if report["valid"] else None, report["errors"]

    def execute_plan(self, payload: dict, session_id: str, idempotency_key: str) -> str:
        response = self.client.post(
            "/v1/robot/plans:execute",
            json={"plan": payload, "session_id": session_id},
            headers={"Idempotency-Key": idempotency_key},
        )
        response.raise_for_status()
        return response.json()["execution_id"]


class DiyDirectTools:
    allowed = {
        "move_forward_slow",
        "move_backward_slow",
        "turn_left_rpc",
        "turn_right_rpc",
        "wrist_wave",
        "right_shoulder_pitch",
        "wave_right",
        "wave_left",
        "raise_hand_left",
        "raise_hand_right",
        "open_arms",
        "hands_forward",
    }

    def __init__(self, interface: str) -> None:
        self.executor = DemoExecutor(R1DemoHardware(interface=interface, root=ROOT))

    def list_actions(self) -> list[dict]:
        return [
            {"name": name, "title": DEMO_ACTIONS[name].title, "parameters": {}}
            for name in sorted(self.allowed)
        ]

    def validate_plan(self, payload: dict):
        try:
            plan = MotionPlan.model_validate(payload)
        except Exception as error:
            return None, [str(error)]
        errors = []
        for step in plan.steps:
            if step.type != "action":
                errors.append(f"step type is not enabled in DIY direct mode: {step.type}")
            elif step.action not in self.allowed:
                errors.append(f"action is not enabled in DIY direct mode: {step.action}")
        return (plan if not errors else None), errors

    def execute_plan(self, payload: dict, session_id: str, idempotency_key: str) -> str:
        del idempotency_key
        if not session_id:
            raise PermissionError("DIY direct mode requires --session-id")
        plan, errors = self.validate_plan(payload)
        if plan is None or errors:
            raise RuntimeError(errors[0])
        actions = [DEMO_ACTIONS[step.action] for step in plan.steps]
        self.executor.execute(actions)
        return f"diy-{uuid4().hex}"


def listen_once(args) -> str:
    completed = subprocess.run(
        [str(args.asr_binary), args.interface, str(args.listen_timeout)],
        text=True,
        capture_output=True,
        timeout=args.listen_timeout + 5,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or "R1 ASR failed")
    return select_transcript(completed.stdout, minimum_confidence=args.minimum_confidence)["text"]


def speak(text: str, args) -> None:
    if args.dry_run:
        return
    completed = subprocess.run(
        [str(args.tts_binary), args.interface, text, "0"],
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or "R1 TTS failed")
    print(completed.stdout.strip() or "tts_return_code=0", flush=True)


def handle(text: str, args, agent: AgentService) -> bool:
    try:
        result = agent.handle(text, mode=args.mode, execute=False)
    except Exception:
        if args.provider != "deepseek":
            raise
        result = AgentService(LocalSafetyAdapter(), agent.tools).handle(
            text, mode="execute", execute=False
        )
        result["reply"] = "云端服务暂时不可用。" + result["reply"]
    print(json.dumps({"student": text, **result}, ensure_ascii=False), flush=True)
    speak(result["reply"], args)
    if result.get("plan") and args.execute:
        if not args.session_id:
            raise RuntimeError("--execute requires an operator-enabled --session-id")
        execution_id = agent.tools.execute_plan(
            result["plan"], args.session_id, f"voice-{uuid4().hex}"
        )
        print(json.dumps({"execution_id": execution_id, "motion_sent": True}), flush=True)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text")
    source.add_argument("--listen-once", action="store_true")
    source.add_argument("--continuous", action="store_true")
    source.add_argument("--pc-mic-once", action="store_true")
    source.add_argument("--pc-mic-continuous", action="store_true")
    parser.add_argument("--provider", choices=["rule", "deepseek"], default="rule")
    parser.add_argument("--mode", choices=["execute", "design"], default="execute")
    parser.add_argument("--bridge-url")
    parser.add_argument("--diy-direct", action="store_true", help="不启动 Bridge，直接执行已验收的固定动作")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--session-id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--interface", default="enp7s0")
    parser.add_argument("--asr-binary", type=Path, default=ROOT / "build/hardware-tests/r1_asr_listener")
    parser.add_argument("--tts-binary", type=Path, default=ROOT / "build/hardware-tests/r1_tts_say")
    parser.add_argument("--listen-timeout", type=int, default=30)
    parser.add_argument("--minimum-confidence", type=float, default=0.45)
    parser.add_argument("--pc-mic-device", default="pulse")
    parser.add_argument("--record-seconds", type=int, default=4)
    parser.add_argument(
        "--vosk-model",
        type=Path,
        default=Path.home() / ".cache/r1-agent-motion/vosk-model-small-cn-0.22",
    )
    parser.add_argument("--cooldown", type=float, default=2.5)
    parser.add_argument("--supervised-trial", choices=["wrist-full", "shoulder-full"])
    parser.add_argument("--trial-confirmation", default="")
    args = parser.parse_args()
    if args.diy_direct and args.bridge_url:
        parser.error("--diy-direct cannot be combined with --bridge-url")
    if args.diy_direct and args.provider != "rule":
        parser.error("--diy-direct currently supports --provider rule only")
    if args.diy_direct and args.execute and (args.listen_once or args.continuous):
        parser.error("DIY execution cannot use onboard ASR; use --pc-mic-once or --pc-mic-continuous")
    if args.supervised_trial:
        if args.bridge_url:
            parser.error("--supervised-trial cannot be combined with --bridge-url")
        if not args.session_id:
            parser.error("--supervised-trial requires --session-id")
        trials = {
            "wrist-full": (
                "wrist_wave",
                "移动右手腕关节",
                ROOT / "build/hardware-tests/r1_safe_wrist_wave",
            ),
            "shoulder-full": (
                "right_shoulder_pitch_trial",
                "移动右肩关节",
                ROOT / "build/hardware-tests/r1_safe_right_shoulder_pitch_trial",
            ),
        }
        action_name, title, binary = trials[args.supervised_trial]
        tools = SupervisedHardwareTrialTools(
            action_name=action_name,
            title=title,
            binary=binary,
            interface=args.interface,
            scale="full",
            authorized_session_id=args.session_id,
            confirmation=args.trial_confirmation,
        )
    elif args.diy_direct:
        tools = DiyDirectTools(args.interface)
    else:
        tools = HttpTools(args.bridge_url) if args.bridge_url else create_app().state.service
    adapter = DeepSeekAdapter() if args.provider == "deepseek" else LocalSafetyAdapter()
    agent = AgentService(adapter, tools)
    pc_mic = None
    if args.pc_mic_once or args.pc_mic_continuous:
        pc_mic = PcMicRecognizer(args.vosk_model, args.pc_mic_device, args.record_seconds)
    try:
        if args.text is not None:
            handle(args.text, args, agent)
            return 0
        while True:
            text = pc_mic.listen() if pc_mic else listen_once(args)
            print(f"识别文本: {text}", flush=True)
            handle(text, args, agent)
            if not args.continuous and not args.pc_mic_continuous:
                return 0
            time.sleep(args.cooldown)
    except KeyboardInterrupt:
        return 0
    except Exception as error:
        print(json.dumps({"error": str(error), "motion_sent": False}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
