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
