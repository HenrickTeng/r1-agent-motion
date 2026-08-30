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

Ubuntu 上用以太网卡（默认 `auto`：选用带 `192.168.123.x` 的网卡；Mac 常见 `en5`，Ubuntu 常见 `enp7s0`），地址 `192.168.123.100`，直连 R1 `192.168.123.161`。C++ SDK 只有 Linux 预编译库，真机 demo 走 Python DDS。Mac 需设置 `CYCLONEDDS_HOME` 和 `DYLD_LIBRARY_PATH`；Ubuntu 一般 `pip install cyclonedds==0.10.2` 即可。

```bash
PYTHONPATH=. .venv/bin/python -m r1_agent --listen --hardware
```

`--listen` 默认走 DeepSeek，从 ASR 错字恢复意图。打字 `--text` 仍用本地规则；加 `--deepseek` 则文本也走模型。密钥：`DEEPSEEK_API_KEY` 或 `deepseek_key.txt`。动作白名单见 `actions.json`，Skill 见 `skill/control-unitree-r1/SKILL.md`。

如需为本次运行预先提供身份、场景或回答风格，可使用 `--context`。学生场景包用 `--scene` 加载组合、别名和 `context.txt`，规则规划和 DeepSeek 共用：

```bash
PYTHONPATH=. .venv/bin/python -m r1_agent --text "校长来了" --scene scenes/classroom
PYTHONPATH=. .venv-r1/bin/python -m r1_agent \
  --listen --continuous --hardware \
  --scene scenes/classroom \
  --context "涉及动作时先说明将要做什么，再执行。"
```

`--scene` 目录里放 `context.txt` 和 `pack.json`。`pack.json` 只能引用 `actions.json` 已有原子动作，不能新增关节动作。`--context` 会接在场景 `context.txt` 后面。

当前固件上行走写 API 可能返回 `127`；上肢固定动作、ASR、TTS 已在 Linux 真机用过。现场需要急停在手。

## 上肢模仿 / 真机跟臂

MediaPipe 跟臂与问答 Demo **分开**：模仿库左右是自拍镜像（人右手 → 机器人左臂），问答 `actions.json` 是机器人自己的左右。真机只走跑 811 + `rt/arm_sdk`。环境、肘零点换算、命令见 [docs/R1_imitate跟臂.md](docs/R1_imitate跟臂.md)，短命令表见 [imitate/README.md](imitate/README.md)。

```bash
PYTHONPATH=. .venv-r1/bin/python -m imitate --r1-camera --no-capture --full-model --hardware
```

## Ubuntu 操作指南

完整部署、代理配置、API key、连续上下文、ASR 异常和真机安全检查请参阅 [docs/Ubuntu操作指南.md](docs/Ubuntu操作指南.md)。

## 本版本改进

- 网卡默认 `auto`：选用带 `192.168.123.x` 的接口，Mac（`en5`）和 Ubuntu（`enp7s0` 等）共用同一套命令。
- 增加 `--scene`：加载学生场景目录（`context.txt` + `pack.json` 组合/别名），规则规划器和 DeepSeek 共用。
- 增加 `--context`：启动时可注入约定的机器人身份、课堂场景和回答风格，并接在场景 `context.txt` 后面。
- 增加连续对话：`--continuous` 在同一进程内保留 DeepSeek 上下文，避免每轮重新认识机器人。
- 增加步数规划提示：前进/后退支持 `1～10` 步，由移动原子动作组合。
- 语音轮次以静音结束：开场播报「请说」，说完后约 3 秒没有新 ASR 包才提交，不会按固定时长截断。
- 保留 `scripts/dds_robot_modified.py` 作为 ready-pose/绝对角度开发稿；默认入口仍是 `r1_agent/dds_robot.py`，避免未经验证的角度改造直接进入真机。
