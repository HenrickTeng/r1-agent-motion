# R1 Agent Ubuntu 操作指南

本文档用于在 Ubuntu 笔记本上运行 R1 语音动作 Demo。当前版本使用 R1 自带麦克风和 ASR，通过 DeepSeek 将自然语言规划为安全动作，再由 Python DDS 控制机器人。

## 1. 网络检查

机器人网口使用 `enp7s0`（以本机 `ip a` 实际结果为准）。典型网络配置如下：

```text
笔记本：192.168.123.99/24
机器人：192.168.123.161
``` 

确认能收到机器人网络包：

```bash
ip a show enp7s0
ping 192.168.123.161
```

## 2. Python 环境

项目需要 Python 3.12 环境。Python 3.13 可能出现 CycloneDDS 的 `_Py_IsFinalizing` 动态库错误。

如果已有 `.venv-r1`，直接使用它；首次安装可以执行：

```bash
python3.12 -m venv .venv-r1
.venv-r1/bin/pip install -e '.[dev]'
.venv-r1/bin/pip install 'cyclonedds==0.10.2' numpy
.venv-r1/bin/pip install -e ../../unitree_sdk2_python --no-deps
```

## 3. DeepSeek API Key

临时设置（只对当前终端有效）：

```bash
export DEEPSEEK_API_KEY='sk-你的真实密钥'
```

长期设置：

```bash
echo 'export DEEPSEEK_API_KEY="sk-你的真实密钥"' >> ~/.bashrc
source ~/.bashrc
```

不要把真实 key 写入 Git、截图或提交到 GitHub。检查是否已设置但不显示完整 key：

```bash
test -n "$DEEPSEEK_API_KEY" && echo 'API key 已设置' || echo 'API key 未设置'
```

## 4. 网络代理

如果使用本机代理 `127.0.0.1:7897`，建议只保留 HTTP/HTTPS 代理：

```bash
unset ALL_PROXY all_proxy
export HTTP_PROXY=http://127.0.0.1:7897
export HTTPS_PROXY=http://127.0.0.1:7897
```

不要同时保留 `ALL_PROXY=socks://...`，部分 Python 网络库会优先读取它并导致 DeepSeek 认证或连接失败。

测试网络（返回 `401` 也说明网络已连通）：

```bash
curl -I -x http://127.0.0.1:7897 https://api.deepseek.com
```

## 5. 启动语音 Demo

推荐使用连续模式，让 DeepSeek 在同一个进程中保留多轮上下文：

```bash
cd /home/henrick/具身智能课程第一部分/r1-agent-motion-ubuntu/r1-agent-motion-feat-mac-named-action-demo

PYTHONPATH=. .venv-r1/bin/python -m r1_agent \
  --listen \
  --continuous \
  --hardware \
  --interface enp7s0 \
  --context "你是学校里的 Unitree R1 课堂助手，面对初中生使用简短友好的中文回答。请理解前进、后退、转向等口语和数量表达，并将它们转换成动作目录中的安全动作。涉及多个动作时按顺序执行。"
```

说话后，终端会先打印 ASR 文本、DeepSeek 回复和动作列表，再执行动作。

## 6. 安全规则

- 同一计划里的行走/转向可以和上肢动作同时执行。
- 前进和后退支持明确提出的 `1～10` 步，由移动原子动作重复组合。
- 每轮开始会播报「请说」；说完后约 3 秒没有新识别结果才提交，不会按固定说话时长截断。
- 行走前机器人必须处于固件 `FSM 811` 的 walk/run 模式；否则只测试上肢动作。
- 真机测试时保持遥控器在手边，随时准备急停。

## 7. 上肢模仿跟臂

语音问答不要和模仿跟臂混用动作名。跟臂文档：[R1_imitate跟臂.md](R1_imitate跟臂.md)。推荐命令：

```bash
PYTHONPATH=. .venv-r1/bin/python -m imitate --r1-camera --no-capture --full-model --hardware
```

须走跑 FSM 811、物理急停在手。软急停不要 Damp。

## 8. 教师课堂控制台

本地网页：手势、键盘、失物识别、图形化编程，见 [教师控制台.md](教师控制台.md)。

```bash
PYTHONPATH=. .venv-r1/bin/python -m r1_studio --hardware
```

浏览器打开后，在画面下方再选笔记本摄像头或 R1 机载摄像头。

## 9. 常见问题

### 模糊识别退化为固定提示

如果输出“我目前能执行挥手、敬礼……”而没有动作，通常是 DeepSeek 请求失败，程序退回本地规则。检查 API key、代理和网络，不要先修改 DDS 动作脚本。

### 说话被截断

本轮在「请说」之后开始听。只要还在说话、ASR 还在出包，就不会提交；停顿约 3 秒后才交给模型。若一直没有可用中文，才按 `--listen-timeout` 超时。

### 机器人无法行走

看到 `loco fsm_id=816, need 811 walk/run mode` 时，先让机器人站稳，并用遥控器切换到 walk/run 模式，再测试前进、后退或转向。

### 修改 ready pose

`scripts/read_ready_pose.py` 用于读取站立时的 13 个关节角度。`scripts/dds_robot_modified.py` 是后续绝对角度开发版本，默认运行入口仍是 `r1_agent/dds_robot.py`，替换前请先备份并在无风险动作下验证。
