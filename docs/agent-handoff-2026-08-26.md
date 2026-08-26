# R1 Agent Motion 交接记录（2026-08-26）

## 当前进度

- 已打通电脑麦克风 → 本地 Vosk ASR → 规则 Agent → TTS → 固定白名单动作。
- 已接入 R1 高层 `LocoClient` RPC；不使用低层腿部 `LowCmd`，不执行上肢与行走同步。
- 前进、后退、左转、右转均已加入语音动作映射和 DIY 直接执行白名单。
- 上肢动作幅度已按需求放大：右腕 `+1.70 rad`、右肩 `-2.00 rad`；两者仍保持 `draft`，未以新幅度完成真机验收。

## 移动实测结论

- `SetVelocity(0.5, 0, 0, 1)` 曾只观察到小碎步前进。
- 后退和单次纯角速度转向此前没有观察到明确位移或转身。
- RPC 返回值 `127` 只能说明固件接口返回结果，不能单独证明机器人真的移动。
- 新版参数已调整为：前进/后退 `±0.5 m/s × 2 s`；左右转 `omega=±0.6 rad/s × 1 s`，各发送 3 次，脉冲间隔 1 秒。
- 转向前后各采集 5 次 yaw、间隔 200 ms，计算环形平均，仅作为观察日志；不再用 IMU 数值判断动作成功，最终以现场观察为准。
- 新版多脉冲参数尚未完成真机验收，后退和转向不可写成“已验证”。

## 网络注意事项

测试期间网卡曾出现 `enp7s0 DOWN / NO-CARRIER`，导致一次新版左转在发送 RPC 前取消。继续真机测试前先确认：

```bash
ip -brief address show enp7s0
./build/gateway-full/r1-unitree-status enp7s0
```

需要看到网卡为 `UP`、地址通常为 `192.168.123.99/24`，并且 `connected=1`、`lowstate_fresh=1`。机器人不在现场或无链路时不要重试运动命令。

## 验证与后续

离线测试曾通过 C++ Gateway `7/7`、Python 约 `75/75`。本轮提交前建议重新编译并运行：

```bash
cmake --build build/gateway-full -j2
cmake --build build/gateway-tests -j2
ctest --test-dir build/gateway-tests --output-on-failure
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q
git diff --check
```

