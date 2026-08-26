# R1 简化碰撞预警

`r1ctl collision-scan` 使用 R1 MJCF 中 `collision` 类的 capsule/sphere 等代理几何，不把 `visual` STL mesh 当作碰撞体。它用于离线筛查自碰撞和接近干涉，不授权真机执行，也不替代正式模型审计。

## 自定义多关节动作

动作文件使用角度制，`action_name` 可以自定义。`base_pose_deg` 是相对模型默认姿态的基准角度，关键帧中的 `offsets_deg` 是相对基准的偏移；同一关键帧可以填写多个手臂关节：

```json
{
  "action_name": "my_two_arm_gesture",
  "title": "我的双臂动作",
  "units": "degrees",
  "base_pose_deg": {
    "right_shoulder_pitch": 13.0,
    "right_elbow": 45.9,
    "left_shoulder_pitch": 13.0,
    "left_elbow": 45.9
  },
  "keyframes": [
    {"time_s": 0.0, "offsets_deg": {"right_shoulder_pitch": 0, "left_shoulder_pitch": 0}},
    {"time_s": 2.0, "offsets_deg": {"right_shoulder_pitch": -20, "left_shoulder_pitch": -20, "right_elbow": 15, "left_elbow": 15}},
    {"time_s": 4.0, "offsets_deg": {"right_shoulder_pitch": 0, "left_shoulder_pitch": 0, "right_elbow": 0, "left_elbow": 0}}
  ]
}
```

允许的手臂关节是左右肩 pitch/roll/yaw、左右 elbow、左右 wrist roll。动作名称只用于报告和后续动作包标识；扫描器不会因为名称而授权执行。

## 扫描

```bash
./scripts/r1ctl collision-scan \
  --model "$UNITREE_R1_MODEL_DIR/r1.xml" \
  --file examples/right-wrist-roll-plus-minus-45.json \
  --sample-hz 50
```

默认阈值：最小距离大于等于 `30 mm` 为 `SAFE`，`10 mm <= 距离 < 30 mm` 为 `WARNING`，小于 `10 mm` 为 `DANGER`，MuJoCo 接触数量大于零为 `COLLISION`。同一刚体或父子刚体链上的相邻代理体不作为自碰撞候选，以免把正常机械连接误报为碰撞。

报告包含每个采样时刻的最小距离、最近代理体、接触数量和状态，并始终输出 `hardware_authorized=false`。当前外部 MJCF 的头部关节缺失、接触排除项不完整，因此报告中的模型警告必须保留。
