"""机载画面里锁定「操控者」，对齐大疆 Neo：先举手认人，再只听这个人的手势。"""

from __future__ import annotations

from r1_studio.gestures import classify_hand

LOCK_POSES = frozenset({"palm", "peace"})


def _xy(point) -> tuple[float, float]:
    if isinstance(point, dict):
        return float(point["x"]), float(point["y"])
    return float(point.x), float(point.y)


def wrist_xy(hand: list) -> tuple[float, float]:
    return _xy(hand[0])


def box_area(box: tuple[float, float, float, float]) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def box_center(box: tuple[float, float, float, float]) -> tuple[float, float]:
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


def pad_box(box: tuple[float, float, float, float], pad: float) -> tuple[float, float, float, float]:
    return (
        max(0.0, box[0] - pad),
        max(0.0, box[1] - pad),
        min(1.0, box[2] + pad),
        min(1.0, box[3] + pad),
    )


def point_in_box(x: float, y: float, box: tuple[float, float, float, float]) -> bool:
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = box_area(a) + box_area(b) - inter
    return inter / union if union > 1e-9 else 0.0


def hand_in_box(hand: list, box: tuple[float, float, float, float], pad: float) -> bool:
    x, y = wrist_xy(hand)
    return point_in_box(x, y, pad_box(box, pad))


def box_from_hands(hands: list[list], margin: float = 0.22) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for hand in hands:
        for index in (0, 8, 9, 12):
            if index < len(hand):
                x, y = _xy(hand[index])
                xs.append(x)
                ys.append(y)
    if not xs:
        return (0.2, 0.1, 0.8, 0.95)
    return (
        max(0.0, min(xs) - margin),
        max(0.0, min(ys) - margin * 1.5),
        min(1.0, max(xs) + margin),
        min(1.0, max(ys) + margin),
    )


def match_person(
    locked: tuple[float, float, float, float],
    persons: list[tuple[float, float, float, float]],
    *,
    min_iou: float = 0.12,
    max_center: float = 0.22,
) -> tuple[float, float, float, float] | None:
    best = None
    best_iou = min_iou
    for box in persons:
        score = iou(locked, box)
        if score > best_iou:
            best_iou = score
            best = box
    if best is not None:
        return best
    lx, ly = box_center(locked)
    nearest = None
    dist = max_center
    for box in persons:
        px, py = box_center(box)
        d = ((px - lx) ** 2 + (py - ly) ** 2) ** 0.5
        if d < dist:
            dist = d
            nearest = box
    return nearest


class OperatorLock:
    """未锁定时不把旁人的手交给手势；张开手掌或比耶认人后只跟这一框。"""

    def __init__(self, *, enabled: bool = False, lost_frames: int = 30, pad: float = 0.10) -> None:
        self.enabled = enabled
        self.lost_frames = lost_frames
        self.pad = pad
        self.box: tuple[float, float, float, float] | None = None
        self._lost = 0
        self.status = "off"

    def reset(self) -> None:
        self.box = None
        self._lost = 0
        self.status = "off" if not self.enabled else "hunting"

    def step(self, persons: list[tuple[float, float, float, float]], hands: list[list]) -> tuple[list[list], dict]:
        if not self.enabled:
            self.status = "off"
            return hands, {"status": "off", "box": None, "label": ""}
        boxes = [tuple(item[:4]) for item in persons]
        if self.box is None:
            owned, box = self._try_acquire(boxes, hands)
            if box is None:
                self.status = "hunting"
                return [], {
                    "status": "hunting",
                    "box": None,
                    "label": "请面向镜头张开手掌，锁定操控者",
                }
            self.box = box
            self._lost = 0
            self.status = "locked"
            return owned, {"status": "locked", "box": box, "label": "已锁定操控者"}

        matched = match_person(self.box, boxes) if boxes else None
        owned = [hand for hand in hands if hand_in_box(hand, self.box, self.pad)]
        if matched is not None:
            self.box = matched
            self._lost = 0
            owned = [hand for hand in hands if hand_in_box(hand, self.box, self.pad)]
        elif owned:
            self._lost = 0
            self.box = box_from_hands(owned)
        else:
            self._lost += 1
            if self._lost >= self.lost_frames:
                self.box = None
                self.status = "hunting"
                return [], {
                    "status": "hunting",
                    "box": None,
                    "label": "操控者丢失，请再举手锁定",
                }
        self.status = "locked"
        return owned, {"status": "locked", "box": self.box, "label": "已锁定操控者"}

    def _try_acquire(
        self,
        persons: list[tuple[float, float, float, float]],
        hands: list[list],
    ) -> tuple[list[list], tuple[float, float, float, float] | None]:
        lock_hands = [hand for hand in hands if classify_hand(hand) in LOCK_POSES]
        if not lock_hands:
            return [], None
        if persons:
            ranked: list[tuple[float, tuple[float, float, float, float]]] = []
            for box in persons:
                if any(hand_in_box(hand, box, self.pad) for hand in lock_hands):
                    ranked.append((box_area(box), box))
            if ranked:
                ranked.sort(key=lambda item: -item[0])
                box = ranked[0][1]
                owned = [hand for hand in hands if hand_in_box(hand, box, self.pad)]
                return owned, box
        # 人体框暂时没有时，用举手的人（偏画面中下部、通常站在机器人正前方）
        def _front_score(hand: list) -> float:
            x, y = wrist_xy(hand)
            return -((x - 0.5) ** 2 + (y - 0.62) ** 2)

        lock_hands.sort(key=_front_score, reverse=True)
        box = box_from_hands([lock_hands[0]])
        owned = [hand for hand in hands if hand_in_box(hand, box, self.pad)]
        return owned, box
