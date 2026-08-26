from __future__ import annotations

import argparse
import json
import sys
import time

from r1_agent.executor import Executor, SimulatedBackend
from r1_agent.hardware import R1Hardware
from r1_agent.planner import DeepSeekPlanner, RulePlanner


def _planner(deepseek: bool):
    return DeepSeekPlanner() if deepseek else RulePlanner()


def handle(text: str, *, planner, backend, speak_reply: bool) -> None:
    reply, actions = planner.plan(text)
    print(json.dumps({"heard": text, "reply": reply, "actions": [action.name for action in actions]}, ensure_ascii=False), flush=True)
    if speak_reply:
        backend.speak(reply)
    if actions:
        Executor(backend).execute(actions)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan and run named R1 actions from text or ASR.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", nargs="+")
    source.add_argument("--listen", action="store_true")
    parser.add_argument("--continuous", action="store_true")
    parser.add_argument("--deepseek", action="store_true")
    parser.add_argument("--hardware", action="store_true")
    parser.add_argument("--interface", default="en5")
    parser.add_argument("--listen-timeout", type=int, default=30)
    parser.add_argument("--cooldown", type=float, default=2.5)
    args = parser.parse_args(argv)
    if args.continuous and not args.listen:
        parser.error("--continuous requires --listen")
    planner = _planner(args.deepseek)
    robot = None
    if args.hardware or args.listen:
        from r1_agent.dds_robot import DdsRobot
        robot = DdsRobot(args.interface)
    backend = R1Hardware(args.interface, robot=robot) if args.hardware else SimulatedBackend()
    try:
        if args.text is not None:
            handle(" ".join(args.text), planner=planner, backend=backend, speak_reply=args.hardware)
            return 0
        while True:
            handle(
                robot.listen(timeout_s=args.listen_timeout),
                planner=planner,
                backend=backend,
                speak_reply=True,
            )
            if not args.continuous:
                return 0
            time.sleep(args.cooldown)
    except KeyboardInterrupt:
        return 0
    except Exception as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
