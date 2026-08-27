"""验证「动作表存度」改造的换算精度。

对比：老版 MOTIONS 里已经是弧度偏移（_offsets 算好的）→
      新版假设存「度（保留2位小数）」→ 执行时 math.radians 转回弧度。
      看两者误差是否远小于用户要求的 2~3 度。
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from r1_agent.dds_robot import MOTIONS, JOINTS  # noqa: E402

JOINT_NAMES = ["LSP", "LSR", "LSY", "LE", "LWR", "RSP", "RSR", "RSY", "RE", "RWR", "WY", "HP", "HY"]


def rad_to_deg_2dp(rad: float) -> float:
    """模拟存度：弧度 → 度，保留 2 位小数（动作表里的写法）"""
    return round(rad * 180.0 / math.pi, 2)


def deg_to_rad(deg: float) -> float:
    """模拟执行：度 → 弧度"""
    return math.radians(deg)


def main() -> int:
    print("验证：动作表存「度(2位小数)」→ 执行转弧度，与老版弧度的误差")
    print("=" * 62)

    max_err_rad = 0.0
    max_err_desc = ""
    total_joints = 0

    for action_name, frames in MOTIONS.items():
        for (dur, offsets, hold) in frames:
            for i, joint in enumerate(JOINT_NAMES):
                rad_old = offsets[i]  # 老版：已经是弧度
                if rad_old == 0:
                    continue
                deg = rad_to_deg_2dp(rad_old)     # 存度（2位小数）
                rad_new = deg_to_rad(deg)          # 执行转回弧度
                err = abs(rad_new - rad_old)
                total_joints += 1
                if err > max_err_rad:
                    max_err_rad = err
                    max_err_desc = f"{action_name}.{joint}: {rad_old:.4f} rad -> {deg}° -> {rad_new:.6f} rad"

    print(f"共检查 {total_joints} 个非零关节角度")
    print(f"最大误差: {max_err_rad:.6f} rad = {math.degrees(max_err_rad):.4f}°")
    print(f"出现在:   {max_err_desc}")
    print()
    ok = math.degrees(max_err_rad) < 0.1
    print("结论: " + ("✅ 误差 < 0.1°，远小于 2~3 度，完全可接受" if ok else "⚠ 需要检查存度精度"))

    # 统计每个动作的最大关节角度（参考，用于确认不超限）
    print()
    print("各动作最大关节角度（绝对值，度）：")
    print("-" * 62)
    for action_name, frames in MOTIONS.items():
        max_deg = 0.0
        for (dur, offsets, hold) in frames:
            for v in offsets:
                max_deg = max(max_deg, abs(math.degrees(v)))
        print(f"  {action_name:<20} max {max_deg:6.2f}°")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
