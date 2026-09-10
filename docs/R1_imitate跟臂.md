# R1 上肢模仿与真机跟臂

MediaPipe Pose → 10 个上肢关节。真机只走 **走跑 FSM 811** + `rt/arm_sdk`，复用已测通的 `r1_agent/dds_robot.py`，不发全身 `rt/lowcmd`，不 `SetFsmId`，不进调试、不 Damp。

更短的命令表见 [imitate/README.md](../imitate/README.md)。问答语音 Demo 仍看 [Ubuntu操作指南.md](Ubuntu操作指南.md)。

## 1. 环境

Python **3.12** + `.venv-r1`。不要用 3.13。CycloneDDS 必须是 **`cyclonedds==0.10.2`**（不要 11）。`unitree_sdk2py` 从课程目录旁的 `unitree_sdk2_python` 可编辑安装。

`r1_agent/dds_setup.py` 会在 `ChannelFactoryInitialize` 之前：

- 加载 `libddsc.so.0`（`CYCLONEDDS_HOME`，或仓库上一级的 `unitree_sdk2_python/.deps/cyclonedds`）
- 去掉官方 XML 里 `<Tracing><Verbosity>config</Verbosity>`，否则本机 0.10.2 会 glibc fortify abort

网卡 `--interface auto` 只选带 **`192.168.123.x`** 的口（本机常见 `enp7s0` = 192.168.123.99，机器人 192.168.123.161）。没有这张网卡会直接报错，不会猜 `enp7s0`。

```bash
python3.12 -m venv .venv-r1
.venv-r1/bin/pip install -e '.[dev,imitate]'
.venv-r1/bin/pip install 'cyclonedds==0.10.2'
.venv-r1/bin/pip install -e ../unitree_sdk2_python --no-deps
export CYCLONEDDS_HOME=/path/to/unitree_sdk2_python/.deps/cyclonedds
PYTHONPATH=. .venv-r1/bin/pytest
```

`unitree_sdk2_python` 相对本仓库一般在 `../unitree_sdk2_python`。

## 2. 真机安全（必须）

- 遥控器 **物理急停** 一直在手。
- 保持走跑 **811**。不要进调试，不要 Damp。官方说明：软急停进阻尼后可能摔倒。
- 软件软急停（跟臂窗口 **E** 或空格）= `StopMove` + 锁住当前臂角（weight 仍为 1），**不** Damp。**R** 恢复，**Q** 退出并缓慢交还 `arm_sdk`。
- 跟臂测试 **不要同时走路**。
- 固件 `arm_sdk` **没有几何自碰**，只有关节行程。软件 `ElectronicLimits`（MuJoCo 30 mm 包络 + 关节 clip）在人/仿真角上、发给真机之前做。包络和编码器几何不完全一致，不能替代物理急停。

## 3. 左右约定（两套库，不要混）

| 场景 | 目录 | 左/右含义 |
| --- | --- | --- |
| 问答 / 语音 Demo | `actions.json`、`dds_robot.MOTIONS` | **机器人自己的**左右。`salute_right` = 机器人右臂 |
| 模仿 / 跟臂 | `imitate/mirror_library/` | 自拍：镜头对着人，**人的右手 → 机器人左臂（蓝）**。名字用 `raise_user_right` / `salute_user_right` |

模仿 JSON schema：`r1-arm-imitate-mirror/v1`，**没有**问答用的 `coeffs`。`imitate/library/` 是旧采集归档，gitignore，不要当动作目录。

## 4. 肘关节三套零点

`rt/lowstate` 和指令是对得上的（下 95°，J4 就约 94.9°）。看起来「肘反了」是 **零点约定不同**，不是宇树遥测写反。

1. **人 / 课 / IK / 仿真**：0° ≈ 伸直，45° ≈ 走跑待机弯，越大越屈。胸前按人肘 **95°** 写。
2. **走跑编码器**：机械零。实测 **~95° 看起来伸直**，**~45° 待机弯**，比 45° 更小才更屈。
3. **官方 `r1.xml` 网格**：肘 0 看起来大约弯 80°，视觉最直大约 76°。`elbows_human_to_official()` **只进仿真** `ArmSim.set_pose`，不上真机。所以仿真胸前弯、真机胸前直，是两套模型。

发给 `rt/arm_sdk` 前，`r1_agent/elbow_map.py` 把人肘换成编码器：人 0 → 硬 95，人 45 → 硬 ~45，人 95 → 硬 ~−10°。只在 `track_arm`（有上肢目标时）和校准播放 `_teacher_to_13_rad` 里换。**`goto_ready` 仍用编码器待机角**，不要再换一次。限位仍在人/仿真角上做。

## 5. 常用命令

一律在仓库根目录，用 `.venv-r1`：

```bash
# 无摄像头自检
PYTHONPATH=. .venv-r1/bin/python -m imitate --self-test

# 笔记本摄像头仿真（先校准再跟）
PYTHONPATH=. .venv-r1/bin/python -m imitate --calibrate --camera 0 --full-model
PYTHONPATH=. .venv-r1/bin/python -m imitate --camera 0 --full-model

# 真机：只回走跑待机
PYTHONPATH=. .venv-r1/bin/python -m imitate --hardware --goto-ready

# 真机：逐个播放校准姿势（人肘约定）
PYTHONPATH=. .venv-r1/bin/python -m imitate --hardware --play-calib --pose hands_chest --hold 10
# 姿势：down tpose forward hands_chest raise_user_right salute_user_right（可用 all）

# 真机跟臂：R1 头部图传（Go2 VideoClient JPEG）
PYTHONPATH=. .venv-r1/bin/python -m imitate --r1-camera --no-capture --full-model --hardware
```

`--calibrate` 不要加 `--hardware`。图传偶发坏 JPEG 会跳过该帧、沿用上一帧；不要把损坏缓冲交给 OpenCV/MediaPipe（曾导致退出码 139）。

跟臂限速（约再 ×1.25 档，见 `r1_agent/arm_safety.py`）：肩俯仰/偏航约 46°/s，肩滚约 39°/s，肘约 51°/s，腕约 57°/s，腰约 22°/s。

## 6. 不要做的事

- 跟臂时行走、进调试、`Damp`、`SetFsmId`、发 `rt/lowcmd`
- 把模仿 JSON 写进 `actions.json` / 问答 Skill
- Python 3.13 或 `cyclonedds` 11 跑 DDS
- 把 `deepseek_key.txt`、`.venv-r1`、个人 `calibration.json` 推到 GitHub
