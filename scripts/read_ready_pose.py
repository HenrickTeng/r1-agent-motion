#!/usr/bin/env python3
"""读取 R1 ready_pose 绝对角度（真机，机器人站好后运行一次）。

用途：
    记录 R1 13 个关节（上肢+腰+头）在「准备姿态」下的绝对角度，
    作为后续「动作清单存绝对角度」改造的零位参考。

前提：
    1. 机器人开机、站好（StandUp 或遥控器站立），摆好你认定的「准备姿态」；
    2. 网线直连；默认使用 SDK 自动网卡配置；
    3. 已装 unitree_sdk2_python（吴博版环境已满足）。

用法（在 Ubuntu 项目根目录）：
    PYTHONPATH=. python3 scripts/read_ready_pose.py

输出：13 个关节的 q（弧度）+ 度，以及可直接贴回改造用的 JSON。
"""
import argparse
import json
import math
import time

from r1_agent.dds_setup import prepare_cyclonedds

prepare_cyclonedds()
from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowState_

JOINTS = (15, 16, 17, 18, 19, 22, 23, 24, 25, 26, 13, 29, 30)
NAMES = ["LSP", "LSR", "LSY", "LE", "LWR", "RSP", "RSR", "RSY", "RE", "RWR", "WY", "HP", "HY"]


def main() -> int:
    ap = argparse.ArgumentParser(description="读取 R1 ready_pose 绝对角度")
    ap.add_argument("--interface", default="auto", help="网卡名；默认 auto，选用 192.168.123.x")
    ap.add_argument("--samples", type=int, default=10, help="采样次数取平均")
    args = ap.parse_args()

    from r1_agent.interface import resolve_interface

    ChannelFactoryInitialize(0, resolve_interface(args.interface))
    holder: dict = {}

    def on_lowstate(msg) -> None:
        holder["q"] = [float(msg.motor_state[j].q) for j in JOINTS]

    sub = ChannelSubscriber("rt/lowstate", LowState_)
    sub.Init(on_lowstate, 10)

    collected: list[list[float]] = []
    deadline = time.time() + 3
    while time.time() < deadline and len(collected) < args.samples:
        if "q" in holder:
            collected.append(holder["q"])
        time.sleep(0.1)

    if not collected:
        print("❌ 未收到 rt/lowstate。请确认：①机器人已开机 ②网卡名正确 ③机器人已站好")
        return 1

    avg = [sum(row[i] for row in collected) / len(collected) for i in range(13)]
    print("=" * 56)
    print("READY_POSE 绝对角度（当前站姿，采样平均）")
    print("=" * 56)
    out: dict = {}
    for name, joint, q in zip(NAMES, JOINTS, avg):
        deg = math.degrees(q)
        out[name] = round(deg, 3)
        print(f"  {name:<4} (joint {joint:2d})  {q:+.6f} rad  =  {deg:+9.3f}°")
    print("=" * 56)
    print("JSON（直接贴回给改造用）：")
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
