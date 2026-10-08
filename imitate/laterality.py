"""模仿与问答的左右约定必须分开，不能共用动作名。

问答 / `actions.json` / `dds_robot.MOTIONS`：名字里的左/右是 **机器人自己的左/右**。
`salute_right` = 机器人右臂敬礼。

模仿 / `imitate/mirror_library`：自拍镜头左右对调，**人的右手 → 机器人左臂（蓝）**。
`salute_user_right` 与问答的 `salute_right` 不是同一个动作。
"""

from pathlib import Path

HERE = Path(__file__).resolve().parent
MIRROR_LIBRARY = HERE / "mirror_library"

# 旧真机参数名 → 模仿库名（人的右 = 机器人左）
POSE_ALIASES: dict[str, str] = {
    "raise_right": "raise_user_right",
    "salute_right": "salute_user_right",
}

LATERALITY = "selfie_mirror_user_right_is_robot_left"
