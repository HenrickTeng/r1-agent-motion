#!/usr/bin/env python3
"""Offline-safe text entry for the model-agnostic R1 classroom agent."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.teacher_bridge.api import create_app
from motion_core.agent.adapters import DeepSeekAdapter, LocalSafetyAdapter
from motion_core.agent.service import AgentService


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", required=True)
    parser.add_argument("--provider", choices=["rule", "deepseek"], default="rule")
    parser.add_argument("--mode", choices=["execute", "design"], default="execute")
    parser.add_argument("--dry-run", action="store_true", default=True)
    args = parser.parse_args()
    tools = create_app().state.service
    adapter = DeepSeekAdapter() if args.provider == "deepseek" else LocalSafetyAdapter()
    try:
        result = AgentService(adapter, tools).handle(args.text, mode=args.mode, execute=False)
    except Exception as error:
        result = {"reply": "服务暂时不可用，我不会执行动作。", "intent": "conversation", "motion_sent": False, "error": str(error)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if "error" not in result else 2


if __name__ == "__main__":
    raise SystemExit(main())
