# R1 学生语音交互

链路为 R1 本地 ASR → 教师电脑 Agent → 本地 Teacher Bridge 双重校验 → R1 本地 TTS → 可选 Gateway 执行。只有识别文本会发给 DeepSeek；原始音频不会上传或写入项目数据库。

## 分层运行

先启动 loopback Teacher Bridge：

```bash
.venv/bin/python -m apps.teacher_bridge
```

离线文字与拒绝测试不会调用 TTS 或动作：

```bash
./scripts/r1_voice_agent.py --text "你好" --provider rule --dry-run
./scripts/r1_voice_agent.py --text "跳舞后鞠躬" --provider rule --dry-run
```

ASR/TTS 分项通过后，做一轮语音对话：

```bash
./scripts/r1_voice_agent.py --listen-once --provider rule \
  --bridge-url http://127.0.0.1:8765 --interface enp7s0
```

## DIY 直连模式（电脑麦克风）

课堂单机演示不需要启动 Teacher Bridge 和 gRPC Gateway。先在 R1 APP 中关闭原厂
语音助手，确保不使用 `L2+Select`。安装本地 ASR 并下载 Vosk 中文模型后，
当机器人已在 FSM 811、遥控器已切到走跑运控高速档时，可运行：

```bash
./scripts/r1_voice_agent.py --pc-mic-continuous --provider rule --diy-direct \
  --execute --session-id classroom-demo --interface enp7s0
```

默认使用 PipeWire/PulseAudio 的当前系统麦克风（`--pc-mic-device pulse`）。

每轮会用电脑麦克风录音 4 秒，可说“向前走一步”、“向后退一步”、“向左转”、
“向右转”、“挥右手”、“请移动右手腕关节”或“请移动右肩关节”。左右横移尚未开放。
该模式只暴露程序内置的已验收固定动作，不接受原始速度、任意关节、Shell 或 DeepSeek
生成动作。Agent 播报完回复后才执行动作，动作完成后重新监听，避免自回声。

R1 机载 `--listen-once/--continuous` 仅保留为只读 ASR 调试。当 `--diy-direct --execute`
启用时，程序会拒绝机载 ASR 参数，避免原厂助手和 DIY Agent 同时执行。

当前 DIY 四向语音使用固定的官方 RPC 参数：

```text
SetVelocity(vx=0.5, vy=0, omega=0, duration=1)
SetVelocity(vx=-0.3, vy=0, omega=0, duration=1)
SetVelocity(vx=0, vy=0, omega=0.5, duration=2)
SetVelocity(vx=0, vy=0, omega=-0.5, duration=2)
```

动作完成后固定调用 `StopMove()`，不开放学生输入原始速度。前进已完成真机验证；
后退与新版转向参数等待机器人回场后逐项确认。转向程序会比较动作前后的 IMU yaw，
偏航变化不足 3°时返回失败，不会仅凭 RPC 返回 `127` 报告成功。

8 月 25 日已验收的右腕、右肩监督动作也支持电脑麦克风。原始验收幅度分别为
`+0.35 rad` 和 `-0.20 rad`。最终课堂可见档按操作员要求调整为右腕 `+1.70 rad`
（约 97.4°）和右肩 `-2.00 rad`（约 114.6°）。右腕不能精确 double 到 `2.40 rad`，
因为会超过官方 `±1.9199 rad` 关节限位，因此使用保留 `0.15 rad` 余量后的固定档。
右腕、右肩往返时间分别延长到 3.5 秒和 6 秒，继续保留实际到达幅度、回位、温度、
IMU 和关节限位余量检查。这两个最终幅度没有进行新的真机验收，动作库保持 `draft`。

```bash
./scripts/r1_voice_agent.py --pc-mic-once --provider rule \
  --supervised-trial wrist-full \
  --trial-confirmation "ENABLE SUPERVISED HARDWARE TRIAL" \
  --execute --session-id classroom-wrist-test --interface enp7s0

./scripts/r1_voice_agent.py --pc-mic-once --provider rule \
  --supervised-trial shoulder-full \
  --trial-confirmation "ENABLE SUPERVISED HARDWARE TRIAL" \
  --execute --session-id classroom-shoulder-test --interface enp7s0
```

分别说“请移动右手腕关节”和“请移动右肩关节”。每个进程只允许执行一次，动作程序
继续负责回位、温度/IMU 检查和 ArmSdk 控制权释放。机器人充电或无人看护时只使用
`--dry-run`，不要使用 `--execute`。

连续模式在 TTS 返回后才重新启动 ASR 监听，因此不会边说边听造成自回声：

```bash
export DEEPSEEK_API_KEY='由教师环境注入，不写入文件'
./scripts/r1_voice_agent.py --continuous --provider deepseek \
  --bridge-url http://127.0.0.1:8765 --interface enp7s0
```

DeepSeek 输出最多修复一次，之后仍无效就拒绝。DeepSeek、TTS、Bridge 或 Gateway 任一失败时，当前轮不提交动作。离线规则适配器始终保留问候、安全拒绝和停止语义。

## 动作会话

教师必须在本机创建临时会话并输入固定确认语；停止会话后权限立即失效。示例 HTTP 请求中的教师身份和会话 ID 应由实际教师端 UI 生成：

```bash
curl -X POST http://127.0.0.1:8765/v1/classroom-sessions \
  -H 'content-type: application/json' \
  -d '{"session_id":"class-001","operator":"teacher","confirmation":"ENABLE CLASSROOM MOTION"}'
```

只有动作已显式注册为 `classroom_enabled`、计划双重校验通过、TTS 成功且命令行带 `--execute --session-id class-001` 时，Agent 才请求 Gateway。语音本身不是现场授权。

## 教师现场监督硬件试验

监督试验模式只用于已经完成小幅单关节资格测试后的目标幅度验收，不替代生产 Gateway 或课堂动作审批。一次进程只暴露一个固定动作、固定目标幅度和空参数，要求独立会话 ID、固定教师确认语和 `--execute`；同一进程最多执行一次。语音只选择本次已经预授权的动作，不能授权动作本身。

右腕与右肩分别使用独立进程：

```bash
./scripts/r1_voice_agent.py --listen-once --provider rule --execute \
  --supervised-trial wrist-full --session-id video-wrist-001 \
  --trial-confirmation 'ENABLE SUPERVISED HARDWARE TRIAL'

./scripts/r1_voice_agent.py --listen-once --provider rule --execute \
  --supervised-trial shoulder-full --session-id video-shoulder-001 \
  --trial-confirmation 'ENABLE SUPERVISED HARDWARE TRIAL'
```

固定语义分别为“移动右手腕关节”和“移动右肩关节”。Agent 生成严格单步 MotionPlan v2，TTS 成功后才调用固定二进制；二进制仍执行自身 `START`、温度、IMU、限位、回位和释放门禁。监督试验通过不会把动作设为 `classroom_enabled`。
