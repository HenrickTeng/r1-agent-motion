from __future__ import annotations

import platform
import subprocess

ROBOT_PREFIX = "192.168.123."


def resolve_interface(name: str = "auto") -> str:
    if name and name not in ("auto",):
        return name
    found = _interface_on_robot_lan()
    if found:
        return found
    raise RuntimeError(
        "没有网卡在 192.168.123.x（机器人网段）。走跑模式只需网线直连，不要进调试。"
        "请接上 enp7s0 或把笔记本地址配成 192.168.123.99。"
    )


def _interface_on_robot_lan() -> str | None:
    if platform.system() == "Darwin":
        output = subprocess.run(["ifconfig"], capture_output=True, text=True, check=False).stdout
        current = None
        for line in output.splitlines():
            if line and not line[:1].isspace() and ":" in line:
                current = line.split(":", 1)[0]
            elif current and "inet " in line:
                address = line.split()[1]
                if address.startswith(ROBOT_PREFIX):
                    return current
        return None
    output = subprocess.run(["ip", "-4", "-o", "addr", "show"], capture_output=True, text=True, check=False).stdout
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[2] == "inet" and parts[3].startswith(ROBOT_PREFIX):
            return parts[1]
    return None
