"""Stable CLI boundary; hardware execution is an isolated, operator-gated command."""

import argparse
import json
import os
from pathlib import Path
import subprocess

from motion_core.config import Settings
from motion_core.library import load_action_library
from motion_core.schemas import MotionPlan
from motion_core.simulator.collision_warning import scan_action_file


def emit(value: dict | list) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def command_status(_args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    emit({"connected": False, "gateway_target": settings.gateway_target, "motion_enabled": False, "network_interface": settings.network_interface, "mode": "offline"})
    return 0


def command_manifest(_args: argparse.Namespace) -> int:
    path = Path(__file__).resolve().parents[1] / "third_party_manifest.json"
    emit(json.loads(path.read_text(encoding="utf-8")))
    return 0


def command_list_actions(_args: argparse.Namespace) -> int:
    emit(load_action_library())
    return 0


def command_plan(args: argparse.Namespace) -> int:
    try:
        payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
        plan = MotionPlan.model_validate(payload)
    except Exception as error:
        emit({"valid": False, "executable": False, "errors": [str(error)], "motion_sent": False})
        return 2
    registry = {action["name"]: action for action in load_action_library()["actions"]}
    errors, unavailable = [], []
    for step in plan.steps:
        if step.type == "action":
            action = registry.get(step.action)
            if action is None:
                errors.append(f"action is not registered: {step.action}")
            elif not action["classroom_enabled"]:
                unavailable.append(step.action)
        elif step.type in {"move_for", "turn_relative"}:
            unavailable.append(step.type)
    emit({"valid": not errors, "executable": not errors and not unavailable, "errors": errors, "unavailable_actions": sorted(set(unavailable)), "motion_sent": False})
    return 0 if not errors else 2


def command_probe(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    interface = args.interface or settings.network_interface
    emit({"mode": "offline_host_probe", "network_interface": interface, "network_interface_exists": (Path("/sys/class/net") / interface).exists(), "robot_connection_attempted": False, "motion_sent": False, "next_step": "Run one named read-only hardware test after the physical checklist."})
    return 0


def command_collision_scan(args: argparse.Namespace) -> int:
    try:
        report = scan_action_file(
            Path(args.model),
            Path(args.file),
            warning_distance_m=args.warning_mm / 1000,
            danger_distance_m=args.danger_mm / 1000,
            sample_hz=args.sample_hz,
        )
    except Exception as error:
        emit({"valid": False, "hardware_authorized": False, "errors": [str(error)]})
        return 2
    emit(report)
    return 0 if report["passed"] else 2


HARDWARE_CASES = {
    "fsm-read": ("R1_LOCO_CLIENT_BIN", "read_only"),
    "lowstate-read": ("R1_ARM_FEEDBACK_TEST_BIN", "read_only"),
    "asr": ("R1_ASR_LISTENER_BIN", "read_only"),
    "tts": ("R1_TTS_SAY_BIN", "audio"),
    "wrist-wave": ("R1_SAFE_WRIST_WAVE_BIN", "motion"),
    "right-shoulder-pitch": ("R1_SAFE_RIGHT_SHOULDER_PITCH_BIN", "motion"),
}


def command_hardware_test(args: argparse.Namespace) -> int:
    if args.case == "list":
        emit({"tests": [{"name": name, "risk": value[1]} for name, value in HARDWARE_CASES.items()]})
        return 0
    environment_name, risk = HARDWARE_CASES[args.case]
    binary = os.getenv(environment_name)
    preview = {"case": args.case, "risk": risk, "configured_binary": binary, "motion_sent": False}
    if not args.run:
        emit(preview)
        return 0
    if risk == "motion" and args.confirm != "START":
        emit({**preview, "error": "motion requires --confirm START after the four-item physical checklist"})
        return 2
    if not binary or not Path(binary).is_file() or not os.access(binary, os.X_OK):
        emit({**preview, "error": f"set {environment_name} to an executable test binary"})
        return 2
    command = [binary, args.interface]
    if args.case == "fsm-read":
        command = [binary, f"--network_interface={args.interface}", "--get_fsm_id", "--get_fsm_mode"]
    elif args.case == "tts":
        command = [binary, args.interface, args.text, "0"]
    elif args.case in {"wrist-wave", "right-shoulder-pitch"}:
        command = [binary, args.interface, args.scale]
    completed = subprocess.run(command, check=False)
    emit({**preview, "exit_code": completed.returncode, "motion_sent": risk == "motion"})
    return completed.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status").set_defaults(handler=command_status)
    subparsers.add_parser("manifest").set_defaults(handler=command_manifest)
    subparsers.add_parser("list-actions").set_defaults(handler=command_list_actions)
    plan = subparsers.add_parser("plan")
    plan.add_argument("--file", required=True)
    plan.set_defaults(handler=command_plan)
    probe = subparsers.add_parser("probe")
    probe.add_argument("--interface")
    probe.set_defaults(handler=command_probe)
    simulate = subparsers.add_parser("collision-scan")
    simulate.add_argument("--model", required=True)
    simulate.add_argument("--file", required=True, help="degree-based named multi-joint action JSON")
    simulate.add_argument("--warning-mm", type=float, default=50)
    simulate.add_argument("--danger-mm", type=float, default=10)
    simulate.add_argument("--sample-hz", type=int, default=50)
    simulate.set_defaults(handler=command_collision_scan)
    hardware = subparsers.add_parser("hardware-test")
    hardware.add_argument("case", choices=["list", *HARDWARE_CASES])
    hardware.add_argument("--interface", default="enp7s0")
    hardware.add_argument("--run", action="store_true")
    hardware.add_argument("--confirm", default="")
    hardware.add_argument("--text", default="语音测试成功。")
    hardware.add_argument("--scale", choices=["small", "full"], default="small")
    hardware.set_defaults(handler=command_hardware_test)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.handler(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
