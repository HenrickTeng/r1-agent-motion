from __future__ import annotations

import argparse
import json
import sys
import time

from r1_agent.catalog import load_catalog, load_scene_pack, merge_scene
from r1_agent.executor import Executor, SimulatedBackend
from r1_agent.hardware import R1Hardware
from r1_agent.planner import DeepSeekPlanner, RulePlanner


def _planner(*, listen: bool, deepseek: bool, context: str = "", catalog=None):
    loaded = catalog or load_catalog()
    return DeepSeekPlanner(loaded, context=context) if listen or deepseek else RulePlanner(loaded)


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
    parser.add_argument(
        "--scene",
        default="",
        help="学生场景目录，内含 context.txt 和 pack.json（组合、别名、话术）",
    )
    parser.add_argument("--hardware", action="store_true")
    parser.add_argument(
        "--interface",
        default="auto",
        help="机器人网卡名；默认 auto，选用带 192.168.123.x 的网卡（Mac 常见 en5，Ubuntu 常见 enp7s0）",
    )
    parser.add_argument("--listen-timeout", type=int, default=45)
    parser.add_argument("--cooldown", type=float, default=4.0)
    parser.add_argument("--silence", type=float, default=3.0, help="说完后静音多少秒才提交本轮语音")
    args = parser.parse_args(argv)
    if args.continuous and not args.listen:
        parser.error("--continuous requires --listen")
    catalog = load_catalog()
    scene_context = ""
    if args.scene:
        pack = load_scene_pack(args.scene)
        catalog = merge_scene(catalog, pack)
        scene_context = pack.context
        print(json.dumps({"scene": args.scene, "compositions": sorted(pack.compositions)}, ensure_ascii=False), flush=True)
    context = "\n\n".join(part for part in (scene_context, args.context.strip()) if part)
    planner = _planner(listen=args.listen, deepseek=args.deepseek, context=context, catalog=catalog)
    robot = None
    if args.hardware or args.listen:
        from r1_agent.dds_robot import DdsRobot
        robot = DdsRobot(args.interface)
        print(json.dumps({"interface": robot._interface}, ensure_ascii=False), flush=True)
    backend = R1Hardware(args.interface, robot=robot) if args.hardware else SimulatedBackend()
    try:
        if args.text is not None:
            handle(" ".join(args.text), planner=planner, backend=backend, speak_reply=args.hardware)
            return 0
        while True:
            print("Listening on R1 ASR. Speak now...", flush=True)
            if args.hardware:
                backend.speak("请说")
                time.sleep(1.5)
            try:
                handle(
                    robot.listen(timeout_s=args.listen_timeout, silence_s=args.silence),
                    planner=planner,
                    backend=backend,
                    speak_reply=True,
                )
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
