from __future__ import annotations

import argparse
import json
import sys
import time

from r1_agent.executor import Executor, SimulatedBackend
from r1_agent.hardware import R1Hardware
from r1_agent.planner import DeepSeekPlanner, RulePlanner
from r1_agent.asr import UnsupportedTranscriptLanguage


def _planner(*, listen: bool, deepseek: bool, context: str = ""):
    return DeepSeekPlanner(context=context) if listen or deepseek else RulePlanner()


def handle(text: str, *, planner, backend, speak_reply: bool) -> None:
    reply, actions = planner.plan(text)
    print(json.dumps({"heard": text, "reply": reply, "actions": [action.name for action in actions]}, ensure_ascii=False), flush=True)
    if actions:
        Executor(backend).execute(actions)
    if speak_reply:
        backend.speak(reply)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan and run named R1 actions from text or ASR.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", nargs="+")
    source.add_argument("--listen", action="store_true")
    parser.add_argument("--continuous", action="store_true")
    parser.add_argument("--deepseek", action="store_true")
    parser.add_argument(
        "--context",
        default="",
        help="提供给 DeepSeek 的初始上下文（身份、场景、回答风格等）",
    )
    parser.add_argument("--hardware", action="store_true")
    parser.add_argument(
        "--interface",
        default="enp7s0",
        help="连接机器人的网卡名（Ubuntu 默认 enp7s0，可用 ip a 查看）",
    )
    parser.add_argument("--listen-timeout", type=int, default=30)
    parser.add_argument("--cooldown", type=float, default=4.0)
    args = parser.parse_args(argv)
    if args.continuous and not args.listen:
        parser.error("--continuous requires --listen")
    planner = _planner(listen=args.listen, deepseek=args.deepseek, context=args.context)
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
            print("Listening on R1 ASR. Speak now...", flush=True)
            try:
                handle(
                    robot.listen(timeout_s=args.listen_timeout),
                    planner=planner,
                    backend=backend,
                    speak_reply=True,
                )
            except UnsupportedTranscriptLanguage as error:
                print(json.dumps({"discarded": str(error)}, ensure_ascii=False), flush=True)
                if not args.continuous:
                    return 0
                time.sleep(args.cooldown)
                continue
            except Exception as error:
                print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
                if not args.continuous:
                    return 2
                try:
                    backend.speak("这个动作当前没法执行，我停在这里。")
                except Exception:
                    pass
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
