"""电子限位：关节行程 + 机体自碰撞包络。

和电机电子限位同一思路：指令可以往危险方向走，实际输出卡在安全边界上，
而不是等撞上再报警。碰撞包络默认 30 mm（与预警阈值一致）。
"""

from __future__ import annotations

from typing import Mapping

from imitate.collision import CollisionSample, scan_pose
from imitate.joints import ARM_JOINTS, clip_pose_rad, ready_pose_rad
from imitate.pose_to_arm import landmarks_to_arm_rad, synthetic_pose
from imitate.sim import ArmSim


def _lerp(start: Mapping[str, float], end: Mapping[str, float], ratio: float) -> dict[str, float]:
    pose = {}
    for name in ARM_JOINTS:
        a = float(start.get(name, 0.0))
        b = float(end.get(name, a))
        pose[name] = a + ratio * (b - a)
    return clip_pose_rad(pose)


class ElectronicLimits:
    def __init__(
        self,
        sim: ArmSim,
        *,
        warning_m: float = 0.03,
        danger_m: float = 0.01,
        search_steps: int = 10,
    ) -> None:
        self.sim = sim
        self.warning_m = warning_m
        self.danger_m = danger_m
        self.search_steps = search_steps
        seed = clip_pose_rad(ready_pose_rad())
        sample = scan_pose(sim, seed, warning_m=warning_m, danger_m=danger_m)
        if sample.status != "SAFE":
            seed = landmarks_to_arm_rad(synthetic_pose("down"))
            sample = scan_pose(sim, seed, warning_m=warning_m, danger_m=danger_m)
        if sample.status != "SAFE":
            seed = landmarks_to_arm_rad(synthetic_pose("tpose"))
        self.last_safe = clip_pose_rad(seed)

    def apply(self, desired: Mapping[str, float]) -> tuple[dict[str, float], CollisionSample, bool]:
        """返回 (实际输出角, 目标姿态的碰撞采样, 是否被限位挡住)。"""
        target = clip_pose_rad({name: float(desired.get(name, self.last_safe[name])) for name in ARM_JOINTS})
        sample = scan_pose(self.sim, target, warning_m=self.warning_m, danger_m=self.danger_m)
        if sample.status == "SAFE":
            self.last_safe = dict(target)
            return target, sample, False
        lo, hi = 0.0, 1.0
        best = dict(self.last_safe)
        for _ in range(self.search_steps):
            mid = (lo + hi) * 0.5
            candidate = _lerp(self.last_safe, target, mid)
            cand_sample = scan_pose(self.sim, candidate, warning_m=self.warning_m, danger_m=self.danger_m)
            if cand_sample.status == "SAFE":
                lo = mid
                best = candidate
            else:
                hi = mid
        self.last_safe = dict(best)
        return best, sample, True
