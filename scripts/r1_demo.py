#!/usr/bin/env python3
"""Run the minimal local R1 Agent demo in simulation mode."""
import argparse
from motion_core.demo import DemoExecutor, DemoPlanner, SimulatedBackend

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("text", nargs="+")
    parser.add_argument("--hardware", action="store_true")
    parser.add_argument("--interface", default="enp7s0")
    args = parser.parse_args()
    planner = DemoPlanner()
    reply, actions = planner.plan(" ".join(args.text))
    print(f"AGENT: {reply}")
    if actions:
        if args.hardware:
            from motion_core.demo_hardware import R1DemoHardware
            backend = R1DemoHardware(args.interface)
        else:
            backend = SimulatedBackend()
        DemoExecutor(backend).execute(actions)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
