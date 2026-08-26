"""Minimal local Agent -> named actions -> serial robot demo pipeline."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Protocol


@dataclass(frozen=True)
class DemoAction:
    name: str
    title: str
    kind: str
    args: dict


DEMO_ACTIONS: dict[str, DemoAction] = {
    "self_intro": DemoAction("self_intro", "自我介绍", "speech", {"text": "你好，我是 R1 课堂助手，很高兴和你一起学习具身智能。"}),
    "wrist_wave": DemoAction("wrist_wave", "右手腕挥动", "arm", {}),
    "right_shoulder_pitch": DemoAction("right_shoulder_pitch", "右肩俯仰", "arm", {}),
    "wave_right": DemoAction("wave_right", "右手挥手", "arm", {}),
    "wave_left": DemoAction("wave_left", "左手挥手", "arm", {}),
    "hands_forward": DemoAction("hands_forward", "双手向前展示", "arm", {}),
    "open_arms": DemoAction("open_arms", "张开双臂", "arm", {}),
    "salute_right": DemoAction("salute_right", "右手敬礼", "arm", {}),
    "salute_left": DemoAction("salute_left", "左手敬礼", "arm", {}),
    "raise_hand_left": DemoAction("raise_hand_left", "左手举手", "arm", {}),
    "raise_hand_right": DemoAction("raise_hand_right", "右手举手", "arm", {}),
    "wrist_wave_left": DemoAction("wrist_wave_left", "左手腕挥动", "arm", {}),
    "present_left": DemoAction("present_left", "左手展示", "arm", {}),
    "present_right": DemoAction("present_right", "右手展示", "arm", {}),
    "ready_pose": DemoAction("ready_pose", "课堂准备姿态", "arm", {}),
    "small_cheer": DemoAction("small_cheer", "双臂鼓励手势", "arm", {}),
    "dual_arm_gesture": DemoAction("dual_arm_gesture", "显著双肩双腕手势", "arm", {}),
    "nod": DemoAction("nod", "点头", "head", {}),
    "look": DemoAction("look", "向左看", "head", {}),
    "shake_head": DemoAction("shake_head", "轻轻摇头", "head", {}),
    "listen_left": DemoAction("listen_left", "面向左侧聆听", "head", {}),
    "listen_right": DemoAction("listen_right", "面向右侧聆听", "head", {}),
    "move_forward_slow": DemoAction("move_forward_slow", "缓慢向前移动", "move", {"vx": 0.05, "vy": 0.0, "duration": 0.5}),
    "move_backward_slow": DemoAction("move_backward_slow", "缓慢向后移动", "move", {"vx": -0.05, "vy": 0.0, "duration": 0.5}),
    "move_left_slow": DemoAction("move_left_slow", "缓慢向左横移", "move", {"vx": 0.0, "vy": 0.05, "duration": 0.6}),
    "move_right_slow": DemoAction("move_right_slow", "缓慢向右横移", "move", {"vx": 0.0, "vy": -0.05, "duration": 0.6}),
    "turn_left_10": DemoAction("turn_left_10", "向左转十度", "turn", {"angle_deg": 10.0}),
    "turn_right_10": DemoAction("turn_right_10", "向右转十度", "turn", {"angle_deg": -10.0}),
    "turn_left_20": DemoAction("turn_left_20", "向左转二十度", "turn", {"angle_deg": 20.0}),
    "turn_right_20": DemoAction("turn_right_20", "向右转二十度", "turn", {"angle_deg": -20.0}),
}

SPEECH = {
    "greeting": "你好，很高兴见到你。",
    "invite_answer": "请举手回答这个问题。",
    "praise": "回答正确，做得很好。",
    "try_again": "没关系，请再试一次。",
    "lesson_start": "同学们好，我们开始上课。",
    "lesson_end": "今天的课程到这里，谢谢大家。",
}

COMPOSITIONS = {
    "欢迎": ["open_arms", "wave_right"],
    "问候学生": ["say:greeting", "wave_right"],
    "邀请回答": ["say:invite_answer", "raise_hand_right"],
    "回答正确": ["nod", "small_cheer", "say:praise"],
    "再试一次": ["shake_head", "open_arms", "say:try_again"],
    "开始上课": ["say:lesson_start", "open_arms", "wave_right", "ready_pose"],
    "结束课程": ["say:lesson_end", "wave_right", "ready_pose"],
    "能力展示": ["look", "wrist_wave", "open_arms"],
}


class DemoBackend(Protocol):
    def speak(self, text: str) -> None: ...
    def arm(self, action: DemoAction) -> None: ...
    def move(self, action: DemoAction) -> None: ...
    def turn(self, action: DemoAction) -> None: ...
    def stop(self) -> None: ...


class SimulatedBackend:
    """Print-only backend used for development and classroom rehearsal."""

    def __init__(self) -> None:
        self.events: list[str] = []

    def _record(self, event: str) -> None:
        self.events.append(event)
        print(event)

    def speak(self, text: str) -> None: self._record(f"SAY {text}")
    def arm(self, action: DemoAction) -> None: self._record(f"ARM {action.name}")
    def move(self, action: DemoAction) -> None: self._record(f"MOVE {action.name} {action.args}")
    def turn(self, action: DemoAction) -> None: self._record(f"TURN {action.name} {action.args}")
    def stop(self) -> None: self._record("STOP")


class DemoPlanner:
    forbidden = re.compile(r"跳舞|跳跃|跳起来|鞠躬|下蹲|蹲下|跑步|奔跑|翻滚")
    aliases = (("向前", "move_forward_slow"), ("向后", "move_backward_slow"),
               ("向左横移", "move_left_slow"), ("向右横移", "move_right_slow"),
               ("向左转二十度", "turn_left_20"), ("向右转二十度", "turn_right_20"),
               ("向左转", "turn_left_10"), ("向右转", "turn_right_10"),
               ("右手腕", "wrist_wave"), ("挥右手", "wave_right"),
               ("挥左手", "wave_left"), ("双手向前", "hands_forward"),
               ("张开双臂", "open_arms"), ("右手敬礼", "salute_right"),
               ("左手敬礼", "salute_left"), ("左手举手", "raise_hand_left"),
               ("右手举手", "raise_hand_right"), ("左手展示", "present_left"),
               ("右手展示", "present_right"), ("鼓励手势", "small_cheer"),
               ("双肩双腕", "dual_arm_gesture"), ("点头", "nod"),
               ("摇头", "shake_head"), ("向左看", "look"),
               ("右肩", "right_shoulder_pitch"),
               ("介绍自己", "self_intro"), ("自我介绍", "self_intro"))

    def plan(self, text: str) -> tuple[str, list[DemoAction]]:
        compact = re.sub(r"\s+", "", text)
        if self.forbidden.search(compact):
            return "这个动作不在当前安全动作库中，我不会执行。", []
        candidates = [(compact.index(phrase), len(phrase), [DEMO_ACTIONS[name]])
                      for phrase, name in self.aliases if phrase in compact]
        for phrase, steps in COMPOSITIONS.items():
            if phrase in compact:
                expanded = []
                for step in steps:
                    if step.startswith("say:"):
                        key = step.split(":", 1)[1]
                        expanded.append(DemoAction(step, SPEECH[key], "speech", {"text": SPEECH[key]}))
                    else:
                        expanded.append(DEMO_ACTIONS[step])
                candidates.append((compact.index(phrase), len(phrase), expanded))
        selected: dict[int, tuple[int, list[DemoAction]]] = {}
        for start, length, group in candidates:
            if start not in selected or length > selected[start][0]:
                selected[start] = (length, group)
        found = [action for _, group in sorted(((start, value[1]) for start, value in selected.items()), key=lambda item: item[0]) for action in group]
        deduplicated: list[DemoAction] = []
        for action in found:
            if action not in deduplicated:
                deduplicated.append(action)
        found = deduplicated
        if not found:
            return "我目前能执行挥手、双手展示、缓慢移动和十度转向。", []
        return "好的，我会按顺序执行：" + "、".join(a.title for a in found), found


class DemoExecutor:
    def __init__(self, backend: DemoBackend) -> None:
        self.backend = backend

    def execute(self, actions: list[DemoAction]) -> None:
        moving = False
        for action in actions:
            if action.kind in {"move", "turn"}:
                if moving:
                    self.backend.stop()
                if action.kind == "move": self.backend.move(action)
                else: self.backend.turn(action)
                self.backend.stop()
                moving = False
            else:
                if moving: self.backend.stop(); moving = False
                if action.kind == "speech": self.backend.speak(action.args["text"])
                else: self.backend.arm(action)
        self.backend.stop()
