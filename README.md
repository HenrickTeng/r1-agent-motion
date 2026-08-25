# R1 Agent Motion

面向初中课堂的 Unitree R1 安全动作与语音 Agent 平台。教师电脑负责对话、审批、动作编译和 MuJoCo 复验；PC1 Gateway 负责确定性执行；学生、模型和公网平台均不能直接访问 DDS。

项目只覆盖经过安全包络约束的上肢、头部动作与短时低速移动，不支持舞蹈、跳跃、跑步、动态全身动作，也不允许模型产生 `LowCmd`、运行时增益或任意代码。

## 开发环境

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
export UNITREE_SDK2_DIR=/home/henrick/unitree_sdk2-main
export UNITREE_R1_MODEL_DIR=/home/henrick/unitree_rl_mjlab/src/assets/robots/unitree_r1/xmls
r1ctl status
```

服务入口、协议、硬件门禁和平台集成说明位于 `docs/`。真实机器人测试必须使用 `hardware-tests/` 的单项程序，并严格遵循 `docs/hardware-test-workflow.md`。

## 安全边界

- Agent 执行模式只能组合 `classroom_enabled` 动作。
- 设计模式只能生成设计规格和仿真任务，不能触发真机。
- Gateway 不接受 Shell、原始 DDS、`LowCmd`、任意关节数组或未安装轨迹。
- 上肢动作和移动在 v1 中互斥。
- 无挂架时，所有新动作必须先通过缩放的小幅单关节和模板验收。
