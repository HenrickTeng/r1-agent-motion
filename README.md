# R1 Agent Skill Demo

自然语言或 R1 麦克风 → 命名动作序列 → 笔记本网线直连 DDS 执行。

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
PYTHONPATH=. .venv/bin/python -m r1_agent --text "请介绍自己，然后挥右手"
PYTHONPATH=. .venv/bin/pytest
```

真机（同一网段，网卡名按实际修改）：

```bash
export UNITREE_SDK2_DIR=/path/to/unitree_sdk2-main
cmake -S robot -B build/robot -DUNITREE_SDK2_DIR="$UNITREE_SDK2_DIR"
cmake --build build/robot -j2
PYTHONPATH=. .venv/bin/python -m r1_agent --listen --hardware --interface enp7s0
```

可选 `DEEPSEEK_API_KEY` 与 `--deepseek`。动作白名单见 `actions.json`，Skill 见 `skill/control-unitree-r1/SKILL.md`。

当前固件上行走写 API 可能返回 `127`；上肢固定动作、ASR、TTS 已在真机用过。现场需要急停在手。
