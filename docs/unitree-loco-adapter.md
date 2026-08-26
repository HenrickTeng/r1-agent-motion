# R1 Unitree LocoClient 适配器

## 官方接口核对

本适配器仅使用 Unitree SDK2 的 R1 官方高层运动接口：

- `unitree::robot::r1::LocoClient`
- 服务名 `sport`
- API 版本 `1.0.0.0`
- `GetFsmId` (`7001`)
- `GetFsmMode` (`7002`)
- `SetFsmId` (`7101`)
- `SetVelocity` (`7105`)
- `SetSpeedMode` (`7107`)

核对来源是 Unitree Robotics 官方 `unitree_sdk2` 仓库 `main` 分支，2026-08-26 访问时提交为 `9754cd153af3da471b0fe5f3aa535e426fb11db3`：

- <https://github.com/unitreerobotics/unitree_sdk2/blob/main/include/unitree/robot/r1/loco/r1_loco_client.hpp>
- <https://github.com/unitreerobotics/unitree_sdk2/blob/main/include/unitree/robot/r1/loco/r1_loco_api.hpp>
- <https://github.com/unitreerobotics/unitree_sdk2/blob/main/example/r1/high_level/r1_loco_client_example.cpp>

R1 官方接口中没有 G1 的 `SwitchToUserCtrl()` / `SwitchToInternalCtrl()`，因此适配器不得调用 G1 控制模式切换 API。实测中 G1 `SwitchToUserCtrl()` 在该 R1 固件上返回 `3203`（server API not implemented），这不是 R1 行走的前置步骤。

## 构建

The adapter is an optional build target. The default Gateway remains fail-closed and does not load the SDK.

```bash
export UNITREE_SDK2_DIR=/home/henrick/unitree_sdk2-main
cmake -S gateway -B build/gateway-unitree \
  -DR1_GATEWAY_BUILD_UNITREE=ON \
  -DR1_GATEWAY_BUILD_TESTS=OFF \
  -DUNITREE_SDK2_DIR="$UNITREE_SDK2_DIR"
cmake --build build/gateway-unitree -j2
```

运动前先在有线网卡上执行纯只读状态探测：

```bash
build/gateway-unitree/r1-unitree-status enp7s0
```

该命令只调用 `GetFsmId`、`GetFsmMode` 并订阅 `rt/lowstate`；退出时不会发送 `StopMove` 或其他写命令。

适配器只有在 `GetFsmId` 成功、FSM 为 `811` 且 `rt/lowstate` 新鲜时才允许执行。部分 R1 固件的可选 `GetFsmMode` 查询会失败；程序保留该诊断信息，但不会在 FSM ID 和 LowState 健康时将机器人误判为断开。`MoveFor` 在有界时间结束、取消或故障后调用 `StopMove`。`TurnRelative` 使用 `rt/lowstate` yaw 闭环，限制角速度，在 1.5° 容差或超时时停车。

## 当前真机兼容性

当前 R1 实测结果：

- `GetFsmId()` 成功，返回 `811`。
- `rt/lowstate` 正常输出。
- `GetFsmMode()` 在当前固件上失败。
- 官方 R1 `SetVelocity()` 和 `StopMove()` 均返回 `127`，机器人未产生显著位移。
- `127` 未在当前 SDK2 R1 错误头文件中定义，不能在项目中臆测为某个具体故障。

因此代码已接入官方 R1 API，但当前机器人固件/服务尚未完成行走写接口验收。在 Unitree 确认当前 R1 固件的服务开启条件前，不使用 Go2/G1 的 `RobotStateClient::ServiceSwitch` 猜测性切换服务，也不降级到低层腿部控制。

当主机安装 gRPC/Protobuf C++ 开发包时，同一构建会产生链接真机适配器的 `r1-gateway-grpc`。未确认现场检查表时不得执行运动测试。
