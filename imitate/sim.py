"""R1 上肢 MuJoCo 预览。默认用仓库内简化臂模型，可选加载官方 r1.xml。"""

from __future__ import annotations

import math
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Mapping

import mujoco
import numpy as np

from imitate.joints import ARM_JOINTS, clip_pose_rad
from imitate.retarget import extra_ready_rad, elbows_human_to_official

HERE = Path(__file__).resolve().parent
PREVIEW_XML = HERE / "assets" / "r1_arm_preview.xml"
DEFAULT_OFFICIAL = Path("/home/henrick/unitree_rl_mjlab/src/assets/robots/unitree_r1/xmls/r1.xml")


def _load_official(path: Path) -> mujoco.MjModel:
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    bodies = {element.attrib.get("name") for element in root.iter("body")}
    contact = root.find("contact")
    if contact is not None:
        for exclusion in list(contact.findall("exclude")):
            body1, body2 = exclusion.attrib.get("body1"), exclusion.attrib.get("body2")
            if body1 not in bodies or body2 not in bodies:
                contact.remove(exclusion)
    asset_dir = path.parent / "assets"
    assets = {item.name: item.read_bytes() for item in asset_dir.iterdir() if item.is_file()} if asset_dir.is_dir() else {}
    return mujoco.MjModel.from_xml_string(ET.tostring(root, encoding="unicode"), assets)


def resolve_model_path(path: str | Path | None = None) -> Path:
    if path:
        return Path(path)
    env = os.environ.get("R1_MJCF")
    if env:
        return Path(env)
    if DEFAULT_OFFICIAL.is_file():
        return DEFAULT_OFFICIAL
    return PREVIEW_XML


def joint_qposadr(model: mujoco.MjModel) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for index in range(model.njnt):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, index)
        if not name:
            continue
        key = name.removesuffix("_joint") if name.endswith("_joint") else name
        mapping[key] = int(model.jnt_qposadr[index])
    return mapping


class ArmSim:
    def __init__(self, model_path: str | Path | None = None, *, preview_only: bool = False) -> None:
        path = PREVIEW_XML if preview_only else resolve_model_path(model_path)
        self.model_path = path
        if path == PREVIEW_XML or path.name == "r1_arm_preview.xml":
            self.model = mujoco.MjModel.from_xml_path(str(path))
            self.preview = True
        else:
            self.model = _load_official(path)
            self.preview = False
        self.data = mujoco.MjData(self.model)
        self.qposadr = joint_qposadr(self.model)
        missing = [name for name in ARM_JOINTS if name not in self.qposadr]
        if missing:
            raise ValueError(f"model missing arm joints: {missing}")
        self._pin_base()
        mujoco.mj_forward(self.model, self.data)

    def _pin_base(self) -> None:
        if "floating_base" in self.qposadr or int(self.model.nq) >= 7 and int(self.model.jnt_type[0]) == 0:
            self.data.qpos[2] = 0.74
            self.data.qpos[3:7] = np.array([1.0, 0.0, 0.0, 0.0])

    def set_pose(self, pose_rad: Mapping[str, float]) -> None:
        clipped = clip_pose_rad(pose_rad)
        if not self.preview:
            clipped = elbows_human_to_official(clipped)
        for name, value in clipped.items():
            if name in self.qposadr:
                self.data.qpos[self.qposadr[name]] = value
        for name, value in extra_ready_rad().items():
            if name in self.qposadr:
                self.data.qpos[self.qposadr[name]] = value
        self._pin_base()
        mujoco.mj_forward(self.model, self.data)

    def set_abs_deg(self, pose_deg: Mapping[str, float]) -> None:
        self.set_pose({name: math.radians(float(value)) for name, value in pose_deg.items()})
