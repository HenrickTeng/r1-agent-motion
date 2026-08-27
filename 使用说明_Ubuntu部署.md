# R1 Agent Motion Demo — Ubuntu 部署说明

吴博（Mac）已验证的 R1 课堂演示极简版，本次在其基础上整理并新增了 3 个文件。纯 Python（unitree_sdk2_python）+ 网线直连 DDS，**不需要 C++ 编译**。

## 本次增量（2026-08-27）

| 文件 | 说明 |
|---|---|
| `read_ready_pose.py` | 读取 R1 的 ready_pose 绝对角度（13 关节），供后续「动作清单存绝对角度」改造当零位 |
| `tests/test_degree_conversion.py` | 度↔弧度换算精度测试（已跑通，最大误差 0.005°，远小于 2~3 度） |
| `动作角度清单.md` | 30 个动作的关节角度（度/弧度）参考，供动作编辑/模仿项目用 |

> 说明：本次**没有改 `dds_robot.py` 本体**。动作仍用吴博原来的「系数×振幅 + 偏移量」写法，真机行为与吴博版完全一致。后续「存度 + 绝对角度」改造等拿到 ready_pose 数据再做。

## 快速开始（Ubuntu）

**1. 查网卡名**（连机器人那根网线）：

```bash
ip a
```

记录网卡名（之前 Codex 那台是 `enp7s0`，不同机器可能不同）。

**2. 配 IP**：连机器人的网卡 IP 设 `192.168.123.100`（机器人是 `192.168.123.161`）。

**3. 装依赖**（项目目录内）：

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pip install 'cyclonedds==0.10.2' numpy
git clone https://github.com/unitreerobotics/unitree_sdk2_python   # 项目旁边
.venv/bin/pip install -e ../../unitree_sdk2_python --no-deps
```

Python 需 ≥ 3.11。

**4. 分步测试**：

```bash
# ① 只读连接 + 读 ready_pose（不动机器人，顺便拿零位数据）
PYTHONPATH=. .venv/bin/python read_ready_pose.py --interface enp7s0

# ② 文字指令（不连真机，验证规划器，不需要 DeepSeek key）
PYTHONPATH=. .venv/bin/python -m r1_agent --text "请介绍自己，然后挥右手"

# ③ 真机 demo（连机器人，急停在手）
PYTHONPATH=. .venv/bin/python -m r1_agent --text "挥手" --hardware --interface enp7s0
```

## 待办

- [ ] **读 ready_pose 绝对角度**：开机 → 机器人站好（StandUp/遥控器）→ 摆好准备姿态 → 跑上面①，把输出 JSON 贴回，用于后续「绝对角度」改造。
- [ ] 后续改造：动作清单「系数 → 度」，再「偏移量 → 绝对角度」（等 ready_pose 数据）。

## 注意事项

- **现场急停必须在手**；`--hardware` 会真动机器人，先清空周边、确认站立姿态。
- 行走 `SetVelocity` 可能返回 `127`（未根治，吴博版同样接受）；转向用 `omega=1.0 + duration` 开环控角度（turn_left_10=0.2s≈11.5° … turn_left_90=1.57s≈90°）。
- 已确认可接受的小问题：转向不精准（未用 IMU 闭环）、语音转向角偏小、偶尔身体轻微倾斜。
- `--text` 走本地规则不需要 DeepSeek key；`--listen`（语音）才需要 `DEEPSEEK_API_KEY` 或 `deepseek_key.txt`。

## 技术要点（快速回顾）

- R1 控制三条通道：①上肢自定义动作 → DDS `rt/arm_sdk` 直发 LowCmd；②行走/转向 → `LocoClient` RPC（sport 服务）；③语音 → `AudioClient` RPC + 订阅 `rt/audio_msg`。
- 关节顺序 `JOINTS=(15,16,17,18,19, 22,23,24,25,26, 13,29,30)`：左臂 J1~J5 = 肩俯仰/肩横滚/肩偏航/肘/腕横滚，右臂同理，再腰偏航、头俯仰、头偏航。
- 角度写法：`_offsets` 里肩俯仰（LSP/RSP）×3.0、其余 ×1.8，乘完是弧度偏移（相对当前姿态）。
