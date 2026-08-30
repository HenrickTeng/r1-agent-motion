# R1 上肢动作模仿

MediaPipe Pose → R1 10 个上肢关节。仿真用 MuJoCo；真机用走跑 **811** + `rt/arm_sdk`。

**真机环境、安全、肘零点、左右约定**：请先读 [docs/R1_imitate跟臂.md](../docs/R1_imitate跟臂.md)。

## 安装

```bash
python3.12 -m venv .venv-r1
.venv-r1/bin/pip install -e ".[imitate,dev]"
.venv-r1/bin/pip install 'cyclonedds==0.10.2'
.venv-r1/bin/pip install -e ../unitree_sdk2_python --no-deps
```

## 自检（无摄像头）

```bash
PYTHONPATH=. .venv-r1/bin/python -m imitate --self-test
PYTHONPATH=. .venv-r1/bin/python -m pytest tests/test_pose_to_arm.py tests/test_elbow_map.py tests/test_imitate_collision.py
```

## 摄像头仿真

换摄像头或换人，先标准校准（只看画面，不要 `--hardware`）：

```bash
PYTHONPATH=. .venv-r1/bin/python -m imitate --calibrate --camera 0 --full-model
PYTHONPATH=. .venv-r1/bin/python -m imitate --camera 0 --full-model
```

键：空格采集 · S 保存到 `imitate/mirror_library/` · Q 退出。自拍：**人的右手 → 机器人左臂（蓝）**。问答库 `salute_right` 是机器人自己的右手，不要混。

无显示器可用 `--demo`。`--view --full-model` 循环播放老师姿势（仿真肘零点 ≠ 真机编码器）。

## 真机

物理急停在手。软急停 E/空格，恢复 R，退出 Q。不要走路、不要调试、不要 Damp。

```bash
PYTHONPATH=. .venv-r1/bin/python -m imitate --hardware --goto-ready
PYTHONPATH=. .venv-r1/bin/python -m imitate --hardware --play-calib --pose hands_chest --hold 10
PYTHONPATH=. .venv-r1/bin/python -m imitate --r1-camera --no-capture --full-model --hardware
```

`--play-calib` 姿势：`down tpose forward hands_chest raise_user_right salute_user_right` 或 `all`。

R1 图传走 Go2 `VideoClient.GetImageSample()`。坏 JPEG 跳过，沿用上一帧。

## 导出

`imitate/mirror_library/`：`r1-arm-imitate-mirror/v1`，`abs_deg` / `offsets_deg`，**无** `coeffs`。`hardware_authorized` 默认 false。保存前扫碰撞；未通过只许仿真看。旧 `imitate/library/` 不入库。
