"""手势控制，对齐大疆 Neo；真机默认人和 R1 **面对面**。

单手张开手掌：按**你自己的左/右**横移（不管上下）。
面对面时：你的左 = 机器人的右（vy<0），不要用机器人自身的左右当画面左右。
双手张开手掌：分开飞远（后退），合拢飞近（前进）。
食指左右指 → 朝你指的那一侧转。握拳停下。比耶欢呼。
"""

from __future__ import annotations

from dataclasses import dataclass

from r1_studio.teleop import MAX_OMEGA, MAX_VX, MAX_VY

WRIST, INDEX_PIP, INDEX_TIP = 0, 6, 8
MIDDLE_PIP, MIDDLE_TIP = 10, 12
RING_PIP, RING_TIP = 14, 16
PINKY_PIP, PINKY_TIP = 18, 20
MIDDLE_MCP = 9
DEADZONE = 0.12


def operator_nx(image_nx: float, *, mirrored: bool) -> float:
    """把画面坐标换成操作者身体左右。负值 = 操作者自己的左边。

    机载摄像头不镜像：面对面站着，人的左手在画面右边。
    笔记本预览会左右翻转，使画面左边就是人的左边。
    """
    return image_nx if mirrored else -image_nx


def face_to_face_strafe(operator_nx: float) -> float:
    """面对面：人往自己左边挥，机器人应往人的左边走 = 机器人右移 (vy<0)。"""
    return max(-MAX_VY, min(MAX_VY, operator_nx * MAX_VY))


def face_to_face_yaw(operator_nx: float) -> float:
    """面对面：人指向自己左边，机器人朝那一侧转 = 右转 (omega<0)。"""
    return max(-MAX_OMEGA, min(MAX_OMEGA, operator_nx * MAX_OMEGA))


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class GestureCommand:
    kind: str
    vx: float = 0.0
    vy: float = 0.0
    omega: float = 0.0
    label: str = "未检测到手"
    pose: str = "none"


def _pt(hand: list, index: int) -> Point:
    item = hand[index]
    if isinstance(item, dict):
        return Point(float(item["x"]), float(item["y"]))
    return Point(float(item.x), float(item.y))


def _extended(tip: Point, pip: Point) -> bool:
    return tip.y < pip.y - 0.02


def finger_flags(hand: list) -> dict[str, bool]:
    return {
        "index": _extended(_pt(hand, INDEX_TIP), _pt(hand, INDEX_PIP)),
        "middle": _extended(_pt(hand, MIDDLE_TIP), _pt(hand, MIDDLE_PIP)),
        "ring": _extended(_pt(hand, RING_TIP), _pt(hand, RING_PIP)),
        "pinky": _extended(_pt(hand, PINKY_TIP), _pt(hand, PINKY_PIP)),
    }


def classify_hand(hand: list) -> str:
    if len(hand) < 21:
        return "none"
    flags = finger_flags(hand)
    up = sum(flags.values())
    if flags["index"] and flags["middle"] and not flags["ring"] and not flags["pinky"]:
        return "peace"
    if up >= 3:
        return "palm"
    if flags["index"] and not flags["middle"] and not flags["ring"] and not flags["pinky"]:
        return "point"
    if up == 0 or (up == 1 and not flags["index"]):
        return "fist"
    return "other"


def _palm_center(hand: list) -> Point:
    wrist = _pt(hand, WRIST)
    mcp = _pt(hand, MIDDLE_MCP)
    return Point((wrist.x + mcp.x) / 2, (wrist.y + mcp.y) / 2)


def palms_span(left: list, right: list) -> float:
    a, b = _palm_center(left), _palm_center(right)
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5


def _axis(value: float, center: float, span: float) -> float:
    n = (value - center) / span
    if abs(n) < DEADZONE:
        return 0.0
    return max(-1.0, min(1.0, n))


def drive_label(
    vx: float,
    vy: float,
    omega: float,
    *,
    two_hands: bool = False,
    operator_nx: float = 0.0,
) -> str:
    """左/右按操作者自己的方向说，不按机器人机身左右。"""
    if two_hands:
        if vx > 0.08:
            return "飞近（前进）"
        if vx < -0.08:
            return "飞远（后退）"
        return "双手间距居中 · 悬停"
    if abs(omega) > 0.15 and abs(vy) < 0.04:
        return "左转" if operator_nx < 0 else "右转"
    if operator_nx < -DEADZONE:
        return "左移"
    if operator_nx > DEADZONE:
        return "右移"
    return "掌心居中 · 悬停"


def palm_to_twist(hand: list, *, mirrored: bool = False, face_to_face: bool = True) -> tuple[float, float, float]:
    """单手只左右横移。默认面对面：你的左 → 机器人右移。"""
    center = _palm_center(hand)
    image_nx = _axis(center.x, 0.5, 0.32)
    op = operator_nx(image_nx, mirrored=mirrored)
    vy = face_to_face_strafe(op) if face_to_face else max(-MAX_VY, min(MAX_VY, -op * MAX_VY))
    return 0.0, vy, 0.0


def two_palms_to_twist(hand_a: list, hand_b: list, *, rest_span: float) -> tuple[float, float, float]:
    """双手：分开=飞远(后退)，合拢=飞近(前进)。越过阈值就用和键盘 W/S 一样的 0.5m/s。"""
    span = palms_span(hand_a, hand_b)
    ratio = (span - rest_span) / max(rest_span, 1e-4)
    vx = 0.0
    if ratio > 0.12:
        vx = -MAX_VX
    elif ratio < -0.12:
        vx = MAX_VX
    return vx, 0.0, 0.0


def point_to_twist(hand: list, *, mirrored: bool = False, face_to_face: bool = True) -> tuple[float, float, float]:
    tip = _pt(hand, INDEX_TIP)
    image_nx = _axis(tip.x, 0.5, 0.32)
    op = operator_nx(image_nx, mirrored=mirrored)
    omega = face_to_face_yaw(op) if face_to_face else max(-MAX_OMEGA, min(MAX_OMEGA, -op * MAX_OMEGA))
    return 0.0, 0.0, omega


class GesturePilot:
    def __init__(
        self,
        *,
        peace_hold_s: float = 0.35,
        cheer_cooldown_s: float = 4.0,
        mirrored: bool = False,
        face_to_face: bool = True,
    ) -> None:
        self.peace_hold_s = peace_hold_s
        self.cheer_cooldown_s = cheer_cooldown_s
        self.mirrored = mirrored
        self.face_to_face = face_to_face
        self._peace_since: float | None = None
        self._last_cheer: float = -1e9
        self._rest_span: float | None = None

    def reset(self) -> None:
        self._peace_since = None
        self._rest_span = None

    def step(self, hands: list[list], now: float) -> GestureCommand:
        if not hands:
            self.reset()
            return GestureCommand("idle", label="未检测到手", pose="none")
        poses = [classify_hand(hand) for hand in hands]
        if "peace" in poses and now - self._last_cheer >= self.cheer_cooldown_s:
            self._rest_span = None
            if self._peace_since is None:
                self._peace_since = now
            if now - self._peace_since >= self.peace_hold_s:
                self._last_cheer = now
                self._peace_since = None
                return GestureCommand("cheer", label="比耶 → 欢呼", pose="peace")
            return GestureCommand("idle", label="比耶保持中…", pose="peace")
        self._peace_since = None
        if "fist" in poses:
            self._rest_span = None
            return GestureCommand("stop", label="握拳停下", pose="fist")
        palm_hands = [hand for hand, pose in zip(hands, poses) if pose == "palm"]
        if len(palm_hands) >= 2:
            if self._rest_span is None:
                self._rest_span = max(palms_span(palm_hands[0], palm_hands[1]), 0.08)
                return GestureCommand("idle", label="双手跟距：分开飞远，合拢飞近", pose="palm")
            vx, vy, omega = two_palms_to_twist(palm_hands[0], palm_hands[1], rest_span=self._rest_span)
            label = drive_label(vx, vy, omega, two_hands=True)
            if abs(vx) < 1e-3:
                return GestureCommand("idle", label=label, pose="palm")
            return GestureCommand("drive", vx=vx, vy=vy, omega=omega, label=label, pose="palm")
        self._rest_span = None
        if len(palm_hands) == 1:
            vx, vy, omega = palm_to_twist(
                palm_hands[0], mirrored=self.mirrored, face_to_face=self.face_to_face
            )
            op = operator_nx(_axis(_palm_center(palm_hands[0]).x, 0.5, 0.32), mirrored=self.mirrored)
            label = drive_label(vx, vy, omega, operator_nx=op)
            if abs(vy) < 1e-3:
                return GestureCommand("idle", label=label, pose="palm")
            return GestureCommand("drive", vx=vx, vy=vy, omega=omega, label=label, pose="palm")
        point_hands = [hand for hand, pose in zip(hands, poses) if pose == "point"]
        if point_hands:
            vx, vy, omega = point_to_twist(
                point_hands[0], mirrored=self.mirrored, face_to_face=self.face_to_face
            )
            op = operator_nx(_axis(_pt(point_hands[0], INDEX_TIP).x, 0.5, 0.32), mirrored=self.mirrored)
            label = drive_label(vx, vy, omega, operator_nx=op)
            if abs(omega) < 1e-3:
                return GestureCommand("idle", label="食指居中 · 不转", pose="point")
            return GestureCommand("drive", vx=vx, vy=vy, omega=omega, label=label, pose="point")
        return GestureCommand("idle", label="手势：" + "/".join(poses), pose=poses[0])
