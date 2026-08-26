# R1 分层真机验收与单项排障

本流程一次只验证一个边界。任何一步失败都停止后续步骤；不要启动“补救动作”。当前没有挂架，因此只允许已知稳定站立状态下的小幅、慢速上肢单项测试。移动测试必须另行清空更大区域并逐项获得现场确认。

## 每次运动前的现场门禁

终端停在预演结果后，由现场操作员逐句确认：

```text
环境清空
急停在手
机器人稳定
允许执行当前命名测试
```

确认只对当前一次、当前幅度有效。出现抖动、异响、意外位移、明显跟踪误差、倾斜、温度异常或通信中断时立即物理急停，保存脱敏终端摘要，不自动重试。

## 固定顺序

| 层级 | 测试 | 运动 | 当前状态 |
|---|---|---:|---|
| H0 | Python、Schema、编译器、包与 C++ Gateway 自动测试 | 否 | 已通过 |
| H1 | `192.168.123.161/.164` 网络 | 否 | 2026-08-25 已通过，验收前复测 |
| H2 | RPC 读取 FSM | 否 | FSM 811 已读到，验收前复测 |
| H3 | `rt/lowstate` 只读反馈 | 否 | 35 电机已读到，验收前复测 |
| H4 | R1 ASR | 否 | 已识别“你好你好。”，验收前复测 |
| H5 | R1 TTS | 否 | 返回码 0，验收前复测 |
| H6 | 右腕回归：0.12 rad 后 0.35 rad | 是 | 当前项目二进制已通过 |
| H7 | 每个新增关节小幅单项 | 是 | 右肩 pitch 小幅与目标幅度已通过；其他关节未开始 |
| H8 | 每个手势小幅模板 | 是 | 未开始 |
| H9 | 每个手势目标幅度 | 是 | 未开始 |
| H10 | 前后 `move_for` | 是 | 未开始 |
| H11 | 横向 `move_for` | 是 | 未开始 |
| H12 | `turn_relative` 10°、20°、30° | 是 | 未开始 |
| H13 | 语音组合与 DeepSeek 工具调用 | 是 | 本地安全 Agent 监督试验已通过；DeepSeek/生产 Gateway 未开始 |
| H14 | `.r1motion` 导入、复验、缩放试验 | 是 | 模型门禁未解除 |

## 构建

```bash
cd /home/henrick/具身智能课程第一部分/r1-agent-motion
cmake -S hardware-tests -B build/hardware-tests \
  -DUNITREE_SDK2_DIR=/home/henrick/unitree_sdk2-main \
  -DCMAKE_BUILD_TYPE=Release
cmake --build build/hardware-tests -j2

export R1_LOCO_CLIENT_BIN=/home/henrick/unitree_sdk2-main/build/bin/r1_loco_client
export R1_ARM_FEEDBACK_TEST_BIN="$PWD/build/hardware-tests/r1_arm_feedback_test"
export R1_ASR_LISTENER_BIN="$PWD/build/hardware-tests/r1_asr_listener"
export R1_TTS_SAY_BIN="$PWD/build/hardware-tests/r1_tts_say"
export R1_SAFE_WRIST_WAVE_BIN="$PWD/build/hardware-tests/r1_safe_wrist_wave"
export R1_SAFE_RIGHT_SHOULDER_PITCH_BIN="$PWD/build/hardware-tests/r1_safe_right_shoulder_pitch_trial"
```

项目自有的腕部测试已迁入 `hardware-tests/`，不再依赖或继续修改 SDK 示例目录。

## H0–H5：不运动

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest
ctest --test-dir build/gateway --output-on-failure
ping -c 4 192.168.123.161
ping -c 4 192.168.123.164
./scripts/r1ctl hardware-test fsm-read --interface enp7s0 --run
./scripts/r1ctl hardware-test lowstate-read --interface enp7s0 --run
./scripts/r1ctl hardware-test asr --interface enp7s0 --run
./scripts/r1ctl hardware-test tts --interface enp7s0 --text "语音测试成功。" --run
```

`lowstate-read` 只创建订阅者，不创建 ArmSdk publisher。它是关节角、速度、估计力矩、温度和 IMU 的只读反馈，不会让机器人动作。ASR 实测固件可能持续 `is_final=false`；最后一条有效文本静默 1.5 秒后被接受。

## H6：右腕回归

先预演，不会启动二进制：

```bash
./scripts/r1ctl hardware-test wrist-wave --interface enp7s0 --scale small
```

完成四句现场确认后，先运行 0.12 rad：

```bash
./scripts/r1ctl hardware-test wrist-wave --interface enp7s0 --scale small --run --confirm START
```

CLI 门禁解除后，真机程序还会再次显示具体幅度并等待输入 `START`。小幅返回误差、IMU 和温度正常后，重新做一次现场确认，才可改为 `--scale full` 验证已接受的 0.35 rad 模板。

程序监控全部 13 个 ArmSdk 电机而不只是右腕；任一温度超过 `classroom-upper-v1` 的 70°C 门禁都会回位并释放。若只读检查发现某个关节接近门禁，应先等待冷却并复测，不要把“尚未超过门禁”理解为建议立即运动。

## H7–H14

每个关节、模板、方向、角度和动作包都是独立测试，不共享一次确认。新动作先使用 `hardware_trial_scale=0.35`，通过后也只推进数据库生命周期，不自动注册为 `classroom_enabled`。

2026-08-26 根据课堂画面可见度反馈，最终扩大档为右腕 `+1.70 rad`、右肩俯仰
`-2.00 rad`。右腕使用保留 `0.15 rad` 余量后的可用大幅值，没有按要求机械翻倍到
超过官方硬限位的 `2.40 rad`；右肩按 `-1.00 rad` 翻倍。二者均没有进行新的真机验收。

首个 H7 固定试验为右肩俯仰相对当前姿态 `-0.07 rad`，不开放运行时关节名或幅度。先预演：

```bash
./scripts/r1ctl hardware-test right-shoulder-pitch --interface enp7s0
```

完成四句现场确认后执行：

```bash
./scripts/r1ctl hardware-test right-shoulder-pitch --interface enp7s0 --run --confirm START
```

真机程序还会再次等待输入 `START`，并监控全部 ArmSdk 电机温度、IMU 和右肩回位误差。小幅档为 `-0.07 rad`；小幅试验通过后，目标幅度档固定封顶为 `-0.20 rad`，使用 `--scale full`，不接受任意运行时幅度。

当前外部 MJCF 缺 `head_pitch/head_yaw` 关节且含无效腕部接触排除项，因此 H14 本地权威复验会按设计失败。修复并锁定 `r1-edu-26dof-v1` 映射以前，不允许借用云端通过结果绕过此门禁。

## 脱敏记录

只保存日期、测试名、软件/配置版本、FSM、幅度、耗时、最大反馈误差、温度范围、是否急停、通过/失败和故障码。不要提交学生音频、原始转写、视频、IP 之外的个人信息或 API 密钥。
