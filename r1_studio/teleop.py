from __future__ import annotations

MAX_VX = 0.5
MAX_VY = 0.5
MAX_OMEGA = 1.0

# 与能走的语音原子 move_forward_slow 同一套速度。
_KEY_TWIST = {
    "w": (MAX_VX, 0.0, 0.0),
    "s": (-MAX_VX, 0.0, 0.0),
    "a": (0.0, MAX_VY, 0.0),
    "d": (0.0, -MAX_VY, 0.0),
    "q": (0.0, 0.0, MAX_OMEGA),
    "e": (0.0, 0.0, -MAX_OMEGA),
    "arrowup": (MAX_VX, 0.0, 0.0),
    "arrowdown": (-MAX_VX, 0.0, 0.0),
    "arrowleft": (0.0, 0.0, MAX_OMEGA),
    "arrowright": (0.0, 0.0, -MAX_OMEGA),
}


def clamp_twist(vx: float, vy: float, omega: float) -> tuple[float, float, float]:
    return (
        max(-MAX_VX, min(MAX_VX, float(vx))),
        max(-MAX_VY, min(MAX_VY, float(vy))),
        max(-MAX_OMEGA, min(MAX_OMEGA, float(omega))),
    )


def normalize_key(raw: str) -> str:
    key = raw.strip().lower()
    if key.startswith("key") and len(key) == 4:
        return key[3:]
    if key.startswith("arrow"):
        return key
    return key


def keys_to_twist(keys: list[str], *, slow: bool = False) -> tuple[float, float, float]:
    vx = vy = omega = 0.0
    for raw in keys:
        part = _KEY_TWIST.get(normalize_key(raw))
        if part is None:
            continue
        vx += part[0]
        vy += part[1]
        omega += part[2]
    if slow:
        vx *= 0.5
        vy *= 0.5
        omega *= 0.5
    return clamp_twist(vx, vy, omega)


def twist_duration(vx: float, vy: float, omega: float) -> float:
    """和 actions.json 能走的原子对齐：前进 0.5s，横移 1.0s。"""
    vx, vy, omega = clamp_twist(vx, vy, omega)
    if abs(vx) + abs(vy) + abs(omega) < 1e-3:
        return 0.0
    if abs(vy) >= 0.05:
        return 1.0
    if abs(vx) >= 0.05:
        return 0.5
    return 0.35
