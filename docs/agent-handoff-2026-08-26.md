# R1 Agent Motion 项目 Agent 交接文档

> 更新日期：2026-08-26
> 用途：将当前全部工作成果、真机证据、已知问题和接手路线交给下一个 Agent。
> 原则：本文严格区分“代码存在”、“自动测试通过”、“真机通路通过”和“可作为课堂功能发布”。

## 1. 用户真正想要的结果

当前优先级不是继续扩建生产级审批平台，而是尽快完成一个稳定、显著、可录像演示的最小系统：

```text
学生语音或文本指令
→ Agent 理解意图
→ R1 Skill 把意图映射为已知命名动作
→ 按顺序执行语音、上肢动作和粗粒度移动
→ 任一步失败则停止后续步骤
→ R1 完成一个复合教学任务
```

期望的代表性演示指令是：

```text
请介绍自己，然后向前走一步，向左转，再挥右手。
```

用户已明确的产品决策：

- 保留已有上肢、头部、组合和自定义多关节动作。
- 受限下肢移动是必需功能。
- 行走采用“速度—时间”粗粒度语义，不追求精确距离。
- 移动与上肢动作只能串行，不同步。
- 跳舞、跳跃、跑步、鞠躬、下蹲和动态全身动作仍应拒绝。
- 开发阶段可以在现场护栏、急停和人员看护下快速迭代显著动作，但不能伪造未通过的测试结论。

## 2. 仓库、依赖和 Git 状态

### 2.1 路径

```text
项目：/home/henrick/具身智能课程第一部分/r1-agent-motion
SDK： /home/henrick/unitree_sdk2-main
MJCF：/home/henrick/unitree_rl_mjlab/src/assets/robots/unitree_r1/xmls/r1.xml
```

SDK 和 MJCF 都是外部依赖，不应把完整资产复制进项目 Git。配置环境变量：

```bash
export UNITREE_SDK2_DIR=/home/henrick/unitree_sdk2-main
export UNITREE_R1_MODEL_DIR=/home/henrick/unitree_rl_mjlab/src/assets/robots/unitree_r1/xmls
```

### 2.2 GitHub

```text
远程：git@github.com:HenrickTeng/r1-agent-motion.git
可见性：private
分支：main
当前提交：584faf4aa973cbcea2d111b18da65b95c459d5eb
当前提交说明：feat: add minimal R1 agent demo and official loco adapter
```

交接文档写入前工作树是干净的。GitHub CLI 已在该主机登录，但下一个 Agent 不应读取、记录或回显 SSH 口令、GitHub token 或 `DEEPSEEK_API_KEY`。

标签：

```text
v0.1.0-execution-platform
v0.2.0-motion-foundry
```

注意：`v0.2.0-motion-foundry` 已存在，但当前外部 MJCF 审计仍不通过。不要仅根据标签名就认为 MuJoCo 动作工厂已经可作为真机授权依据。尚未创建 `v0.2.1-hardware-validated`。

### 2.3 不得提交的本机文件

- `robot-control.zip` 和解压后的 `robot-control/`：仅作为参考 demo，已在 `.gitignore` 排除。
- `build/`、`.venv/`、数据库运行文件、真机日志、原始语音、视频、TLS 私钥和 API 密钥。
- Unitree SDK 二进制和许可未确认的 R1 mesh/MJCF 资产。

## 3. 当前架构：理想路径与 demo 路径

### 3.1 原始生产级架构

```text
公网教学平台
→ .r1motion 手工导出
→ 教师电脑：DeepSeek + Skill + Teacher Bridge + MuJoCo
→ mTLS gRPC
→ R1 PC1 Gateway
→ Unitree RPC / rt/arm_sdk
→ R1
```

这套架构的 Schema、Python 核心、Teacher Bridge、Gateway 核心和部分 SDK 已建立，但真机生产链路尚未打通。

### 3.2 当前优先使用的最小 demo 路径

```text
scripts/r1_demo.py
→ motion_core.demo.DemoPlanner
→ 命名 DemoAction 序列
→ DemoExecutor 串行执行
→ SimulatedBackend
   或 R1DemoHardware
→ R1 本地 TTS / 固定 rt/arm_sdk 二进制 / 固定 LocoClient 二进制
```

参考 `robot-control.zip` 后吸收了“控制器/工作器分离、结构化命名命令、可替换后端、串行执行”的思路，但没有采用任意 Python 代码上传执行或无白名单的动态方法调用。

## 4. 完成度真实矩阵

| 模块 | 代码 | 自动测试 | 真机 | 可发布 | 关键说明 |
|---|---|---|---|---|---|
| JSON Schema v1/v2 | 已实现 | 已通过 | 不适用 | 协议可用 | 严格未知字段拒绝 |
| 确定性 100 Hz 编译器 | 已实现 | 已通过 | 未执行生成轨迹 | 否 | 关节关键帧可编译；末端 IK 受模型限制 |
| MuJoCo 权威仿真 | 部分实现 | 失败路径已测 | 不适用 | 否 | 当前 MJCF 模型门禁未解除 |
| 简化碰撞预警 | 已实现 | 已通过 | 不授权真机 | 仅离线筛查 | 模式一：capsule/sphere 代理几何 |
| `.r1motion` SHA256 导入 | 已实现 | 已通过 | 未验证 | 否 | 只验完整性，不验身份签名 |
| Teacher Bridge | 已实现 | 已通过 | 未连真 Gateway | 否 | 默认 `MockGatewayClient` 且永不发动作 |
| DeepSeek 适配器 | 已实现 | 使用 mock 测试 | 未触发真机 | demo 对话可用 | 仅发识别文本，最多修复一次 |
| R1 ASR/TTS | 已实现 | 解析逻辑已测 | 已通过 | 可用于 demo | ASR 固件可持续 `is_final=false` |
| Gateway 核心 | 已实现 | CTest 通过 | 状态只读已连 | 否 | 校验、取消、幂等和串行骨架可用 |
| Gateway gRPC/mTLS | 已编译 | 核心已测 | 未部署 PC1 | 否 | 动作包安装 RPC 仍是拒绝骨架 |
| Gateway 上肢执行 | 未接通 | 不适用 | 固定独立程序已通 | 否 | `ExecuteInstalledAction()` 当前直接 `return false` |
| 固定上肢动作器 | 已实现 | 可编译 | 代表动作已通 | 开发 demo | 直接 `rt/lowstate → rt/arm_sdk → 回位` |
| R1 LocoClient 适配器 | 按官方 API 实现 | 已编译 | `0.5 m/s × 1 s` 已真机前进 | 是 | 动作执行后仍可返回 `127`，已兼容 |
| 最小 Agent demo | 已实现 | 已通过 | 上肢后端已用 | 开发 demo | 规则解析，还不是 DeepSeek 完整真机演示 |
| 公网平台 SDK | 已交付骨架 | 基本测试 | 不适用 | 可用于对接 | 项目不包含公网页面/账号系统 |

## 5. 已实现的主要代码

### 5.1 协议和核心数据

Schema 位于 `motion_core/schemas/`：

- `MotionDesignSpec v1`
- `CompiledTrajectory v1`
- `MotionPlan v2`
- `MotionPackage v1`

`MotionPlan v2` 只允许：

- `say`
- `action`
- `move_for`
- `turn_relative`
- `wait`

不允许 Agent 提交原始 DDS、`LowCmd`、关节数组、Shell、任意代码或运行时 `kp/kd`。

### 5.2 编译、IK、仿真和动作包

- `motion_core/compiler/compiler.py`：相对当前姿态、五次曲线、100 Hz、回位、限位/速度/加速度检查和确定性 SHA256。
- `motion_core/ik/dls.py`：阻尼最小二乘 IK 基础。
- `motion_core/simulator/service.py`：运动学检查和外部 MJCF 审计；当模型不完整时故意 fail closed。
- `motion_core/simulator/collision_warning.py`：角度制自定义多关节动作的代理几何扫描。
- `motion_core/packages/archive.py`：`.r1motion` 结构和文件 SHA256 校验。
- `apps/simulation_service/api.py`：编译、仿真、报告和 preview REST 接口；结果目前保存在进程内存。

简化碰撞分类：

```text
SAFE:      minimum distance >= 30 mm
WARNING:   10 mm <= minimum distance < 30 mm
DANGER:    minimum distance < 10 mm
COLLISION: MuJoCo reports contact or penetration
```

该扫描是预警器，不是真机执行授权器。

### 5.3 Teacher Bridge

`apps/teacher_bridge/` 已实现：

- SQLite/SQLAlchemy 动作、审批、会话和执行记录。
- 动作生命周期顺序迁移。
- `classroom_enabled` 动作查询。
- 计划本地校验和受限移动宏展开。
- 课堂会话开启/关闭。
- 动作包校验、导入和本地仿真。

关键限制：默认使用 `MockGatewayClient`，其 `execute_plan()` 一定报错，所以 Teacher Bridge 当前不会驱动真机。尚需实现 Python gRPC Gateway Client 并完成 mTLS 配置。

### 5.4 Agent、DeepSeek、ASR 和 TTS

- `motion_core/agent/adapters.py`：`DeepSeekAdapter` 和本地 `LocalSafetyAdapter`。
- `motion_core/agent/service.py`：`conversation / execute_motion / design_motion` 模式分离，无效输出最多修复一次。
- `scripts/r1_voice_agent.py`：R1 ASR → Agent → TTS，支持单次、连续、文本、DeepSeek 和监督式固定真机试验。
- `motion_core/voice/asr.py`：兼容 R1 固件持续 `is_final=false`的实测行为，使用最后有效文本的稳定退化。
- `hardware-tests/r1_asr_listener.cpp` 和 `r1_tts_say.cpp`：真机语音分项工具。

DeepSeek 仅会收到文本，不会收到原始音频。未在本仓库中使用真实 DeepSeek 请求触发过真机动作。

### 5.5 R1 Skill

Skill 位于 `skill/control-unitree-r1/`，定义执行模式和设计模式：

- 执行模式只组合 Teacher Bridge 返回的已发布动作。
- 设计模式只产生规格、编译和仿真任务，不能触发真机。
- 不允许学生、模型或 Skill 直接调用 DDS、SDK 示例、Shell 或固定真机试验二进制。

### 5.6 Gateway

`gateway/` 已有：

- `MotionPlan` 校验。
- FSM 811 和 LowState 新鲜度检查。
- 单任务串行、幂等 key、取消和失败后停止。
- gRPC proto：能力、状态、安装、校验、执行、取消和事件流。
- mTLS server 骨架。
- 可选 Unitree R1 真机适配器。

仍未完成：

- `InstallMotionPackage` 在 C++ gRPC server 中仍固定拒绝。
- `UnitreeR1Hardware::ExecuteInstalledAction()` 仍固定返回 `false`。
- 因此生产 Gateway 尚不能调用已实现的固定上肢动作。
- PC1 systemd 实际部署和教师电脑 mTLS 连通未验收。

## 6. 动作库和固定执行器

### 6.1 注册动作库

`motion-library/actions.json` 当前有 36 个注册项：

- 19 个上肢/头部/语义手势。
- 9 个课堂组合。
- 8 个受限移动宏。

注册不等于真机实现，也不等于课堂发布。动作表中绝大多数仍是 `draft` 且 `classroom_enabled=false`。

受限移动宏：

- `move_forward_slow`
- `move_backward_slow`
- `move_left_slow`
- `move_right_slow`
- `turn_left_10`
- `turn_right_10`
- `turn_left_20`
- `turn_right_20`

### 6.2 开发用固定 `rt/arm_sdk` 动作

`hardware-tests/r1_fixed_action.cpp` 支持：

```text
wrist_wave
wrist_wave_left
wave_left
wave_right
raise_hand_left
raise_hand_right
salute_left
salute_right
open_arms
nod
look
shake_head
listen_left
listen_right
present_left
present_right
hands_forward
ready_pose
small_cheer
dual_arm_gesture
```

程序流程：

```text
rt/lowstate
→ 读当前 13 关节姿态
→ ArmSdk 权重接管
→ minimum-jerk 关键帧
→ 全部 13 个 ArmSdk 关节温度 + IMU 检查
→ 回到起始姿态
→ 平滑释放 ArmSdk 权重
→ 计算回位误差
```

`dual_arm_gesture` 是为视频演示加入的显著动作：

```text
left shoulder pitch  +0.36 rad
right shoulder pitch -0.36 rad
left wrist roll      +0.72 rad
right wrist roll     -0.72 rad
然后回位
```

这些是固定编译时数值，不接受学生运行时修改角度或增益。

### 6.3 最小 demo 动作解析

`motion_core/demo.py` 有一套面向录像的简化中文规则解析，可识别自我介绍、前后左右移动、10°/20° 转向和多个上肢手势。还会展开：

- 欢迎
- 问候学生
- 邀请回答
- 回答正确
- 再试一次
- 开始上课
- 结束课程
- 能力展示

解析器在同一起点优先最长别名，例如“向左转二十度”不会再多产生一个 `turn_left_10`。

离线演示：

```bash
cd /home/henrick/具身智能课程第一部分/r1-agent-motion
PYTHONPATH=. .venv/bin/python scripts/r1_demo.py \
  "请介绍自己，然后向前走一步，向左转，再挥右手"
```

预期事件：

```text
SAY
MOVE
STOP
TURN
STOP
ARM
STOP
```

加 `--hardware --interface enp7s0` 后会直接调用项目固定真机二进制，因此不得把该选项用于无人值守或普通自动测试。

## 7. 真机已验证证据

### 7.1 网络和只读通路

已观测的隔离网段：

```text
教师电脑网卡：enp7s0
R1 controller：192.168.123.161
R1 PC1：       192.168.123.164
```

已通过：

- `.161/.164` ping，记录过 0% 丢包。
- FSM ID 读取，典型值 `811`。
- `rt/lowstate` 读到 35 路 motor state。
- 关节角、速度、温度和 IMU 反馈。

`r1-unitree-status` 曾经有一个隐蔽问题：`UnitreeR1Hardware` 析构时自动调用 `StopMove()`，使所谓只读诊断发生了写调用。已修复：现在状态工具退出时不再发送任何运动写命令。

### 7.2 ASR/TTS

- R1 内置 ASR 已识别中文自我介绍、危险动作拒绝和固定关节试验指令。
- 当前固件可以持续输出 `is_final=false`、confidence 约 `0.5`；本地已有稳定文本退化策略。
- R1 本地 TTS RPC 已返回 `0`，现场确认能听到。
- Agent 说话时不启动下一轮 ASR，连续模式在 TTS 返回后再继续，降低自回声。

### 7.3 单关节验证

已完成：

| 关节 | 相对位移 | 角度约值 | 结果 |
|---|---:|---:|---|
| 右 wrist roll 小幅 | `+0.12 rad` | `+6.9°` | 正常，已回位 |
| 右 wrist roll 目标幅度 | `+0.35 rad` | `+20.1°` | 正常，回位误差约 `0.00144 rad` |
| 右 shoulder pitch 小幅 | `-0.07 rad` | `-4.0°` | 正常，回位误差约 `0.01817 rad` |
| 右 shoulder pitch 目标幅度 | `-0.20 rad` | `-11.5°` | 正常，回位误差约 `0.0122 rad` |

右腕 `±45°` 被用户认为根据机械形态基本不会碰撞机身，项目已有 `examples/right-wrist-roll-plus-minus-45.json` 用于离线碰撞扫描，但这不等于 `±45°` 全行程已完成真机验收。

### 7.4 显著多关节上肢序列

已在真机上串行执行：

```text
wave_right
→ open_arms
→ dual_arm_gesture
```

实测结果：

```text
wave_right       return_error_rad=0.0230702
open_arms        return_error_rad=0.0208752
dual_arm_gesture return_error_rad=0.0214808
sequence_rc=0
```

执行后状态：

```text
connected=1
fsm_id=811
lowstate_fresh=1
```

执行后关键温度观测包括：

```text
head_pitch            51°C
left_shoulder_pitch   44°C
right_shoulder_pitch  42°C
right_shoulder_roll   39°C
right_elbow           37°C
right_wrist_roll      37°C
```

现场观测动作显著、双脚稳定、无异响且正常回位。这是开发 demo 证据，不代表动作库的全部动作已逐个验收或已是 `classroom_enabled`。

## 8. 重要踩坑记录

### 8.1 R1 `LocoClient` 必须在 ChannelFactory 之后构造

最初状态工具发生 segmentation fault，根因是在：

```cpp
ChannelFactory::Instance()->Init(...)
```

之前已经构造 `LocoClient`。修复方式是先初始化 ChannelFactory，再用 `std::unique_ptr` 延后构造 `LocoClient`。

### 8.2 不要把 G1 的控制切换接到 R1

官方 R1 SDK 是：

```text
unitree::robot::r1::LocoClient
service: sport
API version: 1.0.0.0
```

R1 官方接口中没有 G1 `SwitchToUserCtrl()` / `SwitchToInternalCtrl()`。实验中 G1 `SwitchToUserCtrl()` 在 R1 上返回：

```text
3203 = server API not implemented
```

该实验代码已移除，不要恢复。

官方核对来源已记录在 `docs/unitree-loco-adapter.md`。核对时官方 `unitree_sdk2` main 提交为：

```text
9754cd153af3da471b0fe5f3aa535e426fb11db3
```

### 8.3 R1 读 API 成功不代表写 API 可用

当前固件实测：

```text
GetFsmId()          -> success, 811
GetFsmMode()        -> failure
SetVelocity(...)    -> 127
StopMove()          -> 127
Start()/SetFsmId(811) -> 1001
```

`127` 未在已检查的 SDK2 R1 错误头文件中定义。2026-08-26 现场已确认：
官方原样例程和项目直连程序在返回 `127` 时都实际执行了 `0.5 m/s × 1 s`
前进。因此不再把 `127` 当作移动失败，但也不臆测它的精确语义；仍不自动调用
`Start()`。

可以做的下一步只读诊断是查询服务列表，但在获得 R1 官方固件说明前，不要使用 Go2/G1 的 `RobotStateClient::ServiceSwitch()` 猜测性开关 `sport_mode` / `ai_sport`。

### 8.4 `rt/lowstate` 包装器与 gRPC 的 fmt/spdlog 冲突

原来使用的 LowState wrapper 与 gRPC 链接时产生 `spdlog/fmt` 冲突。后来改为直接使用：

```cpp
ChannelSubscriber<unitree_hg::msg::dds_::LowState_>
```

这样 Unitree 适配器和 gRPC target 才能同时编译。不要在没有链接验证的情况下换回旧 wrapper。

### 8.5 “只读”工具必须检查析构和 RAII 副作用

已述的状态工具析构发 `StopMove()` 问题说明：不能只看 main 函数没有调写 API，还必须检查成员析构、scope guard 和底层 wrapper 的副作用。

### 8.6 自动测试曾意外调用真机

`tests/test_demo_hardware.py` 最初因为加入了默认二进制路径，曾在 pytest 中意外执行 `hands_forward` 和 `wrist_wave`。两个动作都正常回位，但这是测试设计错误。

已修复：当前测试对 `subprocess.run` 做 monkeypatch，不再调真机。下一个 Agent 在修改 `R1DemoHardware` 或该测试时，必须先确认 mock 仍生效，再运行全量 pytest。

### 8.7 头部零位/标定读数曾异常

曾在零力矩模式观察到 App 头部角度读数明显不符合实际姿态，包括视觉向前时读数约 `108°`。后来在正常“锁定站立”启动中，头部朝前时 App 和 LowState 约为 `0.19°`，后续反馈约 `0.003 rad`。

结论：

- 头部动作不应作为下一轮代表性真机序列首选。
- 需区分零力矩模式、正常锁定站立和传感器标定状态。
- 如果再出现异常，先只读对比 App、LowState、FSM 和实际方向，不用动作程序“纠正”头部。

### 8.8 当前 MJCF 不是完整 R1 真机映射

已发现：

- MJCF 有 `waist_roll` 和 `waist_yaw`。
- `rt/arm_sdk` 暴露 `waist_yaw`。
- 真机还暴露 `head_pitch/head_yaw`。
- 当前 MJCF 有头部 mesh，但没有正确建模头部关节/actuator。
- MJCF 有引用不存在 wrist body 的 contact exclusion。
- 当前仿真因此故意报 `all_armsdk_joints_mapped=false` 和 `invalid_contact_exclusions`。

在有合法来源的修正模型、35 路 LowState → 26 DOF → 13 ArmSdk → MJCF joint/actuator 映射和动力学阈值之前，不得将本地 MuJoCo 报告作为生成动作上真机的充分条件。

### 8.9 动作库、demo 动作和真机动作并非同一数据源

当前存在三个相关但尚未统一的定义：

1. `motion-library/actions.json`
2. `motion_core/demo.py` 中的 `DEMO_ACTIONS`
3. `hardware-tests/r1_fixed_action.cpp` 中的 `kMotions`

这会导致名称、数值和发布状态漂移。下一阶段应选一个单一源，由生成器产生 C++ 固定动作表或生成编译期头文件，而不是继续手工维护三份。

## 9. 当前最需解决的问题

### P0：打通可录像的完整 demo

1. 确认真机上肢固定动作二进制仍能构建。
2. 将 R1 ASR 文本输入接到最小 `DemoPlanner` 或用 DeepSeek 仅输出命名动作序列。
3. 保持 `SAY → MOVE → STOP → TURN → STOP → ARM → STOP` 串行执行。
4. 完成一次“自我介绍 + 显著上肢组合”语音演示。
5. 行走 API 未解决时，不要让 demo 谎称机器人已行走；可以将语音、拒绝和上肢演示先完成为稳定场景。

### P0：定位 R1 行走写 API 返回 `127`

建议路径：

1. 再次查阅 Unitree R1 当前固件对 `sport`/`ai_sport` 的版本要求和启用方式。
2. 确认当前 PC1 firmware、`ai_sport`、`vui_service` 和 module 版本，回填 `third_party_manifest.json`。
3. 必要时添加纯只读 service-list 工具，先观测服务名、status 和 protect。
4. 仅在 R1 官方文档明确要求时才调用 service switch。
5. 已验证 `0.5 m/s × 1 s` 前进；调用端需等待持续时间完成后再 `StopMove`，不得紧接取消。
6. 再测“能走、能停、能转”，不先做距离精度。

禁止方向：

- 不要将 G1 `SwitchToUserCtrl()` 加回来。
- 不要在固件问题未定位时降级到低层腿部 `LowCmd`。
- 不要在没有人看护的自动测试中调用 `r1-fixed-locomotion`。

### P1：把固定上肢动作接入 Gateway

当前最大的架构断点是：

```cpp
UnitreeR1Hardware::ExecuteInstalledAction(...) { return false; }
```

推荐重构：

- 把 `r1_fixed_action.cpp` 的 Runner 和动作表拆成可复用 C++ library。
- 独立真机测试程序和 Gateway 适配器都调用同一个 library。
- `ExecuteInstalledAction()` 只接受固定白名单 ID，不接受运行时关节数组。
- 动作完成、取消或失败均回位并释放 ArmSdk 权重。
- 补充硬件适配器 mock 测试，不得在 CTest 中创建 DDS publisher。

### P1：实现 Teacher Bridge 到 gRPC Gateway 客户端

- 从 `gateway/proto/r1_gateway.proto` 生成 Python stub。
- 实现 `GatewayClient` 协议的 status/validate/execute/cancel。
- 配置开发 mTLS 时只使用临时目录；`scripts/generate-dev-tls.sh` 可生成 7 天有效的开发证书，不得提交私钥。
- 先用模拟 RobotHardware 做端到端测试，再切 Unitree 后端。
- 在生产链路打通前，保留 `MockGatewayClient` fail closed 默认值。

### P1：统一动作定义

建议以一份版本化的 JSON/YAML 为单一源，生成：

- Python `DEMO_ACTIONS`
- C++ 固定动作表或 constexpr 头文件
- 动作库展示信息
- 别名和组合定义

同时分开：

- `implemented`
- `hardware_tested`
- `classroom_enabled`

不要再用一个含糊的“已有动作”状态表达三件事。

### P2：修正 R1 MJCF 和 26 DOF 映射

- 确认 R1 模型和 mesh 的来源、版本和再分发许可。
- 补齐 head pitch/yaw joint 和 actuator。
- 修正无效 wrist contact exclusion。
- 锁定 LowState 35 索引、26 整机关节、13 ArmSdk 关节和 MJCF actuator 映射。
- 建立双脚接触、浮动基座、支撑区、roll/pitch 和执行后稳定性检查。
- 模型门禁通过后才开始学生生成上肢动作的真机转化。

## 10. 建议的接手执行顺序

### 第一步：确认环境和基线，不运动

```bash
cd /home/henrick/具身智能课程第一部分/r1-agent-motion
git status --short
git log --oneline -5
git remote -v
PYTHONPATH=. .venv/bin/pytest -q
cmake --build build/gateway-full -j2
cmake --build build/hardware-tests -j2
ctest --test-dir build/gateway-full --output-on-failure
```

最近一次结果：

```text
Python: 40 passed
CTest:  5/5 passed
r1-gateway-grpc: built
r1-unitree-status: built
r1-fixed-locomotion: built
r1_fixed_action: built
```

Python 环境实际为 `.venv` 中 Python 3.13，项目声明要求 Python 3.11+。测试中有一条 FastAPI/Starlette `httpx` 弃用警告，不影响通过。

### 第二步：跑离线复合 demo

```bash
PYTHONPATH=. .venv/bin/python scripts/r1_demo.py \
  "请介绍自己，然后向前走一步，向左转，再挥右手"
```

确认输出为串行步骤，然后用危险指令复测：

```bash
PYTHONPATH=. .venv/bin/python scripts/r1_demo.py "跳舞后鞠躬"
```

必须拒绝且不产生 `ARM/MOVE/TURN`。

### 第三步：优先重构上肢执行共享库

不要继续复制第四份动作表。先将 `r1_fixed_action.cpp` 拆成 library，再接 Gateway。这是实现“Agent 通过 Skill 统一控机器人”的最短结构性路径。

### 第四步：只读定位行走 API

机器人开机后，先运行纯只读：

```bash
build/gateway-full/r1-unitree-status enp7s0
```

该工具修复后不会在退出时发 `StopMove`。如果增加 service list，也要保持纯只读。

### 第五步：行走解锁后按最小序列验证

```text
网络
→ FSM
→ LowState
→ 温度
→ Gateway 状态
→ 0.05 m/s × 0.5 s 前进
→ StopMove
→ turn_left_10
→ turn_right_10
→ 目标幅度移动
→ 上肢动作
→ 语音组合
```

任一步失败立即停止后续步骤。

## 11. 真机操作底线

用户曾要求开发阶段不再反复询问确认，但这只是当时现场有人、环境清空、急停在手和护栏就位的上下文，不能传递成未来无条件的永久授权。

新 Agent 必须在每次真机会话开始时重新确认：

```text
环境清空
急停在手
机器人稳定
当前测试幅度和方向已知
```

当前没有挂架。禁止跳跃、跑步、动态全身、长距离、单腿支撑和上肢/行走同步。发生抖动、异响、倾斜、意外位移、跟踪误差、高温或通信中断时立即物理急停，不自动重试。

## 12. 下一个 Agent 可直接复制的启动提示

```text
请接手 /home/henrick/具身智能课程第一部分/r1-agent-motion。

首先完整阅读 docs/agent-handoff-2026-08-26.md，然后阅读 README.md、
docs/unitree-loco-adapter.md、docs/hardware-validation-summary.md、
docs/hardware-test-workflow.md 和 skill/control-unitree-r1/SKILL.md。

当前优先目标是最小可演示系统：人类语音/文本 → Agent → Skill →
命名动作串行执行 → R1 TTS/上肢/受限行走。暂时不要扩建公网页面或
生产级审批细节。

先运行全部离线构建和测试，确保 tests/test_demo_hardware.py 仍 monkeypatch
subprocess.run，不要让 pytest 调用真机。

之后优先完成两件事：
1. 把 hardware-tests/r1_fixed_action.cpp 拆成共享 C++ 固定动作库，接入
   UnitreeR1Hardware::ExecuteInstalledAction()；
2. 继续用官方 R1 文档和纯只读服务状态诊断 SetVelocity/StopMove
   返回 127 的固件原因。

不要恢复 G1 SwitchToUserCtrl，不要降级到低层腿部 LowCmd，不要把
注册动作误报为已真机验证。任何真机运动前必须重新确认现场环境和
机器人当前状态。

当前 GitHub 远程是私有仓库 git@github.com:HenrickTeng/r1-agent-motion.git，
main 基线提交是 584faf4。保留用户已有改动，每次完成一个可验证单元后再
做原子提交和推送。
```

## 13. 一句话状态摘要

项目已有较完整的协议、安全平台骨架、语音通路、固定上肢动作器和最小 Agent 串行 demo，且显著上肢动作已通过真机；但生产 Gateway 还没有调用上肢动作，Teacher Bridge 仍是 mock Gateway，R1 当前固件又拒绝官方行走写 API，所以下一阶段应优先打通这三个断点，而不是继续扩大平台范围。

## 14. 2026-08-26 本轮移动诊断补充

- 前进/后退参数调整为 `±0.5 m/s × 2 s`；左右转为 `omega=±0.6 rad/s × 1 s`，各发送 3 次、间隔 1 秒。
- 前进此前只观察到小碎步；后退和单次纯角速度转向未观察到明确位移或转身。
- 转向前后各采集 5 次 yaw、间隔 200 ms，计算环形平均，仅作观察日志；不再用 IMU 数值宣称动作成功。
- 新版多脉冲参数尚未完成真机验收，后退和转向不可写成“已验证”。
- 测试期间 `enp7s0` 曾出现 `DOWN/NO-CARRIER`；真机复测前先确认网卡 `UP`、`connected=1`、`lowstate_fresh=1`，无链路时不要重试运动命令。
