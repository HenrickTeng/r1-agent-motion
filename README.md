# R1 Agent Motion

面向初中课堂的 Unitree R1 安全动作与语音 Agent 平台。教师电脑负责对话、审批、动作编译和 MuJoCo 复验；PC1 Gateway 负责确定性执行；学生、模型和公网平台均不能直接访问 DDS。

新 Agent 或新开发者接手前，请先完整阅读 [`docs/agent-handoff-2026-08-26.md`](docs/agent-handoff-2026-08-26.md)；其中严格区分已实现代码、自动测试、真机证据和尚未打通的链路。

项目只覆盖经过安全包络约束的上肢、头部动作与短时低速移动，不支持舞蹈、跳跃、跑步、动态全身动作，也不允许模型产生 `LowCmd`、运行时增益或任意代码。

## 开发环境

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
export UNITREE_SDK2_DIR=/home/henrick/unitree_sdk2-main
export UNITREE_R1_MODEL_DIR=/home/henrick/unitree_rl_mjlab/src/assets/robots/unitree_r1/xmls
r1ctl status
```

启动教师端与仿真服务：

```bash
.venv/bin/python -m apps.teacher_bridge
.venv/bin/python -m apps.simulation_service
```

自动验收：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest
cmake -S gateway -B build/gateway -DCMAKE_BUILD_TYPE=Release
cmake --build build/gateway -j2
ctest --test-dir build/gateway --output-on-failure
```

服务入口、协议、模型审计、硬件门禁和平台集成说明位于 `docs/`。真实机器人测试必须使用 `hardware-tests/` 的单项程序，并严格遵循 `docs/hardware-test-workflow.md`。

离线简化碰撞预警和角度制多关节动作文件见 `docs/collision-warning.md`；碰撞扫描只产生预警，不授权真机执行。

## 安全边界

- Agent 执行模式只能组合 `classroom_enabled` 动作。
- 设计模式只能生成设计规格和仿真任务，不能触发真机。
- Gateway 不接受 Shell、原始 DDS、`LowCmd`、任意关节数组或未安装轨迹。
- 上肢动作和移动在 v1 中互斥。
- 无挂架时，所有新动作必须先通过缩放的小幅单关节和模板验收。

## 当前发布门禁

首批动作模板、语音链路、动作包、编译器、仿真服务、Teacher Bridge、Gateway 核心和公网平台 SDK 已实现。当前外部 MJCF 的头部关节/actuator/接触定义审计未通过，PC1 的 Unitree 生产适配器也尚未部署，因此系统保持 fail-closed：不会把生成动作或低速移动标为可真机执行。
