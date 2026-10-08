"""打开 MuJoCo，循环播放真机同一套教师姿势（含电子限位）。"""

from __future__ import annotations

import math
import time

from imitate.calibrate import CALIB_POSES
from imitate.collision import scan_pose
from imitate.limits import ElectronicLimits
from imitate.retarget import elbows_human_to_official, teacher_pose_rad
from imitate.sim import ArmSim


def dump_teacher_table(sim: ArmSim) -> None:
    print("真机同一套教师角 → 仿真（官方网格会换肘零位）")
    print(f"模型 {sim.model_path}  preview={sim.preview}")
    for name in CALIB_POSES:
        pose = teacher_pose_rad(name)
        official = elbows_human_to_official(pose) if not sim.preview else pose
        sim.set_pose(pose)
        sample = scan_pose(sim, pose)
        le_h = math.degrees(pose["left_elbow"])
        re_h = math.degrees(pose["right_elbow"])
        le_o = math.degrees(official["left_elbow"])
        re_o = math.degrees(official["right_elbow"])
        print(
            f"  {name:<20} 人肘 L{le_h:6.1f} R{re_h:6.1f}  "
            f"网格肘 L{le_o:6.1f} R{re_o:6.1f}  {sample.status}  {sample.minimum_distance_m*1000:.0f}mm"
        )


def run_view(*, hold_s: float = 2.5, full_model: bool = True) -> None:
    import mujoco.viewer

    sim = ArmSim(preview_only=not full_model)
    dump_teacher_table(sim)
    limiter = ElectronicLimits(sim)
    print("MuJoCo 每 {:.1f}s 切一个姿势。蓝臂=机器人左=人的右手。关窗口退出。".format(hold_s))
    index = 0
    last = 0.0
    with mujoco.viewer.launch_passive(sim.model, sim.data) as viewer:
        viewer.cam.lookat[:] = (0.05, 0.0, 1.05)
        viewer.cam.distance = 2.2
        viewer.cam.azimuth = 140
        viewer.cam.elevation = -15
        while viewer.is_running():
            now = time.time()
            if now - last >= hold_s:
                name = CALIB_POSES[index % len(CALIB_POSES)]
                desired = teacher_pose_rad(name)
                pose, sample, blocked = limiter.apply(desired)
                sim.set_pose(pose)
                flag = "LIMIT" if blocked else "OK"
                le = math.degrees(desired["left_elbow"])
                print(f"  {name:<20} {flag}  人肘L={le:.0f}  raw={sample.status}")
                index += 1
                last = now
            viewer.sync()
            time.sleep(0.02)
