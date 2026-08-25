# R1 学生语音交互

## 已实现链路

```text
学生说话
  → R1 内置麦克风与离线 ASR
  → rt/audio_msg JSON
  → r1_voice_agent.py
  → 本地规则或 DeepSeek 对话规划
  → 本地响应校验与动作计划校验
  → R1 本地 TTS
  → 教师已使能时，执行已验证 wrist_wave
```

R1 的 ASR 和 TTS 都在机器人本地完成。只有选择 `--provider deepseek` 时，识别后的学生文本才会发送到 DeepSeek API。

## 构建

```bash
cd /home/henrick/具身智能课程第一部分/r1-agent-motion
cmake -S hardware-tests -B build/hardware-tests \
  -DUNITREE_SDK2_DIR=/home/henrick/unitree_sdk2-main
cmake --build build/hardware-tests \
  --target r1_arm_feedback_test r1_asr_listener r1_tts_say -j2
cmake --build /home/henrick/unitree_sdk2-main/build \
  --target r1_loco_client r1_safe_wrist_wave -j2
```

所需 R1 音频服务版本：`vui_service >= 2.2.0.0`、`vui module >= 2.0.0.3`。使用 App 或遥控器将麦克风切换到唤醒模式。

## 分层测试

先做离线文本测试，不连接机器人：

```bash
./scripts/r1_voice_agent.py --text "你好" --provider rule --dry-run
./scripts/r1_voice_agent.py --text "请跳舞" --provider rule --dry-run
./scripts/r1_voice_agent.py --text "请挥手" --provider rule --dry-run
```

再分别验证 ASR 和 TTS：

```bash
./build/hardware-tests/r1_asr_listener enp7s0 30
./build/hardware-tests/r1_tts_say enp7s0 "你好，语音系统测试成功。" 0
```

最后测试一轮不带动作的语音对话：

```bash
./scripts/r1_voice_agent.py --listen-once --provider rule --interface enp7s0
```

## 连续课堂对话

本地演示模式：

```bash
./scripts/r1_voice_agent.py --continuous --provider rule --interface enp7s0
```

本地规则模式只覆盖问候、能力介绍、安全拒绝和右手腕动作意图，用于验证硬件闭环。它不是通用问答模型。

DeepSeek 通用对话模式：

```bash
export DEEPSEEK_API_KEY="填入密钥"
./scripts/r1_voice_agent.py --continuous --provider deepseek --interface enp7s0
```

学校应先确认学生语音转写发送到云端模型的数据处理方案。不要把密钥写入项目文件或日志。

## 动作使能

默认情况下，Agent 即使生成有效动作计划也只会说“需要老师使能”，不会运动。教师在环境清空、急停在手并全程监督时，才能启动：

```bash
./scripts/r1_voice_agent.py --continuous --provider rule \
  --interface enp7s0 --enable-motion
```

程序要求教师输入：

```text
ENABLE CLASSROOM MOTION
```

这是本次进程的会话使能，不是永久授权。每次动作前程序还会读取 FSM `811`、验证计划只能包含一个 `wrist_wave`，再调用今天真机验证过的 `+0.35 rad` 回位模板。停止程序后使能自动失效。

## 现场固件差异

官方文档示例把默认 ASR 描述为非流式并提供 `is_final=true`，但本次 R1 实测消息持续为 `is_final=false`、置信度约 `0.5`。监听器已经兼容：忽略无语音标点，并在最后一条有效文本后静默约 `1.5 秒`作为稳定结果。原始 ASR、对话、TTS、动作和错误事件记录在 `logs/voice-agent.jsonl`。
