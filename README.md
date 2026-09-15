# R1 Agent Skill Demo

本仓库有两块，**不要混用动作名和左右约定**：

| | 入口 | 说明 |
| --- | --- | --- |
| 问答 / 语音 Demo | `python -m r1_agent` | 自然语言或 R1 麦克风 → `actions.json` 命名动作 → 网线 DDS 执行。左右是**机器人自己的**左右。 |
| 上肢动作模仿 | `python -m imitate` | 摄像头 / 合成姿态 → MediaPipe Pose → R1 10 个上肢关节；MuJoCo 仿真，可选真机跟臂。自拍：**人的右手 → 机器人左臂（蓝）**。 |

课程平台接入**仿真模仿**请看下面「上肢动作模仿」，完整命令与键位见 **[imitate/README.md](imitate/README.md)**。真机跟臂另见 [docs/R1_imitate跟臂.md](docs/R1_imitate跟臂.md)。

---

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

## 上肢动作模仿（仿真可上课程平台）

详细步骤、键位、导出格式：**[imitate/README.md](imitate/README.md)**。

人站在摄像头前（或用合成姿态），估计肩/肘/腕，映射到 R1 双臂 10 轴，MuJoCo 里预览并做自碰预警。精度只要求「看着像」：肩抬起来、肘弯了、左右分开。代码在 `imitate/`，不经过问答规划器和 `actions.json`。

**课程平台只需要仿真**，不要加 `--hardware`，也不必装 CycloneDDS / 连机器人：

```bash
python3.12 -m venv .venv-r1
.venv-r1/bin/pip install -e '.[imitate,dev]'
PYTHONPATH=. .venv-r1/bin/python -m imitate --self-test
PYTHONPATH=. .venv-r1/bin/python -m imitate --demo
PYTHONPATH=. .venv-r1/bin/python -m imitate --view --full-model
PYTHONPATH=. .venv-r1/bin/python -m imitate --camera 0 --full-model
```

- `--self-test`：无窗自检，适合 CI / 平台冒烟。
- `--demo`：无摄像头时用键盘切合成姿势。
- `--view --full-model`：官方网格循环播放老师姿势（垂臂、T-pose、前伸、双手胸前、举手、敬礼）。
- `--camera 0`：笔记本摄像头跟臂；换人或换镜头先 `--calibrate`（不要加 `--hardware`）。

自拍镜像：窗口里人的右手对应机器人**左臂（蓝）**。保存到 `imitate/mirror_library/`，schema `r1-arm-imitate-mirror/v1`，**没有**问答用的 `coeffs`。问答里的 `salute_right` 是机器人右臂，和模仿里的 `salute_user_right` 不是同一个动作。

仿真肘零点（官方 `r1.xml` 网格）和真机走跑编码器零点不是同一套；平台演示以 MuJoCo 画面为准即可。真机跟臂（走跑 811 + `rt/arm_sdk`、肘换算、急停）见 [docs/R1_imitate跟臂.md](docs/R1_imitate跟臂.md)，命令仍写在 [imitate/README.md](imitate/README.md)。

## Ubuntu 操作指南

完整部署、代理配置、API key、连续上下文、ASR 异常和真机安全检查请参阅 [docs/Ubuntu操作指南.md](docs/Ubuntu操作指南.md)。教师课堂控制台（手势 / 键盘 / 失物识别 / 图形化编程）见 [docs/教师控制台.md](docs/教师控制台.md)。

## 本版本改进

- 网卡默认 `auto`：选用带 `192.168.123.x` 的接口，Mac（`en5`）和 Ubuntu（`enp7s0` 等）共用同一套命令。
- 增加 `--scene`：加载学生场景目录（`context.txt` + `pack.json` 组合/别名），规则规划器和 DeepSeek 共用。
- 增加 `--context`：启动时可注入约定的机器人身份、课堂场景和回答风格，并接在场景 `context.txt` 后面。
- 增加连续对话：`--continuous` 在同一进程内保留 DeepSeek 上下文，避免每轮重新认识机器人。
- 增加步数规划提示：前进/后退支持 `1～10` 步，由移动原子动作组合。
- 语音轮次以静音结束：开场播报「请说」，说完后约 3 秒没有新 ASR 包才提交，不会按固定时长截断。
- 增加上肢动作模仿：`python -m imitate`，MuJoCo 仿真可单独上课程平台；真机跟臂走跑 811 + `rt/arm_sdk`。说明见 [imitate/README.md](imitate/README.md)。
- 增加教师电脑本地控制台：`python -m r1_studio`。手势操作、键盘遥控、失物单帧识别、Scratch 风格方块编程（导出 `.r1prog.json`）。R1 不接入教学平台。见 [docs/教师控制台.md](docs/教师控制台.md)。
- 分阶段探测：`python -m r1_studio --probe gestures --camera 0` 只打印手势 JSON；动作序列在仿真里编排：`python -m imitate --edit-sequence --full-model`。
- 保留 `scripts/dds_robot_modified.py` 作为 ready-pose/绝对角度开发稿；默认入口仍是 `r1_agent/dds_robot.py`，避免未经验证的角度改造直接进入真机。
