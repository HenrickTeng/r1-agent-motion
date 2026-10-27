# R1 教师控制台

关键词：Unitree R1、宇树 R1 EDU、人形机器人、humanoid robot、具身智能、embodied AI、教师控制台、teacher console、CycloneDDS、arm_sdk、MediaPipe、手势识别、动作模仿、双目相机、stereo vision、近距迎宾、DeepSeek、图形化编程

教师笔记本上的课堂控制台，用来指挥 Unitree R1 EDU：白名单命名动作、键盘和手势、校园识物、图形化程序、语音问答、原地近距迎宾，以及上肢动作模仿。机器人不接入教学平台公网。网页只监听 `127.0.0.1`。

这是实验室代码。真机各项还没有按 [docs/实验室测试清单.md](docs/实验室测试清单.md) 整项跑通。连真机时遥控器急停拿在手里。

## 仓库里有什么

| 功能 | 入口 | 做什么 |
| --- | --- | --- |
| 教师控制台 | `python -m r1_studio` | 浏览器 http://127.0.0.1:8765 。八个选项卡见下文。 |
| 语音 / 文本动作 | `python -m r1_agent` | 中文句子或 R1 麦克风 → `actions.json` 里的动作名 → 网线 DDS。左右是机器人自己的左右。 |
| 上肢模仿仿真 | `python -m imitate` | MediaPipe Pose → 双臂 10 轴，MuJoCo 预览。人的右手对应机器人左臂（蓝）。 |
| 左右眼试看 | `scripts/r1_stereo_preview.py` | 单独网页看左眼、右眼和本地视差。不走教师台，也不当安全距离。 |

更长的操作说明在 [docs/教师控制台.md](docs/教师控制台.md)。模仿键位在 [imitate/README.md](imitate/README.md)，真机跟臂在 [docs/R1_imitate跟臂.md](docs/R1_imitate跟臂.md)。

## 环境

用 Python 3.12。系统自带的 3.13 导入 CycloneDDS 会失败。

```bash
python3.12 -m venv .venv-r1
.venv-r1/bin/pip install -e '.[studio,imitate,dev]'
.venv-r1/bin/pip install 'cyclonedds==0.10.2'
.venv-r1/bin/pip install -e ../unitree_sdk2_python --no-deps
```

`unitree_sdk2_python` 放在本仓库的上一级目录。只跑 MuJoCo 模仿、不连机器人时，不必装 CycloneDDS。

笔记本用以太网直连机器人：网卡上要有 `192.168.123.x`（本机常见 `192.168.123.99`，机器人 `192.168.123.161`）。`--interface auto` 会选这张网卡。

语音和校园识别需要 DeepSeek。密钥放在环境变量里，不要写进仓库：

```bash
export DEEPSEEK_API_KEY='你的 key'
```

## 教师控制台

```bash
# 只看网页，不连机器人
PYTHONPATH=. .venv-r1/bin/python -m r1_studio

# 连真机，并打开头部 video_hub 图传
PYTHONPATH=. .venv-r1/bin/python -m r1_studio --hardware --r1-camera --interface auto
```

浏览器打开 http://127.0.0.1:8765 。点选项卡只是预览，再点该页的「开始」才会发指令。「结束」只停止新指令。

| 选项卡 | 行为 |
| --- | --- |
| 键盘遥控 | W/S 前后，A/D 横移，Q/E 转向，空格停下。开始后要点一次 QWEASD 格子，浏览器才接收按键。 |
| 手势操作 | 笔记本用 MediaPipe Hands；机载超广角用全身 Pose。 |
| 校园识别 | 看一帧画面，按校园背景回答「这是什么、放哪里」。没有 Key 时退回本地检测草稿。 |
| 图形化编程 | 把白名单动作排成程序，可下载 `.r1prog.json`。 |
| 语音问答 | 打字或听一轮，规划器只输出动作库里的名字。 |
| 近距迎宾 | 在 video_hub 右眼画面上用肩宽或躯干估距。约 0.5–1.8 米原地挥手；0.3–0.5 米只提醒退后；0.3 米内停手。这个模式不走路。 |
| 动作模仿 | 人抬右手，机器人左臂跟着动。须在走跑模式。 |
| 扳手腕 | 本页不进调试、也不发走跑。用遥控器进入调试，跑原来的扳手腕程序。结束后必须关机再开机。 |

图传走 `video_hub` 的单张 JPEG（1280×720）。2026-09-24 挡住左眼画面不变，这路是右眼单独在拍。左右眼 UDP 5002/5003 要另开 stereo patch，并且会和 video_hub 冲突，所以教师台不切过去。

近距距离来自骨架，不是双目深度图。肩宽按约 0.38 米、肩到髋按约 0.52 米，水平视场按约 120° 估计。数字可以差几十厘米，先看档位。

单功能探测不打开网页、也不驱动机器人：

```bash
PYTHONPATH=. .venv-r1/bin/python -m r1_studio --probe gestures --camera 0
PYTHONPATH=. .venv-r1/bin/python -m r1_studio --probe vision --camera 0
PYTHONPATH=. .venv-r1/bin/python -m r1_studio --probe keys
PYTHONPATH=. .venv-r1/bin/python -m r1_studio --probe llm
```

## 语音动作和模仿仿真

```bash
PYTHONPATH=. .venv-r1/bin/python -m r1_agent --text "请介绍自己，然后挥右手"
PYTHONPATH=. .venv-r1/bin/python -m r1_agent --listen --hardware --scene scenes/classroom

PYTHONPATH=. .venv-r1/bin/python -m imitate --self-test
PYTHONPATH=. .venv-r1/bin/python -m imitate --demo
PYTHONPATH=. .venv-r1/bin/python -m imitate --camera 0 --full-model
```

`--scene` 目录里是 `context.txt` 和 `pack.json`。`pack.json` 只能引用 `actions.json` 已有的动作，不能新增关节轨迹。大模型只许输出动作名和一句口头回复。

## 左右眼试看

教师台继续用 video_hub。要看左右眼时，在 App 里打开 Stereo patch PC1、关掉 video_hub，然后：

```bash
export R1_ORIN_PASSWORD='Orin 登录口令'
PYTHONPATH=. .venv-r1/bin/python scripts/r1_stereo_preview.py
```

浏览器打开 http://127.0.0.1:8766 。深度是电脑上用左右眼做的 SGBM，左侧搜不到的边已裁掉。官方 `/dev/video-dep` 不在这页里。看完记得关 stereo patch、开回 video_hub。

## 测试

```bash
PYTHONPATH=. .venv-r1/bin/python -m pytest
```

真机勾选顺序见 [docs/实验室测试清单.md](docs/实验室测试清单.md)。

## 安全

- 走跑模式是 FSM 811；上肢接管后可能是 816。没站稳不要从网页发令。
- 软急停只停步并锁上肢，不能代替遥控器急停。拔网线停不了已经发出的步态。
- 控制台不要暴露到公网。
- 跳舞、下蹲、奔跑这类动作不在白名单里。
