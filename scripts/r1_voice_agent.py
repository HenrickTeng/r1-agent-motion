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
from motion_core.voice import select_transcript


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
    parser.add_argument("--provider", choices=["rule", "deepseek"], default="rule")
    parser.add_argument("--mode", choices=["execute", "design"], default="execute")
    parser.add_argument("--bridge-url")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--session-id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--interface", default="enp7s0")
    parser.add_argument("--asr-binary", type=Path, default=ROOT / "build/hardware-tests/r1_asr_listener")
    parser.add_argument("--tts-binary", type=Path, default=ROOT / "build/hardware-tests/r1_tts_say")
    parser.add_argument("--listen-timeout", type=int, default=30)
    parser.add_argument("--minimum-confidence", type=float, default=0.45)
    parser.add_argument("--cooldown", type=float, default=2.5)
    args = parser.parse_args()
    tools = HttpTools(args.bridge_url) if args.bridge_url else create_app().state.service
    adapter = DeepSeekAdapter() if args.provider == "deepseek" else LocalSafetyAdapter()
    agent = AgentService(adapter, tools)
    try:
        if args.text is not None:
            handle(args.text, args, agent)
            return 0
        while True:
            handle(listen_once(args), args, agent)
            if not args.continuous:
                return 0
            time.sleep(args.cooldown)
    except KeyboardInterrupt:
        return 0
    except Exception as error:
        print(json.dumps({"error": str(error), "motion_sent": False}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
