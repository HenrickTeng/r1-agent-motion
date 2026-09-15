"""官方 r1.xml 能加载，上肢碰撞不把髋关节算进去。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from imitate.collision import scan_pose
from imitate.pose_to_arm import landmarks_to_arm_rad, synthetic_pose
from imitate.sim import DEFAULT_OFFICIAL, ArmSim


def test_official_r1_loads_and_tpose_is_arm_safe() -> None:
    if not DEFAULT_OFFICIAL.is_file():
        return
    sim = ArmSim(preview_only=False)
    assert sim.model_path == DEFAULT_OFFICIAL
    sample = scan_pose(sim, landmarks_to_arm_rad(synthetic_pose("tpose")))
    assert sample.status == "SAFE", sample
    assert sample.closest_pair is None or "hip" not in "".join(sample.closest_pair)
