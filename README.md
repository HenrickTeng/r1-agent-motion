# R1 Agent Skill Demo

自然语言或 R1 麦克风 → 命名动作序列 → 笔记本网线直连 DDS 执行。

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pip install 'cyclonedds==0.10.2' numpy
.venv/bin/pip install -e ../../unitree_sdk2_python --no-deps
PYTHONPATH=. .venv/bin/python -m r1_agent --text "请介绍自己，然后挥右手"
PYTHONPATH=. .venv/bin/pytest
```

Ubuntu 上用以太网卡（本目录默认 `enp7s0`，以 `ip a` 的实际结果为准），地址 `192.168.123.100`，直连 R1 `192.168.123.161`。C++ SDK 只有 Linux 预编译库，真机 demo 走 Python DDS。

```bash
PYTHONPATH=. .venv/bin/python -m r1_agent --listen --hardware --interface enp7s0
```

`--listen` 默认走 DeepSeek，从 ASR 错字恢复意图。打字 `--text` 仍用本地规则；加 `--deepseek` 则文本也走模型。密钥：`DEEPSEEK_API_KEY` 或 `deepseek_key.txt`。动作白名单见 `actions.json`，Skill 见 `skill/control-unitree-r1/SKILL.md`。

如需为本次运行预先提供身份、场景或回答风格，可使用 `--context`：

```bash
PYTHONPATH=. .venv-r1/bin/python -m r1_agent \
  --listen --continuous --hardware --interface enp7s0 \
  --context "你是学校里的 Unitree R1 课堂助手，面对来上课的初中生。请用简短、友好、适合课堂的中文回答；涉及动作时先说明将要做什么，再按顺序执行。"
```

当前固件上行走写 API 可能返回 `127`；上肢固定动作、ASR、TTS 已在 Linux 真机用过。现场需要急停在手。

## Ubuntu 操作指南

完整部署、代理配置、API key、连续上下文、ASR 异常和真机安全检查请参阅 [Ubuntu操作指南.md](Ubuntu操作指南.md)。

## 本版本改进

- 适配 Ubuntu：默认网卡从 macOS 的 `en5` 改为 `enp7s0`，并使用 Python 3.12/CycloneDDS 环境。
- 增加 `--context`：启动时可注入约定的机器人身份、课堂场景和回答风格。
- 增加连续对话：`--continuous` 在同一进程内保留 DeepSeek 上下文，避免每轮重新认识机器人。
- 动作执行改为串行：动作之间停止，前一个动作失败时不继续发送后续动作。
- 增加转向安全上限：单轮左转/右转总角度超过 `360°` 时拒绝执行并播报原因。
- 增加步数规划提示：前进/后退支持 `1～10` 步，由移动原子动作组合。
- 增加 ASR 语言保护：识别结果明确标记为日语时丢弃本轮，不调用模型、不执行动作并重新监听。
- 保留 `dds_robot_modified.py` 作为 ready-pose/绝对角度开发稿；默认入口仍是 `dds_robot.py`，避免未经验证的角度改造直接进入真机。
