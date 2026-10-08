"""近距迎宾状态机：固定距离内原地手部互动；半米内提醒；贴脸停手。"""

from __future__ import annotations

from dataclasses import dataclass

from r1_studio.depth import CAUTION_M, DANGER_M, GREET_MAX_M, classify_zone
from r1_studio.gestures import classify_hand

WARN_TEXT = "请稍微离我远一点，半米内挥手我担心不小心伤到你。"
DANGER_TEXT = "太近了，请先退到半米以外。贴脸时我不会动手。"
GREET_TEXT = "你好，很高兴见到你。"
GREET_CONTEXT = (
    "当前是近距迎宾模式：人站在镜头前，机器人只原地说话和做上肢动作，"
    "禁止规划行走、后退、横移和转向。"
    f"距离小于 {DANGER_M:.1f} 米视为贴脸，不要规划任何上肢动作；"
    f"{CAUTION_M:.1f} 米内先请对方退后；"
    f"{GREET_MAX_M:.1f} 米内可以打招呼、挥手、鼓掌、点头。"
    "视觉事件会写入对话，后续语音短句要接上刚才是否已经打过招呼。"
)


@dataclass(frozen=True)
class GreetEvent:
    kind: str
    zone: str
    meters: float | None
    reply: str = ""
    actions: tuple[str, ...] = ()
    pose: str = "none"
    note: str = ""


def drop_locomotion(actions: list) -> list:
    return [action for action in actions if getattr(action, "kind", "") not in ("move", "turn")]


def map_hand_pose(pose: str) -> tuple[str, ...]:
    if pose in ("palm", "right_out"):
        return ("wave_right",)
    if pose == "left_out":
        return ("wave_left",)
    if pose in ("peace", "both_up"):
        return ("cheer_both",)
    if pose in ("tpose", "palms"):
        return ("open_arms",)
    if pose in ("fist", "both_down"):
        return ("ready_pose",)
    return ()


def pick_pose(*, hands: list, body_pose: str) -> str:
    if body_pose and body_pose not in ("none", "both_down"):
        return body_pose
    labels = [classify_hand(hand) for hand in hands or []]
    if labels.count("palm") >= 2:
        return "palms"
    for name in ("peace", "palm", "fist"):
        if name in labels:
            return name
    return body_pose if body_pose else "none"


class GreetPilot:
    def __init__(self) -> None:
        self.zone = "unknown"
        self.meters: float | None = None
        self.visited_greet = False
        self._last_warn = 0.0
        self._last_gesture = 0.0
        self._last_pose = "none"
        self._smooth_m: float | None = None

    def reset(self) -> None:
        self.zone = "unknown"
        self.meters = None
        self.visited_greet = False
        self._last_warn = 0.0
        self._last_gesture = 0.0
        self._last_pose = "none"
        self._smooth_m = None

    def allows_arm(self) -> bool:
        return self.zone == "greet"

    def safety_reply(self) -> str:
        if self.zone == "danger":
            return DANGER_TEXT
        if self.zone == "caution":
            return WARN_TEXT
        return ""

    def step(self, meters: float | None, pose: str, now: float) -> GreetEvent:
        if meters is None:
            self._smooth_m = None
            smoothed = None
        elif self._smooth_m is None:
            self._smooth_m = meters
            smoothed = meters
        elif meters + 0.12 < self._smooth_m:
            # 靠近时立刻跟新值，避免半米贴脸还被均值留在迎宾区。
            self._smooth_m = meters
            smoothed = meters
        else:
            self._smooth_m = 0.55 * self._smooth_m + 0.45 * meters
            smoothed = self._smooth_m
        zone = classify_zone(smoothed)
        self.zone = zone
        self.meters = smoothed
        meters = smoothed
        if zone in ("far", "unknown"):
            self.visited_greet = False
            self._last_pose = "none"
            return GreetEvent("idle", zone, meters, pose=pose or "none", note="等待有人走进 0.5–1.8 米")
        if zone == "danger":
            self.visited_greet = False
            speak = now - self._last_warn >= 4.0
            if speak:
                self._last_warn = now
            return GreetEvent(
                "freeze",
                zone,
                meters,
                DANGER_TEXT if speak else "",
                pose=pose,
                note="贴脸，停手",
            )
        if zone == "caution":
            speak = now - self._last_warn >= 6.0
            if speak:
                self._last_warn = now
            return GreetEvent(
                "warn",
                zone,
                meters,
                WARN_TEXT if speak else "",
                pose=pose,
                note="半米内，不挥手",
            )
        mapped = map_hand_pose(pose)
        if mapped and pose != self._last_pose and now - self._last_gesture >= 2.8:
            self._last_pose = pose
            self._last_gesture = now
            self.visited_greet = True
            title = "挥手打招呼" if mapped[0].startswith("wave") else mapped[0]
            return GreetEvent(
                "gesture",
                zone,
                meters,
                GREET_TEXT if mapped[0].startswith("wave") else "",
                mapped,
                pose,
                f"看到 {pose}，原地{title}",
            )
        if not self.visited_greet:
            if now - self._last_gesture >= 8.0:
                self.visited_greet = True
                self._last_gesture = now
                self._last_pose = pose or "none"
                return GreetEvent(
                    "greet",
                    zone,
                    meters,
                    GREET_TEXT,
                    ("say:greeting", "wave_right"),
                    pose or "none",
                    "有人进入迎宾距离，挥手问好",
                )
        return GreetEvent("idle", zone, meters, pose=pose or "none", note="迎宾范围内待机，可听语音")
