# R1 真机单项功能测试与排障流程

本流程用于验证课堂上肢动作的链路，并把问题定位到网络、RPC、DDS 反馈、单关节轨迹或复合手势中的某一层。一次测试只运行一个测试项；禁止同时启动多个 SDK 控制程序。

> 适用范围：R1 已知的 `rt/arm_sdk` 上肢 DDS 路径。流程不使用 `rt/lowcmd`，不测试走路、跳跃、跳舞、鞠躬等全身动作。

## 固定安全前置条件

开始任何 `motion` 测试前，现场操作员必须逐项确认：

1. R1 位于挂架中；腿部不承重、不测试移动。
2. 遥控器物理急停在操作员手中，且操作员知道如何使用。
3. 机器人周围至少 1 米无人员、桌椅、线缆等障碍物。
4. R1 无故障提示、无异响、上肢未被外力抓握。
5. 只保留本次测试程序；已关闭其他可能发布 DDS 命令的程序。
6. 开始录像，记录机器人全身、操作者、遥控器和终端输出。

若出现抖动、异响、意外动作、控制权无法释放或通信异常：立即按物理急停，不要同时启动“补救脚本”。保存终端输出和录像，再进入排障记录。

## 测试层级

按编号顺序执行；上一步失败时，不运行下一步。

| 编号 | 单项测试 | 是否运动 | 验收与定位价值 |
|---|---|---:|---|
| T0 | 本地离线计划校验 | 否 | 验证 Agent/Schema/动作库边界，不需要 R1 |
| T1 | 网络与本机探测 | 否 | 确认网卡名和本机环境；不会连接 R1 |
| T2 | RPC 读取 FSM | 否 | RPC、DDS 网络和 `sport` 服务是否可用 |
| T3 | `rt/lowstate` 反馈 | 否 | 关节状态话题和上肢 DDS 服务是否可见 |
| T4 | 右手腕小幅测试 | 是 | 最小上肢轨迹、接管/回位/释放是否正常 |
| T5 | 双臂组合手势 | 是 | 多关节同步轨迹是否正常 |
| T6 | 新模板验证 | 是 | 每个新增课堂动作独立验收，不能跳过 T4 |

## T0：离线计划校验

```bash
cd /home/henrick/具身智能课程第一部分/r1-agent-motion
./scripts/r1ctl plan --file tests/fixtures/wave-right-valid.json
./scripts/r1ctl plan --file tests/fixtures/unsupported-dance.json
```

预期：第一个计划 `valid: true`、`executable: false`，因为动作还未教师启用；第二个计划应拒绝未注册的 `dance`。两次均必须显示 `motion_sent: false`。

## T1：本机探测

```bash
./scripts/r1ctl probe --offline --interface enp7s0
./scripts/r1ctl status
```

预期：只输出本机网卡是否存在，并写入 `logs/latest-probe.json`。它故意不 ping、不初始化 DDS、不向 R1 发包。

## T2：RPC 只读 FSM

先编译 SDK 中的 `r1_loco_client`，并设置二进制的绝对路径。此程序只调用 `GetFsmId` 和 `GetFsmMode`，不要附带任何 `--set_*`、`--start`、`--damp` 等参数。

```bash
export R1_LOCO_CLIENT_BIN=/absolute/path/to/r1_loco_client
./scripts/r1ctl test rpc-read-state --interface enp7s0
./scripts/r1ctl test rpc-read-state --interface enp7s0 --run
```

第一条是预演：打印将执行的命令但不运行。第二条执行一次并将标准输出、错误输出与退出码写入 `logs/`。

若失败：先记录命令、退出码和原始错误。依次检查物理网线、主机 IP/路由、网卡名、R1 服务版本；R1 `ai_sport >= 1.0.2.0` 使用 `sport` 服务，旧版使用 `loco`。不要为了“试一下”改为模式切换 RPC。

## T3：只读 `rt/lowstate`

项目提供了一个只订阅 `rt/lowstate`、打印电机数、且**从不创建 `ArmSdk` publisher** 的小工具：`hardware-tests/r1_arm_feedback_test.cpp`。首次在开发电脑构建：

```bash
cd /home/henrick/具身智能课程第一部分/r1-agent-motion
cmake -S hardware-tests -B build/hardware-tests \
  -DUNITREE_SDK2_DIR=/home/henrick/unitree_sdk2-main
cmake --build build/hardware-tests --target r1_arm_feedback_test
```

工具的路径由环境变量指定：

```bash
export R1_ARM_FEEDBACK_TEST_BIN=/absolute/path/to/r1_arm_feedback_test
./scripts/r1ctl test arm-feedback --interface enp7s0
./scripts/r1ctl test arm-feedback --interface enp7s0 --run
```

验收：在超时窗口内收到稳定的关节反馈。若 T2 成功而 T3 失败，优先检查 DDS 话题名、域 ID、网卡选择与 R1 上肢服务状态，而不是修改关节轨迹。

## T4：已验证右手腕小幅动作

仅在 T0–T3 全部通过且安全前置条件满足后执行。SDK 仓库已有 [r1_safe_wrist_wave.cpp](../../unitree_sdk2-main/example/r1/high_level/r1_safe_wrist_wave.cpp)，其行为是右腕缓慢滚转 `+0.35 rad`（约 `20°`）、平滑回位并释放控制权。

```bash
export R1_SAFE_WRIST_WAVE_BIN=/absolute/path/to/r1_safe_wrist_wave
./scripts/r1ctl test wrist-wave --interface enp7s0
./scripts/r1ctl test wrist-wave --interface enp7s0 --run --confirm START
```

`--confirm START` 只解除 CLI 的防误触；已验证二进制仍会要求在终端再次输入 `START`，其交互提示会直接显示在终端。若测试异常，立即急停并保留自动生成的日志；不要在未检查日志前改为执行双臂动作。

## T5：已验证双臂手势

仅在 T4 验收通过后，才可运行此前真机验证过的 `r1_safe_dual_arm_gesture`：

```bash
export R1_SAFE_DUAL_ARM_GESTURE_BIN=/absolute/path/to/r1_safe_dual_arm_gesture
./scripts/r1ctl test dual-arm-gesture --interface enp7s0
./scripts/r1ctl test dual-arm-gesture --interface enp7s0 --run --confirm START
```

它不代表 `wave`、`salute` 等新课堂模板已经可用；它只验证了双肩与双腕的有限组合轨迹路径。

## T6：新动作模板验收

每个新模板（如 `wave_right_v1`）必须单独走以下记录：

1. 文档记录关节集合、相对当前姿态的最大偏移、持续时间和回位策略。
2. 代码始终从 `rt/lowstate` 当前姿态开始，禁止固定绝对起始角。
3. 先只动一个关节、小偏移、慢速度；验收后再逐项扩大，但每次都独立录像。
4. 记录机器人型号、固件、SDK commit、网卡、测试日期、操作者、日志与视频路径。
5. 教师/开发者审阅通过后，才可把动作注册表中对应 `available` 改为 `true`。

## 故障记录模板

每次失败在日志外另存一条记录：

```text
时间：
测试编号与名称：
机器人型号 / 固件：
SDK 二进制路径与版本：
网卡名与主机 IP：
机器人 FSM（若 T2 可读）：
终端原始输出：
动作现象（或“未动作”）：
是否使用急停：
录像/照片路径：
下一步：只回退到最近一个通过的测试层级。
```
