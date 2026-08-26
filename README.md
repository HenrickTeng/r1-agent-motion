# R1 Agent Skill Demo

自然语言或 R1 麦克风 → 命名动作序列 → 笔记本网线直连 DDS 执行。

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pip install 'cyclonedds==0.10.2' numpy
.venv/bin/pip install -e ./unitree_sdk2_python --no-deps
PYTHONPATH=. .venv/bin/python -m r1_agent --text "请介绍自己，然后挥右手"
PYTHONPATH=. .venv/bin/pytest
```

Mac 上用 USB 网卡 `en5`，地址 `192.168.123.100`，直连 R1 `192.168.123.161`。C++ SDK 只有 Linux 预编译库，真机 demo 走 Python DDS。

```bash
PYTHONPATH=. .venv/bin/python -m r1_agent --listen --hardware --interface en5
```

`--listen` 默认走 DeepSeek，从 ASR 错字恢复意图。打字 `--text` 仍用本地规则；加 `--deepseek` 则文本也走模型。密钥：`DEEPSEEK_API_KEY` 或 `deepseek_key.txt`。动作白名单见 `actions.json`，Skill 见 `skill/control-unitree-r1/SKILL.md`。

当前固件上行走写 API 可能返回 `127`；上肢固定动作、ASR、TTS 已在 Linux 真机用过。现场需要急停在手。
