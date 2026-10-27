"""只订阅 rt/lowstate，不发 arm_sdk、不调 LocoClient。走跑模式即可。"""

from __future__ import annotations

import math
import time

from r1_agent.dds_robot import JOINTS, READY_POSE_DEG
from r1_agent.interface import resolve_interface

_NAMES = (
    "LSP",
    "LSR",
    "LSY",
    "LE",
    "LWR",
    "RSP",
    "RSR",
    "RSY",
    "RE",
    "RWR",
    "WY",
    "HP",
    "HY",
)


def run_read_lowstate(*, interface: str = "auto", timeout_s: float = 8.0) -> int:
    from r1_agent.dds_setup import prepare_cyclonedds

    prepare_cyclonedds()
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
    from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowState_

    nic = resolve_interface(interface)
    print(f"只读 lowstate，网卡 {nic}。不进调试、不发 arm_sdk。")
    ChannelFactoryInitialize(0, nic)
    box: list = []

    def on_state(msg) -> None:
        if not box:
            box.append(msg)

    sub = ChannelSubscriber("rt/lowstate", LowState_)
    sub.Init(on_state, 10)
    deadline = time.time() + timeout_s
    while not box and time.time() < deadline:
        time.sleep(0.05)
    if not box:
        print(f"rt/lowstate 超时 {timeout_s:.0f}s。检查网线、走跑是否已站起。")
        return 1
    msg = box[0]
    print("关节角（度）  当前 / 走跑待机")
    for index, name in enumerate(_NAMES):
        deg = math.degrees(float(msg.motor_state[JOINTS[index]].q))
        print(f"  {name:4s} {deg:8.3f}   {READY_POSE_DEG[index]:8.3f}")
    roll, pitch, yaw = msg.imu_state.rpy
    print(f"IMU rpy(rad) roll={roll:.3f} pitch={pitch:.3f} yaw={yaw:.3f}")
    return 0
